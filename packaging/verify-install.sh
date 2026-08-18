#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Installs the built packages into clean containers and shows where the
# files landed.
#
#     ./packaging/verify-install.sh
#
# WHY THIS IS NOT A UNIT TEST
#     tests/packaging/ reads the recipes; it cannot install anything,
#     because installing needs root and a container. What that leaves
#     unanswered is the only question a package really has: does pacman
#     accept it, resolve its dependencies, verify its signature, and put
#     the files where the recipe claims. Every one of those can fail on a
#     package that builds perfectly.
#
# WHY A CLEAN IMAGE AND NOT THE BUILD IMAGE
#     The build container has every build dependency installed and the
#     packages already unpacked in it. Installing there would prove that
#     packages install on a machine that just built them, which is the
#     one machine where it cannot fail. This starts from archlinux:latest
#     with nothing, exactly as an ISO's pacstrap does.
#
# WHY THREE CONTAINERS AND NOT ONE
#     Two of the questions here are about ABSENCE, and absence cannot be
#     measured next to the thing being installed:
#
#       * zepos-installer-tui is the fallback for a machine whose
#         graphical session did not start (spec §8.5). "It works without
#         GTK4" is only a statement about a machine that HAS no GTK4, and
#         the first container installs aylurs-gtk-shell, which brings
#         gtk4 with it.
#       * spec §4.2 puts the three installer packages in the ISO and
#         nowhere else. "zepos-desktop does not drag them in" is only a
#         statement about a machine where nobody installed them by hand,
#         which the second container is not.
#
#     So: the packages and the plugins in one, the installer in the
#     second, the meta package in the third.
#
# WHY THE SIGNATURE IS CHECKED HERE RATHER THAN TRUSTED
#     SigLevel is Required for [zepos], and the public key is imported
#     into the container pacman keyring and locally signed - the same
#     three commands zepos-keyring runs on an installed system. If the
#     signing step of packaging/build.sh produced anything pacman does
#     not accept, this stops here rather than in the ISO build.
#
#     The first container then takes that manual import BACK OUT and
#     lets the package do it, which is the only way to find out whether
#     zepos-keyring works: a keyring package tested on a machine that was
#     already told about the key proves nothing at all.
set -euo pipefail

readonly REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly OUT="$REPO/packaging/out"
readonly IMAGE="archlinux:latest"

die() { printf 'packaging/verify-install.sh: %s\n' "$*" >&2; exit 1; }
step() { printf '\n########## %s ##########\n' "$*"; }

[[ -f "$OUT/x86_64/zepos.db.tar.gz" ]] || die \
    "no repository in packaging/out/ - run ./packaging/build.sh first"

docker() { command sudo -n docker "$@"; }

snapshot="$(sed -n 's#^Server = https://archive.archlinux.org/repos/\([0-9/]*\)/\$repo.*#\1#p' \
    "$REPO/iso/profile/pacman.conf" | head -1)"
[[ -n "$snapshot" ]] || die "no ALA snapshot found in iso/profile/pacman.conf"

signed=false
[[ -f "$OUT/zepos-repo.pub" ]] && signed=true

# --network host: spec §10.1. The container has to reach the Arch archive
# for the dependencies of the ZepOS packages, and a bridged container on
# this machine reaches nothing.
container() {
    docker run --rm --network host \
        -v "$OUT:/zepos-repo:ro" \
        -e "ALA_SNAPSHOT=$snapshot" \
        -e "SIGNED=$signed" \
        "$IMAGE" \
        bash -euo pipefail -c "$1"
}

# Every one of the three scripts below is a SINGLE-QUOTED literal, and
# nothing in it is expanded on this machine. There is one rule that comes
# with that and it has been paid for once already: an apostrophe inside
# such a literal ends it, the shell then reads the remainder as host
# commands, and a container script quietly turns into half a container
# script and half a script running here. So there are no apostrophes
# below - not in prose, not in a message, not in a comment.

