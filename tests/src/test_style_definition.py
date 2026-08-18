# SPDX-License-Identifier: GPL-3.0-or-later
"""The style SSOT and monitors.py have to give the SAME answer.

src/monitors.py exists so that "what is attached" is answered once - its
own closing comment says the point of the module is that there is one
answer, not three. style_definition.py used to ask `hyprctl monitors -j`
a second time, on its own, and got a different answer in three ways:

  * it keyed the screens by the compositor's `id`, which follows the
    order the cables went in, while monitors.py keys them by position on
    the desk. AGS widget sizes were therefore keyed to plug order while
    the Hyprland workspace rules for the same screens were keyed to
    physical position: the widget sized for the 4K screen landed on the
    1080p one as soon as the cables went in differently.
  * it took the MODE as the size, so a rotated 4K panel measured
    3840x2160 - and got the 1.50 width scale meant for a screen three
    and a half times as wide as it actually is.
  * it accepted exactly five ids, 0 to 4, and invented a 1920x1080
    screen for each id nothing reported. A screen at id 5 was dropped.

The desk below reproduces all three at once, and the tests assert that
both modules describe it identically.

The compositor is reached through subprocess.run, so that is where the
fake runner goes - the same injection tests/src/test_monitors.py does at
detect()'s `runner` parameter, one level further out. Nothing here
spawns a process: every stand-in answers with a canned CompletedProcess
or raises, so the isolation guard's job is done rather than avoided.
"""
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from src.monitors import detect

SRC = Path(__file__).resolve().parents[2] / "src"

# Deliberately invented vendor and product names, as in test_monitors.py.
PORTRAIT = "Screen Co Model P 4444"
WIDE = "Screen Co Model L 1111"
ULTRA = "Screen Co Model U 9999"

# Three screens whose PLUG ORDER is not their order on the desk:
#
#   x=0     the portrait 4K, plugged second, so the compositor calls it 1
#   x=2160  the 1080p, plugged first, so the compositor calls it 0
#   x=4080  the ultrawide, at id 5 - a number the old five-slot dict had
#           no room for
#
# hyprctl lists them by id, which is why the array below is not in
# left-to-right order. Everything downstream has to put them in order for
# itself, and that is the whole disagreement.
DESK = json.dumps([
    {"id": 0, "name": "DP-1", "description": WIDE, "x": 2160, "y": 0,
     "width": 1920, "height": 1080, "refreshRate": 60.0, "scale": 1.0,
     "transform": 0},
    {"id": 1, "name": "DP-3", "description": PORTRAIT, "x": 0, "y": 0,
     "width": 3840, "height": 2160, "refreshRate": 60.0, "scale": 1.0,
     "transform": 1},
    {"id": 5, "name": "DP-7", "description": ULTRA, "x": 4080, "y": 0,
     "width": 3440, "height": 1440, "refreshRate": 60.0, "scale": 1.0,
     "transform": 0},
])

# What the desk above looks like from the front, left to right. The
# portrait screen is 2160 wide because it STANDS on its side; the mode
# hyprctl reports is 3840x2160.
DESK_SIZES = {0: (2160, 3840), 1: (1920, 1080), 2: (3440, 1440)}


def _answers(stdout, returncode=0, stderr=""):
    """A stand-in for subprocess.run that starts nothing."""
    def run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout,
                                           stderr=stderr)
    return run


def _import_style(tmp_path, monkeypatch):
    """style_definition, imported the way the generator imports it.

    src/ has no __init__.py and the module uses flat imports (`from paths
    import ...`), because the generator runs it as a sibling of
    template_processor.py from the system root.

    Both roots are pointed at an empty temporary directory, so
    USER_SETTINGS is empty and every scale below is this file's own
    default rather than whatever the person running the tests configured.

    A fresh module object per test, deliberately: the compositor is asked
    once per process and the answer is remembered, so a shared module
    would carry one test's desk into the next.
    """
    module = _import_style_with(tmp_path, monkeypatch, None)
    assert module.USER_SETTINGS == {}, "the temporary root was not empty"
    return module


