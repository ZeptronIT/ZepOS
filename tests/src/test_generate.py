# SPDX-License-Identifier: GPL-3.0-or-later
"""A generation run is all-or-nothing, and it removes nothing it did not write.

Two hazards, and the second is the larger one.

FIRST: the generator wrote straight into the live configuration. A run
that died halfway left a half-written hyprland.conf behind - a desktop
that does not start, from a TTY, with no obvious way back. Generating
into a staging area, checking it, and only then putting the files in
place turns that into a failed run with the working configuration still
in place.

SECOND, and the reason the staging area is a set of files rather than a
directory: the generator does not OWN any of the directories it writes
into. ~/.config/hypr holds monitors.conf, which the settings application
writes; workspaces.conf, which save-profile writes; current-profile;
emergency-backups/; and every timestamped backup an earlier run left
behind. None of those come from a template. "Generate into a temp
directory and move the directory into place" would delete every one of
them, which is a worse failure than the one it fixes - the monitor layout
is not regenerable, and the backups are what the user would have restored
from.

So the tests below prove both halves: nothing broken is ever published,
and nothing foreign is ever removed - after a good run AND after a failed
one.

WHAT IS ATOMIC, precisely
    Each file individually. os.replace() either put the whole new file
    there or left the whole old one. No file is ever seen half-written,
    and no file is published at all unless every file in the run passed
    the checks.

WHAT IS NOT
    The run as a whole. A run killed between two os.replace() calls
    leaves some files new and some old. That is a mix of individually
    valid files, not a truncated one, and it is as far as this can go
    without replacing directories - which is exactly what would delete
    the files above.
"""
import ast
import errno
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

# Anchored on this file, the way every other test in this directory does
# it. src/ has no __init__.py and its modules import each other flatly,
# so `from src.validate_output import validate` cannot work: the first
# `from paths import ...` inside a sibling module would fail.
SRC = Path(__file__).resolve().parents[2] / "src"

# Named absolutely, so finding the interpreter never depends on PATH.
BASH = "/bin/bash"


@pytest.fixture
def validator(monkeypatch):
    monkeypatch.syspath_prepend(str(SRC))
    import validate_output

    return validate_output


def fake_runner(returncode: int = 0, stderr: str = "", record: list | None = None):
    """A stand-in for subprocess.run.

    The isolation guard blocks real processes, and it is right to: a unit
    test has no business spawning anything. The one test that genuinely
    needs a real `bash -n` says so with a marker, further down. Every
    other test here injects this, which also lets it assert which files
    the shell check was and was not asked about.
    """

    def run(argv, **kwargs):
        if record is not None:
            record.append(list(argv))
        return subprocess.CompletedProcess(argv, returncode, "", stderr)

    return run


# --------------------------------------------------------------------
# validate(): what it checks
# --------------------------------------------------------------------

def test_clean_output_has_no_findings(validator, tmp_path):
    (tmp_path / "hyprland.conf").write_text("monitor=,preferred,auto,1\n")
    (tmp_path / "config.jsonc").write_text(json.dumps({"layer": "top"}))
    (tmp_path / "helper.sh").write_text("#!/bin/bash\necho ok\n")

    assert validator.validate(tmp_path, runner=fake_runner()) == []


def test_an_unresolved_placeholder_is_reported(validator, tmp_path):
    """A surviving {{...}} means a template referenced something the SSOT
    does not define. Shipping it writes a literal {{ICON_FOO}} into the
    user's bar."""
    (tmp_path / "hyprland.conf").write_text("bar_text = {{ICON_MISSING}}\n")

    findings = validator.validate(tmp_path, runner=fake_runner())

    assert any("ICON_MISSING" in f for f in findings), findings
    assert any("hyprland.conf" in f for f in findings), findings


def test_a_placeholder_a_substituted_value_brought_in_is_reported(
        validator, monkeypatch, tmp_path):
    """What the run-level check adds over the per-file one.

    template_processor already raises UnresolvedPlaceholders BEFORE writing, so
    an ordinary {{ICON_FOO}} nobody defined never reaches the disk and
    the previous file is left alone (tests/src/test_placeholders.py).
    That guard is not reimplemented here.

    It collects the placeholders before substituting, though. A value
    that itself contains {{...}} is substituted in and never looked at
    again: the file is written and the run reports success over it. That
    is the hole this check covers, and it is the reason the check is not
    redundant.
    """
    monkeypatch.syspath_prepend(str(SRC))
    import template_processor

    template = tmp_path / "looping.template"
    template.write_text("color: {{STYLE_LOOPS}};\n")
    written = tmp_path / "out" / "style.css"
    written.parent.mkdir()

    template_processor.ConfigProcessor(
        styles={"STYLE_LOOPS": "{{ICON_ARROW}}"}
    ).apply_template(template, written)

    assert "{{ICON_ARROW}}" in written.read_text(), (
        "the processor resolved it after all - this test no longer shows a hole")

    findings = validator.validate(written.parent, runner=fake_runner())
    assert any("ICON_ARROW" in f for f in findings), findings


def test_a_dotfile_is_walked_like_any_other(validator, tmp_path):
    """~/.zshrc is one of the generated targets, and it is a dotfile.

    A shell glob skips those. If the walk did too, the login shell would
    be the one file never checked, and nothing would look wrong.
    """
    (tmp_path / ".zshrc").write_text("export PROMPT={{STYLE_MISSING}}\n")

    findings = validator.validate(tmp_path, runner=fake_runner())

    assert any(".zshrc" in f for f in findings), findings


def test_a_finding_names_the_file_it_came_from(validator, tmp_path):
    """The message has to lead the user to one file out of seventy-seven."""
    nested = tmp_path / "home" / "u" / ".config" / "ags"
    nested.mkdir(parents=True)
    (nested / "bar.css").write_text("color: {{STYLE_MISSING}};\n")

    findings = validator.validate(tmp_path, runner=fake_runner())

    assert findings, "nothing reported at all"
    assert "home/u/.config/ags/bar.css" in findings[0], findings


@pytest.mark.parametrize("name", ["config.json", "config.jsonc"])
def test_broken_json_is_reported(validator, tmp_path, name):
    """.jsonc is in here because that is what Waybar's config is called.

    Checking only ".json" would have skipped the one JSON file the whole
    bar depends on. Waybar's own parser tolerates comments; jq, which
    generate_config.sh runs over this very file to merge the workspace
    list in, does not - so strict JSON is already a hard requirement for
    it, and this check does not add one.
    """
    (tmp_path / name).write_text('{"layer": "top",}')

    findings = validator.validate(tmp_path, runner=fake_runner())

    assert any(name in f for f in findings), findings


def test_a_broken_shell_script_is_reported(validator, tmp_path):
    (tmp_path / "helper.sh").write_text("#!/bin/bash\nif [ -z ; then\n")

    findings = validator.validate(
        tmp_path, runner=fake_runner(2, "helper.sh: line 2: syntax error\n"))

    assert any("helper.sh" in f for f in findings), findings
    assert any("syntax error" in f for f in findings), findings


