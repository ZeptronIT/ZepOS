# SPDX-License-Identifier: GPL-3.0-or-later
"""The extra clocks, taken off the two countries that were baked in.

WHAT WAS THERE
    Two templates of one line each, both placed on the bar
    unconditionally. Each had a timezone, a flag emoji and a locale
    written into it - two countries several timezones apart, whichever
    two whoever wrote the templates happened to need - so every user of
    this distribution carried two clocks for two countries they may
    never have been to, and a user with colleagues in three timezones
    could have none of them. There was a generator route, a bar module,
    a colour and a stylesheet rule per clock, which is what makes "just
    add a third" a five-file change.

    Which two they were is deliberately not written here (17.08.2026).
    Two named countries beside the word "author" are a person's address
    in two guesses, and nothing in the argument above needs the names:
    what carries it is the DISTANCE between the zones and the fact that
    the choice was somebody's own.

WHAT REPLACED IT
    One module, one script, any number of zones, and NOTHING at all when
    none are configured - the shape the weather module already has and
    for the same reason: a feature nobody asked for must not arrive
    switched on.

    The zone list is the setting. `clocks.zones` holds IANA names, and an
    IANA name is the ONLY thing that identifies a zone. The flag and the
    locale were derived from a COUNTRY, and there is no reliable mapping
    from a timezone to a country - Europe/Zurich covers three, Etc/GMT-3
    covers none - so this project derives none. The label defaults to the
    zone's own last component with underscores turned into spaces, which
    is the name restating itself rather than a lookup, and a user who
    wants a flag writes the flag.

WHY THESE TESTS RUN THE ARTIFACT
    Every defect this replaces reads perfectly sensibly in the template.
    `TZ="Europe/Berlin"` is not wrong; it is wrong for everybody else.
    And the two failures that matter most here are invisible to any
    assertion about the text:

      * `date` accepts a timezone that does not exist, exits 0 and prints
        UTC. Measured: `TZ=Not/AZone date +"%H:%M %Z"` prints the UTC
        time with "Not" as the zone abbreviation and returns 0. A clock
        that silently shows the wrong hour is worse than no clock,
        because it is believed.
      * `LANG=de_DE.UTF-8` in front of `date` does nothing for %H:%M, and
        where the locale is not generated on the machine it does nothing
        at all: `date` falls back to C without a word and returns 0.
        Measured with LC_ALL set to a locale that does not exist -
        English weekday names, exit status 0, empty stderr.

    So the template is generated from a real settings document and the
    result is executed.

SAFETY
    The same harness as tests/src/test_network_watchdog.py and
    tests/src/test_new_templates.py: every child starts through `env -i`
    with the stub directory as the WHOLE of PATH, asserted before each
    run, so a command nothing stubbed fails with "command not found"
    instead of reaching the real one. `date` is a bash stub built on the
    shell's own `printf %()T`, which reads TZ from the environment the
    same way `date` does - so the times below are genuinely converted and
    at the same time fixed, because the stub formats ONE constant instant
    instead of "now". Nothing here spawns a real binary except bash
    itself and jq, which reads stdin and writes stdout.
"""
import datetime
import importlib.util
import itertools
import json
import os
import shutil
import subprocess
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import pytest

# The shared backstop, from tests/conftest.py: a command the stub
# directory does not provide has to be a failure, not an empty string.
import conftest

from src.clocks import (DEFAULT_FORMAT, UnusableSettings, format_literal,
                        settings_section, time_format, zones, zones_block)

SRC = Path(__file__).resolve().parents[2] / "src"
TEMPLATES = SRC / "templates"

BASH = "/bin/bash"
ENV = "/usr/bin/env"

TEMPLATE = "bar-clocks-config"

# 2026-01-01 00:00:00 UTC. One constant instant, so the expected times
# below are arithmetic rather than a race with the clock on the wall.
FIXED_EPOCH = 1767225600