def _import_style_with(tmp_path, monkeypatch, document):
    """The same import, over a settings file this test wrote.

    `document` None means no file at all - a fresh installation. Anything
    else is written as the user's settings, carrying the schema_version
    settings.load() requires, because a document without one is refused
    and would arrive here as "no settings" rather than as the settings
    the test is about.
    """
    monkeypatch.delenv("ZEPOS_SYSTEM_ROOT", raising=False)
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.syspath_prepend(str(SRC))

    if document is not None:
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "user-settings.json").write_text(
            json.dumps({"schema_version": 1, **document}), encoding="utf-8")

    spec = importlib.util.spec_from_file_location(
        "zepos_style_definition_probe", SRC / "style_definition.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def style(tmp_path, monkeypatch):
    """The style SSOT, with the three-screen desk plugged in."""
    monkeypatch.setattr(subprocess, "run", _answers(DESK))
    return _import_style(tmp_path, monkeypatch)


# --------------------------------------------------------------------
# one answer, not two
# --------------------------------------------------------------------

def test_the_style_ssot_and_monitors_describe_the_same_desk(style):
    """The assertion the whole change exists for.

    Both sides are asked about the same three screens, and both have to
    number them the same way and measure them the same way. Where they
    disagree, an AGS widget and the Hyprland workspace rule for the same
    screen mean two different monitors.
    """
    attached = detect(runner=_answers(DESK))
    expected = {index: monitor.displayed_size
                for index, monitor in enumerate(attached)}

    assert expected == DESK_SIZES, "the fixture desk is not what it claims"
    assert dict(style.MONITOR_RESOLUTIONS) == expected


def test_monitor_zero_is_the_leftmost_screen_not_the_first_cable(style):
    """The 1080p went in first and the compositor calls it id 0.

    Nothing on the desk is arranged by plug order, so neither is this.
    """
    assert style.MONITOR_RESOLUTIONS[0] == (2160, 3840)


def test_a_rotated_screen_is_scaled_by_the_width_it_actually_has(style):
    """A panel standing on its side is 2160 wide, not 3840.

    The 1.50 factor belongs to a 4K screen lying down. Applied to a
    portrait one it stretches every widget on it by half again.
    """
    assert style.MONITOR_WIDTH_SCALES[0] == pytest.approx(1.075)
    assert 1.50 not in style.MONITOR_WIDTH_SCALES.values(), (
        "a screen is being scaled as though it were 3840 wide; none is")


def test_a_sixth_screen_is_kept_and_absent_ones_are_not_invented(style):
    """id 5 was outside the old dict's five slots and simply vanished,
    while ids 2, 3 and 4 - which nothing reported - were filled in with a
    1920x1080 screen that is not there."""
    assert sorted(style.MONITOR_RESOLUTIONS) == [0, 1, 2]
    assert style.MONITOR_RESOLUTIONS[2] == (3440, 1440)


# --------------------------------------------------------------------
# what importing this module costs
# --------------------------------------------------------------------

def test_importing_the_style_ssot_asks_the_compositor_nothing(tmp_path,
                                                              monkeypatch):
    """A `--all` run starts one python process per template.

    Every one of them imports this module, so a query made while the
    module is being imported is a `hyprctl` process per template - for a
    value most templates never name. It also made the module impossible
    to import without a side effect, which is what a test and the doctor
    need it to be.

    The recorder counts what a real run would spawn. It starts nothing
    itself.
    """
    calls = []

    def recorder(cmd, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout=DESK, stderr="")

    monkeypatch.setattr(subprocess, "run", recorder)
    style = _import_style(tmp_path, monkeypatch)

    assert calls == [], "importing the style SSOT queried the compositor"

    assert style.MONITOR_RESOLUTIONS[0] == (2160, 3840)
    assert calls == [["hyprctl", "monitors", "-j"]]

    # Asked once per process, however many values are read out of it.
    dict(style.STYLE_VARIABLES)
    assert style.MONITOR_WIDTH_SCALES[2] == pytest.approx(1.35)
    assert len(calls) == 1, "the compositor was asked more than once"


# --------------------------------------------------------------------
# no compositor at all
# --------------------------------------------------------------------

def test_every_style_still_resolves_with_no_compositor(tmp_path, monkeypatch):
    """Installation, a TTY, and this test suite have no Hyprland running.

    Generating has to work there - it is how the configuration gets
    written in the first place - so a failed query is not an error. What
    it must not do is claim a screen that is not there: the resolutions
    are EMPTY, and the single documented fallback is applied by the
    values that need one.
    """
    def missing(cmd, **kwargs):
        raise FileNotFoundError("hyprctl")

    monkeypatch.setattr(subprocess, "run", missing)
    style = _import_style(tmp_path, monkeypatch)

    assert dict(style.MONITOR_RESOLUTIONS) == {}
    assert dict(style.MONITOR_WIDTH_SCALES) == {}
    assert style.FALLBACK_RESOLUTION == (1920, 1080)

    variables = dict(style.STYLE_VARIABLES)
    assert variables["STYLE_SCALE_FACTOR_MON0"] == "1.00"
    assert "no monitor" in variables["STYLE_SCALE_INFO"].lower(), (
        "the debug line names screens that are not attached")
    assert all(isinstance(value, str) for value in variables.values()), (
        "a placeholder that is not a string cannot be substituted")


def test_a_compositor_that_answers_nonsense_is_not_a_desk(tmp_path,
                                                          monkeypatch):
    """hyprctl present, Hyprland not running: it exits non-zero and says
    so on stderr. Reading that as an empty desk is right; reading it as
    a screen is not."""
    monkeypatch.setattr(
        subprocess, "run",
        _answers("", returncode=1, stderr="Couldn't connect to Hyprland"))
    style = _import_style(tmp_path, monkeypatch)

    assert dict(style.MONITOR_RESOLUTIONS) == {}


# --------------------------------------------------------------------
# the shape the placeholders depend on
# --------------------------------------------------------------------

def test_the_five_monitor_placeholders_survive_any_number_of_screens(style):
    """{{STYLE_*_MON0}} to {{STYLE_*_MON4}} are a contract with the
    templates: the set of placeholder NAMES cannot depend on what is
    plugged in, or a template would resolve on one desk and fail on
    another. Only their values follow the screens - and a slot no screen
    fills falls back rather than disappearing."""
    variables = dict(style.STYLE_VARIABLES)
    for index in range(5):
        assert f"STYLE_SCALE_FACTOR_MON{index}" in variables

    # Three screens are attached, so MON3 and MON4 name nothing and get
    # the fallback rather than a value from a neighbouring screen.
    assert variables["STYLE_SCALE_FACTOR_MON3"] == "1.00"
    assert variables["STYLE_SCALE_FACTOR_MON2"] == "1.35"


# --------------------------------------------------------------------
# a setting that changes nothing
# --------------------------------------------------------------------
#
# Every test below sets ONE thing in the settings file and looks at what
# came out. That is the only way to tell a setting apart from a setting
# that happens to be stored: both look identical in the file, in the
# style editor and in `zepos-settings get`.


def _no_compositor(monkeypatch):
    """Nothing attached, so the values below depend on the settings alone."""
    def missing(cmd, **kwargs):
        raise FileNotFoundError("hyprctl")

    monkeypatch.setattr(subprocess, "run", missing)


def test_the_bar_text_colour_comes_from_the_key_that_offers_it(
        tmp_path, monkeypatch):
    """Die Farbe der Leiste kommt aus dem Schluessel, den die
    Oberflaeche anbietet.

    Der Fall, aus dem diese Pruefung entstanden ist, war
    STYLE_COLOR_NETWORK: der Name stand ZWEIMAL in einem dict, die
    spaetere Zeile gewann, und sie las "network" - einen Schluessel, den
    keine Vorgabe und kein Bedienelement kennt. Der Regler
    "Netzwerk/WLAN Modul" schrieb "bar_network" und faerbte nichts.

    Gemessen wird das seit dem 12.08.2026 an bar_text: die
    Modulfarben der Leiste sind entfallen, ihre Module tragen im
    Ruhezustand genau diesen Wert, und er ist damit der Schluessel, an
    dem derselbe Fehler wieder auftreten koennte.
    """
    _no_compositor(monkeypatch)
    style = _import_style_with(tmp_path, monkeypatch,
                               {"colors": {"bar_text": "#ff0000"}})

    assert style.STYLE_VARIABLES["STYLE_COLOR_BAR_TEXT"] == "#ff0000"


def test_a_colour_key_nothing_offers_reaches_no_generated_value(tmp_path,
                                                                monkeypatch):
    """The other half, and the one that has to stay true.

    Not "STYLE_COLOR_NETWORK is something else now" - EVERY style value,
    so that the second definition cannot come back under another name.
    """
    _no_compositor(monkeypatch)
    style = _import_style_with(tmp_path, monkeypatch,
                               {"colors": {"network": "#ff0000"}})

    assert "#ff0000" not in dict(style.STYLE_VARIABLES).values()


def test_every_colour_the_settings_offer_reaches_a_generated_value(tmp_path,
                                                                   monkeypatch):
    """The duplicate had company: a colour key can also be dead by never
    being read at all.

    Measured before the fix, with the settings below: "grid", "grid_bg",
    "footprint", "footprint_bg", "footprint_text" and the four
    "printer_*" keys reached nothing, because the placeholders that
    should have carried them were written out as literals - and the style
    editor offers a control for every one of them. "border" reached
    nothing either and is no longer offered.

    One import with every key set to a colour of its own, rather than one
    import per key: what is being asserted is that no key is missing from
    the answer, and that is one question about one answer.
    """
    _no_compositor(monkeypatch)
    monkeypatch.syspath_prepend(str(SRC))
    import user_settings

    keys = sorted(user_settings.DEFAULT_SETTINGS["colors"])
    sentinels = {key: f"#{index:06x}" for index, key in enumerate(keys, 1)}
    style = _import_style_with(tmp_path, monkeypatch, {"colors": sentinels})

    values = " ".join(dict(style.STYLE_VARIABLES).values())
    unreachable = [key for key in keys
                   # STYLE_COLOR_HYPRLAND_*_RAW carries the colour with
                   # its "#" cut off, which is still the colour arriving.
                   if sentinels[key] not in values
                   and sentinels[key].lstrip("#") not in values]

    assert unreachable == [], (
        "these settings are offered to the user and read by nothing: "
        + ", ".join(unreachable))


def test_a_stored_height_scale_changes_no_generated_value(tmp_path,
                                                          monkeypatch):
    """Why the height half of the scaling section was retired.

    It was offered with four defaults, migrated by user_settings and
    written back by every save. The only factor any placeholder is built
    from is the width one, so the two documents below - one with a height
    of 3.0 everywhere, one with none at all - have to produce the same
    style values, value for value.

    This test passed before the retirement as well. That is the point:
    it is the measurement that says the setting did nothing, and it now
    holds the decision shut. Wiring a height back up without removing
    the retirement fails here.
    """
    _no_compositor(monkeypatch)
    scaling = {"1920": {"width": 1.0}, "2560": {"width": 1.2},
               "3440": {"width": 1.35}, "3840": {"width": 1.5}}
    with_height = {bracket: {**value, "height": 3.0}
                   for bracket, value in scaling.items()}

    plain = _import_style_with(tmp_path / "plain", monkeypatch,
                               {"scaling": scaling})
    tall = _import_style_with(tmp_path / "tall", monkeypatch,
                              {"scaling": with_height})

    assert dict(tall.STYLE_VARIABLES) == dict(plain.STYLE_VARIABLES)


def test_the_width_scale_beside_it_does_change_what_is_generated(tmp_path,
                                                                 monkeypatch):
    """The control test for the one above.

    A comparison that finds no difference proves nothing unless the same
    comparison can find one. Same file, same shape, the other half of the
    bracket - and the answer moves.
    """
    monkeypatch.setattr(subprocess, "run", _answers(DESK))
    narrow = _import_style_with(tmp_path / "narrow", monkeypatch,
                                {"scaling": {"3440": {"width": 1.0}}})
    monkeypatch.setattr(subprocess, "run", _answers(DESK))
    wide = _import_style_with(tmp_path / "wide", monkeypatch,
                              {"scaling": {"3440": {"width": 2.0}}})

    # The third screen on the fixture desk is 3440 wide.
    assert narrow.STYLE_VARIABLES["STYLE_SCALE_FACTOR_MON2"] == "1.00"
    assert wide.STYLE_VARIABLES["STYLE_SCALE_FACTOR_MON2"] == "2.00"


# --------------------------------------------------------------------
# The per-screen placeholders, and why they are a table now
# --------------------------------------------------------------------

def test_no_per_screen_value_is_written_out_once_per_screen():
    """290 lines carried 58 values, and every one of them agreed.

    Every STYLE_*_MONx family in this file held the same value in all
    five slots - measured, with no exception among the fifty-eight - so
    each was ten or thirty lines copied five times, and every value that
    had to change had to change in five places. _WIDGET_WINDOW_WIDTHS
    was the same argument applied to a ninth family - widget window
    widths - until 18.08.2026, when it and the placeholders it built
    fell for want of a reader; see the note at
    style_definition._monitor_style_variables().

    It matters most for the type scale. The system has three answers to
    "how big is text" - pixels on the desktop, rem in the installer, and
    a size baked into a PF2 font file for GRUB - and the desktop's is
    the only one that could ever follow the screen, because it is the
    only one of the three that knows what is attached. That is a change
    to one table now rather than to five blocks.
    """
    source = (SRC / "style_definition.py").read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines()
                     if not line.lstrip().startswith("#"))

    written_out = re.findall(r'"(STYLE_[A-Z0-9_]*_MON[0-4])"\s*:', code)
    assert written_out == [], (
        "these per-screen placeholders are spelled out slot by slot "
        "again instead of coming from _per_screen(): "
        + ", ".join(sorted(set(written_out))))


