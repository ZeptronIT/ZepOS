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


# DIE FLAECHEN DER SCHALE - die Inhaltskaesten NEBEN der Seitenleiste.
#
# NACHGETRAGEN am 20.08.2026 (Aufgabe 49), weil der Nutzer den fehlenden
# Abstand dort ZWEIMAL melden musste: "der außen abstand, das hast du
# immernoch nicht verändert in dem sidebar mit inner content ags
# fenster", und danach "die abstände in dem inner content neben der
# sidebar, das custom ags fenster was wir gemacht haben, sind auch nicht
# richtig". Beim dritten Mal soll ein Test es vorher sagen.
#
# GEMESSEN am 20.08.2026 am Bild (tests/render/, schale-*.png, Fenster
# 880x430), VOR der Reparatur - vier Seiten, drei verschiedene
# Antworten, zwei davon "gar keine":
#
#     bluetooth  0/0     network  0/0     general  18/18     vpn  25/25
#
# Die Erwartung kommt aus dem Musterblatt ("Die Schale", 19.08.2026, vom
# Nutzer bestaetigt mit "genau so soll das aussehen"): `.flaeche {
# padding: 18px 25px }` - und 18/25 sind SPACE_12/SPACE_16 der
# Abstandsleiter aus src/sizes.py, nicht zwei getippte Zahlen.
_FLAECHEN = (
    # Die eine Regel, die Bluetooth, Netzwerk, Kontrolle, Ton und Anzeige
    # seit dem 20.08.2026 teilen.
    ".zep-shell-flaeche",
    # Die VPN-Seite und das Einstellungsfenster tragen ihre Flaeche noch
    # unter dem eigenen alten Namen - dieselbe Rolle, dieselben zwei
    # Sprossen, und darum stehen sie hier daneben statt darunter.
    ".vpn-container",
    ".set-container",
)


def test_jede_flaeche_der_schale_polstert_auf_denselben_zwei_sprossen():
    """Der Inhalt neben der Seitenleiste haelt 18/25 - auf JEDER Seite.

    Waagerecht SPACE_16, senkrecht SPACE_12, und beide als Platzhalter
    und nicht als Zahl: eine Flaeche, die dem Groessenregler nicht folgt,
    steht bei der naechsten Einstellung wieder falsch da.
    """
    text = STIL.read_text(encoding="utf-8")
    for name in _FLAECHEN:
        block = re.search(rf"^{re.escape(name)}\s*\{{(.*?)^\}}",
                          text, re.M | re.S)
        assert block, f"{name} fehlt im Stylesheet"
        polster = re.search(r"^\s*padding:\s*([^;]+);", block.group(1), re.M)
        assert polster, f"{name} traegt keine Polsterung"
        assert polster.group(1).strip() == "{{STYLE_SPACE_12}} {{STYLE_SPACE_16}}", (
            f"{name} polstert mit {polster.group(1).strip()!r} statt mit den "
            "zwei Sprossen des Musterblatts (18/25 = SPACE_12/SPACE_16)")


def test_keine_seite_der_schale_gibt_ihren_inhalt_ohne_flaeche_heraus():
    """Wer eine Seite baut, gibt sie gepolstert zurueck.

    GEMESSEN, warum dieser Waechter noetig ist: ags-bluetooth.template
    und ags-network.template lieferten ihre Seite bis zum 20.08.2026 als
    nackte Gtk.Box ohne eine einzige Klasse aus - der Inhalt klebte
    dadurch an der Trennlinie der Seitenleiste und an der rechten
    Fensterkante. Eine Seite ohne Flaechenklasse faellt hier auf, bevor
    sie jemand sieht.
    """
    kaesten = tuple(name.lstrip(".") for name in _FLAECHEN)
    # Eine DEKLARATION und kein blosses Vorkommen des Wortes: mehrere
    # Vorlagen erwaehnen "ShellSeite" nur in ihrem Kopfkommentar
    # (ags-config.template etwa erklaert dort die Umstellung), ohne selbst
    # je eine Seite zu bauen. `(?!>)` haelt die Rueckgabetypen der Fabrik
    # heraus - `(id: string): ShellSeite => {` in ags-overlay-utils.
    # template BAUT keine Seite, es sucht eine heraus.
    baut_eine_seite = re.compile(r":\s*ShellSeite(?:\[\])?\s*=(?!>)")
    gepruefte = 0
    for vorlage in sorted((WURZEL / "src" / "templates").glob("ags-*.template")):
        text = vorlage.read_text(encoding="utf-8")
        if not baut_eine_seite.search(text):
            continue
        gepruefte += 1
        assert any(f'add_css_class("{kasten}")' in text for kasten in kaesten), (
            f"{vorlage.name} baut Seiten fuer die Schale, nennt aber keinen "
            f"der gepolsterten Inhaltskaesten {kaesten}")
    # GEMESSEN am 20.08.2026: fuenf Vorlagen deklarieren eine ShellSeite -
    # Bluetooth, Netzwerk, VPN, das Kontrollzentrum (drei Seiten) und die
    # Einstellungen. Faellt eine davon aus der Suche, prueft die Schleife
    # oben weniger, als ihr Name verspricht, und sagt nichts dazu.
    assert gepruefte == 5, (
        f"nur {gepruefte} Vorlagen mit einer ShellSeite-Deklaration gefunden, "
        "erwartet 5 - der Ausdruck findet nicht mehr, was er finden soll")


def test_dieser_flaechen_waechter_wuerde_ueberhaupt_ausloesen():
    """Der Ausdruck oben findet eine Polsterung, die nicht auf den zwei
    Sprossen sitzt - sonst haelt er nichts fest, sondern schweigt nur."""
    text = ".zep-probe {\n  padding: 20px;\n}\n"
    block = re.search(r"^\.zep-probe\s*\{(.*?)^\}", text, re.M | re.S)
    assert block
    polster = re.search(r"^\s*padding:\s*([^;]+);", block.group(1), re.M)
    assert polster and polster.group(1).strip() != (
        "{{STYLE_SPACE_12}} {{STYLE_SPACE_16}}")


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
