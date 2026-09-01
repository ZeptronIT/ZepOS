# SPDX-License-Identifier: GPL-3.0-or-later
"""Ein Volltunnel wird SICHTBAR - und sonst aendert sich nichts.

GEFRAGT am 22.08.2026: "und alle neuen vpn arten wireguard und openvpn
folgen dem split tunneling wie ipsec oder? kein full routing?? ich meine
wireguard war standard so"

GEMESSEN am selben Tag, BEVOR hier etwas gebaut wurde: `0.0.0.0/0` kam in
src/vpn.py genau einmal vor, in einem Kommentar; in
src/templates/ags-vpn-settings.template kam es ueberhaupt nicht vor. Es
gab weder eine Erkennung noch einen Hinweis. Wer eine Anbieterdatei
anheftete, schickte seinen gesamten Verkehr durch den Tunnel und merkte
es an der Geschwindigkeit.

NACHGESETZT, und das ist die Grenze dieser Datei: "nein, ich will das
jetzt nicht umstellen - ich will es konfigurierbar haben". Also KEINE
geaenderte Vorgabe, KEIN Einleser, der aus einem Volltunnel still einen
Teiltunnel macht - ein solcher Einleser waere schlimmer als gar keine
Warnung, weil der Nutzer sich dann geschuetzt glaubte und es nicht waere.

DIE VIER FRAGEN, DIE HIER BEANTWORTET WERDEN
  1. Wird ein Volltunnel gefunden - auch in den Schreibweisen, die nicht
     `0.0.0.0/0` heissen (zwei Haelften, vier Viertel, ::/0)?
  2. Gilt DIESELBE Regel fuer alle drei Bauarten?
  3. Bleibt alles Erzeugte ZEICHENGLEICH? Das ist der Beweis, dass
     nichts umgestellt wurde: gleiche Einstellungen, gleiche Datei.
  4. Rechnet das Fenster dasselbe wie src/vpn.py? Die Rechnung steht
     zweimal da (der Hinweis muss bei jedem Tastendruck stimmen, und ein
     Kindprozess je Tastendruck waere ein Kindprozess je Tastendruck) -
     also werden die beiden Fassungen gegeneinander gemessen und nicht
     nebeneinander gehofft.
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[2]
SRC = WURZEL / "src"
VORLAGE = SRC / "templates" / "ags-vpn-settings.template"

sys.path.insert(0, str(SRC))
import vpn  # noqa: E402
from settings import UnusableSettings  # noqa: E402

# Schluessel in der FORM, die WireGuard benutzt (32 Byte Base64, also mit
# `=` am Ende), zur Laufzeit gebaut und nicht abgeschrieben: eine
# Zeichenkette in Schluesselform im Quelltext ist genau das, wonach der
# Waechter sucht, und sie waere hier auch ohne ihn ueberfluessig.
SCHLUESSEL = base64.b64encode(bytes(range(0, 32))).decode()
OEFFENTLICH = base64.b64encode(bytes(range(32, 64))).decode()
GETEILT = base64.b64encode(bytes(range(64, 96))).decode()


# --------------------------------------------------------------------
# 1. Die Rechnung
# --------------------------------------------------------------------
#
# Die Tabelle steht EINMAL da und wird zweimal benutzt: hier gegen
# src/vpn.py und weiter unten gegen den Zwilling im Fenster. Zwei
# Tabellen waeren zwei, die auseinanderlaufen - und die Frage der ganzen
# Datei ist, ob zwei Fassungen dasselbe sagen.
FAELLE: list[tuple[list[str], list[str]]] = [
    # Die offensichtliche Schreibweise, beide Familien.
    (["0.0.0.0/0"], ["ipv4"]),
    (["::/0"], ["ipv6"]),
    (["0.0.0.0/0", "::/0"], ["ipv4", "ipv6"]),
    # DIE ZWEI HAELFTEN. openvpn(8) nennt sie unter der Fahne `def1`
    # ("override the default gateway by using 0.0.0.0/1 and 128.0.0.0/1
    # rather than 0.0.0.0/0"), und WireGuard-Anbieter schreiben sie aus
    # demselben Grund. Ein Zeichenkettenvergleich sieht davon nichts.
    (["0.0.0.0/1", "128.0.0.0/1"], ["ipv4"]),
    # Auch in der anderen Reihenfolge, und auch in vier Stuecken.
    (["128.0.0.0/1", "0.0.0.0/1"], ["ipv4"]),
    (["0.0.0.0/2", "64.0.0.0/2", "128.0.0.0/1"], ["ipv4"]),
    (["::/1", "8000::/1"], ["ipv6"]),
    # EINE Haelfte allein ist keiner - die andere Haelfte geht direkt.
    (["0.0.0.0/1"], []),
    (["128.0.0.0/1"], []),
    # Ein echter Teiltunnel. Der Normalfall, und er bekommt nichts.
    (["10.0.0.0/8", "192.168.0.0/16"], []),
    (["10.0.0.0/8", "::/0"], ["ipv6"]),
    # Die leere Liste. Kein Tunnel, kein Hinweis.
    ([], []),
    # Wirtsbits sind kein anderes Netz (wie strict=False).
    (["10.1.2.3/8"], []),
    (["0.0.0.1/0"], ["ipv4"]),
    # Was kein Netz ist, deckt keines ab - und bringt die Rechnung nicht
    # aus dem Tritt. Es zu MELDEN ist Sache des Einlesers, der Datei und
    # Zeilennummer vor sich hat.
    (["quatsch", "0.0.0.0/0"], ["ipv4"]),
    (["quatsch"], []),
    (["256.0.0.0/0"], []),
    (["0.0.0.0/33"], []),
]


@pytest.mark.parametrize("netze,erwartet", FAELLE)
def test_die_abdeckung_wird_gerechnet_und_nicht_verglichen(netze, erwartet):
    assert vpn.full_tunnel_families(netze) == erwartet, netze


def test_eine_zeichenkette_statt_einer_liste_wird_benannt():
    """`"routed_networks": "0.0.0.0/0"` ist der wahrscheinlichste
    Hand-Edit dieser Datei. Zeichenweise durchlaufen ergaebe elf
    Bruchstuecke und keinen Volltunnel - also faellt es durch
    nonblank_entries(), wie ueberall sonst in diesem Modul auch."""
    with pytest.raises(UnusableSettings) as fehler:
        vpn.full_tunnel_families("0.0.0.0/0", setting="vpn.routed_networks")
    assert "vpn.routed_networks" in str(fehler.value)


# --------------------------------------------------------------------
# 2. Eine Regel fuer alle drei Bauarten
# --------------------------------------------------------------------

def test_ipsec_meldet_den_volltunnel_aus_der_netzliste():
    """Ein IPsec-Teiltunnel ist eine Gewohnheit dieses Projekts und
    keine Eigenschaft von IPsec: `routed_networks` kann alles
    enthalten."""
    document = {"vpn": {"routed_networks": ["0.0.0.0/1", "128.0.0.0/1"]}}
    assert vpn.settings_full_tunnel(document) == ["ipv4"]


def test_ipsec_mit_firmennetzen_meldet_nichts():
    document = {"vpn": {"routed_networks": ["10.0.0.0/8"]}}
    assert vpn.settings_full_tunnel(document) == []


def test_wireguard_rechnet_ueber_ALLE_gegenstellen():
    """In die Routentabelle kommt die Vereinigung der AllowedIPs. Zwei
    Gegenstellen mit je einer Haelfte sind zusammen ein Volltunnel, den
    keine von beiden allein waere - und genau den saehe eine Rechnung je
    Gegenstelle nicht."""
    document = {"vpn": {"kind": "wireguard", "wireguard": {"peers": [
        {"allowed_ips": ["0.0.0.0/1"]},
        {"allowed_ips": ["128.0.0.0/1"]},
    ]}}}
    assert vpn.settings_full_tunnel(document) == ["ipv4"]


def test_wireguard_mit_dem_ueblichen_anbietersatz():
    document = {"vpn": {"kind": "wireguard", "wireguard": {"peers": [
        {"allowed_ips": ["0.0.0.0/0", "::/0"]}]}}}
    assert vpn.settings_full_tunnel(document) == ["ipv4", "ipv6"]


def test_openvpn_meldet_den_volltunnel_aus_der_netzliste():
    document = {"vpn": {"kind": "openvpn", "openvpn": {},
                        "routed_networks": ["0.0.0.0/0"]}}
    assert vpn.settings_full_tunnel(document) == ["ipv4"]


def test_openvpn_meldet_ihn_auch_aus_redirect_gateway():
    """Der zweite Weg, und der haeufigere: die Netzliste sagt nichts,
    `redirect-gateway` sagt alles. Wer nur die Liste liest, meldet bei
    der Haelfte der Anbieter nichts."""
    document = {"vpn": {"kind": "openvpn", "routed_networks": [],
                        "openvpn": {"extra": [["redirect-gateway", "def1"]]}}}
    assert vpn.settings_full_tunnel(document) == ["ipv4"]


@pytest.mark.parametrize("fahnen,erwartet", [
    ([], ["ipv4"]),
    (["def1"], ["ipv4"]),
    (["def1", "bypass-dhcp", "bypass-dns"], ["ipv4"]),
    (["ipv6"], ["ipv4", "ipv6"]),
    (["ipv6", "!ipv4"], ["ipv6"]),
    (["!ipv4"], []),
])
def test_die_fahnen_von_redirect_gateway(fahnen, erwartet):
    """ABGELESEN an openvpn(8): nur `ipv6` und `!ipv4` aendern etwas am
    OB. local, autolocal, def1, bypass-dhcp, bypass-dns und block-local
    aendern das WIE."""
    assert vpn.openvpn_redirect_families(
        [["redirect-gateway", *fahnen]]) == erwartet


def test_redirect_private_ist_kein_volltunnel():
    """openvpn(8) woertlich: "Like --redirect-gateway, but omit actually
    changing the default gateway. Useful when pushing private subnets."
    Es umzudeuten hiesse, genau die Datei zu bewarnen, die einen
    Teiltunnel beschreibt - und ein Hinweis, der auch bei harmlosen
    Dateien kommt, ist nach dem dritten Mal keiner mehr."""
    assert vpn.openvpn_redirect_families([["redirect-private", "def1"]]) == []


def test_eine_unbekannte_bauart_antwortet_wie_ipsec():
    """Dieselbe Vorsicht wie vpn_kind(): eine vertippte Bauart darf
    nicht in eine andere Antwort fuehren als die, die es vorher gab."""
    document = {"vpn": {"kind": "vertippt", "routed_networks": ["0.0.0.0/0"]}}
    assert vpn.settings_full_tunnel(document) == ["ipv4"]


def test_ohne_einstellungen_wird_nichts_behauptet():
    assert vpn.settings_full_tunnel({}) == []
    assert vpn.settings_full_tunnel(None) == []


# --------------------------------------------------------------------
# 3. Der Befehl - und der Umschlag des Einlesers
# --------------------------------------------------------------------

def test_der_befehl_nennt_die_familien(monkeypatch, capsys):
    monkeypatch.setattr(vpn, "_settings_document", lambda: {"vpn": {
        "kind": "wireguard",
        "wireguard": {"peers": [{"allowed_ips": ["0.0.0.0/0", "::/0"]}]}}})
    assert vpn.main(["--full-tunnel"]) == 0
    assert capsys.readouterr().out.strip() == "ipv4 ipv6"


def test_der_befehl_schweigt_beim_teiltunnel(monkeypatch, capsys):
    monkeypatch.setattr(vpn, "_settings_document",
                        lambda: {"vpn": {"routed_networks": ["10.0.0.0/8"]}})
    assert vpn.main(["--full-tunnel"]) == 0
    assert capsys.readouterr().out.strip() == ""


def _wg_datei() -> str:
    """Eine Anbieterdatei, wie sie tatsaechlich aussieht: alles hinein."""
    return (
        "[Interface]\n"
        f"PrivateKey = {SCHLUESSEL}\n"
        "Address = 203.0.113.9/32\n"
        "\n"
        "[Peer]\n"
        f"PublicKey = {OEFFENTLICH}\n"
        "AllowedIPs = 0.0.0.0/0, ::/0\n"
        "Endpoint = gateway.example.invalid:51820\n"
    )


def test_der_wg_einleser_laesst_die_netze_wort_fuer_wort_stehen(
        tmp_path, monkeypatch, capsys):
    """DER KERN DES AUFTRAGS. Was in der Datei stand, steht nachher in
    den Einstellungen - unveraendert, ungekuerzt, ungefiltert. Gemeldet
    wird es, geaendert wird es nicht."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(vpn, "_settings_document", lambda: {})
    monkeypatch.setattr(vpn, "public_wireguard_key", lambda key: OEFFENTLICH)
    quelle = tmp_path / "anbieter.conf"
    quelle.write_text(_wg_datei(), encoding="utf-8")

    assert vpn.main(["--wg-import", str(quelle)]) == 0
    umschlag = json.loads(capsys.readouterr().out)
    assert umschlag["wireguard"]["peers"][0]["allowed_ips"] == \
        ["0.0.0.0/0", "::/0"]
    assert umschlag["full_tunnel"] == ["ipv4", "ipv6"]


