# SPDX-License-Identifier: GPL-3.0-or-later
"""Die dritte VPN-Bauart - und der Beweis, dass keine Zeile ausbricht.

BESTELLT am 22.08.2026: "ausserdem will ich, dass wir bei vpn auch
openvpn format unterstuetzen - das brauchen wir auch"

WARUM DIESE DATEI SCHAERFER SEIN MUSS ALS DIE FUER WIREGUARD
    `wg-quick` fuehrt FUENF Zeilen als Root aus. OpenVPN fuehrt
    ACHTZEHN aus, und eine davon - `plugin` - laedt eine gemeinsame
    Bibliothek in den eigenen Prozess, ganz ohne Skript. Dazu betten
    .ovpn-Dateien Zertifikate UND den privaten Schluessel im Klartext
    ein, und der Nutzer bekommt solche Dateien von seinem Anbieter.

    Der wichtigste Test dieser Datei ist deshalb
    test_no_executing_directive_ever_comes_back_out: er faehrt ALLE
    achtzehn plus die weiterreichenden durch den Einleser und prueft am
    erzeugten Text, dass keine davon wieder herauskommt.

WAS AM 22.08.2026 GEMESSEN WURDE UND WARUM ES HIER STEHT
    NetworkManagers eigener .ovpn-Einleser verschluckt genau diese
    Zeilen SPURLOS - Rueckgabewert 0, keine Warnung, keine
    Zeilennummer. Ausgefuehrt wird davon nichts (nm-openvpn-service
    kennt kein `--config` und baut openvpns Befehlszeile aus einer
    geschlossenen Liste), aber der Nutzer erfaehrt nie, dass die Zeile,
    die seinen Verkehr eingegrenzt haette, fehlt. Unser Einleser
    benennt sie, mit Datei und Zeile, und endet mit einem eigenen
    Rueckgabewert.

DER EINE PUNKT, DER NICHT GEMESSEN WERDEN KONNTE
    Der Eigenschaftsname `username` in NetworkManagers vpn.data. Er ist
    im Stringtable von libnm-vpn-plugin-openvpn.so als Endstueck von
    `http-proxy-username` zusammengelegt und dort nicht einzeln
    nachweisbar - dieselbe Falle, die `up` hinter `group` versteckt.
    test_the_username_reaches_networkmanager_and_is_checked_afterwards
    misst deshalb, dass der Befehl NACHSIEHT, statt es anzunehmen.

KEIN ECHTES nmcli, KEIN ECHTES NETZ
    Jeder Aufruf, der NetworkManager beruehren wuerde, laeuft gegen
    einen `runner`, der die Argumentliste aufschreibt und eine
    vorbereitete Antwort zurueckgibt - dieselbe Trennung wie in
    tests/src/test_vpn_wireguard.py. Jede Adresse stammt aus dem
    Dokumentationsbereich (RFC 5737), jeder Name aus `.invalid`, und
    jedes Geheimnis ist ein offensichtliches Literal, das nirgends
    sonst existiert.
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
from src.settings import default_connection as settings_default_connection
from src.vpn import (
    OVPN_CARRIED_EXTRA,
    OVPN_ENABLING,
    OVPN_EXECUTING,
    OVPN_IMPORT_REFUSED,
    UnreadableOpenVpnConfig,
    openvpn_document,
    openvpn_dns,
    openvpn_key_dir,
    openvpn_needs_a_secret,
    openvpn_routes,
    openvpn_secrets_text,
    openvpn_status,
    ovpn_conf_text,
    parse_ovpn,
    store_openvpn_blobs,
    swanctl_config,
    vpn_kind,
)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"


# HIER STAND BIS ZUM 01.09.2026 _user_settings_connection()
#
#     Geloescht mit seinem einzigen Aufrufer, dem Vergleich der beiden
#     Vorgabentabellen - der seit der Zusammenlegung eine Tabelle gegen
#     sich selbst hielt. Die ausfuehrliche Begruendung steht an
#     derselben Stelle in tests/src/test_vpn_wireguard.py.


# WARUM DIESE BLOECKE ZUR LAUFZEIT ENTSTEHEN UND NICHT IM QUELLTEXT
# STEHEN
#
#     tests/packaging/test_recipes.py::
#     test_no_private_key_material_is_in_the_working_tree_outside_the_
#     ignored_directory durchsucht den GANZEN Baum nach den Kopfzeilen
#     der fuenf privaten Schluesselformate. CONTRIBUTING.md begruendet
#     das: "ein privater Schluessel in einem Klon ist ein privater
#     Schluessel in jedem Klon".
#
#     Der Waechter kann nicht unterscheiden, ob ein Schluessel echt ist -
#     und genau das ist seine Staerke. Er soll nicht abwaegen muessen.
#     Also wird er hier nicht aufgeweicht, sondern befolgt: die
#     Kopfzeile steht nirgends als zusammenhaengende Zeichenkette im
#     Quelltext, sie wird aus `BEGIN ` und dem Etikett gefuegt.
#
#     WARUM NICHT EINE ERKENNBAR UNECHTE MARKIERUNG (der naheliegende
#     zweite Weg): weil src/vpn.py::openvpn_key_is_encrypted() auf
#     GENAU diese Marker sieht und der Einleser auf genau diese
#     Blockgrenzen. Ein Test mit erfundenen Kopfzeilen wuerde das
#     Format pruefen, das niemand schickt. Und ohne Block gar nicht
#     auszukommen geht auch nicht - das Einbetten IST der Fall, um den
#     es hier geht.
def _pem(etikett: str, koerper: str) -> str:
    """Ein PEM-Block, gefuegt statt geschrieben."""
    rand = "-" * 5
    return f"{rand}BEGIN {etikett}{rand}\n{koerper}\n{rand}END {etikett}{rand}"


# Die Etiketten einzeln, damit auch sie nicht als Kopfzeile dastehen.
ETIKETT_ZERTIFIKAT = "CERTIFICATE"
ETIKETT_SCHLUESSEL = "PRIVATE KEY"
ETIKETT_STATISCH = "OpenVPN Static key V1"

# Offensichtliche Platzhalter. Kein Byte davon ist ein Schluessel, aber
# jedes ist als solcher geformt - der Einleser soll an der FORM nichts
# zerteilen, und PEM-Bloecke tragen `=` als Fuellzeichen.
CA_PEM = _pem(ETIKETT_ZERTIFIKAT,
              "TESTCAtestCAtestCAtestCAtestCAtestCAtestCAtestCAtestCA==")
CERT_PEM = _pem(ETIKETT_ZERTIFIKAT,
                "TESTCERTtestCERTtestCERTtestCERTtestCERTtestCERT==")
KEY_PEM = _pem(ETIKETT_SCHLUESSEL,
               "TESTKEYtestKEYtestKEYtestKEYtestKEYtestKEYtestKEY==")
TA_KEY = _pem(ETIKETT_STATISCH, "0123456789abcdef0123456789abcdef")

OVPN = f"""# Vom Anbieter heruntergeladen
client
dev tun
proto udp
remote gateway.example.invalid 1194
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
cipher AES-256-GCM
auth SHA256
verb 3
route 203.0.113.0 255.255.255.0
dhcp-option DNS 203.0.113.53
dhcp-option DOMAIN example.invalid
data-ciphers AES-256-GCM:AES-128-GCM
<ca>
{CA_PEM}
</ca>
<cert>
{CERT_PEM}
</cert>
<key>
{KEY_PEM}
</key>
<tls-auth>
{TA_KEY}
</tls-auth>
key-direction 1
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
        self.seen: list[str] = []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        if self.watch is not None and self.watch.exists():
            self.modes.append(stat.S_IMODE(self.watch.stat().st_mode))
            self.seen.append(self.watch.read_text(encoding="utf-8"))
        key = " ".join(argv)
        stdout = next((text for needle, text in self.answers.items()
                       if needle in key), "")
        return subprocess.CompletedProcess(argv, self.returncode,
                                           stdout=stdout, stderr="")

    def flat(self) -> str:
        return "\n".join(" ".join(call) for call in self.calls)


