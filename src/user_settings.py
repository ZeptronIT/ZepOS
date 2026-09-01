#!/usr/bin/env python3
"""
User Settings Manager for ZepOS
Handles reading, writing, and merging user settings for style customization.

Settings are stored GLOBALLY (for all profiles) in:
    <user root>/user-settings.json

This means colors and other settings apply to ALL profiles on this PC,
not per-profile.

Usage as module:
    from user_settings import load_settings, save_settings, get_defaults

Usage as CLI:
    python3 user_settings.py get
    python3 user_settings.py save --scale-1920 1.0 --scale-2560 1.2
    python3 user_settings.py set-color --key success --value "#a6e3a1"
    python3 user_settings.py set-size --scale 1.5
    python3 user_settings.py set-size --key STYLE_FONT_SIZE --value 20px
    python3 user_settings.py list-sizes
    python3 user_settings.py set-weather-location --value "Berlin"
    python3 user_settings.py reset
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Flat import: this module is executed as a script from the system
# root, the same way template_processor.py imports icons_db.
import brand
import sizes
from paths import user_root

# The file belongs to settings.py, and this module reads and writes it
# THROUGH settings.py rather than beside it.
#
# It used to have its own pair: json.load() in a try/except that warned
# and carried on with the defaults, and `open(path, 'w')` + json.dump()
# to write. Both halves were wrong in a way that only showed up together.
# The write truncates the file to zero bytes the instant it is opened and
# creates a new one at 0644 - on a document that may hold a VPN
# pre-shared key, and that another process may be reading in exactly that
# window. The read then answered that empty file with the defaults, so
# `set-color` over a settings file this program had failed to parse
# SAVED the defaults over it: the one command that could still have
# recovered the user's settings destroyed them instead. Refusing costs a
# command; guessing cost the file.
#
# SCHEMA_VERSION is taken from there for the same reason. A settings file
# this module created from its own defaults carried no version at all, so
# every versioned reader - zepos-settings among them - refused it on a
# machine where the user had done nothing but change a colour.
from settings import SCHEMA_VERSION, UnusableSettings
from vpn import connection as _vpn_connection
from settings import load as read_settings_document
from settings import merge as merge_settings_sections
from settings import unreadable as unreadable_message

# =============================================================================
# DEFAULT SETTINGS
# =============================================================================

# EINE VPN-VERBINDUNG, WIE SIE UNKONFIGURIERT AUSSIEHT
#
#     Hiess bis zum 22.08.2026 DEFAULT_SETTINGS["vpn"] und ist Zeichen
#     fuer Zeichen dasselbe: der Abschnitt ist nicht umgebaut, er ist
#     eine Ebene tiefer gerutscht. Die Begruendung fuer die Liste steht
#     bei DEFAULT_SETTINGS["vpn"] unten und ausfuehrlich in
#     src/settings.py.
#
#     Dass es diese Tabelle NEBEN settings.default_connection() gibt,
#     ist aelter als diese Aufgabe und wird von
#     tests/src/test_vpn_wireguard.py bewacht - die beiden tragen fuer
#     WireGuard und OpenVPN dieselben Schluessel. Fuer `phase1`,
#     `phase2`, `username` und `remember_username` gilt das NICHT: die
#     stehen nur hier. GEMESSEN am 22.08.2026 durch Vergleich der
#     beiden Tabellen - ein eigener, aelterer Fund, hier benannt und
#     nicht miterledigt, weil ihn zu beheben Vorgabewerte aendern
#     wuerde und nicht Struktur.
DEFAULT_CONNECTION = {
    # Welche Bauart: "ipsec" (strongSwan) oder "wireguard"
    # (NetworkManager). Vorgabe "ipsec", nie geraten - jede
    # Installation von vor dem 21.08.2026 hat diesen Schluessel
    # nicht und muss auf ihrem bisherigen Pfad bleiben.
    "kind": "ipsec",
    "server": "",
    "username": "",
    "connection_name": "work",
    "remember_username": True,
    # One CIDR per entry. The generator derives one child security
    # association and one route from each. The origin had a single
    # child SA carrying three comma-separated networks in one string,
    # which is why adding a fourth meant editing a string.
    "routed_networks": [],
    # Networks kept OUTSIDE the tunnel even though a routed network
    # covers them - a parallel WireGuard link into a home LAN inside
    # 192.168.0.0/16, for instance. The origin had exactly one, its
    # own, written into the connect script alongside the German
    # interface name of its own router.
    "bypass_networks": [],
    # A host that only answers through the tunnel, so that an
    # established tunnel carrying no traffic can be told apart from a
    # working one.
    "test_host": "",
    "phase1": {
        "version": 2,
        "aggressive": False,
        "proposals": "aes256-sha256-ecp521",
        "keylife": 86400,
        "dpd_delay": 30,
        "dpd_timeout": 120,
        "encap": True,
        "mobike": False
    },
    "phase2": {
        "rekey_time": 43200,
        "life_time": 43200,
        "mode": "tunnel",
        "replay_window": 32,
        "esp_proposals": "aes256-sha256-ecp521"
    },
    "dns": {
        "servers": [],
        "search_domain": ""
    },
    # WireGuard, seit dem 21.08.2026 die zweite Bauart. Rein
    # ADDITIV, und `schema_version` bleibt darum 1: load()
    # weist jede andere Version ab, eine Wanderung gibt es
    # nicht, und get_user_vpn_setting() faellt je Schluessel auf
    # seine Vorgabe zurueck. Eine Installation von vorher hat
    # kein `kind`, bekommt "ipsec" und laeuft Zeile fuer Zeile
    # weiter wie bisher.
    #
    # KEIN GEHEIMNIS STEHT HIER. `private_key_file` und
    # `preshared_key_file` tragen DATEINAMEN, nicht Schluessel:
    # dieses Dokument liest der Stil-Erzeuger, gibt
    # `zepos-settings` aus und fasst der Doktor an. Die
    # Schluessel liegen unter ~/.config/wireguard, 0600 vom
    # ersten Byte, Verzeichnis 0700 - siehe
    # src/vpn.py::write_wireguard_secret().
    "wireguard": {
        "addresses": [],
        "listen_port": 0,
        "mtu": 0,
        "private_key_file": "",
        "public_key": "",
        "peers": [],
    },
    # OpenVPN, seit dem 22.08.2026 die dritte Bauart. Rein
    # ADDITIV wie WireGuard, `schema_version` bleibt 1.
    #
    # KEIN GEHEIMNIS STEHT HIER. `ca_file`, `cert_file`,
    # `key_file`, `tls_auth_file` und `tls_crypt_file` tragen
    # DATEINAMEN; die Dateien liegen unter ~/.config/openvpn,
    # 0600 vom ersten Byte, Verzeichnis 0700 - siehe
    # src/vpn.py::store_openvpn_blobs(). Das Passwort steht
    # ueberhaupt nicht auf der Platte: es geht beim Verbinden
    # ueber eine 0600-Datei im Laufzeitverzeichnis an
    # `nmcli ... passwd-file` und wird danach geloescht.
    #
    # `extra` traegt die Direktiven, fuer die es kein eigenes
    # Feld gibt - aus einer ERLAUBNISLISTE
    # (OVPN_CARRIED_EXTRA), nie eine Durchreiche. Die achtzehn
    # ausfuehrenden Direktiven sind lange vorher abgelehnt.
    "openvpn": {
        "remote": "",
        "port": 0,
        "proto": "udp",
        "dev": "tun",
        "dev_type": "",
        "connection_type": "tls",
        "username": "",
        "remote_cert_tls": "",
        "cipher": "",
        "auth": "",
        "comp_lzo": "",
        "tunnel_mtu": 0,
        "reneg_seconds": -1,
        "ta_dir": "",
        "ca_file": "",
        "cert_file": "",
        "key_file": "",
        "tls_auth_file": "",
        "tls_crypt_file": "",
        "pkcs12_file": "",
        "extra": [],
    },
    "xauth_enabled": False,
    "debug": False
}


DEFAULT_SETTINGS = {
    # Both writers of this file state it - see the import above.
    "schema_version": SCHEMA_VERSION,
    "_meta": {
        "version": "3.0",
        "profile": "",
        "created": "",
        "modified": ""
    },
    # DEN REITER "FENSTERGROESSEN" GAB ES, UND ER HAT NIE ETWAS BEWIRKT
    #
    #     Er bot zehn Fenster mal vier Aufloesungen an, schrieb sie nach
    #     user-settings.json unter widget_sizes, und style_definition.py
    #     machte daraus die Platzhalter STYLE_EWW_WINDOW_<WIDGET>_MON<n>
    #     und STYLE_EWW_SCROLL_<WIDGET>_MON<n>.
    #
    #     GEMESSEN am 18.08.2026, `grep -rl` gegen src/templates/ UND
    #     src/styles/: NULL Vorlagen lasen einen dieser Platzhalter. Die
    #     Fenster nahmen stattdessen ihre eigene, ausgemessene WIN_WIDTH.
    #     Vierzig Regler ohne Wirkung.
    #
    #     Das EWW im Namen ist der Rest einer Leiste, die dieses Projekt
    #     nicht mehr hat. An ihre Stelle tritt die Breitenleiter in
    #     sizes.py - drei Sprossen, die das Fenster selbst nennt.
    # One factor per width bracket, and it scales widths. A "height"
    # stood beside every one of these - see RETIRED_SCALING_DIMENSION.
    "scaling": {
        "1920": {"width": 1.00},
        "2560": {"width": 1.20},
        "3440": {"width": 1.35},
        "3840": {"width": 1.50}
    },
    # THE COLOURS ARE NOT WRITTEN OUT HERE ANY MORE.
    #
    # They were, and that made this the first of three copies of
    # ninety-nine values that all had to agree: this dict, the `default`
    # argument of every get_user_color() call in style_definition.py, and
    # the `default:` field of the style editor's colour list. They
    # already disagreed - `warning` was #f9e2af here and #fab387 in the
    # third - so which yellow a machine showed depended on whether
    # anybody had ever opened the editor.
    #
    # src/brand.py is the one place now. It also says why each value is
    # what it is, which a column of hex literals could not.
    #
    # A copy rather than the dict itself: get_defaults() deep-copies this
    # structure and every caller is free to mutate what it gets back, and
    # one of them mutating the module-level palette would recolour the
    # desktop of every later call in the same process.
    "colors": dict(brand.COLORS),
    # Wie gross der Schreibtisch ist: ein Faktor, plus die Ausnahmen
    # davon. src/sizes.py haelt die Tabelle der einstellbaren Namen und
    # begruendet den Vorgabefaktor.
    #
    # HIER STANDEN ZWEI ABSCHNITTE, DIE NICHTS TATEN.
    #
    #     "fonts":   {"base_size": 13, "icon_size": 18}
    #     "spacing": {"module": 10, "bar_height": 50}
    #
    # Vier Zahlen, die genau den vier Werten entsprachen, die
    # style_definition.py als Literale ausschrieb - und keine einzige
    # davon wurde je gelesen. GEMESSEN am 11.08.2026: "fonts",
    # "base_size", "icon_size" und "spacing" kommen ausserhalb dieser
    # Zeilen im ganzen Baum nicht vor. Sie wurden trotzdem von jedem
    # Speichern in die Datei des Nutzers zurueckgeschrieben, also vier
    # Regler, die aussahen wie Regler, sich anfassen liessen wie Regler
    # und nichts bewegten. Dieselbe Geschichte wie
    # RETIRED_SCALING_DIMENSION weiter unten, nur ohne Migration.
    #
    # Sie sind ersatzlos weg, weil "sizes" sie ersetzt: base_size ist
    # STYLE_FONT_SIZE, bar_height ist STYLE_BAR_THICKNESS, module ist
    # STYLE_MODULE_SPACING - und diese drei erreichen jetzt eine Vorlage.
    # Keine Migration: die alten Werte SIND die Vorgaben, die neuen
    # Namen tragen dieselben Zahlen, und ein Wert, der nie gewirkt hat,
    # hat nichts, was gerettet werden koennte.
    "sizes": sizes.defaults(),
    # Every value that identifies a network is empty here on purpose.
    # The origin shipped its employer's gateway address, its own account
    # name, that employer's domain and its two internal resolvers, so a
    # stranger's installation arrived pre-aimed at a company they had
    # never heard of - and, worse, half-aimed: enough to look configured,
    # not enough to work, with no way to tell which of the two it was.
    #
    # The tuning values below are not identifying and stay, so a user who
    # fills in a server and a network gets a tunnel that works.
    # DER VPN-ABSCHNITT IST SEIT DEM 22.08.2026 EINE LISTE
    #
    #     "kann ich auch zwei wireguard verbindungen hinzufuegen,
    #      sodass ich immer die nutze, die ich brauche?"
    #
    #     Bis hierher trug `vpn` GENAU EINE Verbindung. Wer WireGuard
    #     einstellte, verlor damit seinen IPsec-Zugang, ohne dass ihn
    #     jemand gefragt haette. `active` traegt die KENNUNG der
    #     gewaehlten Verbindung, nie ihren Namen - die ausfuehrliche
    #     Begruendung steht in src/settings.py.
    "vpn": {"active": "", "connections": []},
    "watchdog": {
        # A public resolver, unlike the VPN values above: this only asks
        # whether the machine has any connectivity at all, so a working
        # default harms nobody and an empty one would silently disable
        # the watchdog.
        "test_host": "1.1.1.1",
        # Empty means "work it out from the default route". The origin
        # wrote its own VM's gateway, interface and static address in, so
        # on any other machine the watchdog reported an unreachable
        # gateway forever and never acted at all.
        "gateway": "",
        "interface": ""
    },
    # Extra clocks beside the local time. Empty for the same reason the
    # weather location is: the origin put its author's two countries on
    # every user's bar - two templates, each with a timezone, a flag and
    # a locale written into it - and a user with colleagues in three
    # timezones could have none of them. An entry is an IANA name, or a
    # name with a label the user writes themselves; see src/clocks.py for
    # why no flag can be derived from a timezone.
    "clocks": {
        "format": "%H:%M",
        "zones": []
    },
    "weather": {
        # Empty, and emptier than the VPN values above: an unset weather
        # location does not merely leave a feature unconfigured, it is
        # what keeps the bar from telling wttr.in - a third party - where
        # this machine stands, every time the module refreshes. The
        # origin had two scripts with one city each written into the URL.
        # Whoever wants the weather says where; nobody else does.
        "location": ""
    }
}

# The half of a scaling bracket that is being taken out of service, and
# what to tell the user's own settings file about it.
#
# Every bracket used to carry {"width": w, "height": h}. The width is
# read - style_definition derives STYLE_SCALE_FACTOR_MON* from it. The
# height was read by calculate_height_scale(), which fed
# MONITOR_HEIGHT_SCALES, which nothing called: no generated file changed
# by a single byte whichever height a user stored. It was nevertheless
# offered here with four defaults, migrated by migrate_scaling() and
# written back by every save - a setting maintained with some care and
# connected to nothing.
#
# KORREKTUR vom 18.08.2026: hier stand, die Hoehe sei retired statt
# angeschlossen worden, WEIL sie bereits ueber widget_sizes.<width>
# .<widget>.height ankomme - "was the AGS style editor writes". Das war
# nie wahr. GEMESSEN am 18.08.2026, `grep -rl` gegen src/templates/ UND
# src/styles/: STYLE_EWW_WINDOW_* und STYLE_EWW_SCROLL_*, die einzigen
# Platzhalter, die widget_sizes je erreichte, hatten NULL Leser.
# widget_sizes ist seit demselben Tag geloescht (siehe die Notiz an
# seiner alten Stelle in DEFAULT_SETTINGS oben). Ein Widget-Fenster war
# schon vorher HOCH ueber seine eigene, ausgemessene Konstante im
# Vorlagenkopf und nicht ueber eine Einstellung - genau wie beim
# Breitenfaktor, der hier tatsaechlich retired und nicht angeschlossen
# wurde.
RETIRED_SCALING_DIMENSION = "height"
RETIRED_SCALING_REASON = (
    "Nothing read this: the only factor derived from the scaling section "
    "is the width one. What a widget is high was never read from here - "
    "each window carries its own measured height. The value you chose is "
    "kept here so it is not lost, and is no longer applied."
)

# =============================================================================
# PATH HELPERS
# =============================================================================

def get_zepos_dir():
    """Get the ZepOS user directory"""
    return user_root()

def get_profiles_dir():
    """Get the profiles directory"""
    return get_zepos_dir() / "profiles"

def get_profile_dir(profile_name):
    """Get directory for a specific profile"""
    return get_profiles_dir() / profile_name

def get_settings_path(profile_name=None):
    """
    Get path to user-settings.json.

    GLOBAL settings - applies to ALL profiles on this PC.
    The profile_name parameter is ignored (kept for backwards compatibility).
    """
    return get_zepos_dir() / "user-settings.json"

def get_current_profile():
    """Read current profile name from hyprland config"""
    profile_file = Path.home() / ".config" / "hypr" / "current-profile"
    if profile_file.exists():
        return profile_file.read_text().strip()
    return None

# =============================================================================
# CORE FUNCTIONS
# =============================================================================

def get_defaults():
    """Return a copy of the default settings"""
    return json.loads(json.dumps(DEFAULT_SETTINGS))

def deep_merge(base, override):
    """Deep merge two dicts, override takes precedence"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result

