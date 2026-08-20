# SPDX-License-Identifier: GPL-3.0-or-later
"""Das Home - die Regeln, nach denen seine Symbole ausgewaehlt werden.

WAS HIER GEPRUEFT WIRD UND WAS NICHT
    Hier steht die Haelfte, die ohne Compositor auskommt: was in der
    Einstellungsdatei stehen darf, was daraus wird, und was der Befehl
    daraus macht, ueber den das AGS-Fenster liest und schreibt.

    Die andere Haelfte - liegt die Flaeche wirklich auf `bottom`,
    scheint die Tapete wirklich hindurch, bleibt ein Klick auf ein
    Fenster wirklich beim Fenster - laesst sich nur an einem laufenden
    Compositor messen und steht in tests/render/test_home.py.

WARUM DIE REGELN UEBERHAUPT IN PYTHON STEHEN UND NICHT IM WIDGET
    Weil das Dock dieselbe Frage stellt ("gehoert dieser Name auf diese
    Maschine?") und beide sie gleich beantworten muessen. src/apps.py
    sagt es in seinem Kopf: "Ein Dock, das einen Namen annimmt, den das
    Fenster verwirft, waere eine Einstellung, die man sieht und nicht
    bekommt." Fuer das Home gilt derselbe Satz, also gilt derselbe Ort.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from src import settings
from tests.src import test_sizes

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"


VORLAGE = SRC / "templates" / "ags-home.template"
STIL = SRC / "styles" / "home-style.template"


def _document(icons=None, baseline=None):
    """Eine Einstellungsdatei mit genau diesem Home-Abschnitt."""
    document = settings.defaults()
    document["home"] = {"icons": icons, "baseline": baseline}
    return document


# --------------------------------------------------------------------
# Die drei Werte, an denen die Bedienbarkeit der Sitzung haengt
# --------------------------------------------------------------------
#
# WARUM SIE HIER STEHEN UND NICHT NUR IN tests/render/test_home.py
#     Der Render-Test misst sie am laufenden Compositor und ist die
#     staerkere Aussage - er braucht aber Hyprland, swaybg und grim und
#     wird auf einer Maschine ohne sie UEBERSPRUNGEN. Ein uebersprungener
#     Test bewacht nichts.
#
#     Diese drei Zeilen laufen im sicheren Lauf, ueberall, und fangen
#     genau die Aenderung, die den Nutzer aussperrt. Sie sind kein
#     Ersatz fuer die Messung, sondern ihr Riegel fuer den Fall, dass
#     sie nicht laufen kann.

def test_the_home_stays_on_the_bottom_layer():
    """Auf jeder hoeheren Ebene schluckt das Home die Klicks der Fenster.

    GEMESSEN am 20.08.2026: GTK4 ruft `wl_surface.set_input_region` nie,
    die Eingaberegion dieser Flaeche ist also der ganze Schirm. Dass
    Fenster anklickbar bleiben, entscheidet allein die
    Stapelreihenfolge.
    """
    code = VORLAGE.read_text(encoding="utf-8")
    assert "layer: Astal.Layer.BOTTOM" in code, (
        "das Home liegt nicht mehr auf Astal.Layer.BOTTOM - auf jeder "
        "hoeheren Ebene bekommt kein Fenster mehr einen Klick")


def test_the_home_never_takes_the_keyboard():
    """`Keymode.EXCLUSIVE` hat im Versuch die Zeigerzustellung an Fenster
    beendet - zweimal gemessen, das Fenster bekam gar nichts mehr.

    Das Rechtsklickmenue braucht die Tastatur nicht: ein Gtk.Popover ist
    eine eigene Wayland-Flaeche mit eigenem Griff (Messung in
    ags-dock.template).
    """
    code = VORLAGE.read_text(encoding="utf-8")
    assert "keymode: Astal.Keymode.NONE" in code, (
        "das Home nimmt nicht mehr Keymode.NONE - mit EXCLUSIVE bekommt "
        "kein Fenster mehr Zeigerereignisse")
    assert "Astal.Keymode.EXCLUSIVE" not in code


def test_the_home_paints_no_background():
    """Ohne diese Regel malt GTK eine bildschirmfuellende graue Platte.

    GEMESSEN am 20.08.2026, Tapete gruen (0,204,0), Bildpunkt in der
    Schirmmitte: ohne die Regel (246,245,244), mit ihr (0,204,0). GTK
    meldet `set_opaque_region` ueber die ganze Flaeche, solange sie einen
    Hintergrund hat - die Tapete waere nicht gedaempft, sondern weg.
    """
    css = STIL.read_text(encoding="utf-8")
    # Am ZEILENANFANG, weil derselbe Name im Dateikopf im Fliesstext
    # steht - ein blosses `split` fiele auf den Kommentar herein und
    # pruefte einen Absatz statt einer Regel. Dieselbe Vorsicht, die
    # test_design.py bei .overlay-outer walten laesst.
    block = re.search(r"^window\.home-window\s*\{(.*?)^\}", css,
                      re.DOTALL | re.MULTILINE)
    assert block, "es gibt keine Regel fuer window.home-window mehr"
    assert "{{STYLE_BG_TRANSPARENT}}" in block.group(1), (
        "die Flaeche des Homes malt wieder einen Hintergrund - damit "
        "verschwindet die Tapete dahinter vollstaendig")


def test_the_home_is_listed_as_a_surface_without_glass(monkeypatch, tmp_path):
    """Und zwar in PLAIN_LAYERS und ausdruecklich NICHT in GLASS_LAYERS.

    Eine Unschaerfe auf diese Flaeche waere eine Unschaerfe auf die
    TAPETE - ueber den ganzen Schirm und bei jedem Bild. Die
    Vollzaehligkeit selbst prueft tests/src/test_glass.py; hier steht,
    dass es diese eine Flaeche ist und keine andere.

    Ueber test_sizes._import_style() und nicht ueber `from src import`:
    style_definition.py importiert seine Geschwister flach (es laeuft als
    Skript aus dem Systemwurzelverzeichnis) und fragt beim Import den
    Compositor nach den Bildschirmen. Der Helfer legt beides zurecht.
    """
    test_sizes._no_compositor(monkeypatch)
    style = test_sizes._import_style(tmp_path, monkeypatch)
    assert "zepos-home" in style.PLAIN_LAYERS
    assert "zepos-home" not in style.GLASS_LAYERS
    assert "zepos-home" not in style.GLASS_PLATES


# --------------------------------------------------------------------
# Die Form: was in der Datei stehen darf
# --------------------------------------------------------------------

def test_a_missing_section_is_unknown_and_not_empty():
    """null heisst "wie ausgeliefert" und nicht "der Nutzer will nichts".

    Die Unterscheidung ist dieselbe wie bei bar.dock_pins und traegt
    dasselbe Gewicht: eine leere Liste wuerde beim naechsten Speichern
    festgeschrieben, und der Nutzer haette ein Home, auf dem nie wieder
    etwas erscheint.
    """
    assert settings.home_icons(settings.defaults()) is None
    assert settings.home_baseline(settings.defaults()) is None
    assert settings.home_icons({}) is None


def test_an_icon_may_leave_its_cell_out():
    """Ein Eintrag ohne Zelle ist gueltig - er heisst "noch nicht abgelegt".

    Genau diese Form haengt home_effective() an, wenn ZepOS eine neue
    Anwendung mitliefert: WO sie liegen soll, kann die Einstellungsdatei
    nicht wissen.
    """
    icons = settings.home_icons(_document([{"name": "firefox"}]))
    assert icons == [{"name": "firefox"}]


def test_a_full_cell_survives_the_read():
    icons = settings.home_icons(
        _document([{"name": "firefox", "col": 3, "row": 2}]))
    assert icons == [{"name": "firefox", "col": 3, "row": 2}]


def test_half_a_cell_is_refused_and_says_which_half_is_missing():
    """`{"col": 3}` ohne "row" sieht aus wie eine Angabe und ist keine.

    Wer sie als "noch nicht abgelegt" durchliesse, legte das Symbol
    woanders hin als der Nutzer geschrieben hat, ohne dass irgendetwas es
    sagt - die stille Sorte Fehler, die niemand meldet.
    """
    with pytest.raises(settings.UnusableSettings) as problem:
        settings.home_icons(_document([{"name": "firefox", "col": 3}]))
    assert "col" in str(problem.value) and "row" in str(problem.value)


def test_a_boolean_is_not_a_column():
    """`true` IST in Python ein int, und ohne diese Zeile waere es Spalte 1.

    Eine Zahl, die niemand geschrieben hat, ist schlimmer als eine
    Ablehnung: das Symbol laege irgendwo, und in der Datei stuende, dass
    der Nutzer es dorthin gelegt habe.
    """
    with pytest.raises(settings.UnusableSettings):
        settings.home_icons(_document([{"name": "x", "col": True, "row": 0}]))


def test_a_negative_cell_is_refused():
    with pytest.raises(settings.UnusableSettings):
        settings.home_icons(_document([{"name": "x", "col": -1, "row": 0}]))


def test_an_icon_without_a_name_is_refused():
    with pytest.raises(settings.UnusableSettings):
        settings.home_icons(_document([{"col": 0, "row": 0}]))


def test_the_complaint_names_the_position_in_the_list():
    """Eine Klage ueber "einen Eintrag" ist in einer Liste von fuenfzehn
    keine Klage, sondern eine Suchaufgabe."""
    with pytest.raises(settings.UnusableSettings) as problem:
        settings.home_icons(_document([{"name": "a"}, {"name": "b"}, 7]))
    assert "[2]" in str(problem.value)


def test_check_reports_both_keys_at_once():
    """Wer beide danebengeschrieben hat, soll beides in einem Durchgang
    erfahren - dieselbe Regel wie bei check_bar()."""
    problems = settings.check_home({"home": {"icons": 7, "baseline": 7}})
    assert len(problems) == 2


# --------------------------------------------------------------------
# Die Rechnung: was die Auslieferung dazutut
# --------------------------------------------------------------------

def test_a_newly_shipped_application_is_appended_without_a_cell():
    """Der ganze Zweck der Grundlinie, und die Zelle bleibt offen.

    dock_effective() haengt einen Namen an eine Reihe an; hier fehlt die
    Antwort auf "wo", und sie wird NICHT erfunden. Eine hier erfundene
    Zelle laege auf einem schmaleren Schirm daneben - und stuende dann
    auch noch in der Datei, als haette der Nutzer sie gewaehlt.
    """
    effective = settings.home_effective(
        [{"name": "firefox", "col": 0, "row": 0}],
        baseline=["firefox"],
        shipped=["firefox", "kitty"])
    assert effective == [{"name": "firefox", "col": 0, "row": 0},
                         {"name": "kitty"}]


def test_something_the_user_took_off_stays_off():
    """Die andere Haelfte derselben Rechnung. "nautilus" steht in der
    Grundlinie und nicht in der Wahl - genau dieses Fehlen IST das
    Nein."""
    effective = settings.home_effective(
        [{"name": "firefox"}],
        baseline=["firefox", "nautilus"],
        shipped=["firefox", "nautilus"])
    assert effective == [{"name": "firefox"}]


def test_an_unknown_baseline_appends_nothing():
    """Eine Installation von vor dem 20.08.2026 hat den Schluessel nicht.

    Aus einem fehlenden Namen liesse sich dann nicht ablesen, ob er
    abgewaehlt oder erst spaeter dazugekommen ist - und die falsche
    Annahme bringt ein Symbol zurueck, das jemand ausdruecklich
    weggenommen hat.
    """
    effective = settings.home_effective(
        [{"name": "firefox"}], baseline=None, shipped=["firefox", "kitty"])
    assert effective == [{"name": "firefox"}]


def test_a_name_that_is_already_there_is_not_appended_twice():
    effective = settings.home_effective(
        [{"name": "kitty", "col": 5, "row": 5}],
        baseline=[], shipped=["kitty"])
    assert effective == [{"name": "kitty", "col": 5, "row": 5}]


# --------------------------------------------------------------------
# Der Plan: was das Fenster wirklich bekommt
# --------------------------------------------------------------------

def test_the_plan_resolves_null_into_the_shipped_selection(monkeypatch):
    """"Wie ausgeliefert" ist fuer etwas, das zeichnen soll, keine Antwort.

    Aufgeloest wird in settings.py und nicht im Widget, damit es dort
    keine zweite Vorstellung davon gibt, was ZepOS mitliefert.
    """
    monkeypatch.setattr(settings, "shipped_pins", lambda root=None: ["a", "b"])
    monkeypatch.setattr(settings, "pinnable", lambda shipped: shipped)
    plan = settings.home_plan(settings.defaults())
    assert plan["icons"] == [{"name": "a"}, {"name": "b"}]
    assert plan["chosen"] is False


def test_the_plan_says_whether_the_user_chose(monkeypatch):
    """Damit ein Aufrufer "wie ausgeliefert" von "der Nutzer will eine
    leere Flaeche" unterscheiden kann, ohne die Datei zweimal zu lesen."""
    monkeypatch.setattr(settings, "shipped_pins", lambda root=None: ["a"])
    monkeypatch.setattr(settings, "pinnable", lambda shipped: shipped)
    assert settings.home_plan(_document(icons=[]))["chosen"] is True


