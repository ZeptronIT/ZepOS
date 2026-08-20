# SPDX-License-Identifier: GPL-3.0-or-later
"""Abgelegte Fenster im Fuss - sichtbar, erkennbar, abrufbar.

WAS GEMELDET WURDE, woertlich am 20.08.2026
    "sobald fenster minimiert sind werden sie nicht in der dock unten
     bei den aktiven fenstern angezeigt rechts neben den standard icons.
     ich moechte das dort auch minimiert angezeigt werden und immer
     aufgerufen werden koennen, aber ohne dieses fenster zu fokussieren
     sondern es normal erscheinen zu lassen."

    Drei Forderungen in einem Satz, und diese Datei misst alle drei
    einzeln: DASTEHEN, ALS ABGELEGT ERKENNBAR SEIN, MIT DEM RICHTIGEN
    BEFEHL ZURUECKKOMMEN.

DER COMPOSITOR, DEN ES HIER NICHT GIBT
    ags-dock.template liest den Zustand ueber ags-hyprland.template, und
    das ist ein Unix-Socket unter
    $XDG_RUNTIME_DIR/hypr/<Kennung>/.socket.sock - kein Programm, kein
    D-Bus, keine Bibliothek. Also stellt dieser Test genau diesen Socket
    hin und antwortet darauf selbst.

    Das ist der Grund, aus dem hier ECHTE Zusicherungen stehen und keine
    Textsuchen: der Fuss wird gebaut, die Knoepfe entstehen aus einer
    Fenstertabelle, die dieser Test schreibt, und ein Klick schickt
    seinen Befehl an denselben Socket zurueck, wo er mitgeschrieben wird.
    Was hier steht, hat der erzeugte Programmtext wirklich getan.

    NIE gegen den Compositor des Nutzers: die Kennung ist erfunden
    ("zepos-abgelegt"), das Laufzeitverzeichnis liegt unter tmp_path, und
    HYPRLAND_INSTANCE_SIGNATURE des Kindes zeigt genau dorthin. Ohne
    diese Variable faende ags-hyprland.template ueberhaupt keinen Socket
    (siehe socketDirectory() dort) - mit einer falschen faende es den der
    laufenden Sitzung.

WAS AN HYPRLAND GEMESSEN IST UND NICHT ERFUNDEN
    Die Fenstertabellen unten tragen `"workspace": {"id": -98, "name":
    "special:minimized"}`. Beides ist am 20.08.2026 im verschachtelten
    Compositor abgelesen (Hyprland 0.56.1, tests/render/desktop_session
    .py, headless 1920x1080), nachdem ein Fenster genau so minimiert
    wurde, wie der Knopf der Fensterleiste es tut:

        hyprctl dispatch movetoworkspacesilent special:minimized

    Vorher meldete `hyprctl clients -j` fuer dasselbe Fenster
    {"id": 2, "name": "2"}, nachher {"id": -98, "name":
    "special:minimized"} - und sonst nichts, was ein Dock lesen koennte:
    mapped blieb true, hidden blieb false.
"""
from __future__ import annotations

import json
import socket
import subprocess
import threading
from pathlib import Path

import pytest

from tests.gtk4_headless import broadwayd, start_broadwayd, stop_broadwayd
from tests.src.test_bar_headless import (
    CHILD_TIMEOUT, DESKTOP_ENTRIES, Run, _DISPLAYS, _bundle, _desktop_entries)

pytestmark = pytest.mark.allow_subprocess

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
CHILD = Path(__file__).resolve().parent / "dock_minimized_child.tsx"
DOCK = SRC / "templates" / "ags-dock.template"
STYLE = SRC / "styles" / "bar-style.template"
PLUGINS = SRC / "templates" / "hyprland-plugins-config.template"

# Der Name des Sonderbereichs. Er steht in DREI Vorlagen, und dass alle
# drei ihn gleich schreiben, misst test_der_name_des_ablagebereichs...
# weiter unten.
MINIMIZED = "special:minimized"

# Die Kennung, unter der die Fenster liegen. GEMESSEN, siehe Kopf - sie
# steht hier, damit die Tabellen unten nicht behaupten, was Hyprland
# nicht meldet.
MINIMIZED_ID = -98

