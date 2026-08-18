# SPDX-License-Identifier: GPL-3.0-or-later
"""In welchem Verzeichnis ein Terminal aufgeht.

GEMELDET am 12.08.2026, woertlich: "wir starten im terminal immer im
zepos verzeichniss was falsch ist es muss im standard verzeichniss
sein."

GEMESSEN, und in keiner Vorlage stand ein `cd`, das das erklaert haette -
die Ursache ist eine VERERBUNG ueber vier Prozesse:

    greetd
      -> src/bin/zepos-session
      -> ~/.local/bin/start-hyprland      cd "$ZEPOS_SYSTEM_ROOT"
      -> exec /usr/bin/start-hyprland     exec behaelt das Verzeichnis
      -> Hyprland                         Kinder erben es
      -> kitty                            ohne --directory: geerbt
      -> zsh                              der Prompt steht im Projekt

Das `cd` in der dritten Zeile ist notwendig: die ./generate_config.sh-
Aufrufe darunter finden sich sonst nicht. Was fehlte, war der Rueckweg.

WARUM DIESE DATEI ZWEI VERSCHIEDENE SACHEN MISST
    Weil ein Terminal im Heimatverzeichnis aufgehen muss, EGAL woher die
    Sitzung kam - und die Ursache oben deckt nur den Weg ab, der durch
    start-hyprland fuehrt. Wer `Hyprland` von Hand aus einem
    Projektverzeichnis startet, wer einen fremden Anmeldedienst benutzt,
    wer eine Sitzung aus einer Werkstattumgebung heraus aufmacht, umgeht
    ihn. Eine Zusicherung, die nur gilt, solange sich der Elternprozess
    richtig verhaelt, ist keine.

    Also zwei Messungen, und die zweite haelt auch ohne die erste:

      1. Der Starter uebergibt dem Compositor $HOME. Gemessen, indem der
         ERZEUGTE Starter wirklich laeuft - aus einem fremden
         Verzeichnis heraus - und sein Arbeitsverzeichnis im Augenblick
         des exec abgelesen wird.
      2. Jede Terminalbindung nennt ihr Verzeichnis selbst. Gemessen,
         indem die Zeile aus der ERZEUGTEN Konfiguration aus einem
         fremden Verzeichnis heraus wirklich ausgefuehrt wird, mit einem
         kitty, das mitschreibt, was es bekommt.

WIE PUNKT 1 GEMESSEN WIRD, OHNE EINEN COMPOSITOR ZU STARTEN
    Die letzte Zeile des Starters ist `exec /usr/bin/start-hyprland` -
    ein absoluter Pfad, den kein PATH-Stub abfaengt, und ein Compositor,
    den kein Test starten darf. Gemessen wird deshalb der Augenblick
    davor: bash sucht Funktionen vor Builtins, also ersetzt eine ueber
    BASH_ENV geladene Funktion namens `exec` das Builtin, schreibt $PWD
    mit und kehrt zurueck. Nachgeprueft, bevor darauf gebaut wurde -
    test_the_exec_trap_would_notice_a_missing_cd unten bricht die
    Zusicherung einmal und belegt, dass sie faellt.
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.generated_tree import GeneratedTree, build

REPOSITORY = Path(__file__).resolve().parents[2]
SRC = REPOSITORY / "src"
TEMPLATES = SRC / "templates"

ENV = "/usr/bin/env"
BASH = "/bin/bash"

# Die Schreibweisen, mit denen kitty ein Arbeitsverzeichnis annimmt -
# abgelesen an `kitty --help`, nicht geraten. test_the_option_the_binds
# _use_is_one_kitty_really_has haelt sie gegen das installierte Programm.
DIRECTORY_OPTIONS = ("--directory", "--working-directory", "-d")


@pytest.fixture(scope="module")
def tree(tmp_path_factory) -> GeneratedTree:
    return build(tmp_path_factory.mktemp("working-directory"))


# --------------------------------------------------------------------
# Punkt 1: was der Compositor erbt
# --------------------------------------------------------------------

def _generated_launcher(destination: Path, system_root: Path,
                        monkeypatch) -> Path:
    """~/.local/bin/start-hyprland, aus der Vorlage, wie der Generator es
    schreibt - samt eingesetztem {{ZEPOS_SYSTEM_ROOT}}."""
    monkeypatch.syspath_prepend(str(SRC))
    monkeypatch.setenv("ZEPOS_SYSTEM_ROOT", str(system_root))
    import template_processor

    processor = template_processor.ConfigProcessor(
        paths=template_processor.path_variables())
    processor.apply_template(
        TEMPLATES / "start-hyprland-config.template", destination)
    destination.chmod(0o755)
    return destination


def _fake_system_root(root: Path) -> Path:
    """Ein Projektverzeichnis, in das der Starter wechseln kann, mit
    einem generate_config.sh, das nichts tut ausser da zu sein."""
    system = root / "zepos-system-root"
    system.mkdir()
    generator = system / "generate_config.sh"
    generator.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    generator.chmod(0o755)
    return system


def _exec_trap(root: Path) -> Path:
    """Eine Datei fuer BASH_ENV, die `exec` durch eine Funktion ersetzt.

    Sie schreibt das Arbeitsverzeichnis auf, das der Compositor bekommen
    haette, und BEENDET dann die Shell. Das `exit` ist nicht Kosmetik: das
    echte `exec` ersetzt den Prozess, also laeuft danach keine Zeile mehr.
    Mit `return` lief der Starter weiter, fiel aus dem Auto-Zweig heraus
    in den Profil-Zweig und erreichte das zweite exec - zwei Messwerte
    fuer einen Start, und keiner von beiden entsprach einer Sitzung.
    """
    evidence = root / "exec-pwd"
    trap = root / "trap.sh"
    trap.write_text(
        "exec() {\n"
        f'    printf "%s\\n" "$PWD" >>"{evidence}"\n'
        f'    printf "%s\\n" "$*" >>"{evidence}.argv"\n'
        "    exit 0\n"
        "}\n",
        encoding="utf-8")
    return evidence


def _stub_directory(root: Path, *names: str) -> Path:
    """Die echten Programme, unter einem PATH, der sonst nichts enthaelt.

    Dieselbe Begruendung wie in tests/src/test_login.py: der Starter darf
    in diesem Lauf nichts finden, was nicht ausdruecklich hier steht.
    """
    stubs = root / "stubs"
    stubs.mkdir(exist_ok=True)
    for name in names:
        real = shutil.which(name)
        assert real, f"{name} ist auf diesem Rechner nicht da"
        stub = stubs / name
        # OHNE exec, und das ist kein Schoenheitsfehler: BASH_ENV wird
        # vererbt, also laedt auch jeder Stub die Falle aus _exec_trap.
        # Ein `exec "$real"` darin traefe die Funktion statt des Builtins
        # - der Stub taete nichts und schriebe stattdessen sein eigenes
        # Verzeichnis in die Messung. Gemessen: elf Eintraege statt
        # einem.
        stub.write_text(f'#!/bin/bash\n"{real}" "$@"\n', encoding="utf-8")
        stub.chmod(0o755)
    return stubs


def _run_launcher(launcher: Path, *, cwd: Path, home: Path, stubs: Path,
                  trap: Path, system_root: Path, argument: str | None = None):
    command = [ENV, "-i", f"PATH={stubs}", f"HOME={home}",
               f"BASH_ENV={trap}",
               f"XDG_CONFIG_HOME={home}/.config",
               f"ZEPOS_USER_ROOT={home}/.config/zepos",
               BASH, str(launcher)]
    if argument is not None:
        command.append(argument)
    return subprocess.run(command, env={}, cwd=str(cwd), input="",
                          capture_output=True, text=True, timeout=120)


@pytest.mark.allow_subprocess
def test_the_compositor_is_not_handed_the_project_directory(tmp_path, monkeypatch):
    """Der Weg der ersten Anmeldung: kein Profil, Auto-Erkennung.

    Der Starter wird AUS EINEM FREMDEN VERZEICHNIS gestartet und wechselt
    unterwegs in das Projektverzeichnis - beides so, wie es auf einer
    echten Maschine passiert. Gemessen wird, womit er den Compositor
    startet.
    """
    home = tmp_path / "home"
    (home / ".config" / "hypr").mkdir(parents=True)
    (home / ".config" / "zepos" / "profiles").mkdir(parents=True)
    fremd = tmp_path / "irgendwo-anders"
    fremd.mkdir()

    system_root = _fake_system_root(tmp_path)
    launcher = _generated_launcher(tmp_path / "start-hyprland", system_root,
                                   monkeypatch)
    evidence = _exec_trap(tmp_path)
    stubs = _stub_directory(tmp_path, "mkdir", "touch", "ls", "cat", "basename")

    result = _run_launcher(launcher, cwd=fremd, home=home, stubs=stubs,
                           trap=tmp_path / "trap.sh", system_root=system_root)
    assert "command not found" not in result.stderr, result.stderr

    assert evidence.is_file(), (
        "der Starter hat kein exec erreicht:\n" + result.stdout + result.stderr)
    reached = evidence.read_text(encoding="utf-8").split()
    assert reached == [str(home)], (
        f"der Compositor wird aus {reached} gestartet und nicht aus "
        f"{home} - alles, was er startet, erbt dieses Verzeichnis")


@pytest.mark.allow_subprocess
def test_the_compositor_is_not_handed_the_project_directory_with_a_profile(
        tmp_path, monkeypatch):
    """Und der Weg jeder WEITEREN Anmeldung: mit gespeichertem Profil.

    Zwei Tests und nicht einer, weil der Starter zwei exec-Zeilen hat.
    Eine davon zu reparieren und die andere nicht waere ein Fehler, der
    sich erst nach dem ersten `save-profile` zeigt - also genau dann,
    wenn niemand mehr an diese Aenderung denkt.
    """
    home = tmp_path / "home"
    hypr = home / ".config" / "hypr"
    hypr.mkdir(parents=True)
    profile = home / ".config" / "zepos" / "profiles" / "schreibtisch"
    profile.mkdir(parents=True)
    for name in ("monitors.conf", "workspaces.conf", "profile-env.conf",
                 "profile-autostart.conf", "profile-keybinds.conf"):
        (profile / name).write_text("", encoding="utf-8")

    status = hypr / "hyprland-status"
    status.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    status.chmod(0o755)

    fremd = tmp_path / "irgendwo-anders"
    fremd.mkdir()

    system_root = _fake_system_root(tmp_path)
    launcher = _generated_launcher(tmp_path / "start-hyprland", system_root,
                                   monkeypatch)
    evidence = _exec_trap(tmp_path)
    stubs = _stub_directory(tmp_path, "cp", "mkdir", "touch", "ls", "cat",
                            "basename")

    result = _run_launcher(launcher, cwd=fremd, home=home, stubs=stubs,
                           trap=tmp_path / "trap.sh", system_root=system_root,
                           argument="schreibtisch")
    assert "command not found" not in result.stderr, result.stderr

    assert evidence.is_file(), (
        "der Starter hat kein exec erreicht:\n" + result.stdout + result.stderr)
    reached = evidence.read_text(encoding="utf-8").split()
    assert reached == [str(home)], (
        f"der Compositor wird aus {reached} gestartet und nicht aus {home}")


@pytest.mark.allow_subprocess
def test_the_exec_trap_would_notice_a_missing_cd(tmp_path, monkeypatch):
    """Die Gegenprobe zu den beiden Tests darueber.

    Ein Messaufbau, der IMMER $HOME meldet, misst nichts. Hier wird die
    Zeile, die $HOME setzt, aus der erzeugten Datei entfernt - und die
    Messung muss dann das Projektverzeichnis sehen, das der Nutzer
    gemeldet hat. Erst damit ist bewiesen, dass die Zusicherung oben an
    genau dieser Zeile haengt.
    """
    home = tmp_path / "home"
    (home / ".config" / "hypr").mkdir(parents=True)
    (home / ".config" / "zepos" / "profiles").mkdir(parents=True)
    fremd = tmp_path / "irgendwo-anders"
    fremd.mkdir()

    system_root = _fake_system_root(tmp_path)
    launcher = _generated_launcher(tmp_path / "start-hyprland", system_root,
                                   monkeypatch)

    text = launcher.read_text(encoding="utf-8")
    assert 'cd "$HOME" || cd / || exit 1' in text, (
        "die Zeile, die diese Gegenprobe bricht, steht nicht mehr in der "
        "erzeugten Datei - dann misst der Test darueber etwas anderes")
    launcher.write_text(text.replace('cd "$HOME" || cd / || exit 1', ":"),
                        encoding="utf-8")

    evidence = _exec_trap(tmp_path)
    stubs = _stub_directory(tmp_path, "mkdir", "touch", "ls", "cat", "basename")

    _run_launcher(launcher, cwd=fremd, home=home, stubs=stubs,
                  trap=tmp_path / "trap.sh", system_root=system_root)

    assert evidence.is_file(), "der praeparierte Starter hat kein exec erreicht"
    assert evidence.read_text(encoding="utf-8").split() == [str(system_root)], (
        "ohne die Zeile landet der Compositor NICHT im Projektverzeichnis - "
        "dann misst der Aufbau nicht das, was er zu messen behauptet")


# --------------------------------------------------------------------
# Punkt 2: was die Terminalbindung selbst nennt
# --------------------------------------------------------------------

_BIND = re.compile(r"^\s*bind\s*=.*?,\s*exec\s*,\s*(.+)$", re.M)
_DESKTOP_EXEC = re.compile(r"^Exec=(.+)$", re.M)

# kitty, das ein eigenes Programm ausfuehrt, ist kein Terminal fuer den
# Nutzer, sondern eine Ausgabe - der VPN-Fortschritt, der Netz-Watchdog.
# Sein Arbeitsverzeichnis ist gleichgueltig, weil niemand darin tippt.
# Eine Login-Shell dagegen IST ein Terminal fuer den Nutzer, auch wenn
# sie hinter -e steht.
SHELLS = ("zsh", "bash", "sh", "fish")


def _terminal_commands(tree: GeneratedTree) -> list[tuple[str, str]]:
    """Jede erzeugte Zeile, die dem Nutzer ein Terminal aufmacht."""
    found: list[tuple[str, str]] = []
    for path in tree.generated_files():
        text = tree.read(path)
        for command in _BIND.findall(text) + _DESKTOP_EXEC.findall(text):
            words = shlex.split(command, comments=False, posix=True)
            if not words or Path(words[0]).name != "kitty":
                continue
            if "-e" in words:
                program = words[words.index("-e") + 1:]
                if program and Path(program[0]).name not in SHELLS:
                    continue
            found.append((tree.show(path), command))
    return found


def test_every_terminal_control_names_its_own_working_directory(tree):
    """Der Vorwaertslauf: keine Bindung, keine Startdatei bleibt uebrig.

    Fuenf Bindungen und ein Starter-Eintrag, in vier verschiedenen
    Dateien - eine davon in einem Skript, das nur im Notfall laeuft. Eine
    Aufzaehlung von Hand haette genau die vergessen.
    """
    commands = _terminal_commands(tree)
    assert len(commands) >= 6, (
        f"nur {len(commands)} Terminalbedienelemente gefunden - der Scan "
        f"findet nicht mehr, was er finden soll")

    ohne = [f"{where}: {command}" for where, command in commands
            if not any(option in shlex.split(command)
                       for option in DIRECTORY_OPTIONS)]
    assert ohne == [], (
        "diese Terminals uebernehmen das Arbeitsverzeichnis dessen, der "
        "sie startet:\n  " + "\n  ".join(ohne))


@pytest.mark.allow_subprocess
def test_a_terminal_opens_in_the_home_directory_even_from_somewhere_else(
        tree, tmp_path):
    """Der Fall, der den Fehler gemacht hat, nachgestellt und ausgefuehrt.

    Jede Bindung wird durch `sh -c` gejagt - so fuehrt Hyprland sie aus -
    und zwar aus einem Verzeichnis, das NICHT das Heimatverzeichnis ist.
    Ein kitty, das nichts tut ausser mitzuschreiben, haelt fest, was es
    geerbt haette und was ihm stattdessen gesagt wurde.

    Die erste Zusicherung ist die wichtigere: sie belegt, dass der
    Elternprozess wirklich woanders steht. Ohne sie waere der Test auch
    dann gruen, wenn die Vererbung zufaellig schon gestimmt haette.
    """
    home = tmp_path / "heim"
    home.mkdir()
    fremd = tmp_path / "ein-projektverzeichnis"
    fremd.mkdir()
    evidence = tmp_path / "aufgezeichnet"

    stubs = tmp_path / "stubs"
    stubs.mkdir()
    kitty = stubs / "kitty"
    kitty.write_text(
        "#!/bin/bash\n"
        f'printf "geerbt=%s\\n" "$PWD" >>"{evidence}"\n'
        f'printf "gesagt=%s\\n" "$*" >>"{evidence}"\n',
        encoding="utf-8")
    kitty.chmod(0o755)

    commands = _terminal_commands(tree)
    assert commands, "keine Terminalbedienelemente gefunden"

    for where, command in commands:
        evidence.write_text("", encoding="utf-8")
        result = subprocess.run(
            [ENV, "-i", f"PATH={stubs}", f"HOME={home}", "/bin/sh", "-c",
             command],
            env={}, cwd=str(fremd), capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, f"{where}: {result.stderr}"

        aufgezeichnet = dict(
            line.split("=", 1)
            for line in evidence.read_text(encoding="utf-8").splitlines())
        assert aufgezeichnet["geerbt"] == str(fremd), (
            f"{where}: der Elternprozess steht nicht woanders - dann misst "
            f"dieser Test den Fehlerfall gar nicht")

        words = shlex.split(aufgezeichnet["gesagt"])
        genannt = [words[index + 1] for index, word in enumerate(words)
                   if word in DIRECTORY_OPTIONS]
        assert genannt, f"{where}: kitty bekommt kein Verzeichnis genannt"
        for verzeichnis in genannt:
            aufgeloest = Path(os.path.expanduser(
                os.path.expandvars(verzeichnis).replace("$HOME", str(home))))
            assert aufgeloest == home, (
                f"{where}: kitty wird nach {aufgeloest} geschickt und nicht "
                f"ins Heimatverzeichnis {home}")


@pytest.mark.allow_subprocess
def test_the_option_the_binds_use_is_one_kitty_really_has():
    """Eine Schreibweise, die kitty nicht kennt, waere ein Terminal, das
    mit "unknown option" gar nicht erst aufgeht - schlimmer als das
    falsche Verzeichnis. Also gegen das installierte Programm gelesen und
    nicht gegen die Erinnerung an seine Dokumentation.
    """
    kitty = shutil.which("kitty")
    assert kitty, (
        "kitty ist auf diesem Rechner nicht da - dann bleibt die "
        "Schreibweise jeder Terminalbindung ungeprueft")
    hilfe = subprocess.run([kitty, "--help"], capture_output=True, text=True,
                           timeout=60)
    assert hilfe.returncode == 0, hilfe.stderr
    for option in DIRECTORY_OPTIONS:
        assert re.search(rf"(?<![\w-]){re.escape(option)}(?![\w-])",
                         hilfe.stdout), (
            f"kitty --help nennt {option} nicht")
