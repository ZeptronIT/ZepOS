# SPDX-License-Identifier: GPL-3.0-or-later
"""ZeptronIT's colours, fonts and logo, for the graphical installer.

WHY THE PALETTE IS WRITTEN OUT AGAIN HERE
    src/brand.py is the desktop's copy, and this file cannot import it.
    They are two packages and the direction that would help is the
    forbidden one: spec §4.2 keeps zepos-installer, -gui and -tui OFF the
    installed system, while zepos-config IS the installed system. A
    `depends=('zepos-config')` on the installer would put a desktop's
    worth of templates on the medium and the installer on every machine
    it installed.

    A copy nobody checks is a copy that drifts, so
    tests/installer/test_branding.py reads both files and fails if the
    six brand values disagree. That test is the link the import cannot
    be.

WHY libadwaita's OWN COLOUR NAMES AND NOT A STYLESHEET OF OUR OWN
    The installer is built out of Adw.PreferencesPage, Adw.EntryRow,
    Adw.HeaderBar and Adw.AlertDialog, and every one of them draws itself
    from libadwaita's named colours. Redefining those names recolours the
    whole surface, including the widgets this file has never heard of -
    which is most of them. A stylesheet that styled our own widgets by
    hand would leave every dialog, popover and toast in libadwaita's
    default purple.

CONTRAST, WHICH IS WHY SOME OF THIS IS NOT THE OBVIOUS CHOICE
    Every pair below is recomputed by tests/installer/test_branding.py
    against WCAG AA (4.5:1), and two of them decided the design:

      * The accent button is the brand cyan with INK on it, 4.63:1 -
        NOT cyan with white on it, which is 3.43:1. "Weiter" is the one
        control the entire form is driven from and its label has to be
        readable.
      * accent_color, which libadwaita uses for links and focus rings ON
        the window background, is the LIGHTENED cyan: #0096C0 on petrol
        is 3.45:1 and fails. Same brand colour, two jobs, two values.
"""
from __future__ import annotations

from pathlib import Path

# --- the brand, from ZeptronIT's design files --------------------------
PETROL = "#0D3D47"
CYAN = "#0096C0"
YELLOW = "#FFCB00"
SHADE_1 = "#214F59"
SHADE_2 = "#2F728A"
SHADE_3 = "#3B88A5"
# SHADE_3 lightened until the empty part of the progress bar has an
# edge: WCAG 1.4.11 wants 3:1 for a shape, and #3B88A5 on the petrol
# is 2.96:1 - four hundredths short, which is the kind of miss a
# comment rounds up and a measurement does not. #4197B6 is 3.56:1.
TRACK_EDGE = "#4197B6"

# --- derived, for the same reasons src/brand.py derives them -----------
INK = "#08262C"        # below the window background: entries, lists, the bar
TEXT = "#DCEEF4"       # 9.90:1 on petrol, 13.28:1 on ink
TEXT_DIM = "#A9C6CF"   # 6.57:1 on petrol
CYAN_TEXT = "#33C9EE"  # the brand cyan, readable on petrol: 6.04:1
RED = "#FF8A8A"        # 5.21:1 on petrol
RED_BG = "#7A2B2B"     # the destructive "Ja", 7.96:1 with TEXT on it
GREEN = "#57D9A3"

FONT_TEXT = "Roboto"
FONT_CODE = "Fira Code"

