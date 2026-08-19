# SPDX-License-Identifier: GPL-3.0-or-later
"""Everything the generated configuration names must be there when it is named.

This file exists because the same defect has now been found five separate
times on this branch, each time by hand, each time in a different file:

  * hyprland.conf sourced ~/.config/hypr/profile-windowrules.conf, which
    the generator's placeholder loop did not create - so a fresh install
    got "source= globbing error: found no match" from the very `hyprctl
    reload` the generator recommends;
  * it exec'd ~/.config/hypr/lid-startup-check.sh and bound both lid
    switches to ~/.config/hypr/lid-switch.sh, neither of which exists
    anywhere in this repository;
  * config.jsonc DEFINED custom/vpn and custom/helpers and placed neither
    on any bar, so an entire VPN subsystem was generated and could never
    be displayed;
  * the AGS network script asked systemd about watchdog.service while the
    generator writes network-watchdog.service, so the bar and the control
    centre disagreed about the same daemon on the same screen;
  * tty-text-fix-config.template had no route in the generator, fell
    through the generic branch and landed as
    ~/.config/tty-text-fix-config/config - a bash script, not executable,
    on no path, read by nothing.

Every one of them reads perfectly sensibly in the template. None of them
is visible to a text-level assertion about a template, because the
question is never "does this line look right" but "does the thing this
line names exist after a full run". So this module runs a complete
`--all`, then walks the tree it produced and RESOLVES every reference in
it: a `source =`, the command of an `exec-once`, a module name against
the bars it could appear on, a `@import`, a systemd unit, a script a bar
module clicks.

WHAT IT CANNOT SEE
    Paths that are supposed to be absent at generation time and are
    created at runtime - ~/.local/log/network-watchdog.log, the strongSwan
    secrets under ~/.config/strongswan, ~/.config/hypr/current-profile -
    are deliberately not checked. Neither are paths outside the three
    directories this project writes into (~/.config, ~/.local/bin,
    ~/.local/share): `wf-recorder -f ~/Videos/...` names a directory that
    belongs to the user, not to us. A reference that resolves is also not
    a reference that WORKS: this file proves that ~/.local/bin/start-hyprland
    is there, not that it starts anything.

    It also sees only the DEFAULT settings. A user who switches a bar
    module off in user-settings.json leaves its definition in
    config.jsonc unplaced, which Waybar ignores - inert, unlike a placed
    module with no definition, which is an error. The agreement asserted
    below is therefore the agreement a fresh install has.
"""
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

# Anchored on this file, the way every other test in this directory does
# it: pytest can be started from anywhere, and a relative Path("src")
# would measure whatever directory that happens to be.
SRC = Path(__file__).resolve().parents[2] / "src"

# Der Lauf, den dieses Modul liest, steht in tests/generated_tree.py.
#
# Er stand bis zum 11.08.2026 hier, mit BASH, SESSION_COMMANDS,
# OWNED_SUBDIRECTORIES, GeneratedTree und _stubbed_path daneben. Als
# tests/src/test_usable_desktop.py denselben Baum brauchte, war die Wahl
# zwischen einer zweiten Kopie und einer gemeinsamen Datei - und eine
# zweite Kopie eines Laufs, der `pkill -f "gjs.*ags"` ausfuehrt, ist
# genau die Kopie, an der jemand spaeter den Stub vergisst.
from tests.generated_tree import GeneratedTree, build

# There is no allowlist of external units any more.
#
# It held exactly one entry, onedrive.service, justified by an optional
# AUR package the bootstrap installer offered. OneDrive is on spec §6.1's
# "deleted without replacement" list, so the justification never survived
# the fork - and the exemption is what let the exec line, two of its
# keybinds and the window rules for its two windows stay in the
# configuration long after its Waybar module, its stylesheet and that
# stylesheet's @import had been removed. Every unit the generated
# configuration names is now a unit this project writes.

# The verbs that take a unit name. `import-environment` deliberately is
# not among them: its arguments are variable names, and a check that read
# them as units would report WAYLAND_DISPLAY as a missing service.
UNIT_VERBS = (
    "is-active", "is-enabled", "is-failed", "start", "stop", "restart",
    "reload", "enable", "disable", "mask", "unmask", "status",
    "list-unit-files",
)

# Waybar's own module names that carry no "/" - everything else it knows
# is either "custom/x", "hyprland/x" or "x#instance".
BUILTIN_BAR_MODULES = {
    "backlight", "battery", "bluetooth", "clock", "cpu", "disk",
    "idle_inhibitor", "image", "inhibitor", "keyboard-state", "memory",
    "mpd", "network", "power-profiles-daemon", "pulseaudio", "systemd-failed-units",
    "temperature", "tray", "upower", "user", "wireplumber",
}

# The keys of a bar module whose value is a shell command.
MODULE_COMMAND_KEYS = (
    "exec", "exec-if", "on-click", "on-click-right", "on-click-middle",
    "on-click-forward", "on-click-backward", "on-scroll-up", "on-scroll-down",
)


