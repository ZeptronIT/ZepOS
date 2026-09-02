# SPDX-License-Identifier: GPL-3.0-or-later
"""Was die Einstellungs-Anwendung anbietet, und was ein Speichern bewirkt.

Kein `gi` in dieser Datei. Jede Entscheidung - welche Regler es gibt,
welche Grenzen sie haben, was in welche Datei geschrieben wird, was nach
dem Schreiben noch passieren muss - steht hier, damit sie ohne Anzeige
gemessen werden kann. app.py darf einen Wert von einem Widget ablesen und
hier hineinreichen und ein Ergebnis in eine Beschriftung schreiben, mehr
nicht. Dieselbe Trennung wie zwischen installer/gui/app.py und
installer/gui/pages.py, und aus demselben Grund.


DER UMFANG, UND WAS ABSICHTLICH FEHLT
    Es gibt 559 Stilplatzhalter, 50 einstellbare Groessen (27 benannte
    und 23 Sprossen der zwei Leitern), siebzig Farben, einen Wetterort, die
    Aktualisierungseinstellungen und die Monitorprofile. Eine Anwendung
    mit 559 Reglern findet niemand; eine mit dreien reicht nicht. Die
    Auswahl hier folgt EINER Regel:

        Angeboten wird, was ein Mensch an seinem eigenen Schreibtisch
        aendert, was beim Aendern ein erzeugtes Byte bewegt, und wovon
        die Anwendung sagen kann, was es kostet.

    Was das AUFNIMMT:

      Bewegung   Ein Schalter (sizes.motion). Er ist NICHT Geschmack:
                 bewegte Flaechen loesen bei einer vestibulaeren
                 Stoerung Schwindel aus, und bis zum 12.08.2026 gab es
                 auf diesem System keinen Weg, sie abzustellen. Er
                 erreicht beide Seiten - Hyprlands `animations
                 { enabled }` und GTKs `gtk-enable-animations`, also
                 auch die fremden Fenster.
      Groesse    Ein Regler (sizes.scale) und fuenf benannte Ausnahmen.
                 Der Nutzer hat ihn selbst genannt ("das style groesser
                 machen ... aber voll anpassbar", 11.08.2026), und er
                 war bis heute das einzige, was man ueberhaupt nicht
                 ohne Terminal aendern konnte: der Stil-Editor im
                 Schreibtisch kennt `sizes` nicht - GEMESSEN am
                 12.08.2026, kein einziger Treffer in
                 ags-style-editor.template.
      Thema      Die Palette, unter der alle siebzig Farben liegen.
                 Sie gehoert der MASCHINE und nicht diesem Konto, weil
                 der Anmeldebildschirm dazugehoert und vor jedem Konto
                 steht - der Kopf von src/theme.py fuehrt die Messung.
                 Deshalb steht sie auf derselben Seite wie die
                 Aktualisierung und wird ueber denselben Weg
                 geschrieben.
      Farben     Alle siebzig, in den Gruppen aus brand.COLOR_GROUPS.
                 Es waren neunundneunzig, bis diese Regel auf sie
                 angewandt wurde: neunundzwanzig davon veraenderten kein
                 erzeugtes Byte und sind mit ihren Platzhaltern
                 geloescht. Der Stil-Editor im Schreibtisch hatte sie
                 alle angeboten. Die Messung steht im Kopf von
                 src/brand.py, und tests/settings/test_settings_model.py rechnet
                 sie bei jedem Lauf nach.
      Wetter     Der Ort. Ein Feld, und das einzige, das etwas ueber
                 diese Maschine an einen Dritten schickt.
      Aktual.    Ob, was und wie laut. Die Datei gehoert der Maschine,
                 nicht diesem Konto - siehe update_settings() unten.

    Was es NICHT aufnimmt, und warum:

      Die Rollen der vier Leitern
                 Sieben Schriftrollen (MICRO bis HERO), dieselben sieben
                 als Symbolgroesse, drei Rundungen und drei Dauern -
                 zwanzig Sprossen. Sie EINZELN anzubieten waere der
                 Katalog noch einmal, nur mit Reglern davor, und genau
                 der ist am 12.08.2026 abgeschafft worden: sechzehn
                 Schriftgroessen, nach ihren Pixelwerten benannt, von
                 denen die vier haeufigsten einen Pixel auseinanderlagen.
                 Der Regler oben bewegt alle zwanzig, und er bewegt sie
                 IM VERHAELTNIS - das ist der Unterschied zwischen einer
                 Skala und einer Liste.

                 Auch einzeln NICHT angeboten: die Rundungen. Sie tragen
                 die Form der Marke, so wie die Farben ihren Ton tragen,
                 und ein 5er neben einem 13er Radius auf derselben
                 Flaeche sieht nach Versehen aus, egal wie gut die
                 Unschaerfe darunter ist. Die eine Ausnahme steht unten
                 als Drehknopf: STYLE_WINDOW_ROUNDING, weil eine
                 Fensterecke das einzige an dieser Leiter ist, das ein
                 Mensch von sich aus sucht.
      Die 50 Groessen einzeln
                 Fuenf davon stehen unten als DIALS. Von den uebrigen 45
                 sind 23 Sprossen der Schrift- und der Abstandsleiter -
                 die bewegt der eine Regler, und sie EINZELN anzubieten
                 hiesse, die Leiter wieder abzuschaffen, fuer die es
                 GEMESSENE Gruende gibt (src/sizes.py: 294 Abstandszahlen
                 in elf Werten, bevor es sie gab). Die restlichen 22
                 heissen STYLE_LAUNCHER_ROW_MIN_HEIGHT oder
                 STYLE_HYPRBARS_BUTTON_SIZE - das ist die Sprache der
                 Vorlagen und nicht die eines Menschen, und wer sie
                 sucht, sucht sie nicht in einem Fenster. Sie bleiben
                 vollstaendig erreichbar: `zepos-settings get sizes` und
                 `user_settings.py list-sizes` zaehlen alle 50 auf, mit
                 dem Wert, den sie gerade haben. Die Anwendung sagt das
                 auf der Seite selbst, damit "hier nicht" nicht wie
                 "gar nicht" aussieht.
      widget_sizes
                 Breite und Hoehe der zehn Ueberlagerungsfenster, je
                 Aufloesungsklasse. Der Stil-Editor im Schreibtisch hat
                 sie bereits, mit dem Fenster daneben, dessen Groesse
                 man einstellt. Ein zweiter Weg dorthin waere kein
                 zweiter Speicherort - beide schreiben durch
                 settings.merge() -, aber er waere ein zweiter Ort zum
                 Suchen.
      VPN, Ton, Uhren
                 Alle drei haben schon eine Oberflaeche: die
                 VPN-Einstellungen im Schreibtisch, die
                 Kontrollzentrale. Eine Einstellungs-Anwendung, die sie
                 nachbaut, verdoppelt Pflege statt Auffindbarkeit zu
                 schaffen.

    Und was am 12.08.2026 DAZUGEKOMMEN ist:

      Bildschirme
                 Sie standen in der Zeile darueber, mit derselben
                 Begruendung und dem Namen nwg-displays dahinter. Das war
                 das letzte GTK3-Programm dieses Systems, und es ist
                 entfernt - womit die Monitore keine Oberflaeche mehr
                 hatten. Die Regel oben trifft auf sie in allen drei
                 Teilen zu: ein Mensch aendert sie an seinem eigenen
                 Schreibtisch, es bewegt ~/.config/hypr/monitors.conf,
                 und die Anwendung kann sagen, was es kostet.

                 Die Seite ist settings/zepos_settings_gui/screens.py,
                 die Entscheidungen dahinter stehen in src/displays.py.
                 Sie haengt NICHT am Speichern-Knopf oben, aus demselben
                 Grund wie Thema und Aktualisierung: sie schreibt nicht
                 in user-settings.json.

      Leiste     Welche Module auf der Leiste stehen, in welcher
                 Reihenfolge, und was im Dock angeheftet ist.

                 GEMELDET am 12.08.2026: "im footer war ein
                 einstellungs icon was man nicht oeffnen konnte genau
                 sowas will ich im ZepOS zu customizen wenn du
                 verstehst". GEMESSEN am selben Tag: die zwoelf Namen
                 rechts standen in src/style_definition.py, die fuenf
                 links in src/templates/ags-bar.template, die
                 Anheftungen kamen ueber src/apps.py aus einem
                 PKGBUILD - drei Dateien, die auf einer Installation
                 gar nicht liegen, und keine Einstellung dazu.

                 Die Regel oben trifft in allen drei Teilen zu: ein
                 Mensch aendert das an seinem eigenen Schreibtisch, es
                 bewegt die erzeugte Bar.tsx, und die Anwendung kann
                 sagen, was es kostet - denselben Erzeugungslauf wie
                 jede Groesse. Die Seite ist
                 settings/zepos_settings_gui/bar.py, der Abschnitt und
                 seine Regeln stehen in src/settings.py.


WAS NACH DEM SPEICHERN PASSIERT - DIE FRAGE, DIE DIESE DATEI ENTSCHEIDET
    Eine geaenderte Groesse wirkt erst, wenn die Konfiguration neu
    erzeugt wird. GEMESSEN in src/generate_config.sh: ein vollstaendiger
    Lauf ruft `ags quit`, wartet zwei Sekunden auf das Ende des
    Prozesses, schiesst notfalls mit -9 nach und startet AGS neu. Auf
    einem laufenden Schreibtisch heisst das: die Leiste, das Dock und
    jedes Ueberlagerungsfenster verschwinden und kommen wieder. Am
    11.08.2026 ist genau das dem Nutzer mitten in der Arbeit passiert,
    und src/update.py hat daraus bereits die Regel gezogen, dass ein
    Hintergrunddienst so etwas nicht tun darf.

    Die drei denkbaren Antworten und warum es die dritte geworden ist:

      sofort anwenden      Waere ein Eingriff, den der Nutzer nicht
                           bestellt hat: er hat einen Regler bewegt,
                           nicht "starte meine Leiste neu" gesagt.
      nur speichern        Waere eine Einstellung, die nie ankommt.
                           Nichts erzeugt von selbst neu - zepos-session
                           tut es bei der ERSTEN Anmeldung und nach
                           einer Paketaktualisierung, und eine geaenderte
                           Einstellung ist keins von beidem. Das ist die
                           Reglertabelle, die kein erzeugtes Byte
                           veraendert, nur diesmal auf dem Weg dorthin.
      speichern und fragen So ist es. Gespeichert wird sofort und
                           immer, und dabei wird
                           paths.session_regenerate_marker() abgelegt:
                           damit ist die Aenderung spaetestens bei der
                           naechsten Anmeldung da, ohne dass jemand
                           etwas anklickt. Wer nicht warten will, waehlt
                           "Jetzt anwenden" - dann laeuft der Generator,
                           die Marke wird weggeraeumt, und die
                           Anwendung sagt VORHER, was das kostet.

    Die Marke ist der Teil, ohne den "beim naechsten Anmelden" eine
    Behauptung waere. src/bin/zepos-session liest sie und loescht sie.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import brand
import paths
import region
import settings as settings_file
import sizes
import theme
import update

Runner = Callable[..., "subprocess.CompletedProcess"]


# --------------------------------------------------------------------
# Die Groesse
# --------------------------------------------------------------------

# Die Grenzen des einen Reglers.
#
# UNTEN 1.0, weil das die Groesse vor dem 11.08.2026 ist - der Zustand,
# in den `zepos-settings set sizes.scale 1.0` zurueckfuehrt, und damit
# der kleinste, den irgendjemand je gesehen hat. Kleiner waere kein
# Rueckweg, sondern Neuland: sizes.value_of() rundet auf mindestens 1 px
# ab, eine Leiste von 1 px traegt keinen Knopf, und der Weg zurueck
# fuehrt durch genau diese Oberflaeche.
#
# OBEN 3.0. Der ausgelieferte Faktor ist 24/13 = 1.85 (die Schrift des
# Startmenues), also liegt er in der unteren Haelfte und es bleibt Luft
# nach oben. 3.0 macht aus der Grundschrift 39 px und aus der
# Seitenleiste 300 px - auf einem 1920 breiten Schirm ein Sechstel der
# Breite. Mehr waere eine Leiste, die den Schreibtisch auffrisst.
SCALE_MINIMUM = 1.0
SCALE_MAXIMUM = 3.0

# Die Schrittweite des Reglers. Ein Hundertstel waere feiner als das
# Ergebnis: die Grundschrift ist 13 px, ein Hundertstel Faktor bewegt sie
# um 0.13 px, und sizes.value_of() rundet auf ganze Pixel - hundert
# Stellungen des Reglers erzeugten also dieselbe Zahl. Ein Zwanzigstel
# bewegt sie um 0.65 px, so dass jeder zweite Schritt sichtbar wird.
SCALE_STEP = 0.05


@dataclass(frozen=True)
class Dial:
    """Eine benannte Groesse, die ihren eigenen Grund hat.

    `name` ist der Platzhalter aus sizes.TABLE - der Test dazu prueft
    ihn gegen die Tabelle, damit ein Tippfehler hier nicht zu einem
    Regler wird, der nichts erreicht. `also` sind weitere Platzhalter,
    die MIT gesetzt werden muessen, damit eine Zusicherung erhalten
    bleibt; `ratio` sagt, in welchem Verhaeltnis.
    """

    name: str
    label: str
    note: str
    minimum: int
    maximum: int
    also: tuple[tuple[str, float], ...] = ()


# WARUM FUENF UND NICHT NEUNUNDZWANZIG, UND WARUM NICHT NULL
#
# Der eine Regler oben beantwortet die Frage "alles groesser" - und das
# ist die Frage, die gestellt wurde. Diese fuenf sind die Ausnahmen, die
# einen eigenen Grund haben, VON ihm abzuweichen; jede davon steht in
# src/sizes.py bereits mit dieser Begruendung.
#
# Was sie NICHT sind: eine Auswahl nach Geschmack. Die uebrigen 24
# Eintraege der Tabelle sind Innenmasse von Fenstern, die diese
# Anwendung nicht zeigt, und sie tragen den Namen des Platzhalters, den
# sie setzen. Wer sie braucht, findet sie ueber `list-sizes`.
DIALS: tuple[Dial, ...] = (
    Dial(
        "STYLE_TERMINAL_FONT_SIZE",
        "Schrift im Terminal",
        "In Punkt, weil kitty nur Punkt entgegennimmt. Folgt sonst dem "
        "Regler oben - hier stand einmal eine 7.0, also 9 Pixel, in "
        "einem Schreibtisch, der überall sonst 24 zeigte.",
        6, 40),
    Dial(
        "STYLE_BAR_THICKNESS",
        "Dicke der Leiste",
        "Und damit auch die des Fusses - beide Streifen sind gleich "
        "hoch, und die Symbole im Dock folgen dieser Zahl. Zu schmal, "
        "und die Leiste schneidet ihre eigenen Module ab.",
        60, 400),
    Dial(
        "STYLE_DOCK_ICON_SIZE",
        "Symbole im Dock",
        "Normalerweise abgeleitet: der Fuss ist genauso hoch wie die "
        "Leiste, und das Symbol füllt ihn aus. Wer hier eine Zahl "
        "nennt, hat danach zwei verschieden hohe Streifen.",
        16, 128),
    Dial(
        "STYLE_GAPS_IN",
        "Abstand der Fenster",
        "Zwischen zwei Fenstern wird das Doppelte davon sichtbar, weil "
        "Hyprland den inneren Abstand an JEDE Seite legt; zum Schirmrand "
        "und um die Leiste herum ebenfalls das Doppelte. So ist der "
        "Abstand überall derselbe.",
        0, 32),
    Dial(
        "STYLE_WINDOW_ROUNDING",
        "Eckenrundung der Fenster",
        "Dieselbe Sprosse wie die Rundung der Module in der Leiste, "
        "damit ein Fenster und eine Kachel erkennbar aus demselben "
        "Baukasten kommen. 0 sind quadratische Ecken.",
        0, 32),
)


def _unit(name: str) -> str:
    return sizes.TABLE[name].unit


def size_number(text: str) -> float:
    """Die Zahl aus einem erzeugten Groessenwert, ohne seine Einheit.

    sizes.value_of() liefert "24px" oder "24", je nachdem, wer den Wert
    liest - ein Stylesheet oder Hyprland. Ein Drehknopf braucht eine
    Zahl, und die Einheit wieder anzuhaengen ist Sache von
    size_text() unten.
    """
    digits = text.strip().rstrip("pxPX").strip()
    return float(digits)


def size_text(name: str, value: float) -> str:
    """Was fuer diese Groesse in die Einstellungsdatei geschrieben wird.

    Mit der Einheit, die die Tabelle fuer sie vorsieht: die Stylesheets
    brauchen das "px", und ags-bar.template und
    hyprland-universal-config.template scheitern daran - im ersten Fall
    waere `const BAR_THICKNESS = 92px` ein Syntaxfehler, der die ganze
    Leiste kostet.

    Ganzzahlig, wo es ganzzahlig sein kann: "18.0px" ist gueltiges CSS
    und liest sich in einer erzeugten Datei wie ein Fehler.
    """
    if value == int(value):
        return f"{int(value)}{_unit(name)}"
    return f"{value:g}{_unit(name)}"


# Die Beschriftungen der vier Bedienelemente, die keine eigene Tabelle
# haben - die fuenf Ausnahmen tragen ihre in DIALS, die Farben in
# brand.COLOR_GROUPS, die Leistenhaelften in BAR_SIDES, die
# Aktualisierung in UPDATE_LABELS weiter unten.
#
# WARUM SIE HIER STEHEN UND NICHT IN app.py, WO SIE HERKOMMEN
#     Seit dem 19.08.2026 gibt es einen zweiten Leser: bridge.py
#     schreibt dieselben Bedienelemente als JSON heraus, damit das
#     AGS-Fenster sie zeichnen kann, ohne sie noch einmal zu
#     definieren. Eine Beschriftung, die in app.py steht, muesste dort
#     abgeschrieben werden - und ab dem ersten Umformulieren hiesse
#     derselbe Regler in zwei Fenstern verschieden.
#
#     Die langen BESCHREIBUNGEN daneben sind am 19.08.2026 (Aufgabe 29)
#     zunaechst in app.py geblieben, weil sie an libadwaitas Gruppen und
#     Zeilen hingen (Adw.PreferencesGroup description, ActionRow
#     subtitle), also an eine Aufteilung, die ein anderes Fenster nicht
#     hat. Der Bericht dieser Aufgabe sagte dazu: "Wer sie dort braucht,
#     hebt sie einzeln hierher - eine Zeile, die nichts als ihren Ort
#     aendert." Genau das ist am selben Tag (Aufgabe 32, das AGS-Fenster)
#     passiert - siehe NOTE_* weiter unten.
LABEL_SCALE = "Größe des Schreibtischs"
LABEL_MOTION = "Bewegung zeigen"
LABEL_WEATHER = "Ort"
LABEL_THEME = "Thema dieses Rechners"


# --------------------------------------------------------------------
# Die Prosa der Seiten
# --------------------------------------------------------------------
#
# NACHGETRAGEN am 19.08.2026 (Aufgabe 32, das AGS-Einstellungsfenster).
#
# WARUM SIE HIERHER GEHOERT UND NICHT IN EIN FENSTER
#     Bis heute standen diese Texte als `Adw.PreferencesGroup(
#     description=...)` und `Adw.ActionRow(subtitle=...)` in app.py -
#     also in EINEM der beiden Fenster. Das AGS-Fenster haette sie
#     abschreiben muessen, und zwei Fassungen desselben Satzes driften
#     ab der ersten Umformulierung: der Nutzer liest dann je nach
#     Fenster eine andere Begruendung fuer denselben Regler.
#
#     Sie sind WOERTLICH aus app.py hierhergezogen und nicht neu
#     formuliert worden - eine Zeile, die nichts als ihren Ort aendert.
#     app.py liest sie seither von hier, bridge.py schreibt sie ins
#     JSON, das AGS-Fenster zeichnet sie. Eine Quelle, drei Leser.
#
# WARUM ZWEI DAVON FUNKTIONEN SIND
#     Thema und Aktualisierung sagen im letzten Satz, ob DIESES Konto
#     die Maschinendatei schreiben darf. Das ist keine Formulierung,
#     sondern eine Messung (theme_writable()/update_writable()), und
#     sie faellt auf jeder Maschine anders aus. Eine Konstante koennte
#     nur eine der beiden Lagen tragen.

# Die acht Transformationen von wl_output, in der Reihenfolge ihrer
# Nummern - der Index IST der Wert, der in die Zeile kommt.
#
# HIER SEIT DEM 19.08.2026 (Aufgabe 32) UND NICHT MEHR IN screens.py:
# bridge.py schreibt diese Liste ins JSON, und bridge.py darf screens.py
# nicht importieren - die Datei ist ein Gtk.Box und zieht `gi` herein,
# also genau das, wovon `--json get` frei sein muss.
TRANSFORMS = (
    "Normal",
    "90 Grad",
    "180 Grad (auf dem Kopf)",
    "270 Grad",
    "Gespiegelt",
    "Gespiegelt, 90 Grad",
    "Gespiegelt, 180 Grad",
    "Gespiegelt, 270 Grad",
)

# Die Massstaebe, die angeboten werden.
#
# Eine Liste und kein Drehknopf, und das ist eine Messung: Hyprland lehnt
# einen Massstab ab, bei dem Breite oder Hoehe nicht ganzzahlig aufgehen,
# und meldet das als Konfigurationsfehler. Ein Drehknopf in Schritten von
# 0.05 boete ueber dreissig Zahlen an, von denen die meisten fuer einen
# gegebenen Schirm falsch sind. Diese sechs sind Vielfache von 1/4 und
# gehen auf jeder gaengigen Aufloesung auf.
SCALES = (1.0, 1.25, 1.5, 1.75, 2.0, 3.0)


# Die Ueberschriften der Gruppen, aus demselben Grund wie die Texte
# darunter: das AGS-Fenster setzt dieselben Ueberschriften ueber
# dieselben Regler (zepSectionLabel, ags-kit.template), und eine
# Ueberschrift, die in app.py steht, waere dort abgeschrieben.
GROUP_SCALE = "Maßstab"
GROUP_DIALS = "Ausnahmen"
GROUP_MOTION = "Bewegung"
GROUP_THEME = "Thema"
GROUP_WEATHER = "Wetter in der Leiste"
GROUP_UPDATE = "Selbstaktualisierung"

NOTE_SCALE_GROUP = (
    "Ein Faktor auf alles, was Text ist oder Text umschliesst: "
    "die Schrift, die Zeilenhöhen, die Dicke der Leiste. "
    f"{sizes.SCALE_DEFAULT:.4g} ist die ausgelieferte Größe - "
    "dieselbe, in der das Startmenue schreibt. 1 ist die "
    "Größe davor.")

NOTE_SCALE_RESET = (
    f"Stellt den Faktor auf {sizes.SCALE_DEFAULT:.4g} und gibt jede "
    "Ausnahme unten wieder an ihn zurück.")

NOTE_DIALS_GROUP = (
    "Fünf Größen mit einem eigenen Grund, vom Faktor abzuweichen. "
    "Wer hier eine Zahl nennt, sagt, was auf dem Schirm stehen soll - "
    "der Faktor gilt für sie dann nicht mehr.")

# Die drei Dauern werden GELESEN und nicht genannt: sie stehen in
# sizes.py, und eine abgeschriebene Millisekundenzahl hier waere beim
# naechsten Verstellen dort falsch.
NOTE_MOTION_GROUP = (
    "Eine Kurve und drei Dauern - "
    + ", ".join(sizes.value_of(f"{sizes.MOTION_PREFIX}{role}", {})
                for role, _ in sizes.MOTION_ROLES)
    + ". Sie folgen dem Faktor NICHT: wer die Schrift verdoppelt, "
      "will größer lesen und nicht länger warten.")

NOTE_MOTION = (
    "Aus heißt wirklich aus - der Compositor und die fremden "
    "GTK4-Fenster gehen mit. Bewegte Flächen lösen bei einer "
    "vestibulären Störung Schwindel aus; das ist der Grund "
    "für diesen Schalter und kein Geschmack.")

NOTE_SIZES_REST_TITLE = "Die übrigen Größen"

NOTE_SIZES_REST = (
    f"Einstellbar sind {len(sizes.TABLE)}. Die anderen "
    f"{len(sizes.TABLE) - len(DIALS)} sind Sprossen der "
    "vier Leitern - Schrift, Symbol, Rundung, Abstand -, die "
    "der Regler oben IM VERHAELTNIS bewegt, und Innenmasse "
    "von Fenstern, die nach dem Platzhalter heissen, den sie "
    "setzen. Einzeln angeboten wären sie wieder der Katalog, "
    "den die Leitern abgelöst haben. "
    "`zepos-settings get sizes` zeigt, was gesetzt ist, "
    "`user_settings.py list-sizes` alle mit ihrem aktuellen Wert.")

NOTE_WEATHER_GROUP = (
    "Ein Ortsname, eine Postleitzahl oder ein Flughafencode. "
    "Leer heißt: das Modul bleibt leer und fragt niemanden - "
    "und nur dann erfährt wttr.in nicht, wo diese Maschine "
    "steht. Der Ort geht bei jeder Auffrischung dorthin.")

NOTE_UPDATE_ENABLED = (
    "Aus heißt: systemd hält den Zeitgeber gar nicht erst.")

NOTE_UPDATE_SCOPE = (
    "Nur ZepOS lässt die Arch-Basis in Ruhe. Ein "
    "unbeaufsichtigtes Vollupgrade auf einem Rolling Release ist "
    "ein Rechner, der eines Morgens nicht mehr startet.")

NOTE_UPDATE_NOTIFY = (
    "Ein Fehlschlag meldet sich immer, ausser bei \"Nie\" - eine "
    "abgelehnte Unterschrift darf nicht wie \"schon eine Weile "
    "nichts Neues\" aussehen.")

NOTE_UPDATE_REST_TITLE = "Die übrigen Einstellungen"

NOTE_UPDATE_REST = (
    "Verzögerung nach dem Start, zufällige Streuung, Nachholen und "
    "die Meldung über die Arch-Basis stehen in `zepos-update --help`.")


def theme_note(writable: bool) -> str:
    """Die Beschreibung der Themenseite - mit dem Satz, der misst."""
    return (
        "Die Palette, unter der die eigenen Farben liegen: was "
        "auf der Seite \"Farben\" eingestellt ist, überlebt "
        "jeden Wechsel.\n\n"
        "Das Thema gehört der MASCHINE und nicht diesem Konto - "
        "der Anmeldebildschirm steht vor jedem Konto und soll "
        "dasselbe zeigen. "
        + ("Dieses Konto darf es schreiben." if writable else
           "Deshalb wird beim Wechseln nach Rechten gefragt."))


def update_note(writable: bool) -> str:
    """Dieselbe Form fuer die Aktualisierung."""
    return (
        "Diese Einstellungen gehören der MASCHINE und nicht "
        "diesem Konto: der Dienst läuft, bevor sich jemand "
        "angemeldet hat. Sie werden sofort geschrieben - "
        + ("dieses Konto darf das." if writable else
           "und dafür wird nach Rechten gefragt."))


# Die Seiten dieses Fensters, in der Reihenfolge, in der sie im
# Umschalter stehen: Kennung, Beschriftung, Symbol.
#
# WARUM EINE TABELLE UND NICHT SECHS AUFRUFE
#     Bis zum 12.08.2026 waren die sechs `add_titled_with_icon`-Aufrufe
#     in _build() die einzige Aufzaehlung der Seiten. Das genuegte,
#     solange niemand von aussen nach ihnen fragte.
#
#     GEMELDET am 12.08.2026: "ich finde den display manager wie nwg
#     display nicht in der app suche". Die Bildschirmseite ist seit dem
#     Wegfall von nwg-displays kein eigenes Programm mehr, sondern eine
#     SEITE - und zepos-menu kennt nur .desktop-Eintraege und Tasten.
#     Der Auffindbarkeits-Agent hatte genau das angekuendigt: "sobald
#     die Einstellungsanwendung eine .desktop-Datei ausliefert, steht
#     sie durch die Anwendungsquelle im selben Fenster". Eingetreten ist
#     es zur Haelfte - die ANWENDUNG steht dort, ihre Seiten nicht.
#
#     Eine Anwendung mit sieben Seiten verdient sieben Eintraege, und
#     die Freedesktop-Spezifikation hat dafuer eine Form: Desktop
#     Actions. GNOME liefert seine Systemeinstellungen genauso aus.
#     Damit die .desktop-Datei und dieses Fenster nicht
#     auseinanderlaufen koennen, steht die Liste hier EINMAL, und
#     tests/settings/test_settings_model.py haelt die Datei dagegen.
PAGES: tuple[tuple[str, str, str], ...] = (
    ("groesse", "Größe", "preferences-desktop-font-symbolic"),
    # Die Bildschirme direkt hinter der Groesse, weil beide dieselbe
    # Frage beantworten - "wie gross ist das hier eigentlich" -, und
    # VOR dem Thema, weil eine Anordnung der Grund ist, aus dem jemand
    # dieses Fenster ueberhaupt aufmacht, wenn er gerade ein Kabel
    # eingesteckt hat.
    ("bildschirme", "Bildschirme", "video-display-symbolic"),
    # Die Leiste hinter den Bildschirmen: beide beschreiben, WO etwas
    # steht, und die Leiste steht auf den Bildschirmen. Vor dem Thema
    # aus demselben Grund wie die Groesse - was da ist, entscheidet man
    # vor der Farbe, die es hat.
    ("leiste", "Leiste", "view-list-ordered-symbolic"),
    # Vor den Farben, weil es UNTER ihnen liegt: das Thema setzt die
    # Palette, die eigenen Farben liegen darueber. Wer beides aendern
    # will, waehlt erst das Thema.
    ("thema", "Thema", "preferences-desktop-theme-symbolic"),
    ("farben", "Farben", "applications-graphics-symbolic"),
    ("wetter", "Wetter", "weather-few-clouds-symbolic"),
    ("aktualisierung", "Aktualisierung", "software-update-available-symbolic"),
    # Sprache und Zeitzone ZULETZT, und das ist eine Entscheidung mit
    # zwei Haelften.
    #
    # WARUM NICHT ZUERST
    #     Der naheliegende Platz waere ganz vorn: wer die Oberflaeche
    #     nicht lesen kann, braucht genau diese Seite. Nur zeigt das
    #     Fenster beim Oeffnen die ERSTE Seite - sie nach vorn zu
    #     ziehen hiesse, jedem, der die Groesse verstellen will, ab
    #     sofort eine andere Seite vorzulegen. Eine Einstellung, die man
    #     EINMAL trifft, verdraengt nicht die, die man staendig trifft.
    #
    # WARUM TROTZDEM AUFFINDBAR
    #     Ueber die Desktop Action derselben Seite (siehe unten): wer
    #     "sprache", "language", "zeitzone" oder "uhr" in den Starter
    #     tippt, bekommt sie unmittelbar, ohne das Fenster zu oeffnen
    #     und ohne einen Reiter lesen zu muessen.
    ("sprache", "Sprache und Zeit", "preferences-desktop-locale-symbolic"),
)

PAGE_NAMES = tuple(name for name, _, _ in PAGES)

# Der Schalter, mit dem eine Aktion aus der .desktop-Datei ihre Seite
# nennt. Er steht hier, weil main.py ihn liest und die Vorlage der
# Datei ihn schreibt.
PAGE_OPTION = "--page"


# Die Fenstergroesse beim ersten Oeffnen, in Full-HD-Pixeln vor dem
# Massstab. Sie wird MIT ihm multipliziert, weil der Inhalt es auch wird:
# ein Fenster fester Groesse mit doppelt so grosser Schrift zeigt die
# Haelfte.
#
# 720x820: breit genug fuer die laengste Zeile dieser Anwendung (die
# Farbzeile aus Beschriftung, Schluessel, Knopf und Pfeil), hoch genug
# fuer eine ganze Farbgruppe ohne Bildlauf.
WINDOW_WIDTH = 720
WINDOW_HEIGHT = 820

# Der eine Abstand, den diese Anwendung selbst setzt: zwischen dem
# Farbknopf einer Zeile und ihrem Zuruecksetzen-Pfeil.
#
# WARUM UEBERHAUPT EINER, WO libadwaita DOCH ALLES SELBST SETZT
#     Weil libadwaita hier zwei Knoepfe unmittelbar aneinanderlegt und
#     sie damit wie einen aussehen laesst - und der eine faerbt, der
#     andere verwirft. Das ist die einzige Stelle in diesem Fenster, an
#     der ein Abstand eine Aussage ist.
#
# WARUM DIE SPROSSE UND NICHT EINE ZAHL
#     src/sizes.py SPACE_LADDER, dieselbe Leiter, auf der die
#     Ueberlagerungen und der Assistent stehen. Sprosse 4 ist die
#     kleinste, die kein Haarabstand ist - die 2 daneben ist der
#     Zwischenraum zweier Kacheln.
SPACE_RUNG = sizes.SPACE_LADDER[1]


def space(section: dict) -> int:
    """Die Sprosse in Pixeln, so wie sie auch im Stylesheet steht.

    Durch sizes.value_of(), also MIT dem Faktor des Nutzers
    multipliziert. Bliebe sie stehen, klebten die zwei Knoepfe einer
    Farbzeile bei doppelter Schrift wieder aneinander - der Abstand
    waere dann zwar auf der Leiter und trotzdem falsch.
    """
    return int(size_number(
        sizes.value_of(f"{sizes.SPACE_PREFIX}{SPACE_RUNG}", section)))


def window_size(section: dict) -> tuple[int, int]:
    """Wie gross das Fenster aufgeht, beim Massstab dieses Nutzers.

    Mindestens die Grundgroesse: bei einem Faktor unter 1 - den es
    ueber diese Oberflaeche nicht gibt, den eine von Hand editierte
    Datei aber tragen kann - waere ein kleineres Fenster nicht kleiner
    beschriftet, sondern nur enger.
    """
    scale = sizes.scale_of(section)
    return (max(WINDOW_WIDTH, int(WINDOW_WIDTH * scale)),
            max(WINDOW_HEIGHT, int(WINDOW_HEIGHT * scale)))


# --------------------------------------------------------------------
# Die Farben
# --------------------------------------------------------------------

def colour_default(key: str) -> str:
    """Was diese Farbe waere, wenn niemand sie je angefasst haette."""
    return brand.COLORS[key]


def rgb_of(colour: str) -> tuple[float, float, float]:
    """#rrggbb als drei Anteile zwischen 0 und 1, wie GTK sie will."""
    value = colour.lstrip("#")
    return tuple(int(value[index:index + 2], 16) / 255.0
                 for index in (0, 2, 4))


