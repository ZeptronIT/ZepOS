#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Builds the ZepOS packages and the repository they are served from.
#
#     ./packaging/build.sh                    build everything, sign, refresh the repo
#     ./packaging/build.sh zepos-config       build one recipe
#     ./packaging/build.sh --no-sign          build an unsigned repository
#     ./packaging/build.sh --key <id>         sign with a particular key
#     ./packaging/build.sh --rebuild-image    rebuild the build container too
#
# The result is a pacman repository in packaging/out/. Nothing under
# packaging/out/ or packaging/keys/ is committed - see .gitignore.
#
# WHY A CONTAINER
#     Spec §10. makepkg installs build dependencies, and a package built
#     against whatever happens to be on a workstation has a dependency
#     list that describes that workstation. packaging/Dockerfile has the
#     rest of the argument, including why the container is pinned to the
#     same Arch Linux Archive snapshot as the ISO.
#
# WHY --network host ON EVERY docker run
#     Spec §10.1, measured: the IPsec tunnel on this machine routes all
#     three RFC1918 ranges, the Docker bridge sits inside 10.0.0.0/8, and
#     a bridged container's packets vanish into the tunnel. There is no
#     private range left to move the bridge into.
#
# WHY THE PRIVATE KEY NEVER ENTERS THE CONTAINER
#     Signing happens here, on the host, after the container has exited.
#     A build container runs build() functions from upstream tarballs;
#     handing that a signing key means every future upstream release can
#     read it. The container produces packages, the host signs them, and
#     the two steps do not share a directory that could carry a key.
set -euo pipefail

readonly REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly PACKAGING="$REPO/packaging"
readonly OUT="$PACKAGING/out"
readonly REPO_DIR="$OUT/x86_64"
readonly IMAGE="zepos-pkgbuild"

# The name pacman will know this repository by. installer/core/source.py
# writes exactly this into the target's pacman.conf, for both the online
# and the offline source, so the database file has to be called
# zepos.db.tar.gz and nothing else.
readonly REPO_NAME="zepos"

# Build order, which is dependency order: aylurs-gtk-shell declares
# libastal-io and libastal-4 among its depends, and makepkg --syncdeps
# cannot resolve those from any repository until they have been built.
# Each package is installed into the build container as it is finished,
# which is what makes the next one resolvable.
#
# The five plugin recipes are the same shape and a stronger case. A
# Hyprland plugin is compiled against the compositor's own headers, so
# zepos-hyprland is not merely a version they name - it is the source of
# the header set the objects carry inside themselves, and it has to be
# INSTALLED in the container before any of them is configured:
# `pkg_check_modules(HYPRLAND REQUIRED hyprland)` reads the hyprland.pc
# that package puts in /usr/share/pkgconfig, and meson and cmake both
# stop at the configure step without it.
#
# tests/packaging/test_recipes.py requires every directory under
# packaging/ that holds a PKGBUILD to appear here - a recipe that is not
# in the order is a recipe that is never built.
#
# zepos-desktop is last, and that is dependency order too. It is a meta
# package: makepkg --syncdeps resolves its `depends` like any other
# recipe's, so building it is what proves every name in that list exists
# in some repository - the one failure mode a meta package has, and one
# that otherwise appears on a user's machine rather than here. Its ZepOS
# dependencies are exactly the packages the recipes above produced, which
# install_built has already put into the container by then.
readonly PACKAGES=(
    zepos-config
    zepos-keyring
    zepos-installer
    zepos-logout
    zepos-lock
    zepos-menu
    zepos-settings-gui
    zsh-theme-powerlevel10k
    astal
    aylurs-gtk-shell
    zepos-hyprland
    zepos-hyprlaunch
    zepos-hyprclipx
    zepos-hyprzones
    hyprland-plugins
    # Vor zepos-apps, weil dessen depends darauf zeigt: hier steht die
    # Reihenfolge, in der gebaut und ins Repo gelegt wird, und ein Paket,
    # dessen Abhaengigkeit noch nicht im Repo liegt, laesst sich beim
    # Bauen nicht aufloesen.
    zepos-claude-code
    zepos-apps
    zepos-apps-office
    zepos-apps-devel
    zepos-desktop
)

