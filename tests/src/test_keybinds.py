# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Tastenuebersicht KANN nicht mehr luegen - nicht: sie stimmt heute.

DER UNTERSCHIED IST DIE GANZE DATEI
    Eine Zusicherung, die "SUPER+SHIFT+B startet firefox und die
    Uebersicht sagt Firefox" prueft, ist am naechsten Tag richtig und
    beim uebernaechsten Commit falsch. Was hier gemessen wird, ist die
    BAUART:

      1. Es gibt keine Bindung ohne Beschreibung. Wer eine Taste
         hinzufuegt, muss sagen, was sie tut, sonst faellt die Suite.
      2. Es gibt keine Beschreibung ohne Bindung. Sie steht unmittelbar
         ueber ihrer Zeile und nirgends sonst.
      3. Jeder Programmname, den eine Beschreibung in Klammern nennt,
         ist ein Wort DESSELBEN Kommandos. Ohne Ausnahmeliste.
      4. Die beiden Oberflaechen, die Tasten zeigen, enthalten keine
         einzige Taste. Sie haben nichts, womit sie luegen koennten.

    Punkt 4 ist der eigentliche. Am 11.08.2026 wurde in einer der beiden
    Listen "Browser (Epiphany)" auf Firefox korrigiert; die ANDERE Liste
    hat die Korrektur nie erreicht und stand am 12.08.2026 noch immer
    falsch da. Solange es Listen gibt, kann eine davon zurueckbleiben.

GEMESSEN, WOGEGEN
    Gegen den Baum, den EIN vollstaendiger `--all`-Lauf hinterlaesst,
    wie tests/src/test_usable_desktop.py und aus demselben Grund:
    plugins.py entscheidet beim Erzeugen, welche Bindung ueberhaupt in
    die Datei kommt.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.generated_tree import GeneratedTree, build

REPOSITORY = Path(__file__).resolve().parents[2]
SRC = REPOSITORY / "src"

# Der Lauf spawnt den Generator. Die Marke steht auf dem MODUL, damit
# `-k` nicht die Weigerung des Waechters zum Fehlschlag macht.
pytestmark = pytest.mark.allow_subprocess


def _module(name: str, path: Path):
    sys.path.insert(0, str(SRC))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SRC))


keybinds = _module("zepos_keybinds_probe", SRC / "keybinds.py")


@pytest.fixture(scope="module")
def tree(tmp_path_factory) -> GeneratedTree:
    return build(tmp_path_factory.mktemp("keybinds"))


def _configs(tree: GeneratedTree) -> list[Path]:
    found = [tree.config.joinpath(*where)
             for where in keybinds.OVERVIEW_CONFIGS]
    present = [path for path in found if path.is_file()]
    assert present, f"der Lauf hat keine dieser Dateien erzeugt: {found}"
    return present


# --------------------------------------------------------------------
# 1. keine Bindung ohne Beschreibung
# --------------------------------------------------------------------

def test_every_bind_line_the_run_writes_carries_a_description(tree):
    """Die Zusicherung, an der eine neue Taste scheitert.

    Nicht "die heutigen Tasten sind beschrieben", sondern "eine
    unbeschriebene ist nicht ausliefer bar". Wer eine bind-Zeile
    hinzufuegt und die Markierung vergisst, sieht seinen Fehler hier und
    nicht der Nutzer im Fenster.
    """
    nameless = []
    for path in _configs(tree):
        for binding in keybinds.parse(path.read_text(), path.name):
            if not binding.description:
                nameless.append(f"{path.name}: {binding.where}")

    assert nameless == [], (
        "bind-Zeilen ohne `# @Gruppe: Beschreibung` darueber - sie waeren "
        "in keiner Uebersicht und in keiner Suche zu finden: "
        + "; ".join(nameless))