def test_a_shell_script_without_the_suffix_is_still_checked(validator, tmp_path):
    """Half the generated scripts have no .sh at all.

    start-hyprland, save-profile, printer-manager and waybar-launcher all
    land in ~/.local/bin under a bare name. A suffix-only rule would have
    checked none of them - including the one that starts the session.
    """
    asked = []
    (tmp_path / "start-hyprland").write_text("#!/bin/bash\necho ok\n")
    (tmp_path / "hardware-monitor.py").write_text("#!/usr/bin/env python3\nx = (\n")
    (tmp_path / ".zshrc").write_text("autoload -Uz compinit\n")

    validator.validate(tmp_path, runner=fake_runner(record=asked))

    checked = {Path(argv[-1]).name for argv in asked}
    assert "start-hyprland" in checked, "the session starter is never checked"
    assert "hardware-monitor.py" not in checked, "a python script is not bash"
    assert ".zshrc" not in checked, (
        "~/.zshrc is zsh; bash -n would report its own syntax as an error")


def test_a_binary_file_is_skipped_rather_than_decoded(validator, tmp_path):
    """A staging tree can hold a wallpaper or an icon. Reading it as text
    raises; reading it at all is pointless."""
    (tmp_path / "picture.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

    assert validator.validate(tmp_path, runner=fake_runner()) == []


def test_a_directory_that_is_not_a_staging_area_is_refused(validator, tmp_path):
    """The CLI walks every file under what it is given.

    Pointed at a home directory it would read all of it. The marker file
    is what makes "this is a staging area we just built" checkable rather
    than assumed.
    """
    assert validator.main(["check", str(tmp_path)]) != 0


# --------------------------------------------------------------------
# validate(): what it deliberately does not check
# --------------------------------------------------------------------

def test_a_plugin_named_without_a_path_is_not_reported(validator, tmp_path):
    """A bare name cannot be resolved, so it is not answered.

    This is the shape hyprpm took, and a configuration carried over from
    a hyprpm installation still carries it: hyprpm kept the built object
    in its own directory, under a name derived from the Hyprland revision
    it built against, so a bare name cannot be turned into a path from
    here without guessing.

    Guessing wrong means reporting a missing plugin for a line that is
    fine, on every single run, which is how a check gets switched off.
    What this project generates is the shape that CAN be answered - see
    src/plugins.py, which writes absolute paths.
    """
    (tmp_path / "hyprland.conf").write_text("plugin = hyprbars\n")

    assert validator.validate(tmp_path, runner=fake_runner()) == []


def test_a_plugin_line_inside_a_shell_script_is_not_reported(validator, tmp_path):
    """A script that PRINTS such a line has not loaded anything."""
    (tmp_path / "recover.sh").write_text(
        "#!/bin/bash\ncat > ~/.config/hypr/x.conf <<EOF\n"
        "plugin = /usr/lib/hyprland/plugins/absent.so\nEOF\n")

    assert validator.validate(tmp_path, runner=fake_runner()) == []


def test_a_plugin_line_naming_an_absent_object_is_reported(validator, tmp_path):
    """The one plugin shape that CAN be resolved: an absolute path.

    Hyprland refuses to load a plugin whose .so is absent, and refusing
    is fatal to the config it is in. src/plugins.py writes such lines,
    and only for objects it has just found - so the case this reaches is
    the one it did NOT write: a user override naming an object that is
    not on the machine. tests/src/test_plugins.py drives that route
    through the real generator.
    """
    (tmp_path / "hyprland.conf").write_text(
        "plugin = /usr/lib/hyprland/plugins/absent.so\n")

    findings = validator.validate(tmp_path, runner=fake_runner())

    assert any("absent.so" in f for f in findings), findings


def test_an_existing_plugin_object_is_accepted(validator, tmp_path):
    plugin = tmp_path / "present.so"
    plugin.write_bytes(b"\x7fELF")
    (tmp_path / "hyprland.conf").write_text(f"plugin = {plugin}\n")

    assert validator.validate(tmp_path, runner=fake_runner()) == []


def test_a_relative_plugin_path_is_not_measured_against_the_working_directory(
        validator, tmp_path, monkeypatch):
    """`Path("plugins/x.so").is_file()` asks about the CURRENT directory.

    The generator is run from wherever the user happens to stand, so the
    same config would be reported broken or fine depending on the shell's
    cwd. A relative path is therefore not resolvable here either, and is
    left alone rather than answered wrongly.
    """
    (tmp_path / "hyprland.conf").write_text("plugin = plugins/relative.so\n")

    monkeypatch.chdir(tmp_path)
    assert validator.validate(tmp_path, runner=fake_runner()) == []


# --------------------------------------------------------------------
# the shell check, against a real bash
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_the_default_runner_is_a_real_bash_syntax_check(validator, tmp_path):
    """The fake above proves the plumbing, not the check.

    Whether `bash -n` actually rejects what the generator can produce is
    a fact about bash, and the only way to establish it is to run bash.
    This is the one test here that is allowed to, and it is why the
    marker is on this test and not on the others.
    """
    good = tmp_path / "good" / "helper.sh"
    good.parent.mkdir()
    good.write_text("#!/bin/bash\nfor i in 1 2; do echo $i; done\n")
    assert validator.validate(good.parent) == []

    bad = tmp_path / "bad" / "helper.sh"
    bad.parent.mkdir()
    bad.write_text("#!/bin/bash\nif [ -z ; then\n")
    findings = validator.validate(bad.parent)
    assert any("helper.sh" in f for f in findings), findings


# --------------------------------------------------------------------
# publish(): moving the files, and only the files
# --------------------------------------------------------------------

def _stage(root: Path, targets: dict[Path, str]) -> Path:
    """Build a staging area the way generate_config.sh builds one."""
    stage = root / "stage"
    (stage / "files").mkdir(parents=True)
    (stage / ".zepos-stage").write_text("")
    for target, text in targets.items():
        staged = stage / "files" / str(target).lstrip("/")
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_text(text)
    return stage


def test_publish_moves_every_staged_file_to_its_target(validator, tmp_path):
    first = tmp_path / "config" / "hypr" / "hyprland.conf"
    second = tmp_path / "config" / "ags" / "widget" / "Bar.tsx"
    stage = _stage(tmp_path, {first: "the new one\n", second: "{}\n"})

    validator.publish(stage)

    assert first.read_text() == "the new one\n"
    assert second.read_text() == "{}\n"


def test_publish_leaves_the_files_zepos_did_not_write_alone(validator, tmp_path):
    """The data-loss case, at the smallest scale it can be shown.

    monitors.conf comes from the settings application and is not regenerable
    from anything in this tree. workspaces.conf comes from save-profile.
    The third is a timestamped backup an earlier run left behind - what
    the user would restore from. Moving a directory into place removes
    all three.
    """
    hypr = tmp_path / "config" / "hypr"
    hypr.mkdir(parents=True)
    foreign = {
        "monitors.conf": "monitor=DP-1,3440x1440@100,0x0,1\n",
        "workspaces.conf": "workspace=1,monitor:DP-1\n",
        "workspaces-generated.conf.backup-2026-01-01-120000": "older\n",
    }
    for name, text in foreign.items():
        (hypr / name).write_text(text)

    stage = _stage(tmp_path, {hypr / "hyprland.conf": "the new one\n"})
    validator.publish(stage)

    assert (hypr / "hyprland.conf").read_text() == "the new one\n"
    for name, text in foreign.items():
        assert (hypr / name).read_text() == text, f"{name} was changed"


def test_publish_moves_a_dotfile_too(validator, tmp_path):
    """~/.zshrc, again: staged like the rest, and it has to be moved too."""
    target = tmp_path / "home" / ".zshrc"
    stage = _stage(tmp_path, {target: "the new one\n"})

    validator.publish(stage)

    assert target.read_text() == "the new one\n"


def test_publish_backs_up_what_it_replaces(validator, tmp_path):
    """And under the name the restore tool globs for.

    restore-latest-backup and backup-cleanup both look for
    "<file>.backup.*". A backup under any other name is invisible to the
    tool the user is told to reach for.
    """
    target = tmp_path / "config" / "kitty" / "kitty.conf"
    target.parent.mkdir(parents=True)
    target.write_text("the one that worked\n")

    stage = _stage(tmp_path, {target: "the new one\n"})
    validator.publish(stage)

    backups = list(target.parent.glob("kitty.conf.backup.*"))
    assert len(backups) == 1, backups
    assert backups[0].read_text() == "the one that worked\n", (
        "the backup holds the NEW file - it was taken after the replacement")
    assert target.read_text() == "the new one\n"


def test_publish_does_not_back_up_a_file_that_was_not_there(validator, tmp_path):
    target = tmp_path / "config" / "kitty" / "kitty.conf"
    stage = _stage(tmp_path, {target: "the first one\n"})

    validator.publish(stage)

    assert list(target.parent.glob("*.backup.*")) == []


def test_publish_survives_a_filesystem_boundary(validator, tmp_path, monkeypatch):
    """The staging area and the output are not necessarily on one disk.

    The staging area lives under XDG_CACHE_HOME and the output under
    XDG_CONFIG_HOME, and os.replace() cannot cross a filesystem. The
    fallback copies BESIDE the target and renames from there, so the move
    onto the target is still a rename within one filesystem - still
    atomic, and still leaving everything else in the directory alone.
    """
    target = tmp_path / "config" / "hypr" / "hyprland.conf"
    target.parent.mkdir(parents=True)
    target.write_text("the one that worked\n")
    (target.parent / "monitors.conf").write_text("from the GUI\n")
    stage = _stage(tmp_path, {target: "the new one\n"})

    real_replace = os.replace
    refused = []

    def replace(source, destination, **kwargs):
        # Only the move OUT of the staging area is refused. The rename
        # beside the target has to go through, or the fallback is being
        # bypassed rather than exercised.
        if not refused:
            refused.append(source)
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return real_replace(source, destination, **kwargs)

    monkeypatch.setattr(os, "replace", replace)
    validator.publish(stage)

    assert refused, "the fallback was never reached"
    assert target.read_text() == "the new one\n"
    assert (target.parent / "monitors.conf").read_text() == "from the GUI\n"
    strays = [p.name for p in target.parent.iterdir() if p.name.startswith(".")]
    assert strays == [], f"the fallback left its own temporary file behind: {strays}"


def test_a_move_that_fails_says_what_is_already_in_place(validator, tmp_path):
    """The run-level limit, at the moment it becomes visible.

    Moving the files one by one means a failure in the middle leaves some
    targets new and some old. Each of them is a whole file - that is what
    os.replace() buys - but the user has to be told which is which, or
    they are left guessing at a configuration that is half updated.
    """
    first = tmp_path / "config" / "a" / "first.conf"
    second = tmp_path / "config" / "b" / "second.conf"
    stage = _stage(tmp_path, {first: "new first\n", second: "new second\n"})

    # A directory where the second file's target has to be a file.
    second.parent.mkdir(parents=True)
    second.mkdir()

    assert validator.main(["publish", str(stage)]) == 1
    assert first.read_text() == "new first\n", "the first move was rolled back"
    assert second.is_dir(), "the second target was replaced after all"
    assert (stage / "files" / str(second).lstrip("/")).is_file(), (
        "the file that could not be moved is no longer inspectable")


def test_publish_keeps_the_executable_bit(validator, tmp_path):
    """start-hyprland that is not executable is a session that cannot start."""
    target = tmp_path / "bin" / "start-hyprland"
    stage = _stage(tmp_path, {target: "#!/bin/bash\necho ok\n"})
    (stage / "files" / str(target).lstrip("/")).chmod(0o755)

    validator.publish(stage)

    assert os.access(target, os.X_OK)


# --------------------------------------------------------------------
# the generator, run for real
# --------------------------------------------------------------------

# Commands that act on the RUNNING desktop session, not on a file.
# generate_config.sh reaches for these after a successful --all run, and
# HOME cannot redirect any of them: `pkill -f "gjs.*ags"` finds the
# developer's own shell whatever HOME says. Measured, not theorised - an
# intermediate state of this task ran that line and killed the AGS
# session of the machine the tests were running on.
#
# hyprctl is on this list because the generator reaches it INDIRECTLY,
# which is why it was missing: the bar-workspace-detect-config branch runs
# bar-workspace-detect.sh, which runs `python3 monitors.py --bar`,
# whose detect() runs `hyprctl monitors -j` against whatever compositor
# is actually running. Nothing in the list is written down twice, so the
# test below derives it from the source instead of trusting this comment.
# "waybar" und "nohup" standen hier und sind am 11.08.2026 entfallen: die
# Verzweigung, die `pkill -x waybar; nohup waybar` ausfuehrte, gibt es
# nicht mehr. Beide bleiben absichtlich im VOKABULAR darunter stehen -
# damit ein Rueckfall auf waybar diesen Test umwirft statt unbemerkt zu
# bleiben, und zwar mit der Meldung, dass er einen Stub braucht.
SESSION_COMMANDS = (
    "ags", "pkill", "pgrep", "systemctl", "dbus-send", "setsid", "kitty",
    "hyprctl",
)

# Every name that reaches the running session, the compositor, the bar or
# the notification daemon. Deliberately wider than SESSION_COMMANDS: this
# is the vocabulary the check looks FOR, and a name here that the
# generator never mentions simply never comes up.
SESSION_VOCABULARY = (
    "ags", "pkill", "pgrep", "killall", "systemctl", "dbus-send", "setsid",
    "kitty", "waybar", "nohup", "hyprctl", "hyprpm", "swaybg", "swaync",
    "nmcli", "notify-send", "zepos-menu", "gsettings", "loginctl", "udevadm",
)

# What a generation run can execute besides itself. The workspace-detect
# script is generated from its template and then run by its own
# post-generation branch; monitors.py is what that script calls; plugins.py is what the
# -hyprland-plugins-config branch calls to resolve the plugin include
# against the objects on the machine.
_EXECUTED_BY_A_RUN = (
    ("generate_config.sh", "shell"),
    ("templates/bar-workspace-detect-config.template", "shell"),
    ("monitors.py", "python"),
    ("plugins.py", "python"),
)

_SHELL_COMMENT = re.compile(r"(?m)^\s*#.*$")
_DOUBLE_QUOTED = re.compile(r'"(?:[^"\\]|\\.)*"')
_SINGLE_QUOTED = re.compile(r"'(?:[^'\\]|\\.)*'")
_PYTHON_COMMENT = re.compile(r"(?m)#.*$")


def _prose_removed(text: str) -> str:
    """A Python module with its comments and docstrings taken out.

    The same treatment the shell branch already gives its files, for the
    same reason: a name inside prose is not an invocation of it.
    src/plugins.py's header explains at length why this project no longer
    loads plugins with hyprpm, and the raw scan read that explanation as
    a call to hyprpm - which would have been answered either by putting a
    stub in SESSION_COMMANDS for a command no run can reach, or by
    deleting the reason from the module that replaced it.

    DOCSTRINGS ONLY, never every string literal. A Python invocation IS a
    string constant - subprocess.run(["hyprctl", "monitors", "-j"]) - so
    stripping strings the way the shell branch strips quotes would blind
    this to the one shape it exists to find.
    """
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            documentation = ast.get_docstring(node, clean=False)
            if documentation:
                text = text.replace(documentation, " ")
    return _PYTHON_COMMENT.sub(" ", text)


def test_every_session_command_the_run_can_reach_is_stubbed():
    """SESSION_COMMANDS, derived instead of trusted.

    The list is the entire reason these tests may run the real generator
    on a developer's machine, and nothing checked it against the
    generator. It was wrong: `hyprctl` was absent while the bar branch
    reached it through two intermediate scripts, so a run that took that
    branch asked the DEVELOPER's compositor for its monitors - which is
    both a test whose result depends on the desk it runs at, and a
    command one flag away from reconfiguring that desk.

    Read from the source, so a new call site is a failed test rather than
    a discovery. Comments and quoted strings are stripped first: the
    generator says "Run 'hyprctl reload' to reload Hyprland config" in a
    message and stops mako through `systemctl --user stop mako.service`,
    and neither is an invocation of the name inside it.

    Over-inclusive by design - a name mentioned in a way this cannot tell
    apart from a call demands a stub it may not need, which costs one
    no-op file. The opposite mistake costs a killed session.
    """
    reachable = {}
    for relative, kind in _EXECUTED_BY_A_RUN:
        path = SRC / relative
        text = path.read_text(encoding="utf-8")
        if kind == "shell":
            text = _SINGLE_QUOTED.sub(" ", _DOUBLE_QUOTED.sub(
                " ", _SHELL_COMMENT.sub(" ", text)))
        else:
            text = _prose_removed(text)
        for name in SESSION_VOCABULARY:
            if re.search(rf"(?<![\w./-]){re.escape(name)}(?![\w.-])", text):
                reachable.setdefault(name, []).append(relative)

    # A scan that matched nothing would also report nothing missing.
    #
    # Sieben, nicht acht: mit der Waybar-Verzweigung sind `waybar`,
    # `nohup` und `kitty` aus dem Generator verschwunden - der Log-Betrachter,
    # den er nach jeder Erzeugung oeffnete, war die einzige Stelle, die
    # kitty aufrief.
    assert len(reachable) >= 7, (
        f"only {sorted(reachable)} found - the scan is not reading the "
        "generator, so its result means nothing")

    missing = {name: files for name, files in reachable.items()
               if name not in SESSION_COMMANDS}
    assert missing == {}, (
        "these reach the running session and have no stub, so the tests "
        "below run them against the developer's own desktop: "
        + "; ".join(f"{name} (in {', '.join(files)})"
                    for name, files in sorted(missing.items())))


# A generated artifact that puts a system directory on its own PATH
# reaches past whatever PATH it was started with. Two files are allowed
# to, for reasons that are about the file rather than about the rule.
PATH_WIDENING_ALLOWED = {
    # A login shell configuration. Assembling the user's PATH is the
    # entire job of the file; it is not run under a stub directory, and a
    # rule forbidding it here would be a rule against zsh.
    "zshrc-config.template",
    # Guarded, and asserted to stay guarded by
    # tests/src/test_floating_windows.py: the widening happens only when
    # hyprctl or jq cannot be found at all, which is the state a bar
    # module or a keybind can genuinely start in.
    "floating-window-manager.template",
}

SYSTEM_DIRECTORIES = ("/usr/bin", "/usr/sbin", "/usr/local/bin", "/bin",
                      "/sbin")


def test_no_generated_artifact_quietly_widens_its_own_path():
    """The other way a stub directory stops isolating anything.

    Every harness in this suite starts its child with `env -i` and a
    stub-only PATH, and rests on "a command nobody stubbed cannot reach
    the real one". A script that adds /usr/bin to its own PATH breaks
    that silently and completely: stubbed commands are still found in the
    stub directory, so nothing looks wrong, while every UNSTUBBED command
    runs the real binary on the machine the tests are on. There is no
    message, because the command was found.

    Measured on floating-window-manager.template, which reached the real
    /usr/bin/hyprctl of the developer's own session under a harness whose
    docstring said it could not.

    A denylist of directories rather than of forms: `PATH=$PATH:/usr/bin`
    and `PATH="${PATH}":/usr/bin` and an `export` on a later line all do
    the same thing, and the thing they have in common is the literal.
    """
    offenders = []
    scanned = 0
    for path in sorted((SRC / "templates").glob("*.template")):
        scanned += 1
        if path.name in PATH_WIDENING_ALLOWED:
            continue
        for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#") or "PATH=" not in stripped:
                continue
            if any(directory in stripped for directory in SYSTEM_DIRECTORIES):
                offenders.append(f"{path.name}:{number}: {stripped}")

    assert scanned > 50, (
        f"only {scanned} templates scanned - the guard is reading nothing")
    assert offenders == [], (
        "these put a system directory on their own PATH, which defeats "
        "every stub directory they are ever run under: "
        + "; ".join(offenders))


def test_the_exemptions_above_are_still_files_that_need_one():
    """An exemption that outlives its reason is a permanent hole.

    Both entries are exempted because of something they contain. When
    that stops being true the exemption has to go, and nobody has any
    reason to notice unless this says so.
    """
    stale = []
    for name in sorted(PATH_WIDENING_ALLOWED):
        path = SRC / "templates" / name
        assert path.is_file(), f"{name} is gone - remove it from the list"
        text = path.read_text(encoding="utf-8")
        if not any(directory in text for directory in SYSTEM_DIRECTORIES):
            stale.append(name)
    assert stale == [], (
        f"{stale} no longer widens PATH - remove it from "
        "PATH_WIDENING_ALLOWED")


@pytest.fixture
def run_generator(tmp_path):
    """Run src/generate_config.sh with every root it knows inside tmp_path.

    HOME, XDG_CONFIG_HOME and XDG_CACHE_HOME are all redirected, because
    the script derives the output root, ~/.local/bin and the staging area
    from them. A test that got any one of them wrong would write into the
    developer's live desktop configuration - the isolation guard cannot
    see into a subprocess, so the redirection has to be right here.

    The generator needs a real PATH - python3, jq, mktemp, date - so the
    stub directory is PREPENDED rather than made the whole of it, and it
    holds one no-op for each command that would touch the running
    session. Redirecting HOME is not enough for those, and "this test
    cannot reach that code path" is an argument, not a guarantee.
    """
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True)
    (home / ".cache").mkdir()
    assert tmp_path in home.parents or home.parent == tmp_path

    stubs = tmp_path / "session-stubs"
    stubs.mkdir()
    for name in SESSION_COMMANDS:
        stub = stubs / name
        # dbus-send answers the name the script waits for. Without it the
        # wait loop spends five seconds failing to find a session bus
        # that is not there, in a test about files.
        body = ('printf "org.freedesktop.Notifications\\n"\n'
                if name == "dbus-send" else "")
        stub.write_text(f'#!/bin/bash\necho "stub: {name} $*" >&2\n{body}exit 0\n')
        stub.chmod(0o755)
    path = os.pathsep.join([str(stubs), os.environ["PATH"]])
    for name in SESSION_COMMANDS:
        assert shutil.which(name, path=path) == str(stubs / name), (
            f"{name} would reach the real command")

    def run(*arguments, system_root: Path = SRC, user_root: Path | None = None,
            stage: Path | None = None, script: Path | str | None = None,
            cwd: Path | None = None,
            extra_environment: dict[str, str] | None = None,
            ) -> subprocess.CompletedProcess:
        """`script` and `cwd` exist for the recursion tests below.

        generate_config.sh calls itself for every template in a --all
        run, and how it names itself when it does is the whole question
        there: it used $0, which is whatever the caller typed. Naming the
        script relatively, from a directory of the caller's choosing, is
        the only way to ask.

        `extra_environment` exists for the session tests: the environment
        above holds no WAYLAND_DISPLAY, so every branch that asks whether
        there is a screen to draw on takes the "there is none" side, and
        a test that meant to exercise the other side would pass without
        ever reaching it.
        """
        environment = {
            "PATH": path,
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "ZEPOS_SYSTEM_ROOT": str(system_root),
            "ZEPOS_USER_ROOT": str(user_root or (home / ".config" / "zepos")),
        }
        if stage is not None:
            environment["ZEPOS_STAGE_DIR"] = str(stage)
        environment.update(extra_environment or {})
        return subprocess.run(
            [BASH, str(script or (SRC / "generate_config.sh")), *arguments],
            env=environment, cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, timeout=300,
        )

    run.home = home
    run.stages = home / ".cache" / "zepos"
    # The stub directory itself, so a test can say what one of them
    # answers. A stub that always succeeds can only ever prove what
    # happens on the success side; `pkill` reporting "nothing matched" is
    # a state the generator has to behave differently in, and it is the
    # state every session start is in.
    run.stubs = stubs
    return run


