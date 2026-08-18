# SPDX-License-Identifier: GPL-3.0-or-later
"""The origin's own data, held as hashes instead of as text.

WHY THIS FILE EXISTS
--------------------
The guards that keep the previous employer's data out of this repository
used to carry that data in their own source, because a denylist has to
contain what it forbids in order to match it. Every one of them was also
scoped to `src/`, so nothing ever read `tests/` or `docs/` - which is
exactly why the names, the serial numbers and the internal addresses
survived there, in the files whose job was to remove them.

This module breaks that circle. It holds the forbidden strings as keyed
digests, never as text. The guards keep matching; a reader of the
published repository sees hexadecimal.

Three consequences fall out of that, and the third is the important one:

  * The guard works in every clone, for every contributor, with no local
    file to obtain and no step that can be skipped.
  * Nothing here is legible - not to a person, not to `grep`, not to a
    code-search engine or a scraper.
  * **The guard no longer matches its own source**, so it needs no
    self-exclusion. The previous attempt added one and justified it with
    "without this it could never go green"; that was not true - the scan
    was rooted at `src/` and never reached the file at all. Removing the
    plaintext removes the self-match at its root instead of papering over
    it, and there is no exclusion here to justify.

WHAT A READER OF THE PUBLISHED REPOSITORY CAN STILL LEARN, honestly
-------------------------------------------------------------------
  * How many strings are forbidden, and what they are ABOUT - the groups
    below are labelled, because a failure has to be actionable.
  * That the shortest one is `WINDOW` characters long and the longest at
    most `LONGEST`, since a substring search has to know its own bounds.
  * Nothing else by reading. A digest is not reversible.

But a hash of a SHORT string is not a secret from someone who already
suspects the answer: a four-letter word is half a million candidates, and
confirming a guess costs one hash. So the honest claim is narrow and it
is the one that matters here - the repository no longer PUBLISHES these
strings. Someone who already knows them can confirm they are listed.
Someone who does not cannot discover them. Nothing stronger is available
from a denylist that has to ship with the code it guards, and pretending
otherwise would be the same kind of false justification this file exists
to undo.

WHAT THIS DOES NOT DO AT ALL
----------------------------
It guards the working tree, and only the working tree. Every string it
forbids is still in this repository's HISTORY - in the commits that
introduced it and in the commits that took it out. `git log -p` finds all
of it in seconds. A clone published with its history is therefore
published with the origin's data, whatever these guards say about the tip.

No test can close that, and this one does not pretend to. Publishing this
repository open source needs one of three decisions: export without
history, rewrite the history, or accept it. Whoever publishes should make
that decision knowingly rather than discover it afterwards, which is the
only reason this paragraph is here.

The strings themselves are not lost: they are in the working notes of
whoever maintains this list, and `Denylist.from_plaintext()` below is the
one function needed to regenerate the tables. Adding an entry is:

    python -c 'import sys; sys.path.insert(0, "."); \
        from tests.origin_data import Denylist; \
        print(Denylist.from_plaintext(["..."]).as_source(prefix="_GROUP_"))'

Run it with the FULL group, never with one new entry appended to the
printed output - each table below is one set, not a log.

HOW THE MATCH WORKS
-------------------
The old rule was one case-insensitive alternation of seven literals,
searched as a substring, line by line. The replacement has to be at least
as strong as that, and it is:

  1. A line is normalised - lower-cased, every run of characters that is
     not an ASCII letter or digit collapsed to one separator. So does
     each forbidden entry. A two-part entry written with a hyphen, an
     underscore or a space therefore matches all three spellings, which
     the old regex would have missed.
  2. Collapsing rather than deleting is deliberate. Deleting separators
     joins neighbours that have nothing to do with each other - `max
     rows` would contain a four-letter entry that is genuinely not there
     - and a guard that cries wolf is one somebody weakens later.
  3. Matching is substring, not token: a template name with a forbidden
     host in the middle of it, and a machine name with a digit appended,
     both hit, exactly as they did before.

The docstring you are reading was itself rewritten twice, because the
first two drafts quoted the old pattern and its example matches - and
the guard went red over this file. That is the mechanism working: this
module is inside the scan, like every other file in the repository.

Two stages, because hashing every window of every length over two
megabytes takes seconds:

  * Stage one hashes ONE window per position, `WINDOW` characters wide,
    down to `BUCKET_BITS` bits. The bucket set is deliberately coarse:
    around half a percent of positions survive it, and each bucket has
    hundreds of preimages, so the set says nothing about what is in it.
  * Stage two runs only on those survivors and compares the full keyed
    digest at every length from `WINDOW` to `LONGEST`. Entry lengths are
    therefore not stored anywhere, so the table does not leak them.
"""
from __future__ import annotations

