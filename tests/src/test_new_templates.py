# SPDX-License-Identifier: GPL-3.0-or-later
"""The two generic replacements, executed rather than read.

Task 1 deleted five templates that each drove one device or one place:
two printer installers carrying a vendor driver apiece, a status script
naming the same device again, and two weather scripts with a city
written into the URL. The two templates here replace all five, so what
matters about them is not that they mention `lpstat` or `wttr.in` - it
is what they DO when there is no printer, when there are three, when the
weather service answers with rubbish, and when it does not answer at
all. A `"x" in text` assertion proves none of that, so both templates
are generated into tmp_path and run.

Safety, the same argument as in test_network_watchdog.py: every child
starts through `env -i` with PATH set to the stub directory and nothing
else, asserted before each run. A command with no stub therefore fails
with "command not found" instead of reaching the real `curl` or
`lpadmin` on the machine running the tests. No test makes a network
request: `curl` is a bash stub that reads its answer from a file.

`sudo` IS stubbed, and that is a deliberate reversal. It used to be left
out on the argument that "with no stub any attempt is a hard failure
rather than a password prompt nobody sees" - true about safety, and
worthless as a test. The dialog's own guarantee is asserted by reading a
transcript the STUBS write, and a command with no stub writes nothing
into it, so `calls_of(transcript, "sudo") == []` was `[] == []` for
every template that could ever be put in front of it. Measured:
inserting `sudo systemctl restart cups &>/dev/null` into the template
left the whole suite green.

The stub records the attempt and then REFUSES. It never execs what it
was handed, so nothing reaches the real `sudo` through it, and a dialog
that came to depend on it fails its own tests instead of passing
quietly. Both halves matter on this machine, where a failed sudo locks
the account out.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

# The shared backstop, from tests/conftest.py: a command the stub
# directory does not provide has to be a failure, not an empty string.
import conftest

from tests.origin_data import ORIGIN, PLACES
# The one list of commands that must never reach the running
# session, derived from the generator's own source over there.
from tests.src.test_generate import SESSION_COMMANDS

SRC = Path(__file__).resolve().parents[2] / "src"
TEMPLATES = SRC / "templates"
STYLES = SRC / "styles"

# Named absolutely, so finding the interpreter never depends on the stub
# PATH the child is given.
BASH = "/bin/bash"
ENV = "/usr/bin/env"

PRINTER_TEMPLATE = "printer-manager-config"
WEATHER_TEMPLATE = "bar-weather-config"

# A location that is a location and nothing else: no city this project
# was ever pointed at, and no real place whose name could be mistaken for
# a leftover.
TEST_LOCATION = "Musterstadt"

# One current_condition, which is all the module reads.
def wttr_response(temp="7", code="116", desc="Partly cloudy") -> str:
    return json.dumps(
        {
            "current_condition": [
                {
                    "temp_C": temp,
                    "weatherCode": code,
                    "weatherDesc": [{"value": desc}],
                }
            ]
        }
    )


# --------------------------------------------------------------------
# generation
# --------------------------------------------------------------------

@pytest.fixture
def generate(tmp_path, monkeypatch):
    """Generate one of the two templates into tmp_path.

    The weather location is passed in rather than read from the machine
    running the tests: a developer who has configured one would otherwise
    exercise a different branch than a developer who has not, and the
    unconfigured branch - which is the one that decides whether anything
    is sent to a third party at all - would never be reached.
    """
    monkeypatch.syspath_prepend(str(SRC))
    import template_processor

    def build(template: str, output: str, *, styles: dict | None = None) -> Path:
        merged = dict(template_processor.STYLE_VARIABLES)
        merged.update(styles or {})
        processor = template_processor.ConfigProcessor(styles=merged)
        path = tmp_path / output
        processor.apply_template(TEMPLATES / f"{template}.template", path)
        # apply_template raises on an unresolved placeholder, so this can
        # only fail if it ever stops doing so. It is the property the
        # whole SSOT arrangement exists for, and it costs one line.
        assert "{{" not in path.read_text(encoding="utf-8")
        path.chmod(0o755)
        return path

    return build


def icons(monkeypatch):
    monkeypatch.syspath_prepend(str(SRC))
    import icons_db

    return icons_db.ALL_ICONS


# --------------------------------------------------------------------
# stubs
# --------------------------------------------------------------------

def _write_stub(directory: Path, name: str, body: str, calls: Path) -> None:
    """One executable stub that records its call and then answers.

    Recording first and unconditionally: a test asserting a command did
    NOT run is only worth something if every run would have been written
    down.
    """
    script = (
        "#!/bin/bash\n"
        "# Test stub. Records the call; never reaches the real command.\n"
        f"printf '{name} %s\\n' \"$*\" >> '{calls}'\n" + body
    )
    path = directory / name
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def _passthrough(directory: Path, name: str) -> None:
    """A stub that execs the real binary at an absolute path.

    Only for read-only text tools and for `mkdir`, whose every argument
    in these tests lies inside tmp_path. PATH still holds nothing but the
    stub directory, so nothing else can be reached this way.
    """
    conftest.assert_safe_to_passthrough(name)
    real = shutil.which(name)
    assert real, f"the artifact needs {name}"
    stub = directory / name
    stub.write_text(f'#!/bin/bash\nexec "{real}" "$@"\n', encoding="utf-8")
    stub.chmod(0o755)


def _child_path(stubs: Path) -> str:
    """The PATH the child gets - the stub directory and nothing else."""
    path = str(stubs)
    assert path.split(os.pathsep) == [str(stubs)]
    assert not os.environ.get("PATH", "").startswith(path), (
        "the stub directory must not be part of the parent's PATH either"
    )
    return path


def run_child(argv, stubs: Path, home: Path, **extra) -> subprocess.CompletedProcess:
    home.mkdir(parents=True, exist_ok=True)
    environment = {"PATH": _child_path(stubs), "HOME": str(home)}
    environment.update(extra)
    result = subprocess.run(
        [ENV, "-i", *(f"{k}={v}" for k, v in environment.items()), *argv],
        env={},
        input="",
        capture_output=True,
        text=True,
        timeout=60,
    )
    conftest.assert_no_missing_command(result)
    return result


def transcript(calls: Path) -> list[str]:
    if not calls.exists():
        return []
    return calls.read_text(encoding="utf-8").splitlines()


def calls_of(calls: Path, command: str) -> list[str]:
    return [line for line in transcript(calls) if line.split(" ", 1)[0] == command]


# --------------------------------------------------------------------
# the printer dialog
# --------------------------------------------------------------------

DEFAULT_DEVICES = (
    "network ipp://printer.invalid/ipp/print \"Unknown\" \"Ein Netzwerkdrucker\"\n"
    "direct usb://Generic/Printer?serial=1 \"Unknown\" \"Ein USB-Drucker\"\n"
    "file cups-pdf:/ \"Unknown\" \"PDF\"\n"
)


@pytest.fixture
def printer_stubs(tmp_path):
    """Build the CUPS stub directory. Returns a small control object."""
    stubs = tmp_path / "printer-stubs"
    stubs.mkdir()
    calls = tmp_path / "printer-calls.txt"

    printers = tmp_path / "printers.txt"
    printers.write_text("", encoding="utf-8")
    running = tmp_path / "cupsd-running.txt"
    running.write_text("yes\n", encoding="utf-8")
    devices = tmp_path / "devices.txt"
    devices.write_text(DEFAULT_DEVICES, encoding="utf-8")
    answers = tmp_path / "menu-answers.txt"
    answers.write_text("", encoding="utf-8")
    lpadmin_status = tmp_path / "lpadmin-status.txt"
    lpadmin_status.write_text("0\n", encoding="utf-8")

    _write_stub(stubs, "lpstat", f"""
