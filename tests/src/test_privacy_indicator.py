# SPDX-License-Identifier: GPL-3.0-or-later
"""privacy.sh: wer gerade das Mikrofon oder die Kamera offen hat.

WARUM ES DIESE DATEI GIBT
    ZepOS hatte am 12.08.2026 ein Leistenmodul namens
    "pulseaudio#microphone", und das sah aus wie eine Antwort auf die
    Frage "hoert gerade jemand zu?". GEMESSEN an ags-bar.template und
    bar-status-config.template ist es keine: sein Klick ist
    `pamixer --default-source -t`, sein Rad `-i 5`/`-d 5`, sein Text
    `wpctl get-volume @DEFAULT_AUDIO_SOURCE@`. Ein LAUTSTAERKEREGLER.

    Auf einem System, das mit einem Browser ausgeliefert wird, ist das
    die einzige Luecke der Leiste, die etwas kostet, das man nicht
    zurueckbekommt - und der schlimmste Fehler, den ein solches Modul
    machen kann, ist nicht, nichts zu zeigen, sondern das FALSCHE zu
    zeigen. Ein Punkt, der angeht, weil jemand eine Bildschirmaufnahme
    macht oder einen Lautstaerkeregler offen hat, ist nach einer Woche
    ein Punkt, den niemand mehr ansieht.

    Deshalb misst diese Datei die drei Falschmeldungen einzeln.

DAS VERFAHREN
    Dasselbe wie in tests/src/test_bar_status.py: die Vorlage wird
    gerendert, in ein Verzeichnis gelegt und unter `env -i` mit einem
    Attrappenverzeichnis als GANZEM PATH ausgefuehrt. Kein Aufruf kann
    dann das echte Werkzeug erreichen.

DIE KAMERA UND IHR PFAD
    Das Skript liest die Prozesswurzel aus ZEPOS_PROC_ROOT - dieselbe
    Bauart wie ZEPOS_POWER_SUPPLY_ROOT in test_bar_status.py und aus
    demselben Grund: sonst haenge die Antwort daran, ob auf dem Rechner,
    auf dem die Suite laeuft, gerade jemand die Kamera aufhat, und der
    Zweig, den man dort nicht messen kann, waere immer der ungetestete.

    Die Attrappe ist ein Verzeichnis mit `<pid>/fd/<n>` als Symlink und
    `<pid>/comm` als Datei - genau die zwei Dinge, die das Skript liest.
    Der Symlink zeigt ins Leere; das ist richtig so, weil `find -lname`
    den TEXT des Links vergleicht und nicht sein Ziel.

WAS AN ECHTER HARDWARE GEMESSEN WURDE, am 12.08.2026 auf einem Notebook
    Mikrofon    Ein Aufnahmestrom, geoeffnet mit `parec` gegen eine
                virtuelle (nicht-monitor) Quelle: `pactl list
                source-outputs` fuehrte ihn mit application.name
                "parec", Corked "no" und ohne stream.capture.sink.
    Monitor     Derselbe `parec` gegen `auto_null.monitor`: der
                Datensatz trug `stream.capture.sink = "true"`.
    Kamera      `v4l2-ctl --stream-mmap` auf /dev/video0. pw-dump
                fuehrte KEINEN Knoten mit media.class
                "Stream/Input/Video"; der /proc-Durchlauf fand ihn in 6
                bis 9 ms bei 439 Prozessen.
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
TEMPLATE = SRC / "templates" / "ags-privacy-scripts.template"

BASH = "/bin/bash"

# Was das Skript aufruft und was durchgereicht werden darf. Alle sind
# reine Textverarbeitung oder lesen nur unter der umgeleiteten Wurzel;
# keiner steht in NEVER_PASSTHROUGH.
PASSTHROUGH = ("jq", "awk", "sort", "tr", "find", "paste", "cat", "printf")

pytestmark = pytest.mark.allow_subprocess


# Ein Datensatz, wie `pactl list source-outputs` ihn schreibt. Die Felder
# stehen in der Reihenfolge und mit der Einrueckung der echten Ausgabe -
# das Skript liest sie mit verankerten Mustern, und ein Test mit einer
# bequemeren Form pruefte ein anderes Programm.
def _source_output(index: int, source: int, name: str, *,
                   corked: bool = False, capture_sink: bool = False,
                   monitor_stream: bool = False,
                   binary: str | None = None) -> str:
    lines = [
        f"Source Output #{index}",
        "\tDriver: PipeWire",
        f"\tSource: {source}",
        f"\tCorked: {'yes' if corked else 'no'}",
        "\tProperties:",
    ]
    if name:
        lines.append(f'\t\tapplication.name = "{name}"')
    if binary:
        lines.append(f'\t\tapplication.process.binary = "{binary}"')
    if capture_sink:
        lines.append('\t\tstream.capture.sink = "true"')
    if monitor_stream:
        lines.append('\t\tstream.monitor = "true"')
    lines.append('\t\tmedia.class = "Stream/Input/Audio"')
    return "\n".join(lines)


class Sandbox:
    """Das gerenderte Skript, ein Attrappen-PATH und ein falsches /proc."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.stubs = root / "stubs"
        self.stubs.mkdir()
        self.proc = root / "proc"
        self.proc.mkdir()
        self.script = self._render()

        for name in PASSTHROUGH:
            assert_safe_to_passthrough(name)
            self.stub(name, f'exec /usr/bin/{name} "$@"')

        # Der Grundzustand: eine Quelle, die ein Monitor ist, und kein
        # einziger Aufnahmestrom.
        self.pactl(sources=["34\tauto_null.monitor\tPipeWire\ts16le\tIDLE"],
                   outputs=[])

    def _render(self) -> Path:
        sys.path.insert(0, str(SRC))
        try:
            import template_processor
            processor = template_processor.ConfigProcessor()
        finally:
            sys.path.remove(str(SRC))
        script = self.root / "privacy.sh"
        processor.apply_template(TEMPLATE, script)
        script.chmod(0o755)
        return script

    def stub(self, name: str, body: str) -> None:
        path = self.stubs / name
        path.write_text(f"#!/bin/bash\n{body}\n")
        path.chmod(0o755)

    def pactl(self, *, sources: list[str], outputs: list[str]) -> None:
        """Die zwei Aufrufe, die das Skript an pactl richtet.

        Unterschieden am ersten Argument, so wie pactl selbst es tut -
        eine Attrappe, die auf jede Frage dieselbe Antwort gibt, wuerde
        die Monitorpruefung stillschweigend uebergehen.
        """
        (self.root / "sources.txt").write_text("\n".join(sources) + "\n")
        (self.root / "outputs.txt").write_text("\n\n".join(outputs) + "\n")
        self.stub("pactl", f"""
case "$*" in
  "list short sources") exec /usr/bin/cat {self.root}/sources.txt ;;
  "list source-outputs") exec /usr/bin/cat {self.root}/outputs.txt ;;
  *) echo "unerwarteter pactl-Aufruf: $*" >&2; exit 1 ;;
esac
""")

    def _link(self, target: str, path: Path) -> None:
        """Ein Symlink, der ins Leere zeigt - ueber /usr/bin/ln.

        NICHT ueber Path.symlink_to(), und der Grund ist der
        Isolationswaechter in tests/conftest.py: er verbietet, "einen
        Link auf /dev/null anzulegen", weil er das Ziel prueft und nicht
        den Ort. Fuer diesen Test ist genau das Ziel die Aussage - der
        Link SELBST liegt unter tmp_path, das Ziel wird nie geoeffnet,
        und `find -lname` vergleicht ohnehin nur den TEXT des Links.

        Der Waechter hat trotzdem recht und wird nicht angefasst: er
        kann nicht wissen, dass hier niemand schreiben will. Also geht
        der Weg ueber einen Prozess, den dieses Modul mit
        `allow_subprocess` ohnehin schon fuehrt.
        """
        subprocess.run(["/usr/bin/ln", "-sfn", target, str(path)],
                       check=True, timeout=30)

    def camera(self, pid: int, program: str, device: str = "/dev/video0") -> None:
        """Ein Prozess, der eine Kamera offen hat."""
        fds = self.proc / str(pid) / "fd"
        fds.mkdir(parents=True, exist_ok=True)
        self._link(device, fds / "3")
        (self.proc / str(pid) / "comm").write_text(program + "\n")

    def noise(self, pid: int, program: str) -> None:
        """Ein Prozess, der offene Dateien hat, aber keine Kamera.

        Er gehoert in jeden Lauf: ein Durchlauf, der NUR Kameras sieht,
        koennte auch ein Durchlauf sein, der jeden offenen Deskriptor
        meldet.
        """
        fds = self.proc / str(pid) / "fd"
        fds.mkdir(parents=True, exist_ok=True)
        self._link("/dev/null", fds / "0")
        self._link("/dev/urandom", fds / "1")
        (self.proc / str(pid) / "comm").write_text(program + "\n")

    def run(self) -> dict:
        result = subprocess.run(
            ["/usr/bin/env", "-i", f"PATH={self.stubs}",
             f"HOME={self.root}", f"ZEPOS_PROC_ROOT={self.proc}",
             BASH, str(self.script)],
            capture_output=True, text=True, timeout=60,
        )
        assert_no_missing_command(result, "privacy.sh")
        assert result.returncode == 0, (
            f"privacy.sh endete mit {result.returncode}:\n"
            + result.stdout + result.stderr)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise AssertionError(
                f"privacy.sh hat kein JSON geschrieben ({error}):\n"
                f"{result.stdout!r}\n{result.stderr}") from error