# --------------------------------------------------------------------
# the generated tree
# --------------------------------------------------------------------

# Every test here reads a tree that one `--all` produced, and building it
# spawns the generator. The marker is on the module rather than on the
# first test, because whichever test pytest reaches first is the one that
# builds the fixture - selecting a single test with -k must not turn the
# guard's refusal into the failure.
pytestmark = pytest.mark.allow_subprocess


@pytest.fixture(scope="module")
def tree(tmp_path_factory) -> GeneratedTree:
    """A complete, successful `--all` inside a temporary home.

    Der Lauf und seine Absicherung stehen in tests/generated_tree.py;
    siehe dort, warum das Stub-Verzeichnis die tragende Haelfte ist.
    """
    return build(tmp_path_factory.mktemp("reference-resolution"))


@pytest.fixture(scope="module")
def bar(tree) -> str:
    """Die veroeffentlichte Leiste - TypeScript, ohne Kommentarzeilen.

    Hier stand `json.loads(waybar/config.jsonc)`. Die Leiste ist seit
    dem 11.08.2026 ags/widget/Bar.tsx, also gibt es kein Dokument mehr zu
    laden - und die Fragen, die die Tests darunter stellen, sind
    dieselben geblieben: welche Module gibt es, welche stehen auf der
    Leiste, und was ruft jedes auf.

    Ohne Kommentarzeilen, weil der Kopf der Datei die Modulnamen in Prosa
    nennt und jede Teilzeichenkettensuche davon wahr wuerde.
    """
    source = (tree.config / "ags" / "widget" / "Bar.tsx").read_text()
    return "\n".join(line for line in source.splitlines()
                      if not line.lstrip().startswith("//"))


# --------------------------------------------------------------------
# Hyprland: source= and the commands it execs
# --------------------------------------------------------------------

def test_every_source_line_resolves(tree):
    """A `source =` naming a file that is not there is a config error.

    Not a warning: Hyprland reports "source= globbing error: found no
    match" and reads no further into that line. Reproduced against the
    real `Hyprland --verify-config` on line 263 of a freshly generated
    hyprland.conf, for
    ~/.config/hypr/profile-windowrules.conf - a file the generator's
    placeholder loop creates six siblings of and skipped.
    """
    missing = []
    checked = 0
    for path in tree.generated_files():
        if path.suffix != ".conf":
            continue
        for number, line in enumerate(tree.read(path).splitlines(), 1):
            match = re.match(r"\s*source\s*=\s*(\S+)", line)
            if not match:
                continue
            for target in tree.owned_paths(match.group(1)):
                checked += 1
                if not Path(target).exists():
                    missing.append(f"{tree.show(path)}:{number} -> {match.group(1)}")

    assert checked, "no source= line was examined - the walk found nothing"
    assert missing == [], "sourced files that the run did not create:\n" + "\n".join(missing)


def test_every_command_an_exec_line_runs_exists(tree):
    """exec-once and every bind that execs, for the paths we own.

    ~/.config/hypr/lid-startup-check.sh and ~/.config/hypr/lid-switch.sh
    were named here by three lines and produced by no template, so every
    laptop lid event was a dead exec - silent, because Hyprland does not
    report a failed exec anywhere the user looks.

    Only paths below ~/.config, ~/.local/bin and ~/.local/share are
    checked. `wf-recorder -f ~/Videos/...` names a directory that
    belongs to the user; that it is absent in a temporary home says
    nothing about this project.
    """
    execution = re.compile(r"\s*exec(?:-once|-shutdown)?\s*=\s*(.*)")
    binding = re.compile(r"\s*bind[a-z]*\s*=\s*[^,]*,[^,]*,\s*exec\s*,\s*(.*)")

    missing = []
    checked = 0
    for path in tree.generated_files():
        if path.suffix != ".conf":
            continue
        for number, line in enumerate(tree.read(path).splitlines(), 1):
            match = execution.match(line) or binding.match(line)
            if not match:
                continue
            for target in tree.owned_paths(match.group(1)):
                checked += 1
                if not Path(target).exists():
                    missing.append(f"{tree.show(path)}:{number} -> {line.strip()}")

    assert checked, "no exec line was examined - the walk found nothing"
    assert missing == [], (
        "exec lines naming something the run did not create:\n" + "\n".join(missing))


# --------------------------------------------------------------------
# Die Leiste: ein Modulname ist auch eine Referenz
# --------------------------------------------------------------------
#
# Die Fragen sind dieselben wie zur Waybar-Zeit, die Quelle ist eine
# andere: statt eines JSON-Dokuments mit einem Definitionsblock je Modul
# und drei modules-*-Reihen ist es TypeScript mit einem `case`-Zweig je
# Modul und drei Listen. Beide Haelften werden unten aus dem ERZEUGTEN
# Bar.tsx gelesen - also nach dem Einsetzen von
# {{STYLE_BAR_MODULES_LEFT}} und {{STYLE_BAR_MODULES_RIGHT}}, deren
# Inhalt seit dem 12.08.2026 fuer BEIDE Seiten von user-settings.json
# abhaengt. Vorher stand die linke Reihe ausgeschrieben in der Vorlage
# und war damit die einzige Haelfte, die dieser Test gegen etwas hielt,
# das niemand einstellen konnte.

