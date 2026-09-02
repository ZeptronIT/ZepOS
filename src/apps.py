# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Anwendungsauswahl von ZepOS, gelesen statt abgeschrieben.

WARUM ES DIESES MODUL GIBT
    Der Nutzer am 11.08.2026: "die nwg dock unten geht nicht mehr dateien
    und datei manager ist auch nicht vorhanden und screenshot tool auch
    nicht es fehlt gefuehlt alles" - und danach: "es muss wie apple os
    funktionieren ist dir das klar".

    Das Dock, das nwg-dock-hyprland abgeloest hat, zeigte nur OFFENE
    FENSTER. Auf einem frischen Schreibtisch ist das nichts, und ein
    Kasten ohne Inhalt versteckte sich zusaetzlich selbst
    (`box.set_visible(clients.length > 0)`). Das abgeloeste Programm war
    ein STARTER mit angehefteten Anwendungen; beim Ersetzen ist diese
    Haelfte verlorengegangen.

    Ein Starter braucht eine Liste. Diese Liste GIBT ES SCHON, mit jeder
    Begruendung und jeder Messung, in packaging/zepos-apps/PKGBUILD. Sie
    ein zweites Mal hinzuschreiben waere die Art Kopie, die dieses
    Projekt an drei Stellen Catppuccin gekostet hat: der naechste, der
    eine Anwendung tauscht, tauscht sie an einer Stelle, und das Dock
    heftet ab da ein Programm an, das die Maschine nicht mehr hat.

DIE EINE LISTE UND IHRE ZWEI ABDRUECKE
    Getippt wird die Auswahl an genau EINER Stelle: dem `depends`-Array
    in packaging/zepos-apps/PKGBUILD. Dieses Modul liest sie an zwei
    Orten, weil es an zwei Orten laeuft, und beide Orte tragen denselben
    Satz:

      * IM CHECKOUT liegt das Rezept selbst neben src/. Dann wird es
        gelesen.
      * AUF EINER INSTALLATION gibt es kein packaging/. Dort liegt
        /usr/share/zepos/shipped-applications - eine Datei, die
        package() aus "${depends[@]}" SCHREIBT, also aus derselben
        Zeile, die im Checkout gelesen wird. Sie kann gar nicht
        abweichen; sie ist der Abdruck.

    Es gibt keinen dritten Ort und insbesondere keine Aufzaehlung in
    einer Vorlage. Die Frage "welche Anwendungen liefert ZepOS aus" hat
    eine Antwort, und dieses Modul holt sie.

WAS DIESES MODUL NICHT ENTSCHEIDET
    Welche der Namen ein FENSTER haben. Diese Unterscheidung faellt
    dort, wo sie messbar ist: im Dock selbst, an dem, was der
    Anwendungseintrag ueber sich selbst sagt.

    HIER STAND, `cups` und `xdg-desktop-portal-gnome` traegen keine
    .desktop-Datei und fielen deshalb von selbst heraus. Das war falsch,
    und der Irrtum hat den Nutzer ein Zahnrad gekostet, das nichts
    oeffnet. GEMESSEN am 12.08.2026 mit `pacman -Ql` gegen die Pakete
    des angehefteten Schnappschusses:

        cups                      /usr/share/applications/cups.desktop
        xdg-desktop-portal-gnome  /usr/share/applications/
                                  xdg-desktop-portal-gnome.desktop

    Beide tragen einen. Was den Portal-Eintrag trotzdem heraushaelt,
    ist `NoDisplay=true` - die Markierung, mit der die
    Freedesktop-Spezifikation einen Dienst von einer Anwendung
    unterscheidet. Sie steht in der Datei des Dienstes und nicht in
    einer Ausnahmeliste dieses Projekts, und ags-dock.template liest
    sie; dort steht die ganze Messung.

