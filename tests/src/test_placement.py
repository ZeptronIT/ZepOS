# SPDX-License-Identifier: GPL-3.0-or-later
"""Kopf und Fuss: wo sie liegen, was sie reservieren, und der EINE Abstand.

WAS GEMELDET WURDE
    Der Nutzer am 11.08.2026: "bitte eine eigene sidebar verwenden
    schaue dafuer bitte auf summer-day-and-night dieses theme koennen
    wir gut fuer ZepOS verwenden ich will nur es oben breiter machen die
    fenster auch den selben abstand zum rand nutzen usw."

    Und am 12.08.2026, nachdem er das Ergebnis gesehen hatte: "ich
    haette unsere gebaute waybar bitte oben nicht links ja und nwg dock
    auch nachgebaut gtk4 immer angezeigt unten im footer sozusagen".

WARUM DIESE DATEI test_placement.py HEISST UND NICHT MEHR test_sidebar.py
    Weil sie zwei Drehungen ueberlebt hat und die naechste ueberleben
    soll. Eine Datei, die nach der Kante benannt ist, an der die Leiste
    gerade klebt, muss bei jeder Aenderung umbenannt werden - und wird
    es beim ersten Mal nicht, und heisst dann falsch. Was hier steht,
    ist die PLATZIERUNG von Leiste und Dock, und das bleibt die Frage,
    egal wie die Antwort ausfaellt.

WAS DIESE DATEI BEWACHT UND WAS NICHT
    Sie prueft die STRUKTUR: die Anker, die Reservierung, und dass der
    Abstand der Fenster zum Rand und der Abstand der Leiste zum Rand
    dieselbe Zahl sind statt zweier, die zufaellig gleich aussehen.

    Was daraus auf dem Schirm wird - welches Modul wo liegt, was
    eingeklappt wird, ob etwas abgeschnitten ist, was der Fuss an Hoehe
    kostet - misst tests/src/test_bar_headless.py an einer echten
    GTK4-Anzeige. Die Trennung ist dieselbe wie ueberall in diesem
    Verzeichnis: hier steht, was in der Vorlage steht, dort, was daraus
    wird.

WARUM DER ABSTAND UEBERHAUPT EINE ZUSICHERUNG BRAUCHT
    "Derselbe Abstand" ist die Art Eigenschaft, die beim Schreiben
    stimmt und beim naechsten Anfassen verlorengeht, ohne dass irgendwo
    etwas kaputtgeht. Zwei Dateien tragen die Zahl - das Stylesheet der
    Leiste und die Hyprland-Konfiguration -, und solange jede ihre eigene
    hat, ist jede Uebereinstimmung ein Zufall. Genau dieses Argument hat
    schon die Abstandsleiter in src/sizes.py begruendet.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src import sizes

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
BAR = SRC / "templates" / "ags-bar.template"
DOCK = SRC / "templates" / "ags-dock.template"
BAR_STYLE = SRC / "styles" / "bar-style.template"
HYPRLAND = SRC / "templates" / "hyprland-universal-config.template"


def _code(path: Path, marker: str) -> str:
    """Die Datei ohne ihre Kommentare.

    Jede Datei in diesem Baum ERKLAERT, was sie nicht mehr tut - und eine
    Suche nach "WindowAnchor.LEFT" wird von der Erklaerung wahr, in der
    steht, dass der Anker nicht mehr links ist.
    """
    text = path.read_text(encoding="utf-8")
    if marker == "/*":
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        return text
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith(marker))


def _rule(css: str, selector: str) -> str:
    """Der Rumpf einer CSS-Regel, mit Platzhaltern darin.

    Von Hand geklammert und nicht mit `\\{(.*?)\\}`: ein Platzhalter
    heisst {{NAME}}, und die naechste schliessende Klammer nach
    "#bar {" ist deshalb die von {{STYLE_GLASS_PANEL}} und nicht das
    Ende der Regel. Der erste Anlauf dieser Datei hatte genau den
    Fehler und meldete, die Platte habe keine Kante mehr.
    """
    start = css.index(selector + " {") + len(selector) + 2
    depth = 1
    index = start
    while depth:
        if css.startswith("{{", index):
            index += 2
            continue
        if css.startswith("}}", index):
            index += 2
            continue
        if css[index] == "{":
            depth += 1
        elif css[index] == "}":
            depth -= 1
        index += 1
    return css[start:index - 1]


def _anchors(code: str) -> set[str]:
    """Die Anker einer Astal.Window, aus dem Quelltext gelesen."""
    found = re.search(r"anchor:\s*([^,]*(?:\n[^,]*)*?),\s*\n\s*exclusivity",
                      code)
    assert found, "die Flaeche setzt keinen Anker mehr"
    return set(re.findall(r"WindowAnchor\.(\w+)", found.group(1)))


# --------------------------------------------------------------------
# Wo die Leiste liegt und was sie reserviert
# --------------------------------------------------------------------

def test_the_bar_is_anchored_to_the_top_edge_and_not_the_left():
    """Die Drehung selbst, an der Stelle, an der sie stattfindet.

    Drei Anker und nicht einer: mit TOP allein waere die Flaeche so
    breit wie ihr Inhalt statt so breit wie der Schirm. LEFT und RIGHT
    ziehen sie ueber die volle Breite, und erst dadurch reserviert sie
    einen STREIFEN statt eines Kastens.

    BOTTOM darf nicht dabei sein, und das ist die Zeile, die die
    Drehung wirklich macht: mit TOP|BOTTOM|LEFT|RIGHT reservierte die
    Leiste den ganzen Schirm.
    """
    used = _anchors(_code(BAR, "//"))
    assert used == {"TOP", "LEFT", "RIGHT"}, (
        f"die Leiste haengt an {sorted(used)} statt oben ueber die volle "
        "Breite")


def test_the_bar_still_reserves_its_strip():
    """Ohne die Reservierung liegt die Leiste UEBER den Fenstern.

    Astal rechnet die exklusive Zone aus Anker und Groesse; der
    Ankerwechsel oben verschiebt sie also von links nach oben. Dass sie
    ueberhaupt noch angefordert wird, ist die Voraussetzung dafuer - und
    eine Zeile, die man beim Umbauen sehr leicht mitnimmt.
    """
    assert "Astal.Exclusivity.EXCLUSIVE" in _code(BAR, "//"), (
        "die Leiste reserviert sich keinen Platz mehr - sie laege ueber "
        "den Fenstern")


def test_the_bar_is_as_thick_as_the_table_and_as_wide_as_the_screen():
    """set_default_size bekommt die Dicke als HOEHE, nicht als Breite.

    Auf der Seitenleiste stand hier `set_default_size(BAR_THICKNESS, 1)`,
    also "so dick wie die Tabelle sagt, so hoch wie noetig". Vertauscht
    ergaebe das jetzt eine Flaeche von einem Pixel Hoehe.

    Seit dem 12.08.2026 steht dort BAR_THICKNESS + EDGE_GAP. Die Flaeche
    traegt oben einen Rand und unten keinen, ist also um genau diesen
    Rand hoeher als das, was sie BEMALT. Vorher lag der Rand IN der Zahl
    und der Kopf malte 59 Punkte, waehrend der Fuss dieselbe Zahl als
    bemalte Hoehe las und 83 malte. Gemessen wird das seither an
    Bildpunkten, in tests/render/test_geometry.py.
    """
    code = _code(BAR, "//")
    assert "window.set_default_size(1, BAR_THICKNESS + EDGE_GAP)" in code, (
        "die Flaeche bekommt ihre Dicke nicht als HOEHE, oder sie zaehlt "
        "den Rand nicht dazu")


def test_the_bar_reads_the_width_of_its_monitor_and_not_the_height():
    """Die Engstelle einer Kopfleiste ist die Breite des Schirms.

    BarContent() bekommt eine Funktion, die diese Zahl liefert, und
    entscheidet daran, was eingeklappt wird. Mit der HOEHE darin
    rechnete die Leiste auf jedem Querformat mit zu wenig Platz und
    klappte ein, was hingepasst haette - ein Fehler, den kein Absturz
    und keine Warnung meldet.
    """
    code = _code(BAR, "//")
    assert "() => monitor.get_geometry().width" in code, (
        "die Leiste fragt ihren Schirm nach der falschen Achse")


def test_the_three_boxes_and_the_centrebox_all_run_horizontally():
    """Vier Achsen, und drei davon zu drehen reicht nicht.

    GEMESSEN am 11.08.2026: der erste Anlauf der Gegenrichtung drehte
    die drei Kaesten und vergass das Gtk.CenterBox selbst. Die drei
    standen damit als SPALTEN nebeneinander - die Leiste verlangte
    250 px Breite bei 185 px Dicke, und der obere wie der untere Kasten
    begannen bei y=48.

    Ein Gtk.CenterBox ist von sich aus waagerecht, die Zeile
    wiederholte also nur die Vorgabe - wenn sie nicht genau die waere,
    die beim letzten Drehen gefehlt hat.
    """
    code = _code(BAR, "//")
    assert "bar.set_orientation(Gtk.Orientation.HORIZONTAL)" in code, (
        "das CenterBox laeuft noch senkrecht - seine drei Kaesten stehen "
        "dann uebereinander statt nebeneinander")

    boxes = re.findall(
        r'(\w+)\.set_name\("modules-(?:left|center|right)"\)', code)
    assert len(boxes) == 3, "es sind nicht mehr drei Kaesten"
    for name in ("left", "centre", "right"):
        assert re.search(
            rf"const {name} = new Gtk\.Box\(\{{ orientation: "
            rf"Gtk\.Orientation\.HORIZONTAL \}}\)", code), (
            f"der Kasten {name} laeuft noch senkrecht")


def test_the_two_growing_modules_spread_instead_of_stacking():
    """Die Arbeitsbereiche und die Statusablage wachsen mit dem, was der
    Nutzer tut - und muessen deshalb ZUR SEITE wachsen.

    Auf der Seitenleiste stapelten sie senkrecht, weil zehn
    Arbeitsbereiche nebeneinander bei Vorgabegroesse 439 px breit sind
    und damit weit ueber den 155 px lagen, die einem Modul dort blieben.
    Auf einer Kopfleiste ist Breite das, wovon es viel gibt, und Hoehe
    das, was knapp ist: senkrecht gestapelt machte die Ablage die Leiste
    mit ihrem dritten Symbol dreimal so dick.

    WARUM DIE ABLAGE HIER STEHT UND NICHT IN DER KOPFLOSEN MESSUNG
        Sie ist dort LEER, und das mit Absicht: tests/src/
        test_bar_headless.py zeigt auf einen Sitzungsbus, den es nicht
        gibt, damit ein Testlauf nicht die Statusablage der laufenden
        Sitzung des Entwicklers uebernimmt. Eine leere Gtk.Box misst
        sich in beiden Achsen gleich, also kann keine Messung dort
        sehen, wie herum sie steht.

        NACHGEWIESEN, nicht vermutet: die Mutation "tray.set_orientation
        faellt weg" lief durch die ganze kopflose Messung, ohne dass
        eine der Zusicherungen dort etwas gemerkt haette. Deshalb steht
        sie hier - als Textpruefung, die schwaecher ist als eine Messung
        und besser als keine.
    """
    code = _code(BAR, "//")
    assert "tray.set_orientation(Gtk.Orientation.HORIZONTAL)" in code, (
        "die Statusablage laeuft noch senkrecht - sie machte die Leiste "
        "mit ihrem dritten Symbol dreimal so dick")
    assert re.search(
        r"const box = new Gtk\.Box\(\{ orientation: "
        r"Gtk\.Orientation\.HORIZONTAL \}\)\n\s*box\.set_name\(\"workspaces\"\)",
        code), "die Arbeitsbereiche stapeln noch senkrecht"


def test_the_workspaces_sit_in_the_middle_and_are_never_folded():
    """Die Mitte gehoert seit dem 12.08.2026 den Arbeitsbereichen.

    BESTELLT an dem Tag, woertlich: "in der mitte die arbeitsbereiche
    links die uhrzeit und datum den rest kennst du". Hier stand bis
    dahin `centre.append(window.widget)` - der Fenstertitel -, und die
    Begruendung dafuer war die richtige fuer die FRAGE, die sie
    beantwortete: was in der Mitte steht, wird gemessen und nie
    eingeklappt.

    Genau das ist der Grund, aus dem die Arbeitsbereiche jetzt dort
    stehen. Sie sind der Posten, den man mit einem Blick sucht und der
    sich mit jedem Tastendruck aendert; der Titel ist der Posten, der
    NACHGIBT, und Nachgeben kann er auch links.
    """
    code = _code(BAR, "//")
    assert "centre.append(workspaces.widget)" in code, (
        "die Arbeitsbereiche stehen nicht in der Mitte")
    assert "centre.append(window.widget)" not in code, (
        "der Fenstertitel haengt noch in der Mitte - dann stehen dort "
        "zwei Module uebereinander")


def test_the_window_title_gives_way_instead_of_being_folded():
    """Der Fenstertitel ist das eine Modul, das nachgibt statt zu weichen.

    Auf der Seitenleiste lag er im unteren Kasten und trug alwaysFold:
    seine Beschriftung ellipsiert und meldet damit QUER zur Leiste nicht
    die Breite ihres Textes, sondern das, worauf sie zu schrumpfen
    bereit ist - eine Spalte aus Auslassungspunkten. Laengs zur Leiste
    ist genau das die richtige Antwort.

    `alwaysFold` gibt es deshalb nicht mehr. Eine Ausnahme ohne Fall
    ist toter Code, und toter Code in einer Regel, die bei jedem Takt
    eines Moduls laeuft, ist der naechste Leser, der sich fragt, wofuer
    das gut war.

    SEIT DEM 12.08.2026 STEHT ER IN EINER LISTE, und damit ist "nie
    eingeklappt" keine Eigenschaft der Mitte mehr, sondern eine Zeile in
    place(): er kommt in seinen Kasten, aber nicht in `foldable` - und
    dafuer in `fixed`. Beide Haelften stehen hier, weil die eine ohne
    die andere ein Messfehler ist: nicht einklappbar UND nicht gemessen
    hiesse, dass die Leiste mit einem Modul rechnet, das nichts kostet.
    """
    code = _code(BAR, "//")
    assert "alwaysFold" not in code, (
        "alwaysFold hat keinen Fall mehr und steht trotzdem noch da")
    assert re.search(
        r"if \(widget === window\.widget\) \{\n\s*box\.append\(widget\)\n"
        r"\s*fixed\.push\(widget\)", code), (
        "der Fenstertitel wird wie jedes andere Modul aufgestellt - dann "
        "liegt er beim naechsten engen Schirm im Aufklappfenster")
    assert "const folding = foldingOf(bar, overflow, overflowTray, order, fixed)" \
        in code, ("die nicht einklappbaren Widgets gehen nicht in die "
                  "Rechnung des Einklappers ein")


# --------------------------------------------------------------------
# Wo das Dock liegt, und dass es dauerhaft dasteht
# --------------------------------------------------------------------

def test_the_dock_is_anchored_to_the_bottom_edge_only():
    """Unten und nur unten.

    Mit LEFT und RIGHT dazu zoege sich die Flaeche ueber die volle
    Breite. Sie reservierte dann denselben Streifen - aber der waere zu
    beiden Seiten des Docks leer, und ein Klick daneben ginge an das
    Dock statt an das Fenster darunter.
    """
    used = _anchors(_code(DOCK, "//"))
    assert used == {"BOTTOM"}, (
        f"das Dock haengt an {sorted(used)} statt allein unten")


def test_the_dock_reserves_its_strip_so_no_window_hides_it():
    """Eine Fusszeile, die unter dem untersten Fenster liegt, ist keine.

    Hier stand Exclusivity.IGNORE, mit der Begruendung, das Dock stehe
    ohnehin leer. Seit es die angehefteten Anwendungen zeigt, steht
    etwas darauf - und ein maximiertes Fenster verdeckte es.
    """
    assert "Astal.Exclusivity.EXCLUSIVE" in _code(DOCK, "//"), (
        "das Dock reserviert sich keinen Platz mehr - ein maximiertes "
        "Fenster laege darueber")


def test_the_dock_is_visible_without_anyone_pressing_a_key():
    """Der Wortlaut "immer angezeigt", woertlich genommen.

    Hier stand `visible: false`, mit der Begruendung, SUPER+B sei der
    Weg dorthin. Das stimmt weiterhin und ist der Weg wieder HERAUS;
    als einziger Weg HINEIN hiess es, dass ein Nutzer, der die Taste
    nicht kennt, nie ein Dock zu sehen bekam.

    Gesucht wird im Fensterrumpf und nicht in der ganzen Datei: das
    Wort steht auch im Rumpf der Leiste, und die steht dort absichtlich
    auf false und wird erst nach dem Einhaengen ihres Inhalts sichtbar.
    """
    code = _code(DOCK, "//")
    body = code[code.index("namespace: \"zepos-dock\""):]
    assert re.search(r"visible:\s*true", body.split("})")[0]), (
        "das Dock entsteht unsichtbar - dann sieht es nur, wer SUPER+B "
        "kennt")


def test_the_footer_keeps_its_margin_from_the_size_table():
    """Der Abstand zum unteren Schirmrand ist eine Groesse, kein Literal.

    Er gehoert zur reservierten Zone - gtk4-layer-shell rechnet sie aus
    der Groesse der Flaeche plus dem Aussenabstand an der verankerten
    Kante -, also ist er Teil dessen, was die Fusszeile kostet. Eine
    Zahl, die in den Preis eingeht, gehoert in die Tabelle, in der man
    sie sieht.
    """
    code = _code(DOCK, "//")
    assert "export const DOCK_MARGIN_BOTTOM = {{STYLE_GAPS_OUT}}" \
        in code, (
        "der Aussenabstand der Fusszeile kommt nicht aus derselben "
        "Groesse wie der der Leiste - siehe src/sizes.py, wo "
        "STYLE_DOCK_MARGIN_BOTTOM am 12.08.2026 dafuer entfallen ist")
    assert "window.set_margin_bottom(DOCK_MARGIN_BOTTOM)" in code, (
        "die Fusszeile setzt einen anderen Abstand, als sie exportiert")


# --------------------------------------------------------------------
# Der EINE Abstand zum Rand
# --------------------------------------------------------------------

def test_the_window_gaps_are_rungs_of_the_spacing_ladder():
    """Sonst bleibt "derselbe Abstand" nur beim ausgelieferten Faktor
    derselbe.

    Der Auftrag sagt es woertlich: die Abstaende muessen an die Leiter,
    damit sie auch beim Drehen des Reglers zusammenbleiben. Eine Zahl
    neben der Leiter waechst zwar mit - sie waechst nur nicht auf
    dieselben Werte wie alles andere.
    """
    for name in ("STYLE_GAPS_IN", "STYLE_GAPS_OUT"):
        base = sizes.TABLE[name].base
        assert base in sizes.SPACE_LADDER, (
            f"{name} steht auf {base} und damit neben der Leiter "
            + ", ".join(str(step) for step in sizes.SPACE_LADDER))
        assert sizes.TABLE[name].scales, (
            f"{name} folgt dem Faktor nicht - dann waechst die Leiste "
            "daneben und das Fensterraster nicht")
        assert sizes.TABLE[name].unit == sizes.BARE, (
            f"{name} traegt eine Einheit, und Hyprland liest eine nackte "
            "Zahl")


def test_every_visible_gap_is_the_same_number():
    """Die Rechnung hinter "die fenster auch den selben abstand zum rand
    nutzen".

    Hyprland legt gaps_in an JEDE Seite eines Fensters, gaps_out nur nach
    aussen. Zwischen zwei Fenstern sieht man deshalb 2*gaps_in, zum Rand
    gaps_out - und "ueberall derselbe Abstand" ist genau die Gleichung
    2*gaps_in == gaps_out.

    Die alten Werte erfuellten sie nicht: 5 und 20 sind 10 innen gegen
    20 aussen. Die Vorlage erfuellt sie (10 und 20), und die Leiter
    bietet dafuer nur drei Paare an - 4/8, 8/16 und 12/24.
    """
    inner = sizes.TABLE["STYLE_GAPS_IN"].base
    outer = sizes.TABLE["STYLE_GAPS_OUT"].base
    assert 2 * inner == outer, (
        f"zwischen zwei Fenstern stehen {2 * inner} px und zum Rand "
        f"{outer} - das sind zwei Abstaende, nicht einer")


@pytest.mark.parametrize("scale", [1.0, 1.5, sizes.SCALE_DEFAULT, 2.5])
def test_the_gaps_stay_in_step_at_every_setting(scale):
    """Und die Gleichung haelt auch nach dem Runden.

    Nicht nur beim Grundwert: value_of() rundet kaufmaennisch, und eine
    Sprosse, die bei einem Faktor auf- und bei einem anderen abrundet,
    bricht die Gleichung genau dort, wo sie niemand nachrechnet.
    """
    section = {"scale": scale}
    inner = int(sizes.value_of("STYLE_GAPS_IN", section))
    outer = int(sizes.value_of("STYLE_GAPS_OUT", section))
    assert 2 * inner == outer, (
        f"bei sizes.scale {scale} sind es {2 * inner} px zwischen zwei "
        f"Fenstern und {outer} zum Rand")


def test_the_bar_and_the_windows_read_the_same_placeholder():
    """EINE Zahl mit zwei Lesern, und nicht zwei Zahlen, die gleich sind.

    Das ist der ganze Unterschied zwischen "derselbe Abstand" und
    "zufaellig derselbe Abstand". Drei Dateien muessen ihn nennen:

      hyprland-universal-config   gaps_out fuer die Fenster
      bar-style                   der Rand, den die Platte haelt
      ags-bar                     dasselbe noch einmal als Zahl, weil es
                                  vom Platzbudget der Module abgeht
    """
    assert "gaps_out = {{STYLE_GAPS_OUT}}" in HYPRLAND.read_text(
        encoding="utf-8"), (
        "die Fenster bekommen ihren Aussenabstand nicht mehr aus der "
        "Tabelle")
    assert "{{STYLE_GAPS_OUT}}" in _code(BAR_STYLE, "/*"), (
        "die Platte haelt einen anderen Abstand als die Fenster")
    assert "const EDGE_GAP = {{STYLE_GAPS_OUT}}" in _code(BAR, "//"), (
        "die Leiste rechnet mit einem anderen Abstand, als sie zeichnet")


def test_the_panel_keeps_no_margin_on_the_side_the_windows_are_on():
    """Sonst ist genau die eine Fuge doppelt so breit wie alle anderen.

    Das Fenstergebiet beginnt am Ende des reservierten Streifens, und
    dann kommt gaps_out noch dazu. Haelt die Platte UNTEN auch ihren
    Rand, stehen dort 2*G - und zwar in der Fuge, die der Nutzer den
    ganzen Tag ansieht.

    Auf der Seitenleiste war es dieselbe Rechnung und die Kante rechts.
    Gedreht hat sich, an welcher Seite das Fenstergebiet anschliesst,
    und sonst nichts.
    """
    body = _rule(_code(BAR_STYLE, "/*"), "#bar")
    for side in ("left", "right", "top"):
        assert f"margin-{side}: {{{{STYLE_GAPS_OUT}}}}px;" in body, (
            f"die Platte haelt nach {side} keinen Abstand zum Schirmrand")
    assert "margin-bottom" not in body, (
        "die Platte haelt unten einen Rand - dort steht dann der doppelte "
        "Abstand, weil das Fenster darunter seinen eigenen gaps_out hat")


def test_the_bar_does_not_count_its_shelf_against_the_screen_width():
    """Die Kante kostet Hoehe und keine Breite.

    Solange die Leiste senkrecht lief, lag ihre Kante quer zur
    Laufrichtung nicht - sie lag am ENDE, und deshalb zaehlte sie in
    PANEL_OVERHEAD mit. GEMESSEN am 11.08.2026: ohne sie meldete die
    Leiste auf einem 900 px hohen Schirm 902 px Mindesthoehe.

    Waagerecht ist `border-bottom` eine Hoehe. Bliebe sie in der
    Breitenrechnung stehen, klappte die Leiste ein Modul zu frueh ein -
    ein Fehler, den niemand sieht, weil das Ergebnis ordentlich
    aussieht.
    """
    code = _code(BAR, "//")
    assert "const PANEL_OVERHEAD = 2 * EDGE_GAP" in code, (
        "das Platzbudget der Leiste rechnet nicht mit zwei Raendern")
    assert "2 * EDGE_GAP + SHELF" not in code, (
        "die Kante zaehlt gegen die BREITE des Schirms, und sie ist eine "
        "Hoehe")


# --------------------------------------------------------------------
# Die abgesetzte Kante
# --------------------------------------------------------------------

def test_the_bar_has_no_shelf_and_no_second_layer():
    """Die Leiste ist EINE Flaeche, und der Nutzer hat genau das
    verlangt.

    WAS HIER BIS ZUM 12.08.2026 STAND, UND WARUM ES UMGEDREHT IST
        Diese Pruefung hiess `test_the_shelf_sits_under_the_panel_and_
        under_every_chip` und verlangte das Gegenteil: eine 6 px hohe
        Kante unter der Platte UND noch einmal unter jedem Modul, dazu
        eine Kachel unter jedem Modul. Beides war am Vorbild abgelesen
        (seine Leiste #d3c6aa mit #7d6a40 darunter, seine Kacheln
        #343a3f mit #161a1d), und beides hat der Nutzer angesehen und
        abgelehnt - am 12.08.2026, woertlich:

            "entferne bitte diese 3d aussehen von hier sodass sie
             matched mit dem footer und die icon sollen im header nicht
             nochmal ein element haben weil ich die icons seperat von
             dem hintergrund der waybar erkennen kann"

        Das ist keine abgeschwaechte Zusicherung, sondern eine
        umgedrehte: vorher wurde das Vorhandensein zweier Ebenen
        gehalten, jetzt ihre Abwesenheit. Ohne diese Fassung kaeme das
        Brett beim naechsten Blick in die Vorlage des Vorbilds zurueck,
        und niemand wuesste mehr, dass es einmal weggenommen wurde.

    WAS AM FENSTER BLEIBT
        Hyprlands Schatten mit range 0 und `offset = 0 STYLE_BAR_SHELF`.
        Dort ist die Kante die eines FENSTERS und keine zweite Ebene in
        einer Leiste; die naechste Pruefung haelt sie weiterhin.
    """
    css = _code(BAR_STYLE, "/*")
    for selector in ("#bar", ".bar-module", "#dock"):
        body = _rule(css, selector)
        assert "{{STYLE_BAR_SHELF}}" not in body, (
            f"{selector} traegt wieder die abgesetzte Kante - der Nutzer "
            "hat sie am 12.08.2026 abgelehnt")

    # Und die zweite Haelfte: kein Modul malt einen eigenen Grund.
    # Gesucht wird `background` auf der ersten Ebene der Regel, also
    # genau das, was ein Modul zu einem eigenen Element machen wuerde.
    for selector in (".bar-module", "#tray", "#dock button.dock-button"):
        body = _rule(css, selector)
        painted = [line.strip() for line in body.splitlines()
                   if re.match(r"\s*background\s*:", line)
                   and "transparent" not in line]
        assert painted == [], (
            f"{selector} malt wieder einen eigenen Grund: {painted}. Der "
            "Nutzer erkennt die Symbole gegen die Leiste, ohne dass jedes "
            "davon noch ein Element bekommt")

    # Die Platte traegt dafuer die volle einschichtige Deckkraft - sonst
    # waere mit der Kachel auch das Material unter dem Text weg.
    for selector in ("#bar", "#dock"):
        assert "background: {{STYLE_GLASS_SOLO}};" in _rule(css, selector), (
            f"{selector} ist einschichtig und malt trotzdem nicht die "
            "einschichtige Platte. 'sodass sie matched mit dem footer' "
            "heisst dieselbe Zeile und nicht eine aehnliche")


def test_the_windows_get_the_same_shelf_from_hyprlands_own_shadow():
    """Und zwar ohne Plugin und ohne Patch.

    Die README des Vorbilds verlangt dafuer Aenderungen an Hyprlands
    CHyprDropShadowDecoration.cpp. GEMESSEN am 11.08.2026 in seiner
    eigenen Themendatei braucht es die nicht mehr: ein Schatten mit
    range 0 ist keine Weichzeichnung, sondern eine zweite, versetzte
    Kopie der Fensterform - und um die Kantenhoehe nach unten versetzt
    IST das die Kante.

    range = 0 ist dabei der ganze Trick. Mit einem range > 0 wird daraus
    ein weicher Schlagschatten, also genau das, was nicht gemeint ist.
    """
    conf = HYPRLAND.read_text(encoding="utf-8")
    shadow = re.search(r"shadow \{(.*?)\n    \}", conf, re.DOTALL)
    assert shadow, "der Schattenblock ist fort"
    body = shadow.group(1)
    assert re.search(r"^\s*range = 0\s*$", body, re.MULTILINE), (
        "der Schatten hat einen Radius - dann ist er ein Schlagschatten "
        "und keine Kante")
    assert "offset = 0 {{STYLE_BAR_SHELF}}" in body, (
        "der Schatten ist nicht um die Kantenhoehe nach unten versetzt")
    assert "color = rgb({{STYLE_BAR_SHELF_COLOR_RAW}})" in body, (
        "die Kante am Fenster hat eine andere Farbe als die an der Leiste")


def test_the_shelf_follows_the_size_factor():
    """Sonst sitzt bei doppelter Schrift dieselbe 4-px-Kante unter einem
    doppelt so hohen Fenster, und der Koerper verliert seine Tiefe.

    Seit dem 12.08.2026 traegt sie nur noch das FENSTER (Hyprlands
    Schatten, siehe oben) - an der Leiste hat der Nutzer sie abgelehnt.
    Ein Fenster waechst mit dem Groessenregler genauso wie eine Kachel,
    also gilt die Begruendung unveraendert: dieser Rahmen ist kein
    Haarstrich, der eine Flaeche begrenzt, sondern die sichtbare DICKE
    eines Koerpers.
    """
    assert sizes.TABLE["STYLE_BAR_SHELF"].scales
    assert sizes.TABLE["STYLE_BAR_SHELF"].base in sizes.SPACE_LADDER, (
        "die Kante steht neben der Abstandsleiter")
    # Ohne Einheit, weil Hyprland sie ebenfalls liest.
    assert sizes.TABLE["STYLE_BAR_SHELF"].unit == sizes.BARE


def test_a_window_is_as_round_as_the_bar():
    """Ein Fenster und die Leiste sollen erkennbar aus demselben
    Baukasten kommen.

    Hier stand `rounding = 0`, also quadratische Fenster neben einer
    Leiste, die keine einzige rechte Ecke mehr hat. Danach stand hier
    die Sprosse der KACHEL, und das war ein Pixelwert naeher, aber
    dieselbe Sorte Fehler: die Kachel ist das, was AUF einer Platte
    liegt, und ein Fenster ist eine Platte.

    GEMELDET am 17.08.2026: "auch die fenster die erscheinen wie
    terminal mit dem hyprland header sind nicht so rund wie unsere
    waybar das muss alles angepasst werden". GEMESSEN am selben Tag:
    Leiste 20 px, Fenster 12.

    VERGLICHEN WIRD MIT DER PLATTE DER LEISTE, also mit genau der
    Flaeche, die der Nutzer daneben sieht - und die Gleichheit wird
    gerechnet und nicht nachgehalten: faellt diese Zeile, sind die
    beiden wieder verschieden rund, ganz gleich welche Zahl in der
    Leiter steht.
    """
    plate = re.search(r"border-radius: \{\{STYLE_RADIUS_(\w+)\}\};",
                      _rule(_code(BAR_STYLE, "/*"), "#bar"))
    assert plate, "die Platte der Leiste hat keine Rundung von der Leiter"
    assert sizes.TABLE["STYLE_WINDOW_ROUNDING"].base == sizes.TABLE[
        f"{sizes.RADIUS_PREFIX}{plate.group(1)}"].base, (
        "Fenster und Leiste sind verschieden rund")
    assert "rounding = {{STYLE_WINDOW_ROUNDING}}" in HYPRLAND.read_text(
        encoding="utf-8")


# --------------------------------------------------------------------
# Der Abstand zwischen zwei Kacheln
# --------------------------------------------------------------------

def test_the_gap_between_two_chips_comes_from_the_general_ladder():
    """Ein Name, der eine Himmelsrichtung nennt, ist bei jeder Drehung
    wieder falsch - und ein Regler, den niemand mehr liest, ist schlimmer
    als ein falscher Name.

    Die Groesse hiess erst STYLE_MARGIN_TOP, solange die Leiste senkrecht
    lief: dort lag der Abstand zwischen zwei Kacheln oben. Waagerecht ist
    derselbe Abstand ein margin-left, und ein Platzhalter mit "TOP" im
    Namen, der als margin-left gelesen wird, ist genau der Riss zwischen
    Namen und Sache, den der Kopf von src/sizes.py verbietet - deshalb
    wurde sie am 12.08.2026 zu STYLE_CHIP_GAP.

    STYLE_CHIP_GAP SELBST IST AM 19.08.2026 GEFALLEN (Regel 14), NICHT
    NUR UMBENANNT
        .bar-module trug ihn als margin-left UND zaehlte damit denselben
        Abstand zusammen mit seiner eigenen Polsterung doppelt (GEMESSEN:
        60px statt der beabsichtigten 28, Bericht der Aufgabe vom
        19.08.2026 - "sie sind viel zu weit voneinander entfernt und
        auch nicht zentriert in ihrer box"). Die Behebung stellt
        .bar-module auf STYLE_SPACE_8 um, eine Sprosse der allgemeinen
        Abstandsleiter statt einer eigenen Groesse - STYLE_CHIP_GAP hat
        seither keinen Leser mehr und ist restlos entfernt, nicht durch
        einen dritten Namen ersetzt.
    """
    assert "STYLE_CHIP_GAP" not in sizes.TABLE, (
        "STYLE_CHIP_GAP steht wieder in der Tabelle, ohne dass eine "
        "Vorlage ihn liest - genau der Zustand, den Regel 14 verbietet")
    assert "STYLE_MARGIN_TOP" not in sizes.TABLE, (
        "der alte Name steht noch in der Tabelle - dann gibt es zwei "
        "Regler fuer einen Abstand")

    body = _rule(_code(BAR_STYLE, "/*"), ".bar-module")
    assert "margin-left: {{STYLE_SPACE_8}};" in body, (
        "die Kacheln halten ihren Abstand nicht mehr aus der Abstandsleiter")
    assert "margin-left: {{STYLE_CHIP_GAP}};" not in body, (
        "die verworfene Groesse steht noch als margin-left in der Regel, "
        "die sie nicht mehr lesen soll")


def test_a_saved_setting_for_the_retired_gap_is_dropped_not_renamed(monkeypatch):
    """Wer die Groesse eingestellt hatte, verliert die Zahl - und zwar
    sichtbar, nicht heimlich unter einem dritten Namen.

    BIS ZUM 19.08.2026 stand hier die Gegenrichtung: eine Umbenennung
    ohne Migration ist eine stille Ruecksetzung auf den Vorgabewert, weil
    der alte Schluessel in der Datei stehen bleibt, obwohl niemand ihn
    mehr liest. Das gilt weiter fuer eine ECHTE Umbenennung (RENAMED_KEYS,
    die Farben) - aber STYLE_MARGIN_TOP/STYLE_CHIP_GAP ist keine mehr:
    das ZIEL der alten Umbenennung ist selbst gefallen (Regel 14, siehe
    den Kopf von src/user_settings.py bei RENAMED_SIZE_VALUES), es gibt
    also nichts mehr, auf das man umbiegen koennte. Beide Namen stehen
    seither in RETIRED_SIZE_VALUES und werden beim Laden entfernt - das
    ist keine Regression, sondern die einzig ehrliche Antwort: der
    Regler, den diese Zahl einmal bediente, existiert nicht mehr.
    """
    monkeypatch.syspath_prepend(str(SRC))
    import user_settings

    for old_name in ("STYLE_MARGIN_TOP", "STYLE_CHIP_GAP"):
        document = {"schema_version": 1,
                    "sizes": {"values": {old_name: "42px"}}}
        user_settings.migrate_renamed_keys(document)

        values = document["sizes"]["values"]
        assert old_name not in values, (
            f"{old_name} steht noch in der Datei - ein Regler ohne Leser")
        assert values == {}, (
            f"{old_name} wurde auf einen neuen Schluessel umgebogen statt "
            f"entfernt zu werden: {values}")


# --------------------------------------------------------------------
# Was auf dem Schirm steht, bevor irgendetwas von uns laeuft
# --------------------------------------------------------------------

def test_the_compositor_shows_nothing_of_its_own():
    """GEMELDET am 12.08.2026: "ausserdem war kurz das maedchen von
    hyprland sichtbar das moechte ich nicht es darf immer nur mein
    hintergrund da sein".

    Es war kein Zufall und kein Pech. Hyprland zeichnet ohne diese zwei
    Zeilen seine eigene Tapete und sein Logo, sobald es hochkommt, und
    unsere kommt aus einem exec-once - es gab damit bei JEDER Anmeldung
    ein Zeitfenster, in dem etwas Fremdes auf dem Schirm stand.

    Beide Halften werden gemessen, weil eine allein den Fehler nur
    halbiert: die Abschaltung, und dass die Tapete nicht kuenstlich
    verzoegert wird. Das `sleep 2` davor wartete auf eine Bedingung, auf
    die restore_wallpaper() selbst schon wartet.
    """
    code = _code(HYPRLAND, "#")

    assert "force_default_wallpaper = 0" in code, (
        "Hyprland darf wieder seine eigene Tapete zeigen")
    assert "disable_hyprland_logo = true" in code, (
        "Hyprland darf wieder sein Logo zeigen")

    restore = [line for line in code.splitlines()
               if "wallpaper-manager restore" in line]
    assert restore, "nichts stellt die Tapete des Nutzers wieder her"
    assert not any("sleep" in line for line in restore), (
        "die Tapete des Nutzers wartet wieder - und solange der Schirm "
        f"wartet, gehoert er nicht ihm: {restore}")
