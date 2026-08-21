# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Schreibweg des Rechtsklick-Menues: eine Anheftung, die ankommt.

WAS HIER GEMESSEN WIRD, UND WARUM MIT EINEM UEBERSETZTEN PROGRAMM
    tests/render/test_launcher_menue.py zeigt, dass das Menue aufgeht
    und den Punkt traegt. Es zeigt NICHT, dass der Punkt etwas bewirkt -
    ein Mausklick laesst sich in jene Sitzung nicht schieben.

    Diese Datei schliesst die Luecke von der anderen Seite: sie
    uebersetzt den ECHTEN Leser und Schreiber - AppDiscovery.cpp aus
    dem gepatchten Baum - und laesst ihn gegen die ECHTE Bruecke laufen.
    Danach wird nicht die Antwort des Programms geglaubt, sondern
    nachgesehen, was in der Einstellungsdatei steht und was apps.pinned()
    daraus macht: genau die Funktion, aus der das Dock seine Symbole
    bekommt.

    Ohne diesen Schritt waere die Kette eine Vermutung. Ein Menuepunkt,
    der sauber aufklappt und dessen Schreibvorgang nirgends ankommt,
    sieht in jeder Oberflaechenpruefung richtig aus.

DIE PRUEFUNG, DIE HIER AM MEISTEN WERT IST
    test_ein_fehlgeschlagener_lesevorgang_schreibt_nichts. Die
    Anheftungsliste ist eine ERSATZliste - wer sie schreibt, ohne sie
    vorher gelesen zu haben, loescht dem Nutzer jedes Symbol, das er je
    angeheftet hat. AppDiscovery::pinToDock() bricht deshalb ab, wenn
    die Bruecke nicht antwortet, und diese Datei haelt das fest.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.adopted_plugin_source import plugin_source              # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

# Die Sonde. Sie ruft genau die sieben oeffentlichen Funktionen, die das
# Menue ruft, und sonst nichts - AppDiscovery wird NICHT gebaut, weil
# alle sieben statisch sind (der Kopf von AppDiscovery.hpp begruendet
# das).
#
# DER PFAD ZU settings.py IST DAS ZWEITE ARGUMENT, seit dem 21.08.2026:
# das Programm bekommt ihn aus der erzeugten Datei
# (~/.config/hyprlaunch/config, settings_script), und dieser Lauf zeigt
# ihn auf src/settings.py DIESES Checkouts. Damit misst er den echten
# Schreibweg gegen den echten Rechner und nicht gegen einen Nachbau.
_SONDE = r"""
#include "hyprlaunch/AppDiscovery.hpp"
#include <cstdio>
#include <string>

int main(int argc, char** argv) {
    if (argc < 3) return 2;
    const std::string befehl = argv[1];
    const std::string script = argv[2];
    const std::string wert = argc > 3 ? argv[3] : "";

    if (befehl == "name") {
        std::printf("%s\n", hyprlaunch::AppDiscovery::pinName(wert).c_str());
        return 0;
    }
    if (befehl == "dock" || befehl == "home") {
        const auto liste = befehl == "dock"
            ? hyprlaunch::AppDiscovery::dockPins(script)
            : hyprlaunch::AppDiscovery::homeNames(script);
        if (!liste) { std::printf("<keine antwort>\n"); return 0; }
        for (const auto& name : *liste) std::printf("%s\n", name.c_str());
        return 0;
    }

    std::vector<std::string> klagen;
    if (befehl == "pin")        klagen = hyprlaunch::AppDiscovery::pinToDock(script, wert);
    else if (befehl == "unpin") klagen = hyprlaunch::AppDiscovery::unpinFromDock(script, wert);
    else if (befehl == "aufs-home")  klagen = hyprlaunch::AppDiscovery::addToHome(script, wert);
    else if (befehl == "vom-home")   klagen = hyprlaunch::AppDiscovery::removeFromHome(script, wert);
    else return 2;

    if (klagen.empty()) { std::printf("ok\n"); return 0; }
    for (const auto& klage : klagen) std::printf("klage: %s\n", klage.c_str());
    return 1;
}
"""


# ---------------------------------------------------------------------
# Aufbau
# ---------------------------------------------------------------------

def _pakete() -> tuple[list[str], list[str]]:
    namen = ["gio-unix-2.0", "json-glib-1.0"]
    cflags = subprocess.run(["pkg-config", "--cflags", *namen],
                            capture_output=True, text=True, check=True)
    libs = subprocess.run(["pkg-config", "--libs", *namen],
                          capture_output=True, text=True, check=True)
    return cflags.stdout.split(), libs.stdout.split()


