# SPDX-License-Identifier: GPL-3.0-or-later
"""The watchdog and its bar module, executed rather than read.

Both regressions these tests exist for are invisible to a text-level
assertion, because both templates read perfectly sensibly:

  * `detect_gateway()` returns "" for a default route that has no `via`
    ("default dev tun0" - a VPN, a PPP link, any point-to-point route).
    check_and_repair() read that as "no default route" and repaired: ARP
    flushed, interface down and up, NetworkManager reapplied - every ten
    seconds, on a link that was never broken. And where the branch was
    actually needed - genuinely no default route - detect_iface() reads
    the same empty output, so restart_network() bailed at its own
    interface check and nothing was repaired at all.
  * The shell scanned EVERY line of `ip route show default` for the
    keyword while the Python read only the first, so two default routes
    made the service report a healthy connection and the bar report the
    host as down, over the same machine at the same moment.

Nothing but running the generated artifacts catches either. So the
templates are generated into tmp_path and executed with `ip`, `ping`,
`sudo`, `nmcli`, `systemctl`, `sleep`, `mkdir`, `date` and `tee` replaced
by recording stubs.

Safety: every child is started through `env -i`, with PATH set to the
stub directory and NOTHING else, and _child_path() asserts that before
each run. A command with no stub therefore fails with "command not
found"; it cannot fall through to the real `sudo`, `ip` or `nmcli` on the
machine running the tests. The stubs themselves are pure bash - none of
them execs a real binary - and every address used here is from a
documentation range (RFC 5737), so even a stub that somehow leaked would
have nowhere to go.
"""
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

# The shared backstop, from tests/conftest.py: a command the stub
# directory does not provide has to be a failure, not an empty string.
import conftest

SRC = Path(__file__).resolve().parents[2] / "src"

# TEST-NET-2 and TEST-NET-3: reserved for documentation, routed nowhere.
TEST_HOST = "198.51.100.1"
SECOND_ROUTE_GATEWAY = "203.0.113.1"

# The interpreter is named absolutely, so finding it never depends on the
# stub PATH the child is given.
BASH = "/bin/bash"
ENV = "/usr/bin/env"


# --------------------------------------------------------------------
# stubs
# --------------------------------------------------------------------

def _write_stub(directory: Path, name: str, body: str, calls: Path) -> None:
    """One executable stub that records its call and then answers.

    Recording first and unconditionally: a test that asserts a command
    did NOT run is only worth anything if every run would have been
    written down.
    """
    script = (
        "#!/bin/bash\n"
        "# Test stub. Records the call; never reaches the real command.\n"
        f"printf '{name} %s\\n' \"$*\" >> '{calls}'\n"
        + body
    )
    path = directory / name
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def _write_plain_stub(directory: Path, name: str, body: str) -> None:
    """A stub that is not recorded.

    `date` and `tee` are text plumbing for log(); writing them into the
    transcript would bury the network commands the assertions are about.
    They are still stubs, not the real binaries - `tee` here is a bash
    loop and `date` a constant, so the transcript stays reproducible.
    """
    path = directory / name
    path.write_text("#!/bin/bash\n" + body, encoding="utf-8")
    path.chmod(0o755)


def make_stubs(tmp_path: Path, route: str, reachable) -> tuple[Path, Path]:
    """Build the stub directory. Returns (stub directory, transcript)."""
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    calls = tmp_path / "calls.txt"

    route_file = tmp_path / "route.txt"
    route_file.write_text(route, encoding="utf-8")
    reachable_file = tmp_path / "reachable.txt"
    reachable_file.write_text("".join(f"{h}\n" for h in reachable), encoding="utf-8")

    _write_stub(stubs, "ip", f"""
if [ "$1" = "route" ]; then
    while IFS= read -r line; do printf '%s\\n' "$line"; done < '{route_file}'
    exit 0
fi
if [ "$1" = "-4" ] && [ "$2" = "addr" ]; then
    printf '    inet 198.51.100.7/24 brd 198.51.100.255 scope global %s\\n' "$4"
    exit 0
fi
exit 0
""", calls)

    _write_stub(stubs, "ping", f"""
target="${{@: -1}}"
while IFS= read -r host; do
    if [ "$host" = "$target" ]; then exit 0; fi
done < '{reachable_file}'
exit 1
""", calls)

    # Deliberately does NOT run what it was handed. A stub that executed
    # its arguments would put the real `ip` back in reach through sudo.
    _write_stub(stubs, "sudo", "exit 0\n", calls)
    _write_stub(stubs, "nmcli", "exit 0\n", calls)
    _write_stub(stubs, "systemctl", "printf 'active\\n'\nexit 0\n", calls)
    # A no-op, so a repair costs no six seconds of test time.
    _write_stub(stubs, "sleep", "exit 0\n", calls)
    # The log directory is created by the fixture; this only has to exist.
    _write_stub(stubs, "mkdir", "exit 0\n", calls)

    _write_plain_stub(stubs, "date", "printf '2026-01-01 00:00:00\\n'\n")
    _write_plain_stub(stubs, "tee", """
target="${@: -1}"
while IFS= read -r line; do
    printf '%s\\n' "$line"
    printf '%s\\n' "$line" >> "$target"
done
""")

    return stubs, calls