# Zones chosen for three properties: none of them is a place this project
# was ever pointed at, all three are in every tzdata release, and their
# offsets differ from each other and from UTC, so a script that ignored
# TZ entirely would fail rather than coincide.
TOKYO = "Asia/Tokyo"
NEW_YORK = "America/New_York"
AUCKLAND = "Pacific/Auckland"

# Shape-valid and in no timezone database, on purpose: it is the typo
# case, and it is unmistakably not a leftover of somebody's home town.
NOWHERE = "Mars/Olympus_Mons"

# Where glibc looks for a zone when TZDIR is unset. Read, never written.
ZONEINFO = Path("/usr/share/zoneinfo")


def expected(zone: str, fmt: str = DEFAULT_FORMAT) -> str:
    """What the fixed instant is called in that zone."""
    moment = datetime.datetime.fromtimestamp(FIXED_EPOCH, ZoneInfo(zone))
    return moment.strftime(fmt)


# ====================================================================
# 1. the settings become a block of shell - src/clocks.py
# ====================================================================

def test_no_zone_configured_produces_no_zone_and_says_so():
    """The shipping state, and it has to be legible in the file.

    Not an empty array on its own: somebody opening clocks.sh to find out
    why the bar shows no second clock must find the answer there, with
    the name of the setting that switches it on.
    """
    block = zones_block({})

    assert "ZONES=()" in block
    assert "clocks.zones" in block, (
        "the file has to name the setting that turns this on")


def test_one_zone_becomes_one_entry_labelled_after_itself():
    block = zones_block({"zones": [TOKYO]})

    assert f"ZONES=('{TOKYO}')" in block
    assert "LABELS=('Tokyo')" in block


def test_an_underscore_in_a_zone_becomes_a_space_in_its_label():
    """America/New_York is "New York", not "New_York".

    The derivation is the zone name restating itself - the only honest
    label available without a country table.
    """
    assert zones(settings_section({"clocks": {"zones": [NEW_YORK]}}))[0].label \
        == "New York"


def test_three_zones_keep_the_order_they_were_written_in():
    """The bar reads left to right and so does the list.

    Sorting them - by name or by offset - would move a user's own
    arrangement around behind their back.
    """
    entries = zones({"zones": [AUCKLAND, TOKYO, NEW_YORK]})

    assert [entry.zone for entry in entries] == [AUCKLAND, TOKYO, NEW_YORK]


def test_a_label_the_user_wrote_wins_over_the_derived_one():
    """The flag, without a flag table.

    The origin's 🇩🇪 was correct for its author and for nobody else,
    because it came from a country this program cannot derive. It can be
    written down, though, and then it is a fact about the user's own
    settings instead of a guess about their timezone.
    """
    entries = zones({"zones": [{"zone": TOKYO, "label": "🇯🇵 Büro"}]})

    assert entries[0].label == "🇯🇵 Büro"
    assert entries[0].zone == TOKYO


def test_a_blank_entry_is_dropped_rather_than_rendered():
    """A half-finished edit is the normal way one arrives here.

    An empty string is not a timezone, and TZ="" is UTC - so keeping it
    would put a nameless UTC clock on the bar.
    """
    entries = zones({"zones": ["", TOKYO, "   "]})

    assert [entry.zone for entry in entries] == [TOKYO]


def test_a_single_string_where_a_list_belongs_is_refused_by_name():
    """The likeliest hand-edit of this file, and it must not be iterated.

    A str satisfies every iterable signature a list does, so
    "zones": "Asia/Tokyo" would otherwise become ten clocks named A, s,
    i, a, /, T, o, k, y, o - each of them a zone that does not exist.
    The same refusal the VPN lists make, with the same reasoning.
    """
    with pytest.raises(UnusableSettings) as excinfo:
        zones({"zones": TOKYO})

    assert "clocks.zones" in str(excinfo.value)
    assert TOKYO in str(excinfo.value), (
        "the message has to carry the value the user has to correct")