def test_every_per_screen_family_still_reaches_all_five_slots(style):
    """The other half: a table is only safe if it still fills every slot.

    A template naming {{STYLE_EWW_FONT_BASE_MON4}} has to resolve on a
    one-screen machine, or the generation fails on a desk rather than on
    a mistake.
    """
    families = {}
    for name in style.STYLE_VARIABLES:
        match = re.fullmatch(r"(STYLE_.*)_MON([0-4])", name)
        if match:
            families.setdefault(match.group(1), set()).add(match.group(2))

    assert families, "no per-screen placeholders at all, which cannot be right"
    incomplete = {name: sorted(slots) for name, slots in families.items()
                  if slots != {"0", "1", "2", "3", "4"}}
    assert incomplete == {}, (
        f"these families do not cover all five slots: {incomplete}")


# --------------------------------------------------------------------
# was auf der Leiste steht - beide Haelften, einstellbar (Aufgabe #92)
# --------------------------------------------------------------------
#
# DIE FRAGE, DIE DIESER BLOCK STELLT, ist nicht "stimmen die Namen",
# sondern "gilt fuer beide Haelften dasselbe". Bis zum 12.08.2026 stand
# die linke Liste in src/templates/ags-bar.template und die rechte hier;
# eine Vorlage liest keine user-settings.json, also war die eine Haelfte
# der Leiste einstellbar und die andere nicht - ohne dass irgendwo
# stand, warum.

