# SPDX-License-Identifier: GPL-3.0-or-later
"""Welche Zeitzonen es gibt, und in welcher dieses Medium gerade laeuft.

WORAUF DIESE DATEI ANTWORTET
    Der Assistent fragte die Zeitzone bis zum 02.09.2026 als FREIES
    TEXTFELD ab, vorbelegt mit einem Wert, den er aus der SPRACHE ableitete
    ("en" -> UTC). Beides ist falsch, und jedes auf seine Weise:

      das Feld       `date` nimmt JEDEN Namen an. "Europe/Berln" wird
                     anstandslos installiert; danach druckt date(1) die
                     UTC-Zeit mit "Berln" als Kuerzel, Rueckgabewert 0,
                     leere Fehlerausgabe. Die Messung dazu steht in
                     src/doctor.py. Ein Tippfehler bei der Installation
                     wird so zu einer Uhr, die still zwei Stunden falsch
                     geht - und bis zu dieser Aufgabe gab es keinen Weg,
                     sie hinterher zu korrigieren.
      die Ableitung  Eine Sprache ist kein Ort. Englisch wird auf sechs
                     Kontinenten gesprochen, und "en" auf UTC abzubilden
                     ist dieselbe Sorte Annahme wie eine Zeitzone auf ein
                     Land abzubilden - src/clocks.py fuehrt sie in der
                     Gegenrichtung aus ("Europe/Zurich deckt drei Laender
                     ab, Etc/GMT-3 keins"). Wer auf Englisch
                     installierte und nicht zufaellig in der Zone UTC
                     lebt, bekam eine Uhr, die falsch geht.

    Was an die Stelle der Ableitung tritt, ist eine TATSACHE: die Zone,
    in der das Medium gerade laeuft. Sie steht in /etc/localtime, und
    dorthin hat sie entweder das Startmedium gesetzt oder der Mensch, der
    davorsitzt. Wo nichts zu lesen ist, bleibt es bei UTC - der einzigen
    Zone, die keine Behauptung ueber einen Aufenthaltsort enthaelt.

WARUM DAS HIER STEHT UND NICHT src/region.py BENUTZT
    Weil der Assistent auf dem MEDIUM laeuft und src/ dort nicht liegt:
    packaging/zepos-installer bringt installer/ mit und sonst nichts vom
    Baum. Ein Import waere ein Import, der genau auf der Maschine fehlt,
    auf der er gebraucht wird - dieselbe Lage und dieselbe Antwort wie
    bei installer/core/i18n.py neben src/templates/ags-i18n.template.

    Es ist ausdruecklich KEINE zweite Mechanik: dieselbe Datei
    (tzdata.zi), dieselben zwei Zeilenarten, dieselbe Vorgabe, dieselbe
    Ablehnung eines Namens, der die Datenbank verlaesst.
    tests/installer/test_zeitzone.py haelt beide Fassungen gegeneinander
    und wird rot, sobald sie auseinanderlaufen.

    Das EINE, was hier steht und dort nicht, ist matching(). Es ist kein
    zweiter Weg zu denselben Namen, sondern das Suchfeld der
    Textoberflaeche: die grafische hat eines im Auswahlfeld, ein
    Terminal hat keins, und src/region.py bedient kein Terminal. Die
    Begruendung steht bei der Funktion selbst.
"""
from __future__ import annotations

import difflib
import os
from pathlib import Path

# Wo glibc eine Zeitzone nachschlaegt, und die Variable, die es
# verschiebt. Wortgleich zu src/region.py und src/doctor.py.
ZONEINFO = Path("/usr/share/zoneinfo")
ZONEINFO_VARIABLE = "TZDIR"

# Die Datei, aus der die Zonennamen kommen. GEMESSEN am 02.09.2026 als
# Mengenvergleich: die Z- und L-Zeilen dieser Datei sind GENAU die 598
# Namen, die `timedatectl list-timezones` nennt - kein Unterschied.
# systemd baut seine Antwort aus derselben Datei.
#
#     Z <name> ...        eine Zone, ihr Name steht als ZWEITES
#     L <ziel> <name>     ein Verweis, sein Name steht als DRITTES
ZONE_FILE = "tzdata.zi"