def _document(block: dict, *, name: str = "work") -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "vpn": {"kind": "openvpn", "connection_name": name,
                "dns": {"servers": [], "search_domain": ""},
                "routed_networks": [], "openvpn": block},
    }


# --------------------------------------------------------------------
# 1. Die bestehende IPsec-Konfiguration merkt nichts
# --------------------------------------------------------------------

# Eine Einstellungsdatei, wie sie vor dem 21.08.2026 aussah: kein
# `kind`, kein `wireguard`, kein `openvpn`. Genau das, was auf jeder
# Maschine liegt, die es schon gibt.
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


def test_the_old_configuration_produces_the_very_same_swanctl_file():
    """Der wichtigste Test der Vertraeglichkeit, zum zweiten Mal.

    Am 21.08.2026 hat er `wireguard` als zusaetzlichen Schluessel
    ausgehalten; hier kommt `openvpn` dazu. Beide Male gilt dieselbe
    Zusicherung: ein Dokument von VORHER und dasselbe Dokument MIT den
    neuen Schluesseln muessen zeichengleich dieselbe swanctl-Datei
    ergeben.

    Getragen wird das von drei Eigenschaften, jede an ihrer Stelle
    gemessen: settings.load() mischt keine Vorgaben ein,
    get_user_vpn_setting() faellt je Schluessel zurueck, und vpn_kind()
    antwortet auf ein fehlendes `kind` mit "ipsec".
    """
    vorher = swanctl_config(LEGACY)

    nachher_dokument = json.loads(json.dumps(LEGACY))
    nachher_dokument["vpn"]["kind"] = "ipsec"
    nachher_dokument["vpn"]["wireguard"] = settings_default_connection()["wireguard"]
    nachher_dokument["vpn"]["openvpn"] = settings_default_connection()["openvpn"]
    nachher = swanctl_config(nachher_dokument)

    assert vorher == nachher, (
        "adding the openvpn keys changed the generated swanctl file")
    # Die Gegenprobe: der Vergleich haelt nicht zwei leere Zeichenketten.
    assert "gw.example.invalid" in vorher and len(vorher.splitlines()) > 10


def test_a_settings_file_from_before_the_change_is_still_ipsec():
    assert vpn_kind(LEGACY) == "ipsec"
    assert vpn_kind({}) == "ipsec"


def test_an_unknown_kind_is_not_passed_through():
    """Eine vertippte Bauart darf nicht in eine Verbindung fuehren."""
    assert vpn_kind({"vpn": {"kind": "opnvpn"}}) == "ipsec"
    assert vpn_kind({"vpn": {"kind": "OpenVPN"}}) == "ipsec"
    assert vpn_kind({"vpn": {"kind": "openvpn"}}) == "openvpn"


