#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# shellcheck disable=SC2034
#
# The archiso profile of the ZepOS smoke image.
#
# This is NOT the shipping ISO of spec §8. It carries no installer, no
# offline repository, no signature and none of the ZepOS packages; those
# are TP3 and TP5-2. It answers one question that 978 unit tests cannot:
# does a Hyprland session actually come up on top of the configuration
# this repository generates. Everything here exists to make that question
# answerable and to keep the answer reproducible.
#
# Derived from archiso's `baseline` profile rather than from `releng`:
# releng is a rescue system with 130 packages, and every one of them is a
# variable in an experiment that has never been run before.

iso_name="zepos-smoke"

# Uppercase, alphanumeric and underscore only - an ISO 9660 volume
# identifier, not a free-text field. Sixteen characters rather than the
# thirty-two ISO 9660 allows, because Joliet stops at sixteen and
# xorriso warns about every longer one; a warning that is always there is
# a warning nobody reads when it matters. The month comes from
# SOURCE_DATE_EPOCH so that two builds of the same commit produce the
# same label (spec §8.7).
iso_label="ZEPOS_$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y%m)"
# The same address every PKGBUILD under packaging/ carries. It named a
# private GitHub account until 17.08.2026, which put one person's handle
# on the volume header of every medium this project hands out - and it
# disagreed with the twenty recipes that already said ZeptronIT/ZepOS.
iso_publisher="ZeptronIT <https://github.com/ZeptronIT/ZepOS>"
iso_application="ZepOS smoke test image (no installer)"
iso_version="$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y.%m.%d)"

# At most eight characters: it becomes a directory name on an ISO 9660
# filesystem, and it is what %INSTALL_DIR% expands to in every boot
# loader configuration below.
install_dir="zepos"

buildmodes=('iso')

# Both firmware paths, as spec §8 requires of the shipping image. The
# QEMU harness boots the BIOS path because SeaBIOS needs no firmware
# image on the host; the UEFI path is built so that it cannot rot
# unnoticed while nobody looks at it.
bootmodes=('bios.syslinux'
           'uefi.grub')

pacman_conf="pacman.conf"

# squashfs+zstd rather than baseline's erofs+lzma. lzma -109 spends
# minutes squeezing an image that is thrown away after one boot; this
# build is measured in turnaround, not in megabytes. zstd at a fixed
# level is deterministic, so the choice costs nothing in
# reproducibility.
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'zstd' '-Xcompression-level' '5')

# THIS LIST IS NOT OPTIONAL POLISH - IT IS WHERE THE EXECUTABLE BIT
# COMES FROM.
#
# mkarchiso copies the profile's airootfs with
#
#     cp -af --no-preserve=ownership,mode
#
# so every mode in the profile is discarded and every file lands 0644,
# no matter what it looks like in git. Anything that is RUN rather than
# read has to be named here or it is not executable in the image.
#
# Measured on the run that found this: `zepos-generate --all` returned
# 126 - "found, but cannot be executed" - the configuration was never
# generated, and start-hyprland, which the generator writes, did not
# exist for the session phase to start. One missing mode, no desktop.
#
# The entries are applied BEFORE pacstrap, so the numeric ids below are
# written before the user they belong to exists. That is fine: chown
# takes numbers, and etc/sysusers.d/zepos.conf pins the live user to
# exactly this uid.
#
# Without the two /home/zepos entries the live user logs into a home
# directory owned by root, the generator cannot write a single file, and
# the session dies before the compositor is reached.
#
# WHAT IS NO LONGER IN THIS LIST, AND WHY IT MUST NOT COME BACK
#     /usr/bin/zepos-generate, -settings, -doctor and
#     /usr/share/zepos/generate_config.sh used to be here. They now
#     arrive with the zepos-config PACKAGE, which carries its own modes,
#     and packages are installed by pacstrap - which runs AFTER this
#     array is applied. mkarchiso does not skip an entry whose file is
#     not there yet; it stops the build with
#
#         Cannot change permissions of '.../usr/bin/zepos-generate'.
#         The file or directory does not exist.
#
#     So those four lines are not merely redundant now, they are fatal.
#     The invariant did not go away, it moved: it is asserted against
#     packaging/zepos-config/PKGBUILD by tests/packaging/test_recipes.py,
#     from both sides - that the recipe installs them executable, and
#     that nothing a package owns is named here.
file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/home/zepos"]="1000:1000:0700"
  ["/home/zepos/.bash_profile"]="1000:1000:0644"

  # The smoke harness itself.
  ["/usr/local/bin/zepos-smoke"]="0:0:755"
  ["/usr/local/bin/zepos-smoke-collect"]="0:0:755"

  # The update probe. It never runs on the live medium - the unit beside
  # it is deliberately not enabled here, and the script refuses when
  # /run/archiso exists - but zepos-install-unattended copies it onto the
  # TARGET, and `install -Dm755` from a source that arrived 0644 is still
  # 0755 only because install says so. The entry is here for the same
  # reason the other two are: mkarchiso discards the mode git recorded,
  # and the failure is exit 126 on a machine nobody is watching.
  ["/usr/local/bin/zepos-smoke-update"]="0:0:755"

  # The unattended installation. Run by root out of
  # zepos-install-unattended.service, so an entry missing here is a
  # service that fails with status=203/EXEC and an image that boots to a
  # desktop while the disk it was meant to install onto stays empty -
  # which looks like a successful run from every angle except the disk.
  ["/usr/local/bin/zepos-install-unattended"]="0:0:755"

  # The answers that installation is driven with, and they include a user
  # password and a root password in clear text.
  #
  # They are throwaway credentials for a disposable virtual machine and
  # committing them is what makes the run repeatable - but the file ships
  # INSIDE the image, so at 0644 every process on the live system can
  # read the root password of the machine it is about to install. 0600
  # does not make the image safe to hand anybody; it makes the exposure
  # match what the file is.
  #
  # tests/iso/test_smoke_profile.py holds the wider rule: this profile is
  # a test harness, no shipping image may be built from it, and no file
  # in it may carry a credential at a mode the world can read.
  ["/usr/local/share/zepos-install/unattended-install.json"]="0:0:600"
)
