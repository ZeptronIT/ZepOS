# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Anwendungsstarter: welche .desktop-Dateien es gibt und wie sie starten.

WARUM Gio UND KEIN EIGENER LESER
    Eine .desktop-Datei ist nicht die INI-Datei, nach der sie aussieht.
    Was ein Starter richtig machen muss, steht in der Spezifikation und
    ist an jeder Stelle eine eigene Falle: NoDisplay und Hidden,
    OnlyShowIn/NotShowIn gegen XDG_CURRENT_DESKTOP, TryExec, die
    uebersetzten Name[de]-Zeilen, die Vorrangregel zwischen
    XDG_DATA_HOME und XDG_DATA_DIRS bei gleicher Kennung, und
    DBusActivatable, das gar kein Exec hat.

    Gio kann das alles und ist ohnehin da - GTK4 bringt GLib mit. Ein
    eigener Leser waere ein zweiter, schlechterer, dessen Fehler als
    "die Anwendung ist im Starter nicht zu finden" auftreten, was
    niemand als Fehler dieses Programms erkennt.

    Der Preis ist, dass dieses Modul `gi` braucht und deshalb nicht in
    der Testumgebung laeuft. Es wird stattdessen in einem Kind gemessen -
    siehe tests/menu/menu_headless_child.py, das ein eigenes
    XDG_DATA_HOME mit selbst geschriebenen .desktop-Dateien aufbaut.

WARUM Terminal=true NICHT AN Gio ABGEGEBEN WIRD
    g_app_info_launch() sucht sich fuer eine Anwendung mit Terminal=true
    selbst ein Terminal - ueber die GSettings der GNOME-Sitzung und eine
    eingebaute Liste. Auf ZepOS gibt es weder das eine noch das andere,
    und die erzeugte Konfiguration sagt ausdruecklich `terminal=kitty`.
    Ein Starter, der diese Zeile schreibt und dann etwas anderes
    aufmacht, hat die Einstellung nicht.
