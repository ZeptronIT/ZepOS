# SPDX-License-Identifier: GPL-3.0-or-later
"""updates.sh: die Oberflaeche, die src/update.py nie hatte.

WAS DER BEFUND WAR
    src/update.py ist vollstaendig - 1208 Zeilen, ein systemd-Zeitgeber,
    eine Konfiguration unter /etc/zepos, ein Zustandsdokument unter
    /var/lib/zepos, eine Marke fuer "muss neu erzeugt werden", ein
    Benachrichtigungsweg. Und am 12.08.2026 KEINE einzige Flaeche auf
    dem Bildschirm: `zepos-update --status` in einem Terminal war der
    ganze Weg dorthin. Ein Zeitgeber, der still scheitert, scheitert
    weiter.

WAS HIER GEPRUEFT WIRD
    Die eine Frage, die dieses Skript beantwortet: MUSS der Mensch das
    jetzt sehen. Vier Zustaende sagen ja, alles andere nein - und "nein"
    ist der wichtigste Fall, weil er der haeufigste ist: die Leiste
    traegt achtzehn Module und laeuft auf 1366x768 ueber.

    Geprueft wird gegen ein Zustandsdokument, das dieser Test
    hinschreibt, unter einer umgeleiteten Wurzel (ZEPOS_STATE_ROOT).
    Die echte ist /var/lib/zepos und gehoert root; ein Test, der dorthin
    schreiben muesste, koennte nicht laufen.

    Die FELDER des Dokuments sind keine Erfindung dieses Tests: sie
    werden gegen update.state_document() gehalten, damit ein Umbau dort
    hier auffaellt und nicht auf dem Schreibtisch des Nutzers.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src import update
from tests.conftest import assert_no_missing_command, assert_safe_to_passthrough

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
TEMPLATE = SRC / "templates" / "ags-updates-scripts.template"

BASH = "/bin/bash"
PASSTHROUGH = ("jq", "cat", "printf")

pytestmark = pytest.mark.allow_subprocess


class Sandbox:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.stubs = root / "stubs"
        self.stubs.mkdir()
        self.state = root / "state"
        self.state.mkdir()
        self.script = self._render()
        for name in PASSTHROUGH:
            assert_safe_to_passthrough(name)
            self.stub(name, f'exec /usr/bin/{name} "$@"')
        # zepos-update ist NICHT gestubbt, solange niemand es verlangt:
        # `command -v` findet es dann nicht, und das Skript faellt auf
        # seinen eigenen kurzen Satz zurueck. Genau das ist der Zustand
        # einer Maschine, auf der zepos-config fehlt.

    def _render(self) -> Path:
        sys.path.insert(0, str(SRC))
        try:
            import template_processor
            processor = template_processor.ConfigProcessor()
        finally:
            sys.path.remove(str(SRC))
        script = self.root / "updates.sh"
        processor.apply_template(TEMPLATE, script)
        script.chmod(0o755)
        return script

    def stub(self, name: str, body: str) -> None:
        path = self.stubs / name
        path.write_text(f"#!/bin/bash\n{body}\n")
        path.chmod(0o755)

    def wrote(self, document: dict) -> None:
        (self.state / update.STATE_FILE).write_text(json.dumps(document))

    def marker(self) -> None:
        (self.state / update.REGENERATE_MARKER).write_text("")

    def run(self) -> dict:
        result = subprocess.run(
            ["/usr/bin/env", "-i", f"PATH={self.stubs}", f"HOME={self.root}",
             f"ZEPOS_STATE_ROOT={self.state}", BASH, str(self.script)],
            capture_output=True, text=True, timeout=60,
        )
        assert_no_missing_command(result, "updates.sh")
        assert result.returncode == 0, (
            f"updates.sh endete mit {result.returncode}:\n"
            + result.stdout + result.stderr)
        return json.loads(result.stdout)


@pytest.fixture()
def sandbox(tmp_path: Path) -> Sandbox:
    return Sandbox(tmp_path)


def _document(**overrides) -> dict:
    """Ein Zustandsdokument mit den Feldern, die update.py wirklich schreibt.

    Gebaut aus state_document() und nicht von Hand: die Feldnamen sind
    die Schnittstelle zwischen zwei Dateien, und eine Umbenennung dort
    soll hier umfallen und nicht beim Nutzer.
    """
    outcome = update.Outcome(result=update.Outcome.OK, started="", finished="")
    base = update.state_document(outcome, update.defaults())
    base.update(overrides)
    return base


# --------------------------------------------------------------------
# Schweigen
# --------------------------------------------------------------------

def test_a_machine_that_never_ran_says_nothing(sandbox: Sandbox) -> None:
    """Kein Zustandsdokument: eine frische Installation.

    Das ist kein Alarm. update.describe() hat dafuer einen eigenen Satz
    ("hat sich noch nie selbst aktualisiert"), und der gehoert in
    `zepos-doctor`, nicht auf die Leiste.
    """
    answer = sandbox.run()
    assert answer["text"] == "" and answer["class"] == "", answer


def test_a_clean_run_says_nothing(sandbox: Sandbox) -> None:
    """Der haeufigste Zustand ueberhaupt: es lief, es war nichts zu tun."""
    sandbox.wrote(_document())
    assert sandbox.run()["text"] == ""


def test_a_run_that_upgraded_something_says_nothing_by_itself(
        sandbox: Sandbox) -> None:
    """Eingespielt ist erledigt.

    Was danach noch ansteht, ist die Neuerzeugung - und die hat ihre
    eigene Marke, die update.py nur nach einem Lauf setzt, der wirklich
    Pakete getauscht hat.
    """
    sandbox.wrote(_document(
        upgraded=[{"name": "zepos-config", "from": "1", "to": "2"}]))
    assert sandbox.run()["text"] == ""


# --------------------------------------------------------------------
# Reden
# --------------------------------------------------------------------

def test_a_failed_run_is_shown_with_pacmans_own_words(sandbox: Sandbox) -> None:
    """Der Fall, in dem NICHTS anderes es je meldete.

    Der Wortlaut von pacman steht im Tooltip, weil er das Einzige ist,
    was einem Menschen sagt, WARUM - genau die Begruendung, aus der
    update.state_document() ihn mitschreibt.
    """
    sandbox.wrote(_document(result=update.Outcome.FAILED, returncode=1,
                            message="error: target not found: zepos-config"))
    answer = sandbox.run()
    assert answer["text"] != "", answer
    assert "updates-failed" in answer["class"], answer
    assert "target not found" in answer["tooltip"], answer


def test_pending_arch_updates_are_counted(sandbox: Sandbox) -> None:
    """Was update.scope "zepos" mit ABSICHT nicht anfasst.

    update.py sagt selbst, wozu es sie mitzaehlt: "dass der Nutzer den
    vollen Schritt bewusst tun kann". Bewusst tun kann er nur, was er
    weiss.
    """
    sandbox.wrote(_document(base_available=[
        {"name": "linux", "from": "1", "to": "2"},
        {"name": "mesa", "from": "1", "to": "2"},
        {"name": "vim", "from": "1", "to": "2"}]))
    answer = sandbox.run()
    assert "3" in answer["text"], answer
    assert "updates-base" in answer["class"], answer


def test_the_regeneration_marker_wins_over_pending_arch_updates(
        sandbox: Sandbox) -> None:
    """Eine veraltete Konfiguration ist dringender als bereitliegende
    Pakete.

    Sie ist der Zustand, in dem der Nutzer gerade auf etwas sieht, das
    nicht mehr stimmt; die Arch-Pakete liegen nur da.
    """
    sandbox.wrote(_document(base_available=[
        {"name": "linux", "from": "1", "to": "2"}]))
    sandbox.marker()
    answer = sandbox.run()
    assert "updates-regenerate" in answer["class"], answer


def test_a_timer_that_fires_while_updates_are_off_says_so(
        sandbox: Sandbox) -> None:
    """Der Widerspruch, den update.py ausdruecklich in den Zustand
    schreibt, statt zu schweigen.

    Sein Kommentar dazu: "Wer den Zeitgeber von Hand einschaltet, obwohl
    die Einstellung false sagt, soll im Journal lesen koennen, warum
    nichts passiert ist." Ein Journal liest niemand.
    """
    sandbox.wrote(_document(result=update.Outcome.DISABLED))
    answer = sandbox.run()
    assert "updates-disabled" in answer["class"], answer


# --------------------------------------------------------------------
# Der Satz
# --------------------------------------------------------------------

def test_the_sentence_comes_from_the_module_itself(sandbox: Sandbox) -> None:
    """`zepos-update --status` und keine zweite Formulierung.

    Das Feld "detail" ist der Satz, den das KONTROLLZENTRUM zeigt. Ihn
    hier nachzubauen hiesse, dieselbe Auskunft ein zweites Mal zu
    formulieren, und beim naechsten Feld in update.py haette der Nutzer
    zwei Saetze, die einander widersprechen.
    """
    sandbox.stub("zepos-update", 'echo "Der Satz des Moduls."')
    sandbox.wrote(_document(base_available=[
        {"name": "linux", "from": "1", "to": "2"}]))
    assert sandbox.run()["detail"] == "Der Satz des Moduls."


def test_the_sentence_is_only_fetched_when_there_is_something_to_say(
        sandbox: Sandbox) -> None:
    """Ein Prozessstart je Takt fuer einen Satz, den niemand sieht,
    waere der Preis dafuer, ihn nicht zu brauchen."""
    marker = sandbox.root / "gerufen"
    sandbox.stub("zepos-update", f'touch {marker}\necho egal')
    sandbox.wrote(_document())
    sandbox.run()
    assert not marker.exists(), (
        "zepos-update wurde gerufen, obwohl nichts anstand")


def test_without_zepos_update_the_short_sentence_stands_in(
        sandbox: Sandbox) -> None:
    """Eine Maschine ohne zepos-config. Das Modul bleibt trotzdem
    lesbar - ein leeres Feld waere eine Zeile ohne Text."""
    sandbox.wrote(_document(base_available=[
        {"name": "linux", "from": "1", "to": "2"}]))
    answer = sandbox.run()
    assert answer["detail"] == answer["short"] != "", answer


def test_a_broken_state_document_is_silence_and_not_noise(
        sandbox: Sandbox) -> None:
    """Eine halb geschriebene Datei - ein Lauf, den jemand abgebrochen
    hat.

    `jq` scheitert daran, und das Skript darf davon nicht mehr melden
    als von einem leeren Zustand: eine Warnung, deren Ursache ein
    Dateisystemunfall ist, schickt den Nutzer in die falsche Richtung.
    """
    (sandbox.state / update.STATE_FILE).write_text('{"result": "fai')
    assert sandbox.run()["text"] == ""
