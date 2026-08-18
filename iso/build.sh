#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Builds a ZepOS ISO. There are two, and they are not the same image.
#
#     ./iso/build.sh                       the smoke ISO (default)
#     ./iso/build.sh --profile release     the installation medium
#     ./iso/build.sh --snapshot 2026/07/01 build against another ALA date
#     ./iso/build.sh --snapshot current    build against today's mirrors
#     ./iso/build.sh --rebuild-image       rebuild the build container too
#
# THE TWO PROFILES
#     smoke     iso/profile/. A test harness: it logs a user in, ships
#               its own /etc/shadow, installs unattended from a file with
#               a root password in it, writes the session's state to a
#               raw disk and puts console=ttyS0 on the kernel command
#               line. All correct for measuring a desktop and every bit
#               of it wrong for a download.
#     release   iso/profile-release/. The image that can be handed to a
#               person: it boots into the installer and carries none of
#               the above.
#
#     The shipping profile is ASSEMBLED here rather than being a second
#     copy of the first: the files both images share are named in
#     iso/shared-with-release.txt and nothing else crosses over. That
#     file's header has the argument for why the list is an allow-list.
#
# The result and its manifests land in iso/out/. Nothing in iso/out/ or
# iso/work/ is committed - see the repository's .gitignore.
#
# WHY A CONTAINER
#     mkarchiso needs root and is not installed on the development
#     machine. Spec §10 already put the package build in a container and
#     the ISO build has no reason to answer the question differently.
#
# WHY --network host ON EVERY docker run
#     Measured, and predicted by spec §10.1: this machine's IPsec tunnel
#     routes all three RFC1918 ranges, the Docker bridge lives inside
#     10.0.0.0/8, and every packet a bridged container sends disappears
#     into the tunnel. `pacman -Sy` in a bridged container does not fail
#     slowly, it fails completely. There is no subnet left to move the
#     bridge into, because all three private ranges are routed.
#
# WHY --privileged
#     pacstrap bind-mounts /proc, /sys and /dev into the target root and
#     mkarchiso unshares mount namespaces. Neither is possible with
#     Docker's default capability set.
set -euo pipefail

readonly REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ISO_DIR="$REPO/iso"
readonly SMOKE_PROFILE="$ISO_DIR/profile"
readonly RELEASE_PROFILE="$ISO_DIR/profile-release"
readonly SHARED_LIST="$ISO_DIR/shared-with-release.txt"
readonly WORK="$ISO_DIR/work"
readonly OUT="$ISO_DIR/out"
readonly IMAGE="zepos-isobuild"

# The repository packaging/build.sh produced, mounted into the build
# container at the path iso/profile/pacman.conf's [zepos] section names.
#
# This is what replaced copying src/ into the image by hand. That copy
# was honest about being a stand-in - "building the package is TP3 and
# this image is not allowed to wait for it" - and it tested a layout
# nothing ships: files with no package, no dependencies, no signature,
# and modes that had to be repeated in profiledef.sh because the copy
# lost them. The package carries all four, so the image now installs what
# a user will install.
readonly PKG_REPO="$REPO/packaging/out"
readonly PKG_REPO_MOUNT="/zepos-repo"

snapshot=""
rebuild_image=false
profile="smoke"

die() { printf 'iso/build.sh: %s\n' "$*" >&2; exit 1; }
step() { printf '\n==> %s\n' "$*"; }

while (( $# )); do
    case "$1" in
        --profile)
            [[ $# -ge 2 ]] || die "--profile needs a name (smoke or release)"
            profile="$2"; shift 2 ;;
        --snapshot)
            [[ $# -ge 2 ]] || die "--snapshot needs a date (YYYY/MM/DD) or 'current'"
            snapshot="$2"; shift 2 ;;
        --rebuild-image) rebuild_image=true; shift ;;
        -h|--help)
            sed -n '3,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
done

case "$profile" in
    smoke|release) ;;
    *) die "unknown profile '$profile' - there are two: smoke and release" ;;
esac

