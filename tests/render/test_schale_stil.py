# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Schale, gezeichnet und nachgemessen - nicht nur die Vorlage
gelesen.

WARUM ES DIESE DATEI GIBT
    2911 gruene Tests, und keiner davon hat je ein Ueberlagerungsfenster
    gezeichnet - GEMELDET am 19.08.2026, als der Nutzer die neue Schale
    (createShellWindow(), ags-overlay-utils.template) zum ersten Mal
    gesehen hat: "was das design angeht dort ist irgendwie alles
    verbuggt die sidebar macht ganz komische kaestchen und der innere
    inhalt laedt immer komisch ... es sieht mal so garnicht aus wie auf
    dem mockups es fehlt irgendwie mehr breite oder so", und dann: "hast
    du das design wirklich nie getestet mit der test suite".

    tests/render/test_geometry.py misst seit dem 12.08.2026 Leiste und
    Dock. Die Schale hatte bis heute KEIN Bild und KEINE Messung -
    tests/src/test_schale.py (18.08.2026) prueft nur, dass "208px" als
    ZEICHENKETTE im Stylesheet steht, nie, was daraus auf dem Schirm
    wird. Diese Datei ist die erste, die es tut.

WAS HIER GEMESSEN WIRD, UND WAS NICHT
    Vier Seiten der Schale (das Kontrollzentrum selbst - "general" -,
    Netzwerk, Bluetooth, VPN), bei 1920x1080, Vorgabegroesse. Gemessen
    wird an hyprctl (die tatsaechliche Layer-Shell-Flaeche, keine
    behauptete set_default_size()) und an Bildpunkten (measure.py) -
    dieselbe Methode wie test_geometry.py, aus demselben Grund: eine
    Zusicherung, die eine Vorlage liest, kann nicht sehen, was GTK am
    Ende daraus macht.

    NICHT geprueft: die "Kasten in Kasten"-Verschachtelung selbst - das
    ist Quelltext, nicht Geometrie, und steht darum in
    tests/src/test_kit_nesting.py. Diese Datei hier liefert nur die
    ZAHLEN dazu (wie hoch ein Seitenleisten-Eintrag WIRKLICH wird).

DER PREIS
    Ein verschachtelter Compositor je Testlauf (nicht je Testfall - alle
    Zusicherungen hier teilen sich EINE Sitzung, vier Seiten
    nacheinander), rund eine Minute. Siehe test_geometry.py fuer die
    Begruendung, warum das trotzdem billiger ist als eine falsche
    Gewissheit.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.render import measure                      # noqa: E402
from tests.render.desktop_session import (             # noqa: E402
    Session, bundle, render_configuration, required_tools, workspaces_file,
)

SETTLE = 6.0
POPOVER_SETTLE = 2.5

# Reihenfolge = Reihenfolge der Seitenleiste (VERBINDUNGEN vor SYSTEM,
# siehe ags-control-center.template). "general" zuerst, weil das
# Zahnrad in der Leiste genau dorthin oeffnet (startSeite: "general") -
# die Seite, die der Nutzer beim ersten Klick sieht.
SEITEN = (
    ("control", "general"),
    ("network", "network"),
    ("bluetooth", "bluetooth"),
    ("vpn", "vpn"),
)

# Die Sprosse, die die Schale fuer sich beansprucht - SHELL_WIDTH in
# ags-overlay-utils.template, wortgleich STYLE_MODAL_WIDTH_L. Direkt aus
# src/sizes.py gelesen und nicht abgeschrieben, aus demselben Grund wie
# size_of() in desktop_session.py: die Erwartung soll aus DERSELBEN
# Quelle kommen wie die erzeugte Datei.
def _modal_width_l() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    try:
        import sizes
        return sizes.MODAL_WIDTH("L")
    finally:
        sys.path.remove(str(ROOT / "src"))


