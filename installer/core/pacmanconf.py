# SPDX-License-Identifier: GPL-3.0-or-later
"""The repository definition that stays behind in the installed system.

Spec §8.5b. The definition an installation is PERFORMED with is not the
one that may REMAIN: an offline installation reads its ZepOS packages
from `file:///opt/zepos-repo`, a directory of the live medium. The moment
that medium is unplugged the path is gone, and every `pacman -Syu` on the
installed machine fails on a repository it cannot reach. That is not an
edge case - it is what every installation without a network leaves
behind.

WHY THIS CANNOT BE LEFT TO archinstall
    Read against archinstall 4.4, which writes the section twice by two
    different routes, neither of them wrong on its own:

      * `Installer.set_mirrors(..., on_target=False)` APPENDS the
        `[zepos]` section to the LIVE system's /etc/pacman.conf, because
        that is the file pacstrap installs the target from
        (`pacstrap -C /etc/pacman.conf`);
      * `minimal_installation()` then calls `PacmanConfig.persist()`,
        which COPIES that same live /etc/pacman.conf over the target's -
        carrying the section with it;
      * `set_mirrors(..., on_target=True)` appends it a second time,
        to the target's copy.

    So a finished installation carries TWO identical `[zepos]` sections,
    and for an offline installation both name a path that no longer
    exists. Two sections is not merely untidy: pacman reads both, and a
    later correction applied to one of them leaves the other one
    contradicting it.

    Hence "exactly one", which is what §8.5b asks for and what this
    module is measured against.

WHY IT REPLACES RATHER THAN EDITS
    Rewriting the URL in place would leave whichever of the two sections
    the substitution did not reach. Removing every `[zepos]` section and
    appending one is the only form whose result does not depend on how
    many were there to begin with - including none, which is what a
    target produced by some future archinstall might have.
"""
from __future__ import annotations

import re
from pathlib import Path

from .source import ONLINE_REPO_URL, PackageSource, REPO_NAME, mirror_config

# Relative to the target root, so the same function works against /mnt
# during an installation and against a temporary directory in a test.
PACMAN_CONF = Path("etc/pacman.conf")

# A pacman section header is the whole line. pacman's own parser accepts
# nothing after the closing bracket, so anything else is not a header and
# must not be treated as the start of a new section - otherwise a line
# inside [zepos] that merely looks like one would end the removal early
# and leave half a section behind.
_SECTION_HEADER = re.compile(r"^\s*\[([^\]]+)\]\s*$")

# pacman's own name for the switch, spelled as its parser expects it.
# Verified against the binary of pacman 7.1.0, which is the version the
# pinned snapshot installs.
_NO_TIMEOUT = "DisableDownloadTimeout"
_OPTIONS_HEADER = re.compile(r"^\s*\[options\]\s*$")


def _repository(url: str | None) -> dict[str, str]:
    """The [zepos] entry as source.py describes it, with the URL that is
    to survive.

    Taken from mirror_config() rather than written out again: the
    SigLevel the installed system ends up with has to be the SigLevel the
    installation was performed with, or a machine that verified every
    package while it was being installed stops verifying them afterwards
    - or, the other way round, demands a signature nobody arranged for.
    """
    repositories = mirror_config(PackageSource.ONLINE)["custom_repositories"]
    entry = next(repo for repo in repositories if repo["name"] == REPO_NAME)
    if url is not None:
        entry = {**entry, "url": url}
    return entry


def section_text(url: str | None = None) -> str:
    """The one `[zepos]` section, in the shape archinstall writes it.

    Deliberately the same three lines and the same order: a system
    installed by this code and a system whose pacman.conf a person later
    compares against archinstall's own output should differ in the URL
    and in nothing else.
    """
    entry = _repository(url)
    return (
        f"[{entry['name']}]\n"
        f"SigLevel = {entry['sign_check']} {entry['sign_option']}\n"
        f"Server = {entry['url']}\n"
    )


def strip_sections(text: str, name: str) -> str:
    """Remove every section called `name`, header and body.

    A section runs from its header to the next header or to the end of
    the file - pacman has no closing token - so removal is a state
    machine over the lines rather than a regular expression over the
    text.
    """
    kept: list[str] = []
    inside = False
    for line in text.splitlines(keepends=True):
        header = _SECTION_HEADER.match(line)
        if header:
            inside = header.group(1).strip() == name
        if not inside:
            kept.append(line)
    return "".join(kept)


