# SPDX-License-Identifier: GPL-3.0-or-later
"""Wie sich ein installiertes ZepOS selbst aktualisiert (Aufgabe UP-1).

Der Kanal war fertig, bevor dieses Modul geschrieben wurde:
installer/core/source.py legt in jedes installierte System einen
`[zepos]`-Abschnitt mit `SigLevel = Required`, und
`iso/test-boot.py --scenario update` hat gemessen, dass eine installierte
Maschine daraus Pakete holen, pruefen und einspielen kann. Was fehlte,
war der Teil, den niemand anstoesst.

DIE DREI ENTSCHEIDUNGEN, UND WARUM SIE SO GETROFFEN SIND
    Wann?  Ein taeglicher Zeitgeber, verzoegert nach dem Start und
           zusaetzlich zufaellig gestreut. Die Verzoegerung, weil die
           ersten Minuten nach dem Einschalten dem Nutzer gehoeren und
           nicht pacman; die Streuung, weil sonst jede ZepOS-Maschine der
           Welt zur selben Sekunde denselben Server anspricht -
           GitHub Pages haelt das aus, ein spaeterer eigener Wirt
           vielleicht nicht, und ein Nutzer, dessen Aktualisierung an
           einer ueberlasteten Gegenstelle scheitert, sieht einen Fehler,
           den er nicht verursacht hat.

    Was?   Nur, was aus dem [zepos]-Abschnitt kommt. Die Arch-Basis wird
           GEZAEHLT und gemeldet, nicht angefasst. Ein unbeaufsichtigtes
           `pacman -Syu` auf einem Rolling Release ist ein Rechner, der
           eines Morgens nicht mehr startet - und der Nutzer sitzt dann
           vor einem System, das er nicht selbst kaputtgemacht hat. Wer
           es anders will, setzt `update.scope` auf "all"; dann laeuft
           genau dieses `-Syu`, und zwar weil jemand es entschieden hat.

    Sagen?  Ueber die Benachrichtigung, die ohnehin laeuft
           (libastal-notifd). Kein Zwang, kein Neustart von selbst, kein
           Fenster, das den Vordergrund nimmt.

    Alle drei stehen in einer Datei, die `zepos-settings set update.*`
    schreibt, und jede Aenderung daran veraendert erzeugte Bytes - die
    Zeitgeber-Ergaenzung, die Befehlszeile an pacman oder die Frage, ob
    ueberhaupt jemand benachrichtigt wird.

WARUM DIE EINSTELLUNG DER MASCHINE GEHOERT UND NICHT DEM BENUTZER
    user-settings.json liegt in einem Heimatverzeichnis, ist 0600 und
    gehoert einem Konto. Dieser Dienst laeuft als root, moeglicherweise
    bevor sich jemand angemeldet hat, und auf einer Maschine mit zwei
    Konten gaebe es zwei Antworten auf eine Frage, die ein Zeitgeber nur
    einmal beantworten kann. Die Datei liegt deshalb unter
    paths.machine_root(); zepos-settings leitet `update.*` dorthin um und
    sagt, wenn dafuer root fehlt - siehe cli.settings_command.

WAS PASSIERT, WENN SICH zepos-config AENDERT, WAEHREND DER SCHREIBTISCH
LAEUFT
    Das ist die Frage, an der eine Selbstaktualisierung einen Arbeitstag
    kosten kann, und die Antwort steht hier und in perform():

      * Ein UNBEAUFSICHTIGTER Lauf erzeugt NICHTS neu und startet NICHTS
        neu. Kein `zepos-generate`, kein `systemctl restart`, kein
        `pkill waybar`, kein `ags quit`. FORBIDDEN_PROGRAMS haelt das
        fest, und ein Test misst es an den Befehlen, die ein
        vollstaendiger Lauf wirklich abgesetzt hat. Der Grund ist
        gemessen worden, und zwar am 11.08.2026 an der Maschine des
        Entwicklers: ein Generatorlauf im Hintergrund beendet Waybar und
        AGS des Nutzers, mitten in seiner Sitzung, ohne dass er etwas
        angefasst hat.
      * Die laufende Sitzung behaelt darum ihre erzeugte Konfiguration in
        ~/.config. Ein ausgetauschtes /usr/share/zepos aendert an einem
        bereits laufenden Compositor nichts: der haelt seine geoeffneten
        Dateien, und die Vorlagen liest nur der Generator.
      * Damit die neue Fassung trotzdem irgendwann ankommt, hinterlaesst
        ein Lauf, der Pakete getauscht hat, eine Marke (REGENERATE_MARKER).
        src/bin/zepos-session sieht bei der naechsten Anmeldung nach, ob
        sie neuer ist als das, was dieser Benutzer zuletzt erzeugt hat,
        und erzeugt dann neu - vor dem Compositor, also an der einzigen
        Stelle, an der das keine laufende Sitzung trifft.
      * Die Benachrichtigung sagt genau das: es ist eingespielt, sichtbar
        wird es nach der naechsten Anmeldung.

UND WAS PASSIERT, WENN EIN MENSCH DEN LAUF SELBST ANSTOESST (19.08.2026)
    GEMELDET vom Nutzer: "bei einem update --apply wird auch alles
    generiert und neue angezeigt sodass alle update direkt aktiv sind".
    Er will nach einem Lauf, den er selbst gestartet hat, keinen zweiten
    Handgriff und keine Neuanmeldung.

    Der Absatz darueber sagt selbst, wo der Unterschied liegt: "Das ist
    richtig, wenn ein Mensch den Generator ruft, und falsch, wenn ein
    Zeitgeber es tut." Bis heute wurde dieser Unterschied nicht gemacht -
    BEIDE Faelle wurden behandelt wie der Zeitgeber. caller() macht ihn
    jetzt, und die Sperre bleibt genau da, wo sie war:

      Zeitgeber   kein Terminal, kein sudo, kein Sitzplatz -> Marke,
                  sonst nichts. Unveraendert.
      Mensch      Terminal UND ein benennbares Konto UND eine
                  angemeldete grafische Sitzung dieses Kontos -> der
                  Generator laeuft im Vordergrund, als dieses Konto, und
                  der Nutzer sieht ihn laufen.

    Die drei Bedingungen stehen mit UND und nicht mit ODER da, und die
    Begruendung dafuer ist die Kostenverteilung: eine falsch NICHT
    erkannte Sitzung kostet eine Neuanmeldung, eine falsch ERKANNTE
    reisst dem Nutzer die Leiste unter den Haenden weg - das ist der
    Fehler vom 11.08. Im Zweifel wird deshalb nicht neu erzeugt.

DIE SACKGASSE, DIE DAS UEBRIG LIESS (20.08.2026)
    GEMELDET vom Nutzer, zum dritten Mal: "aktualsiert sich das ui mit
    generate all immernoch nicht nach zepos update warum ?".

    Die Neuerzeugung hing bis heute an EINER Bedingung, und zwar an der
    falschen: `if outcome.changed`. Wer den Lauf machte, der wirklich
    Pakete tauschte, hatte damals vielleicht kein Terminal - dann blieb
    es bei der Marke, richtig so. Nur betrat jeder WEITERE Lauf den
    Block gar nicht mehr: `changed` ist falsch, wenn nichts einzuspielen
    ist, und die Marke, die daneben liegt, hat in dieser Datei niemand
    gelesen. Gemessen an drei Runden mit dem Nutzer:

      1. `sudo zepos-update` holt 0.1.3 -> Marke gesetzt, nichts erzeugt
      2. `sudo zepos-update` -> "nothing", Block uebersprungen
      3. wie 2., beliebig oft. Die Oberflaeche bleibt alt.

    Auch `--regenerate` half nicht: der Schalter wirkt ueber caller(),
    und caller() wurde INNERHALB dieses Blocks gefragt.

    Die Neuerzeugung haengt darum jetzt an "steht eine aus?" und nicht
    an "hat dieser Lauf etwas getan?" - siehe regeneration_pending(),
    das dafuer keine zweite Regel erfindet, sondern die von
    src/bin/zepos-session uebernimmt. --regenerate erzwingt ausserdem
    ohne jede Bedingung, und --check SAGT, dass etwas aussteht, samt dem
    Befehl, der es aufloest: die Sackgasse war drei Runden lang
    unsichtbar, weil kein Ausgang sie je erwaehnt hat.

WAS EIN FEHLSCHLAG TUN MUSS
    Reden. `SigLevel = Required` heisst, dass eine Datenbank oder ein
    Paket ohne gueltige Unterschrift abgelehnt wird; pacman endet dann
    mit einem Rueckgabewert ungleich 0. Ein Dienst, der das schluckt,
    verwandelt einen Angriff oder einen kaputten Schluessel in ein
    System, das eben "schon eine Weile keine Aktualisierung hatte". Ein
    Fehlschlag landet deshalb an vier Stellen: im Rueckgabewert, im
    Journal, in der Zustandsdatei - und als Benachrichtigung, sobald
    jemand angemeldet ist, auch dann, wenn `update.notify` sonst nur bei
    Aenderungen meldet. Nur "never" schweigt auf dem Schreibtisch, und
    zepos-doctor meldet es trotzdem.

    Nicht durchsucht wird pacmans Prosa. Ein installiertes ZepOS ist ein
    deutsches System (Spec 3), pacman ist uebersetzt, und ein
    `grep 'signature'` gegen die Ausgabe eines uebersetzten Programms
    ist eine Pruefung, die nur auf der Maschine des Entwicklers
    anschlaegt - iso/profile/airootfs/usr/local/bin/zepos-smoke-update
    hat genau das einmal gekostet. Gemessen wird der Rueckgabewert;
    berichtet werden die letzten Zeilen im Wortlaut.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

# Relativ zuerst, aus demselben Grund wie in settings.py: dieses Modul
# wird als `src.update` aus der Testsuite und als flaches `update` aus
# /usr/share/zepos geladen, und beide Wege muessen dieselbe paths.py
# sehen.
try:
    from .paths import machine_root, state_root
    from . import terminal
except ImportError:
    from paths import machine_root, state_root
    import terminal

Runner = Callable[..., "subprocess.CompletedProcess"]

SCHEMA_VERSION = 1
CONFIG_FILE = "update.json"
STATE_FILE = "update-state.json"

# Die Marke, die eine Anmeldung liest. Eine leere Datei; ihre
# Aenderungszeit IST die Aussage, und deshalb steht nichts darin, was mit
# ihr in Widerspruch geraten koennte.
REGENERATE_MARKER = "regenerate-required"

# Und das Gegenstueck: der Zeitstempel, den REGENERATE_SCRIPT im
# Heimatverzeichnis DES KONTOS hinterlaesst, wenn dort erzeugt worden
# ist. Der Name steht hier ein zweites Mal - src/bin/zepos-session
# schreibt ihn als GENERATED_STAMP -, weil ein Bash-Skript kein Python
# importieren kann; tests/src/test_update.py haelt beide gegeneinander.
#
# ZWEI DATEIEN UND NICHT EINE, UND DAS IST DER GANZE PUNKT
#     Die Marke gehoert der MASCHINE und damit jedem Konto auf ihr; der
#     Zeitstempel gehoert EINEM Konto. Erst der Vergleich beider
#     beantwortet die Frage, die eine Neuerzeugung ausloest: nicht "ist
#     eingespielt worden?", sondern "ist eingespielt worden, seit DIESES
#     Konto zuletzt erzeugt hat?".
GENERATED_STAMP = "generated-at"

# Die Einheit, die den Lauf ausloest, und die Ergaenzung, mit der die
# Einstellungen sie umstellen.
#
# WARUM EINE ERGAENZUNG UND NICHT DIE UNIT SELBST
#     /usr/lib/systemd/system/zepos-update.timer gehoert dem Paket.
#     Wer sie beschreibt, verliert die Aenderung beim naechsten
#     `pacman -Syu` - und pacman legt daneben eine .pacnew, die niemand
#     liest. Eine Ergaenzung unter /etc gehoert dem Administrator, und
#     systemd liest sie nach der Unit.
TIMER_UNIT = "zepos-update.timer"
SERVICE_UNIT = "zepos-update.service"
DROPIN_DIRECTORY = Path("systemd/system") / f"{TIMER_UNIT}.d"
DROPIN_FILE = "10-zepos.conf"

# Wohin die Ergaenzung geht. Unterhalb von /etc, aber NICHT unterhalb von
# machine_root(): /etc/systemd/system ist systemds Verzeichnis und keins
# von ZepOS. Der Pfad ist umlenkbar, damit ein Test ihn in ein
# temporaeres Verzeichnis legen kann.
SYSTEMD_ETC = Path("/etc")
SYSTEMD_ETC_ENV = "ZEPOS_SYSTEMD_ETC"

# Wo pacman seine Repository-Datenbanken ablegt, und der Weg, auf dem ein
# Test einen eigenen Bestand vorgibt.
SYNC_DB = Path("/var/lib/pacman/sync")
SYNC_DB_ENV = "ZEPOS_PACMAN_SYNC"

SCOPE_ZEPOS = "zepos"
SCOPE_ALL = "all"
SCOPES = (SCOPE_ZEPOS, SCOPE_ALL)

NOTIFY_CHANGES = "changes"
NOTIFY_FAILURES = "failures"
NOTIFY_NEVER = "never"
NOTIFY_MODES = (NOTIFY_CHANGES, NOTIFY_FAILURES, NOTIFY_NEVER)

# Der Name, unter dem pacman das Repository kennt. Dieselbe Zeichenkette
# wie installer/core/source.py REPO_NAME; sie steht hier ein zweites Mal,
# weil das installierte System den Installer nicht mitbringt (Spec 4.2) -
# eine Umbenennung faellt in tests/src/test_update.py auf, das beide
# Stellen vergleicht.
REPOSITORY = "zepos"

# Was ein unbeaufsichtigter Lauf niemals tun darf, mit dem Programmnamen
# als Schluessel. Die Liste ist keine Dekoration: sie wird gegen die
# Befehle geprueft, die ein vollstaendiger Lauf wirklich abgesetzt hat.
#
# generate_config.sh beendet an seinem Ende `waybar` und `ags`, damit die
# neue Konfiguration greift. Das ist richtig, wenn ein Mensch den
# Generator ruft, und falsch, wenn ein Zeitgeber es tut: der Nutzer sieht
# seine Leiste verschwinden, ohne etwas getan zu haben.
#
# SEIT DEM 19.08.2026 IST DAS EINE GRENZE UND KEIN VERBOT MEHR
#     perform() und announce() - alles, was ein Zeitgeber ausfuehrt -
#     setzen weiterhin keinen einzigen dieser Befehle ab, und
#     test_an_unattended_run_never_regenerates_and_never_restarts_anything
#     misst das an den wirklich abgesetzten Argumenten. Neu ist nur, dass
#     regenerate() daneben steht: dieselben Programme, aber ausschliesslich
#     hinter caller().human, also hinter einem Terminal, einem sudo und
#     einer angemeldeten Sitzung. Diese Liste wird deshalb nie kuerzer -
#     sie beschreibt den Zeitgeber, und der darf nach wie vor nichts davon.
FORBIDDEN_PROGRAMS = (
    "zepos-generate", "generate_config.sh",
    "pkill", "killall", "kill",
    "waybar", "ags", "hyprctl", "Hyprland",
    "reboot", "shutdown", "systemd-run-reboot",
)

# Argumente, die aus einer gezielten Aktualisierung eine vollstaendige
# machen. `-u` gehoert zu `-Syu`; wer sie im Bereich "zepos" faende,
# haette eine Maschine, die sich nachts das ganze Rolling Release holt.
FULL_UPGRADE_FLAGS = ("-u", "--sysupgrade")

# Ein systemd-Zeitspannenwert, so eng gefasst, wie systemd ihn liest, und
# so weit, wie ein Mensch ihn schreibt: "15min", "1d", "90s", "0".
#
# WARUM DAS GEPRUEFT WIRD
#     systemd weist eine Unit mit einer unlesbaren Zeitspanne ab
#     ("Failed to parse timer value"). Die Unit ist dann nicht kaputt -
#     sie ist WEG, und ein Zeitgeber, den es nicht gibt, feuert nie und
#     beschwert sich nie. Ein Tippfehler in einer Einstellung wuerde eine
#     Maschine also still von der Aktualisierung abschneiden. Genau die
#     Art Fehler, gegen die es zepos-doctor gibt.
TIMESPAN = re.compile(
    r"^\d+(us|ms|s|sec|secs|second|seconds|m|min|mins|minute|minutes"
    r"|h|hr|hour|hours|d|day|days|w|week|weeks)?$"
)

# Die Kalenderworte, die systemd selbst definiert (systemd.time(7),
# "Calendar Events"). `update.schedule.interval` nimmt entweder eins
# davon oder eine Zeitspanne, und das ist der Unterschied zwischen zwei
# Arten, "taeglich" zu meinen:
#
#   daily   um Mitternacht, gestreut, und NACHGEHOLT, wenn die Maschine
#           da gerade aus war. Das ist der Vorgabefall.
#   24h     24 Stunden nach dem letzten Lauf, solange die Maschine
#           laeuft. Ein Rechner, der jeden Abend ausgeht, kommt so nie an
#           die 24 Stunden heran - deshalb ist das nicht die Vorgabe.
#
# Eine beliebige Kalenderangabe ("Mon *-*-* 04:00:00") wird NICHT
# angenommen. Nur systemd selbst kann sie pruefen (systemd-analyze
# calendar), und eine, die es ablehnt, macht die Unit ungueltig: der
# Zeitgeber ist dann nicht falsch eingestellt, sondern weg. Lieber ein
# Wort weniger als eine Maschine, die still nichts mehr holt.
CALENDAR_WORDS = ("hourly", "daily", "weekly", "monthly", "quarterly",
                  "semiannually", "yearly")


def _timespan(value: Any) -> str | None:
    """Der Wert als systemd-Zeitspanne, oder None.

    EINE ZAHL IST AUCH EINE ZEITSPANNE, UND DAS IST GEMESSEN
        `zepos-settings set update.schedule.randomized_delay 0` liest
        seinen Wert wie jede andere Einstellung: was als JSON durchgeht,
        IST JSON - und "0" geht als JSON durch, als Zahl 0. Eine Pruefung,
        die nur Zeichenketten annimmt, lehnt damit genau die Schreibweise
        ab, die ein Mensch tippt, und verlangt '"0"' mit
        Anfuehrungszeichen. cli.py nennt so etwas eine Falle, die niemand
        erwartet, und hat recht damit.

        systemd liest eine blanke Zahl als Sekunden (systemd.time(7)),
        also ist die Zahl nicht nur bequem, sondern richtig. `True` wird
        trotzdem abgelehnt - bool ist in Python ein int, und
        `randomized_delay: true` waere eine Sekunde Streuung, die niemand
        gemeint hat.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value) if value >= 0 else None
    if isinstance(value, str) and TIMESPAN.match(value):
        return value
    return None