@pytest.mark.parametrize("entry", [5, True, None, ["Asia", "Tokyo"]])
def test_an_entry_that_is_neither_a_name_nor_an_object_is_refused(entry):
    with pytest.raises(UnusableSettings) as excinfo:
        zones({"zones": [entry]})

    assert "clocks.zones" in str(excinfo.value)


def test_an_object_without_a_zone_is_refused():
    """A label alone names no time.

    Silently dropping it would leave the user staring at a settings file
    that clearly contains their clock and a bar that does not.
    """
    with pytest.raises(UnusableSettings) as excinfo:
        zones({"zones": [{"label": "Büro"}]})

    assert "zone" in str(excinfo.value)


@pytest.mark.parametrize("bad", [
    # Path traversal. The generated script checks the zone against the
    # timezone database by PATH, so a name that leaves the directory
    # would find a file that is not a zone at all.
    "../../etc/passwd",
    "Europe/../../etc/passwd",
    # An absolute path, and the ":" form glibc also accepts: both reach
    # outside the database by design.
    "/etc/localtime",
    ":Europe/Lisbon",
    # A trailing separator and an empty component.
    "Asia/",
    "Asia//Tokyo",
    # Whitespace inside a name, which no IANA zone has.
    "Asia/To kyo",
])
def test_a_name_that_is_not_a_timezone_name_is_refused(bad):
    """Shape, not existence.

    A zone that is merely UNKNOWN to this machine's database is a typo
    and is reported at runtime, where the database is. A string that
    could not be a zone name at all is refused here, before it is built
    into a script.
    """
    with pytest.raises(UnusableSettings) as excinfo:
        zones({"zones": [bad]})

    assert "clocks.zones" in str(excinfo.value)


def test_a_zone_that_no_database_knows_is_accepted_here():
    """The other half of the rule above, and it has to stay true.

    Refusing unknown names at generation time would mean a tzdata update
    that retires a zone breaks the whole configuration run - every
    template, not just this one - on a machine whose bar was working
    yesterday.
    """
    assert zones({"zones": [NOWHERE]})[0].zone == NOWHERE


def test_the_format_defaults_to_hours_and_minutes():
    assert time_format({}) == DEFAULT_FORMAT
    assert format_literal({}) == f"'{DEFAULT_FORMAT}'"


def test_the_format_is_a_setting_and_not_a_locale():
    """What the origin controlled with LANG belongs here instead.

    LANG=de_DE.UTF-8 in front of `date` changes nothing about %H:%M, and
    where that locale is not generated it changes nothing about anything
    - `date` falls back to C silently and exits 0. A format string says
    what is wanted; a locale name says where to look it up and then does
    not say whether it was found.
    """
    assert time_format({"format": "%H:%M:%S"}) == "%H:%M:%S"


def test_a_blank_format_falls_back_rather_than_printing_nothing():
    assert time_format({"format": "   "}) == DEFAULT_FORMAT


def test_a_format_that_is_not_a_string_is_refused_by_name():
    with pytest.raises(UnusableSettings) as excinfo:
        time_format({"format": 24})

    assert "clocks.format" in str(excinfo.value)


@pytest.mark.allow_subprocess
def test_a_quote_in_a_label_cannot_break_out_of_the_block():
    """The block is shell source, and the label comes from a file a user
    edits by hand. Quoted here rather than hoped about: an apostrophe in
    a label would otherwise end the string and leave the rest of the
    line to be parsed as commands.

    `bash -n` parses without executing, so nothing in the block runs even
    if the quoting were broken - which is the case this exists for.
    """
    block = zones_block({"zones": [{"zone": TOKYO, "label": "Bob's Büro"}]})

    parsed = subprocess.run(
        [BASH, "-n", "-c", block], capture_output=True, text=True, timeout=30)
    assert parsed.returncode == 0, parsed.stderr


def test_the_settings_section_is_read_from_the_document_it_lives_in():
    assert settings_section({"clocks": {"zones": [TOKYO]}}) == {"zones": [TOKYO]}
    assert settings_section({}) == {}