_BUILT = re.compile(r'case\s+"([^"]+)":')
_PLACED_ARRAY = re.compile(r"MODULES_(?:LEFT|RIGHT)[^=]*=\s*(\[[^\]]*\])",
                           re.DOTALL)


def _defined_modules(bar: str) -> set[str]:
    """Die Modulnamen, fuer die build() einen Zweig hat.

    `case "custom/date":` und nicht jedes Vorkommen des Namens: der
    Aufruf in MODULES_LEFT nennt ihn ebenfalls, und eine Suche, die
    beides zaehlt, koennte den Unterschied zwischen "gebaut" und
    "platziert" gar nicht mehr feststellen - also genau das nicht, wofuer
    dieser Test da ist.
    """
    return {name for name in _BUILT.findall(bar) if "/" in name or name in
            BUILTIN_BAR_MODULES or name.split("#")[0] in BUILTIN_BAR_MODULES}


def _placed_modules(bar: str) -> set[str]:
    """Die Namen aus MODULES_LEFT und MODULES_RIGHT, plus die Mitte.

    Die Mitte ist keine Liste: BarContent haengt hyprland/workspaces fest
    in den mittleren Kasten, weil dort genau ein Modul steht und eine
    Liste mit einem Eintrag eine Liste waere, die niemand je aendert.
    Bis zum 12.08.2026 hing dort der Fenstertitel; seit "in der mitte
    die arbeitsbereiche" sind es die Arbeitsbereiche, und der Titel
    steht in MODULES_LEFT.
    """
    placed = {"hyprland/workspaces"}
    for array in _PLACED_ARRAY.findall(bar):
        placed.update(re.findall(r'"([^"]+)"', array))
    return placed


def _available_modules() -> set[str]:
    """Was die Leiste tragen KANN - BAR_MODULES_AVAILABLE aus der SSOT.

    Gelesen und nicht importiert: src/style_definition.py fragt beim
    Import `hyprctl` nach den Bildschirmen, und diese Datei soll auch
    dann etwas sagen, wenn kein Compositor laeuft. Die Liste ist ein
    Python-Literal und steht an genau einer Stelle - eben deshalb.
    """
    text = (SRC / "style_definition.py").read_text(encoding="utf-8")
    match = re.search(r"^BAR_MODULES_AVAILABLE = \[(.*?)\]$", text,
                      re.DOTALL | re.MULTILINE)
    assert match, ("src/style_definition.py hat kein BAR_MODULES_AVAILABLE "
                   "mehr - dann sagt nichts mehr, welche Namen ueberhaupt "
                   "aufgestellt werden duerfen")

    names: set[str] = set()
    for variable, literal in re.findall(r"\*(\w+)|\"([^\"]+)\"",
                                        match.group(1)):
        if literal:
            names.add(literal)
            continue
        # Die Listen wachsen teils in mehreren Zeilen (`_modules_right +=
        # [...]`). Wer nur die erste liest, haelt die uebrigen Module
        # fuer unmoeglich - und der Test waere gruen, weil er zu wenig
        # gefunden hat.
        pieces = re.findall(rf"^{variable} (?:=|\+=) \[(.*?)\]", text,
                            re.DOTALL | re.MULTILINE)
        assert pieces, f"{variable} steht in keiner Liste"
        for piece in pieces:
            names.update(re.findall(r'"([^"]+)"', piece))
    return names


