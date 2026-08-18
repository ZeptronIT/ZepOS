<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Integration test: archinstall dry run

## What this proves

That `archinstall` 4.4 actually accepts the `config.json` and `creds.json`
produced by the real installer code (`to_archinstall_config` /
`to_archinstall_creds` in `installer/core/translate.py`), not a
hand-written fixture that could silently drift from what the code emits.

`--dry-run` builds the configuration and exits before touching any disk.
No root is required on the *host*, and no real device is at risk.

It also proves it against the *command line that ships*: the script calls
`installer.core.runner.install(..., dry_run=True)` instead of assembling
its own `archinstall` invocation. That is the whole reason it was
rewritten - `--mountpoint` and `--offline` appeared in no test at all,
and a wrong spelling of either kills every real installation at the
argument parser while every mocked test keeps passing. The only thing
the script adds is `--skip-version-check --skip-wifi-check`, appended at
the edge in a runner wrapper, because both are facts about the container
rather than about ZepOS.

And it proves the keys were *honoured*, not merely tolerated.
`archinstall` ignores unknown top-level keys in silence, so a misnamed
`bootloader_config`, `locale_config` or `network_config` would load
without a word and produce a system with the wrong keyboard layout, the
wrong locale, or no NetworkManager - which would in turn make the
wireless profile useless. Exit code 0 says nothing about any of that. So
after the dry run the script reads
`/var/log/archinstall/user_configuration.json`, the configuration
archinstall itself parsed and wrote back out (`guided.py` calls
`config.save()` before the `--dry-run` return), and compares the values
that matter against what was sent. A key archinstall did not understand
appears there as missing or default.

Finally it checks what a dry run must *not* have done to the target: the
wireless profile and the ZepOS settings must be absent from the target
root, and no post-installation warning may have been raised. A dry run
installs nothing, so there is no filesystem under `--mountpoint` to
finish off - and `install()` used to write both files there regardless,
which for the default `target_root` means writing a cleartext wireless
passphrase into the host's `/mnt`.

The positive side of those two writes (the profile at mode 600 per spec
8.3 and 11, and the ZepOS options in
`/etc/skel/.config/zepos/user-settings.json`) is covered by
`tests/installer/test_runner.py` against a real target root and a real,
non-dry run. Neither write goes anywhere near archinstall, so nothing is
lost by proving them there instead.

> **Unverified assumption.** The location of `user_configuration.json`
> was read out of archinstall 4.4's source (`logger.directory`, i.e.
> `/var/log/archinstall`), not observed on a running container. If it is
> somewhere else, the script fails loudly with a message saying exactly
> that instead of passing quietly - the correct failure mode, but it does
> mean the first container run may need this path corrected.

## What this does NOT prove

That a real installation results in a bootable system. That needs a real
disk image booted in QEMU and belongs to a later sub-project, once the
ISO exists.

It also does not exercise archinstall's actual partitioning, filesystem
creation or bootloader installation code paths - `--dry-run` stops before
any of that runs. It only proves that archinstall's config *loader*
accepts the shape of what we send it, including walking the full
partition table (see below for why that requires a real device).

## Why the container needs `--privileged`, not just `--network host`

Two independent requirements, for two different reasons:

**`--network host` (network):** the container needs to reach the Arch
Linux mirrors to install `archinstall`, `python` and `openssl`. A VPN on
the host routes all three RFC1918 ranges (10.0.0.0/8, 172.16.0.0/12,
192.168.0.0/16); Docker's default bridge network falls inside one of
them, so a bridged container has no usable network at all. `--network
host` sidesteps that. See Spec §10.1.

**`--privileged` (loop devices):** discovered while building this test,
and not something the original task brief anticipated. archinstall's
`DiskLayoutConfiguration.parse_arg` resolves the configured device via
`device_handler.get_device()`, which only recognizes devices it actually
finds through `lsblk`/`parted` enumeration. If the named device does not
exist at all - which is exactly the case for a placeholder path like
`/dev/vda` inside a plain container that has no such device - the entire
`device_modifications` entry is **silently dropped**: no error, no
partitions parsed, and `config_type` still reports `manual_partitioning`
as if nothing were wrong. Verified directly: running this test's original
form (pointing at `/dev/vda`, which the container doesn't have) against a
config with a deliberately broken partition (`unit: "Percent"`, which
does not exist in archinstall's `Unit` enum and should raise `KeyError`)
still printed "OK" and exited 0, because the broken partition list was
never parsed at all - the device lookup failed first and the whole
disk_config entry was skipped.

That made the test worthless: it "passed" regardless of whether the
partition table was correct, because it never actually looked at the
partition table. To fix this, the script backs a real loop device with a
sparse file and points the generated config at that instead of a fake
path. Creating a loop device from inside a container needs `CAP_SYS_ADMIN`
plus the ability to create new device nodes under `/dev`; the minimal
capability combination tried (`--cap-add SYS_ADMIN --cap-add MKNOD
--device /dev/loop-control`, and separately `-v /dev:/dev --cap-add
SYS_ADMIN` against an existing host loop node) both failed with
`Operation not permitted` under Docker's default seccomp/AppArmor
profile. `--privileged` is the combination that reliably works. The
container is `--rm` and short-lived, and the script detaches its loop
device via a `trap` on exit, so nothing persists on the host afterwards
- verified with `losetup -a` before and after.

## A gap `--dry-run` cannot close: empty partitions plus `wipe: true`

archinstall's config loader does not treat an empty `partitions` list as
an error, with or without a real device behind it. Verified directly: a
config with `wipe: true` and `partitions: []` loads and runs to
completion under `--dry-run`, exit 0, "OK" printed - nothing about the
CLI's behavior signals that this combination would erase the target disk
and create nothing on it in a real, non-dry-run install. Relying on
archinstall's exit code alone is therefore not sufficient to guard
against this specific defect class.

`tests/installer/test_translate.py::test_partitions_are_never_empty_when_wiping`
already guards this at the unit level, purely in Python, without needing
archinstall at all. `test_dry_run.sh` additionally re-asserts the same
invariant against the exact config object it is about to hand to
archinstall, immediately before writing `config.json` - so a regression
here is caught before the `--dry-run` call could mask it again by
silently accepting it.

## Running it

    sudo docker run --rm --network host --privileged \
      -v "$PWD":/src -w /src archlinux:latest bash -c \
      'pacman -Sy --noconfirm >/dev/null && \
       pacman -S --noconfirm archinstall python openssl >/dev/null && \
       ./tests/integration/test_dry_run.sh'

Expected output ends with:

    OK: archinstall accepted the ZepOS configuration.

## What a failure looks like

If the installer's translate.py ever produces a config archinstall
rejects, this test fails loudly: `set -euo pipefail` in
`test_dry_run.sh` means a non-zero exit from `archinstall` (or from the
Python generation step) aborts the script before "OK" is printed. All
three historical defects were reintroduced one at a time against this
test to confirm that:

  * `Percent` as a partition size unit (not a member of archinstall's
    `Unit` enum): exit 1, `KeyError: 'Percent'` raised out of
    `Size.parse_args`, full traceback pointing at
    `archinstall/lib/models/device.py`.
  * `sector_size: null` on a partition: exit 1, `TypeError: 'NoneType'
    object is not subscriptable`, same call stack.
  * `wipe: true` with an empty `partitions` list: exit 1, but from this
    script's own guard (see above), not from archinstall - archinstall's
    exit code stays 0 for this one, which is precisely why the guard is
    there.

Each was reverted (`git diff` empty again) before moving to the next.
