# SPDX-License-Identifier: GPL-3.0-or-later
"""status.sh: die fuenf Angaben, die waybar eingebaut hatte.

WARUM ES DIESE DATEI GIBT
    Ton, Mikrofon, Akku, Netz und Bluetooth waren in waybar
    C++-Module - kompiliert, ohne Prozessstart, und ohne dass dieses
    Projekt eine Zeile davon besass. In der AGS-Leiste kommt jede Angabe
    aus einem Aufruf, also sind es jetzt unsere fuenf Antworten, und sie
    haben denselben Anspruch wie jedes andere erzeugte Skript hier: sie
    werden AUSGEFUEHRT und nicht gelesen.

DAS VERFAHREN
    Dasselbe wie in tests/src/test_network_watchdog.py: die Vorlage wird
    gerendert, in ein Verzeichnis gelegt und unter `env -i` mit einem
    Attrappenverzeichnis als GANZEM PATH ausgefuehrt. Kein Aufruf kann
    dann das echte Werkzeug erreichen, und ein Werkzeug, das niemand
    nachgebaut hat, wird zu "command not found" statt zu einer leeren
    Antwort, die wie ein Messergebnis aussieht - siehe
    assert_no_missing_command() in tests/conftest.py.

DER AKKU UND SEIN PFAD
    `[ -r /sys/class/power_supply/BAT0/capacity ]` beantwortet bash
    selbst; kein Attrappenverzeichnis kommt dazwischen. Das Skript liest
    die Wurzel deshalb aus ZEPOS_POWER_SUPPLY_ROOT - dieselbe Bauart wie
    ZEPOS_PLUGIN_ROOT in tests/src/test_reference_resolution.py und aus
    demselben Grund: sonst haengt die Antwort daran, ob der Rechner, auf
    dem die Suite laeuft, einen Akku hat, und der Zweig, den man dort
    gerade nicht messen kann, waere immer der ungetestete.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.conftest import assert_no_missing_command

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
TEMPLATE = SRC / "templates" / "bar-status-config.template"

BASH = "/bin/bash"

# Was das Skript aufruft. jq ist ein Sonderfall: es ist reine
# Textverarbeitung ueber Argumente, die alle aus diesem Test kommen, also
# darf es das echte sein - dieselbe Regel und dieselbe Begruendung wie in
# tests/conftest.py unter NEVER_PASSTHROUGH, das jq nicht nennt.
PASSTHROUGH = ("jq", "awk", "cat", "grep", "cut", "head", "printf", "tr",
               "sed", "wc", "date",
               # timeout, seit dem 17.08.2026: das Skript umschliesst
               # jeden Aufruf an ein fremdes Werkzeug damit.
               #
               # WARUM ES DURCHGEREICHT UND NICHT NACHGEBAUT WIRD
               #     Eine Attrappe muesste die Frist selbst nachbilden -
               #     also genau das Verhalten, das hier geprueft werden
               #     soll. Sie waere damit die zweite Fassung dessen, was
               #     gemessen wird, und ein Fehler in ihr saehe aus wie
               #     ein Fehler im Skript. timeout ist coreutils und auf
               #     jedem Arch vorhanden, so gut wie `cat` daneben.
               "timeout")

pytestmark = pytest.mark.allow_subprocess


def _render(target: Path) -> Path:
    sys.path.insert(0, str(SRC))
    try:
        import template_processor
        processor = template_processor.ConfigProcessor()
    finally:
        sys.path.remove(str(SRC))
    script = target / "status.sh"
    processor.apply_template(TEMPLATE, script)
    script.chmod(0o755)
    return script


class Sandbox:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.stubs = root / "stubs"
        self.stubs.mkdir()
        self.script = _render(root)

        from tests.conftest import assert_safe_to_passthrough
        for name in PASSTHROUGH:
            assert_safe_to_passthrough(name)
            real = f"/usr/bin/{name}"
            self.stub(name, f'exec {real} "$@"')

    def stub(self, name: str, body: str) -> None:
        path = self.stubs / name
        path.write_text(f"#!/bin/bash\n{body}\n")
        path.chmod(0o755)

    def battery(self, **files: str) -> None:
        """Einen Akku (oder keinen) unter der umgeleiteten Wurzel anlegen."""
        target = self.root / "power" / "BAT0"
        target.mkdir(parents=True, exist_ok=True)
        for name, value in files.items():
            (target / name).write_text(value + "\n")

    def remove(self, name: str) -> None:
        """Ein Werkzeug GANZ wegnehmen - nicht scheitern lassen.

        Der Unterschied ist seit dem 13.08.2026 einer, den das Skript
        macht: ein Werkzeug, das FEHLT, ist ein unvollstaendiges System;
        eines, das SCHEITERT, ein Dienst, der nicht laeuft. Ohne diese
        Methode liesse sich der erste Fall gar nicht nachstellen, und
        genau er ist der wahrscheinlichste auf einer Maschine, auf der
        etwas nicht installiert wurde.
        """
        (self.stubs / name).unlink()

    def run_raw(self) -> subprocess.CompletedProcess:
        """Der Lauf, ohne Erwartung an seinen Ausgang."""
        return subprocess.run(
            ["/usr/bin/env", "-i", f"PATH={self.stubs}",
             f"HOME={self.root}",
             f"ZEPOS_POWER_SUPPLY_ROOT={self.root / 'power'}",
             BASH, str(self.script)],
            capture_output=True, text=True, timeout=60,
        )

    def run(self) -> dict:
        result = self.run_raw()
        assert_no_missing_command(result, "status.sh")
        assert result.returncode == 0, (
            f"status.sh endete mit {result.returncode}:\n"
            + result.stdout + result.stderr)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise AssertionError(
                f"status.sh hat kein JSON geschrieben ({error}):\n"
                f"{result.stdout!r}\n{result.stderr}") from error


def _quiet(sandbox: Sandbox) -> None:
    """Jedes Werkzeug antwortet "nichts da". Der Grundzustand.

    `wpctl exit 1` heisst seit dem 13.08.2026 etwas Bestimmtes: das
    Programm ist da und der Dienst dahinter antwortet nicht. Das ist der
    DRITTE Zustand (siehe den Kopf der Vorlage) und nicht mehr
    dasselbe wie "es gibt hier kein Tongeraet" - dafuer gibt es
    _sound_without_devices() darunter.
    """
    sandbox.stub("wpctl", "exit 1")
    sandbox.stub("nmcli", "exit 0")
    sandbox.stub("bluetoothctl", "exit 1")


def _sound_without_devices(sandbox: Sandbox) -> None:
    """wireplumber laeuft und hat weder Ausgabe noch Eingabe.

    `status` antwortet, `get-volume` nicht - genau die Lage auf einem
    Rechner ohne Tonkarte oder ohne Mikrofon.
    """
    sandbox.stub("wpctl", r"""
