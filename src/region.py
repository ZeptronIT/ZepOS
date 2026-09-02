# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Sprache und die Zeitzone dieser MASCHINE - lesen, pruefen, setzen lassen.

WARUM BEIDES DER MASCHINE GEHOERT UND NICHT DIESEM KONTO
    Dieselbe Messung wie beim Thema (Kopf von src/theme.py): der
    Anmeldebildschirm steht VOR jedem Konto. src/bin/zepos-greeter baut
    seine Maske aus LANG - erst aus der Umgebung, dann aus
    /etc/locale.conf -, und beides gibt es, bevor sich jemand angemeldet
    hat. Eine Sprache, die einem Konto gehoerte, koennte die Maske also
    gar nicht kennen.

    Die Zeitzone gehoert aus dem staerkeren Grund dazu: sie ist keine
    Anzeigeentscheidung. /etc/localtime entscheidet, welche Zeit jeder
    Zeitstempel dieser Maschine traegt - im Protokoll, im Dateisystem,
    in einer Sicherung. Zwei Konten mit zwei Zeitzonen waeren zwei
    Antworten auf eine Frage, die eine Maschine nur einmal beantworten
    kann.

WARUM localectl UND timedatectl UND NICHT EINE EIGENE ZEPOS-EINSTELLUNG
    Weil sie GENAU DIE DATEIEN schreiben, die dieser Baum schon liest,
    und weil es die einzigen sind:

        /etc/locale.conf   liest src/bin/zepos-greeter fuer die Sprache
                           der Anmeldemaske; dorthin schreibt der
                           Installer die Wahl aus LANGUAGE_DEFAULTS
                           ueber archinstall; von dort reicht systemd
                           LANG an greetd und an jede Anmeldung weiter.
        /etc/localtime     liest die C-Bibliothek, und damit das blanke
                           `date` in der erzeugten date.sh, aus der die
                           Uhr der Leiste ihren Text bekommt.

    Eine eigene Datei unter /etc/zepos daneben waere eine ZWEITE
    WAHRHEIT ueber dieselbe Sache: ZepOS haette einen Wert, das System
    haette einen, und wer sie auseinanderbringt, bekommt eine Uhr, die
    etwas anderes anzeigt als `date` sagt. Genau dieser Fehler ist in
    diesem Baum schon einmal bezahlt worden - vier Tabellen fuer
    dieselben VPN-Vorgaben, `set` schrieb an eine Stelle, die niemand
    las.

    Das Thema hat aus dem umgekehrten Grund eine eigene Datei: eine
    ZepOS-Palette ist ein Begriff, den nur ZepOS kennt, und es gibt kein
    Systemwerkzeug dafuer. Sprache und Zeitzone kennt systemd selbst,
    seit es systemd gibt.

    Und die Rechtefrage kommt damit gratis und richtig: beide Befehle
    gehen ueber den Systembus an systemd-localed beziehungsweise
    systemd-timedated, und Polkit fragt in einem Fenster nach - ueber
    denselben Agenten, den hyprland-universal-config.template ohnehin
    startet (exec-once). Kein pkexec-Umweg, kein sudo, kein eigener
    erhoehter Schreibweg, den jemand pflegen muesste.

WELCHE SPRACHEN ANGEBOTEN WERDEN, UND WARUM NICHT MEHR
    Eine Sprache wird angeboten, wenn BEIDE Bedingungen stimmen:

      1. ZepOS kann sie anzeigen. Englisch immer - die msgids IM
         Quelltext sind englisch (tests/src/test_ags_i18n.py haelt das
         fest). Jede andere braucht einen Katalog.
      2. Diese Maschine hat die Sprachumgebung erzeugt.

    Die zweite Bedingung ist nicht Vorsicht, sondern gemessen.
    GEMESSEN am 02.09.2026 mit gjs 1.88.1 gegen den gebauten Katalog:

        Gettext.setlocale(LC_MESSAGES, "fr_FR.UTF-8")  ->  null
        dgettext(...) danach: unveraendert

    Eine nicht erzeugte Sprachumgebung wird also STILL ignoriert - kein
    Fehler, keine Meldung, nur eine Auswahl, die nichts tut. Und
    `localectl set-locale` mit so einem Wert lehnt ab. Eine Sprache
    anzubieten, fuer die es keine Uebersetzung oder keine
    Sprachumgebung gibt, ist deshalb schlechter, als sie wegzulassen.

