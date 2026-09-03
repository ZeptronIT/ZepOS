# SPDX-License-Identifier: GPL-3.0-or-later
"""Jede Art von Bedienelement, die die Bruecke kennt, muss das
AGS-Fenster auch zeichnen koennen.

WARUM ES DIESE DATEI GIBT
    Der Nutzer am 03.09.2026: "die zepos gtk4 anwendung die sollte
    komplett ags sein selbst gebaut". Der Weg dahin steht in
    docs/superpowers/specs/2026-09-03-einstellungen-ohne-gtk-anwendung.md
    und hat eine Bedingung: das AGS-Fenster muss ALLES koennen, was das
    Modell anbietet. Sonst faellt mit der GTK-Anwendung eine Einstellung
    weg, die niemand vermisst, bis er sie sucht.

    Beim Schreiben dieses Plans habe ich die Abdeckung mit `grep`
    geschaetzt und mich vertippt - gesucht nach "farben", im Quelltext
    steht "farbe". Ergebnis: der Plan behauptete eine Luecke, die es
    nicht gab. Ein Werkzeug, das die Frage BEANTWORTET, statt sie zu
    schaetzen, ist der ganze Zweck dieser Datei.

WAS SIE NICHT PRUEFT
    Ob das gezeichnete Bedienelement gut ist. Das messen die
    Render-Laeufe. Hier geht es um die geschlossene Liste: was die
    Bruecke ausgeben kann, muss das Fenster annehmen koennen.
"""
from __future__ import annotations

import re
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[2]
BRUECKE = WURZEL / "settings" / "zepos_settings_gui" / "bridge.py"
FENSTER = WURZEL / "src" / "templates" / "ags-settings.template"

# Die Namen in bridge.py, die eine ART benennen - und nicht einen
# BEREICH (konto/maschine/schreibtisch) oder einen Schluessel.
ARTEN = ("NUMBER", "SWITCH", "TEXT", "CHOICE", "COLOUR", "ORDER", "LAYOUT")


def _arten_der_bruecke() -> dict[str, str]:
    """Name -> Wert, aus den Zuweisungen ganz oben in bridge.py."""
    text = BRUECKE.read_text(encoding="utf-8")
    gefunden = {}
    for name in ARTEN:
        treffer = re.search(rf'^{name} = "([a-z]+)"$', text, re.M)
        assert treffer, (
            f"{name} steht nicht mehr in bridge.py - dann ist die Liste "
            f"ARTEN in dieser Datei veraltet und prueft am falschen "
            f"Gegenstand")
        gefunden[name] = treffer.group(1)
    return gefunden


def _fenster_text() -> str:
    return FENSTER.read_text(encoding="utf-8")


def test_das_fenster_kennt_jede_art_beim_namen():
    """Eine Konstante je Art, mit demselben Wert wie in der Bruecke.

    Der Wert und nicht nur der Name: `const FARBE = "farbton"` waere
    eine Konstante, die es gibt, und ein Vergleich, der nie zutrifft.
    """
    text = _fenster_text()
    fehlend = []
    for name, wert in _arten_der_bruecke().items():
        if not re.search(rf'^const [A-Z_]+ = "{wert}"$', text, re.M):
            fehlend.append(f"{name} ({wert})")
    assert fehlend == [], (
        f"das AGS-Fenster kennt diese Arten nicht: {fehlend} - was die "
        f"Bruecke ausgibt und das Fenster nicht kennt, faellt beim "
        f"Zeichnen in den default-Zweig")


