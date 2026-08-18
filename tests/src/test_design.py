# SPDX-License-Identifier: GPL-3.0-or-later
"""Schrift, Symbol, Ecke und Grenze sind Skalen und keine Kataloge.

WAS GEMELDET WURDE
    Der Nutzer am 12.08.2026: "wir muessen auch ein generelles layout
    fuer ZepOS festlegen icon groessen und schriftgroessen sowie maximale
    element groessen haben wir das schon das sorgt dafuer das wir ein
    sehr schoenes design haben mit glasmorpihms und so weiter".

WAS GEMESSEN WURDE
    Abstaende JA - SPACE_LADDER, seit dem 11.08.2026, sieben Sprossen auf
    einem Raster von vier, und sie folgen dem Regler.

    Schrift NEIN. Sechzehn Platzhalter STYLE_EWW_FONT_9 bis _64, einer
    pro Pixelwert, den irgendwann jemand gebraucht hatte, plus
    STYLE_FONT_SIZE 13, _SMALL 12 und _LARGE 14. Die vier haeufigsten
    Werte des ganzen Schreibtischs - 11, 12, 13, 14 - lagen alle einen
    Pixel auseinander und machten zwei Drittel der 175 Regeln aus.

    Symbole NEIN. Sie standen auf derselben Leiter wie der Fliesstext und
    wurden frei gewaehlt, Regel fuer Regel: `.cc-label` 14 neben
    `.cc-icon` 18, `.cc-svc-label` 9 neben `.cc-svc-icon` 16 - Faktor
    1.29 an der einen Stelle, 1.78 an der anderen, fuer dieselbe Sache.

    Ecken NEIN, und das war der schlimmste Befund: 54 mal
    `border-radius: 0` in ags-style.template, davon elf auf einem
    `*-container`, also auf jeder Glasscheibe des Systems. Daneben sechs
    Radius-Platzhalter mit NULL Lesern. Der Schreibtisch hatte runde
    Fenster und runde Leistenmodule und quadratische Ueberlagerungen
    dazwischen.

    Grenzen GAB ES NICHT. `grep max-width`: kein Treffer. Fuenf Stellen
    begrenzten eine Zeile in ZEICHEN - 60, 40, 40, 60, 60 -, keine davon
    begruendet.

WAS DIESE DATEI BEWACHT
    Dass die Zahlen nicht zurueckkommen, dass jede Sprosse einen Leser
    hat, und dass die Sprossen auf EINEM Verhaeltnis stehen statt
    nebeneinander gewaehlt zu sein.

    Was sie NICHT prueft, ist, ob eine Aenderung an einer Sprosse in der
    erzeugten Datei ankommt. Das tut tests/src/test_sizes.py schon, fuer
    JEDEN Eintrag in sizes.TABLE einzeln und aus der Tabelle aufgezaehlt
    - die vierzehn Schrift- und Symbolrollen, die drei Rundungen und die
    zwei Grenzen stehen dort drin. Eine zweite Kopie waere genau die
    Doppelung, gegen die dieses Verzeichnis sonst argumentiert.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src import sizes
# Auf Modulebene, aus demselben Grund wie in tests/src/test_spacing.py:
# der Isolationswaechter verbietet waehrend eines Tests jedes Schreiben
# ausserhalb von tmp_path, wozu auch das __pycache__ zaehlt, das pytest
# beim ERSTEN Import eines Testmoduls anlegt.
from tests.src import test_sizes

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

# Jedes Stylesheet, das diese Leitern binden. Dieselbe Menge wie in
# test_spacing.py und aus demselben Grund: es sind die Dateien, in denen
# eine Regel eine Groesse setzen KANN.
STYLESHEETS = sorted(
    list((SRC / "styles").glob("*.template"))
    + [SRC / "templates" / "ags-style.template"])

# Jede Vorlage ueberhaupt - fuer die Frage, ob eine Rolle einen Leser
# hat. Der Starter liest seine Grenze aus hyprlaunch-config.template und
# nicht aus einem Stylesheet, und eine Rolle, die nur dort vorkommt, ist
# trotzdem gelesen.
TEMPLATES = sorted(list((SRC / "templates").glob("*.template"))
                   + list((SRC / "styles").glob("*.template")))


def _without_comments(css: str) -> str:
    """CSS ohne Kommentare.

    Wortgleich zu test_sizes.py und test_spacing.py und aus demselben
    Grund: jede Datei in diesem Baum ERKLAERT, was sie nicht mehr tut,
    und eine Suche nach "font-size: 14px" wird von der Erklaerung wahr,
    in der steht, dass die 14 verschwunden ist.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    return "\n".join(line for line in css.splitlines()
                     if not line.lstrip().startswith("//"))


def _named_anywhere(placeholder: str) -> list[Path]:
    needle = "{{" + placeholder + "}}"
    return [path for path in TEMPLATES
            if needle in _without_comments(path.read_text(encoding="utf-8"))]


@pytest.fixture
def processor(monkeypatch):
    """Der Prozessor, so importiert, wie der Generator ihn importiert."""
    monkeypatch.syspath_prepend(str(SRC))
    import template_processor

    return template_processor


def _font_names() -> list[str]:
    return [f"{sizes.FONT_PREFIX}{role}" for role, _ in sizes.FONT_ROLES]


def _icon_names() -> list[str]:
    # sizes.ICON_ROLES und nicht sizes.FONT_ROLES: DISPLAY hat seit
    # task-C (18.08.2026) keinen Symbol-Leser mehr, siehe die
    # Begruendung dort. Von Hand ausgezaehlt waere genau die Liste, die
    # dieser Test verhindern soll.
    return [f"{sizes.ICON_PREFIX}{role}" for role, _ in sizes.ICON_ROLES]


def _radius_names() -> list[str]:
    return [f"{sizes.RADIUS_PREFIX}{role}" for role, _ in sizes.RADIUS_ROLES]


# --------------------------------------------------------------------
# Die Skala ist EINE Skala
# --------------------------------------------------------------------

