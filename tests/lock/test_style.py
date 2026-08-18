# SPDX-License-Identifier: GPL-3.0-or-later
"""Das Stylesheet des Sperrbildschirms, aus der Mitte und von GTK gelesen.

WAS HIER VORHER STAND UND WARUM ES NICHT ZU PRUEFEN WAR
    hyprlock nahm kein Stylesheet. Seine Konfiguration -
    src/templates/hyprlock-config.template - war eine eigene
    Konfigurationssprache mit zwoelf rgb()- und rgba()-Literalen in
    Terminalgruen auf einem #0c0c0c, und es gab keinen Parser, durch den
    ein Test sie haette schicken koennen. Falsch geschriebene Farben
    haette man auf dem Bildschirm gesehen, sonst nirgends.

    Diese Datei ist die Haelfte, die der Wechsel auf GTK4 dazugewinnt:
    ein Stylesheet, das GTKs eigener Parser lesen kann, und damit eine
    Messung statt eines Blicks.

DIE ZWEI FALLEN, DIE DAS ABDECKT
    * Ein Tippfehler in einer CSS-Regel ist KEIN Fehler, den irgendwer
      zu sehen bekommt: GtkCssProvider verwirft die Regel, meldet es
      ueber das Signal "parsing-error" und macht weiter. Weder
      zepos-lock noch regreet haengen an diesem Signal. wofis Stylesheet
      hatte auf diese Weise 39 Fehler, ohne dass es jemandem auffiel.
    * Ein Farbliteral sieht richtig aus, bis brand.py sich aendert. Dann
      ist es die eine Flaeche, die stehen bleibt.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from src import brand
from tests import gtk4_headless
# Die Kontrastrechnung steht schon einmal in diesem Baum, mit derselben
# Begruendung und denselben WCAG-Zahlen. Ein zweites Mal hinschreiben
# hiesse: zwei Rechnungen, die uebereinstimmen muessen, und die zweite
# ist die, die veraltet - genau das Argument, mit dem brand.py anfaengt.
from tests.src import test_glass

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
TEMPLATE = SRC / "styles" / "lock-style.template"


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
    """Jedes Thema durch dieselbe Schleierrechnung.

    Der Schleier und das Bild gehoeren beide dem Thema, und die zwei
    haengen aneinander: ein helles Thema auf einem dunklen Bild ist
    unter keinem zulaessigen Schleier lesbar. Erst wenn jedes Thema
    diese Rechnung einzeln besteht, ist das kein Zufall.
    """
    return _theme.palette(request.param)


@pytest.fixture
def style(monkeypatch):
    """style_definition, so importiert, wie der Generator es importiert.

    Ueber den Suchpfad: src/ ist kein Paket, und style_definition.py
    sagt `import audio` und `import brand` - flach, wie jedes andere
    Modul dort.
    """
    monkeypatch.syspath_prepend(str(SRC))
    for name in ("brand", "style_definition", "audio", "monitors", "sizes"):
        monkeypatch.delitem(__import__("sys").modules, name, raising=False)
    import style_definition

    return style_definition


@pytest.fixture
def processor(monkeypatch):
    monkeypatch.syspath_prepend(str(SRC))
    import template_processor

    return template_processor


def _render(processor_, style_, tmp_path: Path, monkeypatch) -> Path:
    """Die Vorlage, erzeugt mit dem ECHTEN Prozessor.

    Mit dem echten und nicht mit einem str.replace() dieses Tests -
    sonst misst er seine eigene Ersetzung. Dieselbe Form wie
    tests/src/test_sizes.py._render(), und aus derselben Begruendung.

    ZEPOS_SYSTEM_ROOT wird gesetzt, weil die Vorlage den Weg zum
    Hintergrundbild darueber bildet: eine Stilvorlage darf keinen
    Systempfad von sich aus tragen.
    """
    monkeypatch.setenv("ZEPOS_SYSTEM_ROOT", str(SRC))
    out = tmp_path / "style.css"
    processor_.ConfigProcessor(
        styles=dict(style_.STYLE_VARIABLES)).apply_template(TEMPLATE, out)
    return out


# --------------------------------------------------------------------
# 1. Jede Farbe aus der Mitte
# --------------------------------------------------------------------

def test_every_colour_the_lock_screen_paints_is_a_brand_colour(
        style, processor, tmp_path, monkeypatch):
    """Nicht "es steht ein Platzhalter da", sondern: was herauskommt, IST
    eine Farbe aus brand.py.

    Der Unterschied ist gemessen und nicht theoretisch: ein Platzhalter
    kann auf einen Wert zeigen, den jemand in style_definition.py als
    Literal hingeschrieben hat, und dann ist die Vorlage sauber und die
    erzeugte Datei nicht.
    """
    rendered = _render(processor, style, tmp_path,
                       monkeypatch).read_text(encoding="utf-8")
    body = re.sub(r"/\*.*?\*/", "", rendered, flags=re.DOTALL)

    palette = {value.upper() for name, value in vars(brand).items()
               if name.isupper() and isinstance(value, str)
               and re.fullmatch(r"#[0-9A-Fa-f]{6}", value)}
    # Die Knotennamen sind Selektoren wie box#card, keine Farben - nur
    # sechsstellige Hex zaehlen.
    used = {match.upper()
            for match in re.findall(r"#[0-9A-Fa-f]{6}\b", body)}

    assert used, "das erzeugte Stylesheet traegt ueberhaupt keine Farbe"
    assert used <= palette, (
        "Farben ausserhalb der Marke im erzeugten Stylesheet: "
        + ", ".join(sorted(used - palette)))


def test_no_placeholder_survives_into_the_generated_stylesheet(
        style, processor, tmp_path, monkeypatch):
    """Ein {{STYLE_...}}, das stehen bleibt, ist eine Regel, die GTK
    verwirft - und eine Flaeche, die dann GTKs Vorgabefarbe traegt."""
    rendered = _render(processor, style, tmp_path,
                       monkeypatch).read_text(encoding="utf-8")
    leftovers = re.findall(r"\{\{[A-Z_0-9]+\}\}", rendered)
    assert leftovers == [], f"nicht ersetzte Platzhalter: {leftovers}"


def test_the_backdrop_is_the_same_picture_the_login_shows(
        style, processor, tmp_path, monkeypatch):
    """Derselbe Hintergrund wie Anmeldung und Assistent.

    src/login/regreet.toml nennt /usr/share/zepos/branding/
    zepos-backdrop.png, und packaging/zepos-config legt src/branding/
    genau dorthin. Die Stilvorlage darf diesen Pfad nicht selbst tragen -
    sie baut ihn aus {{ZEPOS_SYSTEM_ROOT}} und brand.BACKDROP_FILE.
    """
    assert "/usr/share/zepos" not in TEMPLATE.read_text(encoding="utf-8"), (
        "die Stilvorlage raet, wo das Paket liegt")

    rendered = _render(processor, style, tmp_path,
                       monkeypatch).read_text(encoding="utf-8")
    expected = f"{SRC}/branding/{brand.BACKDROP_FILE}"
    assert expected in rendered, (
        f"der Weg zum Hintergrundbild kommt nicht heraus: erwartet {expected}")

    # Und das Bild ist wirklich da, wo der Pfad hinzeigt - sonst zeigte
    # die Sperre die Farbe darunter und niemand wuesste warum.
    assert (SRC / "branding" / brand.BACKDROP_FILE).is_file(), (
        f"src/branding/{brand.BACKDROP_FILE} fehlt")

    # regreet nennt dieselbe Datei. Ein Test, weil es zwei Stellen sind:
    # die eine ist eine statische TOML, die andere ein Platzhalter.
    toml = (SRC / "login" / "regreet.toml").read_text(encoding="utf-8")
    assert brand.BACKDROP_FILE in toml, (
        "die Anmeldung zeigt ein anderes Bild als der Sperrbildschirm")


# --------------------------------------------------------------------
# 1b. Der Schleier, und ob er sich verdient
# --------------------------------------------------------------------

BACKDROP = SRC / "branding" / brand.BACKDROP_FILE


def backdrop_of(palette) -> Path:
    return SRC / "branding" / palette.BACKDROP_FILE


def texts_on_the_backdrop(palette) -> dict:
    """Was dieser Bildschirm an Text auf den Hintergrund malt.

    Jede dieser Farben liegt DIREKT auf dem Bild - es gibt keine Kachel
    mehr darunter, das ist der Punkt der Form.
    """
    return {
        "die Uhr": palette.TEXT,
        "das Datum": palette.TEXT_DIM,
        "der Name": palette.CYAN_TEXT,
        "die Feststelltaste": palette.YELLOW,
        "die Ablehnung": palette.RED,
    }


_BRIGHTEST_PROBE = """
import sys, gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf
p = GdkPixbuf.Pixbuf.new_from_file(sys.argv[1])
data, stride, n = p.get_pixels(), p.get_rowstride(), p.get_n_channels()
w, h = p.get_width(), p.get_height()
top = [0, 0, 0]
low = [255, 255, 255]
for y in range(h):
    row = data[y * stride:y * stride + w * n]
    for c in range(3):
        band = row[c::n]
        m, k = max(band), min(band)
        if m > top[c]:
            top[c] = m
        if k < low[c]:
            low[c] = k
