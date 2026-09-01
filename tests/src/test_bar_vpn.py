# SPDX-License-Identifier: GPL-3.0-or-later
"""Das VPN-Schild der Leiste - erzeugt, ausgefuehrt und nachgerechnet.

BESTELLT am 22.08.2026: "ein user hat vorgeschlagen, in die waybar im
header ein schild mit farbe und tooltip zu machen, wo man sieht was der
status der vpn ist - nicht verbunden, verbunden, error - mit einer farbe
verbunden. als icon natuerlich auch."

DAS VERFAHREN
    Dasselbe wie in tests/src/test_bar_status.py und
    tests/src/test_hardware.py: die Vorlage wird gerendert, in ein
    Verzeichnis gelegt und unter `env -i` mit einem Attrappenverzeichnis
    als GANZEM PATH ausgefuehrt. Ein Werkzeug, das niemand nachgebaut
    hat, wird damit zu "command not found" statt zu einer leeren
    Antwort, die wie ein Messergebnis aussieht.

WAS HIER NICHT PASSIEREN DARF, UND WIE ES VERHINDERT WIRD
    Dieses Modul fragt nach dem VPN DES ENTWICKLERS, wenn man es laesst.
    Drei Dinge verhindern das, und alle drei sind Bedingungen und keine
    Vorsichtsmassnahmen:

      nmcli, pgrep und ip sind ATTRAPPEN. Sie stehen in
      tests/conftest.py unter NEVER_PASSTHROUGH, koennen hier also gar
      nicht durchgereicht werden - und jede von ihnen schreibt ihren
      Aufruf mit, damit die Zusicherung "es wird nur gelesen" etwas
      wert ist (test_the_module_only_ever_reads).

      ZEPOS_USER_ROOT und XDG_RUNTIME_DIR zeigen in tmp_path. Die
      Einstellungen, aus denen das Modul liest, und die Zustandsdatei,
      auf die es sich stuetzt, gehoeren damit dem Test.

      Kein Aufruf traegt jemals ein Geheimnis. `--status` liest keines -
      das ist die Eigenschaft, aus der es der Vertrag fuer vier
      rechtelose Leser ist (src/vpn.py).
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from tests.conftest import assert_no_missing_command

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
TEMPLATE = SRC / "templates" / "bar-vpn-config.template"
STYLESHEET = SRC / "styles" / "bar-style.template"

ENV = "/usr/bin/env"

pytestmark = pytest.mark.allow_subprocess


def _no_compositor(*args, **kwargs):
    """Ein subprocess.run, das "hyprctl sagt nichts" antwortet.

    style_definition fragt beim Import den Compositor nach den
    angeschlossenen Schirmen. Ohne diese Attrappe liefe die Frage gegen
    die LAUFENDE Sitzung des Entwicklers - dieselbe Begruendung und
    dieselbe Bauart wie in tests/src/test_hardware.py.
    """
    return subprocess.CompletedProcess(args[0] if args else [], 1,
                                       stdout="", stderr="not running")


class Sandbox:
    """Ein erzeugtes VPN-Modul und die Welt, in der es laeuft."""

    def __init__(self, root: Path, system_root: Path | None = None) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.stubs = root / "stubs"
        self.stubs.mkdir()
        self.user_root = root / "zepos"
        self.user_root.mkdir()
        self.runtime = root / "run"
        self.runtime.mkdir()
        self.runtime.chmod(0o700)
        self.calls = root / "aufrufe"

        # Der Interpreter, der die Suite faehrt, unter dem Namen, unter
        # dem das Kind ihn ruft. Absolut benannt, damit das Finden nicht
        # vom Attrappen-PATH abhaengt.
        self.stub("python3", f'exec "{sys.executable}" "$@"')
        self.script = self._render(system_root or SRC)

    def _render(self, system_root: Path) -> Path:
        sys.path.insert(0, str(SRC))
        try:
            with mock.patch.object(subprocess, "run", _no_compositor):
                import template_processor
            processor = template_processor.ConfigProcessor(
                paths={"ZEPOS_SYSTEM_ROOT": str(system_root)})
        finally:
            sys.path.remove(str(SRC))
        script = self.root / "vpn.py"
        processor.apply_template(TEMPLATE, script)
        script.chmod(0o755)
        return script

    def stub(self, name: str, body: str) -> None:
        path = self.stubs / name
        path.write_text(f"#!/bin/bash\n{body}\n", encoding="utf-8")
        path.chmod(0o755)

    def recording_stub(self, name: str, body: str) -> None:
        """Eine Attrappe, die ihren Aufruf ZUERST mitschreibt.

        Unbedingt und vor allem anderen: eine Zusicherung darueber, was
        NICHT gerufen wurde, ist nur so viel wert, wie jeder Aufruf
        aufgeschrieben wird.
        """
        self.stub(name, f"printf '{name} %s\\n' \"$*\" >> '{self.calls}'\n"
                        + body)

    def calls_of(self, name: str) -> list[str]:
        if not self.calls.exists():
            return []
        return [line for line in self.calls.read_text().splitlines()
                if line.split(" ", 1)[0] == name]

    def settings(self, document) -> None:
        """Die Einstellungsdatei, so wie settings.load() sie erwartet."""
        text = (document if isinstance(document, str)
                else json.dumps(document))
        (self.user_root / "user-settings.json").write_text(text,
                                                           encoding="utf-8")

    def state_file(self, payload: str) -> None:
        """Die Zustandsdatei, die vpn-connect.sh schreibt."""
        (self.runtime / "vpn-active").write_text(payload, encoding="utf-8")

    def run_raw(self) -> subprocess.CompletedProcess:
        path = str(self.stubs)
        assert path.split(":") == [path], "PATH traegt genau einen Eintrag"
        return subprocess.run(
            [ENV, "-i", f"PATH={path}", f"HOME={self.root}",
             f"ZEPOS_USER_ROOT={self.user_root}",
             f"XDG_RUNTIME_DIR={self.runtime}",
             "python3", str(self.script)],
            env={}, input="", capture_output=True, text=True, timeout=60)

    def run(self) -> dict:
        result = self.run_raw()
        assert_no_missing_command(result, "vpn.py")
        assert result.returncode == 0, (
            f"vpn.py endete mit {result.returncode}:\n"
            + result.stdout + result.stderr)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise AssertionError(
                f"vpn.py hat kein JSON geschrieben ({error}):\n"
                f"{result.stdout!r}\n{result.stderr}") from error


# Die drei Bauarten, wie eine eingerichtete Verbindung aussieht. Keine
# davon traegt ein Geheimnis - `--status` liest keines, und ein Test, der
# eines hinschriebe, waere die Vorlage fuer einen, der eines liest.
WIREGUARD = {"id": "c1", "kind": "wireguard", "connection_name": "Arbeit"}
IPSEC = {"id": "c1", "connection_name": "Büro", "server": "vpn.example.org"}


def _document(*connections, active: str = "c1") -> dict:
    return {"schema_version": 2,
            "vpn": {"active": active, "connections": list(connections)}}


@pytest.fixture
def box(tmp_path) -> Sandbox:
    """Der Grundzustand: NetworkManager antwortet, sagt aber nichts."""
    sandbox = Sandbox(tmp_path)
    sandbox.recording_stub("nmcli", "exit 0")
    sandbox.recording_stub("pgrep", "exit 1")
    sandbox.recording_stub("ip", "exit 0")
    sandbox.settings(_document(WIREGUARD))
    return sandbox


def _nm(state: str = "activated", address: str = "") -> str:
    """Was `nmcli -t -f GENERAL.STATE,IP4.ADDRESS connection show` schreibt.

    Das Adressfeld heisst `IP4.ADDRESS[1]` - die eckige Klammer ist eine
    Nummer und keine Zierde, und ein Vergleich auf den blossen Namen
    findet sie nie (src/vpn.py::parse_nm_state).
    """
    zeilen = [f"GENERAL.STATE:{state}"]
    if address:
        zeilen.append(f"IP4.ADDRESS[1]:{address}")
    return "printf '" + "\\n".join(zeilen) + "\\n'"


# --------------------------------------------------------------------
# Die Form der Antwort
# --------------------------------------------------------------------

def test_the_answer_always_has_the_three_fields_the_bar_reads(box):
    """`{text, tooltip, class}` - die Form jedes Leistenskripts.

    applyPayload() in ags-bar.template liest genau diese drei. Ein
    fehlendes Feld ist dort kein Fehler, sondern ein leerer Wert - also
    ein Modul, das stillschweigend nichts sagt.
    """
    antwort = box.run()
    assert sorted(antwort) == ["class", "text", "tooltip"], antwort


# --------------------------------------------------------------------
# Die drei Worte, die `vpn.py --status` wirklich kennt
# --------------------------------------------------------------------

def test_a_standing_tunnel_is_green_and_names_its_address(box):
    """`connected`: das Schild mit dem Schloss, die Erfolgsfarbe.

    Die Adresse steht NUR hier - sie ist die einzige Stelle, an der es
    wirklich eine gibt.
    """
    box.stub("nmcli", _nm(address="10.9.0.2/24"))

    antwort = box.run()

    assert antwort["class"] == "vpn-connected", antwort
    assert "10.9.0.2" in antwort["tooltip"], antwort
    assert "Arbeit" in antwort["tooltip"], antwort
    assert "WireGuard" in antwort["tooltip"], antwort


def test_a_tunnel_without_an_assigned_address_says_so(box):
    """Ein Verbund, der die eigene Adresse des Klienten routet, weist
    keine zu - und das ist ein vollstaendig gueltiger Tunnel.

    Die Erklaerung steht bei IkeSA in src/vpn.py: "calling that 'not
    connected' is one of the six failures this replaced". Hier wird
    geprueft, dass das Schild in diesem Fall weder luegt noch schweigt.
    """
    box.settings(_document(IPSEC))
    box.state_file('{"virtual_ip":""}')
    box.stub("pgrep", "exit 0")

    antwort = box.run()

    assert antwort["class"] == "vpn-connected", antwort
    assert "Adresse " not in antwort["tooltip"], antwort
    assert "Ohne zugewiesene Adresse" in antwort["tooltip"], antwort


def test_a_half_up_tunnel_is_the_error_state(box):
    """`stale`: aktiviert und ohne Adresse - der "error" der Bestellung.

    Es ist der Zustand, in dem der Nutzer sich fuer geschuetzt haelt und
    es nicht ist. Deshalb das eigene Zeichen UND die kritische Klasse.
    """
    box.stub("nmcli", _nm())

    antwort = box.run()

    assert antwort["class"] == "vpn-stale", antwort
    assert "unvollständig" in antwort["tooltip"], antwort


def test_the_error_state_never_shows_the_recorded_address(box):
    """Die Falle, in die `--status` einen laufen laesst.

    tunnel_status() gibt die AUFGEZEICHNETE Adresse auch fuer `stale`
    zurueck - der Trennpfad braucht sie genau dann, um sie von einer
    Schnittstelle zu nehmen, die charon nicht mehr haelt. Auf dem Schild
    waere sie eine alte Adresse neben der Aussage, dass nichts traegt:
    "steht kein Tunnel, sagt er das, statt eine alte Adresse zu zeigen".

    GEMESSEN: `vpn.py --status` schreibt in genau diesem Aufbau
    "stale 172.20.4.9" - die Zahl ist also da und wird bewusst nicht
    gezeigt.
    """
    box.settings(_document(IPSEC))
    box.state_file('{"virtual_ip":"172.20.4.9"}')
    box.stub("pgrep", "exit 1")          # charon ist weg

    antwort = box.run()

    assert antwort["class"] == "vpn-stale", antwort
    assert "172.20.4.9" not in antwort["tooltip"], (
        "das Schild zeigt eine Adresse aus einem Tunnel, der nicht mehr "
        "traegt: " + str(antwort))


def test_a_disconnected_tunnel_is_dimmed_and_not_an_error(box):
    """`disconnected`: der Ruhezustand, und er ist kein Fehler.

    Ein Schild, das rot wird, weil gerade kein VPN laeuft, waere eine
    dauerhafte Warnung ueber einen voellig gewoehnlichen Zustand.
    """
    antwort = box.run()

    assert antwort["class"] == "vpn-disconnected", antwort
    assert "getrennt" in antwort["tooltip"], antwort


def test_a_connection_that_is_activating_is_not_shown_as_broken(box):
    """"Verbindet gerade" gibt es im Vertrag nicht - und darf deshalb
    auch nicht als Fehler erscheinen.

    NetworkManager meldet waehrend des Aufbaus `activating`, und
    wireguard_status() nennt alles ausser `activated` "disconnected".
    Das ist die wahre Auskunft (es traegt noch nichts). Ein vierter
    Zustand, der als Fehler erschiene, obwohl keiner vorliegt, kostet
    Vertrauen - diese Zeile haelt fest, dass es ihn nicht gibt.
    """
    box.stub("nmcli", _nm(state="activating"))

    antwort = box.run()

    assert antwort["class"] == "vpn-disconnected", antwort


# --------------------------------------------------------------------
# Die zwei Zustaende, die VOR dem ersten Wort liegen
# --------------------------------------------------------------------

def test_a_machine_with_no_vpn_at_all_shows_no_module(box):
    """Kein Zeichen fuer etwas, das es nicht gibt.

    Dieselbe Regel, nach der der Akku auf einem Standrechner
    verschwindet. Ein graues Schild auf einer frischen Installation waere
    eine Auskunft ueber eine Verbindung, die niemand eingerichtet hat.
    """
    box.settings({"schema_version": 2})

    antwort = box.run()

    assert antwort["text"] == "", antwort
    assert antwort["class"] == "", antwort


def test_an_empty_vpn_section_is_not_a_connection(box):
    """Ein LEERER Abschnitt ist keine Verbindung - dieselbe Regel wie in
    src/vpn.py::connections() und in ags-vpn.template."""
    box.settings({"schema_version": 2, "vpn": {"active": "", "connections": []}})

    assert box.run()["text"] == ""


def test_unreadable_settings_are_shown_and_not_swallowed(box):
    """Der dritte Zustand der Leiste: vorhanden, aber nicht lesbar.

    Eine zerschossene Einstellungsdatei weiss nicht, welche Verbindung
    gewaehlt ist. "Kein VPN eingerichtet" waere darueber eine
    Behauptung - und "ein Fehler, der sich versteckt, ist der teuerste
    Fehler dieses Projekts".
    """
    box.settings("das ist kein JSON")

    antwort = box.run()

    assert antwort["class"] == "broken", antwort
    assert antwort["text"] != "", antwort
    assert "JSONDecodeError" in antwort["tooltip"], antwort


def test_a_missing_vpn_py_is_reported_with_its_reason(tmp_path):
    """Ohne src/vpn.py gibt es keine Auskunft - und das muss man sehen.

    Der Kasten bliebe sonst stehen, wie er ist (unsichtbar), und die
    Leiste haette keinen Grund zu nennen: scriptModule() faengt zwar ein
    Skript ab, das gar nicht laeuft, aber dieses hier LAEUFT - es kann
    nur nichts finden. Der Grund kommt deshalb aus dem Skript selbst.
    """
    leer = tmp_path / "ohne-werkzeuge"
    leer.mkdir()
    box = Sandbox(tmp_path / "box", system_root=leer)
    box.settings(_document(WIREGUARD))

    antwort = box.run()

    assert antwort["class"] == "broken", antwort
    assert "ModuleNotFoundError" in antwort["tooltip"], antwort


# --------------------------------------------------------------------
# Welche Verbindung das Schild meint
# --------------------------------------------------------------------

def test_with_two_connections_the_chosen_one_is_the_one_reported(box):
    """`vpn.active` entscheidet - und der Kurzhinweis nennt sie beim Namen.

    Es kann nur EINE zur Zeit stehen (src/settings.py bei `vpn.active`:
    eine Zustandsdatei mit einem Verbindungsnamen, an der vier
    rechtelose Leser haengen), also ist die gewaehlte zugleich die
    stehende. Ein Schild ohne Namen waere auf einer Maschine mit zwei
    Verbindungen eine Auskunft, von der niemand weiss, worueber sie
    spricht.
    """
    zweite = dict(WIREGUARD, id="c2", connection_name="Zuhause")
    box.settings(_document(WIREGUARD, zweite, active="c2"))
    box.stub("nmcli", _nm(address="10.8.0.5/24"))

    antwort = box.run()

    assert "Zuhause" in antwort["tooltip"], antwort
    assert "Arbeit" not in antwort["tooltip"], antwort


def test_the_build_kind_is_named_in_words(box):
    """IPsec, WireGuard, OpenVPN - dieselben drei Schreibweisen wie in
    der Verbindungsliste (ags-vpn.template::eintragUnterzeile).

    Die Bauart ist der Grund, aus dem die Liste ueberhaupt eine Liste
    ist: zwei Verbindungen zum selben Ziel unterscheiden sich sonst
    nicht.
    """
    box.settings(_document(IPSEC))

    assert "IPsec" in box.run()["tooltip"]

    box.settings(_document(dict(WIREGUARD, kind="openvpn")))

    assert "OpenVPN" in box.run()["tooltip"]


# --------------------------------------------------------------------
# Die Gegenprobe: die Farben kommen wirklich verschieden an
# --------------------------------------------------------------------

def _placeholder_of(klasse: str) -> str:
    """Der Farbname, den bar-style.template dieser Klasse gibt."""
    text = STYLESHEET.read_text(encoding="utf-8")
    # Bis zur schliessenden Klammer AM ZEILENANFANG, und nicht bis zur
    # naechsten ueberhaupt: der Rumpf enthaelt `{{STYLE_...}}`, also
    # selbst Klammern - ein `[^}]*` schneidet mitten im Platzhalter ab
    # und findet die Farbe dann nie.
    treffer = re.search(
        r"#custom-vpn\." + re.escape(klasse) + r"\s*\{(.*?)\n\}",
        text, re.DOTALL)
    assert treffer, (
        f"src/styles/bar-style.template faerbt #custom-vpn.{klasse} nicht - "
        "dann traegt dieser Zustand die Ruhefarbe der Leiste und ist von "
        "den anderen nicht zu unterscheiden")
    platzhalter = re.search(r"color:\s*\{\{([A-Z0-9_]+)\}\}", treffer.group(1))
    assert platzhalter, f"#custom-vpn.{klasse} setzt keine Farbe"
    return platzhalter.group(1)


def _shipped_styles(tmp_path, monkeypatch) -> dict:
    """Die Farbtabelle der AUSGELIEFERTEN Vorgabe.

    FRISCH GELADEN UND MIT LEEREN EINSTELLUNGEN, und beides ist noetig:
    style_definition liest die Einstellungsdatei EINMAL, beim Import.
    Ein bereits importiertes Modul truege damit die Farben dessen, der
    die Suite faehrt - und diese Zusicherung haenge daran, wie er sein
    Thema eingestellt hat, statt daran, was ZepOS ausliefert.

    Dieselbe Bauart wie die `build`-Vorrichtung in
    tests/src/test_hardware.py, und der Compositor wird aus demselben
    Grund abgefangen.
    """
    leer = tmp_path / "vorgabe"
    leer.mkdir()
    monkeypatch.syspath_prepend(str(SRC))
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(leer))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(leer))
    spec = importlib.util.spec_from_file_location(
        "zepos_style_vpn_probe", SRC / "style_definition.py")
    modul = importlib.util.module_from_spec(spec)
    with mock.patch.object(subprocess, "run", _no_compositor):
        spec.loader.exec_module(modul)
    return modul.STYLE_VARIABLES


def test_the_three_states_arrive_in_three_different_colours(tmp_path,
                                                            monkeypatch):
    """"mit einer farbe verbunden" - und drei Zustaende brauchen drei.

    Der Waechter gegen den Fehler, der sich nicht sehen laesst: drei
    Klassen, die alle auf denselben Farbnamen zeigen, ergeben ein
    Schild, das immer gleich aussieht - und jede Zusicherung ueber die
    KLASSEN bliebe dabei gruen.

    Geprueft werden BEIDE Enden: die drei Namen im Stylesheet und die
    drei Werte, die der Erzeuger daraus macht. Verschiedene Namen fuer
    denselben Wert waeren drei Regeln, die dasselbe malen.
    """
    namen = {klasse: _placeholder_of(klasse) for klasse in
             ("vpn-connected", "vpn-stale", "vpn-disconnected")}
    assert len(set(namen.values())) == 3, (
        "zwei Zustaende des Schildes zeigen auf denselben Farbnamen: "
        + str(namen))

    styles = _shipped_styles(tmp_path, monkeypatch)
    werte = {}
    for klasse, name in namen.items():
        assert name in styles, (
            f"{name} ist kein Platzhalter, den der Erzeuger kennt - die "
            "Regel bliebe im erzeugten Stylesheet ungefuellt stehen")
        werte[klasse] = str(styles[name])

    assert len(set(werte.values())) == 3, (
        "zwei Zustaende des Schildes tragen dieselbe Farbe: " + str(werte))


def test_the_three_states_arrive_with_three_different_symbols(box):
    """Und drei verschiedene ZEICHEN, weil Farbe allein nicht fuer jeden
    unterscheidet.

    Rot-Gruen ist die haeufigste Farbsehschwaeche, und "geschuetzt" mit
    "ungeschuetzt" zu verwechseln ist genau der Irrtum, den dieses
    Schild verhindern soll. Gemessen wird an den WIRKLICHEN Laeufen und
    nicht an der Vorlage: es geht darum, was auf der Leiste ankommt.
    """
    box.stub("nmcli", _nm(address="10.9.0.2/24"))
    verbunden = box.run()["text"]
    box.stub("nmcli", _nm())
    unvollstaendig = box.run()["text"]
    box.stub("nmcli", "exit 0")
    getrennt = box.run()["text"]

    zeichen = {"connected": verbunden, "stale": unvollstaendig,
               "disconnected": getrennt}
    assert all(zeichen.values()), zeichen
    assert len(set(zeichen.values())) == 3, (
        "zwei Zustaende des Schildes tragen dasselbe Zeichen: " + str(zeichen))


def test_the_bar_carries_the_symbol_alone_and_nothing_else(box):
    """Ein Zeichen, kein Wert - und das ist eine Entscheidung ueber die
    Breite.

    Alles, was das Schild sonst zu sagen haette (Verbindung, Bauart,
    Adresse), steht im Kurzhinweis. Ein Modul mit Wert waere eines,
    dessen Breite sich aendert - und die rechte Haelfte der Leiste ist
    seit dem 20.08.2026 danach geordnet, dass Klickziele stillstehen.
    """
    box.stub("nmcli", _nm(address="10.9.0.2/24"))

    text = box.run()["text"]

    assert len(text) == 1, (
        "das Schild traegt mehr als ein Zeichen und wird damit ein Modul "
        f"veraenderlicher Breite: {text!r}")


# --------------------------------------------------------------------
# Was das Modul mit der Maschine tut: lesen, und sonst nichts
# --------------------------------------------------------------------

def test_the_module_only_ever_reads(box):
    """Ein Leistenmodul darf die Verbindung des Nutzers NICHT anfassen.

    Es laeuft alle fuenf Sekunden, unbeaufsichtigt, auf jeder Leiste.
    Ein `nmcli connection up` darin waere ein VPN, das sich selbst
    aufbaut, weil jemand hingesehen hat.

    Geprueft an den mitgeschriebenen Aufrufen und nicht an der Vorlage:
    was das Modul TUT, steht in seinen Aufrufen.
    """
    box.settings(_document(IPSEC))
    box.state_file('{"virtual_ip":"172.20.4.9"}')
    box.run()
    box.settings(_document(WIREGUARD))
    box.run()

    verboten = ("up", "down", "add", "modify", "delete", "reload")
    for aufruf in box.calls_of("nmcli"):
        argumente = aufruf.split()[1:]
        assert "show" in argumente, f"nmcli ohne `show`: {aufruf}"
        assert not set(argumente) & set(verboten), (
            f"das Modul veraendert eine Verbindung: {aufruf}")
    for aufruf in box.calls_of("ip"):
        assert "addr" in aufruf and "show" in aufruf, (
            f"`ip` wird nicht nur gelesen: {aufruf}")


def test_the_module_never_reads_a_secret(box):
    """Kein Aufruf dieses Moduls nennt eine Schluesseldatei.

    `--status` liest keine - das ist die Eigenschaft, aus der es der
    Vertrag fuer vier rechtelose Leser ist. Diese Zeile haelt fest, dass
    das Schild daran nichts geaendert hat.
    """
    box.stub("nmcli", _nm(address="10.9.0.2/24"))
    box.run()

    for aufruf in box.calls_of("nmcli") + box.calls_of("pgrep"):
        for wort in ("secret", "psk", ".key", "password", "private"):
            assert wort not in aufruf.lower(), (
                f"ein Aufruf des Schildes fasst ein Geheimnis an: {aufruf}")