def test_the_count_of_descriptions_equals_the_count_of_bind_lines(tree):
    """Der unabhaengige Gegenzaehler.

    Die Zusicherung darueber benutzt denselben Auswerter, der die
    Bindungen findet: findet er eine Zeile gar nicht, meldet er auch
    keine fehlende Beschreibung fuer sie. Also wird hier ein zweites Mal
    gezaehlt, so einfach wie moeglich - jede Zeile, die mit `bind`
    anfaengt und ein `=` hat -, und die beiden Zahlen muessen
    uebereinstimmen.
    """
    for path in _configs(tree):
        text = path.read_text()
        rough = [line for line in text.splitlines()
                 if line.lstrip().startswith("bind") and "=" in line]
        parsed = keybinds.parse(text, path.name)
        assert len(parsed) == len(rough), (
            f"{path.name}: der Auswerter findet {len(parsed)} Bindungen, "
            f"eine blosse Zaehlung findet {len(rough)}")


def test_a_marker_without_a_bind_line_under_it_belongs_to_nothing(tree):
    """Die Gegenrichtung, und sie ist keine Formsache.

    Eine Markierung, unter der keine bind-Zeile steht, ist eine
    Beschreibung, die nie irgendwo erscheint - und beim naechsten Lesen
    haelt jemand sie fuer die Beschreibung der naechsten Taste, die er
    findet. Gezaehlt wird deshalb: so viele Markierungen wie
    beschriebene Bindungen.
    """
    for path in _configs(tree):
        text = path.read_text()
        markers = [line for line in text.splitlines()
                   if keybinds.MARKER.match(line)]
        described = keybinds.described(keybinds.parse(text, path.name))
        assert len(markers) == len(described), (
            f"{path.name}: {len(markers)} Markierungen, aber "
            f"{len(described)} beschriebene Bindungen - eine davon steht "
            f"ueber etwas, das keine Taste ist")


# --------------------------------------------------------------------
# 2. keine Beschreibung, die ein anderes Programm nennt
# --------------------------------------------------------------------

# Wie ein Wort einer Kommandozeile aussieht. Der Schraegstrich TRENNT,
# damit `~/.config/hypr/cliphist-menu.sh` das Wort "cliphist-menu.sh"
# enthaelt - eine Beschreibung nennt den Namen des Skripts und nicht
# seinen Pfad.
WORD = re.compile(r"[^\w.@+-]+")


def test_no_description_names_a_program_its_own_key_does_not_run(tree):
    """DER FUND VOM 11.08.2026, ALS REGEL.

    "SUPER + SHIFT + B - Browser (Epiphany)" stand in beiden
    Uebersichten, waehrend die Bindung firefox startet. Der Grund war
    nicht Nachlaessigkeit, sondern Entfernung: die Beschreibung stand in
    einer anderen Datei als das Kommando.

    Jetzt stehen sie uebereinander, und diese Zusicherung haelt sie
    zusammen - fuer JEDE Bindung, ohne Ausnahmeliste. Was in Klammern
    steht, muss ein Wort dessen sein, was die Taste ausfuehrt.

    Die Klammern sind damit fuer Programmnamen reserviert, und das ist
    die Bedingung, unter der die Regel vollstaendig sein kann: sobald sie
    auch Praezisierungen aufnehmen duerften ("Vollbild (echtes)"),
    muesste diese Pruefung entscheiden, was ein Programmname ist, und
    genau diese Entscheidung hat "Epiphany" durchgelassen - der Name ist
    kein ausgeliefertes Paket.
    """
    disagreeing = []
    for path in _configs(tree):
        for binding in keybinds.parse(path.read_text(), path.name):
            words = {word for word in WORD.split(binding.runnable.lower())
                     if word}
            for group in re.findall(r"\(([^)]*)\)", binding.description):
                for token in re.split(r"[,/]", group):
                    token = token.strip().lower()
                    if token and token not in words:
                        disagreeing.append(
                            f"{path.name}: {binding.where} nennt "
                            f"\"{token}\" und fuehrt `{binding.runnable}` aus")

    assert disagreeing == [], (
        "Beschreibungen, die ein anderes Programm nennen als ihre eigene "
        "Taste startet: " + "; ".join(disagreeing))


