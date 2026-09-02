# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the state behind the GTK4 pages.

PageState is exercised directly, never through a widget: the test
environment has no display. installer.gui.pages must therefore import
without GTK at all - checked explicitly below - so this whole module
stays runnable in a container, and so the text-only fallback path (which
never touches GTK either) cannot be broken by a stray import here.
"""
from __future__ import annotations

import ast
import importlib
import stat
import sys
import tempfile
from pathlib import Path

import pytest

from installer.core.crypt import keyboard_note, loss_warning, unlock_note
from installer.core.disks import Disk, Partition
from installer.core.firmware import firmware_problem
from installer.core.i18n import activate, current_language
from installer.core.layout import (
    ESP_MOUNTPOINT, PlannedPartition, suggested_layout,
)
from installer.core.model import MIN_DISK_MIB
from installer.core.runner import InstallationRefused
from installer.core.validate import validate
from installer.core.wifi import Connection, Network
from installer.gui.pages import (
    PAGE_ORDER, SWAP_CHOICE, LogTail, PageState, confirmation_body,
    default_log_path, discover_networks, run_installation, wireless_step,
)

VDA_20G = Disk(device="/dev/vda", size_bytes=20 * 1024**3)
# Eine Platte, auf der schon etwas liegt. Die Bezeichnungen sind der
# Punkt: "ntfs 'Windows' 39,0 GiB" ist das, woran jemand die falsche
# Platte erkennt, und genau das muss auf der Seite und in der letzten
# Rueckfrage stehen.
WINDOWS_DISK = Disk(
    device="/dev/nvme0n1", size_bytes=40 * 1024**3,
    partitions=(
        Partition(device="/dev/nvme0n1p1", size_bytes=512 * 1024**2,
                  fstype="vfat", label="SYSTEM"),
        Partition(device="/dev/nvme0n1p2", size_bytes=39 * 1024**3,
                  fstype="ntfs", label="Windows"),
    ))
VDA_TOO_SMALL = Disk(device="/dev/vda", size_bytes=100 * 1024**2)
# One MiB below the threshold, on purpose: proves the boundary itself
# (>= MIN_DISK_MIB, not >) rather than just "obviously too small".
VDB_ONE_MIB_SHORT = Disk(
    device="/dev/vdb", size_bytes=(MIN_DISK_MIB - 1) * 1024 * 1024
)


@pytest.fixture(autouse=True)
def _reset_catalogue():
    """to_config() activates a language as one of its first actions (see
    its own docstring). Left active, it would leak into every test
    collected after this module - including ones in other files that
    assert on the English msgid, per the project convention (see
    test_tui.py's identical fixture)."""
    yield
    activate("en")


def _valid_state() -> PageState:
    """Ein Zustand, mit dem installiert werden kann.

    MIT PASSPHRASE, seit dem 12.08.2026. PageState.encrypt ist
    voreingestellt True (der Nutzer hat "immer" verlangt), und ein
    gesetzter Haken ohne Passphrase ist absichtlich UNGUELTIG - sonst
    liefe eine Installation los, die archinstall stillschweigend
    unverschluesselt zu Ende brächte. "Gueltig" heisst hier also
    zwangslaeufig "verschluesselt", und das ist der gewoehnliche Nutzer
    und nicht der Sonderfall.

    Wer den unverschluesselten Weg braucht, setzt encrypt=False - das
    tut test_a_state_without_encryption_is_valid_too() weiter unten.
    """
    state = PageState()
    state.language = "en"
    state.hostname = "zepos"
    state.select_disk(VDA_20G)
    state.encryption_passphrase = "eine-lange-passphrase"
    state.encryption_passphrase_confirm = "eine-lange-passphrase"
    state.username = "lars"
    state.password = "langgenug"
    state.password_confirm = "langgenug"
    state.root_password = "rootlanggenug"
    state.root_password_confirm = "rootlanggenug"
    return state


# --- module shape ---------------------------------------------------


def test_page_order_matches_the_spec():
    """Spec 8.2 zaehlt sieben Schritte auf, und der dritte heisst
    "Festplatte - Ziel und Partitionsschema". Das Schema ist eine eigene
    Seite geworden und steht deshalb direkt hinter der Platte: sie
    braucht deren Groesse, um ueberhaupt eine Einteilung vorschlagen zu
    koennen, und sie muss vor allem stehen, was danach kommt, weil dort
    nichts mehr ueber die Platte entschieden wird.

    Die Verschluesselung kam am 12.08.2026 dazu und steht aus demselben
    Grund an fuenfter Stelle: sie macht Aussagen ueber die Einteilung
    (welche Partitionen eine Passphrase bekommen, welche im Klartext
    bleiben), braucht sie also, und sie ist die letzte Entscheidung ueber
    die Platte.
    """
    assert PAGE_ORDER == [
        "sprache", "netzwerk", "datentraeger", "partitionierung",
        "verschluesselung", "benutzer", "zeit", "zepos", "zusammenfassung",
    ]


def test_the_widget_module_parses_and_only_asks_pages_for_things_it_has():
    """installer.gui.app cannot be imported here at all - this
    environment has no gi - so nothing else in the suite would notice a
    syntax error in it, or a name it imports from pages.py that pages.py
    no longer has. Both would surface for the first time on the ISO, in
    front of a user about to erase a disk.

    Parsing the file and resolving its `from .pages import ...` names
    against the real module is as far as this can be taken without a
    display; it is not a substitute for exercising the widgets, and the
    logic those widgets read back is tested directly throughout this
    module.
    """
    module = ast.parse(Path("installer/gui/app.py").read_text(encoding="utf-8"))
    pages = importlib.import_module("installer.gui.pages")

    imported: list[str] = []
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom) and node.module == "pages":
            imported.extend(alias.name for alias in node.names)

    assert imported, "app.py must keep its logic in pages.py"
    missing = [name for name in imported if not hasattr(pages, name)]
    assert missing == [], f"app.py imports names pages.py does not define: {missing}"


def test_pages_module_imports_without_gtk():
    """A stray `import gi` at module scope would make this module
    untestable in a display-less environment and would also break the
    text-only fallback path, which never touches GTK. Enforced by
    blocking gi's import machinery entirely and re-importing the module
    fresh, rather than trusting that no one added the import by hand."""

    class _BlockGi:
        def find_spec(self, name, path, target=None):
            if name == "gi" or name.startswith("gi."):
                raise ImportError("gi is blocked for this test")
            return None

    sys.modules.pop("installer.gui.pages", None)
    blocker = _BlockGi()
    sys.meta_path.insert(0, blocker)
    try:
        module = importlib.import_module("installer.gui.pages")
    finally:
        sys.meta_path.remove(blocker)
        # Re-import normally so later tests in this module use the real
        # module object rather than the one just imported under the
        # blocker (which is identical, but re-importing is cheap and
        # keeps this test from having any lasting effect on the rest of
        # the suite).
        sys.modules.pop("installer.gui.pages", None)
        importlib.import_module("installer.gui.pages")

    assert "gi" not in sys.modules
    assert hasattr(module, "PageState")