@pytest.mark.allow_subprocess
def test_a_good_run_leaves_the_files_zepos_does_not_own_untouched(run_generator):
    """The same three files as above, through the real generator.

    -hyprland-universal-config writes ~/.config/hypr/hyprland.conf, into
    a directory holding three files no template produces.
    """
    hypr = run_generator.home / ".config" / "hypr"
    hypr.mkdir(parents=True)
    foreign = {
        "monitors.conf": "monitor=DP-1,3440x1440@100,0x0,1\n",
        "workspaces.conf": "workspace=1,monitor:DP-1\n",
        "workspaces-generated.conf.backup-2026-01-01-120000": "older\n",
    }
    for name, text in foreign.items():
        (hypr / name).write_text(text)

    result = run_generator("-hyprland-universal-config")

    assert result.returncode == 0, result.stdout + result.stderr
    written = (hypr / "hyprland.conf").read_text()
    assert "{{" not in written and written.strip()
    for name, text in foreign.items():
        assert (hypr / name).read_text() == text, (
            f"{name} did not survive the run")


@pytest.mark.allow_subprocess
def test_a_failed_run_publishes_nothing_and_keeps_the_staging_area(
        run_generator, tmp_path):
    """The failure path, which is the one that matters.

    The broken template is a user override, because that is a real route
    into this state and it needs no broken file in the source tree. Its
    placeholders all resolve, so the per-file guard that already exists
    (template_processor raises before writing) does not fire - what catches it
    is the run-level check.
    """
    user_root = tmp_path / "userroot"
    (user_root / "templates").mkdir(parents=True)
    broken = "#!/bin/bash\nif [ -z ; then\n"
    (user_root / "templates" / "bar-weather-config.template").write_text(broken)

    scripts = run_generator.home / ".config" / "ags" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "weather.sh").write_text("#!/bin/bash\necho the one that worked\n")
    (scripts / "notes-from-the-user.txt").write_text("keep me\n")

    result = run_generator("-bar-weather-config", user_root=user_root)
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert (scripts / "weather.sh").read_text() == (
        "#!/bin/bash\necho the one that worked\n"), "the old script was replaced"
    assert (scripts / "notes-from-the-user.txt").read_text() == "keep me\n"
    assert list(scripts.glob("*.backup.*")) == [], (
        "a run that changed nothing left a backup behind")

    stages = sorted(run_generator.stages.glob("stage-*"))
    assert len(stages) == 1, f"the staging area was not kept: {stages}"
    staged = stages[0] / "files" / str(scripts / "weather.sh").lstrip("/")
    assert staged.read_text() == broken, "the rejected output is not inspectable"

    # The wording checked here is the validator's own. bash's half of the
    # message is translated - it reads "Syntaxfehler" on the machine this
    # was written on - so asserting on that would tie the test to a locale.
    assert "weather.sh" in output, f"the message does not name the file:\n{output}"
    assert "shell syntax error" in output, f"the message does not say why:\n{output}"
    assert str(stages[0]) in output, f"the message does not say where:\n{output}"


