# SPDX-License-Identifier: GPL-3.0-or-later
"""Abstand ist eine Leiter, und keine Zahl pro Regel.

WAS GEMELDET WURDE UND WAS GEMESSEN WURDE
    Der Nutzer am 11.08.2026: "B1: kein einheitlicher Abstand auf allen
    Seiten von ZepOs".

    Gemessen am selben Tag in src/templates/ags-style.template, dem
    Stylesheet aller Ueberlagerungsfenster: 294 Zahlen in padding- und
    margin-Regeln, in elf verschiedenen Werten (2, 4, 5, 6, 8, 10, 12,
    14, 16, 20, 24). Dazu in src/style_definition.py eine Leiter -
    STYLE_EWW_SPACE_TINY bis _XXL, achtundvierzig Platzhalter mit den
    fuenf Kopien pro Bildschirmplatz -, die KEINE EINZIGE Vorlage nannte.

    Beides zusammen ist der Grund, aus dem "einheitlich" nicht herstellbar
    war: es gab eine Leiter, die niemand benutzte, und daneben zwei-
    hundertvierundneunzig Einzelentscheidungen. Jede Uebereinstimmung
    zwischen zwei Regeln war ein Zufall, der beim naechsten Anfassen einer
    davon wieder verloren geht.

WAS DIESE DATEI BEWACHT
    Dass die Zahlen nicht zurueckkommen, dass jede Sprosse einen Leser
    hat, und dass die drei Oberflaechen - Schreibtisch, Assistent,
    Anmeldung - auf DERSELBEN Leiter stehen und nicht auf drei
    verschiedenen, die zufaellig gerade zusammenpassen.

    Was sie NICHT prueft, ist, ob eine Aenderung an einer Sprosse in der
    erzeugten Datei ankommt. Das tut tests/src/test_sizes.py schon, fuer
    JEDEN Eintrag in sizes.TABLE einzeln und aufgezaehlt aus der Tabelle
    statt von Hand - die Sprossen stehen dort drin, also stehen sie unter
    dieser Pruefung, ohne dass sie hier ein zweites Mal geschrieben
    werden muss. Eine zweite Kopie waere genau die Art Doppelung, gegen
    die dieses ganze Verzeichnis argumentiert.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src import sizes
# Auf Modulebene und nicht in der Pruefung: der Isolationswaechter aus
# tests/conftest.py laeuft waehrend eines Tests und verbietet jedes
# Schreiben ausserhalb von tmp_path - wozu auch das __pycache__ zaehlt,
# das pytests Assertion-Umschreibung beim ERSTEN Import eines
# Testmoduls anlegt. Ein Import mitten im Test faellt daran um.
from tests.src import test_sizes

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

# Jede Regel, die einen ABSTAND setzt. Nicht min-width und nicht
# border-radius: das eine ist eine Breite und das andere eine Ecke, und
# beide gehoeren nicht auf eine Abstandsleiter. Was mit ihnen ist, steht
# unten bei test_the_sizes_and_radii_are_measured_and_still_open.
SPACING_RULE = re.compile(
    r"^(?P<lead>\s*)(?P<prop>(?:padding|margin)(?:-(?:top|right|bottom|left))?)"
    r"\s*:\s*(?P<value>[^;{}]*?)\s*;")

# Die Stylesheets, die diese Regel bindet.
STYLESHEETS = sorted(
    list((SRC / "styles").glob("*.template"))
    + [SRC / "templates" / "ags-style.template"])

# DIE AUSNAHME FUER DIE LEISTE IST AUFGEBRAUCHT.
#
# Hier stand BAR_STYLE_LITERALS = 4 und darueber die Begruendung: am
# 11.08.2026 arbeitete ein zweiter Agent an bar-style.template, und zwei
# Haende in einer Datei sind kein doppelter Fortschritt. Ausgenommen war
# der BESTAND jenes Tages - vier Zahlen: zweimal 60px am Fenstertitel,
# ein "padding: 0px 12px" an den drei Symbolknoepfen und ein "margin: 2px"
# im Dock.
#
# Alle vier sind mit Aufgabe #88 gegangen, und zwar nicht durch
# Aufraeumen, sondern weil die Seitenleiste sie einzeln ueberholt hat:
# die 60px hielten den Fenstertitel aus der waagerechten Mitte, die es
# nicht mehr gibt; die anderen beiden stehen jetzt auf den Sprossen 12,
# 4 und 2.
#
# Die Obergrenze ist deshalb 0 - dieselbe wie fuer jedes andere
# Stylesheet - und der Sondertest darunter ist geloescht. Eine Ausnahme,
# die niemand mehr braucht, ist ein Loch, das offen steht.
BAR_STYLE = SRC / "styles" / "bar-style.template"
BAR_STYLE_LITERALS = 0

# Ein Nullabstand ist bei jedem Faktor null. Ihn ueber die Leiter zu
# fuehren hiesse, eine Sprosse "0" zu erfinden, die multipliziert wird
# und dabei null bleibt - ein Platzhalter, der nie etwas anderes sagt.
ZERO = re.compile(r"^0(px)?$")


def _without_comments(css: str) -> str:
    """CSS ohne Kommentare.

    Wortgleich zu tests/src/test_sizes.py und aus demselben Grund: jede
    Datei in diesem Baum ERKLAERT, was sie nicht mehr tut, und eine Suche
    nach "padding: 8px" wird von der Erklaerung wahr, in der steht, dass
    die 8 verschwunden ist.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    return "\n".join(line for line in css.splitlines()
                     if not line.lstrip().startswith("//"))


