# SPDX-License-Identifier: GPL-3.0-or-later
"""Spec §8.5b: what the installed system is left pointing at.

The repository an installation is performed FROM is not the one that may
remain. An offline installation reads `file:///opt/zepos-repo`, a
directory of the live medium; the installed machine never sees that path
again. Every check here is about the file the user's second `pacman -Syu`
will read, which is the first moment the mistake becomes visible and much
too late.
"""
from pathlib import Path

from installer.core.pacmanconf import (
    PACMAN_CONF,
    disable_download_timeout,
    rewrite_zepos_repository,
    section_text,
    strip_sections,
    zepos_servers,
)
from installer.core.source import (
    OFFLINE_REPO_URL,
    ONLINE_REPO_URL,
    PackageSource,
    REPO_NAME,
    mirror_config,
)

# What archinstall 4.4 leaves behind after an OFFLINE installation, read
# out of its own source rather than imagined:
#
#   * Installer.set_mirrors(on_target=False) appends the section to the
#     LIVE /etc/pacman.conf, because pacstrap installs the target from
#     that file;
#   * minimal_installation() then calls PacmanConfig.persist(), which
#     copies the live pacman.conf over the target's - section included;
#   * set_mirrors(on_target=True) appends it once more.
#
# MirrorConfiguration.repositories_config() is the exact formatting: two
# newlines, the header, SigLevel, Server.
ARCHINSTALL_LEFTOVER = f"""\
[options]
HoldPkg = pacman glibc
Architecture = auto

[core]
Include = /etc/pacman.d/mirrorlist

[extra]
Include = /etc/pacman.d/mirrorlist


[{REPO_NAME}]
SigLevel = Required TrustedOnly
Server = {OFFLINE_REPO_URL}


[{REPO_NAME}]
SigLevel = Required TrustedOnly
Server = {OFFLINE_REPO_URL}
"""


def _write_target(root: Path, text: str) -> Path:
    path = root / PACMAN_CONF
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------
# The property §8.5b actually states
# --------------------------------------------------------------------

def test_exactly_one_zepos_section_survives(tmp_path):
    """"genau eine [zepos]-Sektion". archinstall leaves two, and a
    correction applied to one of them would leave the other one
    contradicting it."""
    _write_target(tmp_path, ARCHINSTALL_LEFTOVER)

    text = rewrite_zepos_repository(tmp_path).read_text(encoding="utf-8")

    assert text.count(f"[{REPO_NAME}]") == 1, text


def test_the_surviving_section_points_at_the_online_repository(tmp_path):
    _write_target(tmp_path, ARCHINSTALL_LEFTOVER)

    text = rewrite_zepos_repository(tmp_path).read_text(encoding="utf-8")

    assert zepos_servers(text) == [ONLINE_REPO_URL]


def test_no_file_url_is_left_anywhere(tmp_path):
    """Spec §8.5b names this as the test to run after an installation:
    the target's pacman.conf contains no `file://` source. Asserted over
    the WHOLE file, not only the section that was replaced - a leftover
    elsewhere fails the same way on the same day."""
    _write_target(tmp_path, ARCHINSTALL_LEFTOVER)

    text = rewrite_zepos_repository(tmp_path).read_text(encoding="utf-8")

    assert "file://" not in text, text


def test_the_rest_of_pacman_conf_is_untouched(tmp_path):
    """Removing the repository must not remove the system. [options],
    [core] and [extra] are what makes the machine an Arch machine at
    all."""
    _write_target(tmp_path, ARCHINSTALL_LEFTOVER)

    text = rewrite_zepos_repository(tmp_path).read_text(encoding="utf-8")

    for kept in ("[options]", "HoldPkg = pacman glibc", "[core]", "[extra]"):
        assert kept in text, f"{kept} was removed from the target's pacman.conf"
    assert text.count("Include = /etc/pacman.d/mirrorlist") == 2


# --------------------------------------------------------------------
# The shapes that are not the ordinary one
# --------------------------------------------------------------------