def hex_of(red: float, green: float, blue: float) -> str:
    """Und zurueck.

    Kaufmaennisch gerundet und nicht abgeschnitten: int(0.999*255) ist
    254, und eine Farbe, die beim blossen Hin- und Herwandeln um einen
    Wert wandert, macht aus jedem Oeffnen des Fensters eine Aenderung.
    """
    return "#" + "".join(
        f"{min(255, max(0, int(channel * 255 + 0.5))):02x}"
        for channel in (red, green, blue))


# --------------------------------------------------------------------
# Die Leiste und das Dock
# --------------------------------------------------------------------
#
# Diese Seite entscheidet NICHTS selbst. Was eine Haelfte ist, was
# "wie ausgeliefert" heisst und was mit einem Namen passiert, den es
# nicht gibt, steht in src/settings.py neben dem Abschnitt, den es
# beschreibt - der Erzeuger liest dieselben Funktionen, und zwei
# Antworten auf "was steht auf dieser Leiste" waeren zwei Leisten.
#
# WAS DIESE SEITE DAZUTUT: die Beschriftungen, unter denen ein Mensch
# die drei Haelften sucht, und die Reihenfolge, in der sie im Fenster
# stehen. Links, rechts, Dock - von oben nach unten so, wie sie auf dem
# Schirm von links nach rechts und dann darunter stehen.
BAR_SIDES: tuple[tuple[str, str, str], ...] = (
    (settings_file.BAR_LEFT, "Links in der Leiste",
     "Das linke Ende der oberen Leiste, von außen nach innen gelesen: "
     "der oberste Eintrag steht am weitesten links."),
    (settings_file.BAR_RIGHT, "Rechts in der Leiste",
     "Das rechte Ende, von innen nach außen: der oberste Eintrag steht "
     "der Fenstertitelmitte am nächsten, der unterste ganz außen."),
    (settings_file.BAR_PINS, "Im Dock angeheftet",
     "Die Anwendungen im Fuss, von links nach rechts. Ein offenes "
     "Fenster erscheint dort ohnehin; hier steht, was auch ohne "
     "geöffnetes Fenster dableibt."),
)