# Die Sidebar-Breite steht als Literal in ags-style.template (.zep-
# sidebar, min-width: 208px) - NICHT hinter einem {{STYLE_*}}-Platz-
# halter und darum auch nicht ueber einen Skalierungsfaktor erreichbar.
# tests/src/test_schale.py haelt genau diese Zahl gegen den Quelltext;
# hier ist sie die Erwartung fuer das BILD.
SIDEBAR_BREITE_SOLL = 208


@pytest.fixture(scope="module")
def schale(tmp_path_factory):
    """Alle vier Seiten der Schale, einmal aufgenommen.

    Ein Wort-zu-Wert-Verzeichnis je Seite: die Layer-Shell-Flaeche laut
    hyprctl (x, y, b, h) und das entpackte Bild danach - derselbe Aufbau
    wie `gemalt` in test_geometry.py.
    """
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Bildlauf fehlt: {', '.join(fehlt)}")

    bau = tmp_path_factory.mktemp("zepschale-bau")
    bilder = tmp_path_factory.mktemp("zepschale-bild")
    ags = render_configuration(bau)
    bundle(ags, bau)

    ergebnis: dict[str, dict] = {}
    with Session(1920, 1080) as sitzung:
        sitzung.start_bus()
        workspaces_file(bau, sitzung.output)
        # Derselbe Grund wie in test_geometry.py: kein Hardware-Cursor
        # auf dem headless-Ausgang, der Compositor malt den Pfeil sonst
        # MIT in jedes Bild.
        ergebnis_cursor = sitzung.hyprctl("keyword", "cursor:invisible", "true")
        assert ergebnis_cursor.returncode == 0, (
            f"cursor:invisible liess sich nicht setzen: {ergebnis_cursor.stderr}")
        sitzung.wallpaper()
        sitzung.move_cursor(960, 540)
        time.sleep(2.0)
        vorher = measure.read_png(sitzung.shoot(bilder / "nur-tapete.png"))

        sitzung.shell(bau / "zepos-shell.js", bau)
        time.sleep(SETTLE)

        for anfrage, name in SEITEN:
            antwort = sitzung.request(anfrage)
            # GERUETTELT STATT EINMAL GEWARTET (derselbe Grundsatz wie
            # test_geometry.py bei test_der_zeigergrund_bleibt_in_der_
            # platte): eine feste Wartezeit ist entweder zu kurz oder zu
            # lang.
            #
            # DIESE HIER IST GROSSZUEGIG, WEIL DAS FENSTER MANCHMAL GAR
            # NICHT ERSCHEINT - GEMESSEN am 19.08.2026, an einem SAUBEREN
            # Arbeitsbaum (git worktree bei 942b543, ohne die
            # gleichzeitigen Aenderungen des zweiten Agenten - siehe
            # Bericht dieser Aufgabe): "ags request control" antwortet
            # zuverlaessig "toggled", aber die Flaeche 'control' bleibt
            # in einem Teil der Laeufe laenger als 20 Sekunden komplett
            # aus, waehrend Leiste, Dock und Tapete laengst stehen.
            #
            # DER VERDAECHTIGE, gefunden im mitgelieferten Protokoll
            # (`bauen/< -> show -> toggleWidget`, sitzung.read_shell_log()):
            # vpnSeite (ags-vpn.template, ~Zeile 848) haengt einen
            # `win.connect("notify::visible", ...)` an das FENSTER, das
            # es von bauen(win, schliessen) hereinbekommt - seit Aufgabe 9
            # (18.08.2026, "VPN als Seite") ist das nicht mehr sein
            # EIGENES Fenster, sondern das GEMEINSAME Fenster der Schale.
            # Der Rueckruf feuert darum bei JEDEM Oeffnen der Schale, egal
            # welche Seite gerade aktiv ist (kein `if (aktivId !==
            # "vpn") return`), liest user-settings.json neu und ruft am
            # Ende bedingungslos `usernameEntry.grab_focus()` bzw.
            # `passwordEntry.grab_focus()` - auf einem Eingabefeld der
            # VPN-Seite, selbst wenn "general" die gerade angezeigte
            # Seite ist und die VPN-Seite im Gtk.Stack gar nicht
            # sichtbar/realisiert ist. Ob GENAU das die Ursache ist
            # (Fokusanforderung auf ein unrealisiertes Widget waehrend
            # die Layer-Shell-Flaeche zum ersten Mal committet wird), ist
            # eine Lesart des Protokolls und keine Reparatur - dieser
            # Auftrag misst, er baut nicht um.
            #
            # 45s und OHNE einen zweiten "ags request": ein zweiter
            # Aufruf waere hier falsch, da GJS einstraengig ist - er
            # wuerde erst NACH dem ersten verarbeitet und knippste das
            # (falls es doch noch erscheint) gerade sichtbare Fenster
            # sofort wieder zu. Ein Waechter, der sein eigenes Messobjekt
            # wegklickt, ist schlimmer als einer, der lang wartet.
            deadline = time.monotonic() + 45.0
            platte = None
            while time.monotonic() < deadline:
                flaechen = sitzung.layers()
                platte = flaechen.get("control")
                if platte:
                    break
                time.sleep(0.3)
            assert platte, (
                f"'{name}': keine Flaeche 'control' auf dem Schirm nach "
                f"'ags request {anfrage}' (Antwort: {antwort!r}):\n"
                + sitzung.read_shell_log())

            # DIE ERSTE ANTWORT IST OFT EIN PLATZHALTER, UND SIE WURDE HIER
            # BIS ZUM 19.08.2026 STEHENGELASSEN, OBWOHL DAS BILD LAENGST
            # ETWAS ANDERES ZEIGT
            #
            #     GEMESSEN (Bericht dieser Aufgabe, zwei eigene Sonden
            #     ausserhalb des Baums): beim ALLERERSTEN "ags request" in
            #     einem frischen Prozess meldet hyprctl fuer 'control' fast
            #     immer zuerst eine reine Buchfuehrungs-Geometrie -
            #     GEMESSEN (0, 84, 200, 200) -, Millisekunden bevor die
            #     echte Flaeche committet. An GENAU dieser Stelle (0,84
            #     plus 5px Rand) ist im FERTIGEN Bild - egal wie lange
            #     spaeter geschossen - NICHTS gemalt: kein 200x200-Fenster,
            #     kein Ausschnitt davon, nur Tapete. Der Nutzer sieht dieses
            #     Fenster nie; nur hyprctl kennt es kurz.
            #
            #     Der alte Code oben brach die Warteschleife beim ERSTEN
            #     nicht-leeren Treffer ab (oft schon dieser Platzhalter,
            #     denn "ags request" selbst braucht ~40-50ms und der
            #     Platzhalter steht da schon), wartete danach
            #     POPOVER_SETTLE (2.5s) und schoss DANN erst das Bild - aber
            #     fragte "platte" fuer die Koordinaten nie erneut. Damit
            #     zeigte "bild" die laengst eingeschwungene, richtige
            #     Geometrie, waehrend "platte" (und jede Messung, die sich
            #     darauf stuetzt - Breite, Seitenleistengrenze,
            #     Zeilenhoehe) noch den Platzhalter oder eine andere
            #     Zwischengeometrie eines Seitenwechsels trug (dieselbe
            #     Racelage, aber irgendeine der 2-3 Zwischenwerte, die JEDER
            #     Seitenwechsel laut Bericht der vorigen Aufgabe durchlaeuft
            #     - nicht nur der allererste). Das war der ganze Grund fuer
            #     "general: 200 statt 880" UND fuer "auf diesen Seiten liess
            #     sich gar keine Grenze finden" auf allen vier Seiten
            #     gleichzeitig: eine Koordinate, die zum Bild nicht mehr
            #     passt, findet im Bild folgerichtig nichts oder das
            #     Falsche.
            #
            #     Die Reparatur: NACH dem Settle noch einmal fragen, direkt
            #     bevor das Bild entsteht - "platte" und "bild" stammen
            #     danach aus DEMSELBEN Moment. Der `or platte`-Rueckfall ist
            #     dieselbe Vorsicht wie beim urspruenglichen `assert
            #     platte` oben: sollte die Flaeche ausgerechnet in der einen
            #     hyprctl-Abfrage kurz nichts melden, bleibt der vorherige,
            #     schon bestaetigt nicht-leere Wert stehen, statt eine
            #     KeyError-Kaskade auszuloesen.
            time.sleep(POPOVER_SETTLE)
            platte = sitzung.layers().get("control") or platte
            bild = measure.read_png(sitzung.shoot(bilder / f"schale-{name}.png"))
            ergebnis[name] = {"platte": platte, "bild": bild, "antwort": antwort}
            # zu, bevor die naechste Seite angefragt wird - sonst zeigt
            # das naechste Bild zwei Seiten gleichzeitig, wenn eine
            # Anfrage zufaellig als Umschalter statt als "hin zu Seite X"
            # wirkt.
            sitzung.request(anfrage)
            time.sleep(1.0)

    return {"vorher": vorher, "seiten": ergebnis}


