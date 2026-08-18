# SPDX-License-Identifier: GPL-3.0-or-later
import stat
import subprocess

import pytest

from installer.core.wifi import Connection, IwctlBackend, Network, associate

GET_NETWORKS_OUTPUT = (
    "\x1b[0m                               Available networks\n"
    "--------------------------------------------------------------------\n"
    "      Network name                    Security            Signal\n"
    "--------------------------------------------------------------------\n"
    "  >   FRITZ!Box 7590                  psk                 ****\n"
    "      Nachbar-WLAN                    psk                 **\n"
    "      Gastnetz                        open                ***\n"
)

DEVICE_LIST_OUTPUT = (
    "                                 Devices\n"
    "--------------------------------------------------------------------\n"
    "      Name        Address            Powered    Adapter    Mode\n"
    "--------------------------------------------------------------------\n"
    "      wlan0       aa:bb:cc:dd:ee:ff  on         phy0       station\n"
)


def _runner(stdout: str, returncode: int = 0):
    def run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")
    return run


def test_devices_are_parsed():
    backend = IwctlBackend(runner=_runner(DEVICE_LIST_OUTPUT))
    assert backend.devices() == ["wlan0"]


def test_networks_are_parsed_without_ansi_or_headers():
    backend = IwctlBackend(runner=_runner(GET_NETWORKS_OUTPUT))
    nets = backend.networks("wlan0")
    assert Network(ssid="FRITZ!Box 7590", signal=4, secured=True) in nets
    assert Network(ssid="Gastnetz", signal=3, secured=False) in nets
    assert all("Network name" not in n.ssid for n in nets)
    assert all("\x1b" not in n.ssid for n in nets)


def test_networks_are_sorted_by_signal_strength():
    backend = IwctlBackend(runner=_runner(GET_NETWORKS_OUTPUT))
    signals = [n.signal for n in backend.networks("wlan0")]
    assert signals == sorted(signals, reverse=True)


def test_connect_passes_passphrase_out_of_argv(tmp_path, monkeypatch):
    """The passphrase must not be readable by other processes.

    A command line is world-readable through `ps` for as long as the
    command runs, so --passphrase is out even though iwctl offers it.

    This test used to also require the passphrase on stdin, which was
    the mechanism at the time and did not work: iwctl asks the TERMINAL
    for a passphrase, never its standard input, so on the medium the
    connection failed on the first try with the right password and
    iwctl's own prompt as the error text. The protection is unchanged
    and now stronger - the file it goes into is checked for its mode as
    well - while the mechanism underneath it is one that works.
    """
    seen = {}

    def run(cmd, **kw):
        seen["cmd"] = cmd
        seen["input"] = kw.get("input")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(IwctlBackend, "CREDENTIALS", tmp_path / "iwd")
    IwctlBackend(runner=run).connect("wlan0", "FRITZ!Box 7590", "wlanpw")

    assert "wlanpw" not in " ".join(seen["cmd"])
    assert seen["input"] is None, "the passphrase must not go to stdin either"

    stored = tmp_path / "iwd" / (
        "=" + "FRITZ!Box 7590".encode("utf-8").hex() + ".psk")
    assert stored.is_file(), (
        f"iwd has no credentials file; {sorted((tmp_path / 'iwd').iterdir())}")
    assert "Passphrase=wlanpw" in stored.read_text(encoding="utf-8")
    assert stat.S_IMODE(stored.stat().st_mode) == 0o600, (
        "the file holding a passphrase is readable by somebody else")


def test_a_plain_ssid_keeps_its_own_name():
    """iwd only hex-encodes a name it could not use as a file name."""
    assert IwctlBackend.credentials_name("Zeptron_5G-2") == "Zeptron_5G-2"


def test_an_ssid_with_a_space_is_hex_encoded():
    """Most home networks. iwd would not find a file called
    "FRITZ!Box 7590.psk", so writing one is the same as writing none."""
    assert IwctlBackend.credentials_name("FRITZ!Box 7590") == (
        "=" + "FRITZ!Box 7590".encode("utf-8").hex())


def test_the_error_text_carries_no_escape_codes_and_no_passphrase():
    """What reached the screen on the medium: iwctl's prompt, in colour.

    The escapes were stripped from the SUCCESS path only, one line below
    where the failure path needed them. And now that the passphrase is
    handled by this method, a message must not be able to repeat it.
    """
    noisy = "\x1b[1;31mType the network passphrase for X psk\x1b[0m geheim123"

    def run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, stdout=noisy, stderr="")

    backend = IwctlBackend(runner=run)
    with pytest.raises(RuntimeError) as caught:
        backend._iwctl("station", "wlan0", "connect", "X", secret="geheim123")

    message = str(caught.value)
    assert "\x1b" not in message, f"escape codes reached the user: {message!r}"
    assert "geheim123" not in message, "the passphrase is in the error text"
    assert "***" in message


