# SPDX-License-Identifier: GPL-3.0-or-later
"""Das Fenster. GTK4, Layer-Shell, und sonst nichts.

WAS HIER ENTSCHIEDEN WIRD UND WAS NICHT
    Nichts. Welche Zeilen es gibt, in welcher Reihenfolge sie stehen und
    was ein Filter durchlaesst, steht in entries.py und wird hier nur
    abgefragt. Der Grund ist derselbe wie bei installer/gui/app.py: `gi`
    ist in .venv nicht installiert, also kann kein Test dieses Projekts
    eine Entscheidung erreichen, die in einem Widget-Rueckruf getroffen
    wird.

DIE TASTATUR IST DIE BEDIENUNG
    Tippen filtert, Pfeile waehlen, Enter bestaetigt, Escape schliesst.
    Die Pfeile muessen dabei die Liste bewegen, waehrend der Fokus im
    Eingabefeld steht - sonst muesste man zwischen Feld und Liste hin und
    her springen, um zu tippen und zu waehlen. Deshalb haengt der
    Tastaturregler am FENSTER und in der Fangphase (CAPTURE): er sieht
    die Taste, bevor irgendein Widget sie verbraucht.

WARUM DIE ANWENDUNG NON_UNIQUE IST
    Eine GtkApplication mit einer Anwendungskennung meldet diese Kennung
    beim Sitzungsbus an. Der zweite Aufruf findet dann den ersten,
    schickt ihm "activate" und beendet sich SOFORT - mit Rueckgabewert 0
    und ohne eine Zeile auf stdout. Fuer die fuenf dmenu-Aufrufer waere
    das ein Menue, das nichts zurueckgibt, und jedes von ihnen liest die
    leere Ausgabe als "abgebrochen". Der Nutzer sieht ein Fenster und
    sein Skript tut nichts.

    NON_UNIQUE meldet keine Kennung an. Zwei Auswahlfenster nebeneinander
    sind zwei Fenster, so wie es bei wofi auch war.
"""
from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
# Gdk ausdruecklich, obwohl Gtk 4.0 es mitbringt. PyGObject waehlt fuer
# einen Namensraum ohne Versionsangabe irgendeine installierte Fassung
# und schreibt eine PyGIWarning auf stderr - gemessen am 11.08.2026 beim
# blossen `import zepos_menu.window`. Auf einer Maschine mit gtk3 daneben
# waere das nicht nur eine Meldung, sondern die falsche Gdk.
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")

from gi.repository import Gdk, Gio, GObject, Gtk, Pango  # noqa: E402
from gi.repository import Gtk4LayerShell as LayerShell  # noqa: E402

from . import entries as model  # noqa: E402
from .options import Options  # noqa: E402

APPLICATION_ID = "org.zepos.Menu"

# Der Name, unter dem der Compositor die Flaeche fuehrt. Hyprland
# adressiert Layer-Shell-Flaechen ueber genau diesen Namen in
# `layerrule`, also ist er Teil der Schnittstelle und kein Detail.
LAYER_NAMESPACE = "zepos-menu"

_LAYERS = {
    "background": LayerShell.Layer.BACKGROUND,
    "bottom": LayerShell.Layer.BOTTOM,
    "top": LayerShell.Layer.TOP,
    "overlay": LayerShell.Layer.OVERLAY,
}

# Wie weit Bild-auf und Bild-ab springen. Zehn, weil das ungefaehr eine
# Fensterhoehe ist und nicht, weil es eine runde Zahl ist: die Liste ist
# bei 864 Pixeln Fensterhoehe und den Zeilenhoehen aus dem Stylesheet
# etwa zwoelf Zeilen hoch, und ein Sprung, der weiter geht als das
# Sichtbare, verliert den Nutzer.
PAGE_STEP = 10