def test_the_check_catches_the_epiphany_that_started_all_of_this():
    """Die Selbstpruefung, ohne die alles darueber wertlos ist.

    Eine Regel, die nichts findet, meldet Ruhe - genau der Zustand, in
    dem dieses Projekt am 11.08.2026 war.
    """
    lied = keybinds.parse(
        "# @Anwendungen: Browser (Epiphany)\n"
        "bind = $mainMod SHIFT, B, exec, firefox\n")
    assert len(lied) == 1
    words = {word for word in WORD.split(lied[0].runnable.lower()) if word}
    assert "epiphany" not in words, (
        "die Zerlegung haelt epiphany fuer ein Wort von `firefox`")

    honest = keybinds.parse(
        "# @Anwendungen: Browser (firefox)\n"
        "bind = $mainMod SHIFT, B, exec, firefox\n")
    words = {word for word in WORD.split(honest[0].runnable.lower()) if word}
    assert "firefox" in words

    # Und die drei Haelften einer Kette, von denen die Regel jede
    # einzelne sehen muss: `grim` allein waere ein Bildschirmfoto ohne
    # Bereichsauswahl und ohne Beschriftung.
    chain = keybinds.parse(
        "# @Bildschirm: Bildschirmfoto (grim, slurp, satty)\n"
        'bind = $mainMod, S, exec, grim -g "$(slurp)" - | satty -f -\n')
    words = {word for word in WORD.split(chain[0].runnable.lower()) if word}
    for expected in ("grim", "slurp", "satty"):
        assert expected in words, words


# --------------------------------------------------------------------
# 3. der Auswerter selbst
# --------------------------------------------------------------------

def test_the_marker_reaches_exactly_one_line_down():
    """Unmittelbar darueber, und keine Zeile weiter.

    Traege sie ueber eine Leerzeile hinweg, landete eine Beschreibung
    frueher oder spaeter an der Taste darunter - und zwar lautlos, weil
    beide Zeilen fuer sich richtig aussehen.
    """
    attached = keybinds.parse(
        "# @Fenster: Fenster schliessen\n"
        "bind = $mainMod SHIFT, X, killactive\n")
    assert [(b.group, b.description) for b in attached] == [
        ("Fenster", "Fenster schliessen")]

    detached = keybinds.parse(
        "# @Fenster: Fenster schliessen\n"
        "\n"
        "bind = $mainMod SHIFT, X, killactive\n")
    assert detached[0].description == "", (
        "eine Markierung hat ueber eine Leerzeile hinweg getragen")

    prose = keybinds.parse(
        "# @Fenster: Fenster schliessen\n"
        "# Und hier steht, warum.\n"
        "bind = $mainMod SHIFT, X, killactive\n")
    assert prose[0].description == "", (
        "eine Markierung hat ueber eine Kommentarzeile hinweg getragen")


def test_a_commented_out_bind_is_not_a_bind():
    """Gemessen: `# bind = $mainMod, E, exec, thunar` stand in diesem
    Baum. Eine Pruefung, die sie liest, meldet ein Programm, das keine
    Taste mehr aufruft."""
    assert keybinds.parse("# bind = $mainMod, E, exec, thunar\n") == []
    assert keybinds.parse("   #bind = $mainMod, E, exec, thunar\n") == []


def test_every_bind_form_this_project_writes_is_understood():
    """bind, bindm und die Zeile ohne Argument.

    `bindm = $mainMod, mouse:272, movewindow` hat drei Felder, `bind =
    $mainMod SHIFT, Z, hyprzones:editor,` vier mit leerem vierten. Beide
    stehen in diesem Projekt, und ein Auswerter, der eine davon
    ueberspringt, laesst genau die Taste unbeschrieben, die er nicht
    sieht.
    """
    found = keybinds.parse(
        "# @Maus: Fenster bewegen\n"
        "bindm = $mainMod, mouse:272, movewindow\n"
        "# @Zonen: Zonen-Editor\n"
        "bind = $mainMod SHIFT, Z, hyprzones:editor,\n"
        "# @Medien: Abspielen (playerctl)\n"
        "bindl = , XF86AudioPlay, exec, playerctl play-pause\n")
    assert [(b.where, b.dispatcher, b.argument) for b in found] == [
        ("SUPER+mouse:272", "movewindow", ""),
        ("SUPER SHIFT+Z", "hyprzones:editor", ""),
        ("XF86AudioPlay", "exec", "playerctl play-pause"),
    ]
    assert [b.chord for b in found] == [
        "SUPER + mouse:272", "SUPER + SHIFT + Z", "XF86AudioPlay"]


