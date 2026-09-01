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
import re
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

# --------------------------------------------------------------------
# ADRESSEN, DIE ES NICHT GIBT (22.08.2026)
#
# Eine MAC-Adresse benennt ein Geraet. Steht die echte Adresse der
# Maschine, auf der entwickelt wurde, in einer Zusicherung, dann steht
# sie ab da im Verlauf, in jedem Klon und in jedem Fehlerbericht, der
# diesen Test zitiert - und sie ist nicht mehr wegzunehmen.
#
# ERFUNDEN ist dabei zu wenig: eine ausgedachte Adresse kann die eines
# fremden Geraetes sein. Die IETF hat fuer genau diesen Zweck einen
# Bereich freihalten lassen - RFC 7042, Abschnitt 2.1.2:
# 00:00:5E:00:53:00 bis 00:00:5E:00:53:FF ist "for use in documentation
# and examples", die IEEE vergibt daraus nichts. Jede Adresse in dieser
# Datei stammt daher, und
# test_keine_echte_adresse_steht_in_diesem_test() rechnet nach.
#
# NICHT benutzt wird dafuer das "lokal verwaltet"-Bit (das zweitniedrigste
# des ersten Bytes), obwohl eine von NetworkManager erzeugte Ersatzadresse
# es traegt: es sagt nur, dass die IEEE die Adresse nicht VERGEBEN hat -
# nicht, dass sie gerade auf keinem Geraet liegt. Eine gewuerfelte Adresse
# ist genau so eine, und sie gehoert in dem Moment zu einem Rechner. Der
# Bereich aus dem RFC ist die einzige Herkunft, die sich beweisen laesst,
# und darum stammen ALLE Adressen hier daraus - auch die, die unten die
# ERSATZadresse spielt. Auf das Bit kommt es im Skript ohnehin nicht an:
# es vergleicht die benutzte mit der dauerhaften, sonst nichts.
DOKU_MAC = "00:00:5E:00:53:01"
DOKU_MAC_ERSATZ = "00:00:5E:00:53:0A"
DOKU_BSSID = "00:00:5E:00:53:A1"
DOKU_BSSID_ZWEITER = "00:00:5E:00:53:A2"
DOKU_BSSID_NACHBAR = "00:00:5E:00:53:B0"

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

    # `ip` DARF EINE EINZIGE FRAGE BEANTWORTEN - NEU am 22.08.2026
    #
    #     Seit die Verbindungsauskunft die Geraeteadresse traegt, ruft
    #     das Skript `ip -d link show dev <geraet>` (siehe
    #     adapter_adresse in ags-network-scripts.template). Diese eine
    #     Form wird aus einer Datei beantwortet, alles andere bleibt bei
    #     `exit 1`.
    #
    #     Das ist Absicht und keine Bequemlichkeit: `ip -4 route get 1`
    #     und `ip route` MUESSEN weiter scheitern. Antworteten sie,
    #     laese dieser Testlauf die Routentabelle der Maschine, auf der
    #     er gerade laeuft - und ein Test, dessen Ergebnis vom
    #     Schreibtisch des Entwicklers abhaengt, sagt nichts ueber das
    #     Skript.
    ip_stub = directory / "ip"
    ip_stub.write_text(
        "#!/bin/bash\n"
        "# Test stub. Reaches no network device.\n"
        "if [ \"$1\" = -d ] && [ \"$2\" = link ] && [ \"$3\" = show ] "
        "&& [ \"$4\" = dev ]; then\n"
        f"    answer='{answers}'/\"link-$5\"\n"
        "    [ -f \"$answer\" ] && exec /bin/cat \"$answer\"\n"
        "fi\n"
        "exit 1\n", encoding="utf-8")
    ip_stub.chmod(0o755)

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