# --------------------------------------------------------------------
# What every container does before it measures anything
# --------------------------------------------------------------------
readonly PREAMBLE='
        printf "Server = https://archive.archlinux.org/repos/%s/\$repo/os/\$arch\n" \
            "$ALA_SNAPSHOT" > /etc/pacman.d/mirrorlist

        if [[ "$SIGNED" == true ]]; then
            # --init first, and it is not a formality: --lsign-key signs
            # the imported key with the local key pacman makes for
            # itself, and the archlinux image ships a populated keyring
            # WITHOUT one. Measured - "There is no secret key available
            # to sign with".
            pacman-key --init

            # The three commands zepos-keyring performs. --lsign-key is
            # the one that matters: --add only puts the key in the
            # keyring, and pacman rejects a signature from a key it has
            # not been told to trust.
            pacman-key --add /zepos-repo/zepos-repo.pub
            fingerprint="$(gpg --with-colons --show-keys /zepos-repo/zepos-repo.pub \
                | awk -F: "/^fpr:/ { print \$10; exit }")"
            pacman-key --lsign-key "$fingerprint"
            siglevel="Required DatabaseOptional"
        else
            echo "WARNING: the repository is unsigned; signatures are not being checked"
            siglevel="Optional TrustAll"
        fi

        printf "\n[zepos]\nSigLevel = %s\nServer = file:///zepos-repo/\$arch\n" \
            "$siglevel" >> /etc/pacman.conf

        pacman -Sy --noconfirm >/dev/null
'