# Schluessel, die am 11.08.2026 umbenannt wurden, und wohin.
#
# WARUM UMBENENNEN UND NICHT EINFACH LASSEN
#     Sie hiessen nach dem Programm, das die Leiste gezeichnet hat.
#     waybar ist weg - die Leiste ist Bar.tsx in AGS -, und ein
#     Einstellungsschluessel, der ein nicht mehr installiertes Paket
#     nennt, ist eine Frage, die sich niemand mehr beantworten kann.
#
# WARUM MIT MIGRATION UND NICHT OHNE
#     Es sind Farben, die der Nutzer selbst gewaehlt hat. `set-color`
#     prueft den Schluessel nicht, also faende ein umbenannter Eintrag
#     seinen Weg nirgendwohin und niemand bekaeme es gesagt: der alte
#     Name bliebe in der Datei stehen, unveraendert, ungelesen, und der
#     Schreibtisch waere ueber Nacht wieder in den Vorgabefarben.
#     Dieselbe Begruendung, aus der scaling.height verschoben und nicht
#     geloescht wurde.
#
#     Der Unterschied zu dort: hier ist der Wert nicht in Ruhestand,
#     sondern an einem neuen Ort weiter in Gebrauch. Er wandert also in
#     die Sektion und nicht ins _meta.
#
# ZWEI DER DREIZEHN SIND AM 12.08.2026 HERAUSGEFALLEN
#     waybar_bg -> bar_bg und waybar_workspace_active ->
#     bar_workspace_active. Ihr ZIEL gibt es nicht mehr: beide Farben
#     erreichten keine Vorlage und sind mit ihren Platzhaltern geloescht
#     (src/brand.py, COLOR_GROUPS, fuehrt die Messung). Eine Migration
#     auf einen Namen, den brand.COLORS nicht kennt, waere schlimmer als
#     keine - get_user_color() beantwortet ihn mit einem KeyError, und
#     das blosse Laden der Einstellungen kostete dann jeden erzeugten
#     Byte. Der alte Eintrag bleibt in der Datei des Nutzers stehen, wo
#     er sichtbar ist und nichts anrichtet; er hat auch vorher nichts
#     bewirkt.
# UND ACHT WEITERE AM 12.08.2026, AUS DEMSELBEN GRUND
#     date, weather, network, bluetooth, battery, audio, microphone und
#     workspace. Auch ihr Ziel gibt es nicht mehr: die Module der Leiste
#     tragen im Ruhezustand die Textfarbe, und Farbe bedeutet dort
#     Zustand - die Messung dazu steht im Kopf von
#     src/styles/bar-style.template. Uebrig bleiben die drei, deren Ziel
#     brand.COLORS weiter kennt.
RENAMED_KEYS = {
    "colors": {f"waybar_{part}": f"bar_{part}" for part in (
        "text", "workspace_visible", "tray")},
}