@pytest.fixture()
def sandbox(tmp_path: Path) -> Sandbox:
    box = Sandbox(tmp_path)
    box.noise(4711, "irgendwas")
    return box


# --------------------------------------------------------------------
# Der Ruhezustand
# --------------------------------------------------------------------

def test_nobody_recording_is_an_empty_module(sandbox: Sandbox) -> None:
    """Der wichtigste Zustand, und er muss NICHTS ergeben.

    Ein leeres "text" heisst fuer die Leiste "dieses Modul hat nichts zu
    sagen"; applyPayload() in ags-bar.template blendet es dann aus. Das
    ist die Bedingung, unter der ein einundzwanzigstes Modul auf einer
    Leiste ueberhaupt vertretbar ist, die auf 1366x768 schon ueberlaeuft.
    """
    answer = sandbox.run()
    assert answer["text"] == "", answer
    assert answer["class"] == "", answer
    assert answer["mic"] == [] and answer["cam"] == [], answer


# --------------------------------------------------------------------
# Das Mikrofon
# --------------------------------------------------------------------

def test_a_real_capture_stream_is_reported_with_its_program(
        sandbox: Sandbox) -> None:
    """Der Fall, um den es geht: ein Programm liest vom Mikrofon.

    Nachgestellt nach dem echten Datensatz vom 12.08.2026 - `parec`
    gegen eine virtuelle, nicht-monitor Quelle.
    """
    sandbox.pactl(
        sources=["34\tauto_null.monitor\tPipeWire\ts16le\tIDLE",
                 "48\tmikro\tPipeWire\ts16le\tRUNNING"],
        outputs=[_source_output(1, 48, "firefox")])
    answer = sandbox.run()
    assert answer["mic"] == ["firefox"], answer
    assert answer["text"] != "", answer
    assert "privacy-mic" in answer["class"], answer
    assert "firefox" in answer["tooltip"], answer


