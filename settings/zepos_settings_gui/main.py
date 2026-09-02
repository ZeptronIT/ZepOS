# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Verdrahtung: Einstellungen lesen, Fenster zeigen, Rueckgabewert.

DIE RUECKGABEWERTE
    0   das Fenster wurde geoeffnet und wieder geschlossen
    1   die Einstellungsdatei ist da und nicht lesbar

    Die 1 ist der Fall, der eine Erklaerung braucht und keinen
    Rueckverfolgungsbericht. settings.py schreibt sie: welche Datei, was
    daran nicht stimmt, und was man dagegen tut. Eine Anwendung, die
    stattdessen mit den Vorgaben aufginge, wuerde beim ersten Speichern
    ueber das schreiben, was der Nutzer noch hat - und das ist genau der
    Fehler, den `set-color` einmal gemacht hat, bevor die Datei einen
    Leser bekam.

WARUM DER IMPORT VON app.py ERST HIER PASSIERT
    Weil er `gi` hereinzieht. Der Fehlerweg oben braucht kein GTK, und
    eine unlesbare Einstellungsdatei soll nicht an einem fehlenden
    python-gobject scheitern - die Meldung waere dann ueber das
    Falsche.

DER SCHALTER --json, UND WARUM ER GANZ OBEN STEHT
    Seit dem 19.08.2026 ist dieser Befehl nicht nur ein Fenster: mit
    `--json` schreibt er den Zustand aller sieben Seiten als ein
    Dokument heraus und nimmt Aenderungen als eines entgegen. Der Kopf
    von bridge.py fuehrt aus, wofuer - kurz: das AGS-Einstellungsfenster
    zeichnet, model.py bleibt das Hirn, und beide duerfen nicht zwei
    Antworten auf dieselbe Frage haben.

    Er wird VOR page_of() und VOR settings_file.load() abgefangen, aus
    zwei Gruenden. Erstens ist `--page` ein Schalter fuer die
    .desktop-Datei und `--json` einer fuer ein anderes Programm; sie
    haben nichts gemeinsam ausser dem Befehl, an dem sie haengen.
    Zweitens meldet bridge.py eine unlesbare Einstellungsdatei als JSON
    und nicht als Satz auf stderr - ein Fenster, das deutsche Prosa aus
    einem Fehlerstrom fischt, liest beim naechsten Wortlaut das
    Falsche.

    Und wie der Fehlerweg oben kommt er ohne `gi` aus. Das ist keine
    Sparsamkeit: `--json get` ist der Weg, auf dem man diese
    Einstellungen auf einer Maschine ohne GTK4 noch lesen kann, also
    genau dort, wo man sie zum Reparieren braucht.
