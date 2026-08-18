# SPDX-License-Identifier: GPL-3.0-or-later
"""floating-window-manager.sh, run against window titles it did not choose.

A window title is foreign text. A browser tab is called
`"Rust" in 2026 - YouTube`, an editor puts the project in brackets, and a
terminal shows whatever is running in it. The script both WROTE those
titles into JSON and READ them back into jq programs, and it did each of
those by pasting the text in:

  * save_positions built the file with a shell heredoc, so a quote in a
    title closed the JSON string early. Measured with the title above:
    `jq: parse error: Invalid numeric literal at line 3`, and the saved
    layout unreadable from then on. save_layout never looked at jq's
    exit status, so it left a 0-byte file behind and said
    "Layout gespeichert".
  * load_positions pasted values into jq's SOURCE. The JetBrains
    fallback assembled `startswith("myproj \\[")` - a backslash-bracket
    JSON escape - so jq stopped with "Invalid escape at line 1,
    column 4" and that branch had never matched a window in its life.

Both are held here by running the generated script: neither is visible
to a text-level assertion, because the template reads as perfectly
ordinary shell either way.

Safety: every child runs through `env -i` with the stub directory as the
ONLY entry on PATH, asserted before the run, so a command with no stub
fails with "command not found" rather than reaching the real `hyprctl`,
`zepos-menu` or `zenity`. `hyprctl` answers from a canned file and records
every dispatch it is asked for; nothing reaches a compositor.
"""
import json
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

# A title of the shape that broke the writer: a quote, and a dash that is
# not the en dash the JetBrains branches look for.
BROWSER_TITLE = '"Rust" in 2026 - YouTube'

# Reads and writes inside tmp_path and reaches nothing else.
PASSTHROUGH = ("jq", "date", "mkdir", "rm", "cat", "sed", "awk", "wc",
               "head", "mktemp", "mkfifo", "ls", "basename", "xargs", "cp",
               "mv", "sort", "grep", "printf")
# Must never run for real.
RECORDED = ("notify-send", "zepos-menu", "sleep")


@pytest.fixture
def script(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(SRC))
    import template_processor

    output = tmp_path / "floating-window-manager"
    template_processor.ConfigProcessor().apply_template(
        SRC / "templates" / "floating-window-manager.template", output)
    output.chmod(0o755)
    return output


def _window(**overrides) -> dict:
    window = {
        "address": "0xaaaa", "class": "firefox", "title": BROWSER_TITLE,
        "initialTitle": "Firefox", "floating": True, "at": [100, 200],
        "size": [800, 600], "pid": 4711, "workspace": {"id": 1},
    }
    window.update(overrides)
    return window


@pytest.fixture
def stubs(tmp_path):
    """The stub directory, with hyprctl answering from a canned file."""
    directory = tmp_path / "stubs"
    directory.mkdir()
    calls = tmp_path / "calls.txt"
    clients = tmp_path / "clients.json"
    clients.write_text("[]", encoding="utf-8")

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
        # The absolute path: with the stub directory as the whole of
        # PATH, `exec jq "$@"` would find this stub again.
        assert real.startswith("/")
        stub = directory / name
        stub.write_text(f'#!/bin/bash\nexec "{real}" "$@"\n', encoding="utf-8")
        stub.chmod(0o755)

    # Answers `clients -j` from the file above and writes down every
    # dispatch. A dispatch is the only thing this script does to the
    # session, so it is the only thing worth recording.
    #
    # It also writes down the PATH it was RUN WITH. That is not
    # bookkeeping: it is the only way to see the PATH the script actually
    # holds by the time it runs a command, as opposed to the one this
    # harness handed to `env -i`. See _assert_the_path_was_not_widened.
    hyprctl = directory / "hyprctl"
    hyprctl.write_text(
        "#!/bin/bash\n"
        "# Test stub. Never reaches the real compositor.\n"
        f"printf 'hyprctl %s\\n' \"$*\" >> '{calls}'\n"
        f"printf 'effective-path %s\\n' \"$PATH\" >> '{calls}'\n"
        "if [ \"$1\" = clients ]; then\n"
        f"    exec /bin/cat '{clients}'\n"
        "fi\n"
        "exit 0\n", encoding="utf-8")
    hyprctl.chmod(0o755)

    # Consumes the progress pipe to the end. A stub that exited at once
    # would close the reading end and the script's next write to fd 3
    # would kill it - a failure of the harness, dressed as one of the
    # script.
    zenity = directory / "zenity"
    zenity.write_text(
        "#!/bin/bash\n"
        f"printf 'zenity %s\\n' \"$*\" >> '{calls}'\n"
        "exec /bin/cat > /dev/null\n", encoding="utf-8")
    zenity.chmod(0o755)

    return directory


