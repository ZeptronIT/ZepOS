# SPDX-License-Identifier: GPL-3.0-or-later
"""The three commands, and the failures they are there to make audible.

WHY THESE TESTS RUN THE COMMANDS
    The commands are installed to /usr/bin while the modules they need
    stay in /usr/share/zepos, so "does it import" is a question about a
    directory layout, not about a function. It can only be answered by
    starting the command - from a checkout, where the modules sit one
    directory above it, and from a copy laid out the way the package
    lays it out, where they do not.

    Every child runs under `env -i` with the stub directory as the ONLY
    entry on PATH, so a command reaching for something no stub provides
    fails with "command not found" instead of running the real `ip`,
    `hyprctl` or `hyprpm` against the machine running the tests. HOME and
    XDG_CONFIG_HOME both point inside tmp_path, because the doctor reads
    the live hyprland.conf and zepos-settings writes the settings file -
    the isolation guard cannot see into a subprocess, so the redirection
    has to be right here.
"""
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

# The shared backstop, from tests/conftest.py: a command the stub
# directory does not provide has to be a failure, not an empty string.
import conftest

# Anchored on this file, the way every other test in this directory does
# it. As a relative path this resolves against wherever pytest was
# started - tests/src/test_inventory.py records what that cost: rglob
# over a directory that was not there found nothing, and every guard
# reported clean without reading a file.
SRC = Path(__file__).resolve().parents[2] / "src"


def settings_schema_version() -> int:
    """Die Fassung, die settings.py fuehrt - nicht eine getippte Zahl.

    Hier stand zweimal `== 1`. Als die Fassung am 22.08.2026 auf 2 stieg
    (der VPN-Abschnitt traegt seither eine Liste), meldeten beide Tests
    einen Fehler an einer Stelle, an der nichts kaputt war - und der
    naechste Anstieg haette dasselbe noch einmal getan.
    """
    from src.settings import SCHEMA_VERSION
    return SCHEMA_VERSION
BIN = SRC / "bin"
COMMANDS = ("zepos-generate", "zepos-settings", "zepos-doctor", "zepos-update")

# Named absolutely, so finding either one never depends on PATH.
ENV = "/usr/bin/env"

# What `hyprctl version -j` answers, reduced to the fields the ABI check
# reads. The version pairs are the granularity Hyprland's own plugin ABI
# hash uses: it carries major.minor of each library
# (..._aq_0.12_hu_0.13_hg_0.5_hc_0.1_hlg_0.6), so a patch difference is
# not a mismatch and a minor difference is.
MATCHING_VERSION = {
    "tag": "v0.55.4",
    "buildAquamarine": "0.12.0", "systemAquamarine": "0.12.1",
    "buildHyprlang": "0.6.8", "systemHyprlang": "0.6.8",
    "buildHyprutils": "0.13.1", "systemHyprutils": "0.13.1",
    "buildHyprcursor": "0.1.13", "systemHyprcursor": "0.1.13",
    "buildHyprgraphics": "0.5.1", "systemHyprgraphics": "0.5.1",
}
MISMATCHED_VERSION = dict(MATCHING_VERSION, systemAquamarine="0.13.1")


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.syspath_prepend(str(SRC))
    import cli as module

    return module


@pytest.fixture
def doctor(monkeypatch):
    monkeypatch.syspath_prepend(str(SRC))
    import doctor as module

    return module


def completed(stdout: str = "", returncode: int = 0):
    """A stand-in for subprocess.run's result.

    The isolation guard blocks real processes and is right to: no unit
    test has any business running `ip` or `hyprctl` against the machine
    it is running on.
    """

    def run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, returncode, stdout, "")

    return run


# --------------------------------------------------------------------
# running a command for real
# --------------------------------------------------------------------

def stub_dir(tmp_path: Path, **stubs: str) -> Path:
    """A directory of bash stubs, and a python3 that is the interpreter
    running the tests.

    python3 has to be here because the commands start through
    `#!/usr/bin/env python3`: with the stub directory as the whole of
    PATH, that lookup finds this and nothing else.
    """
    directory = tmp_path / "stubs"
    directory.mkdir(exist_ok=True)
    stubs.setdefault("python3", f'exec "{sys.executable}" "$@"\n')
    # Der Doktor fragt systemd, ob der Aktualisierungs-Zeitgeber
    # eingeschaltet ist. Ein Stub und nicht das echte systemctl:
    # conftest.NEVER_PASSTHROUGH verbietet den Durchgriff, und die
    # Antwort "es gibt die Einheit hier nicht" ist genau die, die eine
    # Maschine ohne installiertes ZepOS gibt.
    # Wortlaut und Kanal wie beim echten systemctl fuer eine Einheit, die
    # es nicht gibt: nichts auf stdout, die Erklaerung auf stderr, 1.
    stubs.setdefault(
        "systemctl",
        'printf "Failed to get unit file state for %s: '
        'No such file or directory\\n" "$2" >&2\nexit 1\n')
    for name, body in stubs.items():
        stub = directory / name
        stub.write_text("#!/bin/bash\n" + body, encoding="utf-8")
        stub.chmod(0o755)
    return directory


def child_path(stubs: Path) -> str:
    """The PATH the child gets - the stub directory and nothing else.

    Asserted rather than trusted, because this is the whole safety
    argument: with no other directory on PATH, a command this test forgot
    to stub cannot reach the real one.
    """
    path = str(stubs)
    assert path.split(os.pathsep) == [str(stubs)]
    assert not os.environ.get("PATH", "").startswith(path)
    return path


def run_command(command: Path, *arguments: str, stubs: Path, home: Path,
                system_root: Path | None = None):
    home.mkdir(parents=True, exist_ok=True)
    (home / ".config").mkdir(parents=True, exist_ok=True)
    environment = {
        "PATH": child_path(stubs),
        "HOME": str(home),
        # Both, deliberately: output_root() reads XDG_CONFIG_HOME and
        # falls back to Path.home(), which with an unset HOME resolves
        # through the password database to the DEVELOPER's home.
        "XDG_CONFIG_HOME": str(home / ".config"),
    }
    if system_root is not None:
        environment["ZEPOS_SYSTEM_ROOT"] = str(system_root)
    return subprocess.run(
        [ENV, "-i", *(f"{k}={v}" for k, v in environment.items()),
         str(command), *arguments],
        env={}, input="", capture_output=True, text=True, timeout=120,
    )


def assert_ran(result) -> str:
    conftest.assert_no_missing_command(result, "the command")
    assert "Traceback" not in result.stderr, result.stderr
    return result.stdout + result.stderr


def installed_layout(tmp_path: Path) -> tuple[Path, Path]:
    """The package's own split: modules below usr/share/zepos, commands
    in usr/bin, with nothing but PATH connecting the two.

    This is the layout in which a command CANNOT find its modules by
    looking next to itself, which is what makes it worth testing.
    """
    share = tmp_path / "usr" / "share" / "zepos"
    share.mkdir(parents=True)
    for path in sorted(SRC.iterdir()):
        if path.is_file():
            shutil.copy2(path, share / path.name)

    binaries = tmp_path / "usr" / "bin"
    binaries.mkdir(parents=True)
    for name in COMMANDS:
        shutil.copy2(BIN / name, binaries / name)
    return share, binaries


