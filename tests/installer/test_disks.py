# SPDX-License-Identifier: GPL-3.0-or-later
import subprocess

import pytest

from installer.core.disks import (
    DISK_COLUMNS, PARTITION_COLUMNS, Disk, Partition, describe,
    describe_contents, human_size, list_disks, mounted_disks,
)
from installer.core.i18n import _

def _row(**fields) -> str:
    """One line of lsblk -P output, built from the fields a test cares
    about. The rest are present and empty, which is what lsblk itself
    prints for a field it cannot fill - a fake that omitted them would
    be testing a shape lsblk never produces."""
    complete = {"NAME": "", "SIZE": "0", "TYPE": "disk",
                "MODEL": "", "TRAN": "", "RM": "0"}
    complete.update(fields)
    return " ".join(f'{key}="{value}"' for key, value in complete.items()) + "\n"


LSBLK_OUTPUT = (
    _row(NAME="sda", SIZE="500107862016")
    + _row(NAME="sda1", SIZE="524288000", TYPE="part")
    + _row(NAME="sda2", SIZE="499583373312", TYPE="part")
    + _row(NAME="nvme0n1", SIZE="1024209543168")
    + _row(NAME="zram0", SIZE="8589934592")
    + _row(NAME="ram0", SIZE="67108864")
    + _row(NAME="loop0", SIZE="4096")
)


def _runner(stdout: str, returncode: int = 0):
    def run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")
    return run


def test_lsblk_is_invoked_with_the_documented_flags():
    """-b for bytes, -d to omit partitions, -n to omit the header.

    list_disks() makes a second lsblk call internally now (the mount
    check - see the mounted_disks() tests below), so every call is
    recorded rather than overwriting a single slot; this only asserts
    the size-listing one is among them.
    """
    seen = []

    def run(cmd, **kw):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    list_disks(runner=run)
    assert ["lsblk", "-b", "-d", "-P", "-o", DISK_COLUMNS] in seen


def test_disks_are_parsed_with_dev_prefix_and_byte_sizes():
    disks = list_disks(runner=_runner(LSBLK_OUTPUT))
    assert Disk(device="/dev/sda", size_bytes=500107862016) in disks
    assert Disk(device="/dev/nvme0n1", size_bytes=1024209543168) in disks


def test_partitions_are_filtered_out_even_though_minus_d_should_already_do_it():
    """-d already excludes partitions at the source; this is a second,
    independent guard against a TYPE column that is not 'disk'."""
    disks = list_disks(runner=_runner(LSBLK_OUTPUT))
    assert "/dev/sda1" not in [d.device for d in disks]
    assert "/dev/sda2" not in [d.device for d in disks]


def test_only_type_disk_rows_are_kept():
    """zram, ram and loop devices are reported by lsblk with TYPE=disk too
    (there is no more specific type) but are virtual, RAM-backed block
    devices, not installable storage. An install onto /dev/zram0 appears
    to succeed and vanishes on the very next reboot, since zram-generator
    resets it on every boot - a real device on Arch live media, which run
    zram-generator for swap by default. Real disks must be the only ones
    offered."""
    disks = list_disks(runner=_runner(LSBLK_OUTPUT))
    assert [d.device for d in disks] == ["/dev/sda", "/dev/nvme0n1"]


def test_zram_device_is_excluded():
    out = "zram0 8589934592 disk\n"
    assert list_disks(runner=_runner(out)) == []


def test_ram_device_is_excluded():
    out = "ram0 67108864 disk\n"
    assert list_disks(runner=_runner(out)) == []


def test_loop_device_is_excluded():
    """Belt-and-braces, not a regression test for a real gap: real lsblk
    reports a loop device with TYPE=loop, not TYPE=disk (verified on
    this machine, util-linux 2.42.2, against an actual /dev/loop0), so
    the pre-existing `kind != "disk"` check already excludes it on its
    own. This row is synthetic - real lsblk never emits it - kept only
    to document that _VIRTUAL_DEVICE would still catch it if some other
    lsblk version ever did."""
    out = "loop0 4096 disk\n"
    assert list_disks(runner=_runner(out)) == []


def test_empty_output_yields_no_disks():
    assert list_disks(runner=_runner("")) == []


def test_malformed_line_is_skipped_not_crashed_on():
    out = _row(NAME="sda", SIZE="500107862016") + "notenoughcolumns\n"
    assert [d.device for d in list_disks(runner=_runner(out))] == ["/dev/sda"]