def test_every_font_rung_stands_on_the_one_ratio():
    """Jede Sprosse ist BASE_PX mal einer Potenz von FONT_RATIO.

    Das ist der Unterschied zwischen einer Skala und einer Liste. Die
    sechzehn Werte, die hier vorher standen, hatten kein Verhaeltnis
    zueinander - zwischen 9 und 10 lag der Faktor 1.11, zwischen 48 und
    64 der Faktor 1.33, und dazwischen jeder Wert, den irgendwer einmal
    getippt hatte.

    Gerechnet und nicht abgeschrieben: die Tabelle traegt Exponenten,
    also kann eine Sprosse gar nicht neben der Leiter liegen - solange
    niemand einen Grundwert von Hand danebenschreibt. Genau das prueft
    diese Zeile.
    """
    for role, step in sizes.FONT_ROLES:
        base = sizes.TABLE[f"{sizes.FONT_PREFIX}{role}"].base
        assert base == sizes.font_px(step), (
            f"{role} traegt {base} und die Leiter sagt "
            f"{sizes.font_px(step)}")


def test_the_shipped_font_rungs_are_the_measured_ones():
    """Die Zahlen ausgeschrieben, damit ein anderes Verhaeltnis auffaellt.

    Ohne diese Zeile waere der Test darueber eine Tautologie: er rechnet
    mit derselben Formel nach, mit der die Tabelle gebaut wird, und
    ginge deshalb bei JEDEM Verhaeltnis durch. Hier stehen die sieben
    Zahlen, die aus 1.2 wirklich herausfallen; wer das Verhaeltnis
    aendert, aendert sie und muss hier sagen, dass er es wollte.

    Und BODY ist der Anker: 13 px, dieselbe Zahl wie BASE_PX, also
    24 px bei dem Faktor, mit dem ZepOS ausgeliefert wird - die
    Schriftgroesse des Startmenues.
    """
    assert sizes.FONT_RATIO == 1.2
    assert {role: sizes.font_px(step) for role, step in sizes.FONT_ROLES} == {
        "MICRO": 9,
        "CAPTION": 11,
        "BODY": 13,
        "LEAD": 16,
        "TITLE": 19,
        "DISPLAY": 32,
        "HERO": 47,
    }
    assert sizes.font_px(0) == sizes.BASE_PX


def test_the_ladder_has_exactly_one_unoccupied_rung():
    """Eine Luecke ist erlaubt, ein Loch nicht.

    DISPLAY sitzt auf Exponent 5 und HERO auf 7, also fehlen als ROLLE
    die Exponenten 3, 4 und 6. Drei davon sind trotzdem besetzt - als
    Symbolgroesse der Rolle darunter, weil LINE_HEIGHT die Leiter um
    genau eine Sprosse verschiebt. Uebrig bleibt Exponent 4, 27 px, und
    der hat keinen Leser.

    Diese Pruefung faellt in beide Richtungen: wer eine Rolle so setzt,
    dass eine zweite Sprosse leer bleibt, bekommt sie zu sehen, und wer
    eine Rolle auf Exponent 4 legt, ohne die Zahl hier zu aendern,
    ebenso. Ein Katalog schleicht sich naemlich genau so zurueck - eine
    Sprosse nach der anderen, jede fuer sich begruendet.
    """
    occupied = {step for _role, step in sizes.FONT_ROLES}
    occupied |= {step + 1 for _role, step in sizes.FONT_ROLES}

    span = range(min(occupied), max(occupied) + 1)
    empty = sorted(step for step in span if step not in occupied)

    assert empty == [4], (
        "die Schriftleiter hat Loecher bei den Exponenten "
        + ", ".join(f"{step} ({sizes.font_px(step)} px)" for step in empty))


def test_no_two_rungs_are_a_pixel_apart():
    """Der Katalog, an einer Zahl erkannt.

    Er hatte 9/10, 11/12/13/14/15/16 und 18 - sieben Werte in einer
    Spanne, in der das Auge drei unterscheidet. Zwei Sprossen, die einen
    Pixel auseinanderliegen, sind keine zwei Entscheidungen, sondern
    dieselbe Entscheidung zweimal getroffen.

    Geprueft ueber Schrift UND Symbole zusammen, weil beide in derselben
    Datei nebeneinander stehen und ein Leser sie nicht auseinanderhalten
    kann.
    """
    rungs = sorted({sizes.font_px(step) for _r, step in sizes.FONT_ROLES}
                   | {sizes.icon_px(step) for _r, step in sizes.FONT_ROLES})
    tight = [(low, high) for low, high in zip(rungs, rungs[1:])
             if high - low < 2]

    assert tight == [], (
        "diese Sprossen sind nicht zu unterscheiden: "
        + ", ".join(f"{low}/{high}" for low, high in tight))


def test_a_role_name_carries_no_number():
    """Der Name sagt die Aufgabe und nicht das Ergebnis.

    STYLE_EWW_FONT_13 hiess nach dem Skalenwechsel weiter 13, waehrend
    24 herauskam - das Stylesheet las sich wie eine Datei voller
    Dreizehner, in der nirgends eine 13 steht. Ein Name mit einer Zahl
    darin kann diese Luege gar nicht vermeiden.
    """
    numbered = [name for name in _font_names() + _icon_names() + _radius_names()
                if re.search(r"\d", name)]
    assert numbered == [], (
        "diese Rollen tragen eine Zahl im Namen: " + ", ".join(numbered))


# --------------------------------------------------------------------
# Symbole haengen an der Zeile
# --------------------------------------------------------------------

def test_a_symbol_is_as_tall_as_the_line_it_sits_in():
    """GEMESSEN an elf Kopfzeilen, nicht gewaehlt.

    Neun der elf Fenster mit einer Kopfzeile setzten 18 px Text neben
    22 px Zeichen, also das 1.222-fache - jedes fuer sich, ohne
    voneinander zu wissen. Das ist zugleich, was CSS `line-height:
    normal` fuer Roboto und Fira Code aufloest.

    Die Zahlen stehen ausgeschrieben, aus demselben Grund wie oben: aus
    LINE_HEIGHT zurueckgerechnet waere das eine Tautologie, die bei
    jedem Wert durchginge.
    """
    assert sizes.LINE_HEIGHT == 1.2
    assert sizes.font_px(2) == 19 and sizes.icon_px(2) == 22, (
        "die Kopfzeile steht nicht mehr auf der gemessenen 18/22")

    for _role, step in sizes.FONT_ROLES:
        ratio = sizes.icon_px(step) / sizes.font_px(step)
        assert 1.15 <= ratio <= 1.30, (
            f"Sprosse {step}: {sizes.font_px(step)} px Text tragen "
            f"{sizes.icon_px(step)} px Zeichen, also das "
            f"{ratio:.2f}-fache")


