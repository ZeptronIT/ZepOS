# SPDX-License-Identifier: GPL-3.0-or-later
"""Welche Anwendungen DIESE Maschine hat - gelesen, nicht geraten.

WARUM ES DIESES MODUL GIBT, MIT DATUM
    Der Nutzer will Anwendungen per Rechtsklick anheften und wieder
    abnehmen. Bis zum 20.08.2026 konnte er das eine davon gar nicht:
    settings.bar_order() prueft eine Anheftung gegen die AUSGELIEFERTE
    Auswahl (model.placeable_in(), Zweig BAR_PINS), und damit ist
    "anheften, was ZepOS nicht mitliefert" nicht abgelehnt worden,
    sondern unmoeglich gewesen - jeder andere Name fiel mit
    settings.BAR_UNKNOWN heraus.

    Die Auswahl zu weiten heisst, eine zweite Frage stellen zu koennen:
    nicht "liefert ZepOS das aus" (das beantwortet src/apps.py), sondern
    "GIBT es das auf dieser Maschine". Das ist eine Angabe ueber die
    Maschine und nicht ueber das Erzeugnis, und sie hat genau eine
    Quelle: das Anwendungsverzeichnis nach der Freedesktop-Spezifikation.

WARUM EIN EIGENES MODUL UND NICHT ZWEI FUNKTIONEN IN apps.py
    Weil apps.py etwas anderes beantwortet und das in seinem Kopf
    ausdruecklich sagt: "Die Frage 'welche Anwendungen liefert ZepOS
    aus' hat eine Antwort, und dieses Modul holt sie." Die Frage hier
    hat eine ANDERE Antwort, aus einer anderen Quelle, mit einem anderen
    Gueltigkeitsbereich - sie aendert sich, wenn jemand `pacman -R`
    tippt, waehrend die Auslieferung sich nur mit einer neuen Fassung
    von ZepOS aendert. Zwei Fragen in einer Datei waeren zwei Fragen mit
    einem Namen.

WARUM KEIN GIO, OBWOHL DAS DOCK GENAU DAS BENUTZT
    src/templates/ags-dock.template fragt GioUnix.DesktopAppInfo, und
    das ist dort richtig: AGS haelt ohnehin eine GLib-Hauptschleife.

    Hier darf kein `gi` stehen, aus demselben Grund, aus dem
    settings/zepos_settings_gui/model.py keins enthaelt: dieses Modul
    wird vom ERZEUGER gelesen (src/apps.py, aufgerufen aus
    src/generate_config.sh) und vom Einstellungsfenster, und beide
    muessen ohne laufende Anzeige messbar sein. Ein Import, der eine
    Typbibliothek braucht, macht aus jedem Test einen Test der
    Installation.

    Der Preis ist ein eigener Parser fuer eine INI-artige Datei, und er
    ist klein: gebraucht werden drei Schluessel aus einer Gruppe.

WAS "ES GIBT DIESE ANWENDUNG" HEISST - DREI BEDINGUNGEN, KEINE MEHR
    Type=Application    Ein `.desktop` kann auch ein Verzeichnis oder
                        eine Verknuepfung beschreiben. Beides ist kein
                        Programm, das ein Klick starten koennte.
    kein NoDisplay      Die Markierung, mit der die Spezifikation einen
                        DIENST von einer Anwendung unterscheidet. Genau
                        daran ist am 12.08.2026 das Zahnrad im Fuss
                        aufgefallen, das sich "garnicht oeffnen" liess:
                        xdg-desktop-portal-gnome traegt sie.
    kein Hidden         Die Spezifikation nennt das "geloescht": ein
                        Eintrag mit Hidden=true soll behandelt werden,
                        als laege die Datei gar nicht da. Ein
                        Benutzereintrag in ~/.local/share/applications
                        blendet damit einen aus /usr/share aus - wer das
                        getan hat, will ihn nicht im Dock.

    Ob das Programm der Exec-Zeile wirklich auf PATH liegt, wird NICHT
    geprueft. GIO prueft es (gemessen, siehe der Kopf von
    ags-dock.template), und das Dock laesst einen Eintrag ohne
    auffindbares Programm deshalb ohnehin weg. Es hier ein zweites Mal
    zu entscheiden hiesse, zwei Antworten auf eine Frage zu haben, und
    die zweite waere die schlechtere: `Exec=env FOO=1 /usr/bin/prog %U`
    ist eine Zeile, deren erstes Wort nicht das Programm ist.
"""
from __future__ import annotations