# Every path below that depends on which image is being built, decided
# once. A separate work directory per profile so that two builds do not
# overwrite each other's assembled profile, and a separate manifest so
# that the record of the smoke image is not replaced by the record of the
# shipping one.
readonly PROFILE_WORK="$WORK/profile-$profile"
readonly MANIFEST="$OUT/manifest-$profile.txt"
readonly PACKAGE_LIST="$OUT/packages-in-$profile.txt"

command -v docker >/dev/null || die "docker is not installed"
command -v rsync  >/dev/null || die "rsync is not installed"

# sudo -n, never plain sudo: this machine locks the account on a failed
# password prompt, so a build must fail loudly rather than sit at one.
docker() { command sudo -n docker "$@"; }

# --------------------------------------------------------------------
# The build container
# --------------------------------------------------------------------
step "Build container"
if $rebuild_image || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    docker build --network host -t "$IMAGE" -f "$ISO_DIR/Dockerfile" "$ISO_DIR"
else
    echo "reusing $IMAGE (--rebuild-image to refresh it)"
fi

# --------------------------------------------------------------------
# Assemble the profile
# --------------------------------------------------------------------
# The committed profile holds only what is ours. Nothing of src/ is
# copied in any more - packages.x86_64 names zepos-config and pacstrap
# installs it out of the [zepos] repository, which is the whole point of
# the change: the image now carries the same files, in the same places,
# with the same modes and the same signature as an installed system.
#
# The shipping profile is assembled out of two sources and the order
# matters: the allow-listed files from the harness profile first, then
# iso/profile-release/ over the top, which therefore wins on any file
# that appears in both. Nothing else from iso/profile/ is reachable from
# here - see the header of iso/shared-with-release.txt for why that
# direction is the safe one.
step "Assemble profile in $PROFILE_WORK"
rm -rf "$PROFILE_WORK"

mkdir -p "$PROFILE_WORK" "$OUT"

if [[ "$profile" == smoke ]]; then
    rsync -a --exclude '__pycache__' "$SMOKE_PROFILE"/ "$PROFILE_WORK"/
else
    [[ -f "$SHARED_LIST" ]] || die "no $SHARED_LIST - nothing says what the shipping image shares"

    shared_files="$(mktemp)"
    # shellcheck disable=SC2064
    trap "rm -f '$shared_files'" EXIT
    sed -e 's/#.*//' -e 's/[[:space:]]*$//' -e '/^$/d' "$SHARED_LIST" >"$shared_files"

    # Checked one by one before rsync is asked for any of them, so that a
    # typo in the list is a sentence naming the line rather than an
    # rsync error naming a temporary file.
    while read -r entry; do
        [[ -e "$SMOKE_PROFILE/$entry" || -L "$SMOKE_PROFILE/$entry" ]] || die \
            "$SHARED_LIST names $entry, which is not in iso/profile/"
    done <"$shared_files"

    rsync -a --files-from="$shared_files" "$SMOKE_PROFILE"/ "$PROFILE_WORK"/
    echo "shared from iso/profile/: $(wc -l <"$shared_files") files"
    rsync -a --exclude '__pycache__' "$RELEASE_PROFILE"/ "$PROFILE_WORK"/
fi

# --------------------------------------------------------------------
# The ZepOS package repository
# --------------------------------------------------------------------
[[ -f "$PKG_REPO/x86_64/zepos.db.tar.gz" ]] || die \
"no ZepOS package repository in packaging/out/.

The image installs zepos-config and aylurs-gtk-shell from it, so it has
to exist before the image can be built:

    ./packaging/build.sh --key <id>      or --no-sign

pacstrap will look for it at file://$PKG_REPO_MOUNT/\$arch, which is
where the mkarchiso container below mounts packaging/out/."

# Existing is not the same as current, and the difference has shipped.
#
# Measured, 10.08.2026: this build ran at 12:12 and put packages from
# 06.08 17:12 into the image, because the check above was the only one
# there was. The image went onto a USB stick without the TypeError fix
# it had been rebuilt for. Every ZepOS package is 0.1.0-1 before and
# after such a change, so no version, file name or database entry can
# tell the two apart - only the content can, which is what this reads.
step "Package repository is current"
"${PYTHON:-python3}" "$REPO/packaging/check-current.py" \
    --repo "$PKG_REPO/x86_64" || die \
"the packages in packaging/out/ were built from a different tree than
this one, and an image built from them would ship that older tree.