def test_a_symbol_is_rounded_once_and_not_twice():
    """icon_px() rechnet aus dem UNGERUNDETEN Grundwert.

    Aus font_px() heraus waere TITLE 19 * 1.2 = 22.8 -> 23, waehrend die
    Leiter an dieser Stelle 13 * 1.2 hoch 3 = 22.46 -> 22 traegt. Ein
    Pixel, den niemand bestellt hat, und er faellt genau dort an, wo die
    meisten Symbole stehen.
    """
    for _role, step in sizes.FONT_ROLES:
        naive = max(1, int(sizes.font_px(step) * sizes.LINE_HEIGHT + 0.5))
        exact = sizes.icon_px(step)
        assert exact == max(1, int(
            sizes.BASE_PX * sizes.FONT_RATIO ** (step + 1) + 0.5)), (
            f"Sprosse {step} rundet zweimal: {naive} statt {exact}")


def test_the_symbol_of_a_role_is_the_next_rung():
    """Die Folge daraus, dass LINE_HEIGHT und FONT_RATIO gleich sind.

    Sie sind ZWEI Konstanten mit zwei Herkuenften - die eine kommt aus
    elf Kopfzeilen, die andere aus 128 Textregeln - und heute zufaellig
    dieselbe Zahl. Solange das so ist, liegt jedes Symbol genau auf der
    naechsten Sprosse, und die Leiter bleibt EINE Leiter statt zweier,
    die sich kreuzen.

    Wandert eine der beiden, faellt diese Pruefung, und dann ist zu
    entscheiden, ob die Symbole eine eigene Leiter bekommen - statt dass
    es niemandem auffaellt.
    """
    for _role, step in sizes.FONT_ROLES:
        assert sizes.icon_px(step) == sizes.font_px(step + 1), (
            f"Sprosse {step}: das Symbol misst {sizes.icon_px(step)}, die "
            f"naechste Sprosse {sizes.font_px(step + 1)}")


# --------------------------------------------------------------------
# Keine Sprosse ohne Leser, keine Zahl ohne Sprosse
# --------------------------------------------------------------------

@pytest.mark.parametrize("name", _font_names() + _icon_names()
                         + _radius_names()
                         + [f"{sizes.RADIUS_PREFIX}FULL",
                            f"{sizes.MEASURE_PREFIX}LINE",
                            f"{sizes.MEASURE_PREFIX}PROSE"])
def test_every_rung_has_a_reader(name):
    """Eine Sprosse, die keine Vorlage nennt, ist der tote Regler.

    Genau daran ist die Leiter gestorben, die vor der Abstandsleiter
    stand - achtundvierzig Platzhalter, null Leser -, und genau daran
    starben die sechs Radius-Platzhalter, die diese Aenderung entfernt
    (STYLE_EWW_RADIUS_SM/_MD/_BASE/_LG, _CIRCLE und
    STYLE_WALLPAPER_THUMBNAIL_RADIUS).

    Einzeln aufgezaehlt und nicht als Liste geprueft, damit die
    Fehlermeldung die Rolle nennt, die keiner braucht.
    """
    assert _named_anywhere(name), (
        f"{name} wird von keiner Vorlage gelesen - eine Leiter, die nicht "
        f"auf ihre eigene Oberflaeche passt, ist eine Liste")


def test_no_font_size_in_a_stylesheet_is_a_literal():
    """175 Regeln, gezaehlt am 12.08.2026.

    tests/src/test_sizes.py prueft dasselbe fuer ags-style.template
    allein, weil dort die 164 Literale standen, die den Anfang gemacht
    haben. Hier steht es fuer JEDES Stylesheet - der Starter und die
    Zwischenablage trugen ihre vierzehn in eigenen Dateien, und eine
    Regel, die nur eine Datei bindet, ist eine Einladung, die naechste
    Zahl nebenan zu schreiben.
    """
    offenders = {}
    for path in STYLESHEETS:
        code = _without_comments(path.read_text(encoding="utf-8"))
        found = re.findall(r"font-size:\s*[\d.]+\s*(?:px|pt|em|rem)?\s*;", code)
        if found:
            offenders[path.name] = found

    assert offenders == {}, (
        "diese Schriftgroessen stehen als Zahl im Stylesheet statt auf "
        "einer Rolle: "
        + "; ".join(f"{name}: {values}" for name, values in offenders.items()))


def test_the_dead_catalogue_does_not_come_back(tmp_path, monkeypatch):
    """Sechzehn Schriftnamen und sechs Ecken, alle mit null oder einem Leser.

    Geprueft an der ERZEUGTEN Platzhaltermenge und nicht am Quelltext:
    _per_screen() setzt seine Namen aus f-Strings zusammen, also faende
    eine Textsuche eine Rueckkehr ueber diesen Weg gar nicht.
    """
    test_sizes._no_compositor(monkeypatch)
    style = test_sizes._import_style(tmp_path, monkeypatch)

    dead = sorted(name for name in dict(style.STYLE_VARIABLES)
                  if name.startswith("STYLE_EWW_FONT")
                  or name.startswith("STYLE_EWW_RADIUS")
                  or name in {"STYLE_FONT_SIZE", "STYLE_FONT_SIZE_SMALL",
                              "STYLE_FONT_SIZE_LARGE", "STYLE_ICON_SIZE",
                              "STYLE_BORDER_RADIUS",
                              "STYLE_BORDER_RADIUS_SMALL",
                              "STYLE_DOCK_BORDER_RADIUS",
                              "STYLE_TOOLTIP_BORDER_RADIUS",
                              "STYLE_WALLPAPER_THUMBNAIL_RADIUS"})

    assert dead == [], (
        "der Katalog ist wieder da - Namen, die eine Zahl statt einer "
        "Rolle nennen: " + ", ".join(dead))


# --------------------------------------------------------------------
# Die Ecken
# --------------------------------------------------------------------

