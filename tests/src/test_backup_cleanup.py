# SPDX-License-Identifier: GPL-3.0-or-later
"""The deleter, executed against files that are really there.

backup-cleanup.sh walks the directories the generator publishes into,
keeps the newest `*.backup.*` OF EACH FILE and offers to delete the older
generations. Both halves of that sentence used to read differently: the
default search root was `/`, and what it kept was the single newest
backup on the machine.

WHAT IT IS FOR, WHICH IS WHAT DECIDES BOTH
    validate_output.py copies "<file>.backup.<date>" beside every file it
    replaces, and restore-latest-backup takes the newest backup OF THE
    FILE it is restoring. A sweep that keeps one backup in total
    therefore leaves every config but one with nothing to restore, and a
    sweep that starts at `/` offers to delete `*.backup.*` files that
    belong to editors, package managers and other people's scripts, on
    every filesystem the account can read.

    The tests below pin both: which files survive a run, and which
    directories a run with no argument is willing to look in.

It also announced how many files it had removed by subtracting one from
the number it had found - not by looking at what was still on disk.

That arithmetic was wrong wherever a path contained a space, which is
where the whole pipeline came apart:

    find ... -printf '%T@ %p\n' | ... | cut -d' ' -f2- | xargs rm -f

`cut` keeps everything after the first space, so the timestamp goes and
the path survives; `xargs` then splits that path on every space in it.
Measured on `dir one/My Config.conf.backup.20260101`: `rm -f` was handed
three fragments, none of which is a file, the backup was STILL THERE
afterwards, and the script printed "Done! Deleted 1 backups." The
fragments were relative, too - `one/My` - so they were resolved against
whatever directory the user happened to be standing in.

The tests below therefore assert on the FILESYSTEM and on the number the
script says out loud, never on one alone: a count that matches a
deletion that did not happen is the defect.

Safety: every child runs through `env -i` with the stub directory as the
ONLY entry on PATH, and `rm` is the real one because deleting is what is
being measured - it can reach nothing but the test's own tmp_path, which
is the only tree the script is ever pointed at.
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

# Everything this script uses. All of them read and write only where the
# script points them, and it is only ever pointed inside tmp_path.
PASSTHROUGH = ("find", "sort", "uniq", "rm", "cat", "head", "tail", "wc",
               "dirname", "cut", "xargs")


@pytest.fixture
def script(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(SRC))
    import template_processor

    output = tmp_path / "backup-cleanup.sh"
    template_processor.ConfigProcessor().apply_template(
        SRC / "templates" / "backup-cleanup-config.template", output)
    output.chmod(0o755)
    return output


@pytest.fixture
def stubs(tmp_path):
    directory = tmp_path / "stubs"
    directory.mkdir()
    for name in PASSTHROUGH:
        real = shutil.which(name)
        assert real, f"the script needs {name}"
        # The absolute path: with the stub directory as the whole of
        # PATH, `exec find "$@"` would find this stub again.
        assert real.startswith("/")
        stub = directory / name
        stub.write_text(f'#!/bin/bash\nexec "{real}" "$@"\n', encoding="utf-8")
        stub.chmod(0o755)
    return directory


def _run(script: Path, search_dir: Path | None, stubs: Path,
         answer: str = "y", cwd: Path | None = None,
         home: Path | None = None) -> subprocess.CompletedProcess:
    """One run. `search_dir` None means "no argument", which is the case
    the default search roots decide - and those come from HOME and
    XDG_CONFIG_HOME, so both are set for every run rather than left to
    leak in from the machine running the tests."""
    path = str(stubs)
    assert path.split(os.pathsep) == [str(stubs)]
    assert not os.environ.get("PATH", "").startswith(path)
    home = home if home is not None else stubs.parent / "unused-home"
    home.mkdir(parents=True, exist_ok=True)
    arguments = [] if search_dir is None else [str(search_dir)]
    result = subprocess.run(
        [ENV, "-i", f"PATH={path}", f"HOME={home}",
         f"XDG_CONFIG_HOME={home}/.config",
         BASH, str(script), *arguments],
        env={}, input=answer + "\n", capture_output=True, text=True,
        timeout=60, cwd=str(cwd) if cwd else None)
    conftest.assert_no_missing_command(result, "the cleanup script")
    return result


def _backups(root: Path, *names_with_ages) -> list[Path]:
    """Backup files, oldest first, each a second older than the next."""
    created = []
    for index, name in enumerate(names_with_ages):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"content of {name}", encoding="utf-8")
        os.utime(path, (1_000_000 + index, 1_000_000 + index))
        created.append(path)
    return created


# --------------------------------------------------------------------
# what it deletes
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_a_backup_whose_path_holds_a_space_is_actually_deleted(script, stubs,
                                                               tmp_path):
    """The defect, in the two halves it has: nothing deleted, success
    reported.

    Two generations of ONE file, because that is the pair the tool is
    now allowed to choose between - and the space is in the directory
    name, so it is in the path of both of them either way.
    """
    tree = tmp_path / "tree"
    old, newest = _backups(
        tree,
        "dir one/My Config.conf.backup.20260101",
        "dir one/My Config.conf.backup.20260201")

    result = _run(script, tree, stubs)

    assert result.returncode == 0, result.stdout + result.stderr
    assert not old.exists(), (
        "the backup the script said it deleted is still there:\n"
        + result.stdout)
    assert newest.exists(), "the newest backup must be kept"
    assert "Deleted 1 backups" in result.stdout, result.stdout


# --------------------------------------------------------------------
# what it keeps
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_the_newest_backup_of_every_file_survives(script, stubs, tmp_path):
    """The whole point of the tool, and what it used to get wrong.

    restore-latest-backup restores "<file>.backup.*" for ONE file at a
    time. Keeping the single newest backup on the machine therefore left
    every other config with nothing to restore - measured here on three
    configs with two generations each: the old rule kept one file out of
    six and deleted the current backup of the other two.
    """
    tree = tmp_path / "tree"
    hypr_old, hypr_new, way_old, way_new, kitty_old, kitty_new = _backups(
        tree,
        "hypr/hyprland.conf.backup.2026-01-01-000000",
        "hypr/hyprland.conf.backup.2026-02-01-000000",
        "ags/bar.css.backup.2026-01-02-000000",
        "ags/bar.css.backup.2026-02-02-000000",
        "kitty/kitty.conf.backup.2026-01-03-000000",
        "kitty/kitty.conf.backup.2026-02-03-000000")

    result = _run(script, tree, stubs)

    assert result.returncode == 0, result.stdout + result.stderr
    for survivor in (hypr_new, way_new, kitty_new):
        assert survivor.exists(), (
            f"{survivor.name} is the only backup of its file left:\n"
            + result.stdout)
    for gone in (hypr_old, way_old, kitty_old):
        assert not gone.exists(), f"{gone.name} was superseded and kept"
    assert "Deleted 3 backups" in result.stdout, result.stdout


@pytest.mark.allow_subprocess
def test_a_file_with_one_backup_is_left_alone_however_old_it_is(script, stubs,
                                                                tmp_path):
    """Age decides nothing on its own - being superseded does.

    The oldest file here is the only backup its config has, and the newest
    is one of a pair. Sorting the whole tree by time and keeping the head
    of the list deleted exactly the wrong one.
    """
    tree = tmp_path / "tree"
    lonely, superseded, newest = _backups(
        tree,
        "hypr/hyprland.conf.backup.2026-01-01-000000",
        "kitty/kitty.conf.backup.2026-02-01-000000",
        "kitty/kitty.conf.backup.2026-03-01-000000")

    result = _run(script, tree, stubs)

    assert lonely.exists(), (
        "the oldest file was the only backup of its config:\n"
        + result.stdout)
    assert newest.exists()
    assert not superseded.exists()


@pytest.mark.allow_subprocess
def test_the_count_it_reports_is_the_count_it_reached(script, stubs, tmp_path):
    """Reported, not calculated.

    "found minus one" is right only if every deletion succeeded, and the
    whole point of the previous defect is that they did not. A file the
    script cannot remove has to lower the number it announces.
    """
    tree = tmp_path / "tree"
    _backups(tree,
             "a b/one.conf.backup.20260101",
             "a b/one.conf.backup.20260102",
             "a b/one.conf.backup.20260103")
    # Removing a file needs write permission on its DIRECTORY, so the
    # unremovable one gets a directory of its own - and a newer sibling,
    # or it would be the only backup of its file and never a candidate.
    locked = tree / "locked"
    _backups(locked,
             "four.conf.backup.20260102",
             "four.conf.backup.20260103")
    locked.chmod(0o500)
    try:
        result = _run(script, tree, stubs)
    finally:
        locked.chmod(0o700)

    assert "Deleted 2 backups" in result.stdout, (
        "the script counted files it could not remove:\n" + result.stdout)
    assert (locked / "four.conf.backup.20260102").exists()
    assert "Could not delete" in result.stdout + result.stderr, (
        "nothing said which file survived")


@pytest.mark.allow_subprocess
def test_declining_deletes_nothing(script, stubs, tmp_path):
    """The prompt is the only thing between this and a whole filesystem."""
    tree = tmp_path / "tree"
    old, newest = _backups(tree, "one file.conf.backup.20260101",
                           "one file.conf.backup.20260102")

    result = _run(script, tree, stubs, answer="n")

    assert old.exists() and newest.exists(), result.stdout
    assert "Cancelled" in result.stdout


@pytest.mark.allow_subprocess
def test_nothing_outside_the_search_directory_is_touched(script, stubs,
                                                         tmp_path):
    """Where the split fragments used to land.

    `xargs` was handed relative pieces like "one/My", and `rm -f`
    resolves those against the CURRENT directory. The run below stands in
    a directory that holds exactly such a name, so a fragment aimed at it
    would delete it.
    """
    tree = tmp_path / "tree"
    _backups(tree, "dir one/My Config.conf.backup.20260101",
             "dir one/My Config.conf.backup.20260201")

    elsewhere = tmp_path / "elsewhere"
    bait = elsewhere / "dir one" / "My Config.conf.backup.20260101"
    bait.parent.mkdir(parents=True)
    bait.write_text("not the script's business", encoding="utf-8")

    result = _run(script, tree, stubs, cwd=elsewhere)

    assert "Deleted 1 backups" in result.stdout, (
        "nothing was deleted at all, so nothing was aimed anywhere:\n"
        + result.stdout)
    assert bait.exists(), (
        "a fragment resolved against the working directory deleted a file "
        "outside the search root")


@pytest.mark.allow_subprocess
def test_an_empty_tree_says_so_and_stops(script, stubs, tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()

    result = _run(script, tree, stubs)

    assert result.returncode == 0
    assert "No backup files found" in result.stdout


@pytest.mark.allow_subprocess
def test_a_single_backup_is_kept(script, stubs, tmp_path):
    tree = tmp_path / "tree"
    only, = _backups(tree, "the one.conf.backup.20260101")

    result = _run(script, tree, stubs)

    assert only.exists()
    assert "Nothing to delete" in result.stdout


# --------------------------------------------------------------------
# where it looks when nobody says
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_with_no_argument_it_searches_where_the_generator_writes(script,
                                                                 stubs,
                                                                 tmp_path):
    """The default used to be `/`.

    Everything below is inside one temporary HOME, so the run can be
    measured without pointing anything at a real filesystem - which is
    also the point: a default of `/` cannot be tested at all without
    walking the machine the tests run on.

    ~/.zshrc is generated straight into HOME, so HOME itself has to be
    searched; everything BELOW it is the user's own and must not be.
    """
    home = tmp_path / "home"
    # _backups makes each file a second newer than the one before it, so
    # the second of every pair below is the one that has to survive.
    superseded, kept = _backups(
        home,
        ".config/hypr/hyprland.conf.backup.2026-01-01-000000",
        ".config/hypr/hyprland.conf.backup.2026-02-01-000000")

    zshrc_old, zshrc_new = _backups(home, ".zshrc.backup.2026-01-01-000000",
                                    ".zshrc.backup.2026-02-01-000000")
    own_old, own_new = _backups(
        home,
        "Dokumente/Steuer.ods.backup.2026-01-01-000000",
        "Dokumente/Steuer.ods.backup.2026-02-01-000000")

    result = _run(script, None, stubs, home=home)

    assert result.returncode == 0, result.stdout + result.stderr
    assert kept.exists() and not superseded.exists(), (
        "the published configuration was not searched:\n" + result.stdout)
    assert zshrc_new.exists() and not zshrc_old.exists(), (
        "HOME itself holds ~/.zshrc and was not searched:\n" + result.stdout)
    assert own_old.exists() and own_new.exists(), (
        "a file of the user's own, two directories down, was swept up:\n"
        + result.stdout)


@pytest.mark.allow_subprocess
def test_a_file_found_through_two_search_roots_is_counted_once(script, stubs,
                                                               tmp_path):
    """The zepos root normally sits INSIDE XDG_CONFIG_HOME, so both roots
    find the same file. Counted twice, the second sighting is "an older
    generation of itself" - and the newest backup of that file gets
    deleted by the rule that exists to keep it."""
    home = tmp_path / "home"
    only, = _backups(home, ".config/zepos/helpers/x.sh.backup.2026-01-01-000000")

    result = _run(script, None, stubs, home=home)

    assert only.exists(), (
        "the only backup of this file was deleted as its own duplicate:\n"
        + result.stdout)
    assert "Found 1 backup files" in result.stdout, result.stdout