BAR_HALVES = ("modules_left", "modules_right")


def test_both_halves_of_the_bar_are_shipped_from_here(style):
    """Die Namen stehen in diesem Modul, und zwar beide Reihen.

    Eine Zusicherung ueber den ORT und nicht ueber den Inhalt: welche
    Module auf der Leiste stehen, ist eine Entscheidung, die sich aendern
    darf. Dass beide Reihen an derselben Stelle stehen wie der Rest der
    Einstellungen, ist keine.
    """
    for half in BAR_HALVES:
        assert style.SHIPPED_BAR_MODULES[half], (
            f"die ausgelieferte Liste {half} ist leer")

    left = json.loads(style.STYLE_VARIABLES["STYLE_BAR_MODULES_LEFT"])
    right = json.loads(style.STYLE_VARIABLES["STYLE_BAR_MODULES_RIGHT"])
    assert left == style.SHIPPED_BAR_MODULES["modules_left"]
    assert right == style.SHIPPED_BAR_MODULES["modules_right"]

    # Und die Vorlage traegt keine eigene Liste mehr. Ein Umzug, bei dem
    # die alte Fassung stehenbleibt, waere die zweite Liste, die dieses
    # Projekt an drei Stellen Catppuccin gekostet hat.
    bar = (SRC / "templates" / "ags-bar.template").read_text(encoding="utf-8")
    assert "const MODULES_LEFT: string[] = {{STYLE_BAR_MODULES_LEFT}}" in bar
    assert "custom/hypr-shortcuts" not in bar.split("switch (name)")[0], (
        "die Vorlage traegt ueber dem switch noch eine eigene Modulliste")