# --------------------------------------------------------------------
# how the three commands find the rest of ZepOS
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_each_command_starts_from_a_checkout_without_being_told_anything(tmp_path):
    """No environment variable, no working directory, no PATH entry.

    A developer runs src/bin/zepos-settings straight out of the tree. If
    that only worked with ZEPOS_SYSTEM_ROOT exported, the variable would
    end up in someone's shell profile permanently - and paths.py's own
    header explains what that costs: every template lookup then misses,
    silently, against a directory nothing has written to.
    """
    stubs = stub_dir(tmp_path)
    result = run_command(BIN / "zepos-settings", "get",
                         stubs=stubs, home=tmp_path / "home")

    assert_ran(result)
    assert result.returncode == 0, result.stderr
    assert (json.loads(result.stdout)["schema_version"]
            == settings_schema_version())


@pytest.mark.allow_subprocess
def test_each_command_finds_the_modules_where_the_package_puts_them(tmp_path):
    """/usr/bin/zepos-doctor with the code in /usr/share/zepos.

    Looking next to itself finds /usr/lib and /usr/share/man there, so
    the system root has to answer. All three are run, because a rule that
    holds in one of them and not the others is worth nothing.
    """
    share, binaries = installed_layout(tmp_path)
    stubs = stub_dir(tmp_path)

    result = run_command(binaries / "zepos-settings", "get",
                         stubs=stubs, home=tmp_path / "home", system_root=share)
    assert_ran(result)
    assert (json.loads(result.stdout)["schema_version"]
            == settings_schema_version())

    result = run_command(binaries / "zepos-doctor",
                         stubs=stubs, home=tmp_path / "home", system_root=share)
    assert_ran(result)

    result = run_command(binaries / "zepos-generate", "--monitors",
                         stubs=stub_dir(tmp_path, hyprctl='printf "[]\\n"\n'),
                         home=tmp_path / "home", system_root=share)
    assert_ran(result)


@pytest.mark.allow_subprocess
def test_a_command_that_cannot_find_its_modules_says_where_it_looked(tmp_path):
    """The one failure that must not be a traceback.

    A half-installed package - commands in place, /usr/share/zepos not -
    is a plausible state, and "ModuleNotFoundError: No module named
    'cli'" tells the user nothing about which directory is missing.
    """
    if Path("/usr/share/zepos").is_dir():
        pytest.skip("this machine has a real /usr/share/zepos, so the "
                    "installed default resolves and there is nothing to report")

    _, binaries = installed_layout(tmp_path)
    stubs = stub_dir(tmp_path)

    result = run_command(binaries / "zepos-doctor",
                         stubs=stubs, home=tmp_path / "home")

    assert result.returncode != 0
    assert "/usr/share/zepos" in result.stderr, result.stderr
    assert "ZEPOS_SYSTEM_ROOT" in result.stderr, result.stderr


# --------------------------------------------------------------------
# zepos-generate
# --------------------------------------------------------------------

def test_generate_hands_its_arguments_to_the_generator(cli):
    """The staged generation lives in generate_config.sh and is not
    reimplemented here - the command exists so /usr/bin has an entry
    point, not so there is a second generator."""
    seen = []

    def runner(argv, **kwargs):
        seen.append(list(argv))
        return subprocess.CompletedProcess(argv, 0)

    assert cli.generate(["-ags-bar", "-kitty-config"], runner=runner) == 0
    assert seen, "the generator was never called"
    assert seen[0][-2:] == ["-ags-bar", "-kitty-config"]
    assert seen[0][1].endswith("generate_config.sh")


def test_generate_asks_the_generator_for_the_list_of_targets(cli):
    """--help is the generator's own usage, which lists the templates
    that are actually on this machine. A list written here would go out
    of date the first time somebody adds one."""
    seen = []

    def runner(argv, **kwargs):
        seen.append(list(argv))
        return subprocess.CompletedProcess(argv, 0)

    assert cli.generate(["--help"], runner=runner) == 0
    assert seen[0][2:] == [], seen


def test_generate_reports_the_generator_s_own_exit_status(cli):
    """A failed generation must not look like a successful one: the shell
    that called it decides on this number whether to fall back."""
    assert cli.generate([], runner=lambda argv, **kw:
                        subprocess.CompletedProcess(argv, 3)) == 3


def test_generate_monitors_writes_the_layout_the_module_derives(cli, monkeypatch,
                                                                capsys):
    """--monitors is what hypr-monitor-detect.sh redirects into the file
    Hyprland sources, so it writes the assignments and nothing else."""
    monkeypatch.syspath_prepend(str(SRC))
    import monitors

    detected = [
        monitors.Monitor(name="DP-1", description="Screen Co Model X 1111",
                         x=0, width=2560, height=1440, refresh=60.0, scale=1.0,
                         transform=0),
    ]
    monkeypatch.setattr(monitors, "detect", lambda **kwargs: detected)

    assert cli.generate(["--monitors"]) == 0
    written = capsys.readouterr().out
    assert "workspace=1,monitor:" in written, written


def test_generate_monitors_writes_nothing_when_detection_fails(cli, monkeypatch,
                                                               capsys):
    """The caller appends this to a half-written config file. A failure
    that still printed half a block would leave that file broken."""
    monkeypatch.syspath_prepend(str(SRC))
    import monitors

    def refuse(**kwargs):
        raise RuntimeError("no compositor")

    monkeypatch.setattr(monitors, "detect", refuse)

    assert cli.generate(["--monitors"]) != 0
    assert capsys.readouterr().out == ""


# Commands that act on the RUNNING desktop session rather than on a
# file. generate_config.sh reaches for these after a generation, and HOME
# cannot redirect any of them: `pkill -f "gjs.*ags"` finds the
# developer's own shell whatever HOME says. The list is the one
# tests/src/test_generate.py arrived at after an intermediate state of
# that task killed the AGS session of the machine running the tests.
#
# Imported rather than copied out. Two hand-kept copies of a safety list
# drift, and these two had: both were missing `hyprctl`, which the
# generator reaches through bar-workspace-detect.sh and monitors.py.
# test_generate.py now derives its list from the generator's own source,
# and taking it from there is what puts this file behind that derivation
# instead of behind a second transcription of it.
from tests.src.test_generate import SESSION_COMMANDS