# hyprland-failsafe-config.template ist ausgenommen, und das ist keine
# Bequemlichkeit: die Datei ist die Konfiguration, die laeuft, wenn die
# erzeugte nicht mehr laedt ("a minimal safe configuration that should
# work on ANY system"). Ein Wert daraus, der aus den Einstellungen des
# Nutzers kommt, waere genau der Weg, auf dem eine kaputte Einstellung
# auch noch die Rettung mitnimmt.
# Der Wert bis zum Semikolon, MIT geschweiften Klammern.
#
# Hier stand [^;{}]+ - ohne Klammern. Damit konnte
# test_no_corner_comes_from_a_placeholder_beside_the_ladder per
# Konstruktion nichts finden: sein einziger Zweck sind Werte der Form
# {{STYLE_...}}, und genau die schloss das Muster aus. Gemessen am
# 12.08.2026 beim Zusammenfuehren des Sperrbildschirms - er brachte
# STYLE_LOCK_FIELD_RADIUS (999px) mit, einen sechsten Namen neben der
# Leiter, und der Waechter schwieg.
#
# Die Literal-Pruefung darueber lief trotzdem richtig, weil ein Literal
# keine Klammern hat. Ein Muster, das fuer die eine Haelfte stimmt und
# die andere unsichtbar macht, ist schlimmer als keines: die gruene
# Zeile behauptet, es sei geprueft.
RADIUS_RULE = re.compile(r"^\s*border-radius\s*:\s*(?P<value>[^;]+);")


def test_no_corner_in_a_stylesheet_is_a_literal():
    """54 rechte Ecken und zehn Zahlen, gezaehlt am 12.08.2026.

    Die 54 Nullen sind der Grund, aus dem diese Pruefung eine
    Gleichbehandlung von 0 und 4px braucht: eine Null ist hier keine
    "keine Ecke", sondern eine ENTSCHEIDUNG gegen die Ecke, und sie
    stand auf jeder Glasscheibe des Systems. Anders als beim Abstand,
    wo eine Null bei jedem Faktor null bleibt und deshalb erlaubt ist,
    ist eine Ecke von 0 eine Form.
    """
    offenders = {}
    for path in STYLESHEETS:
        found = []
        for line in _without_comments(
                path.read_text(encoding="utf-8")).splitlines():
            match = RADIUS_RULE.match(line)
            if match and "{{" not in match.group("value"):
                found.append(match.group("value").strip())
        if found:
            offenders[path.name] = found

    assert offenders == {}, (
        "diese Ecken stehen als Zahl im Stylesheet statt auf einer "
        "Sprosse. Die Leiter ist {{" + sizes.RADIUS_PREFIX + "ROLLE}} mit "
        "ROLLE aus " + ", ".join(role for role, _ in sizes.RADIUS_ROLES)
        + ", dazu FULL fuer den Kreis: "
        + "; ".join(f"{name}: {values}" for name, values in offenders.items()))


def test_no_corner_comes_from_a_placeholder_beside_the_ladder():
    """Eine Ecke aus einem Platzhalter, der nicht auf der Leiter steht,
    ist genau derselbe Fehler wie eine Zahl - nur schwerer zu sehen.

    So sah der Bestand am 12.08.2026 aus: STYLE_BORDER_RADIUS (0px),
    _SMALL (8px), STYLE_TOOLTIP_BORDER_RADIUS (10px),
    STYLE_DOCK_BORDER_RADIUS (0px) - vier einzeln gewachsene Namen -,
    und dazu {{STYLE_SPACE_8}} und {{STYLE_SPACE_12}} in
    bar-style.template, also die ABSTANDSleiter, benutzt als Radius.
    Das funktionierte, weil die Zahlen zufaellig passten.

    Diese Pruefung faengt auch, was aus einem anderen Zweig kommt: wer
    eine Oberflaeche mit einem eigenen Radius-Platzhalter hinzufuegt -
    einer Sperrmaske zum Beispiel -, bekommt hier die Aufforderung, ihn
    auf die Leiter zu ziehen, statt dass daneben eine sechste Ecke
    entsteht.
    """
    allowed = {f"{sizes.RADIUS_PREFIX}{role}" for role, _ in sizes.RADIUS_ROLES}
    allowed.add(f"{sizes.RADIUS_PREFIX}FULL")
    allowed.add(f"{sizes.RADIUS_PREFIX}PILL")

    offenders = {}
    for path in STYLESHEETS:
        found = []
        for line in _without_comments(
                path.read_text(encoding="utf-8")).splitlines():
            match = RADIUS_RULE.match(line)
            if not match:
                continue
            for name in re.findall(r"\{\{(\w+)\}\}", match.group("value")):
                if name not in allowed:
                    found.append(name)
        if found:
            offenders[path.name] = found

    assert offenders == {}, (
        "diese Ecken kommen aus einem Platzhalter neben der Leiter: "
        + "; ".join(f"{name}: {values}" for name, values in offenders.items()))


def test_the_radius_detector_finds_a_corner_that_is_planted_for_it():
    """Ein Waechter, den niemand hat arbeiten sehen, ist kein Waechter.

    WARUM DIESER TEST EXISTIERT
        Am 12.08.2026 war RADIUS_RULE als [^;{}]+ geschrieben - ohne
        geschweifte Klammern. Damit konnte
        test_no_corner_comes_from_a_placeholder_beside_the_ladder per
        Konstruktion nichts finden: sein einziger Gegenstand sind Werte
        der Form {{STYLE_...}}, und genau die schloss das Muster aus.

        Der Sperrbildschirm brachte STYLE_LOCK_FIELD_RADIUS mit - einen
        sechsten Radiusnamen neben der Leiter -, und der Waechter
        schwieg. Gefunden wurde es beim Zusammenfuehren, von Hand.

        Und selbst nach der Reparatur bleibt eine Luecke: solange der
        Baum sauber ist, findet der Waechter nichts, egal ob sein Muster
        taugt. Das Zuruecksetzen auf die blinde Fassung liess in der
        Mutationspruefung ALLE Tests gruen.

        Deshalb misst dieser Test nicht den Baum, sondern den DETEKTOR:
        er legt ihm eine Ecke hin, die er finden MUSS.
    """
    from types import SimpleNamespace

    gepflanzt = ".x {\n    border-radius: {{STYLE_EIN_FREMDER_RADIUS}};\n}\n"
    gefunden = []
    for line in _without_comments(gepflanzt).splitlines():
        match = RADIUS_RULE.match(line)
        if match:
            gefunden += re.findall(r"\{\{(\w+)\}\}", match.group("value"))

    assert gefunden == ["STYLE_EIN_FREMDER_RADIUS"], (
        f"RADIUS_RULE sieht keinen Radius aus einem Platzhalter - der "
        f"Waechter daneben kann damit nichts finden, egal wie der Baum "
        f"aussieht. Gefunden: {gefunden}")

    # Und die Gegenrichtung: ein Literal muss er weiterhin sehen.
    literal = "    border-radius: 7px;"
    assert RADIUS_RULE.match(literal), "RADIUS_RULE sieht kein Literal mehr"