WARUM DIE NAMEN DER SPRACHEN NICHT DURCH DEN KATALOG LAUFEN
    "Deutsch" und "English" stehen in ihrer EIGENEN Sprache da, und das
    ist der ganze Zweck: wer die Oberflaeche gerade nicht lesen kann,
    sucht in dieser Liste nach dem Wort, das er kennt. Uebersetzt hiesse
    "Deutsch" auf einer englischen Oberflaeche "German" - und dann
    findet genau der Mensch seine Sprache nicht, fuer den die Liste da
    ist.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

# Die Wurzel, unter der /etc liegt. Leer auf einer Installation, gesetzt
# in einem Test - dieselbe Bauform und derselbe Zweck wie
# ZEPOS_GREETER_ROOT in src/bin/zepos-greeter, das GENAU DIESE Datei
# liest. Ein Test darf /etc nicht anfassen, und ein Vorsatz ist der
# einzige Weg dahin, der ohne Rechte auskommt.
ETC_ROOT_ENV = "ZEPOS_ETC_ROOT"

LOCALE_CONF = "etc/locale.conf"
LOCALTIME = "etc/localtime"

# Wo steht, welche Sprachumgebungen diese Maschine erzeugt. Beide
# Quellen und ihre Begruendung stehen bei generated_locales().
LOCALE_GEN = "etc/locale.gen"
# Auch dieser Pfad haengt an der Wurzel, obwohl er nicht unter /etc
# liegt: er beschreibt DIESELBE Maschine, und ein Test, der eine
# vorgibt, muss sie ganz vorgeben. Bliebe er absolut, entschiede das
# /usr/lib/locale des Entwicklers mit darueber, was ein Test misst.
LOCALE_DIRECTORY = "usr/lib/locale"

# Wo glibc eine Zeitzone nachschlaegt, und die Variable, die es
# verschiebt. Beide Schreibweisen sind aus src/doctor.py uebernommen und
# nicht danebengeschrieben: der Arzt beantwortet Fragen ueber DIESELBE
# Datenbank, und zwei Orte, an denen sie steht, waeren zwei Antworten.
ZONEINFO = Path("/usr/share/zoneinfo")
ZONEINFO_VARIABLE = "TZDIR"

# Die Datei, aus der die Zonennamen kommen, und der Befehl, der
# dieselbe Liste fuer einen Menschen ausdruckt.
#
# WARUM EINE DATEI UND NICHT DER BEFEHL
#     Weil es dieselbe Liste ist und die Datei keinen Prozess kostet.
#     GEMESSEN am 02.09.2026 auf dieser Maschine, als Mengen verglichen:
#
#         timedatectl list-timezones                  598 Namen
#         Z- und L-Zeilen aus tzdata.zi               598 Namen
#         Unterschied                                 keiner
#
#     Das ist kein Zufall: systemd baut seine Antwort aus genau dieser
#     Datei. Sie zu lesen heisst also, dieselbe Quelle zu lesen - und
#     nicht, eine zweite Liste zu fuehren.
#
# WARUM NICHT DAS VERZEICHNIS ABLAUFEN
#     /usr/share/zoneinfo enthaelt neben den Zonen auch posix/, right/,
#     zone.tab, leapseconds und Altnamen wie "Eire". Eine Liste, die
#     etwas anbietet, das `timedatectl set-timezone` danach ablehnt,
#     ist eine Liste, die luegt.
#
# DIE FORM DER DATEI, und sie ist der Grund fuer die zwei Faelle unten:
#     Z <name> ...          eine Zone, ihr Name steht als ZWEITES
#     L <ziel> <name>       ein Verweis, sein Name steht als DRITTES
#     Zeilen mit R, Fortsetzungszeilen und Kommentare sind keins von
#     beidem und gehen niemanden etwas an.
ZONE_FILE = "tzdata.zi"
ZONE_LISTING = ("timedatectl", "list-timezones")

# Die Vorgabe, wenn nichts zu lesen ist. UTC und kein Ort: es ist die
# einzige Zeitzone, die keine Behauptung ueber den Aufenthaltsort eines
# Menschen enthaelt.
DEFAULT_TIMEZONE = "UTC"

