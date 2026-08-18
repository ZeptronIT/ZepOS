# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the text interface built directly on installer.core.

collect() is exercised with a scripted io double, so the whole flow is
testable without a terminal. main() additionally injects the wifi
backend, the disk lister and the installer callable - the three other
things a real run would otherwise reach for real subprocesses.
"""
from __future__ import annotations

import pytest

from installer.core.crypt import keyboard_note, loss_warning, unlock_note
from installer.core.disks import Disk
from installer.core.i18n import activate, current_language
from installer.core.model import DiskChoice, InstallConfig, UserAccount
from installer.core.runner import InstallationRefused
from installer.core.wifi import Connection, Network
from installer.tui.app import (
    ConsoleIO, _finish_installation, _print_summary, collect,
)
from installer.tui.app import main as _real_main

VDA_20G = Disk(device="/dev/vda", size_bytes=20 * 1024 ** 3)
VDA_TOO_SMALL = Disk(device="/dev/vda", size_bytes=100 * 1024 ** 2)


def main(**kw):
    """main() with the firmware answer filled in.

    Every test here injects one: main() refuses up front on a machine that
    started in BIOS mode - before the first question, since no answer the
    user could give would change it - and whether the machine RUNNING the
    tests booted through EFI is not what any of these tests are about. The
    two tests that do exercise that refusal pass their own is_uefi. Same
    device, and same reasoning, as test_runner.py's own install() wrapper.
    """
    kw.setdefault("is_uefi", lambda: True)
    return _real_main(**kw)


@pytest.fixture(autouse=True)
def _reset_catalogue():
    """collect() activates a language as its very first step. Left
    active, it would leak into every test collected after this module -
    including ones in other files that assert on the English msgid, per
    the project convention (see test_runner.py's own note on this)."""
    yield
    activate("en")


class ScriptedIO:
    """Answers prompts in order from a scripted list.

    WARUM ES NEBEN `said` NOCH `transcript` GIBT
        `said` haelt nur, was ausgegeben wurde. Damit laesst sich pruefen,
        DASS ein Satz gefallen ist, aber nicht, ob er vor oder nach einer
        FRAGE kam - und genau das ist bei einer Warnung die ganze
        Aussage. Gemessen am 12.08.2026 mit einer Mutation, die in
        installer.tui.app._ask_encryption() die Warnung hinter
        _ask_passphrase() schob: jede Zusicherung, die es damals gab,
        blieb gruen. Eine Warnung, die erst nach der Eingabe erscheint,
        ist keine.

        `transcript` haelt deshalb BEIDES in der Reihenfolge, in der es
        geschah: ("say", text) fuer Ausgaben, ("ask", prompt),
        ("secret", prompt) und ("choose", prompt) fuer Fragen. `said`
        bleibt daneben stehen, damit die vorhandenen Zusicherungen
        unveraendert lesen, was sie immer gelesen haben.
    """

    def __init__(self, answers, choices):
        self.answers = list(answers)
        self.choices = list(choices)
        self.said = []
        self.transcript = []

    def ask(self, prompt, default=""):
        self.transcript.append(("ask", prompt))
        return self.answers.pop(0) or default

    def ask_secret(self, prompt):
        self.transcript.append(("secret", prompt))
        return self.answers.pop(0)

    def choose(self, prompt, options):
        self.transcript.append(("choose", prompt))
        return self.choices.pop(0)

    def say(self, text):
        self.said.append(text)
        self.transcript.append(("say", text))


class ScriptedAssociator:
    """Stands in for installer.core.wifi.associate.

    Never the real one: that opens a socket to check the connection,
    which nothing in this suite may do. Records what it was asked to join
    so a test can prove the passphrase actually reached the live session,
    instead of only the target system's profile.
    """

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, backend, ssid, passphrase):
        self.calls.append((ssid, passphrase))
        return self.results.pop(0) if self.results else Connection(True, "")


# Answers, in the order collect() asks for them: hostname, username,
# password (asked twice - value then confirmation), root password
# (likewise), timezone (empty -> default), weather location (empty ->
# default). Choices: language (German), disk, ZepOS plugins (yes), and
# then the three optional bundles - office, development tools, Firefox -
# each answered "No", which is index 0 for those three.
#
# DIE REIHENFOLGE IST DAS GANZE PROTOKOLL, UND SIE IST POSITIONSGEBUNDEN
#     ScriptedIO.choose() nimmt den naechsten Eintrag, egal wonach
#     gefragt wurde. Eine neue Frage in collect() verschiebt also alles
#     dahinter - am 11.08.2026 waren das die drei Zusatzpakete, und die
#     Bestaetigung aus main() rutschte in jeder Liste um drei Stellen
#     nach hinten. Wer hier eine Frage einfuegt, muss JEDE Liste in
#     dieser Datei anfassen; das ist unbequem und der Grund, aus dem die
#     Listen es ueberhaupt merken.
#
# DIE VERSCHLUESSELUNG STEHT SEIT DEM 12.08.2026 MIT DRIN, und zwar
# BEJAHT. Das ist eine Entscheidung ueber diese Listen und keine
# Bequemlichkeit: die ausgelieferte Vorgabe ist "verschluesseln" (siehe
# installer.gui.pages.PageState.encrypt und installer.tui.app.
# _ask_encryption), und was hier "die gueltigen Antworten" heisst, soll
# der gewoehnliche Nutzer sein und nicht der Sonderfall. Jeder Test, der
# diese Listen benutzt, geht damit nebenbei durch den verschluesselten
# Weg.
#
# Die Frage kommt direkt hinter der Plattenwahl, die Passphrase direkt
# davor in der ANTWORT-Liste: collect() fragt in der Reihenfolge
# WLAN-Passphrase, Plattenpassphrase (zweimal), Rechnername, ... - und
# `answers` ist eine Liste fuer ask() und ask_secret() zusammen. Deshalb
# funktioniert `["wlanpw", *VALID_ANSWERS]` weiter unten unveraendert.
VALID_ANSWERS = [
    "plattenkennwort", "plattenkennwort",
    "zepos", "lars",
    "langgenug", "langgenug",
    "rootlanggenug", "rootlanggenug",
    "", "",
]
# Sprache, Platte, VERSCHLUESSELN (0 = Ja), Plugins, Buero, Entwicklung.
VALID_CHOICES = [0, 0, 0, 0, 0, 0]


