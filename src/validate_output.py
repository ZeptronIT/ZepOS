#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check generated configuration before it replaces the working one, and
then put it in place one file at a time.

The generator used to write straight into the live configuration. A run
that aborted halfway left a broken hyprland.conf behind, which is a
desktop that does not start - discovered from a TTY, with no obvious way
back. generate_config.sh now generates into a staging area, calls `check`
on it, and only calls `publish` when nothing was found.

WHY FILES AND NOT A DIRECTORY
    The obvious version of this is "generate into a temp directory and
    move the directory into place". It destroys data here, because the
    generator does not own a single one of the directories it writes
    into. ~/.config/hypr alone holds

      monitors.conf       written by the settings application
      workspaces.conf     written by save-profile
      current-profile     written by the profile scripts
      emergency-backups/  written by emergency-reset.sh
      *.backup.<date>     every backup this program itself took

    and whatever else the user put there. None of it comes from a
    template, the monitor layout is not regenerable from anything in this
    tree, and replacing the directory deletes all of it - including, in
    the last line, the backups that exist so a bad generation can be
    undone.

    So the staging area mirrors absolute paths - <stage>/files/<path
    without its leading slash> - and publish() moves the files one by one
    with os.replace(). It touches exactly the paths ZepOS generated and
    removes nothing else.

WHAT IS ATOMIC, AND WHAT IS NOT
    os.replace() is atomic per file: a reader sees either the whole old
    file or the whole new one, never a truncated one, and never a missing
    one. And no file is published at all unless every file in the run
    passed the checks.

    The run as a whole is NOT atomic. A run killed between two
    os.replace() calls leaves some files new and some old. That is a mix
    of individually valid files rather than one half-written file, which
    is a different class of problem, and it is as far as this can go
    without replacing directories - which is exactly the thing that would
    delete the files listed above.

WHAT WAS ALREADY GUARANTEED, AND IS NOT REDONE HERE
    template_processor.apply_template() raises UnresolvedPlaceholders
    BEFORE it writes anything, so a template referencing something no
    SSOT defines fails without touching the previous file. That is per
    FILE and it stays where it is; the checks here are per RUN.

    The placeholder check below is not a second copy of it. The processor
    collects the placeholders BEFORE substituting, so a value that itself
    contains {{...}} is substituted in and never looked at again - the
    file is written and success is reported over it. That is the case
    this catches.

WHAT IS DELIBERATELY NOT CHECKED
    Python artifacts are not compiled. Six templates generate Python, and
    py_compile would catch a syntax error in them - but a Waybar module
    that fails to compile leaves one field of the bar empty, while a
    hyprland.conf that fails to parse leaves no session at all. The four
    checks here are the ones whose failure costs the user their desktop.
