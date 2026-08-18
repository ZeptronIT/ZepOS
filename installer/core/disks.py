# SPDX-License-Identifier: GPL-3.0-or-later
"""Enumerate the block devices an installation can target.

Goes through lsblk rather than globbing /dev/sd? or /dev/nvme?n?: a glob
cannot report a device's size, and both validate() and
to_archinstall_config() reject a DiskChoice whose size_bytes is unset -
so a disk list without sizes makes every installation fail before it can
even start.

list_disks() also excludes anything currently mounted (mounted_disks())
and known virtual, RAM-backed devices (_VIRTUAL_DEVICE) - both would
otherwise pass every other check and be offered as an ordinary install
target: the live boot medium in the first case, zram in the second.
"""
from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass
from typing import Callable

from .i18n import _, ngettext

Runner = Callable[..., subprocess.CompletedProcess]

# Up to EiB, not stopping at TiB: a 30 TiB array is an ordinary NAS disk
# today, and a list that renders anything larger as "1024.0 TiB" reads
# like a bug at exactly the moment the user is choosing which disk to
# erase.
_UNITS = ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB")

# zram devices are reported by lsblk with TYPE=disk - there is no more
# specific type - which makes this pattern load-bearing: without it,
# Arch live media (which run zram-generator for swap by default) would
# offer /dev/zram0 as a normal install target. An install onto it looks
# like it succeeded and is gone on the very next reboot, since zram
# lives in RAM and zram-generator recreates it empty on every boot.
#
# "ram", "loop" and "fd" are kept as belt-and-braces, not because a real
# gap was found here: loop devices are actually reported with TYPE=loop
# (verified on this machine, util-linux 2.42.2, against a real
# /dev/loop0 - `lsblk -b -d -n -o NAME,SIZE,TYPE` printed "loop0 0
# loop"), so the TYPE=="disk" check below already excludes them on its
# own, independently of this pattern. "ram" (the legacy ramdisk driver)
# and "fd" (legacy floppy) could not be verified the same way - no such
# device exists on this machine to test against - but their naming
# follows the same numbering convention as zram, and some older
# util-linux versions are documented to have reported them as TYPE=disk.
# Keeping them costs nothing; the risk this module exists to close does
# not.
_VIRTUAL_DEVICE = re.compile(r"^(zram|ram|loop|fd)\d+$")


# What each of the two lsblk calls asks for. Named here so the tests can
# assert on the same string the code sends, rather than a copy of it.
#
# -P for both, and not the columnar format this module used to parse:
# MODEL is "Samsung SSD 980 1TB" - three spaces inside one field - and a
# whitespace split turns that row into six tokens where five were
# expected. _parse_pairs() already existed for exactly this reason.
DISK_COLUMNS = "NAME,SIZE,TYPE,MODEL,TRAN,RM"
PARTITION_COLUMNS = "NAME,PKNAME,SIZE,FSTYPE,LABEL"


@dataclass(frozen=True)
class Partition:
    """One partition of a disk, as far as choosing between disks needs
    to know it: how big it is and what is on it."""
    device: str
    size_bytes: int
    fstype: str = ""
    label: str = ""


@dataclass(frozen=True)
class Disk:
    """A whole disk that could be installed onto.

    Everything past size_bytes has a default, so the two fields that
    identify a disk are still the whole of what a caller must supply.
    That is not only for the tests: mounted_disks() and the model both
    construct and compare Disk values, and a required field added here
    would have made every one of those sites carry information it has no
    way to know.

    WHY MORE THAN A NAME AND A SIZE
        Reported from the shipping medium on 10.08.2026: "man sieht in
        dem dropdown viel zu wenig infos". The list read "/dev/nvme0n1
        (953,9 GiB)", and two disks of the same size were two lines that
        differed by one character. This is the one page of the installer
        that destroys data, and it was the page with the least to decide
        on.
    """
    device: str
    size_bytes: int
    model: str = ""
    # lsblk's TRAN: "nvme", "sata", "usb", "" when it cannot tell.
    transport: str = ""
    removable: bool = False
    partitions: tuple[Partition, ...] = ()