# DIE ZWEI FUNKTIONEN UNTEN ERSETZEN _sidebar_grenze() UND DIE
# HANDGEROLLTE randzeile()-SUCHE DER FRUEHEREN FASSUNG - BEIDE SUCHTEN
# NACH EINER RANDLINIE, UND GENAU DAS WAR DER FEHLER
#
#     GEMELDET (Aufgabenblatt dieser Aufgabe): beide frueheren Tests
#     beschrieben den KAPUTTEN Zustand als Sollzustand. Sie fanden ihre
#     Grenze/Zeilenhoehe ueber eine RANDLINIE - solange jeder
#     Seitenleisten-Eintrag ein zepButton("umrandet") um eine zepRow war
#     (die "Kasten in Kasten"-Wand, siehe tests/src/test_kit_nesting.py),
#     malte JEDE Zeile ihre EIGENE, immer sichtbare Umrandung, und der
#     Abstand zwischen zwei solchen Randlinien war eine robuste, viele
#     Bildpunkte breite Zeilenhoehe.
#
#     74008b5 (19.08.2026, "zepRow traegt ihre Klickbarkeit selbst - kein
#     zweiter Kasten mehr") hat genau das behoben: ein Eintrag ist seither
#     eine randlose Zeile, nur der AKTIVE traegt noch etwas Sichtbares -
#     einen linken Farbstreifen plus getoenten Grund (.zep-row.active,
#     ags-style.template). Die einzige verbliebene Randlinie im ganzen
#     Bild ist .zep-sidebar { border-right: 1px solid $border } - GENAU
#     EIN Bildpunkt breit (GEMESSEN, Bericht dieser Aufgabe: x_offset=209
#     traegt die Randfarbe, x_offset=210 ist schon wieder Hintergrund).
#     Ein Test, der einen Sprung "haelt fuenf Punkte lang" verlangt, kann
#     einen einzelnen Bildpunkt grundsaetzlich nie finden - nicht durch
#     Pech, sondern durch Konstruktion. Und zwischen zwei UNMARKIERTEN
#     Eintraegen gibt es seit 74008b5 ueberhaupt keine Randlinie mehr,
#     die REPARIERTE Seitenleiste beschreibt also exakt das Bild, das die
#     alten Zusicherungen als Fehlschlag gelesen haben.
#
# WAS STATTDESSEN GEMESSEN WIRD
#     Der AKTIVE Eintrag ist auf JEDER der vier gemessenen Seiten
#     vorhanden (die eigene Seite ist immer markiert) und seine
#     Hervorhebung ist keine duenne Linie, sondern eine FLAECHE: 74
#     Bildpunkte hoch und praktisch die ganze Spaltenbreite breit
#     (GEMESSEN, alle vier Seiten, Bericht dieser Aufgabe). Eine Flaeche
#     dieser Groesse haelt einen Schwellenwert-Sprung locker ueber viele
#     Bildpunkte - genau die Eigenschaft, die der alten Suche fehlte.
#     _aktive_zeile() findet ihre Ober-/Unterkante (die Zeilenhoehe der
#     zweiten Zusicherung), _spaltengrenze() ihre rechte Kante (die
#     Spaltenbreite der ersten).
_AKTIV_X_VERSATZ = 50  # GEMESSEN: liegt auf allen vier Seiten sicher
                       # innerhalb des Zeilengrundes, rechts vom Symbol
                       # (Symbole liegen bei x_offset 22-38).
