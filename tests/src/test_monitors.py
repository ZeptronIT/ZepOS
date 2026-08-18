# SPDX-License-Identifier: GPL-3.0-or-later
"""What is attached decides the layout - not what the machine is called.

The origin matched `$(hostname)` against two workstation names and, for
one of them, wrote three monitor serial numbers into the generated
configuration. On any third machine the case statement fell through to a
fallback, so the feature worked on exactly two computers in the world.

Two things this file is careful about, both of which the plan for this
task got wrong:

  * What is generated here are WORKSPACE ASSIGNMENTS, not monitor modes.
    `~/.config/hypr/monitors.conf` belongs to src/displays.py, and a
    second writer emitting `monitor=` lines would fight it.
  * The generated file has to be READ by somebody. It was not: the script
    wrote `workspaces-generated.conf` while the Hyprland config sourced
    `workspaces.conf`, so a correct layout was computed and then dropped.
    Three tests below hold that wiring shut.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# The shared backstop, from tests/conftest.py: a command the stub
# directory does not provide has to be a failure, not an empty string.
import conftest

from src.monitors import (Monitor, detect, layout, ordered, bar_workspaces,
                          workspace_assignments)

# Anchored on this file, not on the working directory: pytest may be
# started from anywhere.
SRC = Path(__file__).resolve().parents[2] / "src"
TEMPLATE = SRC / "templates" / "hypr-monitor-detect-config.template"
UNIVERSAL = SRC / "templates" / "hyprland-universal-config.template"
BAR_TEMPLATE = SRC / "templates" / "bar-workspace-detect-config.template"

BASH = "/bin/bash"
ENV = "/usr/bin/env"

# Deliberately invented vendor and product names. A real EDID string from
# any machine this test could run on would be exactly the kind of value
# this whole task exists to remove.
LAPTOP = "Panel Works Internal 0001"
LEFT = "Screen Co Model X 1111"
RIGHT = "Screen Co Model X 2222"


def _entry(name, description, x, **overrides):
    """One element of `hyprctl monitors -j`, with the keys it really has."""
    entry = {
        "name": name,
        "description": description,
        "x": x,
        "y": 0,
        "width": 1920,
        "height": 1200,
        "refreshRate": 60.0,
        "scale": 1.0,
        "transform": 0,
    }
    entry.update(overrides)
    return entry


SAMPLE = json.dumps([
    _entry("eDP-1", LAPTOP, 0),
    _entry("DP-2", RIGHT, 1920, width=3840, height=2160),
])


def _runner(stdout, returncode=0, stderr=""):
    def run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout,
                                           stderr=stderr)
    return run


def _monitor(name, description, x, **overrides):
    fields = {
        "name": name,
        "description": description,
        "x": x,
        "width": 1920,
        "height": 1200,
        "refresh": 60.0,
        "scale": 1.0,
        "transform": 0,
    }
    fields.update(overrides)
    return Monitor(**fields)


def _assignments(text):
    """{workspace number: monitor selector} out of the generated block."""
    found = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("workspace="):
            continue
        number, _, target = line[len("workspace="):].partition(",")
        assert target.startswith("monitor:"), line
        found[int(number)] = target[len("monitor:"):]
    return found


# --------------------------------------------------------------------
# reading the compositor
# --------------------------------------------------------------------

def test_monitors_are_read_from_the_running_compositor():
    found = detect(runner=_runner(SAMPLE))
    assert [m.description for m in found] == [LAPTOP, RIGHT]


def test_resolution_and_scale_survive():
    first = detect(runner=_runner(SAMPLE))[0]
    assert (first.width, first.height, first.scale) == (1920, 1200, 1.0)


def test_the_connector_and_the_position_survive_too():
    """The plan's dataclass had neither, and the job needs both: `name`
    tells a laptop panel from an external, `x` orders them on the desk."""
    second = detect(runner=_runner(SAMPLE))[1]
    assert (second.name, second.x) == ("DP-2", 1920)


def test_monitors_arrive_ordered_left_to_right():
    """`hyprctl` returns them in the order the compositor happens to hold
    them, which follows the order they were plugged in. Handing workspaces
    1-3 to whatever came first puts them on the right-hand screen as often
    as not."""
    scrambled = json.dumps([
        _entry("DP-3", RIGHT, 3840),
        _entry("eDP-1", LAPTOP, 0),
        _entry("DP-2", LEFT, 1920),
    ])
    assert [m.x for m in detect(runner=_runner(scrambled))] == [0, 1920, 3840]


def test_the_order_does_not_depend_on_the_caller():
    """Both entry points sort, so a hand-built list is laid out left to
    right as well - the layout must not read as correct only because
    detect() happened to sort first."""
    right = _monitor("DP-3", RIGHT, 3840)
    left = _monitor("DP-2", LEFT, 1920)
    assert [m.x for m in ordered([right, left])] == [1920, 3840]
    assert [m.x for m, _ in layout([right, left])] == [1920, 3840]


# --------------------------------------------------------------------
# what a query that fails looks like
# --------------------------------------------------------------------

def test_a_failing_query_raises_rather_than_returning_nothing():
    with pytest.raises(RuntimeError):
        detect(runner=_runner("", returncode=1))


def test_a_missing_compositor_raises_a_clear_error():
    """hyprctl is absent outside a session. FileNotFoundError arrives
    before any CompletedProcess exists, so a returncode check never sees
    it."""
    def run(cmd, **kw):
        raise FileNotFoundError("hyprctl")

    with pytest.raises(RuntimeError, match="hyprctl"):
        detect(runner=run)


@pytest.mark.parametrize("stdout", ["", "   \n", "not json at all", "{}", "null"])
def test_output_that_is_not_a_monitor_list_raises_the_same_error(stdout):
    """One exception type for "the compositor did not answer usefully".

    json.loads() raises JSONDecodeError, which is a ValueError - the type
    an EMPTY monitor list is refused with. A caller that catches
    RuntimeError for a failed query would have let this one through, and
    one that catches ValueError could not tell a broken answer from an
    empty desk. Both are the compositor failing to answer, so both are a
    RuntimeError.
    """
    with pytest.raises(RuntimeError):
        detect(runner=_runner(stdout))


def test_an_entry_missing_every_key_does_not_crash():
    """`hyprctl monitors -j` has changed shape between Hyprland releases.

    An entry this code cannot read must degrade to "no monitor I can
    address" - not to a KeyError inside an exec-once script nobody is
    watching.
    """
    found = detect(runner=_runner(json.dumps([{}, _entry("DP-2", RIGHT, 1920)])))
    assert len(found) == 2
    assert found[0].description == ""
    # Unaddressable, so it gets nothing - and the one that IS addressable
    # keeps every workspace.
    assert set(_assignments(workspace_assignments(found)).values()) == {
        f"desc:{RIGHT}"}


# --------------------------------------------------------------------
# the layout
# --------------------------------------------------------------------

def test_the_layout_is_generated_from_what_is_attached():
    """The origin loaded a prewritten profile matching a known hostname.
    Nothing about the machine's name says what is plugged into it."""
    text = workspace_assignments(detect(runner=_runner(SAMPLE)))
    assert f"monitor:desc:{LAPTOP}" in text
    assert f"monitor:desc:{RIGHT}" in text


