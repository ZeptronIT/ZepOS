# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Installer auf jedem Schirm - und was passiert, wenn das misslingt.

WAS BESTELLT WURDE
    Nachdem der Anmeldebildschirm des installierten Systems am
    01.09.2026 behoben war, blieb dieselbe Blindheit im
    Installationsmedium stehen. Der Nutzer, sinngemaess: wer die ZepOS-ISO
    von einem Stick startet und dabei einen zweiten Monitor angesteckt
    hat, darf nicht vor einem schwarzen Schirm sitzen.

    Und das ist der schlimmere der beiden Faelle. Beim installierten
    System kommt man ueber das GRUB-Menue in den Textmodus; wer von einem
    Stick bootet, sitzt vor einem Rechner, den er noch gar nicht kennt.

DIE URSACHE - WOERTLICH DIESELBE, GEMESSEN am 01.09.2026
    `cage -h` der ausgelieferten Fassung 0.3.1-1 kennt genau zwei
    Betriebsarten, `-m extend` (Vorgabe) und `-m last`. zepos-live-session
    setzt kein -m. Gemessen an echtem cage auf dem headless-Backend mit
    zwei Ausgaengen, aufgenommen ueber cages eigenes wlr-screencopy:

        HEADLESS-1:   1 Farbe   - der Hintergrund, sonst nichts
        HEADLESS-2: 185 Farben  - der Installer

    Nach dem Umstellen beider Ausgaenge auf Position 0,0:

        HEADLESS-1: 185 Farben
        HEADLESS-2: 185 Farben, BYTE-GLEICH zu HEADLESS-1

WAS DIESE DATEI PRUEFT UND WAS NICHT
    Sie FUEHRT /usr/local/bin/zepos-live-schirme AUS, gegen einen
    wlr-randr-Stummel, und misst, welche Aufrufe dabei herauskommen. Was
    sie NICHT kann, ist der Compositor selbst: dafuer braucht es cage,
    grim und wlr-randr auf der Maschine, und das misst
    tests/render/test_live_spiegel.py - der ueberspringt, wo eines davon
    fehlt.

    Die Trennung ist dieselbe wie zwischen tests/src/test_login.py und
    tests/render/test_anmeldung_spiegel.py: hier die Entscheidungen des
    Skripts, dort das Verhalten des Compositors.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from tests import conftest

ROOT = Path(__file__).resolve().parents[2]
RELEASE = ROOT / "iso" / "profile-release"
SCHIRME = RELEASE / "airootfs" / "usr" / "local" / "bin" / "zepos-live-schirme"

ENV = "/usr/bin/env"

# Was das Skript an gewoehnlichem Werkzeug braucht. Jedes geht als
# Durchreiche an sein echtes Programm, und conftest.
# assert_safe_to_passthrough() sagt fuer jedes einzeln, ob das erlaubt
# ist - keins davon aendert etwas ausserhalb von tmp_path.
PASSTHROUGH = ("bash", "date", "awk", "sleep", "tr", "cat")

# Das Abfrageintervall im Test. Im Betrieb sind es zwei Sekunden; hier
# waere das nur Wartezeit, die nichts misst.
INTERVALL = "0.1"

# Eine Ausgabe im Format von wlr-randr. Nur die Eigenschaft, auf die sich
# das Skript stuetzt, ist hier wichtig: Kopfzeilen beginnen ganz links,
# alles Weitere ist eingerueckt.
def _listing(*namen: str) -> str:
    blocks = []
    for name in namen:
        blocks.append(
            f'{name} "Unknown Unknown Unknown"\n'
            "  Make: Unknown\n"
            "  Model: Unknown\n"
            "  Physical size: 340x190 mm\n"
            "  Enabled: yes\n"
            "  Modes:\n"
            "    1920x1080 px, 60.000000 Hz (preferred, current)\n"
            "  Position: 0,0\n"
            "  Transform: normal\n"
            "  Scale: 1.000000\n")
    return "".join(blocks)


