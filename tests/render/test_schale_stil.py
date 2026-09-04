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

WARUM DIESE DATEI ECHTE PROZESSE STARTEN DARF
    Ihr Gegenstand ist das GEZEICHNETE Fenster und nicht die Vorlage,
    die es beschreibt. Ein Bild davon entsteht nur, wenn ein Compositor
    es wirklich malt: gestartet werden darum ein verschachteltes
    Hyprland, ein Bus, `ags bundle` und die erzeugte Oberflaeche. Genau
    das ist der Grund, aus dem diese Datei ueberhaupt existiert (siehe
    oben: 2911 gruene Tests, von denen keiner je ein Fenster gezeichnet
    hatte) - eine Fassung ohne echte Prozesse koennte nur wieder die
    Vorlage lesen, also gerade das, was hier NICHT geprueft werden soll.

    Die Sitzung des Nutzers bleibt dabei unberuehrt: eigener
    HYPRLAND_INSTANCE_SIGNATURE, eigener headless-Ausgang, alles unter
    einem Baum von tmp_path_factory (siehe desktop_session.Session).

    `pytestmark` UND NICHT EIN MARKER JE LAUF, und das ist gemessen und
    nicht Geschmack: die Sitzung entsteht in einer MODULWEITEN
    Vorrichtung, und pytest speichert den Fehlschlag einer Vorrichtung
    zwischen. Eine Freigabe je Lauf waere damit reihenfolgeabhaengig -
    laeuft ein unmarkierter Lauf zuerst, faellt auch der markierte. Auf
    Modulebene ist es in jeder Reihenfolge gruen.
