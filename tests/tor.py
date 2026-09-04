#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Das volle Tor, auf mehrere Spuren verteilt.

WARUM ES DAS GIBT
    Der Nutzer am 04.09.2026: "kannst du bitte ein weg finden die tests
    parallel und schneller zu machen wir verwenden echt viel zeit da
    drinnen". GEMESSEN am selben Tag: ein voller Lauf braucht 21:49 fuer
    4000 Zusicherungen, und er laeuft dabei auf EINEM Kern.

WARUM NICHT pytest-xdist
    Es liegt nicht in dieser Umgebung, und ein Paket zu installieren ist
    nicht meine Entscheidung. Wichtiger: xdist verteilt nach Tests oder
    Dateien, ohne zu wissen, WELCHE nicht nebeneinander duerfen - und
    hier duerfen zwei Sorten das nicht. Diese Datei weiss es.

WAS NICHT NEBENEINANDER LAUFEN DARF, UND WARUM - BEIDES NACHGESEHEN
    DIE BILDLAEUFE (tests/render/)
        Jeder startet ein verschachteltes Hyprland und misst Fristen -
        "in 3 s ist ein Zeigergrund entstanden". Unter Last reissen die.
        GEMESSEN am 03. und 04.09.2026: test_geometry.py und
        test_vpn_liste_platz.py fielen im vollen Lauf und waren allein
        gruen (7 passed in 20,8 s). Zwei davon nebeneinander ist schon
        Last.

    DIE KOPFLOSEN OBERFLAECHEN (broadwayd)
        Sie nehmen eine ANZEIGENUMMER, und die Bereiche ueberlappen
        sich zwischen den Dateien - nachgesehen am 04.09.2026:

            tests/menu/test_menu_headless.py          21-98
            tests/src/test_sprachwechsel.py           71
            tests/src/test_bar_headless.py           120-159
            tests/settings/test_settings_headless.py 121-198
            tests/src/test_vpn_schalter.py           200-219

        Nacheinander stoert das nie: die Nummer ist wieder frei, bevor
        die naechste Datei sie nimmt. Nebeneinander verweigert
        refuse_a_foreign_display() den Dienst - laut, aber es waere ein
        Fehlschlag, den der Messstand erfunden hat.

    Beide Sorten bekommen deshalb ihre eigene Spur und laufen darin
    NACHEINANDER. Der ganze Rest - Text, Vorlagen, Python - darf sich
    verteilen.

WAS ES NICHT TUT
    Es versteckt nichts. Jede Spur bekommt ihre eigene Ausgabe, jede
    Zeile FAILED/ERROR wird gesammelt und am Ende genannt, und der
    Rueckgabewert ist der schlechteste aller Spuren. Ein Laeufer, der
    einen roten Lauf gruen aussehen laesst, ist schlimmer als ein
    langsamer.

AUFRUF
    python tests/tor.py                 alle Spuren, Vorgabe
    python tests/tor.py --spuren 8      mehr schnelle Spuren
    python tests/tor.py --bild 2        zwei Bildspuren statt einer
    python tests/tor.py --nur schnell   nur eine Sorte
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
TESTS = WURZEL / "tests"

# Wo die gemessenen Dauern liegen. Im Cache von pytest, weil es den
# ohnehin gibt und er nicht eingecheckt wird - eine Zahlentabelle im
# Baum waere eine Datei, die bei jedem Lauf einen Diff macht.
DAUERN = WURZEL / ".pytest_cache" / "tor-dauern.json"

