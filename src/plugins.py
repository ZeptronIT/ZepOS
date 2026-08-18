#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Which Hyprland plugins this machine can load, and what may depend on one.

WHY THERE IS A SEPARATE FILE AT ALL
    Hyprland has no conditional. Three shapes of configuration stop
    working the moment a plugin is not loaded, and all three are errors
    in the one file whose failure costs the user their session:

      plugin = /usr/lib/hyprland/plugins/hyprbars.so   the load line
      plugin { hyprbars { bar_height = 25 } }          an option no
                                                       plugin registered
      bind = SUPER, SPACE, hyprlaunch:toggle,          a dispatcher that
                                                       does not exist

    So none of them live in hyprland.conf. They live in a block in
    hyprland-plugins-config.template, hyprland.conf sources the file this
    module writes out of it, and a block is written only when the object
    it depends on is on the machine. With no objects at all the file
    holds nothing but comments - a Hyprland configuration that parses -
    and the desktop starts without a single plugin. That is the failsafe:
    an ABI mismatch after a Hyprland update costs the feature the plugin
    provided, never the session.

PRESENT WHEN?
    At generation time, and generation is arranged to happen immediately
    before every session.

    It cannot be answered later. Hyprland reads `plugin =` while parsing
    its configuration, before anything ZepOS could run inside the
    session, so "check at session start" can only mean "check before the
    compositor exists" - which is the launcher. start-hyprland already
    regenerates the Hyprland configuration and then execs the compositor;
    it regenerates this file in the same breath, so on the supported
    launch path the answer is at most one exec old.

    What that leaves open is the machine where the objects change without
    a regeneration - a `pacman -Syu` in the middle of a session, or a
    login through a display manager that does not go through
    start-hyprland. That case is not left silent, which is the whole
    condition on choosing generation time:

      * the file itself names every plugin it dropped, with the object it
        looked for, the package that provides it and the command to run
        after installing it;
      * zepos-doctor reads the file that is IN PLACE and reports a load
        line whose object is no longer there (doctor.check_plugin_objects);
      * zepos-doctor reports an ABI drift from inside a running session
        (doctor.check_plugin_abi), which needs `hyprctl version -j` and
        therefore cannot be answered by a generator at all.

WHY NOT hyprpm
    hyprpm compiles the plugins per user, from whatever happens to be on
    five GitHub branches at that moment, into a directory whose name
    depends on the Hyprland revision it built against. A distribution
    that pins its versions cannot have its desktop depend on that, and no
    check in this project could name the resulting object. Spec §7.2
    rejects it; the objects come from packages, at one known path.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import settings

# Where a package puts a compiled plugin (spec §7.2). One definition,
# because validate_output, zepos-doctor and the plugin packages TP3
# writes all have to name the same directory - a check looking somewhere
# else than the package installs to is a check that always passes.
PLUGIN_ROOT = Path("/usr/lib/hyprland/plugins")

# Overridable for the same reason the two roots in paths.py are, and with
# the same warning: this exists for tests and packaging tools, not as
# end-user configuration. Both cases that matter - every object present,
# none present - have to be measurable on one machine, and neither is
# measurable at all against a directory a test cannot write to.
PLUGIN_ROOT_ENV = "ZEPOS_PLUGIN_ROOT"

OBJECT_SUFFIX = ".so"

# The five ABI-coupled plugins of spec §7.1, in load order. hyprbars
# first because it is the one with settings; the rest carry binds.
PLUGINS = ("hyprbars", "borders-plus-plus", "hyprlaunch", "hyprclipx",
           "hyprzones")

# The generator target that rewrites the file, named in every comment
# this module writes: a user who has just installed a plugin package
# needs the command, not the knowledge that one exists.
GENERATOR_TARGET = "zepos-generate -hyprland-plugins-config"

# The block markers, in Hyprland's own comment syntax so that a template
# carrying them is still a readable configuration file.
#
#   # zepos-plugin <name>          kept only when <name> can be loaded
#   # zepos-plugin-missing <name>  kept only when it cannot
#   # zepos-plugin-end             closes either
#
# The "missing" form is not decoration: SUPER+SPACE is the application
# launcher, and a desktop whose launcher is a dead key is very close to a
# desktop that did not start.
BEGIN = re.compile(r"^[ \t]*#[ \t]*zepos-plugin[ \t]+(\S+)[ \t]*$")
BEGIN_MISSING = re.compile(r"^[ \t]*#[ \t]*zepos-plugin-missing[ \t]+(\S+)[ \t]*$")
END = re.compile(r"^[ \t]*#[ \t]*zepos-plugin-end[ \t]*$")


