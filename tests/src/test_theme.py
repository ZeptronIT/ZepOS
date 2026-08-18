# SPDX-License-Identifier: GPL-3.0-or-later
"""Das Thema ist ein Ding, es laesst sich wechseln, und der Wechsel WIRKT.

WAS HIER DIE EIGENTLICHE MESSUNG IST
    Nicht "es gibt zwei Eintraege in einem Woerterbuch". Sondern: jedes
    einzelne Feld, das src/theme.py ein Themenfeld nennt, bewegt ein Byte
    in einer erzeugten Datei, wenn man es aendert. Das ist dieselbe
    Regel, mit der dieser Baum am 12.08.2026 neunundzwanzig Farben und
    hundertsechs Platzhalter geloescht hat, nur in die andere Richtung -
    und sie wird hier nicht behauptet, sondern gefahren:

        fuer jedes Feld: Palette mit einem Sentinel darin bauen,
        style_definition damit neu einlesen, nachsehen, welche
        {{STYLE_*}} den Sentinel tragen, und verlangen, dass mindestens
        eine Vorlage einen davon nennt - oder dass er in der
        Anmeldemaske ankommt.

    Ein Themenfeld ohne Leser waere die Reglertabelle, die kein Byte
    bewegt, nur mit einem Themenwaehler davor. Genau die gab es in
    diesem Baum schon dreimal: MONITOR_HEIGHT_SCALES, die
    neunundzwanzig Farben des Stil-Editors und die "fonts"/"spacing"-
    Abschnitte in user_settings.

WAS HIER NICHT GEPRUEFT WIRD, WEIL ES WOANDERS STEHT
    Ob die Farben des zweiten Themas lesbar sind. Das rechnet
    tests/src/test_brand.py, ueber JEDES Thema, mit derselben
    WCAG-Formel - und tests/src/test_glass.py und tests/lock/test_style.py
    tun dasselbe fuer das Glas und den Schleier. Sie sind die
    eigentliche Zusicherung; hier steht nur, dass es zwei Themen gibt
    und dass beide ankommen.
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

# Jede Vorlage, die der Generator ueberhaupt schreibt. Beide
# Verzeichnisse, weil die Stylesheets in src/styles/ liegen und alles
# andere in src/templates/ - und die Farben eines Themas landen
# ueberwiegend in den ersten.
TEMPLATE_DIRS = (SRC / "templates", SRC / "styles")


def _flat(name: str):
    """Ein Modul aus src/, das selbst flach importiert.

    Dieselbe Vorrichtung und dieselbe Begruendung wie in
    tests/src/test_greeter.py: src/ ist kein Paket, und src/theme.py
    sagt `import brand`.
    """
    sys.path.insert(0, str(SRC))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(SRC))


theme = _flat("theme")
brand = _flat("brand")
greeter = _flat("greeter")

THEMES = sorted(theme.THEMES)


# --------------------------------------------------------------------
# 1. Ein Thema ist vollstaendig, oder es ist keins
# --------------------------------------------------------------------

@pytest.mark.parametrize("name", THEMES)
def test_every_theme_names_every_field_and_nothing_else(name):
    """In beide Richtungen, wie bei brand.COLOR_GROUPS.

    EIN FEHLENDES FELD ist der schlimmere der beiden Faelle und der
    Grund, aus dem hier ueberhaupt gemessen wird: eine halbe Palette
    sieht aus wie eine ganze. Jede Zahl im Kopf von src/brand.py ist
    gegen eine ANDERE Zahl derselben Palette gerechnet - TEXT ist
    #DCEEF4, WEIL der Grund #0D3D47 ist -, also ist ein Thema, das
    PETROL austauscht und TEXT stehenlaesst, kein halbes Thema, sondern
    ein Kontrastfehler mit einem Namen.

    EIN ZUVIEL ist der leisere: ein Feld, das nur ein Thema kennt, wird
    von keinem anderen ersetzt, und die Palette gibt dann stumm den Wert
    des ausgelieferten Themas zurueck.
    """
    fields = set(theme.FIELDS)
    named = set(theme.THEMES[name])
    assert named - fields == set(), (
        f"das Thema {name} nennt Felder, die es nicht gibt: "
        f"{sorted(named - fields)}")
    assert fields - named == set(), (
        f"dem Thema {name} fehlen Felder: {sorted(fields - named)}. Eine "
        f"Teilpalette rechnet ihre Kontraste gegen die Farben eines "
        f"anderen Themas.")


def test_the_shipped_theme_is_exactly_what_brand_carries():
    """Das ausgelieferte Thema ist keine Abschrift, sondern brand.py.

    Steht hier eine Abweichung, gibt es zwei Meinungen darueber, was
    ZepOS aussieht - eine in src/brand.py, an der jede Kontrastrechnung
    haengt, und eine in src/theme.py, die wirklich erzeugt wird.
    """
    for field in theme.FIELDS:
        assert theme.THEMES[theme.DEFAULT][field] == getattr(brand, field), (
            f"{field} ist im ausgelieferten Thema nicht das, was "
            f"src/brand.py sagt")


def test_every_theme_has_a_label_and_a_description():
    """Ein Thema ohne Beschriftung ist eins, das niemand auswaehlt.

    Die Einstellungs-Anwendung zeigt LABELS und DESCRIPTIONS; fehlt ein
    Eintrag, stuende dort ein Schluessel wie "tageslicht" oder gar
    nichts.
    """
    assert set(theme.LABELS) == set(theme.THEMES)
    assert set(theme.DESCRIPTIONS) == set(theme.THEMES)
    assert all(theme.LABELS.values()) and all(theme.DESCRIPTIONS.values())


def test_there_is_more_than_one_theme():
    """Ein Thema, das es nur einmal gibt, ist keine Umschaltung.

    Ohne diese Zeile bestuenden alle Pruefungen unten auch dann, wenn es
    nichts gaebe, wohin gewechselt werden koennte - sie liefen einmal,
    ueber das ausgelieferte Thema, und verglichen es mit sich selbst.
    """
    assert len(theme.THEMES) >= 2


def test_the_two_themes_really_differ():
    """Und zwar an mehr als einer Farbe.

    "Anders" heisst nicht "ein Gruen verschoben": ein zweites Thema, das
    sich in drei Werten unterscheidet, beweist nichts ueber die
    neunundzwanzig, die es nicht anfasst.
    """
    shipped = theme.THEMES[theme.DEFAULT]
    for name in THEMES:
        if name == theme.DEFAULT:
            continue
        differing = [field for field in theme.FIELDS
                     if theme.THEMES[name][field] != shipped[field]]
        assert len(differing) >= len(theme.FIELDS) * 0.7, (
            f"{name} unterscheidet sich nur in {len(differing)} von "
            f"{len(theme.FIELDS)} Feldern vom ausgelieferten Thema")


# --------------------------------------------------------------------
# 2. Die Rollen und die Felder passen zusammen
# --------------------------------------------------------------------

def test_every_role_names_a_field_a_theme_replaces():
    """Sonst haetten siebzig Rollen und ein Themenwechsel nichts
    miteinander zu tun.

    brand.COLOR_FIELDS bildet Rolle auf FELDNAME ab. Nennt eine Rolle
    einen Namen, den src/theme.py nicht als Feld fuehrt, dann bleibt
    diese eine Farbe beim Wechsel stehen - und zwar lautlos, weil
    Palette.__getattr__ auf brand.py zurueckfaellt.
    """
    fields = set(theme.FIELDS)
    strays = {role: field for role, field in brand.COLOR_FIELDS.items()
              if field not in fields}
    assert strays == {}, (
        f"diese Rollen zeigen auf Werte, die kein Thema ersetzt: {strays}")


def test_the_resolved_table_is_the_one_the_defaults_use():
    """brand.COLORS ist die aufgeloeste Tabelle und nichts anderes.

    Sie ist das, was user_settings.DEFAULT_SETTINGS ausliefert und was
    die Einstellungs-Anwendung "zuruecksetzen" nennt. Waere sie eine
    zweite Liste, waere sie die, die veraltet.
    """
    assert brand.COLORS == {
        role: getattr(brand, field)
        for role, field in brand.COLOR_FIELDS.items()}
    assert theme.palette(theme.DEFAULT).COLORS == brand.COLORS


# --------------------------------------------------------------------
# 3. Der Kern: jedes Feld bewegt ein erzeugtes Byte
# --------------------------------------------------------------------

SENTINEL_COLOUR = "#BADA55"
SENTINEL_TEXT = "Sentinelschrift"
SENTINEL_ALPHA = 0.4242


def _sentinel_for(field: str, current):
    """Ein Wert, der sich vom jetzigen unterscheidet und auffindbar ist."""
    if isinstance(current, float):
        return SENTINEL_ALPHA
    if current.startswith("#"):
        return SENTINEL_COLOUR
    return SENTINEL_TEXT


def _variables_with(monkeypatch, tmp_path, values):
    """STYLE_VARIABLES, erzeugt mit dieser Palette.

    Ueber die MASCHINENDATEI und nicht durch Hineinschreiben in das
    Modul: genau dieser Weg - Name in /etc/zepos/theme, style_definition
    liest ihn beim Import - ist die Umschaltung, die gemessen werden
    soll. Wuerde der Test THEME von aussen setzen, pruefte er seine
    eigene Zuweisung.
    """
    monkeypatch.setitem(theme.THEMES, "probe", values)
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "theme").write_text("probe\n", encoding="utf-8")
    monkeypatch.setenv("ZEPOS_MACHINE_ROOT", str(tmp_path))
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path / "nutzer"))
    monkeypatch.syspath_prepend(str(SRC))
    for name in ("style_definition", "theme", "brand", "paths", "sizes",
                 "audio", "clocks", "monitors", "vpn", "settings"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    import theme as fresh_theme

    fresh_theme.THEMES["probe"] = values
    import style_definition

    return dict(style_definition.STYLE_VARIABLES)


def _template_text() -> str:
    """Jede Vorlage, aneinandergehaengt - einmal gelesen und dann
    wiederverwendet, weil sonst 29 Felder je 90 Dateien lesen."""
    if not _TEMPLATES:
        _TEMPLATES.append("\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for directory in TEMPLATE_DIRS
            for path in sorted(directory.glob("*.template"))))
    return _TEMPLATES[0]


_TEMPLATES: list[str] = []


@pytest.mark.parametrize("field", theme.FIELDS)
def test_changing_this_field_moves_a_generated_byte(field, monkeypatch,
                                                    tmp_path):
    """Die Messung, um die es in dieser Datei geht.

    DREI WEGE ZAEHLEN, und alle drei enden in erzeugten Dateien:

      * der Schreibtisch, WOERTLICH. Das Feld muss in einen {{STYLE_*}}
        fliessen, UND eine Vorlage muss diesen Platzhalter nennen. Nur
        das erste zu pruefen waere die Falle, in die dieser Baum schon
        getappt ist: es gab 106 Platzhalter, die niemand las.
      * der Schreibtisch, ABGELEITET. Ein Feld muss nicht selbst auf dem
        Schirm landen, um etwas zu bewegen. GLASS_PANEL_ALPHA und
        GLASS_CHIP_ALPHA werden seit dem 12.08.2026 nirgends mehr
        gemalt - die Leiste ist einschichtig geworden, weil der Nutzer
        die Kachel unter jedem Modul abgelehnt hat -, und sie sind
        seither die zwei Zahlen, aus denen brand.py die EINE
        Plattendeckkraft und die Unschaerfeschwelle ausrechnet
        (glass_solo_alpha(), glass_ignore_alpha()).

        Der woertliche Weg allein hat bei genau diesen beiden Feldern
        angeschlagen, obwohl ein Verstellen sehr wohl Bytes bewegt:
        GEMESSEN am 12.08.2026, GLASS_PANEL_ALPHA von 0.55 auf 0.4242,
        wird aus STYLE_GLASS_SOLO `rgba(8, 38, 44, 0.86)` ein
        `rgba(8, 38, 44, 0.83)` und aus STYLE_GLASS_IGNORE_ALPHA 0.28
        eine 0.21. Der Waechter hatte recht mit seiner Frage und
        unrecht mit seiner Antwort.

        Deshalb wird zusaetzlich VERGLICHEN: dieselben Vorlagen einmal
        mit und einmal ohne Mutation, und es zaehlt nur, was auch eine
        Vorlage liest. Das ist strenger als die woertliche Suche und
        nicht schwaecher - ein Feld, das gar nichts bewegt, faellt
        weiter durch, und eines, dessen Wert zwar irgendwo landet, aber
        in keiner Vorlage, ebenfalls.
      * die Anmeldemaske. src/greeter.py baut sein Blatt unmittelbar
        aus der Palette, ohne Platzhalter dazwischen.
    """
    values = dict(theme.THEMES[theme.DEFAULT])
    values[field] = _sentinel_for(field, values[field])

    marker = str(values[field])
    mutated = _variables_with(monkeypatch, tmp_path, values)
    baseline = _variables_with(monkeypatch, tmp_path / "ohne",
                               dict(theme.THEMES[theme.DEFAULT]))

    templates = _template_text()

    def read_by_a_template(name: str) -> bool:
        return f"{{{{{name}}}}}" in templates

    literal = [name for name, value in mutated.items()
               if marker in str(value) and read_by_a_template(name)]
    derived = [name for name, value in mutated.items()
               if str(value) != str(baseline.get(name))
               and read_by_a_template(name)]

    in_the_greeter = marker in greeter.stylesheet(
        theme.Palette("probe", values))

    assert literal or derived or in_the_greeter, (
        f"{field} bewegt kein erzeugtes Byte. Kein Platzhalter, den eine "
        f"Vorlage liest, traegt diesen Wert, und keiner aendert sich, "
        f"wenn das Feld sich aendert; die Anmeldemaske auch nicht. Ein "
        f"Themenfeld ohne Leser ist ein Regler, der nichts tut - "
        f"entweder eine Vorlage lesen lassen oder aus theme.FIELDS "
        f"streichen.")


@pytest.mark.parametrize("field", ("SHADE_2", "TRACK_EDGE"))
def test_the_two_colours_left_out_really_have_no_reader(field):
    """Die Gegenprobe zur Ausschlussentscheidung in src/theme.py.

    Beide sind Farben, beide stehen in src/brand.py, und beide sind
    absichtlich KEIN Themenfeld - weil sie keinen erzeugten Platzhalter
    erreichen. Ohne diese Zeile waere das eine Behauptung im Kommentar,
    und wer die zwei spaeter in einen {{STYLE_*}} schreibt, faende
    nichts, was ihn auf theme.FIELDS hinwiese.
    """
    assert field not in theme.FIELDS
    code = "\n".join(
        line for line in (SRC / "style_definition.py")
        .read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#"))
    assert f"THEME.{field}" not in code, (
        f"{field} erreicht jetzt einen Platzhalter und gehoert damit in "
        f"theme.FIELDS - siehe die Ausschlussliste im Kopf von "
        f"src/theme.py")


# --------------------------------------------------------------------
# 4. Der Wechsel als Ganzes: vorher/nachher, in Zahlen
# --------------------------------------------------------------------

def _render_all(monkeypatch, tmp_path, name):
    """Jede Vorlage, erzeugt im Thema `name`, als {Dateiname: Text}.

    Mit dem ECHTEN Prozessor - sonst misst der Test seine eigene
    Ersetzung. Dieselbe Begruendung wie bei
    tests/lock/test_style.py._render().
    """
    variables = _variables_with(monkeypatch, tmp_path,
                                theme.THEMES[name])
    import template_processor

    monkeypatch.setenv("ZEPOS_SYSTEM_ROOT", str(SRC))
    processor = template_processor.ConfigProcessor(styles=variables)
    out = {}
    for directory in TEMPLATE_DIRS:
        for path in sorted(directory.glob("*.template")):
            target = tmp_path / "aus" / f"{directory.name}-{path.stem}"
            target.parent.mkdir(parents=True, exist_ok=True)
            processor.apply_template(path, target)
            out[target.name] = target.read_text(encoding="utf-8",
                                                errors="replace")
    return out


# Was sich beim Wechsel von "zeptronit" auf "tageslicht" bewegt.
#
# GEMESSEN am 12.08.2026, ueber alle 85 Vorlagen aus src/templates/ und
# src/styles/: SECHZEHN erzeugte Dateien unterscheiden sich. Die
# uebrigen 69 sind Shell-Skripte, Dienstdateien und Konfigurationen ohne
# eine einzige Farbe darin - sie SOLLEN sich nicht aendern, und dass sie
# es nicht tun, ist der Gegenbeweis dazu, dass hier nicht einfach alles
# neu geschrieben wird.
#
# Die Namen stehen ausgeschrieben, weil "sechzehn" allein nicht sagt,
# WELCHE - und weil genau eine Datei mit Farben darin absichtlich NICHT
# dabei ist (siehe die zweite Zusicherung unten).
CHANGES_WITH_THE_THEME = {
    "styles-bar-style",
    "styles-grid-wallpaper-toggle-style",
    "styles-hyprclipx-style",
    "styles-hyprlaunch-style",
    "styles-lock-style",
    "styles-logout-style",
    "styles-zepos-menu-style",
    "templates-ags-style",
    "templates-ags-style-editor",
    # Der Kalender, seit dem 12.08.2026. Er baut sein Monatsgitter selbst
    # und bringt die drei Regeln seiner Tagesfelder mit: der markierte
    # Tag traegt {{STYLE_COLOR_CALENDAR_ACCENT}}, die Tage der
    # Nachbarmonate {{STYLE_COLOR_OVERLAY_SUBTEXT}}. Vorher stand dort
    # ein Gtk.Calendar, dessen gewaehlter Tag auf GTKs eigenem Blau sass -
    # eine Flaeche, die KEIN Thema je erreicht hat. Dass diese Datei
    # jetzt in dieser Liste steht, ist genau die Behebung.
    "templates-ags-calendar",
    "templates-grid-wallpaper-toggle-config",
    "templates-gtk4-colors-config",
    "templates-gtk4-settings-config",
    "templates-hyprland-plugins-config",
    "templates-hyprland-universal-config",
    "templates-kitty-config",
    "templates-mako-config",
    # Die Eingabezeile, seit dem 12.08.2026. Sie ist der Grund, aus dem
    # der Nutzer "und andere themes auch" gesagt hat, und sie war bis
    # dahin die einzige Oberflaeche, die gar keine Farbe aus dieser Mitte
    # bezog: es gab keine ~/.p10k.zsh, und daneben lag eine
    # starship.toml mit vier eigenen Literalen.
    "templates-p10k-config",
}


def test_switching_the_theme_rewrites_every_surface_that_carries_a_colour(
        monkeypatch, tmp_path):
    """Der Beleg, dass die Umschaltung den Schreibtisch wirklich trifft.

    Nicht "eine Datei hat sich geaendert": eine Palette, die nur das
    Stylesheet der Leiste erreicht, waere eine Umfaerbung der Leiste.
    Geprueft wird deshalb NAMENTLICH - jede Oberflaeche, die ein Thema
    tragen muss, steht in der Liste darueber:

      die Leiste, die Ueberlagerungen, der Starter, die Zwischenablage,
      der Sperrbildschirm, das Abmeldefenster, das Menue, der
      Stil-Editor, das Rasterbild, GTK4 fuer die fremden Fenster,
      Hyprland samt Fensterleisten und Glasregeln, kitty und die
      Benachrichtigungen.

    Fehlt eine davon, hat dieser Teil des Schreibtischs das Thema
    verloren, und zwar lautlos: er saehe weiterhin vollstaendig richtig
    aus, nur im falschen Thema.
    """
    shipped = _render_all(monkeypatch, tmp_path / "a", theme.DEFAULT)
    other = _render_all(monkeypatch, tmp_path / "b", "tageslicht")

    assert set(shipped) == set(other)
    changed = {name for name in shipped if shipped[name] != other[name]}
    assert CHANGES_WITH_THE_THEME - changed == set(), (
        f"diese Oberflaechen folgen dem Thema nicht mehr: "
        f"{sorted(CHANGES_WITH_THE_THEME - changed)}")
    assert changed - CHANGES_WITH_THE_THEME == set(), (
        f"diese Dateien aendern sich neuerdings mit dem Thema und stehen "
        f"nicht in der Messung: {sorted(changed - CHANGES_WITH_THE_THEME)}. "
        f"Wenn das richtig ist, gehoeren sie in die Liste.")


def test_the_code_palette_does_not_follow_the_theme(monkeypatch, tmp_path):
    """Die Gegenprobe zur zweiten Ausschlussentscheidung.

    "Terminal Green" ist ein Syntaxthema und wird vom Editor UNTER
    DIESEM NAMEN aus seinen eigenen Einstellungen gewaehlt. Ein
    Themenwechsel, der es mitfaerbte, lieferte ein Thema namens Terminal
    Green aus, das nicht gruen ist - src/brand.py sagt das selbst, und
    hier wird es gemessen statt geglaubt.

    Zugleich ist es der Beweis, dass die Umschaltung oben nicht einfach
    jede Datei neu schreibt: hier ist eine mit zwoelf Farben darin, die
    sich nicht bewegt.
    """
    shipped = _render_all(monkeypatch, tmp_path / "a", theme.DEFAULT)
    other = _render_all(monkeypatch, tmp_path / "b", "tageslicht")
    name = "styles-terminal-green-style"
    assert shipped[name] == other[name], (
        "das Syntaxthema des Editors folgt jetzt dem Schreibtisch-Thema")


def test_a_users_own_colour_survives_the_theme(monkeypatch, tmp_path):
    """Das Thema ist die Palette UNTER den eigenen Aenderungen.

    Ohne diese Reihenfolge waere ein Themenwechsel ein Zuruecksetzen -
    wer sein Gelb eingestellt hat, bekaeme beim Umschalten das des
    Themas und haette keinen Weg zurueck ausser dem Gedaechtnis.
    """
    mine = "#123456"
    root = tmp_path / "nutzer"
    root.mkdir(parents=True, exist_ok=True)
    (root / "user-settings.json").write_text(
        '{"schema_version": 1, "colors": {"bar_text": "%s"}}' % mine,
        encoding="utf-8")

    monkeypatch.setenv("ZEPOS_USER_ROOT", str(root))
    variables = _variables_with(monkeypatch, tmp_path,
                                theme.THEMES["tageslicht"])
    assert variables["STYLE_COLOR_BAR_TEXT"] == mine
    # Und der Rest folgt trotzdem dem Thema.
    assert variables["STYLE_BG_COLOR"] == \
        theme.THEMES["tageslicht"]["PETROL"]


# --------------------------------------------------------------------
# 5. Der Name der Maschine
# --------------------------------------------------------------------

def test_no_file_means_the_shipped_theme(tmp_path):
    """Eine frische Installation hat keine Datei, und das ist normal."""
    assert theme.read_name(tmp_path / "gibtsnicht") == theme.DEFAULT


def test_an_empty_file_means_the_shipped_theme(tmp_path):
    """Ebenso eine leere - `: >/etc/zepos/theme` ist kein Themenname."""
    target = tmp_path / "theme"
    target.write_text("\n", encoding="utf-8")
    assert theme.read_name(target) == theme.DEFAULT


def test_writing_an_unknown_name_is_refused(tmp_path):
    """VOR dem Schreiben geprueft, nicht danach.

    Sonst stuende in der Datei ein Name, ueber den der Generator faellt -
    und der Weg zurueck fuehrt durch dieselbe Datei.
    """
    target = tmp_path / "theme"
    with pytest.raises(theme.UnknownTheme):
        theme.write_name("gibtsnicht", target)
    assert not target.exists()


@pytest.mark.parametrize("name", THEMES)
def test_what_is_written_is_what_is_read(name, tmp_path):
    target = tmp_path / "theme"
    theme.write_name(name, target)
    assert theme.read_name(target) == name


def test_the_generator_refuses_an_unknown_theme(monkeypatch, tmp_path):
    """Und zwar bevor es etwas erzeugt.

    Die andere Antwort - stillschweigend das ausgelieferte Thema nehmen -
    waere ein Lauf, der eine Einstellung uebergeht und "erfolgreich
    erzeugt" meldet. Genau das hat _load_user_settings() fuer eine
    kaputte Einstellungsdatei schon einmal verboten, und der Kopf dort
    beziffert, was es gekostet hat.

    Der Anmeldebildschirm entscheidet ABSICHTLICH anders - siehe
    tests/src/test_greeter.py: ein Tippfehler in einer Datei unter /etc
    darf keine Maschine sein, in die niemand mehr hineinkommt.
    """
    (tmp_path / "theme").write_text("gibtsnicht\n", encoding="utf-8")
    monkeypatch.setenv("ZEPOS_MACHINE_ROOT", str(tmp_path))
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path / "nutzer"))
    monkeypatch.syspath_prepend(str(SRC))
    for name in ("style_definition", "theme", "brand", "paths"):
        monkeypatch.delitem(sys.modules, name, raising=False)

    with pytest.raises(Exception) as failure:
        importlib.import_module("style_definition")
    assert "gibtsnicht" in str(failure.value)


# --------------------------------------------------------------------
# 6. Das Bild, das ein Thema mitbringt
# --------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(theme.BACKDROP_GRADIENTS))
def test_the_generated_backdrop_is_what_the_module_builds(name):
    """Byte fuer Byte, wie beim Stylesheet der Anmeldemaske.

    Ein Bild, das nur als Datei danebenliegt, ist eins, dessen zwei
    Endpunkte niemand nachrechnen kann - und an genau diesen zwei
    Zahlen haengt, ob der Schleier des Sperrbildschirms gebraucht wird
    und ob er reicht.
    """
    shipped = (SRC / "branding"
               / theme.THEMES[name]["BACKDROP_FILE"]).read_bytes()
    assert shipped == theme.backdrop_png(name)


@pytest.mark.parametrize("name", THEMES)
def test_every_theme_points_at_a_picture_that_is_there(name):
    """Ein Thema, dessen Bild fehlt, zeichnet GTK einfach nicht - und
    der Sperrbildschirm steht dann auf einer Farbflaeche, deren
    Kontrast gegen etwas anderes gerechnet wurde."""
    picture = SRC / "branding" / theme.THEMES[name]["BACKDROP_FILE"]
    assert picture.is_file(), f"{picture} fehlt"


def test_the_package_ships_every_theme_picture():
    """Die Bilder gehen ueber das Verzeichnis mit, und das ist geprueft.

    src/branding/ wird als Ganzes kopiert; steht das eines Tages nicht
    mehr so im Rezept, faellt das hier auf und nicht auf dem
    Sperrbildschirm einer Installation.
    """
    recipe = (ROOT / "packaging" / "zepos-config"
              / "PKGBUILD").read_text(encoding="utf-8")
    assert re.search(r"^\s*branding\s", recipe, re.M), (
        "zepos-config kopiert src/branding/ nicht mehr als Ganzes - die "
        "Bilder der Themen muessen dann einzeln abgelegt werden")