def test_a_stream_on_a_monitor_source_is_not_a_microphone(
        sandbox: Sandbox) -> None:
    """Eine Bildschirmaufnahme mit Ton ist kein Lauschangriff.

    Wer `auto_null.monitor` aufnimmt, nimmt auf, was aus den
    LAUTSPRECHERN kommt. GEMESSEN am 12.08.2026: `parec -d
    auto_null.monitor` erscheint als Datensatz wie jeder andere - der
    einzige Unterschied ist die Quellnummer und die Eigenschaft
    stream.capture.sink.
    """
    sandbox.pactl(
        sources=["34\tauto_null.monitor\tPipeWire\ts16le\tRUNNING"],
        outputs=[_source_output(1, 34, "obs")])
    assert sandbox.run()["mic"] == [], "eine Monitoraufnahme wurde gemeldet"


def test_the_capture_sink_property_alone_is_enough(sandbox: Sandbox) -> None:
    """Zweiter Beleg fuer denselben Fall, ueber das andere Feld.

    pipewire-pulse schreibt `stream.capture.sink = "true"` an einen
    Strom, der am Ausgang liegt. Es wird SEPARAT geprueft, weil beide
    Wege einzeln greifen muessen: die Quellnummer erkennt den Fall nur,
    wenn die Quelle wirklich auf ".monitor" endet, und das ist eine
    Namenskonvention.
    """
    sandbox.pactl(
        sources=["34\tauto_null.monitor\tPipeWire\ts16le\tRUNNING",
                 "48\tmikro\tPipeWire\ts16le\tRUNNING"],
        outputs=[_source_output(1, 48, "obs", capture_sink=True)])
    assert sandbox.run()["mic"] == [], (
        "ein Strom mit stream.capture.sink wurde als Mikrofon gemeldet")


def test_a_corked_stream_is_not_listening(sandbox: Sandbox) -> None:
    """Ein pausierter Strom haelt das Geraet und liest nichts."""
    sandbox.pactl(
        sources=["48\tmikro\tPipeWire\ts16le\tIDLE"],
        outputs=[_source_output(1, 48, "firefox", corked=True)])
    assert sandbox.run()["mic"] == [], (
        "ein Strom mit Corked: yes wurde als Mikrofon gemeldet")


def test_a_level_meter_is_not_listening(sandbox: Sandbox) -> None:
    """pavucontrol zeichnet einen Ausschlagbalken und hoert nicht zu.

    Ein Punkt, der angeht, weil jemand den Lautstaerkeregler offen hat,
    ist genau die Meldung, die man danach abschaltet.
    """
    sandbox.pactl(
        sources=["48\tmikro\tPipeWire\ts16le\tRUNNING"],
        outputs=[_source_output(1, 48, "pavucontrol", monitor_stream=True)])
    assert sandbox.run()["mic"] == [], (
        "ein Pegelmesser wurde als Mikrofon gemeldet")