# --- to_config() / findings() ----------------------------------------


def test_state_produces_a_valid_config():
    state = _valid_state()
    assert validate(state.to_config()) == []


def test_wifi_only_set_when_ssid_present():
    state = _valid_state()
    assert state.to_config().wifi is None
    state.wifi_ssid = "Fritz"
    state.wifi_passphrase = "wlanpw"
    assert state.to_config().wifi.ssid == "Fritz"


def test_language_selection_sets_keymap_locale_and_timezone():
    state = PageState()
    state.language = "de"
    cfg = state.to_config()
    assert (cfg.keymap, cfg.locale, cfg.timezone) == (
        "de-latin1", "de_DE", "Europe/Berlin"
    )


def test_findings_are_exposed_for_the_summary_page():
    """Asserted on the msgid, like the rest of the suite.

    This used to look for "Benutzer" - the German translation, which only
    exists once po/build.sh has compiled a catalogue into po/build/, and
    po/build/ is gitignored. The suite therefore passed only on a machine
    where somebody had run that script by hand, and failed from a fresh
    checkout: verified by cloning this repository and running pytest in
    the clone, where exactly this one test failed.
    """
    state = PageState()
    state.set_language("en")
    findings = state.findings()
    assert any("user account" in finding for finding in findings)


def test_explicit_timezone_overrides_the_language_default():
    state = _valid_state()
    state.timezone = "Europe/Vienna"
    assert state.to_config().timezone == "Europe/Vienna"


def test_set_language_activates_the_catalogue_immediately():
    """Mirrors installer.tui.app.collect() calling activate() as its
    very first action: every message computed right after the language
    page - a field's error text, not only the eventual InstallConfig -
    must already be in the chosen language, without waiting for
    to_config() to be called."""
    state = PageState()
    state.set_language("de")
    assert current_language() == "de"
    assert state.language == "de"
    state.set_language("en")
    assert current_language() == "en"


# --- lesson 1: DiskChoice.size_bytes must travel with the device -----


def test_select_disk_fills_both_device_and_size_bytes():
    state = PageState()
    state.select_disk(VDA_20G)
    assert state.device == "/dev/vda"
    assert state.device_size_bytes == 20 * 1024**3
    assert state.to_config().disk.size_bytes == 20 * 1024**3


def test_setting_device_without_a_size_is_caught_by_validate():
    """Guards against the exact defect the text interface review
    flagged: a DiskChoice built from a bare device string, with
    size_bytes left at its default of 0, must fail validate() rather
    than silently installing onto an undersized description of the
    disk."""
    state = _valid_state()
    state.device = "/dev/vda"
    state.device_size_bytes = 0
    findings = validate(state.to_config())
    assert any("too small" in f for f in findings)


# --- lesson 2: only disks at or above MIN_DISK_MIB are offered -------


def test_usable_disks_filters_out_undersized_disks():
    assert PageState.usable_disks([VDA_20G, VDA_TOO_SMALL]) == [VDA_20G]


def test_usable_disks_boundary_is_at_or_above_the_minimum():
    exactly_min = Disk(device="/dev/vdc", size_bytes=MIN_DISK_MIB * 1024 * 1024)
    assert PageState.usable_disks([exactly_min, VDB_ONE_MIB_SHORT]) == [exactly_min]


def test_usable_disks_returns_empty_when_nothing_qualifies():
    assert PageState.usable_disks([VDA_TOO_SMALL]) == []


def test_disk_error_flags_no_disk_selected():
    state = PageState()
    assert state.disk_error() != ""


def test_disk_error_flags_an_undersized_disk():
    state = PageState()
    state.select_disk(VDA_TOO_SMALL)
    assert "too small" in state.disk_error()


def test_disk_error_empty_for_a_properly_sized_disk():
    state = PageState()
    state.select_disk(VDA_20G)
    assert state.disk_error() == ""


# --- lesson 3: fields are validated as they are entered ---------------


def test_hostname_error_flags_an_invalid_hostname():
    state = PageState()
    state.hostname = "-bad-hostname"
    assert "hostname" in state.hostname_error()


def test_hostname_error_empty_for_a_valid_hostname():
    state = PageState()
    state.hostname = "zepos"
    assert state.hostname_error() == ""


def test_username_error_flags_an_empty_username():
    state = PageState()
    assert state.username_error() != ""


def test_username_error_empty_once_set():
    state = PageState()
    state.username = "lars"
    assert state.username_error() == ""


def test_password_error_flags_a_too_short_password():
    state = PageState()
    state.password = "kurz"
    state.password_confirm = "kurz"
    assert "short" in state.password_error()


def test_password_error_flags_mismatched_passwords():
    state = PageState()
    state.password = "langgenug"
    state.password_confirm = "andersgenug"
    assert "match" in state.password_error()


def test_password_error_empty_when_long_enough_and_matching():
    state = PageState()
    state.password = "langgenug"
    state.password_confirm = "langgenug"
    assert state.password_error() == ""


def test_root_password_error_checks_the_root_password_pair_independently():
    """Regression guard: root_password_error() must read
    root_password/root_password_confirm, not accidentally fall back to
    the ordinary user password fields."""
    state = PageState()
    state.password = "langgenug"
    state.password_confirm = "langgenug"
    state.root_password = "kurz"
    state.root_password_confirm = "kurz"
    assert state.password_error() == ""
    assert "short" in state.root_password_error()


# --- lesson 4: wireless passphrase is required once an SSID is set ----


def test_wifi_passphrase_error_empty_with_no_network_selected():
    state = PageState()
    assert state.wifi_passphrase_error() == ""


def test_wifi_passphrase_error_flags_a_network_without_a_password():
    state = PageState()
    state.wifi_ssid = "Fritz"
    assert state.wifi_passphrase_error() != ""


def test_wifi_passphrase_error_empty_once_a_password_is_given():
    state = PageState()
    state.wifi_ssid = "Fritz"
    state.wifi_passphrase = "wlanpw"
    assert state.wifi_passphrase_error() == ""


# --- lesson 5: the wireless step is skipped silently with no networks -


def test_should_skip_wireless_when_no_networks_are_available():
    state = PageState()
    assert state.should_skip("netzwerk") is True


def test_should_skip_wireless_is_false_once_networks_are_available():
    state = PageState()
    state.wifi_networks = [Network(ssid="Fritz", signal=3, secured=True)]
    assert state.should_skip("netzwerk") is False


def test_should_skip_never_applies_to_other_pages():
    state = PageState()
    for page in PAGE_ORDER:
        if page != "netzwerk":
            assert state.should_skip(page) is False


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


def test_discover_networks_returns_nothing_without_a_wireless_device():
    backend = FakeWifiBackend(devices=[])
    assert discover_networks(backend) == []


