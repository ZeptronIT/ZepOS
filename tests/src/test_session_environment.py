# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Umgebung, mit der eine Sitzung anfaengt - gemessen, nicht gelesen.

WORAUF DIESE DATEI ANTWORTET
    Zwei Meldungen vom 17.08.2026, und beide sind dieselbe Sache aus zwei
    Blickwinkeln.

    1. "das source bash command soll dort dann auch auto ausgefuehrt
        werden sodass alles direkt funktioniert"

       Im Erzeugungsprotokoll JEDER frischen Installation steht:

           ⚠ WARNING: ~/.local/bin is NOT in your PATH!
           Add this to your ~/.zshrc or ~/.bashrc:
             export PATH="$HOME/.local/bin:$PATH"
           Then run: source ~/.zshrc

       Die Warnung stammt aus ensure_local_bin() in
       src/generate_config.sh, und sie hatte recht: der Generator laeuft
       aus src/bin/zepos-session heraus, und das startet greetd mit dem
       PATH von systemd. Eine Anleitung an einen Menschen ist die falsche
       Antwort auf eine Bedingung, die das Programm selbst herstellen
       kann - zumal auf einer Maschine, auf der der Mensch die
       Anleitung erst gar nicht zu sehen bekommt.

    2. "warum ist das so anders immernoch"

       GEMESSEN am 17.08.2026 in /etc/passwd der letzten Installation:
       das angelegte Konto bekommt /usr/bin/bash. Erzeugt werden fuer
       dieses Konto ~/.zshrc und ~/.p10k.zsh, und zepos-desktop haengt
       hart an zsh und powerlevel10k. Auf dem Abnahmebild steht deshalb
       `[tester@zepos ~]$` - bash' eingebauter Prompt - und nicht der,
       den dieses Projekt baut.

WARUM AUSGEFUEHRT UND NICHT GELESEN
    Weil ein `grep` nach `export PATH` in einem Skript nur beweist, dass
    die Zeichen dastehen. Ob sie ankommen, entscheidet die Reihenfolge:
    steht der Export HINTER dem Aufruf von zepos-generate, hat der
    Generator ihn nicht. Diese Datei liest deshalb ab, was die
    aufgerufenen Programme WIRKLICH in ihrer Umgebung vorfinden.

DIE SICHERHEITSBEGRUENDUNG, dieselbe wie in tests/src/test_login.py
    Jede Sitzung laeuft unter `env -i` mit einem Stub-Verzeichnis als
    ganzem PATH. Was das Skript aufruft, ist entweder ein Stub aus
    tmp_path oder eines der harmlosen Durchreichprogramme unten; alles
    andere wird zu "command not found", und
    conftest.assert_no_missing_command sieht es auf beiden Stroemen.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests import conftest

REPOSITORY = Path(__file__).resolve().parents[2]
SRC = REPOSITORY / "src"
SESSION = SRC / "bin" / "zepos-session"
GENERATOR = SRC / "generate_config.sh"

ENV = "/usr/bin/env"

# Dieselbe Liste wie in test_login.py, plus die zwei Programme, die der
# neue Block braucht, wenn $SHELL gar nicht gesetzt ist: getent liest
# /etc/passwd, cut schneidet das siebte Feld heraus. Beide lesen nur.
PASSTHROUGH = ("bash", "date", "id", "tty", "sed", "awk", "tail", "rm",
               "mkdir", "chmod", "getent", "cut")


def _stubs(directory: Path, **bodies: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name in PASSTHROUGH:
        conftest.assert_safe_to_passthrough(name)
        real = shutil.which(name)
        assert real, f"{name} ist auf diesem Rechner nicht da"
        bodies.setdefault(name, f'exec "{real}" "$@"\n')
    for name, body in bodies.items():
        stub = directory / name
        stub.write_text("#!/bin/bash\n" + body, encoding="utf-8")
        stub.chmod(0o755)
    return directory


def _run(tmp_path: Path, path_entries: list[Path],
         **environment: str) -> subprocess.CompletedProcess:
    # Die Sicherheitsbedingung, ausgeschrieben: JEDER Eintrag des PATH,
    # den das Kind bekommt, liegt unter tmp_path. Ein Test darf hier also
    # ein zweites Verzeichnis dazunehmen - er braucht das, um zu messen,
    # was bei einem schon vorbelegten PATH passiert - und kann trotzdem
    # kein Programm dieses Rechners erreichen.
    for entry in path_entries:
        assert tmp_path in entry.parents or entry == tmp_path, entry
    path = os.pathsep.join(str(entry) for entry in path_entries)
    assert not os.environ.get("PATH", "").startswith(str(path_entries[0]))
    return subprocess.run(
        [ENV, "-i", f"PATH={path}",
         *(f"{key}={value}" for key, value in environment.items()),
         str(SESSION)],
        env={}, input="", capture_output=True, text=True, timeout=120)


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / ".config" / "zepos").mkdir(parents=True)
    (home / ".local" / "state").mkdir(parents=True)
    return home