def test_every_radius_rung_stands_on_the_one_ratio():
    """Dieselbe Frage wie bei der Schrift, fuer die Ecken.

    Und dieselben zwei Haelften: die Formel oben, damit eine von Hand
    danebengeschriebene Zahl auffaellt, und die drei Werte hier, damit
    ein anderes Verhaeltnis auffaellt.
    """
    assert sizes.RADIUS_RATIO == 1.6
    assert sizes.RADIUS_ANCHOR == 8
    assert {role: sizes.radius_px(step) for role, step in sizes.RADIUS_ROLES} \
        == {"CONTROL": 5, "CARD": 8, "PANEL": 13}

    for role, step in sizes.RADIUS_ROLES:
        base = sizes.TABLE[f"{sizes.RADIUS_PREFIX}{role}"].base
        assert base == sizes.radius_px(step)


def test_the_window_rounding_comes_off_the_radius_ladder():
    """Ein Fenster ist eine PLATTE - dieselbe Sprosse wie die Leiste.

    Hier stand eine 8 als Literal, mit dem Kommentar, sie sei "Sprosse 8"
    der ABSTANDsleiter - eine Ecke, die sich als Abstand ausgab, weil es
    fuer Ecken nichts gab. Faellt diese Zeile, ist die Fensterecke wieder
    eine Zahl neben der Leiter, und ein Fenster und eine Platte kommen
    sichtbar aus zwei Baukaesten.

    UND DIE SPROSSE IST SEIT DEM 17.08.2026 PANEL UND NICHT MEHR CARD.
        GEMELDET: "die fenster die erscheinen wie terminal mit dem
        hyprland header sind nicht so rund wie unsere waybar". GEMESSEN
        am selben Tag: Leiste, Dock, alle zwoelf Aufklappfenster, die
        Einblendungen, das Startmenue und der Starter standen auf PANEL
        (20 px), die Fenster auf CARD (12). Die Begruendung fuer die
        Rolle steht in src/sizes.py bei STYLE_WINDOW_ROUNDING.
    """
    assert sizes.TABLE["STYLE_WINDOW_ROUNDING"].base == sizes.radius_px(1)
    # Und ohne Einheit: `rounding = 8px` ist ein Konfigurationsfehler in
    # der Datei, deren Scheitern den Nutzer die Sitzung kostet.
    assert sizes.TABLE["STYLE_WINDOW_ROUNDING"].unit == sizes.BARE

    # UND AM QUELLTEXT, weil die Zeile darueber allein nicht reicht.
    #
    # NACHGEWIESEN mit genau dieser Mutation am 12.08.2026: `Size(8,
    # BARE, SCALED)` statt `Size(radius_px(0), ...)` lief glatt durch -
    # die 8 und radius_px(0) sind heute dieselbe Zahl, also sagt ein
    # Vergleich der WERTE nichts darueber, ob der eine aus dem anderen
    # kommt. Er wuerde es erst sagen, wenn jemand RADIUS_ANCHOR
    # verschiebt, und dann waere die Fensterecke schon abgekoppelt.
    #
    # Am Code ohne Kommentare, weil der Kommentar daneben die alte 8
    # erklaert und eine Textsuche davon wahr wuerde.
    code = test_sizes._python_code_only(SRC / "sizes.py")
    assert '"STYLE_WINDOW_ROUNDING": Size(radius_px(1)' in code, (
        "die Fensterecke traegt wieder eine Zahl statt der Sprosse - "
        "heute zufaellig dieselbe, morgen nicht mehr")


def test_the_glass_panels_have_the_corner_the_blur_was_computed_for():
    """brand.glass_ignore_alpha() rechnet seit dem 11.08.2026 MIT runden
    Ecken.

    Sein Kommentar: "Die antialiasten Pixel einer runden Ecke steigen von
    0 auf GLASS_PANEL_ALPHA; die Schwelle halbiert diese Rampe, damit die
    Unschaerfe INNERHALB der Ecke endet statt sie eckig abzuschneiden."
    Die Rechnung stand da, und die Ecken, fuer die sie gilt, gab es
    nicht: elf `*-container` und `.overlay-outer` trugen
    `border-radius: 0`.

    Geprueft wird an `.overlay-outer`, weil das die aeusserste Flaeche
    JEDES Ueberlagerungsfensters ist - die eine, hinter der die
    Unschaerfe sitzt.
    """
    code = _without_comments(
        (SRC / "templates" / "ags-style.template").read_text(encoding="utf-8"))

    # Bis zu einer schliessenden Klammer am ZEILENANFANG, und nicht bis
    # zur naechsten ueberhaupt: ein {{PLATZHALTER}} traegt selbst zwei,
    # und ein nicht-gieriges .*? endet dann mitten in der ersten Regel -
    # womit diese Pruefung genau das nicht mehr sehen wuerde, wofuer es
    # sie gibt.
    block = re.search(r"^\.overlay-outer\s*\{\n(.*?)^\}", code,
                      re.DOTALL | re.MULTILINE)
    assert block, "es gibt keine Regel fuer .overlay-outer mehr"
    assert "{{" + sizes.RADIUS_PREFIX + "PANEL}}" in block.group(1), (
        "die aeusserste Flaeche der Ueberlagerungen ist wieder eckig - "
        "und die Unschaerfe darunter ist fuer eine runde gerechnet")

    assert sizes.radius_px(1) > 0


# --------------------------------------------------------------------
# Die Grenzen
# --------------------------------------------------------------------

