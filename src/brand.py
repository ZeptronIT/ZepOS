#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The ZeptronIT brand, and every colour ZepOS ships with.

WHY THIS FILE EXISTS
    The shipped defaults were Catppuccin Mocha, and they were written out
    three times: once as literals in user_settings.DEFAULT_SETTINGS, once
    as the `default` argument of every get_user_color() call in
    style_definition.py, and once as the `default:` field of the style
    editor's colour list. Three copies of ninety-nine values that had to
    agree, and they already did not - `warning` was #f9e2af in two of
    them and #fab387 in the third, so which yellow a machine showed
    depended on whether anybody had ever opened the editor.

    So this is the one place. style_definition.get_user_color() falls
    back to COLORS below, user_settings.DEFAULT_SETTINGS takes its
    "colors" section from it, and neither carries a hex literal of its
    own any more.

WHAT IS BRAND AND WHAT IS DERIVED
    BRAND holds the six values that come out of ZeptronIT's own design
    files and nothing else. They are not ours to adjust: the petrol below
    is the exact background of Design/ZeptronIT_Wallpaper.png, measured
    rather than transcribed.

    Everything under it is DERIVED, and every derivation is a contrast
    decision rather than taste. WCAG 2.1 asks 4.5:1 for body text, and
    the brand's own colours do not all reach it:

        #FFCB00 yellow  on petrol   7.77:1   AAA - yellow on petrol is
                                             the strongest pair we have
        #0096C0 cyan    on petrol   3.45:1   FAILS as text
        #214F59 shade 1 on petrol   1.31:1   a surface, never a text
                                             colour

    The cyan is the one that matters: it is the brand's primary accent
    and it cannot be read as text on the brand's own background. So
    CYAN_TEXT is that cyan lightened until it passes (6.04:1 on petrol,
    4.61:1 on the lightest surface), and the untouched #0096C0 stays for
    borders, indicators and fills - things that are seen and not read.
    A bar nobody can read is worse than one in the wrong colours.

    Every pair this file produces is checked by
    tests/src/test_brand.py, which recomputes the ratios rather than
    trusting the numbers written here.

WHAT IS DELIBERATELY NOT ON THE BRAND
    success, critical and error. Green means "fine" and red means "not
    fine" to everybody who has ever used a computer, and a distribution
    that recoloured its failure states to the company's cyan would be
    hiding failures to look tidy. They are brand-HARMONISED instead -
    the green leans teal, the red is warm rather than crimson - and both
    are lightened until they pass on petrol.

CHANGING ANY OF IT
    All of it is a default and every key is a setting. `zepos-settings
    set colors.<key> "#rrggbb"`, or the style editor. That is what the
    settings layer is for, and shipping a brand is not the same as
    imposing one.