def test_der_einleser_schreibt_keinen_schluessel_den_die_vorgabe_nicht_kennt():
    """Was `zepos-vpn import` anlegt, muss `zepos-settings set` kennen.

    HIER STAND BIS ZUM 01.09.2026 EIN VERGLEICH EINER TABELLE MIT SICH
    SELBST
        Der Test hiess test_both_default_tables_carry_the_same_openvpn_keys
        und hielt settings.default_connection()["openvpn"] gegen
        user_settings.DEFAULT_CONNECTION["openvpn"]. Seine Begruendung
        war richtig und gilt weiter: "ein Schluessel, der nur in einer
        steht, ist ein Pfad, den die Oberflaeche schreiben kann und das
        Kommandozeilenwerkzeug ablehnt."

        Getragen hat er sie seit der Zusammenlegung nicht mehr.
        DEFAULT_CONNECTION IST seitdem der Aufruf von
        default_connection() - beide Seiten waren dieselbe Tabelle, und
        der Test blieb gruen, gleichgueltig was darin steht. Dieselbe
        Stelle in tests/src/test_vpn_wireguard.py fuehrt die
        ausfuehrliche Begruendung.

        Dass die Befehlszeile jeden Schluessel der Tabelle annimmt,
        misst seit dem 01.09.2026 tests/src/test_vpn_vorgaben.py::
        test_die_befehlszeile_erreicht_jeden_schluessel_der_vorgabe.

    WAS DORT NICHT GEMESSEN WIRD UND DARUM HIER STEHT
        openvpn_document() ist der einzige Schreiber des
        `openvpn`-Abschnitts, der ihn OHNE die Tabelle fuellt: er baut
        ihn aus einer .ovpn-Datei. Traegt er einen Schluessel, den sie
        nicht kennt, lehnt `zepos-settings set vpn.openvpn.<x>` einen
        Pfad ab, den der Einleser gerade angelegt hat. Fehlt ihm einer,
        kommt eine importierte Verbindung unvollstaendig an.

        Verglichen werden SCHLUESSEL und nicht Werte - der Einleser
        traegt ein, was in der Datei stand.
    """
    importiert = openvpn_document(parse_ovpn(OVPN, "anbieter.ovpn"))
    tabelle = settings_default_connection()["openvpn"]

    assert set(importiert) == set(tabelle), (
        f"nur im Einleser: {sorted(set(importiert) - set(tabelle))}; "
        f"nur in der Vorgabe: {sorted(set(tabelle) - set(importiert))}")
    # Die Gegenprobe, damit hier nicht zwei leere Mengen gegeneinander
    # stehen - genau die Art gruener Aussage, die diesen Test ersetzt hat.
    assert "ca_file" in tabelle

    # Unveraendert aus dem alten Test: die Bauart einer nicht
    # eingerichteten Verbindung ist "ipsec" und wird nie geraten.
    assert settings_default_connection()["kind"] == "ipsec"


# --------------------------------------------------------------------
# 2. Der Einleser - benennen, ablehnen, abbrechen
# --------------------------------------------------------------------

def test_the_eighteen_executing_directives_are_all_named():
    """Die Liste ist vollstaendig und keine Zeile davon fehlt.

    Abgezaehlt am 22.08.2026 aus `openvpn --help` und openvpn(8) der
    installierten Fassung 2.7.6. Diese Zusicherung haelt die ZAHL fest,
    damit ein spaeteres Streichen auffaellt - eine Liste, aus der
    jemand `plugin` entfernt, sieht sonst genauso aus wie vorher.
    """
    assert len(OVPN_EXECUTING) == 18, OVPN_EXECUTING
    for name in ("up", "down", "route-up", "ipchange", "client-connect",
                 "learn-address", "tls-verify", "auth-user-pass-verify",
                 "plugin", "script-security", "dns-updown", "iproute",
                 "tls-crypt-v2-verify", "client-crresponse"):
        assert name in OVPN_EXECUTING, f"{name} is not on the refusal list"
    # Und die weiterreichenden: `config` zieht eine zweite Datei herein
    # und mit ihr die ganze Liste darueber.
    for name in ("config", "setenv", "management", "chroot", "daemon"):
        assert name in OVPN_ENABLING, f"{name} is not on the refusal list"


@pytest.mark.parametrize("directive", OVPN_EXECUTING)
def test_every_executing_directive_is_refused_with_its_line_number(directive):
    """Benannt und abgelehnt - nicht still verworfen, nicht ausgefuehrt."""
    text = (f"client\ndev tun\nproto udp\nremote a.invalid 1194\n"
            f"{directive} /tmp/nicht-ausfuehren.sh\n")
    conf = parse_ovpn(text, "anbieter.ovpn")
    assert conf.refused == [(5, directive)], conf.refused