The lines above say which files differ. Build the packages again first."

# --------------------------------------------------------------------
# The offline repository, inside the image
# --------------------------------------------------------------------
# Spec §8.4's second row - "Kein Netz: alles aus dem ISO-Repo" - and the
# path is not a choice this build gets to make:
# installer/core/source.py's OFFLINE_REPO_URL is `file:///opt/zepos-repo`
# and does NOT end in $arch, whereas ONLINE_REPO_URL does. So what goes
# to /opt/zepos-repo is the CONTENTS of packaging/out/x86_64/, not the
# directory above it. packaging/README.md wrote that down when the
# repository layout was decided; this is the half of it that had never
# been built.
#
# Into the working profile rather than the committed one: packaging/out/
# is a build artefact, gitignored in full, and a repository of signed
# packages in the source tree would be the largest thing in the
# repository and stale the day after it was added.
#
# Note that this is a SECOND copy of the packages inside the image - the
# first is what pacstrap installs into the live system itself. That is
# not waste: the live system's copy is unpacked files, and what an
# installation needs is the .pkg.tar.zst next to a database pacman can
# read.
step "Offline repository -> airootfs/opt/zepos-repo"
install -d "$PROFILE_WORK/airootfs/opt/zepos-repo"
rsync -a "$PKG_REPO/x86_64"/ "$PROFILE_WORK/airootfs/opt/zepos-repo"/
echo "offline repo: $(du -sh "$PROFILE_WORK/airootfs/opt/zepos-repo" | cut -f1), \
$(ls "$PROFILE_WORK/airootfs/opt/zepos-repo"/*.pkg.tar.zst 2>/dev/null | wc -l) packages"

pacman_conf="$PROFILE_WORK/pacman.conf"

# Whether pacstrap is going to be able to verify what it installs.
#
# The public key is exported next to the repository by
# packaging/build.sh, and its absence means the repository was built with
# --no-sign. That is allowed - it is how someone tries a change without
# a key - but it must not be silent, and it must not leave a pacman.conf
# claiming a verification that is not happening.
if [[ -f "$PKG_REPO/zepos-repo.pub" ]]; then
    repo_signed=true
else
    repo_signed=false
    sed -i '/^\[zepos\]/,$ s/^SigLevel = .*/SigLevel = Optional TrustAll/' "$pacman_conf"
    cat >&2 <<'UNSIGNED'

    WARNING: the ZepOS repository is not signed.

    packaging/out/zepos-repo.pub does not exist, so this build cannot
    check what it installs and [zepos] has been relaxed to
    "Optional TrustAll" in the working copy of pacman.conf. Spec §8.6
    wants signatures from the first ISO. Rebuild the repository with
    ./packaging/build.sh --key <id> before this image is given to
    anybody.

UNSIGNED
fi

# --------------------------------------------------------------------
# Version pinning
# --------------------------------------------------------------------
# Read out of the ASSEMBLED profile, not out of iso/profile/: the
# shipping image's pacman.conf arrives through the shared list, and a pin
# read from one file while another one is edited is how the two images
# end up built against different snapshots under one date.
committed_snapshot="$(sed -n 's#^Server = https://archive.archlinux.org/repos/\([0-9/]*\)/\$repo.*#\1#p' \
    "$PROFILE_WORK/pacman.conf" | head -1)"
[[ -n "$committed_snapshot" ]] || die "no ALA snapshot found in the assembled profile's pacman.conf"

if [[ -z "$snapshot" ]]; then
    snapshot="$committed_snapshot"
elif [[ "$snapshot" == current ]]; then
    # Deliberately awkward to reach. Spec §8.7 wants the image pinned;
    # this exists only to answer "has upstream fixed it yet", and the
    # manifest below records that the answer came from an unpinned build.
    sed -i 's#^Server = https://archive.archlinux.org/repos/.*#Include = /etc/pacman.d/mirrorlist#' \
        "$pacman_conf"
else
    sed -i "s#^Server = https://archive.archlinux.org/repos/[0-9/]*/#Server = https://archive.archlinux.org/repos/${snapshot}/#" \
        "$pacman_conf"
fi
echo "package source: $snapshot"

