# SPDX-License-Identifier: GPL-3.0-or-later
"""media.sh: was gerade laeuft.

WARUM ES DIESE DATEI GIBT
    Die Leiste zeigte bis zum 12.08.2026 keinen Titel und hatte keinen
    Pause-Knopf, waehrend neun Tastenbindungen dieses Projekts genau das
    steuern. Wer keine Medientasten auf der Tastatur hat, hatte keinen
    Weg.

WOMIT GEMESSEN WURDE, am 12.08.2026
    Gegen einen EIGENEN D-Bus-Sitzungsbus (`dbus-run-session`) mit einem
    Attrappen-MPRIS-Spieler darauf - nicht gegen den Bus des angemeldeten
    Nutzers, auf dem sein wirklicher Spieler liegt. Dabei gemessen:

        playerctl -a metadata --format '{{status}}|{{playerName}}|{{artist}}|{{title}}'
        -> "Playing|zepostest|Die Band|Ein Lied mit \"Zitat\" & Zeichen"
        -> 4 ms, dreimal nacheinander
        ohne Spieler: "No players found" auf stderr, Rueckgabewert 1

    Diese Datei stellt genau diese Zeilen nach. Das ist dasselbe
    Verfahren wie in tests/src/test_bar_status.py, das wpctl, nmcli und
    bluetoothctl nachstellt: gemessen wird, was das SKRIPT mit einer
    Antwort tut, und die Antwort ist eine Konstante.

    Das Trennzeichen ist in Wirklichkeit ASCII 0x1F ("unit separator")
    und nicht der Strich, der hier der Lesbarkeit halber steht - warum,
    steht bei SEP in der Vorlage und ist ein Befund DIESER Datei.

WAS DIESE DATEI GEFUNDEN HAT, beim ersten Lauf am 12.08.2026
    Zwei Fehler, beide in der Vorlage, beide beim Zerlegen der Zeile:

      * Ein TABULATOR als Trennzeichen. bash fasst Leerraum-Trennzeichen
        in Folgen zusammen, also verschwand ein leerer Interpret samt
        dem Feld dahinter: aus "Playing<TAB>mpv<TAB><TAB>Kurz" wurde
        artist="Kurz" und title="".
      * `awk` OHNE Locale zaehlt Bytes und nicht Zeichen. Der Titel
        wurde damit unter `env -i` nach 45 BYTES beschnitten - bei
        Umlauten mitten in einem Buchstaben.

UND WARUM NICHT ASTALMPRIS
    Weil es das hier nicht gibt. GEMESSEN am 12.08.2026:
    /usr/share/gir-1.0/ fuehrt Astal-3.0, Astal-4.0, AstalIO-0.1 und
    AstalNotifd-0.1, und packaging/astal/PKGBUILD baut genau diese drei
    Teilpakete - lib/mpris ist keines davon. playerctl liegt dagegen auf
    jeder ZepOS-Installation, weil neun Bindungen es namentlich rufen.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import assert_no_missing_command, assert_safe_to_passthrough

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
TEMPLATE = SRC / "templates" / "ags-media-scripts.template"

BASH = "/bin/bash"
PASSTHROUGH = ("jq", "awk", "printf", "cat")

pytestmark = pytest.mark.allow_subprocess


class Sandbox:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.stubs = root / "stubs"
        self.stubs.mkdir()
        self.script = self._render()
        for name in PASSTHROUGH:
            assert_safe_to_passthrough(name)
            self.stub(name, f'exec /usr/bin/{name} "$@"')
        self.players()

    def _render(self) -> Path:
        sys.path.insert(0, str(SRC))
        try:
            import template_processor
            processor = template_processor.ConfigProcessor()
        finally:
            sys.path.remove(str(SRC))
        script = self.root / "media.sh"
        processor.apply_template(TEMPLATE, script)
        script.chmod(0o755)
        return script

    def stub(self, name: str, body: str) -> None:
        path = self.stubs / name
        path.write_text(f"#!/bin/bash\n{body}\n")
        path.chmod(0o755)

    def players(self, *rows: tuple[str, str, str, str]) -> None:
        """Eine Zeile je Spieler, genau wie `playerctl -a metadata`.

        Ohne Zeilen: der gemessene Rueckgabewert 1 und "No players
        found" auf stderr - nicht ein leerer, erfolgreicher Lauf. Ein
        Skript, das nur mit der freundlichen Variante geprueft wird,
        haette den haeufigsten Fall ueberhaupt nie gesehen.
        """
        if not rows:
            self.stub("playerctl", 'echo "No players found" >&2\nexit 1')
            return
        # ASCII 0x1F, "unit separator" - dasselbe Trennzeichen, das
        # das Skript in seine Formatzeichenkette schreibt. Ein Tabulator
        # stand hier zuerst, und er war der Fehler: bash fasst
        # Leerraum-Trennzeichen in Folgen zusammen, und ein leerer
        # Interpret verschwand damit samt dem Feld dahinter.
        text = "".join("\x1f".join(row) + "\n" for row in rows)
        (self.root / "players.txt").write_text(text)
        self.stub("playerctl", f'exec /usr/bin/cat {self.root}/players.txt')

    def run(self) -> dict:
        result = subprocess.run(
            ["/usr/bin/env", "-i", f"PATH={self.stubs}", f"HOME={self.root}",
             BASH, str(self.script)],
            capture_output=True, text=True, timeout=60,
        )
        assert_no_missing_command(result, "media.sh")
        assert result.returncode == 0, (
            f"media.sh endete mit {result.returncode}:\n"
            + result.stdout + result.stderr)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise AssertionError(
                f"media.sh hat kein JSON geschrieben ({error}):\n"
                f"{result.stdout!r}\n{result.stderr}") from error


@pytest.fixture()
def sandbox(tmp_path: Path) -> Sandbox:
    return Sandbox(tmp_path)


def test_no_player_is_an_empty_module(sandbox: Sandbox) -> None:
    """Der haeufigste Zustand ueberhaupt, und er muss NICHTS ergeben.

    Ein leeres "text" blendet das Modul aus. Das ist die Bedingung,
    unter der ein weiteres Modul auf einer Leiste vertretbar ist, die
    auf 1366x768 schon ueberlaeuft.
    """
    answer = sandbox.run()
    assert answer["text"] == "" and answer["class"] == "", answer
    assert answer["status"] == "", answer


def test_a_stopped_player_shows_nothing(sandbox: Sandbox) -> None:
    """Ein gestoppter Spieler hat nichts geladen.

    Das Modul haette einen Titel, den es nicht gibt, und einen Knopf,
    der nichts fortsetzt.
    """
    sandbox.players(("Stopped", "mpv", "", ""))
    assert sandbox.run()["text"] == ""


def test_a_playing_player_shows_artist_and_title(sandbox: Sandbox) -> None:
    sandbox.players(("Playing", "firefox", "Die Band", "Das Lied"))
    answer = sandbox.run()
    assert "Die Band" in answer["text"] and "Das Lied" in answer["text"], answer
    assert answer["status"] == "Playing", answer
    assert "media-playing" in answer["class"], answer
    assert answer["artist"] == "Die Band" and answer["title"] == "Das Lied"


def test_a_paused_player_stays_visible(sandbox: Sandbox) -> None:
    """Pausiert ist NICHT weg, und das ist eine Entscheidung.

    Waere das Modul nur bei "Playing" da, verschwaende es in dem
    Augenblick, in dem man darauf klickt - und der Knopf zum Fortsetzen
    waere fort, sobald man ihn braucht. Ein Bedienelement, das seine
    eigene Wirkung wegnimmt, ist keines.
    """
    sandbox.players(("Paused", "firefox", "Die Band", "Das Lied"))
    answer = sandbox.run()
    assert answer["text"] != "", answer
    assert "media-paused" in answer["class"], answer


def test_the_playing_one_wins_over_the_paused_one(sandbox: Sandbox) -> None:
    """Ohne `-a` naehme playerctl den ERSTEN, den es findet - das ist
    die Reihenfolge, in der die Programme gestartet wurden.

    Wer einen Browser offen hat und danach Musik startet, bekaeme den
    Browser.
    """
    sandbox.players(("Paused", "firefox", "Ein Reiter", "Ein Video"),
                    ("Playing", "mpv", "Die Band", "Das Lied"))
    answer = sandbox.run()
    assert answer["player"] == "mpv", answer
    assert answer["title"] == "Das Lied", answer


def test_a_player_without_metadata_falls_back_to_its_name(
        sandbox: Sandbox) -> None:
    """Ein Netzradio ohne Metadaten, ein Browserreiter ohne Seitentitel.

    Der Name des Spielers ist die schlechteste Auskunft AUSSER gar
    keiner - und ein Modul ohne Text verschwindet, was hier falsch
    waere: es laeuft ja etwas.
    """
    sandbox.players(("Playing", "vlc", "", ""))
    answer = sandbox.run()
    assert "vlc" in answer["text"], answer


def test_a_very_long_title_is_cut_to_the_narrow_measure(
        sandbox: Sandbox) -> None:
    """Die Decke gegen den einen Strom, der die halbe Leiste kostet.

    src/sizes.py MEASURE_LINE ist 45 - die schmale Sprosse nach
    Bringhurst. Gezaehlt werden ZEICHEN und nicht Bytes; der Titel hier
    traegt Umlaute, damit ein Schnitt mitten in einen Mehrbyte-Buchstaben
    auffiele.
    """
    from src import sizes
    long_title = "Radio Ümläut – Die große Abendsendung mit Gästen aus aller Welt"
    sandbox.players(("Playing", "mpv", "", long_title))
    text = sandbox.run()["text"]
    # Das Zeichen und das Leerzeichen davor gehoeren nicht zum Titel.
    headline = text.split(" ", 1)[1]
    assert len(headline) == sizes.MEASURE_LINE, (
        f"der Titel ist {len(headline)} Zeichen lang, gedeckelt wird bei "
        f"{sizes.MEASURE_LINE}: {headline!r}")
    assert headline.endswith("…"), headline
    assert "�" not in headline, "der Schnitt liegt mitten in einem Zeichen"


def test_a_short_title_is_not_touched(sandbox: Sandbox) -> None:
    """Die Gegenprobe: die Decke ist eine Decke und kein Ziel."""
    sandbox.players(("Playing", "mpv", "", "Kurz"))
    assert sandbox.run()["title"] == "Kurz"
    assert "…" not in sandbox.run()["text"]


def test_a_title_with_a_quote_does_not_break_the_bar(sandbox: Sandbox) -> None:
    """Ein von Hand gebautes JSON waere hier zerbrochen - und dann
    zeigte die LEISTE nichts mehr an, nicht nur dieses Modul."""
    sandbox.players(("Playing", "mpv", "AC/DC", 'Ein "Lied" & mehr'))
    assert sandbox.run()["title"] == 'Ein "Lied" & mehr'
