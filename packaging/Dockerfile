# The container that builds the ZepOS packages.
#
# WHY A CONTAINER AT ALL
#     Spec §10: the development machine is not the build machine. makepkg
#     installs build dependencies, and a package built against whatever
#     happens to be installed on a workstation is a package whose
#     `depends` are a description of that workstation.
#
# WHY THIS IMAGE IS PINNED TO THE SAME SNAPSHOT AS THE ISO
#     iso/Dockerfile draws a line between the tool and the material: the
#     tool (archiso) is current, the material (what goes into the image)
#     is pinned. Package building does not get to draw that line in the
#     same place, because here the tool AND the material are the same
#     packages: astal-4 links against the gtk4 that is installed while it
#     builds, and the resulting binary then has to run against the gtk4
#     in the image. Two different snapshots means a library built against
#     4.22.4 loaded next to 4.23.0, which is exactly the class of failure
#     a pinned image exists to prevent.
#
#     So ALA_SNAPSHOT is passed in by packaging/build.sh, which reads it
#     out of iso/profile/pacman.conf. The pin is written down once, in
#     the file the ISO already uses.
#
# WHY --network host
#     Spec §10.1, measured: this machine's IPsec tunnel routes all three
#     RFC1918 ranges and the Docker bridge sits inside 10.0.0.0/8, so a
#     bridged container has no network at all. It is passed on the
#     command line by packaging/build.sh - a Dockerfile cannot set it.
FROM archlinux:latest

ARG ALA_SNAPSHOT

# Both repositories, one snapshot. -Syyuu rather than -Syu because the
# base image is normally NEWER than the pinned snapshot, and moving to a
# pin is a downgrade; -Syu would refuse it and leave a container whose
# libraries are from two different days.
RUN test -n "$ALA_SNAPSHOT" \
    && printf 'Server = https://archive.archlinux.org/repos/%s/$repo/os/$arch\n' \
        "$ALA_SNAPSHOT" > /etc/pacman.d/mirrorlist \
    && pacman -Syyuu --noconfirm

# base-devel carries fakeroot, gcc and make; spec §10 already recorded
# that archlinux:latest does not. The rest is what the three recipes in
# packaging/ need: go for the AGS command line tool, vala + meson +
# gobject-introspection for the astal libraries, and the GTK stack they
# link against.
RUN pacman -S --needed --noconfirm \
        base-devel \
        git \
        go \
        meson \
        vala \
        gobject-introspection \
        gtk4 \
        gtk4-layer-shell \
        gdk-pixbuf2 \
        json-glib \
        glib2 \
        gjs \
        python \
        pkgconf \
        rsync \
    && pacman -Scc --noconfirm

# The compositor and the five plugins.
#
# WHY THESE ARE IN THE IMAGE AND NOT LEFT TO --syncdeps
#     makepkg would install every one of them by itself, and for the
#     three recipes above that is what happens. Hyprland's set is
#     different in size and in kind: it is around forty packages and a
#     good part of a gigabyte, the container is --rm and therefore new on
#     every run, and the pin points at archive.archlinux.org rather than
#     at a mirror. Downloading it again for every build is minutes per
#     run for a set that does not change between them.
#
# WHY THE LIST LOOKS LIKE zepos-hyprland's depends
#     Because it is, near enough - a compositor's build dependencies are
#     its runtime dependencies plus a toolchain, since everything it
#     links against is a library whose headers ship in the same Arch
#     package. The recipe stays the authority: it declares what the
#     PACKAGE needs, and this only decides what is already unpacked when
#     makepkg looks.
RUN pacman -S --needed --noconfirm \
        cmake \
        ninja \
        cpio \
        aquamarine \
        glaze \
        glslang \
        hyprcursor \
        hyprgraphics \
        hyprland-protocols \
        hyprlang \
        hyprutils \
        hyprwayland-scanner \
        hyprwire \
        lcms2 \
        libdisplay-info \
        libdrm \
        libglvnd \
        libinput \
        libx11 \
        libxcb \
        libxcomposite \
        libxcursor \
        libxfixes \
        libxkbcommon \
        libxrender \
        lua \
        mesa \
        muparser \
        pango \
        cairo \
        pixman \
        re2 \
        systemd-libs \
        tomlplusplus \
        util-linux-libs \
        wayland \
        wayland-protocols \
        xcb-proto \
        xcb-util \
        xcb-util-errors \
        xcb-util-image \
        xcb-util-keysyms \
        xcb-util-renderutil \
        xcb-util-wm \
        xorgproto \
        xorg-xwayland \
    && pacman -Scc --noconfirm

# makepkg refuses to run as root, and it is right to: a PKGBUILD's
# build() is arbitrary code from the internet. The account may call
# pacman without a password because --syncdeps has to install build
# dependencies, and nothing else.
#
# The uid is passed in rather than left to useradd's first free number.
# The build runs with the repository bind-mounted read-write, so every
# file makepkg writes into packaging/ - the source tarball, src/, pkg/ -
# arrives on the host owned by whatever uid wrote it. Matching the
# developer's uid is the difference between artefacts they can delete and
# artefacts that need root to clean up.
ARG BUILDER_UID=1000
ARG BUILDER_GID=1000
RUN groupadd --gid "$BUILDER_GID" builder \
    && useradd --uid "$BUILDER_UID" --gid "$BUILDER_GID" \
        --create-home --shell /bin/bash builder \
    && printf 'builder ALL=(ALL) NOPASSWD: /usr/bin/pacman\n' > /etc/sudoers.d/builder \
    && chmod 0440 /etc/sudoers.d/builder

# Two settings makepkg would otherwise take from a workstation's taste.
#
# !debug because Arch's default OPTIONS builds a second -debug package
# beside every package that contains an ELF binary. ZepOS has nowhere to
# put a debug repository and no user who could use one; without this,
# half the files in packaging/out/ would be detached debug symbols.
#
# PACKAGER because the field is empty otherwise, and `pacman -Qi` on a
# ZepOS machine would then not say where its packages came from. The
# address is the project's own, and it became so on 17.08.2026: it named
# a private GitHub account before, so `pacman -Qi` on every installed
# machine attributed the package to one person by handle.
RUN printf '%s\n' \
        'PACKAGER="ZeptronIT <https://github.com/ZeptronIT/ZepOS>"' \
        'OPTIONS+=(!debug)' \
        >> /etc/makepkg.conf

# What built the packages, recorded inside the thing that built them.
# packaging/build.sh copies this next to the repository, for the same
# reason iso/build.sh does it for the ISO: a build that behaves
# differently from a previous one has to be comparable against something.
RUN pacman -Q > /usr/share/zepos-pkgbuild-toolchain.txt
