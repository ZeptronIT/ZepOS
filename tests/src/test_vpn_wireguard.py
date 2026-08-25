# SPDX-License-Identifier: GPL-3.0-or-later
"""Die zweite VPN-Bauart - und der Beweis, dass die erste sie nicht merkt.

BESTELLT am 21.08.2026: "ich will, dass das vpn fenster auch wireguard
unterstützt - wireguard dateien oder eigene konfigurationen. also
auswahl: ipsec oder ipsecv2 oder wireguard"

WAS DIESE DATEI MISST, UND IN WELCHER REIHENFOLGE
    1. Dass eine BESTEHENDE IPsec-Konfiguration nach der Aenderung
       zeichengleich dieselbe swanctl-Datei erzeugt. Das ist der
       wichtigste Test dieser Aufgabe: `settings.merge()` ERSETZT ganze
       Abschnitte (siehe seinen Kopf, es ist Absicht), und ein Dialog,
       der beim Speichern nur noch die gerade gewaehlte Bauart schreibt,
       loescht die andere. Wer das falsch baut, merkt es nicht am
       Testlauf, sondern an einem Nutzer, dessen Arbeits-VPN weg ist.
    2. Dass der Einleser eine Datei NICHT halb einliest.
    3. Dass ein privater Schluessel nie in einer Befehlszeile steht und
       nie in user-settings.json landet, und dass er 0600 ist, bevor er
       Inhalt hat - nicht erst danach.
    4. Dass WireGuard KEINE neue Zeile in /etc/sudoers.d/zepos braucht.

KEINE ECHTE VERBINDUNG, KEIN ECHTES nmcli
    Jeder Aufruf, der NetworkManager beruehren wuerde, laeuft hier gegen
    einen `runner`, der die Argumentliste aufschreibt und eine
    vorbereitete Antwort zurueckgibt. Dieselbe Trennung, die
    tests/src/test_vpn_secrets.py fuer sudo, ip und swanctl macht, nur
    eine Ebene hoeher: dort ein Stub im PATH, hier der Parameter, den
    src/vpn.py fuer genau diesen Zweck fuehrt.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from src import vpn
from src.settings import SCHEMA_VERSION
from src.settings import defaults as settings_defaults
from src.vpn import (
    UnreadableWireGuardConfig,
    nm_own_argv,
    parse_nm_state,
    parse_wg_conf,
    public_wireguard_key,
    swanctl_config,
    vpn_kind,
    wireguard_conf_text,
    wireguard_dns,
    wireguard_document,
    wireguard_status,
    write_wireguard_secret,
)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"


def _user_settings_defaults() -> dict:
    """DEFAULT_SETTINGS, geladen wie /usr/share/zepos es laedt.

    `from src.user_settings import ...` geht nicht: das Modul importiert
    `brand`, `sizes` und `theme` FLACH, so wie sie neben ihm im
    installierten Paket liegen - als Paketmitglied gibt es die nicht.
    Derselbe Kniff wie _modal_width_l() in
    tests/render/test_schale_stil.py, aus demselben Grund: die
    Erwartung soll aus DERSELBEN Quelle kommen wie die erzeugte Datei.
    """
    import sys
    sys.path.insert(0, str(SRC))
    try:
        import user_settings
        return user_settings.DEFAULT_SETTINGS
    finally:
        sys.path.remove(str(SRC))

# Ein Schluessel in der Form, die WireGuard benutzt: 32 Byte Base64, und
# damit mit `=` als Fuellzeichen am Ende. GENAU DAS ist die Falle, die
# der Einleser treffen muss - `split("=")` ueber alle Vorkommen macht
# daraus einen leeren Schluessel. Ein offensichtliches Literal, das
# nirgends sonst existiert.
PRIVATE_KEY = "iEjBia7X1lB0KEJ0tGRHW5wCcWiUAOs4hV4H1lLBb2M="
PEER_KEY = "Nz0jL1p9RGVtb1B1YmxpY0tleUZvclRlc3RzMTIzND0="
PRESHARED = "c2hhcmVkc2VjcmV0Zm9ydGVzdHNvbmx5bm90cmVhbDEyMz0="

# Adressen aus dem Dokumentationsbereich (RFC 5737 / RFC 3849-Geist),
# dieselbe Regel wie in test_vpn_secrets.py.
CONF = f"""# Von irgendwo heruntergeladen
[Interface]
PrivateKey = {PRIVATE_KEY}
Address = 203.0.113.9/32, 198.51.100.4/32
DNS = 203.0.113.53, example.invalid
ListenPort = 51820
MTU = 1380

