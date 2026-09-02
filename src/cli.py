# SPDX-License-Identifier: GPL-3.0-or-later
"""What the three commands in bin/ do, and how they find this file.

HOW A COMMAND FINDS ITS MODULES
    The package splits the commands from the code they run:

        /usr/bin/zepos-generate        the command
        /usr/share/zepos/*.py          everything it imports

    so a command cannot find its modules by looking next to itself - one
    directory up from /usr/bin is /usr, and the answer is somewhere else
    entirely. In a checkout the opposite is true: src/bin/zepos-generate
    has src/ directly above it and there is no installed package at all,
    quite possibly not even on the machine.

    Each command therefore resolves ONE directory before it imports
    anything, in this order:

      1. the environment variable paths.SYSTEM_ROOT_ENV names, if it is
         set - written out there and nowhere else, so there is one place
         to read it from. Packaging tools and the test suite use it to
         point at a tree that is neither of the two below; paths.py's
         header explains why it is not end-user configuration.
      2. the directory above the command, if this file is in it. That is
         the checkout, and it is checked by looking rather than by
         guessing which of the two situations we are in.
      3. /usr/share/zepos, the installed location.

    That resolution is four lines at the top of each command, because
    nothing can be imported until it has run - there is no earlier place
    to put it. Everything else lives here, including the failure message
    for the case where none of the three answers holds: a half-installed
    package must not greet the user with ModuleNotFoundError, which names
    a module rather than the directory that is actually missing.

WHAT IS AND IS NOT REIMPLEMENTED HERE
    Nothing that already exists. `zepos-generate` runs
    generate_config.sh, which stages, validates and publishes; a second
    generator would be a second set of bugs. `--monitors` renders the
    layout monitors.py derives, so the rule that decides which workspace
    lives on which screen exists once. `zepos-settings` reads and writes
    through settings.py, so the atomic 0600 write and the schema version
    are not repeated either.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import doctor
import monitors
import settings
import theme
import update
# Nur fuer new_connection_id(): eine Kennung wird an EINER Stelle
# vergeben, sonst kollidiert die Befehlszeile irgendwann mit dem Fenster.
import vpn
from paths import user_root

# Named absolutely, so finding the interpreter never depends on PATH -
# and the generated artifacts that call these commands run with a PATH
# somebody else set.
BASH = "/bin/bash"

GENERATOR = "generate_config.sh"

Runner = Callable[..., "subprocess.CompletedProcess"]


# --------------------------------------------------------------------
# zepos-generate
# --------------------------------------------------------------------

def generate(argv: list[str], *, runner: Runner | None = None) -> int:
    """Run the generator, or write the monitor layout.

    Everything but --monitors is handed to generate_config.sh unchanged,
    including no arguments at all: it already knows every target name and
    prints its own usage.

    --help is turned into exactly that empty argument list rather than
    answered here. The list of targets is the set of templates present on
    this machine, user overrides included, and a usage text written here
    would be a second one that goes out of date the first time somebody
    adds a template.
    """
    if argv in (["-h"], ["--help"]):
        argv = []

    if argv and argv[0] == "--monitors":
        if len(argv) > 1:
            print("usage: zepos-generate --monitors\n"
                  "       zepos-generate <target> [<target> ...]",
                  file=sys.stderr)
            return 2
        # monitors.py's own entry point, so that a failed detection still
        # writes NOTHING to stdout: the caller appends this to the file
        # Hyprland sources, and half a block there is a config error.
        return monitors.main([])

    runner = runner or subprocess.run
    generator = Path(__file__).resolve().parent / GENERATOR
    if not generator.is_file():
        print(f"{generator} is missing - this is a broken installation, "
              f"not a configuration problem", file=sys.stderr)
        return 2

    return runner([BASH, str(generator), *argv]).returncode


# --------------------------------------------------------------------
# zepos-settings
# --------------------------------------------------------------------

USAGE = """usage: zepos-settings get [<key>]
       zepos-settings set <key> <value>