def _installierte_anwendung() -> str:
    """Die Kennung eines .desktop-Eintrags, den es hier wirklich gibt.

    NICHT "firefox.desktop" hingeschrieben. settings.bar_order()
    verwirft einen Namen ohne Anwendungseintrag auf dieser Maschine und
    nennt ihn "auf dieser Maschine nicht installiert" - eine
    abgeschriebene Kennung machte diesen Lauf davon abhaengig, was
    zufaellig installiert ist.
    """
    for ort in (Path("/usr/share/applications"),
                Path.home() / ".local/share/applications"):
        if not ort.is_dir():
            continue
        for eintrag in sorted(ort.glob("*.desktop")):
            text = eintrag.read_text(encoding="utf-8", errors="replace")
            if "NoDisplay=true" in text or "Type=Application" not in text:
                continue
            return eintrag.name
    pytest.skip("auf dieser Maschine liegt kein .desktop-Eintrag, an dem "
                "sich eine Anheftung messen liesse")


@pytest.fixture(scope="module")
def sonde(tmp_path_factory) -> Path:
    if shutil.which("pkg-config") is None:
        pytest.skip("pkg-config fehlt")
    uebersetzer = shutil.which("g++") or shutil.which("c++")
    if uebersetzer is None:
        pytest.skip("kein C++-Uebersetzer - der echte Schreiber ist nicht baubar")
    if subprocess.run(["pkg-config", "--exists", "json-glib-1.0"]).returncode != 0:
        pytest.skip("json-glib fehlt - dieselbe Abhaengigkeit, die "
                    "packaging/zepos-hyprlaunch/PKGBUILD anmeldet")

    quelle = plugin_source("hyprlaunch")
    bau = tmp_path_factory.mktemp("launcher-pin")
    datei = bau / "sonde.cpp"
    datei.write_text(_SONDE, encoding="utf-8")
    cflags, libs = _pakete()
    ziel = bau / "sonde"

    ergebnis = subprocess.run(
        [uebersetzer, "-std=c++23", "-I", str(quelle / "include"), *cflags,
         str(datei), str(quelle / "src" / "AppDiscovery.cpp"), *libs,
         "-o", str(ziel)],
        capture_output=True, text=True, timeout=600)
    assert ergebnis.returncode == 0, (
        "der echte Anheft-Code uebersetzt nicht:\n" + ergebnis.stderr)
    return ziel


@pytest.fixture
def stube(tmp_path) -> dict:
    """Ein Heim, in dem diese Sonde schreiben darf.

    NIE das Heim des Nutzers. Diese Sonde SCHREIBT, und ein vergessenes
    HOME schriebe in die user-settings.json der laufenden Sitzung.

    KEINE ATTRAPPE MEHR, SEIT DEM 21.08.2026: hier stand ein Skript
    namens `zepos-settings-gui` auf PATH, weil das Programm diesen
    Befehl rief. Es ruft jetzt `python3 <settings.py>` mit einem Pfad,
    den es uebergeben bekommt - also braucht dieser Lauf keinen PATH
    mehr zu praeparieren, sondern nur den Pfad hinzureichen. Ein
    Schreibweg, der nichts auf dem PATH sucht, kann auch nichts
    Falsches darauf finden.
    """
    heim = tmp_path / "heim"
    (heim / ".config").mkdir(parents=True)

    umgebung = dict(os.environ)
    umgebung["HOME"] = str(heim)
    umgebung["XDG_CONFIG_HOME"] = str(heim / ".config")
    # Die AUSLIEFERUNG dieses Checkouts, damit settings.py weiss, was
    # ZepOS mitbringt - dieselbe Wurzel, die der Generator durchreicht.
    umgebung["ZEPOS_SYSTEM_ROOT"] = str(SRC)
    return {"heim": heim, "env": umgebung,
            "skript": str(SRC / "settings.py")}


def _ruf(sonde: Path, stube: dict, befehl: str,
         *argumente: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(sonde), befehl, stube["skript"], *argumente],
                          env=stube["env"], capture_output=True, text=True,
                          timeout=120)


def _dokument(stube: dict) -> dict:
    datei = stube["heim"] / ".config" / "zepos" / "user-settings.json"
    if not datei.is_file():
        return {}
    return json.loads(datei.read_text(encoding="utf-8"))


def _gespeichert(stube: dict) -> list | None:
    return _dokument(stube).get("bar", {}).get("dock_pins")