read -r state < '{running}'
if [ "$state" != "yes" ]; then
    printf 'lpstat: Transport endpoint is not connected\\n' >&2
    exit 1
fi
case "$1" in
    -e)
        while IFS= read -r name; do
            [ -n "$name" ] && printf '%s\\n' "$name"
        done < '{printers}'
        ;;
    -t)
        printf 'scheduler is running\\n'
        while IFS= read -r name; do
            [ -n "$name" ] && printf 'printer %s is idle.\\n' "$name"
        done < '{printers}'
        ;;
esac
exit 0
""", calls)

    _write_stub(stubs, "lpinfo", f"""
read -r state < '{running}'
if [ "$state" != "yes" ]; then exit 1; fi
while IFS= read -r line; do printf '%s\\n' "$line"; done < '{devices}'
exit 0
""", calls)

    # Reads stdin so the menu it was handed is recorded, and answers with
    # the next queued line - the add dialog asks twice.
    _write_stub(stubs, "zepos-menu", f"""
while IFS= read -r line; do
    printf 'menu-stdin %s\\n' "$line" >> '{calls}'
done
answer=""
rest=""
first=1
while IFS= read -r queued; do
    if [ "$first" = 1 ]; then
        answer="$queued"
        first=0
    else
        rest="$rest$queued"$'\\n'
    fi
done < '{answers}'
printf '%s' "$rest" > '{answers}'
[ -n "$answer" ] && printf '%s\\n' "$answer"
exit 0
""", calls)

    _write_stub(stubs, "lpadmin", f"""
read -r status < '{lpadmin_status}'
if [ "$status" != "0" ]; then
    printf 'lpadmin: Forbidden\\n' >&2
    exit "$status"
fi
exit 0
""", calls)

    _write_stub(stubs, "lpoptions", "exit 0\n", calls)
    _write_stub(stubs, "notify-send", "exit 0\n", calls)

    # Records and refuses. It deliberately does NOT run what it was
    # handed: a stub that execed its arguments would put the real
    # `lpadmin` and `systemctl` back in reach through it.
    #
    # The refusal is the second half of the guarantee. Recording alone
    # makes an attempt visible to the test that looks for it; failing
    # makes it visible to every other test in this file as well, because
    # a dialog that started needing root would stop working under the
    # harness rather than working and being caught by one assertion.
    _write_stub(stubs, "sudo", """