def test_collect_builds_a_valid_config():
    io = ScriptedIO(answers=VALID_ANSWERS, choices=VALID_CHOICES)
    cfg = collect(
        io, devices=[VDA_20G], networks=[], wifi_backend=FakeWifiBackend()
    )
    assert cfg.hostname == "zepos"
    assert cfg.users[0].username == "lars"
    assert cfg.disk.device == "/dev/vda"
    assert cfg.wifi is None


def test_collect_carries_the_disk_size_into_the_config():
    """The whole point of the lsblk-backed lister: a DiskChoice without
    size_bytes fails validate() and to_archinstall_config() outright."""
    io = ScriptedIO(answers=VALID_ANSWERS, choices=VALID_CHOICES)
    cfg = collect(
        io, devices=[VDA_20G], networks=[], wifi_backend=FakeWifiBackend()
    )
    assert cfg.disk.size_bytes == 20 * 1024 ** 3


def test_collect_returns_the_chosen_language():
    io = ScriptedIO(answers=VALID_ANSWERS, choices=VALID_CHOICES)
    cfg = collect(
        io, devices=[VDA_20G], networks=[], wifi_backend=FakeWifiBackend()
    )
    assert cfg.language == "de"


def test_collect_activates_the_chosen_language_within_the_same_call():
    """activate() must take effect immediately, not only after collect()
    returns - every prompt after step 1, in this very call, is already
    user-facing text in the chosen language. Checked through the
    mechanism (current_language()), not by asserting on translated text:
    the project convention is msgid-only assertions in tests."""
    io = ScriptedIO(answers=VALID_ANSWERS, choices=VALID_CHOICES)
    collect(
        io, devices=[VDA_20G], networks=[], wifi_backend=FakeWifiBackend()
    )
    assert current_language() == "de"


def test_collect_password_too_short_triggers_a_reprompt():
    """English (choice 1), so the re-ask message can be asserted on its
    msgid rather than a translation."""
    io = ScriptedIO(
        answers=[
            "plattenkennwort", "plattenkennwort",
            "zepos", "lars",
            "kurz",                          # attempt 1: too short
            "langgenug", "langgenug",        # attempt 2 + matching repeat
            "rootlanggenug", "rootlanggenug",
            "", "",
        ],
        choices=[1, 0, 0, 0, 0, 0],
    )
    cfg = collect(
        io, devices=[VDA_20G], networks=[], wifi_backend=FakeWifiBackend()
    )
    assert any("too short" in text for text in io.said)
    assert cfg.users[0].password == "langgenug"


def test_collect_password_mismatch_triggers_a_reprompt():
    io = ScriptedIO(
        answers=[
            "plattenkennwort", "plattenkennwort",
            "zepos", "lars",
            "langgenug", "differentpw",      # attempt 1: does not match
            "langgenug", "langgenug",        # attempt 2 + matching repeat
            "rootlanggenug", "rootlanggenug",
            "", "",
        ],
        choices=[1, 0, 0, 0, 0, 0],
    )
    cfg = collect(
        io, devices=[VDA_20G], networks=[], wifi_backend=FakeWifiBackend()
    )
    assert any("do not match" in text for text in io.said)
    assert cfg.users[0].password == "langgenug"


def test_collect_invalid_hostname_triggers_a_reprompt():
    io = ScriptedIO(
        answers=[
            "plattenkennwort", "plattenkennwort",
            "-bad-hostname", "zepos",        # attempt 1 invalid, attempt 2 valid
            "lars",
            "langgenug", "langgenug",
            "rootlanggenug", "rootlanggenug",
            "", "",
        ],
        choices=[1, 0, 0, 0, 0, 0],
    )
    cfg = collect(
        io, devices=[VDA_20G], networks=[], wifi_backend=FakeWifiBackend()
    )
    assert cfg.hostname == "zepos"
    assert any("hostname" in text for text in io.said)


def test_collect_empty_username_triggers_a_reprompt():
    io = ScriptedIO(
        answers=[
            "plattenkennwort", "plattenkennwort",
            "zepos",
            "", "lars",                      # attempt 1 empty, attempt 2 valid
            "langgenug", "langgenug",
            "rootlanggenug", "rootlanggenug",
            "", "",
        ],
        choices=[1, 0, 0, 0, 0, 0],
    )
    cfg = collect(
        io, devices=[VDA_20G], networks=[], wifi_backend=FakeWifiBackend()
    )
    assert cfg.users[0].username == "lars"
    assert any("may not be empty" in text for text in io.said)


