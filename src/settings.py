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
    from . import sizes
    from .paths import system_root, user_root
except ImportError:
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
              shipped: list[str] | None) -> tuple[list[str], Discarded]:
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
    """
    if chosen is None:
        return (list(shipped) if shipped is not None else [], [])

    kept: list[str] = []
    discarded: list[tuple[str, str]] = []
    for name in chosen:
        if name in kept:
            discarded.append((name, BAR_REPEATED))
        elif placeable is not None and name not in placeable:
            discarded.append((name, BAR_UNKNOWN))
        else:
            kept.append(name)
    return kept, discarded


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
    """
    problems = []
    for key in BAR_KEYS:
        try:
            bar_choice(document, key)
        except UnusableSettings as problem:
            problems.append(str(problem))
    return problems


USAGE = """usage: settings.py check
       settings.py merge '<json object>'

check reads the user settings and reports what is wrong with them,
saying nothing when there is nothing to say. A file that is not there is
not a fault: a fresh installation has none.

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
        problems = check_bar(document)
        for problem in problems:
            print(f"{target}: {problem}", file=sys.stderr)
        return 1 if problems else 0

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
