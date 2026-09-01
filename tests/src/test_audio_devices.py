# SPDX-License-Identifier: GPL-3.0-or-later
"""audio-devices.sh: die Geraeteliste und der Wechsel zwischen Geraeten.

WORAUF DIESE DATEI ANTWORTET
    Der Nutzer am 22.08.2026, woertlich: "ich will pro ton und mikrofon
    auch das geraet waehlen koennen, falls mehrere angeschlossen sind.
    ok, das muss gehen."

    Bis dahin lief alles ueber @DEFAULT_AUDIO_SINK@ und
    @DEFAULT_AUDIO_SOURCE@ - ueber das, was WirePlumber gerade fuer
    richtig haelt. Es gab keine Auswahl.

DAS VERFAHREN
    Dasselbe wie in tests/src/test_bar_status.py: die Vorlage wird
    gerendert, in ein Verzeichnis gelegt und unter `env -i` mit einem
    Attrappenverzeichnis als GANZEM PATH ausgefuehrt. Kein Aufruf kann
    dann das echte Werkzeug erreichen.

    HIER IST DAS KEINE FORMSACHE, SONDERN DIE GANZE SICHERHEIT DIESER
    DATEI. Dieses Skript SCHREIBT: `wpctl set-default` stellt das
    Vorgabegeraet des laufenden Rechners um. Ein Durchreich-Stummel
    waere das echte Programm gegen den Tondienst dessen, der die Tests
    startet - mitten in seiner Arbeit. `wpctl` steht deshalb seit
    demselben Tag in conftest.NEVER_PASSTHROUGH; hier steht ausserdem
    ein eigener Test, der nachzaehlt, dass die Attrappe wirklich alles
    abfaengt.

DIE ATTRAPPE IST EIN KLEINER WIREPLUMBER
    Sie liest zwei Dateien - die Geraete und die beiden Vorgaben - und
    schreibt daraus die Ausgabe von `wpctl status` nach, samt
    Baumzeichen, Sternchen, Spaltenausrichtung und einem VIDEO-Abschnitt
    mit eigenen "Sinks:"/"Sources:"-Ueberschriften. `set-default`
    aendert die Vorgabedatei.

    Warum so und nicht mit festen Textbloecken: der WECHSEL und das
    VERSCHWINDEN eines Geraets sind Zustandsuebergaenge. Ein Test, der
    zwei feste Bloecke gegeneinander haelt, prueft, dass zwei Texte
    verschieden gelesen werden - nicht, dass ein Wechsel ankommt.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import assert_no_missing_command, assert_safe_to_passthrough

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
TEMPLATE = SRC / "templates" / "audio-devices-config.template"

BASH = "/bin/bash"

# Was das Skript ausser wpctl noch ruft. Dieselbe Regel wie in
# tests/src/test_bar_status.py: reine Textverarbeitung ueber Argumente,
# die alle aus diesem Test kommen, darf das echte Programm sein.
# `timeout` ist coreutils und wird durchgereicht, weil eine Attrappe die
# Frist nachbilden muesste - also genau das, was gemessen werden soll.
PASSTHROUGH = ("jq", "awk", "timeout", "printf", "cat")

pytestmark = pytest.mark.allow_subprocess


# --------------------------------------------------------------------
# die Attrappe
# --------------------------------------------------------------------

# Sie schreibt `wpctl status` nach. Der Aufbau ist der gemessene: eine
# Zeile der obersten Ebene ohne Einrueckung, darunter Ueberschriften mit
# Baumzeichen, darunter die Eintraege - "*" fuer die Vorgabe, die
# Kennung mit einem Punkt, der sprechende Name, und ganz rechts
# "[vol: 0.30]" oder "[vol: 0.30 MUTED]".
#
# Der VIDEO-Abschnitt steht bewusst mit drin und traegt eigene
# "Sinks:"/"Sources:"-Ueberschriften. Er ist der Grund, aus dem der
# Parser den Abschnitt der obersten Ebene mitfuehrt; ohne ihn im
# Prueftext waere genau dieser Teil ungemessen.
WPCTL_STUB = r"""
GERAETE="$STUBDIR/geraete"
VORGABE="$STUBDIR/vorgabe"
PROTOKOLL="$STUBDIR/protokoll"

