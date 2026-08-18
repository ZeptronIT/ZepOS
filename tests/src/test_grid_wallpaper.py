# SPDX-License-Identifier: GPL-3.0-or-later
"""Which screen gets which wallpaper, decided by the screen.

The origin decided it by manufacturer: `$make =~ Samsung` took the left
grid, `$make =~ Acer` the right one, `eDP-1` a black image, and portrait
screens were sorted into "links", "mitte" and "rechts" by comparing their
x position against 3000 and 5000. That is one desk - two particular
monitors, in a particular order, at a particular resolution - written
into a script that ships to everybody.

Three things it got wrong beyond the names, all of which these tests
hold shut:

  * Every grid was drawn at 3840x2160 (portrait: 2160x3840), whatever
    the screen actually was, so a 1920x1080 monitor got a 4K image scaled
    to fit and grid lines that no longer landed on the pixels they were
    drawn for.
  * The portrait branch read GRID_X, GRID_Y, GRID_CELLS_H and
    GRID_CELLS_V from a config template that was deleted with the rest of
    the employer's hardware. Nothing defines them any more: the branch
    computed `$((/ 21))` and produced nothing at all.
  * Footprints were matched to a monitor with `x .. x + 3840`, so on any
    narrower screen every window of the neighbour to the right was drawn
    onto the wrong grid as well.

Safety: every child runs through `env -i` with the stub directory as the
ONLY entry on PATH, so a command with no stub fails with "command not
found" rather than reaching a real `swaybg`, `pkill` or `convert` on the
machine running the tests. `hyprctl` is a bash stub answering from a
canned file; HOME and TMPDIR both point inside tmp_path.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

# The shared backstop, from tests/conftest.py: a command the stub
# directory does not provide has to be a failure, not an empty string.
import conftest

SRC = Path(__file__).resolve().parents[2] / "src"
TEMPLATE = SRC / "templates" / "grid-wallpaper-toggle.template"

BASH = "/bin/bash"
ENV = "/usr/bin/env"

# Invented, and deliberately not a manufacturer anybody sells: if the
# placement ever keys on these strings again, it keys on nothing.
LAPTOP = "Panel Works Internal 0001"
WIDE = "Screen Co Model X 1111"
TALL = "Screen Co Model Y 2222"

# Commands whose real binary is safe here: they read and write inside
# tmp_path and reach nothing else.
PASSTHROUGH = ("jq", "cat", "cp", "mv", "rm", "mkdir", "touch", "xargs",
                "seq", "wc")
# Commands that must never run for real.
RECORDED = ("convert", "composite", "swaybg", "pkill", "notify-send", "sleep")


def _entry(name, description, x, **overrides):
    entry = {
        "name": name, "description": description, "make": "Screen Co",
        "model": "Model X", "x": x, "y": 0,
        "width": 3840, "height": 2160, "refreshRate": 60.0,
        "scale": 1.0, "transform": 0,
    }
    entry.update(overrides)
    return entry


def _window(x, y, width=800, height=600, title="Fenster"):
    return {"floating": True, "at": [x, y], "size": [width, height],
            "title": title, "workspace": {"id": 1}}


@pytest.fixture
def generate(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(SRC))
    import template_processor

    def build(template: str, output: Path) -> Path:
        output.parent.mkdir(parents=True, exist_ok=True)
        template_processor.ConfigProcessor().apply_template(
            SRC / "templates" / f"{template}.template", output)
        output.chmod(0o755)
        return output

    return build


def _stubs(tmp_path: Path, monitors, clients=()) -> tuple[Path, Path]:
    """The stub directory and the transcript every recorded call lands in."""
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    calls = tmp_path / "calls.txt"

    monitors_json = tmp_path / "monitors.json"
    monitors_json.write_text(json.dumps(monitors), encoding="utf-8")
    clients_json = tmp_path / "clients.json"
    clients_json.write_text(json.dumps(list(clients)), encoding="utf-8")

    hyprctl = stubs / "hyprctl"
    hyprctl.write_text(
        "#!/bin/bash\n"
        "# Test stub. Never reaches the real compositor.\n"
        "case \"$1\" in\n"
        f"  monitors) exec /bin/cat '{monitors_json}' ;;\n"
        f"  clients)  exec /bin/cat '{clients_json}' ;;\n"
        "esac\n"
        "exit 1\n", encoding="utf-8")
    hyprctl.chmod(0o755)

    for name in RECORDED:
        stub = stubs / name
        stub.write_text(
            "#!/bin/bash\n"
            f"printf '{name} %s\\n' \"$*\" >> '{calls}'\n"
            # convert and composite are expected to leave a file behind:
            # the script checks for one before drawing it again.
            "target=\"${@: -1}\"\n"
            f"if [ '{name}' = convert ] || [ '{name}' = composite ]; then\n"
            "    printf 'stub image\\n' > \"$target\"\n"
            "fi\n"
            "exit 0\n", encoding="utf-8")
        stub.chmod(0o755)

    # Reports a text label's size for the footprint centring arithmetic.
    identify = stubs / "identify"
    identify.write_text("#!/bin/bash\nprintf '40\\n'\nexit 0\n", encoding="utf-8")
    identify.chmod(0o755)

    for name in PASSTHROUGH:
        assert name not in RECORDED
        conftest.assert_safe_to_passthrough(name)
        real = shutil.which(name)
        assert real, f"the script needs {name}"
        stub = stubs / name
        stub.write_text(f'#!/bin/bash\nexec "{real}" "$@"\n', encoding="utf-8")
        stub.chmod(0o755)

    python3 = stubs / "python3"
    python3.write_text(f'#!/bin/bash\nexec "{sys.executable}" "$@"\n',
                       encoding="utf-8")
    python3.chmod(0o755)
    return stubs, calls


def _run(script: Path, action: str, stubs: Path, home: Path, tmp_path: Path,
         timeout: float = 60):
    path = str(stubs)
    assert path.split(os.pathsep) == [str(stubs)]
    assert not os.environ.get("PATH", "").startswith(path)
    result = subprocess.run(
        [ENV, "-i", f"PATH={path}", f"HOME={home}", f"TMPDIR={tmp_path}",
         BASH, str(script), action],
        env={}, input="", capture_output=True, text=True, timeout=timeout)
    conftest.assert_no_missing_command(result, "the wallpaper script")
    return result


@pytest.fixture
def desk(tmp_path, generate):
    """A generated script and its config, with a HOME to run against."""
    home = tmp_path / "home"
    generate("grid-wallpaper-toggle-config",
             home / ".config" / "hypr" / "grid-wallpaper-toggle-config.sh")
    script = generate("grid-wallpaper-toggle", tmp_path / "grid-wallpaper-toggle")
    return script, home


def _calls(calls: Path, command: str) -> list[str]:
    if not calls.exists():
        return []
    return [line for line in calls.read_text(encoding="utf-8").splitlines()
            if line.split(" ", 1)[0] == command]


def _swaybg_placement(calls: Path) -> dict:
    """{connector: image} out of the recorded swaybg call."""
    lines = _calls(calls, "swaybg")
    assert len(lines) == 1, f"expected exactly one swaybg call, got {lines}"
    fields = lines[0].split()[1:]
    placement = {}
    for index, field in enumerate(fields):
        if field == "-o":
            placement[fields[index + 1]] = fields[fields.index(
                "-i", index) + 1]
    return placement


# --------------------------------------------------------------------
# what the file says
# --------------------------------------------------------------------

def test_the_script_names_no_hardware_and_no_desk():
    """Names are checked everywhere, numbers only where they act.

    A comment may say what the old code did with 3840 - that is how the
    next reader learns why the arithmetic changed. A comment may NOT name
    a manufacturer or a connector, because that is the desk itself. And
    the numbers are checked against code lines only: the first draft of
    this test read the whole file and failed over `-t 3000`, a
    notification timeout. A guard that fires on legitimate content is one
    somebody weakens later.
    """
    text = TEMPLATE.read_text(encoding="utf-8")
    for stray in ("Samsung", "Acer", "Dell", "eDP-1", "portrait-left",
                  "portrait-center", "portrait-right"):
        assert stray not in text, f"{stray} names one particular desk"

    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        assert not re.search(r"-size\s+\d{3,}x\d{3,}", line), (
            f"line {number} draws at a fixed resolution: {line.strip()}")
        assert not re.search(r"-(lt|gt|le|ge)\s+\d{4}", line), (
            f"line {number} compares a position against a fixed threshold: "
            f"{line.strip()}")
        for field in ("$make", "$model", "${make", "${model"):
            assert field not in line, (
                f"line {number} keys on the EDID {field}: {line.strip()}")


# --------------------------------------------------------------------
# drawing
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_every_screen_gets_a_grid_in_its_own_size(desk, tmp_path):
    """The grid is a positioning aid: its lines have to land on the
    pixels of the screen it is shown on. One 4K image for every monitor
    was scaled to fit on everything that was not 4K."""
    script, home = desk
    stubs, calls = _stubs(tmp_path, [
        _entry("eDP-1", LAPTOP, 0, width=1920, height=1200),
        _entry("DP-2", WIDE, 1920, width=2560, height=1440),
        _entry("DP-3", TALL, 4480, transform=1),
    ])

    result = _run(script, "generate", stubs, home, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    sizes = [line.split("-size ", 1)[1].split()[0]
             for line in _calls(calls, "convert") if "-size " in line]
    # The rotated screen's mode is 3840x2160; standing on its side it
    # covers 2160x3840, and that is what has to be drawn.
    assert sizes == ["2560x1440", "2160x3840"], (
        "the panel gets a plain background, the two externals a grid each")


@pytest.mark.allow_subprocess
def test_a_four_k_screen_gets_exactly_the_grid_it_got_before(desk, tmp_path):
    """The change is the derivation, not the picture.

    The origin drew the frame from 17,67 to 3822,2141 with lines every
    100 px on its 3840x2160 screens. The same screen has to come out the
    same way now that margin, top offset and cell size are settings
    rather than four literals - otherwise this is a redesign wearing a
    refactor's clothes.
    """
    script, home = desk
    stubs, calls = _stubs(tmp_path, [_entry("DP-1", WIDE, 0)])

    _run(script, "generate", stubs, home, tmp_path)

    drawn = _calls(calls, "convert")
    assert len(drawn) == 1, drawn
    assert "-size 3840x2160" in drawn[0]
    assert "rectangle 17,67 3822,2141" in drawn[0]
    assert "line 17,67 3822,67" in drawn[0]
    assert "line 3817,67 3817,2141" in drawn[0]


# --------------------------------------------------------------------
# placement
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_each_screen_gets_its_own_image_and_the_panel_a_plain_one(desk, tmp_path):
    script, home = desk
    stubs, calls = _stubs(tmp_path, [
        _entry("eDP-1", LAPTOP, 0, width=1920, height=1200),
        _entry("DP-2", WIDE, 1920, width=2560, height=1440),
        _entry("DP-3", TALL, 4480, transform=1),
    ])

    result = _run(script, "toggle", stubs, home, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    placement = _swaybg_placement(calls)
    assert sorted(placement) == ["DP-2", "DP-3", "eDP-1"]
    assert placement["DP-2"].endswith("-DP-2.png")
    assert placement["DP-3"].endswith("-DP-3.png")
    # The panel keeps the plain background it always had - and at its own
    # size, not at the 1920x1200 the origin wrote out for one laptop.
    assert "grid-wallpaper" not in Path(placement["eDP-1"]).name
    black = [line for line in _calls(calls, "convert")
             if placement["eDP-1"] in line]
    assert black and "-size 1920x1200" in black[0]


@pytest.mark.allow_subprocess
def test_the_manufacturer_field_plays_no_part(desk, tmp_path):
    """The same desk, with the EDID vendor field replaced by a string no
    branch could ever have matched. Placement may not change."""
    script, home = desk
    desks = []
    for make in ("Screen Co", "Nobody At All"):
        run_dir = tmp_path / make.replace(" ", "-")
        run_dir.mkdir()
        stubs, calls = _stubs(run_dir, [
            _entry("DP-2", WIDE, 0, make=make),
            _entry("DP-3", TALL, 3840, make=make, transform=1),
        ])
        _run(script, "toggle", stubs, tmp_path / "home", run_dir)
        desks.append({connector: Path(image).name
                      for connector, image in _swaybg_placement(calls).items()})

    assert desks[0] == desks[1]
    assert sorted(desks[0]) == ["DP-2", "DP-3"]


@pytest.mark.allow_subprocess
def test_moving_a_screen_moves_its_wallpaper_with_it(desk, tmp_path):
    """Position decides where a screen stands, not which picture it is.

    The origin sorted portrait screens into left, middle and right by
    comparing x against 3000 and 5000 - thresholds that describe one desk
    and mislabel every other. Two screens that swap places keep their own
    grids here, because each grid belongs to a screen rather than to a
    slot on somebody's table.
    """
    script, home = desk
    first, second = {}, {}
    for target, positions in ((first, (0, 2560)), (second, (2560, 0))):
        run_dir = tmp_path / f"run{positions[0]}"
        run_dir.mkdir()
        stubs, calls = _stubs(run_dir, [
            _entry("DP-2", WIDE, positions[0], width=2560, height=1440),
            _entry("DP-3", TALL, positions[1], width=2560, height=1440),
        ])
        _run(script, "toggle", stubs, home, run_dir)
        target.update({c: Path(i).name
                       for c, i in _swaybg_placement(calls).items()})

    assert first == second


# --------------------------------------------------------------------
# footprints
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_a_window_is_drawn_on_the_screen_it_is_actually_on(desk, tmp_path):
    """The hardcoded width, measured.

    A monitor was assumed to span `x .. x + 3840`. On this desk of two
    2560-wide screens that range covers both of them, so the window at
    2600 - which sits on the right-hand screen - was drawn onto the left
    one as well, at a position 2560 px off the edge of the image.
    """
    script, home = desk
    stubs, calls = _stubs(
        tmp_path,
        [_entry("DP-2", WIDE, 0, width=2560, height=1440),
         _entry("DP-3", TALL, 2560, width=2560, height=1440)],
        clients=[_window(2600, 100)])

    result = _run(script, "footprint", stubs, home, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    # A footprint is drawn ONTO an existing grid; a grid is created with
    # -size. Both carry "-draw rectangle", so the distinction has to be
    # which of the two the call is.
    footprints = [line for line in _calls(calls, "convert")
                  if "-draw rectangle" in line and "-size" not in line]
    assert footprints, "no footprint was drawn at all"
    assert all("-DP-3.png" in line for line in footprints), (
        "the window sits on DP-3 and may only be drawn there: "
        + "; ".join(footprints))


# --------------------------------------------------------------------
# handing the images to swaybg
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_no_monitors_paints_nothing_and_says_so(desk, tmp_path):
    """`| xargs swaybg` reported success over a failure, twice over.

    xargs runs the command even when its input is empty and exits 0 -
    `printf '' | xargs echo` prints a blank line and returns 0 - and a
    pipeline's status is the LAST command's, so wallpaper_args returning
    1 was thrown away as well.

    Measured on the shipped script with monitor detection failing: exit
    0, a BARE `swaybg` (no -o, no -i, so one image on every output), and
    the notification "Grid Overlay aktiviert". The critical
    "Monitore nicht ermittelbar!" that the code plainly intends had never
    once been shown.
    """
    script, home = desk
    # A compositor that answers with no monitors at all: monitors.py
    # writes its refusal to stderr and exits 1, which is what
    # monitor_list passes on.
    stubs, calls = _stubs(tmp_path, [])

    result = _run(script, "toggle", stubs, home, tmp_path)

    assert result.returncode != 0, (
        "a toggle that could not find a single screen reported success:\n"
        + result.stdout + result.stderr)
    assert _calls(calls, "swaybg") == [], (
        "swaybg was started with nothing to show: "
        + "; ".join(_calls(calls, "swaybg")))
    warnings = [line for line in _calls(calls, "notify-send")
                if "Monitore nicht ermittelbar" in line]
    assert warnings, ("the user was told nothing: "
                      + "; ".join(_calls(calls, "notify-send")))
    assert not [line for line in _calls(calls, "notify-send")
                if "Grid Overlay aktiviert" in line], (
        "the failure was announced as a success")
    # The marker is what the rest of the desktop reads grid mode from -
    # wallpaper-manager refuses to set a wallpaper while it is there - so
    # a toggle that did not happen may not leave one behind.
    markers = list(tmp_path.glob("grid-wallpaper-active-*"))
    assert markers == [], f"a mode that never started left its marker: {markers}"


@pytest.mark.allow_subprocess
def test_the_toggle_returns_while_swaybg_keeps_running(desk, tmp_path):
    """swaybg is a daemon, and it was started in the foreground.

    It runs for as long as the wallpaper stands - until the `pkill -9 -f
    swaybg` of the next toggle - so `swaybg "${args[@]}"` never returned,
    and neither did toggle_wallpaper. Everything after it therefore never
    happened: on a live desktop the "Grid Overlay aktiviert" notification
    had never once been shown, and the key binding that calls this script
    stayed blocked until the mode was switched off again.

    The stub below behaves like the real one - it stays up - and closes
    the output it inherited first, so that what is measured is the SCRIPT
    finishing rather than the pipes emptying. Against the foreground
    version this test times out; that is the defect, in the form the user
    meets it.
    """
    script, home = desk
    stubs, calls = _stubs(tmp_path, [_entry("DP-2", WIDE, 0)])

    lingering = shutil.which("sleep")
    assert lingering and lingering.startswith("/")
    swaybg = stubs / "swaybg"
    swaybg.write_text(
        "#!/bin/bash\n"
        f"printf 'swaybg %s\\n' \"$*\" >> '{calls}'\n"
        # Nothing the script writes may be held open by the daemon it
        # left behind, exactly as on a real desktop.
        "exec >/dev/null 2>&1\n"
        f"exec '{lingering}' 5\n", encoding="utf-8")
    swaybg.chmod(0o755)

    started = time.monotonic()
    result = _run(script, "toggle", stubs, home, tmp_path, timeout=15)
    elapsed = time.monotonic() - started

    assert result.returncode == 0, result.stdout + result.stderr
    assert elapsed < 4, (
        f"the toggle waited {elapsed:.1f}s for a daemon that does not end")
    assert _calls(calls, "swaybg"), "swaybg was never started"
    announcements = [line for line in _calls(calls, "notify-send")
                     if "Grid Overlay aktiviert" in line]
    assert announcements, (
        "the toggle never got as far as telling the user it had happened: "
        + "; ".join(_calls(calls, "notify-send")))


@pytest.mark.allow_subprocess
def test_an_image_path_with_a_space_reaches_swaybg_whole(generate, tmp_path):
    """The other half of what xargs did: it splits on whitespace.

    The image paths are built from $HOME and from $TMPDIR, and neither is
    this program's to choose. Under a home directory whose name contains
    a space, `-o DP-2 -m fill -i /home/some one/.config/...png` reached
    swaybg as two arguments, so it was handed a file called
    ".../some" and an argument "one/.config/...png" it does not
    understand.
    """
    home = tmp_path / "some one"
    generate("grid-wallpaper-toggle-config",
             home / ".config" / "hypr" / "grid-wallpaper-toggle-config.sh")
    script = generate("grid-wallpaper-toggle", tmp_path / "grid-wallpaper-toggle")
    stubs, _ = _stubs(tmp_path, [_entry("DP-2", WIDE, 0)])

    # The shared stub writes "$*", which joins every argument with a
    # space again and makes the very split this test is about invisible.
    # This one writes ONE LINE PER ARGUMENT, so a path that arrived in
    # two pieces reads as two pieces.
    argv_file = tmp_path / "swaybg-argv.txt"
    swaybg = stubs / "swaybg"
    swaybg.write_text(
        "#!/bin/bash\n"
        f"printf '%s\\n' \"$@\" >> '{argv_file}'\n"
        "exit 0\n", encoding="utf-8")
    swaybg.chmod(0o755)

    result = _run(script, "toggle", stubs, home, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert argv_file.exists(), "swaybg was never started"
    received = argv_file.read_text(encoding="utf-8").splitlines()
    image = str(home / ".config" / "hypr" / "grid-wallpaper-unknown-DP-2.png")
    assert received == ["-o", "DP-2", "-m", "fill", "-i", image], (
        f"the image path was cut apart on its space: {received}")