# Der Bereich, den der Nutzer in diesem Aufbau gerade ansieht. Auf ihn
# muss ein zurueckgeholtes Fenster landen - und auf keinen anderen.
SICHTBAR = 3


def _client(address: str, klass: str, title: str,
            workspace: int, name: str) -> dict:
    """Ein Fenster, so wie `hyprctl clients -j` es meldet.

    Nur die Felder, die ags-hyprland.template als `Client` deklariert.
    Ein Feld mehr waere eine Behauptung ueber Hyprland, die niemand
    nachpruefen kann; ein Feld weniger liesse den Fuss auf `undefined`
    laufen.
    """
    return {
        "address": address,
        "title": title,
        "class": klass,
        "workspace": {"id": workspace, "name": name},
        "monitor": 0,
        "floating": False,
        # 0 heisst "kein Prozess dazu". iconFor() faellt dann auf das
        # Ersatzzeichen zurueck, und das ist hier richtig: was gemessen
        # wird, ist der Zustand des Knopfes und nicht sein Bild.
        "pid": 0,
    }


# Die vier Fenster des Hauptlaufs, und jedes steht fuer einen Fall, den
# es ohne dieses Fenster nicht gaebe.
FIREFOX = _client("0x100", "firefox", "Firefox", SICHTBAR, str(SICHTBAR))
# Eine ANGEHEFTETE Anwendung, deren einziges Fenster abgelegt ist. Der
# Fall, in dem ein Klick auf das angeheftete Symbol frueher ein zweites
# Programm gestartet haette.
DATEIEN_ABGELEGT = _client(
    "0x200", "org.gnome.Nautilus", "Dateien abgelegt", MINIMIZED_ID, MINIMIZED)
# Ein Fenster ohne Anheftung, offen. Es misst die GEGENPROBE: an ihm
# darf sich nichts geaendert haben.
LOSES_FENSTER = _client(
    "0x300", "weston-terminal", "Loses Fenster", SICHTBAR, str(SICHTBAR))
# Dasselbe, abgelegt.
LOSES_ABGELEGT = _client(
    "0x400", "mousepad", "Loses abgelegt", MINIMIZED_ID, MINIMIZED)
# EIN ANDERER SONDERBEREICH. Er ist der Grund, aus dem der Filter im
# Dock bleibt: ein Kritzelfenster hat seine eigene Taste
# (togglespecialworkspace) und gehoert nicht in die Reihe der laufenden
# Fenster. Ohne dieses Fenster maesse der Lauf "abgelegte kommen durch"
# und nicht "GENAU die abgelegten kommen durch".
KRITZEL = _client("0x500", "kritzel", "Kritzelfenster", -97, "special:kritzel")

FENSTER = [FIREFOX, DATEIEN_ABGELEGT, LOSES_FENSTER, LOSES_ABGELEGT, KRITZEL]

# Derselbe Satz Fenster, aber NICHTS ist abgelegt. Der Lauf damit
# beantwortet eine Frage fuer sich: kostet die Kennzeichnung Hoehe?
FENSTER_OHNE_ABLAGE = [
    FIREFOX,
    _client("0x200", "org.gnome.Nautilus", "Dateien abgelegt",
            SICHTBAR, str(SICHTBAR)),
    LOSES_FENSTER,
    _client("0x400", "mousepad", "Loses abgelegt", SICHTBAR, str(SICHTBAR)),
    KRITZEL,
]

MONITOR = "PROBE-1"