@pytest.mark.allow_subprocess
def test_the_backup_holds_the_configuration_that_was_replaced(run_generator):
    """Taken at the moment of replacement, so it can only be the old one.

    Taken before generation instead - which is where it used to be - a
    failed run leaves a backup of a file nothing replaced, and the
    directory fills up with copies of the same working config.
    """
    kitty = run_generator.home / ".config" / "kitty"
    kitty.mkdir(parents=True)
    (kitty / "kitty.conf").write_text("the one that was there\n")

    result = run_generator("-kitty-config")

    assert result.returncode == 0, result.stdout + result.stderr
    backups = list(kitty.glob("kitty.conf.backup.*"))
    assert len(backups) == 1, backups
    assert backups[0].read_text() == "the one that was there\n"
    assert (kitty / "kitty.conf").read_text() != "the one that was there\n"


@pytest.mark.allow_subprocess
def test_a_second_run_that_writes_the_same_bytes_leaves_no_backup(run_generator):
    """Eine frische Installation braucht keine Sicherungskopien.

    GEMESSEN AM 11.08.2026 AN EINEM INSTALLIERTEN ABBILD
        Im erzeugten Widget-Verzeichnis lag
        `Bar.tsx.backup.2026-08-11-200947` - auf einer Maschine, die
        genau einmal angemeldet worden war, mit dem Zeitstempel genau
        dieser Anmeldung.

        Der Weg dorthin ist keine Panne, sondern der Normalfall: die
        erste Anmeldung ruft `zepos-generate --all` (zepos-session), und
        unmittelbar danach erzeugt start-hyprland ueber
        `hyprland-status generate` zwoelf davon noch einmal fuer das
        Profil. Beim zweiten Mal steht die Datei da, also wurde sie
        beiseitegelegt - fuenfzehn Kopien von Dateien, die drei Sekunden
        alt und unveraendert waren.

    Beide Richtungen stehen hier und in der Zusicherung darueber: was
    sich AENDERT, wird weiterhin gesichert. Nur das, was gleich bleibt,
    hinterlaesst nichts mehr. Der Grund steht bei
    validate_output._changes().
    """
    kitty = run_generator.home / ".config" / "kitty"

    first = run_generator("-kitty-config")
    assert first.returncode == 0, first.stdout + first.stderr
    written = (kitty / "kitty.conf").read_bytes()
    assert list(kitty.glob("*.backup.*")) == [], (
        "der erste Lauf hat gesichert, obwohl es nichts zu sichern gab")

    second = run_generator("-kitty-config")
    assert second.returncode == 0, second.stdout + second.stderr
    assert (kitty / "kitty.conf").read_bytes() == written, (
        "der zweite Lauf hat etwas anderes geschrieben als der erste - "
        "dann misst diese Zusicherung nicht, was sie messen soll")
    assert list(kitty.glob("*.backup.*")) == [], (
        "eine zweite Erzeugung derselben Bytes hat eine Sicherungskopie "
        "hinterlassen")