def test_lsblk_failure_raises_runtime_error():
    with pytest.raises(RuntimeError, match="lsblk"):
        list_disks(runner=_runner("boom", returncode=1))


def test_missing_lsblk_raises():
    """If the lsblk binary is missing, FileNotFoundError is raised before any
    CompletedProcess exists - it must be caught explicitly, not inferred
    from a returncode. Same defect class as five earlier tasks."""
    def run(cmd, **kw):
        raise FileNotFoundError(2, "No such file or directory", "lsblk")

    with pytest.raises(RuntimeError, match="lsblk"):
        list_disks(runner=run)


# --- mounted_disks() -----------------------------------------------------
#
# The live medium the installer booted from is an ordinary disk by every
# measure list_disks() otherwise checks: TYPE=disk, an sdX/nvme0n1 name
# _VIRTUAL_DEVICE does not match, a plausible size. Only the mount table
# tells it apart from a real install target - selecting it with wipe=True
# would overwrite the running installer's own root filesystem mid-install.


def _pairs_runner(stdout: str, returncode: int = 0):
    def run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")
    return run


def test_mounted_disks_is_invoked_with_the_documented_flags():
    seen = {}

    def run(cmd, **kw):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    mounted_disks(runner=run)
    assert seen["cmd"] == ["lsblk", "-P", "-n", "-o", "NAME,PKNAME,MOUNTPOINTS"]


def test_disk_with_a_mounted_partition_is_reported():
    """The common case: the boot medium's own filesystem is mounted at
    /run/archiso/bootmnt on one of its partitions, not on the whole disk
    itself."""
    out = (
        'NAME="sda" PKNAME="" MOUNTPOINTS=""\n'
        'NAME="sda1" PKNAME="sda" MOUNTPOINTS="/run/archiso/bootmnt"\n'
    )
    assert mounted_disks(runner=_pairs_runner(out)) == {"sda"}


def test_disk_mounted_directly_is_reported():
    """A whole disk mounted with no partition table has an empty PKNAME
    of its own - MOUNTPOINTS on its own row is what marks it, not a
    child row's PKNAME."""
    out = 'NAME="sdb" PKNAME="" MOUNTPOINTS="/run/archiso/bootmnt"\n'
    assert mounted_disks(runner=_pairs_runner(out)) == {"sdb"}


def test_disk_with_no_mounted_children_is_not_reported():
    out = (
        'NAME="sdc" PKNAME="" MOUNTPOINTS=""\n'
        'NAME="sdc1" PKNAME="sdc" MOUNTPOINTS=""\n'
    )
    assert mounted_disks(runner=_pairs_runner(out)) == set()


def test_malformed_pairs_row_is_skipped_not_crashed_on():
    out = (
        "this row is not key=value pairs at all\n"
        'NAME="sdd" PKNAME="" MOUNTPOINTS="/mnt"\n'
    )
    assert mounted_disks(runner=_pairs_runner(out)) == {"sdd"}


def test_mounted_disks_lsblk_failure_raises_runtime_error():
    with pytest.raises(RuntimeError, match="lsblk"):
        mounted_disks(runner=_pairs_runner("boom", returncode=1))


def test_mounted_disks_missing_lsblk_raises():
    def run(cmd, **kw):
        raise FileNotFoundError(2, "No such file or directory", "lsblk")

    with pytest.raises(RuntimeError, match="lsblk"):
        mounted_disks(runner=run)


# --- mounted_disks() wired into list_disks() ------------------------------


def test_list_disks_excludes_a_disk_whose_partition_is_mounted():
    """The realistic shape of the boot medium: mounted via a partition,
    e.g. /run/archiso/bootmnt on an archiso build."""
    size_output = (
        _row(NAME="sda", SIZE="500107862016")
        + _row(NAME="nvme0n1", SIZE="1024209543168")
    )
    mount_output = (
        'NAME="sda" PKNAME="" MOUNTPOINTS=""\n'
        'NAME="sda1" PKNAME="sda" MOUNTPOINTS="/run/archiso/bootmnt"\n'
        'NAME="nvme0n1" PKNAME="" MOUNTPOINTS=""\n'
    )

    def run(cmd, **kw):
        if DISK_COLUMNS in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=size_output, stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout=mount_output, stderr="")

    assert [d.device for d in list_disks(runner=run)] == ["/dev/nvme0n1"]