def _clients(tmp_path: Path, windows) -> None:
    (tmp_path / "clients.json").write_text(json.dumps(list(windows)),
                                           encoding="utf-8")


def _assert_the_path_was_not_widened(stubs: Path, tmp_path: Path) -> None:
    """The other way the "command not found" backstop can be silent.

    That backstop asks whether a command was MISSING. It cannot ask
    whether a command was found somewhere this test never allowed,
    because a command that is found does not complain - and the whole
    isolation argument of this file is "PATH holds the stub directory and
    nothing else, so an unstubbed command cannot reach the real one".

    This script used to break that argument twice over. First by
    PREPENDING /usr/bin and friends, which overrode even the stubs.
    That was fixed by appending - and appending still leaves every
    command WITHOUT a stub falling through to the real binary on the
    machine running the tests, silently, which is exactly what the
    restriction exists to prevent.

    So the PATH is measured from INSIDE the child, at the moment it runs
    a command, rather than assumed from the one handed to `env -i`. The
    hyprctl stub writes its own $PATH into the transcript; this reads it
    back. A script that widens PATH again - by any means, in any
    direction - fails here instead of quietly borrowing the developer's
    /usr/bin.
    """
    transcript = tmp_path / "calls.txt"
    if not transcript.exists():
        return
    seen = [line.split(" ", 1)[1]
            for line in transcript.read_text(encoding="utf-8").splitlines()
            if line.startswith("effective-path ")]
    for value in seen:
        assert value.split(os.pathsep) == [str(stubs)], (
            "the script widened the PATH it was given, so a command with "
            "no stub reaches the real binary on this machine instead of "
            f"failing: {value}")


def _run(script: Path, arguments, stubs: Path, home: Path,
         tmp_path: Path) -> subprocess.CompletedProcess:
    path = str(stubs)
    assert path.split(os.pathsep) == [str(stubs)]
    assert not os.environ.get("PATH", "").startswith(path)
    home.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [ENV, "-i", f"PATH={path}", f"HOME={home}", f"TMPDIR={tmp_path}",
         BASH, str(script), *arguments],
        env={}, input="", capture_output=True, text=True, timeout=60)
    conftest.assert_no_missing_command(result, "the script")
    _assert_the_path_was_not_widened(stubs, tmp_path)
    return result


def _calls(tmp_path: Path, command: str) -> list[str]:
    transcript = tmp_path / "calls.txt"
    if not transcript.exists():
        return []
    return [line for line in transcript.read_text(encoding="utf-8").splitlines()
            if line.split(" ", 1)[0] == command]


def _positions(home: Path) -> Path:
    return home / ".config" / "hypr" / "floating-positions" / "positions.json"


# --------------------------------------------------------------------
# what the harness rests on
# --------------------------------------------------------------------