# Und dasselbe fuer die Groessen, deren Name nicht mehr stimmte.
#
# STYLE_MARGIN_TOP -> STYLE_CHIP_GAP stand hier vom 12.08.2026 bis zum
# 19.08.2026: der Abstand zwischen zwei Kacheln der Leiste lag oben,
# solange sie senkrecht lief, und ein Name, der eine Himmelsrichtung
# nennt, ist bei jeder Drehung wieder falsch - STYLE_CHIP_GAP nannte die
# Sache statt der Richtung.
#
# BEIDE NAMEN SIND SEIT DEM 19.08.2026 UNTEN, NICHT MEHR HIER
#     .bar-module (bar-style.template) trug STYLE_CHIP_GAP als
#     margin-left und zaehlte damit denselben Abstand doppelt mit der
#     Polsterung (siehe die Herleitung in src/sizes.py, direkt vor
#     STYLE_PADDING_BUTTON) - behoben durch Umstellung auf
#     STYLE_SPACE_8, die Sprosse der allgemeinen Abstandsleiter statt
#     einer eigenen Groesse. STYLE_CHIP_GAP hat damit keinen Leser mehr
#     und ist mit STYLE_MARGIN_TOP zusammen unten gelandet, aus
#     demselben Grund wie STYLE_WAYBAR_EDGE_SPACING gleich darunter: eine
#     Umbenennung auf einen Namen, den die Tabelle nicht mehr kennt,
#     waere eine Migration, die einen Wert in die Datei schreibt, den
#     niemand mehr liest.
#
# STYLE_WAYBAR_EDGE_SPACING stand hier und zeigte auf
# STYLE_BAR_EDGE_SPACING. Diese Groesse gibt es seit dem 12.08.2026
# nicht mehr - die Module fangen an der Kante der Platte an, siehe
# src/sizes.py -, und eine Umbenennung auf einen Namen, den die Tabelle
# nicht kennt, waere eine Migration, die einen Wert in die Datei
# schreibt, den niemand mehr liest. Der alte Name faellt jetzt unter
# RETIRED_SIZE_VALUES und wird beim Laden weggeraeumt.
RENAMED_SIZE_VALUES: dict[str, str] = {}