class UnusableConfig(ValueError):
    """Die Aktualisierungseinstellungen sind da und nicht benutzbar.

    Wie settings.UnusableSettings, und aus demselben Grund ein
    ValueError: eine Datei, die nicht da ist, ist der Normalfall einer
    frischen Installation und beantwortet sich aus den Vorgaben. Eine
    Datei, die da ist und Unsinn enthaelt, darf NICHT stillschweigend
    durch die Vorgaben ersetzt werden - sonst aktualisiert sich eine
    Maschine, auf der jemand `enabled: false` schreiben wollte und sich
    vertippt hat, weiter, als haette er nichts gesagt.
    """


@dataclass(frozen=True)
class Change:
    """Ein Paket, das sich bewegt: Name, Fassung vorher, Fassung nachher."""

    name: str
    old: str
    new: str

    def __str__(self) -> str:
        return f"{self.name} {self.old} -> {self.new}"


@dataclass(frozen=True)
class Session:
    """Eine angemeldete Sitzung an einem Sitzplatz, mit ihrer uid."""

    uid: int
    user: str
    seat: str


@dataclass(frozen=True)
class Invocation:
    """Wer diesen Lauf angestossen hat - ein Mensch oder der Zeitgeber.

    `reason` ist kein Protokolltext, sondern die Zeile, die main() dem
    Nutzer druckt, wenn NICHT neu erzeugt wird. Ein Programm, das eine
    Entscheidung trifft und sie fuer sich behaelt, sieht fuer den
    Nutzer aus wie ein Programm, das nichts getan hat.
    """

    human: bool
    uid: int | None
    user: str
    elevated: bool
    reason: str


@dataclass(frozen=True)
class Notification:
    summary: str
    body: str
    urgent: bool = False


@dataclass(frozen=True)
class Outcome:
    """Was ein Lauf getan hat, in der Form, in der er es hinterlaesst."""

    result: str
    upgraded: tuple[Change, ...] = ()
    base_available: tuple[Change, ...] = ()
    # Was der Lauf ENTFERNT hat, weil ein Paket des Repositorys es
    # ersetzt. Es steht getrennt von `upgraded`, weil es keine neue
    # Fassung von etwas ist, sondern ein Name, den es danach nicht mehr
    # gibt - und weil ein Lauf, der ein Paket still entfernt, genau die
    # Art Stille ist, die dieses Projekt nicht duldet.
    replaced: tuple[str, ...] = ()
    returncode: int = 0
    message: str = ""
    sessions: tuple[Session, ...] = ()
    started: str = ""
    finished: str = ""

    # Die Ausgaenge. "nothing" ist ausdruecklich kein Fehler: eine
    # Maschine, die auf dem Stand ist, hat die Frage beantwortet.
    # "pending" kann nur aus --check kommen und wird nie abgelegt - es
    # ist die Antwort auf "was WUERDE passieren".
    OK = "ok"
    NOTHING = "nothing"
    PENDING = "pending"
    DISABLED = "disabled"
    FAILED = "failed"

    @property
    def failed(self) -> bool:
        return self.result == self.FAILED

    @property
    def changed(self) -> bool:
        return bool(self.upgraded)


# --------------------------------------------------------------------
# Die Einstellungen
# --------------------------------------------------------------------