MEASURE_LITERAL = re.compile(
    r"(?:max_width_chars\s*[:=]\s*|set_max_width_chars\s*\(\s*"
    r"|preview_chars\s*=\s*|description_chars\s*=\s*)(\d+)")


def test_no_line_length_is_a_literal():
    """Fuenf Stellen, drei Zahlen, keine begruendet.

    `set_max_width_chars(60)` in der Leiste, zweimal
    `max_width_chars: 40` in den Benachrichtigungen, `preview_chars = 60`
    in der Zwischenablage und ein hartes 60 im C++ des Starters. Die
    Zeilenlaenge ist keine Geschmacksfrage - sie ist die eine
    typografische Groesse, zu der es eine Zahl aus der Literatur gibt -,
    und sie stand fuenfmal als Zufall da.
    """
    offenders = {}
    for path in TEMPLATES:
        found = MEASURE_LITERAL.findall(
            _without_comments(path.read_text(encoding="utf-8")))
        if found:
            offenders[path.name] = found

    assert offenders == {}, (
        "diese Zeilenlaengen stehen als Zahl in der Vorlage statt auf "
        "{{" + sizes.MEASURE_PREFIX + "LINE}} oder {{"
        + sizes.MEASURE_PREFIX + "PROSE}}: "
        + "; ".join(f"{name}: {values}" for name, values in offenders.items()))


def test_the_measure_is_inside_the_band_the_source_names():
    """Robert Bringhurst, "The Elements of Typographic Style", 3. Auflage,
    Abschnitt 2.1.2:

        "Anything from 45 to 75 characters is widely regarded as a
        satisfactory length of line for a single-column page ... 66
        characters (counting both letters and spaces) is widely regarded
        as ideal."

    Also nicht "sieht gut aus", sondern zwei Zahlen aus einer Quelle, die
    man nachschlagen kann. Diese Pruefung faellt, sobald jemand sie
    verschiebt, ohne eine andere Quelle zu nennen.
    """
    assert sizes.MEASURE_LINE == 45
    assert sizes.MEASURE_PROSE == 66
    for value in (sizes.MEASURE_LINE, sizes.MEASURE_PROSE):
        assert 45 <= value <= 75


def test_a_limit_in_characters_does_not_follow_the_factor():
    """Und das ist der Grund, aus dem sie in Zeichen steht.

    Waechst die Schrift auf das 1.85-fache, waechst die Spalte von
    selbst mit, und die Zeile bleibt 66 Zeichen lang. Multiplizierte man
    die Zahl mit, waere die Grenze bei jedem Faktor eine andere Zahl von
    Zeichen - also eine Lesbarkeitsgrenze, die sich beim Drehen am
    Regler verschiebt.

    Ausgeschrieben und nicht aus der Tabelle gefiltert: `[n for n, s in
    TABLE.items() if not s.scales]` waere eine Tautologie, die genau dann
    nichts mehr prueft, wenn jemand der Grenze ein SCALED gibt.
    """
    for name in (f"{sizes.MEASURE_PREFIX}LINE", f"{sizes.MEASURE_PREFIX}PROSE"):
        assert not sizes.TABLE[name].scales, f"{name} folgt dem Faktor"
        assert sizes.TABLE[name].unit == sizes.BARE, (
            f"{name} bekommt ein px angehaengt und ist eine ANZAHL")
        for scale in (1.0, sizes.SCALE_DEFAULT, 4.0):
            assert sizes.value_of(name, {"scale": scale}) == str(
                sizes.TABLE[name].base)


def test_the_launcher_reads_its_line_length_from_the_configuration():
    """Die fuenfte Stelle lag im uebersetzten Objekt.

    `gtk_label_set_max_width_chars(GTK_LABEL(desc), 60)` im Renderer -
    also dort, wo kein Regler und keine Vorlage sie je erreicht haetten.
    Dieselbe Geschichte wie die sieben `static constexpr`, die am
    11.08.2026 aus den beiden Plugins herausgeholt wurden.
    """
    header = (ROOT / "plugins" / "hyprlaunch" / "include" / "hyprlaunch"
              / "Config.hpp").read_text(encoding="utf-8")
    parser = (ROOT / "plugins" / "hyprlaunch" / "src"
              / "ConfigParser.cpp").read_text(encoding="utf-8")
    renderer = (ROOT / "plugins" / "hyprlaunch" / "src"
                / "LauncherRenderer.cpp").read_text(encoding="utf-8")
    template = (SRC / "templates"
                / "hyprlaunch-config.template").read_text(encoding="utf-8")

    assert "int descriptionChars" in header
    assert '"description_chars"' in parser
    assert "m_config.descriptionChars" in renderer
    assert ("description_chars = {{" + sizes.MEASURE_PREFIX + "PROSE}}"
            in template)


# --------------------------------------------------------------------
# Die Bewegung
# --------------------------------------------------------------------

def test_the_motion_ladder_is_one_ratio_between_the_two_known_limits():
    """Jakob Nielsen, "Response Times: The 3 Important Limits" (1993, nach
    Miller 1968): 0.1 s ist die Grenze, unter der etwas unmittelbar
    wirkt, 1.0 s die, bis zu der der Gedankenfluss nicht abreisst.

    Zwischen diesen beiden liegt der ganze Raum, in dem eine Bewegung
    einer Oberflaeche stattfinden darf. Drei Stufen im Verhaeltnis zwei
    passen genau hinein, und der Anker ist die 300 ms, die dieser Baum
    als einzige Dauer je fuer seine Oberflaeche aufgeschrieben hatte
    ("all 0.3s ease").

    Verhaeltnis ZWEI und nicht 1.2 wie bei der Schrift: zwei Bewegungen,
    die sich um zwanzig Prozent unterscheiden, sehen gleich lang aus.
    """
    assert sizes.MOTION_RATIO == 2
    assert sizes.MOTION_ANCHOR_MS == 300
    assert {role: sizes.motion_ms(step) for role, step in sizes.MOTION_ROLES} \
        == {"INSTANT": 150, "BASE": 300, "ENTER": 600}

    for _role, step in sizes.MOTION_ROLES:
        assert 100 <= sizes.motion_ms(step) <= 1000, (
            f"{sizes.motion_ms(step)} ms liegt ausserhalb der beiden "
            f"Grenzen, zwischen denen eine Bewegung wahrgenommen wird")