case "$1" in
    status) exit 0 ;;
    *) exit 1 ;;
esac
""")


@pytest.fixture
def sandbox(tmp_path) -> Sandbox:
    box = Sandbox(tmp_path)
    _quiet(box)
    return box


# --------------------------------------------------------------------
# die Form der Antwort
# --------------------------------------------------------------------

def test_the_answer_always_carries_all_five_modules(sandbox):
    """Fuenf Schluessel, immer, auch wenn keiner etwas zu sagen hat.

    Die Leiste liest `payloads[sink.key] ?? {}`. Ein fehlender Schluessel
    waere also dasselbe wie ein leerer - nur dass die Leiste den Kasten
    dann NIE wieder fuellt, weil kein Fehler auftritt, an dem sich das
    bemerken liesse.
    """
    answer = sandbox.run()
    assert sorted(answer) == ["audio", "battery", "bluetooth", "microphone",
                              "network"]
    for name, payload in answer.items():
        assert sorted(payload) == ["class", "text", "tooltip"], (
            f"{name} hat die falsche Form: {payload}")


def test_a_sound_server_that_does_not_answer_says_so(sandbox):
    """Ein Dienst, der nicht antwortet, ist ein FEHLER und kein leeres Feld.

    GEMELDET am 13.08.2026, viermal: "rechts ist zu leer" - "es fehlt
    auch ein batterie icon ich weiss nicht wie voll der laptop ist" -
    "und lautstaerke und mikrofon auch".

    Bis dahin stand hier die Erwartung, das Modul bleibe LEER. Das war
    die Regel, die den Nutzer eine Woche lang nicht wissen liess, ob
    seine Maschine keine Tonkarte hat oder ob sein Tondienst tot ist:
    beides sah gleich aus, naemlich nach nichts. Die Vorlage
    unterscheidet die beiden Faelle seither ueber `wpctl status` -
    siehe den Kopf von bar-status-config.template.

    Was von der alten Zusicherung bleibt und weiter geprueft wird: der
    Text ist nicht " %".

    GEMESSEN am 11.08.2026: die Mutation, die die Auffanglinie hinter
    `volume_of` entfernt, kam durch eine Pruefung der blossen FORM
    hindurch. Alle fuenf Schluessel waren da, alle drei Felder auch -
    nur stand im Text Unsinn.
    """
    answer = sandbox.run()

    assert answer["audio"]["class"] == "broken", answer["audio"]
    assert answer["audio"]["text"] != "", answer["audio"]
    assert "%" not in answer["audio"]["text"], answer["audio"]
    assert "wireplumber" in answer["audio"]["tooltip"], answer["audio"]
    assert answer["microphone"]["class"] == "broken", answer["microphone"]


def test_a_missing_sound_tool_names_its_package(sandbox):
    """Der andere Zweig desselben Zustands, und er sagt etwas anderes.

    Fehlt `wpctl`, ist nicht der Dienst tot, sondern das Paket nicht
    installiert. Ein Kurzhinweis, der beide Faelle gleich benennt,
    schickt den Nutzer in die falsche Richtung.
    """
    sandbox.remove("wpctl")

    answer = sandbox.run()

    assert answer["audio"]["class"] == "broken", answer["audio"]
    assert "wireplumber" in answer["audio"]["tooltip"], answer["audio"]
    assert "nicht installiert" in answer["audio"]["tooltip"], answer["audio"]


def test_a_machine_without_a_sound_device_shows_no_sound_module(sandbox):
    """Der ERSTE Zustand: der Dienst antwortet, das Geraet gibt es nicht.

    Das ist die Lage, fuer die das leere Modul gedacht war und die
    einzige, in der es richtig ist. Ohne diese Zeile waere die
    Unterscheidung, die die Vorlage am 13.08.2026 eingezogen hat, nur zur
    Haelfte gemessen - und die Haelfte, die fehlte, waere die, in der ein
    Warnzeichen dauerhaft auf der Leiste steht.
    """
    _sound_without_devices(sandbox)

    answer = sandbox.run()

    assert answer["audio"]["text"] == "", answer["audio"]
    assert answer["audio"]["class"] == "", answer["audio"]
    assert answer["microphone"]["text"] == "", answer["microphone"]


def test_without_jq_the_script_fails_loudly_instead_of_writing_nothing(sandbox):
    """Der Fehler, an dem die ganze rechte Haelfte der Leiste hing.

    GEMESSEN am 13.08.2026 an den Bildern des Abnahmelaufs: rechts stand
    nur das Zahnrad. Netz, Ton und Akku standen in der Vorgabe und waren
    unsichtbar - ALLE DREI, denn alle drei kommen aus diesem einen
    Skript.

    Ohne jq gab jede Modulfunktion einen leeren String zurueck, das
    abschliessende `jq -n --argjson audio ""` scheiterte, auf stdout
    stand NICHTS, und die Leiste liess ihre fuenf Kaesten stehen, wie sie
    beim Start waren: unsichtbar. Ein einziges fehlendes Paket, und die
    halbe Leiste verschwindet, ohne dass irgendwo etwas rot wird.

    Seither endet der Lauf mit einem Rueckgabewert und einem Satz auf
    stderr - und sharedStatus() in ags-bar.template zeigt daraufhin alle
    fuenf Module mit dem Warnzeichen.
    """
    sandbox.remove("jq")

    result = sandbox.run_raw()

    assert result.returncode != 0, (
        "ohne jq endet das Skript erfolgreich und schreibt nichts - "
        f"genau der lautlose Fall:\n{result.stdout!r}")
    assert result.stdout.strip() == "", (
        "ohne jq kann kein gueltiges JSON entstehen; was hier steht, "
        f"kann die Leiste nur missverstehen: {result.stdout!r}")
    assert "jq" in result.stderr, result.stderr


def test_one_missing_tool_does_not_empty_the_other_four(sandbox):
    """Ein Rechner ohne Bluetooth-Adapter ist der Normalfall, nicht der
    Fehlerfall - und er darf die anderen vier Antworten nicht kosten.
    """
    sandbox.stub("wpctl", 'printf "Volume: 0.40\\n"')
    sandbox.stub("nmcli", 'printf "eth0:ethernet:connected:Kabel\\n"')
    sandbox.stub("bluetoothctl", 'echo "No default controller available"; exit 1')

    answer = sandbox.run()

    assert answer["bluetooth"]["text"] == "", "ohne Adapter bleibt das Modul leer"
    assert answer["audio"]["text"] != "", (
        "der fehlende Adapter hat den Ton mitgenommen: " + str(answer))
    assert answer["network"]["text"] != "", (
        "der fehlende Adapter hat das Netz mitgenommen: " + str(answer))


def test_an_adapter_with_nothing_connected_still_answers(sandbox):
    """Der haeufigste Bluetooth-Zustand ueberhaupt: an, und nichts dran.

    `bluetoothctl devices Connected | grep -c '^Device '` gibt bei null
    Treffern "0" aus UND kehrt mit 1 zurueck - so zaehlt grep. Ohne das
    `${connected:-0}` im Skript waere der Vergleich danach ein
    `[ "" -gt 0 ]`, also ein Fehler statt einer Antwort.
    """
    sandbox.stub("wpctl", 'printf "Volume: 0.40\\n"')
    sandbox.stub("bluetoothctl", r"""
