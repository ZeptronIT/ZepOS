# SPDX-License-Identifier: GPL-3.0-or-later
"""One desk's hardware, taken back out of the artifacts that ship.

Three groups of findings, one disease. Each of them names a piece of
equipment - or a place on a screen - that is true of exactly one computer,
and each fails on every other machine in a way that produces no message
anywhere:

  * The two audio templates pinned four devices of the author's: a
    headset and a webcam by the ALSA node names their USB product strings
    produce, a microphone by its product name, a pair of headphones by
    their Bluetooth address. A WirePlumber rule whose match never fires
    is INDISTINGUISHABLE from one that fires - the file parses, the
    daemon starts, nothing is logged - so a stranger was told their
    microphone was filtered and their webcam kept out of the way, and
    neither was true. The names come from the user settings now, and an
    unset one produces a file that says so rather than a rule matching
    nothing.
  * The hardware monitor printed one cooler's product designation and one
    graphics card's into the tooltip, BESIDE READINGS TAKEN FROM THE
    MACHINE IT RUNS ON. That is worse than an unlabelled number: a user
    with a different cooler read their own liquid temperature under
    somebody else's product name. liquidctl and nvidia-smi both report
    what the device actually is; that is used when it comes, and nothing
    is claimed when it does not.
  * The development terminals were placed at pixel coordinates measured
    off the author's monitor layout. On a smaller screen the windows land
    partly or wholly outside it, and a window Hyprland has moved off the
    visible area cannot be reached with the mouse. The geometry follows
    from the screen the windows open on, and that screen comes from
    monitors.py - the same answer the workspace rules and the bar are
    built from, so it cannot disagree with them.

None of this is visible to a test that reads the files: every one of them
reads perfectly sensibly, which is how all three survived. So the
artifacts are GENERATED and then EXECUTED.

Safety: every child runs through `env -i` with the stub directory as the
ONLY entry on PATH, asserted before each run, so a command with no stub
fails with "command not found" rather than reaching the real `liquidctl`,
`nvidia-smi`, `pactl`, `wpctl` or `hyprctl` on the machine running the
tests. HOME, TMPDIR and XDG_RUNTIME_DIR all point inside tmp_path, and no
device name used anywhere below belongs to a product that exists.
"""
import importlib.util
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
TEMPLATES = SRC / "templates"

BASH = "/bin/bash"
ENV = "/usr/bin/env"

# Invented, and deliberately not a device anybody sells. If any of this
# ever keys on these strings again, it keys on nothing.
COOLER_NAME = "Waterworks Testing Rig"
GPU_NAME = "Probe Graphics Adapter"
MIC_NODE = "alsa_input.probe-microphone.mono-fallback"
SECOND_MIC_NODE = "alsa_input.probe-second-microphone.mono-fallback"
SINK_NODE = "alsa_output.probe-speakers.stereo"


# --------------------------------------------------------------------
# generating an artifact from a chosen settings document
# --------------------------------------------------------------------

def _no_compositor(*args, **kwargs):
    """A subprocess.run that answers "hyprctl said nothing useful".

    style_definition asks the compositor for the attached screens while
    it builds its variables. Patched explicitly rather than left to the
    isolation guard: the guard's refusal happens to be a RuntimeError,
    which monitors.detect() also raises and attached_screens() catches,
    so the two are indistinguishable here - and a test that depends on
    which one fired is a test that changes meaning when conftest does.
    """
    return subprocess.CompletedProcess(args[0] if args else [], 1,
                                       stdout="", stderr="not running")


@pytest.fixture
def build(tmp_path, monkeypatch):
    """Generate one template against a settings document of our choosing.

    A FRESH style_definition per call. That module reads the settings
    once, at import, and caches them in USER_SETTINGS - a shared module
    would carry the first test's devices into the second.
    """
    monkeypatch.syspath_prepend(str(SRC))
    counter = itertools.count()

    def _build(template: str, output: Path, settings: dict | None = None) -> Path:
        root = tmp_path / f"settings-{next(counter)}"
        root.mkdir(parents=True, exist_ok=True)
        document = {"schema_version": 1}
        document.update(settings or {})
        (root / "user-settings.json").write_text(
            json.dumps(document), encoding="utf-8")

        monkeypatch.setenv("ZEPOS_USER_ROOT", str(root))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(root))

        spec = importlib.util.spec_from_file_location(
            f"zepos_style_probe_{root.name}", SRC / "style_definition.py")
        style = importlib.util.module_from_spec(spec)
        # Patched for the import and put back immediately. Left in place
        # it would still be there when the generated artifact is RUN a
        # few lines later in the caller, and every one of those runs
        # would get this stand-in's "not running" instead of starting a
        # child at all - measured, as eleven tests that never executed
        # anything and said so in a way that looked like a real failure.
        with mock.patch.object(subprocess, "run", _no_compositor):
            spec.loader.exec_module(style)

        import template_processor

        output.parent.mkdir(parents=True, exist_ok=True)
        template_processor.ConfigProcessor(
            styles=style.STYLE_VARIABLES,
            paths={"ZEPOS_SYSTEM_ROOT": str(SRC)},
        ).apply_template(TEMPLATES / f"{template}.template", output)
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


def _passthrough(directory: Path, *names: str) -> None:
    """Commands whose real binary reaches nothing outside tmp_path."""
    for name in names:
        real = shutil.which(name)
        assert real, f"the artifact under test needs {name}"
        _stub(directory, name, f'exec "{real}" "$@"\n')


def _python(directory: Path) -> None:
    """The interpreter running the tests, reachable as `python3`.

    Named absolutely inside the stub, so finding it never depends on the
    stub PATH the child is given.
    """
    _stub(directory, "python3", f'exec "{sys.executable}" "$@"\n')


def _recorder(directory: Path, calls: Path, *names: str) -> None:
    """Stubs that write down every call and then succeed.

    Recording first and unconditionally: an assertion that a command did
    NOT run is only worth something if every run would have been written
    down.
    """
    for name in names:
        _stub(directory, name,
              f"printf '{name} %s\\n' \"$*\" >> '{calls}'\nexit 0\n")


def _calls(calls: Path, command: str) -> list[str]:
    if not calls.exists():
        return []
    return [line for line in calls.read_text(encoding="utf-8").splitlines()
            if line.split(" ", 1)[0] == command]


