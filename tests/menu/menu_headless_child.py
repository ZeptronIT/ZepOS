# SPDX-License-Identifier: GPL-3.0-or-later
"""zepos-menu, einmal wirklich gebaut und wirklich bedient.

KEIN Testmodul - pytest sammelt diese Datei nicht ein (kein test_-Praefix).
tests/menu/test_menu_headless.py startet sie als Kind, weil das der
einzige Weg ist, diesen Code in dieser Suite ueberhaupt auszufuehren:
`gi` fehlt in .venv, und ein GTK4-Widget ohne Anzeige zu bauen wirft
keine Ausnahme, sondern SEGFAULTet (Exit 139) - was innerhalb von pytest
die Sitzung ohne Bericht beenden wuerde.

WARUM DIE SPUR IN EINE DATEI GEHT UND NICHT AUF stdout
    Weil stdout die Antwort ist. Ein dmenu-Ersatz hat genau einen
    Vertrag: auf stdout steht die gewaehlte Zeile und sonst nichts. Ein
    Kind, das seinen Fortschritt dorthin schreibt, macht die einzige
    Aussage kaputt, die zu pruefen sich lohnt - `printer-manager` liest
    diese Ausgabe als Druckernamen und `cliphist-menu.sh` reicht sie an
    `cliphist decode` weiter.

WARUM sys.excepthook BEOBACHTET WIRD
    Gemessen an installer/gui/app.py und dort im Kopf begruendet: eine
    Ausnahme, die in do_activate() fliegt, wird von PyGObject gedruckt,
    und Application.run() gibt trotzdem 0 zurueck - GLib ruft
    do_activate als Signalrueckruf auf, und eine Python-Ausnahme kann
    ueber den C-Stapel nicht zurueck. Ein Kind, das nur den
    Rueckgabewert meldete, hielte einen Absturz fuer einen Erfolg.

WAS ECHT IST
    Alles. Es laeuft zepos_menu.main.main() - dieselbe Funktion, die
    /usr/bin/zepos-menu aufruft -, also die echte Schalterauswertung, das
    echte Einlesen von stdin, das echte Fenster, der echte Filter, der
    echte Tastaturregler, das echte Zaehlwerk und die echte Ausgabe. Die
    Tasten werden ueber den Regler EMITTIERT, nicht als Methode
    aufgerufen: so ist auch die Verdrahtung gemessen und nicht nur der
    Rumpf des Rueckrufs.
"""
from __future__ import annotations

import faulthandler
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GLib  # noqa: E402

from zepos_menu.main import main as menu_main  # noqa: E402

TRACE: list[str] = []
FAILURES: list[str] = []

# Die Tasten, die dieses Programm kennt, unter ihren Namen. Der Test
# schreibt "down enter", das Kind schlaegt hier nach - eine Liste von
# Zahlen im Test waere eine Liste, in der niemand einen Fehler sieht.
KEYS = {
    "down": Gdk.KEY_Down,
    "up": Gdk.KEY_Up,
    "page-down": Gdk.KEY_Page_Down,
    "page-up": Gdk.KEY_Page_Up,
    "enter": Gdk.KEY_Return,
    "escape": Gdk.KEY_Escape,
    # Eine Taste, die das Programm NICHT belegt. Sie muss durchgereicht
    # werden - der Regler haengt in der Fangphase am Fenster, und einer,
    # der alles verschluckt, liesse kein einziges Zeichen ins
    # Eingabefeld.
    "f5": Gdk.KEY_F5,
}


def note(mark: str) -> None:
    TRACE.append(mark)


def visible_labels(window) -> list[str]:
    return [window.selection.get_item(index).entry.label
            for index in range(window.selection.get_n_items())]


def visible_hints(window) -> list[str]:
    """Die Tastenspalte, so wie sie im FENSTER steht.

    Nicht aus dem Modell, sondern aus dem gebundenen Widget: die Taste
    neben einer Zeile ist der Grund, aus dem es `--show all` gibt - wer
    sie nur im Modell prueft, hat gemessen, dass sie berechnet wurde, und
    nicht, dass sie jemand sieht.

    EIN SICHTBARES LEERES FELD BEKOMMT EINEN NAMEN, und das ist kein
    Detail: eine Mutationspruefung am 12.08.2026 hat `set_visible(True)`
    fuer JEDE Zeile eingesetzt - neben jeder Anwendung stuende dann eine
    leere Spalte - und ist durchgekommen, weil "" in der Verkettung
    unsichtbar ist. Genau denselben Unterschied sieht ein Nutzer sehr
    wohl.
    """
    found: list[str] = []
    row = window.list.get_first_child()
    while row is not None:
        box = row.get_first_child()
        if box is not None:
            hint = box.get_last_child()
            if hint is not None and hint.get_visible():
                found.append(hint.get_text() or "<leeres feld>")
        row = row.get_next_sibling()
    return found