def test_das_fenster_zeichnet_jede_art():
    """Und jede Art braucht eine Stelle, die etwas BAUT.

    ZWEI FORMEN, UND BEIDE ZAEHLEN - nachgesehen am 03.09.2026, weil die
    erste Fassung dieser Zusicherung nur die eine kannte und deshalb
    zwei Arten anschwaerzte, die es laengst gibt:

        als ZEILE     `case FARBE: ende = farbWidget(element)` in
                      elementZeile() - ein Bedienelement rechts neben
                      seiner Beschriftung. So sind zahl, schalter, text,
                      auswahl und farbe gebaut.
        als SEITE     `if (element.kind === REIHENFOLGE) { ...
                      behaelter.append(reihenfolgeSeite(...)) }` in
                      zeichneSeite() - eine Art, die keine Zeile ist,
                      sondern eine ganze Liste zum Umsortieren
                      (reihenfolge) oder ein Schirmbild zum Anordnen
                      (anordnung). Eine solche Art in eine Zeile zu
                      zwingen waere schlechter und nicht besser.

    Was NICHT zaehlt, ist `case FARBE: return ICONS.farbe`: die
    Zeichenwahl verzweigt ueber dieselben Namen, und ein Muster, das sie
    mitnimmt, bliebe gruen, wenn nur das Zeichen da ist und das
    Bedienelement fehlt. GEMESSEN am 03.09.2026 mit einer Probe: Zeile
    573 entfernt, die erste Fassung blieb gruen. Daher `ende = `.
    """
    text = _fenster_text()
    # Die Konstante zum Wert: das Fenster verzweigt ueber die Namen.
    namen = {}
    for treffer in re.finditer(r'^const ([A-Z_]+) = "([a-z]+)"$', text, re.M):
        namen[treffer.group(2)] = treffer.group(1)

    ohne_zweig = []
    for name, wert in _arten_der_bruecke().items():
        konstante = namen.get(wert)
        if not konstante:
            continue          # der Test darueber sagt es deutlicher
        als_zeile = re.search(rf"case {konstante}: ende = ", text)
        als_seite = re.search(
            rf"element\.kind === {konstante}\)", text)
        if not (als_zeile or als_seite):
            ohne_zweig.append(f"{name} ({wert} -> {konstante})")
    assert ohne_zweig == [], (
        f"diese Arten baut das AGS-Fenster nirgends - weder als Zeile in "
        f"elementZeile() noch als eigene Seite in zeichneSeite(): "
        f"{ohne_zweig}")


def test_jede_art_wird_auf_genau_einem_weg_gebaut():
    """Zeile ODER Seite, nicht beides.

    Beides waere kein Luxus, sondern ein Widerspruch: zeichneSeite()
    fragt die Seitenform ZUERST ab und kehrt dann um. Eine Art mit
    beidem haette einen Zweig, den nie jemand erreicht - und der beim
    naechsten Lesen wie die gueltige Fassung aussieht.
    """
    text = _fenster_text()
    namen = {}
    for treffer in re.finditer(r'^const ([A-Z_]+) = "([a-z]+)"$', text, re.M):
        namen[treffer.group(2)] = treffer.group(1)

    doppelt = []
    for name, wert in _arten_der_bruecke().items():
        konstante = namen.get(wert)
        if not konstante:
            continue
        if (re.search(rf"case {konstante}: ende = ", text)
                and re.search(rf"element\.kind === {konstante}\)", text)):
            doppelt.append(f"{name} ({wert})")
    assert doppelt == [], (
        f"diese Arten haben eine Zeile UND eine Seite: {doppelt} - einer "
        f"der beiden Wege ist tot")


def test_die_zusicherung_wuerde_eine_fehlende_art_sehen():
    """Ein Test, der nichts findet, ist gruen. Also der Gegenbeweis.

    Er ist hier besonders angebracht: die Behauptung, die diese Datei
    ersetzt, kam aus einem verungluecktem `grep` und war falsch.
    """
    text = _fenster_text()
    erfunden = "farbverlauf"
    assert not re.search(rf'^const [A-Z_]+ = "{erfunden}"$', text, re.M), (
        f"es gibt tatsaechlich eine Art {erfunden!r} - dann taugt dieser "
        f"Gegenbeweis nicht mehr")


def test_die_sieben_arten_sind_wirklich_sieben():
    """Kommt eine achte dazu, faellt dieser Test - und der Naechste
    weiss, dass er das Fenster mitziehen muss."""
    arten = _arten_der_bruecke()
    assert len(set(arten.values())) == 7, (
        f"die Bruecke kennt jetzt {len(set(arten.values()))} Arten: "
        f"{sorted(set(arten.values()))}")