class FakeCompositor:
    """Ein Hyprland, das nur aus seinen beiden Sockets besteht.

    Es beantwortet die vier Fragen, die refresh() stellt, und schreibt
    jedes `dispatch` mit. Mehr braucht der Fuss nicht - und mehr zu
    bauen hiesse, Hyprland nachzubauen und damit zu messen, was der
    Nachbau tut.

    .socket2.sock steht daneben und schweigt. Ohne ihn meldet
    subscribe() "Kein Hyprland-Ereignissocket" auf stderr; die Verbindung
    kommt zustande und es passiert nichts weiter, was genau der
    Ruhezustand ist, den dieser Lauf messen will.
    """

    SIGNATURE = "zepos-abgelegt"

    def __init__(self, runtime: Path, clients: list[dict],
                 focused: int = SICHTBAR) -> None:
        self.directory = runtime / "hypr" / self.SIGNATURE
        self.directory.mkdir(parents=True, exist_ok=True)
        self.dispatches: list[str] = []
        self._running = True
        self._threads: list[threading.Thread] = []
        self._held: list[socket.socket] = []

        bereiche = [{"id": SICHTBAR, "name": str(SICHTBAR),
                     "monitor": MONITOR, "windows": 2}]
        if any(client["workspace"]["id"] == MINIMIZED_ID
               for client in clients):
            bereiche.append({"id": MINIMIZED_ID, "name": MINIMIZED,
                             "monitor": MONITOR, "windows": 1})
        self.answers = {
            "j/workspaces": json.dumps(bereiche),
            "j/monitors": json.dumps([{
                "name": MONITOR,
                "activeWorkspace": {"id": focused, "name": str(focused)},
                "focused": True,
            }]),
            "j/clients": json.dumps(clients),
            "j/activewindow": json.dumps(
                {"title": FIREFOX["title"], "class": FIREFOX["class"]}),
        }

        self._answering = self._listen(".socket.sock", self._answer)
        self._events = self._listen(".socket2.sock", self._hold)

    # -- Aufbau ------------------------------------------------------

    def _listen(self, name: str, handler) -> socket.socket:
        path = self.directory / name
        # sockaddr_un.sun_path fasst 108 Bytes. Ein zu langer Pfad
        # scheitert nicht laut, sondern gar nicht - und der Fuss saehe
        # dann einen leeren Zustand und der Test einen leeren Fuss.
        assert len(str(path)) < 100, f"{path} ist zu lang fuer einen Unix-Socket"
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(path))
        server.listen(16)
        server.settimeout(0.2)
        thread = threading.Thread(target=self._serve, args=(server, handler),
                                  daemon=True)
        thread.start()
        self._threads.append(thread)
        return server

    def _serve(self, server: socket.socket, handler) -> None:
        while self._running:
            try:
                connection, _ = server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            handler(connection)

    # -- Die beiden Sockets ------------------------------------------

    def _answer(self, connection: socket.socket) -> None:
        try:
            payload = connection.recv(65536).decode("utf-8", "replace")
            if payload.startswith("dispatch "):
                self.dispatches.append(payload[len("dispatch "):])
                connection.sendall(b"ok")
            else:
                connection.sendall(self.answers.get(payload, "").encode())
        finally:
            connection.close()

    def _hold(self, connection: socket.socket) -> None:
        """Der Ereignissocket: verbunden, still.

        Er wird FESTGEHALTEN und nicht geschlossen: ein geschlossener
        Strom laesst read_line_finish_utf8() null liefern, und
        subscribe() beendet dann seine Schleife - ein Zustand, den es auf
        einer laufenden Maschine nicht gibt.
        """
        self._held.append(connection)

    # -- Ende --------------------------------------------------------

    def stop(self) -> None:
        self._running = False
        for thread in self._threads:
            thread.join(timeout=5)
        for connection in self._held:
            connection.close()
        self._answering.close()
        self._events.close()

    def __enter__(self) -> "FakeCompositor":
        return self

    def __exit__(self, *_exception) -> None:
        self.stop()


@pytest.fixture(scope="module")
def bundle(tmp_path_factory) -> tuple[Path, Path]:
    """Das uebersetzte Kind, einmal je Lauf.

    Modulweit, weil `ags bundle` ueber eine Sekunde braucht und alle
    Laeufe darunter dieselbe Datei ausfuehren - nur mit einer anderen
    Fenstertabelle davor.
    """
    return _bundle(CHILD, tmp_path_factory.mktemp("abgelegt-bundle"))


