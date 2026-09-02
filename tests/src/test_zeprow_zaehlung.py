# SPDX-License-Identifier: GPL-3.0-or-later
"""Wie oft haengt ein bedienbares Kind in einer klickbaren Zeile?

DIE ZAHL, DIE DEN UMFANG EINES UMBAUS ENTSCHEIDET
    Im Bericht zu Aufgabe 76 steht ein Befund, den ich selbst
    aufgeschrieben und nicht gemessen habe:

        "zepRow haengt sein `ende` - also den Gtk.Switch - INNERHALB der
         Zeile ein und wickelt die Zeile dann in einen Gtk.Button. In
         GTK4 ist ein Button kein Behaelter fuer bedienbare Kinder ...
         verlassen wuerde ich mich darauf nicht."

    Dazu stand dort, es sei ein Problem des GETEILTEN Bauteils und
    treffe "Bluetooth, Netz und die Seitenleiste mit". Diese Datei
    zaehlt nach, ob das stimmt - denn davon haengt ab, ob eine Reparatur
    zepRow selbst anfassen muss oder einen einzigen Aufrufer.

    Was daraus WIRD, wenn man auf die Zeile klickt oder eine Taste
    drueckt, misst tests/render/test_zeprow_verschachtelung.py an einem
    wirklich abgebildeten Fenster. Hier steht nur die Zaehlung, und sie
    steht in tests/src/, weil sie den Quelltext zaehlt und keinen
    Compositor braucht.
"""
from __future__ import annotations

import re
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
TEMPLATES = REPOSITORY / "src" / "templates"

# Die Felder, um die es geht: `aktion` macht die ganze Zeile zu einem
# Knopf, `ende` haengt ein Widget hinein. Beides zusammen ist die
# Verschachtelung.
FELDER = ("aktion", "ende")


def _zeprow_aufrufe() -> dict[str, list[str]]:
    """Jeder zepRow-Aufruf im Baum, mit den Feldern, die er setzt.

    Ueber Klammerzaehlung und nicht ueber einen regulaeren Ausdruck: die
    Felder eines Aufrufs enthalten selbst geschweifte Klammern (jede
    Rueckruffunktion tut das), und ein nicht-gieriges `\\{.*?\\}` schnitte
    beim ersten inneren `}` ab - also mitten in dem Aufbau, ueber den
    hier entschieden wird. Dieselbe Begruendung wie bei
    _object_literals() in tests/src/test_modal_rule.py.
    """
    gefunden: dict[str, list[str]] = {}
    for pfad in sorted(TEMPLATES.glob("*.template")):
        # Zeilenkommentare heraus: jede Datei dieses Baums ERKLAERT, was
        # sie nicht mehr tut, und eine Suche nach "ende:" wuerde von der
        # Erklaerung wahr.
        text = "\n".join(
            zeile for zeile in pfad.read_text(encoding="utf-8").splitlines()
            if not zeile.lstrip().startswith("//"))
        start = 0
        nummer = 0
        while True:
            treffer = text.find("zepRow({", start)
            if treffer < 0:
                break
            offen = 0
            i = treffer + len("zepRow(")
            while i < len(text):
                if text[i] == "{":
                    offen += 1
                elif text[i] == "}":
                    offen -= 1
                    if offen == 0:
                        break
                i += 1
            block = text[treffer:i + 1]
            nummer += 1
            gefunden[f"{pfad.name}#{nummer}"] = [
                feld for feld in FELDER
                if re.search(rf"(^|[\s,{{]){feld}\s*:", block)]
            start = i + 1
    return gefunden


def test_die_zaehlung_findet_ueberhaupt_zeilen():
    """Die Gegenprobe zuerst.

    Die Zusicherung darunter ist erfuellt, wenn NICHTS gefunden wurde -
    und nichts wird auch gefunden, wenn zepRow einmal anders heisst.
    Dann misst die Datei still nichts mehr.
    """
    aufrufe = _zeprow_aufrufe()
    assert len(aufrufe) >= 8, (
        f"nur {len(aufrufe)} zepRow-Aufrufe gefunden - am 02.09.2026 "
        f"waren es sechzehn. Heisst das Bauteil noch zepRow?\n{aufrufe}")
    assert any("aktion" in felder for felder in aufrufe.values()), (
        "kein einziger Aufruf setzt `aktion` - die Suche greift nicht mehr")
    assert any("ende" in felder for felder in aufrufe.values()), (
        "kein einziger Aufruf setzt `ende` - die Suche greift nicht mehr")


def test_nur_ein_einziger_aufrufer_verschachtelt_ueberhaupt():
    """EIN Aufrufer, nicht vier - und das aendert den Umfang.

    GEZAEHLT am 02.09.2026 ueber alle src/templates/*.template -
    sechzehn Aufrufe, und genau EINER haengt beides zusammen:

        ags-vpn.template          aktion + ende  <- der einzige
        ags-settings.template     nur ende (fuenfmal)
        ags-bluetooth.template    nur aktion
        ags-network.template      nur aktion
        ags-kit.template          nur aktion  (die Seitenleiste)
        ags-control-center.template  nur aktion
        ags-dock.template         nur aktion
        ags-home.template         nur aktion
        ags-vpn-settings.template nur aktion

    Dazu drei Aufrufe, die weder das eine noch das andere setzen
    (ags-bluetooth, ags-network, ags-settings je einmal) - reine
    Anzeigezeilen.

    Der Bericht zu Aufgabe 76 hat das anders vermutet ("trifft
    Bluetooth, Netz und die Seitenleiste mit"). Die Zaehlung sagt: nein.
    Bluetooth, Netz und die Seitenleiste haengen KEIN bedienbares Kind in
    ihre Zeile - sie sind ganz Knopf und nichts sonst. Eine Reparatur
    ist damit eine oertliche und kein Eingriff in ein geteiltes Bauteil.

    Waere es eines Tages ein zweiter Aufrufer, gilt dieser Satz nicht
    mehr - dann ist die Verschachtelung ein Problem des Bauteils, und
    diese Zusicherung sagt es laut.

    NACHGEPRUEFT am 02.09.2026, nachdem das Zahnrad in die VPN-Zeile kam:
    die Zahl stimmt unveraendert. Gezaehlt werden AUFRUFER, und der eine
    haengt seither ZWEI Bedienelemente in sein `ende` - eine Gtk.Box mit
    Zahnrad und Schalter darin. Aus einem `ende` werden davon nicht zwei,
    und zepRow hat es nicht bemerkt: der Diff von ags-kit.template ist
    leer. Waeren es zwei `ende` geworden (`ende` als Liste), stuende hier
    eine andere Zahl - das war ein Grund fuer die Box.
    """
    aufrufe = _zeprow_aufrufe()
    beide = sorted(name for name, felder in aufrufe.items()
                   if "aktion" in felder and "ende" in felder)
    assert beide == ["ags-vpn.template#1"], (
        "die Menge der Aufrufer, die ein bedienbares Kind IN eine "
        f"klickbare Zeile haengen, hat sich geaendert: {beide}. Ist ein "
        "zweiter dazugekommen, gehoert die Reparatur nach zepRow selbst "
        "und nicht mehr in ein einzelnes Fenster - und der Bericht dazu.")