def test_collect_empty_wifi_passphrase_triggers_a_reprompt():
    networks = [Network(ssid="FRITZ!Box", signal=4, secured=True)]
    io = ScriptedIO(
        answers=["", "wlanpw", *VALID_ANSWERS],  # attempt 1 empty, attempt 2 valid
        choices=[1, 0, 0, 0, 0, 0, 0],  # language (en), network, disk, verschluesseln, plugins
    )
    cfg = collect(
        io, devices=[VDA_20G], networks=networks,
        wifi_backend=FakeWifiBackend(devices=["wlan0"]),
        associate=ScriptedAssociator(),
    )
    assert cfg.wifi.passphrase == "wlanpw"
    assert any("may not be empty" in text for text in io.said)


def test_collect_returns_none_when_no_disk_is_large_enough():
    """A too-small disk is a fact about the hardware, not a typo -
    re-prompting cannot fix it, so collect() must stop before asking for
    anything else at all."""
    io = ScriptedIO(answers=[], choices=[1])  # only the language is asked
    cfg = collect(
        io, devices=[VDA_TOO_SMALL], networks=[], wifi_backend=FakeWifiBackend()
    )
    assert cfg is None
    assert any("large enough" in text for text in io.said)


def test_collect_uses_the_default_timezone_when_the_user_accepts_it():
    io = ScriptedIO(answers=VALID_ANSWERS, choices=VALID_CHOICES)
    cfg = collect(
        io, devices=[VDA_20G], networks=[], wifi_backend=FakeWifiBackend()
    )
    assert cfg.timezone == "Europe/Berlin"


def test_collect_lets_the_user_override_the_timezone():
    io = ScriptedIO(
        answers=[
            "plattenkennwort", "plattenkennwort",
            "zepos", "lars",
            "langgenug", "langgenug",
            "rootlanggenug", "rootlanggenug",
            "Europe/Vienna", "",
        ],
        choices=[0, 0, 0, 0, 0, 0],
    )
    cfg = collect(
        io, devices=[VDA_20G], networks=[], wifi_backend=FakeWifiBackend()
    )
    assert cfg.timezone == "Europe/Vienna"


def test_collect_english_selection_yields_english_keymap_and_locale():
    io = ScriptedIO(answers=VALID_ANSWERS, choices=[1, 0, 0, 0, 0, 0])
    cfg = collect(
        io, devices=[VDA_20G], networks=[], wifi_backend=FakeWifiBackend()
    )
    assert cfg.language == "en"
    assert cfg.keymap == "us"
    assert cfg.locale == "en_US"


def test_collect_skips_wifi_silently_when_no_networks_are_offered():
    """Installing over ethernet is normal, not an error - collect() must
    not prompt for a network at all when none were found."""
    io = ScriptedIO(answers=VALID_ANSWERS, choices=VALID_CHOICES)
    cfg = collect(
        io, devices=[VDA_20G], networks=[], wifi_backend=FakeWifiBackend()
    )
    assert cfg.wifi is None
    # Only 3 choices were scripted (language, disk, plugins). If collect()
    # had also called choose() for wifi, this list would be exhausted
    # early and the call above would already have raised IndexError.
    assert io.choices == []


def test_collect_selecting_a_network_asks_for_its_passphrase():
    networks = [Network(ssid="FRITZ!Box", signal=4, secured=True)]
    io = ScriptedIO(
        answers=["wlanpw", *VALID_ANSWERS],
        choices=[0, 0, 0, 0, 0, 0, 0],  # language, network (index 0 = the network), disk, verschluesseln, plugins
    )
    cfg = collect(
        io, devices=[VDA_20G], networks=networks,
        wifi_backend=FakeWifiBackend(devices=["wlan0"]),
        associate=ScriptedAssociator(),
    )
    assert cfg.wifi.ssid == "FRITZ!Box"
    assert cfg.wifi.passphrase == "wlanpw"


def test_collect_skip_option_on_offered_networks_yields_no_wifi():
    networks = [Network(ssid="FRITZ!Box", signal=4, secured=True)]
    io = ScriptedIO(
        answers=VALID_ANSWERS,
        choices=[0, 1, 0, 0, 0, 0, 0],  # language, network (index 1 = "Skip"), disk, verschluesseln, plugins
    )
    cfg = collect(
        io, devices=[VDA_20G], networks=networks,
        wifi_backend=FakeWifiBackend(devices=["wlan0"]),
        associate=ScriptedAssociator(),
    )
    assert cfg.wifi is None


def test_collect_joins_the_chosen_network_in_the_live_session():
    """I1: connect() existed, was specified and was unit tested, and no
    surface ever called it. The passphrase only ever reached the target
    system's profile, so the live session stayed offline and every
    installation on wireless-only hardware silently took the offline
    path."""
    networks = [Network(ssid="FRITZ!Box", signal=4, secured=True)]
    io = ScriptedIO(answers=["wlanpw", *VALID_ANSWERS], choices=[0, 0, 0, 0, 0, 0, 0])
    associator = ScriptedAssociator()
    cfg = collect(
        io, devices=[VDA_20G], networks=networks,
        wifi_backend=FakeWifiBackend(devices=["wlan0"]), associate=associator,
    )
    assert associator.calls == [("FRITZ!Box", "wlanpw")]
    assert cfg.wifi.passphrase == "wlanpw"


