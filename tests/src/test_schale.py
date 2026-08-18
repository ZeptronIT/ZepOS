# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Schale - Seitenleiste und Zustandskopf kommen aus dem Kit.

Derselbe Ansatz wie test_button_kit.py: geprueft wird die VORLAGE, nicht
ein laufendes AGS. Ein Fenster, das sich seine Seitenleiste selbst baut,
faellt hier auf, solange es billig ist.
"""
import re
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[2]
KIT = WURZEL / "src" / "templates" / "ags-kit.template"
STIL = WURZEL / "src" / "templates" / "ags-style.template"


def test_das_kit_liefert_die_beiden_schalen_bauteile():
    """Die Schale braucht ZWEI neue Bauteile, nicht drei.

    Hier stand "die_drei_bauteile", und das war eine Ungenauigkeit im
    Plan vom 18.08.2026: die Eintraege der Seitenleiste sind keine
    eigene Form, sie sind `zepRow` mit `ausgewaehlt` - das Bauteil gibt
    es seit demselben Tag, und es deckelt bereits die natuerliche
    Breite von Fremdtexten. Eine dritte Zeilenform danebenzustellen
    waere genau die Doppelung, die dieses Vorhaben in sieben Auftraegen
    fuer Knoepfe abgeraeumt hat.
    """
    text = KIT.read_text(encoding="utf-8")
    for name in ("zepSidebar", "zepStateHeader"):
        assert f"export function {name}" in text, f"{name} fehlt im Kit"


def test_die_seitenleiste_ist_208_breit():
    # Die Zahl steht in der Spezifikation, Abschnitt 2.2, und sie ist
    # der einzige Ort, an dem sie stehen darf.
    text = STIL.read_text(encoding="utf-8")
    block = re.search(r"\.zep-sidebar\s*\{[^}]*\}", text, re.S)
    assert block, ".zep-sidebar fehlt im Stylesheet"
    assert "208px" in block.group(0)


def test_kein_fenster_baut_sich_eine_eigene_seitenleiste():
    # Wer eine Navigationsspalte braucht, ruft zepSidebar auf. Eine
    # zweite Antwort auf dieselbe Frage ist der Fehler, den dieses
    # Vorhaben gerade fuer Knoepfe abgeraeumt hat.
    #
    # WORAUF DIESER AUSDRUCK ZIELT, UND WARUM NICHT AUF class="..."
    #     GEMESSEN am 18.08.2026: die AGS-Vorlagen setzen ihre Klassen
    #     ueber add_css_class("...") und cssClass:/cssClasses: - ein
    #     class="..."-Attribut kommt in keiner einzigen von ihnen vor.
    #     Ein Waechter, der darauf zielt, behauptet nichts.
    verboten = re.compile(
        r"(?:add_css_class\s*\(\s*|cssClass(?:es)?\s*:\s*\[?\s*)"
        r"[\"'`][^\"'`]*(?:sidebar|nav-col|side-nav)")
    for vorlage in (WURZEL / "src" / "templates").glob("ags-*.template"):
        if vorlage.name == "ags-kit.template":
            continue
        text = vorlage.read_text(encoding="utf-8")
        assert not verboten.search(text), (
            f"{vorlage.name} baut sich eine eigene Seitenleiste")


def test_dieser_waechter_wuerde_ueberhaupt_ausloesen():
    # Ein Waechter, der nie ausloest, ist kein Waechter. Der Ausdruck
    # oben wird hier einmal gegen eine Zeile gehalten, die genau so in
    # einer Vorlage stehen wuerde, wenn sich jemand eine eigene
    # Seitenleiste baut.
    verboten = re.compile(
        r"(?:add_css_class\s*\(\s*|cssClass(?:es)?\s*:\s*\[?\s*)"
        r"[\"'`][^\"'`]*(?:sidebar|nav-col|side-nav)")
    assert verboten.search('spalte.add_css_class("cc-sidebar")')
    assert verboten.search('  cssClass: "net-side-nav",')
    assert not verboten.search('const sidebarBreite = 208')


def test_kein_ags_fenster_baut_sich_ein_gtk_window():
    """Auf Wayland ist ein Gtk.Window keine Layer-Shell-Flaeche.

    GEMESSEN am 18.08.2026: ags-wallpaper.template baute sein
    Loeschbestaetigung als blankes Gtk.Window. Es bekam damit Hyprlands
    Fensterregeln statt der Glasregeln, stand nicht ueber der Leiste, und
    die Rundung dieses Vorhabens ging daran vorbei.

    Astal.Window ist erlaubt - das ist die Layer-Shell-Klasse. Verboten
    ist nur der xdg-toplevel-Weg.
    """
    for vorlage in (WURZEL / "src" / "templates").glob("ags-*.template"):
        text = vorlage.read_text(encoding="utf-8")
        treffer = re.findall(r"new\s+Gtk\.Window\b", text)
        assert not treffer, (
            f"{vorlage.name} baut ein Gtk.Window - auf Wayland ist das "
            f"keine Layer-Shell-Flaeche")
