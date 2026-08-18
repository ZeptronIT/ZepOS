# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Anmeldemaske traegt die Marke - und zwar so, dass GTK sie liest.

WAS GEMESSEN WURDE
    iso/out/run-release-installed/key-01-01-anmeldung.png, 11.08.2026, auf
    dem installierten System. Der Hintergrund war ZepOS und alles davor
    war libadwaita: graue Anmeldekachel, graue Uhr, "Login" in #3584e4,
    "Reboot" und "Power Off" im selben #c01c28.

    Der Grund war kein Fehler, sondern eine Luecke: es gab kein
    Stylesheet. src/login/regreet.toml hat sie sogar beschrieben - das
    Blatt des Assistenten steht in installer/gui/branding.py, gehoert
    zepos-installer und liegt nur auf dem Medium (Spec 4.2).

WAS DIESE DATEI BEWACHT
    Vier Dinge, und drei davon fallen sonst lautlos aus:

      * dass die ausgelieferte Datei zu ihrem Erzeuger passt. Sie ist
        eingecheckt, weil das Paket sie kopiert; ein Paket, das seine
        Konfiguration zur Bauzeit aus Python erzeugt, ist eins, dessen
        Inhalt niemand vor dem Bauen lesen kann.
      * dass regreet sie ueberhaupt gereicht bekommt. Ohne --style nimmt
        es /etc/greetd/regreet.css, das es nicht gibt, und zeichnet grau
        weiter - ohne eine Zeile im Log.
      * dass GTK sie fehlerfrei liest. GtkCssProvider meldet einen
        Parse-Fehler ueber ein Signal, an dem regreet nicht haengt, und
        verwirft dann die Regel und macht weiter. Eine kaputte Datei ist
        also wieder eine graue Maske.
      * dass keine Farbe darin ein Literal ist.
"""
from __future__ import annotations

import ast
import importlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

from src import brand, sizes
from tests import gtk4_headless
# Auf Modulebene, weil der Isolationswaechter waehrend eines Tests kein
# __pycache__ anlegen laesst - tests/src/test_spacing.py hat dieselbe
# Zeile und dieselbe Begruendung.
from tests.src import test_sizes

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
LOGIN = SRC / "login"


def _flat(name: str):
    """Ein Modul aus src/, das selbst flach importiert.

    src/theme.py sagt `import brand` und `from paths import ...` - wie
    jedes Modul dort -, also ist es ueber `from src import theme` nicht
    erreichbar: src/ ist kein Paket. Der Suchpfad wird deshalb nur fuer
    die Dauer des Imports erweitert und danach wieder aufgeraeumt, damit
    kein spaeterer Test versehentlich ein src-Modul unter blossem Namen
    findet - dieselbe Sorgfalt, die die Vorrichtungen unten mit
    monkeypatch treiben.
    """
    sys.path.insert(0, str(SRC))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(SRC))


theme = _flat("theme")
THEMES = sorted(theme.THEMES)
GREETER = SRC / "bin" / "zepos-greeter"
REGREET_TOML = SRC / "login" / "regreet.toml"
RECIPE = ROOT / "packaging" / "zepos-config" / "PKGBUILD"

# Wohin die Dateien gehen. Nicht /etc/greetd/regreet.css: das ist
# regreets eigene Vorgabe (CSS_PATH in src/constants.rs) und damit ein
# Pfad, den ein fremdes Paket beanspruchen kann - derselbe
# Dateikonflikt-Grund, aus dem schon zepos.toml und zepos-regreet.toml
# daneben liegen.
#
# EINE DATEI JE THEMA, seit dem 12.08.2026: /etc gehoert root und die
# Maske laeuft als Benutzer "greeter", also kann ein Themenwechsel sie
# nur erreichen, wenn schon alle Blaetter da sind. Der Kopf von
# src/greeter.py fuehrt es aus.
ETC = "/etc/greetd"

# Das Muster steht hier ein zweites Mal, absichtlich: greeter.filename()
# baut es, diese Zeile prueft es (siehe
# test_the_name_the_module_builds_is_the_name_the_tree_carries). Zwei
# Haelften, die einander pruefen, sind etwas anderes als zwei Kopien -
# eine Vorrichtung, die den Namen aus dem Modul holt, koennte einen
# Tippfehler im Modul nicht finden, weil sie ihn mitbraechte.
def shipped(name: str) -> Path:
    return LOGIN / f"zepos-greeter-{name}.css"


def installed(name: str) -> str:
    return f"{ETC}/zepos-greeter-{name}.css"


@pytest.fixture
def greeter(monkeypatch):
    """Das Modul, so importiert, wie der Paketbau es importiert.

    Ueber den Suchpfad und nicht als `from src import greeter`: src/ ist
    kein Paket, und src/greeter.py sagt `import brand` - flach, wie jedes
    andere Modul dort. Dieselbe Form wie die update-Vorrichtung in
    tests/src/test_update.py.
    """
    monkeypatch.syspath_prepend(str(SRC))
    import greeter as module

    return module


def _code(text: str) -> str:
    """Ohne Kommentare.

    Jede Datei in diesem Baum ERKLAERT, was sie tut und warum, und die
    Erklaerung nennt die Namen, um die es geht. `"--style" in datei` ist
    auch dann wahr, wenn --style nur im Kopf erwaehnt wird - genau die
    Falle, die tests/src/test_sizes.py fuer sich schon aufschreibt.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("#"))


