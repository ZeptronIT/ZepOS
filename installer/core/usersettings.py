# SPDX-License-Identifier: GPL-3.0-or-later
"""Carry the ZepOS options into the installed system.

Spec §8.2 step 6 asks the user whether the Hyprland plugins should be
enabled and where the weather widget should point. Neither question has
any effect unless the answers reach the installed machine: the desktop
generator reads them from user-settings.json (spec §5), not from the
installer.

Two places get the file, for two different reasons:

  * /etc/skel/.config/zepos/user-settings.json - the seed every user
    account created LATER inherits (spec §4, "/etc/skel sorgt dafuer,
    dass jeder neu angelegte Nutzer automatisch eine funktionierende
    Konfiguration erhaelt").
  * the home directory of each account this installation created -
    archinstall creates those DURING the installation, so /etc/skel was
    already copied by the time this runs. Seeding skel alone would leave
    the one account the user is about to log in with as the only one
    without the settings they just chose.

Ownership of a written home file is taken from the home directory itself
rather than guessed: the target system's numeric uid for a freshly
created account is not knowable from here, but the directory archinstall
created for it already carries the right one.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Sequence

from .model import SCHEMA_VERSION, ZeposOptions

SETTINGS_RELATIVE_PATH = Path(".config/zepos/user-settings.json")
SKEL_DIR = "etc/skel"
HOME_DIR = "home"


def settings_document(zepos: ZeposOptions) -> dict[str, object]:
    """The JSON document written into the installed system.

    Carries schema_version for the same reason InstallConfig does (spec
    §5.2): without it, a later migration cannot tell what structure a
    file on a stranger's machine has.

    Only the options the installer actually collects appear here. The VPN
    pre-configuration spec §8.2 step 6 also mentions is deliberately
    absent - no surface asks for it, and inventing defaults for a VPN
    would write a configuration nobody chose.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "plugins": {"enabled": zepos.enable_plugins},
        "weather": {"location": zepos.weather_location},
    }


def _write_settings(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    # World readable on purpose, unlike the wireless profile: these are
    # preferences, not credentials, and /etc/skel entries must stay
    # readable by the accounts that inherit them.
    path.chmod(0o644)


def _adopt_owner(path: Path, reference: Path) -> None:
    """Give path the owner of reference, including the directories just
    created below it. Silently skipped when this process may not chown:
    the settings are still correct, only owned by root, and refusing the
    whole installation over a preferences file would be worse."""
    info = reference.stat()
    current = path
    while current != reference:
        try:
            os.chown(current, info.st_uid, info.st_gid)
        except (OSError, AttributeError):
            return
        current = current.parent


def write_user_settings(
    zepos: ZeposOptions, target_root: Path, usernames: Sequence[str] = ()
) -> list[Path]:
    """Write user-settings.json into the target and return every path written."""
    document = settings_document(zepos)
    written: list[Path] = []

    skel = Path(target_root) / SKEL_DIR / SETTINGS_RELATIVE_PATH
    _write_settings(skel, document)
    written.append(skel)

    for username in usernames:
        home = Path(target_root) / HOME_DIR / username
        if not home.is_dir():
            # No home directory means no such account in the target - a
            # system user, or an account archinstall did not create.
            # Writing one here would create a directory tree owned by
            # root that the account would never be able to use.
            continue
        path = home / SETTINGS_RELATIVE_PATH
        _write_settings(path, document)
        _adopt_owner(path, home)
        written.append(path)

    return written