def test_no_monitor_mode_is_written():
    """`~/.config/hypr/monitors.conf` belongs to src/displays.py.

    A `monitor=` line from here would set a resolution the user did not
    ask for, on top of the one the GUI wrote, and the two would disagree
    about which one is in force.
    """
    text = workspace_assignments(detect(runner=_runner(SAMPLE)))
    for line in text.splitlines():
        assert not line.strip().startswith("monitor="), line


def test_an_empty_monitor_list_is_refused():
    """No monitors means the query failed - writing an empty assignment
    block would leave the user with workspaces nobody claims."""
    with pytest.raises(ValueError):
        workspace_assignments([])


def test_a_desk_where_nothing_can_be_addressed_is_refused():
    with pytest.raises(ValueError):
        workspace_assignments([_monitor("", "", 0)])


def test_a_single_monitor_gets_every_workspace():
    found = _assignments(workspace_assignments([_monitor("DP-1", LEFT, 0)]))
    assert sorted(found) == list(range(1, 11))
    assert set(found.values()) == {f"desc:{LEFT}"}


def test_the_laptop_panel_keeps_a_workspace_of_its_own():
    """The panel is small, it is often closed, and it is the one screen
    that is always there. It gets the last workspace; the externals share
    the nine the user actually works on."""
    found = _assignments(workspace_assignments([
        _monitor("eDP-1", LAPTOP, 0),
        _monitor("DP-2", LEFT, 1920),
        _monitor("DP-3", RIGHT, 3840),
    ]))
    assert found[10] == f"desc:{LAPTOP}"
    assert [found[n] for n in range(1, 6)] == [f"desc:{LEFT}"] * 5
    assert [found[n] for n in range(6, 10)] == [f"desc:{RIGHT}"] * 4