DIE ZWEITE HAELFTE DER FRAGE, UND SIE HAT EIN DATUM
    GEMELDET am 12.08.2026, nachdem ein Mensch das gebaute Medium
    benutzt hat: "das einstellungs icon im footer laesst sich garnicht
    oeffnen es erscheint nie".

    Sein erster Halbsatz war die Diagnose und nicht sein zweiter, und
    das ist am 12.08.2026 nachgemessen worden: EIN Zahnrad stand da, es
    war das des Portal-Dienstes (siehe oben), und es liess sich
    "garnicht oeffnen". Der zweite Halbsatz - "es erscheint nie" -
    beschreibt, was auf den Klick folgte, naemlich nichts.

    Die zweite Haelfte der Frage bleibt davon unberuehrt und ist genauso
    wahr: das Dock heftete ausschliesslich die Namen aus `depends` von
    zepos-apps an, und zepos-settings-gui steht dort nicht. Es kann dort
    auch nicht stehen: zepos-apps ist die Auswahl FREMDER Anwendungen,
    eine je Aufgabe, und sein eigener Kopf verbietet die Zeile
    ausdruecklich ("Eine Anwendung, die ZepOS selbst baut, gehoert dort
    nicht hinein"). Das echte Einstellungssymbol hat also gefehlt,
    waehrend eines dastand, das keines war - zwei Fehler, die sich
    gegenseitig verdeckt haben.

    Die Auswahl hat also zwei Haelften, und dieses Modul kannte nur
    eine. Die zweite ist genauso wenig eine Liste wie die erste - sie
    steht in den Rezepten, und zwar in genau der Zeile, mit der ein
    Paket seinen Anwendungseintrag ablegt:

        install -Dm644 ... "$pkgdir/usr/share/applications/<name>.desktop"

    Ein Programm, das ZepOS selbst baut und fuer das es einen Eintrag im
    Anwendungsverzeichnis ausliefert, IST eine Anwendung dieses Systems.
    Ein Programm ohne diese Zeile - zepos-menu, zepos-lock - ist eine
    Taste und gehoert auf kein Dock, und diese Unterscheidung muss
    niemand pflegen: sie steht schon da. zepos-logout gehoerte bis zum
    19.08.2026 (Aufgabe 26) in dieselbe Reihe; sein Nachfolger ist ein
    AGS-Fenster und baut ueberhaupt kein eigenes Programm mehr, das hier
    fehlen koennte.

    Auch hier zwei Abdruecke derselben Zeile. Im Checkout werden die
    Rezepte gelesen; auf einer Installation liegt
    /usr/share/zepos/own-applications, das package() von zepos-config
    aus demselben Ausdruck ueber dieselben Rezepte schreibt.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Flach importiert wie ueberall in src/: dieses Modul laeuft als Skript
# aus dem Systemwurzelverzeichnis und findet seine Geschwister dort.
import desktop_i18n
import settings
from desktop_i18n import _
from paths import user_root

# Wo package() den Abdruck ablegt, relativ zum Systemwurzelverzeichnis.
# Derselbe Ort, an dem auch die Module liegen, die ihn lesen: ein
# installiertes ZepOS hat /usr/share/zepos und sonst nichts von diesem
# Projekt.
IMPRINT = "shipped-applications"

# Wo package() von zepos-config den Abdruck der EIGENEN Anwendungen
# ablegt - derselbe Ort und dieselbe Bauart.
OWN_IMPRINT = "own-applications"

# Das Rezept, relativ zur Wurzel des Checkouts (also eine Ebene ueber
# src/).
RECIPE = Path("packaging") / "zepos-apps" / "PKGBUILD"

# Wo die Rezepte liegen, relativ zur selben Wurzel.
RECIPES = Path("packaging")

# Die Zeile, mit der ein Rezept einen Anwendungseintrag ablegt. Der
# Dateiname OHNE .desktop ist zugleich die Kennung, unter der GIO den
# Eintrag fuehrt - also genau der Name, mit dem das Dock ihn findet
# (GioUnix.DesktopAppInfo.new(`${name}.desktop`), erster Versuch).
DESKTOP_ENTRY = re.compile(
    r"usr/share/applications/([A-Za-z0-9][\w.+-]*)\.desktop")

# Der Name des Pakets, dessen depends die Auswahl IST. Steht hier, damit
# eine Umbenennung an einer Stelle auffaellt statt an keiner.
PACKAGE = "zepos-apps"

_DEPENDS_BLOCK = re.compile(r"^depends=\((.*?)^\)", re.S | re.M)
_QUOTED_NAME = re.compile(r"'([^']+)'")


def _uncommented(text: str) -> str:
    """Der Text ohne die Zeilen, die nur Kommentar sind.

    Ohne das liest jede Suche in diesem Rezept die Begruendungen mit, und
    die nennen jedes Programm, das ABGEWAEHLT wurde, beim Namen - thunar,
    chromium, sublime-text-4. Ein Dock, das die abgewaehlten anheftet,
    waere die schlechteste denkbare Umsetzung dieser Datei.
    """
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("#"))


