#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# shellcheck disable=SC2034
#
# The archiso profile of the ZepOS installation medium.
#
# THIS IS THE IMAGE THAT GETS HANDED TO A PERSON.
#
# It boots into the installer and carries nothing that exists only to be
# measured: no autologin, no /etc/shadow of its own, no answer file with
# a password in it, no collector writing the session's state to a raw
# disk, no serial console on the kernel command line. Everything in that
# sentence is what iso/profile/ - the smoke harness - is FOR, which is
# why the two are separate profiles and why the shipping one is built
# from an allow-list (iso/shared-with-release.txt) rather than by
# deleting things from a copy.
#
# What it does carry, and why each is not a measurement:
#
#   the installer      zepos-installer, -gui and -tui. Spec §4.2 puts
#                      all three in the ISO and in nothing else, and
#                      §8.5's fallback from GTK4 to the text interface
#                      is a decision taken at run time on the machine in
#                      front of the user - an image with one surface has
#                      made that decision at build time instead.
#   a Wayland session  spec §8.5: "Die Live-Umgebung startet eine
#                      minimale Wayland-Sitzung fuer die grafische
#                      Oberflaeche." That is zepos-hyprland plus a
#                      terminal, started by zepos-live-session.
#   an offline repo    /opt/zepos-repo, put there by iso/build.sh. Spec
#                      §8.4's second row: an installation with no network
#                      still gets the ZepOS packages.
#   the ALA pin        spec §8.7, shared with the smoke image, so that
#                      the system this medium installs is the system that
#                      was smoke-tested.

iso_name="zepos"

# Same shape as the smoke image's label and for the same reasons:
# uppercase and short enough for Joliet's sixteen characters, and derived
# from SOURCE_DATE_EPOCH so two builds of one commit produce one label.
iso_label="ZEPOS_$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y%m)"
# Same address as the smoke image's and as every PKGBUILD's, and it
# became so on 17.08.2026: it named a private GitHub account before.
iso_publisher="ZeptronIT <https://github.com/ZeptronIT/ZepOS>"
iso_application="ZepOS installation medium"
iso_version="$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y.%m.%d)"

install_dir="zepos"

buildmodes=('iso')

# Both firmware paths. A medium that only boots one of them is a medium
# somebody cannot boot, and which of the two a machine offers is not
# something the person holding the USB stick gets to choose.
#
# Note that ZepOS can only be INSTALLED from the UEFI path -
# installer/core/firmware.py refuses a machine started in BIOS mode, und
# der Kopf jener Datei traegt den Grund: der Startweg ist seit dem
# 11.08.2026 gemessen, archinstalls Weg dorthin nicht. Booting the BIOS
# path is still the right thing to offer, und dass es traegt, ist
# fotografiert: `./iso/test-boot.py --scenario release --firmware bios`
# zeigt am 11.08.2026 das gethemte syslinux-Menue, danach den Installer,
# und auf dessen erster Seite den Ablehnungssatz in der Sprache des
# Nutzers - statt einer Maschine, die gar nichts anzeigt.
#
# THEY ARE TWO MENUS AND THEY CANNOT BE ONE PICTURE
#     Each boot mode has its own menu and its own way of being told what
#     to look like: GRUB reads a theme file (grub/themes/zepos/theme.txt)
#     with percentage geometry, a scaled PNG and a PF2 font, while
#     syslinux takes ONE background image at ONE fixed resolution, lays
#     text out in character cells and colours each element with
#     #AARRGGBB. Neither mechanism can express the other. So the two
#     menus carry the same brand and are not the same picture: same
#     petrol, same wordmark, same yellow behind the selected entry, same
#     words, different geometry.
#
#     What still has to agree line by line is the kernel command line.
#     The headers of grub/grub.cfg and syslinux/syslinux.cfg say which
#     half is which, and `./iso/test-boot.py --scenario boot-menu` boots
#     each firmware and measures the frame, because a theme that fails to
#     load takes the whole identity with it and says nothing.
bootmodes=('bios.syslinux'
           'uefi.grub')

pacman_conf="pacman.conf"

# squashfs+zstd. The same choice the smoke image makes, for a different
# reason: here it is what the user downloads, and zstd at a fixed level
# is both small and deterministic.
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'zstd' '-Xcompression-level' '9')

# mkarchiso copies the profile's airootfs with
#
#     cp -af --no-preserve=ownership,mode
#
# so every mode in git is discarded and everything lands 0644. Anything
# that is RUN rather than read has to be named here or it is not
# executable in the image - the failure is exit 126 from a systemd unit
# on a machine with nobody watching, which on this image means a black
# screen instead of an installer.
#
# Nothing that a PACKAGE installs may be named here: file_permissions is
# applied BEFORE pacstrap, and mkarchiso stops the build with "Cannot
# change permissions of ... The file or directory does not exist." So
# /usr/bin/zepos-install is deliberately absent - it arrives with
# zepos-installer, which carries its own mode.
file_permissions=(
  ["/usr/local/bin/zepos-live-prepare"]="0:0:755"
  ["/usr/local/bin/zepos-live-session"]="0:0:755"
  ["/usr/local/bin/zepos-live-surface"]="0:0:755"
  ["/usr/local/bin/zepos-live-schirme"]="0:0:755"
)