def test_discover_networks_scans_and_returns_networks_when_a_device_exists():
    backend = FakeWifiBackend(
        devices=["wlan0"], networks=[Network(ssid="Home", signal=5, secured=True)]
    )
    networks = discover_networks(backend)
    assert backend.scanned == ["wlan0"]
    assert networks[0].ssid == "Home"


def test_discover_networks_survives_a_broken_backend():
    backend = RaisingWifiBackend(RuntimeError("iwctl kaputt"))
    assert discover_networks(backend) == []


class GrowingWifiBackend(FakeWifiBackend):
    """A backend whose network list fills in over successive reads.

    This is what iwd does. `iwctl station <dev> scan` starts a scan and
    returns at once; get-networks answers with whatever has been heard
    so far, and more appears as each channel is swept. A fake that
    returns its full list on the first call cannot tell a caller that
    waits from one that does not - which is exactly how the shipped
    version passed its tests while showing three networks out of nine.
    """

    def __init__(self, rounds):
        super().__init__(devices=["wlan0"])
        self._rounds = list(rounds)
        self.reads = 0

    def networks(self, device):
        self.reads += 1
        index = min(self.reads - 1, len(self._rounds) - 1)
        return list(self._rounds[index])


def _net(name):
    return Network(ssid=name, signal=5, secured=True)


def test_a_scan_that_is_still_filling_in_is_waited_for():
    """The bug from the shipping medium, as a test.

    Three networks on the first read, nine once the scan has finished.
    Returning after the first read is what shipped; it is also what
    every earlier test here allowed, because their fake answered the
    same list every time.
    """
    backend = GrowingWifiBackend([
        [_net(n) for n in "ABC"],
        [_net(n) for n in "ABCDEF"],
        [_net(n) for n in "ABCDEFGHI"],
        [_net(n) for n in "ABCDEFGHI"],
    ])

    found = discover_networks(backend, poll=0.0, sleep=lambda _s: None)

    assert [n.ssid for n in found] == list("ABCDEFGHI")


def test_waiting_stops_as_soon_as_the_list_stops_growing():
    """It waits for the scan, not for the budget.

    Two reads that agree end it. Without this the function would sleep
    out its whole allowance on every machine, including the common one
    where the first answer is already complete - and window
    construction blocks on it.
    """
    backend = GrowingWifiBackend([[_net("A")], [_net("A")], [_net("A")]])

    discover_networks(backend, poll=0.0, sleep=lambda _s: None)

    assert backend.reads == 2, (
        f"read the list {backend.reads} times to learn it had stopped "
        "changing; two is enough")


def test_the_wait_is_bounded_and_returns_what_it_has():
    """A list that never settles must not hold the installer.

    The fake grows on every single read, so the only thing that can end
    this is the budget. What comes back is the best list seen, not an
    empty one - an installer that appears with four networks beats one
    that does not appear.
    """
    class Endless(FakeWifiBackend):
        def __init__(self):
            super().__init__(devices=["wlan0"])
            self.reads = 0

        def networks(self, device):
            self.reads += 1
            return [_net(f"N{i}") for i in range(self.reads)]

    backend = Endless()
    slept = []

    found = discover_networks(
        backend, budget=1.0, poll=0.25, sleep=slept.append)

    assert sum(slept) <= 1.0 + 0.25, f"slept {sum(slept)}s past a 1s budget"
    assert len(found) >= 1, "gave up and returned nothing"


def test_a_network_heard_once_is_not_dropped_when_the_list_shrinks():
    """iwd forgets an access point it can no longer hear. A shorter
    second read still means the scan is over, and the answer keeps the
    longer list rather than the newer one - the user is choosing from
    what is around them, and a network that appeared is one they may be
    waiting for."""
    backend = GrowingWifiBackend([
        [_net("A"), _net("B")],
        [_net("A")],
    ])

    found = discover_networks(backend, poll=0.0, sleep=lambda _s: None)

    assert [n.ssid for n in found] == ["A", "B"]


def test_discover_networks_survives_a_missing_iwctl():
    backend = RaisingWifiBackend(FileNotFoundError(2, "No such file", "iwctl"))
    assert discover_networks(backend) == []


# --- page_error() drives a per-page error label ------------------------


def test_page_error_matches_disk_error_on_the_disk_page():
    state = PageState()
    assert state.page_error("datentraeger") == state.disk_error()
    state.select_disk(VDA_20G)
    assert state.page_error("datentraeger") == ""


def test_page_error_matches_wifi_passphrase_error_on_the_network_page():
    state = PageState()
    state.wifi_ssid = "Fritz"
    assert state.page_error("netzwerk") == state.wifi_passphrase_error()


def test_page_error_is_empty_for_pages_without_field_level_checks():
    """Drei Seiten, und "zeit" gehoert seit dem 02.09.2026 NICHT mehr
    dazu.

    Die Seite hat seither einen eigenen Feldbefund
    (PageState.timezone_error): ein Zonenname, den die Datenbank nicht
    kennt, haelt sie an. Sie stand hier weiter in der Liste und war
    trotzdem gruen - aber nur, WEIL PageState() mit einer leeren
    Zeitzone startet und ein leeres Feld kein erfundener Name ist. Der
    Name dieses Tests behauptete damit etwas, das nicht mehr stimmte,
    und die Zusicherung ging aus einem Grund durch, der mit ihrer
    Aussage nichts zu tun hatte.

    Was fuer "zeit" wirklich gilt, halten
    test_page_error_reports_an_invented_timezone_on_the_time_page()
    unten und tests/installer/test_zeitzone.py.
    """
    state = PageState()
    for page in ("sprache", "zepos", "zusammenfassung"):
        assert state.page_error(page) == ""


def test_page_error_reports_an_invented_timezone_on_the_time_page():
    """Die Seite "zeit" hat einen Feldbefund, und hier steht er.

    Sie ist aus der Aufzaehlung darueber herausgefallen; eine
    Zusicherung durch keine zu ersetzen haette die Seite ungeprueft
    gelassen. Der volle Fall - alle drei Tore und die Gegenproben -
    steht in tests/installer/test_zeitzone.py.
    """
    state = PageState()
    # Leer heisst weiter "keine Angabe" und nicht "falsche Angabe": die
    # laufende Zone tritt dann in to_config() ein.
    assert state.page_error("zeit") == ""

    state.timezone = "Europe/Berln"
    assert state.page_error("zeit") != "", (
        "ein Tippfehler in der Zeitzone laesst die Seite wieder "
        "weiterblaettern - `date` nimmt jeden Namen an und die Uhr geht "
        "danach still falsch")
    assert "Europe/Berln" in state.page_error("zeit"), (
        "der Befund nennt den getippten Namen nicht")


# --- is_page_valid() gates the "next" button per page -----------------


