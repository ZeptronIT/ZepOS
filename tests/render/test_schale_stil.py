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


def _sidebar_grenze(bild: measure.Image, platte: tuple[int, int, int, int],
                    y_versatz: int) -> int | None:
    """Die x-Spalte, an der die Seitenleiste aufhoert und der Inhalt
    beginnt - gesucht als NACHHALTIGER Farbsprung (5 Bildpunkte in
    Folge deutlich anders), nicht als einzelner Pixel: ein einzelner
    Pixel waere so gut wie sicher ein Buchstabenrand.
    """
    x_platte, y_platte, _, _ = platte
    y = y_platte + y_versatz
    start_x = x_platte + 180
    ende_x = x_platte + 240
    basis = bild.at(start_x, y)[:3]
    for x in range(start_x, ende_x - 5):
        hier = bild.at(x, y)[:3]
        if max(abs(a - b) for a, b in zip(hier, basis)) <= 10:
            continue
        # Haelt der Sprung fuenf Punkte lang, oder ist es nur ein
        # Buchstabenpixel, das gleich wieder verschwindet?
        haelt = all(
            max(abs(a - b) for a, b in zip(bild.at(x + i, y)[:3], hier)) <= 12
            for i in range(1, 5))
        if haelt:
            return x - x_platte
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
    aktiven Seite abhaengen) und an EINEM y innerhalb der ersten
    Sidebar-Zeile - 100 Punkte unter der Fensteroberkante liegt bei
    allen vier Seiten sicher in der Gruppe VERBINDUNGEN (die
    Kopfzeile+Randabstand braucht darunter deutlich weniger als 100px,
    und der erste Eintrag ist laut Messung dieser Aufgabe rund 74-76px
    hoch - 100 trifft ihn also mittig).
    """
    ergebnisse = {}
    for name, info in schale["seiten"].items():
        grenze = _sidebar_grenze(info["bild"], info["platte"], y_versatz=100)
        ergebnisse[name] = grenze

    fehlend = {name: grenze for name, grenze in ergebnisse.items()
              if grenze is None}
    assert not fehlend, (
        f"auf diesen Seiten liess sich gar keine Grenze finden: "
        f"{sorted(fehlend)} - siehe die Bilder aus dieser Aufgabe")

    falsch = {name: grenze for name, grenze in ergebnisse.items()
             if grenze != SIDEBAR_BREITE_SOLL}
    assert not falsch, (
        f"die Seitenleiste soll {SIDEBAR_BREITE_SOLL}px breit bemalen "
        f"(.zep-sidebar, ags-style.template), gemessen: {falsch}")


def test_ein_seitenleisten_eintrag_ist_nicht_die_knopfhoehe_hoch(schale):
    """Die Kehrseite von tests/src/test_kit_nesting.py, als Zahl:
    zepButton("umrandet") behauptet STYLE_CONTROL_HEIGHT (49px bei
    Vorgabegroesse), aber sein Kind zepRow verlangt STYLE_ROW_HEIGHT
    (74px) - und weil der Knopf keine senkrechte Polsterung traegt,
    gewinnt das Kind. Diese Zusicherung haelt die Kit-Regel ("ein Knopf
    ist 32/49px hoch") gegen das BILD und nicht gegen die Behauptung.

    Gemessen als Abstand zwischen den beiden ersten vollstaendig
    randfarbenen Zeilen der Seitenleiste (der gemeinsame Rand zwischen
    dem ersten und dem zweiten Eintrag) - dieselbe Idee wie
    _sidebar_grenze(), nur senkrecht.
    """
    # NICHT size_of() aus desktop_session.py: das dortige int(...) setzt
    # voraus, dass value_of() OHNE Einheit zurueckkommt (BARE) - fuer
    # STYLE_CONTROL_HEIGHT/STYLE_ROW_HEIGHT (beide PX, siehe TABLE in
    # src/sizes.py) haengt value_of() ein "px" an, und int("49px") wirft.
    # GEMESSEN am 19.08.2026 beim ersten Lauf dieser Datei.
    def _px(name: str) -> int:
        sys.path.insert(0, str(ROOT / "src"))
        try:
            import sizes
            return int(sizes.value_of(name, {}).removesuffix("px"))
        finally:
            sys.path.remove(str(ROOT / "src"))

    knopfhoehe = _px("STYLE_CONTROL_HEIGHT")
    zeilenhoehe = _px("STYLE_ROW_HEIGHT")

    info = schale["seiten"]["general"]
    bild = info["bild"]
    x_platte, y_platte, breite_platte, hoehe_platte = info["platte"]

    rand = (33, 79, 89)  # $border, siehe die Messung im Bericht dieser Aufgabe

    def randzeile(y: int) -> bool:
        n = sum(1 for x in range(x_platte + 6, x_platte + 200)
               if max(abs(a - b) for a, b in
                     zip(bild.at(x, y)[:3], rand)) <= 6)
        return n / 194 > 0.5

    grenzen = [y - y_platte for y in range(y_platte + 60, y_platte + hoehe_platte)
              if randzeile(y)]
    # Benachbarte Treffer (die 1-2px Antialiasing derselben Linie)
    # zusammenfassen.
    zusammengefasst: list[int] = []
    for y in grenzen:
        if zusammengefasst and y - zusammengefasst[-1] <= 2:
            continue
        zusammengefasst.append(y)

    assert len(zusammengefasst) >= 2, (
        f"weniger als zwei Randlinien in der Seitenleiste gefunden: "
        f"{zusammengefasst} - siehe das Bild schale-general.png dieser "
        "Aufgabe")

    erster_eintrag = zusammengefasst[1] - zusammengefasst[0]
    assert erster_eintrag == knopfhoehe, (
        f"der erste Eintrag der Seitenleiste ist {erster_eintrag}px hoch "
        f"(gemessen zwischen y={zusammengefasst[0]} und "
        f"y={zusammengefasst[1]}, bezogen auf die Fensteroberkante). "
        f"zepButton (die aeussere Huelle) beansprucht "
        f"STYLE_CONTROL_HEIGHT={knopfhoehe}px, aber zepRow (das Kind) "
        f"verlangt STYLE_ROW_HEIGHT={zeilenhoehe}px - und gewinnt, weil "
        f"der Knopf keine senkrechte Polsterung hat "
        "(.zep-btn { padding: 0 SPACE_16 }). Siehe "
        "tests/src/test_kit_nesting.py fuer die Ursache.")