# The same date, inside the image, for the one thing that needs it at run
# time rather than at build time.
#
# The image's own [core] and [extra] are pinned by the profile's
# pacman.conf above - but that file only ever configures mkarchiso's
# pacstrap. The LIVE environment's /etc/pacman.conf is the one the
# `pacman` package ships, and it says `Include = /etc/pacman.d/mirrorlist`
# against a mirrorlist whose every server is commented out. So an
# installation started from this medium can reach no Arch repository at
# all until something writes one, and both images write it from here -
# out of the pin that already exists, rather than out of a second copy of
# the date. On the smoke image that is zepos-install-unattended's first
# phase; on the shipping image it is zepos-live-prepare, which runs
# before the installer does.
#
# /usr/local/share, because nothing there is owned by a package: a file
# the profile ships at a path pacman also claims stops the build with
# "exists in filesystem", which is why archiso's own releng edits its
# mirrorlist from a pacman hook instead of shipping one.
install -Dm644 /dev/stdin "$PROFILE_WORK/airootfs/usr/local/share/zepos-install/ala-snapshot" \
    <<<"$snapshot"

# mkarchiso derives the ISO label and version from SOURCE_DATE_EPOCH.
# Taking it from the commit rather than from the clock is what makes two
# builds of one commit produce one image name (spec §8.7).
source_date_epoch="$(git -C "$REPO" log -1 --format=%ct 2>/dev/null || date +%s)"

# --------------------------------------------------------------------
# Which build this is, inside the image
# --------------------------------------------------------------------
# /zepos/version carries the date and nothing else, because mkarchiso
# derives it from SOURCE_DATE_EPOCH - so every image built on one day
# says the same thing. That is exactly the question that could not be
# answered on 10.08.2026, when the medium was rebuilt and rewritten four
# times in an afternoon and the only way to tell one from another was to
# mount it.
#
# The installer shows this line in its footer. Commit and build time,
# because the commit alone is the same across two builds of one tree -
# which is the pair a package rebuild produces.
# The "+" is not decoration. `rev-parse HEAD` names the last COMMIT, and
# an image built from a tree with uncommitted changes in it contains
# something that commit does not describe - which is most builds during
# an afternoon of changes, and exactly when the stamp is being read to
# tell two of them apart. A stamp that quietly named the wrong tree
# would be worse than none.
build_commit="$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)"
[[ -n "$(git -C "$REPO" status --porcelain 2>/dev/null)" ]] && build_commit="$build_commit+"

# -u, UND DAS IST AM 13.08.2026 GEMESSEN WORDEN
#     mkarchiso rechnet SOURCE_DATE_EPOCH in UTC um. Ohne -u steht hier
#     die Ortszeit des Bauenden, und die faellt den halben Sommer ueber
#     nicht auf - nur zwischen Mitternacht und zwei Uhr: ein Commit von
#     01:09 CEST ist 23:09 UTC am VORTAG.
#
#     Gemessen an genau so einem Commit:
#         lokal 2026.08.13   UTC 2026.08.12
#     Die ISO hiess zepos-2026.08.12, dieser Stempel haette 2026.08.13
#     gesagt, und der Lauf brach ab, weil er die Datei unter dem
#     falschen Namen suchte. Der Stempel ist der Weg, zwei Medien eines
#     Nachmittags auseinanderzuhalten - er muss dasselbe Datum tragen
#     wie der Name, sonst trennt er nicht, sondern verwirrt.
install -d "$PROFILE_WORK/airootfs/etc"
printf '%s %s %s\n' \
    "$(date -u --date="@$source_date_epoch" +%Y.%m.%d)" \
    "$build_commit" \
    "$(date -u +%H:%MZ)" \
    > "$PROFILE_WORK/airootfs/etc/zepos-build"

