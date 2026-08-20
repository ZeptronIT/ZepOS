#!/usr/bin/env python3
"""
Style Variable Definitions for ZepOS
Single Source of Truth for all CSS values

Supports user settings from profile directory:
    <user root>/user-settings.json

If user settings exist, they override the default values for:
- Scaling factors per screen width (1920, 2560, 3440, 3840)
- Key colors (success, warning, critical, accent, etc.)

Default values are Full HD (1920x1080) optimized.
"""

import collections
import json
import sys
from collections.abc import Mapping

# Flat imports: this module is imported by template_processor.py, which
# runs as a script from the system root and finds its siblings there.
#
# monitors is imported as a module rather than by name so that
# monitors.detect is looked up when it is called. Bound at import time it
# would be a second, frozen reference to the one function that is allowed
# to ask what is attached.
import audio
import clocks
import monitors
# Als MODUL und nicht nur ueber die drei Namen darunter: der
# Leisten-Abschnitt weiter unten braucht ein halbes Dutzend Funktionen
# und Konstanten von dort, und sechs weitere from-Zeilen waeren sechs
# Gelegenheiten, eine davon aus Versehen hier neu zu definieren. Der
# Name traegt das Suffix, weil "settings" in dieser Datei ueber vierzig
# Mal als gewoehnliches Wort vorkommt.
import settings as settings_module
import sizes
import theme
from paths import user_root
from settings import FILENAME as SETTINGS_FILENAME
from settings import SCHEMA_VERSION, UnusableSettings
from settings import load as read_settings_document
from vpn import (
    child_names,
    nonblank_entries,
    routed_networks_line,
    swanctl_children,
)

# =============================================================================
# USER SETTINGS INTEGRATION
# =============================================================================

def _load_user_settings():
    """
    Load user settings - GLOBAL for all profiles.

    Settings are stored in: <user root>/user-settings.json
    This applies to ALL profiles on this PC.

    NO FILE and NO READABLE FILE are two different answers, and only the
    first one is normal. A fresh installation has no settings file, and
    generating a desktop must not depend on one the user has never been
    asked to create - so that case returns {} and every get_user_*()
    below answers from its own default.

    A file that IS there and cannot be read used to return {} as well,
    from a bare `except: pass`. Every {{STYLE_*}} then resolved - to a
    default - so validate_output found nothing wrong (it checks for
    surviving placeholders, JSON, `bash -n` and plugin paths, and the
    output is perfect by all four), publish() moved it into place, and
    the run printed `✓ Config successfully generated`. Measured on a
    settings file truncated to 60 bytes: the user's vpn-connect.sh went
    from ROUTED_NETWORKS="10.8.0.0/24" and VPN_SERVER="gw.example.org" to
    two empty strings, and the only thing on the terminal was a success.
    A working VPN replaced by one that cannot dial, silently, by a
    command the user ran for an unrelated reason.

    So it raises, and generation stops before anything is staged. The
    settings the user configured are still in the file; a run that
    published defaults over their configuration would have been the one
    thing that could not be undone.
    """
    # Global settings file (applies to all profiles)
    settings_file = user_root() / SETTINGS_FILENAME
    if not settings_file.exists():
        return {}

    try:
        # The same reader zepos-settings and zepos-doctor use, so that
        # "cannot be read" means one thing on this machine rather than
        # three. It refuses a file whose top level is not an object and
        # one that carries no schema_version - both of which the other
        # two commands already refuse, while this layer carried on.
        return read_settings_document(settings_file)
    except (ValueError, OSError) as exc:
        raise UnusableSettings(
            f"{settings_file} cannot be read: {exc}\n"
            f"Nothing was generated. Every setting in that file - the VPN "
            f"server and its networks, the weather location, the colours - "
            f"would have been replaced by this program's own defaults, and "
            f"the generated configuration would have looked entirely "
            f"correct.\n"
            f"Repair the file (it has to be a JSON object carrying "
            f"\"schema_version\": {SCHEMA_VERSION}), or move it aside and let "
            f"the defaults be written again."
        ) from exc

# Load user settings at module import time
USER_SETTINGS = _load_user_settings()

# Die Palette, mit der dieser Lauf erzeugt. Jede Farbe, jede Deckkraft,
# jede Schriftfamilie und das Bild vor der Sitzung kommen ab hier aus
# THEME und nicht mehr aus src/brand.py unmittelbar - im
# ausgelieferten Thema sind das dieselben Werte, und deshalb steht in
# den erzeugten Dateien auch dasselbe wie vorher.
#
# WARUM DER NAME AUS /etc UND NICHT AUS DER EINSTELLUNGSDATEI KOMMT
#     Weil die Anmeldemaske dazugehoert und die vor jedem Konto steht.
#     Der Kopf von src/theme.py fuehrt die Messung; die siebzig
#     einzelnen Farben bleiben dem Konto und liegen ueber dieser
#     Palette, weil get_user_color() unten zuerst die
#     Einstellungsdatei fragt.
#
# WARUM HIER KEIN try: STEHT
#     theme.palette() faellt ueber einen unbekannten Namen, und das ist
#     dieselbe Entscheidung wie bei _load_user_settings() darueber: ein
#     Lauf, der eine Einstellung uebergeht und trotzdem "erfolgreich
#     erzeugt" meldet, hinterlaesst einen Schreibtisch, der vollstaendig
#     richtig aussieht und nicht der eingestellte ist.
THEME = theme.active()

def get_user_scale(width):
    """
    Get the user-defined scale for a given screen width.

    There is one scale per width bracket, and it scales widths. The
    document used to carry a "height" beside it, which this function
    could also be asked for - see user_settings.migrate_scaling for
    where that value went and why.

    Args:
        width: Screen width (e.g., 1920, 2560)

    Returns:
        float or None: User-defined scale, or None if not set
    """
    scales = USER_SETTINGS.get("scaling", {})
    value = scales.get(str(width))
    if value is not None:
        if isinstance(value, dict):
            return float(value.get("width", 1.0))
        else:
            # A document this program has not migrated yet: the scale for
            # a bracket used to be a bare number. This module reads the
            # file directly rather than through user_settings, so it has
            # to understand both shapes.
            return float(value)
    return None

def get_user_color(key, default=None):
    """
    Get the user's colour for `key`, or the active theme's.

    DREI SCHICHTEN, UND IHRE REIHENFOLGE IST DIE ANTWORT AUF "WEM
    GEHOERT DIE FARBE"
        1. die Einstellungsdatei dieses Kontos - was der Mensch selbst
           gesagt hat, und das ueberlebt jeden Themenwechsel
        2. `default`, fuer die zehn Fenster-Akzente, die auf
           overlay_accent zurueckfallen
        3. THEME.COLORS - das eingestellte Thema, aufgeloest aus
           brand.COLOR_FIELDS

    Die dritte Schicht war bis zum 12.08.2026 brand.COLORS und damit
    unveraenderlich. Sie ist der Grund, aus dem ein Thema ueberhaupt
    etwas bewirken kann, und zugleich der Grund, aus dem es die
    eigenen Farben nicht ueberfaehrt.
    It used to be: every call carried its own hex literal, which made
    this file the second of three copies of ninety-nine values that all
    had to agree - and they already did not, `warning` being #f9e2af here
    and #fab387 in the style editor's list of the same key.

    An unknown key raises rather than answering. A misspelled key used to
    return whatever literal was typed beside it, so the placeholder built
    from it produced a perfectly valid stylesheet in a colour no setting
    could ever reach, and nothing said so.

    `default` is for one case and there are ten of them: the per-widget
    AGS accents fall back to `overlay_accent` - the USER's, when they set
    it - before they fall back to the THEME. Nothing else may pass it, or
    the second copy of the palette grows back one call at a time.

    Args:
        key: Colour key (e.g. "success", "warning")
        default: Only for a key whose fallback is another key's value

    Returns:
        str: Colour value (hex)
    """
    colors = USER_SETTINGS.get("colors", {})
    if key in colors:
        return colors[key]
    if default is not None:
        return default
    try:
        return THEME.COLORS[key]
    except KeyError:
        raise KeyError(
            f"no colour is defined for {key!r}: it is in neither the "
            f"settings file nor the {THEME.name} theme. Add the role to "
            f"brand.COLOR_FIELDS in src/brand.py."
        ) from None


def get_user_vpn_setting(key, default=None):
    """
    Get user-defined VPN setting using dot notation for nested keys.

    Args:
        key: Setting key with dot notation (e.g., "server", "phase1.version", "dns.servers")
        default: Default value if not found

    Returns:
        The setting value or default
    """
    vpn_settings = USER_SETTINGS.get("vpn", {})

    # Handle dot notation for nested keys
    keys = key.split(".")
    value = vpn_settings
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            value = None
            break

    if value is None:
        return default

    return value

def get_user_watchdog_setting(key, default):
    """
    Get a user-defined network-watchdog setting.

    A blank value falls back to the default rather than through, unlike
    the VPN settings, where blank is the meaningful "not configured".
    The watchdog has no such state: an empty probe target makes every
    check fail, and the watchdog answers a failed check by taking the
    interface down and up again - every ten seconds, on a connection that
    was never broken.

    Args:
        key: Setting key (e.g., "test_host")
        default: Default value if not set or blank

    Returns:
        The setting value or default
    """
    watchdog_settings = USER_SETTINGS.get("watchdog", {})
    value = watchdog_settings.get(key)
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip()

def get_user_weather_setting(key, default=""):
    """
    Get a user-defined weather setting.

    Blank is meaningful here, as with the VPN settings and unlike the
    watchdog: the weather module sends the configured location to a third
    party on every refresh, so no location can mean anything other than
    "ask nobody anything". A default would turn a feature the user never
    switched on into a request they never made.

    Args:
        key: Setting key (e.g., "location")
        default: Value if the setting is absent

    Returns:
        str: The setting value, stripped, or the default
    """
    weather_settings = USER_SETTINGS.get("weather", {})
    value = weather_settings.get(key)
    if value is None:
        return default
    return str(value).strip()

def vpn_connection_name():
    """Get the configured VPN connection name."""
    return get_user_vpn_setting("connection_name", "work")

def vpn_list_setting(key):
    """One of the VPN settings that is a list, blanks removed.

    routed_networks, bypass_networks and dns.servers, all three
    hand-editable and all three read through the same helper - which
    refuses a value that is not a list rather than iterating it. A string
    is the shape that matters: `"routed_networks": "10.8.0.0/24"` used to
    be walked character by character into eleven child security
    associations with a digit or a dot for a network each.

    The refusal is re-raised carrying the file it came out of. The
    generator prints this and nothing else, and "vpn.routed_networks is
    the single string ..." does not say which of the files on a machine
    holds it.
    """
    try:
        return nonblank_entries(get_user_vpn_setting(key, []),
                                setting=f"vpn.{key}")
    except UnusableSettings as exc:
        raise UnusableSettings(
            f"{user_root() / SETTINGS_FILENAME} cannot be used: {exc}\n"
            f"Nothing was generated. The previous configuration is unchanged."
        ) from exc

def vpn_routed_networks():
    """Get the configured routed networks, blanks removed."""
    return vpn_list_setting("routed_networks")

def vpn_children_block():
    """
    Build the swanctl children block from the configured routed networks.

    An empty result is a legitimate outcome and must not stop the run.
    Generating configuration covers the whole desktop, and somebody who
    has no VPN still needs their bar, their terminal and their shell -
    aborting here would deny them all three over a feature they never
    asked for. The emptiness is carried through to the generated connect
    script instead, which refuses to dial on it and says so to the one
    person it concerns.

    Returns:
        str: The children block, or "" when no network is configured
    """
    networks = vpn_routed_networks()
    if not networks:
        return ""
    return swanctl_children(
        vpn_connection_name(),
        networks,
        rekey_time=str(get_user_vpn_setting("phase2.rekey_time", 43200)),
        life_time=str(get_user_vpn_setting("phase2.life_time", 43200)),
        esp_proposals=get_user_vpn_setting("phase2.esp_proposals", "aes256-sha256-ecp521"),
        mode=get_user_vpn_setting("phase2.mode", "tunnel"),
        replay_window=str(get_user_vpn_setting("phase2.replay_window", 32)),
    )

def audio_section():
    """The audio settings, as audio.py reads them."""
    return audio.settings_section(USER_SETTINGS)

def audio_setting(key):
    """One audio device name from the settings, or "" when unset.

    Blank falls through rather than to a default, as with the weather
    location and unlike the watchdog. There is no name that could be
    right for a machine whose hardware nobody has looked at, and a wrong
    one is a device the user cannot hear anything through.
    """
    value = audio_section().get(key)
    return "" if value is None else str(value).strip()

def audio_defaults_block():
    """The `wireplumber.settings` block, or a comment saying there is none."""
    return audio.default_devices_block(audio_section())

def audio_node_rules_block():
    """The `node.rules` block, or a comment saying no source is blocked.

    A settings value of the wrong shape - a single string where a list of
    node names belongs - is refused rather than iterated, and the refusal
    is re-raised carrying the file it came out of, exactly as the VPN
    lists are. Without the filename "audio.blocked_sources is the single
    string ..." names none of the files on a machine.
    """
    try:
        return audio.node_rules_block(audio_section())
    except UnusableSettings as exc:
        raise UnusableSettings(
            f"{user_root() / SETTINGS_FILENAME} cannot be used: {exc}\n"
            f"Nothing was generated. The previous configuration is unchanged."
        ) from exc

def _unusable_clocks(exc):
    """A clocks refusal, carrying the file it came out of.

    The same wrapping audio_node_rules_block() does, and for the same
    reason: "clocks.zones is the single string 'Asia/Tokyo' ..." names a
    setting but none of the files on a machine, and there is more than
    one settings file on a machine.

    Exactly ONE caller wraps, which is why both builders below read the
    section for themselves instead of sharing a wrapped reader. A reader
    that wrapped too produced the filename and "Nothing was generated"
    TWICE around one sentence, for any settings file whose clocks section
    is the wrong type at all - measured, on `"clocks": "Asia/Tokyo"`.
    """
    return UnusableSettings(
        f"{user_root() / SETTINGS_FILENAME} cannot be used: {exc}\n"
        f"Nothing was generated. The previous configuration is unchanged."
    )

def clock_zones_block():
    """The ZONES/LABELS declarations, or a comment saying there are none."""
    try:
        return clocks.zones_block(clocks.settings_section(USER_SETTINGS))
    except UnusableSettings as exc:
        raise _unusable_clocks(exc) from exc

def clock_format_literal():
    """The date(1) format as one shell literal."""
    try:
        return clocks.format_literal(clocks.settings_section(USER_SETTINGS))
    except UnusableSettings as exc:
        raise _unusable_clocks(exc) from exc

# DIE VIER FUNKTIONEN, DIE HIER STANDEN, UND WARUM SIE WEG SIND
#
#     get_user_widget_size(), resolution_bracket(),
#     get_widget_size_for_monitor() und get_widget_scroll_for_monitor()
#     lasen user-settings.json unter widget_sizes.<breite>.<widget> und
#     bauten daraus STYLE_EWW_WINDOW_<WIDGET>_MON<n> und
#     STYLE_EWW_SCROLL_<WIDGET>_MON<n> - siehe die Notiz bei
#     _monitor_style_variables() weiter unten fuer die Messung, die das
#     am 18.08.2026 als Kette ohne Leser auswies. get_user_widget_size()
#     hatte einen fuenften Aufrufer direkt in _FIXED_STYLE_VARIABLES, ohne
#     MON-Suffix - STYLE_EWW_SCROLL_DISK und vier Geschwister; dieselbe
#     Messung traf auch sie mit NULL Lesern (siehe die Notiz dort).
#
#     resolution_bracket() hatte keinen dritten Aufrufer und faellt mit.

# =============================================================================
# MONITOR DETECTION
# =============================================================================
#
# There is exactly one answer to "what is attached", and monitors.py is
# it. This module used to ask `hyprctl monitors -j` a second time, on its
# own, and the second answer differed from the first in three ways:
#
#   * it numbered the screens by the compositor's `id`, which follows the
#     order the cables went in. monitors.py numbers them by position on
#     the desk. So the AGS widget sized for "monitor 0" and the Hyprland
#     workspace rule for "the leftmost screen" meant different monitors
#     the moment the cables went in in a different order.
#   * it took the MODE for the size. A 4K panel standing on its side
#     reports 3840x2160 and is 2160 wide on the glass; the mode earned it
#     the 1.50 scale factor meant for a screen three and a half thousand
#     pixels wide.
#   * it accepted five ids, 0 to 4, invented a 1920x1080 screen for every
#     id nothing reported, and dropped a screen whose id was 5.
#
# monitors.Monitor.displayed_size and monitors.ordered() answer all
# three, and are what detect() already applies.

# The one screen assumed where a size is needed and none is known. Full
# HD is the smallest of the four brackets the scaling is keyed by, so a
# widget sized for it fits on any real screen, while a widget sized for a
# 4K screen that turned out not to be there hangs off the edge of a 1080p
# panel. Nothing below pretends such a screen EXISTS - MONITOR_RESOLUTIONS
# stays empty - it is only the number handed to the callers that have to
# produce one anyway.
FALLBACK_RESOLUTION = (1920, 1080)

# The compositor's answer for this process, or None while nobody has
# asked yet. Never read directly; attached_screens() owns it.
_ATTACHED_SCREENS = None


def attached_screens():
    """The size of every attached screen as it stands, left to right.

    Empty when nothing can answer. That is the NORMAL case for half the
    runs this module takes part in: the configuration is generated during
    installation, from a TTY, and in the test suite, none of which has a
    compositor. A failed query is therefore not an error here - but it is
    also not a screen. "Nothing is known" and "there is a 1920x1080
    screen" are different statements, and only the first one is true; see
    FALLBACK_RESOLUTION for what the callers that need a number do with
    it.

    Asked once per process and remembered. A `--all` run already starts
    one process per template, so the cost of asking is multiplied by
    every template; asking once per placeholder would multiply it by
    every placeholder as well.
    """
    global _ATTACHED_SCREENS
    if _ATTACHED_SCREENS is None:
        try:
            _ATTACHED_SCREENS = tuple(
                monitor.displayed_size for monitor in monitors.detect())
        except RuntimeError:
            # The single exception detect() raises, deliberately: it
            # covers all four ways the query can fail - Hyprland not
            # running, hyprctl not installed, the call failing, the
            # answer not being a list of monitors - because a caller can
            # do exactly one thing about all four.
            _ATTACHED_SCREENS = ()
    return _ATTACHED_SCREENS


class _PerScreen(Mapping):
    """{position on the desk: value} for every attached screen.

    The three tables below were plain dicts built while this module was
    being imported. A `--all` run starts one process per template, and
    every one of them imports this module, so that import-time `hyprctl`
    was one compositor query per template - 99 of them, measured - for
    values no template names.

    A Mapping rather than a dict so the query can wait until somebody
    actually reads one of them, and a Mapping rather than a function so
    that the callers keep reading them the way they always have:
    `table.get(index, default)` and `table[index]`.
    """

    def __init__(self, value_of):
        self._value_of = value_of

    def _values(self):
        return {index: self._value_of(size)
                for index, size in enumerate(attached_screens())}

    def __getitem__(self, index):
        return self._values()[index]

    def __iter__(self):
        return iter(self._values())

    def __len__(self):
        return len(self._values())

    def __repr__(self):
        return repr(self._values())

def calculate_width_scale(resolution):
    """
    Calculate scaling factor based on screen WIDTH.
    Uses user settings if available, otherwise falls back to defaults.

    User-configurable scale factors (in user-settings.json):
    - 1920px (Full HD)     = default 1.00
    - 2560px (WQHD/UW)     = default 1.20
    - 3440px (Ultrawide)   = default 1.35
    - 3840px (4K)          = default 1.50
    """
    width, height = resolution

    # Check for exact user-defined scale
    user_scale = get_user_scale(width)
    if user_scale is not None:
        return user_scale

    # Check for interpolation between user-defined scales
    user_scales = USER_SETTINGS.get("scaling", {})
    if user_scales:
        # Convert to sorted list of (width, scale) tuples - handle both old and new format
        defined = []
        for w, val in user_scales.items():
            if isinstance(val, dict):
                defined.append((int(w), float(val.get("width", 1.0))))
            else:
                defined.append((int(w), float(val)))
        defined = sorted(defined)

        if defined:
            # Below minimum defined
            if width <= defined[0][0]:
                return defined[0][1]

            # Above maximum defined
            if width >= defined[-1][0]:
                return defined[-1][1]

            # Interpolate between two nearest values
            for i in range(len(defined) - 1):
                w1, s1 = defined[i]
                w2, s2 = defined[i + 1]
                if w1 < width < w2:
                    ratio = (width - w1) / (w2 - w1)
                    return s1 + ratio * (s2 - s1)

    # Fall back to hardcoded defaults
    if width <= 1920:
        return 1.0
    elif width <= 2560:
        return 1.0 + (width - 1920) / (2560 - 1920) * 0.20
    elif width <= 3440:
        return 1.20 + (width - 2560) / (3440 - 2560) * 0.15
    elif width <= 3840:
        return 1.35 + (width - 3440) / (3840 - 3440) * 0.15
    else:
        return 1.50

# The attached screens, left to right, and the scale factor derived from
# each. Same shape as before - {index: value}, read with .get() - but the
# index is now the screen's place on the desk instead of the order its
# cable went in, and there is one entry per screen that is really there
# instead of five entries whatever the desk looks like.
#
# THERE WAS A SECOND TABLE HERE
#     MONITOR_HEIGHT_SCALES, built by calculate_height_scale() from the
#     "height" half of each scaling bracket, with scale_height() and
#     scale_height_px() to apply it. Nothing in this repository called
#     any of the three - the only placeholders derived from a scale are
#     STYLE_SCALE_FACTOR_MON*, and those are width - so a user who set a
#     height scale (the settings file offered one, with defaults, and
#     user_settings migrated it) changed no generated byte anywhere. It
#     is gone rather than wired up.
#
#     KORREKTUR vom 18.08.2026: hier stand, ein Widget-HOEHE komme
#     stattdessen aus widget_sizes.<width>.<widget>.height, und eine
#     zweite Skalierung waere also eine zweite Kontrolle fuer dieselbe
#     Zahl gewesen. Das war so nie wahr - GEMESSEN am 18.08.2026,
#     `grep -rl` gegen src/templates/ UND src/styles/: KEINE Vorlage las
#     je STYLE_EWW_WINDOW_* oder STYLE_EWW_SCROLL_*, die einzigen
#     Platzhalter, die widget_sizes je erreichten. widget_sizes selbst
#     ist seit demselben Tag geloescht (siehe die Notiz bei
#     _monitor_style_variables()); was ein Fenster HOCH ist, stand schon
#     vorher fest in seiner eigenen, ausgemessenen WIN_WIDTH-Konstante.
#     See user_settings.migrate_scaling for what happens to a height a
#     user had already stored.
#
#     scale_window() and scale_window_px() went with them: same story on
#     the width side, minus the settings key - nothing called either.
MONITOR_RESOLUTIONS = _PerScreen(lambda size: size)
MONITOR_WIDTH_SCALES = _PerScreen(calculate_width_scale)