# Warum das Dock einen Namen NICHT anheftet. Zwei Gruende, und beide
# stehen woertlich in resolvePins() in src/templates/ags-dock.template -
# das ist die Stelle, die es wirklich entscheidet, und diese hier ist ihr
# Spiegel im Fenster.
#
# WARUM DIESE ZWEI SAETZE UEBERHAUPT IN EINER OBERFLAECHE STEHEN
#     GEMESSEN am 12.08.2026: xdg-desktop-portal-gnome steht in der
#     ausgelieferten Auswahl und traegt NoDisplay=true. Das Dock laesst
#     es deshalb weg - richtig so, es ist ein D-Bus-Dienst ohne
#     Fenster -, und genau dieser Eintrag war das Zahnrad, das sich
#     "garnicht oeffnen" liess. Eine Einstellungsseite, die ihn als
#     anheftbar anbietet, waere derselbe Fehler noch einmal: ein
#     Bedienelement, hinter dem nichts passiert.
#
#     Also wird er angezeigt und BENANNT, aber nicht zur Wahl gestellt.
#     Angezeigt, weil er in der ausgelieferten Liste steht und der
#     Nutzer sonst ein Symbol weniger sieht, als hier Zeilen stehen -
#     ohne einen Anhaltspunkt, warum.
DOCK_NO_ENTRY = ("kein Anwendungseintrag auf dieser Maschine - "
                 "nicht installiert")