@pytest.mark.allow_subprocess
def test_a_run_that_did_not_open_the_staging_area_publishes_nothing(
        run_generator, tmp_path):
    """How --all keeps a whole run together: the children only stage.

    Each child of a --all run is handed the staging area and leaves the
    publishing to the parent, so a template that fails at number seventy
    stops the sixty-nine before it from reaching the disk.
    """
    stage = tmp_path / "stage"
    (stage / "files").mkdir(parents=True)
    (stage / ".zepos-stage").write_text("")

    result = run_generator("-kitty-config", stage=stage)

    assert result.returncode == 0, result.stdout + result.stderr
    target = run_generator.home / ".config" / "kitty" / "kitty.conf"
    assert not target.exists(), "the child published on its own"
    assert (stage / "files" / str(target).lstrip("/")).is_file()


@pytest.mark.allow_subprocess
def test_a_stage_directory_that_is_not_one_stops_the_run(run_generator, tmp_path):
    """ZEPOS_STAGE_DIR exported into a login shell would otherwise make
    every run stage into it and publish nothing - reporting success."""
    stale = tmp_path / "not-a-stage"
    stale.mkdir()

    result = run_generator("-kitty-config", stage=stale)

    assert result.returncode != 0
    assert not (run_generator.home / ".config" / "kitty" / "kitty.conf").exists()


