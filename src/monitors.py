# SPDX-License-Identifier: GPL-3.0-or-later
"""Which workspace lives on which screen, decided by what is plugged in.

The origin matched the machine's hostname against a list of known
workstations and, for one of them, wrote three monitor serial numbers into
the generated configuration. That works on exactly those machines and
nowhere else; everybody else fell through to a fallback. What is actually
attached is a question only the compositor can answer.

What this module produces are WORKSPACE ASSIGNMENTS - `workspace=N,monitor:X`
- and nothing else. Monitor modes (`monitor=desc:...,1920x1200@60,...`)
live in ~/.config/hypr/monitors.conf, which src/displays.py owns - the
"Bildschirme" page of the settings application writes it. A second
writer emitting mode lines would fight that page over the same setting,
and the user would have no way to tell which one won.

The two modules meet in exactly one place: how a monitor is NAMED in a
Hyprland rule. selector() below answers that, and displays.py calls it
rather than deciding again - two answers to that question are two rules
matching two different screens, which the user meets as workspaces on a
screen where no window ever opens.

Run as a script it writes that block to stdout, which is how
hypr-monitor-detect.sh uses it. `zepos-generate` will import the same two
functions rather than parsing that output.

Two more renderings of the SAME layout live here, for the artifacts that
used to work it out again for themselves:

  --bar     the bar's `persistent-workspaces`. It was derived a second
            time in bar-workspace-detect.sh, from the active profile
            plus three EDID serial numbers. Two derivations of one layout
            disagree as soon as a cable moves, and the user meets that as
            workspace buttons on a screen where the windows never open.
  --list    the geometry of each screen, left to right, for the shell
            scripts that draw something per monitor. They matched the
            EDID vendor field against two manufacturer names to decide
            which screen was which.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Callable, Iterable

Runner = Callable[..., subprocess.CompletedProcess]

# Hyprland's default keybinds bind SUPER+1..0 to these ten, whether a rule
# names them or not. A workspace no rule names opens wherever the focus
# happens to be, so all ten are always handed out.
WORKSPACES = tuple(range(1, 11))

# The workspace the laptop panel keeps for itself when there is at least
# one external screen. It is the last one, so the nine the user works on
# stay together on the big screens.
PANEL_WORKSPACE = WORKSPACES[-1]

# Every internal panel Hyprland has ever named: eDP-1, eDP-2, and LVDS-1
# on hardware old enough to predate embedded DisplayPort.
PANEL_CONNECTORS = ("EDP", "LVDS")


@dataclass(frozen=True)
class Monitor:
    """One entry of `hyprctl monitors -j`, reduced to what the layout needs.

    `name` and `x` are not decoration: without the connector name a laptop
    panel cannot be told from an external screen, and without the position
    the monitors are ordered by whatever sequence the compositor returns -
    which follows the order they were plugged in, so "the left one" ends up
    being whichever cable went in first.

    `transform` is read for the safety check in the generated script,
    which refuses a layout in which every screen is rotated.
    """

    name: str
    description: str
    x: int
    width: int
    height: int
    refresh: float
    scale: float
    transform: int
    # Where the top edge of this screen sits in the layout. Last, and
    # defaulted, so that every existing construction of a Monitor keeps
    # working - it is needed by exactly one caller and would otherwise
    # have to be threaded through all of them.
    #
    # Hyprland's `movewindowpixel exact` takes LAYOUT coordinates, not
    # coordinates on the screen, so anything that places a window on a
    # particular monitor needs the monitor's origin. `x` alone is enough
    # for a desk whose screens stand side by side and wrong for one where
    # they do not.
    y: int = 0

    @property
    def is_panel(self) -> bool:
        return self.name.upper().startswith(PANEL_CONNECTORS)

    @property
    def is_rotated(self) -> bool:
        """Whether the screen stands on its side.

        wl_output numbers its transforms 0-7, and the odd ones are the
        four that turn the picture by 90 degrees - 1 and 3 for a rotated
        screen, 5 and 7 for a rotated screen that is also mirrored. The
        even ones (0, 2, 4, 6) leave width and height where they are.
        """
        return self.transform % 2 == 1

    @property
    def displayed_size(self) -> tuple[int, int]:
        """Width and height as they appear on the glass.

        `hyprctl` reports the MODE - 3840x2160 for a 4K screen, whether
        it stands upright or on its side. Anything drawn for that screen
        needs the size after the rotation, or a wallpaper for a portrait
        monitor comes out landscape and is scaled to fit.
        """
        if self.is_rotated:
            return self.height, self.width
        return self.width, self.height


def ordered(monitors: Iterable[Monitor]) -> list[Monitor]:
    """The monitors left to right, as they stand on the desk.

    The connector name breaks a tie so that two screens at the same x -
    stacked, or mirrored - always come out in the same order. Without a
    tie-break the layout would differ between two runs on an unchanged
    desk, and the user would meet it as workspaces that moved by
    themselves.
    """
    return sorted(monitors, key=lambda monitor: (monitor.x, monitor.name))


def _number(value: Any, fallback: float) -> float:
    """A numeric field of the compositor's answer, or the fallback.

    `hyprctl monitors -j` has changed shape between Hyprland releases.
    A field that is missing, null or not a number must degrade to a
    default here: this runs from exec-once with nobody watching, and a
    TypeError there is a session that comes up with no workspace rules
    and no message saying why.
    """
    if value is None:
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def detect(*, runner: Runner | None = None) -> list[Monitor]:
    """Every monitor the running compositor reports, left to right.

    Raises RuntimeError for anything that means "the compositor did not
    answer usefully" - it is not running, hyprctl is not installed, the
    call failed, or what came back is not a list of monitors. One
    exception type, because a caller can do exactly one thing about all
    four: fall back.
    """
    # Resolved here, not bound as a default: a default argument captures
    # subprocess.run at import time, which the test suite's isolation
    # guard cannot intercept.
    runner = runner or subprocess.run

    try:
        result = runner(
            ["hyprctl", "monitors", "-j"], capture_output=True, text=True
        )
    except OSError as exc:
        raise RuntimeError(f"could not run hyprctl: {exc}") from exc

    if result.returncode != 0:
        raise RuntimeError(f"hyprctl failed: {(result.stderr or '').strip()}")

    try:
        entries = json.loads(result.stdout)
    except ValueError as exc:
        # JSONDecodeError IS a ValueError, and ValueError is what an empty
        # monitor list is refused with below. Left as it comes out, a
        # caller catching ValueError could not tell a truncated answer
        # from an empty desk, and one catching RuntimeError - the type
        # every other failure here uses - would not catch it at all.
        raise RuntimeError(
            f"hyprctl did not return monitor data: {exc}"
        ) from exc

    if not isinstance(entries, list):
        raise RuntimeError(
            f"hyprctl returned {type(entries).__name__}, not a list of monitors"
        )

    return ordered(
        Monitor(
            name=str(entry.get("name", "") or ""),
            description=str(entry.get("description", "") or ""),
            x=int(_number(entry.get("x"), 0.0)),
            y=int(_number(entry.get("y"), 0.0)),
            width=int(_number(entry.get("width"), 0.0)),
            height=int(_number(entry.get("height"), 0.0)),
            refresh=_number(entry.get("refreshRate"), 0.0),
            scale=_number(entry.get("scale"), 1.0),
            transform=int(_number(entry.get("transform"), 0.0)),
        )
        for entry in entries
        if isinstance(entry, dict)
    )


def _description_prefix(monitor: Monitor) -> str:
    """The part of the description a workspace rule can carry.

    A workspace rule is comma-separated, and EDID vendor strings contain
    commas ("Acme, Inc."). Written out whole, everything after the first
    comma is read as a further rule: Hyprland accepts the line - measured,
    `--verify-config` calls it "config ok" - and then looks for a monitor
    called "desc:Acme", which nobody has. Cutting at the comma keeps the
    rule intact, and Hyprland matches `desc:` by prefix, so the shortened
    form still finds the screen.
    """
    return monitor.description.split(",")[0].strip()


def selector(monitor: Monitor, among: Iterable[Monitor] = ()) -> str:
    """How a Hyprland rule names this monitor.

    The description is preferred: it comes from the EDID, so it survives
    a reboot, a different cable and a different port. The connector name
    does not - unplugging a screen and putting it back into the next port
    renames it.

    But the description is only usable while it is unambiguous. Hyprland
    matches it by PREFIX, so two identical screens whose vendor field
    holds a comma both cut down to the same string, and one of them would
    take every workspace while the other took none. Where that happens the
    connector name is the honest choice: unique today, even though it
    moves with the cable.

    Returns "" for an entry that carries neither - one the compositor
    reported in a shape this code cannot read. Such a monitor cannot be
    named in a rule at all, so it is left out of the layout instead of
    being written into a rule that matches nothing.
    """
    description = _description_prefix(monitor)
    if description:
        ambiguous = any(
            other is not monitor and other.description.startswith(description)
            for other in among
        )
        if not ambiguous:
            return f"desc:{description}"
    return monitor.name.strip()


def layout(monitors: Iterable[Monitor]) -> list[tuple[Monitor, list[int]]]:
    """Which workspaces belong to which monitor, left to right.

    The rule is the origin's two hostname branches generalised, and it
    reproduces both of them: three externals plus a panel gives 1-3, 4-6,
    7-9 and 10; one external plus a panel gives 1-9 and 10. It also
    answers the case the origin could not - any other number of screens,
    on any machine.

    The panel is separated out first because it is the odd one: small,
    often closed, and always present. It keeps the last workspace so the
    nine that matter stay on the big screens. A panel with no external
    beside it is simply the single-monitor case and gets all ten - holding
    nine workspaces back for screens that are not there would leave the
    user unable to reach them.

    Raises ValueError when there is nothing to lay out. An empty answer
    means the query failed rather than that the desk is empty; a monitor
    the compositor described in an unreadable shape cannot be named in a
    rule. Writing an empty block over a working one in either case would
    take the user's workspace layout away and say nothing.
    """
    monitors = list(monitors)
    if not monitors:
        raise ValueError(
            "refusing to write workspace assignments with no monitors - the "
            "query failed, and an empty block would drop the layout the user "
            "already had"
        )

    usable = [m for m in ordered(monitors) if selector(m, monitors)]
    if not usable:
        raise ValueError(
            "no monitor could be named: the compositor reported neither a "
            "description nor a connector name"
        )

    panel = next((m for m in usable if m.is_panel), None)
    externals = [m for m in usable if m is not panel]

    if panel is not None and externals:
        blocks = _spread([n for n in WORKSPACES if n != PANEL_WORKSPACE],
                         externals)
        blocks.append((panel, [PANEL_WORKSPACE]))
        return blocks

    return _spread(list(WORKSPACES), usable)


def _spread(workspaces: list[int],
            monitors: list[Monitor]) -> list[tuple[Monitor, list[int]]]:
    """Contiguous blocks of workspaces over the monitors, in order.

    The leftmost screens take the remainder, which is what makes nine
    workspaces over two screens come out as 1-5 and 6-9 rather than the
    other way round. Monitors left over when there are more screens than
    workspaces get no block rather than an empty one: a rule naming no
    workspace is a line Hyprland has to parse for nothing.
    """
    blocks: list[tuple[Monitor, list[int]]] = []
    size, remainder = divmod(len(workspaces), len(monitors))
    start = 0
    for index, monitor in enumerate(monitors):
        count = size + (1 if index < remainder else 0)
        if count:
            blocks.append((monitor, workspaces[start:start + count]))
        start += count
    return blocks


def workspace_assignments(monitors: Iterable[Monitor]) -> str:
    """The `workspace=` block for ~/.config/hypr/workspaces-generated.conf.

    One comment per monitor naming what it is, so that somebody reading
    the generated file can tell which screen a rule means without looking
    up connector names.
    """
    monitors = list(monitors)
    lines = [
        f"# {len(monitors)} monitor(s) detected, listed left to right.",
        "",
    ]
    for monitor, workspaces in layout(monitors):
        target = selector(monitor, monitors)
        label = monitor.description or monitor.name
        span = (f"workspace {workspaces[0]}" if len(workspaces) == 1
                else f"workspaces {workspaces[0]}-{workspaces[-1]}")
        lines.append(f"# {monitor.name}: {label} ({span})")
        lines.extend(f"workspace={number},monitor:{target}"
                     for number in workspaces)
        lines.append("")
    return "\n".join(lines)


def bar_workspaces(monitors: Iterable[Monitor]) -> dict:
    """The bar's `persistent-workspaces`, out of the same layout().

    The bar resolves these keys against the connector names GDK reports,
    so a monitor is named by its CONNECTOR here while the Hyprland rule
    for the same screen prefers `desc:`. That is not a second answer to the same
    question - it is one answer written in the two dialects the two
    programs read. A `desc:` selector in this file would produce a key
    matching no output, and the workspaces would simply never show up.

    A monitor the compositor reported without a connector name gets a
    Hyprland rule (through its description) but no entry here: there is
    nothing to key it on. An empty key would be a persistent workspace on
    an output called "" - the same "never shows up", plus a configuration
    the bar has to parse.

    `panel-workspace` is the workspace the laptop panel holds alone, or
    None. The generated script turns it into the laptop icon on that
    button, and only that case earns one: a panel with no external beside
    it has all ten, where marking one of them would say nothing.
    """
    monitors = list(monitors)
    blocks = layout(monitors)
    panel_workspace = next(
        (numbers[0] for monitor, numbers in blocks
         if monitor.is_panel and numbers == [PANEL_WORKSPACE]),
        None)
    return {
        "persistent-workspaces": {monitor.name: numbers
                                  for monitor, numbers in blocks
                                  if monitor.name.strip()},
        "panel-workspace": panel_workspace,
    }


def describe(monitors: Iterable[Monitor]) -> str:
    """One line per monitor, left to right, for the shell scripts.

    Columns, separated by single spaces:

        connector  x  transform  width  height  panel|external

    No field can contain a space, so a shell reads the whole thing with a
    bare `while read -r name x transform width height role`. Width and
    height are `displayed_size` - the size after any rotation - because
    every caller so far draws something that has to cover the screen.
    The raw `transform` is kept beside them for the one caller that needs
    the direction rather than the shape: the TTY console rotation.

    Monitors that cannot be named are left out, exactly as in layout():
    a caller cannot address them, and a blank first column would silently
    shift every other field one place to the left.
    """
    monitors = list(monitors)
    lines = []
    for monitor in ordered(monitors):
        if not monitor.name.strip():
            continue
        width, height = monitor.displayed_size
        role = "panel" if monitor.is_panel else "external"
        lines.append(f"{monitor.name} {monitor.x} {monitor.transform} "
                     f"{width} {height} {role}")
    if not lines:
        raise ValueError(
            "no monitor could be named: the compositor reported no connector "
            "names at all")
    return "\n".join(lines) + "\n"


def screen_for_workspace(monitors: Iterable[Monitor], number: int) -> str:
    """Where the screen holding one workspace stands, and how big it is.

        x y width height

    Four fields, space separated, so a shell reads them with a bare
    `read -r x y width height`. Width and height are `displayed_size` -
    the size after any rotation - because every caller is placing
    something that has to fit on the glass.

    Which screen a workspace opens on is decided by layout(), and this
    is that same decision read back rather than a second guess at it. A
    script working it out for itself - "the leftmost screen", "the
    widest one" - disagrees with the workspace rules the moment a cable
    moves, and the user meets that as a window positioned for a screen
    it did not open on.

    Raises ValueError for a workspace no screen holds. Returning a
    fallback screen would put the window somewhere plausible and wrong;
    the caller can say it does not know instead.
    """
    for monitor, numbers in layout(monitors):
        if number in numbers:
            width, height = monitor.displayed_size
            return f"{monitor.x} {monitor.y} {width} {height}\n"
    raise ValueError(f"no screen holds workspace {number}")


# What each mode writes to stdout. Every one of them renders the SAME
# detection - the point of the module is that there is one answer, not
# three.
MODES = {
    None: workspace_assignments,
    "--bar": lambda monitors: json.dumps(bar_workspaces(monitors),
                                            indent=2) + "\n",
    "--list": describe,
}

# Modes that need one further argument. Kept out of MODES because every
# entry there is a function of the monitors alone, and code reading that
# table has to be able to rely on it.
ARGUMENT_MODES = {"--workspace": screen_for_workspace}

USAGE = ("usage: monitors.py ["
         + " | ".join(m for m in MODES if m)
         + " | " + " | ".join(f"{m} <number>" for m in ARGUMENT_MODES) + "]")


def main(argv: list[str] | None = None) -> int:
    """Write one rendering of the detected layout to stdout.

    Failure is reported on stderr with a non-zero status and NOTHING on
    stdout, so a caller redirecting this into a configuration file cannot
    end up with half a block: every caller checks the status and falls
    back to its own crude answer.
    """
    argv = sys.argv[1:] if argv is None else argv
    mode = argv[0] if argv else None

    if mode in ARGUMENT_MODES:
        if len(argv) != 2:
            print(USAGE, file=sys.stderr)
            return 2
        try:
            argument = int(argv[1])
        except ValueError:
            print(f"{mode} takes a workspace number, not {argv[1]!r}",
                  file=sys.stderr)
            return 2
        render = lambda monitors: ARGUMENT_MODES[mode](monitors, argument)
    elif mode in MODES:
        render = MODES[mode]
    else:
        print(USAGE, file=sys.stderr)
        return 2

    try:
        text = render(detect())
    except (RuntimeError, ValueError) as exc:
        print(f"monitor detection failed: {exc}", file=sys.stderr)
        return 1
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