def test_the_script_does_not_override_the_path_it_was_given():
    """Every test below is isolated by PATH, and this script used to walk
    straight past that.

    Its first line was
    `export PATH="/usr/bin:/bin:/usr/local/bin:$HOME/.local/bin:$PATH"`,
    which puts the machine's own directories AHEAD of whatever the caller
    set. Measured: a child started with `env -i PATH=<stubs only>` still
    ran the real /usr/bin/hyprctl of the machine the tests were running
    on - and because hyprctl writes "HYPRLAND_INSTANCE_SIGNATURE not set!"
    to STDOUT and exits 0, neither the stub nor any "command not found"
    check noticed.

    The fallback directories still belong here: launched from a Waybar
    module, PATH can be nearly empty. They belong at the END.
    """
    text = (SRC / "templates" / "floating-window-manager.template").read_text(
        encoding="utf-8")
    found = 0
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith("export PATH="):
            continue
        found += 1
        value = stripped.split("=", 1)[1].strip('"')
        assert value.startswith("$PATH"), (
            f"line {number} puts its own directories ahead of the caller's "
            f"PATH: {stripped}")
    assert found == 1, (
        f"expected exactly one `export PATH=` line, found {found} - a "
        "second one is a second chance to get the order wrong")


@pytest.mark.allow_subprocess
def test_the_script_does_not_widen_the_path_it_was_given(script, stubs, tmp_path):
    """Appending was not enough, and that took a second measurement.

    Ordering was the first defect and it is held by the test above,
    which reads the template. It cannot see the second one, because the
    second one is not about order at all:

        export PATH="$PATH:/usr/bin:/bin:/usr/local/bin:$HOME/.local/bin"

    respects the caller's order perfectly and STILL puts /usr/bin on the
    child's PATH. Every command with a stub is then found in the stub
    directory - correctly, first - and every command WITHOUT one falls
    through to the real binary on this machine. The isolation argument
    of this whole file is that the second case cannot happen.

    Nothing could have noticed. "command not found" is the only signal
    the harness has, and it is precisely the signal a command that WAS
    found does not produce. So this measures the PATH from inside the
    child instead: the hyprctl stub writes its own $PATH down, and
    _assert_the_path_was_not_widened - which runs after every child in
    this file - reads it back.

    Named here as well as enforced there, because a property held only
    by a helper is a property no one reads.
    """
    _clients(tmp_path, [_window()])

    _run(script, ["save"], stubs, tmp_path / "home", tmp_path)

    recorded = [line for line in (tmp_path / "calls.txt").read_text(
        encoding="utf-8").splitlines() if line.startswith("effective-path ")]
    assert recorded, (
        "the script never ran a command, so nothing about its PATH was "
        "measured")
    for line in recorded:
        assert line.split(" ", 1)[1].split(os.pathsep) == [str(stubs)], line