DOCK_SERVICE = "ein Dienst ohne Fenster (NoDisplay) - kein Knopf im Dock"


def dock_reason(found: bool, nodisplay: bool) -> str:
    """Warum das Dock diesen Eintrag auslaesst - leer, wenn es ihn zeigt.

    Die zwei Bedingungen sind resolvePins() in ags-dock.template, in
    derselben Reihenfolge: erst gibt es ueberhaupt einen
    Anwendungseintrag, dann sagt der Eintrag selbst, ob er eine
    Anwendung ist.

    Die ANTWORTEN kommen von aussen, weil sie GIO brauchen und in
    dieser Datei kein `gi` stehen darf - siehe den Kopf. Was hier steht,
    ist die Entscheidung, und die ist damit ohne Anzeige zu messen.
    """
    if not found:
        return DOCK_NO_ENTRY
    if nodisplay:
        return DOCK_SERVICE
    return ""


def bar_stored(order: list[str],
               shipped: list[str] | None) -> list[str] | None:
    """Was fuer diese Reihenfolge in die Datei geschrieben wird.

    Die Liste - ausser sie ist Zeichen fuer Zeichen die ausgelieferte.
    Dann null.

    WARUM DAS KEIN UEBERGRIFF IST, SONDERN DIE EINZIGE RICHTIGE ANTWORT
        Wer ein Modul herunternimmt und es wieder aufstellt, steht
        genau da, wo er angefangen hat. Schriebe das Fenster ihm dann
        die Liste in die Datei, haette ein Ausprobieren ohne Ergebnis
        die Auslieferung eingefroren: das naechste Modul, das ZepOS
        hinzufuegt, erschiene bei ihm nie, und er koennte nicht einmal
        sagen, wann er das bestellt hat.

        Der umgekehrte Fall - jemand WILL genau die heutige Reihenfolge
        festhalten - ist damit nicht mehr moeglich, und das ist
        Absicht: "so wie es ausgeliefert wird" ist die Aussage, die er
        trifft, und sie bleibt richtig, wenn ZepOS sich aendert.

    Bei unbekannter Auslieferung (kein Abdruck) wird nichts verglichen
    und nichts eingefroren - dann steht die Liste da, die der Nutzer
    sieht.
    """
    if shipped is not None and order == shipped:
        return None
    return order


# Welche Listen im Abdruck stehen: die drei Haelften plus das Moegliche.
# Nicht BAR_KEYS allein - das sind die Schluessel der EINSTELLUNGSDATEI,
# und "was moeglich ist" stellt niemand ein.
_IMPRINT_LISTS = (*settings_file.BAR_KEYS, settings_file.BAR_AVAILABLE)


def placeable_in(shipped: dict[str, list[str] | None], key: str):
    """Welche Namen fuer diese Haelfte ueberhaupt in Frage kommen.

    Fuer die beiden Leistenhaelften das Moegliche, fuer die
    Anheftungen des Docks die ausgelieferten - dort gibt es nichts, was
    ZepOS kennt und nicht ausliefert, und ein frei getippter Paketname
    waere ein Knopf, hinter dem nichts passiert.

    Hier und nicht in bar.py, aus demselben Grund wie alles andere in
    dieser Datei: das Einstellungsfenster und der Erzeuger muessen
    dieselbe Antwort geben, und eine Antwort, die in einer Datei mit
    Widgets steht, laesst sich ohne Anzeige nicht messen.
    """
    if key == settings_file.BAR_PINS:
        return shipped[key]
    return shipped[settings_file.BAR_AVAILABLE]


def acceptable_in(shipped: dict[str, list[str] | None], key: str):
    """Welche Namen ANGENOMMEN werden - nicht dasselbe wie angeboten.

    Fuer die zwei Leistenhaelften ist es dasselbe: was aufstellbar ist,
    wird angeboten, und was angeboten wird, ist aufstellbar.

    FUER DAS DOCK SIND ES SEIT DEM 20.08.2026 ZWEI FRAGEN
        Angeboten wird, was ZepOS ausliefert - die Liste "Wieder
        hinzufuegen" auf der Seite "Leiste" soll die abgenommenen
        Vorgaben zurueckholen und nicht die zweihundert Anwendungen
        dieser Maschine aufzaehlen.

        ANGENOMMEN wird mehr, naemlich alles, wofuer es hier einen
        Anwendungseintrag gibt (settings.pinnable()). Ohne diese
        Erweiterung waere "anheften, was die Vorgabe nicht kennt" nicht
        abgelehnt, sondern unmoeglich - und genau das ist der Wunsch,
        wegen dem es das Rechtsklick-Menue geben soll.

        Die Richtung stimmt: angenommen wird MEHR als angeboten, nie
        weniger. Andersherum waere es der Fehler, den der Kopf von
        _plan_bar() beschreibt - eine Oberflaeche, die etwas anbietet,
        das die Pruefung danach wegwirft.
    """
    if key == settings_file.BAR_PINS:
        return settings_file.pinnable(shipped[key])
    return placeable_in(shipped, key)