def _two_template_system_root(tmp_path: Path, templates: dict[str, str]) -> Path:
    """A system root holding only the named templates.

    --all over the real one is seventy-seven templates and every service
    restart at the end of it. Two is enough to show that a run either
    publishes all of it or none of it.
    """
    system = tmp_path / "system"
    (system / "templates").mkdir(parents=True)
    (system / "styles").mkdir()
    for module in sorted(SRC.glob("*.py")):
        shutil.copy(module, system / module.name)
    for name, body in templates.items():
        (system / "templates" / f"{name}.template").write_text(body)
    return system


@pytest.mark.allow_subprocess
def test_a_clean_run_publishes_every_config_and_clears_the_staging_area(
        run_generator, tmp_path):
    """The success path of --all, which is the one that has to keep working.

    -hyprland-universal-config carries a post-generation step: it creates
    the placeholder files the universal config sources, and it can only
    run once the config itself is in place. Publishing the whole run
    before any of those steps is what this checks.
    """
    system = _two_template_system_root(tmp_path, {
        "kitty-config": "font_size 12\n",
        "hyprland-universal-config": "source = ~/.config/hypr/monitors.conf\n",
    })
    hypr = run_generator.home / ".config" / "hypr"
    hypr.mkdir(parents=True)
    (hypr / "monitors.conf").write_text("monitor=DP-1,3440x1440@100,0x0,1\n")

    result = run_generator("--all", system_root=system)
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert (run_generator.home / ".config" / "kitty" / "kitty.conf").read_text() == (
        "font_size 12\n")
    assert (hypr / "hyprland.conf").read_text() == (
        "source = ~/.config/hypr/monitors.conf\n")
    assert (hypr / "workspaces.conf").is_file(), (
        "the post-generation step never ran")
    assert (hypr / "monitors.conf").read_text() == (
        "monitor=DP-1,3440x1440@100,0x0,1\n"), (
        "the placeholder step overwrote the layout from the GUI")
    assert sorted(run_generator.stages.glob("stage-*")) == [], (
        "a successful run left its staging area behind")


@pytest.mark.allow_subprocess
def test_one_broken_config_stops_the_whole_run_from_being_published(
        run_generator, tmp_path):
    """Run-level, not file-level: the good config waits for the bad one.

    Two templates in a system root of their own, so the run is two files
    long instead of seventy-seven. The first generates cleanly; the
    second produces a shell script bash rejects. Neither may be
    published, and the configuration that was already there stays.
    """
    system = _two_template_system_root(tmp_path, {
        "kitty-config": "font_size 12\n",
        "bar-weather-config": "#!/bin/bash\nif [ -z ; then\n",
    })

    kitty = run_generator.home / ".config" / "kitty"
    kitty.mkdir(parents=True)
    (kitty / "kitty.conf").write_text("the one that worked\n")

    result = run_generator("--all", system_root=system)
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert (kitty / "kitty.conf").read_text() == "the one that worked\n", (
        "a config that generated cleanly was published although the run failed")
    assert not (run_generator.home / ".config" / "ags" / "scripts"
                / "weather.sh").exists()
    assert list(kitty.glob("*.backup.*")) == []

    stages = sorted(run_generator.stages.glob("stage-*"))
    assert len(stages) == 1, f"expected one staging area, got {stages}"
    assert (stages[0] / "files" / str(kitty / "kitty.conf").lstrip("/")).is_file(), (
        "the good config is not in the staging area either")


@pytest.mark.allow_subprocess
def test_a_template_that_fails_before_it_stages_anything_still_stops_the_run(
        run_generator, tmp_path):
    """The other way a config can fail, and the only one that reaches the
    run-level counter.

    The test above fails a template at VALIDATION: the file is generated,
    it lands in the staging area, the child exits 0, and what refuses it
    is publish_stage() checking the whole staged tree. fail_count is
    still zero at that moment - so `if [ $fail_count -gt 0 ]` in
    generate_all_configs() was never once exercised by it. Measured:
    turning that condition into `if false` left the entire suite green.

    A template with an undefined placeholder fails EARLIER. template_processor
    raises before writing, the child removes the half-staged file and
    exits non-zero, and nothing about the staging area is wrong
    afterwards: it holds one perfectly valid kitty.conf. So with the
    counter ignored, publish_stage() finds nothing to complain about and
    publishes - the run exits 0 and writes over a working configuration
    while one of its templates never generated at all. That is the exact
    failure the staging design exists to prevent, and it is the one the
    gate is responsible for.
    """
    system = _two_template_system_root(tmp_path, {
        "kitty-config": "font_size 12\n",
        "bar-weather-config": "#!/bin/bash\necho {{ICON_NOBODY_DEFINED}}\n",
    })

    kitty = run_generator.home / ".config" / "kitty"
    kitty.mkdir(parents=True)
    (kitty / "kitty.conf").write_text("the one that worked\n")

    result = run_generator("--all", system_root=system)
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert (kitty / "kitty.conf").read_text() == "the one that worked\n", (
        "a config that generated cleanly was published although another "
        "template never generated at all")
    assert list(kitty.glob("*.backup.*")) == [], (
        "a run that published nothing still took a backup")
    assert not (run_generator.home / ".config" / "ags" / "scripts"
                / "weather.sh").exists()

    # The staged good config is what makes the failure inspectable, and
    # what proves the run really did get as far as staging - a run that
    # fell over before it started would satisfy every assertion above.
    stages = sorted(run_generator.stages.glob("stage-*"))
    assert len(stages) == 1, f"expected one staging area, got {stages}"
    assert (stages[0] / "files" / str(kitty / "kitty.conf").lstrip("/")).is_file()

    assert "ICON_NOBODY_DEFINED" in output, (
        f"the message does not name the placeholder to define:\n{output}")


# --------------------------------------------------------------------
# the settings file the run reads
# --------------------------------------------------------------------

# A configured VPN, in the shape settings.py writes. The values are
# documentation-range and example-domain on purpose: they appear in the
# generated script and would otherwise be somebody's real gateway.
CONFIGURED_VPN = {
    "schema_version": 1,
    "vpn": {
        "server": "gw.example.org",
        "connection_name": "work",
        "routed_networks": ["10.8.0.0/24"],
        "bypass_networks": [],
        "dns": {"servers": [], "search_domain": ""},
        "test_host": "",
    },
}