# --------------------------------------------------------------------
# writing
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_a_title_with_quotes_in_it_is_saved_as_valid_json(script, stubs,
                                                          tmp_path):
    """The heredoc, measured.

    `"class": "$class", "title": "$title"` closes its string at the
    first quote the title contains, and everything after it is read as
    JSON syntax. The file this produced could not be loaded again by the
    very next command.
    """
    home = tmp_path / "home"
    _clients(tmp_path, [_window()])

    result = _run(script, ["save", "all"], stubs, home, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    saved = _positions(home)
    assert saved.exists(), "nothing was written at all"
    document = json.loads(saved.read_text(encoding="utf-8"))
    assert [w["title"] for w in document["windows"]] == [BROWSER_TITLE]
    assert document["windows"][0]["position"] == {"x": 100, "y": 200}
    assert document["windows"][0]["size"] == {"width": 800, "height": 600}


@pytest.mark.allow_subprocess
def test_a_backslash_in_a_title_survives_too(script, stubs, tmp_path):
    """A quote is not the only character JSON gives a meaning to."""
    title = 'C:\\Users\\test - "Editor"'
    home = tmp_path / "home"
    _clients(tmp_path, [_window(title=title)])

    _run(script, ["save", "all"], stubs, home, tmp_path)

    document = json.loads(_positions(home).read_text(encoding="utf-8"))
    assert document["windows"][0]["title"] == title


@pytest.mark.allow_subprocess
def test_saving_no_floating_windows_still_writes_a_readable_file(
        script, stubs, tmp_path):
    """An empty list is a state, not a broken file: load_positions checks
    the JSON before it reads it, and refused an empty desk."""
    home = tmp_path / "home"
    _clients(tmp_path, [_window(floating=False)])

    _run(script, ["save", "all"], stubs, home, tmp_path)

    document = json.loads(_positions(home).read_text(encoding="utf-8"))
    assert document["windows"] == []


@pytest.mark.allow_subprocess
def test_a_named_layout_is_written_or_the_failure_is_reported(script, stubs,
                                                              tmp_path):
    """save_layout said "Layout gespeichert" over a 0-byte file.

    `jq ... > "$layout_file"` creates the destination BEFORE jq runs, so
    a jq that dies on the broken positions file left an empty layout
    behind - and nothing read jq's exit status, so the dialog announced a
    success over it.
    """
    home = tmp_path / "home"
    _clients(tmp_path, [_window()])

    result = _run(script, ["save-layout", "arbeit"], stubs, home, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    layout = (home / ".config" / "hypr" / "floating-positions" / "layouts"
              / "arbeit.json")
    assert layout.exists(), "no layout file was written"
    assert layout.stat().st_size > 0, "an empty layout file was left behind"
    document = json.loads(layout.read_text(encoding="utf-8"))
    assert document["layout_name"] == "arbeit"
    assert document["windows"][0]["title"] == BROWSER_TITLE
    assert any("Layout gespeichert" in line
               for line in _calls(tmp_path, "notify-send"))


@pytest.mark.allow_subprocess
def test_a_layout_that_cannot_be_written_is_not_announced_as_saved(
        script, stubs, tmp_path):
    """The half that has to hold when something really does go wrong."""
    home = tmp_path / "home"
    _clients(tmp_path, [_window()])
    layouts = home / ".config" / "hypr" / "floating-positions" / "layouts"
    layouts.mkdir(parents=True)
    layouts.chmod(0o500)

    try:
        result = _run(script, ["save-layout", "arbeit"], stubs, home, tmp_path)
    finally:
        layouts.chmod(0o700)

    assert result.returncode != 0, result.stdout + result.stderr
    assert not (layouts / "arbeit.json").exists(), (
        "an unwritable directory still produced a file")
    assert not any("Layout gespeichert" in line
                   for line in _calls(tmp_path, "notify-send")), (
        "a failure was announced as a success: "
        + "; ".join(_calls(tmp_path, "notify-send")))


# --------------------------------------------------------------------
# reading
# --------------------------------------------------------------------

def _saved(home: Path, **overrides) -> Path:
    """One saved position, written by hand so the reader is measured on
    its own rather than through the writer."""
    window = {
        "class": "jetbrains-idea",
        "title": "myproj [~/src/myproj] – Main.rs",
        "initial_title": "",
        "workspace": 1,
        "position": {"x": 100, "y": 200},
        "size": {"width": 1000, "height": 800},
        "pid": 0,
        "window_fingerprint": "",
        "save_order": 1,
    }
    window.update(overrides)
    path = _positions(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"saved_at": "2026-01-01T00:00:00+01:00",
                                "windows": [window]}), encoding="utf-8")
    return path