"""
from __future__ import annotations

import sys
from typing import Callable

import desktop_i18n
import paths
import settings as settings_file
from desktop_i18n import _

from . import bridge, model


def page_of(arguments: list[str]) -> str | None:
    """Welche Seite die Schalter nennen, oder None fuer "keine".

    Wirft ValueError, wenn die Schalter keine sind. Eine eigene Funktion
    und kein Zweig in main(), damit sie sich pruefen laesst OHNE `gi`:
    main() faellt zwei Zeilen weiter in `settings_file.load()` und
    danach in den Import von app.py, der GTK hereinzieht. Eine
    Zusicherung, die den Text von main.py durchsucht statt ihn
    auszufuehren, ist keine - GEMESSEN am 12.08.2026 mit einer Mutation,
    die JEDE Seite ablehnte und trotzdem gruen blieb.

    Der eine Schalter ist keine Bequemlichkeit fuer die Kommandozeile.
    Er existiert, weil die .desktop-Datei ihn braucht: sie liefert seit
    dem 12.08.2026 eine Aktion je Seite aus, damit `zepos-menu` die
    BILDSCHIRME findet und nicht nur die Anwendung, in der sie liegen.
    Eine Aktion ist eine Exec-Zeile, und eine Exec-Zeile kann eine Seite
    nur nennen, wenn das Programm zuhoert.

    Geprueft wird gegen dieselbe Tabelle, aus der das Fenster seine
    Seiten baut - model.PAGES. Ein unbekannter Name ist ein Fehler und
    keine stille Vorgabeseite: eine Aktion, die klaglos die falsche
    Seite oeffnet, ist ein Bedienelement, das etwas anderes tut als es
    sagt.
    """
    if not arguments:
        return None
    if (len(arguments) == 2
            and arguments[0] == model.PAGE_OPTION
            and arguments[1] in model.PAGE_NAMES):
        return arguments[1]
    # ZEILENWEISE durch den Katalog und nicht als ein Block: ein msgid
    # mit einem \n darin schreibt gettext in der mehrzeiligen Form, und
    # die Kataloguesicherung sucht die einzeilige Zeichenfolge. Fuenf
    # msgids, hier zusammengesetzt - der Umbruch ist Anordnung und keine
    # Sprache.
    raise ValueError("\n".join((
        _("usage: zepos-settings-gui [{option} PAGE]").format(
            option=model.PAGE_OPTION),
        _("       zepos-settings-gui {option} get|set|apply").format(
            option=bridge.OPTION),
        _("`{given}` is none of this application's switches.").format(
            given=" ".join(arguments)),
        _("Pages: {names}").format(names=", ".join(model.PAGE_NAMES)),
        _("For the command line: zepos-settings --help"))))


def main(argv: list[str] | None = None, *,
         on_window_shown: Callable | None = None,
         runner=None) -> int:
    """Ein Durchlauf.

    `on_window_shown` bekommt das fertige Fenster, `runner` tritt an die
    Stelle von subprocess.run. Beide gibt es fuer
    tests/settings/settings_headless_child.py - der Generator beendet die
    Leiste und AGS des Nutzers, also darf kein Test ihn wirklich
    aufrufen, und ohne einen Griff ins Fenster waere die einzige
    pruefbare Aussage, dass die Anwendung startet.
    """
    # DER KATALOG ZUERST, VOR DEM ERSTEN ZEICHEN AUSGABE.
    #
    # Vor dem Abzweig nach bridge.py und vor page_of(): beide Wege geben
    # Text aus - die Bruecke ihre Klagen als JSON, page_of() seinen
    # Gebrauchstext auf stderr -, und ein Katalog, der erst danach
    # gewaehlt wird, kommt fuer diese Zeile zu spaet.
    #
    # Ohne Angabe: die Sprache, die /etc/locale.conf gerade nennt. Der
    # Kopf von src/desktop_i18n.py fuehrt aus, warum die DATEI und nicht
    # die Umgebung - kurz: nach `localectl set-locale` ist die Umgebung
    # dieses Prozesses eine Abschrift von vorher.
    desktop_i18n.activate()

    arguments = list(sys.argv[1:] if argv is None else argv)

    if arguments and arguments[0] == bridge.OPTION:
        return bridge.main(arguments[1:], runner=runner)

    try:
        page = page_of(arguments)
    except ValueError as wrong:
        print(wrong, file=sys.stderr)
        return 2

    try:
        settings_file.load()
    except (ValueError, OSError) as problem:
        # Denselben Pfad wie cli.settings_path(), und aus demselben
        # Grund benannt statt beschrieben: "unsupported schema_version
        # None" sagt nicht, welche Datei zu reparieren ist, und es gibt
        # mehr als eine Einstellungsdatei auf einer Maschine.
        target = paths.user_root() / settings_file.FILENAME
        print(settings_file.unreadable(target, problem), file=sys.stderr)
        return 1

    from .app import SettingsApplication

    application = SettingsApplication(
        runner=runner, on_window_shown=on_window_shown, page=page)
    # Ohne Argumente: GTK wertete sonst unsere eigenen noch einmal aus.
    return application.run([])