printf 'sudo: a password is required\\n' >&2
exit 1
""", calls)

    class Control:
        directory = stubs
        transcript_file = calls

        @staticmethod
        def configured(*names: str) -> None:
            printers.write_text("".join(f"{n}\n" for n in names), encoding="utf-8")

        @staticmethod
        def cupsd(state: bool) -> None:
            running.write_text("yes\n" if state else "no\n", encoding="utf-8")

        @staticmethod
        def devices(text: str) -> None:
            devices.write_text(text, encoding="utf-8")

        @staticmethod
        def answers(*lines: str) -> None:
            answers.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")

        @staticmethod
        def lpadmin_fails() -> None:
            lpadmin_status.write_text("1\n", encoding="utf-8")

    return Control


def run_printer(generate, printer_stubs, tmp_path, *args):
    script = generate(PRINTER_TEMPLATE, "printer-manager")
    return run_child([BASH, str(script), *args], printer_stubs.directory,
                     tmp_path / "home")


def test_the_printer_template_exists():
    assert (TEMPLATES / f"{PRINTER_TEMPLATE}.template").exists()


def test_the_printer_template_names_no_device():
    """It replaces two installers that each drove one specific device.

    Two kinds of name, checked two ways. The notebook model that doubles
    as one of the origin's own machine names is a digest in
    tests/origin_data.py; writing it here is exactly how it would get
    published. The printer vendor and the specification's own
    placeholders are ordinary public words and stay in plaintext.

    The German word "Modell" contains one of these as a substring, which
    is why this scans the lower-cased text: a comment written in German
    about model-independence would otherwise reintroduce the very string
    the guard is looking for.
    """
    text = (TEMPLATES / f"{PRINTER_TEMPLATE}.template").read_text(encoding="utf-8")
    assert not ORIGIN.hits(text), (
        "an origin device name is in the printer template - see "
        "tests/origin_data.py")
    for name in ("dell", "modela", "modelb"):
        assert name not in text.lower(), f"device name in the template: {name}"


def test_the_printer_template_discovers_what_is_there():
    text = (TEMPLATES / f"{PRINTER_TEMPLATE}.template").read_text(encoding="utf-8")
    assert "lpstat" in text and "lpinfo" in text, (
        "a generic printer dialog must find what is there, not assume it")


@pytest.mark.allow_subprocess
def test_no_printer_configured_says_so_and_opens_no_menu(
        generate, printer_stubs, tmp_path):
    """The empty case is the one a stranger's machine starts in.

    A dialog that shows an empty menu here is indistinguishable from
    a broken one.
    """
    printer_stubs.configured()

    result = run_printer(generate, printer_stubs, tmp_path, "menu")

    assert result.returncode == 0, result.stdout + result.stderr
    assert calls_of(printer_stubs.transcript_file, "zepos-menu") == [], (
        "an empty menu was opened over no printers at all")
    notifications = calls_of(printer_stubs.transcript_file, "notify-send")
    assert len(notifications) == 1
    assert "Kein Drucker" in notifications[0]


@pytest.mark.allow_subprocess
def test_one_printer_is_offered_and_selecting_it_makes_it_the_default(
        generate, printer_stubs, tmp_path):
    printer_stubs.configured("Buero")
    printer_stubs.answers("Buero")

    result = run_printer(generate, printer_stubs, tmp_path, "menu")

    assert result.returncode == 0, result.stdout + result.stderr
    offered = [line.split(" ", 1)[1]
               for line in transcript(printer_stubs.transcript_file)
               if line.startswith("menu-stdin ")]
    assert offered == ["Buero"]
    assert calls_of(printer_stubs.transcript_file, "lpoptions") == ["lpoptions -d Buero"]


@pytest.mark.allow_subprocess
def test_several_printers_are_all_offered(generate, printer_stubs, tmp_path):
    """The case both origin scripts could not have: more than one device."""
    printer_stubs.configured("Buero", "Etage2", "Labor")
    printer_stubs.answers("Etage2")

    result = run_printer(generate, printer_stubs, tmp_path, "menu")

    assert result.returncode == 0, result.stdout + result.stderr
    offered = [line.split(" ", 1)[1]
               for line in transcript(printer_stubs.transcript_file)
               if line.startswith("menu-stdin ")]
    assert offered == ["Buero", "Etage2", "Labor"]
    assert calls_of(printer_stubs.transcript_file, "lpoptions") == ["lpoptions -d Etage2"]


@pytest.mark.allow_subprocess
def test_an_abandoned_menu_changes_nothing(generate, printer_stubs, tmp_path):
    """Escape out of the menu and it prints nothing. Reading that as a
    selection would set a printer named "" as the default."""
    printer_stubs.configured("Buero", "Labor")
    printer_stubs.answers()

    result = run_printer(generate, printer_stubs, tmp_path, "menu")

    assert result.returncode == 0, result.stdout + result.stderr
    assert calls_of(printer_stubs.transcript_file, "lpoptions") == []


@pytest.mark.allow_subprocess
def test_list_prints_the_configured_names_and_nothing_else(
        generate, printer_stubs, tmp_path):
    printer_stubs.configured("Buero", "Labor")

    result = run_printer(generate, printer_stubs, tmp_path, "list")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.split() == ["Buero", "Labor"]


@pytest.mark.allow_subprocess
def test_discover_reports_reachable_devices_without_the_pseudo_ones(
        generate, printer_stubs, tmp_path):
    """`lpinfo -v` also lists `file:` and `serial:` back ends. Offering
    those as printers to install is offering nonsense."""
    result = run_printer(generate, printer_stubs, tmp_path, "discover")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        "ipp://printer.invalid/ipp/print",
        "usb://Generic/Printer?serial=1",
    ]


@pytest.mark.allow_subprocess
def test_add_installs_the_chosen_device_driverlessly(
        generate, printer_stubs, tmp_path):
    """What actually replaces the two vendor-driver installers.

    `-m everywhere` is the driverless IPP path: one command for any
    device that speaks it, instead of one script per device.
    """
    printer_stubs.answers("ipp://printer.invalid/ipp/print", "Etage2")

    result = run_printer(generate, printer_stubs, tmp_path, "add")

    assert result.returncode == 0, result.stdout + result.stderr
    assert calls_of(printer_stubs.transcript_file, "lpadmin") == [
        "lpadmin -p Etage2 -v ipp://printer.invalid/ipp/print -E -m everywhere"
    ]


@pytest.mark.allow_subprocess
def test_add_refuses_a_name_cups_would_reject(generate, printer_stubs, tmp_path):
    """CUPS rejects a name with a space in it - after the user typed it,
    in a message they never see because the menu is already gone."""
    printer_stubs.answers("ipp://printer.invalid/ipp/print", "Drucker im Flur")

    result = run_printer(generate, printer_stubs, tmp_path, "add")

    assert result.returncode != 0
    assert calls_of(printer_stubs.transcript_file, "lpadmin") == []
    assert any("Name" in line
               for line in calls_of(printer_stubs.transcript_file, "notify-send"))


@pytest.mark.allow_subprocess
def test_add_with_nothing_reachable_says_so(generate, printer_stubs, tmp_path):
    printer_stubs.devices("file cups-pdf:/ \"Unknown\" \"PDF\"\n")

    result = run_printer(generate, printer_stubs, tmp_path, "add")

    assert result.returncode == 0, result.stdout + result.stderr
    assert calls_of(printer_stubs.transcript_file, "zepos-menu") == []
    assert calls_of(printer_stubs.transcript_file, "lpadmin") == []


@pytest.mark.allow_subprocess
def test_a_refused_installation_is_reported_rather_than_claimed(
        generate, printer_stubs, tmp_path):
    """lpadmin authenticates against cupsd itself. Somebody outside the
    CUPS administration group gets "Forbidden", and a dialog that says
    "eingerichtet" over it has lied to them."""
    printer_stubs.answers("ipp://printer.invalid/ipp/print", "Etage2")
    printer_stubs.lpadmin_fails()

    result = run_printer(generate, printer_stubs, tmp_path, "add")

    assert result.returncode != 0
    messages = calls_of(printer_stubs.transcript_file, "notify-send")
    assert any("fehlgeschlagen" in line for line in messages), messages


@pytest.mark.allow_subprocess
def test_status_reports_a_stopped_cupsd_instead_of_printing_nothing(
        generate, printer_stubs, tmp_path):
    printer_stubs.cupsd(False)

    result = run_printer(generate, printer_stubs, tmp_path, "status")

    assert result.returncode != 0
    assert "CUPS" in result.stderr


@pytest.mark.allow_subprocess
def test_status_passes_through_what_cups_says(generate, printer_stubs, tmp_path):
    printer_stubs.configured("Buero")

    result = run_printer(generate, printer_stubs, tmp_path, "status")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "scheduler is running" in result.stdout
    assert "Buero" in result.stdout


@pytest.mark.allow_subprocess
def test_an_unknown_subcommand_explains_itself(generate, printer_stubs, tmp_path):
    result = run_printer(generate, printer_stubs, tmp_path, "install-everything")

    assert result.returncode != 0
    assert "list" in result.stderr and "add" in result.stderr


@pytest.mark.allow_subprocess
def test_the_printer_dialog_never_reaches_for_sudo(
        generate, printer_stubs, tmp_path):
    """CUPS authenticates against cupsd, not against the shell.

    `lpadmin -p ... -E` asks cupsd, which decides on the CUPS
    administration group; nothing this dialog does needs root, and on
    this machine a failed sudo locks the account out. So an attempt has
    to be a failed test, and it is only a failed test if a successful
    attempt would have been WRITTEN DOWN - which is what the sudo stub is
    for, and what its absence used to prevent.

    Every subcommand, because a dialog that reaches for root does it in
    one branch, not in all of them.
    """
    printer_stubs.configured("Buero")
    printer_stubs.answers("Buero")

    for arguments in (["menu"], ["list"], ["discover"], ["status"], ["add"]):
        run_printer(generate, printer_stubs, tmp_path, *arguments)
    assert calls_of(printer_stubs.transcript_file, "sudo") == []


@pytest.mark.allow_subprocess
def test_the_transcript_would_show_a_dialog_that_did_reach_for_sudo(
        printer_stubs, tmp_path):
    """The test above, made falsifiable.

    Without this, `calls_of(transcript, "sudo") == []` reads as a
    property of the printer template while being a property of the stub
    directory - and it held for every possible template as long as no
    sudo stub existed. So a script that DOES call sudo, in the exact
    shape a restart would be written in, is run through the same
    harness, and the same expression is asserted to come back non-empty.

    `&>/dev/null` on purpose: that is how such a line gets written, it is
    what makes the attempt invisible in both output streams, and the
    transcript is therefore the only place it can still be seen.
    """
    script = tmp_path / "reaches-for-root.sh"
    script.write_text("#!/bin/bash\nsudo systemctl restart cups &>/dev/null\n"
                      "exit 0\n", encoding="utf-8")
    script.chmod(0o755)

    run_child([BASH, str(script)], printer_stubs.directory, tmp_path / "home")

    attempts = calls_of(printer_stubs.transcript_file, "sudo")
    assert attempts == ["sudo systemctl restart cups"], attempts


# --------------------------------------------------------------------
# the weather module
# --------------------------------------------------------------------

@pytest.fixture
def weather_stubs(tmp_path):
    stubs = tmp_path / "weather-stubs"
    stubs.mkdir()
    calls = tmp_path / "weather-calls.txt"

    body = tmp_path / "curl-body.txt"
    body.write_text(wttr_response(), encoding="utf-8")
    code = tmp_path / "curl-code.txt"
    code.write_text("200", encoding="utf-8")
    status = tmp_path / "curl-status.txt"
    status.write_text("0", encoding="utf-8")

    # `curl -w '\n%{http_code}'` writes the body, then a newline, then
    # the status code - including when the transfer failed, where the
    # code is 000. The stub reproduces exactly that shape.
    _write_stub(stubs, "curl", f"""