def test_a_users_own_bindd_is_read_and_not_mistaken_for_a_dispatcher():
    """Was save-profile aus einer laufenden Sitzung schreiben KANN.

    ZepOS selbst schreibt kein `bindd` - der Kopf von src/keybinds.py
    sagt, warum -, aber profile-keybinds.conf traegt, was der Nutzer
    gebunden hat. Ohne diesen Zweig waere dort die Beschreibung der
    Dispatcher, und die Uebersicht meldete eine Taste, die "Mein
    Terminal" ausfuehrt.
    """
    found = keybinds.parse(
        "bindd = SUPER, Y, Mein Terminal, exec, kitty\n")
    assert len(found) == 1
    assert found[0].dispatcher == "exec"
    assert found[0].argument == "kitty"
    assert found[0].commands == ["kitty"]


def test_a_dispatcher_becomes_a_command_a_click_can_run():
    """Die Haelfte, die "zusaetzlich zu den keybinds" heisst.

    Ein `exec` ist schon eine Shell-Zeile. Alles andere ist ein
    Dispatcher, und ohne diese Umrechnung waere jede zweite Bindung
    dieses Projekts zwar auffindbar, aber nicht ausloesbar - was der
    Nutzer ausdruecklich verlangt hat.
    """
    found = keybinds.parse(
        "bind = $mainMod, D, workspace, special:minimized\n"
        "bind = $mainMod SHIFT, X, killactive\n"
        'bind = $mainMod, S, exec, grim -g "$(slurp)" - | satty -f -\n')
    assert [b.runnable for b in found] == [
        "hyprctl dispatch workspace special:minimized",
        "hyprctl dispatch killactive",
        'grim -g "$(slurp)" - | satty -f -',
    ]


# --------------------------------------------------------------------
# 4. die Oberflaechen haben nichts, womit sie luegen koennten
# --------------------------------------------------------------------

# Eine Tastenkombination, wie eine von Hand gepflegte Liste sie schreibt.
# Beide alten Listen sahen so aus: "SUPER + SHIFT + B" und
# "Super + Shift + B".
CHORD_LITERAL = re.compile(
    r"\b(?:SUPER|Super)\s*\+\s*\w", re.IGNORECASE)


def _code(text: str) -> str:
    """Die Datei ohne Kommentare und ohne Doktexte.

    Gemessen wird, was das Programm TUT, nicht was daneben steht. Beide
    Dateien erklaeren in ihrem Kopf, welche Tasten es einmal gab und
    warum die Liste weg ist - eine Pruefung, die das als Rueckfall
    liest, verbietet genau die Begruendung, die den Rueckfall verhindert.

    Umgekehrt reicht sie aus: eine Liste, die wirken soll, muss im Code
    stehen. Eine in einem Kommentar zeigt niemandem etwas.
    """
    kept: list[str] = []
    in_docstring = False
    for line in text.splitlines():
        stripped = line.strip()
        if in_docstring:
            if '"""' in stripped:
                in_docstring = False
            continue
        if stripped.startswith('"""') or stripped.startswith('r"""'):
            # Ein einzeiliger Doktext oeffnet und schliesst in derselben
            # Zeile; er zaehlt genauso wenig wie ein mehrzeiliger.
            if stripped.count('"""') == 1:
                in_docstring = True
            continue
        if stripped.startswith("#") or stripped.startswith("//"):
            continue
        kept.append(line)
    return "\n".join(kept)