"""
from __future__ import annotations

import errno
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")

# `plugin = <value>` at the start of a line, in Hyprland's own syntax.
# [ \t] rather than \s so the leading run cannot cross a line ending and
# the match covers the one line it appears to.
PLUGIN_LINE = re.compile(r"^[ \t]*plugin[ \t]*=[ \t]*(\S+)", re.MULTILINE)

# Marks a directory as one this program built. `check` walks every file
# below what it is given, so it must be impossible to point at a home
# directory by passing the wrong argument.
STAGE_MARKER = ".zepos-stage"

# Where the mirrored tree lives inside a staging area.
STAGE_FILES = "files"

# The name restore-latest-backup and backup-cleanup both glob for. A
# backup under any other name is invisible to the tool the user is told
# to reach for.
BACKUP_SUFFIX = ".backup.%Y-%m-%d-%H%M%S"

# JSON that Waybar and AGS read. ".jsonc" is Waybar's config, and it has
# to be in here: generate_config.sh runs jq over that very file to merge
# the workspace list in, and jq rejects comments, so strict JSON is
# already a hard requirement for it.
JSON_SUFFIXES = (".json", ".jsonc")

# Only Hyprland configuration is searched for plugin lines. A shell
# script that PRINTS such a line - a recovery helper writing a config
# with a heredoc - has not loaded anything.
HYPRLAND_SUFFIXES = (".conf",)

Runner = Callable[..., "subprocess.CompletedProcess"]


def validate(directory: Path, *, runner: Runner | None = None) -> list[str]:
    """Everything wrong with the generated tree, one finding per line.

    An empty list means the tree may be published.

    Paths in the findings are relative to `directory`, which for a real
    run is <stage>/files - so the text names both the file the user can
    open and, with a leading slash, the place it would have gone.

    `runner` exists so unit tests can exercise the plumbing without
    spawning anything; the default is a real `bash -n`.
    """
    runner = runner or subprocess.run
    findings: list[str] = []

    for path in sorted(directory.rglob("*")):
        # is_file() follows symlinks, and following one would take the
        # check outside the staging area. Nothing generated is a symlink.
        if path.is_symlink() or not path.is_file():
            continue

        where = path.relative_to(directory)
        data = path.read_bytes()
        if b"\x00" in data:
            # A binary artifact. There is no text in it to check, and
            # decoding it would only raise.
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue

        for match in PLACEHOLDER.finditer(text):
            findings.append(f"{where}: unresolved placeholder {match.group(1)}")

        if path.suffix in JSON_SUFFIXES:
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                findings.append(f"{where}: invalid JSON ({exc.msg}, line {exc.lineno})")

        if _is_bash(path, text):
            result = runner(
                ["bash", "-n", str(path)], capture_output=True, text=True
            )
            if result.returncode != 0:
                findings.append(
                    f"{where}: shell syntax error ({_first_line(result, path)})")

        if path.suffix in HYPRLAND_SUFFIXES:
            findings.extend(_plugin_findings(where, text))

    return findings


def _first_line(result, path: Path) -> str:
    """bash's own complaint, without the path it repeats back.

    bash prefixes every message with the file it was handed, which here
    is the long staging path. The finding already names the file, and a
    message the user has to read twice to find the useful half is a
    message they stop reading.
    """
    lines = (result.stderr or "").strip().splitlines()
    if not lines:
        return "bash -n failed"
    prefix = f"{path}: "
    return lines[0][len(prefix):] if lines[0].startswith(prefix) else lines[0]


def _is_bash(path: Path, text: str) -> bool:
    """Whether `bash -n` is the right question for this file.

    The suffix alone is not enough: start-hyprland, save-profile,
    printer-manager and floating-window-manager all land in ~/.local/bin under a
    bare name, and one of them starts the session.

    ~/.zshrc has neither a .sh suffix nor a shebang, which is what keeps
    it out - bash -n would report zsh's own syntax as an error.
    """
    return path.suffix == ".sh" or text.startswith(("#!/bin/bash", "#!/usr/bin/env bash"))


def _plugin_findings(where: Path, text: str) -> list[str]:
    """Plugin lines whose object can be shown to be absent.

    WHAT THIS CATCHES, now that it can catch anything
        For as long as plugins were loaded by hyprpm, no template in this
        tree wrote a `plugin =` line at all and this function could not
        produce a finding on any input the generator was able to make.
        plugins.py writes absolute paths - `plugin =
        /usr/lib/hyprland/plugins/hyprzones.so` - so the shape exists
        now, and the route that reaches this check is a USER OVERRIDE: a
        copied template naming an object that is not on the machine.
        Refusing the run leaves the working configuration in place;
        publishing it would have cost the session at the next login.

        plugins.py's own output cannot fail here by construction - it
        writes a line only for an object it has just found - which is
        exactly what makes this the check for the lines it did NOT write.

    Only absolute paths are answered. The two other shapes are left alone
    on purpose:

      * A bare name - `plugin = hyprbars` - is what hyprpm took. Nothing
        in this project produces one any more, but a configuration
        carried over from a hyprpm installation still can, and there is
        no path to check: hyprpm kept the built object under a directory
        name derived from the Hyprland revision it built against.

      * A relative path resolves against the CURRENT WORKING DIRECTORY,
        which is wherever the user happened to stand when they ran the
        generator - so the same config would be called broken or fine
        depending on the shell's cwd.

    A check that reports a missing plugin for a line that is fine gets
    switched off by the first user it inconveniences, which would take
    the other three checks with it.
    """
    findings = []
    for match in PLUGIN_LINE.finditer(text):
        value = match.group(1)
        if not value.startswith("/"):
            continue
        if not Path(value).is_file():
            findings.append(f"{where}: plugin object missing: {value}")
    return findings


# --------------------------------------------------------------------
# publishing
# --------------------------------------------------------------------

def files_root(stage: Path) -> Path:
    return stage / STAGE_FILES


def target_of(root: Path, staged: Path) -> Path:
    """The absolute path a staged file belongs at.

    The mirror is lexical in both directions: <stage>/files/etc/x is
    /etc/x. relative_to() raises if the staged path is not below the
    mirror, which is the only way this could name something else.
    """
    return Path("/") / staged.relative_to(root)


def staged_files(stage: Path) -> list[Path]:
    root = files_root(stage)
    return sorted(
        path for path in root.rglob("*")
        if not path.is_symlink() and path.is_file()
    )


class PublishFailed(Exception):
    """A move failed after other files were already in place.

    Carries both halves, because the caller needs both: what is already
    the new version, and what is still staged. This is the run-level
    non-atomicity described in the module header - made visible at the
    one moment it can actually happen, rather than left for the user to
    work out from a traceback.
    """

    def __init__(self, target: Path, written: list[Path]):
        super().__init__(f"could not put {target} in place")
        self.target = target
        self.written = written


def publish(stage: Path) -> list[Path]:
    """Move every staged file to its target. Returns the targets written.

    Each move is a rename, so a target is never seen half-written, and
    the file it replaces is copied aside first. Nothing is deleted: a
    directory keeps everything in it that this run did not generate.
    """
    root = files_root(stage)
    stamp = datetime.now().strftime(BACKUP_SUFFIX)
    written: list[Path] = []

    for staged in staged_files(stage):
        target = target_of(root, staged)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_file() and _changes(staged, target):
                # Taken here rather than before generation: a run that
                # fails replaces nothing, and so has nothing to back up.
                # Taken beforehand, every failed run left another copy of
                # the same working config in the user's directory.
                shutil.copy2(target, target.with_name(target.name + stamp))
            _replace(staged, target)
        except OSError as exc:
            raise PublishFailed(target, written) from exc
        written.append(target)

    return written


def _changes(staged: Path, target: Path) -> bool:
    """Ob dieser Schritt ueberhaupt etwas an der Datei aendert.

    WORAN DAS GEMESSEN WURDE
        Am 11.08.2026 lag auf einer FRISCH installierten Maschine, nach
        genau einer Anmeldung, im erzeugten Widget-Verzeichnis eine Datei
        namens `Bar.tsx.backup.2026-08-11-200947`. Der Zeitstempel ist
        derselbe Login.

        Der Weg dorthin: zepos-session ruft bei der ersten Anmeldung
        `zepos-generate --all`, das schreibt Bar.tsx. Danach ruft
        start-hyprland `hyprland-status generate`, und das erzeugt zwoelf
        Vorlagen noch einmal - ags-bar darunter. Beim zweiten Mal steht
        die Datei schon da, also wird sie beiseitegelegt. Fuenfzehn
        Sicherungskopien auf einer Installation, die noch nie jemand
        benutzt hat, jede eine Kopie einer Datei, die drei Sekunden
        vorher derselbe Login geschrieben hatte.

    WARUM DIE ANTWORT NICHT "DER ZWEITE LAUF ENTFAELLT" IST
        Weil er einen Grund hat: hyprland-status erzeugt die Konfigura-
        tion FUER EIN PROFIL, und ein Profilwechsel muss dieselben
        zwoelf Dateien neu schreiben. Der zweite Lauf zu streichen hiesse,
        den Profilwechsel zu streichen.

        Die Frage ist nicht, wie oft erzeugt wird, sondern wofuer eine
        Sicherungskopie da ist. validate_output sagt es im Kopf selbst:
        "so a bad generation can be undone". Ein Lauf, der Byte fuer Byte
        dasselbe schreibt, was schon dasteht, KANN nicht schlecht sein -
        und die Kopie, die er hinterlaesst, ist eine Kopie einer Datei,
        die unveraendert daneben liegt. Sie kostet Platz, sie macht das
        Verzeichnis unlesbar, und wenn spaeter wirklich etwas schiefgeht,
        steht die Kopie, die man braucht, zwischen fuenfzehn, die nichts
        sagen.

    Was sich AENDERT, wird weiterhin gesichert - das ist der ganze
    Unterschied, und tests/src/test_generate.py misst beide Richtungen.
    """
    try:
        return staged.read_bytes() != target.read_bytes()
    except OSError:
        # Nicht lesbar heisst nicht "gleich". Im Zweifel wird gesichert:
        # eine ueberfluessige Kopie ist Unordnung, eine fehlende ist der
        # Datenverlust, den diese Funktion verhindern soll.
        return True


def _replace(staged: Path, target: Path) -> None:
    """os.replace(), including across a filesystem boundary.

    os.replace() is the whole point - it is the only way to put a file in
    place without a moment in which the target is truncated - but it
    cannot cross filesystems. XDG_CACHE_HOME and XDG_CONFIG_HOME may well
    be on different ones, so the fallback copies next to the TARGET first
    and renames from there, which is a rename within one filesystem
    again.
    """
    try:
        os.replace(staged, target)
        return
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise

    beside = target.with_name(f".{target.name}.zepos-{os.getpid()}")
    try:
        shutil.copy2(staged, beside)
        os.replace(beside, target)
    finally:
        # A no-op after a successful replace; the point is the failing
        # case, which must not leave a half-copied dotfile behind.
        beside.unlink(missing_ok=True)


# --------------------------------------------------------------------
# command line, used by generate_config.sh
# --------------------------------------------------------------------

def _is_stage(stage: Path) -> bool:
    """Whether this directory is one new_stage() built.

    Both halves of this program walk everything below what they are
    given, and publish() moves what it finds to the matching absolute
    path. Handed the wrong directory - a home directory, a checkout -
    that is not a mistake anyone recovers from, so the marker file is
    checked rather than assumed.
    """
    if not (stage / STAGE_MARKER).is_file():
        print(f"{stage} is not a ZepOS staging directory (no {STAGE_MARKER} "
              "in it)", file=sys.stderr)
        return False
    if not files_root(stage).is_dir():
        print(f"{files_root(stage)} does not exist", file=sys.stderr)
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2 or argv[0] not in ("check", "publish"):
        print(f"usage: {Path(__file__).name} check|publish <stage-directory>",
              file=sys.stderr)
        return 2

    command, argument = argv
    stage = Path(argument)
    if not _is_stage(stage):
        return 2

    if command == "check":
        findings = validate(files_root(stage))
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1 if findings else 0

    try:
        publish(stage)
    except PublishFailed as exc:
        # The one place the run-level limit becomes visible to a user.
        # Saying which files are already the new version, and where the
        # rest still are, is the difference between a recoverable state
        # and an unexplained one.
        print(f"{exc}: {exc.__cause__}", file=sys.stderr)
        print(f"{len(exc.written)} file(s) had already been written and are "
              f"the new version. The rest are still in {files_root(stage)}.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
