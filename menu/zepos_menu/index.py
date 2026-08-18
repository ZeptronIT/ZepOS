# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Zeilen von `--show all`: Anwendungen UND jede Taste dieser Sitzung.

WOZU, UND ES HAT EIN DATUM
    Am 11.08.2026 hat ein Mensch das gebaute System benutzt und gemeldet,
    das Bildschirmfoto-Werkzeug fehle. Es fehlte nicht: grim, slurp und
    satty lagen auf der Platte, SUPER+S rief sie, und er hat es nicht
    gefunden. Fuer einen Nutzer ist "vorhanden, aber unauffindbar"
    dasselbe wie "fehlt".

    Der Anwendungsstarter konnte ihm dabei nicht helfen. Er kennt
    .desktop-Dateien, und ein Bildschirmfoto ist keine Anwendung, sondern
    eine Taste. Genau diese Luecke schliesst diese Betriebsart: wer
    "bild" tippt, findet

        Bildschirm: Bildschirmfoto vom gewaehlten Bereich    SUPER + S

    kann es mit Enter ausloesen - das ist die Haelfte "zusaetzlich zu den
    keybinds", die der Nutzer ausdruecklich verlangt hat - und weiss beim
    naechsten Mal die Taste.

WOHER DIE AKTIONEN KOMMEN, UND WOHER AUSDRUECKLICH NICHT
    Aus `keybinds.py --json`, also aus der Hyprland-Konfiguration, die
    auf dieser Maschine IN PLACE liegt. Nicht aus einer Liste in diesem
    Paket: eine solche Liste waere die dritte gewesen, und die zwei, die
    es schon gab, haben beide gelogen (siehe src/keybinds.py).

    Der Aufruf ist ein Unterprozess und kein Import, obwohl beide Pakete
    Python sind. zepos-menu darf nicht davon abhaengen, WIE zepos-config
    seine Module anordnet - `--json` ist die eine Schnittstelle, die auch
    die Ueberlagerung in AGS benutzt, und die ist GJS und koennte gar
    nicht importieren.

WAS HIER NICHT DRINSTEHT: DIE EINSTELLUNGEN
    Naheliegend waere eine dritte Quelle aus settings.defaults() - 19
    Schluessel, alle ableitbar, kein Nachtragen noetig. Sie fehlt mit
    Absicht: `zepos-settings` ist ein Befehl, der einen Wert AUSGIBT und
    zum Aendern einen zweiten braucht. Eine Zeile in diesem Fenster, die
    beim Auswaehlen einen Wert in ein Terminal schreibt, das sich sofort
    wieder schliesst, waere ein Bedienelement, hinter dem sichtbar nichts
    passiert - genau die Fehlerklasse, gegen die diese ganze Aenderung
    gebaut ist.

    Die Einstellungen kommen trotzdem in dieses Fenster, und zwar ohne
    dass hier etwas nachgetragen werden muss: sobald eine
    Einstellungsanwendung eine .desktop-Datei ausliefert, steht sie unter
    den Anwendungen. Das ist die Ableitung aus dem, was da ist.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .entries import Entry

# Wo zepos-config seine Module hinlegt, und die Variable, die das
# umbiegt. BEIDE stehen auch in src/paths.py, und das ist eine bewusste
# Doppelung ueber eine Paketgrenze hinweg: zepos-menu importiert nichts
# aus zepos-config (siehe Kopf), kann den Pfad also nicht von dort
# erfragen. tests/menu/test_index.py haelt die beiden Namen gegeneinander
# und faellt um, sobald einer von ihnen wandert.
SYSTEM_ROOT = Path("/usr/share/zepos")
SYSTEM_ROOT_ENV = "ZEPOS_SYSTEM_ROOT"
READER = "keybinds.py"