def test_a_file_full_of_hook_lines_reports_every_one_with_its_exit_code(
        tmp_path, capsys, monkeypatch):
    """Der ganze Weg: eine .ovpn voller `up`-Zeilen durch den Befehl.

    Erwartet wird DREIERLEI: die Werte kommen auf der Standardausgabe
    an (die Datei wurde eingelesen), jede abgelehnte Zeile steht mit
    Nummer und Namen auf der Fehlerausgabe, und der Rueckgabewert ist
    3 statt 0 - wer die Ablehnung uebergehen will, muss das aktiv tun.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    quelle = tmp_path / "anbieter.ovpn"
    quelle.write_text(
        "client\ndev tun\nproto udp\nremote a.invalid 1194\n"
        "script-security 2\n"
        "up /tmp/boese-up.sh\n"
        "down /tmp/boese-down.sh\n"
        "route-up /tmp/boese-routeup.sh\n"
        "plugin /tmp/boese.so argument\n"
        f"<ca>\n{CA_PEM}\n</ca>\n", encoding="utf-8")

    rc = vpn.main(["--ovpn-import", str(quelle)])
    assert rc == OVPN_IMPORT_REFUSED == 3

    ausgabe = capsys.readouterr()
    payload = json.loads(ausgabe.out)
    assert [name for _line, name in payload["refused"]] == [
        "script-security", "up", "down", "route-up", "plugin"]
    assert [line for line, _name in payload["refused"]] == [5, 6, 7, 8, 9]
    for stueck in ("anbieter.ovpn:6: up was NOT taken over",
                   "anbieter.ovpn:9: plugin was NOT taken over"):
        assert stueck in ausgabe.err, ausgabe.err
    # Und die Verbindung ist trotzdem entstanden - eine abgelehnte
    # Zeile macht die Datei nicht unbrauchbar.
    assert payload["openvpn"]["remote"] == "a.invalid"


def test_no_executing_directive_ever_comes_back_out():
    """DER WICHTIGSTE TEST DIESER AUFGABE.

    Was hineinging, kommt nicht wieder heraus: die .ovpn, die
    NetworkManager zu sehen bekommt, wird aus UNSEREN Einstellungen
    gebaut, nicht aus der fremden Datei weitergereicht. Geprueft ueber
    ALLE achtzehn ausfuehrenden und alle weiterreichenden Direktiven -
    und zusaetzlich auf `iptables`, weil das der Befehl ist, den solche
    Zeilen in der Praxis tragen.
    """
    zeilen = ["client", "dev tun", "proto udp", "remote a.invalid 1194"]
    for directive in OVPN_EXECUTING + OVPN_ENABLING:
        zeilen.append(f"{directive} /tmp/boese.sh iptables -F")
    zeilen.append(f"<ca>\n{CA_PEM}\n</ca>")
    conf = parse_ovpn("\n".join(zeilen) + "\n", "boese.ovpn")

    assert len(conf.refused) == len(OVPN_EXECUTING) + len(OVPN_ENABLING)
    document = openvpn_document(conf, stored_files={"ca": "work-ca.pem"})
    erzeugt = ovpn_conf_text(document, openvpn_dns(conf), openvpn_routes(conf))

    assert "iptables" not in erzeugt, erzeugt
    assert "boese.sh" not in erzeugt, erzeugt
    for directive in OVPN_EXECUTING + OVPN_ENABLING:
        for zeile in erzeugt.splitlines():
            assert zeile.split(" ")[0] != directive, (
                f"{directive} came back out of the generated file:\n{erzeugt}")


def test_an_unknown_directive_is_refused_with_file_and_line():
    """Abbruch statt halbem Einlesen - mit Datei, Zeile und Namen."""
    with pytest.raises(UnreadableOpenVpnConfig) as fehler:
        parse_ovpn("client\ndev tun\nremote a.invalid\nfrei-erfunden 5\n",
                   "anbieter.ovpn")
    assert "anbieter.ovpn:4" in str(fehler.value)
    assert "frei-erfunden" in str(fehler.value)


def test_the_import_command_ends_with_65_on_an_unknown_directive(
        tmp_path, capsys):
    quelle = tmp_path / "x.ovpn"
    quelle.write_text("client\nfrei-erfunden 5\n", encoding="utf-8")
    assert vpn.main(["--ovpn-import", str(quelle)]) == 65
    assert "x.ovpn:2" in capsys.readouterr().err


def test_an_included_configuration_is_not_followed():
    """`config <datei>` zieht die ganze Liste der achtzehn nach.

    GEMESSEN am 22.08.2026: NetworkManagers eigener Einleser verfolgt
    sie ebenfalls nicht - er verschweigt es nur. Hier wird sie benannt
    abgelehnt, und was in der eingebundenen Datei stand, kommt nirgends
    an.
    """
    conf = parse_ovpn("client\ndev tun\nremote a.invalid\n"
                      "config /tmp/zweite.ovpn\n", "erste.ovpn")
    assert conf.refused == [(4, "config")]
    assert not any(key == "config" for _n, key, _a in conf.directives)


def test_embedded_credentials_are_refused_and_not_written_to_disk():
    """<auth-user-pass> traegt Nutzername und Passwort im Klartext.

    Es abzulegen hiesse, ein Passwort auf die Platte zu schreiben, das
    heute nirgends auf der Platte steht - schlechter als der Zustand
    vorher. Also abgelehnt, mit Zeilennummer und Grund.
    """
    with pytest.raises(UnreadableOpenVpnConfig) as fehler:
        parse_ovpn("client\nremote a.invalid\n"
                   "<auth-user-pass>\nkonto\ngeheim\n</auth-user-pass>\n",
                   "anbieter.ovpn")
    assert "anbieter.ovpn:3" in str(fehler.value)
    assert "clear text" in str(fehler.value)


def test_a_hash_inside_a_value_is_not_a_comment():
    """Kommentare nur in der ERSTEN Spalte.

    GEMESSEN an openvpn(8): `"#" or ";" characters in the first column
    can be used to denote comments`. Anders als wg-quick, wo mitten in
    der Zeile abgeschnitten wird - und wer hier abschneidet, zerteilt
    einen Pfad oder einen Zertifikatsnamen.
    """
    conf = parse_ovpn('client\nremote a.invalid\n'
                      'verify-x509-name "CN=host#1" subject\n'
                      '# eine echte Kommentarzeile\n'
                      '; und noch eine\n', "x.ovpn")
    werte = [args for _n, key, args in conf.directives
             if key == "verify-x509-name"]
    assert werte == [["CN=host#1", "subject"]], werte


def test_a_quoted_path_with_a_space_stays_one_argument():
    """Ein `split()` haette daraus einen Pfad gemacht, den es nicht gibt."""
    conf = parse_ovpn('client\nremote a.invalid\n'
                      'ca "/home/jemand/mein zertifikat.pem"\n', "x.ovpn")
    werte = [args for _n, key, args in conf.directives if key == "ca"]
    assert werte == [["/home/jemand/mein zertifikat.pem"]], werte


def test_an_unterminated_block_is_refused():
    with pytest.raises(UnreadableOpenVpnConfig) as fehler:
        parse_ovpn(f"client\nremote a.invalid\n<ca>\n{CA_PEM}\n", "x.ovpn")
    assert "x.ovpn:3" in str(fehler.value)
    assert "never closed" in str(fehler.value)


def test_a_duplicated_block_is_refused():
    with pytest.raises(UnreadableOpenVpnConfig):
        parse_ovpn(f"client\nremote a.invalid\n"
                   f"<ca>\n{CA_PEM}\n</ca>\n<ca>\n{CA_PEM}\n</ca>\n", "x.ovpn")


def test_a_harmless_but_ineffective_line_is_reported_too():
    """`ignored` ist leiser als `refused`, aber nicht still.

    Der Unterschied ist die Schwere, nicht die Sichtbarkeit: hier
    aendert sich nichts am Verkehr, dort haette etwas ausgefuehrt
    werden koennen. Still verworfen wird nichts - das ist genau der
    Vorwurf, den dieser Einleser gegen NetworkManagers eigenen erhebt.
    """
    conf = parse_ovpn(OVPN, "anbieter.ovpn")
    namen = [name for _line, name in conf.ignored]
    assert "verb" in namen and "nobind" in namen and "resolv-retry" in namen
    assert conf.refused == []


# --------------------------------------------------------------------
# 3. Die Abbildung auf die BESTEHENDEN Reiter
# --------------------------------------------------------------------

def test_routes_and_dns_land_in_the_tabs_that_already_exist():
    """`route` in die Netzliste, `dhcp-option DNS` in den DNS-Reiter.

    Dieselben Reiter, die IPsec und WireGuard benutzen. Ein zweiter
    waere derselbe Reiter zweimal - und `routed_networks` fuehrt CIDR,
    also wird die Maske umgerechnet statt eine vierte Schreibweise
    einzufuehren.
    """
    conf = parse_ovpn(OVPN, "anbieter.ovpn")
    assert openvpn_routes(conf) == ["203.0.113.0/24"]
    assert openvpn_dns(conf) == {"servers": ["203.0.113.53"],
                                 "search_domain": "example.invalid"}


def test_the_settings_section_carries_no_secret(tmp_path, monkeypatch):
    """Kein Zertifikat, kein Schluessel - nur Dateinamen.

    Dieses Dokument liest der Stil-Erzeuger, gibt `zepos-settings` aus
    und fasst der Doktor an. Ein Schluessel darin waere ein Geheimnis in
    vier Programmen.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    conf = parse_ovpn(OVPN, "anbieter.ovpn")
    document = openvpn_document(
        conf, stored_files=store_openvpn_blobs(conf, "work"))
    als_text = json.dumps(document)
    for geheim in (KEY_PEM, CERT_PEM, CA_PEM, TA_KEY,
                   f"BEGIN {ETIKETT_SCHLUESSEL}",
                   f"BEGIN {ETIKETT_ZERTIFIKAT}",
                   f"BEGIN {ETIKETT_STATISCH}"):
        assert geheim not in als_text, "a secret reached the settings document"
    assert document["key_file"] == "work-key.pem"
    assert document["ca_file"] == "work-ca.pem"