def test_der_ovpn_umschlag_traegt_beide_wege(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(vpn, "_settings_document", lambda: {})
    quelle = tmp_path / "anbieter.ovpn"
    quelle.write_text("client\ndev tun\nremote gateway.example.invalid 1194\n"
                      "redirect-gateway def1\n", encoding="utf-8")
    assert vpn.main(["--ovpn-import", str(quelle)]) == 0
    umschlag = json.loads(capsys.readouterr().out)
    # Die Netzliste bleibt leer - `redirect-gateway` ist keine Route und
    # wird auch nicht in eine umgedeutet.
    assert umschlag["routed_networks"] == []
    assert umschlag["openvpn"]["extra"] == [["redirect-gateway", "def1"]]
    assert umschlag["full_tunnel"] == ["ipv4"]


# --------------------------------------------------------------------
# 4. Zeichengleich - der Beweis, dass nichts umgestellt wurde
# --------------------------------------------------------------------
#
# Fuer ALLE DREI Bauarten und nicht nur fuer IPsec. Die erwarteten Texte
# stehen woertlich da statt aus derselben Funktion zu kommen, die sie
# erzeugt: eine Erwartung, die sich mitaendert, ist keine.

def test_die_erzeugte_wg_conf_ist_zeichengleich():
    document = {
        "addresses": ["203.0.113.9/32"], "listen_port": 51820, "mtu": 1380,
        "private_key_file": "work.key", "public_key": OEFFENTLICH,
        "peers": [{"public_key": OEFFENTLICH,
                   "endpoint": "gateway.example.invalid:51820",
                   "allowed_ips": ["0.0.0.0/0", "::/0"], "keepalive": 25,
                   "preshared_key_file": "work-peer1.psk"}],
    }
    erwartet = (
        "[Interface]\n"
        f"PrivateKey = {SCHLUESSEL}\n"
        "Address = 203.0.113.9/32\n"
        "ListenPort = 51820\n"
        "MTU = 1380\n"
        "DNS = 203.0.113.53, example.invalid\n"
        "\n"
        "[Peer]\n"
        f"PublicKey = {OEFFENTLICH}\n"
        f"PresharedKey = {GETEILT}\n"
        "AllowedIPs = 0.0.0.0/0, ::/0\n"
        "Endpoint = gateway.example.invalid:51820\n"
        "PersistentKeepalive = 25\n"
    )
    assert vpn.wireguard_conf_text(
        document, SCHLUESSEL,
        {"servers": ["203.0.113.53"], "search_domain": "example.invalid"},
        [GETEILT]) == erwartet


def test_die_erzeugte_ovpn_ist_zeichengleich():
    document = {
        "remote": "gateway.example.invalid", "port": 1194, "proto": "udp",
        "dev": "tun", "dev_type": "", "connection_type": "password-tls",
        "username": "konto", "remote_cert_tls": "server",
        "cipher": "AES-256-GCM", "auth": "SHA256", "comp_lzo": "",
        "tunnel_mtu": 1400, "reneg_seconds": 0, "ta_dir": "1",
        "ca_file": "work-ca.pem", "cert_file": "work-cert.pem",
        "key_file": "work-key.pem", "tls_auth_file": "work-tls-auth.key",
        "tls_crypt_file": "", "pkcs12_file": "",
        "extra": [["redirect-gateway", "def1"], ["tls-version-min", "1.2"]],
    }
    erwartet = (
        "client\n"
        "dev tun\n"
        "proto udp\n"
        "remote gateway.example.invalid 1194\n"
        "ca /heim/.config/openvpn/work-ca.pem\n"
        "cert /heim/.config/openvpn/work-cert.pem\n"
        "key /heim/.config/openvpn/work-key.pem\n"
        "tls-auth /heim/.config/openvpn/work-tls-auth.key 1\n"
        "auth-user-pass\n"
        "remote-cert-tls server\n"
        "cipher AES-256-GCM\n"
        "auth SHA256\n"
        "tun-mtu 1400\n"
        "redirect-gateway def1\n"
        "tls-version-min 1.2\n"
        "route 0.0.0.0 0.0.0.0\n"
        "dhcp-option DNS 203.0.113.53\n"
        "dhcp-option DOMAIN example.invalid\n"
    )
    assert vpn.ovpn_conf_text(
        document,
        {"servers": ["203.0.113.53"], "search_domain": "example.invalid"},
        ["0.0.0.0/0"], Path("/heim/.config/openvpn")) == erwartet


def test_die_erzeugte_swanctl_conf_ist_zeichengleich():
    erwartet = """connections {
    work {
        version = 2
        proposals = aes256-sha256-ecp521
        dpd_delay = 30s
        dpd_timeout = 120s
        encap = yes
        mobike = no
        rekey_time = 86400s
        remote {
            auth = psk
            id = gateway.example.invalid
        }
        remote_addrs = gateway.example.invalid
        vips = 0.0.0.0
        children {
            work-1 {
                remote_ts = 0.0.0.0/0
                rekey_time = 43200s
                life_time = 43200s
                dpd_action = restart
                esp_proposals = aes256-sha256-ecp521
                mode = tunnel
                replay_window = 32
                start_action = trap
                policies = yes
            }
        }
    }
}
"""
    assert vpn.swanctl_config({"vpn": {
        "server": "gateway.example.invalid", "connection_name": "work",
        "routed_networks": ["0.0.0.0/0"]}}) == erwartet


# --------------------------------------------------------------------
# 5. Der Zwilling im Fenster
# --------------------------------------------------------------------

MARKE_AUF = "// >>> VOLLTUNNEL-RECHNUNG"
MARKE_ZU = "// <<< VOLLTUNNEL-RECHNUNG"


def _rechenblock() -> str:
    text = VORLAGE.read_text(encoding="utf-8")
    assert MARKE_AUF in text and MARKE_ZU in text, (
        "die Marken um die Volltunnel-Rechnung fehlen in "
        f"{VORLAGE.name} - ohne sie kann niemand mehr nachmessen, ob "
        "Fenster und src/vpn.py dasselbe rechnen")
    return text[text.index(MARKE_AUF):text.index(MARKE_ZU)]


def test_der_rechenblock_traegt_keinen_platzhalter():
    """Er wird ohne den Erzeuger uebersetzt (siehe unten). Ein
    {{STYLE_*}} darin liesse `ags bundle` scheitern - und der einzige
    Test, der die zwei Fassungen gegeneinander haelt, waere weg."""
    block = _rechenblock()
    assert "{{" not in block, block


@pytest.mark.allow_subprocess
def test_das_fenster_rechnet_dasselbe_wie_python(tmp_path):
    """DIE MESSUNG, DIE DIE KOPIE ERTRAEGLICH MACHT.

    Die Rechnung steht zweimal da, weil der Hinweis bei jedem
    Tastendruck stimmen muss und ein Kindprozess je Tastendruck ein
    Kindprozess je Tastendruck waere. Also wird der Block aus der
    Vorlage geschnitten, mit `ags bundle` uebersetzt und unter gjs ueber
    DIESELBE Tabelle geschickt, die oben src/vpn.py geprueft hat.

    `ags bundle -g 4` schreibt keine .js, sondern eine Bash-Huelle, die
    ihre eingebettete .js nach $XDG_RUNTIME_DIR auspackt und dort mit
    gjs startet - deshalb `bash` und deshalb ein eigenes
    XDG_RUNTIME_DIR unter tmp_path.
    """
    if shutil.which("ags") is None:
        pytest.skip("ags fehlt; es kommt mit dem Paket aylurs-gtk-shell")

    kind = tmp_path / "child.tsx"
    kind.write_text(_rechenblock() + (
        "\nconst faelle: string[][] = JSON.parse(ARGV[0])\n"
        "print(JSON.stringify("
        "faelle.map((werte) => fullTunnelFamilies(werte))))\n"),
        encoding="utf-8")

    buendel = tmp_path / "child.js"
    gebaut = subprocess.run(
        ["ags", "bundle", str(kind), str(buendel), "-g", "4"],
        capture_output=True, text=True, timeout=300, cwd=str(tmp_path))
    assert gebaut.returncode == 0, (
        "`ags bundle` hat die Volltunnel-Rechnung nicht uebersetzt:\n"
        + gebaut.stdout + gebaut.stderr)

    # OHNE Leerzeichen: die Bash-Huelle reicht ihre Argumente als `$@`
    # ohne Anfuehrungszeichen weiter, ein `, ` im JSON wuerde also
    # zerteilt und gjs bekaeme ein halbes Dokument.
    argument = json.dumps([netze for netze, _ in FAELLE],
                          separators=(",", ":"))
    lauf = subprocess.run(
        ["bash", str(buendel), argument],
        capture_output=True, text=True, timeout=120,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path),
             "XDG_RUNTIME_DIR": str(tmp_path)})
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr
    gemessen = json.loads(lauf.stdout.strip().splitlines()[-1])

    erwartet = [erwarteter for _, erwarteter in FAELLE]
    abweichungen = [
        f"{netze!r}: Fenster {ist!r}, src/vpn.py {soll!r}"
        for (netze, soll), ist in zip(FAELLE, gemessen) if ist != soll]
    assert abweichungen == [], (
        "Fenster und src/vpn.py rechnen verschieden:\n  "
        + "\n  ".join(abweichungen))
    assert gemessen == erwartet


