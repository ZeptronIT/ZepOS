# SPDX-License-Identifier: GPL-3.0-or-later
import configparser
import stat
import uuid

import pytest

from installer.core.model import WifiCredentials
from installer.core.netprofile import profile_problem, write_profile

FIXED = uuid.UUID("12345678-1234-5678-1234-567812345678")


def test_profile_is_written_to_the_expected_path(tmp_path):
    path = write_profile(
        WifiCredentials("FRITZ!Box 7590", "wlanpw"), tmp_path,
        uuid_factory=lambda: FIXED,
    )
    assert path == (
        tmp_path / "etc/NetworkManager/system-connections/FRITZ!Box 7590.nmconnection"
    )
    assert path.exists()


def test_profile_is_only_readable_by_root(tmp_path):
    """NetworkManager ignores profiles that are readable beyond mode 600."""
    path = write_profile(
        WifiCredentials("Fritz", "wlanpw"), tmp_path, uuid_factory=lambda: FIXED
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_profile_contains_ssid_psk_and_autoconnect(tmp_path):
    path = write_profile(
        WifiCredentials("Fritz", "wlanpw"), tmp_path, uuid_factory=lambda: FIXED
    )
    parser = configparser.ConfigParser()
    parser.read(path)
    assert parser["wifi"]["ssid"] == "Fritz"
    assert parser["wifi-security"]["psk"] == "wlanpw"
    assert parser["connection"]["autoconnect"] == "true"
    assert parser["connection"]["type"] == "wifi"
    assert parser["connection"]["uuid"] == str(FIXED)
    assert parser["ipv4"]["method"] == "auto"


def test_slashes_in_ssid_do_not_escape_the_directory(tmp_path):
    path = write_profile(
        WifiCredentials("a/b/../etc", "pw"), tmp_path, uuid_factory=lambda: FIXED
    )
    expected_dir = tmp_path / "etc/NetworkManager/system-connections"
    assert path.parent == expected_dir
    # Percent-encoded, not collapsed: "/" becomes "%2F" rather than "_",
    # so this SSID can no longer collide with a different SSID that
    # happens to contain a literal underscore in the same spot.
    assert path.name == "a%2Fb%2F..%2Fetc.nmconnection"


def test_empty_ssid_is_rejected(tmp_path):
    """Named, not merely raised.

    write_profile() has five ValueError paths and a bare pytest.raises
    cannot tell them apart, so a test can go on passing through a refusal
    that has nothing to do with what it claims to check - which is
    exactly what happened to the one below.
    """
    with pytest.raises(ValueError, match="without an SSID"):
        write_profile(WifiCredentials("", "pw"), tmp_path)


def test_ssid_of_a_single_dot_does_not_escape_the_directory(tmp_path):
    """A sanitised SSID must never end up being exactly '.' - that would
    refer to the profile directory itself rather than a file inside it."""
    path = write_profile(
        WifiCredentials(".", "pw"), tmp_path, uuid_factory=lambda: FIXED
    )
    expected_dir = tmp_path / "etc/NetworkManager/system-connections"
    assert path.parent == expected_dir
    assert path.name not in (".", "..")
    assert path.exists()


def test_ssid_of_double_dot_does_not_escape_the_directory(tmp_path):
    """A sanitised SSID must never end up being exactly '..' - that would
    refer to the parent of the profile directory."""
    path = write_profile(
        WifiCredentials("..", "pw"), tmp_path, uuid_factory=lambda: FIXED
    )
    expected_dir = tmp_path / "etc/NetworkManager/system-connections"
    assert path.parent == expected_dir
    assert path.name not in (".", "..")
    assert path.exists()


def test_leading_dot_ssid_stays_inside_the_directory(tmp_path):
    """A leading dot only makes a hidden file, not an escape: the fixed
    '.nmconnection' suffix guarantees the name is never exactly '.' or
    '..', no matter what the SSID in front of it looks like."""
    path = write_profile(
        WifiCredentials(".hidden-network", "pw"), tmp_path, uuid_factory=lambda: FIXED
    )
    expected_dir = tmp_path / "etc/NetworkManager/system-connections"
    assert path.parent == expected_dir
    assert path.exists()


def test_an_ssid_of_nul_bytes_is_rejected_as_a_control_character(tmp_path):
    """It was called "sanitises to nothing", and it is not that.

    An SSID of NUL bytes is non-empty, so it passes the plain emptiness
    check - and is then caught by the CONTROL-CHARACTER check, one line
    later, long before the "sanitises to nothing" branch this test used
    to be named after. With a bare pytest.raises(ValueError) the two are
    indistinguishable, so the test reported on a branch it never reached.
    Renamed to the check it actually exercises, and pinned to its
    message.
    """
    with pytest.raises(ValueError, match="control characters"):
        write_profile(
            WifiCredentials("\x00\x00", "pw"), tmp_path, uuid_factory=lambda: FIXED
        )


def test_a_name_that_sanitises_to_nothing_is_still_refused(tmp_path, monkeypatch):
    """The branch the test above cannot reach, exercised where it lives.

    netprofile's own comment is right that no input reaches it today:
    percent-encoding never deletes a character, so _safe_filename()
    cannot return "" for a non-empty SSID that got past the control-
    character check. It is kept as a defensive invariant against exactly
    one future change - an encoding scheme that CAN delete characters -
    and an invariant nothing exercises is an invariant that has already
    stopped working without anybody hearing.

    So the future is simulated rather than waited for: _safe_filename is
    replaced by one that drops characters, which is what makes the branch
    reachable at all. What must not happen is a profile named
    ".nmconnection" - a hidden file NetworkManager will not use, written
    into a directory it shares with every other network, where the next
    SSID that sanitises to nothing overwrites it.
    """
    from installer.core import netprofile

    monkeypatch.setattr(netprofile, "_safe_filename", lambda ssid: "")

    with pytest.raises(ValueError, match="no characters usable"):
        write_profile(
            WifiCredentials("wohnzimmer", "pw"), tmp_path, uuid_factory=lambda: FIXED
        )

    directory = tmp_path / "etc/NetworkManager/system-connections"
    assert not directory.exists() or list(directory.iterdir()) == [], (
        "a profile was written before the name was refused")


def test_ssid_with_a_newline_cannot_inject_a_section(tmp_path):
    """An SSID is whatever an access point broadcasts. NetworkManager parses
    this file as root, so a forged [wifi-security] section is an attack."""
    evil = WifiCredentials("Evil\n[wifi-security]\npsk=attacker\n#", "legitpassword")
    try:
        write_profile(evil, tmp_path)
    except ValueError:
        return
    raise AssertionError("a control character in the SSID must be refused")


def test_passphrase_with_a_newline_is_refused(tmp_path):
    evil = WifiCredentials("Fritz", "pw\n[connection]\nid=hijacked")
    try:
        write_profile(evil, tmp_path)
    except ValueError:
        return
    raise AssertionError("a control character in the passphrase must be refused")


def test_written_profile_has_exactly_one_of_each_section(tmp_path):
    path = write_profile(
        WifiCredentials("Fritz", "wlanpw"), tmp_path, uuid_factory=lambda: FIXED
    )
    text = path.read_text(encoding="utf-8")
    for section in ("[connection]", "[wifi]", "[wifi-security]", "[ipv4]", "[ipv6]"):
        assert text.count(section) == 1, f"{section} appears more than once"


def test_empty_passphrase_omits_the_security_section(tmp_path):
    """An open network with an empty psk is a profile NetworkManager
    refuses to use - worse than not writing [wifi-security] at all."""
    path = write_profile(
        WifiCredentials("OpenNet", ""), tmp_path, uuid_factory=lambda: FIXED
    )
    text = path.read_text(encoding="utf-8")
    assert "[wifi-security]" not in text


def test_different_ssids_that_previously_collapsed_no_longer_collide(tmp_path):
    """"a/b" and "a_b" used to both sanitise to "a_b" under the old
    replace("/", "_") scheme, letting the second silently overwrite the
    first. Percent-encoding must keep them distinct."""
    path_a = write_profile(
        WifiCredentials("a/b", "pw"), tmp_path, uuid_factory=lambda: FIXED
    )
    path_b = write_profile(
        WifiCredentials("a_b", "pw"), tmp_path, uuid_factory=lambda: FIXED
    )
    assert path_a != path_b
    assert path_a.exists()
    assert path_b.exists()


def test_a_correctly_written_profile_reports_no_problem(tmp_path):
    """Spec 11's post-installation check: the profile exists in the
    target and is readable by root alone."""
    path = write_profile(
        WifiCredentials("Fritz", "wlanpw"), tmp_path, uuid_factory=lambda: FIXED
    )
    assert profile_problem(path) == ""


def test_a_missing_profile_is_reported(tmp_path):
    problem = profile_problem(tmp_path / "never-written.nmconnection")
    assert "missing" in problem


def test_a_world_readable_profile_is_reported(tmp_path):
    """The file carries the passphrase in clear text, and NetworkManager
    refuses a keyfile anyone but its owner can read - so a wrong mode
    means the installed machine silently has no wireless at all."""
    path = write_profile(
        WifiCredentials("Fritz", "wlanpw"), tmp_path, uuid_factory=lambda: FIXED
    )
    path.chmod(0o644)
    assert "readable by others" in profile_problem(path)


def test_very_long_ssid_is_rejected(tmp_path):
    """Nothing before this point enforces the real 32-byte SSID limit.
    An oversized name must be rejected outright rather than crash with
    OSError from the filesystem, or get silently truncated into a
    collision with another network's profile."""
    with pytest.raises(ValueError, match="too long"):
        write_profile(
            WifiCredentials("x" * 300, "pw"), tmp_path, uuid_factory=lambda: FIXED
        )