# Die Domaene des Katalogs der Oberflaeche und die Orte, an denen er
# liegen kann. Wortgleich zu src/templates/ags-i18n.template und
# po/build.sh - dieselbe Domaene, dieselben zwei Verzeichnisse.
DOMAIN = "zepos-desktop"
SYSTEM_LOCALEDIR = Path("/usr/share/locale")
LOCALEDIR_ENV = "ZEPOS_LOCALEDIR"
CATALOGUE_SUBPATH = "LC_MESSAGES"


@dataclass(frozen=True)
class Language:
    """Eine Sprache, so wie diese Maschine sie kennen muss.

    `code` ist der Name des Katalogverzeichnisses (de, en) und zugleich
    der Schluessel, unter dem der Installer sie fuehrt. `locale` ist
    das, was in LANG steht und was setlocale() annimmt. `label` ist der
    Name, unter dem ein Mensch sie sucht - in ihrer eigenen Sprache,
    siehe den Kopf.
    """

    code: str
    locale: str
    label: str


# Die Sprachen, die dieses Projekt ueberhaupt kennt.
#
# WARUM DIE TABELLE HIER STEHT UND NICHT AUS installer/ KOMMT
#     Weil dieses Modul auf einer INSTALLATION laeuft und der Installer
#     dort nicht liegt: /usr/share/zepos hat src/, nicht installer/.
#     Ein Import waere ein Import, der auf genau der Maschine fehlt, auf
#     der er gebraucht wird.
#
#     Dass sie trotzdem nicht auseinanderlaufen kann, haelt
#     tests/src/test_region.py fest: er legt diese Tabelle gegen
#     installer/gui/pages.py:LANGUAGE_DEFAULTS. Dieselbe Vorrichtung und
#     dieselbe Begruendung wie in tests/src/test_login.py, der die Liste
#     des Greeters gegen dieselbe Tabelle haelt.
LANGUAGES: tuple[Language, ...] = (
    Language("de", "de_DE.UTF-8", "Deutsch"),
    Language("en", "en_US.UTF-8", "English"),
)

# Die Sprache, in der die msgids geschrieben sind. Sie braucht keinen
# Katalog - sie IST der Katalog, und sie ist deshalb die einzige, die
# auf jeder Installation vorhanden ist.
SOURCE_LANGUAGE = "en"

# Womit ausgeliefert wird, wenn nichts zu lesen ist. Dieselbe Wahl wie
# in installer/gui/pages.py (PageState.language = "de").
DEFAULT_LANGUAGE = "de"


class UnknownLanguage(ValueError):
    """Ein Sprachcode, den dieses Projekt nicht kennt."""


class UnknownTimezone(ValueError):
    """Ein Zonenname, den die Datenbank dieser Maschine nicht kennt."""


# --------------------------------------------------------------------
# Wo die Dateien liegen
# --------------------------------------------------------------------

def etc_root() -> Path:
    """Die Wurzel, unter der /etc gesucht wird."""
    return Path(os.environ.get(ETC_ROOT_ENV) or "/")


def locale_conf_path() -> Path:
    return etc_root() / LOCALE_CONF


def localtime_path() -> Path:
    return etc_root() / LOCALTIME


def zoneinfo_directory() -> Path:
    """Die Zeitzonendatenbank, TZDIR beachtet - so wie glibc es tut."""
    return Path(os.environ.get(ZONEINFO_VARIABLE) or ZONEINFO)


# --------------------------------------------------------------------
# Was gerade gilt
# --------------------------------------------------------------------

def read_lang(path: Path | None = None) -> str:
    """Der Wert von LANG aus /etc/locale.conf, oder "".

    Zeile fuer Zeile gelesen und NICHTS ausgefuehrt, wortgleich zur
    Vorgehensweise in src/bin/zepos-greeter: die Datei sieht aus wie ein
    Shell-Schnipsel und ist keines - sie in eine Shell zu geben hiesse,
    einer Datei unter /etc zu erlauben, Befehle zu enthalten.

    Die LETZTE Zuweisung gewinnt, weil eine Shell es auch so machen
    wuerde und weil eine Datei mit zwei LANG-Zeilen sonst je nach Leser
    zwei Antworten gaebe.
    """
    target = path if path is not None else locale_conf_path()
    value = ""
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("LANG="):
            continue
        value = stripped[len("LANG="):].strip().strip('"').strip("'")
    return value


