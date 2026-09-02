# SPDX-License-Identifier: GPL-3.0-or-later
"""Ein erfundener Zonenname darf nicht durchkommen - an jedem Tor.

WORAUF DIESE DATEI ANTWORTET
    Der Assistent fragte die Zeitzone bis zum 02.09.2026 als FREIES
    TEXTFELD ab, ohne jede Pruefung. "Europe/Berln" wurde anstandslos
    installiert - `date` nimmt JEDEN Namen an und druckt fuer einen
    unbekannten die UTC-Zeit mit dem erfundenen Kuerzel, Rueckgabewert
    0, leere Fehlerausgabe (die Messung steht in
    src/doctor.py:check_clock_zones). Heraus kam eine Uhr, die still
    zwei Stunden falsch geht, aus einem Tippfehler, und bis zu derselben
    Aufgabe ohne Weg zur Korrektur.

WARUM DIE ZUSICHERUNG UND NICHT DIE AUSWAHLLISTE DER SCHUTZ IST
    Beide Oberflaechen bieten die Zonen jetzt zur Auswahl an, und beide
    Auswahlen sind EINGABEHILFEN. Eine Eingabehilfe schuetzt nur,
    solange sie dasteht; der naechste Umbau kann sie wegnehmen, und
    genau das ist die Lage, aus der dieser Befund kommt - das Feld WAR
    ein Textfeld, und niemand hat es bemerkt, weil nichts es bemerkt
    hat.

    Deshalb pruefen die Zusicherungen hier nicht die Widgets, sondern
    die drei Stellen, die ein Umbau nicht mitnimmt:

      validate()          Der letzte Halt vor dem Loeschen der Platte.
                          installer.core.runner.install() ruft es
                          unmittelbar davor auf, und es gilt auch fuer
                          eine Konfigurationsdatei, die nie eine
                          Oberflaeche gesehen hat.
      PageState           Das Tor der grafischen Oberflaeche: solange
                          page_error("zeit") etwas sagt, geht es nicht
                          weiter.
      _ask_timezone()     Das Tor der Textoberflaeche: sie fragt noch
                          einmal, statt den Namen zurueckzugeben.

    Ein Test, der stattdessen "die Auswahlliste hat 598 Eintraege"
    behauptete, waere gruen und schuetzte nichts.

UND WARUM installer/core/timezones.py NEBEN src/region.py STEHT
    Weil der Assistent auf dem MEDIUM laeuft und src/ dort nicht liegt
    (packaging/zepos-installer bringt installer/ mit und sonst nichts
    vom Baum). Dass die beiden trotzdem nicht auseinanderlaufen, halten
    die Zusicherungen im letzten Abschnitt fest: dieselbe Datei,
    dieselben zwei Zeilenarten, dieselbe Vorgabe, dieselbe Ablehnung.

WAS HIER NICHT AUSGEFUEHRT WIRD
    `timedatectl set-timezone`. Es wuerde die Uhr der Maschine
    umstellen, auf der der Test laeuft. Gemessen wird an ECHTEN Dateien
    in tmp_path, umgelenkt ueber genau die Variablen, die die Module
    selbst dafuer nennen - TZDIR und ZEPOS_ETC_ROOT. Ein Test, der
    stattdessen eine Funktion ueberschreibt, prueft nicht mehr den Weg,
    den eine Installation geht.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from installer.core import timezones
from installer.core.model import DiskChoice, InstallConfig, UserAccount
from installer.core.validate import validate
from installer.gui.pages import PageState
from installer.tui.app import _ask_timezone

WURZEL = Path(__file__).resolve().parents[2]

# Ein Name, den keine Zeitzonendatenbank hat und der wie einer aussieht.
# Genau die Sorte, die `date` annimmt: ein gueltiger Pfadbestandteil mit
# einem falschen Buchstaben darin.
ERFUNDEN = "Europe/Berln"


@pytest.fixture
def datenbank(tmp_path, monkeypatch):
    """Eine Zeitzonendatenbank aus Dateien, wie glibc sie vorfindet.

    Dieselbe Bauform wie die Vorrichtung `maschine` in
    tests/src/test_region.py, und aus demselben Grund: umgelenkt wird
    ueber TZDIR und ZEPOS_ETC_ROOT, also ueber die Variablen, die die
    Module selbst nennen. tzdata.zi steht mit den zwei Zeilenarten
    darin, die es wirklich hat, und mit einer R-Zeile dazwischen, die
    keine von beiden ist.
    """
    etc = tmp_path / "wurzel"
    (etc / "etc").mkdir(parents=True)
    zoneinfo = tmp_path / "zoneinfo"
    (zoneinfo / "Europe").mkdir(parents=True)
    for zone in ("Europe/Berlin", "Europe/Lisbon", "UTC"):
        (zoneinfo / zone).write_text("TZif", encoding="utf-8")
    (zoneinfo / timezones.ZONE_FILE).write_text(
        "# tzdata.zi\n"
        "Z Europe/Berlin 1:0 - CET\n"
        "R CEST 1981 ma - Mar lastSun 2s 1 S\n"
        "L Europe/Lisbon Portugal\n"
        "Z UTC 0 - UTC\n",
        encoding="utf-8")
    monkeypatch.setenv(timezones.ZONEINFO_VARIABLE, str(zoneinfo))
    monkeypatch.setenv(timezones.ETC_ROOT_ENV, str(etc))
    return etc, zoneinfo


def _cfg(**over) -> InstallConfig:
    """Eine sonst gueltige Konfiguration - siehe test_validate.py._cfg.

    Sonst gueltig ist der ganze Zweck: was validate() dazu sagt, sagt
    es dann ueber die Zeitzone und nicht ueber irgendetwas anderes.
    """
    base = dict(
        language="de", keymap="de-latin1", timezone="Europe/Berlin",
        locale="de_DE", hostname="zepos",
        disk=DiskChoice(device="/dev/vda", size_bytes=64 * 1024**3),
        users=[UserAccount(username="lars", password="langgenug")],
        root_password="langgenug",
    )
    base.update(over)
    return InstallConfig(**base)


class ScriptedIO:
    """Antwortet der Reihe nach und schreibt mit, was gesagt wurde.

    Dieselbe Bauform wie ScriptedIO in tests/installer/test_tui.py -
    die Vorrichtung dort deckt den ganzen Ablauf ab, diese hier nur die
    eine Frage, und sie soll dabei nicht von der Reihenfolge aller
    anderen Antworten abhaengen.
    """

    def __init__(self, *answers):
        self.answers = list(answers)
        self.said = []
        self.asked = 0

    def ask(self, prompt, default=""):
        self.asked += 1
        return self.answers.pop(0) if self.answers else default

    def say(self, text):
        self.said.append(text)


# --------------------------------------------------------------------
# Das Tor vor dem Loeschen: validate()
# --------------------------------------------------------------------

def test_eine_erfundene_zone_haelt_die_installation_an():
    """DIE ZUSICHERUNG, UM DIE ES IN DIESER GANZEN DATEI GEHT.

    validate() ist der letzte Halt vor dem Loeschen der Platte
    (installer.core.runner.install ruft es dort auf), und sie gilt fuer
    JEDE Konfiguration - auch fuer eine vorgeladene Datei, die nie eine
    Auswahlliste gesehen hat. Bis zum 02.09.2026 sagte validate() zu
    der Zeitzone gar nichts, und `date` sagt auch nichts: ein
    Tippfehler wurde stillschweigend installiert.
    """
    befunde = validate(_cfg(timezone=ERFUNDEN))
    assert befunde, (
        "eine Zone, die es nicht gibt, laeuft wieder ungeprueft in die "
        "archinstall-Datei - genau der Fall, aus dem eine still falsch "
        "gehende Uhr entsteht")


def test_der_befund_nennt_den_namen_den_niemand_kennt():
    """Sonst weiss der Mensch nicht, WELCHE Angabe schuld ist.

    Er hat auf dieser Seite genau eine gemacht, und der Name, den er
    getippt hat, ist das einzige, woran er den Tippfehler sehen kann.
    """
    befunde = validate(_cfg(timezone=ERFUNDEN))
    assert any(ERFUNDEN in befund for befund in befunde)


def test_eine_echte_zone_erzeugt_keinen_befund():
    """Die Gegenprobe, ohne die die vorige Zusicherung auch dann gruen
    waere, wenn die Pruefung JEDE Zone ablehnte."""
    assert validate(_cfg(timezone="UTC")) == []


def test_eine_zone_dieser_maschine_erzeugt_keinen_befund():
    """Gegen die ECHTE Datenbank dieser Maschine und nicht gegen eine
    vorgegebene: die Pruefung liest im Betrieb /usr/share/zoneinfo, und
    eine Zusicherung, die nur mit TZDIR gilt, sagt darueber nichts."""
    if not timezones.database_present():
        pytest.skip("diese Maschine hat keine Zeitzonendatenbank")
    echte = timezones.all_zones()
    assert echte, "die Datenbank dieser Maschine nennt keine Zone"
    assert validate(_cfg(timezone=echte[0])) == []


def test_ein_name_der_die_datenbank_verlaesst_wird_abgelehnt(datenbank):
    """Der Name WIRD zu einem Pfad - dieselbe Regel wie in
    src/clocks.py und in region.known_timezone(), und aus demselben
    Grund: ein ".." darin oder ein fuehrender Schraegstrich zeigt aus
    der Datenbank heraus, und dort steht keine Zone."""
    for name in ("../etc/passwd", "/etc/passwd", "Europe/../../etc/passwd"):
        assert validate(_cfg(timezone=name)), (
            f"{name!r} ist kein Zonenname und kam durch")


def test_ohne_datenbank_wird_nichts_behauptet(tmp_path, monkeypatch):
    """Eine fehlende Datenbank ist kein Befund ueber die Zone.

    Ohne sie lehnt known() JEDEN Namen ab, UTC eingeschlossen - es
    fragt nach einer Datei, und wo kein Verzeichnis ist, ist keine
    Datei. Ein Befund daraus hielte auf einem Medium ohne tzdata jede
    Installation an, und zwar mit dem Satz "diese Zone gibt es nicht"
    ueber eine Zone, die es sehr wohl gibt. Die Begruendung steht bei
    timezones.database_present().
    """
    monkeypatch.setenv(timezones.ZONEINFO_VARIABLE,
                       str(tmp_path / "gibt-es-nicht"))
    assert not timezones.database_present()
    assert validate(_cfg(timezone="Europe/Berlin")) == []


def test_eine_leere_zone_ist_kein_erfundener_name():
    """Absichtlich kein Befund - die Begruendung steht bei
    validate._timezone_findings(). Kurz: beide Oberflaechen fuellen die
    Angabe mit timezones.running(), und was ohne sie in archinstall
    passiert, ist ein LAUTER Fehlschlag. Still ist der Fall, um den es
    hier geht."""
    assert validate(_cfg(timezone="")) == []


# --------------------------------------------------------------------
# Das Tor der grafischen Oberflaeche
# --------------------------------------------------------------------

def test_die_seite_zeit_laesst_eine_erfundene_zone_nicht_weiter():
    """Solange page_error("zeit") etwas sagt, geht der Assistent nicht
    weiter. Vor dem 02.09.2026 sagte die Seite ueberhaupt nichts - sie
    stand in der Liste der Seiten "ohne eigenen Befund"."""
    zustand = PageState()
    zustand.timezone = ERFUNDEN
    assert zustand.timezone_error()
    assert zustand.page_error("zeit")
    assert not zustand.is_page_valid("zeit")


def test_die_seite_zeit_laesst_eine_echte_zone_weiter():
    zustand = PageState()
    zustand.timezone = "UTC"
    assert zustand.timezone_error() == ""
    assert zustand.is_page_valid("zeit")


def test_eine_leere_seite_wird_zur_laufenden_zone(datenbank):
    """Ein leeres Feld ist nicht "keine Zone", sondern die laufende -
    und keine aus der SPRACHE abgeleitete. Genau diese Ableitung ist
    mit dieser Aufgabe gefallen ("en" hiess UTC)."""
    etc, zoneinfo = datenbank
    (etc / "etc" / "localtime").symlink_to(zoneinfo / "Europe" / "Lisbon")

    zustand = PageState()
    zustand.timezone = ""
    zustand.device = "/dev/vda"
    zustand.size_bytes = 64 * 1024**3
    assert zustand.to_config().timezone == "Europe/Lisbon"


def test_die_sprache_entscheidet_nicht_mehr_ueber_die_zone(datenbank):
    """Dieselbe Vorbelegung fuer beide Sprachen, und sie ist die
    laufende Zone.

    Die Tabelle LANGUAGE_DEFAULTS bildete "de" auf Europe/Berlin und
    "en" auf UTC ab. Eine Sprache ist kein Ort - wer auf Englisch
    installierte, bekam eine Uhr auf UTC, gleichgueltig, wo er sass.
    """
    etc, zoneinfo = datenbank
    (etc / "etc" / "localtime").symlink_to(zoneinfo / "Europe" / "Lisbon")

    gesehen = set()
    for sprache in ("de", "en"):
        zustand = PageState()
        zustand.language = sprache
        zustand.timezone = ""
        zustand.device = "/dev/vda"
        zustand.size_bytes = 64 * 1024**3
        gesehen.add(zustand.to_config().timezone)
    assert gesehen == {"Europe/Lisbon"}, (
        "die Zeitzone haengt wieder an der Sprache")


# --------------------------------------------------------------------
# Das Tor der Textoberflaeche
# --------------------------------------------------------------------

def test_der_textassistent_fragt_nach_einer_erfundenen_zone_noch_einmal(
        datenbank):
    """Er darf sie nicht zurueckgeben, und er darf auch nicht aufgeben.

    Wortgleich zur Vorgehensweise bei _ask_hostname(): ein Tippfehler
    ist kein Grund, den Assistenten zu verlassen, sondern ein Grund,
    dieselbe Frage noch einmal zu stellen.
    """
    io = ScriptedIO(ERFUNDEN, "Europe/Berlin")
    assert _ask_timezone(io) == "Europe/Berlin"
    assert io.asked == 2, "die Frage wurde nicht wiederholt"
    assert any(ERFUNDEN in text for text in io.said), (
        "die Klage nennt den getippten Namen nicht")


def test_der_textassistent_nennt_den_richtig_geschriebenen_namen(datenbank):
    """DER TIPPFEHLER IST DER FALL, UM DEN ES GEHT, und ihn bloss
    abzulehnen hilft nicht: wer sich vertippt hat, weiss ja nicht,
    WORIN. Ein Teilstueck-Vergleich findet ihn nicht ("Berln" steht in
    keinem Namen), difflib schon - die Messung steht bei
    timezones.SUGGESTION_CUTOFF."""
    io = ScriptedIO(ERFUNDEN, "Europe/Berlin")
    _ask_timezone(io)
    assert any("Europe/Berlin" in text for text in io.said), (
        "der richtige Name wurde nicht vorgeschlagen")


def test_der_textassistent_nimmt_die_laufende_zone_als_vorbelegung(datenbank):
    """Die leere Antwort ist die haeufigste, und sie darf nicht in einer
    aus der Sprache abgeleiteten Zone enden."""
    etc, zoneinfo = datenbank
    (etc / "etc" / "localtime").symlink_to(zoneinfo / "Europe" / "Lisbon")
    assert _ask_timezone(ScriptedIO("")) == "Europe/Lisbon"


def test_der_textassistent_sagt_etwas_auch_ohne_vorschlag(datenbank):
    """Kein Vorschlag ist der Fall, in dem ein Mensch sonst dreimal
    dasselbe tippt. Dann muss dastehen, WO die Namen stehen."""
    io = ScriptedIO("Mars/Olympus_Mons", "UTC")
    assert _ask_timezone(io) == "UTC"
    assert any("timedatectl" in text for text in io.said)


# --------------------------------------------------------------------
# Die zwei Fassungen gegeneinander
# --------------------------------------------------------------------

def _region():
    """src/region.py laden, ohne den Suchpfad dauerhaft zu verstellen.

    Dieselbe Vorrichtung, mit der tests/src/test_login.py den Installer
    aus einem src-Test heraus laedt - nur in der anderen Richtung.
    """
    sys.path.insert(0, str(WURZEL / "src"))
    try:
        import region
        return region
    finally:
        sys.path.remove(str(WURZEL / "src"))


def test_beide_fassungen_nennen_dieselbe_datei_und_dieselbe_vorgabe():
    """Der Assistent kann src/region.py nicht importieren - src/ liegt
    nicht auf dem Medium (siehe den Kopf von
    installer/core/timezones.py). Zwei Fassungen, die auseinanderlaufen,
    waeren zwei Antworten auf dieselbe Frage; diese Zeilen sind das,
    was es statt eines Imports gibt."""
    region = _region()
    assert timezones.ZONE_FILE == region.ZONE_FILE
    assert timezones.ZONEINFO == region.ZONEINFO
    assert timezones.ZONEINFO_VARIABLE == region.ZONEINFO_VARIABLE
    assert timezones.DEFAULT_TIMEZONE == region.DEFAULT_TIMEZONE
    assert timezones.ETC_ROOT_ENV == region.ETC_ROOT_ENV
    assert timezones.LOCALTIME == region.LOCALTIME


def test_beide_fassungen_lesen_dieselbe_zonenliste(datenbank):
    """Aus DERSELBEN vorgegebenen Datenbank, damit der Vergleich die
    Fassungen misst und nicht zwei Maschinen."""
    region = _region()
    assert timezones.all_zones() == region.timezones()
    assert timezones.all_zones() == ["Europe/Berlin", "Portugal", "UTC"], (
        "die Z- und die L-Zeile werden gelesen, die R-Zeile nicht")


def test_beide_fassungen_lehnen_dieselben_namen_ab(datenbank):
    region = _region()
    for name in ("Europe/Berlin", "UTC", ERFUNDEN, "", "/etc/passwd",
                 "../etc/passwd", "Portugal"):
        assert timezones.known(name) == region.known_timezone(name), (
            f"die beiden Fassungen sind sich ueber {name!r} nicht einig")


def test_beide_fassungen_lesen_dieselbe_laufende_zone(datenbank):
    etc, zoneinfo = datenbank
    (etc / "etc" / "localtime").symlink_to(zoneinfo / "Europe" / "Berlin")
    region = _region()
    assert timezones.running() == region.current_timezone() == "Europe/Berlin"


def test_die_echte_datenbank_dieser_maschine_gibt_beiden_dasselbe():
    """Ohne Vorgabe, also gegen /usr/share/zoneinfo.

    Die vorige Zusicherung gilt fuer eine Datenbank aus fuenf Zeilen.
    Diese hier ist die, die den Fall abdeckt, in dem eine der beiden
    Fassungen etwas liest, das nur in der echten Datei vorkommt.
    """
    if not timezones.database_present():
        pytest.skip("diese Maschine hat keine Zeitzonendatenbank")
    region = _region()
    assert timezones.all_zones() == region.timezones()


# --------------------------------------------------------------------
# Die laufende Zone und die Liste
# --------------------------------------------------------------------

def test_ohne_symlink_bleibt_es_bei_utc(datenbank):
    """Und wird nicht geraten. UTC ist die einzige Zone, die keine
    Behauptung ueber den Aufenthaltsort eines Menschen enthaelt."""
    assert timezones.running() == "UTC"


def test_ein_ziel_ausserhalb_der_datenbank_wird_nicht_geraten(datenbank,
                                                              tmp_path):
    """Ein kopiertes /etc/localtime kommt vor, und dann steht der Name
    der Zone nirgends. Das ist eine Nichtantwort und keine Antwort."""
    etc, _zoneinfo = datenbank
    fremd = tmp_path / "irgendwo" / "Zeit"
    fremd.parent.mkdir()
    fremd.write_text("TZif", encoding="utf-8")
    (etc / "etc" / "localtime").symlink_to(fremd)
    assert timezones.running() == "UTC"


def test_die_laufende_zone_steht_immer_zur_wahl(datenbank):
    """Eine Auswahl, in der der geltende Zustand fehlt, stellt beim
    blossen Ansehen etwas anderes ein."""
    etc, zoneinfo = datenbank
    (etc / "etc" / "localtime").symlink_to(zoneinfo / "Europe" / "Lisbon")
    assert timezones.running() in timezones.choices()


def test_auch_ohne_datenbank_gibt_es_etwas_zu_waehlen(tmp_path, monkeypatch):
    """Sonst zeigte der Assistent eine leere Liste, und eine leere
    Liste sieht aus wie ein Absturz."""
    monkeypatch.setenv(timezones.ZONEINFO_VARIABLE,
                       str(tmp_path / "gibt-es-nicht"))
    monkeypatch.setenv(timezones.ETC_ROOT_ENV, str(tmp_path / "leer"))
    assert timezones.choices() == [timezones.DEFAULT_TIMEZONE]


# --------------------------------------------------------------------
# Die Suche der Textoberflaeche
# --------------------------------------------------------------------

def test_die_suche_findet_den_richtig_geschriebenen_namen(datenbank):
    """Die Datenbank ist buchstabengenau - "europe/berlin" ist dort
    KEINE Zone. Eine Suche ohne Ruecksicht auf die Schreibweise ist
    damit auch die Antwort auf einen Kleinschreibungsfehler."""
    assert not timezones.known("europe/berlin")
    assert "Europe/Berlin" in timezones.matching("europe/berlin")


def test_die_suche_findet_einen_tippfehler(datenbank):
    assert "Europe/Berlin" in timezones.matching(ERFUNDEN)


def test_die_suche_findet_ein_teilstueck(datenbank):
    assert timezones.matching("Berlin") == ["Europe/Berlin"]


def test_die_suche_auf_nichts_gibt_nichts(datenbank):
    """Und keine Liste aller Zonen: eine leere Eingabe ist keine Frage."""
    assert timezones.matching("") == []
    assert timezones.matching("   ") == []


def test_die_suche_nach_einem_erfundenen_ort_gibt_ehrlich_nichts(datenbank):
    """Ein Name, der keinem aehnlich sieht, bekommt keinen Vorschlag -
    lieber nichts als ein geratener Ort."""
    assert timezones.matching("Mars/Olympus_Mons") == []


def test_die_suche_dieser_maschine_findet_wirklich_etwas():
    """Gegen die echte Datenbank: alle Zusicherungen darueber gelten
    fuer drei vorgegebene Namen, und drei Namen sind die Menge, bei der
    difflib immer etwas oder nie etwas findet."""
    if not timezones.database_present():
        pytest.skip("diese Maschine hat keine Zeitzonendatenbank")
    if "Europe/Berlin" not in timezones.all_zones():
        pytest.skip("diese Datenbank kennt Europe/Berlin nicht")
    assert timezones.matching("Europe/Berln")[0] == "Europe/Berlin", (
        "difflib schlaegt den richtigen Namen nicht mehr an erster "
        "Stelle vor - SUGGESTION_CUTOFF passt nicht mehr")


def test_die_suche_kuerzt_nicht_selbst(datenbank, monkeypatch):
    """Sie gibt VOLLSTAENDIG zurueck; wer ausgibt, muss zaehlen.

    Eine Liste, die stillschweigend endet, sieht aus wie die ganze
    Antwort - deshalb liegt das Kuerzen bei _ask_timezone(), das die
    uebrigen Namen dabei ZAEHLT.
    """
    treffer = timezones.matching("Europe")
    assert treffer == ["Europe/Berlin"]
    # Und die Grenze selbst ist eine Zahl und keine Meinung: sie steht
    # als Name da, damit der Aufrufer und die Begruendung dieselbe
    # benutzen.
    assert timezones.SUGGESTION_LIMIT > 0