# Der Praefix, unter dem eine Aktion im Zaehlwerk steht. Ohne ihn koennte
# eine Desktop-Kennung mit demselben Text kollidieren, und das Zaehlwerk
# schriebe die Haeufigkeit der einen auf die andere.
ACTION_PREFIX = "aktion:"

# Wie lange auf den Leser gewartet wird. Er liest vier Dateien und
# rechnet; braucht er laenger als das, stimmt etwas anderes nicht, und
# ein Starter, der auf eine Taste hin nicht aufgeht, ist schlimmer als
# einer, der ohne die Aktionen aufgeht.
TIMEOUT_SECONDS = 5


def reader_path() -> Path:
    override = os.environ.get(SYSTEM_ROOT_ENV)
    return (Path(override) if override else SYSTEM_ROOT) / READER


def read_actions(runner=None) -> list[dict]:
    """Die Gruppen aus `keybinds.py --json`, oder gar keine.

    Gar keine ist kein Fehler dieses Fensters: auf einer Maschine ohne
    zepos-config gibt es keine erzeugte Hyprland-Konfiguration, ueber die
    etwas zu sagen waere. Das Fenster geht dann mit den Anwendungen auf,
    was genau das alte `--show drun` ist.

    Gemeldet wird es trotzdem NICHT auf stderr: diese Betriebsart haengt
    an SUPER+SPACE, und eine Warnung bei jedem Tastendruck ist eine
    Warnung, die niemand mehr liest.
    """
    runner = runner or subprocess.run
    reader = reader_path()
    if not reader.is_file():
        return []
    try:
        # sys.executable und nicht "python3": der Leser braucht nur die
        # Standardbibliothek, also ist der Interpreter, der dieses
        # Fenster gerade ausfuehrt, mit Sicherheit einer, der ihn laden
        # kann. Ein Name aus dem PATH waere dagegen eine Annahme ueber
        # eine Umgebung, die dieses Programm nicht setzt - und ein
        # Starter, der auf einem PATH ohne python3 die halbe Liste
        # verliert, verliert sie lautlos.
        result = runner([sys.executable, str(reader), "--json"],
                        capture_output=True, text=True,
                        timeout=TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    try:
        groups = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return [group for group in groups if isinstance(group, dict)]


def action_entries(groups) -> tuple[list[Entry], dict[str, str]]:
    """Die Zeilen und das, was jede von ihnen ausfuehrt.

    Dieselbe Form, die apps.desktop_entries() hat - Zeilen und eine
    Zuordnung daneben -, und aus demselben Grund: was eine Zeile TUT,
    gehoert nicht in die Zeile. Sonst stuende eine Shell-Zeile in dem
    Feld, das bei --dmenu nach stdout geht.

    Die Gruppe steht vorn im Text und nicht in einer eigenen Spalte. Sie
    ist die zweite Haelfte der Suche: die Lautstaerketasten heissen
    "Lauter" und "Leiser", und wer "ton" tippt, findet sie nur, wenn die
    Gruppe im Text steht.
    """
    entries: list[Entry] = []
    commands: dict[str, str] = {}

    for group in groups:
        name = str(group.get("group") or "")
        for binding in group.get("bindings") or []:
            if not isinstance(binding, dict):
                continue
            chord = str(binding.get("chord") or "")
            description = str(binding.get("description") or "")
            run = str(binding.get("run") or "")
            if not chord or not description or not run:
                continue
            key = f"{ACTION_PREFIX}{name}/{chord}"
            # Die erste Bindung einer Taste gewinnt. Eine zweite mit
            # derselben Taste gibt es in einer Hyprland-Konfiguration
            # durchaus - profile-keybinds.conf ueberschreibt eine Zeile
            # aus hyprland.conf -, und zwei Zeilen mit identischem
            # Schluessel waeren zwei Zeilen, zwischen denen niemand
            # waehlen kann.
            if key in commands:
                continue
            commands[key] = run
            entries.append(Entry(
                label=f"{name}: {description}" if name else description,
                value=key, hint=chord))

    return entries, commands