case "$1" in
    show) printf 'Controller AA:BB\n\tPowered: yes\n' ;;
    devices) : ;;
esac
""")
    answer = sandbox.run()

    assert answer["bluetooth"]["class"] == "bluetooth", answer["bluetooth"]
    assert answer["bluetooth"]["text"] != "", (
        "ein eingeschalteter Adapter ohne Geraete zeigt trotzdem sein "
        f"Zeichen: {answer['bluetooth']}")
    assert answer["audio"]["text"] != "", (
        "der leere Adapter hat den Ton mitgenommen: " + str(answer))


def test_a_network_name_with_a_quote_in_it_stays_valid_json(sandbox):
    """Eine SSID darf ein Anfuehrungszeichen tragen.

    Mit einem printf-gebauten JSON zerbricht daran nicht dieses eine
    Modul, sondern die ganze Antwort - die Leiste bekommt eine Zeile, die
    sie nicht parsen kann, und ALLE FUENF Kaesten bleiben stehen, wie sie
    waren. Deshalb baut das Skript sein JSON mit jq.
    """
    sandbox.stub("nmcli", r"""
case "$*" in
    *"DEVICE,TYPE,STATE,CONNECTION"*) printf 'wlan0:wifi:connected:Cafe "Zum Ohr"\n' ;;
    *IP4.ADDRESS*) printf 'IP4.ADDRESS[1]:192.0.2.5/24\n' ;;
    *IN-USE*) printf '*:73\n' ;;