@pytest.mark.parametrize("half, placeholder", [
    ("modules_left", "STYLE_BAR_MODULES_LEFT"),
    ("modules_right", "STYLE_BAR_MODULES_RIGHT"),
])
def test_a_stored_order_replaces_the_shipped_one(tmp_path, monkeypatch,
                                                 half, placeholder):
    """Eine Liste ERSETZT die ausgelieferte vollstaendig - beide Haelften.

    Umgedreht und um einen Namen gekuerzt, weil beides zusammen die
    Aussage ist: die Reihenfolge ist die des Nutzers, und was er
    weggelassen hat, steht nicht mehr da. Ein Abschnitt, der bloss
    ergaenzt, waere eine Leiste, von der man nichts entfernen kann.
    """
    monkeypatch.setattr(subprocess, "run", _answers(DESK))
    shipped = _import_style(tmp_path / "vorher", monkeypatch).SHIPPED_BAR_MODULES[half]
    chosen = list(reversed(shipped))[:-1]

    style = _import_style_with(tmp_path / "nachher", monkeypatch,
                               {"bar": {half: chosen}})
    assert json.loads(style.STYLE_VARIABLES[placeholder]) == chosen


def test_the_shipped_order_is_used_when_the_section_says_null(tmp_path,
                                                              monkeypatch):
    """null heisst "wie ausgeliefert" und nicht "leer".

    Der Unterschied ist die ganze Leiste: als leere Liste gelesen waere
    ein Abschnitt, den die Einstellungs-Anwendung anlegt, bevor jemand
    etwas umgestellt hat, eine Leiste ohne Module.
    """
    monkeypatch.setattr(subprocess, "run", _answers(DESK))
    style = _import_style_with(
        tmp_path, monkeypatch,
        {"bar": {"modules_left": None, "modules_right": None,
                 "dock_pins": None}})

    for half, placeholder in [("modules_left", "STYLE_BAR_MODULES_LEFT"),
                              ("modules_right", "STYLE_BAR_MODULES_RIGHT")]:
        assert (json.loads(style.STYLE_VARIABLES[placeholder])
                == style.SHIPPED_BAR_MODULES[half])


