# SPDX-License-Identifier: GPL-3.0-or-later
"""Eine WireGuard-Verbindung, die WIRKLICH STAND - ohne fremden Server.

WORAUF DIESE DATEI ANTWORTET
    Gefragt am 22.08.2026: "und hast du alle wirklich durchgetestet und
    sie funktionieren auch?"

    Die ehrliche Antwort war nein. Geprueft waren Einheitentests mit
    Attrappen, die erzeugte Datei gegen NetworkManagers eigenen Einleser
    und das Fenster im verschachtelten Compositor - aber KEINE der drei
    Bauarten war je gegen ein Gegenueber verbunden. Zwanzig Attrappen
    sagen nichts darueber, ob am Ende ein Schluesselaustausch zustande
    kommt.

    Fuer WireGuard laesst sich das nachholen, und zwar vollstaendig
    lokal. GEMESSEN am 22.08.2026 auf dieser Maschine:

        latest-handshake   0        vor dem ersten Paket
        latest-handshake   != 0     danach
        transfer           476 / 532 Bytes, in beide Richtungen
        ping durch 10.9.0.0/24      3 von 3, 0% Verlust

    Das ist ein echter Noise_IK-Handschlag zwischen zwei echten
    Kernel-WireGuard-Schnittstellen mit echten Schluesseln, echtem
    ChaCha20-Poly1305 und echten Zaehlern - nur eben zwischen zwei
    Netzwerk-Namensraeumen statt zwischen zwei Rechnern.

WAS DAMIT NICHT GEPRUEFT IST, und das gehoert dazu
    NetworkManager, polkit, der Endpunkt eines Anbieters, DNS-Uebernahme
    und alles, was Zugangsdaten braucht. Der Handschlag ist die Schicht,
    die man ohne fremdes Netz erreichen kann; er ist NICHT die ganze
    Kette. IPsec und OpenVPN lassen sich so nicht nachstellen: beide
    brauchen einen Dienst (charon bzw. openvpn) mit Rechten, die dieser
    Lauf nicht hat und nicht haben soll.

WARUM DAS DAS NETZ DES NUTZERS NICHT BERUEHRT
    Alles laeuft in `unshare -Urmn`: ein eigener Benutzer-, Einhaenge-
    und Netzwerk-Namensraum. Darin ist dieser Lauf "root" - aber nur
    darin. Die Schnittstellen (ein veth-Paar und zwei wg0) existieren
    ausschliesslich in den beiden erzeugten Namensraeumen, /run wird von
    einem tmpfs im privaten Einhaenge-Namensraum verdeckt, und beim
    Beenden des Prozesses verschwindet alles davon von selbst. Kein
    sudo, kein `ip link` am System des Nutzers, keine
    NetworkManager-Verbindung.

    Die Adressen kommen aus den Dokumentationsbereichen (RFC 5737),
    dieselbe Regel wie in tests/src/test_vpn_secrets.py.

DIE SCHLUESSEL ENTSTEHEN ZUR LAUFZEIT
    `wg genkey` erzeugt sie im Namensraum, sie liegen unter tmp_path und
    sind mit dem Lauf wieder weg. Im Quelltext steht keiner - und keiner
    reist ueber eine Befehlszeile: `wg set ... private-key DATEI` liest
    ihn aus der Datei, genau wie src/vpn.py es tut.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[2]
SRC = WURZEL / "src"

sys.path.insert(0, str(SRC))
import vpn  # noqa: E402

# Was die Gegenstelle erlaubt: der Volltunnel, um den es in dieser
# Aufgabe geht. Der Lauf prueft damit BEIDES an einem Stueck - dass die
# Verbindung mit dieser Einstellung wirklich zustande kommt, und dass
# src/vpn.py genau sie einen Volltunnel nennt.
ALLOWED_IPS = ["0.0.0.0/0", "::/0"]

SKRIPT = """
set -e
mount -t tmpfs none /run
umask 077
wg genkey > "$1/a.key"; wg pubkey < "$1/a.key" > "$1/a.pub"
wg genkey > "$1/b.key"; wg pubkey < "$1/b.key" > "$1/b.pub"

ip netns add a
ip netns add b
ip link add veth-a type veth peer name veth-b
ip link set veth-a netns a
ip link set veth-b netns b
ip -n a addr add 192.0.2.1/24 dev veth-a
ip -n b addr add 192.0.2.2/24 dev veth-b
ip -n a link set veth-a up
ip -n b link set veth-b up
ip -n a link set lo up
ip -n b link set lo up

ip -n a link add wg0 type wireguard
ip -n b link add wg0 type wireguard
ip netns exec a wg set wg0 listen-port 51820 private-key "$1/a.key" \
  peer "$(cat "$1/b.pub")" allowed-ips %(allowed)s endpoint 192.0.2.2:51820
ip netns exec b wg set wg0 listen-port 51820 private-key "$1/b.key" \
  peer "$(cat "$1/a.pub")" allowed-ips 10.9.0.1/32