def defaults() -> dict[str, Any]:
    """Was eine Maschine glaubt, an der niemand etwas eingestellt hat.

    Die Zahlen sind die Empfehlung aus docs/specs/
    2026-08-11-weg-zum-eigenen-os.md, in systemds eigener Schreibweise,
    damit die Ergaenzung unten kein Umrechnen braucht - eine Umrechnung
    waere die Stelle, an der aus "1h" spaeter einmal 3600 Sekunden
    wuerden und aus "1min" 60 Stunden.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        # Der eine Schalter. Er steht vor allen anderen, weil er der
        # einzige ist, der auch den Zeitgeber selbst abschaltet: false
        # heisst, dass systemd die Einheit gar nicht erst haelt, und
        # nicht, dass sie taeglich aufwacht, um nichts zu tun.
        "enabled": True,
        "scope": SCOPE_ZEPOS,
        # Melden, was die Arch-Basis anbietet, ohne es anzufassen. Wer
        # das nicht sehen will, setzt es auf false; die Zaehlung
        # unterbleibt dann samt dem `pacman -Qu`, das sie kostet.
        "report_base": True,
        "notify": NOTIFY_CHANGES,
        "schedule": {
            # Nach dem Start, nicht beim Start. Die erste Viertelstunde
            # gehoert dem Nutzer.
            "on_boot": "15min",
            # Ein Kalenderwort und keine Zeitspanne, damit "persistent"
            # weiter unten ueberhaupt etwas bedeuten kann - siehe
            # CALENDAR_WORDS.
            "interval": "daily",
            # Bis zu einer Stunde spaeter, gleichverteilt. Siehe den Kopf
            # dieser Datei.
            "randomized_delay": "1h",
            # Nachholen, was verpasst wurde. Ein Rechner, der jeden Abend
            # ausgeschaltet wird, holt sonst nie etwas: OnUnitActiveSec
            # zaehlt nur, waehrend die Maschine laeuft.
            "persistent": True,
        },
    }


def config_path() -> Path:
    return machine_root() / CONFIG_FILE


def state_path() -> Path:
    return state_root() / STATE_FILE


def marker_path() -> Path:
    return state_root() / REGENERATE_MARKER


def systemd_etc() -> Path:
    override = os.environ.get(SYSTEMD_ETC_ENV)
    return Path(override) if override else SYSTEMD_ETC


def sync_db() -> Path:
    """Wo pacman die Datenbanken der Repositorys liegen hat."""
    override = os.environ.get(SYNC_DB_ENV)
    return Path(override) if override else SYNC_DB


def dropin_path() -> Path:
    return systemd_etc() / DROPIN_DIRECTORY / DROPIN_FILE


def load(path: Path | None = None) -> dict[str, Any]:
    """Die Einstellungen, mit den Vorgaben aufgefuellt und geprueft.

    Aufgefuellt, damit eine Datei aus einer aelteren Fassung von ZepOS
    keinen Schluessel vermissen laesst, den dieses Modul liest - und
    geprueft, damit ein Wert, den systemd oder pacman nicht versteht,
    hier auffaellt und nicht als stiller Ausfall des Zeitgebers.
    """
    target = path if path is not None else config_path()
    if not target.is_file():
        return defaults()

    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UnusableConfig(f"{target} ist kein JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise UnusableConfig(f"{target} ist kein JSON-Objekt")

    version = data.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise UnusableConfig(
            f"{target}: schema_version {version}, erwartet {SCHEMA_VERSION}")

    merged = defaults()
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return validate(merged)


def validate(config: dict[str, Any]) -> dict[str, Any]:
    """Jeder Wert, der spaeter in eine Unit oder an pacman geht.

    Namentlich, mit dem Schluessel im Fehlertext: wer eine Einstellung
    von Hand setzt, hat den Namen vor Augen und nicht die Zeilennummer
    dieses Moduls.
    """
    for key in ("enabled", "report_base"):
        if not isinstance(config.get(key), bool):
            raise UnusableConfig(
                f"update.{key} muss true oder false sein, nicht "
                f"{json.dumps(config.get(key))}")

    if config.get("scope") not in SCOPES:
        raise UnusableConfig(
            f"update.scope muss eins von {', '.join(SCOPES)} sein, nicht "
            f"{json.dumps(config.get('scope'))}")

    if config.get("notify") not in NOTIFY_MODES:
        raise UnusableConfig(
            f"update.notify muss eins von {', '.join(NOTIFY_MODES)} sein, "
            f"nicht {json.dumps(config.get('notify'))}")

    schedule = config.get("schedule")
    if not isinstance(schedule, dict):
        raise UnusableConfig("update.schedule muss ein Objekt sein")
    if not isinstance(schedule.get("persistent"), bool):
        raise UnusableConfig(
            "update.schedule.persistent muss true oder false sein, nicht "
            f"{json.dumps(schedule.get('persistent'))}")
    for key in ("on_boot", "randomized_delay"):
        if _timespan(schedule.get(key)) is None:
            raise UnusableConfig(
                f"update.schedule.{key} muss eine systemd-Zeitspanne sein "
                f"(15min, 1d, 90s, 0), nicht "
                f"{json.dumps(schedule.get(key))}")

    interval = schedule.get("interval")
    if interval not in CALENDAR_WORDS and _timespan(interval) is None:
        raise UnusableConfig(
            f"update.schedule.interval muss eins von "
            f"{', '.join(CALENDAR_WORDS)} oder eine Zeitspanne (6h, 2d) "
            f"sein, nicht {json.dumps(interval)}")
    return config


def save(config: dict[str, Any], path: Path | None = None) -> Path:
    """Geprueft, atomar und 0644 geschrieben.

    0644 und nicht 0600 wie user-settings.json: hier steht kein
    Geheimnis, und `zepos-settings get update.enabled` soll jeder lesen
    koennen, ohne root zu sein - sonst kann ein Nutzer nicht einmal
    nachsehen, ob seine Maschine sich aktualisiert.

    Atomar aus demselben Grund wie settings.save(): der Dienst kann die
    Datei genau in dem Moment lesen, in dem sie geschrieben wird, und ein
    halb geschriebenes JSON waere fuer ihn eine unbenutzbare Einstellung.
    """
    validate(config)
    target = path if path is not None else config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".new")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(config, indent=2) + "\n")
        os.chmod(temporary, 0o644)
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return target


def set_value(key: str, raw: str, path: Path | None = None) -> dict[str, Any]:
    """Einen gepunkteten Schluessel unterhalb von `update.` setzen.

    Dieselbe Lesart wie cli._set: was als JSON durchgeht, ist JSON
    (false, 3, "1h" mit Anfuehrungszeichen), alles andere ist Text. Ein
    unbekannter Schluessel wird abgelehnt statt angelegt - eine
    Einstellung, die niemand liest, ist die leiseste Art, eine Maschine
    nicht zu aktualisieren.
    """
    config = load(path)
    parts = key.split(".")
    section: Any = config
    for part in parts[:-1]:
        if not isinstance(section, dict) or not isinstance(section.get(part), dict):
            raise UnusableConfig(f"keine solche Einstellung: update.{key}")
        section = section[part]
    if not isinstance(section, dict) or parts[-1] not in section:
        raise UnusableConfig(f"keine solche Einstellung: update.{key}")

    try:
        value: Any = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    section[parts[-1]] = value

    validate(config)
    save(config, path)
    return config


def known_keys() -> list[str]:
    """Jeder gepunktete Name, den set_value annimmt - fuer die Hilfe."""
    names: list[str] = []
    for key, value in defaults().items():
        if key == "schema_version":
            continue
        if isinstance(value, dict):
            names += [f"{key}.{inner}" for inner in value]
        else:
            names.append(key)
    return sorted(names)


# --------------------------------------------------------------------
# Der Zeitgeber
# --------------------------------------------------------------------

# Die drei Schluessel im Abschnitt [Timer], die LISTEN sind. Eine zweite
# Zuweisung legt bei ihnen einen zweiten Zeitpunkt an, statt den ersten
# zu ersetzen (systemd.timer(5)) - deshalb muss eine Ergaenzung sie erst
# leeren. Ohne das ergaebe `interval: 6h` einen Zeitgeber, der um
# Mitternacht UND alle sechs Stunden feuert, und die Einstellung saehe
# aus, als haette sie gewirkt.
TIMER_LISTS = ("OnBootSec", "OnCalendar", "OnUnitActiveSec")


def timer_settings(config: dict[str, Any]) -> list[tuple[str, str]]:
    """Der Abschnitt [Timer] als Paare, in der Reihenfolge der Datei.

    Die Fallunterscheidung ist die zwischen den zwei Bedeutungen von
    "taeglich", die CALENDAR_WORDS beschreibt. Persistent= steht nur im
    Kalenderfall in der Datei, und das ist kein Vergessen: systemd wertet
    es ausschliesslich fuer OnCalendar aus. Eine Zeile, die nichts tut,
    waere schlimmer als keine - jemand liest sie und glaubt, verpasste
    Laeufe wuerden nachgeholt.
    """
    schedule = config["schedule"]
    values = [("OnBootSec", _timespan(schedule["on_boot"]))]
    if schedule["interval"] in CALENDAR_WORDS:
        values.append(("OnCalendar", schedule["interval"]))
        values.append(("Persistent",
                       "true" if schedule["persistent"] else "false"))
    else:
        values.append(("OnUnitActiveSec", _timespan(schedule["interval"])))
    values.append(("RandomizedDelaySec",
                   _timespan(schedule["randomized_delay"])))
    return values


def _persistent_note(config: dict[str, Any]) -> list[str]:
    if config["schedule"]["interval"] in CALENDAR_WORDS:
        return []
    return ["# update.schedule.persistent steht hier nicht: systemd wertet",
            "# Persistent= nur zusammen mit OnCalendar= aus, und interval",
            "# ist eine Zeitspanne. Verpasstes holt hier OnBootSec nach."]


def timer_unit(config: dict[str, Any]) -> str:
    """Die ausgelieferte Einheit, aus derselben Tabelle wie die Ergaenzung.

    src/system/zepos-update.timer IST das Ergebnis dieser Funktion auf
    defaults(), und ein Test vergleicht die zwei Byte fuer Byte. Damit
    kann die ausgelieferte Voreinstellung nicht von der abweichen, die
    dieses Modul fuer die Voreinstellung haelt - ein Auseinanderlaufen,
    das sonst niemandem auffiele, weil beide Seiten fuer sich richtig
    aussehen.
    """
    lines = [
        "# Erzeugt aus src/update.py timer_unit(defaults()).",
        "# Nicht von Hand aendern: `zepos-settings set update.schedule.*`",
        "# schreibt eine Ergaenzung unter /etc, die diese Werte ueberstimmt,",
        "# und tests/src/test_update.py vergleicht diese Datei mit dem, was",
        "# das Modul aus seinen Vorgaben baut.",
        "[Unit]",
        "Description=ZepOS-Aktualisierung (taeglich, verzoegert)",
        # Auf die Datei, die die Entscheidung traegt, und nicht auf eine
        # Handbuchseite, die es nicht gibt: `systemctl show` zeigt diese
        # Zeile, und ein Verweis ins Leere ist schlimmer als keiner.
        "Documentation=file:///usr/share/zepos/update.py",
        "",
        "[Timer]",
        f"Unit={SERVICE_UNIT}",
    ]
    lines += _persistent_note(config)
    lines += [f"{name}={value}" for name, value in timer_settings(config)]
    lines += [
        "",
        "[Install]",
        "WantedBy=timers.target",
        "",
    ]
    return "\n".join(lines)


def timer_dropin(config: dict[str, Any]) -> str:
    """Die Ergaenzung, die eine geaenderte Einstellung wirksam macht.

    WARUM ALLE DREI LISTEN GELEERT WERDEN, AUCH DIE UNBENUTZTEN
        OnBootSec, OnCalendar und OnUnitActiveSec sind LISTEN
        (systemd.timer(5)): eine zweite Zuweisung legt einen zweiten
        Zeitpunkt an, sie ersetzt den ersten nicht. Eine Ergaenzung mit
        nur `OnBootSec=2min` ergaebe also einen Zeitgeber, der nach 2
        Minuten UND nach 15 Minuten feuert.

        Und es reicht nicht, die zu leeren, die diese Einstellung
        besetzt. Die ausgelieferte Unit traegt OnCalendar=daily; wer auf
        `interval: 6h` umstellt, bekaeme sonst OnUnitActiveSec=6h NEBEN
        dem taeglichen Kalender - eine Umstellung, die nichts abstellt.
        Deshalb werden erst alle drei geleert und dann die gesetzt, die
        gelten sollen.

        RandomizedDelaySec und Persistent sind einfache Werte, bei denen
        die letzte Zuweisung gilt. Sie brauchen die Ruecksetzung nicht.
    """
    lines = [
        "# Erzeugt von zepos-update --apply-schedule aus den Einstellungen",
        f"# unter {config_path()}. Nicht von Hand aendern - der naechste",
        "# `zepos-settings set update.schedule.*` schreibt sie neu.",
        "[Timer]",
    ]
    lines += _persistent_note(config)
    lines += [f"{name}=" for name in TIMER_LISTS]
    lines += [f"{name}={value}" for name, value in timer_settings(config)]
    lines.append("")
    return "\n".join(lines)


def systemd_actions(config: dict[str, Any]) -> list[list[str]]:
    """Was systemd gesagt werden muss, damit es zur Einstellung passt.

    Als Liste von Argumentlisten statt als Aufrufe, damit die
    Entscheidung ohne systemd geprueft werden kann - und damit sie im
    Testbericht als das erscheint, was sie ist: drei Befehle, nicht drei
    Behauptungen.

    Einschalten UND starten, in zwei Befehlen statt als `enable --now`.
    Der Grund ist das pacstrap-Chroot, in dem der ALPM-Haken laeuft: dort
    gibt es keinen laufenden systemd, `start` scheitert - und bei
    `enable --now` waere danach nicht mehr zu unterscheiden, ob auch das
    Einschalten gescheitert ist. Getrennt scheitert nur die Haelfte, die
    dort ohnehin nicht gehen kann, und der Symlink, auf den es ankommt,
    liegt.

    Umgekehrt wird beim Abschalten auch gestoppt, sonst feuerte der
    abgeschaltete Zeitgeber noch bis zum naechsten Herunterfahren weiter.
    """
    actions = [["systemctl", "daemon-reload"]]
    if config["enabled"]:
        actions.append(["systemctl", "enable", TIMER_UNIT])
        actions.append(["systemctl", "start", TIMER_UNIT])
    else:
        actions.append(["systemctl", "disable", TIMER_UNIT])
        actions.append(["systemctl", "stop", TIMER_UNIT])
    return actions


def apply(config: dict[str, Any], *, runner: Runner | None = None,
          write: bool = True) -> list[list[str]]:
    """Die Ergaenzung schreiben und systemd davon erzaehlen.

    Gerufen von genau zwei Stellen, und beide sind der Grund, dass eine
    Einstellung ueberhaupt etwas bewirkt:

      * `zepos-settings set update.*`, unmittelbar nach dem Schreiben;
      * dem ALPM-Haken, wenn das Paket den Zeitgeber neu ablegt. Ein
        Paket kann unter Arch keinen Dienst einschalten (siehe
        installer/core/translate.py), ein Haken kann es - und eine
        Maschine, die den Aktualisierer per Paketaktualisierung bekommt,
        hat sonst alles ausser dem Symlink, der ihn ausloest.

    Fehler von systemctl beenden das Programm NICHT. Im pacstrap-Chroot
    gibt es keinen laufenden systemd; `enable` legt dort trotzdem den
    Symlink an, `--now` scheitert, und eine Installation abzubrechen,
    weil ein Zeitgeber nicht sofort startet, waere die falsche Reaktion
    auf einen Zustand, der sich beim naechsten Start von selbst aufloest.
    """
    runner = runner or subprocess.run
    target = dropin_path()
    if write:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(timer_dropin(config), encoding="utf-8")

    performed: list[list[str]] = []
    for argv in systemd_actions(config):
        performed.append(argv)
        try:
            runner(argv, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            # Kein systemd erreichbar. Die Ergaenzung liegt trotzdem, und
            # der naechste Start liest sie.
            continue
    return performed


# --------------------------------------------------------------------
# Was pacman sagt
# --------------------------------------------------------------------

def _run(runner: Runner, argv: Sequence[str], *, timeout: float = 3600,
         note: str = "") -> subprocess.CompletedProcess:
    """Ein Aufruf, dessen Ausgabe eingesammelt wird - und ein Lebenszeichen.

    WARUM DIE AUSGABE WEITER EINGESAMMELT WIRD (20.08.2026)
        Sie ist das Einzige, was nach einem Fehlschlag sagt, WARUM: _tail()
        legt sie in die Zustandsdatei, `zepos-update --status` holt sie
        wieder, und die Leiste zeigt sie an. Ein pacman, der direkt auf
        das Terminal schreibt, haette davon nichts uebrig.

        Der Preis war, dass ein Mensch waehrenddessen auf nichts sieht -
        `pacman -Sy` und ein Einspielen dauern. `note` ist die Antwort
        darauf: eine Zeile, die sagt, was gerade laeuft, und die sich
        bewegt, solange es laeuft. An einem Lauf ohne Terminal - dem
        Zeitgeber, dem ALPM-Haken, jeder Umleitung in eine Datei - zeichnet
        terminal.live() dafuer NICHTS, nicht ein Steuerzeichen.
    """
    if not note:
        # Die kurzen Fragen - loginctl, `pacman -Qu`, `pacman -Slq` -
        # bekommen keine. Ein Bild, das nach 40 ms wieder weg ist, ist
        # kein Lebenszeichen, sondern ein Zucken.
        return runner(list(argv), capture_output=True, text=True,
                      timeout=timeout)
    with terminal.live(note):
        return runner(list(argv), capture_output=True, text=True,
                      timeout=timeout)


def refresh_command() -> list[str]:
    """Die Datenbank holen.

    `-Sy` und nicht `-Syy`: die zweite Form laedt jede Datenbank neu,
    auch die unveraenderten der Arch-Basis, und das ist auf einer
    Verbindung, die jemand bezahlt, taeglich unhoeflich.

    Dass ein `-Sy` ohne folgendes `-u` die Maschine in den Zustand
    bringt, vor dem Arch warnt (teilweise Aktualisierung), ist der Preis
    der Entscheidung "nur zepos-*". Er wird hier bewusst gezahlt und
    nicht verschwiegen: das Gegenstueck waere ein unbeaufsichtigtes
    `-Syu`, und was das kostet, steht im Kopf dieser Datei. Die
    Aufstellung der Basis, die jeder Lauf mitfuehrt, ist genau dafuer da,
    dass der Nutzer den vollen Schritt bewusst tun kann.
    """
    return ["pacman", "-Sy", "--noconfirm"]


def upgradable_command() -> list[str]:
    return ["pacman", "-Qu"]


def repository_command() -> list[str]:
    """Welche Pakete das [zepos]-Repository ueberhaupt anbietet.

    Gefragt statt aus dem Namen geraten. `zepos-*` waere die naechst-
    liegende Regel und sie ist falsch: aylurs-gtk-shell, libastal-4,
    libastal-io, libastal-notifd und wlogout kommen aus demselben
    Repository und heissen nicht so. Ein Praefixfilter haette genau die
    Pakete stehen gelassen, die den Schreibtisch ausmachen.
    """
    return ["pacman", "-Slq", REPOSITORY]


def installed_command() -> list[str]:
    """Was installiert IST, in Namen und ohne Prosa.

    `-Qq` und nicht `-Q`: die kurze Form gibt eine Spalte Namen, die
    lange haengt die Fassung an. Gebraucht wird hier nur der Name, und
    eine Spalte weniger ist eine Spalte, die nicht falsch geteilt werden
    kann.
    """
    return ["pacman", "-Qq"]


def removal_command(names: Sequence[str]) -> list[str]:
    """Ein ersetztes Paket abraeumen, bevor sein Nachfolger einzieht.

    `-dd`, und das ist die einzige Stelle dieses Projekts, an der eine
    Abhaengigkeitspruefung uebergangen wird. Der Grund ist gemessen: das
    installierte zepos-apps 0.1.13 fuehrt zepos-claude-code in seinen
    `depends`, also verweigert ein blankes `-R` die Entfernung ("wird
    benoetigt von"). `-Rc` waere die Kaskade und nahm zepos-apps mit -
    also den halben Schreibtisch. Was das Paket bereitstellte, stellt
    der Befehl danach wieder her: zepos-config 0.1.14 legt
    /usr/bin/zepos-claude-code selbst ab.

    Sortiert, damit derselbe Satz Namen denselben Befehl ergibt - ein
    Test, der eine Reihenfolge aus einer Menge prueft, ist ein Test, der
    manchmal faellt.
    """
    return ["pacman", "-Rdd", "--noconfirm", *sorted(names)]


def replaced_by_repository(db: Path | None = None) -> set[str]:
    """Welche Namen die Pakete des [zepos]-Repositorys ERSETZEN.

    WARUM DIESE FUNKTION UEBERHAUPT EXISTIERT, UND ZWAR WOERTLICH
        PKGBUILD(5) ueber das Feld `replaces`:

            "Sysupgrade is currently the only pacman operation that
            utilizes this field. A normal sync or upgrade will not use
            its value."

        Der Bereich "zepos" ist kein Sysupgrade - upgrade_command()
        setzt dort `pacman -S --needed --noconfirm <namen>` ab, und zwar
        mit Absicht (der Grund steht dort). Damit wird `replaces` NICHT
        gelesen. Was gelesen wird, ist `conflicts` desselben Pakets, und
        ein Konflikt mit `--noconfirm` bricht den GANZEN Vorgang ab:
        pacman entfernt kein Paket, ohne gefragt zu haben.

        GEMESSEN am 03.09.2026 auf der Maschine des Nutzers: nach dem
        Fall von zepos-claude-code am 01.09.2026 traegt zepos-config
        0.1.14 beides, `replaces` und `conflicts`, auf denselben Namen.
        Ein Rechner mit dem alten Paket bekam damit KEINE Aktualisierung
        mehr - nicht die von zepos-config, sondern gar keine.

    WARUM AUS DER DATENBANK UND NICHT AUS `pacman -Sii`
        Weil `-Sii` seine Felder uebersetzt ausgibt ("Ersetzt :"), und
        die Regel dieser Datei lautet seit ihrer ersten Fassung: pacmans
        Prosa wird nicht durchsucht (siehe den Kopf). %REPLACES% in der
        Datenbank ist dasselbe Feld, nur in dem Format, das repo-add
        geschrieben hat - und das ist dieselbe Datei, die packaging/
        build.sh hier erzeugt.

    Ein fehlender oder unlesbarer Datenbestand gibt eine leere Menge und
    keinen Fehler: dann faellt schon `pacman -Sy` vorher, und dieser Lauf
    hat kein zweites Urteil darueber zu faellen.
    """
    pfad = (db if db is not None else sync_db()) / f"{REPOSITORY}.db"
    namen: set[str] = set()
    try:
        with tarfile.open(pfad) as archiv:
            for eintrag in archiv:
                if not eintrag.isfile() or not eintrag.name.endswith("/desc"):
                    continue
                inhalt = archiv.extractfile(eintrag)
                if inhalt is None:
                    continue
                text = inhalt.read().decode("utf-8", errors="replace")
                namen |= _section(text, "%REPLACES%")
    except (OSError, tarfile.TarError):
        return set()
    return namen


def _section(text: str, name: str) -> set[str]:
    """Ein Abschnitt einer desc-Datei: Kopfzeile, dann Zeilen bis zur Leerzeile."""
    werte: set[str] = set()
    innen = False
    for zeile in text.splitlines():
        if zeile.startswith("%") and zeile.endswith("%"):
            innen = zeile == name
            continue
        if not innen:
            continue
        if not zeile.strip():
            innen = False
            continue
        # Ein versioniertes replaces (`name<1.0`) nennt trotzdem einen
        # Namen, und der ist alles, was hier gebraucht wird.
        werte.add(re.split(r"[<>=]", zeile.strip(), maxsplit=1)[0])
    return werte


def upgrade_command(config: dict[str, Any], names: Sequence[str]) -> list[str]:
    """Der eine Befehl, der etwas veraendert.

    Im Bereich "zepos" nennt er jedes Paket beim Namen; `-u` kommt darin
    nicht vor, und ein Test misst das. `--needed` laesst aus, was schon
    aktuell ist - zwischen der Aufstellung und diesem Aufruf koennen
    Minuten liegen, wenn das Netz langsam ist.
    """
    if config["scope"] == SCOPE_ALL:
        return ["pacman", "-Syu", "--noconfirm"]
    return ["pacman", "-S", "--needed", "--noconfirm", *names]


def parse_upgradable(text: str) -> list[Change]:
    """`pacman -Qu` in Zeilen der Form `name alt -> neu`.

    Zeilen, die anders aussehen, werden uebergangen statt geraten:
    `pacman -Qu` haengt bei ignorierten Paketen ein "[ignoriert]" an, und
    das ist uebersetzt.
    """
    changes = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[2] == "->":
            changes.append(Change(parts[0], parts[1], parts[3]))
    return changes


def parse_repository(text: str) -> set[str]:
    return {line.strip() for line in text.splitlines() if line.strip()}


def split(changes: Iterable[Change], members: set[str]
          ) -> tuple[list[Change], list[Change]]:
    """Was uns gehoert, und was der Arch-Basis gehoert."""
    ours, base = [], []
    for change in changes:
        (ours if change.name in members else base).append(change)
    return ours, base


# --------------------------------------------------------------------
# Wer angemeldet ist
# --------------------------------------------------------------------

def sessions_command() -> list[str]:
    return ["loginctl", "list-sessions", "--output=json"]


def parse_sessions(text: str) -> list[Session]:
    """Angemeldete Sitzungen an einem Sitzplatz.

    Ohne Sitzplatz ist es keine Sitzung an diesem Bildschirm - eine
    SSH-Anmeldung hat keinen, und eine Benachrichtigung an sie geht ins
    Leere. Die Felder heissen bei systemd 254 `uid`, `user` und `seat`;
    fehlt eins, wird die Zeile uebergangen statt mit einer Vorgabe
    aufgefuellt, denn eine erfundene uid ist ein Befehl an das falsche
    Konto.
    """
    try:
        entries = json.loads(text or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(entries, list):
        return []

    found = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        uid, user, seat = entry.get("uid"), entry.get("user"), entry.get("seat")
        if not isinstance(uid, int) or not user or not seat:
            continue
        found.append(Session(uid, str(user), str(seat)))
    return found


def graphical_sessions(*, runner: Runner | None = None) -> list[Session]:
    runner = runner or subprocess.run
    try:
        result = _run(runner, sessions_command(), timeout=10)
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    return parse_sessions(result.stdout or "")


# --------------------------------------------------------------------
# Mensch oder Zeitgeber - und was der Mensch danach bekommt
# --------------------------------------------------------------------

# Die beiden Umgebungsvariablen, an denen ein root-Prozess erfaehrt, WER
# ihn gestartet hat. sudo setzt SUDO_UID/SUDO_USER, pkexec PKEXEC_UID -
# und kein Zeitgeber setzt eines von beiden, weil systemd den Dienst
# direkt als root startet und keinen Menschen dazwischen hat.
SUDO_UID_ENV = "SUDO_UID"
SUDO_USER_ENV = "SUDO_USER"
PKEXEC_UID_ENV = "PKEXEC_UID"


def _at_a_terminal() -> bool:
    """Haengt an diesem Lauf ein Terminal?

    Das ist das einzige der drei Merkmale, das ein Zeitgeber nicht
    versehentlich erfuellen kann. src/system/zepos-update.service ist ein
    Type=oneshot ohne TTY-Angabe: systemd gibt ihm das Journal als
    Ausgabe und /dev/null als Eingabe, und weder das eine noch das andere
    ist jemals ein Terminal. Ein Mensch, der `sudo zepos-update` tippt -
    in kitty oder auf einer Konsole -, hat beides.

    BEIDE Seiten werden gefragt. `zepos-update | tee protokoll` haette
    eine Eingabe am Terminal und eine Ausgabe in einer Roehre; die
    Erzeugung dauert eine halbe Minute und schreibt in dieser Zeit
    Fortschritt, den dann niemand sieht. Wer sie trotzdem will, sagt es
    mit --regenerate.

    Eine geschlossene Standardeingabe wirft ValueError statt False zu
    liefern; das ist dann eben kein Terminal.
    """
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except (ValueError, AttributeError):
        return False


def _euid() -> int:
    """Als wen dieser Prozess laeuft.

    Eine eigene Funktion und kein os.geteuid() an der Aufrufstelle, damit
    ein Test die Rechtelage setzen kann, ohne os selbst zu verbiegen -
    dieselbe Naht wie runner= bei allem anderen in dieser Datei.
    """
    return os.geteuid()


def _invoking_account() -> tuple[int | None, str]:
    """uid und Name des Menschen hinter diesem Prozess.

    Drei Faelle, in dieser Reihenfolge:

      sudo/pkexec   SUDO_UID bzw. PKEXEC_UID. Der Prozess ist root, das
                    Konto, dessen Schreibtisch gemeint ist, steht in der
                    Umgebung.
      root ohne     Kein Konto. AUSDRUECKLICH kein Raten: ein root, das
      beides        sich den Benutzer aus loginctl aussucht, erzeugt auf
                    einer Maschine mit zwei Anmeldungen in ein fremdes
                    Heimatverzeichnis - und startet die Schale dessen
                    neu, der nichts getan hat. Genau der Fehler vom
                    11.08., nur mit einer anderen uid.
      kein root     Wir selbst. Ein Lauf ohne Rechte kommt zwar an
                    pacman nicht vorbei, aber die Erkennung soll nicht
                    davon abhaengen, wer sie fragt.
    """
    for name in (SUDO_UID_ENV, PKEXEC_UID_ENV):
        raw = os.environ.get(name)
        if raw and raw.isdigit():
            uid = int(raw)
            user = os.environ.get(SUDO_USER_ENV) or ""
            if not user:
                try:
                    import pwd

                    user = pwd.getpwuid(uid).pw_name
                except (ImportError, KeyError):
                    return None, ""
            return uid, user

    if _euid() != 0:
        uid = _euid()
        try:
            import pwd

            return uid, pwd.getpwuid(uid).pw_name
        except (ImportError, KeyError):
            return None, ""
    return None, ""


def caller(sessions: Iterable[Session], *, force: bool | None = None
           ) -> Invocation:
    """Hat ein Mensch das hier angestossen, in seiner eigenen Sitzung?

    DREI MERKMALE, MIT UND VERKNUEPFT, UND WARUM GERADE DIESE DREI

      1. Ein Terminal haengt am Lauf (_at_a_terminal). Das ist der
         strukturelle Unterschied: der Dienst hat keins und kann keins
         bekommen. Allein reicht es nicht - eine root-Schale ueber SSH
         hat auch eins, und dort gibt es keinen Schreibtisch, den ein
         Neuerzeugen erreichen wuerde.

      2. Ein benennbares Konto (_invoking_account). Ohne uid weiss ein
         root-Prozess nicht, WESSEN ~/.config er erzeugen soll, und die
         Antwort darf nicht geraten werden.

      3. Dieses Konto ist gerade an einem Sitzplatz angemeldet
         (parse_sessions verlangt seat). Das ist die Bedingung, die den
         Fall vom 11.08. ausschliesst und zugleich die einzige, unter
         der ein Neustart der Schale ueberhaupt etwas bewirkt: ohne
         laufende Sitzung gibt es nichts neu zu starten, und die naechste
         Anmeldung erzeugt ohnehin neu.

    Die Liste der Sitzungen wird HEREINGEREICHT und nicht hier geholt.
    perform() hat loginctl bereits gefragt, vor der ersten veraendernden
    Handlung; eine zweite Frage haette eine zweite Antwort sein koennen,
    und dann waere die Entscheidung an einer anderen Messung getroffen
    worden als die Benachrichtigung.

    `force` ist der ausdrueckliche Schalter (--regenerate/--no-regenerate).
    Er ueberstimmt Merkmal 1 und 3, NICHT Merkmal 2: ein root ohne
    SUDO_UID kann auch auf Zuruf nicht wissen, wem der Schreibtisch
    gehoert.
    """
    uid, user = _invoking_account()
    elevated = _euid() == 0

    if force is False:
        return Invocation(False, uid, user, elevated,
                          "Nicht neu erzeugt: --no-regenerate.")

    if uid is None or not user:
        return Invocation(
            False, uid, user, elevated,
            "Nicht neu erzeugt: dieser Lauf gehoert zu keinem Konto "
            f"({SUDO_UID_ENV} ist nicht gesetzt), und welcher Schreibtisch "
            "gemeint ist, wird nicht geraten.")

    if force is True:
        return Invocation(True, uid, user, elevated, "")

    if not _at_a_terminal():
        return Invocation(
            False, uid, user, elevated,
            "Nicht neu erzeugt: an diesem Lauf haengt kein Terminal - "
            "so ruft der Zeitgeber. `--regenerate` erzwingt es.")

    if uid not in {session.uid for session in sessions}:
        return Invocation(
            False, uid, user, elevated,
            f"Nicht neu erzeugt: fuer {user} ist gerade keine grafische "
            "Sitzung an einem Sitzplatz angemeldet.")

    return Invocation(True, uid, user, elevated, "")


# Was im Vordergrund wirklich laeuft. Eine Zeichenkette und kein
# zusammengesetzter Befehl, damit nichts, was von aussen kommt, je in
# eine Schale gerat: der Kontoname geht als ARGUMENT an runuser, nicht in
# dieses Skript.
#
# WARUM DIE UMGEBUNG HIER ERGAENZT WIRD
#     sudo setzt die Umgebung zurueck (env_reset ist die Vorgabe), und
#     runuser setzt HOME/USER/SHELL/PATH neu. Was dabei verloren geht,
#     ist genau das, was den Generator mit der laufenden Sitzung
#     verbindet: ohne XDG_RUNTIME_DIR, Sitzungsbus und WAYLAND_DISPLAY
#     erzeugt er zwar jede Datei richtig, aber `ags quit` und der
#     Neustart der Schale gehen ins Leere - und dann waere "direkt aktiv"
#     eine Behauptung.
#
#     /run/user/<uid>/bus ist derselbe Pfad, aus demselben Grund, den
#     notify_commands() weiter oben ausschreibt. Die Wayland-Steckdose
#     wird nicht geraten, sondern GESUCHT: im Laufzeitverzeichnis liegt
#     sie unter ihrem Namen, und -S nimmt die Steckdose und nicht die
#     Sperrdatei daneben (wayland-1 gegen wayland-1.lock).
#
# WARUM DER ZEITSTEMPEL HIER GESETZT WIRD UND NICHT IN PYTHON
#     Er gehoert dem KONTO und liegt in dessen Heimatverzeichnis. Ein
#     root, das ihn schreibt, hinterlaesst dort eine Datei, die dem Konto
#     nicht gehoert - und src/bin/zepos-session macht bei der naechsten
#     Anmeldung `: >"$GENERATED_STAMP"`, was daran scheitert. Hier laeuft
#     er als das Konto selbst und mit derselben Aufloesung von
#     XDG_STATE_HOME wie zepos-session, weil beide dieselbe Zeile tragen.
#
# UND WARUM NUR NACH EINEM ERFOLG
#     Ein gescheiterter Generatorlauf hat nichts erzeugt. Bliebe der
#     Zeitstempel trotzdem stehen, waere die Marke aus mark_regeneration()
#     entwertet - und die naechste Anmeldung, die den Fehlschlag heilen
#     wuerde, uebersaehe ihn.
REGENERATE_SCRIPT = r"""set -u
zustand="${XDG_STATE_HOME:-$HOME/.local/state}/zepos"

: "${XDG_RUNTIME_DIR:=/run/user/$(id -u)}"
export XDG_RUNTIME_DIR
: "${DBUS_SESSION_BUS_ADDRESS:=unix:path=$XDG_RUNTIME_DIR/bus}"
export DBUS_SESSION_BUS_ADDRESS
if [ -z "${WAYLAND_DISPLAY:-}" ]; then
    for steckdose in "$XDG_RUNTIME_DIR"/wayland-*; do
        [ -S "$steckdose" ] || continue
        WAYLAND_DISPLAY="${steckdose##*/}"
        export WAYLAND_DISPLAY
        break
    done
fi

zepos-generate --all
rc=$?
if [ "$rc" -eq 0 ]; then
    mkdir -p "$zustand"
    : >"$zustand/generated-at"
    rm -f "$zustand/regenerate-required"
fi
exit "$rc"
"""


def regenerate_command(invocation: Invocation) -> list[str]:
    """Der Befehl, der die Konfiguration im Vordergrund neu erzeugt.

    Als Argumentliste und nicht als Aufruf, aus demselben Grund wie bei
    systemd_actions(): so ist im Testbericht zu lesen, WAS abgesetzt
    wird, statt dass jemand es glauben muss.

    runuser und nicht `su -c`: dieselbe Ueberlegung wie bei
    notify_commands() - kein Anmeldevorgang, keine Kennwortabfrage, und
    keine Zeichenkette, die eine zweite Schale noch einmal liest.
    Laeuft der Aufruf ohnehin schon als das gemeinte Konto (also nicht
    als root), faellt runuser weg: sich selbst zu werden, kostet nur
    einen Prozess.
    """
    argv = ["bash", "-c", REGENERATE_SCRIPT]
    if invocation.elevated:
        return ["runuser", "-u", invocation.user, "--", *argv]
    return argv


# Die eine Zeile, an der `zepos-generate --all` selbst sagt, wo es steht.
# Sie steht so in src/generate_config.sh (generate_all_configs):
#
#     echo -e "${GREEN}→ Processing:${NC} ${base_name%-config}"
#
# GEZAEHLT WIRD, WAS DER GENERATOR SAGT, UND SONST NICHTS (20.08.2026)
#     Wie viele Vorlagen ein Lauf hat, sagt er selbst erst am Ende
#     ("Total configs: N"): er sammelt sie waehrend des Laufs ein und
#     ueberspringt einige davon. Eine Prozentzahl liesse sich hier also
#     nur aus einer zweiten Zaehlung erfinden, die neben der des
#     Generators herliefe und bei der ersten uebersprungenen Vorlage
#     falsch waere. Gezeigt wird deshalb die laufende Nummer und der
#     Name - beides steht in dieser einen Zeile.
#
# UND WARUM NICHT DER AUSGANG EINES ZIELS ("✓ Success")
#     Weil das ein anderer Satz ist und mehrere Fassungen hat: derselbe
#     Schritt endet auch mit "✗ Failed", und was ein Ziel meldet, das
#     nichts zu tun hatte, ist eine Frage des Generators und nicht
#     dieser Datei. Eine Zaehlung, die an dem Wortlaut haengt, zaehlt
#     falsch, sobald dort ein Wort dazukommt - und zaehlt dann still
#     falsch. Die begonnenen Schritte sind die Zahl, die der Generator
#     unter jeder seiner Fassungen ausschreibt.
GENERATOR_STEP = "→ Processing:"

# Wie lange ein Generatorlauf hoechstens dauern darf. Gemessen dauert er
# rund 30 Sekunden; die halbe Stunde ist der Abstand, ab dem etwas
# haengt und nicht mehr laeuft. Dieselbe Zahl in beiden Wegen - der
# stumme gibt sie an subprocess.run, der mitlesende an seine Uhr.
GENERATOR_TIMEOUT = 1800

# Farbe wird zum Zaehlen weggeschnitten: der Generator schreibt
# "\033[0;32m→ Processing:\033[0m waybar", und ein Vergleich gegen die
# rohe Zeile findet den Namen mitten zwischen Steuerzeichen.
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def regenerate(invocation: Invocation, *, runner: Runner | None = None,
               opener: Callable[..., Any] | None = None,
               stream: Any | None = None) -> int:
    """Neu erzeugen und die Schale neu starten, sichtbar.

    OHNE capture_output, und das ist der Unterschied zu jedem anderen
    Aufruf in dieser Datei: `zepos-generate --all` braucht auf einer
    frischen Maschine rund 30 Sekunden und schreibt in dieser Zeit, was
    es tut. Ein Mensch, der gerade `sudo zepos-update` getippt hat, soll
    das sehen und nicht auf eine stumme halbe Minute schauen.

    AN EINEM TERMINAL WIRD ES MITGELESEN (20.08.2026)
        GEMELDET: "ich will eine coole asci animation im terminal sehen
        statt nach zepos-update immer nicht". Die Ausgabe des Generators
        laeuft dann durch eine Roehre, wird Zeile fuer Zeile
        WEITERGEDRUCKT - keine einzige geht verloren, auch keine
        Fehlermeldung - und traegt daneben eine Statuszeile, die zaehlt,
        was fertig ist. Ohne Terminal bleibt es beim direkten Durchreichen
        an denselben Ausgang, den dieser Lauf ohnehin hat: der Zeitgeber
        laeuft hier nie hinein (caller().human ist dort falsch), aber ein
        `sudo zepos-update --regenerate > protokoll` schon, und der soll
        ein lesbares Protokoll bekommen.

    Der Rueckgabewert ist der des Generators; 127 steht fuer "gar nicht
    erst gestartet" (dieselbe Zahl, die eine Schale fuer einen fehlenden
    Befehl liefert), damit der Aufrufer beide Faelle gleich behandeln
    kann - in beiden ist nichts erzeugt worden.
    """
    argv = regenerate_command(invocation)
    stream = stream if stream is not None else sys.stdout

    if terminal.possible(stream):
        return _regenerate_live(argv, opener or subprocess.Popen, stream)

    runner = runner or subprocess.run
    try:
        result = runner(argv, timeout=GENERATOR_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return 127
    return result.returncode


def _regenerate_live(argv: Sequence[str], opener: Callable[..., Any],
                     stream: Any) -> int:
    """Denselben Befehl, mitgelesen und mitgezaehlt.

    stderr geht in denselben Strom wie stdout (STDOUT), damit eine
    Fehlermeldung des Generators an DER Stelle steht, an der sie
    entstanden ist, und nicht gesammelt hinterher. Sie wird gedruckt wie
    jede andere Zeile - die Statuszeile weicht ihr aus, sie weicht nicht
    der Statuszeile.

    WARUM HIER EINE UHR LAEUFT UND NICHT NUR EIN wait(timeout=...)
        Die Leseschleife endet, wenn die Roehre schliesst, und die
        schliesst erst, wenn JEDER Schreiber sie losgelassen hat - das
        Kind und alles, was es im Hintergrund gestartet hat.
        generate_config.sh startet zwei solche Kinder (helpers/
        notification-stub.py und `ags run`) und haengt beiden
        ">/dev/null 2>&1" an; nachgesehen am 20.08.2026 im Abschnitt
        "Start/restart AGS". Verloere eines davon diese Umleitung, haenge
        `sudo zepos-update` ohne diese Uhr fuer immer - mit einem
        freundlich drehenden Ring, was die Sache schlimmer macht und
        nicht besser. Die Grenze ist dieselbe wie im stummen Weg.
    """
    try:
        child = opener(list(argv), stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, bufsize=1)
    except (OSError, ValueError, subprocess.SubprocessError):
        return 127

    abgelaufen = threading.Event()

    def _abbrechen() -> None:
        abgelaufen.set()
        child.kill()

    uhr = threading.Timer(GENERATOR_TIMEOUT, _abbrechen)
    uhr.daemon = True
    uhr.start()

    nummer = 0
    with terminal.live("zepos-generate --all", stream=stream) as line:
        try:
            for zeile in child.stdout or ():
                zeile = zeile.rstrip("\n")
                # ZUERST drucken, dann auswerten: was der Generator sagt,
                # steht auf dem Bildschirm, auch wenn niemand es liest.
                line.write(zeile)
                nackt = _ANSI.sub("", zeile).strip()
                if nackt.startswith(GENERATOR_STEP):
                    nummer += 1
                    line.note(f"{nummer}. "
                              f"{nackt[len(GENERATOR_STEP):].strip()}")
            code = child.wait()
            # Ein abgewuergter Lauf hat nichts erzeugt, genau wie einer,
            # der nie angefangen hat - dieselbe Zahl fuer denselben
            # Zustand, damit aftermath() nicht zwei Faelle kennen muss.
            return 127 if abgelaufen.is_set() else code
        finally:
            uhr.cancel()
            # Auch bei Strg-C: ein Kind, das weiterlaeuft, waehrend
            # dieser Prozess endet, schriebe gleich in die Eingabezeile
            # der Schale, die den Nutzer dann schon wieder hat.
            if child.poll() is None:
                child.terminate()


def notification(outcome: Outcome, config: dict[str, Any], *,
                 regenerated: bool = False) -> Notification | None:
    """Was dem Nutzer gesagt wird - oder nichts.

    Drei Faelle und drei Einstellungen:

      changes   ein Fehlschlag und eine Aenderung werden gemeldet
      failures  nur der Fehlschlag
      never     nichts auf dem Schreibtisch. zepos-doctor meldet einen
                Fehlschlag trotzdem, denn "still" heisst "nicht stoeren"
                und nicht "verheimlichen".

    Ein Lauf ohne Aenderung meldet nie. Eine taegliche Nachricht
    "nichts zu tun" ist die zuverlaessigste Art, dafuer zu sorgen, dass
    die eine Nachricht, auf die es ankommt, weggeklickt wird, ohne
    gelesen worden zu sein.
    """
    mode = config["notify"]
    if mode == NOTIFY_NEVER:
        return None

    if outcome.failed:
        return Notification(
            summary="ZepOS-Aktualisierung fehlgeschlagen",
            body=(f"pacman endete mit {outcome.returncode}. "
                  f"Einzelheiten: journalctl -u {SERVICE_UNIT}, "
                  f"oder zepos-update --status."),
            urgent=True,
        )

    if mode == NOTIFY_FAILURES or not outcome.changed:
        return None

    names = ", ".join(change.name for change in outcome.upgraded)
    body = f"{names}."
    if outcome.replaced:
        # Ein entferntes Paket wird GENANNT. Ein Lauf, der etwas
        # abraeumt und nur die Neuzugaenge meldet, laesst den Nutzer
        # spaeter raten, wohin ein Befehl verschwunden ist.
        body += (f" Entfernt, weil ersetzt: "
                 f"{', '.join(outcome.replaced)}.")
    if regenerated:
        # Der Fall, den ein Mensch selbst angestossen hat. Der Satz
        # darunter waere hier schlicht falsch - es IST neu erzeugt
        # worden, und die Schale, die diese Nachricht anzeigt, ist
        # gerade deswegen neu gestartet.
        body += (" Die Konfiguration ist neu erzeugt und die Schale neu "
                 "gestartet.")
    elif outcome.sessions:
        # Die Antwort auf "was passiert mit meinem laufenden
        # Schreibtisch": nichts, bis zur naechsten Anmeldung.
        body += (" Die laufende Sitzung bleibt, wie sie ist; die neue "
                 "Fassung erscheint nach der naechsten Anmeldung.")
    if outcome.base_available:
        body += (f" Ausserdem warten {len(outcome.base_available)} "
                 f"Arch-Aktualisierungen; ZepOS fasst sie nicht an "
                 f"(sudo pacman -Syu).")
    return Notification(
        summary=f"ZepOS aktualisiert ({len(outcome.upgraded)})",
        body=body,
    )


def notify_commands(sessions: Iterable[Session], note: Notification
                    ) -> list[list[str]]:
    """Ein `notify-send` je angemeldeter Sitzung, als root abgesetzt.

    WARUM ueber systemd-run UND NICHT ueber su
        Dieser Dienst laeuft als root und muss in den Sitzungsbus eines
        Benutzers sprechen. `su -c` dafuer heisst: eine PAM-Sitzung
        oeffnen, um eine Zeile Text zuzustellen. systemd-run --uid setzt
        die Einheit direkt in den Bereich des Benutzers, ohne
        Anmeldevorgang, ohne Shell und ohne Zeichenkette, die von einer
        Shell noch einmal gelesen wird - der Text der Nachricht kommt
        aus pacman und darf nirgends interpretiert werden.

    Schlaegt es fehl, weil niemand einen Benachrichtigungsdienst laufen
    hat, ist das kein Fehler des Laufs. Die Aktualisierung ist dann
    trotzdem passiert, und die Zustandsdatei weiss davon.
    """
    commands = []
    for session in sessions:
        commands.append([
            "systemd-run", "--quiet", "--collect", f"--uid={session.uid}",
            f"--setenv=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/"
            f"{session.uid}/bus",
            "--", "notify-send", "--app-name=ZepOS",
            "--icon=system-software-update",
            f"--urgency={'critical' if note.urgent else 'normal'}",
            note.summary, note.body,
        ])
    return commands


# --------------------------------------------------------------------
# Der Zustand, den zepos-doctor liest
# --------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def state_document(outcome: Outcome, config: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "result": outcome.result,
        "started": outcome.started,
        "finished": outcome.finished,
        "scope": config["scope"],
        "returncode": outcome.returncode,
        "upgraded": [{"name": c.name, "from": c.old, "to": c.new}
                     for c in outcome.upgraded],
        "base_available": [{"name": c.name, "from": c.old, "to": c.new}
                           for c in outcome.base_available],
        "sessions": [session.user for session in outcome.sessions],
        # Die letzten Zeilen von pacman, im Wortlaut und in der Sprache
        # der Maschine. Sie sind das Einzige, was einem Menschen sagt,
        # WARUM ein Rueckgabewert 1 war.
        "message": outcome.message,
    }


def write_state(outcome: Outcome, config: dict[str, Any],
                path: Path | None = None) -> Path:
    target = path if path is not None else state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(state_document(outcome, config), indent=2) + "\n",
        encoding="utf-8")
    os.chmod(target, 0o644)
    return target


def read_state(path: Path | None = None) -> dict[str, Any] | None:
    """Der letzte Lauf, oder None, wenn es keinen gab.

    None und nicht ein leeres Dokument: "hat noch nie gelaufen" ist eine
    eigene Aussage, und zepos-doctor macht daraus eine andere Meldung als
    aus "ist zuletzt gescheitert".
    """
    target = path if path is not None else state_path()
    if not target.is_file():
        return None
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return document if isinstance(document, dict) else None


def describe(state: dict[str, Any] | None) -> str:
    """Ein Satz fuer einen Menschen: wann war das letzte Mal, was war."""
    if not state:
        return ("Diese Maschine hat sich noch nie selbst aktualisiert "
                "(kein Lauf verzeichnet).")

    when = state.get("finished") or state.get("started") or "unbekannt"
    result = state.get("result")
    upgraded = state.get("upgraded") or []
    base = state.get("base_available") or []

    if result == Outcome.FAILED:
        head = (f"Letzter Versuch {when}: FEHLGESCHLAGEN "
                f"(pacman {state.get('returncode')}).")
        message = (state.get("message") or "").strip()
        return f"{head}\n{message}" if message else head
    if result == Outcome.DISABLED:
        return (f"Zuletzt nachgesehen {when}: abgeschaltet "
                f"(update.enabled ist false).")
    if upgraded:
        names = ", ".join(f"{entry['name']} {entry['from']} -> {entry['to']}"
                          for entry in upgraded)
        head = f"Letzte Aktualisierung {when}: {names}."
    else:
        head = f"Zuletzt nachgesehen {when}: nichts zu tun."
    if base:
        head += (f" {len(base)} Arch-Aktualisierungen liegen bereit und "
                 f"werden nicht angefasst.")
    return head


def mark_regeneration(path: Path | None = None) -> Path:
    """Die Marke, die die naechste Anmeldung neu erzeugen laesst.

    Nur nach einem Lauf, der wirklich Pakete getauscht hat. Eine Marke
    nach jedem Lauf hiesse: jede Anmeldung erzeugt alles neu, taeglich,
    fuer nichts - und `zepos-generate --all` dauert auf einer frisch
    installierten Maschine rund 30 Sekunden, in denen der Nutzer einen
    schwarzen Bildschirm sieht (Spec, Stufe 4, "Erstinbetriebnahme").
    """
    target = path if path is not None else marker_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("", encoding="utf-8")
    os.chmod(target, 0o644)
    return target


def stamp_path(uid: int | None) -> Path | None:
    """Wo der Zeitstempel dieses Kontos liegt - oder None.

    DIESELBE AUFLOESUNG WIE REGENERATE_SCRIPT, ZEICHEN FUER ZEICHEN
        Dort steht `${XDG_STATE_HOME:-$HOME/.local/state}/zepos`, und
        zwar im Kind: runuser setzt HOME auf das Heimatverzeichnis des
        Kontos und laesst die uebrige Umgebung stehen. Hier wird deshalb
        genau dieselbe Reihenfolge gefragt - erst XDG_STATE_HOME, dann
        das Heimatverzeichnis DES KONTOS aus der Benutzerdatenbank, nie
        das des laufenden Prozesses.

        Ein `Path.home()` waere hier der Fehler, den diese Datei schon
        einmal beschrieben hat: der Prozess ist root, das gemeinte
        Heimatverzeichnis ist es nicht. paths.user_state_root() rechnet
        denselben Pfad fuer den EIGENEN Prozess aus und ist genau
        deswegen nicht das, was hier gebraucht wird.

    None heisst "es gibt kein Konto, dessen Zeitstempel gemeint sein
    koennte" - derselbe Fall, in dem caller() nicht erzeugt, weil ein
    root ohne SUDO_UID nicht raet, wessen Schreibtisch gemeint ist.
    """
    if uid is None:
        return None
    state_home = os.environ.get("XDG_STATE_HOME")
    if state_home:
        return Path(state_home) / "zepos" / GENERATED_STAMP
    try:
        import pwd

        home = Path(pwd.getpwuid(uid).pw_dir)
    except (ImportError, KeyError):
        return None
    return home / ".local" / "state" / "zepos" / GENERATED_STAMP


def regeneration_pending(invocation: Invocation) -> bool:
    """Steht fuer DIESES Konto eine Neuerzeugung aus? (20.08.2026)

    WORAN ES HAENGT, UND WARUM AN GENAU DEM
        An der Marke UND am Zeitstempel des aufrufenden Kontos, mit
        derselben Regel, die src/bin/zepos-session bei jeder Anmeldung
        anwendet:

            [[ -e "$UPDATE_MARKER" && "$UPDATE_MARKER" -nt "$GENERATED_STAMP" ]]

        Die Marke ALLEIN genuegt nicht, und das ist keine Feinheit: sie
        gilt der Maschine und jedem Konto auf ihr, und sie wird
        ABSICHTLICH nie geloescht - sie gehoert root, eine Sitzung kann
        das nicht, und ein zweites Konto braucht sein eigenes
        Neuerzeugen noch. Wer nur `marker_path().exists()` fragte, haette
        eine Maschine, die von der ersten Aktualisierung an bei JEDEM
        Lauf 30 Sekunden lang alles neu erzeugt, fuer immer.

        Und es ist bewusst KEINE zweite Antwort auf dieselbe Frage: die
        Anmeldung entscheidet es so, also entscheidet es dieser Lauf
        auch so. Waeren es zwei Regeln, koennte eine Anmeldung erzeugen,
        wo der Aktualisierer schweigt - und der Nutzer haette wieder
        einen Unterschied, den niemand erraten kann.

    NICHT gefragt wird die Bitte der Einstellungs-Anwendung
    (paths.SESSION_REGENERATE_MARKER, dieselbe Datei im Konto). Sie ist
    die Frage eines anderen, und zepos-session beantwortet sie schon;
    laeuft der Generator hier trotzdem, ist sie miterfuellt - dafuer
    raeumt REGENERATE_SCRIPT sie weg.
    """
    marker = marker_path()
    if not marker.exists():
        return False

    stamp = stamp_path(invocation.uid)
    if stamp is None:
        # Ohne Konto gibt es den Vergleich nicht - und ohne Konto wird
        # ohnehin nicht erzeugt (caller()). "Die Marke liegt" statt
        # einer Antwort auszugeben, waere genau die Aussage ueber die
        # MASCHINE, die dieser Datei die Sackgasse eingebracht hat.
        return False
    if not stamp.exists():
        # Genau bashs `-nt`: eine Datei, die es gibt, ist neuer als
        # eine, die es nicht gibt. Dieses Konto hat noch nie erzeugt.
        return True
    return marker.stat().st_mtime_ns > stamp.stat().st_mtime_ns


# --------------------------------------------------------------------
# Der Lauf
# --------------------------------------------------------------------

def _tail(result: subprocess.CompletedProcess, lines: int = 8) -> str:
    text = ((result.stdout or "") + (result.stderr or "")).strip()
    return "\n".join(text.splitlines()[-lines:])


def perform(config: dict[str, Any], *, runner: Runner | None = None,
            check_only: bool = False) -> Outcome:
    """Ein vollstaendiger Lauf: nachsehen, einspielen, berichten.

    Die Reihenfolge ist keine Geschmacksfrage. Erst die Datenbank, dann
    die Aufstellung, dann die eine veraendernde Handlung, dann die
    Sitzungen - so ist alles, was berichtet wird, gemessen worden,
    bevor es berichtet wird, und ein Abbruch in der Mitte hinterlaesst
    einen Zustand, der sagt, wie weit es kam.
    """
    runner = runner or subprocess.run
    started = _now()

    if not config["enabled"]:
        # Nicht stillschweigend. Wer den Zeitgeber von Hand einschaltet,
        # obwohl die Einstellung false sagt, soll im Journal lesen
        # koennen, warum nichts passiert ist.
        return Outcome(result=Outcome.DISABLED, started=started,
                       finished=_now(),
                       message="update.enabled ist false - nichts getan.")

    # Wer angemeldet ist, wird VOR der ersten Handlung gefragt und nicht
    # danach. Gemessen an der eigenen Testsuite: stand die Frage hinter
    # dem `pacman -Sy`, kam ein Lauf, der schon an der Datenbank
    # scheiterte, ohne Sitzungsliste heraus - und die Benachrichtigung
    # ueber den Fehlschlag ging an niemanden. Ausgerechnet der Fall, den
    # SigLevel = Required erzeugt, waere der einzige stille gewesen.
    sessions = graphical_sessions(runner=runner)

    refreshed = _run(runner, refresh_command(),
                     note="Paketdatenbank wird geholt")
    if refreshed.returncode != 0:
        return Outcome(result=Outcome.FAILED, returncode=refreshed.returncode,
                       message=_tail(refreshed), sessions=tuple(sessions),
                       started=started, finished=_now())

    # `pacman -Qu` endet mit 1, wenn nichts zu tun ist. Das ist kein
    # Fehler, und ein Lauf, der es dafuer haelt, meldet auf einer
    # aktuellen Maschine taeglich einen Fehlschlag.
    listed = _run(runner, upgradable_command(), timeout=120)
    changes = parse_upgradable(listed.stdout or "")

    members = set()
    if changes:
        offered = _run(runner, repository_command(), timeout=120)
        members = parse_repository(offered.stdout or "")
    ours, base = split(changes, members)
    if not config["report_base"]:
        base = []

    if config["scope"] == SCOPE_ALL:
        # Der ausdruecklich gewaehlte Weg: alles, was da ist. Dann gibt
        # es keine "Basis, die nur gemeldet wird" - sie wird eingespielt.
        ours, base = ours + base, []

    if not ours:
        return Outcome(result=Outcome.NOTHING, base_available=tuple(base),
                       sessions=tuple(sessions), started=started,
                       finished=_now())

    if check_only:
        # Was passieren WUERDE. upgraded ist besetzt und das Ergebnis
        # heisst trotzdem nicht "ok": ein --check, der als erfolgreiche
        # Aktualisierung abgelegt wuerde, waere eine Maschine, die
        # behauptet, aktuell zu sein, weil jemand nachgesehen hat.
        return Outcome(result=Outcome.PENDING, upgraded=tuple(ours),
                       base_available=tuple(base),
                       sessions=tuple(sessions), started=started,
                       finished=_now())

    # ERST ABRAEUMEN, WAS EIN NEUES PAKET ERSETZT
    #
    # Der Bereich "zepos" setzt `pacman -S` ab, und PKGBUILD(5) sagt zu
    # `replaces`: "Sysupgrade is currently the only pacman operation that
    # utilizes this field." Der Konflikt desselben Pakets wird dagegen
    # gelesen, und ein Konflikt mit `--noconfirm` bricht den GANZEN
    # Vorgang ab. Ohne diese Zeilen bekommt ein Rechner mit einem
    # ersetzten Paket gar keine Aktualisierung mehr - gemessen am
    # 03.09.2026 an zepos-claude-code, das am 01.09.2026 gefallen ist.
    #
    # Nur im Bereich "zepos": `-Syu` IST das Sysupgrade und liest
    # `replaces` selbst.
    #
    # NACH dem check_only-Ausgang darueber, damit `--check` weiterhin
    # nichts veraendert.
    replaced: tuple[str, ...] = ()
    if config["scope"] != SCOPE_ALL:
        gemeldet = _run(runner, installed_command(), timeout=120)
        vorhanden = parse_repository(gemeldet.stdout or "")
        replaced = tuple(sorted(replaced_by_repository() & vorhanden))
    if replaced:
        entfernt = _run(runner, removal_command(replaced),
                        note=f"ersetzt und wird entfernt: "
                             f"{', '.join(replaced)}")
        if entfernt.returncode != 0:
            return Outcome(result=Outcome.FAILED,
                           returncode=entfernt.returncode,
                           message=_tail(entfernt), base_available=tuple(base),
                           sessions=tuple(sessions), started=started,
                           finished=_now())

    # Der Text nennt die Pakete und nicht ihre Anzahl: "3 Pakete" ist
    # nach dem Lauf nicht mehr nachzuvollziehen, "zepos-config, ..."
    # schon - und dieselben Namen stehen gleich darunter mit Fassung
    # vorher und nachher.
    upgraded = _run(runner, upgrade_command(config,
                                            [change.name for change in ours]),
                    note=f"eingespielt wird: "
                         f"{', '.join(change.name for change in ours)}")
    if upgraded.returncode != 0:
        return Outcome(result=Outcome.FAILED, returncode=upgraded.returncode,
                       message=_tail(upgraded), base_available=tuple(base),
                       sessions=tuple(sessions), replaced=replaced,
                       started=started, finished=_now())

    return Outcome(result=Outcome.OK, upgraded=tuple(ours),
                   base_available=tuple(base), sessions=tuple(sessions),
                   replaced=replaced, message=_tail(upgraded),
                   started=started, finished=_now())


def announce(outcome: Outcome, config: dict[str, Any], *,
             runner: Runner | None = None,
             regenerated: bool = False) -> list[list[str]]:
    """Die Benachrichtigung absetzen, wenn es eine gibt.

    `regenerated` steht auf der Vorgabe False, weil das der Fall des
    Zeitgebers ist - und weil ein Vorgabewert, der die seltenere Haelfte
    beschreibt, jeden Aufrufer zwingt, an sie zu denken.
    """
    note = notification(outcome, config, regenerated=regenerated)
    if note is None:
        return []
    runner = runner or subprocess.run
    commands = notify_commands(outcome.sessions, note)
    for argv in commands:
        try:
            runner(argv, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            continue
    return commands


# --------------------------------------------------------------------
# Befehlszeile
# --------------------------------------------------------------------

USAGE = """usage: zepos-update  [--now] [--regenerate|--no-regenerate]
                            EINSPIELEN, was aus [zepos] kommt, und danach
                            neu erzeugen, wenn ein Mensch am Terminal
                            sitzt und angemeldet ist
       zepos-update --check           nur nachsehen und berichten
       zepos-update --status          was der letzte Lauf getan hat
       zepos-update --apply-schedule  NUR den Zeitgeber auf die
                            Einstellungen bringen - es wird dabei NICHTS
                            eingespielt und nichts erzeugt (--apply ist
                            derselbe Befehl unter seinem alten Namen; der
                            ALPM-Haken ruft ihn so)

