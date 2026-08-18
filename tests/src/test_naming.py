# SPDX-License-Identifier: GPL-3.0-or-later
"""No reference to the origin project may survive.

A leftover word is embarrassing; a leftover path is a bug. It names a
directory that exists only on the machine this project was split from, so
the failure appears after installation, on someone else's system, at the
moment the generator tries to read or write there.
"""
import re
from pathlib import Path

# Anchored on this file rather than on the working directory: pytest can
# be started from anywhere, and a relative Path("src") would then measure
# a directory that has nothing to do with this checkout - or, worse, one
# that happens to exist and quietly reports success.
SRC = Path(__file__).resolve().parents[2] / "src"

SUFFIXES = {".py", ".sh", ".template", ".conf", ".json", ".md", ".service"}

# The stem, not the whole word, and with any separator between the two
# halves. Four spellings of one name have to be caught by one pattern:
#
#   iconmanager             the origin's path, ~/.config/iconmanager
#   iconman                 its own abbreviation for helper scripts
#                           (iconman-terminals, ICONMAN_ROOT), which a
#                           pattern anchored on the long form misses
#   Icon Manager            the prose form, in headers and messages
#   icon_manager            a module name - and this is the one the
#                           previous pattern let through
#
# That last omission was not theoretical. `iconman|Icon\s+Manager`
# matches neither "icon_manager" (no such substring; \s+ does not match
# an underscore) nor "Icon-Manager", so src/icon_manager.py sat in the
# tree, was read by the scan below, and the guard reported clean for as
# long as it existed. Matching the stem plus an optional separator run
# covers every spelling a file name, an identifier or a sentence can
# produce, and costs nothing: no word in this tree begins "icon" and
# continues "man".
FORBIDDEN = re.compile(r"icon[\s_-]*man", re.IGNORECASE)

# Every spelling a shell or a JavaScript template literal can produce for
# the user directory. The brace form is the one the AGS widgets use, and
# a pattern that only knows "$HOME/" walks straight past it.
HARDCODED_USER_PATH = re.compile(r"(\$\{?HOME\}?|~)/\.config/zepos")

# Files that are allowed to name the two roots because defining them is
# their job.
ROOT_DEFINITION_FILES = {"paths.py", "test_naming.py"}

ROOTS = ("ZEPOS_SYSTEM_ROOT", "ZEPOS_USER_ROOT")


def _has_shebang(path: Path) -> bool:
    """Whether a file without a suffix is a script.

    The three commands in src/bin carry no extension - nobody types
    "zepos-doctor.py" - so selecting on suffix alone walked past exactly
    the files that get installed into /usr/bin and travel furthest from
    this repository.
    """
    try:
        with path.open("rb") as handle:
            return handle.read(2) == b"#!"
    except OSError:
        return False


