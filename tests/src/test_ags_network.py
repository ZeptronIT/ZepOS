# SPDX-License-Identifier: GPL-3.0-or-later
"""ags-network-scripts, run against names its author did not choose.

The AGS network widget asks this script for a JSON list of the wireless
networks in range and draws whatever comes back. The list was assembled
with `echo`:

    echo "  {\\"ssid\\": \\"$ssid\\", \\"signal\\": $signal, ...}"

An SSID is a name chosen by whoever put the access point there. One
containing a quote closes the JSON string early, and the widget - which
parses the WHOLE answer, not one entry - then shows no networks at all.
A neighbour's router is enough to blank the list.

The same applies to the connection details: `name` is whatever the user
called their connection in NetworkManager.

AND THE ANSWERS ARE WRITTEN THE WAY nmcli WRITES THEM
    `nmcli -t` separates fields with a colon and protects a colon or a
    backslash INSIDE a value with a backslash - nmcli(1), `-e|--escape`,
    default yes. The canned answers below therefore go through _terse(),
    which applies exactly that rule, instead of being pasted in raw.

    They used to be raw, and that hid the second half of the defect: the
    script split on `:` with `IFS=:`, which also splits at a protected
    one, so an SSID with a colon in it shifted every following field by
    one. A fixture that never produces a protected colon cannot show it.

Safety: every child runs through `env -i` with the stub directory as the
ONLY entry on PATH, asserted before the run, so `nmcli` is a stub reading
canned output from a file and no real wireless device is ever touched.
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

SRC = Path(__file__).resolve().parents[2] / "src"

BASH = "/bin/bash"
ENV = "/usr/bin/env"

# An access point whose name is JSON syntax. Every character in it is
# legal in an SSID.
HOSTILE_SSID = 'Free "WiFi" \\o/'

# And one whose name is nmcli's own field separator - equally legal, and
# the character the terse format has to protect.
COLON_SSID = "Cafe: Gast"

# `python3` runs src/vpn.py, which is where the VPN row's answer comes
# from now - the script no longer decides for itself which of the
# machine's addresses belongs to a tunnel. It reads and parses; the `ip`
# and `pgrep` it reaches for are the stubs below, because the child's
# PATH is the stub directory and nothing else.
PASSTHROUGH = ("jq", "awk", "grep", "cat", "head", "wc", "tr", "basename",
               "python3")
# bluetoothctl stand hier und ist am 17.08.2026 gegangen: das Skript
# fragt es nicht mehr. Seine Bluetooth-Antwort hatte genau einen Leser -
# die Zeile im Kontrollzentrum -, und die Bedienung steht seither in
# einem eigenen Fenster, das bluetoothctl SELBST fragt (mit Frist, was
# dieses Skript nie tat). Eine Attrappe fuer einen Aufruf, den es nicht
# gibt, ist eine Zeile, die beim naechsten Lesen als "das ist
# abgesichert" gelesen wird.
RECORDED = ("lpstat", "systemctl", "pgrep", "ip", "sleep")


def _terse(*values: str) -> str:
    """One line of `nmcli -t` output, escaped the way nmcli escapes it.

    nmcli(1) under `-e|--escape`: in terse tabular mode a `:` or a `\\`
    inside a value is written with a leading `\\`, and that is the
    default. The backslash goes first, or the one written for a colon
    would be escaped in turn.
    """
    return ":".join(value.replace("\\", "\\\\").replace(":", "\\:")
                    for value in values)


@pytest.fixture
def script(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(SRC))
    import template_processor

    output = tmp_path / "ags-network-scripts"
    template_processor.ConfigProcessor().apply_template(
        SRC / "templates" / "ags-network-scripts.template", output)
    output.chmod(0o755)
    return output


@pytest.fixture
def stubs(tmp_path):
    """The stub directory. nmcli answers from files, one per query."""
    directory = tmp_path / "stubs"
    directory.mkdir()
    answers = tmp_path / "nmcli"
    answers.mkdir()

    for name in RECORDED:
        stub = directory / name
        stub.write_text("#!/bin/bash\nexit 1\n", encoding="utf-8")
        stub.chmod(0o755)

    for name in PASSTHROUGH:
        assert name not in RECORDED
        conftest.assert_safe_to_passthrough(name)
        real = shutil.which(name)
        assert real, f"the script needs {name}"
        # The absolute path: with the stub directory as the whole of
        # PATH, `exec jq "$@"` would find this stub again.
        assert real.startswith("/")
        stub = directory / name
        stub.write_text(f'#!/bin/bash\nexec "{real}" "$@"\n', encoding="utf-8")
        stub.chmod(0o755)

    # Answers by the field list it is asked for, so one test can arrange
    # a scan result and another a connection, without either reaching a
    # device. Anything not arranged is answered with nothing.
    nmcli = directory / "nmcli"
    nmcli.write_text(
        "#!/bin/bash\n"
        "# Test stub. Never reaches NetworkManager.\n"
        "fields=\"\"\n"
        "while [ $# -gt 0 ]; do\n"
        "    if [ \"$1\" = -f ]; then fields=\"$2\"; fi\n"
        "    shift\n"
        "done\n"
        f"answer='{answers}'/\"${{fields:-none}}\"\n"
        "[ -f \"$answer\" ] && exec /bin/cat \"$answer\"\n"
        "exit 0\n", encoding="utf-8")
    nmcli.chmod(0o755)

    return directory


def _answer(tmp_path: Path, fields: str, text: str) -> None:
    (tmp_path / "nmcli" / fields).write_text(text, encoding="utf-8")


def _run(script: Path, arguments, stubs: Path, home: Path,
         tmp_path: Path) -> subprocess.CompletedProcess:
    path = str(stubs)
    assert path.split(os.pathsep) == [str(stubs)]
    assert not os.environ.get("PATH", "").startswith(path)
    home.mkdir(parents=True, exist_ok=True)
    # XDG_RUNTIME_DIR is where the VPN state file lives, and the script's
    # VPN row is answered from it. Without it here the child would fall
    # back to /run/user/$UID and read the state of whoever is running the
    # tests - which is a test that reports on the developer's desktop.
    runtime = tmp_path / "runtime"
    runtime.mkdir(exist_ok=True)
    result = subprocess.run(
        [ENV, "-i", f"PATH={path}", f"HOME={home}", f"TMPDIR={tmp_path}",
         f"XDG_RUNTIME_DIR={runtime}",
         BASH, str(script), *arguments],
        env={}, input="", capture_output=True, text=True, timeout=60)
    conftest.assert_no_missing_command(result, "the network script")
    return result


# --------------------------------------------------------------------
# the network list
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_a_network_named_with_quotes_does_not_blank_the_list(script, stubs,
                                                             tmp_path):
    """The defect: one hostile name, and the widget shows nothing.

    The answer is parsed as one document, so a single broken entry costs
    every entry. Measured: the SSID below produced a document jq refuses,
    and the other two networks - which are fine - disappeared with it.
    """
    _answer(tmp_path, "SSID,SIGNAL,SECURITY,ACTIVE",
            _terse(HOSTILE_SSID, "88", "WPA2", "no") + "\n"
            + _terse("Zuhause", "72", "WPA2", "yes") + "\n"
            + _terse("Nachbar", "41", "--", "no") + "\n")
    _answer(tmp_path, "active,ssid", _terse("yes", "Zuhause") + "\n")

    result = _run(script, ["list"], stubs, tmp_path / "home", tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    networks = json.loads(result.stdout)
    assert [n["ssid"] for n in networks] == [HOSTILE_SSID, "Zuhause", "Nachbar"]
    assert [n["signal"] for n in networks] == [88, 72, 41]
    assert [n["secure"] for n in networks] == [True, True, False]
    assert [n["active"] for n in networks] == [False, True, False]


@pytest.mark.allow_subprocess
def test_a_network_named_with_a_colon_arrives_whole_and_in_the_right_fields(
        script, stubs, tmp_path):
    """The separator, inside a value.

    nmcli hands over "Cafe\\: Gast:72:WPA2:yes" and means four fields.
    `IFS=:` read five: the name ended at "Cafe", the signal became
    " Gast" - which `tonumber? // 0` turned into 0 - the security became
    "72" (any non-empty value that is not "--" reads as secure, so an
    open network would have shown a padlock), and the ACTIVE column was
    "WPA2".

    Since the jq change the widget no longer blanks, so the wrong values
    are DISPLAYED rather than lost: a name with a stray backslash, no
    signal, and a lock on a network that has none.
    """
    _answer(tmp_path, "SSID,SIGNAL,SECURITY,ACTIVE",
            _terse(COLON_SSID, "72", "--", "yes") + "\n"
            + _terse("Nachbar", "41", "WPA2", "no") + "\n")
    _answer(tmp_path, "active,ssid", _terse("yes", COLON_SSID) + "\n")

    result = _run(script, ["list"], stubs, tmp_path / "home", tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    networks = json.loads(result.stdout)
    assert networks[0] == {"ssid": COLON_SSID, "signal": 72,
                           "secure": False, "active": True}
    assert networks[1]["ssid"] == "Nachbar"


@pytest.mark.allow_subprocess
def test_the_name_of_the_connected_network_survives_its_own_colon(script,
                                                                  stubs,
                                                                  tmp_path):
    """What the bar module itself shows.

    `nmcli -t -f active,ssid | grep '^yes' | cut -d: -f2` keeps the
    SECOND field and stops at the next colon, so this name reached the
    bar as "Cafe\\" - a backslash nobody chose, and half a name.
    """
    _answer(tmp_path, "active,ssid",
            _terse("no", "Nachbar") + "\n" + _terse("yes", COLON_SSID) + "\n")

    result = _run(script, ["info"], stubs, tmp_path / "home", tmp_path)

    assert result.stdout.strip() == COLON_SSID


@pytest.mark.allow_subprocess
def test_one_name_per_network_and_the_strongest_of_them(script, stubs,
                                                        tmp_path):
    """`sort -t: -k2 -rn | awk -F: '!seen[$1]++'` did this, and both
    halves of it split at a protected colon as well: the sort ranked on
    whatever fell into the second field and the deduplication compared
    truncated names. jq does it on the parsed values now, and the order
    and the choice have to come out the same."""
    _answer(tmp_path, "SSID,SIGNAL,SECURITY,ACTIVE",
            _terse(COLON_SSID, "40", "WPA2", "no") + "\n"
            + _terse("Zuhause", "55", "WPA2", "no") + "\n"
            + _terse(COLON_SSID, "91", "WPA2", "no") + "\n")

    result = _run(script, ["list"], stubs, tmp_path / "home", tmp_path)

    networks = json.loads(result.stdout)
    assert [(n["ssid"], n["signal"]) for n in networks] == [
        (COLON_SSID, 91), ("Zuhause", 55)]


@pytest.mark.allow_subprocess
def test_nothing_in_range_is_an_empty_list_not_an_empty_answer(script, stubs,
                                                               tmp_path):
    """The widget asks for JSON every time it opens, whether or not the
    radio found anything."""
    result = _run(script, ["list"], stubs, tmp_path / "home", tmp_path)

    assert json.loads(result.stdout) == []


@pytest.mark.allow_subprocess
def test_a_missing_signal_is_a_number_not_a_hole(script, stubs, tmp_path):
    """`"signal": $signal` with an empty field wrote `"signal": ,` -
    broken JSON from a field nobody controls either."""
    _answer(tmp_path, "SSID,SIGNAL,SECURITY,ACTIVE", "Zuhause::WPA2:no\n")

    result = _run(script, ["list"], stubs, tmp_path / "home", tmp_path)

    networks = json.loads(result.stdout)
    assert networks[0]["signal"] == 0


# --------------------------------------------------------------------
# the connection details
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_a_connection_named_with_quotes_still_yields_a_document(script, stubs,
                                                                tmp_path):
    """The connection name is whatever the user typed into
    NetworkManager, and the widget parses this answer the same way."""
    _answer(tmp_path, "NAME,TYPE,DEVICE,STATE",
            _terse('my "home" net', "802-11-wireless", "wlan0", "activated")
            + "\n")

    result = _run(script, ["details"], stubs, tmp_path / "home", tmp_path)

    details = json.loads(result.stdout)
    assert details["name"] == 'my "home" net'
    assert details["type"] == "802-11-wireless"
    assert details["device"] == "wlan0"


@pytest.mark.allow_subprocess
def test_a_connection_named_with_a_colon_does_not_shift_the_other_fields(
        script, stubs, tmp_path):
    """Three `cut -d:` calls on one line, and the first field is a name
    the user typed. "Buero: VPN" cut the name at "Buero" and moved the
    rest of it into the type, the type into the device, and the device
    out of the answer entirely."""
    _answer(tmp_path, "NAME,TYPE,DEVICE,STATE",
            _terse("Buero: WLAN", "802-11-wireless", "wlan0", "activated")
            + "\n")

    result = _run(script, ["details"], stubs, tmp_path / "home", tmp_path)

    details = json.loads(result.stdout)
    assert details["name"] == "Buero: WLAN"
    assert details["type"] == "802-11-wireless"
    assert details["device"] == "wlan0"


# --------------------------------------------------------------------
# which connection is the VPN
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_the_vpn_is_read_from_the_type_column_not_from_the_line(script, stubs,
                                                                tmp_path):
    """`grep vpn` matched anywhere in the line, and the first field is a
    name the user chose. A wireless connection called "Buero vpn" was
    reported as the active VPN - with its own name, in the widget's VPN
    row - while nothing was connected."""
    _answer(tmp_path, "NAME,TYPE,STATE",
            _terse("Buero vpn", "802-11-wireless", "activated") + "\n")

    result = _run(script, ["vpn"], stubs, tmp_path / "home", tmp_path)

    assert result.stdout.strip() == "Aus"


@pytest.mark.allow_subprocess
def test_a_vpn_named_with_a_colon_is_reported_whole(script, stubs, tmp_path):
    _answer(tmp_path, "NAME,TYPE,STATE",
            _terse("Buero: IPsec", "vpn", "activated") + "\n")

    result = _run(script, ["vpn"], stubs, tmp_path / "home", tmp_path)

    assert result.stdout.strip() == "Buero: IPsec"


@pytest.mark.allow_subprocess
def test_no_active_connection_is_an_empty_document(script, stubs, tmp_path):
    result = _run(script, ["details"], stubs, tmp_path / "home", tmp_path)

    assert json.loads(result.stdout) == {}
