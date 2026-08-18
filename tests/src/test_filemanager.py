# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Dateimanager: kommt die Marke bei einem fremden Fenster an?

WAS GEMELDET WURDE
    Der Nutzer am 12.08.2026: "nautilus einbauen vlt. auch nautilus an
    unser style anpassen". Eingebaut war er zu dem Zeitpunkt schon
    (packaging/zepos-apps), und gtk4-colors-config.template schrieb ihm
    45 benannte libadwaita-Farben nach ~/.config/gtk-4.0/gtk.css. Die
    Frage war also nicht, OB etwas ankommt, sondern WIEVIEL.

WAS GEMESSEN WURDE, UND WOMIT
    Gegen libadwaita 1.9.2 und GTK 4.22.4, mit gtk4-broadwayd nach dem
    Verfahren aus tests/gtk4_headless.py. Jeder der 45 Namen bekam eine
    eigene Sentinel-Farbe; dann wurde eine Flaeche mit
    `background-color: var(--<name>)` gemalt und ihr mittleres Pixel
    aus dem PNG gelesen.

        39 von 45 kommen an
         6 von 45 kommen NICHT an

    Die sechs: accent_color, success_color, warning_color, error_color,
    destructive_color, dimmed_color.

WARUM DIE SECHS DURCHFALLEN
    Aus libadwaitas eigenem Blatt, herausgeholt mit
    `gresource extract /usr/lib/libadwaita-1.so.0 \
     /org/gnome/Adwaita/styles/gtk.css`:

        :root { --accent-bg-color: @accent_bg_color;
                --accent-color: oklab(from var(--accent-bg-color)
                                      var(--standalone-color-oklab)); }

    Es gibt 42 solcher Bruecken vom alten Namen zur Variablen, und die
    fuenf Zustandsfarben sind nicht darunter - libadwaita RECHNET sie
    seit 1.6 aus der Flaechenfarbe aus. `--dimmed-color` gibt es
    ueberhaupt nicht; 1.9 blendet mit `--dim-opacity` ab.

    Die Rechnung haengt an `--standalone-color-oklab`, die auf
    `min(l, 0.5)` steht - dem HELLEN Modus. GEMESSEN: AdwStyleManager
    meldet `dark: False`, und weder gtk-application-prefer-dark-theme
    noch gtk-theme-name in settings.ini aendern das (libadwaita setzt
    beide selbst). Ergebnis auf dem Petrol #0D3D47, nach WCAG 2.1:

        accent       ZepOS #33C9EE 6,04:1   gemalt #006F98 2,10:1
        success            #57D9A3 6,68:1          #007853 2,15:1
        warning            #FFCB00 7,77:1          #835C00 1,97:1
        error              #FF8A8A 5,21:1          #BA0823 1,77:1
        destructive        #FF8A8A 5,21:1          #BA0823 1,77:1

    Alle fuenf reissen die 4,5:1 fuer Text UND die 3:1 fuer Umrisse.

WAS DIESE DATEI BEWACHT
    Dass der :root-Block in gtk4-colors-config.template die Luecke
    schliesst und geschlossen HAELT - gemessen am echten Zeichner, mit
    Pixeln, nicht an der Zeichenkette in der Vorlage. Und dass er
    dabei keine zweite Quelle aufmacht: jede Variable traegt denselben
    Platzhalter wie die @define-color-Zeile darueber.

WAS SIE NICHT PRUEFT
    Ob nautilus GUT aussieht. Das kann nur ein Mensch. Und sie prueft
    nicht die inneren Knoten von nautilus - dass diese Datei KEINE
    Regel darauf schreibt, ist gerade der Punkt, und
    test_no_rule_bets_on_a_foreign_widget_tree haelt ihn fest.