def test_collect_reasks_for_the_passphrase_after_a_failed_association():
    """A mistyped passphrase is the most likely error in the installer.
    Accepting it anyway would write the wrong key into the target
    system's profile, leaving the installed machine offline with no hint
    why."""
    networks = [Network(ssid="FRITZ!Box", signal=4, secured=True)]
    io = ScriptedIO(
        answers=["wrongpw", "rightpw", *VALID_ANSWERS],
        # language, network, try again (yes), disk, verschluesseln, plugins
        choices=[1, 0, 0, 0, 0, 0, 0, 0],
    )
    associator = ScriptedAssociator(
        Connection(False, "iwctl station wlan0 connect failed: invalid key"),
        Connection(True, ""),
    )
    cfg = collect(
        io, devices=[VDA_20G], networks=networks,
        wifi_backend=FakeWifiBackend(devices=["wlan0"]), associate=associator,
    )
    assert [passphrase for _ssid, passphrase in associator.calls] == [
        "wrongpw", "rightpw"
    ]
    assert cfg.wifi.passphrase == "rightpw"
    assert any("invalid key" in text for text in io.said)


def test_collect_continues_without_wireless_when_the_user_gives_up():
    """Declining another try is not an error - installing over ethernet,
    or entirely offline, is normal."""
    networks = [Network(ssid="FRITZ!Box", signal=4, secured=True)]
    io = ScriptedIO(
        answers=["wrongpw", *VALID_ANSWERS],
        choices=[1, 0, 1, 0, 0, 0, 0, 0],  # try again -> No
    )
    cfg = collect(
        io, devices=[VDA_20G], networks=networks,
        wifi_backend=FakeWifiBackend(devices=["wlan0"]),
        associate=ScriptedAssociator(Connection(False, "no such network")),
    )
    assert cfg.wifi is None


def test_collect_keeps_going_when_the_network_has_no_internet():
    """Associated but no route out: a warning, not a refusal. Refusing
    would block exactly the case ZepOS carries an offline repository
    for."""
    networks = [Network(ssid="FRITZ!Box", signal=4, secured=True)]
    io = ScriptedIO(answers=["wlanpw", *VALID_ANSWERS], choices=[1, 0, 0, 0, 0, 0, 0])
    cfg = collect(
        io, devices=[VDA_20G], networks=networks,
        wifi_backend=FakeWifiBackend(devices=["wlan0"]),
        associate=ScriptedAssociator(Connection(True, "no internet was found")),
    )
    assert cfg.wifi.ssid == "FRITZ!Box"
    assert any("no internet was found" in text for text in io.said)


def test_collect_declining_zepos_plugins_is_honoured():
    io = ScriptedIO(answers=VALID_ANSWERS, choices=[0, 0, 0, 1, 0, 0])
    cfg = collect(
        io, devices=[VDA_20G], networks=[], wifi_backend=FakeWifiBackend()
    )
    assert cfg.zepos.enable_plugins is False


def test_collect_weather_location_is_carried_through():
    io = ScriptedIO(
        answers=[
            "plattenkennwort", "plattenkennwort",
            "zepos", "lars",
            "langgenug", "langgenug",
            "rootlanggenug", "rootlanggenug",
            "", "Berlin",
        ],
        choices=[0, 0, 0, 0, 0, 0],
    )
    cfg = collect(
        io, devices=[VDA_20G], networks=[], wifi_backend=FakeWifiBackend()
    )
    assert cfg.zepos.weather_location == "Berlin"


# --- main() -----------------------------------------------------------
#
# main() has four injectable dependencies: io, the wifi backend, the
# disk lister and the installer callable. Every real run would otherwise
# shell out to lsblk, iwctl and archinstall - exactly what the isolation
# guard in tests/conftest.py exists to make impossible.


class FakeWifiBackend:
    def __init__(self, devices=(), networks=()):
        self._devices = list(devices)
        self._networks = list(networks)
        self.scanned = []
        self.connected = []

    def devices(self):
        return list(self._devices)

    def scan(self, device):
        self.scanned.append(device)

    def networks(self, device):
        return list(self._networks)

    def connect(self, device, ssid, passphrase):
        self.connected.append((device, ssid, passphrase))


class RaisingWifiBackend:
    def __init__(self, exc):
        self._exc = exc

    def devices(self):
        raise self._exc

    def scan(self, device):
        raise NotImplementedError

    def networks(self, device):
        raise NotImplementedError

    def connect(self, device, ssid, passphrase):
        raise NotImplementedError


class RecordingInstaller:
    def __init__(self, returncode=0):
        self.returncode = returncode
        self.cfg = None
        self.calls = 0

    def __call__(self, cfg):
        self.calls += 1
        self.cfg = cfg
        return self.returncode


def _list_disks(disks):
    def _list(**kw):
        return list(disks)
    return _list


def test_main_happy_path_calls_the_installer_and_returns_its_code():
    io = ScriptedIO(
        answers=VALID_ANSWERS,
        choices=[0, 0, 0, 0, 0, 0, 0],  # Sprache, Platte, verschluesseln, Plugins, Buero, Entwicklung, Bestaetigung (ja)
    )
    installer = RecordingInstaller(returncode=0)
    rc = main(
        io=io,
        wifi_backend=FakeWifiBackend(devices=[]),
        list_disks=_list_disks([VDA_20G]),
        install=installer,
    )
    assert rc == 0
    assert installer.calls == 1
    assert installer.cfg.hostname == "zepos"
    assert installer.cfg.disk.size_bytes == 20 * 1024 ** 3


def test_main_propagates_the_installers_return_code():
    io = ScriptedIO(answers=VALID_ANSWERS, choices=[0, 0, 0, 0, 0, 0, 0])
    installer = RecordingInstaller(returncode=17)
    rc = main(
        io=io,
        wifi_backend=FakeWifiBackend(devices=[]),
        list_disks=_list_disks([VDA_20G]),
        install=installer,
    )
    assert rc == 17


