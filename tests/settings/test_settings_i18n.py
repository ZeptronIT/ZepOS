# SPDX-License-Identifier: GPL-3.0-or-later
"""Was in diesem Fenster auf dem Schirm steht, geht durch den Katalog.

WARUM DIESE ZUSICHERUNG STRUKTURELL MISST UND NICHT SPRACHLICH
    Die erste Zaehlung dieser Aufgabe suchte Umlaute und fand 86
    Literale. Die strukturelle Zaehlung findet 203. Der Unterschied sind
    Woerter, die im Deutschen keinen Umlaut tragen - `Speichern`,
    `Anwenden`, `Behalten`, `Drehung`, `Eingeschaltet`, `Bewegung`,
    `Herunternehmen`, `Angewendet.`, `Nur ZepOS`, `Nie`, `Melden`,
    `Umfang`, `Gespiegelt, 90 Grad`. Eine Regel, die nach Umlauten
    sucht, sagt bei jedem einzelnen davon "sauber", und wer sie benutzt,
    weiss nie, wann er fertig ist.

    Gemessen wird darum am ORT und nicht am Wort:

        Was in eine SENKE geht, ist Anzeigetext - egal welche
        Buchstaben darin stehen. Also muss es durch `_()` oder `N_()`.

    Eine Senke ist eine Beschriftung: `title=`, `subtitle=`, `label=`,
    `.set_title()`, das ZWEITE Argument von `add_response()`, die Zeilen
    einer `Gtk.StringList`. Die vollstaendige Liste steht unten und ist
    die einzige Stelle, an der sie steht.

WAS AUSDRUECKLICH KEINE SENKE IST
    Eine KENNUNG. `add_response("zurueck", _("Undo"))` fuehrt beide
    nebeneinander: das erste Argument ist der Name, unter dem der
    Rueckruf die Antwort wiedererkennt, das zweite die Aufschrift des
    Knopfes. `model.PAGE_NAMES` verlangt ausdruecklich ASCII
    (test_settings_model.py). Ein `css_classes=`, ein `icon_name=`, ein
    `application_id=`, ein Vergleichswert, ein Abbildungsschluessel -
    alles Maschine, alles bleibt.

    Dieselbe Trennung, die commit 318c082 fuer dieselben Dateien einmal
    von Hand gezogen hat. Sie steht hier, damit die naechste Zeile sie
    nicht wieder aufhebt.

WARUM ES `N_()` UEBERHAUPT GIBT, UND WAS OHNE ES PASSIERT
    model.py haelt 93 der 203 Anzeigetexte als MODULKONSTANTEN
    (LABEL_*, GROUP_*, NOTE_*, DIALS, PAGES, BAR_SIDES, UPDATE_LABELS).
    Eine Konstante wird beim IMPORT ausgewertet - GEMESSEN am
    02.09.2026 mit einem gebauten Katalog:

        LABEL = _("Desktop size")   beim Import
        Katalog umschalten
        LABEL                       -> "Desktop size"      folgt NICHT
        _("Desktop size")           -> die Uebersetzung     folgt

    Ein `_()` an der Definition waere also genau die Falle, in der die
    Beschriftung fuer immer in der Sprache stehen bleibt, die beim
    Programmstart galt. `N_()` ist die MARKE fuer die Auslese und gibt
    seinen Text unveraendert zurueck; uebersetzt wird an der Senke:

        LABEL_SCALE = N_("Desktop size")     # Definition, nur markiert
        title=_(model.LABEL_SCALE)           # Senke, hier uebersetzt

    Beides liest `xgettext --language=Python --keyword=_ --keyword=N_`
    heraus, auch innerhalb der Tabellen - gemessen am selben Tag an
    allen sechs Formen, die in diesen Dateien vorkommen.

WARUM DIE ERSTE PRUEFUNG UNTEN DIE WICHTIGSTE IST
    Ein Scan, der nichts mehr findet, meldet dasselbe "sauber" wie eine
    Oberflaeche ohne einen deutschen Rest. Am 02.09.2026 sind in diesem
    Baum acht Pruefstellen aufgefallen, die gruen waren und nichts
    gemessen haben. `test_der_scan_liest_die_dateien_wirklich` ist der
    Selbsttest dagegen: er verlangt eine Untergrenze an gefundenen
    Senken UND daran, dass die Aufloesung der Konstanten wirklich greift.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PAKET = ROOT / "settings" / "zepos_settings_gui"

# Die Dateien, die ein Fenster bauen. `__init__.py` ist leer, und
# style.py erzeugt ein STYLESHEET - eine CSS-Regel ist kein Satz, den
# jemand liest, und ihr einziger Text sind die Kommentare darin.
DATEIEN = ("model.py", "app.py", "bar.py", "bridge.py", "screens.py",
           "main.py")

# ------------------------------------------------------------------ #
# Die Senken. Die EINZIGE Liste davon in diesem Baum.
# ------------------------------------------------------------------ #

# Schluesselwortargumente, deren Wert auf dem Schirm steht.
SENKEN_KW = frozenset({
    "title", "subtitle", "label", "heading", "body", "tooltip_text",
    "placeholder_text", "text", "description", "secondary_text", "message",
})

# Methoden, deren ERSTES Argument auf dem Schirm steht.
SENKEN_METHODEN = frozenset({
    "set_title", "set_subtitle", "set_label", "set_text", "set_body",
    "set_heading", "set_tooltip_text", "set_button_label",
    "set_placeholder_text", "set_markup",
})

# Methoden, bei denen ein ANDERES Argument die Aufschrift ist.
# add_response(kennung, aufschrift) - siehe den Kopf dieser Datei.
SENKEN_METHODEN_INDEX = {"add_response": 1}

# Schluessel eines Woerterbuchs, dessen Wert bridge.py als JSON
# herausschreibt und das AGS-Fenster zeichnet.
SENKEN_JSON = frozenset({
    "label", "note", "title", "subtitle", "description", "text", "hint",
    "message", "heading", "body", "summary", "reason",
})

# Die Aufrufe, hinter denen ein Anzeigetext stehen darf.
#
# `ngettext` GEHOERT DAZU, und das war beim ersten Schreiben dieser
# Datei vergessen. Es ist kein Nachlassen der Regel, sondern ihre
# Vervollstaendigung: ngettext IST der Katalog, und fuer einen Text,
# dessen Form von einer Anzahl abhaengt, ist es der RICHTIGERE Aufruf
# als `_()`. Wie viele Formen eine Sprache hat, entscheidet die Sprache
# selbst - diese Regel steht im Plural-Forms-Kopf des Katalogs und nicht
# in einem `if` im Quelltext.
KATALOG = frozenset({"_", "N_", "ngettext"})

# ------------------------------------------------------------------ #
# Was NIE auf dem Schirm steht.
# ------------------------------------------------------------------ #

# Aufrufe, deren Argumente Maschine sind.
MASCHINEN_AUFRUFE = frozenset({
    "compile", "which", "strip", "lstrip", "rstrip", "get", "startswith",
    "endswith", "split", "rsplit", "removeprefix", "removesuffix",
    "getenv", "read_text", "write_text", "glob", "match", "search", "sub",
    "findall", "run", "check_output", "Popen", "add_css_class",
    "remove_css_class", "has_css_class", "set_name", "lookup_icon",
    "set_icon_name", "set_visible_child_name", "add_named", "set_property",
    "connect", "add_action", "lookup_action", "set_accels_for_action",
    "keys", "values", "items", "join", "load_from_data", "require_version",
    # add_titled_with_icon(kind, name, titel, symbol) traegt seinen Titel
    # aus model.PAGES herein und nie als Literal - der Name und das
    # Symbol daneben sind Kennungen.
    "add_titled_with_icon",
})
MASCHINEN_FUNKTIONEN = frozenset({
    "getattr", "setattr", "hasattr", "isinstance", "Path", "open",
})
# Schluesselwortargumente, die einen Maschinennamen entgegennehmen.
MASCHINEN_KW = frozenset({
    "css_classes", "icon_name", "action_name", "detailed_action_name",
    "css_name", "application_id", "name",
})

WORT = re.compile(r"[A-Za-zÄÖÜäöüß]{2,}")
FORMAT = re.compile(r"\{[^{}]*\}")
# Einheiten sind keine Sprache: "24px" traegt ein Wort im Sinne der
# Regel und trotzdem nichts zu uebersetzen.
EINHEITEN = frozenset({"px", "pt"})

# Ein Maschinenwort: ASCII, kein Leerzeichen, und entweder durchgehend
# EINE Schreibweise oder mit einem Trenner ZWISCHEN zwei Zeichen.
#
# DER TRENNER MUSS ZWISCHEN ZWEI ZEICHEN STEHEN, und das ist gemessen:
# eine Regel, die den Punkt ueberall zaehlt, haelt `Angewendet.` fuer
# einen Dateinamen und laesst genau die Einwort-Saetze durchfallen, um
# die es hier geht.
TRENNER = re.compile(r"[A-Za-z0-9][.:/=_\-][A-Za-z0-9]")
EINE_SCHREIBWEISE = re.compile(
    r"^(?:[a-z0-9_.:/=,;%@*&$#!?\[\]{}()<>+\-]+"
    r"|[A-Z0-9_.:/=,;%@*&$#!?\[\]{}()<>+\-]+)$")


def _traegt_ein_wort(wert: str) -> bool:
    ohne = FORMAT.sub(" ", wert)
    woerter = WORT.findall(ohne)
    if not woerter:
        return False
    return not all(wort.lower() in EINHEITEN for wort in woerter)


def _ist_maschinenwort(wert: str) -> bool:
    kern = wert.strip()
    if not kern or " " in kern or "\n" in kern or not kern.isascii():
        return False
    if TRENNER.search(kern):
        return True
    return bool(EINE_SCHREIBWEISE.match(kern))


class Quelle:
    """Eine Datei, ihre Eltern-Verweise und ihre Texteinheiten."""

    def __init__(self, pfad: Path):
        self.pfad = pfad
        self.baum = ast.parse(pfad.read_text(encoding="utf-8"), str(pfad))
        self.eltern: dict[int, ast.AST] = {}
        for knoten in ast.walk(self.baum):
            for kind in ast.iter_child_nodes(knoten):
                self.eltern[id(kind)] = knoten
        self.docstrings = {
            id(knoten.body[0].value)
            for knoten in ast.walk(self.baum)
            if isinstance(knoten, (ast.Module, ast.FunctionDef,
                                   ast.AsyncFunctionDef, ast.ClassDef))
            and knoten.body
            and isinstance(knoten.body[0], ast.Expr)
            and isinstance(knoten.body[0].value, ast.Constant)
            and isinstance(knoten.body[0].value.value, str)
        }

    # -- Gruppierung ------------------------------------------------ #
    def einheit(self, knoten: ast.AST) -> ast.AST:
        """Der aeusserste Knoten, der mit diesem Literal EINEN Text
        bildet.

        Benachbarte Stuecke einer Verkettung und die festen Teile einer
        f-Zeichenkette sind zusammen EIN msgid und nicht drei. Ohne
        diese Gruppierung zaehlte die Messung `' ist keine Zahl'` und
        `' liegt nicht zwischen '` als zwei Aufgaben, wo eine steht.
        """
        aktuell = knoten
        while True:
            eltern = self.eltern.get(id(aktuell))
            if isinstance(eltern, (ast.JoinedStr, ast.FormattedValue)):
                aktuell = eltern
                continue
            if isinstance(eltern, ast.BinOp) and isinstance(eltern.op, ast.Add):
                aktuell = eltern
                continue
            if (isinstance(eltern, ast.Call)
                    and isinstance(eltern.func, ast.Attribute)
                    and eltern.func.attr == "format"
                    and eltern.func.value is aktuell):
                aktuell = eltern
                continue
            return aktuell

    # -- Urteil ----------------------------------------------------- #
    def maschinenstelle(self, einheit: ast.AST) -> str | None:
        """Nicht None, wenn der ORT dieser Einheit Maschine ist."""
        eltern = self.eltern.get(id(einheit))

        if isinstance(eltern, ast.Compare):
            return "Vergleichswert"
        if isinstance(eltern, ast.Subscript):
            return "Index"
        if isinstance(eltern, ast.Dict) and any(
                schluessel is einheit for schluessel in eltern.keys):
            return "Abbildungsschluessel"
        if isinstance(eltern, ast.keyword) and eltern.arg in MASCHINEN_KW:
            return f"{eltern.arg}="
        if isinstance(eltern, ast.Call):
            fn = eltern.func
            stelle = next((i for i, arg in enumerate(eltern.args)
                           if arg is einheit), None)
            if isinstance(fn, ast.Attribute):
                if fn.attr in MASCHINEN_AUFRUFE:
                    return f".{fn.attr}()"
                if fn.attr == "add_response" and stelle == 0:
                    return "add_response()[0] - eine Kennung"
            if isinstance(fn, ast.Name) and fn.id in MASCHINEN_FUNKTIONEN:
                return f"{fn.id}()"
        return None

    def durch_den_katalog(self, einheit: ast.AST) -> bool:
        """Steht diese Einheit in einem `_()` oder `N_()`?"""
        aktuell = einheit
        while aktuell is not None:
            if (isinstance(aktuell, ast.Call)
                    and isinstance(aktuell.func, ast.Name)
                    and aktuell.func.id in KATALOG):
                return True
            aktuell = self.eltern.get(id(aktuell))
        return False

    def anzeigetexte(self) -> list[dict]:
        """Jede Texteinheit, die ein Mensch liest - mit der Angabe, ob
        sie durch den Katalog laeuft."""
        gefunden: dict[int, dict] = {}
        for knoten in ast.walk(self.baum):
            if not (isinstance(knoten, ast.Constant)
                    and isinstance(knoten.value, str)):
                continue
            if id(knoten) in self.docstrings:
                continue
            if not _traegt_ein_wort(knoten.value):
                continue
            einheit = self.einheit(knoten)
            eintrag = gefunden.setdefault(id(einheit), {
                "datei": self.pfad.name,
                "zeile": getattr(einheit, "lineno", knoten.lineno),
                "stuecke": [],
                "stelle": self.maschinenstelle(einheit),
                "uebersetzt": self.durch_den_katalog(einheit),
            })
            eintrag["stuecke"].append(knoten.value)

        anzeige = []
        for eintrag in gefunden.values():
            if eintrag["stelle"] is not None:
                continue
            if all(_ist_maschinenwort(s) for s in eintrag["stuecke"]):
                continue
            eintrag["text"] = "".join(eintrag["stuecke"])
            anzeige.append(eintrag)
        return sorted(anzeige, key=lambda e: e["zeile"])

    # -- Senken ----------------------------------------------------- #
    def senken(self) -> list[dict]:
        """Jede Stelle, an der ein Ausdruck zu einer Beschriftung wird."""
        gefunden = []
        for knoten in ast.walk(self.baum):
            if not isinstance(knoten, ast.Call):
                continue
            for schluesselwort in knoten.keywords:
                if schluesselwort.arg in SENKEN_KW:
                    gefunden.append({
                        "datei": self.pfad.name,
                        "zeile": schluesselwort.value.lineno,
                        "senke": f"{schluesselwort.arg}=",
                        "knoten": schluesselwort.value,
                    })
            fn = knoten.func
            if not isinstance(fn, ast.Attribute):
                continue
            if fn.attr in SENKEN_METHODEN and knoten.args:
                gefunden.append({
                    "datei": self.pfad.name,
                    "zeile": knoten.args[0].lineno,
                    "senke": f".{fn.attr}()",
                    "knoten": knoten.args[0],
                })
            stelle = SENKEN_METHODEN_INDEX.get(fn.attr)
            if stelle is not None and len(knoten.args) > stelle:
                gefunden.append({
                    "datei": self.pfad.name,
                    "zeile": knoten.args[stelle].lineno,
                    "senke": f".{fn.attr}()[{stelle}]",
                    "knoten": knoten.args[stelle],
                })
        return gefunden


def _quellen() -> list[Quelle]:
    return [Quelle(PAKET / name) for name in DATEIEN]


@pytest.fixture(scope="module")
def quellen() -> list[Quelle]:
    return _quellen()


# ------------------------------------------------------------------ #
# Der Selbsttest. Er steht zuerst, weil jede Zusicherung darunter
# wertlos ist, wenn er faellt.
# ------------------------------------------------------------------ #

def test_der_scan_liest_die_dateien_wirklich(quellen):
    """Ein Scan, der nichts findet, meldet "sauber".

    Darum steht hier eine Untergrenze und keine "groesser als null":
    ein Muster, das statt 200 noch drei Stellen trifft, ist kaputt und
    haelt sich fuer heil. Die Zahlen sind am 02.09.2026 gemessen (203
    Anzeigetexte, 183 verschiedene) und bewusst niedriger angesetzt, um
    nicht bei jeder neuen Zeile zu brechen - aber hoch genug, dass ein
    ausgefallenes Muster auffliegt.
    """
    assert len(quellen) == len(DATEIEN)
    texte = [text for quelle in quellen for text in quelle.anzeigetexte()]
    senken = [senke for quelle in quellen for senke in quelle.senken()]

    assert len(texte) > 150, (
        f"der Scan findet nur {len(texte)} Anzeigetexte - am 02.09.2026 "
        "waren es 203. Das Muster hat aufgehoert zu greifen, und jede "
        "Zusicherung darunter ist wertlos.")
    assert len(senken) > 60, (
        f"der Scan findet nur {len(senken)} Senken - am 02.09.2026 "
        "waren es 90.")

    # Und die Trennung greift auch NACH UNTEN: eine Messung, die alles
    # fuer Anzeigetext haelt, ist genauso kaputt wie eine, die nichts
    # findet. model.PAGE_NAMES, die Einstellungsschluessel und die
    # Symbolnamen MUESSEN aussortiert worden sein.
    alle = {text["text"] for text in texte}
    for kennung in ("groesse", "bildschirme", "aktualisierung", "enabled",
                    "schedule.interval", "--page", "zepos-generate",
                    "preferences-desktop-font-symbolic",
                    "STYLE_TERMINAL_FONT_SIZE"):
        assert kennung not in alle, (
            f"{kennung!r} ist eine Kennung und wurde als Anzeigetext "
            "gezaehlt - die Trennung greift nicht.")


def test_die_kennungen_der_seiten_bleiben_ascii(quellen):
    """`model.PAGE_NAMES` bleibt ASCII, auch wenn PAGES uebersetzt wird.

    PAGES traegt Kennung, Beschriftung und Symbol nebeneinander. Die
    Beschriftung geht durch den Katalog, die Kennung nicht: main.py
    prueft `--page` dagegen, und die .desktop-Datei schreibt sie in
    ihre Exec-Zeilen. Eine uebersetzte Kennung waere eine Aktion, die
    ins Leere zeigt.
    """
    model = next(q for q in quellen if q.pfad.name == "model.py")
    pages = None
    for knoten in ast.walk(model.baum):
        if isinstance(knoten, ast.AnnAssign) and isinstance(
                knoten.target, ast.Name) and knoten.target.id == "PAGES":
            pages = knoten.value
        if isinstance(knoten, ast.Assign) and any(
                isinstance(z, ast.Name) and z.id == "PAGES"
                for z in knoten.targets):
            pages = knoten.value
    assert pages is not None, "model.PAGES ist nicht mehr zu finden"

    namen = []
    for eintrag in pages.elts:
        erste = eintrag.elts[0]
        assert isinstance(erste, ast.Constant), (
            "die Kennung einer Seite ist kein Literal mehr - sie muss "
            "eines bleiben, sonst kann main.py sie nicht pruefen")
        namen.append(erste.value)

    assert namen, "model.PAGES ist leer"
    for name in namen:
        assert name.isascii() and " " not in name, (
            f"die Seitenkennung {name!r} ist keine Kennung mehr")


# ------------------------------------------------------------------ #
# Die Zusicherung selbst.
# ------------------------------------------------------------------ #

def test_jeder_anzeigetext_geht_durch_den_katalog(quellen):
    """Was ein Mensch liest, steht in `_()` oder `N_()`.

    Gemessen am ORT und nicht am Wort - der Kopf dieser Datei fuehrt
    aus, warum eine Umlaut-Regel hier nicht reicht.
    """
    offen = []
    for quelle in quellen:
        for text in quelle.anzeigetexte():
            if text["uebersetzt"]:
                continue
            offen.append(f"{text['datei']}:{text['zeile']} "
                         f"{text['text'][:60]!r}")

    assert offen == [], (
        f"{len(offen)} Anzeigetexte laufen nicht durch den Katalog:\n  "
        + "\n  ".join(offen))


def test_jede_senke_bekommt_uebersetzten_text(quellen):
    """Und von der anderen Seite: keine Senke nimmt ein nacktes Literal.

    Zwei Richtungen fuer dieselbe Sache, und das ist Absicht. Die
    Zusicherung darueber laeuft vom TEXT zur Marke und faengt einen
    Satz, der irgendwo definiert und irgendwo anders benutzt wird.
    Diese hier laeuft von der SENKE zum Text und faengt den Fall, in
    dem jemand eine Beschriftung unmittelbar hinschreibt. Die erste
    allein liesse eine neue Senke mit einem Maschinenwort darin durch;
    die zweite allein saehe die Konstanten in model.py nicht.

    Und sie schaut NACH UNTEN und nicht nach oben. Hier stand erst
    `durch_den_katalog(senke)`, also die Frage, ob die SENKE in einem
    `_()` steht - und meldete

        app.py .set_title() ' Language {name}.'

    fuer den Ausdruck

        _("Language {name}.").format(name=...) + " " + _(model.TIMING)

    Der ist vollstaendig uebersetzt; die Aufrufe stehen nur UNTER der
    Verkettung und nicht darueber. Gefragt wird darum je LITERAL.
    """
    nackt = []
    for quelle in quellen:
        for senke in quelle.senken():
            for literal in ast.walk(senke["knoten"]):
                if not (isinstance(literal, ast.Constant)
                        and isinstance(literal.value, str)):
                    continue
                if not _traegt_ein_wort(literal.value):
                    continue
                if _ist_maschinenwort(literal.value):
                    continue
                einheit = quelle.einheit(literal)
                if quelle.durch_den_katalog(einheit):
                    continue
                nackt.append(f"{senke['datei']}:{literal.lineno} "
                             f"{senke['senke']} {literal.value[:50]!r}")

    assert nackt == [], (
        f"{len(nackt)} Senken bekommen ein nacktes Literal:\n  "
        + "\n  ".join(nackt))
