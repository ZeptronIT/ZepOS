# SPDX-License-Identifier: GPL-3.0-or-later
"""Every GTK call in installer/gui/, read against GTK's own type data.

tests/installer/test_gui_headless.py EXECUTES the widget tree, which is
the stronger check and the one that would have stopped e1e21cd on its
own. This is the other half: it reads lines nothing executes.

That difference is not hypothetical. _logo()'s `except Exception` branch
needs an SVG that gdk-pixbuf refuses; _build_datentraeger()'s status
page needs a machine whose every disk is too small (the headless child
fakes exactly that, and it took a second run mode to do it); an error
path in the installation handler needs a failed installation. Each of
those is a line with a GTK call in it, and each is one the smoke test
either misses or only reaches because somebody thought to arrange it.

WHAT A CLEAN RUN HERE DOES NOT MEAN
    See tests/installer/gir_types.py's module docstring for the full
    list of what this cannot see. The short version: it only speaks
    about calls where BOTH the receiver's type and the argument's type
    are pinned by the file itself, and it says nothing about whether a
    call that type-checks makes sense. It is a floor, not a ceiling.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from gir_types import GIR_DIR, GirIndex, ModuleCheck, check_tree

ROOT = Path(__file__).resolve().parents[2]
GUI = ROOT / "installer" / "gui"


@pytest.fixture(scope="module")
def index() -> GirIndex:
    built = GirIndex()
    if not built.types:
        # Not a silent skip. A machine that can run the graphical
        # installer has gtk4 on it, and gtk4 ships the .gir files - so
        # "no type data" on such a machine means the directory moved,
        # and this guard would otherwise pass by doing nothing at all.
        if shutil.which("gtk4-broadwayd") is not None:
            pytest.fail(
                f"gtk4 is installed but {GIR_DIR} holds no readable "
                "introspection data, so this guard would check nothing. "
                "Find where the .gir files went before trusting a green "
                "run.")
        pytest.skip(
            f"{GIR_DIR} has no GObject-Introspection XML - install gtk4 "
            "and libadwaita to check the graphical installer's calls "
            "against their real signatures")
    return built


def test_the_gui_makes_no_call_gtk_would_refuse(index: GirIndex) -> None:
    """The whole of installer/gui/, every file, every line.

    A finding here is not a style opinion: each one names a call whose
    argument type the C function's own signature rules out, which
    PyGObject turns into a TypeError the moment that line runs. On the
    shipping medium that moment is in front of a user who has just
    booted the ISO.
    """
    findings = check_tree(GUI.rglob("*.py"), index)
    assert findings == [], (
        "installer/gui/ calls GTK in a way GTK's own type data refuses:\n"
        + "\n".join(f"  {finding}" for finding in findings))


def test_the_check_catches_the_call_that_shipped(index: GirIndex) -> None:
    """The guard's own guard, on the exact line from the hardware report.

    e1e21cd put a Gtk.Picture into Adw.PreferencesPage.add(), whose only
    accepted argument is an Adw.PreferencesGroup. A checker that had
    quietly stopped resolving types would report the tree above as clean
    and say nothing; this is what makes that impossible.
    """
    source = """
from gi.repository import Adw, Gtk