# Wie viel vom Schirm dieses Fenster hoechstens nimmt.
#
# EINER VON VIER ABDRUECKEN EINER ZAHL, DIE IN src/sizes.py STEHT
#     Dort heisst sie MEASURE_MODAL_SHARE und ist begruendet; hier steht
#     sie noch einmal, weil zepos-menu nichts aus zepos-config
#     importiert - dieselbe bewusste Doppelung ueber eine Paketgrenze
#     hinweg wie SYSTEM_ROOT in menu/zepos_menu/index.py, und mit
#     derselben Absicherung: tests/menu/test_options.py haelt die beiden
#     Zahlen gegeneinander und faellt um, sobald eine von ihnen wandert.
#
#     Die anderen drei stehen in
#     src/templates/ags-overlay-utils.template,
#     plugins/hyprlaunch/include/hyprlaunch/Config.hpp und
#     plugins/hyprclipx/include/hyprclipx/Config.hpp. Bis zum 12.08.2026
#     waren es zwei, und die beiden eigenen Programme daneben kannten
#     die Regel gar nicht. tests/src/test_modal_rule.py haelt seither
#     alle vier an einer Stelle gegen die Groessentabelle - eine
#     Zusicherung je Abdruck faende genau den fuenften nicht, den jemand
#     ohne sie hinzufuegt.
#
# WAS SIE BEHEBT
#     GEMELDET am 12.08.2026: "das Suchfenster ist zu hoch". Die Vorgabe
#     ist 1536x864, also auf einem 1080er Schirm genau der ganze Platz,
#     den Kopf und Fuss uebriglassen - auf den Pixel, ohne Rand. Die
#     Vorgabe bleibt, was sie ist; sie ist jetzt eine OBERGRENZE fuer
#     grosse Schirme statt einer Zusage fuer alle.
#
#     Gedeckelt wird gegen den ARBEITSBEREICH und nicht gegen die
#     Aufloesung: gdk_monitor_get_geometry() liefert den ganzen Schirm,
#     get_geometry ist unter Wayland aber das, was es gibt - eine
#     exklusive Zone kennt der Client nicht. Die Haelfte ist deshalb so
#     gewaehlt, dass sie auch dann noch Luft laesst, wenn oben und unten
#     ein Streifen weggeht.
MODAL_SHARE = 0.5


def capped(width: int, height: int) -> tuple[int, int]:
    """Die gewuenschte Groesse, begrenzt auf einen Anteil des Schirms.

    Ohne Anzeige - beim Uebersetzen, in einem Test ohne Monitor - bleibt
    die gewuenschte Groesse stehen: eine Begrenzung gegen einen Schirm,
    den es nicht gibt, waere eine erfundene Zahl.
    """
    display = Gdk.Display.get_default()
    monitors = display.get_monitors() if display else None
    if not monitors or monitors.get_n_items() == 0:
        return width, height

    # Der KLEINSTE angeschlossene Schirm, je Kante einzeln.
    #
    # WARUM NICHT DER ERSTE, WIE ES HIER BIS ZUM 12.08.2026 STAND
    #     Weil dieser Prozess nicht weiss, auf welchem Schirm sein
    #     Fenster aufgeht: die Layer-Shell setzt es ohne set_monitor()
    #     auf den, den der Compositor gerade fuer den aktiven haelt, und
    #     den kann er nicht erfragen. "Der erste" war deshalb eine
    #     Naeherung - und an einem Notebook mit 1080 Zeilen neben einem
    #     4K-Schirm ist sie in der Haelfte der Faelle die falsche: 2160
    #     mal 0.5 sind 1080, also der ganze Notebookschirm.
    #
    #     Eine Grenze, die nur auf einem von zwei Schirmen gilt, ist
    #     keine Grenze. Der kleinste gilt auf allen. Er kostet auf dem
    #     grossen Schirm ein etwas kleineres Fenster, und das ist der
    #     billigere von zwei Fehlern.
    #
    #     Dieselbe Ueberlegung und dieselbe Wahl stehen in
    #     plugins/hyprlaunch/src/LauncherRenderer.cpp; hyprclipx braucht
    #     sie nicht, weil es den Schirm der Schreibmarke kennt.
    #
    # Breite und Hoehe getrennt, weil ein hoher schmaler Schirm neben
    # einem breiten flachen sonst je nach Kante den falschen stellte.
    narrowest = min(monitors.get_item(index).get_geometry().width
                    for index in range(monitors.get_n_items()))
    shortest = min(monitors.get_item(index).get_geometry().height
                   for index in range(monitors.get_n_items()))
    return (min(width, int(narrowest * MODAL_SHARE)),
            min(height, int(shortest * MODAL_SHARE)))