@pytest.mark.allow_subprocess
def test_the_project_fallback_finds_the_window_it_was_written_for(
        script, stubs, tmp_path):
    """The branch that had never matched anything.

    Everything is arranged so that ONLY this fallback can succeed: the
    saved pid is 0 (strategy 1 out), the current title differs from the
    saved one (strategy 2 out), the fingerprint is empty (strategy 3
    out), the initial title is empty (strategy 3b out) and the current
    window is a thousand pixels wider than the saved one, which is
    twenty times strategy 4's tolerance.

    So the window is positioned if and only if `startswith(<project> [)`
    works - and it could not, because the shell pasted the project name
    into jq's source with a `\\[` in it, which is not a valid JSON
    escape. jq stopped at "Invalid escape at line 1, column 4", printed
    nothing, and the loop silently found no address.
    """
    home = tmp_path / "home"
    home.mkdir(parents=True)
    _saved(home)
    _clients(tmp_path, [_window(
        address="0xbeef", **{"class": "jetbrains-idea"},
        title="myproj [~/src/myproj] – Other.rs",
        initialTitle="", size=[2000, 1600], pid=9999)])

    result = _run(script, ["load"], stubs, home, tmp_path)

    output = result.stdout + result.stderr
    assert "jq: error" not in output, output
    assert "Invalid escape" not in output, output
    moved = [line for line in _calls(tmp_path, "hyprctl")
             if "movewindowpixel" in line]
    assert moved, (
        "no window was positioned - the fallback found nothing:\n" + output)
    assert "exact 100 200" in moved[0], moved
    assert "address:0xbeef" in moved[0], moved


@pytest.mark.allow_subprocess
def test_a_project_name_with_a_quote_in_it_is_a_name_not_a_program(
        script, stubs, tmp_path):
    """The other end of the same defect.

    A value pasted into jq's source is jq CODE. A project directory may
    be called anything at all, and the name below closes the string and
    opens a second expression. What it must do is match nothing; what it
    must not do is make jq run something else, or fail.
    """
    home = tmp_path / "home"
    home.mkdir(parents=True)
    _saved(home, title='ev"il [~/src/x] – Main.rs')
    _clients(tmp_path, [_window(
        address="0xbeef", **{"class": "jetbrains-idea"},
        title="myproj [~/src/myproj] – Other.rs",
        initialTitle="", size=[2000, 1600], pid=9999)])

    result = _run(script, ["load"], stubs, home, tmp_path)

    output = result.stdout + result.stderr
    assert "jq: error" not in output, output
    assert "syntax error" not in output, output
    # Nothing matches that project, so nothing may be moved onto it.
    assert not [line for line in _calls(tmp_path, "hyprctl")
                if "movewindowpixel" in line], output


@pytest.mark.allow_subprocess
def test_a_terminal_is_found_by_its_initial_title(script, stubs, tmp_path):
    """The strategy next door, which failed for a third reason.

    `.title | contains($x) or .initialTitle == $x` binds the pipe more
    weakly than the `or`, so `.initialTitle` was looked up ON THE TITLE
    STRING whenever contains() was not already true - "Cannot index
    string with initialTitle", and the whole call produced nothing.
    """
    home = tmp_path / "home"
    home.mkdir(parents=True)
    _saved(home, **{"class": "kitty"}, title="an old title",
           initial_title="Notizen", window_fingerprint="",
           size={"width": 1000, "height": 800})
    _clients(tmp_path, [_window(
        address="0xcafe", **{"class": "kitty"}, title="vim",
        initialTitle="Notizen", size=[2000, 1600], pid=9999)])

    result = _run(script, ["load"], stubs, home, tmp_path)

    output = result.stdout + result.stderr
    assert "Cannot index string" not in output, output
    moved = [line for line in _calls(tmp_path, "hyprctl")
             if "movewindowpixel" in line]
    assert moved, "the terminal was never found:\n" + output
    assert "address:0xcafe" in moved[0], moved


@pytest.mark.allow_subprocess
def test_a_saved_title_with_quotes_still_matches_its_window(script, stubs,
                                                            tmp_path):
    """Save and load, end to end, over the title that broke the writer."""
    home = tmp_path / "home"
    _clients(tmp_path, [_window(address="0xdead")])

    _run(script, ["save", "all"], stubs, home, tmp_path)
    result = _run(script, ["load"], stubs, home, tmp_path)

    output = result.stdout + result.stderr
    assert "jq: error" not in output, output
    moved = [line for line in _calls(tmp_path, "hyprctl")
             if "movewindowpixel" in line]
    assert moved, "the window was saved and then not found again:\n" + output
    assert "address:0xdead" in moved[0], moved
