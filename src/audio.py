# SPDX-License-Identifier: GPL-3.0-or-later
"""Which audio device the desktop routes through, and whether it is there.

The origin wrote four of the author's own devices into the two audio
templates: a headset and a webcam by the ALSA node names their USB
product strings produce, a microphone by its product name, and a pair of
headphones by their Bluetooth address. A PipeWire node name belongs to
one machine's hardware, so on anybody else's desk each of those rules
matched nothing.

That is the failure this module exists to make impossible, and it is
worse than it sounds, because a WirePlumber rule whose match never fires
is INDISTINGUISHABLE from one that fires: the file parses, the daemon
starts, no message is written anywhere. The user is told the microphone
is filtered and the webcam is kept out of the way, and neither is true.

So, exactly as monitors.py does it for screens:

  * The names come from the user settings - never from this source.
  * Nothing is guessed. An unset device means "let PipeWire decide",
    which is the shipping state and a perfectly good desktop.
  * What is actually attached is a question only the sound server can
    answer, and `--check` asks it: every configured name is reported as
    matching something or matching nothing, by name, with a non-zero
    exit for the second case.

WHAT ANSWERS "WHAT IS ATTACHED"
    `pactl list short sources` prints the node name - the exact string a
    WirePlumber rule and EasyEffects both key on - as its second column.
    That is the only place that string is available in machine-readable
    form, so it is the first choice.

    Where pipewire-pulse is not installed pactl does not exist, and
    wireplumber's own `wpctl` does: `wpctl status` lists the nodes by
    their human-readable DESCRIPTION and `wpctl inspect <id>` reports the
    node.name of one of them. Two calls instead of one, for a tool that
    is by definition present on a machine whose WirePlumber configuration
    we are generating.

    When neither answers, detect() raises. "The sound server could not be
    asked" and "the device is not attached" are different statements and
    only one of them is a reason to warn the user about their settings.
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Callable, Iterable

# Loaded both ways, exactly as settings.py's own header describes: as
# `src.audio` from the test suite, where src is a package, and as `audio`
# from /usr/share/zepos, where every module sits flat beside every other.
try:
    from .paths import user_root
    from .settings import FILENAME as SETTINGS_FILENAME
    from .settings import UnusableSettings
    from .settings import load as read_settings_document
    from .vpn import nonblank_entries
except ImportError:
    from paths import user_root
    from settings import FILENAME as SETTINGS_FILENAME
    from settings import UnusableSettings
    from settings import load as read_settings_document
    # The one reader for a settings value that is a LIST, shared rather
    # than reimplemented: a string where a list belongs is walked
    # character by character by every iteration that accepts it, and one
    # refusal for that shape is the difference between a named error and
    # a node rule per letter.
    from vpn import nonblank_entries

Runner = Callable[..., subprocess.CompletedProcess]

# The two kinds of node a rule can name. WirePlumber calls them by their
# PipeWire media class; pactl and wpctl both group them under these two
# headings.
SOURCE = "source"
SINK = "sink"


@dataclass(frozen=True)
class Node:
    """One audio node, reduced to what a rule can key on.

    `name` is the node.name - the identifier a WirePlumber rule matches
    and EasyEffects stores. `description` is what a person recognises the
    device by, and is carried only so that a report can say WHICH device
    a name belongs to; nothing keys on it.
    """

    name: str
    kind: str
    description: str = ""


def _run(runner: Runner, command: list[str]) -> str:
    """One command's stdout, or "" for anything that means "no answer".

    Not raising here is deliberate: this module tries two tools in turn,
    and the first one being absent is the ordinary case rather than a
    fault. detect() raises once, after both have failed.
    """
    try:
        result = runner(command, capture_output=True, text=True)
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout or ""


def _from_pactl(runner: Runner) -> list[Node]:
    """Every node pactl knows, from its short listing.

    `pactl list short sources` is tab-separated: index, node name,
    driver, sample spec, state. Only the name is taken; the sample spec
    changes with whatever last opened the device and says nothing about
    identity.
    """
    nodes: list[Node] = []
    for kind, argument in ((SOURCE, "sources"), (SINK, "sinks")):
        output = _run(runner, ["pactl", "list", "short", argument])
        for line in output.splitlines():
            fields = line.split("\t")
            if len(fields) < 2 or not fields[1].strip():
                continue
            nodes.append(Node(name=fields[1].strip(), kind=kind))
    return nodes


# A line of `wpctl status` that names a node: some tree drawing, the id,
# a dot, and the description up to the volume or the format in brackets.
_WPCTL_ENTRY = re.compile(r"^[^0-9]*?(\d+)\.\s+(.*?)(?:\s*\[[^\]]*\])?\s*$")
# The two headings whose entries are the nodes; everything under any
# other heading (Devices, Streams, Filters) is not one.
_WPCTL_HEADINGS = {"Sinks:": SINK, "Sources:": SOURCE}
# How `wpctl inspect` reports one property.
_WPCTL_PROPERTY = re.compile(r'^\s*[|*\s]*node\.name\s*=\s*"([^"]*)"')


def _from_wpctl(runner: Runner) -> list[Node]:
    """Every node wpctl knows, at the cost of one call per node.

    `wpctl status` has no machine-readable mode and prints descriptions,
    not node names, so the id of each entry is looked up with `wpctl
    inspect`. An entry whose inspect call says nothing is dropped rather
    than kept under its description: a rule keyed on a description
    matches nothing, which is the failure this module exists to prevent.
    """
    status = _run(runner, ["wpctl", "status"])
    if not status:
        return []

    nodes: list[Node] = []
    kind = ""
    for line in status.splitlines():
        stripped = line.strip(" │├└─\t")
        if stripped in _WPCTL_HEADINGS:
            kind = _WPCTL_HEADINGS[stripped]
            continue
        if not kind:
            continue
        # A blank line ends a section. Without this the entries of the
        # next heading - Filters, Streams - would be read as sources.
        if not stripped:
            kind = ""
            continue
        entry = _WPCTL_ENTRY.match(line)
        if not entry:
            continue
        identifier, description = entry.group(1), entry.group(2).strip()
        for property_line in _run(
                runner, ["wpctl", "inspect", identifier]).splitlines():
            found = _WPCTL_PROPERTY.match(property_line)
            if found and found.group(1).strip():
                nodes.append(Node(name=found.group(1).strip(), kind=kind,
                                  description=description))
                break
    return nodes


def detect(*, runner: Runner | None = None) -> list[Node]:
    """Every audio node the running sound server reports.

    Raises RuntimeError when neither tool answered - it is not running,
    neither is installed, both calls failed. One exception type, because
    a caller can do exactly one thing about all of them: say that it
    could not check rather than that the device is missing.
    """
    # Resolved here, not bound as a default: a default argument captures
    # subprocess.run at import time, which the test suite's isolation
    # guard cannot intercept.
    runner = runner or subprocess.run

    nodes = _from_pactl(runner)
    if not nodes:
        nodes = _from_wpctl(runner)
    if not nodes:
        raise RuntimeError(
            "neither pactl nor wpctl reported an audio node - PipeWire is "
            "not running, or neither tool is installed")
    return nodes


# --------------------------------------------------------------------
# what goes into the generated configuration
# --------------------------------------------------------------------
#
# Both renderings below take the settings and nothing else. They are
# called while a configuration is GENERATED, which routinely happens
# during installation and from a TTY, where there is no sound server to
# ask - so neither of them may depend on one. Whether the names still
# match anything is a separate question, asked separately, by --check.

# What WirePlumber is told when the user has configured nothing. A
# comment rather than an empty file: somebody opening
# ~/.config/wireplumber/wireplumber.conf.d/ and finding a file with no
# content in it cannot tell "nothing configured" from "generation
# failed".
NOTHING_CONFIGURED = (
    "# Nothing is configured, so nothing is overridden here and PipeWire\n"
    "# keeps its own choice of default devices. This is the shipping\n"
    "# state, not a fault."
)


def settings_section(document: dict[str, Any] | None = None) -> dict[str, Any]:
    """The audio section of the user settings, or an empty one."""
    if document is None:
        document = _load()
    section = document.get("audio")
    return section if isinstance(section, dict) else {}


def _text(section: dict[str, Any], key: str) -> str:
    value = section.get(key)
    return "" if value is None else str(value).strip()


def blocked_sources(section: dict[str, Any]) -> list[str]:
    """The source node names that must not be connected automatically."""
    return nonblank_entries(section.get("blocked_sources"),
                            setting="audio.blocked_sources")


def default_devices_block(section: dict[str, Any]) -> str:
    """The `wireplumber.settings` block, holding only what is configured.

    A key is written only when it has a value. `default.configured.audio.sink`
    pointing at a node that does not exist is not a no-op - it is a
    default device nothing can play through, which is silence with no
    error, and that is precisely what the origin's file did on every
    machine but one.
    """
    lines = []
    sink = _text(section, "default_sink")
    source = _text(section, "default_source")
    if sink:
        lines.append(f'  default.configured.audio.sink = "{sink}"')
    if source:
        lines.append(f'  default.configured.audio.source = "{source}"')
    if not lines:
        return NOTHING_CONFIGURED

    # Only meaningful beside a pinned default: they stop an application
    # and a newly appeared device from moving the stream off the device
    # the user chose. Written with the defaults rather than always, so a
    # machine that pins nothing is left entirely alone.
    lines.append("  linking.allow-moving-streams = false")
    lines.append("  linking.follow-default-target = true")
    return "wireplumber.settings = {\n" + "\n".join(lines) + "\n}"


def node_rules_block(section: dict[str, Any]) -> str:
    """One `node.rules` entry per blocked source, or a comment.

    The empty case must not emit `node.rules = [ ]`: an empty rule list
    is valid, does nothing, and reads to anyone opening the file as if
    rules were in force.
    """
    names = blocked_sources(section)
    if not names:
        return ("# No source is blocked. `audio.blocked_sources` in the user\n"
                "# settings is the list of node names that must never be\n"
                "# connected automatically.")

    blocks = []
    for name in names:
        blocks.append(
            "  {\n"
            "    matches = [\n"
            f'      {{ node.name = "{name}" }}\n'
            "    ]\n"
            "    actions = {\n"
            "      update-props = {\n"
            "        node.autoconnect = false\n"
            "      }\n"
            "    }\n"
            "  }")
    return "node.rules = [\n" + "\n".join(blocks) + "\n]"


# --------------------------------------------------------------------
# is any of it still there
# --------------------------------------------------------------------

# Every setting that names a device, with the dotted key a user would
# correct it under. A single table, so a key added to the schema cannot
# be forgotten by the check that is supposed to police it.
DEVICE_SETTINGS = (
    ("default_sink", SINK),
    ("default_source", SOURCE),
    ("effects_input", SOURCE),
)


def configured_names(section: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(dotted key, node name, kind) for every device the user named."""
    found = []
    for key, kind in DEVICE_SETTINGS:
        value = _text(section, key)
        if value:
            found.append((f"audio.{key}", value, kind))
    for name in blocked_sources(section):
        found.append(("audio.blocked_sources", name, SOURCE))
    return found