import hashlib
import re
import zlib
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent

# The separator every run of non-alphanumeric characters collapses to.
# A control character, so it cannot occur in the text being scanned and
# cannot be confused with content.
SEPARATOR = "\x00"

# The width of the stage-one window. Also the length of the shortest
# entry: a shorter entry could not be found by a search that starts by
# looking at four characters.
WINDOW = 4

# The longest entry stage two will look for. Raising it costs a little
# time and nothing else; an entry longer than this is silently never
# found, which is why `test_the_denylist_would_catch_a_new_one` measures
# a long entry rather than trusting this number.
LONGEST = 24

# Coarse on purpose - see the module docstring.
BUCKET_BITS = 12
BUCKET_MASK = (1 << BUCKET_BITS) - 1

# A fixed key, so the digests below cannot be looked up in a precomputed
# table of common words. It is not a secret and is not pretending to be
# one; it is in the repository, like the digests it protects.
KEY = b"zepos-origin-guard"

_RUN = re.compile(r"[0-9A-Za-z]+")


def normalise(text: str) -> str:
    """Lower-case, with every run of other characters collapsed to one
    separator, and a separator at each end.

    The outer separators matter: without them a rule anchored at the
    start of a line would behave differently from the same rule in the
    middle of one.
    """
    return SEPARATOR + SEPARATOR.join(
        match.group(0).lower() for match in _RUN.finditer(text)
    ) + SEPARATOR


def _digest(value: str) -> str:
    return hashlib.blake2b(
        value.encode("utf-8"), key=KEY, digest_size=16
    ).hexdigest()


def _bucket(value: str) -> int:
    return zlib.crc32(value.encode("utf-8")) & BUCKET_MASK


class Denylist:
    """A set of forbidden strings, held as digests.

    Built either from the tables at the bottom of this module or - in the
    meta-test that proves this machinery works - from invented plaintext
    that is not the origin's data. That second constructor is what lets
    the mechanism be tested without a single real string appearing in a
    test file, which is the whole point of the exercise.
    """

    def __init__(self, digests: frozenset[str], buckets: frozenset[int]):
        self.digests = digests
        self.buckets = buckets

    def __len__(self) -> int:
        return len(self.digests)

    @classmethod
    def from_plaintext(cls, entries) -> "Denylist":
        digests = set()
        buckets = set()
        for entry in entries:
            normalised = normalise(entry).strip(SEPARATOR)
            if len(normalised) < WINDOW:
                raise ValueError(
                    f"{entry!r} normalises to {len(normalised)} characters, "
                    f"below the stage-one window of {WINDOW} - it could "
                    "never be found")
            if len(normalised) > LONGEST:
                raise ValueError(
                    f"{entry!r} normalises to {len(normalised)} characters, "
                    f"above LONGEST ({LONGEST}) - it could never be found")
            digests.add(_digest(normalised))
            buckets.add(_bucket(normalised[:WINDOW]))
        return cls(frozenset(digests), frozenset(buckets))

    @classmethod
    def union(cls, parts) -> "Denylist":
        """One denylist out of several.

        The groups below exist so a failure can say WHAT KIND of thing
        was found - "a place name" sends somebody to a different line
        than "an internal host" does - and so a rule that is only about
        one kind (the two cities, in test_new_templates.py) can hold
        exactly that kind instead of the whole set.
        """
        parts = list(parts)
        return cls(frozenset().union(*(part.digests for part in parts)),
                   frozenset().union(*(part.buckets for part in parts)))

    def as_source(self, prefix: str = "") -> str:
        """The two tables, ready to paste into this file.

        The `prefix` is not decoration. Regenerating these tables means a
        script that rewrites part of this file, and a header string built
        here is a string that also OCCURS here - the first attempt at
        this rewrite matched the literal inside this very method instead
        of the table below it and truncated the module. A prefixed name
        cannot collide with an unprefixed occurrence.
        """
        head = f"{prefix}DIGESTS"
        lines = [head + " = frozenset({"]
        lines += [f'    "{value}",' for value in sorted(self.digests)]
        lines += ["})", "", f"{prefix}BUCKETS = frozenset({{"]
        lines += [f"    {value}," for value in sorted(self.buckets)]
        lines += ["})"]
        return "\n".join(lines)

    def hits(self, text: str) -> bool:
        """Whether one piece of text - a line, a value, a whole file -
        contains a forbidden string."""
        normalised = normalise(text)
        limit = len(normalised) - WINDOW
        for start in range(limit + 1):
            if _bucket(normalised[start:start + WINDOW]) not in self.buckets:
                continue
            for length in range(WINDOW, LONGEST + 1):
                candidate = normalised[start:start + length]
                if len(candidate) < length:
                    break
                if _digest(candidate) in self.digests:
                    return True
        return False

    def offending_lines(self, text: str) -> list[int]:
        """The line numbers - never the strings.

        A failure names a file and a line and stops there. Printing what
        matched would put the string into every CI log the moment the
        guard did its job, which is the same leak in a different place.
        """
        return [number
                for number, line in enumerate(text.splitlines(), start=1)
                if self.hits(line)]


