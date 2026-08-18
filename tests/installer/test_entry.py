# SPDX-License-Identifier: GPL-3.0-or-later
import importlib.machinery
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from installer.core.i18n import activate, current_language

# Anchored on this file, never on the working directory. The same bug
# tests/installer/test_i18n.py carried: as a relative path this resolves
# against wherever pytest was started, so a cwd holding an unrelated
# installer/bin/zepos-install would be loaded and tested instead of this
# repository's - and a cwd holding none at all turns every test in this
# module into a collection error that looks like a broken checkout.
ENTRY_PATH = Path(__file__).resolve().parents[2] / "installer" / "bin" / "zepos-install"

# spec_from_file_location() picks a loader by matching the location's
# suffix against its list of supported loaders (see
# importlib._bootstrap_external.spec_from_file_location). A file with no
# suffix at all - which installer/bin/zepos-install deliberately has, so
# it can be invoked directly as `zepos-install` - matches none of them
# and the function returns None instead of a spec, regardless of whether
# the file exists. Confirmed on this interpreter: the call used to raise
# AttributeError: 'NoneType' object has no attribute 'loader' even after
# the target file was created. Passing a loader explicitly (the same
# SourceFileLoader spec_from_file_location would have picked for a .py
# file) sidesteps the suffix lookup and loads the file as plain Python
# source, which is all it is.
loader = importlib.machinery.SourceFileLoader("zepos_install", str(ENTRY_PATH))
spec = importlib.util.spec_from_file_location(
    "zepos_install", ENTRY_PATH, loader=loader
)
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


@pytest.fixture(autouse=True)
def _english_environment(monkeypatch):
    """main() now activates a catalogue from the environment's own locale
    - its two messages appear before either surface can ask the user
    anything. This suite asserts on msgids, so the environment is pinned
    to English here, and the catalogue is reset afterwards so a German
    one cannot leak into the tests collected next (same reasoning as
    test_tui.py's own fixture)."""
    monkeypatch.setenv("LC_ALL", "en_US.UTF-8")
    monkeypatch.setenv("LC_MESSAGES", "en_US.UTF-8")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    yield
    activate("en")


def test_gui_chosen_when_display_and_gtk_available():
    assert entry.choose_surface({"WAYLAND_DISPLAY": "wayland-0"}, True) == "gui"


def test_tui_chosen_without_display():
    assert entry.choose_surface({}, True) == "tui"


def test_tui_chosen_when_gtk_import_fails():
    assert entry.choose_surface({"WAYLAND_DISPLAY": "wayland-0"}, False) == "tui"


def test_explicit_tui_request_wins():
    assert entry.choose_surface(
        {"WAYLAND_DISPLAY": "wayland-0", "ZEPOS_INSTALLER_SURFACE": "tui"}, True
    ) == "tui"


def test_x11_display_also_counts():
    assert entry.choose_surface({"DISPLAY": ":0"}, True) == "gui"


# --- main()'s real fallback ------------------------------------------------
#
# GTK4/libadwaita are installed on this machine but there is no display, so
# these tests must never construct a window or call either surface's real
# main(). What they exercise instead:
#
#   * the exact failure shape measured by hand on this machine, without a
#     display: constructing installer.gui.app.InstallerWindow() raises
#     "RuntimeError: Gtk couldn't be initialized" *inside* do_activate(), a
#     signal callback GLib invokes from C. PyGObject cannot propagate a
#     Python exception back across that boundary, so it reports it through
#     sys.excepthook instead and lets the call return normally - here,
#     Adw.Application.run() returned 0, the same code a real successful
#     install would return. A fake below reproduces that shape (raise,
#     catch, hand to sys.excepthook, return 0) without needing gi at all.
#
#   * a real, unmocked run of the "gi is not importable" fallback: this
#     venv genuinely has no gi (checked: `import gi` raises
#     ModuleNotFoundError here), so forcing ZEPOS_INSTALLER_SURFACE=gui and
#     calling entry.main() drives the real import failure and the real
#     installer.tui.app.main() -> installer.core.disks.list_disks() ->
#     subprocess.run() chain. tests/conftest.py's isolation guard blocks
#     that last call and raises its own RuntimeError - seeing exactly that
#     RuntimeError (and not, say, ModuleNotFoundError escaping main()
#     uncaught) is proof the fallback path was actually taken, not just
#     that some exception happened to be swallowed somewhere.


def test_attempt_surface_returns_the_exception_reported_only_via_excepthook():
    """The failure shape measured on this machine: the call returns 0,
    nothing raises, and the only trace of the failure is what reached
    sys.excepthook while the call was running."""

    def fake_gui(argv, stop_watching):
        try:
            raise RuntimeError("Gtk couldn't be initialized")
        except RuntimeError:
            sys.excepthook(*sys.exc_info())
        return 0

    code, error = entry._attempt_surface(fake_gui, [])
    assert code == 0
    assert isinstance(error, RuntimeError)
    assert str(error) == "Gtk couldn't be initialized"