import os
from pathlib import Path

# Der Unterordner, in dem die Eintraege liegen - in jedem Datenverzeichnis
# derselbe. Steht als Name da, damit eine Umbenennung an einer Stelle
# auffiele statt an vier.
APPLICATIONS = "applications"

SUFFIX = ".desktop"

# Die Gruppe, in der die drei Schluessel stehen. Eine Datei kann weitere
# tragen ("Desktop Action new-window"), und die gehoeren einer AKTION und
# nicht der Anwendung: ein NoDisplay in einer Aktionsgruppe sagt nichts
# darueber, ob die Anwendung selbst eines ist.
GROUP = "[Desktop Entry]"

# Die Vorgaben der Freedesktop-Basisverzeichnis-Spezifikation. Sie stehen
# hier und nicht in paths.py, weil paths.py die Wurzeln DIESES Projekts
# beschreibt - das Systemwurzelverzeichnis und das Konto-Wurzelverzeichnis,
# beide unter einem eigenen Namen - und diese hier dem ganzen Schreibtisch
# gehoeren. Sie werden auch nie zu einem Pfad DIESES Projekts erweitert:
# was hier entsteht, ist immer <verzeichnis>/applications.
DATA_HOME_DEFAULT = Path(".local") / "share"
DATA_DIRS_DEFAULT = "/usr/local/share:/usr/share"

APPLICATION = "Application"
TYPE = "Type"
NO_DISPLAY = "NoDisplay"
HIDDEN = "Hidden"
NAME = "Name"

TRUE = "true"


def data_dirs() -> list[Path]:
    """Die Datenverzeichnisse dieses Kontos, in der Reihenfolge der Spec.

    Das eigene zuerst: ein Eintrag in ~/.local/share/applications
    ueberschreibt den gleichnamigen aus /usr/share/applications, und
    genau so blendet jemand einen Eintrag mit Hidden=true aus. Wer
    zuerst gefunden wird, GILT - deshalb wird hier nicht gesammelt,
    sondern abgebrochen (siehe entry_of()).

    Leere Eintraege in XDG_DATA_DIRS werden uebergangen, weil die Spec
    sie fuer unbesetzt erklaert: ein `XDG_DATA_DIRS=/usr/share:` ergaebe
    sonst einen Pfad "", und Path("")/"applications" ist das
    Arbeitsverzeichnis - also ein Verzeichnis, in dem ein Erzeugungslauf
    zufaellig etwas finden koennte.
    """
    home = os.environ.get("XDG_DATA_HOME")
    roots = [Path(home) if home else Path.home() / DATA_HOME_DEFAULT]

    listed = os.environ.get("XDG_DATA_DIRS") or DATA_DIRS_DEFAULT
    roots.extend(Path(part) for part in listed.split(":") if part)
    return [root / APPLICATIONS for root in roots]


