#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Proves that a real archinstall accepts what the real installer code
# produces - the configuration AND the command line.
#
# This script deliberately does NOT build its own archinstall invocation.
# It calls installer.core.runner.install(..., dry_run=True), so the argv
# that ships is the argv that gets tested: --mountpoint and --offline
# used to appear in no test at all, and a wrong spelling of either kills
# every real installation at the argument parser while every mocked test
# still passes.
#
# Needs root INSIDE the container (see README.md for why): archinstall's
# DiskLayoutConfiguration.parse_arg only parses a device_modifications
# entry for a device it can actually find via lsblk/parted
# (device_handler.get_device). If the named device does not exist at
# all - as /dev/vda does not in a plain container - the whole entry is
# silently DROPPED: no error, no partitions parsed, and config_type
# still reports "Manual" as if nothing were wrong. A config naming a
# non-existent device would therefore look accepted no matter what
# garbage is inside its partition list, which defeats the entire point
# of this test. So this script backs a real loop device with a sparse
# file and points the generated config at that instead of a fake path -
# only then does archinstall actually walk the partition table and
# exercise Size.parse_args, Unit lookups, and the alignment/overlap
# checks this test exists to guard.
set -euo pipefail

WORK=$(mktemp -d)
DISK_IMAGE="$WORK/disk.img"
LOOP_DEV=""

cleanup() {
    if [[ -n "$LOOP_DEV" ]]; then
        losetup -d "$LOOP_DEV" 2>/dev/null || true
    fi
    rm -rf "$WORK"
}
trap cleanup EXIT

DISK_SIZE_BYTES=$((4 * 1024 * 1024 * 1024))  # 4 GiB, comfortably above MIN_DISK_MIB
truncate -s "$DISK_SIZE_BYTES" "$DISK_IMAGE"
LOOP_DEV=$(losetup -f --show "$DISK_IMAGE")

# archinstall writes the configuration it actually parsed into its log
# directory before --dry-run returns. Removing any older copy first means
# the check below can never pass on a stale file from an earlier run.
ARCHINSTALL_LOG_DIR=/var/log/archinstall
rm -f "$ARCHINSTALL_LOG_DIR/user_configuration.json"

python - "$WORK" "$LOOP_DEV" "$DISK_SIZE_BYTES" "$ARCHINSTALL_LOG_DIR" <<'PY'
import json, subprocess, sys
from pathlib import Path

from installer.core.model import (
    InstallConfig, DiskChoice, UserAccount, WifiCredentials, ZeposOptions,
)
from installer.core.runner import install
from installer.core.source import PackageSource
from installer.core.translate import to_archinstall_config

work = Path(sys.argv[1])
loop_dev = sys.argv[2]
disk_size_bytes = int(sys.argv[3])
log_dir = Path(sys.argv[4])
target_root = work / "target"
target_root.mkdir()

cfg = InstallConfig(
    language="de", keymap="de-latin1", timezone="Europe/Berlin",
    locale="de_DE", hostname="zepos",
    disk=DiskChoice(device=loop_dev, size_bytes=disk_size_bytes),
    users=[UserAccount(username="lars", password="langgenug")],
    root_password="rootlanggenug",
    wifi=WifiCredentials("Fritz", "wlanpw"),
    zepos=ZeposOptions(enable_plugins=False, weather_location="Wien"),
)

# archinstall's own config loader does NOT reject wipe=True paired with an
# empty partition list - verified empirically: it loads such a config and
# exits 0 under --dry-run, because nothing in
# DiskLayoutConfiguration.parse_arg treats an empty partitions list as an
# error. That combination would erase the target disk for real and create
# nothing on it, so relying on archinstall's exit code alone is not enough
# to guard against it. tests/installer/test_translate.py already guards
# this at the unit level; this check re-asserts it here, against the
# config this script is about to hand to archinstall, so a regression is
# caught before the --dry-run call could mask it again.
preview = to_archinstall_config(cfg, PackageSource.OFFLINE)
mod = preview["disk_config"]["device_modifications"][0]
if mod["wipe"] and not mod["partitions"]:
    sys.exit(
        "REFUSED: wipe=True with an empty partition list would erase the "
        "disk and create nothing. archinstall's config loader accepts "
        "this silently - see tests/integration/README.md."
    )

# The only thing this script adds to the shipped command line, and it
# adds it at the very edge, where it is visible. Both flags are about
# the CONTAINER, not about ZepOS: there is no network to check a version
# against and no wireless device to look at. Everything else - including
# --mountpoint and --offline - comes from install() itself, which is the
# entire point of driving it from here instead of rebuilding the call.
CONTAINER_ONLY_FLAGS = ["--skip-version-check", "--skip-wifi-check"]