def test_every_module_the_bar_defines_is_placed_on_it(bar):
    """Ein Modulname ist eine Referenz, und der Zweig, auf den er zeigt,
    ist das Referenzierte. Beide Richtungen gehen schief, verschieden:

    Gebaut und nicht platziert ist lautlos. build() wird je Name aus den
    Listen einmal aufgerufen, also blieb ein Zweig ohne Platz einfach
    stehen - custom/vpn und custom/helpers waren vollstaendig
    eingerichtet und vollstaendig erzeugt (vpn-status.py, vpn-control.sh,
    helpers-bar.py, drei Stylesheets) und konnten nicht erscheinen.

    Platziert und nicht gebaut ist die laute Richtung, und sie ist in der
    AGS-Fassung billiger geworden: build() gibt null zurueck und schreibt
    "Unbekanntes Leistenmodul" auf die Konsole, wo Waybar den Start der
    ganzen Bar verweigert hat. Lautlos ist sie trotzdem nicht - und ein
    leerer Platz auf der Leiste ist ein Fehler, egal wie billig.

    "ERREICHBAR" HEISST SEIT DEM 12.08.2026 EINES VON DREIEN
        Auf der ausgelieferten Leiste, in der festen Mitte, ODER in
        BAR_MODULES_AVAILABLE - der Liste dessen, was der Nutzer
        zuschalten kann.

        Bis dahin stellte die Vorgabe jedes Modul auf, das es gibt, also
        fielen "ausgeliefert" und "moeglich" zusammen. Seit die Vorgabe
        eine AUSWAHL ist, liesse eine Zusicherung, die beides
        gleichsetzt, den Umbau nur mit zehn GELOESCHTEN Modulen bestehen
        - sie erzwaenge also genau den Verlust, den sie verhindern soll.

        Schwaecher wird sie dabei nicht, sondern staerker: die dritte
        Menge wird ebenfalls gegen die Zweige gehalten. Ein Name im
        Zuschaltbaren OHNE Zweig waere ein Eintrag im
        Einstellungsfenster, hinter dem nichts steht - und den haette
        vorher niemand gefunden.
    """
    defined = _defined_modules(bar)
    placed = _placed_modules(bar)
    available = _available_modules()

    assert defined, "no module definitions found - the bar was not read"
    assert len(defined) >= 15, (
        f"nur {len(defined)} Module gefunden - die Leiste traegt zwanzig, "
        "also liest dieser Test die falsche Datei")
    assert sorted(placed - defined) == [], (
        "modules placed on a bar with no definition: " + ", ".join(sorted(placed - defined)))
    assert sorted(available - defined) == [], (
        "zuschaltbar und ohne Zweig - ein Angebot, hinter dem nichts "
        "steht: " + ", ".join(sorted(available - defined)))
    assert sorted(defined - placed - available) == [], (
        "modules defined and neither placed nor offered, so they can "
        "never appear: " + ", ".join(sorted(defined - placed - available)))


def test_every_script_a_bar_module_runs_exists(tree, bar):
    """Die andere Haelfte eines Moduls: was sein exec und seine Klicks
    aufrufen.

    Gelesen wird jede Zeichenkette der erzeugten Datei, denn genau das
    sind die Befehle jetzt - `${SCRIPTS}/date.sh` ist nach dem Erzeugen
    ein Template-Literal, dessen einzige Variable SCRIPTS ist.
    """
    missing = []
    checked = 0
    scripts = str(tree.config / "ags" / "scripts")
    for literal in re.findall(r'[`"\']([^`"\'\n]*)[`"\']', bar):
        command = literal.replace("${SCRIPTS}", scripts)
        for target in tree.owned_paths(command):
            checked += 1
            if not Path(target).exists():
                missing.append(f"{literal} -> {target}")

    assert checked, "no module command was examined - the bar was not read"
    assert missing == [], (
        "bar modules calling something the run did not create:\n" + "\n".join(missing))


def test_the_bar_asks_for_persistent_workspaces_exactly_once(tree):
    """Zwei Schreibweisen einer Einstellung, und nur eine wird befolgt.

    waybar-config.template schrieb "persistent_workspaces" mit
    Unterstrich, waehrend der jq-Merge des Generators
    "persistent-workspaces" mit Bindestrich einsetzte, abgeleitet aus den
    Schirmen, die wirklich da sind. Beide ueberlebten in config.jsonc:
    eine fest auf zehn Bereiche ueberall, eine gemessen. Welche Waybar
    las, war der anderen egal.

    Den Merge gibt es nicht mehr - die Leiste liest workspaces.json
    selbst -, also ist die Frage jetzt: gibt es GENAU EINE Datei mit
    genau einem Schluessel dafuer, und liest die Leiste genau den.
    """
    written = tree.config / "ags" / "workspaces.json"
    assert written.is_file(), "die Arbeitsbereichsdatei wurde nicht erzeugt"

    document = json.loads(written.read_text())
    spellings = sorted(key for key in document if "persistent" in key)
    assert spellings == ["persistent-workspaces"], (
        f"workspaces.json traegt diese Schluessel: {spellings} - mehr als "
        "einer heisst, dass einer davon lautlos ignoriert wird")

    source = (tree.config / "ags" / "widget" / "Bar.tsx").read_text()
    assert '"persistent-workspaces"' in source, (
        "die Leiste liest den Schluessel nicht, den die Datei traegt")
    assert "persistent_workspaces" not in source, (
        "die Leiste liest wieder die Schreibweise mit Unterstrich")


# --------------------------------------------------------------------
# stylesheets and systemd units
# --------------------------------------------------------------------