def test_a_name_with_no_branch_is_dropped_and_said_out_loud(tmp_path,
                                                            monkeypatch,
                                                            capsys):
    """Ein Name, den die Leiste nicht kennt, waere ein leerer Platz.

    Und ein leerer Platz meldet sich nie von selbst - das ist Spec §7.4,
    dieselbe Regel, an der das Zahnrad im Fuss gescheitert ist. Also
    faellt der Name hier schon heraus, und der Erzeuger sagt es auf der
    Fehlerausgabe: dorthin, wo der Mensch gerade hinsieht, weil er eben
    etwas eingestellt hat.

    Die Leiste selbst hat dafuer noch einen Rueckfall (build() gibt null
    zurueck und schreibt "Unbekanntes Leistenmodul"), aber der steht im
    AGS-Protokoll, das niemand liest.

    GEPRUEFT WIRD GEGEN DAS MOEGLICHE UND NICHT GEGEN DAS AUSGELIEFERTE
        Das ist die zweite Haelfte dieser Zusicherung, und sie ist seit
        dem 12.08.2026 eine eigene Aussage: der Name unten steht in
        KEINER der beiden ausgelieferten Haelften und muss trotzdem
        stehenbleiben.

        Sonst hiesse "ich haette das gern zurueck" fuer den Erzeuger
        "(kennt diese Leiste nicht)" - und die Vorgabe zu aendern waere
        dasselbe wie eine Funktion zu loeschen.

        DER NAME WAR BIS ZUM 13.08.2026 `custom/weather`. Er steht
        seither wieder in der ausgelieferten linken Haelfte - der Nutzer
        wollte mehr auf der Leiste, nicht weniger -, und ein Test, der
        die Zuschaltbarkeit an einem AUSGELIEFERTEN Namen misst, misst
        sie nicht. `custom/wallpaper` ist jetzt der zuschaltbare Fall:
        ein Knopf ohne Anzeige, der nach der Regel in
        src/style_definition.py ins Kontrollzentrum gehoert.
    """
    monkeypatch.setattr(subprocess, "run", _answers(DESK))
    style = _import_style_with(
        tmp_path, monkeypatch,
        {"bar": {"modules_left": ["custom/wallpaper", "gibtsnicht"]}})

    assert "custom/wallpaper" not in style.SHIPPED_BAR_MODULES["modules_left"], (
        "dieser Test misst die Haelfte nicht mehr, wegen der er so "
        "heisst: custom/wallpaper steht wieder in der ausgelieferten "
        "Liste, also waere er auch ohne BAR_MODULES_AVAILABLE gruen")
    assert json.loads(style.STYLE_VARIABLES["STYLE_BAR_MODULES_LEFT"]) == [
        "custom/wallpaper"]

    complaint = capsys.readouterr().err
    assert "gibtsnicht" in complaint and "modules_left" in complaint, (
        "der Erzeuger verwirft den Namen still:\n" + complaint)