def report(section: dict[str, Any], nodes: Iterable[Node]) -> tuple[str, bool]:
    """What every configured name currently matches, and whether all do.

    Returns the text and True when every configured name was found. The
    kind is checked as well as the name: a sink node named as a source
    is a rule that never fires just as surely as a name nothing carries,
    and it is the likelier mistake of the two once someone copies a name
    out of the wrong listing.
    """
    configured = configured_names(section)
    if not configured:
        return ("No audio device is named in the settings, so nothing here "
                "can fail to match.\n"), True

    present = {(node.name, node.kind) for node in nodes}
    by_name = {node.name for node in nodes}
    lines = []
    complete = True
    for key, name, kind in configured:
        if (name, kind) in present:
            lines.append(f"ok      {key}: {name}")
        elif name in by_name:
            complete = False
            lines.append(f"WRONG   {key}: {name} exists, but not as a {kind}")
        else:
            complete = False
            lines.append(f"MISSING {key}: {name} matches no attached device")
    if not complete:
        lines.append("")
        lines.append(
            "A rule naming a device that is not there does nothing at all, "
            "and says so nowhere.\n"
            "`pactl list short sources` prints the node name of every "
            "attached device in its\nsecond column; `wpctl status` shows the "
            "same devices by their descriptions.")
    return "\n".join(lines) + "\n", complete