def _auf_dem_home(stube: dict) -> list | None:
    icons = _dokument(stube).get("home", {}).get("icons")
    return None if icons is None else [icon["name"] for icon in icons]


# ---------------------------------------------------------------------
# Die Messungen
# ---------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_die_kennung_verliert_ihre_endung(sonde, stube):
    """"firefox.desktop" -> "firefox".

    Der Fuss setzt die Endung wieder an (ags-dock.template, entryFor(),
    `${program}.desktop`). Bliebe sie stehen, entstuende dort
    "firefox.desktop.desktop" - eine Anheftung, die geschrieben wird und
    nie einen Knopf bekommt.
    """
    assert _ruf(sonde, stube, "name", "firefox.desktop").stdout.strip() == "firefox"
    # Ohne Endung bleibt sie, wie sie ist - nicht die letzte Silbe weg.
    assert _ruf(sonde, stube, "name", "firefox").stdout.strip() == "firefox"
    # Und eine Kennung, die nur SO heisst, wird nicht geleert.
    assert _ruf(sonde, stube, "name", ".desktop").stdout.strip() == ".desktop"


@pytest.mark.allow_subprocess
def test_eine_anheftung_landet_in_der_einstellungsdatei(sonde, stube):
    """Der Punkt, den das Menue anbietet - und was er wirklich tut."""
    kennung = _installierte_anwendung()
    name = kennung[:-len(".desktop")]

    assert _gespeichert(stube) is None, "die Stube ist nicht leer"

    ergebnis = _ruf(sonde, stube, "pin", kennung)
    assert ergebnis.returncode == 0, (
        f"das Anheften ist gescheitert:\n{ergebnis.stdout}{ergebnis.stderr}")

    gespeichert = _gespeichert(stube)
    assert gespeichert is not None, (
        "nach dem Anheften steht in user-settings.json keine Liste")
    assert name in gespeichert, (
        f"{name!r} steht nicht in {gespeichert!r}")


@pytest.mark.allow_subprocess
def test_die_vorgabe_wird_mitgeschrieben(sonde, stube):
    """dock_baseline geht MIT hinaus, und der Starter schickt es nicht.

    Der Kopf bei BAR_BASELINE in src/settings.py fuehrt aus, woran das
    haengt. Es ist genau der Grund, aus dem der Schreibweg seit dem
    21.08.2026 ein Unterbefehl ist und keine Zeile beim Aufrufer: der
    Starter weiss von der Vorgabe nichts und muss es nicht.
    """
    assert _ruf(sonde, stube, "pin", _installierte_anwendung()).returncode == 0
    assert "dock_baseline" in _dokument(stube)["bar"], _dokument(stube)


@pytest.mark.allow_subprocess
def test_die_anheftung_kommt_beim_dock_an(sonde, stube):
    """Nicht die Datei, sondern der Weg, den das DOCK nimmt.

    apps.pinned() ist die Funktion, aus der die Symbolreihe des Fusses
    entsteht (src/apps.py, `filter`). Was sie nicht zurueckgibt, steht
    nicht im Dock - egal, was in der Datei steht.
    """
    kennung = _installierte_anwendung()
    name = kennung[:-len(".desktop")]

    assert _ruf(sonde, stube, "pin", kennung).returncode == 0

    lesen = subprocess.run(
        [sys.executable, "-c",
         "import sys, json; sys.path.insert(0, %r)\n"
         "import apps\n"
         "namen, verworfen = apps.pinned(apps.user_document(), None)\n"
         "print(json.dumps({'namen': namen, 'verworfen': verworfen}))"
         % str(SRC)],
        env=stube["env"], capture_output=True, text=True, timeout=120)
    assert lesen.returncode == 0, lesen.stderr
    antwort = json.loads(lesen.stdout.strip().splitlines()[-1])

    assert name in antwort["namen"], (
        f"das Dock bekaeme {name!r} nicht zu sehen: {antwort!r}. Die "
        f"Anheftung steht in der Datei und faellt auf dem Weg zum Fuss "
        f"wieder heraus.")


@pytest.mark.allow_subprocess
def test_zweimal_anheften_haengt_nichts_doppelt_an(sonde, stube):
    """Das Menue bietet den Punkt bei einer angehefteten Anwendung gar
    nicht mehr an - es schlaegt in die Gegenrichtung um. Zwei Starter
    nebeneinander koennen es trotzdem beide, und ein Symbol, das zweimal
    im Fuss steht, waere die Folge."""
    kennung = _installierte_anwendung()
    name = kennung[:-len(".desktop")]

    assert _ruf(sonde, stube, "pin", kennung).returncode == 0
    assert _ruf(sonde, stube, "pin", kennung).returncode == 0

    gespeichert = _gespeichert(stube) or []
    assert gespeichert.count(name) == 1, (
        f"{name!r} steht mehrfach in {gespeichert!r}")