def test_a_laptop_on_its_own_still_gets_all_ten():
    """No external to hand the other nine to. Reserving workspace 10 for
    the panel and leaving 1-9 unassigned would be nine workspaces the user
    cannot reach from the bar."""
    found = _assignments(workspace_assignments([_monitor("eDP-1", LAPTOP, 0)]))
    assert sorted(found) == list(range(1, 11))


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5, 11])
def test_every_workspace_is_assigned_exactly_once(count):
    """Ten workspaces are bound to SUPER+1..0 whether they have a monitor
    or not. One that no rule names lands wherever the focus happens to be;
    one named twice is a rule the user cannot predict.

    Eleven monitors is not a realistic desk - it is the case where there
    are more screens than workspaces, which must still not drop one.
    """
    monitors = [_monitor(f"DP-{i}", f"Screen Co Model X {i:04d}", i * 1920)
                for i in range(count)]
    text = workspace_assignments(monitors)
    numbers = [int(line.split("=", 1)[1].split(",", 1)[0])
               for line in text.splitlines()
               if line.strip().startswith("workspace=")]
    assert sorted(numbers) == list(range(1, 11))


# --------------------------------------------------------------------
# how a monitor is named in the rule
# --------------------------------------------------------------------

def test_a_description_with_a_comma_does_not_split_the_rule():
    """A workspace rule is comma-separated, and EDID vendor strings
    contain commas ("Acme, Inc."). Written out whole, everything after the
    first comma becomes a second rule: Hyprland accepts the line without
    complaint and then matches a monitor called "desc:Acme" that nobody
    has. Verified with `Hyprland --verify-config`: the mangled line parses
    as "config ok".

    Hyprland matches `desc:` by prefix, so cutting at the comma still
    finds the monitor.
    """
    text = workspace_assignments([_monitor("DP-1", "Acme, Inc. Model Q 7", 0)])
    for line in text.splitlines():
        if line.startswith("workspace="):
            assert line.count(",") == 1, line
            assert line.endswith(",monitor:desc:Acme"), line


def test_a_description_with_spaces_is_kept_whole():
    """Spaces are not separators. Every real description has them, and a
    rule truncated at the first space matches the vendor rather than the
    screen."""
    text = workspace_assignments([_monitor("DP-1", LEFT, 0)])
    assert f"monitor:desc:{LEFT}" in text


def test_two_monitors_that_cut_down_to_the_same_prefix_use_the_connector():
    """Two identical screens differ only by the serial at the END of the
    description. Cut at a comma in the vendor field, both become the same
    `desc:` - which Hyprland resolves to whichever it finds first, so one
    screen would get all ten workspaces and the other none.

    The connector name is unique but changes when a cable moves. That is
    the honest trade here: a name that is right today beats a description
    that is ambiguous forever.
    """
    found = _assignments(workspace_assignments([
        _monitor("DP-1", "Acme, Inc. Model Q 1111", 0),
        _monitor("DP-2", "Acme, Inc. Model Q 2222", 1920),
    ]))
    assert set(found.values()) == {"DP-1", "DP-2"}


def test_a_description_that_is_the_prefix_of_another_uses_the_connector():
    """`desc:` matches by prefix, so "Screen Co Model X" also matches
    "Screen Co Model X 2" - the shorter one is not wrong, it is ambiguous.

    The longer one is not, which is why only one of the two loses its
    description here. Demoting both would throw away a stable identifier
    over somebody else's ambiguity.
    """
    found = _assignments(workspace_assignments([
        _monitor("DP-1", "Screen Co Model X", 0),
        _monitor("DP-2", "Screen Co Model X 2", 1920),
    ]))
    assert set(found.values()) == {"DP-1", "desc:Screen Co Model X 2"}


def test_a_monitor_without_a_description_falls_back_to_its_connector():
    found = _assignments(workspace_assignments([
        _monitor("DP-1", "", 0),
        _monitor("DP-2", RIGHT, 1920),
    ]))
    assert set(found.values()) == {"DP-1", f"desc:{RIGHT}"}


# --------------------------------------------------------------------
# the template
# --------------------------------------------------------------------

def test_the_hostname_plays_no_part():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "hostname" not in text.lower(), (
        "monitor detection must not depend on the machine's name")


def test_the_template_hardcodes_no_monitor():
    """Three serial numbers and a connector name used to be written into
    the office branch. They named the monitors on one desk."""
    text = TEMPLATE.read_text(encoding="utf-8")
    for stray in ("desc:", "eDP-1", "HDMI-A-1"):
        assert stray not in text, f"{stray} names one particular desk"


