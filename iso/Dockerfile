# The container that builds the smoke ISO.
#
# mkarchiso needs root and is not installed on the development machine,
# so the build runs in a container - spec §10 already decided that for
# the package build, and there is no reason for the ISO build to make a
# second decision.
#
# Two things are pinned in two different places, and confusing them costs
# an afternoon:
#
#   * what goes INTO the image is pinned by iso/profile/pacman.conf,
#     which names an Arch Linux Archive snapshot (spec §8.7).
#   * what BUILDS the image is pinned here. It cannot come from the same
#     snapshot: archiso is the tool, and a tool from an archive that no
#     longer matches the host kernel's loop/erofs support fails in ways
#     that have nothing to do with ZepOS.
#
# So this layer takes current packages and iso/build.sh records their
# exact versions next to the ISO. A build that behaves differently from
# a previous one can then be compared against something.
FROM archlinux:latest

# --network host is mandatory for every container on this machine: the
# IPsec tunnel routes all three RFC1918 ranges, the Docker bridge sits
# inside 10.0.0.0/8, and container traffic disappears into the tunnel.
# Spec §10.1 measured it. It is passed on the command line by
# iso/build.sh, not here, because a Dockerfile cannot set it.
RUN pacman -Sy --noconfirm --needed \
        archiso \
        grub \
        mtools \
        dosfstools \
        libisoburn \
        squashfs-tools \
        erofs-utils \
        syslinux \
    && pacman -Scc --noconfirm

# Recorded into the ISO's manifest by iso/build.sh, so that the tooling
# behind a given image is known and not merely assumed.
RUN pacman -Q >/usr/share/zepos-build-toolchain.txt