def test_main_returns_early_when_no_disk_is_found():
    io = ScriptedIO(answers=[], choices=[])
    installer = RecordingInstaller()
    rc = main(
        io=io,
        wifi_backend=FakeWifiBackend(devices=[]),
        list_disks=_list_disks([]),
        install=installer,
    )
    assert rc == 1
    assert installer.calls == 0
    # No prompt of any kind should have been reached - proven by the
    # scripted io never being asked to pop from its empty lists.


def test_main_handles_a_missing_lsblk_gracefully():
    def raising_list_disks(**kw):
        raise FileNotFoundError(2, "No such file or directory", "lsblk")

    io = ScriptedIO(answers=[], choices=[])
    installer = RecordingInstaller()
    rc = main(
        io=io,
        wifi_backend=FakeWifiBackend(devices=[]),
        list_disks=raising_list_disks,
        install=installer,
    )
    assert rc == 1
    assert installer.calls == 0
    assert any("Could not list disks" in text for text in io.said)


def test_main_skips_wifi_silently_when_no_wireless_device_exists():
    io = ScriptedIO(answers=VALID_ANSWERS, choices=[0, 0, 0, 0, 0, 0, 0])
    backend = FakeWifiBackend(devices=[])
    installer = RecordingInstaller()
    main(
        io=io,
        wifi_backend=backend,
        list_disks=_list_disks([VDA_20G]),
        install=installer,
    )
    assert backend.scanned == []
    assert installer.cfg.wifi is None


def test_main_scans_and_lists_networks_when_a_wireless_device_exists():
    io = ScriptedIO(
        answers=["wlanpw", *VALID_ANSWERS],
        choices=[0, 0, 0, 0, 0, 0, 0, 0],  # Sprache, Netz, Platte, verschluesseln, Plugins, Buero, Entwicklung, Bestaetigung
    )
    backend = FakeWifiBackend(
        devices=["wlan0"], networks=[Network(ssid="Home", signal=5, secured=True)]
    )
    installer = RecordingInstaller()
    associator = ScriptedAssociator()
    main(
        io=io,
        wifi_backend=backend,
        list_disks=_list_disks([VDA_20G]),
        install=installer,
        associate=associator,
    )
    assert backend.scanned == ["wlan0"]
    assert installer.cfg.wifi.ssid == "Home"
    # I1: the live session must actually join, not merely collect a
    # passphrase for the target system's profile.
    assert associator.calls == [("Home", "wlanpw")]


def test_main_survives_a_broken_iwctl_and_proceeds_over_ethernet():
    io = ScriptedIO(answers=VALID_ANSWERS, choices=[0, 0, 0, 0, 0, 0, 0])
    installer = RecordingInstaller()
    rc = main(
        io=io,
        wifi_backend=RaisingWifiBackend(RuntimeError("iwctl kaputt")),
        list_disks=_list_disks([VDA_20G]),
        install=installer,
    )
    assert rc == 0
    assert installer.cfg.wifi is None


def test_main_refuses_to_start_when_no_disk_is_large_enough():
    """collect() filters out unusable disks before offering any choice at
    all; with only a too-small disk available, main() must stop there
    and never reach install() - proven end-to-end through main(), not
    just at the collect() level (see
    test_collect_returns_none_when_no_disk_is_large_enough above)."""
    io = ScriptedIO(answers=[], choices=[1])  # only the language is asked
    installer = RecordingInstaller()
    rc = main(
        io=io,
        wifi_backend=FakeWifiBackend(devices=[]),
        list_disks=_list_disks([VDA_TOO_SMALL]),
        install=installer,
    )
    assert rc == 1
    assert installer.calls == 0
    assert any("large enough" in text for text in io.said)


def test_main_refuses_a_bios_machine_before_the_first_question():
    """The refusal is a fact about the machine that no answer can change,
    so it belongs before the questions - not after seven of them, an
    "erases the entire disk" confirmation and a "Starting installation."
    The disk lister is a tripwire here: reaching it at all would mean the
    check runs later than it must."""
    def _must_not_be_called(**kw):
        raise AssertionError(
            "a BIOS machine must be refused before anything is enumerated"
        )

    io = ScriptedIO(answers=[], choices=[])
    installer = RecordingInstaller()
    rc = _real_main(
        io=io,
        wifi_backend=FakeWifiBackend(devices=["wlan0"]),
        list_disks=_must_not_be_called,
        install=installer,
        is_uefi=lambda: False,
    )
    assert rc == 1
    assert installer.calls == 0
    assert any("UEFI" in text for text in io.said)


def test_main_asks_its_questions_on_a_uefi_machine():
    """The counterpart: the hoisted check must not refuse a machine that
    is perfectly installable."""
    io = ScriptedIO(answers=VALID_ANSWERS, choices=[0, 0, 0, 0, 0, 0, 0])
    installer = RecordingInstaller()
    rc = _real_main(
        io=io,
        wifi_backend=FakeWifiBackend(devices=[]),
        list_disks=_list_disks([VDA_20G]),
        install=installer,
        is_uefi=lambda: True,
    )
    assert rc == 0
    assert installer.calls == 1


def test_main_does_not_install_when_the_user_declines_the_confirmation():
    io = ScriptedIO(
        answers=VALID_ANSWERS,
        choices=[0, 0, 0, 0, 0, 0, 1],  # Sprache, Platte, verschluesseln, Plugins, Buero, Entwicklung, Bestaetigung (nein)
    )
    installer = RecordingInstaller()
    rc = main(
        io=io,
        wifi_backend=FakeWifiBackend(devices=[]),
        list_disks=_list_disks([VDA_20G]),
        install=installer,
    )
    assert rc == 0
    assert installer.calls == 0