def rejection_in(key: str) -> str:
    """Wie eine Ablehnung in dieser Haelfte heisst.

    Auf der Leiste ist ein nicht aufstellbarer Name ein FEHLER in der
    Einstellung; im Dock ist er meistens ein Programm, das jemand
    deinstalliert hat. Ein Wortlaut fuer beides schickte den Nutzer bei
    der zweiten Lage in die falsche Datei.
    """
    if key == settings_file.BAR_PINS:
        return settings_file.BAR_GONE
    return settings_file.BAR_UNKNOWN


def shipped_bar() -> tuple[dict[str, list[str] | None], dict[str, str], str]:
    """Die ausgelieferte Leiste, ihre Beschriftungen, und was zu sagen ist.

    EINMAL gelesen und nicht je Haelfte: der Abdruck ist eine Datei, und
    drei Aufrufe waeren drei Gelegenheiten, sie in verschiedenen
    Zustaenden anzutreffen - und drei verschiedene Saetze darueber, was
    mit ihr los ist.

    Der dritte Rueckgabewert ist der Satz. Es gibt naemlich DREI Lagen
    und nicht zwei: der Abdruck ist da, er fehlt, oder er ist kaputt.
    Die letzten beiden sehen im Fenster gleich aus - keine Namen - und
    sind es nicht, und eine leere Liste ohne Satz daneben waere die
    Oberflaeche, die behauptet, diese Leiste habe keine Module.

    IM ERSTEN RUECKGABEWERT STEHT EINE VIERTE LISTE, und sie ist keine
    Haelfte: BAR_AVAILABLE, das Moegliche. Sie steht hier mit den drei
    anderen, weil sie aus derselben Datei kommt und beim selben Griff
    gelesen wird - zwei Zugriffe waeren zwei Gelegenheiten, den Abdruck
    in zwei Zustaenden anzutreffen, und genau das verhindert der Kopf
    dieser Funktion.
    """
    unknown = {key: None for key in _IMPRINT_LISTS}
    # EIN Wortlaut fuer "der Abdruck ist da und taugt nicht", obwohl es
    # zwei Wege dorthin gibt (unlesbare Datei, unlesbarer Inhalt): zwei
    # Formulierungen fuer eine Lage lesen sich wie zwei Lagen.
    broken = "Die hinterlegte Reihenfolge ist nicht zu lesen: "

    try:
        imprint = settings_file.shipped_bar()
    except settings_file.UnusableSettings as problem:
        return unknown, {}, broken + str(problem)

    if imprint is None:
        return (unknown, {},
                f"Auf dieser Maschine ist nicht hinterlegt, was ZepOS "
                f"ausliefert "
                f"({paths.system_root() / settings_file.SHIPPED_BAR} "
                f"fehlt). Was hier steht, ist deshalb das, was in den "
                f"Einstellungen steht - hinzufügen lässt sich nichts. "
                f"Die Datei bringt das Paket zepos-config mit; ein "
                f"Checkout ohne installiertes Paket hat sie nicht.")

    try:
        lists = {key: settings_file.bar_names(imprint, key)
                 for key in _IMPRINT_LISTS}
        labels = settings_file.bar_labels(imprint, settings_file.BAR_PINS)
    except settings_file.UnusableSettings as problem:
        return unknown, {}, broken + str(problem)

    return lists, labels, ""


# --------------------------------------------------------------------
# Der Entwurf: was verstellt wurde, bevor gespeichert wird
# --------------------------------------------------------------------

@dataclass
class Draft:
    """Der geladene Stand plus das, was der Nutzer daran gedreht hat.

    WARUM UEBERHAUPT EIN ENTWURF UND NICHT SCHREIBEN BEI JEDER BEWEGUNG
        Weil ein Regler waehrend des Ziehens Dutzende Werte durchlaeuft.
        Jeder davon waere ein atomares Schreiben der ganzen
        Einstellungsdatei, und - schlimmer - jeder waere eine Marke fuer
        die naechste Anmeldung. Ein Nutzer, der einen Regler anfasst und
        wieder loslaesst, ohne sich zu entscheiden, haette danach eine
        Neuerzeugung bestellt.

        Ausserdem ist "Speichern" die Stelle, an der die Anwendung sagen
        kann, was jetzt noch passieren muss. Ohne sie gaebe es diese
        Stelle nicht.
    """

    document: dict[str, Any]
    colours: dict[str, str] = field(default_factory=dict)
    values: dict[str, str | None] = field(default_factory=dict)
    scale: float | None = None
    motion: bool | None = None
    weather: str | None = None
    # Je Haelfte der Leiste entweder eine Liste oder None, und None ist
    # hier eine ANGABE und keine Abwesenheit: "wieder wie ausgeliefert".
    # Ob eine Haelfte ueberhaupt angefasst wurde, sagt allein, ob ihr
    # Schluessel in diesem Verzeichnis steht - genau die Unterscheidung,
    # die `values` fuer die Groessen trifft und aus demselben Grund:
    # ohne sie waere Zuruecksetzen nicht von "nichts geaendert" zu
    # unterscheiden.
    bar: dict[str, list[str] | None] = field(default_factory=dict)

    # ---- lesen ----------------------------------------------------

    @property
    def _sizes(self) -> dict[str, Any]:
        return sizes.settings_section(self.document)

    def current_scale(self) -> float:
        if self.scale is not None:
            return self.scale
        return sizes.scale_of(self._sizes)

    def current_size(self, name: str) -> float:
        """Was fuer diese Groesse gerade gilt, als Zahl.

        Der Entwurf zuerst, dann die Datei. Und die Datei antwortet
        durch sizes.value_of(), also einschliesslich des Faktors: steht
        keine Ausnahme in der Datei, zeigt der Drehknopf das Ergebnis
        des Reglers und nicht den Grundwert. Alles andere waere eine
        Zahl, die auf dem Schirm nirgends vorkommt.
        """
        drafted = self.values.get(name, ...)
        if drafted is not ... and drafted is not None:
            return size_number(drafted)
        section = dict(self._sizes)
        if self.scale is not None:
            section["scale"] = self.scale
        if drafted is None:
            # Ausdruecklich zurueckgegeben: dann gilt wieder der Faktor.
            values = dict(section.get("values") or {})
            values.pop(name, None)
            section["values"] = values
        return size_number(sizes.value_of(name, section))

    def follows_scale(self, name: str) -> bool:
        """Ob diese Groesse gerade dem Regler folgt oder von Hand steht."""
        drafted = self.values.get(name, ...)
        if drafted is not ...:
            return drafted is None
        return sizes.override_of(self._sizes, name) is None

    def current_motion(self) -> bool:
        """Ob sich dieser Schreibtisch bewegen darf."""
        if self.motion is not None:
            return self.motion
        return sizes.motion_enabled(self._sizes)

    def current_colour(self, key: str) -> str:
        if key in self.colours:
            return self.colours[key]
        stored = self.document.get("colors")
        if isinstance(stored, dict) and isinstance(stored.get(key), str):
            return stored[key]
        return colour_default(key)

    def current_bar(self, key: str) -> list[str] | None:
        """Was fuer diese Haelfte gilt - None heisst "wie ausgeliefert".

        Der Entwurf zuerst, dann die Datei. `key in self.bar` und nicht
        `self.bar.get(key)`: ein gerade zurueckgesetzter Eintrag steht
        als None darin, und ein `or` wuerde ihn nicht vom nicht
        angefassten unterscheiden - dann faende ein Zuruecksetzen den
        alten Stand aus der Datei wieder.

        Die leere Liste ist ebenfalls eine Angabe ("hier steht nichts")
        und faellt deshalb nicht mit None zusammen. Sie faellt in jeder
        Wahrheitspruefung mit ihm zusammen, und das ist der Grund, aus
        dem hier ueberall `is None` steht.

        DIE ANHEFTUNGEN BEKOMMEN NOCH ETWAS DAZU - seit dem 20.08.2026
            Was aus der DATEI kommt, wurde gegen die Auslieferung von
            damals gesetzt (settings.BAR_BASELINE). Was ZepOS seither
            dazuliefert, hat der Nutzer nie abgewaehlt und gehoert
            angehaengt, sonst zeigte dieses Fenster eine Liste, die der
            Erzeuger anders aufloest - und der Erzeuger hat recht, denn
            apps.pinned() rechnet genauso.

            Nur fuer den Weg aus der Datei, ausdruecklich nicht fuer den
            aus dem Entwurf: was im Entwurf steht, hat der Nutzer GERADE
            zusammengestellt, und zwar aus der bereits ergaenzten Liste.
            Ein zweites Mal ergaenzt hiesse, dass ein frisch
            abgenommenes neues Symbol sofort wieder erschiene - ein
            Knopf, der nachweislich nichts bewirkt.
        """
        if key in self.bar:
            return self.bar[key]
        chosen = settings_file.bar_choice(self.document, key)
        if key != settings_file.BAR_PINS or chosen is None:
            return chosen
        return settings_file.dock_effective(
            chosen, settings_file.bar_baseline(self.document),
            settings_file.shipped_pins())

    def current_weather(self) -> str:
        if self.weather is not None:
            return self.weather
        stored = self.document.get("weather")
        if isinstance(stored, dict) and isinstance(stored.get("location"), str):
            return stored["location"]
        return ""

    # ---- schreiben ------------------------------------------------

    def dirty(self) -> bool:
        return bool(self.colours or self.values or self.bar) \
            or self.scale is not None or self.motion is not None \
            or self.weather is not None

    def sections(self) -> dict[str, Any]:
        """Die VOLLSTAENDIGEN Abschnitte, die geschrieben werden.

        settings.merge() ERSETZT einen Abschnitt, statt ihn tief zu
        verschmelzen - das ist Absicht und in settings.py begruendet:
        "Farben zuruecksetzen" schickt einen leeren Abschnitt und meint
        es. Also muss hier jeder Abschnitt vollstaendig aufgebaut
        werden, aus dem geladenen Stand plus den Aenderungen. Nur die
        Aenderungen zu schicken hiesse, jede Farbe zu loeschen, die
        dieses Fenster nicht angefasst hat.
        """
        out: dict[str, Any] = {}

        if self.colours:
            stored = self.document.get("colors")
            colours = dict(stored) if isinstance(stored, dict) else {}
            colours.update(self.colours)
            out["colors"] = colours

        if self.scale is not None or self.motion is not None or self.values:
            section = dict(self._sizes)
            if self.scale is not None:
                section["scale"] = float(self.scale)
            if self.motion is not None:
                section[sizes.MOTION_ENABLED] = bool(self.motion)
            values = dict(section.get("values") or {})
            for name, value in self.values.items():
                if value is None:
                    values.pop(name, None)
                else:
                    values[name] = value
            section["values"] = values
            out[sizes.SECTION] = section

        if self.weather is not None:
            stored = self.document.get("weather")
            weather = dict(stored) if isinstance(stored, dict) else {}
            weather["location"] = self.weather.strip()
            out["weather"] = weather

        if self.bar:
            # ALLE drei Haelften, auch die unveraenderten: merge()
            # ersetzt den Abschnitt, also waere ein Abschnitt mit nur
            # einer Haelfte darin das Loeschen der anderen zwei.
            #
            # Und die zurueckgesetzte geht als null hinein, nicht als
            # ihre gerade sichtbare Liste. Das ist der ganze Punkt des
            # Zuruecksetzens: eine hier eingefrorene Liste saehe heute
            # richtig aus und zeigte nach dem naechsten neuen Modul auf
            # eine Leiste, die es nicht mehr gibt.
            stored = self.document.get(settings_file.BAR)
            section = dict(stored) if isinstance(stored, dict) else {}
            for key in settings_file.BAR_KEYS:
                if key in self.bar:
                    section[key] = self.bar[key]
                else:
                    section.setdefault(key, None)

            # UND DIE VORGABE, GEGEN DIE DIE ANHEFTUNGEN GESETZT WURDEN
            #
            # HIER, WEIL ES DIE EINZIGE STELLE IST, DIE BEIDES SCHREIBT
            #     settings.BAR_BASELINE traegt die Auslieferung, wie sie
            #     im Augenblick dieser Entscheidung aussah; ohne sie
            #     kann der Erzeuger spaeter nicht unterscheiden, ob ein
            #     Name fehlt, weil der Nutzer ihn abgenommen hat, oder
            #     weil es ihn damals noch nicht gab. Die ganze
            #     Begruendung steht in src/settings.py bei BAR_BASELINE.
            #
            #     Ein Schreiber, der die Liste ohne ihre Vorgabe ablegt,
            #     hinterliesse eine Datei, die nur zur Haelfte aussagt,
            #     was gemeint war. Also gehen sie zusammen hinaus, in
            #     demselben Abschnitt, in demselben settings.merge().
            #
            # UND SIE IST DIE GANZE WANDERUNG
            #     Eine Datei von vor dem 20.08.2026 hat den Schluessel
            #     nicht und laeuft ohne ihn weiter (dock_effective()
            #     haengt bei unbekannter Vorgabe nichts an). Beim ersten
            #     Speichern der Anheftungen entsteht er - dieselbe
            #     Regel, nach der user_settings.migrate_scaling()
            #     arbeitet: beim Lesen wird nichts geschrieben, die
            #     Wanderung erreicht die Platte beim naechsten Speichern.
            #
            #     null beim Zuruecksetzen, und zwar aus demselben Grund
            #     wie oben: "wie ausgeliefert" braucht keine Vorgabe von
            #     damals, und eine stehengebliebene waere die
            #     eingefrorene Liste durch die Hintertuer.
            if settings_file.BAR_PINS in self.bar:
                section[settings_file.BAR_BASELINE] = (
                    None if self.bar[settings_file.BAR_PINS] is None
                    else settings_file.shipped_pins())

            out[settings_file.BAR] = section

        return out

    def set_dial(self, dial: Dial, value: float) -> None:
        """Eine benannte Groesse setzen, samt allem, was mitgehen muss."""
        self.values[dial.name] = size_text(dial.name, value)
        for name, ratio in dial.also:
            self.values[name] = size_text(name, round(value * ratio))

    def clear_dial(self, dial: Dial) -> None:
        """Sie wieder dem Regler ueberlassen.

        Ohne diesen Weg waere jede Ausnahme eine Einbahnstrasse - der
        Rueckweg fuehrte durch das Editieren der JSON-Datei, also genau
        durch das, wofuer es diese Anwendung gibt. Einen Namen auf
        seinen Grundwert zu SETZEN ist nicht dasselbe: er stuende dann
        fest und folgte dem Regler nicht mehr.
        """
        self.values[dial.name] = None
        for name, _ratio in dial.also:
            self.values[name] = None

    def set_bar(self, key: str, names: list[str]) -> None:
        """Diese Haelfte steht ab jetzt so da.

        Eine Kopie und nicht die Liste des Aufrufers: die Seite baut
        ihre Zeilen aus derselben Liste wieder auf, und ein Entwurf, der
        auf das Arbeitsstueck der Oberflaeche zeigt, aenderte sich beim
        naechsten Anfassen mit.
        """
        if key not in settings_file.BAR_KEYS:
            raise KeyError(key)
        self.bar[key] = list(names)

    def reset_bar(self, key: str) -> None:
        """Diese Haelfte wieder der Auslieferung ueberlassen.

        Schreibt None und nicht die gerade sichtbare Liste - siehe
        sections(). Ohne diesen Weg waere jede Umsortierung eine
        Einbahnstrasse, und der Rueckweg fuehrte durch das Editieren der
        JSON-Datei, also genau durch das, wofuer es diese Anwendung
        gibt.
        """
        if key not in settings_file.BAR_KEYS:
            raise KeyError(key)
        self.bar[key] = None