echo "$*" >> "$PROTOKOLL"

eintraege() {
    local art="$1" gewaehlt
    gewaehlt=$(awk -F= -v art="$art" '$1 == art { print $2; exit }' "$VORGABE")
    awk -F'\t' -v art="$art" -v gewaehlt="$gewaehlt" '
        $1 != art { next }
        {
            marke = ($2 == gewaehlt) ? "*" : " "
            klammer = "[vol: " $4 ($5 == "1" ? " MUTED" : "") "]"
            printf " │  %s %4d. %-38s%s\n", marke, $2, $3, klammer
        }
    ' "$GERAETE"
}

status() {
    echo "PipeWire 'pipewire-0' [1.6.8, pruef@pruef, cookie:1]"
    echo " └─ Clients:"
    echo "        32. WirePlumber                         [1.6.8]"
    echo " │  "
    echo "Audio"
    echo " ├─ Devices:"
    echo " │  "
    echo " ├─ Sinks:"
    eintraege ausgabe
    echo " │  "
    echo " ├─ Sources:"
    eintraege eingabe
    echo " │  "
    echo " ├─ Filters:"
    echo " │  "
    echo " └─ Streams:"
    echo ""
    echo "Video"
    echo " ├─ Devices:"
    echo " │      70. Integrated Camera                   [v4l2]"
    echo " │  "
    echo " ├─ Sinks:"
    echo " │  "
    echo " ├─ Sources:"
    echo " │  *  71. Integrated Camera (V4L2)           "
    echo " │  "
    echo " ├─ Filters:"
    echo " │  "
    echo " └─ Streams:"
    echo ""
    echo "Settings"
    echo " └─ Default Configured Devices:"
}

case "$1" in
    status)
        status ;;
    set-default)
        art=$(awk -F'\t' -v kennung="$2" '$2 == kennung { print $1; exit }' "$GERAETE")
        if [ -z "$art" ]; then
            echo "Node $2 not found" >&2
            exit 1
        fi
        neu=$(awk -F= -v art="$art" -v kennung="$2" \
                  '{ if ($1 == art) print $1 "=" kennung; else print }' \
                  "$VORGABE")
        printf '%s\n' "$neu" > "$VORGABE"
        ;;
    *)
        echo "unknown wpctl command: $1" >&2
        exit 1 ;;
esac
"""


class Sandbox:
    """Ein gerendertes audio-devices.sh und ein Attrappen-wireplumber."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.stubs = root / "stubs"
        self.stubs.mkdir()
        self.script = self._render()
        self.geraete = self.stubs / "geraete"
        self.vorgabe = self.stubs / "vorgabe"
        self.protokoll = self.stubs / "protokoll"
        self.geraete.write_text("")
        self.vorgabe.write_text("ausgabe=\neingabe=\n")

        for name in PASSTHROUGH:
            assert_safe_to_passthrough(name)
            self.stub(name, f'exec /usr/bin/{name} "$@"')
        self.stub("wpctl", WPCTL_STUB)

    def _render(self) -> Path:
        sys.path.insert(0, str(SRC))
        try:
            import template_processor
            processor = template_processor.ConfigProcessor()
        finally:
            sys.path.remove(str(SRC))
        script = self.root / "audio-devices.sh"
        processor.apply_template(TEMPLATE, script)
        script.chmod(0o755)
        return script

    def stub(self, name: str, body: str) -> None:
        path = self.stubs / name
        path.write_text(f"#!/bin/bash\n{body}\n")
        path.chmod(0o755)

    def remove(self, name: str) -> None:
        """Ein Werkzeug GANZ wegnehmen - siehe die gleichnamige Methode
        in tests/src/test_bar_status.py: ein FEHLENDES Werkzeug ist ein
        unvollstaendiges System, ein SCHEITERNDES ein toter Dienst."""
        (self.stubs / name).unlink()

    # -- die Welt, die die Attrappe beschreibt --------------------------

    def geraet(self, art: str, kennung: int, name: str,
               volume: str = "0.50", muted: bool = False) -> None:
        with self.geraete.open("a") as handle:
            handle.write(f"{art}\t{kennung}\t{name}\t{volume}\t"
                         f"{'1' if muted else '0'}\n")

    def entferne_geraet(self, kennung: int) -> None:
        """Ein Geraet verschwindet - der Kopfhoerer wird abgezogen."""
        zeilen = [zeile for zeile in self.geraete.read_text().splitlines()
                  if zeile.split("\t")[1] != str(kennung)]
        self.geraete.write_text("".join(zeile + "\n" for zeile in zeilen))

    def setze_vorgabe(self, ausgabe: str = "", eingabe: str = "") -> None:
        self.vorgabe.write_text(f"ausgabe={ausgabe}\neingabe={eingabe}\n")

    # -- Laeufe ---------------------------------------------------------

    def run_raw(self, *argumente: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["/usr/bin/env", "-i", f"PATH={self.stubs}",
             f"HOME={self.root}", f"STUBDIR={self.stubs}",
             BASH, str(self.script), *argumente],
            capture_output=True, text=True, timeout=60)

    def liste(self) -> dict:
        result = self.run_raw("list")
        assert_no_missing_command(result, "audio-devices.sh")
        assert result.returncode == 0, (
            f"list endete mit {result.returncode}:\n"
            + result.stdout + result.stderr)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise AssertionError(
                f"list hat kein JSON geschrieben ({error}):\n"
                f"{result.stdout!r}\n{result.stderr}") from error

    def wpctl_aufrufe(self) -> list[str]:
        if not self.protokoll.exists():
            return []
        return self.protokoll.read_text().splitlines()


