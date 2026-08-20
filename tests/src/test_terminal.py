# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Rueckmeldung im Terminal, an den wirklich geschriebenen Zeichen.

WARUM DIESE DATEI AN ZEICHEN MISST UND NICHT AN VERHALTEN
    Eine Animation ist genau so lange eine Verbesserung, wie sie
    aufhoert. Eine halbe Scheibe, die stehen bleibt, oder ein Cursor,
    der verschwunden ist, kostet den Nutzer mehr als die stumme halbe
    Minute, die es vorher war - und beides sieht man einem gruenen Test
    ueber "es hat funktioniert" nicht an. Gemessen wird deshalb die
    Zeichenkette, die auf dem Bildschirm ankommt, in JEDEM Ausgang:
    Erfolg, Fehlschlag, Strg-C.

    Und die andere Haelfte derselben Frage: was ein Strom sieht, der
    KEIN Terminal ist - der Zeitgeber, der ALPM-Haken, jedes
    `zepos-update > protokoll`. Dort muss es null Steuerzeichen sein,
    nicht wenige.
"""
from __future__ import annotations

import re
import threading
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


@pytest.fixture
def terminal(monkeypatch):
    monkeypatch.syspath_prepend(str(SRC))
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("NO_COLOR", raising=False)
    import terminal as module

    return module


class Screen:
    """Ein Terminal, das nichts tut ausser mitschreiben.

    Mit Sperre, weil der Takt in einem eigenen Faden laeuft: eine Liste,
    an die zwei Faeden anhaengen, ist in CPython zwar heil, aber die
    Zusicherungen lesen sie waehrenddessen.
    """

    def __init__(self, *, tty: bool = True, encoding: str = "utf-8") -> None:
        self._tty = tty
        self.encoding = encoding
        self._parts: list[str] = []
        self._lock = threading.Lock()

    def isatty(self) -> bool:
        return self._tty

    def write(self, text: str) -> int:
        with self._lock:
            self._parts.append(text)
        return len(text)

    def flush(self) -> None:
        return None

    @property
    def text(self) -> str:
        with self._lock:
            return "".join(self._parts)


def _visible(text: str) -> str:
    return _ANSI.sub("", text.replace("\r", ""))


# --------------------------------------------------------------------
# Die dritte Auflage: sie muss enden. In JEDEM Ausgang.
# --------------------------------------------------------------------

def _erfolg() -> None:
    return None


def _fehlschlag() -> None:
    raise RuntimeError("der Generator ist gestorben")


def _strg_c() -> None:
    raise KeyboardInterrupt


@pytest.mark.parametrize("ausgang,fehler", [
    (_erfolg, None),
    (_fehlschlag, RuntimeError),
    (_strg_c, KeyboardInterrupt),
])
def test_the_slice_stops_in_every_exit(terminal, ausgang, fehler):
    """Erfolg, Fehlschlag, Strg-C - dreimal derselbe Schluss.

    Gemessen wird das Ende der Zeichenkette und nicht ein Zustand im
    Objekt: was das Terminal zuletzt bekommen hat, ist das, was der
    Nutzer sieht.
    """
    screen = Screen()

    def lauf() -> None:
        with terminal.live("etwas dauert", stream=screen) as line:
            line.note("mittendrin")
            ausgang()

    if fehler is None:
        lauf()
    else:
        with pytest.raises(fehler):
            lauf()

    text = screen.text
    assert text.endswith(terminal.SHOW_CURSOR), (
        "der Cursor ist nicht zurueckgegeben worden - er bleibt "
        "unsichtbar, bis der Nutzer `reset` tippt")
    # Nach dem letzten Loeschen steht nichts mehr auf der Zeile: kein
    # halber Ring, kein Rest einer Uhr.
    rest = text.rsplit(terminal.CLEAR_LINE, 1)[-1]
    assert rest == terminal.SHOW_CURSOR, (
        f"nach dem Aufraeumen steht noch etwas auf der Zeile: {rest!r}")
    assert terminal.HIDE_CURSOR in text


def test_a_stop_that_is_called_twice_gives_back_one_cursor(terminal):
    """Der Kontextmanager raeumt im finally auf; ein Aufrufer, der es
    selbst schon getan hat, soll dadurch nichts doppelt bekommen."""
    screen = Screen()
    with terminal.live("etwas dauert", stream=screen) as line:
        line.stop()
    assert screen.text.count(terminal.SHOW_CURSOR) == 1


def test_a_stream_that_goes_away_does_not_take_the_run_with_it(terminal):
    """Ein geschlossenes Fenster macht aus jedem write() einen OSError.
    Die Aktualisierung daran scheitern zu lassen, hiesse die Verzierung
    ueber die Sache zu stellen."""

    class Weg(Screen):
        def write(self, text: str) -> int:
            raise OSError("das Fenster ist zu")

    with terminal.live("etwas dauert", stream=Weg()) as line:
        line.note("mittendrin")
        line.write("eine Zeile")


# --------------------------------------------------------------------
# Die erste Auflage: nur an einem Terminal
# --------------------------------------------------------------------

def test_a_stream_that_is_not_a_terminal_never_sees_a_control_character(
        terminal):
    """Der Zeitgeber, der ALPM-Haken und jede Umleitung in eine Datei.

    Null Steuerzeichen und nicht wenige: dieses Projekt liest seine
    Protokolle, und ein Journal voller \\x1b[2K ist keins.
    """
    screen = Screen(tty=False)
    with terminal.live("etwas dauert", stream=screen) as line:
        line.note("mittendrin")
        line.write("eine Zeile des Kindes")

    assert "\x1b" not in screen.text
    assert "\r" not in screen.text
    # Die Ausgabe des KINDES geht trotzdem durch - sie ist die Sache und
    # nicht die Verzierung.
    assert screen.text == "eine Zeile des Kindes\n"


def test_a_dumb_terminal_says_it_cannot_and_is_believed(terminal,
                                                        monkeypatch):
    """TERM=dumb ist die ausdrueckliche Aussage "ich kann keine
    Steuersequenzen" - eine Emacs-Schale sagt das, und sie meint es."""
    monkeypatch.setenv("TERM", "dumb")
    assert terminal.possible(Screen()) is False


def test_a_closed_stream_is_not_a_terminal(terminal):
    class Zu(Screen):
        def isatty(self) -> bool:
            raise ValueError("I/O operation on closed file")

    assert terminal.possible(Zu()) is False


# --------------------------------------------------------------------
# Die zweite Auflage: sie verdeckt nichts
# --------------------------------------------------------------------

def test_a_foreign_line_stands_complete_and_above_the_slice(terminal):
    """Die Fehlermeldung des Generators ist das Wichtigste, was durch
    diese Roehre kommt. Sie wird nicht gekuerzt und nicht ueberschrieben:
    erst loeschen, dann die Zeile, dann neu zeichnen."""
    screen = Screen()
    fehler = ("  ✗ Failed: die Vorlage hat einen Platzhalter, den niemand "
              "fuellt - und dieser Satz ist absichtlich laenger als jedes "
              "Terminal breit ist")
    with terminal.live("zepos-generate --all", stream=screen) as line:
        line.write(fehler)

    assert fehler + "\n" in screen.text
    vor = screen.text.split(fehler)[0]
    assert vor.endswith(terminal.CLEAR_LINE), (
        "die fremde Zeile wurde geschrieben, ohne die Statuszeile vorher "
        "wegzuraeumen - dann steht sie in deren Resten")


def test_the_slice_never_grows_past_the_terminal(terminal, monkeypatch):
    """Eine zu lange Zeile bricht um, und \\r\\x1b[2K raeumt nur die
    letzte Zeile weg: uebrig bliebe ein Bruchstueck, das stehen bleibt,
    bis der Bildschirm scrollt."""
    monkeypatch.setenv("COLUMNS", "40")
    monkeypatch.setenv("LINES", "24")
    screen = Screen()
    with terminal.live("zepos-generate --all", stream=screen) as line:
        line.note("ein sehr langer Name einer Vorlage, die es so nicht "
                  "gibt (17 fertig)")

    # Jede Zeichnung fuer sich: sie beginnt mit \r\x1b[2K, und was
    # danach kommt, steht in der einen Zeile, die geloescht werden kann.
    for stueck in screen.text.split(terminal.CLEAR_LINE):
        for zeile in _visible(stueck).split("\n"):
            assert len(zeile) < 40, (
                f"{len(zeile)} Zeichen auf 40 Spalten: {zeile!r}")
    assert terminal.ELLIPSIS in screen.text


# --------------------------------------------------------------------
# Die vierte Auflage: sie luegt nicht - und sie stuerzt nicht ab
# --------------------------------------------------------------------

def test_the_slice_shows_only_what_it_was_told(terminal):
    """Kein Balken, keine Prozentzahl, kein "gleich fertig". Auf der
    Zeile steht, was der Aufrufer gemessen hat, und die verstrichene
    Zeit."""
    screen = Screen()
    with terminal.live("zepos-generate --all", stream=screen) as line:
        line.note("waybar (17 fertig)")

    sichtbar = _visible(screen.text)
    assert "zepos-generate --all" in sichtbar
    assert "waybar (17 fertig)" in sichtbar
    assert "0:00" in sichtbar
    assert "%" not in sichtbar


def test_a_console_without_braille_gets_ascii_instead_of_a_crash(terminal):
    """Auf einer Textkonsole ([Strg]+[Alt]+[F2]) - genau dort, wo jemand
    sitzt, dessen Schreibtisch nicht hochkommt - laeuft die Shell haeufig
    unter LANG=C. Ein print("⠋") wuerfe dort UnicodeEncodeError, und der
    Aktualisierer stuerbe mitten im Lauf an seiner Verzierung."""
    screen = Screen(encoding="ascii")
    with terminal.live("zepos-generate --all", stream=screen) as line:
        line.note("waybar (17 fertig)")

    screen.text.encode("ascii")
    assert any(zeichen in screen.text for zeichen in terminal.FRAMES_ASCII)
    for zeichen in terminal.FRAMES:
        assert zeichen not in screen.text


def test_the_colours_are_the_brands_own(terminal):
    """Kein zweiter Satz Farben. brand.py rechnet die Kontraste vor,
    tests/src/test_brand.py misst sie - hier wird nur nachgesehen, dass
    diese Datei keine eigenen erfindet."""
    import brand

    assert terminal.ACCENT == brand.CYAN_TEXT
    assert terminal.MUTED == brand.TEXT_MUTED


def test_no_colour_leaves_the_movement_and_takes_the_colour(terminal,
                                                            monkeypatch):
    """NO_COLOR (no-color.org) sagt etwas ueber Farbe und nichts ueber
    Bewegung."""
    monkeypatch.setenv("NO_COLOR", "1")
    screen = Screen()
    with terminal.live("zepos-generate --all", stream=screen) as line:
        line.note("waybar (17 fertig)")

    assert "38;2;" not in screen.text
    assert "zepos-generate --all" in _visible(screen.text)