DER UNTERSCHIED, DEN NIEMAND ERRATEN MUSS
    Was Pakete austauscht, ist `zepos-update` OHNE Argument, oder
    gleichbedeutend `zepos-update --now`. `--apply-schedule` stellt nur
    systemd ein - wann der Zeitgeber feuert und ob ueberhaupt.

WAS NACH EINEM LAUF NEU ERZEUGT WIRD
    Steht eine Neuerzeugung aus UND haengt ein Terminal an diesem Lauf
    UND ist das aufrufende Konto (SUDO_USER) gerade grafisch angemeldet,
    dann laeuft `zepos-generate --all` gleich hinterher, als dieses
    Konto: die Konfiguration ist neu, die Schale startet neu, und es
    braucht keine Neuanmeldung. Fehlt eine der drei Bedingungen - so ruft
    der Zeitgeber -, bleibt es bei der Marke, und die naechste Anmeldung
    erzeugt neu. --regenerate/--no-regenerate entscheiden es ausdruecklich,
    und --regenerate erzwingt es AUCH DANN, wenn nichts aussteht.

    "Steht aus" heisst: die Marke der Maschine ist neuer als der
    Zeitstempel dieses Kontos - dieselbe Regel, nach der eine Anmeldung
    entscheidet. Ein Lauf, der nichts eingespielt hat, holt die
    Neuerzeugung damit nach, die ein frueherer Lauf schuldig geblieben
    ist; `zepos-update --check` sagt, ob eine aussteht.