class Window:
    @staticmethod
    def _logo() -> Gtk.Widget | None:
        return Gtk.Picture.new_for_filename("/logo.svg")

    def _build_page(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        logo = self._logo()
        if logo is not None:
            page.add(logo)
        return page
"""
    findings = ModuleCheck("e1e21cd.py", source, index).run()
    assert len(findings) == 1, findings
    assert "Adw.PreferencesPage.add() takes Adw.PreferencesGroup" in str(findings[0])
    # The `page.add(logo)` line, so a finding points at the call rather
    # than at the file.
    assert source.splitlines()[findings[0].line - 1].strip() == "page.add(logo)"


@pytest.mark.parametrize("snippet, expected", [
    # A widget where a specific subclass is required. Adw.Toast is not a
    # widget at all, and Gtk.Label is not a toast.
    ("""
from gi.repository import Adw, Gtk
def f():
    overlay = Adw.ToastOverlay()
    overlay.add_toast(Gtk.Label(label="x"))
""", "takes Adw.Toast as 'toast', and is given Gtk.Label"),
    # A method the type does not have: an AttributeError with a display
    # attached, and nothing at all without one.
    ("""
from gi.repository import Adw
def f():
    page = Adw.PreferencesPage()
    page.add_group(page)
""", "has no method add_group()"),
    # A construct property that does not exist. PyGObject builds every
    # widget through g_object_new, so this is a TypeError from the
    # constructor - the kind a German keyword typed into an English API
    # produces.
    ("""
from gi.repository import Adw
def f():
    row = Adw.EntryRow(titel="Rechnername")
""", "has no property 'titel'"),
    # Two arguments the wrong way round. Reads perfectly.
    ("""
from gi.repository import Gtk
def f():
    stack = Gtk.Stack()
    stack.add_named("sprache", Gtk.Label(label="x"))
""", "and is given the literal 'sprache'"),
    # Not a widget at all where a child is expected.
    ("""
from gi.repository import Gtk
def f():
    scroller = Gtk.ScrolledWindow()
    scroller.set_child(Gtk.StringList.new(["a"]))
""", "takes Gtk.Widget as 'child', and is given Gtk.StringList"),
], ids=["wrong-subclass", "no-such-method", "no-such-property",
        "arguments-swapped", "not-a-widget"])
def test_the_check_finds_each_shape_of_the_mistake(
    snippet: str, expected: str, index: GirIndex
) -> None:
    findings = ModuleCheck("snippet.py", snippet, index).run()
    assert len(findings) == 1, f"expected exactly one finding, got {findings}"
    assert expected in str(findings[0]), findings[0]


@pytest.mark.parametrize("snippet", [
    # Any widget really is allowed in a preferences group - the
    # declaration says Gtk.Widget, and app.py relies on it for its error
    # labels and its status page.
    """
from gi.repository import Adw, Gtk
def f():
    group = Adw.PreferencesGroup()
    group.add(Gtk.Label(label="x"))
    group.add(Adw.StatusPage(title="x"))
""",
    # Gtk constructors are DECLARED to return Gtk.Widget while PyGObject
    # hands back the real subclass. Trusting the declaration would report
    # every Gtk.Picture-only method below as unknown.
    """
from gi.repository import Gtk
def f():
    picture = Gtk.Picture.new_for_filename("/logo.svg")
    picture.set_content_fit(Gtk.ContentFit.CONTAIN)
    picture.set_can_shrink(True)
""",
    # A parameter annotation is as good as a constructor call.
    """
from gi.repository import Adw, Gtk
def build(group: Adw.PreferencesGroup) -> None:
    group.add(Gtk.Label(label="x"))
""",
    # An attribute holding an injected callable is not a method of the
    # GObject base class, and calling it is not a missing method.
    """
from gi.repository import Adw
class App(Adw.Application):
    def __init__(self, hook=None):
        super().__init__()
        self._hook = hook

    def do_activate(self):
        self._hook()
""",
    # Das erste Argument einer @staticmethod ist NICHT die Instanz.
    #
    # GEMESSEN am 12.08.2026 an installer/gui/app.py: `_replace_tail` ist
    # eine `@staticmethod` mit der Signatur `(buffer, rendered)`, und
    # dieser Waechter gab ihrem `buffer` den Typ der umgebenden Klasse.
    # Ergebnis waren elf Funde in einer einzigen Methode - eine
    # Adw.ApplicationWindow ohne get_start_iter(), get_end_iter(),
    # delete() und insert() -, und alle elf waren falsch. Der ganze Lauf
    # war deswegen rot, und zwar ueber Zeilen, die auf dem Medium bei
    # jeder Installation ausgefuehrt werden.
    """
from gi.repository import Adw
class Window(Adw.ApplicationWindow):
    @staticmethod
    def _replace_tail(buffer, rendered):
        buffer.delete(buffer.get_start_iter(), buffer.get_end_iter())
        buffer.insert(buffer.get_end_iter(), rendered)

    @classmethod
    def _from(cls, buffer):
        buffer.get_end_iter()
""",
], ids=["any-widget-in-a-group", "constructor-returns-the-subclass",
        "annotated-parameter", "injected-callable-attribute",
        "staticmethod-first-argument-is-not-the-instance"])
def test_the_check_stays_quiet_where_the_code_is_right(
    snippet: str, index: GirIndex
) -> None:
    """False positives are the way a guard gets switched off.

    Each snippet is a pattern installer/gui/app.py actually uses, and an
    earlier version of the checker reported three of them.
    """
    assert ModuleCheck("snippet.py", snippet, index).run() == []


def test_every_gui_file_is_actually_read(index: GirIndex) -> None:
    """A checker pointed at nothing passes.

    rglob over a renamed or moved directory yields an empty list, and
    the assertion above would then hold trivially - which is the same
    failure mode as having no guard.
    """
    files = sorted(path.name for path in GUI.rglob("*.py"))
    assert files == ["__init__.py", "app.py", "branding.py", "pages.py"], files
    read = ModuleCheck(
        "app.py", (GUI / "app.py").read_text(encoding="utf-8"), index)
    read.run()
    assert read.gi_namespaces == {"Adw", "Gdk", "GLib", "Gtk", "Pango"}, (
        "app.py no longer imports the namespaces this guard resolves "
        f"its calls through: {read.gi_namespaces}")
    assert read.class_bases == {
        "InstallerWindow": "Adw.ApplicationWindow",
        "ZeposInstallerApp": "Adw.Application",
    }, read.class_bases
