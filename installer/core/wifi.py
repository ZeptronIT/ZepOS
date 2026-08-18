# SPDX-License-Identifier: GPL-3.0-or-later
"""Wireless scanning and association for the live environment.

Sits behind a protocol so the iwctl implementation can later be replaced
by iwd's D-Bus interface without touching any caller. iwctl emits ANSI
colour codes and table headers, both of which are stripped here.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from .i18n import _
from .source import internet_reachable

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_SEPARATOR = re.compile(r"^-+$")

# The SSID group is greedy on purpose: the security keyword is the
# second-to-last column, so the LAST occurrence is the real one. That keeps
# an SSID such as "psk cafe wifi" from being cut at its own first word.
# A single space is enough of a separator - requiring two silently dropped
# long SSIDs, which iwctl renders with a narrow gap.
_NETWORK_LINE = re.compile(
    r"^(?P<ssid>.+)\s+(?P<security>psk|open|8021x|wep)\s*(?P<signal>\S*)\s*$"
)

Runner = Callable[..., subprocess.CompletedProcess]


@dataclass(frozen=True)
class Network:
    ssid: str
    signal: int
    secured: bool


class WifiBackend(Protocol):
    def devices(self) -> list[str]: ...
    def scan(self, device: str) -> None: ...
    def networks(self, device: str) -> list[Network]: ...
    def connect(self, device: str, ssid: str, passphrase: str) -> None: ...


class IwctlBackend:
    def __init__(self, *, runner: Runner | None = None) -> None:
        # Resolved at call time, not bound as a default - see passwords.py.
        self._run = runner or subprocess.run

    def _iwctl(self, *args: str, secret: str | None = None) -> str:
        """Run iwctl and return its output, or raise with what it said.

        `secret` is a value that must never appear in a message, even if
        iwctl echoes it back.
        """
        def _safe(text: str) -> str:
            """What iwctl said, fit to show a person.

            ANSI first: iwctl colours its output, and those escapes used
            to reach the screen as the "strange characters" a failed
            connection was reported with. They were stripped from the
            SUCCESS path only - one line below where the failure path
            needed them.
            """
            text = _ANSI.sub("", text)
            if secret:
                text = text.replace(secret, "***")
            return text.strip()

        try:
            result = self._run(
                ["iwctl", *args],
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            # iwctl missing or not executable, e.g. a damaged live image.
            # Reachable by the user, so it must be translated.
            raise RuntimeError(
                _("Could not run iwctl: {reason}").format(reason=_safe(str(exc)))
            ) from exc
        if result.returncode != 0:
            # Covers every iwctl failure, including a wrong passphrase on
            # connect() - the single most likely error in the installer,
            # and entirely the user's to correct. Must be translated.
            raise RuntimeError(
                _("iwctl {args} failed: {reason}").format(
                    args=_safe(" ".join(args)),
                    reason=_safe(result.stderr or result.stdout),
                )
            )
        return _ANSI.sub("", result.stdout)

    @staticmethod
    def _body(output: str) -> list[str]:
        """Drop ANSI, banners, separators and the column header row."""
        lines = [_ANSI.sub("", line).rstrip() for line in output.splitlines()]
        separators = [i for i, line in enumerate(lines) if _SEPARATOR.match(line.strip())]
        if not separators:
            # No table at all - iwctl said something else entirely ("no
            # wireless adapter", an error banner). Treating those lines as
            # data would invent device names like "No" and feed them back
            # into later iwctl calls.
            return []
        return [line for line in lines[separators[-1] + 1:] if line.strip()]

    def devices(self) -> list[str]:
        out = self._iwctl("device", "list")
        return [line.split()[0] for line in self._body(out)]

    def scan(self, device: str) -> None:
        self._iwctl("station", device, "scan")

    def networks(self, device: str) -> list[Network]:
        out = self._iwctl("station", device, "get-networks")
        found: list[Network] = []
        for line in self._body(out):
            stripped = line.lstrip()
            if stripped.startswith(">"):
                stripped = stripped[1:].lstrip()
            match = _NETWORK_LINE.match(stripped)
            if not match:
                # Not a network row (banner, stray text). Nothing to show.
                continue
            ssid = match.group("ssid").strip()
            signal = match.group("signal") or ""
            found.append(
                Network(
                    ssid=ssid,
                    # Count asterisks rather than requiring them. If iwctl
                    # ever renders signal with a different glyph, the network
                    # must still appear in the list - a user who cannot see
                    # their network is worse off than one seeing signal 0.
                    signal=signal.count("*"),
                    secured=match.group("security") != "open",
                )
            )
        return sorted(found, key=lambda n: n.signal, reverse=True)

    # Where iwd keeps what it knows about a network. It watches this
    # directory, so a file written here is picked up without restarting
    # anything.
    CREDENTIALS = Path("/var/lib/iwd")

    @staticmethod
    def credentials_name(ssid: str) -> str:
        """iwd's own file name for an SSID.

        Its rule, from iwd.network(5): a name made only of characters
        that are safe in a file name is used as it is; anything else is
        written as "=" followed by the SSID's bytes in hex. "FRITZ!Box
        7590" has a space and a "!" in it, so it takes the second form -
        which is most home networks, and the reason this is a function
        rather than an f-string at the call site.
        """
        if ssid and all(c.isalnum() or c in "-_" for c in ssid):
            return ssid
        return "=" + ssid.encode("utf-8").hex()

    def connect(self, device: str, ssid: str, passphrase: str) -> None:
        """Join a network.

        WHY THE PASSPHRASE GOES INTO A FILE
            It used to go on stdin, and that never worked: iwctl does
            not read a passphrase from its standard input, it asks the
            TERMINAL for one, so a piped answer is never seen. What the
            pipe produced was a failure carrying iwctl's own prompt as
            the error text - reported from the medium as "network
            failed" followed by "Type the network passphrase for <ssid>
            psk" and a run of escape characters, on the first try, with
            the right password.

            --passphrase on the command line would work and is what the
            manual page offers, but a command line is readable by every
            process on the machine for as long as it runs. iwd's own
            credentials file needs neither a terminal nor an argument:
            it is written 0600, iwd notices it, and `connect` then has
            nothing to ask.

        WHAT IS LEFT BEHIND
            The file stays in the live system's /var/lib/iwd, which is a
            RAM overlay and gone at the next boot. It is not what puts
            the network into the installed system - runner.py writes a
            NetworkManager profile into the target for that, and checks
            its mode.
        """
        path = self.CREDENTIALS / f"{self.credentials_name(ssid)}.psk"
        try:
            self.CREDENTIALS.mkdir(parents=True, exist_ok=True)
            # os.open with the mode, not open() then chmod: the second
            # leaves the file readable for as long as it takes to run
            # the next line.
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(f"[Security]\nPassphrase={passphrase}\n")
        except OSError as exc:
            raise RuntimeError(
                _("Could not store the wireless passphrase: {reason}")
                .format(reason=exc)
            ) from exc

        self._iwctl("station", device, "connect", ssid, secret=passphrase)


@dataclass(frozen=True)
class Connection:
    """The outcome of one association attempt.

    `connected` says whether the live session is actually on the network,
    and is the only thing a surface may gate on. `message` is what to
    tell the user, and can be non-empty while `connected` is True: a
    network that associates but has no route out is a warning, not a
    reason to refuse. Refusing there would block precisely the case ZepOS
    carries an offline repository for.
    """

    connected: bool
    message: str


def _internet_reachable() -> bool:
    """Whether the live session can reach the outside world.

    Resolved by associate() at call time and never bound as a default
    argument, so a caller (or a test) can replace it - this one opens a
    real socket.

    It used to be `probe() is PackageSource.ONLINE`, and that stopped
    being the same question the day probe() started asking about the
    ZepOS repository instead of about the network. The repository is not
    published, so this would now report "no internet" to every user who
    had just successfully joined a working WLAN - sending them to look
    for a fault in their own network. source.internet_reachable() is the
    original socket check, kept under the name of the thing it measures.
    """
    return internet_reachable()


def _refresh_before_connecting(
    backend: WifiBackend,
    device: str,
    ssid: str,
    *,
    budget: float = 6.0,
    poll: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Put the network back into iwd's current scan results.

    MEASURED ON THE MEDIUM, and reported as: the first attempt says the
    network is unknown, the second one - same network, same password -
    connects.

    iwd will only join a network it can see in its CURRENT scan results,
    and the installer had scanned exactly once, while the window was
    being built. By the time somebody has read the page, chosen a
    network and typed a passphrase, those results have aged out; the
    first connect is refused, iwd scans again on its own, and the second
    attempt therefore works. The retry was not fixing anything - it was
    waiting for the scan the installer never asked for.

    NOT AN ERROR IF THE NAME NEVER APPEARS. A hidden network does not
    broadcast one, so it is absent from every scan by definition - and
    the page offers "Other network" precisely so it can be typed. This
    refreshes what it can and then gets out of the way; deciding whether
    the network exists is iwd's job, and it says so in its own words.
    """
    try:
        backend.scan(device)
    except (RuntimeError, FileNotFoundError):
        # A scan that cannot be started is not a reason to skip the
        # attempt: the results may still be fresh enough.
        return

    waited = 0.0
    while waited < budget:
        try:
            if any(network.ssid == ssid for network in backend.networks(device)):
                return
        except (RuntimeError, FileNotFoundError):
            return
        sleep(poll)
        waited += poll