print(f"{top[0]} {top[1]} {top[2]} {low[0]} {low[1]} {low[2]}")
"""


def _extremes_of(picture: Path) -> dict[str, tuple[float, float, float]]:
    """Die kanalweisen Maxima UND Minima eines Hintergrundbildes.

    AUS DER DATEI GELESEN UND NICHT HINGESCHRIEBEN. Eine Zahl im Test
    waere eine zweite Kopie einer Eigenschaft des Bildes, und beim
    naechsten Austausch der Marke die, die niemand mitzieht.

    KANALWEISE und nicht das hellste bzw. dunkelste EINZELNE Pixel, und
    das ist strenger statt bequemer: (max_r, max_g, max_b) ist
    mindestens so hell wie jedes wirklich vorhandene Pixel und
    (min_r, min_g, min_b) mindestens so dunkel. Wer dagegen besteht,
    besteht gegen das ganze Bild.

    BEIDE ENDEN, seit dem 12.08.2026. Hier stand nur das helle, mit der
    Begruendung "der schlechteste Fall ist die hellste Stelle des
    Bildes". Das gilt fuer HELLEN Text; das zweite Thema hat dunklen,
    und fuer den ist es genau umgekehrt. Die Pruefung war also fuer die
    Haelfte aller denkbaren Paletten blind.

    In einem KIND, aus demselben Grund wie der CSS-Parser weiter unten,
    und ueber GdkPixbuf, weil die virtuelle Umgebung dieses Projekts
    kein Pillow hat - GdkPixbuf kommt dagegen mit GTK4 und ist auf jeder
    Maschine da, die diesen Bildschirm ueberhaupt zeichnen kann.
    """
    found = gtk4_headless.gi_interpreter({"GdkPixbuf": "2.0"})
    if not found:
        pytest.skip("kein Python auf dieser Maschine kann GdkPixbuf laden")
    executable, extra = found
    # MIT PATH, anders als bei jedem anderen Kind dieser Suite, und das
    # ist gemessen: GdkPixbuf 2.44 laedt PNG nicht mehr selbst, sondern
    # ueber glycin, und glycin startet seinen Dekodierer in einem
    # bwrap-Sandkasten. Mit `PATH: ""` endet der Aufruf mit
    #
    #     Could not spawn the following command. Is the used binary
    #     available? `"bwrap" "--unshare-all" ... "glycin-image-rs"`
    #
    # Die Stub-PATH-Disziplin des restlichen Baums gilt fuer ERZEUGTE
    # ARTEFAKTE, die versehentlich ein echtes Werkzeug erwischen
    # koennten. Dieses Kind ist ein Messgeraet und liest genau eine
    # Datei aus diesem Baum.
    environment = {"PATH": os.environ.get("PATH", "/usr/bin")}
    if extra:
        environment["PYTHONPATH"] = ":".join(extra)
    result = subprocess.run(
        [executable, "-c", _BRIGHTEST_PROBE, str(picture)],
        env=environment, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, (
        f"das Bild liess sich nicht lesen:\n{result.stdout}{result.stderr}")
    parts = [float(part) for part in result.stdout.split()]
    return {"hellste": tuple(parts[:3]), "dunkelste": tuple(parts[3:])}


@pytest.mark.allow_subprocess
def test_the_scrim_keeps_every_text_readable_at_both_extremes(palette):
    """Die Rechnung, an der LOCK_SCRIM_ALPHA haengt.

    Seit der Bildschirm keine Kachel mehr hat, liegt JEDER Text direkt
    auf dem Bild. Der schlechteste Fall ist deshalb eine Extremstelle
    des Bildes - nicht reines Weiss wie bei der Leiste, denn dieses Bild
    gehoert dem Paket und nicht dem Nutzer. Genau darum hat der
    Sperrbildschirm eine eigene Zahl und nicht GLASS_PANEL_ALPHA.

    WELCHE der beiden Stellen die schlechtere ist, haengt am Thema: bei
    hellem Text die hellste, bei dunklem die dunkelste. Also beide.
    """
    picture = backdrop_of(palette)
    texts = texts_on_the_backdrop(palette)
    for where, pixel in _extremes_of(picture).items():
        ground = test_glass._over(test_glass._channels(palette.INK),
                                  palette.LOCK_SCRIM_ALPHA, pixel)
        too_dim = {
            name: round(test_glass._contrast(
                test_glass._channels(colour), ground), 2)
            for name, colour in texts.items()
            if test_glass._contrast(test_glass._channels(colour), ground)
            < test_glass.TEXT_CONTRAST
        }
        assert too_dim == {}, (
            f"auf der {where}n Stelle von {picture.name} {pixel} liegt "
            f"Text unter {test_glass.TEXT_CONTRAST}:1 - {too_dim}")


@pytest.mark.allow_subprocess
def test_without_the_scrim_something_would_be_unreadable(palette):
    """Die Gegenprobe, ohne die die Zusicherung darueber nichts sagt.

    Ein Schleier, den man weglassen koennte, ohne dass etwas darunter
    faellt, ist kein gemessener Wert, sondern Geschmack - und der
    naechste Leser haette keinen Grund, ihn stehen zu lassen.

    GEMESSEN am 12.08.2026: im ausgelieferten Thema liegt brand.RED, die
    Farbe der Ablehnung, auf der hellsten Stelle des Bildes bei 4.28:1;
    im hellen Thema liegt dieselbe Rolle auf der dunkelsten Stelle bei
    4.17:1. Das ist ausgerechnet die Farbe, die im schlechtesten Moment
    gelesen werden muss.
    """
    picture = backdrop_of(palette)
    texts = texts_on_the_backdrop(palette)
    worst = min(
        test_glass._contrast(test_glass._channels(colour), pixel)
        for pixel in _extremes_of(picture).values()
        for colour in texts.values())
    assert worst < test_glass.TEXT_CONTRAST, (
        f"ohne Schleier ist auf {picture.name} schon alles lesbar - dann "
        f"ist LOCK_SCRIM_ALPHA eine Zahl ohne Grund und gehoert "
        f"geloescht ({worst:.2f}:1)")


def test_the_scrim_is_thin_enough_that_the_picture_is_still_there(palette):
    """Ein Schleier, der das Bild verdeckt, ist kein Schleier.

    Die Obergrenze ist keine Willkuer: ab GLASS_PANEL_ALPHA waere die
    Schicht dichter als das dickste Glas, das dieser Desktop sonst
    irgendwo malt - und der Hintergrund, der die Form tragen soll, waere
    eine Farbflaeche.
    """
    assert 0 < palette.LOCK_SCRIM_ALPHA < palette.GLASS_PANEL_ALPHA, (
        f"der Schleier ({palette.LOCK_SCRIM_ALPHA}) liegt nicht zwischen "
        f"nichts und der dicksten Glasschicht "
        f"({palette.GLASS_PANEL_ALPHA})")


# --------------------------------------------------------------------
# 1c. Die Form: rund, mittig, wenig
# --------------------------------------------------------------------

def test_the_field_is_a_pill_and_the_avatar_a_circle(style, processor,
                                                     tmp_path, monkeypatch):
    """Was der Nutzer am 12.08.2026 mit "vgl. apple os login" gemeint hat.

    Runde Formen sind der sichtbarste Teil davon, und beide Radien
    muessen ROBUST rund sein: der Kreis ueber 50 %, damit er ein Kreis
    bleibt, wenn jemand die Groesse aendert, und die Pille ueber eine
    Zahl, die groesser ist als die halbe Feldhoehe bei JEDEM
    Skalierungsfaktor - GTK klemmt sie auf die Haelfte der kuerzeren
    Seite.
    """
    rendered = _render(processor, style, tmp_path,
                       monkeypatch).read_text(encoding="utf-8")
    body = re.sub(r"/\*.*?\*/", "", rendered, flags=re.DOTALL)

    avatar = re.search(r"label#avatar\s*\{[^}]*\}", body)
    assert avatar is not None, "es gibt kein Benutzerbild"
    assert "border-radius: 50%" in avatar.group(0), (
        "das Benutzerbild ist kein Kreis:\n" + avatar.group(0))
    for side in ("min-width", "min-height"):
        assert side in avatar.group(0), (
            f"ohne {side} ist der Kreis so breit wie sein Buchstabe - ein "
            '"I" ergaebe eine Ellipse')

    field = re.search(r"entry#password\s*\{[^}]*\}", body)
    assert field is not None, "es gibt kein Passwortfeld"
    radius = re.search(r"border-radius:\s*(\d+)px", field.group(0))
    assert radius is not None, (
        "das Feld hat keinen Radius in px:\n" + field.group(0))
    # Die groesste Schriftstufe der Leiter mal zwei ist mehr als jede
    # Feldhoehe, die dabei herauskommen kann - wer darueber liegt, ist
    # bei jedem Faktor eine Pille.
    assert int(radius.group(1)) >= 2 * 64 * 4, (
        f"der Radius {radius.group(1)}px ist keine sichere Pille - bei einem "
        "grossen Skalierungsfaktor waere das Feld ein Rechteck mit runden "
        "Ecken")


def test_the_screen_carries_no_labels_beside_its_fields(style, processor,
                                                        tmp_path, monkeypatch):
    """"Wenig" ist der erste Punkt an der Form, und der einzige, den man
    aus dem Programm ablesen kann.

    regreet zeigt heute "User:" und "Session:" neben Auswahlfeldern, und
    genau das macht aus einem Bildschirm ein Formular. Dieser hier hat
    vier Texte, und drei davon sind Tatsachen der Maschine.
    """
    source = (ROOT / "lock" / "zepos-lock.c").read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines()
                      if not line.lstrip().startswith(("*", "/*")))
    labels = set(re.findall(r'#define ZEP_TEXT_(\w+)', code))
    assert labels == {"PROMPT", "CHECKING", "REFUSED", "CAPSLOCK",
                      "DATE", "CLOCK"}, (
        f"der Bildschirm traegt andere Texte als erwartet: {sorted(labels)}")

    # Und der Aufforderungstext steht IM Feld und nicht daneben.
    assert "gtk_entry_set_placeholder_text" in code, (
        "der Aufforderungstext ist keine Einblendung im Feld")
    assert "ZEP_TEXT_PROMPT" in code


# --------------------------------------------------------------------
# 2. Und jetzt liest GTK selbst
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
    """Die Datei durch GTKs eigenen Parser, in einem Kind.

    In einem KIND, aus dem Grund, den tests/gtk4_headless.py in voller
    Laenge aufschreibt: GTK4 in den pytest-Prozess zu laden kann die
    Sitzung ohne Bericht beenden. Eine Anzeige braucht ein
    GtkCssProvider nicht.
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
def test_gtk_reads_the_lock_stylesheet_without_a_single_error(
        style, processor, tmp_path, monkeypatch):
    """Gemessen gegen GTK 4.22.4 aus dem angehefteten Schnappschuss."""
    out = _render(processor, style, tmp_path, monkeypatch)

    errors = _parse_with_gtk(out)
    assert errors == [], (
        f"GTK meldet {len(errors)} Parse-Fehler und verwirft die betroffenen "
        "Regeln lautlos:\n" + "\n".join(errors))