def test_an_uninstalled_program_is_dropped_and_the_reason_is_named(
        monkeypatch):
    """Ein Symbol, das nichts oeffnet, ist der Fehler, den niemand meldet.

    Und der GRUND muss der des Docks sein: ein Modulname ohne Zweig ist
    ein Tippfehler, ein angeheftetes Programm ohne Anwendungseintrag ist
    eine Deinstallation. Derselbe Wortlaut fuer beides schickte den
    Nutzer bei der zweiten in die falsche Datei.
    """
    monkeypatch.setattr(settings, "shipped_pins", lambda root=None: ["a"])
    monkeypatch.setattr(settings, "pinnable", lambda shipped: ["a"])
    plan = settings.home_plan(_document([{"name": "a"}, {"name": "weg"}]))
    assert [entry["name"] for entry in plan["icons"]] == ["a"]
    assert plan["discarded"] == [{"name": "weg", "why": settings.BAR_GONE}]


def test_the_cell_survives_the_check(monkeypatch):
    """Die Namenspruefung laeuft ueber bar_order(), das NAMEN kennt und
    keine Zellen. Ohne das Zurueckbinden unten verlaere jedes Symbol beim
    Lesen seinen Platz - also genau das, was der Nutzer eingestellt hat.
    """
    monkeypatch.setattr(settings, "shipped_pins", lambda root=None: ["a"])
    monkeypatch.setattr(settings, "pinnable", lambda shipped: ["a"])
    plan = settings.home_plan(_document([{"name": "a", "col": 4, "row": 1}]))
    assert plan["icons"] == [{"name": "a", "col": 4, "row": 1}]