# Groessen, die es nicht mehr gibt. Ein Einzelwert dafuer in der Datei
# des Nutzers ist ein Regler ohne Leser - genau das, wogegen
# tests/src/test_sizes.py gebaut ist -, also wird er beim Laden
# entfernt statt bei jedem Speichern mitgeschleppt.
RETIRED_SIZE_VALUES = (
    "STYLE_WAYBAR_EDGE_SPACING",
    "STYLE_BAR_EDGE_SPACING",
    "STYLE_DOCK_MARGIN_BOTTOM",
    # Beide am 19.08.2026: siehe den Absatz "BEIDE NAMEN SIND SEIT DEM
    # 19.08.2026 UNTEN" oben. STYLE_CHIP_GAP steht hier zusaetzlich zu
    # STYLE_MARGIN_TOP, damit auch eine Datei, die die erste Umbenennung
    # (vom 12.08.2026) bereits durchlaufen hat, sauber wird.
    "STYLE_MARGIN_TOP",
    "STYLE_CHIP_GAP",
)


def migrate_renamed_keys(settings):
    """Umbenannte Schluessel auf ihren neuen Namen ziehen.

    Ein bereits vorhandener neuer Name GEWINNT: hat der Nutzer nach der
    Umbenennung schon einmal `set-color --key bar_bg` gesagt, ist das die
    juengere Aussage, und ein alter Eintrag daneben darf sie nicht
    ueberschreiben. Der alte verschwindet trotzdem, sonst bliebe die
    Frage, welcher von beiden gilt, in der Datei stehen.

    Nichts wird hier geschrieben: dieselbe Regel wie in
    migrate_scaling() - das Dokument wird im Speicher veraendert, und auf
    die Platte kommt es beim naechsten save_settings().
    """
    for section, renames in RENAMED_KEYS.items():
        values = settings.get(section)
        if not isinstance(values, dict):
            continue
        for old, new in renames.items():
            if old not in values:
                continue
            value = values.pop(old)
            values.setdefault(new, value)

    section = settings.get(sizes.SECTION)
    values = section.get("values") if isinstance(section, dict) else None
    if isinstance(values, dict):
        for old, new in RENAMED_SIZE_VALUES.items():
            if old in values:
                values.setdefault(new, values.pop(old))
        # Und die, die es nicht mehr gibt. Sie werden geloescht und
        # nicht nach _meta.retired verschoben wie die Skalendimension:
        # dort ging es um eine Zahl, die der Nutzer je Aufloesung
        # GEWAEHLT hatte und die er wiederfinden koennen muss. Hier geht
        # es um einen Abstand, den es nicht mehr gibt, weil ein anderer
        # ihn uebernommen hat - STYLE_GAPS_OUT -, und der steht in der
        # Datei sichtbar daneben.
        for retired in RETIRED_SIZE_VALUES:
            values.pop(retired, None)

    return settings