def test_main_prints_a_summary_before_asking_for_confirmation():
    io = ScriptedIO(answers=VALID_ANSWERS, choices=[0, 0, 0, 0, 0, 0, 0])
    installer = RecordingInstaller()
    main(
        io=io,
        wifi_backend=FakeWifiBackend(devices=[]),
        list_disks=_list_disks([VDA_20G]),
        install=installer,
    )
    assert any("zepos" in text for text in io.said)


# --- _finish_installation() ---------------------------------------------
#
# By construction, collect() can no longer produce a config with
# validate() findings: hostname, username, both passwords and the
# wireless passphrase are all validated at the point of entry, and the
# disks collect() offers are pre-filtered to only those large enough
# (see the tests above). _finish_installation()'s own findings check is
# therefore a last-resort net that main() can no longer reach through
# collect() - exercised directly here, bypassing collect() entirely, so
# the gate itself is still proven to work if it ever were reached.


def _valid_cfg() -> InstallConfig:
    return InstallConfig(
        language="en", keymap="us", locale="en_US", timezone="UTC",
        hostname="zepos",
        disk=DiskChoice(device="/dev/vda", size_bytes=20 * 1024 ** 3),
        users=[UserAccount(username="lars", password="langgenug")],
        root_password="rootlanggenug",
    )


class FailingInstaller:
    """An installer that raises, which the real one does at three
    separate points - two of them added by the fix wave this test module
    now covers (the firmware refusal and the disk re-check)."""

    def __init__(self, exception):
        self.exception = exception
        self.calls = 0

    def __call__(self, cfg):
        self.calls += 1
        raise self.exception


def test_finish_installation_reports_a_refusal_instead_of_a_traceback():
    """The user has just confirmed an erase and seen "Starting
    installation." A Python traceback at that moment tells them nothing -
    least of all the one thing they need to know, which is whether the
    disk was already touched."""
    io = ScriptedIO(answers=[], choices=[0])  # confirm (yes)
    installer = FailingInstaller(
        InstallationRefused("The selected disk /dev/vda is no longer available.")
    )
    rc = _finish_installation(io, _valid_cfg(), installer)
    assert rc == 1
    assert any("could not be carried out" in text for text in io.said)
    assert any("no longer available" in text for text in io.said)


def test_finish_installation_says_the_disk_is_untouched_after_a_refusal():
    """A refusal is raised before archinstall is ever invoked, so this
    one statement can be made and is the whole point of catching the
    failure rather than letting it print a traceback."""
    io = ScriptedIO(answers=[], choices=[0])
    installer = FailingInstaller(InstallationRefused("BIOS mode"))
    _finish_installation(io, _valid_cfg(), installer)
    assert any(
        "Nothing on the disk" in text and "/dev/vda" in text for text in io.said
    )


def test_finish_installation_claims_nothing_about_the_disk_for_other_failures():
    """The counterpart, and the reason the refusal has a type of its own:
    a failure that is NOT a refusal may have happened with archinstall
    already running. Saying "nothing was changed" there would be a
    dangerous claim about a disk that may well have been partitioned
    already."""
    io = ScriptedIO(answers=[], choices=[0])
    installer = FailingInstaller(RuntimeError("the run died halfway through"))
    rc = _finish_installation(io, _valid_cfg(), installer)
    assert rc == 1
    assert any("died halfway through" in text for text in io.said)
    assert not any("Nothing on the disk" in text for text in io.said)


def test_finish_installation_reports_a_nonzero_exit_code():
    """archinstall failing is not an exception - it is an exit code, and
    the text interface used to return it without a word."""
    io = ScriptedIO(answers=[], choices=[0])
    rc = _finish_installation(io, _valid_cfg(), RecordingInstaller(returncode=7))
    assert rc == 7
    assert any("exit code" in text and "7" in text for text in io.said)


def test_finish_installation_confirms_a_successful_installation():
    io = ScriptedIO(answers=[], choices=[0])
    rc = _finish_installation(io, _valid_cfg(), RecordingInstaller(returncode=0))
    assert rc == 0
    assert any("successfully" in text for text in io.said)


def test_finish_installation_refuses_to_start_when_validation_findings_remain():
    cfg = InstallConfig(
        language="en", keymap="us", locale="en_US", timezone="UTC",
        hostname="-bad-hostname",  # invalid on purpose; bypasses collect()
        disk=DiskChoice(device="/dev/vda", size_bytes=20 * 1024 ** 3),
        users=[UserAccount(username="lars", password="langgenug")],
        root_password="rootlanggenug",
    )
    io = ScriptedIO(answers=[], choices=[])
    installer = RecordingInstaller()
    rc = _finish_installation(io, cfg, installer)
    assert rc == 1
    assert installer.calls == 0
    assert any("hostname" in text for text in io.said)


def test_finish_installation_calls_the_installer_when_the_config_is_valid():
    cfg = InstallConfig(
        language="en", keymap="us", locale="en_US", timezone="UTC",
        hostname="zepos",
        disk=DiskChoice(device="/dev/vda", size_bytes=20 * 1024 ** 3),
        users=[UserAccount(username="lars", password="langgenug")],
        root_password="rootlanggenug",
    )
    io = ScriptedIO(answers=[], choices=[0])  # confirm (yes)
    installer = RecordingInstaller(returncode=0)
    rc = _finish_installation(io, cfg, installer)
    assert rc == 0
    assert installer.calls == 1
    assert installer.cfg is cfg