"""
from __future__ import annotations

import re

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from .entries import Entry  # noqa: E402

# Die Platzhalter, die eine Exec-Zeile tragen darf. Sie stehen fuer
# Dateien, URLs, das Symbol und den uebersetzten Namen - alles Dinge, die
# ein Starter ohne Argumente nicht liefert. Uebrig gelassen wuerden sie
# als Zeichenkette an das Programm gereicht: `htop %U` startet htop mit
# einer Datei namens "%U".
_FIELD_CODES = re.compile(r"(?<!%)%[fFuUdDnNickvm]")


def strip_field_codes(commandline: str) -> str:
    return " ".join(_FIELD_CODES.sub("", commandline).split())


# Wie eine Aktion in einer Zeile benannt wird: Kennung, dieses Zeichen,
# Name der Aktion. Ein Doppelkreuz, weil eine Desktop-Kennung ein
# Dateiname ist und keiner in diesem System eines traegt - und weil die
# Zeile im Zaehlwerk landet, wo sie von der Kennung der ganzen Anwendung
# unterscheidbar bleiben muss.
ACTION_MARK = "#"


def desktop_entries() -> tuple[list[Entry], dict[str, Gio.AppInfo],
                               dict[str, tuple[Gio.AppInfo, str]]]:
    """Alles, was ein Menue zeigen wuerde, in Eingabereihenfolge.

    g_app_info_get_all() liefert auch die Eintraege mit NoDisplay=true -
    die Handler fuer Dateitypen, die MIME-Zuordnungen, die
    Einzelfenster-Helfer. should_show() ist die Frage, die ein Menue
    stellt, und sie beantwortet zugleich OnlyShowIn/NotShowIn gegen
    XDG_CURRENT_DESKTOP.

    DIE AKTIONEN KOMMEN MIT, UND DAS IST DIE ANTWORT AUF EINE BESCHWERDE
        GEMELDET am 12.08.2026: "ich finde den display manager wie nwg
        display nicht in der app suche". Die Bildschirmeinstellung ist
        seit dem Wegfall von nwg-displays keine Anwendung mehr, sondern
        eine SEITE - und eine Seite hat keinen Anwendungseintrag.

        Die Freedesktop-Spezifikation kennt fuer genau das Desktop
        Actions, GIO liest sie ohne Zutun (list_actions,
        get_action_name, launch_action), und
        settings/zepos-settings.desktop liefert seit demselben Tag eine
        je Seite aus. Sie stehen hier als eigene Zeilen, mit dem Namen
        der Anwendung davor: "Systemeinstellungen: Bildschirme".

        Der Name der Anwendung MUSS davor stehen. Eine Zeile, die nur
        "Bildschirme" heisst, sagt nicht, was sie oeffnet - und im selben
        Fenster stehen die Tastenbindungen, deren Zeilen aus demselben
        Grund ihre Gruppe vorn tragen (siehe index.action_entries).
    """
    entries: list[Entry] = []
    applications: dict[str, Gio.AppInfo] = {}
    actions: dict[str, tuple[Gio.AppInfo, str]] = {}

    for info in Gio.AppInfo.get_all():
        if not info.should_show():
            continue
        identifier = info.get_id()
        name = info.get_display_name() or info.get_name()
        if not identifier or not name:
            continue
        # Die erste Kennung gewinnt. Gio liefert eine Kennung genau
        # einmal, aber der Rueckgabewert ist eine Liste und keine Menge -
        # und die Zuordnung unten muss eindeutig bleiben, sonst startet
        # der zweite Eintrag den ersten.
        if identifier in applications:
            continue
        icon = info.get_icon()
        icon_name = icon.to_string() if icon else None
        applications[identifier] = info
        entries.append(Entry(label=name, value=identifier, icon=icon_name,
                             keywords=keywords_of(info)))

        if not isinstance(info, Gio.DesktopAppInfo):
            continue
        for action in info.list_actions():
            title = info.get_action_name(action) or action
            actions[f"{identifier}{ACTION_MARK}{action}"] = (info, action)
            entries.append(Entry(
                label=f"{name}: {title}",
                value=f"{identifier}{ACTION_MARK}{action}",
                icon=icon_name,
                keywords=keywords_of(info)))

    return entries, applications, actions


def keywords_of(info: Gio.AppInfo) -> str:
    """Die Woerter, unter denen dieser Eintrag ausserdem zu finden ist.

    Keywords, GenericName und Comment - in dieser Reihenfolge und alle
    drei, weil alle drei fuer denselben Zweck da sind und Programme sich
    verschieden entscheiden: GNOME schreibt Keywords, aeltere Pakete nur
    Comment.

    Nur fuer .desktop-Eintraege: Gio.AppInfo ohne Datei dahinter - die
    aus create_from_commandline() - hat diese Felder nicht.
    """
    if not isinstance(info, Gio.DesktopAppInfo):
        return ""
    words = list(info.get_keywords() or [])
    for getter in (info.get_generic_name, info.get_description):
        value = getter()
        if value:
            words.append(value)
    return " ".join(words)


def run_command(command: str) -> None:
    """Eine Shell-Zeile starten und zurueckkommen - fuer `--show all`.

    Eine Aktion ist keine .desktop-Datei, sondern das, was in einer
    bind-Zeile steht: `grim -g "$(slurp)" - | satty -f -`. Also eine
    Shell, sonst waeren Pipe und Kommandoersetzung Argumente von grim.

    Ueber Gio und mit `sh -c`, aus GENAU den beiden Gruenden, die bei
    launch() unten stehen: g_app_info_launch() geht ueber
    gio-launch-desktop, das doppelt forkt und eine eigene Sitzung
    aufmacht - eine gestartete Anwendung haelt den Starter sonst am
    Leben -, und das "%%" ist kein Tippfehler, weil GIO die entstehende
    Exec-Zeile ein zweites Mal auf Platzhalter absucht.
    """
    argv = ["sh", "-c", command]
    Gio.AppInfo.create_from_commandline(
        " ".join(GLib.shell_quote(argument).replace("%", "%%")
                 for argument in argv),
        None, Gio.AppInfoCreateFlags.NONE).launch(None, None)


def launch_action(info: Gio.AppInfo, action: str) -> None:
    """Eine Desktop-Aktion starten.

    Ueber GIO und nicht ueber ihre Exec-Zeile: die Aktion kennt ihre
    eigene, GIO wertet die Platzhalter darin richtig aus, und der Weg
    ist derselbe, den jedes andere Menue dieses Schreibtischs nimmt.
    Terminal=true gibt es fuer eine Aktion nicht - die Spezifikation
    kennt in einer Aktionsgruppe nur Name, Icon und Exec.
    """
    info.launch_action(action, None)


def launch(info: Gio.AppInfo, terminal: str) -> None:
    """Starten und zurueckkommen, ohne auf das Kind zu warten.

    Der Starter beendet sich unmittelbar danach; das Kind wird von init
    uebernommen. Auf den Prozess zu warten hiesse, das Auswahlfenster so
    lange offen zu lassen, wie die gestartete Anwendung laeuft.

    DIE GESTARTETE ANWENDUNG ERBT stdout UND stderr, UND DAS BLEIBT SO
        Gemessen am 11.08.2026 an tests/menu/test_menu_headless.py: der
        Testrahmen las die Ausgabe des Starters aus einer Roehre und
        wartete 120 Sekunden, obwohl der Starter laengst fertig war -
        die gestartete Anwendung hielt das Ende der Roehre offen.

        Der Rueckfall darauf, die Stroeme vorher nach /dev/null zu
        biegen, waere schlimmer als das Problem: aus SUPER+SPACE
        gestartete Anwendungen schreiben ihre Meldungen dann nirgendwohin
        statt in Hyprlands Protokoll, wo man sie sucht. wofi hat sie
        genauso vererbt. Der Testrahmen schreibt jetzt in Dateien.
    """
    needs_terminal = False
    if isinstance(info, Gio.DesktopAppInfo):
        needs_terminal = info.get_boolean("Terminal")

    if not needs_terminal or not terminal:
        info.launch(None, None)
        return

    commandline = strip_field_codes(info.get_commandline() or "")
    if not commandline:
        info.launch(None, None)
        return

    # `-e` und nicht der blosse Anhang: kitty versteht beides, aber
    # foot, alacritty und xterm verstehen nur `-e`, und `terminal` ist
    # eine Einstellung, die jemand aendern darf.
    argv = [terminal, "-e", *GLib.shell_parse_argv(commandline)[1]]

    # Ueber Gio und nicht ueber Gio.Subprocess.new(), obwohl das der
    # kuerzere Weg waere.
    #
    # GEMESSEN am 11.08.2026, tests/menu/test_menu_headless.py:
    # Gio.Subprocess erbt stdin, stdout und stderr des Starters, und der
    # Starter beendet sich unmittelbar danach. Wer den Starter aus einer
    # Pipe heraus gestartet hat, wartet dann auf ein Ende der Ausgabe,
    # das erst kommt, wenn die gestartete ANWENDUNG sich beendet - der
    # Test lief in seine 120-Sekunden-Grenze.
    #
    # g_app_info_launch() geht ueber gio-launch-desktop, das doppelt
    # forkt und eine eigene Sitzung aufmacht. Damit nimmt der Weg fuer
    # Terminalanwendungen genau denselben Ausgang wie der darueber - und
    # eine gestartete Anwendung, die den Starter am Leben haelt, ist auch
    # ausserhalb eines Tests falsch.
    #
    # Das "%%" ist kein Tippfehler. Was hier entsteht, ist wieder eine
    # Exec-Zeile, und GIO wertet beim Starten die Platzhalter darin ein
    # zweites Mal aus. Ein Prozentzeichen, das in einem Pfad oder in
    # einem Argument steckt, waere dort ein Platzhalter - "%c" wuerde zum
    # Namen der Anwendung, "%i" zu einem "--icon" - und die
    # Anfuehrungszeichen von shell_quote() stuenden danach an der
    # falschen Stelle. Gemessen am 11.08.2026 mit einer Exec-Zeile
    # `... monitor %U %c %i` und abgeschalteter Bereinigung oben:
    #
    #     g-shell-error-quark: Text ended before matching quote was found
    #
    # In einer Exec-Zeile schreibt man ein wortwoertliches Prozentzeichen
    # als "%%"; genau das steht hier.
    Gio.AppInfo.create_from_commandline(
        " ".join(GLib.shell_quote(argument).replace("%", "%%")
                 for argument in argv),
        None, Gio.AppInfoCreateFlags.NONE).launch(None, None)
