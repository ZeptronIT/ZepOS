# SPDX-License-Identifier: GPL-3.0-or-later
"""What the settings document keeps, and what it says about what it drops.

user_settings.py offered a height factor per resolution bracket, gave it
four defaults, migrated it into the shape it is stored in and wrote it
back on every save. Nothing read it: the only factor any placeholder is
built from is the width one, and what a widget is HIGH comes from
widget_sizes.<width>.<widget>.height, in pixels. See
tests/src/test_style_definition.py for the measurement - two documents
that differ only in that value produce identical style values.

So it goes. The tests here are about how it goes, which is the part a
user can be hurt by: a number somebody chose may not disappear out of
their own settings file without the file saying where it went.

Nothing here spawns a process or writes outside tmp_path; the module is
imported and called directly.
"""
import json

import pytest

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"


@pytest.fixture
def user_settings(tmp_path, monkeypatch):
    """The module, with both roots inside tmp_path.

    Flat import, the way the CLI runs it: src/ has no __init__.py and the
    module does `from paths import user_root`.
    """
    monkeypatch.delenv("ZEPOS_SYSTEM_ROOT", raising=False)
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.syspath_prepend(str(SRC))

    import user_settings as module
    return module


def _write(tmp_path: Path, document: dict) -> Path:
    path = tmp_path / "user-settings.json"
    path.write_text(json.dumps({"schema_version": 1, **document}),
                    encoding="utf-8")
    return path


# --------------------------------------------------------------------
# the height that did nothing
# --------------------------------------------------------------------

def test_the_defaults_no_longer_offer_a_height(user_settings):
    """A default is an offer. Offering one for a value nothing applies is
    how this survived four resolutions and a migration."""
    for bracket, value in user_settings.DEFAULT_SETTINGS["scaling"].items():
        assert set(value) == {"width"}, (
            f"the {bracket} bracket still offers {sorted(value)}")


def test_a_stored_height_is_moved_out_of_the_section_that_is_applied(
        user_settings, tmp_path):
    _write(tmp_path, {"scaling": {"2560": {"width": 1.2, "height": 1.1}}})

    settings = user_settings.load_settings()

    assert settings["scaling"]["2560"] == {"width": 1.2}


def test_a_stored_height_is_kept_where_the_document_says_what_happened(
        user_settings, tmp_path):
    """The honest half.

    Deleting it silently would leave whoever set 1.30 for their 4K screen
    looking for it in a file that no longer mentions it - and no way to
    tell "I never set that" from "something dropped it".
    """
    _write(tmp_path, {"scaling": {"3840": {"width": 1.5, "height": 1.3}}})

    settings = user_settings.load_settings()

    retired = settings["_meta"]["retired"]["scaling.height"]
    assert retired["values"] == {"3840": 1.3}, retired
    assert retired["reason"] == user_settings.RETIRED_SCALING_REASON
    assert retired["removed"], "nothing says when"


def test_the_retirement_reaches_the_file_when_something_saves(user_settings,
                                                              tmp_path):
    """load_settings only mutates what it hands back. The document on
    disk changes when a command writes one - and then it has to carry
    both halves: no height under scaling, and the value under _meta."""
    path = _write(tmp_path, {"scaling": {"2560": {"width": 1.2,
                                                  "height": 1.1}}})

    user_settings.save_settings(settings=user_settings.load_settings())

    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["scaling"]["2560"] == {"width": 1.2}
    assert (written["_meta"]["retired"]["scaling.height"]["values"]
            == {"2560": 1.1})


def test_a_retirement_already_recorded_is_not_overwritten(user_settings,
                                                          tmp_path):
    """Two brackets retired on two different days stay two entries. The
    record is the only place the numbers still exist."""
    _write(tmp_path, {
        "scaling": {"3840": {"width": 1.5, "height": 1.3}},
        "_meta": {"retired": {"scaling.height": {"values": {"2560": 1.1}}}},
    })

    settings = user_settings.load_settings()

    assert settings["_meta"]["retired"]["scaling.height"]["values"] == {
        "2560": 1.1, "3840": 1.3}


