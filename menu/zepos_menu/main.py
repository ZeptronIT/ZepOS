# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Verdrahtung: Schalter lesen, Zeilen holen, Fenster zeigen, antworten.

DIE RUECKGABEWERTE, UND WARUM SIE SO SIND
    0   es wurde etwas gewaehlt (und bei --dmenu steht es auf stdout)
    1   abgebrochen - Escape, oder das Fenster geschlossen
    2   ein Schalter, den es nicht gibt (argparse)

    1 fuer den Abbruch ist die dmenu-Ueberlieferung, und sie ist hier
    nachgeprueft ungefaehrlich: keine der fuenf aufrufenden Vorlagen
    setzt `set -e`, gemessen am 11.08.2026, und jede von ihnen erkennt
    den Abbruch ohnehin an der leeren Ausgabe (`[ -n "$auswahl" ] ||
    exit 0`). Der Rueckgabewert ist also die zusaetzliche Auskunft, nicht
    die einzige.

WARUM stdin FRUEH GELESEN WIRD UND DIE .desktop-DATEIEN SPAET
    Zwei Quellen, zwei Zeitpunkte, und beide aus einem eigenen Grund.

    stdin ist eine Pipe, und am anderen Ende steht ein Skript, das
    schreibt und wartet: `printf '%s\\n' "$drucker" | zepos-menu --dmenu`.
    Wer erst ein Fenster baut und dann liest, laesst das Fenster so lange
    leer stehen, wie der Schreiber braucht. Also vor GTK, hier.

    Die .desktop-Dateien liest der Starter dagegen erst, wenn das Fenster
    steht - siehe MenuApplication.do_activate(), wo die Messung steht,
    die diese Reihenfolge erzwungen hat.
"""
from __future__ import annotations

import sys

from . import entries as model
from . import index
from .options import MODE_ALL, MODE_DMENU, Options, parse


def main(argv: list[str] | None = None, *, on_window_shown=None) -> int:
    """Ein Durchlauf: Fenster auf, Antwort raus, Rueckgabewert.

    `on_window_shown` bekommt das fertige, gefuellte Fenster. Das ist der
    einzige Griff, den ein GTK-Fenster von aussen hat - es hat keine
    Skriptschnittstelle und keinen Weg, ihm eine Taste zu schicken - und
    tests/menu/menu_headless_child.py bedient das Fenster darueber. Ohne
    diesen Parameter waere die einzige pruefbare Aussage ueber dieses
    Programm, dass es startet. installer/gui/app.py traegt denselben
    Griff aus demselben Grund.
    """
    options = parse(list(sys.argv[1:] if argv is None else argv))
    usage = model.read_usage(options.cache_file)

    # Gefuellt, sobald die Zeilen da sind. Beim Starter braucht die
    # Antwort unten die Zuordnung von Desktop-Kennung auf Anwendung, und
    # die entsteht erst im Fenster-Rueckruf. `commands` ist dasselbe fuer
    # die Aktionen von --show all.
    applications: dict = {}
    commands: dict[str, str] = {}
    # Und die Aktionen der Anwendungseintraege - eine Zeile je Seite der
    # Einstellungen, siehe apps.desktop_entries().
    actions: dict = {}

    if options.mode == MODE_DMENU:
        from_stdin = model.read_dmenu(sys.stdin)

        def load_rows() -> list[model.Entry]:
            return model.order(from_stdin, options.sort_order, usage)
    else:
        def load_rows() -> list[model.Entry]:
            # Erst hier importiert, nicht oben: apps.py zieht `gi`
            # herein, und der dmenu-Weg soll nicht an einem fehlenden Gio
            # scheitern, das er nie benutzt.
            from .apps import desktop_entries
            found, resolved, resolved_actions = desktop_entries()
            applications.update(resolved)
            actions.update(resolved_actions)
            rows = model.order(found, options.sort_order, usage)
            if options.mode != MODE_ALL:
                return rows

            # Die Anwendungen zuerst, die Aktionen dahinter, und JEDE
            # Haelfte fuer sich sortiert. Eine gemeinsame Sortierung
            # schoebe "Arbeitsflaechen: Zur Arbeitsflaeche 1" vor jede
            # Anwendung, deren Name mit B anfaengt - und wer den Starter
            # oeffnet, sucht meistens eine Anwendung. Das Zaehlwerk hebt
            # trotzdem beides hoch, in seiner eigenen Haelfte.
            # `bindings` und nicht `actions`: dieser Name gehoert seit
            # dem 12.08.2026 den Desktop-Aktionen oben, und eine
            # Zuweisung an ihn machte ihn hier lokal - die Zeile
            # `actions.update(...)` darueber waere ein
            # UnboundLocalError geworden, und zwar erst zur Laufzeit
            # und nur in dieser Betriebsart.
            bindings, resolved_commands = index.action_entries(
                index.read_actions())
            commands.update(resolved_commands)
            return rows + model.order(bindings, options.sort_order, usage)

    # Was das Fenster zurueckgibt, in einer Liste statt in einer
    # Variablen: die Rueckrufe laufen im GTK-Hauptzyklus und koennen
    # keinen Namen dieser Funktion binden.
    answer: list[model.Entry] = []

    from .window import MenuApplication

    application = MenuApplication(
        options, load_rows,
        on_chosen=answer.append,
        # Nur der Starter darf keinen freien Text annehmen: eine
        # getippte Zeichenkette, die auf keine .desktop-Datei passt, ist
        # keine Anwendung, und sie auszufuehren waere eine Shell mit
        # Fensterrahmen. Bei --dmenu ist genau das die Antwort - siehe
        # MenuWindow.accept().
        free_text=options.mode == MODE_DMENU,
        on_window_shown=on_window_shown)
    # Ohne Argumente. GTK wuerde sonst unsere eigenen Schalter noch
    # einmal auswerten und an `--dmenu` scheitern.
    application.run([])

    if not answer:
        return 1

    entry = answer[0]
    model.write_usage(options.cache_file, usage, entry.value)

    if options.mode == MODE_DMENU:
        print(entry.value)
        return 0

    from .apps import launch, launch_action, run_command
    if entry.value in commands:
        run_command(commands[entry.value])
        return 0
    if entry.value in actions:
        launch_action(*actions[entry.value])
        return 0
    launch(applications[entry.value], options.terminal)
    return 0