_HALT_PUNKTE = 24      # AUFGABE 19 (19.08.2026): war 37 (STYLE_ROW_HEIGHT
                       # 74 // 2), bevor zepSidebar() auf
                       # STYLE_NAV_ROW_HEIGHT umstellte - siehe dort in
                       # sizes.py. Neu STYLE_NAV_ROW_HEIGHT (49) // 2,
                       # kaufmaennisch abgerundet auf 24: klar ueber jedem
                       # Buchstaben-/Symbol-Ausschlag (GEMESSEN hoechstens
                       # 6 Bildpunkte lang), klar unter der echten
                       # Hervorhebung (GEMESSEN 49 Punkte auf allen vier
                       # Seiten).
_SCHWELLE = 15         # GEMESSEN (Bericht dieser Aufgabe): zwischen zwei
                       # BENACHBARTEN Eintraegen blutet der Weichzeichner
                       # ein paar Bildpunkte lang mit einem Sprung von
                       # ~10-11 ueber - eine Schwelle von 10 (wie in der
                       # alten Fassung) reisst diese Unschaerfe mit in
                       # den Lauf und misst dadurch bis zu 8px zu viel
                       # Zeilenhoehe. 15 liegt klar darueber und klar
                       # unter dem echten Sprung in die Hervorhebung
                       # (mindestens 28 auf allen vier Seiten).