@pytest.fixture
def sandbox(tmp_path) -> Sandbox:
    return Sandbox(tmp_path)


@pytest.fixture
def zwei_und_zwei(sandbox) -> Sandbox:
    """Der Fall, den der Nutzer beschreibt: mehrere sind angeschlossen."""
    sandbox.geraet("ausgabe", 45, "Kopfhörer am USB-Anschluss", "0.30")
    sandbox.geraet("ausgabe", 51, "Internes Audio Analog Stereo", "0.80")
    sandbox.geraet("eingabe", 57, "Headset-Mikrofon", "0.15")
    sandbox.geraet("eingabe", 60, "Internes Mikrofon", "0.65", muted=True)
    sandbox.setze_vorgabe(ausgabe="45", eingabe="57")
    return sandbox


# --------------------------------------------------------------------
# mehrere Geraete
# --------------------------------------------------------------------

def test_several_devices_are_all_listed_with_their_own_volume(zwei_und_zwei):
    """Die Liste, aus der die Auswahl gebaut wird.

    Sie traegt JE GERAET die eigene Lautstaerke - nicht nur die des
    Vorgabegeraets. Genau daran haengt Punkt 4 des Auftrags: der Regler
    im Kontrollzentrum nimmt seinen Wert aus DERSELBEN Antwort, die
    sagt, welches Geraet gewaehlt ist, und kann deshalb nach einem
    Wechsel nichts Falsches zeigen.
    """
    antwort = zwei_und_zwei.liste()

    assert antwort["dienst"] == "da", antwort
    assert [eintrag["kennung"] for eintrag in antwort["ausgabe"]] == [45, 51]
    assert [eintrag["kennung"] for eintrag in antwort["eingabe"]] == [57, 60]

    lautstaerken = {eintrag["kennung"]: eintrag["lautstaerke"]
                    for eintrag in antwort["ausgabe"] + antwort["eingabe"]}
    assert lautstaerken == {45: 30, 51: 80, 57: 15, 60: 65}, antwort


def test_the_names_are_the_ones_a_person_recognises(zwei_und_zwei):
    """`node.description` und nicht `node.name`.

    "alsa_output.pci-0000_00_1f.3.analog-stereo" ist kein Geraetename.
    WirePlumber setzt einen sprechenden zusammen und UEBERSETZT ihn
    sogar - gemessen am 22.08.2026 in
    /usr/share/locale/de/LC_MESSAGES/wireplumber.mo, das genau fuenf
    Eintraege hat und alle fuenf sind Geraetenamen ("Built-in Audio" ->
    "Internes Audio").

    Der Umlaut im Prueftext ist Absicht: die Antwort geht durch awk und
    jq, und beide muessen sie unversehrt durchlassen.
    """
    namen = [eintrag["name"] for eintrag in zwei_und_zwei.liste()["ausgabe"]]

    assert namen == ["Kopfhörer am USB-Anschluss",
                     "Internes Audio Analog Stereo"], namen