die() { printf 'packaging/build.sh: %s\n' "$*" >&2; exit 1; }
step() { printf '\n==> %s\n' "$*"; }

rebuild_image=false
sign=true
key="${ZEPOS_SIGNING_KEY:-}"
selected=()

while (( $# )); do
    case "$1" in
        --rebuild-image) rebuild_image=true; shift ;;
        --no-sign) sign=false; shift ;;
        --key)
            [[ $# -ge 2 ]] || die "--key needs a key id"
            key="$2"; shift 2 ;;
        -h|--help)
            sed -n '3,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        -*) die "unknown argument: $1" ;;
        *) selected+=("$1"); shift ;;
    esac
done

named_on_command_line=false
(( ${#selected[@]} )) && named_on_command_line=true
(( ${#selected[@]} )) || selected=("${PACKAGES[@]}")
for name in "${selected[@]}"; do
    [[ -f "$PACKAGING/$name/PKGBUILD" ]] || die "no recipe: packaging/$name/PKGBUILD"
done

# The two recipes a key is not optional for.
#
# zepos-keyring IS the key - it ships the public half and the ownertrust
# line pacman-key locally signs, and a keyring package built without one
# would install, populate nothing, and leave a machine failing its next
# `pacman -Syu` on a signature from a key nobody can find. The recipe
# refuses rather than produce that. zepos-desktop depends on
# zepos-keyring, so it cannot be built either.
#
# The rest of the repository still builds unsigned, which is what
# --no-sign is for. It is simply not a complete repository, and saying so
# here is cheaper than discovering it from a meta package that resolves
# on the build machine and nowhere else.
readonly NEEDS_KEY=(zepos-keyring zepos-desktop)

command -v docker >/dev/null || die "docker is not installed"
command -v repo-add >/dev/null || die "repo-add is not installed (it comes with pacman)"

# sudo -n, never plain sudo: a failed password prompt locks the account
# on this machine, so a build must fail loudly rather than sit at one.
docker() { command sudo -n docker "$@"; }

# --------------------------------------------------------------------
# The pin, read from the one file that holds it
# --------------------------------------------------------------------
# Not a second copy of the date. iso/profile/pacman.conf is where the
# snapshot is decided, and a package built against a different snapshot
# than the image it is installed into is a package linked against
# libraries that are not there.
snapshot="$(sed -n 's#^Server = https://archive.archlinux.org/repos/\([0-9/]*\)/\$repo.*#\1#p' \
    "$REPO/iso/profile/pacman.conf" | head -1)"
[[ -n "$snapshot" ]] || die "no ALA snapshot found in iso/profile/pacman.conf"

version="$(<"$REPO/VERSION")"
[[ -n "$version" ]] || die "VERSION is empty"

# From the commit rather than from the clock. makepkg clamps every file
# modification time in the package to SOURCE_DATE_EPOCH, so this is what
# stops two builds of one commit producing two different tarballs (spec
# §8.7).
source_date_epoch="$(git -C "$REPO" log -1 --format=%ct 2>/dev/null || date +%s)"

echo "version        $version"
echo "package source $snapshot"
echo "SOURCE_DATE_EPOCH $source_date_epoch"

# --------------------------------------------------------------------
# The key, resolved before anything is built
# --------------------------------------------------------------------
# Resolved here rather than at the signing step below, and that is not a
# tidy-up: zepos-keyring PACKAGES the public half, so the key has to be
# known before the build container starts, not after it exits.
#
# ZEPOS_GNUPGHOME points at a keyring that is not the developer's own.
# packaging/make-test-key.sh creates one under packaging/keys/, which is
# gitignored in full: a private key must never be recoverable from a
# clone, not even a test one.
#
# Made absolute, and that is not tidiness either: repo-add is run from
# inside the repository directory, and a relative GNUPGHOME resolves
# against whatever directory gpg is called from. Measured - the signing
# step succeeded and repo-add then failed with "The key ... does not
# exist in your keyring", pointing at a keyring that had simply moved out
# from under it.
if [[ -n "${ZEPOS_GNUPGHOME:-}" ]]; then
    export GNUPGHOME="$(cd -- "$ZEPOS_GNUPGHOME" && pwd)"
elif [[ -d "$PACKAGING/keys/gnupg" ]]; then
    export GNUPGHOME="$PACKAGING/keys/gnupg"
fi

# Where zepos-keyring's recipe looks for the key it ships. Gitignored,
# for the reason its header gives: today this file holds the throwaway
# key make-test-key.sh produced, and a keyring package committed around
# it would be a distribution trusting a key whose private half is in
# somebody's working tree.
readonly KEYRING_SOURCE="$PACKAGING/zepos-keyring/zepos-repo.pub"

if $sign; then
    [[ -n "$key" ]] || die \
"no signing key. Spec §8.6 wants signatures from the first ISO, because a
repository that starts unsigned makes every already-installed system import
a key by hand later. Give one of:

    --key <id>                  or  ZEPOS_SIGNING_KEY=<id>
    ./packaging/make-test-key.sh    generates a throwaway key for testing
    --no-sign                       build an unsigned repository anyway"

    step "Signing key"
    # The PUBLIC half only, and it is the only piece of key material that
    # ever leaves this keyring. It goes to a directory the build
    # container can read, which is exactly why the private half must not:
    # a build container runs build() functions out of upstream tarballs.
    gpg --batch --yes --export --output "$KEYRING_SOURCE" "$key" \
        || die "could not export the public half of $key"
    [[ -s "$KEYRING_SOURCE" ]] || die \
        "gpg exported nothing for $key - is it in ${GNUPGHOME:-the default keyring}?"
    gpg --with-colons --show-keys "$KEYRING_SOURCE" \
        | awk -F: '/^fpr:/ { printf "  fingerprint  %s\n", $10 }
                   /^uid:/ { printf "  user id      %s\n", $10 }' \
        | head -2
else
    # A stale export from an earlier signed run must not survive into an
    # unsigned one: it would build a zepos-keyring for a key that signed
    # nothing in this repository.
    rm -f "$KEYRING_SOURCE"

    filtered=()
    for name in "${selected[@]}"; do
        for keyed in "${NEEDS_KEY[@]}"; do
            if [[ "$name" == "$keyed" ]]; then
                $named_on_command_line && die \
                    "$name cannot be built with --no-sign: it needs the key it ships."
                rm -f "$REPO_DIR/$name"-*.pkg.tar.zst
                continue 2
            fi
        done
        filtered+=("$name")
    done
    selected=("${filtered[@]}")

    cat >&2 <<'NOKEYRING'

    WARNING: zepos-keyring and zepos-desktop are NOT being built.

    zepos-keyring ships the public half of the key the repository is
    signed with, and --no-sign means there is none. zepos-desktop
    depends on it. Everything else builds; the result is a repository an
    installed system cannot verify and has no meta package to install.
    ./packaging/make-test-key.sh produces a throwaway key in one command.

NOKEYRING
fi

# --------------------------------------------------------------------
# The build container
# --------------------------------------------------------------------
# What the image WOULD be built from, in one string: the Dockerfile and
# the snapshot it is given. Stamped onto the image as a label and
# compared on the next run.
#
# Measured, and it cost an afternoon: adding a build dependency to the
# Dockerfile and running ./packaging/build.sh again reused the old image
# without a word, and the recipe failed on a missing tool that the
# Dockerfile plainly installed. `--rebuild-image` was the fix and
# remembering to type it was the bug. An image that does not match the
# file that describes it is not a cache hit.
# Hashed from the CONTENTS, not with the path in front of them: a clone
# at another location would otherwise compute a different id for the same
# Dockerfile and rebuild an image that is already correct.
dockerfile_id="$(
    { sha256sum <"$PACKAGING/Dockerfile"; echo "$snapshot"; } | sha256sum | cut -d' ' -f1)"
image_id="$(docker image inspect \
    --format '{{index .Config.Labels "zepos.dockerfile"}}' "$IMAGE" 2>/dev/null || true)"

step "Build container"
if $rebuild_image || [[ "$image_id" != "$dockerfile_id" ]]; then
    if [[ -n "$image_id" && "$image_id" != "<no value>" ]]; then
        echo "packaging/Dockerfile or the snapshot changed - rebuilding $IMAGE"
    fi
    docker build --network host \
        --build-arg "ALA_SNAPSHOT=$snapshot" \
        --build-arg "BUILDER_UID=$(id -u)" \
        --build-arg "BUILDER_GID=$(id -g)" \
        --label "zepos.dockerfile=$dockerfile_id" \
        -t "$IMAGE" -f "$PACKAGING/Dockerfile" "$PACKAGING"
else
    echo "reusing $IMAGE (unchanged Dockerfile; --rebuild-image to refresh it anyway)"
fi

# --------------------------------------------------------------------
# The four sources that are ours
# --------------------------------------------------------------------
# zepos-config packages this repository's own src/, zepos-installer
# packages installer/, zepos-logout packages logout/ and zepos-lock
# packages lock/, so their source tarballs are made here rather than
# downloaded. Made from the WORKING TREE, not from git: a developer who
# has just edited a template and runs
# this expects to get that template, and a build that silently packages
# the last commit instead is a build that tests the wrong thing.
#
# --sort=name and the two fixed times make a tarball a function of its
# contents alone, so an unchanged tree gives a byte-identical tarball.
selected_holds() { printf '%s\n' "${selected[@]}" | grep -qx "$1"; }

pack_stage() {
    local recipe="$1" stem="$2"
    tar czf "$PACKAGING/$recipe/$stem.tar.gz" \
        -C "$PACKAGING/$recipe/.stage" \
        --sort=name --owner=0 --group=0 --numeric-owner \
        --mtime="@$source_date_epoch" \
        "$stem"
    rm -rf "$PACKAGING/$recipe/.stage"
    echo "$stem.tar.gz  $(sha256sum "$PACKAGING/$recipe/$stem.tar.gz" | cut -d' ' -f1)"
}

if selected_holds zepos-config; then
    step "Source tarball for zepos-config"
    stage="$PACKAGING/zepos-config/.stage/zepos-$version"
    rm -rf "$PACKAGING/zepos-config/.stage"
    mkdir -p "$stage"
    rsync -a --exclude '__pycache__' --exclude '.gitignore' "$REPO/src"/ "$stage"/
    rsync -a "$REPO/LICENSE" "$stage/LICENSE"

    # Der Katalog der Oberflaeche, und zwar als .po und nicht als .mo.
    #
    # Dieselbe Regel, aus der po/ auch beim Installer mitkommt (siehe
    # dort): das Rezept uebersetzt ihn mit demselben po/build.sh, das
    # ein Entwicklerbaum aufruft, und ein .mo wird nicht eingecheckt.
    #
    # NUR desktop/ und build.sh, nicht das ganze po/. Der Katalog des
    # Installers gehoert dem Paket zepos-installer, und ein zweites
    # Paket, das dieselbe Datei mitschleppt, ist ein zweiter Ort, an dem
    # sie alt sein kann. po/build.sh geht ueber eine Domaene ohne
    # Katalog hinweg, deshalb genuegt die Haelfte.
    mkdir -p "$stage/po"
    rsync -a "$REPO/po/build.sh" "$stage/po/build.sh"
    rsync -a "$REPO/po/desktop"/ "$stage/po/desktop"/

    # Das Startmenue, aus dem ISO-Profil und nicht aus einer zweiten
    # Kopie unter src/.
    #
    # WARUM VON DORT
    #     Es ist dasselbe Menue. Das Medium zeigt es beim Booten und die
    #     Installation soll es danach zeigen - "genauso wie Debian es mit
    #     GRUB macht". Zwei Baeume mit demselben Bild waeren zwei Bilder,
    #     sobald jemand eins davon anfasst, und tests/iso/
    #     test_boot_theme.py misst die Farben an der Datei im ISO-Profil.
    #     Dieselbe Regel, aus der oben schon der ALA-Schnappschuss aus
    #     iso/profile/pacman.conf gelesen wird statt hier wiederholt zu
    #     werden.
    #
    # WARUM DIE SCHRIFTEN INS THEMENVERZEICHNIS WANDERN
    #     Auf dem Medium laedt grub.cfg sie von Hand mit `loadfont
    #     /boot/grub/fonts/roboto-24.pf2`, deshalb liegen sie dort neben
    #     themes/. Auf einer Installation schreibt grub-mkconfig die
    #     Ladezeilen selbst, und /etc/grub.d/00_header sucht dafuer
    #     ausschliesslich in "$themedir"/*.pf2 und "$themedir"/f/*.pf2
    #     (Zeile 281). Eine Schrift daneben wuerde nie geladen, theme.txt
    #     bekaeme fuer "Roboto Regular 24" keine Zuordnung, und GRUB
    #     zeichnet ein Thema ohne Schrift als Textmenue - ohne Fehler.
    #
    #     "f/" und nicht direkt ins Themenverzeichnis: 00_header sucht in
    #     beiden, und getrennt bleibt jedes der zwei Verzeichnisse hier
    #     die Kopie GENAU EINES Verzeichnisses drueben. packaging/
    #     check-current.py vergleicht Paket gegen Baum ueber solche
    #     Praefixe, und zwei Quellen in einem Zielverzeichnis waeren dort
    #     ein Eintrag pro Datei statt einer pro Verzeichnis.
    theme="$REPO/iso/profile-release/grub/themes/zepos"
    fonts="$REPO/iso/profile-release/grub/fonts"
    [[ -d "$theme" ]] || die "no boot theme at $theme"
    [[ -d "$fonts" ]] || die "no boot theme fonts at $fonts"
    rsync -a "$theme"/ "$stage/boot/grub-theme"/
    rsync -a "$fonts"/ "$stage/boot/grub-theme/f"/

    pack_stage zepos-config "zepos-$version"
fi

# installer/ keeps its directory rather than being flattened the way src/
# is: the recipe installs it as the python package `installer`, which is
# the name every module inside it imports itself by. po/ comes along
# because the recipe compiles the catalogue with the same po/build.sh a
# checkout runs - the catalogue is not committed as a .mo, so it has to
# be built from the .po that is.
# menu/ behaelt sein Verzeichnis, genau wie installer/: das Rezept legt
# es als Python-Paket `zepos_menu` ab, und /usr/bin/zepos-menu sucht es
# unter genau diesem Namen. LICENSE kommt mit, weil jedes Paket seine
# eigene Kopie unter /usr/share/licenses ablegt.
if selected_holds zepos-menu; then
    step "Source tarball for zepos-menu"
    stage="$PACKAGING/zepos-menu/.stage/zepos-menu-$version"
    rm -rf "$PACKAGING/zepos-menu/.stage"
    mkdir -p "$stage"
    rsync -a --exclude '__pycache__' "$REPO/menu"/ "$stage"/
    rsync -a "$REPO/LICENSE" "$stage/LICENSE"
    pack_stage zepos-menu "zepos-menu-$version"
fi

# settings/ behaelt sein Verzeichnis wie menu/: das Rezept legt es als
# Python-Paket `zepos_settings_gui` ab, und /usr/bin/zepos-settings-gui
# sucht es unter genau diesem Namen. Die .desktop-Datei kommt mit, weil
# sie in demselben Verzeichnis liegt wie das, was sie startet - eine
# Kopie unter packaging/ waere ein Eintrag mit einem eigenen Leben.
if selected_holds zepos-settings-gui; then
    step "Source tarball for zepos-settings-gui"
    stage="$PACKAGING/zepos-settings-gui/.stage/zepos-settings-gui-$version"
    rm -rf "$PACKAGING/zepos-settings-gui/.stage"
    mkdir -p "$stage"
    rsync -a --exclude '__pycache__' "$REPO/settings"/ "$stage"/
    rsync -a "$REPO/LICENSE" "$stage/LICENSE"
    pack_stage zepos-settings-gui "zepos-settings-gui-$version"
fi

if selected_holds zepos-installer; then
    step "Source tarball for zepos-installer"
    stage="$PACKAGING/zepos-installer/.stage/zepos-installer-$version"
    rm -rf "$PACKAGING/zepos-installer/.stage"
    mkdir -p "$stage"
    rsync -a --exclude '__pycache__' "$REPO/installer" "$stage"/
    rsync -a --exclude 'build' "$REPO/po" "$stage"/
    # The logo, out of the SAME src/branding/ that zepos-config packages
    # the wallpaper from. Two packages, one file in the tree: a copy
    # committed under installer/ would be the same picture with two
    # futures, and the one nobody looks at is the one that goes stale.
    rsync -a "$REPO/src/branding" "$stage"/
    rsync -a "$REPO/LICENSE" "$stage/LICENSE"
    pack_stage zepos-installer "zepos-installer-$version"
fi

# logout/ behaelt sein Verzeichnis wie installer/, und aus einem
# handfesten Grund: logout/meson.build liest die Projektversion mit
# `cat ../VERSION`, also einen Pfad NEBEN dem Verzeichnis. Flach
# ausgepackt gaebe es dieses Neben nicht und meson broeche beim Setup ab.
# VERSION kommt deshalb mit, und das ist keine zweite Kopie der Zahl -
# es ist dieselbe Datei, aus der auch $version oben gelesen wurde.
if selected_holds zepos-logout; then
    step "Source tarball for zepos-logout"
    stage="$PACKAGING/zepos-logout/.stage/zepos-logout-$version"
    rm -rf "$PACKAGING/zepos-logout/.stage"
    mkdir -p "$stage"
    rsync -a "$REPO/logout" "$stage"/
    rsync -a "$REPO/VERSION" "$stage/VERSION"
    rsync -a "$REPO/LICENSE" "$stage/LICENSE"
    pack_stage zepos-logout "zepos-logout-$version"
fi

# lock/ genauso, und aus demselben Grund: lock/meson.build liest die
# Projektversion mit `cat ../VERSION`, also aus dem Verzeichnis DANEBEN.
if selected_holds zepos-lock; then
    step "Source tarball for zepos-lock"
    stage="$PACKAGING/zepos-lock/.stage/zepos-lock-$version"
    rm -rf "$PACKAGING/zepos-lock/.stage"
    mkdir -p "$stage"
    rsync -a "$REPO/lock" "$stage"/
    rsync -a "$REPO/VERSION" "$stage/VERSION"
    rsync -a "$REPO/LICENSE" "$stage/LICENSE"
    pack_stage zepos-lock "zepos-lock-$version"
fi

# Die beiden Plugins, deren Quelle seit dem 11.08.2026 in diesem Baum
# liegt statt auf einem fremden GitHub-Konto.
#
# WARUM SIE FLACH AUSGEPACKT WERDEN UND NICHT WIE logout/ IHR
# VERZEICHNIS BEHALTEN
#     Weil ihr CMakeLists.txt an der Wurzel des Projekts steht und mit
#     ${CMAKE_SOURCE_DIR}/include rechnet. logout/ behaelt sein
#     Verzeichnis, weil sein meson.build die Version mit `cat
#     ../VERSION` aus dem Verzeichnis DANEBEN liest - diese beiden
#     brauchen kein Daneben, und ein zusaetzliches plugins/hyprlaunch/
#     im Tarball waere ein Pfad mehr, den das Rezept nachbilden muss.
#
# WARUM plugins/LICENSE MITKOMMT UND NICHT DAS LICENSE DER WURZEL
#     Weil es eine andere Lizenz ist. Der Baum steht unter GPL-3.0;
#     diese beiden Verzeichnisse sind eine Bearbeitung fremder
#     BSD-3-Clause-Quellen, und der Urhebervermerk, den Bedingung 1
#     dieser Lizenz zu erhalten verlangt, steht in plugins/LICENSE.
#     Das Rezept legt genau diese Datei unter /usr/share/licenses ab -
#     die GPL dorthin zu legen waere eine falsche Auskunft ueber
#     fremden Code.
for _plugin in hyprlaunch hyprclipx; do
    selected_holds "zepos-$_plugin" || continue
    step "Source tarball for zepos-$_plugin"
    stage="$PACKAGING/zepos-$_plugin/.stage/zepos-$_plugin-$version"
    rm -rf "$PACKAGING/zepos-$_plugin/.stage"
    mkdir -p "$stage"
    rsync -a "$REPO/plugins/$_plugin"/ "$stage"/
    rsync -a "$REPO/plugins/LICENSE" "$stage/LICENSE"
    pack_stage "zepos-$_plugin" "zepos-$_plugin-$version"
done
unset _plugin

# --------------------------------------------------------------------
# Build
# --------------------------------------------------------------------
mkdir -p "$REPO_DIR"

# Signatures are made after the build, so none may exist during it.
#
# Measured: on the second run, the packages left by the first were still
# signed, and the container's `pacman -U` - which installs finished
# packages so the next recipe can depend on them - refused all of them
# with "key ... could not be looked up remotely / required key missing
# from keyring". The build container has no reason to hold the signing
# key and must not: verification belongs to the ISO build and to the
# installed system, both of which get the public half deliberately.
#
# It is also correct on its own terms. makepkg rewrites the package, so a
# signature from the previous run describes a file that no longer exists,
# and every package in the repository is re-signed below in any case.
rm -f "$REPO_DIR"/*.pkg.tar.zst.sig

# --------------------------------------------------------------------
# Die alte Fassung jedes Pakets, das gleich neu entsteht
# --------------------------------------------------------------------
# GEMESSEN am 12.08.2026: der Lauf brach nach zepos-lock ab mit
#
#     error: unresolvable package conflicts detected
#     error: failed to prepare transaction (conflicting dependencies)
#
# und der Widerspruch war einer zwischen zwei Staenden DESSELBEN Baums:
# das frisch gebaute zepos-lock traegt conflicts=('hyprlock'), waehrend
# im Repository noch das zepos-desktop des Vortags lag, das hyprlock
# VERLANGT. Das naechste Rezept loeste seine Abhaengigkeiten gegen beide
# auf und fand keinen Weg.
#
# Beide Pakete wurden in diesem Lauf ersetzt. Der Konflikt bestand also
# nur zwischen einer Vergangenheit und einer Zukunft, die sich nie
# begegnen - und genau deshalb faellt er auch nicht durch mehr Sorgfalt
# in den Rezepten weg, sondern nur dadurch, dass die Vergangenheit
# waehrend des Baus nicht mehr im Weg steht.
#
# Deshalb hier und nicht spaeter: repo-add lief bisher NACH jedem
# einzelnen Paket, also stand die alte Datenbank noch, waehrend das
# naechste Rezept aufloeste. Was gleich neu gebaut wird, gehoert vorher
# aus dem Repository.
#
# Nur die AUSGEWAEHLTEN: `build.sh zepos-config` soll nicht nebenbei
# alles andere aus dem Repository raeumen, was es gar nicht anfasst.
step "alte Faelle der ausgewaehlten Pakete entfernen"
for name in "${selected[@]}"; do
    for produced in $(awk '
            /^pkgname=\(/ { gsub(/^pkgname=\(|\)$/, ""); print; next }
            /^pkgname=/    { sub(/^pkgname=/, ""); print }
        ' "$PACKAGING/$name/PKGBUILD" 2>/dev/null | tr -d "'\"" ); do
        rm -f "$REPO_DIR/$produced"-[0-9]*.pkg.tar.zst \
              "$REPO_DIR/$produced"-[0-9]*.pkg.tar.zst.sig
    done
done

step "makepkg"
docker run --rm --network host \
    -v "$REPO:/repo" \
    -e "SOURCE_DATE_EPOCH=$source_date_epoch" \
    -e "PACKAGES=${selected[*]}" \
    --user builder \
    "$IMAGE" \
    bash -euo pipefail -c '
        export PKGDEST=/repo/packaging/out/x86_64
        export HOME=/home/builder
        shopt -s nullglob

        # Everything already in the repository directory, installed into
        # this container.
        #
        # ONE pacman call for all of them, not one call each: the split
        # astal recipe produces libastal-4, which depends on libastal-io,
        # and the shell expands the glob alphabetically - installed one
        # at a time, libastal-4 comes first and fails with "cannot
        # resolve libastal-io". A single transaction sees both.
        install_built() {
            local built=("$PKGDEST"/*.pkg.tar.zst)
            if (( ${#built[@]} )); then
                sudo pacman -U --noconfirm --needed "${built[@]}" >/dev/null
            fi
        }

        # Before the first recipe, not only between them. The container is
        # new on every run, so a build of ONE package whose dependencies
        # were produced by an earlier run has nothing installed and no
        # repository to find them in. Measured:
        #
        #     ./packaging/build.sh aylurs-gtk-shell
        #     error: target not found: libastal-io
        #
        # even though libastal-io was sitting in packaging/out/ at the
        # time. A partial build is the normal case while working on one
        # recipe, so it has to work.
        install_built

        for name in $PACKAGES; do
            printf "\n---- %s ----\n" "$name"
            cd "/repo/packaging/$name"
            # --cleanbuild so that a stale $srcdir from an interrupted
            # run cannot be mistaken for a fresh unpack, --force so that
            # rebuilding an unchanged version replaces the artefact
            # instead of refusing.
            makepkg --syncdeps --noconfirm --cleanbuild --clean --force

            # And again after each recipe, so that the next one can
            # declare what this one just produced.
            install_built
        done
        cp /usr/share/zepos-pkgbuild-toolchain.txt /repo/packaging/out/build-toolchain.txt
    '

# --------------------------------------------------------------------
# Sign
# --------------------------------------------------------------------
# GNUPGHOME and the key were resolved before the build - zepos-keyring
# packages the public half, so waiting until here would be too late.
if $sign; then
    step "Sign"
    for package in "$REPO_DIR"/*.pkg.tar.zst; do
        rm -f "$package.sig"
        gpg --batch --yes --no-armor --detach-sign \
            --local-user "$key" --output "$package.sig" "$package"
        gpg --verify "$package.sig" "$package" 2>&1 | sed 's/^/  /'
    done

    # The public half, next to the repository. iso/build.sh imports this
    # into the build container's pacman keyring so that pacstrap will
    # accept the packages.
    #
    # Copied from the file zepos-keyring was built out of rather than
    # exported a second time. Two exports would almost always agree, and
    # "almost always" is the wrong property for the pair of files that
    # decide whether an installed system trusts the same key the ISO did:
    # a key edited between the two calls - a new uid, a changed expiry -
    # would produce an image trusting one thing and a keyring package
    # shipping another.
    install -Dm644 "$KEYRING_SOURCE" "$OUT/$REPO_NAME-repo.pub"
else
    step "Sign - skipped (--no-sign)"
    # EVERY signature in the directory, not only the packages'. repo-add
    # without --sign does not remove the database signature a previous
    # signed build left, and zepos.db.sig sitting next to a freshly
    # written zepos.db is a file that describes a database that no longer
    # exists. Measured on exactly this sequence: a signed build followed
    # by --no-sign left zepos.db.sig, zepos.files.sig and the .old ones.
    rm -f "$REPO_DIR"/*.sig "$OUT/$REPO_NAME-repo.pub"
fi

# --------------------------------------------------------------------
# The repository
# --------------------------------------------------------------------
# repo-add builds the database; a static directory is all pacman needs to
# serve it. installer/core/source.py already decided where that directory
# is published - https://zeptronit.github.io/ZepOS/$arch online,
# file:///opt/zepos-repo offline - so the layout is fixed by it:
#
#     packaging/out/x86_64/zepos.db -> zepos.db.tar.gz
#     packaging/out/x86_64/*.pkg.tar.zst  and  *.pkg.tar.zst.sig
#
# The online URL ends in $arch, so the published root is packaging/out/
# and the architecture directory below it is what pacman fetches. The
# offline URL does not, so the ISO copies the CONTENTS of x86_64/ into
# /opt/zepos-repo. One build, both layouts, no second copy of anything.
step "repo-add"
repo_add_options=()
$sign && repo_add_options+=(--sign --key "$key")
(
    cd "$REPO_DIR"
    repo-add "${repo_add_options[@]}" \
        "$REPO_NAME.db.tar.gz" ./*.pkg.tar.zst
)

# --------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------
{
    echo "version           $version"
    echo "commit            $(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo unknown)"
    echo "package source    $snapshot"
    echo "SOURCE_DATE_EPOCH $source_date_epoch"
    echo "signed            $($sign && echo "yes, key $key" || echo no)"
    echo "built             $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
    for package in "$REPO_DIR"/*.pkg.tar.zst; do
        printf '%s  %s\n' "$(sha256sum "$package" | cut -d' ' -f1)" "$(basename "$package")"
    done
} > "$OUT/manifest.txt"

step "Done"
cat "$OUT/manifest.txt"
