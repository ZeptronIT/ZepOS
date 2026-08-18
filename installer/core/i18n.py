# SPDX-License-Identifier: GPL-3.0-or-later
"""Bilingual message catalogue.

English source strings are the msgids; German is a first-class catalogue
in po/de.po. Anything a user can see goes through _(), including
exception messages - an unhandled exception is user output.

Purely internal assertions that only fire on a programming error stay
untranslated, so translators are not asked to render text no user reads.
"""
from __future__ import annotations

import gettext
import struct
from pathlib import Path

DOMAIN = "zepos-installer"
SUPPORTED_LANGUAGES = ("en", "de")
SYSTEM_LOCALEDIR = Path("/usr/share/locale")
# A development checkout has no installed .mo; po/build.sh writes one here.
DEV_LOCALEDIR = Path(__file__).resolve().parents[2] / "po" / "build"

_translation: gettext.NullTranslations = gettext.NullTranslations()
_language = "en"


def activate(
    language: str,
    *,
    localedir: Path | None = None,
    translation: gettext.NullTranslations | None = None,
) -> None:
    """Select the catalogue. Never raises: a missing catalogue degrades to
    English rather than leaving the installer unable to print anything."""
    global _translation, _language
    _language = language

    if translation is not None:
        _translation = translation
        return

    candidates = [localedir] if localedir else [SYSTEM_LOCALEDIR, DEV_LOCALEDIR]
    for directory in candidates:
        try:
            _translation = gettext.translation(
                DOMAIN, localedir=str(directory), languages=[language]
            )
            return
        except (OSError, AttributeError, struct.error, ValueError):
            # struct.error: a truncated .mo, e.g. from an interrupted write.
            # It is not an OSError, so it must be named explicitly - an
            # installer that cannot start because a translation file is half
            # written would be worse than one printing English.
            continue

    _translation = gettext.NullTranslations()


def current_language() -> str:
    return _language


def _(message: str) -> str:
    """Look the catalogue up at call time, so activate() takes effect for
    strings imported before it ran."""
    return _translation.gettext(message)


def ngettext(singular: str, plural: str, n: int) -> str:
    """The same, for a string whose form depends on a count.

    Not a convenience over `_()`: a language decides for itself how many
    plural forms it has and which count takes which, and that rule lives
    in the catalogue's Plural-Forms header. Building "1 networks found"
    out of a single template is the failure this exists to prevent, and
    it is the failure a reader notices immediately.

    Resolved at call time for the same reason `_()` is - activate() may
    not have run when the caller's module was imported.
    """
    return _translation.ngettext(singular, plural, n)
