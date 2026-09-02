# SPDX-License-Identifier: GPL-3.0-or-later
"""GTK4/libadwaita surface.

Widgets only - every decision (what is valid, what the "next" button
should do, which page to show next) lives in pages.py and is only ever
read back here. A callback in this module may assign a value it just
read off a widget into a PageState field, or call one of PageState's own
methods and use the result to set a label's text or a button's
sensitivity - nothing more. That split exists so the logic can be
covered by tests/installer/test_gui.py, which needs no display at all: a
decision made inside a callback here could not be exercised there, and
would have to be rewritten wholesale if this surface were ever replaced
(which is exactly why installer.tui.app exists first).

The widgets themselves ARE executed now, which they were not when this
file was written and which is why a wrong argument type once reached the
shipping ISO. tests/installer/test_gui_headless.py builds this window
on gtk4-broadwayd and drives every page, every input callback, the
wireless worker and an installation; tests/installer/test_gui_widget_
types.py reads every GTK call here against GTK's own introspection data.
The split above still stands - a callback is still the worst place to
put a decision - but "no test can reach it" is no longer the reason.

Known limitation, deliberately not solved here: static chrome (page
titles, button labels, the timezone suggestion) is built once, in
whatever language is active when the window is constructed, and does
not retranslate itself if the user changes the language afterwards on
the "sprache" page. Dynamic content - every error message, the summary
page, the confirmation dialog - always reflects the current language,
because it is recomputed from pages.py on every sync, and PageState.
set_language() activates the chosen catalogue immediately. Rebuilding
already-constructed static widgets on a language change would need a
mechanism of its own (rebuild-in-place or an application restart) that
cannot be verified without a display; left as a follow-up rather than
guessed at here.
"""
from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Sequence

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, GLib, Gtk, Pango  # noqa: E402

from installer.core.disks import (  # noqa: E402
    Disk, Partition, describe, describe_contents, human_size,
)
from installer.core.layout import (  # noqa: E402
    ESP_MOUNTPOINT, PlannedPartition,
)
from installer.core.crypt import accelerator_note  # noqa: E402
from installer.core.disks import list_disks as _lsblk_list_disks  # noqa: E402
from installer.core.firmware import firmware_problem  # noqa: E402
from installer.core.i18n import _, ngettext  # noqa: E402
from installer.core.model import MIN_DISK_MIB, InstallConfig  # noqa: E402
from installer.core import timezones  # noqa: E402
from installer.core.runner import install as _run_install  # noqa: E402
from installer.core.wifi import IwctlBackend, Network, WifiBackend  # noqa: E402

from . import branding  # noqa: E402
from .pages import (  # noqa: E402
    FILESYSTEM_CHOICES, MOUNTPOINT_CHOICES, PAGE_ORDER,
    SWAP_CHOICE, InstallationOutcome, LogTail, PageState, TerminalLog,
    confirmation_body, default_log_path, discover_networks, run_installation,
    wireless_step,
)

DiskLister = Callable[..., Sequence[Disk]]
# Keyword arguments included: run_installation() passes log_path and
# on_warning through to whatever installer was injected here.
Installer = Callable[..., int]

# Shown while the installation runs. Deliberately NOT part of PAGE_ORDER:
# it is not a step the user navigates to, it is where the window goes
# once there is no way back.
PROGRESS_PAGE = "installation"

# One label per page, built lazily (as callables, not plain strings) so
# each is evaluated no earlier than window construction - by then
# InstallerWindow.__init__ has already activated PageState's own default
# language, so these are shown in the same language the rest of the
# initial page content is.
PAGE_TITLES: dict[str, Callable[[], str]] = {
    "sprache": lambda: _("Select language"),
    "netzwerk": lambda: _("Network"),
    "datentraeger": lambda: _("Select installation disk"),
    "partitionierung": lambda: _("Partitioning"),
    "verschluesselung": lambda: _("Encryption"),
    "benutzer": lambda: _("User"),
    "zeit": lambda: _("Timezone"),
    "zepos": lambda: _("ZepOS Options"),
    "zusammenfassung": lambda: _("Summary"),
}


def _mountpoint_label(choice: str) -> str:
    """Der Eintrag im Auswahlfeld fuer einen Einhaengepunkt.

    Zwei der Eintraege sind keine Pfade, sondern Rollen, und beide
    brauchen ihren Namen: "/boot" allein sagt nicht, dass daraus die
    EFI-Systempartition wird, und die Auslagerung hat gar keinen Pfad.
    Alle uebrigen stehen als das da, was sie sind - ein Pfad ist in jeder
    Sprache derselbe Pfad.
    """
    if choice == ESP_MOUNTPOINT:
        return _("{mountpoint} (EFI system partition)").format(
            mountpoint=ESP_MOUNTPOINT)
    if choice == SWAP_CHOICE:
        return _("Swap (no mount point)")
    return choice


def _existing_subtitle(partition: Partition) -> str:
    """Dateisystem, Bezeichnung und Groesse einer vorhandenen Partition.

    Die Bezeichnung ist der Teil, der die Frage beantwortet. Eine Zeile
    "ntfs 465,8 GiB" ist eine Partition; "ntfs 'Windows' 465,8 GiB" ist
    die Platte, die gerade NICHT geloescht werden sollte.
    """
    parts = [partition.fstype or _("unknown")]
    if partition.label:
        parts.append(f"\N{LEFT DOUBLE QUOTATION MARK}{partition.label}"
                     f"\N{RIGHT DOUBLE QUOTATION MARK}")
    parts.append(human_size(partition.size_bytes))
    return " ".join(parts)


# WARUM DIES EINE MODULFUNKTION IST UND KEINE @staticmethod
#     Weil tests/installer/gir_types.py den ERSTEN Parameter jeder
#     Methode an den Basistyp ihrer Klasse bindet, ohne auf
#     @staticmethod zu sehen. `buffer` galt damit als
#     Adw.ApplicationWindow, und alle elf GtkTextBuffer-Aufrufe darin
#     wurden als Aufrufe gemeldet, die GTK ablehnen wuerde - gemessen am
#     12.08.2026, ausgeloest von genau dieser Funktion.
#
#     Den Pruefer zu aendern, damit eigener Code durchgeht, ist in
#     diesem Baum verboten (CLAUDE.md Regel 2), und es waere hier auch
#     der schlechtere Weg: die Funktion hat mit dem Fenster nichts zu
#     tun. Sie bekommt einen Puffer und einen Text und gibt nichts
#     zurueck - eine reine Rechnung, die zufaellig in einer Klasse
#     stand.
#
#     Die Luecke im Pruefer bleibt und ist gemeldet: jede @staticmethod
#     in einer Oberflaechendatei wuerde denselben Fehlalarm ausloesen.
def _replace_tail(buffer, rendered: str) -> None:
    """Nur die Zeilen ersetzen, die sich wirklich geaendert haben.

    Zeilenweise und nicht zeichenweise, weil ein Terminal in Zeilen
    denkt: pacman zeichnet EINE Zeile neu, nicht ein Zeichen in der
    Mitte. Ein zeichengenauer Vergleich faende dieselbe Stelle,
    braeuchte aber eine Position im Puffer, und die ist bei
    Mehrbytezeichen nicht dasselbe wie ein Index in der
    Zeichenkette - GtkTextBuffer zaehlt Zeichen, Python zaehlt
    ebenfalls Zeichen, aber die Umrechnung waere eine zweite Stelle,
    an der man sich irren kann.
    """
    alt = buffer.get_text(buffer.get_start_iter(),
                          buffer.get_end_iter(), False).split("\n")
    neu = rendered.split("\n")

    gleich = 0
    for links, rechts in zip(alt, neu):
        if links != rechts:
            break
        gleich += 1

    if gleich == len(alt) == len(neu):
        return

    # WO DER ZEILENUMBRUCH BLEIBT, und das ist der Grenzfall, den
    # ein Test gefangen hat.
    #
    # Steht der Loeschbeginn am ANFANG einer Zeile, liegt der
    # Umbruch der Zeile davor schon im Puffer - der Schwanz darf
    # dann keinen mitbringen. Endet der behaltene Teil dagegen am
    # PUFFERENDE (reines Anhaengen, die haeufigste Bewegung), traegt
    # die letzte Zeile keinen Umbruch, und er muss vorn an den
    # Schwanz. Ohne diese Unterscheidung wurde aus "a\nb" + "c" ein
    # "a\nbc" - zwei Zeilen zu einer verklebt.
    if gleich >= len(alt):
        start = buffer.get_end_iter()
        trenner = "\n" if alt and alt[-1] != "" else ""
    elif gleich:
        ok, start = buffer.get_iter_at_line(gleich)
        if not ok:
            start = buffer.get_end_iter()
        trenner = ""
    else:
        start = buffer.get_start_iter()
        trenner = ""

    # Nur loeschen, wenn es etwas zu loeschen gibt. Beim reinen
    # Anhaengen - dem haeufigsten Fall - liegt `start` schon am Ende,
    # und ein Loeschen der Laenge null waere zwar folgenlos, machte
    # aber die Zusicherung "Anhaengen faesst nichts an" unwahr. Eine
    # Zusicherung, die man nur ungefaehr meint, faengt spaeter nichts.
    ende = buffer.get_end_iter()
    if start != ende:
        buffer.delete(start, ende)
    schwanz = trenner + "\n".join(neu[gleich:])
    if schwanz:
        buffer.insert(buffer.get_end_iter(), schwanz)