def test_a_duration_does_not_follow_the_size_factor():
    """Wer die Schrift verdoppelt, will groesser lesen und nicht laenger
    warten.

    Bei 1.85 waeren aus ENTER 1110 ms geworden - ueber der Grenze, ab der
    der Gedankenfluss abreisst, und das fuer jedes Fenster, das aufgeht.

    Ausgeschrieben und nicht aus der Tabelle gefiltert, aus demselben
    Grund wie bei den Grenzen: aus TABLE gefiltert waere es eine
    Tautologie, die genau dann nichts mehr prueft, wenn jemand einer
    Dauer ein SCALED gibt.
    """
    for role, step in sizes.MOTION_ROLES:
        name = f"{sizes.MOTION_PREFIX}{role}"
        assert not sizes.TABLE[name].scales, f"{name} folgt dem Faktor"
        assert sizes.TABLE[name].unit == sizes.MS
        for scale in (1.0, sizes.SCALE_DEFAULT, 4.0):
            assert sizes.value_of(name, {"scale": scale}) == (
                f"{sizes.motion_ms(step)}ms")


def test_the_compositor_and_the_stylesheet_move_on_the_same_curve():
    """Vier Geschwindigkeiten im Compositor, eine Dauer im Stylesheet.

    GEMESSEN am 12.08.2026 in hyprland-universal-config.template:
    `bezier = myBezier, 0.05, 0.9, 0.1, 1.05` und die Geschwindigkeiten
    7, 7, 10, 7, 6 - wobei DREI der fuenf Zeilen die eigene Kurve gar
    nicht benutzten, sondern `default`. Daneben ein Stylesheet mit
    "all 0.3s ease". Zwei Systeme, zwei Kurven, fuenf Dauern.

    Die Kurve ist die des Compositors, weil sie die einzige war, die je
    aufgeschrieben wurde. Eine zweite zu erfinden hiesse, das Problem zu
    verdoppeln, das gerade behoben wird.
    """
    assert sizes.MOTION_CURVE_POINTS == (0.05, 0.9, 0.1, 1.05)
    assert sizes.motion_curve_css() == "cubic-bezier(0.05, 0.9, 0.1, 1.05)"
    assert sizes.motion_curve_hyprland() == "zepos, 0.05, 0.9, 0.1, 1.05"

    hyprland = (SRC / "templates"
                / "hyprland-universal-config.template").read_text("utf-8")
    code = "\n".join(line for line in hyprland.splitlines()
                     if not line.lstrip().startswith("#"))

    animations = [line.strip() for line in code.splitlines()
                  if line.strip().startswith("animation =")]
    assert animations, "der Compositor animiert nichts mehr"
    for line in animations:
        assert "{{" + sizes.MOTION_PREFIX + "CURVE_NAME}}" in line, (
            f"diese Zeile bewegt sich auf einer anderen Kurve: {line}")
        speeds = [f"{{{{{sizes.MOTION_PREFIX}{role}_HYPR}}}}"
                  for role, _ in sizes.MOTION_ROLES]
        assert any(speed in line for speed in speeds), (
            f"diese Zeile traegt eine Dauer neben der Leiter: {line}")


def test_hyprland_reads_the_duration_the_user_set():
    """Nicht den Grundwert, sondern den eingestellten.

    Ohne das waere der Regler auf der einen Seite verdrahtet und auf der
    anderen nicht - und das faellt erst auf, wenn ein Fenster schneller
    aufgeht, als die Kachel darin hell wird.
    """
    assert sizes.motion_hyprland_speed("ENTER", {}) == "6"
    assert sizes.motion_hyprland_speed("BASE", {}) == "3"
    assert sizes.motion_hyprland_speed(
        "ENTER", {"values": {"STYLE_MOTION_ENTER": "900ms"}}) == "9"
    # Und nie eine 0: die heisst fuer Hyprland "sofort" und wirft die
    # Kurve weg, statt sie schnell zu spielen.
    assert sizes.motion_hyprland_speed(
        "INSTANT", {"values": {"STYLE_MOTION_INSTANT": "10ms"}}) == "1"


def test_motion_can_be_switched_off_on_both_halves(tmp_path, monkeypatch):
    """Bewegung, die man nicht abstellen kann, ist ein
    Zugaenglichkeitsproblem.

    Fuer Menschen mit vestibulaerer Stoerung loesen bewegte Flaechen
    Schwindel aus. Bis zum 12.08.2026 gab es auf diesem System keinen
    Weg dazu: Hyprland stand auf `enabled = yes` als Literal, und fuer
    die fremden GTK4-Fenster gab es ueberhaupt keine Datei.

    Geprueft an BEIDEN Haelften, weil ein Schalter, der nur die eine
    anhaelt, schlimmer ist als keiner - der Nutzer haette dann eine
    unbewegte Leiste vor sich bewegenden Fenstern.
    """
    assert sizes.motion_enabled({}) is True
    assert sizes.motion_enabled({sizes.MOTION_ENABLED: False}) is False
    assert sizes.motion_curve_hyprland_toggle({}) == "yes"
    assert sizes.motion_gtk_toggle({sizes.MOTION_ENABLED: False}) == "0"

    test_sizes._no_compositor(monkeypatch)
    still = test_sizes._import_style(
        tmp_path, monkeypatch,
        {"sizes": {sizes.MOTION_ENABLED: False}})
    assert still.STYLE_VARIABLES[
        f"{sizes.MOTION_PREFIX}ENABLED_HYPR"] == "no"
    assert still.STYLE_VARIABLES[
        f"{sizes.MOTION_PREFIX}ENABLED_GTK"] == "0"