def _lauf(bundle: tuple[Path, Path], root: Path, clients: list[dict],
          klicks: tuple[str, ...] = ()) -> tuple[Run, list[str]]:
    """Ein Lauf des Kindes gegen eine bestimmte Fenstertabelle.

    Zurueck kommen die Spur des Kindes UND die Befehle, die es an den
    Compositor geschickt hat. Die zweite Haelfte ist die eigentliche
    Messung: ein Knopf, der richtig AUSSIEHT und den falschen Befehl
    absetzt, ist genau der Fehler, um den es hier geht.
    """
    display_server = broadwayd()
    if display_server is None:
        pytest.skip("gtk4-broadwayd fehlt; es kommt mit dem Paket gtk4")

    bundled, ags = bundle
    runtime = root / "run"
    runtime.mkdir()
    # GLib lehnt ein weltlesbares XDG_RUNTIME_DIR ab und sagt es auf stderr.
    runtime.chmod(0o700)
    share = root / "share"
    binaries = root / "bin"
    _desktop_entries(share, binaries)

    trace = root / "trace"
    display = next(_DISPLAYS)
    server, _socket = start_broadwayd(display_server, runtime, display)
    compositor = FakeCompositor(runtime, clients)
    try:
        result = subprocess.run(
            [str(bundled)],
            env={
                # Nur die Attrappen, wie im Nachbarlauf: GIO liefert
                # einen Anwendungseintrag nur aus, wenn sein Programm auf
                # dem PATH liegt, und was der Entwickler installiert hat,
                # darf das Ergebnis nicht bewegen.
                "PATH": str(binaries),
                "HOME": str(root),
                "GDK_BACKEND": "broadway",
                "BROADWAY_DISPLAY": f":{display}",
                "XDG_RUNTIME_DIR": str(runtime),
                "XDG_CONFIG_HOME": str(root / "config"),
                "XDG_DATA_DIRS": str(share),
                "XDG_DATA_HOME": str(root / "data"),
                "DBUS_SESSION_BUS_ADDRESS": f"unix:path={root}/kein-bus",
                # DIE ZEILE, DIE DEN COMPOSITOR DES NUTZERS AUSSCHLIESST.
                # ags-hyprland.template sucht seinen Socket unter
                # $XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE;
                # beide zeigen hier in tmp_path.
                "HYPRLAND_INSTANCE_SIGNATURE": FakeCompositor.SIGNATURE,
                "ZEPOS_TRACE": str(trace),
                "ZEPOS_CSS": str(ags / "bar.css"),
                "ZEPOS_KLICKS": "|".join(klicks),
            },
            capture_output=True, text=True, timeout=CHILD_TIMEOUT,
        )
    finally:
        compositor.stop()
        stop_broadwayd(server)

    lauf = Run(result.returncode, result.stdout, result.stderr,
               trace.read_text() if trace.exists() else "", "")
    return lauf, list(compositor.dispatches)


@pytest.fixture(scope="module")
def abgelegt(bundle, tmp_path_factory) -> tuple[Run, list[str]]:
    """Der Hauptlauf: vier Fenster, zwei davon abgelegt, vier Klicks."""
    return _lauf(
        bundle, tmp_path_factory.mktemp("abgelegt-lauf"), FENSTER,
        klicks=("Loses abgelegt", "Loses Fenster", "Dateien (1)",
                "Firefox (1)"))


def _knoepfe(lauf: Run) -> list[str]:
    return [teil for teil in lauf.mark("kinder").split(",") if teil]


def _klassen(lauf: Run, aufschrift: str) -> list[str]:
    for teil in _knoepfe(lauf):
        if teil.startswith(f"{aufschrift}["):
            return teil[len(aufschrift) + 1:].split("]")[0].split()
    raise AssertionError(
        f"kein Knopf mit der Aufschrift {aufschrift!r} auf dem Fuss:\n"
        + "\n  ".join(_knoepfe(lauf)))


# --------------------------------------------------------------------
# 1. Es steht da
# --------------------------------------------------------------------

