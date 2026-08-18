# SPDX-License-Identifier: GPL-3.0-or-later
"""restore-latest-backup, executed rather than read.

This is the tool validate_output.py points at when it explains why a
backup is written at all - "so a bad generation can be undone". It was
also the one tool in the safety story that could not work for anybody
but its author: `CONFIG_PATH` was an absolute path into that author's
own home directory, and six more like it. Run on any other machine it
printed "Config file not found" and exited 1 while the backup it was
reaching for sat right there.

A string assertion cannot show that this is fixed. "the template no
longer names that home directory" would have been just as green over a
path built from $USER, from `getent`, or from a $HOME that the generator does
not write to - and each of those finds nothing on a machine whose
XDG_CONFIG_HOME points somewhere else. So the template is generated into
tmp_path, a config and two backups are put into a sandbox HOME, and the
tool is run.

Safety, the same argument as in test_network_watchdog.py: every child is
started through `env -i` with PATH set to the stub directory and nothing
else, asserted before each run, so a command with no stub fails with
"command not found" instead of reaching the real one. `hyprctl` and
`pkill` are recording stubs - a test must not reload the compositor of
the machine it runs on, nor kill its bar. The text tools the script
parses with (`ls`, `stat`, `head`, `cut`, `dirname`, `basename`, `diff`,
`date`) exec their real binaries, and so does `cp`: proving that the
restore actually replaces the file is the point of this file, and every
path it is handed lies inside tmp_path, because the sandbox HOME and
XDG_CONFIG_HOME are what the tool derives them from.
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

TEMPLATE = "restore-latest-backup-config"

BROKEN = "the generation that has to be undone\n"
NEWEST = "the good one\n"
OLDER = "an older backup that must not win\n"

# Read-only text tools plus `cp`, which is the one that writes and the
# one whose effect is being measured.
REAL_TOOLS = ("ls", "stat", "head", "cut", "dirname", "basename", "diff",
              "date", "cp")

# Never real, under any circumstances: they act on the machine running
# the tests rather than on the sandbox.
FAKE_TOOLS = ("hyprctl", "ags", "sleep")


@pytest.fixture
def generate(tmp_path, monkeypatch):
    """The template, processed exactly as the generator processes it."""
    monkeypatch.syspath_prepend(str(SRC))
    import template_processor

    processor = template_processor.ConfigProcessor()
    script = tmp_path / "restore-latest-backup"
    processor.apply_template(SRC / "templates" / f"{TEMPLATE}.template", script)
    script.chmod(0o755)
    return script


@pytest.fixture
def stubs(tmp_path):
    """The stub directory and the transcript the fake tools write into."""
    directory = tmp_path / "stubs"
    directory.mkdir()
    calls = tmp_path / "calls.txt"

    for name in FAKE_TOOLS:
        assert name not in REAL_TOOLS
        stub = directory / name
        stub.write_text(
            "#!/bin/bash\n"
            "# Test stub. Records the call; never reaches the real command.\n"
            f"printf '{name} %s\\n' \"$*\" >> '{calls}'\n"
            "exit 0\n",
            encoding="utf-8")
        stub.chmod(0o755)

    for name in REAL_TOOLS:
        assert name not in FAKE_TOOLS, f"{name} must never reach its real binary"
        real = shutil.which(name)
        assert real, f"the restore tool needs {name}"
        stub = directory / name
        stub.write_text(f'#!/bin/bash\nexec "{real}" "$@"\n', encoding="utf-8")
        stub.chmod(0o755)

    return directory, calls


def _child_path(directory: Path) -> str:
    """The PATH the child gets - the stub directory and nothing else."""
    path = str(directory)
    assert path.split(os.pathsep) == [path]
    assert not os.environ.get("PATH", "").startswith(path), (
        "the stub directory must not be part of the parent's PATH either")
    return path


def run_tool(script: Path, argv, directory: Path, home: Path,
             xdg: Path | None, answer: str) -> subprocess.CompletedProcess:
    """Run the generated tool with nothing but HOME - and maybe
    XDG_CONFIG_HOME - to find its way with."""
    environment = [f"PATH={_child_path(directory)}", f"HOME={home}"]
    if xdg is not None:
        environment.append(f"XDG_CONFIG_HOME={xdg}")
    result = subprocess.run(
        [ENV, "-i", *environment, BASH, str(script), *argv],
        env={},
        input=answer,
        capture_output=True,
        text=True,
        timeout=60,
    )
    conftest.assert_no_missing_command(result, "the restore tool")
    return result


def place_config(config_home: Path, relative: str) -> Path:
    """A generated config with an older and a newer backup beside it.

    The two backups differ in content AND in modification time, because
    the tool picks with `ls -t`: identical timestamps would let either
    one win and the test would pass by luck half the time.
    """
    target = config_home / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(BROKEN, encoding="utf-8")

    older = target.with_name(target.name + ".backup.2026-01-01-000000")
    older.write_text(OLDER, encoding="utf-8")
    os.utime(older, (1_760_000_000, 1_760_000_000))

    newest = target.with_name(target.name + ".backup.2026-02-02-000000")
    newest.write_text(NEWEST, encoding="utf-8")
    os.utime(newest, (1_770_000_000, 1_770_000_000))

    return target


def safety_backups(target: Path) -> list[Path]:
    return sorted(target.parent.glob(target.name + ".before-restore.*"))


# --------------------------------------------------------------------
# the tool has to work for somebody who is not its author
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_it_restores_the_latest_backup_below_xdg_config_home(
        generate, stubs, tmp_path):
    """The whole point, measured on the file's content.

    XDG_CONFIG_HOME is set to a directory that is NOT $HOME/.config, so a
    tool that fell back to the home directory would find nothing here -
    which is the same failure as the hardcoded path, one layer further
    in. generate_config.sh:30 writes its output to exactly this
    directory, so this is where the file to be restored lives.
    """
    directory, calls = stubs
    home = tmp_path / "home"
    xdg = tmp_path / "xdg"
    target = place_config(xdg, "hypr/hyprland.conf")

    result = run_tool(generate, ["hyprland"], directory, home, xdg, "y\n")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "not found" not in result.stdout, result.stdout
    assert target.read_text() == NEWEST, (
        "the backup was not restored over the broken generation")
    backups = safety_backups(target)
    assert len(backups) == 1, [p.name for p in backups]
    assert backups[0].read_text() == BROKEN, (
        "the file being replaced was not kept - an undo of the undo is "
        "the only thing standing between a wrong answer and lost work")
    assert "Restore complete" in result.stdout
    assert calls.read_text(encoding="utf-8").splitlines() == ["hyprctl reload"], (
        "the compositor is reloaded, and nothing else is touched")


@pytest.mark.allow_subprocess
def test_it_falls_back_to_the_home_config_when_xdg_is_unset(
        generate, stubs, tmp_path):
    """Without XDG_CONFIG_HOME the answer must be $HOME/.config - the
    same fallback generate_config.sh:30 uses, so both halves name the
    same file on a machine that sets neither."""
    directory, _ = stubs
    home = tmp_path / "home"
    target = place_config(home / ".config", "ags/bar.css")

    result = run_tool(generate, ["bar"], directory, home, None, "y\n")

    assert result.returncode == 0, result.stdout + result.stderr
    assert target.read_text() == NEWEST
    assert str(home) in result.stdout, (
        "the tool has to name the file it actually worked on")


@pytest.mark.allow_subprocess
@pytest.mark.parametrize(
    "name, relative",
    [("hyprland", "hypr/hyprland.conf"),
     ("bar", "ags/bar.css"),
     ("kitty", "kitty/kitty.conf")],
)
def test_every_config_it_offers_can_be_restored(
        generate, stubs, tmp_path, name, relative):
    """All three, because all three carried the same hardcoded home and
    a fix that reached only the first one would look identical in a diff
    read quickly."""
    directory, _ = stubs
    home = tmp_path / "home"
    xdg = tmp_path / "xdg"
    target = place_config(xdg, relative)

    result = run_tool(generate, [name], directory, home, xdg, "y\n")

    assert result.returncode == 0, result.stdout + result.stderr
    assert target.read_text() == NEWEST


@pytest.mark.allow_subprocess
def test_declining_changes_nothing(generate, stubs, tmp_path):
    """The confirmation is the last chance to keep a file that is only
    suspected of being broken."""
    directory, calls = stubs
    home = tmp_path / "home"
    xdg = tmp_path / "xdg"
    target = place_config(xdg, "hypr/hyprland.conf")

    result = run_tool(generate, ["hyprland"], directory, home, xdg, "n\n")

    assert result.returncode == 0, result.stdout + result.stderr
    assert target.read_text() == BROKEN, "the config was replaced anyway"
    assert safety_backups(target) == []
    assert not calls.exists(), "nothing may be restarted after a decline"


@pytest.mark.allow_subprocess
def test_a_missing_backup_is_reported_without_touching_the_config(
        generate, stubs, tmp_path):
    """The message that used to appear for the wrong reason.

    "No backups found" is the honest answer when there are none. Before
    the fix the user got "Config file not found" instead, over a config
    that was there and a backup that was there too.
    """
    directory, _ = stubs
    home = tmp_path / "home"
    xdg = tmp_path / "xdg"
    target = xdg / "hypr" / "hyprland.conf"
    target.parent.mkdir(parents=True)
    target.write_text(BROKEN, encoding="utf-8")

    result = run_tool(generate, ["hyprland"], directory, home, xdg, "")

    assert result.returncode == 1
    assert "No backups found" in result.stdout, result.stdout
    assert "Config file not found" not in result.stdout, result.stdout
    assert target.read_text() == BROKEN


@pytest.mark.allow_subprocess
def test_the_usage_names_the_paths_this_machine_would_use(
        generate, stubs, tmp_path):
    """The usage text was the most visible copy of the hardcoded path:
    three lines offering to restore a file in somebody else's home. It
    has to name the directory the tool would really work in, or it sends
    the reader looking in the wrong place."""
    directory, _ = stubs
    home = tmp_path / "home"
    xdg = tmp_path / "xdg"

    result = run_tool(generate, [], directory, home, xdg, "")

    assert result.returncode == 1
    for relative in ("hypr/hyprland.conf", "ags/bar.css",
                     "kitty/kitty.conf"):
        assert f"{xdg}/{relative}" in result.stdout, result.stdout


@pytest.mark.allow_subprocess
def test_an_unknown_config_name_is_refused(generate, stubs, tmp_path):
    directory, _ = stubs
    home = tmp_path / "home"
    xdg = tmp_path / "xdg"

    result = run_tool(generate, ["nonsense"], directory, home, xdg, "")

    assert result.returncode == 1
    assert "Unknown config" in result.stdout, result.stdout
