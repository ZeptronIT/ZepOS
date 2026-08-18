# SPDX-License-Identifier: GPL-3.0-or-later
"""Ein vollstaendiger `--all`-Lauf in einem eigenen Heimatverzeichnis.

WOHER DAS KOMMT
    tests/src/test_reference_resolution.py hat das hier zuerst gebraucht
    und in seinem Kopf begruendet. Als tests/src/test_usable_desktop.py
    denselben Baum brauchte - dieselbe Frage, eine Ebene weiter: nicht
    "gibt es die Datei, die diese Zeile nennt", sondern "gibt es das
    PROGRAMM, das diese Zeile nennt" -, gab es zwei Moeglichkeiten: den
    Lauf ein zweites Mal hinschreiben, oder ihn einmal hinschreiben.

    Zwei Kopien eines Generatorlaufs sind zwei Kopien, die
    auseinanderlaufen, sobald jemand eine davon anfasst. Und die, die
    nicht angefasst wurde, ist dann die, die still etwas anderes misst -
    dieselbe Begruendung, aus der tests/gtk4_headless.py existiert.

DIE GEFAEHRLICHE HAELFTE, und sie ist der Grund, aus dem hier ueberhaupt
eine Datei steht statt eines Fixtures in einer conftest.py
    Der Generator startet am Ende eines `--all`-Laufs die Oberflaeche
    neu: `ags quit`, dann `pkill -f "gjs.*ags"`. HOME umzubiegen hilft
    dagegen NICHTS - pkill sucht im Prozessbaum der Maschine und findet
    das AGS des Entwicklers, der gerade daneben arbeitet. Genau das ist
    am 11.08.2026 passiert.

    stubbed_path() ist die Abwehr, und sie prueft sich selbst: fuer jeden
    Namen in SESSION_COMMANDS wird VOR dem Lauf zugesichert, dass
    shutil.which ihn im Stub-Verzeichnis findet und nicht im echten
    /usr/bin. Ein Stub, der von der echten Datei ueberdeckt wird, ist
    schlimmer als kein Stub.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

BASH = "/bin/bash"

# Anchored on this file, the way every other test does it: pytest can be
# started from anywhere, and a relative Path("src") would measure
# whatever directory that happens to be.
REPOSITORY = Path(__file__).resolve().parent.parent
SRC = REPOSITORY / "src"

# Commands that act on the RUNNING desktop session rather than on a file.
#
# hyprctl is reached, and by a route no reader of generate_config.sh
# would guess: the bar-workspace-detect step runs bar-workspace-detect.sh,
# which runs `python3 monitors.py --bar`, which runs `hyprctl monitors -j`.
# HOME cannot redirect that - hyprctl talks to the compositor over its
# own socket - so an unstubbed run asks the developer's live session for
# its monitor layout and derives the workspace configuration from a desk
# that has nothing to do with the test. Stubbed, monitors.py gets no
# usable answer and the detect script falls back, which is exactly the
# fresh-installation path these files are about.
SESSION_COMMANDS = (
    "ags", "pkill", "pgrep", "systemctl", "dbus-send", "setsid", "kitty",
    "nohup", "hyprctl",
)

# The three directories this project generates into. A reference below
# one of them is a reference to something the run itself was supposed to
# produce; a reference to anything else belongs to the user or to another
# package.
OWNED_SUBDIRECTORIES = (".config", ".local/bin", ".local/share")


class GeneratedTree:
    """One completed `--all`, with the roots it was given."""

    def __init__(self, home: Path):
        self.home = home
        self.config = home / ".config"
        self.user_root = home / ".config" / "zepos"

    def expand(self, text: str) -> str:
        """Resolve the variables a generated artifact writes paths with.

        The generated files do not all spell the same directory the same
        way: hyprland.conf uses `~`, the bar modules use `$HOME`, and
        the ones that have to survive a moved user root carry the full
        `${ZEPOS_USER_ROOT:-${XDG_CONFIG_HOME:-$HOME/.config}/zepos}`.
        All three name one directory, so all three are reduced to it
        before anything is compared - a check that only understood `~`
        would silently skip exactly the references written the careful
        way.
        """
        home = str(self.home)
        text = text.replace(
            "${ZEPOS_USER_ROOT:-${XDG_CONFIG_HOME:-$HOME/.config}/zepos}",
            f"{home}/.config/zepos")
        text = text.replace("${XDG_CONFIG_HOME:-$HOME/.config}", f"{home}/.config")
        text = re.sub(r"\$\{?ZEPOS_USER_ROOT\}?", f"{home}/.config/zepos", text)
        text = re.sub(r"\$\{?XDG_CONFIG_HOME\}?", f"{home}/.config", text)
        text = re.sub(r"\$\{?HOME\}?", home, text)
        # Only a leading ~ is a home directory. "foo~/bar" and "a/~b" are
        # not, and neither is the ~ inside a backup suffix.
        text = re.sub(r"(?<![\w/~])~/", f"{home}/", text)
        return text

    def owned_paths(self, command: str) -> list[str]:
        """Every path in `command` that this project is supposed to have
        written."""
        expanded = self.expand(command)
        pattern = re.escape(str(self.home)) + r"/[\w.@+-]+(?:/[\w.@+-]+)*"
        found = []
        for token in re.findall(pattern, expanded):
            relative = token[len(str(self.home)) + 1:]
            if any(relative == owned or relative.startswith(owned + "/")
                   for owned in OWNED_SUBDIRECTORIES):
                found.append(token)
        return found

    def generated_files(self):
        for path in sorted(self.home.rglob("*")):
            if not path.is_file() or ".cache" in path.parts:
                continue
            yield path

    def read(self, path: Path) -> str:
        return path.read_text(errors="replace")

    def show(self, path: Path) -> str:
        return str(path.relative_to(self.home))


def stubbed_path(root: Path) -> str:
    """A PATH whose session commands are stubs, asserted before use.

    Every generator run in this suite goes through here, so that a second
    caller cannot quietly acquire a weaker guard than the first one.
    """
    stubs = root / "session-stubs"
    stubs.mkdir()
    for name in SESSION_COMMANDS:
        # dbus-send answers the name the generator waits for; without it
        # the wait loop spends five seconds failing to find a session bus
        # that is not there, in a test about files.
        body = ('printf "org.freedesktop.Notifications\\n"\n'
                if name == "dbus-send" else "")
        stub = stubs / name
        stub.write_text(f'#!/bin/bash\necho "stub: {name} $*" >&2\n{body}exit 0\n')
        stub.chmod(0o755)

    path = os.pathsep.join([str(stubs), os.environ["PATH"]])
    for name in SESSION_COMMANDS:
        # Asserted before the first child starts, not hoped for: a stub
        # that is shadowed by the real command is worse than no stub.
        assert shutil.which(name, path=path) == str(stubs / name), (
            f"{name} would reach the real command")
    return path


def build(root: Path) -> GeneratedTree:
    """A complete, successful `--all` inside a temporary home.

    HOME, XDG_CONFIG_HOME and XDG_CACHE_HOME are all redirected, because
    the generator derives its output root, ~/.local/bin and its staging
    area from them; getting any one of them wrong would write into the
    developer's live desktop.
    """
    home = root / "home"
    (home / ".config").mkdir(parents=True)
    (home / ".cache").mkdir()

    # An empty plugin directory, so the whole walk runs against the case
    # the failsafe exists for: no plugin object on the machine at all.
    # Left to /usr/lib/hyprland/plugins the answer would depend on which
    # packages the developer happens to have installed, and the one
    # arrangement that must be proved to produce a session that starts
    # would be the one nobody could be sure had been tested.
    plugins = root / "hyprland-plugins"
    plugins.mkdir()

    result = subprocess.run(
        [BASH, str(SRC / "generate_config.sh"), "--all"],
        env={
            "PATH": stubbed_path(root),
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "ZEPOS_SYSTEM_ROOT": str(SRC),
            "ZEPOS_USER_ROOT": str(home / ".config" / "zepos"),
            "ZEPOS_PLUGIN_ROOT": str(plugins),
        },
        capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, (
        "the run this whole file reads did not finish:\n"
        + result.stdout[-4000:] + result.stderr[-4000:])

    return GeneratedTree(home)
