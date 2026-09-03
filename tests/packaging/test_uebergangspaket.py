# SPDX-License-Identifier: GPL-3.0-or-later
"""Ein Paket zurueckziehen ist etwas anderes, als es zu loeschen.

WAS GESCHEHEN IST
    Am 01.09.2026 fiel zepos-claude-code: Rezept geloescht, Datei aus
    dem Repository entfernt, `replaces=('zepos-claude-code')` und
    `conflicts=(...)` in zepos-config geschrieben.

    Am 03.09.2026 las der Nutzer von seinem Schirm ab: "dort steht
    zeppos config und zepos claude code are in a conflict und es kann
    nicht aktualsierst werden". Zwei Tage lang bekam die Maschine GAR
    KEINE Aktualisierung.

    Der Grund stand in PKGBUILD(5), bevor die Zeilen geschrieben wurden:
    "Sysupgrade is currently the only pacman operation that utilizes
    this field. A normal sync or upgrade will not use its value." Der
    Bereich "zepos" der Selbstaktualisierung setzt `pacman -S` ab.

WAS DIESE DATEI FESTHAELT
    Die Form, die den Fehler unmoeglich macht: der Name bleibt im
    Repository, das Paket wird leer, und sein `epoch` macht die Ablesung
    zu einer gewoehnlichen Aktualisierung.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

# vercmp ist pacmans EIGENES Werkzeug fuer diese Frage. Die
# Fassungsvergleiche selbst nachzubauen hiesse, eine Zusicherung gegen
# meine Vorstellung von pacman zu pruefen statt gegen pacman.
pytestmark = pytest.mark.allow_subprocess

WURZEL = Path(__file__).resolve().parents[2]
PACKAGING = WURZEL / "packaging"
UEBERGANG = PACKAGING / "zepos-claude-code" / "PKGBUILD"
CONFIG = PACKAGING / "zepos-config" / "PKGBUILD"

# Die Fassung, die auf einer Maschine von 0.1.13 steht. Aus dem
# geloeschten Rezept: pkgver=2.1.233, pkgrel=4.
ALT = "2.1.233-4"

# Die sieben Pfade, die das alte Paket ablegte und die zepos-config seit
# dem 01.09.2026 selbst ablegt. Aus dem geloeschten Rezept abgelesen
# (git show <commit>^:packaging/zepos-claude-code/PKGBUILD).
GETEILTE_PFADE = (
    "usr/bin/zepos-claude-code",
    "usr/share/applications/zepos-claude-code.desktop",
    "usr/share/icons/hicolor/48x48/apps/zepos-claude-code.png",
    "usr/share/icons/hicolor/64x64/apps/zepos-claude-code.png",
    "usr/share/icons/hicolor/128x128/apps/zepos-claude-code.png",
    "usr/share/icons/hicolor/256x256/apps/zepos-claude-code.png",
    "usr/bin/claude",
)


def _feld(text: str, name: str) -> str | None:
    treffer = re.search(rf"^{name}=(.*)$", text, re.M)
    return treffer.group(1).strip() if treffer else None


def _ohne_kommentare(text: str) -> str:
    return "\n".join(z for z in text.splitlines()
                     if not z.lstrip().startswith("#"))


def test_das_rezept_ist_da_und_liefert_kein_fremdes_programm_aus():
    """Der Name bleibt im Repository - das ist der ganze Mechanismus.

    Und er bleibt LEER: die Entscheidung des Nutzers vom 01.09.2026
    ("ich will das packet nicht als meins verkaufen") gilt unveraendert.
    """
    assert UEBERGANG.is_file(), (
        "ohne dieses Rezept ist der Name aus dem Repository verschwunden, "
        "und eine Maschine mit der alten Fassung sitzt wieder fest")

    ohne = _ohne_kommentare(UEBERGANG.read_text(encoding="utf-8"))

    # Gemessen wird, was AUSGEFUEHRT wird, und nicht, was dasteht: die
    # Datei /usr/share/doc/.../HERKUNFT erklaert dem Nutzer, dass der
    # Befehl Claude Code aus der npm-Registry holt, und darf das Wort
    # deshalb enthalten. Ein Test, der es verbietet, wo es ERKLAERT
    # wird, verbietet die Erklaerung und nicht den Vorgang.
    aufrufe = [z.strip() for z in ohne.splitlines()]
    for verboten in ("npm", "curl", "wget", "git"):
        gestartet = [z for z in aufrufe if z.split(" ")[0] == verboten]
        assert gestartet == [], (
            f"das Uebergangspaket ruft {verboten} auf: {gestartet}")

    for feld in ("source", "sha256sums", "makedepends"):
        assert _feld(ohne, feld) is None, (
            f"ein Uebergangspaket hat kein {feld} - es baut nichts und "
            f"holt nichts")


def test_seine_fassung_schlaegt_die_alte_und_zwar_nach_pacmans_urteil():
    """0.1.15 ist KLEINER als 2.1.233 - deshalb `epoch`.

    Gemessen mit vercmp und nicht mit einer eigenen Vorstellung davon,
    wie pacman Fassungen vergleicht.
    """
    text = UEBERGANG.read_text(encoding="utf-8")
    epoch = _feld(text, "epoch")
    assert epoch == "1", (
        "ohne epoch haelt pacman die alte Fassung fuer neuer, meldet "
        f"\"local version is newer\" und spielt nichts ein: epoch={epoch!r}")

    fassung = (WURZEL / "VERSION").read_text(encoding="utf-8").strip()
    neu = f"{epoch}:{fassung}-1"

    urteil = subprocess.run(["vercmp", neu, ALT],
                            capture_output=True, text=True)
    if urteil.returncode != 0:
        pytest.skip("vercmp liegt nicht auf dieser Maschine - damit bleibt "
                    "ungeprueft, ob pacman die neue Fassung fuer neuer haelt")
    assert int(urteil.stdout.strip()) > 0, (
        f"pacman haelt {neu} nicht fuer neuer als {ALT} - eine Ablesung "
        f"findet dann nie statt")


def test_es_legt_keinen_pfad_ab_den_zepos_config_ablegt():
    """Sonst waere das Uebergangspaket selbst der Dateikonflikt, den es
    aufloest."""
    ohne = _ohne_kommentare(UEBERGANG.read_text(encoding="utf-8"))
    getroffen = [pfad for pfad in GETEILTE_PFADE if pfad in ohne]
    assert getroffen == [], (
        "das Uebergangspaket legt Pfade ab, die zepos-config ablegt: "
        f"{getroffen}")

    ziele = re.findall(r'"\$pkgdir/([^"]+)"', ohne)
    assert ziele, "das Rezept legt gar nichts ab - dann baut makepkg nichts"
    for ziel in ziele:
        assert ziel.startswith("usr/share/doc/"), (
            f"das Uebergangspaket legt ausserhalb von /usr/share/doc ab: "
            f"{ziel}")


def test_es_zieht_das_paket_nach_in_dem_der_befehl_jetzt_liegt():
    """Ohne diese Abhaengigkeit waere die Ablesung ein Rechner, auf dem
    /usr/bin/zepos-claude-code weg ist und nichts es ersetzt."""
    ohne = _ohne_kommentare(UEBERGANG.read_text(encoding="utf-8"))
    depends = _feld(ohne, "depends") or ""
    assert "zepos-config" in depends, (
        f"das Uebergangspaket zieht zepos-config nicht nach: {depends!r}")


def test_es_verspricht_nichts_und_verdraengt_nichts():
    """provides, conflicts und replaces sind die drei Felder, deren
    falscher Gebrauch den Fehler erzeugt hat."""
    ohne = _ohne_kommentare(UEBERGANG.read_text(encoding="utf-8"))
    for feld in ("provides", "conflicts", "replaces"):
        assert _feld(ohne, feld) is None, (
            f"das Uebergangspaket traegt {feld} - genau davon kam der "
            f"Fehler vom 01.09.2026")


def test_zepos_config_traegt_den_konflikt_nicht_mehr():
    """DIE Zusicherung dieser Datei.

    Ein `conflicts` auf einen Namen, den dasselbe Repository anbietet,
    macht die beiden Pakete unvereinbar - und dann steht der Nutzer
    wieder vor dem Satz vom 03.09.2026.
    """
    ohne = _ohne_kommentare(CONFIG.read_text(encoding="utf-8"))
    for feld in ("conflicts", "replaces"):
        wert = _feld(ohne, feld)
        assert wert is None or "zepos-claude-code" not in wert, (
            f"zepos-config traegt wieder {feld}={wert} - damit ist die "
            f"Aktualisierung fuer jede Maschine mit dem alten Paket "
            f"blockiert, nicht nur die dieses einen Pakets")


def test_kein_paket_haengt_daran_damit_es_niemand_neu_bekommt():
    """Eine frische Installation soll das Uebergangspaket NIE sehen.

    Es ist der Weg von einem alten Zustand weg und kein Bestandteil des
    Schreibtischs. Stuende es in einem depends, installierte jeder neue
    Rechner ein leeres Paket samt seiner Erklaerung fuer ein Problem,
    das er nie hatte.
    """
    haengen = []
    for rezept in sorted(PACKAGING.glob("*/PKGBUILD")):
        if rezept == UEBERGANG:
            continue
        ohne = _ohne_kommentare(rezept.read_text(encoding="utf-8"))
        for feld in ("depends", "optdepends", "provides"):
            wert = _feld(ohne, feld) or ""
            if "'zepos-claude-code'" in wert or '"zepos-claude-code"' in wert:
                haengen.append(f"{rezept.parent.name}: {feld}")
    assert haengen == [], (
        f"etwas zieht das Uebergangspaket nach: {haengen}")