esac
""")
    answer = sandbox.run()

    assert 'Cafe "Zum Ohr"' in answer["network"]["tooltip"], answer["network"]


# --------------------------------------------------------------------
# Ton und Mikrofon
# --------------------------------------------------------------------

def test_the_volume_is_whole_per_cent_and_rounded(sandbox):
    """wpctl meldet einen Bruch, die Leiste zeigt Prozent.

    0.455 sind 46 Prozent und nicht 45 und nicht 45.5: bash kann keine
    Fliesskommazahlen, also rechnet awk, und ohne das +0.5 dort waere
    jede Anzeige systematisch zu niedrig.

    AUF DER LEISTE UND IM TOOLTIP, SEIT DEM 19.08.2026 - und das ist die
    Umkehrung dessen, was hier vom 12.08. bis heute stand.

        Bis heute forderte die zweite Zeile das Gegenteil: "%" durfte im
        Text NICHT vorkommen, mit der Fehlermeldung "die Prozentzahl
        steht wieder auf der Leiste". Das war die Zusicherung zu
        "Symbol allein, Zahl im Tooltip - so macht es macOS."

        UMGEKEHRT hat sie der Nutzer selbst, am 19.08.2026: "in dem
        header fehlen ausserdem beim lautstaerke und mikrofon icon die
        prozent zahlen auf wie viel prozent sie gestellt sind" - auf
        Nachfrage ausdruecklich BEIDE DAUERHAFT mit Zahl, so wie der
        Akku es macht.

        Das Argument von damals ist damit nicht falsch geworden,
        sondern ueberstimmt; was davon bleibt und was es kostet, steht
        im Kopf von bar-status-config.template. Die Rechnung oben ist
        unberuehrt geblieben und wird deshalb weiter hier geprueft.

    Der Waechter ist nicht geloescht, sondern gedreht: er misst
    weiterhin BEIDE Stellen, nur mit umgekehrtem Vorzeichen. Ohne die
    Zeile ueber den Tooltip bestuende dieser Test auch mit einem Skript,
    das die genaue Zahl von dort wegnimmt.
    """
    sandbox.stub("wpctl", r"""
case "$1" in
    get-volume) printf 'Volume: 0.455\n' ;;
    inspect) printf '  node.name = "alsa_output.pci"\n' ;;
esac
""")
    answer = sandbox.run()

    assert "46%" in answer["audio"]["tooltip"], answer["audio"]
    assert "46%" in answer["audio"]["text"], (
        f"die Prozentzahl fehlt auf der Leiste: {answer['audio']}")
    # Und das Zeichen bleibt daneben stehen - dieselbe Zusicherung wie
    # beim Akku: eine nackte Zahl waere auf einer Leiste voller Zeichen
    # nicht als Lautstaerke zu erkennen.
    assert answer["audio"]["text"].strip() != "46%", answer["audio"]

    # Das Mikrofon ist am selben Tag mitbestellt worden und wird deshalb
    # in derselben Zeile gemessen - die Attrappe oben antwortet auf
    # get-volume fuer beide Knoten.
    assert "46%" in answer["microphone"]["text"], (
        f"die Prozentzahl fehlt auf der Leiste: {answer['microphone']}")
    assert answer["microphone"]["text"].strip() != "46%", answer["microphone"]


def test_a_muted_sink_says_so_and_carries_the_muted_class(sandbox):
    """Stumm ist kein Lautstaerkewert, sondern ein Zustand.

    "0%" waere falsch: die Lautstaerke bleibt stehen, wo sie war, und
    kommt beim naechsten Druck auf die Stummtaste zurueck. Die Klasse
    traegt die Farbe, mit der bar-style.template das Modul abblendet.

    UND DIE EINGESTELLTE ZAHL STEHT SEIT DEM 19.08.2026 TROTZDEM DA.

        Das ist kein Widerspruch zum Satz oben, sondern seine
        Praezisierung: verboten ist "0%" - eine FALSCHE Zahl -, nicht
        die richtige. Das durchgestrichene Zeichen sagt den ZUSTAND, die
        Zahl sagt die EINSTELLUNG, und stumm ist genau der Fall, in dem
        man die Einstellung nicht hoeren kann. Bestellt hat der Nutzer
        an diesem Tag die Zahl fuer "auf wie viel prozent sie gestellt
        sind".

        Dazu eine gemessene Folge: ein Modul, dessen Zahl beim
        Stummschalten verschwindet, springt um 27 px und schiebt jeden
        Nachbarn mit - bei jedem Druck auf die Stummtaste.
    """
    sandbox.stub("wpctl", r"""
