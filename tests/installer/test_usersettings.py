# SPDX-License-Identifier: GPL-3.0-or-later
"""The ZepOS options must reach the installed system.

Both surfaces ask whether the Hyprland plugins should be enabled and
where the weather widget points. Until these were written into the
target, both questions changed nothing at all.
"""
from __future__ import annotations

import json
import stat

from installer.core.model import SCHEMA_VERSION, ZeposOptions
from installer.core.usersettings import settings_document, write_user_settings

OPTIONS = ZeposOptions(enable_plugins=False, weather_location="Wien")


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_document_carries_the_collected_options():
    document = settings_document(OPTIONS)
    assert document["plugins"]["enabled"] is False
    assert document["weather"]["location"] == "Wien"


def test_the_document_is_versioned():
    """Spec 5.2: without schema_version, a later migration cannot tell
    what structure a file on a stranger's machine has."""
    assert settings_document(OPTIONS)["schema_version"] == SCHEMA_VERSION


def test_skel_is_seeded_for_accounts_created_later(tmp_path):
    written = write_user_settings(OPTIONS, tmp_path)
    skel = tmp_path / "etc/skel/.config/zepos/user-settings.json"
    assert written == [skel]
    assert _read(skel)["weather"]["location"] == "Wien"


def test_the_account_this_installation_created_gets_the_settings_too(tmp_path):
    """archinstall creates the accounts DURING the installation, so
    /etc/skel was already copied by the time this runs. Seeding skel
    alone would leave the one account the user is about to log in with as
    the only one without the settings they just chose."""
    (tmp_path / "home" / "lars").mkdir(parents=True)
    written = write_user_settings(OPTIONS, tmp_path, ["lars"])
    home_settings = tmp_path / "home/lars/.config/zepos/user-settings.json"
    assert home_settings in written
    assert _read(home_settings)["plugins"]["enabled"] is False


def test_an_account_without_a_home_directory_is_skipped(tmp_path):
    """No home directory means no such account in the target. Creating
    one here would leave a root-owned tree the account could never
    use."""
    written = write_user_settings(OPTIONS, tmp_path, ["nobody"])
    assert not (tmp_path / "home/nobody").exists()
    assert written == [tmp_path / "etc/skel/.config/zepos/user-settings.json"]


def test_the_settings_are_readable_by_the_account_that_inherits_them(tmp_path):
    """Unlike the wireless profile, these are preferences rather than
    credentials - and an /etc/skel entry only works if the accounts
    copying it may read it."""
    write_user_settings(OPTIONS, tmp_path)
    path = tmp_path / "etc/skel/.config/zepos/user-settings.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_writing_twice_replaces_rather_than_appends(tmp_path):
    write_user_settings(OPTIONS, tmp_path)
    write_user_settings(ZeposOptions(enable_plugins=True, weather_location=""), tmp_path)
    document = _read(tmp_path / "etc/skel/.config/zepos/user-settings.json")
    assert document["plugins"]["enabled"] is True
    assert document["weather"]["location"] == ""