def test_a_repeated_name_keeps_its_first_cell(monkeypatch):
    """bar_order() behaelt den ERSTEN Platz und verwirft jeden weiteren.

    Die Zelle muss demselben Eintrag folgen. Naehme sie den letzten,
    benutzte das Home die Zelle eines Eintrags, der gerade als
    "steht mehrfach in der Liste" herausgeflogen ist.
    """
    monkeypatch.setattr(settings, "shipped_pins", lambda root=None: ["a"])
    monkeypatch.setattr(settings, "pinnable", lambda shipped: ["a"])
    plan = settings.home_plan(_document(
        [{"name": "a", "col": 1, "row": 1}, {"name": "a", "col": 9, "row": 9}]))
    assert plan["icons"] == [{"name": "a", "col": 1, "row": 1}]


# --------------------------------------------------------------------
# Das Schreiben: die zwei Schluessel gehen zusammen raus
# --------------------------------------------------------------------

def test_writing_always_carries_a_fresh_baseline(monkeypatch):
    """DIE Zusicherung, an der haengt, ob eine neue Fassung von ZepOS ihre
    Anwendungen zeigen darf.

    Eine Symbolliste ohne frische Grundlinie hiesse: der Nutzer habe
    gegen die Auslieferung von GESTERN entschieden - und alles, was
    seither dazugekommen ist, erschiene noch einmal, auch das, was er
    gerade abgenommen hat.
    """
    monkeypatch.setattr(settings, "shipped_pins", lambda root=None: ["a", "b"])
    section = settings.home_write(settings.defaults(), [{"name": "a"}])
    assert section == {"home": {"icons": [{"name": "a"}],
                                "baseline": ["a", "b"]}}