def _sources():
    for path in sorted(SRC.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix in SUFFIXES or (not path.suffix and _has_shebang(path)):
            yield path


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def test_the_installed_commands_are_actually_scanned():
    """The guards' own blind spot, held open.

    Every content test in this file and in test_inventory.py selects
    files by suffix. src/bin/zepos-generate, -settings and -doctor have
    none, so all three were invisible to all of them - and they are the
    files that get installed into /usr/bin and travel furthest from this
    repository. A guard that silently skips a file reports the same
    "clean" as one that read it.

    Asserting the scan reaches them, rather than trusting the selector:
    a helper that returns nothing looks exactly like a tree with nothing
    wrong in it.
    """
    scanned = {path.relative_to(SRC).as_posix() for path in _sources()}
    for name in ("bin/zepos-generate", "bin/zepos-settings", "bin/zepos-doctor"):
        assert name in scanned, f"{name} is not read by any content guard"


def test_the_patterns_would_catch_what_they_were_written_for():
    """Every guard in this file, measured against lines it must catch and
    lines it must leave alone.

    tests/src/test_inventory.py carries three of these and
    tests/origin_data.py a fourth, for a reason this file had no answer
    to: a rule that matches nothing reports exactly the same "clean" as a
    tree with nothing wrong in it. FORBIDDEN and HARDCODED_USER_PATH
    could each be replaced by a regex that can never match - `(?!)` -
    and all four scans below them stayed green.

    The "must leave alone" half is the one that stops this being made to
    pass by widening the patterns until they match everything, which is
    the other way a guard dies.
    """
    # One line per spelling the comment above FORBIDDEN claims to cover,
    # so dropping any alternative from that list fails here rather than
    # in six months on somebody else's machine. The underscore and hyphen
    # forms are the ones the previous pattern missed: src/icon_manager.py
    # survived every run of the scan below.
    for line in ("ICONMAN_ROOT=/home/x/.config/iconmanager",
                 "# Generated by Icon Manager",
                 "# the icon manager writes this file",
                 "source ~/.config/iconman/helpers/x.sh",
                 "iconman-terminals-config.template",
                 "PYTHON_CMD=(python3 \"$ROOT/icon_manager.py\")",
                 "from icon_manager import ConfigProcessor",
                 "# das Icon-Manager-Projekt"):
        assert FORBIDDEN.search(line), f"the origin guard would miss: {line}"

    # The separator run is optional, which is what makes the pattern a
    # stem rather than three literals - and optional is also how a
    # pattern starts matching things it should not. These are the near
    # misses: "icon" followed by a word that merely starts with "ma", and
    # "manager" with no "icon" in front of it.
    for line in ("ZEPOS_SYSTEM_ROOT=/usr/share/zepos",
                 "manager = IconTable()",
                 "# the icons are managed from one place",
                 "ICON_MAP = {}",
                 "icon_mapping = load()",
                 "# the icon marks a disconnected tunnel"):
        assert not FORBIDDEN.search(line), f"the origin guard cries wolf over: {line}"

    # Every spelling a shell or a JS template literal produces. The brace
    # form is what the AGS widgets use and what a "$HOME/"-only pattern
    # walked straight past.
    for line in ('CONF="$HOME/.config/zepos/user-settings.json"',
                 'CONF="${HOME}/.config/zepos"',
                 "cp x ~/.config/zepos/templates/"):
        assert HARDCODED_USER_PATH.search(line), (
            f"the hardcoded-path guard would miss: {line}")

    for line in ('CONF="$ZEPOS_USER_ROOT/user-settings.json"',
                 'CONF="${XDG_CONFIG_HOME:-$HOME/.config}/zepos"',
                 "# zepos keeps its settings under the user root"):
        assert not HARDCODED_USER_PATH.search(line), (
            f"the hardcoded-path guard cries wolf over: {line}")


def test_the_root_definition_rule_would_catch_a_script_that_defines_neither():
    """test_every_script_that_uses_a_root_also_defines_it, exercised.

    Its regex is four alternatives long and assembled with an f-string,
    which is exactly the shape that quietly stops matching. A file using
    a root without defining it is the failure it exists for, and the
    three legitimate ways to define one are what it must not report.
    """
    def defines(text: str, root: str = "ZEPOS_USER_ROOT") -> bool:
        return bool(re.search(
            rf"(?:{root}\s*=|{root}:-|[\"']{root}[\"']|\{{\{{{root}\}}\}})", text))

    assert not defines('exec "$ZEPOS_USER_ROOT/helpers/watchdog.sh"'), (
        "a script that only USES the root is treated as defining it")

    for definition in ('ZEPOS_USER_ROOT="$HOME/.config/zepos"',
                       'ROOT="${ZEPOS_USER_ROOT:-$HOME/.config/zepos}"',
                       'root = os.environ["ZEPOS_USER_ROOT"]',
                       'ROOT="{{ZEPOS_USER_ROOT}}"'):
        assert defines(definition), f"a legitimate definition is refused: {definition}"


def test_no_file_mentions_the_origin_project():
    offenders = []
    for path in _sources():
        for number, line in enumerate(_text(path).splitlines(), start=1):
            if FORBIDDEN.search(line):
                offenders.append(f"{path.relative_to(SRC)}:{number}")
    assert offenders == [], (
        f"{len(offenders)} origin references left: " + ", ".join(offenders[:10])
    )


def test_no_file_name_carries_the_origin_project():
    """The content scan cannot see this one.

    A template called iconman-terminals-config keeps the origin's name in
    the generator's command line and in the file the user ends up running,
    where a search through file contents never looks.
    """
    offenders = [
        str(path.relative_to(SRC))
        for path in sorted(SRC.rglob("*"))
        if FORBIDDEN.search(path.name)
    ]
    assert offenders == [], "origin names in paths: " + ", ".join(offenders)


def test_no_hardcoded_user_config_path():
    """Templates used to write $HOME/.config/iconmanager directly.

    Every such place must now go through the roots, or a packaged install
    writes into whatever the developer's home happened to be called and
    ignores XDG_CONFIG_HOME entirely.
    """
    offenders = []
    for path in _sources():
        if path.name in ROOT_DEFINITION_FILES:
            continue
        for number, line in enumerate(_text(path).splitlines(), start=1):
            if HARDCODED_USER_PATH.search(line):
                offenders.append(f"{path.relative_to(SRC)}:{number}")
    assert offenders == [], (
        "hardcoded user paths outside paths.py: " + ", ".join(offenders[:10])
    )


def test_generator_reads_from_the_system_root():
    text = _text(SRC / "generate_config.sh")
    assert "ZEPOS_SYSTEM_ROOT" in text, (
        "the generator must honour the overridable system root, or tests "
        "cannot run without touching /usr/share"
    )
    assert "ZEPOS_USER_ROOT" in text, (
        "the generator must honour the user root, or a user override of a "
        "template is never found"
    )


def test_every_script_that_uses_a_root_also_defines_it():
    """An unset $ZEPOS_USER_ROOT expands to nothing.

    "$ZEPOS_USER_ROOT/helpers/network-watchdog.sh" then becomes
    "/helpers/network-watchdog.sh" - a path at the filesystem root, with
    no error at expansion time and no hint in the message that follows.
    The generated scripts run standalone and cannot import paths.py, so
    each one that reads a root has to say where it comes from: either a
    run-time default, or the {{...}} placeholder the generator resolves
    while writing the file.
    """
    offenders = []
    for path in _sources():
        if path.name in ROOT_DEFINITION_FILES:
            continue
        text = _text(path)
        for root in ROOTS:
            if root not in text:
                continue
            defines = re.search(
                rf"(?:{root}\s*=|{root}:-|[\"']{root}[\"']|\{{\{{{root}\}}\}})", text
            )
            if not defines:
                offenders.append(f"{path.relative_to(SRC)}: uses {root} undefined")
    assert offenders == [], "; ".join(offenders)


def test_no_generated_artifact_is_checked_in_beside_its_template():
    """src/helpers/ used to hold the generator's own output.

    While the generator wrote there, regenerating refreshed those files.
    It now writes to the user root instead, so nothing refreshes them and
    they drift: one carried a rendered "?" where its template has
    {{ICON_REPAIR}}, from an icon database two revisions old.

    Worse than drift, a checked-in copy of a generated file obliges the
    next contributor to hand-edit generated output, which every header in
    this tree forbids in its first line.
    """
    templates = SRC / "templates"
    offenders = []
    for path in sorted((SRC / "helpers").rglob("*")):
        if not path.is_file() or path.suffix == ".pyc":
            continue
        for candidate in (f"{path.stem}-config.template", f"{path.stem}.template"):
            if (templates / candidate).is_file():
                offenders.append(f"{path.relative_to(SRC)} is generated from {candidate}")
    assert offenders == [], (
        "checked-in generated files: " + "; ".join(offenders)
    )


def test_no_artifact_defaults_the_system_root_to_a_guess():
    """A generated artifact cannot find the package it came from.

    Defaulting to the literal /usr/share/zepos is a guess that is wrong
    for every install that is not a finished package - and there is no
    PKGBUILD in this tree yet, so today it is wrong for all of them. The
    generator knows the answer and substitutes it, so an artifact that
    still carries the guess never got that substitution.
    """
    offenders = []
    for path in sorted((SRC / "templates").glob("*.template")):
        for number, line in enumerate(_text(path).splitlines(), start=1):
            if "/usr/share/zepos" in line:
                offenders.append(f"{path.relative_to(SRC)}:{number}")
    assert offenders == [], (
        "artifacts guessing the package location: " + ", ".join(offenders)
    )