def _run(argv, stubs: Path, tmp_path: Path, extra: dict | None = None):
    """One child, with the stub directory as the whole of its PATH."""
    path = str(stubs)
    assert path.split(os.pathsep) == [str(stubs)], "PATH must hold one entry"
    assert not os.environ.get("PATH", "").startswith(path), (
        "the stub directory is on the parent's PATH - the isolation is a "
        "coincidence, not a guarantee")
    runtime = tmp_path / "runtime"
    runtime.mkdir(exist_ok=True)
    environment = {
        "PATH": path,
        "HOME": str(tmp_path / "home"),
        "TMPDIR": str(tmp_path),
        "XDG_RUNTIME_DIR": str(runtime),
    }
    environment.update(extra or {})
    result = subprocess.run(
        [ENV, "-i", *(f"{k}={v}" for k, v in environment.items()), *argv],
        env={}, input="", capture_output=True, text=True, timeout=60)
    assert "command not found" not in result.stderr, (
        "the artifact called something the stub directory does not provide:\n"
        + result.stderr)
    return result


# ====================================================================
# 1. AUDIO - the devices come from the settings, or from nowhere
# ====================================================================

def test_a_machine_with_no_audio_settings_gets_no_rule_at_all(build, tmp_path):
    """The shipping state, which is every machine but one.

    Not an empty `node.rules = [ ]` and not a pinned default device: an
    empty rule list is valid, does nothing, and reads to anyone opening
    the file as if rules were in force - and a default sink pointing at a
    node that is not there is silence with no error anywhere.
    """
    text = build("wireplumber-config",
                 tmp_path / "out" / "wireplumber.conf").read_text()

    assert "node.rules" not in text, (
        "an empty rule list is indistinguishable from rules that fire")
    assert "wireplumber.settings" not in text, (
        "nothing was configured, so nothing may be overridden")
    assert "PipeWire" in text and "keeps its own" in text, (
        "the file has to say that this is the shipping state, not a fault")
    # And it has to say what to do about it, or the feature is simply
    # gone rather than configurable.
    assert "audio.blocked_sources" in text
    assert "pactl list short sources" in text


def test_a_configured_source_becomes_exactly_one_rule(build, tmp_path):
    text = build("wireplumber-config", tmp_path / "out" / "wireplumber.conf",
                 settings={"audio": {"blocked_sources": [MIC_NODE]}}).read_text()

    assert f'node.name = "{MIC_NODE}"' in text
    assert text.count("node.autoconnect = false") == 1


def test_three_configured_sources_yield_three_rules(build, tmp_path):
    """The origin spelled out exactly two. A user with three devices to
    keep out of the way had no way to say so, and one with none had no
    way to say that either."""
    names = [MIC_NODE, SECOND_MIC_NODE, "alsa_input.probe-third.mono-fallback"]
    text = build("wireplumber-config", tmp_path / "out" / "wireplumber.conf",
                 settings={"audio": {"blocked_sources": names}}).read_text()

    assert text.count("node.autoconnect = false") == 3
    for name in names:
        assert f'node.name = "{name}"' in text


def test_only_the_default_that_was_set_is_written(build, tmp_path):
    """Half a configuration must come out as half a configuration.

    The origin pinned BOTH defaults to EasyEffects' virtual nodes. On a
    machine where EasyEffects is not running that is a default device
    nothing can play through - which the user meets as silence, from a
    file they never opened.
    """
    text = build("wireplumber-config", tmp_path / "out" / "wireplumber.conf",
                 settings={"audio": {"default_sink": SINK_NODE}}).read_text()

    assert f'default.configured.audio.sink = "{SINK_NODE}"' in text
    assert "default.configured.audio.source" not in text
    # The two linking keys only mean anything beside a pinned default -
    # they stop a newly appeared device from moving the stream off the
    # one the user chose - so they appear with it and not otherwise.
    assert "linking.follow-default-target" in text


def test_the_easyeffects_input_is_blank_until_somebody_sets_it(build, tmp_path):
    """And the file stays comment-free, deliberately.

    It is read by a settings library that rewrites the whole file
    whenever the application saves, and whether that library keeps a
    comment - or tolerates one at all - is not something to establish
    experimentally on somebody's audio configuration. The two other
    templates in this format (kdeglobals, BreezeDark.colors) carry no
    comment either, and the wireplumber template's header names
    audio.effects_input on this one's behalf.
    """
    text = build("easyeffects-config", tmp_path / "out" / "easyeffectsrc").read_text()

    assert "inputDevice=\n" in text, (
        "an unset input device must be blank, not a device")
    # The Bluetooth address the origin stored was dead weight even there:
    # useDefaultOutputDevice overrides it. It is gone entirely.
    assert "\noutputDevice" not in text
    assert "useDefaultOutputDevice=true" in text
    # One person's window on one person's screen.
    assert not re.search(r"^(height|width)=", text, re.M), (
        "the stored window geometry was one desk's")
    assert not [line for line in text.splitlines()
                if line.lstrip().startswith(("#", ";"))], (
        "a comment in a file this project cannot prove the parser accepts")
    # And the fourth setting is documented where a comment IS safe.
    wireplumber = (TEMPLATES / "wireplumber-config.template").read_text(
        encoding="utf-8")
    assert "audio.effects_input" in wireplumber, (
        "nothing anywhere tells the user this setting exists")


def test_the_easyeffects_input_is_the_configured_one(build, tmp_path):
    text = build("easyeffects-config", tmp_path / "out" / "easyeffectsrc",
                 settings={"audio": {"effects_input": MIC_NODE}}).read_text()

    assert f"inputDevice={MIC_NODE}" in text


def test_a_single_string_where_a_list_belongs_is_refused(build, tmp_path):
    """The likeliest hand-edit of this file, and the one that must not be
    iterated. A str satisfies every iterable signature a list does, so
    one node name written without brackets would become one rule per
    CHARACTER - forty rules, each matching a letter."""
    with pytest.raises(ValueError) as raised:
        build("wireplumber-config", tmp_path / "out" / "wireplumber.conf",
              settings={"audio": {"blocked_sources": MIC_NODE}})

    message = str(raised.value)
    assert "audio.blocked_sources" in message, (
        "the message has to name the setting that must be corrected")
    assert "user-settings.json" in message, (
        "and the file it is in - there is more than one settings file on a "
        "machine")


# --------------------------------------------------------------------
# 1b. and whether the names still match anything, asked at run time
# --------------------------------------------------------------------