@pytest.mark.allow_subprocess
def test_the_parser_check_would_notice_a_broken_rule(tmp_path):
    """Die Gegenprobe. Ein Lauf, der 0 Fehler meldet, weil er nicht misst,
    sieht aus wie einer, der 0 Fehler meldet, weil die Datei sauber ist."""
    broken = tmp_path / "kaputt.css"
    broken.write_text(
        "window#lock { background-color: rgb(keine-farbe); }\n",
        encoding="utf-8")
    assert _parse_with_gtk(broken) != [], (
        "der Parser-Lauf findet nicht einmal eine erfundene Farbe")


# --------------------------------------------------------------------
# 3. Die Knotennamen, die das Programm wirklich vergibt
# --------------------------------------------------------------------

def test_every_selector_matches_a_widget_the_program_names():
    """Eine Regel fuer einen Knoten, den es nicht gibt, ist eine Regel,
    die nie greift - und die niemandem auffaellt.

    Genau diese Sorte toter Selektor stand in der Fassung der
    Abmeldemaske fuer wlogout: `button#reboot-local` neben
    `button#reboot`, weil das erzeugte Layout den einen Namen benutzte
    und das Rueckfall-Layout den anderen. Hier wird der Knotenname aus
    dem C-Quelltext gelesen und gegen die Vorlage gehalten.
    """
    source = (ROOT / "lock" / "zepos-lock.c").read_text(encoding="utf-8")
    named = set(re.findall(r'gtk_widget_set_name\([^,]+,\s*"([a-z]+)"\)',
                           source))
    assert named, "das Programm vergibt gar keine Knotennamen mehr"

    body = re.sub(r"/\*.*?\*/", "", TEMPLATE.read_text(encoding="utf-8"),
                  flags=re.DOTALL)
    selected = set(re.findall(r"#([a-z]+)\b", body))

    assert selected <= named, (
        "die Stilvorlage zeigt auf Knoten, die das Programm nicht vergibt: "
        + ", ".join(sorted(selected - named)))
    assert named <= selected, (
        "das Programm vergibt Knotennamen, die niemand faerbt - dann traegt "
        "die Flaeche GTKs Vorgabe: " + ", ".join(sorted(named - selected)))


def test_the_two_css_classes_the_program_toggles_are_styled():
    """`checking` und `failure` sind die zwei Zustaende, die der
    Bildschirm ueberhaupt zeigt. Eine Klasse, die das Programm setzt und
    die Vorlage nicht kennt, ist eine Rueckmeldung, die ausbleibt."""
    source = (ROOT / "lock" / "zepos-lock.c").read_text(encoding="utf-8")
    classes = set(re.findall(r'gtk_widget_add_css_class\([^,]+,\s*"([a-z]+)"\)',
                             source))
    assert classes == {"checking", "failure"}, (
        f"das Programm setzt andere Klassen als erwartet: {sorted(classes)}")

    body = re.sub(r"/\*.*?\*/", "", TEMPLATE.read_text(encoding="utf-8"),
                  flags=re.DOTALL)
    for name in sorted(classes):
        assert f".{name}" in body, (
            f"die Klasse {name} wird gesetzt und nirgends gefaerbt")
