# SPDX-License-Identifier: GPL-3.0-or-later
import subprocess

import pytest

from installer.core.passwords import hash_password


def test_uses_openssl_sha512_and_returns_hash():
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="$6$abc$def\n", stderr="")

    assert hash_password("geheim", runner=fake_run) == "$6$abc$def"
    assert calls[0][:3] == ["openssl", "passwd", "-6"]


def test_password_is_passed_via_stdin_not_argv():
    """A password in argv would be readable by every process on the system."""
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        seen["input"] = kw.get("input")
        return subprocess.CompletedProcess(cmd, 0, stdout="$6$x$y\n", stderr="")

    hash_password("streng-geheim", runner=fake_run)
    assert "streng-geheim" not in " ".join(seen["cmd"])
    assert seen["input"] == "streng-geheim"


def test_openssl_failure_raises():
    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")

    with pytest.raises(RuntimeError, match="boom"):
        hash_password("geheim", runner=fake_run)


def test_empty_password_raises():
    with pytest.raises(ValueError):
        hash_password("", runner=lambda *a, **k: None)


def test_missing_openssl_raises():
    """If openssl is missing, OSError is caught and re-raised as RuntimeError."""
    def fake_run(cmd, **kw):
        raise FileNotFoundError("openssl: not found")

    with pytest.raises(RuntimeError, match="Could not run openssl"):
        hash_password("geheim", runner=fake_run)


# --- a control character in a password corrupts /etc/shadow ------------
#
# Confirmed empirically against real openssl:
#
#     printf 'abc\ndef\n' | openssl passwd -6 -stdin
#
# prints TWO $6$ lines, one per input line. .strip() only removes the
# outer whitespace, so the two-line string travels on into creds.json as
# a single enc_password, and archinstall writes it verbatim into
# /etc/shadow. The user is then locked out of the machine they just
# installed. Neither surface can produce such a password today, but the
# public install() API and the unattended path advertised in the README
# can.


def test_a_password_containing_a_newline_is_refused():
    def fake_run(cmd, **kw):
        raise AssertionError("openssl must never see a multi-line password")

    with pytest.raises(ValueError, match="control characters"):
        hash_password("abc\ndef", runner=fake_run)


@pytest.mark.parametrize("password", ["a\rb", "a\tb", "a\x00b", "a\x7fb", "a\x1bb"])
def test_every_control_character_is_refused(password):
    """The same rule netprofile.py already applies to the wireless
    secret: a genuine password never contains a control character, so
    anything that does is a broken caller or an attack."""
    with pytest.raises(ValueError, match="control characters"):
        hash_password(password, runner=lambda *a, **k: None)


def test_an_ordinary_password_with_punctuation_still_works():
    """The check must reject control characters, not everything unusual:
    a passphrase full of symbols and umlauts is exactly what it should
    let through."""
    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="$6$x$y\n", stderr="")

    assert hash_password("Straße-#42 !?", runner=fake_run) == "$6$x$y"


def test_a_multi_line_hash_is_refused_even_if_one_slips_through():
    """Belt and braces on the other side of the call: whatever openssl
    returns, a hash spanning two lines must never reach /etc/shadow."""
    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(
            cmd, 0, stdout="$6$abc$def\n$6$ghi$jkl\n", stderr=""
        )

    with pytest.raises(RuntimeError):
        hash_password("geheim", runner=fake_run)