def test_an_unknown_shipment_writes_null_and_not_an_empty_list(monkeypatch):
    """Leer hiesse "ZepOS lieferte nichts aus", und danach gaelte jede
    ausgelieferte Anwendung als neu."""
    monkeypatch.setattr(settings, "shipped_pins", lambda root=None: None)
    section = settings.home_write(settings.defaults(), [])
    assert section["home"]["baseline"] is None


# --------------------------------------------------------------------
# Der Befehl, ueber den das Fenster liest und schreibt
# --------------------------------------------------------------------

def _run(*arguments, home):
    """settings.py in einem eigenen Wurzelverzeichnis aufrufen.

    Als KINDPROZESS und nicht ueber main(): das AGS-Fenster ruft ihn
    genauso auf, und was hier gemessen wird, ist der Vertrag zwischen
    beiden - Rueckgabewert, Ausgabe, und dass die Ausgabe JSON ist.
    """
    return subprocess.run(
        [sys.executable, str(SRC / "settings.py"), *arguments],
        capture_output=True, text=True,
        env={"PATH": "/usr/bin", "ZEPOS_USER_ROOT": str(home),
             "ZEPOS_SYSTEM_ROOT": str(SRC)})


@pytest.mark.allow_subprocess
@pytest.mark.allow_system_writes
def test_the_command_answers_with_json(tmp_path):
    result = _run("home", home=tmp_path)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert isinstance(plan["icons"], list)