def test_connect_raises_on_failure(tmp_path, monkeypatch):
    """CREDENTIALS is redirected because connect() now writes the
    passphrase into iwd's directory before it calls iwctl, and
    tests/conftest.py refuses a test that would touch /var/lib."""
    monkeypatch.setattr(IwctlBackend, "CREDENTIALS", tmp_path / "iwd")
    backend = IwctlBackend(runner=_runner("Operation failed", returncode=1))
    with pytest.raises(RuntimeError):
        backend.connect("wlan0", "FRITZ!Box 7590", "falsch")


def test_missing_iwctl_raises():
    """If the iwctl binary is missing, FileNotFoundError is raised before any
    CompletedProcess exists - it must be caught explicitly, not inferred
    from a returncode."""
    def run(cmd, **kw):
        raise FileNotFoundError("iwctl: not found")

    backend = IwctlBackend(runner=run)
    with pytest.raises(RuntimeError, match="Could not run iwctl"):
        backend.devices()


def test_long_ssid_with_a_narrow_gap_is_not_dropped():
    """iwctl renders a long SSID with less padding. Requiring two spaces
    made those networks invisible."""
    out = (
        "                               Available networks\n"
        "--------------------------------------------------------------------\n"
        "      Network name                    Security            Signal\n"
        "--------------------------------------------------------------------\n"
        "      EinSehrLangerNetzwerkNameHier psk ****\n"
    )
    nets = IwctlBackend(runner=_runner(out)).networks("wlan0")
    assert [n.ssid for n in nets] == ["EinSehrLangerNetzwerkNameHier"]


def test_ssid_containing_a_security_keyword_survives():
    out = (
        "--------------------------------------------------------------------\n"
        "      psk cafe wifi                   open                **\n"
    )
    nets = IwctlBackend(runner=_runner(out)).networks("wlan0")
    assert nets[0].ssid == "psk cafe wifi"
    assert nets[0].secured is False


def test_unknown_signal_glyph_keeps_the_network_visible():
    """Signal 0 is acceptable. An invisible network is not."""
    out = (
        "--------------------------------------------------------------------\n"
        "      Nachbarnetz                     psk                 XXX\n"
    )
    nets = IwctlBackend(runner=_runner(out)).networks("wlan0")
    assert [(n.ssid, n.signal) for n in nets] == [("Nachbarnetz", 0)]


def test_no_table_yields_no_devices():
    """A non-tabular reply must not be mistaken for data - otherwise the
    device 'No' gets fed into the next iwctl call."""
    out = "No wireless adapter found\n"
    assert IwctlBackend(runner=_runner(out)).devices() == []


def test_empty_network_list_is_not_an_error():
    out = (
        "--------------------------------------------------------------------\n"
        "      Network name                    Security            Signal\n"
        "--------------------------------------------------------------------\n"
    )
    assert IwctlBackend(runner=_runner(out)).networks("wlan0") == []


def test_scan_invokes_iwctl_for_the_given_device():
    """scan() had no coverage at all."""
    seen = {}

    def run(cmd, **kw):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    IwctlBackend(runner=run).scan("wlan0")
    assert seen["cmd"] == ["iwctl", "station", "wlan0", "scan"]


# --- associate(): the step no surface used to perform ------------------


class FakeBackend:
    """A WifiBackend whose connect() records instead of shelling out."""

    def __init__(self, devices=("wlan0",), error=None):
        self._devices = list(devices)
        self._error = error
        self.connected = []

    def devices(self):
        return list(self._devices)

    def scan(self, device):
        raise NotImplementedError

    def networks(self, device):
        raise NotImplementedError

    def connect(self, device, ssid, passphrase):
        if self._error is not None:
            raise self._error
        self.connected.append((device, ssid, passphrase))


def test_associate_joins_the_network_and_reports_success():
    backend = FakeBackend()
    result = associate(backend, "FRITZ!Box", "wlanpw", verify=lambda: True, sleep=lambda _s: None)
    assert backend.connected == [("wlan0", "FRITZ!Box", "wlanpw")]
    assert result == Connection(True, "")


def test_associate_reports_a_wrong_passphrase_instead_of_raising():
    """The most likely error in the whole installer, and entirely the
    user's to correct - so it has to come back as something a surface can
    show, not as an exception nobody catches."""
    backend = FakeBackend(error=RuntimeError("iwctl station wlan0 connect failed: invalid key"))
    result = associate(backend, "FRITZ!Box", "wrongpw", verify=lambda: True, sleep=lambda _s: None)
    assert result.connected is False
    assert "invalid key" in result.message


def test_associate_reports_a_machine_without_a_wireless_adapter():
    result = associate(FakeBackend(devices=()), "FRITZ!Box", "pw", verify=lambda: True, sleep=lambda _s: None)
    assert result.connected is False
    assert "adapter" in result.message


def test_associate_survives_a_missing_iwctl():
    backend = FakeBackend(error=FileNotFoundError(2, "No such file", "iwctl"))
    result = associate(backend, "FRITZ!Box", "pw", verify=lambda: True, sleep=lambda _s: None)
    assert result.connected is False


