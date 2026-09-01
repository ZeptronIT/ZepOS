# SPDX-License-Identifier: GPL-3.0-or-later
"""The shipped palette, measured rather than admired.

Contrast is a correctness question here and not a matter of taste. A bar
whose clock cannot be read against the bar is broken in a way no test of
"is the module present" can see, and the brand's own primary accent -
#0096C0 on #0D3D47 - is 3.45:1, which is under WCAG AA. So every pair
this project ships is recomputed here from the sRGB formula rather than
trusted from a comment.

WHY THE RATIOS ARE COMPUTED AND NOT ASSERTED AS NUMBERS
    A test that said `assert ratio == 6.04` would fail on a colour
    change that is perfectly fine and pass on one that is not. What
    matters is the threshold, so that is what is checked, and the
    measured value is printed in the failure message so whoever broke it
    can see by how much.
"""
from __future__ import annotations

import re
import struct
import zlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"


def _flat(name: str):
    """Ein Modul aus src/, das selbst flach importiert.

    src/theme.py sagt `import brand`, ist ueber `from src import theme`
    also nicht erreichbar. Dieselbe Vorrichtung wie in
    tests/src/test_greeter.py; der Pfad wird gleich wieder abgeraeumt.
    """
    import importlib
    import sys

    sys.path.insert(0, str(SRC))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(SRC))


_theme = _flat("theme")


@pytest.fixture(params=sorted(_theme.THEMES))
def palette(request):
    """JEDES Thema, durch dieselbe Kontrastrechnung.

    WARUM DIESE DATEI SEIT DEM 12.08.2026 ZWEIMAL LAEUFT
        Weil eine Palette, die nur einmal gerechnet wird, keine Palette
        ist, sondern eine Farbliste. Jede Zusicherung hier - "diese
        Farbe auf jenem Grund" - ist eine Aussage ueber die BEZIEHUNG
        zweier Werte, und ob sie eine Regel oder ein Zufall des
        ausgelieferten Themas ist, laesst sich erst an einem zweiten
        sehen.

        Es hat sich sofort ausgezahlt: das zweite Thema ist hell, und
        drei Zusicherungen dieses Baums waren fuer hellen Text auf
        dunklem Grund geschrieben und nicht fuer den umgekehrten Fall
        (siehe test_glass.py und tests/lock/test_style.py). Sie rechnen
        jetzt beide Richtungen.

    Die Werte kommen aus theme.Palette und nicht aus brand.py: dort
    steht das ausgelieferte Thema, hier stehen alle.
    """
    return _theme.palette(request.param)


@pytest.fixture
def brand(monkeypatch):
    """The palette module, imported the way the generator imports it.

    src/ has no __init__.py and every module in it uses flat imports, so
    the directory goes on the path rather than the package - the same
    fixture shape tests/src/test_user_settings.py already uses, and for
    the same reason. monkeypatch takes it back off afterwards, so no
    later test finds a src/ module under a bare name by accident.
    """
    monkeypatch.syspath_prepend(str(SRC))
    import brand as module
    return module

# WCAG 2.1 SC 1.4.3: 4.5:1 for body text, 3:1 for large text and for the
# visual boundary of a user interface component (SC 1.4.11).
AA_TEXT = 4.5
AA_LARGE = 3.0


