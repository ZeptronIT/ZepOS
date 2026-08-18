# SPDX-License-Identifier: GPL-3.0-or-later
"""No generated artifact forces the language its output is displayed in.

The origin was one person's German desktop, and the residue of that is a
locale written in front of commands: `LANG=de_DE.UTF-8 date`,
`LANG=de_DE.UTF-8 cal`, `exec env LANG=de_DE.UTF-8 waybar`. It reads like
a guarantee and is not one, measured on this machine:

  * for a format with no words in it - %H:%M, %d.%m.%Y - it changes
    nothing at all;
  * where the locale is not generated, `date` falls back to C silently:
    English weekday names, exit status 0, empty stderr. Nothing in the
    output says the setting was ignored;
  * `LANG` loses to `LC_TIME` and `LC_ALL`, so a user who sets either
    gets their own answer anyway - `LC_TIME=C LANG=de_DE.UTF-8 date +%a`
    prints "Wed".

So a forced display locale does one of two things: nothing, or something
other than what it promises. Meanwhile ZepOS's own installer offers
English (installer/gui/pages.py: "en" -> en_US, UTC), and on such an
installation de_DE.UTF-8 need not exist at all - the bar of a user who
chose English would be asking for a locale their system does not have.

WHAT REPLACES IT
    The session's locale, which the user picked during installation and
    which is therefore generated on their machine. What they actually
    want a say in is the FORMAT, and that is a setting: src/clocks.py
    holds `clocks.format` and its header records the same measurement.

WHY `LANG=C` IS NOT THE SAME THING
    It is the opposite purpose. `LANG=C nmcli -t -f active,ssid ...`
    forces the MACHINE-READABLE form so that the shell around it can
    parse it; that output is never displayed and its stability is the
    whole point. A check that lumped the two together would either have
    to permit the display locales or break every parser in the tree.
"""
import re
from pathlib import Path

# Anchored on this file, like every other test here: pytest can be
# started from anywhere and a relative Path("src") measures whatever
# directory that happens to be.
SRC = Path(__file__).resolve().parents[2] / "src"

# The three directories generate_config.sh reads templates from.
TEMPLATE_SUBDIRECTORIES = ("templates", "styles", "system")

# Any of the variables that decide what language a command speaks.
# LC_TIME is here because it is the specific one for `date` and `cal`,
# and a rule that only knew LANG would be satisfied by moving the same
# mistake one variable across.
LOCALE_ASSIGNMENT = re.compile(r"\b(LANG|LC_ALL|LC_TIME|LC_MESSAGES)=(\S+)")

# The values that ask for the machine-readable form rather than for a
# language. "C.UTF-8" is the same request with a usable character set.
PARSEABLE = {"C", "C.UTF-8", "POSIX"}


def _templates():
    for subdirectory in TEMPLATE_SUBDIRECTORIES:
        yield from sorted((SRC / subdirectory).glob("*.template"))


def _assignments():
    """(file, line number, variable, value) for every locale set in a
    template, ignoring comments and the shell's own `export LANG` docs."""
    for path in _templates():
        for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue
            for variable, value in LOCALE_ASSIGNMENT.findall(line):
                yield path, number, variable, value


def test_no_template_forces_a_display_locale():
    """The rule.

    date-config forced de_DE.UTF-8 on both `date` and `cal`, and
    waybar-launcher forced it on the whole bar process - which every
    module script inherits, so it silently overrode the removal
    src/clocks.py had already made and documented.
    """
    forced = [
        f"{path.name}:{number} {variable}={value}"
        for path, number, variable, value in _assignments()
        if value.strip('"\'') not in PARSEABLE
    ]
    assert forced == [], (
        "a display locale is forced instead of inherited from the "
        "session:\n  " + "\n  ".join(forced))


def test_the_parseable_locale_is_still_used_somewhere():
    """The positive control.

    Without it the rule above passes on a tree that sets no locale
    anywhere - including one where somebody removed the `LANG=C` in front
    of nmcli, which is the one place a locale genuinely belongs.
    """
    parseable = [
        f"{path.name}:{number}"
        for path, number, _variable, value in _assignments()
        if value.strip('"\'') in PARSEABLE
    ]
    assert parseable, (
        "no template asks for the machine-readable locale any more - the "
        "commands whose output is parsed have lost their LANG=C")