def scale_info():
    """One line naming every attached screen and its width factor.

    Written into the generated files as a comment, for the person who has
    to work out why a widget came out the size it did. It lists the
    screens that ARE there - it used to list five whatever the desk
    looked like, so a single-monitor machine's stylesheet claimed four
    monitors that were not plugged in.
    """
    if not attached_screens():
        width, height = FALLBACK_RESOLUTION
        return f"no monitor detected - assuming {width}x{height}"
    return ", ".join(
        f"Mon{index}: {size[0]}x{size[1]} "
        f"({MONITOR_WIDTH_SCALES[index]:.2f}x)"
        for index, size in MONITOR_RESOLUTIONS.items())


# How many screens the placeholders can address. It is a contract with
# the templates and NOT a limit on detection: the set of placeholder
# names cannot depend on what is plugged in, or a template naming
# {{STYLE_SCALE_FACTOR_MON2}} would resolve on a three-screen desk and
# fail the whole run on a two-screen one. attached_screens() has no such
# limit - a sixth screen is detected, ordered and scaled; it simply has
# no placeholder of its own, because no template asks for one.
#
# A slot no screen fills falls back (see FALLBACK_RESOLUTION) rather than
# borrowing its neighbour's size.
#
# It stands here, above _FIXED_STYLE_VARIABLES, because _per_screen()
# below is called while that dict is being built.
MONITOR_SLOTS = 5


def _per_screen(values):
    """One placeholder per screen for a value that is the same on all of
    them.

    These are per-monitor in NAME only. A template addresses a screen
    uniformly - the position placeholders below are named per slot and
    hold the same value in each - and the five names have to exist all
    the same, or a template would resolve on one desk and fail the whole
    run on another.

    Written out, that was 290 lines carrying 58 distinct values: every
    block was its own ten or thirty lines copied five times, and every
    value that had to change had to change in five places.

    _WIDGET_WINDOW_WIDTHS stood here as the same argument applied to a
    ninth family - widget window widths, keyed by widget rather than
    named directly - until 18.08.2026: it and the placeholders it built,
    STYLE_EWW_WINDOW_*_MON<n> and STYLE_EWW_SCROLL_*_MON<n>, had zero
    readers in src/templates/ and src/styles/, GEMESSEN that day with
    `grep -rl`. Both fell with the settings tab that was their only
    writer; see the note at _monitor_style_variables() for the measurement.

    DIE SCHRIFTLEITER GEHOERT NICHT MEHR HIERHER, und das ist eine
    Korrektur an dem, was hier stand. Der Satz war: nur der
    Schreibtisch koenne seine Schriftgroesse je dem Schirm folgen
    lassen, weil nur er weiss, was angeschlossen ist. Das erste stimmt
    und das zweite folgt nicht daraus. GEMESSEN am 11.08.2026: die
    beiden Dateien, in denen die Schriftgroessen ankommen, sind
    base-style.template (EIN Stylesheet fuer alle Leisten) und
    ags-style.template (EINES fuer alle Ueberlagerungen), und GTK-CSS
    kennt keinen Selektor fuer einen Monitor. Eine Regel darin kann
    nicht sagen "auf dem zweiten Schirm 16 px" - fuenf Namen pro Sprosse
    waren also nicht ungenutzt, sondern unbenutzbar.

    Die Leiter steht deshalb in src/sizes.py, einmal, und wird von einem
    Faktor bewegt. Was pro Schirm wirklich verschieden sein kann - wie
    breit ein Ueberlagerungsfenster ist - liegt weiter unten in
    _monitor_style_variables() und ist es auch.
    """
    return {f"{name}_MON{index}": value
            for index in range(MONITOR_SLOTS)
            for name, value in values.items()}


def _channels(colour):
    """A brand hex as the three decimal channels CSS wants inside rgba().

    An alpha channel is the one thing a six-digit hex cannot carry -
    tests/src/test_brand.py::test_every_colour_is_a_six_digit_hex holds
    every value in THEME.COLORS to six digits, because mako appends its
    own DD and AA to two of them. So a translucent surface has to be
    written as rgba() somewhere.

    Written out whole it becomes a SECOND copy of the colour, in decimal:
    ein rgba() mit den Kanaelen 13, 61, 71 ist THEME.PETROL, geschrieben
    so, dass keine Suche nach #0D3D47 es findet - und die drei, die es
    noch gibt, sind der Grund, aus dem die Literalpruefung in
    test_brand.py ueberhaupt eine Ausnahmeliste braucht.

    Vier waren es bis zum 12.08.2026. Die vierte war die Platte des
    Docks, und sie trug nicht nur eine zweite Kopie der Farbe, sondern
    auch eine GERATENE Deckkraft daneben; sie kommt jetzt aus
    THEME.rgba() mit der abgeleiteten Zahl.

    So this returns the channels only and the template writes the rgba()
    around them. The CSS function then lives in the CSS, this module
    carries no colour of its own - which is what that check is FOR, and
    it caught the first attempt at this helper, which built the whole
    call here in an f-string.
    """
    digits = colour.lstrip("#")
    return ", ".join(str(int(digits[i:i + 2], 16)) for i in (0, 2, 4))


# =============================================================================
# SIZES
# =============================================================================
#
# src/sizes.py haelt die Tabelle, den Anker und die Begruendung. Sie
# steht dort und nicht hier, weil user_settings.py sie ebenfalls liest -
# fuer `set-size`, `list-sizes` und die Vorgaben - und dieses Modul
# beim Import die Einstellungsdatei liest und monitors.py nach dem
# Schreibtisch fragen kann. Ein Befehl, der Einstellungen SCHREIBT, darf
# beides nicht ausloesen.


def size_value(name):
    """Der erzeugte Wert einer Groesse, mit den Einstellungen dieses Laufs.

    sizes.value_of() nimmt den Abschnitt als Argument, damit es ohne
    Zustand auskommt; hier wird der Abschnitt aus den einmal geladenen
    USER_SETTINGS nachgereicht, wie audio_section() es fuer den
    Tonabschnitt tut.
    """
    return sizes.value_of(name, sizes.settings_section(USER_SETTINGS))