def test_exactly_one_device_is_marked_as_the_default_per_direction(zwei_und_zwei):
    """Das Sternchen von `wpctl status`, und zwar je Richtung eines.

    Ohne diese Zusicherung koennte die Liste jede Zeile als "aktiv"
    zeichnen oder keine - und die Seite saehe in beiden Faellen aus wie
    eine, die nur nichts hervorhebt.
    """
    antwort = zwei_und_zwei.liste()

    for richtung in ("ausgabe", "eingabe"):
        gewaehlt = [eintrag["kennung"] for eintrag in antwort[richtung]
                    if eintrag["vorgabe"]]
        assert len(gewaehlt) == 1, (richtung, antwort[richtung])
    assert [e["kennung"] for e in antwort["ausgabe"] if e["vorgabe"]] == [45]
    assert [e["kennung"] for e in antwort["eingabe"] if e["vorgabe"]] == [57]


def test_a_muted_device_says_so_without_losing_its_number(zwei_und_zwei):
    """"[vol: 0.65 MUTED]" ist ZWEI Angaben und nicht eine.

    Die Zahl ist die EINSTELLUNG, "stumm" der Zustand - dieselbe
    Unterscheidung, die audio_module() in bar-status-config.template am
    19.08.2026 gekostet hat. Ein Parser, der bei MUTED die Lautstaerke
    fallen laesst, laesst den Regler beim Stummschalten auf null
    springen.
    """
    intern = [eintrag for eintrag in zwei_und_zwei.liste()["eingabe"]
              if eintrag["kennung"] == 60][0]

    assert intern["stumm"] is True, intern
    assert intern["lautstaerke"] == 65, intern


def test_the_camera_is_not_an_audio_device(zwei_und_zwei):
    """`wpctl status` fuehrt "Sinks:" und "Sources:" ZWEIMAL.

    Einmal unter "Audio" und einmal unter "Video". Ein Parser, der nur
    auf die Ueberschrift sieht, zaehlt die Kamera als Tonquelle - und
    ein Klick darauf stellte dann die Vorgabe fuer VIDEO um. Die
    Attrappe schreibt darum einen vollstaendigen Video-Abschnitt mit;
    hier steht, dass nichts daraus in der Antwort landet.
    """
    antwort = zwei_und_zwei.liste()

    kennungen = [eintrag["kennung"]
                 for eintrag in antwort["ausgabe"] + antwort["eingabe"]]
    assert 70 not in kennungen, antwort
    assert 71 not in kennungen, antwort


# --------------------------------------------------------------------
# ein Geraet, kein Geraet
# --------------------------------------------------------------------

def test_a_single_device_is_still_reported(sandbox):
    """EIN Geraet ist eine Auskunft und keine Auswahl.

    Das Skript verschweigt es NICHT - es nennt es mit Namen und
    Lautstaerke. Ob daraus eine Liste wird, entscheidet die Oberflaeche:
    zeichneWahl() in ags-control-center.template zeigt sie erst ab zwei
    Eintraegen, und der Name steht dann im Seitenkopf.

    Die Trennung ist Absicht. Ein Skript, das bei einem Geraet nichts
    meldet, koennte den Kopf nicht beschriften - und "welches Geraet
    spielt gerade" ist die Frage, die auch ohne Wahl eine Antwort hat.
    """
    sandbox.geraet("ausgabe", 34, "Internes Audio", "1.00")
    sandbox.setze_vorgabe(ausgabe="34")

    antwort = sandbox.liste()

    assert len(antwort["ausgabe"]) == 1, antwort
    assert antwort["ausgabe"][0]["name"] == "Internes Audio"
    assert antwort["ausgabe"][0]["vorgabe"] is True
    assert antwort["eingabe"] == [], antwort


def test_a_machine_without_any_audio_device_answers_with_empty_lists(sandbox):
    """Der Dienst antwortet, es gibt nur nichts.

    Das ist NICHT derselbe Zustand wie ein toter Tondienst, und die
    beiden auseinanderzuhalten ist der Grund, aus dem `dienst` im
    Ergebnis steht: der eine ist ein Rechner ohne Tonkarte, der andere
    ein Rechner, auf dem etwas kaputt ist.
    """
    antwort = sandbox.liste()

    assert antwort == {"dienst": "da", "ausgabe": [], "eingabe": []}, antwort


