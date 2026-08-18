# SPDX-License-Identifier: GPL-3.0-or-later
"""Jede Groesse, die man einstellen kann, muss ein Byte bewegen.

DIE FALLE, DIE DIESE DATEI ZUHAELT
    Es gab schon einmal eine zweite Skalentabelle in diesem Projekt -
    MONITOR_HEIGHT_SCALES, mit vier Vorgabewerten, einer Migration und
    einem Befehlszeilenschalter. Sie veraenderte KEIN EINZIGES erzeugtes
    Byte. Niemand merkte es, weil eine Einstellung, die nichts tut, in
    der Datei, im Stil-Editor und in `zepos-settings get` genauso
    aussieht wie eine, die etwas tut. Sie wurde deshalb geloescht; die
    Begruendung steht in user_settings.RETIRED_SCALING_DIMENSION.

    Dieselbe Geschichte ein zweites Mal, kleiner: user_settings.py trug
    "fonts": {"base_size": 13, "icon_size": 18} und "spacing":
    {"module": 10, "bar_height": 50}. Vier Zahlen, die genau den vier
    Werten entsprachen, die style_definition.py als Literale
    ausschrieb - und keine davon wurde gelesen. Jedes Speichern schrieb
    sie zurueck in die Datei des Nutzers.

    Also wird hier nicht geprueft, dass es die Einstellung GIBT, sondern
    dass ihre Aenderung in einer erzeugten Datei ankommt. Und zwar fuer
    JEDE einzelne, aufgezaehlt aus der Tabelle statt von Hand - eine
    Liste von Hand haette genau die neue Groesse nicht drin, die jemand
    hinzufuegt, ohne sie zu verdrahten.
"""
import ast
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from src import sizes

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
TEMPLATE_DIRS = (SRC / "templates", SRC / "styles")

# Das Stylesheet der AGS-Ueberlagerungen. Es trug 164 font-size-Literale
# und benutzte keinen einzigen der vierundachtzig Platzhalter, die
# genau dafuer da waren.
AGS_STYLE = SRC / "templates" / "ags-style.template"

# Die Leiste. Ihre Hoehe stand als nackte 50 in der Vorlage, waehrend
# STYLE_BAR_THICKNESS daneben als "50px" definiert war und von niemandem
# gelesen wurde.
BAR_SOURCE = SRC / "templates" / "ags-bar.template"


def _python_code_only(path):
    """Python-Quelltext ohne Kommentare und ohne Docstrings.

    `"NAME" in datei` ist auch dann wahr, wenn NAME nur im Kommentarkopf
    steht - und genauso, wenn es in einem Docstring steht. Genau daran
    fiel die erste Fassung dieser Pruefung um: sie strich nur Zeilen,
    die mit # anfangen, und stolperte dann ueber einen Satz in einem
    Docstring, der eine Sprosse nannte, die es nicht mehr gibt.

    Ein Docstring ist keine Zeile, die mit etwas anfaengt, also kann
    zeilenweise Textarbeit ihn nicht finden. ast sieht dieselbe
    Struktur wie der Uebersetzer.

    Die UEBRIGEN Zeichenketten bleiben stehen, und das ist der
    Unterschied, der zaehlt: die Namen, um die es hier geht, SIND
    Zeichenketten - Schluessel in DEFAULT_SETTINGS. Sie mit
    wegzuwerfen hiesse, eine Pruefung zu bauen, die nichts mehr finden
    kann und deshalb immer durchgeht.
    """
    source = path.read_text(encoding="utf-8")
    prose = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if ast.get_docstring(node, clean=False) is None:
            continue
        literal = node.body[0]
        prose.update(range(literal.lineno, literal.end_lineno + 1))

    lines = []
    for number, line in enumerate(source.splitlines(), start=1):
        if number in prose:
            continue
        lines.append(re.sub(r"(?<!['\"])#.*$", "", line))
    return "\n".join(lines)


def _no_compositor(monkeypatch):
    """Nichts angeschlossen, damit die Werte allein an den Einstellungen
    haengen."""
    def missing(cmd, **kwargs):
        raise FileNotFoundError("hyprctl")

    monkeypatch.setattr(subprocess, "run", missing)