# --------------------------------------------------------------------
# 6. Der Hinweis haengt dort, wo der Nutzer die Netze sieht
# --------------------------------------------------------------------
#
# Gelesen wird die Vorlage als Text, aus demselben Grund wie in
# tests/src/test_kit_nesting.py: sie ist TypeScript-AEHNLICH und wird
# erst NACH der Platzhalter-Ersetzung uebersetzt, ein echter Parser
# haette {{STYLE_*}} zu verdauen.

def test_alle_drei_netzlisten_bekommen_den_mitlaufenden_hinweis():
    """Drei Listen, drei Hinweise - und keine vierte Bauart, die
    vergessen wurde."""
    text = VORLAGE.read_text(encoding="utf-8")
    assert text.count("fullTunnelNote(") >= 4, (
        "der Hinweis haengt nicht an allen Netzlisten: er gehoert an die "
        "IPsec-Liste (Phase 2), an die AllowedIPs jeder WireGuard-"
        "Gegenstelle und an die OpenVPN-Netzliste")
    assert "wgFullTunnel()" in text
    assert "ovpnRedirectFamilies()" in text


def test_der_hinweis_wird_nach_jeder_aenderung_neu_erfragt():
    """Ein Hinweis, der nur beim Einlesen einmal aufblitzt, beschreibt
    einen Zustand von damals. refreshNote() haengt deshalb am
    `changed`-Signal jeder Zeile UND am Neuaufbau der Liste."""
    text = VORLAGE.read_text(encoding="utf-8")
    assert text.count("refreshNote()") >= 3, text.count("refreshNote()")