[Peer]
PublicKey = {PEER_KEY}
PresharedKey = {PRESHARED}
Endpoint = gateway.example.invalid:51820
AllowedIPs = 10.0.0.0/8
AllowedIPs = 192.0.2.0/24
PersistentKeepalive = 25
"""


class Recorder:
    """Ein `runner`, der aufschreibt und nichts ausfuehrt."""

    def __init__(self, answers: dict[str, str] | None = None,
                 returncode: int = 0) -> None:
        self.calls: list[list[str]] = []
        self.answers = answers or {}
        self.returncode = returncode
        self.modes: list[int] = []
        self.watch: Path | None = None

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        if self.watch is not None and self.watch.exists():
            self.modes.append(stat.S_IMODE(self.watch.stat().st_mode))
        key = " ".join(argv)
        stdout = next((text for needle, text in self.answers.items()
                       if needle in key), "")
        return subprocess.CompletedProcess(argv, self.returncode,
                                           stdout=stdout, stderr="")

    def flat(self) -> str:
        return "\n".join(" ".join(call) for call in self.calls)


# --------------------------------------------------------------------
# 1. Die bestehende IPsec-Konfiguration merkt nichts
# --------------------------------------------------------------------

# Eine Einstellungsdatei, wie sie VOR dem 21.08.2026 aussah: kein
# `kind`, kein `wireguard`. Genau das, was auf jeder Maschine liegt, die
# es schon gibt.
LEGACY = {
    "schema_version": SCHEMA_VERSION,
    "vpn": {
        "server": "gw.example.invalid",
        "username": "someone",
        "connection_name": "work",
        "routed_networks": ["10.0.0.0/8", "192.0.2.0/24"],
        "bypass_networks": [],
        "test_host": "inside.example.invalid",
        "dns": {"servers": ["203.0.113.53"], "search_domain": "example.invalid"},
        "phase1": {"version": 2, "aggressive": False,
                   "proposals": "aes256-sha256-ecp521", "keylife": 86400,
                   "dpd_delay": 30, "dpd_timeout": 120,
                   "encap": True, "mobike": False},
        "phase2": {"rekey_time": 43200, "life_time": 43200, "mode": "tunnel",
                   "replay_window": 32,
                   "esp_proposals": "aes256-sha256-ecp521"},
        "xauth_enabled": False,
        "debug": False,
    },
}


def test_a_settings_file_from_before_the_change_is_still_ipsec():
    """Kein `kind` heisst IPsec - und darf nie etwas anderes heissen."""
    assert vpn_kind(LEGACY) == "ipsec"


def test_an_unknown_kind_is_not_passed_through():
    """Eine vertippte Bauart darf nicht in eine Verbindung fuehren, die
    niemand gemeint hat - sie faellt auf die zurueck, die es vorher
    schon gab."""
    typo = json.loads(json.dumps(LEGACY))
    typo["vpn"]["kind"] = "wireguardd"
    assert vpn_kind(typo) == "ipsec"


def test_the_old_configuration_produces_the_very_same_swanctl_file():
    """DER WICHTIGSTE TEST DIESER AUFGABE.

    Zeichengleich, nicht "sieht gleich aus": eine Aenderung an den
    Vorgaben, an der Reihenfolge der Schluessel oder an einem der
    Phasenwerte faellt hier auf und nicht auf der Maschine eines
    Nutzers, dessen Tunnel danach etwas anderes aushandelt als vorher.

    Gehalten wird das ALTE Dokument gegen dasselbe Dokument MIT den
    neuen Schluesseln: wenn die zweite Bauart die erste beruehrt, sind
    die beiden Ergebnisse verschieden.
    """
    before = swanctl_config(LEGACY)

    migrated = json.loads(json.dumps(LEGACY))
    migrated["vpn"]["kind"] = "ipsec"
    migrated["vpn"]["wireguard"] = settings_defaults()["vpn"]["wireguard"]
    after = swanctl_config(migrated)

    assert before == after, (
        "the WireGuard keys changed the generated swanctl configuration")
    # Und die Gegenprobe, damit der Vergleich nicht zwei leere Zeichen-
    # ketten gegeneinander haelt.
    assert "gw.example.invalid" in before


def test_both_default_tables_carry_the_same_wireguard_keys():
    """Zwei Vorgabentabellen, ein Schema.

    src/settings.py::defaults() und src/user_settings.py::DEFAULT_SETTINGS
    fuehren beide einen vpn-Abschnitt, und sie fuehren ihn seit jeher
    VERSCHIEDEN LANG (die zweite kennt phase1/phase2/xauth, die erste
    nicht). Was sie beide fuehren, muessen sie gleich fuehren - sonst
    lehnt `zepos-settings set` einen Pfad ab, den das Fenster daneben
    schreibt.
    """
    lean = settings_defaults()["vpn"]
    full = _user_settings_defaults()["vpn"]
    assert lean["kind"] == full["kind"] == "ipsec"
    assert lean["wireguard"] == full["wireguard"]
    assert lean["wireguard"]["private_key_file"] == ""


# --------------------------------------------------------------------
# 2. Der Einleser liest keine Datei halb
# --------------------------------------------------------------------

def test_a_base64_key_survives_its_padding():
    """`PrivateKey = ...=` am ersten `=` trennen, nicht an allen.

    Ein Schluessel endet auf `=` oder `==`. Ein `split("=")` ueber alle
    Vorkommen haette hier einen LEEREN Schluessel ergeben - eine
    Verbindung, die sich anlegen laesst und nie zustande kommt.
    """
    conf = parse_wg_conf(CONF, "wg0.conf")
    assert conf.interface["PrivateKey"] == PRIVATE_KEY
    assert conf.peers[0]["PresharedKey"] == PRESHARED


def test_several_allowed_ips_lines_are_one_list():
    """wg-quick erlaubt mehrere AllowedIPs-Zeilen je Gegenstelle. Die
    einzige Wiederholung, die kein Fehler ist."""
    conf = parse_wg_conf(CONF, "wg0.conf")
    document = wireguard_document(conf)
    assert document["peers"][0]["allowed_ips"] == ["10.0.0.0/8", "192.0.2.0/24"]


def test_an_unknown_key_is_refused_with_file_and_line():
    """Abgebrochen, nicht ueberlesen - und mit der Stelle, die der
    Nutzer reparieren soll."""
    broken = CONF.replace("MTU = 1380", "Tabel = auto")
    with pytest.raises(UnreadableWireGuardConfig) as raised:
        parse_wg_conf(broken, "wg0.conf")
    message = str(raised.value)
    assert "wg0.conf:7" in message, message
    assert "Tabel" in message, message


def test_a_file_without_an_interface_section_is_refused():
    with pytest.raises(UnreadableWireGuardConfig):
        parse_wg_conf("[Peer]\nPublicKey = x\n", "wg0.conf")


def test_a_key_before_any_section_is_refused():
    with pytest.raises(UnreadableWireGuardConfig) as raised:
        parse_wg_conf(f"PrivateKey = {PRIVATE_KEY}\n[Interface]\n", "wg0.conf")
    assert "wg0.conf:1" in str(raised.value)


def test_a_peer_key_in_the_interface_section_is_refused():
    with pytest.raises(UnreadableWireGuardConfig) as raised:
        parse_wg_conf("[Interface]\nEndpoint = a.invalid:1\n", "wg0.conf")
    assert "Endpoint" in str(raised.value)


def test_a_second_interface_section_is_refused():
    with pytest.raises(UnreadableWireGuardConfig):
        parse_wg_conf(CONF + "\n[Interface]\nMTU = 1400\n", "wg0.conf")


# --------------------------------------------------------------------
# 3. PostUp: benannt und abgelehnt, nicht still verworfen
# --------------------------------------------------------------------

HOOKED = CONF.replace(
    "MTU = 1380",
    "MTU = 1380\nPostUp = iptables -A FORWARD -i %i -j ACCEPT\n"
    "PostDown = iptables -D FORWARD -i %i -j ACCEPT")


def test_a_hook_line_is_named_with_its_line_number():
    """`wg-quick` wuerde diese Zeile ALS ROOT AUSFUEHREN. ZepOS
    verbindet ueber NetworkManager, der das nicht tut - und der Nutzer
    erfaehrt, was nicht uebernommen wurde, statt es zu erraten."""
    conf = parse_wg_conf(HOOKED, "wg0.conf")
    assert [key for _line, key in conf.refused] == ["PostUp", "PostDown"]
    assert conf.refused[0][0] == 8, conf.refused
    # Der Rest der Datei ist trotzdem angekommen.
    assert conf.interface["MTU"] == "1380"
    assert conf.peers[0]["Endpoint"] == "gateway.example.invalid:51820"


def test_a_hook_line_never_comes_back_out():
    """Was hineinging, kommt nicht wieder heraus.

    wireguard_conf_text() schreibt die Datei, die NetworkManager
    einliest. Sie ist UNSERE Datei, aus unseren Einstellungen gebaut -
    nicht die fremde weitergereicht. Eine Haken-Zeile kann darin also
    nicht stehen, und dieser Test ist der Grund, aus dem sie es auch
    nach der naechsten Aenderung nicht kann.
    """
    conf = parse_wg_conf(HOOKED, "wg0.conf")
    text = wireguard_conf_text(wireguard_document(conf), PRIVATE_KEY,
                               wireguard_dns(conf), [PRESHARED])
    for hook in vpn.WG_HOOK_KEYS:
        assert hook not in text, f"{hook} survived into the file NM reads"
    assert "iptables" not in text


def test_the_import_command_reports_refused_lines_with_its_exit_code(
        tmp_path, monkeypatch):
    """Rueckgabewert 3: eingelesen, aber Zeilen abgelehnt.

    Ein Aufrufer, der die Ablehnung uebergehen will, muss das AKTIV tun.
    `exit 0` haette ihm erlaubt, sie nicht zu bemerken - und genau das
    ist der Unterschied zwischen "abgelehnt" und "still verworfen".
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    # `wg pubkey` waere ein echter Prozess, und tests/conftest.py
    # verbietet das zu Recht. Gemessen wird hier der Rueckgabewert des
    # Einlesens, nicht wireguard-tools.
    monkeypatch.setattr(vpn, "public_wireguard_key", lambda key: "oeffentlich")
    source = tmp_path / "wg0.conf"
    source.write_text(HOOKED, encoding="utf-8")

    assert vpn.main(["--wg-import", str(source)]) == vpn.WG_IMPORT_REFUSED

    clean = tmp_path / "clean.conf"
    clean.write_text(CONF, encoding="utf-8")
    assert vpn.main(["--wg-import", str(clean)]) == 0