def test_a_target_that_already_points_online_still_ends_up_with_one(tmp_path):
    """The online path leaves two sections as well: persist() copies the
    live file and set_mirrors(on_target=True) appends to the copy. So
    this runs for both sources, and there is one code path rather than a
    branch nobody exercises."""
    online = ARCHINSTALL_LEFTOVER.replace(OFFLINE_REPO_URL, ONLINE_REPO_URL)
    _write_target(tmp_path, online)

    text = rewrite_zepos_repository(tmp_path).read_text(encoding="utf-8")

    assert text.count(f"[{REPO_NAME}]") == 1
    assert zepos_servers(text) == [ONLINE_REPO_URL]


def test_a_pacman_conf_with_no_zepos_section_gains_exactly_one(tmp_path):
    """A future archinstall that stops writing the section at all must
    not produce a machine with no ZepOS repository - the packages it was
    installed from would then be unupgradable."""
    _write_target(tmp_path, "[options]\n\n[core]\nInclude = /etc/pacman.d/mirrorlist\n")

    text = rewrite_zepos_repository(tmp_path).read_text(encoding="utf-8")

    assert text.count(f"[{REPO_NAME}]") == 1
    assert zepos_servers(text) == [ONLINE_REPO_URL]


def test_an_absent_pacman_conf_is_created_rather_than_reported(tmp_path):
    """Cannot happen on a real target - pacstrap installs `pacman`,
    which owns the file - and creating it is the outcome that still
    satisfies §8.5b. A warning here would put a message in front of a
    user that nothing they could do would answer."""
    path = rewrite_zepos_repository(tmp_path)

    assert path == tmp_path / PACMAN_CONF
    assert zepos_servers(path.read_text(encoding="utf-8")) == [ONLINE_REPO_URL]


def test_the_section_ends_with_a_newline(tmp_path):
    """pacman reads line by line. A final line with no terminator is
    read, but a later append would land on the same line as `Server =`
    and take the repository with it."""
    _write_target(tmp_path, ARCHINSTALL_LEFTOVER)

    text = rewrite_zepos_repository(tmp_path).read_text(encoding="utf-8")

    assert text.endswith("\n")


# --------------------------------------------------------------------
# The section itself
# --------------------------------------------------------------------

def test_the_siglevel_is_the_one_the_installation_used(tmp_path):
    """A machine that verified every package while it was being
    installed and stops verifying them afterwards has been downgraded
    silently. Taken from mirror_config() rather than repeated, so the two
    cannot drift."""
    entry = next(
        repo
        for repo in mirror_config(PackageSource.ONLINE)["custom_repositories"]
        if repo["name"] == REPO_NAME
    )

    assert f"SigLevel = {entry['sign_check']} {entry['sign_option']}" in section_text()


def test_the_section_has_archinstalls_own_shape():
    """Header, SigLevel, Server, in that order. A person comparing an
    installed pacman.conf against archinstall's own output should find
    the URL different and nothing else."""
    lines = section_text().splitlines()

    assert lines[0] == f"[{REPO_NAME}]"
    assert lines[1].startswith("SigLevel = ")
    assert lines[2].startswith("Server = ")
    assert len(lines) == 3


# --------------------------------------------------------------------
# The parser, at the two places it could be fooled
# --------------------------------------------------------------------

def test_a_section_runs_to_the_next_header():
    """pacman has no closing token, so removal is a state machine. A
    regular expression over `[zepos]` alone would leave SigLevel and
    Server behind, attached to whatever section came before."""
    text = (
        f"[core]\nServer = a\n"
        f"[{REPO_NAME}]\nSigLevel = Required TrustedOnly\nServer = b\n"
        f"[extra]\nServer = c\n"
    )

    stripped = strip_sections(text, REPO_NAME)

    assert stripped == "[core]\nServer = a\n[extra]\nServer = c\n"


def test_a_line_that_merely_looks_like_a_header_does_not_end_the_section():
    """pacman accepts nothing after the closing bracket on a header line.
    Treating a commented-out one as a real header would end the removal
    early and leave `Server = file://...` in the file."""
    text = (
        f"[{REPO_NAME}]\n"
        "#[extra]\n"
        "SigLevel = Required TrustedOnly\n"
        f"Server = {OFFLINE_REPO_URL}\n"
        "[extra]\nServer = c\n"
    )

    stripped = strip_sections(text, REPO_NAME)

    assert stripped == "[extra]\nServer = c\n"
    assert OFFLINE_REPO_URL not in stripped