case "$1" in
    get-volume) printf 'Volume: 0.40 [MUTED]\n' ;;
    inspect) printf '  node.name = "alsa_output.pci"\n' ;;
esac
""")
    answer = sandbox.run()

    # Das durchgestrichene Lautsprechersymbol, und kein Wort daneben.
    # "Muted" stand hier bis zum 12.08.2026 und war das einzige englische
    # Wort, das dieses Skript je auf eine deutsche Leiste geschrieben
    # hat - das Zeichen sagt dasselbe und braucht keine Uebersetzung.
    assert answer["audio"]["text"] != "", answer["audio"]
    assert "Muted" not in answer["audio"]["text"], answer["audio"]
    assert "stumm" in answer["audio"]["tooltip"], answer["audio"]
    assert answer["audio"]["class"] == "audio-muted", answer["audio"]

    # Die eingestellten 40 Prozent, und nicht "0%".
    assert "40%" in answer["audio"]["text"], (
        "stumm zeigt die eingestellte Zahl seit dem 19.08.2026 mit: "
        f"{answer['audio']}")
    assert "0%" not in answer["audio"]["text"].replace("40%", ""), (
        f"stumm ist nicht null Prozent: {answer['audio']}")

    # Das Mikrofon ist der vierte Fall derselben Bestellung: die
    # Attrappe antwortet auf get-volume fuer beide Knoten, also ist es
    # hier ebenfalls stumm.
    assert answer["microphone"]["class"] == "microphone-muted", (
        answer["microphone"])
    assert "40%" in answer["microphone"]["text"], (
        "stumm zeigt die eingestellte Zahl seit dem 19.08.2026 mit: "
        f"{answer['microphone']}")


def test_headphones_get_the_headphone_icon(sandbox):
    """Der Knotenname ist die einzige maschinenlesbare Angabe darueber,
    wohin der Ton geht.

    Bluetooth-Kopfhoerer melden sich als bluez_output.* - dieselbe
    Unterscheidung, die die Waybar-Fassung unter format-icons.headphone
    traf, nur dass dort das Modul sie machte und hier wir.
    """
    sandbox.stub("wpctl", r"""
case "$1" in
    get-volume) printf 'Volume: 0.50\n' ;;
    inspect) printf '  node.name = "bluez_output.AA_BB.1"\n' ;;
esac
""")
    quiet = sandbox.run()["audio"]["text"]

    sandbox.stub("wpctl", r"""
case "$1" in
    get-volume) printf 'Volume: 0.50\n' ;;
    inspect) printf '  node.name = "alsa_output.pci"\n' ;;
esac
""")
    speakers = sandbox.run()["audio"]["text"]

    assert quiet != speakers, (
        "Kopfhoerer und Lautsprecher zeigen dasselbe Zeichen: "
        f"{quiet!r} / {speakers!r}")


def test_the_microphone_is_its_own_module(sandbox):
    """Zwei Regler, zwei Kaesten - und der zweite fragt die QUELLE.

    @DEFAULT_AUDIO_SOURCE@ und nicht @DEFAULT_AUDIO_SINK@: mit dem
    falschen Knoten zeigte das Mikrofon die Lautstaerke der Lautsprecher
    an, was auf jedem Rechner plausibel aussieht und nie stimmt.
    """
    sandbox.stub("wpctl", r"""
case "$2" in
    @DEFAULT_AUDIO_SINK@) printf 'Volume: 0.10\n' ;;
    @DEFAULT_AUDIO_SOURCE@) printf 'Volume: 0.90\n' ;;
    *) printf '  node.name = "alsa_output.pci"\n' ;;