<key> is a dotted path into the settings document, e.g. weather.location
or vpn.connection_name. <value> is read as JSON when it parses as JSON
(["10.0.0.0/8"], 30, true) and as plain text otherwise.

update.* gehoert der Maschine und nicht diesem Konto: die Werte liegen
unter /etc/zepos/update.json, lesen darf sie jeder, schreiben nur root.
`zepos-update --help` zaehlt sie auf.

`theme` gehoert der Maschine aus demselben Grund - der Anmeldebildschirm
steht vor jedem Konto und muss dasselbe Thema tragen. Der Name liegt in
/etc/zepos/theme. `zepos-settings get theme` nennt das eingestellte und
alle, die es gibt."""

# Der eine Praefix, der nicht in das Dokument dieses Benutzers geht.
#
# WARUM DIESE UMLEITUNG UND NICHT EIN ABSCHNITT IN user-settings.json
#     Der Aktualisierer laeuft als Systemdienst, moeglicherweise bevor
#     sich jemand angemeldet hat. Ein Abschnitt in einem Heimatverzeich-
#     nis waere fuer ihn nicht auffindbar (welches Konto?), nicht lesbar
#     (0600) und auf einer Maschine mit zwei Konten zweideutig. Der Kopf
#     von update.py fuehrt das aus.
#
#     Die ALTERNATIVE waere gewesen, update.* einfach in
#     user-settings.json zu schreiben und den Dienst raten zu lassen. Das
#     ist die Reglertabelle, die kein erzeugtes Byte veraendert: der
#     Nutzer setzt etwas, der Befehl sagt nichts, und die Maschine
#     aktualisiert sich weiter wie vorher.
UPDATE_PREFIX = "update."

# Der zweite Name, der nicht in das Dokument dieses Benutzers geht, und
# der einzige ohne Punkt dahinter: er hat keine Unterschluessel.
#
# WARUM ER DER MASCHINE GEHOERT
#     src/bin/zepos-greeter laeuft als Benutzer "greeter", bevor
#     irgendjemand angemeldet ist. Er kann die Einstellungsdatei eines
#     Kontos nicht lesen, weil es zu diesem Zeitpunkt kein Konto gibt,
#     das gemeint waere. Damit die Anmeldemaske dasselbe Thema tragen
#     kann wie der Schreibtisch - genau das war die Forderung vom
#     12.08.2026 -, muss der Name dort stehen, wo die Maschine ihre
#     Entscheidungen hinschreibt. Der Kopf von src/theme.py fuehrt es
#     aus.
#
#     Die siebzig einzelnen FARBEN bleiben dabei diesem Konto. Ein
#     Thema ist die Palette, unter der die eigenen Aenderungen liegen,
#     und nicht statt ihrer.
THEME_KEY = "theme"


def settings_command(argv: list[str]) -> int:
    if argv in (["-h"], ["--help"]):
        # On stdout and with a zero status: asking for help is not a
        # mistake, and a user piping this into a pager sees nothing when
        # it goes to stderr.
        print(USAGE)
        return 0
    if not argv or argv[0] not in ("get", "set"):
        print(USAGE, file=sys.stderr)
        return 2

    command, arguments = argv[0], argv[1:]
    if command == "get" and len(arguments) > 1:
        print(USAGE, file=sys.stderr)
        return 2
    if command == "set" and len(arguments) != 2:
        print(USAGE, file=sys.stderr)
        return 2

    if arguments and arguments[0].startswith(UPDATE_PREFIX):
        return _update_setting(command, arguments)
    if arguments and arguments[0] == THEME_KEY:
        return _theme_setting(command, arguments)

    try:
        document = settings.load()
    except (ValueError, OSError) as exc:
        # The wording belongs to settings.py, which owns the file and the
        # schema. Four callers say this - that command line, this one,
        # the style settings manager and the generator - and four
        # wordings for one condition read as four different conditions.
        print(f"{settings.unreadable(settings_path(), exc)}\n"
              f"Nothing was changed.", file=sys.stderr)
        return 1

    if command == "get":
        return _get(document, arguments[0] if arguments else None)
    return _set(document, arguments[0], arguments[1])


def settings_path() -> Path:
    """The file settings.py reads and writes, named for a message."""
    return user_root() / settings.FILENAME


def _get(document: dict[str, Any], key: str | None) -> int:
    if key is None:
        print(json.dumps(document, indent=2))
        return 0

    # DIESELBE UMLEITUNG WIE IM SCHREIBWEG - NACHGETRAGEN 22.08.2026
    #
    #     Der Absatz ueber _vpn_target() sagt seit dem 22.08.2026,
    #     `vpn.server` sei "dieselbe Auskunft, die get_vpn_setting() und
    #     der Erzeuger geben". Fuer `set` stimmte das, fuer `get` nicht:
    #     die Umleitung stand nur in _set(). GEMESSEN an einer Datei mit
    #     zwei Verbindungen -
    #
    #         set vpn.server vpn.example.org   -> geschrieben, Rueckgabe 0
    #         get vpn.server                   -> "no such setting: vpn.server"
    #
    #     - also ein Programm, das seinen eigenen Wert nicht wiederfindet.
    #     Kein Test deckte es, weil es zu `get vpn.*` ueberhaupt keinen
    #     gab.
    parts = _vpn_target(document, key.split(".")) or key.split(".")

    value: Any = document
    for part in parts:
        # Eine Ziffer laeuft in eine Liste hinein - dieselbe Regel wie in
        # _holds() und aus demselben Grund: `vpn.connections.0.server`
        # ist seit dem 22.08.2026 ein gueltiger Weg, und die Umleitung
        # oben erzeugt genau so einen.
        if isinstance(value, list) and part.isdigit():
            index = int(part)
            if index >= len(value):
                print(f"no such setting: {key}", file=sys.stderr)
                return 1
            value = value[index]
            continue
        if not isinstance(value, dict) or part not in value:
            print(f"no such setting: {key}", file=sys.stderr)
            return 1
        value = value[part]

    print(value if isinstance(value, str) else json.dumps(value))
    return 0


# `vpn.<etwas>` MEINT DIE GEWAEHLTE VERBINDUNG - SEIT DEM 22.08.2026
#
#     `vpn` traegt seit heute eine Liste (`connections`) und die Kennung
#     der gewaehlten (`active`). Damit gaebe es `vpn.server` als Pfad
#     nicht mehr, und `zepos-settings set vpn.server ...` - der Weg, auf
#     dem eine frische Installation ueberhaupt erst einen Zugang bekommt
#     - haette "no such setting" geantwortet.
#
#     Das waere ein weggefallener Pfad und damit genau das, was dieser
#     Umbau nicht tun darf. `vpn.server` bleibt deshalb `vpn.server` und
#     landet in der GEWAEHLTEN Verbindung - dieselbe Auskunft, die
#     get_vpn_setting() und der Erzeuger geben.
#
#     Die zwei Schluessel des Abschnitts selbst (`active`,
#     `connections`) bleiben ausdruecklich erreichbar: wer die Liste
#     als Ganzes setzen will, kann das, und `vpn.active` ist der Weg,
#     die gewaehlte Verbindung von der Befehlszeile aus zu wechseln.
VPN_SECTION_KEYS = ("active", "connections")

# Der Abschnittsname, einmal benannt statt viermal getippt - dieselbe
# Ueberlegung, aus der settings.py VPN/VPN_ACTIVE/VPN_CONNECTIONS fuehrt.
VPN_SECTION = settings.VPN


def _erste_verbindung(document: dict[str, Any]) -> dict[str, Any]:
    """Die eine Verbindung, die `set vpn.<etwas>` vorfinden muss.

    AUS default_connection() UND MIT EIGENER KENNUNG
        Aus der Vorgabentabelle gebaut und nicht getippt: sie ist seit
        dem 01.09.2026 die einzige Stelle, an der steht, welche
        Schluessel eine Verbindung hat (siehe ihren Kopf in
        src/settings.py). Eine hier abgeschriebene Menge waere genau
        die fuenfte, die dieser Umbau abgeschafft hat.

        Die Kennung kommt aus vpn.new_connection_id() und nicht aus
        settings.MIGRATED_ID: "c1" gehoert der Wanderung und darf nur
        einmal vergeben werden - eine zweite Verbindung mit derselben
        Kennung liesse Schalter und Schluesseldateien auf die falsche
        zeigen.

    `active` ZEIGT DANACH AUF SIE
        Eine Verbindung, die zwar in der Liste steht, aber nicht
        gewaehlt ist, sieht jeder Leser ueber vpn.connection() - der
        antwortet mit der ERSTEN, wenn die gesuchte Kennung fehlt. Das
        haette hier funktioniert und waere trotzdem falsch: der Nutzer
        hat gerade seinen einzigen Zugang eingerichtet, und der soll
        auch der gewaehlte sein.
    """
    section = document.get(VPN_SECTION)
    if not isinstance(section, dict):
        section = {settings.VPN_ACTIVE: "", settings.VPN_CONNECTIONS: []}
        document[VPN_SECTION] = section
    entries = section.get(settings.VPN_CONNECTIONS)
    if not isinstance(entries, list):
        entries = []
        section[settings.VPN_CONNECTIONS] = entries

    neu = dict(settings.default_connection(),
               **{settings.VPN_ID: vpn.new_connection_id()})
    entries.append(neu)
    section[settings.VPN_ACTIVE] = neu[settings.VPN_ID]
    return neu


def _vpn_target(document: dict[str, Any], parts: list[str]) -> list[str] | None:
    """`["vpn", "server"]` -> `["vpn", "connections", "0", "server"]`.

    Antwortet None, wenn der Pfad kein VPN-Verbindungspfad ist - dann
    gilt die gewoehnliche Pruefung darunter unveraendert.
    """
    if len(parts) < 2 or parts[0] != "vpn" or parts[1] in VPN_SECTION_KEYS:
        return None
    section = document.get("vpn")
    if not isinstance(section, dict):
        return None
    entries = section.get("connections")
    if not isinstance(entries, list) or not entries:
        return None
    gesucht = section.get("active")
    index = next((i for i, e in enumerate(entries)
                  if isinstance(e, dict) and e.get("id") == gesucht), 0)
    return ["vpn", "connections", str(index)] + parts[1:]


def _set(document: dict[str, Any], key: str, raw: str) -> int:
    parts = key.split(".")

    # Known to the schema OR already in the file. Both are needed: the
    # installer writes a document holding only the two questions it
    # asked, so a fresh installation has no "vpn" section at all and
    # checking the file alone would refuse vpn.server on exactly the
    # machines where it has to be set first. Checking the schema alone
    # would refuse the keys the style layer and the installer put there,
    # which are not in settings.defaults().
    # Ein VPN-Pfad zeigt auf die gewaehlte Verbindung; gibt es noch
    # keine, wird sie ANGELEGT, damit `set vpn.server` auf einer
    # frischen Installation weiter geht.
    #
    # HIER STAND BIS ZUM 01.09.2026 EIN RUECKFALL, DER NUR DIE PRUEFUNG
    # UMLEITETE UND NICHT DEN SCHREIBWEG
    #
    #     `_holds({"vpn": default_connection()}, parts)` liess den Pfad
    #     durch, `parts` blieb aber `["vpn", "server"]`. Geschrieben
    #     wurde der Wert damit als Geschwister von `active` und
    #     `connections` IN DEN ABSCHNITT - und der Abschnitt ist seit
    #     dem 22.08.2026 keine Verbindung mehr, sondern eine Liste von
    #     Verbindungen.
    #
    #     GEMESSEN am 01.09.2026 an einem frischen Benutzerverzeichnis
    #     ohne Einstellungsdatei:
    #
    #         set vpn.server gw.example.org   -> 0
    #         get vpn.server                  -> gw.example.org
    #         vpn.connection(load())          -> {}
    #
    #     Derselbe Schluessel mit zwei Antworten, je nachdem wer fragt.
    #     `get` las den verlegten Wert ueber denselben Rueckfall zurueck
    #     und sah darum richtig aus, waehrend der Erzeuger, das
    #     Verbindungsskript und das Fenster einen leeren Server sahen.
    #     Genau die leise Art zu scheitern, vor der _unknown() weiter
    #     unten woertlich warnt.
    #
    #     Angelegt wird nur, wenn der Pfad WIRKLICH ein Schluessel einer
    #     Verbindung ist - `set vpn.tippfehler x` legt nichts an und
    #     bleibt "no such setting". Und nur beim SCHREIBEN: _get() legt
    #     nichts an, ein Lesen darf die Datei nicht veraendern.
    umgeleitet = _vpn_target(document, parts)
    if (umgeleitet is None
            and len(parts) >= 2
            and parts[0] == VPN_SECTION
            and parts[1] not in VPN_SECTION_KEYS
            and _holds({"vpn": settings.default_connection()}, parts)):
        _erste_verbindung(document)
        umgeleitet = _vpn_target(document, parts)

    if umgeleitet is not None:
        if not (_holds(document, umgeleitet)
                or _holds({"vpn": settings.default_connection()}, parts)):
            return _unknown(key)
        parts = umgeleitet
    elif not (_holds(document, parts)
              or _holds({"vpn": settings.default_connection()}, parts)
              or _holds(settings.defaults(), parts)):
        # Refused rather than created. A mistyped key that is written and
        # then read by nobody is the quietest failure this program has:
        # the user changed a setting, the command said "saved", and
        # nothing about the machine changed.
        return _unknown(key)

    section: Any = document
    for part in parts[:-1]:
        if isinstance(section, list):
            section = section[int(part)]
            continue
        if not isinstance(section.get(part), (dict, list)):
            section[part] = {}
        section = section[part]

    try:
        value: Any = json.loads(raw)
    except json.JSONDecodeError:
        # A location, a connection name, a hostname. Quoting those as
        # JSON on the command line would be a trap nobody expects.
        value = raw

    section[parts[-1]] = value
    # The whole document goes back, not just the key: the installer
    # writes plugins.enabled into this same file and the style layer
    # keeps widget sizes and colours in it. Writing only what this
    # command knows about would delete the rest.
    settings.save(document)
    return 0


def _holds(document: dict[str, Any], parts: list[str]) -> bool:
    """Whether a dotted key names something in this document."""
    section: Any = document
    for part in parts[:-1]:
        # Eine Ziffer laeuft in eine Liste hinein - `vpn.connections.0`
        # ist seit dem 22.08.2026 ein gueltiger Weg, und ohne diesen
        # Zweig endete jeder VPN-Pfad hier an der Liste.
        if isinstance(section, list) and part.isdigit():
            index = int(part)
            if index >= len(section):
                return False
            section = section[index]
            continue
        if not isinstance(section, dict) or part not in section:
            return False
        section = section[part]
        if not isinstance(section, (dict, list)):
            return False
    if isinstance(section, list) and parts[-1].isdigit():
        return int(parts[-1]) < len(section)
    return isinstance(section, dict) and parts[-1] in section


def _unknown(key: str) -> int:
    print(f"no such setting: {key}\n"
          f"Run `zepos-settings get` to see the settings that exist.",
          file=sys.stderr)
    return 1


def _update_setting(command: str, arguments: list[str]) -> int:
    """`zepos-settings get/set update.*`, an der Maschinendatei.

    Und danach update.apply(), was der eigentliche Punkt ist - auf der
    Befehlszeile heisst dasselbe `zepos-update --apply-schedule`: die
    Datei allein waere ein Wert in einem JSON. Erst der Aufruf schreibt
    die Zeitgeber-Ergaenzung und sagt systemd Bescheid - ohne ihn wuerde
    `zepos-settings set update.enabled false` melden, dass es
    geschrieben hat, und die Maschine aktualisierte sich am naechsten
    Morgen weiter.
    """
    key = arguments[0][len(UPDATE_PREFIX):]
    try:
        config = update.load()
    except (ValueError, OSError) as exc:
        print(f"{exc}\nNothing was changed.", file=sys.stderr)
        return 1

    if command == "get":
        # Ein leeres `update.` druckt das ganze Dokument, wie `get` ohne
        # Schluessel es fuer das Benutzerdokument tut.
        return _get(config, key or None)

    try:
        config = update.set_value(key, arguments[1])
    except update.UnusableConfig as exc:
        print(f"{exc}\n`zepos-update --help` nennt jede Einstellung, die "
              f"es gibt.", file=sys.stderr)
        return 1
    except PermissionError:
        # Der haeufigste Fehlschlag, und der einzige, aus dem der Nutzer
        # ohne Hilfe nicht herausfindet: /etc/zepos gehoert root.
        print(f"{update.config_path()} kann nicht geschrieben werden: "
              f"diese Einstellung gehoert der Maschine.\n"
              f"    sudo zepos-settings set {arguments[0]} {arguments[1]}",
              file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"{update.config_path()}: {exc}\nNothing was changed.",
              file=sys.stderr)
        return 1

    update.apply(config)
    return 0


def _theme_setting(command: str, arguments: list[str]) -> int:
    """`zepos-settings get/set theme`, an der Maschinendatei.

    WAS ES NICHT TUT: ERZEUGEN.
        Ein Themenwechsel bewegt jede erzeugte Datei, und das kostet
        einen vollstaendigen Lauf, der AGS beendet und neu startet -
        mitten in der Arbeit ein Eingriff, den niemand bestellt hat.
        Dieselbe Ueberlegung, die settings/zepos_settings_gui/model.py
        fuer die Groessen schon angestellt hat, und dieselbe Antwort:
        gespeichert wird sofort, angewandt wird beim naechsten
        `zepos-generate --all`. Deshalb sagt dieser Befehl es auch.

        Die Anmeldemaske ist die Ausnahme und braucht gar nichts: ihre
        Blaetter liegen alle schon unter /etc/greetd, und
        src/bin/zepos-greeter liest den Namen bei jedem Start.
    """
    if command == "get":
        current = theme.read_name()
        print(current)
        others = ", ".join(sorted(name for name in theme.THEMES
                                  if name != current))
        print(f"(auch da: {others})", file=sys.stderr)
        return 0

    try:
        written = theme.write_name(arguments[1])
    except theme.UnknownTheme as exc:
        print(f"{exc}\nNothing was changed.", file=sys.stderr)
        return 1
    except PermissionError:
        # Derselbe haeufigste Fehlschlag wie bei update.*: /etc/zepos
        # gehoert root, und dieses Thema gehoert der Maschine, weil die
        # Anmeldemaske dazugehoert.
        print(f"{theme.name_path()} kann nicht geschrieben werden: "
              f"dieses Thema gehoert der Maschine, weil der "
              f"Anmeldebildschirm dazugehoert.\n"
              f"    sudo zepos-settings set theme {arguments[1]}",
              file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"{theme.name_path()}: {exc}\nNothing was changed.",
              file=sys.stderr)
        return 1

    print(f"Thema {arguments[1]} steht in {written}.\n"
          f"Der Anmeldebildschirm zeigt es beim naechsten Mal. Der "
          f"Schreibtisch, sobald `zepos-generate --all` gelaufen ist - "
          f"spaetestens bei der naechsten Anmeldung.")
    return 0


# --------------------------------------------------------------------
# zepos-doctor
# --------------------------------------------------------------------

def doctor_command(argv: list[str]) -> int:
    return doctor.main(argv)


# --------------------------------------------------------------------
# zepos-update
# --------------------------------------------------------------------

def update_command(argv: list[str]) -> int:
    return update.main(argv)