@pytest.mark.allow_subprocess
def test_generate_produces_configuration_through_the_real_generator(tmp_path):
    """The whole chain, once: command, module resolution, generator,
    staging, validation, publication.

    The generator needs a real PATH - python3, jq, mktemp, date - so the
    stub directory is PREPENDED here rather than being the whole of it,
    and every command that would touch the running session is a no-op in
    front of it. `shutil.which` is asked BEFORE anything starts, because
    "this run cannot reach that code path" is an argument, not a
    guarantee.
    """
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True)
    (home / ".cache").mkdir()

    stubs = tmp_path / "session-stubs"
    stubs.mkdir()
    for name in SESSION_COMMANDS:
        body = ('printf "org.freedesktop.Notifications\\n"\n'
                if name == "dbus-send" else "")
        stub = stubs / name
        stub.write_text(f'#!/bin/bash\necho "stub: {name} $*" >&2\n{body}exit 0\n',
                        encoding="utf-8")
        stub.chmod(0o755)
    path = os.pathsep.join([str(stubs), os.environ["PATH"]])
    for name in SESSION_COMMANDS:
        assert shutil.which(name, path=path) == str(stubs / name), (
            f"{name} would reach the real command")

    result = subprocess.run(
        [str(BIN / "zepos-generate"), "-kitty-config"],
        env={"PATH": path, "HOME": str(home),
             "XDG_CONFIG_HOME": str(home / ".config"),
             "XDG_CACHE_HOME": str(home / ".cache")},
        capture_output=True, text=True, timeout=300,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (home / ".config" / "kitty" / "kitty.conf").is_file(), (
        result.stdout + result.stderr)


# --------------------------------------------------------------------
# zepos-settings
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_settings_writes_what_it_reads_back(tmp_path):
    stubs = stub_dir(tmp_path)
    home = tmp_path / "home"

    written = run_command(BIN / "zepos-settings", "set", "weather.location",
                          "Bremen", stubs=stubs, home=home)
    assert_ran(written)
    assert written.returncode == 0, written.stderr

    read = run_command(BIN / "zepos-settings", "get", "weather.location",
                       stubs=stubs, home=home)
    assert_ran(read)
    assert read.stdout.strip() == "Bremen"


@pytest.mark.allow_subprocess
def test_settings_keeps_the_file_unreadable_to_other_users(tmp_path):
    """It may hold a VPN pre-shared key. settings.save() is what
    guarantees that, which is the reason this command does not write the
    file itself."""
    home = tmp_path / "home"
    result = run_command(BIN / "zepos-settings", "set", "weather.location",
                         "Bremen", stubs=stub_dir(tmp_path), home=home)
    assert_ran(result)

    path = home / ".config" / "zepos" / "user-settings.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.allow_subprocess
def test_settings_refuses_a_key_the_schema_does_not_have(tmp_path):
    """A typo that is accepted and then ignored by everything is the
    quietest possible failure: the user changed a setting, the command
    said nothing, and nothing happened."""
    home = tmp_path / "home"
    result = run_command(BIN / "zepos-settings", "set", "wether.location",
                         "Bremen", stubs=stub_dir(tmp_path), home=home)

    assert_ran(result)
    assert result.returncode != 0
    assert "wether.location" in result.stdout + result.stderr
    assert not (home / ".config" / "zepos" / "user-settings.json").exists()


@pytest.mark.allow_subprocess
@pytest.mark.parametrize("command,argument", [
    ("zepos-settings", "--help"), ("zepos-doctor", "--help"),
])
def test_asking_for_help_is_not_an_error(tmp_path, command, argument):
    """A usage message on stderr with a non-zero status is what a user
    gets for a MISTAKE. Typing --help is not one, and the answer has to
    be on stdout or piping it into a pager shows nothing."""
    result = run_command(BIN / command, argument, stubs=stub_dir(tmp_path),
                         home=tmp_path / "home")

    assert_ran(result)
    assert result.returncode == 0, result.stderr
    assert command in result.stdout, result.stdout
    assert result.stderr == ""


def test_settings_reads_and_writes_through_the_versioned_module(cli, tmp_path,
                                                                monkeypatch):
    """Not through user_settings.py, and not through a third writer of
    its own. The file carries a schema version because a later migration
    cannot guess what shape a stranger's file has.

    DIE FUNDSTELLE HAT SICH AM 01.09.2026 VERSCHOBEN, DIE ZUSICHERUNG NICHT
        Nachgesehen wird jetzt in `vpn.connection(...)` statt in
        `...["vpn"][...]`. Das ist keine aufgeweichte Zusicherung,
        sondern eine strengere an der richtigen Stelle - und der Grund
        dafuer ist der Fehler, den dieser Test bis dahin NICHT sah.

        GEMESSEN am 01.09.2026 am Stand vor der Behebung, frisches
        ZEPOS_USER_ROOT ohne Einstellungsdatei:

            set vpn.server gw.example.org            -> 0
            get vpn.server                           -> gw.example.org
            Datei: {"active": "", "connections": [],
                    "server": "gw.example.org"}
            vpn.connection(settings.load())          -> {}
            user_settings.get_vpn_setting("server")  -> ""

        Der Abschnitt `vpn` ist seit dem 22.08.2026 keine Verbindung
        mehr, sondern eine LISTE von Verbindungen. Ein Wert, der als
        Geschwister von `active` und `connections` darin liegt, gehoert
        zu keiner - gelesen hat ihn danach niemand ausser der
        Befehlszeile selbst. `...["vpn"]["connection_name"]` war also
        genau der Griff, mit dem der Schreibfehler unsichtbar blieb: er
        fand den verlegten Wert dort, wo er lag, und nicht dort, wo ihn
        jemand braucht.

        Der Test misst darum bis zum LESER. Und er verlangt zusaetzlich,
        was er vorher nicht verlangte: dass die Verbindung eine Kennung
        traegt und `active` auf sie zeigt. Ohne beides faende der
        Schalter sie beim naechsten Lesen nicht wieder - ein
        Wiederfinden, das vpn.connection() zwar auch ohne `active`
        vortaeuscht, weil es bei fehlender Kennung die ERSTE Verbindung
        antwortet.
    """
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    monkeypatch.syspath_prepend(str(SRC))
    import settings
    import vpn

    assert cli.settings_command(["set", "vpn.connection_name", "office"]) == 0

    dokument = settings.load()
    gewaehlt = vpn.connection(dokument)
    assert gewaehlt["connection_name"] == "office"
    assert gewaehlt.get("id")
    assert dokument["vpn"]["active"] == gewaehlt["id"]


def test_settings_keeps_the_keys_it_does_not_know_about(cli, tmp_path,
                                                        monkeypatch):
    """The installer writes plugins.enabled into the same file, and the
    style layer keeps widget sizes and colours there. A command that
    wrote only its own keys back would delete all of it."""
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    monkeypatch.syspath_prepend(str(SRC))
    import settings

    document = settings.defaults()
    document["plugins"] = {"enabled": True}
    document["colors"] = {"success": "#a6e3a1"}
    settings.save(document)

    assert cli.settings_command(["set", "weather.location", "Bremen"]) == 0

    after = settings.load()
    assert after["plugins"] == {"enabled": True}
    assert after["colors"] == {"success": "#a6e3a1"}
    assert after["weather"]["location"] == "Bremen"


def test_settings_can_configure_what_a_fresh_installation_left_out(cli, tmp_path,
                                                                   monkeypatch):
    """The installer writes only the two questions it asked - plugins and
    the weather location - so a just-installed machine has no vpn section
    at all. Refusing vpn.server there would refuse it on exactly the
    machines where it has to be set before anything works.

    DIE FUNDSTELLE HAT SICH AM 01.09.2026 VERSCHOBEN, DIE ZUSICHERUNG NICHT
        Was dieser Test zusichert, bleibt Wort fuer Wort dasselbe: auf
        einer frisch installierten Maschine ohne VPN-Abschnitt muss
        `set vpn.server` durchgehen. Nur der Ort, an dem er nachsieht,
        ist ein anderer - `vpn.connection(...)` statt `...["vpn"][...]`.

        Der Grund ist, dass "durchgehen" hier bis dahin zu wenig hiess.
        GEMESSEN am 01.09.2026 am Stand vor der Behebung, genau in der
        Lage, die dieser Test aufbaut:

            set vpn.server gw.example.org            -> 0
            get vpn.server                           -> gw.example.org
            Datei: {"active": "", "connections": [],
                    "server": "gw.example.org"}
            vpn.connection(settings.load())          -> {}
            user_settings.get_vpn_setting("server")  -> ""

        Der Befehl gab 0 zurueck, dieser Test war gruen - und der
        Erzeuger, das Verbindungsskript und das Einstellungsfenster
        sahen einen leeren Server. Genau auf den Maschinen also, fuer
        die der Test geschrieben wurde, war "es geht durch" nichts
        wert. Der Rueckfall auf default_connection() liess die PRUEFUNG
        des Pfades durch und leitete den SCHREIBWEG nicht mit um; der
        Wert landete als Geschwister von `active` und `connections` im
        Abschnitt, und der ist seit dem 22.08.2026 eine Liste von
        Verbindungen und keine Verbindung mehr.

        Zusaetzlich verlangt wird jetzt, dass die angelegte Verbindung
        eine Kennung traegt und `active` auf sie zeigt - sonst waere der
        Griff nur verschoben und nicht verschaerft: vpn.connection()
        antwortet auch ohne passende `active` die erste Verbindung der
        Liste und saehe damit ueber eine ungewaehlte hinweg.
    """
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    monkeypatch.syspath_prepend(str(SRC))
    import settings
    import vpn

    (tmp_path / "user-settings.json").write_text(json.dumps({
        "schema_version": settings.SCHEMA_VERSION,
        "plugins": {"enabled": True},
        "weather": {"location": ""},
    }), encoding="utf-8")

    assert cli.settings_command(["set", "vpn.server", "vpn.example.org"]) == 0

    dokument = settings.load()
    gewaehlt = vpn.connection(dokument)
    assert gewaehlt["server"] == "vpn.example.org"
    assert gewaehlt.get("id")
    assert dokument["vpn"]["active"] == gewaehlt["id"]
    assert dokument["plugins"] == {"enabled": True}


def _zwei_verbindungen(settings, gewaehlt: str) -> dict:
    """Eine Einstellungsdatei mit zwei VPN-Verbindungen.

    Aus settings.default_connection() gebaut und nicht getippt - dieselbe
    Begruendung wie ueberall in diesem Baum: eine abgeschriebene
    Verbindung waere die zweite Fassung der Feldnamen, und sie waere die,
    die veraltet.
    """
    dokument = settings.defaults()
    zuhause = dict(settings.default_connection())
    zuhause.update({"id": "c1", "connection_name": "home",
                    "server": "heim.example.net"})
    arbeit = dict(settings.default_connection())
    arbeit.update({"id": "c2", "connection_name": "work",
                   "server": "arbeit.example.net"})
    dokument["vpn"] = {"active": gewaehlt, "connections": [zuhause, arbeit]}
    return dokument


def test_get_findet_wieder_was_set_geschrieben_hat(cli, tmp_path, monkeypatch,
                                                   capsys):
    """GEMELDET am 22.08.2026 bei der Durchsicht vor 0.1.11.

    `vpn` traegt seit dem Umbau eine Liste, und `vpn.server` zeigt auf
    die GEWAEHLTE Verbindung darin - so steht es im Absatz ueber
    _vpn_target() in src/cli.py, und dort steht auch, das sei "dieselbe
    Auskunft, die get_vpn_setting() und der Erzeuger geben".

    Fuer `set` stimmte es. Die Umleitung stand aber NUR in _set():

        set vpn.server vpn.example.org   -> geschrieben, Rueckgabe 0
        get vpn.server                   -> "no such setting: vpn.server"

    Ein Programm, das seinen eigenen Wert nicht wiederfindet. Kein Test
    deckte es, weil es zu `get vpn.*` ueberhaupt keinen gab - deshalb
    steht dieser hier.

    Er misst BEIDE Richtungen an derselben Datei: erst lesen, was
    dasteht, dann schreiben, dann wieder lesen. Ein Test, der nur nach
    dem Schreiben liest, waere auch mit zwei Umleitungen gruen, die sich
    beide gleich irren.
    """
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    monkeypatch.syspath_prepend(str(SRC))
    import settings

    settings.save(_zwei_verbindungen(settings, gewaehlt="c2"))

    # GELESEN WIRD DIE GEWAEHLTE UND NICHT DIE ERSTE. Die zweite steht
    # auf `active`, also muss ihr Server herauskommen - stuende hier die
    # erste, waere jede Zusicherung darunter auch mit einer Umleitung
    # gruen, die `active` gar nicht liest.
    assert cli.settings_command(["get", "vpn.server"]) == 0
    assert capsys.readouterr().out.strip() == "arbeit.example.net"

    assert cli.settings_command(["set", "vpn.server", "vpn.example.org"]) == 0

    assert cli.settings_command(["get", "vpn.server"]) == 0
    assert capsys.readouterr().out.strip() == "vpn.example.org"

    # Und die andere Verbindung ist unberuehrt geblieben: eine Umleitung,
    # die auf die falsche Zeile zeigt, faellt sonst nirgends auf.
    assert settings.load()["vpn"]["connections"][0]["server"] == "heim.example.net"


def test_get_liest_die_zwei_schluessel_des_abschnitts_weiter_unverlegt(
        cli, tmp_path, monkeypatch, capsys):
    """`vpn.active` und `vpn.connections` gehoeren dem ABSCHNITT und
    nicht einer Verbindung.

    Sie stehen deshalb in VPN_SECTION_KEYS und duerfen von der Umleitung
    nicht angefasst werden - `vpn.active` ist der Weg, die gewaehlte
    Verbindung von der Befehlszeile aus zu wechseln, und eine Umleitung
    darauf zeigte auf `vpn.connections.<i>.active`, was es nicht gibt.
    """
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    monkeypatch.syspath_prepend(str(SRC))
    import settings

    settings.save(_zwei_verbindungen(settings, gewaehlt="c2"))

    assert cli.settings_command(["get", "vpn.active"]) == 0
    assert capsys.readouterr().out.strip() == "c2"

    assert cli.settings_command(["get", "vpn.connections"]) == 0
    gelesen = json.loads(capsys.readouterr().out)
    assert [eintrag["id"] for eintrag in gelesen] == ["c1", "c2"]

    # Der Weg mit der Ziffer, den die Umleitung selbst benutzt, muss
    # auch von Hand gehen - sonst waere die Umleitung ein Pfad, den das
    # Programm erzeugt und nicht lesen kann.
    assert cli.settings_command(["get", "vpn.connections.0.server"]) == 0
    assert capsys.readouterr().out.strip() == "heim.example.net"


def test_get_sagt_weiter_nein_zu_einem_pfad_den_es_nicht_gibt(
        cli, tmp_path, monkeypatch, capsys):
    """Die Gegenprobe zur Umleitung: sie darf nicht alles durchlassen.

    Eine Umleitung, die jeden `vpn.*`-Pfad auf die gewaehlte Verbindung
    schickt, sagte zu einem Tippfehler nicht mehr nein - sie liefe in
    die Verbindung hinein und fande dort nichts, oder schlimmer, sie
    fande zufaellig etwas.
    """
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    monkeypatch.syspath_prepend(str(SRC))
    import settings

    settings.save(_zwei_verbindungen(settings, gewaehlt="c2"))

    assert cli.settings_command(["get", "vpn.serverr"]) == 1
    assert "no such setting: vpn.serverr" in capsys.readouterr().err

    assert cli.settings_command(["get", "vpn.connections.9.server"]) == 1
    assert "no such setting" in capsys.readouterr().err


def test_settings_says_what_is_wrong_with_a_file_it_cannot_read(cli, tmp_path,
                                                               monkeypatch,
                                                               capsys):
    """A file from before the versioning, or one written by a tool that
    does not carry the version. Refusing is correct - guessing its shape
    is not - but the refusal has to name the file and the fix, and it
    must not overwrite what it could not read."""
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    monkeypatch.syspath_prepend(str(SRC))

    path = tmp_path / "user-settings.json"
    original = json.dumps({"colors": {"success": "#a6e3a1"}})
    path.write_text(original, encoding="utf-8")

    assert cli.settings_command(["set", "weather.location", "Bremen"]) != 0
    printed = capsys.readouterr()
    assert "schema_version" in printed.out + printed.err
    assert str(path) in printed.out + printed.err
    assert path.read_text(encoding="utf-8") == original, (
        "the settings it could not read were overwritten anyway")


# --------------------------------------------------------------------
# the two settings modules that share one file
# --------------------------------------------------------------------

def test_a_file_the_style_settings_wrote_can_still_be_read(tmp_path, monkeypatch):
    """user_settings.py and settings.py write the SAME file.

    The style layer's CLI (set-color, set-widget-size, the AGS dialogs)
    creates it from its own defaults, which carried no schema_version -
    so a machine whose settings file was created that way had every
    versioned reader refuse it, including zepos-settings. One file, two
    writers, and only one of them stating the version is not a
    disagreement anybody could see.
    """
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    monkeypatch.syspath_prepend(str(SRC))
    import settings
    import user_settings

    user_settings.save_settings(settings=user_settings.get_defaults())

    assert settings.load()["schema_version"] == settings.SCHEMA_VERSION


# --------------------------------------------------------------------
# zepos-doctor: a VPN that swallows the private address space
# --------------------------------------------------------------------

def test_a_tunnel_that_covers_a_bridge_names_the_bridge(doctor):
    """Routing all three RFC1918 ranges leaves no subnet for container
    and virtualisation bridges. That is not hypothetical: it is why this
    project's own build containers need --network host. The traffic
    disappears into the tunnel and nothing logs anything."""
    findings = doctor.check_vpn_networks(
        [doctor.Network("10.0.0.0/8", "wlan0"),
         doctor.Network("172.16.0.0/12", "wlan0"),
         doctor.Network("192.168.0.0/16", "wlan0")],
        bridges=[doctor.Network("10.222.0.0/24", "docker0")],
    )

    assert len(findings) == 1, findings
    assert "10.222.0.0/24" in str(findings[0])
    assert "docker0" in str(findings[0])
    assert "10.0.0.0/8" in str(findings[0])


def test_a_bridge_no_route_covers_is_not_reported(doctor):
    assert doctor.check_vpn_networks(
        [doctor.Network("10.0.0.0/8", "wlan0")],
        bridges=[doctor.Network("172.17.0.0/16", "docker0")],
    ) == []


def test_a_bridge_s_own_route_is_not_a_finding(doctor):
    """Every bridge has a route to its own network, on itself. Reading
    that as "the tunnel swallows the bridge" would report every machine
    with a bridge on it, which is how a check gets switched off."""
    assert doctor.check_vpn_networks(
        [doctor.Network("192.168.122.0/24", "virbr0")],
        bridges=[doctor.Network("192.168.122.0/24", "virbr0")],
    ) == []


def test_a_bridge_of_the_other_address_family_does_not_stop_the_doctor(doctor):
    """ip_network("fd00::/8").subnet_of(ip_network("10.0.0.0/8")) raises
    TypeError. A doctor that dies on an IPv6 bridge reports nothing at
    all, which is worse than the condition it was asked to look for."""
    findings = doctor.check_vpn_networks(
        [doctor.Network("10.0.0.0/8", "wlan0")],
        bridges=[doctor.Network("fd00:dead:beef::/48", "podman0"),
                 doctor.Network("10.88.0.0/16", "podman1")],
    )

    assert len(findings) == 1, findings
    assert "10.88.0.0/16" in str(findings[0])


def test_a_bridge_the_settings_keep_out_of_the_tunnel_is_not_reported(doctor):
    """bypass_networks exists exactly so a range covered by a routed
    network stays outside the tunnel. Reporting it would tell the user to
    fix something they already fixed."""
    assert doctor.check_vpn_networks(
        [doctor.Network("10.0.0.0/8", "wlan0")],
        bridges=[doctor.Network("10.222.0.0/24", "docker0")],
        bypassed=["10.222.0.0/24"],
    ) == []


def test_an_unparsable_network_does_not_stop_the_doctor(doctor):
    """routed_networks is a hand-edited list in a settings file."""
    findings = doctor.check_vpn_networks(
        [doctor.Network("not a network", ""),
         doctor.Network("10.0.0.0/8", "wlan0")],
        bridges=[doctor.Network("10.222.0.0/24", "docker0")],
    )

    assert len(findings) == 1, findings


def test_the_bridges_come_from_the_running_system(doctor):
    """A check applied to nothing reports nothing. The bridges are read
    from the machine, not passed in by a caller that does not exist."""
    payload = json.dumps([{
        "ifname": "virbr0",
        "addr_info": [{"family": "inet", "local": "192.168.122.1",
                       "prefixlen": 24}],
    }])

    found = doctor.discover_bridges(runner=completed(payload))

    assert found == [doctor.Network("192.168.122.0/24", "virbr0")]


def test_the_routes_come_from_the_running_system(doctor):
    # DIE FORM IST ECHT, DIE WERTE SIND ES NICHT (17.08.2026)
    #
    # Diese zwei Zeilen sind einem laufenden `ip -j route` abgelesen, und
    # daran haengt die Pruefung: eine Default-Route MIT Gateway, die
    # verworfen wird, und eine Netzroute OHNE, die bleibt. Was hier stand,
    # war die Gateway-Adresse eines bestimmten Heimrouters und der
    # vorhersagbare Schnittstellenname einer bestimmten WLAN-Karte -
    # zusammen die Anschrift eines Wohnzimmers. Genommen sind jetzt
    # 203.0.113.1 aus TEST-NET-3 (RFC 5737, fuer Dokumentation gedacht,
    # und dieselbe Adresse, mit der tests/src/test_network_watchdog.py
    # schon rechnet) und `wlan0`, der Name, den jeder hat.
    payload = json.dumps([
        {"dst": "default", "gateway": "203.0.113.1", "dev": "wlan0"},
        {"dst": "10.0.0.0/8", "dev": "wlan0"},
    ])

    found = doctor.discover_routes(runner=completed(payload))

    assert found == [doctor.Network("10.0.0.0/8", "wlan0")], found


def test_discovery_survives_a_machine_without_iproute2(doctor):
    def missing(argv, **kwargs):
        raise FileNotFoundError(argv[0])

    assert doctor.discover_bridges(runner=missing) == []
    assert doctor.discover_routes(runner=missing) == []


# --------------------------------------------------------------------
# zepos-doctor: plugins
# --------------------------------------------------------------------

def test_a_library_the_plugins_would_be_built_against_is_reported(doctor):
    """Hyprland refuses a plugin whose ABI hash differs from its own, and
    that hash carries the major.minor of every library. A plugin built on
    this machine is built against the SYSTEM libraries; when Hyprland was
    built against different ones, the plugin is refused - and the desktop
    starts anyway, so the only sign is a feature that is not there."""
    findings = doctor.check_plugin_abi(MISMATCHED_VERSION)

    assert len(findings) == 1, findings
    assert "0.12.0" in str(findings[0])
    assert "0.13.1" in str(findings[0])


def test_a_patch_level_difference_is_not_a_mismatch(doctor):
    """The ABI hash carries aq_0.12, not aq_0.12.0. Reporting 0.12.0
    against 0.12.1 would fire on a machine where every plugin loads."""
    assert doctor.check_plugin_abi(MATCHING_VERSION) == []


def test_no_compositor_means_no_plugin_findings(doctor):
    """zepos-doctor runs from a TTY too. Nothing can be said about the
    ABI of a compositor that is not running, and inventing a finding
    would be worse than saying nothing."""
    assert doctor.check_plugin_abi({}) == []

    def missing(argv, **kwargs):
        raise FileNotFoundError(argv[0])

    assert doctor.discover_hyprland_version(runner=missing) == {}


def test_a_plugin_object_the_configuration_names_but_cannot_load(doctor, tmp_path):
    conf = tmp_path / "hyprland.conf"
    conf.write_text("plugin = /nonexistent/foo.so\n", encoding="utf-8")

    findings = doctor.check_plugin_objects(conf)

    assert any("foo.so" in str(f) for f in findings), findings


def test_the_doctor_answers_only_the_plugin_shape_that_can_be_answered(doctor,
                                                                      tmp_path,
                                                                      monkeypatch):
    """The rule belongs to validate_output._plugin_findings and is used
    from there rather than written a second time: a bare name cannot be
    turned into a path at all, and a relative path would be measured
    against whatever directory the user happened to be standing in."""
    conf = tmp_path / "hyprland.conf"
    conf.write_text("plugin = hyprbars\nplugin = plugins/relative.so\n",
                    encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert doctor.check_plugin_objects(conf) == []


def test_a_configuration_that_is_not_there_is_not_a_plugin_problem(doctor,
                                                                  tmp_path):
    assert doctor.check_plugin_objects(tmp_path / "absent.conf") == []


# --------------------------------------------------------------------
# zepos-doctor: the catalogue
# --------------------------------------------------------------------

def _catalogue(tmp_path: Path, pot: str, po: str) -> tuple[Path, Path]:
    directory = tmp_path / "po"
    directory.mkdir(exist_ok=True)
    (directory / "zepos-installer.pot").write_text(pot, encoding="utf-8")
    (directory / "de.po").write_text(po, encoding="utf-8")
    return directory / "zepos-installer.pot", directory / "de.po"


def test_a_msgid_the_german_catalogue_has_no_entry_for_is_reported(doctor,
                                                                   tmp_path):
    """A German user then reads that one message in English, and nothing
    anywhere says a translation is missing."""
    pot, po = _catalogue(
        tmp_path,
        'msgid ""\nmsgstr ""\n\nmsgid "Installation failed."\nmsgstr ""\n',
        'msgid ""\nmsgstr ""\n',
    )

    findings = doctor.check_catalogue(pot, po)

    assert any("Installation failed." in str(f) for f in findings), findings


def test_an_entry_with_an_empty_translation_is_reported(doctor, tmp_path):
    pot, po = _catalogue(
        tmp_path,
        'msgid ""\nmsgstr ""\n\nmsgid "No disk was selected."\nmsgstr ""\n',
        'msgid ""\nmsgstr ""\n\nmsgid "No disk was selected."\nmsgstr ""\n',
    )

    findings = doctor.check_catalogue(pot, po)

    assert any("No disk was selected." in str(f) for f in findings), findings


def test_a_complete_catalogue_is_quiet(doctor, tmp_path):
    pot, po = _catalogue(
        tmp_path,
        'msgid ""\nmsgstr ""\n\nmsgid "No disk was selected."\nmsgstr ""\n',
        'msgid ""\nmsgstr ""\n\nmsgid "No disk was selected."\n'
        'msgstr "Es wurde keine Festplatte ausgewählt."\n',
    )

    assert doctor.check_catalogue(pot, po) == []


def test_the_shipped_german_catalogue_is_complete(doctor):
    """The doctor is pointed at this project's own catalogue, so a gap
    that shows up here is a gap a German user would meet."""
    root = SRC.parent
    findings = doctor.check_catalogue(root / "po" / "zepos-installer.pot",
                                      root / "po" / "de.po")

    assert findings == [], [str(f) for f in findings]


def test_a_catalogue_that_is_not_installed_is_not_a_finding(doctor, tmp_path):
    assert doctor.check_catalogue(tmp_path / "absent.pot",
                                  tmp_path / "absent.po") == []


# --------------------------------------------------------------------
# what a finding says
# --------------------------------------------------------------------

def test_every_finding_says_what_it_costs_and_what_to_do(doctor, tmp_path):
    """A diagnostic that only names a condition leaves the user to search
    for the fix themselves - which is barely better than the silence it
    replaced."""
    conf = tmp_path / "hyprland.conf"
    conf.write_text("plugin = /nonexistent/foo.so\n", encoding="utf-8")
    pot, po = _catalogue(
        tmp_path,
        'msgid ""\nmsgstr ""\n\nmsgid "Installation failed."\nmsgstr ""\n',
        'msgid ""\nmsgstr ""\n',
    )

    findings = [
        *doctor.check_vpn_networks([doctor.Network("10.0.0.0/8", "wlan0")],
                                   bridges=[doctor.Network("10.222.0.0/24",
                                                           "docker0")]),
        *doctor.check_plugin_abi(MISMATCHED_VERSION),
        *doctor.check_plugin_objects(conf),
        *doctor.check_catalogue(pot, po),
    ]

    assert len(findings) == 4, findings
    for finding in findings:
        assert finding.what.strip(), finding
        assert finding.costs.strip(), f"{finding.what}: no cost stated"
        assert finding.fix.strip(), f"{finding.what}: nothing to do about it"


# --------------------------------------------------------------------
# zepos-doctor, run
# --------------------------------------------------------------------

IP_STUB = """
if [ "$2" = "route" ] || [ "$3" = "route" ]; then
    printf '[{"dst":"10.0.0.0/8","dev":"wlan0"},{"dst":"10.222.0.0/24","dev":"docker0"}]\\n'
    exit 0
fi
printf '[{"ifname":"docker0","addr_info":[{"family":"inet","local":"10.222.0.1","prefixlen":24}]}]\\n'
exit 0
"""


@pytest.mark.allow_subprocess
def test_the_doctor_finds_the_swallowed_bridge_on_the_machine_it_runs_on(tmp_path):
    """The check, the discovery and main() in one run.

    A pure function nothing calls reports on nothing, which is the state
    this test exists to keep it out of.
    """
    result = run_command(BIN / "zepos-doctor",
                         stubs=stub_dir(tmp_path, ip=IP_STUB),
                         home=tmp_path / "home")

    output = assert_ran(result)
    assert result.returncode != 0
    assert "docker0" in output, output
    assert "10.0.0.0/8" in output, output
    assert "--network host" in output or "bypass_networks" in output, output


@pytest.mark.allow_subprocess
def test_the_doctor_reads_the_configuration_that_is_actually_in_place(tmp_path):
    """The live hyprland.conf, not a staged one: validate_output checks
    what is about to be written, the doctor checks what is there."""
    home = tmp_path / "home"
    hypr = home / ".config" / "hypr"
    hypr.mkdir(parents=True)
    (hypr / "hyprland.conf").write_text(
        "plugin = /nonexistent/foo.so\n", encoding="utf-8")

    result = run_command(BIN / "zepos-doctor", stubs=stub_dir(tmp_path),
                         home=home)

    output = assert_ran(result)
    assert result.returncode != 0
    assert "foo.so" in output, output


@pytest.mark.allow_subprocess
def test_the_doctor_reports_an_abi_mismatch_it_read_from_the_compositor(tmp_path):
    # printf, not a heredoc: `cat` is not in the stub directory, and its
    # absence would be swallowed - the doctor captures what it runs, so a
    # stub that failed would look exactly like a compositor that is not
    # running.
    payload = json.dumps(MISMATCHED_VERSION).replace("'", "'\\''")
    hyprctl = ('if [ "$1" = "version" ]; then\n'
               f"    printf '%s\\n' '{payload}'\n"
               "    exit 0\nfi\nexit 1\n")

    result = run_command(BIN / "zepos-doctor",
                         stubs=stub_dir(tmp_path, hyprctl=hyprctl),
                         home=tmp_path / "home")

    output = assert_ran(result)
    assert result.returncode != 0
    assert "0.13.1" in output, output


@pytest.mark.allow_subprocess
def test_the_doctor_reports_a_missing_catalogue_entry_where_it_is_installed(
        tmp_path):
    """The catalogue ships beside the modules, so the doctor looks for it
    below the system root."""
    share, binaries = installed_layout(tmp_path)
    _catalogue(share, 'msgid ""\nmsgstr ""\n\nmsgid "Installation failed."\n'
                      'msgstr ""\n', 'msgid ""\nmsgstr ""\n')

    result = run_command(binaries / "zepos-doctor", stubs=stub_dir(tmp_path),
                         home=tmp_path / "home", system_root=share)

    output = assert_ran(result)
    assert result.returncode != 0
    assert "Installation failed." in output, output


@pytest.mark.allow_subprocess
def test_a_healthy_machine_gets_a_clean_bill_and_a_zero_status(tmp_path):
    """Nothing to report has to be distinguishable from "did not run",
    both for the user and for whatever calls this in a script."""
    quiet_ip = ('if [ "$2" = "route" ] || [ "$3" = "route" ]; then\n'
                '    printf \'[{"dst":"192.168.1.0/24","dev":"wlan0"}]\\n\'\n'
                "    exit 0\nfi\n"
                'printf \'[{"ifname":"docker0","addr_info":'
                '[{"family":"inet","local":"172.17.0.1","prefixlen":16}]}]\\n\'\n'
                "exit 0\n")

    result = run_command(BIN / "zepos-doctor",
                         stubs=stub_dir(tmp_path, ip=quiet_ip),
                         home=tmp_path / "home")

    output = assert_ran(result)
    assert result.returncode == 0, output
    assert output.strip(), "a command that says nothing looks like one that failed"


@pytest.mark.allow_subprocess
def test_the_doctor_never_reaches_for_root(tmp_path):
    """Nothing it does needs it, and this machine locks the account out
    on a failed sudo. A stub that records the attempt is the only way to
    show it did not happen."""
    recorder = tmp_path / "sudo-calls"
    stubs = stub_dir(
        tmp_path,
        ip=IP_STUB,
        sudo=f'printf "%s\\n" "$*" >> "{recorder}"\nexit 0\n',
        hyprpm=f'printf "hyprpm %s\\n" "$*" >> "{recorder}"\nexit 0\n',
    )

    result = run_command(BIN / "zepos-doctor", stubs=stubs,
                         home=tmp_path / "home")

    # The run has to have happened, or "sudo was never called" is true of
    # a command that never started either.
    output = assert_ran(result)
    assert "docker0" in output, output
    assert not recorder.exists(), recorder.read_text(encoding="utf-8")


# --------------------------------------------------------------------
# a settings file the commands cannot read
# --------------------------------------------------------------------

# The four JSON documents whose top level is not an object. json.loads
# answers each of them without complaint, and .get() exists on none of
# them - so settings.load() raised AttributeError, which is neither
# ValueError nor OSError and therefore missed by every handler that
# exists for "this file cannot be read".
NON_OBJECT_DOCUMENTS = ("[]", "null", "5", '"text"')


@pytest.mark.allow_subprocess
@pytest.mark.parametrize("document", NON_OBJECT_DOCUMENTS)
def test_the_doctor_reports_a_settings_file_that_is_not_an_object(tmp_path,
                                                                  document):
    """The doctor is what a user runs when the configuration is broken.

    A raw traceback there is the worst possible answer: it names a line
    of Python instead of the file the user has to fix, and it exits with
    a status nothing can act on.
    """
    home = tmp_path / "home"
    settings_file = home / ".config" / "zepos" / "user-settings.json"
    settings_file.parent.mkdir(parents=True)
    settings_file.write_text(document, encoding="utf-8")

    result = run_command(BIN / "zepos-doctor", stubs=stub_dir(tmp_path),
                         home=home)

    output = assert_ran(result)
    assert result.returncode != 0, output
    assert str(settings_file) in output, output
    assert "schema_version" in output, output


@pytest.mark.allow_subprocess
@pytest.mark.parametrize("document", NON_OBJECT_DOCUMENTS)
def test_settings_get_reports_a_file_that_is_not_an_object(tmp_path, document):
    """Same file, the other command that reads it."""
    home = tmp_path / "home"
    settings_file = home / ".config" / "zepos" / "user-settings.json"
    settings_file.parent.mkdir(parents=True)
    settings_file.write_text(document, encoding="utf-8")

    result = run_command(BIN / "zepos-settings", "get",
                         stubs=stub_dir(tmp_path), home=home)

    output = assert_ran(result)
    assert result.returncode != 0, output
    assert str(settings_file) in output, output
    assert settings_file.read_text(encoding="utf-8") == document, (
        "the file it could not read was overwritten")


# --------------------------------------------------------------------
# one writer for one file
# --------------------------------------------------------------------

def test_the_style_settings_writer_never_truncates_the_file(tmp_path,
                                                            monkeypatch):
    """`open(path, 'w')` drops the file to zero bytes the moment it is
    opened, and it creates a new one at 0644.

    Both matter on a file that may hold a VPN pre-shared key and that
    another process may be reading at that instant: a reader landing in
    the window sees an empty document, falls back to its own defaults and
    reports success over a machine that is now configured with nothing.
    """
    import stat

    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    monkeypatch.syspath_prepend(str(SRC))
    import settings
    import user_settings

    path = tmp_path / "user-settings.json"
    document = settings.defaults()
    document["plugins"] = {"enabled": True}
    settings.save(document)

    truncating = []
    real_open = os.open

    def watching_open(target, flags, *args, **kwargs):
        if str(target) == str(path) and flags & (os.O_TRUNC | os.O_WRONLY):
            truncating.append(flags)
        return real_open(target, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", watching_open)
    user_settings.save_settings(settings=user_settings.get_defaults())

    assert truncating == [], "the live file was opened for writing in place"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert settings.load()["plugins"] == {"enabled": True}, (
        "a section this writer does not know about was deleted")


def test_the_style_settings_writer_refuses_a_file_it_cannot_read(tmp_path,
                                                                 monkeypatch,
                                                                 capsys):
    """It warned and carried on with its own defaults - which it then
    saved over the file it had just failed to read, so the one command
    that could still have recovered the settings destroyed them."""
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    monkeypatch.syspath_prepend(str(SRC))
    import user_settings

    path = tmp_path / "user-settings.json"
    original = '{"colors": {"success": "#a6e3a1"}, "vpn": {"serv'
    path.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError):
        user_settings.set_weather_location("Bremen")

    assert path.read_text(encoding="utf-8") == original, (
        "the settings it could not read were overwritten anyway")


def _shipped_files() -> list[Path]:
    """Every file the package installs, source and template alike."""
    return [path for path in sorted(SRC.rglob("*"))
            if path.is_file() and path.suffix != ".pyc"
            and "__pycache__" not in path.parts]


# A line that names the settings file, and a line that writes a file.
# Both on the same line is a writer: `GLib.file_set_contents(SETTINGS_FILE,
# json)`, `open(settings_path, 'w')`, `printf ... > "$USER_SETTINGS_FILE"`.
# Reads are deliberately not matched - file_get_contents and jq are how a
# widget shows what is configured, and nothing about that is dangerous.
SETTINGS_REFERENCE = re.compile(r"SETTINGS_FILE|settings_path|user-settings\.json")
SETTINGS_WRITE = re.compile(
    r"file_set_contents|replace_contents|json\.dump|write_text|write_bytes"
    r"|\bopen\(|>\s*\"?\$\{?\w*SETTINGS|\btee\b")


def test_nothing_writes_the_settings_file_except_the_module_that_owns_it():
    """Four writers of one document, each with its own guarantees, is how
    the file ends up at 0644 on one machine and 0600 on another - and how
    a dialog that could not parse it replaced the whole document with its
    own section.

    The rule is structural because it has to hold for the writers that
    are NOT Python: a GJS dialog cannot import settings.py, so it must
    call it rather than reimplement it. Every shipped file is read,
    templates included - the two dialogs are templates, and a guard that
    only looked at .py files would have seen neither of them.
    """
    offenders = []
    for path in _shipped_files():
        if path.name == "settings.py":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            if SETTINGS_REFERENCE.search(line) and SETTINGS_WRITE.search(line):
                offenders.append(
                    f"{path.relative_to(SRC)}:{number}: {line.strip()}")
    assert offenders == [], (
        "these write user-settings.json themselves instead of through "
        "settings.py: " + "; ".join(offenders))


def test_the_guard_above_recognises_the_writers_it_replaced():
    """The four write forms this project actually contained, so the guard
    cannot quietly stop matching anything."""
    caught = [
        "    GLib.file_set_contents(SETTINGS_FILE, json)",
        "    with open(settings_path, 'w') as f:",
        "        json.dump(settings, f, indent=2)   # settings_path",
        'printf "%s" "$json" > "$USER_SETTINGS_FILE"',
    ]
    for line in caught:
        assert SETTINGS_REFERENCE.search(line) and SETTINGS_WRITE.search(line), (
            f"the guard would miss: {line}")

    left_alone = [
        "    const [ok, contents] = GLib.file_get_contents(SETTINGS_FILE)",
        '    XAUTH_ENABLED=$(jq -r \'.vpn.xauth_enabled\' "$USER_SETTINGS_FILE" 2>/dev/null)',
        "const SETTINGS_FILE = `${ZEPOS_USER_ROOT}/user-settings.json`",
    ]
    for line in left_alone:
        assert not (SETTINGS_REFERENCE.search(line)
                    and SETTINGS_WRITE.search(line)), (
            f"the guard cries wolf over: {line}")


@pytest.mark.allow_subprocess
@pytest.mark.parametrize("template", ["ags-style-editor", "ags-vpn-settings"])
def test_the_command_the_dialogs_call_writes_the_file_the_module_owns(tmp_path,
                                                                     template):
    """The dialogs' write path, run exactly as they spell it.

    A structural check alone would pass over a command line that does not
    work: the argument order, the module path and the section shape all
    have to be right, and none of them can be checked by reading the
    template. So the command is taken OUT of the template and run.
    """
    text = (SRC / "templates" / f"{template}.template").read_text(
        encoding="utf-8")
    call = re.search(r"SETTINGS_WRITER\s*=\s*\[([^\]]*)\]", text)
    assert call, (
        f"{template} no longer names its writer as SETTINGS_WRITER = [...]")
    argv = re.findall(r'["\'`]([^"\'`]+)["\'`]', call.group(1))
    argv = [part.replace("${ZEPOS_SYSTEM_ROOT}", str(SRC)) for part in argv]
    assert argv[0] == "python3", argv
    argv[0] = sys.executable

    home = tmp_path / "home"
    (home / ".config" / "zepos").mkdir(parents=True)
    existing = home / ".config" / "zepos" / "user-settings.json"
    existing.write_text(json.dumps({
        "schema_version": 1,
        "colors": {"success": "#a6e3a1"},
        "vpn": {"server": "gw.example.org"},
        "plugins": {"enabled": True},
    }), encoding="utf-8")

    section = json.dumps({"weather": {"location": "Bremen"}})
    result = subprocess.run(
        [ENV, "-i", f"HOME={home}",
         f"XDG_CONFIG_HOME={home / '.config'}", *argv, section],
        env={}, input="", capture_output=True, text=True, timeout=120)

    assert result.returncode == 0, result.stdout + result.stderr
    written = json.loads(existing.read_text(encoding="utf-8"))
    assert written["weather"] == {"location": "Bremen"}
    assert written["colors"] == {"success": "#a6e3a1"}, "a section was deleted"
    # DER VPN-ABSCHNITT IST GEWANDERT, UND DAS IST DER PUNKT.
    #
    #     Die Datei oben traegt schema_version 1. settings.load() wandert
    #     sie beim Lesen (eine Verbindung wird zu einer Liste mit einer
    #     darin), und dieser Schreibvorgang - ausgeloest von einem
    #     Dialog, der ueber das WETTER spricht - legt die gewanderte
    #     Fassung ab. Genau so war es entworfen: gewandert wird im
    #     Speicher, geschrieben wird, wenn ohnehin jemand schreibt.
    #
    #     Geprueft wird deshalb beides: dass die Liste da ist UND dass
    #     der Serverwert des Nutzers Zeichen fuer Zeichen mitgekommen
    #     ist. Ein Abschnitt, der die Wanderung ueberlebt, aber seinen
    #     Server verloren hat, waere schlimmer als einer, der gar nicht
    #     gewandert waere.
    assert written["schema_version"] == 2
    assert written["vpn"]["active"] == "c1", "a section was deleted"
    assert written["vpn"]["connections"] == [
        {"server": "gw.example.org", "id": "c1"}], "a section was deleted"
    assert written["plugins"] == {"enabled": True}, "a section was deleted"
    assert stat.S_IMODE(existing.stat().st_mode) == 0o600


def test_the_doctor_reports_a_network_list_that_is_a_string(doctor, tmp_path,
                                                            monkeypatch):
    """The same shape the generator refuses, read by the other consumer.

    `"routed_networks": "10.8.0.0/24"` was iterated character by
    character here too: eleven entries, of which "1", "0", "8" and "2"
    parse as networks - 1.0.0.0/32 and friends - so the doctor reported
    on routes the machine has never had and would have named a bridge
    covered by one of them. A report about a configuration nobody has is
    worse than no report.
    """
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    (tmp_path / "user-settings.json").write_text(json.dumps({
        "schema_version": 1,
        "vpn": {"routed_networks": "10.8.0.0/24"},
    }), encoding="utf-8")

    routed, bypassed, findings = doctor.configured_networks()

    assert routed == [], f"a string was read as {len(routed)} networks: {routed}"
    assert bypassed == []
    assert len(findings) == 1, findings
    assert "routed_networks" in str(findings[0]), findings[0]
    assert "10.8.0.0/24" in str(findings[0]), findings[0]


def test_the_doctor_reads_a_proper_network_list(doctor, tmp_path, monkeypatch):
    """The shape that is meant, beside the one that is refused."""
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    (tmp_path / "user-settings.json").write_text(json.dumps({
        "schema_version": 1,
        "vpn": {"routed_networks": ["10.8.0.0/24", " "],
                "bypass_networks": ["192.168.1.0/24"]},
    }), encoding="utf-8")

    routed, bypassed, findings = doctor.configured_networks()

    assert [network.address for network in routed] == ["10.8.0.0/24"]
    assert bypassed == ["192.168.1.0/24"]
    assert findings == []