# Everything that does NOT depend on what is plugged in. Kept apart from
# the monitor-dependent values below so that building this dict - which
# happens while the module is being imported, on every generator run -
# cannot start a `hyprctl` process. STYLE_VARIABLES, at the end of the
# file, is the two halves together.
_FIXED_STYLE_VARIABLES = {
    # ============================================================================
    # SPACING (fixed - NOT scaled, these affect the bar)
    # ============================================================================
    "STYLE_MODULE_SPACING": size_value("STYLE_MODULE_SPACING"),
    "STYLE_GROUP_SPACING": "40px",               # Special spacing between time+weather groups
    "STYLE_GROUP_INTERNAL": "0px",               # No spacing within groups

    # HIER STAND EIN RAHMEN, DER KEINER WAR (12.08.2026)
    #     STYLE_BORDER_WIDTH ("0px"), STYLE_BORDER_STYLE ("solid") und
    #     STYLE_BORDER_COLOR (SHADE_1) hatten zusammen genau EINEN Leser:
    #     die Zeile `border: {{STYLE_BORDER_WIDTH}} {{STYLE_BORDER_STYLE}}
    #     {{STYLE_BORDER_COLOR}}` auf .bar-module. Mit einer Breite von
    #     null hat sie nie etwas gemalt - eine Farbe und ein Stil fuer
    #     einen Rahmen, den es nicht gab.
    #
    #     Die Zeile ist mit der Kachel gegangen ("die icon sollen im
    #     header nicht nochmal ein element haben"), und damit die drei
    #     Namen. Ein "vielleicht spaeter wieder" waere hier besonders
    #     teuer: der naechste Leser haette einen Rahmen von 0 px
    #     bekommen und lange gesucht, warum nichts zu sehen ist.
    #
    #     STYLE_BORDER_RADIUS ist denselben Weg schon frueher gegangen -
    #     es stand als "0px" da und wurde von sieben Vorlagen gelesen,
    #     also von vier Fenstern, deren Ecken auf null standen, weil eine
    #     Ecke keinen anderen Platzhalter hatte. Sie stehen jetzt auf
    #     {{STYLE_RADIUS_PANEL}}; die Leiter dazu steht in src/sizes.py.

    # ============================================================================
    # COMMON VALUES (fixed - NOT scaled, these affect the bar)
    # ============================================================================
    "STYLE_MARGIN_VERTICAL": "3px 0px",
    # STYLE_CHIP_GAP stand hier bis zum 19.08.2026 - .bar-module trug
    # ihn als margin-left, bis genau diese Zeile hier (STYLE_PADDING_MODULE)
    # denselben Doppelzaehlungs-Fehler behob und .bar-module auf
    # STYLE_SPACE_8 umstellte. Die Herleitung und die Loeschung stehen
    # bei sizes.py, direkt vor STYLE_PADDING_BUTTON (Regel 14).
    # DIESER WERT WAR BIS ZUM 19.08.2026 STYLE_MODULE_SPACING, UND DAS
    # WAR DER GRUND FUER "die icon untereinander komisch viel platz von
    # der margin her" (Nutzer, 19.08.2026)
    #
    #     Der Kommentar, der hier stand, war einmal richtig und dann
    #     nicht mehr: "Der seitliche Anteil ist derselbe Abstand wie
    #     zwischen zwei Modulen und wird deshalb aus derselben Groesse
    #     gebaut" - geschrieben, als .bar-module noch eine Kachel mit
    #     eigenem Grund war und die Polsterung MITBESTIMMTE, wie breit
    #     diese Kachel aussah. Der Umbau vom 12.08.2026 hat die Kachel
    #     abgeschafft (".bar-module ... GEMELDET: 'die icon sollen im
    #     header nicht nochmal ein element haben'") und dabei selbst
    #     festgehalten, was seither gilt: "margin ... der Abstand
    #     zwischen zwei Modulen. Er ist seit heute das EINZIGE, was sie
    #     trennt" (siehe .bar-module, bar-style.template). Die
    #     Polsterung blieb stehen, aber nur noch als "die FLAECHE, die
    #     der Zeigereffekt bemalt" - eine Klickflaeche, kein zweiter
    #     Abstand. Ihre GROESSE wurde bei diesem Rollenwechsel nicht
    #     nachgezogen.
    #
    #     GEMESSEN (Bericht der Aufgabe vom 19.08.2026): ein Modul, das
    #     .bar-module traegt UND STYLE_MODULE_SPACING als eigenen
    #     margin-right setzt (die grosse Mehrheit), stand seinem
    #     Nachbarn padding-right(15) + margin-right(15) + margin-left
    #     (STYLE_CHIP_GAP, 15) + padding-left(15) = 60px entfernt, bei
    #     Vorgabegroesse - der Zeigergrund zaehlte doppelt mit, einmal
    #     als eigene Polsterung, einmal (unter anderem Namen) als
    #     Modulabstand. Ein Modulpaar mit margin-right:
    #     STYLE_GROUP_INTERNAL (0px, "zusammengehoerige Module") kam
    #     trotzdem nur auf 45px - die Polsterung allein war schon fast
    #     so breit wie der ganze beabsichtigte Abstand zwischen
    #     ZUSAMMENGEHOERIGEN Modulen.
    #
    #     STYLE_PADDING_BUTTON ist die Groesse, die dieses Projekt
    #     bereits fuer eine reine Klickflaeche ohne Trennfunktion
    #     benutzt (#tray button.tray-item, tooltip label - siehe
    #     bar-style.template) - genau die Rolle, die die Polsterung
    #     seit dem 12.08.2026 hat. Beide sind SCALED (src/sizes.py),
    #     folgen also weiterhin gemeinsam dem Groessenregler - die
    #     Sorge, derentwegen der alte Kommentar padding und Modulabstand
    #     an dieselbe Zahl gebunden hat (das Auseinanderfallen bei
    #     grosser Schrift), gilt unveraendert nicht mehr.
    "STYLE_PADDING_MODULE": f'0px {size_value("STYLE_PADDING_BUTTON")}',
    "STYLE_PADDING_BUTTON": size_value("STYLE_PADDING_BUTTON"),
    # Fuer die vier reinen Symbolmodule der Leiste (#network, #bluetooth,
    # #pulseaudio, #pulseaudio#microphone) aus bar-style.template -
    # Aufgabe 19, 19.08.2026. Herleitung bei STYLE_BAR_SYMBOL_WIDTH in
    # src/sizes.py.
    "STYLE_BAR_SYMBOL_WIDTH": size_value("STYLE_BAR_SYMBOL_WIDTH"),

    # ============================================================================
    # HEIGHTS
    # ============================================================================
    "STYLE_BAR_THICKNESS": size_value("STYLE_BAR_THICKNESS"),
    "STYLE_BAR_SHELF": size_value("STYLE_BAR_SHELF"),
    "STYLE_GAPS_IN": size_value("STYLE_GAPS_IN"),
    "STYLE_GAPS_OUT": size_value("STYLE_GAPS_OUT"),
    "STYLE_WINDOW_ROUNDING": size_value("STYLE_WINDOW_ROUNDING"),
    # Fuer .zep-btn und .zep-row aus ags-kit.template (task-1u4,
    # 18.08.2026). Die Sprossen stehen in src/sizes.py bei
    # STYLE_MODULE_SPACING; ohne diesen Eintrag hier kennt kein Lauf den
    # Wert, und die Vorlage scheitert mit UnresolvedPlaceholders.
    "STYLE_CONTROL_HEIGHT": size_value("STYLE_CONTROL_HEIGHT"),
    "STYLE_ROW_HEIGHT": size_value("STYLE_ROW_HEIGHT"),
    # Fuer .zep-row-nav aus ags-style.template (Aufgabe 19, 19.08.2026).
    # Herleitung bei STYLE_NAV_ROW_HEIGHT in src/sizes.py.
    "STYLE_NAV_ROW_HEIGHT": size_value("STYLE_NAV_ROW_HEIGHT"),

    # ============================================================================
    # DIE BREITENLEITER - drei Sprossen fuer alle Aufklappfenster
    # ============================================================================
    #
    # Eine Sprosse haengt an keinem Bildschirm, deshalb hier bei den
    # FESTEN Werten und nicht in _monitor_style_variables(). Die Tabelle,
    # die Rechnung und die Begruendung stehen in src/sizes.py bei
    # MODAL_WIDTHS; hier wird daraus nur, was ein {{STYLE_*}}-Platzhalter
    # sein muss, weil acht Fenstervorlagen (task-1u5, 18.08.2026) ihn
    # direkt in `const WIN_WIDTH = ...` lesen.
    #
    # OHNE "px", UND DAS IST GEPRUEFT UND KEINE VERMUTUNG: alle acht
    # Leser stehen in TypeScript-Zahlenkontext (`const WIN_WIDTH = ...`,
    # das dann als `width: WIN_WIDTH` in createOverlayWindow() landet,
    # typisiert als `width: number` in ags-overlay-utils.template) -
    # nie in einer CSS-Regel. "500px" waere dort keine Zahl, sondern ein
    # Syntaxfehler (bestaetigt: `node --check` isoliert wirft "Identifier
    # cannot follow number"; im vollen, Modul-praefixierten Fenster
    # bleibt derselbe Fehler unbemerkt, siehe Bericht). STYLE_GAPS_OUT,
    # STYLE_BAR_THICKNESS und STYLE_DOCK_ICON_SIZE sind derselbe Fall
    # daneben: alle drei bleiben unitless, weil ihre Leser ebenfalls
    # `const X = {{STYLE_*}}` in TypeScript oder ein zahliges Feld in
    # hyprland-universal-config.template sind.
    **{f"STYLE_MODAL_WIDTH_{name}": str(px)
       for name, px in sizes.MODAL_WIDTHS.items()},

    # ============================================================================
    # DIE ABGESETZTE KANTE - der 3D-Effekt aus summer-day-and-night
    # ============================================================================
    #
    # NACHGEBAUT UND NICHT UEBERNOMMEN: das Vorbild hat keine Lizenz, also
    # ist von dort nur die MESSUNG genommen. Sie faerbt jede Kante als
    # dunklere Fassung der Flaeche darueber - die Leiste #d3c6aa mit
    # #7d6a40 darunter, die Kacheln #343a3f mit #161a1d. Ihre Farben sind
    # Everforest und kaemen hier gar nicht in Frage; uebernommen ist die
    # REGEL "eine Stufe dunkler als das, was daraufsteht".
    #
    # EINE KANTENFARBE UND NICHT ZWEI, und das ist gemessen. Die Kante des
    # Vorbilds steht bei seiner hellen Leiste auf 3.10:1 gegen die Flaeche
    # darueber, bei seinen dunklen Kacheln auf 1.52:1 - dieselbe Regel,
    # zwei sehr verschiedene Ergebnisse, weil man unter #343a3f kaum noch
    # dunkler werden kann. Die ganze ZepOS-Palette liegt im dunklen
    # Register, also landet sie im zweiten Fall: THEME.INK misst 1.76:1
    # gegen das Panel (SHADE_1) und 1.34:1 gegen eine Kachel (PETROL).
    # Beide klammern die 1.52 des Vorbilds ein.
    #
    # Zwei Namen fuer denselben Wert waeren hier genau die Doppelung,
    # gegen die diese Datei sonst argumentiert - also einer, und seit dem
    # 12.08.2026 nur noch der fuer Hyprland.
    #
    # STYLE_BAR_SHELF_COLOR stand hier daneben und hatte genau zwei
    # Leser, beide in bar-style.template: die Kante unter #bar und die
    # unter .bar-module. Der Nutzer am 12.08.2026, nachdem er die Bilder
    # gesehen hatte: "entferne bitte diese 3d aussehen von hier sodass
    # sie matched mit dem footer". Beide Kanten sind fort, also auch der
    # Name - Regel 14 dieses Projekts, keine tote Zeile "fuer spaeter".
    #
    # Am FENSTER bleibt die Kante: Hyprlands `shadow` mit range 0 und
    # `offset = 0 STYLE_BAR_SHELF` ist dort die Kante eines Fensters und
    # keine zweite Ebene in einer Leiste. Sie liest den Wert unten.

    # Die Kantenfarbe fuer Hyprland, ohne das Doppelkreuz.
    #
    # In einer Hyprland-Konfiguration beginnt `#` einen KOMMENTAR. Ein
    # `color = #08262C` im Schattenblock ist dort also `color = ` und
    # nichts weiter, und Hyprland sagt dazu "cannot parse "" as an int" -
    # gemessen am 11.08.2026 an genau dieser Zeile, gefangen von
    # tests/src/test_plugins.py. Die Schreibweise ist `rgb(08262C)`, und
    # dieselbe Loesung steht seit jeher zwei Bloecke weiter oben bei
    # col.active_border.
    "STYLE_BAR_SHELF_COLOR_RAW": THEME.INK.lstrip("#"),

    # ============================================================================
    # GLAS - EINE PLATTE, UND ZWAR UEBERALL DIESELBE
    # ============================================================================
    #
    # Die Deckkraft steht in brand.py, samt der Rechnung, aus der sie
    # kommt. Hier wird sie zu dem, was ein GTK4-Stylesheet lesen kann.
    #
    # WAS HIER BIS ZUM 12.08.2026 DANEBEN STAND
    #     STYLE_GLASS_PANEL (SHADE_1 @ 0.55) und STYLE_GLASS_CHIP
    #     ("background" @ 0.70) - die zwei Schichten der Leiste. Sie
    #     hatten genau zwei Leser, `#bar` und `.bar-module`, und beide
    #     sind fort. Der Nutzer, nachdem er die Bilder gesehen hatte:
    #     "die icon sollen im header nicht nochmal ein element haben weil
    #     ich die icons seperat von dem hintergrund der waybar erkennen
    #     kann". Die Kachel WAR dieses zweite Element.
    #
    #     Damit ist jede Flaeche dieses Schreibtischs einschichtig, und
    #     zwei Namen ohne Leser haben hier nichts mehr zu suchen (Regel
    #     14). Die zwei Deckkraefte in src/brand.py bleiben, aber sie
    #     werden nicht mehr GEMALT - sie sind nur noch das, woraus
    #     glass_solo_alpha() und glass_ignore_alpha() rechnen.
    #
    #     GEMESSEN, was das den Text kostet: NICHTS, es bringt ihm etwas.
    #     bar_text auf der Platte, ueber der hellsten bzw. dunkelsten
    #     denkbaren Tapete, Thema ZeptronIT:
    #
    #         Kachel 0.70 auf Platte 0.55   6.33 / 10.62   bis heute
    #         diese Platte (overlay_bg)     8.64 / 14.06
    #
    #     Der Grund ist die FARBE und nicht die Zahl der Schichten:
    #     overlay_bg ist dunkler als "background", und der Text ist hell.
    "STYLE_GLASS_IGNORE_ALPHA": str(THEME.GLASS_IGNORE_ALPHA),

    # DIE PLATTE.
    #
    # Warum die Deckkraft 0.86 und nicht 0.70 ist, steht in src/brand.py
    # bei glass_solo_alpha() - kurz: eine einzelne Schicht muss so viel
    # Material tragen wie zwei gestapelte, weil derselbe Text darauf
    # gelesen wird.
    #
    # Sie liegt seit dem 12.08.2026 unter ALLEM: den zwoelf Ueberlagerungen,
    # dem Starter, dem Menue, der Zwischenablage - und jetzt auch unter
    # der Leiste und dem Fuss. "sodass sie matched mit dem footer" ist
    # damit keine Aehnlichkeit, sondern derselbe Wert.
    "STYLE_GLASS_SOLO": THEME.rgba(get_user_color("overlay_bg"),
                                   THEME.GLASS_SOLO_ALPHA),

    # Der Melder hat eigene Farbschluessel (notification_bg), und bis
    # heute erreichten sie nur mako: die AGS-Karte malte $bg, also
    # overlay_bg. Wer im Farbwaehler "Benachrichtigung / Hintergrund"
    # verstellte, aenderte damit den einen Melder und nicht den anderen.
    "STYLE_GLASS_NOTIFICATION": THEME.rgba(get_user_color("notification_bg"),
                                           THEME.GLASS_SOLO_ALPHA),

    # Die oberste Sprosse der Dringlichkeitsleiter. Bis zum 12.08.2026
    # stand hier im Stylesheet ein hartes #1a0c0c - eine Farbe, die kein
    # Thema anfassen kann, ausgerechnet an der Meldung, die am meisten
    # auffallen muss. Unter "Tageslicht" wurde der ganze Schreibtisch
    # hell und die kritische Meldung blieb fast schwarz.
    #
    # THEME.STATE_CRITICAL_BG ist derselbe Grund, den die Hardwarezeilen
    # fuer ihren kritischen Zustand nehmen: ein Rot, so weit zum Grund
    # genommen, dass die Schrift darauf haelt.
    #
    # BIS ZUM 19.08.2026 (Aufgabe 26) legte auch zepos-logout sein
    # "Ausschalten" auf diese Sprosse - eine DRITTE Stelle, die mit dem
    # C-Programm gefallen ist. Sein Nachfolger ags-logout.template
    # benutzt zepButton() und dessen Rolle "kritisch" (ags-style.
    # template, .zep-btn-kritisch), keine eigene Farbe mehr aus dieser
    # Sprosse - die Leiter hat damit an zwei Stellen dieselben Sprossen,
    # nicht mehr an drei.
    "STYLE_GLASS_NOTIFICATION_CRITICAL": THEME.rgba(THEME.STATE_CRITICAL_BG,
                                                    THEME.GLASS_SOLO_ALPHA),

    # ============================================================================
    # EWW WINDOW GEOMETRY - the same on every screen
    # ============================================================================
    #
    # The window SIZES that follow from the screen a widget opens on live
    # in _monitor_style_variables() at the end of the file. What is left
    # here is per-monitor in name only: a placeholder per screen, the
    # same value in each, so a template can address them uniformly.
    # Reading them must not cost a compositor query.
    **_per_screen({
        "STYLE_EWW_POS_X":                    "20px",
        "STYLE_EWW_POS_Y":                    "55px",
        "STYLE_EWW_DISK_RING_SIZE":           "150",
        "STYLE_EWW_DISK_RING_THICKNESS":      "12",
        "STYLE_EWW_THUMB_WIDTH":              "100",
        "STYLE_EWW_THUMB_HEIGHT":             "65",
    }),

    # ============================================================================
    # EWW ELEMENT SIZES - FIXED (Full HD base, same for all monitors)
    # ============================================================================
    **_per_screen({
        "STYLE_EWW_MIN_WIDTH_TINY":           "16px",
        "STYLE_EWW_MIN_WIDTH_SM":             "22px",
        "STYLE_EWW_MIN_WIDTH_MD":             "32px",
        "STYLE_EWW_MIN_WIDTH_LG":             "40px",
        "STYLE_EWW_MIN_WIDTH_XL":             "60px",
        "STYLE_EWW_MIN_WIDTH_BTN":            "80px",
        "STYLE_EWW_MIN_WIDTH_BTN_LG":         "90px",
        "STYLE_EWW_MIN_WIDTH_BTN_XL":         "100px",
        "STYLE_EWW_MIN_WIDTH_SECTION":        "100px",
        "STYLE_EWW_MIN_WIDTH_KEY":            "155px",
        "STYLE_EWW_MIN_WIDTH_COL":            "260px",
        "STYLE_EWW_MIN_WIDTH_POPUP":          "340px",
        "STYLE_EWW_MIN_WIDTH_POPUP_LG":       "350px",
        "STYLE_EWW_MIN_WIDTH_DISK":           "460px",
        "STYLE_EWW_MIN_WIDTH_SHORTCUTS":      "600px",
        "STYLE_EWW_MIN_WIDTH_CALENDAR":       "380px",
        "STYLE_EWW_MIN_WIDTH_SCALE":          "250px",
        "STYLE_EWW_MIN_WIDTH_SCALE_LG":       "280px",
        "STYLE_EWW_MIN_HEIGHT_ROW":           "22px",
        "STYLE_EWW_MIN_HEIGHT_ROW_MD":        "28px",
        "STYLE_EWW_MIN_HEIGHT_BAR":           "6px",
        "STYLE_EWW_MIN_HEIGHT_BAR_MD":        "8px",
        "STYLE_EWW_MIN_HEIGHT_BAR_LG":        "10px",
        "STYLE_EWW_MIN_HEIGHT_BAR_XL":        "12px",
        "STYLE_EWW_MIN_HEIGHT_SLIDER":        "16px",
        "STYLE_EWW_MIN_HEIGHT_INPUT":         "20px",
    }),

    # EWW GLOBAL VALUES - "dynamically calculated from widget heights"
    # stand hier bis zum 18.08.2026, ueber fuenf Eintraegen
    # (STYLE_EWW_SCROLL_DISK und vier Geschwister ohne MON-Suffix), die
    # get_user_widget_size() gegen die Aufloesung "1920" fest verdrahtet
    # aufriefen - selbst auf einem 4K-Schirm. GEMESSEN am 18.08.2026,
    # `grep -rl` gegen src/templates/ UND src/styles/: keine dieser fuenf
    # Zeichenketten hatte einen Leser. Sie fielen mit der Kette, die sie
    # speiste - siehe die Notiz bei _monitor_style_variables().
    "STYLE_EWW_DISK_RING_SIZE": "150",
    "STYLE_EWW_DISK_RING_THICKNESS": "12",
    "STYLE_EWW_MIN_WIDTH_KEY": "155px",
    "STYLE_EWW_MIN_WIDTH_COL": "260px",
    "STYLE_EWW_MIN_WIDTH_SHORTCUTS": "600px",

    # ============================================================================
    # DIE SCHRIFTLEITER UND IHRE SYMBOLE
    # ============================================================================
    #
    # EINE Leiter, nicht fuenf. Sie stand hier zweimal: einmal global und
    # einmal durch _per_screen() pro Bildschirmplatz, also 14 + 70 Namen
    # fuer 14 Zahlen.
    #
    # Die fuenf Kopien pro Platz sind ersatzlos weg, und das ist keine
    # Aufraeumarbeit, sondern eine Unmoeglichkeit: ags-style.template ist
    # EIN Stylesheet fuer alle Schirme. GTK-CSS kennt keinen Selektor fuer
    # einen Monitor, also kann eine Regel darin gar nicht sagen "auf dem
    # zweiten Schirm 16 px". Siebzig Platzhalter, die ihr einziger
    # moeglicher Leser strukturell nicht benutzen kann.
    #
    # Dasselbe Argument gilt fuer die Leiste: bar-style.template ist
    # ebenfalls ein Stylesheet fuer alle Leisten. Deshalb ist auch der
    # Faktor oben EINER und keine Tabelle pro Aufloesungsklasse.
    #
    # SEIT DEM 12.08.2026 SIND ES ROLLEN UND KEINE PIXELWERTE. Was hier
    # stand, waren sechzehn Namen der Form STYLE_EWW_FONT_14 - einer pro
    # Pixelwert, den irgendwann jemand gebraucht hatte. src/sizes.py
    # traegt die Messung, aus der die sieben Rollen und das Verhaeltnis
    # 1.2 kommen; hier ist nur die Stelle, an der sie zu Platzhaltern
    # werden.
    #
    # Jede Rolle zweimal: als Schrift und als die Hoehe der Zeile, in der
    # ein Symbolzeichen steht. Das ist der Unterschied, den der Katalog
    # nicht ausdruecken konnte - `.cc-label` und `.cc-icon` standen beide
    # auf 14, obwohl das eine ein Wort ist und das andere ein Bild.
    #
    # sizes.ICON_ROLES und nicht sizes.FONT_ROLES fuer die zweite Haelfte
    # (18.08.2026, task-C): DISPLAY hat keinen Symbol-Leser mehr, siehe
    # die Begruendung bei ICON_ROLES in src/sizes.py. sizes.TABLE traegt
    # "STYLE_ICON_DISPLAY" darum nicht mehr, und size_value() darauf
    # waere ein KeyError - dieselbe Rolle bleibt als Schrift bestehen,
    # nur nicht mehr als Symbolgroesse.
    **{f"{sizes.FONT_PREFIX}{role}": size_value(f"{sizes.FONT_PREFIX}{role}")
       for role, _step in sizes.FONT_ROLES},
    **{f"{sizes.ICON_PREFIX}{role}": size_value(f"{sizes.ICON_PREFIX}{role}")
       for role, _step in sizes.ICON_ROLES},

    # ============================================================================
    # DIE RUNDUNGSLEITER
    # ============================================================================
    #
    # src/sizes.py haelt die Sprossen und die Messung, aus der sie kommen:
    # 54 rechte Ecken in ags-style.template, davon elf auf Glasscheiben,
    # neben sechs Radius-Platzhaltern mit null Lesern.
    **{f"{sizes.RADIUS_PREFIX}{role}":
       size_value(f"{sizes.RADIUS_PREFIX}{role}")
       for role, _step in sizes.RADIUS_ROLES},

    # Der Kreis. Kein Eintrag in sizes.TABLE, weil er keine Laenge ist:
    # 50 % einer Breite ist bei jedem Faktor ein Kreis, und ein Wert, der
    # dem Regler nicht folgen KANN, gehoert nicht in eine Tabelle, deren
    # ganzer Zweck der Regler ist.
    f"{sizes.RADIUS_PREFIX}FULL": sizes.RADIUS_FULL,
    f"{sizes.RADIUS_PREFIX}PILL": sizes.RADIUS_PILL,

    # ============================================================================
    # DIE GRENZEN
    # ============================================================================
    #
    # In Zeichen und nicht in Pixeln - src/sizes.py sagt, warum, und
    # nennt die Quelle fuer die 45 und die 66.
    **{f"{sizes.MEASURE_PREFIX}{name}":
       size_value(f"{sizes.MEASURE_PREFIX}{name}")
       for name in ("LINE", "PROSE")},

    # ============================================================================
    # DIE ABSTANDSLEITER
    # ============================================================================
    #
    # src/sizes.py haelt die Sprossen, die Grundeinheit und die Messung,
    # aus der beide kommen. Hier ist nur die Stelle, an der sie zu
    # Platzhaltern werden - dieselbe Form wie bei der Schriftleiter
    # darueber, und aus demselben Grund an derselben Stelle.
    #
    # WAS HIER STAND UND WARUM ES WEG IST
    #     STYLE_EWW_SPACE_TINY bis _XXL, acht Namen, und noch einmal
    #     dieselben acht durch _per_screen() pro Bildschirmplatz - also
    #     48 Platzhalter fuer acht Zahlen. GEMESSEN am 11.08.2026: KEINE
    #     EINZIGE Vorlage nannte auch nur einen davon, waehrend
    #     ags-style.template daneben 294 Abstandszahlen ausschrieb.
    #
    #     Das ist genau der Zustand, in dem MONITOR_HEIGHT_SCALES war,
    #     und die Leiter hatte dazu dieselben zwei Fehler wie die alte
    #     Schriftleiter: die Namen sagten TINY/XS/SM statt der Zahl, also
    #     waere jede Ersetzung im Stylesheet eine Ermessensentscheidung
    #     gewesen; und die fuenf Kopien pro Platz waren nicht ungenutzt,
    #     sondern unbenutzbar, weil GTK-CSS keinen Selektor fuer einen
    #     Monitor kennt.
    #
    #     Die Leiter, die jetzt hier steht, traegt die Zahl im Namen,
    #     steht genau einmal da und folgt dem Faktor. tests/src/
    #     test_spacing.py haelt sie gegen die Stylesheets und faellt um,
    #     sobald wieder eine nackte Zahl in einer padding- oder
    #     margin-Regel steht.
    **{f"{sizes.SPACE_PREFIX}{step}":
       size_value(f"{sizes.SPACE_PREFIX}{step}")
       for step in sizes.SPACE_LADDER},

    # The whole shipped palette, as a JSON object, for the one artifact
    # that needs to know what a colour would be if the user had never
    # touched it: the style editor's "reset" and its picker's starting
    # point. It carried its own copy of all ninety-nine values until
    # now - the third one, and the one that disagreed with the other two
    # about `warning`.
    #
    # sort_keys so the generated file is a function of the palette and
    # not of dict insertion order, which would make every regeneration
    # look like a change.
    "STYLE_BRAND_COLORS_JSON": json.dumps(THEME.COLORS, sort_keys=True, indent=2),

    # Wie die neunundneunzig gruppiert und benannt werden, wenn sie
    # jemandem vorgelegt werden - THEME.COLOR_GROUPS, in der Form, die
    # der Stil-Editor bisher als Literal trug.
    #
    # NICHT sort_keys, und das ist hier der Unterschied: die Reihenfolge
    # IST die Aussage. "Status" steht vor "Dock", weil man eher eine
    # Warnfarbe sucht als die Farbe eines Dock-Anzeigers, und
    # "background" steht in seiner Gruppe zuerst, weil alles darunter
    # gegen es gelesen wird. Alphabetisch waere aus einer begruendeten
    # Reihenfolge eine zufaellige geworden.
    #
    # Die Form ist die des Literals, das hier bis zum 12.08.2026 im
    # Editor stand - [{name, colors: [{key, label}]}] -, damit die
    # Ersetzung dort eine Ersetzung ist und keine Umschreibung.
    "STYLE_COLOR_GROUPS_JSON": json.dumps(
        [{"name": name,
          "colors": [{"key": key, "label": label} for key, label in rows]}
         for name, rows in THEME.COLOR_GROUPS],
        ensure_ascii=False, indent=2),

    # Background & Opacity (user-configurable via user-settings.json)
    "STYLE_BG_COLOR": get_user_color("background"),
    "STYLE_BG_TRANSPARENT": "rgba(13, 61, 71, 0)",
    "STYLE_MODULE_BG": "rgba(13, 61, 71, 0.5)",

    # ============================================================================
    # DIE LEISTE (user-configurable via user-settings.json)
    # ============================================================================
    #
    # Hier standen dreizehn Namen - STYLE_COLOR_WAYBAR_BG bis
    # _WAYBAR_TRAY -, und GEMESSEN am 11.08.2026 las KEINE Vorlage auch
    # nur einen davon. Zehn von ihnen waren ausserdem Doppelungen: die
    # Modulfarben weiter unten lesen dieselben Schluessel und WERDEN
    # gelesen.
    #
    # Von den drei, die damals uebrig blieben, ist am 12.08.2026 noch
    # eine gefallen: STYLE_COLOR_BAR_BG las "bar_bg", und auch dieser
    # Platzhalter kam in keiner Vorlage vor. Die Leiste nimmt ihren
    # Grund aus STYLE_GLASS_PANEL und ihre Kacheln aus
    # STYLE_GLASS_CHIP, und beide werden aus "background" gebaut. Der
    # Schluessel "bar_bg" ist mit ihm geloescht - siehe den Kopf von
    # src/brand.py, Abschnitt COLOR_GROUPS.
    "STYLE_COLOR_BAR_TEXT": get_user_color("bar_text"),

    # HIER STAND STYLE_COLOR_BAR_TRAY, UND ES WAR EIN KLOTZ (12.08.2026)
    #     `get_user_color("bar_tray")`, ein sechsstelliges Hex ohne
    #     Alphakanal, und in bar-style.template ueberschrieb es den Grund
    #     der Ablage. GEMESSEN auf out/render/schreibtisch-1920.png,
    #     frische Sitzung, kein Programm mit Ablagesymbol: ein
    #     volldeckender Block (33, 79, 89) von 30x47 Bildpunkten bei
    #     x=1707..1736, zwischen "87%" und den drei Symbolknoepfen. Eine
    #     LEERE Ablage malte einen Klotz in eine durchscheinende Leiste -
    #     im haeufigsten Zustand ueberhaupt.
    #
    #     Zwei Dinge sind dagegen geschehen, und beide sind noetig: die
    #     Ablage malt gar keinen Grund mehr (dieselbe Forderung, die
    #     jedem Modul seine Kachel genommen hat), und die Box macht sich
    #     unsichtbar, solange kein Programm ein Symbol angemeldet hat -
    #     siehe Tray() in ags-tray.template.
    #
    # UND WAS DIE ROLLE STATTDESSEN JETZT TUT
    #     Sie faerbt den ZEIGEREFFEKT der Ablagesymbole, und das
    #     schliesst eine Luecke, die vorher niemandem auffiel, weil der
    #     Klotz sie verdeckt hat: `#tray button.tray-item` steht auf
    #     `background: transparent` und hatte KEINE :hover-Regel. Jedes
    #     andere Bedienelement der Leiste hebt sich unter dem Zeiger
    #     hervor, die Ablagesymbole nicht - und sie sind anklickbar,
    #     dreifach sogar (Activate, SecondaryActivate, ContextMenu).
    #
    #     Ein Zustand und keine Ruheflaeche: der Nutzer hat "nicht
    #     nochmal ein element" verlangt, und ein Hervorheben, das nur
    #     unter dem Zeiger existiert, ist keines. Der Vorgabewert
    #     (SHADE_1) ist derselbe wie STYLE_HOVER_BG, die Ablage sieht
    #     also aus wie ihre Nachbarn - nur dass sie fuer sich verstellbar
    #     bleibt, weil sie als einzige FREMDE Symbole traegt, deren
    #     Farben dieses Projekt nicht kennt.
    "STYLE_COLOR_BAR_TRAY": get_user_color("bar_tray"),

    # ============================================================================
    # HYPRLAND BARS (user-configurable via user-settings.json)
    # ============================================================================
    "STYLE_COLOR_HYPRLAND_ACTIVE_BORDER": get_user_color("hyprland_active_border"),
    "STYLE_COLOR_HYPRLAND_INACTIVE_BORDER": get_user_color("hyprland_inactive_border"),
    "STYLE_COLOR_HYPRLAND_ACTIVE_BORDER_RAW": get_user_color("hyprland_active_border").lstrip("#"),
    "STYLE_COLOR_HYPRLAND_INACTIVE_BORDER_RAW": get_user_color("hyprland_inactive_border").lstrip("#"),
    "STYLE_COLOR_HYPRBAR_BG": get_user_color("hyprbar_bg"),
    "STYLE_COLOR_HYPRBAR_TEXT": get_user_color("hyprbar_text"),
    "STYLE_COLOR_HYPRBAR_CLOSE": get_user_color("hyprbar_close"),
    "STYLE_COLOR_HYPRBAR_MINIMIZE": get_user_color("hyprbar_minimize"),
    "STYLE_COLOR_HYPRBAR_MAXIMIZE": get_user_color("hyprbar_maximize"),

    # ============================================================================
    # HIER STANDEN EINUNDZWANZIG WEITERE FARBPLATZHALTER
    # ============================================================================
    # Neun EWW_*, sechs CALENDAR_*, drei DISK_* und drei HARDWARE_*.
    # GEMESSEN am 12.08.2026, mit demselben Verfahren, das oben schon die
    # dreizehn WAYBAR_* gefaellt hat: jede Farbe einzeln auf einen
    # Sentinel gesetzt, die Stil-SSOT neu eingelesen, und nachgesehen,
    # welcher Platzhalter sich bewegt und ob ihn eine Vorlage nennt.
    # Keiner dieser einundzwanzig wird von einer Vorlage genannt.
    #
    # Es waren also einundzwanzig Regler im Stil-Editor, die sich
    # anfassen liessen wie Regler, in der Einstellungsdatei landeten wie
    # Regler und kein erzeugtes Byte veraenderten - dieselbe Geschichte
    # wie MONITOR_HEIGHT_SCALES und wie "fonts"/"spacing" in
    # user_settings.py, nur mit einundzwanzig Namen statt mit vieren.
    #
    # Die Ueberlagerungen nehmen ihre Farben aus den OVERLAY_*-
    # Schluesseln, die Widgets ihren Akzent aus den *_accent-
    # Schluesseln; beide werden gelesen. Die Schluessel selbst sind mit
    # den Platzhaltern geloescht, weil ein Schluessel ohne Leser eine
    # Einstellung ohne Wirkung ist - src/brand.py, COLOR_GROUPS, fuehrt
    # die Messung.

    # ============================================================================
    # WALLPAPER COLORS (user-configurable via user-settings.json)
    # ============================================================================
    "STYLE_COLOR_WALLPAPER_LANDSCAPE": get_user_color("wallpaper_landscape"),

    # ============================================================================
    # TERMINAL (KITTY) COLORS (user-configurable via user-settings.json)
    # ============================================================================
    "STYLE_COLOR_TERMINAL_BG": get_user_color("terminal_bg"),
    "STYLE_COLOR_TERMINAL_FG": get_user_color("terminal_fg"),
    "STYLE_COLOR_TERMINAL_CURSOR": get_user_color("terminal_cursor"),
    "STYLE_COLOR_TERMINAL_SELECTION": get_user_color("terminal_selection"),
    "STYLE_COLOR_TERMINAL_ACTIVE_TAB_FG": get_user_color("terminal_active_tab_fg"),
    "STYLE_COLOR_TERMINAL_ACTIVE_TAB_BG": get_user_color("terminal_active_tab_bg"),
    "STYLE_COLOR_TERMINAL_INACTIVE_TAB_FG": get_user_color("terminal_inactive_tab_fg"),
    "STYLE_COLOR_TERMINAL_INACTIVE_TAB_BG": get_user_color("terminal_inactive_tab_bg"),

    # ============================================================================
    # PROMPT (POWERLEVEL10K) COLORS (user-configurable via user-settings.json)
    # ============================================================================
    # Sie landen in ~/.p10k.zsh, das p10k-config.template erzeugt.
    # powerlevel10k nimmt eine Farbe als Namen, als Zahl 0-255 oder als
    # #rrggbb (internal/p10k.zsh, _p9k_translate_color) - also genau in
    # der Schreibweise, in der sie hier ohnehin stehen. Waere das nicht
    # so, muesste hier eine Umrechnung auf die 256er-Palette stehen, und
    # die Marke haette im Terminal andere Farben als daneben.
    "STYLE_COLOR_PROMPT_PATH": get_user_color("prompt_path"),
    "STYLE_COLOR_PROMPT_VCS_CLEAN": get_user_color("prompt_vcs_clean"),
    "STYLE_COLOR_PROMPT_VCS_DIRTY": get_user_color("prompt_vcs_dirty"),
    "STYLE_COLOR_PROMPT_OK": get_user_color("prompt_ok"),
    "STYLE_COLOR_PROMPT_ERROR": get_user_color("prompt_error"),
    "STYLE_COLOR_PROMPT_CONTEXT": get_user_color("prompt_context"),
    "STYLE_COLOR_PROMPT_TIME": get_user_color("prompt_time"),

    # Notification (Mako) Colors
    "STYLE_COLOR_NOTIFICATION_BG": get_user_color("notification_bg"),
    "STYLE_COLOR_NOTIFICATION_TEXT": get_user_color("notification_text"),
    "STYLE_COLOR_NOTIFICATION_BORDER": get_user_color("notification_border"),
    "STYLE_COLOR_NOTIFICATION_PROGRESS": get_user_color("notification_progress"),
    "STYLE_COLOR_NOTIFICATION_LOW_TEXT": get_user_color("notification_low_text"),
    "STYLE_COLOR_NOTIFICATION_LOW_BORDER": get_user_color("notification_low_border"),
    "STYLE_COLOR_NOTIFICATION_CRITICAL_TEXT": get_user_color("notification_critical_text"),
    "STYLE_COLOR_NOTIFICATION_CRITICAL_BORDER": get_user_color("notification_critical_border"),

    # nwg-dock Colors
    "STYLE_COLOR_DOCK_ICON": get_user_color("dock_icon"),
    "STYLE_COLOR_DOCK_INDICATOR": get_user_color("dock_indicator"),

    # HIER STANDEN ZEHN MODULFARBEN, UND SIE HABEN DIE LEISTE MONOTON
    # GEMACHT
    #
    # STYLE_COLOR_DATE, _CLOCKS, _FLOATING_LAYOUTS, _WEATHER, _WORKSPACE,
    # _NETWORK, _BLUETOOTH, _BATTERY, _AUDIO und _MICROPHONE - je eine
    # Farbe fuer den RUHEZUSTAND eines Moduls, gelesen aus je einem
    # bar_*-Schluessel.
    #
    # GEMELDET am 12.08.2026: "die icons im header sollen auch nicht
    # alle zepdesk farben tragen weil es sonst voll monoton aussieht".
    # Die Messung dazu - zehn von neunzehn Farben in einem Fenster von
    # dreieinhalb Grad Farbton, und die Warnfarbe Byte fuer Byte
    # dieselbe wie die des Datums - steht im Kopf von
    # src/styles/bar-style.template.
    #
    # Ein Modul im Ruhezustand erbt jetzt die Textfarbe der Leiste.
    # Farbe bedeutet ab hier ZUSTAND, und die Zustandsfarben stehen
    # weiter unten. Die zugehoerigen Schluessel sind in src/brand.py
    # mitgegangen: ein Regler, den keine Vorlage mehr liest, ist genau
    # das, wogegen die COLOR_GROUPS-Messung dort gebaut ist.
    "STYLE_COLOR_WORKSPACE_VISIBLE": get_user_color("bar_workspace_visible"),
    # Was #3d0000 - a near-black red used as the TEXT colour of an
    # urgent workspace, 1.4:1 on the module behind it. The one state
    # on the bar that exists to be noticed was the only one that could
    # not be read. THEME.RED is 5.21:1 on the same background.
    "STYLE_COLOR_WORKSPACE_URGENT": THEME.RED,
    "STYLE_COLOR_HARDWARE": get_user_color("accent"),

    # Grid Wallpaper Colors
    #
    # Read from the settings rather than written out here. All six values
    # below are the DEFAULTS of keys the style editor already offers
    # ("Grid Linien", "Grid Hintergrund", "Footprint Farbe" ...) and that
    # user_settings.DEFAULT_SETTINGS already carries - they were simply
    # never read, so changing any of them in the editor moved a value
    # into the settings file and left the grid exactly as it was.
    #
    # The outer frame takes "grid" as well: the editor offers one colour
    # for the grid's lines, and the frame is the outermost of them. Two
    # settings for one visible thing would be a control that appears to
    # do half its job.
    "STYLE_COLOR_GRID": get_user_color("grid"),
    "STYLE_COLOR_GRID_BORDER": get_user_color("grid"),
    "STYLE_COLOR_GRID_BG": get_user_color("grid_bg"),
    "STYLE_COLOR_FOOTPRINT": get_user_color("footprint"),
    "STYLE_COLOR_FOOTPRINT_BG": get_user_color("footprint_bg"),
    "STYLE_COLOR_FOOTPRINT_TEXT": get_user_color("footprint_text"),
    
    # Status Colors (user-configurable via user-settings.json)
    "STYLE_COLOR_WARNING": get_user_color("warning"),
    "STYLE_COLOR_CRITICAL": get_user_color("critical"),
    "STYLE_COLOR_OFFLINE": get_user_color("inactive"),
    "STYLE_COLOR_SUCCESS": get_user_color("success"),
    "STYLE_COLOR_SUCCESS_DIM": get_user_color("success_dim"),
    "STYLE_COLOR_INACTIVE": get_user_color("inactive"),
    "STYLE_COLOR_GAMING": get_user_color("critical"),

    # A second set of widget colours stood here - CLIPBOARD, TEXT,
    # SUBTEXT, FAVORITE, LAUNCHER, CALENDAR, SHORTCUTS, DISK, CONTROL,
    # NETWORK, WALLPAPER, STYLE - reading the settings "clipboard",
    # "text", "network" and so on. It is gone, because it did damage
    # rather than nothing:
    #
    #   * no template named a single one of those placeholders, and no
    #     key it read exists in user_settings.DEFAULT_SETTINGS or in the
    #     style editor. The AGS widgets take their colours from the
    #     *_accent keys further down, which ARE offered and ARE read.
    #   * its STYLE_COLOR_NETWORK was the SECOND definition of that name
    #     in this dict. The later one wins, so the one placeholder of the
    #     twelve that a template does use - {{STYLE_COLOR_NETWORK}} in
    #     styles/bar-style.template, the network module - was
    #     coloured from "network", a setting nothing offers, while
    #     "bar_network" (the style editor's "Netzwerk/WLAN Modul",
    #     and the key beside bar_bluetooth and bar_battery, which
    #     do reach their modules) changed nothing at all.
    #
    # The module colour is defined once now, above, from bar_network.

    # Opacity Values
    "STYLE_OPACITY_DISABLED": "0.6",
    "STYLE_OPACITY_FULL": "1.0",
    
    # ============================================================================
    # FONT (fixed - NOT scaled, these affect the bar globally)
    # ============================================================================
    "STYLE_FONT_FAMILY": THEME.FONT_FAMILY_CODE,
    "STYLE_FONT_FAMILY_TEXT": THEME.FONT_FAMILY_TEXT,
    # The bare family names, for the configuration formats that take a
    # name rather than a CSS list - kitty and hyprbars.
    "STYLE_FONT_NAME_CODE": THEME.FONT_CODE,
    "STYLE_FONT_NAME_TEXT": THEME.FONT_TEXT,
    "STYLE_FONT_NAME_ICONS": THEME.FONT_ICONS,
    "STYLE_FONT_WEIGHT": "bold",
    # STYLE_FONT_SIZE 13, _SMALL 12 und _LARGE 14 standen hier - drei
    # Namen fuer drei Zahlen, die einen Pixel auseinanderliegen, und
    # keiner sagte, WOFUER er da war. Sie stehen jetzt auf den Rollen
    # BODY, CAPTION und LEAD der Schriftleiter in src/sizes.py.
    #
    # _LARGE ist dabei auf LEAD (16) gegangen und nicht auf die naechste
    # Sprosse (BODY, 13), obwohl 13 naeher an 14 liegt. Der Grund steht
    # im Kommentar, den es hier abloest: es ist "the one control on a
    # surface that is the reason the surface is open - the launcher's
    # search box". Das IST die Rolle LEAD, und eine Rollenleiter
    # entscheidet nach der Rolle und nicht nach dem Abstand.

    # Die Schrift im Terminal. In Punkt und ohne Einheit, weil kitty
    # nichts anderes annimmt - warum sie trotzdem an demselben Regler
    # haengt wie alles andere, steht bei STYLE_TERMINAL_FONT_SIZE in
    # src/sizes.py.
    "STYLE_TERMINAL_FONT_SIZE": size_value("STYLE_TERMINAL_FONT_SIZE"),

    # ============================================================================
    # DIE BEWEGUNGSLEITER
    # ============================================================================
    #
    # src/sizes.py haelt die drei Dauern, die eine Kurve und die Messung,
    # aus der beide kommen. Hier ist nur die Stelle, an der sie zu
    # Platzhaltern werden.
    #
    # WAS HIER STAND
    #     STYLE_TRANSITION_DEFAULT = "all 0.3s ease" - eine Zeichenkette
    #     aus drei Entscheidungen (was, wie lange, welche Kurve), von
    #     denen keine einzeln erreichbar war. Wer eine Regel schreiben
    #     wollte, die nur die Farbe uebergehen laesst, musste die Dauer
    #     und die Kurve daneben neu hinschreiben.
    #
    #     Die Dauer und die Kurve stehen deshalb getrennt, und die
    #     Eigenschaft nennt die Regel selbst - `transition: background
    #     {{STYLE_MOTION_INSTANT}} {{STYLE_MOTION_CURVE}}`.
    **{f"{sizes.MOTION_PREFIX}{role}":
       size_value(f"{sizes.MOTION_PREFIX}{role}")
       for role, _step in sizes.MOTION_ROLES},

    # Dieselben drei Dauern in Zehntelsekunden, fuer den Compositor.
    # Nicht als eigene Eintraege in sizes.TABLE, weil es dieselbe
    # Einstellung ist und nicht eine zweite - motion_hyprland_speed()
    # rechnet den EINGESTELLTEN Wert um, nicht den Grundwert.
    **{f"{sizes.MOTION_PREFIX}{role}_HYPR":
       sizes.motion_hyprland_speed(role,
                                   sizes.settings_section(USER_SETTINGS))
       for role, _step in sizes.MOTION_ROLES},

    # Der Schalter, in den zwei Schreibweisen seiner zwei Leser.
    f"{sizes.MOTION_PREFIX}ENABLED_HYPR": sizes.motion_curve_hyprland_toggle(
        sizes.settings_section(USER_SETTINGS)),
    f"{sizes.MOTION_PREFIX}ENABLED_GTK": sizes.motion_gtk_toggle(
        sizes.settings_section(USER_SETTINGS)),

    # Die Grundschrift, wie Pango sie annimmt - Familie und Punkt. Der
    # einzige Weg, auf dem eine Anwendung, die dieses Projekt nicht
    # geschrieben hat, die GROESSE dieses Schreibtischs erfaehrt.
    "STYLE_GTK_FONT_NAME": (
        f"{THEME.FONT_TEXT} "
        f"{sizes.gtk_font_points(sizes.settings_section(USER_SETTINGS))}"),

    # Die eine Kurve, in den zwei Schreibweisen, die ihre zwei Leser
    # verlangen.
    f"{sizes.MOTION_PREFIX}CURVE": sizes.motion_curve_css(),
    f"{sizes.MOTION_PREFIX}CURVE_HYPR": sizes.motion_curve_hyprland(),
    f"{sizes.MOTION_PREFIX}CURVE_NAME": sizes.MOTION_CURVE_NAME,
    
    # ============================================================================
    # TOOLTIP (fixed - NOT scaled)
    # ============================================================================
    "STYLE_TOOLTIP_BG": THEME.INK,
    "STYLE_TOOLTIP_BORDER_WIDTH": "2px",
    "STYLE_TOOLTIP_BORDER_STYLE": "solid",
    "STYLE_TOOLTIP_BORDER_COLOR": THEME.SHADE_1,
    
    # Hover Effects
    "STYLE_HOVER_BG": THEME.SHADE_1,
    "STYLE_HOVER_COLOR": THEME.TEXT,
    
    # ============================================================================
    # DIE FREMDEN GTK4-FENSTER
    # ============================================================================
    # Die Namen unten sind nicht unsere: es sind die benannten Farben von
    # libadwaita, und gtk4-colors-config.template schreibt sie als
    # @define-color nach ~/.config/gtk-4.0/gtk.css. Jede Anwendung aus
    # packaging/zepos-apps liest diese Datei beim Start und traegt danach
    # die Marke - das ist der ganze Mechanismus, mit dem ein
    # Dateimanager, den wir nicht geschrieben haben, aussieht wie ZepOS.
    #
    # WARUM DAS UEBERHAUPT GEHT, UND WARUM NUR HIER
    #     Weil alle neun Anwendungen GTK4 tragen. Eine GTK3-Anwendung
    #     liest diese Datei nicht; sie liest ~/.config/gtk-3.0/gtk.css mit
    #     anderen Farbnamen. Genau das ist der Grund, aus dem die Auswahl
    #     in packaging/zepos-apps so ausgefallen ist, wie sie ausgefallen
    #     ist - die Regel "global GTK4" und die Forderung "wie Apple OS"
    #     sind an dieser Stelle dieselbe Forderung.
    #
    # ES STEHT KEIN NEUER FARBSCHLUESSEL DAHINTER
    #     Jeder Wert unten kommt aus einem Schluessel, den THEME.COLORS
    #     schon hat. Ein eigener Satz Farben fuer fremde Fenster waere
    #     eine zweite Marke: wer `zepos-settings set colors.overlay_accent`
    #     aufruft, erwartet, dass sich das Cyan UEBERALL bewegt, und nicht
    #     nur in unseren eigenen Ueberlagerungen.
    #
    # DIE TRENNUNG ZWISCHEN accent UND accent_bg IST DIESELBE WIE OBEN
    #     overlay_accent ist CYAN_TEXT, weil libadwaita `accent_color` als
    #     TEXTFARBE benutzt (Verweise, aktive Reiter, markierte Eintraege)
    #     - und die Marken-Cyan #0096C0 misst 3,45:1 auf dem Petrol und
    #     darf nicht gelesen werden. `accent_bg_color` ist dagegen eine
    #     Flaeche, auf der Text liegt, also die unveraenderte Marke, mit
    #     dem Ink darauf. Dieselbe Unterscheidung, die src/brand.py im
    #     Kopf begruendet, nur in libadwaitas Namen.
    "STYLE_GTK4_WINDOW_BG": get_user_color("overlay_surface"),
    "STYLE_GTK4_WINDOW_FG": get_user_color("overlay_text"),
    # Der Inhalt liegt TIEFER als der Rahmen: Listen, Textflaechen und
    # Bildbetrachter bekommen das Ink, die Leisten darum das Petrol. Ohne
    # diesen Unterschied ist ein Fenster eine einzige Flaeche, auf der
    # sich nicht ablesen laesst, was Bedienung ist und was Inhalt.
    "STYLE_GTK4_VIEW_BG": get_user_color("overlay_bg"),
    "STYLE_GTK4_VIEW_FG": get_user_color("overlay_text"),
    "STYLE_GTK4_HEADERBAR_BG": get_user_color("overlay_surface"),
    "STYLE_GTK4_HEADERBAR_FG": get_user_color("overlay_text"),
    "STYLE_GTK4_SIDEBAR_BG": get_user_color("overlay_surface"),
    "STYLE_GTK4_SIDEBAR_FG": get_user_color("overlay_text"),
    "STYLE_GTK4_CARD_BG": get_user_color("overlay_item_hover"),
    "STYLE_GTK4_DIALOG_BG": get_user_color("overlay_surface"),
    "STYLE_GTK4_POPOVER_BG": get_user_color("overlay_surface"),
    "STYLE_GTK4_BORDER": get_user_color("overlay_border"),
    "STYLE_GTK4_SUBTEXT": get_user_color("overlay_subtext"),
    "STYLE_GTK4_ACCENT": get_user_color("overlay_accent"),
    "STYLE_GTK4_ACCENT_BG": THEME.CYAN,
    # Auf der Cyan-Flaeche steht das Ink und nicht das Text-Weiss.
    #
    # NACHGERECHNET am 19.08.2026, WCAG 2.1, dieselbe Formel wie
    # tests/src/test_brand.py:
    #
    #     #08262C auf #0096C0    4,63:1   besteht
    #     #DCEEF4 auf #0096C0    2,87:1   besteht NICHT
    #
    # Hier standen 6,79:1 und 1,87:1. Beide Zahlen waren falsch, und die
    # erste in die gefaehrliche Richtung: sie liess eine KNAPPE Wahl
    # bequem aussehen. Der Abstand zur Schwelle betraegt 0,13 und nicht
    # 2,29. Die Entscheidung bleibt richtig - eine Schaltflaeche, deren
    # Beschriftung man nicht liest, ist keine -, aber wer die Cyan-
    # Flaeche kuenftig auch nur eine Spur heller macht, faellt darunter.
    # Gefunden beim Umstellen der Einstellungen auf die Knopf-Rollen.
    "STYLE_GTK4_ACCENT_FG": THEME.INK,
    "STYLE_GTK4_SUCCESS": get_user_color("success"),
    "STYLE_GTK4_SUCCESS_BG": THEME.GREEN_DIM,
    "STYLE_GTK4_WARNING": get_user_color("warning"),
    "STYLE_GTK4_WARNING_BG": THEME.YELLOW_DIM,
    # critical und nicht error: dies ist die Farbe, die libadwaita als
    # Text setzt, und RED ist die des Paares, die gelesen werden darf
    # (5,21:1 auf Petrol). RED_DEEP steht darunter als Flaeche.
    "STYLE_GTK4_ERROR": get_user_color("critical"),
    "STYLE_GTK4_ERROR_BG": THEME.RED_DEEP,
    "STYLE_GTK4_ON_STATE_FG": THEME.INK,

    # ============================================================================
    # SPECIAL VALUES (fixed - NOT scaled)
    # ============================================================================
    "STYLE_TRAY_SPACING": "10px",
    # Die Kantenlaenge der Symbole in der Statusablage. Ein Bild aus
    # einem fremden Prozess, also FIXED - siehe src/sizes.py.
    "STYLE_TRAY_ICON_SIZE": size_value("STYLE_TRAY_ICON_SIZE"),
    "STYLE_SCROLL_STEP": "5",  # Keep as-is (step count, not pixels)
    
    # SIEBEN HARDWARE-PLATZHALTER STANDEN HIER und sind ersatzlos weg.
    # STYLE_HARDWARE_WARNING_BG, _WARNING_COLOR, _CRITICAL_BG,
    # _CRITICAL_COLOR, _OFFLINE_BG, _OFFLINE_COLOR und
    # _OFFLINE_OPACITY, alle sieben mit genau einem Leser
    # (bar-style.template).
    #
    # GEMESSEN am 13.08.2026: die drei Farben waren Byte fuer Byte die
    # drei allgemeinen Zustandsfarben - #FFCB00 ist STYLE_COLOR_WARNING,
    # #FF8A8A ist STYLE_COLOR_CRITICAL, #8FB0BA ist
    # STYLE_COLOR_INACTIVE. Drei Namen fuer Farben, die es schon gab.
    #
    # Die drei Hintergruende sind mit ihrer REGEL gegangen und nicht nur
    # mit ihrem Namen: sie malten einen deckenden Kasten auf die eine
    # Glasplatte der Leiste, und der Nutzer hat Kaesten auf dieser
    # Flaeche am 12.08.2026 abgelehnt. Die Begruendung steht bei
    # #custom-hardware in bar-style.template.

    # SECHS ANIMATIONS-PLATZHALTER STANDEN HIER und sind ersatzlos weg.
    # STYLE_ANIMATION_PULSE_SYNC, _CHECK, _ERROR, _DELETE,
    # STYLE_ANIMATION_BLINK und _SUCCESS_FLASH - GEMESSEN am 12.08.2026:
    # zusammen NULL Leser, und dazu vier Dauern (1s, 1.5s, 2s) und zwei
    # Kurven (linear, ease-out), die neben der Bewegungsleiter stehen.
    #
    # Ersatzlos, aus demselben Grund wie bei den 29 Farben: sie haben nie
    # gewirkt, also gibt es nichts zu retten. Wer eine pulsierende
    # Anzeige braucht, schreibt ihre @keyframes ins Stylesheet und nimmt
    # die Dauer von der Leiter.
    
    # VPN Configuration (user-configurable via user-settings.json -> vpn section)
    #
    # Every default here is empty on purpose. The origin shipped its
    # employer's gateway address, its own account name and its domain, so
    # a stranger's installation came pre-aimed at a company they had
    # never heard of. An empty value reaches the generated connect
    # script, which refuses to dial and says which setting is missing.
    "STYLE_VPN_SERVER": get_user_vpn_setting("server", ""),
    "STYLE_VPN_USERNAME": get_user_vpn_setting("username", ""),
    "STYLE_VPN_CONNECTION_NAME": get_user_vpn_setting("connection_name", "work"),
    "STYLE_COLOR_VPN_CONNECTING": get_user_color("vpn_connecting"),
    "STYLE_OVERLAY_BORDER_COLOR": get_user_color("overlay_border"),

    # ============================================================================
    # AGS OVERLAY BASE COLORS (user-configurable via user-settings.json)
    # ============================================================================
    "STYLE_COLOR_OVERLAY_BG": get_user_color("overlay_bg"),
    "STYLE_COLOR_OVERLAY_SURFACE": get_user_color("overlay_surface"),
    "STYLE_COLOR_OVERLAY_TEXT": get_user_color("overlay_text"),
    "STYLE_COLOR_OVERLAY_SUBTEXT": get_user_color("overlay_subtext"),
    "STYLE_COLOR_OVERLAY_ACCENT": get_user_color("overlay_accent"),
    "STYLE_COLOR_OVERLAY_ACCENT_HOVER": get_user_color("overlay_accent_hover"),
    "STYLE_COLOR_OVERLAY_ACCENT_DIM": get_user_color("overlay_accent_dim"),
    "STYLE_COLOR_OVERLAY_ITEM_HOVER": get_user_color("overlay_item_hover"),
    "STYLE_COLOR_OVERLAY_GREEN": get_user_color("overlay_green"),

    # Per-Widget Overlay Accents (default = overlay_accent)
    "STYLE_COLOR_LAUNCHER_ACCENT": get_user_color("launcher_accent", get_user_color("overlay_accent")),
    # The same accent as three decimal channels, for the glow behind the
    # selected row of zepos-menu, which needs an alpha a hex cannot
    # carry. The template writes the rgba() around it - see _channels()
    # above.
    "STYLE_COLOR_LAUNCHER_ACCENT_RGB": _channels(
        get_user_color("launcher_accent", get_user_color("overlay_accent"))),
    "STYLE_COLOR_CALENDAR_ACCENT": get_user_color("calendar_accent", get_user_color("overlay_accent")),
    "STYLE_COLOR_SHORTCUTS_ACCENT": get_user_color("shortcuts_accent", get_user_color("overlay_accent")),
    "STYLE_COLOR_BATTERY_ACCENT": get_user_color("battery_accent", get_user_color("overlay_accent")),
    "STYLE_COLOR_DISK_ACCENT": get_user_color("disk_accent", get_user_color("overlay_accent")),
    "STYLE_COLOR_CONTROL_ACCENT": get_user_color("control_accent", get_user_color("overlay_accent")),
    "STYLE_COLOR_NETWORK_ACCENT": get_user_color("network_accent", get_user_color("overlay_accent")),
    "STYLE_COLOR_WALLPAPER_ACCENT": get_user_color("wallpaper_accent", get_user_color("overlay_accent")),
    "STYLE_COLOR_STYLE_ACCENT": get_user_color("style_accent", get_user_color("overlay_accent")),
    "STYLE_COLOR_VPN_ACCENT": get_user_color("vpn_accent", get_user_color("overlay_accent")),

    # VPN Phase 1 (IKE) Settings
    #
    # These match user_settings.py's DEFAULT_SETTINGS exactly, because
    # that is the set that actually reaches disk: load_settings() merges
    # it under whatever the file holds, and any CLI command that saves
    # writes the result back. The two used to disagree about the IKE
    # version and the key lifetime, so whether a tunnel came up as IKEv2
    # main mode or IKEv1 aggressive mode depended on which of the two had
    # last written the settings file.
    "STYLE_VPN_VERSION": str(get_user_vpn_setting("phase1.version", 2)),
    "STYLE_VPN_AGGRESSIVE": "yes" if get_user_vpn_setting("phase1.aggressive", False) else "no",
    "STYLE_VPN_IKE_PROPOSALS": get_user_vpn_setting("phase1.proposals", "aes256-sha256-ecp521"),
    "STYLE_VPN_DPD_DELAY": str(get_user_vpn_setting("phase1.dpd_delay", 30)),
    "STYLE_VPN_DPD_TIMEOUT": str(get_user_vpn_setting("phase1.dpd_timeout", 120)),
    "STYLE_VPN_KEYLIFE": str(get_user_vpn_setting("phase1.keylife", 86400)),
    "STYLE_VPN_ENCAP": "yes" if get_user_vpn_setting("phase1.encap", True) else "no",
    "STYLE_VPN_MOBIKE": "yes" if get_user_vpn_setting("phase1.mobike", False) else "no",

    # VPN Phase 2 (ESP) Settings
    "STYLE_VPN_REKEY_TIME": str(get_user_vpn_setting("phase2.rekey_time", 43200)),
    "STYLE_VPN_LIFE_TIME": str(get_user_vpn_setting("phase2.life_time", 43200)),
    "STYLE_VPN_ESP_PROPOSALS": get_user_vpn_setting("phase2.esp_proposals", "aes256-sha256-ecp521"),
    "STYLE_VPN_MODE": get_user_vpn_setting("phase2.mode", "tunnel"),
    "STYLE_VPN_REPLAY_WINDOW": str(get_user_vpn_setting("phase2.replay_window", 32)),

    # VPN DNS Settings
    #
    # A whitespace-separated list rather than two numbered slots. The
    # origin had exactly two internal resolvers and wrote one placeholder
    # per resolver, so a third could not be expressed and a single one
    # left an empty second slot behind.
    "STYLE_VPN_DNS_SERVERS": " ".join(vpn_list_setting("dns.servers")),
    "STYLE_VPN_SEARCH_DOMAIN": get_user_vpn_setting("dns.search_domain", ""),

    # VPN Routed Networks
    #
    # One list, seven consumers: the child security associations, the
    # routes added to the main table, the routes in table 220, the routes
    # removed again on disconnect, the route summary in the bar, the
    # children the connect script initiates, and the ones the watcher
    # re-initiates after a dead tunnel. The origin spelled the same three
    # networks out separately in each of them.
    "STYLE_VPN_ROUTED_NETWORKS": routed_networks_line(vpn_routed_networks()),
    "STYLE_VPN_CHILDREN": vpn_children_block(),
    "STYLE_VPN_CHILD_NAMES": " ".join(
        child_names(vpn_connection_name(), vpn_routed_networks())
    ),

    # Networks kept OUTSIDE the tunnel even though a routed network
    # covers them - a parallel WireGuard link into a home LAN that sits
    # inside 192.168.0.0/16, for instance. The origin had exactly one,
    # its own, alongside the German interface name of its own router.
    "STYLE_VPN_BYPASS_NETWORKS": " ".join(
        vpn_list_setting("bypass_networks")
    ),

    # A host that only answers through the tunnel. Reaching the internet
    # proves the internet works, not that the VPN does.
    "STYLE_VPN_TEST_HOST": get_user_vpn_setting("test_host", ""),

    # ============================================================================
    # NETWORK WATCHDOG
    # ============================================================================
    #
    # A public resolver, unlike the VPN defaults above: this only probes
    # whether the machine has any connectivity at all, so a working
    # default harms nobody and an unset one would disable the watchdog.
    "STYLE_WATCHDOG_TEST_HOST": get_user_watchdog_setting("test_host", "1.1.1.1"),

    # Empty on purpose, and read as "work it out from the default route".
    # The origin wrote its own virtual machine's gateway and interface in,
    # so on every other machine the watchdog reported an unreachable
    # gateway forever and never acted - and the bar showed "N/A" for the
    # address. A default here could not be right for anyone; detection is.
    "STYLE_WATCHDOG_GATEWAY": get_user_watchdog_setting("gateway", ""),
    "STYLE_WATCHDOG_INTERFACE": get_user_watchdog_setting("interface", ""),

    # ============================================================================
    # WEATHER
    # ============================================================================
    #
    # Empty by default, and that is the whole point: the origin had two
    # scripts with one city each written into the URL, so a stranger's
    # bar showed the weather of a town they had never been to - and, on
    # every refresh, told a third party where that bar was standing. The
    # location is now the user's to set, and until they do, nothing is
    # requested and nothing is sent.
    "STYLE_WEATHER_LOCATION": get_user_weather_setting("location", ""),

    # ============================================================================
    # EXTRA CLOCKS
    # ============================================================================
    #
    # The same shape as the weather location, and the same story: the
    # origin had two one-line templates, each with a timezone, a flag
    # emoji and a locale of one country written into it, both placed on
    # every bar unconditionally. One person's two homes, on everybody's
    # screen - and unextendable, because a third clock meant a third
    # template, a third generator route, a third bar module and a third
    # stylesheet rule.
    #
    # BUILT rather than filled in, like the two audio blocks: "no zone
    # configured" has to come out as a sentence naming the setting, not
    # as an empty array that reads like a fault. Any number of zones goes
    # into ONE module - the bar's module names are static in its source,
    # so a variable number of MODULES could only be had as a fixed number
    # of slots, most of them permanently empty and all of them a ceiling
    # nobody is told about. See src/clocks.py.
    "STYLE_CLOCK_ZONES": clock_zones_block(),
    "STYLE_CLOCK_FORMAT": clock_format_literal(),

    # ============================================================================
    # AUDIO
    # ============================================================================
    #
    # The same shape as the weather location and for a stronger reason.
    # The origin named four of its own devices in the two audio
    # templates - a headset and a webcam by the ALSA node names their USB
    # product strings produce, a microphone by its product name, a pair
    # of headphones by their Bluetooth address - and a node name belongs
    # to one machine. Elsewhere the rules matched nothing, and a
    # WirePlumber rule that never fires is indistinguishable from one
    # that does: the file parses, the daemon starts, nothing is said.
    #
    # Both blocks are BUILT from the settings rather than filled in, so
    # that "nothing configured" comes out as a sentence saying so instead
    # of as an empty rule list that reads like a rule.
    "STYLE_AUDIO_DEFAULTS": audio_defaults_block(),
    "STYLE_AUDIO_NODE_RULES": audio_node_rules_block(),

    # The hardware microphone EasyEffects processes. Blank leaves
    # EasyEffects on whatever PipeWire hands it, which is a working
    # effects chain rather than a broken one.
    "STYLE_AUDIO_EFFECTS_INPUT": audio_setting("effects_input"),

    # ============================================================================
    # Das Dock (fixed - NOT scaled)
    # ============================================================================
    # WARUM HIER KEINE EIGENE PLATTENFARBE MEHR STEHT (12.08.2026)
    #     Hier stand `THEME.rgba(get_user_color("background"),
    #     THEME.GLASS_SOLO_ALPHA)`. Beide Haelften waren falsch, und die
    #     FARBE schwerer als die Deckkraft.
    #
    # DIE MESSUNG, DIE ES ZEIGT
    #     Die ausgelieferte Tapete src/branding/zepos-wallpaper.png,
    #     jeder zweite Bildpunkt gezaehlt (518400 Proben, 12.08.2026):
    #
    #         (13, 61, 71)     95.42 %   <- der flache Grund
    #         ( 0,150,192)      0.82 %
    #         (255,255,255)     0.53 %
    #         (255,203,  0)     0.26 %
    #
    #     (13, 61, 71) IST get_user_color("background"), Byte fuer Byte.
    #     Die Platte des Docks malte also die Farbe, auf der sie liegt,
    #     und aus derselben Farbe kommt bei JEDER Deckkraft dieselbe
    #     Farbe heraus:
    #
    #         Platte                            ueber (13,61,71)
    #         background @ 0.86  (bisher)       (13, 61, 71)   unsichtbar
    #         SHADE_1    @ 0.55  (die Leiste)   (24, 71, 81)   sichtbar
    #
    #     Auf out/render/dock-1366.png ist das zu sehen: draussen das
    #     Liniennetz der Tapete, drinnen eine flache Flaeche mit einer
    #     Haarlinie darum. Kein Glas, sondern ein Loch. Der Kommentar,
    #     der hier stand, nannte das "dieselbe Farbe wie die Kacheln der
    #     Leiste" - richtig, und genau das war der Fehler: die Kacheln
    #     der Leiste liegen auf einer PLATTE aus SHADE_1 und nicht auf
    #     der Tapete.
    #
    # UND DIE DECKKRAFT KOSTET NICHTS, WEIL DAS DOCK JETZT ZWEI SCHICHTEN
    # HAT
    #     GLASS_SOLO_ALPHA ist fuer eine Flaeche, die ihre Schrift DIREKT
    #     traegt. Das Dock traegt seine Symbole seit heute auf Kacheln
    #     (`#dock button.dock-button` in bar-style.template), ist also
    #     zweischichtig wie die Leiste - und zwei Schichten stapeln sich
    #     auf 0.70 + 0.30*0.55 = 0.865, also auf genau das Material, das
    #     die einschichtige Platte hatte. UNTER dem Symbol aendert sich
    #     damit nichts; NEBEN dem Symbol wird aus dem Loch Glas.
    #
    #     Deshalb steht hier gar keine Farbe mehr: #dock liest
    #     STYLE_GLASS_PANEL und seine Knoepfe STYLE_GLASS_CHIP, dieselben
    #     zwei Platzhalter wie #bar und .bar-module. Zwei Streifen, die
    #     gleich aussehen sollen, lesen dieselben zwei Werte.
    #
    # WAS AUSSERDEM GEGANGEN IST
    #     STYLE_DOCK_SPACING ("4") hatte am 12.08.2026 keinen einzigen
    #     Leser - `grep -rn` ueber src/, tests/ und settings/ fand nur
    #     diese Zeile.
    #     STYLE_DOCK_HOVER_BG stand als `rgba(33, 79, 89, 0.9)` da, also
    #     als ausgeschriebene Kanaele von SHADE_1 mit einer erfundenen
    #     Deckkraft - genau das, was test_no_stylesheet_writes_its_own_
    #     transparency in den Stilvorlagen verbietet. Der Waechter sah es
    #     nicht, weil das Literal HIER stand und nicht dort. Das Dock
    #     nimmt jetzt STYLE_HOVER_BG, also denselben Hervorhebungsgrund
    #     wie jedes Modul der Leiste.
    "STYLE_DOCK_ICON_SIZE": size_value("STYLE_DOCK_ICON_SIZE"),
    "STYLE_DOCK_PADDING": size_value("STYLE_DOCK_PADDING"),
    "STYLE_DOCK_BORDER_COLOR": get_user_color("overlay_border"),
    "STYLE_DOCK_ICON_COLOR": get_user_color("dock_icon"),
    "STYLE_DOCK_ICON_ACTIVE_COLOR": get_user_color("dock_indicator"),

    # ============================================================================
    # ADDITIONAL COLORS (not scaled)
    # ============================================================================
    "STYLE_COLOR_GREEN_DIM": THEME.GREEN_DIM,
    "STYLE_COLOR_YELLOW": THEME.YELLOW,
    "STYLE_COLOR_YELLOW_DARK": THEME.YELLOW_DIM,

    # ============================================================================
    # Hyprbars - Window Titlebars (fixed - NOT scaled, colors user-configurable)
    # ============================================================================
    # DIE TITELLEISTE TRUG BIS ZUM 19.08.2026 CATPPUCCIN, NICHT ZEPOS
    #
    #     GEMELDET: "der header alle seiten ist immernoch in der alten
    #     hintergrund farbe ... ich meine hyprbars bitte stelle diese
    #     farbe auch auf die hintergrund farbe des headers dunkle
    #     petrol".
    #
    #     Er hat recht, und es betraf nicht nur den Grund. ALLE FUENF
    #     Vorgaben hier waren Catppuccin Mocha, aus der Zeit vor der
    #     Marke:
    #
    #         Grund        1e1e2e   Mocha base
    #         Text         cdd6f4   Mocha text
    #         Schliessen   f38ba8   Mocha red
    #         Minimieren   f9e2af   Mocha yellow
    #         Maximieren   a6e3a1   Mocha green
    #
    #     Warum es niemandem auffiel: hyprbars zeichnet auf NORMALEN
    #     Fenstern (Browser, Dateien, Einstellungen, Kitty), und die
    #     AGS-Flaechen sind Layer-Shell - sie bekommen nie eine
    #     hyprbars-Leiste. Die ganze Arbeit an den Fenstern dieses
    #     Projekts konnte an dieser Leiste vorbeigehen.
    #
    #     Der Grund ist jetzt overlay_surface, also GENAU die Farbe, mit
    #     der der Kopf eines AGS-Fensters malt ($surface in
    #     ags-style.template) - darum ging es dem Nutzer. Die uebrigen
    #     vier folgen derselben Zuordnung: Text auf overlay_text,
    #     Schliessen auf critical, Minimieren auf warning, Maximieren
    #     auf success.
    #
    #     KONTRAST NACHGERECHNET (WCAG 2.1, dieselbe Formel wie
    #     tests/src/test_brand.py): #DCEEF4 auf #0D3D47 = 9,90:1.
    #
    #     Die Namen bleiben eigene Regler - wer eine andere Titelleiste
    #     will, stellt sie weiterhin um. Geaendert hat sich nur, worauf
    #     sie zeigen, wenn niemand etwas eingestellt hat.
    "STYLE_HYPRBARS_HEIGHT": size_value("STYLE_HYPRBARS_HEIGHT"),
    # KORREKTUR AM SELBEN TAG: overlay_bg UND NICHT overlay_surface.
    #
    #     Am 19.08.2026 habe ich hier zuerst overlay_surface (#0D3D47,
    #     Petrol) gesetzt, weil der Kopf eines AGS-FENSTERS damit malt.
    #     Der Nutzer hat sofort widersprochen: "die header der fenster
    #     sind nicht im dunklen petrol wie der header oder die dock man
    #     sieht den header dadurch nicht".
    #
    #     Er hat recht, und die Zahlen zeigen warum - der Massstab ist
    #     nicht der Fensterkopf, sondern das, was daneben auf demselben
    #     Schirm liegt:
    #
    #         Leiste (#bar)          rgba(8, 38, 44, 0.86)   Tinte
    #         Dockplatte             dieselbe Tinte
    #         hyprbars, mein Fehler  #0D3D47                 Petrol
    #
    #     Petrol ist die HELLERE der beiden Markenfarben. Eine
    #     Titelleiste darin steht heller da als Leiste und Dock, und
    #     genau das hat er gesehen. overlay_bg ist die Tinte - dieselbe
    #     Farbe, aus der Leiste und Dock ihr Glas mischen.
    #
    #     Deckend und nicht halbdurchsichtig: hyprbars zeichnet auf
    #     einem Fenster, nicht auf der Tapete, und Hyprlands
    #     Unschaerfe-Regeln gelten fuer Layer-Shell-Flaechen, nicht fuer
    #     Titelleisten. Ein rgba hier waere eine Durchsichtigkeit ohne
    #     das Glas dahinter.
    "STYLE_HYPRBARS_BG_COLOR": f"rgb({get_user_color('hyprbar_bg', get_user_color('overlay_bg'))[1:]})",
    "STYLE_HYPRBARS_TEXT_COLOR": f"rgb({get_user_color('hyprbar_text', get_user_color('overlay_text'))[1:]})",
    "STYLE_HYPRBARS_TEXT_SIZE": size_value("STYLE_HYPRBARS_TEXT_SIZE"),
    "STYLE_HYPRBARS_BUTTON_SIZE": size_value("STYLE_HYPRBARS_BUTTON_SIZE"),
    "STYLE_HYPRBARS_BUTTON_CLOSE_COLOR": f"rgb({get_user_color('hyprbar_close', get_user_color('critical'))[1:]})",
    "STYLE_HYPRBARS_BUTTON_MINIMIZE_COLOR": f"rgb({get_user_color('hyprbar_minimize', get_user_color('warning'))[1:]})",
    "STYLE_HYPRBARS_BUTTON_MAXIMIZE_COLOR": f"rgb({get_user_color('hyprbar_maximize', get_user_color('success'))[1:]})",

    # ============================================================================
    # Der Starter und der Zwischenablage-Verlauf (plugins/)
    # ============================================================================
    # Sieben Groessen, die bis zum 11.08.2026 als `static constexpr` im
    # uebersetzten Objekt der beiden Programme standen und deshalb von
    # keinem Regler erreichbar waren. src/sizes.py haelt die Tabelle und
    # die Begruendung, welche davon der Schrift folgen und welche nicht.
    "STYLE_LAUNCHER_WIDTH": size_value("STYLE_LAUNCHER_WIDTH"),
    "STYLE_LAUNCHER_SEARCH_HEIGHT": size_value("STYLE_LAUNCHER_SEARCH_HEIGHT"),
    "STYLE_LAUNCHER_ROW_HEIGHT": size_value("STYLE_LAUNCHER_ROW_HEIGHT"),
    "STYLE_LAUNCHER_ROW_MIN_HEIGHT": size_value("STYLE_LAUNCHER_ROW_MIN_HEIGHT"),
    "STYLE_LAUNCHER_ICON_SIZE": size_value("STYLE_LAUNCHER_ICON_SIZE"),
    "STYLE_CLIPBOARD_WIDTH": size_value("STYLE_CLIPBOARD_WIDTH"),
    "STYLE_CLIPBOARD_HEIGHT": size_value("STYLE_CLIPBOARD_HEIGHT"),

    # ============================================================================
    # Wallpaper Selector - FIXED (Full HD base, no scaling)
    # ============================================================================
    "STYLE_WALLPAPER_SELECTOR_WIDTH": "450px",
    "STYLE_WALLPAPER_THUMBNAIL_SIZE": "120px",
    "STYLE_WALLPAPER_THUMBNAIL_BORDER": f'2px solid {get_user_color("overlay_border")}',
    "STYLE_WALLPAPER_THUMBNAIL_BORDER_ACTIVE": f'2px solid {get_user_color("wallpaper_accent", get_user_color("overlay_accent"))}',
    "STYLE_WALLPAPER_GRID_GAP": "10px",
    "STYLE_WALLPAPER_SECTION_SPACING": "15px",
    "STYLE_WALLPAPER_COLOR_LANDSCAPE": get_user_color("wallpaper_landscape"),
    "STYLE_WALLPAPER_CURRENT_HEIGHT": "150px",

    # ============================================================================
    # zepos-logout ist GEFALLEN (Aufgabe 26, 19.08.2026)
    # ============================================================================
    #
    # Die einunddreissig STYLE_LOGOUT_*-Schluessel, die hier standen
    # (Kostenleiter sicher/Neustart/Ausschalten, Maske, Knopf, Masse),
    # gehoerten dem eigenstaendigen C-Programm logout/zepos-logout.c -
    # geloescht mit ihm, nach Regel 14 (loeschen statt als veraltet
    # markieren). Sein Nachfolger, src/templates/ags-logout.template,
    # liest KEINEN dieser Schluessel: er benutzt zepButton() und dessen
    # vier Rollen (.zep-btn-voll/-umrandet/-still/-kritisch,
    # ags-style.template), dieselben, die jedes andere AGS-Fenster
    # benutzt - keine eigene Farbrechnung mehr fuer sechs Knoepfe.
    #
    # WAS AUS DER KOSTENLEITER GEWORDEN IST
    #     Die Handlungskosten-Idee selbst lebt weiter, nur groeber
    #     gerastert: statt drei durchgehenden Farbstufen (sicher/
    #     Neustart/Ausschalten) hat zepButton nur zwei Rollen fuer diese
    #     sechs Knoepfe - "kritisch" (Abmelden, Neustart, Herunterfahren
    #     beenden die Sitzung) und "umrandet" (Sperren, Bereitschaft,
    #     Ruhezustand sind vollstaendig umkehrbar). src/greeter.py
    #     behaelt seine EIGENE dreistufige Leiter (_cost_ladder) - sie
    #     ist die Anmeldemaske, kein AGS-Fenster, und kann zepButton
    #     nicht importieren.

    # ============================================================================
    # zepos-lock - der Sperrbildschirm
    # ============================================================================
    #
    # WAS HIER VORHER STAND
    #     Nichts. hyprlock war kein GTK-Programm und nahm kein
    #     Stylesheet entgegen; src/templates/hyprlock-config.template
    #     trug seine eigenen zwoelf rgb()- und rgba()-Literale in
    #     Terminalgruen auf #0c0c0c - eine Farbwelt, die seit dem Umzug
    #     von kittys Chrom auf die Marke nirgends sonst mehr vorkam. Das
    #     Erste, was ein Nutzer nach jeder Pause sah, war das Einzige,
    #     was nicht nach ZepOS aussah.
    #
    # WARUM DIESELBE STAFFELUNG WIE DIE ANMELDEMASKE UND KEINE EIGENE
    #     Weil es derselbe Moment ist. src/greeter.py setzt die
    #     Anmeldekachel als THEME.INK mit einem Rand aus THEME.SHADE_1
    #     auf den Hintergrund und die Eingabefelder DARAUF in
    #     THEME.PETROL. Wer sich anmeldet und wer sich zurueckmeldet,
    #     sieht damit dieselbe Kachel; ein zweiter Satz Farben fuer
    #     dieselbe Handlung waere zwei Produkte.
    #
    # WARUM KEIN GLAS, OBWOHL DIE LEISTE SEIT DEM 11.08.2026 WELCHES HAT
    #     Zweimal nicht. Vom Zweck her laesst Glas sehen, was dahinter
    #     ist, und dahinter ist der Schreibtisch, den dieser Bildschirm
    #     zu VERBERGEN hat - Hyprland hat fuer das Gegenteil sogar einen
    #     eigenen Schalter, misc:session_lock_xray, und der bleibt aus.
    #
    #     Technisch koennte es ohnehin nicht greifen: GLASS_LAYERS unten
    #     spricht Flaechen ueber ihren Layer-Shell-Namensraum an, und
    #     eine ext_session_lock_surface_v1 hat keinen - sie steht in
    #     `hyprctl layers` nicht. Gemessen am 12.08.2026 im
    #     verschachtelten Hyprland: null Treffer auf "zepos-lock",
    #     waehrend ein unabhaengiger zweiter Sperr-Client gleichzeitig
    #     abgewiesen wurde. Deshalb sind die Flaechen hier deckend.
    "STYLE_LOCK_BACKDROP": THEME.INK,
    "STYLE_LOCK_BACKDROP_IMAGE": THEME.BACKDROP_FILE,
    # Der Schleier ueber dem Bild. Warum es ihn gibt und warum genau so
    # duenn, steht bei THEME.LOCK_SCRIM_ALPHA - kurz: ohne ihn liegt die
    # Ablehnungsmeldung auf der hellsten Stelle des Bildes bei 4.28:1
    # und damit unter der Linie.
    "STYLE_LOCK_SCRIM": THEME.rgba(THEME.INK, THEME.LOCK_SCRIM_ALPHA),
    # Das Benutzerbild: der erste Buchstabe des Namens in einem Kreis.
    # Die Groesse ist fest und nicht auf der Schriftleiter - es ist eine
    # FLAECHE und keine Schrift, und ein Kreis, der mit dem Faktor
    # waechst, schiebt das Feld darunter vom Schirm.
    "STYLE_LOCK_AVATAR_BG": THEME.SHADE_1,
    "STYLE_LOCK_AVATAR_FG": THEME.TEXT,
    "STYLE_LOCK_AVATAR_SIZE": "96px",
    # Pillenform. Groesser als die halbe Feldhoehe; GTK klemmt den Radius
    # auf die Haelfte der kuerzeren Seite, also ist jede genuegend grosse
    # Zahl genau eine Pille - und zwar bei JEDEM Skalierungsfaktor, was
    # eine ausgerechnete Haelfte nicht waere.
    "STYLE_LOCK_CLOCK_COLOR": THEME.TEXT,
    "STYLE_LOCK_DATE_COLOR": THEME.TEXT_DIM,
    "STYLE_LOCK_USER_COLOR": THEME.CYAN_TEXT,
    "STYLE_LOCK_FIELD_BG": THEME.PETROL,
    "STYLE_LOCK_FIELD_TEXT": THEME.TEXT,
    "STYLE_LOCK_FIELD_BORDER": THEME.SHADE_1,
    "STYLE_LOCK_FIELD_BORDER_FOCUS": THEME.CYAN,
    # Waehrend PAM antwortet. Der Rand geht auf die gedaempfte Marke
    # zurueck, damit sichtbar ist, dass gerade nichts angenommen wird -
    # eine Antwort kann Sekunden dauern, weil pam_faildelay sie
    # absichtlich verzoegert.
    "STYLE_LOCK_FIELD_BORDER_BUSY": THEME.CYAN_DIM,
    "STYLE_LOCK_MESSAGE_COLOR": THEME.TEXT_DIM,
    # Die Ablehnung. THEME.RED ist der Rot-Ton, der GELESEN werden darf
    # (5.21:1 auf Petrol, 6.98:1 auf der Tinte dieser Kachel);
    # THEME.RED_DEEP daneben ist der fuer Raender und Flaechen.
    "STYLE_LOCK_FAILURE_COLOR": THEME.RED,
    "STYLE_LOCK_FAILURE_BORDER": THEME.RED_DEEP,
    # Die Feststelltaste, der haeufigste Grund fuer ein richtiges
    # Passwort, das abgelehnt wird. Auf der Warnsprosse und nicht auf
    # der Fehlersprosse: es ist noch nichts schiefgegangen.
    "STYLE_LOCK_CAPSLOCK_COLOR": THEME.YELLOW,

    # ============================================================================
    # Die Passphrasen-Abfrage (fest - NICHT skaliert)
    # ============================================================================
    #
    # pinentry-bemenu, gesetzt von src/system/gpg-agent-config.template.
    # Warum ausgerechnet das und nicht eine GTK4-Variante, steht dort mit
    # den Messungen; die kurze Fassung ist, dass es keine GTK4-Variante
    # gibt - pinentrys Ursprung nennt GTK4 im ganzen Baum nicht, und
    # gcr-4 bringt entgegen der Erwartung keinen Prompter mit.
    #
    # EINE ZEICHENKETTE STATT ACHT SCHLUESSEL, UND WARUM DAS HIER RICHTIG IST
    #     bemenu nimmt seine Farben ueber Kommandozeilenflaggen entgegen,
    #     und gpg-agent.conf laesst hinter pinentry-program keine
    #     Argumente zu - sie muessen also durch BEMENU_OPTS, das eine
    #     einzige Umgebungsvariable ist. Acht Schluessel, die die Vorlage
    #     doch wieder zu einer Zeile zusammensetzt, waeren acht Stellen
    #     zum Nachschlagen fuer eine Zeile zum Lesen. Zusammengesetzt
    #     wird sie hier, aus brand-Namen: kein Hex steht in der Zeichen-
    #     kette, jedes kommt aus der Mitte.
    #
    #     tb/tf  Titel: der Text, den gpg-agent schickt ("Passphrase
    #            eingeben"), auf dem Grund der Warnung.
    #     nb/nf  der ruhende Zustand, auf der Tinte.
    #     fb/ff  das Eingabefeld.
    #     hb/hf  die Hervorhebung.
    #     -p     das Zeichen vor der Eingabe; -x zeigt Punkte statt der
    #            Passphrase, und das ist die Flagge, ohne die dieses
    #            Fenster die Passphrase auf den Bildschirm schriebe.
    "STYLE_PINENTRY_BEMENU_OPTS": (
        "--fn '" + THEME.FONT_CODE + " 14'"
        " -x"
        " --tb '" + THEME.STATE_WARNING_BG + "' --tf '" + THEME.YELLOW + "'"
        " --nb '" + THEME.INK + "' --nf '" + THEME.TEXT + "'"
        " --fb '" + THEME.INK + "' --ff '" + THEME.TEXT + "'"
        " --hb '" + THEME.PETROL + "' --hf '" + THEME.CYAN_TEXT + "'"
    ),

    # ============================================================================
    # The code palette - "Terminal Green" (fixed - NOT scaled)
    # ============================================================================
    #
    # A syntax theme for an editor, not desktop chrome, and the only
    # place in this project that is deliberately not on the THEME. The
    # whole argument is in brand.py under THE CODE PALETTE; the short
    # version is that a theme called Terminal Green has to be green, and
    # its name is what the editor's own preferences reach it by.
    "STYLE_CODE_BG": THEME.CODE_BG,
    "STYLE_CODE_BG_RAISED": THEME.CODE_BG_RAISED,
    "STYLE_CODE_GREEN": THEME.CODE_GREEN,
    "STYLE_CODE_GREEN_DIM": THEME.CODE_GREEN_DIM,
    "STYLE_CODE_GREEN_BRIGHT": THEME.CODE_GREEN_BRIGHT,
    "STYLE_CODE_TEXT": THEME.CODE_TEXT,
    "STYLE_CODE_COMMENT": THEME.CODE_COMMENT,
    "STYLE_CODE_GUIDE": THEME.CODE_GUIDE,
    "STYLE_CODE_RED": THEME.CODE_RED,
    "STYLE_CODE_YELLOW": THEME.CODE_YELLOW,
    "STYLE_CODE_BLUE": THEME.CODE_BLUE,
    "STYLE_CODE_SELECTION_DIM": THEME.CODE_SELECTION_DIM,
}