def _session(tmp_path: Path, *, vorbelegt: bool = False,
             **environment: str) -> dict[str, str]:
    """Eine Anmeldung, und was die beiden gerufenen Programme sehen.

    Zurueck kommen die Umgebungen als flache Namen: `generate_PATH`,
    `launcher_SHELL` und so fort. Beide Seiten werden gebraucht - der
    Generator ist der, der die Warnung schreibt, und der Starter ist der,
    von dem der Compositor und damit jedes Terminal erbt.

    `vorbelegt` legt ~/.local/bin schon in den PATH, mit dem die Sitzung
    startet: der Fall, in dem eine Anmeldung den Eintrag ein zweites Mal
    voranstellen koennte.
    """
    home = _home(tmp_path)
    evidence = tmp_path / "evidence"
    evidence.mkdir(exist_ok=True)
    launcher = home / ".local" / "bin" / "start-hyprland"
    launcher.parent.mkdir(parents=True, exist_ok=True)

    # Der Starter wird HIER geschrieben und vom Generator-Stub nur an
    # seinen Platz gelegt. Ein Skript, das ein Skript schreibt, das ein
    # Skript schreibt, ist drei Ebenen Maskierung tief - und die mittlere
    # hat beim ersten Versuch `${SHELL-}` woertlich ausgegeben statt es
    # aufzuloesen.
    vorlage = evidence / "launcher-vorlage"
    vorlage.write_text(
        "#!/bin/bash\n"
        f'printf "%s" "$PATH" >"{evidence}/launcher_PATH"\n'
        f'printf "%s" "${{SHELL-}}" >"{evidence}/launcher_SHELL"\n',
        encoding="utf-8")

    stubs = _stubs(
        tmp_path / "stubs",
        # Der Stub schreibt seine Umgebung auf und legt danach den
        # Starter an - genau wie der echte Generator, dessen erste
        # Wirkung dieses Skript ist. `$(<datei)` ist ein Builtin: kein
        # cat, also auch kein weiteres Programm im PATH.
        **{"zepos-generate":
           f'printf "%s\\n" "$PATH" >"{evidence}/generate_PATH"\n'
           f'printf "%s\\n" "${{SHELL-}}" >"{evidence}/generate_SHELL"\n'
           f'mkdir -p "{launcher.parent}"\n'
           f'printf "%s\\n" "$(<"{vorlage}")" >"{launcher}"\n'
           f'chmod 0755 "{launcher}"\n'},
    )

    environment.setdefault("HOME", str(home))
    environment.setdefault("XDG_CONFIG_HOME", str(home / ".config"))
    environment.setdefault("XDG_STATE_HOME", str(home / ".local" / "state"))
    entries = [stubs] + ([launcher.parent] if vorbelegt else [])
    result = _run(tmp_path, entries, **environment)
    conftest.assert_no_missing_command(result, "die Sitzung")

    seen: dict[str, str] = {"home": str(home)}
    for name in ("generate_PATH", "generate_SHELL",
                 "launcher_PATH", "launcher_SHELL"):
        file = evidence / name
        assert file.is_file(), (
            f"{name} wurde nicht geschrieben - die Sitzung hat das "
            f"zugehoerige Programm nicht erreicht.\n{result.stdout}\n"
            f"{result.stderr}")
        seen[name] = file.read_text(encoding="utf-8").strip()
    return seen


# --------------------------------------------------------------------
# Der PATH
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_the_generator_no_longer_has_a_reason_to_print_that_warning(tmp_path):
    """Die Bedingung der Warnung, gegen den PATH, den der Generator hat.

    Nicht der Text wird geprueft, sondern die Lage, die ihn ausloest -
    sonst waere der Test mit einem `echo` weniger zu bestehen.
    """
    generator = GENERATOR.read_text(encoding="utf-8")
    assert '":$PATH:" != *":$LOCAL_BIN:"*' in generator, (
        "ensure_local_bin() in generate_config.sh prueft nicht mehr so, "
        "wie dieser Test annimmt - die Messung unten misst dann etwas "
        "anderes als die Warnung")

    seen = _session(tmp_path)
    lokal = f"{seen['home']}/.local/bin"
    assert lokal in seen["generate_PATH"].split(os.pathsep), (
        f"der Generator laeuft ohne {lokal} im PATH und schreibt darum "
        f"weiterhin die Anleitung: {seen['generate_PATH']}")