def test_the_carried_extras_come_from_an_allowlist():
    """`extra` ist eine ERLAUBNISLISTE und keine Durchreiche."""
    conf = parse_ovpn(OVPN, "anbieter.ovpn")
    document = openvpn_document(conf)
    namen = [entry[0] for entry in document["extra"]]
    assert namen == ["data-ciphers"], namen
    for name in namen:
        assert name in OVPN_CARRIED_EXTRA


# --------------------------------------------------------------------
# 4. Die Geheimnisse auf der Platte
# --------------------------------------------------------------------

def test_a_stored_blob_is_private_from_its_first_byte(tmp_path, monkeypatch):
    """0600 vom ersten Byte, Verzeichnis 0700 - nicht erst nach einem chmod.

    Gemessen mit `umask 000`, weil eine Datei, deren Privatheit an
    einem spaeteren chmod haengt, sonst versehentlich privat entsteht -
    dieselbe Sorgfalt, die tests/src/test_vpn_secrets.py fuer die
    IPsec-Seite aufwendet.

    Und gemessen gegen NetworkManagers eigenen Weg: der packt dieselben
    Bloecke nach $XDG_DATA_HOME/networkmanagement/certificates/ aus, die
    Dateien 0600, das VERZEICHNIS aber 0755 (GEMESSEN am 22.08.2026).
    Die Namen der Dateien verraten damit, welche Verbindungen es gibt.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    alt = os.umask(0o000)
    try:
        conf = parse_ovpn(OVPN, "anbieter.ovpn")
        gespeichert = store_openvpn_blobs(conf, "work")
    finally:
        os.umask(alt)

    verzeichnis = openvpn_key_dir()
    assert stat.S_IMODE(verzeichnis.stat().st_mode) == 0o700
    assert set(gespeichert) == {"ca", "cert", "key", "tls-auth"}
    for name in gespeichert.values():
        pfad = verzeichnis / name
        assert stat.S_IMODE(pfad.stat().st_mode) == 0o600, pfad
    assert KEY_PEM.splitlines()[1] in (verzeichnis / gespeichert["key"]).read_text()


def test_replacing_a_blob_does_not_keep_an_older_wider_mode(
        tmp_path, monkeypatch):
    """Ein einmal zu weit geoeffneter Speicher bleibt nicht zu weit offen."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    verzeichnis = openvpn_key_dir()
    verzeichnis.mkdir(parents=True, exist_ok=True)
    (verzeichnis / "work-ca.pem").write_text("alt\n")
    os.chmod(verzeichnis / "work-ca.pem", 0o644)

    conf = parse_ovpn(f"client\nremote a.invalid\n<ca>\n{CA_PEM}\n</ca>\n",
                      "x.ovpn")
    store_openvpn_blobs(conf, "work")
    assert stat.S_IMODE((verzeichnis / "work-ca.pem").stat().st_mode) == 0o600