def _literals(path: Path) -> list[str]:
    """Jede Abstandsregel dieser Datei, die eine nackte Zahl traegt."""
    found = []
    for line in _without_comments(path.read_text(encoding="utf-8")).splitlines():
        match = SPACING_RULE.match(line)
        if not match:
            continue
        value = match.group("value")
        for token in value.split():
            if token.startswith("{{") or ZERO.fullmatch(token):
                continue
            if re.search(r"\d", token):
                found.append(f"{match.group('prop')}: {value}")
                break
    return found


# --------------------------------------------------------------------
# Die Zahlen kommen nicht zurueck
# --------------------------------------------------------------------

def test_no_spacing_in_a_stylesheet_is_a_literal():
    """294 Zahlen, gezaehlt am 11.08.2026, in elf verschiedenen Werten.

    Das ist die Pruefung, die "einheitlich" ueberhaupt erst haltbar
    macht. Ohne sie ist eine einmalige Aufraeumaktion genau das - einmal
    -, und die naechste Regel, die jemand schreibt, traegt wieder ihre
    eigene Zahl.
    """
    offenders = {}
    for path in STYLESHEETS:
        found = _literals(path)
        allowed = BAR_STYLE_LITERALS if path == BAR_STYLE else 0
        if len(found) > allowed:
            offenders[path.name] = found

    assert offenders == {}, (
        "diese Abstaende stehen als Zahl im Stylesheet statt auf einer "
        "Sprosse. Die Leiter ist {{" + sizes.SPACE_PREFIX + "N}} mit N aus "
        + ", ".join(str(step) for step in sizes.SPACE_LADDER) + " - "
        "src/sizes.py sagt, wie gerundet wird: "
        + "; ".join(f"{name}: {values}" for name, values in offenders.items()))


def test_every_rung_of_the_ladder_has_a_reader():
    """Die andere Haelfte: keine Sprosse ohne Regel.

    Genau daran ist die Leiter gestorben, die hier vorher stand -
    achtundvierzig Platzhalter, null Leser. sizes.py schreibt die Regel
    fuer seine ganze Tabelle auf ("JEDER EINTRAG HIER MUSS VON
    MINDESTENS EINER VORLAGE BENUTZT WERDEN"); das hier ist sie fuer die
    Abstandsleiter im besonderen, mit einer Fehlermeldung, die die
    ueberzaehlige Sprosse nennt.
    """
    text = "\n".join(_without_comments(path.read_text(encoding="utf-8"))
                     for path in STYLESHEETS)
    unused = [step for step in sizes.SPACE_LADDER
              if "{{" + f"{sizes.SPACE_PREFIX}{step}" + "}}" not in text]

    assert unused == [], (
        "diese Sprossen benutzt kein Stylesheet - eine Leiter, die nicht "
        "auf ihre eigene Oberflaeche passt, ist eine Liste: "
        + ", ".join(str(step) for step in unused))