def test_a_minimized_window_gets_a_button_in_the_dock(abgelegt):
    """Die erste Haelfte der Bestellung, woertlich.

    "sobald fenster minimiert sind werden sie nicht in der dock unten
     [...] angezeigt" - jetzt schon, und zwar beide: das lose und das,
    dessen Anwendung angeheftet ist.
    """
    lauf, _ = abgelegt
    aufschriften = [teil.split("[")[0] for teil in _knoepfe(lauf)]
    for titel in ("Loses abgelegt", "Dateien abgelegt"):
        assert titel in aufschriften, (
            f"{titel!r} steht nicht auf dem Fuss - genau die Meldung vom "
            f"20.08.2026:\n  " + "\n  ".join(_knoepfe(lauf)))


def test_the_minimized_windows_stand_behind_the_open_ones(abgelegt):
    """"rechts neben den standard icons", und dahinter die Reihenfolge.

    Der Sonderbereich hat eine NEGATIVE Kennung. Ohne die erste Stufe
    der Sortierung in update() stuenden die abgelegten Fenster deshalb
    ganz vorn - vor den offenen und direkt hinter dem Trenner, also
    genau falschherum.
    """
    lauf, _ = abgelegt
    aufschriften = [teil.split("[")[0] for teil in _knoepfe(lauf)]
    offen = aufschriften.index("Loses Fenster")
    for titel in ("Loses abgelegt", "Dateien abgelegt"):
        assert aufschriften.index(titel) > offen, (
            f"{titel!r} steht VOR dem offenen Fenster:\n  "
            + "\n  ".join(_knoepfe(lauf)))


def test_a_window_on_another_special_workspace_stays_out(abgelegt):
    """Die Haelfte des alten Filters, die GILT.

    Ein Sonderbereich ist in Hyprland auch das Werkzeug fuer
    Kritzelfenster, und die haben ihre eigene Taste. Ausgenommen ist
    deshalb der NAME special:minimized und nicht "negative Kennung" -
    ohne diese Zusicherung waere der Unterschied nicht gemessen, und der
    naechste, der `< 0` schreibt, merkte nichts.
    """
    lauf, _ = abgelegt
    aufschriften = [teil.split("[")[0] for teil in _knoepfe(lauf)]
    assert "Kritzelfenster" not in aufschriften, (
        "ein Fenster auf special:kritzel steht im Fuss - der Fuss zeigt "
        "damit jeden Sonderbereich und nicht die Ablage:\n  "
        + "\n  ".join(_knoepfe(lauf)))


# --------------------------------------------------------------------
# 2. Man sieht ihm an, dass es abgelegt ist
# --------------------------------------------------------------------

def test_a_minimized_window_is_marked_as_one(abgelegt):
    """"ich moechte das dort auch MINIMIERT angezeigt werden".

    Ein Symbol, das aussieht wie ein offenes Fenster und keines ist,
    verwirrt mehr, als es hilft. Die Marke ist die Klasse `minimized`;
    was sie zeichnet, steht in bar-style.template.
    """
    lauf, _ = abgelegt
    for titel in ("Loses abgelegt", "Dateien abgelegt"):
        assert "minimized" in _klassen(lauf, titel), (
            f"der Knopf von {titel!r} traegt keine Marke: "
            f"{_klassen(lauf, titel)}")


def test_an_open_window_is_not_marked(abgelegt):
    """Die Gegenprobe. Eine Marke, die JEDER traegt, markiert nichts."""
    lauf, _ = abgelegt
    klassen = _klassen(lauf, "Loses Fenster")
    assert "minimized" not in klassen, (
        f"ein offenes Fenster gilt als abgelegt: {klassen}")