def type_text(window, text: str) -> None:
    """Zeichen fuer Zeichen in den Puffer, so wie eine Taste es tut.

    set_text() waere ein Sprung; insert_text() ist das, was GtkEntry
    intern bei jedem Tastendruck macht, und es loest denselben
    "changed"-Rueckruf aus, der den Filter neu laufen laesst.
    """
    buffer = window.search.get_buffer()
    for character in text:
        buffer.insert_text(buffer.get_length(), character, 1)


def press(window, name: str) -> bool:
    handled = window.key_controller.emit(
        "key-pressed", KEYS[name], 0, Gdk.ModifierType(0))
    note(f"key:{name}:{'handled' if handled else 'passed-on'}")
    return handled


def drive(window, script: str) -> None:
    """Ein Schritt je Anweisung, alle im Leerlauf des Hauptzyklus.

    GLib.idle_add und nicht direkt aus on_window_shown heraus: das
    Fenster ist dort zwar gebaut, aber noch nicht abgebildet, und
    Gtk.ListView fuellt sein Sichtfeld erst beim ersten Durchlauf. Ein
    scroll_to() davor traefe eine Liste ohne Zeilen.
    """
    def step() -> bool:
        try:
            note(f"backend:{Gdk.Display.get_default().__gtype__.name}")
            note(f"items:{window.selection.get_n_items()}")
            note(f"visible:{window.search.get_visibility()}")
            note(f"placeholder:{window.search.get_placeholder_text()}")
            note("size:%dx%d" % tuple(window.get_default_size()))
            note("order:" + "|".join(visible_labels(window)))
            for instruction in script.split():
                verb, _, argument = instruction.partition(":")
                if verb == "type":
                    type_text(window, argument)
                    note("filtered:" + "|".join(visible_labels(window)))
                    note("hints:" + "|".join(visible_hints(window)))
                    note(f"message:{window.message.get_visible()}")
                elif verb == "key":
                    press(window, argument)
                    note(f"selected:{window.selection.get_selected()}")
                elif verb == "click":
                    # Die Maus, ueber dasselbe Signal, das ein Klick
                    # ausloest. single_click_activate ist an, also ist
                    # ein Klick genau ein "activate" auf dieser Position.
                    window.list.emit("activate", int(argument))
                    note(f"clicked:{argument}")
                else:                                    # pragma: no cover
                    FAILURES.append(f"unbekannte Anweisung: {instruction}")
        except Exception as problem:                     # noqa: BLE001
            FAILURES.append(f"{type(problem).__name__}: {problem}")
            window.close()
        return GLib.SOURCE_REMOVE

    GLib.idle_add(step)


def run(argv: list[str], script: str) -> int:
    return menu_main(argv, on_window_shown=lambda window: drive(window, script))


# Nach dieser Zeit gibt das Kind auf und schreibt vorher, wo es steht.
#
# WARUM UEBERHAUPT
#     Ein GTK-Hauptzyklus, der nicht endet, ist von einem Testrahmen aus
#     nicht zu unterscheiden von einem, der noch arbeitet: subprocess.run
#     laeuft in seine Zeitgrenze, toetet das Kind, und der Bericht sagt
#     "timed out" und sonst nichts. Gemessen am 11.08.2026 dreimal
#     hintereinander an den drun-Tests, jedes Mal 120 Sekunden ohne eine
#     einzige Zeile darueber, WO.
#
#     faulthandler schreibt den Stapel jedes Threads nach stderr und
#     beendet den Prozess. Deutlich unter CHILD_TIMEOUT, damit der Rahmen
#     den Bericht noch einsammelt statt selbst zuzuschlagen.
GIVE_UP_SECONDS = 45


def child(arguments: list[str]) -> int:
    faulthandler.dump_traceback_later(GIVE_UP_SECONDS, exit=True)
    trace_file = Path(arguments[0])
    script = arguments[1]
    argv = arguments[2:]

    escaped: list[str] = []
    previous_hook = sys.excepthook

    def capture(exc_type, exc_value, exc_tb) -> None:
        escaped.append(f"{exc_type.__name__}: {exc_value}")
        previous_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = capture
    try:
        code = run(argv, script)
    except SystemExit as stop:
        # `raise SystemExit("text")` schreibt seinen Text sonst der
        # Interpreter auf stderr, kurz bevor er mit 1 endet. Weil er hier
        # abgefangen wird, muss beides von Hand nachgeholt werden - sonst
        # verschwindet die Begruendung, an der der Test die richtige
        # Ablehnung von einer beliebigen unterscheidet.
        if isinstance(stop.code, str):
            print(stop.code, file=sys.stderr)
            code = 1
        else:
            code = int(stop.code or 0)
    except Exception as problem:                         # noqa: BLE001
        FAILURES.append(f"{type(problem).__name__}: {problem}")
        code = 70
    finally:
        sys.excepthook = previous_hook

    for problem in escaped:
        FAILURES.append(f"escaped: {problem}")

    note(f"exit:{code}")
    for problem in FAILURES:
        note(f"FAILURE: {problem}")
    trace_file.write_text("\n".join(TRACE) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(child(sys.argv[1:]))