@pytest.mark.parametrize("step", sizes.SPACE_LADDER)
def test_a_rung_carries_its_own_base(step):
    """Der Name nennt den Grundwert, und das ist nachpruefbar.

    Dieselbe Regel wie bei der Schriftleiter, und aus demselben Grund:
    sie macht die Ersetzung im Stylesheet mechanisch statt zu
    zweihundertdreizehn Ermessensentscheidungen. `padding: 12px` wird
    {{STYLE_SPACE_12}}, ohne dass jemand entscheiden muss, ob das nun LG
    oder BASE heisst - die alte Leiter hatte fuer genau diese Frage keine
    Antwort.
    """
    assert sizes.TABLE[f"{sizes.SPACE_PREFIX}{step}"].base == step


def test_the_rungs_stand_on_the_base_unit():
    """Eine Leiter, deren Sprossen nicht auf einem Raster liegen, ist
    eine Liste von Zahlen mit einem besseren Namen.

    Die halbe Sprosse ist die einzige Ausnahme und ausgeschrieben: sie
    ist der Haarabstand zwischen zwei Kacheln, und sie auf 4 zu heben
    hiesse, ihn zu verdoppeln.
    """
    off_grid = [step for step in sizes.SPACE_LADDER
                if step % sizes.SPACE_UNIT and step != sizes.SPACE_UNIT // 2]
    assert off_grid == [], (
        f"diese Sprossen liegen neben dem Raster von {sizes.SPACE_UNIT}: "
        + ", ".join(str(step) for step in off_grid))


def test_the_dead_ladder_does_not_come_back(monkeypatch, tmp_path):
    """Achtundvierzig Platzhalter, die ihr einziger Leser nicht benutzte.

    Geprueft an der ERZEUGTEN Menge und nicht am Quelltext: _per_screen()
    setzt seine Namen aus f-Strings zusammen, also faende eine Textsuche
    im Quelltext eine Rueckkehr ueber diesen Weg gar nicht.
    """
    test_sizes._no_compositor(monkeypatch)
    style = test_sizes._import_style(tmp_path, monkeypatch)

    dead = [name for name in dict(style.STYLE_VARIABLES)
            if name.startswith("STYLE_EWW_SPACE")]
    assert dead == [], (
        "die alte Abstandsleiter ist wieder da - benannt nach Groessen "
        "statt nach Zahlen, und fuenfmal pro Bildschirmplatz: "
        + ", ".join(sorted(dead)))


# --------------------------------------------------------------------
# Dieselbe Leiter auf allen drei Oberflaechen
# --------------------------------------------------------------------

def test_the_spacing_follows_the_font_factor(monkeypatch, tmp_path):
    """Der Kern der Meldung, und der Grund fuer die ganze Aenderung.

    Vorher: die Schriftleiter folgte dem Faktor und die Abstaende nicht.
    Bei der ausgelieferten 1.85 hiess das 24 px hohe Buchstaben in 8 px
    Innenabstand - die Schrift dreimal so hoch wie der Rand um sie
    herum. Das ist der Zustand, den jemand "nicht einheitlich" nennt.

    Gemessen wird an der ERZEUGTEN Datei und nicht am Platzhalterwert:
    ein Wert, der sich bewegt und in keiner Datei ankommt, ist genau der
    Regler, an dem dieses Projekt schon einmal gescheitert ist.
    """
    templates = [SRC / "templates" / "ags-style.template"]

    test_sizes._no_compositor(monkeypatch)
    small = test_sizes._import_style(tmp_path / "klein", monkeypatch,
                                     {"sizes": {"scale": 1.0}})
    test_sizes._no_compositor(monkeypatch)
    large = test_sizes._import_style(tmp_path / "gross", monkeypatch,
                                     {"sizes": {"scale": 2.0}})

    for step in sizes.SPACE_LADDER:
        name = f"{sizes.SPACE_PREFIX}{step}"
        assert small.STYLE_VARIABLES[name] != large.STYLE_VARIABLES[name], (
            f"{name} folgt dem Faktor nicht")

    import template_processor as processor

    assert (test_sizes._render(processor, small, templates, tmp_path / "a")
            != test_sizes._render(processor, large, templates, tmp_path / "b"))


def test_the_installer_stands_on_the_same_ladder():
    """Der Assistent kann src/sizes.py nicht importieren und traegt die
    Leiter deshalb ein zweites Mal.

    Der Kopf von installer/gui/branding.py sagt, warum der Import die
    verbotene Richtung waere (Spec §4.2), und dieselbe Datei traegt aus
    demselben Grund schon die sechs Markenfarben doppelt. Eine Kopie,
    die niemand nachrechnet, laeuft auseinander - das ist hier keine
    Vermutung, sondern die Geschichte von `warning`, das in einer der
    drei Farbkopien #f9e2af war und in der anderen #fab387.

    Nachgerechnet wird gegen sizes.rem_of() und nicht gegen eine zweite
    Liste in diesem Test, die dann die dritte Kopie waere.
    """
    from installer.gui import branding

    for step in sizes.SPACE_LADDER:
        name = f"SPACE_{step}"
        assert hasattr(branding, name), (
            f"der Assistent kennt die Sprosse {step} nicht")
        assert getattr(branding, name) == sizes.rem_of(step), (
            f"{name} ist im Assistenten {getattr(branding, name)!r} und "
            f"auf dem Schreibtisch {sizes.rem_of(step)!r}")

    # Und die Gegenrichtung: keine Sprosse im Assistenten, die es auf dem
    # Schreibtisch nicht gibt. Ohne sie koennte dort ein SPACE_10 stehen,
    # das nirgends sonst vorkommt, und die Pruefung oben ginge durch.
    extra = sorted(name for name in vars(branding)
                   if re.fullmatch(r"SPACE_\d+", name)
                   and int(name[6:]) not in sizes.SPACE_LADDER)
    assert extra == [], f"Sprossen, die es nur im Assistenten gibt: {extra}"


def test_the_installer_writes_no_spacing_of_its_own():
    """Und die Leiter wird auch BENUTZT.

    Sie zu definieren und daneben weiter 0.3rem zu schreiben waere
    dieselbe Sorte toter Regler wie die achtundvierzig Platzhalter, die
    diese Aenderung entfernt. Gemessen am ERZEUGTEN Stylesheet, also an
    dem, was GTK zu sehen bekommt - der Quelltext traegt f-String-
    Klammern, hinter denen sich eine Zahl verstecken koennte.
    """
    from installer.gui import branding

    offenders = []
    for line in _without_comments(branding.css()).splitlines():
        match = SPACING_RULE.match(line)
        if not match:
            continue
        for token in match.group("value").split():
            if ZERO.fullmatch(token):
                continue
            if token not in {sizes.rem_of(step) for step in sizes.SPACE_LADDER}:
                offenders.append(line.strip())
                break

    assert offenders == [], (
        "der Assistent setzt Abstaende neben der Leiter: " + "; ".join(offenders))


def test_a_rem_and_a_rung_are_the_same_thing_on_the_shipped_factor():
    """Wo die zwei Einheitensysteme aneinanderstossen, und wie weit.

    GTKs Vorgabeschrift ist Cantarell 11, also 14.67 px bei 96 dpi; ein
    rem im Assistenten ist genau das. Die Sprosse 8 des Schreibtischs
    war beim ausgelieferten Faktor 1.85 fuenfzehn Pixel - auf ein
    Drittel Pixel dasselbe.

    DAS GILT SEIT DEM 12.08.2026 NICHT MEHR, UND DIE FRAGE IST BEANTWORTET
        An dem Tag ist die ausgelieferte Grundschrift von 24 auf 20 px
        gefallen, weil sonst sechs Module nicht auf die Leiste passen
        (siehe DEFAULT_PX in src/sizes.py). Die Sprosse 8 ist damit 12 px
        und ein rem weiterhin 14.67 - sie laufen um 2.67 px auseinander.

        Welche der beiden Oberflaechen steht falsch? KEINE, und das ist
        die Antwort, die diese Pruefung verlangt hat. Verglichen wurde
        hier ein ABSTAND des Assistenten mit einem Abstand des
        Schreibtischs; was ein Mensch nebeneinander sieht, ist die
        SCHRIFT, und die trifft sich jetzt besser als vorher: der
        Assistent setzt Zeilen, Beschriftungen und Knoepfe auf 1.35rem,
        also 19.8 px, und der Schreibtisch auf DEFAULT_PX = 20 px. Vorher
        standen 19.8 gegen 24.

        Nachgehalten wird deshalb ab hier die Schrift und nicht der
        Abstand. Die Sprossen bleiben glatte Viertel-rem, damit im
        Stylesheet des Assistenten keine 0.375rem stehen - das ist die
        zweite Haelfte, die SPACE_REM_UNIT traegt, und sie gilt
        unveraendert.
    """
    gtk_default_rem = 14.67
    installer_body = 1.35 * gtk_default_rem

    assert sizes.rem_of(sizes.SPACE_REM_UNIT) == "1rem"

    desktop_body = int(sizes.value_of(
        f"{sizes.FONT_PREFIX}BODY", {}).removesuffix("px"))
    assert abs(desktop_body - installer_body) < 1.0, (
        f"der Assistent schreibt in {installer_body:.2f} px und der "
        f"Schreibtisch in {desktop_body} px - die zwei Oberflaechen "
        "stehen nicht mehr in derselben Groesse")

    # Und jede Sprosse ist ein sauberes Viertel-rem, ohne Nachkommarest,
    # der sich in einem Stylesheet als 0.375rem niederschlaegt.
    for step in sizes.SPACE_LADDER:
        rem = float(sizes.rem_of(step).removesuffix("rem"))
        assert (rem * 4).is_integer(), f"Sprosse {step} ist {rem}rem"


# --------------------------------------------------------------------
# Was gemessen und ABSICHTLICH nicht angefasst wurde
# --------------------------------------------------------------------

def test_the_sizes_are_measured_and_still_open():
    """Eine Zahl in einer Datei, die niemand aufschreibt, ist eine Zahl,
    die niemand findet.

    Die Abstandsleiter fasst padding und margin. min-width und
    min-height bleiben Literale, und das ist eine Entscheidung und kein
    Vergessen: sie sind BREITEN und HOEHEN. Sie haben in
    style_definition.py bereits ihre eigene, ebenfalls tote Leiter
    (STYLE_EWW_MIN_WIDTH_TINY bis _SCALE_LG - GEMESSEN am 18.08.2026,
    dieselbe `grep -rl` gegen src/templates/ UND src/styles/, dieselben
    NULL Treffer wie bei der Groessen-Kette, die Aufgabe 2 an diesem Tag
    entfernt hat). Die Fenstergroessen selbst kamen bis zum 18.08.2026
    zusaetzlich aus _WIDGET_WINDOW_WIDTHS - ebenfalls ohne Leser und mit
    derselben Aufgabe geloescht; jedes Fenster traegt seine Breite seither
    nur noch in seiner eigenen, ausgemessenen WIN_WIDTH-Konstante. Beides
    auf die Abstandsleiter zu ziehen waere falsch; sie brauchen eine
    eigene, und die ist eine zweite Aufgabe.

    BORDER-RADIUS STAND HIER MIT 54 UND IST JETZT NULL. Das war die
    zweite Haelfte des Satzes oben - "alle Werte im Baum sind heute 0
    oder aus STYLE_BORDER_RADIUS" -, und die 54 Nullen waren keine
    fehlenden Ecken, sondern jede Glasscheibe des Systems. Seit dem
    12.08.2026 gibt es die Rundungsleiter; tests/src/test_design.py
    haelt sie und laesst KEINE Zahl mehr zu, auch keine 0.

    Diese Pruefung haelt die uebrigen Zahlen fest, damit die naechste
    Messung weiss, wovon sie ausgeht - und faellt, sobald sie WACHSEN.
    """
    measured = {"min-width": 51, "min-height": 42, "border-radius": 0}
    ags = _without_comments(
        (SRC / "templates" / "ags-style.template").read_text(encoding="utf-8"))

    grown = {}
    for prop, count in measured.items():
        now = len(re.findall(rf"^\s*{prop}\s*:\s*[^;{{}}]*\d", ags, re.M))
        if now > count:
            grown[prop] = (count, now)

    assert grown == {}, (
        "diese Literale sind mehr geworden statt weniger: "
        + "; ".join(f"{prop}: {was} -> {now}" for prop, (was, now) in grown.items()))