# --------------------------------------------------------------------
# generation and execution
# --------------------------------------------------------------------

@pytest.fixture
def generate(tmp_path, monkeypatch):
    """Generate a watchdog template into tmp_path, unconfigured.

    The three watchdog settings are overridden rather than read from the
    machine running the tests: someone who HAS configured a gateway would
    otherwise exercise a different branch than someone who has not, and
    the run-time detection - which is what is under test - would never be
    reached at all.
    """
    monkeypatch.syspath_prepend(str(SRC))
    import template_processor

    styles = dict(template_processor.STYLE_VARIABLES)
    styles["STYLE_WATCHDOG_GATEWAY"] = ""
    styles["STYLE_WATCHDOG_INTERFACE"] = ""
    styles["STYLE_WATCHDOG_TEST_HOST"] = TEST_HOST
    processor = template_processor.ConfigProcessor(styles=styles)

    def build(template: str, output: str) -> Path:
        path = tmp_path / output
        processor.apply_template(SRC / "templates" / f"{template}.template", path)
        path.chmod(0o755)
        return path

    return build


def _child_path(stubs: Path) -> str:
    """The PATH the child gets - the stub directory and nothing else.

    Asserted here rather than trusted, because this is the whole safety
    argument: with no other directory on PATH, a command this test forgot
    to stub fails with "command not found" instead of quietly running the
    real one against the developer's machine.
    """
    path = str(stubs)
    assert path.split(os.pathsep) == [str(stubs)]
    assert not os.environ.get("PATH", "").startswith(path), (
        "the stub directory must not be part of the parent's PATH either"
    )
    return path


def run_child(argv, stubs: Path, home: Path) -> subprocess.CompletedProcess:
    """Run argv under `env -i` with only the stub directory on PATH.

    HOME is handed over too - the watchdog writes its log below it, and
    an unset HOME would send that write to the filesystem root.
    """
    home.mkdir(parents=True, exist_ok=True)
    (home / ".local" / "log").mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [ENV, "-i", f"PATH={_child_path(stubs)}", f"HOME={home}", *argv],
        # env={} rather than the caller's environment, so `env -i` starts
        # from nothing at all rather than from whatever pytest inherited.
        env={},
        input="",
        capture_output=True,
        text=True,
        timeout=60,
    )
    # An artifact reaching for a command with no stub is a hole in this
    # harness, and a silent one: the failed call usually just yields an
    # empty string, which the parsers read as "no route" - the very state
    # under test.
    conftest.assert_no_missing_command(result)
    return result


def calls_of(calls: Path, command: str) -> list[str]:
    if not calls.exists():
        return []
    return [line for line in calls.read_text(encoding="utf-8").splitlines()
            if line.split(" ", 1)[0] == command]


def transcript(calls: Path) -> list[str]:
    if not calls.exists():
        return []
    return calls.read_text(encoding="utf-8").splitlines()


REPAIR_COMMANDS = ("sudo", "nmcli")


# --------------------------------------------------------------------
# the service
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_a_point_to_point_route_that_works_is_left_alone(generate, tmp_path):
    """The first regression, measured.

    Before the fix this same run recorded, in order: sudo ip neigh flush
    dev tun0, sudo ip link set tun0 down, sudo ip link set tun0 up, sudo
    nmcli device reapply tun0 - and then logged "Internet
    wiederhergestellt!" over a connection that was never down. In daemon
    mode that repeats every ten seconds, forever.
    """
    script = generate("network-watchdog-config", "network-watchdog.sh")
    stubs, calls = make_stubs(tmp_path, "default dev tun0\n", [TEST_HOST])

    result = run_child([BASH, str(script), "--once"], stubs, tmp_path / "home")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Alles OK" in result.stdout
    repairs = [line for line in transcript(calls)
               if line.split(" ", 1)[0] in REPAIR_COMMANDS]
    assert repairs == [], "a healthy point-to-point link was repaired: " + "; ".join(repairs)
    assert "wiederhergestellt" not in result.stdout


