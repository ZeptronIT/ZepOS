# SPDX-License-Identifier: GPL-3.0-or-later
"""Das Fenster von zepos-menu, gebaut und bedient.

WAS DAS SCHLIESST
    zepos-menu ersetzt wofi an sechs Stellen, von denen fuenf ihre
    Ausgabe unmittelbar weiterverarbeiten: printer-manager macht daraus
    einen Druckernamen, cliphist-menu reicht sie an `cliphist decode`,
    network-manager-gui liest eine SSID heraus, floating-window-manager
    einen Dateinamen. Ein Fenster, das nur GEBAUT wurde, sagt ueber keine
    dieser Stellen etwas.

    Deshalb wird hier getippt, gefiltert, mit den Pfeilen gewaehlt, mit
    Enter bestaetigt und mit Escape abgebrochen - und danach steht auf
    stdout genau das, was der Aufrufer erwartet, oder es steht nichts da.

DIE ANZEIGE
    tests/gtk4_headless.py, dieselbe wie beim graphischen Installer.

WAS HIER NICHT GEMESSEN WIRD
    Der Weg von einer echten Tastatur bis zum GtkEventControllerKey. GTK4
    hat keine Schnittstelle, um ein Tastenereignis einzuspeisen, und
    broadway nimmt Eingaben nur ueber seinen HTML5-Kanal entgegen. Das
    Kind emittiert deshalb das Signal "key-pressed" am Regler selbst -
    damit ist alles ab dem Regler echt, einschliesslich der Frage, ob
    ueberhaupt etwas daran haengt: ein Fenster ohne verbundenen Rueckruf
    liefert False und faellt hier durch.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from tests.gtk4_headless import (
    broadwayd, gi_interpreter, start_broadwayd, stop_broadwayd,
)

ROOT = Path(__file__).resolve().parents[2]
MENU_ROOT = ROOT / "menu"
SRC = ROOT / "src"
CHILD = Path(__file__).resolve().parent / "menu_headless_child.py"

CHILD_TIMEOUT = 120

# Jeder Test bekommt eine eigene Anzeigenummer. Zwei broadwayd auf
# derselben Nummer teilen sich einen Socketnamen, und der zweite findet
# den Socket des ersten - der Lauf misst dann ein Fenster im falschen
# Prozess. 11 und 12 gehoeren tests/installer/test_gui_headless.py.
_DISPLAYS = iter(range(21, 99))


def _interpreter():
    return gi_interpreter({"Gtk": "4.0", "Gtk4LayerShell": "1.0"})


class Run:
    """Was ein Lauf hinterlassen hat."""

    def __init__(self, returncode: int, stdout: str, stderr: str,
                 trace: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.trace = trace

    @property
    def marks(self) -> list[str]:
        return self.trace.splitlines()

    def mark(self, prefix: str) -> str:
        found = [line for line in self.marks if line.startswith(prefix + ":")]
        assert found, f"keine Marke {prefix} in der Spur:\n{self.report}"
        return found[0].split(":", 1)[1]

    @property
    def report(self) -> str:
        return (f"rueckgabewert: {self.returncode}\n"
                f"stdout: {self.stdout!r}\n"
                f"stderr:\n{self.stderr}\n"
                f"spur:\n{self.trace}")


def run_menu(tmp_path: Path, script: str, argv: list[str], *,
             stdin: str = "", config: str = "", style: str = "",
             extra_env: dict[str, str] | None = None) -> Run:
    interpreter = _interpreter()
    if interpreter is None:
        pytest.skip(
            "kein Interpreter hier kann gi/Gtk4/Gtk4LayerShell laden - "
            "python-gobject, gtk4 und gtk4-layer-shell installieren")
    display_server = broadwayd()
    if display_server is None:
        pytest.skip("gtk4-broadwayd fehlt; es kommt mit dem Paket gtk4")

    executable, extra_path = interpreter
    display = next(_DISPLAYS)

    # exist_ok, weil ein Test zwei Laeufe unter zwei Unterverzeichnissen
    # von tmp_path braucht - und weil die Starter-Tests ihre
    # .desktop-Dateien vorher unter data/ ablegen.
    tmp_path.mkdir(parents=True, exist_ok=True)
    runtime_dir = tmp_path / "run"
    runtime_dir.mkdir(exist_ok=True)
    # GLib lehnt ein weltlesbares XDG_RUNTIME_DIR ab und sagt es auf stderr.
    runtime_dir.chmod(0o700)
    for name in ("tmp", "home", "cache", "config", "data", "data-dirs"):
        (tmp_path / name).mkdir(exist_ok=True)
    empty_path = tmp_path / "no-binaries-here"
    empty_path.mkdir(exist_ok=True)

    menu_config = tmp_path / "config" / "zepos-menu"
    menu_config.mkdir(exist_ok=True)
    if config:
        (menu_config / "config").write_text(config, encoding="utf-8")
    if style:
        (menu_config / "style.css").write_text(style, encoding="utf-8")

    trace_file = tmp_path / "trace.txt"

    environment = {
        "PATH": str(empty_path),
        "HOME": str(tmp_path / "home"),
        "TMPDIR": str(tmp_path / "tmp"),
        "XDG_RUNTIME_DIR": str(runtime_dir),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        # Ein LEERES Verzeichnis als Systemanteil. Ohne das liest
        # Gio.AppInfo.get_all() /usr/share/applications des Entwicklers,
        # und der Starter-Test misst dessen Anwendungen statt der
        # eigenen.
        "XDG_DATA_DIRS": str(tmp_path / "data-dirs"),
        "GDK_BACKEND": "broadway",
        "BROADWAY_DISPLAY": f":{display}",
        "GSETTINGS_BACKEND": "memory",
        "NO_AT_BRIDGE": "1",
        "LC_ALL": "C",
        "PYTHONPATH": os.pathsep.join([str(ROOT), str(MENU_ROOT), *extra_path]),
        "PYTHONUNBUFFERED": "1",
    }
    environment.update(extra_env or {})

    # In DATEIEN und nicht in Roehren, und das ist eine Messung vom
    # 11.08.2026 und keine Bequemlichkeit.
    #
    # Der Starter startet eine Anwendung und beendet sich sofort. Die
    # gestartete Anwendung erbt dabei stdout und stderr des Starters -
    # so macht es jeder Starter, wofi eingeschlossen, und deshalb
    # landen die Meldungen einer aus SUPER+SPACE gestarteten Anwendung
    # im Protokoll des Compositors, wo man sie sucht.
    #
    # Fuer subprocess.run(capture_output=True) heisst das: das Kind ist
    # laengst fertig, aber communicate() wartet weiter auf ein Ende der
    # Ausgabe, das die ENKELIN noch offen haelt. Gemessen an
    # test_the_launcher_lists_what_a_menu_shows_and_starts_it: 120
    # Sekunden bis zur Zeitgrenze, Rueckgabewert des Kindes 0, Marke
    # geschrieben. Eine Datei hat kein solches Ende.
    stdout_file = tmp_path / "stdout.txt"
    stderr_file = tmp_path / "stderr.txt"

    process, _socket = start_broadwayd(display_server, runtime_dir, display)
    try:
        with stdout_file.open("w", encoding="utf-8") as out, \
                stderr_file.open("w", encoding="utf-8") as err:
            completed = subprocess.run(
                [executable, str(CHILD), str(trace_file), script, *argv],
                env=environment, cwd=str(tmp_path), input=stdin,
                stdout=out, stderr=err, text=True, timeout=CHILD_TIMEOUT,
            )
    finally:
        stop_broadwayd(process)

    trace = trace_file.read_text(encoding="utf-8") if trace_file.exists() else ""
    run = Run(completed.returncode,
              stdout_file.read_text(encoding="utf-8"),
              stderr_file.read_text(encoding="utf-8"),
              trace)

    assert run.returncode != 139, (
        "das Kind ist abgestuerzt - das ist, was GTK ohne Anzeige tut, "
        "also hat broadway die Verbindung nicht angenommen:\n" + run.report)
    assert "FAILURE" not in trace, run.report
    # GLib schreibt seine Diagnosen hierhin und nirgendwo sonst. Sie sind
    # keine Ausschmueckung: die kritische Meldung von
    # gtk4_layer_shell_is_supported() auf einer Nicht-Wayland-Anzeige
    # war der Grund, den Anzeigetyp vorher zu pruefen.
    for level in ("-CRITICAL **:", "-WARNING **:", "-ERROR **:"):
        assert level not in run.stderr, (
            f"GLib hat ein {level.strip(' *:-')} gemeldet:\n" + run.report)
    return run


# --------------------------------------------------------------------
# dmenu - der Weg, an dem fuenf Skripte haengen
# --------------------------------------------------------------------

DMENU = ["--dmenu", "--prompt", "Auswahl", "--cache-file", "/dev/null",
         "--sort-order=default"]


@pytest.mark.allow_subprocess
def test_typing_filters_arrows_choose_and_enter_writes_it_to_stdout(tmp_path):
    """Der ganze Vertrag in einem Lauf.

    Vier Zeilen hinein, "er" getippt - was auf zwei davon passt -, einmal
    nach unten, Enter. Auf stdout steht die zweite der beiden und sonst
    nichts.

    Die Eingabereihenfolge bleibt, weil --sort-order=default es sagt:
    "Etage2" steht in der Liste hinter "Buero", obwohl es alphabetisch
    davor kaeme.
    """
    run = run_menu(
        tmp_path, "type:er key:down key:enter", DMENU,
        stdin="Etage2\nBuero\nLabor\nKeller\n")

    assert run.mark("order") == "Etage2|Buero|Labor|Keller"
    assert run.mark("filtered") == "Buero|Keller"
    assert run.marks.count("key:down:handled") == 1, run.report
    assert run.stdout == "Keller\n", run.report
    assert run.returncode == 0, run.report


@pytest.mark.allow_subprocess
def test_escape_writes_nothing_and_says_so_in_the_exit_code(tmp_path):
    """Der Abbruch. Jeder der fuenf Aufrufer prueft `[ -n "$auswahl" ]`,
    also ist eine leere Ausgabe hier die Bedingung dafuer, dass Escape
    keinen Drucker namens "" einrichtet."""
    run = run_menu(tmp_path, "type:Bu key:escape", DMENU,
                   stdin="Buero\nLabor\n")

    assert run.stdout == "", run.report
    assert run.returncode == 1, run.report


@pytest.mark.allow_subprocess
def test_a_typed_name_comes_back_when_the_list_holds_nothing(tmp_path):
    """`printf '' | zepos-menu --dmenu --prompt "Name"`.

    Genau so fragt printer-manager-config.template nach dem Namen eines
    neuen Druckers, und floating-window-manager nach dem eines neuen
    Layouts. Ohne diese Betriebsart haetten beide Vorlagen keinen Weg,
    eine Zeichenkette entgegenzunehmen.

    Die Meldung "Keine Treffer" darf dabei NICHT erscheinen: ueber einem
    leeren Feld waere sie eine Fehlermeldung ueber eine Eingabe, die noch
    niemand gemacht hat.
    """
    run = run_menu(tmp_path, "type:Etage2 key:enter", DMENU, stdin="")

    assert run.mark("items") == "0"
    assert run.mark("message") == "False", run.report
    assert run.stdout == "Etage2\n", run.report
    assert run.returncode == 0, run.report


@pytest.mark.allow_subprocess
def test_a_typed_name_comes_back_when_nothing_in_the_list_matches(tmp_path):
    """Derselbe Weg mit gefuellter Liste: floating-window-manager bietet
    "[Neues Layout]" und die vorhandenen an, und ein Name, den es noch
    nicht gibt, passt auf keinen davon.

    Hier MUSS "Keine Treffer" stehen - es gab etwas zu finden.
    """
    run = run_menu(tmp_path, "type:Werkstatt key:enter", DMENU,
                   stdin="[Neues Layout]\nBuero\nLabor\n")

    assert run.mark("filtered") == ""
    assert run.mark("message") == "True", run.report
    assert run.stdout == "Werkstatt\n", run.report


@pytest.mark.allow_subprocess
def test_a_click_chooses_the_row_it_lands_on(tmp_path):
    """Die Maus. single_click_activate ist an, also ist ein Klick genau
    ein "activate" - dieselbe Strecke, die auch Enter auf einer
    fokussierten Liste nimmt."""
    run = run_menu(tmp_path, "click:2", DMENU, stdin="eins\nzwei\ndrei\n")

    assert run.stdout == "drei\n", run.report


@pytest.mark.allow_subprocess
def test_the_password_prompt_does_not_show_what_is_typed(tmp_path):
    """network-manager-gui-config.template, letzter Rueckfall fuer das
    WLAN-Passwort. Ein Auswahlfenster, das --password entgegennimmt und
    den Text trotzdem zeigt, gibt das Passwort auf einem Bildschirm aus,
    von dem der Nutzer glaubt, es sei verdeckt."""
    run = run_menu(
        tmp_path, "type:geheim key:enter",
        ["--dmenu", "--prompt", "Passwort", "--password",
         "--width", "350", "--height", "120", "--cache-file", "/dev/null"],
        stdin="")

    assert run.mark("visible") == "False", run.report
    assert run.stdout == "geheim\n", run.report


@pytest.mark.allow_subprocess
def test_case_is_ignored_only_when_it_is_asked_to_be(tmp_path):
    """--insensitive, wie network-manager-gui es uebergibt. Ohne den
    Schalter und mit insensitive=false in der Datei bleibt "wlan" ein
    anderer Text als "WLAN"; mit ihm nicht."""
    lines = "WLAN Gast\nEthernet\n"

    strict = run_menu(tmp_path / "strict", "type:wlan key:escape", DMENU,
                      stdin=lines, config="insensitive=false\n")
    assert strict.mark("filtered") == ""

    loose = run_menu(tmp_path / "loose", "type:wlan key:enter",
                     DMENU + ["--insensitive"], stdin=lines,
                     config="insensitive=false\n")
    assert loose.stdout == "WLAN Gast\n", loose.report


@pytest.mark.allow_subprocess
def test_a_key_the_program_does_not_use_is_passed_on(tmp_path):
    """Der Regler haengt in der Fangphase am Fenster und sieht jede
    Taste vor jedem Widget. Einer, der alles verschluckt, liesse kein
    einziges Zeichen ins Eingabefeld - und dann filterte nichts mehr."""
    run = run_menu(tmp_path, "key:f5 key:escape", DMENU, stdin="eins\n")

    assert "key:f5:passed-on" in run.marks, run.report


@pytest.mark.allow_subprocess
def test_the_prompt_and_the_size_come_off_the_command_line(tmp_path):
    """network-manager-gui oeffnet drei verschieden grosse Fenster mit
    drei verschiedenen Texten. Ein Ersatz, der --prompt, --width und
    --height nur entgegennimmt, macht daraus dreimal dasselbe Fenster."""
    run = run_menu(
        tmp_path, "key:escape",
        ["--dmenu", "--prompt", "Netzwerk", "--width", "450",
         "--height", "200", "--cache-file", "/dev/null"],
        stdin="eins\n")

    assert run.mark("placeholder") == "Netzwerk"
    assert run.mark("size") == "450x200", run.report


# --------------------------------------------------------------------
# Die Reihenfolge, und das Zaehlwerk, das sie aendern darf
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_alphabetical_is_a_different_order_than_the_input(tmp_path):
    """Der Beweis, dass --sort-order=default ueberhaupt etwas tut. Ohne
    ihn ist die Vorgabe aus der erzeugten Konfiguration alphabetisch,
    und die WLAN-Liste von network-manager-gui - nach Signalstaerke
    sortiert, mit Ueberschriften dazwischen - waere danach eine andere
    Liste."""
    lines = "Etage2\nBuero\nLabor\n"

    as_given = run_menu(tmp_path / "given", "key:escape", DMENU, stdin=lines)
    assert as_given.mark("order") == "Etage2|Buero|Labor"

    sorted_run = run_menu(
        tmp_path / "sorted", "key:escape",
        ["--dmenu", "--cache-file", "/dev/null", "--sort-order", "alphabetical"],
        stdin=lines)
    assert sorted_run.mark("order") == "Buero|Etage2|Labor"


@pytest.mark.allow_subprocess
def test_what_was_chosen_before_comes_first_the_next_time(tmp_path):
    """--cache-file, und der Grund, aus dem alle fuenf Skripte
    /dev/null uebergeben.

    Erst waehlen, dann noch einmal oeffnen: das Gewaehlte steht oben,
    obwohl die Eingabereihenfolge unveraendert ist. Genau das wollen die
    fuenf Skripte NICHT, weil ihre Reihenfolge etwas bedeutet - und
    genau deshalb muss der Schalter etwas tun.
    """
    cache = tmp_path / "zaehlwerk"
    lines = "Etage2\nBuero\nLabor\n"
    argv = ["--dmenu", "--sort-order=default", "--cache-file", str(cache)]

    first = run_menu(tmp_path / "first", "type:Labor key:enter", argv,
                     stdin=lines)
    assert first.stdout == "Labor\n", first.report
    assert cache.read_text(encoding="utf-8") == "1 Labor\n"

    second = run_menu(tmp_path / "second", "key:escape", argv, stdin=lines)
    assert second.mark("order") == "Labor|Etage2|Buero"


@pytest.mark.allow_subprocess
def test_dev_null_keeps_no_count_at_all(tmp_path):
    """Der Sonderfall, der keiner sein darf. /dev/null liest sich leer
    und nimmt jeden Schreibvorgang an - waere das Zaehlwerk mit
    schreiben-und-umbenennen gebaut, scheiterte hier jeder einzelne
    Aufruf der fuenf Skripte."""
    lines = "Etage2\nBuero\n"

    first = run_menu(tmp_path / "first", "type:Buero key:enter", DMENU,
                     stdin=lines)
    assert first.stdout == "Buero\n", first.report

    second = run_menu(tmp_path / "second", "key:escape", DMENU, stdin=lines)
    assert second.mark("order") == "Etage2|Buero"


# --------------------------------------------------------------------
# Das Stylesheet - der Fehler, den wofi getragen hat
# --------------------------------------------------------------------

@pytest.fixture
def generated_style(tmp_path, monkeypatch) -> str:
    """src/styles/zepos-menu-style.template, durch das Zentrum gedreht.

    Nicht ein Beispiel und nicht die Vorlage selbst: die Vorlage traegt
    {{STYLE_*}}-Platzhalter, und ob GTK4 das ERGEBNIS lesen kann, ist
    genau die Frage, die sich bei wofi niemand gestellt hat.
    """
    monkeypatch.syspath_prepend(str(SRC))
    import template_processor

    processor = template_processor.ConfigProcessor(
        styles=dict(template_processor.STYLE_VARIABLES))
    rendered = tmp_path / "zepos-menu-style.css"
    processor.apply_template(
        SRC / "styles" / "zepos-menu-style.template", rendered)
    text = rendered.read_text(encoding="utf-8")
    assert "{{" not in text, "das Stylesheet hat unaufgeloeste Platzhalter"
    return text


@pytest.mark.allow_subprocess
def test_the_generated_stylesheet_parses_without_a_single_error(
        tmp_path, generated_style):
    """wofis erzeugtes style.css warf 39 Parserfehler, gemessen am
    11.08.2026, und der Starter erschien seit jeher in GTKs
    Standardgrau. GTK verwirft eine Deklaration, die es nicht versteht,
    behaelt den Rest und meldet es nirgendwo hin, wo jemand hinsieht.

    Hier wird DAS ERZEUGTE Stylesheet geladen - nicht ein Beispiel -,
    und jeder Parserfehler landet auf stderr, wo diese Zusicherung ihn
    findet.
    """
    run = run_menu(tmp_path, "key:escape", DMENU, stdin="eins\n",
                   style=generated_style)

    assert "Stylesheet" not in run.stderr, (
        "das erzeugte Stylesheet hat GTK4 nicht durch den Parser "
        "gebracht:\n" + run.report)


@pytest.mark.allow_subprocess
def test_a_stylesheet_gtk_cannot_read_is_reported_and_not_swallowed(tmp_path):
    """Die Gegenprobe zur Zusicherung darueber.

    Ohne sie waere "keine Fehlermeldung" auch dann wahr, wenn das
    Programm gar nicht hinsieht - und das ist exakt der Zustand, in dem
    wofi jahrelang war.
    """
    run = run_menu(tmp_path, "key:escape", DMENU, stdin="eins\n",
                   style="window { background-color: keinefarbe; }\n")

    assert "Stylesheet" in run.stderr, run.report
    assert "keinefarbe" in run.stderr, run.report


# --------------------------------------------------------------------
# Der Starter
# --------------------------------------------------------------------

def _desktop_files(tmp_path: Path, marker: Path, runner: Path) -> None:
    applications = tmp_path / "data" / "applications"
    applications.mkdir(parents=True)
    (applications / "zepos-editor.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Schreibmaschine\n"
        f"Exec={runner} editor\n", encoding="utf-8")
    # Drei Platzhalter der .desktop-Spezifikation, und drei verschiedene
    # Sorten Schaden:
    #
    #   %U  die URLs, die ein Dateimanager mitgibt - ein Starter hat
    #       keine
    #   %c  der uebersetzte Name der Anwendung
    #   %i  --icon und der Symbolname
    #
    # Ein Starter ohne Argumente muss alle drei entfernen. Stehen
    # gelassen startet er das Programm mit einer Datei namens "%U"
    # beziehungsweise - wenn eine Zwischenstelle sie doch noch ersetzt -
    # mit seinem eigenen Namen als Argument.
    (applications / "zepos-monitor.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Systemwaechter\n"
        f"Exec={runner} monitor %U %c %i\nTerminal=true\n",
        encoding="utf-8")
    (applications / "zepos-hidden.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Nicht anzuzeigen\n"
        f"Exec={runner} hidden\nNoDisplay=true\n", encoding="utf-8")
    marker.parent.mkdir(parents=True, exist_ok=True)


def _runner_script(path: Path, marker: Path) -> None:
    path.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> {marker}\n', encoding="utf-8")
    path.chmod(0o755)


def _wait_for(path: Path, seconds: float = 20.0) -> str:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists() and path.read_text(encoding="utf-8").strip():
            return path.read_text(encoding="utf-8")
        time.sleep(0.05)
    return ""


@pytest.mark.allow_subprocess
def test_the_launcher_lists_what_a_menu_shows_and_starts_it(tmp_path):
    """`zepos-menu --show drun`, der Rueckfall fuer SUPER+SPACE.

    Drei .desktop-Dateien, von denen eine NoDisplay=true traegt. Genau
    die darf nicht in der Liste stehen: g_app_info_get_all() liefert sie
    mit, und ein Starter, der sie zeigt, bietet die Dateityp-Handler des
    ganzen Systems zum Anklicken an.

    Und der Starter STARTET: das Kind zeigt auf ein Skript, das seine
    Argumente in eine Datei schreibt, und diese Datei ist der Beweis.
    """
    marker = tmp_path / "gestartet.txt"
    runner = tmp_path / "runner.sh"
    _runner_script(runner, marker)
    _desktop_files(tmp_path, marker, runner)

    run = run_menu(
        tmp_path, "type:Schreib key:enter",
        ["--show", "drun", "--cache-file", "/dev/null"])

    assert run.mark("order") == "Schreibmaschine|Systemwaechter", run.report
    # Kein `print` beim Starter: SUPER+SPACE hat keinen Aufrufer, der
    # etwas liest, und eine Zeile auf stdout waere hier nur Muell in
    # Hyprlands Protokoll.
    assert run.stdout == "", run.report
    assert run.returncode == 0, run.report
    assert _wait_for(marker).split() == ["editor"], run.report


def _settings_like_entry(tmp_path: Path, runner: Path) -> None:
    """Ein Eintrag in der Form, die zepos-settings.desktop wirklich hat.

    Nicht die Datei selbst, sondern ihre FORM: ein Name, unter dem
    niemand sucht, die Woerter, unter denen gesucht wird, und eine
    Aktion je Seite. Die echte Datei laege ausserhalb dieses Baums und
    startete ein Programm, das dieser Lauf nicht haben darf.
    """
    applications = tmp_path / "data" / "applications"
    applications.mkdir(parents=True, exist_ok=True)
    (applications / "zepos-settings.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Systemeinstellungen\n"
        f"Exec={runner} settings\n"
        "Keywords=bildschirme;monitor;displays;\n"
        "Actions=bildschirme;\n"
        "\n"
        "[Desktop Action bildschirme]\n"
        "Name=Bildschirme\n"
        f"Exec={runner} settings --page bildschirme\n",
        encoding="utf-8")


@pytest.mark.allow_subprocess
def test_a_word_from_the_keywords_finds_the_application(tmp_path):
    """GEMELDET am 12.08.2026: "ich finde den display manager wie nwg
    display nicht in der app suche".

    Der Eintrag der Einstellungen fuehrt seit seiner ersten Fassung
    `displays` unter Keywords, und der Filter las nur den Namen. Wer
    "display" tippte, sah eine leere Liste - ueber einem System, auf dem
    das Werkzeug installiert ist.
    """
    marker = tmp_path / "gestartet.txt"
    runner = tmp_path / "runner.sh"
    _runner_script(runner, marker)
    _desktop_files(tmp_path, marker, runner)
    _settings_like_entry(tmp_path, runner)

    run = run_menu(
        tmp_path, "type:display key:enter",
        ["--show", "drun", "--cache-file", "/dev/null"])

    assert run.returncode == 0, run.report
    assert _wait_for(marker).split() == ["settings"], run.report


@pytest.mark.allow_subprocess
def test_every_action_of_an_entry_is_a_line_of_its_own(tmp_path):
    """Eine Seite ist kein Programm, und trotzdem muss man sie finden.

    Die Bildschirmeinstellung war bis zum 12.08.2026 nwg-displays, also
    eine Anwendung mit eigenem Eintrag. Seither ist sie eine SEITE in
    zepos-settings-gui. Ohne die Aktionen stuende im Starter genau eine
    Zeile - "Systemeinstellungen" -, und sie oeffnete die erste Seite.

    Hier wird beides gemessen: dass die Zeile dasteht und dass sie die
    Exec-Zeile IHRER Aktion startet und nicht die der Anwendung.
    """
    marker = tmp_path / "gestartet.txt"
    runner = tmp_path / "runner.sh"
    _runner_script(runner, marker)
    _desktop_files(tmp_path, marker, runner)
    _settings_like_entry(tmp_path, runner)

    # Beide Zeilen stehen da, und das ist richtig so: die Anwendung
    # traegt "bildschirme" unter Keywords. Ausgeloest wird die ZWEITE,
    # deshalb ein Schritt nach unten - sonst pruefte dieser Test wieder
    # nur den Weg, den es vorher schon gab.
    run = run_menu(
        tmp_path, "type:Bildschirme key:down key:enter",
        ["--show", "drun", "--cache-file", "/dev/null"])

    assert run.mark("filtered") == (
        "Systemeinstellungen|Systemeinstellungen: Bildschirme"), run.report
    assert run.returncode == 0, run.report
    assert _wait_for(marker).split() == [
        "settings", "--page", "bildschirme"], run.report


# --------------------------------------------------------------------
# --show all: die Suche ueber Anwendungen UND Tasten
# --------------------------------------------------------------------

def _hyprland_config(tmp_path: Path, marker: Path, runner: Path) -> None:
    """Eine Hyprland-Konfiguration, aus der der Leser etwas macht.

    Sie liegt unter XDG_CONFIG_HOME, weil keybinds.output_root() genau
    dort nachsieht - dieselbe Antwort, die der Generator beim Schreiben
    benutzt hat.
    """
    hypr = tmp_path / "config" / "hypr"
    hypr.mkdir(parents=True, exist_ok=True)
    (hypr / "hyprland.conf").write_text(
        "$mainMod = SUPER\n"
        "# @Bildschirm: Bildschirmfoto vom gewaehlten Bereich\n"
        f"bind = $mainMod, S, exec, {runner} bildschirmfoto\n"
        # ALT+F4 und nicht SUPER+SHIFT+X, damit die zweite Zeile keine
        # SUPER-Taste traegt: der Filter vergleicht Teilzeichenketten,
        # und "SUPER+S" steckt auch in "SUPER+SHIFT+X". Das ist richtig
        # so - wer "super+s" tippt, hat SUPER+SHIFT+X noch nicht
        # ausgeschlossen -, macht aber die Zusicherung unten stumpf.
        "# @Fenster: Fenster schliessen\n"
        "bind = ALT, F4, killactive\n",
        encoding="utf-8")


@pytest.mark.allow_subprocess
def test_the_search_finds_a_key_that_is_not_an_application_and_runs_it(tmp_path):
    """DIE BESCHWERDE VOM 11.08.2026, IM FENSTER NACHGESTELLT.

    "screenshot tool auch nicht" - es war da, SUPER+S rief es, und der
    Nutzer hat es nicht gefunden. Ein Anwendungsstarter konnte ihm nicht
    helfen: ein Bildschirmfoto ist keine .desktop-Datei.

    Hier wird genau das getippt, was er getippt haette - "Bildschirm" -,
    und gemessen wird beides: dass die Zeile erscheint, MIT ihrer Taste
    daneben, und dass Enter sie wirklich ausfuehrt. Der Beweis fuer das
    Zweite ist eine Datei, die das ausgefuehrte Skript schreibt.
    """
    marker = tmp_path / "gestartet.txt"
    runner = tmp_path / "runner.sh"
    _runner_script(runner, marker)
    _desktop_files(tmp_path, marker, runner)
    _hyprland_config(tmp_path, marker, runner)

    # Eine Aktion ist eine SHELL-Zeile und keine .desktop-Datei - in
    # einer bind-Zeile stehen Pipes und Kommandoersetzungen. Also braucht
    # dieser eine Lauf `sh`, und er bekommt genau das: ein Verzeichnis
    # mit einem Verweis darauf und sonst nichts. Der leere PATH der
    # uebrigen Laeufe ist Absicht, damit ein Starter kein echtes Programm
    # der Maschine erreichen kann; ein PATH mit /usr/bin darin haette
    # genau diese Absperrung fuer alle geoeffnet.
    #
    # Ein Weiterreicher und kein Symlink: die Isolationssperre in
    # tests/conftest.py verbietet das Anlegen eines Verweises AUF
    # /bin/sh, und zwar zu Recht - sie sieht nur den Pfad, auf den
    # gezeigt wird, und ein Test, der Verweise ausserhalb von tmp_path
    # anlegen darf, ist einer, der sie auch ueberschreiben koennte.
    shell_path = tmp_path / "shell"
    shell_path.mkdir(exist_ok=True)
    shell = shell_path / "sh"
    shell.write_text('#!/bin/sh\nexec /bin/sh "$@"\n', encoding="utf-8")
    shell.chmod(0o755)

    run = run_menu(
        tmp_path, "type:Bildschirm key:enter key:escape",
        ["--show", "all", "--cache-file", "/dev/null"],
        extra_env={"ZEPOS_SYSTEM_ROOT": str(SRC), "PATH": str(shell_path)})

    # Die Anwendungen zuerst, die Aktionen dahinter.
    assert run.mark("order") == (
        "Schreibmaschine|Systemwaechter|"
        "Bildschirm: Bildschirmfoto vom gewaehlten Bereich|"
        "Fenster: Fenster schliessen"), run.report

    assert run.mark("filtered") == (
        "Bildschirm: Bildschirmfoto vom gewaehlten Bereich"), run.report
    # Und die Taste steht daneben, im Fenster.
    assert run.mark("hints") == "SUPER + S", run.report

    assert run.returncode == 0, run.report
    assert run.stdout == "", run.report
    assert _wait_for(marker).split() == ["bildschirmfoto"], run.report


@pytest.mark.allow_subprocess
def test_the_key_itself_can_be_typed_when_the_name_is_forgotten(tmp_path):
    """Der andere Nutzer: der, der die Taste halb im Kopf hat.

    Er tippt "super s". Ein Filter, der nur den Text liest, findet dann
    nichts - und er ist derjenige, der am naechsten dran war.
    """
    marker = tmp_path / "gestartet.txt"
    runner = tmp_path / "runner.sh"
    _runner_script(runner, marker)
    _desktop_files(tmp_path, marker, runner)
    _hyprland_config(tmp_path, marker, runner)

    run = run_menu(
        tmp_path, "type:SUPER+S key:escape",
        ["--show", "all", "--cache-file", "/dev/null"],
        extra_env={"ZEPOS_SYSTEM_ROOT": str(SRC)})

    assert run.mark("filtered") == (
        "Bildschirm: Bildschirmfoto vom gewaehlten Bereich"), run.report


@pytest.mark.allow_subprocess
def test_without_the_reader_the_search_is_still_a_launcher(tmp_path):
    """Ohne zepos-config gibt es keine erzeugte Konfiguration.

    Das Fenster geht dann mit den Anwendungen auf. Es haengt an
    SUPER+SPACE - ein Starter, der wegen einer fehlenden Datei gar nicht
    mehr aufgeht, ist ein Desktop, den man nicht mehr bedienen kann
    (Spec §7.4).
    """
    marker = tmp_path / "gestartet.txt"
    runner = tmp_path / "runner.sh"
    _runner_script(runner, marker)
    _desktop_files(tmp_path, marker, runner)

    run = run_menu(
        tmp_path, "type:Schreib key:enter",
        ["--show", "all", "--cache-file", "/dev/null"],
        extra_env={"ZEPOS_SYSTEM_ROOT": str(tmp_path / "kein-zepos")})

    assert run.mark("order") == "Schreibmaschine|Systemwaechter", run.report
    assert run.returncode == 0, run.report
    assert _wait_for(marker).split() == ["editor"], run.report


@pytest.mark.allow_subprocess
def test_an_application_still_has_no_key_beside_it(tmp_path):
    """Die Gegenprobe zur Tastenspalte.

    Waere sie in jeder Zeile sichtbar, stuende neben jeder Anwendung ein
    leeres Feld - und `--show drun` und `--dmenu`, die fuenf Skripte
    benutzen, saehen anders aus als vorher.
    """
    marker = tmp_path / "gestartet.txt"
    runner = tmp_path / "runner.sh"
    _runner_script(runner, marker)
    _desktop_files(tmp_path, marker, runner)
    _hyprland_config(tmp_path, marker, runner)

    run = run_menu(
        tmp_path, "type:Schreib key:escape",
        ["--show", "all", "--cache-file", "/dev/null"],
        extra_env={"ZEPOS_SYSTEM_ROOT": str(SRC)})

    assert run.mark("filtered") == "Schreibmaschine", run.report
    assert run.mark("hints") == "", run.report


@pytest.mark.allow_subprocess
def test_a_terminal_application_is_opened_in_the_configured_terminal(tmp_path):
    """Terminal=true. g_app_info_launch() suchte sich sonst selbst ein
    Terminal - ueber GSettings der GNOME-Sitzung und eine eingebaute
    Liste -, und `terminal=` in der erzeugten Konfiguration waere eine
    Einstellung ohne Wirkung."""
    marker = tmp_path / "gestartet.txt"
    runner = tmp_path / "runner.sh"
    # Ein Prozentzeichen im Namen des Terminals, und zwar mit Absicht:
    # was launch() zusammenbaut, ist wieder eine Exec-Zeile, und GIO
    # wertet die Platzhalter darin ein zweites Mal aus. Ein Pfad mit "%"
    # darin faende sich danach zerschnitten wieder.
    terminal = tmp_path / "terminal 100%.sh"
    _runner_script(runner, marker)
    _runner_script(terminal, marker)
    _desktop_files(tmp_path, marker, runner)

    run = run_menu(
        tmp_path, "type:waechter key:enter",
        ["--show", "drun", "--cache-file", "/dev/null"],
        config=f"terminal={terminal}\n")

    assert run.returncode == 0, run.report
    # Genau diese vier Woerter und kein fuenftes: das %U aus der
    # Exec-Zeile muss weg sein. Gemessen am 11.08.2026 - mit einer
    # Exec-Zeile ohne Platzhalter blieb diese Zusicherung gruen, als
    # strip_field_codes() durch die unveraenderte Zeile ersetzt wurde.
    assert _wait_for(marker).split() == ["-e", str(runner), "monitor"], (
        run.report)


@pytest.mark.allow_subprocess
def test_the_launcher_refuses_to_run_something_that_was_only_typed(tmp_path):
    """Der Unterschied zwischen dmenu und Starter.

    Bei --dmenu ist getippter Text die Antwort. Im Starter ist er keine
    Anwendung, und Enter darf ihn weder ausgeben noch ausfuehren - sonst
    waere SUPER+SPACE eine Shell mit Fensterrahmen. Das Fenster bleibt
    stehen; erst Escape beendet es.
    """
    marker = tmp_path / "gestartet.txt"
    runner = tmp_path / "runner.sh"
    _runner_script(runner, marker)
    _desktop_files(tmp_path, marker, runner)

    run = run_menu(
        tmp_path, "type:rm-rf-slash key:enter key:escape",
        ["--show", "drun", "--cache-file", "/dev/null"])

    assert run.stdout == "", run.report
    assert run.returncode == 1, run.report
    assert not marker.exists() or marker.read_text() == "", run.report


@pytest.mark.allow_subprocess
def test_a_show_mode_that_does_not_exist_stops_instead_of_guessing(tmp_path):
    """wofi kennt `--show run`. ZepOS ruft es nirgends auf, also ist es
    hier nicht gebaut - und ein Starter, der stillschweigend etwas
    anderes zeigt, waere schlimmer als einer, der es sagt."""
    run = run_menu(tmp_path, "key:escape", ["--show", "run"])

    assert run.returncode != 0, run.report
    assert "--show run" in run.stderr, run.report


@pytest.mark.allow_subprocess
def test_an_unknown_switch_stops_instead_of_being_ignored(tmp_path):
    """Ein ignoriertes `--passwrod` waere ein Passwortfeld im Klartext
    in einem Fenster, das trotzdem aufgeht."""
    run = run_menu(tmp_path, "key:escape", ["--dmenu", "--passwrod"],
                   stdin="eins\n")

    assert run.returncode == 2, run.report
    assert "--passwrod" in run.stderr, run.report


# --------------------------------------------------------------------
# Das Toolkit, und zwar gemessen statt behauptet
# --------------------------------------------------------------------

# Ein Kind, das NUR importiert. Kein Fenster, keine Anzeige, kein
# broadway - die Frage ist, welche Bibliotheken der Prozess danach
# abbildet, und die beantwortet /proc/self/maps.
_TOOLKIT_PROBE = r"""
import re, sys
import zepos_menu.window
mapped = sorted({m.group(0) for line in open("/proc/self/maps")
                 for m in [re.search(r"/usr/lib/lib(gtk|adwaita)[^\s]*", line)] if m})