def runner(cmd, **kwargs):
    if cmd and cmd[0] == "archinstall":
        cmd = [*cmd, *CONTAINER_ONLY_FLAGS]
        print("+ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, **kwargs)


warnings = []
code = install(
    cfg,
    source=PackageSource.OFFLINE,
    dry_run=True,
    target_root=target_root,
    runner=runner,
    # A container has no firmware of its own to report, and --dry-run
    # partitions nothing. The refusal this bypasses is about the machine
    # being installed, which here is no machine at all.
    is_uefi=lambda: True,
    on_warning=warnings.append,
)

if code != 0:
    sys.exit(f"archinstall rejected the ZepOS configuration (exit code {code}).")

# --- what a dry run must NOT have done (spec 8.3, 11) -----------------
#
# A dry run installs nothing, so there is no filesystem under
# --mountpoint to finish off, and install() must leave the target root
# exactly as it found it. It used to write the wireless profile - with
# the passphrase in clear text - and the ZepOS settings there anyway,
# which for a caller who leaves target_root at its default means writing
# them into the HOST's /mnt.
#
# The positive side of those two writes (the profile at mode 0600, the
# settings' content) is covered in tests/installer/test_runner.py against
# a real target root and a real, non-dry run. Neither write involves
# archinstall at all, so nothing is lost by proving them there; what
# needs a REAL archinstall is the configuration and the command line,
# which is what the rest of this script is about.
#
# The warnings list is part of the same check: on_warning() is only ever
# called from install()'s post-installation step, so anything in it here
# means that step ran when it must not have.
if warnings:
    sys.exit("REFUSED: a dry run reached the post-installation step: " + "; ".join(warnings))

leaked = [
    path
    for path in (
        target_root / "etc/NetworkManager/system-connections/Fritz.nmconnection",
        target_root / "etc/skel/.config/zepos/user-settings.json",
    )
    if path.exists()
]
if leaked:
    sys.exit(
        "REFUSED: a dry run wrote into the target root: "
        + ", ".join(str(path) for path in leaked)
    )

# --- did archinstall HONOUR our keys, or merely tolerate them? --------
#
# archinstall ignores unknown top-level keys in silence. A misnamed
# bootloader_config, locale_config or network_config would therefore load
# without a word and install a system with the wrong keyboard layout, the
# wrong locale, or no NetworkManager at all - which would in turn make
# the wireless profile above useless. An exit code of 0 says nothing
# about any of that.
#
# What does say something: archinstall writes the configuration it
# actually PARSED to user_configuration.json before --dry-run returns
# (guided.py calls config.save() ahead of the dry-run return; the default
# destination is its log directory). Everything checked below therefore
# went through archinstall's own parse-and-serialise round trip, so a key
# it did not understand shows up here as a missing or default value.

saved_path = log_dir / "user_configuration.json"
if not saved_path.exists():
    sys.exit(
        f"REFUSED: archinstall wrote no {saved_path}. Without it this test cannot "
        "tell an honoured key from a silently discarded one - check where this "
        "archinstall version saves its parsed configuration."
    )
saved = json.loads(saved_path.read_text(encoding="utf-8"))


def at(document, path):
    for step in path:
        if isinstance(step, int):
            if not isinstance(document, list) or len(document) <= step:
                return None
            document = document[step]
        else:
            if not isinstance(document, dict) or step not in document:
                return None
            document = document[step]
    return document


EXPECTED = [
    (("hostname",), "zepos"),
    (("timezone",), "Europe/Berlin"),
    (("locale_config", "kb_layout"), "de-latin1"),
    (("locale_config", "sys_lang"), "de_DE"),
    (("bootloader_config", "bootloader"), "Grub"),
    (("network_config", "type"), "nm"),
    (("app_config", "audio_config", "audio"), "pipewire"),
    (("swap", "enabled"), True),
    (("swap", "algorithm"), "zstd"),
    (("mirror_config", "custom_repositories", 0, "name"), "zepos"),
    (("disk_config", "device_modifications", 0, "device"), loop_dev),
]

dropped = []
for path, expected in EXPECTED:
    actual = at(saved, path)
    if actual != expected:
        dropped.append(f"{'.'.join(str(p) for p in path)}: expected {expected!r}, got {actual!r}")

if "zepos-desktop" not in (at(saved, ("packages",)) or []):
    dropped.append("packages: zepos-desktop is missing")

if dropped:
    sys.exit(
        "REFUSED: archinstall did not honour these keys (it accepts unknown "
        "keys in silence, so the exit code above proves nothing about them):\n  "
        + "\n  ".join(dropped)
    )

print("OK: every ZepOS key survived archinstall's own parsing.")
PY

echo "OK: archinstall accepted the ZepOS configuration and command line."
