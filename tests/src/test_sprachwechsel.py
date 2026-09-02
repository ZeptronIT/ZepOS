# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Sprachwechsel der Oberflaeche - ausgefuehrt, nicht durchsucht.

WOFUER DIESE DATEI DA IST
    Der Nutzer am 02.09.2026: "man muss in den einstellungen auch die
    sprache wechseln koennen". Eine Umschaltung, die einen Wert
    schreibt, ist keine Umschaltung - erst eine, die den Katalog
    wirklich wechselt, ist eine. Und dazwischen liegt in diesem System
    genau eine Frage, die sich nicht durch Lesen beantworten laesst:

        Woher nimmt die laufende Schale ihre Sprache - aus der DATEI,
        die das Einstellungsfenster gerade beschrieben hat, oder aus der
        UMGEBUNG, die eine Abschrift dieser Datei von der Anmeldung ist?

    Deshalb baut diese Datei die erzeugte utils/i18n.ts, buendelt sie
    mit `ags bundle` wie eine Installation es tut, und laesst sie in
    gjs laufen - mit einer /etc/locale.conf, die etwas ANDERES sagt als
    LANG. Wer die Umgebung liest, gibt hier die falsche Antwort.

WARUM `ags bundle` UND NICHT `ags run`
    Aus demselben Grund wie in tests/src/test_bar_headless.py: bundle
    liest Dateien und schreibt eine Datei, es fasst die laufende Sitzung
    des Menschen davor nicht an.

WAS HIER NIE PASSIERT
    /etc anfassen. Jede Sprachumgebung, jede locale.conf und jeder
    Katalog dieses Laufs liegen in tmp_path, und die Vorsatzwurzel
    ZEPOS_ETC_ROOT ist der Weg dorthin - dieselbe Vorrichtung, die
    src/region.py und src/bin/zepos-greeter benutzen. `localectl` laeuft
    hier nicht.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[2]
SRC = WURZEL / "src"

sys.path.insert(0, str(WURZEL))
from tests.gtk4_headless import (                             # noqa: E402
    broadwayd, start_broadwayd, stop_broadwayd,
)

# Diese Datei startet Prozesse, und zwar drei Sorten: msgfmt baut den
# Katalog, `ags bundle` uebersetzt die erzeugte Datei, gjs fuehrt sie
# aus. Anders geht es nicht - eine .template in TypeScript kann diese
# Suite nicht selbst ausfuehren, und "der Katalog wechselt wirklich" ist
# keine Aussage, die man einer Datei ansieht.
#
# WAS DIE DISZIPLIN DAHINTER IST (siehe den Kopf von tests/conftest.py:
# der Marker reicht die Erlaubnis an das KIND weiter)
#   * jeder Pfad, den ein Kind hier liest oder schreibt, liegt in
#     tmp_path: die Maschinenwurzel ueber ZEPOS_ETC_ROOT, der Katalog
#     ueber ZEPOS_LOCALEDIR, das Buendel und der Laufzeitordner ohnehin;
#   * kein Kind bekommt einen SETZENDEN Befehl zu sehen - `localectl`
#     und `timedatectl` kommen in dieser Datei nicht vor;
#   * das einzige, was ausserhalb gelesen wird, ist `locale -a`, und das
#     beantwortet eine Frage ueber die Maschine, ohne sie zu aendern.
pytestmark = pytest.mark.allow_subprocess

VORLAGE = SRC / "templates" / "ags-i18n.template"

# Die beiden Sprachumgebungen, um die es geht, und ein Eintrag, der in
# beiden Katalogen anders lautet.
DEUTSCH = "de_DE.UTF-8"
ENGLISCH = "en_US.UTF-8"
MSGID = "Disk space"
DEUTSCHER_TEXT = "Speicherplatz"

# Eine Sprachumgebung, die auf keiner Maschine dieses Projekts erzeugt
# ist. Sie steht hier, weil ein STILLER Fehlschlag der gefaehrlichste
# Fall ist: setlocale gibt null zurueck und aendert nichts.
FEHLENDE = "fr_FR.UTF-8"