print("\n".join(mapped))
"""


@pytest.mark.allow_subprocess
def test_the_program_maps_gtk4_and_no_gtk3(tmp_path):
    """Der Toolkit-Nachweis, an der einzigen Stelle, an der er zaehlt.

    Bei einem uebersetzten Programm fragte man `objdump -p <binary> |
    grep NEEDED`. Ein Python-Programm hat kein solches Objekt; was es
    hat, sind die gi.require_version-Zeilen - und was daraus WIRKLICH
    geladen wird, steht in /proc/self/maps.

    Gemessen am 11.08.2026: `import zepos_menu.window` bildet
    /usr/lib/libgtk-4.so.1.2200.4 ab und kein libgtk-3. wofi, das dieses
    Programm ersetzt, meldet an derselben Frage
    `objdump -p /usr/bin/wofi | grep NEEDED` -> libgtk-3.so.0, und genau
    das war der Grund fuer den Austausch.
    """
    interpreter = _interpreter()
    if interpreter is None:
        pytest.skip("kein Interpreter hier kann gi/Gtk4 laden")
    executable, extra_path = interpreter

    result = subprocess.run(
        [executable, "-c", _TOOLKIT_PROBE],
        env={"PATH": "", "HOME": str(tmp_path),
             "PYTHONPATH": os.pathsep.join([str(MENU_ROOT), *extra_path])},
        capture_output=True, text=True, timeout=120)

    assert result.returncode == 0, result.stdout + result.stderr
    mapped = result.stdout.split()
    assert any("libgtk-4.so" in name for name in mapped), (
        "zepos-menu bildet kein GTK4 ab:\n" + result.stdout)
    assert not any("libgtk-3.so" in name for name in mapped), (
        "zepos-menu bildet GTK3 ab. ZepOS ist GTK4 - das ist der Grund, "
        "aus dem wofi ersetzt wurde:\n" + result.stdout)


@pytest.mark.allow_subprocess
def test_importing_the_window_says_nothing_on_stderr(tmp_path):
    """Ein sauberer Import, und das ist keine Kosmetik.

    Gemessen am 11.08.2026: window.py importierte Gdk ohne
    gi.require_version, und PyGObject schrieb bei JEDEM Start

        PyGIWarning: Gdk was imported without specifying a version first

    Auf dieser Maschine kam trotzdem Gdk 4.0 herein, weil Gtk 4.0 es
    mitbringt - auf einer mit gtk3 daneben entscheidet die Reihenfolge
    der Importe, welche. Und eine Zeile auf stderr bei jedem Druck auf
    SUPER+SPACE landet in Hyprlands Protokoll, wo sie die Meldungen
    verdeckt, um derentwillen jemand hineinsieht.

    Das kopflose Kind konnte das nicht sehen: es fordert Gdk fuer seine
    eigenen Tastencodes selbst an, und zwar vorher.
    """
    interpreter = _interpreter()
    if interpreter is None:
        pytest.skip("kein Interpreter hier kann gi/Gtk4 laden")
    executable, extra_path = interpreter

    result = subprocess.run(
        [executable, "-c", "import zepos_menu.window"],
        env={"PATH": "", "HOME": str(tmp_path),
             "PYTHONPATH": os.pathsep.join([str(MENU_ROOT), *extra_path])},
        capture_output=True, text=True, timeout=120)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == "", (
        "der blosse Import schreibt auf stderr:\n" + result.stderr)


@pytest.mark.allow_subprocess
def test_the_command_finds_its_own_package(tmp_path):
    """menu/bin/zepos-menu, so wie das Paket es nach /usr/bin legt.

    Es ist die einzige Datei, die kein Test sonst anfasst, und sie hat
    genau eine Aufgabe: das Verzeichnis mit `zepos_menu` vor dem ersten
    Import in den Suchpfad legen. Faellt sie aus, ist die Meldung
    "ModuleNotFoundError" auf einer Tastenkombination, die nichts tut.

    Gefahren wird sie mit `--show run` - eine Betriebsart, die es nicht
    gibt. Damit endet main() an der Schalterauswertung, bevor ein Fenster
    gebaut wird, und der Lauf braucht keine Anzeige. Was er beweist, ist
    trotzdem die ganze Kette: Befehl, Suchpfad, Paket, main().
    """
    interpreter = _interpreter()
    if interpreter is None:
        pytest.skip("kein Interpreter hier kann gi/Gtk4 laden")
    executable, extra_path = interpreter
    command = MENU_ROOT / "bin" / "zepos-menu"

    assert os.access(command, os.X_OK), (
        f"{command} ist nicht ausfuehrbar; das Paket installiert sie mit 0755")

    result = subprocess.run(
        [executable, str(command), "--show", "run"],
        env={"PATH": "", "HOME": str(tmp_path),
             "XDG_CONFIG_HOME": str(tmp_path / "config"),
             # NICHT auf menu/ zeigend: der Befehl muss sich das
             # Verzeichnis selbst hinlegen, und genau das wird gemessen.
             "PYTHONPATH": os.pathsep.join(extra_path)},
        capture_output=True, text=True, timeout=120)

    assert "ModuleNotFoundError" not in result.stderr, (
        "der Befehl findet sein eigenes Paket nicht:\n" + result.stderr)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "--show run" in result.stderr, result.stdout + result.stderr