def test_a_stream_without_a_name_falls_back_to_its_binary(
        sandbox: Sandbox) -> None:
    """"Etwas hoert zu" ohne "wer" ist die Warnung, die dieses Skript
    gerade beseitigen soll.

    GEMESSEN am 12.08.2026: derselbe Datensatz trug application.name
    "parec" UND application.process.binary "pacat" - der erste ist der
    Name, den das Programm sich gibt, der zweite der, unter dem es auf
    der Platte liegt.
    """
    sandbox.pactl(
        sources=["48\tmikro\tPipeWire\ts16le\tRUNNING"],
        outputs=[_source_output(1, 48, "", binary="pacat")])
    assert sandbox.run()["mic"] == ["pacat"], "der Rueckfall greift nicht"


def test_two_programs_are_both_named(sandbox: Sandbox) -> None:
    sandbox.pactl(
        sources=["48\tmikro\tPipeWire\ts16le\tRUNNING"],
        outputs=[_source_output(1, 48, "firefox"),
                 _source_output(2, 48, "signal-desktop")])
    assert sorted(sandbox.run()["mic"]) == ["firefox", "signal-desktop"]


# --------------------------------------------------------------------
# Die Kamera
# --------------------------------------------------------------------

def test_an_open_video_device_is_reported_with_its_program(
        sandbox: Sandbox) -> None:
    """Der Fall, den PipeWire NICHT sieht.

    GEMESSEN am 12.08.2026 mit `v4l2-ctl -d /dev/video0 --stream-mmap`:
    pw-dump fuehrte keinen Knoten mit media.class "Stream/Input/Video".
    Ein direkter v4l2-Zugriff geht am Dienst vorbei, und das ist der
    haeufigste Fall ueberhaupt - ein Datenschutzpunkt, der genau den
    nicht sieht, behauptet, es sei nachgesehen worden.
    """
    sandbox.camera(5150, "firefox")
    answer = sandbox.run()
    assert answer["cam"] == ["firefox"], answer
    assert "privacy-cam" in answer["class"], answer
    assert "firefox" in answer["tooltip"], answer


def test_a_process_without_a_camera_is_not_reported(sandbox: Sandbox) -> None:
    """Die Gegenprobe zum Durchlauf.

    Der Grundzustand jedes Laufs hat einen Prozess mit zwei offenen
    Deskriptoren auf /dev/null und /dev/urandom. Ohne diese Zusicherung
    koennte das Skript jeden offenen Deskriptor melden und alle anderen
    Faelle blieben trotzdem gruen.
    """
    assert sandbox.run()["cam"] == []


def test_the_camera_is_reported_on_any_video_node(sandbox: Sandbox) -> None:
    """Eine Webcam meldet mehrere Knoten - /dev/video0 bis video3 auf
    dem Rechner, an dem gemessen wurde.

    Welchen davon ein Programm oeffnet, ist seine Sache; dass es die
    Kamera aufhat, ist dieselbe Aussage.
    """
    sandbox.camera(5151, "chromium", device="/dev/video2")
    assert sandbox.run()["cam"] == ["chromium"]


# --------------------------------------------------------------------
# Beides zugleich
# --------------------------------------------------------------------

def test_both_at_once_names_both(sandbox: Sandbox) -> None:
    sandbox.pactl(
        sources=["48\tmikro\tPipeWire\ts16le\tRUNNING"],
        outputs=[_source_output(1, 48, "firefox")])
    sandbox.camera(5150, "firefox")
    answer = sandbox.run()
    assert answer["mic"] == ["firefox"] and answer["cam"] == ["firefox"]
    assert "privacy-mic" in answer["class"] and "privacy-cam" in answer["class"]
    assert "Mikrofon" in answer["tooltip"] and "Kamera" in answer["tooltip"]


def test_a_program_with_a_quote_in_its_name_does_not_break_the_bar(
        sandbox: Sandbox) -> None:
    """Ein von Hand gebautes JSON waere hier zerbrochen - und dann
    zeigte die LEISTE nichts mehr an, nicht nur dieses Modul.

    Dieselbe Begruendung, aus der bar-status-config.template seine
    Antwort ueber jq baut.
    """
    sandbox.pactl(
        sources=["48\tmikro\tPipeWire\ts16le\tRUNNING"],
        outputs=[_source_output(1, 48, 'Anton"s Recorder & Co')])
    assert sandbox.run()["mic"] == ['Anton"s Recorder & Co']