def _audio_stubs(tmp_path: Path, *, pactl_sources=None, pactl_sinks=None,
                 wpctl=None) -> Path:
    """A stub directory answering as PipeWire's two command-line tools.

    `pactl_sources=None` means the command is not there at all - no stub
    is written, so the child gets ENOENT, which is what a machine without
    pipewire-pulse installed does.
    """
    stubs = tmp_path / "stubs"
    stubs.mkdir(exist_ok=True)
    _python(stubs)

    if pactl_sources is not None or pactl_sinks is not None:
        listing = tmp_path / "pactl"
        listing.mkdir(exist_ok=True)
        for kind, names in (("sources", pactl_sources or ()),
                            ("sinks", pactl_sinks or ())):
            (listing / kind).write_text(
                "".join(f"{50 + index}\t{name}\tPipeWire\ts32le 2ch 48000Hz\t"
                        f"SUSPENDED\n"
                        for index, name in enumerate(names)),
                encoding="utf-8")
        _stub(stubs, "pactl",
              f'if [ "$1" = list ] && [ "$2" = short ]; then\n'
              f'    exec /bin/cat "{listing}/$3"\n'
              f'fi\nexit 1\n')

    if wpctl is not None:
        status = tmp_path / "wpctl-status.txt"
        headings = []
        inspect = {}
        for kind, names in (("Sinks:", wpctl.get("sinks", ())),
                            ("Sources:", wpctl.get("sources", ()))):
            headings.append(f" \u251c\u2500 {kind}")
            for index, name in enumerate(names):
                identifier = 60 + len(inspect)
                headings.append(
                    f" \u2502      {identifier}. Probe device {index}   "
                    f"[vol: 1.00]")
                inspect[identifier] = name
            headings.append(" \u2502  ")
        status.write_text("Audio\n" + "\n".join(headings) + "\n",
                          encoding="utf-8")
        cases = "".join(
            f'        {identifier}) printf \'    node.name = "{name}"\\n\' ;;\n'
            for identifier, name in inspect.items())
        _stub(stubs, "wpctl",
              f'case "$1" in\n'
              f'    status) exec /bin/cat "{status}" ;;\n'
              f'    inspect)\n'
              f'        case "$2" in\n{cases}        esac\n'
              f'        exit 0 ;;\n'
              f'esac\nexit 1\n')

    return stubs


def _settings_root(tmp_path: Path, audio: dict | None) -> Path:
    root = tmp_path / "user-root"
    root.mkdir(exist_ok=True)
    document = {"schema_version": 1}
    if audio is not None:
        document["audio"] = audio
    (root / "user-settings.json").write_text(json.dumps(document),
                                             encoding="utf-8")
    return root


def _check(tmp_path, stubs, root):
    return _run(["python3", str(SRC / "audio.py"), "--check"], stubs, tmp_path,
                extra={"ZEPOS_USER_ROOT": str(root)})


@pytest.mark.allow_subprocess
def test_naming_no_device_cannot_fail_and_asks_nobody(tmp_path):
    """No stubs at all, deliberately.

    A machine that names no device has nothing that can fail to match, so
    the sound server must not even be asked. Generating a configuration
    routinely happens during installation and from a TTY, where asking
    would produce a warning about a configuration nobody made.
    """
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    _python(stubs)

    result = _check(tmp_path, stubs, _settings_root(tmp_path, None))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "nothing here can fail to match" in result.stdout