def from_recipe(text: str) -> list[str]:
    """Die depends-Liste eines PKGBUILD-Textes, in ihrer Reihenfolge.

    Reihenfolge und nicht Menge: sie ist im Rezept nach Aufgaben
    gruppiert - Browser, Dateimanager, Archive, Bilder - und das ist
    genau die Reihenfolge, in der ein Dock sie zeigen soll. Eine Menge
    haette sie weggeworfen und das Dock haette bei jedem Lauf eine
    andere.
    """
    block = _DEPENDS_BLOCK.search(text)
    if not block:
        return []
    return _QUOTED_NAME.findall(_uncommented(block.group(1)))


def _recipe_path(system_root: Path) -> Path:
    """Wo das Rezept liegt, wenn dies ein Checkout ist.

    src/ liegt neben packaging/, also ist die Wurzel eine Ebene ueber dem
    Systemwurzelverzeichnis. Auf einer Installation zeigt derselbe
    Ausdruck auf /usr/share/packaging/... - das gibt es nicht, und genau
    deshalb steht unten eine Existenzpruefung und keine Annahme.
    """
    return system_root.parent / RECIPE


def _read_imprint(path: Path) -> list[str]:
    """Ein Abdruck, Zeile fuer Zeile, ohne Leerzeilen und Kommentare."""
    if not path.is_file():
        return []
    return [line.strip() for line in
            path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


def from_recipes(directory: Path) -> list[str]:
    """Die Anwendungseintraege, die die Rezepte in `directory` ablegen.

    Alphabetisch, und das ist die eine Stelle, an der diese Datei NICHT
    die Reihenfolge des Rezepts uebernimmt: ein Verzeichnisdurchlauf hat
    keine zugesagte Reihenfolge, und `sort -u` ist das, was der Abdruck
    auf einer Installation liefert. Zwei Abdruecke derselben Zeile
    muessen auch dieselbe Reihenfolge haben, sonst zeigt dasselbe System
    im Checkout ein anderes Dock als nach der Installation.

    Ohne die Kommentarzeilen, aus demselben Grund wie bei from_recipe():
    ein Rezept darf begruenden, welchen Eintrag es NICHT ablegt.
    """
    found: set[str] = set()
    for recipe in directory.glob("*/PKGBUILD"):
        text = _uncommented(recipe.read_text(encoding="utf-8"))
        found.update(DESKTOP_ENTRY.findall(text))
    return sorted(found)


def own(system_root: Path | None = None) -> list[str]:
    """Die Anwendungen, die ZepOS SELBST baut - siehe den Kopf.

    Dieselben zwei Orte wie bei shipped() und in derselben Reihenfolge:
    im Checkout die Rezepte, auf einer Installation der Abdruck.
    """
    root = Path(system_root) if system_root else Path(__file__).resolve().parent

    recipes = root.parent / RECIPES
    if recipes.is_dir():
        return from_recipes(recipes)

    return _read_imprint(root / OWN_IMPRINT)


def shipped(system_root: Path | None = None) -> list[str]:
    """Die Anwendungen, die ZepOS ausliefert - beide Haelften.

    Erst die ausgewaehlten fremden, dann die eigenen. Die Reihenfolge ist
    die, in der das Dock sie zeigt, und sie ist eine Entscheidung: links
    steht, womit man arbeitet, rechts das System. Ein Browser vor den
    Einstellungen ist dieselbe Anordnung, die jeder Schreibtisch hat, an
    dem der Nutzer ZepOS misst.

    Leer ist eine gueltige Antwort und heisst: auf dieser Maschine ist
    weder das Rezept noch der Abdruck zu finden. Der Aufrufer muss damit
    umgehen koennen - ein Dock ohne angeheftete Anwendungen ist immer
    noch ein Dock, und eine Ausnahme an dieser Stelle waere eine
    Sitzung, die nicht startet, weil eine Liste fehlt.
    """
    root = Path(system_root) if system_root else Path(__file__).resolve().parent

    recipe = _recipe_path(root)
    if recipe.is_file():
        foreign = from_recipe(recipe.read_text(encoding="utf-8"))
    else:
        foreign = _read_imprint(root / IMPRINT)

    # OHNE DOPPELTE, UND DAS IST KEINE VORSICHT, SONDERN EINE REPARATUR
    #
    # GEMELDET am 17.08.2026: "aktuell sind in der taskbar zwei claude
    # code icon was ich nicht moechte" - und, am selben Tag und aus
    # derselben Wurzel: "wenn ich auf den claude icon druecke spammt er
    # terminal mit claude auf die oberflaeche immer mehr bis alles
    # laggt".
    #
    # DIE UEBERSCHNEIDUNG WAR: zepos-claude-code stand in BEIDEN
    # Haelften. Bei den fremden, weil zepos-apps es in seinen
    # Abhaengigkeiten nannte - das war die Zeile, die es ueberhaupt
    # installierte. Bei den eigenen, weil es ein ZepOS-Paket war. Beides
    # war richtig; die Summe nicht.
    #
    # SEIT DEM 01.09.2026 GIBT ES GENAU DIESE UEBERSCHNEIDUNG NICHT
    # MEHR, und dieser Block bleibt trotzdem stehen. Der Nutzer hat das
    # Paket gestuerzt ("ich will das packet nicht als meins verkaufen");
    # der Eintrag im Starter kommt jetzt aus zepos-config und steht nur
    # noch in der EIGENEN Haelfte. Damit ist der Fall vom 17.08.2026
    # nicht mehr zu erreichen - aber die BEDINGUNG dafuer ist eine
    # Zeile in einem fremden Rezept, und die haelt niemand fest. Ein
    # Filter, der nichts findet, kostet einen Mengendurchlauf ueber
    # fuenfzehn Namen; ein fehlender kostete den Rechner des Nutzers.
    #
    # WARUM DAS MEHR KOSTET ALS EIN ZEICHEN ZU VIEL: das Dock fuehrt
    # seine Klick-Verbindungen in einer Tabelle, die nach dem
    # PROGRAMMNAMEN geschluesselt ist (`handlers` in
    # ags-dock.template). Zwei Eintraege mit demselben Namen heissen,
    # dass beim Auffrischen die Verbindung des FALSCHEN Knopfes getrennt
    # wird - der andere sammelt bei jedem Hyprland-Ereignis eine weitere
    # an. Nach ein paar hundert Ereignissen startet ein Klick ein paar
    # hundert Programme, und jedes neue Fenster erzeugt Ereignisse, die
    # weitere anhaengen.
    #
    # Der erste Platz gewinnt: die Reihenfolge ist eine Entscheidung
    # (siehe oben - links, womit man arbeitet), und ein Name, der spaeter
    # noch einmal faellt, soll nicht nach hinten wandern.
    gesehen: set[str] = set()
    ohne_doppelte: list[str] = []
    for name in foreign + own(root):
        if name in gesehen:
            continue
        gesehen.add(name)
        ohne_doppelte.append(name)
    return ohne_doppelte


# --------------------------------------------------------------------
# was der Nutzer daran aendert (Aufgabe #92)
# --------------------------------------------------------------------
#
# DIE DRITTE HAELFTE DERSELBEN FRAGE
#     "bar.dock_pins" in user-settings.json ist die Reihenfolge des
#     Nutzers; null heisst "wie ausgeliefert". Die Regeln dafuer - was
#     eine gueltige Liste ist, was mit einem unbekannten Namen passiert,
#     wie die Klage darueber lautet - stehen NICHT hier, sondern in
#     src/settings.py, weil die Einstellungs-Anwendung dieselbe Frage
#     stellt und beide dieselbe Antwort geben muessen. Ein Dock, das
#     einen Namen annimmt, den das Fenster verwirft, waere eine
#     Einstellung, die man sieht und nicht bekommt.
#
#     SIE ERSETZT DIE AUSLIEFERUNG NICHT MEHR - seit dem 20.08.2026
#         Bis dahin stand hier "ersetzt die ausgelieferte Reihenfolge
#         vollstaendig", und genau das war der Fehler: wer EINMAL ein
#         Symbol abgenommen hatte, sah nie wieder eine Anwendung, die
#         ZepOS spaeter dazugeliefert hat. Neben der Liste steht deshalb
#         jetzt "bar.dock_baseline", die Auslieferung von damals, und
#         settings.dock_effective() haengt an, was seither dazugekommen
#         ist. Die ganze Begruendung steht bei settings.BAR_BASELINE.
#
# WARUM EIN UNBEKANNTER NAME NICHT DURCHGEREICHT WIRD
#     Weil er im Dock ein Knopf waere, der nichts oeffnet - genau der
#     Fehler, den Aufgabe #93 gerade behoben hat. settings.bar_order()
#     verwirft ihn und sagt, warum; hier wird die Klage AUSGESPROCHEN
#     und nicht bloss abgeholt.

def imprint_pins(system_root: Path | None = None) -> list[dict[str, str]]:
    """Die ausgelieferten Anheftungen fuer /usr/share/zepos/shipped-bar.json.

    Zwei Felder je Eintrag, und jedes ist etwas anderes:

      name     der Paketname - das, was gespeichert wird, und das, was
               settings.bar_order() gegen die ausgelieferte Liste haelt.
      desktop  wo das Dock zuerst nachsieht (entryFor() in
               ags-dock.template versucht `<name>.desktop`). Es ist kein
               Versprechen: GNOME benennt seine Eintraege in Umkehr-DNS,
               und der zweite Versuch dort findet sie ueber das
               Programm der Exec-Zeile.

    ES WAREN DREI, UND DAS DRITTE IST AM 02.09.2026 WEGGEFALLEN
        `label` trug den sichtbaren Namen der EIGENEN Anwendungen, aus
        ihrer .desktop-Datei im Baum gelesen (`Name[de]=` zuerst,
        `Name=` als Rueckfall). Fuer die fremden stand dort "" - im
        Chroot liegt keine davon.

        Der Wert entstand BEIM BAUEN und konnte die Sprache des Nutzers
        grundsaetzlich nicht kennen: ein Paket wird in einem Chroot
        gebaut, lange vor jeder Anmeldung. Solange die einzige Flaeche,
        die ihn anzeigt, ausschliesslich Deutsch sprach - die
        Anheftungsauswahl im Einstellungsfenster -, war "Deutsch
        hineinbacken" die richtige Antwort. Seit dieses Fenster gettext
        ruft, ist es die falsche: der Wert waere die eine deutsche
        Beschriftung in einem englischen Fenster.

        WEGGELASSEN und nicht zweisprachig gemacht, weil der Rueckfall
        die Antwort schon HAT. bar.py:_entry_row() fragt in dieser
        Reihenfolge:

            machine   GIO auf DIESER Maschine (entry_for()) - und GIO
                      beachtet die Sprache der Sitzung von selbst
            labels    der Abdruck   <- diese Stelle
            name      der Paketname

        Fuer jeden Eintrag, den es auf der Maschine WIRKLICH gibt,
        antwortet GIO - der Abdruck kam nie zum Zug. Er kam nur dort
        zum Zug, wo GIO nichts findet, und das ist genau der Fall
        "Paket entfernt". Dort ist der PAKETNAME die ehrlichere Antwort
        als eine gebackene Uebersetzung eines Programms, das nicht mehr
        installiert ist.

        WAS DESHALB NICHT WEGFAELLT, und warum das kein toter Code ist:
        settings.bar_labels() LIEST den Abdruck, sie schreibt ihn nicht.
        Ein frisch erzeugter Abdruck traegt kein `label` mehr, und dann
        antwortet sie {} - ein fehlendes Feld behandelt sie wie ein
        leeres. Ein Rechner, der von 0.1.13 hochgezogen wird, hat den
        ALTEN Abdruck aber noch auf der Platte, bis der naechste
        Erzeugungslauf laeuft, und bis dahin gibt sie die Beschriftungen
        heraus, die dort stehen. Sie zu loeschen hiesse, diese Rechner
        zwischen Aktualisierung und Erzeugungslauf schlechter zu
        stellen, ohne dass jemand etwas davon haette.

        Dasselbe gilt fuer `labels` in bridge.py: das Feld gehoert zur
        AUSGABE von `--json get`, also zu einer veroeffentlichten
        Schnittstelle. Es verschwinden zu lassen ist eine Entscheidung
        ueber diese Schnittstelle und keine Aufraeumarbeit nebenbei.
    """
    root = Path(system_root) if system_root else Path(__file__).resolve().parent
    return [{"name": name, "desktop": f"{name}.desktop"}
            for name in shipped(root)]


def pinned(document: dict | None = None,
           system_root: Path | None = None) -> tuple[list[str], list[tuple[str, str]]]:
    """Was wirklich angeheftet wird, und was dabei verworfen wurde.

    Zwei Rueckgaben aus demselben Grund, aus dem settings.bar_order()
    zwei hat: ein verworfener Name muss gesagt werden. Siehe oben.
    """
    listed = shipped(system_root)
    if not document:
        return listed, []
    chosen = settings.bar_choice(document, settings.BAR_PINS)

    # ERST DIE HEUTIGE AUSLIEFERUNG DAZURECHNEN, DANN PRUEFEN
    #     dock_effective() haengt an, was ZepOS seit der hinterlegten
    #     Vorgabe dazugeliefert hat - siehe settings.BAR_BASELINE.
    #     VOR bar_order() und nicht danach: das Angehaengte ist eine
    #     Anheftung wie jede andere und muss durch dieselbe Pruefung,
    #     sonst stuende ein neu ausgeliefertes Programm im Dock, das
    #     diese Maschine gar nicht installiert hat.
    merged = settings.dock_effective(
        chosen, settings.bar_baseline(document), listed)

    # NICHT MEHR ZWEIMAL `listed`, UND DAS IST DER GANZE PUNKT VON #45
    #     bar_order() nimmt seit dem 12.08.2026 drei Listen: was diese
    #     Haelfte tragen KANN (`placeable`) und was ohne jede Einstellung
    #     darauf steht (`shipped`). Hier standen dafuer zweimal dieselbe
    #     Liste, mit der Begruendung, es gebe im Dock nichts, was ZepOS
    #     kennt und nicht ausliefert.
    #
    #     Das stimmte, solange nur ZepOS anheften durfte. Seit der Nutzer
    #     selbst anheftet, ist "was kann hier stehen" die Frage nach
    #     dieser MASCHINE und nicht nach dem Erzeugnis:
    #     settings.pinnable() vereinigt die Auslieferung mit dem, was
    #     src/desktop_entries.py im Anwendungsverzeichnis findet. Mit
    #     `listed` allein waere "anheften, was die Vorgabe nicht kennt"
    #     nicht abgelehnt, sondern unmoeglich.
    #
    #     Und `unknown=BAR_GONE`, weil die Ablehnung hier fast immer
    #     eine andere Ursache hat als auf der Leiste: nicht ein falscher
    #     Name, sondern ein deinstalliertes Programm. Es bleibt dabei in
    #     der Einstellungsdatei stehen - wer es wieder installiert,
    #     findet sein Symbol an seinem Platz wieder -, aber es wird
    #     nicht gezeichnet: ein Knopf, der nichts oeffnet, ist nach Spec
    #     7.4 der schlimmste Fehler, den ZepOS erzeugen kann.
    #
    # GEMESSEN AM 13.08.2026, UND ES HAT DAS SYSTEM UNBENUTZBAR GEMACHT
    #     Hier stand `bar_order(chosen, listed)`, also der Aufruf von
    #     vorher. Auf einer frischen Installation, im Sitzungsprotokoll:
    #
    #         TypeError: bar_order() missing 1 required positional
    #                    argument: 'shipped'
    #         Error: Pinned applications could not be resolved
    #         Total configs: 90   Successful: 89   Failed: 1
    #         zepos-generate --all rc=1
    #         !!! Sitzung nicht gestartet: der Starter wurde nicht erzeugt
    #
    #     Der Generator schreibt alles oder nichts. EINE von neunzig
    #     Konfigurationen genuegte, damit ~/.local/bin/start-hyprland nie
    #     entsteht - und ohne den beendet sich zepos-session mit exit 1,
    #     woraufhin greetd wieder die Anmeldung zeigt. Der Nutzer sah
    #     einen schwarzen Schirm und war zurueck bei der Anmeldemaske,
    #     endlos.
    #
    #     Die Signatur wurde geaendert, dieser Aufrufer nicht. Gefunden
    #     hat es kein Test, sondern ein Mensch auf echter Hardware; die
    #     Zusicherung darueber steht jetzt in
    #     tests/src/test_apps_pinned_call.py.
    return settings.bar_order(merged, settings.pinnable(listed), listed,
                              unknown=settings.BAR_GONE)


def user_document() -> dict:
    """Die Einstellungen dieses Kontos, oder {} - dieselbe Antwort wie im Erzeuger.

    KEINE DATEI und KEINE LESBARE DATEI sind zwei Antworten, und nur die
    erste ist normal; die Begruendung in ganzer Laenge steht bei
    style_definition._load_user_settings(). Ein Lauf, der eine kaputte
    Einstellungsdatei uebergeht, heftet still die ausgelieferte Auswahl
    an - also genau das, was der Nutzer weggestellt hatte.
    """
    target = user_root() / settings.FILENAME
    if not target.is_file():
        return {}
    return settings.load(target)


# --------------------------------------------------------------------
# die Marke im erzeugten Dock
# --------------------------------------------------------------------
#
# Dieselbe Form wie in src/plugins.py und aus demselben Grund: die
# Auswahl ist eine Angabe ueber DIESE Maschine und kein Platzhalter, den
# ein SSOT beantworten koennte. Der Prozessor kennt drei Praefixe -
# ICON_, STYLE_, ZEPOS_ -, und "welche Anwendungen liefert das Paket
# zepos-apps aus" gehoert in keinen davon. Also wird die erzeugte Datei
# nachbearbeitet, genau eine Zeile, an einer Marke, die dastehen MUSS.

MARKER = re.compile(r"^([ \t]*)const PINNED: string\[\] = .*//[ \t]*zepos-pinned[ \t]*$")


class MalformedTemplate(Exception):
    """Die Marke fehlt oder steht mehrfach da.

    Kein Grund weiterzumachen: ohne sie waere das erzeugte Dock ein Dock
    ohne angeheftete Anwendungen, also genau der Zustand, den diese
    Aenderung behebt - und es waere still. Ein Lauf, der hier abbricht,
    laesst die vorige Konfiguration stehen und sagt, warum.
    """


def render(text: str, *, names: list[str] | None = None) -> str:
    """Die Markenzeile, mit der ausgelieferten Auswahl darin.

    Die Namen gehen als JSON hinein und nicht ueber eine eigene
    Zeichenkettenformatierung: JSON ist eine echte Teilmenge von
    TypeScript-Literalen, und ein Paketname mit einem Anfuehrungszeichen
    darin waere sonst eine Datei, die der Buendler nicht mehr uebersetzt.
    """
    listed = shipped() if names is None else names

    lines = text.splitlines(keepends=True)
    hits = [index for index, line in enumerate(lines)
            if MARKER.match(line.rstrip("\n"))]
    if len(hits) != 1:
        raise MalformedTemplate(_(
            "the marker `// zepos-pinned` appears {count} times in it, "
            "exactly once is expected").format(count=len(hits)))

    index = hits[0]
    indent = MARKER.match(lines[index].rstrip("\n")).group(1)
    lines[index] = (f"{indent}const PINNED: string[] = "
                    f"{json.dumps(listed)}  // zepos-pinned\n")
    return "".join(lines)


USAGE = """usage: apps.py filter <file>

Setzt in einer erzeugten Datei die Zeile mit der Marke `// zepos-pinned`
auf die Anwendungsauswahl aus packaging/zepos-apps/PKGBUILD - im
Checkout aus dem Rezept, auf einer Installation aus dem Abdruck, den
dessen package() geschrieben hat.

Hat der Nutzer "bar.dock_pins" in user-settings.json gesetzt, steht
seine Reihenfolge darin, ergaenzt um alles, was ZepOS seit
"bar.dock_baseline" dazuliefert. Ein Name ohne Anwendungseintrag auf
dieser Maschine wird verworfen und auf der Fehlerausgabe genannt; in
der Einstellungsdatei bleibt er stehen."""


def main(argv: list[str] | None = None) -> int:
    # Der Katalog zuerst, wie in den anderen beiden Einstiegspunkten
    # dieser Oberflaeche. Dieser hier laeuft im CHROOT beim Bauen, wo
    # /etc/locale.conf regelmaessig gar nichts sagt - dann faellt
    # activate() auf die Quellsprache zurueck, und die Klagen unten
    # stehen englisch da. Das ist richtig so: sie gehen an den, der
    # baut, und im Baulauf ist Englisch die Sprache.
    desktop_i18n.activate()

    argv = list(sys.argv[1:] if argv is None else argv)
    if argv in (["-h"], ["--help"]):
        print(USAGE)
        return 0
    if len(argv) != 2 or argv[0] != "filter":
        print(USAGE, file=sys.stderr)
        return 2

    target = Path(argv[1])
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        print(_("{path} cannot be read: {problem}").format(
            path=target, problem=exc), file=sys.stderr)
        return 1

    # Derselbe Wurzelbegriff wie ueberall: der Generator reicht ihn in
    # der Umgebung durch, damit ein Lauf aus einem Checkout das Rezept
    # dieses Checkouts liest und nicht das eines installierten Pakets.
    root = os.environ.get("ZEPOS_SYSTEM_ROOT")
    # ValueError deckt UnusableSettings mit ab - es ist eine davon -, und
    # OSError den Fall, dass die Datei da ist und sich nicht lesen laesst.
    # Beides bricht ab, statt still die ausgelieferte Auswahl anzuheften:
    # ein Lauf, der die Einstellungen uebergeht und "erfolgreich erzeugt"
    # meldet, hinterlaesst ein Dock, das vollstaendig richtig aussieht
    # und nicht das eingestellte ist.
    try:
        names, discarded = pinned(user_document(), Path(root) if root else None)
    except (ValueError, OSError) as exc:
        print(f"{target}: {exc}", file=sys.stderr)
        return 1

    # Auf die FEHLERausgabe, weil generate_config.sh seine Erfolgszeilen
    # auf die Standardausgabe schreibt und eine Klage, die dazwischen
    # steht, wie eine davon aussieht.
    if discarded:
        print(settings.bar_complaint(settings.BAR_PINS, discarded),
              file=sys.stderr)

    try:
        rendered = render(text, names=names)
    except MalformedTemplate as exc:
        print(f"{target}: {exc}", file=sys.stderr)
        return 1

    try:
        target.write_text(rendered, encoding="utf-8")
    except OSError as exc:
        print(_("{path} cannot be written: {problem}").format(
            path=target, problem=exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
