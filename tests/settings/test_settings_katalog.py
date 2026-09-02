# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Katalog dieses Fensters - gebaut, befragt, und beim Wechsel gemessen.

WARUM HIER NICHTS "DER msgstr IST NICHT LEER" PRUEFT
    Am 02.09.2026 sind in diesem Baum acht Pruefstellen aufgefallen, die
    gruen waren und nichts gemessen haben. Bei einer Uebersetzung ist
    "der Eintrag steht im .po" genau so eine: `msgfmt` laesst einen mit
    `#, fuzzy` markierten Eintrag aus der .mo FALLEN, und der Text
    steht dann englisch da, obwohl er im Katalog uebersetzt dasteht.
    Dreimal an einem Tag passiert, bei drei verschiedenen Bearbeitern.

    Jede Zusicherung hier baut darum den Katalog mit `msgfmt` und fragt
    ihn ueber `gettext` - also auf demselben Weg, auf dem das Fenster
    ihn fragt. Was `msgfmt` fallen laesst, faellt hier auf.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
SETTINGS_ROOT = ROOT / "settings"

# Ein Katalog mit genau den Formen, die dieses Fenster braucht: ein
# gewoehnlicher Eintrag, einer mit einem Platzhalter, und einer mit
# zwei Pluralformen.
KATALOG = '''\
msgid ""
msgstr ""
"Project-Id-Version: zepos-desktop\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"Plural-Forms: nplurals=2; plural=(n != 1);\\n"

msgid "Desktop size"
msgstr "Größe des Schreibtischs"

msgid "Language {name}."
msgstr "Sprache {name}."

msgid "One entry is not shown"
msgid_plural "{count} entries are not shown"
msgstr[0] "Ein Eintrag steht nicht da"
msgstr[1] "{count} Einträge stehen nicht da"
'''


def _baue(verzeichnis: Path, sprache: str, text: str = KATALOG) -> Path:
    """Einen Katalog wirklich bauen, mit msgfmt, wie po/build.sh es tut."""
    quelle = verzeichnis / f"{sprache}.po"
    quelle.write_text(text, encoding="utf-8")
    ziel = verzeichnis / sprache / "LC_MESSAGES"
    ziel.mkdir(parents=True, exist_ok=True)
    mo = ziel / "zepos-desktop.mo"
    fertig = subprocess.run(
        ["msgfmt", "--statistics", "-o", str(mo), str(quelle)],
        capture_output=True, text=True)
    assert fertig.returncode == 0, (
        f"msgfmt scheiterte an diesem Katalog:\n{fertig.stderr}")
    # Die Statistik ist die Stelle, an der ein fuzzy-Eintrag auffliegt:
    # msgfmt zaehlt ihn getrennt und nimmt ihn NICHT in die .mo.
    assert "fuzzy" not in fertig.stderr, (
        "msgfmt meldet ungenau markierte Eintraege - sie fehlen in der "
        f".mo:\n{fertig.stderr}")
    return mo


