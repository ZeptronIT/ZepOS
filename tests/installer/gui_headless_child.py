# SPDX-License-Identifier: GPL-3.0-or-later
"""The graphical installer, built and driven once, in a throwaway process.

NOT a test module - pytest never collects this file (no test_ prefix).
tests/installer/test_gui_headless.py starts it as a child, because it is
the only way this code can be executed at all in this suite:

  * `gi` is not installed in .venv, so the pytest process cannot import
    installer.gui.app;
  * a GTK4 widget cannot be CONSTRUCTED without a display connection -
    measured, not assumed: Gtk.Box() with no GDK display segfaults the
    interpreter (exit 139), which inside pytest would end the whole
    session with no report at all.

The display is gtk4-broadwayd, GTK's own HTML5 backend. It ships with
gtk4 itself, needs neither X nor Wayland nor a GPU, and the test starts
one per run against a socket inside tmp_path.

WHY THE EXIT CODE IS NOT ENOUGH, AND sys.excepthook IS WATCHED
    Measured on the version this file was written for (e1e21cd, the
    ZeptronIT branding commit): the TypeError raised inside
    do_activate() is printed by PyGObject and Adw.Application.run()
    still returns 0. GLib invokes do_activate as a signal callback and a
    Python exception cannot cross back over the C stack that called it.
    A child that only reported run()'s return value would have called
    that crash a success. installer/bin/zepos-install carries the same
    finding in its own docstring and watches the same hook for the same
    reason - this is that mechanism, used as a test instrument.

WHAT IS FAKED AND WHAT IS NOT
    The three dependencies that touch hardware - the disk list, the
    wireless backend, the installer itself - are injected fakes, exactly
    as ZeposInstallerApp's constructor is built to allow. Everything
    else is the real thing: the real do_activate(), the real branding
    stylesheet, the real InstallerWindow, every page builder, every
    signal callback.

    branding.LOGO is repointed at the SVG in the checkout. It normally
    names a path only the zepos-installer-gui PACKAGE creates, and
    _logo() returns None when the file is absent - so an unpatched run
    would skip the very branch that crashed on real hardware and report
    clean.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from installer.core import crypt  # noqa: E402
from installer.core.disks import Disk, Partition  # noqa: E402
from installer.core.wifi import Connection, Network  # noqa: E402
from installer.gui import app as gui_app  # noqa: E402
from installer.gui import branding  # noqa: E402
from installer.gui import pages as gui_pages  # noqa: E402

# How long the fake association takes. NOT zero, and that is a
# correctness requirement rather than realism.
#
# MEASURED with an instant fake: wireless_step() sets
# state.wifi_connected_to on the WORKER thread, before it hands the
# result back. A fake that returns immediately can therefore finish
# between the first click on Weiter and the second - and then the second
# click sees needs_association() == False, falls through to _step(1) and
# advances the page itself. Which of the two paths the run covers becomes
# a race: the double-click guard sometimes, the completion handler's
# _step(1) sometimes, neither reliably. A connect that takes a moment -
# as every real one does, iwctl blocks for seconds - makes both
# deterministic.
ASSOCIATE_SECONDS = 0.25


def _fake_associate(result: Connection):
    """installer.gui.pages.wireless_step() resolves the real
    installer.core.wifi.associate() when its caller passes none - and
    app.py's caller passes none, deliberately, so the surface cannot bind
    a fake by accident. That real function drives iwctl and opens a
    socket to check the route. Replacing the module-level name is the
    smallest fake that leaves wireless_step() itself,
    _start_wireless_step() and _on_wireless_finished() running for real.
    """
    def _associate(backend, ssid, passphrase, **kwargs) -> Connection:
        time.sleep(ASSOCIATE_SECONDS)
        return result

    gui_pages._iwd_associate = _associate


# Two, not one, and the second is what makes the difference:
# _build_datentraeger() pre-selects position 0 when it builds the row, so
# setting the combo to 0 emits no notify::selected and its callback -
# the one that decides WHICH disk gets erased - never runs. With a second
# disk there is a position to move to.
#
# Beide tragen Partitionen, und das ist nicht Ausschmueckung: die Seite
# "partitionierung" zaehlt sie auf, und die Rueckfrage vor dem Loeschen
# nennt sie beim Namen. Eine Platte ohne Partitionen laesst beide Listen
# leer und der Lauf wuerde beweisen, dass eine leere Liste nicht
# abstuerzt - nicht, dass die gefuellte richtig ist.
DISK = Disk(
    device="/dev/vda", size_bytes=40 * 1024**3,
    partitions=(
        Partition(device="/dev/vda1", size_bytes=512 * 1024**2,
                  fstype="vfat", label="SYSTEM"),
        Partition(device="/dev/vda2", size_bytes=39 * 1024**3,
                  fstype="ntfs", label="Windows"),
    ))
SECOND_DISK = Disk(
    device="/dev/vdb", size_bytes=120 * 1024**3,
    partitions=(
        Partition(device="/dev/vdb1", size_bytes=120 * 1024**3, fstype="ext4"),
    ))
# Below MIN_DISK_MIB, so PageState.usable_disks() drops it and
# _build_datentraeger() takes its Adw.StatusPage branch instead of
# building a combo row. That branch has its own widget call
# (group.add(status)) and is only reachable on a machine whose disks are
# all too small - i.e. never, on any developer's machine.
TINY_DISK = Disk(device="/dev/vdz", size_bytes=64 * 1024**2)


class FakeWifi:
    """installer.core.wifi.WifiBackend, without iwctl."""

    def __init__(self, networks: list[Network]) -> None:
        self._networks = networks

    def devices(self) -> list[str]:
        return ["wlan0"] if self._networks else []

    def scan(self, device: str) -> None:
        pass

    def networks(self, device: str) -> list[Network]:
        return list(self._networks)

    def connect(self, device: str, ssid: str, passphrase: str) -> Connection:
        return Connection(True, "")


def _walk(widget):
    """Every widget below one root, in tree order.

    Adw rows put their content inside containers of their own, so the
    rows the page builders added are not direct children of anything
    this file holds a reference to. A generic walk is how a driver
    reaches them without app.py having to expose them.
    """
    child = widget.get_first_child()
    while child is not None:
        yield child
        yield from _walk(child)
        child = child.get_next_sibling()


def _drive_inputs(window) -> list[str]:
    """Fire every input callback app.py connected.

    Setting a value on a row emits the same signal a user's click or
    keystroke emits, so this runs the real _on_changed /
    _on_network_changed / _on_plugins_changed bodies - the code that
    reads a widget and writes into PageState. Those callbacks exist
    nowhere else and are executed by nothing else in this suite.
    """
    touched: list[str] = []
    for widget in _walk(window):
        if isinstance(widget, Adw.ComboRow):
            model = widget.get_model()
            count = model.get_n_items() if model is not None else 0
            # Only positions the model actually has: a ComboRow selection
            # past the end is not a user-reachable state, and
            # _build_datentraeger's callback indexes usable_disks with it.
            for position in range(count):
                widget.set_selected(position)
            touched.append(f"combo:{count}")
        elif isinstance(widget, Adw.EntryRow):
            # PasswordEntryRow is an EntryRow, so this covers both.
            widget.set_text("zepos-test")
            touched.append("entry")
        elif isinstance(widget, Adw.SwitchRow):
            widget.set_active(not widget.get_active())
            touched.append("switch")
    return touched


def _png_size(path: Path) -> tuple[int, int] | None:
    """Width and height out of a PNG's IHDR, without an image library.

    The first chunk of every PNG is IHDR and its first eight bytes are
    the two dimensions, big-endian. Reading them here rather than
    through GdkPixbuf keeps this check independent of the loader whose
    failure it is meant to detect.
    """
    try:
        header = path.read_bytes()[:24]
    except OSError:
        return None
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return (int.from_bytes(header[16:20], "big"),
            int.from_bytes(header[20:24], "big"))


def _check_logo(window, reached: list[str], failures: list[str]) -> None:
    """The wordmark is in the header, and what it shows is the wordmark.

    MEASURED, and it is the reason this does more than a None check:
    a picture built from a file GTK cannot decode is not None. Handed a
    corrupt image it used to come back as a perfectly valid widget
    carrying GTK's own 200x200 "image-missing" icon, and _logo() passed
    it on - so the installer showed a broken-image glyph where the brand
    belongs, and nothing raised, printed or returned anything to say so.

    The size is what separates the two. branding.WORDMARK is a PNG
    rendered at exactly the height the header asks for, so the picture's
    intrinsic size must equal the file's own - a substituted icon is
    square and fails on both numbers.

    Its presence also proves the header was built with a mark at all,
    rather than skipped because branding.WORDMARK named nothing.
    """
    # By its style class, not "the first picture in the window": the
    # window now also carries the backdrop, which is a Gtk.Picture too
    # and comes first in the walk because it is painted first. Taking
    # the first one measured the ground and called it the wordmark.
    picture = next((w for w in _walk(window)
                    if isinstance(w, Gtk.Picture)
                    and "wizard-mark" in w.get_css_classes()), None)
    if picture is None:
        failures.append(
            "no Gtk.Picture in the window - the wizard header has no "
            "wordmark, so this run proves nothing about the branch that "
            "crashed the shipping ISO")
        return
    paintable = picture.get_paintable()
    if paintable is None:
        failures.append(
            "the wordmark widget carries no image at all: the file at "
            "branding.WORDMARK is empty or unreadable")
        return
    size = (paintable.get_intrinsic_width(), paintable.get_intrinsic_height())
    declared = _png_size(branding.WORDMARK)
    if declared is None:
        failures.append(f"{branding.WORDMARK} is not a PNG this can read")
        return
    if size != declared:
        failures.append(
            f"the wordmark rendered at {size[0]}x{size[1]} while "
            f"{branding.WORDMARK.name} is {declared[0]}x{declared[1]} - "
            "GTK substituted its image-missing icon, so the installer "
            "would show a broken-image glyph where the brand is")
        return
    if declared[1] != branding.MARK_HEIGHT:
        failures.append(
            f"{branding.WORDMARK.name} is {declared[1]} pixels high but "
            f"the header asks for {branding.MARK_HEIGHT}; "
            "the picture cannot shrink, so the header is the wrong size")
        return
    reached.append(f"logo:{size[0]}x{size[1]}")


def _drive_wireless(window, reached: list[str], failures: list[str]) -> bool:
    """Choose a network, type a passphrase, press Weiter.

    The one user path that leaves the main thread before anything is
    installed: _start_wireless_step() shows a toast, spawns a worker and
    only lets the page be left once _on_wireless_finished() comes back
    through GLib.idle_add. Nothing reaches it unless a network is
    actually selected - the combo defaults to "Ueberspringen" - so a
    driver that only clicks Weiter walks straight past it.

    Returns False when there is no network page to drive (the "no-disks"
    mode scans nothing, and PageState.should_skip() then removes the
    page from the walk entirely).
    """
    try:
        page = window.stack.get_child_by_name("netzwerk")
        if page is None or window.state.should_skip("netzwerk"):
            return False
        combo = next(w for w in _walk(page) if isinstance(w, Adw.ComboRow))
        entry = next(w for w in _walk(page) if isinstance(w, Adw.PasswordEntryRow))
        combo.set_selected(0)
        entry.set_text("geheimgenug")

        window.index = gui_app.PAGE_ORDER.index("netzwerk")
        window._sync()
        assert window.state.needs_association(), (
            "the wireless page was filled in but the state does not "
            "consider an association necessary - the worker path this "
            "phase exists to reach would be skipped")
        window.forward.emit("clicked")
        # Immediately again, which is the bug _start_wireless_step()'s
        # docstring records: a keystroke in the passphrase field
        # re-enabled the button mid-connect, the second click started a
        # second worker, and the two completions advanced TWO pages -
        # past the disk page, whose combo row has already pre-selected a
        # disk to erase. PageState.begin_wireless_step() is the gate that
        # refuses the second one, and this is what asks it to.
        window.forward.emit("clicked")
        reached.append("wireless-started")
    except BaseException as exc:                            # noqa: BLE001
        failures.append(f"{type(exc).__name__}: {exc}")
        return False
    return True


def _click_until(button, window, target: str) -> str:
    """Press one footer button until the stack shows `target`.

    Counted rather than fixed, because PageState.should_skip() removes
    the network page from the walk when nothing was scanned - a fixed
    number of clicks would overshoot into the confirmation dialog in one
    mode and stop short in the other.
    """
    for _click in range(len(gui_app.PAGE_ORDER) + 1):
        if window.stack.get_visible_child_name() == target:
            break
        button.emit("clicked")
    return window.stack.get_visible_child_name()


def _answer_confirmation(window, answer: str) -> str:
    """Press Ja or Nein on the erase dialog. "" heisst: hat geklappt.

    The dialog is the point of no return and its handler is where the
    installation actually starts: choose_finish() reads the answer, "ja"
    calls _run_installation(), anything else raises a toast. None of that
    is reachable by calling a method - Adw.AlertDialog.choose() only
    completes when a response is activated - so the dialog is found in
    the widget tree and answered, which is what a click does.

    MEASURED, because the obvious spelling does not work:
    adw_alert_dialog_response() IS listed as a method in Adw-1.gir, and
    PyGObject still does not expose it as dialog.response() - the type
    has a SIGNAL of the same name, and the signal wins. The method is
    reachable only as do_response(), and emitting the signal is what the
    C function does anyway. (This is one of the cases the static guard in
    tests/installer/gir_types.py cannot see; see its docstring.)
    """
    dialog = next(
        (w for w in _walk(window)
         if isinstance(w, Adw.AlertDialog) and w.has_response("yes")),
        None)
    if dialog is None:
        return ("the last press of Weiter presented no erase dialog - "
                "the confirmation before the point of no return is not there")
    # Was der Text nennt, bevor er beantwortet wird. Eine Rueckfrage, die
    # nur "die ganze Platte" sagt, ist die, die man bestaetigt, waehrend
    # man an eine andere Platte denkt - deshalb muss jede vorhandene
    # Partition mit ihrer Bezeichnung darin stehen und jede geplante mit
    # ihrer Groesse. Hier gelesen und nicht im Test, weil Adw.AlertDialog
    # ausserhalb dieses Kindprozesses nicht existiert.
    body = dialog.get_body()
    for partition in window.state.device_partitions:
        if partition.device not in body:
            return f"die Rueckfrage nennt {partition.device} nicht: {body!r}"
        if partition.label and partition.label not in body:
            return (f"die Rueckfrage nennt die Bezeichnung "
                    f"{partition.label!r} nicht: {body!r}")
    for planned in window.state.layout:
        if planned.filesystem not in body:
            return (f"die Rueckfrage nennt nicht, dass "
                    f"{planned.filesystem} angelegt wird: {body!r}")
    dialog.emit("response", answer)
    return ""



def _pump() -> None:
    """Let the main loop run once.

    Adw.AlertDialog.choose() presents on an idle callback, so the dialog
    does not exist on the line after _finish() was called. Nothing here
    may block waiting for it - the loop that would create it is this
    one.
    """
    context = GLib.MainContext.default()
    while context.pending():
        context.iteration(False)
    time.sleep(0.01)


def _answer_completion(window, reached, failures, answer: str) -> None:
    """Press "Restart now" on the dialog that ends the installation.

    THE HOLE THIS COVERS: the installer had no ending. Back and Next are
    switched off when the erase begins and were never switched on again,
    so a FINISHED installation left the only way out as the power
    switch - reported from the medium as "jetzt wo die installation
    abgeschlossen ist ... geht es nicht mehr weiter".

    The dialog is found by a response only it has, so it cannot be
    confused with the erase confirmation, and the response is emitted -
    which is what a click does. See _answer_confirmation for why
    emitting the signal is the only way in.
    """
    if answer != "yes":
        return          # nothing was installed, so nothing ended
    for _attempt in range(200):
        dialog = next(
            (w for w in _walk(window)
             if isinstance(w, Adw.AlertDialog) and w.has_response("restart")),
            None)
        if dialog is not None:
            dialog.emit("response", "restart")
            reached.append("restart-pressed")
            return
        _pump()
    failures.append(
        "the installation finished and offered no way onwards - no dialog "
        "with a restart response ever appeared")


def _check_plan_rows(window, failures: list[str], when: str) -> None:
    """So viele Zeilen auf der Seite wie geplante Partitionen.

    Gezaehlt wird, was WIRKLICH in der Gtk.ListBox haengt, und nicht die
    Liste, die app.py dafuer mitfuehrt. Die beiden koennen auseinander
    laufen, und genau dann sieht der Nutzer eine Partition doppelt: ein
    _refresh_partitioning(), das self._plan_rows leert, ohne die Zeilen
    vorher aus der Liste zu nehmen, haengt beim naechsten Aufbau
    einfach weitere daneben. Gemessen im Mutationslauf zu dieser
    Aufgabe - gegen window._plan_rows gezaehlt blieb das unsichtbar.
    """
    rows = [w for w in _walk(window._plan_list) if isinstance(w, Adw.ActionRow)]
    if len(rows) != len(window.state.layout):
        failures.append(
            f"{when}: {len(rows)} Zeilen in der Liste fuer "
            f"{len(window.state.layout)} geplante Partitionen")


def _drive_partitioning(window, reached: list[str], failures: list[str]) -> None:
    """Die Platte bereinigen und von Hand neu einteilen.

    Genau der Weg, den der Nutzer verlangt hat ("bereinigen koennen und
    neu zuweisen mit partitionen"), gegangen ueber die echten
    Bedienelemente: der Knopf wird geklickt, die Auswahlfelder werden
    gesetzt, die Eingabezeile wird beschrieben. Alles, was dabei laeuft -
    _on_clear_clicked, _on_mountpoint_changed, _on_size_changed,
    _on_add_partition_clicked, _on_remove_partition_clicked,
    _refresh_partitioning - ist Code in app.py, den sonst nichts
    ausfuehrt.

    Die drei Zwischenzustaende, auf die es ankommt, werden einzeln
    geprueft, weil jeder von ihnen fuer sich eine Zusicherung ist:

      * nach dem Bereinigen ist die Einteilung leer, der Weiter-Knopf
        tot und der Grund steht auf der Seite;
      * eine Groesse ohne Einheit wird abgelehnt und sagt warum;
      * eine Groesse, die nicht mehr hineinpasst, wird abgelehnt und
        sagt, wie viel noch frei ist.

    Am Ende steht eine von Hand gebaute, gueltige Einteilung - der Rest
    des Laufs installiert sie, sodass auch der Weg vom Formular bis in
    die archinstall-Konfiguration einmal ganz gegangen wird.
    """
    if not window.usable_disks:
        # Der "no-disks"-Lauf. Ohne gewaehlte Platte ist die Plattengroesse
        # 0, und jede Groesse, die dieser Treiber eintippt, passt zu Recht
        # nicht hinein. Die Seite selbst wird trotzdem gebaut und beim
        # Durchklicken angezeigt - was hier fehlt, ist nur der Treiber.
        reached.append("part:no-disk")
        return
    try:
        window.index = gui_app.PAGE_ORDER.index("partitionierung")
        window._sync()
        reached.append(f"part:start:{len(window.state.layout)}")
        if len(window._existing_rows) != len(window.state.device_partitions):
            failures.append(
                "die vorhandene Einteilung wird nicht angezeigt: "
                f"{len(window._existing_rows)} Zeilen fuer "
                f"{len(window.state.device_partitions)} Partitionen")
        if not window._existing_heading.get_text():
            failures.append(
                "ueber der vorhandenen Einteilung steht nicht, dass sie "
                "geloescht wird")

        # Bereinigen. Danach ist nichts geplant, und das muss die Seite
        # sagen statt es durchzulassen.
        window._partition_clear.emit("clicked")
        if window.state.layout:
            failures.append("Bereinigen hat die Einteilung nicht geleert")
        _check_plan_rows(window, failures, "nach dem Bereinigen")
        if window.forward.get_sensitive():
            failures.append(
                "eine leere Einteilung laesst den Weiter-Knopf zu - "
                "wipe=True ohne Partitionen loescht die Platte und legt "
                "nichts an")
        if not window._error_labels["partitionierung"].get_text():
            failures.append(
                "die leere Einteilung wird abgelehnt, aber die Seite sagt "
                "nicht warum")
        reached.append("part:cleared")

        # Eine Groesse ohne Einheit. "20" ist auf dieser Seite nicht
        # eindeutig, und der Unterschied zwischen 20 MiB und 20 GiB faellt
        # sonst erst am installierten System auf.
        window._size_row.set_text("20")
        window._partition_add.emit("clicked")
        if window.state.layout:
            failures.append("eine Groesse ohne Einheit wurde angenommen")
        if not window._size_error.get_text():
            failures.append(
                "eine Groesse ohne Einheit wird abgelehnt, ohne einen "
                "Grund neben der Eingabezeile zu nennen")
        reached.append("part:unit-refused")

        # Die EFI-Systempartition von Hand.
        esp_index = gui_app.MOUNTPOINT_CHOICES.index(gui_app.ESP_MOUNTPOINT)
        window._mountpoint_row.set_selected(esp_index)
        if window._filesystem_row.get_sensitive():
            failures.append(
                "das Dateisystem der EFI-Systempartition steht zur Wahl - "
                "die Firmware liest nur FAT, jede andere Wahl waere eine "
                "Eingabe, die still verworfen wird")
        window._size_row.set_text("512M")
        window._partition_add.emit("clicked")
        if len(window.state.layout) != 1:
            failures.append(
                f"die ESP wurde nicht angelegt: {window.state.layout}")
            return
        if not window.state.layout[0].is_esp():
            failures.append(
                "die angelegte Partition traegt die ESP-Flaggen nicht - "
                "archinstalls get_efi_partition() findet sie dann nicht "
                "und add_bootloader() bricht ab")
        reached.append("part:esp")

        # Mehr, als noch frei ist.
        window._mountpoint_row.set_selected(
            gui_app.MOUNTPOINT_CHOICES.index("/home"))
        window._size_row.set_text("999T")
        window._partition_add.emit("clicked")
        if len(window.state.layout) != 1:
            failures.append(
                "eine Partition groesser als die Platte wurde angenommen")
        if "999" not in window._size_error.get_text():
            failures.append(
                "die zu grosse Groesse wird abgelehnt, ohne sie zu nennen: "
                f"{window._size_error.get_text()!r}")
        reached.append("part:too-large")

        # /home, damit es etwas zu entfernen gibt - und damit der Weg
        # ueber _on_remove_partition_clicked einmal gegangen wird.
        window._size_row.set_text("4G")
        window._partition_add.emit("clicked")
        if len(window.state.layout) != 2:
            failures.append(f"/home wurde nicht angelegt: {window.state.layout}")
            return
        buttons = [w for w in _walk(window._plan_list)
                   if isinstance(w, Gtk.Button)]
        if not buttons:
            failures.append(
                "keine geplante Partition hat einen Knopf zum Entfernen")
            return
        # Der LETZTE, also der von /home. Die Zeilen stehen in der
        # Reihenfolge der Platte, und der erste Knopf gehoert zur ESP -
        # die zu entfernen wuerde die Einteilung ungueltig machen und
        # damit die Zusicherung am Ende dieser Funktion beantworten,
        # statt sie zu stellen.
        before = list(window.state.layout)
        buttons[-1].emit("clicked")
        if len(window.state.layout) != len(before) - 1:
            failures.append(
                f"Entfernen hat nichts entfernt: {window.state.layout}")
        if any(p.mountpoint == "/home" for p in window.state.layout):
            failures.append(
                "Entfernen hat die falsche Partition getroffen - /home "
                f"steht noch in {window.state.layout}")
        # SOFORT, nicht erst am Ende. Jede weitere Aenderung baut die
        # Liste ohnehin neu auf und wuerde eine Zeile, die nach dem
        # Entfernen stehengeblieben ist, wieder wegraeumen - gemessen im
        # Mutationslauf zu dieser Aufgabe: ein _on_remove_partition_
        # clicked() ohne _refresh_partitioning() kam so durch.
        _check_plan_rows(window, failures, "nach dem Entfernen")
        reached.append("part:removed")

        # Ein Sprachwechsel mittendrin. Zwei der Eintraege im
        # Auswahlfeld sind uebersetzte Saetze, das Modell wird dafuer neu
        # gebaut - und set_model() setzt die Auswahl auf 0. Wer hier
        # gerade /home eingestellt hatte, haette danach die
        # EFI-Systempartition im Formular stehen und wuerde es nicht
        # merken.
        chosen = window.state.new_mountpoint
        language = next(
            w for w in _walk(window.stack.get_child_by_name("sprache"))
            if isinstance(w, Adw.ComboRow))
        language.set_selected(1 if language.get_selected() == 0 else 0)
        if window.state.new_mountpoint != chosen:
            failures.append(
                "der Sprachwechsel hat den Einhaengepunkt im Formular von "
                f"{chosen!r} auf {window.state.new_mountpoint!r} gestellt")
        if (gui_app.MOUNTPOINT_CHOICES[window._mountpoint_row.get_selected()]
                != chosen):
            failures.append(
                "nach dem Sprachwechsel zeigt das Auswahlfeld etwas "
                "anderes an, als der Zustand sagt")
        reached.append("part:language-kept")

        # Und die Wurzel ueber den ganzen Rest.
        window._mountpoint_row.set_selected(gui_app.MOUNTPOINT_CHOICES.index("/"))
        window._size_row.set_text("rest")
        window._partition_add.emit("clicked")
        if window._error_labels["partitionierung"].get_text():
            failures.append(
                "eine Einteilung aus ESP und Wurzel wird abgelehnt: "
                + window._error_labels["partitionierung"].get_text())
        if not window.forward.get_sensitive():
            failures.append(
                "eine gueltige Einteilung laesst den Weiter-Knopf nicht zu")
        _check_plan_rows(window, failures, "am Ende")
        reached.append(f"part:planned:{len(window.state.layout)}")
    except BaseException as exc:                            # noqa: BLE001
        failures.append(f"{type(exc).__name__}: {exc}")
    finally:
        window.index = 0
        window._sync()


def _tab_stops(window, page: str) -> list[str]:
    """Die Halte, die die Tabulatortaste auf einer Seite findet, gemessen
    am gebauten Widget-Baum.

    WARUM DAS HIER STEHT UND NICHT IN test_gui.py
        Weil es sich nur an einem gebauten Fenster messen laesst. Welche
        Bedienelemente die Tabulatortaste anspringt, entscheidet
        libadwaita aus dem fertigen Baum: eine Adw.PasswordEntryRow
        bringt einen Knopf zum Sichtbarmachen mit, und der ist ein Halt;
        ein Gtk.Label ist keiner. Nichts davon steht in
        installer/gui/app.py, und nichts davon laesst sich aus dem
        Quelltext ablesen.

    WOFUER DIE ZAHL GEBRAUCHT WIRD
        iso/test-boot.py's RELEASE_INSTALL_SCRIPT ist eine feste Folge
        von Tastendruecken, und wie viele Tabulatoren eine Seite braucht,
        steht darin ausgeschrieben. Am 11.08.2026 hat genau so eine Zahl
        - eine Seite, die dazukam, ohne dass das Skript davon wusste -
        einen Lauf mit rc=0 und 0,0 GiB beendet. Eine im Kommentar
        gezaehlte Kette ist eine Behauptung; das hier ist eine Messung.

    GEZAEHLT UND NICHT ABGELAUFEN, und das ist gemessen: der naechstliegende
    Weg - set_focus(None), dann window.child_focus(TAB_FORWARD) in einer
    Schleife - liefert an diesem Fenster genau EINEN Halt (ein AdwGizmo)
    und bricht dann ab. GTK laeuft die Kette nur an einem dargestellten
    Fenster ab, und broadwayd stellt hier nichts dar. Was sich verlaesslich
    messen laesst, ist die Eigenschaft, aus der GTK die Kette bildet:
    welche Widgets der Seite fokussierbar SIND, in Baumreihenfolge.
    """
    child = window.stack.get_child_by_name(page)
    return [
        type(widget).__name__ for widget in _walk(child)
        if widget.get_focusable() and widget.get_visible()
    ]


# Die Bedienelemente der Benutzerseite und der Verschluesselungsseite, so
# wie _tab_stops() sie am gebauten Fenster vorfindet. Gemessen am
# 12.08.2026 gegen gtk4-broadwayd auf dieser Maschine.
#
# WOFUER DAS GUT IST - UND WARUM DIE BENUTZERSEITE MITGEMESSEN WIRD,
# OBWOHL SIE SICH NICHT GEAENDERT HAT
#     Die Benutzerseite ist der EICHPUNKT. Ihre echte Tabulatorkette ist
#     an einer laufenden Maschine gemessen und in iso/test-boot.py
#     ausgeschrieben: zwoelf Halte, davon zehn auf der Seite selbst
#     (1 Rechnername, 2 Benutzername, 3 Passwort, 4 Auge, 5 wiederholen,
#     6 Auge, 7 Root, 8 Auge, 9 wiederholen, 10 Auge) und zwei im
#     Fussbereich.
#
#     Aus diesen zehn und den 24 Widgets unten folgt die Umrechnung, die
#     hier ueberhaupt erst brauchbar macht, was diese Datei messen kann:
#
#         Adw.EntryRow         -> EntryRow|Text|Button           = 1 Halt
#         Adw.PasswordEntryRow -> PasswordEntryRow|Text|Button|Button
#                                                                = 2 Halte
#
#     Probe: 2 * 1 + 4 * 2 = 10. Das ist genau die gemessene Zahl.
#
#     Die Verschluesselungsseite bringt eine Adw.SwitchRow dazu, die als
#     SwitchRow|Switch erscheint - dieselbe Form wie eine EntryRow ohne
#     ihren Text und ohne ihren Knopf, also ein Halt. Damit sind es dort
#     1 + 2 + 2 = 5 Halte auf der Seite, und genau diese fuenf sind es,
#     die RELEASE_INSTALL_SCRIPT durchtabuliert.
#
#     Was diese beiden Listen also halten, ist die GRUNDLAGE der
#     Tastendruckfolge. Wenn libadwaita seine Zeilen anders baut, aendert
#     sich hier eine Liste - und nicht erst ein Installationslauf, der
#     eine Passphrase in das falsche Feld tippt.
BENUTZER_WIDGETS = [
    "ScrolledWindow", "ListBox",
    "EntryRow", "Text", "Button",
    "EntryRow", "Text", "Button",
    "PasswordEntryRow", "Text", "Button", "Button",
    "PasswordEntryRow", "Text", "Button", "Button",
    "PasswordEntryRow", "Text", "Button", "Button",
    "PasswordEntryRow", "Text", "Button", "Button",
]
VERSCHLUESSELUNG_WIDGETS = [
    "ScrolledWindow", "ListBox",
    "SwitchRow", "Switch",
    "PasswordEntryRow", "Text", "Button", "Button",
    "PasswordEntryRow", "Text", "Button", "Button",
]


def _check_tab_chain(window, reached: list[str], failures: list[str]) -> None:
    """Die Bedienelemente beider Seiten gegen die gemessenen Listen.

    Der Eichpunkt zuerst: stimmt die Benutzerseite nicht mehr, dann
    stimmt die Umrechnung nicht mehr, und dann sagt die zweite Pruefung
    nichts. Deshalb sind es zwei Vergleiche und nicht einer.
    """
    for page, expected in (("benutzer", BENUTZER_WIDGETS),
                           ("verschluesselung", VERSCHLUESSELUNG_WIDGETS)):
        found = _tab_stops(window, page)
        if found != expected:
            failures.append(
                f"die Bedienelemente der Seite '{page}' sind nicht mehr die "
                f"gemessenen. RELEASE_INSTALL_SCRIPT in iso/test-boot.py "
                f"zaehlt Tabulatoren nach genau dieser Liste und wuerde "
                f"seine Eingaben in die falschen Felder tippen.\n"
                f"    erwartet: {'|'.join(expected)}\n"
                f"    gefunden: {'|'.join(found)}")
        reached.append(f"chain:{page}:{len(found)}")


def _check_encryption(window, reached: list[str], failures: list[str]) -> None:
    """Die Verschluesselungsseite, ueber ihre echten Bedienelemente.

    WAS HIER GEPRUEFT WIRD, UND WARUM JEDES EINZELNE
        Der eine Fehler, der bei dieser Seite zaehlt, ist nicht "der
        Haken laesst sich nicht setzen". Er ist: der Haken steht, die
        Passphrase fehlt oder passt nicht zusammen, und der Assistent
        laesst es durch. archinstall wuerde daraus eine Installation mit
        Rueckgabewert 0 und einer unverschluesselten Platte machen
        (DiskEncryption.parse_arg gibt ohne Passwort None zurueck), und
        niemand saehe es.

        Deshalb wird jeder unfertige Zustand einzeln angefahren und
        jedesmal verlangt, dass der Weiter-Knopf TOT ist und die Seite
        sagt, warum.

      * Haken an, Felder leer          -> tot, mit Begruendung
      * zu kurz                        -> tot, mit Begruendung
      * beide Felder verschieden       -> tot, mit Begruendung
      * beide gleich und lang genug    -> frei
      * Haken aus                      -> frei, auch mit leeren Feldern

    UND DIE WARNUNG. Sie ist der Grund, aus dem diese Seite mehr ist als
    ein Schalter: wer die Passphrase verliert, verliert die Daten. Dass
    der Satz auf der Seite STEHT, wird hier verlangt - eine Warnung, die
    nur in einer Funktion existiert, die niemand aufruft, ist keine.
    """
    try:
        window.index = gui_app.PAGE_ORDER.index("verschluesselung")
        window._sync()

        # Der Haken wird hier GESETZT und nicht geprueft. Dass die Vorgabe
        # "an" ist, gehoert zu PageState und steht in
        # tests/installer/test_gui.py; an dieser Stelle im Lauf hat
        # _drive_inputs() schon jeden Schalter des Fensters einmal
        # umgelegt, um seine Rueckrufe auszuloesen.
        window.state.encrypt = True
        window._refresh_encryption()

        warning = window._encryption_warning.get_text()
        if not warning:
            failures.append(
                "auf der Verschluesselungsseite steht keine Warnung - wer "
                "die Passphrase verliert, verliert die Daten, und das muss "
                "dastehen, bevor jemand weiterklickt")
        elif warning != crypt.loss_warning():
            failures.append(
                "die Warnung auf der Seite ist nicht die aus "
                "installer.core.crypt.loss_warning() - zwei Formulierungen "
                "derselben Warnung sind zwei, die auseinanderlaufen")
        if not window._encryption_notes.get_text():
            failures.append(
                "die Seite sagt nichts darueber, was die Verschluesselung "
                "im Betrieb kostet")
        reached.append("crypt:warned")

        for passphrase, confirm, why in (
            ("", "", "leere Felder"),
            ("kurz", "kurz", "eine zu kurze Passphrase"),
            ("langgenug1234", "langgenug1235", "zwei verschiedene Eingaben"),
        ):
            window.state.encryption_passphrase = passphrase
            window.state.encryption_passphrase_confirm = confirm
            window._refresh_validation()
            if window.forward.get_sensitive():
                failures.append(
                    f"{why} laesst den Weiter-Knopf zu - archinstall "
                    "installiert daraus eine unverschluesselte Platte und "
                    "meldet Erfolg")
            if not window._error_labels["verschluesselung"].get_text():
                failures.append(
                    f"{why} wird abgelehnt, ohne dass die Seite sagt warum")
        reached.append("crypt:refused")

        window.state.encryption_passphrase = "langgenug1234"
        window.state.encryption_passphrase_confirm = "langgenug1234"
        window._refresh_validation()
        if not window.forward.get_sensitive():
            failures.append(
                "eine gueltige Passphrase laesst den Weiter-Knopf nicht zu: "
                + window._error_labels["verschluesselung"].get_text())
        reached.append("crypt:accepted")

        # Und der Weg ohne Verschluesselung. Er muss offen bleiben - eine
        # Vorgabe, die sich nicht abwaehlen laesst, ist keine Vorgabe.
        window.state.encrypt = False
        window.state.encryption_passphrase = ""
        window.state.encryption_passphrase_confirm = ""
        window._refresh_encryption()
        window._refresh_validation()
        if not window.forward.get_sensitive():
            failures.append(
                "ohne Verschluesselung kommt der Assistent nicht weiter")
        if window._encryption_warning.get_text():
            failures.append(
                "die Warnung steht auch ohne Verschluesselung da - eine "
                "Warnung, die immer dasteht, wird nicht mehr gelesen")
        for row in window._passphrase_rows:
            if row.get_sensitive():
                failures.append(
                    "die Passphrasenfelder nehmen Eingaben entgegen, "
                    "obwohl nicht verschluesselt wird")
        reached.append("crypt:optional")

        # Zurueck in den Zustand, in dem der Rest des Laufs installiert:
        # verschluesselt, mit einer Passphrase. So geht auch der Weg von
        # dieser Seite bis in die archinstall-Konfiguration einmal ganz
        # durch.
        window.state.encrypt = True
        window.state.encryption_passphrase = "langgenug1234"
        window.state.encryption_passphrase_confirm = "langgenug1234"
        window._refresh_encryption()

        _check_tab_chain(window, reached, failures)
    except BaseException as exc:                            # noqa: BLE001
        failures.append(f"{type(exc).__name__}: {exc}")
    finally:
        window.index = 0
        window._sync()


def _check_wizard_header(window, reached: list[str], failures: list[str]) -> None:
    """The band above the page says where you are, and moves.

    A header that is built but never updated looks right in a
    screenshot of one page and is wrong on every other. So this walks
    the pages and requires the three things _sync_header() writes to
    change together: the step's name, its number, and the fraction of
    the rule that is filled.

    The fraction is the part worth holding. A counter that reads "3 of
    7" beside a bar that has not moved since the first page is the
    failure that looks like a working wizard.
    """
    # Driven through _step() and not the forward button. The button is
    # page-specific - on the wireless page it starts an association and
    # deliberately does not advance - and this is a check on
    # _sync_header(), which every page reaches through _sync(). The
    # button's own behaviour is covered by the walk in _drive().
    seen: list[tuple[str, str, float]] = []
    while True:
        seen.append((
            window._step_title.get_text(),
            window._step_counter.get_text(),
            round(window._progress.get_fraction(), 4),
        ))
        before = window.stack.get_visible_child_name()
        window._step(1)
        if window.stack.get_visible_child_name() == before:
            break
        if len(seen) > len(gui_app.PAGE_ORDER):
            break

    titles = [title for title, _c, _f in seen]
    counters = [counter for _t, counter, _f in seen]
    fractions = [fraction for _t, _c, fraction in seen]
    reached.append(f"header:{len(seen)}")

    if len(seen) < 2:
        failures.append(
            "the header was only ever read on one page, so nothing here "
            "says whether it follows the steps")
        return
    if not all(titles):
        failures.append(f"a step had no title in the header: {titles}")
    if not all(counters):
        failures.append(f"a step had no number in the header: {counters}")
    if len(set(counters)) != len(counters):
        failures.append(
            f"the step number repeats across pages: {counters} - it is "
            "not being updated by _sync_header()")
    if fractions != sorted(fractions) or fractions[0] == fractions[-1]:
        failures.append(
            f"the progress bar does not advance across the steps: {fractions}")

    # Back to where the walk started, so the caller finds the window
    # as it left it.
    while window.index > 0:
        window._step(-1)


def _drive(window, reached: list[str], failures: list[str], answer: str) -> None:
    """Walk the whole form the way the footer buttons walk it."""
    try:
        reached.append(f"start:{window.stack.get_visible_child_name()}")
        _check_logo(window, reached, failures)
        _check_wizard_header(window, reached, failures)
        reached.extend(_drive_inputs(window))
        # NACH _drive_inputs, das jedes Auswahlfeld durch alle Positionen
        # und jede Eingabezeile auf "zepos-test" setzt - auch die drei des
        # Partitionierungsformulars. Was dieser Treiber dort einstellt,
        # muss das Letzte sein, was eingestellt wurde.
        _drive_partitioning(window, reached, failures)
        # NACH der Partitionierung, weil die Seite aufzaehlt, was von
        # DIESER Einteilung im Klartext bleibt.
        _check_encryption(window, reached, failures)

        # The real callback chain: clicked -> _on_forward_clicked ->
        # _step -> _sync -> _refresh_validation. emit() rather than a
        # synthetic pointer event, and it deliberately ignores the
        # button's sensitivity: a page whose fields are incomplete must
        # still be buildable and drawable.
        reached.append(
            f"forward:{_click_until(window.forward, window, 'zusammenfassung')}")

        # Twice, because the second call is the one that goes through
        # Adw.PreferencesGroup.remove() on the rows the first added -
        # the path app.py's own comment records as having raised "tried
        # to remove non-child" once already.
        window._refresh_summary()
        window._refresh_summary()

        reached.append(f"back:{_click_until(window.back, window, 'sprache')}")
        # One more, on the first page, where there is nowhere to go back
        # to. _step() has a guard for it and nothing else asks for it.
        window.back.emit("clicked")
        if window.stack.get_visible_child_name() != "sprache":
            failures.append(
                "Zurueck on the first page moved somewhere - the guard "
                "in _step() for a target outside PAGE_ORDER did not hold")
        window._show_message("Kopf", "Rumpf")
        reached.append(
            f"again:{_click_until(window.forward, window, 'zusammenfassung')}")

        # Seeded before the dialog is answered, because "ja" starts the
        # installation immediately and _on_tick() begins reading this
        # file 250 ms later.
        window._log_path.parent.mkdir(parents=True, exist_ok=True)
        window._log_path.write_text("archinstall sagt etwas\n", encoding="utf-8")

        # One more press on the last page is _confirm_installation().
        window.forward.emit("clicked")
        problem = _answer_confirmation(window, answer)
        if problem:
            failures.append(problem)
            return
        reached.append(f"answered:{answer}")
        _answer_completion(window, reached, failures, answer)
    except BaseException as exc:                            # noqa: BLE001
        failures.append(f"{type(exc).__name__}: {exc}")


def _run_as_the_entry_point(reached: list[str], failures: list[str]) -> int:
    """installer/bin/zepos-install's own call, with nothing injected.

    Everything above builds ZeposInstallerApp directly with fakes, which
    is what makes the disks, the networks and the installation drivable
    - and which means the line the shipping medium actually executes,

        gui_main(gui_argv, on_window_shown=stop_watching)

    is executed by nothing. Its signature, and do_activate()'s
    resolution of IwctlBackend(), list_disks and install when no fake was
    passed, would first be tried in front of a user.

    Safe to run for real because the child's PATH is an empty directory:
    lsblk and iwctl are invoked by name, both raise FileNotFoundError,
    and both callers already treat that as "no disks" and "no networks"
    - which is also the only way to reach those two branches. Nothing
    installs anything: that needs the confirmation dialog answered.
    """
    def _shown() -> None:
        reached.append("window-shown")
        application = Gio.Application.get_default()
        if application is None:
            failures.append("no application object once the window was up")
            return
        window = application.get_windows()[0] if application.get_windows() else None
        if window is None:
            failures.append("the entry point's main() showed no window")
        else:
            reached.append(f"entry:{window.stack.get_visible_child_name()}")
        GLib.idle_add(application.quit)

    return gui_app.main([], on_window_shown=_shown)


def main(argv: list[str]) -> int:
    mode = argv[0]
    branding.LOGO = Path(argv[1])
    branding.WORDMARK = branding.LOGO.with_name('zepos-wordmark.png')
    branding.BACKDROP = branding.LOGO.with_name('zepos-backdrop.png')

    networks = [] if mode == "no-disks" else [
        Network(ssid="Fritz!Box 7590", signal=3, secured=True)
    ]
    disks = [TINY_DISK] if mode == "no-disks" else [DISK, SECOND_DISK]
    # A wrong wireless passphrase is the commonest thing that goes wrong
    # in front of this form, and it is the only way into
    # _on_wireless_finished()'s other two branches: the one that shows
    # the failure and the one that does NOT advance the page.
    _fake_associate(
        Connection(False, "Falsche Passphrase") if mode == "wireless-fails"
        else Connection(True, ""))
    # "nein" on the erase dialog raises a toast and installs nothing;
    # "ja" is the point of no return. Both are answers a user gives and
    # both are code in app.py.
    answer = "no" if mode == "no-disks" else "yes"

    reached: list[str] = []
    failures: list[str] = []

    # See the module docstring: run() returns 0 even when do_activate()
    # raised, so the hook is the channel that carries the failure.
    escaped: list[str] = []
    previous_hook = sys.excepthook

    def _capture(exc_type, exc_value, exc_tb) -> None:
        escaped.append(f"{exc_type.__name__}: {exc_value}")
        previous_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = _capture

    if mode == "entry-point":
        try:
            code = _run_as_the_entry_point(reached, failures)
        finally:
            sys.excepthook = previous_hook
        print(f"reached: {reached}")
        print(f"run: {code}")
        for problem in failures + escaped:
            print(f"FAILURE: {problem}")
        return 1 if (failures or escaped or code != 0) else 0

    app = gui_app.ZeposInstallerApp(
        wifi_backend=FakeWifi(networks),
        list_disks=lambda *args, **kwargs: list(disks),
        install=lambda cfg, **kwargs: 0,
        # Records instead of rebooting the machine running the suite.
        # The restart is the last thing the installer does and the one
        # step nobody could take on the medium - it has to be executed
        # here or it is executed for the first time by a user.
        reboot=lambda cmd, **kwargs: (
            reached.append(f"reboot:{' '.join(cmd)}")
            or subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")),
        on_window_shown=lambda: reached.append("window-shown"),
    )

    def _finished(outcome) -> None:
        reached.append(f"outcome:{outcome.succeeded}")
        app.quit()

    def _after_activate() -> bool:
        windows = app.get_windows()
        if not windows:
            failures.append("do_activate() produced no window")
            app.quit()
            return GLib.SOURCE_REMOVE
        window = windows[0]
        # The wireless association runs on a worker thread, so the rest
        # of the drive has to wait for it rather than follow it directly.
        if _drive_wireless(window, reached, failures):
            _when(lambda: not window.state.wireless_busy,
                  lambda: _rest(window), "the wireless worker")
            return GLib.SOURCE_REMOVE
        return _rest(window)

    def _when(ready, then, what: str, deadline: list[float] | None = None) -> None:
        """Run `then` once `ready()` holds, polling the main loop.

        A worker thread hands its result back through GLib.idle_add, so
        the only way to observe it is to let the loop turn. Polling with
        a deadline rather than waiting on a lock: a lock held on the main
        thread would stop the very loop the result arrives on.
        """
        attempts = [0]

        def _poll() -> bool:
            if ready():
                then()
                return GLib.SOURCE_REMOVE
            attempts[0] += 1
            if attempts[0] > 400:                           # 20 s at 50 ms
                failures.append(f"{what} never reported back")
                app.quit()
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE

        GLib.timeout_add(50, _poll)

    def _rest(window) -> bool:
        # Wrapped BEFORE the drive, because the drive is what answers the
        # erase dialog and "ja" starts the installation on the spot.
        # Wrapped rather than replaced: the real handler still runs (it
        # stops the tick, fills the bar and shows the dialog), and only
        # then does the loop end.
        real_finished = window._on_installation_finished

        def _wrapper(outcome):
            try:
                result = real_finished(outcome)
            except BaseException as exc:                    # noqa: BLE001
                failures.append(f"{type(exc).__name__}: {exc}")
                result = GLib.SOURCE_REMOVE
            _finished(outcome)
            return result

        window._on_installation_finished = _wrapper
        _drive(window, reached, failures, answer)
        if failures:
            # A form that could not be walked cannot be installed from
            # either, and waiting out the worker timeout below would only
            # make a failing run slow.
            app.quit()
            return GLib.SOURCE_REMOVE
        if answer != "yes":
            # "Nein" installs nothing, so no worker is coming - but the
            # dialog's own handler has not run yet either. Adw's choose()
            # completes its task through an idle source at the DEFAULT
            # priority; quitting here outright ends the loop before the
            # handler that raises the cancelled toast. A LOW-priority
            # idle is dispatched after it, which is the difference
            # between covering that branch and only appearing to.
            GLib.idle_add(app.quit, priority=GLib.PRIORITY_LOW)
            return GLib.SOURCE_REMOVE
        # A hard stop, so a worker that never comes back is a failed test
        # rather than a hung suite.
        GLib.timeout_add_seconds(20, _give_up)
        return GLib.SOURCE_REMOVE

    def _give_up() -> bool:
        failures.append("the installation worker never reported back")
        app.quit()
        return GLib.SOURCE_REMOVE

    GLib.idle_add(_after_activate)
    try:
        code = app.run([])
    finally:
        sys.excepthook = previous_hook

    print(f"reached: {reached}")
    print(f"run: {code}")
    for problem in failures + escaped:
        print(f"FAILURE: {problem}")
    return 1 if (failures or escaped or code != 0) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