def test_list_disks_excludes_a_disk_mounted_directly():
    size_output = "sdb 500107862016 disk\n"
    mount_output = 'NAME="sdb" PKNAME="" MOUNTPOINTS="/run/archiso/bootmnt"\n'

    def run(cmd, **kw):
        if DISK_COLUMNS in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=size_output, stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout=mount_output, stderr="")

    assert list_disks(runner=run) == []


def test_list_disks_keeps_a_disk_with_no_mounted_children():
    size_output = _row(NAME="sdc", SIZE="500107862016")
    mount_output = (
        'NAME="sdc" PKNAME="" MOUNTPOINTS=""\n'
        'NAME="sdc1" PKNAME="sdc" MOUNTPOINTS=""\n'
    )

    def run(cmd, **kw):
        if DISK_COLUMNS in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=size_output, stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout=mount_output, stderr="")

    assert [d.device for d in list_disks(runner=run)] == ["/dev/sdc"]


def test_list_disks_propagates_a_mount_check_failure_rather_than_guessing():
    """If lsblk cannot report what is mounted, list_disks() must refuse
    rather than silently offer every disk regardless of mount status: an
    installer that cannot tell which disk it is running from must not
    offer to erase one. See the report for the full reasoning."""
    size_output = "sdd 500107862016 disk\n"

    def run(cmd, **kw):
        if DISK_COLUMNS in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=size_output, stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")

    with pytest.raises(RuntimeError, match="lsblk"):
        list_disks(runner=run)


def test_list_disks_and_mounted_disks_use_distinguishable_lsblk_invocations():
    """A single fake runner answers list_disks()'s two lsblk calls
    differently based on their exact arguments. If a future change ever
    made one call's result silently stand in for the other, this test
    would catch it: reusing the size output for the mount check would
    parse to zero mounted disks (wrong, undercounting); reusing the
    mount output for the size listing would parse to zero disks with a
    valid size (wrong, overcounting - everything would vanish)."""
    size_output = (
        _row(NAME="sda", SIZE="500107862016")
        + _row(NAME="sdb", SIZE="500107862016")
    )
    mount_output = (
        'NAME="sda" PKNAME="" MOUNTPOINTS=""\n'
        'NAME="sda1" PKNAME="sda" MOUNTPOINTS="/run/archiso/bootmnt"\n'
        'NAME="sdb" PKNAME="" MOUNTPOINTS=""\n'
    )

    def run(cmd, **kw):
        if DISK_COLUMNS in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=size_output, stderr="")
        if "NAME,PKNAME,MOUNTPOINTS" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=mount_output, stderr="")
        if PARTITION_COLUMNS in cmd:
            # The third call, which describes what is on each disk. It
            # is answered rather than refused, and answered emptily:
            # this test is about the first two telling each other apart.
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected lsblk invocation: {cmd}")

    assert [d.device for d in list_disks(runner=run)] == ["/dev/sdb"]


def test_human_size_formats_bytes():
    assert human_size(0) == "0 B"
    assert human_size(1023) == "1023 B"


def test_human_size_formats_kib_mib_gib_tib():
    assert human_size(1024) == "1.0 KiB"
    assert human_size(1024 ** 2) == "1.0 MiB"
    assert human_size(1024 ** 3) == "1.0 GiB"
    assert human_size(2 * 1024 ** 4) == "2.0 TiB"


def test_human_size_of_a_realistic_disk():
    assert human_size(21474836480) == "20.0 GiB"


def test_human_size_does_not_stop_at_tebibytes():
    """A 30 TiB array is an ordinary NAS disk. Rendering anything above a
    tebibyte as "1024.0 TiB" reads like a bug at exactly the moment the
    user picks which disk to erase."""
    assert human_size(1024 ** 5) == "1.0 PiB"
    assert human_size(3 * 1024 ** 6) == "3.0 EiB"


# --- what a disk says about itself, for the page that erases it -----------


def test_a_disk_carries_its_model_transport_and_partitions():
    """The fields the selection page needs, read off lsblk rather than
    inferred. Before this, a Disk was a name and a size, and two disks
    of the same size were two lines that differed by one character."""
    disks = list_disks(runner=_two_disks_with_partitions())

    nvme = next(d for d in disks if d.device == "/dev/nvme0n1")
    assert nvme.model == "Samsung SSD 980 1TB"
    assert nvme.transport == "nvme"
    assert nvme.removable is False
    assert [p.device for p in nvme.partitions] == [
        "/dev/nvme0n1p1", "/dev/nvme0n1p2"]
    assert nvme.partitions[1].fstype == "ntfs"
    assert nvme.partitions[1].label == "Windows"


