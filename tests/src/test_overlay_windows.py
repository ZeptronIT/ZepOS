# SPDX-License-Identifier: GPL-3.0-or-later
"""Die elf Aufklappfenster: wie gross sie werden und welche Sprache sie
sprechen.

WAS GEMELDET WURDE
    Der Nutzer am 12.08.2026: "ich die app suche ist zu gross von der
    hoehe das gleiche gilt fuer andere modale".

WAS GEMESSEN WURDE, am selben Tag, im verschachtelten Compositor von
tests/render/
    Das Kontrollzentrum meldete sich in seiner Vorlage als 400x580 an
    und stand als 545x1622 auf einem Schirm mit 1080 Zeilen - 645 Punkte
    unter dem Bildrand, darunter eine ganze Abschnittsueberschrift. Der
    Kalender: angemeldet 420x480, gestanden 472x810.

    Die Ursache stand in ags-overlay-utils.template: die Fabrik rechnete
    aus den angemeldeten Massen eine `effectiveW`/`effectiveH` aus und
    benutzte das Ergebnis NUR fuer die Raender. Es gab kein
    set_default_size(), kein set_size_request() und keine
    Bildlaufleiste - die angemeldeten Masse waren Zierrat.

WARUM DIESE DATEI NEBEN test_placement.py STEHT UND NICHT DARIN
    Dort geht es um Kopf und Fuss, die auf dem Schirm KLEBEN. Hier geht
    es um die Fenster, die sich davorstellen: eine andere Frage mit einer
    anderen Regel (MEASURE_MODAL_SHARE) und einem anderen Fehlerbild.

WAS HIER GEPRUEFT WIRD UND WAS NICHT
    Was in den Vorlagen STEHT. Was daraus auf dem Schirm wird, misst
    tests/render/shoot.py an einem echten Compositor und legt es als
    Bild ab - dieselbe Trennung wie zwischen test_placement.py und
    test_bar_headless.py.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from src import sizes

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
OVERLAY = SRC / "templates" / "ags-overlay-utils.template"
CALENDAR = SRC / "templates" / "ags-calendar.template"
CONTROL = SRC / "templates" / "ags-control-center.template"
BAR = SRC / "templates" / "ags-bar.template"
BLUETOOTH = SRC / "templates" / "ags-bluetooth.template"


def _code(path: Path) -> str:
    """Die Datei ohne ihre Zeilenkommentare.

    Jede Datei in diesem Baum ERKLAERT, was sie nicht mehr tut. Eine
    Suche nach "Gtk.Calendar" wuerde von der Erklaerung wahr, in der
    steht, dass es keinen Gtk.Calendar mehr gibt.
    """
    return "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("//"))


# --------------------------------------------------------------------
# Die Groesse
# --------------------------------------------------------------------

def test_the_modal_share_is_the_one_in_the_size_table():
    """Der zweite Abdruck einer Zahl, die in src/sizes.py steht.

    MEASURE_MODAL_SHARE ist mit Absicht kein Platzhalter - sizes.py sagt
    warum: "eine Anzahl und keine Laenge ... gelesen wird sie nicht von
    einer Vorlage, sondern von den Programmen, die ein solches Fenster
    aufziehen". Dann muss aber etwas die Abdruecke gegen das Original
    halten, sonst ist der zweite Ort eine Kopie. Fuer den ersten -
    menu/zepos_menu/window.py - tut das tests/menu/test_options.py; dies
    hier ist dieselbe Zusicherung fuer den zweiten.
    """
    found = re.search(r"^const MODAL_SHARE = ([0-9.]+)$",
                      OVERLAY.read_text(encoding="utf-8"), re.M)
    assert found, "die Fabrik der Aufklappfenster kennt keine Hoehengrenze"
    assert float(found.group(1)) == sizes.MEASURE_MODAL_SHARE, (
        f"die Aufklappfenster deckeln bei {found.group(1)}, die "
        f"Groessentabelle sagt {sizes.MEASURE_MODAL_SHARE}")


def test_the_cap_is_applied_to_the_window_and_not_only_to_the_margins():
    """Der eigentliche Befund: gerechnet wurde, angewendet nicht.

    Drei Dinge muessen zusammenkommen, und jedes einzeln waere
    wirkungslos:

      * der Deckel selbst (MODAL_SHARE mal Schirm),
      * eine Bildlaufleiste, denn ein Gtk.Window wird nie kleiner als
        die MINDESTgroesse seines Kindes - ohne sie ist jede
        Groessenangabe eine Bitte, die GTK ablehnt,
      * die Uebergabe an das Fenster.
    """
    code = _code(OVERLAY)
    assert "MODAL_SHARE" in code, "der Deckel wird nicht mehr gerechnet"
    assert "win.set_default_size(" in code, (
        "die gerechnete Groesse kommt am Fenster nicht an - genau der "
        "Zustand vom 12.08.2026, in dem 400x580 als 545x1622 dastand")
    assert "new Gtk.ScrolledWindow(" in code, (
        "die Fabrik haengt keinen Bildlauf mehr um den Inhalt; ohne ihn "
        "meldet der Inhalt seine ganze Hoehe als Mindesthoehe an und der "
        "Deckel greift nicht")


def test_the_window_is_as_tall_as_its_content_and_never_taller_than_allowed():
    """Nicht "so hoch wie erlaubt", sondern "so hoch wie noetig".

    set_default_size() ist keine Obergrenze, sondern eine Ansage:
    GEMESSEN am 12.08.2026 stand der Kalender auf einem 2160er Schirm
    mit genau 1080 Punkten da - dem Deckel, nicht seinem Inhalt. Erst
    das Minimum aus gemessener und erlaubter Hoehe macht daraus eine
    Grenze.
    """
    code = _code(OVERLAY)
    assert "measure(Gtk.Orientation.VERTICAL" in code, (
        "das Fenster misst seinen Inhalt nicht mehr und fuellt damit "
        "immer seinen Deckel aus")
    assert re.search(r"Math\.min\(naturalHeight, pos\.height\)", code), (
        "die gemessene Hoehe wird nicht gegen den Deckel gehalten")


def test_the_cap_counts_three_limits_and_names_them_all():
    """Wunsch, Anteil, Platz - und der Anteil geht auf den GANZEN Schirm.

    So steht es in src/sizes.py ("wie viel vom Schirm") und so tut es
    menu/zepos_menu/window.py, das gegen die Monitorgeometrie deckelt.
    Zwei Programme, die denselben Anteil auf zwei verschiedene Bezugs-
    groessen rechnen, waeren zwei verschiedene Regeln mit einem Namen.
    """
    code = _code(OVERLAY)
    for bound in ("winHeight", "mh * MODAL_SHARE", "usableH - 2 * EDGE_GAP"):
        assert bound in code, f"die Hoehe wird nicht mehr gegen {bound} gedeckelt"
    for bound in ("winWidth", "mw * MODAL_SHARE", "usableW - 2 * EDGE_GAP"):
        assert bound in code, f"die Breite wird nicht mehr gegen {bound} gedeckelt"


def test_a_cut_off_word_gets_a_scrollbar_beside_it():
    """Eine schwebende Leiste, die erst bei Beruehrung erscheint, sagt
    einem Bild gar nichts.

    GEMESSEN am 12.08.2026: das gedeckelte Kontrollzentrum endete mitten
    in der Ueberschrift "TON & BILD", und nichts daran unterschied den
    behobenen Zustand vom kaputten.
    """
    assert "overlay_scrolling: false" in _code(OVERLAY), (
        "die Bildlaufleiste schwebt wieder ueber dem Inhalt und ist damit "
        "unsichtbar, solange niemand hineinfaehrt")


def test_every_overlay_declares_a_size_that_was_measured():
    """Die beiden Fenster, um die es ging, tragen ihre gemessenen Masse.

    Nicht die Zahl wird geprueft - die aendert sich mit jedem Inhalt -,
    sondern dass es keine der ALTEN gibt. 400x580 und 420x480 sind die
    Masse aus der Zeit, in der sie nirgends ankamen; wer sie
    zurueckschreibt, hat den Befund nicht gelesen.
    """
    control = _code(CONTROL)
    assert "width: 400," not in control and "height: 580," not in control, (
        "das Kontrollzentrum meldet wieder 400x580 an - die Masse, die "
        "nie eines Fensters waren")
    calendar = _code(CALENDAR)
    assert "const WIN_HEIGHT = 480" not in calendar, (
        "der Kalender meldet wieder 480 Punkte Hoehe an; gemessen sind "
        "678 fuer einen Monat mit sechs Wochenzeilen")


# Welches Fenster in welchem Kasten sitzt. Die Breite, die ein Fenster
# anmeldet, und die min-width des Kastens darin sind ZWEI Zahlen, die
# Verschiedenes messen - der Deckel des Fensters und der Anspruch des
# Inhalts. Beim Kalender waren beide 420, und daran ist der Sonntag
# verlorengegangen.
FENSTER_UND_KASTEN = {
    "ags-calendar.template": ".calendar-container",
    "ags-shortcuts.template": ".shortcuts-container",
    "ags-battery.template": ".battery-container",
    "ags-disk.template": ".disk-container",
    "ags-wallpaper.template": ".wp-container",
    "ags-style-editor.template": ".se-container",
    "ags-vpn.template": ".vpn-container",
    "ags-vpn-settings.template": ".vpn-settings-container",
}

# Die beiden, deren Kasten mit Absicht keine min-width hat. Der Grund
# steht in ags-style.template ueber .bt-power-btn: "Die Groesse kommt aus
# Schrift und Innenabstand, also aus der Leiter in src/sizes.py, und
# nicht aus einem min-width daneben." Ohne min-width gibt es hier nichts
# nachzurechnen - aber es muss AUFGESCHRIEBEN sein, sonst faellt ein
# neues Fenster einfach aus dieser Zusicherung heraus.
OHNE_MIN_WIDTH = {"ags-network.template", "ags-bluetooth.template"}

# DIE SENKRECHTE BILDLAUFLEISTE, GEMESSEN und nicht geschaetzt.
#
#     utils/overlay.ts fragt sie selbst
#     (scroller.get_vscrollbar()?.measure(...)) und rechnet sie IMMER
#     dazu - der Grund steht dort und ist gemessen: der Inhalt dieser
#     Fenster aendert sich, solange sie offen sind, und die Leiste kommt
#     und geht damit. Hier kann sie nicht gefragt werden, weil in dieser
#     Suite kein Anzeigegeraet laeuft; die 24 sind der Wert aus dem Lauf
#     vom 17.08.2026, der auch alle Inhaltsbreiten gemessen hat.
BILDLAUFLEISTE = 24


def _style_sheet() -> str:
    return (SRC / "templates" / "ags-style.template").read_text(
        encoding="utf-8")


def _rule(style_sheet: str, selector: str) -> str:
    """Der Rumpf einer CSS-Regel, bis zur Klammer AM ZEILENANFANG.

    Ein `.*?\\}` faende das `}` in `{{STYLE_RADIUS_PANEL}}` und haette
    den Block nach drei Zeilen beendet - die Werte, um die es geht,
    stehen darunter.
    """
    found = re.search(re.escape(selector) + r" \{\n(.*?)\n\}",
                      style_sheet, re.S)
    assert found, f"es gibt keine Regel {selector} mehr"
    return found.group(1)


def _space(placeholder: str) -> int:
    """Ein Abstand aus dem Stilsystem, in Punkten."""
    import importlib
    import sys

    sys.path.insert(0, str(SRC))
    try:
        style = importlib.import_module("style_definition")
        return int(str(style.STYLE_VARIABLES[placeholder]).rstrip("px"))
    finally:
        sys.path.remove(str(SRC))


def test_every_overlay_is_wider_than_the_box_its_content_sits_in():
    """Sechs Fenster meldeten weniger Breite an, als ihr Inhalt braucht.

    GEMELDET, woertlich: "die ags fenster sind so eingequetscht das man
    nach rechts und nach unten scrollen muss", und daneben, dass die
    Akkuanzeige mit Prozentzeichen nicht zu sehen sei.

    ANGEFANGEN HAT ES BEIM KALENDER, am 17.08.2026: das Gitter hat sieben
    Spalten, zu sehen waren sechs - der Sonntag lag hinter der rechten
    Kante. Das Gitter war nie zu breit (es misst sich 259). Zu klein war
    das FENSTER, und zwar um genau das, was der Kasten kostet, in dem das
    Gitter sitzt: `.calendar-container` traegt `min-width: 420px` UND ein
    padding, und `const WIN_WIDTH` stand ebenfalls auf 420. Zwei Zahlen
    420, die Verschiedenes messen, waren gleichgesetzt.

    GEMESSEN am selben Tag im verschachtelten Compositor, Schirm
    1920x1080, je einmal unter de_DE.UTF-8 und en_US.UTF-8: derselbe
    Fehler stand in fuenf weiteren Fenstern. Was der Inhalt brauchte,
    was das Fenster anmeldete:

        Speicherplatz     556 / 500     Hintergruende  576 / 520
        Stil-Editor       474 / 420     VPN            476 / 420
        VPN-Einstellungen 642 / 500     Akku           581 / 320

    Bei den Hintergruenden waren es sogar 614: die Bildchen kommen erst
    in onShow und damit NACH der Messung der Fabrik.

    WARUM DIESE ZUSICHERUNG DIE ADDITION NACHRECHNET UND KEINE ZAHL LIEST
        Eine Zusicherung auf die Zahl selbst faellt bei jedem neuen
        Inhalt und sagt nie, warum. Diese hier faellt genau dann, wenn
        das Verhaeltnis kippt: wenn jemand eine min-width erhoeht, wenn
        das padding aus dem Stilsystem waechst - es folgt dem
        Groessenregler - oder wenn eine Fensterbreite wieder auf den Wert
        ihrer min-width gesetzt wird.

    WAS SIE NICHT PRUEFT
        Ob der Inhalt DARIN passt. Ein Kasten kann breiter sein als seine
        min-width - beim Stil-Editor ist es die Reiterleiste (398), bei
        den VPN-Einstellungen die Knopfreihe unten (566 auf Deutsch).
        Das misst tests/render/, an einem echten Compositor, mit einem
        Bild daneben. Hier steht die Untergrenze, die ohne Anzeigegeraet
        nachrechenbar ist.
    """
    style_sheet = _style_sheet()
    rahmen = re.search(r"^\s*border:\s*(\d+)px",
                       _rule(style_sheet, ".overlay-outer"), re.M)
    assert rahmen, "die Platte der Aufklappfenster hat keinen Rahmen mehr"

    erklaert = {path.name: found.group(1)
                for path in sorted((SRC / "templates").glob("ags-*.template"))
                for found in [re.search(r"^const WIN_WIDTH = (\d+)$",
                                        path.read_text(encoding="utf-8"),
                                        re.M)]
                if found}
    vergessen = set(erklaert) - set(FENSTER_UND_KASTEN) - OHNE_MIN_WIDTH
    assert not vergessen, (
        f"{', '.join(sorted(vergessen))} meldet eine Breite an, steht aber "
        "in keiner der beiden Listen dieser Datei. Entweder gehoert der "
        "Kasten dazu, in dem sein Inhalt sitzt, oder der Grund, aus dem "
        "es keinen mit min-width gibt")

    for vorlage, kasten in sorted(FENSTER_UND_KASTEN.items()):
        rumpf = _rule(style_sheet, kasten)
        innen = re.search(r"min-width:\s*(\d+)px", rumpf)
        assert innen, (
            f"{kasten} hat keine min-width mehr - dann gehoert {vorlage} "
            "nicht mehr in diese Liste, sondern in OHNE_MIN_WIDTH, und "
            "zwar mit dem Grund daneben")
        polster = re.search(r"padding:\s*\{\{(STYLE_SPACE_\d+)\}\}", rumpf)
        assert polster, (
            f"das padding von {kasten} ist kein Platzhalter mehr - dann "
            "folgt es dem Groessenregler nicht, und diese Rechnung auch "
            "nicht")
        space = _space(polster.group(1))

        noetig = (int(innen.group(1)) + 2 * space
                  + 2 * int(rahmen.group(1)) + BILDLAUFLEISTE)
        assert vorlage in erklaert, (
            f"{vorlage} meldet keine Breite mehr an")
        assert int(erklaert[vorlage]) >= noetig, (
            f"{vorlage} meldet {erklaert[vorlage]} Punkte Breite an, der "
            f"Kasten darin braucht {noetig} ({innen.group(1)} min-width "
            f"+ 2x{space} padding + 2x{rahmen.group(1)} Rahmen "
            f"+ {BILDLAUFLEISTE} Bildlaufleiste). Die Differenz faellt "
            "hinter die rechte Kante")


# --------------------------------------------------------------------
# Der Rand
# --------------------------------------------------------------------

def test_the_overlays_hold_the_same_edge_gap_as_the_bar():
    """Eine Zahl fuer den Schirmrand, nicht zwei.

    GEMESSEN am 12.08.2026 auf einem Bildschirmabzug: der Kalender
    begann bei x=20, die Leiste darueber bei x=24. Die 20 stand als
    `const edgePad = 20` in der Fabrik, die 24 kam aus
    {{STYLE_GAPS_OUT}} - vier Punkte Versatz, sichtbar, und keiner der
    beiden Werte wusste vom anderen.
    """
    overlay = _code(OVERLAY)
    assert "const EDGE_GAP = {{STYLE_GAPS_OUT}}" in overlay, (
        "die Aufklappfenster holen ihren Randabstand nicht mehr aus dem "
        "Stilsystem")
    assert "const EDGE_GAP = {{STYLE_GAPS_OUT}}" in _code(BAR), (
        "die Leiste holt ihn woanders her - dann ist die Gleichheit "
        "wieder Zufall")
    assert "edgePad" not in overlay, (
        "es gibt wieder eine zweite Randzahl neben der aus dem Stilsystem")


# --------------------------------------------------------------------
# Der Kalender
# --------------------------------------------------------------------

def test_the_week_of_the_calendar_starts_on_monday():
    """ISO 8601 und DIN 1355-1, und auf Deutsch.

    GEMESSEN am 12.08.2026: unter der deutschen Zeile "Mittwoch / 12.
    August 2026" stand eine Wochenzeile "Sun Mon Tue ..." mit Sonntag
    vorn. Beides schrieb dieselbe Datei - die eine Haelfte selbst, die
    andere ueberliess sie dem Gtk.Calendar, der sie aus der Locale nimmt.
    """
    code = _code(CALENDAR)

    # SEIT DEM 17.08.2026 WIRD ETWAS ANDERES GEMESSEN, und die Regel ist
    # dieselbe geblieben.
    #
    #     Bis dahin las diese Zusicherung `const WEEKDAY_HEADS = ["Mo",
    #     "Di", ...]`, also eine DEUTSCHE Tabelle in der Vorlage. Genau
    #     die ist weg: der Nutzer hat gemeldet, die Oberflaeche trage
    #     fest verdrahtetes Deutsch, und eine Wochenzeile, die auf einer
    #     englischen Installation "Mo Di Mi" schreibt, ist der Befund
    #     und nicht seine Behebung. Die Namen kommen jetzt aus der
    #     Sitzung (%a), wie jede andere Beschriftung dieses Fensters
    #     auch - siehe tests/src/test_ags_i18n.py.
    #
    #     Der WOCHENBEGINN ist davon unberuehrt und wird weiter
    #     zugesichert: er ist eine Norm (ISO 8601, DIN 1355-1) und keine
    #     Sprache. Er steht an zwei Stellen, und beide werden hier
    #     nachgerechnet - der Anker von weekdayHead() muss ein Montag
    #     sein, und firstColumn() muss Date.getDay() um sechs drehen.
    #
    #     Der Befund vom 12.08.2026 kann dadurch nicht zurueckkommen. Er
    #     entstand, weil die eine Haelfte des Fensters aus der Locale kam
    #     und die andere aus einer deutschen Tabelle; jetzt kommen beide
    #     aus derselben Quelle.
    anker = re.search(r"GLib\.DateTime\.new_local\(\s*(\d+),\s*(\d+),"
                      r"\s*(\d+)\s*\+\s*column", code)
    assert anker, "weekdayHead() rechnet nicht mehr von einem festen Tag aus"
    jahr, monat, tag = (int(gruppe) for gruppe in anker.groups())
    assert date(jahr, monat, tag).weekday() == 0, (
        f"der Anker der Wochenzeile ist der {tag}.{monat}.{jahr} und damit "
        "kein Montag - die Spalten stuenden um so viele Tage verschoben")

    assert re.search(r"getDay\(\)\s*\+\s*6\s*\)\s*%\s*7", code), (
        "firstColumn() dreht nicht mehr um sechs - der Erste faellt damit "
        "in die Spalte einer Woche, die am Sonntag beginnt")

    assert "new Gtk.Calendar" not in code, (
        "der Gtk.Calendar ist zurueck; mit ihm sein eigener Wochenbeginn "
        "als zweite Quelle neben firstColumn()")


def test_the_calendar_marks_today_in_the_colour_of_the_house():
    """Der markierte Tag sass auf Adwaita-Blau.

    ags-style.template fuehrt `.calendar-widget:selected` mit dem
    Kalenderakzent - eine Regel, die nie gegriffen hat, weil :selected am
    Tagesfeld TIEF im Gtk.Calendar sitzt und nicht am Widget selbst. Was
    man sah, war GTKs eigene Auswahlfarbe mitten in einer Oberflaeche aus
    ZepOS-Cyan und -Gelb.

    Die Regeln der selbst gebauten Tagesfelder stehen jetzt in der Datei,
    die die Felder baut - und keine einzige Farbe darin ist eine Zahl.
    """
    text = CALENDAR.read_text(encoding="utf-8")
    found = re.search(r"const DAY_STYLE = `(.*?)`", text, re.S)
    assert found, "der Kalender bringt keine Regeln fuer seine Tage mehr mit"
    rules = found.group(1)
    assert "{{STYLE_COLOR_CALENDAR_ACCENT}}" in rules, (
        "der heutige Tag traegt nicht mehr den Kalenderakzent")
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", rules), (
        "in den Regeln der Tagesfelder steht wieder eine Farbe als Zahl")
    assert not re.findall(r"(?:font-size|padding|border-radius):\s*[\d.]+\s*(?:px|pt)",
                          rules), (
        "in den Regeln der Tagesfelder steht wieder eine Groesse als Zahl")


def test_the_calendar_offers_only_programs_this_machine_has():
    """Zwei Knoepfe, hinter denen nichts passierte.

    GEMESSEN am 12.08.2026: weder gnome-calendar noch thunderbird steht
    in einem der drei Anwendungspakete - ZepOS liefert keinen Kalender
    und kein Mailprogramm aus. Derselbe Befund wie beim Druckerknopf
    (Spec §7.4), nur zweimal.
    """
    code = _code(CALENDAR)
    assert "GLib.find_program_in_path(" in code, (
        "der Kalender bietet seine Programme wieder an, ohne nachzusehen, "
        "ob es sie gibt")
    for program in ("gnome-calendar", "thunderbird"):
        assert program not in _shipped_applications(), (
            f"{program} wird inzwischen ausgeliefert - dann darf sein Knopf "
            f"auch ohne Nachsehen stehen, und diese Zusicherung ist falsch")


def _shipped_applications() -> set[str]:
    """Die ausgelieferte Anwendungsauswahl, aus src/apps.py gelesen."""
    import importlib
    import sys

    sys.path.insert(0, str(SRC))
    try:
        apps = importlib.import_module("apps")
        return set(apps.shipped(SRC))
    finally:
        sys.path.remove(str(SRC))


# --------------------------------------------------------------------
# Das Kontrollzentrum
# --------------------------------------------------------------------

def test_the_control_centre_speaks_one_language():
    """Englische Ueberschriften ueber deutschen Zeilen.

    GEMESSEN am 12.08.2026 auf einem Bildschirmabzug: der Titel hiess
    "Control Center", die Abschnitte "NETWORK & CONNECTIVITY" und "AUDIO
    & DISPLAY", und darunter stand "Nicht verbunden", "VPN: Aus", "Aus".

    WORAN DAS SEIT DEM 17.08.2026 GEMESSEN WIRD, und warum es gewechselt
    hat
        Bis dahin stand hier: diese deutschen Woerter muessen in der
        Vorlage stehen, diese englischen nicht. Das WAR die Regel,
        solange die Vorlage die Sprache selbst trug.

        Sie tut es nicht mehr. Der Nutzer hat gemeldet, "meinche UI
        Elemente sind noch Deutsch und nicht variabel", und die Antwort
        darauf ist, dass jede Beschriftung durch einen Katalog laeuft -
        der msgid ist Englisch, das Deutsche steht in po/desktop/de.po.
        Eine Zusicherung, die deutsche Woerter IN DER VORLAGE verlangt,
        verlangt damit genau den Zustand zurueck, der gemeldet wurde.

        Die Absicht bleibt Wort fuer Wort dieselbe: KEINE Mischung. Sie
        wird nur eine Ebene tiefer geprueft - der msgid steht in der
        Vorlage, und zu jedem msgid MUSS es einen deutschen Eintrag
        geben. Dann liest ein deutscher Nutzer Deutsch und ein
        englischer Englisch, und keiner von beiden liest beides.

        Dass ueberhaupt keine Beschriftung am Katalog vorbeigeht,
        sichert tests/src/test_ags_i18n.py fuer alle elf Fenster zu -
        mit zwei voneinander unabhaengigen Suchen, weil eine von ihnen
        die fuenf Knoepfe unten in diesem Fenster nicht gesehen hat.

    "Style editor" ist die eine Ausnahme und steht deshalb hier: es ist
    der NAME des Fensters, das die Zeile oeffnet. Eine Zeile, die anders
    heisst als das, was sie aufmacht, waere ein zweiter Name fuer eine
    Sache.
    """
    code = _code(CONTROL)
    katalog = (Path(__file__).resolve().parents[2]
               / "po" / "desktop" / "de.po").read_text(encoding="utf-8")

    # Links der msgid, wie er in der Vorlage steht. Rechts das, was ein
    # deutscher Nutzer an dieser Stelle lesen muss.
    ZEILEN = {
        "Control center": "Kontrollzentrum",
        "NETWORK & CONNECTIONS": "NETZ & VERBINDUNGEN",
        "SOUND & DISPLAY": "TON & BILD",
        "SYSTEM SERVICES": "SYSTEMDIENSTE",
        "Helper scripts": "Hilfsskripte",
        "Network watchdog": "Netz-Watchdog",
        "Shut down": "Herunterfahren",
        "Restart": "Neustart",
        "Suspend": "Bereitschaft",
        "Lock": "Sperren",
        "Log out": "Abmelden",
        "Style editor": "Stil-Editor",
    }
    for msgid, deutsch in ZEILEN.items():
        assert f'_("{msgid}")' in code, (
            f'"{msgid}" laeuft nicht mehr durch den Katalog - die Zeile '
            "traegt wieder eine feste Sprache")
        assert f'msgid "{msgid}"\nmsgstr "{deutsch}"' in katalog, (
            f'"{msgid}" hat keinen deutschen Eintrag "{deutsch}" - ein '
            "deutscher Nutzer laese an dieser Stelle Englisch, mitten in "
            "einem Fenster, dessen Rest uebersetzt ist")


def test_a_row_with_nothing_in_it_is_not_drawn():
    """Die leere Ethernet-Zeile.

    GEMESSEN am 12.08.2026: ohne Verbindung zeigte das Kontrollzentrum
    eine Zeile in voller Hoehe mit einem Symbol und einem Gedankenstrich.
    Der Strich war der Grund - er machte aus "keine Adresse" ein
    "irgendeine Zeichenkette", und die Zeile konnte die Leere nicht mehr
    sehen.
    """
    code = _code(CONTROL)
    assert 'runScript("ip") || "—"' not in code, (
        "die IP-Abfrage gibt wieder ein Ersatzzeichen zurueck")
    assert "ipRow.set_visible(" in code, (
        "die IP-Zeile blendet sich nicht mehr aus, wenn es keine Adresse "
        "gibt")


def test_the_five_switches_stand_in_three_columns():
    """Warum die Sprache das Layout anfassen musste.

    GEMESSEN am 12.08.2026: "Herunterfahren" ist bei
    {{STYLE_FONT_MICRO}} vierzehn Zeichen; fuenf solche Knoepfe
    nebeneinander haetten das Fenster von gemessenen 545 auf ueber 800
    Punkte verbreitert. In drei Spalten misst es 495 - fuenfzig Punkte
    WENIGER als mit den englischen Woertern in einer Reihe.
    """
    code = _code(CONTROL)
    assert "column_homogeneous: true" in code and "powerGrid.attach(" in code, (
        "die fuenf Schalter stehen wieder in einer Reihe; mit den "
        "deutschen Woertern waere das Fenster ueber 800 Punkte breit")



# --------------------------------------------------------------------
# Das Bluetooth-Fenster
# --------------------------------------------------------------------

def test_every_question_to_bluetoothctl_carries_a_deadline():
    """Der Grund, aus dem es dieses Fenster ueberhaupt gibt.

    GEMELDET am 17.08.2026: "wenn ich auf meinem zepos system versuche
    das auszufuehren stuckt er freeze es passiert nichts" - ueber
    ags/scripts/status.sh, aus dem Ton, Mikrofon, Akku, Netz und
    Bluetooth kommen.

    `bluetoothctl show` wartet auf org.bluez am Systembus. Laeuft
    bluetoothd nicht, kommt der Name nie, und das Werkzeug kehrt nicht
    zurueck. bar-status-config.template hat dafuer `frag` bekommen (also
    `timeout 3`); dieselbe Regel gilt hier, sonst haengt das FENSTER
    statt des Skripts.

    GEPRUEFT wird jeder Aufruf und nicht nur die Hilfsfunktion: `scan on`
    und `connect` laufen an ihr vorbei, weil sie andere Fristen
    brauchen - und genau die zwei sind die, die von Natur aus warten.
    """
    code = _code(BLUETOOTH)

    # Gesucht wird am AUFRUF und nicht an jeder Zeile, die das Wort
    # enthaelt: die Datei erklaert an mehreren Stellen, was bluetoothctl
    # tut, und eine Textsuche wuerde von der Erklaerung falsch.
    aufrufe = []
    for stelle in re.finditer(r"execAsync\(", code):
        rumpf = code[stelle.start():stelle.start() + 220]
        if "bluetoothctl" in rumpf:
            aufrufe.append(" ".join(rumpf.split())[:120])
    assert aufrufe, "die Vorlage ruft bluetoothctl gar nicht mehr"
    ohne = [aufruf for aufruf in aufrufe if "timeout" not in aufruf]
    assert ohne == [], (
        "diese Aufrufe haben keine Frist - einer davon genuegt, damit "
        "das Fenster steht statt zu antworten: " + "; ".join(ohne))


def test_a_bluetoothctl_that_does_not_answer_gets_a_sentence():
    """Ein Werkzeug, das schweigt, ist etwas anderes als ein fehlendes
    Geraet - dieselbe Regel wie in bar-status-config.template.

    Und der Satz nennt den Befehl, der es behebt. GEMESSEN am 17.08.2026
    an der Testinstallation: bluez war da, bluetooth.service war NICHT
    aktiviert, und ohne den Alias dbus-org.bluez.service kann der
    Systembus org.bluez weder starten noch vermitteln.
    """
    code = _code(BLUETOOTH)
    assert "systemctl enable --now bluetooth.service" in code, (
        "der Fehlerfall nennt den Befehl nicht mehr, der ihn behebt")
    assert 'fehler: string' in code, (
        "die Auskunft 'antwortet nicht' ist nicht mehr von 'kein "
        "Adapter' zu unterscheiden")


def test_no_button_of_the_bluetooth_window_stands_there_without_a_target():
    """Spec §7.4 an der Stelle, an der sie am leichtesten faellt.

    Ohne Adapter kann man nichts einschalten und nichts suchen lassen.
    Ein Knopf, der dann trotzdem so aussieht wie immer, ist einer, hinter
    dem nichts passiert.
    """
    code = _code(BLUETOOTH)
    for knopf in ("powerBtn", "scanBtn"):
        assert f"{knopf}.set_sensitive(false)" in code, (
            f"{knopf} bleibt bedienbar, auch wenn es nichts zu bedienen "
            "gibt")
    # Und der dritte Knopf fuehrt zu einem Programm, das ZepOS
    # ausliefert: blueman ist harte Abhaengigkeit von zepos-desktop.
    # tests/src/test_usable_desktop.py haelt diese Richtung ueber den
    # ganzen Baum; hier steht, dass es diesen Weg ueberhaupt noch gibt.
    assert 'execAsync("blueman-manager")' in code, (
        "der Weg zu den Nebenfunktionen - Koppeln, Dateien senden - ist "
        "aus dem Fenster verschwunden")