# ============================================================================
# WELCHE MODULE RECHTS AUF DER LEISTE STEHEN
# ============================================================================
#
# Diese Liste und die `case`-Zweige in ags-bar.template sind zwei
# Haelften einer Aussage, und die Leiste baut nur, was HIER steht: build()
# wird je Name aus dieser Liste einmal aufgerufen. Ein Zweig, den nichts
# nennt, ist deshalb kein Ersatzteil, sondern toter Code - lautlos, ohne
# eine Zeile im Log.
#
# Vier Module waren genau in diesem Zustand. custom/vpn und
# custom/helpers waren die teuren: vpn-status.py, vpn-control.sh,
# vpn-connect.sh, das Stylesheet, der ganze AGS-VPN-Verwalter und das
# Helfermenue wurden bei jedem Lauf erzeugt und konnten nicht erscheinen.
# `network` und `bluetooth` hatten Stilregeln und sonst nichts. Alle vier
# stehen unten, damit tests/src/test_reference_resolution Definition und
# Platzierung aneinanderhalten kann.
#
# Die beiden, die auf einer frischen Installation nicht eingerichtet
# sind, schweigen statt zu luegen: `bluetooth` gibt bei fehlendem Adapter
# einen leeren Text aus und verschwindet damit. Dieselbe Entscheidung wie
# bei custom/weather, und das Gegenteil davon, den Einstieg in eine
# Funktion zu verstecken, die der Nutzer sonst nicht findet.
#
# HERZ UND SCHILD SIND HIER NICHT MEHR, UND WARUM SIE GANZ WEG SIND
#     GEMELDET am 11.08.2026: "herz und schild in der waybar oben kommen
#     weg". Das Herz war custom/network-watchdog (nf-md-heart_pulse und
#     seine drei Geschwister), das Schild custom/vpn (nf-md-shield_lock
#     und seine zwei). Beide kamen aus der persoenlichen Konfiguration,
#     aus der dieses Projekt hervorgegangen ist: ein Wachhund auf ein
#     bestimmtes Heimnetz und ein Tunnel zu einem bestimmten Arbeitgeber.
#
#     Ausgeblendet statt geloescht waeren sie ein Schalter geblieben,
#     den niemand umlegt, und mit ihm zwei Skriptvorlagen samt ihren
#     Erzeugungsrouten, vier Symbole, sieben Farbschluessel und neun
#     Stilregeln, die bei jedem Lauf erzeugt werden und auf keinem Schirm
#     erscheinen koennen. Genau das war der Zustand des Druckermoduls,
#     bevor es am 11.08.2026 mit derselben Begruendung ging.
#
#     Der Schalter war modules.network_watchdog, sein einziger Leser
#     get_module_visible() und sein einziger Bediener ein Reiter im
#     Stil-Editor mit genau einem Eintrag darin. Alle drei sind mit
#     gegangen.
#
#     Was BLEIBT, weil es einen anderen Leser hat: der Wachhund selbst
#     (die Systemd-Einheit und helpers/network-watchdog.sh, die das
#     Kontrollzentrum startet) und der ganze VPN-Verwalter (ags-vpn,
#     vpn-control.sh, vpn.py). Verschwunden ist nur der Blick darauf von
#     der Leiste aus - im Kontrollzentrum stehen beide Zeilen weiter.
#
# Die umgekehrte Richtung - ein Name hier, den ags-bar.template nicht
# kennt - kostet in der AGS-Fassung nicht mehr die ganze Leiste: build()
# gibt null zurueck und schreibt "Unbekanntes Leistenmodul" auf die
# Konsole. Waybar verweigerte an dieser Stelle den Start der ganzen Bar.
# =============================================================================
# WELCHE FLAECHEN GLASIG SIND
# =============================================================================
#
# Jeder Layer-Shell-Namensraum, den dieses Projekt anmeldet. Hyprland
# spricht seine `layerrule` ueber genau diesen Namen an, und ohne eine
# Regel bekommt eine Flaeche KEINE Unschaerfe - egal wie durchsichtig
# ihr Hintergrund im Stylesheet ist. Ein durchsichtiger Hintergrund ohne
# Unschaerfe ist kein Glas, sondern ein Loch: man sieht die Tapete
# scharf hindurch.
#
# GEMESSEN am 11.08.2026: `grep -rn layerrule src/` fand KEINE EINZIGE
# Zeile, waehrend decoration:blur in hyprland-universal-config.template
# seit jeher auf `enabled = true` steht. Die Unschaerfe war also an - und
# galt fuer FENSTER, weil Layer-Shell-Flaechen sie einzeln angefordert
# bekommen muessen. Die Leiste, das Dock und alle elf Ueberlagerungen
# hatten sie nie.
#
# WARUM EINE LISTE UND NICHT EINE REGEL JE VORLAGE
#     Die Regeln stehen alle in EINER Hyprland-Datei, weil Hyprland sie
#     alle beim Start liest; die Namen entstehen aber in dreizehn
#     AGS-Vorlagen. Eine Liste hier ist die einzige Stelle, an der beide
#     Seiten zusammenkommen - und tests/src/test_glass.py haelt sie
#     gegeneinander: es liest die Namensraeume aus den Vorlagen und
#     faellt um, sobald einer dabei ist, der hier fehlt. Eine neue
#     Oberflaeche ohne Glasregel kostet also die Suite und nicht das
#     Aussehen.
#
# `network` und `notifications` sind KEINE Ueberlagerung im Sinne von
# ags-overlay-utils.template - sie melden ihre Astal.Window selbst an -
# und stehen deshalb ausgeschrieben da statt aus einer Widget-Liste zu
# kommen.
#
# DIE VIER, DIE AM 12.08.2026 DAZUGEKOMMEN SIND
#     Sie fehlten nicht aus einem Grund, sondern durch eine Luecke in
#     der Pruefung: tests/src/test_glass.py las die Namensraeume aus
#     `src/templates/ags-*.template`, und diese vier melden sich
#     woanders an -
#
#         hyprlaunch          plugins/hyprlaunch/src/LauncherRenderer.cpp
#         clipboard-manager   plugins/hyprclipx/src/ClipboardRenderer.cpp
#         zepos-menu          menu/zepos_menu/window.py
#         zepos-logout        logout/zepos-logout.c
#
#     Eine Pruefung, die nur eine Sprache liest, ist fuer die anderen
#     nicht streng, sondern blind, und sie sagt es nicht. Sie liest
#     jetzt alle vier Quellen; GLASS_PLATES unten haelt fest, wo jede
#     Flaeche sich malt, damit auch die zweite Haelfte geprueft werden
#     kann.
#
#     VON DEN VIER IST NUR NOCH ZEPOS-LOGOUT SELBST GEGANGEN (Aufgabe 26,
#     19.08.2026): das C-Programm ist geloescht, sein Namensraum "logout"
#     steht seither weiter unten, als Zeile wie jede andere AGS-
#     Ueberlagerung - ags-logout.template meldet ihn ueber
#     `createOverlayWindow({ name: "logout", ... })`, dieselbe vierte
#     Schreibweise, die tests/src/test_glass.py::_declared_namespaces()
#     schon fuer "control" kennt.
#
#     ACHTUNG BEIM NACHSEHEN: hyprclipx meldet sich NICHT unter seinem
#     Programmnamen an, sondern als "clipboard-manager". Der Name steht
#     in der C++-Zeile und nirgends sonst - geraten haette man ihn
#     falsch, und eine layerrule auf einen Namensraum, den niemand
#     anmeldet, greift lautlos nie.
#
# zepos-lock steht bewusst NICHT hier. Eine ext_session_lock_surface_v1
# hat gar keinen Namensraum, und der Sperrbildschirm soll verbergen und
# nicht durchlassen - die ganze Begruendung steht oben bei
# STYLE_LOCK_BACKDROP, und tests/src/test_gtk4_only.py haelt sie fest.
GLASS_LAYERS = (
    "zepos-bar",
    "zepos-dock",
    # Der Abschaltknopf am Dock - Aufgabe 26, Teil 3, 19.08.2026. Eine
    # eigene Flaeche je Schirm (ags-power-button.template), dieselbe
    # Glasplatte wie #dock, aber unter einer eigenen ID (#power-button,
    # styles/bar-style.template) und einem eigenen Namensraum.
    "zepos-power",
    "notifications",
    # Der Verlauf und "Nicht stoeren", seit dem 12.08.2026. Eine EIGENE
    # Flaeche neben "notifications" und kein Zusatz zu ihr: der
    # Einblendstapel ist eine Layer-Shell-Flaeche an der oberen rechten
    # Ecke, das Zentrum eine am Zeiger, und `match:namespace` sucht
    # verankert - ^(notifications)$ traefe diese hier nicht mit.
    "notification-center",
    # "network" (Aufgabe 8) und "bluetooth" (Aufgabe 7) sind am
    # 18.08.2026 gefallen: weder ags-network.template noch
    # ags-bluetooth.template bauen ein eigenes Astal.Window mehr (kein
    # `namespace:`/`createOverlayWindow({` mehr im eigenen Quelltext,
    # siehe dort) - beide teilen sich seither die Glasplatte des
    # Namensraums "control" (die Schale).
    # tests/src/test_glass.py::_declared_namespaces() faende sonst
    # einen Eintrag ohne meldende Quelle - siehe Bericht zu Aufgabe 7/8.
    "calendar",
    "shortcuts",
    "battery",
    "disk",
    "control",
    "wallpaper",
    "style-editor",
    # "vpn" ist am 18.08.2026 (Aufgabe 9, "VPN wird eine Seite, die drei
    # Fenster fallen") gefallen - dieselbe Begruendung wie bei "network"
    # (Aufgabe 8) und "bluetooth" (Aufgabe 7) oben: ags-vpn.template baut
    # kein eigenes Astal.Window mehr und teilt sich seither die
    # Glasplatte des Namensraums "control". "vpn-settings" bleibt: die
    # VPN-Einstellungen sind ein eigenes Fenster, kein Verbindungsziel.
    "vpn-settings",
    # Die Einstellungen als eigenes AGS-Fenster, seit Aufgabe 32
    # (19.08.2026). Die ZWEITE Schale dieses Baums (createShellWindow(),
    # ags-settings.template) neben dem Kontrollzentrum - eine eigene
    # Flaeche und kein Teil von "control", weil sie ein eigenes Fenster
    # ist: sie geht auf, ohne dass das Kontrollzentrum aufgeht, und sie
    # bleibt offen, waehrend jemand dort etwas anderes tut.
    "settings",
    # Die Sitzungsmaske, seit Aufgabe 26 (19.08.2026) - der Ersatz fuer
    # zepos-logout (siehe die Anmerkung weiter oben) ist ein Fenster wie
    # Kalender, Kuerzel und die uebrigen: `createOverlayWindow({name:
    # "logout", ...})` in ags-logout.template, dieselbe `.overlay-outer`-
    # Platte wie sie alle.
    "logout",
    "hyprlaunch",
    "clipboard-manager",
    "zepos-menu",
)