def test_zepos_servers_ignores_servers_of_other_repositories():
    """The reporting half of this module: it answers "what does [zepos]
    point at", and a count that included [core]'s mirrors would report
    success on a machine that has none."""
    text = (
        "[core]\nServer = https://mirror.example/core\n"
        f"[{REPO_NAME}]\nServer = {ONLINE_REPO_URL}\n"
        "[extra]\nServer = https://mirror.example/extra\n"
    )

    assert zepos_servers(text) == [ONLINE_REPO_URL]


# --- the ten-second fuse on a single-mirror system -------------------------
#
# An installation from this medium died on 11.08.2026 with "Operation too
# slow" from archive.archlinux.org, four minutes in, and took the whole
# transaction with it. pacman's default is written for a mirrorlist with
# something to fall back to; a ZepOS system has exactly one line in its
# mirrorlist, because pacstrap(8) copies the medium's pin into the target.
# So the same fuse is left burning under every later `pacman -Syu`.


def test_the_installed_system_does_not_abort_an_update_on_a_slow_archive(tmp_path):
    """The property, on the file the target actually gets."""
    _write_target(tmp_path, ARCHINSTALL_LEFTOVER)

    text = rewrite_zepos_repository(tmp_path).read_text(encoding="utf-8")

    assert "DisableDownloadTimeout" in text, (
        "the installed system still aborts a whole transaction after ten "
        "seconds of silence from the one host it can reach")


def test_the_switch_lands_inside_options_and_not_before_it():
    """pacman assigns a setting to the section above it. One written
    before the first header belongs to no section, and pacman ignores it
    - which looks exactly like a setting that is present."""
    text = disable_download_timeout(
        "[options]\nHoldPkg = pacman glibc\n\n[core]\nServer = a\n")

    lines = text.splitlines()
    assert lines.index("DisableDownloadTimeout") < lines.index("[core]")
    assert lines.index("[options]") < lines.index("DisableDownloadTimeout")


def test_the_switch_is_not_added_twice():
    """rewrite_zepos_repository runs against whatever archinstall left,
    and a future archinstall may set this itself. pacman takes the last
    of two, so a duplicate is harmless to it and a lie to anyone
    reading the file."""
    once = disable_download_timeout("[options]\nHoldPkg = pacman glibc\n")

    assert disable_download_timeout(once) == once
    assert once.count("DisableDownloadTimeout") == 1


def test_a_switch_that_is_already_there_under_indentation_still_counts():
    """pacman strips leading whitespace before it parses. A checker that
    did not would add a second one."""
    text = "[options]\n  DisableDownloadTimeout\n"

    assert disable_download_timeout(text) == text


def test_a_pacman_conf_without_an_options_section_gains_one():
    """Cannot come from archinstall, and the alternative is worse than
    the unlikely case: prepending the switch bare would put it above
    every header, where pacman ignores it."""
    text = disable_download_timeout("[core]\nServer = a\n")

    lines = text.splitlines()
    assert lines[0] == "[options]"
    assert lines[1] == "DisableDownloadTimeout"
    assert "[core]" in text and "Server = a" in text


def test_disabling_the_timeout_keeps_the_rest_of_the_file(tmp_path):
    """The edit is one inserted line. Everything §8.5b asserts about this
    file has to survive it - measured together, because the two edits now
    share one write."""
    _write_target(tmp_path, ARCHINSTALL_LEFTOVER)

    text = rewrite_zepos_repository(tmp_path).read_text(encoding="utf-8")

    assert text.count(f"[{REPO_NAME}]") == 1
    assert zepos_servers(text) == [ONLINE_REPO_URL]
    assert "file://" not in text
    for kept in ("[options]", "HoldPkg = pacman glibc", "[core]", "[extra]"):
        assert kept in text, f"{kept} was lost when the timeout was disabled"
