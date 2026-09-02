# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Entscheidungen der Einstellungs-Anwendung, ohne Anzeige gemessen.

Alles, was hier steht, koennte auch im kopflosen Lauf stehen und stuende
dort schlechter: ein Fenster zu bauen kostet eine Anzeige, einen
Kindprozess und zwei Sekunden, und keine dieser Zusicherungen braucht
davon irgendetwas. Was den kopflosen Lauf braucht, ist die Frage, ob die
Widgets ueberhaupt an diesen Entscheidungen haengen - und die steht in
test_settings_headless.py.

DIE WICHTIGSTE DATEI IN DIESEM VERZEICHNIS IST DIE ERSTE PRUEFUNG UNTEN.
Sie rechnet fuer JEDE angebotene Farbe nach, dass eine Aenderung daran in
einer erzeugten Datei ankommt. Genau das war bei neunundzwanzig von
neunundneunzig nicht der Fall, und niemand hat es gemerkt, weil eine
Einstellung, die nichts tut, in der Datei und im Editor genauso aussieht
wie eine, die etwas tut.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
SETTINGS_ROOT = ROOT / "settings"


@pytest.fixture
def model(monkeypatch, tmp_path):
    """model.py mit src/ auf dem Pfad, so wie der Befehl es hinlegt.

    src/ hat kein __init__.py und jedes Modul darin importiert flach -
    dieselbe Fixture-Form wie in tests/src/test_brand.py, und aus
    demselben Grund muss der Pfad danach wieder herunter: ein
    liegengelassenes src/ laesst tests/src/test_placeholders.py
    durchgehen, wo es abbrechen soll.
    """
    monkeypatch.syspath_prepend(str(SRC))
    monkeypatch.syspath_prepend(str(SETTINGS_ROOT))
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path / "zepos"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("ZEPOS_MACHINE_ROOT", str(tmp_path / "etc-zepos"))
    monkeypatch.setenv("ZEPOS_SYSTEMD_ETC", str(tmp_path / "etc"))
    # NACHGETRAGEN am 20.08.2026: seit Draft.sections() die
    # hinterlegte Vorgabe der Anheftungen mitschreibt, liest diese
    # Fixture den Abdruck - und ohne diese Zeile waere das
    # /usr/share/zepos der Maschine, auf der die Tests laufen. Auf einem
    # Rechner ohne installiertes ZepOS faellt das nicht auf (die Datei
    # fehlt, die Antwort ist "unbekannt"); auf einem MIT hinge das
    # Ergebnis daran, welche Fassung dort gerade installiert ist. Ein
    # Test, dessen Antwort die Maschine gibt, misst die Maschine.
    monkeypatch.setenv("ZEPOS_SYSTEM_ROOT", str(tmp_path / "share-zepos"))
    for name in list(sys.modules):
        if name.startswith("zepos_settings_gui") or name in (
                "brand", "sizes", "settings", "update", "paths"):
            monkeypatch.delitem(sys.modules, name, raising=False)
    from zepos_settings_gui import model as module

    return module