@pytest.mark.allow_subprocess
def test_the_compositor_inherits_the_directory_its_own_launcher_lives_in(
        tmp_path):
    """Der Starter LIEGT in ~/.local/bin, und alles, was der Compositor
    danach startet, erbt den PATH von hier. Ohne diese Zeile findet eine
    Bindung, die `wallpaper-manager` oder `save-profile` ruft, nichts."""
    seen = _session(tmp_path)
    lokal = f"{seen['home']}/.local/bin"
    assert lokal in seen["launcher_PATH"].split(os.pathsep), (
        f"start-hyprland startet ohne {lokal} im PATH: "
        f"{seen['launcher_PATH']}")


@pytest.mark.allow_subprocess
def test_the_directory_is_first_because_that_is_what_it_is_for(tmp_path):
    """~/.local/bin ist der Ort fuer die erzeugten Hilfsskripte. Steht es
    HINTER /usr/bin, gewinnt ein gleichnamiges Programm des Systems -
    und der Sinn des Verzeichnisses ist genau der umgekehrte."""
    seen = _session(tmp_path)
    lokal = f"{seen['home']}/.local/bin"
    assert seen["launcher_PATH"].split(os.pathsep)[0] == lokal, (
        f"{lokal} steht nicht vorn: {seen['launcher_PATH']}")


@pytest.mark.allow_subprocess
def test_the_path_does_not_grow_by_one_entry_at_every_login(tmp_path):
    """Ein PATH, der sich bei jeder Anmeldung wiederholt, ist der Fehler,
    den diese Vorlage schon einmal hatte: GEMESSEN am 17.08.2026 auf dem
    Rechner, von dem sie stammt, stand ~/.local/bin dort dreimal drin.
    """
    seen = _session(tmp_path, vorbelegt=True)
    lokal = f"{seen['home']}/.local/bin"
    assert seen["launcher_PATH"].split(os.pathsep).count(lokal) == 1, (
        f"{lokal} steht mehrfach im PATH: {seen['launcher_PATH']}")


# --------------------------------------------------------------------
# Die Schale
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_a_bash_account_gets_the_shell_the_configuration_is_written_for(
        tmp_path):
    """GEMESSEN in /etc/passwd der letzten Installation:

        tester:x:1000:1000::/home/tester:/usr/bin/bash

    Erzeugt werden fuer dasselbe Konto ~/.zshrc und ~/.p10k.zsh. Ein
    Terminal, das bash oeffnet, liest keine der beiden Dateien - der
    Prompt auf dem Abnahmebild ist der eingebaute von bash.

    kitty nimmt $SHELL vor dem Eintrag in /etc/passwd
    (/usr/lib/kitty/kitty/constants.py Zeile 166, nachgelesen am
    17.08.2026), also reicht diese Variable, um jedes Terminal der
    Sitzung auf die Schale zu stellen, fuer die konfiguriert ist.
    """
    if not Path("/usr/bin/zsh").is_file():
        pytest.skip("zsh liegt nicht unter /usr/bin - der Zweig, der es "
                    "setzt, kann hier nicht gemessen werden")

    seen = _session(tmp_path, SHELL="/usr/bin/bash")
    assert seen["launcher_SHELL"] == "/usr/bin/zsh", (
        f"die Sitzung startet weiter mit SHELL={seen['launcher_SHELL']}")


@pytest.mark.allow_subprocess
def test_a_shell_somebody_chose_on_purpose_is_left_alone(tmp_path):
    """bash ist keine Wahl, sondern die Vorgabe von useradd. Was jemand
    per `chsh` eingetragen hat, IST eine - und eine Sitzung, die eine
    Entscheidung ueberschreibt, ist ein Fehler und kein Dienst."""
    seen = _session(tmp_path, SHELL="/usr/bin/fish")
    assert seen["launcher_SHELL"] == "/usr/bin/fish", (
        f"eine eigene Wahl wurde ueberschrieben: {seen['launcher_SHELL']}")