def test_the_imprint_carries_all_three_shipped_lists(tmp_path, monkeypatch):
    """/usr/share/zepos/shipped-bar.json, so wie package() es schreibt.

    Er ist der Weg, auf dem die Einstellungs-Anwendung die AUSGELIEFERTE
    Reihenfolge zeigt, ohne dieses Modul zu importieren - der Import
    hier fragt den Compositor, und ein Einstellungsfenster, das das
    braucht, geht auf einer Maschine ohne Hyprland nicht mehr auf.

    AUSGELIEFERT und nicht eingestellt, und das ist die zweite
    Zusicherung unten: gaebe er die Wahl des Nutzers zurueck, pruefte
    settings.bar_order() dessen gespeicherte Liste gegen sie selbst -
    und ein Name, den er einmal entfernt hat, waere fuer immer weg.

    UND EINE VIERTE LISTE, DAS MOEGLICHE
        Seit dem 12.08.2026 ist "was ausgeliefert wird" eine Auswahl
        aus "was die Leiste tragen kann". Ohne die vierte Liste im
        Abdruck kann das Einstellungsfenster ein zugeschaltetes Modul
        nicht von einem Schreibfehler unterscheiden - und boete unter
        "Wieder hinzufuegen" genau die zehn Namen NICHT an, um die es
        dabei geht.

    UND DIE ANHEFTUNGEN STEHEN NICHT DARIN - GEMESSEN AM 13.08.2026
        Hier wurde ein vierter Schluessel `dock_pins` verlangt, und der
        Paketbau ist daran gescheitert:

            AssertionError: {... 'dock_pins': []}

        package() macht `cd "$srcdir/zepos-$pkgver"`, und `python -c`
        stellt das Arbeitsverzeichnis VOR PYTHONPATH. Geladen wird also
        apps.py aus dem entpackten Tarball, und neben dem liegt kein
        packaging/ - weder Rezept noch Abdruck sind zu finden, die
        Antwort ist eine leere Liste. Der PYTHONPATH im Rezept hat fuer
        diese Importe nie gewirkt; sein Kommentar behauptete das
        Gegenteil und ist berichtigt.

        Der andere Weg waere gewesen, eine leere Liste zu erlauben.
        Dagegen steht dieselbe Regel, an der dieses Projekt sonst Kopien
        loescht: die Auswahl HAT mit
        /usr/share/zepos/shipped-applications ihren eigenen Abdruck,
        geschrieben von dem Paket, das sie kennt. Ein zweiter Ort, an
        dem sie leer steht und den jeder Leser kennen und ignorieren
        muss, ist schlechter als kein zweiter Ort.

        settings.shipped_bar() holt sie deshalb beim LESEN dort und gibt
        weiter alle vier Schluessel zurueck - fuer jeden Aufrufer aendert
        sich nichts. Geprueft wird hier die DATEI, und die traegt drei.
    """
    monkeypatch.setattr(subprocess, "run", _answers(DESK))
    style = _import_style_with(
        tmp_path, monkeypatch,
        {"bar": {"modules_left": ["custom/date"]}})

    imprint = style.shipped_bar_imprint()
    assert set(imprint) == {"modules_left", "modules_right",
                            "modules_available"}
    assert imprint["modules_left"] == style.SHIPPED_BAR_MODULES["modules_left"]
    assert imprint["modules_right"] == style.SHIPPED_BAR_MODULES["modules_right"]
    assert len(imprint["modules_left"]) > 1, (
        "der Abdruck traegt die Liste des Nutzers statt der ausgelieferten")

    # Das Moegliche enthaelt das Ausgelieferte - sonst stuende auf der
    # Leiste etwas, das dasselbe Fenster fuer unbekannt haelt - und ist
    # ECHT groesser, sonst gaebe es nichts zuzuschalten.
    available = imprint["modules_available"]
    for half in BAR_HALVES:
        missing = [name for name in imprint[half] if name not in available]
        assert missing == [], (
            f"ausgeliefert, aber nicht moeglich: {missing}")
    assert len(available) > len(imprint["modules_left"]) + len(
        imprint["modules_right"]), (
        "das Moegliche ist genau das Ausgelieferte - dann gibt es unter "
        "\"Wieder hinzufuegen\" nichts, und die Trennung ist Zierrat")
    assert len(set(available)) == len(available), (
        f"ein Name steht zweimal im Moeglichen: {available}")