def test_attempt_surface_returns_a_directly_raised_exception():
    """Covers failures reached before any event loop starts, e.g. the
    Application subclass's own constructor raising."""

    def fake_gui(argv, stop_watching):
        raise RuntimeError("no Application object")

    code, error = entry._attempt_surface(fake_gui, [])
    assert code == 1
    assert isinstance(error, RuntimeError)


def test_attempt_surface_reports_no_error_on_a_clean_run():
    def fake_gui(argv, stop_watching):
        return 0

    code, error = entry._attempt_surface(fake_gui, [])
    assert code == 0
    assert error is None


def test_attempt_surface_does_not_report_nonzero_exit_without_an_exception():
    """A surface reporting its own failed installation (disk write error,
    etc.) is not a reason to fall back to the other interface - only an
    inability to run the surface at all is."""

    def fake_gui(argv, stop_watching):
        return 7

    code, error = entry._attempt_surface(fake_gui, [])
    assert code == 7
    assert error is None


def test_attempt_surface_lets_a_direct_keyboard_interrupt_propagate():
    """Ctrl-C means stop, not 'try the other interface'."""

    def fake_gui(argv, stop_watching):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        entry._attempt_surface(fake_gui, [])


def test_attempt_surface_does_not_treat_a_keyboard_interrupt_from_excepthook_as_failure():
    """PyGObject funnels a KeyboardInterrupt raised inside a GLib callback
    through sys.excepthook exactly like any other exception (checked by
    hand against real GLib: a KeyboardInterrupt raised inside a
    GLib.idle_add callback was reported via sys.excepthook while the
    surrounding GLib.MainLoop.run() call returned normally). If that were
    recorded the same way an ordinary exception is, main() would print
    "falling back" and silently start the text interface after the user
    pressed Ctrl-C."""

    def fake_gui(argv, stop_watching):
        try:
            raise KeyboardInterrupt
        except KeyboardInterrupt:
            sys.excepthook(*sys.exc_info())
        return 0

    code, error = entry._attempt_surface(fake_gui, [])
    assert code == 0
    assert error is None


def test_attempt_surface_stops_watching_once_the_surface_says_so():
    """The watch exists to catch ONE failure: the graphical session not
    coming up at all, which happens before any window is shown. Left
    running for the whole session it records every later exception too -
    a failed installation, a stray error in a callback - and main() then
    prints "the graphical interface could not start" and restarts the
    text interface from its first question underneath a perfectly working
    window. After a successful installation that walks the user into a
    second erase of an already-installed disk."""

    def fake_gui(argv, stop_watching):
        stop_watching()
        try:
            raise RuntimeError("archinstall failed halfway through")
        except RuntimeError:
            sys.excepthook(*sys.exc_info())
        return 0

    code, error = entry._attempt_surface(fake_gui, [])
    assert code == 0
    assert error is None


def test_attempt_surface_still_reports_a_failure_before_the_window_is_shown():
    """The counterpart: nothing has called stop_watching() yet, so this
    is exactly the failure the watch exists for."""

    def fake_gui(argv, stop_watching):
        try:
            raise RuntimeError("Gtk couldn't be initialized")
        except RuntimeError:
            sys.excepthook(*sys.exc_info())
        stop_watching()
        return 0

    _code, error = entry._attempt_surface(fake_gui, [])
    assert isinstance(error, RuntimeError)


def test_attempt_surface_restores_the_previous_excepthook():
    previous = sys.excepthook
    entry._attempt_surface(lambda argv, stop_watching: 0, [])
    assert sys.excepthook is previous


def test_gui_import_failure_falls_back_to_the_real_tui(monkeypatch, capsys,
                                                       request):
    """No mocking of installer.gui.app or installer.tui.app: this venv
    genuinely has no gi (verified separately), so forcing the gui surface
    drives a real ModuleNotFoundError out of `from installer.gui.app
    import main`, and the fallback must reach the real
    installer.tui.app.main(), which reaches the real
    installer.core.disks.list_disks(), which reaches the real
    subprocess.run() that tests/conftest.py's isolation guard blocks.

    installer.tui.app.main() treats a RuntimeError from list_disks() as an
    ordinary, expected failure (no disk tool available) and reports it
    through its own io.say() instead of letting it propagate - so the
    guard tripping is visible in captured stdout, and main()'s return
    value (1, from installer.tui.app.main()'s own "could not list disks"
    branch) is what proves the real text interface ran, not a mock.

    WHAT THIS TEST IS STANDING ON, made explicit
        Nothing here is mocked, so the only thing between this test and
        `lsblk` - and, if list_disks ever succeeded, `iwctl station <dev>
        scan` against the developer's own wireless card - is the
        isolation guard. It is not a backdrop: it is load-bearing, and it
        is one @pytest.mark.allow_subprocess away from being absent.

        So the marker's absence is asserted, and the guard is PROVED to
        be in force by tripping it here rather than assumed from the fact
        that its message showed up. And the message is taken from the
        guard itself instead of being spelled out: "real process" written
        as a literal keeps passing after the guard has been reworded, at
        which point this test is asserting on a string nothing produces
        any more - which is the same silence it was written to prevent.
    """
    assert request.node.get_closest_marker("allow_subprocess") is None, (
        "this test drives the installer with nothing mocked at all; with "
        "the marker it runs lsblk, and iwctl, against this machine")

    with pytest.raises(RuntimeError) as blocked:
        subprocess.run(["true"])
    guard_message = str(blocked.value)

    monkeypatch.setenv("ZEPOS_INSTALLER_SURFACE", "gui")
    assert entry.main([]) == 1
    out = capsys.readouterr()
    assert guard_message in out.out, (
        "the text interface did not report the blocked process, so it is "
        f"not clear it ran at all:\n{out.out}")
    assert "graphical interface could not start" in out.err
    assert "Falling back to the text interface." in out.err


