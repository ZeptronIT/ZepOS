# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Protokollanzeige des Assistenten darf nicht springen.

GEMELDET VOM MEDIUM am 12.08.2026, nach zwei vorangegangenen
Reparaturen an derselben Stelle:

    "das terminal flackert immernoch und verhaelt sich nicht normal wie
     ein terminal ... im installation wizard wackelt er die ganze zeit
     von oben nach unten buggy as hell"

DIE URSACHE, UND WARUM SIE ZWEIMAL UEBERLEBT HAT
    Die zweite Fassung haengte an, WENN der neue Text eine Verlaengerung
    des alten war, und ersetzte sonst den ganzen Puffer. Beides fuer
    sich richtig.

    Nur ist pacman kein Programm, das anhaengt. Es zeichnet seine
    Fortschrittszeilen staendig neu - mit \\r und mit ESC[nF, das den
    Cursor ueber bereits gezeigte Zeilen nach oben nimmt. Nach jeder
    Neuzeichnung ist der neue Text KEINE Verlaengerung mehr, also lief
    der Ersetzungszweig, mehrmals je Sekunde. set_text() setzt den Blick
    an den Anfang, die Zeile danach holt ihn ans Ende: das Wackeln ist
    nicht ein Zeichenfehler, sondern zwei richtige Anweisungen in
    falscher Reihenfolge, vier Mal in der Sekunde.

    Dasselbe ein zweites Mal, sobald der Log seine Zeilengrenze erreicht
    und vorne Zeilen wegfallen - dann ist der neue Text NIE wieder eine
    Verlaengerung.

WAS HIER GEMESSEN WIRD
    Nicht "der Text stimmt danach" - das taete ein set_text() auch, und
    genau das war der Fehler. Gemessen wird, WIE VIEL angefasst wurde:
    alles vor der ersten abweichenden Zeile muss unberuehrt bleiben.
    Ein Puffer, der nicht geloescht wird, verliert seine Blickposition
    nicht, und ohne verlorene Blickposition gibt es nichts, das
    zurueckspringen koennte.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _replace_tail():
    """Die Methode ohne `gi` laden.

    installer/gui/app.py importiert beim Modulimport Gtk, und `gi` liegt
    nicht in .venv - deshalb wird die Funktion aus dem Quelltext geholt
    statt das Modul zu importieren. Sie ist eine @staticmethod ohne
    Bezug auf self und laeuft so unveraendert.
    """
    quelle = (ROOT / "installer/gui/app.py").read_text(encoding="utf-8")
    anfang = quelle.index("def _replace_tail(")
    ende = quelle.index("\n\n", quelle.index("buffer.insert", anfang))
    text = quelle[anfang:ende]
    namensraum: dict = {}
    exec(compile(text, "app.py", "exec"), namensraum)   # noqa: S102
    return namensraum["_replace_tail"]


class Puffer:
    """So viel von GtkTextBuffer, wie die Methode anfasst - und ein
    Protokoll darueber, was sie angefasst hat."""

    def __init__(self, text: str = "") -> None:
        self.text = text
        self.geloescht: list[tuple[int, int]] = []
        self.eingefuegt: list[str] = []

    # Ein "Iterator" ist hier eine Zeichenposition.
    def get_start_iter(self) -> int:
        return 0

    def get_end_iter(self) -> int:
        return len(self.text)

    def get_iter_at_line(self, line: int):
        zeilen = self.text.split("\n")
        if line >= len(zeilen):
            return False, len(self.text)
        return True, sum(len(z) + 1 for z in zeilen[:line])

    def get_text(self, start: int, end: int, _hidden: bool) -> str:
        return self.text[start:end]

    def delete(self, start: int, end: int) -> None:
        self.geloescht.append((start, end))
        self.text = self.text[:start] + self.text[end:]

    def insert(self, at: int, text: str) -> None:
        self.eingefuegt.append(text)
        self.text = self.text[:at] + text + self.text[at:]


def _lauf(vorher: str, nachher: str) -> Puffer:
    puffer = Puffer(vorher)
    _replace_tail()(puffer, nachher)
    assert puffer.text == nachher, "der Text stimmt danach nicht"
    return puffer


def test_anhaengen_faesst_nichts_an():
    """Der haeufigste Fall: eine Zeile kommt dazu."""
    puffer = _lauf("a\nb", "a\nb\nc")

    assert puffer.geloescht == [], "es wurde geloescht, obwohl nur angehaengt wurde"
    assert puffer.eingefuegt == ["\nc"]


def test_eine_neugezeichnete_zeile_laesst_alles_davor_stehen():
    """DER FALL, DER DAS WACKELN MACHTE.

    pacman zeichnet die letzte Zeile neu. Frueher war der neue Text
    damit keine Verlaengerung, und der ganze Puffer wurde ersetzt.
    """
    alt = "\n".join(f"Zeile {n}" for n in range(1000)) + "\ncore  40%"
    neu = "\n".join(f"Zeile {n}" for n in range(1000)) + "\ncore  70%"

    puffer = _lauf(alt, neu)

    assert len(puffer.geloescht) == 1
    start, _ende = puffer.geloescht[0]
    unberuehrt = alt[:start]
    assert unberuehrt == "\n".join(f"Zeile {n}" for n in range(1000)) + "\n", (
        "es wurde mehr geloescht als die eine neugezeichnete Zeile")
    assert puffer.eingefuegt == ["core  70%"]


def test_zwei_zeilen_nach_oben_bleibt_ebenfalls_oertlich():
    """ESC[2F - pacman zeichnet BEIDE Zeilen eines Downloads neu."""
    kopf = "\n".join(f"Zeile {n}" for n in range(500))
    puffer = _lauf(f"{kopf}\ncore  10%\nextra  5%",
                   f"{kopf}\ncore  90%\nextra 80%")

    start, _ = puffer.geloescht[0]
    assert start == len(kopf) + 1, (
        "der unveraenderte Kopf wurde mit angefasst")


def test_wegfallende_zeilen_am_anfang_ersetzen_alles():
    """Die Zeilengrenze: vorne faellt etwas weg.

    Hier IST ein vollstaendiger Austausch richtig - aber er ist selten
    (einmal je Zeilengrenze), nicht viermal je Sekunde.
    """
    puffer = _lauf("a\nb\nc", "b\nc\nd")

    assert puffer.geloescht == [(0, 5)]


def test_gleicher_text_faesst_gar_nichts_an():
    """_show_log filtert das schon ab; diese Methode darf sich trotzdem
    nicht darauf verlassen - sie ist von aussen aufrufbar."""
    puffer = _lauf("a\nb\nc", "a\nb\nc")

    assert puffer.geloescht == [] and puffer.eingefuegt == []


def test_leerer_puffer_am_anfang():
    puffer = _lauf("", "erste Zeile")

    assert puffer.eingefuegt == ["erste Zeile"]


def test_die_anzeige_benutzt_den_schwanzersatz_wirklich():
    """Die Methode zu pruefen genuegt nicht - sie muss auch gerufen
    werden.

    GEMESSEN in der Mutationspruefung am 12.08.2026: `_replace_tail(...)`
    im Aufrufer durch `buffer.set_text(...)` zu ersetzen liess ALLE
    Tests oben gruen. Sie messen die Einheit, nicht die Verdrahtung -
    und das Wackeln kam aus der Verdrahtung.

    Dieselbe Luecke wie beim Radien-Waechter am selben Tag: ein
    Bauteil, das nachweislich richtig rechnet, und niemand, der prueft,
    dass jemand es fragt.
    """
    import ast

    quelle = (ROOT / "installer/gui/app.py").read_text(encoding="utf-8")
    baum = ast.parse(quelle)
    funktion = next(
        knoten for knoten in ast.walk(baum)
        if isinstance(knoten, ast.FunctionDef) and knoten.name == "_show_log")

    # OHNE Docstring, und das ist keine Feinheit: der Docstring dieser
    # Methode ERKLAERT den alten Fehler und nennt set_text() beim Namen.
    # Eine Pruefung ueber den Rohtext waere von der Begruendung erfuellt
    # worden statt vom Code - dieselbe Falle, die an diesem Tag schon
    # dreimal zugeschlagen hat (der Waechter im Livesystem, der
    # Radien-Detektor, die Farbpruefung).
    anweisungen = funktion.body
    if (anweisungen and isinstance(anweisungen[0], ast.Expr)
            and isinstance(anweisungen[0].value, ast.Constant)
            and isinstance(anweisungen[0].value.value, str)):
        anweisungen = anweisungen[1:]
    koerper = "\n".join(ast.unparse(knoten) for knoten in anweisungen)

    assert "_replace_tail(" in koerper, (
        "_show_log ruft den Schwanzersatz nicht - der Puffer wird wieder "
        "als Ganzes geschrieben, und der Blick springt viermal je Sekunde")
    assert "set_text(" not in koerper, (
        "_show_log schreibt den Puffer wieder als Ganzes; genau das war "
        "die Ursache des Wackelns")