# Die Dateien, die eine Anzeigenummer nehmen. Ausgeschrieben und nicht
# gesucht: eine Liste, die sich aus dem Bestand ergibt, ist mit jedem
# Bestand einverstanden - auch mit einem, in dem eine Datei die Nummer
# neuerdings anders holt. Wer eine hinzufuegt, traegt sie hier ein; wer
# es vergisst, sieht einen Fehlschlag von refuse_a_foreign_display() und
# findet ueber ihn hierher.
MIT_ANZEIGE = (
    "installer/test_gui_headless.py",
    "lock/test_lock_screen.py",
    "lock/test_style.py",
    "menu/test_menu_headless.py",
    "settings/test_settings_headless.py",
    "src/test_bar_headless.py",
    "src/test_bar_notifications.py",
    "src/test_bluetooth_kopplung.py",
    "src/test_dock_menue.py",
    "src/test_dock_minimized.py",
    "src/test_filemanager.py",
    "src/test_greeter.py",
    "src/test_own_plugins.py",
    "src/test_sprachwechsel.py",
    "src/test_vpn_fenster_unbekannt.py",
    "src/test_vpn_schalter.py",
    "src/test_vpn_zahnrad.py",
)

# Die Dateien AUSSERHALB von tests/render/, die ebenfalls ein
# verschachteltes Hyprland starten. Sie gehoeren in dieselbe Spur wie
# die Bildlaeufe - GEMESSEN am 04.09.2026: in der Anzeigespur, also
# neben der Bildspur, fiel test_a_wrong_password_leaves_the_session_
# locked; allein ist es in 6,58 s gruen. Zwei Compositoren nebeneinander
# sind genau die Last, gegen die die Fristen dieser Laeufe nicht
# gebaut sind.
MIT_COMPOSITOR = (
    "lock/test_auth.py",
    "lock/test_lock_screen.py",
)

# Eine Zeile wie "12.34s call     tests/src/test_x.py::test_y"
DAUER_ZEILE = re.compile(
    r"^(\d+\.\d+)s\s+\w+\s+(tests/[^:]+\.py)::", re.M)


def alle_dateien() -> list[str]:
    """Jede Testdatei, als Pfad relativ zu tests/."""
    return sorted(str(pfad.relative_to(TESTS))
                  for pfad in TESTS.rglob("test_*.py"))