# =============================================================================
# WO SICH JEDE FLAECHE MALT
# =============================================================================
#
# WAS DIESE TABELLE IST UND WAS SIE AUSDRUECKLICH NICHT IST
#     Sie behauptet KEINE Deckkraft. Sie sagt nur, welcher Wahlausdruck
#     in welcher Stilvorlage die aeusserste Flaeche eines Namensraums
#     malt - einen Zeiger, keinen Wert. Die Deckkraft liest
#     tests/src/test_glass.py an ebenjener Zeile ab, und erst der
#     Vergleich mit GLASS_LAYERS oben ist die Aussage.
#
#     Deshalb ist sie auch keine Doppelung von GLASS_LAYERS: eine Liste
#     gegen eine Liste zu halten pruefte, dass jemand zweimal dasselbe
#     getippt hat. Hier steht eine Liste gegen eine GEMESSENE Datei.
#
# DIE ZWEI FEHLER, DIE ERST DAMIT AUFFALLEN
#     deckend, aber in GLASS_LAYERS   Der Compositor rechnet die
#                                     Unschaerfe und niemand sieht sie.
#                                     Genau der Zustand von zwoelf der
#                                     dreizehn Flaechen am 12.08.2026.
#     durchsichtig, aber nicht drin   Man sieht den Schreibtisch SCHARF
#                                     hindurch. Das ist kein Glas,
#                                     sondern ein Loch - GEMESSEN bis
#                                     zum 19.08.2026 am Zustand von
#                                     zepos-logout, dessen Maske seit
#                                     jeher auf neun Zehnteln stand
#                                     (Aufgabe 26 hat das Programm samt
#                                     seiner Maske entfernt; das Beispiel
#                                     bleibt stehen, weil es zeigt, WAS
#                                     diese Tabelle verhindern soll).
#
# WAS DIE VIER FELDER BEDEUTEN
#     stylesheet  unter src/, weil zwei Ordner Stilvorlagen halten:
#                 styles/ die eigenstaendigen, templates/ die eine
#                 grosse von AGS.
#     selector    die Zeile, an der die aeusserste Flaeche gemalt wird.
#     text        die Farbrollen, die DURCH diese Platte hindurch
#                 gelesen werden - als Rolle aus brand.COLOR_FIELDS und
#                 nicht als Farbe, weil der Nutzer sie verstellen kann.
#                 Genannt wird die DUENNSTE Schrift, die die Platte
#                 traegt: haelt die, halten die kraeftigeren erst recht.
#     covered_by  nur wenn `text` leer ist: der Wahlausdruck, der
#                 zwischen der Schrift und dieser Platte liegt.
#
# WARUM covered_by UND NICHT EINFACH EIN LEERES TUPEL
#     Weil "traegt keine Schrift" sonst die bequemste Antwort waere und
#     jede Kontrastrechnung abschalten koennte. Ein leeres `text`-Tupel
#     muss darum BELEGEN, was stattdessen die Schrift traegt.
#
#     BIS ZUM 19.08.2026 (Aufgabe 26) gab es dafuer zwei Beispiele:
#     zepos-bar (ihre Schrift stand auf .bar-module, einer zweiten
#     Glasschicht darauf) und zepos-logout (ihre Schrift stand auf
#     `button`, und der war deckend - siehe zep_build_grid() im
#     inzwischen geloeschten logout/zepos-logout.c). Beide sind
#     inzwischen fort: zepos-bar traegt seine Schrift seit dem
#     12.08.2026 SELBST (siehe den Eintrag "zepos-bar" unten, `text` ist
#     dort laengst nicht mehr leer), und zepos-logout ist mit seinem
#     ganzen Programm gefallen. KEIN aktueller Eintrag in GLASS_PLATES
#     nutzt `covered_by` mehr - das Feld bleibt trotzdem stehen, mit
#     derselben Begruendung, aus der "logout" in NAMESPACE_ROOTS
#     (tests/src/test_glass.py) trotz leerem Verzeichnis bleibt: ein
#     leerer Fall ist keine Luecke, solange die Pruefung, die ihn
#     braeuchte, noch existiert (test_a_plate_that_carries_no_text_says_
#     what_covers_it) und ein zukuenftiges Fenster ohne eigene Schrift
#     ihn wieder fuellen kann.
#
#     Die Pruefung schlaegt den Wahlausdruck nach und verlangt, dass er
#     wirklich einen Hintergrund malt. Verschwindet er, faellt sie um.
GlassPlate = collections.namedtuple(
    "GlassPlate", "stylesheet selector text covered_by")