def test_a_usb_stick_is_reported_as_removable():
    """RM=1, and it has to survive into the description: an installer
    offering to erase the stick it booted from is a mistake worth
    labelling. (It is normally filtered out for being mounted - this is
    the case where it is not.)"""
    disks = list_disks(runner=_two_disks_with_partitions())

    stick = next(d for d in disks if d.device == "/dev/sdb")
    assert stick.removable is True
    assert stick.transport == "usb"
    assert _("removable") in describe_contents(stick)


def test_describe_names_the_model_and_the_size():
    disk = Disk(device="/dev/nvme0n1", size_bytes=1024209543168,
                model="Samsung SSD 980 1TB")
    text = describe(disk)
    assert "Samsung SSD 980 1TB" in text
    assert human_size(1024209543168) in text


def test_describe_falls_back_when_lsblk_reports_no_model():
    """A virtual disk under QEMU has an empty MODEL. The row still has
    to say something other than a dash where its name should be."""
    disk = Disk(device="/dev/vda", size_bytes=64 * 1024**3)
    assert describe(disk).startswith(_("Disk"))
    assert human_size(64 * 1024**3) in describe(disk)


def test_describe_contents_names_what_is_on_the_disk():
    disk = Disk(
        device="/dev/sda", size_bytes=500107862016, transport="sata",
        partitions=(
            Partition(device="/dev/sda1", size_bytes=524288000, fstype="vfat"),
            Partition(device="/dev/sda2", size_bytes=499583373312,
                      fstype="ntfs", label="Windows"),
        ))
    text = describe_contents(disk)
    assert "/dev/sda" in text
    assert "SATA" in text
    assert "ntfs" in text
    assert "Windows" in text


def test_an_empty_disk_says_so_rather_than_saying_nothing():
    """"" and "no partitions" read very differently to somebody deciding
    which disk to erase."""
    disk = Disk(device="/dev/sdc", size_bytes=500107862016)
    assert _("no partitions") in describe_contents(disk)


def test_a_disk_with_many_partitions_is_summarised_not_listed():
    """The count is exact, the naming stops at three. A row that grows
    with the partition table pushes the disks below it off the page."""
    disk = Disk(
        device="/dev/sda", size_bytes=500107862016,
        partitions=tuple(
            Partition(device=f"/dev/sda{i}", size_bytes=1024**3, fstype="ext4")
            for i in range(1, 8)))
    text = describe_contents(disk)
    assert "7" in text
    assert text.count("ext4") == 3
    assert "\N{HORIZONTAL ELLIPSIS}" in text


def test_a_partition_check_that_fails_costs_the_detail_not_the_page():
    """lsblk answering nothing for the partition call must still yield
    disks - the description is an improvement on the choice, not a
    precondition for making one."""
    def run(cmd, **kw):
        if DISK_COLUMNS in cmd:
            return subprocess.CompletedProcess(
                cmd, 0, stdout=_row(NAME="sda", SIZE="500107862016"), stderr="")
        if PARTITION_COLUMNS in cmd:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    disks = list_disks(runner=run)
    assert [d.device for d in disks] == ["/dev/sda"]
    assert disks[0].partitions == ()


def _two_disks_with_partitions():
    disk_output = (
        _row(NAME="nvme0n1", SIZE="1024209543168",
             MODEL="Samsung SSD 980 1TB", TRAN="nvme", RM="0")
        + _row(NAME="sdb", SIZE="15728640000",
               MODEL="Basic Line", TRAN="usb", RM="1")
    )
    partition_output = (
        'NAME="nvme0n1" PKNAME="" SIZE="1024209543168" FSTYPE="" LABEL=""\n'
        'NAME="nvme0n1p1" PKNAME="nvme0n1" SIZE="536870912" FSTYPE="vfat"'
        ' LABEL="EFI"\n'
        'NAME="nvme0n1p2" PKNAME="nvme0n1" SIZE="1023672672256" FSTYPE="ntfs"'
        ' LABEL="Windows"\n'
    )

    def run(cmd, **kw):
        if DISK_COLUMNS in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=disk_output, stderr="")
        if PARTITION_COLUMNS in cmd:
            return subprocess.CompletedProcess(
                cmd, 0, stdout=partition_output, stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    return run