def test_is_page_valid_sprache_and_zepos_have_no_required_fields():
    """"zeit" ist am 02.09.2026 aus dem Namen und aus der Liste
    gefallen: die Seite HAT jetzt ein Pflichtfeld im Sinne dieser Frage
    - eine Zone, die die Datenbank nicht kennt, sperrt den
    Weiter-Knopf.

    Die alte Fassung behauptete das Gegenteil und war trotzdem gruen,
    weil PageState() mit einer leeren Zeitzone startet. Ein leeres Feld
    ist keine falsche Angabe; geprueft hat sie damit den Anfangszustand
    und nicht die Zusage.
    """
    state = PageState()
    assert state.is_page_valid("sprache") is True
    assert state.is_page_valid("zepos") is True


def test_is_page_valid_zeit_gates_the_next_button_on_the_timezone():
    """Der Ersatz fuer die Zeile, die oben herausgefallen ist.

    Leer bleibt gueltig - to_config() setzt dann die laufende Zone.
    Ein erfundener Name ist es nicht: er kaeme sonst ueber diese Seite
    bis in die archinstall-Datei, und `date` beschwert sich nicht
    (installer/core/validate.py:_timezone_findings fuehrt die Messung
    aus).
    """
    state = PageState()
    assert state.is_page_valid("zeit") is True

    state.timezone = "Europe/Berln"
    assert state.is_page_valid("zeit") is False, (
        "der Weiter-Knopf laesst eine Zone durch, die es nicht gibt")

    state.timezone = "UTC"
    assert state.is_page_valid("zeit") is True, (
        "eine Zone, die jede Datenbank kennt, wird abgelehnt - dann "
        "prueft die Zeile darueber nicht die Zone, sondern irgendetwas "
        "anderes")


def test_is_page_valid_datentraeger_requires_a_properly_sized_disk():
    state = PageState()
    assert state.is_page_valid("datentraeger") is False
    state.select_disk(VDA_20G)
    assert state.is_page_valid("datentraeger") is True


def test_is_page_valid_benutzer_requires_every_field_to_check_out():
    state = PageState()
    assert state.is_page_valid("benutzer") is False
    state.username = "lars"
    state.password = "langgenug"
    state.password_confirm = "langgenug"
    state.root_password = "rootlanggenug"
    state.root_password_confirm = "rootlanggenug"
    assert state.is_page_valid("benutzer") is True


def test_is_page_valid_netzwerk_is_true_without_a_chosen_network():
    """Skipping the wireless page (no SSID chosen at all) must not block
    navigation - only a chosen SSID with a missing passphrase does."""
    state = PageState()
    assert state.is_page_valid("netzwerk") is True
    state.wifi_ssid = "Fritz"
    assert state.is_page_valid("netzwerk") is False
    state.wifi_passphrase = "wlanpw"
    assert state.is_page_valid("netzwerk") is True


def test_is_page_valid_zusammenfassung_mirrors_findings():
    state = PageState()
    assert state.is_page_valid("zusammenfassung") is False
    state = _valid_state()
    assert state.is_page_valid("zusammenfassung") is True


# --- the live session actually joins the chosen network ---------------