_AGS = "templates/ags-style.template"
_BAR = "styles/bar-style.template"

# Die elf AGS-Ueberlagerungen teilen sich EINE Platte: die Fabrik in
# ags-overlay-utils.template haengt `.overlay-outer` in jedes ihrer
# Fenster. Nur der Melder baut seine Karte selbst.
_OVERLAY = GlassPlate(_AGS, ".overlay-outer", ("overlay_subtext",), None)

GLASS_PLATES = {
    # Die Leiste stand hier bis zum 12.08.2026 als `(), ".bar-module"` -
    # eine Platte, deren Schrift auf einer zweiten Glasschicht liegt.
    # Diese Schicht ist fort ("die icon sollen im header nicht nochmal
    # ein element haben"), also traegt die Platte ihre Schrift jetzt
    # selbst und muss die Kontrastrechnung selbst bestehen. Genannt ist
    # bar_text: die Farbe, in der JEDES Modul im Ruhezustand schreibt.
    "zepos-bar": GlassPlate(_BAR, "#bar", ("bar_text",), None),
    "zepos-dock": GlassPlate(_BAR, "#dock", ("dock_icon",), None),
    # Derselbe Farbwert wie #dock (dock_icon) - visuell dieselbe Familie,
    # nur eine eigene ID (siehe den Kommentar bei #power-button in
    # bar-style.template).
    "zepos-power": GlassPlate(_BAR, "#power-button", ("dock_icon",), None),
    "notifications": GlassPlate(_AGS, ".notif-card", ("overlay_subtext",),
                                None),
    # Das Zentrum kommt vollstaendig aus createOverlayWindow() und traegt
    # deshalb dieselbe Platte wie die anderen elf - `.overlay-outer`.
    # Die Karten des Verlaufs liegen DARAUF (`.notif-card`), also ist
    # die aeusserste Flaeche hier dieselbe wie beim Kalender und nicht
    # dieselbe wie beim Einblendstapel, der gar keine Fensterplatte hat.
    "notification-center": _OVERLAY,
    # "network" (Aufgabe 8) und "bluetooth" (Aufgabe 7) sind am
    # 18.08.2026 gefallen - siehe der Kommentar bei GLASS_LAYERS oben.
    # Beide malen sich seither auf der Platte des Namensraums "control".
    "calendar": _OVERLAY,
    "shortcuts": _OVERLAY,
    "battery": _OVERLAY,
    "disk": _OVERLAY,
    "control": _OVERLAY,
    "wallpaper": _OVERLAY,
    "style-editor": _OVERLAY,
    # Die Sitzungsmaske, seit Aufgabe 26 (19.08.2026) - dieselbe Platte
    # wie jedes andere Fenster aus createOverlayWindow(). Ihr Vorgaenger
    # "zepos-logout" trug hier eine eigene Zeile (eigenes Stylesheet,
    # eigener Wahlausdruck "window", leeres `text` mit `covered_by`
    # "button") - siehe die Anmerkung bei "WARUM covered_by" oben.
    "logout": _OVERLAY,
    # "vpn" ist am 18.08.2026 (Aufgabe 9) gefallen - siehe der Kommentar
    # bei GLASS_LAYERS oben. VPN malt sich seither auf der Platte des
    # Namensraums "control".
    "vpn-settings": _OVERLAY,
    # Die Einstellungen (Aufgabe 32, 19.08.2026): createShellWindow()
    # reicht an createOverlayWindow() weiter, also traegt dieses Fenster
    # dieselbe `.overlay-outer`-Platte wie die uebrigen elf - genau wie
    # das Kontrollzentrum, die andere Schale.
    "settings": _OVERLAY,
    "hyprlaunch": GlassPlate("styles/hyprlaunch-style.template",
                             ".launcher-container", ("overlay_subtext",),
                             None),
    "clipboard-manager": GlassPlate("styles/hyprclipx-style.template",
                                    ".cm-root", ("overlay_subtext",), None),
    "zepos-menu": GlassPlate("styles/zepos-menu-style.template", "#outer-box",
                             ("overlay_subtext",), None),
}


