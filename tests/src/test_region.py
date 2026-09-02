# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Sprache und die Zeitzone der Maschine - an echten Dateien gemessen.

WAS HIER AUSGEFUEHRT WIRD UND WAS NICHT
    Jede Pruefung dieser Datei legt eine ECHTE Datei an und liest sie
    mit dem echten Code wieder - eine locale.conf in tmp_path, einen
    Symlink nach /etc/localtime, eine Zeitzonendatenbank aus zwei
    Dateien. Nichts davon wird durchsucht, alles davon wird
    ausgefuehrt.

    Was NICHT ausgefuehrt wird: `localectl set-locale` und `timedatectl
    set-timezone`. Sie wuerden die Maschine aendern, auf der der Test
    laeuft, und ein Test, der die Sprachumgebung des Entwicklers
    umstellt, ist ein Test, der genau einmal laeuft. Geprueft wird
    deshalb die argv-Liste, die hinausginge - dieselbe Trennung wie in
    tests/settings/test_settings_model.py, wo `runner` eingespeist wird
    und der Befehl selbst nie startet.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WURZEL / "src"))
sys.path.insert(0, str(WURZEL))

import region                                                   # noqa: E402
from installer.gui.pages import LANGUAGE_DEFAULTS               # noqa: E402


@pytest.fixture
def maschine(tmp_path, monkeypatch):
    """Eine Maschine aus Verzeichnissen: /etc und eine Zonendatenbank.

    Beide werden ueber genau die Variablen umgelenkt, die das Modul
    selbst dafuer nennt - ZEPOS_ETC_ROOT und TZDIR. Ein Test, der
    stattdessen eine Funktion ueberschreibt, prueft nicht mehr den Weg,
    den eine Installation geht.
    """
    etc = tmp_path / "wurzel"
    (etc / "etc").mkdir(parents=True)
    zoneinfo = tmp_path / "zoneinfo"
    (zoneinfo / "Europe").mkdir(parents=True)
    (zoneinfo / "Europe" / "Berlin").write_text("TZif", encoding="utf-8")
    (zoneinfo / "Europe" / "Lisbon").write_text("TZif", encoding="utf-8")
    (zoneinfo / "UTC").write_text("TZif", encoding="utf-8")
    monkeypatch.setenv(region.ETC_ROOT_ENV, str(etc))
    monkeypatch.setenv(region.ZONEINFO_VARIABLE, str(zoneinfo))
    return etc, zoneinfo


# --------------------------------------------------------------------
# Die Tabelle der Sprachen
# --------------------------------------------------------------------

def test_die_sprachtabelle_stimmt_mit_der_des_installers_ueberein():
    """Zwei Tabellen ueber dieselbe Sache, und nur eine wird gepflegt.

    Dieselbe Vorrichtung wie in tests/src/test_login.py fuer den
    Greeter: src/region.py kann installer/gui/pages.py nicht importieren
    (auf einer Installation liegt der Assistent nicht), also haelt
    dieser Test die beiden zusammen. Ohne ihn faellt eine dritte Sprache
    im Assistenten hier still unter den Tisch, und die Einstellung boete
    sie nie an.
    """
    aus_dem_installer = {
        code: f"{locale}.UTF-8"
        for code, (_keymap, locale, *_rest) in LANGUAGE_DEFAULTS.items()
    }
    hier = {sprache.code: sprache.locale for sprache in region.LANGUAGES}
    assert hier == aus_dem_installer


def test_die_quellsprache_steht_in_der_tabelle():
    """Englisch ist kein Sonderfall neben der Tabelle, sondern in ihr."""
    assert region.SOURCE_LANGUAGE in {s.code for s in region.LANGUAGES}
    assert region.DEFAULT_LANGUAGE in {s.code for s in region.LANGUAGES}


def test_ein_unbekannter_sprachcode_wird_abgelehnt_und_nennt_die_bekannten():
    with pytest.raises(region.UnknownLanguage) as klage:
        region.language_named("fr")
    assert "de" in str(klage.value) and "en" in str(klage.value)


# --------------------------------------------------------------------
# /etc/locale.conf
# --------------------------------------------------------------------