def migrate_scaling(settings):
    """
    Bring the scaling section to the one shape that is read.

    Old format:  {"1920": 1.0, "2560": 1.2}
    Shape read:  {"1920": {"width": 1.0}, "2560": {"width": 1.2}}

    and the "height" a middle version of this file wrote beside every
    width. That one is not converted, it is RETIRED - moved to
    _meta.retired with the reason beside it, and taken out of the section
    the generator applies.

    Moved rather than deleted, because it is a number the user chose. A
    document that loses a setting has to say where it went, or the person
    who set 1.30 for their 4K screen is left looking for it in a file
    that no longer mentions it. See RETIRED_SCALING_DIMENSION for why it
    is going.

    Nothing is written here: this runs on every load and mutates the
    document in memory. The retirement reaches the disk when something
    saves, which is also the first moment the user could notice it.
    """
    if "scaling" not in settings:
        return settings

    scaling = settings["scaling"]
    if not isinstance(scaling, dict):
        # A hand-edited file may hold anything at all here. Refusing is
        # settings.load()'s job, not this function's; what it must not do
        # is raise on the way past.
        return settings

    migrated = False
    retired = {}

    for res_key, val in list(scaling.items()):
        if not isinstance(val, dict):
            # Old format - one number for the bracket, which was the
            # width scale then and is the width scale now.
            scaling[res_key] = {"width": float(val)}
            migrated = True
        elif RETIRED_SCALING_DIMENSION in val:
            retired[res_key] = val.pop(RETIRED_SCALING_DIMENSION)
            migrated = True

    if retired:
        # setdefault twice over: another retirement may already be
        # recorded, and it is not this one's to overwrite.
        record = settings.setdefault("_meta", {}).setdefault("retired", {})
        entry = record.setdefault(f"scaling.{RETIRED_SCALING_DIMENSION}", {})
        entry["removed"] = datetime.now().isoformat()
        entry["reason"] = RETIRED_SCALING_REASON
        entry.setdefault("values", {}).update(retired)

    if migrated:
        # setdefault, because the document being migrated is a USER's
        # file and need not have a _meta section at all. A hand-written
        # file with old-format scaling and no _meta ended this with a
        # KeyError - a traceback out of every user_settings command, over
        # a file that was otherwise perfectly readable.
        settings.setdefault("_meta", {})["version"] = DEFAULT_SETTINGS["_meta"]["version"]

    return settings

def load_settings(profile_name=None):
    """
    Load GLOBAL settings, merging with defaults.

    A file that is not there is answered with the defaults - that is a
    fresh installation, and it is the normal state. A file that IS there
    and cannot be read raises: every caller of this either shows the
    settings or saves them back, and both of those turn a warning into
    silent data loss. See the header for what the warning-and-carry-on
    version cost.

    Args:
        profile_name: Ignored (kept for backwards compatibility)

    Returns:
        dict: Merged settings (user settings override defaults)

    Raises:
        UnusableSettings: the file exists and cannot be read
    """
    settings_path = get_settings_path()

    user_settings = {}
    if settings_path.exists():
        try:
            user_settings = read_settings_document(settings_path)
        except (ValueError, OSError) as e:
            # The wording belongs to settings.py, which owns the file and
            # the schema, so that the same condition reads the same way
            # whichever command the user happened to run.
            raise UnusableSettings(
                f"{unreadable_message(settings_path, e)}\nNothing was changed."
            ) from e

    # Migrate old scaling format if needed
    user_settings = migrate_scaling(user_settings)
    user_settings = migrate_renamed_keys(user_settings)
    # Merge with defaults (user settings take precedence)
    merged = deep_merge(get_defaults(), user_settings)
    # Always show "Global" since settings are global
    merged.setdefault("_meta", {})["profile"] = "Global"
    return merged

def drop_untouched_colours(settings):
    """Jede Farbe streichen, die genau die ausgelieferte ist.

    DER FEHLER, DEN DAS BEHEBT, UND WIE ER GEMESSEN WURDE
        load_settings() verschmilzt mit DEFAULT_SETTINGS, also traegt
        JEDES geladene Dokument alle siebzig Farben - auch das eines
        Kontos, das nie eine angefasst hat. save_settings() schrieb es
        anschliessend vollstaendig zurueck. GEMESSEN am 12.08.2026:
        `user_settings.py set-weather --location Kiel` auf einer
        frischen Installation hinterlaesst eine Einstellungsdatei mit
        einem "colors"-Abschnitt aus siebzig Eintraegen, obwohl von
        Farben nie die Rede war.

        Bis es Themen gab, war das folgenlos - die siebzig Werte waren
        dieselben, die brand.py ohnehin geliefert haette. Seit dem
        12.08.2026 ist es der Unterschied zwischen einem Themenwechsel,
        der wirkt, und einem, der nichts tut: get_user_color() fragt
        die Einstellungsdatei ZUERST, und siebzig festgeschriebene
        Farben ueberfahren jede Palette. Ein Wetterort haette also
        stillschweigend das Umschalten abgeschaltet.

    WAS DAS KOSTET, UND WARUM ES TROTZDEM RICHTIG IST
        Wer eine Farbe AUSDRUECKLICH auf genau den ausgelieferten Wert
        setzt, verliert diese Aussage - sie folgt danach wieder dem
        Thema. Das ist der einzige Fall, und er ist der richtige:
        "genau die ausgelieferte Farbe" IST die Aussage "keine eigene
        Meinung", und es gibt keinen zweiten Weg, sie zurueckzunehmen.
        Genau darauf verlaesst sich reset_colors() unten, seit es
        diesen Filter gibt.

        Die Farben eines ANDEREN Themas bleiben unangetastet: der
        Vergleich laeuft gegen brand.COLORS, also gegen die
        Auslieferung, und nicht gegen die gerade eingestellte Palette.
        Wer unter "Tageslicht" ein eigenes Gelb setzt, behaelt es auch
        nach dem Zurueckschalten.
    """
    colours = settings.get("colors")
    if not isinstance(colours, dict):
        return settings
    settings["colors"] = {key: value for key, value in colours.items()
                          if brand.COLORS.get(key) != value}
    return settings


def save_settings(profile_name=None, settings=None):
    """
    Save GLOBAL settings.

    Written through settings.merge(), which replaces the sections handed
    to it, keeps every other one, and puts the file in place with a
    rename rather than truncating it - see the header. The sections this
    module does not know about (the installer's plugins.enabled, anything
    a later version adds) survive a save from here because of that, not
    because this function happens to have loaded them first.

    Args:
        profile_name: Ignored (kept for backwards compatibility)
        settings: Settings dict to save

    Raises:
        UnusableSettings: the existing file cannot be read, so what is in
            it cannot be preserved and must not be overwritten
    """
    if settings is None:
        return

    # Was nur gelesen wurde, wird nicht geschrieben. Siehe
    # drop_untouched_colours() darueber - ohne diese Zeile macht der
    # naechste `set-weather` jeden kuenftigen Themenwechsel wirkungslos.
    drop_untouched_colours(settings)

    settings_path = get_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # Update metadata. _meta belongs to this module - it is what
    # `user_settings.py get` reports - so this is the one place that
    # maintains it.
    meta = settings.setdefault("_meta", {})
    meta["profile"] = "Global"
    meta["modified"] = datetime.now().isoformat()
    if not meta.get("created"):
        meta["created"] = meta["modified"]

    try:
        merge_settings_sections(settings, settings_path)
    except (ValueError, OSError) as e:
        # Reached when this function is called directly as a module
        # rather than through the CLI, which loads first and would have
        # refused there. The message has to name the file either way:
        # "unsupported schema_version None" on its own says nothing about
        # which file to repair.
        raise UnusableSettings(
            f"{unreadable_message(settings_path, e)}\nNothing was changed."
        ) from e

    print(f"Settings saved to {settings_path}")