def test_a_document_with_no_height_is_left_alone(user_settings, tmp_path):
    """Nothing was retired, so nothing is recorded. A file that gains a
    "retired" section it has no reason for is noise in the one place a
    user goes looking for what they configured."""
    _write(tmp_path, {"scaling": {"2560": {"width": 1.2}}})

    settings = user_settings.load_settings()

    assert "retired" not in settings.get("_meta", {})


# --------------------------------------------------------------------
# the format before that
# --------------------------------------------------------------------

def test_a_bracket_written_as_one_number_still_migrates(user_settings,
                                                        tmp_path):
    """The oldest shape: one number per bracket, which was the width
    scale then and is the width scale now. It used to be copied into a
    height as well, which invented a value the user never chose."""
    _write(tmp_path, {"scaling": {"1920": 1.0, "2560": 1.25}})

    settings = user_settings.load_settings()

    assert settings["scaling"]["1920"] == {"width": 1.0}
    assert settings["scaling"]["2560"] == {"width": 1.25}


def test_a_scaling_section_that_is_not_an_object_does_not_raise(user_settings,
                                                                tmp_path):
    """A hand-edited file may hold anything. Deciding whether a document
    is usable belongs to settings.load(); what this must not do is fail
    on the way past, out of every command at once."""
    _write(tmp_path, {"scaling": "1.5"})

    settings = user_settings.load_settings()

    assert settings["scaling"] == "1.5"


def test_saving_a_scale_writes_the_shape_that_is_read(user_settings, tmp_path,
                                                      capsys):
    """`save --scale-2560` wrote a bare number - the format the migration
    exists to convert AWAY from - so every use of the command put the
    document back into the old shape and the next load migrated it
    again."""
    path = _write(tmp_path, {"scaling": {"2560": {"width": 1.2}}})

    class Arguments:
        scale_1920 = None
        scale_2560 = 1.4
        scale_3440 = None
        scale_3840 = None

    user_settings.cmd_save(Arguments())
    capsys.readouterr()

    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["scaling"]["2560"] == {"width": 1.4}


# --------------------------------------------------------------------
# die Schluessel, die nach der falschen Leiste hiessen
# --------------------------------------------------------------------
#
# Am 11.08.2026 sind waybar und nwg-dock-hyprland entfallen; die Leiste
# ist ags/widget/Bar.tsx. Dreizehn Farbschluessel und eine Groesse trugen
# den Namen des Programms, das sie gezeichnet hat, und heissen seither
# bar_*.
#
# WARUM DAS EINE MIGRATION BRAUCHT UND NICHT NUR EINE UMBENENNUNG
#     `set-color` prueft seinen Schluessel nicht - cmd_set_color schreibt
#     jeden Namen, den es bekommt. Ein umbenannter Eintrag faende also
#     seinen Weg nirgendwohin und niemand bekaeme es gesagt: der alte
#     Name bliebe in der Datei stehen, unveraendert, ungelesen, und der
#     Schreibtisch waere ueber Nacht wieder in den Vorgabefarben.

def test_a_stored_bar_colour_survives_the_rename(user_settings, tmp_path):
    """Der Wert wandert mit, der alte Name verschwindet.

    Beides, und beides einzeln geprueft: bliebe der alte Name stehen,
    stuende in der Datei eine Frage, die niemand mehr beantworten kann -
    welcher von beiden gilt.
    """
    # waybar_text und waybar_tray, nicht mehr waybar_bg: dessen Ziel
    # bar_bg ist am 12.08.2026 geloescht worden, weil es keine Vorlage
    # erreichte, und mit ihm die Zeile in RENAMED_KEYS.
    _write(tmp_path, {"colors": {"waybar_text": "#123456",
                                 "waybar_workspace_visible": "#abcdef"}})

    settings = user_settings.load_settings()

    assert settings["colors"]["bar_text"] == "#123456"
    assert settings["colors"]["bar_workspace_visible"] == "#abcdef"
    assert "waybar_text" not in settings["colors"]
    assert "waybar_workspace_visible" not in settings["colors"]