def current_locale() -> str:
    """Die Sprachumgebung dieser MASCHINE, aus der Datei.

    Und nicht aus der Umgebung dieses Prozesses, obwohl LANG dort
    steht: die Umgebung einer laufenden Sitzung ist eine ABSCHRIFT der
    Datei, angefertigt bei der Anmeldung. Wer die Sprache umstellt und
    danach etwas startet, bekommt aus der Umgebung den alten Wert - und
    genau das saehe aus, als haette die Einstellung nichts getan.

    Die Umgebung bleibt der Rueckfall, weil es Maschinen ohne
    /etc/locale.conf gibt (ein Container, ein Chroot), und dort ist sie
    das einzige, was es gibt.
    """
    return read_lang() or os.environ.get("LANG", "")


def language_of(locale: str) -> str:
    """Der Sprachcode zu einer Sprachumgebung: "de_DE.UTF-8" -> "de".

    Ueber die Tabelle und nicht ueber den ersten Unterstrich: de_AT und
    de_DE sind beide "de", en_GB waere es auch, und keins davon liefert
    dieses Projekt aus. Was die Tabelle nicht kennt, bekommt "" - eine
    ehrliche Nichtantwort, keine geratene.
    """
    if not locale:
        return ""
    stem = locale.split(".")[0].split("@")[0]
    for language in LANGUAGES:
        if language.locale.split(".")[0] == stem or language.code == stem:
            return language.code
    return ""


def current_language() -> str:
    """Der Sprachcode, in dem diese Maschine spricht."""
    return language_of(current_locale()) or DEFAULT_LANGUAGE


def language_named(code: str) -> Language:
    for language in LANGUAGES:
        if language.code == code:
            return language
    raise UnknownLanguage(
        f"es gibt keine Sprache namens {code!r}. Bekannt sind: "
        f"{', '.join(language.code for language in LANGUAGES)}.")


def current_timezone() -> str:
    """Die Zeitzone dieser Maschine, aus /etc/localtime.

    An dem Symlink und nicht an `timedatectl show`: die C-Bibliothek
    liest genau diese Datei, und die Uhr der Leiste liest die
    C-Bibliothek. Wer stattdessen den Dienst fragt, beantwortet eine
    Frage ueber systemd und nicht ueber die Uhr, die der Nutzer ansieht.

    Kein Symlink, sondern eine kopierte Datei - das kommt vor - ist
    keine Antwort, sondern eine Nichtantwort: der Name der Zone steht
    dann nirgends. Dann bleibt es bei UTC, und die Oberflaeche zeigt es
    als "unveraendert" an, statt eine Zone zu behaupten.
    """
    target = localtime_path()
    try:
        resolved = os.readlink(target)
    except OSError:
        return DEFAULT_TIMEZONE
    database = zoneinfo_directory()
    path = Path(resolved)
    if not path.is_absolute():
        path = (target.parent / path).resolve(strict=False)
    try:
        return str(path.relative_to(database))
    except ValueError:
        # Ein Ziel ausserhalb der Datenbank ist kein Zonenname. Es zu
        # melden waere richtig, es zu RATEN waere falsch.
        return DEFAULT_TIMEZONE


# --------------------------------------------------------------------
# Was diese Maschine anbieten kann
# --------------------------------------------------------------------

def _normalised(name: str) -> str:
    """"de_DE.utf8" und "de_DE.UTF-8" auf eine Schreibweise bringen.

    `locale -a` schreibt das eine, LANG das andere - dieselbe
    Sprachumgebung, zwei Schreibweisen. Der Vergleich ist aus
    tests/render/desktop_session.py uebernommen, wo derselbe Unterschied
    schon einmal einen Befund erzeugt hat, den es nicht gab.
    """
    return name.lower().replace("-", "")