# HIER STAND test_every_stylesheet_import_resolves, UND ES IST GELOESCHT.
#
# Der Test las jede erzeugte .css und .scss, suchte @import-Zeilen und
# pruefte, ob die genannte Datei daneben liegt. Er hatte genau einen
# Gegenstand: waybar/style.css, das aus nichts als fuenfzehn @import
# bestand und dessen Kette bei jedem neuen Modul verlaengert werden
# musste.
#
# GEMESSEN am 11.08.2026 nach dem Umbau: `grep -rn '@import\|@use'` ueber
# src/templates und src/styles findet drei Treffer, und alle drei stehen
# in Kommentaren, die erklaeren, dass es die Kette nicht mehr gibt. Der
# Stil der Leiste ist EINE Datei, ags/bar.css, die app.ts ueber
# app.apply_css() laedt.
#
# Ein Test ohne Gegenstand ist kein Netz, sondern eine Zeile, die bei der
# naechsten Aenderung als "der prueft das ja" gelesen wird. Seine
# Aufgabe - "die Stildatei, die jemand laedt, muss auch erzeugt werden" -
# hat test_every_generated_file_is_reached_by_something uebernommen:
# ags/bar.css steht in READ_BY_CONVENTION, mit dem Namen dessen, der sie
# liest.


def test_every_systemd_unit_the_configuration_names_exists(tree):
    """A unit name is a reference with no filesystem path in it, which is
    why this one went unnoticed longest.

    The AGS network script asked `systemctl --user is-active
    watchdog.service`; the generator writes network-watchdog.service. The
    Waybar module asked correctly. So the bar showed the watchdog's
    heartbeat as fine while the AGS control centre read "Watchdog:
    Inaktiv" - same daemon, same screen, same moment - and neither of
    them was wrong about anything it could see.
    """
    verbs = "|".join(UNIT_VERBS)
    pattern = re.compile(
        r"systemctl\s+--user\s+(?:-\S+\s+)*(?:" + verbs + r")\s+([\w@.\\-]+)")

    unit_directory = tree.config / "systemd" / "user"
    generated = {path.name for path in unit_directory.iterdir()} if unit_directory.is_dir() else set()
    assert generated, "the run generated no systemd user unit at all"

    dangling = {}
    checked = 0
    for path in tree.generated_files():
        for match in pattern.finditer(tree.read(path)):
            unit = match.group(1)
            # `systemctl --user start foo` and `... foo.service` name the
            # same unit; systemd appends the default type.
            if "." not in unit:
                unit += ".service"
            checked += 1
            if unit in generated:
                continue
            dangling.setdefault(unit, set()).add(tree.show(path))

    assert checked, "no systemctl call was examined - the walk found nothing"
    assert dangling == {}, (
        "units nothing creates and nothing installs:\n"
        + "\n".join(f"  {unit} <- {sorted(where)}" for unit, where in sorted(dangling.items())))


# --------------------------------------------------------------------
# the generator's own routing
# --------------------------------------------------------------------

def _case_labels() -> set[str]:
    """The config names generate_config.sh routes by hand."""
    script = (SRC / "generate_config.sh").read_text()
    start = script.index('case "$CONFIG_NAME" in')
    end = script.index("\nesac", start)
    labels = set()
    for line in script[start:end].splitlines():
        match = re.match(r"\s{4}([\w|*./-]+)\)\s*$", line)
        if not match:
            continue
        for part in match.group(1).split("|"):
            labels.add(part.strip())
    # The two guards at the end of the case are not config names.
    return labels - {"*", "*/*", ".*"}


# Every directory generate_config.sh's ZEPOS_TEMPLATE_SUBDIR can name.
# Derived from the generator rather than listed by hand: a new subdirectory
# that this test does not know about makes every route into it look like a
# route to nothing, which is a failure that says the opposite of the truth.
TEMPLATE_SUBDIRECTORIES = ("templates", "styles", "system")


def _template_names() -> set[str]:
    names: set[str] = set()
    for subdir in TEMPLATE_SUBDIRECTORIES:
        names |= {path.stem for path in (SRC / subdir).glob("*.template")}
    return names


def test_the_subdirectory_list_matches_the_generator():
    """Held against the generator, not trusted.

    _template_names() decides what "the template exists" means for the
    test below. If the generator learns a fourth subdirectory and this
    tuple does not, every route into it is reported as broken - and the
    natural reaction to a test that cries wolf is to loosen it.
    """
    generator = (SRC / "generate_config.sh").read_text(encoding="utf-8")
    named = set(re.findall(r'ZEPOS_TEMPLATE_SUBDIR="([a-z]+)"', generator))
    # The default assignment at the top names the primary directory.
    named.discard("")
    unknown = named - set(TEMPLATE_SUBDIRECTORIES)
    assert unknown == set(), (
        f"generate_config.sh names template subdirectories this test does "
        f"not know: {sorted(unknown)}")


def test_every_generator_route_names_a_template_that_exists():
    """A case entry for a template that was deleted is a route to
    nothing: `generate_config.sh -ags-theme` reaches its branch, sets a
    target, and dies at "Template not found" - a name the generator
    advertises by carrying it and cannot serve.

    The entries that answer a REMOVED name with a migration message and
    exit 1 are excluded: those are reachable on purpose, and telling a
    user what replaced -hyprland-gaming-config is the whole point of
    them.
    """
    script = (SRC / "generate_config.sh").read_text()
    templates = _template_names()

    unreachable = sorted(
        label for label in _case_labels()
        if label not in templates
        and not re.search(r"^\s{4}[\w|-]*\b" + re.escape(label) + r"\b[\w|-]*\)\s*$\n\s+echo -e \"\$\{RED\}DEPRECATED",
                          script, re.M)
    )

    assert unreachable == [], (
        "generator routes whose template does not exist: " + ", ".join(unreachable))