@pytest.mark.allow_subprocess
@pytest.mark.allow_system_writes
def test_add_then_remove_leaves_the_file_readable(tmp_path):
    """Der ganze Weg, den ein Menuepunkt geht - und danach liest ihn
    derselbe Befehl wieder."""
    assert _run("home", "add", "firefox", home=tmp_path).returncode == 0
    plan = json.loads(_run("home", home=tmp_path).stdout)
    assert "firefox" in [entry["name"] for entry in plan["icons"]]

    assert _run("home", "remove", "firefox", home=tmp_path).returncode == 0
    plan = json.loads(_run("home", home=tmp_path).stdout)
    assert "firefox" not in [entry["name"] for entry in plan["icons"]]


@pytest.mark.allow_subprocess
@pytest.mark.allow_system_writes
def test_adding_twice_is_not_an_error(tmp_path):
    """Ein Rueckgabewert ungleich 0 liesse das Menue eine Fehlermeldung
    zeigen, wo gar nichts fehlt."""
    assert _run("home", "add", "firefox", home=tmp_path).returncode == 0
    assert _run("home", "add", "firefox", home=tmp_path).returncode == 0
    plan = json.loads(_run("home", home=tmp_path).stdout)
    names = [entry["name"] for entry in plan["icons"]]
    assert names.count("firefox") == 1


@pytest.mark.allow_subprocess
@pytest.mark.allow_system_writes
def test_set_writes_the_cells(tmp_path):
    layout = json.dumps([{"name": "firefox", "col": 2, "row": 3}])
    assert _run("home", "set", layout, home=tmp_path).returncode == 0
    stored = json.loads((tmp_path / "user-settings.json").read_text())
    assert stored["home"]["icons"] == [{"name": "firefox", "col": 2, "row": 3}]
    assert "baseline" in stored["home"], (
        "die Grundlinie fehlt - siehe home_write(), sie gehoert zu JEDEM "
        "Schreibvorgang")


@pytest.mark.allow_subprocess
@pytest.mark.allow_system_writes
def test_a_bad_layout_blames_the_argument_and_not_the_file(tmp_path):
    """DIE Meldung, die einen Nutzer sonst seine Einstellungen kostet.

    unreadable() sagt "diese Datei ist kaputt, repariere sie oder raeume
    sie weg". Ueber eine Datei, die vollkommen in Ordnung ist, ist das
    keine Diagnose, sondern eine Anleitung zum Datenverlust.
    """
    # Erst eine Datei anlegen, und zwar ueber `set`: `add` schreibt
    # NICHT, wenn der Name ohnehin schon auf dem Home liegt (er steht in
    # der Auslieferung), und dann gaebe es hier gar keine Datei, deren
    # Unversehrtheit man messen koennte.
    assert _run("home", "set", '[{"name": "firefox", "col": 0, "row": 0}]',
                home=tmp_path).returncode == 0
    vorher = (tmp_path / "user-settings.json").read_text()

    result = _run("home", "set", '[{"name": "x", "col": 1}]', home=tmp_path)
    assert result.returncode == 2
    assert "cannot be read" not in result.stderr, (
        "die Klage ueber das ARGUMENT nennt die DATEI als kaputt: "
        + result.stderr)
    assert (tmp_path / "user-settings.json").read_text() == vorher, (
        "eine abgelehnte Belegung hat die Datei trotzdem veraendert")