@pytest.fixture
def i18n(monkeypatch):
    """i18n.py mit src/ auf dem Pfad, so wie der Befehl es hinlegt.

    Frisch je Test: das Modul haelt den gewaehlten Katalog in einer
    Modulvariablen, und ein liegengelassener Katalog aus dem
    vorhergehenden Test waere genau die Art Kopplung, die eine
    Zusicherung von der Reihenfolge abhaengig macht.
    """
    monkeypatch.syspath_prepend(str(SRC))
    monkeypatch.syspath_prepend(str(SETTINGS_ROOT))
    for name in [n for n in sys.modules
                 if n == "region" or n.startswith("zepos_settings_gui")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    from zepos_settings_gui import i18n as modul
    return modul


@pytest.fixture
def maschine(monkeypatch, tmp_path):
    """Eine Maschinenwurzel, deren /etc/locale.conf der TEST vorgibt."""
    wurzel = tmp_path / "maschine"
    (wurzel / "etc").mkdir(parents=True)
    monkeypatch.setenv("ZEPOS_ETC_ROOT", str(wurzel))
    return wurzel


def _locale_conf(wurzel: Path, locale: str) -> None:
    (wurzel / "etc" / "locale.conf").write_text(
        f"LANG={locale}\n", encoding="utf-8")


# ------------------------------------------------------------------ #

def test_die_domaene_ist_die_der_schale(i18n):
    """Ein Katalog, zwei Oberflaechen.

    Wortgleich zu src/region.py und src/templates/ags-i18n.template.
    Laeuft dieses Fenster auf einer eigenen Domaene, hat derselbe Satz
    zwei Eintraege - und ab dem ersten Umformulieren heisst dasselbe
    Bedienelement in der Leiste anders als hier.
    """
    import region
    assert i18n.DOMAIN == region.DOMAIN == "zepos-desktop"


@pytest.mark.allow_subprocess
def test_der_gebaute_katalog_gibt_die_uebersetzung_wirklich_heraus(
        i18n, tmp_path):
    """Gebaut mit msgfmt, befragt ueber gettext - nicht gelesen."""
    _baue(tmp_path, "de")
    assert i18n.activate("de", localedir=tmp_path) == "de"
    assert i18n._("Desktop size") == "Größe des Schreibtischs"
    assert i18n._("Language {name}.").format(name="Deutsch") == (
        "Sprache Deutsch.")


@pytest.mark.allow_subprocess
def test_der_plural_kommt_aus_dem_katalog_und_nicht_aus_einer_vorlage(
        i18n, tmp_path):
    """Wie viele Formen eine Sprache hat, entscheidet der Katalog."""
    _baue(tmp_path, "de")
    i18n.activate("de", localedir=tmp_path)
    eine = i18n.ngettext("One entry is not shown",
                         "{count} entries are not shown", 1)
    mehrere = i18n.ngettext("One entry is not shown",
                            "{count} entries are not shown", 4)
    assert eine == "Ein Eintrag steht nicht da"
    assert mehrere.format(count=4) == "4 Einträge stehen nicht da"


@pytest.mark.allow_subprocess
def test_die_sprache_kommt_aus_locale_conf_und_nicht_aus_der_umgebung(
        i18n, maschine, tmp_path, monkeypatch):
    """Die Entscheidung, ohne die ein Sprachwechsel nicht ankommt.

    Nach `localectl set-locale` ist die Umgebung dieses Prozesses eine
    ABSCHRIFT von vorher, angefertigt bei der Anmeldung. Die Datei ist
    die frische Angabe. Ein Fenster, das sich aus seiner Umgebung neu
    uebersetzt, uebersetzt sich in die alte Sprache zurueck.

    Darum steht hier BEIDES gegeneinander: die Umgebung sagt Englisch,
    die Datei sagt Deutsch. Gewinnen muss die Datei.
    """
    _baue(tmp_path, "de")
    monkeypatch.setenv("ZEPOS_LOCALEDIR", str(tmp_path))
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("LC_ALL", "en_US.UTF-8")
    monkeypatch.setenv("LANGUAGE", "en")
    _locale_conf(maschine, "de_DE.UTF-8")

    assert i18n.activate() == "de"
    assert i18n._("Desktop size") == "Größe des Schreibtischs", (
        "das Fenster hat die Sprache aus der Umgebung genommen - dann "
        "kommt ein Sprachwechsel im laufenden Fenster nie an")


@pytest.mark.allow_subprocess
def test_ein_fehlender_katalog_faellt_auf_die_quellsprache_zurueck(
        i18n, tmp_path):
    """Nicht aus, sondern auf Englisch.

    Die msgids SIND die englische Oberflaeche. Der Rueckfall ist also
    eine vollstaendige Anzeige und keine leere - und ein
    Einstellungsfenster, das an einer halb geschriebenen .mo nicht mehr
    startet, waere genau dort unbrauchbar, wo man es zum Reparieren
    braucht.
    """
    leer = tmp_path / "leer"
    leer.mkdir()
    assert i18n.activate("de", localedir=leer) == "de"
    assert i18n._("Desktop size") == "Desktop size"


@pytest.mark.allow_subprocess
def test_eine_abgeschnittene_mo_bringt_das_fenster_nicht_um(i18n, tmp_path):
    """struct.error ist kein OSError - darum steht er eigens im except.

    Der Fall ist ein unterbrochenes Schreiben, und er ist der Grund,
    aus dem installer/core/i18n.py denselben Namen nennt.

    ES WIRD GEPRUEFT, DASS DIESER TEST DEN RICHTIGEN ZWEIG TRIFFT.
    Eine abgeschnittene Datei, die gar nicht dort liegt, wo gesucht
    wird, faellt aus demselben Grund auf Englisch zurueck wie eine, die
    fehlt - und meldete dann "sauber", ohne den Zweig je zu beruehren.
    Darum steht die Gegenprobe daneben: die VOLLSTAENDIGE Datei in
    derselben Anordnung muss uebersetzen.

    UND SIE STEHT IN EINEM ANDEREN VERZEICHNIS, WEIL gettext SICH DEN
    KATALOG AM PFAD MERKT. GEMESSEN am 02.09.2026:

        mo schreiben (ganz)   -> translation() -> "Größe des ..."
        dieselbe mo kuerzen   -> translation() -> "Größe des ..."
        gettext._translations  {(GNUTranslations, '<pfad>'): ...}

    Der Zwischenspeicher haengt an (Klasse, absoluter Pfad) und prueft
    die Aenderungszeit NICHT. Beide Haelften im selben Verzeichnis
    haetten also gemessen, dass gettext einen Zwischenspeicher hat -
    und nicht, was eine kaputte Datei bewirkt.

    Fuer das Fenster ist derselbe Umstand harmlos: ein Sprachwechsel
    liest eine ANDERE Datei (de/... statt en/...), also nie die
    zwischengespeicherte. Ein Katalog, der sich unter einem laufenden
    Prozess AENDERT, kaeme dort allerdings nicht an - das steht auch im
    Kopf von settings/zepos_settings_gui/i18n.py.
    """
    ganz = tmp_path / "ganz"
    ganz.mkdir()
    roh = _baue(ganz, "de").read_bytes()

    # Gegenprobe: diese Anordnung wird wirklich gelesen.
    heil = tmp_path / "heil" / "de" / "LC_MESSAGES"
    heil.mkdir(parents=True)
    (heil / "zepos-desktop.mo").write_bytes(roh)
    assert i18n.activate("de", localedir=tmp_path / "heil") == "de"
    assert i18n._("Desktop size") == "Größe des Schreibtischs", (
        "der Katalog wird in dieser Anordnung gar nicht gelesen - dann "
        "misst der Rest dieser Pruefung nichts")

    # Dieselbe Datei, mitten im Schreiben abgebrochen, an einem
    # Pfad, den gettext noch nicht gesehen hat.
    kaputt = tmp_path / "kaputt" / "de" / "LC_MESSAGES"
    kaputt.mkdir(parents=True)
    (kaputt / "zepos-desktop.mo").write_bytes(roh[:len(roh) // 3])
    assert i18n.activate("de", localedir=tmp_path / "kaputt") == "de"
    assert i18n._("Desktop size") == "Desktop size"


@pytest.mark.allow_subprocess
def test_eine_marke_gibt_ihren_text_unveraendert_zurueck(i18n, tmp_path):
    """N_() uebersetzt NICHT, und das ist ihr ganzer Zweck."""
    _baue(tmp_path, "de")
    i18n.activate("de", localedir=tmp_path)
    assert i18n.N_("Desktop size") == "Desktop size"
    # Und an der Senke wird daraus die Uebersetzung.
    assert i18n._(i18n.N_("Desktop size")) == "Größe des Schreibtischs"


@pytest.mark.allow_subprocess
def test_eine_gebackene_konstante_folgt_dem_wechsel_nicht(i18n, tmp_path):
    """Die Messung, die N_() ueberhaupt begruendet.

    Sie steht als Zusicherung und nicht als Kommentar, weil sie sonst
    beim naechsten Umbau von model.py stillschweigend falsch wird: wer
    dort `LABEL = _("...")` schreibt, hat eine Beschriftung gebaut, die
    fuer immer in der Sprache steht, die beim Programmstart galt - und
    nichts sagt es ihm.
    """
    _baue(tmp_path, "de")

    # Vor der Umschaltung: die Quellsprache.
    i18n.activate("en", localedir=tmp_path)
    gebacken = i18n._("Desktop size")
    markiert = i18n.N_("Desktop size")

    # Umschalten, so wie das Fenster es nach einem Sprachwechsel tut.
    i18n.activate("de", localedir=tmp_path)

    assert gebacken == "Desktop size", (
        "eine beim Import gebackene Beschriftung hat sich veraendert - "
        "dann ist diese Messung ueberholt und N_() vielleicht unnoetig")
    assert i18n._(markiert) == "Größe des Schreibtischs", (
        "die Marke an der Senke folgt dem Wechsel nicht - dann ist der "
        "ganze Entwurf falsch")


@pytest.mark.allow_subprocess
def test_der_wechsel_im_laufenden_prozess_geht_in_beide_richtungen(
        i18n, tmp_path):
    """Zurueck auf Englisch muss genauso ankommen wie hin auf Deutsch.

    Eine Umschaltung, die nur in eine Richtung wirkt, ist die Falle,
    in der ein Nutzer die Sprache nicht mehr zuruecknehmen kann - und
    das ist die Sackgasse, in der er das Fenster nicht mehr lesen kann,
    mit dem er sie zuruecknimmt.
    """
    _baue(tmp_path, "de")
    i18n.activate("de", localedir=tmp_path)
    assert i18n._("Desktop size") == "Größe des Schreibtischs"
    i18n.activate("en", localedir=tmp_path)
    assert i18n._("Desktop size") == "Desktop size"
    i18n.activate("de", localedir=tmp_path)
    assert i18n._("Desktop size") == "Größe des Schreibtischs"
