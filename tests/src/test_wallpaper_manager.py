# SPDX-License-Identifier: GPL-3.0-or-later
"""Whether grid mode is on, asked of the place the marker is written.

`is_grid_active()` could never answer "true" for the marker file, in two
independent ways at once:

  * the path "/tmp/grid-wallpaper-active-" was written across a line
    break in the template, so the test ran against a file literally
    called "/t\\n    mp/grid-wallpaper-active-";
  * even spelled correctly, `[ -f "$prefix"* ]` does the wrong thing at
    both ends: with no match it tests the unexpanded pattern, and with
    more than one it hands `-f` three arguments and fails as a syntax
    error. A wildcard does not belong inside a single `-f`.

The second half is the one that matters after the typo is gone, and no
text-level assertion sees either: the template reads as a perfectly
ordinary existence check. So the generated script is executed, with the
marker file actually on disk.

`grid-wallpaper-toggle.sh` writes that marker under `${TMPDIR:-/tmp}`,
so the check has to look there too - a hardcoded /tmp misses it for
anyone who sets TMPDIR, which every one of these tests does.

Safety: the child runs through `env -i` with the stub directory as the
ONLY entry on PATH, so a command with no stub fails with "command not
found" rather than reaching a real `swaybg`, `pkill` or `hyprctl`.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

# The shared backstop, from tests/conftest.py: a command the stub
# directory does not provide has to be a failure, not an empty string.
import conftest

SRC = Path(__file__).resolve().parents[2] / "src"

BASH = "/bin/bash"
ENV = "/usr/bin/env"

# Reads and writes inside tmp_path and reaches nothing else.
PASSTHROUGH = ("cat", "date", "mkdir", "rm", "find", "basename", "jq", "sort")
# Must never run for real.
RECORDED = ("swaybg", "pkill", "notify-send", "hyprctl", "convert", "sleep",
            "timeout")


@pytest.fixture
def script(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(SRC))
    import template_processor

    output = tmp_path / "wallpaper-manager.sh"
    template_processor.ConfigProcessor().apply_template(
        SRC / "templates" / "wallpaper-manager-config.template", output)
    output.chmod(0o755)
    return output


@pytest.fixture
def stubs(tmp_path):
    directory = tmp_path / "stubs"
    directory.mkdir()
    calls = tmp_path / "calls.txt"

    for name in RECORDED:
        stub = directory / name
        stub.write_text(
            "#!/bin/bash\n"
            f"printf '{name} %s\\n' \"$*\" >> '{calls}'\n"
            "exit 0\n", encoding="utf-8")
        stub.chmod(0o755)

    for name in PASSTHROUGH:
        assert name not in RECORDED
        real = shutil.which(name)
        assert real, f"the script needs {name}"
        # The absolute path, not the bare name: with the stub directory
        # as the whole of PATH, `exec find "$@"` finds this stub again
        # and spins there instead of running anything.
        assert real.startswith("/")
        stub = directory / name
        stub.write_text(f'#!/bin/bash\nexec "{real}" "$@"\n', encoding="utf-8")
        stub.chmod(0o755)

    # Reports a picture's size, which apply_wallpaper compares to decide
    # whether a wallpaper is portrait. A stub answering nothing would put
    # `[: : integer expected` in the way of the assertions below.
    identify = directory / "identify"
    identify.write_text(
        "#!/bin/bash\n"
        f"printf 'identify %s\\n' \"$*\" >> '{calls}'\n"
        "printf '1920\\n'\n"
        "exit 0\n", encoding="utf-8")
    identify.chmod(0o755)

    return directory


def _run(script: Path, action: str, stubs: Path, home: Path, tmp_path: Path):
    path = str(stubs)
    assert path.split(os.pathsep) == [str(stubs)]
    assert not os.environ.get("PATH", "").startswith(path)
    home.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [ENV, "-i", f"PATH={path}", f"HOME={home}", f"TMPDIR={tmp_path}",
         BASH, str(script), action],
        env={}, input="", capture_output=True, text=True, timeout=60)
    conftest.assert_no_missing_command(result, "the wallpaper manager")
    return result


@pytest.mark.allow_subprocess
def test_grid_mode_is_off_when_no_marker_exists(script, stubs, tmp_path):
    result = _run(script, "grid-active", stubs, tmp_path / "home", tmp_path)
    assert result.stdout.strip() == "false", result.stdout + result.stderr


@pytest.mark.allow_subprocess
def test_the_toggle_scripts_marker_is_found(script, stubs, tmp_path):
    """The marker grid-wallpaper-toggle.sh actually writes.

    Its name carries the profile - "grid-wallpaper-active-office" - so
    the check cannot look for a fixed filename and has to match a
    prefix. That is where the wildcard came from, and where it went
    wrong.
    """
    (tmp_path / "grid-wallpaper-active-office").write_text("1", encoding="utf-8")

    result = _run(script, "grid-active", stubs, tmp_path / "home", tmp_path)
    assert result.stdout.strip() == "true", result.stdout + result.stderr


@pytest.mark.allow_subprocess
def test_two_profiles_left_a_marker_each(script, stubs, tmp_path):
    """The failure the typo was hiding.

    As shipped, the broken path matched nothing, so the wildcard never
    expanded and `-f` got one argument: a wrong answer, but a quiet one.
    Correcting only the path would have swapped that for `-f` receiving
    two filenames - "too many arguments" - as soon as a second profile
    had ever been toggled. Measured on the pre-fix script: `false` with
    one marker present, `false` with two.
    """
    (tmp_path / "grid-wallpaper-active-office").write_text("1", encoding="utf-8")
    (tmp_path / "grid-wallpaper-active-home").write_text("1", encoding="utf-8")

    result = _run(script, "grid-active", stubs, tmp_path / "home", tmp_path)
    assert result.stdout.strip() == "true", result.stdout + result.stderr
    assert "unary operator" not in result.stderr
    assert "too many arguments" not in result.stderr


@pytest.mark.allow_subprocess
def test_a_directory_with_the_markers_name_is_not_a_marker(script, stubs,
                                                           tmp_path):
    """-f, not -e: the marker is a file."""
    (tmp_path / "grid-wallpaper-active-office").mkdir()

    result = _run(script, "grid-active", stubs, tmp_path / "home", tmp_path)
    assert result.stdout.strip() == "false", result.stdout + result.stderr


@pytest.mark.allow_subprocess
def test_the_hypr_flag_file_also_counts(script, stubs, tmp_path):
    """The other half of the condition, which did work - held so that
    fixing the wildcard cannot quietly drop it."""
    home = tmp_path / "home"
    (home / ".config" / "hypr").mkdir(parents=True)
    (home / ".config" / "hypr" / ".grid_mode_active").write_text(
        "1", encoding="utf-8")

    result = _run(script, "grid-active", stubs, home, tmp_path)
    assert result.stdout.strip() == "true", result.stdout + result.stderr


def _calls(tmp_path: Path) -> list[str]:
    transcript = tmp_path / "calls.txt"
    if not transcript.exists():
        return []
    return transcript.read_text(encoding="utf-8").splitlines()


@pytest.mark.allow_subprocess
def test_a_random_wallpaper_whose_name_holds_a_space_is_applied_whole(
        script, stubs, tmp_path):
    """`local wallpapers=($(find ...))` split the file list on spaces.

    A wallpaper is a file somebody downloaded, and its name may contain
    a space. Measured with ONE such file present: the array held two
    entries - "…/Sunset" and "Beach.jpg" - so the count the random index
    is drawn from is not the number of files, and every single draw
    handed apply_wallpaper a path that does not exist. The script then
    said "Datei nicht gefunden: Beach.jpg" and stopped.

    One file rather than two, so the failure is certain rather than
    likely: with a single spaced name, BOTH fragments are wrong.

    The same file already reads its lists line by line in three other
    places (list_all_rows, list_with_thumbnails, list_for_monitor); this
    was the one call site that did not.
    """
    home = tmp_path / "home"
    landscape = home / ".config" / "hypr" / "wallpapers" / "landscape"
    landscape.mkdir(parents=True)
    wallpaper = landscape / "Sunset Beach.jpg"
    wallpaper.write_text("not really a picture", encoding="utf-8")

    result = _run(script, "random", stubs, home, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    missing = [line for line in _calls(tmp_path)
               if "Datei nicht gefunden" in line]
    assert missing == [], (
        "a path that is not a file was applied: " + "; ".join(missing))
    # The whole name reached the tool that reads the picture, which is
    # only possible if the whole name survived the list.
    looked_at = [line for line in _calls(tmp_path)
                 if line.startswith("identify ")]
    assert looked_at, "no wallpaper was applied at all"
    assert all(str(wallpaper) in line for line in looked_at), (
        "identify was handed a fragment: " + "; ".join(looked_at))


def test_the_marker_directory_is_the_one_the_toggle_writes_to():
    """Both halves must agree on where the marker lives.

    grid-wallpaper-toggle.template honours TMPDIR; the manager used to
    hardcode /tmp, so with TMPDIR set the toggle wrote a marker the
    manager could not have found even with the path spelled correctly.

    What this does and does not prove: the tests above set TMPDIR and
    place the marker themselves, so they show the manager reads TMPDIR -
    but not that the toggle still writes there. This holds that second
    half. It compares the mechanism both files use, not their exact
    quoting, and it would not catch the two drifting apart by way of a
    third variable.
    """
    toggle = (SRC / "templates" / "grid-wallpaper-toggle.template").read_text(
        encoding="utf-8")
    manager = (SRC / "templates" / "wallpaper-manager-config.template").read_text(
        encoding="utf-8")

    for name, text in (("toggle", toggle), ("manager", manager)):
        assert "${TMPDIR:-/tmp}" in text, (
            f"the {name} must honour TMPDIR, not hardcode /tmp")
        assert "grid-wallpaper-active-" in text, (
            f"the {name} lost the marker's name")


# --------------------------------------------------------------------
# Dass kein Aufraeumer sich selbst erschiesst
# --------------------------------------------------------------------

# Die Vorlagen, die swaybg beenden. Ausgeschrieben und nicht gesucht:
# eine Liste, die sich aus dem Bestand ergibt, ist mit jedem Bestand
# einverstanden - auch mit einem, in dem eine davon den Aufraeumer
# verloren hat.
TAPETEN_VORLAGEN = (
    "wallpaper-manager-config.template",
    "grid-wallpaper-toggle.template",
    "random-wallpaper-config.template",
)


def _befehlszeilen(vorlage: str) -> list[tuple[int, str]]:
    """Die Zeilen einer Vorlage, ohne die Kommentare.

    `pkill -9 -f swaybg` steht in mehreren Koepfen als Beschreibung
    dessen, was passiert. Eine Suche ueber den ganzen Text faende die
    Erklaerung und nicht den Befehl.
    """
    pfad = SRC / "templates" / vorlage
    gefunden = []
    for nummer, zeile in enumerate(
            pfad.read_text(encoding="utf-8").splitlines(), 1):
        ohne = zeile.split("#", 1)[0]
        if ohne.strip():
            gefunden.append((nummer, ohne))
    return gefunden


@pytest.mark.parametrize("vorlage", TAPETEN_VORLAGEN)
def test_kein_aufraeumer_vergleicht_die_ganze_befehlszeile(vorlage):
    """`pkill -f swaybg` trifft seinen eigenen Starter.

    WAS GEMESSEN IST (04.09.2026)
        `pkill -9 -f <muster>` vergleicht die GANZE Befehlszeile, und
        die des eigenen Starters enthaelt das Muster. Ein
        `timeout 2 pkill -9 -f zepprobe-muster-xyz` endete mit 137 -
        SIGKILL, von sich selbst. Mit dem echten Muster stand dieselbe
        Zeile im Protokoll eines Laufes:

            wallpaper-manager: Zeile 256: 223953 Getoetet
                timeout 2 pkill -9 -f swaybg

        Die Folge ist keine Fehlermeldung, sondern Zufall: wie weit das
        Aufraeumen kam, entscheidet, welche swaybg es erreicht hat.
        Danach wird je Schirm neu gestartet, und ein Schirm, dessen
        alter Prozess ueberlebte, bekommt zwei - ein anderer keinen.
        Auf dem Schirm heisst das schwarz, und genau das war die
        Meldung vom 04.09.2026.

    ZWEI ERLAUBTE FORMEN
        `-x swaybg`       vergleicht den Prozessnamen genau. Der ist
                          beim Aufraeumer "pkill" - kein Selbsttreffer.
        `-f "[s]waybg"`   wo ein EINZELNER Schirm gemeint ist und nur
                          die Argumente ihn nennen: ein Ausdruck, der
                          auf "swaybg" passt und auf sich selbst nicht.
    """
    schlecht = []
    for nummer, zeile in _befehlszeilen(vorlage):
        for werkzeug in ("pkill", "pgrep"):
            if werkzeug not in zeile:
                continue
            if "-f" not in zeile:
                continue
            if "swaybg" not in zeile:
                continue
            if "[s]waybg" in zeile:
                continue          # der Klammerkniff, siehe oben
            schlecht.append(f"{vorlage}:{nummer}: {zeile.strip()}")

    assert schlecht == [], (
        "diese Zeilen vergleichen die ganze Befehlszeile gegen "
        "\"swaybg\" und treffen damit ihren eigenen Starter:\n  "
        + "\n  ".join(schlecht)
        + "\n\nEntweder `-x swaybg` (der Prozessname) oder, wo ein "
          "einzelner Schirm gemeint ist, `-f \"[s]waybg -o <name>\"`.")


def test_die_zusicherung_wuerde_die_alte_form_sehen():
    """Der Gegenbeweis - eine Zusicherung, die nichts findet, ist gruen.

    Nachgestellt wird genau die Zeile, die bis zum 04.09.2026 in
    wallpaper-manager-config.template stand.
    """
    zeilen = [
        (1, '    timeout 2 pkill -9 -f swaybg 2>/dev/null || true'),
        (2, '    timeout 2 pkill -9 -x swaybg 2>/dev/null || true'),
        (3, '    timeout 2 pkill -f "[s]waybg -o $name" 2>/dev/null || true'),
    ]
    getroffen = []
    for nummer, zeile in zeilen:
        if ("pkill" in zeile and "-f" in zeile and "swaybg" in zeile
                and "[s]waybg" not in zeile):
            getroffen.append(nummer)

    assert getroffen == [1], (
        f"die Regel trifft die Zeilen {getroffen} - sie soll genau die "
        f"erste treffen: die alte Form. Die zweite (-x) und die dritte "
        f"(Klammerkniff) sind die beiden erlaubten.")
