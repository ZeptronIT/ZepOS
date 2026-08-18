#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Regenerates the binary parts of the boot menu's ZeptronIT identity.
#
#     ./iso/make-boot-theme.sh
#
# WHAT IT WRITES, AND WHY THOSE FILES ARE COMMITTED
#     iso/profile-release/grub/fonts/*.pf2
#     iso/profile-release/grub/themes/zepos/background.png
#     iso/profile-release/grub/themes/zepos/select_*.png
#     iso/profile-release/syslinux/splash.png
#
#     None of them is a build artefact. A GRUB theme whose font or whose
#     background is missing at boot does not fail loudly - GRUB drops
#     back to the text console and says nothing - so the assets have to
#     be present with the same certainty as grub.cfg itself. Generating
#     them during iso/build.sh would put the whole identity behind a
#     package the build container happens to have on the day, and would
#     leave tests/iso/test_boot_theme.py with nothing to check the
#     configuration against.
#
#     So they live in the tree and this script is the record of how they
#     were made. It is not run by the build.
#
# WHY EVERYTHING HAPPENS IN A CONTAINER
#     grub-mkfont, librsvg and ImageMagick would otherwise be three more
#     things the development machine has to have at the right versions,
#     and the point of a committed asset is that it does not change when
#     somebody's laptop does. Same image the ISO is built with, plus the
#     fonts and the two image libraries; the versions that produced the
#     files in the tree are printed at the end of a run.
#
# WHY ROBOTO
#     src/brand.py: FONT_TEXT is Roboto, and a boot menu is prose. Fira
#     Code is the other brand family and belongs to things aligned like
#     code, which two menu entries are not.
#
#     The range is cut down to Latin-1 plus the punctuation German
#     actually uses. A full Roboto at three sizes is most of a megabyte
#     of glyphs nothing in a boot menu will ever ask for, and every one
#     of them would be carried by every copy of the medium.
set -euo pipefail

readonly REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly PROFILE="$REPO/iso/profile-release"
readonly THEME="$PROFILE/grub/themes/zepos"
readonly FONTS="$PROFILE/grub/fonts"
readonly IMAGE="zepos-isobuild"

command -v docker >/dev/null || { echo "docker is not installed" >&2; exit 1; }

# sudo -n, never plain sudo: this machine locks the account on a failed
# password prompt. Same rule as iso/build.sh.
docker() { command sudo -n docker "$@"; }

docker image inspect "$IMAGE" >/dev/null 2>&1 \
    || docker build --network host -t "$IMAGE" -f "$REPO/iso/Dockerfile" "$REPO/iso"

install -d "$THEME" "$FONTS"