class ScriptedAssociator:
    """Stands in for installer.core.wifi.associate, which opens a socket
    to check the connection - nothing in this suite may."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, backend, ssid, passphrase):
        self.calls.append((ssid, passphrase))
        return self.results.pop(0) if self.results else Connection(True, "")


def test_no_association_is_needed_without_a_chosen_network():
    """Installing over ethernet is normal, and the wireless page is
    skipped entirely when nothing was found."""
    assert PageState().needs_association() is False


def test_association_is_needed_once_a_network_is_chosen():
    state = PageState()
    state.wifi_ssid = "Fritz"
    state.wifi_passphrase = "wlanpw"
    assert state.needs_association() is True


def test_wireless_step_joins_the_network_and_remembers_it():
    """I1: no surface used to call connect() at all, so the live session
    never joined and every installation on wireless-only hardware
    silently took the offline path."""
    state = PageState()
    state.wifi_ssid = "Fritz"
    state.wifi_passphrase = "wlanpw"
    associator = ScriptedAssociator()

    result = wireless_step(state, FakeWifiBackend(devices=["wlan0"]),
                           associate=associator)

    assert associator.calls == [("Fritz", "wlanpw")]
    assert result.connected is True
    assert state.needs_association() is False


def test_wireless_step_does_nothing_the_second_time_around():
    """Paging back and forth must not re-run a connect that takes
    seconds."""
    state = PageState()
    state.wifi_ssid = "Fritz"
    state.wifi_passphrase = "wlanpw"
    associator = ScriptedAssociator()
    backend = FakeWifiBackend(devices=["wlan0"])
    wireless_step(state, backend, associate=associator)
    wireless_step(state, backend, associate=associator)
    assert len(associator.calls) == 1


def test_a_corrected_passphrase_is_tried_again():
    """The stored pair, not a flag: editing the passphrase after a failed
    attempt must invalidate the association by itself."""
    state = PageState()
    state.wifi_ssid = "Fritz"
    state.wifi_passphrase = "wrongpw"
    associator = ScriptedAssociator(Connection(False, "invalid key"))
    backend = FakeWifiBackend(devices=["wlan0"])

    failed = wireless_step(state, backend, associate=associator)
    assert failed.connected is False
    assert state.needs_association() is True

    state.wifi_passphrase = "rightpw"
    wireless_step(state, backend, associate=associator)
    assert [passphrase for _ssid, passphrase in associator.calls] == [
        "wrongpw", "rightpw"
    ]


def test_wireless_step_is_a_no_op_when_no_network_was_chosen():
    associator = ScriptedAssociator()
    result = wireless_step(PageState(), FakeWifiBackend(), associate=associator)
    assert result.connected is True
    assert associator.calls == []


def test_wireless_step_never_raises_out_of_the_worker_thread():
    """wireless_step() runs on a worker thread, and an exception escaping
    one reaches sys.excepthook and is shown to nobody - the same reason
    run_installation() catches everything. Worse here: the completion
    callback is what clears the in-flight flag below, so an escaping
    exception would leave the "next" button dead for the rest of the
    session."""
    def exploding(backend, ssid, passphrase):
        raise RuntimeError("iwd went away")

    state = PageState()
    state.wifi_ssid = "Fritz"
    state.wifi_passphrase = "wlanpw"
    result = wireless_step(
        state, FakeWifiBackend(devices=["wlan0"]), associate=exploding
    )
    assert result.connected is False
    assert "iwd went away" in result.message
    assert state.needs_association() is True


# --- only one wireless worker may ever be in flight --------------------
#
# The race this closes: the GTK surface disabled the "next" button while
# a connect ran, but any keystroke in the passphrase field re-enabled it
# through the ordinary validation refresh. A click then started a SECOND
# worker, and each completion advanced the form by one page - so two
# completions skipped the disk page entirely, where the disk to be erased
# is pre-selected. The user would never have seen it.


def test_only_one_wireless_worker_may_be_in_flight():
    state = PageState()
    state.wifi_ssid = "Fritz"
    state.wifi_passphrase = "wlanpw"
    assert state.begin_wireless_step() is True
    assert state.begin_wireless_step() is False, (
        "a second worker would advance the form twice and skip the disk page"
    )
    state.end_wireless_step()
    assert state.begin_wireless_step() is True


def test_the_network_page_is_invalid_while_a_connect_is_in_flight():
    """Gated on the flag, not on the button's own sensitivity: every
    keystroke recomputes that sensitivity from here, so this is the only
    place the answer can come from."""
    state = PageState()
    state.wifi_ssid = "Fritz"
    state.wifi_passphrase = "wlanpw"
    assert state.is_page_valid("netzwerk") is True
    state.begin_wireless_step()
    assert state.is_page_valid("netzwerk") is False
    state.end_wireless_step()
    assert state.is_page_valid("netzwerk") is True


def test_a_connect_in_flight_is_not_an_error_message():
    """A connection in progress is a transient state, not a mistake the
    user made - the page is un-leavable while it runs, but there is
    nothing to correct and nothing to show in red."""
    state = PageState()
    state.wifi_ssid = "Fritz"
    state.wifi_passphrase = "wlanpw"
    state.begin_wireless_step()
    assert state.page_error("netzwerk") == ""


def test_the_in_flight_flag_leaves_other_pages_alone():
    state = _valid_state()
    state.wifi_ssid = "Fritz"
    state.wifi_passphrase = "wlanpw"
    state.begin_wireless_step()
    assert state.is_page_valid("datentraeger") is True
    assert state.is_page_valid("benutzer") is True


# --- a machine that cannot boot what ZepOS installs is refused up front -
#
# The check itself is in the right place in installer.core.runner (before
# anything destructive), but reaching it meant answering every question
# and confirming an erase first. Whether the machine started in UEFI mode
# is knowable before the first page, so app.py reads it once at window
# construction and drops the answer here.


def test_a_firmware_refusal_blocks_every_page():
    state = _valid_state()
    state.firmware_error = firmware_problem(is_uefi=lambda: False)
    for page in PAGE_ORDER:
        assert state.page_error(page) == state.firmware_error
        assert state.is_page_valid(page) is False


def test_the_firmware_refusal_names_the_reason():
    """The same single msgid installer.core.runner refuses with - one
    description of one rule, not a parallel one per surface."""
    state = PageState()
    state.firmware_error = firmware_problem(is_uefi=lambda: False)
    assert "UEFI" in state.page_error("sprache")


def test_a_uefi_machine_leaves_the_pages_untouched():
    state = _valid_state()
    state.firmware_error = firmware_problem(is_uefi=lambda: True)
    assert state.firmware_error == ""
    assert state.is_page_valid("sprache") is True
    assert state.is_page_valid("zusammenfassung") is True


# --- the point of no return names the disk ----------------------------


def test_the_confirmation_names_the_disk_that_is_about_to_be_erased():
    """"This erases the entire disk" without saying which one is the
    sentence a user confirms while picturing a different disk - and this
    dialog is the last moment that can still be noticed."""
    body = confirmation_body("/dev/nvme0n1")
    assert "/dev/nvme0n1" in body


def test_the_confirmation_names_every_partition_it_destroys():
    """Der Geraetename allein reicht nicht. "/dev/nvme0n1" ist auf einer
    Maschine mit zwei Platten kein Wort, an dem jemand die falsche
    erkennt; "ntfs 'Windows' 465,8 GiB" ist eines."""
    body = confirmation_body(
        "/dev/nvme0n1", existing=WINDOWS_DISK.partitions)
    for partition in WINDOWS_DISK.partitions:
        assert partition.device in body
    assert "Windows" in body
    assert "ntfs" in body


def test_the_confirmation_counts_what_it_destroys():
    body = confirmation_body("/dev/nvme0n1", existing=WINDOWS_DISK.partitions)
    assert "2 partitions will be deleted" in body


def test_the_confirmation_also_names_what_is_created():
    """Eine Rueckfrage, die nur das Schlimme nennt, ist eine Warnung;
    eine, die beides nennt, ist eine Entscheidung."""
    body = confirmation_body(
        "/dev/nvme0n1", layout=suggested_layout(20 * 1024 ** 3))
    assert "fat32" in body
    assert "ext4" in body


def test_the_confirmation_stays_one_sentence_without_the_lists():
    """Ein Aufrufer, der nur den Geraetenamen hat, bekommt denselben Satz
    wie vor dieser Seite - deshalb sind beide Listen
    Schluesselwortargumente mit einer Vorgabe."""
    assert confirmation_body("/dev/vda").splitlines() == [
        "This erases the entire disk /dev/vda."
    ]


# --- die Einteilung der Platte ----------------------------------------
#
# Gemeldet als "ausserdem soll man im wizard die festplatten bereinigen
# koennen und neu zuweisen mit partitionen usw. das fehlt noch komplett".


def _planned_state() -> PageState:
    state = _valid_state()
    state.select_disk(WINDOWS_DISK)
    return state


def test_choosing_a_disk_also_reads_what_is_on_it():
    """Die Liste ist das, was die Seite aufzaehlt und was die letzte
    Rueckfrage beim Namen nennt. Ohne sie waere "die Platte wird
    geloescht" eine Floskel."""
    state = _planned_state()
    assert state.device_partitions == WINDOWS_DISK.partitions


def test_choosing_a_disk_puts_the_suggestion_in_place():
    state = _planned_state()
    assert state.layout == suggested_layout(WINDOWS_DISK.size_bytes)
    assert state.layout_error() == ""


def test_changing_the_disk_replaces_the_layout():
    """Eine Einteilung ist in MiB ab dem Anfang GENAU DIESER Platte
    gerechnet. Eine Wurzel, die auf 40 GiB bis zum Ende reicht, ragt auf
    20 GiB darueber hinaus, und archinstall lehnt dann die ganze
    Konfiguration ab."""
    state = _planned_state()
    state.select_disk(VDA_20G)
    assert state.layout_error() == ""
    assert state.layout[-1].end_mib < VDA_20G.size_bytes // (1024 * 1024)


def test_choosing_the_same_disk_again_keeps_a_hand_made_layout():
    """_build_datentraeger() waehlt die erste Platte beim Bauen der
    Seite, und _on_disk_toggled() ruft dieselbe Methode. Ein Klick auf
    die schon gewaehlte Zeile darf nicht wegwerfen, was jemand eine Seite
    weiter von Hand geplant hat."""
    state = _planned_state()
    state.clear_layout()
    state.new_mountpoint = "/"
    state.new_size = "8G"
    assert state.add_partition() == ""
    mine = list(state.layout)

    state.select_disk(WINDOWS_DISK)
    assert state.layout == mine


def test_clearing_the_disk_empties_the_layout():
    state = _planned_state()
    state.clear_layout()
    assert state.layout == []


def test_an_empty_layout_stops_the_next_button_and_says_why():
    """wipe=True mit einer leeren Partitionsliste loescht die Platte und
    legt nichts an."""
    state = _planned_state()
    state.clear_layout()
    assert state.is_page_valid("partitionierung") is False
    assert "empty" in state.page_error("partitionierung")