def reset_settings(profile_name=None):
    """
    Reset GLOBAL settings (delete user-settings.json).

    Args:
        profile_name: Ignored (kept for backwards compatibility)
    """
    settings_path = get_settings_path()
    if settings_path.exists():
        settings_path.unlink()
        print(f"Global settings reset: {settings_path}")
    else:
        print("No custom settings found")

def reset_colors(profile_name=None):
    """
    Reset only colors to defaults, keeping other settings.
    Saves to GLOBAL settings.

    Args:
        profile_name: Ignored (kept for backwards compatibility)
    """
    settings = load_settings()
    settings["colors"] = DEFAULT_SETTINGS["colors"].copy()
    save_settings(None, settings)
    print("Colors reset to defaults")

def reset_sizes(profile_name=None):
    """Faktor und Einzelwerte zurueck auf die ausgelieferten.

    Der Abschnitt wird ERSETZT und nicht mit den Vorgaben verschmolzen.
    Bei `values` ist das der ganze Unterschied: ein Verschmelzen liesse
    jede einzeln gesetzte Groesse stehen, weil die Vorgabe dort ein
    leeres Objekt ist und ein leeres Objekt nichts ueberschreibt - und
    ausgerechnet die Einzelwerte sind das, was jemand loswerden will,
    der "zuruecksetzen" tippt, nachdem er sich verstellt hat.
    """
    settings = load_settings()
    settings[sizes.SECTION] = sizes.defaults()
    save_settings(None, settings)
    print("Sizes reset to defaults")


def set_size_scale(scale, profile_name=None):
    """Den einen Faktor setzen.

    Args:
        scale: Faktor > 0. 1.0 ist die Groesse vor dem 11.08.2026,
            sizes.SCALE_DEFAULT die des Startmenues.

    Raises:
        ValueError: bei einem Faktor, der keine positive Zahl ist. Die
            Erzeugung faengt so etwas zwar ab und faellt auf die Vorgabe
            zurueck, aber sie tut es STILL - der Nutzer haette einen
            Befehl abgesetzt, eine Bestaetigung gelesen und keine
            Aenderung gesehen. Abgelehnt wird deshalb hier, wo noch
            jemand zuschaut.
    """
    value = float(scale)
    if value <= 0:
        raise ValueError(
            f"a size factor has to be greater than zero, not {scale}. "
            f"A factor of zero or less is a desktop with nothing legible "
            f"on it, and the way back leads through that desktop."
        )

    settings = load_settings()
    settings.setdefault(sizes.SECTION, {})["scale"] = value
    save_settings(None, settings)


def set_size(name, value, profile_name=None):
    """Eine einzelne Groesse setzen, am Faktor vorbei.

    Args:
        name: Platzhaltername aus sizes.TABLE, z.B. STYLE_FONT_SIZE
        value: Was in der erzeugten Datei stehen soll, z.B. "20px"

    Raises:
        KeyError: bei einem Namen, den die Tabelle nicht kennt.

            Abgelehnt und nicht angelegt, aus demselben Grund, aus dem
            cli._set() einen unbekannten Pfad ablehnt: ein vertippter
            Name, der gespeichert und von niemandem gelesen wird, ist
            das leiseste Versagen dieses Programms. Der Nutzer hat eine
            Einstellung geaendert, der Befehl hat "gespeichert" gesagt,
            und an der Maschine hat sich nichts geaendert.
    """
    if name not in sizes.TABLE:
        raise KeyError(
            f"{name} is not a size this system has. Run "
            f"`user_settings.py list-sizes` for the ones it does."
        )

    settings = load_settings()
    section = settings.setdefault(sizes.SECTION, {})
    values = section.setdefault("values", {})
    if not isinstance(values, dict):
        # Ein von Hand editiertes Dokument darf hier alles stehen haben.
        # Ueberschrieben statt weiterbenutzt: .setdefault() auf einer
        # Liste ist ein AttributeError mitten in einem Befehl, der die
        # Datei bereits geladen hat.
        values = {}
        section["values"] = values
    values[name] = value
    save_settings(None, settings)


def clear_size(name, profile_name=None):
    """Eine einzelne Groesse wieder dem Faktor ueberlassen.

    Ohne das waere `set-size` eine Einbahnstrasse: der einzige Weg
    zurueck fuehrte durch das Editieren der JSON-Datei von Hand, also
    genau durch das, wofuer es diese Befehle gibt. Einen Namen auf
    seinen Grundwert zu SETZEN ist nicht dasselbe - er stuende dann
    fest und wuerde dem Faktor nicht mehr folgen.
    """
    if name not in sizes.TABLE:
        raise KeyError(
            f"{name} is not a size this system has. Run "
            f"`user_settings.py list-sizes` for the ones it does."
        )

    settings = load_settings()
    values = settings.get(sizes.SECTION, {}).get("values")
    if isinstance(values, dict):
        values.pop(name, None)
    save_settings(None, settings)


def get_scale(width, profile_name=None):
    """
    Get the scaling factor for a specific screen width.

    One factor per bracket. The get_width_scale/get_height_scale pair
    that used to wrap this went with the height itself - see
    RETIRED_SCALING_DIMENSION.

    Args:
        width: Screen width (e.g., 1920, 2560, 3440, 3840)
        profile_name: Profile name, or None for current

    Returns:
        float: Scaling factor
    """
    settings = load_settings(profile_name)
    scales = settings.get("scaling", {})
    scale_entry = scales.get(str(width), {"width": 1.0})

    # Handle both old (single value) and new (dict) formats
    if isinstance(scale_entry, dict):
        return float(scale_entry.get("width", 1.0))
    else:
        return float(scale_entry)

def get_color(key, profile_name=None, default=None):
    """
    Get a color value from settings.

    Args:
        key: Color key (e.g., "success", "warning")
        profile_name: Profile name, or None for current
        default: Default value if not found

    Returns:
        str: Color value (hex)
    """
    settings = load_settings(profile_name)
    colors = settings.get("colors", {})
    if default is None:
        # brand.COLORS, not a literal. This used to fall back to
        # "#ffffff" for a key it did not know - white, which is a colour
        # ZepOS does not use anywhere, so an unknown key produced a
        # value that looked deliberate and belonged to nothing.
        default = brand.COLORS.get(key)
    return colors.get(key, default)

