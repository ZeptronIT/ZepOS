# SPDX-License-Identifier: GPL-3.0-or-later
"""User settings, versioned from the first release.

Without a version field the first migration would have to guess what
structure a file on someone else's machine has. The field costs one line
now and cannot be added retroactively.

THE ONE READER AND THE ONE WRITER
    <user root>/user-settings.json had four writers, each with its own
    guarantees: this module's atomic 0600 replace, user_settings.py's
    `open(path, 'w')` (which truncates the file to zero bytes while it is
    held and creates it at 0644), and one in each of the two AGS dialogs,
    which read the document in a `catch {}`, fell back to an empty object
    and wrote their own section over the lot. Whichever ran first on a
    fresh machine decided the permissions; whichever ran over a document
    it could not parse decided that the rest of it no longer existed.

    They all go through save() and merge() now. The two dialogs are GJS
    and cannot import this module, so they CALL it - see main() at the
    bottom, which exists for exactly that and does nothing the functions
    above do not.

    The same holds for reading. load() decides what "cannot be read"
    means - not valid JSON, not an object, not this schema version - and
    every reader, including the style layer the generator builds every
    config from, gets the same answer to that question or none of them
    can be relied on to have got it.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

# This module is loaded two ways, and both have to work.
#
#   * as `src.settings`, from the test suite, which puts the repository
#     root on the path - `src` is then a package and the relative import
#     is the correct one.
#   * as `settings`, from /usr/share/zepos, where every module sits flat
#     beside every other and there is no package at all. A relative
#     import raises ImportError there ("attempted relative import with no
#     known parent package"), which is what made this module the one
#     thing in src/ that could not be used by an installed command.
#
# Relative first, so the choice is decided by how this module was loaded
# and never by whether some earlier import happened to leave a top-level
# `paths` on the path - that would silently give the two loaders two
# different copies of it.
try:
    from . import desktop_entries, sizes
    from .paths import system_root, user_root
except ImportError:
    import desktop_entries
    import sizes
    from paths import system_root, user_root

SCHEMA_VERSION = 1
FILENAME = "user-settings.json"


class UnusableSettings(ValueError):
    """The settings file exists and cannot be used.

    A file that is not there and a file that cannot be read are two
    different states, and only the first one is normal: a fresh
    installation has no settings file at all, and every reader is
    expected to answer from its own defaults for it.

    The second state used to be indistinguishable from the first. The
    style layer read the file in a bare `except: pass` and returned {},
    so a truncated document produced a complete, syntactically perfect
    configuration built from defaults - published over the working one,
    with `✓ Config successfully generated` on the terminal. This
    exception is what the readers raise instead, so that the one thing
    every caller must not do - carry on as if the user had configured
    nothing - takes a deliberate `except` to reach.

    A ValueError, because that is what json and the version check already
    raise and what every existing handler catches.
    """


def defaults() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "vpn": {
            # Welche Bauart. "ipsec" (strongSwan) oder "wireguard"
            # (NetworkManager). Die Vorgabe ist "ipsec" und darf nie
            # geraten werden - siehe src/vpn.py::vpn_kind().
            "kind": "ipsec",
            "server": "",
            "connection_name": "work",
            "dns": {"servers": [], "search_domain": ""},
            "test_host": "",
            "routed_networks": [],
            # Networks that must stay OUTSIDE the tunnel even though a
            # routed network covers them - a parallel WireGuard link to a
            # home LAN inside 192.168.0.0/16, say. Without a passthrough
            # policy IPsec captures that traffic and the other tunnel
            # goes dark. The origin had its own home subnet, and the
            # German interface name it used, written into the script.
            "bypass_networks": [],
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
        },
        "weather": {"location": ""},
        # Extra clocks beside the local time, by IANA timezone name. The
        # origin had two templates with one country each written into
        # them - a timezone, a flag and a locale apiece - so every user
        # carried one person's two homes on their bar and nobody could
        # have a third. Empty by default for the same reason the weather
        # location is: a feature nobody asked for must not arrive
        # switched on. An entry is a name, or a name with a label of the
        # user's own choosing:
        #
        #   ["Europe/Lisbon", {"zone": "Asia/Tokyo", "label": "🇯🇵"}]
        #
        # The label is theirs to write because it cannot be derived - see
        # src/clocks.py for why a timezone does not give a country.
        # `format` is a date(1) format string and applies to all of them.
        "clocks": {"format": "%H:%M", "zones": []},
        # Audio devices, by the node name PipeWire knows them under -
        # the second column of `pactl list short sources`. Every one of
        # them is blank on purpose: the origin wrote four of its own
        # devices into the two audio templates by USB product string,
        # USB id and Bluetooth address, and a node name belongs to one
        # machine's hardware. Blank means "let PipeWire decide", which
        # is a working desktop; a name that is not there is a rule that
        # silently never fires. See src/audio.py, and `audio.py --check`
        # for whether the names still match anything attached.
        "audio": {
            "default_sink": "",
            "default_source": "",
            # Sources that must never be picked up automatically - a
            # headset microphone that is not the one being spoken into,
            # a webcam's microphone.
            "blocked_sources": [],
            # The real microphone EasyEffects takes its input from. Not
            # the same as default_source: where the effects chain is the
            # default, default_source is the VIRTUAL node EasyEffects
            # publishes and this is the hardware behind it.
            "effects_input": "",
        },
        # Wie gross der Schreibtisch ist. `scale` ist der eine Regler,
        # `values` die Ausnahmen davon, benannt nach dem Platzhalter, den
        # sie setzen. Die Tabelle der einstellbaren Namen und die
        # Begruendung des Vorgabefaktors stehen in src/sizes.py; hier
        # stehen die zwei Schluessel, weil `zepos-settings set` einen Weg
        # ablehnt, den weder die Datei noch dieses Schema kennt - und
        # `zepos-settings set sizes.scale 1.0` ist der Befehl, mit dem
        # jemand die Vergroesserung wieder abstellt.
        "sizes": sizes.defaults(),
        # Was auf der Leiste steht, in welcher Reihenfolge, und was im
        # Dock angeheftet ist.
        #
        # GEMELDET am 12.08.2026: "im footer war ein einstellungs icon
        # was man nicht oeffnen konnte genau sowas will ich im ZepOS zu
        # customizen wenn du verstehst". Bis dahin gab es dafuer keine
        # Einstellung, und zwar an keiner Stelle - GEMESSEN am selben
        # Tag: die zwoelf Namen rechts standen in src/style_definition.py
        # (_modules_right), die fuenf links in
        # src/templates/ags-bar.template (MODULES_LEFT) und damit in
        # einer Vorlage, die gar keine Einstellung lesen kann; die
        # Anheftungen kommen ueber src/apps.py aus dem depends-Array von
        # packaging/zepos-apps/PKGBUILD, und `grep -c '"bar"'` ueber
        # diese Datei antwortete 0.
        #
        # Beide Modullisten stehen seit demselben Tag in
        # src/style_definition.py (_modules_left, _modules_right); die
        # Vorlage traegt nur noch die zwei Platzhalter. Der Umzug war
        # die Bedingung dafuer, dass diese Einstellung ueberhaupt beide
        # Haelften erreicht.
        #
        # WARUM None UND NICHT DIE AUSGELIEFERTE LISTE ALS VORGABE
        #     Eine hier abgeschriebene Liste veraltet in dem Augenblick,
        #     in dem jemand ein Modul umbenennt oder eines dazukommt: der
        #     Nutzer traegt dann eine Liste mit sich herum, die auf einen
        #     Zweig zeigt, den es nicht mehr gibt, und die das neue Modul
        #     nie erwaehnt. Dieses Projekt hat genau diese Kopie schon
        #     dreimal bezahlt - drei Kopien der Vorgabefarben, `warning`
        #     an zweien #f9e2af und an der dritten #fab387; der Kopf von
        #     src/brand.py erzaehlt es.
        #
        #     Also: None heisst "wie ausgeliefert" und traegt keine
        #     Namen. Es gibt weiter EINE ausgelieferte Liste, und sie
        #     bleibt, wo sie ist. Eine Liste hier ERSETZT sie
        #     vollstaendig - auch die leere, die "auf dieser Seite steht
        #     nichts" bedeutet und nicht "wie ausgeliefert".
        #
        # Die Namen sind die der Leiste ("custom/date",
        # "hyprland/workspaces") und die der Anheftungen
        # ("firefox", "zepos-settings"), also genau das, was
        # shipped_bar() unten aufzaehlt. Ein Name, den es dort nicht
        # gibt, wird beim Lesen verworfen UND gemeldet - siehe
        # bar_order().
        "bar": {
            "modules_left": None,
            "modules_right": None,
            "dock_pins": None,
            # KEINE vierte Haelfte, sondern die Vorgabe, gegen die
            # "dock_pins" gesetzt wurde - deshalb steht sie NICHT in
            # BAR_KEYS und wird von der Oberflaeche nicht als
            # Reihenfolge angeboten. Die ganze Begruendung steht bei
            # BAR_BASELINE weiter unten. null heisst hier unbekannt und
            # nicht leer, und das ist auch der Zustand jeder
            # Installation von vor dem 20.08.2026.
            "dock_baseline": None,
        },
        # Das Home: die Programmsymbole auf der Flaeche hinter allen
        # Fenstern. Seit dem 20.08.2026 (Aufgabe 52).
        #
        # EIN EIGENER ABSCHNITT UND KEINE VIERTE LEISTENHAELFTE
        #     Der Kopf bei BAR_BASELINE begruendet ausdruecklich, warum
        #     "dock_pins" eine Liste von NAMEN bleibt: die Gleichform der
        #     drei Haelften ist es, die bar_choice(), bar_order(), das
        #     Bruecken-Bedienelement `reihenfolge` und die Seite "Leiste"
        #     mit EINEM Zweig auskommen laesst, und "ein Objekt an genau
        #     einer der drei haette an jeder dieser Stellen einen
        #     Sonderweg erzwungen".
        #
        #     Das Home BRAUCHT Objekte: das Dock ist eine Reihe, das Home
        #     eine FLAECHE, und wo etwas liegt, ist keine Reihenfolge.
        #     Es in "bar" hineinzuschreiben hiesse, genau die Gleichform
        #     zu brechen, die jener Absatz verteidigt. Also ein eigener
        #     Abschnitt - und ausdruecklich DIESELBEN REGELN, siehe
        #     home_effective() unten, das dock_effective() nachbaut.
        #
        # null heisst auch hier "wie ausgeliefert" und nicht "leer".
        "home": {
            "icons": None,
            # Wortgleich dasselbe wie bar.dock_baseline und aus
            # demselben Grund: ohne sie friert das Home fuer jeden, der
            # EINMAL ein Symbol abgenommen hat, auf jenen Tag ein.
            "baseline": None,
        },
        "watchdog": {
            "interval_seconds": 60,
            "test_host": "1.1.1.1",
            # Empty means "work it out from the default route". The
            # origin wrote its own virtual machine's gateway, interface
            # and address in, so on any other machine the watchdog
            # reported an unreachable gateway forever and never acted.
            "gateway": "",
            "interface": "",
        },
    }


def _path(path: Path | None) -> Path:
    return path if path is not None else user_root() / FILENAME


# What the user wrote, in the vocabulary they wrote it in. Python's own
# type names leak into the message otherwise - "a JSON NoneType" and "a
# JSON str" name nothing that appears in a JSON file, and the person
# reading this is looking at their settings file, not at a traceback.
JSON_TYPES = {
    list: "array", type(None): "null", bool: "boolean",
    int: "number", float: "number", str: "string",
}


def _json_type(value: Any) -> str:
    return JSON_TYPES.get(type(value), type(value).__name__)


def load(path: Path | None = None) -> dict[str, Any]:
    target = _path(path)
    if not target.is_file():
        return defaults()

    data = json.loads(target.read_text(encoding="utf-8"))
    # json.loads answers a list, None, an int or a str just as happily as
    # a dict, and .get() exists on none of them. The AttributeError that
    # produced is neither ValueError nor OSError, so every handler
    # written for "this file cannot be read" - cli.py's and doctor.py's
    # both - missed it, and a settings file holding `[]`, `null`, `5` or
    # `"text"` answered zepos-settings AND zepos-doctor with a raw
    # traceback. The doctor is the command a user reaches for when the
    # configuration is broken; it is the one that must not do that.
    if not isinstance(data, dict):
        raise UnusableSettings(
            f"the settings are a JSON {_json_type(data)}, not an object"
        )

    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        raise UnusableSettings(
            f"unsupported schema_version {version}, expected {SCHEMA_VERSION}"
        )
    return data


def save(data: dict[str, Any], path: Path | None = None) -> None:
    target = _path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Written to a fresh file and moved into place, rather than opened and
    # truncated in place. The file may hold a VPN pre-shared key, so it
    # must never be more than 0o600 at any instant - not "shortly after".
    #
    # A first version of this tightened `target`'s permissions with
    # chmod() before writing, which closes every SEQUENTIAL ordering (a
    # pre-existing file left over from an older version, or created by
    # something else) but not a CONCURRENT one: another process can still
    # replace `target` between that chmod and the write, and the new
    # content lands at whatever mode the replacement used. Measured
    # directly, by making a stand-in for the write itself recreate the
    # file at 0o644 on entry - the new content landed at 0o644, tightened
    # only by the trailing chmod.
    #
    # O_EXCL means we own the file we create: no other process can hand
    # us one at a looser mode, because if the temporary name already
    # exists - as a file OR as a symlink pointed elsewhere - opening it
    # fails outright instead of writing through it. os.replace() is
    # atomic on the same filesystem, so a concurrent reader sees either
    # the old file or the fully-written new one, never a half-written one
    # and never new content sitting at the old file's permissions.
    # Narrowing the umask around a write only ever helped the
    # file-does-not-exist case - a settings file is normally being
    # rewritten, not created, which is exactly the case that approach
    # could not cover.
    #
    # A unique name, not a fixed one. O_EXCL guarantees we own the file we
    # create - but with a fixed name, a temporary file left behind by a
    # killed process (power loss, an OOM kill, a closed lid at the wrong
    # moment) blocks every later save with FileExistsError, permanently,
    # naming a dotfile the user has no reason to know about. A unique
    # name means a crashed run leaves litter rather than a lock, and two
    # concurrent saves no longer collide on the same path either - the
    # loser's content is simply overwritten by the winner's os.replace(),
    # which is the correct behaviour for a settings file one person edits
    # at a time. mkstemp() creates at 0600, which is what we want anyway.
    fd, temporary_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".new"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(data, indent=2) + "\n")
        os.replace(temporary, target)
    except BaseException:
        # BaseException, not Exception: this project's isolation guard
        # raises a BaseException subclass on purpose, so that an
        # `except Exception` handler in production code cannot swallow
        # it. A cleanup path that only caught Exception would leave the
        # temporary file behind on exactly the runs where a test is
        # telling us something is wrong.
        temporary.unlink(missing_ok=True)
        raise


def merge(sections: dict[str, Any], path: Path | None = None) -> None:
    """Replace whole top-level sections and keep everything else.

    The read-modify-write every PARTIAL writer goes through - the two AGS
    dialogs and the style settings manager, each of which owns one or
    three sections of a document that holds five or six.

    Each of them used to do this for itself, and each of them did it
    differently. Both dialogs read the file inside a `catch {}` that fell
    back to an empty object and then wrote that object back with their
    own section added, so a dialog that could not parse the file replaced
    the WHOLE document with the one section it knows about: every colour,
    every widget size, the weather location and the VPN gone, from
    pressing "save" in a dialog about something else. Neither wrote
    schema_version, so a file first created by one of them made every
    versioned reader - zepos-settings among them - refuse it.

    Refusing here is the whole point of routing them through one
    function: load() raises on a document that cannot be read, nothing is
    written, and the file the user still has is the one that can be
    repaired. A writer that cannot parse a document has no business
    deciding what the rest of it should be.

    Sections are REPLACED, not deep-merged. The style editor's "reset
    colours" sends an empty colours section and means it; a deep merge
    would read that as "change nothing" and the button would silently do
    nothing at all.
    """
    document = load(path)
    document.update(sections)
    save(document, path)


# --------------------------------------------------------------------
# Die Leiste: eine ausgelieferte Liste, und was der Nutzer daran aendert
# --------------------------------------------------------------------
#
# DIE AUFTEILUNG, UND WARUM SIE HIER STEHT UND NICHT IM ERZEUGER
#     Zwei Programme stellen dieselbe Frage - "was steht auf der Leiste
#     dieses Nutzers?" -, und sie duerfen sie nicht verschieden
#     beantworten:
#
#       der Erzeuger        setzt die Namen in ags-bar.template ein
#       die Einstellungen   zeigen sie und lassen sie umsortieren
#
#     Beantwortet wird sie deshalb einmal, hier, neben dem Abschnitt,
#     um den es geht. Die Einstellungs-Anwendung importiert den Erzeuger
#     NICHT: src/style_definition.py fragt beim Import `hyprctl` nach den
#     Bildschirmen, und ein Einstellungsfenster, das dafuer den
#     Compositor anspricht, ist ein Fenster, das auf einer Maschine ohne
#     Hyprland nicht mehr aufgeht.
#
# DER ABDRUCK, UND WARUM ER DERSELBE KNIFF IST WIE BEI DEN ANWENDUNGEN
#     Getippt wird die ausgelieferte Auswahl an genau einer Stelle je
#     Haelfte: die beiden Modullisten in src/style_definition.py
#     (_modules_left und _modules_right), die Anheftungen im
#     depends-Array von packaging/zepos-apps/PKGBUILD. Wer sie LESEN will,
#     ohne den Erzeuger zu importieren, braucht einen Abdruck - genau
#     wie /usr/share/zepos/shipped-applications einer ist, den
#     package() aus "${depends[@]}" schreibt (siehe den Kopf von
#     src/apps.py).
#
#     Hier heisst er shipped-bar.json und traegt beide Haelften:
#
#       {"modules_left": [...], "modules_right": [...],
#        "dock_pins": [{"name": ..., "desktop": ..., "label": ...}, ...]}
#
#     Er kann fehlen - ein frischer Checkout ohne Erzeugungslauf, ein
#     Paket, das aelter ist als diese Zeilen. Dann ist die ausgelieferte
#     Reihenfolge UNBEKANNT, und das ist etwas anderes als LEER: gegen
#     eine leere Liste geprueft waere jeder gespeicherte Name unbekannt
#     und wuerde verworfen, und der Nutzer verlaere seine Leiste an einen
#     fehlenden Abdruck. shipped_bar() antwortet deshalb None und nicht
#     {}, und bar_order() verwirft gegen None nichts.

BAR = "bar"
BAR_LEFT = "modules_left"
BAR_RIGHT = "modules_right"
BAR_PINS = "dock_pins"
BAR_KEYS = (BAR_LEFT, BAR_RIGHT, BAR_PINS)

# WAS DIE LEISTE TRAGEN KANN, IM UNTERSCHIED ZU DEM, WAS SIE TRAEGT
#
#     KEIN Schluessel der Einstellungsdatei - er steht deshalb NICHT in
#     BAR_KEYS. Er steht nur im Abdruck, und er beantwortet die eine
#     Frage, die dort bis zum 12.08.2026 gefehlt hat: welche Namen darf
#     jemand ueberhaupt aufstellen.
#
#     GEMESSEN am 12.08.2026, bevor es ihn gab: bar_order() prueft
#     gegen die AUSGELIEFERTE Haelfte, und die Seite "Leiste" bot unter
#     "Wieder hinzufuegen" ebenfalls nur ausgelieferte Namen an. Beides
#     zusammen hiess: ein Modul, das die Vorgabe nicht aufstellt, ist
#     unerreichbar - der Nutzer bekommt "custom/weather (kennt diese
#     Leiste nicht)" zu lesen, obwohl der Zweig dafuer da ist und das
#     Skript dazu bei jedem Lauf erzeugt wird.
#
#     Solange die Vorgabe ALLES enthielt, was es gibt, fiel das nicht
#     auf. Sobald sie eine AUSWAHL ist, ist es der Unterschied zwischen
#     "umgeraeumt" und "weggenommen".
#
#     Fehlt der Schluessel im Abdruck, ist das Moegliche UNBEKANNT und
#     nicht LEER - dieselbe Unterscheidung wie beim ganzen Abdruck, und
#     aus demselben Grund: gegen eine leere Liste geprueft waere jeder
#     Name unbekannt, und der Nutzer verlaere seine Leiste an einen
#     alten Abdruck.
BAR_AVAILABLE = "modules_available"

# Wo der Abdruck liegt, relativ zum Systemwurzelverzeichnis - derselbe
# Ort wie shipped-applications und own-applications.
SHIPPED_BAR = "shipped-bar.json"

# Warum ein Eintrag nicht auf der Leiste gelandet ist. Zwei Gruende, und
# beide werden GENANNT: ein Name ohne Zweig ist ein leerer Platz, und ein
# leerer Platz meldet sich nie von selbst.
BAR_UNKNOWN = "kennt diese Leiste nicht"
BAR_REPEATED = "steht mehrfach in der Liste"

# Der dritte Grund, und er gilt nur fuer das Dock. Ein Modulname ohne
# Zweig ist ein Fehler in der Einstellung; ein angeheftetes Programm ohne
# Anwendungseintrag ist KEINER - es war einmal da und ist deinstalliert
# worden. Derselbe Wortlaut waere dieselbe Diagnose fuer zwei ganz
# verschiedene Lagen, und nur bei einer davon hilft "richtigstellen".
BAR_GONE = "auf dieser Maschine nicht installiert"

# --------------------------------------------------------------------
# Die Anheftungen des Docks: eine Wahl UND die Vorgabe, gegen die sie fiel
# --------------------------------------------------------------------
#
# DAS PROBLEM, DAS EINE BLOSSE LISTE NICHT LOESEN KANN
#     "dock_pins" allein ist ein ERSATZ: was darinsteht, steht im Dock,
#     und was nicht darinsteht, steht nicht darin. Das traegt zwei der
#     drei Faelle, die es gibt -
#
#       anheften   ein Name kommt dazu, den die Vorgabe nicht kennt
#       abnehmen   ein Name aus der VORGABE fehlt in der Liste, und
#                  genau dieses Fehlen IST das "nein"
#
#     - und scheitert am dritten. ZepOS liefert in einer neuen Fassung
#     eine weitere Anwendung mit. Fuer einen Nutzer, der nie etwas
#     angeheftet hat, erscheint sie (dock_pins ist null, es gilt die
#     Auslieferung). Fuer einen, der EINMAL ein Symbol abgenommen hat,
#     erscheint sie NIE: seine Liste nennt sie nicht, und eine Liste, die
#     die Vorgabe ersetzt, kann eine Vorgabe, die sich geaendert hat,
#     nicht bemerken. Sein Schreibtisch friert auf den Tag ein, an dem er
#     zum ersten Mal etwas angefasst hat.
#
#     Dieselbe Falle ist an derselben Datei schon einmal umgangen worden:
#     model.bar_stored() schreibt null statt der Liste, wenn beide Zeichen
#     fuer Zeichen gleich sind, "sonst haette ein Ausprobieren ohne
#     Ergebnis die Auslieferung eingefroren". Das deckt den Fall ab, in
#     dem am Ende NICHTS anders ist. Sobald ein Symbol wirklich
#     abgenommen wird, greift es nicht mehr.
#
# DIE LOESUNG: DIE VORGABE VON DAMALS STEHT DANEBEN
#     "dock_baseline" ist die ausgelieferte Liste, wie sie AUSSAH, als
#     der Nutzer zuletzt etwas an den Anheftungen geaendert hat. Damit
#     sind aus einer Liste zwei Aussagen ableitbar, und keine davon muss
#     eigens gepflegt werden:
#
#       abgewaehlt      steht in dock_baseline und nicht in dock_pins
#       neu geliefert   steht in der HEUTIGEN Auslieferung und nicht in
#                       dock_baseline
#
#     Das Neue wird angehaengt, das Abgewaehlte bleibt weg. Ein DRITTER
#     Schluessel fuer die Abwahl waere ableitbar und damit die Sorte
#     Kopie, die auseinanderlaeuft: zwei Listen, die dasselbe sagen
#     muessen, sagen irgendwann Verschiedenes.
#
# WARUM EIN ZWEITER SCHLUESSEL UND NICHT EIN OBJEKT IN dock_pins
#     Weil dock_pins dieselbe Form behaelt wie die zwei Leistenhaelften -
#     Liste von Namen oder null -, und diese Gleichform ist es, die
#     bar_choice(), bar_order(), das Bruecken-Bedienelement `reihenfolge`
#     und die Seite "Leiste" fuer alle drei Haelften mit EINEM Zweig
#     auskommen laesst. Ein Objekt an genau einer der drei haette an
#     jeder dieser Stellen einen Sonderweg erzwungen.
#
#     Es ist trotzdem keine zweite Wahrheitsquelle: dock_pins bleibt die
#     einzige Antwort auf "was will der Nutzer", dock_baseline beantwortet
#     "wogegen hat er das gesagt". Zwei Fragen, zwei Schluessel. Sie
#     werden GEMEINSAM geschrieben (model.Draft.sections()), damit sie
#     nicht auseinanderfallen koennen.
#
# WANDERUNG: null HEISST "UNBEKANNT" UND NICHT "LEER"
#     Eine Installation von vor dem 20.08.2026 hat den Schluessel nicht.
#     Dann ist die Vorgabe von damals unbekannt, und aus einem fehlenden
#     Namen laesst sich nicht ablesen, ob er abgewaehlt wurde oder erst
#     spaeter dazugekommen ist. In dem Fall wird NICHTS angehaengt - also
#     genau das Verhalten von vorher, und keines, das eine abgenommene
#     Anwendung stillschweigend zurueckbringt.
#
#     Geschrieben wird die Datei dabei nicht. Dieselbe Regel wie bei
#     user_settings.migrate_scaling(): "Nothing is written here ... The
#     retirement reaches the disk when something saves." Die Wanderung
#     passiert beim ersten Speichern der Anheftungen, und ab da ist der
#     Schluessel da.
BAR_BASELINE = "dock_baseline"


def bar_choice(document: dict[str, Any], key: str) -> list[str] | None:
    """Was der Nutzer fuer diese Haelfte gesagt hat.

    None heisst "wie ausgeliefert".

    Die Pruefung ist hier und nicht bei den Aufrufern, weil es zwei
    Aufrufer gibt und eine Liste, die der eine annimmt und der andere
    ablehnt, schlimmer ist als eine, die beide ablehnen: die Leiste
    stuende dann anders da als das Fenster, in dem man sie eingestellt
    hat.

    Abgelehnt wird alles, was keine Liste von Zeichenketten ist. Eine
    Zahl oder ein einzelner Name als Zeichenkette waere sonst ein
    Abschnitt, den der Erzeuger als "keine Aenderung" liest und das
    Fenster als "leer" zeigt - und der Nutzer sucht den Fehler auf
    seiner Leiste.
    """
    if key not in BAR_KEYS:
        raise KeyError(f"{key} ist keine Haelfte der Leiste; es gibt "
                       f"{', '.join(BAR_KEYS)}")
    return _bar_list(document, key)


def bar_baseline(document: dict[str, Any]) -> list[str] | None:
    """Die Auslieferung, gegen die der Nutzer seine Anheftungen gesetzt hat.

    None heisst UNBEKANNT und nicht leer - siehe den Kopf bei
    BAR_BASELINE. Eine Datei von vor dem 20.08.2026 hat den Schluessel
    nicht, und eine leere Liste an seiner Stelle hiesse "ZepOS lieferte
    damals nichts aus", woraufhin jede heute ausgelieferte Anwendung als
    NEU gaelte und wieder auftauchte - auch jede, die der Nutzer
    abgenommen hat.

    Dieselbe Formpruefung wie bei bar_choice(), durch dieselbe Funktion:
    was hier steht, wird gegen dieselben Namen gehalten und muss deshalb
    dieselbe Form haben. Zwei Pruefungen waeren zwei Formen.
    """
    return _bar_list(document, BAR_BASELINE)


def _bar_list(document: dict[str, Any], key: str) -> list[str] | None:
    """Eine Namensliste aus dem Abschnitt "bar", oder None.

    Die gemeinsame Haelfte von bar_choice() und bar_baseline(). Ihr
    Unterschied ist die Frage, WELCHE Schluessel es geben darf, und die
    beantwortet jede von beiden selbst; die Form ist dieselbe.
    """
    section = document.get(BAR)
    if section is None:
        return None
    if not isinstance(section, dict):
        raise UnusableSettings(
            f"\"{BAR}\" ist ein JSON {_json_type(section)} und kein Objekt "
            f"mit {', '.join(BAR_KEYS)}")

    value = section.get(key)
    if value is None:
        return None
    if not isinstance(value, list):
        raise UnusableSettings(
            f"\"{BAR}.{key}\" ist ein JSON {_json_type(value)}; erwartet "
            f"wird eine Liste von Namen oder null fuer die ausgelieferte "
            f"Reihenfolge")
    wrong = [_json_type(item) for item in value
             if not isinstance(item, str)]
    if wrong:
        raise UnusableSettings(
            f"\"{BAR}.{key}\" enthaelt "
            f"{', '.join(f'ein JSON {kind}' for kind in wrong)}; "
            f"jeder Eintrag muss ein Name sein")
    return list(value)


def shipped_bar(root: Path | None = None) -> dict[str, Any] | None:
    """Der Abdruck der ausgelieferten Leiste, oder None, wenn er fehlt.

    None heisst "unbekannt" und nicht "leer" - der Unterschied steht im
    Kopf dieses Abschnitts und entscheidet, ob ein gespeicherter Name
    verworfen wird oder stehenbleibt.

    Eine Datei, die DA ist und nicht gelesen werden kann, ist dagegen
    ein Fehler und wird gemeldet: sie wird erzeugt, also ist ein
    kaputter Inhalt ein Fehler dieses Systems und keine Eigenheit der
    Maschine, auf der es laeuft.

    DIE ANHEFTUNGEN STEHEN NICHT IN DER DATEI, UND ZWAR AUS ZWEI GRUENDEN
        Bis zum 13.08.2026 schrieb package() von zepos-config sie mit
        hinein. Das ging nicht, und der Paketbau hat es gemeldet:

            AssertionError: {... 'dock_pins': []}

        Der ERSTE Grund ist zeitlich. zepos-config wird aus einem
        Tarball gebaut, in dem packaging/ nicht liegt, und
        /usr/share/zepos ist zu diesem Zeitpunkt leer - die
        Anwendungsauswahl gehoert zepos-apps und ist beim Bauen dieses
        Pakets schlicht nicht zu erfahren.

        Der ZWEITE ist der wichtigere: sie STEHT schon irgendwo. Die
        Auswahl hat mit /usr/share/zepos/shipped-applications ihren
        eigenen Abdruck, geschrieben von dem Paket, das sie kennt. Sie
        ein zweites Mal in diese Datei zu legen waere genau die Kopie,
        die dieses Projekt an drei Stellen Catppuccin gekostet hat.

        Also wird die eine Quelle beim LESEN gefragt statt beim Bauen
        abgeschrieben. Fuer jeden Aufrufer sieht der Abdruck unveraendert
        aus - er traegt weiter alle vier Schluessel.

        setdefault und nicht Zuweisung: eine Maschine, die von einem
        aelteren Paket kommt, hat den Schluessel noch in der Datei. Dann
        gilt er. Was dort steht, ist die Auslieferung DIESES Pakets, und
        die ist naeher an der Wahrheit als eine Auswahl, die vielleicht
        schon halb aktualisiert ist.
    """
    root_path = Path(root) if root is not None else system_root()
    target = root_path / SHIPPED_BAR
    if not target.is_file():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UnusableSettings(
            f"{target} kann nicht gelesen werden: {exc}") from exc
    if not isinstance(data, dict):
        raise UnusableSettings(
            f"{target} ist ein JSON {_json_type(data)} und kein Objekt mit "
            f"{', '.join(BAR_KEYS)}")

    # Hier und nicht oben: apps importiert dieses Modul (es fragt
    # bar_choice), ein Import am Kopf waere ein Ring.
    import apps
    data.setdefault(BAR_PINS, apps.imprint_pins(root_path))
    return data


def bar_names(imprint: dict[str, Any] | None, key: str) -> list[str] | None:
    """Die ausgelieferten Namen dieser Haelfte, aus dem Abdruck.

    Die Anheftungen stehen darin mit Beschriftung und Anwendungseintrag,
    die Leistenmodule als blosse Namen. Beide Formen werden gelesen, und
    das ist keine Nachsicht: der NAME ist in beiden Faellen das, was
    gespeichert wird, und eine Funktion, die je nach Haelfte eine andere
    Form verlangt, haette an jeder Aufrufstelle einen Zweig.
    """
    if imprint is None:
        return None
    listed = imprint.get(key)
    if listed is None:
        return None
    if not isinstance(listed, list):
        raise UnusableSettings(
            f"\"{key}\" im Abdruck ist ein JSON {_json_type(listed)} und "
            f"keine Liste")

    names = []
    for item in listed:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"])
        else:
            raise UnusableSettings(
                f"ein Eintrag in \"{key}\" im Abdruck ist ein JSON "
                f"{_json_type(item)} ohne Namen")
    return names


def bar_labels(imprint: dict[str, Any] | None, key: str) -> dict[str, str]:
    """Wie ein Eintrag heisst, wenn der Abdruck es sagt.

    Nur fuer die Anheftungen: `firefox` ist ein Paketname und `Firefox`
    das, was auf dem Schirm steht. Die Beschriftung kommt aus dem
    Abdruck und nicht aus einer Tabelle hier - eine Tabelle waere die
    zweite Liste, die veraltet, sobald jemand eine Anwendung tauscht.
    Ein Modulname der Leiste hat keine; er IST der Name, unter dem der
    Zweig in ags-bar.template steht, und ein erfundenes deutsches Wort
    davor waere nicht auffindbar.
    """
    if imprint is None:
        return {}
    listed = imprint.get(key)
    if not isinstance(listed, list):
        return {}
    return {item["name"]: item["label"] for item in listed
            if isinstance(item, dict) and isinstance(item.get("name"), str)
            and isinstance(item.get("label"), str) and item["label"]}


Discarded = list[tuple[str, str]]


def bar_order(chosen: list[str] | None,
              placeable: list[str] | None,
              shipped: list[str] | None,
              *, unknown: str = BAR_UNKNOWN) -> tuple[list[str], Discarded]:
    """Was wirklich dasteht, und was dabei unter den Tisch gefallen ist.

    Zurueck kommen zwei Listen: die wirksame Reihenfolge und die
    verworfenen Eintraege mit dem Grund. Der zweite Teil ist der Grund,
    aus dem diese Funktion ueberhaupt eine eigene ist - ein Name, den es
    nicht gibt, DARF nicht still verschwinden:

      * auf der Leiste waere er ein leerer Platz. build() gibt null
        zurueck und schreibt eine Zeile auf eine Konsole, die niemand
        liest.
      * im Dock waere er ein Knopf, der nichts oeffnet - und ein toter
        Knopf ist nach Spec §7.4 der schlimmste Fehler, den ZepOS
        erzeugen kann, weil ihn niemand meldet. Genau daran ist das
        Einstellungssymbol im Fuss aufgefallen, und auch das erst, als
        ein Mensch das gebaute Medium benutzt hat.

    DREI LISTEN UND NICHT ZWEI, SEIT DEM 12.08.2026
        `placeable` ist, was diese Haelfte tragen KANN, `shipped`, was
        ohne jede Einstellung darauf steht. Bis zu diesem Tag war das
        eine Liste, weil die Vorgabe alles enthielt, was es gab.

        Seit die Vorgabe eine AUSWAHL ist, sind es zwei Fragen: gegen
        `shipped` geprueft waere jedes zugeschaltete Modul "unbekannt" -
        also genau das, was der Nutzer gerade eingeschaltet hat, mit
        einer Klage daneben. Fuer die Anheftungen des Docks sind beide
        Listen weiterhin dieselbe; dort gibt es nichts, was ZepOS kennt
        und nicht ausliefert.

    `placeable is None` heisst "auf dieser Maschine ist unbekannt, was
    moeglich ist" (kein Abdruck, oder ein aelterer ohne diesen
    Schluessel). Dann wird NICHTS verworfen: eine Liste gegen nichts zu
    pruefen hiesse, jeden Namen fuer unbekannt zu halten.

    `unknown` IST DIE DIAGNOSE, NICHT DIE REGEL - seit dem 20.08.2026
        Nur ein Wort mit Vorgabewert, und ausdruecklich nach Schluessel
        uebergeben, damit die drei Stellen, die bisher drei Werte
        uebergeben, unveraendert weiterlaufen. Eine vierte POSITIONELLE
        Liste hat am 13.08.2026 eine installierte Maschine in eine
        Anmeldeschleife geschickt (siehe tests/src/test_apps_pinned_
        call.py); die Erweiterung hier kann das nicht, weil ein alter
        Aufruf gueltig bleibt.

        Warum ueberhaupt: fuer die Leiste heisst "nicht aufstellbar",
        dass der Name falsch ist. Fuer das Dock heisst es meistens, dass
        ein Programm DEINSTALLIERT wurde - dieselbe Ablehnung, zwei
        ganz verschiedene Ursachen, und "kennt diese Leiste nicht"
        schickt den Nutzer bei der zweiten in die falsche Datei.
    """
    if chosen is None:
        return (list(shipped) if shipped is not None else [], [])

    kept: list[str] = []
    discarded: list[tuple[str, str]] = []
    for name in chosen:
        if name in kept:
            discarded.append((name, BAR_REPEATED))
        elif placeable is not None and name not in placeable:
            discarded.append((name, unknown))
        else:
            kept.append(name)
    return kept, discarded


def dock_effective(chosen: list[str] | None,
                   baseline: list[str] | None,
                   shipped: list[str] | None) -> list[str] | None:
    """Die Anheftungen, nachdem die HEUTIGE Auslieferung dazugerechnet ist.

    Die eine Funktion, um derentwillen es BAR_BASELINE gibt; die ganze
    Begruendung steht dort. Kurz: `chosen` sagt, was der Nutzer wollte,
    `baseline`, wogegen er es gesagt hat, `shipped`, was heute
    ausgeliefert wird. Was seit damals DAZUGEKOMMEN ist, hat er nie
    abgewaehlt - er konnte es nicht - und wird angehaengt.

    Zurueck kommt None, wenn `chosen` None ist: "wie ausgeliefert" ist
    eine Angabe, die niemand nachbessern muss, und sie hier in die
    ausgelieferte Liste aufzuloesen haette den einen Aufrufer, der
    zwischen beidem unterscheidet (model.Draft.current_bar()), um genau
    diese Unterscheidung gebracht.

    DAS NEUE KOMMT ANS ENDE, UND DAS IST EINE ENTSCHEIDUNG
        An seinen Platz in der ausgelieferten Reihenfolge einsortiert
        waere es huebscher - die Auswahl ist dort nach Aufgaben gruppiert
        (siehe apps.from_recipe()). Es waere aber auch die einzige
        Stelle, an der sich die Reihenfolge des Nutzers von selbst
        aendert: wer seine Symbole sortiert hat, faende beim naechsten
        Anmelden eines dazwischen, und zwar unter dem Mauszeiger. Ans
        Ende ist vorhersagbar, sichtbar, und in einem Zug wegzuziehen.

    UNBEKANNTE VORGABE HAENGT NICHTS AN
        `baseline is None` heisst "wogegen er das gesagt hat, steht
        nicht in der Datei" - eine Installation von vor dem 20.08.2026.
        Aus einem fehlenden Namen liesse sich dann nicht ablesen, ob er
        abgewaehlt oder erst spaeter dazugekommen ist, und die falsche
        Annahme bringt ein Symbol zurueck, das jemand ausdruecklich
        weggenommen hat. Also nichts - genau das Verhalten von vorher.
    """
    if chosen is None:
        return None
    if baseline is None or shipped is None:
        return list(chosen)

    known = set(baseline)
    already = set(chosen)
    return list(chosen) + [name for name in shipped
                           if name not in known and name not in already]


def shipped_pins(root: Path | None = None) -> list[str] | None:
    """Was ZepOS heute anheftet, aus derselben Quelle wie alles andere.

    Erst der Abdruck (shipped-bar.json), weil das die Datei ist, gegen
    die auch die Seite "Leiste" prueft. Fehlt er - ein Checkout ohne
    Erzeugungslauf -, wird apps.shipped() gefragt, das im Checkout die
    Rezepte liest. Zwei Wege, EIN Ergebnis: der Abdruck entsteht
    seinerseits aus apps.imprint_pins(), siehe shipped_bar().

    None heisst unbekannt. Das ist die Antwort, wenn weder Abdruck noch
    Rezept noch Paketliste auf dieser Maschine zu finden sind, und sie
    ist wichtig: als leere Liste geschrieben waere eine Vorgabe
    hinterlegt, die es nie gab, und beim naechsten Lauf gaelte JEDE
    ausgelieferte Anwendung als neu.
    """
    root_path = Path(root) if root is not None else system_root()

    names = bar_names(shipped_bar(root_path), BAR_PINS)
    if names is not None:
        return names

    # Hier und nicht am Kopf: apps importiert dieses Modul, ein Import
    # oben waere ein Ring. Dieselbe Stelle, an der shipped_bar() es tut.
    import apps
    listed = apps.shipped(root_path)
    return listed or None


def pinnable(shipped: list[str] | None) -> list[str] | None:
    """Welche Namen ueberhaupt angeheftet werden duerfen.

    Die Vereinigung aus zwei Listen, und beide werden gebraucht:

      ausgeliefert   was ZepOS mitbringt. Steht auch dann drin, wenn auf
                     DIESER Maschine kein Anwendungseintrag dafuer liegt
                     - im Checkout ist das der Normalfall, und ein
                     Erzeugungslauf, der die halbe Vorgabe verwirft,
                     weil der Entwickler die Programme nicht
                     installiert hat, erzeugt ein anderes Dock als die
                     Installation.
      installiert    was der Schreibtisch dieses Kontos wirklich hat
                     (src/desktop_entries.py). DAS ist die Haelfte, die
                     "anheften, was die Vorgabe nicht kennt" ueberhaupt
                     erst moeglich macht.

    None bleibt None: ist die Auslieferung unbekannt, wird nicht
    geprueft - dieselbe Regel wie bei bar_order(), und aus demselben
    Grund. Eine Pruefung, die nur die halbe Wahrheit kennt, verwirft
    Namen, die in Ordnung sind.
    """
    if shipped is None:
        return None
    known = set(shipped)
    return list(shipped) + [name for name in desktop_entries.names()
                            if name not in known]


def dock_plan(document: dict[str, Any],
              root: Path | None = None) -> dict[str, Any]:
    """Was WIRKLICH im Fuss steht, und was dabei herausgefallen ist.

    Das Gegenstueck zu home_plan(), Satz fuer Satz - und ausdruecklich
    dieselbe Rechnung, die `zepos-settings-gui --json get` fuer das
    Bedienelement "bar.dock_pins" anstellt (settings/zepos_settings_gui/
    bridge.py, _page_leiste(), und model.Draft.current_bar() davor):

        die Wahl des Nutzers        bar_choice()
        plus die HEUTIGE Auslieferung, soweit sie nach der Grundlinie
        dazugekommen ist                        dock_effective()
        jeder Name gegen das, was diese Maschine anheften KANN
                                    bar_order(..., pinnable(...))

    Es ist keine zweite Antwort auf dieselbe Frage, sondern DIESELBE
    Antwort aus denselben vier Funktionen. Sie steht hier, weil die drei
    Rechtsklick-Menues sie brauchen und keines davon Python importieren
    kann - das Dock und das Home sind GJS, der Starter ist C++.

    WARUM DAS UEBERHAUPT HIER STEHT UND NICHT WEITER BEI DER BRUECKE
        Bis zum 21.08.2026 nahm das Dock den Weg ueber
        `zepos-settings-gui --json get`, und der Starter tat es ihm
        nach. Das war die Antwort auf eine Frage, die das Dock damals
        alleine hatte. Seit es DREI Menues sind, ist es eine Antwort,
        die dreimal abgeschrieben werden muesste - und die Antwort des
        Homes (`settings.py home`) waere die vierte. Ein Unterbefehl
        weiss es fuer alle drei; der Kopf von _home_command() fuehrt
        dieselbe Ueberlegung fuer das Home aus.

    ZURUECK KOMMT IMMER EINE LISTE, AUCH BEI null - genau wie bei
    home_plan(): "wie ausgeliefert" ist fuer eine Oberflaeche, die
    zeichnen soll, keine brauchbare Antwort. Ob der Nutzer eine Wahl
    getroffen hat, steht daneben in "chosen".
    """
    shipped = shipped_pins(root)
    chosen = bar_choice(document, BAR_PINS)
    effective = dock_effective(chosen, bar_baseline(document), shipped)

    kept, discarded = bar_order(effective, pinnable(shipped), shipped,
                                unknown=BAR_GONE)
    return {
        "pins": kept,
        "discarded": [{"name": name, "why": why} for name, why in discarded],
        "chosen": chosen is not None,
    }


def dock_write(document: dict[str, Any], pins: list[str],
               root: Path | None = None) -> dict[str, Any]:
    """Der Abschnitt, wie er auf die Platte gehoert - Anheftungen UND Vorgabe.

    DIE ZWEI SCHLUESSEL WERDEN GEMEINSAM GESCHRIEBEN, IMMER
        Der Kopf bei BAR_BASELINE sagt es fuer diese Datei ("Sie werden
        GEMEINSAM geschrieben (model.Draft.sections()), damit sie nicht
        auseinanderfallen koennen"), home_write() sagt es fuer das Home.
        Hier ist die dritte Stelle, an der es gilt, und ab heute die
        einzige, die die drei Menues betrifft: eine Anheftungsliste ohne
        frische Vorgabe hiesse, der Nutzer haette gegen die Auslieferung
        von GESTERN entschieden.

    DER GANZE ABSCHNITT UND NICHT NUR DIE ZWEI SCHLUESSEL
        merge() ERSETZT einen Abschnitt (siehe dort, "Sections are
        REPLACED, not deep-merged"). Wer hier nur die Anheftungen
        zurueckgaebe, loeschte modules_left und modules_right - also die
        ganze Leiste des Nutzers, beim Anheften eines Symbols.
        model.Draft.sections() baut den Abschnitt aus demselben Grund
        vollstaendig auf.

    Die Vorgabe ist die HEUTIGE Auslieferung. Ist sie unbekannt (kein
    Abdruck), bleibt der Schluessel null statt leer - eine leere Liste
    hiesse "ZepOS lieferte nichts aus", und danach gaelte jede
    ausgelieferte Anwendung als neu.
    """
    stored = document.get(BAR)
    section = dict(stored) if isinstance(stored, dict) else {}
    for key in BAR_KEYS:
        section.setdefault(key, None)
    section[BAR_PINS] = list(pins)
    section[BAR_BASELINE] = shipped_pins(root)
    return {BAR: section}


# --------------------------------------------------------------------
# Das Home: dieselben Regeln wie das Dock, nur mit einem Ort dabei
# --------------------------------------------------------------------
#
# WARUM EINE ZELLE UND NICHT ZWEI BILDPUNKTE - GEMESSEN am 20.08.2026
#     Der naheliegende Weg waere `{"x": 1800, "y": 900}`. Er ist an zwei
#     Messungen gescheitert, und die zweite ist die, mit der niemand
#     gerechnet hat:
#
#       1. Der kleinere Schirm. Ein Symbol bei (1800, 900) liegt auf
#          einem 1366 breiten Schirm ausserhalb und ist nie wieder
#          anzuklicken.
#       2. DAS DOCK FAEHRT EIN UND AUS. GEMESSEN im verschachtelten
#          Compositor: die Layer-Shell-Flaeche des Homes ist bei
#          Exclusivity.NORMAL genau so gross wie der Schirm MINUS die
#          reservierten Zonen, und sie wird im Betrieb umgebaut -
#
#              ohne Leiste        931x1081
#              mit Leiste         931x1041   (Ursprung 0,40)
#              Leiste wieder weg  931x1081
#
#          Das Dock hat ein toggle() (ags-dock.template). Mit
#          Bildpunkten wanderte also bei jedem Ein- und Ausfahren des
#          Docks JEDES Symbol. Ein Aufloesungswechsel ist gar nicht
#          noetig; eine Taste genuegt.
#
#     Gespeichert wird deshalb eine ZELLE: `{"name": ..., "col": 3,
#     "row": 1}`. Wie viele Spalten und Zeilen es HEUTE gibt, rechnet
#     die Oberflaeche aus der heutigen Flaeche und dem Zellmass
#     (sizes.home_cell_px()) - hier steht keine Zahl, die einen Schirm
#     kennt.
#
# EIN EINTRAG DARF SEINE ZELLE AUCH WEGLASSEN
#     `{"name": "firefox"}` ohne col/row heisst "noch nicht abgelegt".
#     Genau das schreibt home_effective() fuer eine Anwendung, die ZepOS
#     seit der Grundlinie dazuliefert: WO sie liegen soll, kann diese
#     Datei nicht wissen - das haengt daran, welche Zellen auf DIESEM
#     Schirm gerade frei sind, und das ist eine Frage der Anzeige und
#     nicht der Einstellung. Die Oberflaeche legt sie in die erste freie
#     Zelle und schreibt nichts zurueck.
#
#     Dieselbe Regel gilt fuer eine Zelle, die es heute nicht GIBT (der
#     kleinere Schirm): ersatzweise anzeigen, NICHT zurueckschreiben.
#     Steckt der Nutzer den grossen Schirm wieder an, liegt das Symbol
#     wieder dort, wo er es hingelegt hat. Das ist derselbe Gedanke wie
#     bei BAR_BASELINE: eine Anzeige, die sich an die Lage anpasst, darf
#     die WAHL des Nutzers nicht ueberschreiben.
HOME = "home"
HOME_ICONS = "icons"
HOME_BASELINE = "baseline"

# Die Felder eines Eintrags. "name" ist Pflicht, die Zelle nicht.
HOME_NAME = "name"
HOME_COL = "col"
HOME_ROW = "row"
HOME_CELL = (HOME_COL, HOME_ROW)


def home_icons(document: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Was der Nutzer auf sein Home gelegt hat. None heisst "wie ausgeliefert".

    Geprueft wird hier und nicht beim Aufrufer, aus demselben Grund wie
    bei bar_choice(): es gibt mehr als einen Leser, und eine Liste, die
    der eine annimmt und der andere ablehnt, ist schlimmer als eine, die
    beide ablehnen - das Home stuende dann anders da als das Fenster, in
    dem man es eingestellt hat.

    EINE HALBE ZELLE IST EIN FEHLER UND KEIN "NOCH NICHT ABGELEGT"
        `{"name": "firefox", "col": 3}` ohne "row" sieht aus wie eine
        Angabe und ist keine. Wer sie als "nicht abgelegt" durchliesse,
        legte das Symbol woanders hin als der Nutzer geschrieben hat,
        ohne dass irgendetwas es sagt. Entweder BEIDE Zahlen oder KEINE.
    """
    section = document.get(HOME)
    if section is None:
        return None
    if not isinstance(section, dict):
        raise UnusableSettings(
            f"\"{HOME}\" ist ein JSON {_json_type(section)} und kein Objekt "
            f"mit {HOME_ICONS}, {HOME_BASELINE}")

    value = section.get(HOME_ICONS)
    if value is None:
        return None
    if not isinstance(value, list):
        raise UnusableSettings(
            f"\"{HOME}.{HOME_ICONS}\" ist ein JSON {_json_type(value)}; "
            f"erwartet wird eine Liste von Symbolen oder null fuer die "
            f"ausgelieferte Belegung")

    entries: list[dict[str, Any]] = []
    for position, item in enumerate(value):
        where = f"\"{HOME}.{HOME_ICONS}\"[{position}]"
        if not isinstance(item, dict):
            raise UnusableSettings(
                f"{where} ist ein JSON {_json_type(item)}; erwartet wird ein "
                f"Objekt wie {{\"{HOME_NAME}\": \"firefox\", "
                f"\"{HOME_COL}\": 0, \"{HOME_ROW}\": 0}}")
        name = item.get(HOME_NAME)
        if not isinstance(name, str) or not name:
            raise UnusableSettings(
                f"{where}.{HOME_NAME} ist ein JSON {_json_type(name)}; "
                f"jedes Symbol braucht den Namen einer Anwendung")

        entry: dict[str, Any] = {HOME_NAME: name}
        given = [field for field in HOME_CELL if item.get(field) is not None]
        if given and len(given) != len(HOME_CELL):
            missing = [f for f in HOME_CELL if f not in given]
            raise UnusableSettings(
                f"{where} nennt {', '.join(given)} und nicht "
                f"{', '.join(missing)}; eine Zelle braucht beide Zahlen, "
                f"oder keine - dann sucht das Home selbst einen Platz")
        for field in given:
            number = item.get(field)
            # bool IST in Python ein int, und `true` als Spaltennummer
            # waere sonst die Spalte 1 - eine Zahl, die niemand
            # geschrieben hat.
            if not isinstance(number, int) or isinstance(number, bool):
                raise UnusableSettings(
                    f"{where}.{field} ist ein JSON {_json_type(number)}; "
                    f"erwartet wird eine ganze Zahl ab 0")
            if number < 0:
                raise UnusableSettings(
                    f"{where}.{field} ist {number}; eine Zelle zaehlt ab 0 "
                    f"und kann nicht negativ sein")
            entry[field] = number
        entries.append(entry)
    return entries


def home_baseline(document: dict[str, Any]) -> list[str] | None:
    """Die Auslieferung, gegen die der Nutzer sein Home gesetzt hat.

    Eine Liste von NAMEN und keine von Symbolen, obwohl sie neben einer
    Symbolliste steht: sie beantwortet "was lieferte ZepOS damals aus",
    und die Auslieferung hat keine Zellen - wo etwas liegt, ist die
    Antwort des Nutzers und nie die der Auslieferung. Genau dieselbe
    Form wie bar.dock_baseline, damit dock_effective() und
    home_effective() dieselbe Rechnung machen koennen.

    None heisst UNBEKANNT und nicht leer - siehe BAR_BASELINE.
    """
    section = document.get(HOME)
    if section is None:
        return None
    if not isinstance(section, dict):
        raise UnusableSettings(
            f"\"{HOME}\" ist ein JSON {_json_type(section)} und kein Objekt "
            f"mit {HOME_ICONS}, {HOME_BASELINE}")

    value = section.get(HOME_BASELINE)
    if value is None:
        return None
    if not isinstance(value, list):
        raise UnusableSettings(
            f"\"{HOME}.{HOME_BASELINE}\" ist ein JSON {_json_type(value)}; "
            f"erwartet wird eine Liste von Namen oder null")
    wrong = [_json_type(item) for item in value if not isinstance(item, str)]
    if wrong:
        raise UnusableSettings(
            f"\"{HOME}.{HOME_BASELINE}\" enthaelt "
            f"{', '.join(f'ein JSON {kind}' for kind in wrong)}; "
            f"jeder Eintrag muss ein Name sein")
    return list(value)


def home_effective(chosen: list[dict[str, Any]] | None,
                   baseline: list[str] | None,
                   shipped: list[str] | None) -> list[dict[str, Any]] | None:
    """Das Home, nachdem die HEUTIGE Auslieferung dazugerechnet ist.

    Die Schwester von dock_effective(), Satz fuer Satz dieselbe Rechnung
    - und deshalb steht die Begruendung dort und wird hier nicht noch
    einmal erzaehlt: `chosen` ist, was der Nutzer wollte, `baseline`,
    wogegen er es gesagt hat, `shipped`, was heute ausgeliefert wird.
    Was seit damals dazugekommen ist, hat er nie abgewaehlt - er konnte
    es nicht - und wird angehaengt.

    DER EINE UNTERSCHIED: DAS NEUE KOMMT OHNE ZELLE
        dock_effective() haengt einen Namen an eine Reihe; hier fehlt
        die Antwort auf "wo". Sie wird auch nicht erfunden: welche Zelle
        frei ist, weiss nur die Oberflaeche, die gerade eine Flaeche
        einer bestimmten Groesse vor sich hat. Angehaengt wird deshalb
        `{"name": ...}` ohne col/row, und das Home sucht beim Zeichnen
        die erste freie Zelle. Eine hier erfundene Zelle waere eine, die
        auf einem schmaleren Schirm daneben liegt - und sie stuende dann
        auch noch in der Datei, als haette der Nutzer sie gewaehlt.

    UNBEKANNTE VORGABE HAENGT NICHTS AN - dieselbe Regel wie beim Dock.
    """
    if chosen is None:
        return None
    if baseline is None or shipped is None:
        return list(chosen)

    known = set(baseline)
    already = {entry[HOME_NAME] for entry in chosen}
    return list(chosen) + [{HOME_NAME: name} for name in shipped
                           if name not in known and name not in already]


def home_names(icons: list[dict[str, Any]] | None) -> list[str] | None:
    """Nur die Namen, in ihrer Reihenfolge - fuer bar_order().

    Damit das Home seine Namen durch DIESELBE Pruefung schicken kann wie
    das Dock (kennt diese Maschine die Anwendung ueberhaupt?), statt
    daneben eine zweite zu fuehren. Eine zweite Pruefung waere eine
    zweite Antwort auf dieselbe Frage, und src/apps.py beschreibt in
    seinem Kopf, was das kostet: "Ein Dock, das einen Namen annimmt, den
    das Fenster verwirft, waere eine Einstellung, die man sieht und
    nicht bekommt."
    """
    return None if icons is None else [entry[HOME_NAME] for entry in icons]


def home_plan(document: dict[str, Any],
              root: Path | None = None) -> dict[str, Any]:
    """Was WIRKLICH auf dem Home liegt, und was dabei herausgefallen ist.

    Das Gegenstueck zu dem, was `zepos-settings-gui --json get` fuer das
    Dock tut - und aus demselben Grund hier und nicht im Fenster: die
    Regeln (Grundlinie anhaengen, unbekannte Namen verwerfen, den Grund
    NENNEN) sind dieselben, und zwei Antworten auf dieselbe Frage waeren
    ein Home, das einen Namen annimmt, den das Dock verwirft.

    WARUM DAS HOME NICHT DIE BRUECKE BENUTZT
        Das Dock liest ueber `zepos-settings-gui --json get`, weil seine
        Reihenfolge dort ein Bedienelement der Seite "Leiste" IST - es
        holt sich genau das Feld, das der Nutzer im Einstellungsfenster
        sieht. Das Home hat kein solches Bedienelement; es hat eine
        eigene Datei-Sektion. Es fragt deshalb settings.py direkt, ueber
        `settings.py home` - denselben Weg, ueber den die AGS-Fenster
        auch SCHREIBEN (`settings.py merge`, siehe USAGE).

    ZURUECK KOMMT IMMER EINE LISTE, AUCH BEI null
        `home.icons` ist null bei jeder frischen Installation, und
        "wie ausgeliefert" ist fuer eine Oberflaeche, die zeichnen soll,
        keine brauchbare Antwort. Aufgeloest wird deshalb hier: die
        ausgelieferte Auswahl, jede Anwendung OHNE Zelle - wo sie liegt,
        entscheidet die erste freie Zelle auf dem Schirm, den es gerade
        gibt (siehe den Kopf bei HOME).

    DIE AUSGELIEFERTE AUSWAHL IST DIESELBE WIE DIE DES DOCKS
        Und das ist eine Entscheidung: es gibt EINE Liste "was ZepOS
        mitliefert" (shipped_pins(), aus demselben Abdruck), und zwei
        davon waeren zwei Listen, die dasselbe sagen muessten. Was der
        NUTZER daraus macht, ist getrennt - das ist der Unterschied, um
        den es ihm ging: "Zum Home hinzufuegen" NEBEN "Zum Dock
        hinzufuegen". Getrennt sind die WAHLEN, nicht die Auslieferung.
    """
    shipped = shipped_pins(root)
    chosen = home_icons(document)
    if chosen is None:
        effective: list[dict[str, Any]] | None = (
            None if shipped is None else [{HOME_NAME: n} for n in shipped])
    else:
        effective = home_effective(chosen, home_baseline(document), shipped)

    kept, discarded = bar_order(home_names(effective), pinnable(shipped),
                                shipped, unknown=BAR_GONE)

    # Die Zellen wieder an die Namen - der ERSTE Treffer gewinnt, genau
    # wie bar_order() den ersten Platz behaelt und jeden weiteren als
    # "steht mehrfach in der Liste" verwirft. Ein spaeterer Eintrag
    # desselben Namens ist dort schon herausgefallen; seine Zelle hier
    # noch zu nehmen hiesse, einen verworfenen Eintrag doch zu benutzen.
    cells: dict[str, dict[str, Any]] = {}
    for entry in (effective or []):
        cells.setdefault(entry[HOME_NAME], entry)

    return {
        "icons": [cells.get(name, {HOME_NAME: name}) for name in kept],
        "discarded": [{"name": name, "why": why} for name, why in discarded],
        # Damit der Aufrufer "wie ausgeliefert" von "der Nutzer hat eine
        # leere Flaeche gewaehlt" unterscheiden kann, ohne die Datei ein
        # zweites Mal zu lesen. Genau diese Unterscheidung ist der Grund,
        # aus dem home_icons() null zurueckgibt statt einer leeren Liste.
        "chosen": chosen is not None,
    }


def home_write(document: dict[str, Any], icons: list[dict[str, Any]],
               root: Path | None = None) -> dict[str, Any]:
    """Der Abschnitt, wie er auf die Platte gehoert - Symbole UND Vorgabe.

    DIE ZWEI SCHLUESSEL WERDEN GEMEINSAM GESCHRIEBEN, IMMER
        settings.py sagt das bei BAR_BASELINE ueber das Dock ("Sie werden
        GEMEINSAM geschrieben (model.Draft.sections()), damit sie nicht
        auseinanderfallen koennen"), und fuer das Home gilt es genauso.
        Eine Symbolliste ohne frische Vorgabe hiesse: der Nutzer haette
        gegen die Auslieferung von GESTERN entschieden, und alles, was
        seither dazugekommen ist, erschiene beim naechsten Anmelden noch
        einmal - auch das, was er gerade abgenommen hat.

        Genau deshalb ist das hier eine Funktion und keine Zeile beim
        Aufrufer: das Home ist nicht der einzige Schreiber. Das Dock und
        der Starter sollen "Zum Home hinzufuegen" auch anbieten, und drei
        Aufrufer, die je daran denken muessen, die Vorgabe mitzuschreiben,
        sind zwei Aufrufer, die es einmal vergessen.

    Die Vorgabe ist die HEUTIGE Auslieferung. Ist sie unbekannt (kein
    Abdruck), bleibt der Schluessel null statt leer - eine leere Liste
    hiesse "ZepOS lieferte nichts aus", und danach gaelte jede
    ausgelieferte Anwendung als neu.
    """
    return {HOME: {HOME_ICONS: icons, HOME_BASELINE: shipped_pins(root)}}


def check_home(document: dict[str, Any]) -> list[str]:
    """Was am Home-Abschnitt nicht stimmt, in Saetzen.

    Eine Liste und kein Wurf, aus demselben Grund wie bei check_bar():
    wer die Symbolliste falsch geschrieben hat, hat moeglicherweise auch
    die Vorgabe danebengeschrieben, und eine Meldung nach der anderen zu
    erarbeiten ist die Art Sitzung, die niemand zu Ende bringt.
    """
    problems = []
    for reader in (home_icons, home_baseline):
        try:
            reader(document)
        except UnusableSettings as problem:
            problems.append(str(problem))
    return problems


def bar_complaint(key: str, discarded: Discarded) -> str:
    """Was ueber die verworfenen Eintraege zu sagen ist - einmal formuliert.

    Aus demselben Grund an einer Stelle wie unreadable(): die Meldung
    erscheint im Einstellungsfenster und auf der Kommandozeile, und zwei
    Wortlaute fuer eine Lage lesen sich wie zwei Lagen.
    """
    if not discarded:
        return ""
    listed = ", ".join(f"{name} ({why})" for name, why in discarded)
    return (f"Aus \"{BAR}.{key}\" wurde verworfen: {listed}. "
            f"Der Rest steht unveraendert da; ein Zuruecksetzen auf die "
            f"ausgelieferte Reihenfolge raeumt auch das weg.")


def check_bar(document: dict[str, Any]) -> list[str]:
    """Was an diesem Leisten-Abschnitt nicht stimmt, in Saetzen.

    Eine Liste und kein Wurf, weil der Aufrufer alle drei Haelften
    hoeren will: wer `modules_left` falsch geschrieben hat, hat es
    moeglicherweise auch rechts getan, und eine Meldung nach der anderen
    zu erarbeiten ist genau die Art Sitzung, die niemand zu Ende bringt.

    Die hinterlegte Vorgabe wird MITGEPRUEFT, obwohl sie keine Haelfte
    ist: sie steht im selben Abschnitt, sie wird beim naechsten
    Erzeugungslauf gegen dieselben Namen gehalten, und eine kaputte
    Vorgabe ist ein Dock, dem Symbole fehlen. Ein `check`, das sie
    uebergeht, meldete "nichts zu beanstanden" ueber eine Datei, an der
    der Erzeuger gleich scheitert.
    """
    problems = []
    for key in BAR_KEYS:
        try:
            bar_choice(document, key)
        except UnusableSettings as problem:
            problems.append(str(problem))
    try:
        bar_baseline(document)
    except UnusableSettings as problem:
        problems.append(str(problem))
    return problems


USAGE = """usage: settings.py check
       settings.py merge '<json object>'
       settings.py home
       settings.py home set '<json array>'
       settings.py home add <name>
       settings.py home remove <name>
       settings.py dock
       settings.py dock add <name>
       settings.py dock remove <name>

check reads the user settings and reports what is wrong with them,
saying nothing when there is nothing to say. A file that is not there is
not a fault: a fresh installation has none.

home writes the effective Home layout to standard output as JSON - the
user's icons with the shipped selection appended, every name checked
against the applications this machine actually has, and the discarded
ones named with a reason. The AGS Home widget is GJS and cannot import
this module, so it asks for the answer instead of working it out a
second time.

home set/add/remove change it. They exist beside merge because the
Home's two keys - the icons and the shipped baseline they were chosen
against - have to be written together or the next release quietly brings
back what the user just took off. add and remove take a name, so the
Dock and the Starter can offer "add to Home" without knowing any of
that; set takes the whole array and is how the Home itself saves a
layout somebody dragged.

    settings.py home add firefox

dock is the same three things for the Dock's pinned applications, and it
exists for the same reason - bar.dock_pins and bar.dock_baseline have to
be written together, and there are now three menus that offer to change
them: the Dock's own, the Home's, and the Starter's. Two of the three
are not Python. A subcommand knows the rule once; three callers that
each have to remember it are two that forget it.

    settings.py dock add firefox

Both add commands are silent about a name that is already there: they
end with 0 and write nothing. Pinning twice is not a complaint worth
making, and a non-zero exit would put an error in front of somebody for
whom nothing is missing.

merge merges whole top-level sections into the settings and writes them
back atomically at 0600, keeping every section the argument does not
name. Both exist for the callers that cannot import this module - the
generator is bash, the AGS dialogs are GJS - so that one implementation
still reads and writes the file.

    settings.py merge '{"vpn": {"server": "gw.example.org"}}'"""


def unreadable(target: Path, exc: BaseException) -> str:
    """What to say about a settings file that cannot be used.

    Both halves matter, which is why this is one sentence and not the
    exception on its own: WHICH file, and WHAT is wrong with it. The
    exception alone says "unsupported schema_version None" without naming
    the file that carries it, and there is more than one settings file on
    a machine. Written once because four callers say it - this module's
    own command line, zepos-settings, the style settings manager and the
    generator - and four wordings for one condition read as four
    different conditions."""
    return (f"{target} cannot be read: {exc}\n"
            f"A settings file has to be a JSON object carrying "
            f"\"schema_version\": {SCHEMA_VERSION}; repair it, or move it "
            f"aside and let the defaults be written again.")


def _home_command(rest: list[str]) -> int:
    """`settings.py home [set <json> | add <name> | remove <name>]`.

    VIER UNTERBEFEHLE UND NICHT EIN merge MIT EINEM OBJEKT, und das ist
    der Grund, aus dem es sie ueberhaupt gibt: `merge` verlangte vom
    Aufrufer, die Vorgabe selbst mitzuschicken (siehe home_write()). Das
    Home weiss davon; das Dock und der Starter, die "Zum Home
    hinzufuegen" ebenfalls anbieten sollen, muessten es lernen. Ein
    Unterbefehl weiss es fuer alle drei.

    `add` und `remove` nehmen einen NAMEN und keine Zelle: wer ein
    Symbol von woanders aufs Home legt, sagt WELCHES und nicht WOHIN -
    den Platz sucht das Home in der ersten freien Zelle. `set` nimmt die
    ganze Liste und ist der Weg des Homes selbst, wenn dort etwas
    gezogen wurde.
    """
    target = _path(None)
    try:
        document = load(target)
    except (ValueError, OSError) as exc:
        # Auf STDERR und mit Rueckgabewert 1, wie `check`: eine
        # Oberflaeche darf eine unlesbare Datei nicht als "der Nutzer hat
        # nichts abgelegt" missverstehen, ein leeres Home zeichnen und
        # beim naechsten Anheften darueberschreiben.
        print(unreadable(target, exc), file=sys.stderr)
        return 1

    try:
        if not rest:
            json.dump(home_plan(document), sys.stdout)
            sys.stdout.write("\n")
            return 0

        if rest[0] == "set" and len(rest) == 2:
            try:
                wanted = json.loads(rest[1])
            except json.JSONDecodeError as exc:
                print(f"the icons are not JSON: {exc}", file=sys.stderr)
                return 2
            # Durch home_icons() und nicht direkt auf die Platte: was
            # hereinkommt, wird gegen DIESELBE Formpruefung gehalten wie
            # das, was schon dort steht. Ein Schreiber, der an ihr
            # vorbeikaeme, koennte eine Datei hinterlassen, die der
            # naechste Lesevorgang ablehnt - und dann waere das Home
            # leer, ohne dass jemand etwas geloescht hat.
            #
            # EIGENER FANG, UND DAS IST KEIN SCHMUCK: die Klage ueber das
            # ARGUMENT darf nicht in unreadable() landen. Die sagt "diese
            # Datei ist kaputt, repariere sie oder raeume sie weg" - ueber
            # eine Datei, die vollkommen in Ordnung ist. Der Nutzer suchte
            # den Fehler an der falschen Stelle, und die Anweisung, die
            # Datei wegzuraeumen, kostete ihn alle seine Einstellungen.
            try:
                icons = home_icons({HOME: {HOME_ICONS: wanted}})
            except UnusableSettings as problem:
                print(f"these icons cannot be written: {problem}",
                      file=sys.stderr)
                return 2
            if icons is None:
                print("the icons are null; pass an array, empty if the Home "
                      "should carry nothing", file=sys.stderr)
                return 2

        elif rest[0] in ("add", "remove") and len(rest) == 2:
            name = rest[1]
            # Von der WIRKSAMEN Liste aus und nicht von der rohen: wer
            # heute etwas hinzufuegt, will die Anwendungen behalten, die
            # er gerade sieht. Von der rohen Liste aus verschwaende alles,
            # was home_effective() gerade erst angehaengt hat - beim
            # naechsten Speichern waere es abgewaehlt.
            icons = list(home_plan(document)["icons"])
            if rest[0] == "add":
                if any(entry[HOME_NAME] == name for entry in icons):
                    # Kein Fehler: zweimal anheften ist keine Klage wert,
                    # und ein Rueckgabewert ungleich 0 liesse ein Menue
                    # eine Fehlermeldung zeigen, wo nichts fehlt.
                    return 0
                icons.append({HOME_NAME: name})
            else:
                icons = [entry for entry in icons
                         if entry[HOME_NAME] != name]
        else:
            print(USAGE, file=sys.stderr)
            return 2

        merge(home_write(document, icons), target)
    except (ValueError, OSError) as exc:
        print(f"{unreadable(target, exc)}\nNothing was changed.",
              file=sys.stderr)
        return 1
    return 0


def _dock_command(rest: list[str]) -> int:
    """`settings.py dock [add <name> | remove <name>]`.

    DREI UNTERBEFEHLE UND NICHT VIER: es gibt kein `set`. Die
    Reihenfolge der Anheftungen ist ein Bedienelement der Seite
    "Leiste", und die schreibt das Einstellungsfenster ueber
    model.Draft.sections(). Ein zweiter Weg, die GANZE Liste zu setzen,
    waere ein zweiter Weg an derselben Stelle - `add` und `remove` sind
    das, was ein Menue braucht, und mehr braucht ein Menue nicht.

    LESEN, RECHNEN, SCHREIBEN - IN EINEM PROZESS, UND DAS IST DER PUNKT
        bar.dock_pins ist eine ERSATZliste: anheften heisst lesen,
        anhaengen, ganz zurueckschreiben. Bis zum 21.08.2026 tat das
        jeder Aufrufer selbst, und jeder musste dabei an dieselben zwei
        Dinge denken - zuerst lesen (sonst nimmt er eine fremde
        Aenderung still zurueck) und bei einem fehlgeschlagenen
        Lesevorgang gar nichts schreiben (sonst loescht er dem Nutzer
        jedes Symbol, das er je angeheftet hat). Zwei Aufrufer taten es;
        ein dritter kam dazu, ein vierter waere gefolgt.

        Hier ist es eine Funktion. Ein Lesevorgang, der nicht geht, ist
        eine Ausnahme aus load(), und die faellt unten in denselben
        Fang, der auch merge() abfaengt - geschrieben wird dann nichts,
        und der Rueckgabewert sagt es.

    `add` und `remove` nehmen einen NAMEN, also genau das, was
    bar.dock_pins traegt (siehe den Kopf bei BAR_BASELINE, "warum ein
    zweiter Schluessel und nicht ein Objekt in dock_pins").
    """
    target = _path(None)
    try:
        document = load(target)
    except (ValueError, OSError) as exc:
        # Auf STDERR und mit Rueckgabewert 1, wie `check` und wie
        # `home`: eine Oberflaeche darf eine unlesbare Datei nicht als
        # "der Nutzer hat nichts angeheftet" missverstehen, ein leeres
        # Dock zeichnen und beim naechsten Anheften darueberschreiben.
        print(unreadable(target, exc), file=sys.stderr)
        return 1

    try:
        if not rest:
            json.dump(dock_plan(document), sys.stdout)
            sys.stdout.write("\n")
            return 0

        if rest[0] in ("add", "remove") and len(rest) == 2:
            name = rest[1]
            # Von der WIRKSAMEN Liste aus und nicht von der rohen -
            # dieselbe Begruendung wie bei `home add`: wer heute etwas
            # anheftet, will die Symbole behalten, die er gerade sieht.
            # Von der rohen Liste aus verschwaende alles, was
            # dock_effective() gerade erst angehaengt hat.
            pins = list(dock_plan(document)["pins"])
            if rest[0] == "add":
                if name in pins:
                    # Kein Fehler - siehe USAGE. Ein Rueckgabewert
                    # ungleich 0 liesse ein Menue eine Fehlermeldung
                    # zeigen, wo nichts fehlt.
                    return 0
                pins.append(name)
            else:
                if name not in pins:
                    return 0
                pins = [pin for pin in pins if pin != name]
        else:
            print(USAGE, file=sys.stderr)
            return 2

        merge(dock_write(document, pins), target)
    except (ValueError, OSError) as exc:
        print(f"{unreadable(target, exc)}\nNothing was changed.",
              file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """The entry point for a caller that is not Python.

    Deliberately not a second copy of anything: it parses one argument
    and calls load() or merge(). zepos-settings stays the command a
    PERSON types - it takes a dotted key and one value, which is the
    wrong shape both for a dialog handing over a whole section and for a
    generator asking one question before it starts.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv in (["-h"], ["--help"]):
        print(USAGE)
        return 0

    if argv == ["check"]:
        target = _path(None)
        try:
            document = load(target)
        except (ValueError, OSError) as exc:
            print(unreadable(target, exc), file=sys.stderr)
            return 1
        # Und die Abschnitte, die eine eigene Form haben. Der Leisten-
        # Abschnitt ist der erste davon, und er faellt genau hier auf:
        # `zepos-settings set bar.modules_right '"tray"'` schreibt eine
        # Zeichenkette, die Datei bleibt gueltiges JSON, und ohne diese
        # Zeilen erfuehre der Nutzer es an einer Leiste, auf der ein
        # Modul fehlt.
        # Und seit dem 20.08.2026 das Home daneben. Es steht in DERSELBEN
        # Zeile und nicht in einem zweiten `check`, weil der Nutzer eine
        # Datei repariert und nicht zwei: wer beide Abschnitte
        # danebengeschrieben hat, soll das in einem Durchgang erfahren.
        problems = check_bar(document) + check_home(document)
        for problem in problems:
            print(f"{target}: {problem}", file=sys.stderr)
        return 1 if problems else 0

    if argv and argv[0] == "home":
        return _home_command(argv[1:])

    # Und das Dock daneben, seit dem 21.08.2026. In derselben Form und
    # aus demselben Grund: drei Rechtsklick-Menues aendern diese Liste,
    # zwei davon sind nicht in Python geschrieben.
    if argv and argv[0] == "dock":
        return _dock_command(argv[1:])

    if len(argv) != 2 or argv[0] != "merge":
        print(USAGE, file=sys.stderr)
        return 2

    try:
        sections = json.loads(argv[1])
    except json.JSONDecodeError as exc:
        print(f"the sections to merge are not JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(sections, dict):
        print(f"the sections to merge are a JSON {_json_type(sections)}, not "
              f"an object of top-level sections, e.g. "
              f"'{{\"vpn\": {{\"server\": \"gw.example.org\"}}}}'",
              file=sys.stderr)
        return 2

    target = _path(None)
    try:
        merge(sections, target)
    except (ValueError, OSError) as exc:
        # Named in full, and with what was NOT done. A dialog reports
        # this back to the user, who has no other way to learn that the
        # setting they just changed never reached the disk.
        print(f"{unreadable(target, exc)}\nNothing was changed.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