# --- ConsoleIO ----------------------------------------------------------
#
# The real terminal implementation. Exercised through monkeypatched
# builtins rather than a real tty - this is the one piece of the module
# the isolation guard has nothing to say about, since input()/print()/
# getpass.getpass() are not subprocesses and do not write to disk.


def test_console_io_ask_returns_the_typed_value(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "lars")
    assert ConsoleIO().ask("Username") == "lars"


def test_console_io_ask_falls_back_to_the_default_on_empty_input(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    assert ConsoleIO().ask("Hostname", "zepos") == "zepos"


def test_console_io_ask_strips_surrounding_whitespace(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "  lars  ")
    assert ConsoleIO().ask("Username") == "lars"


def test_console_io_ask_secret_goes_through_getpass_not_input(monkeypatch):
    """The whole reason ask_secret exists separately from ask(): the
    value must never be echoed to the terminal."""
    monkeypatch.setattr("installer.tui.app.getpass.getpass", lambda prompt: "hunter2")

    def _fail_if_called(prompt):
        raise AssertionError("ask_secret must not go through input()")

    monkeypatch.setattr("builtins.input", _fail_if_called)
    assert ConsoleIO().ask_secret("Password") == "hunter2"


def test_console_io_choose_accepts_a_valid_number(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "2")
    assert ConsoleIO().choose("Select language", ["Deutsch", "English"]) == 1


def test_console_io_choose_reprompts_on_invalid_input(monkeypatch, capsys):
    answers = iter(["0", "abc", "1"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    assert ConsoleIO().choose("Select language", ["Deutsch", "English"]) == 0
    assert "Please enter one of the offered numbers." in capsys.readouterr().out


def test_console_io_say_prints_the_text(capsys):
    ConsoleIO().say("Starting installation.")
    assert capsys.readouterr().out == "Starting installation.\n"


def test_the_confirmation_names_the_disk_that_is_about_to_be_erased():
    """"This erases the entire disk" without saying which one is the
    sentence a user confirms while picturing a different disk - and this
    is the last moment at which that can still be noticed."""
    cfg = InstallConfig(
        language="en", keymap="us", locale="en_US", timezone="UTC",
        hostname="zepos",
        disk=DiskChoice(device="/dev/nvme0n1", size_bytes=20 * 1024 ** 3),
        users=[UserAccount(username="lars", password="langgenug")],
        root_password="rootlanggenug",
    )
    io = ScriptedIO(answers=[], choices=[1])  # decline, so nothing installs
    _finish_installation(io, cfg, RecordingInstaller())
    assert any("/dev/nvme0n1" in text for text in io.said)


# --- die Verschluesselung im Textassistenten ---------------------------
#
# Derselbe Vertrag wie auf der grafischen Seite, ueber dieselbe
# Pruefregel (installer.core.crypt.passphrase_error). Was hier zusaetzlich
# geprueft wird, ist die REIHENFOLGE der Saetze: eine Warnung nach der
# Entscheidung ist eine Warnung, die niemand mehr braucht.


def test_collect_encrypts_by_default_and_carries_the_passphrase():
    io = ScriptedIO(answers=VALID_ANSWERS, choices=VALID_CHOICES)
    cfg = collect(
        io, devices=[VDA_20G], networks=[], wifi_backend=FakeWifiBackend()
    )
    assert cfg.disk.encrypt is True
    assert cfg.disk.passphrase == "plattenkennwort"


def test_collect_warns_about_losing_the_passphrase_before_asking_for_it():
    """Die Warnung MUSS vor der Frage stehen. Wer schon "ja" gesagt hat,
    liest die Begruendung fuer "ja" nicht mehr - er sucht die naechste
    Frage."""
    io = ScriptedIO(answers=VALID_ANSWERS, choices=[1, 0, 0, 0, 0, 0])
    collect(io, devices=[VDA_20G], networks=[], wifi_backend=FakeWifiBackend())

    assert loss_warning() in io.said
    assert keyboard_note() in io.said
    assert unlock_note() in io.said

    # UND ZWAR VOR DER EINGABE, nicht nur irgendwo. Gegen `transcript`
    # geprueft und nicht gegen `said`, weil `said` nur Ausgaben kennt:
    # eine Warnung, die nach dem Tippen erscheint, steht darin an
    # derselben Stelle wie eine davor. Gemessen mit genau dieser Mutation
    # am 12.08.2026 - sie ueberlebte die erste Fassung dieses Tests.
    kinds = [kind for kind, _text in io.transcript]
    texts = [text for _kind, text in io.transcript]

    warned = texts.index(loss_warning())
    typed = next(index for index, kind in enumerate(kinds)
                 if kind == "secret" and "passphrase" in texts[index].lower())
    assert warned < typed, (
        "die Warnung erscheint erst, nachdem die Passphrase eingegeben "
        "wurde - dann ist sie keine Warnung mehr")
    assert texts.index(keyboard_note()) < typed, (
        "der Hinweis auf die Tastaturbelegung kommt zu spaet - er muss "
        "gelesen sein, BEVOR getippt wird")

    # Die Kosten stehen vor der ENTSCHEIDUNG, nicht erst vor der Eingabe:
    # sie sind das, woran jemand "ja" oder "nein" festmacht. Die Frage
    # wird ueber ihren Text gefunden und nicht ueber ihre Stelle - die
    # Stelle waere hier die Plattenwahl.
    decided = next(index for index, kind in enumerate(kinds)
                   if kind == "choose" and "Encrypt" in texts[index])
    assert texts.index(unlock_note()) < decided, (
        "was die Verschluesselung kostet, steht erst hinter der Frage, "
        "ob verschluesselt werden soll")
    assert decided < warned, (
        "die Verlustwarnung steht schon vor der Frage - dann liest sie "
        "auch, wer gleich 'nein' sagt, und sie verliert ihr Gewicht")


def test_collect_names_what_stays_readable():
    io = ScriptedIO(answers=VALID_ANSWERS, choices=[1, 0, 0, 0, 0, 0])
    collect(io, devices=[VDA_20G], networks=[], wifi_backend=FakeWifiBackend())
    assert any("EFI system partition" in text for text in io.said)


def test_collect_declining_encryption_asks_for_no_passphrase():
    """Und es darf keine verlangen: eine Frage nach einer Passphrase, die
    nichts aufschliesst, ist eine Frage, deren Antwort im Klartext in
    einer InstallConfig landet."""
    io = ScriptedIO(
        # Ohne die zwei Passphrasen am Anfang - werden sie doch gefragt,
        # rutscht alles um zwei und der Rechnername waere "langgenug".
        answers=[
            "zepos", "lars",
            "langgenug", "langgenug",
            "rootlanggenug", "rootlanggenug",
            "", "",
        ],
        choices=[1, 0, 1, 0, 0, 0],   # Sprache, Platte, verschluesseln = Nein
    )
    cfg = collect(
        io, devices=[VDA_20G], networks=[], wifi_backend=FakeWifiBackend())

    assert cfg.disk.encrypt is False
    assert cfg.disk.passphrase == ""
    assert cfg.hostname == "zepos"
    assert loss_warning() not in io.said


def test_collect_reasks_a_too_short_passphrase_only_once_per_attempt():
    """Zu kurz wird bemerkt, BEVOR nach der Wiederholung gefragt wird -
    sonst tippt jemand eine zu kurze Passphrase zweimal, um dann zu
    erfahren, dass sie zu kurz war. Die Antwortliste beweist es: nach
    "kurz" folgt sofort der naechste Versuch und keine Wiederholung."""
    io = ScriptedIO(
        answers=[
            "kurz",                                  # Versuch 1: zu kurz
            "plattenkennwort", "plattenkennwort",    # Versuch 2 mit Wiederholung
            "zepos", "lars",
            "langgenug", "langgenug",
            "rootlanggenug", "rootlanggenug",
            "", "",
        ],
        choices=[1, 0, 0, 0, 0, 0],
    )
    cfg = collect(
        io, devices=[VDA_20G], networks=[], wifi_backend=FakeWifiBackend())

    assert cfg.disk.passphrase == "plattenkennwort"
    assert any("too short" in text for text in io.said)


def test_collect_reasks_a_mistyped_repeat():
    io = ScriptedIO(
        answers=[
            "plattenkennwort", "vertippt-anders",     # Versuch 1: stimmt nicht
            "plattenkennwort", "plattenkennwort",     # Versuch 2
            "zepos", "lars",
            "langgenug", "langgenug",
            "rootlanggenug", "rootlanggenug",
            "", "",
        ],
        choices=[1, 0, 0, 0, 0, 0],
    )
    cfg = collect(
        io, devices=[VDA_20G], networks=[], wifi_backend=FakeWifiBackend())

    assert cfg.disk.passphrase == "plattenkennwort"
    assert any("do not match" in text for text in io.said)


def test_the_summary_says_whether_the_disk_is_encrypted():
    cfg = InstallConfig(
        language="en", keymap="us", timezone="UTC", locale="en_US",
        hostname="zepos",
        disk=DiskChoice(device="/dev/vda", size_bytes=64 * 1024 ** 3,
                        encrypt=True, passphrase="eine-lange-passphrase"),
        users=[UserAccount(username="lars", password="langgenug")],
        root_password="langgenug")
    io = ScriptedIO(answers=[], choices=[])
    _print_summary(io, cfg)
    assert any("Encryption" in text for text in io.said)
    # Und niemals die Passphrase selbst.
    assert not any("eine-lange-passphrase" in text for text in io.said)


def test_the_summary_also_says_when_the_disk_is_not_encrypted():
    """Der Fall, den man hier bemerken koennen muss."""
    cfg = InstallConfig(
        language="en", keymap="us", timezone="UTC", locale="en_US",
        hostname="zepos",
        disk=DiskChoice(device="/dev/vda", size_bytes=64 * 1024 ** 3),
        users=[UserAccount(username="lars", password="langgenug")],
        root_password="langgenug")
    io = ScriptedIO(answers=[], choices=[])
    _print_summary(io, cfg)
    assert any("Encryption" in text for text in io.said)


def test_the_confirmation_repeats_the_loss_warning():
    """Der letzte Augenblick, in dem "ich habe sie nirgends notiert" noch
    ein korrigierbarer Zustand ist - und woertlich derselbe Satz wie auf
    der Seite und in der grafischen Rueckfrage."""
    cfg = InstallConfig(
        language="en", keymap="us", timezone="UTC", locale="en_US",
        hostname="zepos",
        disk=DiskChoice(device="/dev/vda", size_bytes=64 * 1024 ** 3,
                        encrypt=True, passphrase="eine-lange-passphrase"),
        users=[UserAccount(username="lars", password="langgenug")],
        root_password="langgenug")
    io = ScriptedIO(answers=[], choices=[1])   # ablehnen, nichts installiert
    _finish_installation(io, cfg, lambda c: 0)
    assert loss_warning() in io.said
