# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os

import pytest

from src.settings import (SCHEMA_VERSION, default_connection, defaults,
                          load, save)
from tests.origin_data import ORIGIN


def test_defaults_carry_the_schema_version():
    assert defaults()["schema_version"] == SCHEMA_VERSION


def test_defaults_contain_no_employer_values():
    """The origin hardcoded a corporate domain, two internal DNS servers
    and a file server hostname. None of that belongs in a default.

    The four strings this used to spell out are digests in
    tests/origin_data.py now, along with twenty more - so this checks
    against a wider set than it did, and does it without writing the
    employer's domain into a file that is about to be published. Each
    value is checked on its own as well as the whole document, because a
    settings default is a single value and a guard that only ever sees
    the concatenation would miss one that straddles no line at all.
    """
    document = defaults()
    assert not ORIGIN.hits(json.dumps(document)), (
        "an origin value survives in the defaults - see tests/origin_data.py")

    def walk(node, trail="defaults"):
        if isinstance(node, dict):
            for key, value in node.items():
                assert not ORIGIN.hits(str(key)), f"{trail}.{key}: the key"
                walk(value, f"{trail}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{trail}[{index}]")
        else:
            assert not ORIGIN.hits(str(node)), f"{trail}: the value"

    walk(document)


def test_roundtrip_preserves_values(tmp_path):
    path = tmp_path / "user-settings.json"
    # Ueber eine echte Verbindung in der Liste, seit `vpn` am
    # 22.08.2026 eine Liste traegt: `defaults()["vpn"]` ist jetzt
    # {"active": "", "connections": []}, und ein Wert, den man dort
    # hineinschreibt, waere keiner, den irgendein Leser findet.
    data = defaults()
    verbindung = dict(default_connection(), id="c1")
    verbindung["dns"]["search_domain"] = "example.org"
    data["vpn"] = {"active": "c1", "connections": [verbindung]}
    save(data, path)
    gelesen = load(path)["vpn"]["connections"][0]
    assert gelesen["dns"]["search_domain"] == "example.org"


def test_a_missing_file_yields_the_defaults(tmp_path):
    assert load(tmp_path / "absent.json") == defaults()


def test_an_unknown_schema_version_is_refused(tmp_path):
    path = tmp_path / "user-settings.json"
    path.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
    with pytest.raises(ValueError, match="99"):
        load(path)


def test_a_file_without_a_version_is_refused(tmp_path):
    """A file predating the versioning cannot be interpreted safely -
    refusing is honest, guessing is not."""
    path = tmp_path / "user-settings.json"
    path.write_text(json.dumps({"vpn": {}}), encoding="utf-8")
    with pytest.raises(ValueError):
        load(path)