printf '%s' "$(< '{body}')"
printf '\\n%s' "$(< '{code}')"
read -r rc < '{status}'
exit "$rc"
""", calls)

    _passthrough(stubs, "jq")
    _passthrough(stubs, "mkdir")

    class Control:
        directory = stubs
        transcript_file = calls

        @staticmethod
        def answers(text: str, http_code: str = "200", exit_status: str = "0") -> None:
            body.write_text(text, encoding="utf-8")
            code.write_text(http_code, encoding="utf-8")
            status.write_text(exit_status, encoding="utf-8")

        @staticmethod
        def times_out() -> None:
            # curl(1): 28 is "operation timeout", and nothing was
            # transferred, so there is no code either.
            body.write_text("", encoding="utf-8")
            code.write_text("000", encoding="utf-8")
            status.write_text("28", encoding="utf-8")

    return Control


@pytest.fixture
def run_weather(generate, weather_stubs, tmp_path):
    cache = tmp_path / "cache"

    def run(location: str = TEST_LOCATION):
        script = generate(WEATHER_TEMPLATE, "weather.sh",
                          styles={"STYLE_WEATHER_LOCATION": location})
        result = run_child([BASH, str(script)], weather_stubs.directory,
                           tmp_path / "home", XDG_CACHE_HOME=str(cache))
        assert result.returncode == 0, result.stdout + result.stderr
        # Waybar reads one JSON object per run. Anything else and the
        # module renders nothing, with no hint why.
        return json.loads(result.stdout)

    run.cache_directory = cache
    return run


def test_the_weather_template_exists():
    assert (TEMPLATES / f"{WEATHER_TEMPLATE}.template").exists()


def test_the_weather_template_takes_its_location_from_the_settings():
    text = (TEMPLATES / f"{WEATHER_TEMPLATE}.template").read_text(encoding="utf-8")
    assert "{{STYLE_WEATHER_LOCATION}}" in text


def test_the_weather_template_builds_its_json_with_jq():
    """`printf '{"text":"%s"}' "$desc"` is not JSON construction.

    `desc` is a string from a third-party HTTP response; one double
    quote or backslash in it and Waybar gets a malformed object, renders
    nothing, and says nothing. test_a_description_with_quotes_survives
    proves the behaviour; this names the mechanism, because the printf
    version passes every test that does not happen to use a quote.
    """
    text = (TEMPLATES / f"{WEATHER_TEMPLATE}.template").read_text(encoding="utf-8")
    assert "jq -cn" in text or "jq -nc" in text, (
        "the JSON has to be built by something that escapes its values")


def test_the_weather_template_says_where_the_data_goes():
    """The module sends the location to a third party on every refresh.

    That is inherent to the feature, but the next person to read this
    file should not have to infer it from a URL.
    """
    text = (TEMPLATES / f"{WEATHER_TEMPLATE}.template").read_text(encoding="utf-8")
    assert "wttr.in" in text
    lowered = text.lower()
    assert "datenschutz" in lowered or "privacy" in lowered, (
        "nothing in the file says that the location leaves the machine")


@pytest.mark.allow_subprocess
def test_without_a_location_nothing_is_requested(run_weather, weather_stubs):
    """The opt-in, measured.

    An unset location must not be "fetch the weather for wherever this
    IP address is" - that is a request the user never made, carrying
    their address to a service they never chose.
    """
    output = run_weather(location="")

    assert output["text"] == ""
    assert calls_of(weather_stubs.transcript_file, "curl") == [], (
        "a request went out over an unconfigured module")


@pytest.mark.allow_subprocess
def test_a_good_response_becomes_a_temperature_and_a_condition(
        run_weather, weather_stubs, monkeypatch):
    weather_stubs.answers(wttr_response(temp="7", code="116", desc="Partly cloudy"))

    output = run_weather()

    assert "7" in output["text"]
    assert "°C" in output["text"]
    assert icons(monkeypatch)["ICON_WEATHER_PARTLY_CLOUDY"] in output["text"]
    assert TEST_LOCATION in output["tooltip"]
    assert "Partly cloudy" in output["tooltip"]
    assert output["class"] == "weather-ok"


@pytest.mark.allow_subprocess
def test_a_negative_temperature_is_not_mistaken_for_rubbish(
        run_weather, weather_stubs):
    weather_stubs.answers(wttr_response(temp="-11", code="338", desc="Heavy snow"))

    output = run_weather()

    assert "-11" in output["text"]
    assert output["class"] == "weather-ok"


@pytest.mark.allow_subprocess
def test_an_unknown_condition_code_still_renders(
        run_weather, weather_stubs, monkeypatch):
    """wttr.in may answer with a code this table does not know. That is a
    reason to show the temperature under a neutral glyph, not to show
    nothing."""
    weather_stubs.answers(wttr_response(temp="3", code="999", desc="Etwas Neues"))

    output = run_weather()

    assert "3" in output["text"]
    assert icons(monkeypatch)["ICON_WEATHER_UNKNOWN"] in output["text"]


@pytest.mark.allow_subprocess
def test_a_description_with_quotes_survives(run_weather, weather_stubs):
    """The defect the plan's printf version shipped.

    `Regen "stark" \\ Wind` closes the JSON string early and leaves a
    stray backslash behind. Waybar's parser gives up on the whole object
    and the module simply disappears - the single hardest failure of
    this kind to diagnose from a bar that shows nothing.
    """
    weather_stubs.answers(wttr_response(desc='Regen "stark" \\ Wind'))

    output = run_weather()

    assert 'Regen "stark" \\ Wind' in output["tooltip"]


@pytest.mark.allow_subprocess
def test_a_malformed_response_is_a_state_not_a_crash(run_weather, weather_stubs):
    weather_stubs.answers("<html>502 Bad Gateway</html>")

    output = run_weather()

    assert output["class"] == "weather-error"
    assert output["tooltip"]


@pytest.mark.allow_subprocess
def test_a_response_missing_the_temperature_is_treated_as_malformed(
        run_weather, weather_stubs):
    """Valid JSON is not the same as usable JSON. jq answers `null`,
    which a bar renders as the word "null" next to a degree sign."""
    weather_stubs.answers(json.dumps({"current_condition": [{}]}))

    output = run_weather()

    assert output["class"] == "weather-error"
    assert "null" not in output["text"]


@pytest.mark.allow_subprocess
def test_a_timeout_is_an_ordinary_state(run_weather, weather_stubs):
    """A laptop off the network is not a broken configuration."""
    weather_stubs.times_out()

    output = run_weather()

    assert output["class"] == "weather-offline"
    assert output["tooltip"]


@pytest.mark.allow_subprocess
def test_being_rate_limited_is_an_ordinary_state(run_weather, weather_stubs):
    weather_stubs.answers("", http_code="429")

    output = run_weather()

    assert output["class"] == "weather-throttled"


@pytest.mark.allow_subprocess
def test_an_unknown_place_says_which_one(run_weather, weather_stubs):
    weather_stubs.answers("", http_code="404")

    output = run_weather()

    assert output["class"] == "weather-unknown-location"
    assert TEST_LOCATION in output["tooltip"]


@pytest.mark.allow_subprocess
def test_the_second_run_uses_the_cache(run_weather, weather_stubs):
    """A Waybar module runs on an interval. Without a cache this asks a
    free service every few seconds, which earns a rate limit and
    deserves one."""
    run_weather()
    assert len(calls_of(weather_stubs.transcript_file, "curl")) == 1

    output = run_weather()

    assert len(calls_of(weather_stubs.transcript_file, "curl")) == 1, (
        "the cached answer was not used")
    assert output["class"] == "weather-ok"


@pytest.mark.allow_subprocess
def test_a_failure_falls_back_to_the_last_known_value(run_weather, weather_stubs):
    """Old and labelled beats empty.

    The cache is dated back so the module has to go out again, and the
    request then fails - which is the only interesting combination:
    something to show, and no way to refresh it.
    """
    weather_stubs.answers(wttr_response(temp="21", desc="Sunny"))
    run_weather()

    cached = list(run_weather.cache_directory.rglob("weather*"))
    assert len(cached) == 1, f"expected one cache file, found {cached}"
    cache_file = cached[0]
    stored = cache_file.read_text(encoding="utf-8").split("\n", 1)
    cache_file.write_text("1\n" + stored[1], encoding="utf-8")

    weather_stubs.times_out()
    output = run_weather()

    assert "21" in output["text"], "the last known value was thrown away"
    assert output["class"] == "weather-offline"
    assert "Stand" in output["tooltip"] or "veraltet" in output["tooltip"], (
        "a stale value must say that it is stale")


def test_the_bar_actually_runs_the_generated_weather_script(tmp_path, monkeypatch):
    """A generated artifact nobody reads is the same as no artifact.

    The generator writes weather.sh into ~/.config/ags/scripts. If the
    bar's own configuration never names it, the module exists on disk and
    nowhere else - the same gap as a template with no generator entry,
    one layer further out, and just as invisible: every test passes, the
    file is there, and the user sees nothing.

    "ERREICHBAR" HEISST SEIT DEM 12.08.2026 NICHT MEHR "AUF DER LEISTE"
        Die ausgelieferte Leiste stellt das Wetter nicht mehr auf; es
        steht in BAR_MODULES_AVAILABLE (src/style_definition.py), ist
        also zuschaltbar, und im Kontrollzentrum steht es im Abschnitt
        SCHREIBTISCH.

        Die Frage dieser Datei bleibt dieselbe und wird deshalb ZWEIMAL
        gestellt: ruft irgendetwas dieses Skript. Der Zweig in der
        Leiste tut es, sobald jemand das Modul zuschaltet; die Zeile im
        Kontrollzentrum tut es immer. Ohne die zweite waere
        "zuschaltbar" die Ausrede, mit der ein Skript erzeugt wird, das
        auf keinem Schirm je erscheint.
    """
    monkeypatch.syspath_prepend(str(SRC))
    import template_processor

    generated = tmp_path / "Bar.tsx"
    template_processor.ConfigProcessor().apply_template(
        TEMPLATES / "ags-bar.template", generated)
    source = generated.read_text(encoding="utf-8")

    # Gegen den Code ohne Kommentare und zeilengenau. Der Kopf der Vorlage
    # nennt die Module in Prosa, und eine Teilzeichenkettensuche wuerde
    # davon wahr - siehe die Falle im Kopf von tests/src/test_gtk4_only.py.
    lines = [line.strip() for line in source.splitlines()
             if not line.lstrip().startswith("//")]

    assert any('"custom/weather"' in line and "case" in line for line in lines), (
        "die Leiste hat keinen Zweig, der custom/weather baut")
    assert any("SCRIPTS}/weather.sh" in line for line in lines), (
        "der Zweig ruft das erzeugte Skript nicht auf")

    centre = tmp_path / "ControlCenter.tsx"
    template_processor.ConfigProcessor().apply_template(
        TEMPLATES / "ags-control-center.template", centre)
    control = [line.strip() for line in
               centre.read_text(encoding="utf-8").splitlines()
               if not line.lstrip().startswith("//")]
    assert any("scripts/weather.sh" in line for line in control), (
        "das Kontrollzentrum liest das Wetter nicht - dann ist das "
        "Modul nur noch erreichbar, wenn man die Einstellungen kennt")


# --------------------------------------------------------------------
# the generator, and the inventory
# --------------------------------------------------------------------

def test_the_generator_dispatches_both_templates():
    """A template with no entry in generate_config.sh is never turned
    into a script. Nothing else in the tree would notice: the file is
    present, the placeholders resolve, and the artifact simply never
    appears on the user's machine."""
    text = (SRC / "generate_config.sh").read_text(encoding="utf-8")
    for name in (PRINTER_TEMPLATE, WEATHER_TEMPLATE):
        assert f"{name})" in text, f"no generator entry for {name}"