@pytest.mark.allow_subprocess
def test_a_point_to_point_route_without_internet_is_repaired(generate, tmp_path):
    """The other half of the same branch: no gateway to ping means the
    internet probe decides alone - and it says no."""
    script = generate("network-watchdog-config", "network-watchdog.sh")
    stubs, calls = make_stubs(tmp_path, "default dev tun0\n", [])

    result = run_child([BASH, str(script), "--once"], stubs, tmp_path / "home")

    assert result.returncode == 1
    sudo = calls_of(calls, "sudo")
    assert "sudo ip neigh flush dev tun0" in sudo
    assert "sudo ip link set tun0 down" in sudo
    assert "sudo ip link set tun0 up" in sudo
    assert "sudo nmcli device reapply tun0" in sudo
    assert "Reparatur fehlgeschlagen" in result.stdout


@pytest.mark.allow_subprocess
def test_no_default_route_at_all_reaches_the_repair(generate, tmp_path):
    """The case the branch was written for, and what it can actually do.

    With no default route there is also no interface to act on, so
    restart_network() stops at its own check and the run reports the
    failure instead of pretending. What this test can prove is that the
    branch is ENTERED and reported - the repair is attempted rather than
    skipped, and the log names both the missing route and the missing
    interface. What it cannot prove is that a repair helps: there is
    nothing here to repair with unless the user configured an interface,
    and inventing one would test the stub rather than the watchdog.
    """
    script = generate("network-watchdog-config", "network-watchdog.sh")
    stubs, calls = make_stubs(tmp_path, "", [])

    result = run_child([BASH, str(script), "--once"], stubs, tmp_path / "home")

    assert result.returncode == 1
    assert "Keine Default-Route" in result.stdout
    assert "Starte Netzwerk-Reparatur" in result.stdout
    assert "Kein Netzwerk-Interface ermittelbar" in result.stdout
    assert "Reparatur fehlgeschlagen" in result.stdout
    assert calls_of(calls, "sudo") == [], (
        "nothing may be reconfigured when no interface could be determined"
    )


# --------------------------------------------------------------------
# der Dienst auf zwei Routen
# --------------------------------------------------------------------

TWO_ROUTES = (
    "default dev tun0 scope link\n"
    f"default via {SECOND_ROUTE_GATEWAY} dev eth0 metric 600\n"
)


@pytest.mark.allow_subprocess
def test_the_service_reads_only_the_first_default_route(generate, tmp_path):
    """Die zweite Regression, gemessen am Dienst.

    Er durchsuchte JEDE Zeile nach dem Schluesselwort, nahm also das
    Gateway aus Zeile 2 und das Interface aus Zeile 1: eine Reparatur
    haette tun0 ab- und angeschaltet, um das Gateway von eth0 zu
    berichtigen.

    HIER STAND EINE ZWEITE HAELFTE, UND SIE IST WEG
        Dieselbe Messung lief gegen watchdog-status.py, das Leistenmodul
        mit dem Herzsymbol. Es ist am 11.08.2026 geloescht worden
        ("herz und schild in der waybar oben kommen weg"), und mit ihm
        die einzige zweite Stelle, die diese Routenzeile las. Die dritte
        - das Diagnoseskript - steht weiter unten und wird dort gegen
        genau dieselben zwei Zeilen gehalten.
    """
    script = generate("network-watchdog-config", "network-watchdog.sh")

    # Gesund: nichts darf gemeldet werden.
    healthy = tmp_path / "healthy"
    healthy.mkdir()
    stubs, calls = make_stubs(healthy, TWO_ROUTES, [TEST_HOST])
    shell = run_child([BASH, str(script), "--once"], stubs, healthy / "home")

    assert shell.returncode == 0, shell.stdout + shell.stderr
    healthy_calls = transcript(calls)

    # Kaputt: es muss tun0 sein, das angefasst wird.
    broken = tmp_path / "broken"
    broken.mkdir()
    stubs, calls = make_stubs(broken, TWO_ROUTES, [])
    run_child([BASH, str(script), "--once"], stubs, broken / "home")

    assert "sudo ip link set tun0 down" in calls_of(calls, "sudo")
    assert "sudo ip link set tun0 up" in calls_of(calls, "sudo")
    broken_calls = transcript(calls)

    # In keinem der beiden Zustaende darf ein Feld der zweiten Zeile mit
    # einem der ersten gepaart werden.
    for line in healthy_calls + broken_calls:
        assert "eth0" not in line, f"a field was taken from the second route: {line}"
        assert SECOND_ROUTE_GATEWAY not in line, (
            f"the second route's gateway was used: {line}")


