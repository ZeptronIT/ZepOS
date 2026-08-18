# SPDX-License-Identifier: GPL-3.0-or-later
"""The installer's palette, and the link that keeps it one palette.

installer/gui/branding.py repeats ZeptronIT's six brand values because it
cannot import src/brand.py: they are two packages, and the direction that
would help is the forbidden one. Spec §4.2 keeps zepos-installer, -gui
and -tui OFF the installed system while zepos-config IS the installed
system, so a dependency from the installer onto zepos-config would put a
desktop's worth of templates on the medium and the installer on every
machine it installs.

A copy nobody checks is a copy that drifts, and this file is the check.
It reads both modules and fails if they disagree - which is the whole
reason the repetition is acceptable at all.

Nothing here imports gi. installer/gui/app.py needs GTK4 and libadwaita
and would not import on a machine without them; branding.py is a
stylesheet and two paths, so it imports anywhere.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from installer.gui import branding

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"


@pytest.fixture
def desktop_brand(monkeypatch):
    """src/brand.py, imported the way the generator imports it."""
    monkeypatch.syspath_prepend(str(SRC))
    import brand as module
    return module


def _channel(value: int) -> float:
    c = value / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(colour: str) -> float:
    digits = colour.lstrip("#")
    r, g, b = (int(digits[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def ratio(foreground: str, background: str) -> float:
    a, b = _luminance(foreground), _luminance(background)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


AA_TEXT = 4.5


def assert_readable(foreground: str, background: str, what: str) -> None:
    measured = ratio(foreground, background)
    assert measured >= AA_TEXT, (
        f"{what}: {foreground} on {background} is {measured:.2f}:1, under "
        f"WCAG AA's {AA_TEXT}:1. This is the screen a person has to get "
        f"through in order to install anything.")


def test_the_installer_and_the_desktop_agree_on_the_brand(desktop_brand):
    """The link the import cannot be."""
    for name in ("PETROL", "CYAN", "YELLOW", "SHADE_1", "SHADE_2", "SHADE_3"):
        assert getattr(branding, name) == getattr(desktop_brand, name), (
            f"{name} differs between installer/gui/branding.py and "
            f"src/brand.py - the medium and the system it installs would "
            f"be two different products")


def test_the_derived_values_agree_too(desktop_brand):
    """Not only the six. A derivation repeated with different arithmetic
    is the same drift one step later."""
    for name in ("INK", "TEXT", "TEXT_DIM", "CYAN_TEXT", "RED"):
        assert getattr(branding, name) == getattr(desktop_brand, name), (
            f"{name} differs between the installer and the desktop")
    assert branding.FONT_TEXT == desktop_brand.FONT_TEXT
    assert branding.FONT_CODE == desktop_brand.FONT_CODE


def test_the_button_the_whole_form_is_driven_from_can_be_read():
    """accent_bg_color with accent_fg_color on it.

    libadwaita's own answer would be white on the accent, and white on
    the brand cyan is 3.43:1 - a "Weiter" whose label cannot be read, on
    the one control every page of the installer is advanced with.
    """
    assert_readable(branding.INK, branding.CYAN, "the Weiter button")
    assert ratio("#FFFFFF", branding.CYAN) < AA_TEXT, (
        "white on the brand cyan now passes, which would make the ink "
        "label unnecessary - check before changing it")


def test_the_accent_used_for_text_is_not_the_one_used_for_fill():
    """Same brand colour, two jobs. On the window background #0096C0 is
    3.45:1 and fails; accent_color is where links and focus rings are
    drawn, so it is the lightened one."""
    assert_readable(branding.CYAN_TEXT, branding.PETROL, "a link or focus ring")
    assert ratio(branding.CYAN, branding.PETROL) < AA_TEXT


def test_every_pair_the_stylesheet_defines_is_readable():
    """The named pairs libadwaita draws text with, taken out of the CSS
    itself rather than repeated here - so a value edited in the
    stylesheet and not here cannot pass this."""
    defined = dict(re.findall(r"@define-color (\w+) (#[0-9A-Fa-f]{6});",
                              branding.CSS))
    pairs = [
        ("window_fg_color", "window_bg_color"),
        ("view_fg_color", "view_bg_color"),
        ("headerbar_fg_color", "headerbar_bg_color"),
        ("popover_fg_color", "popover_bg_color"),
        ("card_fg_color", "card_bg_color"),
        ("dialog_fg_color", "dialog_bg_color"),
        ("sidebar_fg_color", "sidebar_bg_color"),
        ("accent_fg_color", "accent_bg_color"),
        ("destructive_fg_color", "destructive_bg_color"),
    ]
    for foreground, background in pairs:
        assert foreground in defined and background in defined, (
            f"{foreground}/{background} is no longer defined; libadwaita "
            f"falls back to its own colour and the pair goes unchecked")
        assert_readable(defined[foreground], defined[background],
                        f"{foreground} on {background}")


def test_the_status_colours_are_readable_on_both_surfaces():
    """error_color and warning_color are drawn as TEXT, on the window
    background and inside a view."""
    defined = dict(re.findall(r"@define-color (\w+) (#[0-9A-Fa-f]{6});",
                              branding.CSS))
    for name in ("success_color", "warning_color", "error_color", "accent_color"):
        for surface in (branding.PETROL, branding.INK):
            assert_readable(defined[name], surface, f"{name} on {surface}")


def test_the_stylesheet_names_both_brand_families():
    assert f'"{branding.FONT_TEXT}"' in branding.CSS
    assert f'"{branding.FONT_CODE}"' in branding.CSS


def test_the_logo_is_installed_by_the_package_that_needs_it():
    """/usr/share/zepos-installer, not /usr/share/zepos: the installer
    must not depend on zepos-config. And the -gui package, not the core
    one - the text surface has no use for an SVG."""
    assert str(branding.LOGO).startswith("/usr/share/zepos-installer/")

    recipe = (REPO / "packaging/zepos-installer/PKGBUILD").read_text(
        encoding="utf-8")
    gui = recipe[recipe.index("package_zepos-installer-gui()"):]
    gui = gui[:gui.index("package_zepos-installer-tui()")]
    assert str(branding.LOGO) in gui, (
        "zepos-installer-gui does not install the logo at the path "
        "installer/gui/branding.py looks for it")
    # Comments excluded: the recipe explains its own layout by comparing
    # itself to zepos-config's, and that paragraph is worth keeping.
    code = "\n".join(line for line in recipe.splitlines()
                     if not line.lstrip().startswith("#"))
    assert "zepos-config" not in code, (
        "the installer has taken a dependency on the installed system")


def test_the_logo_the_package_installs_is_the_one_in_the_tree():
    """packaging/build.sh stages src/branding/ into this recipe's
    tarball, so the logo the installer shows and the wallpaper
    zepos-config ships come from one directory. A copy committed under
    installer/ would be the same picture with two futures."""
    build = (REPO / "packaging/build.sh").read_text(encoding="utf-8")
    assert 'rsync -a "$REPO/src/branding" "$stage"/' in build
    assert (REPO / "src/branding/zepos-logo.svg").is_file()
    assert not list((REPO / "installer").rglob("*.svg")), (
        "there is now a second copy of the logo under installer/")


# --- the wordmark the header actually draws --------------------------------


def _png_size(path) -> tuple[int, int]:
    """Width and height out of a PNG's IHDR.

    Read here rather than through an image library so this test needs
    nothing installed - and so it stays independent of the loader whose
    absence is half the reason the PNG exists at all.
    """
    header = path.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
    return (int.from_bytes(header[16:20], "big"),
            int.from_bytes(header[20:24], "big"))


def _svg_viewbox(path) -> tuple[float, float]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r'viewBox="[\d.]+ [\d.]+ ([\d.]+) ([\d.]+)"', text)
    assert match, f"{path} declares no viewBox"
    return float(match.group(1)), float(match.group(2))


def test_the_wordmark_is_rendered_at_the_height_the_header_asks_for():
    """A committed rendering goes stale silently, so its size is checked
    against the number that decides it.

    installer/gui/app.py draws the wordmark with can_shrink off - the
    picture is exactly the texture's size and nothing negotiates, which
    is the whole reason the PNG exists. So a PNG rendered at some other
    height is not a slightly wrong logo, it is a wrong-sized header.
    """
    mark = REPO / "src/branding/zepos-wordmark.png"
    assert mark.is_file(), (
        "src/branding/zepos-wordmark.png is missing - run "
        "./packaging/make-brand-assets.sh")
    assert _png_size(mark)[1] == branding.MARK_HEIGHT, (
        f"the wordmark is {_png_size(mark)[1]} pixels high and the header "
        f"asks for {branding.MARK_HEIGHT} - run "
        "./packaging/make-brand-assets.sh")


def test_the_wordmark_still_has_the_logos_proportions():
    """The half that notices a REDRAWN logo.

    Comparing sizes catches a wrong -resize; it cannot catch an SVG that
    was redrawn and never re-rendered. The aspect ratio can, as long as
    the redraw changed the shape - which a wordmark gaining or losing a
    word does. It cannot catch a redraw that keeps the proportions
    exactly, and nothing short of rendering the SVG here could; that
    would need librsvg in the test environment, which is the dependency
    the PNG exists to avoid.
    """
    width, height = _png_size(REPO / "src/branding/zepos-wordmark.png")
    svg_width, svg_height = _svg_viewbox(REPO / "src/branding/zepos-logo.svg")

    assert abs(width / height - svg_width / svg_height) < 0.02, (
        f"the wordmark is {width}x{height} ({width / height:.3f}) but "
        f"zepos-logo.svg is {svg_width:g}x{svg_height:g} "
        f"({svg_width / svg_height:.3f}) - the SVG was changed and the "
        "PNG was not re-rendered. Run ./packaging/make-brand-assets.sh")


def test_the_backdrop_is_the_boot_menus_picture_at_the_same_settings():
    """The installer and the boot menu have to look like one screen.

    They are rendered by two scripts - iso/make-boot-theme.sh for the
    menu, packaging/make-brand-assets.sh for the window - because one
    runs in a container and the other does not, and because the menu
    bakes its title block into the picture while the window draws it as
    widgets. Two scripts is two places for the numbers to drift, so the
    numbers are compared here: the band of the wallpaper the texture is
    built from, and the opacity it is laid on at.

    What this cannot see: whether the composition ORDER is still the
    same in both. That is prose in each script, and a difference there
    would show up as one screen looking washed out beside the other.
    """
    menu = (REPO / "iso/make-boot-theme.sh").read_text(encoding="utf-8")
    window = (REPO / "packaging/make-brand-assets.sh").read_text(
        encoding="utf-8")

    assert "1920x330+0+0" in menu, "the boot menu changed which band it uses"
    assert 'BAND_H=330' in window, (
        "the installer builds its texture from a different band of the "
        "wallpaper than the boot menu does")

    assert "-evaluate multiply 0.12" in menu, (
        "the boot menu changed the texture opacity")
    assert "TEXTURE_ALPHA=0.12" in window, (
        "the installer lays the texture on at a different opacity than "
        "the boot menu - the two screens will not match")

    backdrop = REPO / "src/branding/zepos-backdrop.png"
    assert backdrop.is_file(), (
        "src/branding/zepos-backdrop.png is missing - run "
        "./packaging/make-brand-assets.sh")
    assert _png_size(backdrop) == (1920, 1080), (
        f"the backdrop is {_png_size(backdrop)}, not the 1920x1080 the "
        "boot menu renders")


def test_the_wordmark_the_package_installs_is_the_one_in_the_tree():
    recipe = (REPO / "packaging/zepos-installer/PKGBUILD").read_text(
        encoding="utf-8")
    gui = recipe[recipe.index("package_zepos-installer-gui()"):]
    gui = gui[:gui.index("package_zepos-installer-tui()")]
    assert str(branding.WORDMARK) in gui, (
        "zepos-installer-gui does not install the wordmark at the path "
        "installer/gui/branding.py looks for it")
    assert str(branding.BACKDROP) in gui, (
        "zepos-installer-gui does not install the backdrop at the path "
        "installer/gui/branding.py looks for it")