def _stubs(directory: Path, **bodies: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name in PASSTHROUGH:
        conftest.assert_safe_to_passthrough(name)
        real = shutil.which(name)
        assert real, f"{name} ist auf diesem Rechner nicht da"
        bodies.setdefault(name, f'exec "{real}" "$@"\n')
    for name, body in bodies.items():
        stub = directory / name
        stub.write_text("#!/bin/bash\n" + body, encoding="utf-8")
        stub.chmod(0o755)
    return directory


def _child_path(stubs: Path) -> str:
    """Das Stub-Verzeichnis und nichts sonst - darauf ruht die ganze
    Sicherheitsbegruendung dieser Datei."""
    path = str(stubs)
    assert path.split(os.pathsep) == [str(stubs)]
    assert not os.environ.get("PATH", "").startswith(path)
    return path


class Lauf:
    """Ein laufendes zepos-live-schirme samt seinem wlr-randr-Stummel.

    Das Skript ist eine Endlosschleife, also wird es gestartet, beobachtet
    und beendet - nur der eigene Prozess, nie ein fremder.
    """

    def __init__(self, tmp_path: Path, *, mit_wlr_randr: bool = True) -> None:
        self.tmp = tmp_path
        self.liste = tmp_path / "liste.txt"
        self.aufrufe = tmp_path / "aufrufe.txt"
        self.log = tmp_path / "schirme.log"
        self.liste.write_text("", encoding="utf-8")

        zusatz = {}
        if mit_wlr_randr:
            # Ohne Argumente antwortet der Stummel wie wlr-randr beim
            # Auflisten; MIT Argumenten schreibt er sie mit, statt etwas
            # zu tun.
            zusatz["wlr-randr"] = (
                'if [ "$#" -eq 0 ]; then\n'
                f'    cat "{self.liste}"\n'
                "else\n"
                f'    printf "%s\\n" "$*" >>"{self.aufrufe}"\n'
                "fi\n"
                "exit 0\n")
        self.stubs = _stubs(tmp_path / "stubs", **zusatz)
        self.process: subprocess.Popen | None = None

    def zeige(self, *namen: str) -> None:
        self.liste.write_text(_listing(*namen), encoding="utf-8")

    def start(self) -> None:
        self.process = subprocess.Popen(
            [ENV, "-i", f"PATH={_child_path(self.stubs)}",
             f"ZEPOS_SCHIRME_INTERVALL={INTERVALL}",
             f"ZEPOS_SCHIRME_LOG={self.log}",
             str(SCHIRME)],
            env={}, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True)

    def warte_auf_aufrufe(self, anzahl: int, frist: float = 15.0) -> list[str]:
        ende = time.monotonic() + frist
        while time.monotonic() < ende:
            if len(self.gesehen()) >= anzahl:
                break
            time.sleep(0.05)
        return self.gesehen()

    def gesehen(self) -> list[str]:
        if not self.aufrufe.exists():
            return []
        return [z for z in self.aufrufe.read_text(encoding="utf-8").splitlines()
                if z.strip()]

    def protokoll(self) -> str:
        return self.log.read_text(encoding="utf-8") if self.log.exists() else ""

    def stop(self) -> str:
        assert self.process
        if self.process.poll() is None:
            self.process.terminate()
        try:
            ausgabe, _ = self.process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            ausgabe, _ = self.process.communicate(timeout=10)
        return ausgabe or ""

    def __enter__(self) -> "Lauf":
        return self

    def __exit__(self, *_exception) -> None:
        if self.process and self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=10)


# --------------------------------------------------------------------
# Was das Skript entscheidet
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_two_screens_are_put_on_the_same_spot(tmp_path):
    """DIE BESTELLUNG. Zwei Ausgaenge, ein Bild.

    Gemessen wird an EINEM Aufruf mit beiden Ausgaengen darin und nicht
    an zwei Aufrufen: wlr-randr baut daraus eine einzige Konfiguration,
    und der Compositor nimmt sie als Ganzes an oder gar nicht.
    Nacheinander umgestellt gaebe es einen Zwischenzustand, in dem die
    Flaeche kurz anders aussieht.
    """
    with Lauf(tmp_path) as lauf:
        lauf.zeige("eDP-1", "HDMI-A-1")
        lauf.start()
        aufrufe = lauf.warte_auf_aufrufe(1)
        ausgabe = lauf.stop()

    conftest.assert_no_missing_command(
        type("R", (), {"stdout": ausgabe, "stderr": ""})(), "zepos-live-schirme")
    assert len(aufrufe) == 1, f"{len(aufrufe)} Aufrufe statt einem: {aufrufe}"
    assert aufrufe[0] == "--output eDP-1 --pos 0,0 --output HDMI-A-1 --pos 0,0", (
        f"nicht beide Ausgaenge auf 0,0: {aufrufe[0]!r}\n" + lauf.protokoll())