@pytest.mark.allow_subprocess
def test_the_generator_actually_writes_both_artifacts(tmp_path):
    """The entry above, exercised rather than read.

    The generator runs with HOME and XDG_CONFIG_HOME inside tmp_path, so
    every path it derives - ~/.local/bin, the output root, the backup it
    would take - lands there.

    THE OTHER HALF, which used to be a sentence rather than a check
        HOME redirects files. It does not redirect `pkill -f "gjs.*ags"`,
        `systemctl --user stop mako.service` or `hyprctl`, and the
        generator ends every run in a case statement that can reach all
        three. This test ran on the DEVELOPER'S OWN PATH, and what stood
        between it and the developer's own desktop session was a
        docstring: "neither of these two names matches a branch of the
        restart case". True today, asserted by nothing, and one added
        branch away from being false - at which point this test kills the
        session of whoever runs it and there is no failure to read
        afterwards.

        So both halves are made real. The session commands are no-ops
        PREPENDED to PATH - the generator needs python3, jq, mktemp and
        date, so the stub directory cannot be the whole of it - and the
        claim about the case statement is asserted against the script
        itself.
    """
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True)

    generator = (SRC / "generate_config.sh").read_text(encoding="utf-8")
    # The LAST case statement in the file - the one that restarts
    # services - and not the earlier one that only picks an output
    # directory, which both of these names do appear in.
    marker = "# Restart the service\ncase \"$CONFIG_NAME\" in"
    start = generator.index(marker)
    restart_case = generator[start:generator.index("\nesac", start)]
    assert "bar-workspace-detect-config)" in restart_case, (
        "the restart case was not found where this looks for it")
    for name in (PRINTER_TEMPLATE, WEATHER_TEMPLATE):
        assert f"{name})" not in restart_case, (
            f"{name} has gained a branch in the restart case - this test "
            "would now run it against the developer's own session")

    stubs = tmp_path / "session-stubs"
    stubs.mkdir()
    for name in SESSION_COMMANDS:
        stub = stubs / name
        stub.write_text(f'#!/bin/bash\necho "stub: {name} $*" >&2\nexit 0\n',
                        encoding="utf-8")
        stub.chmod(0o755)
    path = os.pathsep.join([str(stubs), os.environ["PATH"]])
    for name in SESSION_COMMANDS:
        assert shutil.which(name, path=path) == str(stubs / name), (
            f"{name} would reach the real command")

    environment = {
        "PATH": path,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "ZEPOS_SYSTEM_ROOT": str(SRC),
        "ZEPOS_USER_ROOT": str(home / ".config" / "zepos"),
    }

    expected = {
        PRINTER_TEMPLATE: home / ".local" / "bin" / "printer-manager",
        WEATHER_TEMPLATE: home / ".config" / "ags" / "scripts" / "weather.sh",
    }
    for name, artifact in expected.items():
        result = subprocess.run(
            [BASH, str(SRC / "generate_config.sh"), f"-{name}"],
            env=environment, capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert artifact.is_file(), f"{name} generated nothing at {artifact}"
        assert os.access(artifact, os.X_OK), f"{artifact} is not executable"
        assert "{{" not in artifact.read_text(encoding="utf-8")


def _template_files() -> list[Path]:
    files = sorted(TEMPLATES.glob("*.template")) + sorted(STYLES.glob("*.template"))
    assert len(files) > 50, (
        f"only {len(files)} templates found under {SRC} - the scan is not "
        "reading the source tree, so its result means nothing")
    return files


# The two places the deleted weather scripts were pointed at are digests
# in tests/origin_data.py now - they are the author's home town and his
# other one, so a tuple spelling them out was the leak rather than the
# guard. They needed their own rule and still do: neither appeared in a
# file NAME after Task 1, they survived as CSS selectors, where a
# name-based search does not look, and the bar still carried the rules
# for two modules that no longer existed.
#
# PLACES is the two-entry group, not the whole denylist. That matters
# here: the exception below is a statement about ONE file naming ONE
# place, and scanning with all twenty-four entries would let an unrelated
# find in the same file be absorbed by it. The other twenty-two are the
# whole-repository guard's job in tests/src/test_inventory.py.

# EMPTY, and that is the finished state.
#
# It held one entry: time-br-config.template, a second clock with its
# author's other home town written into it as an IANA timezone next to a
# flag emoji on the same line. The exception was self-expiring on
# purpose, and it expired the way it was meant to - the two one-line
# clock templates are gone, replaced by bar-clocks-config.template,
# whose zones come from `clocks.zones` in the user settings and which
# renders nothing at all when none are set. test_inventory.py's
# KNOWN_UNFIXED carried the identical entry and is empty for the same
# reason; the two expired together, as their comments said they would.
#
# The tuple stays so the rule below keeps its shape for the next
# exception somebody has to make - and so that making one is a visible
# edit rather than a new mechanism.
KNOWN_PLACE_BOUND = ()


def test_nothing_in_the_tree_still_names_one_of_the_two_cities():
    offenders = []
    for path in _template_files():
        for number in PLACES.offending_lines(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.name}:{number}")

    unexpected = [o for o in offenders if not o.startswith(KNOWN_PLACE_BOUND)]
    assert unexpected == [], "place names left: " + "; ".join(unexpected)

    # The exception has to expire by itself. Without this, fixing the
    # second clock leaves a permanent hole in the guard that nobody has
    # any reason to notice.
    stale = [name for name in KNOWN_PLACE_BOUND
             if not any(o.startswith(name) for o in offenders)]
    assert stale == [], (
        f"{stale} no longer names a place - remove it from KNOWN_PLACE_BOUND")


def test_the_template_count_is_seventy_seven():
    """75 until the two place-bound clocks were replaced by one generic
    one (75 - 2 + 1 = 74), then 74 + 1 for the plugin include, then
    75 - 4 + 5 = 76 fuer die Leiste.

    clock-config and time-config produced clock.sh and time.sh in
    ~/.config/ags/scripts and nothing in the tree named either.
    hyprland-plugins-config produces ~/.config/hypr/plugins.conf, which
    hyprland.conf sources: everything that needs a plugin to be LOADED
    moved out of hyprland.conf into it, so that a machine without the
    objects gets a file of comments instead of a session that does not
    start. The reasoning is written out once, beside the twin assertion
    in tests/src/test_inventory.py; the two are one contract counted in
    two places and must move together.

    Die vier, die am 11.08.2026 verschwunden sind: waybar-config,
    waybar-style, waybar-launcher-config, nwg-dock-toggle-config. Die
    fuenf, die dazugekommen sind: ags-bar, ags-dock, ags-hyprland,
    ags-tray, bar-status-config. Sechzehn Stilvorlagen sind ausserdem
    entfallen - die zaehlt diese Zusicherung nicht, weil sie in
    src/styles/ liegen.

    75 + 2 = 77, nachgezaehlt am 11.08.2026.

    PLUS EINS  gtk4-settings-config.template, am 12.08.2026 - die
    GROESSE fuer fremde GTK4-Fenster, neben den Farben, die sie schon
    hatten. Die Begruendung steht bei der Zwillingszusicherung in
    tests/src/test_inventory.py.

    hyprlaunch-config und hyprclipx-config kamen dazu, als die beiden
    Plugins in den Baum geholt wurden: ihre Fenstermasse standen vorher
    als `static constexpr` im C++ und liessen sich weder faerben noch
    skalieren. Ihre STYLESHEETS liegen unter src/styles/ und zaehlen hier
    nicht mit - der Zweig hatte mit 79 gerechnet und alle vier gezaehlt.

    77 zu 76, am 12.08.2026. hyprlock-config.template ist weg, weil
    hyprlock weg ist. Es war die einzige erzeugte Datei, deren Farben
    nicht aus brand.py kamen und auch nicht konnten - hyprlock ist kein
    GTK-Programm (gemessen: `objdump -p /usr/bin/hyprlock` nennt libEGL,
    libGLESv2 und libcairo und keine Zeile mit gtk) und nimmt kein
    Stylesheet, sondern eine eigene Konfigurationssprache mit zwoelf
    rgb()-Literalen in Terminalgruen. Der Ersatz lock/zepos-lock.c ist
    GTK4 und liest src/styles/lock-style.template - das zaehlt hier nicht
    mit, weil es unter src/styles/ liegt, genau wie die vier
    Stylesheets zwei Absaetze weiter oben.

    77 - 1 + 1 = 77, nachgezaehlt am 12.08.2026. Zwei Zweige desselben
    Tages, jeder mit einer Haelfte.

    MINUS EINS  hyprlock-config, weil hyprlock durch lock/zepos-lock.c
    ersetzt ist. Es war die einzige erzeugte Datei, deren Farben nicht
    aus brand.py kamen und auch nicht kommen KONNTEN: hyprlock ist kein
    GTK-Programm und nimmt kein Stylesheet, sondern eine eigene
    Konfigurationssprache - sie trug zwoelf rgb()-Literale in
    Terminalgruen. Der Ersatz ist GTK4 und liest
    src/styles/lock-style.template, das unter src/styles/ liegt und hier
    deshalb nicht mitzaehlt.

    PLUS EINS  gtk4-settings-config.template. Neben den FARBEN von
    gtk4-colors-config schreibt es die GROESSE nach
    ~/.config/gtk-4.0/settings.ini - bis dahin wuchsen beim Drehen des
    Reglers alle eigenen Oberflaechen mit und die fremden GTK4-Fenster
    nicht.

    77 - 1 + 1 = 77, nachgezaehlt am 12.08.2026 - dieselbe Rechnung ein
    drittes Mal an demselben Tag, und diesmal mit den zwei Haelften einer
    Eingabezeile.

    MINUS EINS  starship-config, und es ist der reinste Fall von
    "erzeugt und nirgends gelesen", den dieser Baum bisher hatte. Es
    schrieb ~/.config/starship.toml, eine vollstaendige
    Prompt-Konfiguration mit vier eigenen Farbliteralen (#00cc00,
    #00ff00, #1a1a1a, #0c0c0c) - waehrend starship in keiner Paketliste
    dieses Projekts steht und kein `starship init zsh` in
    zshrc-config.template. Der Rueckwaertslauf in
    tests/src/test_reference_resolution.py hat es durchgelassen, weil ein
    Eintrag unter READ_BY_CONVENTION einen Leser BEHAUPTETE.

    PLUS EINS  p10k-config, das ~/.p10k.zsh schreibt. Der Nutzer hat am
    12.08.2026 powerlevel10k verlangt; zshrc-config.template
    konfigurierte es seit jeher und sourcte eine ~/.p10k.zsh, die
    niemand erzeugte. Jetzt gibt es sie, mit den Farben des aktiven
    Themas und den Symbolen aus src/icon_definition.py.

    80 statt 77, am 12.08.2026, und diesmal ohne ein Minus: drei
    Skripte fuer die drei BEDINGTEN Leistenmodule (Aufgabe #94).

    PLUS EINS  ags-privacy-scripts.template. Wer gerade das Mikrofon
    oder die Kamera offen hat, mit Namen. Es beantwortet eine Frage, die
    kein vorhandenes Modul beantwortete - das Mikrofonmodul der Leiste
    ist gemessen ein LAUTSTAERKEREGLER (`pamixer --default-source -t`),
    und wie laut ein Mikrofon eingestellt ist, sagt nichts darueber, ob
    jemand daran hoert.

    PLUS EINS  ags-media-scripts.template. Was gerade laeuft, ueber
    playerctl - dasselbe Programm, das die neun Medientasten dieses
    Projekts schon rufen, also kein neues Paket.

    PLUS EINS  ags-updates-scripts.template. src/update.py war am
    12.08.2026 vollstaendig und hatte KEINE Oberflaeche; dieses Skript
    liest den Zustand, den ein Lauf hinterlaesst, und entscheidet, ob
    der Mensch ihn sehen muss.

    Alle drei liegen NEBEN bar-status-config.template und nicht darin,
    obwohl dessen Kopf gute Gruende fuer ein gemeinsames Skript nennt.
    Der Grund ist der Takt, und ein gemeinsames Skript kann nur einen
    haben: zwei Sekunden fuer eine Lautstaerke, zehn Minuten fuer einen
    Zustand, den ein Zeitgeber taeglich schreibt. Die Begruendung steht
    ausgeschrieben in src/generate_config.sh bei den drei Zweigen.

    81 STATT 80, am 17.08.2026: ags-bluetooth. Der Klick auf das
    Bluetooth-Modul der Leiste startete bis dahin `blueman-manager` -
    einen GTK3-Prozess neben der Sitzung -, und der Nutzer hat verlangt,
    dass die Hauptfunktionen oben BEDIENBAR sind ("wlan soll direkt
    dahin ... bluetooth soll funktionieren"). Die Vorlage baut das
    Fenster dafuer, aus derselben Fabrik wie die anderen zehn.

    82 STATT 81, am 17.08.2026: ags-i18n. Sie erzeugt ags/utils/i18n.ts,
    aus dem jedes Widget `_()` holt - dasselbe gettext wie im Installer,
    unter der Domaene zepos-desktop. Die ganze Rechnung und die
    gemessene Ausgangslage (297 sichtbare Zeichenketten, 297 davon fest
    verdrahtet) stehen in der Zwillingszusicherung in
    tests/src/test_inventory.py; beide muessen zusammen wandern.

    83 STATT 82, am 18.08.2026: ags-kit. Sie erzeugt ags/utils/kit.ts -
    Funktionen (zepButton, zepRow, zepToggle, zepSectionLabel,
    zepDivider), die fertige Widgets zurueckgeben, damit ein Fenster
    gar nicht erst in die Lage kommt, sich einen eigenen Knopf zu
    bauen. Die gemessene Ausgangslage (45 Knopfregeln in 41 Klassen,
    keine gemeinsame) steht bei der Zwillingszusicherung in
    tests/src/test_inventory.py; beide muessen zusammen wandern.

    84 STATT 83, am 19.08.2026 (Aufgabe 26): netto plus eins, aus drei
    Bewegungen. logout-config.template faellt - zepos-logout ist
    geloescht (Regel 14), seine erzeugte layout.json gibt es nicht
    mehr. ags-logout.template kommt dazu: dasselbe Fenster, jetzt ein
    AGS-Fenster aus createOverlayWindow() statt eines eigenen
    C-Programms, dieselben sechs Aktionen als TypeScript-Literal statt
    erzeugter JSON. ags-power-button.template kommt ebenfalls dazu: der
    Dock-Knopf, der SUPER+M's Fenster jetzt auch per Klick oeffnet -
    eine eigene kleine Layer-Shell-Flaeche, kein Teil von ags-dock.
    template. -1 + 2 = +1.

    85 STATT 84, am 19.08.2026 (Aufgabe 32): ags-settings. Der Nutzer
    hatte am 18.08.2026 "ein komplett eigenes ags fenster" fuer die
    Einstellungen bestellt und am 19.08.2026 festgestellt, dass er
    stattdessen eine Umfaerbung der GTK4-Anwendung bekommen hatte
    ("uebrigens hast du die settings die du selber gebaut hast immernoch
    nicht in einem ags fenster umgesetzt was ich eigentlich wollte").
    Die neue Vorlage erzeugt ags/widget/Settings.tsx - die zweite Schale
    dieses Baums (createShellWindow) neben dem Kontrollzentrum. Sie
    traegt KEINE Einstellung selbst: sie zeichnet, was
    `zepos-settings-gui --json get` ausgibt.

    86 STATT 85, am 20.08.2026 (Aufgabe 44): ags-starter-button. Der
    Starterknopf unten rechts, das Gegenstueck zum Abschaltknopf unten
    links - dieselbe Bauart, dieselbe Groesse, dieselbe Mitfahrt am Dock,
    nur das Rastersymbol aus sechs Punkten und der Anwendungsstarter
    dahinter. Die vollstaendige Rechnung und der Wortlaut der Bestellung
    stehen bei der Zwillingszusicherung in tests/src/test_inventory.py;
    beide muessen zusammen wandern.

    87 STATT 86, am 20.08.2026 (Aufgabe 52): ags-home. Der Schreibtisch
    mit Programmsymbolen, den der Nutzer bestellt hat ("wo die apps mit
    den logos sein sollen wie windows"). Eine Layer-Shell-Flaeche je
    Schirm auf `bottom` - ueber der Tapete, unter jedem Fenster. Sein
    Stylesheet liegt unter src/styles/home-style.template und zaehlt hier
    nicht mit, genau wie lock-style.template weiter oben. Die
    vollstaendige Rechnung steht bei der Zwillingszusicherung in
    tests/src/test_inventory.py.

    88 STATT 87, am 21.08.2026 (Aufgabe 53): ags-user-settings. Sie
    erzeugt ags/utils/user-settings.ts - der eine Weg, auf dem das Dock
    und das Home die Einstellungsdatei lesen, ueber `settings.py
    dock|home add|remove` aendern und ueber einen Gio.FileMonitor
    voneinander erfahren. Ein Baustein wie kit.ts und i18n.ts, kein
    Fenster. Die vollstaendige Rechnung und der Wortlaut der Bestellung
    stehen bei der Zwillingszusicherung in tests/src/test_inventory.py;
    beide muessen zusammen wandern.

    89 STATT 88, am 21.08.2026 (Aufgabe 54, Stufe 2):
    ags-bluetooth-agent. Sie erzeugt ags/widget/BluetoothAgent.tsx - ein
    org.bluez.Agent1 auf dem Systembus, der alle sieben Rueckfragen von
    org.bluez.Agent(5) beantwortet und sein Fenster aus derselben
    createOverlayWindow()-Fabrik holt wie die uebrigen zwoelf.

    Sie ersetzt blueman-applet, das seit Stufe 1 als `exec-once` in der
    Sitzung lief - netto plus eine Vorlage und minus ein fremdes
    GTK3-Programm. Die vollstaendige Begruendung samt der gemessenen
    Kette bis in den Kern steht bei der Zwillingszusicherung in
    tests/src/test_inventory.py.

    90 STATT 89, am 22.08.2026 (Aufgabe 64): audio-devices-config. Sie
    erzeugt ags/scripts/audio-devices.sh - die Liste der Ton-Geraete und
    der Wechsel zwischen ihnen, bestellt mit "ich will pro ton und
    mikrofon auch das geraet waehlen koennen, falls mehrere angeschlossen
    sind". Ein Skript NEBEN status.sh und nicht darin, weil es einen
    anderen Takt hat. Was es tut, wird in tests/src/test_audio_devices.py
    ausgefuehrt und nicht gelesen; die vollstaendige Rechnung steht bei
    der Zwillingszusicherung in tests/src/test_inventory.py, und beide
    muessen zusammen wandern.

    91 STATT 90, am 22.08.2026 (Aufgabe 69): bar-vpn-config. Sie erzeugt
    ags/scripts/vpn.py - das VPN-Schild der Leiste, bestellt mit "ein
    user hat vorgeschlagen, in die waybar im header ein schild mit farbe
    und tooltip zu machen, wo man sieht was der status der vpn ist -
    nicht verbunden, verbunden, error - mit einer farbe verbunden".
    Wieder ein Skript NEBEN status.sh, und diesmal nicht wegen des
    Taktes: die Antwort auf "steht der Tunnel?" steht in src/vpn.py, also
    in Python, und haette in status.sh denselben einen Interpreterstart
    gekostet - nur dass ein haengender Aufruf DORT fuenf Module leer
    stehen laesst statt eines. Was es tut, wird in
    tests/src/test_bar_vpn.py ausgefuehrt und nicht gelesen; die
    vollstaendige Rechnung steht bei der Zwillingszusicherung in
    tests/src/test_inventory.py, und beide muessen zusammen wandern.
    """
    assert len(list(TEMPLATES.glob("*.template"))) == 91
