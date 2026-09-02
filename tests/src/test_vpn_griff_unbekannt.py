# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Griff und der Trennpfad, gegen ein `ip`, das nicht antwortet.

DER SATZ, AUF DEN ES ANKOMMT
    Ein fehlendes oder haengendes `ip` baut keinen stehenden Tunnel mehr
    ab, und eine Trennung, bei der niemand nachsehen konnte, meldet
    keinen Erfolg.

    Gemessen wird das am GERENDERTEN Skript und gegen das ECHTE
    src/vpn.py - nicht gegen eine Attrappe, die das gewuenschte Wort
    schreibt. Der Unterschied ist hier wesentlich: die Kette, die
    geprueft wird, ist genau die, die vorher gerissen ist -

        ip -o addr show  ->  configured_addresses()  ->  address_present()
                         ->  tunnel_status()  ->  --status  ->  VPN_STATE
                         ->  toggle_vpn  ->  disconnect_vpn

    Ein Test, der irgendwo in der Mitte eine Attrappe einsetzt, misst
    die Haelfte der Kette und laesst die andere Haelfte offen.

WAS VORHER GESCHAH - GEMESSEN am 01.09.2026
    `ip` fehlt oder haengt -> configured_addresses() = {} ->
    address_present() = "" -> tunnel_status() = ('stale', <Adresse>) ->
    `toggle` liest "nicht disconnected" -> TRENNT.

    Und im Trennpfad ein zweites Mal, in die andere Richtung: die
    Erfolgspruefung las aus demselben "" ab, die Adresse sei
    verschwunden, und meldete "Erfolgreich getrennt", waehrend sie
    womoeglich noch anlag.

SICHERHEIT
    `env -i` mit dem Attrappenverzeichnis als GANZEM PATH, vorher
    zugesichert. `ip`, `pgrep`, `swanctl`, `systemctl` und `sudo` sind
    Attrappen, die ihren Aufruf mitschreiben; die Zustandsdatei liegt in
    tmp_path. Kein Aufruf geht gegen die Sitzung des Entwicklers, und
    keiner traegt ein Geheimnis - `--status` liest keines.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

BASH = "/bin/bash"
ENV = "/usr/bin/env"

pytestmark = pytest.mark.allow_subprocess

# RFC 5737 TEST-NET-3, wie ueberall in dieser Suite.
ZUGEWIESEN = "203.0.113.9"

# Werkzeuge, die nichts ueber die Maschine verraten und nichts an ihr
# aendern. `ip`, `pgrep`, `swanctl`, `systemctl`, `sudo` und
# `notify-send` sind ausdruecklich NICHT dabei.
DURCHGEREICHT = ("date", "mkdir", "id", "cat", "sed", "grep", "awk", "tr",
                 "sleep", "rm", "curl")


def _wo(name: str) -> str:
    from shutil import which
    return which(name, path="/usr/bin:/bin:/usr/local/bin") or ""