def test_a_path_in_the_file_is_not_copied_into_our_directory(
        tmp_path, monkeypatch):
    """Ein Pfad bleibt ein Pfad.

    Wer sein Zertifikat schon irgendwo liegen hat, bekommt keine zweite
    Kopie - ein verdoppeltes Geheimnis ist ein Geheimnis an zwei
    Stellen, und die zweite raeumt niemand auf.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    conf = parse_ovpn("client\nremote a.invalid\nca /etc/ssl/eigenes.pem\n",
                      "x.ovpn")
    document = openvpn_document(conf, stored_files=store_openvpn_blobs(conf, "work"))
    assert document["ca_file"] == "/etc/ssl/eigenes.pem"
    assert "ca /etc/ssl/eigenes.pem" in ovpn_conf_text(document)


# --------------------------------------------------------------------
# 5. NetworkManager - und kein Geheimnis in einer Befehlszeile
# --------------------------------------------------------------------

def test_apply_never_puts_a_secret_in_a_command_line(tmp_path, monkeypatch):
    """Die erzeugte .ovpn geht als PFAD und wird danach geloescht."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("USER", "tester")

    conf = parse_ovpn(OVPN, "anbieter.ovpn")
    block = openvpn_document(conf,
                             stored_files=store_openvpn_blobs(conf, "work"))
    recorder = Recorder()
    recorder.watch = tmp_path / "run" / "zepos-vpn" / "work.ovpn"
    assert vpn._ovpn_apply(_document(block), recorder) == 0

    flach = recorder.flat()
    assert "import type openvpn file" in flach.replace("  ", " ")
    assert recorder.modes and set(recorder.modes) == {0o600}, recorder.modes
    assert not recorder.watch.exists(), "the generated file was left behind"
    for geheim in (KEY_PEM.splitlines()[1], CA_PEM.splitlines()[1]):
        assert geheim not in flach


def test_the_connection_is_written_to_the_user_and_not_to_the_machine(
        tmp_path, monkeypatch):
    """`connection.permissions user:<konto>`, `autoconnect no`.

    Dieselbe Zeile und dieselbe Begruendung wie bei WireGuard: ein
    Konto OHNE wheel faellt damit auf modify.own (allow_active=yes)
    statt auf einen polkit-Dialog, und die Verbindung gehoert diesem
    Konto statt allen Konten der Maschine.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("USER", "tester")
    recorder = Recorder()
    vpn._ovpn_apply(_document({"remote": "a.invalid", "port": 1194}), recorder)
    flach = recorder.flat()
    assert "connection.permissions user:tester" in flach
    assert "connection.autoconnect no" in flach


def test_the_username_reaches_networkmanager_and_is_checked_afterwards(
        tmp_path, monkeypatch):
    """DER TEST, DEN DIESE AUFGABE SCHULDET.

    Der Eigenschaftsname `username` in NetworkManagers vpn.data liess
    sich am 22.08.2026 NICHT direkt messen: er ist im Stringtable von
    libnm-vpn-plugin-openvpn.so als Endstueck von
    `http-proxy-username` zusammengelegt und dort nicht einzeln
    nachweisbar - dieselbe Falle, die `up` hinter `group` versteckt.

    Also wird hier nicht der Name geprueft (das kann nur eine echte
    NM-Instanz), sondern DASS DER BEFEHL NACHSIEHT: er schreibt, liest
    zurueck und scheitert mit einer Meldung, wenn der Wert nicht
    angekommen ist. Ein falscher Name faellt damit beim Speichern auf
    und nicht erst, wenn der Nutzer sich anzumelden versucht.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("USER", "tester")
    block = {"remote": "a.invalid", "port": 1194,
             "connection_type": "password", "username": "konto"}

    # NetworkManager BEHAELT den Wert: der Befehl gelingt.
    gut = Recorder(answers={"vpn.data": "vpn.data:username = konto\n"})
    assert vpn._ovpn_apply(_document(block), gut) == 0
    assert "+vpn.data username=konto" in gut.flat()
    # Der Nutzername ist KEIN Geheimnis und darf als Argument stehen -
    # das Passwort steht in keinem einzigen Aufruf.
    assert "password" not in gut.flat()

    # NetworkManager kennt den Schluessel NICHT: der Befehl scheitert,
    # statt eine Verbindung zurueckzulassen, die nach einem Konto fragt,
    # das sie nicht hat.
    schlecht = Recorder(answers={"vpn.data": "vpn.data:remote = a.invalid\n"})
    assert vpn._ovpn_apply(_document(block), schlecht) == 1