# --------------------------------------------------------------------
# Die ausgelieferte Datei ist die erzeugte
# --------------------------------------------------------------------

@pytest.mark.parametrize("name", THEMES)
def test_the_shipped_stylesheet_is_what_the_module_builds(greeter, name):
    """Byte fuer Byte, wie bei src/system/zepos-update.timer.

    Ohne das koennte jemand die CSS-Datei von Hand berichtigen, waehrend
    src/greeter.py etwas anderes fuer richtig haelt - und beide Seiten
    saehen fuer sich vollstaendig richtig aus. Beim naechsten Erzeugen
    waere die Handarbeit weg.
    """
    built = greeter.stylesheet(theme.palette(name))
    assert shipped(name).read_text(encoding="utf-8") == built, (
        f"{shipped(name)} und src/greeter.py sind auseinander. "
        f"Neu schreiben mit: {WRITE_COMMAND}")


WRITE_COMMAND = (
    "python -c \"import sys,pathlib; sys.path.insert(0,'src'); "
    "import greeter,theme; "
    "[pathlib.Path('src/login',greeter.filename(n)).write_text("
    "greeter.stylesheet(theme.palette(n))) for n in theme.THEMES]\"")


@pytest.mark.parametrize("name", THEMES)
def test_the_name_the_module_builds_is_the_name_the_tree_carries(
        greeter, name):
    """Die eine Zeichenkette, die an vier Stellen dieselbe sein muss.

    src/greeter.py baut sie, src/login/ traegt sie, der PKGBUILD legt
    sie ab und src/bin/zepos-greeter setzt sie aus dem Themennamen
    zusammen. Waere sie an einer der vier anders, faende der Greeter
    sein Blatt nicht - und ein fehlendes Blatt kostet die Farben und
    nicht die Anmeldung, faellt also niemandem auf.
    """
    assert greeter.filename(name) == shipped(name).name


def test_every_theme_has_a_stylesheet_and_no_stylesheet_is_orphaned():
    """In beide Richtungen, wie bei brand.COLOR_GROUPS.

    Ein Thema ohne Blatt heisst: der Greeter faellt auf das
    ausgelieferte zurueck, und die Anmeldemaske zeigt still ein anderes
    Thema als der Schreibtisch dahinter. Ein Blatt ohne Thema heisst:
    eine Datei unter /etc, die niemand mehr waehlen kann.
    """
    on_disk = {path.name for path in LOGIN.glob("zepos-greeter-*.css")}
    expected = {shipped(name).name for name in THEMES}
    assert on_disk == expected