def test_die_openvpn_bauart_zeigt_ihre_netzliste_ueberhaupt():
    """Sie wurde beim Einlesen gefuellt und beim Verbinden gelesen -
    gezeigt wurde sie in keinem der vier Reiter. Der Nutzer konnte also
    nicht sehen, was durch den Tunnel geht, und nichts daran aendern."""
    text = VORLAGE.read_text(encoding="utf-8")
    anfang = text.index("function buildOvpnConnectionTab")
    ende = text.index("function buildOvpnCertificatesTab")
    reiter = text[anfang:ende]
    assert "buildStringList(" in reiter, (
        "der OpenVPN-Reiter zeigt die Netzliste nicht - sie ist damit "
        "weder sichtbar noch bearbeitbar")
    assert "currentSettings.routed_networks" in reiter, (
        "der OpenVPN-Reiter fuehrt eine EIGENE Netzliste statt der "
        "gemeinsamen - zwei Listen sind zwei, die auseinanderlaufen")


def test_die_reiterleiste_bleibt_bei_vier_knoepfen():
    """Die Netzliste kam in einen BESTEHENDEN Reiter und nicht in einen
    fuenften: die Breitenrechnung im Kopf der Vorlage haengt daran."""
    text = VORLAGE.read_text(encoding="utf-8")
    anfang = text.index("function tabsForKind")
    ende = text.index("function clearBox")
    assert text[anfang:ende].count('{ id: "') == 12, (
        "drei Bauarten mal vier Reiter - es sind nicht mehr zwoelf")