@pytest.mark.allow_subprocess
def test_a_configured_device_that_is_attached_is_reported_as_such(tmp_path):
    root = _settings_root(tmp_path, {"blocked_sources": [MIC_NODE],
                                     "default_sink": SINK_NODE})
    stubs = _audio_stubs(tmp_path, pactl_sources=[MIC_NODE],
                         pactl_sinks=[SINK_NODE])

    result = _check(tmp_path, stubs, root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"ok      audio.blocked_sources: {MIC_NODE}" in result.stdout
    assert f"ok      audio.default_sink: {SINK_NODE}" in result.stdout


@pytest.mark.allow_subprocess
def test_a_rule_that_matches_nothing_says_so(tmp_path):
    """The whole point of the exercise.

    This is exactly the state every machine but the author's was in, and
    the state nothing anywhere reported. It has to be a non-zero exit and
    a line naming the setting AND the name that matches nothing - "audio
    is misconfigured" sends nobody anywhere.
    """
    root = _settings_root(tmp_path, {"blocked_sources": [MIC_NODE]})
    stubs = _audio_stubs(tmp_path, pactl_sources=[SECOND_MIC_NODE])

    result = _check(tmp_path, stubs, root)

    assert result.returncode == 1, result.stdout + result.stderr
    assert f"MISSING audio.blocked_sources: {MIC_NODE}" in result.stdout
    assert "matches no attached device" in result.stdout


@pytest.mark.allow_subprocess
def test_a_sink_named_as_a_source_is_a_rule_that_never_fires(tmp_path):
    """The likelier of the two mistakes once somebody copies a name out
    of the wrong listing, and the harder one to see: the name IS there."""
    root = _settings_root(tmp_path, {"blocked_sources": [SINK_NODE]})
    stubs = _audio_stubs(tmp_path, pactl_sources=[MIC_NODE],
                         pactl_sinks=[SINK_NODE])

    result = _check(tmp_path, stubs, root)

    assert result.returncode == 1, result.stdout + result.stderr
    assert f"WRONG   audio.blocked_sources: {SINK_NODE} exists, but not as a source" \
        in result.stdout


@pytest.mark.allow_subprocess
def test_without_pactl_wireplumbers_own_tool_answers(tmp_path):
    """pactl belongs to pipewire-pulse, which need not be installed.
    wpctl belongs to WirePlumber, which by definition is - this is its
    configuration we are generating."""
    root = _settings_root(tmp_path, {"blocked_sources": [MIC_NODE]})
    stubs = _audio_stubs(tmp_path, wpctl={"sources": [MIC_NODE],
                                          "sinks": [SINK_NODE]})
    assert not (stubs / "pactl").exists(), "this test is about pactl's absence"

    result = _check(tmp_path, stubs, root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"ok      audio.blocked_sources: {MIC_NODE}" in result.stdout


@pytest.mark.allow_subprocess
def test_no_tool_at_all_is_not_reported_as_a_missing_device(tmp_path):
    """"The sound server could not be asked" and "the device is not
    there" are different statements, and only one of them is a reason to
    send the user off to change a setting that may be perfectly right."""
    root = _settings_root(tmp_path, {"blocked_sources": [MIC_NODE]})
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    _python(stubs)

    result = _check(tmp_path, stubs, root)

    assert result.returncode == 1
    assert "could not check the configured devices" in result.stderr
    assert "MISSING" not in result.stdout


@pytest.mark.allow_subprocess
def test_the_listing_shows_what_a_rule_could_be_keyed_on(tmp_path):
    """`--list` is what somebody runs to find the string to configure.
    It has to print the NODE NAME - a rule keyed on the description a
    person recognises matches nothing at all."""
    stubs = _audio_stubs(tmp_path, pactl_sources=[MIC_NODE],
                         pactl_sinks=[SINK_NODE])

    result = _run(["python3", str(SRC / "audio.py"), "--list"], stubs, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"source\t{MIC_NODE}" in result.stdout
    assert f"sink\t{SINK_NODE}" in result.stdout


# ====================================================================
# 2. HARDWARE MONITOR - the label comes from the device
# ====================================================================

def _monitor_stubs(tmp_path: Path, *, liquidctl=None, nvidia=None,
                   rgb=None) -> Path:
    stubs = tmp_path / "stubs"
    stubs.mkdir(exist_ok=True)
    _python(stubs)
    for name, answer in (("liquidctl", liquidctl), ("nvidia-smi", nvidia),
                         ("openrgb", rgb)):
        if answer is None:
            continue
        payload = tmp_path / f"{name}.txt"
        payload.write_text(answer, encoding="utf-8")
        _stub(stubs, name, f'exec /bin/cat "{payload}"\n')
    return stubs


def _bar(tmp_path, script: Path, stubs: Path, run_dir: Path,
         extra: dict | None = None) -> dict:
    """One run of the generated bar module, as the bar reads it."""
    result = _run(["python3", str(script)], stubs, run_dir, extra)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _machine(root: Path, *, busy: int = 5, memory_used: int = 10,
             temperature: int | None = None, sensor: str = "coretemp") -> dict:
    """Ein /proc und ein /sys, in denen genau das steht, was gemessen wird.

    WARUM DAS SEIN MUSS, STATT DAS ECHTE /proc ZU NEHMEN
        hardware-monitor.py liest seit dem 13.08.2026 Prozessorlast,
        Arbeitsspeicher und Temperatur aus dem Kern - genau deshalb sagt
        es auf einem Notebook nicht mehr "No HW". Damit haenge aber jede
        Zusicherung darueber daran, wie warm und wie ausgelastet die
        Maschine gerade ist, auf der die Suite laeuft: der Zweig
        "kritisch" waere nur zu messen, indem man den Rechner anheizt.

        Dieselbe Bauart wie ZEPOS_POWER_SUPPLY_ROOT in
        bar-status-config.template, und aus demselben Grund.

    Die Last kommt aus dem Unterschied ZWEIER Aufnahmen von /proc/stat.
    Die Datei hier steht still, der Unterschied ist also null - was das
    Skript korrekt als "keine Messung" behandelt und nicht als 0 %. Wer
    eine Last messen will, schreibt die Datei zwischen zwei Laeufen um;
    `busy` setzt den Ausgangsstand.
    """
    proc = root / "proc"
    proc.mkdir(parents=True, exist_ok=True)
    # cpu <user> <nice> <system> <idle> <iowait> ... - die Reihenfolge
    # steht in proc(5).
    (proc / "stat").write_text(
        f"cpu  {busy} 0 0 {100 - busy} 0 0 0 0 0 0\n"
        "cpu0 0 0 0 0 0 0 0 0 0 0\n", encoding="utf-8")
    total = 16_000_000
    (proc / "meminfo").write_text(
        f"MemTotal:       {total} kB\n"
        "MemFree:        1000 kB\n"
        f"MemAvailable:   {total - total * memory_used // 100} kB\n",
        encoding="utf-8")

    hwmon = root / "hwmon"
    hwmon.mkdir(parents=True, exist_ok=True)
    if temperature is not None:
        zone = hwmon / "hwmon0"
        zone.mkdir(exist_ok=True)
        (zone / "name").write_text(sensor + "\n", encoding="utf-8")
        (zone / "temp1_input").write_text(f"{temperature * 1000}\n",
                                          encoding="utf-8")
    return {"ZEPOS_PROC_ROOT": str(proc), "ZEPOS_HWMON_ROOT": str(hwmon)}


@pytest.mark.allow_subprocess
def test_the_tooltip_names_the_device_the_tools_reported(build, tmp_path):
    """The label and the reading have to come from the same machine."""
    script = build("hardware-monitor-config", tmp_path / "hardware-monitor.py")
    stubs = _monitor_stubs(
        tmp_path,
        liquidctl=f"{COOLER_NAME}\n"
                  "\u251c\u2500\u2500 Liquid temperature    29.7  \u00b0C\n"
                  "\u251c\u2500\u2500 Fan 1 speed            634  rpm\n"
                  "\u2514\u2500\u2500 Pump speed            2130  rpm\n",
        nvidia=f"41, 3, 1024, 12288, 32.10, 30, {GPU_NAME}\n")

    output = _bar(tmp_path, script, stubs, tmp_path)

    assert f"{COOLER_NAME}:" in output["tooltip"]
    assert f"{GPU_NAME}:" in output["tooltip"]
    assert "Liquid: 29.7\u00b0C" in output["tooltip"]
    assert "Pump: 2130 RPM" in output["tooltip"]


@pytest.mark.allow_subprocess
def test_a_cooler_that_reports_no_name_is_given_none(build, tmp_path):
    """The half the origin got wrong. It had a product designation to
    print whatever the device turned out to be, so a reading from one
    cooler appeared under another cooler's name. With no name reported,
    the category is all that may be said."""
    script = build("hardware-monitor-config", tmp_path / "hardware-monitor.py")
    stubs = _monitor_stubs(
        tmp_path,
        liquidctl="\u251c\u2500\u2500 Liquid temperature    31.0  \u00b0C\n"
                  "\u2514\u2500\u2500 Pump speed            1900  rpm\n")

    output = _bar(tmp_path, script, stubs, tmp_path)

    assert "Liquid cooler:" in output["tooltip"]
    assert "Liquid: 31.0\u00b0C" in output["tooltip"]
    # Nothing that looks like a product was invented to fill the gap.
    assert not PRODUCT_DESIGNATION.search(output["tooltip"]), (
        f"a device designation appeared from nowhere: {output['tooltip']!r}")


@pytest.mark.allow_subprocess
def test_a_machine_with_none_of_this_hardware_still_says_something(
        build, tmp_path):
    """Der Befund vom 13.08.2026, und er ist der Grund fuer den Umbau.

    GEMELDET: "im header sollte btop dargestellt werden wie am anfang
    auch" - und dass das Modul "No HW" zeige.

    GEMESSEN am selben Tag auf dem Notebook des Nutzers: genau das, und
    zwar dauerhaft. Keine Wasserkuehlung, keine eigenstaendige
    Grafikkarte, kein RGB-Geraet - also die Ausstattung, die die meisten
    Menschen haben -, und dieses Modul konnte darueber nichts sagen und
    nannte den Zustand ausserdem "offline", also einen Fehler.

    Hier stand deshalb bis heute die Erwartung `class ==
    "hardware-offline"` und `"No HW" in text`. Das war die Zusicherung
    darueber, dass der Fehler zuverlaessig auftritt.

    Was ein solcher Rechner jetzt sagt: Prozessorlast und
    Arbeitsspeicher, beides aus /proc, beides auf jeder Maschine da.
    """
    script = build("hardware-monitor-config", tmp_path / "hardware-monitor.py")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    _python(stubs)

    output = _bar(tmp_path, script, stubs, tmp_path,
                  _machine(tmp_path, memory_used=42, temperature=45))

    assert output["class"] == "hardware-normal", output
    assert "No HW" not in output["text"], output
    assert "42%" in output["text"], (
        f"der Arbeitsspeicher steht nicht auf der Leiste: {output}")
    assert "45" in output["tooltip"], (
        f"die Temperatur steht nirgends: {output}")
    assert not PRODUCT_DESIGNATION.search(output["tooltip"])


@pytest.mark.allow_subprocess
def test_a_machine_that_answers_nothing_at_all_is_the_only_offline_case(
        build, tmp_path):
    """"Offline" heisst ab sofort, was das Wort sagt.

    Es gibt weder /proc noch /sys noch eines der drei Werkzeuge. Auf
    einer laufenden Maschine kann das nicht vorkommen - und genau
    deshalb ist es die richtige Bedingung fuer eine Zustandsklasse: sie
    meldet einen Fehler und keine Ausstattung.

    Ohne diese Zeile waere der Zweig, den die Aenderung vom 13.08.2026
    uebrig gelassen hat, ungemessen - und ein Zweig ohne Messung ist der,
    der beim naechsten Anfassen still verschwindet.
    """
    script = build("hardware-monitor-config", tmp_path / "hardware-monitor.py")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    _python(stubs)

    output = _bar(tmp_path, script, stubs, tmp_path, {
        "ZEPOS_PROC_ROOT": str(tmp_path / "gibtsnicht"),
        "ZEPOS_HWMON_ROOT": str(tmp_path / "auchnicht"),
    })

    assert output["class"] == "hardware-offline", output
    assert output["text"].strip(), "ein leeres Modul erklaert gar nichts"
    assert "proc" in output["tooltip"], output


@pytest.mark.allow_subprocess
@pytest.mark.parametrize("temperature, expected", [
    (45, "hardware-normal"),
    (80, "hardware-warning"),
    (90, "hardware-critical"),
])
def test_the_processor_temperature_drives_the_state(build, tmp_path,
                                                    temperature, expected):
    """Die beiden Schwellen, und sie sind an Tjmax geeicht.

    Ein x86-Prozessor drosselt selbst zwischen 95 und 105 Grad. 90 ist
    damit "es wird gleich langsam", 80 "Volllast". Die Zahlen stehen in
    hardware-monitor-config.template mit dieser Begruendung; hier steht,
    dass sie auch greifen.

    Ueber eine nachgestellte hwmon-Wurzel und nicht ueber den echten
    Sensor: sonst waere der kritische Zweig nur zu messen, indem man den
    Rechner anheizt - siehe _machine().
    """
    script = build("hardware-monitor-config", tmp_path / "hardware-monitor.py")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    _python(stubs)

    output = _bar(tmp_path, script, stubs, tmp_path,
                  _machine(tmp_path, temperature=temperature))

    assert output["class"] == expected, output


@pytest.mark.allow_subprocess
def test_a_full_memory_is_a_critical_state(build, tmp_path):
    """95 Prozent belegt heisst, dass der Kern gleich auslagert oder
    Prozesse beendet.

    Ueber MemAvailable und nicht ueber MemFree - die Begruendung steht
    bei get_memory_use() in der Vorlage. Ohne diese Zeile bliebe die
    zweite Haelfte der Zustandsrechnung ungemessen.
    """
    script = build("hardware-monitor-config", tmp_path / "hardware-monitor.py")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    _python(stubs)

    output = _bar(tmp_path, script, stubs, tmp_path,
                  _machine(tmp_path, memory_used=96, temperature=40))

    assert output["class"] == "hardware-critical", output
    assert "96%" in output["text"], output


@pytest.mark.allow_subprocess
def test_a_fans_number_is_not_reported_as_its_speed(build, tmp_path):
    """Found by running the thing rather than reading it.

    liquidctl NUMBERS its fans - "Fan 1 speed   634  rpm" - and the
    parser took the first whole number on the line. So the tooltip of
    every machine with a three-fan cooler read "Fans: 1, 2, 3 RPM": three
    numbers that were never speeds, and that nobody could tell from three
    fans turning very slowly.
    """
    script = build("hardware-monitor-config", tmp_path / "hardware-monitor.py")
    stubs = _monitor_stubs(
        tmp_path,
        liquidctl=f"{COOLER_NAME}\n"
                  "├── Fan 1 speed            634  rpm\n"
                  "├── Fan 2 speed            701  rpm\n"
                  "└── Pump speed            2130  rpm\n")

    output = _bar(tmp_path, script, stubs, tmp_path)

    assert "Fans: 634, 701 RPM" in output["tooltip"]
    assert "Pump: 2130 RPM" in output["tooltip"]


@pytest.mark.allow_subprocess
def test_a_second_devices_fans_are_not_reported_as_the_firsts(build, tmp_path):
    """liquidctl prints a block per device. The origin appended every
    block's fan speeds to one list and printed the lot under one heading,
    so a machine with a cooler AND a fan controller reported the second
    device's fans as the first device's."""
    script = build("hardware-monitor-config", tmp_path / "hardware-monitor.py")
    stubs = _monitor_stubs(
        tmp_path,
        liquidctl=f"{COOLER_NAME}\n"
                  "\u251c\u2500\u2500 Liquid temperature    29.7  \u00b0C\n"
                  "\u2514\u2500\u2500 Fan 1 speed            634  rpm\n"
                  "\n"
                  "Another Testing Controller\n"
                  "\u2514\u2500\u2500 Fan 1 speed           1500  rpm\n")

    output = _bar(tmp_path, script, stubs, tmp_path)

    assert f"{COOLER_NAME}:" in output["tooltip"]
    assert "Fans: 634 RPM" in output["tooltip"]
    assert "1500" not in output["tooltip"], (
        "the second device's reading was labelled with the first's name")


@pytest.mark.allow_subprocess
def test_a_comma_in_the_reported_name_does_not_shift_the_readings(
        build, tmp_path):
    """nvidia-smi separates csv fields with ", " and the product name is
    the one field that could contain that sequence. Queried first, a
    single comma in it moves every reading one place along - the
    temperature becomes the utilisation and the bar colours itself on a
    number that means something else."""
    script = build("hardware-monitor-config", tmp_path / "hardware-monitor.py")
    stubs = _monitor_stubs(tmp_path, nvidia="88, 3, 1024, 12288, 32.10, 30, "
                                            "Probe Adapter, Special Edition\n")

    output = _bar(tmp_path, script, stubs, tmp_path)

    assert "Probe Adapter, Special Edition:" in output["tooltip"]
    assert "Temp: 88\u00b0C" in output["tooltip"]
    assert output["class"] == "hardware-critical", (
        "88 degrees is critical; a shifted field would have read 3")


@pytest.mark.allow_subprocess
def test_the_cache_is_this_users_and_not_a_shared_file_in_tmp(build, tmp_path):
    """A fixed path in /tmp is ONE file for every account on the machine.
    The first user to run this owns it; everybody else's write fails
    through a bare `except: pass`, so their bar re-runs liquidctl and
    nvidia-smi on every refresh and reads the first user's temperatures
    in the meantime."""
    script = build("hardware-monitor-config", tmp_path / "hardware-monitor.py")
    stubs = _monitor_stubs(tmp_path, nvidia=f"41, 3, 1, 2, 3, 4, {GPU_NAME}\n")

    _bar(tmp_path, script, stubs, tmp_path)

    runtime = tmp_path / "runtime"
    cached = list(runtime.glob("*hardware-cache*"))
    assert cached, f"nothing was cached below XDG_RUNTIME_DIR: {list(runtime.iterdir())}"
    assert "/tmp/waybar-hardware-cache.json" not in script.read_text(), (
        "the shared path is still compiled in")


# ====================================================================
# 3. TERMINALS - the geometry follows the screen
# ====================================================================

def _screen(name, x, y, width, height, description="Screen Co Model X 1111",
            **overrides):
    entry = {"name": name, "description": description, "make": "Screen Co",
             "model": "Model X", "x": x, "y": y, "width": width,
             "height": height, "refreshRate": 60.0, "scale": 1.0,
             "transform": 0}
    entry.update(overrides)
    return entry


TITLES = ("ZepOS: Main", "ZepOS: Home")


def _terminal_stubs(tmp_path: Path, screens) -> tuple[Path, Path]:
    stubs = tmp_path / "stubs"
    stubs.mkdir(exist_ok=True)
    calls = tmp_path / "calls.txt"
    _python(stubs)
    _passthrough(stubs, "jq", "cat")
    _recorder(stubs, calls, "setsid", "kitty", "notify-send", "sleep")

    monitors_json = tmp_path / "monitors.json"
    monitors_json.write_text(json.dumps(screens), encoding="utf-8")
    clients_json = tmp_path / "clients.json"
    clients_json.write_text(json.dumps(
        [{"title": title, "address": f"0x{index:04x}", "workspace": {"id": 1}}
         for index, title in enumerate(TITLES, start=1)]), encoding="utf-8")

    _stub(stubs, "hyprctl",
          f'case "$1" in\n'
          f'    monitors) exec /bin/cat "{monitors_json}" ;;\n'
          f'    clients)  exec /bin/cat "{clients_json}" ;;\n'
          f'    dispatch) printf \'hyprctl %s\\n\' "$*" >> "{calls}"; exit 0 ;;\n'
          f'esac\nexit 1\n')
    return stubs, calls


def _placements(calls: Path) -> dict:
    """{address: (x, y, width, height)} out of the recorded dispatches."""
    moved, sized = {}, {}
    for line in _calls(calls, "hyprctl"):
        found = re.search(
            r"(movewindowpixel|resizewindowpixel) exact (-?\d+) (-?\d+),"
            r"address:(\S+)", line)
        if not found:
            continue
        target = moved if found.group(1) == "movewindowpixel" else sized
        target[found.group(4)] = (int(found.group(2)), int(found.group(3)))
    return {address: moved[address] + sized.get(address, ())
            for address in moved}


@pytest.mark.allow_subprocess
def test_the_windows_are_placed_as_fractions_of_their_screen(build, tmp_path):
    script = build("zepos-terminals-config", tmp_path / "zepos-terminals.sh")
    stubs, calls = _terminal_stubs(
        tmp_path, [_screen("DP-1", 0, 0, 3840, 2160)])

    result = _run([BASH, str(script)], stubs, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    placements = _placements(calls)
    assert len(placements) == 2, f"both windows have to be placed: {placements}"
    # 2% and 51% from the left, 20% down, 47% wide, 60% high.
    assert sorted(placements.values()) == [
        (76, 432, 1804, 1296), (1958, 432, 1804, 1296)]


@pytest.mark.allow_subprocess
def test_a_smaller_screen_gets_smaller_windows(build, tmp_path):
    """The measured failure. The origin's numbers put one window at
    x=2357 with a width of 1433 - 3790 pixels along a screen that, here,
    is 1920 wide. A window Hyprland has moved past the edge cannot be
    reached with the mouse."""
    script = build("zepos-terminals-config", tmp_path / "zepos-terminals.sh")
    stubs, calls = _terminal_stubs(
        tmp_path, [_screen("eDP-1", 0, 0, 1920, 1080)])

    result = _run([BASH, str(script)], stubs, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    for x, y, width, height in _placements(calls).values():
        assert 0 <= x and x + width <= 1920, f"{x}+{width} runs off the screen"
        assert 0 <= y and y + height <= 1080, f"{y}+{height} runs off the screen"


@pytest.mark.allow_subprocess
def test_the_screens_own_origin_is_added_to_every_coordinate(build, tmp_path):
    """`movewindowpixel exact` takes LAYOUT coordinates, not coordinates
    on the screen. A desk whose leftmost screen sits at a negative x and
    a non-zero y - which is what the settings application writes for a
    monitor placed left of and above the primary - is the case where
    forgetting the origin puts both windows on the wrong screen
    entirely."""
    script = build("zepos-terminals-config", tmp_path / "zepos-terminals.sh")
    stubs, calls = _terminal_stubs(tmp_path, [
        _screen("DP-1", -2560, 200, 2560, 1440),
        _screen("DP-2", 0, 0, 1920, 1080, description="Screen Co Model Y 2222"),
    ])

    result = _run([BASH, str(script)], stubs, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    # Two screens, ten workspaces: 1-5 on the left one, 6-10 on the
    # right. Workspace 3 is therefore the left screen's, at -2560,200.
    for x, y, width, height in _placements(calls).values():
        assert -2560 <= x and x + width <= 0, f"x={x} is not on that screen"
        assert 200 <= y and y + height <= 1640, f"y={y} is not on that screen"


@pytest.mark.allow_subprocess
def test_a_rotated_screen_is_measured_as_it_stands(build, tmp_path):
    """hyprctl reports the MODE - 2160 wide for a 4K panel, whether it
    stands upright or on its side. A window sized from the mode on a
    portrait screen is wider than the screen it is on."""
    script = build("zepos-terminals-config", tmp_path / "zepos-terminals.sh")
    stubs, calls = _terminal_stubs(
        tmp_path, [_screen("DP-1", 0, 0, 3840, 2160, transform=1)])

    result = _run([BASH, str(script)], stubs, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    placements = _placements(calls)
    assert placements, "nothing was placed at all"
    for x, y, width, height in placements.values():
        assert x + width <= 2160, (
            f"{x}+{width} is wider than the screen standing on its side")
        assert y + height <= 3840


@pytest.mark.allow_subprocess
def test_no_screen_means_no_position_and_a_word_about_it(build, tmp_path):
    """A compositor that answers with no monitors at all. The terminals
    are the point and still open; their placement is not, and a guessed
    coordinate is exactly what this whole change is about."""
    script = build("zepos-terminals-config", tmp_path / "zepos-terminals.sh")
    stubs, calls = _terminal_stubs(tmp_path, [])

    result = _run([BASH, str(script)], stubs, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _placements(calls) == {}, "a coordinate was invented"
    assert "not detectable" in result.stdout, (
        f"the user was told nothing: {result.stdout!r}")
    # The windows still reach the workspace they belong on.
    moves = [line for line in _calls(calls, "hyprctl")
             if "movetoworkspacesilent" in line]
    assert len(moves) == 2, f"the terminals were not opened at all: {moves}"


# ====================================================================
# 4. the guard: this class of thing may not come back
# ====================================================================
#
# Three rules, one per shape the three findings above had. Each is
# written to fire on a SHAPE - or on a fact about how a device is named -
# never on a list of the strings that happen to be in the tree today: a
# pattern naming the four audio nodes would have caught nothing before
# they were written and nothing after they were removed.

# A device identity that carries its own hardware in it. All three
# spellings were in the tree:
#   - an ALSA node name built from a USB product string
#   - a Bluetooth device address
#   - a USB vendor:product pair, which is what the webcam was pinned by
# The word boundary that the monitor-identity guard's serial rule needs
# does not exist inside these - they are one long token glued with dots
# and underscores - which is exactly why that guard could not see them
# and this one keys on the prefix instead.
DEVICE_STRING = re.compile(
    r"\busb-[A-Za-z0-9]{2,}[_-][A-Za-z0-9]"
    r"|\bbluez_(?:output|input)\.[0-9A-Fa-f]{2}[:_]"
    r"|\b[0-9a-f]{4}_[0-9a-f]{4}\b")

# A product designation is not recognisable by shape alone - "H150i" has
# the shape of a hex constant and "F43A" is a codepoint kitty-config is
# full of. What makes it recognisable is the company it keeps: a line
# that is about a piece of equipment. Both halves have to match, so the
# codepoints stay legitimate and a cooler's model name does not.
#
# The vocabulary half is a list of DEVICE KINDS and of the tools that
# report a device's identity - never a list of manufacturers. A vendor
# list catches the vendors somebody thought of; "a line that talks about
# a microphone" catches the microphone nobody has bought yet.
DEVICE_CONTEXT = re.compile(
    # the tools that report what a device is
    r"\bliquidctl\b|\bnvidia-smi\b|\bopenrgb\b|\bwpctl\b|\bpactl\b"
    # the fields a device is named in
    r"|\bnode\.name\b|\balsa_(?:input|output)\b|\bbluez_"
    r"|\binputDevice\b|\boutputDevice\b|\bdefault\.configured\.audio"
    # front-bounded: the names appear glued to a suffix
    # (easyeffects_sink, wireplumber.conf), where a closing \b never
    # matches and the whole rule would silently do nothing
    r"|\beasyeffects|\bwireplumber|\bpipewire"
    # the words a line naming a device uses
    r"|\bmicrophones?\b|\bmic\b|\bwebcam\b|\bheadsets?\b|\bheadphones?\b"
    r"|\bcoolers?\b|\bpump\b|\bgraphics card\b|\bgpu\b|\bkeyboard\b|\bmouse\b"
    r"|\bdevices?\b"
    # and the bar icons that stand in for a device where the word does
    # not appear at all - ICON_COOLER has no word boundary in front of
    # "COOLER", so the vocabulary above walks straight past it
    r"|\bICON_COOLER\b|\bICON_TEMP\b|\bICON_RGB\b|\bICON_GPU\b",
    re.I)

# XF86 is excluded by name: the X11 keysym namespace has this exact
# shape (XF86AudioMute), it appears beside `pactl` in every volume
# keybind, and it is a fact about X rather than about anybody's hardware.
PRODUCT_DESIGNATION = re.compile(
    r"\b(?!XF86)[A-Za-z]{1,4}[- ]?[0-9]{2,4}[A-Za-z][A-Za-z0-9]*\b"
    r"|\b[A-Z]{1,4}[- ]?[0-9]{3,4}\b")

# A place on one person's screen. Three shapes, because the coordinates
# reached Hyprland three ways: through its own pixel dispatchers, through
# a windowrule, and as a run of arguments to a shell function that passed
# them on. Sizes are deliberately NOT matched - `size 1200 800` on a
# dialog that is also `center on` is a default that fits any screen -
# and neither is `move 100%-820 40`, which is relative and therefore
# already right everywhere.
ABSOLUTE_PIXELS = re.compile(
    r"\bexact\s+-?\d{2,}\s+-?\d{2,}"
    r"|\bmove\s+-?\d{3,}\s+-?\d{3,}"
    r"|(?<![\w.%-])-?\d{3,}\s+-?\d{3,}\s+-?\d{3,}(?![\w.%])")

SCANNED_SUFFIXES = {".py", ".sh", ".template", ".conf", ".json", ".md"}


def _is_comment(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("#") or stripped.startswith("//")


def _shipped_files() -> list[Path]:
    """Every file under src/ that can carry a name to a user's machine.

    Asserts it found some. A selector that quietly reads nothing produces
    the same "clean" as one that read everything and found nothing, which
    is the failure mode every guard in this repository has had at least
    once.
    """
    files = [path for path in sorted(SRC.rglob("*"))
             if path.is_file() and path.suffix in SCANNED_SUFFIXES]
    assert len(files) > 50, (
        f"only {len(files)} files found under {SRC} - the scan is not "
        "reading the source tree, so its result means nothing")
    for required in ("templates/wireplumber-config.template",
                     "templates/easyeffects-config.template",
                     "templates/hardware-monitor-config.template",
                     "templates/zepos-terminals-config.template",
                     "audio.py", "monitors.py"):
        assert SRC / required in files, f"{required} is not read by this guard"
    return files


def _findings(line: str, *, code: bool = True) -> list[str]:
    """What is wrong with one line, named. Empty means nothing."""
    findings = []
    if DEVICE_STRING.search(line):
        findings.append("a device's own identity string")
    if DEVICE_CONTEXT.search(line) and PRODUCT_DESIGNATION.search(line):
        findings.append("a product designation on a line naming a device")
    # Coordinates on code lines only. A comment saying what the old code
    # did with 2357 is how the next reader learns why the arithmetic
    # changed, and a guard that fires on that is one somebody weakens.
    if code and not _is_comment(line) and ABSOLUTE_PIXELS.search(line):
        findings.append("an absolute pixel coordinate")
    return findings


def test_no_hardware_identity_or_desk_coordinate_remains():
    """The three findings, as rules rather than as a list of strings.

    WHAT THIS COVERS
      * ALSA node names built from a USB product string, Bluetooth
        addresses and USB vendor:product pairs, anywhere in src/.
      * Product designations on a line that is about a device - in code
        and in comments alike, because the origin's webcam and headphones
        were named in comments and nowhere else.
      * Absolute pixel positions on code lines.

    WHAT IT DOES NOT COVER, honestly
      * A product designation with no device vocabulary anywhere on its
        line. "WH-1000XM3" alone has the shape of a hex constant, and
        telling them apart needs a list of products - which is the kind
        of list this guard exists to avoid.
      * Device names that are ordinary words. A microphone sold under a
        name like "Meteor" cannot be distinguished from prose.
      * A desk encoded WITHOUT names or coordinates - three monitors
        assumed by count, an audio rule that assumes exactly one sink.
        No pattern sees that; the executed tests above are what cover it.
      * Anything outside src/. This is a shape rule and its own meta-test
        has to contain the shapes, so widening it to tests/ would make
        this file fail over itself - the same trade tests/src/
        test_inventory.py's shape rules make, and for the same reason.
    """
    offenders = []
    for path in _shipped_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            for finding in _findings(line):
                offenders.append(
                    f"{path.relative_to(SRC)}:{number}: {finding}")

    assert offenders == [], (
        "one desk's hardware is back in the tree: " + "; ".join(offenders[:15]))


def test_the_hardware_guard_would_catch_a_new_one():
    """The guard's own regression test.

    Every rule above is written to be precise, and precision tightened
    far enough stops catching anything - which is how a monitor-identity
    guard came to report this tree clean while two audio templates pinned
    four devices by USB id. So each rule is exercised against lines it
    must catch and lines it must leave alone, and the second half is what
    keeps this from being made to pass by widening the patterns until
    they match everything.

    Every device name below is INVENTED and has the shape of the real
    ones. Putting the real strings here to prove the rule would leave
    this file carrying exactly what the rule exists to remove.
    """
    def offends(line: str) -> bool:
        return bool(_findings(line))

    caught = [
        # The shape an ALSA node name built from a USB product string
        # has - a headset, and a webcam pinned by vendor:product:serial.
        '      { node.name = "alsa_input.usb-Probe_Probe_Headset-00.mono-fallback" }',
        '      { node.name = "alsa_input.usb-1234_abcd_ZZ001122-02.mono-fallback" }',
        # A Bluetooth address, in the two separators bluez uses.
        "outputDevice=bluez_output.11:22:33:44:55:66",
        "outputDevice=bluez_output.11_22_33_44_55_66",
        # Product designations, in code and in a comment, on lines whose
        # only clue is the kind of device they are about.
        "# Prevent the Probe Nine mic and the Webcam Q310 mic from auto-routing",
        "# OUTPUT: Apps -> easyeffects_sink -> QQ-1000XM9",
        'tooltip_lines.append(f"\\n{ICON_COOLER} Probe H150i:")',
        'tooltip_lines.append(f"\\n{ICON_TEMP} QTX 3080 12GB:")',
        'Monitors: Probe H150i, some GPU, System Sensors, OpenRGB',
        '    """Get the Probe H150i status via liquidctl"""',
        "# RGB: 300s TTL - device list is static; avoids usbfs spam on H150i",
        # One desk's coordinates, in the three shapes they reached
        # Hyprland by.
        '    position_window "ZepOS: Main" 3 2357 1164 1433 482',
        'hyprctl dispatch movewindowpixel "exact 2357 1164,address:$addr"',
        "windowrule = match:class ^(kitty)$, float on, move 2357 1164",
    ]
    for line in caught:
        assert offends(line), f"the guard would miss: {line}"

    left_alone = [
        # The X11 keysym namespace, which has a designation's exact shape
        # and sits beside `pactl` in every volume keybind there is.
        "bind = , XF86AudioRaiseVolume, exec, pactl set-sink-volume @DEFAULT_SINK@ +5%",
        "bind = , XF86AudioMicMute, exec, pactl set-source-mute @DEFAULT_SOURCE@ toggle",
        # A default size for a dialog that is also centred: it fits any
        # screen, and it is not a position.
        "windowrule = match:class ^(floating-center)$, float on, center on, size 1200 800",
        # A position expressed relative to the screen, which is right
        # everywhere by construction.
        "windowrule = match:class ^(status)$, float on, size 800 600, move 100%-820 40",
        # Reading the device's identity generically is the FIX, not the
        # bug - in all three of the places it now happens.
        "output = run_command(['liquidctl', 'status'])",
        "    '--query-gpu=temperature.gpu,utilization.gpu,memory.used,name',",
        "# the node name is the second column of `pactl list short sources`",
        'hyprctl dispatch movewindowpixel "exact $x $y,address:$addr" >/dev/null',
        "local width=$(( screen_w * width_percent / 100 ))",
        # The virtual node EasyEffects publishes: software, not hardware,
        # and the same on every machine.
        '  default.configured.audio.sink = "easyeffects_sink"',
        # Constants and codepoints that have a designation's shape and
        # nothing to do with a device.
        "map U+F43A JetBrainsMono Nerd Font",
        'STYLE_COLOR_1920 = "#1e1e2e"',
        "CACHE_TTL_SLOW = 300  # seconds - the rgb device list rarely changes",
        # A documentation-range address on a line about a network device.
        "default via 203.0.113.1 dev eth0 metric 600",
        # A comment recording what the old code did with a number, which
        # is how the next reader learns why the arithmetic changed.
        "#     position_window ... 3 2357 1164 1433 482 - one desk's pixels",
    ]
    for line in left_alone:
        assert not offends(line), f"the guard cries wolf over: {line}"