# --------------------------------------------------------------------
# what gets scanned
# --------------------------------------------------------------------
#
# Everything that would be published. The old guards read `src/` only, on
# the argument that "only what ships can carry a name to a machine". That
# argument is true about machines and false about publication: the
# repository itself is what gets published, and `tests/` and `docs/` are
# in it.

SKIP_NAMES = frozenset({"__pycache__", ".git", ".venv", ".idea", ".vscode",
                        ".superpowers", ".pytest_cache", ".mypy_cache"})

# Build outputs, named by their position rather than by their basename: a
# directory called `out` somewhere else is not one of these.
SKIP_TREES = frozenset({"build/out", "iso/work", "iso/out", "po/build"})

SKIP_SUFFIXES = frozenset({".pyc", ".pyo", ".iso", ".zst", ".sig", ".gz",
                           ".png", ".jpg", ".jpeg", ".gif", ".ico", ".mo",
                           ".db", ".files"})

# Files that must be in the scan, checked rather than assumed. A selector
# that quietly drops a file reports the same "clean" as one that read it
# and found nothing - which is how three commands under `src/bin/` went
# unread for four tasks, and how `tests/` and `docs/` went unread for all
# of them.
MUST_BE_SCANNED = (
    "README.md",
    "src/generate_config.sh",
    "src/bin/zepos-doctor",
    "tests/conftest.py",
    "tests/origin_data.py",
    "tests/src/test_inventory.py",
    "docs/specs/2026-08-03-zepos-design.md",
    "docs/superpowers/plans/2026-08-04-zepos-basis-und-generisierung.md",
    "installer/core/model.py",
    "po/de.po",
)


def _is_skipped(path: Path) -> bool:
    relative = path.relative_to(REPOSITORY)
    if any(part in SKIP_NAMES for part in relative.parts):
        return True
    posix = relative.as_posix()
    return any(posix == tree or posix.startswith(tree + "/")
               for tree in SKIP_TREES)


def repository_files() -> list[Path]:
    """Every file in the repository a reader could open, sorted.

    Asserts it found a plausible number and that the files named above
    are among them: an empty or truncated list is the failure mode that
    made the old guards meaningless, first because `SRC` was a relative
    path that resolved to nothing, then because the suffix rule dropped
    the three files that end up furthest from here.
    """
    files = [path for path in sorted(REPOSITORY.rglob("*"))
             if not _is_skipped(path)
             and not path.is_symlink() and path.is_file()
             and path.suffix.lower() not in SKIP_SUFFIXES]

    assert len(files) > 100, (
        f"only {len(files)} files found under {REPOSITORY} - the scan is "
        "not reading the repository, so its result means nothing")
    found = {path.relative_to(REPOSITORY).as_posix() for path in files}
    missing = [name for name in MUST_BE_SCANNED if name not in found]
    assert missing == [], f"not read by the origin-data guard: {missing}"
    return files


def repository_directories() -> list[Path]:
    """Every directory, so that an EMPTY one is checked too.

    A file's full relative path is scanned, so a directory holding
    anything is already covered through its contents. An empty one is
    not - and while git cannot commit an empty directory, that is a fact
    about git rather than about this guard, and it was a mutation test
    planting `src/<hostname>-scripts/` that found the hole. Closing it
    costs one walk.
    """
    return [path for path in sorted(REPOSITORY.rglob("*"))
            if not _is_skipped(path) and not path.is_symlink()
            and path.is_dir()]