@pytest.mark.allow_subprocess
def test_a_single_screen_is_left_alone(tmp_path):
    """Der Normalfall, und er darf durch diese Datei nicht schlechter
    werden.

    Ein einzelner Ausgang liegt ohnehin auf 0,0. Ihn trotzdem
    umzustellen hiesse, bei JEDEM Start des Mediums eine
    Ausgangskonfiguration festzuschreiben, die nichts aendert - und jede
    davon ist ein Moduswechsel, den der Compositor ausfuehren darf.
    """
    with Lauf(tmp_path) as lauf:
        lauf.zeige("eDP-1")
        lauf.start()
        time.sleep(1.5)
        aufrufe = lauf.gesehen()
        protokoll = lauf.protokoll()
        lauf.stop()

    assert aufrufe == [], (
        f"der einzige Schirm wurde umgestellt: {aufrufe}\n{protokoll}")
    assert "nichts zu ueberlagern" in protokoll, protokoll


@pytest.mark.allow_subprocess
def test_a_screen_plugged_in_later_is_caught(tmp_path):
    """Ein Kabel, das waehrend der Installation dazukommt.

    Auf einem Installationsmedium ist das keine Spitzfindigkeit: wer
    einen Rechner zum ersten Mal aufbaut, steckt waehrenddessen Sachen
    an.
    """
    with Lauf(tmp_path) as lauf:
        lauf.zeige("eDP-1")
        lauf.start()
        time.sleep(1.0)
        assert lauf.gesehen() == [], "mit einem Schirm wurde schon umgestellt"

        lauf.zeige("eDP-1", "DP-2")
        aufrufe = lauf.warte_auf_aufrufe(1)
        protokoll = lauf.protokoll()
        lauf.stop()

    assert len(aufrufe) == 1, (
        f"der angesteckte Schirm wurde nicht eingefangen: {aufrufe}\n"
        + protokoll)
    assert aufrufe[0] == "--output eDP-1 --pos 0,0 --output DP-2 --pos 0,0", (
        aufrufe[0])


@pytest.mark.allow_subprocess
def test_an_unchanged_list_is_not_applied_over_and_over(tmp_path):
    """Waehrend jemand ein WLAN-Passwort tippt, soll nicht alle zwei
    Sekunden eine Ausgangskonfiguration geschrieben werden.

    Gemessen ueber viele Durchlaeufe: bei INTERVALL=0.1 s sind anderthalb
    Sekunden fuenfzehn Gelegenheiten, es falsch zu machen.
    """
    with Lauf(tmp_path) as lauf:
        lauf.zeige("eDP-1", "HDMI-A-1")
        lauf.start()
        lauf.warte_auf_aufrufe(1)
        time.sleep(1.5)
        aufrufe = lauf.gesehen()
        protokoll = lauf.protokoll()
        lauf.stop()

    assert len(aufrufe) == 1, (
        f"in anderthalb Sekunden {len(aufrufe)} Aufrufe: {aufrufe}\n"
        + protokoll)


@pytest.mark.allow_subprocess
def test_a_screen_going_away_is_a_change_too(tmp_path):
    """Abgesteckt ist auch geaendert.

    Verglichen wird die LISTE und nicht ihre Laenge - ein Schirm ab und
    ein anderer an ergibt dieselbe Anzahl und eine andere Lage. Hier
    bleiben zwei Ausgaenge, aber ein anderer Zweiter.
    """
    with Lauf(tmp_path) as lauf:
        lauf.zeige("eDP-1", "HDMI-A-1")
        lauf.start()
        lauf.warte_auf_aufrufe(1)

        lauf.zeige("eDP-1", "DP-3")
        aufrufe = lauf.warte_auf_aufrufe(2)
        protokoll = lauf.protokoll()
        lauf.stop()

    assert len(aufrufe) == 2, (
        f"der Wechsel wurde nicht bemerkt: {aufrufe}\n" + protokoll)
    assert aufrufe[1] == "--output eDP-1 --pos 0,0 --output DP-3 --pos 0,0", (
        aufrufe[1])