# --------------------------------------------------------------------
# the diagnostic script - the third artifact reading the same route
# --------------------------------------------------------------------
#
# It is the tool a user runs when the bar says something is wrong, so it
# is the one place the two halves' answer gets checked by hand. It had
# the same two defects: it scanned every line for `via`, and it read an
# empty gateway as "keine Default-Route vorhanden" - on a working
# point-to-point link.
#
# It parses with `head` and `awk` rather than the pure-bash reader the
# service uses, so those two have to be reachable. They are provided as
# stubs that exec the real binary at an absolute path resolved here:
# PATH still holds nothing but the stub directory, and the allowlist is
# read-only text tools that cannot touch the network, the disks or
# privileges. `sudo`, `ip` and `nmcli` stay fake.

REAL_TOOLS = ("head", "awk", "grep")


def _passthrough_tools(stubs: Path) -> None:
    import shutil as _shutil

    for name in REAL_TOOLS:
        conftest.assert_safe_to_passthrough(name)
        real = _shutil.which(name)
        assert real, f"the diagnostic script needs {name}"
        stub = stubs / name
        stub.write_text(f'#!/bin/bash\nexec "{real}" "$@"\n', encoding="utf-8")
        stub.chmod(0o755)


def _run_diagnostic(generate, tmp_path, route, reachable):
    script = generate("network-diagnostic-config", "network-diagnostic.sh")
    stubs, calls = make_stubs(tmp_path, route, reachable)
    _passthrough_tools(stubs)
    # The script clears the terminal on entry. Nothing to record.
    _write_plain_stub(stubs, "clear", "exit 0\n")
    # The unreachable-internet branch runs
    #     traceroute ... 2>&1 | head -15 | tee -a "$LOG_FILE"
    # and there was no traceroute stub. Four of the five tests below take
    # that branch, so on every run bash wrote "traceroute: command not
    # found" - onto STDOUT, because of the 2>&1 - and the harness check
    # that exists to catch exactly this was reading stderr alone. A
    # probe that leaves the machine is the one thing these stubs are
    # here to prevent, and it was the one command that had no stub.
    _write_stub(stubs, "traceroute", """
printf ' 1  198.51.100.1  0.4 ms\\n'
printf ' 2  * * *\\n'
exit 0
""", calls)
    # log() pipes through `tee` into /tmp; the stub sends it to the test's
    # own directory instead, so a run leaves nothing behind outside it.
    _write_plain_stub(stubs, "tee", f"""
while IFS= read -r line; do
    printf '%s\\n' "$line"
    printf '%s\\n' "$line" >> '{tmp_path / "diagnostic.log"}'
done
""")
    result = run_child([BASH, str(script)], stubs, tmp_path / "home")
    return result, calls


@pytest.mark.allow_subprocess
def test_the_diagnostic_does_not_call_a_working_p2p_link_routeless(
        generate, tmp_path):
    """"default dev tun0" is a default route. It just has no gateway.

    Before the fix an empty gateway meant both things at once, so a
    healthy VPN or mobile connection was diagnosed "Kein Gateway
    ermittelbar - keine Default-Route vorhanden" - which sends the user
    looking for a fault that is not there.
    """
    result, calls = _run_diagnostic(
        generate, tmp_path, "default dev tun0\n", [TEST_HOST, "archlinux.org"])

    assert "Keine Default-Route vorhanden" not in result.stdout, result.stdout
    assert "Punkt-zu-Punkt" in result.stdout, result.stdout
    assert "default dev tun0" in result.stdout, result.stdout
    # Nothing to ping, so it must not have invented a target: the only
    # pings are the two internet probes.
    for call in calls_of(calls, "ping"):
        assert TEST_HOST in call or "archlinux.org" in call, call


@pytest.mark.allow_subprocess
def test_the_diagnostic_still_reports_a_genuinely_missing_route(
        generate, tmp_path):
    result, _ = _run_diagnostic(generate, tmp_path, "", [])

    assert "Keine Default-Route vorhanden" in result.stdout, result.stdout
    assert "KEINE Default Route gefunden" in result.stdout, result.stdout


