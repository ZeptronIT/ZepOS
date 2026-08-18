# SPDX-License-Identifier: GPL-3.0-or-later
"""Das ZWEITE Aufgehen desselben Fensters.

WAS GEMELDET WURDE
    Der Nutzer am 17.08.2026, auf echter Hardware: "Waybar Control Modal
    bei klick einmal geht es beim zweiten klick erscheint das modal links
    am rand des bildschirms und laesst sich nicht richtig nach unten
    scrollen es verbuggt."

WAS GEMESSEN WURDE, am selben Tag, im verschachtelten Compositor von
tests/render/ - Schirm 1920x1080, Zeiger auf dem Zahnrad bei x=1860, das
Kontrollzentrum dreimal auf und zu, mit den Zeilen einer laufenden
Maschine (WLAN-Name, Druckerstatus, Datenschutzzeile)

    erstes Aufgehen    measure(HORIZONTAL) = min 495 / nat 495
                       Fenster 495 breit, Lage x=1401 - richtig
    zweites Aufgehen   measure(HORIZONTAL) = min 930 / nat 930
                       Fenster 930 breit, gestellt fuer 495

    Mit laengeren, aber immer noch echten Zeilen: 1386 statt 495. Das
    Fenster stand damit 402 Punkte ueber dem rechten Bildrand - und die
    senkrechte Bildlaufleiste sitzt am RECHTEN Rand des Fensters, also
    dort draussen mit. Das ist die dritte Meldung ("laesst sich nicht
    richtig nach unten scrollen"): die Leiste war nicht kaputt, sie war
    nicht auf dem Schirm.

ZWEI URSACHEN, UND SIE SIND VERSCHIEDEN
    1. Der Deckel griff nur senkrecht. Gtk.PolicyType.NEVER an der
       waagerechten Bildlaufleiste heisst nicht "keine Leiste", sondern
       "der Inhalt bestimmt die Breite": die Gtk.ScrolledWindow meldet
       dann die MINDESTbreite ihres Kindes als eigene weiter, und ein
       Gtk.Window wird nie schmaler als sein Kind. set_default_size()
       war damit waagerecht dieselbe Bitte, die GTK ablehnt, wie sie es
       senkrecht vor dem 12.08.2026 war.

       Der Unterschied zwischen erstem und zweitem Klick ist die
       REIHENFOLGE: updateDisplay() laeuft in onShow und damit NACH
       measure(). Beim ersten Messen stehen in den Zeilen noch "Lade …"
       und "VPN: Aus", beim zweiten der Text des letzten Males.

    2. Die Nachfuehrung fragte den Zeiger neu. getOverlayPosition() las
       `hyprctl cursorpos` bei jedem Aufruf selbst - auch in dem Takt,
       der nach dem Aufgehen zwei Sekunden lang die Groesse beobachtet.
       GEMESSEN: Klick bei x=1860, Fenster geht bei x=1401 auf, Zeiger
       danach nach x=300 - 100 ms spaeter steht das Fenster bei x=24.
       Das ist der linke Bildschirmrand aus der Meldung, und er entsteht
       aus der Klemmung `if (localX < EDGE_GAP) localX = EDGE_GAP`.

    Nach beiden Aenderungen, gemessen im selben Aufbau: dreimal
    (1401, 108, 495, 540), mit kurzen wie mit langen Zeilen, mit und
    ohne Mausbewegung danach.

    UND EINE DRITTE, die noch am selben Tag dazugekommen ist: die Lage
    kam ueberhaupt vom MAUSZEIGER und nicht von dem Bedienelement, das
    das Fenster aufmacht. Sie steht mit ihren Messungen ganz unten in
    dieser Datei, unter "Wo ein Fenster aufgeht".

WARUM DIESE DATEI NEBEN test_overlay_windows.py UND test_modal_rule.py
STEHT
    test_overlay_windows.py fragt, OB die Fabrik deckelt. test_modal_rule
    fragt, ob es einen zweiten Weg gibt, so ein Fenster zu bauen. Hier
    steht die Frage, die beide nicht stellen: ob der Deckel auch dann
    noch greift, wenn das Fenster ZUM ZWEITEN MAL aufgeht - also wenn
    sein Inhalt nicht mehr der ist, mit dem es gebaut wurde.

WAS HIER GEPRUEFT WIRD UND WAS NICHT
    Was in den Vorlagen STEHT. Was daraus auf dem Schirm wird, misst
    tests/render/ an einem echten Compositor.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
FACTORY = SRC / "templates" / "ags-overlay-utils.template"
CONTROL = SRC / "templates" / "ags-control-center.template"
BAR = SRC / "templates" / "ags-bar.template"
APP = SRC / "templates" / "ags-config.template"


def _code(path: Path) -> str:
    """Die Datei ohne ihre Zeilenkommentare.

    Jede Datei in diesem Baum ERKLAERT, was sie nicht mehr tut. Eine
    Suche nach `Gtk.PolicyType.NEVER` wuerde von der Erklaerung wahr, in
    der steht, dass es dieses NEVER nicht mehr gibt.
    """
    return "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("//"))


# --------------------------------------------------------------------
# Der Deckel, waagerecht
# --------------------------------------------------------------------

def test_the_content_does_not_decide_how_wide_the_window_is():
    """Gtk.PolicyType.NEVER war die Stelle, an der die Breite entglitt.

    NEVER heisst "keine waagerechte Leiste UND die volle Mindestbreite
    des Kindes". Damit ist jede Angabe an set_default_size() waagerecht
    wirkungslos - dasselbe, was senkrecht vor dem 12.08.2026 der Fall
    war, bis die Bildlaufleiste dazukam.
    """
    code = _code(FACTORY)
    assert "hscrollbar_policy: Gtk.PolicyType.NEVER" not in code, (
        "die waagerechte Bildlaufleiste steht wieder auf NEVER; damit "
        "meldet der Inhalt seine Mindestbreite an das Fenster weiter und "
        "der Deckel greift nur noch senkrecht (gemessen 930 statt 495)")
    assert "propagate_natural_width: true" in code, (
        "ohne propagate_natural_width meldet die Bildlaufleiste keine "
        "Wunschbreite mehr - das Fenster fiele auf die Breite seines "
        "Kopfes zusammen")
    assert "propagate_natural_height: true" in code, (
        "die senkrechte Haelfte derselben Paarung fehlt")


def test_the_window_is_as_wide_as_its_content_and_never_wider_than_allowed():
    """Derselbe Satz wie fuer die Hoehe, und aus demselben Grund.

    Die Rechnung sagt, was erlaubt ist (pos.width), die Messung sagt,
    was noetig ist (naturalWidth). Nur das Minimum aus beiden ist eine
    Grenze; jedes fuer sich ist eine Bitte.
    """
    code = _code(FACTORY)
    assert "measure(Gtk.Orientation.HORIZONTAL" in code, (
        "das Fenster misst seine Breite nicht mehr")
    assert re.search(r"Math\.min\(naturalWidth \+ \w+, pos\.width\)", code), (
        "die gemessene Breite wird nicht gegen den Deckel gehalten - "
        "genau der Zustand vom 17.08.2026, in dem 495 als 930 dastand")
    # Der Summand ist die senkrechte Bildlaufleiste, und sie gehoert in
    # die Rechnung: sie liegt NEBEN dem Inhalt, taucht erst auf, wenn die
    # Hoehe gedeckelt wird, und ist damit Breite, die measure() nicht
    # kennt. GEMESSEN am 17.08.2026: ohne sie lag der dritte Knopf des
    # Bluetooth-Fensters hinter der rechten Kante.
    assert "scroller.get_vscrollbar()" in code, (
        "die Breite der Bildlaufleiste wird nicht mehr gemessen, sondern "
        "fehlt oder ist geraten")
    assert re.search(r"Math\.min\(naturalHeight, pos\.height\)", code), (
        "die senkrechte Haelfte derselben Regel fehlt")


# --------------------------------------------------------------------
# Der Zeiger
# --------------------------------------------------------------------

def test_the_pointer_is_read_once_for_each_opening():
    """Ein Fenster gehoert dorthin, wo geklickt wurde.

    GEMESSEN am 17.08.2026: mit einem zweiten Lesen in der Nachfuehrung
    wanderte das offene Fenster von x=1401 nach x=24, weil der Zeiger
    sich in der Zwischenzeit nach x=300 bewegt hatte.
    """
    code = _code(FACTORY)
    assert code.count("hyprctl cursorpos") == 1, (
        "der Zeigerstand wird an mehr als einer Stelle gelesen; dann "
        "kann das Fenster der Maus hinterherlaufen, nachdem es steht")
    stelle = code.index("hyprctl cursorpos")
    assert stelle < code.index("async function getOverlayPosition"), (
        "das Lesen des Zeigers steht wieder IN der Lagerechnung - dann "
        "liest jeder Aufruf neu, auch die Nachfuehrung")


def test_the_follow_up_positions_against_the_same_point_as_the_opening():
    """Dieselbe Rechnung, derselbe Punkt, dasselbe Ergebnis.

    Die Nachfuehrung gibt es, weil Raender erst nach einer Runde ueber
    den Compositor wirken. Sie soll die LAGE nachziehen, nicht das
    Fenster umsetzen.
    """
    code = _code(FACTORY)
    assert "getOverlayPosition(config.width, config.height, anchor)" in code, (
        "das Aufgehen rechnet nicht mehr gegen einen festgehaltenen "
        "Zeigerstand")
    assert "getOverlayPosition(w, h, anchor)" in code, (
        "die Nachfuehrung rechnet gegen einen anderen Punkt als das "
        "Aufgehen - dann steht das Fenster 100 ms spaeter woanders")


# --------------------------------------------------------------------
# Die Zeilen des Kontrollzentrums
# --------------------------------------------------------------------

def _labels(text: str) -> list[tuple[int, str]]:
    """Jedes `new Gtk.Label({...})` samt seiner Klammer.

    Ueber Klammerzaehlung und nicht ueber einen regulaeren Ausdruck: die
    Angaben stehen mal in einer Zeile und mal in vieren, und ein Ausdruck
    ueber eine Zeile faende genau die mehrzeiligen nicht - also die
    laengsten.
    """
    found: list[tuple[int, str]] = []
    for match in re.finditer(r"new Gtk\.Label\(\{", text):
        index = match.end() - 1
        depth = 0
        while index < len(text):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        found.append((text[:match.start()].count("\n") + 1,
                      text[match.end() - 1:index + 1]))
    return found


def test_every_line_of_the_control_centre_knows_where_to_stop():
    """`hexpand: true` heisst "diese Beschriftung traegt die Zeile".

    Und genau diese tragen den Text, der aus einem fremden Programm
    kommt: der WLAN-Name, der Druckerstatus, die Liste der Programme am
    Mikrofon. Ohne Grenze wird das Fenster so breit wie seine laengste
    Zeile.

    GEMESSEN am 17.08.2026: neun Beschriftungen mit hexpand, zwei davon
    mit Grenze. Fensterbreite 930 statt 495, mit laengeren Zeilen 1386.
    """
    text = _code(CONTROL)
    ohne = [(zeile, " ".join(block.split())[:80])
            for zeile, block in _labels(text)
            if "hexpand: true" in block
            and "ellipsize" not in block and "wrap: true" not in block]
    assert not ohne, (
        "diese Beschriftungen nehmen den freien Platz, ohne zu wissen, "
        "wo sie aufhoeren:\n"
        + "\n".join(f"    Zeile {zeile}: {block}" for zeile, block in ohne))


def test_the_control_centre_builds_its_row_labels_in_one_place():
    """Ein Weg, eine Zeilenbeschriftung zu bauen.

    Die vier Angaben gehoeren zusammen (hexpand, xalign, ellipsize,
    max_width_chars). Ausgeschrieben standen sie neunmal da und waren
    zweimal vollstaendig - so ist dieser Fehler entstanden. Eine
    Vorsichtsmassnahme, an die sich jede neue Zeile erst erinnern muss,
    ist keine.
    """
    text = _code(CONTROL)
    assert "const ccLabel = (text: string): Gtk.Label =>" in text, (
        "es gibt keine gemeinsame Zeilenbeschriftung mehr")

    # NEUN STELLEN SEIT DEM 17.08.2026, und die Zahl ist kleiner
    # geworden, weil Zeilen GEGANGEN sind - nicht, weil eine von ihnen
    # ihre Beschriftung wieder selbst baut.
    #
    #     Mikrofon, Kamera, VPN, Wiedergabe, Bildschirme, deskRow (das
    #     sind die sieben Zeilen des Abschnitts SCHREIBTISCH aus EINER
    #     Hand), Drucker, Watchdog, Hilfsskripte.
    #
    #     Weg sind Netz, Bluetooth und Style Editor: ihre Bedienung steht
    #     seit dem 17.08.2026 auf der Leiste (siehe den Abschnitt NETZ &
    #     VERBINDUNGEN in ags-control-center.template). Eine Zeile, die
    #     es nicht mehr gibt, kann ihre Beschriftung auch nicht falsch
    #     bauen.
    #
    # Die Gegenprobe steht darunter und ist die eigentliche Zusicherung:
    # ausgeschrieben duerfen die vier Angaben GENAU EINMAL stehen.
    benutzt = len(re.findall(r"\bccLabel\(", text))
    assert benutzt >= 9, (
        f"nur {benutzt} Zeilen holen ihre Beschriftung aus einer Hand; "
        f"die uebrigen bauen sie wieder selbst")

    ausgeschrieben = [zeile for zeile, block in _labels(text)
                      if "hexpand: true" in block and "ellipsize" in block]
    assert len(ausgeschrieben) == 1, (
        f"die vier Angaben stehen an {len(ausgeschrieben)} Stellen "
        f"ausgeschrieben (Zeilen {ausgeschrieben}) - erwartet ist die "
        f"EINE in ccLabel. Beim naechsten Ausschreiben fehlt wieder eine "
        f"davon, und genau so ist der Fehler vom 17.08.2026 entstanden")


# --------------------------------------------------------------------
# Wo ein Fenster aufgeht: das Modul, nicht die Maus
# --------------------------------------------------------------------
#
# WAS GEMELDET WURDE, am 17.08.2026
#     "die modale fuer kontroll zentrum erscheint ganz links im fenster
#     buggy wir brauchen es aber dort der user mit maus raufklickt".
#
# WAS GEMESSEN WURDE, am selben Tag, verschachtelter Compositor,
# 1920x1200 (der Schirm des Nutzers), das Zahnrad rechts aussen bei
# x=1848 mit 48 Punkten Breite
#
#     ERSTE MESSUNG, ohne Klick (`ags request control`, also das, was
#     eine Tastenbindung tut) - dreimal derselbe Aufruf, nur der Zeiger
#     woanders:
#
#         Zeiger 1872   Fenster x=1401
#         Zeiger  960   Fenster x= 713
#         Zeiger  120   Fenster x=  24   <- der linke Bildrand
#
#     ZWEITE MESSUNG, mit einem ECHTEN Klick auf das Zahnrad ueber
#     zwlr_virtual_pointer_unstable_v1: druecken, den Zeiger nach
#     (120,600) ziehen, DANN loslassen. Das ist kein Kunstgriff, sondern
#     ein Klick, bei dem die Hand schon weiterfaehrt - GTK4 loest die
#     Geste beim LOSLASSEN aus, und der implizite Griff haelt sie beim
#     gedrueckten Widget.
#
#         Fabrik 148b1eb   Fenster x=  24, zweimal hintereinander
#         Fabrik danach    Fenster x=1401, zweimal hintereinander
#
#     Beide Bilder liegen dem Bericht vom 17.08.2026 bei. Das erste ist
#     genau das gemeldete: das Kontrollzentrum klebt am linken Rand,
#     waehrend das Zahnrad, das es aufmacht, rechts aussen sitzt.
#
# DIE URSACHE
#     utils/overlay.ts nahm die Lage aus `hyprctl cursorpos`. Der Zeiger
#     ist nur solange derselbe Punkt wie das Bedienelement, wie ein
#     Mausklick der Ausloeser ist UND die Maus sich seither nicht bewegt
#     hat. Seither sagt der Ausloeser, wo er sitzt.


def test_the_factory_prefers_the_control_that_opened_it():
    """Der Anhaltspunkt kommt von aussen; der Zeiger ist der Rueckfall.

    Die REIHENFOLGE ist die ganze Aussage. Ein `await pointerPosition()`
    vor der Abfrage des Ausloesers waere derselbe Zustand wie vorher,
    nur mit einem ungenutzten Feld daneben.
    """
    code = _code(FACTORY)
    assert "export interface OverlayAnchor" in code, (
        "die Fabrik kennt keinen Anhaltspunkt mehr, den ein "
        "Bedienelement ihr geben koennte")
    assert "show: (at?: OverlayAnchor) => Promise<void>" in code, (
        "OverlayWidget.show() nimmt den Anhaltspunkt nicht entgegen")

    fall = re.search(
        r"const anchor: Spot \| null = angeklickt\s*\n\s*\?\s*\{ kind: "
        r'"widget".*?\n\s*:\s*await pointerPosition\(\)', code, re.S)
    assert fall, (
        "show() waehlt nicht mehr zuerst das Bedienelement und erst dann "
        "den Zeiger - gemessen am 17.08.2026 landet das Kontrollzentrum "
        "sonst bei x=24, wenn die Maus links steht")


def test_a_named_screen_beats_a_search_for_the_one_under_the_pointer():
    """Ein Bedienelement NENNT seinen Schirm.

    Ohne diesen Zweig muesste auch der Anhaltspunkt eines Widgets ueber
    die Zeigerkoordinaten einem Schirm zugeordnet werden - und genau
    dieser Umweg ist es, der auf einem zweiten Schirm oder bei einer
    fehlgeschlagenen Abfrage in den Rueckfall laeuft (marginLeft =
    EDGE_GAP, also den linken Bildrand).
    """
    code = _code(FACTORY)
    assert 'anchor.kind === "widget"\n' in code or \
           'anchor.kind === "widget"' in code, (
        "die Lagerechnung unterscheidet die beiden Anhaltspunkte nicht")
    assert "mon.name === anchor.monitor" in code, (
        "der genannte Schirm wird nicht ueber seinen Anschlussnamen "
        "gefunden")


def test_a_bar_module_says_where_it_sits():
    """Die andere Haelfte: die Leiste muss den Punkt AUSRECHNEN.

    Und zwar beim Klick und nicht beim Bauen - ein Modul wandert, sobald
    ein Nachbar ein- oder ausklappt.
    """
    code = _code(BAR)
    assert "function anchorOf(" in code, (
        "die Leiste rechnet die Lage ihrer Module nicht aus")
    assert "widget.compute_bounds(" in code, (
        "die Lage wird nicht gegen die Wurzel gemessen - dann ist sie "
        "relativ zum Elternkasten und nicht zum Schirm")
    assert "const open = (name: string) => toggle(name, anchorOf(widget," in code, (
        "der Klick reicht den Anhaltspunkt nicht weiter; dann ist "
        "anchorOf() eine Rechnung, die niemand liest")

    # Und die Fabrik wird dabei NICHT importiert - nur ihr Typ. Ein
    # `import { OverlayAnchor }` ohne `type` waere zur Laufzeit die
    # Anforderung eines Ausfuhrnamens, den es in der uebersetzten
    # utils/overlay.js gar nicht gibt.
    assert 'import type { OverlayAnchor } from "../utils/overlay"' in code, (
        "die Leiste holt den Typ nicht als Typ - das ueberlebt das "
        "Uebersetzen nicht")


def test_the_application_hands_the_point_through():
    """Dazwischen liegt app.ts, und ein Glied, das den Punkt fallen
    laesst, macht beide Enden wirkungslos."""
    code = _code(APP)
    assert "function toggleByName(name: string, at?: OverlayAnchor)" in code, (
        "der Umschalter der Leiste nimmt den Anhaltspunkt nicht entgegen")
    assert "toggleWidget(widgets[name] ?? null, at)" in code, (
        "toggleByName reicht ihn nicht weiter")
    assert "await widget.show(at)" in code, (
        "das Fenster bekommt ihn nicht")