esac
""")
    answer = sandbox.run()

    assert "10%" in answer["audio"]["tooltip"], answer["audio"]
    assert "90%" in answer["microphone"]["tooltip"], answer["microphone"]
    # Und seit dem 19.08.2026 auf der Leiste, jedes mit SEINER Zahl -
    # mit dem falschen Knoten stuenden hier zweimal dieselben 10%, und
    # das faellt im Text eher auf als im Kurzhinweis.
    assert "10%" in answer["audio"]["text"], answer["audio"]
    assert "90%" in answer["microphone"]["text"], answer["microphone"]


# --------------------------------------------------------------------
# Akku
# --------------------------------------------------------------------

def test_a_machine_without_a_battery_shows_no_battery(sandbox):
    """Ein Standrechner hat kein Akkumodul, und das ist kein Fehler.

    Der leere Text ist der Weg, auf dem das Modul verschwindet - siehe
    applyPayload() in ags-bar.template. Ein "0%" hier waere ein Akku, der
    auf jedem Standrechner als leer gemeldet wird.
    """
    answer = sandbox.run()
    assert answer["battery"]["text"] == "", answer["battery"]


def test_a_battery_that_cannot_be_read_says_so_instead_of_vanishing(sandbox):
    """Der dritte Zustand am Akku - der, nach dem der Nutzer gefragt hat.

    GEMELDET am 13.08.2026: "es fehlt auch ein batterie icon ich weiss
    nicht wie voll der laptop ist sollte im header stehen".

    Es gibt ein Akkuverzeichnis, aber die capacity ist keine Zahl. Bis
    heute war die Antwort darauf ein leeres Modul, also genau dieselbe
    wie fuer einen Standrechner - und der Nutzer konnte aus dem, was er
    sah, nicht schliessen, welcher der beiden Faelle vorlag.
    """
    sandbox.battery(capacity="unbekannt", status="Discharging")

    answer = sandbox.run()

    assert answer["battery"]["class"] == "broken", answer["battery"]
    assert answer["battery"]["text"] != "", answer["battery"]
    assert "capacity" in answer["battery"]["tooltip"], answer["battery"]


def test_the_battery_carries_its_per_cent_on_the_bar(sandbox):
    """"ich will auch eine prozentzahl haben fuer die batterie nicht nur
    ein symbol" - gemeldet am 13.08.2026.

    Der Akku war die ERSTE Ausnahme von "Symbol allein, Zahl im
    Tooltip": ein Ladestand ist eine Messung, ueber die man planen muss,
    keine Einstellung, die man gerade selbst gemacht hat.

    SEIT DEM 19.08.2026 IST ER NICHT MEHR ALLEIN - Ton und Mikrofon
    tragen ihre Zahl auf Ansage des Nutzers ebenfalls auf der Leiste,
    und diese Zeile ist die Vorlage dafuer (die Schreibweise
    "$icon $wert%" steht seither an vier weiteren Stellen). Die
    Begruendung im Wortlaut steht im Kopf von
    bar-status-config.template.
    """
    sandbox.battery(capacity="47", status="Discharging")

    answer = sandbox.run()

    assert "47%" in answer["battery"]["text"], answer["battery"]
    # Und das Zeichen bleibt: eine nackte Zahl ohne Symbol waere auf
    # einer Leiste voller Zeichen nicht als Akku zu erkennen.
    assert answer["battery"]["text"].strip() != "47%", answer["battery"]


def test_a_charging_battery_says_so(sandbox):
    """Laden ist ein eigener Zustand und kein Prozentwert.

    Er ueberschreibt die Schwellen absichtlich: ein Akku bei 9 Prozent AM
    KABEL ist nicht kritisch, sondern in Ordnung, und ein rotes Modul
    dort waere eine Warnung, auf die niemand etwas tun kann.
    """
    sandbox.battery(capacity="9", status="Charging")

    answer = sandbox.run()
    assert answer["battery"]["class"] == "battery-charging", answer["battery"]


def test_a_low_battery_is_named_critical(sandbox):
    """Die Schwellen der Waybar-Fassung, unveraendert: 30 warnend, 15
    kritisch.

    Sie stehen jetzt in unserem Skript statt in waybars `states`-Block,
    und bar-style.template haengt die Farben daran. Ein Zustand, den
    niemand meldet, ist eine Regel, die nie greift.
    """
    sandbox.battery(capacity="9", status="Discharging")

    answer = sandbox.run()
    assert "9%" in answer["battery"]["tooltip"], answer["battery"]
    assert answer["battery"]["class"] == "battery-critical", answer["battery"]


# --------------------------------------------------------------------
# Netz und Bluetooth
# --------------------------------------------------------------------

def test_no_connection_is_a_state_and_not_an_empty_module(sandbox):
    """Kein Netz ist etwas, das der Nutzer SEHEN muss.

    Ein leeres Modul hiesse "es gibt hier nichts zu wissen", und das ist
    der Unterschied zum Akku: ein Rechner ohne Akku hat keinen, ein
    Rechner ohne Verbindung hat ein Problem.
    """
    answer = sandbox.run()

    assert answer["network"]["text"] != "", answer["network"]
    assert answer["network"]["class"] == "network-disconnected", answer["network"]


def test_a_missing_network_tool_is_not_reported_as_no_connection(sandbox):
    """"Keine Verbindung" ist eine AUSKUNFT, und sie muss stimmen.

    Bis zum 13.08.2026 lief die Ausgabe von nmcli direkt in die Schleife.
    Ein fehlendes oder totes nmcli war damit dasselbe wie eine leere
    Liste, und beides ergab "Keine Verbindung" - ein Modul, das etwas
    Falsches ueber den Netzzustand sagt. Das ist die gefaehrlichere
    Haelfte des Fehlers: ein leeres Modul faellt auf, ein falsches nicht.
    """
    sandbox.remove("nmcli")

    answer = sandbox.run()

    assert answer["network"]["class"] == "broken", answer["network"]
    assert "networkmanager" in answer["network"]["tooltip"].lower(), (
        answer["network"])


def test_a_switched_off_adapter_is_visible_and_dimmed(sandbox):
    """Aus ist etwas anderes als nicht vorhanden.

    Bis zum 13.08.2026 gab ein Adapter mit `Powered: no` ein leeres
    Modul, also dasselbe wie eine Maschine ohne Bluetooth. Der Nutzer
    hatte damit keinen Hinweis darauf, dass er ihn nur einschalten muss -
    und ein Modul, das ausgeliefert wird und auf seinem Rechner nie
    erscheint, ist genau die Sorte Leere, die er am selben Tag gemeldet
    hat.
    """
    sandbox.stub("bluetoothctl", r"""
