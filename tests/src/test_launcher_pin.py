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

# Die Sonde. Sie ruft genau die vier oeffentlichen Funktionen, die das
# Menue ruft, und sonst nichts - AppDiscovery wird NICHT gebaut, weil
# alle vier statisch sind (der Kopf von AppDiscovery.hpp begruendet das).
_SONDE = r"""
#include "hyprlaunch/AppDiscovery.hpp"
#include <cstdio>
#include <string>

int main(int argc, char** argv) {
    if (argc < 2) return 2;
    const std::string befehl = argv[1];
    const std::string wert = argc > 2 ? argv[2] : "";

    if (befehl == "name") {
        std::printf("%s\n", hyprlaunch::AppDiscovery::pinName(wert).c_str());
        return 0;
    }
    if (befehl == "list") {
        const auto pins = hyprlaunch::AppDiscovery::dockPins();
        if (!pins) { std::printf("<keine antwort>\n"); return 0; }
        for (const auto& name : *pins) std::printf("%s\n", name.c_str());
        return 0;
    }
    if (befehl == "pin" || befehl == "unpin") {
        const auto klagen = befehl == "pin"
            ? hyprlaunch::AppDiscovery::pinToDock(wert)
            : hyprlaunch::AppDiscovery::unpinFromDock(wert);
        if (klagen.empty()) { std::printf("ok\n"); return 0; }
        for (const auto& klage : klagen) std::printf("klage: %s\n", klage.c_str());
        return 1;
    }
    return 2;
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
    """Ein Heim mit einem `zepos-settings-gui` auf PATH, das dorthin zeigt.

    NIE das Heim des Nutzers. Diese Sonde SCHREIBT, und ein vergessenes
    HOME schriebe in die user-settings.json der laufenden Sitzung.
    """
    heim = tmp_path / "heim"
    (heim / ".config").mkdir(parents=True)

    python = ROOT / ".venv" / "bin" / "python"
    if not python.exists():
        python = Path(sys.executable)

    binz = tmp_path / "bin"
    binz.mkdir()
    skript = binz / "zepos-settings-gui"
    skript.write_text(
        "#!/bin/sh\n"
        f'exec "{python}" "{ROOT / "settings" / "bin" / "zepos-settings-gui"}" "$@"\n',
        encoding="utf-8")
    skript.chmod(0o755)

    umgebung = dict(os.environ)
    umgebung["HOME"] = str(heim)
    umgebung["XDG_CONFIG_HOME"] = str(heim / ".config")
    umgebung.pop("ZEPOS_SYSTEM_ROOT", None)
    umgebung["PATH"] = f"{binz}:{umgebung.get('PATH', '/usr/bin')}"
    return {"heim": heim, "env": umgebung, "bin": binz}


def _ruf(sonde: Path, stube: dict, *argumente: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(sonde), *argumente], env=stube["env"],
                          capture_output=True, text=True, timeout=120)


def _gespeichert(stube: dict) -> list | None:
    datei = stube["heim"] / ".config" / "zepos" / "user-settings.json"
    if not datei.is_file():
        return None
    doc = json.loads(datei.read_text(encoding="utf-8"))
    return doc.get("bar", {}).get("dock_pins")


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
    nicht mehr an - aber zwei Starter nebeneinander koennen es doch.
    Ein Symbol, das zweimal im Fuss steht, waere die Folge."""
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


@pytest.mark.allow_subprocess
def test_ein_fehlgeschlagener_lesevorgang_schreibt_nichts(sonde, stube):
    """DIE Pruefung dieser Datei.

    "bar.dock_pins" ist eine ERSATZliste: was darinsteht, steht im Dock,
    und was nicht darinsteht, steht nicht darin. Wer sie schreibt, ohne
    sie vorher gelesen zu haben, schreibt eine Liste aus einem einzigen
    Namen - und jedes Symbol, das der Nutzer je angeheftet hat, ist weg.

    Hier wird der Bruecke der Weg genommen (PATH ohne sie). Erwartet
    wird: eine Klage, ein Rueckgabewert ungleich null, und KEINE
    geschriebene Datei.
    """
    kennung = _installierte_anwendung()

    # Erst eine echte Anheftung, damit es etwas zu verlieren gibt.
    assert _ruf(sonde, stube, "pin", kennung).returncode == 0
    vorher = _gespeichert(stube)
    assert vorher, "der Aufbau dieser Pruefung hat nichts angeheftet"

    ohne_bruecke = dict(stube["env"])
    ohne_bruecke["PATH"] = "/nonexistent"
    blind = dict(stube, env=ohne_bruecke)

    ergebnis = _ruf(sonde, blind, "pin", "etwas-anderes.desktop")
    assert ergebnis.returncode != 0, (
        "das Anheften meldet Erfolg, obwohl die Bruecke fehlt:\n"
        + ergebnis.stdout)
    assert "klage:" in ergebnis.stdout, (
        f"es kommt keine Begruendung zurueck: {ergebnis.stdout!r}")

    nachher = _gespeichert(stube)
    assert nachher == vorher, (
        f"ein fehlgeschlagener Lesevorgang hat die Liste veraendert: "
        f"{vorher!r} -> {nachher!r}. Genau so verliert ein Nutzer sein Dock.")


@pytest.mark.allow_subprocess
def test_ohne_bruecke_ist_die_antwort_nichts_und_nicht_leer(sonde, stube):
    """`<keine antwort>` und nicht die leere Liste.

    Die beiden auseinanderzuhalten ist der ganze Zweck des
    Rueckgabetyps: eine leere Liste wuerde geschrieben, ein
    fehlgeschlagener Lesevorgang darf nichts schreiben. Dieselbe Regel,
    die gepflegtePins() im Fuss aufschreibt.
    """
    ohne_bruecke = dict(stube["env"])
    ohne_bruecke["PATH"] = "/nonexistent"
    ergebnis = _ruf(sonde, dict(stube, env=ohne_bruecke), "list")
    assert ergebnis.stdout.strip() == "<keine antwort>", (
        f"ohne Bruecke meldet dockPins() etwas anderes als nichts: "
        f"{ergebnis.stdout!r}")