"""
from __future__ import annotations

# =============================================================================
# THE BRAND - ZeptronIT's own values, from Design/ on the company drive
# =============================================================================
PETROL = "#0D3D47"   # the wallpaper's background, measured off the PNG
CYAN = "#0096C0"     # the primary accent
YELLOW = "#FFCB00"   # the highlight
SHADE_1 = "#214F59"  # the three petrol shades, darkest first
SHADE_2 = "#2F728A"
SHADE_3 = "#3B88A5"

BRAND = {
    "petrol": PETROL,
    "cyan": CYAN,
    "yellow": YELLOW,
    "shade_1": SHADE_1,
    "shade_2": SHADE_2,
    "shade_3": SHADE_3,
}

# =============================================================================
# DERIVED - each of these exists because a brand value could not do the job
# =============================================================================

# Below the petrol. Panels that sit ON the desktop go darker than the
# desktop itself, or they read as a hole in it rather than a surface over
# it - and the desktop IS petrol, because the wallpaper is.
INK = "#08262C"

# Between the two, for a row that is being hovered or selected.
INK_HOVER = "#10333B"

# Body text. 9.90:1 on petrol, 13.28:1 on ink, 7.55:1 on SHADE_1 - AAA
# on all three. A light tint of the brand rather than white, so that the
# desktop does not go grey the moment anything says anything.
TEXT = "#DCEEF4"

# Secondary text: weekday names, units, the half of a label that is not
# the value. 6.57:1 on petrol and 5.01:1 on SHADE_1, so it is still text
# and not decoration.
TEXT_DIM = "#A9C6CF"

# Text that is switched off - a module with nothing to report, a VPN that
# is not connected. 5.12:1 on petrol. Dimmer than TEXT_DIM to the eye and
# still over the line.
TEXT_MUTED = "#8FB0BA"

# THE ONE THAT MATTERS. #0096C0 is 3.45:1 on petrol and may not be read
# as text; this is the same hue lightened to 6.04:1 (4.61:1 on SHADE_1).
# Everywhere a template says `color:` and means "the brand accent", it
# means this one.
CYAN_TEXT = "#33C9EE"
CYAN_BRIGHT = "#66D9FF"  # its hover state, 9.77:1 on ink
CYAN_DIM = "#2AB7DC"     # and its pressed/disabled state, 6.73:1 on ink
# CYAN_SOFT = "#7FDCF2" stand hier - "a second cyan, so two neighbouring
# modules are still two modules". Es hatte genau einen Leser, bar_bluetooth,
# und der ist am 12.08.2026 mit den uebrigen Ruhefarben der Leiste
# entfallen. Zwei benachbarte Module unterscheidet jetzt ihr Zeichen und
# nicht ihre Farbe - und das war ohnehin der einzige Unterschied, den ein
# Farbton von 191.5 gegen einen von 191.9 herstellen konnte.

# Semantic, harmonised, and measured. See the module docstring for why
# these are not on the brand.
GREEN = "#57D9A3"        # 6.68:1 on petrol
GREEN_DIM = "#3FB58C"    # 4.62:1 on petrol
RED = "#FF8A8A"          # 5.21:1 on petrol - the red that is READ
RED_DEEP = "#FF5C5C"     # 3.91:1 - borders and fills only, never text
YELLOW_DIM = "#C79E00"   # the brand yellow, darkened, for a filled shape

# Backgrounds for the three hardware states. Each is its own status hue
# taken almost to black, so the status colour on top clears 4.5:1
# without the row shouting: 8.42:1, 6.80:1 and 5.86:1 respectively.
STATE_WARNING_BG = "#3D3100"
STATE_CRITICAL_BG = "#3D1A1A"
STATE_OFFLINE_BG = "#16323A"

# The grid overlay, which is drawn on its own black-ish canvas rather
# than on the desktop. Three of its four colours ARE surfaces named
# above - the canvas is the ink, the lines are the first shade, the
# outline is the third - and they are written out that way in
# COLOR_FIELDS below rather than as three aliases here. An alias would
# be a second name for a value a theme replaces, and src/theme.py would
# then have to decide which of the two names it swaps.
FOOTPRINT_BG = "#0A2F37"

# The edge of a progress bar that has not filled yet. SHADE_3 is the
# shade that WOULD be right and measures 2.96:1 on the petrol, under the
# 3:1 WCAG 1.4.11 asks of a control's visual boundary - so this is that
# shade lightened to 3.56:1. Without it the countdown bar in both boot
# menus has no extent until it starts emptying, and a bar that appears
# out of nowhere cannot be read as a bar.
#
# It lives here rather than only at the edges because it is the one
# value the two boot menus and the installer share that the centre did
# not hold: it was written into iso/profile-release/grub/themes/zepos/
# theme.txt and installer/gui/branding.py and nowhere else, so the two
# copies had nothing to be checked against.
TRACK_EDGE = "#4197B6"

# =============================================================================
# GLASS - how much of the wallpaper a surface lets through
# =============================================================================
# REPORTED on 11.08.2026: "vlt. muessen wir das os auch ein bisschen
# umstylen damit wir diesen glasmorphism effekt haben koennen".
#
# These are opacities and not colours, and they live here anyway: the
# thing they decide is a colour - what a pixel of the bar actually IS
# once the wallpaper has been mixed into it - and the number that limits
# them is a contrast ratio, which is what the rest of this file is about.
# In a stylesheet they would be the next dead knob: a glass effect nobody
# can adjust from the centre.
#
# WHY TWO AND NOT ONE
#     Text on glass is the reason most glass looks bad: contrast is
#     computed against a background, and the background is now partly the
#     wallpaper, which is arbitrary. The way out is not a single very
#     opaque layer - that is not glass any more - but TWO layers, which
#     is also how the model this look comes from is built: chips on a
#     slab.
#
#       PANEL  the slab. Carries no text of its own, so nothing has to
#              stay legible against it. This is where the effect lives.
#       CHIP   the modules on it. These carry the text, and they sit ON
#              the panel, so what is behind a chip is panel-over-wallpaper
#              and not wallpaper.
#
#     The two alphas stack: a 0.70 chip on a 0.55 panel puts
#     0.70 + 0.30*0.55 = 0.865 of coloured material between the text and
#     the wallpaper, while the panel next to it still shows 45 % of it.
#
# MEASURED, NOT CHOSEN - THE WORST CASE
#     The worst case for light text is the BRIGHTEST conceivable
#     wallpaper under the THINNEST part of the stack: pure white behind
#     everything. Composited that way, with the shipped colours - text
#     TEXT #DCEEF4 on a chip of PETROL on a panel of SHADE_1:
#
#         panel  chip   contrast
#         0.40   0.60     4.62:1   the floor, and too close to it
#         0.55   0.70     6.33:1   shipped
#         0.55   1.00     7.37:1   what an opaque chip would buy
#
#     WCAG 2.1 asks 4.5:1 for body text. 6.33:1 leaves 41 % of headroom,
#     which is what a user-changed module colour has to eat through
#     before text becomes unreadable. tests/src/test_glass.py recomputes
#     this from brand.py itself and falls over if a colour change spends
#     the headroom.
#
#     For comparison, the same text on the same chip with NO wallpaper
#     showing through is 9.90:1. Glass costs about a third of the
#     contrast, and that third is what is being budgeted here.
GLASS_PANEL_ALPHA = 0.55
GLASS_CHIP_ALPHA = 0.70

# THE THIRD ONE: a plate that stands ALONE on the wallpaper.
#
# WARUM ES SIE BRAUCHT, GEMESSEN AM 12.08.2026
#     Die zwei Deckkraefte darueber beschreiben einen Aufbau aus ZWEI
#     Schichten - Kachel auf Platte -, und genau so ist die Leiste
#     gebaut. Jede ANDERE Flaeche dieses Projekts ist einschichtig: die
#     Ueberlagerungen malen `.overlay-outer` und schreiben ihren Text
#     direkt darauf, die Meldung malt `.notif-card`, der Starter
#     `.launcher-container`. Unter dem Text liegt dort nur EINE Schicht
#     und dann die Tapete.
#
#     `grep -rn "GLASS" src/styles/ src/templates/` fand am 12.08.2026
#     zwei Treffer, beide in bar-style.template. Die anderen zwoelf
#     Flaechen, die in GLASS_LAYERS stehen und vom Compositor eine
#     Unschaerfe angefordert bekommen, malten DECKEND: `background: $bg`
#     mit $bg = INK, also ein sechsstelliges Hex ohne Alphakanal. Der
#     Effekt wurde dreizehnmal gerechnet und einmal gesehen.
#
# ABGELEITET UND NICHT GEWAEHLT
#     Eine einschichtige Platte muss so viel Material zwischen Text und
#     Tapete legen wie der zweischichtige Aufbau der Leiste, denn es ist
#     DERSELBE Text, der darauf gelesen werden muss. Zwei Schichten
#     stapeln sich zu
#
#         chip + (1 - chip) * panel = 0.70 + 0.30 * 0.55 = 0.865
#
#     und das ist diese Zahl. Sie kann deshalb nicht driften, wenn
#     jemand oben eine der beiden verstellt - dieselbe Bauart wie
#     GLASS_IGNORE_ALPHA weiter unten.
#
# GEMESSEN, DER SCHLECHTESTE FALL - hellste bzw. dunkelste denkbare
# Tapete unter der Platte, beide Themen, WCAG 2.1 verlangt 4.5:1:
#
#         Farbe auf der Platte              0.70    0.86   deckend
#         TEXT auf INK                      5.00    8.64    13.28
#         TEXT_DIM auf INK                  3.32    5.42     7.46
#         CYAN_TEXT auf INK                 3.05    5.19     8.81
#         TEXT_DIM auf STATE_CRITICAL_BG    3.26    4.93     5.93
#         TEXT auf PETROL (das Dock)        4.05    6.53     9.90
#
#     Die Kachel-Deckkraft allein - die naheliegende Wahl - faellt in
#     VIER von fuenf Zeilen durch. Das ist der Grund, aus dem hier eine
#     dritte Zahl steht und nicht GLASS_CHIP_ALPHA wiederverwendet wird.
#
#     Die duennste Stelle nach der Umstellung ist TEXT_DIM auf dem
#     kritischen Grund mit 4.93:1, also 9 % ueber der Linie.
#     tests/src/test_glass.py rechnet jede dieser Zeilen aus dieser Datei
#     nach, ueber jedes Thema und beide Extreme.
#
# WAS HIER NICHT MEHR HINPASST, UND DAS IST EINE MESSUNG
#     brand.RED auf STATE_CRITICAL_BG kommt unter dieser Platte auf
#     4.33:1 und faellt durch. Die drei Zustandsgruende sind gegen einen
#     DECKENDEN Grund gerechnet (6.80:1); unter Glas bleibt davon nicht
#     genug. Die kritische Meldung traegt ihre Schrift deshalb weiter in
#     TEXT und nicht im Rot - das Rot steht an ihrem Rand, wo 3:1 nach
#     WCAG 1.4.11 genuegt und wo es mit 4.33:1 mehr als reicht.
#
# EINE FUNKTION UND KEINE KONSTANTE, UND DAS IST GEMESSEN
#     Der erste Anlauf schrieb hier `GLASS_SOLO_ALPHA = round(...)` und
#     dieselbe Zeile noch einmal in Palette.__init__, weil ein Thema
#     seine eigenen zwei Deckkraefte hat. Zwei Kopien einer Rechnung,
#     und die hier hatte damit KEINEN Leser: alles im Baum geht ueber
#     THEME.
#
#     Aufgefallen ist es der Mutationspruefung am 12.08.2026 - die
#     Konstante wurde auf GLASS_CHIP_ALPHA gesetzt, und die ganze
#     Glaspruefung blieb gruen. Ein Wert, den man verstellen kann, ohne
#     dass sich etwas bewegt, ist genau der tote Regler, gegen den
#     dieses Projekt schon einmal angetreten ist.
def glass_solo_alpha(panel: float, chip: float) -> float:
    """Die Deckkraft einer einschichtigen Platte, aus den zweien der
    Leiste."""
    return round(chip + (1 - chip) * panel, 2)

# THE LOCK SCREEN'S SCRIM - the opposite job, and therefore its own number.
#
# REPORTED on 12.08.2026: "sorge dafuer das der login auch wirklich
# modern aussieht vgl. apple os login ja ?". One of the things that
# makes that look work is that the picture carries the screen - there is
# no card, the text sits directly on the backdrop. Which only works as
# long as the text stays readable on it.
#
# WHY THE GLASS NUMBERS ABOVE CANNOT BE REUSED
#     They are computed against pure white, because the bar sits on the
#     USER'S wallpaper and that can be anything. The lock screen sits on
#     zepos-backdrop.png, which the package owns - so the worst case is
#     not "any picture", it is "the brightest pixel of THAT picture", and
#     assuming white here would buy a scrim so heavy the picture would be
#     gone. That is the whole difference between a wallpaper and an
#     asset.
#
# MEASURED, ON THE FILE ITSELF
#     `magick identify -verbose src/branding/zepos-backdrop.png` on
#     12.08.2026: the per-channel maxima are r=31 g=74 b=83, and the mean
#     is (11, 53, 61). It is a dark, calm petrol image - which is why the
#     scrim can be thin.
#
#     Contrast of every colour this screen paints on text, against that
#     brightest pixel, composited under a scrim of INK:
#
#         scrim   TEXT  TEXT_DIM  CYAN_TEXT  YELLOW   RED    worst
#         0.00    8.13    5.39      4.96      6.38    4.28   4.28  FAILS
#         0.25    9.28    6.16      5.66      7.28    4.88   4.88
#         0.35    9.77    6.48      5.96      7.67    5.14   5.14  shipped
#
#     WCAG 2.1 asks 4.5:1 for body text. Without a scrim the failure
#     message - brand.RED, the one colour that has to be read at the
#     worst moment - lands at 4.28:1 and misses. That is what this value
#     is for, and it is the reason it is not zero.
#
#     0.35 clears it by 14 % and still lets 65 % of the picture through.
#     tests/lock/test_style.py recomputes all of it from this file and
#     from the PNG - including the counter-probe that a scrim of 0 would
#     fail - so a brighter backdrop or a changed colour cannot spend the
#     headroom unnoticed.
LOCK_SCRIM_ALPHA = 0.35

# The alpha below which Hyprland must NOT blur - `layerrule = ignorealpha`.
#
# WHAT IT IS FOR
#     Blur is applied to the whole layer surface, including the parts of
#     it that are fully transparent: the margin the panel keeps to the
#     screen edge, and everything outside its rounded corners. Without a
#     threshold the compositor blurs a RECTANGLE, and the blur is visible
#     beyond the panel it belongs to - a soft grey box around a rounded
#     slab, which is the single most common way this effect is got wrong.
#
# DERIVED AND NOT GUESSED
#     It has to sit strictly between "nothing" and the thinnest glass we
#     actually paint, or it either blurs the empty margin (too low, at 0)
#     or stops blurring the panel itself (too high, at or above
#     GLASS_PANEL_ALPHA). Half of the thinnest layer is the midpoint of
#     that interval, so it is as far from both failures as it can be -
#     and because it is computed, it cannot drift when the alphas above
#     are changed.
#
#     The antialiased pixels of a rounded corner ramp from 0 to
#     GLASS_PANEL_ALPHA; the threshold cuts that ramp in half, so the
#     blur ends inside the corner instead of squaring it off.
#
#     Eine Funktion aus demselben Grund wie glass_solo_alpha() darueber:
#     ein Thema bringt seine eigene Panel-Deckkraft mit, und eine
#     Konstante hier haette dieselbe Rechnung ein zweites Mal in
#     Palette.__init__ stehen lassen - ohne Leser und ohne dass eine
#     Mutation davon etwas bewegt haette.
def glass_ignore_alpha(panel: float) -> float:
    """Die Schwelle, unter der Hyprland nicht verwischen darf."""
    return round(panel / 2, 2)


def rgba(colour: str, alpha: float) -> str:
    """A brand colour as a CSS rgba(), for the surfaces that are glass.

    A function and not a table of pre-mixed strings: the alphas above are
    two and the colours they are applied to are user-settable, so a table
    would have to be rebuilt whenever either end moves. GTK4 has its own
    `alpha()` in CSS and it is deliberately not used - it takes a named
    colour, and these come out of a placeholder as a literal `#RRGGBB`.
    """
    value = colour.lstrip("#")
    channels = ", ".join(str(int(value[index:index + 2], 16))
                         for index in (0, 2, 4))
    return f"rgba({channels}, {alpha})"


# =============================================================================
# THE CODE PALETTE - "Terminal Green", a named theme and not the chrome
# =============================================================================
# WHY THERE IS A SECOND PALETTE AT ALL
#     Everything above dresses the DESKTOP: the bar, the overlays, the
#     power menu, the boot menu. This dresses a DOCUMENT - the syntax of
#     a file open in an editor - and the two are not the same job. A
#     desktop should look like one product, which is why the rest of this
#     file exists; a syntax theme is something a person chooses, the way
#     they choose a font size, and the one shipped here is green on black
#     because that is what "Terminal Green" is.
#
#     It is written out as src/styles/terminal-green-style.template ->
#     "Terminal Green.sublime-color-scheme", which the editor finds BY
#     THAT NAME out of its own preferences. Recolouring it to the petrol
#     would leave a theme called Terminal Green that is not green, and
#     renaming it would silently break the preference that names it. So
#     it stays green, and it stays HERE rather than as eleven literals in
#     a template nothing checks.
#
# WHAT IS NOT IN HERE
#     wofi and wlogout - the launcher and the logout menu that
#     zepos-menu and zepos-logout replaced - used to carry a verbatim
#     copy of these eleven values and were dressed as a terminal because
#     kitty once was.
#     kitty's own chrome moved to the brand in e1e21cd - its background
#     is INK #08262C now, not #0c0c0c - so the copies were matching a
#     look that no longer existed anywhere. They are desktop chrome and
#     they are on the brand now; this palette has one consumer.
#
# CONTRAST, AND THE TWO VALUES THAT MOVED
#     Measured on CODE_BG and on CODE_BG_RAISED, which is the highlighted
#     line the cursor sits on and therefore the stricter of the two:
#
#         green        14.26 / 12.68    white   15.67 / 13.94
#         green_dark    8.98 /  7.99    red      5.38 /  4.78
#         green_light  14.43 / 12.84    yellow  18.26 / 16.25
#
#     Two failed in roles that are TEXT and are lightened here, in the
#     same way and for the same reason CYAN became CYAN_TEXT above -
#     same hue, same saturation, raised until it clears 4.5:1 on both
#     grounds:
#
#         comments  #808080 -> #838383   4.95/4.41 became 5.16/4.59
#         links     #3366ff -> #4D79FF   4.18/3.72 became 5.12/4.55
#
#     CODE_GUIDE is deliberately NOT among them. At 1.89:1 it would fail
#     any text threshold and it is not text: it is the indent guide and
#     the selection FILL, a shape behind characters that keep their own
#     colour. Lightening it would put a grey bar through the code.
CODE_BG = "#0c0c0c"            # the editor canvas
CODE_BG_RAISED = "#1a1a1a"     # the line the cursor is on, and find-bars
CODE_GREEN = "#00ff00"         # keywords, storage, types - the theme itself
CODE_GREEN_DIM = "#00cc00"     # the second rank: support functions, borders
CODE_GREEN_BRIGHT = "#33ff33"  # strings, numbers, function names, the caret
CODE_TEXT = "#e6e6e6"          # plain identifiers, which are not syntax
CODE_COMMENT = "#838383"       # prose inside code, dimmer than the code
CODE_GUIDE = "#404040"         # indent guides and the selection fill - a
                               # SHAPE, never a text colour, see above
CODE_RED = "#ff3333"           # invalid, and a deleted line in a diff
CODE_YELLOW = "#ffff33"        # the background of something deprecated
CODE_BLUE = "#4D79FF"          # links in markup, the one non-green accent
CODE_SELECTION_DIM = "#1a3d1a"  # the selection where focus has moved away:
                                # the green taken almost to the canvas, so
                                # it is still visibly a selection

# =============================================================================
# FONTS
# =============================================================================
# Two families, because ZeptronIT has two: Fira Code for anything that is
# code or is aligned like code, Roboto for anything that is prose.
#
# The Nerd Font stays in the CSS list behind Fira Code, and that is not a
# leftover: every glyph in src/icon_definition.py is a Nerd Font
# codepoint, Fira Code does not carry one of them, and a bar whose font
# list named only Fira Code would draw the whole of Waybar's iconography
# as tofu. Fontconfig takes the first family that HAS the glyph, per
# glyph - so the text is Fira Code and the icons are the Nerd Font,
# which is exactly the arrangement wanted.
FONT_CODE = "Fira Code"
FONT_TEXT = "Roboto"
FONT_ICONS = "JetBrainsMono Nerd Font"


# Die zwei Listen als FUNKTIONEN der Familie, seit es Themen gibt
# (12.08.2026). Ein Thema tauscht FONT_CODE und FONT_TEXT aus; die
# Regel darum herum - Nerd Font dahinter, weil sonst jedes Symbol Tofu
# waere - gehoert nicht dem Thema, sondern dieser Datei. Waeren die
# fertigen Listen weiterhin Konstanten, muesste src/theme.py sie
# nachbauen, und die Begruendung darueber staende dann an einer Liste,
# die niemand liest.
def font_family_code(family: str) -> str:
    return (f'"{family}", "{FONT_ICONS}", '
            '"Font Awesome 6 Free", "Font Awesome 6 Brands", monospace')


def font_family_text(family: str) -> str:
    return f'"{family}", "{FONT_ICONS}", sans-serif'


FONT_FAMILY_CODE = font_family_code(FONT_CODE)
FONT_FAMILY_TEXT = font_family_text(FONT_TEXT)

# =============================================================================
# ASSETS
# =============================================================================
# Installed by packaging/zepos-config out of src/branding/. Named here
# because the generator has to write the path into wallpaper-manager, and
# a template may not carry a system path of its own
# (tests/src/test_naming.py::test_no_artifact_defaults_the_system_root_to_a_guess).
WALLPAPER_FILE = "zepos-wallpaper.png"
LOGO_FILE = "zepos-logo.svg"
LOGO_PNG_FILE = "zepos-logo.png"

# Das Bild hinter jeder Maske, die vor der Sitzung steht: der Assistent,
# die Anmeldung - und seit dem 12.08.2026 der Sperrbildschirm.
#
# Es ist dieselbe Datei, die src/login/regreet.toml unter
# /usr/share/zepos/branding/zepos-backdrop.png nennt; packaging/
# zepos-config legt src/branding/ genau dorthin, und der Sperrbildschirm
# ist auf einer Installation mit dem Schreibtisch da, also auch das Bild.
# Der Name steht hier aus demselben Grund wie die zwei darueber: die
# Stilvorlage setzt ihn hinter {{ZEPOS_SYSTEM_ROOT}} ein und darf keinen
# Systempfad von sich aus tragen.
#
# Fehlt die Datei doch, zeichnet GTK4 die background-image-Regel
# einfach nicht und die Farbe darunter bleibt stehen. Ein
# Sperrbildschirm ohne Bild ist eine Sperre; das ist der Grund, aus dem
# das Bild und nicht die Farbe die Zugabe ist.
BACKDROP_FILE = "zepos-backdrop.png"

# =============================================================================
# EVERY COLOUR ZepOS HAS
# =============================================================================
# The keys are the settings keys. style_definition.get_user_color(key)
# answers from the user's settings file first and from the ACTIVE
# THEME's resolution of this table otherwise, and raises on a key that
# is in neither - so a typo is a failed generation rather than a colour
# that silently stays Catppuccin.
#
# WARUM HIER SEIT DEM 12.08.2026 FELDNAMEN STEHEN UND KEINE FARBEN
#     Weil eine Rolle und ein Wert zwei verschiedene Dinge sind, und
#     erst seit es ein zweites Thema gibt, faellt der Unterschied auf:
#     "success" IST nicht #57D9A3, sondern "das Gruen dieses Themas".
#     Stuende hier weiterhin die Konstante GREEN, waere diese Tabelle
#     an das ausgelieferte Thema gebunden und ein zweites koennte sie
#     nur ersetzen - also eine zweite Tabelle mit siebzig Zeilen, die
#     mit dieser uebereinstimmen muesste. Der Kopf dieser Datei
#     erzaehlt, was drei solche Kopien gekostet haben.
#
#     COLORS darunter loest sie fuer das AUSGELIEFERTE Thema auf und
#     hat damit genau die Form und die Werte, die es vorher hatte -
#     jeder Leser (user_settings.DEFAULT_SETTINGS, der Stil-Editor,
#     tests/src/test_brand.py) bleibt unveraendert. theme.Palette loest
#     dieselbe Tabelle fuer das eingestellte Thema auf.
COLOR_FIELDS: dict[str, str] = {
    # -- Status ------------------------------------------------------
    "success": "GREEN",
    "success_dim": "GREEN_DIM",
    "warning": "YELLOW",
    "critical": "RED",
    # Not read as text anywhere today; kept distinct from `critical`
    # because a border and a label are two different things.
    "inactive": "TEXT_MUTED",

    # -- Accents -----------------------------------------------------
    "accent": "CYAN_TEXT",

    # -- Die Leiste --------------------------------------------------
    # Every one of these is a foreground on `background` below, at
    # GLASS_CHIP_ALPHA over GLASS_PANEL_ALPHA over the wallpaper - and
    # the wallpaper's own background IS petrol, so the composited colour
    # is petrol wherever the dots are not. That is the reason
    # `background` is the brand petrol and not something darker: it
    # makes the number the contrast was computed against the number that
    # is actually on the screen. What happens when the wallpaper is NOT
    # petrol - a picture, or someone else's - is the worst case computed
    # under GLASS above.
    # DIE EINE FARBE, DIE DIE LEISTE IM RUHEZUSTAND TRAEGT.
    #
    # Hier standen acht weitere - bar_date, bar_weather, bar_network,
    # bar_bluetooth, bar_battery, bar_audio, bar_microphone und
    # bar_workspace -, also acht Regler fuer den Ruhezustand von acht
    # Modulen. Sie sind am 12.08.2026 entfallen, nachdem der Nutzer die
    # Leiste auf echter Hardware gesehen hatte: "die icons im header
    # sollen auch nicht alle zepdesk farben tragen weil es sonst voll
    # monoton aussieht".
    #
    # Die Messung steht im Kopf von src/styles/bar-style.template. Ihr
    # Kern in einer Zeile: bar_date war YELLOW und `warning` ist YELLOW,
    # bar_battery war GREEN und `success` ist GREEN - die Zustandsfarben
    # waren von den Ruhefarben nicht zu unterscheiden, weil die
    # Ruhefarben sie schon benutzten. Empty workspaces werden bei
    # STYLE_OPACITY_DISABLED (0.6) gezeichnet und kommen von diesem Wert
    # aus auf 4.62:1; TEXT_DIM laege bei 3.39:1 - die Deckkraft gehoert
    # hier zur Farbe.
    "bar_text": "TEXT",
    # Der sichtbare Arbeitsbereich ist ein ZUSTAND und behaelt deshalb
    # seine Farbe.
    "bar_workspace_visible": "YELLOW",
    "bar_tray": "SHADE_1",

    # -- Hyprland window bars ----------------------------------------
    # Borders and buttons, seen and not read, so the untouched brand
    # cyan belongs here.
    "hyprland_active_border": "CYAN",
    "hyprland_inactive_border": "SHADE_1",
    "hyprbar_bg": "PETROL",
    "hyprbar_text": "TEXT",
    "hyprbar_close": "RED",
    "hyprbar_minimize": "YELLOW",
    "hyprbar_maximize": "GREEN",

    # -- EWW ---------------------------------------------------------

    # -- Calendar ----------------------------------------------------

    # -- Disk and hardware -------------------------------------------

    # -- Grid overlay and wallpaper ----------------------------------
    "grid": "SHADE_1",
    "grid_bg": "INK",
    "footprint": "SHADE_3",
    "footprint_bg": "FOOTPRINT_BG",
    "footprint_text": "TEXT_DIM",
    "wallpaper_landscape": "CYAN_TEXT",

    # -- Terminal (kitty) --------------------------------------------
    "terminal_bg": "INK",
    "terminal_fg": "TEXT",
    "terminal_cursor": "YELLOW",
    "terminal_selection": "SHADE_1",
    # The active tab is the brand yellow with the ink on top: 10.42:1,
    # and the one place the two brand colours meet at full strength.
    "terminal_active_tab_fg": "INK",
    "terminal_active_tab_bg": "YELLOW",
    "terminal_inactive_tab_fg": "TEXT_DIM",
    "terminal_inactive_tab_bg": "INK_HOVER",

    # -- Die Eingabezeile (powerlevel10k) ----------------------------
    #
    # WARUM SIEBEN ROLLEN UND KEINE EINZIGE NEUE FARBE
    #     Ein Prompt hat sieben Dinge zu sagen - wo bin ich, was macht
    #     das Repository, hat der letzte Befehl geklappt -, und jede
    #     dieser Aussagen gibt es auf dieser Oberflaeche schon: ein
    #     Zweigname im Prompt bedeutet dasselbe wie eine gruene Zeile in
    #     der Leiste. Sieben FELDER dafuer waeren eine zweite Palette
    #     gewesen, die zufaellig genauso aussieht wie die erste - und
    #     genau das ist der Zustand, mit dessen Beseitigung der Kopf
    #     dieser Datei anfaengt.
    #
    #     Rollen und keine Literale, weil die Eingabezeile trotzdem
    #     EINSTELLBAR sein muss: wer sein Gruen im Prompt anders will,
    #     stellt `prompt_vcs_clean` und nicht `overlay_green` um.
    #
    # WORAUF DAS GEMESSEN IST
    #     Auf terminal_bg, und das ist INK - der Prompt sitzt im
    #     Terminal und nirgendwo sonst. Jede Farbe hier steht deshalb in
    #     ON_INK in tests/src/test_brand.py, gerechnet gegen BEIDE
    #     Themen. Die zwei engsten am 12.08.2026: GREEN auf dem hellen
    #     Grund 5.68:1, TEXT_MUTED dort 5.40:1.
    "prompt_path": "CYAN_TEXT",
    "prompt_vcs_clean": "GREEN",
    "prompt_vcs_dirty": "YELLOW",
    "prompt_ok": "GREEN",
    "prompt_error": "RED",
    "prompt_context": "TEXT_DIM",
    "prompt_time": "TEXT_MUTED",

    # -- Notifications (mako) ----------------------------------------
    # mako-config.template appends DD and AA to the background and the
    # border, so every value here must stay a six-digit hex.
    "notification_bg": "INK",
    "notification_text": "TEXT",
    "notification_border": "CYAN",
    "notification_progress": "CYAN_TEXT",
    "notification_low_text": "TEXT_DIM",
    "notification_low_border": "SHADE_1",
    "notification_critical_text": "RED",
    "notification_critical_border": "RED_DEEP",

    # -- nwg-dock ----------------------------------------------------
    "dock_icon": "TEXT",
    "dock_indicator": "YELLOW",

    # -- AGS overlays ------------------------------------------------
    # Two levels, ink underneath and petrol on top, so a widget's header
    # is visibly a header. $accent is used as a TEXT colour in
    # ags-style.template, which is why it is CYAN_TEXT and not CYAN.
    "overlay_bg": "INK",
    "overlay_surface": "PETROL",
    "overlay_text": "TEXT",
    "overlay_subtext": "TEXT_DIM",
    "overlay_accent": "CYAN_TEXT",
    "overlay_accent_hover": "CYAN_BRIGHT",
    "overlay_accent_dim": "CYAN_DIM",
    "overlay_item_hover": "INK_HOVER",
    "overlay_border": "SHADE_1",
    "overlay_green": "GREEN",

    # -- Per-widget accents ------------------------------------------
    # All the same value, and they are ten keys rather than one so that
    # somebody can tell their calendar from their launcher. A user who
    # sets `overlay_accent` alone still moves all ten: each of these
    # falls back to it before it falls back to here.
    "launcher_accent": "CYAN_TEXT",
    "calendar_accent": "CYAN_TEXT",
    "shortcuts_accent": "CYAN_TEXT",
    "battery_accent": "CYAN_TEXT",
    "disk_accent": "CYAN_TEXT",
    "control_accent": "CYAN_TEXT",
    "network_accent": "CYAN_TEXT",
    "wallpaper_accent": "CYAN_TEXT",
    "style_accent": "CYAN_TEXT",
    "vpn_accent": "CYAN_TEXT",

    # -- VPN module --------------------------------------------------
    "vpn_connecting": "YELLOW",

    # -- The module background --------------------------------------
    # Last because everything above is read against it.
    #
    # Named after no widget, and older than the ones that are.
    # "background" is read - it is STYLE_BG_COLOR, the Waybar modules'
    # background and the grid wallpaper's backdrop. A key called "border"
    # used to stand beside it and was read by nothing: STYLE_BORDER_COLOR
    # is a literal (brand.SHADE_1 now) and a different colour, so
    # offering the key promised a control over a value it could not
    # reach. A user's own stored "border" is untouched - load_settings()
    # keeps whatever the file says; this is only what a fresh file gets.
    "background": "PETROL",
}

# Dieselbe Tabelle, aufgeloest fuer das AUSGELIEFERTE Thema.
#
# Sie ist das, was COLORS immer war - siebzig Schluessel auf siebzig
# Hexwerte -, nur nicht mehr abgeschrieben, sondern gerechnet. Wer sie
# fuer ein anderes Thema braucht, nimmt theme.Palette.COLORS; wer die
# Vorgabe meint (user_settings.DEFAULT_SETTINGS, "zuruecksetzen" in der
# Einstellungs-Anwendung), meint diese hier.
COLORS: dict[str, str] = {
    role: globals()[field] for role, field in COLOR_FIELDS.items()
}

# =============================================================================
# WIE DIE NEUNUNDNEUNZIG EINEM MENSCHEN VORGELEGT WERDEN
# =============================================================================
# Die Tabelle darueber sagt, welche Farbe ein Schluessel HAT. Diese hier
# sagt, wie er HEISST, wenn ihn jemand einstellen soll, und neben welchen
# er dabei steht. Das sind zwei verschiedene Fragen, und deshalb sind es
# zwei Tabellen - aber nur EINE Liste von Schluesseln: der Test dazu
# haelt beide gegeneinander und faellt um, sobald ein Schluessel in der
# einen steht und in der anderen nicht.
#
# WARUM DAS HIER STEHT UND NICHT IN DER OBERFLAECHE, DIE ES ZEIGT
#     Weil es zwei Oberflaechen sind. Der Stil-Editor im Schreibtisch
#     (src/templates/ags-style-editor.template, GJS) trug diese
#     Gruppierung bis zum 12.08.2026 als Literal - dreizehn Gruppen,
#     fuenfundneunzig Zeilen -, und die Einstellungs-Anwendung
#     (settings/, GTK4) braucht dieselbe. Zwei Kopien einer Liste von
#     fuenfundneunzig Namen sind zwei Listen, die auseinanderlaufen,
#     sobald jemand eine davon anfasst; genau das ist diesem Projekt mit
#     den DREI Kopien der Vorgabefarben schon passiert, und der Kopf
#     dieser Datei erzaehlt, was es gekostet hat.
#
#     Der Editor liest sie jetzt als {{STYLE_COLOR_GROUPS_JSON}}, die
#     Anwendung importiert dieses Modul. Eine Liste, zwei Leser.
#
# WARUM JEDER SCHLUESSEL VORKOMMEN MUSS
#     Vier taten es bisher nicht: background, overlay_accent_dim, vpn und
#     vpn_connecting. GEMESSEN am 12.08.2026 am Literal des Editors -
#     fuenfundneunzig von neunundneunzig. Sie waren nicht abgelehnt,
#     sondern vergessen: es gibt keinen Grund, aus dem man die Farbe
#     einer verbindenden VPN-Anzeige nicht soll einstellen duerfen, und
#     `background` ist die Flaeche, gegen die jede andere gelesen wird.
#     Eine Farbe, die es gibt und die keine Oberflaeche zeigt, ist nur
#     ueber das Editieren der JSON-Datei erreichbar - also fuer niemanden.
#
#     Der Test verlangt deshalb Vollstaendigkeit in BEIDE Richtungen.
#     Wer eine Farbe hinzufuegt, gibt ihr hier einen Namen, oder die
#     Suite geht nicht mehr durch.
#
# UND WARUM ES JETZT SIEBZIG SIND UND NICHT MEHR NEUNUNDNEUNZIG
#     Weil neunundzwanzig davon nichts taten.
#
#     GEMESSEN am 12.08.2026, als diese Tabelle fuer die
#     Einstellungs-Anwendung gebraucht wurde: jede Farbe einzeln auf
#     einen Sentinel gesetzt, style_definition.py damit neu eingelesen,
#     und nachgesehen, welcher {{STYLE_*}}-Platzhalter sich bewegt und
#     ob irgendeine Vorlage ihn nennt. Bei diesen neunundzwanzig nennt
#     ihn keine:
#
#       accent_secondary bar_bg bar_workspace_active
#       calendar_bg calendar_day calendar_header calendar_selected
#       calendar_today calendar_weekday
#       disk_ring_bg disk_ring_used disk_text
#       dock_bg dock_icon_hover error
#       eww_bg eww_border eww_button eww_button_text eww_hover
#       eww_progress_bg eww_progress_fill eww_scrollbar eww_text
#       hardware_cpu hardware_memory hardware_temp
#       vpn wallpaper_portrait
#
#     Der Stil-Editor bot sie alle an. Wer dort "Popup Hintergrund"
#     aenderte, bekam eine Bestaetigung, einen Eintrag in seiner
#     Einstellungsdatei und einen Schreibtisch, an dem sich nichts
#     geaendert hatte - dieselbe Geschichte wie MONITOR_HEIGHT_SCALES
#     und wie "fonts"/"spacing" in user_settings.py, nur mit
#     neunundzwanzig Namen statt mit vieren.
#
#     Sie sind ersatzlos geloescht, samt der dreissig Platzhalter, deren
#     einziger Leser sie waren. Ersatzlos, weil es fuer jeden von ihnen
#     bereits einen gibt, der ANKOMMT: die Ueberlagerungsfenster nehmen
#     ihre Farben aus overlay_*, die Widgets ihren Akzent aus *_accent,
#     die Leiste ihren Grund aus "background" (ueber STYLE_GLASS_PANEL
#     und STYLE_GLASS_CHIP). Und keine Migration, aus demselben Grund
#     wie bei "fonts" und "spacing": ein Wert, der nie gewirkt hat, hat
#     nichts, was gerettet werden koennte.
#
#     tests/settings/test_settings_model.py rechnet die Messung bei jedem Lauf
#     nach. Wer eine dieser Farben wieder in eine Vorlage schreibt,
#     bekommt dort einen roten Test mit der Aufforderung, sie hier
#     wieder aufzunehmen.
COLOR_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("Status", (
        ("success", "Erfolg (Akku voll, VPN steht, Abgleich fertig)"),
        ("success_dim", "Erfolg, gedaempft (aktiver Arbeitsbereich)"),
        ("warning", "Warnung (Akku niedrig, Temperatur)"),
        ("critical", "Kritisch (Akku leer, Fehler)"),
        ("inactive", "Inaktiv (Geraet aus, nichts zu melden)"),
    )),
    ("Akzente", (
        ("accent", "Primaer (Hervorhebungen, aktive Stellen)"),
    )),
    ("Ueberlagerungen", (
        ("overlay_bg", "Hintergrund"),
        ("overlay_surface", "Flaeche (Kopfzeilen, Kacheln)"),
        ("overlay_text", "Text"),
        ("overlay_subtext", "Nebentext"),
        ("overlay_accent", "Akzent"),
        ("overlay_accent_hover", "Akzent unter dem Zeiger"),
        ("overlay_accent_dim", "Akzent, gedrueckt oder abgeschaltet"),
        ("overlay_item_hover", "Zeile unter dem Zeiger"),
        ("overlay_border", "Rahmen"),
        ("overlay_green", "Verbunden / aktiv"),
    )),
    ("Akzent je Fenster", (
        ("launcher_accent", "Anwendungsstarter"),
        ("calendar_accent", "Kalender"),
        ("shortcuts_accent", "Tastenuebersicht"),
        ("battery_accent", "Akku"),
        ("disk_accent", "Datentraeger"),
        ("control_accent", "Kontrollzentrale"),
        ("network_accent", "Netzwerk"),
        ("wallpaper_accent", "Hintergrundbild"),
        ("style_accent", "Stil-Editor"),
        ("vpn_accent", "VPN"),
    )),
    ("Leiste", (
        # Zuerst, weil jede Farbe darunter gegen diese gelesen wird -
        # dieselbe Reihenfolge, in der COLORS sie begruendet, nur
        # umgedreht: dort steht sie zuletzt, weil sie alles andere
        # traegt, hier zuerst, weil man sie zuerst waehlt.
        ("background", "Modul-Hintergrund"),
        ("bar_text", "Standardtext"),
        ("bar_workspace_visible", "Arbeitsbereich, sichtbar"),
        ("bar_tray", "Statusablage"),
    )),
    ("Fenster", (
        ("hyprland_active_border", "Aktives Fenster (Rahmen)"),
        ("hyprland_inactive_border", "Inaktives Fenster (Rahmen)"),
        ("hyprbar_bg", "Titelleiste"),
        ("hyprbar_text", "Titelleiste, Text"),
        ("hyprbar_close", "Schliessen"),
        ("hyprbar_minimize", "Minimieren"),
        ("hyprbar_maximize", "Maximieren"),
    )),
    ("Raster und Hintergrundbild", (
        ("grid", "Rasterlinien"),
        ("grid_bg", "Rasterflaeche"),
        ("footprint", "Umriss"),
        ("footprint_bg", "Umriss, Flaeche"),
        ("footprint_text", "Umriss, Text"),
        ("wallpaper_landscape", "Querformat"),
    )),
    ("Terminal", (
        ("terminal_bg", "Hintergrund"),
        ("terminal_fg", "Text"),
        ("terminal_cursor", "Schreibmarke"),
        ("terminal_selection", "Auswahl"),
        ("terminal_active_tab_fg", "Aktiver Reiter, Text"),
        ("terminal_active_tab_bg", "Aktiver Reiter, Flaeche"),
        ("terminal_inactive_tab_fg", "Inaktiver Reiter, Text"),
        ("terminal_inactive_tab_bg", "Inaktiver Reiter, Flaeche"),
    )),
    # Eine eigene Gruppe und kein Anhaengsel an "Terminal": das Terminal
    # ist ein Fenster, die Eingabezeile ist das, was darin steht. Wer
    # seinen Prompt umfaerbt, will nicht die Reiterleiste treffen.
    ("Eingabezeile", (
        ("prompt_path", "Pfad"),
        ("prompt_vcs_clean", "Repository, unveraendert"),
        ("prompt_vcs_dirty", "Repository, geaendert"),
        ("prompt_ok", "Eingabezeichen nach einem gelungenen Befehl"),
        ("prompt_error", "Eingabezeichen und Fehlernummer nach einem Fehler"),
        ("prompt_context", "Benutzer und Rechner (als root, ueber SSH)"),
        ("prompt_time", "Uhrzeit und Laufzeit"),
    )),
    ("Benachrichtigungen", (
        ("notification_bg", "Hintergrund"),
        ("notification_text", "Text"),
        ("notification_border", "Rahmen"),
        ("notification_progress", "Fortschritt"),
        ("notification_low_text", "Niedrige Dringlichkeit, Text"),
        ("notification_low_border", "Niedrige Dringlichkeit, Rahmen"),
        ("notification_critical_text", "Kritisch, Text"),
        ("notification_critical_border", "Kritisch, Rahmen"),
    )),
    ("Dock", (
        ("dock_icon", "Symbol"),
        ("dock_indicator", "Anzeiger (laeuft)"),
    )),
    ("VPN", (
        ("vpn_connecting", "Verbindet gerade"),
    )),
)