def test_the_detected_layout_is_actually_sourced():
    """The defect this task inherited: nothing read the file.

    The script wrote `workspaces-generated.conf`; the Hyprland config
    sourced `workspaces.conf` and nothing else. Every layout it ever
    computed went into a file no compositor opened.
    """
    lines = [line.strip() for line in UNIVERSAL.read_text(encoding="utf-8").splitlines()]
    profile = lines.index("source = ~/.config/hypr/workspaces.conf")
    generated = lines.index("source = ~/.config/hypr/workspaces-generated.conf")
    assert generated > profile, (
        "the detected assignments have to be sourced AFTER the profile's, "
        "or the profile silently wins and the detection is decoration")


def test_the_sourced_file_is_created_before_hyprland_reads_it():
    """A `source =` line pointing at a file that is not there is a config
    ERROR, not a skipped line.

    Measured on Hyprland 0.55.4: `Hyprland --verify-config` on a config
    whose only content is `source = <missing>` exits 1 and prints "source=
    globbing error: found no match". The generator already creates empty
    placeholders for the five files the universal config sources for
    exactly this reason; the sixth has to be in that list too.
    """
    text = SRC.joinpath("generate_config.sh").read_text(encoding="utf-8")
    loop = [line for line in text.splitlines()
            if line.strip().startswith("for placeholder in")]
    assert loop, "the placeholder loop that keeps sourced files present is gone"
    assert any("workspaces-generated.conf" in line for line in loop), (
        "workspaces-generated.conf is sourced but never created, so a fresh "
        "installation starts with a config error")


def test_the_recovery_advice_does_not_dangle_the_source():
    """The footer tells the user what to do from a TTY when the layout is
    wrong. Telling them to DELETE the sourced file trades a bad layout for
    a config error on every subsequent start."""
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "rm $output_file" not in text
    assert "rm $OUTPUT_FILE" not in text
    assert 'rm "$OUTPUT_FILE"' not in text


# --------------------------------------------------------------------
# the generated script, executed
# --------------------------------------------------------------------
#
# Safety: every child runs through `env -i` with the stub directory as the
# ONLY entry on PATH, so a command with no stub fails with "command not
# found" instead of reaching the real hyprctl on the machine running the
# tests. `hyprctl` is a bash stub that prints canned JSON and never execs
# anything; the read-only text tools are passed through to their real
# binaries. HOME and TMPDIR both point inside tmp_path, so the script's
# output and its log stay there.

PASSTHROUGH = ("jq", "cat", "mv", "rm", "mkdir", "date", "tee")


@pytest.fixture
def generate(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(SRC))
    import template_processor

    def build(template: str, output: str) -> Path:
        path = tmp_path / output
        template_processor.ConfigProcessor().apply_template(
            SRC / "templates" / f"{template}.template", path)
        path.chmod(0o755)
        return path

    return build


def _stubs(tmp_path: Path, monitors_json: str) -> Path:
    import shutil

    stubs = tmp_path / "stubs"
    stubs.mkdir()

    payload = tmp_path / "monitors.json"
    payload.write_text(monitors_json + "\n", encoding="utf-8")
    hyprctl = stubs / "hyprctl"
    # `|| [ -n "$line" ]` so a payload without a trailing newline is still
    # printed: read returns non-zero on the last partial line, and the
    # loop body would never run for it. Without this the stub answered
    # with nothing at all, which the script reads as "no compositor".
    hyprctl.write_text(
        "#!/bin/bash\n"
        "# Test stub. Never reaches the real compositor.\n"
        "while IFS= read -r line || [ -n \"$line\" ]; do "
        f"printf '%s\\n' \"$line\"; done < '{payload}'\n"
        "exit 0\n",
        encoding="utf-8")
    hyprctl.chmod(0o755)

    for name in PASSTHROUGH:
        conftest.assert_safe_to_passthrough(name)
        real = shutil.which(name)
        assert real, f"the script needs {name}"
        stub = stubs / name
        stub.write_text(f'#!/bin/bash\nexec "{real}" "$@"\n', encoding="utf-8")
        stub.chmod(0o755)

    # The module the script calls. Passed through to the interpreter
    # running the tests, so the real src/monitors.py is what answers.
    python3 = stubs / "python3"
    python3.write_text(f'#!/bin/bash\nexec "{sys.executable}" "$@"\n',
                       encoding="utf-8")
    python3.chmod(0o755)

    # The command the script now calls, which the package installs into
    # /usr/bin and a checkout does not install anywhere. It is reached
    # through the python3 stub above rather than through the interpreter
    # directly, so a test that breaks python3 to model a broken
    # installation still breaks this.
    command = stubs / "zepos-generate"
    command.write_text(
        f'#!/bin/bash\nexec python3 "{SRC / "bin" / "zepos-generate"}" "$@"\n',
        encoding="utf-8")
    command.chmod(0o755)
    return stubs