class Row(GObject.Object):
    """Eine Zeile im Modell.

    Gtk.StringObject waere fertig da und traegt genau eine Zeichenkette.
    Eine Zeile hat aber drei Dinge - angezeigter Text, ausgegebener Wert,
    Symbol - und beim Starter sind die ersten beiden verschieden.
    """

    __gtype_name__ = "ZeposMenuRow"

    def __init__(self, entry: model.Entry) -> None:
        super().__init__()
        self.entry = entry


class MenuWindow(Gtk.ApplicationWindow):
    """Eingabezeile oben, Liste darunter, mehr ist es nicht."""

    def __init__(self, application: Gtk.Application, options: Options,
                 on_chosen, free_text: bool) -> None:
        super().__init__(application=application)

        self.options = options
        self._on_chosen = on_chosen
        self._free_text = free_text
        self._answered = False

        self.set_default_size(*capped(options.width, options.height))
        self.set_title(LAYER_NAMESPACE)
        self.set_name("zepos-menu")

        self._install_layer_shell()

        self.search = Gtk.Entry()
        self.search.set_name("search")
        self.search.set_placeholder_text(options.prompt)
        self.search.set_hexpand(True)
        if options.password:
            self.search.set_visibility(False)
            self.search.set_input_purpose(Gtk.InputPurpose.PASSWORD)

        self.store = Gio.ListStore(item_type=Row)

        self.filter = Gtk.CustomFilter.new(self._row_matches)
        filtered = Gtk.FilterListModel(model=self.store, filter=self.filter)
        self.selection = Gtk.SingleSelection(model=filtered)
        self.selection.set_autoselect(True)
        self.selection.set_can_unselect(False)

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._setup_row)
        factory.connect("bind", self._bind_row)

        self.list = Gtk.ListView(model=self.selection, factory=factory)
        self.list.set_name("list")
        self.list.set_single_click_activate(True)
        self.list.connect("activate", self._on_row_activated)

        scroller = Gtk.ScrolledWindow()
        scroller.set_name("scroll")
        scroller.set_child(self.list)
        scroller.set_vexpand(True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        # Der Text fuer "nichts gefunden" - und er erscheint NUR, wenn es
        # ueberhaupt etwas zu finden gab. printer-manager oeffnet dieses
        # Fenster mit leerem stdin, um einen Druckernamen tippen zu
        # lassen; "Keine Treffer" ueber einem leeren Feld waere dort eine
        # Fehlermeldung ueber eine Eingabe, die der Nutzer noch gar nicht
        # gemacht hat.
        self._has_rows = False
        self.message = Gtk.Label(label="Keine Treffer")
        self.message.set_name("message")
        self.message.set_visible(False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_name("outer-box")
        box.append(self.search)
        box.append(self.message)
        box.append(scroller)
        self.set_child(box)

        # Erst jetzt, wo Filter und Auswahl stehen: ein "changed", das
        # vor ihnen kaeme, liefe in ein Attribut, das es noch nicht gibt.
        self.search.connect("changed", self._on_search_changed)
        # Enter im Eingabefeld. Nicht dasselbe wie Enter im
        # Tastaturregler unten: ein Gtk.Entry verbraucht Return selbst
        # und meldet es als "activate", und ohne diese Zeile waere die
        # haeufigste Taste des ganzen Programms die einzige ohne Wirkung.
        self.search.connect("activate", lambda _entry: self.accept())

        self.key_controller = Gtk.EventControllerKey()
        self.key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(self.key_controller)

        self._update_message()

    # -- Layer-Shell ---------------------------------------------------

    def _install_layer_shell(self) -> None:
        """Vor dem Realisieren, sonst wirkt es nicht.

        WARUM ERST DER ANZEIGETYP UND DANN is_supported()
            gtk4_layer_shell_is_supported() prueft intern
            GDK_IS_WAYLAND_DISPLAY und meldet den Fehlschlag als
            g_critical. Gemessen am 11.08.2026 unter gtk4-broadwayd:

                CRITICAL **: init_and_get_layer_shell_global:
                assertion 'GDK_IS_WAYLAND_DISPLAY(gdk_display)' failed

            Eine kritische Meldung ist in diesem Projekt ein Testfehler -
            tests/installer/test_gui_headless.py faellt auf jeder - und
            sie waere hier auch falsch: dass eine HTML5-Anzeige keine
            Layer-Shell hat, ist kein Fehler, sondern die Antwort.

        Ohne Layer-Shell bleibt es ein gewoehnliches Fenster. Das ist
        ausdruecklich richtig - die Alternative waere ein Starter, der
        auf jeder Anzeige ohne Layer-Shell gar nicht erst aufgeht.

        Die Zeile auf stderr steht trotzdem da. wlogout zeigt, was
        passiert, wenn sie fehlt: es nimmt `--protocol layer-shell`
        entgegen, faellt still auf xdg zurueck und wird zu einem
        gewoehnlichen Fenster, das der Compositor platziert - siehe
        packaging/wlogout/PKGBUILD.
        """
        display = Gdk.Display.get_default()
        wayland = display is not None and \
            display.__gtype__.name == "GdkWaylandDisplay"
        if not wayland or not LayerShell.is_supported():
            print("zepos-menu: keine Layer-Shell auf dieser Anzeige - "
                  "das Fenster ist ein gewoehnliches Fenster",
                  file=sys.stderr)
            return

        LayerShell.init_for_window(self)
        LayerShell.set_namespace(self, LAYER_NAMESPACE)
        LayerShell.set_layer(self, _LAYERS[self.options.layer])
        # EXCLUSIVE und nicht ON_DEMAND: das Fenster wird ueber eine
        # Tastenkombination geoeffnet, also ist die Tastatur schon in
        # Benutzung, und ON_DEMAND verlangte einen Mausklick, bevor die
        # erste Taste ankommt.
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.EXCLUSIVE)

    # -- Liste ---------------------------------------------------------

    def _setup_row(self, _factory, item: Gtk.ListItem) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.set_name("entry")
        image = Gtk.Image()
        image.set_name("img")
        image.set_pixel_size(self.options.image_size)
        label = Gtk.Label(xalign=0.0)
        label.set_name("text")
        # Abschneiden statt umbrechen: der Zwischenablageverlauf enthaelt
        # Zeilen beliebiger Laenge, und eine Zeile, die die halbe Liste
        # hoch ist, verdraengt alle anderen aus dem Fenster.
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_single_line_mode(True)
        label.set_hexpand(True)
        # Die Taste rechts. Sie steht in JEDER Zeile im Baum, auch in
        # denen ohne Taste - ein Widget, das je nach Zeile da ist oder
        # nicht, muesste bei jedem Binden angelegt und weggeworfen
        # werden, und die Liste wird beim Tippen fortlaufend neu
        # gebunden. Sichtbar ist es nur, wo es etwas zu zeigen gibt.
        hint = Gtk.Label(xalign=1.0)
        hint.set_name("hint")
        hint.set_single_line_mode(True)
        box.append(image)
        box.append(label)
        box.append(hint)
        item.set_child(box)

    def _bind_row(self, _factory, item: Gtk.ListItem) -> None:
        row: Row = item.get_item()
        box = item.get_child()
        image = box.get_first_child()
        label = image.get_next_sibling()
        hint = label.get_next_sibling()
        # set_text und nicht set_markup: allow_markup=true stand in
        # wofis erzeugter Konfiguration, und eine SSID oder ein
        # Zwischenablagetext mit "&" darin ist als Markup ungueltig -
        # Pango zeigt dann die Rohzeile oder gar nichts.
        label.set_text(row.entry.label)
        hint.set_text(row.entry.hint or "")
        hint.set_visible(bool(row.entry.hint))
        if row.entry.icon:
            image.set_from_gicon(Gio.Icon.new_for_string(row.entry.icon))
            image.set_visible(True)
        else:
            image.set_visible(False)

    def _row_matches(self, row: Row) -> bool:
        return model.matches(row.entry.searchable, self.search.get_text(),
                             self.options.insensitive)

    def _on_search_changed(self, _entry) -> None:
        self.filter.changed(Gtk.FilterChange.DIFFERENT)
        if self.selection.get_n_items():
            self.selection.set_selected(0)
        self._update_message()

    def _update_message(self) -> None:
        self.message.set_visible(
            self._has_rows and self.selection.get_n_items() == 0)

    def fill(self, rows: list[model.Entry]) -> None:
        """Die Zeilen hineingeben - NACH present(), siehe MenuApplication.

        Ein zweiter Aufruf ersetzt nicht, er ergaenzt; es gibt genau
        einen Aufrufer und der ruft einmal. Waeren es mehr, muesste hier
        auch die getroffene Auswahl neu bedacht werden.
        """
        for entry in rows:
            self.store.append(Row(entry))
        self._has_rows = self._has_rows or bool(rows)
        if self.selection.get_n_items():
            self.selection.set_selected(0)
        self._update_message()

    # -- Tastatur ------------------------------------------------------

    def _move(self, delta: int) -> None:
        total = self.selection.get_n_items()
        if not total:
            return
        current = self.selection.get_selected()
        if current == Gtk.INVALID_LIST_POSITION:
            current = 0
        else:
            current = max(0, min(total - 1, current + delta))
        self.selection.set_selected(current)
        self.list.scroll_to(current, Gtk.ListScrollFlags.NONE, None)

    def _on_key_pressed(self, _controller, keyval: int, _keycode: int,
                        _state) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.cancel()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_ISO_Enter):
            self.accept()
            return True
        if keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
            self._move(1)
            return True
        if keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
            self._move(-1)
            return True
        if keyval in (Gdk.KEY_Page_Down, Gdk.KEY_KP_Page_Down):
            self._move(PAGE_STEP)
            return True
        if keyval in (Gdk.KEY_Page_Up, Gdk.KEY_KP_Page_Up):
            self._move(-PAGE_STEP)
            return True
        return False

    # -- Antwort -------------------------------------------------------

    def _on_row_activated(self, _list, position: int) -> None:
        self.selection.set_selected(position)
        self.accept()

    def accept(self) -> None:
        """Die getroffene Auswahl, sonst der getippte Text.

        Der zweite Fall ist kein Rueckfall, sondern eine benutzte
        Betriebsart: `printf '' | zepos-menu --dmenu --prompt "Name"` in
        printer-manager-config.template hat gar keine Zeilen und ist
        allein dafuer da, einen Druckernamen entgegenzunehmen, und
        floating-window-manager fragt genauso nach einem Layoutnamen.
        wofi verhielt sich so, und die Tests der beiden Vorlagen messen
        genau das.

        Im Starter gibt es diesen Fall nicht: dort ist getippter Text,
        der auf nichts passt, keine Anwendung. Enter tut dann nichts, und
        das Fenster bleibt stehen - was der Nutzer als "der Name stimmt
        nicht" liest, waehrend ein geschlossenes Fenster ohne Wirkung
        wie ein Absturz aussieht.
        """
        if self._answered:
            return
        row = self.selection.get_selected_item()
        if row is not None:
            chosen = row.entry
        elif self._free_text and self.search.get_text():
            typed = self.search.get_text()
            chosen = model.Entry(label=typed, value=typed)
        else:
            return
        self._answered = True
        self._on_chosen(chosen)
        self.close()

    def cancel(self) -> None:
        if self._answered:
            return
        self._answered = True
        self.close()