def load(path: Path | None = None) -> Draft:
    """Der Stand auf der Platte, als Entwurf ohne Aenderungen.

    settings.load() und nicht user_settings.load_settings(): das zweite
    verschmilzt mit den Vorgaben, und dann waere in der Datei nicht mehr
    zu erkennen, was der Nutzer selbst gesagt hat und was die
    Auslieferung. Genau das braucht diese Oberflaeche aber, um
    "zuruecksetzen" von "auf den Vorgabewert gestellt" unterscheiden zu
    koennen.

    Eine Datei, die es gibt und die nicht gelesen werden kann, wirft -
    settings.UnusableSettings. Sie wird hier NICHT abgefangen: die
    Anwendung wuerde sonst die Vorgaben zeigen und beim Speichern ueber
    das schreiben, was der Nutzer verloren zu haben glaubt.
    """
    return Draft(document=settings_file.load(path))


def save(draft: Draft, path: Path | None = None) -> None:
    """Die Abschnitte schreiben - durch settings.merge() und sonst nichts.

    Derselbe Weg, den `zepos-settings`, der Stil-Editor und die
    VPN-Maske nehmen: dieselbe Datei, dasselbe atomare Schreiben mit
    0600, dieselbe Schemaversion. Zwei Wege zu einer Einstellung, die
    verschiedene Dateien anfassen, sind zwei Einstellungen.
    """
    sections = draft.sections()
    if not sections:
        return
    settings_file.merge(sections, path)


# --------------------------------------------------------------------
# Was danach noch passieren muss
# --------------------------------------------------------------------

# Der Befehl, der die Konfiguration neu erzeugt. Nicht
# generate_config.sh unmittelbar: zepos-generate ist der Befehl, den das
# Paket nach /usr/bin legt, und er findet seine Module selbst - siehe
# den Kopf von src/cli.py.
GENERATE_COMMAND = ("zepos-generate", "--all")

# Was ein Neuerzeugen kostet, im Wortlaut, damit die Oberflaeche es nicht
# umschreibt. GEMESSEN in src/generate_config.sh: `ags quit`, bis zu
# zwei Sekunden warten, `pkill -9 -f "gjs.*ags"`, neu starten.
GENERATE_COST = (
    "Die Leiste, das Dock und alle Ueberlagerungsfenster werden dabei "
    "beendet und neu gestartet - sie sind für wenige Sekunden weg. "
    "Bereits geöffnete Terminals behalten ihre alte Schriftgröße, "
    "bis sie neu geöffnet werden."
)


def marker_path() -> Path:
    return paths.session_regenerate_marker()


def request_regeneration_at_login(path: Path | None = None) -> Path:
    """Die Marke ablegen, die die naechste Anmeldung liest.

    Eine leere Datei; ihr VORHANDENSEIN ist die Aussage, genau wie bei
    der Marke der Selbstaktualisierung. Steht nichts darin, kann auch
    nichts darin falsch sein.
    """
    target = path if path is not None else marker_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()
    return target


def forget_regeneration_request(path: Path | None = None) -> None:
    """Sie wieder wegraeumen, weil gerade erzeugt worden ist.

    missing_ok, weil dieser Weg auch dann genommen wird, wenn jemand
    "Jetzt anwenden" drueckt, ohne vorher etwas geaendert zu haben.
    """
    target = path if path is not None else marker_path()
    target.unlink(missing_ok=True)


def regenerate(*, runner: Runner | None = None,
               marker: Path | None = None) -> subprocess.CompletedProcess:
    """Jetzt erzeugen, und die Bitte fuer die naechste Anmeldung streichen.

    Die Marke faellt NACH dem Lauf und nur bei Erfolg. Ein
    fehlgeschlagener Generatorlauf hat nichts erzeugt; die Aenderung
    liegt dann weiter in der Einstellungsdatei und soll bei der
    naechsten Anmeldung noch einmal versucht werden.
    """
    runner = runner or subprocess.run
    completed = runner(list(GENERATE_COMMAND), capture_output=True, text=True)
    if completed.returncode == 0:
        forget_regeneration_request(marker)
    return completed


# --------------------------------------------------------------------
# Die Aktualisierung - die eine Einstellung, die diesem Konto nicht gehoert
# --------------------------------------------------------------------

# Was angeboten wird, in der Reihenfolge, in der man es entscheidet:
# erst ob ueberhaupt, dann was, dann wie laut, dann wie oft.
#
# update.known_keys() zaehlt neun Namen auf. Die vier hier sind die, zu
# denen ein Mensch eine Meinung hat; die uebrigen fuenf
# (schedule.on_boot, schedule.randomized_delay, schedule.persistent,
# report_base, schema_version) sind Feineinstellung eines Zeitgebers und
# stehen mit ihrer Begruendung in src/update.py. `zepos-update --help`
# zaehlt alle auf, und die Seite sagt das.
UPDATE_ENABLED = "enabled"
UPDATE_SCOPE = "scope"
UPDATE_NOTIFY = "notify"
UPDATE_INTERVAL = "schedule.interval"

UPDATE_LABELS = {
    UPDATE_ENABLED: "Automatisch aktualisieren",
    UPDATE_SCOPE: "Umfang",
    UPDATE_NOTIFY: "Melden",
    UPDATE_INTERVAL: "Wie oft",
}

UPDATE_SCOPE_LABELS = {
    update.SCOPE_ZEPOS: "Nur ZepOS",
    update.SCOPE_ALL: "Alles, auch die Arch-Basis",
}

UPDATE_NOTIFY_LABELS = {
    update.NOTIFY_CHANGES: "Wenn sich etwas geändert hat",
    update.NOTIFY_FAILURES: "Nur bei Fehlschlägen",
    update.NOTIFY_NEVER: "Nie",
}