@pytest.mark.allow_subprocess
def test_the_diagnostic_checks_an_ordinary_gateway(generate, tmp_path):
    route = f"default via {TEST_HOST} dev eth0 metric 100\n"
    result, calls = _run_diagnostic(generate, tmp_path, route, [TEST_HOST])

    assert f"Gateway {TEST_HOST} erreichbar" in result.stdout, result.stdout
    assert any(TEST_HOST in call for call in calls_of(calls, "ping"))


@pytest.mark.allow_subprocess
def test_the_diagnostic_names_the_same_gateway_as_the_service(
        generate, tmp_path):
    """Zwei Artefakte, eine Routenzeile.

    The diagnostic scanned every line for `via`, so on these two routes
    it named 203.0.113.1 while the service - which selects the first
    line - was talking about tun0. A diagnostic that contradicts the
    thing it diagnoses is worse than no diagnostic.
    """
    result, calls = _run_diagnostic(
        generate, tmp_path, TWO_ROUTES, [TEST_HOST, SECOND_ROUTE_GATEWAY])

    assert SECOND_ROUTE_GATEWAY not in result.stdout, result.stdout
    for line in transcript(calls):
        assert SECOND_ROUTE_GATEWAY not in line, (
            f"the second route's gateway was used: {line}")


@pytest.mark.allow_subprocess
def test_the_diagnostic_traces_the_route_only_when_the_internet_is_gone(
        generate, tmp_path):
    """The branch the harness was silently failing inside.

    The deeper analysis is what a user runs this tool FOR, and it costs a
    probe that leaves the machine - so it has to happen when the internet
    is unreachable and must not happen when it is. Neither half was
    measured: there was no traceroute stub at all, so every run of this
    branch reached for a command that was not there, got nothing, and
    reported the same as a run that traced successfully.

    "archlinux.org" is the template's own INTERNET_TEST, and it is checked
    here rather than assumed: a stub answering for one name while the
    script asks about another is the same hole in a quieter form.
    """
    route = f"default via {TEST_HOST} dev eth0 metric 100\n"

    _, gone = _run_diagnostic(generate, tmp_path, route, [TEST_HOST])
    traces = calls_of(gone, "traceroute")
    assert len(traces) == 1, traces
    assert "archlinux.org" in traces[0], traces

    working = tmp_path / "reachable"
    working.mkdir()
    _, fine = _run_diagnostic(generate, working,
                              route, [TEST_HOST, "archlinux.org"])
    assert calls_of(fine, "traceroute") == [], (
        "a working connection was traced anyway")


@pytest.mark.allow_subprocess
def test_the_diagnostic_shows_the_route_it_took_the_gateway_from(
        generate, tmp_path):
    """One query, not two.

    The displayed route came from `ip route | grep default | head -1` -
    the whole routing table, filtered for a word - while the gateway came
    from `ip route show default`. The two could name different routes,
    and the variable holding the first silently overwrote the second.
    """
    route = f"default via {TEST_HOST} dev eth0 metric 100\n"
    result, _ = _run_diagnostic(generate, tmp_path, route, [TEST_HOST])

    assert f"Default Route: default via {TEST_HOST} dev eth0" in result.stdout


# --------------------------------------------------------------------
# what Task 5 removed must not walk back in
# --------------------------------------------------------------------

# The previous employer's virtual machine: its interface, its subnet, its
# gateway - plus the two shapes a private home network is written in that
# would be just as wrong on somebody else's machine. Neither the device
# name marker in test_inventory.py nor the address marker in
# test_vpn_config.py covers any of these; the latter deliberately
# excludes 10.10.10.x.
#
# The interface name is word-bounded so that a longer name that merely
# contains it cannot trip this.
PERSONAL_VALUES = (
    re.compile(r"\bens18\b"),
    re.compile(r"10\.10\.10\."),
    re.compile(r"192\.168\.10\.1"),
    re.compile(r"192\.168\.178"),
    re.compile(r"Heimnetzwerk", re.IGNORECASE),
)


def test_no_template_carries_a_personal_network_value():
    offenders = []
    for path in sorted((SRC / "templates").glob("*.template")):
        for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1):
            for pattern in PERSONAL_VALUES:
                if pattern.search(line):
                    offenders.append(f"{path.name}:{number} ({pattern.pattern})")
    assert offenders == [], (
        "personal network values in templates: " + "; ".join(offenders))