def _channel(value: int) -> float:
    c = value / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(colour: str) -> float:
    digits = colour.lstrip("#")
    r, g, b = (int(digits[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def ratio(foreground: str, background: str) -> float:
    a, b = luminance(foreground), luminance(background)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def assert_readable(foreground: str, background: str, what: str,
                    threshold: float = AA_TEXT) -> None:
    measured = ratio(foreground, background)
    assert measured >= threshold, (
        f"{what}: {foreground} on {background} is {measured:.2f}:1, "
        f"under the {threshold}:1 WCAG AA threshold. Text nobody can read "
        f"is worse than text in the wrong colour.")



def _png_corner(path: Path) -> tuple[int, int, str]:
    """Size and top-left pixel of a PNG, with the standard library only.

    Pillow is not a dependency of this project and must not become one
    for a test. PNG is not hard to read this far: IHDR is fixed-width and
    always first, and the first scanline needs one filter type undone.
    Only the shapes the shipped wallpaper is actually in are handled -
    8-bit truecolour, no interlacing - and anything else raises rather
    than guessing, because a silent wrong answer here is worse than none.
    """
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"

    width, height = struct.unpack(">II", data[16:24])
    depth, colour_type, _comp, _filt, interlace = data[24:29]
    assert (depth, interlace) == (8, 0), (
        f"{path} is {depth}-bit, interlace {interlace}; this reader "
        f"handles 8-bit non-interlaced only")
    channels = {2: 3, 6: 4}.get(colour_type)
    assert channels, f"{path} has colour type {colour_type}, not truecolour"

    # Every IDAT chunk, concatenated, is one zlib stream.
    stream, offset = b"", 8
    while offset < len(data):
        length, kind = struct.unpack(">I4s", data[offset:offset + 8])
        if kind == b"IDAT":
            stream += data[offset + 8:offset + 8 + length]
        offset += 12 + length
        if kind == b"IEND":
            break

    row = zlib.decompressobj().decompress(stream, 1 + width * channels)
    filter_type = row[0]
    # Row 0 only: the previous row is all zeroes, so Up contributes
    # nothing and Average and Paeth reduce to the pixel on the left.
    pixels = bytearray(row[1:1 + channels])
    if filter_type in (1, 3, 4):
        # The first pixel of a row has no left neighbour either, so for
        # row 0 every one of these filters leaves it unchanged.
        pass
    elif filter_type not in (0, 2):
        raise AssertionError(f"unhandled PNG filter type {filter_type}")
    return width, height, "#%02X%02X%02X" % tuple(pixels[:3])


# --------------------------------------------------------------------
# The brand itself
# --------------------------------------------------------------------

def test_the_brand_values_are_zeptronits_own(brand):
    """Not ours to adjust. The petrol is the measured background of
    Design/ZeptronIT_Wallpaper.png; the rest come from the same folder."""
    assert brand.PETROL == "#0D3D47"
    assert brand.CYAN == "#0096C0"
    assert brand.YELLOW == "#FFCB00"
    assert (brand.SHADE_1, brand.SHADE_2, brand.SHADE_3) == (
        "#214F59", "#2F728A", "#3B88A5")


def test_the_wallpapers_own_background_is_the_module_background(brand):
    """Not a coincidence and worth keeping.

    Die Kacheln der Leiste liegen mit GLASS_CHIP_ALPHA auf einer Platte
    mit GLASS_PANEL_ALPHA auf dem, was die Tapete dahinter hat - mit
    einer anderen Hintergrundfarbe waere die wirksame also unbekannt und
    jedes Verhaeltnis hier geraten. Mit dem Petrol auf dem Petrol IST
    die Mischung das Petrol, ueberall dort, wo die Tapete ihre eigene
    Grundfarbe zeigt, und das ist der groesste Teil.

    Der schlechteste Fall - eine fremde, helle Tapete - wird in
    tests/src/test_glass.py gerechnet.
    """
    assert brand.COLORS["background"] == brand.PETROL

    width, height, corner = _png_corner(REPO / "src/branding/zepos-wallpaper.png")
    assert (width, height) == (1920, 1080)
    assert corner == brand.PETROL, (
        f"the shipped wallpaper's background is {corner}, not the petrol "
        f"every contrast ratio in this file was computed against")


def test_the_brand_cyan_is_not_used_as_text_anywhere(palette):
    """The measurement the whole derived palette exists for.

    #0096C0 on #0D3D47 is 3.45:1. It is the company's primary accent and
    it cannot be read on the company's own background, so CYAN_TEXT is
    that hue lightened until it can - and the untouched value is kept for
    borders, fills and indicators, which are seen rather than read.
    """
    assert ratio(palette.CYAN, palette.PETROL) < AA_TEXT, (
        "the brand cyan now passes as text, which would make CYAN_TEXT "
        "unnecessary - check before deleting it")
    assert_readable(palette.CYAN_TEXT, palette.PETROL, "the readable cyan")

    # Everywhere the raw cyan is used, it is used as a shape.
    seen_as_shape = {
        "hyprland_active_border", "eww_progress_fill", "disk_ring_used",
        "notification_border",
    }
    for key, value in palette.COLORS.items():
        if value == palette.CYAN:
            assert key in seen_as_shape, (
                f"{key} is the raw brand cyan; if it is a text colour it "
                f"is 3.45:1 on petrol and must be CYAN_TEXT instead")


# --------------------------------------------------------------------
# Every text colour, against the surface it is drawn on
# --------------------------------------------------------------------

# The three surfaces anything in ZepOS is written on, and what is written
# on each. Read off the templates rather than assumed - see the module
# docstring of src/brand.py.
# Vierzehn Namen sind am 12.08.2026 aus diesen beiden Listen gefallen -
# accent_secondary, dock_icon_hover, hardware_cpu/_memory/_temp, vpn,
# wallpaper_portrait, die sechs calendar_*, eww_text und disk_text. Nicht,
# weil sich an ihrem Kontrast etwas geaendert haette, sondern weil es die
# Farben nicht mehr gibt: sie erreichten keine Vorlage, und der Kopf von
# src/brand.py fuehrt die Messung. Eine Kontrastpruefung fuer eine Farbe,
# die nirgends gezeichnet wird, prueft nichts.
# Und seit dem 12.08.2026 acht weniger: bar_date, bar_weather,
# bar_network, bar_bluetooth, bar_battery, bar_audio, bar_microphone und
# bar_workspace. Die Module tragen im Ruhezustand die Textfarbe der
# Leiste; Farbe bedeutet dort jetzt Zustand. Siehe den Kopf von
# src/styles/bar-style.template.
ON_PETROL = (
    "bar_text", "bar_workspace_visible", "hyprbar_text",
    "hyprbar_close", "hyprbar_minimize", "hyprbar_maximize", "dock_icon",
    "dock_indicator", "accent",
    "success", "warning", "critical", "inactive",
    "vpn_connecting", "wallpaper_landscape",
)
ON_INK = (
    "overlay_text", "overlay_subtext", "overlay_accent",
    "overlay_accent_hover", "overlay_accent_dim", "overlay_green",
    "terminal_fg", "terminal_cursor", "notification_text",
    "notification_progress", "notification_low_text",
    "notification_critical_text",
    # Die Eingabezeile sitzt IM Terminal, also auf terminal_bg - und das
    # ist INK. Sieben Rollen, seit dem 12.08.2026, als aus einer
    # konfigurierten und nirgends installierten Prompt-Einrichtung eine
    # erzeugte ~/.p10k.zsh wurde. Die zwei engsten Werte stehen bei
    # brand.COLOR_FIELDS; beide liegen im hellen Thema und nicht im
    # dunklen, was ohne das zweite Thema niemand gesehen haette.
    "prompt_path", "prompt_vcs_clean", "prompt_vcs_dirty", "prompt_ok",
    "prompt_error", "prompt_context", "prompt_time",
)
# The AGS header is brand.PETROL and $text/$subtext/$accent are drawn on
# it as well as on the ink, so both have to hold.
ON_SURFACE = ("overlay_text", "overlay_subtext", "overlay_accent")


@pytest.mark.parametrize("key", ON_PETROL)
def test_every_colour_on_the_petrol_can_be_read(palette, key):
    assert_readable(palette.COLORS[key], palette.PETROL, key)


@pytest.mark.parametrize("key", ON_INK)
def test_every_colour_on_the_ink_can_be_read(palette, key):
    assert_readable(palette.COLORS[key], palette.INK, key)


@pytest.mark.parametrize("key", ON_SURFACE)
def test_every_colour_on_the_ags_header_can_be_read(palette, key):
    assert_readable(palette.COLORS[key], palette.COLORS["overlay_surface"], key)


def test_the_dimmed_workspace_still_clears_the_threshold(palette):
    """styles/workspaces-style.template draws an empty workspace at
    STYLE_OPACITY_DISABLED, which is 0.6. The opacity is part of the
    colour: TEXT_DIM there composites to 3.39:1 and fails, which is why
    the bar's text colour is the full TEXT and not the dim one.

    Gemessen wird seit dem 12.08.2026 `bar_text`: der eigene Schluessel
    des Arbeitsbereichs ist mit den sieben anderen Ruhefarben entfallen,
    und ein leerer Arbeitsbereich erbt jetzt genau diese Farbe.
    """
    opacity = 0.6
    fg = palette.COLORS["bar_text"].lstrip("#")
    bg = palette.PETROL.lstrip("#")
    blended = "#" + "".join(
        "%02X" % round(opacity * int(fg[i:i + 2], 16)
                       + (1 - opacity) * int(bg[i:i + 2], 16))
        for i in (0, 2, 4))
    assert_readable(blended, palette.PETROL,
                    "an empty workspace at 0.6 opacity")


# Die Gruende, auf denen ein fremdes GTK4-Fenster eine Nebenzeile malt.
# ROLLEN und keine Hexwerte, weil der Nutzer sie verstellen kann - und
# genau die drei, die gtk4-colors-config.template als --window-bg-color,
# --view-bg-color und --card-bg-color setzt. Kopfleiste, Aufklapper und
# Rueckfrage tragen dieselbe Farbe wie der Fenstergrund.
GTK4_DIM_GROUNDS = ("overlay_surface", "overlay_bg", "overlay_item_hover")


def _blend(foreground: str, alpha: float, ground: str) -> str:
    """Was man sieht, wenn `foreground` mit `alpha` auf `ground` liegt."""
    top, bottom = foreground.lstrip("#"), ground.lstrip("#")
    return "#" + "".join(
        "%02X" % round(alpha * int(top[i:i + 2], 16)
                       + (1 - alpha) * int(bottom[i:i + 2], 16))
        for i in (0, 2, 4))


def test_the_dimmed_line_of_a_foreign_gtk4_window_stays_readable(palette):
    """Die Nebenzeile jedes GTK4-Fensters, gerechnet statt geglaubt.

    GEMELDET am 01.09.2026: "die einstellungen sind irgendwie verbuggt,
    die schrift ist so blass, man kann sie kaum sehen".

    libadwaita 1.9.3 malt `.dimmed`, `row label.subtitle`, `.dim-label`,
    `headerbar .subtitle` und die Platzhalter der Eingabefelder mit
    `opacity: var(--dim-opacity)` und liest `@define-color dimmed_color`
    dafuer NIE. Bei seinen 55 % misst der Fenstergrund 4.15:1 unter
    ZeptronIT und eine Listenzeile 3.95:1 unter Tageslicht - beide unter
    AA. brand.dim_opacity() rechnet stattdessen die Deckkraft aus, bei
    der die Vordergrundfarbe genau die zweite Textstufe DIESER Palette
    ergibt, und gtk4-colors-config.template setzt sie in :root.

    Diese Zusicherung ist die Gegenrechnung dazu. Ohne sie waere die
    Ableitung eine Behauptung: eine Palette, deren Vorder- und
    Hintergrundfarbe naeher aneinanderruecken, kann sie unter die Linie
    ziehen, ohne dass ein anderer Test etwas merkt.
    """
    text = palette.COLORS["overlay_text"]
    surface = palette.COLORS["overlay_surface"]
    dimmed = palette.COLORS["overlay_subtext"]

    prozent = palette.dim_opacity(text, surface, dimmed)
    assert prozent.endswith("%"), (
        f"--dim-opacity ist {prozent!r} und damit kein Prozentwert - "
        "libadwaita reicht dieselbe Variable an color-mix() weiter, und "
        "das nimmt nur Prozent; ein blosser Bruch laesst die ganze "
        "Deklaration lautlos fallen")
    alpha = int(prozent.rstrip("%")) / 100

    for role in GTK4_DIM_GROUNDS:
        ground = palette.COLORS[role]
        assert_readable(_blend(text, alpha, ground), ground,
                        f"eine Nebenzeile auf {role} bei {prozent}")

    # Die Gegenprobe: eine Deckkraft, die nichts mehr daempft, waere
    # keine zweite Textstufe, sondern dieselbe wie die erste.
    assert alpha < 1.0, (
        "--dim-opacity steht auf 100 % - dann sieht eine Nebenzeile aus "
        "wie ihre Zeile, und die Stufe, die sie tragen soll, gibt es "
        "nicht mehr")


def test_the_terminals_active_tab_reads_both_ways(palette):
    """The one place the two brand colours meet at full strength."""
    assert_readable(palette.COLORS["terminal_active_tab_fg"],
                    palette.COLORS["terminal_active_tab_bg"],
                    "the active kitty tab")
    assert_readable(palette.COLORS["terminal_inactive_tab_fg"],
                    palette.COLORS["terminal_inactive_tab_bg"],
                    "an inactive kitty tab")


def test_the_two_state_backgrounds_read_against_their_own_text(palette):
    """Die zwei Zustandsgruende, und was auf ihnen steht.

    DER NAME HAT SICH AM 13.08.2026 GEAENDERT, weil sich der Leser
    geaendert hat. Die drei Paare hiessen damals "hardware warning/
    critical/offline", und das Hardwaremodul der Leiste hat sie
    wirklich benutzt - als deckende Kaesten auf dem Glas. Diese Regel
    ist an dem Tag gefallen (siehe #custom-hardware in
    src/styles/bar-style.template: ein Zustand ist eine Farbe und kein
    Kasten), und mit ihr die sieben STYLE_HARDWARE_*-Platzhalter.

    Zwei der drei Gruende blieben zunaechst, weil sie andere Leser
    hatten - STYLE_GLASS_NOTIFICATION_CRITICAL (STATE_CRITICAL_BG),
    STYLE_LOGOUT_RESTART_BG (STATE_WARNING_BG) und STYLE_LOGOUT_SAFE_BG
    (STATE_OFFLINE_BG, der dritte). Geprueft wurde, dass auf jedem
    dieser Gruende die Schrift lesbar ist, die dort steht.

    DREI WURDEN ZWEI, AM 19.08.2026 (Aufgabe 26)
        zepos-logout ist geloescht (Regel 14) - mit ihm STYLE_LOGOUT_
        SAFE_BG, der letzte Leser von STATE_OFFLINE_BG. GEMESSEN:
        `grep -rn STATE_OFFLINE_BG src/` fand danach nur noch seine
        eigene Definition in brand.py/theme.py, keinen Verbraucher mehr
        - tests/src/test_theme.py::test_changing_this_field_moves_a_
        generated_byte haelt genau das fest ("ein Themenfeld ohne Leser
        ist ein Regler, der nichts tut") und hat sie durchfallen
        lassen. STATE_OFFLINE_BG ist darum aus theme.FIELDS und beiden
        Paletten gestrichen (Regel 14 - kein "vielleicht spaeter
        wieder"), nicht als ungenutzte Option stehen geblieben.
    """
    for colour, background, what in (
        (palette.YELLOW, palette.STATE_WARNING_BG, "der warnende Grund"),
        (palette.RED, palette.STATE_CRITICAL_BG, "der kritische Grund"),
    ):
        assert_readable(colour, background, what)


def test_the_urgent_workspace_is_readable_at_all(palette):
    """It used to be #3d0000 - 1.4:1 on the module behind it. The one
    state on the bar that exists to be noticed was the only one that
    could not be seen."""
    assert_readable(palette.RED, palette.PETROL, "an urgent workspace")


def test_the_hover_state_is_readable(palette):
    """styles/misc-style.template puts STYLE_HOVER_COLOR on
    STYLE_HOVER_BG, and both are literals in style_definition.py rather
    than settings keys - so nothing but this checks them."""
    assert_readable(palette.TEXT, palette.SHADE_1, "a hovered module")


# --------------------------------------------------------------------
# The palette is one palette
# --------------------------------------------------------------------

def test_every_colour_is_a_six_digit_hex(palette):
    """mako-config.template appends DD and AA to the background and the
    border it is given. A three-digit value or an rgba() there produces a
    colour mako cannot parse, and a notification daemon that will not
    start is a desktop with no notifications and no error."""
    for key, value in palette.COLORS.items():
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", value), (
            f"{key} is {value!r}, which is not a six-digit hex")


def test_the_style_layer_answers_for_every_key_the_settings_offer(brand):
    """user_settings' defaults and style_definition's fallbacks used to
    be two lists that had to agree, and did not."""
    import user_settings
    assert user_settings.DEFAULT_SETTINGS["colors"] == brand.COLORS


def test_the_style_layer_holds_no_colour_literal_of_its_own(brand):
    """The point of src/brand.py, checked where the drift actually was.

    style_definition.py carried a hex literal beside every one of a
    hundred and thirty-three get_user_color() calls, plus twenty-eight
    placeholders defined as literals outright - and those twenty-eight
    were the ones no setting could reach at all, which is how the tooltip,
    the dock and every hardware state stayed Catppuccin after everything
    around them had stopped being.

    Only rgba() survives, three of them, and they are named here one by
    one: they are the brand petrol with an alpha channel and the first
    shade, and an alpha channel is the one thing a six-digit hex cannot
    carry.

    DREI UND NICHT MEHR VIER, SEIT DEM 12.08.2026
        `rgba(13, 61, 71, 0.85)` war die Platte des Docks, und beides
        daran war falsch: die Kanaele konnte kein Thema austauschen, und
        die 0.85 war geraten. Sie kommt jetzt aus THEME.rgba() mit der
        abgeleiteten Deckkraft - der Wert bewegt sich damit von 0.85 auf
        0.86, und zwar weil er GERECHNET wird und nicht, weil jemand ihn
        anders gewaehlt hat.

    user_settings.py is not scanned - it is checked more strictly, by
    the equality above.
    """
    allowed_rgba = {"rgba(13, 61, 71, 0)", "rgba(13, 61, 71, 0.5)",
                    "rgba(33, 79, 89, 0.9)"}
    name = "src/style_definition.py"
    text = (REPO / name).read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("#"))
    found = re.findall(r'"(#[0-9a-fA-F]{3,8})"', code)
    assert found == [], f"{name} carries colour literals again: {found}"
    for rgba in re.findall(r'"(rgba\([^"]*\))"', code):
        assert rgba in allowed_rgba, (
            f"{name} carries an unlisted rgba: {rgba}")


# --------------------------------------------------------------------
# The same question one layer out: the stylesheets themselves
# --------------------------------------------------------------------
#
# The check above holds src/style_definition.py to the palette. It says
# nothing about src/styles/, and that is where the drift actually was:
#
#     wlogout-style.template   35 colour literals,  0 placeholders
#     terminal-green-style     12 colour literals,  0 placeholders
#     wofi-style.template      11 colour literals,  5 placeholders
#     the other seventeen       0 colour literals
#
# wofi counted as connected to the centre because it HAS placeholders -
# it had one for the font and none for any colour, so a file that was
# entirely off the brand passed for a file that was on it. Counting
# placeholders answers "does this file know about the centre"; counting
# literals answers "does it still have a palette of its own", which is
# the question that matters.

_CSS_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"^\s*//.*$", re.MULTILINE)