def _aktive_zeile(bild: measure.Image,
                  platte: tuple[int, int, int, int]) -> tuple[int, int] | None:
    """Ober- und Unterkante (relativ zur Fensteroberkante) des einen
    Seitenleisten-Eintrags, der gerade als "aktiv" markiert ist -
    gefunden ueber seine Hervorhebungsflaeche, nicht ueber eine Randlinie
    (siehe der Blattkopf oben).

    Beginnt bei y_platte+85 (sicher unterhalb des Fensterkopfs, sicher
    oberhalb jeder Gruppenmarke - GEMESSEN: die Kopfzeile endet bei
    Versatz 77, "CONNECTIONS"/"SYSTEM" beginnt fruehestens bei 118) und
    sucht den ERSTEN Lauf abweichender Farbe, der mindestens
    _HALT_PUNKTE lang haelt.
    """
    x = platte[0] + _AKTIV_X_VERSATZ
    y_start = platte[1] + 85
    y_ende = platte[1] + platte[3] - 5
    basis = bild.at(x, y_start)[:3]

    lauf_start = None
    for y in range(y_start, y_ende):
        anders = max(abs(a - b) for a, b in
                    zip(bild.at(x, y)[:3], basis)) > _SCHWELLE
        if anders and lauf_start is None:
            lauf_start = y
        elif not anders and lauf_start is not None:
            if y - lauf_start >= _HALT_PUNKTE:
                return (lauf_start - platte[1], y - platte[1])
            lauf_start = None
    return None


