# SPDX-License-Identifier: GPL-3.0-or-later
"""Carry the live environment's wireless credentials into the target.

Associating with a network in the live session does not give the
installed system network access. Without this profile, a freshly
installed laptop with no ethernet port reboots into a system that has
no way to get online, even though the installer knew the credentials
a moment earlier. This module exists to satisfy spec §8.3.
"""
from __future__ import annotations

import os
import re
import stat
import uuid as uuid_module
from pathlib import Path
from typing import Callable

from .i18n import _
from .model import WifiCredentials

PROFILE_DIR = "etc/NetworkManager/system-connections"
PROFILE_SUFFIX = ".nmconnection"

# NAME_MAX on ext4 and most Linux filesystems. A name past this fails
# with OSError at write time; rejecting it up front turns that crash
# into a clear error, and - just as important - stops two SSIDs that
# would truncate to the same on-disk name from silently overwriting
# each other's profile.
_MAX_FILENAME_BYTES = 255

# C0 controls plus DEL. Both the SSID and the passphrase end up
# verbatim inside an INI-style file that NetworkManager parses as
# root. A newline in either field lets whoever controls the value
# inject a forged section - e.g. a second [wifi-security] block
# carrying an attacker's own key - ahead of or instead of the real
# one. An SSID is attacker-influenceable in principle (it is whatever
# an access point broadcasts), so this is rejected outright rather
# than escaped: a genuine SSID or passphrase never contains a control
# character, so anything that does is either a broken access point or
# an attack, and silently rewriting it would connect the user to
# something other than what they picked.
_FORBIDDEN = re.compile(r"[\x00-\x1f\x7f]")


def _safe_filename(ssid: str) -> str:
    """Percent-encode an SSID into a single, injective filesystem path component.

    Only "/" and "%" are encoded, "%" first. "/" is the sole character
    pathlib treats as a path separator, so encoding it guarantees the
    result is always a single path component - "a/../etc" becomes
    "a%2F..%2Fetc", not a traversal. "%" is the escape character this
    encoding itself introduces, so it must be encoded too: otherwise an
    SSID containing the literal text "%2F" would sanitise to the same
    string as one containing a literal "/", and the two would silently
    overwrite each other's profile. Encoding "%" before "/" keeps the
    output from re-escaping the "%" that "/" itself expands into. With
    only those two characters touched, the mapping is injective - two
    different SSIDs always produce two different filenames - while an
    ordinary SSID such as "FRITZ!Box 7590" passes through unchanged.

    Control characters (including NUL) never reach this function:
    write_profile rejects them outright before calling it, via
    _FORBIDDEN.

    A sanitised SSID could still equal "." or ".." on its own, which
    would refer to the profile directory itself or its parent.
    write_profile closes that gap the same way it always has: by always
    appending PROFILE_SUFFIX before the result is used as a filename,
    so the final name can never be exactly "." or ".." - even on the
    (now unreachable, since this encoding never deletes characters)
    chance this function returned an empty string.
    """
    return ssid.replace("%", "%25").replace("/", "%2F")


def write_profile(
    wifi: WifiCredentials,
    target_root: Path,
    *,
    uuid_factory: Callable[[], uuid_module.UUID] = uuid_module.uuid4,
) -> Path:
    """Write a NetworkManager keyfile connection profile under target_root.

    The profile lands at
    <target_root>/etc/NetworkManager/system-connections/<ssid>.nmconnection,
    so the same call serves both a real install (target_root=/mnt) and a
    test (target_root=tmp_path). autoconnect is deliberately "true": the
    whole point of this module is that the installed system joins the
    network by itself on first boot, without the user re-entering the
    passphrase. The [wifi-security] section is written only when a
    passphrase was given, so an open network does not end up with an
    empty psk that NetworkManager would refuse to use.
    """
    if not wifi.ssid:
        raise ValueError(_("Refusing to write a wireless profile without an SSID."))

    if _FORBIDDEN.search(wifi.ssid):
        raise ValueError(_("The wireless network name contains control characters."))
    if _FORBIDDEN.search(wifi.passphrase):
        raise ValueError(_("The wireless password contains control characters."))

    sanitized = _safe_filename(wifi.ssid)
    if not sanitized:
        # A single literal, not two concatenated ones: the source-vs-
        # catalogue completeness check in test_i18n.py extracts msgids
        # with a regex that does not follow Python's implicit string
        # concatenation, so a msgid split across literals would look
        # missing from po/de.po even when it is fully and correctly
        # cataloged.
        raise ValueError(
            _("The wireless network name contains no characters usable in a profile filename.")
        )

    filename = f"{sanitized}{PROFILE_SUFFIX}"
    if len(filename.encode("utf-8")) > _MAX_FILENAME_BYTES:
        raise ValueError(
            _("The wireless network name is too long to use as a profile filename.")
        )

    directory = Path(target_root) / PROFILE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename

    security_section = ""
    if wifi.passphrase:
        security_section = (
            "\n[wifi-security]\n"
            "key-mgmt=wpa-psk\n"
            f"psk={wifi.passphrase}\n"
        )

    content = (
        "[connection]\n"
        f"id={wifi.ssid}\n"
        f"uuid={uuid_factory()}\n"
        "type=wifi\n"
        "autoconnect=true\n"
        "\n"
        "[wifi]\n"
        "mode=infrastructure\n"
        f"ssid={wifi.ssid}\n"
        f"{security_section}"
        "\n"
        "[ipv4]\n"
        "method=auto\n"
        "\n"
        "[ipv6]\n"
        "method=auto\n"
    )

    # The passphrase must never be readable even for the instant between
    # file creation and the chmod below. Narrowing the umask makes the
    # file's initial mode 0600 from the moment write_text() creates it,
    # instead of relying solely on a chmod that runs after the content is
    # already on disk. This still goes through Path.write_text() - the
    # exact method the test suite's isolation guard patches (see
    # tests/conftest.py) - so a test that pointed target_root at a real
    # system path by mistake is still caught. os.open() would create the
    # file through a path the guard does not watch at all.
    previous_umask = os.umask(0o077)
    try:
        path.write_text(content, encoding="utf-8")
    finally:
        os.umask(previous_umask)
    path.chmod(0o600)
    return path


def profile_problem(path: Path) -> str:
    """Check a written profile the way spec §11 requires, and describe
    what is wrong with it - or return "" when it is exactly right.

    Returns a message instead of raising because the only caller runs
    after archinstall already reported success: at that point the machine
    is installed, and an exception would be presented to the user as a
    failed installation.

    A mode other than 0600 is not a formality. The file carries the
    passphrase in clear text, and NetworkManager itself refuses to use a
    keyfile that is readable by anyone but its owner.
    """
    if not path.exists():
        return (
            _("The wireless profile is missing from the installed system: {path}")
            .format(path=path)
        )
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode != 0o600:
        return (
            _("The wireless profile in the installed system is readable by others: {path}")
            .format(path=path)
        )
    return ""
