# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Bildschirmanordnung, ohne Anzeige und ohne Compositor gemessen.

Hier steht alles, was src/displays.py entscheidet: was aus der Antwort
des Compositors gelesen wird, was in monitors.conf geschrieben wird, was
angewandt wird, was eingerastet wird und was verweigert wird. Der
Waechter selbst - der Prozess, der den Rueckweg geht - hat eigene Tests
in tests/src/test_displays_guard.py, weil er nur als echter Prozess etwas
beweist.

WAS DIESE DATEI NICHT ANFASST
    `hyprctl`. Es steht in conftest.NEVER_PASSTHROUGH, und zwar zurecht:
    es aendert die Sitzung, in der diese Suite laeuft. Jeder Lauf hier
    bekommt einen `runner`, der eine hinterlegte Antwort zurueckgibt.
"""
from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"


def _flat(name: str):
    """Ein Modul aus src/, das selbst flach importiert.

    Dieselbe Vorrichtung und dieselbe Begruendung wie in
    tests/src/test_theme.py: src/ ist kein Paket, und src/displays.py
    sagt `import monitors` - so, wie es unter /usr/share/zepos auch
    liegen wird.
    """
    sys.path.insert(0, str(SRC))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(SRC))


displays = _flat("displays")

# DIE FORM IST ECHT, DIE NAMEN SIND ES NICHT (17.08.2026)
#
# Die Anordnung - ein 3440x1440-Schirm bei 59.97 Hz links, ein
# 1920x1200-Panel bei 60.001 Hz rechts daneben bei x=3440 - ist an einem
# wirklichen Schreibtisch abgelesen, und daran haengt jede Messung in
# dieser Datei: die krumme Bildwiederholrate, die einrastende Kante bei
# 3440 und die zwei verschiedenen Beschreibungen, an denen
# monitors.selector() `desc:` gegen den Anschlussnamen abwaegt.
#
# Die BESCHREIBUNGEN sind erfunden. Vorher stand hier die
# EDID-Beschreibung zweier echter Geraete, und die des aeusseren trug am
# Ende eine siebenstellige Servicenummer - eine geraetegenaue Kennung,
# aus der beim Hersteller Kaufdatum, Garantie und Region abrufbar sind.
# Genommen sind die Kunstnamen, die der Baum schon fuehrt:
# "Screen Co Model X 1111" fuer einen externen Schirm (tests/src/
# test_monitors.py, test_hardware.py, test_grid_wallpaper.py) und
# "Panel Works 16" fuer ein eingebautes Panel (tests/settings/
# test_screens_headless.py, das genau diese Anordnung nachstellt). Eine
# Sprache fuer erfundene Geraete, statt zweier.
#
# Keiner der beiden Namen ist Praefix des anderen. Das ist die
# Eigenschaft, an der test_a_screen_is_named_the_way_a_hyprland_rule_
# names_it haengt: bei einem Praefix faellt monitors.selector() auf den
# Anschlussnamen zurueck, und die Pruefung maesse dann etwas anderes.
ANSWER = [
    {
        "name": "DP-1",
        "description": "Screen Co Model X 1111",
        "width": 3440, "height": 1440, "refreshRate": 59.97,
        "x": 0, "y": 0, "scale": 1.0, "transform": 0, "disabled": False,
        "availableModes": ["3440x1440@59.97Hz", "1920x1080@60.00Hz"],
    },
    {
        "name": "eDP-1",
        "description": "Panel Works 16",
        "width": 1920, "height": 1200, "refreshRate": 60.001,
        "x": 3440, "y": 0, "scale": 1.0, "transform": 0, "disabled": False,
        "availableModes": ["1920x1200@60.00Hz"],
    },
]


def answering(entries, *, returncode: int = 0, text: str | None = None):
    """Ein runner, der genau eine hinterlegte hyprctl-Antwort gibt."""
    def runner(argv, **kwargs):
        assert argv[:2] == ["hyprctl", "monitors"], argv
        assert "all" in argv, (
            "ohne `all` zaehlt Hyprland die abgeschalteten Schirme nicht "
            f"auf: {argv}")
        return subprocess.CompletedProcess(
            argv, returncode,
            text if text is not None else json.dumps(entries), "")
    return runner


def a_desk(**overrides) -> list[displays.Placement]:
    outputs = displays.read_outputs(runner=answering(ANSWER))
    return displays.current_layout(outputs, overrides.get("options"))


# --------------------------------------------------------------------
# Lesen
# --------------------------------------------------------------------

def test_the_outputs_come_back_with_their_modes():
    outputs = displays.read_outputs(runner=answering(ANSWER))

    assert [item.name for item in outputs] == ["DP-1", "eDP-1"]
    assert outputs[0].modes == (
        displays.Mode(3440, 1440, 59.97), displays.Mode(1920, 1080, 60.0))
    assert outputs[1].refresh == pytest.approx(60.001)


def test_a_monitor_without_a_connector_name_is_left_out():
    """Es gibt keine `monitor=`-Zeile, die ihn benennen koennte.

    Dieselbe Entscheidung wie in monitors.layout(), und aus demselben
    Grund: eine Zeile, die auf nichts passt, ist schlimmer als ein
    fehlender Schirm, weil sie aussieht, als taete sie etwas.
    """
    outputs = displays.read_outputs(
        runner=answering([{"name": "", "width": 800}, *ANSWER]))

    assert [item.name for item in outputs] == ["DP-1", "eDP-1"]


def test_a_missing_field_does_not_take_the_whole_answer_down():
    """`hyprctl monitors -j` hat zwischen Hyprland-Fassungen die Form
    gewechselt - src/monitors.py fuehrt dieselbe Begruendung."""
    outputs = displays.read_outputs(runner=answering([{"name": "DP-9"}]))

    assert outputs[0].scale == 1.0
    assert outputs[0].width == 0
    assert outputs[0].modes == ()


@pytest.mark.parametrize("entries, code, text, needle", [
    (None, 1, "", "endete mit 1"),
    (None, 0, "nicht wirklich json", "kein JSON"),
    (None, 0, '{"name": "DP-1"}', "keine Liste"),
])
def test_an_unusable_answer_is_one_kind_of_failure(entries, code, text, needle):
    """Ein Typ, weil ein Aufrufer genau eine Sache damit tun kann."""
    with pytest.raises(RuntimeError, match=needle):
        displays.read_outputs(
            runner=answering(entries, returncode=code, text=text))


def test_a_compositor_that_is_not_running_is_the_same_kind_of_failure():
    def runner(argv, **kwargs):
        raise FileNotFoundError("hyprctl")

    with pytest.raises(RuntimeError, match="liess sich nicht starten"):
        displays.read_outputs(runner=runner)


@pytest.mark.parametrize("text, expected", [
    ("1920x1200@60.00Hz", displays.Mode(1920, 1200, 60.0)),
    ("1920x1200@60.00hz", displays.Mode(1920, 1200, 60.0)),
    ("1920x1200", displays.Mode(1920, 1200, 0.0)),
    ("kaputt", None),
    ("", None),
])
def test_a_mode_is_read_or_left_out(text, expected):
    assert displays.parse_mode(text) == expected


# --------------------------------------------------------------------
# Schreiben
# --------------------------------------------------------------------

def test_a_screen_is_named_the_way_a_hyprland_rule_names_it():
    """Ueber monitors.selector(), also mit derselben Antwort wie die
    Arbeitsbereichs-Regeln.

    Zwei Antworten auf "wie heisst dieser Schirm in einer Regel" waeren
    zwei Regeln, die auf verschiedene Schirme passen - und der Nutzer
    traefe das als Arbeitsbereiche auf einem Schirm, auf dem nie ein
    Fenster aufgeht.
    """
    layout = a_desk()

    assert displays.spec(layout[0]).startswith(
        "desc:Screen Co Model X 1111,")


def test_two_identical_screens_fall_back_to_their_connector_names():
    twins = [dict(entry, description="Acme Vision 24") for entry in ANSWER]
    outputs = displays.read_outputs(runner=answering(twins))

    layout = displays.current_layout(outputs)

    assert [displays.spec(item).split(",")[0] for item in layout] == [
        "DP-1", "eDP-1"]


def test_the_line_carries_mode_position_and_scale_in_hyprlands_order():
    layout = a_desk()

    assert displays.spec(layout[1]) == (
        "desc:Panel Works 16,1920x1200@60.001,3440x0,1")


def test_a_screen_that_is_off_gets_the_one_word_hyprland_reads():
    off = displays.replace(a_desk()[0], enabled=False)

    assert displays.spec(off) == "desc:Screen Co Model X 1111,disable"


def test_a_rotation_rides_in_the_same_line():
    """nwg-displays schreibt dafuer eine ZWEITE monitor=-Zeile fuer
    denselben Schirm (settings_applier.py:463).

    Eine Regel je Schirm ist die Form, die `hyprctl keyword monitor` auch
    anwenden kann - zwei Zeilen waeren zwei Aufrufe, und der zweite
    ueberschriebe den ersten.
    """
    turned = displays.replace(a_desk()[1], transform=1)

    assert displays.spec(turned).endswith(",1,transform,1")


def test_transform_zero_is_not_written_out():
    assert "transform" not in displays.spec(a_desk()[0])


def test_what_the_page_does_not_offer_survives_a_rewrite():
    """Die Spiegelung, die VRR-Stellung, die Bittiefe.

    Eine Oberflaeche, die beim Anfassen einer Einstellung eine andere
    loescht, ist schlimmer als eine, die die andere nicht kennt.
    """
    options = displays.trailing_options(
        "monitor=desc:Screen Co Model X 1111,"
        "3440x1440@59.97,0x0,1,mirror,eDP-1,bitdepth,10\n")
    layout = displays.current_layout(
        displays.read_outputs(runner=answering(ANSWER)), options)

    assert displays.spec(layout[0]).endswith(",mirror,eDP-1,bitdepth,10")


def test_the_second_line_nwg_writes_for_a_rotation_keeps_its_hands_off():
    """DER FEHLER, DEN DIESE PRUEFUNG FAENGT, IST GEMESSEN.

    nwg-displays haengt die Drehung als eigene Zeile hinter die Regel.
    Ohne die Pruefung auf ein vollstaendiges Modusfeld ueberschriebe
    diese zweite Zeile die Zusatzworte der ersten mit nichts - und
    `mirror,DP-2` waere beim ersten Speichern still weg.
    """
    options = displays.trailing_options(
        "monitor=DP-1,3440x1440@59.97,0x0,1.0,mirror,DP-2\n"
        "monitor=DP-1,transform,1\n")

    assert options == {"DP-1": ("mirror", "DP-2")}


def test_a_file_written_by_nwg_displays_is_read_under_its_own_name():
    """Sie traegt `desc:...`, wenn `use-desc` an war, und sonst den
    Anschlussnamen. Nur unter einem von beiden zu suchen hiesse, die
    Spiegelung der Haelfte aller Nutzer wegzuwerfen."""
    layout = displays.current_layout(
        displays.read_outputs(runner=answering(ANSWER)),
        {"eDP-1": ("vrr", "1")})

    assert displays.spec(layout[1]).endswith(",vrr,1")


def test_the_fallback_line_of_the_universal_config_is_not_a_screen():
    # Die Auffangzeile aus hyprland-universal-config.template.
    assert displays.parse_line("monitor=,preferred,auto,1") is None
    assert displays.parse_line("# nur ein Kommentar") is None
    assert displays.parse_line("general { gaps_in = 5 }") is None


def test_the_file_reads_back_as_what_was_written():
    layout = a_desk()
    text = displays.render(layout)

    assert displays.trailing_options(text) == {
        displays.spec(item).split(",")[0]: () for item in layout}
    assert text.count("monitor=") == 2


def test_the_file_is_sorted_so_an_unchanged_desk_makes_an_unchanged_file():
    layout = a_desk()

    assert displays.render(layout) == displays.render(reversed(layout))


def test_writing_replaces_the_file_instead_of_growing_it(tmp_path):
    target = tmp_path / "hypr" / "monitors.conf"
    layout = a_desk()

    displays.write(layout, [target])
    displays.write(layout, [target])

    assert target.read_text(encoding="utf-8").count("monitor=") == 2
    assert not list(target.parent.glob("*.neu")), (
        "die Nachbardatei ist liegengeblieben - dann war das Schreiben "
        "kein os.replace(), sondern zwei Dateien")


def test_the_active_profile_gets_the_same_file(tmp_path, monkeypatch):
    """Sonst waere die Anordnung bei der naechsten Anmeldung wieder weg:
    start-hyprland kopiert das Profil ueber ~/.config/hypr."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path / "user"))
    (tmp_path / "config" / "hypr").mkdir(parents=True)
    (tmp_path / "config" / "hypr" / "current-profile").write_text("buero\n")
    (tmp_path / "user" / "profiles" / "buero").mkdir(parents=True)

    assert displays.targets() == [
        tmp_path / "config" / "hypr" / "monitors.conf",
        tmp_path / "user" / "profiles" / "buero" / "monitors.conf",
    ]