case "$1" in
    show) printf 'Controller AA:BB\n\tPowered: no\n' ;;
    *) : ;;
esac
""")

    answer = sandbox.run()

    assert answer["bluetooth"]["text"] != "", answer["bluetooth"]
    assert answer["bluetooth"]["class"] == "bluetooth-off", answer["bluetooth"]


def _wifi_answer(sandbox, signal: str) -> dict:
    """Eine WLAN-Antwort mit genau dieser Feldstaerke."""
    sandbox.stub("nmcli", """
case "$*" in
    *"DEVICE,TYPE,STATE,CONNECTION"*) printf 'wlan0:wifi:connected:Zuhause\\n' ;;
    *IP4.ADDRESS*) printf 'IP4.ADDRESS[1]:192.0.2.5/24\\n' ;;
    *IN-USE*) printf ':91\\n*:""" + signal + """\\n:88\\n' ;;
esac
""")
    return sandbox.run()["network"]


def test_a_wifi_connection_shows_its_signal_strength(sandbox):
    """Der Prozentwert kommt aus der Zeile mit dem Stern.

    `nmcli -t -f IN-USE,SIGNAL device wifi list` markiert die verbundene
    Zelle mit `*`. Ohne die Auswahl stuende dort die Staerke der ersten
    fremden Zelle in der Liste.

    GEZEIGT WIRD SIE SEIT DEM 12.08.2026 IM ZEICHEN
        Die Zahl ist in den Tooltip gezogen, und sie darf das nur, weil
        das Zeichen sie ersetzt: nf-md-wifi_strength_1..4, vier Balken,
        also vier Viertel. Deshalb steht unten nicht nur, dass die Zahl
        im Tooltip ankommt, sondern dass zwei verschiedene Staerken auch
        zwei verschiedene ZEICHEN ergeben - sonst waere aus einer
        Auskunft eine Zusicherung ueber einen Tooltip geworden, den
        niemand aufmacht.
    """
    answer = _wifi_answer(sandbox, "42")

    assert "42%" in answer["tooltip"], answer
    assert answer["class"] == "network-wifi", answer
    assert "%" not in answer["text"], answer

    # 42 ist die zweite Stufe, 91 die vierte.
    assert answer["text"] != _wifi_answer(sandbox, "91")["text"], (
        "schwaches und starkes Signal malen dasselbe Zeichen - dann "
        "steht die Feldstaerke nirgends mehr")


def test_an_ethernet_connection_shows_its_address(sandbox):
    """Kabel zeigt die Adresse, WLAN die Staerke - dieselbe
    Unterscheidung, die format-ethernet und format-wifi trafen.

    Beide stehen seit dem 12.08.2026 im Tooltip: eine IPv4-Adresse sind
    bis zu fuenfzehn Zeichen auf der Leiste fuer eine Angabe, die man
    einmal am Tag braucht.

    DIE ADRESSE IM BEISPIEL IST ERFUNDEN (17.08.2026). Hier stand die
    Adresse, die der Rechner des Autors in seinem Heimnetz trug - also
    sein Router-Praefix. Genommen ist "198.51.100.7" aus TEST-NET-2
    (RFC 5737), dieselbe Adresse, die die Attrappe unten schon ausgibt:
    der Kommentar und der gemessene Fall sagen damit endlich dasselbe.
    Die LAENGE traegt hier nichts - gemessen wird, dass die Adresse im
    Tooltip landet und nicht auf der Leiste.
    """
    sandbox.stub("nmcli", r"""