# --------------------------------------------------------------------
# der Wechsel
# --------------------------------------------------------------------

def test_switching_the_output_moves_the_default_and_the_volume_with_it(
        zwei_und_zwei):
    """Der Kern des Auftrags, und Punkt 4 gleich mit.

    Nach dem Wechsel ist das gewaehlte Geraet die Vorgabe UND die
    Antwort traegt seine eigene Lautstaerke (80 % statt der 30 % des
    alten). Der Regler im Kontrollzentrum liest genau diese Zahl, also
    kann er nach dem Wechsel nicht mehr den alten Wert zeigen.

    GEMESSEN am 22.08.2026 an einer eigenen, privaten PipeWire-Instanz
    (nicht an der Sitzung des Nutzers): `set-sink` kehrt nach 21,5 ms
    zurueck, die naechste Liste 15,4 ms spaeter nennt bereits das neue
    Geraet mit 77 % statt 55 %.
    """
    vorher = zwei_und_zwei.liste()
    assert [e["kennung"] for e in vorher["ausgabe"] if e["vorgabe"]] == [45]

    result = zwei_und_zwei.run_raw("set-sink", "51")
    assert_no_missing_command(result, "audio-devices.sh")
    assert result.returncode == 0, result.stdout + result.stderr

    nachher = zwei_und_zwei.liste()
    gewaehlt = [e for e in nachher["ausgabe"] if e["vorgabe"]]
    assert [e["kennung"] for e in gewaehlt] == [51], nachher
    assert gewaehlt[0]["lautstaerke"] == 80, gewaehlt
    # Und die Eingabe hat der Ausgabewechsel NICHT angefasst.
    assert [e["kennung"] for e in nachher["eingabe"] if e["vorgabe"]] == [57]


def test_switching_the_input_leaves_the_output_alone(zwei_und_zwei):
    """Zwei Richtungen, zwei Vorgaben - der Nutzer nennt beide.

    "pro ton und mikrofon" heisst: getrennt. Ein Wechsel beim Mikrofon,
    der nebenbei den Lautsprecher umstellt, waere derselbe Fehler wie
    gar keine Wahl, nur schwerer zu bemerken.
    """
    zwei_und_zwei.run_raw("set-source", "60")

    nachher = zwei_und_zwei.liste()

    assert [e["kennung"] for e in nachher["eingabe"] if e["vorgabe"]] == [60]
    assert [e["kennung"] for e in nachher["ausgabe"] if e["vorgabe"]] == [45]


def test_the_switch_goes_through_wpctl_set_default(zwei_und_zwei):
    """Womit umgeschaltet wird, steht hier und nicht nur im Kommentar.

    `wpctl set-default` und nicht ein selbstgeschriebenes
    `pw-metadata default.audio.sink`: der WUNSCH des Nutzers steht in
    `default.configured.audio.sink`, `default.audio.sink` ist
    WirePlumbers Antwort darauf. GEMESSEN am 22.08.2026 an der privaten
    Instanz - ein `wpctl set-default` schreibt beide, in dieser
    Reihenfolge. Wer selbst schreibt und den zweiten Schluessel nimmt,
    setzt eine Vorgabe, die beim naechsten Nachdenken des Dienstes
    wieder verschwindet.
    """
    zwei_und_zwei.run_raw("set-sink", "51")

    aufrufe = zwei_und_zwei.wpctl_aufrufe()

    assert "set-default 51" in aufrufe, aufrufe
    assert not any(zeile.startswith("set-volume") for zeile in aufrufe), (
        "der Wechsel hat an der Lautstaerke gedreht: " + str(aufrufe))
    assert not any(zeile.startswith("set-mute") for zeile in aufrufe), (
        "der Wechsel hat stumm geschaltet: " + str(aufrufe))


