# SPDX-License-Identifier: GPL-3.0-or-later
"""Was in der Liste steht, in welcher Reihenfolge, und was uebrig bleibt.

Ohne `gi`, mit Absicht: das hier ist der Teil, der falsch sein kann, ohne
dass ein Fenster aufgeht, und er muss deshalb in der Testumgebung dieses
Projekts laufen koennen - in der `gi` nicht installiert ist.

DIE REIHENFOLGE IST DREI ENTSCHEIDUNGEN, NICHT EINE
    1. Die Grundordnung: `sort_order=default` laesst die Zeilen so
       stehen, wie sie hereinkamen, `alphabetical` sortiert sie.

       Das ist kein Geschmack. network-manager-gui sortiert seine
       WLAN-Liste selbst nach Signalstaerke und setzt Ueberschriften
       dazwischen, cliphist-menu setzt seine Navigationszeilen nach oben,
       und beide uebergeben deshalb `--sort-order=default`. Ein
       Auswahlfenster, das darueber alphabetisch sortiert, zerlegt beide
       Menues in eine Liste, in der die Ueberschrift irgendwo in der
       Mitte steht.

    2. Das Zaehlwerk: was schon einmal gewaehlt wurde, steigt nach oben,
       das Haeufigste zuerst. Dafuer gibt es --cache-file.

    3. Der Filter aendert die Reihenfolge NICHT. Er entfernt nur. Eine
       Liste, die sich beim Tippen umsortiert, laesst den Pfeil nach
       unten auf etwas anderes zeigen, als der Nutzer gerade gesehen hat.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Entry:
    """Eine Zeile der Liste.

    `label` wird angezeigt und durchsucht, `value` geht nach stdout
    beziehungsweise benennt die zu startende Anwendung. Bei --dmenu sind
    beide dieselbe Zeichenkette; beim Starter ist `label` der Name der
    Anwendung und `value` ihre Desktop-Kennung, weil zwei Anwendungen
    denselben Namen tragen duerfen und das Zaehlwerk sie dann
    auseinanderhalten muss.

    `icon` ist das, was Gio.Icon.to_string() liefert - eine Zeichenkette
    also, keine GObject-Referenz. Sonst waere dieses Modul nicht mehr
    ohne `gi` zu laden, und damit nicht mehr zu testen.

    `hint` steht rechts in der Zeile und ist bei einer Aktion ihre Taste.
    Das ist der Punkt, an dem dieses Fenster mehr tut als ausfuehren: wer
    "bild" tippt und "Bildschirmfoto vom gewaehlten Bereich   SUPER + S"
    liest, hat beim naechsten Mal die Taste. Ein Starter, der nur
    startet, bringt einem Nutzer den Schreibtisch nie bei.
    """

    label: str
    value: str
    icon: str | None = None
    hint: str | None = None
    # Woraufhin diese Zeile ausserdem gefunden werden soll, ohne dass es
    # dasteht. Bei einer Anwendung sind das die Schluesselwoerter ihres
    # Eintrags.
    #
    # GEMELDET am 12.08.2026: "ich finde den display manager wie nwg
    # display nicht in der app suche". GEMESSEN am selben Tag:
    # settings/zepos-settings.desktop fuehrt seit seiner ersten Fassung
    # `Keywords=...;bildschirme;monitor;monitore;aufloesung;anordnung;
    # displays;` - dreizehn Woerter, sorgfaeltig gewaehlt, und KEIN
    # Leser. `searchable` gab nur `label` heraus, also den Namen
    # "Systemeinstellungen", und wer "display" tippte, fand nichts.
    #
    # Es ist derselbe Fehler wie ein Regler ohne Wirkung, nur andersherum:
    # eine Angabe, die jemand gepflegt hat und die niemand liest.
    keywords: str = ""

    @property
    def searchable(self) -> str:
        """Woraufhin gefiltert wird.

        Die Taste gehoert dazu, nicht nur der Text: wer sie halb im Kopf
        hat, tippt "super s" und will die Zeile finden, die er sucht.
        Umgekehrt wuerde ein Filter, der NUR den Text liest, genau bei
        dem Nutzer versagen, der sich an die Taste erinnert und nicht an
        ihren Namen.

        ZWEIMAL, MIT UND OHNE LEERZEICHEN, und das ist gemessen: die
        Taste wird als "SUPER + S" angezeigt, weil das lesbar ist, und
        getippt wird sie als "SUPER+S", weil man so ueber eine Taste
        schreibt. matches() vergleicht Teilzeichenketten - der Filter
        haette bei genau der Eingabe nichts gefunden, die am naechsten
        dran war.

        Nicht in matches() geloest, sondern hier: dieselbe Funktion
        filtert den Zwischenablageverlauf, und dort waeren Leerzeichen
        Teil des Textes, den jemand gesucht hat.
        """
        parts = [self.label]
        if self.hint:
            parts += [self.hint, self.hint.replace(" ", "")]
        if self.keywords:
            parts.append(self.keywords)
        return " ".join(parts)


def read_dmenu(stream) -> list[Entry]:
    """Zeilen von stdin, leere Zeilen weg.

    Leere Zeilen fallen raus, weil eine leere Zeile in der Liste
    ununterscheidbar von "abgebrochen" waere: jeder der fuenf Aufrufer
    prueft die Ausgabe mit `[ -n "$auswahl" ]`, also bedeutet die leere
    Zeichenkette dort bereits Abbruch. Eine waehlbare leere Zeile waere
    ein Klick, der wie Escape wirkt.

    Der Zeilenumbruch am Ende wird abgeschnitten, sonst nichts:
    cliphist stellt seinen Zeilen eine Kennung und einen Tabulator
    voran, und `cliphist decode` braucht genau diese Kennung zurueck.
    """
    entries: list[Entry] = []
    seen: set[str] = set()
    for raw in stream:
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        # Doppelte Zeilen erscheinen einmal. Der Zwischenablageverlauf
        # ist voll davon - wer denselben Text zweimal kopiert, hat ihn
        # zweimal im Verlauf - und zwei identische Zeilen sind zwei
        # Zeilen, zwischen denen niemand waehlen kann.
        if line in seen:
            continue
        seen.add(line)
        entries.append(Entry(label=line, value=line))
    return entries


def matches(label: str, query: str, insensitive: bool) -> bool:
    """Teilzeichenkette, so wie wofis `matching=contains`.

    Kein Fuzzy-Vergleich. Der Zwischenablageverlauf enthaelt beliebigen
    Text, und ein Fuzzy-Vergleich findet darin auf jede Eingabe fast
    alles - eine Liste, die nie kuerzer wird, ist keine Suche.
    """
    if not query:
        return True
    if insensitive:
        return query.casefold() in label.casefold()
    return query in label


def order(entries: list[Entry], sort_order: str,
          usage: dict[str, int]) -> list[Entry]:
    """Grundordnung, dann das Zaehlwerk darueber.

    Beide Sortierungen sind stabil, also behaelt alles mit gleicher
    Zaehlung die Grundordnung. Ohne Zaehlwerk - `--cache-file /dev/null` -
    ist `usage` leer und es bleibt bei der Grundordnung allein.
    """
    ordered = list(entries)
    if sort_order == "alphabetical":
        ordered.sort(key=lambda entry: entry.label.casefold())
    if usage:
        ordered.sort(key=lambda entry: -usage.get(entry.value, 0))
    return ordered


def read_usage(path: Path) -> dict[str, int]:
    """`<zahl> <wert>` je Zeile.

    /dev/null liest sich als leere Datei, und das ist der ganze Grund,
    aus dem `--cache-file /dev/null` funktioniert, ohne dass hier ein
    Sonderfall dafuer steht.

    Eine unlesbare oder zerschossene Datei ist kein Fehler, der das
    Fenster kostet: es ist ein Zaehlwerk. Was sich nicht lesen laesst,
    zaehlt eben nicht.
    """
    usage: dict[str, int] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return usage

    for line in text.splitlines():
        count, _, value = line.partition(" ")
        if not value:
            continue
        try:
            usage[value] = int(count)
        except ValueError:
            continue
    return usage


# Mehr Zeilen als das haelt keine Datei. Ohne Deckel waechst das
# Zaehlwerk der Zwischenablage mit jedem gewaehlten Text um eine Zeile
# und wird nie wieder kleiner - der Verlauf liefert bei jedem Aufruf
# andere Zeichenketten, also wird jede Zeile genau einmal gezaehlt und
# danach nie wieder gefunden.
USAGE_LIMIT = 200


def write_usage(path: Path, usage: dict[str, int], chosen: str) -> None:
    """Die Zaehlung fortschreiben.

    KEIN schreiben-und-umbenennen, obwohl das hier die uebliche Vorsicht
    waere: `--cache-file /dev/null` ist ein Zeichengeraet, und ein
    os.rename() auf /dev/null waere ein Fehler bei jedem einzelnen
    Aufruf von cliphist-menu.sh, network-manager-gui.sh und
    floating-window-manager. Ein halb geschriebenes Zaehlwerk kostet
    hoechstens eine Reihenfolge; ein Sonderfall fuer /dev/null kostet
    genau die Ehrlichkeit, mit der die Datei sonst gelesen wird.
    """
    counted = dict(usage)
    counted[chosen] = counted.get(chosen, 0) + 1

    ranked = sorted(counted.items(), key=lambda item: (-item[1], item[0]))
    del ranked[USAGE_LIMIT:]

    try:
        # Nur anlegen, was fehlt. `mkdir(exist_ok=True)` ueber ein
        # vorhandenes Verzeichnis ist zwar kein Fehler, aber ein
        # Schreibversuch auf einem fremden Pfad: bei
        # `--cache-file /dev/null` waere das ein mkdir auf /dev, bei
        # jedem einzelnen Aufruf der fuenf Skripte.
        if not path.parent.is_dir():
            path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for value, count in ranked:
                # Ein Wert mit Zeilenumbruch darin waere beim Lesen zwei
                # Zeilen, von denen die zweite eine Zahl sein muesste.
                # Kommt bei dmenu nicht vor - dort ist eine Zeile eine
                # Zeile - und beim Starter erst recht nicht.
                if "\n" in value:
                    continue
                handle.write(f"{count} {value}\n")
    except OSError:
        # Ein nicht schreibbares Zaehlwerk ist kein Grund, die getroffene
        # Auswahl nicht auszugeben. Der Aufrufer wartet auf stdout.
        pass