def test_lang_wird_aus_der_datei_gelesen(maschine):
    etc, _zoneinfo = maschine
    (etc / "etc" / "locale.conf").write_text(
        "LANG=de_DE.UTF-8\n", encoding="utf-8")
    assert region.read_lang() == "de_DE.UTF-8"
    assert region.current_language() == "de"


def test_anfuehrungszeichen_gehoeren_nicht_zum_wert(maschine):
    etc, _zoneinfo = maschine
    (etc / "etc" / "locale.conf").write_text(
        'LANG="en_US.UTF-8"\n', encoding="utf-8")
    assert region.read_lang() == "en_US.UTF-8"
    assert region.current_language() == "en"


def test_die_letzte_zuweisung_gewinnt(maschine):
    """Wie in einer Shell - sonst gaebe dieselbe Datei zwei Antworten."""
    etc, _zoneinfo = maschine
    (etc / "etc" / "locale.conf").write_text(
        "LANG=de_DE.UTF-8\nLC_TIME=de_DE.UTF-8\nLANG=en_US.UTF-8\n",
        encoding="utf-8")
    assert region.read_lang() == "en_US.UTF-8"


def test_die_datei_wird_gelesen_und_nicht_ausgefuehrt(maschine, tmp_path):
    """Eine Datei unter /etc darf keine Befehle enthalten duerfen.

    Sie sieht aus wie ein Shell-Schnipsel; sie in eine Shell zu geben
    waere der Fehler. Der Beweis ist die Datei, die dabei entstuende.
    """
    etc, _zoneinfo = maschine
    beweis = tmp_path / "ausgefuehrt"
    (etc / "etc" / "locale.conf").write_text(
        f"LANG=de_DE.UTF-8\n$(touch {beweis})\n`touch {beweis}`\n",
        encoding="utf-8")
    assert region.read_lang() == "de_DE.UTF-8"
    assert not beweis.exists()


def test_ohne_datei_bleibt_die_umgebung_der_rueckfall(maschine, monkeypatch):
    """Ein Container hat kein /etc/locale.conf und trotzdem ein LANG."""
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert region.read_lang() == ""
    assert region.current_locale() == "en_US.UTF-8"
    assert region.current_language() == "en"


def test_die_datei_schlaegt_die_umgebung(maschine, monkeypatch):
    """Der Punkt, an dem die ganze Sofortwirkung haengt.

    Die Umgebung einer laufenden Sitzung ist eine ABSCHRIFT der Datei,
    angefertigt bei der Anmeldung. Wer die Sprache umstellt, aendert die
    Datei - und wer danach die Umgebung liest, liest den alten Wert.
    """
    etc, _zoneinfo = maschine
    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    (etc / "etc" / "locale.conf").write_text(
        "LANG=en_US.UTF-8\n", encoding="utf-8")
    assert region.current_locale() == "en_US.UTF-8"


def test_eine_unbekannte_sprachumgebung_gibt_keine_geratene_antwort():
    assert region.language_of("fr_FR.UTF-8") == ""
    assert region.language_of("") == ""
    assert region.language_of("de_AT.UTF-8") == ""


# --------------------------------------------------------------------
# /etc/localtime
# --------------------------------------------------------------------

def test_die_zeitzone_kommt_aus_dem_symlink(maschine):
    etc, zoneinfo = maschine
    (etc / "etc" / "localtime").symlink_to(zoneinfo / "Europe" / "Berlin")
    assert region.current_timezone() == "Europe/Berlin"


def test_ohne_symlink_bleibt_es_bei_utc(maschine):
    """Keine Datei ist keine Zone - und UTC behauptet keinen Ort."""
    assert region.current_timezone() == region.DEFAULT_TIMEZONE


def test_ein_ziel_ausserhalb_der_datenbank_wird_nicht_geraten(maschine,
                                                             tmp_path):
    etc, _zoneinfo = maschine
    fremd = tmp_path / "irgendwo"
    fremd.write_text("TZif", encoding="utf-8")
    (etc / "etc" / "localtime").symlink_to(fremd)
    assert region.current_timezone() == region.DEFAULT_TIMEZONE


# --------------------------------------------------------------------
# Was die Datenbank kennt
# --------------------------------------------------------------------

