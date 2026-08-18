# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Einstellungs-Anwendung, einmal wirklich gebaut und wirklich bedient.

KEIN Testmodul - pytest sammelt diese Datei nicht ein (kein test_-Praefix).
tests/settings/test_settings_headless.py startet sie als Kind, weil das
der einzige Weg ist, diesen Code in dieser Suite ueberhaupt auszufuehren:
`gi` fehlt in .venv, und ein GTK4-Widget ohne Anzeige zu bauen wirft keine
Ausnahme, sondern SEGFAULTet (Exit 139) - was innerhalb von pytest die
Sitzung ohne Bericht beenden wuerde.

WAS ECHT IST
    Alles ausser dem einen, was echt zu sein sich verbietet. Es laeuft
    zepos_settings_gui.main.main() - dieselbe Funktion, die
    /usr/bin/zepos-settings-gui aufruft -, also das echte Fenster, die
    echten Rueckrufe, das echte settings.merge() in eine echte Datei und
    das echte update.apply(), das eine echte Zeitgeber-Ergaenzung
    schreibt.

    Das eine ist der Generator. `zepos-generate --all` beendet die
    Leiste und AGS DES ENTWICKLERS - gemessen am 11.08.2026, mitten in
    einer Sitzung -, also bekommt die Anwendung hier einen `runner`, der
    den Befehl nur aufschreibt. Was damit gemessen wird, ist trotzdem
    alles, was diese Anwendung dazu beitraegt: WELCHER Befehl, mit
    welchen Argumenten, und was danach mit der Marke fuer die naechste
    Anmeldung passiert.

WARUM DIE SPUR IN EINE DATEI GEHT
    Wortgleich zu tests/menu/menu_headless_child.py. Hier ist stdout
    zwar keine Antwort, aber GTK und GLib schreiben ihre eigenen
    Meldungen dorthin und nach stderr, und der Test prueft die auf
    Warnungen - eine Spur dazwischen machte diese Pruefung wertlos.