# Die Kalenderworte von systemd, die als "wie oft" einen Sinn ergeben.
# update.CALENDAR_WORDS kennt mehr - "hourly" und "quarterly" darunter -,
# und eine Aktualisierung, die stuendlich nach Paketen fragt, ist keine
# Einstellung, sondern ein Fehler mit einem Namen.
UPDATE_INTERVAL_LABELS = {
    "daily": "Täglich",
    "weekly": "Wöchentlich",
    "monthly": "Monatlich",
}


# --------------------------------------------------------------------
# Das Thema - die zweite Einstellung, die der Maschine gehoert
# --------------------------------------------------------------------

def theme_names() -> list[str]:
    """Die Themen, in der Reihenfolge, in der sie vorgelegt werden.

    Das ausgelieferte zuerst, der Rest alphabetisch. Nicht alphabetisch
    insgesamt: die Vorgabe ist der Ort, an den man zurueckwill, und den
    sucht man oben.
    """
    return [theme.DEFAULT, *sorted(name for name in theme.THEMES
                                   if name != theme.DEFAULT)]


def current_theme() -> str:
    return theme.read_name()


def theme_label(name: str) -> str:
    return theme.LABELS[name]


def theme_description(name: str) -> str:
    return theme.DESCRIPTIONS[name]


def theme_writable() -> bool:
    """Ob dieses Konto /etc/zepos/theme schreiben darf.

    Gefragt und nicht angenommen, aus demselben Grund wie bei
    update_writable(): auf einer Installation lautet die Antwort "nein",
    in einem Test, der die Wurzel umlenkt, "ja". Am VERZEICHNIS, weil
    die Datei auf einer frischen Installation noch nicht existiert.
    """
    directory = theme.name_path().parent
    if directory.is_dir():
        return os.access(directory, os.W_OK | os.X_OK)
    parent = directory.parent
    return parent.is_dir() and os.access(parent, os.W_OK | os.X_OK)


def theme_elevated_command(name: str) -> list[str]:
    """Derselbe Weg mit Rechten: `zepos-settings set theme <name>`.

    Und nicht ein eigener Schreibweg als root - dieser Befehl prueft den
    Namen gegen theme.THEMES, bevor er schreibt, und sagt hinterher, was
    noch passieren muss. Ein zweiter Weg waere ein zweiter Satz Fehler.
    """
    return ["zepos-settings", "set", "theme", name]


def set_theme(name: str, *, runner: Runner | None = None) -> UpdateOutcome:
    """Das Thema der Maschine setzen, mit Rechten oder ohne.

    WARUM DIESELBE VORRICHTUNG WIE FUER DIE AKTUALISIERUNG
        Weil es dieselbe Frage ist: eine Datei unter /etc, die dieses
        Konto meistens nicht schreiben darf. Erst der unmittelbare Weg,
        dann pkexec - die Reihenfolge ist nicht Bequemlichkeit, sondern
        vermeidet ein Rechtefenster fuer etwas, das schon erlaubt ist.

    WARUM DAS THEMA UEBERHAUPT DER MASCHINE GEHOERT
        Der Anmeldebildschirm steht vor jedem Konto. Der Kopf von
        src/theme.py fuehrt die Messung; die siebzig einzelnen FARBEN
        bleiben diesem Konto und liegen ueber der Palette.
    """
    command = tuple(theme_elevated_command(name))
    if theme_writable():
        try:
            theme.write_name(name)
        except (theme.UnknownTheme, OSError) as problem:
            return UpdateOutcome(False, str(problem), command)
        return UpdateOutcome(True, "", command)

    lifting = elevator()
    if not lifting:
        return UpdateOutcome(
            False,
            "Das Thema gehört der Maschine und nicht diesem Konto, weil "
            "der Anmeldebildschirm dazugehört. Auf diesem System ist "
            "kein pkexec vorhanden, also geht es nur so:\n    sudo "
            + " ".join(command),
            command)

    runner = runner or subprocess.run
    completed = runner([*lifting, *command], capture_output=True, text=True)
    if completed.returncode == 0:
        return UpdateOutcome(True, "", command)
    return UpdateOutcome(
        False,
        (completed.stderr or "").strip()
        or f"{' '.join(command)} endete mit {completed.returncode}",
        command)


# Was ein Themenwechsel wann erreicht. Im Wortlaut, damit die
# Oberflaeche es nicht umschreibt - und weil die drei Zeitpunkte
# gemessen sind und nicht versprochen:
#
#   sofort        Die Anmeldemaske. Ihre Blaetter liegen alle schon
#                 unter /etc/greetd; src/bin/zepos-greeter liest den
#                 Namen bei jedem Start. Kein Erzeugungslauf noetig.
#   nach dem Lauf Der Schreibtisch. src/generate_config.sh schreibt die
#                 Stylesheets neu und startet AGS neu - GEMESSEN am
#                 12.08.2026 aendern sich dabei 16 von 85 erzeugten
#                 Dateien.
#   beim Neustart Hyprland liest seine Konfiguration nur beim Start oder
#                 auf `hyprctl reload` - Fensterrahmen, Glasregeln und
#                 Fensterleisten also erst dann. Und schon offene
#                 Terminals behalten ihre Farben, bis sie neu geoeffnet
#                 werden: kitty liest kitty.conf einmal.
THEME_TIMING = (
    "Der Anmeldebildschirm zeigt das neue Thema sofort - beim nächsten "
    "Mal, ohne dass etwas erzeugt werden muss. Der Schreibtisch braucht "
    "einen Erzeugungslauf. Fensterrahmen und schon offene Terminals "
    "folgen erst nach `hyprctl reload` beziehungsweise beim nächsten "
    "Oeffnen."
)


def update_settings() -> dict[str, Any]:
    """Was die MASCHINE ueber ihre Aktualisierung sagt.

    Aus /etc/zepos/update.json und nicht aus user-settings.json: der
    Dienst laeuft als root, moeglicherweise bevor sich jemand angemeldet
    hat, und auf einer Maschine mit zwei Konten gaebe es sonst zwei
    Antworten auf eine Frage, die ein Zeitgeber nur einmal beantworten
    kann. Der Kopf von src/update.py fuehrt das aus.
    """
    return update.load()


def update_writable() -> bool:
    """Ob dieses Konto die Maschinendatei ueberhaupt schreiben darf.

    Gefragt und nicht angenommen. /etc/zepos gehoert root, also lautet
    die Antwort auf einer Installation "nein" und in einem Test, der die
    Wurzel umlenkt, "ja" - und der Unterschied entscheidet, ob die
    Oberflaeche gleich schreibt oder erst nach einer Anmeldung fragt.

    Am Verzeichnis und nicht an der Datei: update.save() schreibt
    ueber eine temporaere Datei daneben und benennt sie um, braucht also
    das Verzeichnis. Und die Datei gibt es auf einer frischen
    Installation gar nicht.
    """
    directory = update.config_path().parent
    if directory.is_dir():
        return os.access(directory, os.W_OK | os.X_OK)
    parent = directory.parent
    return parent.is_dir() and os.access(parent, os.W_OK | os.X_OK)


def update_elevated_command(key: str, value: Any) -> list[str]:
    """Der Befehl, mit dem dieselbe Aenderung mit Rechten liefe.

    `zepos-settings set update.<key> <wert>` und nicht ein eigener
    Schreibweg als root: dieser Befehl kennt die Umleitung nach
    /etc/zepos bereits, prueft den Wert mit update.validate() und ruft
    danach update.apply(), das die Zeitgeber-Ergaenzung schreibt und
    systemd Bescheid sagt. Ein zweiter Weg waere ein zweiter Satz
    Fehler.

    In JSON-Schreibweise, weil update.set_value() den Wert so liest:
    ohne die waere `false` die Zeichenkette "false", und die faellt in
    update.validate() durch - richtig, aber verwirrend fuer jemanden,
    der nur einen Schalter umgelegt hat.
    """
    return ["zepos-settings", "set", f"update.{key}", json.dumps(value)]


def elevator() -> list[str]:
    """Womit ein Befehl auf dieser Maschine Rechte bekommt.

    pkexec und nicht sudo: der Schreibtisch startet einen Polkit-Agenten
    (hyprland-universal-config.template, exec-once), und der fragt in
    einem Fenster nach - sudo haette hier kein Terminal, in dem es
    fragen koennte. Dieselbe Wahl und dieselbe Begruendung wie in
    vpn-control-config.template.

    Eine leere Liste, wenn es ihn nicht gibt. Dann bleibt der Befehl
    trotzdem stehen, zum Abtippen - eine Oberflaeche, die eine
    Einstellung anbietet und beim Speichern schweigt, ist schlimmer als
    eine, die sagt, dass sie es nicht kann.
    """
    found = shutil.which("pkexec")
    return [found] if found else []


@dataclass(frozen=True)
class UpdateOutcome:
    """Was aus dem Versuch geworden ist, die Maschinendatei zu aendern."""

    written: bool
    message: str
    command: tuple[str, ...] = ()


def set_update_value(key: str, value: Any, *,
                     runner: Runner | None = None) -> UpdateOutcome:
    """Eine Aktualisierungseinstellung setzen, mit Rechten oder ohne.

    Erst der unmittelbare Weg, dann der erhoehte. Die Reihenfolge ist
    nicht Bequemlichkeit: die Anwendung kann laufen, waehrend
    /etc/zepos diesem Konto gehoert (ein Test, ein System mit einer
    eigenen Regel), und dann waere ein Rechtefenster eine Frage nach
    etwas, das schon erlaubt ist.
    """
    command = tuple(update_elevated_command(key, value))
    if update_writable():
        try:
            config = update.set_value(key, json.dumps(value))
        except update.UnusableConfig as problem:
            return UpdateOutcome(False, str(problem), command)
        update.apply(config, runner=runner)
        return UpdateOutcome(True, "", command)

    lifting = elevator()
    if not lifting:
        return UpdateOutcome(
            False,
            "Diese Einstellung gehört der Maschine und nicht diesem "
            "Konto. Auf diesem System ist kein pkexec vorhanden, also "
            "geht es nur so:\n    sudo " + " ".join(command),
            command)

    runner = runner or subprocess.run
    completed = runner([*lifting, *command], capture_output=True, text=True)
    if completed.returncode == 0:
        return UpdateOutcome(True, "", command)
    return UpdateOutcome(
        False,
        (completed.stderr or "").strip()
        or f"{' '.join(command)} endete mit {completed.returncode}",
        command)