def test_the_mark_is_drawn_and_costs_no_pixel(abgelegt):
    """Wie die Marke aussieht - und was sie den Schirm kostet.

    Der Fuss haelt eine EXKLUSIVE Zone: was ihn hoeher macht, schiebt
    jedes Fenster des Schirms. Ein zusaetzliches Zeichen im Knopf oder
    ein zweiter Rahmen haette genau das getan.

    GEMESSEN wird deshalb nicht behauptet, sondern gerechnet: derselbe
    Fuss mit denselben vier Fenstern, einmal mit zweien davon abgelegt
    und einmal ohne, muss dieselbe Hoehe melden.
    """
    lauf, _ = abgelegt
    stil = STYLE.read_text(encoding="utf-8")
    regel = "#dock button.dock-button.minimized {"
    assert regel in stil, (
        "bar-style.template zeichnet die Klasse `minimized` nicht - der "
        "Knopf traegt eine Marke, die man nicht sieht")
    # Bis zur schliessenden Klammer AM ZEILENANFANG. Ein schlichtes
    # split("}") endete mitten im Platzhalter {{STYLE_OPACITY_DISABLED}} -
    # und der Block, der dabei herauskam, enthielt genau den Namen nicht,
    # nach dem hier gesucht wird.
    block = stil.split(regel, 1)[1].split("\n}", 1)[0]
    assert "opacity" in block and "{{STYLE_OPACITY_DISABLED}}" in block, (
        "die Marke ist nicht die Deckkraft aus der Groessentabelle, "
        f"sondern:{block}")
    # Kein fester Farbwert und keine feste Zahl - dieselbe Regel wie
    # ueberall in diesem Baum.
    for verdaechtig in ("#", "rgba(", "rgb("):
        assert verdaechtig not in block, (
            f"die Regel traegt einen festen Wert ({verdaechtig}):{block}")


def test_the_footer_is_not_one_pixel_higher_with_minimized_windows(
        bundle, tmp_path_factory, abgelegt):
    """Die zweite Haelfte derselben Frage, ausgefuehrt statt gelesen."""
    mit, _ = abgelegt
    ohne, _ = _lauf(bundle, tmp_path_factory.mktemp("ohne-ablage"),
                    FENSTER_OHNE_ABLAGE)
    assert mit.mark("hoehe") == ohne.mark("hoehe"), (
        f"der Fuss ist mit abgelegten Fenstern {mit.mark('hoehe')} px hoch "
        f"und ohne {ohne.mark('hoehe')} px - jeder Punkt Unterschied "
        "verschiebt jedes Fenster des Schirms, sobald jemand etwas "
        "minimiert")


# --------------------------------------------------------------------
# 3. Ein Klick holt es zurueck - und fokussiert es nicht
# --------------------------------------------------------------------

def test_a_click_on_a_minimized_window_moves_it_back_silently(abgelegt):
    """Der Kern der Bestellung, und er ist ein einziger Befehl.

    "immer aufgerufen werden koennen, aber ohne dieses fenster zu
     fokussieren sondern es normal erscheinen zu lassen."

    GEMESSEN am 20.08.2026 im verschachtelten Compositor an einem echten
    minimierten Fenster, alle drei in Frage kommenden Befehle:

        focuswindow             das Fenster BLEIBT auf
                                special:minimized und der Sonderbereich
                                wird als Ueberlagerung eingeblendet -
                                es ist weiterhin minimiert.
        movetoworkspace         holt es zurueck UND nimmt den Fokus mit
                                (activewindow wechselte).
        movetoworkspacesilent   holt es zurueck, activewindow ist vorher
                                und nachher dasselbe Fenster.

    Der dritte ist es also, und diese Zusicherung haelt genau ihn fest.
    """
    _, befehle = abgelegt
    erwartet = (f"movetoworkspacesilent {SICHTBAR},"
                f"address:{LOSES_ABGELEGT['address']}")
    assert erwartet in befehle, (
        f"der Klick hat {erwartet!r} nicht abgesetzt, sondern:\n  "
        + "\n  ".join(befehle))


def test_the_window_lands_on_the_workspace_the_user_is_looking_at(abgelegt):
    """Auf welchen Bereich - und warum nicht auf den urspruenglichen.

    `hyprctl clients -j` fuehrt kein Feld fuer den frueheren
    Arbeitsbereich; GEMESSEN am 20.08.2026 an der vollstaendigen Antwort
    fuer ein minimiertes Fenster - dreissig Felder, keines davon nennt
    einen. Und ein Fenster, das auf einem Bereich erscheint, den der
    Nutzer gerade nicht ansieht, ist fuer ihn nicht erschienen.

    Also der sichtbare, und zwar in JEDEM abgesetzten Befehl.
    """
    _, befehle = abgelegt
    zurueckgeholt = [befehl for befehl in befehle
                     if befehl.startswith("movetoworkspacesilent")]
    assert zurueckgeholt, f"kein Fenster zurueckgeholt:\n  {befehle}"
    for befehl in zurueckgeholt:
        ziel = befehl.split(" ", 1)[1].split(",", 1)[0]
        assert ziel == str(SICHTBAR), (
            f"{befehl!r} legt das Fenster auf Bereich {ziel} statt auf den "
            f"sichtbaren ({SICHTBAR})")