class MenuApplication(Gtk.Application):
    def __init__(self, options: Options, load_rows, on_chosen,
                 free_text: bool, on_window_shown=None) -> None:
        super().__init__(application_id=APPLICATION_ID,
                         flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.options = options
        self._load_rows = load_rows
        self._on_chosen = on_chosen
        self._free_text = free_text
        self._on_window_shown = on_window_shown
        self.window: MenuWindow | None = None

    def load_stylesheet(self) -> list[str]:
        """Das erzeugte Stylesheet, und jeder Fehler darin auf stderr.

        DAS IST DER FEHLER, DEN DIESES PROGRAMM ERBT.
            wofis erzeugtes style.css setzte seine Farben ueber
            CSS-Variablen, die GTK3 nicht kannte. GTK verwirft eine
            Deklaration, die es nicht versteht, behaelt den Rest und
            meldet nichts, was jemand sieht: 39 Parserfehler, gemessen am
            11.08.2026, und ein Starter, der seit jeher in GTKs
            Standardgrau erschien, waehrend die Vorlage aussah, als
            setzte sie Farben.

            Deshalb geht hier jeder Parserfehler nach stderr, und
            deshalb misst tests/menu/test_menu_headless.py, dass es
            keinen gibt.
        """
        problems: list[str] = []
        path = self.options.style_sheet
        if not path.is_file():
            return problems

        provider = Gtk.CssProvider()

        def note(_provider, section, error) -> None:
            problems.append(f"{section.to_string()}: {error.message}")

        provider.connect("parsing-error", note)
        provider.load_from_path(str(path))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        # "Stylesheet" steht ausdruecklich im Text und nicht nur der
        # Pfad: stderr traegt auch die Zeile ueber die fehlende
        # Layer-Shell, und ein Test, der bloss nach "zepos-menu:" sucht,
        # faende die und meldete einen Parserfehler, den es nicht gibt.
        for problem in problems:
            print(f"zepos-menu: Stylesheet {path}: {problem}",
                  file=sys.stderr)
        return problems

    def do_activate(self) -> None:
        """Fenster zuerst, Inhalt danach - und die Reihenfolge ist gemessen.

        WARUM DIE ZEILEN ERST NACH present() GELADEN WERDEN
            Der Starter liest dafuer jede .desktop-Datei aus
            XDG_DATA_HOME und XDG_DATA_DIRS. Das ist die einzige Arbeit
            in diesem Programm, die mit der Zahl der installierten
            Anwendungen waechst, und sie vor dem ersten Bild zu erledigen
            heisst, eine Taste zu druecken und zu warten.

            Der zweite Grund ist ein Klemmer in GTK selbst. Gemessen am
            11.08.2026, GTK 4.22.4 auf gtk4-broadwayd, an einem
            Nachbau aus rund fuenfunddreissig Zeilen ohne eine Zeile
            ZepOS darin:

                Gio.AppInfo.get_all() vor present()   4 von 12 Laeufen
                                                      blieben in
                                                      gtk_window_present()
                                                      stehen, einzelner
                                                      Thread, kein Ende
                ohne den Aufruf                       0 von 12
                der Aufruf nach present()             0 von 12

            Es ist also kein Fehler dieses Programms und er trifft
            Wayland nicht - aber eine Reihenfolge, die einen Backend des
            eigenen Toolkits verklemmt, ist die schlechtere von zwei
            Reihenfolgen, die sonst gleich viel kosten.

        Ein Enter in den ersten Bildern ist dabei folgenlos: im Starter
        nimmt accept() keinen getippten Text an (free_text ist aus), also
        tut die Taste ueber einer noch leeren Liste nichts.
        """
        self.load_stylesheet()
        self.window = MenuWindow(self, self.options,
                                 self._on_chosen, self._free_text)
        self.window.present()
        # Der Fokus ausdruecklich auf das Eingabefeld. Ohne das nimmt ihn
        # die Liste, und der erste getippte Buchstabe waere eine
        # Typenauswahl in der Liste statt eines Filters.
        self.window.set_focus(self.window.search)
        self.window.fill(self._load_rows())
        if self._on_window_shown is not None:
            self._on_window_shown(self.window)