def test_the_password_travels_in_a_file_and_the_file_is_deleted(
        tmp_path, monkeypatch):
    """Nie in argv - und nach dem Aufruf ist sie weg.

    /proc/<pid>/cmdline ist fuer jedes Konto der Maschine lesbar. Die
    IPsec-Seite reicht Nutzername, Passwort und Einmal-Kennwort bis
    heute als Argumente durch; hier wird das nicht wiederholt.
    """
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    recorder = Recorder()
    recorder.watch = tmp_path / "run" / "zepos-vpn" / "work.secrets"

    rc = vpn._ovpn_up(_document({"remote": "a.invalid"}),
                      {"password": "GEHEIM-nur-hier-42",
                       "token": "TOKEN-nur-hier-99"}, recorder)
    assert rc == 0
    flach = recorder.flat()
    assert "GEHEIM-nur-hier-42" not in flach, "the password reached argv"
    assert "TOKEN-nur-hier-99" not in flach, "the one-time code reached argv"
    assert "passwd-file" in flach
    # 0600, WAEHREND nmcli sie lesen wuerde - und danach weg.
    assert recorder.modes == [0o600], recorder.modes
    assert "vpn.secrets.password:GEHEIM-nur-hier-42" in recorder.seen[0]
    assert "vpn.secrets.challenge-response:TOKEN-nur-hier-99" in recorder.seen[0]
    assert not recorder.watch.exists(), "the password file was left behind"


def test_the_one_time_code_is_not_glued_onto_the_password():
    """Zwei Geheimnisse, zwei Zeilen - geraten wird nicht.

    Die IPsec-Seite haengt Token an Passwort (`FULL_SECRET`), weil
    XAuth es so verlangt. OpenVPN hat dafuer die
    Rueckfrage-Antwort-Schiene, und der Anmeldedialog des Zusatzpakets
    nennt das Geheimnis `challenge-response` (GEMESSEN am 22.08.2026
    im --external-ui-mode). Ein falsch geratenes Passwort ist bei einem
    Anbieter mit Sperrzaehler teurer als eine leere Zeile.
    """
    text = openvpn_secrets_text(password="pw", token="otp")
    assert "vpn.secrets.password:pw\n" in text
    assert "vpn.secrets.challenge-response:otp" in text
    assert "pwotp" not in text


def test_a_certificate_only_connection_hands_over_no_secret_file(
        tmp_path, monkeypatch):
    """Ohne Geheimnis kein passwd-file - und genau das ist der Fall,
    in dem die Verbindung unbeaufsichtigt zurueckkommt."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    recorder = Recorder()
    assert vpn._ovpn_up(_document({"remote": "a.invalid",
                                   "connection_type": "tls"}), {}, recorder) == 0
    assert "passwd-file" not in recorder.flat()
    assert recorder.calls == [["nmcli", "connection", "up", "work"]]


# --------------------------------------------------------------------
# 6. Der unbeaufsichtigte Wiederaufbau - beide Faelle, gemessen
# --------------------------------------------------------------------

def test_only_a_certificate_connection_comes_back_on_its_own(
        tmp_path, monkeypatch):
    """GEMESSEN am 22.08.2026 an NetworkManagers eigenem Einleser.

    Vier .ovpn-Dateien wurden ihm vorgelegt: nur Zertifikate,
    Zertifikate mit verschluesseltem Schluessel, nur Anmeldung, beides.
    Ergebnis: `auth-user-pass` ergibt `password-flags = 1`
    (agentengehalten, NICHT gespeichert), eine reine Zertifikatsdatei
    gar keine Geheimnisflagge. Dazu erfragt nm-openvpn-service
    `cert-pass`, wenn der private Schluessel verschluesselt ist - seine
    Zeichenkettentabelle fuehrt dafuer eigens
    `-----BEGIN ENCRYPTED PRIVATE KEY-----` und `Proc-Type: 4,ENCRYPTED`.

    Folge, und sie steht auch im Fenster: eine reine
    Zertifikatsverbindung kommt nach einem Netzwechsel oder dem
    Aufwachen von selbst zurueck, eine mit Anmeldung nicht.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    verzeichnis = openvpn_key_dir()
    verzeichnis.mkdir(parents=True, exist_ok=True)
    (verzeichnis / "klar.pem").write_text(KEY_PEM, encoding="utf-8")
    (verzeichnis / "verschluesselt.pem").write_text(
        _pem(f"ENCRYPTED {ETIKETT_SCHLUESSEL}", "AAAA") + "\n",
        encoding="utf-8")

    nur_zertifikate = {"connection_type": "tls", "key_file": "klar.pem"}
    mit_passphrase = {"connection_type": "tls",
                      "key_file": "verschluesselt.pem"}
    mit_anmeldung = {"connection_type": "password", "key_file": ""}
    beides = {"connection_type": "password-tls", "key_file": "klar.pem"}

    assert openvpn_needs_a_secret(nur_zertifikate) is False
    assert openvpn_needs_a_secret(mit_passphrase) is True
    assert openvpn_needs_a_secret(mit_anmeldung) is True
    assert openvpn_needs_a_secret(beides) is True