def _glass_layerrules():
    """Die layerrule-Zeilen fuer alle Flaechen, als ein Block Text.

    Zwei Zeilen je Flaeche, und beide werden gebraucht:

      blur on            schaltet die Unschaerfe fuer diese Flaeche
                         ueberhaupt ein. decoration:blur gilt sonst nur
                         fuer Fenster.
      ignore_alpha <s>   nimmt die durchsichtigen Stellen davon aus.
                         Ohne sie verwischt der Compositor auch den
                         Rand, den die Flaeche zum Schirm haelt, und um
                         die runden Ecken herum steht ein weicher grauer
                         Kasten.

    DIE SYNTAX IST DIE VON HYPRLAND 0.53+, UND SIE IST GEMESSEN
        Der erste Anlauf schrieb `layerrule = blur, zepos-bar` - die
        Form, die in jeder aelteren Anleitung im Netz steht. Hyprland
        0.55.4 lehnt sie ab, und zwar dreizehnmal, in genau der Datei,
        deren Scheitern den Nutzer die Sitzung kostet:
            invalid field blur: missing a value
            invalid field type ignorealpha
        Aufgefallen ist es tests/src/test_plugins.py, das die erzeugte
        Konfiguration durch `Hyprland --verify-config` schickt.

        Ausprobiert wurden am 11.08.2026 sieben Schreibweisen gegen
        genau diesen Prueflauf; angenommen werden zwei:
            layerrule = match:namespace ^(name)$, blur on
            layerrule = match:namespace ^(name)$, ignore_alpha 0.28
        Der Regelkopf heisst also `match:` und die Aktion braucht einen
        Wert - dieselbe Umstellung, die windowrule schon hinter sich hat.
        Und die Schwelle heisst `ignore_alpha` mit Unterstrich; ohne ihn
        ist es ein unbekanntes Feld.

    Der Namensraum steht als verankerter regulaerer Ausdruck da und
    nicht als blosses Wort: `match:namespace` vergleicht mit einem
    Muster, und ein unverankertes "vpn" traefe auch "vpn-settings".

    Erzeugt und nicht ausgeschrieben: 26 Zeilen von Hand sind 26
    Gelegenheiten, bei der vierzehnten Flaeche eine davon zu vergessen -
    und die vergessene faellt nicht auf, weil eine Flaeche ohne Regel
    genauso aussieht wie vorher.
    """
    threshold = THEME.GLASS_IGNORE_ALPHA
    lines = []
    for namespace in GLASS_LAYERS:
        match = f"match:namespace ^({namespace})$"
        lines.append(f"layerrule = {match}, blur on")
        lines.append(f"layerrule = {match}, ignore_alpha {threshold}")
    return "\n".join(lines)


_FIXED_STYLE_VARIABLES["STYLE_GLASS_LAYERRULES"] = _glass_layerrules()


# =============================================================================
# WAS AUF DER LEISTE STEHT - BEIDE HAELFTEN, EINSTELLBAR (Aufgabe #92)
# =============================================================================
#
# WARUM AUCH DIE LINKE LISTE HIER STEHT
#     Bis zum 12.08.2026 stand sie in ags-bar.template, waehrend die
#     rechte hier stand. Die Begruendung fuer die rechte gilt fuer die
#     linke woertlich genauso - "ein Zweig, den keine Liste nennt, ist
#     toter Code, und ein Name, den kein Zweig kennt, ein leerer Platz" -,
#     und dazu kam eine zweite: eine Liste in einer Vorlage ist nicht
#     einstellbar. Der Nutzer haette die eine Haelfte seiner Leiste
#     umsortieren koennen und die andere nicht, ohne dass irgendwo
#     stuende, warum.
#
#     Es entsteht dabei KEINE zweite Liste. Die Namen sind aus der
#     Vorlage hierher UMGEZOGEN; dort steht jetzt der Platzhalter.
#
# WAS DER NUTZER DARAN AENDERT
#     "bar.modules_left" / "bar.modules_right" in user-settings.json.
#     null heisst "wie ausgeliefert", eine Liste ERSETZT die
#     ausgelieferte vollstaendig. Die Regeln stehen in src/settings.py -
#     dort, weil die Einstellungs-Anwendung dieselbe Frage stellt und
#     beide dieselbe Antwort geben muessen.
#
# UND WARUM EIN UNBEKANNTER NAME HIER SCHON AUFFAELLT
#     Die Leiste selbst hat einen Rueckfall: build() gibt fuer einen
#     Namen ohne `case`-Zweig null zurueck und schreibt "Unbekanntes
#     Leistenmodul" auf die Konsole. Das ist die letzte Verteidigung und
#     eine schlechte erste - sie steht im AGS-Protokoll, das niemand
#     liest, und auf der Leiste bleibt ein leerer Platz.
#
#     Also wird schon HIER geprueft, gegen die ausgelieferte Liste, und
#     die Klage geht auf die Fehlerausgabe des Erzeugers - dorthin, wo
#     der Mensch gerade hinsieht, weil er eben etwas eingestellt hat.

# DIE VIER BEDINGTEN MODULE, UND WO SIE STEHEN (Aufgabe #94)
#
#     Vier der einundzwanzig Namen unten zeigen sich nur MANCHMAL, und
#     alle vier zeigen nichts, wenn sie nichts zu sagen haben - ihr
#     Skript gibt dann ein leeres "text", und applyPayload() in
#     ags-bar.template blendet das Modul aus. Ein unsichtbares Widget
#     beantwortet gtk_widget_measure mit 0, sie kosten also auch keinen
#     Platz.
#
#         custom/notifications  "Nicht stoeren" ist an, oder es kam
#                               etwas herein, seit das Zentrum zuletzt
#                               offen war.
#         custom/media          Ein Spieler spielt oder pausiert.
#         custom/updates        Etwas steht an: der letzte Lauf ist
#                               gescheitert, es muss neu erzeugt
#                               werden, oder Arch-Pakete liegen bereit.
#         custom/privacy        Irgendein Programm hat gerade das
#                               Mikrofon oder die Kamera offen.
#
#     DAS IST DER GRUND, AUS DEM ES UEBERHAUPT VIER NEUE SEIN DUERFEN.
#     Die Leiste trug am 12.08.2026 achtzehn Module und lief auf
#     1366x768 bei jeder Schriftgroesse ueber (COMPLETE_FROM in
#     tests/src/test_bar_headless.py). Vier weitere, die IMMER dastehen,
#     haetten das schlimmer gemacht. Vier, die es nur manchmal tun,
#     nicht - im Ruhezustand ist die Leiste unveraendert achtzehn
#     Module lang.
#
# WARUM SIE GENAU HIER IN DER REIHE STEHEN
#     Die Reihenfolge ist zugleich die EINKLAPPREIHENFOLGE: der rechte
#     Kasten geht von innen nach aussen, der linke von innen nach aussen
#     (siehe `order` in ags-bar.template). Was vorn im rechten Kasten
#     steht, verschwindet also zuerst ins Aufklappfenster.
#
#         custom/media      ganz vorn im rechten Kasten, also das
#                           ERSTE, was eingeklappt wird. Es ist auch das
#                           breiteste der vier - ein Titel statt eines
#                           Zeichens -, und was gerade laeuft, weiss man
#                           auch ohne Leiste.
#         custom/updates    hinten, kurz vor dem Kontrollzentrum. Es
#                           erscheint hoechstens einmal am Tag, und wenn
#                           es erscheint, ist es das, was man sehen
#                           soll.
#         custom/privacy    HINTER updates, also noch spaeter dran.
#                           Es ist die einzige Auskunft der Leiste, die
#                           etwas kostet, das man nicht zurueckbekommt.
#         custom/notifications  im LINKEN Kasten, direkt neben der Uhr,
#                           die das Zentrum oeffnet. Zwei Wege zu einer
#                           Sache gehoeren nebeneinander.
# DIE VORGABE VOM 12.08.2026, UND WAS SIE ERSETZT (Aufgabe #96)
#
#     BESTELLT, woertlich: "in der mitte die arbeitsbereiche links die
#     uhrzeit und datum den rest kennst du".
#
#     Daraus die drei Plaetze:
#
#         LINKS   Datum und Uhrzeit (custom/date sagt beides in EINER
#                 Zeile), Wetter, Zusatzuhren, daneben die Glocke.
#         MITTE   die Arbeitsbereiche. Sie stehen NICHT in diesen Listen -
#                 die Mitte ist der feste Platz des Gtk.CenterBox, siehe
#                 ags-bar.template.
#         RECHTS  alles, was eine Auskunft traegt: Wiedergabe, Hardware,
#                 Speicherplatz, Netz, Bluetooth, Ton, Mikrofon, Akku,
#                 die Ablage und die drei bedingten. Dazu die beiden
#                 Eingaenge ganz aussen - das Aussehen und das
#                 Kontrollzentrum. Die Begruendung dafuer, warum das
#                 seit dem 13.08.2026 wieder so viele sind, steht am
#                 Kopf von _modules_left.
#
#     DER FENSTERTITEL STEHT NICHT DABEI, UND DAS IST GEMESSEN
#         Bestellt war "wenn er dort ohne Ueberlauf passt". Er passt
#         ohne Ueberlauf - und er kostet die MITTE, also genau das, was
#         der Nutzer in derselben Zeile bestellt hat.
#
#         GEMESSEN am 12.08.2026 im verschachtelten Hyprland, mit einem
#         wirklichen Fenster (ein kitty mit dem Titel einer
#         Browserseite), an den Bildpunkten der gelben Knoepfe:
#
#             ohne Titel   Arbeitsbereiche mittig, 26 px neben der
#                          Schirmmitte (der Rest sind die 313 px des
#                          Datums gegen die 200 px rechts)
#             mit Titel    239 px daneben auf 1366, 243 px auf 1920
#
#         Der Grund steht in GTK: ein Gtk.CenterBox zentriert sein
#         Mittelstueck nur, solange Anfang und Ende in die Haelften
#         passen. Eine ellipsierende Beschriftung meldet als NATUERLICHE
#         Breite ihre volle Zeile - hier {{STYLE_MEASURE_LINE}}
#         Zeichen -, und um deren halbe Breite wandert die Mitte nach
#         rechts. Kuerzen hilft nicht: damit die Mitte auf 1366 stehen
#         bleibt, duerfte der Titel 142 px haben, also acht Zeichen.
#
#         Er ist deshalb ZUSCHALTBAR und nicht fort (siehe
#         _bar_optional), und er ist auch nicht ersatzlos: dieses System
#         laedt hyprbars (src/plugins.py), und das schreibt den Titel an
#         das Fenster selbst - dorthin, wo er hingehoert, wenn die
#         Leiste ihn nicht tragen kann.
#
#     WAS DAMIT VON DER LEISTE GEHT, UND WOHIN
#         Kein Modul ist geloescht worden; jedes hat weiter seinen
#         `case`-Zweig und steht in _bar_optional unten, ist also
#         zuschaltbar. Und jedes hat einen zweiten Weg, damit es auch
#         der findet, der die Einstellungen nicht kennt:
#
#           custom/hypr-shortcuts     Kontrollzentrum, "Tastenkuerzel"
#           custom/floating-layouts   Kontrollzentrum, "Schwebende Fenster"
#           custom/wallpaper          Kontrollzentrum, "Hintergrundbild"
#           custom/helpers            Kontrollzentrum, "Hilfsskripte"
#                                     (stand dort schon vorher)
#
#         Die sechs uebrigen, die am 12.08.2026 hier standen -
#         custom/clocks, custom/weather, custom/hardware, custom/disk,
#         bluetooth, pulseaudio#microphone -, sind am 13.08.2026 auf die
#         Leiste zurueckgekehrt. Ihre Zeile im Kontrollzentrum bleibt;
#         sie ist jetzt der zweite Weg und nicht mehr der einzige.
#
#     WARUM UEBERHAUPT, MIT DER ZAHL
#         GEMESSEN am 12.08.2026 mit tests/src/test_bar_headless.py auf
#         dem Stand 12c3b93: die achtzehn Module wollten 1902 px. Auf
#         1366x768 - dem verbreitetsten Notebookschirm - lagen deshalb
#         SECHS davon hinter dem Einklapp-Knopf (custom/helpers,
#         network, bluetooth, custom/hardware, pulseaudio,
#         pulseaudio#microphone), auf 1280 sieben.
#
#         Der Knopf ist die richtige Antwort auf einen Schirm, der
#         einmal zu klein ist, und die falsche auf die ausgelieferte
#         Vorgabe: was IMMER dahinter liegt, ist nicht eingeklappt,
#         sondern versteckt.
#
# UND WARUM DIESE KUERZUNG AM 13.08.2026 WIEDER ZURUECKGENOMMEN IST
#     Sie hat die Leiste auf fuenf Gruppen eingedampft, und der Nutzer
#     hat das am selben Tag VIERMAL beanstandet:
#
#         "rechts ist zu leer"
#         "im header will ich mehr rein schreiben"
#         "wir brauchen mehr informationen im header"
#         "es fehlt auch ein batterie icon ich weiss nicht wie voll der
#          laptop ist sollte im header stehen" - "und lautstaerke und
#          mikrofon auch"
#
#     Die Kuerzung hat die richtige Frage gestellt ("was passt auf
#     1366?") und die falsche Antwort gegeben. Eine Leiste ist eine
#     ANZEIGE; ihr Zweck ist Dichte. Was auf einem kleinen Schirm nicht
#     mehr hinpasst, klappt der Knopf weg - dafuer ist er da, und das ist
#     etwas anderes, als es gar nicht erst aufzustellen.
#
#     DIE REGEL SEITHER trennt nach "sagt es etwas" oder "tut es etwas":
#
#       auf der Leiste   jedes Modul, das eine AUSKUNFT traegt - eine
#                        Zahl, einen Zustand, eine Warnung. Man sieht
#                        hin, ohne zu klicken.
#       im Zentrum       was reine BEDIENUNG ist. custom/wallpaper waehlt
#                        ein Bild, custom/floating-layouts laedt eine
#                        Anordnung; beide zeigen im Ruhezustand ein
#                        Zeichen und sonst nichts, und beide haben ihre
#                        Zeile im Kontrollzentrum.
#
#     UND SEIT DEM 17.08.2026 HAT DIESE REGEL EINE AUSNAHME, DIE MIT
#     NAMEN DASTEHT: custom/theme und custom/system tragen keine
#     Auskunft und stehen trotzdem oben.
#
#         Beide sind EINGAENGE und keine Anzeigen - das Kontrollzentrum
#         und der Style Editor. Ein Eingang, der im Kontrollzentrum
#         liegt, ist genau dann unerreichbar, wenn man ihn braucht: der
#         Style Editor stand dort unter SYSTEMDIENSTE, zwischen Drucker
#         und Netz-Watchdog, und der Nutzer hat ihn mehrfach vermisst
#         ("theme manager icon im header fehlt immernoch").
#
#         Die Regel bleibt trotzdem richtig und wird nicht aufgeweicht:
#         sie sortiert ANZEIGEN. Fuer die zwei Eingaenge gilt daneben,
#         dass eine Sache genau einen Platz hat - custom/theme steht
#         oben, ALSO ist die Zeile im Kontrollzentrum weg, und nicht
#         beides.
#
#     custom/hardware ist ausdruecklich zurueck ("im header sollte btop
#     dargestellt werden wie am anfang auch", 13.08.2026): es ist die
#     einzige Stelle, an der Last, Speicher und Temperatur auf dem Schirm
#     stehen, und sein Klick oeffnet btop.
#
#     custom/helpers und custom/hypr-shortcuts sind ZAEHLER - "acht
#     Hilfsskripte", "66 Tastenkuerzel". Sie sagen etwas, das sich nie
#     aendert, und sind deshalb die beiden, die dieser Regel am
#     schwaechsten genuegen; sie bleiben zuschaltbar. Was das an Breite
#     spart, steht in tests/src/test_bar_headless.py.
#
# WAS AM 17.08.2026 IN DIE LINKE HAELFTE GEKOMMEN IST, UND WARUM IN
# GENAU DIESER REIHENFOLGE
#
#     BESTELLT, zwei Saetze desselben Tages, woertlich:
#
#         "hardware monitor icon soll nach links recht neben die zeit
#          anzeige"
#         "die tastatur icon fehlt auch noch links neben dem datum"
#
#     Beide Ansagen nennen dasselbe Nachbarmodul - custom/date sagt
#     Datum UND Uhrzeit in einer Zeile.
#
#     HIER STAND die Tastatur LINKS NEBEN dem Datum, weil "links neben
#     dem datum" sich woertlich so liest. Das war falsch, und der Nutzer
#     hat es am selben Tag richtiggestellt:
#
#         "wie ist die tastatus icon jetzt links von dem kaleder ich
#          wollte es rechts davon haben"
#
#     Gemeint war die linke HAELFTE der Leiste, nicht die Seite des
#     Datums. Also:
#
#         custom/date  custom/keyboard  custom/hardware  ...
#
#     WAS DAS AN DER EINKLAPPREIHENFOLGE AENDERT, und es ist die
#     bessere: der linke Kasten geht von innen nach aussen (siehe
#     `order` in ags-bar.template), das AEUSSERSTE Modul verschwindet
#     also zuletzt. Das ist jetzt custom/date - Datum und Uhrzeit
#     ueberleben am laengsten, und das ist auf einem engen Schirm die
#     richtige Rangfolge. Die Belegungsanzeige steht direkt dahinter und
#     faellt erst danach; sie bleibt damit weiterhin laenger stehen als
#     alles, was rechts von ihr liegt.
#
#     custom/hardware STAND VORHER RECHTS, direkt hinter custom/media.
#     Es ist kein neues Modul und keines mehr; es hat den Platz
#     gewechselt, und die Leiste traegt danach genauso viele.
#
# WAS DAS AN BREITE KOSTET, GEMESSEN am 17.08.2026 mit
# tests/src/test_bar_headless.py, Vorgabegroesse, zehn Arbeitsbereichen:
# die Zahl steht dort bei COMPLETE_FROM und FOLDED_ON_COMMON_NOTEBOOK,
# weil sie dort auch gehalten wird.
_modules_left = ["custom/date", "custom/hardware"]
_modules_left += ["custom/weather", "custom/clocks"]
_modules_left += ["custom/notifications"]

# DIE KUERZEL-ZAHL STAND IN KEINER DER BEIDEN HAELFTEN
#
#     GEMELDET am 19.08.2026: "ich sehe im header aber immernoch nicht
#     die keybind anzahl und bei klick erscheint die ganzen keybinds
#     warum nicht?"
#
#     Weil sie hier fehlte, und nur hier. Alles andere war fertig und
#     wurde nie gezeigt: ags-bar.template hat den Zweig
#     `case "custom/hypr-shortcuts"` mit `toggles: "shortcuts"`,
#     hypr-shortcuts-config.template zaehlt die Kuerzel und gibt
#     ICON_KEYBOARD plus die Zahl aus, dazu die ganze Liste als Tooltip,
#     und ags-shortcuts.template baut das Fenster dahinter. Ein Modul,
#     das gebaut wird und in keiner Belegung steht, ist unsichtbar -
#     ohne Fehlermeldung, ohne Luecke in der Leiste, ohne dass irgendein
#     Test es merkt.
#
#     WARUM ANS INNERE ENDE: die Reihenfolge IST die
#     Einklappreihenfolge, und der linke Kasten geht von innen nach
#     aussen. Was hier zuletzt steht, verschwindet auf einem engen
#     Schirm zuerst. Die Kuerzel-Zahl ist die entbehrlichste der
#     Anzeigen - man schlaegt Kuerzel nach, man beobachtet sie nicht -,
#     also traegt sie diesen Platz zu Recht.
#
#     UND WARUM custom/keyboard DAFUER WEICHT, statt die Zusage zu
#     senken: gemessen am 19.08.2026 passte die Leiste mit einem Modul
#     mehr auf einem 1680er Schirm nicht mehr - vier andere klappten
#     ein, darunter die LAUTSTAERKE. Die Zusage COMPLETE_FROM = 1680
#     ("ab hier zeigt die Leiste alles") zu erhoehen waere gewesen, den
#     Waechter an den Code anzupassen statt umgekehrt. Vor die Wahl
#     gestellt hat der Nutzer am selben Tag entschieden: "in die leiste
#     und keyboard icon mit de oder us weg".
#
#     Die Belegungsanzeige war am 17.08.2026 auf seinen Wunsch
#     hinzugekommen ("die tastatur icon fehlt auch noch links neben dem
#     datum") - sie faellt jetzt auf seinen Wunsch wieder weg. Das
#     Modul selbst bleibt gebaut; nur diese Liste nennt es nicht mehr.
#
#     Wer es anders will, braucht keinen Codewechsel: bar.modules_left
#     in user-settings.json ueberschreibt diese Liste.
_modules_left += ["custom/hypr-shortcuts"]