class MalformedTemplate(ValueError):
    """A marker this module cannot act on.

    Raised rather than skipped, because every way of getting a marker
    wrong produces the SAME output as a plugin that is merely not
    installed: a block that quietly disappears. A user would then be
    looking for a missing package to explain a typo.
    """


def plugin_root() -> Path:
    override = os.environ.get(PLUGIN_ROOT_ENV)
    return Path(override) if override else PLUGIN_ROOT


def object_path(name: str) -> Path:
    return plugin_root() / f"{name}{OBJECT_SUFFIX}"


# Der Sammler hinter hyprclipx, und der Grund, aus dem dieses Modul
# ueberhaupt auf etwas anderes als ein Objekt sieht.
#
# WAS DIE PRUEFUNG UEBER DEM OBJEKT UEBERSAH
#     Jede Zeile darueber fragt "gibt es die .so". Fuer vier der fuenf
#     Plugins ist das die ganze Frage: das Objekt IST das Plugin. Bei
#     hyprclipx ist es die kleinere Haelfte. Das Fenster fragt einen
#     Unix-Socket nach dem Verlauf, und wer den Socket bedient, ist ein
#     eigenes Programm - der Sammler.
#
#     Der Ausfall sieht deshalb aus wie ein Erfolg: das Objekt ist da,
#     also wird geladen, also steht der Dispatcher, also oeffnet
#     SUPER+SHIFT+V ein Fenster. Ein leeres. Ohne Fehlermeldung, ohne
#     Zeile im Protokoll, mit dem richtigen Stil und der richtigen
#     Groesse. GEMESSEN am 12.08.2026: bis zu diesem Tag lieferte kein
#     Paket den Sammler aus, also war das der Zustand JEDER
#     Installation.
#
# WARUM DER RUECKFALL BESSER IST ALS DAS LEERE FENSTER
#     Weil es ihn gibt und weil er etwas anzeigt. Faellt hyprclipx aus,
#     schreibt hyprland-plugins-config.template den
#     zepos-plugin-missing-Block, und der bindet SUPER+SHIFT+V auf
#     cliphist-menu.sh - denselben Verlauf, den `wl-paste --watch
#     cliphist store` seit der Anmeldung sammelt, mit Favoriten. Ein
#     Verlauf mit fremdem Aussehen schlaegt einen leeren im eigenen.
#
# WARUM NUR HIER UND KEIN ALLGEMEINER MECHANISMUS
#     Weil genau ein Plugin eine zweite Haelfte hat. Eine Tabelle
#     "Plugin -> weitere Bedingungen" mit einem Eintrag ist der Katalog,
#     gegen den dieses Projekt an einem Dutzend Stellen argumentiert:
#     sie beschreibt eine Allgemeinheit, die es nicht gibt, und macht
#     die eine Bedingung schwerer zu finden statt leichter.
COLLECTOR = Path("/usr/lib/hyprclipx/collector.py")
COLLECTOR_ENV = "ZEPOS_HYPRCLIPX_COLLECTOR"
COLLECTOR_OWNER = "hyprclipx"


def collector_path() -> Path:
    override = os.environ.get(COLLECTOR_ENV)
    return Path(override) if override else COLLECTOR


def package(name: str) -> str:
    """The package that provides the object (spec §4.2, §4.3)."""
    return f"zepos-{name}"


def enabled_in_settings() -> bool:
    """Whether the user wants plugins at all.

    The installer asks this (spec §8.2 step 6) and writes
    plugins.enabled into user-settings.json. Until this function existed
    nothing read it back: the question was asked, stored, carried into
    the installed system by installer/core/usersettings.py - and every
    plugin loaded either way.

    A document without the section means yes. A fresh installation has no
    settings file at all, and every file written before the section
    existed lacks it; reading silence as "off" would switch the desktop's
    features off on exactly those machines.
    """
    section = settings.load().get("plugins")
    if not isinstance(section, dict):
        return True
    return bool(section.get("enabled", True))