class InstallerWindow(Adw.ApplicationWindow):
    """The whole installer flow, one Adw.PreferencesPage per PAGE_ORDER
    entry inside a Gtk.Stack, with a shared back/next footer.

    devices and networks are enumerated once, at construction, rather
    than freshly on every visit to their page: both list_disks() and a
    wireless scan are slow enough (real hardware I/O) that repeating
    them on every "back" and "forward" click would make the form feel
    unresponsive for no benefit - the set of disks or networks present
    at boot is what the installer runs against either way.
    """

    def __init__(
        self,
        app: Adw.Application,
        state: PageState,
        *,
        wifi_backend: WifiBackend,
        list_disks: DiskLister,
        install: Installer,
        reboot: Callable[..., subprocess.CompletedProcess] | None = None,
    ) -> None:
        super().__init__(application=app)
        # Injected like every other outside effect in this class, so the
        # headless test can press the button without rebooting the
        # machine running the suite.
        self._reboot = reboot or subprocess.run
        self.set_default_size(900, 640)
        self.state = state
        self.install = install
        self.wifi_backend = wifi_backend
        self.index = 0
        self._log_path = default_log_path()
        self._log_tail = LogTail(self._log_path)
        self._terminal = TerminalLog()
        self._shown = ""
        self._tick_id = 0

        # Activate the state's own current language before building a
        # single widget, so the static titles and labels built just
        # below start out in the same language PageState.language
        # already names - see PageState.set_language()'s docstring for
        # why this must happen immediately rather than lazily.
        self.state.set_language(self.state.language)

        # The window title AFTER the catalogue, not in the super() call
        # above. Measured on the first boot of the shipping medium: every
        # word on the screen was German and the title bar said "Install
        # ZepOS", because _() was evaluated while the argument list was
        # being built - which is before the line above ran, and therefore
        # before any catalogue existed.
        self.set_title(_("Install ZepOS"))

        # Asked once, here, and only assigned into the state - the same
        # marshalling every other callback in this module does. Whether
        # this machine started in UEFI mode is a fact about the hardware
        # that no answer can change, so PageState refuses every page while
        # it holds a refusal (see PageState.page_error()), and the user
        # reads it on the first page instead of after confirming an erase.
        # installer.core.runner.install() keeps checking it too, at the
        # last moment before the erase.
        self.state.firmware_error = firmware_problem()

        # Ebenso einmal hier und nur abgelegt: ob diese CPU AES in
        # Hardware kann, steht in /proc/cpuinfo, und pages.py fasst kein
        # Dateisystem an. Gemessen (siehe installer/core/crypt.py): mit
        # AES-NI 4820 MiB/s, ohne rund 500 - der Unterschied zwischen
        # "faellt nicht auf" und "eine schnelle SSD wird ausgebremst".
        self.state.accelerator_warning = accelerator_note()

        try:
            devices = list(list_disks())
        except (RuntimeError, FileNotFoundError):
            devices = []
        self.usable_disks = PageState.usable_disks(devices)

        self.state.wifi_networks = discover_networks(wifi_backend)

        # Set before any page is built: _build_netzwerk() populates
        # its list during construction and reads this on the way.
        self._populating = False

        # Every label that is written once at build time and would
        # otherwise keep the language it was built in. The module header
        # used to call this a known limitation and leave it; the medium
        # then showed a form that switched to English except for its
        # buttons and row titles, which is worse than not offering the
        # switch at all.
        #
        # A closure per label rather than a rebuild of the pages: the
        # disk page pre-selects a disk and the network page resets its
        # choice when it is built, so rebuilding would quietly undo
        # decisions the user had already made on later pages.
        self._retranslate: list[Callable[[], None]] = []

        # The chrome BEFORE the pages, although it is added to the
        # window after them. Building a page ends in a validation pass,
        # and validation decides whether "next" may be clicked - so a
        # page built before the footer exists reaches for a button that
        # is not there yet. Measured as AttributeError: 'InstallerWindow'
        # object has no attribute 'forward', on the network page, which
        # is the first page that refreshes validation while it is being
        # built.
        header = self._build_wizard_header()
        footer = self._build_footer()

        self.stack = Gtk.Stack()
        self._error_labels: dict[str, Gtk.Label] = {}
        self._summary_group = Adw.PreferencesGroup()
        self._summary_rows: list[Gtk.Widget] = []
        for name in PAGE_ORDER:
            self.stack.add_named(self._build_page(name), name)
        self.stack.add_named(self._build_progress_page(), PROGRESS_PAGE)

        titlebar = Adw.HeaderBar()
        mark = self._logo()
        if mark is not None:
            titlebar.set_title_widget(mark)

        # OUR close button, not the window manager's.
        #
        # The system one was reported as too small three times. Twice I
        # tried to grow it from the stylesheet - min-height and
        # min-width, then -gtk-icon-size - and on the medium it stayed
        # exactly the same size both times. Whatever libadwaita does to
        # that widget, this file does not win the argument from CSS.
        #
        # So it is replaced by an ordinary Gtk.Button, which takes the
        # size it is given because nothing else has an opinion about it.
        # The window keeps exactly one way to be closed, in the same
        # corner, doing the same thing.
        titlebar.set_show_end_title_buttons(False)
        close = Gtk.Button(icon_name="window-close-symbolic")
        close.add_css_class("wizard-close")
        close.set_valign(Gtk.Align.CENTER)
        self._tr(lambda: close.set_tooltip_text(_("Close")))
        # OUT of the keyboard order, which the window-manager button it
        # replaced also was.
        #
        # MEASURED: putting it in shifted every Tab stop in the window by
        # one. The next run of iso/test-boot.py filled the hostname with
        # what belonged in the username, left both passwords empty, and
        # sat on "the password is too short" while the driver pressed on
        # - an installation that wrote 0.0 GiB where the run before it
        # wrote 5.0. A person tabbing through the form would have hit the
        # same wall one field earlier every time.
        #
        # It stays reachable the way it always was: with the pointer, and
        # through the compositor.
        close.set_can_focus(False)
        close.set_focus_on_click(False)
        close.connect("clicked", lambda _b: self.close())
        titlebar.pack_end(close)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(titlebar)
        toolbar.add_top_bar(header)
        toolbar.set_content(self.stack)
        toolbar.add_bottom_bar(footer)

        # The backdrop is DRAWN, not styled.
        #
        # It was a CSS background-image on the window node, and that
        # works here: the image appears in every QEMU run of the medium.
        # On the machine this was built for it did not, four rebuilds in
        # a row, and no measurement available from here could say why.
        #
        # So the mechanism that might be failing is gone. A CSS
        # background can be lost to a theme loaded at a higher priority,
        # to a child widget painting its own ground over it, or to any
        # rule this file has never heard of. A picture placed behind the
        # content in an overlay is none of those things - it is a widget,
        # drawn before its siblings, and the only way to lose it is to
        # not create it.
        canvas: Gtk.Widget = toolbar
        backdrop = self._backdrop()
        if backdrop is not None:
            overlay = Gtk.Overlay()
            overlay.set_child(backdrop)     # painted first, so behind
            overlay.add_overlay(toolbar)    # and everything else on top
            canvas = overlay

        self.toasts = Adw.ToastOverlay()
        self.toasts.set_child(canvas)
        self.set_content(self.toasts)

        self._sync()

    # --- chrome -------------------------------------------------------

    def _build_wizard_header(self) -> Gtk.Widget:
        """The band above every page: which step this is, and how far in.

        Always the same shape, so that moving between pages moves the
        content and nothing else. What changes is the three things
        _sync() writes into it - the step's name, its number, and how
        much of the rule is filled.

        The wordmark sits at the top, centred, exactly where the boot
        menu puts it - the installer is seen a minute after that menu,
        and the same mark in the same place is what says it is still the
        same system. It is on EVERY page rather than only the first,
        which is what makes it chrome rather than a splash.

        Under it, the bar: light petrol for the track, brand yellow for
        the part that has been done. Yellow is the active thing in this
        system - the selected entry of the boot menu is yellow, so the
        steps taken are too.
        """
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        header.add_css_class("wizard-header")

        # The name under the mark, as the boot menu writes it: Roboto
        # Light, wide-tracked, the same share of the screen. The mark
        # itself sits in the title bar above this, which is where the
        # menu puts it too - so the two screens open with the same two
        # lines in the same order.
        name = Gtk.Label(label="ZepOS")
        name.add_css_class("wizard-name")
        header.append(name)

        # Everything below the wordmark lives in one column, and the
        # column is the boot menu's: theme.txt puts boot_menu, the
        # countdown label and its bar at left = 19% with width = 62%,
        # so the menu is a 62%-wide strip centred on the screen. The
        # installer used the whole width, which is why the two screens
        # did not read as one even with the same picture behind them.
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        column.add_css_class("wizard-column")
        column.set_halign(Gtk.Align.CENTER)

        line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        self._step_title = Gtk.Label(label="")
        self._step_title.add_css_class("wizard-title")
        self._step_title.set_xalign(0)
        self._step_title.set_hexpand(True)
        self._step_title.set_ellipsize(Pango.EllipsizeMode.END)
        line.append(self._step_title)

        self._step_counter = Gtk.Label(label="")
        self._step_counter.add_css_class("wizard-step")
        self._step_counter.set_valign(Gtk.Align.CENTER)
        line.append(self._step_counter)

        column.append(line)

        self._progress = Gtk.ProgressBar()
        self._progress.add_css_class("wizard-progress")
        self._progress.set_hexpand(True)
        self._progress.set_valign(Gtk.Align.CENTER)
        column.append(self._progress)

        header.append(column)
        return header

    def _build_footer(self) -> Gtk.Widget:
        """Back at the left edge, forward at the right, across the width.

        Both used to sit together in the bottom-right corner at the
        default button size. On the shipping medium that was reported as
        "hard to see and small" - and the two of them side by side in one
        corner also means the button that goes back and the button that
        erases a disk are a few millimetres apart. Opposite ends is the
        arrangement every installer uses, and it is not a convention for
        its own sake.
        """
        self.back = Gtk.Button()
        self._tr(lambda: self.back.set_label(_("Back")))
        self.back.add_css_class("wizard-nav")
        self.back.connect("clicked", lambda _b: self._step(-1))

        self.forward = Gtk.Button()
        self.forward.add_css_class("suggested-action")
        self.forward.add_css_class("wizard-nav")
        self.forward.connect("clicked", self._on_forward_clicked)

        # In the same column as everything above it. The header sits in
        # the boot menu's 62%-wide centred strip; buttons pinned to the
        # window edges would be the one row that does not line up with
        # it, and on a wide screen they end up far outside the content
        # they belong to.
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.add_css_class("wizard-column")
        row.set_halign(Gtk.Align.CENTER)
        row.set_hexpand(True)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        footer.add_css_class("wizard-footer")
        footer.append(row)
        row.append(self.back)

        # WHICH MEDIUM THIS IS, in the corner, dim.
        #
        # Written because of an afternoon spent unable to tell a rebuilt
        # image from the one before it. The image was rewritten to the
        # stick four times on 10.08.2026 and each time the question came
        # back the same way - "it still looks the same" - with no way,
        # from the screen, to say whether that was a stale boot or a
        # change that had not worked. A build date costs one dim line and
        # answers it in a second.
        #
        # Read from the medium rather than compiled in: the package does
        # not know which ISO it ended up on, and the ISO is the thing
        # somebody writes to a stick and loses track of.
        stamp = self._medium_version()
        if stamp:
            label = Gtk.Label(label=stamp)
            label.add_css_class("wizard-stamp")
            label.set_valign(Gtk.Align.CENTER)
            row.append(label)

        # Pushes the two apart at any window width. set_halign on each
        # would not: a box hands its children the space they asked for
        # and leaves the rest at the end.
        gap = Gtk.Box()
        gap.set_hexpand(True)
        row.append(gap)

        row.append(self.forward)
        return footer

    # What iso/build.sh writes into the image: date, commit, build time.
    # /run/archiso/bootmnt/zepos/version is the fallback and carries the
    # date alone, which does not separate two builds made on one day -
    # the very case this line exists for.
    BUILD_STAMP = Path("/etc/zepos-build")
    MEDIUM_VERSION = Path("/run/archiso/bootmnt/zepos/version")

    @staticmethod
    def _medium_version() -> str:
        """Which build of the medium this is, or nothing.

        Nothing on an installed system, where neither file is there, and
        nothing if they cannot be read - a version line is worth one
        line of code and no risk at all.
        """
        for path in (InstallerWindow.BUILD_STAMP,
                     InstallerWindow.MEDIUM_VERSION):
            try:
                text = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            # One line, and bounded, so that a corrupt file cannot fill
            # the footer with whatever it happens to contain.
            first = text.splitlines()[0].strip() if text else ""
            if first:
                return f"ZepOS {first[:40]}"
        return ""

    def _tr(self, apply: Callable[[], None]) -> None:
        """Apply a label now, and again whenever the language changes."""
        self._retranslate.append(apply)
        apply()

    def _retranslate_all(self) -> None:
        for apply in self._retranslate:
            apply()
        # The header, the step counter and the forward button are
        # rewritten by _sync() on every page change anyway, so they only
        # need to be asked once more.
        self._sync()

    def _visible_steps(self) -> list[str]:
        """The pages this run will actually show, in order.

        should_skip() answers about the state as it is now - the network
        page disappears once a cable is found - so "step 3 of 6" has to
        be recomputed on arrival rather than counted once. A page that is
        skipped is not a step the user is asked to take, and counting it
        would leave the number stuck one short of the total at the end.
        """
        return [name for name in PAGE_ORDER if not self.state.should_skip(name)]

    @staticmethod
    def _backdrop() -> Gtk.Widget | None:
        """The picture the whole window sits on, or nothing.

        Nothing when the file is absent - a checkout that has never been
        packaged has no backdrop, and the installer must still open.

        COVER and not CONTAIN: the file is 16:9 and a screen may not be,
        and a band of bare window either side would be worse than losing
        a little of the texture off the edge. Nothing in the picture is
        information; it is a ground.
        """
        if not branding.BACKDROP.is_file():
            return None
        try:
            texture = Gdk.Texture.new_from_filename(str(branding.BACKDROP))
        except Exception:                                   # noqa: BLE001
            return None
        picture = Gtk.Picture.new_for_paintable(texture)
        picture.set_content_fit(Gtk.ContentFit.COVER)
        # It must not decide how big the window is - it is 1920x1080 and
        # the window is whatever the screen gives it. can_shrink lets the
        # overlay size itself from the content on top instead.
        picture.set_can_shrink(True)
        picture.set_hexpand(True)
        picture.set_vexpand(True)
        return picture

    @staticmethod
    def _logo() -> Gtk.Widget | None:
        """The ZeptronIT wordmark, or nothing at all.

        Nothing rather than a broken-image icon when the file is not
        there: it is installed by zepos-installer-gui, and a checkout
        that has never been packaged does not have it. A missing mark
        has to cost a mark and not an installer, which is why the load
        is inside a try as well.

        WHY A PNG WHEN THE PACKAGE ALSO SHIPS THE SVG
            Both reasons were measured on 10.08.2026, and
            packaging/make-brand-assets.sh carries the long version.

            The layout one: a Gtk.Picture whose paintable is bigger than
            it should be drawn has to shrink, and while its box works
            out its own minimum it proposes -1 as the other dimension.
            Something on that path subtracts, GTK is handed less than
            -1, and every build logs

                Gtk-CRITICAL: gtk_widget_measure:
                assertion 'for_size >= -1' failed

            which tests/installer/test_gui_headless.py fails on. Turning
            can_shrink off silences it by making the file's own 700x400
            binding, which is most of the window. A texture that is
            ALREADY 91x52 has nothing to negotiate.

            The loader one: on this machine gdk-pixbuf hands SVG
            decoding to glycin, which runs the loader inside bwrap.
            Where that cannot spawn - the test harness, and plausibly a
            live medium - the render fails and the mark silently
            disappears. GTK's own PNG path involves none of it.
        """
        mark = branding.WORDMARK
        if not mark.is_file():
            return None
        try:
            texture = Gdk.Texture.new_from_filename(str(mark))
        except Exception:                                   # noqa: BLE001
            return None
        picture = Gtk.Picture.new_for_paintable(texture)
        picture.set_can_shrink(False)
        picture.add_css_class("wizard-mark")
        return picture

    # --- page construction -------------------------------------------

    def _build_page(self, name: str) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        # No logo here. It used to sit on this page, once, above the
        # first question; it is now in the wizard header, on every page,
        # where the boot menu also puts it.
        #
        # WHAT THAT MOVE MUST NOT LOSE, because this line crashed the
        # shipping medium once. A Gtk.Picture cannot be handed to
        # Adw.PreferencesPage.add(), which is typed to
        # Adw.PreferencesGroup and nothing else:
        #
        #     TypeError: argument group: Expected Adw.PreferencesGroup,
        #     but got gi.repository.Gtk.Picture
        #
        # It raised while the first page was being built - on the medium,
        # the moment the installer would have appeared - and no test
        # caught it, because `gi` was absent from the virtual environment
        # and every widget in this file had zero coverage. In the header
        # the picture goes into a Gtk.Box, which takes any widget, so the
        # trap is not there; it is still written down here because this
        # is where somebody would put a logo back.
        #
        # The two guards that make it a caught mistake rather than a
        # remembered one: tests/installer/test_gui_headless.py builds
        # this window for real on gtk4-broadwayd - GTK's own display
        # server, no X, no Wayland, no GPU - and
        # tests/installer/test_gui_widget_types.py reads every GTK call
        # in this directory against the .gir data PyGObject marshals
        # from, including the lines the smoke test does not reach.

        # No title on the group. The wizard header above it already says
        # which step this is, and on the language page the row beneath
        # said it a third time - "Select language" as the heading, as the
        # group and as the row, one under the other.
        group = Adw.PreferencesGroup()
        page.add(group)
        builder = getattr(self, f"_build_{name}", None)
        if builder is not None:
            builder(group)
        if name != "zusammenfassung":
            # The summary page has nothing of its own to validate - its
            # error text is the findings list, rendered as rows inside
            # _summary_group by _refresh_summary(), not a single label.
            error_label = Gtk.Label(label="")
            error_label.add_css_class("error")
            error_label.set_wrap(True)
            error_label.set_xalign(0)
            group.add(error_label)
            self._error_labels[name] = error_label
        return page

    def _build_sprache(self, group: Adw.PreferencesGroup) -> None:
        row = Adw.ComboRow()
        self._tr(lambda: row.set_title(_("Select language")))
        row.set_model(Gtk.StringList.new([_("German"), _("English")]))
        row.set_selected(0 if self.state.language == "de" else 1)

        def _on_changed(widget, _pspec):
            language = "de" if widget.get_selected() == 0 else "en"
            self.state.set_language(language)
            self._retranslate_all()

        row.connect("notify::selected", _on_changed)
        group.add(row)

    def _build_netzwerk(self, group: Adw.PreferencesGroup) -> None:
        """The wireless page: every network that was heard, and a way to
        reach the ones that were not.

        Two entries follow the scan results and neither is a network.
        "Other network" is for one that does not broadcast its name, and
        for the one that the scan missed anyway - without it, a hidden
        SSID cannot be typed at all and the only way on is Ethernet.
        "Skip" stays the default, because it is the right answer for
        every machine with a cable.

        The count is shown rather than left to be inferred from the list.
        A wireless list is the one control here whose contents the user
        can check against the world they are sitting in: "3 networks"
        next to a phone showing nine is a fact they can act on, and
        acting on it is what the button beside it is for.
        """
        self._network_status = Adw.ActionRow()
        self._rescan = Gtk.Button()
        self._tr(lambda: self._rescan.set_label(_("Scan again")))
        self._rescan.set_valign(Gtk.Align.CENTER)
        self._rescan.connect("clicked", self._on_rescan_clicked)
        self._network_status.add_suffix(self._rescan)
        group.add(self._network_status)

        self._network_row = Adw.ComboRow()
        self._tr(lambda: self._network_row.set_title(_("Select wireless network")))
        group.add(self._network_row)

        self._ssid_row = Adw.EntryRow()
        self._tr(lambda: self._ssid_row.set_title(_("Network name (SSID)")))
        self._ssid_row.set_visible(False)
        group.add(self._ssid_row)

        self._passphrase_row = Adw.PasswordEntryRow()
        # Its title carries the chosen network and is rewritten by
        # _on_network_changed; only the empty starting state needs the
        # register, for the case where the language changes before any
        # network was picked.
        self._tr(lambda: self._passphrase_row.set_title(
            _("Password for {ssid}").format(ssid=self.state.wifi_ssid)))
        self._passphrase_row.set_sensitive(False)
        group.add(self._passphrase_row)

        def _on_ssid_changed(widget):
            # Only while it is the answer. The row is hidden unless
            # "Other network" is chosen, and a hidden field must not
            # decide anything: text left in it from an earlier choice
            # would otherwise mean the installer tries to associate with
            # a network the user has since navigated away from - with
            # "Skip" showing on the screen.
            if not self._ssid_row.get_visible():
                return
            self.state.wifi_ssid = widget.get_text()
            self._refresh_validation()

        def _on_passphrase_changed(widget):
            self.state.wifi_passphrase = widget.get_text()
            self._refresh_validation()

        self._ssid_row.connect("changed", _on_ssid_changed)
        self._passphrase_row.connect("changed", _on_passphrase_changed)
        self._network_row.connect("notify::selected", self._on_network_changed)

        self._populate_networks()

    def _populate_networks(self) -> None:
        """Fill the list from state.wifi_networks and reset the choice.

        Called again after every rescan, so it has to put the page back
        into a known state rather than assume the one it left: the
        network the user had selected may not be in the new list, and a
        passphrase typed for it must not be carried over to whatever now
        sits at that index.
        """
        networks = self.state.wifi_networks
        self._network_status.set_title(
            ngettext("{count} network found", "{count} networks found",
                     len(networks)).format(count=len(networks)))

        options = [self._network_label(n) for n in networks]
        options += [_("Other network (enter the name)"), _("Skip")]

        # notify::selected fires while the model is being replaced, and
        # the handler indexes into `networks` - which is the list being
        # replaced. A flag rather than handler_block_by_func(): that is
        # a PyGObject convenience with no entry in GTK's own type data,
        # so tests/installer/test_gui_widget_types.py cannot confirm it
        # exists, and a call it cannot confirm is one nobody can promise
        # will still be there.
        self._populating = True
        self._network_row.set_model(Gtk.StringList.new(options))
        self._network_row.set_selected(len(options) - 1)   # "Skip"
        self._populating = False

        self.state.wifi_ssid = ""
        self.state.wifi_passphrase = ""
        self._ssid_row.set_text("")
        self._ssid_row.set_visible(False)
        self._passphrase_row.set_text("")
        self._passphrase_row.set_sensitive(False)
        self._refresh_validation()

    @staticmethod
    def _network_label(network: Network) -> str:
        """The name, and whether a password will be wanted.

        The lock is the part that is not guessable from the name, and it
        is the one that decides whether the next field matters. Signal
        strength is left out on purpose: iwctl reports it in units that
        would need a legend, and the user is picking their own network
        by name, not shopping for the strongest one.
        """
        if network.secured:
            return f"\N{LOCK} {network.ssid}"
        return network.ssid

    def _on_network_changed(self, widget, _pspec) -> None:
        if self._populating:
            return
        networks = self.state.wifi_networks
        selected = widget.get_selected()
        other = len(networks)          # "Other network"
        skip = len(networks) + 1       # "Skip"

        if selected == other:
            self._ssid_row.set_visible(True)
            self.state.wifi_ssid = self._ssid_row.get_text()
            self._passphrase_row.set_title(_("Password"))
            self._passphrase_row.set_sensitive(True)
        elif selected >= skip:
            self._ssid_row.set_visible(False)
            self.state.wifi_ssid = ""
            self.state.wifi_passphrase = ""
            self._passphrase_row.set_text("")
            self._passphrase_row.set_sensitive(False)
        else:
            self._ssid_row.set_visible(False)
            network = networks[selected]
            self.state.wifi_ssid = network.ssid
            self._passphrase_row.set_title(
                _("Password for {ssid}").format(ssid=network.ssid))
            self._passphrase_row.set_sensitive(True)
        self._refresh_validation()

    def _on_rescan_clicked(self, _button: Gtk.Button) -> None:
        """Scan again, without the window going still for it.

        discover_networks() now waits for the scan to settle, which is
        seconds. On the main thread that is a frozen form - the same
        reason the installation and the wireless association run on
        workers.
        """
        self._rescan.set_sensitive(False)
        self._network_status.set_title(_("Searching for networks…"))

        def _worker() -> None:
            found = discover_networks(self.wifi_backend)
            GLib.idle_add(self._on_rescan_finished, found)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_rescan_finished(self, found: list[Network]) -> bool:
        self.state.wifi_networks = found
        self._populate_networks()
        self._rescan.set_sensitive(True)
        return GLib.SOURCE_REMOVE

    def _build_datentraeger(self, group: Adw.PreferencesGroup) -> None:
        if not self.usable_disks:
            status = Adw.StatusPage(
                title=_(
                    "No disk is large enough to install ZepOS. At least {minimum} MiB are required."
                ).format(minimum=MIN_DISK_MIB)
            )
            group.add(status)
            return

        # One row per disk instead of a dropdown, and the reason is not
        # taste. A dropdown shows one line at a time and hides the rest
        # behind a click, so two disks are compared from memory; here
        # they are side by side. It also gives each disk two lines - the
        # model and size above, the device node, how it is attached and
        # what is on it below - which is what "viel zu wenig infos"
        # asked for and what a dropdown row has no room to say.
        first: Gtk.CheckButton | None = None
        for index, disk in enumerate(self.usable_disks):
            row = Adw.ActionRow(
                title=describe(disk), subtitle=describe_contents(disk))
            row.set_subtitle_lines(2)

            choice = Gtk.CheckButton()
            choice.set_valign(Gtk.Align.CENTER)
            if first is None:
                first = choice
            else:
                # One group, so choosing one clears the others. Set on
                # the later buttons and pointing at the first, which is
                # the direction Gtk.CheckButton.set_group expects.
                choice.set_group(first)
            choice.set_active(index == 0)
            choice.connect("toggled", self._on_disk_toggled, disk)

            row.add_prefix(choice)
            # The whole row activates its button, so the target is the
            # row and not a 16-pixel circle.
            row.set_activatable_widget(choice)
            group.add(row)

        self.state.select_disk(self.usable_disks[0])

        warning = Gtk.Label()
        self._tr(lambda: warning.set_label(_("This erases the entire disk.")))
        warning.add_css_class("warning")
        warning.set_xalign(0)
        group.add(warning)

    def _on_disk_toggled(self, button: Gtk.CheckButton, disk: Disk) -> None:
        # Toggling fires on the button being cleared as well as the one
        # being set, and the cleared one arrives first. Acting on it
        # would select the disk the user just moved away from.
        if not button.get_active():
            return
        self.state.select_disk(disk)
        self._refresh_validation()

    # --- die Einteilung ------------------------------------------------

    def _build_partitionierung(self, group: Adw.PreferencesGroup) -> None:
        """Was auf der Platte liegt, was daraus wird, und die Knoepfe
        dazwischen.

        GEMELDET ALS: "ausserdem soll man im wizard die festplatten
        bereinigen koennen und neu zuweisen mit partitionen usw. das
        fehlt noch komplett". Bis hierher konnte der Assistent eine
        Platte aussuchen und komplett loeschen lassen; was auf ihr lag,
        stand in einer Zeile Kleingedrucktem auf der Seite davor, und die
        Einteilung, die danach entstand, war eine Konstante im
        Uebersetzungsmodul.

        DIE SEITE HAT ZWEI LISTEN, UND DAS IST DER GANZE ENTWURF.
        Oben, was jetzt da ist - jede Partition mit Dateisystem,
        Bezeichnung und Groesse, und darueber der Satz, dass sie geloescht
        wird. Unten, was entstehen soll. Beide untereinander auf einer
        Seite, weil die Frage, die hier beantwortet wird, ein Vergleich
        ist: ist das, was ich verliere, weniger wert als das, was ich
        bekomme.

        Die beiden Listen sind Gtk.ListBox und nicht weitere Zeilen in
        dieser Gruppe. Sie werden bei jeder Aenderung neu gefuellt, und
        Adw.PreferencesGroup haengt jede add() ans ENDE - die neuen
        Zeilen laegen also hinter dem Formular statt darueber, sobald
        einmal etwas hinzugefuegt wurde. Eine ListBox raeumt ihre
        eigenen Kinder, und ihre Zeilen sind Adw.ActionRow wie ueberall
        sonst im Assistenten.

        KEINE EIGENEN GROESSEN, UND DAS IST GEPRUEFT UND NICHT VERGESSEN.
        "button und aktionen etwas groesser alle" ist bereits als Regel
        in installer/gui/branding.py umgesetzt und gilt fuer Knoepfe und
        Zeilen dieser Seite genauso: `button` bekommt dort min-height
        2.4rem, `row, label, button` 1.35rem Schrift und `row` 4rem
        Hoehe. Eine dritte Knopfgroesse nur hier waere die eine Seite,
        die aus der Reihe faellt; die groesste bleibt .wizard-nav, weil
        das die Knoepfe sind, an denen der Assistent entlanggeht.
        """
        self._existing_heading = Gtk.Label(label="")
        self._existing_heading.add_css_class("warning")
        self._existing_heading.set_xalign(0)
        self._existing_heading.set_wrap(True)
        group.add(self._existing_heading)

        self._existing_list = Gtk.ListBox()
        self._existing_list.add_css_class("boxed-list")
        self._existing_list.set_selection_mode(Gtk.SelectionMode.NONE)
        group.add(self._existing_list)

        plan_heading = Gtk.Label()
        self._tr(lambda: plan_heading.set_label(_("New layout")))
        plan_heading.add_css_class("heading")
        plan_heading.set_xalign(0)
        group.add(plan_heading)

        self._plan_list = Gtk.ListBox()
        self._plan_list.add_css_class("boxed-list")
        self._plan_list.set_selection_mode(Gtk.SelectionMode.NONE)
        group.add(self._plan_list)

        self._plan_summary = Gtk.Label(label="")
        self._plan_summary.add_css_class("dim-label")
        self._plan_summary.set_xalign(0)
        group.add(self._plan_summary)

        # Die zwei Knoepfe, die die ganze Einteilung auf einmal setzen.
        # Nebeneinander und nicht als Zeilen, weil sie Handlungen sind
        # und keine Einstellungen - dieselbe Unterscheidung, die den
        # Fussbereich von den Formularzeilen trennt.
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        actions.set_homogeneous(True)

        self._partition_suggest = Gtk.Button()
        self._tr(lambda: self._partition_suggest.set_label(_("Use suggestion")))
        self._partition_suggest.connect("clicked", self._on_suggest_clicked)
        actions.append(self._partition_suggest)

        self._partition_clear = Gtk.Button()
        self._tr(lambda: self._partition_clear.set_label(_("Clear the disk")))
        # destructive-action, obwohl hier nichts geloescht wird: der Knopf
        # wirft weg, was der Nutzer geplant hat, und libadwaita hat genau
        # eine Farbe fuer "das nimmt etwas weg". Sie ist auf dieser Seite
        # sonst nirgends, also sagt sie etwas.
        self._partition_clear.add_css_class("destructive-action")
        self._partition_clear.connect("clicked", self._on_clear_clicked)
        actions.append(self._partition_clear)

        group.add(actions)

        form_heading = Gtk.Label()
        self._tr(lambda: form_heading.set_label(_("Add a partition")))
        form_heading.add_css_class("heading")
        form_heading.set_xalign(0)
        group.add(form_heading)

        # Erst alle drei Zeilen bauen, dann verbinden. Ein
        # notify::selected auf dem oberen Auswahlfeld laeuft in
        # _on_mountpoint_changed, und das fasst die beiden unteren an -
        # eine Verbindung, die vor ihnen geknuepft wird, ist ein
        # AttributeError im Konstruktor. Dieselbe Reihenfolge, aus
        # demselben Grund, wie sie _build_netzwerk() einhaelt.
        self._mountpoint_row = Adw.ComboRow()
        self._tr(lambda: self._mountpoint_row.set_title(_("Mount point")))
        group.add(self._mountpoint_row)

        self._filesystem_row = Adw.ComboRow()
        self._tr(lambda: self._filesystem_row.set_title(_("File system")))
        # Die Namen sind Bezeichner, keine Prosa: "ext4" heisst auf
        # Deutsch ext4. Sie gehen deshalb NICHT durch _() - eine
        # Uebersetzung koennte sie nur falsch machen, und archinstall
        # nimmt sie genau so entgegen (FilesystemType, eine StrEnum).
        self._filesystem_row.set_model(
            Gtk.StringList.new(list(FILESYSTEM_CHOICES)))
        group.add(self._filesystem_row)

        self._size_row = Adw.EntryRow()
        self._tr(lambda: self._size_row.set_title(_("Size (for example 20G, or rest)")))
        group.add(self._size_row)

        self._size_error = Gtk.Label(label="")
        self._size_error.add_css_class("error")
        self._size_error.set_wrap(True)
        self._size_error.set_xalign(0)
        group.add(self._size_error)

        self._mountpoint_row.connect(
            "notify::selected", self._on_mountpoint_changed)
        self._filesystem_row.connect(
            "notify::selected", self._on_filesystem_changed)
        self._size_row.connect("changed", self._on_size_changed)

        # Zwei der Eintraege sind uebersetzte Saetze und nicht nur Pfade
        # ("/boot (EFI-Systempartition)", "Auslagerung"), also muss das
        # Modell bei einem Sprachwechsel neu gebaut werden. Sonst steht
        # hier das, was die Modulkopfzeile als gemeldeten Fehler
        # festhaelt: eine Maske, die auf Deutsch umschaltet - ausser bei
        # ihren Knoepfen und Zeilentiteln.
        #
        # Die Auswahl kommt danach aus dem Zustand zurueck und nicht aus
        # dem Feld: set_model() setzt sie auf 0, und der Nutzer haette
        # nach einem Sprachwechsel eine andere Partition im Formular als
        # vorher.
        self._tr(self._retranslate_mountpoints)

        self._partition_add = Gtk.Button()
        self._tr(lambda: self._partition_add.set_label(_("Add a partition")))
        self._partition_add.add_css_class("suggested-action")
        self._partition_add.connect("clicked", self._on_add_partition_clicked)
        group.add(self._partition_add)

        # Die Zeilen, die diese Seite selbst angelegt hat, damit
        # _refresh_partitioning() genau sie wieder entfernt und nicht das,
        # was die ListBox intern um sie herum baut - dieselbe Regel, die
        # _refresh_summary() befolgt.
        self._existing_rows: list[Gtk.Widget] = []
        self._plan_rows: list[Gtk.Widget] = []

    def _retranslate_mountpoints(self) -> None:
        """Die Eintraege in der neuen Sprache, mit derselben Auswahl.

        Die Auswahl wird VOR set_model() gemerkt, und das ist keine
        Vorsicht, sondern ein gemessener Fehler: set_model() loest selbst
        ein notify::selected mit Position 0 aus, _on_mountpoint_changed
        schreibt daraufhin MOUNTPOINT_CHOICES[0] in den Zustand, und die
        Zeile darunter liest dann genau diese 0 zurueck. Der kopflose
        Lauf hat es so gefunden: nach einem Wechsel auf Englisch stand im
        Formular "/" statt des eingestellten "/home", und auf dem Schirm
        war nichts zu sehen, das darauf hingewiesen haette.
        """
        chosen = self.state.new_mountpoint
        self._mountpoint_row.set_model(
            Gtk.StringList.new([_mountpoint_label(choice)
                                for choice in MOUNTPOINT_CHOICES]))
        self._mountpoint_row.set_selected(MOUNTPOINT_CHOICES.index(chosen))

    def _on_suggest_clicked(self, _button: Gtk.Button) -> None:
        self.state.reset_layout()
        self._refresh_partitioning()
        self._refresh_validation()

    def _on_clear_clicked(self, _button: Gtk.Button) -> None:
        self.state.clear_layout()
        self._refresh_partitioning()
        self._refresh_validation()

    def _on_mountpoint_changed(self, widget: Adw.ComboRow, _pspec) -> None:
        self.state.new_mountpoint = MOUNTPOINT_CHOICES[widget.get_selected()]
        self._filesystem_row.set_sensitive(self.state.filesystem_is_chosen())
        self._refresh_size_error()

    def _on_filesystem_changed(self, widget: Adw.ComboRow, _pspec) -> None:
        self.state.new_filesystem = FILESYSTEM_CHOICES[widget.get_selected()]

    def _on_size_changed(self, widget: Adw.EntryRow) -> None:
        self.state.new_size = widget.get_text()
        self._refresh_size_error()

    def _refresh_size_error(self) -> None:
        """Was an der getippten Groesse nicht stimmt, neben der Zeile.

        Leer, solange nichts getippt wurde: eine rote Zeile unter einem
        Feld, das noch niemand angefasst hat, ist keine Hilfe, sondern
        ein Vorwurf.
        """
        self._size_error.set_text(
            self.state.size_error() if self.state.new_size.strip() else "")

    def _on_add_partition_clicked(self, _button: Gtk.Button) -> None:
        problem = self.state.add_partition()
        if problem:
            self._size_error.set_text(problem)
            return
        self._size_row.set_text("")
        self._refresh_partitioning()
        self._refresh_validation()

    def _on_remove_partition_clicked(
        self, _button: Gtk.Button, planned: PlannedPartition
    ) -> None:
        self.state.remove_partition(planned)
        self._refresh_partitioning()
        self._refresh_validation()

    def _refresh_partitioning(self) -> None:
        """Beide Listen neu aufbauen.

        Aufgerufen von _sync(), also bei jedem Betreten der Seite: die
        gewaehlte Platte kann sich eine Seite vorher geaendert haben, und
        mit ihr die vorhandenen Partitionen und die vorgeschlagene
        Einteilung.

        Entfernt wird nur, was diese Methode selbst angelegt hat. Eine
        Gtk.ListBox haengt jede Zeile in einen eigenen Behaelter, sodass
        ein Durchlauf mit get_first_child() die Zeilen liefert, die
        append() angenommen hat - remove() aber genau die erwartet. Die
        Liste mitzufuehren kostet zwei Felder und macht daraus eine
        Frage, die nicht gestellt werden muss.
        """
        for row in self._existing_rows:
            self._existing_list.remove(row)
        self._existing_rows = []
        for row in self._plan_rows:
            self._plan_list.remove(row)
        self._plan_rows = []

        self._existing_heading.set_text(self.state.existing_summary())
        for partition in self.state.device_partitions:
            row = Adw.ActionRow(
                title=partition.device,
                subtitle=_existing_subtitle(partition))
            self._existing_list.append(row)
            self._existing_rows.append(row)

        for planned in self.state.layout:
            row = Adw.ActionRow(
                title=planned.describe(), subtitle=planned.describe_contents())
            remove = Gtk.Button()
            remove.set_label(_("Remove"))
            remove.set_valign(Gtk.Align.CENTER)
            remove.add_css_class("destructive-action")
            remove.connect("clicked", self._on_remove_partition_clicked, planned)
            row.add_suffix(remove)
            self._plan_list.append(row)
            self._plan_rows.append(row)

        self._plan_summary.set_text(self.state.layout_summary())
        self._refresh_size_error()

    def _build_verschluesselung(self, group: Adw.PreferencesGroup) -> None:
        """Der Haken, die zwei Felder, und die Warnung dazwischen.

        DIE REIHENFOLGE IST DIE AUSSAGE
            Haken, dann WARNUNG, dann die Eingabefelder. Nicht Haken,
            Felder, Warnung: wer die Passphrase schon getippt hat, liest
            darunter nichts mehr - er sucht "Weiter". Die Warnung steht
            deshalb dort, wo der Blick auf dem Weg von der einen
            Entscheidung zur anderen ohnehin vorbeikommt.

        WARUM DIE FELDER NICHT VERSCHWINDEN, WENN DER HAKEN WEG IST
            Sie werden unempfindlich, nicht unsichtbar. Ein Feld, das
            verschwindet, nimmt die Seite mit - sie waere danach fast
            leer, und der Nutzer haette keinen Anhaltspunkt mehr, was er
            gerade abgewaehlt hat. Unempfindlich sagt beides: es gibt das
            hier, und es ist gerade nicht Ihre Aufgabe.
        """
        encrypt_row = Adw.SwitchRow()
        self._tr(lambda: encrypt_row.set_title(_("Encrypt this disk")))
        self._tr(lambda: encrypt_row.set_subtitle(_("AES-256, the strength governments use for classified material. Without the passphrase the disk is unreadable, even taken out of this computer.")))
        encrypt_row.set_active(self.state.encrypt)
        group.add(encrypt_row)

        # Die Warnung, und sie sieht aus wie eine. Adw.ActionRow haette
        # sie in derselben Schrift wie den Wetterort daneben gestellt;
        # die CSS-Klasse "error" ist dieselbe, die _build_page() dem
        # Fehlertext jeder Seite gibt, also die eine Farbe, die in diesem
        # Fenster schon "hier stimmt etwas nicht" bedeutet.
        self._encryption_warning = Gtk.Label(label="")
        self._encryption_warning.add_css_class("error")
        self._encryption_warning.set_wrap(True)
        self._encryption_warning.set_xalign(0)
        group.add(self._encryption_warning)

        # Und darunter das Uebrige - Kosten, Tastatur, was offen bleibt.
        # Getrennt von der Warnung und in der gewoehnlichen Farbe: was
        # rot ist und trotzdem nur eine Auskunft, macht das Rote daneben
        # billiger.
        self._encryption_notes = Gtk.Label(label="")
        self._encryption_notes.add_css_class("dim-label")
        self._encryption_notes.set_wrap(True)
        self._encryption_notes.set_xalign(0)
        group.add(self._encryption_notes)

        self._passphrase_rows = []
        passphrase_row = Adw.PasswordEntryRow()
        self._tr(lambda: passphrase_row.set_title(_("Disk passphrase")))
        self._bind_entry(passphrase_row, "encryption_passphrase")
        group.add(passphrase_row)
        self._passphrase_rows.append(passphrase_row)

        passphrase_confirm_row = Adw.PasswordEntryRow()
        self._tr(lambda: passphrase_confirm_row.set_title(_("Repeat the passphrase")))
        self._bind_entry(passphrase_confirm_row, "encryption_passphrase_confirm")
        group.add(passphrase_confirm_row)
        self._passphrase_rows.append(passphrase_confirm_row)

        def _on_encrypt_changed(widget, _pspec):
            self.state.encrypt = widget.get_active()
            self._refresh_encryption()
            self._refresh_validation()

        encrypt_row.connect("notify::active", _on_encrypt_changed)
        self._refresh_encryption()

    def _refresh_encryption(self) -> None:
        """Die Seite an den Haken anpassen.

        Von _build_verschluesselung() beim Bauen, vom Schalter bei jedem
        Umlegen und von _sync() bei jedem Betreten gerufen - das letzte,
        weil die Liste dessen, was im Klartext bleibt, aus der Einteilung
        kommt und die eine Seite vorher geaendert worden sein kann.
        """
        notes = self.state.encryption_notes() if self.state.encrypt else []
        # Der erste Eintrag ist die Warnung (siehe
        # PageState.encryption_notes()), der Rest ist Auskunft.
        self._encryption_warning.set_text(notes[0] if notes else "")
        self._encryption_notes.set_text("\n\n".join(notes[1:]))
        for row in self._passphrase_rows:
            row.set_sensitive(self.state.encrypt)

    def _build_benutzer(self, group: Adw.PreferencesGroup) -> None:
        hostname_row = Adw.EntryRow()
        self._tr(lambda: hostname_row.set_title(_("Hostname")))
        hostname_row.set_text(self.state.hostname)
        self._bind_entry(hostname_row, "hostname")
        group.add(hostname_row)

        username_row = Adw.EntryRow()
        self._tr(lambda: username_row.set_title(_("Username")))
        self._bind_entry(username_row, "username")
        group.add(username_row)

        password_row = Adw.PasswordEntryRow()

        self._tr(lambda: password_row.set_title(_("Password")))
        self._bind_entry(password_row, "password")
        group.add(password_row)

        password_confirm_row = Adw.PasswordEntryRow()

        self._tr(lambda: password_confirm_row.set_title(_("Repeat the password")))
        self._bind_entry(password_confirm_row, "password_confirm")
        group.add(password_confirm_row)

        root_password_row = Adw.PasswordEntryRow()

        self._tr(lambda: root_password_row.set_title(_("Root password")))
        self._bind_entry(root_password_row, "root_password")
        group.add(root_password_row)

        root_password_confirm_row = Adw.PasswordEntryRow()

        self._tr(lambda: root_password_confirm_row.set_title(_("Repeat the password")))
        self._bind_entry(root_password_confirm_row, "root_password_confirm")
        group.add(root_password_confirm_row)

    def _build_zeit(self, group: Adw.PreferencesGroup) -> None:
        """Die Zeitzone - eine AUSWAHL, seit dem 02.09.2026.

        WAS HIER STAND UND WARUM ES WEG IST
            Eine Adw.EntryRow, also ein freies Textfeld, vorbelegt mit
            einem Wert aus LANGUAGE_DEFAULTS - "en" hiess UTC. Zwei
            Fehler in vier Zeilen:

              * ein Tippfehler wurde installiert. `date` nimmt JEDEN
                Namen an und druckt fuer einen unbekannten die UTC-Zeit
                mit dem erfundenen Kuerzel, Rueckgabewert 0 (die Messung
                steht in src/doctor.py). "Europe/Berln" ergab eine Uhr,
                die still zwei Stunden falsch ging.
              * die Vorbelegung leitete einen ORT aus einer SPRACHE ab.
                Wer auf Englisch installierte, bekam UTC - wo auch
                immer er sass.

        WAS STATTDESSEN DASTEHT
            Die Namen aus der Zeitzonendatenbank dieses Mediums
            (installer/core/timezones.py), vorbelegt mit der Zone, in
            der das Medium GERADE laeuft - eine Tatsache statt einer
            Ableitung. pages.timezone_error() bleibt als Netz darunter,
            fuer eine vorgeladene Konfiguration, die keine Auswahl
            durchlaufen hat.

        WARUM DIE LISTE SUCHBAR IST
            GEMESSEN am 02.09.2026: die Datenbank nennt 598 Namen. Eine
            Aufklappliste mit 598 Zeilen ist eine Liste, in der niemand
            ankommt. Adw.ComboRow sucht, sobald ein Ausdruck dasteht,
            der einer Zeile ihren Text entnimmt - ohne ihn bleibt
            enable-search wirkungslos, und zwar lautlos.
        """
        row = Adw.ComboRow()
        self._tr(lambda: row.set_title(_("Timezone")))

        self._timezone_choices = timezones.choices()
        row.set_model(Gtk.StringList.new(self._timezone_choices))
        row.set_expression(
            Gtk.PropertyExpression.new(Gtk.StringObject, None, "string"))
        row.set_enable_search(True)

        current = self.state.timezone or timezones.running()
        if current in self._timezone_choices:
            row.set_selected(self._timezone_choices.index(current))
        # Der Wert steht danach im Zustand, auch wenn niemand die Zeile
        # anfasst - wortgleich zur Absicht der alten Fassung, die
        # `self.state.timezone = row.get_text()` schrieb.
        self.state.timezone = current

        def _on_changed(widget, _pspec):
            gewaehlt = widget.get_selected()
            if 0 <= gewaehlt < len(self._timezone_choices):
                self.state.timezone = self._timezone_choices[gewaehlt]
            self._refresh_validation()

        row.connect("notify::selected", _on_changed)
        group.add(row)

    def _build_zepos(self, group: Adw.PreferencesGroup) -> None:
        plugins_row = Adw.SwitchRow()
        self._tr(lambda: plugins_row.set_title(_("Enable ZepOS plugins?")))
        plugins_row.set_active(self.state.enable_plugins)

        def _on_plugins_changed(widget, _pspec):
            self.state.enable_plugins = widget.get_active()

        plugins_row.connect("notify::active", _on_plugins_changed)
        group.add(plugins_row)

        weather_row = Adw.EntryRow()
        self._tr(lambda: weather_row.set_title(_("Location for the weather widget")))
        self._bind_entry(weather_row, "weather_location")
        group.add(weather_row)

        # Die drei Zusatzpakete.
        #
        # WARUM JEDE ZEILE IHREN PREIS NENNT
        #     Der Unterschied zwischen einer Installation von zwanzig und
        #     einer von vierzig Minuten steckt in diesen drei Schaltern,
        #     und wer das erst am Fortschrittsbalken merkt, kann nichts
        #     mehr daran aendern. Die Zahlen sind gemessen - siehe
        #     installer/core/model.py, ZeposOptions.
        #
        # WARUM DREI BLOECKE UND KEINE SCHLEIFE UEBER EIN TUPEL
        #     Der Aufruf der Uebersetzung muss INNERHALB des Lambdas
        #     stehen, weil self._tr() es bei jedem Sprachwechsel erneut
        #     aufruft - ein einmal uebersetzter Text in einem Tupel
        #     bliebe in der Sprache stehen, die beim Bau des Fensters
        #     galt. Und die Zeichenkette muss woertlich als Literal im
        #     Aufruf stehen, weil tests/installer/test_i18n.py den
        #     Katalog mit genau diesem Muster gegen die Quellen
        #     abgleicht; eine Variable darin faende es nicht.
        #
        # WARUM JEDER TEXT AUF EINER ZEILE STEHT
        #     Gemessen, nachdem es schiefging: das Muster in test_i18n.py
        #     endet am ersten schliessenden Anfuehrungszeichen. Bei einer
        #     ueber mehrere Zeilen zusammengesetzten Zeichenkette faengt
        #     es also nur das erste Stueck, waehrend gettext zur Laufzeit
        #     nach dem ganzen Satz sucht - der Katalog haette den
        #     Eintrag, den die Pruefung will, und nicht den, den die
        #     Oberflaeche braucht. Zwei Fehler, die sich gegenseitig
        #     verdecken.
        office_row = Adw.SwitchRow()
        self._tr(lambda: office_row.set_title(_("Office applications")))
        self._tr(lambda: office_row.set_subtitle(_("LibreOffice with German and English dictionaries, about 646 MB. It has no GTK4 version, so it is the one window that does not carry the ZepOS colours.")))
        office_row.set_active(self.state.install_office)

        def _on_office_changed(widget, _pspec):
            self.state.install_office = widget.get_active()

        office_row.connect("notify::active", _on_office_changed)
        group.add(office_row)

        devel_row = Adw.SwitchRow()
        self._tr(lambda: devel_row.set_title(_("Development tools")))
        self._tr(lambda: devel_row.set_subtitle(_("base-devel and git, for building software, about 440 MB.")))
        devel_row.set_active(self.state.install_devel)

        def _on_devel_changed(widget, _pspec):
            self.state.install_devel = widget.get_active()

        devel_row.connect("notify::active", _on_devel_changed)
        group.add(devel_row)


    def _build_zusammenfassung(self, group: Adw.PreferencesGroup) -> None:
        self._summary_group = group

    def _build_progress_page(self) -> Gtk.Widget:
        """The page the window shows for the whole installation.

        A pulsing bar rather than a percentage: archinstall does not
        report progress in a form anything here could turn into a
        fraction, and a fake percentage that stalls at 40% is worse than
        an honest "still working". The log view underneath shows what
        archinstall itself is saying - without it, the output goes to the
        terminal that started the graphical session, which nobody sees.
        """
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for margin in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{margin}")(24)

        title = Gtk.Label()
        self._tr(lambda: title.set_label(_("ZepOS is being installed.")))
        title.add_css_class("title-2")
        title.set_xalign(0)
        box.append(title)

        self._progress_bar = Gtk.ProgressBar()
        self._progress_bar.set_show_text(True)
        self._progress_bar.set_text(
            _("{percent}% - please do not switch the computer off.")
            .format(percent=0))
        box.append(self._progress_bar)

        self._log_view = Gtk.TextView()
        self._log_view.set_editable(False)
        self._log_view.set_monospace(True)
        self._log_view.set_cursor_visible(False)
        self._log_scroller = Gtk.ScrolledWindow()
        self._log_scroller.set_vexpand(True)
        self._log_scroller.set_child(self._log_view)
        box.append(self._log_scroller)

        # Created once and never deleted - see _show_log for what
        # deleting it cost. Right gravity, so it stays at the end as
        # text is inserted before it.
        log_buffer = self._log_view.get_buffer()
        self._log_end = log_buffer.create_mark(
            "zepos-log-end", log_buffer.get_end_iter(), False)
        return box

    # --- generic field binding -----------------------------------------

    def _bind_entry(self, row: Adw.EntryRow, attribute: str) -> None:
        """Write a text row's content straight into one PageState field
        on every change, then refresh validation feedback. The callback
        itself decides nothing: it only marshals a value from a widget
        into pages.py and asks pages.py what that means."""

        def _on_changed(widget):
            setattr(self.state, attribute, widget.get_text())
            self._refresh_validation()

        row.connect("changed", _on_changed)

    # --- navigation -------------------------------------------------------

    def _step(self, delta: int) -> None:
        target = self.index + delta
        while 0 <= target < len(PAGE_ORDER) and self.state.should_skip(PAGE_ORDER[target]):
            target += delta
        if not 0 <= target < len(PAGE_ORDER):
            return
        self.index = target
        self._sync()

    def _on_forward_clicked(self, _button: Gtk.Button) -> None:
        if PAGE_ORDER[self.index] == "netzwerk" and self.state.needs_association():
            self._start_wireless_step()
        elif self.index == len(PAGE_ORDER) - 1:
            self._confirm_installation()
        else:
            self._step(1)

    def _start_wireless_step(self) -> None:
        """Join the chosen network before this page may be left.

        On a worker thread for the same reason the installation is:
        iwctl's connect blocks for seconds and the connection check
        blocks for seconds more, and a form that stops repainting while
        the user waits looks broken.

        Whether a worker may start at all is not decided here:
        PageState.begin_wireless_step() decides, and it is the ONLY gate.
        The button's own sensitivity was never one - _refresh_validation()
        recomputes that on every keystroke, so a character typed into the
        passphrase field re-enabled the button mid-connect, a second click
        started a second worker, and each worker's completion called
        _step(1). Two completions therefore advanced TWO pages and skipped
        the disk page, whose combo row has already pre-selected a disk to
        erase.
        """
        if not self.state.begin_wireless_step():
            return
        self._refresh_validation()
        self.toasts.add_toast(Adw.Toast.new(_("Connecting to the wireless network.")))

        def _worker() -> None:
            result = wireless_step(self.state, self.wifi_backend)
            GLib.idle_add(self._on_wireless_finished, result)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_wireless_finished(self, result) -> bool:
        # Released first, and unconditionally: wireless_step() never
        # raises (see its docstring), so this runs for every worker that
        # was ever started, and a claim never released would leave the
        # "next" button dead for the rest of the session.
        self.state.end_wireless_step()
        if result.message:
            self._show_message(_("Wireless network"), result.message)
        if result.connected and PAGE_ORDER[self.index] == "netzwerk":
            # Only ever advances the page the connect belonged to. "Back"
            # stays clickable while a connect runs, and a user who used it
            # must not be pulled forward again by a worker they left
            # behind. _step(1) calls _sync(), which refreshes the button
            # on the page it lands on.
            self._step(1)
        else:
            self._refresh_validation()
        return GLib.SOURCE_REMOVE

    def _sync(self) -> None:
        page = PAGE_ORDER[self.index]
        self.stack.set_visible_child_name(page)
        self.back.set_sensitive(self.index > 0)
        last = self.index == len(PAGE_ORDER) - 1
        self.forward.set_label(_("Install") if last else _("Next"))
        self._sync_header(page)
        if page == "partitionierung":
            # Bei jedem Betreten, nicht nur beim Bauen: die Platte wird
            # eine Seite vorher gewaehlt, und mit ihr wechseln die
            # vorhandenen Partitionen und der Vorschlag.
            self._refresh_partitioning()
        if page == "verschluesselung":
            # Ebenfalls bei jedem Betreten: welche Partitionen im
            # Klartext bleiben, steht in der Einteilung, und die wird
            # eine Seite vorher gemacht.
            self._refresh_encryption()
        if page == "zusammenfassung":
            self._refresh_summary()
        self._refresh_validation()

    def _sync_header(self, page: str) -> None:
        """The three things that change between steps.

        The current page is looked up in the visible list rather than
        assumed to be in it. It always is - _step() walks past skipped
        pages and never lands on one - but the fallback costs a line and
        the alternative is a ValueError on the one screen that would
        then be a black window.
        """
        steps = self._visible_steps()
        total = len(steps)
        position = steps.index(page) + 1 if page in steps else self.index + 1

        self._step_title.set_text(PAGE_TITLES[page]())
        self._step_counter.set_text(
            _("Step {position} of {total}").format(
                position=position, total=total))
        self._progress.set_fraction(position / total if total else 0.0)

    def _refresh_validation(self) -> None:
        page = PAGE_ORDER[self.index]
        label = self._error_labels.get(page)
        if label is not None:
            label.set_text(self.state.page_error(page))
        self.forward.set_sensitive(self.state.is_page_valid(page))

    def _refresh_summary(self) -> None:
        # Adw.PreferencesGroup wraps its rows in an internal container of
        # its own, so a generic get_first_child()/get_next_sibling() walk
        # does not yield the rows add() accepted - remove() then rejects
        # the internal wrapper it finds instead ("tried to remove
        # non-child"). Only rows this method itself added and tracked
        # are ever passed to remove(), which is the only widget set
        # Adw.PreferencesGroup.remove() actually recognises.
        group = self._summary_group
        for row in self._summary_rows:
            group.remove(row)
        self._summary_rows = []

        cfg = self.state.to_config()
        username = cfg.users[0].username if cfg.users else ""
        texts = [
            _("Hostname: {value}").format(value=cfg.hostname),
            _("Disk: {value}").format(value=cfg.disk.device),
            # Die Einteilung gehoert auf die Zusammenfassung, weil sie
            # die einzige Entscheidung dieses Assistenten ist, die man
            # nach der Installation nicht mehr aendern kann, ohne alles
            # noch einmal zu machen. Eine Zeile je Partition, in der
            # Reihenfolge der Platte.
            *(_("Partition: {value}").format(
                value=f"{planned.describe()} ({planned.filesystem})")
              for planned in cfg.disk.layout),
            # Verschluesselt oder nicht, immer - auch das "nein". Eine
            # Zusammenfassung, die den Haken nur nennt, wenn er gesetzt
            # ist, laesst genau den Fall stumm, den man hier bemerken
            # koennen muss: dass er es NICHT ist. Die Passphrase steht
            # selbstverstaendlich nicht dabei.
            _("Encryption: {value}").format(
                value=_("yes, AES-256") if cfg.disk.encrypt else _("no")),
            _("Username: {value}").format(value=username),
            _("Timezone: {value}").format(value=cfg.timezone),
        ]

        findings = self.state.findings()
        if findings:
            texts.append(_("The installation cannot start:"))
            texts.extend(f"  - {finding}" for finding in findings)

        for text in texts:
            row = Adw.ActionRow(title=text)
            group.add(row)
            self._summary_rows.append(row)

    # --- installation -------------------------------------------------

    def _show_message(self, heading: str, body: str) -> None:
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("ok", _("OK"))
        dialog.present(self)

    def _confirm_installation(self) -> None:
        dialog = Adw.AlertDialog(
            heading=_("Start installation now?"),
            # Mit beiden Listen: was verlorengeht und was entsteht. Der
            # Geraetename allein war die Rueckfrage, die man beantwortet,
            # waehrend man an eine andere Platte denkt - siehe
            # confirmation_body().
            body=confirmation_body(
                self.state.device,
                existing=self.state.device_partitions,
                layout=self.state.layout,
                encrypt=self.state.encrypt),
        )
        dialog.add_response("no", _("No"))
        dialog.add_response("yes", _("Yes"))
        dialog.set_response_appearance("yes", Adw.ResponseAppearance.DESTRUCTIVE)

        def _on_response(source, result, _user_data=None) -> None:
            response = source.choose_finish(result)
            if response == "yes":
                self._run_installation()
            else:
                self.toasts.add_toast(Adw.Toast.new(_("Installation cancelled.")))

        dialog.choose(self, None, _on_response)

    def _run_installation(self) -> None:
        """Start the installation on a worker thread and show progress.

        installer.core.runner.install() blocks for the entire archinstall
        run. Called straight from this callback it would block the GTK
        main loop with it: the window would stop repainting for minutes
        in the middle of erasing a disk, the compositor would offer to
        kill the "unresponsive" application, and the only output would go
        to a terminal the user cannot see.
        """
        self.back.set_sensitive(False)
        self.forward.set_sensitive(False)
        self._log_tail = LogTail(self._log_path)
        self._terminal = TerminalLog()
        self._shown = ""
        self.stack.set_visible_child_name(PROGRESS_PAGE)
        # The header keeps its shape here too, and says the true thing:
        # every step has been taken. Leaving it on "Step 7 of 7 -
        # Summary" while a disk is being erased would be the one moment
        # the band above the page disagrees with the page.
        self._step_title.set_text(_("Installing"))
        self._step_counter.set_text("")
        self._progress.set_fraction(1.0)
        self._tick_id = GLib.timeout_add(250, self._on_tick)
        threading.Thread(
            target=self._install_worker, args=(self.state.to_config(),), daemon=True
        ).start()

    def _install_worker(self, cfg: InstallConfig) -> None:
        """Runs OFF the main thread, so it must not touch a single widget.
        GLib.idle_add is the one way back in: it runs its callback on the
        main loop, where widgets may be touched again."""
        outcome = run_installation(cfg, self.install, log_path=self._log_path)
        GLib.idle_add(self._on_installation_finished, outcome)

    def _on_tick(self) -> bool:
        chunk = self._log_tail.read_new()
        if chunk:
            self._terminal.feed(chunk)
            self._show_log(self._terminal.text())

        fraction = self._terminal.progress()
        self._progress_bar.set_fraction(fraction)
        self._progress_bar.set_text(
            _("{percent}% - please do not switch the computer off.")
            .format(percent=int(fraction * 100)))
        return GLib.SOURCE_CONTINUE

    def _show_log(self, rendered: str) -> None:
        """Put the rendered log in the view without fighting the reader.

        THREE THINGS WENT WRONG HERE, all of them mine, all reported
        from the medium: the view stuck to its first line while entries
        poured in, older output disappeared, and scrolling up was undone
        a quarter of a second later.

        NUR DEN GEAENDERTEN SCHWANZ ERSETZEN, und das ist die dritte
        Fassung dieser Stelle.

        Die zweite haengte an, WENN der neue Text eine Verlaengerung des
        alten war, und ersetzte sonst alles. Gemeldet vom Medium am
        12.08.2026: "im installation wizard wackelt er die ganze zeit
        von oben nach unten buggy as hell".

        Der Grund ist pacman. Es zeichnet seine Fortschrittszeilen
        staendig neu - mit \r und mit ESC[nF, das den Cursor ueber
        bereits gezeigte Zeilen nach oben nimmt. Jede dieser Neuzeichnungen
        macht den neuen Text zu etwas, das KEINE Verlaengerung mehr ist,
        also lief der Ersetzungszweig - mehrmals je Sekunde. set_text()
        setzt den Blick an den Anfang, und die Zeile danach holt ihn ans
        Ende zurueck. Das ist das Wackeln: nicht ein Zeichenfehler,
        sondern zwei richtige Anweisungen in falscher Reihenfolge, vier
        Mal in der Sekunde.

        Dasselbe passiert ein zweites Mal, sobald der Log seine
        Zeilengrenze erreicht und vorne Zeilen wegfallen - dann ist der
        neue Text nie wieder eine Verlaengerung.

        Also wird verglichen, was WIRKLICH anders ist: die erste Zeile,
        in der sich alt und neu unterscheiden. Alles davor bleibt
        unangetastet - kein Loeschen, kein Einfuegen, kein Sprung. Bei
        einer Fortschrittszeile sind das die letzten ein bis zwei Zeilen
        von tausenden.

        FOLLOW ONLY IF ALREADY AT THE BOTTOM. That is what a log viewer
        owes its reader: keep up while they are watching the end, and
        hold still while they are reading something further up.

        A MARK THAT STAYS. The scroll used to be asked for with a mark
        created and deleted in the same breath - and GTK performs it
        after the layout has settled, by which time the mark was gone
        and the scroll with it. self._log_end is created once and moves
        with the text.
        """
        if rendered == self._shown:
            return

        adjustment = self._log_scroller.get_vadjustment()
        # Within one line of the bottom counts as being at the bottom;
        # a scrollbar rarely sits exactly on its maximum.
        follow = (adjustment.get_value() + adjustment.get_page_size()
                  >= adjustment.get_upper() - 32)

        buffer = self._log_view.get_buffer()
        _replace_tail(buffer, rendered)
        self._shown = rendered

        if follow:
            buffer.move_mark(self._log_end, buffer.get_end_iter())
            self._log_view.scroll_to_mark(self._log_end, 0.0, True, 0.0, 1.0)

    def _on_installation_finished(self, outcome: InstallationOutcome) -> bool:
        GLib.source_remove(self._tick_id)
        self._on_tick()  # whatever the log gained since the last tick
        self._progress_bar.set_fraction(1.0)
        self._progress_bar.set_text(outcome.heading)
        self._finish(outcome)
        return GLib.SOURCE_REMOVE

    def _finish(self, outcome: InstallationOutcome) -> None:
        """The end of the installer, which it did not have.

        REPORTED FROM THE MEDIUM: the installation finishes, a dialog
        says so, and there is nothing behind it. Back and Next were
        switched off when the erase began and are never switched on
        again, so the only way out of a FINISHED installation was the
        power switch - on a machine whose new system was sitting on the
        disk, ready.

        A successful run therefore ends where it should: a restart, into
        what was just installed. It is offered rather than done, because
        somebody may want to read the log first, and because pulling the
        medium is easier before the firmware asks for it again.

        A failed run offers no restart. There is nothing to restart INTO
        - the disk was erased and the installation did not finish - and
        a button that reboots a machine into nothing is worse than no
        button.
        """
        dialog = Adw.AlertDialog(heading=outcome.heading, body=outcome.message)
        if outcome.succeeded:
            dialog.add_response("later", _("Close"))
            dialog.add_response("restart", _("Restart now"))
            dialog.set_response_appearance(
                "restart", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_default_response("restart")
        else:
            dialog.add_response("later", _("Close"))

        def _on_response(source, result, _user_data=None) -> None:
            if source.choose_finish(result) == "restart":
                self._restart()

        dialog.choose(self, None, _on_response, None)

    def _restart(self) -> None:
        """Reboot, and say so if it does not happen.

        systemctl and not `reboot`: the live session runs under systemd
        and this is the request that goes through it rather than around
        it. If it fails - no privileges, no systemd - the user is told
        in the window instead of being left with a button that did
        nothing.
        """
        try:
            result = self._reboot(
                ["systemctl", "reboot"], capture_output=True, text=True)
        except OSError as exc:
            self._show_message(_("Restart failed"), str(exc))
            return
        if result.returncode != 0:
            self._show_message(
                _("Restart failed"),
                (result.stderr or result.stdout or "").strip()
                or _("The system did not accept the restart request."))


class ZeposInstallerApp(Adw.Application):
    """Owns the one PageState for the run and the real (non-test)
    dependencies InstallerWindow needs. Each is resolved here, not bound
    as a __init__ default, for the same reason installer.tui.app.main()
    resolves its own dependencies inside the function body: a default
    argument captures the real implementation at import time, before a
    caller (or a test) has any chance to inject a fake."""

    def __init__(
        self,
        *,
        wifi_backend: WifiBackend | None = None,
        list_disks: DiskLister | None = None,
        install: Installer | None = None,
        reboot: Callable[..., subprocess.CompletedProcess] | None = None,
        on_window_shown: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(application_id="org.zepos.Installer")
        self.state = PageState()
        self._wifi_backend = wifi_backend
        self._list_disks = list_disks
        self._install = install
        self._reboot = reboot
        self._on_window_shown = on_window_shown

    def _apply_branding(self) -> None:
        """ZeptronIT's colours and fonts, over libadwaita's defaults.

        Two halves and both are needed. The colour scheme has to be
        forced dark, or libadwaita picks light on a live medium where no
        portal and no desktop settings exist to ask - and a light
        libadwaita puts its own near-white behind widgets whose named
        colours this stylesheet has already made dark.

        APPLICATION priority, not USER: USER is above a user's own
        gtk.css and would override something somebody wrote for
        themselves. On this medium nobody has, and taking the higher
        priority anyway would be a habit that is wrong the first time it
        is copied.

        Never raises. A stylesheet that will not parse costs the brand;
        an exception here costs the installer, on the one screen a person
        has to reach in order to install anything at all.
        """
        try:
            Adw.StyleManager.get_default().set_color_scheme(
                Adw.ColorScheme.FORCE_DARK)
            provider = Gtk.CssProvider()
            provider.load_from_string(branding.css())
            display = Gdk.Display.get_default()
            if display is not None:
                Gtk.StyleContext.add_provider_for_display(
                    display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        except Exception as problem:                        # noqa: BLE001
            print(f"branding not applied: {problem}", file=sys.stderr)

    def do_activate(self) -> None:
        self._apply_branding()
        window = InstallerWindow(
            self,
            self.state,
            wifi_backend=self._wifi_backend or IwctlBackend(),
            list_disks=self._list_disks or _lsblk_list_disks,
            install=self._install or _run_install,
            reboot=self._reboot,
        )
        window.present()
        if self._on_window_shown is not None:
            # The window is up, so the graphical session works. Everything
            # after this point is an ordinary application failure and must
            # NOT be mistaken for "the graphical interface could not
            # start" - see installer/bin/zepos-install for what that
            # mistake costs.
            self._on_window_shown()


def main(
    argv: Sequence[str] | None = None,
    *,
    on_window_shown: Callable[[], None] | None = None,
) -> int:
    return ZeposInstallerApp(on_window_shown=on_window_shown).run(
        list(argv) if argv else []
    )


if __name__ == "__main__":
    sys.exit(main())