# --------------------------------------------------------------------
# Und was passiert, wenn es misslingt: nichts
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_an_unreadable_listing_changes_nothing_and_ends(tmp_path):
    """Der wichtigste Test dieser Datei.

    Auf dem Startpfad eines Installationsmediums darf eine Zugabe nichts
    kaputtmachen koennen. Antwortet wlr-randr mit etwas, aus dem sich
    kein Ausgangsname lesen laesst - ein geaendertes Format, ein Fehler,
    ein leerer Compositor -, dann wird NICHT geraten und NICHT umgestellt,
    sondern aufgehoert.
    """
    with Lauf(tmp_path) as lauf:
        lauf.liste.write_text("  voellig anderes Format ohne Kopfzeile\n",
                              encoding="utf-8")
        lauf.start()
        assert lauf.process
        try:
            lauf.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pytest.fail("das Skript laeuft weiter, obwohl es nichts lesen "
                        "kann:\n" + lauf.protokoll())
        aufrufe = lauf.gesehen()
        protokoll = lauf.protokoll()
        rc = lauf.process.returncode

    assert aufrufe == [], f"es wurde trotzdem umgestellt: {aufrufe}"
    assert rc == 0, f"das Skript endete mit {rc}\n{protokoll}"


@pytest.mark.allow_subprocess
def test_without_wlr_randr_at_all_it_simply_ends(tmp_path):
    """Ohne das Programm verhaelt sich das Medium wie vorher.

    KEIN assert_no_missing_command hier, und das ist der Punkt: "command
    not found" ist in DIESEM Test das erwartete Ergebnis. Geprueft wird,
    dass das Skript daran nicht haengenbleibt - eine Endlosschleife, die
    alle zwei Sekunden ein fehlendes Programm sucht, waere ein Prozess,
    der bis zum Neustart des Rechners laeuft.
    """
    with Lauf(tmp_path, mit_wlr_randr=False) as lauf:
        lauf.start()
        assert lauf.process
        try:
            lauf.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pytest.fail("das Skript laeuft weiter, obwohl es wlr-randr "
                        "nicht gibt:\n" + lauf.protokoll())
        rc = lauf.process.returncode
        protokoll = lauf.protokoll()

    assert rc == 0, f"das Skript endete mit {rc}\n{protokoll}"


@pytest.mark.allow_subprocess
def test_a_refused_change_is_not_retried_forever(tmp_path):
    """wlr-randr sagt nein - und das Skript merkt sich das NICHT als
    erledigt.

    Ein abgelehntes Umstellen darf nicht wie ein gelungenes behandelt
    werden: sonst bliebe es beim schwarzen Schirm, und der naechste
    Durchlauf wuerde es gar nicht mehr versuchen. Es darf aber auch nicht
    aufgeben - der Compositor kann eine Konfiguration voruebergehend
    ablehnen.
    """
    with Lauf(tmp_path) as lauf:
        lauf.zeige("eDP-1", "HDMI-A-1")
        # Auflisten geht, Umstellen misslingt.
        (lauf.stubs / "wlr-randr").write_text(
            "#!/bin/bash\n"
            'if [ "$#" -eq 0 ]; then\n'
            f'    cat "{lauf.liste}"\n'
            "else\n"
            f'    printf "%s\\n" "$*" >>"{lauf.aufrufe}"\n'
            "    exit 1\n"
            "fi\n", encoding="utf-8")
        (lauf.stubs / "wlr-randr").chmod(0o755)

        lauf.start()
        aufrufe = lauf.warte_auf_aufrufe(3)
        protokoll = lauf.protokoll()
        lauf.stop()

    assert len(aufrufe) >= 3, (
        f"nach einer Ablehnung wurde nicht mehr versucht: {aufrufe}\n"
        + protokoll)
    assert "abgelehnt" in protokoll, protokoll