def test_the_pins_come_from_the_one_place_that_knows_them():
    """Die Anheftungen, an der Quelle geprueft statt am Abdruck.

    Diese Zusicherungen standen bis zum 13.08.2026 im Test darueber und
    lasen `imprint["dock_pins"]`. Sie sind nicht weggefallen, sondern
    mitgezogen: seit der Abdruck die Anheftungen nicht mehr traegt, ist
    apps.imprint_pins() die Stelle, an der sie entstehen - und
    settings.shipped_bar() holt sie von dort.

    Was hier geprueft wird, ist unveraendert: dass es sie ueberhaupt
    gibt, dass jeder Eintrag seine drei Felder hat, und dass die
    Einstellungen darunter sind. Ohne den letzten Punkt koennte die
    Einstellungs-Anwendung sich selbst nicht anbieten.
    """
    sys.path.insert(0, str(SRC))
    try:
        import apps
    finally:
        sys.path.remove(str(SRC))

    pins = apps.imprint_pins()
    assert pins, "es sind keine Anheftungen zu finden"
    for pin in pins:
        assert set(pin) == {"name", "desktop", "label"}
        assert pin["desktop"] == f"{pin['name']}.desktop"
    assert {"name": "zepos-settings", "desktop": "zepos-settings.desktop",
            "label": "Systemeinstellungen"} in pins, (
        "die Einstellungen stehen nicht in der Auswahl, also kann die "
        f"Einstellungs-Anwendung sie nicht zeigen: {pins}")