def test_eine_zone_der_datenbank_ist_bekannt(maschine):
    assert region.known_timezone("Europe/Berlin")
    assert region.known_timezone("UTC")


def test_eine_zone_die_es_nicht_gibt_ist_unbekannt(maschine):
    assert not region.known_timezone("Mars/Olympus_Mons")
    assert not region.known_timezone("")


@pytest.mark.parametrize("name", [
    "/etc/passwd",
    "../../etc/passwd",
    "Europe/../../etc/passwd",
])
def test_ein_name_der_die_datenbank_verlaesst_ist_kein_zonenname(maschine,
                                                                name):
    """Dieselbe Regel wie in src/clocks.py, und aus demselben Grund:
    der Name wird zu einem Pfad."""
    assert not region.known_timezone(name)


def test_der_setzbefehl_lehnt_eine_unbekannte_zone_ab_bevor_er_laeuft(
        maschine):
    with pytest.raises(region.UnknownTimezone) as klage:
        region.timezone_command("Mars/Olympus_Mons")
    assert "timedatectl list-timezones" in str(klage.value)


def test_der_setzbefehl_fuer_eine_bekannte_zone(maschine):
    assert region.timezone_command("Europe/Lisbon") == [
        "timedatectl", "set-timezone", "Europe/Lisbon"]


def test_der_setzbefehl_fuer_eine_sprache_setzt_LANG_und_nicht_LC_MESSAGES():
    """LANG stellt alle Kategorien um - siehe den Kopf von region.py."""
    assert region.language_command("en") == [
        "localectl", "set-locale", "LANG=en_US.UTF-8"]


# --------------------------------------------------------------------
# Welche Sprachen wirklich angeboten werden
# --------------------------------------------------------------------

def _katalog(verzeichnis: Path, code: str) -> None:
    ziel = verzeichnis / code / region.CATALOGUE_SUBPATH
    ziel.mkdir(parents=True, exist_ok=True)
    (ziel / f"{region.DOMAIN}.mo").write_bytes(b"\xde\x12\x04\x95")


def _erzeugt(etc: Path, *namen: str) -> None:
    """Eine /etc/locale.gen, die genau diese Sprachumgebungen nennt.

    In der Form, in der Arch sie fuehrt: Name, Leerzeichen,
    Zeichensatz - und die uebrigen dreihundert Zeilen auskommentiert.
    """
    zeilen = ["# Configuration file for locale-gen", "#fr_FR.UTF-8 UTF-8"]
    zeilen += [f"{name} UTF-8" for name in namen]
    (etc / "etc" / "locale.gen").write_text("\n".join(zeilen) + "\n",
                                            encoding="utf-8")


def test_eine_sprache_ohne_katalog_wird_nicht_angeboten(maschine, tmp_path,
                                                        monkeypatch):
    """Der Kern der Bestellung: die Liste kommt aus dem, was da ist."""
    etc, _zoneinfo = maschine
    (etc / "etc" / "locale.conf").write_text(
        "LANG=en_US.UTF-8\n", encoding="utf-8")
    katalogverzeichnis = tmp_path / "locale"
    monkeypatch.setenv(region.LOCALEDIR_ENV, str(katalogverzeichnis))
    # Beide Sprachumgebungen sind erzeugt, aber es liegt KEIN deutscher
    # Katalog - Deutsch waere also eine Auswahl ohne Uebersetzung.
    _erzeugt(etc, "de_DE.UTF-8", "en_US.UTF-8")
    assert [s.code for s in region.available_languages()] == ["en"]


def test_eine_sprache_ohne_erzeugte_sprachumgebung_wird_nicht_angeboten(
        maschine, tmp_path, monkeypatch):
    """GEMESSEN: setlocale gibt fuer eine fehlende Umgebung null zurueck
    und aendert still nichts."""
    etc, _zoneinfo = maschine
    (etc / "etc" / "locale.conf").write_text(
        "LANG=en_US.UTF-8\n", encoding="utf-8")
    katalogverzeichnis = tmp_path / "locale"
    _katalog(katalogverzeichnis, "de")
    monkeypatch.setenv(region.LOCALEDIR_ENV, str(katalogverzeichnis))
    _erzeugt(etc, "en_US.UTF-8")
    assert [s.code for s in region.available_languages()] == ["en"]