def test_no_click_ever_toggles_the_special_workspace(abgelegt):
    """Der Befehl, der NICHT vorkommen darf.

    `togglespecialworkspace` blendet die Ablage als Ueberlagerung ein.
    Das Fenster bliebe dabei minimiert - "ohne dieses fenster zu
    fokussieren sondern es normal erscheinen zu lassen" verlangt das
    Gegenteil.
    """
    _, befehle = abgelegt
    verboten = [befehl for befehl in befehle
                if "togglespecialworkspace" in befehl
                or befehl.startswith("movetoworkspace ")]
    assert verboten == [], (
        "ein Klick blendet die Ablage ein oder nimmt den Fokus mit: "
        f"{verboten}")


def test_an_open_window_still_just_gets_the_focus(abgelegt):
    """Die Gegenprobe: an einem gewoehnlichen Fenster aendert sich nichts."""
    _, befehle = abgelegt
    assert f"focuswindow address:{LOSES_FENSTER['address']}" in befehle, (
        "ein offenes Fenster wird nicht mehr einfach nach vorn geholt:\n  "
        + "\n  ".join(befehle))


# --------------------------------------------------------------------
# 4. Die angeheftete Anwendung, deren Fenster abgelegt ist
# --------------------------------------------------------------------

def test_a_pin_whose_only_window_is_minimized_looks_like_it_runs(abgelegt):
    """Ein minimiertes Programm LAEUFT.

    Ohne das saehe eine Anwendung, deren einziges Fenster abgelegt ist,
    aus wie "nicht gestartet" - und der Strich unter dem Symbol sagt
    "laeuft", nicht "ist zu sehen".
    """
    lauf, _ = abgelegt
    klassen = _klassen(lauf, "Dateien (1)")
    assert "running" in klassen, (
        f"die Anheftung von Dateien meldet nicht 'laeuft': {klassen}")
    assert "dock-pin" in klassen, f"das ist kein angehefteter Knopf: {klassen}"


def test_a_pin_whose_only_window_is_minimized_restores_it(abgelegt):
    """Und der Klick darauf startet KEIN zweites Programm.

    Das ist dieselbe Sorte Fehler wie die Fork-Bombe vom 17.08.2026, nur
    langsamer: wer minimiert hat, erwartet, dass ein Klick auf dasselbe
    Symbol es rueckgaengig macht - und nicht, dass er einen zweiten
    Dateimanager bekommt.
    """
    _, befehle = abgelegt
    erwartet = (f"movetoworkspacesilent {SICHTBAR},"
                f"address:{DATEIEN_ABGELEGT['address']}")
    assert erwartet in befehle, (
        f"der Klick auf die Anheftung hat {erwartet!r} nicht abgesetzt, "
        "sondern:\n  " + "\n  ".join(befehle))


def test_a_pin_with_an_open_window_is_unchanged(abgelegt):
    """Die Gegenprobe fuer die Anheftungen."""
    _, befehle = abgelegt
    assert f"focuswindow address:{FIREFOX['address']}" in befehle, (
        "eine laufende Anheftung holt ihr Fenster nicht mehr nach vorn:\n  "
        + "\n  ".join(befehle))


def test_a_minimized_window_gets_exactly_one_button(abgelegt):
    """Die Regel, die auch nach dieser Aenderung gilt.

    "Ein Fenster an beiden Stellen waere dasselbe Programm zweimal im
    Dock." Ein abgelegtes Fenster einer ANGEHEFTETEN Anwendung bekommt
    einen eigenen Knopf - und steht deshalb NICHT zusaetzlich in der
    Zaehlung seiner Anheftung als zweites Fenster.
    """
    lauf, _ = abgelegt
    aufschriften = [teil.split("[")[0] for teil in _knoepfe(lauf)]
    assert aufschriften.count("Dateien abgelegt") == 1, (
        f"das abgelegte Fenster steht mehrfach im Fuss: {aufschriften}")
    # Die Anheftung zaehlt genau ihr eines Fenster - das abgelegte.
    assert "Dateien (1)" in aufschriften, (
        f"die Anheftung zaehlt anders als 1: {aufschriften}")