@pytest.mark.parametrize("where", [
    ("ags", "scripts", "hypr-shortcuts.py"),
    ("ags", "widget", "Shortcuts.tsx"),
])
def test_no_surface_that_shows_keys_contains_a_key(tree, where):
    """DIE ZUSICHERUNG, UM DIE ES IN DIESER GANZEN AUFGABE GEHT.

    Sie prueft nicht, dass die Uebersicht heute stimmt. Sie prueft, dass
    sie nichts hat, womit sie etwas anderes sagen KOENNTE als die
    Konfiguration: in beiden Dateien steht keine einzige
    Tastenkombination.

    Ohne diese Zusicherung waere die Ableitung eine Entscheidung, die
    beim naechsten "ich trag das schnell von Hand nach" wieder verloren
    geht. Genau so sind die beiden Listen entstanden, die es hier
    gab - 65 Eintraege in der einen, 77 in der anderen, und keiner der
    beiden hat je jemand angesehen, ob er noch stimmt.

    Die einzige erlaubte Ausnahme steht in der Fusszeile des
    Leistenmoduls: SUCHTASTE, die Taste, mit der man alles durchsucht.
    Sie ist keine Liste, sondern der Weg zur Liste, und sie wird
    ausdruecklich gegen die Konfiguration geprueft - siehe
    test_the_footer_key_of_the_bar_module_is_really_bound.
    """
    path = tree.config.joinpath(*where)
    assert path.is_file(), f"{path} wurde nicht erzeugt"

    text = _code(path.read_text())
    if path.name == "hypr-shortcuts.py":
        # Der eine erlaubte Wert, mit Namen und nicht als Ausnahme fuer
        # alles, was zufaellig so aussieht.
        text = "\n".join(line for line in text.splitlines()
                         if not line.strip().startswith("SUCHTASTE ="))

    literals = CHORD_LITERAL.findall(text)
    assert literals == [], (
        f"{path.name} traegt wieder Tastenkombinationen im Quelltext - "
        f"das ist die zweite Liste, die zurueckbleibt: {literals}")


def test_the_footer_key_of_the_bar_module_is_really_bound(tree):
    """Die eine Taste, die das Leistenmodul selbst nennt.

    Sie steht dort, weil ein Tooltip, der nicht alles zeigen kann, sagen
    muss, wo der Rest ist. Sie ist damit die letzte Zeichenkette in
    diesem Baum, die eine Taste behauptet, ohne sie zu lesen - also wird
    genau sie gegen die Konfiguration gehalten.
    """
    module = tree.config / "ags" / "scripts" / "hypr-shortcuts.py"
    named = re.search(r'^SUCHTASTE = "([^"]+)"', module.read_text(), re.M)
    assert named, "das Leistenmodul nennt keine Suchtaste"

    chords = {binding.chord
              for path in _configs(tree)
              for binding in keybinds.parse(path.read_text(), path.name)}
    assert named.group(1) in chords, (
        f"das Leistenmodul nennt {named.group(1)}, und diese Taste ist in "
        f"der erzeugten Konfiguration nicht gebunden")


def test_the_overlay_recognises_the_emergency_keys_by_their_file(tree):
    """Der Dateiname, an dem die Ueberlagerung die Notfalltasten faerbt.

    Sie kann sie nicht am Gruppennamen erkennen - der ist deutscher Text
    aus einer Vorlage und beim naechsten Umformulieren ein anderer. Sie
    nimmt die Datei, und die muss eine sein, die der Leser ueberhaupt
    liest.
    """
    overlay = (tree.config / "ags" / "widget" / "Shortcuts.tsx").read_text()
    named = re.search(r'^const FAILSAFE_SOURCE = "([^"]+)"', overlay, re.M)
    assert named, "die Ueberlagerung nennt keine Notfalldatei"
    assert named.group(1) in {where[-1]
                              for where in keybinds.OVERVIEW_CONFIGS}, (
        f"die Ueberlagerung faerbt nach {named.group(1)}, und diese Datei "
        f"liest keybinds.OVERVIEW_CONFIGS gar nicht")


def test_the_overlay_calls_the_one_reader_and_parses_nothing_itself(tree):
    """Kein zweiter Auswerter fuer Hyprlands Syntax, in keiner Sprache.

    Ein Auswerter in TypeScript waere wieder eine zweite Wahrheit - er
    wuerde bei der ersten Bindungsform, die er nicht kennt, still eine
    Taste weglassen.
    """
    overlay = (tree.config / "ags" / "widget" / "Shortcuts.tsx").read_text()
    assert "keybinds.py" in overlay, (
        "die Ueberlagerung ruft den Leser nicht auf")
    assert '"--json"' in overlay
    for forbidden in ("bind =", "bindm", "$mainMod"):
        assert forbidden not in overlay, (
            f"die Ueberlagerung wertet Hyprlands Syntax selbst aus: "
            f"{forbidden}")


# --------------------------------------------------------------------
# 5. die Suche ist selbst auffindbar
# --------------------------------------------------------------------

SEARCH_COMMAND = "zepos-menu --show all"