def _import_style(tmp_path, monkeypatch, document=None):
    """Die Stil-SSOT ueber einer Einstellungsdatei, die dieser Test schreibt.

    Dieselbe Form wie in test_style_definition.py: das Modul liest die
    Datei beim IMPORT, also gibt es keinen anderen Weg, ihm andere
    Einstellungen zu geben, als es neu zu importieren.
    """
    monkeypatch.delenv("ZEPOS_SYSTEM_ROOT", raising=False)
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.syspath_prepend(str(SRC))

    if document is not None:
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "user-settings.json").write_text(
            json.dumps({"schema_version": 1, **document}), encoding="utf-8")

    spec = importlib.util.spec_from_file_location(
        f"zepos_style_probe_{tmp_path.name}", SRC / "style_definition.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _uncommented(text: str, marker: str = "#") -> list[str]:
    """Die Zeilen ohne die, die nur Kommentar sind.

    Wortgleich zu tests/src/test_gtk4_only.py und aus demselben Grund:
    jede Datei in diesem Baum ERKLAERT, was sie nicht mehr tut, und eine
    Pruefung der Form `"50" in text` wird von der Erklaerung wahr, in der
    steht, dass die 50 verschwunden ist.
    """
    return [line.strip() for line in text.splitlines()
            if not line.lstrip().startswith(marker)]


def _templates_naming(placeholder):
    """Jede Vorlage, die diesen Platzhalter wirklich nennt."""
    needle = "{{" + placeholder + "}}"
    return [path
            for directory in TEMPLATE_DIRS
            for path in sorted(directory.glob("*.template"))
            if needle in path.read_text(encoding="utf-8")]


def _render(processor, style, templates, out):
    """Die genannten Vorlagen erzeugen und als ein Text zurueckgeben.

    Erzeugt wird mit dem ECHTEN ConfigProcessor, nicht mit einem
    str.replace() dieses Tests. Sonst misst der Test seine eigene
    Ersetzung und nicht die, die auf der Maschine des Nutzers laeuft.
    """
    out.mkdir(parents=True, exist_ok=True)
    rendered = []
    for template in templates:
        target = out / template.stem
        processor.ConfigProcessor(
            styles=dict(style.STYLE_VARIABLES)).apply_template(template, target)
        rendered.append(target.read_text(encoding="utf-8"))
    return "\n".join(rendered)


@pytest.fixture
def processor(monkeypatch):
    """Der Prozessor, so importiert, wie der Generator ihn importiert."""
    monkeypatch.syspath_prepend(str(SRC))
    import template_processor

    return template_processor


# --------------------------------------------------------------------
# die Tabelle und die Vorlagen
# --------------------------------------------------------------------

def test_every_settable_size_is_named_by_a_template():
    """Der strukturelle Riegel: kein Regler ohne Leser.

    Das ist die billige Haelfte der Pruefung - sie braucht keine
    Erzeugung und faellt sofort um, wenn jemand einen Namen in die
    Tabelle schreibt, den keine Vorlage nennt. Die teure Haelfte steht
    darunter und prueft, dass der Platzhalter auch wirklich anders
    herauskommt.
    """
    unread = [name for name in sorted(sizes.TABLE)
              if not _templates_naming(name)]

    assert unread == [], (
        "diese Groessen sind einstellbar und werden von keiner Vorlage "
        "gelesen - genau der Zustand, in dem MONITOR_HEIGHT_SCALES war: "
        + ", ".join(unread))


@pytest.mark.parametrize("name", sorted(sizes.TABLE))
def test_changing_one_size_changes_a_generated_file(name, processor, tmp_path,
                                                    monkeypatch):
    """Fuer JEDE Groesse einzeln: der Wert steht danach anders in der Datei.

    Aufgezaehlt aus sizes.TABLE und nicht aus einer Liste von Hand.
    Eine Liste von Hand haette genau den Eintrag nicht, den jemand
    hinzufuegt, ohne ihn zu verdrahten - also genau den Fall, den dieser
    Test fangen soll.

    Verglichen wird gegen einen Sentinel, der in keinem Grundwert
    vorkommen kann, damit "unveraendert" nicht zufaellig gleich aussieht.
    """
    templates = _templates_naming(name)
    assert templates, f"{name} wird von keiner Vorlage gelesen"

    _no_compositor(monkeypatch)
    plain = _import_style(tmp_path / "plain", monkeypatch)
    before = _render(processor, plain, templates, tmp_path / "out-plain")

    _no_compositor(monkeypatch)
    sentinel = "1234"
    changed = _import_style(
        tmp_path / "changed", monkeypatch,
        {"sizes": {"values": {name: sentinel}}})
    after = _render(processor, changed, templates, tmp_path / "out-changed")

    # Der Platzhalter selbst, und nicht irgendein Wert in derselben
    # Datei. Ohne diese Zeile genuegte es, dass IRGENDEIN Wert sich
    # bewegt: STYLE_PADDING_MODULE wird aus STYLE_MODULE_SPACING
    # gebaut, also aenderte sich die Ausgabe auch dann noch, als
    # {{STYLE_MODULE_SPACING}} selbst wieder ein Literal war -
    # nachgewiesen mit genau dieser Mutation.
    assert changed.STYLE_VARIABLES[name] == sentinel, (
        f"{name} ist einstellbar, aber der Platzhalter traegt den "
        f"eingestellten Wert nicht")
    assert after != before, (
        f"{name} laesst sich einstellen und veraendert keine erzeugte "
        f"Datei. Vorlagen, die ihn nennen: "
        + ", ".join(t.name for t in templates))
    assert sentinel in after, (
        f"{name} wurde gesetzt, aber der Wert steht nicht in der Ausgabe")


def test_the_size_factor_changes_what_is_generated(processor, tmp_path,
                                                   monkeypatch):
    """Der eine Regler, an der ganzen Leiter gemessen.

    Nicht an einem Platzhalter, sondern an jeder Vorlage, die irgendeine
    skalierende Groesse nennt: ein Faktor, der nur eine davon bewegt,
    ist kein Faktor.
    """
    # AUSGESCHRIEBEN und nicht aus der Tabelle gefiltert.
    #
    # `[name for name, size in TABLE.items() if size.scales]` sieht
    # gruendlicher aus und ist eine Tautologie: nimmt man einer Groesse
    # das SCALED weg, faellt sie aus der Liste und der Test prueft sie
    # nicht mehr. NACHGEWIESEN - die Mutation "STYLE_FONT_BODY folgt dem
    # Faktor nicht mehr" lief so glatt durch.
    #
    # Diese vier sind die Schrift, die man auf dem Schirm sieht: die
    # Leiste, ihre Hoehe, die kleine Schrift daneben und die Leiter der
    # Ueberlagerungen. Waechst eine davon nicht mit, ist der Regler
    # kaputt, ganz gleich was in der Tabelle steht.
    scaling = [
        "STYLE_FONT_BODY",
        "STYLE_FONT_CAPTION",
        "STYLE_ICON_BODY",
        "STYLE_RADIUS_PANEL",
        "STYLE_BAR_THICKNESS",
        "STYLE_MODULE_SPACING",
    ]
    assert all(sizes.TABLE[name].scales for name in scaling)

    templates = sorted({path
                        for name in scaling
                        for path in _templates_naming(name)})
    assert templates

    _no_compositor(monkeypatch)
    small = _import_style(tmp_path / "small", monkeypatch,
                          {"sizes": {"scale": 1.0}})
    _no_compositor(monkeypatch)
    large = _import_style(tmp_path / "large", monkeypatch,
                          {"sizes": {"scale": 2.0}})

    for name in scaling:
        assert small.STYLE_VARIABLES[name] != large.STYLE_VARIABLES[name], (
            f"{name} sagt, es folge dem Faktor, und tut es nicht")

    assert (_render(processor, small, templates, tmp_path / "out-small")
            != _render(processor, large, templates, tmp_path / "out-large"))


def test_a_picture_does_not_follow_the_factor(tmp_path, monkeypatch):
    """Die Gegenprobe zur Grenze, die sizes.SCALED/FIXED zieht.

    Ohne sie waere "folgt dem Faktor" eine Behauptung, die die Tabelle
    ueber sich selbst aufstellt und niemand nachrechnet.

    STYLE_DOCK_ICON_SIZE stand hier bis zum 12.08.2026 und steht nicht
    mehr: es ist seither ABGELEITET und folgt der Dicke des Streifens,
    weil der Nutzer verlangt hat, dass Kopf und Fuss gleich hoch sind
    (siehe sizes.DERIVED). Die Grenze selbst gilt weiter - nachgemessen
    wird sie jetzt an den beiden, die noch darunterfallen.
    """
    # Ausgeschrieben, aus demselben Grund wie oben: aus der Tabelle
    # gefiltert waere das eine Tautologie, die genau dann nichts mehr
    # prueft, wenn jemand einem Bild ein SCALED gibt. NACHGEWIESEN.
    fixed = ["STYLE_TRAY_ICON_SIZE", "STYLE_DOCK_PADDING",
             "STYLE_LAUNCHER_ICON_SIZE"]
    assert not any(sizes.TABLE[name].scales for name in fixed), (
        "ein Bild ist als schriftfolgend eingetragen")
    assert not any(name in sizes.DERIVED for name in fixed), (
        "eine abgeleitete Groesse kann nicht zugleich fest sein")

    _no_compositor(monkeypatch)
    small = _import_style(tmp_path / "small", monkeypatch,
                          {"sizes": {"scale": 1.0}})
    _no_compositor(monkeypatch)
    large = _import_style(tmp_path / "large", monkeypatch,
                          {"sizes": {"scale": 4.0}})

    for name in fixed:
        assert small.STYLE_VARIABLES[name] == large.STYLE_VARIABLES[name], (
            f"{name} ist ein Bild und waechst trotzdem mit der Schrift")


def test_a_size_the_user_names_beats_the_factor(tmp_path, monkeypatch):
    """sizes.values gewinnt gegen sizes.scale, und wird nicht mit ihm
    multipliziert.

    Wer eine genaue Groesse nennt, hat gesagt, was auf dem Schirm stehen
    soll. Eine anschliessende Multiplikation hiesse, dass die getippte
    Zahl dort nirgends vorkommt.
    """
    _no_compositor(monkeypatch)
    style = _import_style(tmp_path, monkeypatch, {"sizes": {
        "scale": 3.0,
        "values": {"STYLE_FONT_BODY": "20px"},
    }})

    assert style.STYLE_VARIABLES["STYLE_FONT_BODY"] == "20px"
    # Der Nachbar auf derselben Leiter folgt weiter dem Faktor, sonst
    # haette der Einzelwert die ganze Leiter angehalten. 11 * 3.
    assert style.STYLE_VARIABLES["STYLE_FONT_CAPTION"] == "33px"


# --------------------------------------------------------------------
# der Anker, und dass die Namen nicht luegen
# --------------------------------------------------------------------

def test_the_shipped_factor_is_the_size_the_bar_can_carry():
    """Der Fixpunkt der Kette, und er hat sich am 12.08.2026 verschoben.

    Bis dahin war es der Anker des Startmenues: der Schreibtisch schrieb
    in 24 px, weil `grub-mkfont -s 24` es tut. Der Nutzer hat das
    Ergebnis auf echter Hardware gesehen und widerrufen - "die fontsize
    muss vlt ein bisschen kleiner gemacht werden weil wir zu wenig
    inhalt drauf bekommen auf den header" -, und seither entscheidet
    ueber die ausgelieferte Groesse, was auf die Leiste passt.

    Beide Zahlen bleiben und heissen verschieden, weil sie verschiedene
    Dinge sind: ANCHOR_PX ist eine Messung an iso/make-boot-theme.sh,
    DEFAULT_PX eine Entscheidung ueber diesen Schreibtisch. Die
    Ableitung der 20 steht im Kopf von src/sizes.py; nachgemessen wird
    sie an der Leiste selbst, in
    test_the_bar_holds_every_module_on_the_common_screen.
    """
    assert sizes.DEFAULT_PX == 20
    assert sizes.TABLE["STYLE_FONT_BODY"].base == sizes.BASE_PX
    assert sizes.value_of("STYLE_FONT_BODY", {}) == f"{sizes.DEFAULT_PX}px"
    assert sizes.SCALE_DEFAULT == sizes.DEFAULT_PX / sizes.BASE_PX


def test_the_anchor_is_the_size_the_boot_menu_really_uses():
    """Und der Anker wird an der Quelle nachgerechnet, nicht geglaubt.

    Ohne das ist die 24 eine Zahl, die zu sich selbst passt. Sie steht
    in iso/make-boot-theme.sh als `-s 24` und in theme.txt als "Roboto
    Regular 24"; wandert eine der beiden, muss die andere mitwandern,
    sonst behauptet diese Datei etwas ueber ein Startmenue, das es so
    nicht gibt.

    Seit dem 12.08.2026 ist das ALLES, was ANCHOR_PX noch bindet - die
    ausgelieferte Groesse des Schreibtischs haengt nicht mehr daran.
    """
    assert sizes.ANCHOR_PX == 24
    script = (ROOT / "iso" / "make-boot-theme.sh").read_text(encoding="utf-8")
    code = "\n".join(line for line in script.splitlines()
                     if not line.lstrip().startswith("#"))
    assert f"-s {sizes.ANCHOR_PX} " in code, (
        "das Startmenue wird nicht mehr in der Groesse gebaut, auf die "
        "der Schreibtisch zielt")

    theme = (ROOT / "iso" / "profile-release" / "grub" / "themes" / "zepos"
             / "theme.txt").read_text(encoding="utf-8")
    assert f'item_font = "Roboto Regular {sizes.ANCHOR_PX}"' in theme


def test_the_ladder_rounds_the_same_way_at_every_rung():
    """Kaufmaennisch, nicht zur geraden Zahl.

    Pythons round() rundet auf die GERADE Zahl: 11 * 1.5 sind 16.5 und
    werden zu 16, 13 * 1.5 sind 19.5 und werden zu 20. Eine Leiter, die
    an manchen Sprossen ab- und an anderen aufrundet, ist keine mehr -
    und der Fehler faellt nur bei genau .5 an, also bei den halben
    Faktoren, die ein Nutzer als erstes ausprobiert.
    """
    section = {"scale": 1.5}
    # 11 * 1.5 = 16.5, 13 * 1.5 = 19.5, 9 * 1.5 = 13.5 - drei Sprossen,
    # die alle genau auf der halben Stelle liegen.
    assert sizes.value_of("STYLE_FONT_CAPTION", section) == "17px"
    assert sizes.value_of("STYLE_FONT_BODY", section) == "20px"
    assert sizes.value_of("STYLE_FONT_MICRO", section) == "14px"


def test_no_size_can_be_rounded_down_to_nothing():
    """Ein sehr kleiner Faktor darf keine 0 erzeugen.

    0.02 ist ein Tippfehler fuer 0.2 und liegt eine Taste daneben.
    9 * 0.02 sind 0.18 und werden zu 0 gerundet - eine Schrift der
    Groesse 0px ist eine unsichtbare Oberflaeche, und der Weg zurueck
    fuehrt durch genau diese Oberflaeche. Der Faktor selbst wird beim
    Setzen geprueft, aber nur gegen "groesser als null", und 0.02 ist
    groesser als null.
    """
    section = {"scale": 0.02}
    for name, size in sizes.TABLE.items():
        value = sizes.value_of(name, section)
        digits = int(re.match(r"\d+", value).group())
        assert digits >= 1, f"{name} kommt als {value!r} heraus"


def test_a_factor_that_is_not_a_number_does_not_stop_the_generation(
        tmp_path, monkeypatch):
    """Die Einstellungsdatei ist von Hand editierbar.

    "gross" statt 1.5 in sizes.scale liess bis hierher JEDE Groesse mit
    einem TypeError sterben, mitten in der Erzeugung, ohne dass
    irgendetwas sagt, welcher Wert es war. Der Rest der Konfiguration -
    Leiste, Terminal, Shell - haengt an einer Zahl, die mit ihm nichts
    zu tun hat.
    """
    _no_compositor(monkeypatch)
    for broken in ("gross", None, 0, -2, [1.5]):
        style = _import_style(
            tmp_path / f"broken-{abs(hash(str(broken)))}", monkeypatch,
            {"sizes": {"scale": broken}})
        assert style.STYLE_VARIABLES["STYLE_FONT_BODY"] == (
            f"{sizes.DEFAULT_PX}px"), f"scale={broken!r} kam nicht zurueck"


def test_a_sizes_section_of_the_wrong_shape_is_read_as_none(tmp_path,
                                                            monkeypatch):
    """`"sizes": 1.5` ist der naheliegendste Fehler von jemandem, der den
    Faktor sucht. Er darf nicht in einem AttributeError enden."""
    _no_compositor(monkeypatch)
    style = _import_style(tmp_path, monkeypatch, {"sizes": 1.5})
    assert style.STYLE_VARIABLES["STYLE_FONT_BODY"] == f"{sizes.DEFAULT_PX}px"


# --------------------------------------------------------------------
# die 164 Literale, und dass sie nicht zurueckkommen
# --------------------------------------------------------------------

def _without_comments(css):
    """CSS ohne Kommentare.

    "font-size: 14px" in einer Datei zu suchen ist auch dann wahr, wenn
    es nur in einem Kommentarkopf steht. Geprueft wird deshalb gegen den
    Code, und der Kommentar ueber einer Regel darf die Zahl weiter
    nennen, die er erklaert.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    return "\n".join(line for line in css.splitlines()
                     if not line.lstrip().startswith("//"))


def test_no_font_size_in_the_ags_stylesheet_is_a_literal():
    """164 Literale, gezaehlt am 11.08.2026.

    So lange konnte die groesste Oberflaeche des Schreibtischs gar nicht
    vergroessert werden: die Platzhalter dafuer gab es (vierundachtzig
    Stueck), und das Stylesheet benutzte keinen davon. Das ist auch der
    Satz, mit dem CLAUDE.md anfaengt - NIEMALS hart hinschreiben.
    """
    code = _without_comments(AGS_STYLE.read_text(encoding="utf-8"))
    literals = re.findall(r"font-size:\s*[\d.]+\s*(?:px|pt|em|rem)?\s*;", code)

    assert literals == [], (
        f"{len(literals)} Schriftgroessen stehen wieder als Zahl im "
        f"Stylesheet statt als {{{{{sizes.FONT_PREFIX}ROLLE}}}} oder "
        f"{{{{{sizes.ICON_PREFIX}ROLLE}}}}: "
        + ", ".join(sorted(set(literals))))


def test_the_per_screen_copies_of_the_ladder_are_gone(tmp_path, monkeypatch):
    """Siebzig Platzhalter, die ihr einziger Leser nicht benutzen KANN.

    Die Leiter stand einmal global und einmal pro Bildschirmplatz da.
    ags-style.template ist EIN Stylesheet fuer alle Schirme, und
    GTK-CSS kennt keinen Selektor fuer einen Monitor - eine Regel darin
    kann gar nicht sagen "auf dem zweiten Schirm 16 px".

    Geprueft wird an der ERZEUGTEN Menge und nicht an der Quelle: eine
    Textsuche im Quelltext findet einen zweiten Weg nicht, die
    Platzhalter doch wieder anzulegen, und _per_screen() setzt die Namen
    ohnehin aus f-Strings zusammen.
    """
    _no_compositor(monkeypatch)
    style = _import_style(tmp_path, monkeypatch)

    per_screen = [name for name in dict(style.STYLE_VARIABLES)
                  if re.fullmatch(r"STYLE_(EWW_FONT|FONT|ICON)_.*_MON[0-4]",
                                  name)]
    assert per_screen == [], (
        "die Schriftleiter wird wieder pro Bildschirmplatz ausgegeben: "
        + ", ".join(sorted(per_screen)))

    # Und die Leiter, die es GIBT, hat keinen Platz-Namen.
    assert [name for name in sizes.TABLE if "_MON" in name] == []


def test_the_bar_thickness_is_not_a_literal_in_the_bar(): 
    """Zwei Zahlen fuer eine Hoehe, von denen die eine nichts tat.

    STYLE_BAR_THICKNESS war als "50px" definiert und wurde von keiner
    Vorlage gelesen; die Leistendicke stand als nackte 50 in
    waybar-config.template. Sie MUSS der Schrift folgen: 50 px trugen
    13 px Text, und 24 px Text in einer 50 px hohen Leiste werden oben
    und unten beschnitten.

    Zeilengenau und gegen den Code ohne Kommentare: der Kopf der Vorlage
    ERKLAERT die alte 50, und eine Teilzeichenkettensuche wuerde von der
    Erklaerung wahr.
    """
    lines = _uncommented(BAR_SOURCE.read_text(encoding="utf-8"), "//")
    assert "export const BAR_THICKNESS = {{STYLE_BAR_THICKNESS}}" in lines
    height_literals = [line for line in lines
                       if re.match(r"(export )?const BAR_THICKNESS\s*=\s*\d", line)]
    assert height_literals == [], (
        f"die Leistendicke steht wieder als Zahl in der Vorlage: {height_literals}")


@pytest.mark.parametrize("scale", [1.0, 1.5, sizes.SCALE_DEFAULT, 4.0])
def test_the_bar_thickness_carries_no_unit(scale):
    """ags-bar.template ist TypeScript.

    "50px" dort hinein ist kein grosser Balken, sondern ein
    Syntaxfehler - `const BAR_THICKNESS = 185px` -, und der kostet nicht die
    Hoehe, sondern die ganze Leiste. Der einzige Hinweis darauf steht in
    der Konsolenausgabe von AGS, die ausser dem Generator niemand
    aufmacht.

    Bei jedem Faktor geprueft und nicht nur bei einem: die Einheit haengt
    am Tabelleneintrag, aber die Rundung baut die Zeichenkette, und eine
    Zeichenkette, die bei einem Faktor sauber ist und bei einem anderen
    ein Komma traegt, ist derselbe Fehler.
    """
    assert sizes.TABLE["STYLE_BAR_THICKNESS"].unit == sizes.BARE

    rendered = sizes.value_of("STYLE_BAR_THICKNESS", {"scale": scale})
    assert re.fullmatch(r"\d+", rendered), (
        f"die Leistendicke kommt als {rendered!r} heraus, und eine "
        f"TypeScript-Konstante nimmt nur eine nackte Zahl")


# --------------------------------------------------------------------
# die Schrift im Terminal
# --------------------------------------------------------------------

KITTY = SRC / "templates" / "kitty-config.template"

# Punkt in Pixel, bei 96 dpi. kitty rechnet px = pt * dpi / 72, und 96
# ist die Aufloesung, bei der GTK seine CSS-Pixel definiert - also die
# Zahl, in der die beiden Schriften ueberhaupt vergleichbar sind.
PER_POINT = 96 / 72


def test_the_terminal_font_is_not_a_literal_in_the_kitty_config():
    """GEMELDET am 11.08.2026: "die font size im terminal ist zu beginn
    zu klein".

    Hier stand `font_size 7.0`, waehrend der Regler daneben 29 andere
    Groessen bewegte. Ein Terminal, das man den ganzen Tag ansieht, war
    das einzige Fenster des Schreibtischs, an dem der Regler nicht griff.

    Geprueft wird auf den Platzhalter UND darauf, dass keine nackte Zahl
    danebensteht: eine zweite font_size-Zeile unter der ersten gewinnt
    in kitty, und die Vorlage saehe trotzdem richtig aus.
    """
    lines = [line.strip() for line in KITTY.read_text(encoding="utf-8").splitlines()
             if line.strip().startswith("font_size")]

    assert lines == ["font_size        {{STYLE_TERMINAL_FONT_SIZE}}"], (
        "kitty bekommt seine Schriftgroesse nicht (nur) aus sizes.py: "
        + repr(lines))


@pytest.mark.parametrize("scale", [1.0, 1.3, 1.5, sizes.SCALE_DEFAULT, 2.0])
def test_the_terminal_font_is_as_large_as_the_desktop_font(scale):
    """Dieselbe Schriftgroesse, in zwei Einheiten.

    Die Vorgabe faellt an beiden Enden auf die Zahlen des Systems: bei
    Faktor 1.00 sind 10 pt 13.3 px und damit sizes.BASE_PX, bei der
    ausgelieferten 1.54 sind 15.4 pt 20.5 px und damit sizes.DEFAULT_PX,
    die Grundschrift des Schreibtischs.

    Eine Pixel Spielraum, und keine mehr: kitty nimmt nur ganze Zehntel
    Punkt, value_of() rundet auf ganze Zahlen, und 0.75 px ist der
    groesste Abstand, den diese beiden Rasterungen zusammen erzeugen
    koennen. Zwei waeren schon die Toleranz, unter der `font_size 7.0`
    NICHT aufgefallen waere - der Fehler, der das hier ausgeloest hat,
    war 15 px gross.
    """
    section = {"scale": scale}
    terminal = int(sizes.value_of("STYLE_TERMINAL_FONT_SIZE", section))
    desktop = int(sizes.value_of("STYLE_FONT_BODY", section).removesuffix("px"))

    assert abs(terminal * PER_POINT - desktop) <= 1, (
        f"bei Faktor {scale} zeigt das Terminal {terminal} pt "
        f"({terminal * PER_POINT:.1f} px) und der Schreibtisch "
        f"{desktop} px")


def _kitty_modules() -> Path | None:
    """Das Verzeichnis, in dem kittys eigene Python-Module liegen.

    Aus dem Pfad des Programms abgeleitet statt geraten: `kitty` liegt in
    <praefix>/bin und seine Module in <praefix>/lib/kitty. Findet sich
    dort keine config.py, gibt es nichts zu befragen und der Test wird
    uebersprungen - eine Maschine ohne kitty kann diese Frage nicht
    beantworten, und eine erfundene Antwort waere schlimmer als keine.
    """
    program = shutil.which("kitty")
    if program is None:
        return None
    modules = Path(program).resolve().parent.parent / "lib" / "kitty"
    return modules if (modules / "kitty" / "config.py").is_file() else None


@pytest.mark.allow_subprocess
def test_kitty_itself_reads_the_generated_size(processor, tmp_path,
                                               monkeypatch):
    """Nicht "es steht die richtige Zahl da", sondern "kitty liest sie".

    Der Unterschied ist die Einheit. `font_size 18px` sieht in der Datei
    aus wie ein gesetzter Wert, und kitty verwirft die Zeile mit einer
    Warnung, die in keinem Log landet, das jemand aufmacht - das Terminal
    steht dann auf KITTYS Vorgabe von 11 pt, egal was eingestellt ist.
    Eine Textsuche in der Vorlage kann das nicht unterscheiden; kittys
    eigener Parser kann es.

    Er wird in einem Kind gestartet, weil er den Systeminterpreter
    braucht: kittys Module liegen ausserhalb der virtuellen Umgebung.
    Angefasst wird dabei nichts - load_config() liest eine Datei.
    """
    modules = _kitty_modules()
    if modules is None:
        pytest.skip("kitty fehlt; ohne seinen Parser gibt es nichts zu fragen")

    # Vor _no_compositor gegriffen: das ersetzt subprocess.run durch
    # etwas, das JEDEN Kindprozess mit FileNotFoundError beantwortet -
    # damit die Groessen allein an den Einstellungen haengen und nicht an
    # einem hyprctl. Der Aufruf unten ist aber genau der Punkt dieses
    # Tests.
    spawn = subprocess.run

    _no_compositor(monkeypatch)
    style = _import_style(tmp_path / "settings", monkeypatch)
    out = tmp_path / "out"
    out.mkdir()
    target = out / "kitty.conf"
    processor.ConfigProcessor(
        styles=dict(style.STYLE_VARIABLES)).apply_template(KITTY, target)

    result = spawn(
        ["/usr/bin/python3", "-c",
         "import sys; from kitty.config import load_config;"
         "print(load_config(sys.argv[1]).font_size)", str(target)],
        env={"PYTHONPATH": str(modules), "PATH": "/usr/bin:/bin",
             "HOME": str(tmp_path)},
        capture_output=True, text=True, timeout=120)

    assert result.returncode == 0, result.stdout + result.stderr
    expected = float(sizes.value_of("STYLE_TERMINAL_FONT_SIZE", {}))
    assert float(result.stdout.strip()) == expected, (
        f"kitty liest {result.stdout.strip()} aus der erzeugten Datei, die "
        f"Tabelle sagt {expected}")


def test_the_terminal_font_carries_no_unit():
    """kitty liest eine nackte Zahl. "18px" hinter font_size ist kein
    grosser Balken, sondern eine Zeile, die kitty mit einer Warnung
    verwirft - und dann steht das Terminal auf SEINER Vorgabe von 11 pt,
    egal was der Nutzer eingestellt hat."""
    assert sizes.TABLE["STYLE_TERMINAL_FONT_SIZE"].unit == sizes.BARE
    for scale in (1.0, sizes.SCALE_DEFAULT, 4.0):
        rendered = sizes.value_of("STYLE_TERMINAL_FONT_SIZE", {"scale": scale})
        assert re.fullmatch(r"\d+", rendered), (
            f"font_size kaeme als {rendered!r} heraus")


# --------------------------------------------------------------------
# was aus den zwei toten Abschnitten wurde
# --------------------------------------------------------------------

def test_the_two_dead_settings_sections_do_not_come_back():
    """"fonts" und "spacing" standen in DEFAULT_SETTINGS und wurden von
    keiner Zeile gelesen.

    Vier Zahlen - base_size 13, icon_size 18, module 10, bar_height 50 -
    die genau den vier Werten entsprachen, die style_definition.py als
    Literale ausschrieb. Jedes Speichern schrieb sie in die Datei des
    Nutzers zurueck. Sie sind durch "sizes" ersetzt, und zwar durch
    einen Abschnitt, dessen jeder Eintrag oben nachgewiesen wird.

    Geprueft gegen den Code ohne Kommentare: der Kommentar, der ihren
    Abgang begruendet, nennt beide Namen und soll das weiter tun.
    """
    code = _python_code_only(SRC / "user_settings.py")
    for dead in ('"fonts"', '"base_size"', '"icon_size"', '"spacing"'):
        assert dead not in code, (
            f"{dead} ist wieder da - eine Einstellung, die niemand liest")

    # Und dasselbe an der Struktur statt am Text, weil ein Abschnitt
    # auch ueber einen berechneten Schluessel zurueckkommen kann.
    import sys
    sys.path.insert(0, str(SRC))
    import user_settings

    assert "fonts" not in user_settings.DEFAULT_SETTINGS
    assert "spacing" not in user_settings.DEFAULT_SETTINGS


def test_the_settings_schema_knows_the_size_section():
    """`zepos-settings set sizes.scale 1.0` ist der dokumentierte Weg
    zurueck.

    cli._set() lehnt jeden Pfad ab, den weder die Datei noch
    settings.defaults() kennt. Ohne den Abschnitt dort waere der Befehl,
    der in sizes.py als Rueckweg genannt wird, ein "no such setting".
    """
    from src import settings

    assert settings.defaults()[sizes.SECTION]["scale"] == sizes.SCALE_DEFAULT
    assert settings.defaults()[sizes.SECTION]["values"] == {}


# --------------------------------------------------------------------
# der ganze Weg: Befehl -> Datei -> erzeugte Konfiguration
# --------------------------------------------------------------------
#
# Die Tests oben schreiben die Einstellungsdatei selbst. Das prueft die
# Leseseite und laesst die Schreibseite offen - und die Schreibseite ist
# die, die der Nutzer bedient. Ein Setzer, der in einen Abschnitt
# schreibt, den der Leser nicht liest, sieht in beiden Haelften richtig
# aus.


@pytest.fixture
def commands(tmp_path, monkeypatch):
    """user_settings, mit seiner Einstellungsdatei in tmp_path."""
    monkeypatch.delenv("ZEPOS_SYSTEM_ROOT", raising=False)
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path / "settings"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "settings"))
    monkeypatch.syspath_prepend(str(SRC))
    import user_settings

    return user_settings


def test_the_command_line_reaches_the_generated_file(commands, processor,
                                                     tmp_path, monkeypatch):
    """`set-size --key ... --value ...` und dann erzeugen.

    Das ist die Pruefung, die MONITOR_HEIGHT_SCALES nicht ueberlebt
    haette: dort gab es einen Befehl, er schrieb in die Datei, die Datei
    war danach anders - und die erzeugte Konfiguration nicht.
    """
    commands.set_size("STYLE_FONT_BODY", "42px")

    stored = json.loads(
        (tmp_path / "settings" / "user-settings.json").read_text("utf-8"))
    assert stored[sizes.SECTION]["values"]["STYLE_FONT_BODY"] == "42px"

    _no_compositor(monkeypatch)
    style = _import_style(tmp_path / "settings", monkeypatch)
    templates = _templates_naming("STYLE_FONT_BODY")
    assert "42px" in _render(processor, style, templates, tmp_path / "out")


def test_the_factor_from_the_command_line_reaches_the_generated_file(
        commands, processor, tmp_path, monkeypatch):
    """Dasselbe fuer den einen Regler."""
    commands.set_size_scale(2.0)

    _no_compositor(monkeypatch)
    style = _import_style(tmp_path / "settings", monkeypatch)
    templates = _templates_naming("STYLE_FONT_BODY")
    # 13 * 2
    assert "26px" in _render(processor, style, templates, tmp_path / "out")


def test_clearing_a_size_hands_it_back_to_the_factor(commands, tmp_path,
                                                     monkeypatch):
    """Ohne das waere set-size eine Einbahnstrasse.

    Der einzige Weg zurueck fuehrte durch das Editieren der JSON-Datei
    von Hand - also genau durch das, wofuer es diese Befehle gibt. Den
    Namen auf seinen Grundwert zu SETZEN ist nicht dasselbe: er stuende
    dann fest und wuerde dem Faktor nicht mehr folgen.
    """
    commands.set_size_scale(2.0)
    commands.set_size("STYLE_FONT_BODY", "42px")

    _no_compositor(monkeypatch)
    fixed = _import_style(tmp_path / "settings", monkeypatch)
    assert fixed.STYLE_VARIABLES["STYLE_FONT_BODY"] == "42px"

    commands.clear_size("STYLE_FONT_BODY")

    _no_compositor(monkeypatch)
    freed = _import_style(tmp_path / "settings", monkeypatch)
    assert freed.STYLE_VARIABLES["STYLE_FONT_BODY"] == "26px"


def test_resetting_the_sizes_drops_the_single_values_too(commands, tmp_path,
                                                         monkeypatch):
    """Der Abschnitt wird ERSETZT, nicht verschmolzen.

    Beim Verschmelzen bliebe jede einzeln gesetzte Groesse stehen, weil
    die Vorgabe fuer `values` ein leeres Objekt ist und ein leeres
    Objekt nichts ueberschreibt. Ausgerechnet die Einzelwerte sind das,
    was jemand loswerden will, der "zuruecksetzen" tippt, nachdem er
    sich verstellt hat.
    """
    commands.set_size_scale(3.0)
    commands.set_size("STYLE_FONT_BODY", "42px")
    commands.reset_sizes()

    _no_compositor(monkeypatch)
    style = _import_style(tmp_path / "settings", monkeypatch)
    assert style.STYLE_VARIABLES["STYLE_FONT_BODY"] == f"{sizes.DEFAULT_PX}px"


def test_a_size_nobody_has_is_refused_rather_than_stored(commands):
    """Ein vertippter Name, der gespeichert und von niemandem gelesen
    wird, ist das leiseste Versagen dieses Programms: der Nutzer hat eine
    Einstellung geaendert, der Befehl hat "gespeichert" gesagt, und an
    der Maschine hat sich nichts geaendert.

    Dieselbe Entscheidung, die cli._set() fuer einen unbekannten Pfad
    trifft.
    """
    for name in ("STYLE_FONT_BDOY", "font_size", "STYLE_EWW_FONT_13",
                 "STYLE_FONT_HUGE"):
        with pytest.raises(KeyError):
            commands.set_size(name, "20px")
        with pytest.raises(KeyError):
            commands.clear_size(name)


@pytest.mark.parametrize("refused", [0, -1, -0.5])
def test_a_factor_of_zero_or_less_is_refused_at_the_command_line(commands,
                                                                 refused):
    """Die Erzeugung faengt das auch ab - aber STILL, indem sie auf die
    Vorgabe zurueckfaellt.

    Der Nutzer haette dann einen Befehl abgesetzt, eine Bestaetigung
    gelesen und keine Aenderung gesehen. Abgelehnt wird deshalb hier, wo
    noch jemand zuschaut.
    """
    with pytest.raises(ValueError):
        commands.set_size_scale(refused)


def test_the_shipped_values_map_is_empty():
    """Nicht mit allen Namen und ihren Grundwerten vorbefuellt.

    Das waere eine zweite Kopie der Tabelle, in einer Datei, die niemand
    mitpflegt - genau die Falle, in die die Farben schon einmal getappt
    sind, wo `warning` in der einen Kopie #f9e2af war und in der anderen
    #fab387. Ab dem ersten Speichern gewinnt die Kopie.
    """
    assert sizes.defaults()["values"] == {}


# --------------------------------------------------------------------
# Der Streifen: eine Dicke fuer Kopf und Fuss
# --------------------------------------------------------------------

@pytest.mark.parametrize("scale", [1.0, 1.2, 1.3, 1.385, 1.4615, 1.5,
                                   sizes.SCALE_DEFAULT, 2.0, 2.5, 4.0])
def test_the_header_and_the_footer_are_one_number_at_every_setting(scale):
    """"der header soll IMMER genauso gross sein wie unser nwg dock".

    Das "immer" ist der Teil, den eine einzelne Messung nicht beweist.
    Vor dem 12.08.2026 waren es zwei unabhaengige Zahlen, und sie
    kreuzten sich zwischen Faktor 1.3 und 1.4 - bei kleiner Schrift war
    die Leiste duenner als der Fuss, bei grosser dicker. Ein Test bei
    Vorgabegroesse allein haette das nicht gesehen.

    Gerechnet wird hier und nicht gemessen; die Verbindung zur
    Wirklichkeit stellt test_the_header_is_exactly_as_tall_as_the_footer
    in tests/src/test_bar_headless.py her, das die echte Hoehe unter
    gtk4-broadwayd nimmt.
    """
    section = {"scale": scale}
    bar = int(sizes.value_of("STYLE_BAR_THICKNESS", section))
    icon = int(sizes.value_of("STYLE_DOCK_ICON_SIZE", section))
    footer = icon + sizes.dock_chrome(section)

    assert bar == footer, (
        f"bei sizes.scale {scale} ist die Leiste {bar} px dick und der "
        f"Fuss {footer} px hoch ({icon} px Symbol plus "
        f"{sizes.dock_chrome(section)} px Beiwerk)")

    # Und der Fuss traegt wirklich ein Symbol. Ohne diese Zeile waere
    # die Gleichung mit einem Symbol der Groesse 0 zu erfuellen.
    assert icon >= sizes.MINIMUM_DOCK_ICON, icon


def test_a_named_thickness_carries_the_footer_with_it():
    """Wer die Leiste dicker stellt, stellt den Fuss mit.

    Das ist die Probe darauf, dass die Ableitung NACH dem Einzelwert
    greift und nicht davor: ein Nutzer, der STYLE_BAR_THICKNESS setzt,
    haette sonst wieder zwei verschieden hohe Streifen - genau der
    Zustand, den diese Aenderung behebt.
    """
    section = {"scale": 1.0, "values": {"STYLE_BAR_THICKNESS": "140"}}
    bar = int(sizes.value_of("STYLE_BAR_THICKNESS", section))
    icon = int(sizes.value_of("STYLE_DOCK_ICON_SIZE", section))

    assert bar == 140
    assert icon + sizes.dock_chrome(section) == 140, (
        f"der Fuss folgt der eingestellten Dicke nicht: {icon} px Symbol "
        f"plus {sizes.dock_chrome(section)} px Beiwerk")


def test_a_named_icon_size_still_wins():
    """Und die Gegenrichtung: eine genannte Zahl schlaegt die Ableitung.

    Sonst waere aus einem Regler eine Anzeige geworden. Der Preis - zwei
    verschieden hohe Streifen - steht in src/sizes.py bei DERIVED und
    ist dann die Entscheidung des Nutzers.
    """
    section = {"scale": 1.0, "values": {"STYLE_DOCK_ICON_SIZE": "24"}}
    assert sizes.value_of("STYLE_DOCK_ICON_SIZE", section) == "24"