class Welt:
    """Das gerenderte vpn-control.sh, gegen das ECHTE src/vpn.py."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.stubs = root / "stubs"
        self.stubs.mkdir(parents=True)
        self.aufrufe = root / "aufrufe"
        self.runtime = root / "run"
        self.runtime.mkdir()
        self.runtime.chmod(0o700)
        self.home = root / "home"
        self.home.mkdir()

        for name in DURCHGEREICHT:
            echt = _wo(name)
            if echt:
                self.stub(name, f'exec "{echt}" "$@"')
        self.stub("python3", f'exec "{sys.executable}" "$@"')

        # Der Grundzustand: charon laeuft, `ip` zaehlt die zugewiesene
        # Adresse auf. Also ein STEHENDER Tunnel.
        self.charon(True)
        self.ip_antwortet([f"{ZUGEWIESEN}/32"])
        for name in ("swanctl", "systemctl", "sudo", "notify-send"):
            self.mitschreibende_attrappe(name, "exit 0")

        self.script = self._rendern()

    # -- Attrappen ---------------------------------------------------

    def stub(self, name: str, body: str) -> None:
        pfad = self.stubs / name
        pfad.write_text(f"#!/bin/bash\n{body}\n", encoding="utf-8")
        pfad.chmod(0o755)

    def mitschreibende_attrappe(self, name: str, body: str) -> None:
        self.stub(name, f"printf '{name} %s\\n' \"$*\" >> '{self.aufrufe}'\n"
                        + body)

    def charon(self, laeuft: bool) -> None:
        self.mitschreibende_attrappe(
            "pgrep", "echo 123" if laeuft else "exit 1")

    def ip_antwortet(self, adressen) -> None:
        zeilen = "".join(
            f"echo '2: eth0    inet {a} scope global eth0'\n" for a in adressen)
        self.mitschreibende_attrappe("ip", zeilen + "exit 0")

    def ip_fehlt(self) -> None:
        """Kein `ip` auf der Maschine.

        Nachgebildet und nicht weggelassen: eine Attrappe, die es GAR
        NICHT gibt, liesse den PATH-Waechter dieser Suite anschlagen,
        und der Unterschied zwischen "127 vom Interpreter" und "OSError
        aus subprocess" ist fuer die gepruefte Kette keiner - beide
        enden in configured_addresses() als "nicht gefragt".
        """
        self.mitschreibende_attrappe("ip", "exit 127")

    def ip_haengt(self) -> None:
        """`ip`, das nicht zurueckkommt.

        Sieben Sekunden gegen die fuenf, die _antwort() als Frist
        setzt - nicht laenger, damit der Test nicht zur Geduldsprobe
        wird, und nicht knapper, damit die Frist auf einer langsamen
        Maschine wirklich zuschlaegt.
        """
        self.mitschreibende_attrappe("ip", f'"{_wo("sleep")}" 7')

    # -- Zustand und Lauf --------------------------------------------

    def aufzeichnung(self, **felder) -> None:
        dokument = {"status": "connected", "connection_name": "work",
                    "virtual_ip": ZUGEWIESEN}
        dokument.update(felder)
        (self.runtime / "vpn-active").write_text(json.dumps(dokument),
                                                 encoding="utf-8")

    def aufzeichnung_da(self) -> bool:
        return (self.runtime / "vpn-active").exists()

    def _rendern(self) -> Path:
        sys.path.insert(0, str(SRC))
        try:
            import template_processor
            processor = template_processor.ConfigProcessor(
                paths={"ZEPOS_SYSTEM_ROOT": str(SRC)})
        finally:
            sys.path.remove(str(SRC))
        ziel = self.root / "vpn-control.sh"
        processor.apply_template(
            SRC / "templates" / "vpn-control-config.template", ziel)
        ziel.chmod(0o755)
        return ziel

    def notierte_aufrufe(self) -> list[str]:
        if not self.aufrufe.exists():
            return []
        return self.aufrufe.read_text(encoding="utf-8").splitlines()

    def notiert(self, *werkzeuge: str) -> list[str]:
        return [z for z in self.notierte_aufrufe()
                if z.split(" ", 1)[0] in werkzeuge]

    def protokoll(self) -> str:
        ordner = self.runtime / "zepos-vpn"
        if not ordner.is_dir():
            return ""
        return "\n".join(p.read_text(encoding="utf-8")
                         for p in sorted(ordner.glob("vpn-control-*.log")))

    def lauf(self, *argumente: str) -> subprocess.CompletedProcess:
        pfad = str(self.stubs)
        assert pfad.split(os.pathsep) == [pfad], "PATH traegt genau einen Eintrag"
        # ZEPOS_USER_ROOT in tmp_path: `--status` liest die
        # Einstellungen, und ohne diese Zeile laese es die des
        # Entwicklers. Ohne Datei ist die Bauart "ipsec" - genau die
        # Haelfte, um die es hier geht.
        return subprocess.run(
            [ENV, "-i", f"PATH={pfad}", f"HOME={self.home}",
             f"XDG_RUNTIME_DIR={self.runtime}",
             f"ZEPOS_USER_ROOT={self.home}/zepos",
             f"XDG_CONFIG_HOME={self.home}/.config",
             BASH, str(self.script), *argumente],
            env={}, input="", capture_output=True, text=True, timeout=120)


@pytest.fixture
def welt(tmp_path) -> Welt:
    w = Welt(tmp_path)
    w.aufzeichnung()
    return w


# --------------------------------------------------------------------
# 1. Die Ausgangslage - ohne sie sagt der Rest nichts
# --------------------------------------------------------------------

def test_bei_antwortendem_ip_steht_der_tunnel(welt):
    """Die Gegenprobe, und sie ist keine Formsache.

    Alle Zusicherungen darunter haben die Form "es passiert NICHT". Sie
    waeren samt und sonders gruen, wenn dieser Aufbau ueberhaupt keinen
    stehenden Tunnel erzeugte - also muss zuerst dastehen, dass er
    einen erzeugt.
    """
    ergebnis = welt.lauf("status")

    assert ergebnis.stdout.strip() == f"connected", (
        ergebnis.stdout + ergebnis.stderr)


def test_bei_antwortendem_ip_trennt_der_griff_auch_wirklich(welt):
    """Und der Griff handelt auf diesen Zustand hin.

    Die zweite Haelfte der Gegenprobe: `toggle` MUSS auf einen
    stehenden Tunnel hin trennen. Ohne diese Zeile bewiese
    test_ein_fehlendes_ip_baut_keinen_stehenden_tunnel_ab nur, dass
    dieses Skript nie etwas tut.
    """
    welt.lauf("toggle")

    assert welt.notiert("swanctl", "systemctl", "sudo") != [], (
        "der Griff hat auf einen stehenden Tunnel hin nichts getan")


# --------------------------------------------------------------------
# 2. DER SATZ, AUF DEN ES ANKOMMT
# --------------------------------------------------------------------

@pytest.mark.parametrize("lage", ["fehlt", "haengt"])
def test_ein_stummes_ip_baut_keinen_stehenden_tunnel_ab(welt, lage):
    """Die eine Zusicherung, um deretwillen es diese Aufgabe gibt.

    GEMESSEN am 01.09.2026, vor der Behebung: ein fehlendes `ip` machte
    aus einem stehenden Tunnel ('stale', <Adresse>), `toggle` las "nicht
    disconnected" und TRENNTE. Die Verbindung, die der Nutzer wirklich
    benutzt, ist IPsec.

    Gemessen wird nicht das Wort, sondern die HANDLUNG: kein
    privilegiertes Werkzeug wurde angefasst, und die Aufzeichnung des
    Tunnels steht noch. Ein Test auf das Wort allein liesse offen, ob
    der Griff es auch beachtet.
    """
    getattr(welt, f"ip_{lage}")()

    ergebnis = welt.lauf("toggle")

    gehandelt = welt.notiert("swanctl", "systemctl", "sudo")
    assert gehandelt == [], (
        f"ein `ip`, das {lage}, hat einen Tunnelabbau ausgeloest: "
        + str(gehandelt))
    assert welt.aufzeichnung_da(), (
        "die Aufzeichnung des Tunnels ist weg - der Abbau hat "
        "stattgefunden")
    assert ergebnis.returncode != 0, ergebnis.stdout + ergebnis.stderr


@pytest.mark.parametrize("lage", ["fehlt", "haengt"])
def test_ein_stummes_ip_ergibt_unknown_und_nicht_stale(welt, lage):
    """Das Wort dahinter - und dass es nicht `stale` ist.

    Der Zustand, den der Griff oben nicht mehr zum Anlass nimmt. Hier
    steht er als Wort da, damit ein spaeterer Fehlschlag sagt, an
    welcher Stelle der Kette er sitzt: schreibt `--status` schon das
    falsche Wort, oder liest das Skript das richtige falsch?
    """
    getattr(welt, f"ip_{lage}")()

    ergebnis = welt.lauf("status")

    assert ergebnis.stdout.split()[0] == "unknown", (
        ergebnis.stdout + ergebnis.stderr)


def test_ein_stummes_pgrep_baut_ebenfalls_nichts_ab(welt):
    """Das zweite erfragte Beweisstueck, dieselbe Zusicherung.

    `pgrep` rc=2 ist "Fehler in der Befehlszeile" und sagt nichts ueber
    charon - anders als rc=1, das "kein Treffer" heisst und im Test
    darunter steht.
    """
    welt.mitschreibende_attrappe("pgrep", "exit 2")

    welt.lauf("toggle")

    assert welt.notiert("swanctl", "systemctl", "sudo") == []
    assert welt.aufzeichnung_da()


# --------------------------------------------------------------------
# 3. Und was WEITERHIN getrennt wird - sonst waere der Umbau ein Schaden
# --------------------------------------------------------------------

def test_ein_wirklich_halb_abgestuerzter_tunnel_wird_weiterhin_getrennt(welt):
    """`stale` bleibt ein Grund zu handeln.

    DIE ZUSICHERUNG, DIE DIE VERWORFENE ALTERNATIVE ERSETZT
        Der andere Weg waere gewesen, `toggle` nicht mehr auf `stale`
        trennen zu lassen. Er traegt nicht: ein halb abgestuerzter
        Tunnel MUSS abgebaut werden, sonst baut das naechste Verbinden
        auf xfrm-Policies, Routen und einer virtuellen Adresse auf, die
        niemand abgeraeumt hat.

        Der Umbau macht diese Alternative ueberfluessig, statt sie zu
        brauchen: seit kein Messfehler mehr `stale` erzeugt, IST `stale`
        wieder das, was es behauptet - und der Griff darf darauf
        trennen. Diese Zeile haelt fest, dass er es noch tut.

    Aufgebaut wird der Fall mit `pgrep` rc=1: charon ist nachweislich
    weg, waehrend die Aufzeichnung steht. Eine Auskunft, kein Ausfall.
    """
    welt.charon(False)

    welt.lauf("toggle")

    assert welt.notiert("swanctl", "systemctl", "sudo") != [], (
        "ein halb abgestuerzter Tunnel wird nicht mehr abgebaut - das "
        "naechste Verbinden baut auf seinen Resten auf")


# --------------------------------------------------------------------
# 4. Der Trennpfad: kein Erfolg ohne Nachsehen
# --------------------------------------------------------------------

@pytest.mark.parametrize("lage", ["fehlt", "haengt"])
def test_eine_ungepruefte_trennung_meldet_keinen_erfolg(welt, lage):
    """Die zweite, gefaehrlichere Haelfte desselben Fundes.

    Hier zeigt die Blindheit in die ANDERE Richtung als beim Griff: die
    Erfolgspruefung las aus dem leeren Ergebnis ab, die Adresse sei
    verschwunden - also "Erfolgreich getrennt", waehrend sie womoeglich
    noch anlag und der Nutzer weiter im fremden Netz war. Wortgleich
    derselbe Schaden, den der Kommentar an jener Stelle schon einmal
    beschreibt.

    Der Erfolgszweig LOESCHT die Zustandsdatei. Danach ist die Adresse,
    die abgeraeumt werden muesste, nirgends mehr notiert - darum wird
    hier gemessen, dass sie noch da ist: ein zu Unrecht gemeldeter
    Erfolg kostet die einzige Spur.
    """
    # Die Gegenprobe zuerst, sonst sagt die Zusicherung darunter nichts:
    # eine Trennung, bei der `ip` ANTWORTET und die Adresse nachweislich
    # weg ist, muss die Aufzeichnung abraeumen. `ip_antwortet([])` ist
    # dabei kein Trick, sondern der Zustand nach einem geglueckten
    # Abbau - die Attrappe kann nicht selbst loeschen, was sie aufzaehlt.
    welt.charon(False)
    welt.ip_antwortet([])
    welt.lauf("disconnect")
    assert not welt.aufzeichnung_da(), (
        "Aufbau stimmt nicht: eine nachgewiesene Trennung raeumt die "
        "Aufzeichnung ab")

    welt.aufzeichnung()
    getattr(welt, f"ip_{lage}")()

    welt.lauf("disconnect")

    assert welt.aufzeichnung_da(), (
        "die Trennung hat sich als erfolgreich verbucht, ohne nachsehen "
        "zu koennen - und dabei die einzige Spur der Adresse geloescht")
    assert "unverified" in welt.protokoll(), welt.protokoll()