def _wait_for_internet(
    verify: Callable[[], bool],
    *,
    budget: float = 20.0,
    poll: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    """Give the address time to arrive before deciding there is none.

    REPORTED FROM THE MEDIUM: "wlan netzwerkxxx verbunden aber es wurde
    keine verbindung zum internet gefunden".

    Two things were wrong and this is the second. The first was that
    nothing on the medium ever asked for an IP address - iwd.service was
    the only network daemon and its own network configuration is off
    unless a file turns it on; iso/profile-release/airootfs/etc/iwd/
    main.conf now does.

    This is the half that remains once an address CAN arrive: it does
    not arrive instantly. Associating is fast, DHCP is a conversation -
    a discover, an offer, a request, an acknowledgement, and on a busy
    home network several seconds. Asking one second later and reporting
    "no internet" would send a user to look for a fault in a network
    that was about to work.

    Twenty seconds, checked every second, and the FIRST check happens
    immediately: a machine already on the network - one that was
    connected before the installer started - answers at once and waits
    for nothing.
    """
    waited = 0.0
    while True:
        if verify():
            return True
        if waited >= budget:
            return False
        sleep(poll)
        waited += poll


def associate(
    backend: WifiBackend,
    ssid: str,
    passphrase: str,
    *,
    verify: Callable[[], bool] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Connection:
    """Join a wireless network in the live session and check the result.

    Spec §8.2 step 2 is "WLAN suchen, verbinden, Verbindung pruefen".
    Until this was called, connect() existed, was specified and was unit
    tested - and no surface ever invoked it. The consequence on
    wireless-only hardware: the live session never joined anything, the
    collected passphrase only ever reached the TARGET system's profile,
    probe() therefore always reported no network, and every installation
    silently took the offline path - on exactly the hardware the wireless
    step exists for.

    Never raises. Every failure - no adapter, a missing iwctl, a wrong
    passphrase - comes back as a Connection carrying a message meant for
    the user, because a wrong passphrase is the most likely error in the
    whole installer and entirely theirs to correct.
    """
    verify = verify or _internet_reachable
    try:
        devices = backend.devices()
        if not devices:
            return Connection(False, _("No wireless adapter was found."))
        device = devices[0]
        _refresh_before_connecting(backend, device, ssid, sleep=sleep)
        backend.connect(device, ssid, passphrase)
    except (RuntimeError, FileNotFoundError) as exc:
        return Connection(False, str(exc))

    if not _wait_for_internet(verify, sleep=sleep):
        return Connection(
            True,
            _("Connected to {ssid}, but no connection to the internet was found. The installation continues from the offline package source.")
            .format(ssid=ssid),
        )
    return Connection(True, "")