def test_mit_katalog_und_umgebung_steht_die_sprache_zur_wahl(
        maschine, tmp_path, monkeypatch):
    etc, _zoneinfo = maschine
    (etc / "etc" / "locale.conf").write_text(
        "LANG=en_US.UTF-8\n", encoding="utf-8")
    katalogverzeichnis = tmp_path / "locale"
    _katalog(katalogverzeichnis, "de")
    monkeypatch.setenv(region.LOCALEDIR_ENV, str(katalogverzeichnis))
    _erzeugt(etc, "de_DE.UTF-8", "en_US.UTF-8")
    assert [s.code for s in region.available_languages()] == ["de", "en"]


def test_die_geltende_sprache_steht_immer_in_der_liste(maschine, tmp_path,
                                                       monkeypatch):
    """Eine Auswahl ohne den geltenden Zustand stellt beim Ansehen um."""
    etc, _zoneinfo = maschine
    (etc / "etc" / "locale.conf").write_text(
        "LANG=de_DE.UTF-8\n", encoding="utf-8")
    katalogverzeichnis = tmp_path / "leer"
    katalogverzeichnis.mkdir()
    monkeypatch.setenv(region.LOCALEDIR_ENV, str(katalogverzeichnis))
    # Weder Katalog noch erzeugte Umgebung fuer Deutsch - es ist
    # trotzdem der Wert, der gerade gilt.
    _erzeugt(etc)
    assert "de" in {s.code for s in region.available_languages()}


@pytest.mark.parametrize("geschrieben", ["de_DE.utf8", "de_DE.UTF-8"])
def test_beide_schreibweisen_einer_sprachumgebung_zaehlen(maschine, tmp_path,
                                                          monkeypatch,
                                                          geschrieben):
    """`locale -a` schreibt de_DE.utf8, LANG schreibt de_DE.UTF-8 -
    dieselbe Sprachumgebung, zwei Schreibweisen."""
    etc, _zoneinfo = maschine
    (etc / "etc" / "locale.conf").write_text(
        "LANG=en_US.UTF-8\n", encoding="utf-8")
    katalogverzeichnis = tmp_path / "locale"
    _katalog(katalogverzeichnis, "de")
    monkeypatch.setenv(region.LOCALEDIR_ENV, str(katalogverzeichnis))
    _erzeugt(etc, geschrieben)
    assert "de" in {s.code for s in region.available_languages()}


def test_ein_verzeichnis_unter_usr_lib_locale_zaehlt_auch(maschine, tmp_path,
                                                          monkeypatch):
    """Eine Maschine ohne locale-gen - ein Container - hat nur das."""
    etc, _zoneinfo = maschine
    (etc / "etc" / "locale.conf").write_text(
        "LANG=en_US.UTF-8\n", encoding="utf-8")
    katalogverzeichnis = tmp_path / "locale"
    _katalog(katalogverzeichnis, "de")
    monkeypatch.setenv(region.LOCALEDIR_ENV, str(katalogverzeichnis))
    # Keine locale.gen, aber das Verzeichnis ist da.
    (etc / region.LOCALE_DIRECTORY / "de_DE.utf8").mkdir(parents=True)
    assert "de" in {s.code for s in region.available_languages()}


@pytest.mark.allow_subprocess
def test_die_dateien_nennen_dieselben_sprachumgebungen_wie_locale_a(
        monkeypatch):
    """Der Beleg fuer die Behauptung bei generated_locales().

    Er ist der Grund, aus dem hier Dateien gelesen werden DUERFEN statt
    `locale -a`: fuer die Sprachen, um die es geht, sagen beide
    dasselbe. `locale -a` LIEST nur und aendert nichts.

    Verglichen werden ausschliesslich die Sprachumgebungen aus
    region.LANGUAGES. C, C.utf8 und POSIX stehen in keiner locale.gen
    und sind auch keine Sprache, in der diese Oberflaeche sprechen kann
    - sie hier zu verlangen hiesse, eine Uebereinstimmung zu fordern,
    die es nie gab.
    """
    monkeypatch.delenv(region.ETC_ROOT_ENV, raising=False)
    fertig = subprocess.run(["locale", "-a"], capture_output=True, text=True)
    if fertig.returncode != 0:
        pytest.skip("`locale -a` laeuft auf dieser Maschine nicht")
    von_glibc = {eintrag.lower().replace("-", "")
                 for eintrag in fertig.stdout.split()}
    aus_dateien = region.generated_locales()
    for sprache in region.LANGUAGES:
        name = sprache.locale.lower().replace("-", "")
        assert (name in von_glibc) == (name in aus_dateien), (
            f"{sprache.locale}: `locale -a` sagt "
            f"{name in von_glibc}, die Dateien sagen {name in aus_dateien}")