# --------------------------------------------------------------------
# Container 1: the repository, the keyring, the compositor, the plugins
# --------------------------------------------------------------------
readonly CORE='
        echo
        echo "==> what the repository offers"
        pacman -Sl zepos

        echo
        echo "==> the plugin dependencies, on a machine with no compositor"
        # BEFORE anything is installed, because this is the one moment at
        # which the machine is in the state the assertion is about.
        #
        # Spec §7.3 asks for zepos-hyprland>=0.56.1 and <0.57.0 on every
        # plugin package. Until zepos-hyprland existed the range could be
        # written but never tried, and a dependency nobody has seen
        # refuse anything is a comment.
        #
        # `pacman -T` and not `pacman -S --print`: --print resolves but
        # does NOT run the conflict check, so it happily prints hyprland
        # and zepos-hyprland in one list. -T answers the only question
        # here - is this dependency satisfied on this machine - and exits
        # 127 with the unsatisfied ones on stdout.
        abi="$(pacman -Si zepos-hyprland | sed -n "s/.*hyprland-plugin-abi=\([^ ]*\).*/\1/p")"
        [[ -n "$abi" ]] || { echo "FAIL: zepos-hyprland publishes no ABI token"; exit 1; }
        echo "  the ABI zepos-hyprland publishes: $abi"

        if pacman -T "zepos-hyprland>=0.56.1" "zepos-hyprland<0.57.0" >/dev/null; then
            echo "FAIL: the version range is satisfied with no compositor installed"
            exit 1
        fi
        if pacman -T "hyprland-plugin-abi=$abi" >/dev/null; then
            echo "FAIL: the ABI token is satisfied with no compositor installed"
            exit 1
        fi
        echo "  both are unsatisfied, as they have to be"

        echo
        echo "==> zepos-keyring: what it contains"
        pacman -S --noconfirm zepos-keyring
        ls -l /usr/share/pacman/keyrings/zepos.gpg /usr/share/pacman/keyrings/zepos-trusted
        echo "  zepos-trusted: $(cat /usr/share/pacman/keyrings/zepos-trusted)"
        pacman -Qi zepos-keyring | grep -E "^(Name|Version|Description)"

        # The ownertrust line has to name the key the repository was
        # actually signed with. A keyring package carrying somebody
        # elses key installs, populates, and leaves every signature
        # rejected - with an error naming a key nobody can find.
        if [[ "$SIGNED" == true ]]; then
            trusted="$(cut -d: -f1 /usr/share/pacman/keyrings/zepos-trusted)"
            if [[ "$trusted" != "$fingerprint" ]]; then
                echo "FAIL: zepos-keyring trusts $trusted, the repository is signed by $fingerprint"
                exit 1
            fi
            echo "  it is the fingerprint that signed this repository"

            echo
            echo "==> and now the same machine, with the key taken away again"
            # The measurement the package exists for. Everything above
            # ran against a keyring this script populated by hand, so
            # nothing so far says whether zepos-keyring would have
            # worked. Delete the key, and pacman has to refuse.
            pacman-key --delete "$fingerprint" >/dev/null 2>&1
            rm -f /var/cache/pacman/pkg/*.pkg.tar.zst
            if pacman -Sw --noconfirm zepos-config >/tmp/nokey.log 2>&1; then
                echo "FAIL: a package was accepted with no trusted key in the keyring"
                exit 1
            fi
            # The refusal lands on the database signature rather than on
            # the package: pacman re-validates the synced database every
            # time it loads it, and reaches that before it looks at any
            # package. Same conclusion, one step earlier - without the
            # key this machine cannot use the repository at all.
            { grep -iE "signature|key" /tmp/nokey.log || true; } | tail -2 | sed "s/^/  /"

            echo
            echo "==> pacman-key --populate zepos, which is all the scriptlet does"
            pacman-key --populate zepos 2>&1 | sed "s/^/  /"
            rm -f /var/cache/pacman/pkg/*.pkg.tar.zst
            pacman -Sw --noconfirm zepos-config >/dev/null
            echo "  a package signature is accepted again"
            # And the database signature too, which is a different file
            # and a different SigLevel field.
            pacman -Sy --noconfirm >/dev/null
            echo "  the repository database verifies again"
        fi

        echo
        echo "==> installing zepos-config and aylurs-gtk-shell"
        # Named on the command line: zepos-config, and AGS. libastal-io,
        # libastal-4 and libastal-notifd are NOT named - if they arrive,
        # they arrived because the recipes declare them and pacman
        # resolved them out of the repository database.
        pacman -S --noconfirm zepos-config aylurs-gtk-shell libastal-notifd

        echo
        echo "==> zepos-config: the commands"
        ls -l /usr/bin/zepos-generate /usr/bin/zepos-settings \
              /usr/bin/zepos-doctor /usr/bin/zepos-update \
              /usr/bin/zepos-displays-guard

        echo
        echo "==> zepos-config: der Waechter der Bildschirmanordnung"
        # Er wird GEFAHREN und nicht nur aufgelistet. Ohne Plan auf der
        # Standardeingabe endet er mit 2 und ohne etwas zu tun - genau
        # das ist die Aussage, die zaehlt: er findet seine Module, er
        # laeuft, und er stellt nichts um, was niemand bestellt hat.
        #
        # Die Seite "Bildschirme" wendet nichts an, bevor er "bereit"
        # gemeldet hat. Ein fehlender oder kaputter Waechter ist auf
        # einer Installation deshalb kein stiller Verlust, sondern eine
        # Seite, die gar nichts mehr tut.
        env -i /usr/bin/zepos-displays-guard </dev/null; guard_code=$?
        if [ "$guard_code" -ne 2 ]; then
            echo "  FEHLER: der Waechter endete mit $guard_code statt 2" >&2
            exit 1
        fi
        echo "  ohne Plan: Rueckgabewert 2, nichts umgestellt"

        echo
        echo "==> zepos-config: die Selbstaktualisierung (UP-1)"
        # Die drei Dateien, ohne die eine installierte Maschine nichts
        # von selbst holt - und der Haken, der den Zeitgeber einschaltet.
        # Die Unit wird GELESEN und nicht nur aufgelistet: eine
        # .timer-Datei, deren [Timer]-Abschnitt systemd nicht versteht,
        # sieht in `ls -l` genau richtig aus.
        ls -l /usr/lib/systemd/system/zepos-update.timer \
              /usr/lib/systemd/system/zepos-update.service \
              /usr/share/libalpm/hooks/90-zepos-update.hook
        cat /usr/lib/systemd/system/zepos-update.timer
        systemd-analyze verify /usr/lib/systemd/system/zepos-update.timer \
            && echo "  systemd-analyze verify: in Ordnung"

        echo
        echo "==> zepos-config: the package root"
        ls -l /usr/share/zepos | head -20
        printf "templates  %s\nstyles     %s\nsystem     %s\n" \
            "$(ls /usr/share/zepos/templates | wc -l)" \
            "$(ls /usr/share/zepos/styles | wc -l)" \
            "$(ls /usr/share/zepos/system | wc -l)"
        ls -l /usr/share/zepos/generate_config.sh

        echo
        echo "==> zepos-config: the default settings for a new account"
        ls -l /etc/skel/.config/zepos/user-settings.json
        head -c 200 /etc/skel/.config/zepos/user-settings.json; echo

        echo
        echo "==> the commands run, with nothing set in the environment"
        # env -i, so that nothing this shell exported can stand in for
        # what the package installed. If /usr/share/zepos were not found
        # from /usr/bin, this is where it would show.
        env -i /usr/bin/zepos-generate --help
        env -i /usr/bin/zepos-settings --help | head -3

        echo
        echo "==> aylurs-gtk-shell"
        ls -l /usr/bin/ags
        /usr/bin/ags --version 2>&1 | head -3 || true

        echo
        echo "==> the imports every ZepOS widget begins with"
        # This is the question the AGS package exists to answer. The
        # fifteen templates import these three typelibs before they draw
        # anything; gjs resolves them the same way here as it does under
        # a compositor, and needs no display to do it.
        #
        # From a file rather than `gjs -m -c`: measured, gjs resolves the
        # module name of a -c script to the literal path "<command line>"
        # and fails to open it. A module needs somewhere to be.
        cat >/tmp/imports.js <<"PROBE"
import Astal from "gi://Astal?version=4.0"
import AstalIO from "gi://AstalIO"
import AstalNotifd from "gi://AstalNotifd?version=0.1"
print("Astal", Astal.Window.$gtype.name)
print("AstalIO", AstalIO.Process.$gtype.name)
print("AstalNotifd", AstalNotifd.Notifd.$gtype.name)
PROBE
        gjs -m /tmp/imports.js

        echo
        echo "==> nothing points back at the build tree"
        # A library that kept an RPATH into the staging directory of the
        # split astal build would work on the build machine and nowhere
        # else.
        for library in /usr/lib/libastal-4.so.4 /usr/lib/libastal-notifd.so.0; do
            if readelf -d "$library" | grep -E "RPATH|RUNPATH"; then
                echo "FAIL: $library carries a build-tree search path"
                exit 1
            fi
        done
        echo "no RPATH or RUNPATH in the astal libraries"

        echo
        echo "==> zepos-logout, und das Toolkit, auf dem es steht"
        # SUPER+M oeffnet die Abmeldemaske. Das Rezept misst das fertige
        # Objekt zur Paketzeit; hier wird die Datei gemessen, die
        # tatsaechlich installiert wurde - zwei verschiedene Momente,
        # zwischen denen ein Paket ausgetauscht worden sein kann.
        #
        # Beide Richtungen, und die zweite ist nicht ueberfluessig: ein
        # Programm kann libgtk-4 UND libgtk-3 laden, wenn eine
        # Bibliothek dazwischen die alte hereinzieht. Die
        # Entscheidung vom 11.08.2026 ist damit nicht erfuellt.
        pacman -S --noconfirm zepos-logout
        ls -l /usr/bin/zepos-logout
        if ! readelf -d /usr/bin/zepos-logout | grep -q "libgtk-4"; then
            echo "FAIL: das installierte zepos-logout ist nicht gegen GTK4 gelinkt"
            exit 1
        fi
        if readelf -d /usr/bin/zepos-logout | grep -q "libgtk-3"; then
            echo "FAIL: das installierte zepos-logout zieht libgtk-3 herein"
            exit 1
        fi
        if ! readelf -d /usr/bin/zepos-logout | grep -q "gtk4-layer-shell"; then
            echo "FAIL: das installierte zepos-logout ist nicht gegen gtk4-layer-shell gelinkt"
            exit 1
        fi
        echo "  gegen libgtk-4 und gtk4-layer-shell gelinkt, ohne libgtk-3"

        echo
        echo "==> the compositor Arch ships does not satisfy them either"
        # The sharpest form of the question, and the reason the ABI token
        # exists at all. extra has hyprland 0.56.1-3 at this snapshot -
        # the same upstream release, built from the same commit, inside
        # the >=0.56.1 <0.57.0 range the plugins name. Install it and
        # then ask:
        #
        #   the range   is still unsatisfied, because the package is
        #               called hyprland and the range names
        #               zepos-hyprland. That is the second correction
        #               in spec §4.2, and it is what stops the Arch
        #               release schedule from moving the compositor
        #               under five plugin packages.
        #   the token   is still unsatisfied, because nothing but
        #               zepos-hyprland publishes it - and a compositor
        #               that was not built here cannot say which headers
        #               these objects were compiled against.
        #
        # Then the transaction itself, because -T answers about
        # dependencies and this is about conflicts.
        pacman -S --noconfirm hyprland >/dev/null
        echo "  installed from extra: $(pacman -Q hyprland)"
        if pacman -T "zepos-hyprland>=0.56.1" >/dev/null; then
            echo "FAIL: Arch hyprland satisfies the plugins version range"
            exit 1
        fi
        if pacman -T "hyprland-plugin-abi=$abi" >/dev/null; then
            echo "FAIL: Arch hyprland satisfies the plugin ABI token"
            exit 1
        fi
        # || true and a temporary file rather than a pipeline: this shell
        # runs with `set -e -o pipefail`, and the whole point of the
        # command is that it fails.
        pacman -S --noconfirm zepos-hyprzones >/tmp/refused.log 2>&1 || true
        tail -4 /tmp/refused.log | sed "s/^/  /"
        if pacman -Qq zepos-hyprzones >/dev/null 2>&1; then
            echo "FAIL: a plugin installed next to the compositor from extra"
            exit 1
        fi
        echo "  the transaction was refused"

        # -Rdd: the point was made, and the rest of this script is
        # about the compositor that belongs here. The second d is
        # there so that a future addition to this script - anything
        # installed that depends on a compositor - cannot turn this
        # cleanup into a cascade.
        pacman -Rdd --noconfirm hyprland >/dev/null

        echo
        echo "==> installing the compositor and the five plugins"
        # zepos-hyprland is named; the plugins are named; nothing else
        # is. hyprland-plugin-abi is resolved out of the repository
        # database, which is the point - it is a dependency no human
        # types and pacman has to be able to satisfy it from what the
        # build published.
        pacman -S --noconfirm zepos-hyprland \
            zepos-hyprbars zepos-borders-plus-plus \
            zepos-hyprlaunch zepos-hyprclipx zepos-hyprzones

        echo
        echo "==> the objects, at the one path src/plugins.py looks at"
        # Asked THROUGH the module rather than by repeating the path.
        # src/plugins.py is where /usr/lib/hyprland/plugins is defined
        # and where the decision to write a plugin block is taken; a
        # check that spelled the directory out again could pass while the
        # generator looked somewhere else.
        ls -l /usr/lib/hyprland/plugins/
        PYTHONPATH=/usr/share/zepos python - <<"PROBE"
import sys
import plugins

missing = {name: str(plugins.object_path(name))
           for name in plugins.PLUGINS
           if not plugins.object_path(name).is_file()}
for name in plugins.PLUGINS:
    print(f"  {name:<20} {plugins.object_path(name)}")
if missing:
    print("FAIL: no object for " + ", ".join(missing))
    sys.exit(1)
print("all five objects are where the generator will look for them")
PROBE

        echo
        echo "==> the ABI the compositor published, and what depends on it"
        # The token is the abiHash upstream computes: the commit Hyprland
        # was built from plus the major.minor of the five libraries it
        # was built against. Hyprland does not check it at load time -
        # its own check compares the literal string "0.1" - so the
        # packages do, and this is where that is visible.
        cat /usr/lib/hyprland/plugin-abi
        pacman -Qi zepos-hyprzones | grep -A3 "Depends On"

        # The file the compositor installed and the token it published
        # have to be the same string: the plugin recipes read the file at
        # build time and pacman resolves the token at install time, so a
        # disagreement would mean the objects were compiled against one
        # compositor and matched to another.
        if [[ "$(cat /usr/lib/hyprland/plugin-abi)" != "$abi" ]]; then
            echo "FAIL: the installed ABI file is not the published token"
            exit 1
        fi
        for plugin in zepos-hyprbars zepos-borders-plus-plus \
                      zepos-hyprlaunch zepos-hyprclipx zepos-hyprzones; do
            if ! pacman -Qi "$plugin" | grep -q "hyprland-plugin-abi=$abi"; then
                echo "FAIL: $plugin does not depend on the ABI of the compositor next to it"
                exit 1
            fi
        done
        echo "all five plugins are pinned to $abi"

        # And the token is compared exactly, not by prefix. One component
        # changed - aquamarine a minor version on - and it is a
        # dependency this machine cannot satisfy, which is precisely the
        # case the version range cannot see: 0.56.1 rebuilt against a new
        # aquamarine is still 0.56.1.
        if pacman -T "hyprland-plugin-abi=${abi/_aq_/_aq_9}" >/dev/null; then
            echo "FAIL: a different ABI token is satisfied by this compositor"
            exit 1
        fi
        echo "a token differing in one library version is not satisfied"

        echo
        echo "==> nothing points back at the build tree"
        for object in /usr/lib/hyprland/plugins/*.so; do
            if readelf -d "$object" | grep -E "RPATH|RUNPATH"; then
                echo "FAIL: $object carries a build-tree search path"
                exit 1
            fi
        done
        echo "no RPATH or RUNPATH in the five plugin objects"

        echo
        echo "==> every installed file is the file the package shipped"
        # -Qkk compares every path against the package database: mode,
        # size and checksum, not merely existence.
        #
        # The filter is for this container and not for the packages.
        # archlinux:latest ships
        #
        #     NoExtract = usr/share/man/* usr/share/info/*
        #     NoExtract = usr/share/doc/* usr/share/locale/* ...
        #
        # in its pacman.conf, so pacman deliberately does not unpack
        # those and then reports them as missing. zepos-hyprland is the
        # first ZepOS package with man pages - Hyprland.1 and hyprctl.1 -
        # which is why this never came up before. Any other alteration
        # is still a failure.
        pacman -Qkk zepos-config zepos-keyring zepos-logout aylurs-gtk-shell \
            libastal-io libastal-4 \
            libastal-notifd zepos-hyprland zepos-hyprbars \
            zepos-borders-plus-plus zepos-hyprlaunch zepos-hyprclipx \
            zepos-hyprzones >/tmp/qkk.log 2>&1 || true

        grep "^warning:" /tmp/qkk.log \
            | grep -vE " /usr/share/(man|info|doc|locale)" >/tmp/qkk-real.log || true
        if [[ -s /tmp/qkk-real.log ]]; then
            echo "FAIL: an installed file is not what the package shipped"
            cat /tmp/qkk-real.log
            exit 1
        fi
        grep "total files" /tmp/qkk.log
        grep -c "^warning:" /tmp/qkk.log | sed "s/^/paths NoExtract skipped in this container: /"
'

# --------------------------------------------------------------------
# Container 2: the installer, and the fallback that has to work without GTK
# --------------------------------------------------------------------
readonly INSTALLER='
        # archlinux:latest ships NoExtract lines that skip
        # usr/share/locale, so the German catalogue zepos-installer
        # installs would never be unpacked in this container and the
        # check further down would be measuring the pacman.conf of a
        # docker image rather than the package. Removed here, for this
        # container only.
        sed -i "/^NoExtract/d" /etc/pacman.conf

        echo
        echo "==> zepos-installer and zepos-installer-tui, and nothing else"
        # Spec §8.5: the text interface is what runs when the graphical
        # session does not come up. On this machine there is no GTK4, no
        # libadwaita and no PyGObject, and there must be none afterwards
        # either - a dependency that pulls the toolkit in would defeat
        # the fallback silently, because a machine that CAN run GTK4
        # never notices.
        pacman -S --noconfirm zepos-installer zepos-installer-tui

        for toolkit in gtk4 gtk3 libadwaita python-gobject; do
            if pacman -Qq "$toolkit" >/dev/null 2>&1; then
                echo "FAIL: $toolkit is installed next to the text interface"
                pacman -Qi "$toolkit" | head -3
                exit 1
            fi
        done
        echo "  no gtk4, no gtk3, no libadwaita, no python-gobject"
        echo "  what did arrive:"
        pacman -Qq | grep -E "^(zepos-|archinstall|iwd)" | sed "s/^/    /"

        echo
        echo "==> what the three packages own"
        pacman -Ql zepos-installer | sed "s/^/  /"
        pacman -Ql zepos-installer-tui | sed "s/^/  /"

        echo
        echo "==> the entry point runs, chooses the text interface, and speaks German"
        # env -i, so nothing this shell exported can stand in for what
        # the package installed - the same rule the zepos-config checks
        # above follow. With no WAYLAND_DISPLAY and no gi to import,
        # choose_surface() has to land on the text interface by itself;
        # nothing here asks it to.
        #
        # It gets as far as the firmware check and stops there, which is
        # exactly right for a container: /sys/firmware/efi does not
        # exist, so installer.core.firmware refuses before a single
        # question. That refusal is the proof - reaching it means
        # /usr/bin/zepos-install found /usr/share/zepos-installer,
        # imported installer.core and installer.tui, activated the
        # catalogue from LANG, and printed a translated message. Nothing
        # is asked and no disk is touched.
        set +e
        env -i LANG=de_DE.UTF-8 /usr/bin/zepos-install >/tmp/tui.log 2>&1
        tui_rc=$?
        set -e
        sed "s/^/  /" /tmp/tui.log
        if (( tui_rc != 1 )); then
            echo "FAIL: the text interface exited $tui_rc, expected 1 from the firmware refusal"
            exit 1
        fi
        if ! grep -q "UEFI-Modus gestartet wurde" /tmp/tui.log; then
            echo "FAIL: the message is not the German one; the catalogue did not load"
            exit 1
        fi
        echo "  exit 1, in German, with no GTK on the machine"

        echo
        echo "==> what imports on this machine, and what does not"
        # The three packages are one python package split across three
        # pacman packages, so this is also the check that the split did
        # not lose an __init__.py. And it is the sharpest form of the
        # question above: installer.tui.app imports, installer.gui.app
        # does not, on the same interpreter and the same root.
        env -i PYTHONPATH=/usr/share/zepos-installer python - <<"PROBE"
import sys

import installer.core.runner          # noqa: F401
import installer.core.translate       # noqa: F401
import installer.tui.app              # noqa: F401
print("  installer.core and installer.tui import")

try:
    import installer.gui.app          # noqa: F401
except ImportError as exc:
    print(f"  installer.gui does not, and says why: {exc}")
else:
    print("FAIL: the GTK4 surface imported on a machine with no GTK4")
    sys.exit(1)
PROBE

        echo
        echo "==> the GUI package is the only one that names a toolkit"
        pacman -S --noconfirm zepos-installer-gui
        for toolkit in gtk4 libadwaita python-gobject; do
            pacman -Qq "$toolkit" >/dev/null 2>&1 || {
                echo "FAIL: $toolkit did not arrive with zepos-installer-gui"
                exit 1
            }
        done
        echo "  gtk4, libadwaita and python-gobject arrived with it and not before"
        pacman -Ql zepos-installer-gui | sed "s/^/  /"

        echo
        echo "==> archinstall, at the version the translation was read against"
        # Spec §4.3 pins archinstall 4.4 and installer/core/translate.py
        # names it in its header: the config keys, the Size and Unit
        # types and the spelling of --mountpoint all come from that
        # release. A different one is not a broken import, it is a
        # configuration archinstall accepts and reads differently.
        pacman -Q archinstall
        case "$(pacman -Q archinstall)" in
            "archinstall 4.4"*) echo "  4.4, as installer/core/translate.py was written against" ;;
            *) echo "FAIL: the pinned snapshot no longer carries archinstall 4.4"; exit 1 ;;
        esac

        echo
        echo "==> every installed file is the file the package shipped"
        pacman -Qkk zepos-installer zepos-installer-gui zepos-installer-tui \
            >/tmp/qkk.log 2>&1 || true
        grep "^warning:" /tmp/qkk.log \
            | grep -vE " /usr/share/(man|info|doc|locale)" >/tmp/qkk-real.log || true
        if [[ -s /tmp/qkk-real.log ]]; then
            echo "FAIL: an installed file is not what the package shipped"
            cat /tmp/qkk-real.log
            exit 1
        fi
        grep "total files" /tmp/qkk.log
'

# --------------------------------------------------------------------
# Container 3: the meta package, which is the shape of an installed ZepOS
# --------------------------------------------------------------------
readonly DESKTOP='
        echo
        echo "==> zepos-desktop, named alone"
        # installer/core/translate.py hands archinstall exactly this one
        # package name, so this transaction is the installed system.
        # Everything that arrives, arrives because a recipe declared it.
        pacman -S --noconfirm zepos-desktop
        pacman -Qi zepos-desktop | grep -E "^(Name|Version|Depends On)" -A6 | head -20

        echo
        echo "==> the three installer packages are NOT here"
        # Spec §4.2, the line under the table: the installer lives in the
        # ISO and not in the installed system. A machine that carries the
        # program which erases disks would carry archinstall and iwd with
        # it, and would offer to reinstall itself.
        for absent in zepos-installer zepos-installer-gui zepos-installer-tui archinstall; do
            if pacman -Qq "$absent" >/dev/null 2>&1; then
                echo "FAIL: $absent was pulled into a zepos-desktop installation"
                echo "  required by: $(pacman -Qi "$absent" | grep "Required By")"
                exit 1
            fi
        done
        echo "  no zepos-installer, no -gui, no -tui, no archinstall"

        echo
        echo "==> what a zepos-desktop machine does have"
        for needed in zepos-config zepos-keyring zepos-hyprland \
                      zepos-hyprbars zepos-borders-plus-plus zepos-hyprlaunch \
                      zepos-hyprclipx zepos-hyprzones \
                      aylurs-gtk-shell libastal-notifd dart-sass \
                      kitty zepos-menu zepos-logout zepos-lock; do
            pacman -Qq "$needed" >/dev/null 2>&1 || {
                echo "FAIL: $needed is missing from a zepos-desktop installation"
                exit 1
            }
        done
        printf "  %s\n" "$(pacman -Qq | wc -l) packages in total"

        echo
        echo "==> the keyring is there, which is why the next pacman -Syu works"
        # The dependency that is easiest to forget and worst to forget.
        # installer/core/source.py leaves a [zepos] section with SigLevel
        # = Required in the installed pacman.conf; without the keyring
        # the first update fails on a key the machine was never given.
        ls -l /usr/share/pacman/keyrings/zepos.gpg
        pacman -Qo /usr/share/pacman/keyrings/zepos-trusted

        echo
        echo "==> the five plugin objects, asked through the generator"
        PYTHONPATH=/usr/share/zepos python - <<"PROBE"
import sys
import plugins

missing = [name for name in plugins.PLUGINS
           if not plugins.object_path(name).is_file()]
if missing:
    print("FAIL: no object for " + ", ".join(missing))
    sys.exit(1)
print("  all five plugin objects are present on a zepos-desktop machine")
PROBE

        echo
        echo "==> the commands a user types"
        env -i /usr/bin/zepos-generate --help
'

step "1/3  the repository, the keyring, the compositor and the plugins"
container "$PREAMBLE$CORE"

step "2/3  the installer, on a machine with no GTK"
container "$PREAMBLE$INSTALLER"

step "3/3  zepos-desktop, which is what an installed ZepOS is"
container "$PREAMBLE$DESKTOP"

step "all three containers finished"