def test_the_search_over_everything_has_a_key_and_the_bar_opens_it(tree):
    """"vorhanden, aber unauffindbar" ist dasselbe wie "fehlt".

    Das gilt fuer die Suche selbst am staerksten: eine, die man nur
    findet, wenn man sie schon kennt, ist keine. Also zwei Wege, und
    beide werden gemessen - eine Taste, und ein Klick auf ein Modul, das
    dauernd auf dem Schirm steht.
    """
    bound = [binding for path in _configs(tree)
             for binding in keybinds.parse(path.read_text(), path.name)
             if SEARCH_COMMAND in binding.runnable]
    assert bound, f"keine Taste oeffnet `{SEARCH_COMMAND}`"
    for binding in bound:
        assert binding.description, (
            f"{binding.where} oeffnet die Suche und beschreibt sich nicht - "
            f"dann steht sie in der Suche selbst nicht drin")

    module = (tree.config / "ags" / "scripts" / "hypr-shortcuts.py")
    answer = json.loads(subprocess.run(
        [sys.executable, str(module)],
        capture_output=True, text=True, timeout=60,
        env={"HOME": str(tree.home), "PATH": ""}).stdout)
    assert answer["on-click"] == SEARCH_COMMAND, (
        "der Klick auf das Tastenmodul oeffnet nicht die Suche, sondern: "
        + repr(answer["on-click"]))


def test_the_bar_module_answers_from_the_configuration_and_not_from_itself(tree):
    """Das Leistenmodul, wirklich ausgefuehrt.

    Eine Textpruefung an der erzeugten Datei sagt, dass keine Liste
    darin steht. Sie sagt nicht, dass etwas herauskommt - und ein Modul,
    das keine Liste mehr hat und auch nichts liest, waere ein leerer
    Tooltip, den niemand als Fehler erkennt.
    """
    module = tree.config / "ags" / "scripts" / "hypr-shortcuts.py"
    result = subprocess.run(
        [sys.executable, str(module)], capture_output=True, text=True,
        timeout=60, env={"HOME": str(tree.home), "PATH": ""})
    assert result.returncode == 0, result.stderr
    answer = json.loads(result.stdout)

    described = keybinds.described(
        keybinds.read(root=tree.config.parent / ".config"))
    assert described, "der erzeugte Baum hat keine beschriebene Bindung"

    # Die Zahl im Modul ist gezaehlt, nicht geschrieben.
    count = re.search(r"(\d+)", answer["text"])
    assert count, answer["text"]
    assert int(count.group(1)) >= len(described), (
        f"das Modul zeigt {count.group(1)}, gelesen wurden "
        f"{len(described)} Bindungen")

    # Und der Tooltip nennt die Bildschirmfoto-Zeile, um die es ging.
    screenshot = [binding for binding in described
                  if binding.chord == "SUPER + S"]
    assert screenshot, "SUPER+S ist nicht beschrieben"
    assert screenshot[0].description in answer["tooltip"], (
        "der Tooltip zeigt die Bildschirmfoto-Zeile nicht")


def test_the_reader_answers_the_same_thing_on_the_command_line(tree):
    """`keybinds.py --json` - die Schnittstelle, die AGS und zepos-menu
    benutzen.

    Beide sind kein Python dieses Prozesses, also ist der Aufruf die
    Schnittstelle und nicht die Funktion darunter. Eine Aenderung, die
    nur die Funktion prueft, kann das Format brechen, von dem zwei
    Oberflaechen leben.
    """
    result = subprocess.run(
        [sys.executable, str(SRC / "keybinds.py"), "--json"],
        capture_output=True, text=True, timeout=60,
        env={"HOME": str(tree.home),
             "XDG_CONFIG_HOME": str(tree.config), "PATH": ""})
    assert result.returncode == 0, result.stderr

    groups = json.loads(result.stdout)
    assert groups, "der Leser meldet keine einzige Gruppe"
    for group in groups:
        assert group["group"], "eine Gruppe ohne Namen"
        assert group["bindings"], f"die Gruppe {group['group']} ist leer"
        for binding in group["bindings"]:
            assert binding["chord"] and binding["description"]
            assert binding["run"], (
                f"{binding['chord']} laesst sich nicht ausloesen")
            assert binding["source"]