# One file, and the reason it is not a stylesheet. Its own first line
# says "Diese Werte werden vom Bash-Script gelesen": it is a key-value
# document that borrowed CSS syntax, and the custom properties in it are
# fields rather than declarations GTK is ever asked to parse. Whether
# anything still reads it is a separate and open question - GRID_COLOR,
# the value it looks like it should supply, is exported by
# grid-wallpaper-toggle-config.template instead - but that is a question
# about a dead file, not about a palette.
NOT_A_STYLESHEET = {"grid-wallpaper-toggle-style.template"}


# Die groesste Stilvorlage des Projekts liegt NICHT in src/styles/.
#
# GEMESSEN am 12.08.2026: `src/templates/ags-style.template` ist mit
# ueber zweitausend Zeilen und elf Fenstern die groesste Oberflaeche des
# Schreibtischs - und wurde von der Pruefung unten nie gelesen, weil sie
# `src/styles/*.template` abklapperte. Der Ordner ist eine Entscheidung
# des Generators (ZEPOS_TEMPLATE_SUBDIR), keine Aussage darueber, ob
# eine Datei ein Stylesheet ist.
#
# Was in der Luecke ueberlebt hat, gezaehlt am selben Tag: ZWOELF
# Farbliterale und ein rgba(). Darunter das #1a0c0c der kritischen
# Meldung, zwei Graustufen des Farbwaehlers, ein Gruen fuer den
# gewaehlten Kalendertag - und neun Farben je Anwendung, von denen fuenf
# woertlich aus der Syntaxpalette des Editors stammten.
EXTRA_STYLESHEETS = ("src/templates/ags-style.template",)