"""
from __future__ import annotations

import faulthandler
import json
import os
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import GLib  # noqa: E402

import displays  # noqa: E402

from zepos_settings_gui import model  # noqa: E402
from zepos_settings_gui.main import main as settings_main  # noqa: E402

TRACE: list[str] = []
FAILURES: list[str] = []

# Jeder Befehl, den die Anwendung abgesetzt haette. Der Test liest ihn
# aus der Spur; ohne ihn waere "der Generator wurde nicht wirklich
# gerufen" auch dann wahr, wenn die Anwendung ihn gar nicht ruft.
COMMANDS: list[list[str]] = []


def note(mark: str) -> None:
    TRACE.append(mark)


def runner(argv, **kwargs) -> subprocess.CompletedProcess:
    """Der Platzhalter fuer subprocess.run.

    Er gibt 0 zurueck, weil beide Aufrufer den Rueckgabewert lesen und
    daraus etwas folgern: model.regenerate() raeumt die Marke nur bei 0
    weg, und update.apply() nimmt jeden Ausgang hin. Ein Fehlschlag ist
    ein eigener Lauf mit `fail-generator` - siehe unten.
    """
    COMMANDS.append(list(argv))
    note("cmd:" + " ".join(str(part) for part in argv))
    return subprocess.CompletedProcess(list(argv), 0, "", "")


def failing_runner(argv, **kwargs) -> subprocess.CompletedProcess:
    COMMANDS.append(list(argv))
    note("cmd:" + " ".join(str(part) for part in argv))
    return subprocess.CompletedProcess(list(argv), 1, "", "kaputt")


def report(window) -> None:
    """Was gerade im Fenster steht, in Marken."""
    note(f"scale:{window.scale_row.get_value():.4f}")
    for dial in model.DIALS:
        row = window.dial_rows[dial.name]
        # "inherited" heisst: kein Eintrag in sizes.values, der Wert
        # kommt aus Grundwert und Faktor. NICHT dasselbe wie "folgt dem
        # Faktor" - STYLE_DOCK_ICON_SIZE ist ein Bild und folgt ihm nie,
        # steht aber trotzdem nicht in sizes.values.
        state = "inherited" if window.draft.follows_scale(dial.name) else "named"
        note(f"dial:{dial.name}={row.get_value():.0f}:{state}")
    note(f"dirty:{window.draft.dirty()}")
    note(f"save-sensitive:{window.save_button.get_sensitive()}")
    note(f"banner:{window.banner.get_revealed()}:{window.banner.get_title()}")
    note(f"marker:{model.marker_path().exists()}")
    # Was die Auswahllisten der Aktualisierung anbieten und was davon
    # gerade steht. Ohne das koennte ein Test nur die geschriebene Datei
    # lesen - und ein Fenster, das einen unbekannten Wert beim Oeffnen
    # durch "daily" ERSETZT, aendert die Datei erst, wenn jemand die
    # Auswahl anfasst. Bis dahin sieht alles richtig aus.
    for key, row in sorted(window.update_rows.items()):
        if key not in window.update_options:
            continue
        options = window.update_options[key]
        note(f"choice:{key}={options[row.get_selected()]}"
             f"|{','.join(str(option) for option in options)}")

    report_bar(window)
    report_screens(window)


def report_bar(window) -> None:
    """Was auf der Leistenseite gerade steht.

    Je Haelfte fuenf Marken, und eine sechste, solange ueberhaupt etwas
    dasteht. Die Reihenfolge allein waere zu wenig: sie sagt nicht, ob
    man aus ihr wieder herauskommt.

      bar-<haelfte>            die wirksame Reihenfolge
      bar-missing-<haelfte>    was ZepOS ausliefert und hier fehlt
      bar-reset-<haelfte>      ob der Rueckweg anwaehlbar ist
      bar-add-<haelfte>        ob sich etwas hinzufuegen laesst
      bar-offer-<haelfte>      was die Zeile zum Hinzufuegen sagt
      bar-title-<haelfte>      wie die Zeilen beschriftet sind
      bar-sub-<haelfte>        was unter der Beschriftung steht
      bar-complaint-<haelfte>  was die Seite zu verworfenen Namen sagt
      bar-ends-<haelfte>       die zwei Pfeile an den Enden

    Dazu, je Anheftung, was das Dock aus ihr macht:

      bar-dock:<name>=<beschriftung>|<grund>

    Der Grund ist leer, wenn das Dock sie anheftet. Ohne diese Marke
    waere nicht zu messen, ob die Seite einen Dienst ohne Fenster
    KENNZEICHNET oder ihn nur zufaellig nicht anbietet.
    """
    page = window.bar_page
    if page is None:
        note("bar:keine")
        return

    note(f"bar-note:{page.note or '-'}")
    for name, (label, reason) in sorted(page.dock.items()):
        note(f"bar-dock:{name}={label}|{reason}")
    for key, _title, _description in model.BAR_SIDES:
        note(f"bar-{key}:{','.join(page.shown[key])}")
        note(f"bar-missing-{key}:{','.join(page.missing[key])}")
        note(f"bar-reset-{key}:{page.reset_buttons[key].get_sensitive()}")
        note(f"bar-add-{key}:{page.add_buttons[key].get_sensitive()}")
        # Was die Zeile zum Hinzufuegen SAGT. Eine Auswahl, in der ein
        # Name fehlt, ohne dass daneben steht warum, sieht aus wie eine
        # unvollstaendige Anwendung.
        note(f"bar-offer-{key}:{page.add_rows[key].get_subtitle()}")
        # Und wie die Zeilen wirklich heissen. Der gespeicherte Name
        # steht schon oben; hier steht, was der Mensch liest - und ob
        # dort ueberhaupt etwas steht, wenn der Abdruck keine
        # Beschriftung mitbringt.
        note(f"bar-title-{key}:"
             + "|".join(f"{name}={title}"
                        for name, title in page.titles[key].items()))
        note(f"bar-sub-{key}:"
             + "|".join(f"{name}={subtitle}"
                        for name, subtitle in page.subtitles[key].items()))
        note(f"bar-complaint-{key}:{page.complaints[key] or '-'}")
        # Die zwei Enden. Ein Pfeil, der ueber den Rand hinausfuehrt,
        # waere ein Knopf, hinter dem nichts passiert - und das ist der
        # Fehler, den diese ganze Seite behebt.
        order = page.shown[key]
        if order:
            note(f"bar-ends-{key}:"
                 f"{page.buttons[key][order[0]]['up'].get_sensitive()},"
                 f"{page.buttons[key][order[-1]]['down'].get_sensitive()}")


def report_screens(window) -> None:
    """Was die Bildschirmseite gerade zeigt.

    Jede Zeile beschreibt EINEN Schirm vollstaendig, weil eine Anordnung
    nur als ganze etwas bedeutet: "DP-1 steht bei 0x0" ist wahr und sagt
    nichts darueber, ob eDP-1 daneben oder darunter steht.

        screen:<name>=<x>x<y>:<breite>x<hoehe>:<an|aus>:<gewaehlt|->
    """
    page = window.screens_page
    if page is None or page.desk is None:
        note("screens:keine")
        return
    note(f"screens:{len(page.desk.placements)}")
    note(f"screens-changed:{page.desk.changed()}")
    note(f"screens-apply-sensitive:{page.apply_button.get_sensitive()}")
    note(f"screens-report:{page.report}")
    note(f"screens-countdown:{page.countdown}")
    note(f"screens-attempt:{page.attempt is not None}")

    # DIE ZWEI MARKEN, DIE "ANGEWANDT" VON "GESCHRIEBEN" TRENNEN.
    #
    # Beides IN DIESEM AUGENBLICK und nicht nach dem Lauf: was am Ende
    # in der Datei steht, sagt nichts darueber, ob sie beim Anwenden
    # schon dastand - und genau das ist die Zusicherung dieser Seite.
    # Nach dem Lauf gemessen waere ausserdem alles verwaschen, was das
    # Aufraeumen noch tut.
    log = os.environ.get("HYPRCTL_LOG")
    lines = []
    if log and Path(log).is_file():
        lines = [line for line in
                 Path(log).read_text(encoding="utf-8").splitlines() if line]
    note(f"applied:{len(lines)}")
    if lines:
        note(f"applied-last:{lines[-1]}")
    note(f"written:{displays.config_path().is_file()}")
    if page.dialog is not None:
        # Was die Rueckfrage tut, wenn niemand einen ihrer Knoepfe
        # drueckt. Der Unterschied zwischen einer Rueckfrage und einer
        # Falle steht in genau diesen zwei Werten.
        note(f"dialog-default:{page.dialog.get_default_response()}")
        note(f"dialog-close:{page.dialog.get_close_response()}")
    for item in page.desk.placements:
        note(f"screen:{item.name}={item.x}x{item.y}:"
             f"{item.displayed_width}x{item.displayed_height}:"
             f"{'an' if item.enabled else 'aus'}:"
             f"{'gewaehlt' if item.name == page.selected else '-'}")
        note(f"spec:{item.name}={displays.spec(item)}")


def drive(window, script: str) -> None:
    """Ein Schritt je Anweisung, im Leerlauf des Hauptzyklus.

    GLib.idle_add und nicht unmittelbar aus on_window_shown: das Fenster
    ist dort gebaut, aber noch nicht abgebildet, und Adw.PreferencesPage
    fuellt seine Gruppen erst beim ersten Durchlauf.
    """
    def step() -> bool:
        try:
            note("backend:"
                 + window.get_display().__gtype__.name)
            note(f"pages:{window.stack.get_pages().get_n_items()}")
            note(f"colours:{len(window.colour_buttons)}")
            report(window)

            for instruction in script.split():
                verb, _, argument = instruction.partition(":")
                perform(window, verb, argument)
                note(f"after-{verb}:")
                report(window)
        except Exception as problem:                         # noqa: BLE001
            FAILURES.append(f"{type(problem).__name__}: {problem}")
        finally:
            # Eine offene Rueckfrage zuerst, DANN das Fenster.
            #
            # GEMESSEN am 12.08.2026: ein Adw.Dialog ueber dem Fenster
            # frisst das erste close() - libadwaita schliesst den Dialog
            # und laesst das Fenster stehen. Der Lauf lief danach in die
            # 45-Sekunden-Grenze, weil die Hauptschleife nie leer wurde.
            # Was der WINDOW-Weg bedeutet, misst die Anweisung
            # "screen-shut" ausdruecklich; hier geht es nur darum, dass
            # ein Lauf endet.
            page = window.screens_page
            if page is not None and page.attempt is not None:
                page._settle(False)
            window.close()
        return GLib.SOURCE_REMOVE

    GLib.idle_add(step)


def perform(window, verb: str, argument: str) -> None:
    if verb == "scale":
        # set_value auf der Anpassung und nicht auf der Zeile: das ist
        # genau der Weg, den ein Pfeilklick und ein Tastendruck nehmen,
        # und er loest dasselbe "notify::value" aus.
        window.scale_row.get_adjustment().set_value(float(argument))
    elif verb == "scale-reset":
        window._on_scale_reset(None)
    elif verb == "dial":
        name, _, value = argument.partition("=")
        window.dial_rows[name].get_adjustment().set_value(float(value))
    elif verb == "dial-reset":
        dial = next(d for d in model.DIALS if d.name == argument)
        window._on_dial_reset(None, dial)
    elif verb == "colour":
        key, _, value = argument.partition("=")
        window.colour_buttons[key].set_rgba(window._rgba(value))
    elif verb == "colour-reset":
        window._on_colour_reset(None, argument)
    elif verb == "weather":
        # Zeichen fuer Zeichen, so wie eine Taste es tut - insert_text
        # ist das, was GtkEntry intern bei jedem Tastendruck macht, und
        # es loest denselben "changed"-Rueckruf aus.
        buffer = window.weather_row.get_delegate().get_buffer()
        for character in ("" if argument == "-" else argument):
            buffer.insert_text(buffer.get_length(), character, 1)
    elif verb == "update":
        key, _, value = argument.partition("=")
        row = window.update_rows[key]
        if hasattr(row, "set_active"):
            row.set_active(json.loads(value))
        else:
            row.set_selected(window.update_options[key].index(value))
    elif verb in ("bar-remove", "bar-up", "bar-down"):
        # Ueber die Knoepfe der Zeile und nicht ueber die Methoden
        # dahinter: was hier gemessen werden soll, ist die Verdrahtung.
        # Eine Seite, deren Pfeile an nichts haengen, sortiert in jedem
        # Test tadellos um und auf dem Schirm gar nicht.
        key, _, name = argument.partition("=")
        which = {"bar-remove": "remove", "bar-up": "up",
                 "bar-down": "down"}[verb]
        window.bar_page.buttons[key][name][which].emit("clicked")
    elif verb == "bar-add":
        key, _, name = argument.partition("=")
        page = window.bar_page
        page.add_rows[key].set_selected(page.missing[key].index(name))
        page.add_buttons[key].emit("clicked")
    elif verb == "bar-reset":
        window.bar_page.reset_buttons[argument].emit("clicked")
    elif verb == "save":
        window._on_save(None)
    elif verb == "apply":
        note(f"apply-rc:{window.apply_now()}")
    elif verb == "ask":
        # Der Weg ueber den Knopf im Banner: er oeffnet den Dialog, und
        # der Dialog ist die Stelle, an der die Kosten stehen.
        window._on_banner_clicked(None)
    elif verb == "screen":
        # Einen Schirm waehlen, so wie ein Klick auf die Zeichnung es
        # tut - ueber dieselbe Methode, die die Geste ruft.
        window.screens_page.area.select(argument)
    elif verb == "drag":
        # NAME@X,Y in BILDSCHIRMkoordinaten, hier durch to_canvas() in
        # Zeichnungskoordinaten gewandelt und dann durch drag_to()
        # wieder zurueck.
        #
        # WARUM NICHT UNMITTELBAR IN ZEICHNUNGSKOORDINATEN
        #     Weil die Umrechnung an der GROESSE des Widgets haengt, und
        #     die ist hier 0: on_window_shown laeuft, bevor GTK das
        #     Fenster einmal vermessen hat. GEMESSEN am 12.08.2026: ein
        #     "drag:eDP-1@0,0" landete bei 2680x720 - genau der Mitte
        #     des Schreibtischs, weil _offset() gegen eine Breite von 0
        #     rechnet. Der Test maesse dann die Reihenfolge von GTKs
        #     Layoutlauf und nicht das Verschieben.
        #
        #     Ueber to_canvas() faellt die Groesse aus der Rechnung
        #     heraus, und was uebrig bleibt, ist der Weg, um den es geht:
        #     drag_to() -> Desk.move() -> einrasten -> normalisieren.
        name, _, point = argument.partition("@")
        x, _, y = point.partition(",")
        area = window.screens_page.area
        area.select(name)
        # Angefasst wird die linke obere Ecke: ohne einen Griff wuerde
        # drag_to() den vorherigen weiterverwenden, und der Test setzte
        # dann nicht die Stelle, die er nennt.
        area.grab = (0, 0)
        area.drag_to(name, *area.to_canvas(int(x), int(y)))
    elif verb == "screen-off":
        window.screens_page.rows["enabled"].set_active(False)
    elif verb == "screen-on":
        window.screens_page.rows["enabled"].set_active(True)
    elif verb == "screen-scale":
        page = window.screens_page
        page.rows["scale"].set_selected(
            page.scale_options.index(float(argument)))
    elif verb == "screen-mode":
        window.screens_page.rows["mode"].set_selected(int(argument))
    elif verb == "screen-transform":
        window.screens_page.rows["transform"].set_selected(int(argument))
    elif verb == "screen-apply":
        note(f"screen-apply-report:{window.screens_page.apply_now()}")
    elif verb == "screen-keep":
        window.screens_page._settle(True)
    elif verb == "screen-back":
        window.screens_page._settle(False)
    elif verb == "screen-shut":
        # Das Fenster zumachen, waehrend die Frage steht. libadwaita
        # schliesst dabei seine Dialoge selbst, mit dem
        # Schliess-Ergebnis - und genau das soll "zuruecknehmen"
        # bedeuten.
        window.close()
    elif verb == "screen-wait":
        # Den Zaehler ablaufen lassen, Tick fuer Tick.
        #
        # Gerufen wird genau die Funktion, die GLib nach funfzehn
        # Sekunden auch riefe - nur eben sofort, damit ein Test nicht
        # funfzehn Sekunden dauert. Was hier NICHT gemessen wird, ist der
        # Rueckfall selbst: der laeuft im Waechter, in einem eigenen
        # Prozess, und tests/src/test_displays_guard.py laesst dessen
        # Frist wirklich ablaufen.
        page = window.screens_page
        source = page.countdown_source
        while page.countdown_source and page.attempt is not None:
            page._tick()
        # Die Quelle haelt GLib noch, weil _tick() hier nicht aus der
        # Hauptschleife kam und sein GLib.SOURCE_REMOVE deshalb niemanden
        # erreicht hat. Bliebe sie stehen, liefe sie eine Sekunde spaeter
        # noch einmal - in einen Zustand, den dieser Lauf schon verlassen
        # hat.
        if source:
            GLib.Source.remove(source)
    else:                                                    # pragma: no cover
        FAILURES.append(f"unbekannte Anweisung: {verb}:{argument}")


def child(arguments: list[str]) -> int:
    faulthandler.dump_traceback_later(45, exit=True)
    trace_file = Path(arguments[0])
    script = arguments[1]
    chosen = failing_runner if "fail-generator" in arguments[2:] else runner

    escaped: list[str] = []
    previous_hook = sys.excepthook

    def capture(exc_type, exc_value, exc_tb) -> None:
        escaped.append(f"{exc_type.__name__}: {exc_value}")
        previous_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = capture
    try:
        code = settings_main(
            [], runner=chosen,
            on_window_shown=lambda window: drive(window, script))
    except SystemExit as stop:
        code = int(stop.code or 0)
    except Exception as problem:                             # noqa: BLE001
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