@pytest.mark.allow_subprocess
def test_a_settings_file_that_cannot_be_read_stops_the_run(run_generator,
                                                           tmp_path):
    """A file that exists and cannot be read is not the same as no file.

    Every {{STYLE_*}} resolves either way - the style layer answers from
    its own defaults - so validate_output sees a syntactically perfect
    script and publishes it. The user's working VPN is replaced by a
    connect script with no server and no networks in it, over a run that
    printed a success and exited 0.

    The first half of this test is what makes the second half mean
    anything: it shows the settings really do reach the generated script,
    so the empty values after the truncation can only have come from the
    file no longer being readable.
    """
    user_root = tmp_path / "userroot"
    user_root.mkdir()
    settings_file = user_root / "user-settings.json"
    settings_file.write_text(json.dumps(CONFIGURED_VPN), encoding="utf-8")

    good = run_generator("-vpn-connect-script", user_root=user_root)
    assert good.returncode == 0, good.stdout + good.stderr

    script = (run_generator.home / ".config" / "ags" / "scripts"
              / "vpn-connect.sh")
    working = script.read_text()
    assert 'ROUTED_NETWORKS="10.8.0.0/24"' in working, working[:2000]
    assert 'VPN_SERVER="gw.example.org"' in working, working[:2000]

    # 60 bytes of what was there: the shape a killed writer leaves behind.
    settings_file.write_text(
        json.dumps(CONFIGURED_VPN)[:60], encoding="utf-8")

    result = run_generator("-vpn-connect-script", user_root=user_root)
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert script.read_text() == working, (
        "the working connect script was replaced from a settings file "
        "nothing could read")
    assert str(settings_file) in output, (
        f"the message does not name the file that is wrong:\n{output}")