# --------------------------------------------------------------------
# 5. Der Name, an dem alles haengt
# --------------------------------------------------------------------

def test_the_name_of_the_put_away_workspace_is_the_same_in_every_template():
    """Drei Vorlagen, ein Name.

    Der Knopf der Fensterleiste SCHREIBT ihn, SUPER+D blendet ihn ein,
    das Dock LIEST ihn. Wer ihn an einer Stelle aendert, nimmt dem Fuss
    lautlos jedes abgelegte Fenster wieder weg - kein Fehler, keine
    Meldung, nur ein Dock, das wieder ist wie am 20.08.2026 morgens.
    """
    schreiber = PLUGINS.read_text(encoding="utf-8")
    assert f"movetoworkspacesilent {MINIMIZED}" in schreiber, (
        f"{PLUGINS.name} minimiert nicht mehr nach {MINIMIZED}")

    leser = DOCK.read_text(encoding="utf-8")
    assert f'const MINIMIZED_WORKSPACE = "{MINIMIZED}"' in leser, (
        f"{DOCK.name} liest einen anderen Bereich als den, in den der "
        "Minimieren-Knopf schreibt")

    binder = (SRC / "templates" / "hyprland-universal-config.template"
              ).read_text(encoding="utf-8")
    assert f"workspace, {MINIMIZED}" in binder, (
        "die Taste blendet einen anderen Bereich ein als den, in den "
        "minimiert wird")


def test_the_dock_reads_the_name_and_not_the_number():
    """Warum der NAME und nicht die -98.

    Hyprland vergibt die Kennungen der Sonderbereiche in der
    Reihenfolge, in der sie entstehen. Wer ein Kritzelfenster vor dem
    ersten Minimieren oeffnet, bekommt eine andere Zahl und denselben
    Namen. Eine -98 im Programmtext waere eine Zahl, die auf der Maschine
    des Entwicklers stimmt.
    """
    leser = DOCK.read_text(encoding="utf-8")
    zeilen = [zeile for zeile in leser.splitlines()
              if "-98" in zeile and not zeile.lstrip().startswith(("//", "*"))]
    assert zeilen == [], (
        "die Kennung des Sonderbereichs steht im Programmtext und nicht "
        "nur in der Erklaerung:\n  " + "\n  ".join(zeilen))


def test_the_run_produced_no_critical_warning(abgelegt):
    """Eine CRITICAL-Zeile ist in diesem Projekt ein Testfehler.

    MIT EINER AUSNAHME, UND SIE GEHOERT DIESEM AUFBAU UND NICHT DEM FUSS
        Die Fenstertabelle oben traegt `"pid": 0` - dieser Test hat
        keine Prozesse, nur Zeilen. iconFor() geht deshalb bis an sein
        Ende durch (Klasse nicht im Symbolthema, kein Programm zur PID)
        und schreibt seine dokumentierte Zeile ins Protokoll, bevor es
        das Ersatzzeichen setzt. gjs macht aus jedem console.error ein
        Gjs-Console-CRITICAL.

        Das ist genau der Zweig, den iconFor() fuer diesen Fall
        vorsieht, und er hat seine eigene Zusicherung in
        test_bar_headless.py. Ausgenommen ist deshalb dieser eine
        Wortlaut - und nur er: jede ANDERE laute Zeile faellt weiter auf.
    """
    lauf, _ = abgelegt
    assert lauf.returncode == 0, f"das Kind endete mit Fehler:\n{lauf.report}"
    laut = [zeile for zeile in lauf.stderr.splitlines()
            if ("CRITICAL" in zeile or "Gjs-WARNING" in zeile)
            and "kein Programm zu seiner PID" not in zeile]
    assert laut == [], "der Lauf hat gemeckert:\n  " + "\n  ".join(laut)
