# SPDX-License-Identifier: GPL-3.0-or-later
"""The console follows the screens, not a remembered desk.

The header named a manufacturer, an office and a count of three portrait
monitors, and the script agreed with it: it counted `/sys/class/drm/card*-DP-*` and
refused to do anything below three, then wrote the fixed value 3 into the
framebuffer console. So it did nothing at all for one or two portrait
screens, it rotated the wrong way for screens standing the other way
round, and on a desk with three landscape monitors it happily turned a
perfectly readable console on its side.

None of that is a comment problem. The count was the gate and the 3 was
the direction, and both described one particular room.

Safety: the children run through `env -i` with the stub directory as the
ONLY entry on PATH. The console device the script writes to is named once
in the script and overridden here to a file inside tmp_path - a test that
reached the real /sys/class/graphics/fbcon/rotate_all would rotate the
console of the machine running it.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# The shared backstop, from tests/conftest.py: a command the stub
# directory does not provide has to be a failure, not an empty string.
import conftest

SRC = Path(__file__).resolve().parents[2] / "src"
TEMPLATE = SRC / "templates" / "tty-monitor-rotation-config.template"

BASH = "/bin/bash"
ENV = "/usr/bin/env"

PANEL = "Panel Works Internal 0001"
SCREEN = "Screen Co Model X 1111"

PASSTHROUGH = ("cat", "rm")
RECORDED = ("chvt", "fgconsole", "clear", "sleep")


def _entry(name, description, x, **overrides):
    entry = {
        "name": name, "description": description, "x": x, "y": 0,
        "width": 3840, "height": 2160, "refreshRate": 60.0,
        "scale": 1.0, "transform": 0,
    }
    entry.update(overrides)
    return entry


@pytest.fixture
def generate(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(SRC))
    import template_processor

    def build() -> Path:
        path = tmp_path / "tty-monitor-rotation.sh"
        template_processor.ConfigProcessor().apply_template(
            SRC / "templates" / "tty-monitor-rotation-config.template", path)
        path.chmod(0o755)
        return path

    return build


def _stubs(tmp_path: Path, monitors) -> Path:
    stubs = tmp_path / "stubs"
    stubs.mkdir()

    payload = tmp_path / "monitors.json"
    payload.write_text(json.dumps(monitors), encoding="utf-8")
    hyprctl = stubs / "hyprctl"
    hyprctl.write_text(
        "#!/bin/bash\n"
        "# Test stub. Never reaches the real compositor.\n"
        f"exec /bin/cat '{payload}'\n", encoding="utf-8")
    hyprctl.chmod(0o755)

    for name in RECORDED:
        stub = stubs / name
        stub.write_text("#!/bin/bash\nprintf '1\\n'\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)

    for name in PASSTHROUGH:
        real = shutil.which(name)
        assert real, f"the script needs {name}"
        stub = stubs / name
        stub.write_text(f'#!/bin/bash\nexec "{real}" "$@"\n', encoding="utf-8")
        stub.chmod(0o755)

    python3 = stubs / "python3"
    python3.write_text(f'#!/bin/bash\nexec "{sys.executable}" "$@"\n',
                       encoding="utf-8")
    python3.chmod(0o755)
    return stubs


def _run(script: Path, args, stubs: Path, console: Path, tmp_path: Path):
    path = str(stubs)
    assert path.split(os.pathsep) == [str(stubs)]
    assert not os.environ.get("PATH", "").startswith(path)
    assert console.parent == tmp_path or tmp_path in console.parents, (
        "the console file has to live inside tmp_path")
    result = subprocess.run(
        [ENV, "-i", f"PATH={path}", f"HOME={tmp_path}", f"TMPDIR={tmp_path}",
         f"FBCON_ROTATE={console}", BASH, str(script), *args],
        env={}, input="", capture_output=True, text=True, timeout=60)
    conftest.assert_no_missing_command(result, "the rotation script")
    return result


@pytest.fixture
def console(tmp_path):
    """Stands in for /sys/class/graphics/fbcon/rotate_all."""
    path = tmp_path / "rotate_all"
    path.write_text("0\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------
# what the file says
# --------------------------------------------------------------------

def test_the_script_describes_no_particular_desk():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "Dell" not in text
    assert "3 portrait monitors" not in text
    assert "card*-DP-*" not in text, (
        "counting DP connectors is the desk again: it says nothing about "
        "whether a screen stands on its side")


# --------------------------------------------------------------------
# the direction comes from the screens
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
@pytest.mark.parametrize("transform, expected", [(1, "3"), (3, "1"), (2, "2")])
def test_the_console_turns_the_way_the_screens_do(
        generate, tmp_path, console, transform, expected):
    """fbcon counts its rotation the opposite way round from wl_output.

    wl_output's transform is the compensation the compositor applies, and
    fbcon's number names the direction the console text is turned, so the
    two are mirror images: transform 1 needs fbcon 3 and transform 3
    needs fbcon 1. That pairing is not a guess - it is what the origin's
    desk used. Its portrait screens were the ones its waybar script
    counted with `select(.transform == 1)`, and the value it wrote here
    was 3.
    """
    script = generate()
    stubs = _stubs(tmp_path, [_entry("DP-1", SCREEN, 0, transform=transform)])

    result = _run(script, ["rotate"], stubs, console, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert console.read_text(encoding="utf-8").strip() == expected


@pytest.mark.allow_subprocess
def test_one_portrait_screen_is_enough(generate, tmp_path, console):
    """The count gate, gone. A single screen standing on its side leaves
    exactly the sideways console this script exists to fix - and the
    origin refused to touch it, because two more were missing."""
    script = generate()
    stubs = _stubs(tmp_path, [
        _entry("eDP-1", PANEL, 0, width=1920, height=1200),
        _entry("DP-1", SCREEN, 1920, transform=1),
    ])

    result = _run(script, ["rotate"], stubs, console, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert console.read_text(encoding="utf-8").strip() == "3"


@pytest.mark.allow_subprocess
def test_three_upright_screens_are_left_alone(generate, tmp_path, console):
    """The other half of the same mistake: three DP connectors used to be
    reason enough to turn the console sideways."""
    script = generate()
    stubs = _stubs(tmp_path, [
        _entry("DP-1", SCREEN, 0),
        _entry("DP-2", SCREEN, 3840),
        _entry("DP-3", SCREEN, 7680),
    ])

    result = _run(script, ["rotate"], stubs, console, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert console.read_text(encoding="utf-8").strip() == "0", (
        "nothing stands on its side, so nothing may be rotated")


# --------------------------------------------------------------------
# when the compositor cannot be asked
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_an_unreachable_compositor_asks_instead_of_guessing(
        generate, tmp_path, console):
    """A TTY is exactly where Hyprland may not be running.

    Guessing a direction there is how the console ends up upside down
    with no session to fix it from, so the script says what it needs.
    """
    script = generate()
    stubs = _stubs(tmp_path, [_entry("DP-1", SCREEN, 0, transform=1)])
    (stubs / "python3").write_text("#!/bin/bash\nexit 1\n", encoding="utf-8")
    (stubs / "python3").chmod(0o755)

    result = _run(script, ["rotate"], stubs, console, tmp_path)

    assert result.returncode == 1
    assert "90" in result.stdout, "the message has to name a usable angle"
    assert console.read_text(encoding="utf-8").strip() == "0"


@pytest.mark.allow_subprocess
def test_an_explicit_angle_needs_no_compositor(generate, tmp_path, console):
    script = generate()
    stubs = _stubs(tmp_path, [_entry("DP-1", SCREEN, 0, transform=1)])
    (stubs / "python3").write_text("#!/bin/bash\nexit 1\n", encoding="utf-8")
    (stubs / "python3").chmod(0o755)

    result = _run(script, ["rotate", "270"], stubs, console, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert console.read_text(encoding="utf-8").strip() == "1"


@pytest.mark.allow_subprocess
def test_an_angle_that_is_not_a_quarter_turn_is_refused(
        generate, tmp_path, console):
    script = generate()
    stubs = _stubs(tmp_path, [_entry("DP-1", SCREEN, 0)])

    result = _run(script, ["rotate", "45"], stubs, console, tmp_path)

    assert result.returncode == 1
    assert console.read_text(encoding="utf-8").strip() == "0", (
        "an unusable angle may not reach the console")


@pytest.mark.allow_subprocess
def test_reset_puts_the_console_back(generate, tmp_path, console):
    script = generate()
    console.write_text("3\n", encoding="utf-8")
    stubs = _stubs(tmp_path, [_entry("DP-1", SCREEN, 0, transform=1)])

    result = _run(script, ["reset"], stubs, console, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert console.read_text(encoding="utf-8").strip() == "0"