def _spaltengrenze(bild: measure.Image, platte: tuple[int, int, int, int],
                   y_mitte_abs: int) -> int | None:
    """Die x-Spalte, an der die Hervorhebung des aktiven Eintrags aufhoert
    - die rechte Kante der Seitenleiste, gemessen an der Flaeche selbst
    statt an ihrer 1px-Randlinie (siehe der Blattkopf oben).

    `y_mitte_abs` ist die Mitte der Zeile, die _aktive_zeile() gefunden
    hat - garantiert innerhalb der Hervorhebung, nicht daneben.

    -1 AM ENDE: platte[0] ist die AEUSSERE Fensterkante, und die traegt
    selbst einen 1px-Rand (.overlay-outer { border: 1px solid $border }).
    Der erste Bildpunkt DAHINTER (Versatz 1) ist der Beginn von
    .zep-sidebar - eine Spaltenbreite wird also von DORT gezaehlt, nicht
    von der Fensterkante. GEMESSEN (Bericht dieser Aufgabe): ohne diesen
    Abzug landet die Messung bei 209, nicht bei den 208px, die
    .zep-sidebar in ags-style.template als min-width traegt.
    """
    x_start = platte[0] + _AKTIV_X_VERSATZ
    basis = bild.at(x_start, y_mitte_abs)[:3]

    lauf_start = None
    for i in range(0, 260 - _AKTIV_X_VERSATZ):
        x = x_start + i
        anders = max(abs(a - b) for a, b in
                    zip(bild.at(x, y_mitte_abs)[:3], basis)) > _SCHWELLE
        if anders and lauf_start is None:
            lauf_start = x
        elif not anders and lauf_start is not None:
            lauf_start = None
        if anders and lauf_start is not None and x - lauf_start >= _HALT_PUNKTE:
            return lauf_start - platte[0] - 1
    return None


def test_alle_vier_seiten_haben_dieselbe_flaeche_control(schale):
    """Die Schale ist EIN Fenster mit vier Seiten, nicht vier Fenster -
    trivial, wenn createShellWindow() haelt, aber die billigste
    Zusicherung dieser Datei und darum zuerst."""
    for name, info in schale["seiten"].items():
        assert info["platte"], f"Seite {name!r} meldet keine Flaeche"


def test_die_schale_haelt_ihre_breite_ueber_die_seiten(schale):
    """"es fehlt irgendwie mehr breite oder so" - gemeldet am
    19.08.2026, ueber genau die drei Seiten, die dieser Test misst.

    ShellConfig setzt SHELL_WIDTH (= STYLE_MODAL_WIDTH_L, 880) EINMAL
    fuer alle Seiten (ags-overlay-utils.template) - aber die Fabrik
    (createOverlayWindow) laesst den Inhalt ueber eine Gtk.ScrolledWindow
    mit propagate_natural_width laufen, und ein Gtk.Window wird nie
    breiter, als sein Inhalt es verlangt. 880 ist damit ein WUNSCH, kein
    Versprechen (das steht so im Kommentar bei SHELL_WIDTH) - dieser
    Test misst, ob der Wunsch bei den drei Verbindungsseiten ankommt.
    """
    soll = _modal_width_l()
    breiten = {name: info["platte"][2] for name, info in schale["seiten"].items()}

    abweichungen = {name: soll - breite for name, breite in breiten.items()
                    if breite != soll}
    assert not abweichungen, (
        f"SHELL_WIDTH ist {soll}px, aber gemessen: {breiten}. Es fehlen "
        + ", ".join(f"{name}: {diff}px" for name, diff in
                    sorted(abweichungen.items(), key=lambda kv: -kv[1]))
        + " - die Schale springt beim Seitenwechsel in der Breite, und "
        "keine der drei Verbindungsseiten (genau die, ueber die zuerst "
        "geklagt wurde) erreicht die Sprosse, fuer die sie gebaut ist.")


