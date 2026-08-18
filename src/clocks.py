# SPDX-License-Identifier: GPL-3.0-or-later
"""Which extra clocks stand on the bar, and what they are called.

The origin had two templates of one line each, both placed on the bar
unconditionally:

    LANG=de_DE.UTF-8 TZ="Europe/Berlin"    date +"<flag> <clock> %H:%M"
    LANG=en_US.UTF-8 TZ="America/<city>"   date +"<flag> <clock> %H:%M"

- one person's two countries, on every user's bar, with a generator
route, a bar module, a colour and a stylesheet rule apiece. Somebody who
lives in one place wanted neither; somebody with colleagues in three
timezones could have none of them, because a third clock meant a fifth
file.

So the list is a setting, and this module is what turns it into the shell
the generated script declares. The same arrangement as src/audio.py: the
BLOCK is built here rather than filled in, so that "nothing configured"
comes out as a sentence saying so instead of as an empty array that reads
like an array of clocks.

WHAT IDENTIFIES A ZONE
    The IANA name and nothing else. The flag and the locale in those two
    lines were both derived from a COUNTRY, and from a timezone there is
    no reliable way back to one: Europe/Zurich covers three countries,
    Asia/Kolkata covers one that flies more than one flag in practice,
    and Etc/GMT-3 covers none. Any table mapping the one to the other
    would be a guess dressed as data, so there is none here.

    The label therefore defaults to the zone's own last component with
    underscores turned into spaces - "America/New_York" becomes "New
    York". That is the name restating itself, not a lookup, and it cannot
    be wrong about a country because it says nothing about one. A user
    who wants a flag or an abbreviation writes it down themselves:

        clocks.zones = [{"zone": "Asia/Tokyo", "label": "🇯🇵"}]

    which is then a fact about their settings rather than a claim this
    program made on their behalf.

WHAT IS REFUSED HERE AND WHAT IS REPORTED LATER
    Two different failures, and only one of them belongs at generation
    time.

      * A string that could not be a timezone name AT ALL - a path, a
        number, an object with no zone in it - is refused here, before it
        is built into a script. The generated script looks a zone up in
        the timezone database by path, so a name that can leave that
        directory is a name that must never reach it.
      * A well-formed name that this machine's database does not happen
        to know is a typo, and it is reported by the script, at the
        moment it runs, where the database is. Refusing it here would
        mean a tzdata release retiring a zone breaks the WHOLE
        configuration run - every template, not only this one - on a
        machine whose bar worked yesterday.

WHY NO LOCALE
    `LANG=de_DE.UTF-8` in front of `date` does nothing whatever for
    %H:%M, and where that locale is not generated on the machine it does
    nothing for any format: date(1) falls back to C silently and exits 0.
    Measured, with LC_ALL naming a locale that does not exist - English
    weekday names, status 0, empty stderr. A forced locale can therefore
    only do one of two things, nothing or something other than it
    promises, and neither is worth a setting. What the user actually
    wants a say in is the FORMAT, which is `clocks.format`; the locale is
    the session's, which they chose and which exists on their machine.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Loaded both ways, exactly as settings.py's own header describes: as
# `src.clocks` from the test suite, where src is a package, and as
# `clocks` from /usr/share/zepos, where every module sits flat beside
# every other and there is no package at all.
try:
    from .settings import JSON_TYPES, UnusableSettings
except ImportError:
    from settings import JSON_TYPES, UnusableSettings

SECTION = "clocks"

# Hours and minutes, and nothing that depends on a locale being present.
DEFAULT_FORMAT = "%H:%M"

# An IANA zone name: components of letters, digits, "_", "+" and "-",
# separated by single slashes, with no component empty.
#
# This is a SHAPE rule, not a list of zones - see the header. It exists
# because the generated script resolves a zone against the timezone
# database by path, so the three things it must not admit are a leading
# slash, an empty component and a ".." - all three of which leave the
# database directory, and one of which ("/etc/localtime") reads as a
# perfectly ordinary configuration mistake rather than as an attack.
# "+" and "-" are in the set because Etc/GMT+5 is a real zone.
ZONE_NAME = re.compile(r"[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)*\Z")


@dataclass(frozen=True)
class Clock:
    """One extra clock: the zone that identifies it, and what it is called."""

    zone: str
    label: str


def _json_type(value: Any) -> str:
    """What the user wrote, in the vocabulary they wrote it in.

    settings.py's table, for settings.py's reason: "a str" and "a
    NoneType" name nothing that appears in a JSON file, and the person
    reading this message is looking at their settings file rather than at
    a traceback. The fallback is the Python name, because a type that is
    not in the table came from somewhere other than json.loads and has no
    JSON name to give.
    """
    return JSON_TYPES.get(type(value), type(value).__name__)


def _quote(value: str) -> str:
    """One shell literal, always quoted.

    shlex.quote() leaves a "safe" string bare, and "%H:%M" is safe by its
    rules - so the generated line would read `FORMAT=%H:%M` beside
    `ZONES=('Asia/Tokyo')`, two spellings of the same thing in one file
    somebody is expected to read. Always quoting costs two characters and
    makes the block uniform.

    The label comes out of a file a user edits by hand, so the apostrophe
    is the case that matters: end the string, escape one quote, start a
    new string.
    """
    return "'" + value.replace("'", "'\\''") + "'"


def settings_section(document: dict[str, Any]) -> dict[str, Any]:
    """The clocks section of a settings document, or an empty one.

    A missing section is the shipping state and answers with {}. A
    section of the wrong TYPE is refused: `"clocks": "Asia/Tokyo"` is a
    plausible hand-edit, and every reader below would otherwise call
    .get() on a string and fail with an AttributeError that names a line
    of this file rather than a line of the user's.
    """
    section = document.get(SECTION)
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise UnusableSettings(
            f"{SECTION} is a JSON {_json_type(section)} ({section!r}) where a "
            f"section holding \"zones\" and \"format\" belongs, e.g. "
            f"{{\"zones\": [\"Europe/Lisbon\"]}}."
        )
    return section


def _zone_name(value: Any, position: int) -> str:
    """One entry's zone name, checked for shape.

    `position` is the index in the list, because "one of your zones is
    wrong" is not something a user can act on when there are four.
    """
    if not isinstance(value, str):
        raise UnusableSettings(
            f"{SECTION}.zones[{position}] is a JSON {_json_type(value)} "
            f"({value!r}) where a timezone name belongs, e.g. "
            f"\"Europe/Lisbon\"."
        )
    name = value.strip()
    if not ZONE_NAME.match(name):
        raise UnusableSettings(
            f"{SECTION}.zones[{position}] is {value!r}, which is not the "
            f"shape of an IANA timezone name. Those are letters, digits, "
            f"\"_\", \"+\" and \"-\" in components separated by single "
            f"slashes - \"Europe/Lisbon\", \"America/New_York\", "
            f"\"Etc/GMT+5\". `timedatectl list-timezones` prints the ones "
            f"this machine knows."
        )
    return name


def derived_label(zone: str) -> str:
    """What a zone is called when the user has not said.

    The last component of the name, with underscores as spaces. Not a
    lookup and not a translation: it is the identifier saying its own
    name, which is the only label available that cannot be wrong about a
    country - see the header.
    """
    return zone.rsplit("/", 1)[-1].replace("_", " ")


def zones(section: dict[str, Any]) -> list[Clock]:
    """The configured clocks, in the order they were written.

    Order is kept rather than sorted - by name or by offset - because the
    bar reads left to right and the arrangement is the user's.

    Blank entries are dropped. A half-finished edit is the normal way one
    arrives here (the same reason the VPN lists drop them), and an empty
    string is not merely useless: TZ="" is UTC, so a blank entry that
    survived would put a nameless UTC clock on the bar.
    """
    raw = section.get("zones")
    if raw is None:
        return []
    # A str satisfies every iterable signature a list does, so
    # "zones": "Asia/Tokyo" would be walked CHARACTER BY CHARACTER: ten
    # clocks named A, s, i, a, "/", T, o, k, y, o. Refused by name, with
    # the value to correct, exactly as vpn.nonblank_entries does it.
    if isinstance(raw, (str, bytes)):
        raise UnusableSettings(
            f"{SECTION}.zones is the single string {raw!r} where a list of "
            f"timezone names belongs. One zone is a list of one: [{raw!r}]."
        )
    if not isinstance(raw, (list, tuple)):
        raise UnusableSettings(
            f"{SECTION}.zones is a JSON {_json_type(raw)} ({raw!r}) where a "
            f"list of timezone names belongs."
        )

    found = []
    for position, entry in enumerate(raw):
        if isinstance(entry, dict):
            if "zone" not in entry:
                raise UnusableSettings(
                    f"{SECTION}.zones[{position}] is {entry!r}, which names "
                    f"no zone. A label alone identifies no time: write "
                    f"{{\"zone\": \"Europe/Lisbon\", \"label\": \"...\"}}."
                )
            name = _zone_name(entry["zone"], position)
            label = entry.get("label")
            # A label that is present and blank is not a choice, it is an
            # empty text box. Falling back to the derived name leaves a
            # clock somebody can tell apart from its neighbour.
            label = str(label).strip() if label is not None else ""
        else:
            if isinstance(entry, str) and not entry.strip():
                continue
            name = _zone_name(entry, position)
            label = ""

        found.append(Clock(zone=name, label=label or derived_label(name)))
    return found


def time_format(section: dict[str, Any]) -> str:
    """The strftime format every clock is rendered with.

    One format for all of them, not one per zone: the point of a row of
    clocks is comparing them, and two of them in different formats is a
    row that has to be read twice.
    """
    value = section.get("format")
    if value is None:
        return DEFAULT_FORMAT
    if not isinstance(value, str):
        raise UnusableSettings(
            f"{SECTION}.format is a JSON {_json_type(value)} ({value!r}) where "
            f"a date(1) format string belongs, e.g. \"{DEFAULT_FORMAT}\"."
        )
    return value.strip() or DEFAULT_FORMAT


def format_literal(section: dict[str, Any]) -> str:
    """The format as one shell literal, ready to be assigned."""
    return _quote(time_format(section))


NOTHING_CONFIGURED = (
    "# Keine Zusatzuhr eingestellt - der Auslieferungszustand.\n"
    "#\n"
    "# `clocks.zones` in den Nutzereinstellungen ist die Liste der\n"
    "# Zeitzonen, die neben der Ortszeit stehen sollen; ohne Eintrag gibt\n"
    "# dieses Modul nichts aus und Waybar blendet es aus.\n"
    "#\n"
    "#   zepos-settings set clocks.zones '[\"Europe/Lisbon\"]'\n"
    "ZONES=()\n"
    "LABELS=()"
)


def zones_block(section: dict[str, Any]) -> str:
    """The two shell arrays the generated script reads, or a comment.

    Two parallel arrays rather than one array of "zone=label" pairs: a
    label may contain anything a user types, separators included, and a
    script that split them apart again would be one delimiter away from
    rendering half a label as a timezone.

    The empty case must not be a bare `ZONES=()`. An empty array is valid
    shell, does nothing, and reads to anyone opening the file as if the
    feature were broken rather than switched off - the same argument
    audio.node_rules_block() makes about an empty rule list.
    """
    clocks = zones(section)
    if not clocks:
        return NOTHING_CONFIGURED

    names = " ".join(_quote(clock.zone) for clock in clocks)
    labels = " ".join(_quote(clock.label) for clock in clocks)
    return f"ZONES=({names})\nLABELS=({labels})"
