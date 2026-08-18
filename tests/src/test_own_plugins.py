# SPDX-License-Identifier: GPL-3.0-or-later
"""Die zwei Plugins, deren Quelle am 11.08.2026 in diesen Baum gezogen ist.

WORUM ES GEHT
    Der Nutzer am 11.08.2026: "ich will das du auch den hyprlauncher
    customized aber als eigenes plugin und die anderen auch der
    clipboard manager usw." - im Rahmen von "wir wollen ein OS
    erstellen vergleichbar mit den anderen linux distro aber 100%
    custom".

    Vorher hiessen die Pakete zepos-hyprlaunch und zepos-hyprclipx und
    waren Nachbauten: packaging/ holte zur Bauzeit einen Tarball von
    github.com/azzuriel. Das Aussehen der beiden Fenster stand als
    `static const char* ...CSS` im uebersetzten Objekt, die
    Fenstermasse als `static constexpr` daneben. Beides konnte
    src/brand.py und src/sizes.py grundsaetzlich nicht erreichen.

WAS DIESE DATEI PRUEFT, UND WAS NICHT
    Sie misst Text und erzeugte Dateien, und an einer Stelle den
    ECHTEN Leser: test_the_vendored_parser_really_reads_the_generated
    _file uebersetzt plugins/hyprlaunch/src/ConfigParser.cpp und
    laesst es die Datei lesen, die der Generator geschrieben hat.

    Was sie nicht kann, ist das fertige Objekt gegen libgtk-4 messen -
    dafuer braucht es einen Bau. Das tun die beiden Rezepte selbst mit
    readelf und ldd, und hier wird festgehalten, DASS sie es tun; die
    Zahlen dieser Messung stehen in den Rezepten.

DIE FALLE, DIE DIESE DATEI VERMEIDET
    `"NAME" in datei` ist auch wahr, wenn NAME nur in einem Kommentar
    steht. Jede Datei in diesem Baum erklaert ausfuehrlich, was sie
    NICHT mehr tut - die Koepfe der beiden Renderer zitieren die
    Farbliterale, die sie losgeworden sind. Also laeuft jede Suche hier
    ueber _cpp_code() beziehungsweise _uncommented(), zeilengenau.
    NACHGEWIESEN: ohne das faellt schon die erste Zusicherung um, weil
    LauncherRenderer.cpp die Zeichenkette `R"CSS(` in seinem eigenen
    Kopf nennt, um zu erklaeren, dass sie weg ist.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import socket as socketlib
import subprocess
import time
from pathlib import Path

import pytest

from src import sizes
from tests.gtk4_headless import gi_interpreter

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
PLUGINS = ROOT / "plugins"
PACKAGING = ROOT / "packaging"

# Die zwei, die uebernommen wurden: Verzeichnis, Rezept, Objektname,
# Namensraum unter ~/.config.
ADOPTED = {
    "hyprlaunch": "zepos-hyprlaunch",
    "hyprclipx": "zepos-hyprclipx",
}

# Die drei, die bewusst nicht uebernommen wurden, mit dem Rezept, das
# sie weiterhin herunterlaedt. Ausgeschrieben und nicht aus dem
# Dateisystem gefiltert: eine Liste, die sich selbst aus dem Bestand
# ergibt, ist mit jedem Bestand einverstanden.
NOT_ADOPTED = {
    "hyprzones": "zepos-hyprzones",
    "hyprbars": "hyprland-plugins",
    "borders-plus-plus": "hyprland-plugins",
}

STYLE_TEMPLATES = {
    "hyprlaunch": SRC / "styles" / "hyprlaunch-style.template",
    "hyprclipx": SRC / "styles" / "hyprclipx-style.template",
}
CONFIG_TEMPLATES = {
    "hyprlaunch": SRC / "templates" / "hyprlaunch-config.template",
    "hyprclipx": SRC / "templates" / "hyprclipx-config.template",
}

# Die sieben Groessen, die mit dieser Aenderung in src/sizes.py
# dazugekommen sind. Ausgeschrieben, aus demselben Grund, aus dem
# tests/src/test_sizes.py seine skalierende Liste ausschreibt: aus der
# Tabelle gefiltert waere es eine Tautologie, die genau dann nichts mehr
# prueft, wenn jemand einen Eintrag herausnimmt.
NEW_SIZES = (
    "STYLE_LAUNCHER_WIDTH",
    "STYLE_LAUNCHER_SEARCH_HEIGHT",
    "STYLE_LAUNCHER_ROW_HEIGHT",
    "STYLE_LAUNCHER_ROW_MIN_HEIGHT",
    "STYLE_LAUNCHER_ICON_SIZE",
    "STYLE_CLIPBOARD_WIDTH",
    "STYLE_CLIPBOARD_HEIGHT",
)

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _read(path: Path) -> str:
    assert path.is_file(), f"{path} fehlt"
    return path.read_text(encoding="utf-8")


def _cpp_code(path: Path) -> list[tuple[int, str]]:
    """Die Zeilen einer C++-Datei, die kein Kommentar sind, mit Nummer.

    Zuerst /* ... */ heraus, dabei die Zeilenzahl erhalten, damit die
    Nummern in einer Fehlermeldung noch auf die Datei zeigen. Dann jede
    Zeile weg, die nach dem Einruecken mit // anfaengt.

    Was NICHT passiert, ist das Entfernen eines // mitten in der Zeile:
    das trifft `"https://..."` in einer Zeichenkette, und eine Pruefung,
    die dem eigenen Werkzeug nicht trauen kann, ist keine.
    """
    text = _BLOCK_COMMENT.sub(
        lambda m: "\n" * m.group(0).count("\n"), _read(path))
    return [(number, line)
            for number, line in enumerate(text.splitlines(), start=1)
            if not line.lstrip().startswith("//")]


def _uncommented(text: str, marker: str = "#") -> list[str]:
    """Wortgleich zu tests/src/test_gtk4_only.py, aus demselben Grund."""
    return [line.strip() for line in text.splitlines()
            if not line.lstrip().startswith(marker)]


def _sources(name: str) -> list[Path]:
    root = PLUGINS / name
    return sorted(list((root / "src").glob("*.cpp"))
                  + list((root / "include").rglob("*.hpp")))


def _pkgbuild(recipe: str) -> str:
    return _read(PACKAGING / recipe / "PKGBUILD")


def _pkgbuild_code(recipe: str) -> str:
    return "\n".join(_uncommented(_pkgbuild(recipe)))


# --------------------------------------------------------------------
# Die Quelle liegt hier
# --------------------------------------------------------------------

@pytest.mark.parametrize("name, recipe", sorted(ADOPTED.items()))
def test_the_adopted_source_is_in_this_tree(name, recipe):
    """Das erste Stueck des Auftrags: "Ihre Quelle gehoert in dieses
    Repository, nicht in ein Tarball von einem fremden Konto."

    GEMESSEN am 11.08.2026 an der GitHub-API, fuer beide Baeume: Tags 0,
    Forks 0, Beitragende 1, "license": null. Verschwindet das Konto,
    laesst sich ZepOS an der Stelle nicht mehr bauen, die den
    Anwendungsstarter und die Zwischenablage liefert.
    """
    root = PLUGINS / name
    assert (root / "CMakeLists.txt").is_file(), (
        f"plugins/{name}/CMakeLists.txt fehlt")
    assert (root / "src").is_dir() and (root / "include").is_dir(), (
        f"plugins/{name} hat keine Quelle")
    assert _sources(name), f"plugins/{name} enthaelt keine Uebersetzungseinheit"

    code = _pkgbuild_code(recipe)
    # Der eigene Baum darf genannt werden - url= zeigt auf ihn. Was
    # nicht mehr vorkommen darf, ist der Ursprungsbaum dieses Plugins:
    # daraus wurde bis zum 11.08.2026 zur Bauzeit heruntergeladen.
    assert f"github.com/azzuriel/{name}" not in code, (
        f"packaging/{recipe} holt seine Quelle weiterhin aus dem fremden "
        f"Ursprungsbaum")
    assert "http" not in code.split("source=(", 1)[1].split(")", 1)[0], (
        f"packaging/{recipe} laedt seine Quelle aus dem Netz")
    assert f'source=("zepos-{name}-$pkgver.tar.gz")' in code, (
        f"packaging/{recipe} baut nicht aus dem Arbeitsbaum")


def test_the_working_tree_tarballs_are_actually_made():
    """Ein Rezept, das einen lokalen Tarball nennt, den niemand
    erzeugt, scheitert erst im Bau - und dann mit "file not found",
    das nicht sagt, welcher Schritt fehlt."""
    build = _read(PACKAGING / "build.sh")
    code = "\n".join(_uncommented(build))

    assert 'rsync -a "$REPO/plugins/$_plugin"/ "$stage"/' in code, (
        "packaging/build.sh macht aus plugins/ keinen Quelltarball")
    assert 'rsync -a "$REPO/plugins/LICENSE" "$stage/LICENSE"' in code, (
        "der BSD-Vermerk kommt nicht in den Tarball; das Rezept legt "
        "dann eine Datei ab, die es nicht gibt, oder - schlimmer - die "
        "GPL dieses Baums als Auskunft ueber fremden Code")
    assert 'for _plugin in hyprlaunch hyprclipx; do' in code, (
        "die Schleife nennt nicht beide Plugins")


@pytest.mark.parametrize("plugin, recipe", sorted(NOT_ADOPTED.items()))
def test_what_was_deliberately_left_upstream_is_still_pinned(plugin, recipe):
    """Ein begruendetes "bleibt wie es ist" ist ein Ergebnis, und es
    muss nachpruefbar sein, dass es dabei geblieben ist.

    hyprbars und borders-plus-plus kommen aus hyprwm/hyprland-plugins,
    dem Baum des Hyprland-Projekts selbst. GEMESSEN am 11.08.2026:
    1433 Sterne, 190 Forks, 69 Beitragende, eine echte LICENSE-Datei,
    die GitHub als BSD-3-Clause erkennt, und Tags im Gleichschritt mit
    dem Compositor (v0.55.0, v0.56.0). Sie haben ausserdem keine eigene
    Oberflaeche - hyprbars zeichnet mit dem Renderer des Compositors -,
    also gibt es nichts, was auf die Marke zu bringen waere. Uebernehmen
    hiesse, die Pflege von 69 Leuten selbst zu leisten, fuer null
    gestalterischen Gewinn.

    hyprzones ist der schaerfere Fall, weil es von demselben Konto
    kommt wie die zwei uebernommenen. Es bleibt trotzden draussen, und
    zwar aus drei gemessenen Gruenden:

      * Es hat keine GTK4-Oberflaeche. Sein Editor ist AGS/TypeScript
        und wird von packaging/zepos-hyprzones ausdruecklich NICHT
        ausgeliefert - SUPER+SHIFT+Z oeffnet heute nichts. Der Auftrag
        lautete, die Oberflaechen auf die Marke zu bringen; hier ist
        keine.
      * Es haengt am tiefsten am Compositor. GEZAEHLT an Commit
        73171c7: 52 Zeilen mit Hyprland-API in src/main.cpp von 606,
        17 in src/Renderer.cpp von 217, dazu DragState.hpp und
        Globals.hpp - es haengt sich in den Renderpass und in die
        Fensterablage. Zum Vergleich: hyprlaunch hat 17 solche Zeilen,
        alle in einer Datei von 139.
      * Sein Ausfall kostet keine Taste, die der Nutzer braucht.
        src/plugins.py laesst seinen Block ersatzlos weg, und
        src/templates/hyprland-plugins-config.template hat fuer
        hyprzones bewusst KEINEN zepos-plugin-missing-Zweig, waehrend
        die anderen beiden einen haben.

    Was damit offen bleibt und nicht verschwiegen wird: die
    Verfuegbarkeit. Verschwindet das Konto, faellt hyprzones aus dem
    Bau. Der Unterschied zu vorher ist, dass dann der Schreibtisch
    seine Zonen verliert und nicht seinen Starter.
    """
    assert not (PLUGINS / plugin).exists(), (
        f"plugins/{plugin} ist da - dann ist die Entscheidung eine "
        f"andere geworden und diese Begruendung gehoert umgeschrieben")

    text = _pkgbuild(recipe)
    match = re.search(r"^_commit=([0-9a-f]+)$", text, re.M)
    assert match, f"packaging/{recipe} pinnt keinen Commit"
    assert len(match.group(1)) == 40, (
        f"packaging/{recipe} pinnt eine gekuerzte Kennung")
    assert re.search(r"sha256sums=\('[0-9a-f]{64}'", text), (
        f"packaging/{recipe} laedt herunter und prueft keine Summe")


# --------------------------------------------------------------------
# Die Lizenz
# --------------------------------------------------------------------

def test_the_licence_file_records_the_permission_and_claims_no_licence():
    """Was plugins/LICENSE sagen darf und was nicht.

    HIER STAND EIN VOLLSTAENDIGER BSD-3-CLAUSE-TEXT AUF JAN OHLMANNS
    NAMEN, und dieser Test verlangte ihn.

    Er war beim Uebernehmen der Quellen entstanden, aus einer
    nachvollziehbaren Ueberlegung: die Rezepte behaupteten seit jeher
    license=('BSD-3-Clause'), BSD-3 verlangt beim Weitergeben einen
    Urhebervermerk, und den gab es nirgends - also wurde er
    "erstmals ausgeschrieben".

    Die Ueberlegung hatte eine falsche Voraussetzung. GEMESSEN am
    11.08.2026 an beiden Ursprungsbaeumen: keine LICENSE-Datei, kein
    einziges "Copyright", GitHubs API meldet "license": null. Es gab
    keine BSD-3-Lizenz, die einen Vermerk verlangt haette. Der Text hat
    also nicht eine Bedingung erfuellt, sondern eine Lizenz behauptet,
    die der Rechteinhaber nie erteilt hat - und zwar in seinem Namen.
    Das ist der schwerere der beiden Fehler.

    Was stattdessen wahr ist und hier stehen muss: wem der Code gehoert,
    aus welchem Stand er stammt, dass eine Erlaubnis vorliegt, wer sie
    gegeben hat - und dass eine Erlaubnis keine Lizenz ist. Wer ZepOS
    installiert, bekommt diesen Code aus unserer Hand und muss erfahren,
    was ER damit darf.
    """
    licence = _read(PLUGINS / "LICENSE")

    # Keine Lizenz im Namen eines Dritten. Der Bedingungstext von BSD-3
    # ist daran zu erkennen, dass er Bedingungen STELLT.
    for behauptung in ("BSD 3-Clause License",
                       "Redistribution and use in source and binary forms",
                       "THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS"):
        assert behauptung not in licence, (
            f"plugins/LICENSE behauptet wieder eine Lizenz, die der "
            f"Rechteinhaber nicht erteilt hat: {behauptung!r}")

    # Wem es gehoert - mit dem Namen, nicht nur dem Kontonamen in einer
    # URL. GEMESSEN in der Mutationspruefung des Vorgaengers: der Test
    # `"azzuriel" in licence` ueberlebte das Entfernen des Vermerks, weil
    # der Kontoname weiter unten in den URLs steht.
    assert "Jan Ohlmann" in licence, (
        "der Urheber der uebernommenen Quellen ist nicht beim Namen "
        "genannt")

    # Aus welchem Stand.
    for commit in ("24e5c8b82f96f87ac25000353e36a8b17ced4b00",
                   "1eed6ee90a1c3e48ec76510377f8b05f27a4e650"):
        assert commit in licence, (
            f"der Stand {commit[:7]}, aus dem uebernommen wurde, fehlt")

    # Dass eine Erlaubnis vorliegt, von wem, und wann.
    assert "Leon Marzoll" in licence and "11.08.2026" in licence, (
        "die Erlaubnis ist nicht mit Geber und Datum festgehalten")

    # Und der Unterschied, um den es geht.
    assert "ersetzt keine Lizenz" in licence, (
        "plugins/LICENSE sagt nicht, dass eine Erlaubnis keine Lizenz "
        "ist - genau diese Verwechslung hat den ersten Text erzeugt")


def test_the_recipes_do_not_claim_a_licence_the_upstream_never_gave():
    """Die andere Haelfte desselben Fehlers.

    Die drei Rezepte trugen license=('BSD-3-Clause') - vermutlich
    mitgewandert von packaging/hyprland-plugins, das vom
    Hyprland-Projekt kommt und wirklich so lizenziert ist. 'custom'
    beschreibt die Lage; BSD-3 behauptet Bedingungen, die niemand
    gestellt hat.
    """
    for rezept in ("zepos-hyprlaunch", "zepos-hyprclipx", "zepos-hyprzones"):
        text = _read(PACKAGING / rezept / "PKGBUILD")
        zeilen = [z for z in text.splitlines() if z.startswith("license=")]
        assert zeilen == ["license=('custom')"], (
            f"{rezept} behauptet {zeilen} statt 'custom' - die Quelle "
            f"traegt keine Lizenz")


def test_the_window_sizes_left_the_compiled_object():
    """Die drei `static constexpr` des Starters und die angenommene
    Zeilenhoehe des Verlaufs.

    Solange sie im Objekt standen, konnte `zepos-settings set
    sizes.scale 2.0` die Schrift verdoppeln und die Zeile, die sie
    traegt, stehen lassen. Genau diesen Fehler schreibt src/sizes.py
    fuer die Leistenhoehe schon auf.
    """
    launcher = PLUGINS / "hyprlaunch" / "include" / "hyprlaunch" / "Config.hpp"
    code = "\n".join(line for _, line in _cpp_code(launcher))

    for gone in ("static constexpr int SEARCH_HEIGHT",
                 "static constexpr int ITEM_HEIGHT",
                 "static constexpr int CHROME"):
        assert gone not in code, (
            f"{gone} steht wieder im Objekt statt in der erzeugten Datei")

    for field in ("int searchHeight", "int itemHeight", "int chrome",
                  "int windowWidth", "int iconSize"):
        assert field in code, (
            f"{field} fehlt - dann liest das Programm die erzeugte Datei "
            f"nicht mehr vollstaendig")

    clip = (PLUGINS / "hyprclipx" / "include" / "hyprclipx"
            / "ClipboardRenderer.hpp")
    clip_code = "\n".join(line for _, line in _cpp_code(clip))
    assert "static constexpr int ITEM_HEIGHT" not in clip_code, (
        "die angenommene Zeilenhoehe von 28 Pixeln ist zurueck. Sie war "
        "richtig, solange das Aussehen im Objekt stand; mit einem "
        "Stylesheet, dessen Schrift dem Faktor folgt, scrollt die Liste "
        "um denselben Faktor daneben")

    renderer = PLUGINS / "hyprclipx" / "src" / "ClipboardRenderer.cpp"
    render_code = "\n".join(line for _, line in _cpp_code(renderer))
    assert "gtk_widget_compute_bounds" in render_code, (
        "die Zeilenhoehe wird nicht gemessen. Der Starter macht es seit "
        "jeher so, und eine gemessene Hoehe kann bei keinem Faktor "
        "falsch sein")


def test_the_launcher_cannot_grow_past_the_screen():
    """Die Gegenrichtung zum ganzen Auftrag, und sie ist gemessen.

    Ein Starter, der beim Drehen des Reglers nicht mitwaechst, ist
    kaputt. Einer, der aus dem Bild waechst, ist es auch: bei dem
    ausgelieferten Faktor 1.85 ergaeben 20 Zeilen 96 + 20*83 + 9 = 1765
    Pixel, also anderthalb Bildschirmhoehen auf einem 1080er Schirm.
    """
    config = PLUGINS / "hyprlaunch" / "include" / "hyprlaunch" / "Config.hpp"
    code = "\n".join(line for _, line in _cpp_code(config))
    assert "int rowsThatFit(int availableHeight) const" in code, (
        "die Zeilenzahl wird nicht gegen den Schirm gedeckelt")

    renderer = PLUGINS / "hyprlaunch" / "src" / "LauncherRenderer.cpp"
    render_code = "\n".join(line for _, line in _cpp_code(renderer))
    assert "fittingHeight()" in render_code, (
        "das Fenster benutzt die gedeckelte Hoehe nicht")
    assert "gdk_display_get_monitors" in render_code, (
        "gedeckelt wird gegen nichts Gemessenes")

    # Und die Rechnung selbst, damit die Behauptung oben nicht bloss
    # eine Behauptung ist: bei einer verfuegbaren Hoehe von 1080 und
    # den Werten, die der Faktor 1.85 erzeugt, passen weniger als die
    # eingestellten zwanzig Zeilen.
    search, item, chrome, wanted = 96, 83, 9, 20
    fits = (1080 - search - chrome) // item
    assert 1 <= fits < wanted, (
        f"die Rechnung, auf der der Deckel steht, stimmt nicht mehr: "
        f"{fits} Zeilen von {wanted}")


# --------------------------------------------------------------------
# Der Regler bewegt wirklich etwas
# --------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(NEW_SIZES))
def test_every_new_size_is_in_the_table_and_read_by_a_template(name):
    """Die billige Haelfte, hier fuer die sieben neuen Eintraege
    einzeln. Die teure - der Wert steht danach anders in der Datei -
    macht tests/src/test_sizes.py fuer die ganze Tabelle."""
    assert name in sizes.TABLE, f"{name} steht nicht in sizes.TABLE"

    needle = "{{" + name + "}}"
    readers = [path for path in
               list(CONFIG_TEMPLATES.values()) + list(STYLE_TEMPLATES.values())
               if needle in _read(path)]
    assert readers, (
        f"{name} ist einstellbar und wird von keiner der vier Vorlagen "
        f"gelesen - genau der Zustand, in dem MONITOR_HEIGHT_SCALES war")


def test_the_icon_is_a_picture_and_does_not_follow_the_factor():
    """Die Grenze, die src/sizes.py zwischen Schrift und Bild zieht,
    gilt auch hier. Das Anwendungssymbol kommt aus dem Symbolthema
    eines fremden Pakets; mit dem Faktor 1.85 waere es 67 Pixel hoch in
    einer Zeile von 83."""
    assert not sizes.TABLE["STYLE_LAUNCHER_ICON_SIZE"].scales, (
        "das Anwendungssymbol ist als schriftfolgend eingetragen")
    for name in ("STYLE_LAUNCHER_WIDTH", "STYLE_LAUNCHER_ROW_HEIGHT",
                 "STYLE_LAUNCHER_ROW_MIN_HEIGHT",
                 "STYLE_LAUNCHER_SEARCH_HEIGHT",
                 "STYLE_CLIPBOARD_WIDTH", "STYLE_CLIPBOARD_HEIGHT"):
        assert sizes.TABLE[name].scales, (
            f"{name} umschliesst Text und folgt dem Faktor nicht")


def _render(tmp_path, monkeypatch, template: Path, scale: float) -> str:
    """Eine Vorlage mit einem bestimmten Faktor erzeugen.

    Mit dem ECHTEN ConfigProcessor und der ECHTEN Stil-SSOT, so wie
    tests/src/test_sizes.py es macht: ein str.replace() dieses Tests
    wuerde die eigene Ersetzung messen und nicht die, die auf der
    Maschine des Nutzers laeuft.
    """
    room = tmp_path / f"scale-{scale}"
    room.mkdir(parents=True, exist_ok=True)
    (room / "user-settings.json").write_text(
        json.dumps({"schema_version": 1, "sizes": {"scale": scale}}),
        encoding="utf-8")

    monkeypatch.delenv("ZEPOS_SYSTEM_ROOT", raising=False)
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(room))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(room))
    monkeypatch.syspath_prepend(str(SRC))

    # Kein Compositor, damit die Werte allein an den Einstellungen
    # haengen - wortgleich zu tests/src/test_sizes.py._no_compositor.
    def missing(cmd, **kwargs):
        raise FileNotFoundError("hyprctl")

    monkeypatch.setattr(subprocess, "run", missing)

    spec = importlib.util.spec_from_file_location(
        f"zepos_style_probe_plugins_{scale}", SRC / "style_definition.py")
    style = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(style)

    import template_processor

    target = room / template.stem
    template_processor.ConfigProcessor(
        styles=dict(style.STYLE_VARIABLES)).apply_template(template, target)
    return target.read_text(encoding="utf-8")


# Die Schluessel der erzeugten Konfiguration, die dem Faktor folgen
# MUESSEN. Ausgeschrieben und je Programm, weil genau hier die Falle
# liegt, die tests/src/test_sizes.py schon einmal beschrieben hat:
# "Ohne diese Zeile genuegte es, dass IRGENDEIN Wert sich bewegt."
#
# NACHGEWIESEN in der Mutationspruefung: die erste Fassung dieses Tests
# verglich die ganzen Dateien, und die Mutation, die BEIDE Fenstermasse
# des Verlaufs durch Zahlen ersetzte, ging glatt durch - die
# Abstandsleiter in derselben Datei bewegte sich ja weiterhin.
GEOMETRY_KEYS = {
    "hyprlaunch": ("window_width", "item_height", "search_height"),
    "hyprclipx": ("window_width", "window_height"),
}


def _key_values(text: str) -> dict[str, str]:
    return dict(re.findall(r"^([a-z_0-9]+)\s*=\s*(\S+)$", text, re.M))


@pytest.mark.parametrize("name", sorted(ADOPTED))
def test_turning_the_knob_changes_both_generated_files(name, tmp_path,
                                                       monkeypatch):
    """Der Nachweis, den der Auftrag ausdruecklich verlangt: erzeugen
    mit einem anderen Skalenwert, und die erzeugte Datei muss sich
    aendern.

    Fuer BEIDE Dateien je Programm - Konfiguration und Stylesheet -,
    weil eine davon zu aendern reichte, wenn nur eine geprueft wuerde.
    Und bei der Konfiguration Schluessel fuer Schluessel statt Datei
    gegen Datei, aus dem Grund, der bei GEOMETRY_KEYS steht.
    """
    for template in (CONFIG_TEMPLATES[name], STYLE_TEMPLATES[name]):
        small = _render(tmp_path / template.stem, monkeypatch, template, 1.0)
        large = _render(tmp_path / template.stem, monkeypatch, template, 2.0)
        assert small != large, (
            f"{template.name} sieht bei Faktor 1.0 und 2.0 gleich aus - "
            f"der Regler erreicht diese Datei nicht")

    config = CONFIG_TEMPLATES[name]
    before = _key_values(_render(tmp_path / "geo", monkeypatch, config, 1.0))
    after = _key_values(_render(tmp_path / "geo", monkeypatch, config, 2.0))

    for key in GEOMETRY_KEYS[name]:
        assert key in before, f"{config.name} nennt {key} nicht mehr"
        assert before[key] != after[key], (
            f"{key} steht bei Faktor 1.0 und 2.0 auf {before[key]} - "
            f"das Fenster waechst mit der Schrift nicht mit, und genau "
            f"das war der Auftrag")

    # Und die Gegenrichtung, damit "alles bewegt sich" nicht die
    # Antwort wird: das Anwendungssymbol ist ein Bild und steht still.
    if name == "hyprlaunch":
        assert before["icon_size"] == after["icon_size"], (
            "das Anwendungssymbol waechst mit der Schrift - die Grenze "
            "zwischen SCALED und FIXED aus src/sizes.py gilt auch hier")


@pytest.mark.parametrize("name", sorted(ADOPTED))
def test_the_generated_configuration_carries_the_whole_ladder(name, tmp_path,
                                                              monkeypatch):
    """Alle sieben Sprossen, nicht nur die drei, die heute gebraucht
    werden: eine Leiter, von der die Haelfte fehlt, laedt dazu ein,
    beim naechsten Kasten wieder eine Zahl hinzuschreiben.

    Je Programm, und das ist nicht Formsache: die erste Fassung dieser
    Pruefung sah nur in die Datei des Starters, und die
    Mutationspruefung hat eine geloeschte Sprosse in der Datei des
    Verlaufs ueberleben lassen.
    """
    text = _render(tmp_path, monkeypatch, CONFIG_TEMPLATES[name], 1.0)
    written = {int(rung): value for rung, value in
               re.findall(r"^space_(\d+)\s*=\s*(\S+)$", text, re.M)}

    assert sorted(written) == sorted(sizes.SPACE_LADDER), (
        f"die erzeugte Datei traegt die Sprossen {sorted(written)}, "
        f"die Leiter hat {sorted(sizes.SPACE_LADDER)}")
    # Bei Faktor 1.0 ist ein Full-HD-Pixel ein Pixel, also traegt jede
    # Sprosse ihren eigenen Grundwert. Das ist die Probe darauf, dass
    # hier wirklich die Leiter steht und nicht sieben Zufallszahlen.
    for rung, value in written.items():
        assert value == f"{rung}px", (
            f"Sprosse {rung} traegt bei Faktor 1.0 den Wert {value}")


# --------------------------------------------------------------------
# Der echte Leser
# --------------------------------------------------------------------

_PROBE = r"""
#include "%(ns)s/ConfigParser.hpp"
#include <cstdio>

