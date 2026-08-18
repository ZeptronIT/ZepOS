# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Zeilen von `--show all`, ohne Fenster und ohne `gi`.

Dieselbe Trennung wie bei tests/menu/test_entries.py: was falsch sein
kann, ohne dass ein Fenster aufgeht, wird hier gemessen - in einer
Umgebung, in der `gi` nicht installiert ist. Das Fenster selbst misst
tests/menu/test_menu_headless.py in einem Kind.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from menu.zepos_menu import index
from menu.zepos_menu.entries import Entry

REPOSITORY = Path(__file__).resolve().parents[2]
SRC = REPOSITORY / "src"


def _paths_module():
    """src/paths.py, so geladen wie der Generator es laedt."""
    spec = importlib.util.spec_from_file_location(
        "zepos_paths_index_probe", SRC / "paths.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_package_root_is_the_one_zepos_config_installs_into():
    """Die eine bewusste Doppelung ueber eine Paketgrenze, abgesichert.

    zepos-menu importiert nichts aus zepos-config - der Kopf von
    index.py sagt, warum -, also steht der Pfad zweimal da. Zweimal
    derselbe Pfad ist in diesem Projekt sonst ein Fehler; hier ist er
    unvermeidbar und deshalb GEMESSEN. Wandert /usr/share/zepos, faellt
    diese Zusicherung, und nicht das Suchfenster eines Nutzers.
    """
    paths = _paths_module()
    assert index.SYSTEM_ROOT == paths.SYSTEM_ROOT
    assert index.SYSTEM_ROOT_ENV == paths.SYSTEM_ROOT_ENV


def test_the_reader_is_where_zepos_config_puts_it():
    """Und die Datei selbst gibt es im Baum."""
    assert (SRC / index.READER).is_file(), (
        f"src/{index.READER} gibt es nicht - `--show all` haette keine "
        f"Aktionen")


def test_the_environment_moves_the_reader(monkeypatch, tmp_path):
    monkeypatch.setenv(index.SYSTEM_ROOT_ENV, str(tmp_path))
    assert index.reader_path() == tmp_path / index.READER
    monkeypatch.delenv(index.SYSTEM_ROOT_ENV)
    assert index.reader_path() == index.SYSTEM_ROOT / index.READER


# --------------------------------------------------------------------
# aus den Gruppen werden Zeilen
# --------------------------------------------------------------------

GROUPS = [
    {"group": "Bildschirm", "bindings": [
        {"chord": "SUPER + S",
         "description": "Bildschirmfoto vom gewaehlten Bereich",
         "run": 'grim -g "$(slurp)" - | satty -f -',
         "source": "hyprland.conf"},
    ]},
    {"group": "Ton", "bindings": [
        {"chord": "SUPER + F12", "description": "Lauter",
         "run": "pactl set-sink-volume @DEFAULT_SINK@ +5%",
         "source": "hyprland.conf"},
    ]},
]


def test_the_group_stands_in_the_text_because_the_search_reads_the_text():
    """"ton" muss die Lautstaerketasten finden.

    Sie heissen "Lauter" und "Leiser". Ohne die Gruppe im Text findet
    sie nur, wer schon weiss, wie sie heissen - und das ist genau der
    Nutzer, der die Suche nicht braucht.
    """
    entries, _ = index.action_entries(GROUPS)
    assert [entry.label for entry in entries] == [
        "Bildschirm: Bildschirmfoto vom gewaehlten Bereich",
        "Ton: Lauter",
    ]


def test_the_key_stands_beside_the_line_and_can_be_searched_for():
    """Die Taste ist die Auskunft, wegen der es diese Betriebsart gibt.

    Sie steht rechts in der Zeile UND im durchsuchten Text: wer sie halb
    im Kopf hat, tippt sie.
    """
    entries, _ = index.action_entries(GROUPS)
    assert [entry.hint for entry in entries] == ["SUPER + S", "SUPER + F12"]
    assert "SUPER + S" in entries[0].searchable
    assert "Bildschirmfoto" in entries[0].searchable


def test_what_a_line_runs_is_not_in_the_line():
    """Dieselbe Form wie apps.desktop_entries(): Zeilen und eine
    Zuordnung daneben.

    Sonst stuende eine Shell-Zeile in dem Feld, das bei --dmenu nach
    stdout geht - und im Zaehlwerk, das haeufig Gewaehltes hochholt.
    """
    entries, commands = index.action_entries(GROUPS)
    for entry in entries:
        assert entry.value.startswith(index.ACTION_PREFIX)
        assert entry.value in commands
    assert commands[entries[0].value] == 'grim -g "$(slurp)" - | satty -f -'


def test_a_second_binding_of_the_same_key_does_not_become_a_second_line():
    """profile-keybinds.conf ueberschreibt eine Zeile aus hyprland.conf.

    Zwei Zeilen mit demselben Text und derselben Taste waeren zwei
    Zeilen, zwischen denen niemand waehlen kann - und der Zaehler
    schriebe beide auf denselben Schluessel.
    """
    doubled = [{"group": "Fenster", "bindings": [
        {"chord": "SUPER + V", "description": "Schweben",
         "run": "hyprctl dispatch togglefloating", "source": "hyprland.conf"},
        {"chord": "SUPER + V", "description": "Etwas anderes",
         "run": "hyprctl dispatch fullscreen",
         "source": "profile-keybinds.conf"},
    ]}]
    entries, commands = index.action_entries(doubled)
    assert len(entries) == 1
    assert commands[entries[0].value] == "hyprctl dispatch togglefloating"


@pytest.mark.parametrize("broken", [
    {"group": "X", "bindings": [{"chord": "", "description": "a", "run": "b"}]},
    {"group": "X", "bindings": [{"chord": "A", "description": "", "run": "b"}]},
    {"group": "X", "bindings": [{"chord": "A", "description": "a", "run": ""}]},
    {"group": "X", "bindings": ["nicht einmal ein Objekt"]},
    {"group": "X"},
])
def test_a_half_entry_becomes_no_entry(broken):
    """Eine Zeile ohne Taste, ohne Text oder ohne Kommando.

    Alle drei sind unbedienbar, und die dritte ist die schlimmste: sie
    sieht aus wie eine Aktion und tut beim Auswaehlen nichts. Genau die
    Fehlerklasse, gegen die diese ganze Aenderung gebaut ist.
    """
    entries, commands = index.action_entries([broken])
    assert entries == []
    assert commands == {}


# --------------------------------------------------------------------
# der Aufruf des Lesers
# --------------------------------------------------------------------

class _Answer:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


def test_the_groups_come_from_the_reader(tmp_path, monkeypatch):
    monkeypatch.setenv(index.SYSTEM_ROOT_ENV, str(tmp_path))
    (tmp_path / index.READER).write_text("")

    seen = {}

    def runner(argv, **kwargs):
        seen["argv"] = argv
        return _Answer(stdout=json.dumps(GROUPS))

    assert index.read_actions(runner) == GROUPS
    assert seen["argv"][1:] == [str(tmp_path / index.READER), "--json"]


@pytest.mark.parametrize("answer", [
    _Answer(returncode=1, stdout=json.dumps(GROUPS)),
    _Answer(stdout="das ist kein JSON"),
    _Answer(stdout=""),
])
def test_a_reader_that_cannot_answer_costs_the_actions_and_not_the_window(
        tmp_path, monkeypatch, answer):
    """Ohne zepos-config gibt es keine erzeugte Konfiguration.

    Das Fenster geht dann mit den Anwendungen auf, also mit genau dem,
    was `--show drun` zeigt. Es haengt an SUPER+SPACE - ein Starter, der
    an einer fehlenden Datei gar nicht mehr aufgeht, ist ein Desktop,
    den man nicht mehr bedienen kann (Spec §7.4).
    """
    monkeypatch.setenv(index.SYSTEM_ROOT_ENV, str(tmp_path))
    (tmp_path / index.READER).write_text("")
    assert index.read_actions(lambda *a, **k: answer) == []


def test_a_reader_that_is_not_there_is_not_even_started(tmp_path, monkeypatch):
    """Kein Unterprozess fuer eine Datei, die es nicht gibt.

    Sonst kostet jedes Oeffnen des Starters auf einer Maschine ohne
    zepos-config einen fehlgeschlagenen exec - und der Nutzer wartet
    darauf.
    """
    monkeypatch.setenv(index.SYSTEM_ROOT_ENV, str(tmp_path))

    def runner(*args, **kwargs):                     # pragma: no cover
        raise AssertionError("der Leser wurde trotzdem gestartet")

    assert index.read_actions(runner) == []


def test_a_reader_that_hangs_is_given_up_on(tmp_path, monkeypatch):
    monkeypatch.setenv(index.SYSTEM_ROOT_ENV, str(tmp_path))
    (tmp_path / index.READER).write_text("")

    def runner(argv, **kwargs):
        assert kwargs["timeout"] == index.TIMEOUT_SECONDS
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    assert index.read_actions(runner) == []


# --------------------------------------------------------------------
# und der Leser selbst, wirklich aufgerufen
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_the_real_reader_answers_this_shape(tmp_path):
    """Der Vertrag zwischen zwei Paketen, an beiden Enden gemessen.

    Die Zusicherungen oben geben sich das Format selbst vor. Wenn
    keybinds.py morgen ein anderes schreibt, sind sie alle noch gruen und
    das Suchfenster ist leer - also wird hier der echte Leser gestartet,
    gegen eine Konfiguration, die dieser Test hinschreibt.
    """
    config = tmp_path / ".config"
    (config / "hypr").mkdir(parents=True)
    (config / "hypr" / "hyprland.conf").write_text(
        "# @Bildschirm: Bildschirmfoto vom gewaehlten Bereich (grim)\n"
        "bind = $mainMod, S, exec, grim -\n"
        "# @Fenster: Fenster schliessen\n"
        "bind = $mainMod SHIFT, X, killactive\n")

    result = subprocess.run(
        [sys.executable, str(SRC / index.READER), "--json"],
        capture_output=True, text=True, timeout=60,
        env={"HOME": str(tmp_path), "XDG_CONFIG_HOME": str(config),
             "PATH": ""})
    assert result.returncode == 0, result.stderr

    entries, commands = index.action_entries(json.loads(result.stdout))
    assert [(entry.label, entry.hint) for entry in entries] == [
        ("Bildschirm: Bildschirmfoto vom gewaehlten Bereich (grim)",
         "SUPER + S"),
        ("Fenster: Fenster schliessen", "SUPER + SHIFT + X"),
    ]
    assert sorted(commands.values()) == [
        "grim -", "hyprctl dispatch killactive"]


def test_an_entry_without_a_hint_stays_what_it_was():
    """Die Anwendungen sind dieselben Zeilen wie vorher.

    `hint` ist neu; eine Zeile ohne sie muss sich verhalten wie am Tag
    davor, sonst haette diese Aenderung den Starter angefasst, um die
    Suche zu bauen.
    """
    application = Entry(label="Firefox", value="firefox.desktop")
    assert application.hint is None
    assert application.searchable == "Firefox"