def test_switching_motion_off_changes_the_generated_files(processor, tmp_path,
                                                          monkeypatch):
    """Und es kommt in den Dateien an.

    Derselbe Massstab wie fuer jede Groesse in sizes.TABLE: ein
    Schalter, der kein erzeugtes Byte bewegt, ist der Regler, den dieses
    Projekt schon dreimal geloescht hat. Der Schalter steht NICHT in der
    Tabelle - er ist keine Groesse -, also braucht er diese Pruefung
    eigens.
    """
    templates = [SRC / "templates" / "hyprland-universal-config.template",
                 SRC / "templates" / "gtk4-settings-config.template"]

    test_sizes._no_compositor(monkeypatch)
    moving = test_sizes._import_style(tmp_path / "an", monkeypatch)
    test_sizes._no_compositor(monkeypatch)
    still = test_sizes._import_style(
        tmp_path / "aus", monkeypatch,
        {"sizes": {sizes.MOTION_ENABLED: False}})

    # JEDE Datei einzeln, und nicht die beiden zusammen.
    #
    # NACHGEWIESEN mit der Mutation `enabled = yes` in
    # hyprland-universal-config.template am 12.08.2026: gegen die
    # zusammengehaengte Ausgabe lief sie glatt durch, weil die
    # GTK-Datei daneben sich weiter bewegte. Ein Schalter, der EINE
    # der beiden Haelften anhaelt, ist schlimmer als keiner - der
    # Nutzer haette dann eine unbewegte Leiste vor sich bewegenden
    # Fenstern.
    for template in templates:
        assert (test_sizes._render(processor, moving, [template],
                                   tmp_path / f"an-{template.stem}")
                != test_sizes._render(processor, still, [template],
                                      tmp_path / f"aus-{template.stem}")), (
            f"{template.name} sieht gleich aus, ob Bewegung an ist oder "
            f"aus")


def test_the_six_dead_animation_placeholders_do_not_come_back(tmp_path,
                                                              monkeypatch):
    """STYLE_ANIMATION_PULSE_SYNC, _CHECK, _ERROR, _DELETE,
    STYLE_ANIMATION_BLINK und _SUCCESS_FLASH.

    GEMESSEN am 12.08.2026: zusammen NULL Leser, und dazu vier Dauern
    (1 s, 1.5 s, 2 s) und zwei Kurven (linear, ease-out) neben der
    Leiter. Dieselbe Geschichte wie die 29 Farben und die sechs
    Radius-Platzhalter, nur mit Animationen.
    """
    test_sizes._no_compositor(monkeypatch)
    style = test_sizes._import_style(tmp_path, monkeypatch)

    dead = sorted(name for name in dict(style.STYLE_VARIABLES)
                  if name.startswith("STYLE_ANIMATION")
                  or name == "STYLE_TRANSITION_DEFAULT")
    assert dead == [], (
        "tote Bewegungs-Platzhalter sind zurueck: " + ", ".join(dead))


def test_no_transition_in_a_stylesheet_carries_its_own_duration():
    """Eine Regel, die ihre eigene Dauer schreibt, ist die naechste 0.3s.

    Und `all` ist ebenfalls verboten: eine Regel, die JEDE Eigenschaft
    uebergehen laesst, animiert auch die, an die niemand gedacht hat -
    eine Breite, die sich beim Fuellen einer Liste aendert, laeuft dann
    sichtbar auseinander.
    """
    offenders = {}
    for path in STYLESHEETS:
        found = []
        for line in _without_comments(
                path.read_text(encoding="utf-8")).splitlines():
            match = re.match(r"\s*transition\s*:\s*(?P<value>[^;]+);", line)
            if not match:
                continue
            value = match.group("value")
            if re.search(r"\d+\s*(ms|s)\b", value) or value.strip().startswith(
                    "all "):
                found.append(value.strip())
        if found:
            offenders[path.name] = found

    assert offenders == {}, (
        "diese Uebergaenge tragen ihre eigene Dauer oder animieren `all`: "
        + "; ".join(f"{name}: {values}" for name, values in offenders.items()))


# --------------------------------------------------------------------
# Die fremden GTK4-Fenster
# --------------------------------------------------------------------

def test_a_foreign_gtk4_window_gets_the_size_of_this_desktop():
    """Die Luecke, die "global" schliessen musste.

    gtk4-colors-config.template gibt nautilus, loupe, papers, celluloid,
    gnome-text-editor und baobab seit langem die 45 Farben der Marke.
    Eine GROESSE bekamen sie nie - GEMESSEN am 12.08.2026: kein einziger
    Treffer fuer `gtk-font-name` im ganzen Baum. Bei sizes.scale 1.85
    trug jedes eigene Fenster 24 px Schrift und der Dateimanager daneben
    rund 15.

    Die Punktzahl wird nachgerechnet und nicht geglaubt: die
    ausgelieferte Grundschrift sind bei 96 dpi genau
    DEFAULT_PX * 72/96 Punkt, und das ist zugleich die Zahl, auf die das
    Terminal faellt - die drei Einheiten dieses Systems treffen sich
    hier. Seit dem 12.08.2026 sind es 20 px und damit 15 pt; davor 24
    und 18.
    """
    assert sizes.gtk_font_points({}) == round(sizes.DEFAULT_PX * 72 / 96)
    assert sizes.value_of(f"{sizes.FONT_PREFIX}BODY", {}) == f"{sizes.DEFAULT_PX}px"
    assert int(sizes.value_of("STYLE_TERMINAL_FONT_SIZE", {})) == round(
        sizes.DEFAULT_PX * 72 / 96)

    template = (SRC / "templates"
                / "gtk4-settings-config.template").read_text("utf-8")
    code = "\n".join(line for line in template.splitlines()
                     if not line.lstrip().startswith("#"))
    assert "gtk-font-name = {{STYLE_GTK_FONT_NAME}}" in code
    assert ("gtk-enable-animations = {{" + sizes.MOTION_PREFIX
            + "ENABLED_GTK}}") in code


def test_the_generator_writes_the_gtk4_settings_where_gtk_looks():
    """Der Pfad ist GTKs eigener und nicht verhandelbar.

    Eine Vorlage ohne Eintrag in generate_config.sh faellt in den
    Sammelzweig und landet als ~/.config/<name>/config - eine Datei, die
    niemand liest, jeden Lauf neu erzeugt. Das ist tty-text-fix-config
    schon einmal passiert.
    """
    script = (SRC / "generate_config.sh").read_text(encoding="utf-8")
    assert "gtk4-settings-config)" in script
    assert 'CONFIG_FILE="settings.ini"' in script

    # Und bei jeder Anmeldung, wie die Farben daneben: GTK liest die
    # Datei EINMAL, beim Start jeder Anwendung.
    session = (SRC / "templates"
               / "start-hyprland-config.template").read_text("utf-8")
    assert "./generate_config.sh -gtk4-settings-config" in session