def test_the_unattended_question_has_exactly_one_answer(
        tmp_path, monkeypatch, capsys):
    """`--ovpn-unattended` sagt ein Wort, wie `--status` eines sagt.

    Der Aufrufer soll die Antwort nicht selbst aus `connection_type`
    und dem Kopf einer Schluesseldatei herleiten muessen: zwei
    Herleitungen fuer eine Auskunft sind zwei Stellen, an denen etwas
    Verschiedenes stehen kann.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(
        vpn, "_settings_document",
        lambda: _document({"connection_type": "password", "key_file": ""}))
    assert vpn.main(["--ovpn-unattended"]) == 0
    assert capsys.readouterr().out.strip() == "no"

    monkeypatch.setattr(
        vpn, "_settings_document",
        lambda: _document({"connection_type": "tls", "key_file": ""}))
    assert vpn.main(["--ovpn-unattended"]) == 0
    assert capsys.readouterr().out.strip() == "yes"


def test_the_window_says_it_where_the_kind_is_chosen():
    """Der Satz steht in der Oberflaeche und nicht nur im Bericht.

    Eine Verbindung, die nach dem Aufwachen weg ist und niemand weiss
    warum, kostet mehr Vertrauen als ein Hinweis beim Einrichten.
    """
    text = (SRC / "templates" / "ags-vpn-settings.template").read_text(
        encoding="utf-8")
    code = "\n".join(zeile for zeile in text.splitlines()
                     if not zeile.strip().startswith("//"))
    assert '"--ovpn-unattended"' in code, (
        "the dialog never asks whether this connection can come back on "
        "its own")
    for satz in ("comes back on its own after a network change or resume",
                 "it stays down until you connect again"):
        assert satz in code, f"the window does not say: {satz}"


# --------------------------------------------------------------------
# 7. Der Vertrag nach aussen, und die Rechte
# --------------------------------------------------------------------

@pytest.mark.parametrize("report,erwartet", [
    ("GENERAL.STATE:activated\nIP4.ADDRESS[1]:203.0.113.9/24\n",
     ("connected", "203.0.113.9")),
    ("GENERAL.STATE:activated\n", ("stale", "")),
    ("GENERAL.STATE:deactivated\n", ("disconnected", "")),
    ("", ("disconnected", "")),
])
def test_the_three_words_mean_the_same_for_openvpn(report, erwartet):
    """Vier Leser teilen sich eine Zeile Text, und keiner darf wissen
    muessen, welche Bauart eingestellt ist."""
    recorder = Recorder(answers={"connection show": report})
    assert openvpn_status("work", recorder) == erwartet


def test_a_connection_without_a_name_is_not_asked_about():
    recorder = Recorder()
    assert openvpn_status("", recorder) == ("disconnected", "")
    assert recorder.calls == []


def test_the_status_command_picks_the_openvpn_half(monkeypatch, capsys):
    """`--status` entscheidet nach `vpn.kind` - und im Zweifel IPsec."""
    monkeypatch.setattr(vpn, "_settings_document",
                        lambda: _document({"remote": "a.invalid"}))
    monkeypatch.setattr(vpn, "openvpn_status",
                        lambda name, *a, **k: ("connected", "203.0.113.9"))
    monkeypatch.setattr(vpn, "tunnel_status",
                        lambda *a, **k: ("disconnected", ""))
    assert vpn.main(["--status"]) == 0
    assert capsys.readouterr().out.strip() == "connected 203.0.113.9"


def test_openvpn_needs_no_new_privileged_command():
    """KEINE neue Zeile in /etc/sudoers.d/zepos.

    IPsec braucht dort sieben Cmnd_Alias-Bloecke. OpenVPN laeuft ueber
    NetworkManager und polkit und braucht keinen - GEMESSEN am
    22.08.2026 mit pkcheck: settings.modify.own rc=0,
    settings.modify.system rc=0, network-control rc=0, und als
    Gegenprobe settings.modify.hostname rc=2 ("requires
    authentication"), obwohl es dieselbe auth_admin_keep-Vorgabe traegt.

    Und wenn hier je `openvpn` als privilegierter Befehl auftaucht, ist
    das die Regel, vor der der Kopf von
    zepos-privileges-config.template warnt: eine .ovpn kann `up`,
    `plugin` und `script-security` tragen, und ein `openvpn --config *`
    unter sudo waere beliebiger Root-Code aus einer heruntergeladenen
    Datei.
    """
    text = (SRC / "system" / "zepos-privileges-config.template").read_text(
        encoding="utf-8")
    for verboten in ("openvpn", "/usr/sbin/openvpn", "nm-openvpn"):
        assert verboten not in text, f"{verboten} became a privileged command"


def test_the_dialog_offers_openvpn_as_a_fourth_choice():
    text = (SRC / "templates" / "ags-vpn-settings.template").read_text(
        encoding="utf-8")
    code = "\n".join(zeile for zeile in text.splitlines()
                     if not zeile.strip().startswith("//"))
    for label in ('_("IPsec (IKEv1)")', '_("IPsec (IKEv2)")',
                  '_("WireGuard")', '_("OpenVPN")'):
        assert label in code, f"{label} is not on offer"


def test_the_page_never_disconnects_openvpn_with_the_ipsec_script():
    """vpn-control.sh raeumt swanctl-Kinder, Routen und xfrm-Policies ab.

    Auf einem NetworkManager-Profil gibt es nichts davon - der Aufruf
    waere im besten Fall wirkungslos und im schlechteren ein Eingriff in
    Routen, die jemand anders gesetzt hat.
    """
    seite = (SRC / "templates" / "ags-vpn.template").read_text(encoding="utf-8")
    code = "\n".join(zeile for zeile in seite.splitlines()
                     if not zeile.strip().startswith("//"))
    assert '"--ovpn-down"' in code and '"--ovpn-up"' in code
    assert 'vpnSettings.kind === "openvpn"' in code
    # Genau EIN Aufruf des IPsec-Steuerskripts, und der steht im
    # letzten else-Zweig der Weiche.
    assert code.count("SCRIPTS.vpnControl,") == 1


def test_the_page_hands_the_credentials_over_stdin_and_not_as_arguments():
    """Die Seite darf das Passwort nicht in eine Argumentliste legen.

    Gemessen an der Vorlage, weil dieser Fehler genau dort entsteht:
    daneben steht der IPsec-Zweig, der es bis heute tut.
    """
    seite = (SRC / "templates" / "ags-vpn.template").read_text(encoding="utf-8")
    code = "\n".join(zeile for zeile in seite.splitlines()
                     if not zeile.strip().startswith("//"))
    assert "Gio.SubprocessFlags.STDIN_PIPE" in code
    assert "communicate_utf8(payload" in code
    # Und der Aufruf selbst traegt nichts ausser dem Unterbefehl.
    assert '[...VPN_TOOL, "--ovpn-up"]' in code