@pytest.fixture
def settings_module(monkeypatch, tmp_path):
    """src/settings.py, mit einer Wurzel, die niemandem gehoert.

    Eigene Fixture und nicht `model.settings_file`: was hier geprueft
    wird, sind die Regeln des Abschnitts selbst - der Erzeuger liest
    dieselben, und ein Test, der sie durch die Oberflaeche hindurch
    misst, koennte nicht mehr sagen, welche der beiden Seiten sie
    traegt.
    """
    monkeypatch.syspath_prepend(str(SRC))
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    for name in ("settings", "paths", "sizes"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    import settings as module

    return module


@pytest.fixture
def brand(monkeypatch):
    monkeypatch.syspath_prepend(str(SRC))
    monkeypatch.delitem(sys.modules, "brand", raising=False)
    import brand as module

    return module


# --------------------------------------------------------------------
# Jeder Regler muss wirken
# --------------------------------------------------------------------

def _placeholders_named_by_a_template() -> set[str]:
    named: set[str] = set()
    for directory in ("templates", "styles", "system"):
        for path in sorted((SRC / directory).glob("*.template")):
            named |= set(re.findall(r"\{\{([A-Z0-9_]+)\}\}",
                                    path.read_text(encoding="utf-8")))
    return named


def _style_variables(home: Path, document: dict | None, monkeypatch) -> dict:
    """Die Stil-SSOT ueber einer Einstellungsdatei, frisch eingelesen.

    Sie liest die Datei beim IMPORT, also gibt es keinen anderen Weg,
    ihr andere Einstellungen zu geben, als sie neu zu importieren -
    dasselbe Verfahren wie in tests/src/test_sizes.py.
    """
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    monkeypatch.delenv("ZEPOS_SYSTEM_ROOT", raising=False)
    if document is not None:
        (home / "user-settings.json").write_text(
            json.dumps({"schema_version": 1, **document}), encoding="utf-8")
    spec = importlib.util.spec_from_file_location(
        f"zepos_style_colour_probe_{home.name}", SRC / "style_definition.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.STYLE_VARIABLES


def test_every_colour_the_application_offers_reaches_a_generated_file(
        brand, tmp_path, monkeypatch):
    """Die Pruefung, an der neunundzwanzig Farben gefallen sind.

    Fuer jede Farbe der Reihe nach: einen Sentinel setzen, die Stil-SSOT
    neu einlesen, sehen welche {{STYLE_*}} sich bewegen - und ob
    irgendeine Vorlage einen davon nennt. Bewegt sich keiner, den eine
    Vorlage liest, dann ist die Farbe ein Regler ohne Wirkung.

    Aufgezaehlt aus brand.COLORS und nicht aus einer Liste von Hand: eine
    Liste von Hand haette genau die Farbe nicht drin, die jemand
    hinzufuegt, ohne sie zu verdrahten.

    Die Gegenrichtung - dass die Anwendung jede Farbe auch WIRKLICH
    zeigt - steht in test_the_groups_cover_the_palette_exactly() weiter
    unten, und der kopflose Lauf zaehlt die Knoepfe im Fenster nach.
    """
    monkeypatch.syspath_prepend(str(SRC))
    named = _placeholders_named_by_a_template()
    baseline = _style_variables(tmp_path / "base", None, monkeypatch)

    sentinel = "#123457"
    unread = []
    for index, key in enumerate(sorted(brand.COLORS)):
        variables = _style_variables(
            tmp_path / f"k{index}", {"colors": {key: sentinel}}, monkeypatch)
        moved = {name for name, value in variables.items()
                 if value != baseline.get(name)}
        assert moved, f"{key} bewegt nicht einmal einen Platzhalter"
        if not moved & named:
            unread.append(f"{key} (nur {', '.join(sorted(moved))})")

    assert unread == [], (
        "diese Farben lassen sich einstellen und erreichen keine "
        "erzeugte Datei - genau der Zustand, in dem MONITOR_HEIGHT_SCALES "
        "war:\n  " + "\n  ".join(unread))


def test_the_groups_cover_the_palette_exactly(brand):
    """Die Farbseite zeigt brand.COLOR_GROUPS. Was dort fehlt, ist fuer
    einen Nutzer nicht vorhanden; was dort zuviel steht, ist ein Knopf
    auf eine Farbe, die es nicht gibt.

    In beide Richtungen, und ohne Doppelung: ein Schluessel in zwei
    Gruppen waere zwei Knoepfe auf einen Wert, von denen der zweite den
    ersten still ueberschreibt.
    """
    keys = [key for _name, rows in brand.COLOR_GROUPS for key, _label in rows]

    assert len(keys) == len(set(keys)), "eine Farbe steht in zwei Gruppen"
    assert set(keys) == set(brand.COLORS), (
        "fehlen in den Gruppen: "
        f"{sorted(set(brand.COLORS) - set(keys))}; "
        "gibt es gar nicht: "
        f"{sorted(set(keys) - set(brand.COLORS))}")
    assert all(rows for _name, rows in brand.COLOR_GROUPS), (
        "eine Gruppe ist leer - eine Ueberschrift ohne Zeile darunter")
    assert all(label.strip() for _name, rows in brand.COLOR_GROUPS
               for _key, label in rows), "eine Farbe hat keine Beschriftung"


def test_the_style_editor_reads_the_same_table(brand):
    """Der Stil-Editor im Schreibtisch trug diese Tabelle als Literal.

    Jetzt nicht mehr: er liest {{STYLE_COLOR_GROUPS_JSON}}. Ohne diese
    Pruefung koennte jemand das Literal zurueckschreiben, und die zweite
    Kopie waere wieder da - unbemerkt, weil beide Oberflaechen dann
    weiterhin funktionieren, nur eben mit zwei Listen, die
    auseinanderlaufen.
    """
    editor = (SRC / "templates" / "ags-style-editor.template").read_text(
        encoding="utf-8")

    assert "{{STYLE_COLOR_GROUPS_JSON}}" in editor, (
        "der Stil-Editor liest die Farbgruppen nicht aus der Mitte")
    body = "\n".join(line for line in editor.splitlines()
                     if not line.lstrip().startswith("//"))
    assert 'name: "Status Farben"' not in body, (
        "der Editor traegt wieder eine eigene Gruppentabelle")


@pytest.mark.parametrize("index", range(5))
def test_every_dial_names_a_size_this_system_has(model, index):
    """Ein Platzhaltername mit einem Tippfehler waere ein Regler, den
    `set_size` mit einem KeyError ablehnt - oder, schlimmer, ein
    Eintrag in sizes.values, den niemand liest."""
    import sizes

    dial = model.DIALS[index]
    assert dial.name in sizes.TABLE, f"{dial.name} steht nicht in sizes.TABLE"
    for name, _ratio in dial.also:
        assert name in sizes.TABLE, f"{name} steht nicht in sizes.TABLE"
    assert dial.minimum < dial.maximum
    assert dial.label.strip() and dial.note.strip()


def test_the_dials_are_a_subset_and_the_page_says_how_many_are_not(model):
    """Fuenf von fuenfzig, und das ist eine Entscheidung.

    Die Zahl steht in der Oberflaeche, damit "hier nicht" nicht wie
    "gar nicht" aussieht - und sie wird dort aus sizes.TABLE GERECHNET
    und nicht getippt. Genau das prueft diese Zusicherung: eine getippte
    Zahl waere ab der naechsten neuen Groesse falsch, und niemand
    bekaeme es gesagt.

    GEPRUEFT WIRD SEIT DEM 19.08.2026 (Aufgabe 32) model.py UND NICHT
    MEHR app.py: der Satz, der die Zahl nennt, ist als NOTE_SIZES_REST
    dorthin gezogen, weil ihn seither ZWEI Fenster zeigen (das GTK- und
    das AGS-Fenster, ueber bridge.py). Die Zusicherung selbst ist
    dieselbe geblieben - sie zeigt nur dorthin, wo der Satz jetzt
    wohnt. `len(DIALS)` statt `len(model.DIALS)`, weil model.py auf
    seine eigene Tabelle ohne Modulnamen zeigt.
    """
    import sizes

    names = {dial.name for dial in model.DIALS}
    assert names < set(sizes.TABLE)
    assert len(names) == len(model.DIALS), "ein Regler steht doppelt"

    source = (SETTINGS_ROOT / "zepos_settings_gui" / "model.py").read_text(
        encoding="utf-8")
    # GERECHNET und nicht getippt, wie vorher - nur steht die
    # Rechnung seit dem 02.09.2026 in sizes_rest_note() und nicht
    # mehr in der Konstante: der msgid traegt {total}/{rest},
    # damit eine neue Groesse in sizes.TABLE nicht jedes Mal
    # einen neuen Katalogeintrag verlangt.
    assert "len(sizes.TABLE)" in source, (
        "die Anwendung nennt die Zahl der einstellbaren Groessen nicht "
        "mehr aus der Tabelle")
    assert "len(sizes.TABLE) - len(DIALS)" in source
    assert "{total}" in model.NOTE_SIZES_REST
    assert "{rest}" in model.NOTE_SIZES_REST


# --------------------------------------------------------------------
# Der Entwurf und was er schreibt
# --------------------------------------------------------------------

def test_a_saved_section_carries_everything_that_was_in_it(model, tmp_path):
    """settings.merge() ERSETZT einen Abschnitt.

    Nur das Geaenderte zu schicken hiesse, jede Farbe zu loeschen, die
    dieses Fenster nicht angefasst hat - der Fehler, den die beiden
    AGS-Dialoge einmal hatten, nur an einer anderen Stelle.
    """
    draft = model.Draft(document={
        "schema_version": 1,
        "colors": {"warning": "#111111", "critical": "#222222"},
    })
    draft.colours["warning"] = "#333333"

    sections = draft.sections()
    assert sections["colors"] == {"warning": "#333333", "critical": "#222222"}


def test_an_untouched_section_is_not_written_at_all(model):
    """Ein Abschnitt, den niemand angefasst hat, darf nicht in der
    Schreibliste stehen: settings.merge() ersetzt ihn dann durch das,
    was diese Anwendung von ihm weiss - und das ist weniger, als in der
    Datei steht."""
    draft = model.Draft(document={"schema_version": 1})
    assert draft.sections() == {}
    assert not draft.dirty()

    draft.weather = "Bochum"
    assert set(draft.sections()) == {"weather"}


def test_a_named_size_carries_the_unit_its_reader_needs(model):
    """kitty liest eine nackte Zahl und scheitert an "18px"; ein
    Stylesheet braucht die Einheit. Die Tabelle weiss, welche."""
    draft = model.Draft(document={"schema_version": 1})
    by_name = {dial.name: dial for dial in model.DIALS}

    draft.set_dial(by_name["STYLE_TERMINAL_FONT_SIZE"], 18)
    draft.set_dial(by_name["STYLE_BAR_THICKNESS"], 120)

    values = draft.sections()["sizes"]["values"]
    # Beide ohne Einheit, weil beide Leser eine nackte Zahl nehmen -
    # kitty und ags-bar.template. Die Tabelle sagt das, nicht dieser Test.
    assert values["STYLE_TERMINAL_FONT_SIZE"] == "18"
    assert values["STYLE_BAR_THICKNESS"] == "120"

    # Und die Gegenprobe an einer Groesse, deren Leser ein Stylesheet
    # ist: ohne das "px" verwirft GTK die ganze Deklaration.
    assert model.size_text("STYLE_LAUNCHER_ROW_MIN_HEIGHT", 40) == "40px"


def test_the_window_gap_writes_one_half_and_derives_the_other(model):
    """2*gaps_in == gaps_out, und zwar ohne dass jemand beides einstellt.

    Der Regler schrieb bis zum 12.08.2026 BEIDE Zahlen - gaps_out und
    daneben die Haelfte davon als gaps_in. Das hielt die Gleichung genau
    so lange, wie niemand am Groessenregler drehte: value_of() rundet
    kaufmaennisch, und bei der neuen ausgelieferten Groesse wurde aus 8
    eine 12 (abgerundet) und aus 16 eine 25 (aufgerundet). Seither ist
    der aeussere Abstand in src/sizes.py ABGELEITET, und einstellbar ist
    der innere.
    """
    import sizes

    draft = model.Draft(document={"schema_version": 1})
    gap = next(d for d in model.DIALS if d.name == "STYLE_GAPS_IN")
    assert not any(d.name == "STYLE_GAPS_OUT" for d in model.DIALS), (
        "der aeussere Abstand ist wieder einzeln einstellbar - dann gibt "
        "es zwei Regler fuer eine Gleichung")

    draft.set_dial(gap, 10)
    values = draft.sections()["sizes"]["values"]
    assert values == {"STYLE_GAPS_IN": "10"}, values
    assert sizes.value_of("STYLE_GAPS_OUT", {"values": values}) == "20"

    draft.clear_dial(gap)
    assert draft.sections()["sizes"]["values"] == {}


def test_a_colour_survives_the_trip_through_gtks_floats(model):
    """Gdk.RGBA rechnet in Anteilen zwischen 0 und 1.

    Der Hin- und Rueckweg allein beweist die Rundung NICHT, und das ist
    gemessen: fuer alle 256 Bytewerte ist int(v / 255 * 255) wieder v,
    also besteht auch eine abschneidende Fassung diese Haelfte. Sie faellt
    erst an einem Anteil, der nicht aus einem Byte kam - und genau die
    liefert der Farbwaehler, sobald jemand im Farbkreis zieht statt eine
    Zahl einzutippen. Abgeschnitten wandert die Farbe dann um einen
    Wert, und jedes Oeffnen des Fensters waere eine Aenderung.
    """
    for colour in ("#000000", "#ffffff", "#0d3d47", "#33c9ee", "#010203"):
        assert model.hex_of(*model.rgb_of(colour)) == colour

    # 0.999999 * 255 = 254.99..., 0.5 * 255 = 127.5. Kaufmaennisch
    # gerundet sind das ff und 80; abgeschnitten fe und 7f.
    assert model.hex_of(0.999999, 0.5, 0.0) == "#ff8000"


# --------------------------------------------------------------------
# Die Leiste und das Dock
# --------------------------------------------------------------------
#
# Die Regeln stehen in src/settings.py, neben dem Abschnitt, den sie
# beschreiben, weil zwei Programme sie lesen: der Erzeuger, der die
# Namen in ags-bar.template einsetzt, und diese Anwendung. Geprueft
# werden sie deshalb hier an der Quelle und nicht an der Oberflaeche -
# was die Widgets daraus machen, misst der kopflose Lauf.

def test_a_bar_setting_is_a_list_of_names_or_the_word_null(settings_module):
    """Die Pruefung, ohne die eine falsche Form still verschwaende.

    `zepos-settings set bar.modules_right tray` schreibt eine
    ZEICHENKETTE - der Befehl nimmt jeden Wert entgegen, der kein JSON
    ist, und das ist fuer einen Ortsnamen richtig. Ohne diese Ablehnung
    laese der Erzeuger daraus eine Leiste aus vier Buchstaben oder gar
    nichts, und der Nutzer suchte den Fehler auf seiner Leiste.
    """
    settings = settings_module

    for key in settings.BAR_KEYS:
        assert settings.defaults()["bar"][key] is None, (
            "die Vorgabe traegt eine abgeschriebene Liste - genau die "
            "Kopie, die veraltet, sobald jemand ein Modul umbenennt")
        assert settings.bar_choice({"bar": {key: ["tray"]}}, key) == ["tray"]
        assert settings.bar_choice({"bar": {key: None}}, key) is None
        assert settings.bar_choice({}, key) is None

        for wrong in ("tray", 5, {"tray": True}, ["tray", 5], [None]):
            with pytest.raises(settings.UnusableSettings):
                settings.bar_choice({"bar": {key: wrong}}, key)

    with pytest.raises(settings.UnusableSettings):
        settings.bar_choice({"bar": "tray"}, settings.BAR_RIGHT)
    with pytest.raises(KeyError):
        settings.bar_choice({}, "modules_middle")


def test_an_empty_list_is_not_the_same_as_no_list(settings_module):
    """[] heisst "auf dieser Seite steht nichts" und null "wie
    ausgeliefert".

    Beide sind in jeder Wahrheitspruefung falsch, und genau daran
    scheitert die naheliegende Fassung: `chosen or shipped` gaebe dem
    Nutzer, der alles heruntergenommen hat, beim naechsten Oeffnen die
    ganze Leiste zurueck - und beim Speichern schriebe er sie sich fest.
    """
    settings = settings_module

    assert settings.bar_choice({"bar": {"modules_right": []}},
                               settings.BAR_RIGHT) == []
    assert settings.bar_order([], ["tray"], ["tray"]) == ([], [])
    assert settings.bar_order(None, ["tray"], ["tray"]) == (["tray"], [])


def test_a_name_the_bar_does_not_have_is_dropped_and_named(settings_module):
    """Ein Name ohne Zweig ist ein leerer Platz, und ein leerer Platz
    meldet sich nie von selbst.

    Er entsteht nicht aus Boesswilligkeit, sondern von allein: ein Modul
    wird umbenannt, und in der Einstellungsdatei jedes Nutzers steht der
    alte Name weiter. Ihn still zu behalten hiesse, auf der Leiste eine
    Luecke zu erzeugen; ihn still zu verwerfen hiesse, ein Modul
    verschwinden zu lassen, ohne dass jemand sagt, warum.

    Also beides: verworfen UND genannt.
    """
    settings = settings_module

    # Geprueft wird gegen das MOEGLICHE (zweites Argument) und nicht
    # gegen das Ausgelieferte (drittes): `network` steht hier absichtlich
    # nur im Moeglichen und muss trotzdem stehenbleiben - seit dem
    # 12.08.2026 ist die Vorgabe eine Auswahl, und ein zugeschaltetes
    # Modul darf nicht als unbekannt gelten.
    kept, discarded = settings.bar_order(
        ["tray", "custom/weg", "network", "tray"], ["network", "tray"],
        ["tray"])

    assert kept == ["tray", "network"]
    assert discarded == [("custom/weg", settings.BAR_UNKNOWN),
                         ("tray", settings.BAR_REPEATED)]

    complaint = settings.bar_complaint(settings.BAR_RIGHT, discarded)
    assert "custom/weg" in complaint and settings.BAR_UNKNOWN in complaint
    assert settings.BAR_REPEATED in complaint
    assert settings.bar_complaint(settings.BAR_RIGHT, []) == ""

    # Und gegen eine UNBEKANNTE Auslieferung wird nichts verworfen: eine
    # Liste gegen nichts zu pruefen hiesse, jeden Namen fuer unbekannt
    # zu halten und dem Nutzer seine Leiste wegen einer fehlenden Datei
    # zu nehmen.
    assert settings.bar_order(["tray", "custom/weg"], None, ["tray"]) == (
        ["tray", "custom/weg"], [])


def test_the_shipped_order_is_read_from_an_imprint_and_not_typed_here(
        settings_module, tmp_path, monkeypatch):
    """Derselbe Kniff wie bei shipped-applications, und aus demselben
    Grund.

    Diese Anwendung darf den Erzeuger nicht importieren -
    src/style_definition.py fragt beim Import `hyprctl` nach den
    Bildschirmen -, und die ausgelieferte Reihenfolge zweimal
    hinzuschreiben waere die Kopie, die dieses Projekt schon dreimal
    bezahlt hat. Also liest sie den Abdruck, den der Erzeugungslauf
    hinterlegt.

    Drei Lagen, und alle drei sind verschieden: da, fehlt, kaputt.
    """
    settings = settings_module
    monkeypatch.setenv("ZEPOS_SYSTEM_ROOT", str(tmp_path))

    assert settings.shipped_bar() is None, (
        "ein fehlender Abdruck muss UNBEKANNT heissen und nicht LEER - "
        "gegen eine leere Liste geprueft waere jeder gespeicherte Name "
        "unbekannt")

    target = tmp_path / settings.SHIPPED_BAR
    target.write_text(json.dumps({
        "modules_left": ["custom/date"],
        "modules_right": ["tray"],
        "dock_pins": [{"name": "firefox", "desktop": "firefox.desktop",
                       "label": "Firefox"}],
    }), encoding="utf-8")

    imprint = settings.shipped_bar()
    assert settings.bar_names(imprint, settings.BAR_LEFT) == ["custom/date"]
    assert settings.bar_names(imprint, settings.BAR_PINS) == ["firefox"]
    assert settings.bar_labels(imprint, settings.BAR_PINS) == {
        "firefox": "Firefox"}
    # Ein Leistenmodul hat keine Beschriftung: es IST der Name, unter dem
    # sein Zweig in ags-bar.template steht.
    assert settings.bar_labels(imprint, settings.BAR_LEFT) == {}
    assert settings.bar_names(None, settings.BAR_LEFT) is None

    # Eine Datei, die DA ist und nicht gelesen werden kann, ist ein
    # Fehler dieses Systems - sie wird erzeugt - und wird gemeldet
    # statt als "leer" gelesen.
    target.write_text("{kein json", encoding="utf-8")
    with pytest.raises(settings.UnusableSettings):
        settings.shipped_bar()


def test_the_check_command_names_a_bar_that_cannot_be_read(settings_module,
                                                           tmp_path, capsys):
    """`zepos-settings check` ist der Befehl, den jemand aufruft, wenn
    etwas nicht stimmt - also muss er das hier sagen koennen.

    Alle drei Haelften auf einmal: wer links falsch geschrieben hat, hat
    es moeglicherweise auch rechts getan, und eine Meldung nach der
    anderen zu erarbeiten ist die Sitzung, die niemand zu Ende bringt.
    """
    settings = settings_module

    assert settings.check_bar({"bar": {"modules_right": ["tray"]}}) == []

    problems = settings.check_bar(
        {"bar": {"modules_left": "custom/date", "modules_right": 5}})
    assert len(problems) == 2, problems

    target = tmp_path / settings.FILENAME
    target.write_text(json.dumps(
        {"schema_version": settings.SCHEMA_VERSION,
         "bar": {"modules_right": "tray"}}), encoding="utf-8")

    assert settings.main(["check"]) == 1
    said = capsys.readouterr().err
    assert "bar.modules_right" in said, said
    assert str(target) in said, said


def test_resetting_a_side_writes_null_and_not_the_list_it_shows(model,
                                                                tmp_path):
    """DIE PRUEFUNG, DERENTWEGEN "wie ausgeliefert" null IST.

    Ein Zuruecksetzen, das die gerade sichtbare Liste in die Datei
    schreibt, ist am selben Tag nicht von einem richtigen zu
    unterscheiden - dieselben Namen, dieselbe Reihenfolge. Der
    Unterschied zeigt sich beim naechsten Modul, das ZepOS ausliefert:
    wer einmal zurueckgesetzt hat, saehe es nie.
    """
    import settings as settings_file

    path = tmp_path / "user-settings.json"
    draft = model.Draft(document={
        "schema_version": 1,
        "bar": {"modules_right": ["tray", "network"],
                "modules_left": ["custom/date"]},
    })

    draft.reset_bar(settings_file.BAR_RIGHT)
    assert draft.dirty()

    section = draft.sections()["bar"]
    assert section["modules_right"] is None, (
        "das Zuruecksetzen hat die sichtbare Liste eingefroren")
    # Die anderen Haelften stehen vollstaendig darin: merge() ersetzt
    # den Abschnitt, also waere ein Abschnitt mit einer Haelfte das
    # Loeschen der zwei anderen.
    assert section["modules_left"] == ["custom/date"]
    assert section["dock_pins"] is None

    model.save(draft, path)
    written = json.loads(path.read_text(encoding="utf-8"))["bar"]
    assert written["modules_right"] is None, written
    assert written["modules_left"] == ["custom/date"], written

    # Und danach steht wieder die Auslieferung da, ohne dass die Datei
    # sie kennt.
    after = model.Draft(document=json.loads(path.read_text(encoding="utf-8")))
    assert after.current_bar(settings_file.BAR_RIGHT) is None
    assert settings_file.bar_order(
        after.current_bar(settings_file.BAR_RIGHT),
        ["network", "battery", "tray"],
        ["network", "battery", "tray"]) == (["network", "battery", "tray"], [])


def test_a_reordered_side_is_kept_and_the_untouched_ones_are_not_frozen(model):
    """Was die Seite schreibt, wenn nur eine Haelfte angefasst wurde.

    Die anderen zwei gehen als null hinein und nicht als ihre gerade
    sichtbare Reihenfolge. Sonst haette jemand, der einmal das Dock
    umsortiert, damit auch seine Leiste eingefroren - ohne es zu
    bestellen und ohne es zu merken.
    """
    import settings as settings_file

    draft = model.Draft(document={"schema_version": 1})
    assert not draft.dirty()

    draft.set_bar(settings_file.BAR_PINS, ["firefox", "nautilus"])
    assert draft.dirty()

    section = draft.sections()["bar"]
    # "dock_baseline" geht seit dem 20.08.2026 mit hinaus, sobald die
    # Anheftungen angefasst werden: es ist die Auslieferung, gegen die
    # diese Reihenfolge gesetzt wurde, und ohne sie kann der Erzeuger
    # spaeter nicht unterscheiden, ob ein Name fehlt, weil der Nutzer ihn
    # abgenommen hat, oder weil ZepOS ihn erst spaeter dazuliefert.
    #
    # Hier null, weil dieser Lauf keinen Abdruck hat - "unbekannt" und
    # nicht "leer". Der Fall mit einer bekannten Auslieferung steht in
    # test_the_baseline_goes_out_with_the_pins().
    assert section == {"modules_left": None, "modules_right": None,
                       "dock_pins": ["firefox", "nautilus"],
                       "dock_baseline": None}

    # Und der Entwurf haelt eine KOPIE: die Seite baut ihre Zeilen aus
    # derselben Liste wieder auf, und ein Entwurf, der auf ihr
    # Arbeitsstueck zeigt, aenderte sich beim naechsten Anfassen mit.
    order = ["firefox"]
    draft.set_bar(settings_file.BAR_PINS, order)
    order.append("nautilus")
    assert draft.current_bar(settings_file.BAR_PINS) == ["firefox"]


def test_the_baseline_goes_out_with_the_pins(model, tmp_path):
    """Die Vorgabe von damals wird MIT den Anheftungen geschrieben.

    DER FALL, DEN DIESE ZEILE VERHINDERT
        Der Nutzer nimmt ein Symbol ab. Ohne diesen Schluessel steht in
        der Datei danach nur noch seine gekuerzte Liste, und die
        beantwortet zwei verschiedene Fragen mit derselben Auslassung:
        "hier fehlt etwas, weil ich es weggenommen habe" und "hier fehlt
        etwas, weil es das damals noch nicht gab". Der Erzeuger muss
        beim naechsten Lauf zwischen beidem entscheiden - und ohne die
        Vorgabe von damals kann er nur die erste annehmen. Damit
        erscheint keine spaeter ausgelieferte Anwendung je wieder.

    Und zurueckgesetzt geht sie MIT auf null: "wie ausgeliefert" braucht
    keine Vorgabe von damals, und eine stehengebliebene waere die
    eingefrorene Liste durch die Hintertuer.
    """
    import settings as settings_file

    root = tmp_path / "share-zepos"
    root.mkdir(parents=True, exist_ok=True)
    (root / settings_file.SHIPPED_BAR).write_text(json.dumps({
        "modules_left": [], "modules_right": [], "modules_available": [],
        "dock_pins": [{"name": "firefox", "desktop": "firefox.desktop",
                       "label": ""},
                      {"name": "nautilus", "desktop": "nautilus.desktop",
                       "label": ""}]}), encoding="utf-8")

    draft = model.Draft(document={"schema_version": 1})
    draft.set_bar(settings_file.BAR_PINS, ["nautilus"])

    section = draft.sections()["bar"]
    assert section[settings_file.BAR_PINS] == ["nautilus"]
    assert section[settings_file.BAR_BASELINE] == ["firefox", "nautilus"], (
        "die Auslieferung von damals fehlt neben der Wahl - dann ist "
        "nicht mehr abzulesen, dass firefox ABGEWAEHLT wurde")

    draft.reset_bar(settings_file.BAR_PINS)
    zurueck = draft.sections()["bar"]
    assert zurueck[settings_file.BAR_PINS] is None
    assert zurueck[settings_file.BAR_BASELINE] is None


def test_landing_back_on_the_shipped_order_stores_null_again(model):
    """Die zweite Stelle, an der eine eingefrorene Liste entstuende.

    "Zuruecksetzen" ist die eine; die andere ist das Ausprobieren ohne
    Ergebnis - ein Modul heruntergenommen und wieder aufgestellt. Der
    Nutzer steht dann genau da, wo er angefangen hat, und ein Fenster,
    das ihm dafuer die ganze Liste in die Datei schreibt, hat ihm die
    Auslieferung eingefroren, ohne dass er es bestellt hat.
    """
    shipped = ["network", "battery", "tray"]

    assert model.bar_stored(list(shipped), shipped) is None
    assert model.bar_stored(["tray", "network", "battery"], shipped) == [
        "tray", "network", "battery"]
    assert model.bar_stored(["network", "tray"], shipped) == [
        "network", "tray"]
    # Ohne Abdruck wird nichts verglichen: dann ist "wie ausgeliefert"
    # eine Aussage, die diese Maschine gar nicht treffen kann.
    assert model.bar_stored(list(shipped), None) == shipped


def test_an_entry_the_dock_refuses_has_a_reason_and_it_is_the_docks(model):
    """Die zwei Bedingungen aus resolvePins() in ags-dock.template,
    hier als Entscheidung, die ohne Anzeige messbar ist.

    Sie sind der Grund, aus dem es diese ganze Aufgabe gibt: das Zahnrad
    im Fuss war der Eintrag von xdg-desktop-portal-gnome, NoDisplay=true,
    ein D-Bus-Dienst ohne Fenster. Eine Einstellungsseite, die so etwas
    zum Anheften anbietet, baut denselben toten Knopf noch einmal.

    Die ANTWORTEN kommen aus GIO und damit aus bar.py - model.py darf
    kein `gi` importieren. Was hier steht, ist die Regel: erst gibt es
    ueberhaupt einen Eintrag, dann sagt der Eintrag, ob er eine
    Anwendung ist.
    """
    assert model.dock_reason(True, False) == "", (
        "eine gewoehnliche Anwendung braucht keinen Grund")
    assert model.dock_reason(True, True) == model.DOCK_SERVICE
    assert model.dock_reason(False, False) == model.DOCK_NO_ENTRY
    # Ein Eintrag, den es nicht gibt, kann kein Dienst sein: der erste
    # Grund gewinnt, so wie im Dock die erste Bedingung.
    assert model.dock_reason(False, True) == model.DOCK_NO_ENTRY

    assert "NoDisplay" in model.DOCK_SERVICE, (
        "der Grund nennt die Markierung nicht, an der er haengt - dann "
        "kann niemand nachsehen, ob er stimmt")

    # Und die Regel steht wirklich im Dock und nicht nur hier: faellt
    # sie dort weg, heftet der Fuss den Dienst wieder an, waehrend diese
    # Seite ihn weiterhin ausschliesst.
    dock = (SRC / "templates" / "ags-dock.template").read_text(
        encoding="utf-8")
    assert "info.get_nodisplay()" in dock, (
        "das Dock prueft NoDisplay nicht mehr; dann ist die Regel hier "
        "eine Behauptung ueber ein Programm, das etwas anderes tut")


def test_the_page_offers_exactly_the_halves_the_settings_have(model):
    """Eine Haelfte ohne Gruppe waere unerreichbar, eine Gruppe ohne
    Haelfte ein Bedienelement, hinter dem nichts passiert."""
    import settings as settings_file

    keys = [key for key, _title, _description in model.BAR_SIDES]
    assert keys == list(settings_file.BAR_KEYS)
    for _key, title, description in model.BAR_SIDES:
        assert title.strip() and description.strip()


# --------------------------------------------------------------------
# Was nach dem Speichern passiert
# --------------------------------------------------------------------

def test_the_marker_is_the_one_the_session_script_reads(model):
    """Der Pfad steht zweimal da - einmal in src/paths.py und einmal in
    src/bin/zepos-session, das kein Python importieren kann. Diese
    Pruefung ist die Verbindung, die der Import nicht sein kann.

    Ohne sie waere "wirksam beim naechsten Anmelden" eine Behauptung:
    die Anwendung legte eine Datei ab, die Anmeldung sieht an einer
    anderen Stelle nach, und niemand bekaeme es gesagt.
    """
    import paths

    session = (SRC / "bin" / "zepos-session").read_text(encoding="utf-8")
    lines = [line for line in session.splitlines()
             if line.startswith("SETTINGS_MARKER=")]

    assert lines == [
        'SETTINGS_MARKER="${XDG_STATE_HOME:-$HOME/.local/state}'
        '/zepos/regenerate-required"'], (
        "zepos-session nennt die Marke anders als src/paths.py:\n"
        + "\n".join(lines))
    assert paths.SESSION_REGENERATE_MARKER == "regenerate-required"
    assert model.marker_path().name == paths.SESSION_REGENERATE_MARKER

    # Und die Anmeldung muss sie AUCH LESEN, nicht nur benennen.
    assert '-e "$SETTINGS_MARKER"' in session, (
        "zepos-session sieht die Marke nicht an")
    assert 'rm -f "$SETTINGS_MARKER"' in session, (
        "zepos-session raeumt die Marke nicht weg - jede weitere "
        "Anmeldung erzeugte dann wieder neu")


def test_the_generator_is_the_command_the_package_installs(model):
    """`zepos-generate` und nicht generate_config.sh unmittelbar: der
    Befehl findet seine Module selbst, und ein Pfad in eine Installation
    waere ein Pfad, den diese Anwendung raten muesste."""
    assert model.GENERATE_COMMAND == ("zepos-generate", "--all")


def test_a_failed_generator_keeps_the_marker(model, tmp_path):
    """Ein Lauf, der nichts erzeugt hat, darf die Vormerkung nicht
    streichen. Sonst waere die Aenderung gespeichert, nicht angewendet
    und nicht mehr vorgemerkt - also verloren, ohne dass irgendwo etwas
    fehlt."""
    marker = tmp_path / "marke"
    model.request_regeneration_at_login(marker)
    assert marker.exists()

    def failing(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, "", "")

    model.regenerate(runner=failing, marker=marker)
    assert marker.exists()

    def working(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, "", "")

    model.regenerate(runner=working, marker=marker)
    assert not marker.exists()


def test_the_cost_of_a_generator_run_is_named_and_measured(model):
    """Was im Bestaetigungsdialog steht, muss das sein, was wirklich
    passiert. GEMESSEN in src/generate_config.sh: `ags quit`, warten,
    `pkill -9 -f "gjs.*ags"`, neu starten."""
    generator = (SRC / "generate_config.sh").read_text(encoding="utf-8")
    code = "\n".join(line for line in generator.splitlines()
                     if not line.lstrip().startswith("#"))

    assert "ags quit" in code and "pkill" in code, (
        "der Generator beendet AGS nicht mehr - dann stimmt der Satz im "
        "Dialog nicht mehr")
    assert "stopped and restarted" in model.GENERATE_COST
    assert "Terminals" in model.GENERATE_COST


# --------------------------------------------------------------------
# Die Aktualisierung
# --------------------------------------------------------------------

def test_an_update_value_is_written_where_the_service_reads_it(
        model, tmp_path):
    """Nicht in user-settings.json: der Dienst laeuft als root, bevor
    sich jemand angemeldet hat, und faende dort nichts."""
    import update

    outcome = model.set_update_value(
        model.UPDATE_NOTIFY, update.NOTIFY_NEVER,
        runner=lambda argv, **kw: subprocess.CompletedProcess(argv, 0, "", ""))

    assert outcome.written, outcome.message
    stored = json.loads(update.config_path().read_text(encoding="utf-8"))
    assert stored["notify"] == update.NOTIFY_NEVER
    assert not (tmp_path / "zepos" / "user-settings.json").exists()


def test_an_update_value_changes_the_timer_dropin(model, tmp_path):
    """Die erzeugte Datei dieser Seite ist die systemd-Ergaenzung."""
    import update

    model.set_update_value(
        "schedule.interval", "weekly",
        runner=lambda argv, **kw: subprocess.CompletedProcess(argv, 0, "", ""))

    dropin = update.dropin_path().read_text(encoding="utf-8")
    assert "OnCalendar=weekly" in dropin


def test_a_value_the_service_would_refuse_is_refused_here(model):
    """update.validate() prueft, was in eine Unit oder an pacman geht.
    Eine Oberflaeche, die daran vorbeischreibt, erzeugt einen Zeitgeber,
    den systemd nicht laedt."""
    outcome = model.set_update_value(
        model.UPDATE_SCOPE, "alles-und-jedes",
        runner=lambda argv, **kw: subprocess.CompletedProcess(argv, 0, "", ""))

    assert not outcome.written
    assert "scope" in outcome.message


def test_without_rights_the_command_is_offered_instead_of_a_silent_failure(
        model, monkeypatch):
    """/etc/zepos gehoert root. Eine Oberflaeche, die das entdeckt und
    schweigt, ist schlimmer als eine, die es sagt: der Nutzer hat einen
    Schalter umgelegt und glaubt, die Maschine folge ihm jetzt."""
    monkeypatch.setattr(model, "update_writable", lambda: False)
    monkeypatch.setattr(model, "elevator", list)

    outcome = model.set_update_value(model.UPDATE_ENABLED, False)

    assert not outcome.written
    assert "zepos-settings set update.enabled false" in outcome.message
    assert outcome.command == (
        "zepos-settings", "set", "update.enabled", "false")


def test_with_pkexec_the_same_command_is_run_with_rights(model, monkeypatch):
    """pkexec und nicht sudo: der Schreibtisch startet einen
    Polkit-Agenten, und der fragt in einem Fenster - sudo haette hier
    kein Terminal, in dem es fragen koennte."""
    monkeypatch.setattr(model, "update_writable", lambda: False)
    monkeypatch.setattr(model, "elevator", lambda: ["/usr/bin/pkexec"])
    seen = []

    def runner(argv, **kwargs):
        seen.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    outcome = model.set_update_value(model.UPDATE_ENABLED, False,
                                     runner=runner)

    assert outcome.written, outcome.message
    assert seen == [["/usr/bin/pkexec", "zepos-settings", "set",
                     "update.enabled", "false"]]


# --------------------------------------------------------------------
# Das Thema - die zweite Einstellung, die der Maschine gehoert
# --------------------------------------------------------------------

def test_the_application_writes_the_machine_theme(model, tmp_path):
    """Die Auswahl kommt in /etc/zepos/theme an, wenn sie darf.

    Ohne diese Zeile waere der Themenwaehler das, was dieser Baum schon
    dreimal geloescht hat: eine Auswahl, die etwas bestaetigt und nichts
    bewegt.
    """
    outcome = model.set_theme("tageslicht")

    assert outcome.written, outcome.message
    assert (tmp_path / "etc-zepos" / "theme").read_text().strip() == \
        "tageslicht"
    assert model.current_theme() == "tageslicht"


def test_a_theme_that_does_not_exist_is_refused(model):
    """Und zwar bevor geschrieben wird - der Generator faellt sonst
    ueber den Namen, und der Weg zurueck fuehrt durch diese
    Anwendung."""
    outcome = model.set_theme("gibtsnicht")

    assert not outcome.written
    assert "gibtsnicht" in outcome.message


def test_without_rights_the_theme_command_is_offered(model, monkeypatch):
    """Dieselbe Vorrichtung wie bei der Aktualisierung, und derselbe
    Grund: /etc gehoert root, und eine Oberflaeche, die das entdeckt
    und schweigt, laesst den Nutzer glauben, die Maschine folge ihm."""
    monkeypatch.setattr(model, "theme_writable", lambda: False)
    monkeypatch.setattr(model, "elevator", list)

    outcome = model.set_theme("tageslicht")

    assert not outcome.written
    assert "zepos-settings set theme tageslicht" in outcome.message


def test_with_pkexec_the_theme_is_set_with_rights(model, monkeypatch):
    monkeypatch.setattr(model, "theme_writable", lambda: False)
    monkeypatch.setattr(model, "elevator", lambda: ["/usr/bin/pkexec"])
    seen = []

    def runner(argv, **kwargs):
        seen.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    outcome = model.set_theme("tageslicht", runner=runner)

    assert outcome.written, outcome.message
    assert seen == [["/usr/bin/pkexec", "zepos-settings", "set", "theme",
                     "tageslicht"]]


def test_the_shipped_theme_is_offered_first(model):
    """Die Vorgabe ist der Ort, an den man zurueckwill, und den sucht
    man oben."""
    names = model.theme_names()
    assert names[0] == "zeptronit"
    assert set(names) == set(model.theme_names())
    assert len(names) >= 2


def test_the_application_says_when_a_theme_change_arrives(model):
    """Ein Versprechen, das nicht haelt, ist schlimmer als keins.

    Die drei Zeitpunkte sind gemessen (src/theme.py, model.THEME_TIMING),
    und die Oberflaeche muss alle drei nennen - sonst heisst "sofort
    umschaltbar" fuer den Nutzer etwas anderes als fuer die Maschine.
    """
    timing = model.THEME_TIMING
    assert "login screen" in timing and "immediately" in timing
    assert "generation run" in timing
    assert "hyprctl reload" in timing and "terminals" in timing


def test_the_offered_choices_are_ones_the_service_accepts(model):
    """Ein Wort in einer Auswahlliste, das update.validate() ablehnt,
    waere ein Eintrag, der beim Anklicken eine Fehlermeldung erzeugt."""
    import update

    assert set(model.UPDATE_SCOPE_LABELS) == set(update.SCOPES)
    assert set(model.UPDATE_NOTIFY_LABELS) == set(update.NOTIFY_MODES)
    assert set(model.UPDATE_INTERVAL_LABELS) <= set(update.CALENDAR_WORDS)


def test_the_four_offered_keys_exist_in_the_machine_configuration(model):
    """Ein gepunkteter Name, den update.set_value() nicht kennt, wird
    abgelehnt - und der Schalter taete dann nichts."""
    import update

    known = set(update.known_keys())
    for key in (model.UPDATE_ENABLED, model.UPDATE_SCOPE,
                model.UPDATE_NOTIFY, model.UPDATE_INTERVAL):
        assert key in known, f"update.{key} gibt es nicht"


# --------------------------------------------------------------------
# Auffindbar sein
# --------------------------------------------------------------------

def _desktop_groups() -> dict[str, dict[str, str]]:
    """Die Datei nach ihren Gruppen getrennt.

    Getrennt und nicht als eine Zuordnung, seit die Datei am 12.08.2026
    eine Aktion je Seite traegt: ein flacher Leser haette danach das
    letzte `Exec=` der Datei fuer das der Anwendung gehalten - also
    `--page aktualisierung` fuer den Eintrag selbst. Genau das hat diese
    Suite an dem Tag gemeldet, und es waere im Starter eine Anwendung
    gewesen, die immer auf der falschen Seite aufgeht.
    """
    text = (SETTINGS_ROOT / "zepos-settings.desktop").read_text(
        encoding="utf-8")
    groups: dict[str, dict[str, str]] = {}
    current: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = groups.setdefault(line[1:-1], {})
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            current[key] = value
    return groups


def _desktop_entry() -> dict[str, str]:
    return _desktop_groups()["Desktop Entry"]


def test_the_application_has_a_desktop_entry_the_launcher_will_show():
    """Ein Programm unter /usr/bin, das in keiner .desktop-Datei steht,
    gibt es fuer den Nutzer nicht: `zepos-menu --show drun` liest
    g_app_info_get_all(), und das liest /usr/share/applications.

    NoDisplay darf nicht darin stehen - zepos-menu filtert genau darauf,
    und ein Eintrag mit NoDisplay=true waere eine Datei, die alles
    richtig macht und trotzdem unsichtbar bleibt.
    """
    entry = _desktop_entry()

    assert entry["Type"] == "Application"
    assert entry["Exec"] == "/usr/bin/zepos-settings-gui"
    assert entry["TryExec"] == entry["Exec"]
    assert entry.get("NoDisplay", "false") != "true"
    assert entry["Terminal"] == "false"
    assert entry["Icon"] and "/" not in entry["Icon"], (
        "das Symbol muss ein Name aus dem Thema sein, keine Datei")
    assert "Settings" in entry["Categories"]

    # DIE SUCHWOERTER, IN BEIDEN SPRACHEN - nachgezogen am 02.09.2026.
    #
    # Hier stand `"einstellungen" in entry["Keywords"]`, und der Satz war
    # richtig, solange Deutsch die Ausgangssprache dieser Datei war. Ist
    # es nicht mehr: `Keywords=` traegt seither die englischen
    # Suchwoerter und `Keywords[de]=` die deutschen (die Begruendung
    # steht in der Datei selbst).
    #
    # ERWEITERT und nicht bloss verschoben. Die Zusage war "man findet
    # die Anwendung unter einem deutschen Suchwort"; sie am neuen
    # Schluessel zu wiederholen haette das Problem nur verschoben, denn
    # dann faende sie der englische Nutzer nicht. Geprueft wird deshalb
    # BEIDES - und ein fehlender Schluessel faellt mit auf, weil
    # entry[...] dann wirft.
    assert "einstellungen" in entry["Keywords[de]"].lower(), (
        "kein deutsches Suchwort - wer 'Einstellungen' tippt, findet "
        "diese Anwendung nicht")
    assert "settings" in entry["Keywords"].lower(), (
        "kein englisches Suchwort im unbezeichneten Schluessel - wer "
        "'settings' tippt, findet diese Anwendung nicht")


def test_every_page_of_the_settings_is_findable(model):
    """Die Zusicherung, die den FEHLER faengt und nicht das Symptom.

    GEMELDET am 12.08.2026: "ich finde den display manager wie nwg
    display nicht in der app suche". Das Symptom war eine Seite, das
    Symptom haette sich mit einem Schluesselwort erschlagen lassen. Der
    FEHLER ist allgemeiner: dieses Fenster hat sechs Seiten, und ein
    Nutzer kann nur die Anwendung suchen.

    Gefragt wird deshalb ueber ALLE Seiten und in beide Richtungen -
    jede Seite braucht eine Aktion, und jede Aktion muss eine Seite
    nennen, die es gibt. Eine siebte Seite ohne Aktion faellt hier um,
    bevor jemand sie vermisst.

    Und die Exec-Zeile wird gegen den Schalter gehalten, den main.py
    wirklich annimmt: eine Aktion mit einem Namen, den das Programm
    ablehnt, waere eine Zeile im Starter, die mit Rueckgabewert 2 endet
    und kein Fenster oeffnet - genau das Bedienelement, hinter dem
    nichts passiert.
    """
    groups = _desktop_groups()
    entry = groups["Desktop Entry"]

    listed = [name for name in entry["Actions"].split(";") if name]
    assert listed == list(model.PAGE_NAMES), (
        "die Aktionen der .desktop-Datei sind nicht die Seiten des "
        f"Fensters.\n  Datei:  {listed}\n  PAGES:  {list(model.PAGE_NAMES)}")

    for name, title, icon in model.PAGES:
        action = groups.get(f"Desktop Action {name}")
        assert action, f"die Seite {name} hat keine Aktion"

        # ZURUECK AUF `Name`, seit dem 02.09.2026 (Aufgabe 85).
        #
        # Hier stand zwei Stunden lang `Name[de]`, und der Grund dafuer
        # war im Docstring benannt: `Name=` war englisch geworden,
        # waehrend model.PAGES noch deutsch war - das Fenster rief kein
        # gettext. Der deutsche Schluessel war der einzige Anker, gegen
        # den die Zusage "die Aktion heisst so wie ihr Reiter" noch
        # wahr war.
        #
        # Dieser Grund ist weg. model.PAGES traegt jetzt englische
        # msgids, also gehoert der Vergleich wieder an den
        # unbezeichneten Schluessel - beide sind die Ausgangssprache,
        # und beide kommen aus derselben Umstellung.
        #
        # Der DEUTSCHE wird MITgeprueft, aus demselben Grund, aus dem
        # vorher der englische mitgeprueft wurde: ohne ihn steht im
        # Starter eines deutschen Nutzers eine Zeile, die niemand
        # bemerkt, wenn sie fehlt.
        assert action["Name"] == title, (
            f"die Aktion {name} heisst anders als ihre Seite: "
            f"{action['Name']!r} gegen {title!r}")
        assert action.get("Name[de]"), (
            f"die Aktion {name} hat keinen deutschen Namen - im Starter "
            "eines deutschen Nutzers stuende sie dann englisch da")
        assert action["Icon"] == icon, (
            f"die Aktion {name} traegt ein anderes Symbol als ihre Seite")
        assert action["Exec"] == (
            f"{entry['Exec']} {model.PAGE_OPTION} {name}"), (
            f"die Aktion {name} startet etwas anderes: {action['Exec']!r}")

    # Keine Aktion ohne Seite. Ein Rest, den jemand nach dem Loeschen
    # einer Seite stehenlaesst, oeffnet nichts.
    extra = [group[len("Desktop Action "):] for group in groups
             if group.startswith("Desktop Action ")
             and group[len("Desktop Action "):] not in model.PAGE_NAMES]
    assert extra == [], f"Aktionen ohne Seite: {extra}"


def test_the_program_accepts_exactly_the_pages_its_entry_names(model):
    """Die andere Haelfte: was `--page` wirklich annimmt.

    Ohne diese Zusicherung sagte die vorige nur, dass zwei Textdateien
    zueinander passen. Gemessen wird hier der Leser selbst - dieselbe
    Tabelle, gegen die main.py prueft -, damit die Aktion nicht nur
    richtig geschrieben ist, sondern auch ankommt.
    """
    assert model.PAGE_OPTION.startswith("--"), model.PAGE_OPTION
    assert len(set(model.PAGE_NAMES)) == len(model.PAGE_NAMES), (
        "zwei Seiten tragen denselben Namen; der Umschalter zeigt dann "
        "eine von beiden nie")
    for name in model.PAGE_NAMES:
        assert name and name.isascii() and " " not in name, (
            f"{name!r} laesst sich nicht als Aktionsname schreiben - die "
            "Spezifikation erlaubt dort keine Leerzeichen")

    command = SETTINGS_ROOT / "bin" / "zepos-settings-gui"
    assert command.is_file()

    # AUSGEFUEHRT und nicht durchsucht. Eine erste Fassung dieser
    # Zusicherung sah nur nach, ob "model.PAGE_NAMES" im Quelltext von
    # main.py steht - und eine Mutation, die JEDE Seite ablehnte, blieb
    # gruen, weil derselbe Name auch in der Fehlermeldung darunter
    # vorkommt. GEMESSEN am 12.08.2026 in der Mutationspruefung.
    from zepos_settings_gui.main import page_of

    for name in model.PAGE_NAMES:
        assert page_of([model.PAGE_OPTION, name]) == name, (
            f"die Aktion fuer {name} wird abgelehnt - im Starter waere "
            "das eine Zeile, die kein Fenster oeffnet")

    assert page_of([]) is None, (
        "ohne Schalter darf die Anwendung nicht auf einer Seite bestehen")

    for wrong in ([model.PAGE_OPTION, "gibtsnicht"], ["--bogus"],
                  [model.PAGE_OPTION], [model.PAGE_OPTION, "farben", "extra"]):
        with pytest.raises(ValueError):
            page_of(wrong)

    # Und main.py darf gi erst NACH der Pruefung hereinziehen, sonst
    # scheitert eine falsche Eingabe an python-gobject statt an sich
    # selbst.
    source = (SETTINGS_ROOT / "zepos_settings_gui" / "main.py").read_text(
        encoding="utf-8")
    assert "from .app import" not in source.split("settings_file.load")[0]


def test_the_application_says_nothing_about_a_toolkit_it_does_not_use(
        model):
    """Die Entscheidung vom 11.08.2026 gilt fuer jede Oberflaeche, die
    ZepOS selbst baut. Hier wird der Text gemessen; ob wirklich libgtk-4
    geladen wird, misst der kopflose Lauf am /proc/self/maps."""
    app = (SETTINGS_ROOT / "zepos_settings_gui" / "app.py").read_text(
        encoding="utf-8")
    lines = [line for line in app.splitlines()
             if line.startswith("gi.require_version")]

    assert lines == ['gi.require_version("Gtk", "4.0")',
                     'gi.require_version("Adw", "1")'], lines


def _python_code_only(path: Path) -> str:
    """Python-Quelltext ohne Kommentare und ohne Docstrings.

    Wortgleich zum Verfahren in tests/src/test_sizes.py, und aus
    demselben Grund: jede Datei in diesem Baum ERKLAERT, was sie nicht
    tut, und eine Suche der Form `"#0D3D47" in datei` wird von der
    Erklaerung wahr, in der steht, dass keine Farbe hier stehen darf.

    Die UEBRIGEN Zeichenketten bleiben stehen, und das ist der
    Unterschied, der hier zaehlt: das Stylesheet dieser Anwendung IST
    eine dreifach zitierte Zeichenkette, also genau der Ort, an dem ein
    Farbliteral am ehesten landet. Eine Fassung, die alle
    Dreifachzitate wegwirft, kann es nicht mehr finden - NACHGEWIESEN
    mit genau dieser Mutation.
    """
    source = path.read_text(encoding="utf-8")
    prose = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if ast.get_docstring(node, clean=False) is None:
            continue
        literal = node.body[0]
        prose.update(range(literal.lineno, literal.end_lineno + 1))

    lines = []
    for number, line in enumerate(source.splitlines(), start=1):
        if number in prose:
            continue
        lines.append(re.sub(r"(?<![\'\"])#.*$", "", line))
    return "\n".join(lines)


def test_the_application_brings_no_colours_of_its_own():
    """~/.config/gtk-4.0/gtk.css traegt die Marke fuer jede
    GTK4-Anwendung auf diesem System, und diese ist eine.

    Ein Hex-Literal hier waere die 46. Kopie eines Wertes, den
    src/brand.py schon hat - der Fehler, an dem die Vorgabefarben dieses
    Projekts einmal gescheitert sind.

    screens.py steht seit dem 12.08.2026 mit in der Liste, und es ist die
    Datei, bei der die Versuchung am groessten war: sie ZEICHNET, also
    braucht sie eine Farbe fuer die Rechtecke der Bildschirme. Sie holt
    sie mit Gtk.Widget.get_color() aus dem Stilblatt - also aus
    derselben erzeugten gtk.css wie jede Zeile darunter.
    """
    # Aufgezaehlt aus dem Verzeichnis und nicht von Hand. Eine Liste von
    # Hand haette genau die Datei nicht darin, die jemand hinzufuegt -
    # und eine neue Seite ist der wahrscheinlichste Ort fuer die erste
    # eigene Farbe seit langem. GEMESSEN am 12.08.2026: bar.py kam dazu
    # und stand in keiner der beiden Aufzaehlungen dieser Datei.
    modules = sorted((SETTINGS_ROOT / "zepos_settings_gui").glob("*.py"))
    assert len(modules) >= 6, [path.name for path in modules]
    for path in modules:
        body = _python_code_only(path)
        literals = re.findall(r"#[0-9A-Fa-f]{3,8}\b", body)
        assert literals == [], f"Farbliterale in {path.name}: {literals}"


def test_the_one_spacing_this_window_sets_comes_off_the_ladder():
    """src/sizes.py SPACE_LADDER, wie ueberall sonst in diesem Projekt.

    Es ist genau einer - libadwaita setzt alle anderen selbst -, und
    gerade deshalb ist die Pruefung in beide Richtungen noetig: dass er
    von der Leiter kommt, UND dass kein zweiter als nackte Zahl
    danebengeraet. Eine Zahl in einem spacing- oder margin-Argument
    waere dieselbe Zufalls-Uebereinstimmung, wegen der es die Leiter
    ueberhaupt gibt.
    """
    # Ueber ALLE Widget-Dateien, aus demselben Grund wie bei den Farben
    # oben: die naechste Seite ist der wahrscheinlichste Ort fuer die
    # erste nackte Zahl.
    app = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((SETTINGS_ROOT / "zepos_settings_gui").glob("*.py")))
    decisions = (SETTINGS_ROOT / "zepos_settings_gui" / "model.py").read_text(
        encoding="utf-8")

    assert "sizes.SPACE_LADDER" in decisions, (
        "das Fenster setzt seinen Abstand nicht mehr von der Leiter")
    for line in app.splitlines():
        if line.lstrip().startswith("#"):
            continue
        for argument in ("spacing=", "margin_top=", "margin_bottom=",
                         "margin_start=", "margin_end="):
            if argument not in line:
                continue
            value = line.split(argument, 1)[1]
            assert not value[:1].isdigit(), (
                f"ein Abstand steht als Zahl statt auf der Leiter: {line}")


def test_the_spacing_and_the_window_follow_the_users_scale(model):
    """Beide kommen durch sizes, also MIT dem Faktor.

    Bliebe der Abstand stehen, klebten die zwei Knoepfe einer Farbzeile
    bei doppelter Schrift wieder aneinander - er waere dann zwar auf der
    Leiter und trotzdem falsch. Und ein Fenster fester Groesse mit
    doppelt so grosser Schrift zeigt die Haelfte.
    """
    import sizes

    assert model.SPACE_RUNG in sizes.SPACE_LADDER
    assert model.space({"scale": 1.0}) < model.space({"scale": 3.0})
    assert model.window_size({"scale": 1.0}) < model.window_size({"scale": 2.0})
    # Nie kleiner als die Grundgroesse, auch bei einem von Hand
    # eingetragenen Faktor unter 1: das Fenster waere sonst nicht
    # kleiner beschriftet, sondern nur enger.
    assert model.window_size({"scale": 0.5}) == (model.WINDOW_WIDTH,
                                                 model.WINDOW_HEIGHT)


def test_the_command_is_executable():
    """Das Paket installiert sie mit 0755; im Arbeitsbaum muss sie es
    auch sein, sonst faellt es erst auf der Zielmaschine auf."""
    command = SETTINGS_ROOT / "bin" / "zepos-settings-gui"
    assert os.access(command, os.X_OK), f"{command} ist nicht ausfuehrbar"


def _recipe() -> str:
    return (ROOT / "packaging" / "zepos-settings-gui" / "PKGBUILD").read_text(
        encoding="utf-8")


def _recipe_code() -> str:
    """Das Rezept ohne seine Kommentare.

    Jede Datei unter packaging/ erklaert ebenso sorgfaeltig, was sie
    NICHT tut - dieses Rezept begruendet, warum polkit KEINE
    Abhaengigkeit ist -, und eine Pruefung, die diese Erklaerung als Code
    liest, findet einen Fehler im Absatz ueber seine Abwesenheit.
    """
    return "\n".join(line for line in _recipe().splitlines()
                     if not line.lstrip().startswith("#"))


def test_the_recipe_installs_the_entry_the_launcher_reads():
    """Ohne diese Zeile ist die Anwendung installiert und unauffindbar.

    Sie steht hier UND in test_the_application_has_a_desktop_entry...
    oben, und das ist keine Doppelung: dort geht es um den INHALT der
    Datei, hier darum, dass sie ueberhaupt in das Verzeichnis kommt, das
    g_app_info_get_all() liest.
    """
    code = _recipe_code()

    assert "usr/share/applications/zepos-settings.desktop" in code, (
        "das Rezept legt keinen Starter-Eintrag ab")
    assert "usr/bin/zepos-settings-gui" in code


def test_the_recipe_refuses_a_package_without_the_page_it_advertises():
    """Eine Seite steht in model.PAGES, also baut das Fenster sie.

    Faellt ihre Datei aus dem Paket, ist das kein fehlender Reiter,
    sondern ein ImportError beim Start: die ganze Anwendung ginge nicht
    mehr auf. Das Rezept installiert `zepos_settings_gui/*.py`, was das
    heute miterfasst - und genau deshalb steht die Pruefung darin: eine
    Umstellung auf eine Aufzaehlung waere sonst still.

    Und die zweite Zeile ist die, die diese Anwendung von ihrem eigenen
    Erzeuger trennt: src/style_definition.py fragt beim Import `hyprctl`
    nach den Bildschirmen. Ein Einstellungsfenster, das das tut, geht
    ohne laufenden Compositor nicht mehr auf - also genau dort nicht,
    wo man es zum Reparieren braucht.
    """
    code = _recipe_code()

    assert "zepos_settings_gui/bar.py" in code, (
        "das Rezept prueft nicht, ob die Seite \"Leiste\" mitkommt")
    assert "import style_definition" in code, (
        "das Rezept prueft nicht, ob die Anwendung den Erzeuger "
        "importiert")

    for page in ("bar.py", "screens.py"):
        assert (SETTINGS_ROOT / "zepos_settings_gui" / page).is_file()


def test_the_recipe_depends_on_the_package_that_owns_the_settings_file():
    """Der Punkt der ganzen Anwendung, als Paketkante.

    Sie schreibt durch settings.py, sizes.py, brand.py und update.py aus
    /usr/share/zepos. Ohne zepos-config waere jeder dieser Importe ein
    ModuleNotFoundError auf einem Eintrag im Starter - und die
    Alternative, die Module mitzuliefern, waere eine zweite Kopie der
    Einstellungsdatei, also zwei Einstellungen.
    """
    depends = re.search(r"^depends=\((.*?)\)$", _recipe_code(),
                        re.S | re.M)
    assert depends, "das Rezept hat keine depends-Zeile"
    names = re.findall(r"'([^']+)'", depends.group(1))

    for required in ("zepos-config", "python-gobject", "gtk4", "libadwaita"):
        assert required in names, f"{required} fehlt in depends"
    assert "gtk3" not in names


def test_the_desktop_installs_the_settings_application():
    """Ein Paket, das in keiner Abhaengigkeit steht, installiert
    niemand. Der Schreibtisch traegt die Kante, weil er die Antwort auf
    "wie stelle ich die Schriftgroesse um" mitbringen muss."""
    desktop = (ROOT / "packaging" / "zepos-desktop" / "PKGBUILD").read_text(
        encoding="utf-8")
    code = "\n".join(line for line in desktop.splitlines()
                     if not line.lstrip().startswith("#"))

    assert "'zepos-settings-gui'" in code, (
        "zepos-desktop bringt die Einstellungs-Anwendung nicht mit")


def test_the_build_driver_makes_a_tarball_for_it():
    """packaging/build.sh baut jedes Rezept in PACKAGES - aber ein
    Rezept mit einer source=(), fuer die niemand ein Archiv packt,
    scheitert erst im Container."""
    build = (ROOT / "packaging" / "build.sh").read_text(encoding="utf-8")

    assert "selected_holds zepos-settings-gui" in build, (
        "build.sh packt kein Quellarchiv fuer zepos-settings-gui")
    assert 'rsync -a --exclude \'__pycache__\' "$REPO/settings"/' in build, (
        "das Archiv wird nicht aus settings/ gepackt")