# Die Datei, in der die Zone der laufenden Maschine steht.
LOCALTIME = "etc/localtime"

# Die Vorgabe, wenn nichts zu lesen ist.
DEFAULT_TIMEZONE = "UTC"

# Die Wurzel, unter der /etc gesucht wird. Wie ZEPOS_ETC_ROOT in
# src/region.py und ZEPOS_GREETER_ROOT in src/bin/zepos-greeter: ein
# Test darf /etc nicht anfassen, und ein Vorsatz ist der einzige Weg
# dorthin, der ohne Rechte auskommt.
ETC_ROOT_ENV = "ZEPOS_ETC_ROOT"

# Wie aehnlich ein Name einem Zonennamen sein muss, damit er als
# Tippfehler durchgeht, und wie viele Vorschlaege hoechstens genannt
# werden. Beides gilt nur fuer die TEXTOBERFLAECHE - siehe matching().
#
# 0.6 ist die Vorgabe von difflib und ist hier GEMESSEN und nicht
# uebernommen. Am 02.09.2026 gegen die 598 Namen dieser Maschine:
#
#     "Europe/Berln"      -> Europe/Berlin an erster Stelle
#     "Europe/Berlim"     -> Europe/Berlin an erster Stelle
#     "Amerika/New_York"  -> America/New_York an erster Stelle
#
# Zehn, weil ein Fenster in einem Textterminal herkoemmlich
# vierundzwanzig Zeilen hat und die Frage, die Klage und die neue Frage
# davon schon vier brauchen. Was darueber hinausgeht, wird GEZAEHLT und
# nicht abgeschnitten: eine Liste, die stillschweigend endet, sieht aus
# wie die ganze Antwort.
SUGGESTION_CUTOFF = 0.6
SUGGESTION_LIMIT = 10


def etc_root() -> Path:
    return Path(os.environ.get(ETC_ROOT_ENV) or "/")


def zoneinfo_directory() -> Path:
    return Path(os.environ.get(ZONEINFO_VARIABLE) or ZONEINFO)


def known(zone: str) -> bool:
    """Kennt die Datenbank dieses Mediums diesen Namen?

    An der DATEI und nicht an `date`, aus dem Grund im Kopf: ein
    Werkzeug, das jeden Namen annimmt, kann keinen pruefen.

    Ein Name, der aus der Datenbank herausfuehrt, ist kein Zonenname.
    Dieselbe Regel wie in src/clocks.py und aus demselben Grund: der
    Name WIRD zu einem Pfad, und ein fuehrender Schraegstrich oder ein
    ".." darin verlaesst das Verzeichnis.
    """
    if not zone or zone.startswith("/") or ".." in zone.split("/"):
        return False
    return (zoneinfo_directory() / zone).is_file()


def database_present() -> bool:
    """Gibt es auf diesem Medium ueberhaupt eine Zeitzonendatenbank?

    WOZU DIE FRAGE UEBERHAUPT GESTELLT WIRD
        Weil known() ohne Datenbank JEDEN Namen ablehnt, UTC
        eingeschlossen - es fragt nach einer Datei, und wo kein
        Verzeichnis ist, ist auch keine Datei. Eine Pruefung, die daraus
        einen Befund macht, wuerde auf einem Medium ohne tzdata jede
        Installation anhalten, und zwar mit dem Satz "diese Zone gibt es
        nicht" ueber eine Zone, die es sehr wohl gibt. Das waere eine
        Behauptung, die dieses Medium nicht belegen kann.

        Deshalb prueft installer/core/validate.py erst hier nach und
        klagt nur, wenn es eine Datenbank GIBT und der Name nicht darin
        steht. Dieselbe Haltung wie bei all_zones(), das eine fehlende
        Datenbank als leere Liste und nicht als Ausnahme meldet: eine
        Auskunft und kein Absturz.
    """
    return zoneinfo_directory().is_dir()