int main() {
    %(ns)s::Config c = %(ns)s::loadConfig();
    std::printf("path=%%s\n", %(ns)s::getConfigPath().c_str());
    std::printf("style=%%s\n", c.styleSheet.c_str());
    std::printf("width=%%d\n", c.windowWidth);
    %(extra)s
    std::printf("space12=%%d\n", c.space(12));
    std::printf("space99=%%d\n", c.space(99));
    return 0;
}
"""


@pytest.mark.allow_subprocess
@pytest.mark.parametrize("name", sorted(ADOPTED))
def test_the_vendored_parser_really_reads_the_generated_file(name, tmp_path,
                                                             monkeypatch):
    """Die eine Stelle, an der diese Datei nicht Text misst.

    Alles darueber prueft, dass die richtigen Zeichen an den richtigen
    Stellen stehen. Das hier uebersetzt den ECHTEN Leser -
    plugins/<name>/src/ConfigParser.cpp - und laesst ihn die Datei
    lesen, die der ECHTE Generator geschrieben hat. Ohne diesen Schritt
    waere die ganze Kette eine Vermutung: ein Platzhalter, der sauber
    ersetzt wird, in einer Datei, die niemand liest, sieht in jeder
    Textpruefung richtig aus.

    Der Rueckfall am Ende ist die zweite Haelfte: space(99) fragt nach
    einer Sprosse, die die erzeugte Datei nicht kennt, und muss ihren
    eigenen Grundwert zurueckgeben statt 0. Ein Abstand, der still zu
    null wird, ist genau die Sorte Fehler, die niemand meldet.
    """
    compiler = shutil.which("g++") or shutil.which("c++")
    if compiler is None:
        pytest.skip("kein C++-Uebersetzer - der echte Leser ist nicht baubar")

    # Festgehalten, BEVOR _render() subprocess.run gegen ein
    # FileNotFoundError tauscht. Der Tausch gehoert dorthin - die Werte
    # sollen allein an den Einstellungen haengen und nicht an einem
    # angeschlossenen Compositor -, und er ueberlebt die Funktion, weil
    # monkeypatch bis zum Testende gilt. Ohne diese Zeile scheitert der
    # Uebersetzeraufruf danach mit "hyprctl". GEMESSEN, genau so.
    real_run = subprocess.run

    # NICHT bei Faktor 1.0, und das ist der Unterschied zwischen einer
    # Pruefung und einer, die durchgeht.
    #
    # GEMESSEN in der Mutationspruefung: bei 1.0 traegt jede Sprosse
    # ihren eigenen Grundwert, und Config::space() gibt bei einer
    # Sprosse, die es nicht in die Datei geschafft hat, ebenfalls den
    # Grundwert zurueck. Die Mutation "parseInt streift das px nicht
    # mehr ab" liess also jede Sprosse durchfallen - und die Antwort
    # war trotzdem richtig, weil der Rueckfall dieselbe Zahl liefert.
    #
    # Bei 2.0 ist die Sprosse 12 vierundzwanzig Pixel breit und ihr
    # Grundwert zwoelf. Jetzt sagt die Antwort, ob die Datei wirklich
    # gelesen wurde.
    scale = 2.0
    section = {"scale": scale}
    room = tmp_path / "home"
    (room / name).mkdir(parents=True)
    generated = _render(tmp_path / "render", monkeypatch,
                        CONFIG_TEMPLATES[name], scale)
    (room / name / "config").write_text(generated, encoding="utf-8")

    extra = ('std::printf("rows=%d\\n", c.rowsThatFit(1080));'
             if name == "hyprlaunch"
             else 'std::printf("height=%d\\n", c.windowHeight);')
    probe = tmp_path / "probe.cpp"
    probe.write_text(_PROBE % {"ns": name, "extra": extra}, encoding="utf-8")

    binary = tmp_path / "probe"
    build = real_run(
        [compiler, "-std=c++20", "-I", str(PLUGINS / name / "include"),
         str(probe), str(PLUGINS / name / "src" / "ConfigParser.cpp"),
         "-o", str(binary)],
        capture_output=True, text=True)
    assert build.returncode == 0, (
        f"der Leser von plugins/{name} uebersetzt nicht mehr:\n"
        f"{build.stderr}")

    run = real_run([str(binary)], capture_output=True, text=True,
                   env={**os.environ, "XDG_CONFIG_HOME": str(room),
                        "HOME": str(room)})
    assert run.returncode == 0, run.stderr
    answer = dict(line.split("=", 1)
                  for line in run.stdout.splitlines() if "=" in line)

    assert answer["path"] == str(room / name / "config"), (
        "der Leser sucht die Datei woanders, als der Generator sie "
        "schreibt - src/generate_config.sh und ConfigParser.cpp sind "
        "auseinandergelaufen")
    assert answer["style"] == str(room / name / "style.css")

    # Die erwarteten Zahlen kommen aus sizes.value_of(), also aus
    # derselben Rechnung, die auch die Datei gefuellt hat - nicht aus
    # einer zweiten, die dieser Test selbst anstellt.
    width_name = ("STYLE_LAUNCHER_WIDTH" if name == "hyprlaunch"
                  else "STYLE_CLIPBOARD_WIDTH")
    expected_width = sizes.value_of(width_name, section)
    assert answer["width"] == expected_width, (
        f"der Leser bekommt {answer['width']} statt {expected_width} - "
        f"die erzeugte Datei kommt nicht an")

    expected_rung = sizes.value_of(f"{sizes.SPACE_PREFIX}12", section)
    assert expected_rung.endswith("px") and expected_rung != "12px", (
        "der Faktor dieses Tests bewegt die Sprosse nicht mehr; dann "
        "prueft die naechste Zeile nichts")
    assert answer["space12"] == expected_rung.removesuffix("px"), (
        f"die Sprosse 12 kommt als {answer['space12']} an statt als "
        f"{expected_rung.removesuffix('px')}. Der Wert traegt in der "
        f"erzeugten Datei ein px, weil derselbe Platzhalter das "
        f"Stylesheet fuellt; parseInt() soll es abstreifen - und wenn "
        f"es das nicht tut, faellt space() auf den Grundwert 12 zurueck")
    assert answer["space99"] == "99", (
        "eine unbekannte Sprosse faellt nicht auf ihren Grundwert "
        "zurueck")

    if name == "hyprlaunch":
        # Der Deckel, an der Rechnung gemessen statt an einer Zahl von
        # Hand: bei diesem Faktor passen weniger als die eingestellten
        # zwanzig Zeilen auf einen 1080er Schirm.
        item = int(sizes.value_of("STYLE_LAUNCHER_ROW_HEIGHT", section))
        search = int(sizes.value_of("STYLE_LAUNCHER_SEARCH_HEIGHT", section))
        expected_rows = (1080 - search - 9) // item
        assert 1 <= expected_rows < 20
        assert answer["rows"] == str(expected_rows), (
            f"der Deckel liefert {answer['rows']} Zeilen statt "
            f"{expected_rows}")


# --------------------------------------------------------------------
# Der Rueckfall bleibt heil
# --------------------------------------------------------------------

def test_the_failsafe_still_covers_both_surfaces():
    """src/plugins.py laesst den Block eines Plugins weg, dessen Objekt
    fehlt, und schreibt an seine Stelle einen Kommentar. Fuer die zwei
    Tasten, die der Nutzer taeglich drueckt, gibt es zusaetzlich einen
    zepos-plugin-missing-Zweig mit einem Ersatz.

    Beides musste diese Aenderung ueberstehen: die Uebernahme aendert,
    WOHER das Objekt kommt, und nichts daran, was passiert, wenn es
    fehlt.
    """
    from src import plugins

    template = _read(SRC / "templates" / "hyprland-plugins-config.template")

    for name in ADOPTED:
        assert name in plugins.PLUGINS, (
            f"{name} steht nicht mehr auf der Liste, die src/plugins.py "
            f"prueft")
        assert f"# zepos-plugin {name}" in template
        assert f"# zepos-plugin-missing {name}" in template, (
            f"{name} hat keinen Rueckfall mehr - seine Taste waere tot, "
            f"sobald das Objekt fehlt")
        assert plugins.package(name) == ADOPTED[name], (
            "der Paketname, den der Kommentar dem Nutzer nennt, ist nicht "
            "der des Rezepts")

    # Und die Gegenprobe: hyprzones hat bewusst keinen, und das ist
    # keine Luecke. Stuende hier einer, waere er ein Rueckfall auf
    # nichts - es gibt kein zweites Programm, das Zonen kann.
    assert "# zepos-plugin-missing hyprzones" not in template

    rendered = plugins.render(template, reasons={
        name: "Pruefung" for name in ADOPTED})
    assert "hyprlaunch:toggle" not in rendered, (
        "der Dispatcher des fehlenden Plugins steht weiterhin in der "
        "erzeugten Datei - Hyprland bricht darauf die Konfiguration ab")
    # `--show all` und nicht mehr `--show drun`: ohne das Plugin ist
    # dieses Fenster das einzige, das auf eine getippte Zeichenkette
    # antwortet, und seit dem 12.08.2026 kennt es neben den Anwendungen
    # jede beschriebene Tastenbindung. Wer den Starter oeffnet, weil er
    # etwas SUCHT, findet es dann auch, wenn es keine Anwendung ist -
    # genau der Fall aus der Beschwerde "das Bildschirmfoto-Werkzeug
    # fehlt" ueber ein Werkzeug, das da war.
    assert "zepos-menu --show all" in rendered, (
        "der Ersatz fuer SUPER+SPACE fehlt")


def test_both_surfaces_are_written_before_every_session():
    """Der Grund, aus dem die beiden Programme keinen Rueckfallstil in
    /etc brauchen - und der einzige, der es rechtfertigt, keinen zu
    haben. Wortgleiche Begruendung wie bei zepos-logout.
    """
    status = _uncommented(
        _read(SRC / "templates" / "hyprland-status-config.template"))
    generator = _read(SRC / "generate_config.sh")

    for target in ("hyprlaunch-config", "hyprlaunch-style",
                   "hyprclipx-config", "hyprclipx-style"):
        assert f"./generate_config.sh -{target}" in status, (
            f"{target} wird beim Sitzungsstart nicht erzeugt")
        assert f"    {target})" in generator, (
            f"src/generate_config.sh kennt das Ziel {target} nicht - der "
            f"Aufruf oben liefe ins Leere")


@pytest.mark.parametrize("name", sorted(ADOPTED))
def test_the_generated_files_land_where_the_programs_look(name):
    """Ein Generator, der in ein anderes Verzeichnis schreibt als das,
    in dem das Programm nachsieht, erzeugt zwei richtige Haelften und
    ein ungestyltes Fenster."""
    generator = _read(SRC / "generate_config.sh")
    assert f'CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/{name}"' in generator, (
        f"der Generator schreibt nicht nach ~/.config/{name}")

    parser = _read(PLUGINS / name / "src" / "ConfigParser.cpp")
    assert f'CONFIG_NAMESPACE = "{name}"' in parser, (
        f"plugins/{name} sucht in einem anderen Namensraum")


# --------------------------------------------------------------------
# Das Toolkit, gemessen am fertigen Objekt - vom Rezept
# --------------------------------------------------------------------

@pytest.mark.parametrize("name, recipe", sorted(ADOPTED.items()))
def test_each_recipe_measures_the_toolkit_after_the_build(name, recipe):
    """Diese Datei misst Text. Ob das gebaute Objekt gegen libgtk-4
    gelinkt ist, kann nur readelf am fertigen Objekt sagen - das tun
    die Rezepte, und hier steht, dass sie es tun. Dieselbe
    Arbeitsteilung wie zwischen tests/src/test_gtk4_only.py und
    packaging/zepos-logout/PKGBUILD.
    """
    code = _pkgbuild_code(recipe)

    assert f'ui="$pkgdir/usr/bin/{name}-ui"' in code, (
        f"packaging/{recipe} prueft die UI-Haelfte gar nicht")
    assert 'needed="$(readelf -d "$ui")"' in code, (
        f"packaging/{recipe} fragt das fertige Objekt nicht")
    assert 'grep -q "libgtk-4" <<<"$needed"' in code, (
        f"packaging/{recipe} prueft nicht auf GTK4")
    assert 'grep -q "gtk4-layer-shell" <<<"$needed"' in code, (
        f"packaging/{recipe} prueft nicht auf die Layer-Shell; ohne sie "
        f"platziert der Compositor das Fenster wie ein gewoehnliches")
    assert 'loaded="$(ldd "$ui")"' in code and \
        'grep -q "libgtk-3" <<<"$loaded"' in code, (
        f"packaging/{recipe} prueft nur, was direkt gelinkt ist. Arch "
        f"setzt -Wl,--as-needed, und die Gefahr ist die Bibliothek, die "
        f"IHRERSEITS GTK3 mitbringt - die sieht nur ldd")

    # Die Gegenprobe zur Teilung: das Objekt, das IN den Compositor
    # geladen wird, darf gar kein GTK anfordern. Genau dafuer hat
    # upstream die zwei Haelften getrennt.
    assert f'readelf -d "$pkgdir/$_plugin_dir/{name}.so" | grep -q "libgtk"' \
        in code, (
        f"packaging/{recipe} prueft nicht, dass die Plugin-Haelfte GTK-frei "
        f"bleibt")


@pytest.mark.parametrize("name", sorted(ADOPTED))
def test_the_plugin_half_stays_free_of_gtk(name):
    """Dieselbe Frage an der Quelle statt am Objekt, und sie ist
    billiger: das CMakeLists darf der Plugin-Haelfte kein GTK
    dazulinken.

    Der Grund ist keine Geschmacksfrage. Die Plugin-Haelfte laeuft IM
    Compositor-Prozess; eine zweite GTK-Hauptschleife darin ist der
    Grund, aus dem upstream ueberhaupt geteilt hat, und die Teilung ist
    das, was die beiden Fenster ueberhaupt zu Layer-Shell-Clients
    macht.
    """
    text = _read(PLUGINS / name / "CMakeLists.txt")
    plugin_block = text.split("add_library", 1)[1].split("add_executable", 1)[0]
    assert "GTK4_LIBRARIES" not in plugin_block, (
        f"plugins/{name}/CMakeLists.txt linkt GTK an die Plugin-Haelfte")
    assert f"target_link_libraries({name}-ui" in text, (
        "die UI-Haelfte linkt gar nichts - dann ist die Teilung eine "
        "andere geworden")


def test_the_two_surfaces_are_not_documented_as_someone_elses_any_more():
    """Die Rezepte tragen jetzt die Versionsnummer dieses Baums, weil
    sie den Code dieses Baums ausliefern. tests/packaging/
    test_recipes.py prueft die Form; hier steht der Grund, damit die
    Aenderung nicht als Formsache durchgeht.
    """
    for recipe in ADOPTED.values():
        code = _pkgbuild_code(recipe)
        assert 'pkgver="$(<"$_zepos_repo/VERSION")"' in code, (
            f"packaging/{recipe} traegt eine fremde Versionsnummer fuer "
            f"eigenen Code")
        assert not re.search(r"^_commit=", code, re.M), (
            f"packaging/{recipe} pinnt weiterhin einen fremden Commit")


# --------------------------------------------------------------------
# Wie weit die Uebernahme geht: was ein MENSCH liest, ist unseres
# --------------------------------------------------------------------
#
# DIE ENTSCHEIDUNG, DIE DIESER ABSCHNITT FESTHAELT (12.08.2026)
#     Der Nutzer: "hyprlaunch eigene version bauen also forken". Die
#     Frage dahinter ist, ob die Programme umbenannt werden.
#
#     GEMESSEN, was an den Namen haengt: 250 Vorkommen von "hyprlaunch"
#     und 181 von "hyprclipx" in 31 Dateien, und darunter sechs
#     Bindungen, die kein Mensch liest und die alle gleichzeitig
#     brechen wuerden - der Name des Objekts, den src/plugins.py prueft
#     und in die erzeugte Datei schreibt; die Dispatcher
#     `hyprlaunch:toggle` und `hyprclipx:toggle`, an denen zwei Tasten
#     haengen; die hyprctl-Befehle; der Namensraum `plugin:<name>:*`,
#     den Hyprland beim Laden anmeldet; das Verzeichnis
#     ~/.config/<name>, in das der Generator schreibt und in dem der
#     Parser nachsieht; und `<name>-ui`, das die Plugin-Haelfte mit
#     execlp in PATH sucht.
#
#     Was ein MENSCH dagegen von diesen Namen zu sehen bekam, war eine
#     kurze Liste, und sie ist abgearbeitet:
#
#       * zwei gruene Kaesten bei JEDER Anmeldung, fuenf Sekunden lang,
#         "[HyprLaunch] Loaded successfully!" - ersatzlos weg, siehe
#         plugins/hyprlaunch/src/main.cpp
#       * der Urheber in `hyprctl plugin list` - jetzt ZepOS
#       * die Beschreibung ebenda - jetzt deutsch
#       * der Fenstertitel - jetzt ZepOS
#       * die Paketnamen - waren schon zepos-*
#
#     Der Fork geht also tief in der Sache (die Fehler, der Sammler,
#     die Bewegung) und flach in den Bezeichnern. Eine Umbenennung der
#     sechs Bindungen braechte keinem Nutzer etwas, das er sehen kann,
#     und riskiert sechs gleichzeitige Brueche.

# Was in keiner Zeile Code mehr stehen darf. Der Produktname des
# fremden Baums, in beiden Schreibweisen, die vorkamen.
FOREIGN_PRODUCT_NAMES = ("HyprLaunch", "HyprClipX")


@pytest.mark.parametrize("name", sorted(ADOPTED))
def test_no_foreign_product_name_is_shown_to_a_human(name):
    """Kein Code dieser beiden Programme zeigt noch den Produktnamen
    des Baums, aus dem sie kommen.

    Ueber _cpp_code() und damit zeilengenau ohne Kommentare - und das
    ist hier nicht Vorsicht, sondern noetig: die Koepfe von main.cpp
    ZITIEREN die geloeschte Meldung, um zu erklaeren, warum sie weg
    ist, und plugins/LICENSE nennt den Ursprung, weil die Lizenz das
    verlangt. Eine Suche ueber den rohen Text faende beides.
    """
    for path in _sources(name):
        for number, line in _cpp_code(path):
            for foreign in FOREIGN_PRODUCT_NAMES:
                assert foreign not in line, (
                    f"{path.name}:{number} zeigt weiterhin {foreign!r}: "
                    f"{line.strip()}")


@pytest.mark.parametrize("name", sorted(ADOPTED))
def test_the_plugin_names_itself_as_ours_in_hyprctl(name):
    """PLUGIN_INIT gibt {Name, Beschreibung, Urheber, Version} zurueck,
    und `hyprctl plugin list` druckt das als "Plugin <n> by <u>".

    Der Urheber stand auf dem fremden Produktnamen. Der NAME bleibt,
    wie er ist - er ist derselbe, den src/plugins.py prueft und den die
    Dispatcher tragen; siehe die Begruendung ueber diesem Abschnitt.
    """
    code = "\n".join(line for _n, line
                     in _cpp_code(PLUGINS / name / "src" / "main.cpp"))
    # Ab PLUGIN_INIT gesucht und nicht ueber die ganze Datei: die
    # Dispatcher darueber enden alle auf `return {.success = true};`,
    # und ein `return\s*\{` ueber der ganzen Datei findet den ersten
    # davon. NACHGEWIESEN - die erste Fassung dieser Pruefung fiel
    # genau darauf herein und meldete "len(fields) == 4" gegen eine
    # leere Liste.
    start = code.find("PLUGIN_INIT")
    assert start != -1, f"plugins/{name}/src/main.cpp hat kein PLUGIN_INIT"
    match = re.search(r"return\s*\{\s*\"(.*?)\};", code[start:], re.DOTALL)
    assert match, f"plugins/{name}/src/main.cpp gibt keine Beschreibung zurueck"
    fields = re.findall(r'"([^"]*)"', match.group(0))
    assert len(fields) == 4, fields
    assert fields[0] == name, (
        f"der Plugin-Name ist {fields[0]!r} und nicht {name!r} - er ist die "
        f"Bindung, die src/plugins.py und die Dispatcher tragen")
    assert fields[2] == "ZepOS", (
        f"der Urheber, den `hyprctl plugin list` zeigt, ist {fields[2]!r}")


@pytest.mark.parametrize("name", sorted(ADOPTED))
def test_no_plugin_greets_the_user_at_every_login(name):
    """addNotification in PLUGIN_INIT laeuft bei jeder Anmeldung.

    Zwei Plugins mal fuenf Sekunden gruener Kasten, in englischer
    Sprache, ueber etwas, das der Nutzer nicht angestossen hat. Was
    wirklich eine Nachricht waere - das Plugin laedt NICHT - kann eine
    Zeile hinter dem Laden ohnehin nicht melden; dafuer gibt es
    src/plugins.py.
    """
    for path in _sources(name):
        for number, line in _cpp_code(path):
            assert "addNotification" not in line, (
                f"{path.name}:{number} meldet sich bei jeder Anmeldung: "
                f"{line.strip()}")


# --------------------------------------------------------------------
# Die drei Fehler, die am 11.08.2026 offen standen
# --------------------------------------------------------------------

def test_the_compositor_half_writes_no_debug_log():
    """/tmp/hyprclipx-debug.log ist weg, und zwar ganz.

    Fuenfzehn Schreibstellen, im COMPOSITOR-Prozess, bei jedem Druck
    auf SUPER+SHIFT+V, unbegrenzt wachsend in ein tmpfs - und mit
    `window class` und `window title` darin, in einer Datei, die jedes
    Konto der Maschine lesen kann. Ein Fenstertitel ist der Name des
    geoeffneten Dokuments.
    """
    for path in _sources("hyprclipx"):
        for number, line in _cpp_code(path):
            assert "hyprclipx-debug" not in line, (
                f"{path.name}:{number} schreibt weiter ins Protokoll")
            assert "/tmp/" not in line or "clipboard-manager" in line \
                or "clipman" in line or "hyprclipx-ui.sock" in line, (
                f"{path.name}:{number} legt eine neue Datei in /tmp: "
                f"{line.strip()}")


def test_the_dead_client_path_is_gone():
    """clipmanClient hatte zwei Zuweisungen und null Leser.

    Es zeigte auf clipman-client.py, ein Python-Programm, das Befehle
    ueber den Socket schickt - was die C++-Haelfte in
    ClipboardManager::sendCommand() seit jeher selbst tut.
    """
    for path in _sources("hyprclipx") + [
            PLUGINS / "hyprclipx" / "include" / "hyprclipx" / "Config.hpp"]:
        for number, line in _cpp_code(path):
            assert "clipmanClient" not in line, (
                f"{path.name}:{number} fuehrt das tote Feld weiter")


def test_no_file_a_package_must_provide_is_looked_for_under_the_home():
    """Der Grund, aus dem der Sammler nie ausgeliefert werden konnte.

    `home + "/.local/bin/get-caret-position.py"` stand im Objekt, und
    ein pacman-Paket darf unterhalb von ~ nichts besitzen (der Kopf von
    src/paths.py fuehrt das Argument). Die Suche traf damit einen Pfad,
    den keine Installation je fuellt.

    DIE GRENZE, DIE DIESE PRUEFUNG ZIEHT, UND WARUM SIE NICHT PAUSCHAL IST
        Nicht jeder Pfad unter ~ ist falsch - im Gegenteil, die meisten
        gehoeren dorthin. `~/.cache/hyprlaunch-recent.json` ist die
        Liste der zuletzt gestarteten Programme, und
        `~/.local/bin/helpers` sind die EIGENEN Skripte des Nutzers,
        die der Helfer-Modus auflistet. Beides sind Nutzerdaten, und
        ein Paket hat dort nichts verloren.

        Falsch ist nur der umgekehrte Fall: eine Datei, die aus einem
        PAKET kommen muss, unter ~ zu suchen. Eine pauschale Pruefung
        auf ".local/bin" faende alle drei und zwaenge dazu, die zwei
        richtigen wegzuerklaeren - eine Pruefung, die man wegerklaeren
        muss, wird abgeschaltet.

        Gesucht wird deshalb nach dem Muster, das den Fehler ausmacht:
        ein aus $HOME zusammengesetzter Pfad auf eine .py-Datei. Die
        beiden Python-Helfer sind das einzige an diesen Programmen, was
        ein Paket ausliefert und was zur Laufzeit gefunden werden muss.
    """
    home_built = re.compile(r"home\s*\+\s*\"[^\"]*\.py\"")
    for name in ADOPTED:
        for path in _sources(name):
            for number, line in _cpp_code(path):
                assert not home_built.search(line), (
                    f"{path.name}:{number} sucht eine Datei, die aus einem "
                    f"Paket kommen muss, unterhalb von ~: {line.strip()}")


def test_the_launcher_takes_its_helper_directory_from_the_generated_file():
    """Der Ort der eigenen Skripte darf unter ~ liegen - aber nicht im
    uebersetzten Objekt.

    Wer seine Skripte woanders hat, konnte es dem Starter bis zum
    12.08.2026 nicht sagen: der Pfad war einkompiliert. Jetzt steht er
    in der erzeugten Datei, und der Parser loest die fuehrende Tilde
    auf - ohne das waere der Wert ein Verzeichnis namens "~" im
    Arbeitsverzeichnis des Compositors.
    """
    parser = _read(PLUGINS / "hyprlaunch" / "src" / "ConfigParser.cpp")
    code = "\n".join(line for _n, line
                     in _cpp_code(PLUGINS / "hyprlaunch" / "src"
                                  / "ConfigParser.cpp"))
    assert 'key == "helpers_dir"' in code, (
        "der Starter liest den Ort seiner Helfer nicht aus der Datei")
    # Die AUFRUFSTELLE, nicht die Definition. NACHGEWIESEN in der
    # Mutationspruefung: `config.helpersDir = parseString(value);` -
    # also der Aufruf entfernt, die Funktion stehen gelassen - kam
    # durch ein blosses `"expandHome" in code` hindurch, und der Wert
    # aus der Datei waere wieder ein Verzeichnis namens "~".
    assert "config.helpersDir = expandHome(" in code, (
        "eine fuehrende Tilde wird nicht aufgeloest - der Wert aus der "
        "Datei waere dann ein Verzeichnis namens ~")
    assert 'path.rfind("~/", 0)' in parser, (
        "expandHome loest etwas anderes auf als ein fuehrendes ~/")

    template = _read(CONFIG_TEMPLATES["hyprlaunch"])
    assert re.search(r"^helpers_dir\s*=", template, re.M), (
        "die Vorlage schreibt den Schluessel nicht, also bleibt es beim "
        "Grundwert und der Regler ist wieder tot")


def test_the_collector_and_the_caret_helper_ship_with_the_package():
    """Beide Python-Haelften liegen im Baum und werden installiert.

    Ohne den Sammler oeffnet SUPER+SHIFT+V ein leeres Fenster; ohne den
    Schreibmarken-Helfer faellt die zweite von drei Strategien lautlos
    aus und der Verlauf geht am Mauszeiger auf statt an der
    Schreibmarke.
    """
    helpers = PLUGINS / "hyprclipx" / "helpers"
    collector = helpers / "collector.py"
    caret = helpers / "caret-position.py"
    assert collector.is_file(), "der Sammler liegt nicht im Baum"
    assert caret.is_file(), "der Schreibmarken-Helfer liegt nicht im Baum"

    cmake = _read(PLUGINS / "hyprclipx" / "CMakeLists.txt")
    for helper in ("helpers/collector.py", "helpers/caret-position.py"):
        assert helper in cmake, f"{helper} wird nicht installiert"
    assert "DESTINATION lib/hyprclipx" in cmake

    # Und der Pfad, an dem die C++-Haelfte den Helfer sucht, ist der,
    # an den CMake ihn legt. Zwei Wege, die auseinanderlaufen, waeren
    # ein Helfer, der da ist und nicht gefunden wird.
    config = _read(PLUGINS / "hyprclipx" / "include" / "hyprclipx"
                   / "Config.hpp")
    assert '"/usr/lib/hyprclipx/caret-position.py"' in config

    # Und die erzeugte Datei nennt ihn ebenfalls. Der Grundwert im
    # Objekt allein reichte technisch - genau deshalb ist diese Zeile
    # noetig: NACHGEWIESEN in der Mutationspruefung ging die Fassung
    # ohne sie durch, als caret_helper aus der Vorlage verschwand.
    #
    # Was dabei verloren geht, ist der Regler. Wer aus dem Arbeitsbaum
    # baut, hat kein /usr/lib/hyprclipx, und ohne den Schluessel in der
    # Datei kann er dem Plugin nicht sagen, wo der Helfer liegt - die
    # zweite Strategie der Schreibmarkensuche faellt dann lautlos aus,
    # also genau der Zustand, gegen den diese Aenderung geschrieben ist.
    template = _read(CONFIG_TEMPLATES["hyprclipx"])
    key = re.search(r'^caret_helper\s*=\s*"([^"]+)"', template, re.M)
    assert key, (
        "die Vorlage schreibt caret_helper nicht - der Pfad laesst sich "
        "dann nur noch durch Neuuebersetzen aendern")
    assert key.group(1) == "/usr/lib/hyprclipx/caret-position.py", (
        f"die Vorlage nennt {key.group(1)!r}, das Paket legt den Helfer "
        f"aber nach /usr/lib/hyprclipx/caret-position.py")


def test_the_collector_reads_the_generated_configuration():
    """Der Sammler holt sich Socket und Obergrenze aus derselben Datei
    wie beide C++-Haelften.

    Vorher stand beides in seinem Kopf ein zweites Mal, und die Zahlen
    stimmten nicht ueberein: max_items = 700 dort gegen 50 in
    src/templates/hyprclipx-config.template. Das Fenster holte fuenfzig
    Eintraege, der Sammler hob siebenhundert auf - der Verlauf war also
    dauerhaft groesser als alles, was man je zu sehen bekam.
    """
    source = _read(PLUGINS / "hyprclipx" / "helpers" / "collector.py")
    code = "\n".join(_uncommented(source))

    # Mit der Klammer, und das ist keine Kosmetik: NACHGEWIESEN in der
    # Mutationspruefung ging `def load_config_abgeschaltet` durch diese
    # Zeile hindurch, weil sie den Namen als Teilwort enthaelt.
    assert "def load_config()" in code, (
        "der Sammler liest die erzeugte Datei nicht")
    assert re.search(r"^\s*load_config\(\)", code, re.M), (
        "load_config() wird nirgends AUFGERUFEN - eine Funktion, die die "
        "Datei liest und die niemand ruft, aendert nichts")
    assert '"hyprclipx"' in code, "er sucht in einem anderen Namensraum"
    for key in ("socket_path", "max_items", "preview_chars"):
        assert key in code, f"{key} wird nicht aus der Datei gelesen"

    # Und die Obergrenze im Kopf ist jetzt dieselbe wie in der Vorlage.
    template = _read(CONFIG_TEMPLATES["hyprclipx"])
    wanted = re.search(r"^max_items\s*=\s*(\d+)", template, re.M)
    assert wanted, "die Vorlage nennt max_items nicht"
    fallback = re.search(r'"max_items":\s*(\d+)', code)
    assert fallback, "der Sammler hat keinen Grundwert fuer max_items"
    assert fallback.group(1) == wanted.group(1), (
        f"der Grundwert des Sammlers ({fallback.group(1)}) ist nicht der "
        f"der Vorlage ({wanted.group(1)}) - genau die Abweichung, wegen "
        f"der diese Zeile hierher gezogen ist")


def test_the_session_starts_the_collector():
    """Eine Konfiguration, die den Sammler nicht startet, ist ein
    Verlauf, der leer bleibt - egal wie richtig alles andere ist.

    Und `wl-paste --watch cliphist store` bleibt daneben stehen: es
    fuellt den ANDEREN Verlauf, den auf SUPER+ALT+V, der Favoriten
    kann und den das Plugin nicht ersetzt.
    """
    universal = _read(SRC / "templates"
                      / "hyprland-universal-config.template")
    lines = _uncommented(universal)

    started = [line for line in lines if "collector.py" in line]
    assert started, "die Sitzung startet den Sammler nicht"
    assert any(line.startswith("exec-once") for line in started), (
        f"der Sammler steht nicht in einem exec-once: {started}")
    assert any("/usr/lib/hyprclipx/collector.py" in line
               for line in started), (
        "der Startbefehl nennt einen anderen Pfad als den, an den das "
        "Paket den Sammler legt")

    assert any("cliphist store" in line for line in lines), (
        "der Sammler fuer SUPER+ALT+V ist mit weggefallen - jene Taste "
        "liest cliphists eigene Datenbank und braucht ihn")


# --------------------------------------------------------------------
# Die Bewegung, die die beiden Fenster bis zum 12.08.2026 nicht hatten
# --------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(ADOPTED))
def test_every_state_change_is_carried_by_the_motion_ladder(name):
    """Was seinen Zustand wechselt, tut es ueber die eine Kurve und
    eine Dauer der Leiter - nicht sprunghaft und nicht mit einer
    eigenen Zahl.

    GEMESSEN am 12.08.2026: diese beiden Stylesheets hatten NULL
    transition-Zeilen, waehrend zepos-menu, lock, logout und ags ihre
    Zustandswechsel schon auf der Leiter hatten. Kein Verzicht, sondern
    eine Luecke - die Uebernahme holte Farbe und Groesse aus dem
    Objekt, und Bewegung stand dort nirgends.
    """
    text = _read(STYLE_TEMPLATES[name])
    body = _BLOCK_COMMENT.sub("", text)

    # (?<![-\w]) davor, und auch das ist nachgewiesen noetig: die
    # Mutation, die jedes `transition:` in `no-transition:` umbenannte -
    # also die Bewegung vollstaendig abschaltete, weil GTK die
    # Eigenschaft dann nicht kennt -, kam durch ein blosses
    # `transition:` glatt hindurch.
    transitions = re.findall(r"(?<![-\w])transition:\s*([^;]+);", body,
                             re.DOTALL)
    assert transitions, (
        f"{STYLE_TEMPLATES[name].name} bewegt nichts. Jede andere "
        f"Oberflaeche dieses Baums tut es.")

    for rule in transitions:
        assert "{{STYLE_MOTION_CURVE}}" in rule, (
            f"eine Bewegung ohne die Kurve der Marke: {rule.strip()!r}")
        assert "{{STYLE_MOTION_INSTANT}}" in rule, (
            f"eine Bewegung, deren Dauer nicht auf der Leiter steht: "
            f"{rule.strip()!r}")
        # Keine ausgeschriebene Dauer daneben. `0.3s` oder `200ms` waere
        # genau der tote Regler, gegen den die Leiter geschrieben ist.
        assert not re.search(r"\b\d+(\.\d+)?m?s\b", rule), (
            f"eine ausgeschriebene Dauer neben der Leiter: {rule.strip()!r}")


@pytest.mark.parametrize("name", sorted(ADOPTED))
def test_the_window_itself_does_not_animate(name):
    """Das Fenster ist eine Layer-Shell-Flaeche, die der Compositor
    auf- und zumacht. Eine zweite Animation im Stylesheet liefe gegen
    seine."""
    body = _BLOCK_COMMENT.sub("", _read(STYLE_TEMPLATES[name]))
    assert "animation:" not in body, (
        f"{STYLE_TEMPLATES[name].name} animiert selbst")
    assert "@keyframes" not in body


# --------------------------------------------------------------------
# Und ob GTK die erzeugten Stylesheets ueberhaupt versteht
# --------------------------------------------------------------------

_CSS_CHILD = r"""
import sys
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