def test_saved_file_is_not_world_readable(tmp_path):
    """Settings may carry a VPN pre-shared key."""
    import stat
    path = tmp_path / "user-settings.json"
    save(defaults(), path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_save_never_makes_the_new_content_visible_above_0600(tmp_path, monkeypatch):
    """save() writes to a fresh temporary file and moves it into place
    with os.replace() rather than truncating `target` in place - see the
    comment in save() for why an in-place chmod()-then-write is not
    enough under a concurrent replacement of `target`.

    The property to check is: whatever file os.replace() is about to make
    visible at `target`'s path is already 0o600 *before* that happens -
    os.replace() is the instant the new content stops being private to
    this function and starts being what a reader of `target` sees. This
    instruments os.replace() itself (through the isolation guard's own
    wrapper, so the guard stays in effect) to record the mode of the file
    being moved into place at exactly that instant, rather than inferring
    it from the state after save() has already returned - both a correct
    and a broken ordering end at 0o600 once save() is done, so only
    observing the moment of the swap can tell them apart.
    """
    import stat

    path = tmp_path / "user-settings.json"

    observed_modes = []
    # Captured *after* the isolation guard's own autouse fixture has
    # already wrapped this function, so calling through here still goes
    # through that guard - this only adds an observation point, it does
    # not bypass anything the guard enforces.
    guarded_replace = os.replace

    def probing_replace(src, dst, *args, **kwargs):
        if dst == path:
            observed_modes.append(stat.S_IMODE(os.stat(src).st_mode))
        return guarded_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", probing_replace)

    save(defaults(), path)

    assert observed_modes == [0o600], (
        "temporary file was not yet 0o600 when it replaced the target: "
        f"observed mode(s) {[oct(m) for m in observed_modes]}"
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert load(path) == defaults()


def test_a_stale_temporary_file_does_not_block_saving(tmp_path):
    """A killed process leaves its temporary file behind. With a fixed
    temp name that blocked every later save with FileExistsError - a
    failure that outlives its cause and names a file the user has never
    seen."""
    target = tmp_path / "user-settings.json"
    (tmp_path / ".user-settings.json.new").write_text("half-written")

    save(defaults(), target)

    assert load(target) == defaults()


@pytest.mark.parametrize("document", ["[]", "null", "5", '"text"'])
def test_a_top_level_that_is_not_an_object_is_refused(tmp_path, document):
    """json.loads answers a list, None, an int or a str just as happily
    as a dict, and .get() exists on none of them.

    An AttributeError is neither ValueError nor OSError, so every caller
    that handles "this file cannot be read" - zepos-settings and
    zepos-doctor both - misses it and shows the user a traceback instead.
    The doctor is the command someone reaches for when the configuration
    is broken; it is the one that must not do that.
    """
    path = tmp_path / "user-settings.json"
    path.write_text(document, encoding="utf-8")

    with pytest.raises(ValueError):
        load(path)


# --------------------------------------------------------------------
# merge(): the read-modify-write every partial writer goes through
# --------------------------------------------------------------------

def test_merge_keeps_the_sections_the_writer_does_not_own(tmp_path):
    """The AGS dialogs each own one section of a file that holds five.

    Both of them read it in a `catch {}`, fell back to an empty object
    and wrote that - so a dialog that could not parse the file replaced
    the whole document with its own section and deleted every other
    setting on the machine.
    """
    from src.settings import merge

    path = tmp_path / "user-settings.json"
    document = defaults()
    document["colors"] = {"success": "#a6e3a1"}
    document["plugins"] = {"enabled": True}
    save(document, path)

    merge({"vpn": {"server": "gw.example.org"}}, path)

    after = load(path)
    assert after["vpn"] == {"server": "gw.example.org"}, "the section was not written"
    assert after["colors"] == {"success": "#a6e3a1"}, "another section was deleted"
    assert after["plugins"] == {"enabled": True}, "another section was deleted"
    assert after["weather"] == document["weather"]


def test_merge_writes_a_versioned_document_when_there_is_none(tmp_path):
    """Whichever writer runs first on a fresh machine decides what the
    file is. One that wrote no schema_version made every versioned reader
    - zepos-settings among them - refuse a file the user created by
    changing a colour."""
    from src.settings import merge

    path = tmp_path / "user-settings.json"
    merge({"colors": {"success": "#a6e3a1"}}, path)

    assert load(path)["schema_version"] == SCHEMA_VERSION
    assert load(path)["colors"] == {"success": "#a6e3a1"}


def test_merge_is_not_world_readable_and_never_truncates(tmp_path, monkeypatch):
    """`open(path, 'w')` drops the file to zero bytes while it is held,
    which is the state a reader then falls back to its own defaults over.
    Every writer of this file has to go through the same replace."""
    import stat
    from src.settings import merge

    path = tmp_path / "user-settings.json"
    save(defaults(), path)

    sizes = []
    real_open = os.open

    def watching_open(target, flags, *args, **kwargs):
        if str(target) == str(path):
            sizes.append(("open", flags & os.O_TRUNC, flags & os.O_WRONLY))
        return real_open(target, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", watching_open)
    merge({"weather": {"location": "Bremen"}}, path)

    assert [entry for entry in sizes if entry[1] or entry[2]] == [], (
        f"the target itself was opened for writing: {sizes}")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert load(path)["weather"] == {"location": "Bremen"}


def test_merge_refuses_a_file_it_cannot_read_and_changes_nothing(tmp_path):
    """The dialog's own state is one section. Writing it over a document
    that could not be parsed is how the other four disappear."""
    from src.settings import merge

    path = tmp_path / "user-settings.json"
    original = '{"colors": {"success": "#a6e3a1"}, "vpn": {"serv'
    path.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError):
        merge({"vpn": {"server": "gw.example.org"}}, path)

    assert path.read_text(encoding="utf-8") == original, (
        "the settings it could not read were overwritten anyway")
