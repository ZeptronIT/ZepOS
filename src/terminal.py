#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Eine Rueckmeldung, die nur ein Terminal je zu sehen bekommt.

WARUM ES DIESE DATEI GIBT (20.08.2026)
    GEMELDET vom Nutzer: "ich will eine coole asci animation im terminal
    sehen statt nach zepos-update immer nicht". Ein `sudo zepos-update`
    holt die Paketdatenbank, spielt ein und ruft danach
    `zepos-generate --all` - auf einer frischen Maschine rund 30
    Sekunden, waehrend derer pacmans Ausgabe eingesammelt wird und der
    Nutzer auf einen stehenden Cursor sieht. Er kann in dieser Zeit
    nicht unterscheiden, ob etwas laeuft oder etwas haengt.

DIE VIER AUFLAGEN, UND WIE SIE HIER EINGEHALTEN WERDEN

  1. NUR AN EINEM TERMINAL. possible() fragt stream.isatty(), und zwar
     den Strom, auf den wirklich geschrieben wird. Der Zeitgeber
     (src/system/zepos-update.service, Type=oneshot ohne TTY), der
     ALPM-Haken und jedes `zepos-update > protokoll` bekommen dadurch
     nicht ein einziges Steuerzeichen zu sehen. Das ist keine
     Bequemlichkeit: dieses Projekt liest seine Protokolle, und ein
     Journal voller \\x1b[2K ist keins.

     Gefragt wird der STROM und nicht update._at_a_terminal(). Das sind
     zwei verschiedene Fragen: dort geht es darum, ob ein MENSCH den
     Lauf angestossen hat (Terminal UND Konto UND Sitzung), hier darum,
     ob das, was geschrieben wird, ueberhaupt gezeichnet werden kann.

  2. SIE VERDECKT NICHTS. Fremde Zeilen gehen durch write(): die
     Statuszeile wird geloescht, die fremde Zeile steht vollstaendig und
     mit Zeilenende, danach wird die Statuszeile neu gezeichnet. Eine
     Fehlermeldung des Generators kann so nie ueberschrieben werden -
     sie steht ueber der Scheibe, nicht darunter.

     Die Statuszeile selbst wird auf die Breite des Terminals gekuerzt.
     Ohne das schriebe eine zu lange Zeile in die naechste Zeile um, und
     \\r\\x1b[2K raeumt nur die letzte davon weg: uebrig blieben
     Bruchstuecke, die stehen bleiben, bis der Bildschirm scrollt.

  3. SIE ENDET. live() ist ein Kontextmanager; stop() steht in seinem
     finally und laeuft damit bei Erfolg, bei jeder Ausnahme und bei
     KeyboardInterrupt (Strg-C). stop() loescht die Zeile und holt den
     Cursor zurueck, ist mehrfach aufrufbar und schluckt einen
     geschlossenen Strom. tests/src/test_terminal.py misst genau diese
     drei Ausgaenge an den wirklich geschriebenen Zeichen.

  4. SIE LUEGT NICHT. Hier steht kein Fortschrittsbalken. Gezeigt werden
     nur Dinge, die gemessen sind: ein Takt, der laeuft, die verstrichene
     Zeit und ein Text, den der Aufrufer aus der Ausgabe des Kindes
     nimmt. Wie viele Schritte noch kommen, weiss `zepos-generate --all`
     selbst erst am Ende (es zaehlt seine Vorlagen beim Durchlaufen und
     ueberspringt einige davon) - eine Prozentzahl waere hier eine
     erfundene Zahl, und eine erfundene Zahl ist schlimmer als keine.
"""
from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from contextlib import contextmanager
from typing import Iterator, TextIO

# Dieselbe Wurzel wie in update.py und aus demselben Grund: dieses Modul
# wird als `src.terminal` aus der Testsuite und als flaches `terminal`
# aus /usr/share/zepos geladen.
try:
    from . import brand
except ImportError:  # pragma: no cover - der Weg aus /usr/share/zepos
    import brand

# Die Steuerzeichen, einzeln benannt, damit die Tests sie einzeln
# nachweisen koennen statt eine Zeichenkette zu glauben.
CSI = "\x1b["
CLEAR_LINE = "\r" + CSI + "2K"
HIDE_CURSOR = CSI + "?25l"
SHOW_CURSOR = CSI + "?25h"
RESET = CSI + "0m"

# Der Takt. Zehn Bilder je Sekunde: schnell genug, dass es lebt,
# langsam genug, dass eine serielle Konsole daran nicht erstickt.
TICK = 0.1

# Der Ring, der sich dreht. Braille-Punkte, weil sie in einer Zelle
# rotieren, ohne dass sich die Breite aendert - eine Laufschrift aus
# Zeichen verschiedener Breite ruckelt.
#
# UND WARUM ES EINEN ZWEITEN SATZ GIBT
#     Auf einer Textkonsole ([Strg]+[Alt]+[F2]) - genau dort, wo jemand
#     sitzt, dessen Schreibtisch nicht hochkommt - laeuft die Shell
#     haeufig unter LANG=C. Ein print("⠋") wirft dann
#     UnicodeEncodeError, und der Aktualisierer stuerbe mitten im Lauf
#     an seiner Verzierung. Der Ausweichsatz ist reines ASCII.
FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
FRAMES_ASCII = "|/-\\"
SEPARATOR = "·"
SEPARATOR_ASCII = "-"
ELLIPSIS = "…"
ELLIPSIS_ASCII = "..."

# Die Farben kommen aus der Marke und nicht aus dem Gefuehl: CYAN_TEXT
# ist der Akzent in der Fassung, die als TEXT lesbar ist (brand.py
# rechnet die Kontraste vor, tests/src/test_brand.py misst sie), und
# TEXT_MUTED ist das Grau, das die Nebensachen traegt.
ACCENT = brand.CYAN_TEXT
MUTED = brand.TEXT_MUTED

# TERM=dumb ist die ausdrueckliche Aussage "ich kann keine
# Steuersequenzen"; NO_COLOR (no-color.org) ist die ausdrueckliche
# Aussage "keine Farbe" und sagt ueber Bewegung nichts.
DUMB_TERMS = ("", "dumb")
NO_COLOR_ENV = "NO_COLOR"


def _colour(value: str) -> str:
    """#RRGGBB als 24-Bit-Vordergrundfarbe."""
    red, green, blue = (int(value[index:index + 2], 16)
                        for index in (1, 3, 5))
    return f"{CSI}38;2;{red};{green};{blue}m"


def possible(stream: TextIO | None = None) -> bool:
    """Darf auf diesen Strom gezeichnet werden?

    Ein geschlossener Strom wirft ValueError statt False zu liefern, ein
    Ersatzobjekt ohne isatty() wirft AttributeError; beides heisst hier
    dasselbe wie False.
    """
    stream = stream if stream is not None else sys.stdout
    if os.environ.get("TERM", "") in DUMB_TERMS:
        return False
    try:
        return bool(stream.isatty())
    except (ValueError, AttributeError):
        return False


def _encodable(text: str, stream: TextIO) -> bool:
    encoding = getattr(stream, "encoding", None) or "ascii"
    try:
        text.encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def _clock(seconds: float) -> str:
    """Verstrichene Zeit als m:ss - gemessen, nicht geschaetzt."""
    whole = int(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


class Live:
    """Eine Zeile, die sich selbst neu zeichnet, bis sie aufhoert.

    Der Takt laeuft in einem eigenen Faden, weil der Hauptfaden auf ein
    Kind wartet: waehrend `pacman -S` laeuft, kaeme aus dem Hauptfaden
    kein einziges Bild. Der Faden ist ein daemon und haelt nichts auf,
    und jede Zeichnung nimmt dieselbe Sperre wie write() - sonst
    schoebe sich ein halbes Bild in eine fremde Zeile.
    """

    def __init__(self, label: str, stream: TextIO, *,
                 colour: bool = True) -> None:
        self._label = label
        self._stream = stream
        self._frames = FRAMES if _encodable(FRAMES, stream) else FRAMES_ASCII
        self._separator = (SEPARATOR if _encodable(SEPARATOR, stream)
                           else SEPARATOR_ASCII)
        self._ellipsis = (ELLIPSIS if _encodable(ELLIPSIS, stream)
                          else ELLIPSIS_ASCII)
        self._accent = _colour(ACCENT) if colour else ""
        self._muted = _colour(MUTED) if colour else ""
        self._reset = RESET if colour else ""
        self._lock = threading.RLock()
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None
        self._frame = 0
        self._note = ""
        self._drawn = False
        self._started = time.monotonic()

    # ----------------------------------------------------------------
    # Was der Aufrufer benutzt
    # ----------------------------------------------------------------

    def note(self, text: str) -> None:
        """Was gerade geschieht - in den Worten dessen, der es tut."""
        with self._lock:
            self._note = text
            self._draw()

    def write(self, line: str) -> None:
        """Eine fremde Zeile, vollstaendig und ueber der Scheibe.

        Erst loeschen, dann schreiben, dann neu zeichnen. In dieser
        Reihenfolge kann keine Ausgabe des Kindes von der Animation
        ueberschrieben werden - die zweite der vier Auflagen.
        """
        with self._lock:
            self._erase()
            self._put(line + "\n")
            self._draw()

    def stop(self) -> None:
        """Aufhoeren, aufraeumen, den Cursor zurueckgeben.

        Mehrfach aufrufbar: der Kontextmanager ruft es im finally, und
        ein Aufrufer, der es selbst schon getan hat, soll dadurch keinen
        zweiten Cursor bekommen.
        """
        if self._stopped.is_set():
            return
        self._stopped.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=1.0)
        with self._lock:
            self._erase()
            self._put(SHOW_CURSOR)

    # ----------------------------------------------------------------
    # Das Innere
    # ----------------------------------------------------------------

    def start(self) -> None:
        with self._lock:
            self._put(HIDE_CURSOR)
            self._draw()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="zepos-live")
        self._thread.start()

    def _run(self) -> None:
        while not self._stopped.wait(TICK):
            with self._lock:
                if self._stopped.is_set():
                    return
                self._frame += 1
                self._draw()

    def _draw(self) -> None:
        if self._stopped.is_set():
            return
        self._put(CLEAR_LINE + self._render())
        self._drawn = True

    def _erase(self) -> None:
        if self._drawn:
            self._put(CLEAR_LINE)
            self._drawn = False

    def _render(self) -> str:
        """Die Zeile, auf die Breite des Terminals gekuerzt.

        Zusammengesetzt aus Stuecken mit ihrer Farbe, damit die Kuerzung
        die SICHTBAREN Zeichen zaehlt. Eine Kuerzung ueber die fertige
        Zeichenkette schnitte mitten in eine Steuersequenz - und was
        danach kommt, ist dann keine Farbe mehr, sondern Text.
        """
        turn = self._frames[self._frame % len(self._frames)]
        pieces = [(self._accent, turn), ("", " " + self._label)]
        if self._note:
            pieces.append((self._muted,
                           f" {self._separator} {self._note}"))
        pieces.append((self._muted,
                       f" {self._separator} "
                       f"{_clock(time.monotonic() - self._started)}"))

        # Eine Spalte bleibt frei: schreibt etwas in die letzte Spalte,
        # rueckt der Cursor bei manchen Terminals schon in die naechste
        # Zeile, und die naechste Loeschung raeumt dann die falsche.
        width = max(shutil.get_terminal_size(fallback=(80, 24)).columns - 1, 8)
        out: list[str] = []
        used = 0
        for colour, text in pieces:
            if used + len(text) > width:
                room = width - used - len(self._ellipsis)
                if room > 0:
                    out.append(f"{colour}{text[:room]}{self._ellipsis}"
                               f"{self._reset}")
                break
            out.append(f"{colour}{text}{self._reset}" if colour else text)
            used += len(text)
        return "".join(out)

    def _put(self, text: str) -> None:
        """Schreiben, und einen weggezogenen Strom nicht zum Fehler machen.

        Ein Terminal, das waehrend des Laufs verschwindet (das Fenster
        wird geschlossen), macht aus jedem write() einen OSError. Die
        Aktualisierung daran scheitern zu lassen, waere die Verzierung
        ueber die Sache zu stellen.
        """
        try:
            self._stream.write(text)
            self._stream.flush()
        except (OSError, ValueError):
            self._stopped.set()


class Silent:
    """Dieselbe Oberflaeche, ohne ein einziges Steuerzeichen.

    Der Zeitgeber, der ALPM-Haken und jede Umleitung in eine Datei
    bekommen dieses hier. note() SCHWEIGT: eine Zeile "Paketdatenbank
    wird geholt" je Lauf ist im Journal Laerm, den niemand bestellt hat
    (dieselbe Ueberlegung wie bei update.APPLY_NOTE). write() schreibt
    dagegen IMMER - das ist die Ausgabe des Kindes und nicht die
    Verzierung, und sie darf nirgends verloren gehen.
    """

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def note(self, text: str) -> None:
        return None

    def write(self, line: str) -> None:
        try:
            self._stream.write(line + "\n")
            self._stream.flush()
        except (OSError, ValueError):
            pass

    def stop(self) -> None:
        return None


@contextmanager
def live(label: str, *, stream: TextIO | None = None,
         enabled: bool | None = None) -> Iterator[Live | Silent]:
    """Die Rueckmeldung fuer die Dauer eines Blocks.

    `enabled` ist die Naht fuer die Tests - dieselbe wie runner= in
    update.py: ein Test kann die Zeichnung einschalten, ohne dass pytest
    ein Terminal haette, und sie ausschalten, ohne eins zu verstecken.

    Das finally ist die dritte Auflage. Es laeuft bei Erfolg, bei jeder
    Ausnahme und bei KeyboardInterrupt - in JEDEM Ausgang bleibt weder
    eine halbe Scheibe stehen noch ein Cursor verschwunden.
    """
    stream = stream if stream is not None else sys.stdout
    if enabled is None:
        enabled = possible(stream)
    if not enabled:
        yield Silent(stream)
        return

    line = Live(label, stream, colour=NO_COLOR_ENV not in os.environ)
    line.start()
    try:
        yield line
    finally:
        line.stop()