def _strings_in(path: Path) -> list[str]:
    """Jede Zeichenkette der Datei, ausser den Docstrings.

    WARUM NICHT _python_code_only() AUS test_sizes.py, WIE NEBENAN
        Weil es genau das Gegenteil von dem tut, was hier gebraucht wird.
        Es streicht Python-KOMMENTARE, also alles ab einem `#`, das nicht
        direkt hinter einem Anfuehrungszeichen steht - und eine Farbe
        heisst `#08262C`. In `background-color: #08262C;` steht vor dem
        Doppelkreuz ein Leerzeichen, also strich es die Farbe mitsamt dem
        Rest der Zeile weg.

        NACHGEWIESEN mit einer Mutationsprobe: eine Farbe von Hand in
        src/greeter.py geschrieben, und die Pruefung ging durch. Sie war
        eine Tautologie - sie KONNTE nichts finden.

        Gesucht wird deshalb dort, wo eine Farbe im Erzeuger stehen
        WUERDE: in den Zeichenketten, aus denen er das Blatt baut.
        ast.Constant findet sie auch innerhalb eines f-Strings, wo eine
        zeilenweise Textsuche zwischen Text und Ausdruck nicht
        unterscheiden kann.

        Die Docstrings bleiben draussen, und das ist dieselbe Regel wie
        in test_sizes.py: der Kopf von src/greeter.py BESCHREIBT die drei
        libadwaita-Farben des Messbilds, und ein Wachhund, der die
        Messung verbietet, die seine eigene Regel begruendet, wird
        umgangen, indem man die Messung loescht.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            if ast.get_docstring(node, clean=False) is not None:
                docstrings.add(id(node.body[0].value))
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings]


def test_the_stylesheet_carries_no_colour_of_its_own():
    """Jede Farbe kommt aus brand.py.

    Das ist die Regel, mit der brand.py anfaengt, und die Geschichte
    dahinter ist gemessen: die Vorgabefarben standen dreimal im Baum, und
    `warning` war in zweien #f9e2af und in der dritten #fab387 - welches
    Gelb eine Maschine zeigte, hing davon ab, ob jemand den Stil-Editor
    aufgemacht hatte.

    Geprueft wird am QUELLTEXT des Erzeugers und nicht an der erzeugten
    Datei: in der stehen die Hexwerte natuerlich, das ist ihr Zweck.
    """
    literals = [found
                for text in _strings_in(SRC / "greeter.py")
                for found in re.findall(r"#[0-9a-fA-F]{6}\b", text)]
    assert literals == [], (
        f"src/greeter.py schreibt Farben selbst hin statt sie aus "
        f"brand.py zu nehmen: {sorted(set(literals))}")


@pytest.mark.parametrize("name", THEMES)
def test_every_spacing_in_the_stylesheet_is_a_rung(greeter, name):
    """Und jeder Abstand aus sizes.py.

    Gemessen an der ERZEUGTEN Datei, weil der Erzeuger f-Strings baut und
    eine Zahl sich hinter einer Klammer verstecken kann.
    """
    rungs = {sizes.value_of(f"{sizes.SPACE_PREFIX}{step}", {})
             for step in sizes.SPACE_LADDER}
    offenders = []
    for line in _code(greeter.stylesheet(theme.palette(name))).splitlines():
        # min-height und min-width seit dem 13.08.2026 mit im Netz. Sie
        # standen vorher nicht drin, weil die Maske keine hatte; als sie
        # welche bekam - der Nutzer wollte Felder wie die des
        # Assistenten -, waere die naechstliegende Zahl eine gewesen, die
        # zu 45 px passt, und 45 ist keine Sprosse, sondern regreets
        # `set_height_request` aus dem Rust-Quelltext.
        match = re.match(
            r"\s*(padding|margin|min-height|min-width)[a-z-]*\s*:\s*([^;]+);",
            line)
        if not match:
            continue
        for token in match.group(2).split():
            if token not in rungs and token not in {"0", "0px"}:
                offenders.append(line.strip())
                break

    assert offenders == [], (
        "die Anmeldemaske setzt Abstaende neben der Leiter: "
        + "; ".join(offenders))


@pytest.mark.parametrize("name", THEMES)
def test_every_rounding_in_the_stylesheet_is_a_rung(greeter, name):
    """Und jede Ecke, aus demselben Grund - und aus einem zweiten.

    GEMELDET am 13.08.2026: "das sieht nicht gut aus ich sagte eigenens
    style". Auf dem Messbild dazu standen in EINER Zeile des Rasters
    zwei Formen nebeneinander: das Auswahlfeld als Pille (999px) und
    der Stiftknopf daneben mit 8px. Beide waren einzeln begruendet - die
    Pille "wie der Sperrbildschirm", die 8 "wie ein Knopf" - und
    zusammen waren sie eine Maske aus zwei Baukaesten.

    sizes.py fuehrt fuer genau diesen Fall eine Leiter mit drei Sprossen
    und schreibt dazu, wofuer jede da ist; STYLE_RADIUS_CONTROL nennt
    sie woertlich fuer "Knopf, Eingabe, Reiter". Diese Zusicherung haelt
    die Maske darauf fest. RADIUS_PILL und RADIUS_FULL sind ausdruecklich
    KEINE Sprossen - sizes.py sagt das an ihrer Definition -, also faellt
    eine Pille hier durch.
    """
    rungs = {sizes.value_of(f"{sizes.RADIUS_PREFIX}{role}", {})
             for role, _ in sizes.RADIUS_ROLES}
    offenders = []
    for line in _code(greeter.stylesheet(theme.palette(name))).splitlines():
        match = re.match(r"\s*border-radius\s*:\s*([^;]+);", line)
        if not match:
            continue
        for token in match.group(1).split():
            if token not in rungs and token not in {"0", "0px"}:
                offenders.append(line.strip())
                break

    assert offenders == [], (
        "die Anmeldemaske rundet neben der Leiter - "
        f"die Sprossen sind {sorted(rungs)}: " + "; ".join(offenders))


# --------------------------------------------------------------------
# Die drei Waechter vom 13.08.2026
# --------------------------------------------------------------------
# Sie stehen hier, weil an diesem Tag zum zweiten Mal derselbe Satz kam -
# "du hast die login felder und style dropdown und button immernoch nicht
# veraendert" - und die Zusicherungen darueber ALLE gruen waren.
#
# Sie waren gruen und sie hatten recht: jede Farbe kam aus theme.py,
# jeder Abstand von der Leiter, GTK las die Datei ohne einen Fehler. Was
# keine davon lesen konnte, ist, ob eine Regel jemals ein WIDGET
# ERREICHT. Eine Regel, die nichts trifft, ist syntaktisch tadellos.
#
# Die drei unten pruefen genau das, jede an einem Fehler, der wirklich
# passiert ist und der auf dem Bild stand.

# Die Knoten, die regreets Maske in einem echten GTK4 wirklich hat.
#
# GEMESSEN am 13.08.2026 gegen GTK 4.22.4: regreets Widget-Baum aus
# src/gui/templates.rs des Tags 0.5.0 nachgebaut (tests/render/
# greeter_shot.py baut denselben) und jeder Knoten mit
# Gtk.Widget.get_css_name() abgefragt - Popover der Auswahlfelder,
# Bildlaufleisten und Fensterrahmen eingeschlossen.
#
# Vollstaendig, und deshalb ist die Liste eine Zusicherung und keine
# Bequemlichkeit: was hier fehlt, gibt es in dieser Maske nicht.
REGREET_NODES = frozenset({
    "arrow", "box", "button", "cellview", "combobox", "contents", "entry",
    "frame", "grid", "headerbar", "image", "infobar", "label", "modelbutton",
    "none", "overlay", "picture", "popover", "range", "revealer", "scrollbar",
    "scrolledwindow", "slider", "stack", "text", "trough", "viewport",
    "window", "windowcontrols", "windowhandle",
})


def _selectors(css: str) -> list[str]:
    """Die Selektoren des Blattes, ohne Kommentare und ohne Rumpf."""
    return [part.strip()
            for block in re.findall(r"([^{}]+)\{[^{}]*\}", _code(css))
            for part in block.split(",")
            if part.strip() and not part.strip().startswith("@")]


@pytest.mark.parametrize("name", THEMES)
def test_every_element_selector_names_a_node_that_exists(greeter, name):
    """Der Fehler, der `passwordentry` drei Tage lang hat mitlaufen lassen.

    Im Blatt stand `entry, combobox button, passwordentry {...}`, und
    `passwordentry` hat nie etwas getroffen: eine GtkPasswordEntry heisst
    im Knotenbaum `entry` und traegt die Klasse `password`. GEMESSEN am
    13.08.2026 ueber get_css_name() an einem echten GTK 4.22.4.

    Es ist die leiseste Sorte Fehler, die dieses Projekt kennt - genau
    die, die der Kopf von greeter._surfaces() fuer eine CSS-Regel auf dem
    Fensterhintergrund beschreibt. Der Selektor sah aus wie der Name des
    Widgets, GTK meldet dazu NICHTS (ein unbekannter Knotenname ist
    gueltiges CSS, er passt nur nie), und das Feld war zufaellig trotzdem
    richtig gefaerbt, weil `entry` daneben stand.

    Ohne diese Zusicherung merkt das niemand, bis jemand die Regel teilt.
    """
    unknown = {}
    for selector in _selectors(greeter.stylesheet(theme.palette(name))):
        for element in re.findall(r"(?:^|[\s>+~])([a-zA-Z][a-zA-Z0-9-]*)",
                                  selector):
            if element not in REGREET_NODES:
                unknown.setdefault(element, selector)

    assert unknown == {}, (
        "diese Selektoren nennen Knoten, die es in regreets Maske nicht "
        "gibt - sie treffen nie etwas und GTK sagt darueber kein Wort: "
        + "; ".join(f"{element!r} in {selector!r}"
                    for element, selector in sorted(unknown.items())))


@pytest.mark.parametrize("name", THEMES)
def test_every_ground_under_a_button_switches_the_gradient_off(greeter, name):
    """Der Fehler, der die Felder grau gelassen hat, obwohl alles stimmte.

    GTKs eigenes Adwaita malt jeden Knopf mit einem background-IMAGE -
    einem Verlauf -, und ein Bild liegt ueber der Farbe. Eine Regel, die
    nur `background-color` setzt, gewinnt die Kaskade und aendert
    trotzdem nichts.

    GEMESSEN am 13.08.2026 mit tests/render/greeter_shot.py, zwei Laeufe,
    die sich in genau einer Zeile unterschieden:

        `background-image: none` dazu     -> #0D3D47   die Marke
        stattdessen Selektor `button.combo` -> #393939 unveraendert

    Also nicht der Selektor, sondern die fehlende Zeile - und sie fehlte
    NUR dort. Bei suggested-action und destructive-action stand sie von
    Anfang an, weil sie dort beim ersten Versuch aufgefallen war.

    GEPRUEFT WIRD DIE REGEL, DIE JEDEN KNOPF ERREICHT, und nicht jede
    einzelne, die einen Grund setzt. Der Unterschied ist gemessen und
    nicht theoretisch: dieser Test hat beim ersten Lauf drei
    :hover-Regeln angezeigt, die KEINEN Fehler haben -
    `button.suggested-action:hover` setzt nur die Farbe, und das
    background-image: none seiner Grundregel gilt weiter, weil beide
    Regeln zugleich passen. Eine Zusicherung, die das anzeigt, zwingt
    dieselbe Zeile viermal ins Blatt und erklaert nichts.

    Der Zustand, der WIRKLICH schuetzt, ist: es gibt eine Regel, die
    JEDEN Knopf der Maske trifft - der blosse Knoten `button` - und
    genau die schaltet den Verlauf ab. Dann kann keine spaetere Farbe
    mehr unter einem Bild verschwinden, egal auf welchem Selektor sie
    steht. Am 12.08.2026 war es andersherum: `button` setzte nur Ecke
    und Polster, und die zwei Sonderregeln kannten die Zeile - der
    Feldknopf dazwischen nicht.
    """
    css = greeter.stylesheet(theme.palette(name))
    reaches_every_button = []
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", _code(css)):
        if selector.strip().startswith("@"):
            continue
        parts = [part.strip() for part in selector.split(",")]
        if "button" not in parts:
            continue
        reaches_every_button.append((selector.strip(), body))

    assert reaches_every_button, (
        "keine Regel im Blatt trifft den blossen Knoten `button`. Ohne "
        "sie steht jeder Knopf, den keine Sonderregel kennt, in Adwaitas "
        "Grau - und das war am 12.08.2026 der Stiftknopf neben jedem Feld")

    without = [selector for selector, body in reaches_every_button
               if not re.search(r"^\s*background-image\s*:", body, re.MULTILINE)]
    assert without == [], (
        "die Regel, die jeden Knopf erreicht, schaltet Adwaitas Verlauf "
        "nicht ab - jede Farbe darunter liegt dann unter einem Bild und "
        "niemand sieht sie: " + "; ".join(without))

    grounded = [selector for selector, body in reaches_every_button
                if re.search(r"^\s*background-color\s*:", body, re.MULTILINE)]
    assert grounded, (
        "die Regel, die jeden Knopf erreicht, gibt ihm keinen eigenen "
        "Grund - dann ist der Knopf zwar nicht mehr Adwaitas Verlauf, "
        "aber auch nicht die Marke")


@pytest.mark.parametrize("name", THEMES)
def test_no_rule_paints_a_label_that_belongs_to_a_button(greeter, name):
    """Der Fehler, der die ganze Kostenleiter unsichtbar gemacht hat.

    Ein Knopf traegt seinen Text in einem `label`. Eine Regel auf
    `label` schlaegt deshalb die Farbe, die der Knopf vererbt - und das
    Blatt hatte zwei davon, `label` und `frame.background label`, beide
    fuer die Beschriftungen NEBEN den Feldern gedacht.

    GEMESSEN am 13.08.2026 am Nachbau, Bildpunkte gezaehlt:

        "Login"      #A9C6CF auf #0096C0 = 1,91:1  unlesbar
        "Reboot"     105 Bildpunkte Weiss,  0 Gelb
        "Power Off"  142 Bildpunkte Weiss,  0 Rot

    Die drei Kostenstufen darunter waren also sorgfaeltig begruendet,
    einzeln gepruefte verschiedene Gruende - und keine davon war je zu
    sehen. Nach der Behebung: 95 Bildpunkte Gelb, 111 Rot, 0 Weiss.

    Die Zusicherung verlangt, dass jede Regel auf `label` an einem
    Elternteil haengt, der KEIN Knopf sein kann. `grid > label` erfuellt
    das (ein Knopf steckt nie direkt im Raster), ein blosses `label`
    nicht.
    """
    offenders = []
    for selector in _selectors(greeter.stylesheet(theme.palette(name))):
        parts = re.split(r"\s*>\s*|\s+", selector.strip())
        last = parts[-1].split(":")[0]
        if last != "label":
            continue
        # Der direkte Elternteil muss genannt und darf kein Knopf sein.
        if len(parts) < 2 or parts[-2].split(":")[0] not in {"grid", "infobar"}:
            offenders.append(selector)

    assert offenders == [], (
        "diese Regeln faerben ein Label, ohne zu sagen, in welchem "
        "Elternteil - sie treffen damit auch die Beschriftung jedes "
        "Knopfes und uebermalen die Kostenleiter: " + "; ".join(offenders))


def test_nothing_in_src_login_carries_a_colour_of_its_own(greeter):
    """Der Waechter, der src/login bis zum 13.08.2026 gar nicht gelesen hat.

    tests/src/test_brand.py klappert `src/styles/*.template` ab und
    dieses Modul den Quelltext von src/greeter.py. Dazwischen lag ein
    ganzes Verzeichnis, das keiner von beiden anfasst: src/login traegt
    vier Konfigurationsdateien und zwei Stylesheets, und eine harte Farbe
    darin haette niemand gemeldet.

    Die Unterscheidung, auf die es dabei ankommt: die
    zepos-greeter-<thema>.css SOLLEN Hexwerte tragen - sie sind erzeugt,
    das ist ihr Zweck, und test_the_shipped_stylesheet_is_what_the_module
    _builds haelt sie Byte fuer Byte an ihrem Erzeuger fest. Alles
    ANDERE in diesem Verzeichnis ist von Hand geschrieben und darf keine
    Farbe kennen.

    Deshalb prueft dieser Waechter zwei Dinge auf einmal:
      * kein .css hier, das nicht aus greeter.stylesheet() faellt. Sonst
        waere die Luecke mit einer einzigen `cp` wieder offen.
      * keine Farbe in irgendeiner anderen Datei.
    """
    generated = {greeter.filename(name) for name in THEMES}

    stray = sorted(path.name for path in LOGIN.glob("*.css")
                   if path.name not in generated)
    assert stray == [], (
        "in src/login liegen Stylesheets, die niemand erzeugt - sie "
        "gehen an jeder Zusicherung dieses Moduls vorbei und ein "
        f"Themenwechsel erreicht sie nie: {stray}")

    offenders = {}
    for path in sorted(LOGIN.iterdir()):
        if not path.is_file() or path.name in generated:
            continue
        found = re.findall(r"#[0-9a-fA-F]{3,8}\b",
                           _code(path.read_text(encoding="utf-8")))
        if found:
            offenders[path.name] = found

    assert offenders == {}, (
        "diese Dateien in src/login tragen eine Farbe selbst, statt sie "
        "aus theme.py zu nehmen - ein Themenwechsel laesst sie stehen: "
        + "; ".join(f"{name}: {values}"
                    for name, values in offenders.items()))


@pytest.mark.parametrize("name", THEMES)
def test_the_three_cost_levels_are_three_different_grounds(greeter, name):
    """Sicher, Neustart, Ausschalten - und nicht zweimal dasselbe Rot.

    regreet gibt beiden Endknoepfen die Klasse "destructive-action"
    (src/gui/templates.rs, `EndButton`), also sind sie in seiner Vorgabe
    ununterscheidbar. Das ist der Zustand auf dem Messbild, und es ist
    die eine Sache an dieser Maske, die nicht nur haesslich, sondern
    falsch ist: ein Neustart und ein Ausschalten kosten nicht dasselbe.

    Geprueft wird, dass die drei Gruende WIRKLICH verschieden sind - drei
    Regeln, die alle dieselbe Farbe setzen, waeren dieselbe Leiter auf
    dem Papier und keine auf dem Schirm.
    """
    palette = theme.palette(name)
    css = greeter.stylesheet(palette)
    grounds = {
        "sicher": palette.CYAN,
        "neustart": palette.STATE_WARNING_BG,
        "ausschalten": palette.STATE_CRITICAL_BG,
    }
    assert len(set(grounds.values())) == 3, (
        "zwei der drei Kostenstufen haben denselben Grund")
    for name, colour in grounds.items():
        assert colour in css, f"die Stufe {name} kommt im Blatt nicht vor"

    # Und sie kommen aus derselben Mitte wie zepos-logout, statt hier neu
    # gewaehlt zu sein. Ohne diese Zeile koennte die Anmeldung ein
    # anderes Gelb benutzen als die Abmeldung, und beide waeren "auf der
    # Marke".
    #
    # Gegen das AUSGELIEFERTE Thema, denn style_definition liest das
    # eingestellte aus /etc/zepos/theme und in einem Testlauf steht dort
    # nichts. Genau das ist hier die richtige Probe: der Abmeldedialog
    # und die Anmeldemaske muessen im SELBEN Thema dieselben Gruende
    # haben, und das ausgelieferte ist das, in dem beide gemessen sind.
    if name == theme.DEFAULT:
        from src import style_definition
        assert style_definition.STYLE_VARIABLES["STYLE_LOGOUT_RESTART_BG"] == \
            palette.STATE_WARNING_BG
        assert style_definition.STYLE_VARIABLES["STYLE_LOGOUT_POWEROFF_BG"] == \
            palette.STATE_CRITICAL_BG


# --------------------------------------------------------------------
# Die Kette: Skript -> Datei -> Paket
# --------------------------------------------------------------------

def test_the_greeter_hands_the_stylesheet_to_regreet():
    """Ohne --style laedt regreet /etc/greetd/regreet.css.

    Das ist seine eingebaute Vorgabe (CSS_PATH in src/constants.rs des
    Tags 0.5.0), ZepOS legt dort nichts ab, und component.rs laedt nur,
    `if input.css_path.exists()`. Die Maske bliebe also grau, und zwar
    ohne Meldung - regreet sagt "Loading custom CSS" nur auf debug und
    sagt gar nichts, wenn die Datei fehlt.

    Gegen den Code ohne Kommentare, weil der Kopf des Skripts den
    Schalter erklaert und eine Textsuche von der Erklaerung wahr wird.
    """
    code = _code(GREETER.read_text(encoding="utf-8"))
    assert "--style" in code, "zepos-greeter reicht regreet kein Stylesheet"
    assert f"{ETC}/zepos-greeter-" in code, (
        f"zepos-greeter zeigt nicht nach {ETC}")

    # Und der Pfad wird auch WEITERGEREICHT und nicht nur zugewiesen. Eine
    # Variable, die gesetzt und nie benutzt wird, sieht in beiden Haelften
    # richtig aus - nachgewiesen mit genau dieser Mutation.
    assert re.search(r'--style "\$\d"', code), (
        "der Pfad steht in einer Variablen und kommt nicht bei regreet an")


def test_the_greeter_reads_the_machine_theme_and_falls_back():
    """Der ganze Umschaltmechanismus der Anmeldemaske, in einem Skript.

    DREI DINGE, UND JEDES EINZELNE IST EIN AUSFALL, WENN ES FEHLT
      * es liest ueberhaupt /etc/zepos/theme. Ohne das ist die Maske
        auf das ausgelieferte Thema genagelt und die Forderung vom
        12.08.2026 unerfuellt.
      * es faellt auf das ausgelieferte Thema zurueck. Ein Tippfehler
        in einer Datei unter /etc darf keine Maschine sein, in die
        niemand mehr hineinkommt.
      * der Rueckfallname ist der, den src/theme.py wirklich
        ausliefert. Steht dort etwas anderes, greift der Rueckfall ins
        Leere und die Maske bleibt grau.
    """
    code = _code(GREETER.read_text(encoding="utf-8"))
    assert "/etc/zepos/theme" in code, (
        "zepos-greeter liest das Thema der Maschine nicht - die "
        "Anmeldemaske haengt dann auf dem ausgelieferten fest")
    assert f'"{theme.DEFAULT}"' in code, (
        f"der Rueckfall des Greeters nennt nicht {theme.DEFAULT!r}, das "
        f"Thema, das src/theme.py ausliefert")
    assert re.search(r"if \[\[ ! -r \"\$REGREET_STYLE\" \]\]", code), (
        "zepos-greeter prueft nicht, ob es das Blatt des eingestellten "
        "Themas ueberhaupt gibt")


@pytest.mark.parametrize("name", THEMES)
def test_the_package_installs_the_stylesheet_where_the_greeter_looks(name):
    """Die zwei Haelften, die einander nicht pruefen koennen.

    Das Skript setzt einen Pfad aus einem Namen zusammen, das Rezept
    legt an Pfaden ab. Sind es verschiedene, meldet das niemand: ein
    fehlendes Stylesheet kostet die Farben und nicht die Anmeldung, also
    faellt es erst jemandem auf, der hinsieht.
    """
    recipe = RECIPE.read_text(encoding="utf-8")
    assert f"login/{shipped(name).name}" in recipe, (
        f"zepos-config legt {shipped(name).name} nicht nach {ETC}")
    assert f'"$pkgdir{ETC}"' in recipe or f'"$pkgdir{installed(name)}"' in recipe, (
        f"zepos-config legt die Blaetter nicht nach {ETC}")

    # Und sie ueberleben eine Aktualisierung, wie die zwei Nachbardateien
    # unter /etc auch. Ohne backup= wirft das naechste `pacman -Syu` jede
    # Anpassung wortlos weg.
    backup = re.search(r"^backup=\((.*?)^\)", recipe, re.S | re.M)
    assert backup and f"'{installed(name).lstrip('/')}'" in backup.group(1), (
        f"{installed(name)} steht nicht in backup=")


def test_the_stylesheet_is_not_a_path_another_package_owns():
    """greetd-regreet 0.5.0 besitzt /etc/greetd/regreet.css als seine
    eingebaute Vorgabe.

    Dieselbe Regel und dieselbe Begruendung wie fuer zepos.toml und
    zepos-regreet.toml: zwei Pakete auf einem Pfad sind in pacman ein
    Dateikonflikt, und der bricht die Installation ab, statt sie nur zu
    verfaerben.
    """
    recipe = RECIPE.read_text(encoding="utf-8")
    assert '"$pkgdir/etc/greetd/regreet.css"' not in recipe, (
        "zepos-config beansprucht /etc/greetd/regreet.css - das ist "
        "regreets eigene Vorgabe")


def test_the_two_configurable_strings_are_both_german():
    """Was sich an dieser Maske uebersetzen LAESST, ist uebersetzt.

    Gemessen an regreet 0.5.0: von allen Zeichenketten der Oberflaeche
    sind genau zwei einstellbar - `[appearance] greeting_msg` und
    `[widget.clock] locale`. Alles andere ("User:", "Session:", "Cancel",
    "Login", "Reboot", "Power Off" und die zwei Hinweisfaehnchen) steht in
    src/gui/templates.rs als gewoehnliche Rust-Zeichenkette, und in den
    1183 Zeilen GUI-Quelltext des Tags gibt es NULL Aufrufe von gettext
    oder einer anderen Uebersetzungsfunktion. Es gibt keinen Katalog.

    Die Uhr ist der Fall, der ohne Messung als unloesbar durchgegangen
    waere: sie stand auf "Tue 20:09", was nach glibc-Locale aussieht und
    keines ist - chrono traegt seine Sprachdaten ueber
    pure-rust-locales einkompiliert, also wirkt diese Zeile auch auf
    einem System ohne erzeugtes de_DE.UTF-8.
    """
    toml = REGREET_TOML.read_text(encoding="utf-8")
    code = _code(toml)
    assert re.search(r'^greeting_msg\s*=\s*"Willkommen bei ZepOS"\s*$',
                     code, re.M)
    assert "[widget.clock]" in code, (
        "die Uhr hat keinen Abschnitt und faellt damit auf en_US zurueck")
    assert re.search(r'^locale\s*=\s*"de_DE"\s*$', code, re.M), (
        "die Uhr der Anmeldung zeigt englische Wochentage")


# --------------------------------------------------------------------
# Und jetzt liest GTK selbst
# --------------------------------------------------------------------

_PARSE_PROBE = """
import sys, gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk
errors = []
provider = Gtk.CssProvider()
provider.connect("parsing-error",
                 lambda p, section, error: errors.append(
                     f"{section.to_string()}: {error.message}"))