# The same line on the BOOT SCREEN, which is the first thing a medium
# shows and therefore the first place the question "which build is
# this" can be answered. The installer's footer carries it too, but
# that is two menus and a kernel later - and on 10.08.2026 an afternoon
# went into not being able to tell, from the screen, which of four
# images had booted.
#
# Appended to the help line both loaders already draw at the foot of
# the menu, so it costs no new element and no layout decision. Patched
# into the assembled profile rather than committed, because it is true
# of one build and not of the file.
# The separator is a dash and the sed delimiter is a tilde, because the
# help line's own separator is "|" - which is the character sed would
# otherwise have to be told is not the end of the pattern.
build_stamp="$(cat "$PROFILE_WORK/airootfs/etc/zepos-build")"
for menu in "$PROFILE_WORK/grub/themes/zepos/theme.txt" \
            "$PROFILE_WORK/syslinux/syslinux.cfg"; do
    [[ -f "$menu" ]] || continue
    sed -i "s~\(bearbeitet die Startoptionen\)~\1  -  $build_stamp~" "$menu"
done

# --------------------------------------------------------------------
# Build
# --------------------------------------------------------------------
step "mkarchiso"
docker run --rm --network host --privileged \
    -v "$ISO_DIR:/build" \
    -v "$PKG_REPO:$PKG_REPO_MOUNT:ro" \
    -e "SOURCE_DATE_EPOCH=$source_date_epoch" \
    -e "REPO_SIGNED=$repo_signed" \
    -e "PKG_REPO_MOUNT=$PKG_REPO_MOUNT" \
    -e "PROFILE=$profile" \
    "$IMAGE" \
    bash -euo pipefail -c '
        # ------------------------------------------------------------
        # Trust the ZepOS repository key
        # ------------------------------------------------------------
        # pacstrap verifies signatures against the pacman keyring of the
        # machine it RUNS on - this container - not against one in the
        # image being built: mkarchiso passes -G, so no keyring is copied
        # into the target, and pacman does not prefix its gpgdir with
        # --root. So the key has to be trusted here.
        #
        # --init before --add: --lsign-key signs the imported key with
        # pacman own local key, and the archlinux image ships a populated
        # keyring without one. Measured, in packaging/verify-install.sh
        # first: "There is no secret key available to sign with".
        #
        # These are the same three commands zepos-keyring will run on an
        # installed system, which is why they are worth getting right
        # here rather than working around.
        if [ "$REPO_SIGNED" = true ]; then
            pacman-key --init
            pacman-key --add "$PKG_REPO_MOUNT/zepos-repo.pub"
            fingerprint="$(gpg --with-colons --show-keys "$PKG_REPO_MOUNT/zepos-repo.pub" \
                | awk -F: "/^fpr:/ { print \$10; exit }")"
            pacman-key --lsign-key "$fingerprint"
            echo "ZepOS repository key trusted: $fingerprint"
        fi

        # Start from nothing, every time.
        #
        # mkarchiso remembers finished steps as marker files inside its
        # work directory and skips them on the next run. Measured: a
        # second build, after a real fix to the profile, produced an ISO
        # with the SAME sha256 as the first - it had skipped every step
        # and repackaged the previous root. A build tool that answers "no
        # change" to a change is worse than one that is slow.
        #
        # The removal happens in here rather than on the host because the
        # tree contains directories the packages install read-only
        # (dr-xr-xr-x), which only root can unlink through.
        work=/build/work/mkarchiso-$PROFILE
        rm -rf "$work"

        mkarchiso -v -w "$work" -o /build/out "/build/work/profile-$PROFILE"

        root=$work/x86_64/airootfs

        if [ "$PROFILE" = smoke ]; then
            # The live user has to exist in the built root, or the image
            # boots to a login prompt nobody can answer. It is created by
            # systemd-sysusers during pacstrap, through a hook - a chain
            # long enough that it is worth checking rather than assuming.
            if ! grep -q "^zepos:" "$root/etc/passwd"; then
                echo "FATAL: the live user was not created in the image" >&2
                exit 1
            fi
            grep "^zepos:" "$root/etc/passwd"
        else
            # ----------------------------------------------------------
            # The shipping image, checked against the root that was
            # actually built rather than against the profile it was built
            # from.
            # ----------------------------------------------------------
            # These are the four properties that make this image
            # handable, and every one of them is a property of the built
            # tree: a package could bring an autologin drop-in, a
            # mis-assembled profile could bring the harness back, and
            # neither would be visible in iso/profile-release/.
            fatal() { echo "FATAL: $*" >&2; exit 1; }

            [ -x "$root/usr/bin/zepos-install" ] \
                || fatal "the image has no executable /usr/bin/zepos-install"

            for path in usr/local/bin/zepos-smoke \
                        usr/local/bin/zepos-smoke-collect \
                        usr/local/bin/zepos-smoke-update \
                        usr/local/bin/zepos-install-unattended \
                        usr/local/share/zepos-install/unattended-install.json; do
                if [ -e "$root/$path" ]; then
                    fatal "the harness leaked into the image: /$path"
                fi
            done

            if grep -rl -- "--autologin" "$root/etc" 2>/dev/null | grep -q .; then
                grep -rl -- "--autologin" "$root/etc" >&2
                fatal "something in /etc logs a user in without asking"
            fi

            # An empty password field is a login that asks for nothing;
            # anything that is not a lock marker is a password somebody
            # could be told. Both are refused, and every account is
            # checked rather than root alone - a package can create a
            # user too.
            #
            # No single quotes anywhere in this container script: the
            # whole of it is one single-quoted argument on the host side,
            # and an awk program with quotes in it ends that argument
            # early. Measured, as an unbound $2 on the host.
            while IFS=: read -r account hash _rest; do
                case "$hash" in
                    "*"|"!"*) ;;
                    *) fatal "account $account in /etc/shadow has a usable password: $hash" ;;
                esac
            done <"$root/etc/shadow"

            echo "shipping image: installer present, no harness, no autologin, no credential"
        fi

        # What actually went in. mkarchiso writes this list from the
        # built root itself, so it is what IS in the image rather than
        # what packages.x86_64 asked for - the difference is every
        # dependency, which is most of it.
        cp "$work/iso/zepos/pkglist.x86_64.txt" "/build/out/packages-in-$PROFILE.txt"
        cp /usr/share/zepos-build-toolchain.txt /build/out/build-toolchain.txt
    '