def test_an_unreadable_file_ends_with_its_own_exit_code(tmp_path):
    source = tmp_path / "wg0.conf"
    source.write_text("[Interface]\nTabel = auto\n", encoding="utf-8")
    assert vpn.main(["--wg-import", str(source)]) == 65


# --------------------------------------------------------------------
# 4. Geheimnisse
# --------------------------------------------------------------------

def test_the_settings_section_carries_no_secret():
    """Der private Schluessel und die PSKs stehen NICHT in dem, was nach
    user-settings.json geht.

    Diese Datei liest der Stil-Erzeuger, gibt `zepos-settings` aus und
    fasst der Doktor an. Ein Geheimnis darin waere ein Geheimnis in vier
    Programmen.
    """
    conf = parse_wg_conf(CONF, "wg0.conf")
    document = wireguard_document(conf, private_key_file="work.key",
                                  public_key="not-a-secret",
                                  preshared_key_files=["work-peer1.psk"])
    text = json.dumps(document)
    assert PRIVATE_KEY not in text
    assert PRESHARED not in text
    assert document["private_key_file"] == "work.key"
    assert document["peers"][0]["preshared_key_file"] == "work-peer1.psk"
    # Der OEFFENTLICHE Schluessel der Gegenstelle darf und muss drin
    # stehen - ohne ihn gibt es keine Verbindung, und er ist keins.
    assert document["peers"][0]["public_key"] == PEER_KEY