def zepos_servers(text: str) -> list[str]:
    """Every `Server =` line that belongs to a `[zepos]` section.

    Exists so that the property §8.5b actually asks for - one section,
    one server, and no `file://` among them - can be asserted against a
    real installed pacman.conf without a second parser being written
    wherever somebody wants to check it.
    """
    servers: list[str] = []
    inside = False
    for line in text.splitlines():
        header = _SECTION_HEADER.match(line)
        if header:
            inside = header.group(1).strip() == REPO_NAME
            continue
        if inside and line.strip().startswith("Server"):
            _, _, value = line.partition("=")
            servers.append(value.strip())
    return servers


def disable_download_timeout(text: str) -> str:
    """Add `DisableDownloadTimeout` to `[options]`, if it is not there.

    WHY AN INSTALLED SYSTEM NEEDS THIS AND AN ARCH SYSTEM DOES NOT
        pacman aborts a download that moves less than a byte per second
        for ten seconds, and it fails the whole transaction with it.
        Against a mirrorlist that is a sensible default: there are other
        mirrors, and the next one is probably fine.

        A ZepOS installation has no other mirror. pacstrap(8) copies the
        live medium's mirrorlist into the new root, and that mirrorlist
        holds exactly one line - the Arch Linux Archive snapshot this
        medium was pinned to (spec §8.7). So the installed machine
        updates from one rate-limited host, and ten seconds of silence
        from it ends a `pacman -Syu` that had already downloaded
        hundreds of megabytes.

        Measured on 11.08.2026 during an installation, which is the same
        host and the same fuse:

            error: failed retrieving file
            'linux-firmware-mediatek-20260622-1-any.pkg.tar.zst'
            from archive.archlinux.org : Operation too slow

        iso/profile-release/airootfs/usr/local/bin/zepos-live-prepare
        does this to the LIVE system, for the installation itself, and
        states the trade it makes. This is the same switch for what is
        left behind, and it matters more here: nobody is watching an
        automatic update (task UP-1).

    Text in, text out, so the decision can be tested without a
    filesystem - and applied to whatever archinstall left, rather than
    to a file this code wrote and could therefore assume the shape of.
    """
    lines = text.splitlines()
    if any(line.strip() == _NO_TIMEOUT for line in lines):
        return text

    for index, line in enumerate(lines):
        if _OPTIONS_HEADER.match(line):
            lines.insert(index + 1, _NO_TIMEOUT)
            return "\n".join(lines) + "\n"

    # No [options] at all. pacman reads settings before the first section
    # header as belonging to no section and ignores them, so the switch
    # has to bring its own header rather than be prepended bare.
    return f"[options]\n{_NO_TIMEOUT}\n\n{text}" if text else \
        f"[options]\n{_NO_TIMEOUT}\n"


def rewrite_zepos_repository(target_root: Path, *, url: str | None = None) -> Path:
    """Leave exactly one `[zepos]` section in the target's pacman.conf,
    pointing at the online repository, and disable the download timeout.
    Returns the file written.

    Two guarantees in one pass because they are two edits to one file,
    and a second function that re-read and re-wrote it would be a second
    chance for the two to disagree about what was in it.

    An absent pacman.conf is created rather than reported. The only
    caller reaches this after archinstall has said the installation
    succeeded, which means pacstrap installed `pacman`, which owns that
    file - so absence cannot happen on a real target, and inventing a
    warning for it would put a message in front of a user that nothing
    they could do would answer. What CAN fail here - an unwritable path,
    a target root that is not a directory - raises, and runner.py turns
    that into the warning it turns every other post-installation failure
    into.
    """
    path = Path(target_root) / PACMAN_CONF
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    remainder = strip_sections(existing, REPO_NAME).rstrip("\n")
    body = section_text(url if url is not None else ONLINE_REPO_URL)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        disable_download_timeout(
            f"{remainder}\n\n{body}" if remainder else body
        ),
        encoding="utf-8",
    )
    return path