# Everything docker wrote belongs to root; hand it back so the next run
# does not need privileges just to delete a work directory.
step "Restore ownership"
docker run --rm --network host -v "$ISO_DIR:/build" "$IMAGE" \
    chown -R "$(id -u):$(id -g)" /build/work /build/out

# --------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------
# By name, not by timestamp. Both images land in iso/out/, and
# `ls -t | head -1` picked "the newest ISO", which is the right file only
# for as long as the build that just ran is the one that wrote it - a
# release build that produced nothing would otherwise be reported with
# the smoke image's checksum.
iso_name="$(sed -n 's/^iso_name="\(.*\)"$/\1/p' "$PROFILE_WORK/profiledef.sh" | head -1)"
# -u aus demselben Grund wie beim Stempel oben: mkarchiso benennt die
# Datei nach SOURCE_DATE_EPOCH in UTC. Ohne -u sucht dieser Lauf zwischen
# Mitternacht und zwei Uhr nach einer Datei, die es nicht gibt.
iso_version="$(date -u --date="@$source_date_epoch" +%Y.%m.%d)"
iso_path="$OUT/${iso_name}-${iso_version}-x86_64.iso"
[[ -f "$iso_path" ]] || die "mkarchiso produced no $iso_path"

{
    echo "profile        $profile"
    echo "iso            $(basename "$iso_path")"
    echo "sha256         $(sha256sum "$iso_path" | cut -d' ' -f1)"
    echo "size           $(stat -c %s "$iso_path") bytes"
    echo "commit         $(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo unknown)"
    echo "package source $snapshot"
    echo "SOURCE_DATE_EPOCH $source_date_epoch"
    echo "built          $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "zepos repo     $($repo_signed && echo signed || echo UNSIGNED)"
    # Which build of the ZepOS packages went in. Without this the image's
    # manifest names a commit and a snapshot but not the third input, and
    # two images built from one commit against two package builds would
    # be indistinguishable here.
    grep -E '^(zepos-|libastal-|aylurs-)' "$PACKAGE_LIST" 2>/dev/null \
        | sed 's/^/zepos package  /'
} > "$MANIFEST"

step "Done"
cat "$MANIFEST"
echo
if [[ "$profile" == release ]]; then
    echo "Boot it with: ./iso/test-boot.py --scenario release"
else
    echo "Boot it with: ./iso/test-boot.py"
fi