@pytest.mark.allow_subprocess
def test_abnehmen_nimmt_denselben_namen_wieder_weg(sonde, stube):
    kennung = _installierte_anwendung()
    name = kennung[:-len(".desktop")]

    assert _ruf(sonde, stube, "pin", kennung).returncode == 0
    assert name in (_gespeichert(stube) or [])

    assert _ruf(sonde, stube, "unpin", kennung).returncode == 0
    assert name not in (_gespeichert(stube) or []), (
        "das Abnehmen hat den Namen nicht entfernt")


# ---------------------------------------------------------------------
# Das Home - die zweite Haelfte, seit dem 21.08.2026
# ---------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_der_starter_legt_eine_anwendung_aufs_home(sonde, stube):
    """GEMELDET, woertlich: "auch im ags launcher bzw hyprlauncher kann
    ich nicht mit rechtsklick zu home hinzufügen".

    Geschrieben wird ueber `settings.py home add` - denselben
    Unterbefehl, den das Home selbst und der Fuss rufen.
    """
    kennung = _installierte_anwendung()
    name = kennung[:-len(".desktop")]

    assert _ruf(sonde, stube, "aufs-home", kennung).returncode == 0
    assert name in (_auf_dem_home(stube) or []), _dokument(stube)


@pytest.mark.allow_subprocess
def test_aufs_home_legen_fasst_die_anheftungen_nicht_an(sonde, stube):
    """Zwei getrennte Auswahlen - das ist die Begruendung des Nutzers:
    "weil ich nicht jedes icon auf der dock oder auf dem home haben
    will"."""
    kennung = _installierte_anwendung()
    assert _ruf(sonde, stube, "aufs-home", kennung).returncode == 0
    assert _dokument(stube).get("bar", {}).get("dock_pins") is None, (
        "das Ablegen auf dem Home hat die Anheftungen angefasst: "
        + str(_dokument(stube).get("bar")))


@pytest.mark.allow_subprocess
def test_vom_home_nehmen_nimmt_denselben_namen_wieder_weg(sonde, stube):
    kennung = _installierte_anwendung()
    name = kennung[:-len(".desktop")]

    assert _ruf(sonde, stube, "aufs-home", kennung).returncode == 0
    assert name in (_auf_dem_home(stube) or [])

    assert _ruf(sonde, stube, "vom-home", kennung).returncode == 0
    assert name not in (_auf_dem_home(stube) or []), _dokument(stube)


@pytest.mark.allow_subprocess
def test_beide_listen_kommen_zurueck_und_sind_verschieden(sonde, stube):
    """Woran die RICHTUNG der zwei Menuepunkte haengt.

    Das Menue fragt beide Listen und entscheidet daran, ob es "Zum ...
    hinzufuegen" oder "Vom ... entfernen" zeigt. Faende es dieselbe
    Liste zweimal, zeigte einer der beiden Punkte immer in die falsche
    Richtung.
    """
    kennung = _installierte_anwendung()
    name = kennung[:-len(".desktop")]

    assert _ruf(sonde, stube, "pin", kennung).returncode == 0
    dock = _ruf(sonde, stube, "dock").stdout.split()
    home = _ruf(sonde, stube, "home").stdout.split()
    assert name in dock, dock
    assert name not in home, (
        f"{name!r} liegt auf dem Home, obwohl es nur angeheftet wurde: "
        f"{home}")