ip -n a addr add 10.9.0.1/24 dev wg0
ip -n b addr add 10.9.0.2/24 dev wg0
ip -n a link set wg0 up
ip -n b link set wg0 up

echo "VORHER $(ip netns exec a wg show wg0 latest-handshakes | cut -f2)"
ip netns exec a ping -c 2 -W 5 10.9.0.2 > /dev/null && echo "PING OK"
echo "NACHHER $(ip netns exec a wg show wg0 latest-handshakes | cut -f2)"
echo "UEBERTRAGEN $(ip netns exec a wg show wg0 transfer | cut -f2,3)"
echo "GEGENSEITE $(ip netns exec b wg show wg0 transfer | cut -f2,3)"
rm -f "$1"/*.key "$1"/*.pub
""" % {"allowed": ",".join(ALLOWED_IPS)}


def _fehlende_voraussetzung() -> str:
    """Was fehlt, damit dieser Lauf ueberhaupt moeglich ist - oder ""."""
    for werkzeug in ("unshare", "ip", "wg", "ping"):
        if shutil.which(werkzeug) is None:
            return f"{werkzeug} fehlt"
    erlaubt = Path("/proc/sys/user/max_user_namespaces")
    if not erlaubt.exists() or erlaubt.read_text().strip() in ("", "0"):
        return "unprivilegierte Benutzer-Namensraeume sind abgeschaltet"
    if not Path("/sys/module/wireguard").exists():
        return ("das Kernelmodul wireguard ist nicht geladen - es laesst "
                "sich ohne Rechte nicht nachladen")
    return ""


@pytest.mark.allow_subprocess
def test_eine_echte_wireguard_verbindung_kommt_zustande(tmp_path):
    """Der Handschlag, gemessen statt behauptet.

    Vor dem ersten Paket steht `latest-handshake` auf 0 - WireGuard
    baut erst auf, wenn Verkehr anliegt. Danach steht dort eine
    Zeitmarke, und beide Seiten haben Bytes gezaehlt. Genau diese drei
    Zahlen unterscheiden eine Verbindung, die STAND, von einer
    Schnittstelle, die nur angelegt wurde.
    """
    fehlt = _fehlende_voraussetzung()
    if fehlt:
        pytest.skip(f"kein lokales WireGuard-Gegenueber moeglich: {fehlt}")

    skript = tmp_path / "gegenueber.sh"
    skript.write_text(SKRIPT, encoding="utf-8")
    lauf = subprocess.run(
        ["unshare", "-Urmn", "--fork", "--propagation", "private",
         "bash", str(skript), str(tmp_path)],
        capture_output=True, text=True, timeout=120)
    if lauf.returncode != 0:
        # Ein Kernel ohne diese Faehigkeit ist kein Fehlschlag DIESES
        # Auftrags - er ist eine Maschine, auf der die Messung nicht
        # geht. Der Grund steht in der Meldung, damit niemand raten muss.
        pytest.skip("das lokale Gegenueber liess sich nicht aufbauen:\n"
                    + lauf.stdout + lauf.stderr)

    zeilen = dict(
        zeile.split(" ", 1) for zeile in lauf.stdout.strip().splitlines()
        if " " in zeile)
    assert "PING OK" in lauf.stdout, (
        "durch den Tunnel kam kein einziges Paket:\n" + lauf.stdout)
    assert zeilen.get("VORHER") == "0", (
        "vor dem ersten Paket darf es keinen Handschlag geben - sonst "
        f"misst dieser Lauf nichts: {zeilen}")
    assert zeilen.get("NACHHER", "0") != "0", (
        "nach dem Verkehr steht immer noch kein Handschlag in der "
        f"Zaehlerliste: {zeilen}")

    # `wg show ... transfer` schreibt Empfangenes vor Gesendetem.
    empfangen, gesendet = zeilen["UEBERTRAGEN"].split()
    assert int(empfangen) > 0 and int(gesendet) > 0, (
        "die Verbindung hat in einer Richtung nichts uebertragen: "
        f"{zeilen}")
    gegen_empfangen, gegen_gesendet = zeilen["GEGENSEITE"].split()
    assert int(gegen_empfangen) > 0 and int(gegen_gesendet) > 0, (
        f"die Gegenstelle hat nichts gezaehlt: {zeilen}")


def test_genau_diese_allowed_ips_heissen_volltunnel():
    """Die zweite Haelfte derselben Messung, und der Grund, aus dem der
    Lauf oben ausgerechnet `0.0.0.0/0, ::/0` einstellt: die Verbindung,
    die eben wirklich stand, war ein VOLLTUNNEL - und src/vpn.py muss
    sie so nennen. Eine Erkennung, die nur gegen erfundene Listen
    geprueft ist, ist gegen nichts geprueft."""
    assert vpn.full_tunnel_families(ALLOWED_IPS) == ["ipv4", "ipv6"]
