# SPDX-License-Identifier: GPL-3.0-or-later
"""Glas: was durchscheint, was unscharf wird, und was noch lesbar ist.

WAS GEMELDET WURDE
    Der Nutzer am 11.08.2026: "vlt. muessen wir das os auch ein bisschen
    umstylen damit wir diesen glasmorphism effekt haben koennen".

WAS GEMESSEN WURDE
    `grep -rn layerrule src/` fand am selben Tag KEINE EINZIGE Zeile,
    waehrend decoration:blur in hyprland-universal-config.template seit
    jeher auf `enabled = true` steht. Die Unschaerfe war also an - und
    galt fuer FENSTER. Eine Layer-Shell-Flaeche bekommt sie nur ueber
    eine eigene `layerrule`, angesprochen ueber den Namensraum, unter
    dem die Flaeche sich anmeldet. Die Leiste, das Dock, der
    Benachrichtigungsdienst und die elf Ueberlagerungen hatten sie nie.

    Ein durchsichtiger Hintergrund OHNE Unschaerfe ist kein Glas,
    sondern ein Loch: man sieht die Tapete scharf hindurch.

DIE DREI DINGE, DIE DIESE DATEI BEWACHT
    1. Jede Flaeche, die dieses Projekt anmeldet, hat ihre beiden
       Regeln - blur und ignorealpha. Geprueft gegen die VORLAGEN und
       nicht gegen eine Liste, damit eine vierzehnte Flaeche nicht
       lautlos ohne Glas bleibt.
    2. Die Schwelle von ignorealpha liegt zwischen "nichts" und der
       duennsten Glasschicht. Darunter verwischt der Compositor den
       leeren Rand um die Platte, darueber hoert er auf, die Platte
       selbst zu verwischen.
    3. Der Text bleibt lesbar - im SCHLECHTESTEN Fall, also unter der
       hellsten denkbaren Tapete. Das ist der Punkt, an dem die meisten
       Glaseffekte scheitern, und der einzige, den man ausrechnen kann.

WAS SIE NICHT PRUEFT
    Ob es gut AUSSIEHT. Das kann nur ein Mensch, und der hat es
    bestellt.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src import brand
# Auf Modulebene und nicht in der Pruefung, aus demselben Grund wie in
# tests/src/test_spacing.py: der Isolationswaechter aus tests/conftest.py
# verbietet waehrend eines Tests jedes Schreiben ausserhalb von tmp_path,
# wozu auch das __pycache__ des ersten Imports zaehlt.
from tests.src import test_sizes

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
HYPRLAND = SRC / "templates" / "hyprland-universal-config.template"

# WCAG 2.1: 4.5:1 fuer Fliesstext, 3:1 fuer die Umrisse von Bedienelementen.
# Dieselben Zahlen, mit denen src/brand.py seine ganze Palette begruendet.
TEXT_CONTRAST = 4.5

# Die zwei denkbaren Extreme einer Tapete. Kein Grauwert und kein
# "typisches" Hintergrundbild: unter Glas ist der Grund das, was der
# Nutzer eingestellt hat, und die Rechnung darf nicht davon abhaengen,
# dass er etwas Bestimmtes gewaehlt hat.
#
# WARUM ES SEIT DEM 12.08.2026 ZWEI SIND
#     Hier stand nur BRIGHTEST_WALLPAPER, mit der Begruendung "fuer
#     helle Schrift ist das die hellste denkbare Tapete". Der Satz ist
#     richtig UND enthaelt seine eigene Voraussetzung: er gilt fuer
#     HELLE Schrift. Seit es ein zweites, helles Thema gibt, ist die
#     Schrift dunkel, und der schlechteste Fall ist dann die dunkelste
#     Tapete - genau andersherum.
#
#     Beide zu rechnen ist deshalb keine Anpassung an das neue Thema,
#     sondern die Beseitigung einer stillen Annahme: die Pruefung war
#     fuer die Haelfte aller denkbaren Paletten blind, und man konnte
#     es ihr nicht ansehen.
EXTREME_WALLPAPERS = {
    "weiss": (255, 255, 255),
    "schwarz": (0, 0, 0),
}


def _flat(name: str):
    """Ein Modul aus src/, das selbst flach importiert - siehe
    tests/src/test_greeter.py fuer die Begruendung."""
    import importlib
    import sys

    sys.path.insert(0, str(SRC))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(SRC))


_theme = _flat("theme")


@pytest.fixture(params=sorted(_theme.THEMES))
def palette(request):
    """Jedes Thema durch dieselbe Glasrechnung.

    Die Deckkraefte gehoeren dem Thema (src/theme.py fuehrt aus, warum
    eine Deckkraft hier eine Farbentscheidung ist), also muss jedes
    Thema seine eigene Rechnung bestehen.
    """
    return _theme.palette(request.param)


@pytest.fixture
def processor(monkeypatch):
    """Der Prozessor, so importiert, wie der Generator ihn importiert."""
    monkeypatch.syspath_prepend(str(SRC))
    import template_processor
    return template_processor


def _channels(colour: str) -> tuple[float, float, float]:
    value = colour.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def _luminance(rgb) -> float:
    """Relative Leuchtdichte nach WCAG 2.1."""
    def channel(raw: float) -> float:
        share = raw / 255.0
        return (share / 12.92 if share <= 0.04045
                else ((share + 0.055) / 1.055) ** 2.4)
    red, green, blue = (channel(part) for part in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(one, other) -> float:
    first, second = _luminance(one), _luminance(other)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def _over(top, alpha: float, bottom):
    """Was man sieht, wenn `top` mit `alpha` auf `bottom` liegt."""
    return tuple(alpha * top[index] + (1 - alpha) * bottom[index]
                 for index in range(3))


# --------------------------------------------------------------------
# Jede Flaeche bekommt ihre Regel
# --------------------------------------------------------------------

# Die Baeume, in denen dieses Projekt Fenster anmeldet. Vier Sprachen,
# und das ist der Punkt.
#
# WARUM DIESE LISTE AM 12.08.2026 VON EINEM AUF FUENF EINTRAEGE GEWACHSEN IST
#     Vorher las diese Datei ausschliesslich `src/templates/ags-*.template`.
#     Das war nicht streng, sondern BLIND, und es sagte nichts: vier
#     Flaechen melden sich woanders an -
#
#         hyprlaunch          plugins/hyprlaunch/src/LauncherRenderer.cpp
#         clipboard-manager   plugins/hyprclipx/src/ClipboardRenderer.cpp
#         zepos-menu          menu/zepos_menu/window.py
#         zepos-logout        logout/zepos-logout.c
#
#     und alle vier fehlten deshalb in GLASS_LAYERS, ohne dass ein Test
#     etwas gemerkt haette. Eine Pruefung, die nur eine Sprache liest,
#     erzeugt genau den Fehler, gegen den sie geschrieben ist.
#
# tests/ steht ABSICHTLICH nicht darin: tests/lock/fake_lock_layer_shell.c
# meldet einen erfundenen Namensraum an, um zu beweisen, dass der
# Sperrbildschirm einen zweiten Client abweist. Ein Testhilfsmittel ist
# kein Fenster dieses Systems.
NAMESPACE_ROOTS = ("src/templates", "plugins", "menu", "logout", "lock")

# Eine Zeile, die einen Namensraum anmeldet - in jeder der vier
# Sprachen dieselbe Form: der Name steht als LETZTES Argument.
#
#     gtk_layer_set_namespace(GTK_WINDOW(m_window), "hyprlaunch")   C/C++
#     LayerShell.set_namespace(self, LAYER_NAMESPACE)               Python
_SET_NAMESPACE = re.compile(r"set_namespace\s*\(\s*(?:[^(),]|\([^()]*\))+,"
                            r"\s*([^,()]+?)\s*\)")

# Wie eine Konstante in denselben Dateien geschrieben wird.
_CONSTANTS = (
    re.compile(r'#\s*define\s+(\w+)\s+"([^"]+)"'),   # C und C++
    re.compile(r'^(\w+)\s*=\s*"([^"]+)"', re.M),     # Python
)


def _namespace_sources(root: Path):
    """Jede Quelldatei, die eine Flaeche anmelden koennte."""
    for relative in NAMESPACE_ROOTS:
        directory = root / relative
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if path.suffix in (".c", ".cpp", ".py", ".template"):
                yield path


def _declared_namespaces(root: Path = SRC.parent) -> dict[str, str]:
    """Jeder Layer-Shell-Namensraum dieses Projekts: Name -> woher.

    Aus den QUELLEN gelesen und nicht aus einer Liste. Eine Liste gegen
    eine Liste zu halten pruefte nur, dass jemand zweimal dasselbe
    getippt hat.

    In den AGS-Vorlagen kommen drei Schreibweisen vor, und alle drei
    muessen erkannt werden:
      namespace: "notifications"   direkt
      namespace: WINDOW_NAME       ueber eine Konstante derselben Datei
      namespace: config.name       die Fabrik in ags-overlay-utils, die
                                   ihren Namen vom Aufrufer bekommt

    Die anderen drei Sprachen rufen alle set_namespace() auf und
    schreiben den Namen entweder direkt hin oder ueber eine Konstante
    derselben Datei. Aufgeloest wird nur DIESE zweite Form: ein Name,
    der aus einer anderen Datei kaeme, waere geraten, und ein geratener
    Namensraum ist genau der Fehler, den hyprclipx bereithaelt - es
    meldet sich als "clipboard-manager" an und nicht als "hyprclipx".

    `root` ist ein Parameter, damit
    test_the_namespace_scan_finds_a_window_planted_in_each_language dem
    Sucher einen Fund hinlegen kann. Ein sauberer Baum gibt einem Sucher
    nichts zu finden, und dann besteht auch einer die Pruefung, der per
    Konstruktion nichts finden KANN.
    """
    found: dict[str, str] = {}
    for path in _namespace_sources(root):
        text = path.read_text(encoding="utf-8", errors="replace")

        constants: dict[str, str] = {}
        for pattern in _CONSTANTS:
            constants.update(dict(pattern.findall(text)))

        for argument in _SET_NAMESPACE.findall(text):
            if argument.startswith('"') and argument.endswith('"'):
                found[argument.strip('"')] = path.name
            elif argument in constants:
                found[constants[argument]] = path.name

        if path.suffix != ".template":
            continue
        if "namespace:" not in text and "createOverlayWindow({" not in text:
            continue

        for literal in re.findall(r'namespace:\s*"([^"]+)"', text):
            found[literal] = path.name

        if re.search(r"namespace:\s*WINDOW_NAME", text):
            for name in re.findall(r'WINDOW_NAME\s*=\s*"([^"]+)"', text):
                found[name] = path.name

        # Die Fabrik selbst meldet nichts an - ihre AUFRUFER tun es.
        for call in re.findall(r"createOverlayWindow\(\{(.*?)\}\)", text,
                               re.DOTALL):
            match = re.search(r'name:\s*"([^"]+)"', call)
            if match:
                found[match.group(1)] = path.name
                continue
            if re.search(r"name:\s*WINDOW_NAME", call):
                for name in re.findall(r'WINDOW_NAME\s*=\s*"([^"]+)"', text):
                    found[name] = path.name
    return found


# Vier Sprachen, vier Schreibweisen, ein hingelegter Fund je Sprache.
# Der Text ist so knapp wie moeglich und trotzdem echt: jede Zeile ist
# die Form, in der die entsprechende Datei dieses Baums wirklich
# schreibt.
PLANTED_WINDOWS = {
    "src/templates/ags-erfunden.template":
        ('const WINDOW_NAME = "vorlage-fund"\n'
         'new Astal.Window({ namespace: WINDOW_NAME })\n'),
    "plugins/erfunden/src/Renderer.cpp":
        ('gtk_layer_set_namespace(GTK_WINDOW(m_window), "cpp-fund");\n'),
    "logout/erfunden.c":
        ('#define ERFUNDEN_NAMESPACE "c-fund"\n'
         'gtk_layer_set_namespace(GTK_WINDOW(window), ERFUNDEN_NAMESPACE);\n'),
    "menu/erfunden/fenster.py":
        ('LAYER_NAMESPACE = "python-fund"\n'
         '        LayerShell.set_namespace(self, LAYER_NAMESPACE)\n'),
}


def test_the_namespace_scan_finds_a_window_planted_in_each_language(tmp_path):
    """Dem Sucher wird ein Fund HINGELEGT, in jeder der vier Sprachen.

    WARUM DIESE PRUEFUNG UEBERHAUPT EXISTIERT
        Weil ein sauberer Baum einem Sucher nichts zu finden gibt und
        deshalb auch einen bestehen laesst, der per Konstruktion nichts
        finden KANN. Genau das ist am 12.08.2026 hier passiert: ein
        Waechter gegen Radien neben der Leiter fand nie etwas, weil sein
        Muster geschweifte Klammern ausschloss, und die Mutations-
        pruefung merkte es nicht.

        Und es ist nicht theoretisch: der Sucher, den diese Datei bis
        heute hatte, fand die vier C++-, C- und Python-Fenster nicht -
        derselbe Fehler, eine Sprache spaeter.
    """
    for relative, text in PLANTED_WINDOWS.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    found = _declared_namespaces(tmp_path)
    for expected in ("vorlage-fund", "cpp-fund", "c-fund", "python-fund"):
        assert expected in found, (
            f"der Sucher findet {expected!r} nicht - eine Flaeche in dieser "
            f"Sprache koennte ohne Glasregel bleiben, ohne dass etwas "
            f"davon faellt. Gefunden wurde: {sorted(found)}")


def test_the_four_windows_outside_the_ags_templates_are_really_found():
    """Und die vier echten stehen wirklich drin, mit ihren echten Namen.

    Der hingelegte Fund oben beweist, dass der Sucher jede der vier
    Schreibweisen LESEN kann. Diese Zeile beweist, dass er sie im
    wirklichen Baum auch ANTRIFFT - der Unterschied zwischen einem
    Muster, das funktioniert, und einem, das an der richtigen Stelle
    sucht.

    "clipboard-manager" steht hier ausgeschrieben, weil genau dieser
    Name die Falle ist: das Programm heisst hyprclipx, und eine
    layerrule auf "hyprclipx" greift lautlos nie.
    """
    declared = _declared_namespaces()
    for name in ("hyprlaunch", "clipboard-manager", "zepos-menu",
                 "zepos-logout"):
        assert name in declared, (
            f"{name} wird von keiner Quelle angemeldet, die dieser Sucher "
            f"liest")


def test_every_surface_this_project_opens_is_named_in_the_glass_list(
        monkeypatch, tmp_path):
    """Keine Flaeche ohne Glasregel, und keine Regel ohne Flaeche.

    Beide Richtungen, und beide haben einen Fehlermodus:

      fehlt eine Flaeche   sie bleibt scharf, und zwar lautlos. Nichts
                           an einem Fenster ohne layerrule sagt, dass
                           eines fehlt - es sieht nur billiger aus als
                           seine Geschwister.
      fehlt eine Flaeche   eine layerrule auf einen Namensraum, den
      nicht, dafuer eine   niemand anmeldet, ist eine Zeile
      Regel zuviel        Compositor-Konfiguration, die nie greift.
                           Genau der Zustand, in dem
                           MONITOR_HEIGHT_SCALES war.
    """
    test_sizes._no_compositor(monkeypatch)
    style = test_sizes._import_style(tmp_path, monkeypatch)

    declared = _declared_namespaces()
    listed = set(style.GLASS_LAYERS)

    # Die Fabrik selbst ist kein Fenster.
    missing = sorted(set(declared) - listed)
    assert missing == [], (
        "diese Flaechen melden einen Layer-Shell-Namensraum an und stehen "
        "nicht in GLASS_LAYERS - sie bekommen keine Unschaerfe: "
        + ", ".join(f"{name} ({declared[name]})" for name in missing))

    orphaned = sorted(listed - set(declared))
    assert orphaned == [], (
        "fuer diese Namensraeume wird eine layerrule erzeugt, und keine "
        "Vorlage meldet sie an: " + ", ".join(orphaned))


def test_the_generated_config_carries_both_rules_for_every_surface(
        processor, monkeypatch, tmp_path):
    """Zwei Zeilen je Flaeche, und beide werden gebraucht.

    `blur` schaltet die Unschaerfe fuer diese Flaeche ueberhaupt ein.
    `ignorealpha` nimmt die durchsichtigen Stellen davon aus - ohne sie
    verwischt der Compositor auch den Rand, den die Platte zum Schirm
    haelt, und um ihre runden Ecken steht ein weicher grauer Kasten.

    Geprueft an der ERZEUGTEN Datei und nicht am Platzhalter: ein Block,
    der gebaut wird und in keiner Datei ankommt, ist der Regler, an dem
    dieses Projekt schon einmal gescheitert ist.
    """
    test_sizes._no_compositor(monkeypatch)
    style = test_sizes._import_style(tmp_path / "stil", monkeypatch)

    out = tmp_path / "hyprland.conf"
    processor.ConfigProcessor(
        styles=dict(style.STYLE_VARIABLES)).apply_template(HYPRLAND, out)
    text = out.read_text(encoding="utf-8")

    assert "{{" not in text, (
        "in der erzeugten Hyprland-Konfiguration steht noch ein "
        "Platzhalter")

    # Die Syntax ist die von Hyprland 0.53+, und sie ist gemessen -
    # siehe _glass_layerrules() in src/style_definition.py fuer die
    # sieben Schreibweisen, die dafuer durch `Hyprland --verify-config`
    # gelaufen sind. Dass sie WIRKLICH gilt, prueft nicht diese Datei,
    # sondern tests/src/test_plugins.py mit ebenjenem Aufruf; hier steht
    # nur, dass jede Flaeche ihre beiden Zeilen bekommt.
    for namespace in style.GLASS_LAYERS:
        match = re.escape(f"match:namespace ^({namespace})$")
        assert re.search(f"layerrule = {match}, blur on", text), (
            f"{namespace} bekommt keine Unschaerfe")
        assert re.search(f"layerrule = {match}, ignore_alpha [0-9.]+", text), (
            f"{namespace} bekommt eine Unschaerfe, die auch ueber seine "
            "durchsichtigen Stellen laeuft")


# --------------------------------------------------------------------
# Und jede Flaeche malt auch wirklich durchsichtig
# --------------------------------------------------------------------
#
# DIE LUECKE ZWISCHEN DEN BEIDEN PRUEFUNGEN DARUEBER UND DIESEN HIER
#     Oben steht, dass jede Flaeche eine layerrule BEKOMMT. Damit ist
#     die halbe Aussage geprueft, und die andere Haelfte war bis zum
#     12.08.2026 vollstaendig ungeprueft: WOMIT die Flaeche sich malt.
#
#     Zwei Fehler passen in diese Luecke, und beide waren drin:
#
#       deckend, aber in GLASS_LAYERS
#           Der Compositor rechnet die Unschaerfe bei jedem Bild, und
#           niemand sieht sie. GEMESSEN am 12.08.2026: von dreizehn
#           Flaechen malte EINE durchsichtig (die Leiste). Die anderen
#           zwoelf standen auf `background: $bg` mit $bg = INK - ein
#           sechsstelliges Hex ohne Alphakanal.
#
#       durchsichtig, aber nicht in GLASS_LAYERS
#           Kein Glas, sondern ein Loch: man sieht die Tapete oder die
#           Sitzung SCHARF hindurch, und das sieht billig aus statt
#           edel. GEMESSEN: zepos-logout stand seit jeher auf neun
#           Zehnteln und in keiner Regel.
#
# WARUM AN DER ERZEUGTEN DATEI UND NICHT AM PLATZHALTER
#     Weil `{{STYLE_GLASS_SOLO}}` in einer Vorlage nichts darueber sagt,
#     ob der Wert dahinter einen Alphakanal HAT. Gelesen wird die Zeile,
#     die GTK4 wirklich bekommt.

_CSS_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_CSS_LINE_COMMENT = re.compile(r"^\s*//.*$", re.MULTILINE)

# Ein deckender Grund ist alles mit Alpha 1. Die Zahl steht hier als
# Name, weil sie in drei Meldungen vorkommt und weil "1.0" in einer
# Bedingung nicht sagt, was gemeint ist.
OPAQUE = 1.0


def _stylesheet(style, relative: str) -> str:
    """Eine Stilvorlage, so wie GTK4 sie am Ende liest.

    Ohne Kommentare, und das ist nicht Kosmetik: die Vorlagen dieses
    Baums ERKLAEREN, was sie nicht mehr tun, und mehrere Erklaerungen
    zitieren dabei die Zeile, die gegangen ist - `background: $bg` steht
    woertlich im Kopf von .overlay-outer. Ein Leser, der Erklaerung und
    Regel nicht unterscheidet, liest die alte Fassung.
    """
    text = (SRC / relative).read_text(encoding="utf-8")
    text = _CSS_LINE_COMMENT.sub("", _CSS_BLOCK_COMMENT.sub("", text))
    for name, value in style.STYLE_VARIABLES.items():
        text = text.replace("{{" + name + "}}", str(value))
    return text


def _scss_variables(text: str) -> dict[str, str]:
    """Die `$name: wert;`-Zeilen im Kopf von ags-style.template."""
    return dict(re.findall(r"^\$([\w-]+):\s*([^;]+);", text, re.M))


def _rule_body(text: str, selector: str):
    """Der Rumpf EINER Regel, ueber die Klammern gezaehlt.

    Gezaehlt und nicht bis zur naechsten schliessenden Klammer gelesen,
    weil ags-style.template SCSS ist und schachtelt.
    """
    start = re.search(rf"^{re.escape(selector)}\s*\{{", text, re.M)
    if not start:
        return None
    depth = 0
    for index in range(start.end() - 1, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start.end():index]
    return None


def _own_background(body: str):
    """Der Hintergrund DIESER Regel, nicht der einer geschachtelten.

    Nur die erste Ebene: alles innerhalb einer inneren `{...}` gehoert
    einem anderen Wahlausdruck. Ohne diese Trennung faende
    `.overlay-outer` den Hintergrund seines Kopfbereichs.
    """
    depth, flat = 0, []
    for character in body:
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
        elif depth == 0:
            flat.append(character)
    found = re.search(r"(?:^|;)\s*background(?:-color)?\s*:\s*([^;]+)",
                      "".join(flat), re.M)
    return found.group(1).strip() if found else None


def _colour(value: str, variables: dict[str, str]):
    """Eine CSS-Farbe als (Kanaele, Deckkraft), oder eine Ausnahme.

    Keine stille Vorgabe bei einer Schreibweise, die hier noch nicht
    vorkommt: eine Farbe, die als "wahrscheinlich deckend" durchginge,
    waere genau die Annahme, gegen die diese Datei geschrieben ist.
    """
    seen = set()
    while value.startswith("$"):
        name = value[1:]
        if name in seen:
            raise ValueError(f"$-Variable {name} zeigt im Kreis")
        seen.add(name)
        value = variables[name].strip()

    if value == "transparent":
        return (0, 0, 0), 0.0
    hexed = re.fullmatch(r"#([0-9a-fA-F]{6})", value)
    if hexed:
        return _channels(value), OPAQUE
    rgba = re.fullmatch(
        r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", value)
    if rgba:
        return (tuple(int(rgba.group(index)) for index in (1, 2, 3)),
                float(rgba.group(4)))
    raise ValueError(f"unbekannte Farbschreibweise: {value!r}")


def _plate(style, plate):
    """Die Platte einer Flaeche: (Kanaele, Deckkraft), an ihrer Zeile
    abgelesen."""
    text = _stylesheet(style, plate.stylesheet)
    body = _rule_body(text, plate.selector)
    assert body is not None, (
        f"GLASS_PLATES nennt {plate.selector} in {plate.stylesheet}, und "
        "dort gibt es diese Regel nicht - der Zeiger geht ins Leere und die "
        "Glaspruefung dieser Flaeche laeuft ins Nichts")
    raw = _own_background(body)
    assert raw is not None, (
        f"{plate.selector} in {plate.stylesheet} malt gar keinen "
        "Hintergrund - dann ist nicht entscheidbar, ob die Unschaerfe "
        "dahinter etwas zu tun hat")
    return _colour(raw, _scss_variables(text))


def _plates(monkeypatch, tmp_path, theme_name: str = None):
    """Die Stil-SSOT und jede Platte daraus, einmal ausgelesen.

    Mit `theme_name` ueber die MASCHINENDATEI und nicht durch
    Hineinschreiben in das Modul - genau dieser Weg ist die Umschaltung,
    die gemessen werden soll. Dieselbe Begruendung wie bei
    _variables_with() in tests/src/test_theme.py.
    """
    test_sizes._no_compositor(monkeypatch)
    if theme_name is not None:
        machine = tmp_path / "maschine"
        machine.mkdir(parents=True, exist_ok=True)
        (machine / "theme").write_text(f"{theme_name}\n", encoding="utf-8")
        monkeypatch.setenv("ZEPOS_MACHINE_ROOT", str(machine))
    style = test_sizes._import_style(tmp_path / "nutzer", monkeypatch)
    assert theme_name is None or style.THEME.name == theme_name, (
        f"die Umschaltung auf {theme_name} ist nicht angekommen - gemalt "
        f"wird mit {style.THEME.name}")
    return style, {name: _plate(style, plate)
                   for name, plate in style.GLASS_PLATES.items()}


def test_every_surface_that_asks_for_blur_really_paints_through(
        monkeypatch, tmp_path):
    """Ein Effekt, der gerechnet und nicht gesehen wird, ist der teuerste
    Fehler von beiden."""
    style, plates = _plates(monkeypatch, tmp_path)

    opaque = sorted(name for name in style.GLASS_LAYERS
                    if plates[name][1] >= OPAQUE)
    assert opaque == [], (
        "diese Flaechen fordern eine Unschaerfe an und malen dann deckend - "
        "der Compositor rechnet den Effekt bei jedem Bild, und niemand sieht "
        "ihn: " + ", ".join(
            f"{name} ({style.GLASS_PLATES[name].selector} in "
            f"{style.GLASS_PLATES[name].stylesheet})" for name in opaque))


def test_no_surface_paints_through_without_asking_for_blur(
        monkeypatch, tmp_path):
    """Die Gegenrichtung, und sie sieht schlimmer aus als gar kein Glas.

    Ohne Unschaerfe dahinter ist eine durchsichtige Flaeche kein Glas,
    sondern ein Loch: die Tapete oder die Sitzung steht SCHARF darin.
    """
    style, plates = _plates(monkeypatch, tmp_path)

    listed = set(style.GLASS_LAYERS)
    holes = sorted(name for name, (_, alpha) in plates.items()
                   if alpha < OPAQUE and name not in listed)
    assert holes == [], (
        "diese Flaechen lassen den Schreibtisch durch und bekommen keine "
        "Unschaerfe - man sieht ihn scharf hindurch: " + ", ".join(holes))


def test_every_surface_this_project_opens_has_a_plate(monkeypatch, tmp_path):
    """Und die Tabelle beschreibt wirklich JEDE Flaeche.

    Ohne diese Zeile waere die Pruefung darueber davon abhaengig, dass
    jemand einen Eintrag anlegt: eine neue Ueberlagerung ohne Eintrag
    stuende in keiner der beiden Listen und faende deshalb in beiden
    Richtungen nichts zu beanstanden.
    """
    style = test_sizes._import_style(tmp_path, monkeypatch)
    declared = _declared_namespaces()

    missing = sorted(set(declared) - set(style.GLASS_PLATES))
    assert missing == [], (
        "diese Flaechen melden einen Namensraum an, und GLASS_PLATES sagt "
        "nicht, wo sie sich malen - fuer sie ist die Glaspruefung blind: "
        + ", ".join(f"{name} ({declared[name]})" for name in missing))

    unknown = sorted(set(style.GLASS_PLATES) - set(declared))
    assert unknown == [], (
        "fuer diese Namen steht eine Platte in GLASS_PLATES, und keine "
        "Quelle meldet sie an: " + ", ".join(unknown))


def test_a_plate_that_carries_no_text_says_what_covers_it(monkeypatch,
                                                          tmp_path):
    """"Traegt keine Schrift" ist die bequemste Antwort - also muss sie
    belegt werden.

    Sonst schaltete ein leeres Tupel die ganze Kontrastrechnung der
    naechsten Flaeche ab, und niemand saehe es dem Eintrag an. Zwei
    Flaechen sagen es zu Recht, und beide nennen den Wahlausdruck, der
    zwischen ihrer Schrift und ihnen liegt; hier wird er nachgeschlagen.
    """
    style, _ = _plates(monkeypatch, tmp_path)

    for namespace, plate in style.GLASS_PLATES.items():
        if plate.text:
            assert plate.covered_by is None, (
                f"{namespace} nennt gelesene Schrift UND eine Deckung - "
                "eines von beidem ist falsch")
            continue

        assert plate.covered_by, (
            f"{namespace} traegt angeblich keine Schrift und sagt nicht, "
            "was stattdessen unter ihr liegt")
        text = _stylesheet(style, plate.stylesheet)
        body = _rule_body(text, plate.covered_by)
        assert body is not None, (
            f"{namespace} nennt {plate.covered_by} als Deckung, und diese "
            f"Regel gibt es in {plate.stylesheet} nicht")
        assert _own_background(body) is not None, (
            f"{plate.covered_by} deckt angeblich die Schrift von "
            f"{namespace} und malt selbst keinen Hintergrund")


# --------------------------------------------------------------------
# Und der Text darauf bleibt lesbar, im schlechtesten Fall
# --------------------------------------------------------------------

def _plate_contrast_cases(style, plates):
    """(Namensraum, Rolle, Platte) fuer jede Schrift auf jeder Platte."""
    for namespace, plate in sorted(style.GLASS_PLATES.items()):
        for role in plate.text:
            yield namespace, role, plates[namespace]


@pytest.mark.parametrize("theme_name", sorted(_theme.THEMES))
def test_the_text_on_every_glass_plate_survives_either_extreme_wallpaper(
        theme_name, monkeypatch, tmp_path):
    """Der Punkt, an dem die meisten Glaseffekte scheitern.

    Dieselbe Rechnung, die die Leiste seit dem 11.08.2026 besteht, jetzt
    fuer jede einschichtige Platte: Schrift auf Platte auf der hellsten
    UND der dunkelsten denkbaren Tapete, und der schlechtere der beiden
    Werte zaehlt. Ueber JEDES Thema, weil welches der beiden Extreme das
    schlechtere ist daran haengt, ob die Schrift hell oder dunkel ist.

    GEMESSEN am 12.08.2026, schlechtester Fall, ZeptronIT / Tageslicht:

        Nebentext auf der Ueberlagerung        5.73 / 5.42
        Nebentext auf der kritischen Meldung   5.60 / 4.93
        Symbole auf dem Dock                   6.53 / 13.21

    Bei der Kachel-Deckkraft der Leiste (0.70) waeren es 3.32, 3.26 und
    4.05 gewesen - drei Durchfaller. Das ist der Grund, aus dem
    src/brand.py eine dritte Deckkraft ausrechnet, und diese Zeile ist
    das, was ihn festhaelt.

    Die Farbe kommt aus der ROLLE und nicht aus der Palette: der Nutzer
    kann sie verstellen, und geprueft gehoert, was diese Installation
    wirklich malt.
    """
    style, plates = _plates(monkeypatch, tmp_path, theme_name)
    colours = style.THEME.COLORS

    for namespace, role, (channels, alpha) in _plate_contrast_cases(
            style, plates):
        for ground, wallpaper in sorted(EXTREME_WALLPAPERS.items()):
            ratio = _contrast(_channels(colours[role]),
                              _over(channels, alpha, wallpaper))
            assert ratio >= TEXT_CONTRAST, (
                f"{role} auf der Platte von {namespace} misst {ratio:.2f}:1 "
                f"ueber einer {ground}en Tapete im Thema {theme_name}, WCAG "
                f"verlangt {TEXT_CONTRAST}:1. Entweder die Deckkraft in "
                "src/brand.py hoch oder die Farbe anders")


@pytest.mark.parametrize("theme_name", sorted(_theme.THEMES))
def test_the_glass_plates_are_glass_and_not_almost_opaque(
        theme_name, monkeypatch, tmp_path):
    """Die Gegenprobe zur Rechnung darueber.

    Ohne sie liesse sich jeder Kontrastfehler dadurch beheben, dass die
    Platte deckender wird - bis sie deckend IST und die Pruefung
    muehelos besteht, weil gar kein Glas mehr da ist. Diese hier
    verlangt, dass die Tapete durch jede Platte noch messbar
    durchkommt.
    """
    style, plates = _plates(monkeypatch, tmp_path, theme_name)

    for namespace, role, (channels, alpha) in _plate_contrast_cases(
            style, plates):
        colour = _channels(style.THEME.COLORS[role])
        opaque = _contrast(colour, channels)
        worst = min(_contrast(colour, _over(channels, alpha, wallpaper))
                    for wallpaper in EXTREME_WALLPAPERS.values())
        assert worst < opaque, (
            f"die Platte von {namespace} kommt auf denselben Kontrast wie "
            "eine deckende - dann laesst sie nichts durch und ist kein Glas")


# --------------------------------------------------------------------
# Und die zwei Waechter finden auch wirklich etwas
# --------------------------------------------------------------------

def test_the_plate_reader_finds_an_opaque_background_planted_for_it():
    """Dem Deckkraft-Leser wird ein Fund hingelegt.

    WARUM DAS EINE EIGENE PRUEFUNG IST
        Ein sauberer Baum gibt einem Waechter nichts zu finden. Die zwei
        Pruefungen oben stehen deshalb auf gruen, solange nichts kaputt
        ist - und genauso, wenn der Leser per Konstruktion nichts finden
        KANN. Am 12.08.2026 ist genau das in diesem Baum passiert: ein
        Waechter gegen Radien neben der Leiter fand nie etwas, weil sein
        Muster geschweifte Klammern ausschloss.

        Hier steht deshalb die Zeile, die es bis zum 12.08.2026 wirklich
        gab, mit dem Wert, den sie wirklich hatte.
    """
    planted = ("$bg: #08262C;\n"
               ".overlay-outer {\n"
               "  background: $bg;\n"
               "  border: 1px solid $border;\n"
               "}\n")
    body = _rule_body(planted, ".overlay-outer")
    assert body is not None
    channels, alpha = _colour(_own_background(body), _scss_variables(planted))
    assert alpha == OPAQUE, (
        "der Leser haelt `background: $bg` mit einem sechsstelligen Hex "
        "nicht fuer deckend - dann faende er den Zustand nicht wieder, in "
        "dem zwoelf Flaechen dieses Projekts waren")
    assert channels == (8, 38, 44)


def test_the_plate_reader_is_not_fooled_by_a_nested_rule():
    """Und er liest den Hintergrund DIESER Regel, nicht den der naechsten.

    ags-style.template ist SCSS und schachtelt. Ein Leser, der einfach
    den ersten `background:` im Rumpf nimmt, faende bei `.overlay-outer`
    irgendwann den Grund eines Kopfbereichs - und meldete eine
    durchsichtige Platte als deckend oder umgekehrt, je nachdem, was
    zuerst kommt.
    """
    planted = (".platte {\n"
               "  .kopfzeile { background: #08262C; }\n"
               "  background: rgba(8, 38, 44, 0.86);\n"
               "}\n")
    body = _rule_body(planted, ".platte")
    _, alpha = _colour(_own_background(body), {})
    assert alpha == 0.86, (
        "der Leser hat den Hintergrund einer geschachtelten Regel fuer den "
        "der Platte gehalten")


def test_the_plate_reader_refuses_a_colour_it_cannot_read():
    """Und er raet nicht.

    Eine Schreibweise, die dieser Leser nicht kennt, muss die Pruefung
    ANHALTEN und nicht als "wohl deckend" durchgehen - sonst waere die
    naechste Farbform ein lautloses Loch in beiden Richtungen.
    """
    with pytest.raises(ValueError):
        _colour("color-mix(in srgb, red 50%, blue)", {})


# --------------------------------------------------------------------
# Die Schwelle ist abgeleitet und nicht geraten
# --------------------------------------------------------------------

def test_the_blur_threshold_lies_between_nothing_and_the_thinnest_glass(
        palette):
    """Beide Grenzen, und jede hat einen sichtbaren Fehlermodus.

    Bei 0 verwischt der Compositor auch das, was gar nichts ist: den
    Rand um die Platte und alles ausserhalb ihrer runden Ecken. Bei
    GLASS_PANEL_ALPHA oder darueber hoert er auf, die Platte selbst zu
    verwischen - dann ist der Hintergrund durchsichtig und scharf, also
    genau das Loch, gegen das der ganze Effekt gebaut ist.
    """
    assert 0 < palette.GLASS_IGNORE_ALPHA < palette.GLASS_PANEL_ALPHA, (
        f"die Schwelle {palette.GLASS_IGNORE_ALPHA} liegt nicht zwischen 0 "
        f"und der duennsten Glasschicht {palette.GLASS_PANEL_ALPHA}")


def test_the_threshold_is_computed_from_the_thinnest_layer(palette):
    """Und sie ist nicht nur zufaellig richtig, sondern abgeleitet.

    Die Pruefung darueber liesse jede Zahl im Intervall zu, auch eine
    von Hand hineingeschriebene - und die driftet, sobald jemand die
    Deckkraft aendert. Die Mitte des Intervalls ist die einzige Zahl,
    die von BEIDEN Fehlern gleich weit weg ist.
    """
    assert palette.GLASS_IGNORE_ALPHA == round(palette.GLASS_PANEL_ALPHA / 2, 2)


def test_the_chip_is_less_transparent_than_the_panel_it_sits_on(palette):
    """Die Schichtung, auf der die ganze Lesbarkeit beruht.

    Der Text steht auf den Kacheln, nicht auf der Platte. Waere die
    Kachel die duennere der beiden, saesse er auf der duennsten Stelle
    des Aufbaus - und dann waere die Rechnung unten nicht mehr zu
    gewinnen, ohne das Glas praktisch undurchsichtig zu machen.
    """
    assert palette.GLASS_CHIP_ALPHA > palette.GLASS_PANEL_ALPHA


# --------------------------------------------------------------------
# Der Text bleibt lesbar, im schlechtesten Fall
# --------------------------------------------------------------------

def _through_the_glass(palette, wallpaper):
    """Der Kontrast des Leistentexts durch den ganzen Aufbau.

    Kachel auf Platte auf Tapete. Genau diese Schichtung ist es, die den
    Effekt bezahlbar macht - die beiden Deckkraefte stapeln sich, so
    dass die Platte daneben duenn bleiben darf.
    """
    panel = _over(_channels(palette.SHADE_1), palette.GLASS_PANEL_ALPHA,
                  wallpaper)
    chip = _over(_channels(palette.PETROL), palette.GLASS_CHIP_ALPHA, panel)
    return _contrast(_channels(palette.TEXT), chip)


@pytest.mark.parametrize("ground", sorted(EXTREME_WALLPAPERS))
def test_text_on_glass_survives_either_extreme_wallpaper(palette, ground):
    """Der Grund, aus dem die meisten Glaseffekte schlecht sind.

    Kontrast wird gegen einen Hintergrund gerechnet, und unter Glas ist
    der Hintergrund teilweise die Tapete - also etwas, das der Nutzer
    jederzeit aendern kann. Berechenbar bleibt nur der SCHLECHTESTE
    Fall, und welches der beiden Extreme das ist, haengt daran, ob die
    Schrift des Themas hell oder dunkel ist. Also werden beide
    gerechnet.
    """
    ratio = _through_the_glass(palette, EXTREME_WALLPAPERS[ground])
    assert ratio >= TEXT_CONTRAST, (
        f"Leistentext auf Glas misst {ratio:.2f}:1 ueber einer {ground}en "
        f"Tapete, WCAG verlangt {TEXT_CONTRAST}:1. Entweder die "
        "Deckkraft in src/theme.py hoch oder die Farbe anders")


def test_the_glass_keeps_headroom_and_is_not_sitting_on_the_limit(palette):
    """Eine Deckkraft, die 4.51:1 erreicht, besteht die Pruefung oben und
    ist trotzdem falsch gewaehlt.

    Der Kontrast oben gilt fuer die AUSGELIEFERTEN Farben. Die
    Kachelfarbe ist einstellbar (get_user_color("background")), also
    muss zwischen der Rechnung und der Grenze so viel Platz sein, dass
    ein Nutzer die Farbe anfassen kann, ohne die Schrift zu verlieren.

    Ein Fuenftel ueber der Grenze ist die Entscheidung; gemessen sind es
    beim ausgelieferten Thema 6.33:1 ueber Weiss, also 41 % darueber.
    """
    worst = min(_through_the_glass(palette, ground)
                for ground in EXTREME_WALLPAPERS.values())
    assert worst >= TEXT_CONTRAST * 1.2


def test_glass_costs_contrast_and_the_test_knows_how_much(palette):
    """Die Gegenprobe: ohne Tapete darunter ist derselbe Text deutlich
    besser lesbar.

    Ohne sie koennte die Rechnung oben die Deckkraft ganz ignorieren und
    trotzdem gruen sein - eine Kachel mit alpha 1.0 besteht sie
    muehelos. Diese hier besteht sie NICHT: sie verlangt, dass Glas
    ueberhaupt etwas durchlaesst.
    """
    opaque = _contrast(_channels(palette.TEXT), _channels(palette.PETROL))
    worst = min(_through_the_glass(palette, ground)
                for ground in EXTREME_WALLPAPERS.values())
    assert worst < opaque, (
        "die Glasrechnung kommt auf denselben Kontrast wie eine deckende "
        "Kachel - dann laesst das Glas nichts durch und ist keines")


# --------------------------------------------------------------------
# Die Deckkraft kommt aus dem Zentrum und nicht aus dem Stylesheet
# --------------------------------------------------------------------

# Dieselbe Menge, die tests/src/test_brand.py auf Farbliterale prueft,
# und aus demselben Grund: `src/templates/ags-style.template` ist die
# groesste Stilvorlage dieses Projekts und lag bis zum 12.08.2026 hinter
# BEIDEN Waechtern, weil beide nach `src/styles/*.template` griffen.
STYLESHEETS = sorted((SRC / "styles").glob("*.template")) + [
    SRC / "templates" / "ags-style.template"]


@pytest.mark.parametrize("path", STYLESHEETS, ids=lambda path: path.name)
def test_no_stylesheet_writes_its_own_transparency(path):
    """Ein Glaseffekt, den man nicht am Zentrum verstellen kann, ist der
    naechste tote Regler.

    Gesucht wird nach rgba() mit einer ausgeschriebenen Deckkraft, also
    nach `rgba(13, 61, 71, 0.7)` im Quelltext der VORLAGE. In der
    erzeugten Datei steht genau das - dort kommt es aber aus
    brand.rgba() und laesst sich an einer Stelle aendern.

    BEIDE KOMMENTARFORMEN, seit ags-style.template dazugekommen ist:
    die Datei ist SCSS und erklaert sich in `//`-Zeilen, und mehrere
    dieser Erklaerungen ZITIEREN die Deckkraft, die gegangen ist - der
    Kalender nennt sein altes rgba(42, 90, 42, 0.3) beim Namen. Ein
    Waechter, der Erklaerung und Regel nicht unterscheidet, treibt die
    Erklaerungen aus dem Baum, und das ist das Gegenteil dessen, was
    dieses Projekt mit ihnen tut.
    """
    text = re.sub(r"^\s*//.*$", "",
                  re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"),
                         flags=re.DOTALL), flags=re.MULTILINE)
    literal = re.findall(r"rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*[\d.]+\s*\)",
                         text)
    assert literal == [], (
        f"{path.name} schreibt seine Deckkraft selbst aus: {literal}. Sie "
        "gehoert nach src/brand.py, wo die Kontrastrechnung sie sehen kann")


def test_the_bar_no_longer_dims_its_own_text():
    """`opacity` in GTK4 blendet das ganze Widget ab, SAMT SEINER SCHRIFT.

    In bar-style.template stand `opacity: 0.8` auf .bar-module, also
    auf jeder Kachel der Leiste. Die 0.8 haben damit
    nicht den Hintergrund durchsichtig gemacht, sondern zusaetzlich den
    Text - und genau den Kontrast weggenommen, den src/brand.py fuer
    diesen Text ausgerechnet hat.

    Fuer Glas ist das ohnehin die falsche Eigenschaft: durchsichtig
    gehoert der Hintergrund, und dafuer gibt es rgba().
    """
    text = re.sub(r"/\*.*?\*/", "",
                  (SRC / "styles" / "bar-style.template").read_text(
                      encoding="utf-8"), flags=re.DOTALL)
    # DREI AUSNAHMEN, UND ALLE DREI MEINEN GENAU DAS, WAS opacity TUT:
    # ein ganzes Element abblenden, Schrift eingeschlossen. Ein
    # Arbeitsbereich ohne Fenster, ein Ablagesymbol, das nichts will,
    # und ein Hardwaremodul, dessen Sensoren nicht antworten, sollen
    # BLASSER sein als ihre Geschwister - das ist keine Durchsichtigkeit,
    # sondern eine Aussage, und ihr Kontrast ist Absicht.
    allowed = ("OPACITY_FULL", "OPACITY_DISABLED",
               "HARDWARE_OFFLINE_OPACITY")
    offenders = [line.strip() for line in text.splitlines()
                 if re.match(r"\s*opacity\s*:", line)
                 and not any(name in line for name in allowed)]
    assert offenders == [], (
        "diese Regeln blenden ein ganzes Modul ab statt nur seinen "
        f"Hintergrund: {offenders}")