def test_an_id_from_the_other_direction_is_refused(zwei_und_zwei):
    """Der Waechter, ohne den ein Klick die Kamera umstellen koennte.

    `wpctl set-default` nimmt JEDE Knotenkennung, auch die einer Kamera.
    Und Kennungen sind fluechtig: zwischen dem Zeichnen der Liste und
    dem Klick kann ein Geraet verschwunden und seine Nummer neu vergeben
    worden sein. Deshalb wird die Liste unmittelbar vor dem Wechsel noch
    einmal gelesen und die Kennung in DER GEFRAGTEN RICHTUNG gesucht.
    """
    result = zwei_und_zwei.run_raw("set-sink", "57")

    assert result.returncode != 0, result.stdout
    assert "Richtung" in result.stderr, result.stderr
    assert "set-default" not in " ".join(zwei_und_zwei.wpctl_aufrufe()), (
        "die Kennung der falschen Richtung ist trotzdem durchgereicht "
        "worden: " + str(zwei_und_zwei.wpctl_aufrufe()))


def test_an_unknown_id_is_refused_and_says_which(zwei_und_zwei):
    """Ein Geraet, das zwischen Liste und Klick verschwunden ist."""
    result = zwei_und_zwei.run_raw("set-sink", "9999")

    assert result.returncode != 0, result.stdout
    assert "9999" in result.stderr, result.stderr
    assert "set-default" not in " ".join(zwei_und_zwei.wpctl_aufrufe())


def test_something_that_is_not_a_number_never_reaches_wpctl(zwei_und_zwei):
    """Was aus der Oberflaeche kommt, wird an der Grenze geprueft.

    Die Kennung kommt aus einem JSON-Feld, das dieses Skript selbst
    geschrieben hat - und genau deshalb ist die Pruefung hier billig und
    ihr Fehlen teuer: sie ist die einzige Stelle, an der aus dem Wert
    ein Argument fuer ein fremdes Programm wird.
    """
    result = zwei_und_zwei.run_raw("set-source", "; rm -rf /")

    assert result.returncode != 0, result.stdout
    assert zwei_und_zwei.wpctl_aufrufe() == [], (
        "wpctl ist trotzdem gerufen worden: "
        + str(zwei_und_zwei.wpctl_aufrufe()))


def test_an_unknown_subcommand_explains_itself(sandbox):
    """Ein Skript, das seinen eigenen Pfad ausgibt, hat nicht geantwortet
    - siehe runScript() in ags-control-center.template. Hier steht, dass
    die Hinweiszeile auf stderr geht und der Rueckgabewert sie begleitet,
    damit kein Aufrufer sie fuer eine Antwort haelt."""
    result = sandbox.run_raw("quatsch")

    assert result.returncode != 0, result.stdout
    assert result.stdout.strip() == "", result.stdout
    assert "Usage:" in result.stderr, result.stderr


# --------------------------------------------------------------------
# das Geraet verschwindet
# --------------------------------------------------------------------

def test_when_the_chosen_device_disappears_wireplumber_picks_and_we_follow(
        zwei_und_zwei):
    """Der Kopfhoerer wird abgezogen.

    WirePlumber waehlt dann selbst ein anderes Geraet. Die Liste muss
    das mitbekommen - und zwar vollstaendig: das verschwundene Geraet
    steht nicht mehr drin, und das neue traegt das Sternchen UND SEINE
    EIGENE Lautstaerke.

    Die Leiste erfaehrt es unabhaengig davon sofort. GEMESSEN am
    22.08.2026 an der privaten Instanz: nach dem Wegfall des Knotens
    kamen ZWEI Meldungen - `object-removed` und, 0,5 ms spaeter, ein
    `changed` auf der Metadata "default" mit dem neuen
    `default.audio.sink`. Siehe VORGABE_METADATEN in ags-bar.template.
    """
    zwei_und_zwei.entferne_geraet(45)
    zwei_und_zwei.setze_vorgabe(ausgabe="51", eingabe="57")

    antwort = zwei_und_zwei.liste()

    assert [e["kennung"] for e in antwort["ausgabe"]] == [51], antwort
    assert antwort["ausgabe"][0]["vorgabe"] is True, antwort
    assert antwort["ausgabe"][0]["lautstaerke"] == 80, antwort