# --------------------------------------------------------------------
# the forbidden set
# --------------------------------------------------------------------
#
# 24 entries in six groups. The groups are named - a failure has to tell
# somebody what kind of thing they just committed - and the entries are
# not, because that is the leak this file exists to close.
#
# Entries that were CONSIDERED and left out, with the reason, so that the
# next person does not have to guess:
#
#   * The build tool's own three-letter name. Three characters is below
#     the stage-one window, and would be recovered from a digest in
#     milliseconds anyway. It stays a shape rule (`TOOLCHAIN_NAME` in
#     tests/src/test_inventory.py), which is what its word-boundary
#     semantics need in any case.
#   * The employer's six product codes. Two of them are ordinary English
#     words; forbidding those fires on half the tree. The naming SCHEME
#     is a shape rule instead, and it catches a seventh product nobody
#     has written yet.
#   * Display manufacturers and monitor model designations. Public
#     product names that say nothing about who the author is, and
#     already covered by a shape rule over what ships.
#   * The private address range the VPN templates assume. It is named in
#     an xfail reason in tests/src/test_vpn_config.py, and it is one of
#     the most-used private ranges there is - it identifies nobody.

_ORGANISATION_DIGESTS = frozenset({
    "052b1c2f9d2bd7072bb75cea01400537",
    "31262beead765a99a2a17ebe88aafc74",
    "3e30be251a6993c4debb3dca067cd2b8",
    "60577197769c81134f5b5b2bf252feb8",
    "86b2a27c232dc1ed006fa7f5916d48f0",
    "871c9d1c95b31ffc06f9dc273bbdbe65",
    "b2882ad0bf3bba3e68b28d94ff2d9163",
    "c9ff2d1d2d8fe518e08eaea9b6365fe4",
    "f35032704235780223a7ebcbe52257d2",
})

_ORGANISATION_BUCKETS = frozenset({
    303,
    544,
    1431,
    2234,
    2639,
    2708,
    2742,
    3060,
    3544,
})

_HARDWARE_DIGESTS = frozenset({
    "0561d6aeb9d2de304f3b20872577f942",
    "3032661bb9c320de137e4ccda1f7c58c",
    "4be359bc3eefeb33e14317eccfb0b7c8",
    "50774d793f23624d54578c08ea767c36",
    "bc6ddde4c89a9aa9adec47cc90a8d70a",
})

_HARDWARE_BUCKETS = frozenset({
    1967,
    3781,
    3833,
})

_DESKS_DIGESTS = frozenset({
    "aabab326f65971cfd81fc506654e48b5",
    "b1e94ede726bb2e242ed8eaa55f2f22e",
})

_DESKS_BUCKETS = frozenset({
    3931,
})

_PLACES_DIGESTS = frozenset({
    "4074652f31ecdfc17a00a48f6eab5c2f",
    "82f31fc1a999491b0212c08caf3f2f92",
})

_PLACES_BUCKETS = frozenset({
    1145,
    1423,
})

_PATHS_DIGESTS = frozenset({
    "a9efd89ac7153f7659a2549d92bf8686",
    "f37a2bbb2bc54ec87570173505ad6e4e",
})

_PATHS_BUCKETS = frozenset({
    2586,
    3280,
})

_TOOLCHAIN_DIGESTS = frozenset({
    "8c0624c9ba957b0c4c74e5c6cd0abd05",
    "8f301d6bdeb0489d1f6795a64070a139",
    "b52b6938264b006109c0ae4e8a8bff04",
    "c33265bbcaecbbde56db479ec90eba93",
})

_TOOLCHAIN_BUCKETS = frozenset({
    620,
    1132,
    3579,
    3722,
})


# One name per group. Nothing here has to be kept in step with the tables
# above by hand: ORIGIN is their union, and the meta-test in
# tests/src/test_inventory.py checks the total.
ORGANISATION = Denylist(_ORGANISATION_DIGESTS, _ORGANISATION_BUCKETS)
HARDWARE = Denylist(_HARDWARE_DIGESTS, _HARDWARE_BUCKETS)
DESKS = Denylist(_DESKS_DIGESTS, _DESKS_BUCKETS)
PLACES = Denylist(_PLACES_DIGESTS, _PLACES_BUCKETS)
PATHS = Denylist(_PATHS_DIGESTS, _PATHS_BUCKETS)
TOOLCHAIN = Denylist(_TOOLCHAIN_DIGESTS, _TOOLCHAIN_BUCKETS)

GROUPS = {
    "an organisation, a host or an internal address": ORGANISATION,
    "a hardware identity": HARDWARE,
    "a label naming one particular desk": DESKS,
    "a place name": PLACES,
    "a path that exists on one machine only": PATHS,
    "the previous employer's toolchain": TOOLCHAIN,
}

ORIGIN = Denylist.union(GROUPS.values())


def what_kind(text: str) -> str:
    """Which group matched, for a failure message - never the string.

    Enough to send somebody to the right line without putting the string
    back into a CI log.
    """
    return ", ".join(name for name, group in GROUPS.items()
                     if group.hits(text)) or "nothing"
