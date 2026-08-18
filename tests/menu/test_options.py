# SPDX-License-Identifier: GPL-3.0-or-later
"""Die neun Schalter, gegen die sechs Aufrufer, die sie schreiben.

WARUM DIESE DATEI OHNE ANZEIGE AUSKOMMT
    menu/zepos_menu/options.py fasst kein GTK an. Das ist der Grund, aus
    dem es ein eigenes Modul ist: die Schalterauswertung ist der Teil,
    der falsch sein kann, ohne dass ein Fenster anders aussieht, und er
    muss deshalb hier laufen und nicht in einem Kind auf broadway.

WAS HIER GEMESSEN WIRD UND WAS IN test_menu_headless.py
    Hier: dass ein Schalter ankommt. Dort: dass er etwas bewirkt. Beide
    Haelften sind noetig - ein --width, das in Options landet und das
    Fenster nie erreicht, bestuende diese Datei.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# menu/ in den Suchpfad, bevor zepos_menu importiert wird.
#
# `zepos_menu` liegt nicht in site-packages und soll da auch nicht liegen -
# packaging/zepos-menu/PKGBUILD begruendet das -, also findet ein Import es
# nicht von selbst. /usr/bin/zepos-menu legt sich das Verzeichnis zur
# Laufzeit hin; hier steht dieselbe Zeile.
#
# NICHT IN EINER conftest.py, UND DAS IST TEUER GELERNT
#     Genau dafuer stand hier zuerst tests/menu/conftest.py. pytest legt
#     das Verzeichnis JEDER conftest.py vorne in sys.path, und die Suite
#     hat schon eine: tests/conftest.py, die vier Testdateien mit
#     `import conftest` beim Namen holen. Mit einer zweiten gewann meine.
#     Gemessen am 11.08.2026: 226 fehlgeschlagene Tests, darunter 77 in
#     tests/test_isolation_guard.py, alle mit
#     "module 'conftest' has no attribute '_is_protected'" - der
#     Isolationswaechter war fuer die halbe Suite verschwunden. Jede Datei
#     fuer sich lief gruen.
sys.path.insert(0, str(ROOT / "menu"))

from zepos_menu import options as opt        # noqa: E402

TEMPLATES = ROOT / "src" / "templates"
STYLES = ROOT / "src" / "styles"

# Die sechs erzeugten Dateien, die zepos-menu aufrufen. Namentlich, weil
# "irgendwo im Baum" die Frage nicht ist: jede einzelne davon ist ein
# Skript, das ohne das Fenster nichts mehr tut.
CALLERS = (
    "cliphist-menu-config",
    "network-manager-gui-config",
    "printer-manager-config",
    "floating-window-manager",
    "hyprland-plugins-config",
    "hyprland-universal-config",
)


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    directory = tmp_path / "config" / "zepos-menu"
    directory.mkdir(parents=True)
    return directory


# --------------------------------------------------------------------
# Die Schalter selbst
# --------------------------------------------------------------------

def test_dmenu_is_the_mode_the_five_scripts_ask_for(home):
    assert opt.parse(["--dmenu"]).mode == "dmenu"


def test_drun_is_what_super_space_falls_back_to(home):
    assert opt.parse(["--show", "drun"]).mode == "drun"


def test_both_spellings_of_every_switch_are_understood(home):
    """floating-window-manager schreibt `--cache-file=/dev/null`,
    cliphist-menu schreibt `--cache-file /dev/null`, und
    network-manager-gui mischt `--sort-order=default` mit `--width 500`
    in EINEM Aufruf. Ein Ersatz, der nur eine der beiden Schreibweisen
    kennt, macht drei Skripte kaputt und zwei nicht."""
    joined = opt.parse(["--dmenu", "--cache-file=/dev/null",
                        "--sort-order=default", "--width=450",
                        "--height=200", "--prompt=Netzwerk"])
    spaced = opt.parse(["--dmenu", "--cache-file", "/dev/null",
                        "--sort-order", "default", "--width", "450",
                        "--height", "200", "--prompt", "Netzwerk"])
    assert joined == spaced
    assert joined.cache_file == Path("/dev/null")
    assert joined.sort_order == "default"
    assert (joined.width, joined.height) == (450, 200)
    assert joined.prompt == "Netzwerk"


def test_password_is_off_unless_it_is_asked_for(home):
    assert opt.parse(["--dmenu"]).password is False
    assert opt.parse(["--dmenu", "--password"]).password is True


def test_insensitive_can_be_switched_on_but_never_off(home):
    """network-manager-gui uebergibt --insensitive, obwohl die erzeugte
    Konfiguration insensitive=true ohnehin sagt: das Skript kann nicht
    wissen, was in der Datei steht. Ein Schalter, der einen Wert aus der
    Datei UEBERSCHREIBEN wuerde, machte den Aufruf zu einem
    Ausschalter."""
    (home / "config").write_text("insensitive=false\n", encoding="utf-8")
    assert opt.parse(["--dmenu"]).insensitive is False
    assert opt.parse(["--dmenu", "--insensitive"]).insensitive is True

    # Und die Richtung, die die beiden Zeilen darueber NICHT abdecken:
    # steht in der Datei "true" und faellt der Schalter weg, muss es
    # true bleiben. Ohne diese Zeile bestuende auch ein Programm, das
    # den Schalter statt der Datei nimmt - gemessen mit genau dieser
    # Mutation am 11.08.2026, die drei Zeilen darueber liefen gruen.
    (home / "config").write_text("insensitive=true\n", encoding="utf-8")
    assert opt.parse(["--dmenu"]).insensitive is True


def test_an_abbreviated_switch_is_not_guessed_at(home):
    """argparse ratet Praefixe von sich aus. `--pass` waere dann
    `--password`, `--sort` waere `--sort-order` - und ein Tippfehler in
    einem erzeugten Skript liefe jahrelang als etwas anderes durch."""
    with pytest.raises(SystemExit):
        opt.parse(["--dmenu", "--pass"])


def test_an_unknown_switch_stops_the_program(home):
    with pytest.raises(SystemExit) as stop:
        opt.parse(["--dmenu", "--erfundenes"])
    assert stop.value.code == 2


def test_a_show_mode_that_is_not_built_says_which_one_is(home):
    with pytest.raises(SystemExit) as stop:
        opt.parse(["--show", "run"])
    assert "drun" in str(stop.value.code)


def test_dmenu_is_a_switch_and_not_a_value_of_show(home):
    """`show=dmenu` in der Datei waere eine Betriebsart ohne stdin: das
    Fenster ginge leer auf und niemand wuesste, worauf es wartet."""
    (home / "config").write_text("show=dmenu\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        opt.parse([])


# --------------------------------------------------------------------
# Die Konfigurationsdatei
# --------------------------------------------------------------------

def test_the_command_line_beats_the_file_which_beats_the_default(home):
    (home / "config").write_text("width=800\nheight=600\n", encoding="utf-8")

    assert opt.parse(["--dmenu"]).width == 800
    assert opt.parse(["--dmenu", "--width", "350"]).width == 350
    (home / "config").unlink()
    assert opt.parse(["--dmenu"]).width == opt.DEFAULTS["width"]


def test_a_missing_file_is_not_an_error(home):
    """Der Starter ist die Taste, ohne die ein Desktop nicht bedienbar
    ist. Eine fehlende Konfiguration darf ihn nicht ausschalten."""
    assert opt.parse(["--dmenu"]).prompt == opt.DEFAULTS["prompt"]


def test_an_unknown_key_is_reported_and_does_not_stop_anything(home):
    (home / "config").write_text("width=800\nfarbe=blau\n", encoding="utf-8")
    warnings: list[str] = []

    parsed = opt.parse(["--dmenu"], warn=warnings.append)

    assert parsed.width == 800
    assert any("farbe" in message for message in warnings), warnings


def test_a_number_that_is_not_a_number_is_reported_and_skipped(home):
    (home / "config").write_text("width=breit\n", encoding="utf-8")
    warnings: list[str] = []

    parsed = opt.parse(["--dmenu"], warn=warnings.append)

    assert parsed.width == opt.DEFAULTS["width"]
    assert any("breit" in message for message in warnings), warnings


def test_a_hash_inside_a_value_stays_in_the_value(home):
    """Nur ganze Zeilen sind Kommentare. Ein `#` mitten in einer Zeile
    abzuschneiden hiesse, jeden Text mit einem Doppelkreuz darin still
    zu halbieren."""
    (home / "config").write_text("prompt=Suchen # jetzt\n", encoding="utf-8")

    assert opt.parse(["--dmenu"]).prompt == "Suchen # jetzt"


# --------------------------------------------------------------------
# Das Zaehlwerk
# --------------------------------------------------------------------

def test_each_mode_counts_for_itself(home):
    """Ein gemeinsamer Speicher wuerfe die Namen der Anwendungen mit den
    Zeilen der Zwischenablage zusammen - und der Verlauf liefert bei
    jedem Aufruf andere Zeilen, also waechst er unbegrenzt und ordnet
    nichts."""
    assert opt.parse(["--dmenu"]).cache_file \
        != opt.parse(["--show", "drun"]).cache_file


def test_the_count_lives_under_the_cache_home_and_nowhere_else(home,
                                                              tmp_path):
    assert opt.parse(["--dmenu"]).cache_file.is_relative_to(
        tmp_path / "cache")


# --------------------------------------------------------------------
# Die erzeugte Konfiguration und dieses Modul muessen sich einig sein
# --------------------------------------------------------------------

def _template_keys() -> set[str]:
    text = (TEMPLATES / "zepos-menu-config.template").read_text(
        encoding="utf-8")
    code = "\n".join(line for line in text.splitlines()
                     if line.strip() and not line.lstrip().startswith("#"))
    return {line.split("=", 1)[0].strip() for line in code.splitlines()}


def test_the_generated_configuration_sets_exactly_the_keys_that_are_read():
    """Beide Richtungen, und beide sind schon einmal schiefgegangen.

    Ein Schluessel in der Datei, den niemand liest, ist eine Einstellung,
    die jemand aendert und deren Ausbleiben er sich nicht erklaeren kann -
    wofis erzeugte Konfiguration hatte elf davon. Ein Schluessel im Code,
    den die Datei nicht setzt, ist eine Vorgabe, die nirgends steht und
    die niemand findet, der sie sucht.
    """
    assert _template_keys() == set(opt.DEFAULTS)


def test_the_defaults_here_are_the_values_the_template_writes():
    """Bis auf den Text der Eingabezeile, dem die Vorlage das
    Lupensymbol aus der Symboldatenbank voranstellt - vor dem Erzeugen
    gibt es dieses Zeichen nicht."""
    text = (TEMPLATES / "zepos-menu-config.template").read_text(
        encoding="utf-8")
    written = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition("=")
        written[key.strip()] = value.strip()

    for key, value in opt.DEFAULTS.items():
        if key == "prompt":
            continue
        expected = str(value).lower() if isinstance(value, bool) else str(value)
        assert written[key] == expected, (
            f"{key}: die Vorlage schreibt {written[key]!r}, "
            f"options.DEFAULTS sagt {expected!r}")


# --------------------------------------------------------------------
# Die Aufrufer
# --------------------------------------------------------------------

def _caller_text(name: str) -> str:
    return (TEMPLATES / f"{name}.template").read_text(encoding="utf-8")


def _caller_code(name: str) -> str:
    """Die Vorlage ohne ihre Kommentarzeilen, Fortsetzungen verbunden.

    ZWEI GRUENDE, UND BEIDE HABEN HEUTE ZUGESCHLAGEN
        1. Jede dieser Dateien ERKLAERT im Kopf, was sie tut, und
           mehrere nennen dabei den Vorgaenger. `"wofi" in datei` waere
           auch dann wahr, wenn das Wort nur in einer Begruendung steht -
           die Pruefung faende einen Fehler in genau dem Absatz, der
           seine Abwesenheit beschreibt. Also zeilenweise gegen den Code.

        2. network-manager-gui schreibt EINEN Aufruf ueber sechs Zeilen
           mit einem Rueckstrich am Ende. Zeilenweise gelesen steht "zepos-menu" in der
           ersten und `--width` in der dritten, und eine Suche nach
           Schaltern auf Zeilen mit dem Programmnamen faende genau einen
           von sieben. Die Fortsetzungen werden deshalb verbunden.
    """
    code = [line for line in _caller_text(name).splitlines()
            if not line.lstrip().startswith("#")]
    joined: list[str] = []
    for line in code:
        if joined and joined[-1].endswith("\\"):
            joined[-1] = joined[-1][:-1].rstrip() + " " + line.strip()
        else:
            joined.append(line)
    return "\n".join(joined)


@pytest.mark.parametrize("name", CALLERS)
def test_no_caller_still_reaches_for_the_old_launcher(name):
    for number, line in enumerate(_caller_code(name).splitlines(), start=1):
        assert "wofi" not in line, (
            f"{name}.template:{number} ruft noch wofi auf: {line.strip()}")


@pytest.mark.parametrize("name", CALLERS)
def test_every_caller_names_the_new_one(name):
    assert "zepos-menu" in _caller_code(name) \
        or "cliphist-menu.sh" in _caller_code(name), (
        f"{name}.template ruft weder zepos-menu noch das Skript auf, das "
        "es benutzt - dann ist es kein Aufrufer mehr und gehoert nicht "
        "in CALLERS")


def test_every_switch_the_callers_write_is_a_switch_this_program_has():
    """Die Pruefung, um die es bei diesem Austausch ueberhaupt geht.

    Ein Ersatz, der einen benutzten Schalter nicht kennt, macht sechs
    Helferskripte kaputt statt eines Programms besser - und zwar leise:
    argparse beendet sich mit 2, der Aufrufer liest eine leere Ausgabe
    und haelt sie fuer einen Abbruch durch den Nutzer.
    """
    known = set()
    for action in opt.build_parser()._actions:
        known.update(action.option_strings)

    used: dict[str, set[str]] = {}
    for name in CALLERS:
        for line in _caller_code(name).splitlines():
            if "zepos-menu" not in line:
                continue
            for switch in re.findall(r"(--[a-z-]+)", line):
                used.setdefault(switch, set()).add(name)

    unknown = {switch: sorted(names) for switch, names in used.items()
               if switch not in known}
    assert unknown == {}, (
        "diese Schalter stehen in erzeugten Skripten und kennt "
        f"zepos-menu nicht: {unknown}")

    # Und die Gegenrichtung: neun Schalter waren gemessen, neun sind
    # gebaut. Ein zehnter waere Code, den kein Aufrufer erreicht.
    assert known - {"-h", "--help"} == {
        "--show", "--dmenu", "--prompt", "--width", "--height",
        "--password", "--insensitive", "--sort-order", "--cache-file",
    }


# --------------------------------------------------------------------
# Die Hoehengrenze
# --------------------------------------------------------------------

def test_the_modal_share_is_the_one_in_the_size_table():
    """Zwei Abdruecke einer Zahl, ueber eine Paketgrenze hinweg.

    zepos-menu importiert nichts aus zepos-config - der Grund steht im
    Kopf von menu/zepos_menu/index.py -, also steht MODAL_SHARE dort ein
    zweites Mal. Ein zweiter Ort fuer eine Zahl ist nur dann keine
    Kopie, wenn etwas die beiden gegeneinander haelt.

    Und der Kopf dieses Fensters muss ohne `gi` lesbar bleiben: die
    Konstante wird aus dem Quelltext geholt und nicht importiert, weil
    window.py GTK hereinzieht und diese Suite es nicht hat.
    """
    import re
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "src"))
    try:
        import sizes
    finally:
        sys.path.remove(str(root / "src"))

    source = (root / "menu" / "zepos_menu" / "window.py").read_text(
        encoding="utf-8")
    found = re.search(r"^MODAL_SHARE = ([0-9.]+)$", source, re.M)
    assert found, "menu/zepos_menu/window.py kennt keine Hoehengrenze mehr"
    assert float(found.group(1)) == sizes.MEASURE_MODAL_SHARE, (
        f"das Suchfenster deckelt bei {found.group(1)}, die Groessentabelle "
        f"sagt {sizes.MEASURE_MODAL_SHARE}")

    # Und die Grenze greift ueberhaupt: die ausgelieferte Vorgabe ist
    # groesser als die Haelfte eines verbreiteten Schirms, sonst waere
    # der Deckel eine Zeile ohne Wirkung.
    assert opt.DEFAULTS["height"] > 1080 * sizes.MEASURE_MODAL_SHARE, (
        "die Vorgabehoehe liegt schon unter der Grenze - dann prueft "
        "diese Zusicherung nichts")
    assert "capped(" in (root / "menu" / "zepos_menu" / "window.py").read_text(
        encoding="utf-8"), (
        "das Fenster ruft die Begrenzung nicht auf")
