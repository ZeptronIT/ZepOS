# SPDX-License-Identifier: GPL-3.0-or-later
"""Was auf der Kommandozeile steht und was in der erzeugten Konfiguration.

DIE SCHALTERLISTE IST GEMESSEN, NICHT ERFUNDEN
    Am 11.08.2026 rief ZepOS wofi an sechs Stellen auf. Ausgezaehlt ueber
    `grep -rn "wofi" src/templates/` benutzten diese sechs zusammen genau
    neun Schalter:

        --show drun        hyprland-plugins-config      (Rueckfallstarter)
        --dmenu            alle fuenf Skriptstellen
        --prompt           alle fuenf Skriptstellen
        --cache-file       cliphist, network-manager, floating-windows
        --sort-order       cliphist, network-manager
        --width/--height   network-manager (drei verschiedene Groessen)
        --password         network-manager (letzter Rueckfall fuer WLAN)
        --insensitive      network-manager (Hauptmenue)

    Alle neun stehen hier, und zwar mit der Bedeutung, die die Skripte
    voraussetzen. Ein Ersatz, der einen benutzten Schalter nur
    entgegennimmt und ignoriert, macht keinen Fehler, den irgendjemand
    sieht: die Fenstergroesse ist dann eben falsch, die Reihenfolge eben
    anders, das Passwort eben lesbar. Genau solche Fehler hat dieses
    Projekt in wofis Stylesheet ueber Jahre getragen.

    Beide Schreibweisen muessen gehen: floating-window-manager schreibt
    `--cache-file=/dev/null`, cliphist schreibt `--cache-file /dev/null`,
    und network-manager mischt `--sort-order=default` mit `--width 500`.
    argparse kann beides von sich aus - allow_abbrev ist aus, damit ein
    vertipptes `--pass` nicht stillschweigend `--password` bedeutet.

WARUM EIN UNBEKANNTER SCHALTER DAS PROGRAMM BEENDET
    Weil der Aufrufer ein erzeugtes Skript ist. Ein ignoriertes
    `--passwrod` waere ein Passwortfeld, das im Klartext tippt, in einem
    Fenster, das trotzdem aufgeht - und niemand erfaehrt es. argparse
    beendet mit 2 und schreibt die Nutzungszeile; das ist laut genug, um
    beim ersten Aufruf aufzufallen.

WARUM EIN UNBEKANNTER KONFIGURATIONSSCHLUESSEL DAS PROGRAMM NICHT BEENDET
    Weil die Konfiguration erzeugt wird und der Starter die Taste ist,
    ohne die ein Desktop nicht bedienbar ist (Spec §7.4). Ein Tippfehler
    in ~/.config/zepos-menu/config darf den Starter nicht ausschalten -
    er bekommt eine Zeile auf stderr und das Fenster geht auf.
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

PROGRAM = "zepos-menu"

# Die Betriebsarten von `--show`, die in ZepOS vorkommen.
#
# wofi kannte zusaetzlich `run` (ausfuehrbare Dateien im PATH) und
# `dmenu` als Wert von --show. Beide stehen in keinem Aufruf dieses
# Projekts, und eine Betriebsart, die niemand aufruft, ist Code, den
# niemand testet. `--show run` beendet deshalb mit einer Meldung, die den
# Namen nennt, statt still in den Starter zu fallen.
#
# `all` ist am 12.08.2026 dazugekommen, aus der Beschwerde "das
# Bildschirmfoto-Werkzeug fehlt" ueber ein Werkzeug, das da war. Es zeigt
# die Anwendungen von `drun` UND jede beschriebene Tastenbindung dieser
# Sitzung, mit der Taste daneben - siehe menu/zepos_menu/index.py.
#
# `drun` bleibt und wird gebraucht: die Anwendungen allein sind das, was
# ein Starter zeigt, wenn jemand ausdruecklich nur sie will.
SHOW_MODES = ("drun", "all")

MODE_DRUN = "drun"
MODE_ALL = "all"
MODE_DMENU = "dmenu"

SORT_ORDERS = ("default", "alphabetical")
LAYERS = ("background", "bottom", "top", "overlay")


@dataclass(frozen=True)
class Options:
    """Der fertige Zustand: Konfigurationsdatei, dann Kommandozeile."""

    mode: str
    prompt: str
    width: int
    height: int
    insensitive: bool
    sort_order: str
    password: bool
    cache_file: Path
    terminal: str
    layer: str
    image_size: int
    style_sheet: Path


# Die Vorgaben, die gelten, wenn weder Datei noch Kommandozeile etwas
# sagen. Bis auf den Text der Eingabezeile sind es dieselben Werte, die
# src/templates/zepos-menu-config.template hinschreibt: eine geloeschte
# Konfiguration darf das Fenster nicht anders verhalten lassen als eine
# vorhandene, sonst ist der erste Fehlerbericht ueber etwas, das gar
# nicht kaputt ist. Der Text ist die Ausnahme, weil die Vorlage ihm das
# Lupensymbol aus der Symboldatenbank voranstellt und dieses Symbol es
# vor dem Erzeugen nirgends gibt.
DEFAULTS: dict[str, object] = {
    "show": MODE_DRUN,
    "prompt": "Suchen ...",
    "width": 1536,
    "height": 864,
    "insensitive": True,
    "sort_order": "alphabetical",
    "terminal": "kitty",
    "layer": "overlay",
    "image_size": 40,
}

_BOOLEAN_KEYS = frozenset({"insensitive"})
_INTEGER_KEYS = frozenset({"width", "height", "image_size"})


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def cache_home() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")


def default_cache_file(mode: str) -> Path:
    """Ein Zaehlwerk je Betriebsart, nicht eines fuer beide.

    Die Zaehlung ordnet haeufig Gewaehltes nach oben. Ein gemeinsamer
    Speicher wuerde die Namen der Anwendungen mit den Zeilen der
    Zwischenablage in einen Topf werfen, und die Zwischenablage liefert
    bei jedem Aufruf andere Zeilen: der Topf waechst unbegrenzt und
    ordnet nichts.
    """
    return cache_home() / PROGRAM / mode


def _boolean(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def read_config(path: Path, warn=None) -> dict[str, object]:
    """`schluessel=wert` je Zeile, eine Zeile mit `#` davor ist ein Kommentar.

    Dasselbe Format, das wofi las, weil die erzeugte Datei dasselbe
    Format hatte - und weil ein Format, das ein Mensch in einer Zeile
    korrigieren kann, fuer neun Schluessel angemessen ist.

    Nur GANZE Zeilen sind Kommentare. Ein `#` mitten in einer Zeile
    bleibt Teil des Wertes: `prompt=# Suchen` waere sonst ein leerer
    Text, und eine Farbe oder ein Zeichen, das jemand in den Text
    schreibt, verschwaende ohne Meldung.
    """
    values: dict[str, object] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values

    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            if warn:
                warn(f"{path}:{number}: keine Zuweisung: {raw.strip()}")
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key not in DEFAULTS:
            if warn:
                warn(f"{path}:{number}: unbekannter Schluessel: {key}")
            continue
        if key in _BOOLEAN_KEYS:
            values[key] = _boolean(value)
        elif key in _INTEGER_KEYS:
            try:
                values[key] = int(value)
            except ValueError:
                if warn:
                    warn(f"{path}:{number}: {key} ist keine Zahl: {value}")
        else:
            values[key] = value

    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        allow_abbrev=False,
        description="Das GTK4-Auswahlfenster von ZepOS.",
    )
    parser.add_argument("--show", metavar="MODUS",
                        help="Betriebsart; einzig 'drun' ist gebaut")
    parser.add_argument("--dmenu", action="store_true",
                        help="Zeilen von stdin lesen, gewaehlte auf stdout")
    parser.add_argument("--prompt", metavar="TEXT")
    parser.add_argument("--width", type=int, metavar="N")
    parser.add_argument("--height", type=int, metavar="N")
    parser.add_argument("--password", action="store_true",
                        help="Eingabe verdeckt darstellen")
    parser.add_argument("--insensitive", action="store_true",
                        help="Gross- und Kleinschreibung beim Filtern egal")
    parser.add_argument("--sort-order", choices=SORT_ORDERS, metavar="ORDNUNG",
                        help="default (Eingabereihenfolge) oder alphabetical")
    parser.add_argument("--cache-file", metavar="PFAD",
                        help="Zaehlwerk fuer haeufig Gewaehltes; /dev/null schaltet es ab")
    return parser


def parse(argv: list[str], warn=None) -> Options:
    """Kommandozeile ueber Konfigurationsdatei ueber Vorgabe."""
    if warn is None:
        def warn(message: str) -> None:
            print(f"{PROGRAM}: {message}", file=sys.stderr)

    arguments = build_parser().parse_args(argv)

    directory = config_home() / PROGRAM
    settings = dict(DEFAULTS)
    settings.update(read_config(directory / "config", warn))

    if arguments.dmenu:
        mode = MODE_DMENU
    else:
        show = arguments.show if arguments.show is not None else settings["show"]
        if show == MODE_DMENU:
            # `show=dmenu` in der Datei waere eine Betriebsart ohne
            # stdin - das Fenster ginge leer auf und niemand wuesste,
            # worauf es wartet.
            raise SystemExit(
                f"{PROGRAM}: dmenu ist ein Schalter, kein Wert von --show")
        if show not in SHOW_MODES:
            raise SystemExit(
                f"{PROGRAM}: --show {show} gibt es nicht; gebaut ist "
                + ", ".join(SHOW_MODES))
        mode = show

    if arguments.cache_file is not None:
        cache_file = Path(arguments.cache_file)
    else:
        cache_file = default_cache_file(mode)

    sort_order = arguments.sort_order or str(settings["sort_order"])
    if sort_order not in SORT_ORDERS:
        warn(f"unbekannte Sortierung {sort_order}; benutze "
             f"{DEFAULTS['sort_order']}")
        sort_order = str(DEFAULTS["sort_order"])

    layer = str(settings["layer"])
    if layer not in LAYERS:
        warn(f"unbekannte Ebene {layer}; benutze {DEFAULTS['layer']}")
        layer = str(DEFAULTS["layer"])

    return Options(
        mode=mode,
        prompt=arguments.prompt if arguments.prompt is not None
        else str(settings["prompt"]),
        width=arguments.width if arguments.width is not None
        else int(settings["width"]),
        height=arguments.height if arguments.height is not None
        else int(settings["height"]),
        # Der Schalter kann nur einschalten, nie ausschalten. Genau so
        # benutzt ihn network-manager-gui: die Datei sagt schon
        # insensitive=true, und der Aufruf sagt es noch einmal, weil das
        # Skript nicht wissen kann, was in der Datei steht.
        insensitive=bool(settings["insensitive"]) or arguments.insensitive,
        sort_order=sort_order,
        password=arguments.password,
        cache_file=cache_file,
        terminal=str(settings["terminal"]),
        layer=layer,
        image_size=int(settings["image_size"]),
        style_sheet=directory / "style.css",
    )
