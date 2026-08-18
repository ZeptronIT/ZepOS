# SPDX-License-Identifier: GPL-3.0-or-later
"""The boot menu's identity, checked without booting anything.

WHY THIS FILE EXISTS
    The boot menu is the first thing anybody sees of ZepOS, and it is the
    one surface in the whole distribution whose failure mode is silence.
    GRUB answers a missing theme file, a missing PF2 font or an
    undecodable background by putting up its plain text menu; syslinux
    answers a splash.png it cannot read by drawing its colours over
    black. Neither writes anything anywhere. There is no log, no exit
    code and no unit that failed - the medium boots, the installer comes
    up, and the brand is gone.

    So the identity has to be checked from two directions, and this file
    is the cheap half of it:

      * that every file the two configurations NAME is in the profile,
        at the path mkarchiso will copy it to, with the internal name the
        configuration asks for. That is what a theme "being in the image"
        actually consists of, and three of those four are not visible in
        a diff of the configuration alone.
      * that every colour pair the two configurations produce clears WCAG
        AA, recomputed from the files rather than trusted from the
        comments beside them.
      * that iso/test-boot.py's frame classifier - the expensive half,
        which boots the medium and measures the screen - separates a
        branded menu from a fallback rather than merely from black.

    The other half is `./iso/test-boot.py --scenario boot-menu`, which
    needs QEMU, an ISO and half a minute, and is the only thing that can
    prove the theme loads on a machine. Neither replaces the other: this
    one cannot boot anything, and that one cannot run in a test suite
    that is forbidden to start processes.

WHY THE TWO LOADERS ARE CHECKED TOGETHER
    Because they are one brand and two mechanisms, and the mechanisms
    share nothing. A change made to one and forgotten in the other is the
    defect this file is most likely to catch, and it is invisible to
    anybody who only ever boots the firmware their own machine has.
"""
from __future__ import annotations

import importlib.util
import re
import struct
import zlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ISO = REPO / "iso"
SRC = REPO / "src"
PROFILE = ISO / "profile-release"
GRUB = PROFILE / "grub"
THEME = GRUB / "themes" / "zepos"
SYSLINUX = PROFILE / "syslinux"

# WCAG 2.1: 4.5:1 for body text (SC 1.4.3), 3:1 for the visual boundary
# of a user interface component (SC 1.4.11).
AA_TEXT = 4.5
AA_COMPONENT = 3.0

# The nine names GRUB builds out of a `*`-style pixmap prefix. All of
# them have to exist: grub_gfxmenu_create_box() loads each slice by name
# and a missing one is a hole in the box, not an error.
BOX_SLICES = ("c", "n", "s", "e", "w", "ne", "nw", "se", "sw")


# --------------------------------------------------------------------
# Reading the things under test
# --------------------------------------------------------------------

