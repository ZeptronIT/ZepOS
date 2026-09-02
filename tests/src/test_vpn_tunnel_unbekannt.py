# SPDX-License-Identifier: GPL-3.0-or-later
"""Die IPsec-Haelfte: drei Beweisstuecke, und was gilt, wenn eines fehlt.

DER BEFUND, GEMESSEN am 01.09.2026 und am 02.09.2026 bestaetigt
    `tunnel_status()` setzt drei Beweisstuecke zusammen. Zwei davon
    kosten einen Unterprozess, und beide Helfer sahen bis zum 02.09.2026
    nicht hin, ob der ueberhaupt gelaufen ist:

        alles antwortet -> ('connected','10.9.0.2')
        `ip` fehlt      -> ('stale','10.9.0.2')
        `ip` Zeitablauf -> ('stale','10.9.0.2')
        `ip` rc=1       -> ('stale','10.9.0.2')
        `pgrep` fehlt   -> ('stale','10.9.0.2')

    `stale` ist keine Verlegenheitsantwort, sondern eine BEHAUPTUNG, und
    eine der schaerfsten, die dieses Programm kennt: "der Tunnel steht
    und traegt nichts" - der Nutzer haelt sich fuer geschuetzt und ist
    es nicht. Das Schild malt sie im Kritischrot, und der Griff TRENNT
    darauf hin. Ein fehlendes `ip` genuegte also, um einen gesunden
    Tunnel abzubauen.

    Und die Verbindung, die der Nutzer wirklich benutzt, ist IPsec.

DIE ENTSCHEIDUNG, DIE HIER GEMESSEN WIRD
    Die ausfuehrliche Begruendung steht im Kopf von
    src/vpn.py::tunnel_status(). Kurz:

      1. Die AUFZEICHNUNG ist die Praemisse und kostet keinen
         Unterprozess - sie kann nicht unbeantwortbar sein.
      2. Ist EINES der beiden erfragten Beweisstuecke unbeantwortbar,
         heisst der Gesamtzustand `unknown`. Auch wenn nur eines fehlt,
         auch wenn beide fehlen: der Leser hat eine Zeile Text und eine
         Entscheidung, und "teilweise unbekannt" ist nichts, worauf er
         anders handeln koennte.
      3. `unknown` traegt die AUFGEZEICHNETE Adresse - anders als bei
         wireguard_status(), wo es keine gibt. Sie ist das eine
         Beweisstueck, das in diesem Zweig BEKANNT ist, und der
         Trennpfad braucht sie genau dann.

DIE EIGENTLICHE ZUSICHERUNG DIESER DATEI
    Abschnitt 4: ein fehlendes oder haengendes `ip` baut keinen
    stehenden Tunnel mehr ab. Gemessen am gerenderten Skript, nicht am
    Quelltext.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.vpn import (CONNECTED, DISCONNECTED, STALE, STATUS_WORDS, UNKNOWN,
                     address_present, configured_addresses, tunnel_status)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

BASH = "/bin/bash"
ENV = "/usr/bin/env"

# Eine Adresse aus dem Dokumentationsbereich (RFC 5737, TEST-NET-3), wie
# ueberall in dieser Suite: eine ausgedachte kann die eines fremden
# Geraetes sein.
ZUGEWIESEN = "203.0.113.9"
FREMD = "198.51.100.7"


# --------------------------------------------------------------------
# Die Welt, in der `tunnel_status()` fragt
# --------------------------------------------------------------------

class Antworter:
    """Ein `runner` mit einer eigenen Antwort je Werkzeug.

    `pgrep` und `ip` sind die beiden Fragen, die tunnel_status() stellt.
    Getrennt einstellbar, weil genau die Trennung hier gemessen wird:
    ein Beweisstueck kann fehlen, waehrend das andere antwortet.
    """

    def __init__(self, *, charon=0, adressen=(), ip=0) -> None:
        # `charon` und `ip`: ein int ist ein Rueckgabewert, eine
        # Ausnahme wird geworfen.
        self.charon = charon
        self.ip = ip
        self.adressen = list(adressen)
        self.aufrufe: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        self.aufrufe.append(list(argv))
        lage = self.charon if argv[0] == "pgrep" else self.ip
        if isinstance(lage, BaseException):
            raise lage
        if argv[0] == "pgrep":
            return subprocess.CompletedProcess(
                argv, lage, stdout="123\n" if lage == 0 else "", stderr="")
        text = "".join(f"2: eth0    inet {a} scope global eth0\n"
                       for a in self.adressen)
        return subprocess.CompletedProcess(argv, lage, stdout=text, stderr="")


def zustandsdatei(tmp_path: Path, **felder) -> Path:
    pfad = tmp_path / "vpn-active"
    dokument = {"status": "connected", "connection_name": "work"}
    dokument.update(felder)
    pfad.write_text(json.dumps(dokument), encoding="utf-8")
    return pfad


# Jede Art, wie eine Frage unbeantwortet bleiben kann. Der Zeitablauf
# und das fehlende Werkzeug sind Ausnahmen, die anderen sind
# Rueckgabewerte - pgrep(1) und ip(8) fuehren beide welche, und keiner
# davon heisst "die Antwort ist nein".
UNBEANTWORTBAR = [
    pytest.param(FileNotFoundError("nicht da"), id="werkzeug-fehlt"),
    pytest.param(subprocess.TimeoutExpired("cmd", 5), id="zeitablauf"),
    pytest.param(PermissionError("darf nicht"), id="darf-nicht"),
    pytest.param(1, id="rc-1"),
    pytest.param(2, id="rc-2"),
    pytest.param(127, id="rc-127"),
]


# --------------------------------------------------------------------
# 1. Was NICHT mehr "stale" heissen darf
# --------------------------------------------------------------------

@pytest.mark.parametrize("lage", UNBEANTWORTBAR)
def test_eine_unbeantwortbare_adressfrage_ist_unbekannt(tmp_path, lage):
    """`ip` antwortet nicht - und das heisst nicht "die Adresse ist weg".

    Der gefaehrliche der beiden Faelle, weil `stale` hier eine Aussage
    UEBER DEN SCHUTZ ist: "du haeltst dich fuer geschuetzt und bist es
    nicht". Wer das liest, handelt - und der Griff handelt automatisch.

    Beachte `rc=1`: bei `ip -o addr show` ist das kein "keine Adresse
    gefunden", sondern ein Fehler. Das Werkzeug schreibt seine Liste mit
    rc=0, auch wenn sie leer ist.
    """
    datei = zustandsdatei(tmp_path, virtual_ip=ZUGEWIESEN)
    antworter = Antworter(charon=0, ip=lage)

    zustand, adresse = tunnel_status(datei, antworter)

    assert zustand == UNKNOWN, f"{lage!r} ergibt {zustand!r}"
    assert zustand != STALE


@pytest.mark.parametrize("lage", UNBEANTWORTBAR[:3] + UNBEANTWORTBAR[4:])
def test_eine_unbeantwortbare_charonfrage_ist_unbekannt(tmp_path, lage):
    """`pgrep` antwortet nicht - und das heisst nicht "charon ist tot".

    `rc=1` ist hier ausgenommen und steht in Abschnitt 2: bei pgrep(1)
    IST 1 eine Antwort, naemlich "kein Treffer". Genau diese
    Unterscheidung - welcher Rueckgabewert eine Auskunft ist und welcher
    das Fehlen einer - ist der ganze Umbau; ohne sie waere `unknown` nur
    ein neuer Name fuer den alten Sammelzweig.
    """
    datei = zustandsdatei(tmp_path, virtual_ip=ZUGEWIESEN)
    antworter = Antworter(charon=lage, adressen=[f"{ZUGEWIESEN}/32"])

    assert tunnel_status(datei, antworter)[0] == UNKNOWN


def test_unbekannt_traegt_die_aufgezeichnete_adresse(tmp_path):
    """Und zwar anders als bei WireGuard - mit Absicht.

    `wireguard_status()` gibt zu `unknown` KEINE Adresse: dort waere sie
    geraten. Hier ist sie AUFGESCHRIEBEN, vom Verbindungsskript, und sie
    ist das einzige der drei Beweisstuecke, das in diesem Zweig bekannt
    ist. Sie wegzulassen hiesse, das eine Bekannte auch noch
    wegzuwerfen - und der Trennpfad braucht sie genau dann, um eine
    Adresse von einer Schnittstelle zu nehmen, die charon nicht mehr
    haelt.

    Was sie NICHT darf, ist auf dem Schild stehen. Das haelt
    tests/src/test_bar_vpn.py::
    test_the_error_state_never_shows_the_recorded_address fest.
    """
    datei = zustandsdatei(tmp_path, virtual_ip=ZUGEWIESEN)

    assert tunnel_status(datei, Antworter(charon=0, ip=FileNotFoundError())) \
        == (UNKNOWN, ZUGEWIESEN)


def test_zwei_fehlende_beweisstuecke_sind_derselbe_zustand(tmp_path):
    """Ein unbeantwortbares Beweisstueck oder zwei - dasselbe Wort.

    Die Frage ist nicht rhetorisch: "die Aufzeichnung sagt verbunden,
    aber niemand kann pruefen ob charon laeuft" ist SACHLICH etwas
    anderes als "charon laeuft, aber niemand kann die Adresse pruefen" -
    im zweiten Fall weiss man immerhin, dass ein Tunnelprozess lebt.

    Fuer den LESER ist es dasselbe: er hat eine Zeile Text und eine
    Entscheidung, und beide Male lautet die einzige ehrliche Auskunft
    "niemand weiss, ob dein Verkehr geschuetzt ist". Ein fuenftes Wort
    fuer "teilweise unbekannt" waere eine Unterscheidung, auf die kein
    Leser anders handeln koennte - und vier Leser muessten sie
    mittragen.
    """
    datei = zustandsdatei(tmp_path, virtual_ip=ZUGEWIESEN)

    nur_ip = tunnel_status(datei, Antworter(charon=0, ip=FileNotFoundError()))
    nur_charon = tunnel_status(
        datei, Antworter(charon=FileNotFoundError(),
                         adressen=[f"{ZUGEWIESEN}/32"]))
    beide = tunnel_status(datei, Antworter(charon=FileNotFoundError(),
                                           ip=FileNotFoundError()))

    assert nur_ip == nur_charon == beide == (UNKNOWN, ZUGEWIESEN)


# --------------------------------------------------------------------
# 2. Was WEITERHIN eine Auskunft ist - ohne das waere der Umbau wertlos
# --------------------------------------------------------------------

def test_ein_geantwortetes_kein_treffer_bleibt_stale(tmp_path):
    """pgrep rc=1 IST eine Auskunft: charon laeuft nicht.

    Die andere Haelfte der Aufgabe. Saugte `unknown` jeden Fehlschlag
    auf, waere `stale` verschwunden - und mit ihm der Zustand, fuer den
    es das Wort gibt: charon ist weg, waehrend der Schreibtisch sich
    fuer verbunden haelt.
    """
    datei = zustandsdatei(tmp_path, virtual_ip=ZUGEWIESEN)

    assert tunnel_status(datei, Antworter(charon=1,
                                          adressen=[f"{ZUGEWIESEN}/32"])) \
        == (STALE, ZUGEWIESEN)


def test_eine_geantwortete_liste_ohne_die_adresse_bleibt_stale(tmp_path):
    """`ip` hat rc=0 geliefert und die Adresse steht nicht darin.

    Das ist eine vollstaendige Auskunft ueber die Schnittstellen: die
    virtuelle Adresse ist fort, waehrend charon lebt. Der zweite der
    beiden Wege, auf denen ein Tunnel stirbt, ohne es zu sagen.
    """
    datei = zustandsdatei(tmp_path, virtual_ip=ZUGEWIESEN)

    assert tunnel_status(datei, Antworter(charon=0, adressen=[f"{FREMD}/24"])) \
        == (STALE, ZUGEWIESEN)


def test_eine_leere_geantwortete_liste_bleibt_stale(tmp_path):
    """rc=0 und gar keine Zeile: eine Maschine ohne konfigurierte
    Adressen. Unwahrscheinlich, aber eine Antwort - und `ip` schreibt
    eine leere Liste mit rc=0, nicht mit rc=1."""
    datei = zustandsdatei(tmp_path, virtual_ip=ZUGEWIESEN)

    assert tunnel_status(datei, Antworter(charon=0, adressen=[])) \
        == (STALE, ZUGEWIESEN)


def test_ohne_aufzeichnung_wird_gar_nicht_gefragt(tmp_path):
    """Die Praemisse, und sie kostet keinen Unterprozess.

    Die Aufzeichnung ist das eine Beweisstueck, das nicht unbeantwortbar
    sein KANN: es wird eine Datei gelesen, kein Programm gerufen. Ihr
    Fehlen ist eine Auskunft ("diese Maschine hat nichts aufgebaut") und
    kein Ausfall - strongswan.service kann auf einer Maschine beim Start
    laufen, die nie gewaehlt hat.

    Gemessen wird zusaetzlich, dass NICHTS gefragt wurde: ein `unknown`
    an dieser Stelle waere nicht nur falsch, es waere auch zwei
    Unterprozesse je Takt teuer.
    """
    antworter = Antworter(charon=FileNotFoundError(), ip=FileNotFoundError())

    assert tunnel_status(tmp_path / "vpn-active", antworter) \
        == (DISCONNECTED, "")
    assert antworter.aufrufe == []


def test_ohne_zugewiesene_adresse_wird_nicht_nach_ihr_gefragt(tmp_path):
    """Ein Gegenstellenverbund, der keine Adresse zuweist.

    Voellig gueltig (siehe IkeSA in src/vpn.py). Es gibt nichts gegen
    die Schnittstellen zu pruefen, also wird nicht gefragt - und ein
    `ip`, das gar nicht erst gerufen wird, darf den Zustand auch nicht
    unbekannt machen. Sonst breitete sich `unknown` in einen Zweig aus,
    der nie eine Frage gestellt hat.
    """
    datei = zustandsdatei(tmp_path, virtual_ip="")
    antworter = Antworter(charon=0, ip=FileNotFoundError())

    assert tunnel_status(datei, antworter) == (CONNECTED, "")
    assert [a for a in antworter.aufrufe if a[0] == "ip"] == []


def test_alle_drei_beweisstuecke_ergeben_verbunden(tmp_path):
    """Die Gegenprobe: der gute Fall ist unberuehrt."""
    datei = zustandsdatei(tmp_path, virtual_ip=ZUGEWIESEN)

    assert tunnel_status(datei, Antworter(charon=0,
                                          adressen=[f"{ZUGEWIESEN}/32"])) \
        == (CONNECTED, ZUGEWIESEN)


# --------------------------------------------------------------------
# 3. Die Eigenschaft, auf die es ankommt
# --------------------------------------------------------------------

def test_kein_messfehler_erzeugt_noch_eine_behauptung(tmp_path):
    """`stale` und `connected` sind ab jetzt GEMESSENE Zustaende.

    DIE ZUSICHERUNG, DIE DIE ALTERNATIVE UEBERFLUESSIG MACHT
        Der naheliegende andere Weg waere gewesen, den GRIFF zu
        aendern - "toggle trennt nicht mehr auf `stale`". Er traegt
        nicht, und diese Zeile sagt warum: sobald kein Messfehler mehr
        `stale` erzeugen kann, IST `stale` wieder das, was es behauptet,
        und der Griff darf darauf trennen. Die Alternative haette einen
        von vier Lesern geflickt, waehrend das falsche Wort weiter zu
        den anderen dreien geflossen waere.

    Durchgegangen wird jede Art, wie eine der beiden Fragen scheitern
    kann, in jeder Kombination - und keine davon darf in einer Aussage
    ueber den Schutz enden.
    """
    datei = zustandsdatei(tmp_path, virtual_ip=ZUGEWIESEN)
    behauptungen = {}

    for fall in UNBEANTWORTBAR:
        lage = fall.values[0]
        # `pgrep` rc=1 ist eine Auskunft und gehoert nicht in diese
        # Aufzaehlung - siehe Abschnitt 2.
        for name, antworter in (
                ("ip", Antworter(charon=0, ip=lage)),
                ("beide", Antworter(charon=lage, ip=lage))):
            if name == "beide" and lage == 1:
                continue
            zustand, _ = tunnel_status(datei, antworter)
            if zustand != UNKNOWN:
                behauptungen[f"{name}/{fall.id}"] = zustand

    assert behauptungen == {}, (
        "ein Messfehler endet weiterhin in einer Aussage ueber den "
        f"Schutz: {behauptungen}")


def test_der_vertrag_bleibt_bei_vier_woertern(tmp_path):
    """Kein fuenftes Wort fuer "teilweise unbekannt".

    STATUS_WORDS ist die Liste, gegen die alle Leser gemessen werden
    (tests/src/test_bar_vpn_unbekannt.py geht sie durch). Die IPsec-
    Haelfte darf sie nicht erweitern - vier Leser muessten ein fuenftes
    Wort mittragen, und keiner koennte darauf anders handeln.
    """
    datei = zustandsdatei(tmp_path, virtual_ip=ZUGEWIESEN)
    gesehen = {
        tunnel_status(datei, Antworter(charon=0,
                                       adressen=[f"{ZUGEWIESEN}/32"]))[0],
        tunnel_status(datei, Antworter(charon=1))[0],
        tunnel_status(datei, Antworter(charon=0, ip=FileNotFoundError()))[0],
        tunnel_status(tmp_path / "gibt-es-nicht", Antworter())[0],
    }
    assert gesehen == set(STATUS_WORDS)


# --------------------------------------------------------------------
# 4. Die zwei Helfer, dreiwertig
# --------------------------------------------------------------------

def test_die_adressliste_unterscheidet_leer_von_ungefragt():
    """`{}` heisst "keine Adresse", `None` heisst "nicht gefragt".

    Der Unterschied, den es vorher nicht gab, und er ist die ganze
    Ursache: `_run()` gab bei einem Fehlschlag "" zurueck, daraus wurde
    eine leere Abbildung, und eine leere Abbildung sieht aus wie eine
    Maschine ohne Adressen.
    """
    assert configured_addresses(Antworter(ip=0, adressen=[])) == {}
    assert configured_addresses(Antworter(ip=FileNotFoundError())) is None
    assert configured_addresses(Antworter(ip=1)) is None
    assert configured_addresses(
        Antworter(ip=0, adressen=[f"{ZUGEWIESEN}/32"])) \
        == {ZUGEWIESEN: f"{ZUGEWIESEN}/32"}


def test_address_present_unterscheidet_nicht_da_von_nicht_nachsehbar():
    """`""` heisst "liegt nicht an", `None` heisst "nicht feststellbar".

    Zwei falsche Werte, die nicht dasselbe heissen. Jeder Aufrufer muss
    zuerst auf `None` pruefen - `if not cidr` faellt sonst fuer beide
    gleich aus, und genau das ist der Fehler, der in vpn-control.sh eine
    Trennung als erfolgreich meldete.
    """
    assert address_present(ZUGEWIESEN,
                           Antworter(adressen=[f"{ZUGEWIESEN}/32"])) \
        == f"{ZUGEWIESEN}/32"
    assert address_present(ZUGEWIESEN, Antworter(adressen=[f"{FREMD}/24"])) == ""
    assert address_present(ZUGEWIESEN, Antworter(ip=FileNotFoundError())) is None
    # Ohne Adresse wird nicht gefragt - und "" bleibt "", nicht None:
    # nach nichts zu fragen ist kein Ausfall.
    antworter = Antworter(ip=FileNotFoundError())
    assert address_present("", antworter) == ""
    assert antworter.aufrufe == []