# --- die Abstandsleiter, in rem ----------------------------------------
# Dieselbe Leiter wie src/sizes.py SPACE_LADDER, und dieselbe Kopie aus
# demselben Grund wie die sechs Markenwerte darueber: dieses Paket darf
# zepos-config nicht importieren (Spec §4.2), also steht die Leiter hier
# ein zweites Mal und tests/installer/test_branding.py rechnet beide
# gegeneinander nach. Der Test ist die Verbindung, die der Import nicht
# sein darf.
#
# WARUM rem UND NICHT PIXEL
#     Der Assistent laeuft, bevor auf dem Zielsystem irgendeine
#     Monitorkonfiguration existiert - der Kopf von src/sizes.py fuehrt
#     das aus. In rem folgt jeder Abstand der Textskalierung der Maschine,
#     in Pixeln folgt er nichts.
#
# WARUM DIE ZAHLEN GENAU DIESE SIND
#     GEMESSEN am 11.08.2026: von den acht Abstandswerten, die dieses
#     Stylesheet trug, lagen sechs bereits auf einem halben rem - 1rem,
#     1.5rem, "1rem 1.5rem", 1.5rem. Die Leiter wurde an diesem Bestand
#     kalibriert und nicht daneben erfunden; ein halbes rem ist ihre
#     Grundeinheit, und die Sprosse 8 IST ein rem.
#
#     Zwei Regeln lagen daneben und sind darauf gezogen worden:
#     .wizard-header hatte unten 0.75rem und hat jetzt 1rem,
#     .wizard-stamp hatte 0.3rem 0.6rem und hat jetzt 0.25rem 0.5rem.
#     Das sind die beiden Stellen, an denen der Assistent nach dieser
#     Aenderung anders aussieht.
SPACE_2 = "0.25rem"
SPACE_4 = "0.5rem"
SPACE_8 = "1rem"
SPACE_12 = "1.5rem"
SPACE_16 = "2rem"
SPACE_20 = "2.5rem"
SPACE_24 = "3rem"

# Installed by packaging/zepos-installer into the -gui package. Absent in
# a checkout that has not been packaged, which is why every reader checks
# .is_file() rather than assuming - a missing logo must cost a logo and
# not an installer.
LOGO = Path("/usr/share/zepos-installer/branding/zepos-logo.svg")

# What the wizard header actually draws, and how tall it is. The two
# belong together: app.py draws the picture with can_shrink off, so the
# header is exactly as tall as the file - a PNG rendered at some other
# height is not a slightly wrong logo but a wrong-sized header.
#
# The height lives here rather than in app.py so that everything which
# needs it can read it. packaging/make-brand-assets.sh renders to it, and
# tests/installer/test_branding.py checks the file against it - neither
# can import app.py, which needs gi.
WORDMARK = Path("/usr/share/zepos-installer/branding/zepos-wordmark.png")
MARK_HEIGHT = 122

# The picture the whole window is drawn on: the same petrol, the same
# gradient and the same constellation texture at the same 12% as the
# boot menu, rendered by packaging/make-brand-assets.sh from the same
# two sources. The menu and the installer are a minute apart on one
# machine, and this is what makes them one screen rather than two
# programs that share a colour.
BACKDROP = Path("/usr/share/zepos-installer/branding/zepos-backdrop.png")