def _load() -> dict[str, Any]:
    """The user settings, or an empty document when there are none.

    No file is the normal state of a fresh installation. A file that
    cannot be read is not, and it is re-raised carrying its own path -
    the caller prints one line and exits, and "unsupported schema_version
    None" names none of the files on a machine.
    """
    target = user_root() / SETTINGS_FILENAME
    if not target.is_file():
        return {}
    try:
        return read_settings_document(target)
    except (ValueError, OSError) as exc:
        raise UnusableSettings(f"{target} cannot be read: {exc}") from exc


USAGE = """usage: audio.py --list
       audio.py --check

--list   every audio node the sound server reports, one per line:
         kind, node name, description.
--check  every device named in the user settings, and whether it still
         matches something attached. Exits 1 when one of them does not."""


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    mode = argv[0] if argv else None
    if mode not in ("--list", "--check"):
        print(USAGE, file=sys.stderr)
        return 2

    if mode == "--list":
        try:
            nodes = detect()
        except RuntimeError as exc:
            print(f"could not ask PipeWire what is attached: {exc}",
                  file=sys.stderr)
            return 1
        for node in sorted(nodes, key=lambda n: (n.kind, n.name)):
            print(f"{node.kind}\t{node.name}\t{node.description}")
        return 0

    try:
        section = settings_section()
        # Asked only when there is something to check. A machine that
        # names no device has nothing that can fail to match, and
        # reporting "PipeWire could not be asked" at it - during
        # installation, from a TTY - would be a warning about a
        # configuration nobody made.
        nodes = detect() if configured_names(section) else []
        text, complete = report(section, nodes)
    except UnusableSettings as exc:
        print(exc, file=sys.stderr)
        return 1
    except RuntimeError as exc:
        # Not a failure of the settings. Reporting this as "the device is
        # missing" would send the user to change a setting that is
        # correct, which is worse than saying nothing.
        print(f"could not check the configured devices: {exc}\n"
              f"The settings themselves are unchanged and may well be right.",
              file=sys.stderr)
        return 1
    print(text, end="")
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
