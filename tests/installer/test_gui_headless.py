# SPDX-License-Identifier: GPL-3.0-or-later
"""Execute installer/gui/ - the one component nothing else here runs.

WHAT THIS CLOSES
    installer/gui/app.py had zero executable coverage. `gi` is not
    installed in .venv, so the module cannot even be imported by the
    pytest process, and tests/installer/test_gui.py says so in its own
    docstring: it tests installer.gui.pages (which is deliberately
    widget-free) and parses app.py as text. A GTK call with the wrong
    argument type therefore reached the shipping ISO and crashed the
    installer on real hardware after the kernel had come up - commit
    e1e21cd, `Adw.PreferencesPage.add(Gtk.Picture)`.

    This test builds the real window, drives the real callbacks and
    fails on that commit. Measured, both ways: with the fix in place it
    exits 0, and against e1e21cd's app.py it exits 1 and reports
    "TypeError: argument group: Expected Adw.PreferencesGroup, but got
    gi.repository.Gtk.Picture".

HOW IT GETS A DISPLAY WITHOUT ONE
    tests/gtk4_headless.py, which is where the three measurements that
    decided the design are written down. They used to be here; they
    moved when tests/menu/test_menu_headless.py needed the same display
    and copying the routine would have created a second one to keep in
    step.

ISOLATION
    The child gets a constructed environment, never this process's own:
    HOME, TMPDIR, XDG_RUNTIME_DIR and every XDG_*_HOME point inside
    tmp_path, GSETTINGS_BACKEND=memory keeps GTK away from the
    developer's dconf, and PATH is an EMPTY directory so neither the
    child nor GLib can reach any binary that was not named here by
    absolute path. That is the same rule tests/conftest.py sets out for
    every allow_subprocess harness; what differs is that the two
    binaries this one does run (the interpreter and gtk4-broadwayd) are
    real by design, and neither writes outside tmp_path.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests.gtk4_headless import (
    broadwayd, gi_interpreter, start_broadwayd, stop_broadwayd,
)

ROOT = Path(__file__).resolve().parents[2]
CHILD = Path(__file__).resolve().parent / "gui_headless_child.py"
# The logo the zepos-installer-gui package installs. Passed to the child
# so branding.LOGO names a file that exists - without it _logo() returns
# None, the crashing branch is never taken, and this test would report
# clean on the commit it exists to catch.
LOGO = ROOT / "src" / "branding" / "zepos-logo.svg"

# Enough for a GTK application to start, build seven pages, run a faked
# installation through a worker thread and exit. Measured at well under
# ten seconds on this machine; the margin is for a loaded CI box.
CHILD_TIMEOUT = 120


def _gi_interpreter() -> tuple[str, list[str]] | None:
    return gi_interpreter({"Gtk": "4.0", "Adw": "1"})


@pytest.mark.allow_subprocess
@pytest.mark.parametrize(
    "mode", ["full", "no-disks", "wireless-fails", "entry-point"])
def test_the_graphical_installer_builds_and_runs(mode: str, tmp_path: Path) -> None:
    """Build the window the ISO builds, and walk it the way a user does.

    Four runs, four different things:

      "full"          every page, every input callback, a wireless
                      association that works, and "Ja" on the erase
                      dialog carried through to the completion handler -
                      with the disks, the networks and the installer
                      injected as fakes.
      "no-disks"      every disk too small and an empty wireless scan,
                      answered with "Nein". Every disk being too small is
                      the only way to reach _build_datentraeger()'s
                      Adw.StatusPage branch; an empty scan is the only
                      way navigation reaches PageState.should_skip();
                      "Nein" is the only way to reach the cancelled
                      toast. None of the three happens on a developer's
                      machine and each is code of its own.
      "wireless-fails" a wrong passphrase - the commonest thing that
                      actually goes wrong in front of this form, and the
                      only way into the two branches of
                      _on_wireless_finished() that show the failure and
                      keep the user on the page.
      "entry-point"   installer.gui.app.main(argv, on_window_shown=...) -
                      the exact line installer/bin/zepos-install runs,
                      with NOTHING injected, so do_activate() resolves
                      IwctlBackend(), list_disks and install for real. It
                      is the one run that proves that signature; the
                      others build ZeposInstallerApp directly and would
                      not notice if main() drifted.
    """
    interpreter = _gi_interpreter()
    if interpreter is None:
        pytest.skip(
            "no interpreter here can import gi/Gtk4/Adw - install "
            "python-gobject, gtk4 and libadwaita to run the graphical "
            "installer's only executable test")
    display_server = broadwayd()
    if display_server is None:
        pytest.skip(
            "gtk4-broadwayd is missing - it ships with gtk4 and is the "
            "headless display this test builds the window on")
    assert LOGO.is_file(), (
        f"{LOGO} is gone. The child points branding.LOGO at it so the "
        "logo branch of _build_page() is actually taken; without a real "
        "file _logo() returns None and this test stops covering the "
        "line that crashed the shipping ISO.")

    executable, extra_path = interpreter
    runtime_dir = tmp_path / "run"
    runtime_dir.mkdir()
    # GLib refuses a world-readable XDG_RUNTIME_DIR and says so on stderr.
    runtime_dir.chmod(0o700)
    for name in ("tmp", "home", "cache", "config", "data"):
        (tmp_path / name).mkdir()
    empty_path = tmp_path / "no-binaries-here"
    empty_path.mkdir()

    process, _socket = start_broadwayd(display_server, runtime_dir, display=11)
    try:
        env = {
            "PATH": str(empty_path),
            "HOME": str(tmp_path / "home"),
            "TMPDIR": str(tmp_path / "tmp"),
            "XDG_RUNTIME_DIR": str(runtime_dir),
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "XDG_DATA_HOME": str(tmp_path / "data"),
            "GDK_BACKEND": "broadway",
            "BROADWAY_DISPLAY": ":11",
            # Not the developer's dconf, and no dbus call to reach it.
            "GSETTINGS_BACKEND": "memory",
            "NO_AT_BRIDGE": "1",
            # The installer activates its own catalogue; a locale
            # inherited from the developer would decide which language
            # the assertions below are reading.
            "LC_ALL": "C",
            "PYTHONPATH": os.pathsep.join([str(ROOT), *extra_path]),
            "PYTHONUNBUFFERED": "1",
        }
        result = subprocess.run(
            [executable, str(CHILD), mode, str(LOGO)],
            env=env, cwd=str(tmp_path), capture_output=True, text=True,
            timeout=CHILD_TIMEOUT,
        )
    finally:
        stop_broadwayd(process)

    report = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert result.returncode != 139, (
        "the child segfaulted, which is what GTK does when it has no "
        "display - the broadway server did not take the connection:\n"
        + report)
    assert result.returncode == 0, (
        "building or driving the graphical installer failed:\n" + report)

    # The child prints what it managed to reach. Asserting on it here
    # rather than only on the exit code, because a child that quit early
    # for some reason of its own would otherwise be indistinguishable
    # from a run that did the work.
    # _apply_branding() never raises - a stylesheet that will not parse
    # must cost the brand and not the installer - so the ONLY sign that
    # ZeptronIT's colours were not applied is this line on stderr. A
    # medium that installs perfectly in libadwaita's default purple is a
    # medium nobody would file a bug about.
    assert "branding not applied" not in result.stderr, (
        "installer/gui/branding.py's stylesheet did not load:\n" + report)
    # GLib prints its diagnostics here and nowhere else, and GTK's are
    # not decoration: e1e21cd's crash also produced "Child name 'sprache'
    # not found in GtkStack" on this stream, from the code that carried
    # on after it. Measured empty in all three modes on this machine, so
    # anything at all appearing is new.
    for level in ("-CRITICAL **:", "-WARNING **:", "-ERROR **:"):
        assert level not in result.stderr, (
            f"GLib reported a {level.strip(' *:-')} while the installer "
            "was being built:\n" + report)
    assert "window-shown" in result.stdout, (
        "do_activate() never reported the window as shown:\n" + report)
    if mode == "entry-point":
        # The entry point resolves its own dependencies, so there is
        # nothing here to drive - the window existing IS the assertion.
        assert "entry:sprache" in result.stdout, (
            "main(argv, on_window_shown=...) returned without a window "
            "on its first page:\n" + report)
        assert "FAILURE" not in result.stdout, report
        return
    # The form was walked to the last page, back to the first, and
    # forward again. Anything less and the erase dialog below was reached
    # by some shortcut rather than by the footer buttons.
    assert "forward:zusammenfassung" in result.stdout, (
        "Weiter did not reach the summary page:\n" + report)
    assert "back:sprache" in result.stdout, (
        "Zurueck did not reach the first page again:\n" + report)
    assert "again:zusammenfassung" in result.stdout, (
        "the second pass forward did not reach the summary page:\n" + report)
    # Not just "a Gtk.Picture was built" - that is what e1e21cd did. This
    # is the picture having an image in it, which is the only difference
    # between a logo and an empty space, and which
    # Gtk.Picture.new_for_filename() reports through nothing at all.
    assert "logo:" in result.stdout, (
        "the ZeptronIT logo is missing or did not decode:\n" + report)

    # Die Partitionierungsseite, ueber ihre echten Bedienelemente
    # gegangen: bereinigen, eine Groesse ohne Einheit ablehnen, eine ESP
    # von Hand anlegen, eine zu grosse Partition ablehnen, eine geplante
    # wieder entfernen, die Wurzel ueber den Rest legen. Jede dieser
    # Marken ist eine Stelle, an der der Treiber weitergekommen ist -
    # fehlt eine, hat die Seite an dieser Stelle etwas anderes getan, und
    # die Begruendung steht als FAILURE daneben.
    #
    # Sie sind hier einzeln aufgezaehlt statt als eine Marke am Ende,
    # weil ein Treiber, der auf halbem Weg aufhoert, sonst nicht von
    # einem zu unterscheiden waere, der durchgelaufen ist.
    if mode == "no-disks":
        assert "part:no-disk" in result.stdout, (
            "ohne nutzbare Platte darf der Partitionierungstreiber nicht "
            "laufen - was er dann meldet, waere die fehlende Platte und "
            "nicht die Seite:\n" + report)
    else:
        for mark in ("part:cleared", "part:unit-refused", "part:esp",
                     "part:too-large", "part:removed", "part:language-kept"):
            assert mark in result.stdout, (
                f"der Partitionierungstreiber kam nicht bis {mark}:\n"
                + report)
        # Zwei: die ESP von Hand und die Wurzel ueber den Rest. Die Zahl
        # steht hier, weil "eine Einteilung" auch das ist, was eine Seite
        # meldet, die den zweiten Knopfdruck verschluckt hat.
        assert "part:planned:2" in result.stdout, (
            "die von Hand gebaute Einteilung hat nicht genau zwei "
            "Partitionen:\n" + report)

    if mode == "no-disks":
        # "Nein" on the erase dialog: choose_finish() read the answer and
        # nothing was installed.
        assert "answered:no" in result.stdout, (
            "the erase dialog was never answered with Nein:\n" + report)
        assert "outcome:" not in result.stdout, (
            "an installation ran after the user declined it:\n" + report)
        assert "FAILURE" not in result.stdout, report
        return

    # "Ja" on the point of no return, and the installation carried
    # through to _on_installation_finished(). Reached by answering the
    # real Adw.AlertDialog, not by calling _run_installation() - the
    # dialog's own handler is where an installation starts.
    assert "answered:yes" in result.stdout, (
        "the erase dialog was never answered with Ja:\n" + report)
    assert "outcome:True" in result.stdout, (
        "the installation path never reached its completion handler:\n"
        + report)

    # _start_wireless_step() and _on_wireless_finished() are the only
    # widget code that leaves the main thread before anything is
    # installed, and they are unreachable unless a network is actually
    # chosen. Which page the drive then STARTS on is the proof of what
    # the worker reported: the completion handler advances the page only
    # when the association worked.
    assert "wireless-started" in result.stdout, (
        "the wireless worker path was not driven:\n" + report)
    if mode == "full":
        assert "start:datentraeger" in result.stdout, (
            "_on_wireless_finished() never advanced past the network "
            "page, so the worker's success path is not covered:\n" + report)
    if mode == "wireless-fails":
        assert "start:netzwerk" in result.stdout, (
            "a failed association still advanced the page - the branch "
            "that keeps the user on the network page to correct the "
            "passphrase is not covered, or is wrong:\n" + report)
    assert "FAILURE" not in result.stdout, report


@pytest.mark.allow_subprocess
def test_the_headless_child_is_what_fails_when_a_widget_call_is_wrong(
    tmp_path: Path,
) -> None:
    """The guard's own guard.

    A smoke test that cannot fail is worse than none: it reports green
    and is believed. This runs the same child against a copy of the tree
    whose _build_page() carries e1e21cd's line back - one edit,
    reversing the fix - and requires the exact TypeError from the
    hardware report.

    It also pins the finding that made the child watch sys.excepthook:
    Adw.Application.run() still returns 0 after that exception, because
    GLib invoked do_activate() as a signal callback and PyGObject cannot
    raise back across it. A child that trusted the exit code alone would
    call this crash a success - which is exactly what the shipping ISO
    did.
    """
    interpreter = _gi_interpreter()
    if interpreter is None:
        pytest.skip("no interpreter here can import gi/Gtk4/Adw")
    display_server = broadwayd()
    if display_server is None:
        pytest.skip("gtk4-broadwayd is missing")

    source = (ROOT / "installer" / "gui" / "app.py").read_text(encoding="utf-8")

    # The mistake is re-INTRODUCED rather than un-fixed, because the
    # line it lived on is gone: the wordmark moved out of _build_page()
    # into the wizard header, where it goes into a Gtk.Box and a
    # Gtk.Box takes any widget. What has to keep working is the harness -
    # that it still turns "a widget handed to an API typed against a
    # different one" into a failure rather than a passing run.
    #
    # So a page gains the exact call that crashed the shipping medium:
    # Adw.PreferencesPage.add() with a Gtk.Picture, which raises
    #
    #     TypeError: argument group: Expected Adw.PreferencesGroup,
    #     but got gi.repository.Gtk.Picture
    #
    # while the first page is built. If this test ever goes green, the
    # child stopped noticing, and nothing else would.
    anchor = "        page = Adw.PreferencesPage()\n"
    assert anchor in source, (
        "installer/gui/app.py no longer builds pages the way this test "
        "injects into. Update the anchor below - do not delete the test: "
        "the crash it reproduces is the reason the headless child "
        "exists.")
    broken = source.replace(
        anchor,
        anchor + "        page.add(Gtk.Picture())          # injected\n",
        1)

    tree = tmp_path / "tree"
    for package in ("", "core", "gui", "tui", "bin"):
        (tree / "installer" / package).mkdir(parents=True, exist_ok=True)
    for path in (ROOT / "installer").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        target = tree / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    (tree / "installer" / "gui" / "app.py").write_text(broken, encoding="utf-8")

    executable, extra_path = interpreter
    runtime_dir = tmp_path / "run"
    runtime_dir.mkdir()
    runtime_dir.chmod(0o700)
    for name in ("tmp", "home"):
        (tmp_path / name).mkdir()
    empty_path = tmp_path / "no-binaries-here"
    empty_path.mkdir()

    process, _socket = start_broadwayd(display_server, runtime_dir, display=12)
    try:
        result = subprocess.run(
            [executable, str(CHILD), "full", str(LOGO)],
            env={
                "PATH": str(empty_path),
                "HOME": str(tmp_path / "home"),
                "TMPDIR": str(tmp_path / "tmp"),
                "XDG_RUNTIME_DIR": str(runtime_dir),
                "GDK_BACKEND": "broadway",
                "BROADWAY_DISPLAY": ":12",
                "GSETTINGS_BACKEND": "memory",
                "NO_AT_BRIDGE": "1",
                "LC_ALL": "C",
                "PYTHONPATH": os.pathsep.join([str(tree), *extra_path]),
                "PYTHONUNBUFFERED": "1",
            },
            cwd=str(tmp_path), capture_output=True, text=True,
            timeout=CHILD_TIMEOUT,
        )
    finally:
        stop_broadwayd(process)

    report = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert result.returncode == 1, (
        "the headless child accepted a build that crashes the installer "
        "on real hardware:\n" + report)
    assert (
        "TypeError: argument group: Expected Adw.PreferencesGroup, but "
        "got gi.repository.Gtk.Picture" in result.stdout
    ), ("the child failed, but not with the crash from the hardware "
        "report - so it is measuring something else:\n" + report)
    assert "\nrun: 0\n" in result.stdout, (
        "Adw.Application.run() no longer returns 0 after do_activate() "
        "raised. If that changed, the sys.excepthook watch in the child "
        "and in installer/bin/zepos-install may no longer be the only "
        "channel that carries the failure - re-measure before "
        "simplifying either:\n" + report)