def test_when_the_last_device_disappears_the_direction_goes_empty(
        zwei_und_zwei):
    """Und wenn gar keines mehr da ist, bleibt die Richtung leer - nicht
    stehen. Eine Liste, die das letzte Geraet behaelt, waere die
    gefaehrlichere Luege: sie boete einen Klick auf etwas an, das es
    nicht mehr gibt."""
    zwei_und_zwei.entferne_geraet(45)
    zwei_und_zwei.entferne_geraet(51)
    zwei_und_zwei.setze_vorgabe(ausgabe="", eingabe="57")

    antwort = zwei_und_zwei.liste()

    assert antwort["ausgabe"] == [], antwort
    assert len(antwort["eingabe"]) == 2, antwort


# --------------------------------------------------------------------
# die drei Zustaende des Dienstes
# --------------------------------------------------------------------

def test_a_sound_server_that_does_not_answer_is_named_as_such(sandbox):
    """`wpctl` ist da, der Dienst antwortet nicht.

    Dieselbe Unterscheidung wie in bar-status-config.template, und aus
    demselben Grund: "es gibt hier kein Tongeraet" und "der Tondienst
    ist tot" sehen auf dem Bildschirm gleich aus - naemlich nach nichts
    -, und nur der zweite ist etwas, das man reparieren kann.
    """
    sandbox.stub("wpctl", "exit 1")

    antwort = sandbox.liste()

    assert antwort["dienst"] == "stumm", antwort
    assert antwort["ausgabe"] == [] and antwort["eingabe"] == [], antwort


def test_a_missing_tool_is_a_different_state_from_a_dead_service(sandbox):
    """Fehlt `wpctl`, ist nicht der Dienst tot, sondern das Paket nicht
    installiert. Das Kontrollzentrum sagt dann "wireplumber ist nicht
    installiert" statt "der Tondienst antwortet nicht" - zwei
    verschiedene Wege aus dem Problem heraus."""
    sandbox.remove("wpctl")

    antwort = sandbox.liste()

    assert antwort["dienst"] == "fehlt", antwort


def test_the_switch_refuses_when_the_service_is_not_there(sandbox):
    """Kein Umschalten ins Leere.

    Ohne diese Pruefung liefe `wpctl set-default` in seinen eigenen
    Fehler, und das Kontrollzentrum bekaeme dessen englischen Text zu
    sehen statt eines Satzes, der sagt, was zu tun ist.
    """
    sandbox.stub("wpctl", "exit 1")

    result = sandbox.run_raw("set-sink", "45")

    assert result.returncode != 0, result.stdout
    assert "wireplumber" in result.stderr, result.stderr


# --------------------------------------------------------------------
# die Form der Antwort und die Sprache, in der gefragt wird
# --------------------------------------------------------------------

def test_the_answer_is_always_a_json_object_with_the_same_three_keys(sandbox):
    """Auch dann, wenn nichts zu melden ist.

    Das Kontrollzentrum liest `geraete.ausgabe` und `geraete.eingabe`.
    Ein fehlender Schluessel waere dort dasselbe wie eine leere Liste -
    nur ohne Fehler, an dem sich das bemerken liesse. `dienst` fehlt in
    KEINEM Zweig, weil die Seite genau daran ihre Klage aufhaengt.
    """
    for aufbau in (lambda: None,
                   lambda: sandbox.stub("wpctl", "exit 1"),
                   lambda: sandbox.remove("wpctl")):
        aufbau()
        antwort = sandbox.liste()
        assert sorted(antwort) == ["ausgabe", "dienst", "eingabe"], antwort
        assert isinstance(antwort["ausgabe"], list), antwort
        assert isinstance(antwort["eingabe"], list), antwort


def test_wpctl_is_asked_in_a_language_the_parser_knows(sandbox):
    """LC_ALL=C vor jedem wpctl-Aufruf.

    Die Ueberschriften und das Wort "MUTED" sind das, worauf dieses
    Skript parst; sie duerfen nicht an der Sprache des Aufrufers
    haengen. Und es kostet den GERAETENAMEN nicht: GEMESSEN am
    22.08.2026 gegen die laufende Sitzung zeigt `LC_ALL=C wpctl status`
    das Geraet weiterhin als "Schein-Ausgabe" - der Name entsteht im
    Dienst und steht in node.description, wpctl gibt ihn nur weiter.

    tests/src/test_locale.py laesst LC_ALL=C ausdruecklich zu und
    verbietet nur eine ANZEIGESPRACHE; hier steht, dass die Angabe
    ueberhaupt da ist.
    """
    quelle = sandbox.script.read_text(encoding="utf-8")
    zeilen = [zeile.strip() for zeile in quelle.splitlines()
              if "timeout" in zeile and not zeile.strip().startswith("#")]

    assert zeilen, "kein Aufruf mit Frist gefunden - die Suche misst nichts"
    for zeile in zeilen:
        assert "LC_ALL=C" in zeile, (
            "ein Aufruf an wpctl ohne feste Sprache: " + zeile)