def test_a_stored_key_is_private_from_its_first_byte(tmp_path, monkeypatch):
    """0600 beim Anlegen, nicht 0644 mit einem chmod hinterher.

    Gemessen unter `umask 000`, aus demselben Grund, aus dem
    tests/src/test_vpn_secrets.py seine Kinder so startet: `echo > f;
    chmod 600 f` endet bei 0600 und war dazwischen fuer jedes Konto der
    Maschine lesbar. Mit umask 000 ist der Modus, den os.open setzt, der
    Modus, den die Datei bekommt - eine 0644 hier waere eine echte 0644.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    vorher = os.umask(0)
    try:
        target = write_wireguard_secret("work.key", PRIVATE_KEY)
    finally:
        os.umask(vorher)

    assert stat.S_IMODE(target.stat().st_mode) == 0o600, oct(
        stat.S_IMODE(target.stat().st_mode))
    # Das Verzeichnis 0700 - anders als ~/.config/strongswan (0755, per
    # stat am 21.08.2026): dort liegt EINE Datei, hier liegen mehrere,
    # und ihre blossen Namen verraten schon, welche Gegenstellen es gibt.
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    assert target.read_text(encoding="utf-8").strip() == PRIVATE_KEY


def test_replacing_a_key_does_not_keep_an_older_wider_mode(
        tmp_path, monkeypatch):
    """Ein einmal zu weit geoeffneter Speicher bleibt nicht zu weit
    geoeffnet - dieselbe Wirkung wie REPLACE_DESTINATION im Fenster."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    directory = tmp_path / "wireguard"
    directory.mkdir(parents=True)
    stale = directory / "work.key"
    stale.write_text("alt\n", encoding="utf-8")
    stale.chmod(0o644)

    vorher = os.umask(0)
    try:
        target = write_wireguard_secret("work.key", PRIVATE_KEY)
    finally:
        os.umask(vorher)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_the_private_key_reaches_wg_pubkey_on_stdin_and_not_as_an_argument():
    """/proc/<pid>/cmdline ist fuer jedes Konto der Maschine lesbar,
    solange der Prozess laeuft. Dieselbe Regel, aus der das
    Sudo-Passwort aus vpn-connect.sh verschwunden ist."""
    recorder = Recorder(answers={"wg pubkey": "abc\n"})
    assert public_wireguard_key(PRIVATE_KEY, recorder) == "abc"
    assert recorder.calls == [["wg", "pubkey"]]
    assert PRIVATE_KEY not in recorder.flat()