provider.load_from_path(sys.argv[1])
print(len(errors))
for message in errors:
    print(message)
"""


def _parse_with_gtk(path: Path) -> list[str]:
    """Die Datei durch GTKs eigenen CSS-Parser, in einem Kind.

    In einem KIND, aus demselben Grund, den tests/gtk4_headless.py in
    voller Laenge aufschreibt: GTK4 in den pytest-Prozess zu laden ist
    ein Risiko, das die ganze Sitzung ohne Bericht beenden kann.

    Eine Anzeige braucht es hier nicht - ein GtkCssProvider parst ohne
    einen Bildschirm, und genau deshalb kann diese Pruefung ohne
    broadwayd auskommen.
    """
    found = gtk4_headless.gi_interpreter({"Gtk": "4.0"})
    if not found:
        pytest.skip("kein Python auf dieser Maschine kann GTK4 laden")
    executable, extra = found
    environment = {"PATH": "", "GDK_BACKEND": "broadway"}
    if extra:
        environment["PYTHONPATH"] = ":".join(extra)
    result = subprocess.run(
        [executable, "-c", _PARSE_PROBE, str(path)],
        env=environment, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, (
        f"der Parser-Lauf ist gescheitert:\n{result.stdout}\n{result.stderr}")
    lines = result.stdout.strip().splitlines()
    return lines[1:1 + int(lines[0])]


@pytest.mark.allow_subprocess
@pytest.mark.parametrize("name", THEMES)
def test_gtk_reads_the_stylesheet_without_a_single_error(name):
    """Der Beleg, dass das Blatt WIRKLICH greift.

    GtkCssProvider verwirft eine Regel, die es nicht versteht, meldet das
    ueber das Signal "parsing-error" - und regreet haengt an diesem
    Signal nicht. Ein Tippfehler hier ist also kein Fehler, den irgendwer
    zu sehen bekommt, sondern eine Maske, die teilweise grau bleibt.
    Genau diese Sorte Fehler hat wofis Stylesheet einmal 39 Mal gehabt,
    ohne dass es jemandem auffiel (tests/src/test_brand.py).

    Gemessen gegen GTK 4.22.4, die Fassung aus dem angehefteten
    Schnappschuss: 0 Fehler.
    """
    errors = _parse_with_gtk(shipped(name))
    assert errors == [], (
        f"GTK meldet {len(errors)} Parse-Fehler und verwirft die "
        f"betroffenen Regeln lautlos:\n" + "\n".join(errors))


@pytest.mark.allow_subprocess
def test_the_parser_check_would_notice_a_broken_rule(tmp_path):
    """Die Gegenprobe, ohne die die Pruefung darueber nichts wert ist.

    Ein Testlauf, der 0 Fehler meldet, weil er gar nicht misst, sieht
    genauso aus wie einer, der 0 Fehler meldet, weil das Blatt sauber
    ist. Hier wird ein Fehler ABSICHTLICH eingebaut, und die Pruefung
    muss ihn finden.
    """
    broken = tmp_path / "kaputt.css"
    broken.write_text("window { background-color: rgb(nicht-eine-farbe); }\n",
                      encoding="utf-8")
    assert _parse_with_gtk(broken), (
        "der Parser meldet auch eine kaputte Regel nicht - die Pruefung "
        "darueber misst nichts")