def test_the_suggestion_can_be_put_back():
    state = _planned_state()
    state.clear_layout()
    state.reset_layout()
    assert state.layout == suggested_layout(WINDOWS_DISK.size_bytes)


def test_a_partition_is_added_where_there_is_room():
    state = _planned_state()
    state.clear_layout()
    state.new_mountpoint = "/"
    state.new_size = "8G"
    assert state.add_partition() == ""
    assert state.layout[0].size_mib == 8 * 1024
    assert state.layout[0].start_mib == 1


def test_adding_a_partition_clears_the_size_field():
    """Sonst legt der naechste Druck auf denselben Knopf dieselbe
    Partition ein zweites Mal an."""
    state = _planned_state()
    state.clear_layout()
    state.new_mountpoint = "/"
    state.new_size = "8G"
    state.add_partition()
    assert state.new_size == ""


def test_a_size_without_a_unit_adds_nothing_and_gives_a_reason():
    state = _planned_state()
    state.clear_layout()
    state.new_size = "20"
    problem = state.add_partition()
    assert state.layout == []
    assert "unit" in problem


def test_a_partition_bigger_than_the_free_space_adds_nothing():
    state = _planned_state()
    state.new_size = "1T"
    problem = state.add_partition()
    assert state.layout == suggested_layout(WINDOWS_DISK.size_bytes)
    assert "does not fit" in problem


def test_the_esp_choice_carries_the_flags_and_the_filesystem():
    """Die Firmware liest nur FAT, und archinstalls
    get_efi_partition()/get_boot_partition() finden die Partition nur
    ueber die beiden Flaggen."""
    state = _planned_state()
    state.clear_layout()
    state.new_mountpoint = ESP_MOUNTPOINT
    state.new_filesystem = "btrfs"          # wird nicht gefragt
    state.new_size = "512M"
    assert state.add_partition() == ""
    esp = state.layout[0]
    assert esp.filesystem == "fat32"
    assert set(esp.flags) == {"boot", "esp"}


def test_the_swap_choice_has_no_mount_point():
    """archinstall erkennt die Auslagerung am Dateisystem und bindet sie
    mit swapon() statt mount() ein - ein Einhaengepunkt waere hier
    falsch."""
    state = _planned_state()
    state.clear_layout()
    state.new_mountpoint = SWAP_CHOICE
    state.new_size = "2G"
    assert state.add_partition() == ""
    assert state.layout[0].mountpoint == ""
    assert state.layout[0].filesystem == "linux-swap"


@pytest.mark.parametrize("choice, chosen", [
    ("/", True), ("/home", True), (ESP_MOUNTPOINT, False), (SWAP_CHOICE, False),
])
def test_the_filesystem_is_only_a_question_where_there_is_a_choice(
    choice: str, chosen: bool
):
    """Bei der ESP und der Auslagerung ist es die Folge der Entscheidung
    darueber. app.py schaltet die Zeile daraufhin unbedienbar, statt eine
    Eingabe entgegenzunehmen und still zu verwerfen."""
    state = _planned_state()
    state.new_mountpoint = choice
    assert state.filesystem_is_chosen() is chosen


def test_added_partitions_stay_in_the_order_of_the_disk():
    """Die Seite zeigt sie als Liste, und eine Liste, deren Reihenfolge
    nicht die der Platte ist, macht aus einer Luecke eine unsichtbare."""
    state = _planned_state()
    state.clear_layout()
    for mountpoint, size in (("/", "8G"), (ESP_MOUNTPOINT, "512M")):
        state.new_mountpoint = mountpoint
        state.new_size = size
        assert state.add_partition() == ""
    assert [p.start_mib for p in state.layout] == sorted(
        p.start_mib for p in state.layout)


def test_a_new_partition_fills_the_hole_a_removed_one_left():
    state = _planned_state()
    state.clear_layout()
    for mountpoint, size in ((ESP_MOUNTPOINT, "512M"), ("/home", "4G"),
                             ("/", "8G")):
        state.new_mountpoint = mountpoint
        state.new_size = size
        assert state.add_partition() == ""
    home = state.layout[1]
    state.remove_partition(home)

    state.new_mountpoint = "/var"
    state.new_size = "1G"
    assert state.add_partition() == ""
    assert state.layout[1].mountpoint == "/var"
    assert state.layout[1].start_mib == home.start_mib


def test_removing_takes_the_partition_that_was_asked_for():
    """Nach dem Wert und nicht nach dem Index: app.py baut die Zeilen bei
    jeder Aenderung neu, und ein Index, der beim Bauen richtig war, zeigt
    danach auf die Nachbarin."""
    state = _planned_state()
    esp, root = state.layout
    state.remove_partition(esp)
    assert state.layout == [root]


def test_removing_something_that_is_not_planned_changes_nothing():
    state = _planned_state()
    before = list(state.layout)
    state.remove_partition(PlannedPartition(
        start_mib=99, size_mib=1, filesystem="ext4", mountpoint="/srv"))
    assert state.layout == before


def test_the_size_error_stays_quiet_until_something_was_typed():
    state = _planned_state()
    state.clear_layout()
    assert state.size_error() != ""      # leer heisst "bitte eine Groesse"
    state.new_size = "8G"
    assert state.size_error() == ""


def test_the_layout_reaches_the_install_config():
    """Ohne das waere die Seite eine Anzeige: installer.core.translate
    liest cfg.disk.layout und nichts sonst."""
    state = _planned_state()
    state.clear_layout()
    state.new_mountpoint = ESP_MOUNTPOINT
    state.new_size = "512M"
    state.add_partition()
    assert state.to_config().disk.layout == state.layout


def test_the_config_gets_a_copy_and_not_the_list_itself():
    """Die InstallConfig geht an einen Arbeitsthread, der sie waehrend
    der Installation liest, und die Seite bleibt so lange bedienbar, wie
    sie sichtbar ist.

    Die Liste wird hier AN ORT UND STELLE veraendert und nicht neu
    zugewiesen. clear_layout() und add_partition() binden self.layout neu,
    und dagegen hilft auch eine geteilte Liste - dieser Test war deshalb
    zuerst einer, der gruen blieb, als die Kopie entfernt wurde. Gemessen
    im Mutationslauf zu dieser Aufgabe.
    """
    state = _planned_state()
    cfg = state.to_config()
    state.layout.clear()
    assert cfg.disk.layout != []


def test_the_page_says_how_many_partitions_it_will_delete():
    state = _planned_state()
    assert "2 partitions will be deleted" in state.existing_summary()


def test_one_partition_is_counted_in_the_singular():
    """ngettext und nicht eine Vorlage: "1 partitions will be deleted"
    ist der Fehler, den ein Leser sofort bemerkt."""
    state = _valid_state()
    state.select_disk(Disk(
        device="/dev/vdc", size_bytes=20 * 1024 ** 3,
        partitions=(Partition(device="/dev/vdc1", size_bytes=1024 ** 3),)))
    assert "1 partition will be deleted" in state.existing_summary()