Was, wann und ob ueberhaupt entscheidet {config}; geschrieben wird das
mit `zepos-settings set update.<name> <wert>`:

{keys}

Die Arch-Basis wird gezaehlt und gemeldet, nicht angefasst - ausser
update.scope steht auf "all"."""


def usage_text() -> str:
    return USAGE.format(
        config=config_path(),
        keys="\n".join(f"    update.{name}" for name in known_keys()))


# Die Namen fuer die eine Handlung, die nur den Zeitgeber einstellt.
#
# WARUM ES ZWEI SIND, OBWOHL EINER GENUEGEN WUERDE
#     GEMELDET am 19.08.2026: der Nutzer hat in dieser Sitzung gefragt,
#     ob er "apply versuchen" solle, um Aktualisierungen einzuspielen.
#     Es haette nichts getan - "--apply" liest sich wie "spiel es ein",
#     und der Befehl schreibt eine systemd-Ergaenzung. Das ist ein Mangel
#     der Benennung und kein Missverstaendnis.
#
#     Der sprechende Name ist deshalb --apply-schedule, und er steht in
#     der Hilfe an erster Stelle. --apply bleibt trotzdem gueltig, weil
#     es nicht nur ein Tippweg ist: /usr/share/libalpm/hooks/
#     90-zepos-update.hook ruft `/usr/bin/zepos-update --apply`, und ein
#     Haken, der auf der Platte liegt, wird von der Aktualisierung
#     gerufen, die ihn gerade ersetzt. Ein ersatzlos geloeschter Aufruf
#     waere eine Maschine, die genau bei DEM pacman-Lauf ihren Zeitgeber
#     verliert, mit dem sie den neuen Namen bekommt.
SCHEDULE_FLAGS = ("--apply-schedule", "--apply")

# Der Hinweis, den ein MENSCH bekommt, der --apply getippt hat. Der Haken
# bekommt ihn nicht: an ihm haengt kein Terminal, und eine Zeile Prosa in
# jeder pacman-Transaktion ist Laerm, den niemand bestellt hat.
APPLY_NOTE = (
    "Hinweis: das hat nur den Zeitgeber eingestellt - es wurde nichts "
    "eingespielt.\n"
    "         Was Pakete austauscht, ist `sudo zepos-update` (oder "
    "`sudo zepos-update --now`).\n"
    "         Der sprechende Name dieses Befehls ist --apply-schedule.")


def aftermath(outcome: Outcome, invocation: Invocation,
              regeneration: int | None, *, dry: bool = False,
              pending: bool = False) -> list[str]:
    """Was nach dem Lauf gilt - und was NICHT gilt.

    Die eigentliche Bestellung des Nutzers steckt in diesen Zeilen: "und
    neue angezeigt sodass alle update direkt aktiv sind". Er will nach
    einem Lauf wissen, was er bekommen hat und ob er noch etwas tun muss.

    JEDE ZEILE HIER MUSS WAHR SEIN, AUCH DIE UNBEQUEME
        `zepos-generate --all` erzeugt die Konfiguration neu und startet
        AGS neu (siehe den Abschnitt "Start/restart AGS" in
        src/generate_config.sh). Hyprland startet es NICHT neu und laedt
        es auch nicht neu - es schreibt am Ende nur "Info: Run 'hyprctl
        reload'". Und `plugin=`-Zeilen liest Hyprland ausschliesslich
        beim Parsen, also beim Start (src/plugins.py). "Fertig, alles
        aktiv" waere darum in zwei Punkten gelogen, und der Nutzer merkte
        es erst, wenn er sich fragt, warum eine geaenderte Tastenbelegung
        nicht greift.

    `regeneration` ist None, wenn gar nicht erzeugt wurde, sonst der
    Rueckgabewert des Generators. `dry` ist der Probelauf: dann ist noch
    nichts geschehen, und jeder Satz steht im Konjunktiv - "erzeugt" zu
    drucken, wo nichts erzeugt wurde, waere dieselbe Unwahrheit wie
    "fertig" zu drucken, wo eine Neuanmeldung fehlt.

    `pending` ist die Lage, die drei Runden lang unsichtbar war
    (20.08.2026): es steht eine Neuerzeugung aus, die dieser Lauf nicht
    verursacht hat. Sie GEHOERT in die Ausgabe, samt dem Befehl, der sie
    aufloest - ein Nutzer, der dreimal "nothing" liest und dreimal eine
    alte Oberflaeche sieht, hat keinen Weg, von selbst darauf zu kommen.
    """
    lines: list[str] = []

    if outcome.failed:
        return ["Es wurde nichts eingespielt. Der Wortlaut oben ist "
                "pacmans eigener; `zepos-update --status` zeigt ihn "
                "wieder."]

    if outcome.base_available:
        lines.append(f"{len(outcome.base_available)} Arch-Aktualisierungen "
                     f"liegen bereit und werden nicht angefasst - "
                     f"`sudo pacman -Syu` spielt sie ein.")

    # Was DIESER Lauf eingespielt hat und was von frueher aussteht, sind
    # zwei verschiedene Aussagen. Nur die zweite braucht einen eigenen
    # Satz: die erste steht schon als Paketliste darueber.
    #
    # Und nur, solange sie noch WAHR ist: hat dieser Lauf gerade
    # erfolgreich erzeugt (regeneration == 0), steht nichts mehr aus, und
    # der Satz waere die Sorte Unwahrheit, gegen die der Absatz oben
    # geschrieben ist. Beim Probelauf und bei einem gescheiterten
    # Generator steht sie weiter.
    stale = pending and not outcome.changed and regeneration != 0
    if stale:
        lines.append(f"Eine Neuerzeugung steht aus: {marker_path()} ist "
                     f"neuer als {stamp_path(invocation.uid)} - es ist "
                     f"schon einmal etwas eingespielt worden, ohne dass "
                     f"seither erzeugt wurde.")
        # Der Befehl gehoert in dieselbe Ausgabe wie die Lage. Drei
        # Runden lang stand hier nichts, und der Nutzer hatte keinen
        # Weg, von "nothing" auf "dann eben --regenerate" zu kommen.
        lines.append("`sudo zepos-update --regenerate` erzeugt jetzt neu; "
                     "sonst tut es die naechste Anmeldung.")

    # `regeneration is not None` heisst: es ist erzeugt worden, ganz
    # gleich warum. Das ist der Fall `--regenerate` ohne alles - er hat
    # weder eine Aenderung noch eine ausstehende Marke, und ein Lauf, der
    # eine halbe Minute lang erzeugt und danach schweigt, sieht aus wie
    # einer, der nichts getan hat.
    if not (outcome.changed or pending or regeneration is not None):
        return lines

    if dry:
        if invocation.human:
            lines.append(f"Ein Lauf ohne --check wuerde danach "
                         f"`zepos-generate --all` als {invocation.user} "
                         f"ausfuehren; eine Neuanmeldung waere nicht noetig.")
        elif outcome.changed:
            lines.append(invocation.reason)
            lines.append("Ein Lauf ohne --check wuerde nur die Marke "
                         "setzen; erzeugt wuerde bei der naechsten "
                         "Anmeldung.")
        else:
            # Der Befehl steht schon im Absatz darueber; hier fehlt nur
            # noch, WARUM dieser Lauf ihn nicht von selbst ausfuehren
            # wuerde.
            lines.append(invocation.reason)
        return lines

    if regeneration is None:
        lines.append(invocation.reason)
        lines.append("Die laufende Sitzung behaelt ihre erzeugte "
                     "Konfiguration; die neue Fassung erscheint nach der "
                     "naechsten Anmeldung.")
        return lines

    if regeneration != 0:
        lines.append(f"Das Neuerzeugen ist gescheitert (rc={regeneration}). "
                     f"Es gilt weiter die alte Konfiguration; die naechste "
                     f"Anmeldung versucht es erneut, oder "
                     f"`zepos-generate --all` von Hand.")
        return lines

    lines.append("Neu erzeugt und die Schale (AGS) neu gestartet - dafuer "
                 "ist keine Neuanmeldung noetig.")
    lines.append("Hyprland selbst laeuft weiter mit der Konfiguration, mit "
                 "der es gestartet ist: geaenderte Regeln uebernimmt "
                 "`hyprctl reload`, geaenderte Plugins erst die naechste "
                 "Anmeldung.")
    return lines


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv in (["-h"], ["--help"]):
        print(usage_text())
        return 0

    # Handgeschrieben und nicht argparse, aus demselben Grund wie im Rest
    # dieses Baums: argparse haette fuer --apply eine eigene Fehlermeldung
    # gedruckt statt der Hilfe, die den Unterschied zwischen den beiden
    # Befehlen erklaert - und genau dieser Unterschied ist das Problem,
    # das hier behoben wird.
    action = ""
    force: bool | None = None
    for argument in argv:
        if argument in SCHEDULE_FLAGS or argument in ("--check", "--status",
                                                      "--now"):
            if action:
                print(usage_text(), file=sys.stderr)
                return 2
            action = argument
        elif argument == "--regenerate":
            force = True
        elif argument == "--no-regenerate":
            force = False
        else:
            print(usage_text(), file=sys.stderr)
            return 2

    if force is not None and action not in ("", "--now", "--check"):
        # Ein Schalter, der auf die gewaehlte Handlung nicht wirkt, ist
        # eine Anweisung, die ins Leere geht. Sie wird abgelehnt statt
        # uebergangen.
        print(usage_text(), file=sys.stderr)
        return 2

    try:
        config = load()
    except (UnusableConfig, OSError) as exc:
        print(f"{exc}\nNichts getan.", file=sys.stderr)
        return 1

    if action == "--status":
        print(describe(read_state()))
        return 0

    if action in SCHEDULE_FLAGS:
        for command in apply(config):
            print(" ".join(command))
        if action == "--apply" and _at_a_terminal():
            print(APPLY_NOTE)
        return 0

    check_only = action == "--check"
    outcome = perform(config, check_only=check_only)
    print(f"zepos-update: {outcome.result}")
    for change in outcome.upgraded:
        # Fassung vorher und nachher - Change.__str__ schreibt
        # "name alt -> neu". Das ist der Unterschied zwischen "es hat
        # sich etwas geaendert" und "DAS hat sich geaendert".
        print(f"  {change}")
    if outcome.message:
        print(outcome.message)

    invocation = caller(outcome.sessions, force=force)

    if check_only:
        # Auch der Probelauf sagt, was DANACH passieren wuerde. Bis heute
        # war das die eine Frage, die man nur durch Ausfuehren beantworten
        # konnte - und Ausfuehren ist genau das, was ein --check vermeidet.
        #
        # Und seit dem 20.08.2026 sagt er auch, was JETZT schon aussteht:
        # das ist die Lage, in der der Nutzer dreimal "nothing" gelesen
        # und dreimal eine alte Oberflaeche gesehen hat.
        for line in aftermath(outcome, invocation, None, dry=True,
                              pending=regeneration_pending(invocation)):
            print(line)
        return 0

    write_state(outcome, config)

    if outcome.changed:
        # Die Marke wird IMMER gesetzt, auch wenn gleich im Vordergrund
        # erzeugt wird. Sie gilt der MASCHINE und damit jedem Konto: wer
        # hier nicht angemeldet ist, bekommt sein Neuerzeugen bei seiner
        # naechsten Anmeldung. Der Vordergrundlauf entwertet sie nur fuer
        # SICH, indem er den Zeitstempel dieses Kontos danach neu setzt -
        # siehe REGENERATE_SCRIPT.
        mark_regeneration()

    # NACH mark_regeneration() gefragt, und das ist der Kern der
    # Korrektur vom 20.08.2026: erzeugt wird, wenn etwas AUSSTEHT - nicht
    # nur, wenn dieser eine Lauf etwas eingespielt hat. Ein Lauf, der
    # nichts zu tun fand, holt damit nach, was ein frueherer Lauf ohne
    # Terminal schuldig geblieben ist. Vorher blieb genau diese Schuld
    # liegen, beliebig oft wiederholbar, und kein Ausgang erwaehnte sie.
    pending = regeneration_pending(invocation)

    regeneration: int | None = None
    if invocation.human and (outcome.changed or pending or force is True):
        # force is True steht ausdruecklich noch einmal da: `--regenerate`
        # muss auch dann erzwingen, wenn nichts aussteht und nichts
        # eingespielt wurde. Ein Schalter, der schweigend nichts tut, ist
        # schlimmer als keiner - dann glaubt der Nutzer, es sei versucht
        # worden.
        print("")
        print(f"zepos-generate --all (als {invocation.user}) - "
              f"das dauert einen Moment.")
        regeneration = regenerate(invocation)

    announce(outcome, config, regenerated=regeneration == 0)

    for line in aftermath(outcome, invocation, regeneration, pending=pending):
        print(line)
    return 1 if outcome.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