def test_every_wpctl_call_carries_a_deadline(sandbox):
    """`wpctl` wartet auf wireplumber, ohne Zeitgrenze.

    Dieselbe Messung, die bar-status-config.template am 17.08.2026
    seinen `frag`-Wrapper gebracht hat ("wenn ich das ausfuehre stuckt
    er freeze es passiert nichts"). Hier haengt weniger dran - eine
    Seite statt der halben Leiste -, aber es haengt an derselben
    Bibliothek, und ein Kontrollzentrum, das beim Oeffnen der Ton-Seite
    stehenbleibt, ist genauso kaputt.
    """
    quelle = sandbox.script.read_text(encoding="utf-8")
    # `wpctl` an einer BEFEHLSSTELLE, also nicht in einem Text. Die
    # Vorlage nennt das Programm auch in Meldungen ("wpctl ist nicht
    # installiert"), und eine Suche nach der blossen Zeichenfolge
    # zaehlte die als Aufruf mit - sie waere dann nur noch dadurch gruen
    # zu bekommen, dass man den Namen aus der Meldung nimmt.
    befehlsstelle = re.compile(r"""(?<![\w"'-])wpctl\s""")
    roh = [zeile.strip() for zeile in quelle.splitlines()
           if befehlsstelle.search(zeile)
           and not zeile.strip().startswith("#")
           and "frag wpctl" not in zeile
           and "command -v wpctl" not in zeile]

    assert roh == [], (
        "diese Aufrufe an wpctl haben keine Frist: " + "; ".join(roh))


def test_the_deadline_guard_would_catch_a_bare_call():
    """Und der Waechter darueber faengt wirklich etwas.

    Ohne diese Gegenprobe koennte sein regulaerer Ausdruck an jeder
    Zeile vorbeigehen und der Test waere trotzdem gruen - genau die
    Sorte Zusicherung, die nichts misst.
    """
    befehlsstelle = re.compile(r"""(?<![\w"'-])wpctl\s""")

    # Die beiden Formen, die AUFRUFE sind:
    assert befehlsstelle.search('    wpctl set-default "$kennung"')
    assert befehlsstelle.search('raw=$(wpctl get-volume "$node")')
    # Und die beiden, die keine sind:
    assert not befehlsstelle.search('echo "wpctl ist nicht installiert"')
    assert not befehlsstelle.search("printf '%s' \"wpctl ist nicht da\"")


def test_the_stub_really_catches_everything(zwei_und_zwei):
    """Die Zusicherung unter allen anderen dieser Datei.

    Jede Aussage hier ruht darauf, dass KEIN Aufruf das echte wpctl
    erreicht - sonst haette ein Testlauf das Vorgabegeraet dessen
    umgestellt, der ihn gestartet hat. Gemessen wird das am Protokoll
    der Attrappe: es enthaelt jeden Aufruf, und ein Lauf, der sie
    umgeht, hinterliesse dort eine Luecke.
    """
    zwei_und_zwei.liste()
    zwei_und_zwei.run_raw("set-sink", "51")
    zwei_und_zwei.liste()

    aufrufe = zwei_und_zwei.wpctl_aufrufe()

    # zweimal `status` je Liste (Dienstprobe und Tabelle), plus die
    # Probe und die Tabelle des Wechsels und das set-default selbst.
    assert aufrufe.count("set-default 51") == 1, aufrufe
    assert aufrufe.count("status") == len(aufrufe) - 1, aufrufe
    assert len(aufrufe) >= 6, (
        "zu wenige Aufrufe protokolliert - erreicht ein Weg das echte "
        "wpctl?: " + str(aufrufe))