def _vorhanden(name: str) -> bool:
    """Ist diese Sprachumgebung auf DIESER Maschine erzeugt?

    Wortgleich zu tests/render/desktop_session.py: `locale -a` schreibt
    "de_DE.utf8", die Variable will "de_DE.UTF-8" - dieselbe
    Sprachumgebung, zwei Schreibweisen. Ohne diese Frage misst ein
    roter Lauf die Maschine und nicht den Quelltext.
    """
    try:
        vorhandene = subprocess.run(["locale", "-a"], capture_output=True,
                                    text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return False
    gesucht = name.lower().replace("-", "")
    return any(eintrag.lower().replace("-", "") == gesucht
               for eintrag in vorhandene)


@pytest.fixture(scope="module")
def katalog(tmp_path_factory) -> Path:
    """Der deutsche Katalog, gebaut wie po/build.sh ihn baut."""
    if shutil.which("msgfmt") is None:
        pytest.skip("msgfmt fehlt; es kommt mit dem Paket gettext")
    ziel = tmp_path_factory.mktemp("katalog")
    lc = ziel / "de" / "LC_MESSAGES"
    lc.mkdir(parents=True)
    fertig = subprocess.run(
        ["msgfmt", "-o", str(lc / "zepos-desktop.mo"),
         str(WURZEL / "po" / "desktop" / "de.po")],
        capture_output=True, text=True)
    assert fertig.returncode == 0, fertig.stderr
    return ziel


@pytest.fixture(scope="module")
def gebuendelt(tmp_path_factory) -> Path:
    """utils/i18n.ts aus der Vorlage, gebuendelt mit einem Kind davor."""
    if shutil.which("ags") is None:
        pytest.skip("ags fehlt; es kommt mit dem Paket aylurs-gtk-shell")

    bau = tmp_path_factory.mktemp("sprachwechsel")
    ags = bau / "ags"
    (ags / "utils").mkdir(parents=True)

    sys.path.insert(0, str(SRC))
    try:
        import template_processor
        template_processor.ConfigProcessor().apply_template(
            VORLAGE, ags / "utils" / "i18n.ts")
    finally:
        sys.path.remove(str(SRC))

    shutil.copy(Path(__file__).parent / "sprachwechsel_child.tsx",
                ags / "child.tsx")

    buendel = bau / "child.js"
    fertig = subprocess.run(
        ["ags", "bundle", str(ags / "child.tsx"), str(buendel),
         "-r", str(ags), "-g", "4"],
        capture_output=True, text=True, timeout=300)
    assert fertig.returncode == 0, (
        "`ags bundle` hat das i18n-Modul nicht uebersetzt:\n"
        + fertig.stdout + fertig.stderr)
    return buendel


def _lauf(buendel: Path, tmp_path: Path, katalog: Path, *,
          lang: str, in_der_datei: str | None,
          anzeige: str | None = None) -> dict[str, str]:
    """Das Kind einmal laufen lassen und seine Zeilen einlesen.

    `lang` ist die Umgebung, `in_der_datei` das, was in
    /etc/locale.conf steht - None heisst: es gibt keine solche Datei.
    Der ganze Zweck dieser Datei ist, dass die beiden sich
    unterscheiden duerfen.
    """
    wurzel = tmp_path / "wurzel"
    (wurzel / "etc").mkdir(parents=True, exist_ok=True)
    if in_der_datei is not None:
        (wurzel / "etc" / "locale.conf").write_text(
            f"LANG={in_der_datei}\n", encoding="utf-8")

    umgebung = dict(os.environ)
    umgebung.update({
        "LANG": lang,
        "ZEPOS_ETC_ROOT": str(wurzel),
        "ZEPOS_LOCALEDIR": str(katalog),
    })
    for name in ("LC_ALL", "LC_MESSAGES", "LANGUAGE"):
        umgebung.pop(name, None)
    if anzeige is not None:
        umgebung["GDK_BACKEND"] = "broadway"
        umgebung["BROADWAY_DISPLAY"] = anzeige

    fertig = subprocess.run([str(buendel)], capture_output=True, text=True,
                            env=umgebung, timeout=120)
    assert fertig.returncode == 0, fertig.stdout + fertig.stderr
    zeilen = {}
    for zeile in fertig.stdout.splitlines():
        if "=" in zeile:
            name, _, wert = zeile.partition("=")
            zeilen[name.strip()] = wert.strip()
    assert zeilen, "das Kind hat nichts gemeldet:\n" + fertig.stdout
    return zeilen


# --------------------------------------------------------------------
# Die Frage, um die es geht: Datei oder Umgebung
# --------------------------------------------------------------------

def test_die_maschinendatei_entscheidet_und_nicht_die_geerbte_umgebung(
        gebuendelt, tmp_path, katalog):
    """Der Kern der ganzen Aufgabe, in einer Zeile Ergebnis.

    LANG sagt Deutsch, die Datei sagt Englisch - so sieht eine Sitzung
    aus, in der jemand gerade umgestellt hat und die Schale neu startet.
    Wer die Umgebung liest, bekommt "Speicherplatz" und der Nutzer
    denkt, die Einstellung tue nichts.
    """
    if not (_vorhanden(DEUTSCH) and _vorhanden(ENGLISCH)):
        pytest.skip("diese Maschine hat nicht beide Sprachumgebungen erzeugt")

    zeilen = _lauf(gebuendelt, tmp_path, katalog,
                   lang=DEUTSCH, in_der_datei=ENGLISCH)
    assert zeilen["maschine"] == ENGLISCH
    assert zeilen["katalog"] == MSGID, (
        "die Schale spricht die Sprache ihrer UMGEBUNG und nicht die der "
        "Maschine - nach einem Neustart der Schale kaeme die alte Sprache "
        "zurueck")


def test_und_umgekehrt_genauso(gebuendelt, tmp_path, katalog):
    """Die Gegenrichtung, ohne die der Test oben auch dann durchginge,
    wenn die Schale IMMER Englisch spraeche."""
    if not (_vorhanden(DEUTSCH) and _vorhanden(ENGLISCH)):
        pytest.skip("diese Maschine hat nicht beide Sprachumgebungen erzeugt")

    zeilen = _lauf(gebuendelt, tmp_path, katalog,
                   lang=ENGLISCH, in_der_datei=DEUTSCH)
    assert zeilen["maschine"] == DEUTSCH
    assert zeilen["katalog"] == DEUTSCHER_TEXT


def test_ohne_datei_gilt_die_umgebung(gebuendelt, tmp_path, katalog):
    """Ein Container hat kein /etc/locale.conf, und dann ist die
    Umgebung das einzige, was es gibt."""
    if not _vorhanden(DEUTSCH):
        pytest.skip("diese Maschine hat de_DE.UTF-8 nicht erzeugt")

    zeilen = _lauf(gebuendelt, tmp_path, katalog,
                   lang=DEUTSCH, in_der_datei=None)
    assert zeilen["maschine"] == ""
    assert zeilen["katalog"] == DEUTSCHER_TEXT


def test_eine_nicht_erzeugte_sprachumgebung_wird_nicht_behauptet(
        gebuendelt, tmp_path, katalog):
    """Der stille Fall, und der Grund, aus dem spracheAnwenden() das
    ZURUECKGIBT, was gilt, statt zu melden, es habe geklappt.

    setlocale gibt hier null zurueck und laesst alles stehen. Ein
    Aufrufer, der das nicht erfaehrt, schriebe "Sprache umgestellt" auf
    den Schirm, waehrend nichts umgestellt ist.
    """
    if not _vorhanden(DEUTSCH):
        pytest.skip("diese Maschine hat de_DE.UTF-8 nicht erzeugt")
    if _vorhanden(FEHLENDE):
        pytest.skip(f"{FEHLENDE} ist auf dieser Maschine erzeugt")

    zeilen = _lauf(gebuendelt, tmp_path, katalog,
                   lang=DEUTSCH, in_der_datei=FEHLENDE)
    assert zeilen["maschine"] == FEHLENDE, "die Datei sagt, was sie sagt"
    assert zeilen["angewandt"] != FEHLENDE, (
        "spracheAnwenden() behauptet eine Sprachumgebung, die diese "
        "Maschine nicht hat")
    assert zeilen["katalog"] == DEUTSCHER_TEXT, (
        "der Katalog hat sich auf eine Sprachumgebung umgestellt, die es "
        "nicht gibt")


def test_die_datei_wird_gelesen_und_nicht_ausgefuehrt(gebuendelt, tmp_path,
                                                      katalog):
    """/etc/locale.conf sieht aus wie ein Shell-Schnipsel und ist keines."""
    if not _vorhanden(DEUTSCH):
        pytest.skip("diese Maschine hat de_DE.UTF-8 nicht erzeugt")

    wurzel = tmp_path / "wurzel"
    (wurzel / "etc").mkdir(parents=True, exist_ok=True)
    beweis = tmp_path / "ausgefuehrt"
    (wurzel / "etc" / "locale.conf").write_text(
        f"LANG={DEUTSCH}\n$(touch {beweis})\n", encoding="utf-8")

    umgebung = dict(os.environ)
    umgebung.update({"LANG": DEUTSCH, "ZEPOS_ETC_ROOT": str(wurzel),
                     "ZEPOS_LOCALEDIR": str(katalog)})
    fertig = subprocess.run([str(gebuendelt)], capture_output=True, text=True,
                            env=umgebung, timeout=120)
    assert fertig.returncode == 0, fertig.stdout + fertig.stderr
    assert not beweis.exists()


# --------------------------------------------------------------------
# Was ein Katalogwechsel an einem GEZEICHNETEN Fenster tut
# --------------------------------------------------------------------

def test_eine_gezeichnete_beschriftung_folgt_dem_katalogwechsel_nicht(
        gebuendelt, tmp_path, katalog):
    """Die Messung, auf der das ganze Zeitmodell des Fensters ruht.

    GEMESSEN am 02.09.2026 mit gjs 1.88.1 und GTK 4.22.4, an einem
    Fenster, das present() gesehen hat und dessen get_realized() true
    meldet:

        A  vor dem Wechsel   alte Beschriftung  "Speicherplatz"
        B  nach dem Wechsel  dgettext(...)      "Disk space"
        C  nach dem Wechsel  ALTE Beschriftung  "Speicherplatz"
        D  nach dem Wechsel  NEUE Beschriftung  "Disk space"

    Und eine zweite Messung derselben Reihe, weil sie die erste
    ueberhaupt erst traegt: `nachInit`. gtk_init() galt lange als der
    Ort, an dem setlocale(LC_ALL, "") passiert - dann haette es die
    Arbeit von spracheAnwenden() aus der UMGEBUNG heraus wieder
    umgeworfen, und die Schale spraeche nach einem Neustart doch die
    alte Sprache. GEMESSEN am selben Tag mit GTK 4.22.4: tut es nicht.

    C ist der Befund: der Katalog wechselt im laufenden Prozess, aber
    eine gebaute Gtk.Label ist eine Zeichenkette, die einmal gesetzt
    wurde. Deshalb sagt das Einstellungsfenster im WORTLAUT, was sofort
    folgt (es selbst, weil es sich neu zeichnet) und was erst nach einem
    Erzeugungslauf folgt (Leiste und Dock, die einmal gebaut werden).

    Ohne diese Pruefung koennte jemand die drei Saetze im Fenster fuer
    Uebervorsicht halten und sie streichen.
    """
    if not (_vorhanden(DEUTSCH) and _vorhanden(ENGLISCH)):
        pytest.skip("diese Maschine hat nicht beide Sprachumgebungen erzeugt")
    befehl = broadwayd()
    if befehl is None:
        pytest.skip("gtk4-broadwayd fehlt; es kommt mit dem Paket gtk4")

    # Der Laufzeitordner muss KURZ sein: der Pfad eines Unix-Sockets
    # darf 108 Zeichen nicht ueberschreiten, und tmp_path von pytest ist
    # unter manchen Wurzeln schon laenger. Dieselbe Falle, die
    # tests/lock/nested_compositor.py als SUN_PATH_MAX fuehrt.
    laufzeit = tmp_path / "rt"
    laufzeit.mkdir()
    assert len(str(laufzeit / "broadway00.socket")) < 108, (
        f"der Pfad {laufzeit} ist zu lang fuer einen Unix-Socket")

    anzeige = 71
    prozess, _socket = start_broadwayd(befehl, laufzeit, anzeige)
    try:
        umgebung_extra = {"XDG_RUNTIME_DIR": str(laufzeit)}
        wurzel = tmp_path / "wurzel"
        (wurzel / "etc").mkdir(parents=True, exist_ok=True)
        (wurzel / "etc" / "locale.conf").write_text(
            f"LANG={DEUTSCH}\n", encoding="utf-8")
        umgebung = dict(os.environ)
        umgebung.update({
            "LANG": DEUTSCH,
            "ZEPOS_ETC_ROOT": str(wurzel),
            "ZEPOS_LOCALEDIR": str(katalog),
            "GDK_BACKEND": "broadway",
            "BROADWAY_DISPLAY": f":{anzeige}",
            "ZEPOS_SPRACHPROBE_FENSTER": ENGLISCH,
            **umgebung_extra,
        })
        for name in ("LC_ALL", "LC_MESSAGES", "LANGUAGE"):
            umgebung.pop(name, None)
        fertig = subprocess.run([str(gebuendelt)], capture_output=True,
                                text=True, env=umgebung, timeout=120)
    finally:
        stop_broadwayd(prozess)

    assert fertig.returncode == 0, fertig.stdout + fertig.stderr
    zeilen = {}
    for zeile in fertig.stdout.splitlines():
        if "=" in zeile:
            name, _, wert = zeile.partition("=")
            zeilen[name.strip()] = wert.strip()

    assert zeilen["nachInit"] == DEUTSCHER_TEXT, (
        "Gtk.init() hat den Katalog wieder umgeworfen - dann traegt "
        "spracheAnwenden() beim Laden des Moduls nichts, und die Schale "
        "kaeme nach einem Neustart in der Sprache ihrer Umgebung zurueck")
    assert zeilen.get("gezeichnet") == "true", (
        "das Fenster stand gar nicht - die Messung darunter saehe "
        "genauso aus, ohne etwas zu beweisen:\n" + fertig.stdout)
    assert zeilen["A"] == DEUTSCHER_TEXT
    assert zeilen["B"] == MSGID, (
        "der Katalog eines LAUFENDEN Prozesses wechselt nicht mehr - "
        "dann kann auch das Einstellungsfenster nicht sofort folgen")
    assert zeilen["C"] == DEUTSCHER_TEXT, (
        "eine schon gezeichnete Beschriftung folgt dem Katalogwechsel "
        "doch - dann sind die Saetze im Einstellungsfenster ueber "
        "»nach einem Erzeugungslauf« zu vorsichtig geworden")
    assert zeilen["D"] == MSGID