def _link_answer(tmp_path: Path, device: str, benutzt: str,
                 dauerhaft: str = "") -> None:
    """Was `ip -d link show dev <device>` sagt.

    iproute2 schreibt die dauerhafte Adresse NUR dann hinter die
    benutzte, wenn beide sich unterscheiden - `permaddr` fehlt also,
    solange auf dem Adapter seine eigene Adresse liegt. Genau diese
    beiden Formen bildet der Aufruf hier ab.
    """
    zeile = f"    link/ether {benutzt} brd ff:ff:ff:ff:ff:ff"
    if dauerhaft:
        zeile += f" permaddr {dauerhaft}"
    zeile += " promiscuity 0 allmulti 0 minmtu 256 maxmtu 2304"
    (tmp_path / "nmcli" / f"link-{device}").write_text(
        f"3: {device}: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 "
        "qdisc noqueue state UP mode DORMANT group default qlen 1000\n"
        f"{zeile}\n", encoding="utf-8")


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
    _answer(tmp_path, "SSID,SIGNAL,SECURITY,ACTIVE,BSSID",
            _terse(HOSTILE_SSID, "88", "WPA2", "no", DOKU_BSSID) + "\n"
            + _terse("Zuhause", "72", "WPA2", "yes", DOKU_BSSID_ZWEITER) + "\n"
            + _terse("Nachbar", "41", "--", "no", DOKU_BSSID_NACHBAR) + "\n")
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
    _answer(tmp_path, "SSID,SIGNAL,SECURITY,ACTIVE,BSSID",
            _terse(COLON_SSID, "72", "--", "yes", DOKU_BSSID) + "\n"
            + _terse("Nachbar", "41", "WPA2", "no", DOKU_BSSID_NACHBAR) + "\n")
    _answer(tmp_path, "active,ssid", _terse("yes", COLON_SSID) + "\n")

    result = _run(script, ["list"], stubs, tmp_path / "home", tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    networks = json.loads(result.stdout)
    assert networks[0] == {"ssid": COLON_SSID, "signal": 72,
                           "secure": False, "active": True,
                           "bssid": DOKU_BSSID}
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
    _answer(tmp_path, "SSID,SIGNAL,SECURITY,ACTIVE,BSSID",
            _terse(COLON_SSID, "40", "WPA2", "no", DOKU_BSSID) + "\n"
            + _terse("Zuhause", "55", "WPA2", "no", DOKU_BSSID_NACHBAR) + "\n"
            + _terse(COLON_SSID, "91", "WPA2", "no", DOKU_BSSID_ZWEITER) + "\n")

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
    _answer(tmp_path, "SSID,SIGNAL,SECURITY,ACTIVE,BSSID",
            _terse("Zuhause", "", "WPA2", "no", DOKU_BSSID) + "\n")

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
def test_ohne_verbindung_bleiben_die_verbindungsfelder_leer(script, stubs,
                                                            tmp_path):
    """Hiess bis zum 22.08.2026 "no active connection is an empty
    document" und verlangte woertlich `{}`.

    Das ist mit der Geraeteadresse hinfaellig geworden, und zwar aus
    einem Grund und nicht aus Bequemlichkeit: die eigene Adresse
    existiert OHNE Verbindung, und genau dann braucht man sie - wer sie
    in einem Hochschul- oder Firmennetz anmelden muss, ist noch nicht
    drin. Ein leeres Dokument haette sie in dem einen Fall verschwiegen,
    fuer den sie angezeigt wird.

    Was NICHT existiert, steht weiterhin nicht da: kein Name, keine
    Adresse im Netz, kein Gateway, kein Namensdienst, keine
    Verschluesselung. Hier findet die Attrappe auch kein WLAN-Geraet,
    also bleibt selbst die Adresse leer - behauptet wird nichts.
    """
    result = _run(script, ["details"], stubs, tmp_path / "home", tmp_path)

    details = json.loads(result.stdout)
    assert details == {"name": "", "type": "", "device": "", "ip": "",
                       "gateway": "", "dns": "", "security": "",
                       "mac": "", "mac_wechselt": False}


# --------------------------------------------------------------------
# die Geraeteadresse (22.08.2026)
#
# GEMELDET, woertlich: "mir ist aufgefallen, dass man in dem ags fenster
# für wlan nirgendwo eine info zur macadresse hat, weil diese teilweise
# auch sehr wichtig ist".
#
# DIE GEFAHR DIESER ANZEIGE steht ueber adapter_adresse() in
# ags-network-scripts.template: NetworkManager kann die Adresse ersetzen
# (`wifi.cloned-mac-address`), und dann gibt es zwei - die dauerhafte auf
# dem Geraet und die benutzte, die das Netz sieht. Wer die falsche zeigt,
# schickt den Nutzer in einen Fehler, den er nicht findet: er meldet eine
# Adresse an, das Netz sieht eine andere, nichts geht.
#
# Die drei Faelle unten sind darum genau die drei, in denen sich das
# entscheidet.
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_die_geraeteadresse_kommt_aus_derselben_auskunft(script, stubs,
                                                         tmp_path):
    """Verbunden, und auf dem Adapter liegt seine eigene Adresse.

    `ip -d link` schreibt dann kein `permaddr` - es gibt nichts zu
    unterscheiden -, und die Anzeige braucht keinen Hinweis.
    """
    _answer(tmp_path, "NAME,TYPE,DEVICE,STATE",
            _terse("Zuhause", "802-11-wireless", "wlan0", "activated") + "\n")
    _answer(tmp_path, "802-11-wireless-security.key-mgmt",
            _terse("802-11-wireless-security.key-mgmt", "wpa-psk") + "\n")
    _link_answer(tmp_path, "wlan0", DOKU_MAC)

    result = _run(script, ["details"], stubs, tmp_path / "home", tmp_path)

    details = json.loads(result.stdout)
    assert details["mac"] == DOKU_MAC
    assert details["mac_wechselt"] is False
    # Die Verschluesselung faehrt in DERSELBEN Antwort mit. Sie stand bis
    # zum 22.08.2026 als eigener `execAsync("bash -c ...")`-Aufruf im
    # Fenster - siehe test_die_detailansicht_stellt_nur_noch_eine_frage.
    assert details["security"] == "wpa-psk"


@pytest.mark.allow_subprocess
def test_eine_ersetzte_adresse_wird_als_wechselnd_gemeldet(script, stubs,
                                                           tmp_path):
    """Der gefaehrliche Fall: NetworkManager benutzt eine Ersatzadresse.

    Angezeigt wird die BENUTZTE - das ist die, die das Netz sieht und
    die in ein Anmeldeformular gehoert. Dass sie nicht die eigene des
    Adapters ist, MUSS mitgesagt werden: eine Adresse ohne den Hinweis
    "diese wechselt" ist eine Falle.

    Die dauerhafte taucht in der Antwort NICHT auf. Sie waere die
    Adresse, die auf dem Geraet steht - und die anzuzeigen ist genau der
    Fehler, um den es hier geht.
    """
    _answer(tmp_path, "NAME,TYPE,DEVICE,STATE",
            _terse("Campus", "802-11-wireless", "wlan0", "activated") + "\n")
    _link_answer(tmp_path, "wlan0", DOKU_MAC_ERSATZ, dauerhaft=DOKU_MAC)

    result = _run(script, ["details"], stubs, tmp_path / "home", tmp_path)

    details = json.loads(result.stdout)
    assert details["mac"] == DOKU_MAC_ERSATZ
    assert details["mac_wechselt"] is True
    assert DOKU_MAC not in result.stdout


@pytest.mark.allow_subprocess
def test_ohne_verbindung_steht_die_geraeteadresse_trotzdem_da(script, stubs,
                                                              tmp_path):
    """Der Fall, fuer den die ganze Anzeige da ist.

    Keine aktive Verbindung, aber ein WLAN-Adapter mit einer Adresse.
    Sie kommt ueber `nmcli -t -f DEVICE,TYPE dev`, und `p2p-dev-wlan0`
    darf sie nicht liefern: dieses Geraet traegt den Typ `wifi-p2p`, hat
    keine eigene Verbindung, und seine Adresse waere die falsche
    Antwort.
    """
    _answer(tmp_path, "DEVICE,TYPE",
            _terse("p2p-dev-wlan0", "wifi-p2p") + "\n"
            + _terse("wlan0", "wifi") + "\n"
            + _terse("eth0", "ethernet") + "\n")
    _link_answer(tmp_path, "wlan0", DOKU_MAC)

    result = _run(script, ["details"], stubs, tmp_path / "home", tmp_path)

    details = json.loads(result.stdout)
    assert details["device"] == "wlan0"
    assert details["mac"] == DOKU_MAC
    assert details["mac_wechselt"] is False
    # Was es ohne Verbindung nicht gibt, wird auch nicht behauptet.
    assert details["name"] == ""
    assert details["ip"] == ""
    assert details["security"] == ""


@pytest.mark.allow_subprocess
def test_bei_stehendem_vpn_beschreibt_die_auskunft_die_leitung_darunter(
        script, stubs, tmp_path):
    """`con show --active | head -1` nahm die erste Zeile, die nmcli
    nennt - und das ist bei stehendem Tunnel der Tunnel.

    Bis zum 22.08.2026 war das ein falscher Name und ein falscher Typ in
    der Detailansicht. Seit die Geraeteadresse dazugehoert, ist es
    schlimmer: ein tun-Anschluss hat gar keine, die Zeile stuende also
    leer da, waehrend der Adapter darunter seine hat.
    """
    _answer(tmp_path, "NAME,TYPE,DEVICE,STATE",
            _terse("Buero: IPsec", "vpn", "tun0", "activated") + "\n"
            + _terse("Campus", "802-11-wireless", "wlan0", "activated") + "\n")
    _link_answer(tmp_path, "wlan0", DOKU_MAC)

    result = _run(script, ["details"], stubs, tmp_path / "home", tmp_path)

    details = json.loads(result.stdout)
    assert details["name"] == "Campus"
    assert details["type"] == "802-11-wireless"
    assert details["device"] == "wlan0"
    assert details["mac"] == DOKU_MAC


@pytest.mark.allow_subprocess
def test_die_adresse_des_zugangspunktes_ist_die_des_aktiven_senders(
        script, stubs, tmp_path):
    """Ein Name, zwei Sender - und der aktive ist der SCHWAECHERE.

    Fuer Signal und Verschluesselung gilt weiter der staerkste (mit dem
    haette ein Verbinden zu tun). Fuer die BSSID nicht: gefragt ist, an
    welchem Sender dieser Rechner haengt, und ein Rechner bleibt an
    seinem, bis der Wechsel sich lohnt. Naehme hier der staerkste, zeigte
    das Fenster in genau dem Netz die falsche Adresse an, fuer das die
    Angabe gedacht ist - einem grossen mit mehreren Sendern.
    """
    _answer(tmp_path, "SSID,SIGNAL,SECURITY,ACTIVE,BSSID",
            _terse("Campus", "88", "WPA2", "no", DOKU_BSSID) + "\n"
            + _terse("Campus", "44", "WPA2", "yes", DOKU_BSSID_ZWEITER) + "\n"
            + _terse("Nachbar", "41", "--", "no", DOKU_BSSID_NACHBAR) + "\n")

    result = _run(script, ["list"], stubs, tmp_path / "home", tmp_path)

    networks = json.loads(result.stdout)
    assert networks[0]["ssid"] == "Campus"
    assert networks[0]["signal"] == 88
    assert networks[0]["active"] is True
    assert networks[0]["bssid"] == DOKU_BSSID_ZWEITER
    # Ohne aktiven Sender bleibt es beim staerksten - dann ist die
    # Adresse ohnehin nur eine Auskunft ueber ein fremdes Netz.
    assert networks[1]["bssid"] == DOKU_BSSID_NACHBAR


@pytest.mark.allow_subprocess
def test_die_bssid_ueberlebt_ihre_eigenen_doppelpunkte(script, stubs,
                                                       tmp_path):
    """Das Feld dieser Zeile mit den MEISTEN Doppelpunkten.

    nmcli schuetzt jeden davon mit einem Backslash. Ginge die BSSID an
    nmcli_fields vorbei, machte `IFS=:` aus einem Netz zehn Felder - und
    im Fenster stuende "00" als Adresse des Zugangspunktes.
    """
    _answer(tmp_path, "SSID,SIGNAL,SECURITY,ACTIVE,BSSID",
            _terse("Campus", "88", "WPA2", "yes", DOKU_BSSID) + "\n")

    result = _run(script, ["list"], stubs, tmp_path / "home", tmp_path)

    networks = json.loads(result.stdout)
    assert networks[0]["bssid"] == DOKU_BSSID


def test_keine_echte_adresse_steht_in_diesem_test():
    """Der Selbstschutz - siehe den Kopf bei DOKU_MAC.

    Eine MAC-Adresse benennt ein Geraet. Eine, die beim Ausprobieren
    "mal eben" aus `ip link` in eine Zusicherung kopiert wurde, steht ab
    da im Verlauf und in jedem Klon.

    Geprueft wird nicht "sieht erfunden aus" - das kann niemand
    entscheiden -, sondern die Herkunft: JEDE Adresse in dieser Datei
    und in den beiden Vorlagen, um die es geht, muss aus dem Bereich
    stammen, den RFC 7042 (2.1.2) fuer Dokumentation freihaelt. Aus dem
    vergibt die IEEE nichts, er kann also kein Geraet benennen.
    """
    doku = re.compile(r"^00:00:5[Ee]:00:53:[0-9A-Fa-f]{2}$")
    muster = re.compile(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}")
    # ff:ff:ff:ff:ff:ff ist keine Adresse, sondern "an alle" - sie steht
    # in der Zeile, die `ip -d link` ausgibt, und benennt nichts.
    rundruf = "ff:ff:ff:ff:ff:ff"

    dateien = [Path(__file__),
               SRC / "templates" / "ags-network-scripts.template",
               SRC / "templates" / "ags-network.template"]

    gefunden = []
    for pfad in dateien:
        for treffer in muster.findall(pfad.read_text(encoding="utf-8")):
            if treffer.lower() == rundruf or doku.match(treffer):
                continue
            gefunden.append(f"{pfad.name}: {treffer}")

    assert gefunden == [], (
        "diese Adressen stammen nicht aus dem Dokumentationsbereich von "
        f"RFC 7042 (00:00:5E:00:53:00-FF): {gefunden}. Eine MAC-Adresse "
        "benennt ein Geraet - hier darf keine stehen, die eines "
        "bezeichnen koennte.")


# --------------------------------------------------------------------
# ags-control-center.template, gegen das, was dieses Skript kennt
# --------------------------------------------------------------------
#
# NEU am 19.08.2026, GEMELDET vom Nutzer ein zweites Mal ("ich sehe bei
# kontrollzentrum immernoch die pfade bei netzwerk und verbindungen ...
# auch bei bluetooth"): ags-control-center.template ruft
# `runScript(action)` acht Mal, gegen DASSELBE Skript wie oben - der
# Kommentar bei SCRIPTS dort sagt, warum es kein zweites gibt. Zwei der
# acht Aktionen (`icon`, `bluetooth`) kennt der `case`-Zweig oben nicht
# mehr: er hat sie am 17.08.2026 verloren (siehe der Kommentar ueber dem
# `case`), aber niemand hat die beiden Aufrufer mitgezogen. Der
# `*)`-Zweig antwortet mit "Usage: $0 {...}" - einer ZEILE und keinem
# leeren String -, also griff kein `|| Rueckfall` im Kontrollzentrum,
# und der Nutzer sah den Skriptpfad statt eines Wertes.
#
# Reine Textsuche und kein Lauf: die Frage ist nicht, was das Skript
# ANTWORTET, sondern ob eine gerufene Aktion im `case`-Zweig UEBERHAUPT
# STEHT - das entscheidet sich, ohne dass irgendetwas laeuft.

_CONTROL_CENTER = SRC / "templates" / "ags-control-center.template"
_RUN_SCRIPT_CALL = re.compile(r'runScript\("([^"]+)"\)')
# Eine Zeile des `case "$ACTION" in`-Zweigs: vier Leerzeichen Einrueckung,
# dann ein bareword vor der schliessenden Klammer. Faengt weder
# `case "$ACTION" in` selbst noch `*)` (beginnt mit `*`, keinem Buchstaben).
_NETWORK_SCRIPT_ACTION = re.compile(r'^ {4}([a-z][a-z0-9-]*)\)', re.MULTILINE)


def test_every_action_the_control_centre_asks_for_exists_in_the_script():
    """Jede Aktion, die ags-control-center.template ruft, muss im
    `case`-Zweig von ags-network-scripts.template stehen - sonst
    landet der Rueckgabewert im `*)`-Zweig und ist der Skriptpfad, kein
    Wert (siehe den Kopf dieses Abschnitts).

    NICHT geprueft wird die Gegenrichtung: `list`, `connect` und
    `details` stehen im `case`-Zweig und werden trotzdem von hier aus
    nie gerufen - sie gehoeren dem Netzwerkfenster
    (NetworkManager.tsx), nicht diesem Fenster, und das ist gewollt.
    """
    called = set(_RUN_SCRIPT_CALL.findall(
        _CONTROL_CENTER.read_text(encoding="utf-8")))
    known = set(_NETWORK_SCRIPT_ACTION.findall(
        (SRC / "templates" / "ags-network-scripts.template")
        .read_text(encoding="utf-8")))

    unknown = called - known
    assert unknown == set(), (
        f"ags-control-center.template ruft runScript() mit {sorted(unknown)} "
        f"- ags-network-scripts.template kennt im case-Zweig nur "
        f"{sorted(known)}. Der `*)`-Zweig dort gibt seinen eigenen Pfad "
        "zurueck, und der landet unveraendert auf dem Bildschirm.")


# --------------------------------------------------------------------
# was ein Oeffnen kosten darf (Aufgabe 36, 20.08.2026)
#
# GEMELDET, woertlich: "die ags fenster bluetooth und wlan laden
# teilweise sehr lange um den inhalt anzuzeigen das muss performanter
# und user friendly werden".
#
# Die Reparatur haengt an vier Aussagen, und jede einzelne davon laesst
# sich mit einer Zeile wieder einreissen, ohne dass ein anderer Test
# hier etwas merkt: der Aufbau wuerde weiter funktionieren, nur wieder
# zwei Sekunden dauern. Genau dafuer stehen die Waechter unten.
# --------------------------------------------------------------------

_NETWORK_PAGE = SRC / "templates" / "ags-network.template"
_BLUETOOTH_PAGE = SRC / "templates" / "ags-bluetooth.template"


def _ohne_kommentare(text: str) -> str:
    """Die Vorlage ohne ihre `//`-Zeilen.

    Dieselbe Falle wie in tests/src/test_ags_i18n.py: die Koepfe dieser
    beiden Dateien ZITIEREN die Zeilen, um die es geht (`await
    scanWifi()`, `sleep 1`), um zu erklaeren, warum sie weg sind. Ein
    schlichtes `in text` waere damit auch dann wahr, wenn die Reparatur
    zurueckgenommen wird.
    """
    zeilen = []
    for zeile in text.splitlines():
        blank = zeile.lstrip()
        if blank.startswith("//") or blank.startswith("*") or blank.startswith("/*"):
            continue
        zeilen.append(zeile)
    return "\n".join(zeilen)


def test_der_schnelle_weg_der_netzliste_sagt_ausdruecklich_nicht_suchen():
    """`nmcli dev wifi list` OHNE `--rescan` ist `--rescan auto`.

    nmcli sucht dann von sich aus, sobald der Zwischenspeicher aelter
    als 30 Sekunden ist - derselbe Aufruf antwortet mal in 13 ms und mal
    in Sekunden. GEMESSEN am 20.08.2026: 13 ms mit `--rescan no` gegen
    3552 ms und 5899 ms mit `--rescan yes`.

    Das ist das "TEILWEISE" aus der Meldung. Der schnelle Weg muss
    ausdruecklich "nein" sagen, sonst ist er nicht verlaesslich schnell.
    """
    text = (SRC / "templates" / "ags-network-scripts.template").read_text(
        encoding="utf-8")
    rumpf = "\n".join(z for z in text.splitlines()
                      if not z.lstrip().startswith("#"))

    # Fortsetzungszeilen zuerst zusammenziehen: der Aufruf steht ueber
    # zwei Zeilen, und ein `\` am Zeilenende wuerde ihn sonst genau vor
    # dem `--rescan` abschneiden.
    ganz = re.sub(r"\\\n\s*", " ", rumpf)
    aufrufe = re.findall(r"nmcli[^\n|]*dev wifi list[^\n|]*", ganz)
    assert aufrufe, "ags-network-scripts.template fragt keine Netzliste mehr ab"
    ohne = [a for a in aufrufe if "--rescan" not in a]
    assert ohne == [], (
        "eine Netzabfrage ohne --rescan - nmcli nimmt dann 'auto' und sucht "
        f"nach 30 Sekunden von selbst: {ohne}")


def test_die_netzliste_startet_nicht_ein_jq_je_netz():
    """GEMESSEN am 20.08.2026 bei zehn Netzen: 16 ms fuer zehn
    jq-Starts gegen 2 ms fuer einen einzigen.

    Der Betrag ist klein, das Muster ist es nicht - es waechst mit der
    Zahl der Nachbarn. Geprueft wird die Schleife selbst: zwischen
    `while ... read` und dem `done` darf kein jq stehen.
    """
    text = (SRC / "templates" / "ags-network-scripts.template").read_text(
        encoding="utf-8")
    rumpf = "\n".join(z for z in text.splitlines()
                      if not z.lstrip().startswith("#"))

    schleifen = re.findall(r"while IFS= read -r line; do(.*?)done", rumpf,
                           re.DOTALL)
    assert schleifen, "die Zerlegeschleife der Netzliste ist verschwunden"
    mit_jq = [s for s in schleifen if "jq" in s]
    assert mit_jq == [], (
        "ein jq-Start INNERHALB der Schleife, also einer je Netz in "
        "Reichweite - alle Netze gehen in EINEN Aufruf (--args)")


def test_die_verbindungsauskunft_stoesst_keinen_suchlauf_an():
    """Der teuerste gemessene Fund: DERSELBE Suchlauf, zweimal.

    `getConnectionInfo()` rief `scanWifi()` nur fuer die Signalstaerke,
    und `updateDisplay()` rief es unmittelbar danach ein zweites Mal.
    GEMESSEN am 20.08.2026: zwei Suchlaeufe zu je 1060 ms in einem
    einzigen Aufbau von 2160 ms.

    Die Liste kommt seither als Parameter herein. Wer sie nicht hat,
    uebergibt eine leere - er bekommt dann 0, genau wie vorher bei einem
    fehlgeschlagenen Suchlauf.
    """
    rumpf = _ohne_kommentare(_NETWORK_PAGE.read_text(encoding="utf-8"))

    koerper = re.search(
        r"async function getConnectionInfo\((.*?)\n\}", rumpf, re.DOTALL)
    assert koerper, "getConnectionInfo() ist verschwunden"
    assert "scanWifi(" not in koerper.group(1), (
        "getConnectionInfo() sucht wieder selbst - das ist der doppelte "
        "Suchlauf von vor dem 20.08.2026, 1060 ms geschenkt")


def test_der_erste_aufbau_der_netzseite_fragt_den_funk_nicht():
    """Stufe 1 zeigt den Zwischenspeicher (51 ms), Stufe 2 sucht nach.

    `scanWifi(true)` ist der echte Suchlauf (3,5 bis 5,9 s, GEMESSEN am
    20.08.2026) und darf NUR in `sucheNach()` stehen - dem Zweig, der
    ohne `await` angestossen wird und waehrenddessen sagt, dass er
    laeuft. Stuende er in `updateDisplay()`, waere das Fenster wieder
    das, was gemeldet wurde: sekundenlang leer.
    """
    rumpf = _ohne_kommentare(_NETWORK_PAGE.read_text(encoding="utf-8"))

    update = re.search(
        r"const updateDisplay = async \(\) => \{(.*?)\n    \}", rumpf,
        re.DOTALL)
    assert update, "updateDisplay() der Netzseite ist verschwunden"
    assert "scanWifi(true)" not in update.group(1), (
        "updateDisplay() sucht wieder selbst, statt erst den "
        "Zwischenspeicher zu zeigen - genau der Zustand der Meldung")
    assert "scanWifi(false)" in update.group(1), (
        "updateDisplay() liest die Netzliste gar nicht mehr")


def test_bluetooth_fragt_seine_vier_listen_gleichzeitig():
    """GEMESSEN am 20.08.2026 mit einer Attrappe, die nicht antwortet:
    nacheinander 12006 ms, gleichzeitig 3003 ms.

    Im gesunden Fall ist diese Seite nicht langsam (10 ms). Der Fall aus
    der Meldung ist der andere - antwortet bluez nicht, lief jede der
    vier Fragen in ihre volle Frist, und die vier Fristen addierten
    sich. FRIST soll die laengste Wartezeit sein, nicht ein Viertel
    davon.
    """
    rumpf = _ohne_kommentare(_BLUETOOTH_PAGE.read_text(encoding="utf-8"))

    lese = re.search(r"async function readDevices\(\).*?\n\}", rumpf,
                     re.DOTALL)
    assert lese, "readDevices() ist verschwunden"
    assert "Promise.all" in lese.group(0), (
        "readDevices() fragt seine drei Listen wieder nacheinander - "
        "drei Fristen statt einer")

    update = re.search(
        r"const updateDisplay = async \(\) => \{(.*?)\n    \}", rumpf,
        re.DOTALL)
    assert update, "updateDisplay() der Bluetooth-Seite ist verschwunden"
    assert "Promise.all" in update.group(1), (
        "updateDisplay() fragt Adapter und Geraete wieder nacheinander")


def test_beide_seiten_frischen_beim_seitenwechsel_auf():
    """`wechsleSeite()` setzt nur `set_visible_child_name()`.

    Keine Seite erfaehrt darueber, dass sie jetzt die gezeigte ist -
    `notify::visible` feuert nur, wenn die GANZE Schale auf- oder
    zugeht. Ohne die `map`-Zeile sieht, wer bei offener Schale links
    umschaltet, den Stand des letzten Taktes (bis zu 5000 ms alt), und
    erst DANACH laeuft die Abfrage.

    GEMESSEN am 20.08.2026 (GTK4 headless ueber broadwayd, eigener
    XDG_RUNTIME_DIR, kein Sitzungsbus): ein Gtk.Stack mappt genau sein
    sichtbares Kind und unmappt das vorige - beim Blaettern UND beim
    Wiederaufgehen der Schale.
    """
    for pfad in (_NETWORK_PAGE, _BLUETOOTH_PAGE):
        rumpf = _ohne_kommentare(pfad.read_text(encoding="utf-8"))
        assert re.search(r'container\.connect\("map"', rumpf), (
            f"{pfad.name} frischt beim Seitenwechsel nicht auf - "
            "ohne den map-Rueckruf bleibt bis zu 5 Sekunden der alte "
            "Stand stehen")


def test_die_wartezeile_wird_in_jedem_ausgang_wieder_weggenommen():
    """Eine Scheibe, die sich ueber einem Fehler weiterdreht, behauptet,
    es laufe noch etwas - sie ist schlimmer als eine Fehlermeldung.

    Geprueft wird das Verhaeltnis: wer `sucheWrap` sichtbar macht, muss
    es mindestens ebenso oft wieder unsichtbar machen.
    """
    for pfad in (_NETWORK_PAGE, _BLUETOOTH_PAGE):
        rumpf = _ohne_kommentare(pfad.read_text(encoding="utf-8"))
        an = len(re.findall(r"sucheWrap\.set_visible\(true\)", rumpf))
        aus = len(re.findall(r"sucheWrap\.set_visible\(false\)", rumpf))
        assert an > 0, f"{pfad.name} zeigt gar keine Wartezeile mehr"
        assert aus >= an, (
            f"{pfad.name} zeigt die Wartezeile {an}x und nimmt sie {aus}x "
            "wieder weg - ein Ausgang ohne Ruecknahme laesst die Scheibe "
            "ueber einem Fehler stehen")


# --------------------------------------------------------------------
# was ein Oeffnen der DETAILANSICHT kosten darf (22.08.2026)
#
# Dieselbe Sorte Waechter wie der Block darueber und aus demselben
# Grund: die Reparatur laesst sich mit einer Zeile wieder einreissen,
# ohne dass ein anderer Test hier etwas merkt - die Ansicht wuerde
# weiter funktionieren, nur wieder drei Prozessketten kosten.
# --------------------------------------------------------------------

def test_die_detailansicht_stellt_nur_noch_eine_frage():
    """Bis zum 22.08.2026 drei `execAsync` hintereinander, jedes mit
    eigenem `bash -c` und eigenem `await`: Gateway, DNS,
    Verschluesselung.

    Sie sind drei Felder EINER Auskunft, und `details` in
    ags-network-scripts.template hatte genau diese Auskunft schon als
    Aufgabe - es rief sie nur niemand. Die Geraeteadresse, der Anlass
    der Aenderung, ist darum kein VIERTER Aufruf geworden, sondern ein
    Feld derselben Antwort.

    Es ist dieselbe Rechnung wie am 20.08.2026 (Aufgabe 36, 2160 ms auf
    43 ms): nicht die einzelne Frage ist teuer, sondern ihre Zahl.
    """
    rumpf = _ohne_kommentare(_NETWORK_PAGE.read_text(encoding="utf-8"))

    koerper = re.search(r"const showDetail = async \(\) => \{(.*?)\n    \}",
                        rumpf, re.DOTALL)
    assert koerper, "showDetail() ist verschwunden"
    aufrufe = re.findall(r"execAsync\(", koerper.group(1))
    assert len(aufrufe) == 1, (
        f"showDetail() stellt {len(aufrufe)} Fragen statt einer - alle "
        "Felder der Detailansicht kommen aus `details`")
    assert "bash -c" not in koerper.group(1), (
        "showDetail() startet wieder eine Shell - die Auskunft holt das "
        "Skript, nicht das Fenster")


def test_die_detailansicht_ist_auch_ohne_verbindung_erreichbar():
    """Die eigene Geraeteadresse braucht man, um sie ANZUMELDEN - und
    wer das tut, ist noch nicht verbunden.

    Das Info-Symbol hatte bis zum 22.08.2026 ein `if
    (currentConnectionInfo.type !== "none")` um sich: es tat im
    getrennten Zustand nichts, ohne zu sagen warum. Genau dieser Zustand
    ist der, in dem die Ansicht jetzt ihre wichtigste Auskunft traegt.
    """
    rumpf = _ohne_kommentare(_NETWORK_PAGE.read_text(encoding="utf-8"))

    knopf = re.search(r"const buildDetailButton = \(\).*?\n      \}\)",
                      rumpf, re.DOTALL)
    assert knopf, "buildDetailButton() ist verschwunden"
    assert 'type !== "none"' not in knopf.group(0), (
        "das Info-Symbol ist im getrennten Zustand wieder gesperrt - "
        "dann fehlt die Geraeteadresse genau dann, wenn man sie braucht")

    # Und die Kehrseite: was es ohne Verbindung nicht gibt, darf auch
    # nicht angeboten werden.
    assert "detailDisconnectBtn.set_visible(verbunden)" in rumpf, (
        "der Trennen-Knopf steht auch ohne Verbindung da - ein Angebot "
        "auf eine Handlung ohne Gegenstand")
    assert 'detailBssidRow.set_visible(currentConnectionInfo.type === "wifi")' in rumpf, (
        "die Zeile des Zugangspunktes bleibt an einer Kabelverbindung "
        "oder ohne Verbindung stehen - ein Gedankenstrich behauptet "
        "dort, es gaebe eine Antwort")


def test_die_adresse_des_zugangspunktes_kostet_keine_eigene_abfrage():
    """Sie faehrt in der Netzliste mit, die ohnehin jeden Takt laeuft.

    Eine eigene `nmcli ... dev wifi list`-Abfrage nur fuer die BSSID
    waere ein zweiter Prozess (GEMESSEN am 20.08.2026: ~13 ms je Aufruf,
    im Kopf von network_list aufgeschrieben) fuer eine Spalte, die
    dieselbe Antwort ohne Aufpreis mitbringt - und eine zweite
    Gelegenheit fuer den `--rescan auto`-Fall, an dem die Meldung vom
    20.08.2026 hing.
    """
    text = (SRC / "templates" / "ags-network-scripts.template").read_text(
        encoding="utf-8")
    rumpf = "\n".join(z for z in text.splitlines()
                      if not z.lstrip().startswith("#"))
    ganz = re.sub(r"\\\n\s*", " ", rumpf)

    aufrufe = re.findall(r"nmcli[^\n|]*dev wifi list[^\n|]*", ganz)
    # `get_wifi_ssid` fragt dieselbe Quelle nach EINEM Feld (active,ssid)
    # und beantwortet damit `info` - die Leiste fragt das mehrmals je
    # Minute und braucht die Liste nicht. Gemeint ist hier die Abfrage
    # der LISTE, erkennbar an der Signalspalte.
    liste = [a for a in aufrufe if "SIGNAL" in a]
    assert len(liste) == 1, (
        f"{len(liste)} Abfragen der Netzliste statt einer: {liste}")
    assert "BSSID" in liste[0], (
        "die BSSID fehlt in der Feldliste der Netzabfrage - sie kaeme "
        "dann aus einem zweiten nmcli-Start")
    mit_bssid = [a for a in aufrufe if "BSSID" in a]
    assert mit_bssid == liste, (
        f"eine zweite Abfrage nur fuer die BSSID: {mit_bssid}")

    # Und im Fenster fragt danach ueberhaupt niemand: die Adresse steht
    # in currentConnectionInfo, aus der Liste des laufenden Taktes.
    seite = _ohne_kommentare(_NETWORK_PAGE.read_text(encoding="utf-8"))
    assert not re.search(r"execAsync\([^)]*[Bb][Ss][Ss][Ii][Dd]", seite), (
        "das Netzfenster fragt die BSSID selbst ab - sie liegt schon in "
        "currentConnectionInfo")