def test_a_network_without_internet_is_a_warning_not_a_refusal():
    """Associated, but no route out. Refusing here would block exactly
    the case ZepOS carries an offline repository for."""
    result = associate(FakeBackend(), "FRITZ!Box", "wlanpw", verify=lambda: False, sleep=lambda _s: None)
    assert result.connected is True
    assert "FRITZ!Box" in result.message


def test_the_connection_is_verified_and_not_assumed():
    """Spec 8.2 step 2 is "suchen, verbinden, Verbindung pruefen" - the
    check is a third step, not an assumption that connect() returning
    means anything."""
    checked = []
    associate(FakeBackend(), "FRITZ!Box", "wlanpw", verify=lambda: checked.append(1) or True)
    assert checked == [1]


# --- die Suche vor dem Verbinden -------------------------------------------


class RecordingBackend:
    """Records the order of calls, and can make the SSID appear late.

    `appears_after` is how many networks() calls happen before the name
    is in the results - which is what a scan settling looks like from
    the outside.
    """

    def __init__(self, *, appears_after: int = 0, ssid: str = "Zeptron"):
        self.calls: list[str] = []
        self.reads = 0
        self._appears_after = appears_after
        self._ssid = ssid

    def devices(self):
        self.calls.append("devices")
        return ["wlan0"]

    def scan(self, device):
        self.calls.append("scan")

    def networks(self, device):
        self.calls.append("networks")
        self.reads += 1
        if self.reads > self._appears_after:
            return [Network(ssid=self._ssid, signal=5, secured=True)]
        return []

    def connect(self, device, ssid, passphrase):
        self.calls.append("connect")


def test_the_network_is_scanned_for_again_before_connecting():
    """The bug from the medium: first attempt "network unknown", second
    one connects.

    iwd joins only what is in its CURRENT scan results, and the
    installer scanned once while the window was being built. By the time
    a passphrase has been typed those results have aged out. The retry
    was not fixing anything; it was waiting for the scan nobody asked
    for.
    """
    backend = RecordingBackend()

    associate(backend, "Zeptron", "geheim", verify=lambda: True,
              sleep=lambda _s: None)

    assert "scan" in backend.calls, (
        "connect() was called without asking for a fresh scan first")
    assert backend.calls.index("scan") < backend.calls.index("connect")


def test_it_waits_for_the_name_to_appear_in_the_results():
    """A scan takes seconds and the answer arrives channel by channel."""
    backend = RecordingBackend(appears_after=3)

    associate(backend, "Zeptron", "geheim", verify=lambda: True,
              sleep=lambda _s: None)

    assert "connect" in backend.calls
    assert backend.reads >= 4, (
        f"stopped reading after {backend.reads} tries, before the network "
        "had appeared")


def test_a_hidden_network_is_still_attempted():
    """A hidden network broadcasts no name, so it is in no scan result
    ever - and the page offers "Other network" exactly so it can be
    typed. Waiting for it to appear must not turn into refusing it."""
    backend = RecordingBackend(ssid="etwas anderes")

    result = associate(backend, "Unsichtbar", "geheim", verify=lambda: True,
                       sleep=lambda _s: None)

    assert "connect" in backend.calls, (
        "a hidden network was never even attempted")
    assert result.connected


def test_the_wait_for_the_scan_is_bounded():
    """The name never appears, so only the budget can end this."""
    backend = RecordingBackend(ssid="etwas anderes")
    slept: list[float] = []

    associate(backend, "Unsichtbar", "geheim", verify=lambda: True,
              sleep=slept.append)

    assert sum(slept) <= 7.0, f"waited {sum(slept)}s for a scan"


# --- die Adresse braucht Zeit ----------------------------------------------


def test_the_first_check_for_internet_happens_immediately():
    """A machine already on the network must not wait for anything."""
    slept: list[float] = []

    result = associate(FakeBackend(), "FRITZ!Box", "pw",
                       verify=lambda: True, sleep=slept.append)

    assert result.connected and result.message == ""
    assert slept == [], "waited although the network was already up"


def test_it_keeps_checking_while_the_address_arrives():
    """Associating is fast, DHCP is a conversation.

    REPORTED FROM THE MEDIUM: "verbunden aber es wurde keine verbindung
    zum internet gefunden". Asking one second after the association and
    reporting no internet sends a user to look for a fault in a network
    that was about to work.
    """
    answers = [False, False, False, True]

    result = associate(FakeBackend(), "FRITZ!Box", "pw",
                       verify=lambda: answers.pop(0), sleep=lambda _s: None)

    assert result.connected
    assert result.message == "", (
        f"reported a problem although the address arrived: {result.message}")


def test_the_wait_for_an_address_is_bounded():
    """A network that never routes anywhere is a real outcome - a
    captive portal, a router with no uplink - and the installer has an
    offline package source for exactly that. It must say so rather than
    wait forever."""
    slept: list[float] = []

    result = associate(FakeBackend(), "FRITZ!Box", "pw",
                       verify=lambda: False, sleep=slept.append)

    assert result.connected, "the association itself did work"
    assert "internet" in result.message.lower()
    assert sum(slept) <= 21.0, f"waited {sum(slept)}s"