def test_a_clocks_section_of_the_wrong_shape_is_refused():
    """`"clocks": "Asia/Tokyo"` is a plausible hand-edit and a dict is
    what every reader below assumes."""
    with pytest.raises(UnusableSettings) as excinfo:
        settings_section({"clocks": TOKYO})

    assert "clocks" in str(excinfo.value)


# ====================================================================
# 2. generating the artifact from a settings document
# ====================================================================

def _no_compositor(*args, **kwargs):
    """A subprocess.run that answers "hyprctl said nothing useful".

    style_definition asks the compositor for the attached screens while
    it builds its variables. Patched explicitly rather than left to the
    isolation guard, exactly as tests/src/test_hardware.py does it: the
    guard's refusal is a RuntimeError, which monitors.detect() also
    raises and attached_screens() catches, so a test that depended on
    which one fired would change meaning when conftest does.
    """
    return subprocess.CompletedProcess(args[0] if args else [], 1,
                                       stdout="", stderr="not running")


@pytest.fixture
def build(tmp_path, monkeypatch):
    """Generate the clocks template against a settings document.

    A FRESH style_definition per call: it reads the settings once, at
    import, and caches them, so a shared module would carry the first
    test's zones into the second.
    """
    monkeypatch.syspath_prepend(str(SRC))
    counter = itertools.count()

    def _build(clocks: dict | None = None) -> Path:
        root = tmp_path / f"settings-{next(counter)}"
        root.mkdir(parents=True, exist_ok=True)
        document: dict = {"schema_version": 1}
        if clocks is not None:
            document["clocks"] = clocks
        (root / "user-settings.json").write_text(
            json.dumps(document), encoding="utf-8")

        monkeypatch.setenv("ZEPOS_USER_ROOT", str(root))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(root))

        spec = importlib.util.spec_from_file_location(
            f"zepos_style_clocks_{root.name}", SRC / "style_definition.py")
        style = importlib.util.module_from_spec(spec)
        # Put back immediately: left in place it would still be patched
        # when the generated artifact is RUN a few lines later, and every
        # one of those runs would get this stand-in instead of a child.
        with mock.patch.object(subprocess, "run", _no_compositor):
            spec.loader.exec_module(style)

        import template_processor

        output = root / "clocks.sh"
        template_processor.ConfigProcessor(
            styles=style.STYLE_VARIABLES,
            paths={"ZEPOS_SYSTEM_ROOT": str(SRC)},
        ).apply_template(TEMPLATES / f"{TEMPLATE}.template", output)
        # apply_template raises on an unresolved placeholder, so this can
        # only fail if it ever stops doing so - the property the whole
        # SSOT arrangement exists for, at the cost of one line.
        assert "{{" not in output.read_text(encoding="utf-8")
        output.chmod(0o755)
        return output

    return _build


# --------------------------------------------------------------------
# running one under env -i
# --------------------------------------------------------------------