def _install_fake_module(monkeypatch, name, **attrs):
    """Inject a fake module into sys.modules for the duration of a test, so
    `from <name> import ...` inside entry.main() picks it up without ever
    importing the real (gi-dependent, or subprocess-touching) module."""
    fake_module = type(sys)(name)
    for attr, value in attrs.items():
        setattr(fake_module, attr, value)
    monkeypatch.setitem(sys.modules, name, fake_module)
    return fake_module


def test_main_returns_the_gui_result_without_falling_back_on_success(
    monkeypatch, capsys
):
    monkeypatch.setenv("ZEPOS_INSTALLER_SURFACE", "gui")
    _install_fake_module(
        monkeypatch, "installer.gui.app",
        main=lambda argv, on_window_shown=None: 42,
    )

    assert entry.main([]) == 42
    assert capsys.readouterr().err == ""


def test_main_falls_back_to_the_tui_result_when_the_gui_cannot_start(
    monkeypatch, capsys
):
    """Full chain with both surfaces faked: the gui fake reproduces the
    measured failure shape (exception only reaches sys.excepthook, call
    returns 0), and the tui fake's distinct return value proves main()
    actually reached and returned the *text* surface's result, not the
    gui's own (misleading, successful-looking) 0."""
    monkeypatch.setenv("ZEPOS_INSTALLER_SURFACE", "gui")

    def fake_gui_main(argv, on_window_shown=None):
        try:
            raise RuntimeError("Gtk couldn't be initialized")
        except RuntimeError:
            sys.excepthook(*sys.exc_info())
        return 0

    _install_fake_module(monkeypatch, "installer.gui.app", main=fake_gui_main)
    _install_fake_module(monkeypatch, "installer.tui.app", main=lambda argv: 5)

    assert entry.main([]) == 5
    err = capsys.readouterr().err
    assert "Gtk couldn't be initialized" in err
    assert "graphical interface could not start" in err
    assert "Falling back to the text interface." in err


# --- the entry point's own two messages -------------------------------


def test_the_environment_locale_selects_the_catalogue():
    assert entry.environment_language({"LANG": "de_DE.UTF-8"}) == "de"
    assert entry.environment_language({"LANG": "en_US.UTF-8"}) == "en"


def test_lc_all_wins_over_lang():
    assert entry.environment_language(
        {"LC_ALL": "en_US.UTF-8", "LANG": "de_DE.UTF-8"}
    ) == "en"


def test_an_unsupported_or_missing_locale_falls_back_to_english():
    assert entry.environment_language({}) == "en"
    assert entry.environment_language({"LANG": "kl_GL.UTF-8"}) == "en"
    assert entry.environment_language({"LANG": ""}) == "en"


def test_main_speaks_the_environments_language(monkeypatch, capsys):
    """The counterpart to the fixture above: these two messages used to
    stay English whatever the live environment's locale was - and they
    are exactly the messages a failing graphical start produces, when
    being told what happened matters most."""
    monkeypatch.setenv("LC_ALL", "de_DE.UTF-8")
    monkeypatch.setenv("ZEPOS_INSTALLER_SURFACE", "gui")

    def fake_gui_main(argv, on_window_shown=None):
        raise RuntimeError("Gtk couldn't be initialized")

    _install_fake_module(monkeypatch, "installer.gui.app", main=fake_gui_main)
    _install_fake_module(monkeypatch, "installer.tui.app", main=lambda argv: 5)

    assert entry.main([]) == 5
    err = capsys.readouterr().err
    # Asserted through the mechanism rather than on translated text: the
    # German string only exists once po/build.sh has compiled a
    # catalogue, and po/build/ is gitignored (see I5).
    assert current_language() == "de"
    assert err != ""