def get_vpn_setting(key, default=None):
    """
    Get a VPN setting value using dot notation for nested keys.

    Args:
        key: Setting key with dot notation (e.g., "server", "phase1.version", "dns.servers")
        default: Default value if not found

    Returns:
        The setting value or default
    """
    settings = load_settings()
    # Die GEWAEHLTE Verbindung, seit dem 22.08.2026 - dieselbe Auskunft,
    # die auch der Erzeuger bekommt (src/style_definition.py). Ueber
    # vpn.connection() und nicht selbst herausgegriffen: zwei Leser der
    # Frage "welche Verbindung?" waeren zwei Gelegenheiten, sie
    # verschieden zu beantworten.
    vpn_settings = _vpn_connection(settings)

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
        # Try to get default from DEFAULT_SETTINGS
        if default is None:
            # Auf DEFAULT_CONNECTION und nicht auf
            # DEFAULT_SETTINGS["vpn"]: dort steht seit dem 22.08.2026
            # die leere Liste, und ein Rueckfall darauf haette fuer
            # JEDEN Schluessel None ergeben.
            default_value = DEFAULT_CONNECTION
            for k in keys:
                if isinstance(default_value, dict):
                    default_value = default_value.get(k)
                else:
                    default_value = None
                    break
            return default_value
        return default

    return value

def get_weather_setting(key, default=""):
    """
    Get a weather setting value.

    Args:
        key: Setting key (e.g., "location")
        default: Value if the setting is absent

    Returns:
        The setting value, or the default
    """
    settings = load_settings()
    value = settings.get("weather", {}).get(key)
    if value is None:
        return DEFAULT_SETTINGS.get("weather", {}).get(key, default)
    return value

def set_weather_location(location):
    """
    Set the location the weather module asks about.

    An empty string switches the module off again, which is the state a
    fresh installation is in - and the only state in which nothing about
    this machine reaches wttr.in.

    Args:
        location: Place name, postcode, airport code, or "" for none
    """
    settings = load_settings()
    settings.setdefault("weather", {})["location"] = location.strip()
    save_settings(None, settings)

# interpolate_scale() stood here: the same interpolation
# style_definition.calculate_width_scale() does, over `float(s)` where s
# is a bracket. A bracket has been an object since the migration above,
# so this raised TypeError on any document written in the last two
# formats - and it raised it nowhere, because nothing called it.

# get_widget_size(), set_widget_size() und get_all_widget_sizes() standen
# hier und lasen/schrieben settings["widget_sizes"] - die Kette, die
# die Notiz bei DEFAULT_SETTINGS oben (und die bei
# style_definition._monitor_style_variables()) als ohne Leser ausweist.
# get_all_widget_sizes() hatte ohnehin keinen Aufrufer ausser sich
# selbst - GEMESSEN am 18.08.2026, `grep -rn` gegen den ganzen Baum.
# Alle drei fallen mit dem Reiter, der sie fuellte.

# =============================================================================
# CLI INTERFACE
# =============================================================================

def cmd_get(args):
    """Get current GLOBAL settings as JSON"""
    settings = load_settings()
    print(json.dumps(settings, indent=2 if args.pretty else None))

def cmd_save(args):
    """Save scaling settings to GLOBAL settings"""
    settings = load_settings()

    # Written in the shape the section is READ in. This wrote a bare
    # number - the format migrate_scaling() exists to convert away from -
    # so `save --scale-2560 1.3` put the document back into the old shape
    # on every use, and the next load quietly migrated it again.
    scales = {"1920": args.scale_1920, "2560": args.scale_2560,
              "3440": args.scale_3440, "3840": args.scale_3840}
    for bracket, value in scales.items():
        if value is not None:
            settings.setdefault("scaling", {})[bracket] = {"width": float(value)}

    save_settings(None, settings)

def cmd_set_color(args):
    """Set a single color value in GLOBAL settings"""
    settings = load_settings()

    if "colors" not in settings:
        settings["colors"] = {}

    settings["colors"][args.key] = args.value
    save_settings(None, settings)

def cmd_set_weather_location(args):
    """Set the weather location in GLOBAL settings"""
    set_weather_location(args.value)
    if args.value.strip():
        print(f"Weather location set to {args.value.strip()}")
        print("Note: the module sends this location to wttr.in on every refresh.")
    else:
        print("Weather location cleared - the module stays empty and asks nobody.")
    print("Run: generate_config.sh -waybar-weather-config")

def cmd_set_size(args):
    """Set the size factor, or one single size, in GLOBAL settings.

    Der Faktor und ein Einzelwert sind EIN Unterbefehl mit zwei
    Argumenten und nicht zwei Unterbefehle, weil sie zusammen die
    Antwort auf eine Frage sind: --scale bewegt die ganze Leiter,
    --key/--value nimmt eine Sprosse davon aus. Wer `set-size --help`
    liest, soll beide sehen.
    """
    if args.scale is None and args.key is None:
        raise ValueError(
            "nothing to set: give --scale, or --key with --value.\n"
            "  --scale moves every size that carries text;\n"
            "  --key with --value sets one of them exactly, and\n"
            "  --key with --clear hands it back to --scale."
        )

    if args.scale is not None:
        set_size_scale(args.scale)
        print(f"Size factor set to {float(args.scale):.4g} "
              f"(shipped: {sizes.SCALE_DEFAULT:.4g}, "
              f"before 11.08.2026: 1)")

    if args.key is not None:
        if args.clear:
            clear_size(args.key)
            print(f"{args.key} follows the size factor again")
        elif args.value is None:
            raise ValueError(
                f"--key {args.key} needs either --value or --clear")
        else:
            set_size(args.key, args.value)
            print(f"{args.key} set to {args.value} "
                  f"(the size factor no longer applies to it)")

    print("Run: generate_config.sh --all")


def cmd_list_sizes(args):
    """Every size that can be set, with what it comes to right now.

    Der Antwortteil auf "voll anpassbar, aber keine 365 Knoepfe": es
    gibt EINEN Regler und eine Liste. Die Liste muss auffindbar sein,
    sonst ist der Ausnahmeweg einer, den nur findet, wer die Quelle
    liest - genau der Zustand, in dem die Farben vor dem Stil-Editor
    waren.

    Der aktuelle Wert steht daneben und nicht nur der Grundwert. Ohne
    ihn muesste der Nutzer den Faktor im Kopf multiplizieren, um zu
    sehen, was auf seinem Schirm steht.
    """
    settings = load_settings()
    section = sizes.settings_section(settings)
    scale = sizes.scale_of(section)

    print(f"size factor: {scale:.4g}")
    print()
    print(f"{'name':<32} {'base':>6} {'now':>8}  follows the factor")
    for name in sorted(sizes.TABLE):
        size = sizes.TABLE[name]
        current = sizes.value_of(name, section)
        if sizes.override_of(section, name) is not None:
            follows = "no - set by hand"
        else:
            follows = "yes" if size.scales else "no - a picture"
        print(f"{name:<32} {str(size.base) + size.unit:>6} "
              f"{current:>8}  {follows}")