def _stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text("#!/bin/bash\n"
                    "# Test stub. Never reaches the real command.\n"
                    + body, encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture
def stubs(tmp_path):
    """`date` and `jq`, and nothing else on PATH.

    `date` is pure bash: the shell's own printf %()T formats ONE fixed
    instant, and it reads TZ out of the environment the way date(1) does,
    so a zone that is genuinely wrong produces a genuinely wrong time
    here rather than a coincidence. It records every call, because two of
    the tests below are about a call that must NOT happen.

    jq execs the real binary. It reads stdin and writes stdout and
    touches nothing else, which is the whole of the passthrough rule.
    """
    directory = tmp_path / "stubs"
    directory.mkdir()
    calls = tmp_path / "calls.txt"

    _stub(directory, "date", f"""
printf 'date %s\\n' "$*" >> '{calls}'
fmt="${{1#+}}"
printf "%(${{fmt}})T\\n" {FIXED_EPOCH}
""")

    real_jq = shutil.which("jq")
    assert real_jq, "the artifact under test needs jq"
    _stub(directory, "jq", f'exec "{real_jq}" "$@"\n')

    class Control:
        path = directory
        transcript = calls

        @staticmethod
        def calls_of(command: str) -> list[str]:
            if not calls.exists():
                return []
            return [line for line in calls.read_text(encoding="utf-8").splitlines()
                    if line.split(" ", 1)[0] == command]

    return Control


@pytest.fixture
def run_clocks(build, stubs, tmp_path):
    """Generate for a settings section, run it, return the parsed object."""
    # Stated rather than assumed: the script asks this directory whether
    # a zone exists, and every assertion about "unknown zone" below is
    # meaningless if the directory is not there at all.
    assert (ZONEINFO / TOKYO).is_file(), (
        f"{ZONEINFO} has no {TOKYO} - this machine has no timezone database, "
        "so nothing below is measuring what it claims to")

    def run(clocks: dict | None = None):
        script = build(clocks)
        path = str(stubs.path)
        assert path.split(os.pathsep) == [path], "PATH must hold one entry"
        assert not os.environ.get("PATH", "").startswith(path), (
            "the stub directory is on the parent's PATH - the isolation "
            "would be a coincidence, not a guarantee")
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        result = subprocess.run(
            [ENV, "-i", f"PATH={path}", f"HOME={home}", BASH, str(script)],
            env={}, input="", capture_output=True, text=True, timeout=60)
        conftest.assert_no_missing_command(result)
        assert result.returncode == 0, result.stdout + result.stderr
        # Waybar reads one JSON object per run. Anything else and the
        # module renders nothing, with no hint anywhere why.
        return json.loads(result.stdout)

    return run


# ====================================================================
# 3. what the artifact does
# ====================================================================

@pytest.mark.allow_subprocess
def test_nothing_configured_renders_nothing_at_all(run_clocks, stubs):
    """The shipping state, and the whole point of the change.

    Waybar hides a module whose text is empty, so this is not a silent
    module - it is an absent one. And `date` is not called even once: a
    module that renders nothing must not be doing work to get there.
    """
    output = run_clocks()

    assert output["text"] == ""
    assert output["class"] == "clocks-unconfigured"
    assert stubs.calls_of("date") == [], (
        "an unconfigured module asked for the time anyway")
    assert "clocks.zones" in output["tooltip"], (
        "the tooltip has to say which setting turns this on")


@pytest.mark.allow_subprocess
def test_one_zone_renders_that_zone_and_only_that_zone(run_clocks, monkeypatch):
    output = run_clocks({"zones": [TOKYO]})

    assert expected(TOKYO) in output["text"]
    assert "Tokyo" in output["text"]
    assert output["class"] == "clocks-ok"
    # The IANA name is what identifies the zone, so it belongs where a
    # user can read it back - the label may be anything they like.
    assert TOKYO in output["tooltip"]


@pytest.mark.allow_subprocess
def test_three_zones_render_three_times_in_order(run_clocks):
    """The case the origin could not express at all.

    Three modules would have meant a third template, a third route, a
    third bar module and a third stylesheet rule; the count is a setting
    now, and the bar is one module whatever it holds.
    """
    output = run_clocks({"zones": [AUCKLAND, TOKYO, NEW_YORK]})

    text = output["text"]
    positions = [text.index(expected(zone))
                 for zone in (AUCKLAND, TOKYO, NEW_YORK)]
    assert positions == sorted(positions), (
        f"the zones came out in a different order than they were set: {text}")
    # All three offsets differ at this instant, so three identical times
    # would mean TZ never reached `date`.
    assert len({expected(zone) for zone in (AUCKLAND, TOKYO, NEW_YORK)}) == 3
    for zone in (AUCKLAND, TOKYO, NEW_YORK):
        assert zone in output["tooltip"]


@pytest.mark.allow_subprocess
def test_a_zone_no_database_knows_is_named_rather_than_shown_as_utc(
        run_clocks, stubs, monkeypatch):
    """Measured behaviour of date(1), and the reason this check exists.

    `TZ=Mars/Olympus_Mons date +"%H:%M %Z"` prints the UTC time with
    "Mars" as the zone abbreviation and exits 0. Nothing is written to
    stderr and nothing about the output says it is not what was asked
    for, so a typo in a settings file becomes a clock that is quietly
    hours wrong - and believed, because it looks exactly like a clock.

    So the zone is looked up in the timezone database first, and `date`
    is not asked at all when it is not there.
    """
    monkeypatch.syspath_prepend(str(SRC))
    import icons_db

    output = run_clocks({"zones": [NOWHERE]})

    assert expected("UTC") not in output["text"], (
        "an unknown zone was rendered as UTC, which is exactly the silent "
        "wrong answer this check exists to prevent")
    assert icons_db.ALL_ICONS["ICON_QUESTION"] in output["text"]
    assert output["class"] == "clocks-unknown-zone"
    assert NOWHERE in output["tooltip"]
    assert stubs.calls_of("date") == [], (
        "date was asked about a zone the database does not have")


@pytest.mark.allow_subprocess
def test_one_unknown_zone_does_not_take_the_working_ones_down(run_clocks):
    """A typo in the third entry must not blank the first two."""
    output = run_clocks({"zones": [TOKYO, NOWHERE, NEW_YORK]})

    assert expected(TOKYO) in output["text"]
    assert expected(NEW_YORK) in output["text"]
    assert output["class"] == "clocks-unknown-zone"


@pytest.mark.allow_subprocess
def test_the_format_from_the_settings_reaches_date(run_clocks, stubs):
    output = run_clocks({"zones": [TOKYO], "format": "%H:%M:%S"})

    assert expected(TOKYO, "%H:%M:%S") in output["text"]
    assert any("%H:%M:%S" in line for line in stubs.calls_of("date")), (
        "the configured format never reached date")


@pytest.mark.allow_subprocess
def test_a_label_with_a_quote_in_it_still_produces_valid_json(run_clocks):
    """The defect a printf-built JSON object ships with.

    One double quote in a value closes the string early; Waybar's parser
    gives up on the whole object and the module simply disappears, which
    is the hardest failure of this kind to diagnose from a bar that shows
    nothing. run_clocks() parses the output, so this test fails at the
    parse if the JSON is built by hand.
    """
    output = run_clocks({"zones": [{"zone": TOKYO, "label": 'Bob "Chef" \\ K'}]})

    assert 'Bob "Chef" \\ K' in output["text"]


@pytest.mark.allow_subprocess
def test_a_label_the_user_chose_replaces_the_derived_one_on_the_bar(run_clocks):
    output = run_clocks({"zones": [{"zone": TOKYO, "label": "🇯🇵"}]})

    assert "🇯🇵" in output["text"]
    assert "Tokyo" not in output["text"], (
        "both labels were rendered - the user's choice has to replace the "
        "derived one, not stand beside it")


def test_a_refusal_names_the_settings_file_once(build):
    """One wrapper, not two.

    The style layer wraps a refusal from src/clocks.py so that it carries
    the FILE it came out of - "clocks.zones is the single string ..."
    names a setting but none of the files on a machine. A first version
    wrapped in the section reader AND in the two builders that call it,
    so a settings file whose clocks section is the wrong type at all
    produced the path and "Nothing was generated" twice around one
    sentence. Measured on `"clocks": "Asia/Tokyo"`, through the real
    generator.
    """
    with pytest.raises(Exception) as excinfo:
        build(TOKYO)

    message = str(excinfo.value)
    assert message.count("cannot be used") == 1, message
    assert message.count("Nothing was generated") == 1, message


# ====================================================================
# 4. what is written down about it
# ====================================================================

def test_the_template_names_no_timezone_of_its_own():
    """The regression, stated as a rule rather than as two file names.

    Any `TZ="..."` with something inside it is a place written into the
    distribution again.
    """
    text = (TEMPLATES / f"{TEMPLATE}.template").read_text(encoding="utf-8")

    uses = [line for line in text.splitlines()
            if "TZ=" in line and not line.strip().startswith("#")]
    assert uses, "nothing in the template sets TZ - it cannot be showing a zone"
    for line in uses:
        assert 'TZ="$' in line, (
            f"the zone has to come from a variable, not from this line: {line}")


def test_the_template_forces_no_locale():
    """LANG in front of `date` was decoration that could only mislead.

    For %H:%M it changes nothing. For a format where it would change
    something, an absent locale makes `date` fall back to C without a
    word - so the setting either does nothing or does something other
    than it says. Leaving it out means `date` inherits the session's
    locale, which the user chose and which is generated on their machine.
    """
    text = (TEMPLATES / f"{TEMPLATE}.template").read_text(encoding="utf-8")

    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        assert "LANG=" not in line and "LC_ALL=" not in line, (
            f"a locale is forced in the template: {line}")


def test_the_template_says_how_to_configure_it():
    """A feature that ships switched off has to say how to switch it on,
    in the file somebody opens when the bar shows nothing."""
    text = (TEMPLATES / f"{TEMPLATE}.template").read_text(encoding="utf-8")

    assert "clocks.zones" in text
    assert "zepos-settings" in text


def test_the_bar_places_the_clock_module_and_defines_it_once():
    """Placed and undefined is a module that never gets built; defined
    and unplaced is a `case` branch nothing reaches. The full agreement
    over a generated bar is asserted in
    tests/src/test_reference_resolution.py - this is the one module this
    file is responsible for, so that a change here fails here.

    ZWEI DATEIEN SEIT DEM 12.08.2026, und das ist der ganze Unterschied
    zu vorher: der ZWEIG steht in der Vorlage, der PLATZ in
    src/style_definition.py. MODULES_LEFT ist dorthin umgezogen, damit
    beide Haelften der Leiste einstellbar sind - die Begruendung steht
    dort unter "WAS AUF DER LEISTE STEHT". Der Test fragt weiterhin
    beides, nur eben je einmal an der Stelle, an der es jetzt steht.
    """
    bar = (TEMPLATES / "ags-bar.template").read_text(encoding="utf-8")

    assert 'case "custom/clocks":' in bar, (
        "die Leiste kennt kein Modul custom/clocks")
    assert bar.count('"custom/clocks"') == 1, (
        "custom/clocks has to appear exactly once in the template: as the "
        "case branch that builds it. Its place on the bar is in "
        "src/style_definition.py")
    placed = (SRC / "style_definition.py").read_text(encoding="utf-8")
    assert placed.count('"custom/clocks"') == 1, (
        "custom/clocks steht nicht genau einmal auf einer ausgelieferten "
        "Liste in src/style_definition.py, also wird sein Zweig entweder "
        "nie erreicht oder zweimal")
    assert "time-de" not in bar and "time-br" not in bar, (
        "the two place-bound clock modules are still on the bar")


def test_the_settings_document_offers_the_section():
    """A key the schema does not know is refused by `zepos-settings set`,
    which would leave the feature configurable only by hand-editing
    JSON - the exact state the weather location was rescued from."""
    import src.settings as settings_module

    section = settings_module.defaults()["clocks"]
    assert section == {"format": DEFAULT_FORMAT, "zones": []}


# ====================================================================
# 5. zepos-doctor asks whether the zones exist
# ====================================================================
#
# The bar module already refuses to invent a time for a zone it cannot
# find - it prints the label with a question mark, writes the reason into
# its tooltip and sets a class the stylesheet colours. That is the right
# answer in the right place, and it is still a tooltip: it exists while
# the pointer is over one small module of one bar, and the user has to be
# suspicious enough to hover there.
#
# A typo in clocks.zones is exactly the case where they are NOT
# suspicious, because the failure looks like a working clock until the
# hour is compared with something. So the same question is asked from the
# command line, where a user can ask it deliberately and a script can act
# on the exit status - the arrangement src/audio.py --check already has
# for a device name that matches nothing.


@pytest.fixture
def doctor(monkeypatch):
    """The module as it is loaded on an installed system: flat, from the
    system root, beside every other module."""
    monkeypatch.syspath_prepend(str(SRC))
    import doctor

    return doctor


def _settings_document(tmp_path, document):
    """Write a settings file the doctor will read, and point it there."""
    import src.settings as settings_module

    root = tmp_path / "zepos"
    root.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": settings_module.SCHEMA_VERSION}
    payload.update(document)
    (root / settings_module.FILENAME).write_text(
        json.dumps(payload), encoding="utf-8")
    return root


def test_the_doctor_names_a_zone_the_timezone_database_does_not_have(
        doctor, tmp_path, monkeypatch):
    """The finding, with the zone in it.

    Not "one of your clocks is wrong": a user with four zones cannot act
    on that, which is the same reason clocks.py puts the index in its own
    refusals.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("ZEPOS_USER_ROOT",
                       str(_settings_document(tmp_path, {
                           "clocks": {"zones": [TOKYO, NOWHERE]}})))

    findings = [f for f in doctor.collect(runner=_no_command)
                if NOWHERE in str(f)]

    assert len(findings) == 1, findings
    assert TOKYO not in str(findings[0]), (
        "a zone the database does have was reported alongside it")
    assert "timedatectl list-timezones" in str(findings[0]), (
        "the finding does not say where the known names come from")
    assert "clocks.zones" in str(findings[0]), (
        "the finding does not name the setting to correct")


def test_the_doctor_is_silent_about_zones_that_exist(doctor, tmp_path,
                                                     monkeypatch):
    """The negative control. Without it the test above passes on a check
    that reports every zone."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("ZEPOS_USER_ROOT",
                       str(_settings_document(tmp_path, {
                           "clocks": {"zones": [TOKYO, NEW_YORK, AUCKLAND]}})))

    assert [f for f in doctor.collect(runner=_no_command)
            if "clocks" in str(f)] == []