# --------------------------------------------------------------------
# Die Zonenliste
# --------------------------------------------------------------------

def test_die_zonenliste_liest_zonen_und_verweise_und_sonst_nichts(maschine):
    """Z-Zeilen tragen den Namen an zweiter, L-Zeilen an dritter Stelle.

    Das ist die ganze Form der Datei, und die zwei Faelle sind der
    Grund, aus dem eine naive Auslese ("nimm das zweite Feld") 257 von
    598 Namen falsch ausliest: bei einem Verweis steht dort das ZIEL.
    """
    _etc, zoneinfo = maschine
    (zoneinfo / region.ZONE_FILE).write_text(
        "# ein Kommentar\n"
        "R d 1916 o - Ap 30 23s 1 S\n"
        "Z Europe/Berlin 0:53:28 - LMT 1893 Ap\n"
        "Z America/New_York -4:56:2 - LMT 1883 N 18 17u\n"
        "L Europe/Berlin Europe/Busingen\n"
        "L America/New_York US/Eastern\n",
        encoding="utf-8")
    assert region.timezones() == [
        "America/New_York", "Europe/Berlin", "Europe/Busingen",
        "US/Eastern"]


def test_ohne_datenbank_bleibt_die_liste_leer_statt_zu_werfen(maschine):
    assert region.timezones() == []


def test_diese_maschine_nennt_wirklich_zonen():
    """Die positive Gegenprobe, an der ECHTEN Datenbank.

    Ohne sie gingen alle Pruefungen darueber auch auf einem Baum durch,
    auf dem timezones() immer eine leere Liste gibt.
    """
    if not (region.ZONEINFO / region.ZONE_FILE).is_file():
        pytest.skip(f"{region.ZONE_FILE} liegt nicht auf dieser Maschine")
    echte = region.timezones()
    assert len(echte) > 100, f"nur {len(echte)} Zonen"
    assert "UTC" in echte
    assert echte == sorted(echte)


@pytest.mark.allow_subprocess
def test_die_datei_nennt_genau_das_was_timedatectl_nennt():
    """Der Beleg fuer die Behauptung im Kopf von region.ZONE_FILE.

    Er ist der Grund, aus dem hier eine Datei gelesen werden DARF statt
    eines Befehls: waeren es zwei verschiedene Listen, boete die
    Oberflaeche Namen an, die der Setzbefehl danach ablehnt. Der Befehl
    LIEST nur - `set-timezone` laeuft in dieser Datei nie.
    """
    if not region.can_set_timezone():
        pytest.skip("timedatectl liegt nicht auf dieser Maschine")
    if not (region.ZONEINFO / region.ZONE_FILE).is_file():
        pytest.skip(f"{region.ZONE_FILE} liegt nicht auf dieser Maschine")
    fertig = subprocess.run(list(region.ZONE_LISTING),
                            capture_output=True, text=True, check=True)
    vom_befehl = sorted(zeile.strip() for zeile in fertig.stdout.splitlines()
                        if zeile.strip())
    assert region.timezones() == vom_befehl


def test_die_zonen_dieser_maschine_sind_auch_in_der_datenbank(monkeypatch):
    """Was die Liste nennt, muss known_timezone() auch annehmen - sonst
    lehnte der Setzbefehl ab, was die Liste anbietet."""
    monkeypatch.delenv(region.ZONEINFO_VARIABLE, raising=False)
    if not (region.ZONEINFO / region.ZONE_FILE).is_file():
        pytest.skip(f"{region.ZONE_FILE} liegt nicht auf dieser Maschine")
    unbekannt = [zone for zone in region.timezones()
                 if not region.known_timezone(zone)]
    assert unbekannt == []