def unavailable(*, enabled: bool | None = None) -> dict[str, str]:
    """Every plugin that must not be loaded, and why, in German.

    An empty dict means every plugin on the roster can be loaded. The
    reason is German because it is written into the generated file, which
    the user reads.
    """
    if enabled is None:
        enabled = enabled_in_settings()

    reasons: dict[str, str] = {}
    for name in PLUGINS:
        if not enabled:
            reasons[name] = ("Plugins sind in den Nutzereinstellungen "
                             "abgeschaltet (plugins.enabled = false).")
            continue
        target = object_path(name)
        if not target.is_file():
            reasons[name] = f"{target} ist nicht vorhanden."
            continue
        # Die zweite Haelfte, und nur dieses eine Plugin hat eine. Die
        # Begruendung steht bei COLLECTOR.
        if name == COLLECTOR_OWNER:
            collector = collector_path()
            if not collector.is_file():
                reasons[name] = (
                    f"{collector} ist nicht vorhanden - ohne den Sammler "
                    f"bliebe der Verlauf leer.")
    return reasons


def _explain(name: str, reason: str) -> list[str]:
    """The comment that replaces a block that was dropped.

    A feature that disappears without a word is precisely the failure
    zepos-doctor exists to break, and the file that dropped it is the
    cheapest place to say so.
    """
    return [
        f"# --- {name}: nicht geladen ---",
        f"# Grund:   {reason}",
        "# Folge:   Die Funktionen dieses Plugins fehlen. Die Sitzung",
        "#          startet trotzdem - genau dafuer steht dieser Block hier.",
        f"# Abhilfe: Paket {package(name)} installieren, danach",
        f"#          `{GENERATOR_TARGET}` ausfuehren.",
    ]


def render(text: str, *, reasons: dict[str, str] | None = None) -> str:
    """The template with every block resolved against this machine.

    The load line is written HERE rather than in the template, so that
    the path in the file is by construction the path that was just
    checked. A template spelling it out could name a second directory,
    and the check would then be about a file the configuration does not
    load.
    """
    if reasons is None:
        reasons = unavailable()

    out: list[str] = []
    body: list[str] = []
    block: tuple[str, bool, int] | None = None

    for number, line in enumerate(text.splitlines(), 1):
        begin = BEGIN.match(line)
        missing = BEGIN_MISSING.match(line)

        if begin or missing:
            if block is not None:
                raise MalformedTemplate(
                    f"line {number}: a zepos-plugin block inside another one")
            name = (begin or missing).group(1)
            if name not in PLUGINS:
                raise MalformedTemplate(
                    f"line {number}: {name!r} is not one of the plugins this "
                    f"project ships ({', '.join(PLUGINS)})")
            block = (name, begin is not None, number)
            body = []
            continue

        if END.match(line):
            if block is None:
                raise MalformedTemplate(
                    f"line {number}: zepos-plugin-end closes no block")
            name, wants_present, _start = block
            absent = name in reasons
            if wants_present and not absent:
                out.append(f"plugin = {object_path(name)}")
                out.extend(body)
            elif wants_present:
                out.extend(_explain(name, reasons[name]))
            elif absent:
                out.extend(body)
            block = None
            body = []
            continue

        (body if block is not None else out).append(line)

    if block is not None:
        raise MalformedTemplate(
            f"line {block[2]}: the zepos-plugin block for {block[0]} is never "
            f"closed")

    return "\n".join(out) + "\n"


USAGE = """usage: plugins.py filter <file>

Rewrites <file> in place, keeping only the plugin blocks whose object is
on this machine. Called by generate_config.sh after the template
processor has substituted the icons and styles, so the block bodies are
already finished configuration by the time they are kept or dropped."""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv in (["-h"], ["--help"]):
        print(USAGE)
        return 0
    if len(argv) != 2 or argv[0] != "filter":
        print(USAGE, file=sys.stderr)
        return 2

    target = Path(argv[1])
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"{target} cannot be read: {exc}", file=sys.stderr)
        return 1

    try:
        rendered = render(text)
    except MalformedTemplate as exc:
        # A broken marker is a broken installation or a broken user
        # override, not a configuration choice, so the run stops here and
        # the previous configuration stays in place.
        print(f"{target}: {exc}", file=sys.stderr)
        return 1
    except settings.UnusableSettings as exc:
        print(f"{exc}", file=sys.stderr)
        return 1

    try:
        target.write_text(rendered, encoding="utf-8")
    except OSError as exc:
        print(f"{target} cannot be written: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
