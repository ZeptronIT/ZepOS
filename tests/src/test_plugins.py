# SPDX-License-Identifier: GPL-3.0-or-later
"""The desktop has to start when the plugins are not there.

That is the whole reason this file exists, and it is not a preference: a
Hyprland plugin is an ABI-coupled shared object, so the ordinary course
of a distribution - Hyprland moves a minor version, the plugin packages
have not been rebuilt yet - produces a machine whose plugins cannot load.
If that costs the session, the user meets it on a black screen from a
TTY. It has to cost the feature instead.

WHAT DEPENDS ON A PLUGIN, precisely
    Three things, and only the first is obvious:

      * `plugin = <path>` - the load line itself.
      * `plugin { hyprbars { ... } }` - Hyprland refuses a configuration
        option that no loaded plugin registered.
      * `bind = SUPER, SPACE, hyprlaunch:toggle,` - a dispatcher that
        belongs to a plugin is not a dispatcher until the plugin is
        loaded.

    All three therefore live in ~/.config/hypr/plugins.conf, and
    src/plugins.py writes a block into it only when the object that block
    depends on is on the machine. With no objects at all the file holds
    nothing but comments, which is a Hyprland configuration that parses -
    the session starts and the comments say what is missing and why.

WHY THE ANSWER IS NOT "hyprpm"
    hyprpm builds plugins per user, from whatever is on GitHub at that
    moment. A distribution that pins its versions cannot have its desktop
    depend on the state of five foreign branches, and the user cannot see
    that it does until the build fails. Spec §7.2 rejects it; this file
    holds the replacement to its promises.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.adopted_plugin_source import plugin_source

# Anchored on this file, the way every other test in this directory does
# it. src/ has no __init__.py and its modules import each other flatly.
SRC = Path(__file__).resolve().parents[2] / "src"

BASH = "/bin/bash"

# The same list tests/src/test_generate.py keeps, and for the same
# reason: HOME cannot redirect a command that talks to the running
# compositor over its own socket.
SESSION_COMMANDS = (
    "ags", "pkill", "pgrep", "systemctl", "dbus-send", "setsid", "kitty",
    "nohup", "hyprctl",
)

# The five ABI-coupled plugins spec §7.1 names. Written out here rather
# than imported from the module under test: a roster that checks itself
# against itself agrees with every typo.
SPEC_PLUGINS = ("hyprbars", "borders-plus-plus", "hyprlaunch", "hyprclipx",
                "hyprzones")

TEMPLATE = SRC / "templates" / "hyprland-plugins-config.template"


@pytest.fixture
def plugins(monkeypatch):
    monkeypatch.syspath_prepend(str(SRC))
    import plugins

    return plugins


@pytest.fixture
def plugin_root(tmp_path, monkeypatch, plugins):
    """A plugin directory this test owns, in place of /usr/lib/hyprland.

    Without the override every assertion below would depend on which
    packages the developer happens to have installed - and the two cases
    that matter, "every object is there" and "none of them are", could
    not both be measured on one machine.
    """
    root = tmp_path / "hyprland-plugins"
    root.mkdir()
    monkeypatch.setenv(plugins.PLUGIN_ROOT_ENV, str(root))

    # Die zweite Haelfte von hyprclipx, ebenfalls umgelenkt. Seit dem
    # 12.08.2026 sieht src/plugins.py ausser dem Objekt auch nach dem
    # Sammler, und /usr/lib/hyprclipx/collector.py auf der Maschine des
    # Entwicklers waere genau die Abhaengigkeit, die dieser Fixture
    # sonst ueberall vermeidet: die Antwort haengt dann daran, welche
    # Pakete zufaellig installiert sind.
    monkeypatch.setenv(plugins.COLLECTOR_ENV, str(tmp_path / "collector.py"))
    return root


def install(root: Path, *names: str) -> None:
    """Put a plugin object where a package would have put it.

    Fuer hyprclipx sind das ZWEI Dateien, weil zepos-hyprclipx zwei
    ablegt: das Objekt und den Sammler. Diese Funktion bildet ab, was
    ein PAKET tut - schriebe sie nur die .so, hiesse "installiert" hier
    etwas anderes als draussen, und die Pruefungen darunter bewiesen
    einen Zustand, den keine Installation je hat.
    """
    for name in names:
        (root / f"{name}.so").write_bytes(b"\x7fELF")
        if name == "hyprclipx":
            collector = Path(os.environ["ZEPOS_HYPRCLIPX_COLLECTOR"])
            collector.write_text("#!/usr/bin/env python3\n", encoding="utf-8")


# --------------------------------------------------------------------
# the roster
# --------------------------------------------------------------------

def test_the_roster_is_the_five_plugins_the_spec_names(plugins):
    """§7.1 lists five. A sixth added here without a package to provide
    it writes a load line for an object that will never appear; a fifth
    dropped silently takes its feature with it."""
    assert sorted(plugins.PLUGINS) == sorted(SPEC_PLUGINS)


def test_an_object_lives_where_the_package_will_put_it(plugins):
    """Spec §7.2: /usr/lib/hyprland/plugins/<name>.so.

    validate_output, zepos-doctor and the packages TP3 writes all have to
    name the same directory, so it is defined once and read from here.
    """
    assert plugins.PLUGIN_ROOT == Path("/usr/lib/hyprland/plugins")
    assert plugins.object_path("hyprzones").name == "hyprzones.so"


# --------------------------------------------------------------------
# what the filter does with a block
# --------------------------------------------------------------------

def test_a_present_object_is_loaded_by_its_absolute_path(plugins, plugin_root):
    """An absolute path, because that is the only shape anything can
    check. A bare name is what hyprpm took, and it cannot be resolved
    without knowing which revision hyprpm built against."""
    install(plugin_root, "hyprzones")

    rendered = plugins.render(
        "# zepos-plugin hyprzones\n"
        "bind = SUPER, Z, hyprzones:show,\n"
        "# zepos-plugin-end\n")

    assert f"plugin = {plugin_root}/hyprzones.so" in rendered
    assert "bind = SUPER, Z, hyprzones:show," in rendered


def test_an_absent_object_leaves_nothing_but_comments(plugins, plugin_root):
    """The failsafe, at its smallest.

    Not only the load line: the bind goes too. A dispatcher that belongs
    to a plugin nobody loaded is a config error in the file whose failure
    costs the session.
    """
    rendered = plugins.render(
        "# zepos-plugin hyprzones\n"
        "bind = SUPER, Z, hyprzones:show,\n"
        "# zepos-plugin-end\n")

    assert "plugin =" not in rendered
    assert "hyprzones:show" not in rendered
    for line in rendered.splitlines():
        assert not line.strip() or line.lstrip().startswith("#"), line


def test_the_comment_says_what_is_missing_and_what_to_do(plugins, plugin_root):
    """A feature that vanishes without a word is the failure zepos-doctor
    exists to break. The file that dropped the block says so itself."""
    rendered = plugins.render(
        "# zepos-plugin hyprzones\nbind = SUPER, Z, hyprzones:show,\n"
        "# zepos-plugin-end\n")

    assert str(plugin_root / "hyprzones.so") in rendered
    assert "zepos-hyprzones" in rendered, "the package to install is not named"
    assert "zepos-generate" in rendered, "the command to re-run is not named"


def test_a_replacement_block_is_written_only_when_the_plugin_is_absent(
        plugins, plugin_root):
    """SUPER+SPACE is the application launcher. With hyprlaunch gone it
    would be a dead key, so the absent case binds it to zepos-menu -
    which is a required package, carries a generated configuration, and
    is deliberately not the GTK4 plugin whose absence this block is
    about."""
    text = ("# zepos-plugin hyprlaunch\n"
            "bind = SUPER, SPACE, hyprlaunch:toggle,\n"
            "# zepos-plugin-end\n"
            "# zepos-plugin-missing hyprlaunch\n"
            "bind = SUPER, SPACE, exec, zepos-menu --show drun\n"
            "# zepos-plugin-end\n")

    absent = plugins.render(text)
    assert "zepos-menu --show drun" in absent
    assert "hyprlaunch:toggle" not in absent

    install(plugin_root, "hyprlaunch")
    present = plugins.render(text)
    assert "hyprlaunch:toggle" in present
    assert "zepos-menu --show drun" not in present


def test_a_line_outside_every_block_is_kept(plugins, plugin_root):
    assert "# header" in plugins.render("# header\n")


# --------------------------------------------------------------------
# die zweite Haelfte, die es nur bei hyprclipx gibt
# --------------------------------------------------------------------

def test_the_clipboard_needs_its_collector_and_not_only_its_object(
        plugins, plugin_root):
    """Das Objekt allein reicht bei hyprclipx nicht, und der Grund ist
    ein Ausfall, der wie ein Erfolg aussieht.

    Das Fenster fragt einen Unix-Socket nach dem Verlauf; wer ihn
    bedient, ist ein eigenes Programm. Ist nur die .so da, laedt das
    Plugin, steht der Dispatcher und oeffnet SUPER+SHIFT+V ein Fenster.
    Ein LEERES - richtig gestylt, richtig gross, ohne Fehlermeldung,
    ohne Zeile im Protokoll.

    GEMESSEN am 12.08.2026: bis zu diesem Tag lieferte kein Paket den
    Sammler aus (er lag unter ~/.local/bin, wo pacman nichts ablegen
    darf), also war das der Zustand JEDER Installation.
    """
    (plugin_root / "hyprclipx.so").write_bytes(b"\x7fELF")
    collector = Path(os.environ[plugins.COLLECTOR_ENV])
    assert not collector.exists()

    reasons = plugins.unavailable()
    assert "hyprclipx" in reasons, (
        "das Plugin gilt als ladbar, obwohl sein Sammler fehlt - dann "
        "oeffnet SUPER+SHIFT+V ein leeres Fenster statt in den "
        "Rueckfall zu gehen")
    assert str(collector) in reasons["hyprclipx"], (
        "der Grund nennt nicht die Datei, die fehlt")

    # Und die Gegenprobe: mit dem Sammler ist es ladbar. Ohne sie
    # koennte diese Pruefung auch von einem hyprclipx erfuellt werden,
    # das gar nicht mehr auf die Liste kommt.
    collector.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    assert "hyprclipx" not in plugins.unavailable()


def test_the_missing_collector_reaches_the_fallback_for_that_key(
        plugins, plugin_root):
    """Der Rueckfall greift wirklich - das ist der Punkt der ganzen
    Aenderung.

    Vorher orientierte sich die Pruefung ausschliesslich am Objekt, und
    das Objekt war da. Der zepos-plugin-missing-Block wurde also NICHT
    geschrieben, obwohl genau sein Fall vorlag.
    """
    (plugin_root / "hyprclipx.so").write_bytes(b"\x7fELF")

    rendered = plugins.render(
        "# zepos-plugin hyprclipx\n"
        "bind = SUPER SHIFT, V, hyprclipx:toggle,\n"
        "# zepos-plugin-end\n"
        "# zepos-plugin-missing hyprclipx\n"
        "bind = SUPER SHIFT, V, exec, ~/.config/hypr/cliphist-menu.sh\n"
        "# zepos-plugin-end\n")

    assert "hyprclipx:toggle" not in rendered, (
        "die Taste haengt weiter am Plugin, dessen Sammler fehlt")
    assert "cliphist-menu.sh" in rendered, (
        "der Ersatz fehlt - die Taste waere ein leeres Fenster")


def test_only_the_clipboard_is_measured_against_a_second_file(plugins,
                                                              plugin_root):
    """Die vier anderen haben keine zweite Haelfte, und eine Pruefung,
    die ihnen trotzdem eine unterstellte, liesse sie alle ausfallen,
    sobald /usr/lib/hyprclipx fehlt."""
    for name in SPEC_PLUGINS:
        if name != "hyprclipx":
            (plugin_root / f"{name}.so").write_bytes(b"\x7fELF")

    reasons = plugins.unavailable()
    assert sorted(reasons) == ["hyprclipx"], (
        "ausser hyprclipx faellt noch etwas aus, obwohl sein Objekt da "
        f"ist: {reasons}")


def test_the_collector_path_is_the_one_the_package_writes(plugins):
    """Ein Pfad, den die Pruefung erwartet und das Paket nicht schreibt,
    ist ein Plugin, das auf jeder Installation als fehlend gilt - also
    eine Taste, die nie das Plugin bekommt.

    Beide Seiten stehen hier nebeneinander: der Pfad aus src/plugins.py
    und der, den plugins/hyprclipx/CMakeLists.txt installiert - seit dem
    19.08.2026 aus dem Netz nachgebaut statt aus diesem Baum gelesen
    (tests/adopted_plugin_source.py, plugins/LICENSE).
    """
    assert plugins.COLLECTOR == Path("/usr/lib/hyprclipx/collector.py")

    cmake = (plugin_source("hyprclipx")
             / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "helpers/collector.py" in cmake
    assert "DESTINATION lib/hyprclipx" in cmake, (
        "CMake legt den Sammler woandershin, als src/plugins.py sucht")


# --------------------------------------------------------------------
# the setting the installer writes, and nothing used to read
# --------------------------------------------------------------------

def test_plugins_switched_off_in_the_settings_load_nothing(plugins,
                                                           plugin_root):
    """The installer asks the question (spec §8.2 step 6) and writes
    plugins.enabled into user-settings.json. Until this, the answer
    reached nothing at all: every plugin loaded either way."""
    install(plugin_root, *SPEC_PLUGINS)

    rendered = plugins.render(
        "# zepos-plugin hyprzones\nbind = SUPER, Z, hyprzones:show,\n"
        "# zepos-plugin-end\n",
        reasons=plugins.unavailable(enabled=False))

    assert "plugin =" not in rendered
    assert "plugins.enabled" in rendered, (
        "the file does not say which setting switched the plugins off")


def test_the_setting_is_read_from_the_users_settings_file(plugins, plugin_root,
                                                          tmp_path, monkeypatch):
    """Read through settings.load(), so a file that cannot be read raises
    rather than answering "enabled" from a default."""
    user_root = tmp_path / "userroot"
    user_root.mkdir()
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(user_root))
    (user_root / "user-settings.json").write_text(
        '{"schema_version": 1, "plugins": {"enabled": false}}', encoding="utf-8")

    assert plugins.unavailable()["hyprzones"], "the setting was not read"


def test_a_settings_file_without_a_plugins_section_enables_them(
        plugins, plugin_root, tmp_path, monkeypatch):
    """A fresh installation has no settings file, and every existing one
    predates the section. Silence must not switch the desktop off."""
    install(plugin_root, "hyprzones")
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path / "empty"))

    assert "hyprzones" not in plugins.unavailable()


# --------------------------------------------------------------------
# a marker the filter cannot act on
# --------------------------------------------------------------------

def test_a_marker_naming_an_unknown_plugin_is_refused(plugins, plugin_root):
    """A typo would otherwise drop the block on every run - silently, and
    identically to the case where the plugin is merely not installed."""
    with pytest.raises(plugins.MalformedTemplate):
        plugins.render("# zepos-plugin hyprzonez\nx\n# zepos-plugin-end\n")


def test_an_unclosed_block_is_refused(plugins, plugin_root):
    with pytest.raises(plugins.MalformedTemplate):
        plugins.render("# zepos-plugin hyprzones\nbind = a\n")


def test_a_nested_block_is_refused(plugins, plugin_root):
    with pytest.raises(plugins.MalformedTemplate):
        plugins.render("# zepos-plugin hyprzones\n# zepos-plugin hyprbars\n"
                       "# zepos-plugin-end\n# zepos-plugin-end\n")


def test_an_end_marker_with_no_block_is_refused(plugins, plugin_root):
    with pytest.raises(plugins.MalformedTemplate):
        plugins.render("# zepos-plugin-end\n")


# --------------------------------------------------------------------
# the template this project ships
# --------------------------------------------------------------------

def test_the_shipped_template_survives_both_extremes(plugins, plugin_root):
    """Every plugin present, and none of them. A malformed marker in the
    template is a broken generation on a user's machine, and the only
    way to find one is to run the filter over the real file."""
    text = TEMPLATE.read_text(encoding="utf-8")

    nothing = plugins.render(text)
    assert "plugin =" not in nothing

    install(plugin_root, *SPEC_PLUGINS)
    everything = plugins.render(text)
    for name in SPEC_PLUGINS:
        assert f"plugin = {plugin_root}/{name}.so" in everything, name


def test_the_template_declares_every_plugin_in_the_roster(plugins):
    """A plugin with no block is a plugin the machine never loads, which
    is the same as not shipping it."""
    declared = set(re.findall(r"^#\s*zepos-plugin\s+(\S+)\s*$",
                              TEMPLATE.read_text(encoding="utf-8"), re.M))
    assert declared == set(plugins.PLUGINS)


def test_no_template_loads_a_plugin_outside_this_file(plugins):
    """hyprland.conf must never carry a plugin dependency again.

    A `plugin =` line, a `plugin { }` settings block or a plugin
    dispatcher anywhere else is a dependency the filter cannot switch
    off, and therefore a config error on a machine without the object.
    """
    dispatcher = re.compile(
        r"^\s*bind[a-z]*\s*=\s*[^,]*,[^,]*,\s*(" +
        "|".join(re.escape(name) for name in SPEC_PLUGINS) + r")\s*:", re.M)
    offenders = []
    for path in sorted((SRC / "templates").glob("*.template")):
        if path == TEMPLATE:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"^\s*plugin\s*[={]", text, re.M):
            offenders.append(f"{path.name}: a plugin line or block")
        if dispatcher.search(text):
            offenders.append(f"{path.name}: a plugin dispatcher in a bind")
    assert offenders == [], "; ".join(offenders)


# --------------------------------------------------------------------
# hyprpm is gone
# --------------------------------------------------------------------

def _shell_hyprpm(text: str) -> bool:
    """hyprpm outside a comment, in a shell file.

    Comments are stripped rather than counted, because the comments about
    hyprpm are the point: the file that used to run it says why it does
    not any more, and a guard that forbade the explanation would take the
    reason out with the code.
    """
    return "hyprpm" in re.sub(r"(?m)#.*$", "", text)


def _python_hyprpm(path: Path) -> list[str]:
    """hyprpm in Python code or in a string a user could be shown.

    Docstrings are excluded for the same reason shell comments are - and
    only docstrings: a `subprocess.run(["hyprpm", ...])` and a fix line
    reading "run `hyprpm update`" are both strings, and both are the
    thing this forbids.
    """
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    documented = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                documented.add(doc)

    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "hyprpm" in node.value and node.value not in documented:
                hits.append(node.value)
        elif isinstance(node, ast.Name) and "hyprpm" in node.id:
            hits.append(node.id)
    return hits


def test_nothing_in_the_source_tree_runs_hyprpm_or_tells_a_user_to():
    """Spec §7.2. hyprpm builds per user from whatever is on five GitHub
    branches at that moment, which is the opposite of a pinned
    distribution - and it leaves the object in a directory named after
    the Hyprland revision it built against, which no check in this
    project can name.

    install-system.sh ran it with four unpinned repositories, and the
    doctor's own ABI finding told the user to run `hyprpm update` as the
    fix. Advice naming a tool the project removed is worse than no
    advice: it sends the user to build the plugins the one way this
    design rejects.
    """
    offenders = []
    for path in sorted(SRC.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix in {".sh", ".template", ".conf", ".json", ".md"}:
            if _shell_hyprpm(path.read_text(encoding="utf-8", errors="replace")):
                offenders.append(path.relative_to(SRC).as_posix())
        elif path.suffix == ".py":
            if _python_hyprpm(path):
                offenders.append(path.relative_to(SRC).as_posix())
    assert offenders == [], f"hyprpm survives in: {offenders}"


# --------------------------------------------------------------------
# executed: the generator, against a machine with no plugin objects
# --------------------------------------------------------------------

@pytest.fixture
def generator(tmp_path):
    """Run the real generator inside tmp_path, with the plugin directory
    under this test's control.

    Modelled on tests/src/test_generate.py's run_generator: HOME,
    XDG_CONFIG_HOME and XDG_CACHE_HOME all redirected, because the script
    derives its output root, ~/.local/bin and its staging area from them,
    and one no-op stub per command that would reach the running session.
    The stub directory is prepended rather than made the whole PATH - the
    generator needs a real python3, mktemp and date - and every stub is
    checked with shutil.which before a child starts.
    """
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True)
    (home / ".cache").mkdir()

    stubs = tmp_path / "session-stubs"
    stubs.mkdir()
    for name in SESSION_COMMANDS:
        stub = stubs / name
        stub.write_text(f'#!/bin/bash\necho "stub: {name} $*" >&2\nexit 0\n')
        stub.chmod(0o755)
    path = os.pathsep.join([str(stubs), os.environ["PATH"]])
    for name in SESSION_COMMANDS:
        assert shutil.which(name, path=path) == str(stubs / name), (
            f"{name} would reach the real command")

    plugin_root = tmp_path / "hyprland-plugins"
    plugin_root.mkdir()

    # Der Sammler von hyprclipx, aus demselben Grund umgelenkt wie das
    # Plugin-Verzeichnis darueber: er liegt sonst unter /usr/lib, und
    # dann haengt das Ergebnis daran, ob zepos-hyprclipx auf der
    # Maschine des Entwicklers installiert ist.
    collector = tmp_path / "collector.py"

    def run(*arguments, user_root: Path | None = None):
        return subprocess.run(
            [BASH, str(SRC / "generate_config.sh"), *arguments],
            env={
                "PATH": path,
                "HOME": str(home),
                "XDG_CONFIG_HOME": str(home / ".config"),
                "XDG_CACHE_HOME": str(home / ".cache"),
                "ZEPOS_SYSTEM_ROOT": str(SRC),
                "ZEPOS_USER_ROOT": str(user_root or (home / ".config" / "zepos")),
                "ZEPOS_PLUGIN_ROOT": str(plugin_root),
                "ZEPOS_HYPRCLIPX_COLLECTOR": str(collector),
            },
            capture_output=True, text=True, timeout=300,
        )

    run.home = home
    run.hypr = home / ".config" / "hypr"
    run.plugin_root = plugin_root
    run.collector = collector
    return run


@pytest.mark.allow_subprocess
def test_a_machine_with_no_plugin_objects_gets_a_config_that_parses(generator):
    """The case the failsafe exists for, generated end to end.

    Nothing is installed in the plugin directory, so every block is
    dropped. What has to survive is the include itself: hyprland.conf
    sources plugins.conf unconditionally, and a `source =` naming a file
    that is not there is not skipped - Hyprland answers it with "source=
    globbing error: found no match" and reads no further into that line.
    """
    assert generator("-hyprland-universal-config").returncode == 0
    result = generator("-hyprland-plugins-config")
    assert result.returncode == 0, result.stdout + result.stderr

    hyprland = (generator.hypr / "hyprland.conf").read_text()
    include = generator.hypr / "plugins.conf"

    assert "source = ~/.config/hypr/plugins.conf" in hyprland
    assert include.is_file(), "the file hyprland.conf sources was not written"
    # Comments stripped on both sides: they are what the failsafe writes
    # in place of what it dropped, and both files explain in prose why a
    # plugin dependency does not belong in hyprland.conf.
    assert "plugin" not in _uncommented(include.read_text())
    assert "hyprlaunch:" not in _uncommented(hyprland), (
        "a plugin dispatcher survives in the file that costs the session")


def _uncommented(text: str) -> str:
    return re.sub(r"(?m)^\s*#.*$", "", text)


@pytest.mark.allow_subprocess
def test_the_universal_config_alone_still_leaves_the_include_behind(generator):
    """`zepos-generate -hyprland-universal-config` on a fresh machine.

    start-hyprland runs exactly that before it starts the session, and
    the placeholder step that creates the six other sourced files skipped
    this one - so the very first login would have met the globbing error.
    """
    assert generator("-hyprland-universal-config").returncode == 0
    assert (generator.hypr / "plugins.conf").is_file()


@pytest.mark.allow_subprocess
def test_an_installed_plugin_is_loaded_by_the_path_the_package_uses(generator):
    """The other half: with the objects in place the lines appear, and
    every one of them resolves to a file that is really there."""
    for name in SPEC_PLUGINS:
        (generator.plugin_root / f"{name}.so").write_bytes(b"\x7fELF")
    # Und die zweite Haelfte von hyprclipx - das Paket legt beide ab.
    generator.collector.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    result = generator("-hyprland-plugins-config")
    assert result.returncode == 0, result.stdout + result.stderr

    loaded = re.findall(r"(?m)^\s*plugin\s*=\s*(\S+)",
                        (generator.hypr / "plugins.conf").read_text())
    assert sorted(Path(p).stem for p in loaded) == sorted(SPEC_PLUGINS)
    for target in loaded:
        assert Path(target).is_file(), target


@pytest.mark.allow_subprocess
def test_a_plugin_line_naming_an_absent_object_stops_the_run(generator,
                                                             tmp_path):
    """validate_output._plugin_findings, reached.

    The check could not fire while no template in this tree wrote a
    `plugin = <path>` line at all. It can now, and this is the route that
    reaches it: a user override - the supported way to change a template
    - naming an object that is not on the machine. Refusing the run
    leaves the working configuration in place; publishing it would have
    cost the session at the next login.
    """
    user_root = tmp_path / "userroot"
    (user_root / "templates").mkdir(parents=True)
    (user_root / "templates" / "hyprland-failsafe-config.template").write_text(
        "monitor=,preferred,auto,1\n"
        f"plugin = {tmp_path}/nowhere/hyprexpo.so\n", encoding="utf-8")

    result = generator("-hyprland-failsafe-config", user_root=user_root)

    assert result.returncode != 0, result.stdout
    assert "hyprexpo.so" in result.stderr, result.stderr
    assert not (generator.hypr / "hyprland-failsafe.conf").exists(), (
        "a configuration naming an absent plugin object was published")


# --------------------------------------------------------------------
# executed: Hyprland's own verdict on the generated configuration
# --------------------------------------------------------------------

HYPRLAND = "/usr/bin/Hyprland"


@pytest.mark.allow_subprocess
@pytest.mark.skipif(not Path(HYPRLAND).is_file(),
                    reason="Hyprland is not installed on this machine")
def test_hyprland_accepts_a_configuration_generated_without_any_plugin(
        generator, tmp_path):
    """The claim, measured by the only thing entitled to settle it.

    `Hyprland --verify-config` parses the configuration and exits; it
    starts no compositor. It is given an EMPTY XDG_RUNTIME_DIR and the
    test's own HOME under `env -i`, so it cannot see - and could not
    reach - the session running on the machine the tests are on. That
    isolation is the whole reason this may be run at all.

    Both directions, because a check that cannot fail proves nothing:

      * the configuration this branch generates on a machine with no
        plugin object at all: accepted;
      * the same configuration with one plugin dispatcher put back into
        hyprland.conf, which is where all of them used to live: three
        config errors, exactly as measured against the pre-change
        template ("Invalid dispatcher, requested hyprlaunch:toggle does
        not exist").

    That second half is what the failsafe is FOR. It is also why the
    dispatchers moved: Hyprland reports them at parse time, on the file
    that starts the desktop.
    """
    assert generator("-hyprland-universal-config").returncode == 0

    accepted = _verify(generator.home, tmp_path / "runtime-ok")
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert "config ok" in accepted.stdout, accepted.stdout

    # One plugin dispatcher, appended to the published file the way the
    # template used to carry it.
    conf = generator.hypr / "hyprland.conf"
    conf.write_text(conf.read_text() + "bind = SUPER, SPACE, hyprlaunch:toggle,\n")

    refused = _verify(generator.home, tmp_path / "runtime-bad")
    assert refused.returncode != 0, (
        "Hyprland accepted a dispatcher from a plugin that is not loaded - "
        "then moving the binds out of hyprland.conf bought nothing")
    assert "hyprlaunch:toggle" in refused.stdout + refused.stderr


def _verify(home: Path, runtime: Path) -> subprocess.CompletedProcess:
    """Hyprland's config parser, with nothing of this machine in reach.

    XDG_RUNTIME_DIR is required - Hyprland aborts without one - and it is
    the directory a compositor's socket would live in, so it is a fresh
    empty one per call rather than the session's.
    """
    runtime.mkdir(mode=0o700)
    return subprocess.run(
        ["/usr/bin/env", "-i", "PATH=/usr/bin", f"HOME={home}",
         f"XDG_CONFIG_HOME={home / '.config'}", f"XDG_RUNTIME_DIR={runtime}",
         HYPRLAND, "--verify-config"],
        capture_output=True, text=True, timeout=120,
    )


# --------------------------------------------------------------------
# zepos-doctor reads what is in place, not what was generated
# --------------------------------------------------------------------

@pytest.fixture
def doctor(monkeypatch):
    monkeypatch.syspath_prepend(str(SRC))
    import doctor

    return doctor


def test_the_doctor_reads_the_include_as_well_as_hyprland_conf(doctor,
                                                               tmp_path,
                                                               monkeypatch):
    """Where the drift shows up.

    The generator writes a load line only for an object that is there.
    Three weeks later a package update removes it and nothing rewrites
    the file: the configuration in place now names an object that is
    gone. That is the state check_plugin_objects exists for, and it could
    never see it while it read only hyprland.conf - the load lines are
    not in hyprland.conf.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path / "zepos"))
    hypr = tmp_path / "hypr"
    hypr.mkdir()
    (hypr / "hyprland.conf").write_text("source = ~/.config/hypr/plugins.conf\n",
                                        encoding="utf-8")
    (hypr / "plugins.conf").write_text(
        "plugin = /usr/lib/hyprland/plugins/hyprzones.so\n", encoding="utf-8")

    findings = doctor.collect(runner=_no_command)

    assert any("hyprzones.so" in str(finding) for finding in findings), findings


def _no_command(argv, **kwargs):
    raise FileNotFoundError(argv[0])


def test_the_doctor_says_nothing_when_every_named_object_is_there(doctor,
                                                                  tmp_path,
                                                                  monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path / "zepos"))
    hypr = tmp_path / "hypr"
    hypr.mkdir()
    obj = tmp_path / "hyprzones.so"
    obj.write_bytes(b"\x7fELF")
    (hypr / "plugins.conf").write_text(f"plugin = {obj}\n", encoding="utf-8")

    assert [f for f in doctor.collect(runner=_no_command)
            if "hyprzones" in str(f)] == []


def test_the_doctors_rebuild_advice_does_not_name_a_tool_this_project_dropped(
        doctor):
    """The ABI finding told the user to run `hyprpm update`, on a system
    where hyprpm no longer installs anything. Advice that names a tool
    the project removed is worse than no advice: it sends the user to
    build the plugins the one way this design rejects."""
    findings = doctor.check_plugin_abi({
        "buildAquamarine": "0.12.0", "systemAquamarine": "0.13.1",
    })

    assert len(findings) == 1, findings
    assert "hyprpm" not in str(findings[0])
    assert "zepos-" in str(findings[0]), (
        "the finding does not name the packages that provide the objects")