def all_zones() -> list[str]:
    """Die Zonennamen, sortiert - oder eine leere Liste.

    Eine fehlende Datenbank ist kein Fehler, sondern ein Medium, auf dem
    keine Auswahl moeglich ist. Der Assistent zeigt dann das, was er
    gelesen hat, und nicht eine leere Liste, die wie ein Absturz
    aussieht - siehe choices().
    """
    try:
        text = (zoneinfo_directory() / ZONE_FILE).read_text(encoding="utf-8")
    except OSError:
        return []
    names = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] == "Z":
            names.append(fields[1])
        elif len(fields) >= 3 and fields[0] == "L":
            names.append(fields[2])
    return sorted(names)


def running() -> str:
    """Die Zone, in der DIESES Medium gerade laeuft.

    Am Symlink /etc/localtime und nicht an `timedatectl`: die
    C-Bibliothek liest genau diese Datei, und die Uhr, die der Mensch vor
    dem Assistenten sieht, liest die C-Bibliothek. Ein Ziel ausserhalb
    der Datenbank ist kein Zonenname - dann bleibt es bei UTC, statt
    einen zu raten.
    """
    target = etc_root() / LOCALTIME
    try:
        resolved = os.readlink(target)
    except OSError:
        return DEFAULT_TIMEZONE
    path = Path(resolved)
    if not path.is_absolute():
        path = (target.parent / path).resolve(strict=False)
    try:
        name = str(path.relative_to(zoneinfo_directory()))
    except ValueError:
        return DEFAULT_TIMEZONE
    return name if known(name) else DEFAULT_TIMEZONE


def choices() -> list[str]:
    """Die Liste fuer das Auswahlfeld, mit der laufenden Zone darin.

    Die laufende Zone steht IMMER darin, auch wenn die Datenbank sie
    nicht kennt: eine Auswahl, in der der geltende Zustand fehlt,
    stellt beim blossen Ansehen etwas anderes ein. Und die Vorgabe steht
    darin, damit es auf einem Medium ohne Datenbank ueberhaupt etwas zu
    waehlen gibt.
    """
    zones = all_zones()
    for extra in (running(), DEFAULT_TIMEZONE):
        if extra not in zones:
            zones.append(extra)
    return zones


def matching(fragment: str) -> list[str]:
    """Die Namen, die zu diesem Versuch passen - fuer die TEXTOBERFLAECHE.

    WARUM ES DAS IN DER GRAFISCHEN NICHT GIBT
        Weil die Auswahlliste dort ein Suchfeld hat (Adw.ComboRow mit
        set_enable_search, siehe installer/gui/app.py:_build_zeit). Ein
        Textterminal hat keins, und 598 Namen auszudrucken ist keine
        Hilfe, sondern eine Wand. Diese Funktion ist das Suchfeld der
        Textoberflaeche - dieselbe Aufgabe, dieselbe Quelle, nur ohne
        GTK darum.

    ZWEI SUCHEN, UND DIE ZWEITE IST DIE WICHTIGE
        Erst der TEILTREFFER, ohne Ruecksicht auf Gross- und
        Kleinschreibung: wer "berlin" tippt, meint Europe/Berlin, und
        die Datenbank ist buchstabengenau - "europe/berlin" ist dort
        KEINE Zone. Eine Suche, die den richtig geschriebenen Namen
        zurueckgibt, ist damit auch die Antwort auf einen
        Kleinschreibungsfehler.

        Wenn es keinen Teiltreffer gibt, war es vermutlich ein
        TIPPFEHLER - und der ist der Fall, um den es in dieser ganzen
        Aufgabe geht. Ein Teilstueck-Vergleich findet ihn nicht:
        "Berln" steht in keinem Namen. difflib schon, GEMESSEN, siehe
        SUGGESTION_CUTOFF.

    Die Liste kommt VOLLSTAENDIG zurueck und wird hier nicht gekuerzt.
    Wer sie ausgibt, muss sagen, wie viele es waren - sonst sieht ein
    abgeschnittenes Ende wie das Ende aus.
    """
    versuch = fragment.strip()
    if not versuch:
        return []
    zones = all_zones()
    klein = versuch.lower()
    teiltreffer = [name for name in zones if klein in name.lower()]
    if teiltreffer:
        return teiltreffer
    return difflib.get_close_matches(
        versuch, zones, n=SUGGESTION_LIMIT, cutoff=SUGGESTION_CUTOFF)
