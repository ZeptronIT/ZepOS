# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from src.paths import (
    SYSTEM_ROOT_ENV, USER_ROOT_ENV,
    find_template, output_root, system_root, user_root,
)


def test_system_root_defaults_to_the_package_location(monkeypatch):
    """SYSTEM_ROOT_ENV is removed rather than left ambient: a caller's
    shell setting it - deliberately or not - would make this assertion
    about that shell instead of about the code."""
    monkeypatch.delenv(SYSTEM_ROOT_ENV, raising=False)
    assert str(system_root()) == "/usr/share/zepos"


def test_user_root_defaults_below_the_home_config(monkeypatch):
    """XDG_CONFIG_HOME is removed rather than left ambient: with it set to
    anything not ending in .config - which a CI container or a sandboxed
    runner may well do - this assertion is about the environment rather
    than about the code."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv(USER_ROOT_ENV, raising=False)
    assert str(user_root()).endswith(".config/zepos")


def test_both_roots_are_overridable_for_testing(tmp_path, monkeypatch):
    monkeypatch.setenv(SYSTEM_ROOT_ENV, str(tmp_path / "sys"))
    monkeypatch.setenv(USER_ROOT_ENV, str(tmp_path / "usr"))
    assert system_root() == tmp_path / "sys"
    assert user_root() == tmp_path / "usr"


def test_a_user_template_wins_over_the_system_one(tmp_path, monkeypatch):
    """The whole point of the split: pacman -Syu updates the system
    template without touching what the user changed."""
    monkeypatch.setenv(SYSTEM_ROOT_ENV, str(tmp_path / "sys"))
    monkeypatch.setenv(USER_ROOT_ENV, str(tmp_path / "usr"))
    for root in ("sys", "usr"):
        (tmp_path / root / "templates").mkdir(parents=True)
    (tmp_path / "sys/templates/ags-bar.template").write_text("system")
    (tmp_path / "usr/templates/ags-bar.template").write_text("user")

    assert find_template("ags-bar").read_text() == "user"


def test_the_system_template_is_used_when_the_user_has_none(tmp_path, monkeypatch):
    monkeypatch.setenv(SYSTEM_ROOT_ENV, str(tmp_path / "sys"))
    monkeypatch.setenv(USER_ROOT_ENV, str(tmp_path / "usr"))
    (tmp_path / "sys/templates").mkdir(parents=True)
    (tmp_path / "sys/templates/ags-bar.template").write_text("system")

    assert find_template("ags-bar").read_text() == "system"


def test_a_missing_template_names_both_places_it_looked(tmp_path, monkeypatch):
    monkeypatch.setenv(SYSTEM_ROOT_ENV, str(tmp_path / "sys"))
    monkeypatch.setenv(USER_ROOT_ENV, str(tmp_path / "usr"))
    with pytest.raises(FileNotFoundError) as excinfo:
        find_template("does-not-exist")
    message = str(excinfo.value)
    assert "sys" in message and "usr" in message


def test_a_template_name_cannot_escape_its_directory(tmp_path, monkeypatch):
    """Template names reach this from configuration files. A name of
    '../../etc/passwd' must not resolve outside the template directory."""
    monkeypatch.setenv(SYSTEM_ROOT_ENV, str(tmp_path / "sys"))
    monkeypatch.setenv(USER_ROOT_ENV, str(tmp_path / "usr"))
    with pytest.raises(ValueError):
        find_template("../../etc/passwd")


def test_output_root_is_the_config_home_not_the_package(monkeypatch, tmp_path):
    """Generated files belong to the user, never below /usr/share."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert output_root() == tmp_path


# --- Additional guard coverage -----------------------------------------
#
# The brief's single traversal test proves "../../etc/passwd" is refused.
# It does not, by itself, show *why* the guard holds in general. These
# cases probe the other ways a single-component check could be bypassed:
# an absolute path (which pathlib's `/` operator would otherwise splice
# in and discard the base directory entirely), a bare "..", and a name
# that is empty or otherwise degenerate. All of them must be refused
# without ever touching the filesystem outside the two configured roots.

def test_an_absolute_template_name_is_rejected(tmp_path, monkeypatch):
    """Path('base') / '/etc/passwd' silently returns '/etc/passwd' -
    pathlib treats joining with an absolute path as a full replacement,
    not an append. An absolute name must be refused for that reason,
    not merely because it happens to contain a slash."""
    monkeypatch.setenv(SYSTEM_ROOT_ENV, str(tmp_path / "sys"))
    monkeypatch.setenv(USER_ROOT_ENV, str(tmp_path / "usr"))
    with pytest.raises(ValueError):
        find_template("/etc/passwd")


def test_a_bare_parent_reference_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv(SYSTEM_ROOT_ENV, str(tmp_path / "sys"))
    monkeypatch.setenv(USER_ROOT_ENV, str(tmp_path / "usr"))
    with pytest.raises(ValueError):
        find_template("..")


def test_an_empty_template_name_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv(SYSTEM_ROOT_ENV, str(tmp_path / "sys"))
    monkeypatch.setenv(USER_ROOT_ENV, str(tmp_path / "usr"))
    with pytest.raises(ValueError):
        find_template("")


def test_a_name_that_is_only_a_dotfile_is_rejected(tmp_path, monkeypatch):
    """Guards against a name of '.' as well as hidden-file names such as
    '.bashrc', which have no business being looked up as templates."""
    monkeypatch.setenv(SYSTEM_ROOT_ENV, str(tmp_path / "sys"))
    monkeypatch.setenv(USER_ROOT_ENV, str(tmp_path / "usr"))
    with pytest.raises(ValueError):
        find_template(".")