def cmd_reset(args):
    """Reset GLOBAL settings to defaults"""
    # Handle scoped resets
    if args.scope == "colors":
        reset_colors()
    elif args.scope == "sizes":
        reset_sizes()
    else:
        # Full reset
        reset_settings()

def cmd_list_profiles(args):
    """List all profiles with settings status"""
    profiles_dir = get_profiles_dir()
    if not profiles_dir.exists():
        print("No profiles directory found")
        return

    current = get_current_profile()

    for profile_dir in sorted(profiles_dir.iterdir()):
        if profile_dir.is_dir():
            name = profile_dir.name
            settings_file = profile_dir / "user-settings.json"
            has_settings = settings_file.exists()
            marker = "*" if name == current else " "
            status = "[custom]" if has_settings else "[default]"
            print(f"{marker} {name} {status}")

def main():
    parser = argparse.ArgumentParser(
        description="User Settings Manager for ZepOS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s get --profile laptop
  %(prog)s save --profile laptop --scale-2560 1.25
  %(prog)s set-color --profile laptop --key success --value "#00ff00"
  %(prog)s set-size --scale 1.5
  %(prog)s set-size --key STYLE_BAR_THICKNESS --value 70
  %(prog)s set-size --key STYLE_BAR_THICKNESS --clear
  %(prog)s list-sizes
  %(prog)s set-weather-location --value "Berlin"
  %(prog)s reset --profile laptop
  %(prog)s list
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # get command
    get_parser = subparsers.add_parser("get", help="Get current settings as JSON")
    get_parser.add_argument("--profile", "-p", help="Profile name (default: current)")
    get_parser.add_argument("--pretty", action="store_true", help="Pretty print JSON")
    get_parser.set_defaults(func=cmd_get)

    # save command
    save_parser = subparsers.add_parser("save", help="Save scaling settings")
    save_parser.add_argument("--profile", "-p", help="Profile name (default: current)")
    save_parser.add_argument("--scale-1920", type=float, help="Scale for 1920px width")
    save_parser.add_argument("--scale-2560", type=float, help="Scale for 2560px width")
    save_parser.add_argument("--scale-3440", type=float, help="Scale for 3440px width")
    save_parser.add_argument("--scale-3840", type=float, help="Scale for 3840px width")
    save_parser.set_defaults(func=cmd_save)

    # set-color command
    color_parser = subparsers.add_parser("set-color", help="Set a color value")
    color_parser.add_argument("--profile", "-p", help="Profile name (default: current)")
    color_parser.add_argument("--key", "-k", required=True, help="Color key (e.g., success, warning)")
    color_parser.add_argument("--value", "-v", required=True, help="Color value (hex)")
    color_parser.set_defaults(func=cmd_set_color)

    # set-weather-location command
    #
    # The location has to be settable without hand-editing JSON, or the
    # weather module is a feature only its author can switch on. An empty
    # value is explicitly allowed: that is how it gets switched off again.
    weather_parser = subparsers.add_parser(
        "set-weather-location",
        help="Set the location the weather module asks wttr.in about")
    weather_parser.add_argument(
        "--value", "-v", required=True,
        help='Place name, postcode or airport code; "" switches the module off')
    weather_parser.set_defaults(func=cmd_set_weather_location)

    # reset command
    reset_parser = subparsers.add_parser("reset", help="Reset settings to defaults")
    reset_parser.add_argument("--profile", "-p", help="Profile name (default: current)")
    reset_parser.add_argument("--scope", "-s",
                              choices=["all", "colors", "sizes"],
                              default="all",
                              help="What to reset: all, colors, or sizes")
    reset_parser.set_defaults(func=cmd_reset)

    # set-widget-size stand hier. Es rief set_widget_size() auf, das mit
    # der ganzen widget_sizes-Kette am 18.08.2026 gefallen ist - siehe
    # die Notiz bei DEFAULT_SETTINGS oben. Ein Unterbefehl, der eine
    # Einstellung ohne Wirkung anbietet, ist dieselbe Luege eine Ebene
    # tiefer, also faellt er mit.

    # set-size command
    #
    # Dasselbe Muster wie set-color, und das ist die Vorgabe des
    # Nutzers gewesen: "so einstellbar werden, wie es die Farben schon
    # sind". Eine Groesse pro Aufruf, benannt, gegen eine Tabelle
    # geprueft - und daneben der eine Faktor, den die Farben nicht
    # brauchen, weil Farben keine gemeinsame Achse haben und Groessen
    # eine haben.
    size_parser = subparsers.add_parser(
        "set-size",
        help="Set the size factor, or one single size")
    size_parser.add_argument("--profile", "-p", help="Profile name (default: current)")
    size_parser.add_argument(
        "--scale", type=float,
        help="Factor on every size that carries text (1 = as before "
             f"11.08.2026, {sizes.SCALE_DEFAULT:.4g} = the boot menu's)")
    size_parser.add_argument(
        "--key", "-k",
        help="One size by name; see `list-sizes`")
    size_parser.add_argument(
        "--value", "-v",
        help="What that size should be, e.g. 20px. The factor no longer "
             "applies to it")
    size_parser.add_argument(
        "--clear", action="store_true",
        help="Hand --key back to the factor")
    size_parser.set_defaults(func=cmd_set_size)

    # list-sizes command
    sizes_parser = subparsers.add_parser(
        "list-sizes",
        help="Every size that can be set, and what it comes to now")
    sizes_parser.set_defaults(func=cmd_list_sizes)

    # list command
    list_parser = subparsers.add_parser("list", help="List profiles with settings status")
    list_parser.set_defaults(func=cmd_list_profiles)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except UnusableSettings as exc:
        # The message already names the file and the repair. A traceback
        # here would name a line of this program instead, over a mistake
        # that is in the user's file.
        print(exc, file=sys.stderr)
        sys.exit(1)
    except (KeyError, ValueError) as exc:
        # Ein unbekannter Groessenname und ein Faktor, der keine Zahl
        # ist. Beides sind Tippfehler auf der Befehlszeile, und beide
        # nannten bis hierher eine Zeile DIESES Programms statt des
        # Wortes, das der Nutzer falsch geschrieben hat. KeyError druckt
        # seine Nachricht ausserdem mit Anfuehrungszeichen darum, was
        # aus einem Satz ein Zitat macht - daher args[0] statt str().
        print(exc.args[0] if exc.args else exc, file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