def test_the_newer_name_wins_over_the_older_one(user_settings, tmp_path):
    """Hat der Nutzer nach der Umbenennung schon einmal `set-color --key
    bar_bg` gesagt, ist DAS die juengere Aussage.

    Der alte Eintrag verschwindet trotzdem - sonst bliebe die Frage in
    der Datei stehen.
    """
    _write(tmp_path, {"colors": {"waybar_text": "#111111",
                                 "bar_text": "#222222"}})

    settings = user_settings.load_settings()

    assert settings["colors"]["bar_text"] == "#222222"
    assert "waybar_text" not in settings["colors"]


def test_a_stored_bar_size_survives_the_rename(user_settings, tmp_path):
    """Dieselbe Umbenennung, andere Sektion.

    sizes.values wird gegen sizes.TABLE geprueft - anders als die
    Farben -, aber die PRUEFUNG greift nur beim Schreiben. Ein Wert, der
    vor der Umbenennung in die Datei kam, steht dort weiterhin unter dem
    alten Namen und wuerde beim Erzeugen einfach nicht gefunden.
    """
    _write(tmp_path, {"sizes": {"scale": 1.0,
                                "values": {"STYLE_MARGIN_TOP": "30px"}}})

    settings = user_settings.load_settings()
    values = settings["sizes"]["values"]

    assert values["STYLE_CHIP_GAP"] == "30px"
    assert "STYLE_MARGIN_TOP" not in values


def test_a_size_that_no_longer_exists_is_removed_from_the_document(
        user_settings, tmp_path):
    """Ein Einzelwert ohne Groesse dahinter ist ein Regler ohne Leser.

    STYLE_BAR_EDGE_SPACING ist am 12.08.2026 entfallen - die Module der
    Leiste fangen jetzt an der Kante der Platte an, und der Abstand zum
    Schirmrand heisst ueberall STYLE_GAPS_OUT. Ein Dokument, das den
    alten Namen behaelt, traegt ihn bei jedem Speichern weiter mit, und
    beim naechsten Lesen haelt ihn jemand fuer eine Einstellung.
    """
    _write(tmp_path, {"sizes": {"scale": 1.0, "values": {
        "STYLE_WAYBAR_EDGE_SPACING": "30px",
        "STYLE_BAR_EDGE_SPACING": "30px",
        "STYLE_DOCK_MARGIN_BOTTOM": "10",
        "STYLE_CHIP_GAP": "12px"}}})

    values = user_settings.load_settings()["sizes"]["values"]

    assert values == {"STYLE_CHIP_GAP": "12px"}, values
    from src import sizes

    for gone in user_settings.RETIRED_SIZE_VALUES:
        assert gone not in sizes.TABLE, (
            f"{gone} steht wieder in der Groessentabelle - dann darf die "
            "Migration ihn nicht wegraeumen")


def test_a_document_with_none_of_the_old_names_is_left_alone(user_settings,
                                                             tmp_path):
    """Die Gegenprobe. Eine Migration, die auch dann etwas anfasst, wenn
    es nichts zu migrieren gibt, ist eine Migration, die bei jedem Laden
    eine Aenderung erfindet."""
    _write(tmp_path, {"colors": {"bar_bg": "#333333"}})

    settings = user_settings.load_settings()

    assert settings["colors"]["bar_bg"] == "#333333"
    assert [key for key in settings["colors"] if key.startswith("waybar")] == []