"""
from __future__ import annotations

import json
import os
import re
import struct
import subprocess
import zlib
from pathlib import Path

import pytest

from tests.gtk4_headless import (broadwayd, gi_interpreter, start_broadwayd)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
TEMPLATE = SRC / "templates" / "gtk4-colors-config.template"

# Die fuenf, die ueber den alten Namen nicht ankommen, mit dem
# Platzhalter, der ihren Wert traegt. Ausgeschrieben und nicht aus der
# Vorlage gefiltert: eine Liste, die sich aus der geprueften Datei
# ergibt, ist mit jeder Fassung dieser Datei einverstanden - auch mit
# der, aus der jemand eine Zeile herausgenommen hat.
COMPUTED_BY_LIBADWAITA = {
    "accent-color": "STYLE_GTK4_ACCENT",
    "success-color": "STYLE_GTK4_SUCCESS",
    "warning-color": "STYLE_GTK4_WARNING",
    "error-color": "STYLE_GTK4_ERROR",
    "destructive-color": "STYLE_GTK4_ERROR",
}

# Die drei Bruecken, die libadwaita fuehrt und die die
# @define-color-Liste ausliess, und die vier, die nur im dunklen Modus
# gesetzt werden. Beide Gruppen standen damit auf Adwaitas Vorgabe.
WAS_LEFT_ON_ADWAITA = (
    "headerbar-darker-shade-color",
    "popover-shade-color",
    "secondary-sidebar-backdrop-color",
    "active-toggle-bg-color",
    "active-toggle-fg-color",
    "overview-bg-color",
    "overview-fg-color",
)

# Die Vorschrift, mit der libadwaita an vier Stellen lokal
# nachrechnet - unter anderem im Dateiauswaehler, den jede Anwendung
# aufmacht, die eine Datei oeffnet.
STANDALONE = "standalone-color-oklab"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _uncommented(text: str) -> str:
    """Die Vorlage ohne ihre Kommentare.

    Dieselbe Falle wie in tests/src/test_own_plugins.py: der Kopf dieser
    Vorlage ZITIERT die Zeile, um die es geht ("--accent-color:
    oklab(...)"), um zu erklaeren, warum sie nicht reicht. Ein
    `"--accent-color" in text` waere damit auch dann wahr, wenn der
    :root-Block ganz fehlte.
    """
    return _BLOCK_COMMENT.sub("", text)


def _read(path: Path) -> str:
    assert path.is_file(), f"{path} fehlt"
    return path.read_text(encoding="utf-8")


def _root_block(text: str) -> str:
    """Der Inhalt des :root-Blocks, ohne Kommentare."""
    body = _uncommented(text)
    match = re.search(r":root\s*\{(.*?)\n\}", body, re.DOTALL)
    assert match, (
        "gtk4-colors-config.template hat keinen :root-Block mehr. Ohne ihn "
        "sind fuenf Zustandsfarben und sieben weitere Namen wieder die von "
        "Adwaita - der Kopf der Vorlage fuehrt die Messung.")
    return match.group(1)


# --------------------------------------------------------------------
# Der Text: die Luecke ist benannt, und sie kommt aus derselben Quelle
# --------------------------------------------------------------------

@pytest.mark.parametrize("variable, placeholder",
                         sorted(COMPUTED_BY_LIBADWAITA.items()))
def test_every_colour_libadwaita_computes_is_written_out(variable, placeholder):
    """Die fuenf, die ueber @define-color nicht ankommen, stehen als
    Variable da - und mit DEMSELBEN Platzhalter wie ihr alter Name.

    Der zweite Halbsatz ist der wichtigere. Zwei Zeilen fuer eine Farbe
    sind nur dann keine zweite Quelle, wenn beide dieselbe Zahl holen;
    stuende in der einen der Platzhalter und in der anderen ein
    Literal, waere `zepos-settings set colors.overlay_accent` ein
    Regler, der die Haelfte bewegt.
    """
    block = _root_block(_read(TEMPLATE))
    assert f"--{variable}:" in block, (
        f"--{variable} fehlt im :root-Block. libadwaita rechnet sie dann "
        f"aus der Flaechenfarbe aus, im HELLEN Modus - gemessen 2,10:1 bis "
        f"1,77:1 auf dem Petrol, wo ZepOS 6,04:1 bis 5,21:1 wollte.")
    line = re.search(rf"--{variable}:\s*([^;]+);", block)
    assert line, f"--{variable} hat keinen Wert"
    assert line.group(1).strip() == "{{%s}}" % placeholder, (
        f"--{variable} traegt {line.group(1).strip()!r} statt des "
        f"Platzhalters {placeholder} - das ist eine zweite Quelle fuer "
        f"dieselbe Farbe")


@pytest.mark.parametrize("variable", WAS_LEFT_ON_ADWAITA)
def test_the_names_that_stood_on_adwaitas_default_are_set(variable):
    """Sieben Namen, die libadwaita liest und die alte Liste ausliess.

    Drei davon fuehrt libadwaita als Bruecke (es gibt 42, die Liste
    setzte 37), vier setzt es nur im dunklen Modus - der auf diesem
    Schreibtisch nicht greift. --overview-bg-color stand damit auf
    #f3f3f5, einem fast weissen Grau, in einem sonst petrolfarbenen
    Fenster.
    """
    block = _root_block(_read(TEMPLATE))
    assert f"--{variable}:" in block, (
        f"--{variable} fehlt - dieser Name faellt damit auf Adwaitas "
        f"Vorgabe zurueck")


def test_the_local_recomputation_is_pushed_to_the_dark_form():
    """`--standalone-color-oklab`, und warum eine Zeile fuer vier
    Stellen reicht.

    libadwaita rechnet die Zustandsfarben an vier Stellen NOCH EINMAL
    aus, nachdem es die Flaechenfarbe dort veraendert hat: in `.osd`,
    in `toast`, in `toggle-group.osd > toggle:checked` und im
    Dateiauswaehler. Die ersten drei setzen ihre eigene Vorschrift
    daneben. Der Dateiauswaehler erbt die von :root - und der geht auf,
    sobald irgendeine Anwendung eine Datei oeffnen laesst.
    """
    block = _root_block(_read(TEMPLATE))
    assert f"--{STANDALONE}:" in block, (
        "die Rechenvorschrift fehlt; der Dateiauswaehler faerbt seine "
        "Auswahl dann nach der hellen Formel")
    assert "max(l, 0.85)" in block, (
        "die Vorschrift steht nicht auf der dunklen Form. `min(l, 0.5)` "
        "ist die helle, und dieser Schreibtisch ist dunkel")


def test_no_rule_bets_on_a_foreign_widget_tree():
    """Der Satz, den der Kopf dieser Vorlage seit jeher fuehrt, als
    Pruefung: "Weil ein Selektor auf ein fremdes Fenster eine Wette auf
    dessen inneren Aufbau ist, und die verliert man bei der naechsten
    Version der Anwendung - lautlos".

    Der :root-Block ist dabei ausdruecklich KEIN Verstoss: :root ist
    libadwaitas eigener Anker, derselbe, an dem seine 42 Bruecken
    haengen, und kein Knoten von nautilus.

    Erlaubt ist deshalb genau EIN Selektor, und ein zweiter faellt hier
    um - egal ob er `.nautilus-pathbar` heisst oder `columnview >
    listview > row`.

    DIE PLATZHALTER MUESSEN VORHER WEG, UND ZWAR GEMESSEN
        `{{STYLE_GTK4_ACCENT}}` traegt geschweifte Klammern, und ohne
        diesen Schritt meldete die Pruefung 51 Selektoren - jede
        Variablenzeile des Blocks einmal. Sie waere damit nicht etwa zu
        streng gewesen, sondern unbrauchbar: eine Pruefung, die immer
        faellt, wird abgeschaltet und nicht gelesen.
    """
    body = _uncommented(_read(TEMPLATE))
    body = re.sub(r"\{\{[A-Z0-9_]+\}\}", "PLATZHALTER", body)
    # Alles vor einer geschweiften Klammer, das keine At-Regel ist.
    selectors = [match.strip()
                 for match in re.findall(r"(?m)^([^@\n{}][^{}\n]*)\{", body)]
    assert selectors == [":root"], (
        "diese Datei enthaelt Selektoren ausser :root: "
        f"{selectors}. Jeder davon ist eine Annahme ueber den inneren "
        "Aufbau einer Anwendung, die ZepOS nicht geschrieben hat - und "
        "eine CSS-Regel, die nichts trifft, meldet GTK nirgends.")


def test_the_two_halves_of_every_colour_agree():
    """Jede Variable im :root-Block traegt denselben Platzhalter wie
    ihr @define-color-Zwilling.

    Die allgemeine Fassung der Pruefung ganz oben, ueber alle Namen
    statt nur ueber die fuenf. Sie ist das, was den Block von einer
    zweiten Quelle unterscheidet.
    """
    text = _read(TEMPLATE)
    defines = dict(re.findall(r"(?m)^@define-color\s+(\w+)\s+([^;]+);", text))
    assert len(defines) >= 45, f"nur {len(defines)} @define-color-Zeilen"

    block = _root_block(text)
    variables = dict(re.findall(r"--([a-z-]+):\s*([^;]+);", block))

    disagree = []
    for name, value in sorted(defines.items()):
        variable = name.replace("_", "-")
        if variable not in variables:
            continue
        if variables[variable].strip() != value.strip():
            disagree.append(f"{name}: {value.strip()} vs "
                            f"--{variable}: {variables[variable].strip()}")
    assert disagree == [], (
        "diese Farben stehen zweimal mit VERSCHIEDENEN Werten da - das "
        "ist genau die zweite Quelle, die der Block nicht sein "
        "darf:\n" + "\n".join(disagree))


# --------------------------------------------------------------------
# Der echte Zeichner: Pixel, keine Zeichenketten
# --------------------------------------------------------------------

_CHILD = r'''
import sys
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk, GLib

Adw.init()
out, names = sys.argv[1], sys.argv[2].split(",")
provider = Gtk.CssProvider()
provider.load_from_string("\n".join(
    ".v-%s { background-color: var(--%s); }" % (n, n) for n in names))
Gtk.StyleContext.add_provider_for_display(
    Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

window = Gtk.Window()
box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
window.set_child(box)
widgets = {}
for name in names:
    probe = Gtk.Box()
    probe.add_css_class("v-%s" % name)
    probe.set_size_request(8, 8)
    box.append(probe)
    widgets[name] = probe
window.present()

context = GLib.MainContext.default()
for _ in range(300):
    while context.pending():
        context.iteration(False)

renderer = window.get_native().get_renderer()
for name, probe in widgets.items():
    paintable = Gtk.WidgetPaintable.new(probe)
    snapshot = Gtk.Snapshot()
    paintable.snapshot(snapshot, 8, 8)
    node = snapshot.to_node()
    if node is None:
        print("NONODE %s" % name)
        continue
    renderer.render_texture(node, None).save_to_png("%s/%s.png" % (out, name))
print("done")
'''


def _centre_pixel(path: Path) -> tuple[int, int, int]:
    """Das mittlere Pixel eines PNG, ohne eine neue Abhaengigkeit.

    Pillow ist in dieser Umgebung nicht da, und GdkPixbuf waere ein
    zweites gi-Kind fuer drei Zahlen. zlib und struct stehen in der
    Standardbibliothek; die fuenf Zeilenfilter von PNG sind der ganze
    Aufwand.
    """
    data = path.read_bytes()
    position, pixels = 8, b""
    width = height = depth = colour_type = 0
    while position < len(data):
        length = struct.unpack(">I", data[position:position + 4])[0]
        kind = data[position + 4:position + 8]
        chunk = data[position + 8:position + 8 + length]
        if kind == b"IHDR":
            width, height, depth, colour_type = struct.unpack(">IIBB",
                                                              chunk[:10])
        elif kind == b"IDAT":
            pixels += chunk
        position += 12 + length

    raw = zlib.decompress(pixels)
    per_pixel = {0: 1, 2: 3, 4: 2, 6: 4}[colour_type] * (depth // 8)
    stride = width * per_pixel
    out, previous, cursor = bytearray(), bytearray(stride), 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        line = bytearray(raw[cursor:cursor + stride])
        cursor += stride
        for index in range(stride):
            left = line[index - per_pixel] if index >= per_pixel else 0
            above = previous[index]
            corner = previous[index - per_pixel] if index >= per_pixel else 0
            if filter_type == 1:
                line[index] = (line[index] + left) & 255
            elif filter_type == 2:
                line[index] = (line[index] + above) & 255
            elif filter_type == 3:
                line[index] = (line[index] + (left + above) // 2) & 255
            elif filter_type == 4:
                estimate = left + above - corner
                distances = (abs(estimate - left), abs(estimate - above),
                             abs(estimate - corner))
                if distances[0] <= distances[1] and distances[0] <= distances[2]:
                    nearest = left
                elif distances[1] <= distances[2]:
                    nearest = above
                else:
                    nearest = corner
                line[index] = (line[index] + nearest) & 255
        out += line
        previous = line

    middle = (height // 2) * stride + (width // 2) * per_pixel
    return tuple(out[middle:middle + 3])


def _render(tmp_path: Path, scale: float) -> str:
    """Die Vorlage mit dem ECHTEN Generator erzeugen.

    In einem KIND und nicht hier im Prozess, anders als
    tests/src/test_own_plugins.py._render(): jene Datei laedt
    style_definition.py mit importlib in denselben Interpreter und
    haengt danach an monkeypatch, um subprocess.run wieder loszuwerden.
    Hier wird ohnehin ein Kind gebraucht (fuer gi), also kostet der Weg
    ueber die Umgebung nichts und laesst den Testprozess unberuehrt.
    """
    room = tmp_path / f"scale-{scale}"
    room.mkdir(parents=True, exist_ok=True)
    (room / "user-settings.json").write_text(
        json.dumps({"schema_version": 1, "sizes": {"scale": scale}}),
        encoding="utf-8")
    target = room / "gtk.css"

    environment = dict(os.environ)
    environment.pop("ZEPOS_SYSTEM_ROOT", None)
    environment["ZEPOS_USER_ROOT"] = str(room)
    environment["XDG_CONFIG_HOME"] = str(room)

    # Kein Compositor: die Werte sollen an den Einstellungen haengen und
    # nicht an einem angeschlossenen Schirm - wortgleiche Begruendung
    # wie in tests/src/test_sizes.py._no_compositor.
    code = "\n".join((
        "import importlib.util, subprocess, sys",
        f"sys.path.insert(0, {str(SRC)!r})",
        "def missing(cmd, **kwargs):",
        "    raise FileNotFoundError('hyprctl')",
        "subprocess.run = missing",
        "from pathlib import Path",
        "spec = importlib.util.spec_from_file_location(",
        f"    'zepos_style_probe_fm', {str(SRC / 'style_definition.py')!r})",
        "style = importlib.util.module_from_spec(spec)",
        "spec.loader.exec_module(style)",
        "import template_processor",
        "template_processor.ConfigProcessor(",
        "    styles=dict(style.STYLE_VARIABLES)).apply_template(",
        f"    Path({str(TEMPLATE)!r}), Path({str(target)!r}))",
    ))
    result = subprocess.run(["python3", "-c", code], env=environment,
                            capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    return target.read_text(encoding="utf-8")


@pytest.mark.allow_subprocess
def test_the_brand_reaches_libadwaita_where_it_did_not_before(tmp_path):
    """Die Messung selbst, als Pruefung: die fuenf gerechneten Farben
    kommen an, und die Flaechen kommen weiter an.

    Gegen den ECHTEN Zeichner und mit Pixeln. Eine Textpruefung kann
    hier grundsaetzlich nicht ausreichen: die Zeile
    `@define-color accent_color #33C9EE` sah zwoelf Monate lang richtig
    aus und wurde von libadwaita 1.6 an nicht mehr gelesen.
    """
    interpreter = gi_interpreter({"Gtk": "4.0", "Adw": "1"})
    if interpreter is None:
        pytest.skip("kein Interpreter hier kann gi/Gtk4/Adw laden")
    server = broadwayd()
    if server is None:
        pytest.skip("kein gtk4-broadwayd")
    executable, extra = interpreter

    css = _render(tmp_path, 1.0)
    assert "{{" not in css, "die erzeugte Datei traegt noch Platzhalter"

    # Die Werte, die drinstehen sollen, aus der erzeugten Datei selbst
    # gelesen: die Palette ist einstellbar, also darf hier keine
    # Zahl stehen. Was geprueft wird, ist die ANKUNFT.
    wanted = {}
    block = _root_block(css)
    for variable in sorted(COMPUTED_BY_LIBADWAITA):
        match = re.search(rf"--{variable}:\s*(#[0-9A-Fa-f]{{6}});", block)
        assert match, f"--{variable} steht nicht als Farbe in der Datei"
        value = match.group(1)
        wanted[variable] = tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
    for variable in ("window-bg-color", "view-bg-color"):
        match = re.search(rf"--{variable}:\s*(#[0-9A-Fa-f]{{6}});", block)
        value = match.group(1)
        wanted[variable] = tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))

    runtime = tmp_path / "run"
    runtime.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    config = tmp_path / "config"
    (config / "gtk-4.0").mkdir(parents=True)
    (config / "gtk-4.0" / "gtk.css").write_text(css, encoding="utf-8")

    display = 371
    process, _socket = start_broadwayd(server, runtime, display)
    try:
        environment = {"PATH": "/usr/bin", "XDG_RUNTIME_DIR": str(runtime),
                       "XDG_CONFIG_HOME": str(config),
                       "GDK_BACKEND": "broadway",
                       "BROADWAY_DISPLAY": f":{display}"}
        if extra:
            environment["PYTHONPATH"] = os.pathsep.join(extra)
        child = tmp_path / "probe.py"
        child.write_text(_CHILD, encoding="utf-8")
        result = subprocess.run(
            [executable, str(child), str(out), ",".join(sorted(wanted))],
            env=environment, capture_output=True, text=True, timeout=180)
        assert result.returncode == 0, result.stdout + result.stderr[-3000:]
        assert "NONODE" not in result.stdout, (
            "eine Variable loest nicht auf, die Flaeche blieb leer:\n"
            + result.stdout)
    finally:
        process.terminate()

    wrong = []
    for variable, expected in sorted(wanted.items()):
        painted = _centre_pixel(out / f"{variable}.png")
        if painted != expected:
            wrong.append(f"--{variable}: erwartet {expected}, gemalt {painted}")
    assert wrong == [], (
        "libadwaita malt nicht, was die erzeugte Datei sagt:\n"
        + "\n".join(wrong))


@pytest.mark.allow_subprocess
def test_the_measurement_would_notice_if_the_root_block_went_away(tmp_path):
    """Die Gegenprobe, ohne die die Pruefung darueber nichts wert ist.

    Sie nimmt dieselbe erzeugte Datei, streicht den :root-Block heraus
    und misst noch einmal. Kaeme dabei dasselbe heraus, waere der Block
    wirkungslos und die Pruefung darueber eine Tautologie ueber
    libadwaitas Vorgaben.

    NACHGEWIESEN am 12.08.2026: ohne den Block malt libadwaita
    #006F98 statt #33C9EE fuer den Akzent - die helle Ableitung aus der
    Flaechenfarbe, 2,10:1 auf dem Petrol statt 6,04:1.
    """
    interpreter = gi_interpreter({"Gtk": "4.0", "Adw": "1"})
    if interpreter is None:
        pytest.skip("kein Interpreter hier kann gi/Gtk4/Adw laden")
    server = broadwayd()
    if server is None:
        pytest.skip("kein gtk4-broadwayd")
    executable, extra = interpreter

    css = _render(tmp_path, 1.0)
    without = re.sub(r":root\s*\{.*?\n\}", "", css, flags=re.DOTALL)
    assert ":root" not in without, "der Block liess sich nicht entfernen"

    block = _root_block(css)
    match = re.search(r"--accent-color:\s*(#[0-9A-Fa-f]{6});", block)
    value = match.group(1)
    intended = tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))

    runtime = tmp_path / "run2"
    runtime.mkdir()
    out = tmp_path / "out2"
    out.mkdir()
    config = tmp_path / "config2"
    (config / "gtk-4.0").mkdir(parents=True)
    (config / "gtk-4.0" / "gtk.css").write_text(without, encoding="utf-8")

    display = 373
    process, _socket = start_broadwayd(server, runtime, display)
    try:
        environment = {"PATH": "/usr/bin", "XDG_RUNTIME_DIR": str(runtime),
                       "XDG_CONFIG_HOME": str(config),
                       "GDK_BACKEND": "broadway",
                       "BROADWAY_DISPLAY": f":{display}"}
        if extra:
            environment["PYTHONPATH"] = os.pathsep.join(extra)
        child = tmp_path / "probe2.py"
        child.write_text(_CHILD, encoding="utf-8")
        result = subprocess.run(
            [executable, str(child), str(out), "accent-color"],
            env=environment, capture_output=True, text=True, timeout=180)
        assert result.returncode == 0, result.stdout + result.stderr[-3000:]
    finally:
        process.terminate()

    painted = _centre_pixel(out / "accent-color.png")
    assert painted != intended, (
        "ohne den :root-Block malt libadwaita DIESELBE Farbe wie mit ihm. "
        "Dann traegt der Block nichts bei, und die Messung, auf die sich "
        "der Kopf dieser Datei beruft, gilt fuer diese Fassung von "
        "libadwaita nicht mehr.")