# Die Reihenfolge ist zugleich die EINKLAPPREIHENFOLGE (siehe `order` in
# ags-bar.template): der rechte Kasten geht von innen nach aussen. Was
# vorn steht, verschwindet zuerst.
#
# Geordnet nach dem, was am ehesten entbehrlich ist: zuerst das
# Wachsende - was gerade spielt und die Ablage -, dann die Messwerte und
# die Geraete, zuletzt die beiden, die nur bei einem Anlass etwas sagen.
# Ganz aussen das Kontrollzentrum - der Knopf, ueber den alles
# Eingeklappte ohnehin erreichbar bleibt.
#
# VIER GRUPPEN, VON INNEN NACH AUSSEN, UND SEIT DEM 20.08.2026 IN DIESER
# ORDNUNG (Aufgabe 42)
#
#     BESTELLT, woertlich: "ich wollte auch das du sie zentrierst die
#     icon und sie anders anordnest logisch gesehen im header". Die
#     Zentrierung ist der Tag davor (siehe dea3f0b); hier steht die
#     ANORDNUNG. Der Nutzer hat aus drei Entwuerfen diesen gewaehlt:
#
#         media tray | disk net bt vol mic bat | priv upd | theme Zahnrad
#         Programme  |         Zustand         | Hinweise |  Aktionen
#         waechst    |       feste Breite      |          |    fest
#
#     BEWEGT HAT SICH DABEI GENAU EIN MODUL: `tray` stand zwischen dem
#     Akku und den festen Knoepfen und steht jetzt als zweites, direkt
#     hinter `custom/media`. Die uebrigen elf behalten ihren Platz und
#     ihre Nachbarn.
#
# UND DER GRUND IST KEIN GESCHMACK: WACHSENDE MODULE VERSCHIEBEN
# KLICKZIELE
#
#     Die Ablage waechst um ein ganzes Symbol, sobald irgendein fremdes
#     Programm eines hineinstellt - `box.append(item.button)` je Dienst
#     in Tray() (ags-tray.template), ohne Obergrenze, und niemand fragt
#     die Leiste vorher.
#
#     IN WELCHE RICHTUNG DAS SCHIEBT, IST GEMESSEN UND NICHT GERATEN
#     (20.08.2026, tests/src/test_bar_headless.py, 1920 px,
#     Vorgabegroesse). Der rechte Kasten ist das Endstueck eines
#     Gtk.CenterBox und haengt damit an der RECHTEN Kante: seine rechte
#     Seite steht fest, seine linke wandert. Waechst ein Modul, geht das
#     Wachstum also nach INNEN - alles LINKS davon rueckt weg, alles
#     rechts davon bleibt stehen.
#
#     Nachgestellt an genau dem Platz, an dem die Ablage bis heute
#     stand (dem achten, zwischen Akku und Datenschutz): ein Modul dort
#     um 160 Punkte verbreitert, und SECHS Klickziele wandern mit -
#
#         custom-disk            1405 -> 1245   (-160)
#         network                1447 -> 1287   (-160)
#         bluetooth              1489 -> 1329   (-160)
#         pulseaudio             1550 -> 1390   (-160)
#         pulseaudio#microphone  1648 -> 1488   (-160)
#         battery                1733 -> 1573   (-160)
#         custom-theme           1812 -> 1812   (steht)
#         custom-system          1848 -> 1848   (steht)
#
#     Sechs Ziele, die man anklickt, und jedes von ihnen sitzt nach dem
#     naechsten Ablagesymbol woanders. Ein Klickziel, das sich unter dem
#     Zeiger bewegt, ist der Fehler - nicht seine Breite.
#
#     DIESELBE MESSUNG AM INNERSTEN PLATZ, und sie ist der ganze Beleg:
#     custom/media mit 121 Punkten aufgestellt, und KEIN Modul bewegt
#     sich um einen Punkt - custom-disk bleibt auf 1405, custom-system
#     auf 1848. Das Wachstum verschwindet in der Luecke zur Mitte, wo
#     nichts steht, das man anklickt.
#
#     DASSELBE GILT DESHALB FUER custom/media, und es steht aus diesem
#     Grund weiter ganz vorn: es ist ueberhaupt nur da, solange ein
#     Spieler laeuft, und es traegt einen TITEL - auf
#     STYLE_MEASURE_LINE Zeichen geschnitten (TITLE_LIMIT in
#     ags-media-scripts.template), also alles zwischen null und einer
#     halben Zeile.
#
#     NACH DEM UMBAU STEHT ALLES WACHSENDE INNEN, und das Einzige, was
#     ein neues Ablagesymbol noch verschiebt, ist custom/media - selbst
#     ein fluechtiges Modul und kein Ziel, das man blind anfaehrt.
#
#     DASS DAS SO BLEIBT, HAELT EIN WAECHTER:
#     test_kein_wachsendes_modul_steht_rechts_von_einem_festen_klickziel
#     in tests/src/test_bar_headless.py. Er liest beide Listen aus der
#     Quelle - die Reihenfolge aus shipped_bar_imprint(), die Einteilung
#     in "waechst" und "festes Klickziel" aus den `case`-Zweigen von
#     ags-bar.template und den Skripten, die sie nennen. Eine
#     abgeschriebene Liste veraltet still; dieser Baum hat daran an
#     einem Tag drei schlafende Tests gefunden.
#
#     ES IST AUCH EIN GEWINN AUF DEM SCHMALEN SCHIRM. Die Ablage ist
#     jetzt das zweite, was der Einklapper abgibt, statt des achten -
#     und sie ist der Posten, dessen Inhalt man am ehesten entbehrt:
#     jedes Ablagesymbol gehoert zu einem laufenden Programm, das man
#     auch ueber sein Fenster erreicht.
#
# WAS DAS AN BREITE KOSTET: NICHTS, UND DAS IST GEMESSEN am 20.08.2026
# mit tests/src/test_bar_headless.py (Vorgabegroesse, zehn
# Arbeitsbereiche, echte Zeichen):
#
#         Schirm   vorher   nachher   eingeklappt (nachher)
#          1024     1020      1020     9
#          1280     1256      1256     5
#          1366     1341      1341     4
#          1600     1504      1504     0
#          1680     1504      1504     0
#          1920     1504      1504     0
#
#     Punkt fuer Punkt dieselbe Leiste, und der Grund steht in
#     ags-tray.template: eine LEERE Ablage ist unsichtbar
#     (`box.set_visible(items.size > 0)`), und ein unsichtbares Widget
#     beantwortet gtk_widget_measure mit 0. Sie kostet im Ruhezustand
#     nichts, egal wo sie steht - ein Umzug ohne Preis.
#
#     Der Unterschied faellt an, sobald ein Symbol darin liegt, und
#     genau dann ist er der bestellte: die Ablage geht als zweite hinter
#     den Knopf, und nicht der Akku.
_modules_right = ["custom/media"]
# custom/hardware stand hier und steht seit dem 17.08.2026 links neben
# dem Datum - siehe den Block ueber _modules_left.
#
# DIE ABLAGE STEHT SEIT DEM 20.08.2026 HIER und nicht mehr hinter dem
# Akku - die ganze Begruendung steht im Block darueber. Kurz: sie ist
# das einzige Modul der Leiste, dessen Breite ein FREMDES Programm
# bestimmt, ihr Wachstum geht nach INNEN, und deshalb darf nichts, was
# man anklickt, links von ihr stehen.
_modules_right += ["tray"]
_modules_right += ["custom/disk"]
_modules_right += ["network", "bluetooth", "pulseaudio",
                   "pulseaudio#microphone", "battery"]
# custom/theme steht DIREKT VOR dem Kontrollzentrum, und beides ist eine
# Entscheidung.
#
#     WARUM ES UEBERHAUPT AUF DER LEISTE STEHT (17.08.2026)
#         GEMELDET, zum wiederholten Mal: "theme manager icon im header
#         fehlt immernoch". Der Style Editor war nur ueber eine Zeile im
#         Kontrollzentrum erreichbar, im Abschnitt SYSTEMDIENSTE - die
#         Zeile ist dafuer weg (siehe ags-control-center.template).
#
#     WARUM AUSSEN UND NICHT VORN
#         Die Reihenfolge IST die Einklappreihenfolge, von innen nach
#         aussen. Weiter vorn waere das Zeichen auf einem 1366er Schirm
#         als eines der ersten hinter dem Knopf verschwunden - also
#         genau dort, wo der Nutzer es viermal vermisst hat. Neben dem
#         Zahnrad ist ausserdem der Platz, an dem man es sucht: zwei
#         Knoepfe, die beide etwas einstellen, stehen nebeneinander.
#
#     WAS ES KOSTET, GEMESSEN am 17.08.2026 mit
#     tests/src/test_bar_headless.py, Vorgabegroesse, zehn
#     Arbeitsbereichen:
#
#         vorher   1510 px Mindestbreite, auf 1366 klappen drei Module
#                  ein (custom-hardware, custom-disk, network)
#         nachher  1558 px, auf 1366 klappen VIER ein - bluetooth kommt
#                  dazu
#
#         48 Punkte, und das ist GENAU die Zeichenbreite und kein
#         Pixel Rand: der Knopf steht im Block am rechten Ende, und der
#         traegt `margin-left: 0; margin-right: 0` (siehe
#         src/styles/bar-style.template bei #custom-disk). Ein Modul in
#         der Reihe davor haette 15 Punkte mehr gekostet.
#
#         Die Grenze aus COMPLETE_FROM bleibt bei 1600, und der Schirm
#         des Nutzers ist 1920x1200 bei Faktor 1.00 - dort steht alles.
#
# GEMELDET UND NICHT ENTSCHIEDEN am 20.08.2026 (Aufgabe 42): custom/privacy
# UND custom/updates STEHEN HIER ANDERSHERUM, ALS DER BLOCK OBEN SAGT.
#
#     Im Absatz "DIE VIER BEDINGTEN MODULE" weiter oben steht woertlich:
#     "custom/privacy HINTER updates, also noch spaeter dran. Es ist die
#     einzige Auskunft der Leiste, die etwas kostet, das man nicht
#     zurueckbekommt." Diese Liste stellt sie umgekehrt auf - erst
#     Datenschutz, dann Aktualisierungen -, der Datenschutz klappt also
#     FRUEHER ein und nicht spaeter.
#
#     DAS IST AELTER ALS DIESE AUFGABE UND WIRD VON IHR NICHT BERUEHRT:
#     `git log -S` findet die Zeile unveraendert seit edb20e2, der ersten
#     oeffentlichen Fassung, und der Umbau vom 20.08.2026 bewegt allein
#     `tray`. Der vom Nutzer gewaehlte Entwurf schreibt an dieser Stelle
#     "priv upd" und bestaetigt damit die Reihenfolge, wie sie hier steht.
#
#     Aufgeloest wird der Widerspruch trotzdem nicht im Vorbeigehen: der
#     Kommentar oben nennt einen GRUND, und ihn zu streichen oder die
#     Liste zu drehen waere beides eine Entscheidung ueber eine
#     Sicherheitsanzeige, die dem Nutzer gehoert und nicht dieser Zeile.
#     Er steht im Bericht zu Aufgabe 42.
_modules_right += ["custom/privacy", "custom/updates",
                   "custom/theme", "custom/system"]

# WAS DIE LEISTE AUSSERDEM TRAGEN KANN
#
#     Jeder `case`-Zweig aus ags-bar.template, den die Vorgabe oben
#     nicht aufstellt. Ohne diese Liste waeren es fuenf tote Zweige -
#     und der Nutzer haette fuenf Funktionen verloren statt fuenf
#     Module umgeraeumt.
#
#     DAS IST DER UNTERSCHIED ZWISCHEN "AUSGELIEFERT" UND "MOEGLICH",
#     UND ER HAT AM 12.08.2026 GEFEHLT. bar_order() verwarf jeden
#     Namen, der nicht in der ausgelieferten Haelfte stand, und die
#     Seite "Leiste" bot nur an, was ausgeliefert und gerade nicht
#     aufgestellt war. Ein Modul aus der Vorgabe zu nehmen hiess damit,
#     es UNERREICHBAR zu machen: weder ueber user-settings.json noch
#     ueber das Einstellungsfenster waere es zurueckgekommen.
#
#     hyprland/workspaces fehlt hier mit Absicht: die Mitte ist kein
#     Listenplatz. Sie in eine Haelfte zu stellen hiesse, sie zweimal
#     zu bauen - der `case`-Zweig gibt beide Male dasselbe Widget
#     zurueck, und ein Widget hat einen Elternteil.
#
#     GETAUSCHT am 19.08.2026: custom/hypr-shortcuts steht jetzt in
#     _modules_left (siehe dort) und damit nicht mehr hier - es ist
#     ausgeliefert und nicht mehr bloss moeglich. An seiner Stelle steht
#     custom/keyboard: sein `case`-Zweig in ags-bar.template bleibt
#     (der Nutzer wollte nur das ZEICHEN von der Leiste, nicht die
#     Faehigkeit geloescht haben), aber es traegt keine der beiden
#     Haelften mehr. Ohne diesen Eintrag waere es der sechste tote
#     Zweig aus dem Absatz oben, unerreichbar auch fuer
#     bar.modules_left in user-settings.json. Die Liste bleibt fuenf
#     Eintraege lang - der Tausch aendert die Zahl nicht, nur den
#     Namen.
_bar_optional = ["hyprland/window", "custom/keyboard",
                 "custom/floating-layouts", "custom/helpers",
                 "custom/wallpaper"]

# Die ausgelieferten Listen, unter dem Namen, unter dem sie gespeichert
# werden. Der Abdruck unten und die Pruefung darueber lesen beide von
# hier, damit ein Umbenennen nicht an einer Stelle vergessen werden kann.
SHIPPED_BAR_MODULES = {
    settings_module.BAR_LEFT: _modules_left,
    settings_module.BAR_RIGHT: _modules_right,
}

# Was eine Haelfte ueberhaupt tragen kann - die Vorgabe plus das
# Zuschaltbare. EINE Liste fuer beide Haelften und nicht zwei: ein Modul
# ist nicht links oder rechts von Natur aus, es steht dort, wo man es
# hinstellt. Wer die Uhr rechts haben will, soll sie rechts haben.
BAR_MODULES_AVAILABLE = [*_modules_left, *_modules_right, *_bar_optional]


def _bar_modules(key):
    """Die Namen einer Haelfte, nachdem der Nutzer daran war.

    Verworfen wird gegen BAR_MODULES_AVAILABLE und nicht gegen die
    `case`-Zweige der Vorlage: die Zweige stehen in TypeScript, und ein
    Erzeuger, der sie mit einem regulaeren Ausdruck aus einer Vorlage
    liest, haette eine zweite, stillschweigende Definition davon, was
    ein Modul ist. Die Liste und die Zweige werden ohnehin schon
    gegeneinander gehalten - in tests/src/test_reference_resolution.py,
    in beide Richtungen -, also ist "steht in BAR_MODULES_AVAILABLE"
    genau dasselbe wie "hat einen Zweig", nur an einer Stelle, an der es
    der Erzeuger auch wirklich weiss.
    """
    chosen = settings_module.bar_choice(USER_SETTINGS, key)
    names, discarded = settings_module.bar_order(
        chosen, BAR_MODULES_AVAILABLE, SHIPPED_BAR_MODULES[key])
    if discarded:
        print(settings_module.bar_complaint(key, discarded), file=sys.stderr)
    return names


_FIXED_STYLE_VARIABLES["STYLE_BAR_MODULES_LEFT"] = json.dumps(
    _bar_modules(settings_module.BAR_LEFT))
_FIXED_STYLE_VARIABLES["STYLE_BAR_MODULES_RIGHT"] = json.dumps(
    _bar_modules(settings_module.BAR_RIGHT))


def shipped_bar_imprint():
    """Der Abdruck der ausgelieferten Leiste - siehe src/settings.py.

    Er wird von package() nach /usr/share/zepos/shipped-bar.json
    geschrieben, damit die Einstellungs-Anwendung die ausgelieferte
    Reihenfolge ZEIGEN kann, ohne dieses Modul zu importieren: der
    Import hier fragt `hyprctl` nach den Bildschirmen, und ein
    Einstellungsfenster, das dafuer den Compositor braucht, geht auf
    einer Maschine ohne Hyprland nicht mehr auf.

    Derselbe Kniff wie /usr/share/zepos/shipped-applications, und aus
    demselben Grund - der Kopf von src/apps.py fuehrt ihn aus.

    AUSGELIEFERT und nicht eingestellt: hier stehen die Listen, wie sie
    aus dem Paket kommen. Wogegen sonst sollte bar_order() die Wahl des
    Nutzers halten?

    MODULES_AVAILABLE steht daneben, weil "ausgeliefert" und "moeglich"
    seit dem 12.08.2026 zwei Listen sind - die Begruendung steht bei
    BAR_AVAILABLE in src/settings.py. Ohne diesen Eintrag koennte weder
    der Erzeuger noch das Einstellungsfenster ein zugeschaltetes Modul
    von einem Schreibfehler unterscheiden.

    OHNE DIE ANHEFTUNGEN, UND DAS IST AM 13.08.2026 GEMESSEN WORDEN
        Hier stand `settings_module.BAR_PINS: apps.imprint_pins()`, und
        der Paketbau ist daran gescheitert:

            AssertionError: {... 'dock_pins': []}

        zepos-config wird aus einem Tarball gebaut, in dem packaging/
        nicht liegt, und /usr/share/zepos ist zu diesem Zeitpunkt leer.
        apps.shipped() findet also weder das Rezept noch den Abdruck und
        antwortet mit einer leeren Liste - eine richtige Antwort auf eine
        Frage, die dieses Paket gar nicht stellen darf.

        Die Anwendungsauswahl gehoert zepos-apps und hat dort ihren
        eigenen Abdruck. settings.shipped_bar() holt sie beim LESEN von
        dort; fuer jeden Aufrufer sieht der Abdruck unveraendert aus und
        traegt weiter alle vier Schluessel.
    """
    return {
        settings_module.BAR_LEFT: list(_modules_left),
        settings_module.BAR_RIGHT: list(_modules_right),
        settings_module.BAR_AVAILABLE: list(BAR_MODULES_AVAILABLE),
    }


# =============================================================================
# THE MONITOR-DEPENDENT HALF
# =============================================================================

# DIE TOTE GROESSEN-KETTE FIEL AM 18.08.2026
#
#     _WIDGET_WINDOW_WIDTHS und _WIDGET_SCROLL_HEIGHTS standen hier:
#     Widget -> Vorgabe-BREITE seines Fensters, Widget -> Vorgabe-HOEHE
#     seiner Bildlauflaeche. _monitor_style_variables() baute daraus, pro
#     angeschlossenem Schirm, STYLE_EWW_WINDOW_<WIDGET>_MON<n> und
#     STYLE_EWW_SCROLL_<WIDGET>_MON<n> - je aus get_widget_size_for_monitor()
#     und get_widget_scroll_for_monitor(), die wiederum user-settings.json
#     unter widget_sizes.<breite>.<widget> lasen. Diese Zahlen kamen vom
#     Reiter "Größen" im Stil-Editor (ags-style-editor.template):
#     zehn Fenster mal vier Aufloesungen mal zwei Masse, vierzig Regler.
#
#     GEMESSEN am 18.08.2026, `grep -rl` gegen src/templates/ UND
#     src/styles/: NULL Vorlagen lasen STYLE_EWW_WINDOW_* oder
#     STYLE_EWW_SCROLL_*, ob mit oder ohne MON-Suffix. Jedes Fenster nahm
#     stattdessen seine eigene, ausgemessene WIN_WIDTH-Konstante im
#     Vorlagenkopf. Die ganze Kette - der Reiter, widget_sizes in
#     DEFAULT_SETTINGS, die vier Funktionen, die sie lasen, und die
#     Platzhalter, die sie erzeugten - ist deshalb geloescht, samt der
#     fuenf verwandten STYLE_EWW_SCROLL_*-Eintraege ohne MON-Suffix, die
#     direkt in _FIXED_STYLE_VARIABLES standen (siehe die Notiz dort).
#
#     An ihre Stelle tritt die Breitenleiter in src/sizes.py
#     (MODAL_WIDTHS) - drei Sprossen, die das Fenster selbst nennt, statt
#     vierzig Zahlen, die niemand las.
#
#     Was von dieser Funktion stehen bleibt, sind STYLE_SCALE_INFO und
#     STYLE_SCALE_FACTOR_MON<n> - die einzigen Werte, die tatsaechlich
#     einen Compositor brauchen.


def _monitor_style_variables():
    """The style values that depend on what is plugged in.

    Separated from _FIXED_STYLE_VARIABLES because these are the only
    values that need the compositor, and building them is the only thing
    that may ask it.
    """
    variables = {"STYLE_SCALE_INFO": scale_info()}
    for index in range(MONITOR_SLOTS):
        variables[f"STYLE_SCALE_FACTOR_MON{index}"] = (
            f"{MONITOR_WIDTH_SCALES.get(index, 1.0):.2f}")
    return variables


class _StyleVariables(Mapping):
    """Every {{STYLE_*}} value, with the monitor-dependent ones deferred.

    template_processor asks this by name, once per placeholder a
    template actually contains (`placeholder in self.styles`, then
    `self.styles[placeholder]`). So a template that names no per-monitor
    value never reaches _monitor_style_variables(), and the generator
    process it runs in never starts `hyprctl` at all - which is the
    difference between a `--all` run costing one compositor query per
    template and costing none.

    Asking for the whole set - dict(STYLE_VARIABLES) - does query, once:
    it is a request for every value, monitor-dependent ones included.
    """

    def __getitem__(self, name):
        if name in _FIXED_STYLE_VARIABLES:
            return _FIXED_STYLE_VARIABLES[name]
        return _monitor_style_variables()[name]

    def _all(self):
        return {**_FIXED_STYLE_VARIABLES, **_monitor_style_variables()}

    def __iter__(self):
        return iter(self._all())

    def __len__(self):
        return len(self._all())

    def __repr__(self):
        return repr(self._all())


STYLE_VARIABLES = _StyleVariables()