def fields(path: Path) -> dict[str, str]:
    """Die Schluessel der Gruppe [Desktop Entry], als Abbildung.

    Nur DIESE Gruppe: bei der naechsten eckigen Klammer ist Schluss.

    Sprachvarianten werden auf ihren Grundnamen gezogen - `Name[de]`
    zaehlt als `Name`, und der erste gewinnt, weil die Spec den
    unbeschrifteten Schluessel zuerst verlangt. Ohne diese Zeile stuende
    bei einem uebersetzten Eintrag die zuletzt gelesene Sprache im
    Ergebnis, und welche das ist, entscheidet die Reihenfolge in der
    Datei.

    Eine Datei, die sich nicht lesen laesst, ergibt ein leeres
    Verzeichnis und keinen Wurf: sie gehoert nicht diesem Projekt, ein
    Erzeugungslauf darf an einem fremden kaputten Eintrag nicht
    abbrechen, und "leer" faellt unten ohnehin durch is_application().
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    found: dict[str, str] = {}
    inside = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            if inside:
                break
            inside = stripped == GROUP
            continue
        if not inside or not stripped or stripped.startswith("#"):
            continue
        key, sep, value = stripped.partition("=")
        if not sep:
            continue
        key = key.strip()
        bracket = key.find("[")
        if bracket != -1:
            key = key[:bracket]
        found.setdefault(key, value.strip())
    return found


def entry_of(name: str) -> Path | None:
    """Wo der Anwendungseintrag `name` liegt, oder None.

    `<verzeichnis>/<name>.desktop` und sonst nichts - dieselbe erste
    Frage, die entryFor() in ags-dock.template stellt
    (`GioUnix.DesktopAppInfo.new(`${name}.desktop`)`). Der zweite Versuch
    dort - ueber das Programm der Exec-Zeile - wird hier NICHT
    nachgebaut: er waere ein zweiter Rechenweg zu derselben Antwort, und
    er wird auch nicht gebraucht. Was ZepOS ausliefert, ist ohnehin
    anheftbar (settings.pinnable() vereinigt beide Listen); was der
    Nutzer selbst anheftet, heftet er ueber die Kennung an, unter der
    sein Schreibtisch den Eintrag fuehrt - und das IST der Dateiname
    ohne Endung.

    `name` kommt aus einer Einstellungsdatei, also aus fremder Hand, und
    wird wie in paths.find_template() behandelt: ein Name mit "/" darin
    oder mit einem Punkt am Anfang waere ein Pfad und kein Name.
    "../../etc/passwd" faende hier zwar nichts Ausfuehrbares, wuerde aber
    einen Lesezugriff ausserhalb der Anwendungsverzeichnisse ausloesen,
    und das ist eine Frage, die dieses Modul gar nicht erst stellen soll.
    """
    if not name or "/" in name or name.startswith("."):
        return None
    for directory in data_dirs():
        candidate = directory / f"{name}{SUFFIX}"
        if candidate.is_file():
            return candidate
    return None


def is_application(entry: dict[str, str]) -> bool:
    """Ob diese Felder eine Anwendung beschreiben - die drei Bedingungen.

    Fehlt `Type`, gilt der Eintrag NICHT als Anwendung. Die Spec nennt
    den Schluessel verpflichtend; eine Datei ohne ihn ist kaputt, und
    eine kaputte Datei als Anwendung zu zaehlen hiesse, einen Knopf
    anzubieten, hinter dem nichts passiert.
    """
    if entry.get(TYPE) != APPLICATION:
        return False
    if entry.get(NO_DISPLAY, "").lower() == TRUE:
        return False
    return entry.get(HIDDEN, "").lower() != TRUE


def installed(name: str) -> bool:
    """Ob `name` auf dieser Maschine als Anwendung anheftbar waere."""
    entry = entry_of(name)
    return entry is not None and is_application(fields(entry))


def label_of(name: str) -> str:
    """Wie der Eintrag heisst, oder leer.

    Fuer die Oberflaeche, die einen frisch angehefteten Namen anzeigen
    will, bevor GIO danach gefragt wurde. Leer und nicht der Name als
    Rueckfall: wer den Rueckfall braucht, hat ihn schon
    (settings.bar_labels() rechnet damit, dass eine Beschriftung fehlt),
    und zwei Rueckfaelle waeren zwei Beschriftungen.
    """
    entry = entry_of(name)
    return fields(entry).get(NAME, "") if entry is not None else ""


def names() -> list[str]:
    """Jede anheftbare Anwendung dieser Maschine, alphabetisch, ohne Doppel.

    Alphabetisch, weil ein Verzeichnisdurchlauf keine zugesagte
    Reihenfolge hat - dieselbe Begruendung wie bei apps.from_recipes().
    Diese Liste ist NIE eine Reihenfolge fuer das Dock; sie beantwortet
    nur, was ueberhaupt angenommen werden darf.

    Der ERSTE Fund gewinnt, wie in entry_of(): ein ausgeblendeter
    Eintrag in ~/.local/share/applications haelt den gleichnamigen aus
    /usr/share/applications heraus, statt von ihm ueberstimmt zu werden.
    """
    seen: dict[str, bool] = {}
    for directory in data_dirs():
        try:
            listed = sorted(directory.glob(f"*{SUFFIX}"))
        except OSError:
            continue
        for path in listed:
            name = path.name[:-len(SUFFIX)]
            if name in seen:
                continue
            seen[name] = is_application(fields(path))
    return sorted(name for name, usable in seen.items() if usable)