"""
from __future__ import annotations

import re
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

pytestmark = pytest.mark.allow_subprocess

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


# Die Sidebar-Breite ist das GESCHUETZTE Ziel (tests/src/test_schale.py
# haelt "208px" als Zeichenkette gegen den Quelltext), aber seit Aufgabe
# 27 (19.08.2026, Musterblatt "Die Schale") keine simple Literal-Regel
# mehr: .zep-sidebar traegt jetzt `padding: {{STYLE_SPACE_8}}` UND
# `min-width: 208px - (2 * {{STYLE_SPACE_8}})` - die Polsterung, die dem
# Nutzer fehlte ("die sidebar hat kein außen padding da fehlt so viel"),
# minus zweimal herausgerechnet, damit die SUMME bei jedem sizes.scale
# wieder 208 ergibt (siehe der Kommentar dort: "GTK rechnet Polster
# IMMER oben auf eine gesetzte min-width drauf"). Die 208 hier bleibt
# darum weiterhin die Erwartung fuer die GESAMTE Spaltenbreite.
SIDEBAR_BREITE_SOLL = 208


# Wieviel Sass STYLE_SPACE_8 bei DIESEM Lauf ausrechnet - dieselbe
# Sprosse, die .zep-sidebar (Polsterung) und .zep-row-nav (Polsterung +
# Symbolabstand) jetzt teilen. Ueber sizes.value_of() und nicht
# abgeschrieben, aus demselben Grund wie _modal_width_l() oben: die
# Erwartung soll aus DERSELBEN Quelle kommen wie die erzeugte Datei, bei
# JEDEM sizes.scale, nicht nur beim ausgelieferten Faktor.
def _px(name: str) -> int:
    sys.path.insert(0, str(ROOT / "src"))
    try:
        import sizes
        return int(sizes.value_of(name, {}).removesuffix("px"))
    finally:
        sys.path.remove(str(ROOT / "src"))


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
        # AUF DIE RUHE UND NICHT AUF DIE UHR - seit dem 04.09.2026.
        # Hier stand ein fester Schlaf. Warum "die Flaeche ist da"
        # dafuer nicht reicht - und mit welchen Zahlen das gemessen
        # ist - steht bei Session.warte_auf_ruhe().
        sitzung.warte_auf_ruhe("zepos-bar", "zepos-dock",
                               frist=40.0)

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

        # NACHGETRAGEN am 19.08.2026 (Aufgabe 23). GELESEN, SOLANGE DIE
        # SITZUNG NOCH STEHT: Session.__exit__ (stop()) raeumt
        # self.runtime per shutil.rmtree ab, und shell_log liegt DARIN -
        # ausserhalb dieses `with`-Blocks gelesen waere die Datei schon
        # weg. createOverlayWindow() (ags-overlay-utils.template,
        # notify::upper, Aufgabe 19/d766b7a) schreibt genau dann eine
        # Zeile, wenn eine Seite mehr Breite verlangt, als das Fenster
        # ihr laesst - derselbe Fall, unter dem Gtk.PolicyType.AUTOMATIC
        # ueberhaupt erst eine waagerechte Bildlaufleiste einblendet
        # (siehe der Kommentar dort). Der volle Log ueber alle vier
        # Seiten hinweg ist damit ein direkter Nachweis "Leiste
        # sichtbar" bzw. ihr Fehlen ein Nachweis "keine Leiste".
        schalen_log = sitzung.read_shell_log()

    return {"vorher": vorher, "seiten": ergebnis, "schalen_log": schalen_log}


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


# DIE WAAGERECHTE SUCHE BRAUCHT EINE EIGENE HALTELAENGE, UND DAS IST DER
# GRUND, WARUM DIESE DATEI AM 02.09.2026 EIN ZWEITES MAL AM MESSGERAET
# REPARIERT WURDE
#
#     747e68d (01.09.2026) hat die Y-HALFTE der Messung geradegezogen:
#     gemessen wird seither dicht unter der Oberkante der Zeile, oberhalb
#     der Glyphen. Danach meldete _spaltengrenze() auf allen vier Seiten
#     stabil 209 statt der erwarteten 196, und das sah nach einem
#     Rueckfall der Polsterung aus. Es war der REST DESSELBEN
#     MESSFEHLERS, eine Ebene tiefer.
#
#     _HALT_PUNKTE ist aus der ZEILENHOEHE abgeleitet
#     (STYLE_NAV_ROW_HEIGHT 49 // 2 = 24) und war fuer die SENKRECHTE
#     Suche gedacht, die eine 49 Punkte hohe Flaeche findet. Waagerecht
#     sucht dieselbe Zahl aber nach dem Streifen NEBEN der Hervorhebung,
#     und der ist genau so breit wie die Polsterung, um die es geht -
#     STYLE_SPACE_8, bei Vorgabegroesse 12 Punkte. Ein Lauf, der 24
#     Punkte halten muss, passt in einen 12 Punkte breiten Streifen
#     grundsaetzlich nicht hinein: nicht durch Pech, sondern durch
#     Konstruktion - dieselbe Sorte Fehler, die der Blattkopf oben schon
#     einmal fuer die 1px-Randlinie aufgeschrieben hat.
#
#     Die Suche lief deshalb ueber die Polsterung hinweg. Der eine
#     Bildpunkt der Randlinie von .zep-sidebar setzte sie zusaetzlich
#     zurueck: GEMESSEN am 02.09.2026, Rand (33,79,89) gegen
#     Hervorhebung (18,78,91), Abstand GENAU 15 - und die Bedingung
#     lautet `> _SCHWELLE`, also gilt der Rand als "gleich" und bricht
#     den Lauf. Gefunden wurde am Ende die Flaeche HINTER der
#     Seitenleiste, deren linke Kante bei Versatz 210 liegt: 210 - 1 =
#     209.
#
#     GEMESSEN, an den Bildern desselben Laufs, waagerecht durch die
#     aktive Zeile (Versatz: Farbe), alle vier Seiten gleich aufgebaut:
#
#         0-0     (33,79,89)   Rand der Platte (.overlay-outer)
#         1-12    (10,43,49)   Polsterung von .zep-sidebar   <- 12 = SPACE_8
#         13-196  (18,78,91)   die Hervorhebung              <- 184 = 208-2*12
#         197-208 (10,43,49)   Polsterung von .zep-sidebar   <- 12 = SPACE_8
#         209-209 (33,79,89)   border-right von .zep-sidebar
#         210-    Seite
#
#     Die Polsterung wirkt also, und die rechte Kante der Hervorhebung
#     liegt bei 196 - genau auf der Erwartung, die dieser Test seit
#     Aufgabe 27 traegt. 196 ist NICHT angefasst worden.
#
# WARUM DIE HAELFTE DER SPROSSE UND KEINE GETIPPTE ZAHL
#     Durchgerechnet ueber alle Haltelaengen von 1 bis 24, an den vier
#     Bildern (Bericht dieser Aufgabe): 1 bis 11 ergeben 196, ab 12
#     ergeben alle 209. Die Kippstelle ist die Breite der Polsterung
#     selbst. Die Haelfte davon (6) liegt klar ueber der einzigen
#     Unschaerfe, die es dort gibt - der Kantenpunkt bei Versatz 13
#     bzw. 196 ist GEMESSEN genau EINEN Punkt breit - und klar unter der
#     Kippstelle. Aus _px("STYLE_SPACE_8") gerechnet und nicht getippt,
#     damit sie dem Groessenregler folgt wie die Polsterung, die sie
#     misst.
#
# DIE GEGENPROBE IST GEFAHREN, UND SIE IST DER EIGENTLICHE BEWEIS
#     Ein kuerzerer Lauf koennte auch einfach "196" behaupten, weil er
#     frueher stehenbleibt. Darum ist dieselbe Messung an einem Baum OHNE
#     die Polsterung gefahren worden - die Regel .zep-sidebar im
#     ERZEUGTEN style.scss auf den Stand vor Aufgabe 27
#     zurueckgedreht (min-width: 208px, kein padding), neu gebuendelt,
#     neu abgebildet. GEMESSEN, alle vier Seiten:
#
#         mit Polsterung     Hervorhebung 13-196, Haltelaenge 6 -> 196
#         ohne Polsterung    Hervorhebung  2-207, Haltelaenge 6 -> 209
#
#     Die reparierte Messung unterscheidet die beiden Zustaende also.
#     Die alte tat es nicht: sie meldete 209 fuer BEIDE.
def _halt_waagerecht() -> int:
    return max(2, _px("STYLE_SPACE_8") // 2)


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

    DIE HALTELAENGE IST NICHT _HALT_PUNKTE, UND DAS IST DER KERN DER
    REPARATUR VOM 02.09.2026 - die Herleitung steht bei
    _halt_waagerecht() oben. Waagerecht muss der Lauf in die POLSTERUNG
    passen (SPACE_8, 12 Punkte), nicht in die Zeilenhoehe (49).
    """
    x_start = platte[0] + _AKTIV_X_VERSATZ
    basis = bild.at(x_start, y_mitte_abs)[:3]
    halt = _halt_waagerecht()

    lauf_start = None
    for i in range(0, 260 - _AKTIV_X_VERSATZ):
        x = x_start + i
        anders = max(abs(a - b) for a, b in
                    zip(bild.at(x, y_mitte_abs)[:3], basis)) > _SCHWELLE
        if anders and lauf_start is None:
            lauf_start = x
        elif not anders and lauf_start is not None:
            lauf_start = None
        if anders and lauf_start is not None and x - lauf_start >= halt:
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

    ANGEPASST am 19.08.2026 (Aufgabe 27, Musterblatt "Die Schale"), UND
    EINMAL GEGEN DIE ALTE ZAHL FALLEN GELASSEN, WIE VERLANGT
        Vor dieser Aufgabe reichte die Hervorhebung randgleich bis an
        .zep-sidebar heran (208, siehe die alte Toleranz-Begruendung
        unten), weil .zep-row-nav die volle Sidebar-Breite ausfuellte.
        Die neue Polsterung auf .zep-sidebar selbst (siehe dort) zieht
        die Hervorhebung jetzt auf allen vier Seiten INNERHALB dieser
        Polsterung zusammen - GENAU das Bild des Musterblatts ("keinen
        eigenen Kasten"). GEMESSEN, gegen die alte Erwartung (208): der
        Waechter fiel wie vorhergesagt, mit `{'general': 196, 'network':
        196, 'bluetooth': 196, 'vpn': 196}` - deterministisch auf allen
        vier Seiten, keine Streuung wie bei der alten 208/209-Rundung
        unten. 196 ist keine neue Handzahl: die Hervorhebung beginnt bei
        SPACE_8 (links) und reicht bis SPACE_8 vor der rechten Kante,
        die Erwartung ist darum SIDEBAR_BREITE_SOLL minus einmal SPACE_8
        (208 - 12 = 196) - dieselbe Sprosse, mit der .zep-sidebar seine
        eigene Polsterung bekommen hat.

    TOLERANZ VON 1 PUNKT, UND SIE IST GEMESSEN, NICHT GERATEN
        Vor der Polsterung lag die rechte Kante der Hervorhebung GENAU
        auf der 1px Randlinie von .zep-sidebar (border-right), und ob
        dieser eine Bildpunkt (halb Hervorhebungs-, halb Randfarbe durch
        Antialiasing) die Schwelle _SCHWELLE ueberschritt, schwankte
        zwischen 208 (general/network/bluetooth) und 209 (vpn) - derselbe
        Sachverhalt, ein Bildpunkt anders gerundet. Mit der Polsterung
        endet die Hervorhebung nicht mehr AN einer Randlinie, sondern
        mitten im $bg-Grund der Seitenleiste - GEMESSEN (dieser Lauf):
        alle vier Seiten treffen exakt 196, keine Streuung mehr. Die
        Toleranz bleibt trotzdem stehen, aus demselben Vorsichtsgrund wie
        vorher: eine einzelne Bildpunkt-Rundung ist kein Fehler.
    """
    ergebnisse: dict[str, int | None] = {}
    for name, info in schale["seiten"].items():
        zeile = _aktive_zeile(info["bild"], info["platte"])
        if zeile is None:
            ergebnisse[name] = None
            continue
        oben, unten = zeile
        # NICHT DIE MITTE DER ZEILE, SONDERN EIN STREIFEN DICHT UNTER
        # IHRER OBERKANTE - GEAENDERT am 02.09.2026, und die Aenderung ist
        # eine REPARATUR DES MESSGERAETS, keine Anpassung der Erwartung.
        #
        # WAS DIE MITTE MASS
        #     _spaltengrenze() taastet waagerecht ab und haelt beim ersten
        #     Lauf abweichender Farbe. In der MITTE der Zeile stehen
        #     Symbol und Beschriftung, und Glyphen SIND abweichende
        #     Farbe. Gemessen wurde damit der Abstand bis zum ersten
        #     Buchstaben, nicht die rechte Kante der Hervorhebung - und
        #     weil _AKTIV_X_VERSATZ (50) mitten im Textbereich liegt,
        #     konnte sogar die VERGLEICHSFARBE selbst schon Schrift sein.
        #
        #     Das Ergebnis schwankte darum von Lauf zu Lauf und von Seite
        #     zu Seite. Zwei Laeufe am selben Stand:
        #         {'general': 128, 'network': 130, 'bluetooth':  81, 'vpn': 209}
        #         {'general': 158, 'network': 142, 'bluetooth':  81, 'vpn': 209}
        #
        # WAS DIESER STREIFEN MISST
        #     oben+6 liegt innerhalb der Hervorhebung (sie ist
        #     STYLE_NAV_ROW_HEIGHT hoch) und OBERHALB der Glyphen. Damit
        #     ist die erste Abweichung wieder das, was gesucht war: die
        #     rechte Kante der Flaeche.
        #
        # UND HIER STAND EIN BEFUND, DEN ICH NICHT NACHGEMESSEN HATTE -
        # BERICHTIGT am 02.09.2026
        #     An dieser Stelle stand: "Gemessen danach ... {'general':
        #     209, 'network': 209, 'bluetooth': 209, 'vpn': 209} - die
        #     Zusicherung bleibt damit ROT, und zwar zu Recht ... Der
        #     Zustand ist zurueckgefallen."
        #
        #     Die vier 209 waren echt, der Schluss daraus war falsch. Es
        #     ist KEIN Rueckfall: die Polsterung von .zep-sidebar wirkt,
        #     und die Hervorhebung endet auf allen vier Seiten GENAU bei
        #     196. Was 209 gemeldet hat, war der Rest desselben
        #     Messfehlers - die Haltelaenge der waagerechten Suche war
        #     aus der Zeilenhoehe abgeleitet (24) und passte darum nie in
        #     die 12 Punkte breite Polsterung, die sie finden sollte. Die
        #     Herleitung, die Farbtabelle und die Gegenprobe stehen bei
        #     _halt_waagerecht() weiter oben.
        #
        #     Die Lehre steht hier und nicht nur im Bericht: ich habe
        #     dieselbe Messung an einem Tag zweimal repariert, und beim
        #     ersten Mal aus dem verbliebenen Fehler einen Befund ueber
        #     den Baum gemacht. "209 ist genau der Wert von vor Aufgabe
        #     27" hat dabei wie eine Bestaetigung gewirkt und war ein
        #     Zufall: 209 ist die linke Kante der Seite, und dort landet
        #     jede Suche, die ueber die Seitenleiste hinweglaeuft.
        #
        #     Die Erwartung (196) ist in beiden Runden NICHT angefasst
        #     worden. Ein Test, dessen Messung kaputt war, hat trotzdem
        #     den richtigen Sollwert gehabt.
        y_mitte_abs = info["platte"][1] + oben + 6
        ergebnisse[name] = _spaltengrenze(info["bild"], info["platte"], y_mitte_abs)

    fehlend = {name: grenze for name, grenze in ergebnisse.items()
              if grenze is None}
    assert not fehlend, (
        f"auf diesen Seiten liess sich die Hervorhebung des aktiven "
        f"Eintrags gar nicht finden: {sorted(fehlend)} - siehe die "
        "Bilder aus dieser Aufgabe")

    hervorhebung_soll = SIDEBAR_BREITE_SOLL - _px("STYLE_SPACE_8")

    falsch = {name: grenze for name, grenze in ergebnisse.items()
             if abs(grenze - hervorhebung_soll) > 1}
    assert not falsch, (
        f"die Hervorhebung des aktiven Eintrags soll {hervorhebung_soll}px "
        f"weit reichen (.zep-sidebar Breite {SIDEBAR_BREITE_SOLL}px minus "
        f"einmal STYLE_SPACE_8 Polsterung, ags-style.template), gemessen: "
        f"{falsch}")


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
    #
    # NACH AUFGABE 27 (19.08.2026) STEHT _px() OBEN, MODULWEIT: die
    # Sidebar-Polsterung braucht denselben Kunstgriff jetzt auch fuer
    # STYLE_SPACE_8 - keine zweite Kopie derselben vier Zeilen.
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


# DIE FLAECHE - DER INHALT NEBEN DER SEITENLEISTE
#
# NACHGETRAGEN am 20.08.2026 (Aufgabe 49). GEMELDET vom Nutzer, ZWEIMAL:
# "der außen abstand, das hast du immernoch nicht verändert in dem
# sidebar mit inner content ags fenster", und danach noch einmal "die
# abstände in dem inner content neben der sidebar, das custom ags fenster
# was wir gemacht haben, sind auch nicht richtig". Beim dritten Mal soll
# ein Test es vorher sagen.
#
# WOGEGEN GEMESSEN WIRD, UND WARUM GEGEN DEN TRENNER
#     Der Trenner unter dem Zustandskopf (zepDivider, ags-kit.template)
#     ist ein Kind DERSELBEN Saeule wie die Flaeche darunter und laeuft
#     von Kante zu Kante durch. Seine beiden Enden sind damit exakt die
#     Kanten des Sichtfensters, in dem die Flaeche sitzt - einschliesslich
#     dessen, was die Bildlaufleiste sich gerade nimmt. GEMESSEN am
#     20.08.2026: ohne senkrechte Leiste laeuft er von Versatz 210 bis
#     878, mit ihr endet er 24 Punkte frueher.
#
#     Genau deshalb steht hier der Trenner und nicht die Fensterkante:
#     die Rinne der Bildlaufleiste kommt aus dem GTK-Thema, und ein Test,
#     der sie abschreibt, liegt beim naechsten Thema falsch - dieselbe
#     Lehre, an der der Boden `.zep-shell-page` dreimal gescheitert ist
#     (siehe der Block dazu in ags-style.template). Als Nebenwirkung
#     liegt der Schieber der Leiste AUSSERHALB des gemessenen Streifens
#     und kann den Waechter nicht faelschlich ausloesen.
#
# NUR DIE ZWEI SEITEN MIT EINEM TRENNER
#     "general" und "vpn" tragen keinen Zustandskopf mit Trennlinie;
#     ihre Flaeche laesst sich hier also nicht gegen etwas messen, das
#     aus derselben Saeule kommt. Ihre Polsterung haelt
#     tests/src/test_schale.py fest (dieselben zwei Sprossen, an der
#     Vorlage geprueft).
_FLAECHEN_SEITEN = ("bluetooth", "network")

# KEINE TOLERANZ, UND DAS IST EINE MESSUNG UND KEINE STRENGE
#
#     Der erste Entwurf dieses Waechters liess zwei Punkte Unschaerfe zu
#     - und wurde damit GRUEN auf dem kaputten Baum. GEMESSEN am
#     20.08.2026 vor der Reparatur: der aeusserste Bildpunkt stand 23
#     Punkte vor dem rechten Ende des Trenners, obwohl die Seite
#     ueberhaupt keine Polsterung trug. Die 23 sind das Innenpolster des
#     Zahnradknopfs - es verdeckt den Fehlbetrag fast vollstaendig, und
#     zwei Punkte Nachsicht verdecken den Rest.
#
#     Die gemessenen Abstaende NACH der Reparatur liegen weit weg von der
#     Schwelle: 48 rechts (beide Seiten), 65 links (Bluetooth), 181 links
#     (Netzwerk, mittige Ueberschrift) gegen eine Erwartung von 25. Ein
#     Zuschlag hat hier nichts zu glaetten, er kann nur etwas
#     durchlassen.


def _trenner(bild: measure.Image,
             platte: tuple[int, int, int, int]) -> tuple[int, int, int] | None:
    """(y, x_links, x_rechts) der durchlaufenden Trennlinie unter dem
    Zustandskopf - alles absolut, nicht als Versatz.

    Gesucht wird die erste Zeile unterhalb des Fensterkopfs, die auf
    ihrer ganzen Breite anders aussieht als drei Punkte darueber. Drei
    und nicht einer, weil die Linie einen Punkt breit ist und ihre
    Nachbarn schon mit anfaerbt.
    """
    x_pruef = range(platte[0] + 260, platte[0] + platte[2] - 60, 7)
    for y in range(platte[1] + 85, platte[1] + platte[3] - 40):
        if all(max(abs(a - b) for a, b in
                   zip(bild.at(x, y)[:3], bild.at(x, y - 3)[:3])) > 12
               for x in x_pruef):
            links = rechts = None
            for x in range(platte[0] + 210, platte[0] + platte[2]):
                if max(abs(a - b) for a, b in
                       zip(bild.at(x, y)[:3], bild.at(x, y - 3)[:3])) > 12:
                    links = x
                    break
            for x in range(platte[0] + platte[2] - 1, platte[0] + 210, -1):
                if max(abs(a - b) for a, b in
                       zip(bild.at(x, y)[:3], bild.at(x, y - 3)[:3])) > 12:
                    rechts = x
                    break
            if links is not None and rechts is not None and rechts - links > 400:
                return (y, links, rechts)
    return None


def _tinte(bild: measure.Image, x_von: int, x_bis: int,
           y_von: int, y_bis: int) -> tuple[int, int] | None:
    """Erste und letzte Spalte im Streifen, in der ueberhaupt etwas
    gemalt ist - gefunden ueber den SENKRECHTEN Kontrast innerhalb der
    Spalte und nicht ueber einen Farbvergleich mit dem Grund.

    Der Grund der Schale ist Glas: er zeigt die Tapete darunter und
    aendert seine Farbe von Spalte zu Spalte. Ein Schwellenwert gegen
    eine feste Grundfarbe waere darum entweder taub oder ueberall
    ausgeloest. Der senkrechte Kontrast INNERHALB einer Spalte kennt das
    Problem nicht: der Verlauf des Glases ist weich (GEMESSEN: unter 3
    Punkte je Schritt), jede Kante einer Zeile, eines Knopfs oder einer
    Glyphe ist hart.
    """
    treffer = [x for x in range(x_von, x_bis + 1)
               if any(max(abs(a - b) for a, b in
                          zip(bild.at(x, y)[:3], bild.at(x, y + 1)[:3])) > 14
                      for y in range(y_von, y_bis))]
    return (treffer[0], treffer[-1]) if treffer else None


def test_die_flaeche_haelt_ihre_polsterung_zu_beiden_kanten(schale):
    """Der Inhalt unter dem Zustandskopf klebt an keiner der beiden
    Kanten - er haelt mindestens eine Sprosse Abstand.

    DASS ER UEBERHAUPT AUSLOEST, IST NACHGEMESSEN UND NICHT BEHAUPTET
        Die Bilder VOR der Reparatur dieser Aufgabe liegen noch (ein
        eigener Lauf am 20.08.2026, `--basetemp`), und _trenner()/
        _tinte() sind gegen genau diese Dateien gehalten worden:

            bluetooth   links 40   rechts 23   -> ROT
            network     links 181  rechts 23   -> ROT

        Gegen dieselben Funktionen auf den Bildern NACH der Reparatur:

            bluetooth   links 65   rechts 48   -> gruen
            network     links 181  rechts 48   -> gruen

        Die 23 sind das Innenpolster des Zahnradknopfs - mehr Abstand
        hatte der Inhalt nicht, die Seiten trugen ueberhaupt keine
        Polsterung. Die 25 Punkte Unterschied sind genau das, was
        `.zep-shell-flaeche` seither beisteuert.
    """
    sprosse = _px("STYLE_SPACE_16")
    fehler = []
    for name in _FLAECHEN_SEITEN:
        info = schale["seiten"][name]
        bild, platte = info["bild"], info["platte"]
        linie = _trenner(bild, platte)
        assert linie, (
            f"'{name}': keine durchlaufende Trennlinie unter dem "
            f"Zustandskopf gefunden - siehe schale-{name}.png")
        y, x_links, x_rechts = linie
        # DIE UNTERSTEN PUNKTE BLEIBEN AUSSEN VOR, UND DAS IST KEINE
        # BEQUEMLICHKEIT - GEMESSEN am 20.08.2026 beim ersten Lauf dieses
        # Waechters: er meldete "rechts 1px" auf beiden Seiten, obwohl
        # der Inhalt laengst gepolstert war. Gefunden hatte er die
        # RUNDE UNTERE ECKE der Platte (.overlay-outer, border-radius
        # STYLE_RADIUS_PANEL) - eine harte Kante wie jede andere, nur
        # gehoert sie dem Fenster und nicht der Flaeche. Ein Streifen von
        # der Hoehe des Radius bleibt darum ungemessen; die Polsterung
        # steht dort ohnehin nicht zur Debatte.
        tinte = _tinte(bild, x_links, x_rechts, y + 3,
                       platte[1] + platte[3] - _px("STYLE_RADIUS_PANEL") - 2)
        assert tinte, (
            f"'{name}': unter dem Trenner ist ueberhaupt nichts gemalt - "
            f"das misst keine Polsterung, sondern eine leere Seite")
        links = tinte[0] - x_links
        rechts = x_rechts - tinte[1]
        if links < sprosse:
            fehler.append(f"{name}: links {links}px statt {sprosse}px")
        if rechts < sprosse:
            fehler.append(f"{name}: rechts {rechts}px statt {sprosse}px")
    assert not fehler, (
        "der Inhalt neben der Seitenleiste klebt an einer Kante - genau "
        "das hat der Nutzer zweimal gemeldet ('die abstände in dem inner "
        "content neben der sidebar ... sind auch nicht richtig'). "
        "Erwartet wird mindestens STYLE_SPACE_16 auf jeder Seite, so wie "
        "das Musterblatt ('Die Schale') die Flaeche zeichnet:\n  "
        + "\n  ".join(fehler))


# Die Zeile, die beobachteWaagerechtenUeberhang()
# (ags-overlay-utils.template, notify::upper, Aufgabe 19/d766b7a) NUR
# dann schreibt, wenn der Inhalt einer Seite tatsaechlich mehr Breite
# verlangt als das Fenster ihr laesst - siehe der Kommentar dort.
# `[^"]*` statt "control", weil config.name der Schale gehoert
# (ShellConfig, ags-control-center.template) und diese Datei ihn nicht
# abschreiben soll, nur die Zahlen dahinter.
#
# DIESER AUSDRUCK HAT AB DEM 21.08.2026 AUF NICHTS MEHR GEPASST, UND DIE
# ZUSICHERUNG DARUNTER WAR SEITHER GRUEN, OHNE ETWAS ZU MESSEN -
# BERICHTIGT am 02.09.2026 (Aufgabe 83)
#
#     Er stand auf der EINZAHLIGEN Fassung der Meldung:
#         Ueberlagerung "...": Inhalt 63px breiter als das Fenster erlaubt
#     Am 21.08.2026 hat die Meldung ihre zweite und dritte Zahl bekommen,
#     damit eine Momentaufnahme von einem echten Ueberhang zu
#     unterscheiden ist (die Herleitung steht bei
#     beobachteWaagerechtenUeberhang()):
#         Ueberlagerung "control": Inhalt 950px, Sichtfenster 645px -
#         305px breiter als das Fenster erlaubt.
#     `Inhalt (\d+)px breiter` konnte darauf nicht mehr passen. Elf Tage
#     lang hat diese Datei also einen Log durchsucht, in dem der gesuchte
#     Wortlaut nicht mehr vorkam, und JEDEN Zustand als "kein Ueberlauf"
#     gelesen.
#
#     GEMESSEN am 02.09.2026, an derselben Schale, im erzeugten Baum:
#         ohne Boden                        0 Zeilen  (Ausdruck: 0 Treffer)
#         .zep-shell-flaeche min-width 900  1 Zeile   (alt: 0, neu: 1)
#             Ueberlagerung "control": Inhalt 950px, Sichtfenster 645px -
#             305px breiter als das Fenster erlaubt.
#     Der alte Ausdruck fand also auch DANN nichts, wenn eine Seite 305
#     Punkte zu breit war - die Zusicherung blieb gruen. Der neue findet
#     genau diese eine Zeile und keine im sauberen Baum.
#
# ALLE DREI ZAHLEN, damit die Fehlermeldung eine Momentaufnahme
# erkennbar macht: ein Sichtfenster, das kleiner ist als die Sprosse des
# Fensters, stammt aus der ersten Zuteilung und ist kein Befund (siehe
# ags-overlay-utils.template). Im sauberen Baum kommt beides nicht vor -
# GEMESSEN, 0 Zeilen -, also braucht der Ausdruck dafuer keine Ausnahme;
# er soll den Fall nur benennen koennen, wenn er einmal auftritt.
_UEBERLAUF_ZEILE = re.compile(
    r'Ueberlagerung "[^"]*": Inhalt (\d+)px, Sichtfenster (\d+)px - '
    r'(\d+)px breiter als das Fenster erlaubt')


def test_keine_seite_der_schale_scrollt_waagerecht(schale):
    """"ich will auch nicht horizontal scrollen in diesem ags fenster" -
    diese Meldung zweimal in dieser Sitzung (Blattkopf Aufgabe 23),
    zuerst schon ganz am Anfang ("die ags fenster ... sind so
    eingequetscht das man nach rechts und nach unten scrollen muss").

    WARUM DER LOG UND KEIN BILDPUNKT-ABGLEICH
        `overlay_scrolling: false` (ags-overlay-utils.template) laesst
        die waagerechte Leiste, sobald sie erscheint, echten Platz
        einnehmen statt zu schweben - sie waere also grundsaetzlich im
        Bild zu finden. Aber `notify::upper` feuert GENAU dann, wenn
        Gtk.PolicyType.AUTOMATIC dieselbe Leiste einblendet (derselbe
        Vergleich upper > page_size, den GTK selbst fuer die
        Sichtbarkeit einer AUTOMATIC-Leiste anstellt) - der Log ist
        damit kein Naeherungswert fuer "Leiste sichtbar", sondern
        derselbe Bedingungsausdruck, nur mitgeschrieben. Eine
        Bildpunktsuche muesste zusaetzlich raten, welche Farbe/Zeile die
        Leiste auf JEDER der vier Seiten traegt; der Log braucht das
        nicht.

    GEMESSEN (Bericht Aufgabe 19, d766b7a, VOR der Reparatur dieser
    Aufgabe): general 63px, network 27px, bluetooth 77px zu breit fuer
    ihre Seite der Schale - drei Zeilen in `schalen_log`, eine je Seite.
    Dieser Waechter ist an genau diesem Baum (vor der Reparatur) einmal
    gefallen, mit denselben drei Zeilen (siehe der Bericht dieser
    Aufgabe) - der Beweis, dass er ueberhaupt etwas findet, nicht nur
    dass er nie ausloest.

    DIE GEGENPROBE IST AM 02.09.2026 NEU GEFAHREN WORDEN, UND SIE HAT
    DIESE ZUSICHERUNG BEIM NICHTSTUN ERWISCHT
        Der Ausdruck oben passte seit dem 21.08.2026 auf keine Zeile
        mehr (die Herleitung steht dort). GEMESSEN, mit einem Boden
        `.zep-shell-flaeche { min-width: 900px }` im erzeugten
        style.scss:

            Waechter an beiden Flaechen, alter Ausdruck   gruen (blind)
            Waechter an beiden Flaechen, neuer Ausdruck   ROT, 305px
            Waechter NUR an der Fabrik,  neuer Ausdruck   gruen

        Die dritte Zeile ist der Grund, warum
        beobachteWaagerechtenUeberhang() seit Aufgabe 83 an BEIDEN
        Bildlaufflaechen haengt: der Ueberhang einer Schalenseite kommt
        seit dem Umbau bei der INNEREN an. Ohne den zweiten Waechter
        waere diese Zusicherung ein zweites Mal fuer immer gruen
        geworden - aus einem anderen Grund als beim ersten Mal.
    """
    treffer = _UEBERLAUF_ZEILE.findall(schale["schalen_log"])
    assert not treffer, (
        "die Schale meldet waagerechten Ueberlauf "
        "(beobachteWaagerechtenUeberhang(), notify::upper) auf mindestens "
        "einer Seite: "
        + ", ".join(f"{ueber}px zu breit (Inhalt {inhalt}px in "
                    f"Sichtfenster {sicht}px)"
                    for inhalt, sicht, ueber in treffer)
        + "\n\nEin Sichtfenster, das deutlich kleiner ist als die Sprosse "
        "des Fensters, waere eine erste Zuteilung und kein Befund - siehe "
        "beobachteWaagerechtenUeberhang() in ags-overlay-utils.template."
        "\n\nVoller Log:\n" + schale["schalen_log"])