@pytest.fixture(scope="module")
def harness():
    """iso/test-boot.py, imported by path.

    Its name has a hyphen in it, so `import` cannot reach it - the same
    reason tests/src/test_placeholders.py loads what it tests this way.
    Module-scoped because the file is 2000 lines and nothing in it has
    state a test could disturb.
    """
    spec = importlib.util.spec_from_file_location("zepos_test_boot",
                                                  ISO / "test-boot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def brand():
    """src/brand.py, the palette everything below is measured against."""
    spec = importlib.util.spec_from_file_location("zepos_brand", SRC / "brand.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(path: Path) -> str:
    assert path.is_file(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


def _code_lines(text: str) -> list[str]:
    """The file without its whole-line comments.

    Stripped everywhere here for the reason tests/iso/test_release_profile
    .py strips them: both configurations explain at length what they do
    and name the very strings being searched for, and a scan that could
    not tell an explanation from a setting would force the explanations
    out. Only WHOLE-line comments go - a `#` inside a line is a colour.
    """
    return [line for line in text.splitlines() if not line.lstrip().startswith("#")]


def theme_file() -> tuple[dict[str, str], list[tuple[str, dict[str, str]]]]:
    """theme.txt as (top-level properties, [(component type, properties)]).

    GRUB's theme syntax is `name: "value"` at the top level and
    `+ type { name = value }` for components. Quotes are optional and
    stripped; percentages and bare numbers come back as the strings they
    are, because what is being checked here is names and colours.
    """
    top: dict[str, str] = {}
    components: list[tuple[str, dict[str, str]]] = []
    current: dict[str, str] | None = None
    for line in _code_lines(_read(THEME / "theme.txt")):
        line = line.strip()
        if not line:
            continue
        if line.startswith("+"):
            kind = line[1:].split("{")[0].strip()
            current = {}
            components.append((kind, current))
            continue
        if line == "}":
            current = None
            continue
        for separator, target in ((":", top), ("=", current)):
            if separator in line and (separator == "=") == (current is not None):
                name, _, value = line.partition(separator)
                target[name.strip()] = value.strip().strip('"')
                break
    return top, components


def component(kind: str, identifier: str | None = None) -> dict[str, str]:
    _, components = theme_file()
    for found, properties in components:
        if found == kind and (identifier is None
                              or properties.get("id") == identifier):
            return properties
    raise AssertionError(f"theme.txt has no {kind} component"
                         + (f" with id {identifier!r}" if identifier else ""))


_MENU_COLOUR = re.compile(
    r"^MENU\s+COLOR\s+(\S+)\s+\S+\s+(#[0-9A-Fa-f]{8})\s+(#[0-9A-Fa-f]{8})")


def syslinux_colours() -> dict[str, tuple[str, str]]:
    """Every MENU COLOR line as element -> (foreground, background), in
    #AARRGGBB."""
    found = {}
    for line in _code_lines(_read(SYSLINUX / "syslinux.cfg")):
        match = _MENU_COLOUR.match(line.strip())
        if match:
            found[match.group(1)] = (match.group(2), match.group(3))
    assert found, "syslinux.cfg sets no MENU COLOR at all"
    return found


def syslinux_directive(name: str) -> str:
    for line in _code_lines(_read(SYSLINUX / "syslinux.cfg")):
        if line.strip().upper().startswith(name.upper() + " "):
            return line.strip()[len(name) + 1:].strip()
    raise AssertionError(f"syslinux.cfg has no {name}")


def pf2_name(path: Path) -> str:
    """The name GRUB will know a font by.

    A PF2 is a magic number followed by four-character sections with
    big-endian lengths. The NAME section is what `item_font` in a theme
    has to match, and it is built by grub-mkfont out of the TTF's family,
    weight and size - which is to say it is NOT derivable from the file
    name, which is exactly why this function exists.
    """
    data = path.read_bytes()
    assert data[:12] == b"FILE\x00\x00\x00\x04PFF2", f"{path} is not a PF2 font"
    offset = 12
    while offset + 8 <= len(data):
        section, length = struct.unpack(">4sI", data[offset:offset + 8])
        offset += 8
        if section == b"DATA":
            break
        if section == b"NAME":
            return data[offset:offset + length].rstrip(b"\0").decode()
        offset += length
    raise AssertionError(f"{path} carries no NAME section")


def png_header(path: Path) -> tuple[int, int, int, int, int]:
    """(width, height, bit depth, colour type, interlace) from the IHDR."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
    width, height = struct.unpack(">II", data[16:24])
    depth, colour_type, _compression, _filter, interlace = data[24:29]
    return width, height, depth, colour_type, interlace


# --------------------------------------------------------------------
# Contrast
# --------------------------------------------------------------------
# The sRGB relative-luminance formula, written out here rather than
# imported from tests/src/test_brand.py. A test module is not a library:
# importing one into another gives pytest two module objects for one file
# and makes this file fail for a reason that lives somewhere else. What
# is duplicated is a published formula with one right answer, and
# test_the_two_files_agree_on_what_a_contrast_ratio_is below checks the
# two implementations against each other so the copy cannot drift.

def _channel(value: int) -> float:
    c = value / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(colour: str) -> float:
    digits = colour.lstrip("#")
    if len(digits) == 8:                       # #AARRGGBB, as syslinux writes it
        digits = digits[2:]
    r, g, b = (int(digits[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def ratio(foreground: str, background: str) -> float:
    a, b = luminance(foreground), luminance(background)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def assert_readable(foreground: str, background: str, what: str,
                    threshold: float = AA_TEXT) -> None:
    measured = ratio(foreground, background)
    assert measured >= threshold, (
        f"{what}: {foreground} on {background} is {measured:.2f}:1, under "
        f"the {threshold}:1 WCAG threshold. A boot menu is read once, "
        f"quickly, often on a panel nobody calibrated.")


def opaque(colour: str) -> bool:
    """Whether a syslinux #AARRGGBB actually paints anything."""
    return colour.lstrip("#")[:2].upper() != "00"


def rgb(colour: str) -> str:
    digits = colour.lstrip("#")
    return "#" + (digits[2:] if len(digits) == 8 else digits)


# --------------------------------------------------------------------
# A synthetic framebuffer, for the classifier's own tests
# --------------------------------------------------------------------

def write_png(path: Path, width: int, height: int,
              paint) -> Path:
    """An 8-bit truecolour PNG, filter 0 on every row.

    The classifier has to be shown a frame it did not produce, or all it
    is being tested against is its own output. paint(x, y) returns the
    pixel.
    """
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(paint(x, y))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + chunk(b"IEND", b""))
    return path


PETROL = (0x0D, 0x3D, 0x47)
YELLOW = (0xFF, 0xCB, 0x00)
TEXTISH = (0xDC, 0xEE, 0xF4)
CONSOLE_GREY = (0xAA, 0xAA, 0xAA)
BLACK = (0, 0, 0)


def _branded(x: int, y: int):
    """A menu: petrol everywhere, a yellow selected bar, a line of text."""
    if 40 <= y < 48 and 20 <= x < 300:          # the selected entry, ~2.6%
        return YELLOW
    if 60 <= y < 64 and 20 <= x < 200:          # an unselected one
        return TEXTISH
    return PETROL


def _text_console(x: int, y: int):
    """GRUB's fallback: black, with grey text and an inverted line."""
    if 20 <= y < 28 and 8 <= x < 300:
        return CONSOLE_GREY
    if 40 <= y < 44 and 8 <= x < 200:
        return CONSOLE_GREY
    return BLACK


def _colours_without_the_picture(x: int, y: int):
    """The splash failed to decode; the colour attributes still work."""
    if 40 <= y < 48 and 20 <= x < 300:
        return YELLOW
    if 60 <= y < 64 and 20 <= x < 200:
        return TEXTISH
    return BLACK


def _picture_without_the_theme(x: int, y: int):
    """The background loaded and nothing was themed over it."""
    if 60 <= y < 64 and 20 <= x < 200:
        return TEXTISH
    return PETROL


# --------------------------------------------------------------------
# Is the theme in the image at all
# --------------------------------------------------------------------

def test_the_uefi_menu_reaches_a_graphical_terminal():
    """`terminal_output console` is a text menu, whatever else is set.

    That is what this file said before it had an identity, and it is what
    it would say again if somebody moved the line back while leaving the
    theme in place - a change that looks like a revert of nothing.
    """
    lines = [line.strip() for line in _code_lines(_read(GRUB / "grub.cfg"))]
    graphical = [i for i, line in enumerate(lines) if "terminal_output gfxterm" in line]
    textual = [i for i, line in enumerate(lines) if "terminal_output console" in line]
    assert graphical, (
        "grub.cfg never switches to gfxterm, so no theme can be drawn "
        "whatever themes/zepos/theme.txt says")
    assert not textual or min(graphical) < min(textual), (
        "grub.cfg reaches `terminal_output console` before it tries "
        "gfxterm; the text console is the FALLBACK for firmware that "
        "gives GRUB no video mode, not the thing it settles for first")
    assert any("set theme=" in line for line in lines), (
        "grub.cfg loads no theme; gfxterm alone is the same text menu on "
        "a graphical terminal")


def test_every_file_the_uefi_configuration_names_is_in_the_profile():
    """The load-bearing half of "the theme is in the image".

    mkarchiso copies a profile's grub/ directory into /boot/grub on the
    ISO, so a path the configuration names as /boot/grub/x is the file
    iso/profile-release/grub/x. Nothing checks that correspondence at
    build time: a name that is wrong produces a menu in text, silently.
    """
    text = _read(GRUB / "grub.cfg") + _read(GRUB / "loopback.cfg")
    named = set(re.findall(r'(?:loadfont|set theme=)\s*"(/boot/grub/[^"]+)"', text))
    assert named, "neither GRUB configuration names a font or a theme"
    for path in sorted(named):
        on_disk = GRUB / path[len("/boot/grub/"):]
        assert on_disk.is_file(), (
            f"the configuration names {path}, which mkarchiso would take "
            f"from {on_disk.relative_to(REPO)} - and that file does not exist")


def test_mkarchiso_would_copy_every_theme_asset():
    """The copy is `${profile}/grub/!(*.cfg)`, recursively.

    Two ways to lose a file to it, and both look reasonable in a diff: a
    `.cfg` extension anywhere under grub/ makes mkarchiso run the file
    through its %PLACEHOLDER% substitution and write it flat into
    /boot/grub instead of copying the directory, and an asset put
    anywhere but grub/ is not copied at all.
    """
    assets = [p for p in GRUB.rglob("*") if p.is_file()]
    assert assets, "the profile's grub/ directory is empty"
    for path in assets:
        relative = path.relative_to(GRUB)
        if len(relative.parts) == 1:
            continue                       # grub.cfg and loopback.cfg live here
        assert path.suffix != ".cfg", (
            f"{relative} is a .cfg below grub/, which mkarchiso would "
            f"substitute and flatten into /boot/grub/{path.name} rather "
            f"than copy to /boot/grub/{relative}")


def test_the_selected_entry_pixmap_is_complete():
    """A nine-slice box needs nine slices.

    GRUB builds the file names from the `*` in the style and loads each
    one; a slice it cannot find is simply not drawn, so a box missing its
    centre is a highlight with a hole in it and no error anywhere.
    """
    style = component("boot_menu")["selected_item_pixmap_style"]
    assert "*" in style, f"{style!r} is not a nine-slice pixmap style"
    for slice_name in BOX_SLICES:
        path = THEME / style.replace("*", slice_name)
        assert path.is_file(), (
            f"the selected entry's box needs {path.name}; "
            f"{style!r} names it and it is not in {THEME.relative_to(REPO)}")


def test_the_theme_asks_only_for_fonts_the_configuration_loads():
    """Fonts are loaded by PATH and used by NAME, and nothing joins the two.

    theme.txt asks for "Roboto Regular 24"; grub.cfg loads
    /boot/grub/fonts/roboto-24.pf2; the name inside that file is what
    decides whether those are the same font. GRUB's answer to a name it
    has never loaded is to fall back to the built-in one - so a renamed
    file, a font generated at a different size, or a loadfont line
    deleted from the configuration all produce a menu in Unifont and no
    complaint.
    """
    text = _read(GRUB / "grub.cfg")
    loaded = {pf2_name(GRUB / path[len("/boot/grub/"):])
              for path in re.findall(r'loadfont\s*"(/boot/grub/[^"]+)"', text)}
    # The one GRUB carries in its own memdisk, which grub.cfg loads
    # through ${prefix} and which is therefore not a file in this tree.
    builtin = {"Unknown Regular 16", "Unifont Regular 16"}

    top, components = theme_file()
    wanted = {value for name, value in top.items() if name.endswith("font")}
    for _kind, properties in components:
        wanted |= {value for name, value in properties.items()
                   if name.endswith("font")}

    for font in sorted(wanted):
        assert font in loaded | builtin, (
            f"theme.txt asks for the font {font!r}. grub.cfg loads "
            f"{sorted(loaded)} and GRUB brings {sorted(builtin)}; a name "
            f"that is in neither is silently replaced by the default font")


def test_the_background_is_a_picture_grubs_own_modules_can_read():
    """PNG, eight bits, no interlacing.

    grub-core/video/readers/png.c has no interlaced path at all - an
    Adam7 image is an error at draw time, which for a desktop-image means
    the theme comes up on the flat desktop-color and the wordmark is
    gone. The module itself is in mkarchiso's grubmodules list; this is
    about what is handed to it.
    """
    name = theme_file()[0]["desktop-image"]
    path = THEME / name
    assert path.is_file(), f"theme.txt names {name}, which is not in {THEME}"
    width, height, depth, colour_type, interlace = png_header(path)
    assert depth == 8, f"{name} is {depth}-bit"
    assert interlace == 0, f"{name} is interlaced, which GRUB cannot read"
    assert colour_type in (2, 6), f"{name} has colour type {colour_type}"
    assert (width, height) == (1920, 1080), (
        f"{name} is {width}x{height}; the theme scales it with "
        f"desktop-image-scale-method, and the composition was drawn at "
        f"16:9 so that a 4:3 crop keeps the wordmark")


def test_the_bios_splash_is_exactly_the_mode_it_is_shown_in():
    """syslinux does not scale MENU BACKGROUND.

    The image is drawn at its own size, so a splash that does not match
    MENU RESOLUTION is a picture in the corner of a screen with the rest
    of it a colour. The two numbers are in two different files and
    nothing but this compares them.
    """
    name = syslinux_directive("MENU BACKGROUND")
    path = SYSLINUX / name
    assert path.is_file(), (
        f"syslinux.cfg names {name}; mkarchiso only copies a file called "
        f"splash.png out of a profile's syslinux/ directory, and there is "
        f"no {path.relative_to(REPO)}")
    assert name == "splash.png", (
        f"mkarchiso copies {SYSLINUX.name}/splash.png and nothing else out "
        f"of this directory, so a background called {name} would not reach "
        f"the image at all")

    declared = syslinux_directive("MENU RESOLUTION").split()
    width, height, depth, colour_type, interlace = png_header(path)
    assert [str(width), str(height)] == declared, (
        f"MENU RESOLUTION is {' '.join(declared)} and splash.png is "
        f"{width}x{height}")
    assert (depth, interlace, colour_type) == (8, 0, 2), (
        f"splash.png is depth {depth}, interlace {interlace}, colour type "
        f"{colour_type}; syslinux's own decoder wants plain 8-bit truecolour")


def test_the_bios_menu_uses_the_module_that_can_draw_a_picture():
    """menu.c32 ignores MENU BACKGROUND entirely.

    It is the text-mode menu: it colours characters and knows nothing of
    an image. Swapping it back in leaves every colour line in this file
    working and the splash simply absent - which is the same silent
    half-failure the GRUB side has.
    """
    lines = [line.strip() for line in _code_lines(_read(SYSLINUX / "syslinux.cfg"))]
    assert any(line.upper().startswith("UI VESAMENU.C32") for line in lines), (
        "syslinux.cfg does not select vesamenu.c32, so MENU BACKGROUND "
        "is read and ignored")


# --------------------------------------------------------------------
# Readability
# --------------------------------------------------------------------

def test_the_uefi_menu_reads_against_the_petrol_it_is_drawn_on(brand):
    """Every text colour the GRUB theme sets, against the brand petrol.

    The petrol is no longer the worst case - the texture covers the
    whole frame now, so the pixel behind a given letter can be lighter -
    and test_every_colour_still_reads_against_the_brightest_pixel_behind_it
    is the one that measures what is actually there.

    This one stays because it asks a different question: whether the
    PALETTE is sound, independently of any picture. A colour that fails
    here is wrong even on a plain background, and it would keep failing
    if the texture were ever removed. Read together, one checks the
    design and the other checks the file.
    """
    menu = component("boot_menu")
    assert_readable(menu["item_color"], brand.PETROL, "an unselected entry")

    countdown = component("label", "__timeout__")
    assert_readable(countdown["color"], brand.PETROL, "the countdown")

    for _kind, properties in theme_file()[1]:
        if _kind == "label" and "id" not in properties:
            assert_readable(properties["color"], brand.PETROL,
                            f"the label {properties['text'][:32]!r}")


def test_the_selected_entry_reads_against_its_own_block(harness, brand):
    """The one place two brand colours meet at full strength.

    The colour is taken out of the pixmap rather than out of a comment:
    the block behind the selected entry is whatever select_c.png is, and
    a regenerated theme with a different yellow would leave every comment
    in the file still saying 7.77:1.
    """
    menu = component("boot_menu")
    centre = THEME / menu["selected_item_pixmap_style"].replace("*", "c")
    _width, _height, depth, colour_type, _interlace = png_header(centre)
    assert (depth, colour_type) == (8, 2), f"{centre.name} is not 8-bit RGB"
    _w, _h, channels, pixels = harness.read_png(centre)
    block = "#%02X%02X%02X" % (pixels[0], pixels[1], pixels[2])
    assert block == brand.YELLOW, (
        f"the selected entry's block is {block}, not the brand yellow "
        f"{brand.YELLOW}")
    assert_readable(menu["selected_item_color"], block, "the SELECTED entry")


def test_the_selected_entry_is_more_than_a_change_of_colour(brand):
    """Colour is one channel and a boot menu is read by somebody who is
    not looking for the highlight.

    So the selection also changes the shape - a filled block where there
    was none - and the weight of the type. Either one alone would be a
    defensible design; the reason both are asserted is that the block is
    what carries it on a washed-out panel and the weight is what carries
    it for somebody who cannot tell the two hues apart.
    """
    menu = component("boot_menu")
    assert menu.get("selected_item_pixmap_style"), (
        "the selected entry has no block behind it, so the only thing "
        "separating it from the others is its colour")
    assert menu["selected_item_font"] != menu["item_font"], (
        "the selected entry is set in the same font as the others")


def test_the_countdown_is_visible_without_being_the_loudest_thing(brand):
    """Two requirements that pull against each other, both checked.

    Visible: the bar's own outline has to clear 3:1 against the
    background, or the component has no edge until it starts emptying
    (WCAG 1.4.11). Not the loudest: the countdown is the one element that
    changes every second, and it is deliberately the dim text colour
    rather than the yellow the selected entry uses - which would put the
    two strongest things on the screen in competition.
    """
    bar = component("progress_bar", "__timeout__")
    assert_readable(bar["border_color"], brand.PETROL,
                    "the countdown bar's outline", AA_COMPONENT)
    assert_readable(bar["fg_color"], brand.PETROL,
                    "the countdown bar's fill", AA_COMPONENT)

    countdown = component("label", "__timeout__")
    assert countdown["color"] != brand.YELLOW, (
        "the countdown is in the same yellow as the selected entry, which "
        "makes the thing that changes every second as loud as the thing "
        "the user is choosing")

    # And the reason the text is not inside the bar. #DCEEF4 on #0096C0
    # is 2.87:1, and GRUB centres a progress bar's own text over its
    # fill - so show_text would put the one line that moves under the
    # threshold for most of the countdown.
    assert bar.get("show_text", "false").lower() == "false", (
        "the countdown bar draws its own text, which GRUB centres over "
        "the cyan fill; no text colour clears 4.5:1 on both the fill and "
        "the trough")


def test_the_bios_menu_reads_against_the_splash_it_is_drawn_on(brand):
    """Every MENU COLOR line, recomputed.

    A transparent background is not a colour: it is what lets the splash
    show through, so the effective background for those elements is the
    petrol of the picture. The two that are opaque - the selected entry
    and its hotkey - are measured against their own.
    """
    # Which of syslinux's elements are read as words and which are shapes.
    # `border` is transparent on transparent and draws nothing.
    text_elements = {"screen", "title", "unsel", "hotkey", "sel", "hotsel",
                     "disabled", "tabmsg", "help", "timeout_msg", "timeout",
                     "cmdmark", "cmdline", "msg07"}
    shape_elements = {"scrollbar"}

    colours = syslinux_colours()
    missing = (text_elements | shape_elements) - colours.keys()
    assert not missing, f"syslinux.cfg sets no colour for {sorted(missing)}"

    for element, (foreground, background) in sorted(colours.items()):
        if not opaque(foreground):
            continue                       # draws nothing at all
        behind = rgb(background) if opaque(background) else brand.PETROL
        if element in shape_elements:
            assert_readable(rgb(foreground), behind, f"MENU COLOR {element}",
                            AA_COMPONENT)
        elif element in text_elements:
            assert_readable(rgb(foreground), behind, f"MENU COLOR {element}")


def brightest_behind_the_text(harness, path) -> tuple[float, tuple[int, int]]:
    """The lightest pixel in the band both loaders draw their text in.

    38% to 92% of the height, which is where every entry, the help line
    and the countdown land. Sampled every second row and every fourth
    column: the texture is a field of small dots and thin lines, and a
    denser sweep of the same picture moved the answer by less than a
    thousandth while taking four times as long.
    """
    width, height, channels, pixels = harness.read_png(path)
    stride = width * channels
    worst = 0.0
    where = (0, 0)
    for y in range(int(height * 0.38), int(height * 0.92), 2):
        row = y * stride
        for x in range(0, width, 4):
            i = row + x * channels
            value = luminance("#%02X%02X%02X"
                              % (pixels[i], pixels[i + 1], pixels[i + 2]))
            if value > worst:
                worst, where = value, (x, y)
    return worst, where


def test_every_colour_still_reads_against_the_brightest_pixel_behind_it(
        harness, brand):
    """The measurement the other ratios in this file rest on.

    IT USED TO SAY SOMETHING WEAKER, and the difference matters. The
    picture had a texture at the top and the bottom and flat petrol in
    between, so this test asserted that nothing in the text band went
    lighter than #0D3D47 - which let every other test here compare
    against the petrol and call the result a lower bound.

    The texture now covers the whole frame, at an opacity chosen so
    that the guarantee survives, so the proxy is gone and the thing it
    stood for is checked directly: every colour either menu draws over
    the picture, against the lightest pixel that picture actually has
    where text goes. That is strictly stronger - the old form could not
    have caught a texture that stayed under the petrol while a text
    colour was changed to something too dark.

    The disabled entry is in here too. It is the tightest pair by some
    way, and WCAG 1.4.3 would have exempted it as an inactive
    component; iso/make-boot-theme.sh picked 12% rather than 14% so
    that no exemption has to be claimed.
    """
    for path in (THEME / "background.png", SYSLINUX / "splash.png"):
        worst, where = brightest_behind_the_text(harness, path)
        background = "brightest pixel of %s at %s" % (path.name, where)

        assert worst >= luminance(brand.PETROL), (
            f"{path.name} is DARKER than the brand petrol everywhere text "
            f"goes ({worst:.5f} < {luminance(brand.PETROL):.5f}). That is "
            "not a contrast problem, it is a sign the texture did not "
            "reach the middle of the frame at all")

        menu = component("boot_menu")
        assert_readable_against(menu["item_color"], worst,
                                "an unselected entry", background)
        if "disabled_item_color" in menu:
            assert_readable_against(menu["disabled_item_color"], worst,
                                    "a disabled entry", background)

        countdown = component("label", "__timeout__")
        assert_readable_against(countdown["color"], worst, "the countdown",
                                background)

        for kind, properties in theme_file()[1]:
            if kind == "label" and "id" not in properties:
                assert_readable_against(
                    properties["color"], worst,
                    f"the label {properties['text'][:32]!r}", background)


def assert_readable_against(foreground: str, background_luminance: float,
                            what: str, where: str) -> None:
    """4.5:1 against a measured luminance rather than a named colour."""
    a = luminance(foreground)
    b = background_luminance
    hi, lo = max(a, b), min(a, b)
    contrast = (hi + 0.05) / (lo + 0.05)
    assert contrast >= 4.5, (
        f"{what}: {foreground} on the {where} (luminance "
        f"{background_luminance:.5f}) is {contrast:.2f}:1, under WCAG AA. "
        "A boot menu is read once, quickly, often on a panel nobody "
        "calibrated")


def test_the_two_files_agree_on_what_a_contrast_ratio_is():
    """This file's copy of the sRGB formula against the one in
    tests/src/test_brand.py, on the pair both of them care about.

    The copy exists because a test module is not a library. It is checked
    here rather than trusted, so the two cannot drift into disagreeing
    about whether something is readable.
    """
    spec = importlib.util.spec_from_file_location(
        "zepos_brand_contrast", REPO / "tests/src/test_brand.py")
    other = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(other)
    for foreground, background in (("#DCEEF4", "#0D3D47"),
                                   ("#0D3D47", "#FFCB00"),
                                   ("#A9C6CF", "#0D3D47"),
                                   ("#0096C0", "#0D3D47")):
        assert abs(ratio(foreground, background)
                   - other.ratio(foreground, background)) < 1e-9


# --------------------------------------------------------------------
# One brand, two mechanisms
# --------------------------------------------------------------------

def test_both_firmwares_offer_the_same_two_things():
    """The entries are content, not appearance, and content may not diverge.

    Measured, the first time the two menus were put side by side: GRUB
    offered "ZepOS installieren" and "Rechner ausschalten" and syslinux
    offered the first alone. Nobody had seen it because no machine shows
    both menus.
    """
    grub_entries = re.findall(r'^menuentry\s+"([^"]+)"',
                              _read(GRUB / "grub.cfg"), re.MULTILINE)
    # In the order syslinux reads them, INCLUDE spliced in where it
    # stands - which is the order the entries appear in the menu and
    # therefore part of what "the same two things" means.
    assembled: list[str] = []
    for line in _code_lines(_read(SYSLINUX / "syslinux.cfg")):
        if line.strip().upper().startswith("INCLUDE "):
            assembled += _code_lines(_read(SYSLINUX / line.split()[1]))
        else:
            assembled.append(line)
    syslinux_entries = [line.strip()[len("MENU LABEL"):].strip()
                        for line in assembled
                        if line.strip().startswith("MENU LABEL")]

    assert len(grub_entries) == len(syslinux_entries), (
        f"the UEFI menu offers {grub_entries} and the BIOS menu offers "
        f"{syslinux_entries}; a person sees one firmware or the other and "
        f"has no way of knowing what the other one would have let them do")

    # The firmware's own name is the one word allowed to differ, because
    # it is the one thing that IS different.
    def generic(label: str) -> str:
        return label.replace("UEFI", "").replace("BIOS", "").replace("%ARCH%", "")

    assert ([generic(e) for e in grub_entries]
            == [generic(e) for e in syslinux_entries])


def test_both_menus_carry_the_same_brand(brand):
    """The colours are the point of contact between two mechanisms that
    have nothing else in common.

    GRUB names a theme file and syslinux names #AARRGGBB attributes;
    neither can express the other, so the only thing that can be checked
    across them is the palette. All four values below come out of
    src/brand.py, which is what makes the two menus one brand rather than
    two designs that happen to be blue.
    """
    menu = component("boot_menu")
    colours = syslinux_colours()

    assert rgb(colours["sel"][1]) == brand.YELLOW, (
        "the BIOS menu highlights the selected entry in "
        f"{rgb(colours['sel'][1])}, not the brand yellow")
    assert rgb(colours["sel"][0]) == menu["selected_item_color"], (
        "the two menus write the selected entry in two different colours")
    assert rgb(colours["unsel"][0]) == menu["item_color"], (
        "the two menus write an unselected entry in two different colours")
    assert rgb(colours["help"][0]) == component("label", "__timeout__")["color"], (
        "the two menus write their help line in two different colours")


# --------------------------------------------------------------------
# The other direction: not "do the two menus agree with each other", but
# "do they still agree with src/brand.py"
# --------------------------------------------------------------------
#
# The test above holds the two menus to EACH OTHER, and only one of its
# four assertions reaches src/brand.py at all - the yellow. The other
# three compare the two files, and would still pass if both had drifted
# away from the palette together. Drifting together is not the unlikely
# case either: whoever edits the boot menu edits both files in one
# sitting, because that is the only way to keep the two firmwares
# showing the same product.
#
# Measured on this tree before these tests: theme.txt writes nine colour
# values and syslinux.cfg writes seventeen, and exactly one of the
# twenty-six was ever compared against src/brand.py.
#
# The copies themselves are unavoidable and are not the problem. GRUB
# cannot import Python, syslinux reads nothing but its own directives,
# and both are parsed by a bootloader long before anything that could
# generate them exists. installer/gui/branding.py is the same situation
# for a different reason and tests/installer/test_branding.py is the
# same answer. What is avoidable is nobody noticing when a copy stops
# being one.
#
# Each entry names the brand constant the value is a copy OF, rather
# than the value itself, so a colour that changes into some other
# perfectly good brand colour still fails. Both tables are exhaustive by
# construction: the tests walk what the FILES contain and fail on
# anything the table does not mention, so a colour added to a boot menu
# cannot arrive unchecked - and test_the_tables_above_have_not_gone_
# stale walks it the other way, so a colour REMOVED from a menu cannot
# leave a table entry behind that no longer guards anything.

_HEX_COLOUR = re.compile(r"#[0-9A-Fa-f]{6}$")

UEFI_BRAND_COPIES = {
    ("theme", "desktop-color"): "PETROL",
    ("theme", "message-color"): "TEXT",
    ("theme", "message-bg-color"): "PETROL",
    ("boot_menu", "item_color"): "TEXT",
    ("boot_menu", "selected_item_color"): "PETROL",
    # Both labels - the help line and the countdown - are secondary text.
    ("label", "color"): "TEXT_DIM",
    ("progress_bar", "fg_color"): "YELLOW",
    ("progress_bar", "bg_color"): "SHADE_2",
    # The trough's edge, so the bar has an extent before it has filled.
    ("progress_bar", "border_color"): "TRACK_EDGE",
}

BIOS_BRAND_COPIES = {
    ("screen", "fg"): "TEXT",
    ("title", "fg"): "YELLOW",
    ("unsel", "fg"): "TEXT",
    ("hotkey", "fg"): "YELLOW",
    ("sel", "fg"): "PETROL",
    ("sel", "bg"): "YELLOW",
    ("hotsel", "fg"): "PETROL",
    ("hotsel", "bg"): "YELLOW",
    ("disabled", "fg"): "TEXT_MUTED",
    ("scrollbar", "fg"): "CYAN",
    ("tabmsg", "fg"): "TEXT_DIM",
    ("help", "fg"): "TEXT_DIM",
    ("timeout_msg", "fg"): "TEXT_DIM",
    ("timeout", "fg"): "YELLOW",
    ("cmdmark", "fg"): "CYAN_TEXT",
    ("cmdline", "fg"): "TEXT",
    ("msg07", "fg"): "TEXT",
}


def _uefi_colours() -> list[tuple[tuple[str, str], str]]:
    """Every colour theme.txt actually sets, as ((where, name), value).

    Whole-line comments are already gone - theme.txt explains its own
    contrast ratios and names half these colours while doing it, so a
    scan that could not tell an explanation from a setting would be
    guarding the prose.
    """
    top, components = theme_file()
    found = [(("theme", name), value) for name, value in top.items()
             if _HEX_COLOUR.match(value)]
    for kind, properties in components:
        found.extend(((kind, name), value)
                     for name, value in properties.items()
                     if _HEX_COLOUR.match(value))
    return found


def _bios_colours() -> list[tuple[tuple[str, str], str, str]]:
    """Every MENU COLOR slot, as ((element, slot), alpha, #rrggbb)."""
    found = []
    for element, pair in syslinux_colours().items():
        for slot, value in zip(("fg", "bg"), pair):
            found.append(((element, slot), value.lstrip("#")[:2], rgb(value)))
    return found


def test_every_colour_the_uefi_menu_writes_is_still_a_brand_value(brand):
    """theme.txt against src/brand.py, value by value."""
    found = _uefi_colours()
    assert found, "theme.txt sets no colour at all, which cannot be right"

    for where, value in found:
        name = UEFI_BRAND_COPIES.get(where)
        assert name, (
            f"theme.txt sets {where[1]} on {where[0]} to {value} and "
            f"UEFI_BRAND_COPIES does not say which brand value that is. "
            f"Add it, so the copy is checked like the others.")
        expected = getattr(brand, name)
        assert value.upper() == expected.upper(), (
            f"theme.txt sets {where[1]} on {where[0]} to {value}, but "
            f"brand.{name} is {expected}. GRUB cannot import src/brand.py, "
            f"so this file is a copy of it - and it has stopped being one.")


def test_every_colour_the_bios_menu_writes_is_still_a_brand_value(brand):
    """syslinux.cfg against src/brand.py, the same way.

    Its colours are #AARRGGBB, and every background but the selected
    entry's is fully transparent so the splash shows through. A
    transparent slot has no colour to check - the RGB behind alpha 00 is
    not drawn - so it is required to be absent from the table rather
    than mapped to something that is never seen.
    """
    for where, alpha, value in _bios_colours():
        if alpha == "00":
            assert where not in BIOS_BRAND_COPIES, (
                f"BIOS_BRAND_COPIES claims {where[0]}'s {where[1]} is a "
                f"brand colour, but syslinux.cfg draws it at alpha 00 - "
                f"it is transparent and nothing of it is on the screen")
            continue

        assert alpha.upper() == "FF", (
            f"syslinux.cfg draws {where[0]}'s {where[1]} at alpha {alpha}. "
            f"A partly transparent colour composites against the splash, "
            f"so the measured contrast in this file no longer describes "
            f"what is on the screen")
        name = BIOS_BRAND_COPIES.get(where)
        assert name, (
            f"syslinux.cfg draws {where[0]}'s {where[1]} in {value} and "
            f"BIOS_BRAND_COPIES does not say which brand value that is")
        expected = getattr(brand, name)
        assert value.upper() == expected.upper(), (
            f"syslinux.cfg draws {where[0]}'s {where[1]} in {value}, but "
            f"brand.{name} is {expected}. The BIOS menu and the desktop "
            f"it installs would be two different products.")


def test_the_tables_above_have_not_gone_stale():
    """The third direction, and the one a guard usually forgets.

    A table entry for a colour the file no longer sets guards nothing,
    and looks exactly like one that does. Both walks above start from
    the files, so they cannot see it; this one starts from the tables.
    """
    uefi_seen = {where for where, _ in _uefi_colours()}
    stale = sorted(set(UEFI_BRAND_COPIES) - uefi_seen)
    assert stale == [], (
        f"UEFI_BRAND_COPIES names colours theme.txt no longer sets: {stale}")

    bios_seen = {where for where, alpha, _ in _bios_colours() if alpha != "00"}
    stale = sorted(set(BIOS_BRAND_COPIES) - bios_seen)
    assert stale == [], (
        f"BIOS_BRAND_COPIES names colours syslinux.cfg no longer draws: "
        f"{stale}")


def test_the_help_line_says_the_same_thing_on_both(harness):
    """One sentence, and the one word in it that has to differ.

    GRUB edits an entry on `e` and syslinux on Tab, so the two lines
    cannot be identical - but everything around that word can be, and a
    line that drifted into two different sentences would be two different
    products.
    """
    grub_help = None
    for kind, properties in theme_file()[1]:
        if kind == "label" and "id" not in properties:
            grub_help = properties["text"]
    assert grub_help, "the UEFI menu has no help line"
    bios_help = syslinux_directive("MENU TABMSG")

    def shape(text: str) -> str:
        return re.sub(r"\b(e|Tab)\b", "<key>", text)

    assert shape(grub_help) == shape(bios_help), (
        f"the two menus say different things:\n  UEFI: {grub_help}\n"
        f"  BIOS: {bios_help}")

    # Ascii only, and that is not an accident: syslinux draws through a
    # codepage font and would put two boxes where an umlaut is.
    assert bios_help.isascii(), (
        f"the BIOS help line has a character syslinux cannot draw: {bios_help!r}")


# --------------------------------------------------------------------
# The classifier, which is the half that can prove the theme LOADED
# --------------------------------------------------------------------

def test_the_classifier_measures_this_brand_and_not_some_other(harness, brand):
    """The three colours it counts are the three the theme is made of.

    Without this, the guard would keep passing after a palette change
    that left the menu looking like something else entirely - it would be
    measuring a brand nothing ships any more.
    """
    ground = ["#%02X%02X%02X" % rgb_triple for rgb_triple in harness.BRAND_GROUND]
    assert ground[0] == brand.PETROL, (
        f"the classifier's first ground colour is {ground[0]}, not the "
        f"brand petrol {brand.PETROL}")
    assert "#%02X%02X%02X" % harness.BRAND_YELLOW == brand.YELLOW
    assert "#%02X%02X%02X" % harness.BRAND_CYAN == brand.CYAN


def test_the_classifier_calls_a_branded_menu_branded(harness, tmp_path):
    frame = write_png(tmp_path / "branded.png", 320, 200, _branded)
    measured = harness.measure_frame(frame)
    assert harness.is_themed(measured), measured


def test_the_classifier_calls_a_text_console_a_fallback(harness, tmp_path):
    """The failure this whole apparatus exists for: GRUB drops to text
    without an error when the theme, the font or the image cannot be
    read."""
    frame = write_png(tmp_path / "console.png", 320, 200, _text_console)
    measured = harness.measure_frame(frame)
    assert not harness.is_themed(measured), measured
    assert measured["black"] > 0.8, measured


def test_a_splash_that_did_not_load_is_not_a_branded_menu(harness, tmp_path):
    """The half-failure, and the reason there are three measures.

    syslinux's colour attributes work whether or not MENU BACKGROUND
    could be decoded, so a menu with no picture still paints its yellow
    selected bar. A guard that only looked for the yellow would call this
    branded; it is a black screen with a yellow stripe on it.
    """
    frame = write_png(tmp_path / "no-splash.png", 320, 200,
                      _colours_without_the_picture)
    measured = harness.measure_frame(frame)
    assert measured["yellow"] >= harness.BOOT_MENU_MIN_YELLOW, (
        "the fixture is meant to still have the yellow bar on it")
    assert not harness.is_themed(measured), measured


def test_a_picture_with_nothing_themed_over_it_is_not_a_branded_menu(harness,
                                                                     tmp_path):
    """The other half-failure. GRUB reaching gfxterm and then failing to
    parse theme.txt gives a text menu on a graphical terminal - which can
    still have the background behind it if `background_image` ran, and
    has none of the theme's own colours."""
    frame = write_png(tmp_path / "no-theme.png", 320, 200,
                      _picture_without_the_theme)
    measured = harness.measure_frame(frame)
    assert measured["ground"] >= harness.BOOT_MENU_MIN_GROUND, (
        "the fixture is meant to still have the petrol behind it")
    assert not harness.is_themed(measured), measured


def test_one_branded_frame_in_a_series_is_enough(harness, tmp_path):
    """A boot is photographed several times and only some of the frames
    can be the menu: firmware output comes before it and a kernel scrolls
    over it afterwards. What is asked is whether the menu was ever on the
    screen with its identity on it."""
    frames = [write_png(tmp_path / "01.png", 320, 200, _text_console),
              write_png(tmp_path / "02.png", 320, 200, _branded),
              write_png(tmp_path / "03.png", 320, 200, _text_console)]
    themed, report = harness.grade_boot_menu(frames)
    assert themed
    assert sum("THEMED" in line for line in report) == 1

    themed, report = harness.grade_boot_menu([frames[0], frames[2]])
    assert not themed
    assert any("no frame reached" in line for line in report), report


def test_a_run_that_photographed_no_menu_says_so_instead_of_accusing(harness):
    """Nichts gemessen ist nicht dasselbe wie nichts gefunden.

    Gemessen an einem release-install-Lauf: sein Zeitplan fotografiert
    bei 30 und 60 Sekunden, beide hinter dem Menuefenster, also kam hier
    eine leere Liste an. Darunter stand trotzdem "That is what a GRUB
    theme ... that could not be loaded looks like" - eine Anklage gegen
    ein Menue, das in diesem Lauf niemand angesehen hatte, und sie liest
    sich genau wie der echte Fund.
    """
    themed, report = harness.grade_boot_menu([])

    assert not themed, "eine leere Messung darf nichts bestaetigen"
    assert not any("could not be loaded" in line for line in report), (
        "eine leere Messung klingt wie ein gefallenes Thema")
    assert any("not looked at here" in line for line in report), report


def test_the_installed_system_is_photographed_while_its_menu_is_up(harness):
    """Seit installer/core/translate.py GRUB einrichtet, hat auch die
    INSTALLATION ein Startmenue - und es ist die einzige Stelle, an der
    sichtbar wird, ob das Thema sie ueberlebt hat: GRUB antwortet auf ein
    Thema, das es nicht lesen kann, mit dem Textmodus und ohne Fehler.

    Der Zeitplan muss also mindestens eine Marke im Menuefenster haben,
    sonst misst grade_boot_menu() bei diesem Lauf nichts.
    """
    marks = harness.RELEASE_SETTLE["release-installed"]
    inside = [mark for mark in marks if mark <= harness.BOOT_MENU_WINDOW]
    assert len(inside) >= 2, (
        f"nur {inside} von {marks} liegen im Menuefenster; ein einziger "
        "Treffer macht aus einem langsamen POST einen Fehlbefund ueber das "
        "Thema")


def test_the_guard_is_wired_to_an_exit_code(harness):
    """A measurement nothing acts on is a comment.

    The boot-menu scenario is the one release-family run whose exit code
    depends on what was on the screen, and the thresholds have to be far
    enough from the measured values that a different display adapter is
    not a failure about the theme.
    """
    assert "boot-menu" in harness.SCENARIOS
    assert "boot-menu" in harness.RELEASE_FAMILY
    assert set(harness.BOOT_MENU_SETTLE) == {"uefi", "bios"}, (
        "both firmwares put up a menu, drawn by two different programs, "
        "and a machine offers one of them")

    source = (ISO / "test-boot.py").read_text(encoding="utf-8")
    assert "grade_boot_menu(menu_frames)" in source, (
        "run_release no longer measures the frames it took")
    assert "return 0 if themed and not died else 1" in source, (
        "the boot-menu scenario no longer reports its verdict as an exit "
        "code, so nothing that runs it would notice a fallback")

    # Measured on real frames; see the table in test-boot.py. Every
    # threshold has to sit clear of BOTH sides, or the guard becomes a
    # report about the display adapter: at least a factor of two below
    # the tightest branded reading (the BIOS menu's yellow, 0.0170) and
    # at least a factor of two above nothing / below the fallback's own
    # 0.947 of black.
    assert harness.BOOT_MENU_MIN_YELLOW <= 0.0170 / 2
    assert harness.BOOT_MENU_MIN_GROUND <= 0.923 / 1.4
    assert 0.0 < harness.BOOT_MENU_MAX_BLACK <= 0.947 / 2