def generated_locales() -> set[str]:
    """Die Sprachumgebungen, die auf DIESER Maschine erzeugt sind.

    AUS ZWEI DATEIQUELLEN UND NICHT AUS `locale -a`
        `locale -a` waere die genaueste Antwort - es ist die Liste, an
        der setlocale() scheitert oder nicht. Es ist aber ein PROZESS,
        und dieser Aufruf steht im Weg zum blossen ANSEHEN der
        Einstellungsseite. tests/conftest.py verbietet einem Test aus
        gutem Grund, Prozesse zu starten; eine Seite, die sich ohne
        einen nicht einmal aufbauen laesst, zwingt jeden Test daneben
        zu einem Ersatzlaeufer fuer eine blosse Auskunft.

        Gelesen wird deshalb dort, wo die Entscheidung STEHT:

          /etc/locale.gen        Die Zeilen ohne '#'. Genau sie liest
                                 locale-gen, und genau sie schreibt der
                                 Installer ueber archinstall. Auf Arch
                                 ist das die Datei, in der steht, welche
                                 Sprachumgebungen es geben soll.
          /usr/lib/locale/*      Die Verzeichnisse, die glibc daneben
                                 kennt. Auf einer Maschine ohne
                                 locale-gen - einem Container etwa - ist
                                 das die einzige Spur.

        GEMESSEN am 02.09.2026 auf dieser Maschine: locale.gen nennt
        de_DE.UTF-8 und en_US.UTF-8, `locale -a` nennt dieselben zwei
        plus C, C.utf8 und POSIX. Ueber die Sprachen, um die es hier
        geht, sagen beide dasselbe -
        tests/src/test_region.py rechnet es bei jedem Lauf nach.

    WAS DAS SCHLECHTESTENFALLS KOSTET
        Eine Zeile in locale.gen, die nie durch locale-gen gelaufen ist.
        Dann steht eine Sprache zur Wahl, die es noch nicht gibt - und
        `localectl set-locale` lehnt sie ab, mit seiner eigenen Meldung,
        die das Fenster anzeigt. Ein sichtbarer Fehlschlag im Moment des
        Klicks, kein stiller.
    """
    found: set[str] = set()
    try:
        text = (etc_root() / LOCALE_GEN).read_text(encoding="utf-8")
    except OSError:
        text = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # "de_DE.UTF-8 UTF-8" - der Name steht vorn, der Zeichensatz
        # dahinter ist die Angabe fuer locale-gen und nicht Teil des
        # Namens.
        found.add(_normalised(stripped.split()[0]))

    try:
        for entry in (etc_root() / LOCALE_DIRECTORY).iterdir():
            if entry.is_dir():
                found.add(_normalised(entry.name))
    except OSError:
        pass
    return found


def catalogue_directories() -> list[Path]:
    """Wo ein Katalog der Oberflaeche liegen kann, in dieser Reihenfolge.

    ZEPOS_LOCALEDIR SCHLAEGT BEIDE, es steht nicht bloss davor -
    derselbe Name, derselbe Zweck und dieselbe Vorrangregel wie in
    src/templates/ags-i18n.template ("ZEPOS_LOCALEDIR schlaegt beides").

    Dass es SCHLAEGT und nicht nur vorangeht, ist gemessen und nicht
    Geschmack: mit einer blossen Voranstellung fand ein Testlauf, der
    ein LEERES Katalogverzeichnis vorgab, trotzdem den Katalog aus
    po/build daneben - und behauptete damit eine Sprache, die er gerade
    wegnehmen wollte.

    Ohne die Variable: die Paketwurzel, dann der Bauplatz eines
    Quellbaums (po/build), den po/build.sh fuellt.
    """
    override = os.environ.get(LOCALEDIR_ENV)
    if override:
        return [Path(override)]
    return [SYSTEM_LOCALEDIR,
            Path(__file__).resolve().parents[1] / "po" / "build"]


def translated_languages() -> set[str]:
    """Die Sprachcodes, in denen die Oberflaeche wirklich sprechen kann.

    Die Quellsprache immer, und jede weitere, fuer die ein .mo liegt.
    Gesucht wird nach der DATEI und nicht nach dem .po im Quellbaum:
    ein Katalog, der nie uebersetzt wurde, ist auf einer Installation
    nicht vorhanden, und eine Auswahl daraus faende nichts vor.
    """
    found = {SOURCE_LANGUAGE}
    for directory in catalogue_directories():
        for language in LANGUAGES:
            catalogue = (directory / language.code / CATALOGUE_SUBPATH
                         / f"{DOMAIN}.mo")
            if catalogue.is_file():
                found.add(language.code)
    return found