docker run --rm --network host \
    -v "$REPO/src/branding:/brand:ro" \
    -v "$THEME:/theme" \
    -v "$FONTS:/fonts" \
    -v "$PROFILE/syslinux:/syslinux" \
    "$IMAGE" bash -euo pipefail -c '
    # -Syu and not -Sy. The build image is pinned to the day it was made
    # and these five packages come from today: installing them into an
    # older root is a partial upgrade, and the first one measured was
    # "magick: /usr/lib/libm.so.6: version GLIBC_2.44 not found" - a
    # tool that will not start, for a reason that has nothing to do with
    # what it was asked to do. Nothing about the ISO depends on this
    # containers own versions; only these files come out of it, and they
    # are read back and checked.
    #
    # pacman-key --init first, and for the reason iso/build.sh already
    # writes down: the archlinux image ships a populated keyring without
    # a local signing key, so archlinux-keyrings own post-install
    # scriptlet fails with "There is no secret key available to sign
    # with" and pacman reports "error: command failed to execute
    # correctly". An error in the log of a run that worked is a thing
    # somebody has to be told to ignore, and next time they will ignore
    # the real one.
    pacman-key --init >/dev/null 2>&1
    pacman -Syu --noconfirm --needed ttf-roboto freetype2 imagemagick librsvg >/dev/null

    # ----------------------------------------------------------------
    # The fonts
    # ----------------------------------------------------------------
    # -b on Roboto-Medium rather than a second family: grub-mkfont names
    # a font from the TTF face, and the shipped Roboto statics all report
    # family "Roboto" style "Regular" - so Roboto-Medium came out as
    # "Roboto Regular 24", the same name as the body font, and GRUB
    # identifies fonts BY NAME. Two fonts with one name is one font.
    # --bold sets the weight, which puts "Roboto Bold 24" in the PF2s
    # name field, and theme.txt asks for it under that name.
    range="0x20-0x7e,0xa0-0xff,0x2013-0x2014,0x2018-0x201e,0x20ac-0x20ac"
    grub-mkfont -r "$range" -s 16 -o /fonts/roboto-16.pf2      /usr/share/fonts/TTF/Roboto-Regular.ttf
    grub-mkfont -r "$range" -s 24 -o /fonts/roboto-24.pf2      /usr/share/fonts/TTF/Roboto-Regular.ttf
    grub-mkfont -r "$range" -s 24 -o /fonts/roboto-bold-24.pf2 -b /usr/share/fonts/TTF/Roboto-Medium.ttf

    # ----------------------------------------------------------------
    # The selected entry
    # ----------------------------------------------------------------
    # GRUBs nine-slice box: the four corners keep their size, the four
    # edges stretch along one axis and the centre stretches along both.
    # All nine are the same solid brand yellow here, which makes the box
    # a plain filled rectangle a little larger than the text row - the
    # ten pixels are the padding.
    #
    # A filled block rather than a colour change on the text, because
    # colour alone is one channel: the selected entry has to be obvious
    # to somebody who is not looking for it, on a panel that may be
    # washed out, in the four seconds before the timeout runs down.
    for slice in c n s e w ne nw se sw; do
        magick -size 10x10 "xc:#FFCB00" -alpha off -depth 8 \
            -define png:color-type=2 -strip "/theme/select_${slice}.png"
    done

    # ----------------------------------------------------------------
    # The two backgrounds
    # ----------------------------------------------------------------
    work=$(mktemp -d)

    # The wordmark, trimmed to its own ink rather than to the SVGs
    # artboard, so that "centred" means the mark is centred and not the
    # empty box around it.
    rsvg-convert -w 1400 -h 800 /brand/zepos-logo.svg -o "$work/logo.png"
    magick "$work/logo.png" -trim +repage -resize 600x "$work/logo-trim.png"

    # The constellation texture, taken from the band of the shipped
    # wallpaper that carries no wordmark - the middle of that image is
    # the ZeptronIT mark at full size, and a second copy of it behind
    # the menu is a background competing with its own foreground.
    #
    # That one band then covers the WHOLE frame by being mirrored onto
    # itself: a 330-row strip and its own reflection make a 660-row tile
    # whose first and last rows are the same, so it repeats with nothing
    # to see at the join. Every junction is a mirror and therefore
    # continuous, and the period is 660 rather than 330 - 1.6 repeats
    # over 1080, too few to read as a pattern.
    magick /brand/zepos-wallpaper.png -crop 1920x330+0+0 +repage "$work/band.png"
    magick "$work/band.png" \( "$work/band.png" -flip \) -append "$work/tile.png"

    # WHY 12%, AND WHY THE TEXTURE SITS ON TOP OF THE GRADIENT
    #     The texture used to be confined to the top 30% and the bottom
    #     12% of the frame, leaving the middle as flat petrol. That is
    #     what made the contrast figures exact - text was measured
    #     against #0D3D47 and nothing behind it was brighter - and it is
    #     also what left a hard horizontal edge where the band stopped.
    #
    #     Covering the whole frame retires that argument, so something
    #     had to replace it. 12% is not a taste: it is the largest
    #     opacity at which EVERY colour the two menus draw still clears
    #     4.5:1 against the brightest pixel of the finished picture,
    #     measured across the band both loaders draw in.
    #
    #       12%   entry 8.86   help 5.88   yellow 6.95   disabled 4.58
    #       14%   entry 8.47   help 5.62   yellow 6.65   disabled 4.38
    #
    #     The disabled colour decides it. WCAG 1.4.3 exempts inactive
    #     components and this menu has no disabled entry today, so 14%
    #     would have been defensible - but an exemption that has to be
    #     explained is worth less than two percent of opacity.
    #
    #     The texture goes ON TOP of the darkening gradient, not under
    #     it. Underneath, the gradient washed it out towards the foot of
    #     the frame and the lower third came out empty again: covering
    #     the whole background and then hiding half of it.
    #
    #     tests/iso/test_boot_theme.py measures the finished file rather
    #     than trusting this comment, so changing either decision moves
    #     the assertions with it.
    compose() {         # compose <width> <height> <destination>
        local W=$1 H=$2 dest=$3
        local logo_w logo_y word_pt word_y rule_w rule_x rule_y rule_h

        # From the HEIGHT, not the width. The GRUB theme scales this
        # image with "crop", which preserves the aspect ratio and takes
        # the overflow off the left and right - so height is the axis
        # that maps one to one onto every screen the menu comes up on,
        # and a logo sized off the width would be a different size on a
        # 4:3 panel than on a 16:9 one.
        logo_w=$(( H * 268 / 1000 ))
        logo_y=$(( H * 6 / 100 ))
        word_pt=$(( H * 65 / 1000 ))
        word_y=$(( H * 235 / 1000 ))
        rule_w=$(( W * 62 / 100 ))
        rule_x=$(( (W - rule_w) / 2 ))
        rule_y=$(( H * 36 / 100 ))
        rule_h=$(( H > 700 ? 3 : 2 ))

        # The rule is one unbroken line in the light petrol, and it used
        # to open with a short yellow segment. That segment was decoration
        # in the colour this brand now reserves for one job: yellow is
        # the ACTIVE thing - the selected entry here, the filled part of
        # the countdown below, the progress in the installer header. A
        # yellow tick that never means anything is the colour saying two
        # things at once, and the tick is the one of the two that carries
        # no information.
        magick -size "${W}x${H}" "xc:#0D3D47" \
            \( -size "${W}x${H}" gradient:"none-#092A31" \) \
            -gravity center -composite \
            \( "$work/tile.png" -write mpr:tile +delete \
               -size "${W}x${H}" tile:mpr:tile \
               -alpha set -channel A -evaluate multiply 0.12 +channel \) \
            -gravity north -composite \
            \( "$work/logo-trim.png" -resize "${logo_w}x" \) \
            -gravity north -geometry "+0+${logo_y}" -composite \
            -gravity north -font /usr/share/fonts/TTF/Roboto-Light.ttf \
            -pointsize "$word_pt" -fill "#DCEEF4" -kerning "$(( word_pt / 6 ))" \
            -annotate "+$(( word_pt / 6 ))+${word_y}" "ZepOS" \
            -gravity northwest \
            -fill "#2F728A" -draw "rectangle ${rule_x},${rule_y} $(( rule_x + rule_w )),$(( rule_y + rule_h ))" \
            -alpha off -depth 8 -define png:color-type=2 -strip "$dest"
    }

    # 1920x1080 for GRUB, which scales it; 800x600 for syslinux, which
    # does not. See iso/profile-release/syslinux/syslinux.cfg for why the
    # BIOS path is pinned to one mode and one image size.
    compose 1920 1080 /theme/background.png
    compose  800  600 /syslinux/splash.png

    rm -rf "$work"
    echo
    echo "built with:"
    pacman -Q grub freetype2 ttf-roboto imagemagick librsvg
    chown -R '"$(id -u):$(id -g)"' /theme /fonts /syslinux
'

echo
echo "wrote:"
find "$THEME" "$FONTS" "$PROFILE/syslinux/splash.png" -type f -printf '  %-64p %s bytes\n' | sort