def gelesene_dauern() -> dict[str, float]:
    try:
        return json.loads(DAUERN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def schaetze(datei: str, gemessen: dict[str, float]) -> float:
    """Wie lange die Datei braucht.

    Gemessen, wenn es eine Messung gibt. Sonst die GROESSE als
    Naeherung: sie ist grob, aber sie ist besser als "alle gleich" -
    eine Spur mit den drei dicksten Dateien laeuft sonst allein weiter,
    waehrend die anderen fertig sind.
    """
    if datei in gemessen:
        return gemessen[datei]
    try:
        return (TESTS / datei).stat().st_size / 5000.0
    except OSError:
        return 1.0


def verteile(dateien: list[str], spuren: int,
             gemessen: dict[str, float]) -> list[list[str]]:
    """Die laengste zuerst, immer auf die leerste Spur.

    Das ist die einfachste Regel, die etwas taugt (longest processing
    time first): sie liegt nie mehr als ein Drittel ueber der bestmoeg-
    lichen Verteilung, und sie braucht nichts als die Schaetzungen.
    """
    spuren = max(1, spuren)
    koerbe: list[list[str]] = [[] for _ in range(spuren)]
    lasten = [0.0] * spuren
    for datei in sorted(dateien, key=lambda d: -schaetze(d, gemessen)):
        leerste = lasten.index(min(lasten))
        koerbe[leerste].append(datei)
        lasten[leerste] += schaetze(datei, gemessen)
    return [korb for korb in koerbe if korb]


class Spur:
    """Ein pytest-Prozess mit seinem eigenen Zeug."""

    def __init__(self, name: str, dateien: list[str], basis: Path) -> None:
        self.name = name
        self.dateien = dateien
        self.protokoll = basis / f"{name}.log"
        self.temp = basis / f"{name}-tmp"
        self.begonnen = 0.0
        self.dauer = 0.0
        self.kind: subprocess.Popen | None = None

    def starte(self) -> None:
        self.temp.mkdir(parents=True, exist_ok=True)
        befehl = [
            sys.executable, "-m", "pytest", "-q",
            # Die Reihenfolge fest, wie im Tor: ein Lauf, der sich nicht
            # wiederholen laesst, ist kein Messstand.
            "-p", "no:randomly",
            # Jede Spur ihr eigenes tmp: pytest nummeriert seine
            # Verzeichnisse durch, und zwei Prozesse wuerden sich um
            # dieselbe Nummer streiten.
            f"--basetemp={self.temp}",
            # Kein gemeinsamer Cache - dieselbe Ueberlegung.
            "-p", "no:cacheprovider",
            # Die Dauern, aus denen die naechste Verteilung entsteht.
            "--durations=0", "--durations-min=0.05",
        ] + [f"tests/{datei}" for datei in self.dateien]
        self.begonnen = time.monotonic()
        self.kind = subprocess.Popen(
            befehl, cwd=WURZEL, stdout=self.protokoll.open("wb"),
            stderr=subprocess.STDOUT)

    def fertig(self) -> bool:
        return self.kind is not None and self.kind.poll() is not None

    def ende(self) -> int:
        assert self.kind
        wert = self.kind.wait()
        self.dauer = time.monotonic() - self.begonnen
        return wert

    def text(self) -> str:
        try:
            return self.protokoll.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def zusammenfassung(self) -> str:
        for zeile in reversed(self.text().splitlines()):
            if " passed" in zeile or " failed" in zeile or " error" in zeile:
                return zeile.strip()
        return "(keine Zusammenfassung)"

    def klagen(self) -> list[str]:
        return [zeile for zeile in self.text().splitlines()
                if zeile.startswith(("FAILED", "ERROR"))]


def lies_dauern(spuren: list[Spur]) -> dict[str, float]:
    """Aus --durations je Datei eine Summe machen."""
    summen: dict[str, float] = {}
    for spur in spuren:
        for dauer, datei in DAUER_ZEILE.findall(spur.text()):
            kurz = datei[len("tests/"):]
            summen[kurz] = summen.get(kurz, 0.0) + float(dauer)
    return summen


def main(argv: list[str] | None = None) -> int:
    zerleger = argparse.ArgumentParser(
        description="Das volle Tor, auf mehrere Spuren verteilt.")
    # VIER UND NICHT "alle Kerne minus zwei" - und das ist gemessen.
    #
    #     Mit zwoelf schnellen Spuren war der ganze schnelle Teil nach
    #     zwei Minuten durch (30 bis 126 s je Spur), und die Bildspur
    #     brauchte 640 s. Die zwoelf haben also nichts gespart und der
    #     Bildspur genau in den ersten zwei Minuten die Kerne
    #     weggenommen - dort, wo sie ihre Fristen misst ("in 3 s ist ein
    #     Zeigergrund entstanden"). Ergebnis: elf Fehler in
    #     test_geometry.py und test_schale_stil.py, beide allein gruen.
    #
    #     Vier Spuren brauchen fuer denselben Teil rund vier Minuten und
    #     laufen damit im Schatten der Bildspur, die ohnehin laenger
    #     dauert. Die Gesamtzeit aendert sich dadurch NICHT.
    zerleger.add_argument("--spuren", type=int, default=4,
                          help="parallele Spuren fuer die schnellen Dateien "
                               "(Vorgabe 4 - mehr spart nichts und stoert "
                               "die Bildspur)")
    zerleger.add_argument("--bild", type=int, default=1,
                          help="Spuren fuer tests/render/ (Vorgabe 1 - sie "
                               "messen Fristen und reissen unter Last)")
    zerleger.add_argument("--anzeige", type=int, default=1,
                          help="Spuren fuer die kopflosen Oberflaechen "
                               "(Vorgabe 1 - ihre Anzeigenummern "
                               "ueberlappen sich)")
    zerleger.add_argument("--nur", choices=("bild", "anzeige", "schnell"),
                          help="nur eine Sorte laufen lassen")
    argumente = zerleger.parse_args(argv)

    dateien = alle_dateien()
    if not dateien:
        print("keine Testdateien gefunden", file=sys.stderr)
        return 2

    bild = [d for d in dateien
            if d.startswith("render/") or d in MIT_COMPOSITOR]
    anzeige = [d for d in dateien if d in MIT_ANZEIGE and d not in bild]
    schnell = [d for d in dateien if d not in bild and d not in anzeige]

    gemessen = gelesene_dauern()
    gruppen: list[tuple[str, list[list[str]]]] = []
    if argumente.nur in (None, "bild") and bild:
        gruppen.append(("bild", verteile(bild, argumente.bild, gemessen)))
    if argumente.nur in (None, "anzeige") and anzeige:
        gruppen.append(("anzeige",
                        verteile(anzeige, argumente.anzeige, gemessen)))
    if argumente.nur in (None, "schnell") and schnell:
        gruppen.append(("schnell", verteile(schnell, argumente.spuren,
                                            gemessen)))

    basis = Path(tempfile.mkdtemp(prefix="zeptor-"))
    spuren: list[Spur] = []
    for art, koerbe in gruppen:
        for nummer, korb in enumerate(koerbe, 1):
            spuren.append(Spur(f"{art}-{nummer}", korb, basis))

    print(f"{len(dateien)} Dateien in {len(spuren)} Spuren "
          f"({', '.join(sorted({s.name.split('-')[0] for s in spuren}))})")
    for spur in spuren:
        last = sum(schaetze(d, gemessen) for d in spur.dateien)
        print(f"  {spur.name:<12} {len(spur.dateien):>3} Dateien, "
              f"geschaetzt {last:>6.0f} s")

    angefangen = time.monotonic()
    for spur in spuren:
        spur.starte()

    # JEDE SPUR WIRD ABGEHOLT, WENN SIE FERTIG IST - und nicht der
    # Reihe nach. Hier stand `for spur in spuren: spur.ende()`, und
    # damit stand in der Auswertung fuer JEDE Spur die Dauer der
    # laengsten: wer als zweiter abgewartet wird, ist laengst fertig,
    # aber die Uhr laeuft bis zum wait(). GEMESSEN am 04.09.2026: alle
    # vierzehn Spuren meldeten 640 s, waehrend pytest selbst 30 bis 247
    # sagte.
    werte: dict[str, int] = {}
    offen = list(spuren)
    while offen:
        for spur in list(offen):
            if spur.fertig():
                werte[spur.name] = spur.ende()
                offen.remove(spur)
        if offen:
            time.sleep(0.2)
    gesamt = time.monotonic() - angefangen

    print()
    schlimmster = 0
    for spur in sorted(spuren, key=lambda s: -s.dauer):
        wert = werte[spur.name]
        schlimmster = max(schlimmster, wert)
        zeichen = "ok " if wert == 0 else "ROT"
        print(f"  {zeichen} {spur.name:<12} {spur.dauer:>6.0f}s  "
              f"{spur.zusammenfassung()}")

    klagen = [zeile for spur in spuren for zeile in spur.klagen()]
    if klagen:
        print(f"\n{len(klagen)} Fehlschlaege:")
        for zeile in klagen:
            print(f"  {zeile}")
        print("\nDie ganzen Ausgaben liegen in:")
        for spur in spuren:
            if werte[spur.name] != 0:
                print(f"  {spur.protokoll}")

    # Die Dauern fuer die naechste Verteilung. Auch bei einem roten
    # Lauf: was gelaufen ist, ist gemessen.
    neue = lies_dauern(spuren)
    if neue:
        zusammen = gelesene_dauern()
        zusammen.update(neue)
        DAUERN.parent.mkdir(parents=True, exist_ok=True)
        DAUERN.write_text(json.dumps(zusammen, indent=1, sort_keys=True),
                          encoding="utf-8")

    print(f"\n{gesamt:.0f}s insgesamt "
          f"(laengste Spur {max(s.dauer for s in spuren):.0f}s)")

    if not klagen and schlimmster == 0:
        shutil.rmtree(basis, ignore_errors=True)
    return schlimmster


if __name__ == "__main__":
    sys.exit(main())