def _style_templates():
    return (sorted((REPO / "src/styles").glob("*.template"))
            + [REPO / name for name in EXTRA_STYLESHEETS])


def _without_comments(text: str) -> str:
    """The file with its comments gone.

    Both kinds: these files explain themselves at length and several of
    the explanations quote the very colours that were removed - the
    measurement that proved wofi's greens never reached GTK is a comment
    containing #00ff00. A scan that could not tell an explanation from a
    declaration would force the explanations out, which is the opposite
    of what this project does with them.
    """
    return _LINE_COMMENT.sub("", _CSS_BLOCK_COMMENT.sub("", text))


def test_no_stylesheet_carries_a_colour_of_its_own(brand):
    """Every colour in src/styles/ comes from the centre, or it is not a
    colour this project can change in one place."""
    offenders = {}
    for path in _style_templates():
        found = re.findall(r"#[0-9a-fA-F]{3,8}\b",
                           _without_comments(path.read_text(encoding="utf-8")))
        if found:
            offenders[path.name] = found

    assert offenders == {}, (
        "these stylesheets carry colour literals again, so the palette is "
        "in two places: "
        + "; ".join(f"{name}: {values}" for name, values in offenders.items()))


def test_no_stylesheet_asks_gtk_for_a_css_variable():
    """The bug that hid inside wofi for as long as it existed.

    GTK3 has neither custom properties nor var(). Measured against its
    own parser:

        Gtk.CssProvider().load_from_data(
            b'* { --green: #00ff00; } window { background-color: var(--green); }')
        -> "Expected semicolon"
        -> "'var' is not a valid color name"

    GTK drops the declaration it cannot parse and keeps the rest, so a
    stylesheet written this way LOOKS like it sets colours, sets none of
    them, and reports nothing anywhere. wofi's generated CSS produced 39
    parser errors and rendered in GTK's own default grey; it is 0 now.

    GTK4 HAS LEARNED THEM, AND THE RULE STAYS. Measured 11.08.2026
    against the shipped GTK 4.22.4 - the version in the pinned
    snapshot -

        Gtk.CssProvider().load_from_data(
            b':root { --zep-bg: #08262c; } window { background-color: var(--zep-bg); }')
        -> 0 parser errors

    so zepos-menu's stylesheet COULD use them. It does not, and neither
    may any other file here: nineteen of the twenty stylesheets in this
    directory are read by GTK3 programs - waybar, wlogout,
    nwg-dock-hyprland - and a rule that holds for one file and not for
    its neighbours is a rule nobody can apply while writing. The values
    are substituted at generation time in any case, so a variable would
    only be a second indirection in front of the same number.

    Note `var(` alone is not the test. terminal-green-style.template is
    a Sublime colour scheme and `var(green)` is that format's own
    syntax, which is fine - it is the CSS custom-property spelling,
    `--name`, that no GTK stylesheet may use.
    """
    offenders = {}
    for path in _style_templates():
        if path.name in NOT_A_STYLESHEET:
            continue
        code = _without_comments(path.read_text(encoding="utf-8"))
        found = re.findall(r"var\(\s*--[\w-]+\s*\)", code)
        found += re.findall(r"^\s*(--[\w-]+)\s*:", code, re.MULTILINE)
        if found:
            offenders[path.name] = found

    assert offenders == {}, (
        "GTK understands neither of these and silently drops the whole "
        "declaration, so these colours never reach the screen: "
        + "; ".join(f"{name}: {values}" for name, values in offenders.items()))


