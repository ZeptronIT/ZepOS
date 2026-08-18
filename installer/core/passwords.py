# SPDX-License-Identifier: GPL-3.0-or-later
"""SHA-512 password hashing for archinstall's creds.json.

Python removed the `crypt` module in 3.13, so this shells out to
openssl. The plaintext goes through stdin: an argument vector is world
readable via /proc, stdin is not.
"""
from __future__ import annotations

import re
import subprocess
from typing import Callable

from .i18n import _

Runner = Callable[..., subprocess.CompletedProcess]

# C0 controls plus DEL - the same rule netprofile.py applies to the
# wireless secret, and for a closely related reason.
#
# The plaintext is fed to `openssl passwd -6 -stdin`, which hashes one
# line at a time: confirmed empirically that
# `printf 'abc\ndef\n' | openssl passwd -6 -stdin` prints TWO $6$ lines.
# .strip() removes only the outer whitespace, so a password containing a
# newline becomes a two-line "hash", travels on as one enc_password, and
# archinstall writes it verbatim into /etc/shadow - locking the user out
# of the machine they have just installed, with no way back in.
#
# Rejected rather than trimmed or escaped: a genuine password never
# contains a control character, and silently changing what someone typed
# would set a password they cannot reproduce.
_FORBIDDEN = re.compile(r"[\x00-\x1f\x7f]")


def hash_password(plain: str, *, runner: Runner | None = None) -> str:
    if not plain:
        # Left untranslated on purpose, unlike the two exceptions below.
        # No user can reach this: validate() rejects a password shorter
        # than MIN_PASSWORD_LENGTH before install() runs, and both
        # surfaces re-ask at the point of entry. An empty password
        # arriving here is a caller passing something it never collected
        # - a programming error, and translators should not be asked to
        # render text no user will read (see source.py's own note on
        # where that line is drawn).
        raise ValueError("refusing to hash an empty password")

    if _FORBIDDEN.search(plain):
        # Reachable through the public install() API and the unattended
        # path the README advertises, so it must be translated even
        # though neither surface can produce such a password today.
        raise ValueError(_("The password contains control characters."))

    # Resolved here, not bound as a default: a default argument captures
    # subprocess.run at import time, which the test suite's isolation guard
    # cannot intercept.
    runner = runner or subprocess.run

    try:
        result = runner(
            ["openssl", "passwd", "-6", "-stdin"],
            input=plain,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        # openssl missing or not executable. Reachable on a damaged live
        # image, so the user can see it - hence _().
        raise RuntimeError(
            _("Could not run openssl to hash the password: {reason}")
            .format(reason=exc)
        ) from exc

    if result.returncode != 0:
        raise RuntimeError(
            _("Hashing the password failed: {reason}")
            .format(reason=result.stderr.strip())
        )

    hashed = result.stdout.strip()
    if "\n" in hashed:
        # The other side of the control-character check above: whatever
        # openssl produced, a "hash" spanning two lines would become two
        # lines in /etc/shadow, and the account would be unusable.
        raise RuntimeError(
            _("Hashing the password produced more than one hash.")
        )
    return hashed