case "$*" in
    *"DEVICE,TYPE,STATE,CONNECTION"*) printf 'lo:loopback:connected:lo\neth0:ethernet:connected:Kabel\n' ;;
    *IP4.ADDRESS*) printf 'IP4.ADDRESS[1]:198.51.100.7/24\n' ;;
esac
""")
    answer = sandbox.run()

    assert "198.51.100.7" in answer["network"]["tooltip"], answer["network"]
    assert answer["network"]["class"] == "network-ethernet", answer["network"]


def test_the_loopback_is_not_a_connection(sandbox):
    """lo ist immer "connected".

    Ohne die Filterung nach Typ waere jede Maschine verbunden, auch die
    ohne Kabel und ohne Funk - der eine Zustand, den dieses Modul
    ueberhaupt melden soll.
    """
    sandbox.stub("nmcli", r"""
case "$*" in
    *"DEVICE,TYPE,STATE,CONNECTION"*) printf 'lo:loopback:connected:lo\n' ;;
esac
""")
    answer = sandbox.run()

    assert answer["network"]["class"] == "network-disconnected", answer["network"]


def test_bluetooth_says_something_different_when_it_is_off(sandbox):
    """Aus und verbunden sind zwei Zustaende, und beide sind sichtbar.

    Hier stand `format-disabled: ""` der Waybar-Fassung, in unseren
    Worten: ein ausgeschalteter Adapter zeigte NICHTS. Am 13.08.2026 ist
    das zurueckgenommen - siehe
    test_a_switched_off_adapter_is_visible_and_dimmed weiter oben. Was
    hier bleibt, ist die Frage, die diese Zeile immer gestellt hat: dass
    sich die beiden Zustaende UNTERSCHEIDEN und nicht beide dasselbe
    zeigen.
    """
    sandbox.stub("bluetoothctl", 'printf "Controller AA:BB\\n\\tPowered: no\\n"')
    off = sandbox.run()["bluetooth"]

    sandbox.stub("bluetoothctl", r"""
case "$1" in
    show) printf 'Controller AA:BB\n\tPowered: yes\n' ;;
    devices) printf 'Device CC:DD Kopfhoerer\n' ;;
esac
""")
    connected = sandbox.run()["bluetooth"]
    assert connected["text"] != ""
    assert "1" in connected["text"], connected
    assert "Kopfhoerer" in connected["tooltip"], connected
    assert connected["class"] != off["class"], (
        f"aus und verbunden tragen dieselbe Klasse: {off} / {connected}")
    assert connected["text"] != off["text"], (
        f"aus und verbunden zeigen dasselbe: {off} / {connected}")


@pytest.mark.allow_subprocess
def test_ein_werkzeug_das_nie_antwortet_haelt_die_leiste_nicht_an(sandbox):
    """GEMELDET am 17.08.2026, auf echter Hardware.

    Der Nutzer sah in der Leiste "btop das drive und das zahnrad icon
    mehr nicht" - und auf die Bitte, dieses Skript von Hand aufzurufen:
    "wenn ich auf meinem zepos system versuche das auszufuehren stuckt
    er freeze es passiert nichts".

    DAS BILD PASST AUF EINE URSACHE
        btop, Platte und Zahnrad sind EIGENE Skripte je Modul. Ton,
        Mikrofon, Akku, Netz und Bluetooth kommen aus DIESEM einen.
        Haengt es, bleiben genau diese fuenf leer und die drei anderen
        laufen weiter.

        Sein Schirm ist 1920x1200 bei Faktor 1.00 - der Einklapp-Knopf
        scheidet also aus, dafuer waere reichlich Platz.

    GEZAEHLT vor der Behebung: NULL Aufrufe mit einer Frist. `nmcli`
    wartet ohne NetworkManager, `bluetoothctl show` auf einen Controller
    und auf D-Bus, `wpctl` auf wireplumber. Ein blockierter Aufruf haelt
    das ganze Skript an.

    Hier haengt bluetoothctl fuer immer. Ohne die Frist lief dieser Test
    in den Zeitausschnitt von run_raw() (60 s) - mit ihr antwortet das
    Skript, und die vier anderen Module stehen da.
    """
    _quiet(sandbox)
    sandbox.stub("bluetoothctl", "sleep 3600")

    beginn = time.monotonic()
    answer = sandbox.run()
    gebraucht = time.monotonic() - beginn

    assert gebraucht < 30, (
        f"das Skript brauchte {gebraucht:.1f} s - ein haengendes Werkzeug "
        f"haelt es also weiter an")
    assert set(answer) == {"audio", "microphone", "battery", "network",
                           "bluetooth"}, answer