def test_die_seitenleiste_bemalt_208_punkte(schale):
    """Die Zahl aus .zep-sidebar (ags-style.template), am Bild
    nachgemessen statt im Quelltext gelesen - tests/src/test_schale.py
    prueft nur die Zeichenkette "208px", nicht was GTK daraus macht.

    Gemessen auf JEDER der vier Seiten (der Wert darf nicht von der
    aktiven Seite abhaengen) - ueber die Hervorhebung des jeweils
    AKTIVEN Eintrags (siehe der Blattkopf ueber _aktive_zeile()/
    _spaltengrenze()), nicht mehr ueber eine Randlinie zwischen zwei
    Eintraegen, die es seit 74008b5 nicht mehr gibt.

    TOLERANZ VON 1 PUNKT, UND SIE IST GEMESSEN, NICHT GERATEN
        Die rechte Kante der Hervorhebung liegt GENAU auf der 1px
        Randlinie von .zep-sidebar (border-right) - derselbe Bildpunkt
        traegt beides. Ob DIESER eine Bildpunkt (halb Hervorhebungs-,
        halb Randfarbe durch Antialiasing) die Schwelle _SCHWELLE
        ueberschreitet, haengt vom exakten Farbmix ab: GEMESSEN (Bericht
        dieser Aufgabe, alle vier Seiten desselben Laufs) ergab general/
        network/bluetooth exakt 208, vpn 209 - derselbe Sachverhalt, ein
        Bildpunkt anders gerundet. Eine Zusicherung, die diesen einen
        Bildpunkt nicht zulaesst, verwechselt Rundung mit einem Fehler.
    """
    ergebnisse: dict[str, int | None] = {}
    for name, info in schale["seiten"].items():
        zeile = _aktive_zeile(info["bild"], info["platte"])
        if zeile is None:
            ergebnisse[name] = None
            continue
        oben, unten = zeile
        y_mitte_abs = info["platte"][1] + (oben + unten) // 2
        ergebnisse[name] = _spaltengrenze(info["bild"], info["platte"], y_mitte_abs)

    fehlend = {name: grenze for name, grenze in ergebnisse.items()
              if grenze is None}
    assert not fehlend, (
        f"auf diesen Seiten liess sich die Hervorhebung des aktiven "
        f"Eintrags gar nicht finden: {sorted(fehlend)} - siehe die "
        "Bilder aus dieser Aufgabe")

    falsch = {name: grenze for name, grenze in ergebnisse.items()
             if abs(grenze - SIDEBAR_BREITE_SOLL) > 1}
    assert not falsch, (
        f"die Seitenleiste soll {SIDEBAR_BREITE_SOLL}px breit bemalen "
        f"(.zep-sidebar, ags-style.template), gemessen: {falsch}")