def test_a_profile_without_a_directory_is_not_invented(tmp_path, monkeypatch):
    """Ein Profil entsteht durch `save-profile`, das fuenf Dateien
    ablegt. Eins, das nur monitors.conf enthaelt, laesst start-hyprland
    beim naechsten `cp` scheitern - also mit einer Sitzung, die nicht
    hochkommt.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path / "user"))
    (tmp_path / "config" / "hypr").mkdir(parents=True)
    (tmp_path / "config" / "hypr" / "current-profile").write_text("buero\n")

    assert displays.targets() == [
        tmp_path / "config" / "hypr" / "monitors.conf"]


@pytest.mark.parametrize("written", ["unknown", "auto", "", "../anderswo",
                                     ".versteckt"])
def test_a_profile_name_that_names_no_directory_is_no_profile(
        written, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    (tmp_path / "config" / "hypr").mkdir(parents=True)
    (tmp_path / "config" / "hypr" / "current-profile").write_text(written)

    assert displays.current_profile() == ""


# --------------------------------------------------------------------
# Anordnen
# --------------------------------------------------------------------

def test_a_screen_that_is_nearly_touching_snaps_to_the_edge():
    layout = a_desk()
    moved = displays.replace(layout[1], x=3440 - 40)

    landed = displays.snap([layout[0], moved], "eDP-1")

    assert landed.x == 3440


def test_the_nearest_edge_wins_and_not_the_first_one_in_the_list():
    """DIE EINE STELLE, AN DER HIER ANDERS GERECHNET WIRD ALS IN DER
    VORLAGE.

    nwg-displays bricht beim ersten Treffer ab (main.py:280-300), obwohl
    der Kommentar darueber "find nearest" sagt. Bei drei Schirmen
    nebeneinander liegen mehrere Kandidaten im Fangbereich, und "der
    erste in der Liste" ist die Reihenfolge, in der die Kabel
    eingesteckt wurden.
    """
    # Zwei Nachbarn: einer bietet die Kante bei 1000, einer bei 1080.
    # Gezogen wird nach 1075 - also nah an beiden, naeher an 1080.
    left = displays.Placement("A", "A", True, 1000, 1000, 60, 0, 0, 1.0, 0)
    right = displays.Placement("B", "B", True, 80, 1000, 60, 1000, 0, 1.0, 0)
    moving = displays.Placement("C", "C", True, 500, 500, 60, 1075, 0, 1.0, 0)

    landed = displays.snap([left, right, moving], "C")

    assert landed.x == 1080


def test_nothing_snaps_beyond_the_reach():
    layout = a_desk()
    moved = displays.replace(layout[1], x=3440 + displays.SNAP_DISTANCE + 1)

    assert displays.snap([layout[0], moved], "eDP-1").x == moved.x


def test_a_screen_that_is_off_does_not_move():
    layout = a_desk()
    off = displays.replace(layout[1], enabled=False, x=99)

    assert displays.snap([layout[0], off], "eDP-1").x == 99


def test_the_snap_does_not_stack_a_screen_on_its_neighbour():
    """DIE URSACHE VON "alles doppelt auf einem monitor" (01.09.2026).

    GEMESSEN vor der Behebung: zwei gleich grosse Schirme, der eine bei
    0,0, der andere nach 40,40 gezogen. _snap_axis fand auf BEIDEN
    Achsen den Kandidaten "vorne buendig" (0, Abstand 40 - innerhalb von
    SNAP_DISTANCE), und das Ergebnis war 0,0: der gezogene Schirm lag
    exakt auf dem anderen. Zwei Schirme auf demselben Fleck heissen zwei
    Leisten und zwei Docks an derselben Stelle - genau das Bild, das der
    Nutzer gemeldet hat.

    Die zwei buendigen Kandidaten sind AUSRICHTUNGEN und keine
    Anlegungen; getrennt je Achse gerechnet koennen sie beide zugleich
    gewinnen. Das Einrasten hat die Ueberlappung also nicht durchgelassen
    - es hat sie erzeugt.
    """
    steht = displays.Placement("A", "A", True, 1920, 1080, 60, 0, 0, 1.0, 0)
    gezogen = displays.Placement("B", "B", True, 1920, 1080, 60, 40, 40, 1.0, 0)

    assert displays._snap_axis(40, 1920, [(0, 1920)], 100) == 0
    assert displays._snap_axis(40, 1080, [(0, 1080)], 100) == 0

    landed = displays.snap([steht, gezogen], "B")

    assert displays.overlaps([steht, landed]) == [], (
        f"B ist auf {landed.x},{landed.y} eingerastet und liegt damit auf A")
    # Und zwar an die naechstgelegene Kante. GEMESSEN am 01.09.2026:
    # nach unten sind es 1040 Punkte, nach oben 1120, nach rechts 1880 -
    # also unten. Die Zahl steht hier, weil "irgendwohin, Hauptsache
    # nicht darauf" keine Zeichnung ergibt, der man beim Ziehen zusieht.
    assert (landed.x, landed.y) == (0, 1080)


def test_a_screen_dragged_above_its_neighbour_lands_above_it():
    """Die Richtung kommt aus der Bewegung und nicht aus einer Vorliebe.

    Gezogen wird von OBEN in den Schirm hinein, 180 Punkte zu tief - zu
    weit fuer den Fangbereich (SNAP_DISTANCE, 100), also greift hier
    nichts als das Ausweichen selbst. Es legt den Schirm an die Kante an,
    an der er steht: darueber.
    """
    steht = displays.Placement("A", "A", True, 1920, 1080, 60, 0, 0, 1.0, 0)
    gezogen = displays.Placement("B", "B", True, 1920, 1080, 60, 30, -900,
                                 1.0, 0)

    landed = displays.snap([steht, gezogen], "B")

    assert (landed.x, landed.y) == (0, -1080)
    assert displays.overlaps([steht, landed]) == []


def test_a_screen_dropped_dead_centre_still_lands_beside_the_other():
    """Ohne jeden Fangpunkt in Reichweite - also nichts, was das
    Einrasten retten koennte. Ein Rechteck, das sich mitten auf einem
    anderen ablegen laesst, ist der Fehler; der Fangbereich ist nur der
    haeufigste Weg dorthin."""
    steht = displays.Placement("A", "A", True, 3440, 1440, 60, 0, 0, 1.0, 0)
    gezogen = displays.Placement("B", "B", True, 800, 600, 60, 1300, 400, 1.0, 0)

    landed = displays.snap([steht, gezogen], "B")

    assert displays.overlaps([steht, landed]) == [], (
        f"B liegt auf {landed.x},{landed.y} mitten auf A")


def test_a_screen_that_lands_free_is_not_pushed_anywhere():
    """Die Gegenprobe. Ein Ausweichen, das auch dann zieht, wenn nichts
    im Weg liegt, waere eine Zeichnung, die den Schirm nicht dort
    ablegt, wo der Zeiger ihn hinbringt."""
    layout = a_desk()
    frei = displays.replace(layout[1], x=3440 + displays.SNAP_DISTANCE + 1)

    landed = displays.snap([layout[0], frei], "eDP-1")

    assert (landed.x, landed.y) == (frei.x, frei.y)


def test_a_screen_that_is_off_is_no_obstacle():
    """Ein abgeschalteter Schirm nimmt keine Flaeche ein - dieselbe
    Regel, nach der normalised() ihn beim Ursprung uebergeht und
    overlaps() ihn nicht zaehlt. Er zieht deshalb nicht an, und man weicht
    ihm auch nicht aus: der Schirm bleibt genau da, wo er abgelegt wird."""
    aus = displays.Placement("A", "A", False, 1920, 1080, 60, 0, 0, 1.0, 0)
    gezogen = displays.Placement("B", "B", True, 1920, 1080, 60, 40, 40, 1.0, 0)

    landed = displays.snap([aus, gezogen], "B")

    assert (landed.x, landed.y) == (40, 40)


def test_a_rotated_screen_occupies_its_short_side():
    """`hyprctl` meldet den MODUS. Ein Nachbar, der gegen die
    Modus-Breite gesetzt wird, ueberlappt bei jeder Drehung."""
    turned = displays.replace(a_desk()[0], transform=1)

    assert (turned.displayed_width, turned.displayed_height) == (1440, 3440)


def test_a_scaled_screen_occupies_less_room():
    """Hyprland dreht den Modus und teilt danach durch den Massstab.
    Gegen die ungeteilte Breite gerechnet ueberlappt jeder Nachbar."""
    smaller = displays.replace(a_desk()[1], scale=2.0)

    assert (smaller.displayed_width, smaller.displayed_height) == (960, 600)


def test_the_desk_always_starts_at_the_origin():
    """Sonst wanderten die Zahlen bei jedem Verschieben weiter ins Minus,
    und zwei Sitzungen mit derselben Anordnung haetten verschiedene
    Dateien."""
    layout = [displays.replace(item, x=item.x - 5000, y=item.y - 40)
              for item in a_desk()]

    assert [(item.x, item.y) for item in displays.normalised(layout)] == [
        (0, 0), (3440, 0)]


def test_a_screen_that_is_off_does_not_decide_where_the_origin_is():
    """Es nimmt keine Flaeche ein. Liesse man es den Ursprung bestimmen,
    zoege ein abgeschalteter Schirm links aussen den ganzen sichtbaren
    Schreibtisch nach rechts."""
    layout = a_desk()
    layout[0] = displays.replace(layout[0], enabled=False, x=-4000)

    # eDP-1 ist der einzige, der noch leuchtet, also faengt der
    # Schreibtisch bei IHM an. Der abgeschaltete behaelt seinen Abstand
    # und wandert mit - er verschiebt nichts, er wird verschoben.
    landed = {item.name: item.x for item in displays.normalised(layout)}
    assert landed["eDP-1"] == 0
    assert landed["DP-1"] == -4000 - 3440


def test_two_screens_on_the_same_spot_are_reported():
    layout = a_desk()
    layout[1] = displays.replace(layout[1], x=0)

    assert displays.overlaps(layout) == [("DP-1", "eDP-1")]
    assert "uebereinander" in displays.problems(layout)[0]


def test_screens_that_merely_touch_do_not_overlap():
    assert displays.overlaps(a_desk()) == []
    assert displays.problems(a_desk()) == []


def test_an_overlap_is_a_remark_and_not_a_blocker():
    """DIE ENTSCHEIDUNG VOM 01.09.2026, als Zusicherung.

    Eine Ueberlappung wird GEMELDET und nicht verweigert - die
    Begruendung steht bei overlaps() und bei blockers(). Ohne diese
    Trennung behandelten die zwei Oberflaechen dieselbe Anordnung
    verschieden: das AGS-Fenster lehnte ab, das GTK-Fenster warnte.
    """
    layout = a_desk()
    layout[1] = displays.replace(layout[1], x=0)

    assert displays.blockers(layout) == []
    assert len(displays.remarks(layout)) == 1
    assert "uebereinander" in displays.remarks(layout)[0]
    assert displays.problems(layout) == displays.remarks(layout)


def test_a_desk_without_a_screen_left_on_is_a_blocker():
    """Der eine Fall, aus dem es keinen Rueckweg gibt, bleibt einer."""
    layout = [displays.replace(item, enabled=False) for item in a_desk()]

    assert len(displays.blockers(layout)) == 1
    assert "Kein Bildschirm" in displays.blockers(layout)[0]
    assert displays.remarks(layout) == [], (
        "ein Schreibtisch ohne eingeschalteten Schirm hat keine "
        "Ueberlappung - abgeschaltete Schirme nehmen keine Flaeche ein")


# --------------------------------------------------------------------
# Anwenden
# --------------------------------------------------------------------

def test_a_desk_with_no_screen_left_on_is_refused():
    """DIE ZUSICHERUNG, DIE DIESE GANZE DATEI TRAEGT.

    Es gibt keinen Rueckfall aus einem Schreibtisch ohne Bild - die
    Frage, ob man ihn behalten will, stuende auf keinem Schirm mehr.
    """
    layout = [displays.replace(item, enabled=False) for item in a_desk()]

    assert "Kein Bildschirm bleibt an" in displays.problems(layout)[0]
    with pytest.raises(displays.NoScreenLeft):
        displays.apply_command(layout)


def test_one_screen_left_on_is_enough():
    layout = a_desk()
    layout[0] = displays.replace(layout[0], enabled=False)

    assert displays.problems(layout) == []
    assert "disable" in displays.apply_command(layout)[2]


def test_the_whole_desk_goes_over_in_one_call():
    """Jeder einzelne Aufruf waere ein Moduswechsel, also ein
    Schwarzbild. Und ein Rueckfall aus drei Aufrufen kann nach dem
    ersten unterbrochen werden - dann steht eine Anordnung, die es nie
    gab.
    """
    command = displays.apply_command(a_desk())

    assert command[:2] == ["hyprctl", "--batch"]
    assert command[2].count("keyword monitor") == 2
    assert " ; " in command[2]


def test_the_applied_line_is_the_written_line():
    """Sonst zeigte der Schirm etwas anderes als die Datei sagt, und der
    Unterschied faellt erst bei der naechsten Anmeldung auf."""
    layout = a_desk()
    command = displays.apply_command(layout)

    for item in layout:
        assert f"keyword monitor {displays.spec(item)}" in command[2]


def test_the_plan_the_guard_gets_is_a_finished_command():
    """Er soll im Ernstfall nichts mehr ausrechnen: er laeuft dann
    moeglicherweise allein, weil das Programm, das ihn gestartet hat,
    gerade gestorben ist."""
    plan = displays.guard_plan(a_desk(), 20)

    assert plan["seconds"] == 20
    assert plan["command"] == displays.apply_command(a_desk())
    assert json.loads(json.dumps(plan)) == plan


def test_a_restore_plan_that_switches_everything_off_is_refused():
    """Ein Rueckfall in genau den Zustand, vor dem er schuetzen soll."""
    dark = [displays.replace(item, enabled=False) for item in a_desk()]

    with pytest.raises(displays.NoScreenLeft):
        displays.guard_plan(dark, 20)


# --------------------------------------------------------------------
# Der Schreibtisch als Entwurf
# --------------------------------------------------------------------

def test_the_desk_knows_when_nothing_has_been_touched(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    desk = displays.Desk.load(runner=answering(ANSWER))

    assert not desk.changed()

    desk.change("eDP-1", scale=2.0)
    assert desk.changed()
    assert desk.get("eDP-1").scale == 2.0


def test_moving_a_screen_snaps_it_and_keeps_the_desk_at_the_origin(
        monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    desk = displays.Desk.load(runner=answering(ANSWER))

    desk.move("eDP-1", 3400, 30)

    assert (desk.get("eDP-1").x, desk.get("eDP-1").y) == (3440, 0)
    assert (desk.get("DP-1").x, desk.get("DP-1").y) == (0, 0)


def test_a_screen_pulled_far_to_the_left_pulls_the_origin_with_it(
        monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    desk = displays.Desk.load(runner=answering(ANSWER))

    desk.move("eDP-1", -1920, 0)

    assert [(item.name, item.x) for item in desk.placements] == [
        ("DP-1", 1920), ("eDP-1", 0)]