def _run_script(script: Path, stubs: Path, home: Path, tmp_path: Path):
    path = str(stubs)
    assert path.split(os.pathsep) == [str(stubs)]
    assert not os.environ.get("PATH", "").startswith(path)
    (home / ".config" / "hypr").mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [ENV, "-i", f"PATH={path}", f"HOME={home}", f"TMPDIR={tmp_path}",
         BASH, str(script)],
        env={}, input="", capture_output=True, text=True, timeout=60)
    # Here rather than repeated in each caller: six of them checked
    # stderr only, and this script sends most of its work through
    # substitutions and pipes whose stderr it drops.
    conftest.assert_no_missing_command(result, "the detect script")
    return result


@pytest.mark.allow_subprocess
def test_the_script_writes_the_layout_it_detected(generate, tmp_path):
    script = generate("hypr-monitor-detect-config", "hypr-monitor-detect.sh")
    stubs = _stubs(tmp_path, json.dumps([
        _entry("DP-3", RIGHT, 3840),
        _entry("eDP-1", LAPTOP, 0),
        _entry("DP-2", LEFT, 1920),
    ]))
    home = tmp_path / "home"

    result = _run_script(script, stubs, home, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    written = (home / ".config" / "hypr" / "workspaces-generated.conf").read_text(
        encoding="utf-8")
    found = _assignments(written)
    assert found[1] == f"desc:{LEFT}"
    assert found[10] == f"desc:{LAPTOP}"


@pytest.mark.allow_subprocess
def test_a_failed_detection_still_leaves_the_sourced_file_behind(
        generate, tmp_path):
    """The script exits 1 when the compositor answers with nothing. The
    file the Hyprland config sources must exist all the same, or the next
    start fails to parse over a detection that merely did not run."""
    script = generate("hypr-monitor-detect-config", "hypr-monitor-detect.sh")
    stubs = _stubs(tmp_path, "[]")
    home = tmp_path / "home"

    result = _run_script(script, stubs, home, tmp_path)

    assert result.returncode == 1
    assert (home / ".config" / "hypr" / "workspaces-generated.conf").exists()


@pytest.mark.allow_subprocess
def test_a_broken_module_falls_back_to_the_first_monitor(generate, tmp_path):
    """The fallback the origin had, kept: all workspaces on the first
    monitor. A desk with no assignments at all is worse than a crude
    one."""
    script = generate("hypr-monitor-detect-config", "hypr-monitor-detect.sh")
    stubs = _stubs(tmp_path, json.dumps([_entry("DP-2", LEFT, 1920)]))
    # The layout comes from zepos-generate, which is a Python program.
    # An interpreter that refuses to start is how a broken installation
    # looks from inside this script: it gets a non-zero status and no
    # output, which is exactly what the fallback exists for.
    (stubs / "python3").write_text("#!/bin/bash\nexit 1\n", encoding="utf-8")
    (stubs / "python3").chmod(0o755)
    home = tmp_path / "home"

    result = _run_script(script, stubs, home, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    written = (home / ".config" / "hypr" / "workspaces-generated.conf").read_text(
        encoding="utf-8")
    assert set(_assignments(written).values()) == {"DP-2"}


# --------------------------------------------------------------------
# the bar
# --------------------------------------------------------------------
#
# bar-workspace-detect.sh is the twin of hypr-monitor-detect.sh: both
# answer "which workspaces belong on which screen", one for the bar and
# one for the compositor. It used to answer it on its own - by reading
# ~/.config/hypr/current-profile and, in the office branch, by selecting
# monitors through three EDID serial numbers. Two derivations of one
# layout disagree the moment a cable moves, and the user meets that
# disagreement as workspace buttons on a bar where the windows never
# appear.

def test_the_bar_layout_comes_from_the_same_function():
    """Same monitors in, same blocks out - the bar's mapping is layout()
    rendered for the bar, not a second rule that happens to agree today."""
    monitors = [
        _monitor("eDP-1", LAPTOP, 0),
        _monitor("DP-2", LEFT, 1920),
        _monitor("DP-3", RIGHT, 3840),
    ]
    bar = bar_workspaces(monitors)

    assert bar["persistent-workspaces"] == {
        "DP-2": [1, 2, 3, 4, 5],
        "DP-3": [6, 7, 8, 9],
        "eDP-1": [10],
    }
    assert bar["panel-workspace"] == 10


def test_the_bar_names_monitors_by_connector_not_by_description():
    """The bar resolves persistent-workspaces against the connector
    names. `desc:` is a Hyprland selector and means nothing to the bar:
    written there it produces a key that matches no output, so the
    workspaces simply never appear."""
    bar = bar_workspaces([_monitor("DP-1", LEFT, 0)])
    assert list(bar["persistent-workspaces"]) == ["DP-1"]


def test_a_desk_with_no_panel_reports_no_panel_workspace():
    """The laptop icon on workspace 10 is only honest when a laptop
    holds workspace 10."""
    bar = bar_workspaces([_monitor("DP-1", LEFT, 0), _monitor("DP-2", RIGHT, 1920)])
    assert bar["panel-workspace"] is None
    assert bar["persistent-workspaces"] == {
        "DP-1": [1, 2, 3, 4, 5],
        "DP-2": [6, 7, 8, 9, 10],
    }


def test_a_laptop_on_its_own_reports_no_panel_workspace_either():
    """It has all ten. Marking one of them as "the laptop's" would put
    the icon on a workspace that is no different from the other nine."""
    bar = bar_workspaces([_monitor("eDP-1", LAPTOP, 0)])
    assert bar["panel-workspace"] is None


def test_a_monitor_the_bar_cannot_name_is_left_out():
    """A monitor with a description but no connector name can be named in
    a Hyprland rule and cannot be named in the bar. Writing an empty key
    would give the bar a persistent workspace on an output called "",
    which it matches against nothing - the same outcome, minus the
    invalid configuration."""
    bar = bar_workspaces([_monitor("", LEFT, 0), _monitor("DP-2", RIGHT, 1920)])
    assert list(bar["persistent-workspaces"]) == ["DP-2"]


def test_the_bar_script_reads_no_profile_and_names_no_monitor():
    """The two mechanisms that made the bar disagree with the compositor.

    The profile file said "office" or "home"; Hyprland's own layout never
    depended on it. And the office branch picked its three screens by
    serial number, so on any other desk the bar fell through to a
    position-based guess while the compositor used its own.
    """
    text = BAR_TEMPLATE.read_text(encoding="utf-8")
    assert "current-profile" not in text, (
        "the bar must not derive the layout from the active profile - the "
        "compositor does not")
    for stray in ("desc:", "eDP-1", "HDMI-", "hostname"):
        assert stray not in text, f"{stray} names one particular desk"


@pytest.mark.allow_subprocess
def test_the_bar_script_writes_the_layout_it_detected(generate, tmp_path):
    script = generate("bar-workspace-detect-config", "bar-workspace-detect.sh")
    stubs = _stubs(tmp_path, json.dumps([
        _entry("DP-3", RIGHT, 3840),
        _entry("eDP-1", LAPTOP, 0),
        _entry("DP-2", LEFT, 1920),
    ]))
    home = tmp_path / "home"

    result = _run_script(script, stubs, home, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    written = json.loads((home / ".config" / "ags" / "workspaces.json")
                         .read_text(encoding="utf-8"))
    assert written["persistent-workspaces"] == {
        "DP-2": [1, 2, 3, 4, 5],
        "DP-3": [6, 7, 8, 9],
        "eDP-1": [10],
    }
    # The generator merges this key into the bar's own config.
    assert list(written["format-icons"]) == ["10"]


@pytest.mark.allow_subprocess
def test_the_bar_falls_back_to_showing_everything_everywhere(generate, tmp_path):
    """A bar with no persistent workspaces shows only the ones that
    happen to be occupied, which on a fresh session is one. Ten buttons
    on every screen is crude; it is not a bar the user cannot navigate
    with."""
    script = generate("bar-workspace-detect-config", "bar-workspace-detect.sh")
    stubs = _stubs(tmp_path, json.dumps([_entry("DP-2", LEFT, 1920)]))
    (stubs / "python3").write_text("#!/bin/bash\nexit 1\n", encoding="utf-8")
    (stubs / "python3").chmod(0o755)
    home = tmp_path / "home"

    result = _run_script(script, stubs, home, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    written = json.loads((home / ".config" / "ags" / "workspaces.json")
                         .read_text(encoding="utf-8"))
    assert written["persistent-workspaces"] == {"*": list(range(1, 11))}


@pytest.mark.allow_subprocess
def test_a_broken_answer_leaves_the_previous_bar_configuration_alone(
        generate, tmp_path):
    """Half a JSON document is a bar that will not start.

    The check has to happen before the file is in place, not after: the
    origin's sibling wrote first and reported "not applied" over a file
    that was already live.
    """
    script = generate("bar-workspace-detect-config", "bar-workspace-detect.sh")
    stubs = _stubs(tmp_path, json.dumps([_entry("DP-2", LEFT, 1920)]))
    (stubs / "python3").write_text(
        '#!/bin/bash\nprintf \'{"persistent-workspaces": {"DP-2": [1,\'\nexit 0\n',
        encoding="utf-8")
    (stubs / "python3").chmod(0o755)
    home = tmp_path / "home"
    previous = home / ".config" / "ags" / "workspaces.json"
    previous.parent.mkdir(parents=True)
    previous.write_text('{"persistent-workspaces": {"*": [1]}}\n', encoding="utf-8")

    result = _run_script(script, stubs, home, tmp_path)

    assert result.returncode == 1
    assert json.loads(previous.read_text(encoding="utf-8")) == {
        "persistent-workspaces": {"*": [1]}}


# --------------------------------------------------------------------
# the two halves against each other
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
@pytest.mark.parametrize("desk", [
    # The office desk the serial numbers used to name: three externals
    # and a panel.
    [_entry("eDP-1", LAPTOP, 0), _entry("DP-2", "Screen Co Model A 1", 1920),
     _entry("DP-3", "Screen Co Model B 2", 3840),
     _entry("DP-4", "Screen Co Model C 3", 5760)],
    # A laptop and one external - the branch where the bar used to show
    # all ten workspaces on both screens while Hyprland put nine on one.
    [_entry("eDP-1", LAPTOP, 0), _entry("DP-2", RIGHT, 1920)],
    # No panel at all.
    [_entry("DP-1", LEFT, 0), _entry("DP-2", RIGHT, 3840)],
    # One screen.
    [_entry("DP-1", LEFT, 0)],
    # Two screens whose descriptions cut down to the same prefix, so the
    # compositor rule has to fall back to connector names - the case
    # where the two halves are most likely to drift apart.
    [_entry("DP-1", "Acme, Inc. Model Q 1111", 0),
     _entry("DP-2", "Acme, Inc. Model Q 2222", 1920)],
])
def test_bar_and_compositor_place_every_workspace_on_the_same_screen(
        generate, tmp_path, desk):
    """The point of the whole exercise, measured on both artifacts.

    Both scripts run against the same compositor answer, and every
    workspace has to land on the same physical screen in both. Before
    this, the bar reached that answer through the profile file and three
    serial numbers while the compositor read the monitors, so the two
    agreed only on the desk the serials were copied from.

    The comparison resolves the compositor's `desc:` selector back to a
    connector name through the same monitor list both scripts were given
    - otherwise "desc:Screen Co Model A 1" and "DP-2" would read as a
    disagreement when they name one screen.
    """
    payload = json.dumps(desk)
    stubs = _stubs(tmp_path, payload)
    home = tmp_path / "home"

    compositor = generate("hypr-monitor-detect-config", "hypr-monitor-detect.sh")
    bar = generate("bar-workspace-detect-config", "bar-workspace-detect.sh")
    first = _run_script(compositor, stubs, home, tmp_path)
    second = _run_script(bar, stubs, home, tmp_path)
    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr

    by_description = {entry["description"]: entry["name"] for entry in desk}

    def connector(selector: str) -> str:
        if not selector.startswith("desc:"):
            return selector
        prefix = selector[len("desc:"):]
        matches = {name for description, name in by_description.items()
                   if description.startswith(prefix)}
        assert len(matches) == 1, f"{selector} names {matches or 'nothing'}"
        return matches.pop()

    hypr = {number: connector(selector) for number, selector in _assignments(
        (home / ".config" / "hypr" / "workspaces-generated.conf")
        .read_text(encoding="utf-8")).items()}

    written = json.loads((home / ".config" / "ags" / "workspaces.json")
                         .read_text(encoding="utf-8"))
    bar_layout = {number: name
                  for name, numbers in written["persistent-workspaces"].items()
                  for number in numbers}

    assert bar_layout == hypr
    assert sorted(hypr) == list(range(1, 11))


# --------------------------------------------------------------------
# the shortcut overlay
# --------------------------------------------------------------------
#
# A third artifact stating a layout: the shortcut module carried a
# "Monitor-Layout" section reading DP-1 (Links) / HDMI-A-1 (Rechts) with
# two manufacturer names and a workspace split. It was written once and
# then described nobody's desk but one - and it contradicted the two
# scripts above the moment a cable moved.

SHORTCUTS = SRC / "templates" / "hypr-shortcuts-config.template"


def test_the_shortcut_overlay_states_no_layout_of_its_own():
    text = SHORTCUTS.read_text(encoding="utf-8")
    for stray in ("DP-1", "HDMI-A-1", "Workspaces 1-5", "Workspaces 6-10"):
        assert stray not in text, f"{stray} states one desk's layout"


@pytest.mark.allow_subprocess
def test_the_overlay_reads_the_layout_from_the_attached_monitors(
        generate, tmp_path):
    """Run as the bar runs it, against a desk that is not the one the
    fixed rows described."""
    module = generate("hypr-shortcuts-config", "hypr-shortcuts.py")
    stubs = _stubs(tmp_path, json.dumps([
        _entry("eDP-1", LAPTOP, 0),
        _entry("DP-5", LEFT, 1920),
        _entry("DP-7", RIGHT, 3840),
    ]))

    # runpy rather than an import: the module has to be executed the way
    # the bar executes it, with a stub PATH and no site-packages of the
    # test process, and its monitor section read afterwards.
    #
    # abschnitte() rather than a dict at module level: since 12.08.2026
    # the key sections are DERIVED from the Hyprland configuration
    # (src/keybinds.py) instead of written out here, so there is no
    # `shortcuts` dict any more to read a name out of. The monitor rows
    # are the last section the module still assembles itself, and
    # abschnitte() is where it does it.
    reader = tmp_path / "read_section.py"
    reader.write_text(
        "import json, runpy, sys\n"
        "namespace = runpy.run_path(sys.argv[1])\n"
        "print(json.dumps([rows for name, rows in namespace['abschnitte']()\n"
        "                  if 'Monitor-Layout' in name]))\n",
        encoding="utf-8")

    result = subprocess.run(
        [ENV, "-i", f"PATH={stubs}", f"HOME={tmp_path}",
         sys.executable, str(reader), str(module)],
        env={}, input="", capture_output=True, text=True, timeout=60)

    assert result.returncode == 0, result.stdout + result.stderr
    sections = json.loads(result.stdout)
    assert len(sections) == 1, "the overlay lost its monitor section"
    rows = dict(tuple(row) for row in sections[0])
    assert sorted(rows) == ["DP-5", "DP-7", "eDP-1"]
    assert "Workspaces 1-5" in rows["DP-5"]
    assert "Workspace 10" in rows["eDP-1"]
    assert LEFT in rows["DP-5"]


@pytest.mark.allow_subprocess
def test_the_overlay_still_renders_without_a_compositor(generate, tmp_path):
    """This is a bar module: it runs whether a compositor answers or not.

    Losing every shortcut because the monitor query failed would trade a
    section nobody can see for the whole panel.
    """
    module = generate("hypr-shortcuts-config", "hypr-shortcuts.py")
    stubs = _stubs(tmp_path, "[]")

    # Eine Konfiguration, die es zu zeigen gibt. Ohne sie waere "der
    # Tooltip ist nicht leer" auch dann erfuellt, wenn das Modul gar
    # nichts mehr liest - und genau das ist seit dem 12.08.2026 die
    # Frage: die Tastenzeilen stehen nicht mehr im Modul, sondern in der
    # Hyprland-Konfiguration.
    (tmp_path / ".config" / "hypr").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".config" / "hypr" / "hyprland.conf").write_text(
        "# @Anwendungen: Terminal in einem schwebenden Fenster (kitty)\n"
        'bind = $mainMod, Q, exec, kitty --class="floating-default"\n',
        encoding="utf-8")

    result = subprocess.run(
        [ENV, "-i", f"PATH={stubs}", f"HOME={tmp_path}",
         sys.executable, str(module)],
        env={}, input="", capture_output=True, text=True, timeout=60)

    assert result.returncode == 0, result.stdout + result.stderr
    output = json.loads(result.stdout)
    assert "Terminal" in output["tooltip"]
    assert "SUPER + Q" in output["tooltip"], (
        "der fehlgeschlagene Monitorabschnitt hat die Tasten mitgenommen")