def test_an_empty_disk_says_there_is_nothing_on_it():
    state = _valid_state()
    state.select_disk(VDA_20G)
    assert "no partition" in state.existing_summary()


def test_the_page_says_how_much_is_still_free():
    """Die "Belegung", die auf dieser Seite ueberhaupt zu haben ist:
    lsblks FSUSE% ist nur bei eingehaengten Dateisystemen gefuellt, und
    list_disks() wirft jede Platte weg, auf der etwas eingehaengt ist -
    siehe den Kopf von installer/core/layout.py."""
    state = _planned_state()
    state.clear_layout()
    state.new_mountpoint = "/"
    state.new_size = "8G"
    state.add_partition()
    summary = state.layout_summary()
    assert "32.0 GiB" in summary     # 40 GiB minus 8 GiB minus die Raender
    assert "40.0 GiB" in summary


# --- run_installation(): every ending becomes something readable -------


class RecordingInstaller:
    """Stands in for installer.core.runner.install, which
    run_installation() calls with keyword arguments it must accept."""

    def __init__(self, returncode=0, exception=None, warnings=()):
        self.returncode = returncode
        self.exception = exception
        self.warnings = list(warnings)
        self.calls = 0
        self.log_path = None

    def __call__(self, cfg, *, log_path=None, on_warning=None):
        self.calls += 1
        self.log_path = log_path
        for warning in self.warnings:
            on_warning(warning)
        if self.exception is not None:
            raise self.exception
        return self.returncode


def test_run_installation_reports_success():
    outcome = run_installation(_valid_state().to_config(), RecordingInstaller())
    assert outcome.succeeded is True
    assert "successfully" in outcome.message


def test_run_installation_reports_a_nonzero_exit_code():
    outcome = run_installation(
        _valid_state().to_config(), RecordingInstaller(returncode=7)
    )
    assert outcome.succeeded is False
    assert "7" in outcome.message


def test_run_installation_turns_a_raised_error_into_a_message():
    """The whole reason this function exists: it runs on a worker thread,
    where an escaping exception reaches sys.excepthook and is shown to
    nobody - leaving the window claiming the installation just started."""
    outcome = run_installation(
        _valid_state().to_config(),
        RecordingInstaller(exception=RuntimeError("Could not run archinstall: boom")),
    )
    assert outcome.succeeded is False
    assert "Could not run archinstall: boom" in outcome.message


def test_run_installation_keeps_a_post_install_warning_out_of_the_verdict():
    """A warning is only ever raised after archinstall reported success,
    so the installation did happen. Calling that a failure would invite a
    second erase of a machine that is already installed."""
    outcome = run_installation(
        _valid_state().to_config(),
        RecordingInstaller(warnings=["The wireless profile is missing."]),
    )
    assert outcome.succeeded is True
    assert "successfully" in outcome.message
    assert "The wireless profile is missing." in outcome.message


def test_run_installation_passes_the_log_path_through(tmp_path):
    """An explicit path, not default_log_path(): that function now hands
    back a fresh, unpredictable path on every call (see below), so
    comparing two of its results would compare two different files."""
    installer = RecordingInstaller()
    log_path = tmp_path / "install.log"
    run_installation(_valid_state().to_config(), installer, log_path=log_path)
    assert installer.log_path == log_path


def test_run_installation_says_the_disk_is_untouched_after_a_refusal():
    """A refusal is raised before archinstall is ever invoked. That is the
    one thing the user cannot see for themselves once the progress page is
    up, and the one moment it can be stated truthfully."""
    outcome = run_installation(
        _valid_state().to_config(),
        RecordingInstaller(exception=InstallationRefused("BIOS mode")),
    )
    assert outcome.succeeded is False
    assert "Nothing on the disk" in outcome.message
    assert "/dev/vda" in outcome.message


def test_run_installation_claims_nothing_about_the_disk_for_other_failures():
    """A failure that is not a refusal may have happened with archinstall
    already partitioning. Claiming an untouched disk there would be a
    dangerous claim, so nothing is claimed at all."""
    outcome = run_installation(
        _valid_state().to_config(),
        RecordingInstaller(exception=RuntimeError("the run died halfway through")),
    )
    assert outcome.succeeded is False
    assert "the run died halfway through" in outcome.message
    assert "Nothing on the disk" not in outcome.message


# --- where archinstall's output is collected ---------------------------


def test_default_log_path_is_unpredictable_and_private():
    """A fixed /tmp/zepos-install.log is opened "w" by a root process in a
    world-writable sticky directory: anyone can plant a symlink under that
    name first and have root truncate whatever it points at. A directory
    of its own, created 0700 under a name nobody can guess, closes both
    halves of that."""
    first = default_log_path()
    second = default_log_path()
    try:
        assert first != second, "a predictable name is the whole problem"
        assert first.parent != Path(tempfile.gettempdir())
        assert stat.S_IMODE(first.parent.stat().st_mode) == 0o700
        assert first.name.endswith(".log")
    finally:
        first.parent.rmdir()
        second.parent.rmdir()


def test_default_log_path_is_ready_to_be_written_to():
    """The directory has to exist by the time install() opens the file -
    installer.core.runner._run_archinstall() opens it directly and does
    not create parents."""
    path = default_log_path()
    try:
        path.write_text("Formatting /dev/vda2\n", encoding="utf-8")
        assert LogTail(path).read_new() == "Formatting /dev/vda2\n"
    finally:
        path.unlink()
        path.parent.rmdir()


# --- LogTail: the only progress the user gets --------------------------


def test_log_tail_returns_nothing_for_a_file_that_does_not_exist(tmp_path):
    """The normal state for the first fraction of a second after the
    installation starts. No log is a reason to show less, never to
    interrupt an installation."""
    assert LogTail(tmp_path / "absent.log").read_new() == ""


def test_log_tail_returns_only_what_was_added_since_the_last_read(tmp_path):
    log = tmp_path / "install.log"
    log.write_text("Formatting /dev/vda2\n", encoding="utf-8")
    tail = LogTail(log)
    assert tail.read_new() == "Formatting /dev/vda2\n"
    assert tail.read_new() == ""
    with log.open("a", encoding="utf-8") as handle:
        handle.write("Installing base\n")
    assert tail.read_new() == "Installing base\n"


def test_log_tail_survives_undecodable_bytes(tmp_path):
    """archinstall draws progress bars; a chunk read mid-character must
    not raise inside the GTK main loop."""
    log = tmp_path / "install.log"
    log.write_bytes(b"partition \xff\xfe done\n")
    assert "partition" in LogTail(log).read_new()


# --- die Verschluesselungsseite ---------------------------------------
#
# Was hier NICHT geprueft wird: dass ein Haken einen Haken setzt. Was
# geprueft wird: dass ein gesetzter Haken ohne brauchbare Passphrase die
# Seite ANHAELT. Der Unterschied ist der ganze Punkt - archinstall macht
# aus einer Verschluesselung ohne Passphrase eine unverschluesselte
# Installation mit Rueckgabewert 0, und die einzige Stelle, an der das
# noch auffallen kann, ist diese Seite.