def test_the_doctor_looks_where_the_bar_module_looks(doctor, tmp_path,
                                                     monkeypatch):
    """TZDIR, the same variable the generated script honours.

    Both have to read one database or the doctor is answering about a
    different machine than the bar is. Asserted by moving the database:
    with TZDIR naming a directory that holds only Tokyo, New York has to
    become a finding.
    """
    database = tmp_path / "zoneinfo"
    (database / "Asia").mkdir(parents=True)
    (database / "Asia" / "Tokyo").write_bytes(b"TZif")

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("ZEPOS_USER_ROOT",
                       str(_settings_document(tmp_path, {
                           "clocks": {"zones": [TOKYO, NEW_YORK]}})))
    monkeypatch.setenv("TZDIR", str(database))

    reported = [str(f) for f in doctor.collect(runner=_no_command)
                if "clocks.zones" in str(f)]

    assert len(reported) == 1, reported
    assert NEW_YORK in reported[0] and TOKYO not in reported[0]


def test_an_unusable_clocks_section_is_a_finding_rather_than_a_traceback(
        doctor, tmp_path, monkeypatch):
    """`"zones": "Asia/Tokyo"` - one zone as a string - is the likeliest
    hand-edit of this file. clocks.py refuses it by name, and the doctor
    has to carry that refusal through as a finding: a diagnostic tool
    that dies on the configuration it was asked to diagnose reports
    nothing about anything else either."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("ZEPOS_USER_ROOT",
                       str(_settings_document(tmp_path, {
                           "clocks": {"zones": TOKYO}})))

    findings = [f for f in doctor.collect(runner=_no_command)
                if "clocks" in str(f)]

    assert len(findings) == 1, findings
    assert TOKYO in str(findings[0])


def _no_command(argv, **kwargs):
    """No `ip`, no `hyprctl`: this file's subject is the settings, and a
    doctor run that reached the developer's own routing table would make
    the assertions above depend on it."""
    raise FileNotFoundError(argv[0])