errors = []
provider = Gtk.CssProvider()
provider.connect(
    "parsing-error",
    lambda prov, section, error: errors.append(
        "%s: %s" % (section.to_string(), error.message)))
provider.load_from_path(sys.argv[1])
for line in errors:
    print(line)
print("errors=%d" % len(errors))
"""


@pytest.mark.allow_subprocess
@pytest.mark.parametrize("name", sorted(ADOPTED))
def test_gtk_parses_the_generated_stylesheet_without_a_single_complaint(
        name, tmp_path, monkeypatch):
    """Die Pruefung, an der wofi jahrelang vorbeigekommen ist.

    GTK4 verwirft eine Regel, die es nicht versteht, und behaelt den
    Rest - ohne ein Wort irgendwohin. wofis erzeugtes Stylesheet
    erzeugte so 39 Parserfehler und rendere in GTKs eigenem Grau, und
    gemerkt hat es jahrelang niemand. Ein neu geschriebenes Stylesheet
    ist genau der Zeitpunkt, an dem derselbe Fehler wieder entsteht.

    Kein Anzeigeserver noetig - GEMESSEN mit `env -u WAYLAND_DISPLAY -u
    DISPLAY`: das Zerlegen eines Stylesheets braucht keinen. Deshalb
    auch kein broadwayd wie in tests/menu/test_menu_headless.py,
    sondern nur ein Kind, das `gi` laden kann; .venv sieht das
    systemweite PyGObject nicht.
    """
    interpreter = gi_interpreter({"Gtk": "4.0"})
    if interpreter is None:
        pytest.skip("kein Interpreter hier kann gi/Gtk4 laden")
    executable, extra_path = interpreter

    real_run = subprocess.run
    rendered = _render(tmp_path / "render", monkeypatch,
                       STYLE_TEMPLATES[name], 1.85)
    sheet = tmp_path / f"{name}.css"
    sheet.write_text(rendered, encoding="utf-8")

    child = tmp_path / "parse.py"
    child.write_text(_CSS_CHILD, encoding="utf-8")

    environment = dict(os.environ)
    environment.pop("WAYLAND_DISPLAY", None)
    environment.pop("DISPLAY", None)
    if extra_path:
        environment["PYTHONPATH"] = os.pathsep.join(
            extra_path + [environment.get("PYTHONPATH", "")]).rstrip(os.pathsep)

    result = real_run([executable, str(child), str(sheet)],
                      capture_output=True, text=True, env=environment,
                      timeout=120)
    assert result.returncode == 0, result.stderr
    assert "errors=0" in result.stdout, (
        f"GTK versteht {STYLE_TEMPLATES[name].name} nicht vollstaendig. "
        f"Jede gemeldete Zeile ist eine Regel, die verworfen wird - "
        f"ohne dass irgendwo etwas anderes davon steht:\n{result.stdout}")


# --------------------------------------------------------------------
# Der Sammler, ausgefuehrt
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_the_collector_speaks_the_protocol_the_window_speaks(tmp_path,
                                                             monkeypatch):
    """Die Stelle, an der dieser Abschnitt nicht Text misst.

    Alles darueber prueft Zeichenketten. Hier laeuft der ECHTE Sammler
    gegen eine ECHTE erzeugte Konfiguration, und gefragt wird ihn mit
    genau dem Byte-Format, das plugins/hyprclipx/src/
    ClipboardManager.cpp::sendCommand() ueber den Draht schickt:

        {"cmd":"ping","args":{}}

    Ohne diesen Schritt waere die ganze Kette eine Vermutung. Ein
    Sammler, der laeuft und ein anderes JSON spricht, sieht in jeder
    Textpruefung richtig aus - und liefert ein leeres Fenster, also
    genau den Zustand, gegen den die Aenderung geschrieben ist.

    DER SOCKET LIEGT UNTER tmp_path UND NICHT AUF /tmp/clipman.sock
        Sonst traefe dieser Test den Sammler, der auf der Maschine des
        Entwicklers laeuft, oder er nimmt ihm den Pfad weg. Der
        Socketpfad ist einstellbar (socket_path in der erzeugten
        Datei), also kostet das nichts - und es prueft die
        Einstellbarkeit gleich mit.
    """
    # Kein `real_run = subprocess.run` wie in den Nachbarn darunter:
    # _render() tauscht nur subprocess.RUN gegen ein FileNotFoundError,
    # und dieser Test startet den Sammler mit subprocess.POPEN. Eine
    # Zeile, die einen Namen festhaelt, den niemand benutzt, sieht aus
    # wie eine Vorsichtsmassnahme und ist keine.
    collector = PLUGINS / "hyprclipx" / "helpers" / "collector.py"
    assert collector.is_file()

    # Die ECHTE erzeugte Datei, mit einem Faktor ungleich 1.0, damit
    # ein Wert darin nicht zufaellig sein eigener Grundwert ist.
    generated = _render(tmp_path / "render", monkeypatch,
                        CONFIG_TEMPLATES["hyprclipx"], 2.0)

    room = tmp_path / "room"
    (room / "config" / "hyprclipx").mkdir(parents=True)
    (room / "data").mkdir(parents=True)
    socket_path = tmp_path / "clipman.sock"

    # socket_path umbiegen - dieselbe Datei, ein anderer Wert. Das ist
    # zugleich die Probe, dass der Sammler die Datei wirklich liest:
    # nimmt er sie nicht, macht er /tmp/clipman.sock auf und dieser
    # Test findet unter tmp_path nichts.
    generated = re.sub(r'(?m)^socket_path\s*=.*$',
                       f'socket_path = "{socket_path}"', generated)
    assert str(socket_path) in generated
    (room / "config" / "hyprclipx" / "config").write_text(
        generated, encoding="utf-8")

    environment = dict(os.environ)
    environment["XDG_CONFIG_HOME"] = str(room / "config")
    environment["XDG_DATA_HOME"] = str(room / "data")
    # wl-paste unerreichbar machen: der Sammler soll in diesem Test die
    # Zwischenablage des Entwicklers weder lesen noch in eine Datenbank
    # unter tmp_path schreiben. Sein Beobachter faengt das Scheitern ab
    # (er schreibt eine Zeile auf stderr und macht weiter), der
    # Socket-Teil laeuft unberuehrt - und genau der wird hier gefragt.
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "wl-paste").write_text("#!/bin/bash\nexit 1\n")
    (stubs / "wl-paste").chmod(0o755)
    environment["PATH"] = os.pathsep.join([str(stubs), os.environ["PATH"]])

    process = subprocess.Popen(
        ["/usr/bin/python3", str(collector)], env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not socket_path.exists():
            if process.poll() is not None:
                raise AssertionError(
                    "der Sammler ist gestorben, bevor er seinen Socket "
                    "aufgemacht hat:\n" + (process.stdout.read()
                                           if process.stdout else ""))
            time.sleep(0.05)
        assert socket_path.exists(), (
            f"der Sammler hat {socket_path} nicht aufgemacht - er liest "
            f"socket_path nicht aus der erzeugten Datei")

        def ask(payload: bytes) -> str:
            client = socketlib.socket(socketlib.AF_UNIX,
                                      socketlib.SOCK_STREAM)
            client.settimeout(10)
            client.connect(str(socket_path))
            client.send(payload)
            answer = client.recv(65536).decode("utf-8")
            client.close()
            return answer

        # Wortgleich zu ClipboardManager::sendCommand("ping", "{}").
        pong = ask(b'{"cmd":"ping","args":{}}')
        assert '"ok"' in pong, (
            f"der Sammler antwortet nicht, wie ClipboardManager es liest "
            f"(es sucht die Zeichenkette \"ok\"): {pong!r}")

        # Und die Antwort, aus der das Fenster seine Liste baut. Leer
        # ist in Ordnung - geprueft wird die FORM, die
        # parseListResponse() zerlegt: Status "ok" und ein "data"-Feld
        # mit einer Reihung darin.
        listing = ask(b'{"cmd":"list","args":{"filter":"all","limit":50}}')
        assert '"ok"' in listing and '"data"' in listing, (
            f"parseListResponse() faende in dieser Antwort nichts: "
            f"{listing!r}")
        assert re.search(r'"data"\s*:\s*\[', listing), listing
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()

    # Und die Daten liegen unter XDG_DATA_HOME, nicht in ~.
    assert (room / "data" / "hyprclipx" / "clipman.db").is_file(), (
        "der Sammler legt seine Datenbank nicht unter $XDG_DATA_HOME ab")


# ---------------------------------------------------------------------
# Die Ecken der beiden Plugin-Oberflaechen
# ---------------------------------------------------------------------
# GEMELDET am 18.08.2026: "die externen plugins die wir zepos genannt
# haben wie hyprlauncher unsw sind nicht wirklich abgerundet das fenster
# ist nicht rund".
#
# ZWEI VERSCHIEDENE URSACHEN, beide dieselbe Eigenschaft von GTK4: ein
# Kasten mit border-radius beschneidet seine Kinder NICHT, und `overflow:
# hidden` gibt es in GTKs CSS-Teilmenge nicht. Ein Kind mit deckendem
# Grund und ohne eigenen Radius malt also ein Rechteck in die runde Ecke.
#
#   hyprlaunch  .launcher-container war rund, .launcher-search - sein
#               erstes Kind - nicht. Oben eckig, unten rund.
#   hyprclipx   .cm-root hatte ueberhaupt keinen Radius. Grund und
#               Rahmen ja, Rundung nie.
#
# Dieselbe Ursache war am 17.08.2026 in den AGS-Fenstern gefunden und
# behoben worden (.overlay-header in ags-style.template). Die
# Plugin-Stylesheets hat dabei niemand mitgeprueft - deshalb steht die
# Regel jetzt als Test und nicht als Erinnerung.
#
# WAS DIESER TEST NICHT KANN: ein Bild machen. Ob eine Ecke rund
# AUSSIEHT, entscheidet ein Lauf mit den gebauten Plugins. Er haelt die
# Zusage ab, die man ohne Compositor abhalten kann - dass jedes Kind, das
# eine Ecke besetzt, dort auch einen Radius traegt.

_ECKEN = {
    "hyprlaunch-style.template": {
        # container -> search (erstes Kind, oben). Unten traegt
        # .launcher-list keinen Grund und `scrollbar` ist ausdruecklich
        # durchsichtig, dort scheint die Rundung durch.
        ".launcher-container": "voll",
        ".launcher-search": "oben",
    },
    "hyprclipx-style.template": {
        # Aus ClipboardRenderer::buildUI() abgelesen: cm-root ist eine
        # senkrechte Kiste aus Kopfzeile, Rumpf und Hinweiszeile.
        ".cm-root": "voll",
        ".cm-sidebar-header": "eine",   # oben links
        ".cm-search": "eine",           # oben rechts
        ".cm-hints": "unten",           # volle Breite, beide unteren
    },
}


def _radius_von(text: str, klasse: str) -> str | None:
    """Der border-radius-Wert einer Regel, oder None."""
    block = re.search(rf"^{re.escape(klasse)}\s*\{{(.*?)^\}}",
                      text, re.M | re.S)
    if not block:
        return None
    treffer = re.search(r"^\s*border-radius\s*:\s*([^;]+);",
                        block.group(1), re.M)
    return treffer.group(1).strip() if treffer else None


@pytest.mark.parametrize("datei", sorted(_ECKEN))
def test_every_child_that_owns_a_corner_rounds_it(datei):
    """Wer eine Ecke besetzt, rundet sie - sonst ist das Fenster dort
    eckig, egal was der Kasten darunter sagt."""
    pfad = ROOT / "src" / "styles" / datei
    text = pfad.read_text(encoding="utf-8")

    ohne = []
    for klasse in _ECKEN[datei]:
        wert = _radius_von(text, klasse)
        if wert is None:
            ohne.append(klasse)
    assert ohne == [], (
        f"{datei}: {ohne} besetzen eine Ecke des Fensters und tragen "
        "keinen border-radius. GTK4 beschneidet Kinder nicht - dort wird "
        "ein Rechteck in die runde Ecke gemalt.")


@pytest.mark.parametrize("datei", sorted(_ECKEN))
def test_those_corners_use_the_shared_radius(datei):
    """Und zwar mit der Sprosse der Marke, nicht mit einer eigenen Zahl.

    Ein Fenster, das seinen Radius selbst waehlt, ist genau das, was der
    Nutzer am 17.08.2026 beanstandet hat - "alle styles von ZEPOS muessen
    einheitlich aussehen".
    """
    pfad = ROOT / "src" / "styles" / datei
    text = pfad.read_text(encoding="utf-8")

    fremd = {}
    for klasse in _ECKEN[datei]:
        wert = _radius_von(text, klasse)
        if wert and "{{STYLE_RADIUS_PANEL}}" not in wert:
            fremd[klasse] = wert
    assert fremd == {}, (
        f"{datei}: diese Ecken tragen einen eigenen Radius statt "
        f"STYLE_RADIUS_PANEL: {fremd}")


def test_that_rule_would_notice_a_missing_radius():
    """Der Selbsttest: die Ablesefunktion muss ein Fehlen auch merken.

    Eine Regel, die es nicht gibt, und eine Regel ohne border-radius
    muessen beide None ergeben - sonst waere der Test darueber gruen,
    weil er nichts findet.
    """
    beispiel = ".a {\n    background: red;\n}\n.b {\n    border-radius: 4px;\n}\n"
    assert _radius_von(beispiel, ".a") is None
    assert _radius_von(beispiel, ".gibtsnicht") is None
    assert _radius_von(beispiel, ".b") == "4px"