def test_every_renamed_key_names_a_colour_the_style_layer_knows(user_settings):
    """Die Tabelle darf nicht von der Marke wegdriften.

    Ein Ziel, das brand.COLORS nicht kennt, waere eine Migration, die
    einen Wert auf einen Namen schiebt, den get_user_color() mit einem
    KeyError beantwortet - also ein Lauf, der ueberhaupt nichts mehr
    erzeugt, ausgeloest durch das blosse LADEN der Einstellungen.
    """
    import brand
    import sizes

    for old, new in user_settings.RENAMED_KEYS["colors"].items():
        assert new in brand.COLORS, f"{old} -> {new} kennt brand.py nicht"
        assert old not in brand.COLORS, f"{old} steht noch in brand.py"

    for old, new in user_settings.RENAMED_SIZE_VALUES.items():
        assert new in sizes.TABLE, f"{old} -> {new} kennt sizes.TABLE nicht"
        assert old not in sizes.TABLE, f"{old} steht noch in sizes.TABLE"


# --------------------------------------------------------------------
# Die Farben, die nur gelesen und trotzdem geschrieben wurden
# --------------------------------------------------------------------
#
# GEMESSEN am 12.08.2026, als es Themen gab: load_settings() verschmilzt
# mit DEFAULT_SETTINGS, also traegt jedes geladene Dokument alle siebzig
# Farben - auch das eines Kontos, das nie eine angefasst hat.
# save_settings() schrieb es vollstaendig zurueck. Ein einziges
# `set-weather` genuegte damit, um jede kuenftige Themenumschaltung
# wirkungslos zu machen, denn get_user_color() fragt die
# Einstellungsdatei ZUERST.
#
# Bis es Themen gab, war das folgenlos - die siebzig Werte waren
# dieselben, die brand.py ohnehin geliefert haette. Genau deshalb hat es
# niemand bemerkt.

def test_setting_a_location_does_not_pin_every_colour(user_settings,
                                                      tmp_path):
    """Der Fehler in seiner urspruenglichen Form.

    Ein Wetterort ist keine Aussage ueber Farben. Stuenden sie danach
    doch in der Datei, waere der Themenwaehler ein Regler, der nichts
    bewegt - und zwar erst ab dem Tag, an dem jemand einmal etwas
    anderes eingestellt hat.
    """
    user_settings.set_weather_location("Kiel")

    document = json.loads(
        (tmp_path / "user-settings.json").read_text(encoding="utf-8"))
    assert document["weather"]["location"] == "Kiel"
    assert document.get("colors", {}) == {}, (
        "ein Wetterort hat die ganze Palette festgeschrieben")


def test_a_colour_the_user_really_chose_is_kept(user_settings, tmp_path):
    """Und die Gegenprobe, ohne die der Filter zu viel wegnaehme.

    Wer eine Farbe eingestellt hat, hat etwas gesagt. Sie muss jeden
    Themenwechsel ueberleben - das ist die ganze Schichtung, auf der
    get_user_color() beruht.
    """
    _write(tmp_path, {"colors": {"bar_text": "#123456"}})
    user_settings.set_weather_location("Kiel")

    document = json.loads(
        (tmp_path / "user-settings.json").read_text(encoding="utf-8"))
    assert document["colors"] == {"bar_text": "#123456"}


def test_resetting_the_colours_hands_them_back_to_the_theme(user_settings,
                                                            tmp_path):
    """"Zuruecksetzen" heisst seit dem 12.08.2026 "keine eigene Meinung".

    Vorher schrieb es die siebzig ausgelieferten Werte in die Datei -
    also genau den Zustand, in dem ein Themenwechsel nichts mehr tut.
    Ein Zuruecksetzen, das eine Einstellung UNMOEGLICH macht, ist kein
    Zuruecksetzen.
    """
    _write(tmp_path, {"colors": {"bar_text": "#123456"}})
    user_settings.reset_colors()

    document = json.loads(
        (tmp_path / "user-settings.json").read_text(encoding="utf-8"))
    assert document.get("colors", {}) == {}