@pytest.mark.allow_subprocess
def test_no_settings_file_at_all_is_not_an_error(run_generator, tmp_path):
    """A fresh installation has none, and generating the desktop must not
    depend on a file the user has never been asked to create."""
    user_root = tmp_path / "userroot"
    user_root.mkdir()
    assert not (user_root / "user-settings.json").exists()

    result = run_generator("-vpn-connect-script", user_root=user_root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (run_generator.home / ".config" / "ags" / "scripts"
            / "vpn-connect.sh").is_file()


@pytest.mark.allow_subprocess
def test_a_run_over_every_template_stops_before_it_generates_anything(
        run_generator, tmp_path):
    """The whole desktop is built from that one file, so the answer to a
    file that cannot be read is known before the first template is
    opened.

    Checked once, by the process that owns the run: without that, the
    same refusal is repeated by every template in the run - seventy-seven
    of them on a real machine - and the one line that says what to repair
    is somewhere in the middle of it.
    """
    system = _two_template_system_root(tmp_path, {
        "kitty-config": "font_size 12\n",
        "hyprland-universal-config": "source = ~/.config/hypr/monitors.conf\n",
    })
    user_root = tmp_path / "userroot"
    user_root.mkdir()
    settings_file = user_root / "user-settings.json"
    settings_file.write_text(json.dumps(CONFIGURED_VPN)[:60], encoding="utf-8")

    kitty = run_generator.home / ".config" / "kitty"
    kitty.mkdir(parents=True)
    (kitty / "kitty.conf").write_text("the one that worked\n")

    result = run_generator("--all", system_root=system, user_root=user_root)
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert (kitty / "kitty.conf").read_text() == "the one that worked\n"
    assert sorted(run_generator.stages.glob("stage-*")) == [], (
        "the run got as far as staging files it could never publish")
    assert str(settings_file) in output, (
        f"the message does not name the file that is wrong:\n{output}")


@pytest.mark.allow_subprocess
def test_one_network_written_as_a_string_stops_the_run(run_generator, tmp_path):
    """The other half of "refuse rather than guess", through the real
    generator.

    `"routed_networks": "10.8.0.0/24"` is valid JSON, so nothing about
    the FILE is wrong - only its shape. Iterated as the string it is, it
    produced eleven child security associations (work-1 to work-11) with
    a single digit or a dot as each remote_ts, and eleven `ip route add`
    targets to match, in a connect script that reported nothing unusual.
    """
    user_root = tmp_path / "userroot"
    user_root.mkdir()
    document = json.loads(json.dumps(CONFIGURED_VPN))
    document["vpn"]["routed_networks"] = "10.8.0.0/24"
    (user_root / "user-settings.json").write_text(json.dumps(document),
                                                  encoding="utf-8")

    result = run_generator("-vpn-connect-script", user_root=user_root)
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    script = (run_generator.home / ".config" / "ags" / "scripts"
              / "vpn-connect.sh")
    assert not script.exists(), (
        "a connect script was published from eleven invented networks:\n"
        + script.read_text())
    assert "routed_networks" in output, (
        f"the message does not name the setting to correct:\n{output}")
    assert str(user_root / "user-settings.json") in output, (
        f"the message does not name the file to correct:\n{output}")


# --------------------------------------------------------------------
# how the generator names things: its interpreter, and itself
# --------------------------------------------------------------------
#
# Two defects of one kind. `PYTHON_CMD="python3 $ZEPOS_SYSTEM_ROOT/..."`
# and `VALIDATE_CMD=...` are command STRINGS, and a string is only a
# command if it is expanded unquoted - which splits it on every space in
# it. `$0` is not a path: it is whatever the caller typed on the command
# line, so a relative invocation gave every recursive call a name bash
# cannot find. Neither is visible in a checkout whose path has no space
# in it, run from a directory that is not its own.

def _placeable_system_root(tmp_path: Path, where: str,
                           templates: dict[str, str]) -> Path:
    """A complete system root - the generator included - at a chosen path.

    `where` may contain a space. That is the point: a checkout under
    "/home/u/My Projects/ZepOS" is an ordinary thing for a user to make,
    and nothing in the generator may care.
    """
    system = tmp_path / where
    (system / "templates").mkdir(parents=True)
    (system / "styles").mkdir()
    for module in sorted(SRC.glob("*.py")):
        shutil.copy(module, system / module.name)
    shutil.copy(SRC / "generate_config.sh", system / "generate_config.sh")
    for name, body in templates.items():
        (system / "templates" / f"{name}.template").write_text(body)
    return system


@pytest.mark.allow_subprocess
def test_a_system_root_whose_path_holds_a_space_generates_normally(
        run_generator, tmp_path):
    """The measurement: `python3: can't open file '.../sp'`.

    The command string "python3 /home/u/sp ace/ZepOS/template_processor.py",
    expanded unquoted, is four words. python3 is handed the first piece
    as a file name, does not find it, and the generator reports
    "Generation failed" with no hint that the path is the problem.
    """
    system = _placeable_system_root(tmp_path, "sp ace", {
        "kitty-config": "font_size 12\n",
    })

    result = run_generator("-kitty-config", system_root=system,
                           script=system / "generate_config.sh")
    output = result.stdout + result.stderr

    assert "can't open file" not in output, output
    assert result.returncode == 0, output
    assert (run_generator.home / ".config" / "kitty" / "kitty.conf").read_text() \
        == "font_size 12\n"


@pytest.mark.allow_subprocess
def test_a_whole_run_from_a_path_with_a_space_publishes_everything(
        run_generator, tmp_path):
    """`--all` is where the count was: one such error per template.

    The staging area makes the run all-or-nothing, so every template
    failing the same way is one failed run - which is what a user with a
    space in their checkout path saw, ninety-eight times over, with no
    file written at all.
    """
    system = _placeable_system_root(tmp_path, "my projects", {
        "kitty-config": "font_size 12\n",
        "hyprland-universal-config": "source = ~/.config/hypr/monitors.conf\n",
    })

    result = run_generator("--all", system_root=system,
                           script=system / "generate_config.sh")
    output = result.stdout + result.stderr

    assert "can't open file" not in output, output
    assert result.returncode == 0, output
    assert (run_generator.home / ".config" / "kitty" / "kitty.conf").read_text() \
        == "font_size 12\n"
    assert (run_generator.home / ".config" / "hypr" / "hyprland.conf").is_file()


@pytest.mark.allow_subprocess
def test_a_run_started_by_a_relative_name_still_finds_itself(run_generator,
                                                             tmp_path):
    """`bash generate_config.sh --all`, standing in its own directory.

    $0 is then "generate_config.sh" - a name, not a path - and bash
    answered "generate_config.sh: command not found" for every template
    in the run. Measured over the real template directory: ninety-nine
    of them, every one counted as a failed config, so the run wrote
    nothing and the summary blamed the templates.
    """
    system = _placeable_system_root(tmp_path, "checkout", {
        "kitty-config": "font_size 12\n",
        "hyprland-universal-config": "source = ~/.config/hypr/monitors.conf\n",
    })

    result = run_generator("--all", system_root=system,
                           script="generate_config.sh", cwd=system)
    output = result.stdout + result.stderr

    assert "command not found" not in output, output
    assert result.returncode == 0, output
    assert (run_generator.home / ".config" / "kitty" / "kitty.conf").read_text() \
        == "font_size 12\n"
    assert (run_generator.home / ".config" / "hypr" / "hyprland.conf").is_file()


# --------------------------------------------------------------------
# what a generation does to the session it is generating for
# --------------------------------------------------------------------
#
# The first boot of ZepOS ended with exactly one window on the desktop:
#
#   kitty --class floating-center -e bash -c "tail -f .../waybar.log"
#
# 1200x800, floating, centred, in front of everything (evidence run
# 2026-08-05: `hyprctl clients -j` returned that one client and nothing
# else). Nobody chose it. ~/.config/waybar/waybar-launcher ran a
# complete `-waybar-config` at session start, and the branch behind it
# opened a log viewer after every generation - a development convenience
# that had become the first thing a user of the distribution sees. The
# same branch also started a bar twice per login and once with no
# compositor at all.
#
# AM 11.08.2026 IST DIESE GANZE VERZWEIGUNG WEGGEFALLEN, und mit ihr die
# drei Fehler: die Leiste ist ags/widget/Bar.tsx und wird von dem
# AGS-Prozess getragen, den ein `--all`-Lauf ganz am Ende einmal neu
# startet. Ein einzelner Lauf startet gar nichts mehr.
#
# Die Tests bleiben, weil die Zusicherung bleibt und in beide Richtungen
# nachpruefbar sein muss: eine Erzeugung schreibt Dateien und fasst die
# laufende Sitzung nicht an. Sie fragen jetzt die Stubs, denn nur die
# koennen sagen, was WIRKLICH ausgefuehrt wurde.


def _executed(result) -> list[str]:
    """Was die Stubs gemeldet haben, ein Befehl je Zeile.

    Jeder Stub in run_generator schreibt "stub: <name> <argumente>" auf
    stderr. Das ist die einzige Quelle in dieser Datei, die zwischen
    "der Generator ERWAEHNT ags" und "der Generator RUFT ags AUF"
    unterscheidet - eine Textsuche im Skript kann das nicht.
    """
    return [line.split("stub: ", 1)[1]
            for line in (result.stderr or "").splitlines()
            if "stub: " in line]


@pytest.mark.allow_subprocess
def test_generating_the_bar_opens_no_window(run_generator):
    """No terminal, no log viewer, nothing that takes the screen.

    Asserted through the stub's own report rather than by reading the
    generator: the question is what the run EXECUTES, and a line that
    merely mentions kitty is not that.
    """
    result = run_generator(
        "-ags-bar", extra_environment={"WAYLAND_DISPLAY": "wayland-1"})

    assert result.returncode == 0, result.stdout + result.stderr
    assert [command for command in _executed(result)
            if command.startswith("kitty")] == [], (
        "the run opened a terminal window:\n" + result.stderr)


@pytest.mark.allow_subprocess
def test_generating_the_bar_touches_no_running_process(run_generator):
    """Eine Erzeugung schreibt eine Datei. Sie startet nichts und sie
    beendet nichts.

    Hier stand die Gegenprobe zu `pkill -x waybar; nohup waybar`, und
    die Verzweigung gibt es nicht mehr. Die Zusicherung ist dadurch
    staerker geworden statt zu verschwinden: KEIN Sitzungsbefehl darf
    mehr fallen, nicht nur kein waybar.

    Mit Anzeigeserver in der Umgebung, weil genau der der Ausloeser war -
    die alte Verzweigung sprang nur an, wenn WAYLAND_DISPLAY gesetzt war,
    und ein Test ohne ihn haette den Fall nie erreicht.
    """
    result = run_generator(
        "-ags-bar", extra_environment={"WAYLAND_DISPLAY": "wayland-1"})

    assert result.returncode == 0, result.stdout + result.stderr
    assert _executed(result) == [], (
        "die Erzeugung der Leiste hat in die laufende Sitzung gegriffen:\n"
        + result.stderr)


@pytest.mark.allow_subprocess
def test_the_bar_is_generated_where_ags_reads_it(run_generator):
    """Die Gegenprobe zu den beiden oben.

    Ohne sie koennte die Erzeugung aus jedem beliebigen Grund gar nichts
    mehr tun und beide Zusicherungen wuerden ueber nichts gruen. Die
    Datei muss dort liegen, wo `ags run` sie sucht - ags/widget/, neben
    den elf Ueberlagerungen -, und sie muss die Hoehe tragen, die
    src/sizes.py ausrechnet.
    """
    result = run_generator(
        "-ags-bar", extra_environment={"WAYLAND_DISPLAY": "wayland-1"})
    assert result.returncode == 0, result.stdout + result.stderr

    written = run_generator.home / ".config" / "ags" / "widget" / "Bar.tsx"
    assert written.is_file(), "Bar.tsx wurde nicht erzeugt"
    text = written.read_text()
    assert "{{" not in text, "in der erzeugten Leiste stehen Platzhalter"
    assert re.search(r"const BAR_THICKNESS = \d+$", text, re.MULTILINE), (
        "die Leiste traegt keine ausgerechnete Dicke")


@pytest.mark.allow_subprocess
def test_no_bar_is_started_when_there_is_no_screen_to_draw_on(run_generator):
    """Measured on the first boot: `generate_config.sh --all` runs before
    the compositor, printed "No display server detected, skipping log
    viewer" - and started Waybar anyway, PID 2594, with nothing to
    attach a layer surface to. It was killed unseen a minute later by the
    generation the session's own waybar-launcher ran.

    Ohne Anzeigeserver, und deshalb die haerteste der vier: schon die
    ERZEUGUNG darf hier nichts ausfuehren.
    """
    result = run_generator("-ags-bar")
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert _executed(result) == [], (
        "a bar was started with no display server:\n" + output)