def test_ein_seitenleisten_eintrag_ist_nicht_die_knopfhoehe_hoch(schale):
    """UMGESCHRIEBEN am 19.08.2026 (Aufgabe 19). GEMELDET: "die sidebar
    items nav links sind viel zu hoch und nicht zu gebaut". zepSidebar()
    baute ihre Eintraege bis dahin aus zepRow OHNE Modifikator und bekam
    darum STYLE_ROW_HEIGHT (74px) - die Hoehe einer INHALTSKARTE, nicht
    eines einzeiligen Navigationseintrags. zepRow traegt seither die
    Option `navEintrag` (ags-kit.template), zepSidebar setzt sie, und die
    Zeile bekommt STYLE_NAV_ROW_HEIGHT statt STYLE_ROW_HEIGHT - siehe die
    Herleitung dort in src/sizes.py.

    DIESE ZUSICHERUNG HIESS URSPRUENGLICH ANDERS UND PRUEFTE ETWAS
    ANDERES, UND DAS IST HIER OFFEN AUFGESCHRIEBEN, NICHT STILL GEAENDERT
        Sie verglich bis hierher gegen STYLE_ROW_HEIGHT (74px) und
        verlangte ZUSAETZLICH `eintrag_hoehe != STYLE_CONTROL_HEIGHT`,
        um die "Kasten in Kasten"-Regression zu fangen: zepButton als
        aeussere Huelle traegt keine senkrechte Polsterung, ein
        Rueckfall auf diese Huelle haette die Zeile also auf
        Knopfhoehe (49px) zusammenfallen lassen. GEMESSEN mit der neuen
        Sprosse: STYLE_NAV_ROW_HEIGHT ist bei Vorgabegroesse EBENFALLS
        49px - dieselbe Zahl wie STYLE_CONTROL_HEIGHT, aus derselben
        Rechnung (Zeileninhalt + 2x SPACE_8), aber unabhaengig benannt
        (siehe der Kommentar bei STYLE_NAV_ROW_HEIGHT). Ein `!=`-Vergleich
        gegen die Knopfhoehe koennte damit nie mehr etwas finden - er
        WUERDE JETZT IMMER FEHLSCHLAGEN, ohne dass ein Fehler vorliegt.
        Die eigentliche Kasten-in-Kasten-Regression bleibt bewacht: auf
        Quelltextebene durch tests/src/test_kit_nesting.py (unveraendert),
        und auf Bildebene dadurch, dass diese Zusicherung weiterhin genau
        EINEN erwarteten Wert verlangt (STYLE_NAV_ROW_HEIGHT) statt eines
        Bereichs - eine zurueckgekehrte Knopfhuelle mit eigener
        Mindesthoehe wuerde die Zeile wieder ueber diesen Wert heben.

    GEMESSEN UEBER DIE HERVORHEBUNG, NICHT MEHR UEBER RANDLINIEN
        Die fruehere Fassung suchte den Abstand zwischen zwei
        "vollstaendig randfarbenen" Zeilen - ein Muster, das es seit
        74008b5 nur noch an der AEUSSEREN Fensterplatte gibt (Kopf- und
        Fussrand), nicht mehr zwischen zwei Eintraegen. GEMESSEN, mit dem
        alten Code gegen den REPARIERTEN Baum: die einzigen beiden
        "Randzeilen", die er fand, waren der untere Rand des
        Fensterkopfs (y=77) und die UNTERKANTE DER GANZEN PLATTE
        (y=539, praktisch hoehe_platte) - macht 462px "Zeilenhoehe",
        offensichtlich kein einzelner Eintrag.
        _aktive_zeile() misst stattdessen die Ausdehnung der
        Hervorhebungsflaeche des aktiven Eintrags direkt - dieselbe
        Flaeche, mit der test_die_seitenleiste_bemalt_208_punkte oben
        auch die Spaltenbreite findet.

    Gemessen auf "general" (wie vorher) - der aktive Eintrag ist dort
    "Control", per Messung dieser Aufgabe 49 Bildpunkte hoch, mit
    derselben 1-Punkt-Toleranz wie oben.
    """
    # NICHT size_of() aus desktop_session.py: das dortige int(...) setzt
    # voraus, dass value_of() OHNE Einheit zurueckkommt (BARE) - fuer
    # STYLE_NAV_ROW_HEIGHT (PX, siehe TABLE in src/sizes.py) haengt
    # value_of() ein "px" an, und int("49px") wirft. GEMESSEN am
    # 19.08.2026 beim ersten Lauf dieser Datei.
    def _px(name: str) -> int:
        sys.path.insert(0, str(ROOT / "src"))
        try:
            import sizes
            return int(sizes.value_of(name, {}).removesuffix("px"))
        finally:
            sys.path.remove(str(ROOT / "src"))

    zeilenhoehe = _px("STYLE_NAV_ROW_HEIGHT")

    info = schale["seiten"]["general"]
    zeile = _aktive_zeile(info["bild"], info["platte"])
    assert zeile is not None, (
        "auf 'general' liess sich die Hervorhebung des aktiven Eintrags "
        "('Control') nicht finden - siehe schale-general.png dieser "
        "Aufgabe")

    oben, unten = zeile
    eintrag_hoehe = unten - oben
    assert abs(eintrag_hoehe - zeilenhoehe) <= 1, (
        f"der aktive Eintrag der Seitenleiste ('Control') ist "
        f"{eintrag_hoehe}px hoch (gemessen zwischen y={oben} und y={unten}, "
        f"bezogen auf die Fensteroberkante), erwartet wird "
        f"STYLE_NAV_ROW_HEIGHT={zeilenhoehe}px.")