def test_the_style_editor_no_longer_carries_its_own_copy(brand):
    """It was the third one, and the one that disagreed about `warning`.
    It now reads BRAND_DEFAULTS, which the generator substitutes."""
    editor = (REPO / "src/templates/ags-style-editor.template").read_text(
        encoding="utf-8")
    assert "{{STYLE_BRAND_COLORS_JSON}}" in editor
    assert 'default: "#' not in editor, (
        "the style editor carries per-key colour literals again")
    assert "colors: BRAND_DEFAULTS," in editor, (
        "the ZeptronIT preset no longer restores the shipped palette")


def test_the_fonts_keep_the_icon_font_behind_the_brand_one(brand):
    """Every glyph in icon_definition.py is a Nerd Font codepoint and
    Fira Code carries none of them. fontconfig picks the first family
    that HAS each glyph, so the order is what makes the text the brand's
    and the icons legible. Drop the Nerd Font and the bar is boxes."""
    assert brand.FONT_FAMILY_CODE.index(brand.FONT_CODE) < \
        brand.FONT_FAMILY_CODE.index(brand.FONT_ICONS)
    assert brand.FONT_ICONS in brand.FONT_FAMILY_CODE
    assert brand.FONT_ICONS in brand.FONT_FAMILY_TEXT
    assert brand.FONT_FAMILY_TEXT.startswith(f'"{brand.FONT_TEXT}"')