# --------------------------------------------------------------------
# Die Sprache und die Zeitzone - die dritte und vierte Einstellung,
# die der Maschine gehoert
# --------------------------------------------------------------------
#
# WAS BESTELLT WURDE
#     Der Nutzer am 02.09.2026, woertlich: "ausserdem will ich i18n
#     unterstuetzung man muss in den einstellungen auch die sprache
#     wechseln koennen und die uhrzeit anhand der zeitzone".
#
# WAS GEMESSEN WURDE, BEVOR ETWAS GEBAUT WURDE
#     Die Uhr der Leiste war NICHT kaputt. custom/date ruft das blanke
#     `date` (src/templates/date-config.template, ohne TZ davor), und
#     das liest /etc/localtime - die Zeitzone der Maschine also, wie es
#     sich gehoert. Was fehlte, war der Weg, sie nach der Installation
#     zu AENDERN: im ganzen Baum gab es keinen. Der Assistent fragt sie
#     einmal ab, und danach war sie fuer immer gesetzt.
#
#     Warum das mehr ist als eine Bequemlichkeit: der Assistent schlug
#     die Zone bis heute aus der SPRACHE vor, "en" also UTC. Wer ZepOS
#     auf Englisch installierte und durchklickte, bekam eine Uhr auf
#     UTC und keinen Weg zurueck. Die Ableitung ist mit dieser Aufgabe
#     gefallen (installer/gui/pages.py), der fehlende Weg ist diese
#     Seite.
#
# WARUM BEIDES DURCH localectl UND timedatectl GEHT
#     Der Kopf von src/region.py fuehrt es aus: sie schreiben GENAU die
#     Dateien, die der Greeter und der Installer schon lesen, und
#     Polkit fragt dabei ueber denselben Agenten nach, den der
#     Schreibtisch ohnehin startet. Eine eigene Datei unter /etc/zepos
#     daneben waere eine zweite Wahrheit ueber dieselbe Sache.
#
#     Deshalb gibt es hier auch KEIN Gegenstueck zu theme_writable():
#     die Frage ist nicht, ob dieses Konto eine Datei schreiben darf,
#     sondern ob der Befehl ueberhaupt vorhanden ist. Alles Weitere
#     entscheidet Polkit, und zwar erst beim Klick.

LABEL_LANGUAGE = "Sprache"
LABEL_TIMEZONE = "Zeitzone"

GROUP_REGION = "Sprache und Zeit"

NOTE_REGION_GROUP = (
    "Beides gehört der MASCHINE und nicht diesem Konto: der "
    "Anmeldebildschirm spricht eine Sprache, bevor sich jemand "
    "angemeldet hat, und die Zeitzone entscheidet, welche Uhrzeit jeder "
    "Zeitstempel dieses Rechners trägt. Beides wird sofort geschrieben, "
    "und dabei wird nach Rechten gefragt."
)

# Was ein Sprachwechsel WANN erreicht. Im Wortlaut, damit die
# Oberflaeche es nicht umschreibt - und weil die drei Zeitpunkte
# GEMESSEN sind und nicht versprochen:
#
#   sofort        Die Anmeldemaske. src/bin/zepos-greeter liest LANG bei
#                 jedem Start, erst aus der Umgebung, dann aus
#                 /etc/locale.conf - genau der Datei, die localectl
#                 gerade geschrieben hat. Kein Erzeugungslauf noetig,
#                 dieselbe Lage wie beim Thema.
#
#                 Und das Fenster, in dem man es umstellt. GEMESSEN am
#                 02.09.2026 mit gjs 1.88.1 und GTK 4.22.4 an einem
#                 wirklich gezeichneten Fenster:
#
#                     Gettext.setlocale(LC_MESSAGES, "en_US.UTF-8")
#                     dgettext(...)              -> "Disk space"
#                                                   (vorher "Speicherplatz")
#                     schon gebaute Beschriftung -> "Speicherplatz"
#                     neu gebaute Beschriftung   -> "Disk space"
#
#                 Der Katalog wechselt also im laufenden Prozess, aber
#                 eine bereits GEZEICHNETE Beschriftung bleibt stehen.
#                 Das AGS-Einstellungsfenster zeichnet sich nach jedem
#                 Schreiben ohnehin neu (neuLaden) und folgt deshalb
#                 sofort.
#   nach dem Lauf Leiste, Dock und die uebrigen Fenster. Sie werden beim
#                 Start der Schale EINMAL gebaut - ags-config.template
#                 legt widgets.calendar und die anderen dort an -, und
#                 nach derselben Messung folgt eine gebaute Beschriftung
#                 keinem Katalogwechsel mehr. Ein Erzeugungslauf startet
#                 die Schale neu, und die neue liest /etc/locale.conf.
#   beim Anmelden Alles ausserhalb der Schale. Die Umgebung einer
#                 laufenden Sitzung ist eine ABSCHRIFT von
#                 /etc/locale.conf, angefertigt bei der Anmeldung; ein
#                 Programm, das jetzt startet, erbt sie und nicht die
#                 Datei.
LANGUAGE_TIMING = (
    "Der Anmeldebildschirm und dieses Fenster folgen sofort. Leiste, "
    "Dock und die übrigen Fenster nach einem Erzeugungslauf - "
    "»Jetzt anwenden« macht ihn. Programme außerhalb der Oberfläche "
    "beim nächsten Anmelden."
)

# Und was ein Zeitzonenwechsel wann erreicht. Kuerzer, weil er weniger
# betrifft: hier ist nichts uebersetzt und nichts gebaut.
#
#   sofort       Alles, was die Zeit von der C-Bibliothek holt, und das
#                ist jedes Programm dieser Maschine. timedatectl legt
#                /etc/localtime neu, und der naechste Aufruf von `date`
#                liest die neue Zone - kein Neustart, keine Anmeldung.
#   binnen einer Die Uhr der Leiste. Sie fragt ihr Skript einmal je
#   Minute       Minute ab (intervalMs 60000 an custom/date in
#                ags-bar.template), also steht die neue Zeit spaetestens
#                nach einer Minute da.
TIMEZONE_TIMING = (
    "Wirkt sofort für alles, was die Uhrzeit vom System holt. Die Uhr "
    "in der Leiste fragt einmal je Minute nach und zeigt die neue Zeit "
    "deshalb spätestens nach einer Minute."
)


def language_codes() -> list[str]:
    """Die Sprachen, die diese Maschine wirklich anbieten kann.

    Aus src/region.py und nicht aus einer Aufzaehlung hier: die Regel
    ("hat einen Katalog UND eine erzeugte Sprachumgebung") ist dort
    gemessen und begruendet, und eine zweite Liste waere die erste
    Stelle, an der eine dritte Sprache nur in einer von beiden landet.

    OHNE `runner`, wie timezone_names(): beide Haelften der Regel stehen
    in DATEIEN - der Katalog liegt oder liegt nicht, und /etc/locale.gen
    nennt die Sprachumgebungen. Das blosse Ansehen dieser Seite startet
    damit keinen einzigen Prozess, und das ist Absicht: eine Seite, die
    sich ohne Prozess nicht aufbauen laesst, zwingt jeden Test daneben
    zu einem Ersatzlaeufer fuer eine blosse Auskunft.
    """
    return [language.code for language in region.available_languages()]


def language_label(code: str) -> str:
    """Der Name der Sprache, in ihrer eigenen Sprache - siehe region.py."""
    return region.language_named(code).label


def current_language() -> str:
    return region.current_language()


def language_writable() -> bool:
    """Gibt es auf dieser Maschine localectl?

    Und nicht "darf dieses Konto /etc/locale.conf schreiben": es darf es
    fast nie, und es MUSS es auch nicht - localectl geht ueber den
    Systembus, und Polkit fragt beim Klick. Ein Regler, der gesperrt
    waere, weil eine Datei root gehoert, waere hier eine Sperre gegen
    etwas, das ohnehin funktioniert.
    """
    return region.can_set_language()


def language_elevated_command(code: str) -> list[str]:
    return region.language_command(code)


def set_language(code: str, *, runner: Runner | None = None) -> UpdateOutcome:
    """Die Sprache der Maschine setzen.

    KEIN pkexec DAVOR, anders als beim Thema. localectl redet mit
    systemd-localed ueber den Systembus, und die Rechtefrage stellt
    Polkit - dasselbe Fenster, derselbe Agent, nur ohne einen zweiten
    erhoehten Prozess dazwischen. `pkexec localectl` waere zwei
    Rechteabfragen fuer eine Handlung.
    """
    try:
        command = tuple(language_elevated_command(code))
    except region.UnknownLanguage as problem:
        return UpdateOutcome(False, str(problem), ())

    if not language_writable():
        return UpdateOutcome(
            False,
            "Die Sprache gehört der Maschine und nicht diesem Konto, "
            "weil der Anmeldebildschirm dazugehört. Auf diesem System "
            "gibt es kein localectl, also geht es nur über die Datei "
            f"selbst: {region.locale_conf_path()}",
            command)

    runner = runner or subprocess.run
    completed = runner(list(command), capture_output=True, text=True)
    if completed.returncode == 0:
        return UpdateOutcome(True, "", command)
    return UpdateOutcome(
        False,
        (completed.stderr or "").strip()
        or f"{' '.join(command)} endete mit {completed.returncode}",
        command)


def timezone_names() -> list[str]:
    """Die Zonennamen, die `timedatectl set-timezone` auch annimmt.

    OHNE `runner`, anders als language_codes(): die Liste kommt aus
    einer DATEI (region.ZONE_FILE) und nicht aus einem Prozess. Ein
    Parameter, den niemand braucht, waere die Andeutung, hier starte
    etwas.
    """
    return region.timezones()


def current_timezone() -> str:
    return region.current_timezone()


def timezone_writable() -> bool:
    return region.can_set_timezone()


def timezone_elevated_command(zone: str) -> list[str]:
    return region.timezone_command(zone)


def set_timezone(zone: str, *, runner: Runner | None = None) -> UpdateOutcome:
    """Die Zeitzone der Maschine setzen.

    Der Name wird VOR dem Aufruf gegen die Datenbank gehalten -
    region.timezone_command() wirft sonst -, und das ist nicht doppelt
    gemoppelt: `date` nimmt JEDEN Namen an und druckt fuer einen
    unbekannten die UTC-Zeit mit dem erfundenen Kuerzel, die Begruendung
    dazu steht in src/doctor.py. Eine Zone, die dieses Fenster
    durchliesse, waere eine Uhr, die still falsch geht.
    """
    try:
        command = tuple(timezone_elevated_command(zone))
    except region.UnknownTimezone as problem:
        return UpdateOutcome(False, str(problem), ())

    if not timezone_writable():
        return UpdateOutcome(
            False,
            "Die Zeitzone gehört der Maschine und nicht diesem Konto. "
            "Auf diesem System gibt es kein timedatectl, also geht es "
            f"nur über {region.localtime_path()} selbst.",
            command)

    runner = runner or subprocess.run
    completed = runner(list(command), capture_output=True, text=True)
    if completed.returncode == 0:
        return UpdateOutcome(True, "", command)
    return UpdateOutcome(
        False,
        (completed.stderr or "").strip()
        or f"{' '.join(command)} endete mit {completed.returncode}",
        command)