def available_languages() -> list[Language]:
    """Was das Fenster anbieten darf, in der Reihenfolge von LANGUAGES.

    Der Schnitt aus "hat einen Katalog" und "hat eine erzeugte
    Sprachumgebung" - die Begruendung fuer beide Haelften steht im Kopf.

    Die JETZT eingestellte Sprache ist immer dabei, auch wenn eine der
    beiden Bedingungen fehlt. Sonst zeigte die Liste den geltenden Wert
    nicht an, und eine Auswahl, in der der aktuelle Zustand fehlt, ist
    eine Auswahl, die beim blossen Ansehen etwas anderes einstellt.
    """
    catalogues = translated_languages()
    locales = generated_locales()
    now = current_language()
    return [language for language in LANGUAGES
            if language.code == now
            or (language.code in catalogues
                and _normalised(language.locale) in locales)]


def timezones() -> list[str]:
    """Die Zonennamen, die `timedatectl set-timezone` annimmt.

    Aus tzdata.zi gelesen - siehe den Kopf von ZONE_FILE, wo steht,
    warum das dieselbe Liste ist und weshalb kein Prozess dafuer
    startet.

    Sortiert, weil die Datei es nicht ist: sie steht in der Reihenfolge,
    in der tzdata sie pflegt, und eine Auswahlliste, in der Europa
    zwischen Amerika und Asien auftaucht, ist keine Liste zum
    Nachschlagen.

    Eine fehlende Datei gibt eine leere Liste und keine Ausnahme: eine
    Maschine ohne Zeitzonendatenbank ist eine, auf der niemand eine Zone
    waehlen kann, und das ist eine Auskunft und kein Absturz.
    """
    try:
        text = (zoneinfo_directory() / ZONE_FILE).read_text(encoding="utf-8")
    except OSError:
        return []
    namen = []
    for line in text.splitlines():
        felder = line.split()
        if len(felder) >= 2 and felder[0] == "Z":
            namen.append(felder[1])
        elif len(felder) >= 3 and felder[0] == "L":
            namen.append(felder[2])
    return sorted(namen)


def known_timezone(zone: str) -> bool:
    """Kennt die Datenbank DIESER Maschine diesen Namen?

    An der Datei und nicht an `date`, aus dem Grund, den
    src/doctor.py:check_clock_zones ausfuehrt: `TZ=Mars/Olympus_Mons
    date` endet mit 0 und druckt die UTC-Zeit mit "Mars" als Kuerzel.
    Ein Werkzeug, das jeden Namen annimmt, kann keinen pruefen.

    Ein Name, der aus der Datenbank herausfuehrt, ist kein Zonenname -
    dieselbe Regel wie in src/clocks.py, und aus demselben Grund: der
    Name wird zu einem Pfad, und ein Pfad mit ".." oder einem
    fuehrenden Schraegstrich ist ein Pfad, der die Datenbank verlaesst.
    """
    if not zone or zone.startswith("/") or ".." in zone.split("/"):
        return False
    return (zoneinfo_directory() / zone).is_file()


# --------------------------------------------------------------------
# Die Befehle, mit denen es gesetzt wird
# --------------------------------------------------------------------

def language_command(code: str) -> list[str]:
    """`localectl set-locale LANG=<locale>` - siehe den Kopf.

    LANG und nicht LC_MESSAGES: LANG setzt alle Kategorien auf einmal,
    und wer die Sprache umstellt, will auch das Datumsformat und die
    Sortierung umgestellt haben. LC_MESSAGES allein waere eine
    Oberflaeche in der einen Sprache mit den Zahlen der anderen.
    """
    return ["localectl", "set-locale", f"LANG={language_named(code).locale}"]


def timezone_command(zone: str) -> list[str]:
    """`timedatectl set-timezone <zone>` - siehe den Kopf."""
    if not known_timezone(zone):
        raise UnknownTimezone(
            f"{zone!r} steht nicht in {zoneinfo_directory()}. "
            f"`{' '.join(ZONE_LISTING)}` nennt die Namen, die diese "
            f"Maschine kennt.")
    return ["timedatectl", "set-timezone", zone]


def can_set_language() -> bool:
    """Gibt es auf dieser Maschine ueberhaupt localectl?"""
    return shutil.which("localectl") is not None


def can_set_timezone() -> bool:
    """Gibt es auf dieser Maschine ueberhaupt timedatectl?"""
    return shutil.which(ZONE_LISTING[0]) is not None