def test_no_template_falls_through_to_the_generic_branch(tree):
    """The fallback writes ~/.config/<name>/config, and for a template
    whose name ends in -config that reads as a plausible directory.

    tty-text-fix-config.template landed as
    ~/.config/tty-text-fix-config/config: a bash script, without the
    executable bit its `MAKE_EXECUTABLE=true` would have set, in a
    directory no program reads, under a name that does not say it is a
    script. Generated on every run, reachable by nothing.

    Read off the tree rather than off the case statement, because that is
    where the consequence is: a legitimate route also produces a file
    called "config" - ~/.config/mako/config, ~/.config/zepos-menu/config - and
    what distinguishes the fallback is that the directory is named after
    the TEMPLATE.
    """
    templates = _template_names()
    stranded = sorted(
        entry.name for entry in tree.config.iterdir()
        if entry.is_dir() and entry.name in templates and (entry / "config").is_file()
    )

    assert stranded == [], (
        "templates that fell through to ~/.config/<name>/config: " + ", ".join(stranded))


# --------------------------------------------------------------------
# a generated artifact that reads a generated directory
# --------------------------------------------------------------------

def test_the_helper_menu_lists_the_helpers_the_run_generated(tree):
    """Executed, because the defect is a directory name and nothing else.

    helpers-bar.py scanned ~/.local/bin/helpers while the generator
    writes its helper scripts to $ZEPOS_USER_ROOT/helpers. The module
    therefore rendered " 0" and a tooltip reading "Keine Helper-Scripts
    gefunden" on a machine that had just generated six of them - and the
    template was word for word correct about a directory that is simply
    not the one in use.

    The child gets PATH and HOME and nothing else, so a script that
    reached for the developer's own home would find a different answer
    here and fail rather than quietly agree.
    """
    module = tree.config / "ags" / "scripts" / "helpers-bar.py"
    helpers = sorted(path.name for path in (tree.user_root / "helpers").iterdir()
                     if path.is_file() and os.access(path, os.X_OK))
    assert helpers, "the run generated no helper script at all"

    result = subprocess.run(
        ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin", f"HOME={tree.home}",
         "python3", str(module)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    payload = json.loads(result.stdout)
    assert payload["text"].strip().endswith(str(len(helpers))), (
        f"the menu reports {payload['text']!r} for {len(helpers)} generated "
        f"helper scripts: {helpers}")
    for name in helpers:
        assert name in payload["tooltip"], (
            f"{name} is generated but the helper menu does not list it")


# --------------------------------------------------------------------
# die Tastenuebersichten - die Frage ist hierher gewandert
# --------------------------------------------------------------------
#
# HIER STANDEN DREI ZUSICHERUNGEN UND ZWEI UEBERSETZUNGSTABELLEN, und
# sie sind am 12.08.2026 ersatzlos entfallen, weil das, was sie geprueft
# haben, es nicht mehr gibt.
#
# ZepOS lieferte zwei Listen von Tastenkuerzeln aus - den Tooltip der
# Leiste (hypr-shortcuts.py) und die Ueberlagerung (Shortcuts.tsx) -,
# beide von Hand gepflegt neben einer von Hand gepflegten Konfiguration.
# Diese Zusicherungen sind der Versuch gewesen, die drei Fassungen
# nachtraeglich zur Deckung zu bringen: eine Tabelle KEY_SPELLINGS, die
# "SUPER + ←/→/↑/↓" in vier Hyprland-Tasten uebersetzte, eine Tabelle
# NOT_A_HYPRLAND_BIND, die entschuldigte, was gar keine Bindung war, und
# ein Vorwaertslauf, der jede angebotene Taste in den erzeugten Dateien
# suchte.
#
# Sie haben dabei viel gefunden - SUPER+ALT+SHIFT+Z fuer einen
# Dispatcher, der nirgends hing, SUPER+TAB fuer ein Plugin, das ZepOS
# nicht ausliefert, zwei zu kurz geschriebene XF86-Keysyms. Was sie NICHT
# finden konnten, ist der Fall, an dem der Nutzer haengengeblieben ist:
# eine Taste, die gebunden ist und in keiner der beiden Listen steht. 19
# davon gab es, gemessen am 12.08.2026.
#
# Beide Listen sind jetzt weg. Die Beschreibungen stehen als
# `# @Gruppe: Text` ueber den bind-Zeilen selbst, src/keybinds.py liest
# sie, und beide Oberflaechen zeigen, was von dort kommt. Damit ist die
# Frage "wird jede angebotene Taste auch gebunden" keine Pruefung mehr,
# sondern eine Eigenschaft: angeboten wird, was gebunden ist.
#
# Was an ihre Stelle getreten ist, steht in tests/src/test_keybinds.py -
# insbesondere test_no_surface_that_shows_keys_contains_a_key, das
# misst, dass in beiden Dateien keine einzige Tastenkombination mehr
# steht. Eine Uebersetzungstabelle zwischen zwei Schreibweisen braucht
# es nicht mehr, weil es die zweite Schreibweise nicht mehr gibt.

# --------------------------------------------------------------------
# the other direction
# --------------------------------------------------------------------
#
# Everything above resolves references FORWARD: does the thing this line
# names exist? That misses the opposite failure entirely - a file this
# project generates that nothing ever reaches.
#
# It is not a hypothetical. Five separate instances were found on this
# branch: workspaces-generated.conf written where Hyprland never looked,
# weather.sh with no bar module, the three src/bin commands no guard
# read, the whole VPN bar subsystem defined but placed on no bar, and
# clock.sh/time.sh, which survived precisely because the forward test
# cannot see them. Measured: restoring clock-config.template left the
# suite at 850 passed with only the two count assertions failing.
#
# The producer does not count as a reference. generate_config.sh names
# every file it writes - CONFIG_FILE="clock.sh" - so including it makes
# "is this named anywhere" true by construction, which is exactly the
# vacuous shape this file exists to avoid.

# Read by the program it belongs to, which finds it by its own
# convention rather than because anything here names it. Each entry says
# which program, because "something must read this" is the claim that
# stops being true silently.
READ_BY_CONVENTION = {
    "zepos-menu/style.css": "zepos-menu",
    # "zepos-logout/style.css" and "zepos-logout/layout.json" stood here
    # until 19.08.2026 (Aufgabe 26): zepos-logout itself is deleted
    # (Regel 14), and generate_config.sh no longer has a -logout-config
    # or -logout-style route to produce either file - see
    # test_the_convention_list_does_not_outlive_its_files, which would
    # fail on a stale entry naming a file nothing generates any more.
    # The replacement, src/templates/ags-logout.template, writes no
    # generated file of its own; it is bundled straight into ags/app.ts
    # like every other AGS window.
    "ags/bar.css": "app.ts, das sie ueber app.apply_css() nachlaedt",
    # "starship.toml": "starship, via STARSHIP_CONFIG's default" stand
    # hier bis zum 12.08.2026, und der Eintrag war genau die Art
    # Freibrief, vor der der Absatz ueber dieser Liste warnt: er BEHAUPTETE
    # einen Leser. Gemessen: starship steht in keiner Paketliste dieses
    # Projekts, und kein `starship init zsh` steht in
    # zshrc-config.template. Es gab die Datei, es gab die Vorlage mit
    # ihren vier eigenen Farbliteralen, und es gab auf keiner
    # Installation ein Programm, das sie oeffnet.
    #
    # Beides ist weg. Was ZepOS an Prompt hat, ist ~/.p10k.zsh - und das
    # steht nicht hier, sondern wird von ~/.zshrc namentlich gesourct,
    # also findet der Rueckwaertslauf es von selbst.
    "ncspot/config.toml": "ncspot",
    "zepos-lock/style.css": "zepos-lock",
    "hypr/grid-wallpaper-style.css": "the grid overlay's own GTK layer",
    "wireplumber/wireplumber.conf.d/99-zepos-audio.conf": "wireplumber, which reads every .conf in that directory",
    "sublime-text/Packages/User/Terminal Green.sublime-color-scheme": "sublime-text, by name from its preferences",
    "ags/app.ts": "ags, which runs the entry point of the directory it is given",
    # GTK 4 selbst, beim Start JEDER Anwendung, aus dem Verzeichnis, das
    # die Bibliothek fest kennt. Der Eintrag steht hier und nicht als
    # Erwaehnung in einer anderen Datei, obwohl
    # start-hyprland-config.template den Pfad im Kommentar nennt: eine
    # Zeichenkette in einem Kommentar ist kein Leser. Was diese Datei
    # liest, sind die neun Anwendungen aus packaging/zepos-apps - ueber
    # libadwaita, das die @define-color darin als Ueberschreibung seiner
    # benannten Farben nimmt.
    "gtk-4.0/gtk.css": "GTK 4 und libadwaita, aus ihrem eigenen Pfad",
    "gtk-4.0/settings.ini": (
        "GTK 4 selbst, aus ihrem eigenen Pfad - die GROESSE fuer fremde "
        "Fenster, gemessen am 12.08.2026 gegen gtk4-broadwayd"),
}

# Found by listing a directory, so no file in it is ever named. The
# helper menu scans this one; test_the_helper_menu_lists_the_helpers_the
# _run_generated above holds that it really does.
SCANNED_DIRECTORIES = ("zepos/helpers",)

# Outside .config, and reached by their own mechanism.
READ_BY_CONVENTION_OUTSIDE_CONFIG = {
    ".local/share/applications/floating-center.desktop": "the desktop environment's application database",
    ".local/share/dbus-1/services/org.freedesktop.Notifications.service": "dbus, which activates the name this file claims",
    # gpg-agent liest ausschliesslich $GNUPGHOME/gpg-agent.conf, und
    # GNUPGHOME ist voreingestellt ~/.gnupg. Der Eintrag steht hier,
    # obwohl der Rueckwaertslauf die Datei auch ohne ihn durchgelassen
    # haette: ihr Name kommt in den Kommentaren von style_definition.py
    # und hyprland-universal-config.template vor, und der Lauf sucht
    # bloss nach einer Erwaehnung. Eine Zusicherung, die von einem
    # Kommentar wahr wird, ist keine - also wird das lesende Programm
    # hier benannt, und test_the_convention_list_does_not_outlive_its
    # _files haelt umgekehrt fest, dass die Datei ueberhaupt entsteht.
    ".gnupg/gpg-agent.conf": "gpg-agent, das nur an diesem einen Pfad nachsieht",
}


def _reference_corpus(tree) -> str:
    """Everything that could name a generated file, except its producer."""
    parts = []
    for path in tree.generated_files():
        parts.append(tree.read(path))
    for path in sorted(SRC.rglob("*")):
        if path.name == "generate_config.sh":
            continue
        if path.is_file() and path.suffix in {
                ".sh", ".py", ".template", ".conf", ".json", ".md"}:
            parts.append(path.read_text(errors="replace"))
    return "\n".join(parts)


def test_every_generated_file_is_reached_by_something(tree):
    """The backward walk.

    A generated file that nothing names, nothing scans and no program
    reads by convention is dead weight that looks like a feature - and
    the forward tests above all pass over it without a word.
    """
    corpus = _reference_corpus(tree)
    orphans = []

    for path in tree.generated_files():
        relative = path.relative_to(tree.home).as_posix()
        inside_config = relative.removeprefix(".config/")

        if inside_config in READ_BY_CONVENTION:
            continue
        if relative in READ_BY_CONVENTION_OUTSIDE_CONFIG:
            continue
        if any(inside_config.startswith(scanned + "/")
               for scanned in SCANNED_DIRECTORIES):
            continue

        # A file cannot name itself into existence.
        others = corpus.replace(tree.read(path), "")
        if path.name in others:
            continue
        # TypeScript and SCSS imports drop the extension
        # ("./widget/Calendar"), so those - and only those - are also
        # accepted by their stem. Allowing a bare stem for every file
        # makes the check useless, and that is measured rather than
        # assumed: with the stem accepted everywhere, restoring
        # clock-config.template passed, because the word "clock" occurs
        # in a stylesheet.
        if path.suffix in {".ts", ".tsx", ".scss"} and path.stem in others:
            continue

        orphans.append(relative)

    assert orphans == [], (
        "generated but reached by nothing - wire them up, delete them, or "
        "record which program reads them:\n  " + "\n  ".join(orphans))


def test_the_convention_list_does_not_outlive_its_files(tree):
    """A self-expiring exception, like KNOWN_PLACE_BOUND next door.

    An entry naming a file the run no longer generates is a claim about
    nothing, and it would silently excuse a future file that happens to
    take the same path.
    """
    generated = {path.relative_to(tree.home).as_posix()
                 for path in tree.generated_files()}
    stale = [name for name in READ_BY_CONVENTION
             if f".config/{name}" not in generated]
    stale += [name for name in READ_BY_CONVENTION_OUTSIDE_CONFIG
              if name not in generated]
    assert stale == [], (
        "these are excused as read-by-convention but are no longer "
        f"generated - delete the entries: {stale}")


def test_the_gnupg_directory_is_created_private(tree):
    """0700, und das ist keine Kosmetik.

    GnuPG prueft die Rechte seines Heimatverzeichnisses bei jedem Start
    und meldet "unsafe permissions on homedir" - eine Warnung, die
    weiterlaeuft, sodass niemand sie bemerkt, und die ZepOS hier selbst
    verursachen wuerde: `mkdir -p` legt mit der umask des Nutzers an, und
    die ueblichen 0755 machen ~/.gnupg fuer jeden lesbar. Darin liegen
    private Schluessel.

    Gemessen am erzeugten Baum statt an der Zeile in generate_config.sh,
    weil eine Zeile, die CONFIG_DIR_MODE setzt, und ein Verzeichnis, das
    danach 0700 hat, zwei verschiedene Aussagen sind.
    """
    gnupg = tree.home / ".gnupg"
    assert gnupg.is_dir(), (
        "~/.gnupg wurde nicht angelegt - erzeugt der Lauf gpg-agent.conf?")
    assert gnupg.stat().st_mode & 0o777 == 0o700, (
        "~/.gnupg ist %o statt 0700; gpg meldet 'unsafe permissions'"
        % (gnupg.stat().st_mode & 0o777))