# libadwaita resolves these names at draw time, so redefining them
# reaches every widget. Names it does not know are ignored rather than
# fatal, which is why naming a few extra costs nothing and missing one
# shows up as a purple patch.
CSS = f"""
@define-color window_bg_color {PETROL};
@define-color window_fg_color {TEXT};
@define-color view_bg_color {INK};
@define-color view_fg_color {TEXT};
@define-color headerbar_bg_color {INK};
@define-color headerbar_fg_color {TEXT};
@define-color headerbar_border_color {SHADE_1};
@define-color headerbar_backdrop_color {PETROL};
@define-color popover_bg_color {INK};
@define-color popover_fg_color {TEXT};
@define-color card_bg_color {SHADE_1};
@define-color card_fg_color {TEXT};
@define-color dialog_bg_color {INK};
@define-color dialog_fg_color {TEXT};
@define-color sidebar_bg_color {INK};
@define-color sidebar_fg_color {TEXT};

/* The brand cyan at full strength, with the ink on top: 4.63:1. White on
   the same fill is 3.43:1 and is what libadwaita would have done. */
@define-color accent_bg_color {CYAN};
@define-color accent_fg_color {INK};
/* Links and focus rings sit ON the window background, where #0096C0 is
   3.45:1. Same colour, lightened until it can be read. */
@define-color accent_color {CYAN_TEXT};

/* "Ja", on the erase confirmation. It stays red, and it stays the only
   red on the screen - which is the whole of what makes it mean
   anything. */
@define-color destructive_bg_color {RED_BG};
@define-color destructive_fg_color {TEXT};
@define-color destructive_color {RED};

@define-color success_color {GREEN};
@define-color warning_color {YELLOW};
@define-color error_color {RED};

/* Roboto for prose. */
* {{
    font-family: "{FONT_TEXT}", "Cantarell", sans-serif;
}}

/* Fira Code for the two things that are columns of characters and read
   wrongly in a proportional font: the disk sizes and the installation
   log. */
textview, textview text, .monospace {{
    font-family: "{FONT_CODE}", monospace;
}}

/* ---------------------------------------------------------------------
   Size
   ---------------------------------------------------------------------
   Measured on the shipping medium, 10.08.2026, on a laptop panel: the
   two buttons the whole form is driven from sat in the bottom-right
   corner at libadwaita's default size and were reported as "hard to
   see and small". These are defaults for a desktop application whose
   user is sitting at their own machine; an installer is read once, on
   unfamiliar hardware, often at arm's length, sometimes on a screen
   whose scaling nobody has set yet.

   In rem, not px: the unit follows the text scale, so a machine
   configured for large text gets a proportionally larger control
   rather than a large label crammed into a small box. */
button {{
    min-height: 2.4rem;
    padding-left: {SPACE_8};
    padding-right: {SPACE_8};
}}

/* The boot menu sets its entries in Roboto at 2.2% of the frame height
   - 24px on a 1080 screen, and about 18 on the panel an installer
   usually runs on. GTK's default is nearer 15, so the two screens were
   a step apart in type size with nothing between them to explain it.
   Everything the form is read from goes up to match. */
row, label, button {{
    font-size: 1.35rem;
}}

row {{
    min-height: 4rem;
}}

/* The two the form is driven from, larger again, and wide enough that
   the click target does not depend on the length of the word - "Weiter"
   and "Installieren" differ by half a button. */
.wizard-nav {{
    min-height: 3.4rem;
    min-width: 11rem;
    padding-left: {SPACE_12};
    padding-right: {SPACE_12};
    font-size: 1.35rem;
    font-weight: bold;
}}

/* ---------------------------------------------------------------------
   The wizard's own chrome
   ---------------------------------------------------------------------
   The header carries the brand device from the boot menu into the
   installer, which is the one place the two are seen minutes apart: a
   short yellow tick, a gap, then the cyan rule. Here the rule is also
   the progress - the same shape says where you are, so the screen gains
   an indicator without gaining an element. */
/* No ground of its own: the backdrop has to run behind the header the
   way the boot menu's picture runs behind its title block. A darker
   band here would put a horizontal edge across the texture in exactly
   the place the old background.png had one. */
/* Nothing between the picture and the eye.
   ------------------------------------------------------------------
   The backdrop is drawn behind everything, but a widget that paints
   its own ground hides it - and three of them did. The header bar had
   headerbar_bg_color, which put a dark band across the top where the
   boot menu has picture; the toolbar view and the scrolled page each
   carry a ground of their own.

   The form's own rows keep theirs. They are cards and have to be read
   against something; it is the CHROME that has to disappear, which is
   exactly the part the boot menu does not have. */
headerbar {{
    background: transparent;
    box-shadow: none;
    border: none;
}}

toolbarview, toolbarview > box {{
    background: transparent;
}}

preferencespage, preferencespage > scrolledwindow,
preferencespage viewport, preferencespage > scrolledwindow > viewport {{
    background: transparent;
}}

stack {{
    background: transparent;
}}

.wizard-header {{
    padding: {SPACE_12} {SPACE_12} {SPACE_8} {SPACE_12};
}}

/* The boot menu's column: theme.txt sets boot_menu, the countdown and
   its bar to left = 19%, width = 62%. A window is not a fixed 1280 wide,
   so this is that share of the width the installer opens at, and the
   column is centred rather than positioned - which comes to the same
   place and survives a resize. */
.wizard-column {{
    min-width: 48rem;
}}

.wizard-title {{
    font-size: 1.7rem;
    font-weight: bold;
}}

/* "ZepOS" under the mark, set the way the boot menu sets it: Roboto
   Light, wide-tracked, at the same share of the screen. The menu draws
   it at 6.5% of the frame height and this is that share of the window
   the installer opens at. */
.wizard-name {{
    font-family: "{FONT_TEXT}", sans-serif;
    font-weight: 300;
    font-size: 2.6rem;
    letter-spacing: 0.4rem;
    color: {TEXT};
}}

/* OUR close button - an ordinary Gtk.Button that app.py puts in the
   header bar after switching the window-manager one off.

   The system button was reported as too small three times. min-height
   and min-width grew its click target and left the glyph alone;
   -gtk-icon-size did nothing visible either. A plain button has no such
   argument: it is this size because nothing else claims it. */
.wizard-close {{
    min-height: 3rem;
    min-width: 3rem;
}}

.wizard-close image {{
    -gtk-icon-size: 1.8rem;
}}

.wizard-step {{
    color: {TEXT_DIM};
}}

/* The build date, between the two buttons. Dim, because it is not part
   of the form and must not compete with them - but NOT smaller, and
   that is the fix rather than the taste.

   It was 0.95rem while everything else in that row is 1.15rem, and the
   ascenders came out shaved: the row's height is settled from the
   larger metrics and the label then draws with the smaller ones. The
   colour alone carries "this is secondary", and the padding keeps the
   glyphs clear of the row's edges whatever font the system resolves. */
.wizard-stamp {{
    color: {TEXT_DIM};
    padding: {SPACE_2} {SPACE_4};
}}

/* trough and progress are the two nodes GtkProgressBar draws; naming
   both keeps the bar the same height whichever one libadwaita's own
   rule wins. */
.wizard-progress, .wizard-progress trough, .wizard-progress progress {{
    min-height: 6px;
}}

/* Light petrol for the track, brand yellow for what has been done.
   Yellow is the ACTIVE thing throughout ZepOS - the selected entry of
   the boot menu, the filled part of its countdown, the steps taken
   here - so the same colour answers the same question on every screen.

   Measured: #FFCB00 on #2F728A is 3.54:1, over the 3:1 WCAG 1.4.11 asks
   of a shape. The border is a shade lighter again, because the EMPTY
   part of the bar has to be visible too: #2F728A on the window ground
   is 2.19:1 and #4197B6 is 3.56:1, so the bar has an extent before
   anything has filled it. */
.wizard-progress trough {{
    background-color: {SHADE_2};
    /* An inset shadow and not a border. A border takes part in the box
       model, so GTK measures the trough with for_size minus the border
       - and while the box works out its own minimum it passes -1, which
       becomes -2 and trips

           Gtk-CRITICAL: gtk_widget_measure: assertion 'for_size >= -1'

       once per build. The shadow draws the same 1px edge and changes no
       measurement. */
    box-shadow: inset 0 0 0 1px {TRACK_EDGE};
}}

.wizard-progress progress {{
    background-color: {YELLOW};
}}

/* The wordmark, the same one the boot menu opens with, in the same
   place. It is what carries "this is still the same system" across the
   handover from the loader to the installer.

   NO MARGIN HERE, and that is not a preference. A Gtk.Picture is
   measured height-for-width, and its box measures it with for_size=-1
   while working out its own minimum. GTK subtracts the CSS margin from
   that -1, hands -1-margin to gtk_widget_measure(), and the result is

       Gtk-CRITICAL: gtk_widget_measure: assertion 'for_size >= -1'

   twice per build, caught by tests/installer/test_gui_headless.py,
   which fails on any CRITICAL. Spacing between the mark and the line
   below it belongs to the box that holds them both. */
.wizard-mark {{
    min-height: 2.5rem;
}}

/* A footer has to look like one, or two buttons in a corner are just
   two buttons in a corner. The line and the darker ground separate it
   from the page above it the way the header is separated. */
/* The footer keeps a line but loses its fill, for the same reason. The
   line is what separates it; the fill would have hidden the picture. */
.wizard-footer {{
    padding: {SPACE_8} {SPACE_12};
    border-top: 1px solid {SHADE_1};
}}
"""

# The window's own picture. Appended rather than written into CSS above
# because a url() naming a file that is not there is a GTK CSS error on
# every start - and in a checkout that has never been packaged, it is
# not there. GTK reports it as a warning, which
# tests/installer/test_gui_headless.py fails on, so the rule is only
# offered when the file can be pointed at.


def css() -> str:
    """The stylesheet, with the backdrop if this machine has one."""
    if not BACKDROP.is_file():
        return CSS
    return CSS + f"""
window {{
    background-image: url("file://{BACKDROP}");
    background-size: cover;
    background-position: center;
}}
"""