def list_disks(*, runner: Runner | None = None) -> list[Disk]:
    """Return every real, installable, currently-unmounted whole disk
    lsblk reports, in lsblk's own order.

    -b reports bytes rather than a rounded human unit, -d omits
    partitions, -n omits the column header lsblk would otherwise print.
    The TYPE column is still checked explicitly rather than trusted to
    -d alone, since a row that is not a disk (e.g. a "rom" device
    slipping through) must never become a DiskChoice. TYPE=="disk" alone
    is not enough, though: zram devices report the same TYPE with no
    more specific one available, so _VIRTUAL_DEVICE filters by name as
    well - see its comment for exactly which of its patterns are
    load-bearing.

    Beyond that, a disk currently mounted anywhere - on itself or on one
    of its partitions - is excluded via mounted_disks(), using the same
    runner so a single fake in a test drives both lsblk calls. On a live
    installer, that is precisely the boot medium: it passes every other
    check here (TYPE=disk, a name _VIRTUAL_DEVICE does not match, a
    plausible size), and selecting it with wipe=True would overwrite the
    running installer's own root filesystem mid-install - worse than the
    zram case, which at least completes and only fails on reboot.
    """
    # Resolved here, not bound as a default: a default argument captures
    # subprocess.run at import time, which the test suite's isolation guard
    # cannot intercept.
    runner = runner or subprocess.run

    try:
        result = runner(
            ["lsblk", "-b", "-d", "-P", "-o", DISK_COLUMNS],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        # lsblk missing - part of util-linux, effectively always present
        # on Arch, but a damaged live image is not impossible, and every
        # other subprocess call in this codebase guards the same way.
        raise RuntimeError(
            _("Could not run lsblk: {reason}").format(reason=exc)
        ) from exc

    if result.returncode != 0:
        raise RuntimeError(
            _("lsblk failed: {reason}").format(
                reason=(result.stderr or result.stdout).strip()
            )
        )

    # Not wrapped in try/except: if lsblk cannot report what is mounted,
    # this propagates as-is (the same RuntimeError mounted_disks() itself
    # raises) rather than being swallowed into "assume nothing is
    # mounted". An installer that cannot tell which disk it is currently
    # running from must refuse rather than guess - the same asymmetry
    # that makes _VIRTUAL_DEVICE a denylist rather than requiring an
    # allowlist of known-safe names.
    mounted = mounted_disks(runner=runner)
    contents = _partitions(runner=runner)

    disks: list[Disk] = []
    for line in result.stdout.splitlines():
        fields = _parse_pairs(line)
        if fields is None:
            # Not a well-formed KEY="value" row - nothing to extract.
            continue
        name = fields.get("NAME", "")
        if not name or fields.get("TYPE") != "disk":
            continue
        if _VIRTUAL_DEVICE.match(name):
            continue
        if name in mounted:
            continue
        try:
            size_bytes = int(fields.get("SIZE", ""))
        except ValueError:
            continue
        disks.append(Disk(
            device=f"/dev/{name}",
            size_bytes=size_bytes,
            model=fields.get("MODEL", "").strip(),
            transport=fields.get("TRAN", "").strip(),
            # lsblk prints RM as "0" or "1"; anything else is a version
            # that does not answer, and "not removable" is the reading
            # that does not talk somebody into erasing an internal disk.
            removable=fields.get("RM", "0") == "1",
            partitions=contents.get(name, ()),
        ))
    return disks


def _partitions(*, runner: Runner) -> dict[str, tuple[Partition, ...]]:
    """What is on each disk today, keyed by the disk's lsblk name.

    Its own call rather than more columns on the one above, because the
    two ask about different things: that one is `-d`, whole disks only,
    and this one is the opposite. mounted_disks() is a second call for
    the same reason and this is the third; each is a few milliseconds
    against a decision that erases a disk.

    A failure here is not fatal. Knowing that /dev/sda holds a 500 GiB
    NTFS partition makes the choice safer, and not knowing it leaves the
    installer exactly where it was before this existed - so a broken or
    old lsblk costs the detail, not the page.
    """
    try:
        result = runner(
            ["lsblk", "-b", "-P", "-o", PARTITION_COLUMNS],
            capture_output=True,
            text=True,
        )
    except OSError:
        return {}
    if result.returncode != 0:
        return {}

    found: dict[str, list[Partition]] = {}
    for line in result.stdout.splitlines():
        fields = _parse_pairs(line)
        if fields is None:
            continue
        parent = fields.get("PKNAME", "")
        name = fields.get("NAME", "")
        if not parent or not name:
            # A whole disk (empty PKNAME), or a row with no name.
            continue
        try:
            size_bytes = int(fields.get("SIZE", ""))
        except ValueError:
            continue
        found.setdefault(parent, []).append(Partition(
            device=f"/dev/{name}",
            size_bytes=size_bytes,
            fstype=fields.get("FSTYPE", "").strip(),
            label=fields.get("LABEL", "").strip(),
        ))
    return {parent: tuple(parts) for parent, parts in found.items()}


def describe(disk: Disk) -> str:
    """The one line that names a disk: what it is, then how big.

    The model first, because that is the word the user recognises from
    the sticker or the invoice. The device node is NOT here - it goes
    underneath, in describe_contents()'s line, since /dev/nvme0n1 is
    what the installer needs and the least of what the user is choosing
    by.
    """
    name = disk.model or _("Disk")
    return f"{name} \N{EN DASH} {human_size(disk.size_bytes)}"


def describe_contents(disk: Disk) -> str:
    """The device node, how it is attached, and what is on it now.

    The last part is the point. A disk with a 500 GiB NTFS partition
    called "Windows" is a disk somebody will recognise as the wrong one,
    and this page is where that has to happen - the next confirmation is
    the last.

    At most three partitions are named. A disk with eleven would push
    the row taller than the ones around it, and by the eleventh the
    question has been answered anyway; the count in front says how many
    there are in total, so nothing is hidden silently.
    """
    parts = [disk.device]
    if disk.transport:
        parts.append(disk.transport.upper())
    if disk.removable:
        parts.append(_("removable"))

    if not disk.partitions:
        parts.append(_("no partitions"))
        return " \N{BULLET} ".join(parts)

    named = []
    for partition in disk.partitions[:3]:
        kind = partition.fstype or _("unknown")
        if partition.label:
            named.append(f"{kind} “{partition.label}” "
                         f"{human_size(partition.size_bytes)}")
        else:
            named.append(f"{kind} {human_size(partition.size_bytes)}")
    if len(disk.partitions) > 3:
        named.append("\N{HORIZONTAL ELLIPSIS}")

    parts.append(ngettext("{count} partition", "{count} partitions",
                          len(disk.partitions)).format(
                              count=len(disk.partitions))
                 + ": " + ", ".join(named))
    return " \N{BULLET} ".join(parts)


def _parse_pairs(line: str) -> dict[str, str] | None:
    """Parse one line of `lsblk -P` output into a field dict.

    -P quotes every value in shell-word syntax (KEY="value", with
    internal quotes and backslashes escaped the way a shell would need
    them) specifically so scripts do not have to guess at column widths
    - unlike the plain columnar format list_disks() itself parses just
    above, where an empty PKNAME or MOUNTPOINTS value collapses away
    under a naive whitespace split (a whole disk's PKNAME is always
    empty, and most partitions are not mounted), making rows with a
    different number of real fields indistinguishable by token count
    alone. shlex implements exactly the word-splitting rules -P output
    is meant to be read with.

    Returns None for a line that is not a well-formed run of KEY="value"
    tokens, so the caller can skip it rather than guess at its meaning.
    """
    try:
        tokens = shlex.split(line)
    except ValueError:
        # Unbalanced quoting - not a row this format could have produced.
        return None
    fields: dict[str, str] = {}
    for token in tokens:
        key, sep, value = token.partition("=")
        if not sep:
            return None
        fields[key] = value
    return fields


def mounted_disks(*, runner: Runner | None = None) -> set[str]:
    """Names of disks that currently have something mounted, on the
    disk itself or on any of its partitions.

    The live medium the installer booted from is an ordinary disk by
    every other measure - same naming, same type, a plausible size.
    Installing onto it overwrites the running installer's own
    filesystem. Nothing but the mount table distinguishes it.
    """
    # Resolved here, not bound as a default: a default argument captures
    # subprocess.run at import time, which the test suite's isolation guard
    # cannot intercept.
    runner = runner or subprocess.run

    try:
        result = runner(
            ["lsblk", "-P", "-n", "-o", "NAME,PKNAME,MOUNTPOINTS"],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise RuntimeError(
            _("Could not run lsblk: {reason}").format(reason=exc)
        ) from exc

    if result.returncode != 0:
        raise RuntimeError(
            _("lsblk failed: {reason}").format(
                reason=(result.stderr or result.stdout).strip()
            )
        )

    mounted: set[str] = set()
    for line in result.stdout.splitlines():
        fields = _parse_pairs(line)
        if fields is None:
            # Not a well-formed KEY="value" row - skipped, not guessed at.
            continue
        name = fields.get("NAME", "")
        pkname = fields.get("PKNAME", "")
        mountpoints = fields.get("MOUNTPOINTS", "")
        if not name or not mountpoints:
            continue
        # A mounted partition's parent disk is unsafe; a disk mounted
        # directly (no PKNAME - no partition table) is unsafe by its own
        # name.
        mounted.add(pkname or name)
    return mounted


def human_size(size_bytes: int) -> str:
    """Format a byte count for display, e.g. '20.0 GiB'.

    Not passed through _(): unit abbreviations (KiB, MiB, GiB, TiB) are
    conventionally left unlocalised - lsblk, du and archinstall's own
    output all print them the same way regardless of locale.
    """
    value = float(size_bytes)
    unit = _UNITS[0]
    for unit in _UNITS[:-1]:
        if value < 1024:
            break
        value /= 1024
    else:
        unit = _UNITS[-1]
    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"