# ---------------------------------------------------------------------
# Wenn settings.py nicht antwortet
# ---------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_ein_fehlgeschlagener_schreibvorgang_aendert_nichts(sonde, stube):
    """DIE Pruefung dieser Datei.

    "bar.dock_pins" ist eine ERSATZliste: was darinsteht, steht im Dock,
    und was nicht darinsteht, steht nicht darin. Wer sie schreibt, ohne
    sie vorher gelesen zu haben, schreibt eine Liste aus einem einzigen
    Namen - und jedes Symbol, das der Nutzer je angeheftet hat, ist weg.

    SEIT DEM 21.08.2026 KANN DIESES PROGRAMM DIESEN FEHLER NICHT MEHR
    MACHEN, und das ist der Grund, aus dem der Schreibweg ein
    Unterbefehl geworden ist: es liest gar nicht mehr, um zu schreiben -
    `settings.py dock add` liest, rechnet und schreibt in einem Prozess.
    Gemessen wird trotzdem weiter, und zwar von der anderen Seite: geht
    der Aufruf schief, muss die Datei unveraendert dastehen.
    """
    kennung = _installierte_anwendung()

    # Erst eine echte Anheftung, damit es etwas zu verlieren gibt.
    assert _ruf(sonde, stube, "pin", kennung).returncode == 0
    vorher = _dokument(stube)
    assert vorher.get("bar", {}).get("dock_pins"), (
        "der Aufbau dieser Pruefung hat nichts angeheftet")

    blind = dict(stube, skript=str(stube["heim"] / "gibt-es-nicht.py"))
    ergebnis = _ruf(sonde, blind, "pin", "etwas-anderes.desktop")
    assert ergebnis.returncode != 0, (
        "das Anheften meldet Erfolg, obwohl settings.py fehlt:\n"
        + ergebnis.stdout)
    assert "klage:" in ergebnis.stdout, (
        f"es kommt keine Begruendung zurueck: {ergebnis.stdout!r}")

    assert _dokument(stube) == vorher, (
        "ein fehlgeschlagener Aufruf hat die Datei veraendert. Genau so "
        "verliert ein Nutzer sein Dock.")


@pytest.mark.allow_subprocess
def test_ohne_settings_py_ist_die_antwort_nichts_und_nicht_leer(sonde, stube):
    """`<keine antwort>` und nicht die leere Liste.

    Die beiden auseinanderzuhalten ist der ganze Zweck des
    Rueckgabetyps: eine leere Liste heisst "der Nutzer hat nichts
    angeheftet", nichts heisst "die Frage ist unbeantwortet". Das Menue
    bietet im zweiten Fall GAR KEINEN Punkt an - einer, der in die
    falsche Richtung zeigt, waere schlimmer als keiner.
    """
    blind = dict(stube, skript=str(stube["heim"] / "gibt-es-nicht.py"))
    for befehl in ("dock", "home"):
        ergebnis = _ruf(sonde, blind, befehl)
        assert ergebnis.stdout.strip() == "<keine antwort>", (
            f"ohne settings.py meldet {befehl} etwas anderes als nichts: "
            f"{ergebnis.stdout!r}")


# ---------------------------------------------------------------------
# Was die erzeugte Datei tragen muss
# ---------------------------------------------------------------------

def test_die_erzeugte_datei_traegt_drei_verschiedene_zeichen():
    """Drei Menuepunkte, drei Zeichen - und keines zweimal.

    Das Menue des Starters traegt hoechstens zwei Punkte gleichzeitig
    (einen fuer den Fuss, einen fuer das Home), und sein Zeichen nennt
    das ZIEL. Zwei gleiche Zeichen mit zwei Wirkungen in einem Menue
    sind ein Bedienfehler mit Ansage - der Kopf von
    src/templates/ags-dock.template schreibt die Regel auf, und der
    Starter faellt nicht darunter heraus, nur weil er in C++
    geschrieben ist.

    GEPRUEFT wird gegen die Zeichenquelle und nicht gegen abgeschriebene
    Glyphen: src/icon_definition.py ist die eine Stelle, an der ein
    Zeichen getippt wird.
    """
    vorlage = (SRC / "templates" / "hyprlaunch-config.template").read_text(
        encoding="utf-8")
    namen = ["ICON_PIN", "ICON_MINUS", "ICON_COMPUTER"]
    for name in namen:
        assert "{{%s}}" % name in vorlage, (
            f"{name} steht nicht in hyprlaunch-config.template")

    sys.path.insert(0, str(SRC))
    import icons_db
    zeichen = [icons_db.icons[name] for name in namen]
    assert len(set(zeichen)) == 3, (
        f"zwei der drei Menuezeichen sind dasselbe: {zeichen!r}")


def test_die_erzeugte_datei_sagt_wo_settings_py_liegt():
    """Ohne diesen Schluessel schriebe der Starter nirgendwohin.

    Ein uebersetztes Programm kann nicht wissen, aus welchem Paket es
    stammt - genau die Frage, die src/template_processor.py mit
    {{ZEPOS_SYSTEM_ROOT}} beantwortet. Ein Bau aus einem Checkout
    bekommt den Checkout, ein Paket das Paket.
    """
    vorlage = (SRC / "templates" / "hyprlaunch-config.template").read_text(
        encoding="utf-8")
    assert 'settings_script = "{{ZEPOS_SYSTEM_ROOT}}/settings.py"' in vorlage, (
        "hyprlaunch-config.template sagt dem Starter nicht, wo settings.py "
        "liegt")