def test_encryption_is_on_by_default():
    """Der Nutzer am 12.08.2026: "von anfang an", "immer". Eine Vorgabe
    ist das, was die meisten Installationen bekommen, also muss die
    Vorgabe die sichere sein."""
    assert PageState().encrypt is True


def test_the_default_state_cannot_be_clicked_past():
    """Und die Kehrseite davon, die aus der Vorgabe eine Entscheidung
    macht statt einer Falle: mit dem Haken und ohne Passphrase ist die
    Seite ungueltig. Wer stumpf durchdrueckt, kommt nicht vorbei - er
    muss eine Passphrase eingeben oder den Haken bewusst wegnehmen."""
    state = PageState()
    assert state.is_page_valid("verschluesselung") is False
    assert state.page_error("verschluesselung")


def test_a_short_passphrase_holds_the_page():
    state = _valid_state()
    state.encryption_passphrase = "kurz"
    state.encryption_passphrase_confirm = "kurz"
    assert state.is_page_valid("verschluesselung") is False
    assert "too short" in state.page_error("verschluesselung")


def test_a_mistyped_repeat_holds_the_page():
    """Der Fehler, den eine verdeckte Eingabe nicht zeigt - und der bei
    dieser Passphrase eine Platte kostet statt eines Anmeldeversuchs."""
    state = _valid_state()
    state.encryption_passphrase_confirm = "etwas-ganz-anderes"
    assert state.is_page_valid("verschluesselung") is False
    assert "not match" in state.page_error("verschluesselung")


def test_a_good_passphrase_releases_the_page():
    assert _valid_state().is_page_valid("verschluesselung") is True


def test_switching_encryption_off_releases_the_page_with_empty_fields():
    """Eine Vorgabe, die sich nicht abwaehlen laesst, ist keine
    Vorgabe."""
    state = _valid_state()
    state.encrypt = False
    state.encryption_passphrase = ""
    state.encryption_passphrase_confirm = ""
    assert state.is_page_valid("verschluesselung") is True
    assert state.page_error("verschluesselung") == ""


def test_a_state_without_encryption_is_valid_too():
    state = _valid_state()
    state.encrypt = False
    state.encryption_passphrase = ""
    state.encryption_passphrase_confirm = ""
    assert validate(state.to_config()) == []
    assert state.to_config().disk.encrypt is False


def test_the_passphrase_reaches_the_config():
    cfg = _valid_state().to_config()
    assert cfg.disk.encrypt is True
    assert cfg.disk.passphrase == "eine-lange-passphrase"


def test_a_passphrase_typed_and_then_unticked_does_not_travel():
    """Sonst stuende sie im Klartext in einer InstallConfig, die niemand
    mehr benutzt - und ein spaeterer Leser dieses Feldes koennte daraus
    schliessen, es sei doch verschluesselt worden."""
    state = _valid_state()
    state.encrypt = False
    cfg = state.to_config()
    assert cfg.disk.encrypt is False
    assert cfg.disk.passphrase == ""


def test_the_page_carries_the_warning_before_anything_else():
    """Die Reihenfolge ist die Aussage: app.py stellt den ersten Eintrag
    rot heraus und haengt den Rest darunter. Steht die Warnung nicht
    vorn, ist sie eine Auskunft unter Auskunften."""
    notes = _valid_state().encryption_notes()
    assert notes
    assert notes[0] == loss_warning()


def test_the_page_says_what_encryption_costs():
    notes = _valid_state().encryption_notes()
    assert unlock_note() in notes
    assert keyboard_note() in notes


def test_the_aes_warning_is_a_field_and_not_a_measurement():
    """Ob diese CPU AES in Hardware kann, steht in /proc/cpuinfo - und
    dieses Modul fasst kein Dateisystem an (siehe seinen Kopf). app.py
    fragt einmal und legt den fertigen Satz hier ab, genau wie bei
    firmware_error.

    Der Standardwert ist deshalb LEER und nicht das Ergebnis einer
    Messung: waere hier ein Aufruf, kaeme die Antwort von der Maschine,
    die die Tests laeuft, und die Seite haette eine Abhaengigkeit, die
    kein Aufrufer setzen kann.
    """
    assert PageState().accelerator_warning == ""
    assert _valid_state().accelerator_warning not in _valid_state().encryption_notes()


def test_the_aes_warning_appears_once_it_is_set():
    state = _valid_state()
    state.accelerator_warning = "diese CPU kann kein AES"
    notes = state.encryption_notes()
    assert "diese CPU kann kein AES" in notes
    # Hinter der Warnung und den zwei Kostenhinweisen, vor dem, was offen
    # bleibt: es ist eine Auskunft ueber diese Maschine, keine Warnung.
    assert notes.index("diese CPU kann kein AES") > notes.index(loss_warning())


def test_the_page_names_what_stays_readable():
    """Die EFI-Systempartition bleibt offen, und das muss dastehen -
    sonst wundert sich jemand spaeter, warum eine "vollverschluesselte"
    Platte einen lesbaren Anfang hat."""
    notes = _valid_state().encryption_notes()
    assert any("EFI" in note for note in notes)


def test_the_page_speaks_about_the_layout_that_will_be_installed():
    """Ueber effective_layout() und nicht ueber state.layout: wenn
    niemand eine Einteilung geplant hat, wird der Vorschlag installiert,
    und die Seite muss ueber DEN reden."""
    state = _valid_state()
    state.layout = []
    assert state.encryption_layout()
    assert any("EFI" in note for note in state.encryption_notes())


def test_no_notes_at_all_once_encryption_is_off():
    """app.py leert daraufhin beide Beschriftungen. Eine Warnung, die
    immer dasteht, wird nicht mehr gelesen."""
    state = _valid_state()
    state.encrypt = False
    assert state.encryption_error() == ""


def test_the_confirmation_repeats_the_warning():
    """Der letzte Augenblick, in dem "ich habe sie nirgends notiert" noch
    ein korrigierbarer Zustand ist."""
    body = confirmation_body("/dev/vda", encrypt=True)
    assert loss_warning() in body


def test_the_confirmation_says_nothing_about_encryption_when_there_is_none():
    body = confirmation_body("/dev/vda", encrypt=False)
    assert loss_warning() not in body
    assert "/dev/vda" in body


def test_the_confirmation_still_names_the_disk_and_the_partitions():
    """Die Warnung darf das nicht verdraengen: der Geraetename und die
    Aufzaehlung dessen, was verlorengeht, sind der Grund, aus dem es
    diese Rueckfrage gibt."""
    body = confirmation_body(
        "/dev/vda",
        existing=WINDOWS_DISK.partitions,
        layout=suggested_layout(20 * 1024 ** 3),
        encrypt=True)
    assert "/dev/vda" in body
    assert "Windows" in body
    assert loss_warning() in body