# --------------------------------------------------------------------
# 5. NetworkManager
# --------------------------------------------------------------------

def test_apply_never_puts_the_key_in_a_command_line(tmp_path, monkeypatch):
    """Der ganze Grund fuer den Umweg ueber eine Datei.

    `nmcli connection modify <c> wireguard.private-key <schluessel>`
    waere der kuerzere Weg und stuende damit in /proc/<pid>/cmdline.
    Gemessen wird hier, dass er nirgends in einer Argumentliste steht -
    und dass die Datei, die ihn traegt, 0600 ist, WAEHREND nmcli sie
    lesen wuerde, und danach weg.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("USER", "tester")
    write_wireguard_secret("work.key", PRIVATE_KEY)

    conf = parse_wg_conf(CONF, "wg0.conf")
    document = {
        "schema_version": SCHEMA_VERSION,
        "vpn": {
            "kind": "wireguard",
            "connection_name": "work",
            "dns": wireguard_dns(conf),
            "wireguard": wireguard_document(conf, private_key_file="work.key"),
        },
    }

    recorder = Recorder()
    recorder.watch = tmp_path / "run" / "zepos-vpn" / "work.conf"
    assert vpn._wg_apply(document, recorder) == 0

    assert PRIVATE_KEY not in recorder.flat(), (
        "the private key travelled through a command line")
    assert recorder.modes and set(recorder.modes) == {0o600}, recorder.modes
    assert not recorder.watch.exists(), (
        "the file holding the private key was left behind")


def test_the_connection_is_written_to_the_user_and_not_to_the_machine():
    """`connection.permissions user:<konto>`.

    GEMESSEN am 21.08.2026 mit pkcheck: modify.own steht auf
    `allow_active=yes`, modify.system auf `auth_admin_keep`. Auf einem
    ZepOS-Konto (wheel, oertliche Sitzung) kommt ohnehin kein Dialog,
    weil das Paket networkmanager selbst eine Regel dafuer mitbringt -
    aber ein Konto OHNE wheel faellt mit dieser Zeile auf modify.own
    zurueck statt auf einen Passwortdialog. Und die Verbindung gehoert
    dann diesem Konto statt allen Konten der Maschine.
    """
    argv = nm_own_argv("work", "tester")
    assert "connection.permissions" in argv
    assert argv[argv.index("connection.permissions") + 1] == "user:tester"
    # Ein VPN ist eine Handlung und kein Zustand - dieselbe Haltung, aus
    # der die IPsec-Seite `start_action = trap` fuehrt und nicht `start`.
    assert argv[argv.index("connection.autoconnect") + 1] == "no"


@pytest.mark.parametrize("report,erwartet", [
    ("GENERAL.STATE:activated\nIP4.ADDRESS[1]:203.0.113.9/32\n",
     ("connected", "203.0.113.9")),
    # Steht, traegt nichts - genau die halbe Verbindung, fuer die es bei
    # IPsec `stale` gibt.
    ("GENERAL.STATE:activated\n", ("stale", "")),
    ("GENERAL.STATE:deactivated\nIP4.ADDRESS[1]:203.0.113.9/32\n",
     ("disconnected", "")),
    # Ohne Auskunft wird nichts behauptet.
    ("", ("disconnected", "")),
])
def test_the_three_words_mean_the_same_for_both_kinds(report, erwartet):
    assert wireguard_status("work", Recorder(answers={"nmcli": report})) == erwartet


def test_the_address_field_is_read_with_its_index_not_without():
    """Das Feld heisst `IP4.ADDRESS[1]`, nicht `IP4.ADDRESS`. Die eckige
    Klammer ist eine Nummer und keine Zierde, und ein Vergleich auf den
    blossen Namen findet sie nie."""
    state, address = parse_nm_state(
        "GENERAL.STATE:activated\nIP4.ADDRESS[1]:198.51.100.4/24\n")
    assert (state, address) == ("activated", "198.51.100.4")


def test_a_connection_without_a_name_is_not_asked_about():
    recorder = Recorder()
    assert wireguard_status("", recorder) == ("disconnected", "")
    assert recorder.calls == []


# --------------------------------------------------------------------
# 6. Was NICHT dazugekommen ist
# --------------------------------------------------------------------

def test_wireguard_needs_no_new_privileged_command():
    """KEINE neue Zeile in /etc/sudoers.d/zepos.

    IPsec braucht dort sieben Cmnd_Alias-Bloecke. WireGuard laeuft ueber
    NetworkManager und polkit und braucht keinen - und wenn hier je
    `wg-quick` auftaucht, ist das die Regel, vor der der Kopf von
    zepos-privileges-config.template warnt: `wg-quick` liest seine
    .conf ALS SHELL, `PostUp` laeuft als root, und eine sudoers-Regel
    darauf waere Root mit Umweg aus einer heruntergeladenen Datei.
    """
    text = (SRC / "system" / "zepos-privileges-config.template").read_text(
        encoding="utf-8")
    for verboten in ("wg-quick", "/usr/bin/wg "):
        assert verboten not in text, f"{verboten} became a privileged command"


def test_the_dialog_offers_three_choices_and_no_second_switch_for_one_value():
    """Die dreiteilige Auswahl - und der alte Umschalter ist WEG.

    Zwei Bedienelemente fuer phase1.version waeren zwei Stellen, an
    denen etwas Verschiedenes stehen kann, und die, die niemand findet,
    gewinnt am Ende. Regel 14: geloescht, nicht als veraltet markiert.
    """
    text = (SRC / "templates" / "ags-vpn-settings.template").read_text(
        encoding="utf-8")
    code = "\n".join(line for line in text.splitlines()
                     if not line.strip().startswith("//"))
    for label in ('_("IPsec (IKEv1)")', '_("IPsec (IKEv2)")', '_("WireGuard")'):
        assert label in code, f"{label} is not on offer"
    assert '_("IKE version")' not in code, (
        "the old IKE version toggle is still a second control for "
        "phase1.version")


def test_the_dialog_stands_on_the_rung_its_content_needs():
    """702 Punkte Inhalt passen nicht auf Sprosse M (660).

    Der Befund steht seit dem 18.08.2026 in aufgabe-34-report.md 2.6 und
    aufgabe-43-report.md. Gemessen wird der Ueberhang am gezeichneten
    Fenster in tests/render/test_vpn_breite.py; hier steht nur, dass die
    Vorlage die richtige Sprosse NENNT.
    """
    text = (SRC / "templates" / "ags-vpn-settings.template").read_text(
        encoding="utf-8")
    assert "const WIN_WIDTH = {{STYLE_MODAL_WIDTH_L}}" in text
    assert "const WIN_WIDTH = {{STYLE_MODAL_WIDTH_M}}" not in text


def test_the_dialog_still_shows_the_values_the_generator_uses():
    """Dieselbe Zusicherung wie in test_vpn_config.py, fuer die zweite
    Bauart: der WireGuard-Abschnitt der Vorgaben kommt aus DEM Erzeuger
    und ist nicht im Dialog abgeschrieben. Ein Speichern ohne
    Bearbeitung schreibt genau diese Vorgaben zurueck."""
    text = (SRC / "templates" / "ags-vpn-settings.template").read_text(
        encoding="utf-8")
    assert "{{STYLE_VPN_WIREGUARD}}" in text
    assert "{{STYLE_VPN_KIND}}" in text


def test_the_ipsec_watcher_cannot_act_on_a_wireguard_tunnel():
    """Der Waechter ruehrt sich nicht, wenn WireGuard verbunden ist.

    vpn-watcher.sh baut zusammengebrochene CHILD_SAs wieder auf, mit
    `swanctl --initiate --child`. Auf einem WireGuard-Tunnel waere das
    Unsinn - und es waere Unsinn, der jede Minute wiederkehrt.

    Er kann es nicht, und zwar aus Bauart und nicht aus Absicht:
    check_tunnel_health() steigt in der ERSTEN Zeile aus, wenn die
    Zustandsdatei fehlt, und die schreibt ausschliesslich
    vpn-connect.sh - die IPsec-Seite. Eine WireGuard-Verbindung legt sie
    nie an, also endet jede Runde bei rc=2 ("nothing to do").

    Diese Zusicherung haelt genau das fest: es ist eine Eigenschaft, auf
    die man sich verlaesst, und ohne Test waere sie beim naechsten Umbau
    des Waechters unbemerkt weg.
    """
    text = (SRC / "templates" / "vpn-watcher-config.template").read_text(
        encoding="utf-8")
    koerper = text[text.index("check_tunnel_health() {"):]
    koerper = koerper[:koerper.index("\n}\n")]
    erste = next(zeile.strip() for zeile in koerper.splitlines()[1:]
                 if zeile.strip() and not zeile.strip().startswith("#"))
    assert erste == '[ -f "$STATE_FILE" ] || return 2', (
        "check_tunnel_health() prueft nicht mehr zuerst die IPsec-"
        f"Zustandsdatei, sondern: {erste!r}. Damit koennte der Waechter "
        "auf einem WireGuard-Tunnel swanctl-Kinder wiederherstellen "
        "wollen, die es nicht gibt.")


def test_only_the_page_decides_which_script_disconnects():
    """Ein Trennen darf nicht in die falsche Bauart laufen.

    vpn-control.sh raeumt swanctl-Kinder, Routen, xfrm-Policies und
    resolv.conf ab. Auf einer WireGuard-Verbindung gibt es nichts davon,
    und der Aufruf waere im besten Fall wirkungslos und im schlechteren
    ein Eingriff in Routen, die jemand anders gesetzt hat.

    Gemessen wird, dass die Seite die Weiche wirklich hat - und dass sie
    NICHT irgendwo daneben steht: `vpn-control.sh` wird in diesem Baum
    ausser von seiner eigenen Vorlage nur von ags-vpn.template gerufen.
    """
    seite = (SRC / "templates" / "ags-vpn.template").read_text(encoding="utf-8")
    code = "\n".join(zeile for zeile in seite.splitlines()
                     if not zeile.strip().startswith("//"))
    assert 'vpnSettings.kind === "wireguard"' in code
    assert '"--wg-down"' in code and '"--wg-up"' in code
    # Genau EIN Aufruf des IPsec-Steuerskripts, und der steht im
    # else-Zweig der Weiche.
    assert code.count("SCRIPTS.vpnControl,") == 1

    # Und kein zweiter Ort, der das Skript kennt. `install-privileges`
    # bleibt erlaubt: das ist der Hinweistext, mit dem der Waechter und
    # das Verbindungsskript auf die einmalige Rechte-Regel zeigen, und
    # er trennt nichts.
    #
    # GEFUNDEN am 21.08.2026, als diese Zusicherung zum ersten Mal lief:
    # ags-control-center.template fuehrte ein `vpnControl` in seiner
    # Skripttabelle, das keine Zeile der Datei je gelesen hat. Es ist
    # mit demselben Commit geloescht - eine tote Zeile ist genau der
    # Ort, an dem eine Weiche fehlt und es niemandem auffaellt.
    andere = []
    for pfad in (SRC / "templates").glob("*.template"):
        if pfad.name in ("vpn-control-config.template", "ags-vpn.template"):
            continue
        zeilen = [z for z in pfad.read_text(encoding="utf-8").splitlines()
                  if "vpn-control.sh" in z
                  and "install-privileges" not in z
                  and not z.strip().startswith(("#", "//"))]
        if zeilen:
            andere.append(f"{pfad.name}: {zeilen[0].strip()[:60]}")
    assert andere == [], (
        f"diese Vorlagen rufen vpn-control.sh ohne die Bauart-Weiche: {andere}")
