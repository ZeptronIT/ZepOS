# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Seite "Bildschirme": eine Zeichnung, die man schiebt, und was
danach passiert.

WARUM EINE EIGENE DATEI NEBEN app.py
    app.py baut ZEILEN - Adw.SpinRow, Adw.ComboRow, Adw.ActionRow -, und
    die vier anderen Seiten bestehen aus nichts anderem. Diese hier
    bringt ein EIGENES WIDGET mit: eine Zeichenflaeche mit Zeigergesten,
    hundert Zeilen Zeichencode und einer Umrechnung zwischen
    Bildschirm- und Zeichnungspixeln. Sie zwischen die Reglerzeilen zu
    legen hiesse, die vier kurzen Seiten unter der einen langen zu
    begraben.

    Die Trennung, die dieses Projekt wirklich durchhaelt, ist eine
    andere und bleibt: KEINE Entscheidung in einer Widget-Datei. Was ein
    Schirm ist, wie er einrastet, was in die Datei kommt, was angewandt
    wird und wie zurueckgenommen wird, steht vollstaendig in
    src/displays.py und ist dort ohne Anzeige gemessen. Hier steht, was
    man anfasst.

WARUM DIESE SEITE IN DIESES FENSTER GEHOERT UND KEIN EIGENES PROGRAMM IST
    settings/zepos_settings_gui/model.py hat die Monitore ausdruecklich
    NICHT aufgenommen, mit dieser Begruendung: "VPN, Ton, Uhren,
    Monitore - alle vier haben schon eine Oberflaeche: [...]
    nwg-displays. Eine Einstellungs-Anwendung, die sie nachbaut,
    verdoppelt Pflege statt Auffindbarkeit zu schaffen."

    Der Grund ist am 12.08.2026 entfallen: nwg-displays war das letzte
    GTK3-Programm des Systems und ist entfernt. Damit hatten die
    Monitore keine Oberflaeche mehr, und die Regel dieser Anwendung -
    "angeboten wird, was ein Mensch an seinem eigenen Schreibtisch
    aendert, was beim Aendern ein erzeugtes Byte bewegt, und wovon die
    Anwendung sagen kann, was es kostet" - trifft auf sie in allen drei
    Teilen zu.

    Ein EIGENES Programm waere der zweite Ort zum Suchen, gegen den
    dieselbe Datei an drei Stellen argumentiert, plus eine zweite
    .desktop-Datei, ein zweites Paket und ein zweiter GTK4-Stapel. Und es
    haette fuer das einzige, was hier wirklich zaehlt, NICHTS gebracht:
    der Rueckfall liegt ohnehin in einem eigenen Prozess
    (zepos-displays-guard), weil er den Absturz DES PROGRAMMS ueberleben
    muss - egal ob dieses Programm ein Einstellungsfenster ist oder ein
    eigenes.

WAS SOFORT PASSIERT UND WAS ERST AUF EINEN KNOPF
    Nichts von dem, was man hier verstellt, wirkt beim Verstellen. Es
    gibt einen Knopf "Anwenden", und der ist ein anderer als das
    "Speichern" oben im Fenster: dieses schreibt Einstellungen, jener
    stellt Bildschirme um. Dieselbe Unterscheidung wie auf den Seiten
    "Thema" und "Aktualisierung", die auch nicht am Speichern haengen,
    und aus demselben Grund: sie schreiben nicht in user-settings.json.

WARUM DIESE SEITE KEIN `runner` HAT, ANDERS ALS DER REST DES FENSTERS
    Der `runner` des Fensters gibt es, weil `zepos-generate --all` die
    Leiste und AGS des Entwicklers beenden wuerde - ein Testlauf darf ihn
    nicht wirklich rufen. `hyprctl` ist nicht dieser Fall: es wird hier
    WIRKLICH gerufen, und der Test stellt ihm einen Stellvertreter auf
    PATH. Anders ginge es auch nicht - der Waechter ist ein eigener
    Prozess und ruft sein eigenes `hyprctl`, an jedem `runner` vorbei.
    Ein Test mit einem falschen `runner` maesse also nur die Haelfte, und
    zwar genau die Haelfte, die im Ernstfall nicht zaehlt.
"""
from __future__ import annotations

import math
from contextlib import contextmanager

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

import displays  # noqa: E402
import sizes  # noqa: E402

from . import model  # noqa: E402

# Wie viele Bildschirmpixel hoechstens auf einen Zeichnungspixel gehen.
# Die Zeichnung passt sich der Flaeche an, die sie bekommt (siehe
# DeskArea.factor()); diese Zahl ist nur die Obergrenze, damit ein
# einzelner Laptopschirm die Flaeche nicht in Postergroesse fuellt.
#
# Die Vorlage nennt dieselbe Groesse `view-scale` und liefert 0.15 aus,
# also 1:6.7 (tools.py:481); dort ist sie fest und vom Nutzer als Regler
# einstellbar. Hier wird sie ausgerechnet, weil eine feste Zahl auf einem
# Schreibtisch mit drei 4K-Schirmen aus der Flaeche laeuft - und ein
# Regler dafuer waere eine Einstellung, um eine Einstellung sichtbar zu
# machen.
MAXIMUM_MAGNIFICATION = 1 / 6

# Wie hoch die Zeichnung mindestens ist, in Pixeln vor dem Massstab des
# Nutzers. Ein Schreibtisch aus einem einzigen Schirm braucht wenig; die
# Flaeche darf trotzdem nicht auf Zeilenhoehe schrumpfen, weil man in sie
# hineinziehen koennen muss.
CANVAS_HEIGHT = 240

# Die acht Transformationen von wl_output, in der Reihenfolge ihrer
# Nummern - der Index IST der Wert, der in die Zeile kommt.
TRANSFORMS = (
    "Normal",
    "90 Grad",
    "180 Grad (auf dem Kopf)",
    "270 Grad",
    "Gespiegelt",
    "Gespiegelt, 90 Grad",
    "Gespiegelt, 180 Grad",
    "Gespiegelt, 270 Grad",
)

# Die Massstaebe, die angeboten werden.
#
# Eine Liste und kein Drehknopf, und das ist eine Messung: Hyprland lehnt
# einen Massstab ab, bei dem Breite oder Hoehe nicht ganzzahlig aufgehen,
# und meldet das als Konfigurationsfehler. Ein Drehknopf in Schritten von
# 0.05 boete ueber dreissig Zahlen an, von denen die meisten fuer einen
# gegebenen Schirm falsch sind. Diese sechs sind Vielfache von 1/4 und
# gehen auf jeder gaengigen Aufloesung auf.
SCALES = (1.0, 1.25, 1.5, 1.75, 2.0, 3.0)


def _rung(section: dict, index: int) -> int:
    """Eine Sprosse der Abstandsleiter, in Pixeln, mit dem Faktor darin."""
    name = f"{sizes.SPACE_PREFIX}{sizes.SPACE_LADDER[index]}"
    return int(model.size_number(sizes.value_of(name, section)))


def _radius(section: dict) -> float:
    """Die Ecke einer Flaeche - dieselbe Sprosse wie in style.py.

    Ein eckiges Rechteck auf einer Seite voller runder Zeilen sieht aus
    wie aus einem anderen Programm.
    """
    return model.size_number(
        sizes.value_of(f"{sizes.RADIUS_PREFIX}PANEL", section))


def _font(section: dict) -> float:
    return model.size_number(
        sizes.value_of(f"{sizes.FONT_PREFIX}BODY", section))


class DeskArea(Gtk.DrawingArea):
    """Der Schreibtisch als Zeichnung, mit den Schirmen darauf.

    Eine Gtk.DrawingArea und kein Kasten voller Knoepfe, wie die Vorlage
    es macht (ein Gtk.Fixed mit einem Gtk.Button je Schirm,
    main.py:395). Der Grund ist GTK4: das Ziehen lief dort ueber
    `button_press_event` und `motion_notify_event` - Ereignisse, die GTK4
    nicht mehr kennt. Was GTK4 hat, sind Gesten, und die haengen ohnehin
    am Widget und nicht am Kind. Ein Rechteck zu zeichnen ist dann
    weniger Code als ein Knopf, der wie ein Rechteck aussehen soll.

    Die Zeichnung ENTSCHEIDET nichts: sie rechnet Zeigerkoordinaten in
    Bildschirmpixel um und reicht sie an displays.Desk weiter.
    """

    def __init__(self, desk: displays.Desk, section: dict, on_change) -> None:
        super().__init__(hexpand=True, vexpand=True)
        self.desk = desk
        self.section = section
        self.on_change = on_change
        self.selected = desk.placements[0].name if desk.placements else ""
        self.dragging = ""
        self.grab = (0, 0)

        self.set_draw_func(self._draw)

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_begin)
        drag.connect("drag-update", self._on_update)
        self.add_controller(drag)

    # ---- Umrechnung ------------------------------------------------

    def extent(self) -> tuple[int, int, int, int]:
        """Das umschliessende Rechteck aller Schirme, in Bildschirmpixeln.

        Auch die ABGESCHALTETEN gehen ein, anders als bei
        displays.normalised(): sie werden gezeichnet - blass und
        durchgestrichen -, und ein Schirm, den man wieder einschalten
        will, muss sichtbar sein, um angeklickt zu werden.
        """
        items = self.desk.placements
        if not items:
            return 0, 0, 1, 1
        left = min(item.x for item in items)
        top = min(item.y for item in items)
        right = max(item.right for item in items)
        bottom = max(item.bottom for item in items)
        return left, top, max(1, right - left), max(1, bottom - top)

    def factor(self) -> float:
        """Wie viele Zeichnungspixel ein Bildschirmpixel ist.

        So gross wie moeglich, aber nie groesser als
        MAXIMUM_MAGNIFICATION und nie so gross, dass der Schreibtisch aus
        der Flaeche laeuft. Ausgerechnet und nicht eingestellt: die
        Zeichnung soll den Schreibtisch zeigen, den es gibt, und nicht
        den, fuer den ein Regler zuletzt stand.
        """
        _, _, width, height = self.extent()
        border = 2 * _rung(self.section, 2)
        available_width = max(1, self.get_width() - border)
        available_height = max(1, self.get_height() - border)
        return min(MAXIMUM_MAGNIFICATION,
                   available_width / width, available_height / height)

    def _offset(self) -> tuple[float, float]:
        _, _, width, height = self.extent()
        factor = self.factor()
        return ((self.get_width() - width * factor) / 2,
                (self.get_height() - height * factor) / 2)

    def to_screen(self, x: float, y: float) -> tuple[int, int]:
        """Von Zeichnungs- in Bildschirmkoordinaten."""
        left, top, _, _ = self.extent()
        factor = self.factor()
        offset_x, offset_y = self._offset()
        return (round((x - offset_x) / factor + left),
                round((y - offset_y) / factor + top))

    def to_canvas(self, x: int, y: int) -> tuple[float, float]:
        left, top, _, _ = self.extent()
        factor = self.factor()
        offset_x, offset_y = self._offset()
        return ((x - left) * factor + offset_x, (y - top) * factor + offset_y)

    def at(self, x: float, y: float) -> str:
        """Welcher Schirm unter diesem Punkt liegt, oder "".

        Von hinten nach vorn durchsucht, damit bei zwei uebereinander-
        liegenden Schirmen der zuletzt gezeichnete gewinnt - also der,
        den man auch sieht.
        """
        screen_x, screen_y = self.to_screen(x, y)
        for item in reversed(self.desk.placements):
            if (item.x <= screen_x < item.right
                    and item.y <= screen_y < item.bottom):
                return item.name
        return ""

    # ---- Ziehen ----------------------------------------------------

    def _on_begin(self, gesture, start_x, start_y) -> None:
        name = self.at(start_x, start_y)
        if not name:
            return
        self.select(name)
        self.dragging = name
        item = self.desk.get(name)
        # Wo INNERHALB des Schirms angefasst wurde. Ohne diesen Griff
        # spraenge der Schirm beim ersten Millimeter mit seiner linken
        # oberen Ecke unter den Zeiger.
        screen_x, screen_y = self.to_screen(start_x, start_y)
        self.grab = (screen_x - item.x, screen_y - item.y)

    def _on_update(self, gesture, offset_x, offset_y) -> None:
        if not self.dragging:
            return
        found, start_x, start_y = gesture.get_start_point()
        if not found:
            return
        self.drag_to(self.dragging, start_x + offset_x, start_y + offset_y)

    def drag_to(self, name: str, x: float, y: float) -> None:
        """Diesen Schirm so schieben, dass der Griff unter (x, y) liegt.

        Oeffentlich, aus demselben Grund, aus dem
        SettingsWindow.apply_now() es ist: das kopflose Kind in tests/
        greift hier hinein. Einer Gtk.GestureDrag von aussen eine
        Bewegung unterzuschieben hiesse, GTKs Gestenerkennung zu messen
        statt dieser Anwendung - und ohne einen Griff waere die einzige
        pruefbare Aussage ueber diese Zeichnung, dass sie gezeichnet
        wird.
        """
        screen_x, screen_y = self.to_screen(x, y)
        self.desk.move(name, screen_x - self.grab[0], screen_y - self.grab[1])
        self.queue_draw()
        self.on_change()

    def select(self, name: str) -> None:
        self.selected = name
        self.queue_draw()
        self.on_change()

    # ---- Zeichnen --------------------------------------------------

    def _draw(self, area, context, width, height) -> None:
        for item in self.desk.placements:
            self._draw_one(context, item)

    def _draw_one(self, context, item: displays.Placement) -> None:
        factor = self.factor()
        x, y = self.to_canvas(item.x, item.y)
        w = max(1.0, item.displayed_width * factor)
        h = max(1.0, item.displayed_height * factor)
        radius = min(_radius(self.section), w / 4, h / 4)

        # Die Farbe kommt aus dem Stilblatt und nicht aus brand.py: ZepOS
        # erzeugt ~/.config/gtk-4.0/gtk.css aus brand.py, GTK liest sie
        # beim Start JEDER GTK4-Anwendung, und diese Flaechen sollen
        # dieselben Toene tragen wie die Zeilen darunter. Ein zweiter
        # Satz Zahlen hier waere die Kopie, gegen die style.py
        # argumentiert.
        colour = self.get_color()
        chosen = item.name == self.selected

        _rounded(context, x, y, w, h, radius)
        context.set_source_rgba(
            colour.red, colour.green, colour.blue,
            (0.38 if chosen else 0.18) if item.enabled else 0.06)
        context.fill_preserve()
        context.set_source_rgba(colour.red, colour.green, colour.blue,
                                1.0 if chosen else 0.45)
        context.set_line_width(3.0 if chosen else 1.5)
        context.stroke()

        if not item.enabled:
            # Durchgestrichen. Eine blasse Flaeche allein sagt "weiter
            # hinten" und nicht "aus" - und der Unterschied ist genau
            # der, den diese Zeichnung zeigen muss.
            context.set_line_width(1.5)
            context.move_to(x, y)
            context.line_to(x + w, y + h)
            context.move_to(x + w, y)
            context.line_to(x, y + h)
            context.stroke()

        context.set_source_rgba(colour.red, colour.green, colour.blue, 1.0)
        context.set_font_size(_font(self.section))
        reach = context.text_extents(item.name)
        context.move_to(x + (w - reach.width) / 2, y + (h + reach.height) / 2)
        context.show_text(item.name)


def _rounded(context, x, y, w, h, radius) -> None:
    """Ein Rechteck mit runden Ecken, aus vier Boegen. Cairo hat keins."""
    context.new_sub_path()
    context.arc(x + w - radius, y + radius, radius, -math.pi / 2, 0)
    context.arc(x + w - radius, y + h - radius, radius, 0, math.pi / 2)
    context.arc(x + radius, y + h - radius, radius, math.pi / 2, math.pi)
    context.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
    context.close_path()


def _notice(title: str, body: str) -> Adw.PreferencesGroup:
    """Eine Seite, die nur erklaert, warum sie nichts anbietet.

    Eine leere Flaeche waere die schlechteste Antwort auf "der Compositor
    laeuft nicht": sie sieht aus wie ein Fehler dieser Anwendung.
    """
    group = Adw.PreferencesGroup(title=title)
    group.add(Adw.ActionRow(title=body, title_lines=0))
    return group


class ScreensPage(Gtk.Box):
    """Die Seite: Zeichnung oben, die Regler des gewaehlten Schirms unten.

    Kein Adw.PreferencesPage, obwohl die anderen vier es sind: eine
    Zeichnung, die waechst, ist keine Zeile, und eine
    Adw.PreferencesGroup, die eine hexpandierende Flaeche traegt, gibt ihr
    die Breite einer Zeile. Die Gruppen DARUNTER sind welche.
    """

    def __init__(self, section: dict, *, on_report=None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL,
                         spacing=_rung(section, 3))
        self.section = section
        self.on_report = on_report or (lambda text: None)
        self.attempt = None
        self.countdown = 0
        self.countdown_source = 0
        self.dialog = None
        self.report = ""
        self.rows: dict[str, Gtk.Widget] = {}
        self.mode_options: list[displays.Mode] = []
        self.scale_options: list[float] = []
        # Fuer welchen Schirm die zwei Listen zuletzt gebaut wurden.
        # Siehe _rebuild_lists(): sie neu zu bauen, wenn sich nichts an
        # der Auswahl geaendert hat, war ein Fenster, das nie fertig
        # wurde.
        self._listed = ""
        self.desk: displays.Desk | None = None
        self.area: DeskArea | None = None
        self.apply_button: Gtk.Button | None = None
        self._quiet = False

        margin = _rung(section, 3)
        for setter in (self.set_margin_top, self.set_margin_bottom,
                       self.set_margin_start, self.set_margin_end):
            setter(margin)

        try:
            self.desk = displays.Desk.load()
        except RuntimeError as problem:
            self.report = f"Kein Compositor: {problem}"
            self.append(_notice(
                "Der Compositor antwortet nicht",
                f"{problem}\n\nDiese Seite fragt `hyprctl monitors all -j`. "
                "Ausserhalb einer laufenden Hyprland-Sitzung gibt es darauf "
                "keine Antwort - und dann auch nichts einzustellen."))
            return
        if not self.desk.placements:
            self.report = "Kein Bildschirm gemeldet"
            self.append(_notice(
                "Kein Bildschirm gemeldet",
                "Der Compositor laeuft und zaehlt keinen einzigen Ausgang "
                "auf. Eine Anordnung liesse sich darauf nicht schreiben."))
            return

        self._build()

    # ---- Aufbau ----------------------------------------------------

    def _build(self) -> None:
        self.area = DeskArea(self.desk, self.section, self._on_desk_changed)
        self.area.set_content_height(
            int(CANVAS_HEIGHT * sizes.scale_of(self.section)))

        frame = Gtk.Frame()
        frame.add_css_class("view")
        frame.set_child(self.area)
        self.append(frame)

        self.hint = Gtk.Label(wrap=True, xalign=0.0)
        self.append(self.hint)

        group = Adw.PreferencesGroup(title="Der gewaehlte Bildschirm")

        self.chooser = Adw.ComboRow(
            title="Bildschirm",
            subtitle="Oder oben in der Zeichnung anklicken und ziehen.",
            model=Gtk.StringList.new(
                [self.desk.output(item.name).label
                 for item in self.desk.placements]))
        self.chooser.connect("notify::selected", self._on_chosen)
        group.add(self.chooser)

        self.rows["enabled"] = Adw.SwitchRow(
            title="Eingeschaltet",
            subtitle="Aus heisst: der Ausgang wird abgeschaltet, und "
                     "Fenster darauf wandern auf einen anderen Schirm.")
        self.rows["enabled"].connect("notify::active", self._on_enabled)
        group.add(self.rows["enabled"])

        self.rows["mode"] = Adw.ComboRow(
            title="Aufloesung und Bildrate",
            subtitle="Was dieser Bildschirm laut seinem EDID kann.",
            model=Gtk.StringList.new([]))
        self.rows["mode"].connect("notify::selected", self._on_mode)
        group.add(self.rows["mode"])

        self.rows["scale"] = Adw.ComboRow(
            title="Massstab",
            subtitle="Teilt die Aufloesung. Hyprland lehnt einen Massstab "
                     "ab, bei dem sie nicht ganzzahlig aufgeht - dann nimmt "
                     "der Waechter die Anordnung wieder zurueck.",
            model=Gtk.StringList.new([]))
        self.rows["scale"].connect("notify::selected", self._on_scale)
        group.add(self.rows["scale"])

        self.rows["transform"] = Adw.ComboRow(
            title="Drehung", model=Gtk.StringList.new(list(TRANSFORMS)))
        self.rows["transform"].connect("notify::selected", self._on_transform)
        group.add(self.rows["transform"])

        self.rows["position"] = Adw.ActionRow(title="Steht bei")
        group.add(self.rows["position"])

        self.append(group)

        where = Adw.PreferencesGroup()
        self.rows["where"] = Adw.ActionRow(title="Geschrieben wird nach",
                                           subtitle_lines=0)
        where.add(self.rows["where"])
        self.append(where)

        self.apply_button = Gtk.Button(
            label="Anwenden", halign=Gtk.Align.END, sensitive=False)
        self.apply_button.add_css_class("suggested-action")
        self.apply_button.connect("clicked", self._on_apply)
        self.append(self.apply_button)

        self._show_selection()
        self._show_state()

    # ---- Anzeigen --------------------------------------------------

    @property
    def selected(self) -> str:
        return self.area.selected if self.area is not None else ""

    @contextmanager
    def _quietly(self):
        """Anzeigen, ohne damit etwas zu bestellen.

        Dieselbe Vorrichtung und dieselbe Begruendung wie der
        Stillhalte-Schalter in app.py: waehrend die Anwendung selbst
        Werte in Widgets schreibt, sind die Rueckrufe still.

        ER REICHT HIER NICHT ALLEIN, und das ist gemessen und nicht
        vermutet - siehe _rebuild_lists() unten.
        """
        was, self._quiet = self._quiet, True
        try:
            yield
        finally:
            self._quiet = was

    def _rebuild_lists(self) -> None:
        """Die zwei Auswahllisten, die vom gewaehlten Schirm abhaengen.

        NUR BEI EINEM WECHSEL DES GEWAEHLTEN SCHIRMS, und das ist keine
        Sparsamkeit, sondern die Behebung eines Aufhaengers.

        GEMESSEN am 12.08.2026 gegen libadwaita unter gtk4-broadwayd:
        Adw.ComboRow.set_model() loest "notify::selected" NICHT
        synchron aus, sondern NACHTRAEGLICH. Eine Probe mit einem
        Stillhalte-Schalter um set_model() herum meldete den Rueckruf
        sieben Mal hintereinander, jedes Mal mit quiet=False - der
        Schalter war beim Eintreffen laengst wieder zurueckgesetzt.

        Standen die Listen also im selben Weg wie jede andere Anzeige,
        dann galt: Rueckruf -> Wert setzen -> anzeigen -> set_model() ->
        nachtraeglicher Rueckruf -> ... Die Schleife lief NICHT ueber
        den Aufrufstapel, sondern ueber die Hauptschleife, also sah man
        keine Rekursion, sondern ein Fenster, das nie fertig wurde: zehn
        von vierzehn Pruefungen liefen in die 45-Sekunden-Grenze.

        Die Listen haengen ohnehin nur am gewaehlten Schirm - seine
        Modi kommen aus dem EDID, die Massstaebe sind eine feste Leiter.
        Sie bei jeder Bewegung neu zu bauen war auch ohne den Aufhaenger
        falsch.

        Die zweite Haelfte der Behebung steht in _on_mode() und
        _on_scale(): ein Rueckruf, der den Wert meldet, der ohnehin
        schon gilt, ist kein Wechsel. Damit ist der nachtraegliche
        Rueckruf nach einem Listenwechsel strukturell folgenlos statt
        nur selten.
        """
        name = self.selected
        item = self.desk.get(name)
        output = self.desk.output(name)
        self._listed = name

        with self._quietly():
            # Der LAUFENDE Modus zuerst, falls der Bildschirm ihn nicht
            # in seiner eigenen Liste fuehrt. Ein Fenster, das beim
            # blossen Oeffnen eine andere Aufloesung einstellt, waere
            # kein Anzeigen - dieselbe Regel wie bei den Auswahllisten
            # der Aktualisierung.
            running = displays.Mode(item.width, item.height, item.refresh)
            self.mode_options = list(output.modes)
            if running not in self.mode_options:
                self.mode_options.insert(0, running)
            self.rows["mode"].set_model(
                Gtk.StringList.new([mode.label for mode in self.mode_options]))

            self.scale_options = sorted({item.scale, *SCALES})
            self.rows["scale"].set_model(Gtk.StringList.new(
                [f"{displays.number(value)} x"
                 for value in self.scale_options]))

    def _show_selection(self) -> None:
        name = self.selected
        item = self.desk.get(name)

        if name != self._listed:
            self._rebuild_lists()

        with self._quietly():
            names = [placement.name for placement in self.desk.placements]
            self.chooser.set_selected(names.index(name))
            self.rows["enabled"].set_active(item.enabled)
            self.rows["mode"].set_selected(self.mode_options.index(
                displays.Mode(item.width, item.height, item.refresh)))
            self.rows["scale"].set_selected(
                self.scale_options.index(item.scale))
            self.rows["transform"].set_selected(
                item.transform % len(TRANSFORMS))

        for key in ("mode", "scale", "transform", "position"):
            self.rows[key].set_sensitive(item.enabled)

    def _show_state(self) -> None:
        item = self.desk.get(self.selected)
        self.rows["position"].set_subtitle(
            f"{item.x} x {item.y}, und misst dort {item.displayed_width} x "
            f"{item.displayed_height} Pixel. Die Stelle kommt aus der "
            "Zeichnung oben und rastet an den Kanten der Nachbarn ein.")
        self.rows["where"].set_subtitle(self.where_note())

        troubles = self.desk.problems()
        self.hint.set_text("\n".join(troubles) if troubles else (
            "Einen Schirm anklicken und ziehen. Er rastet an den Kanten der "
            "anderen ein."))
        for name, wanted in (("error", bool(troubles)),
                             ("dim-label", not troubles)):
            if wanted:
                self.hint.add_css_class(name)
            else:
                self.hint.remove_css_class(name)

        # Anwendbar heisst: etwas ist anders, es laeuft kein Versuch, und
        # mindestens ein Schirm bleibt an. Eine UEBERLAPPUNG sperrt den
        # Knopf NICHT - sie ist eine Anordnung, die man sieht und
        # zuruecknehmen kann, und die Warnung darueber steht schon oben.
        # Der Fall ohne Rueckweg ist der andere.
        self.apply_button.set_sensitive(
            self.desk.changed()
            and self.attempt is None
            and any(each.enabled for each in self.desk.placements))

    def where_note(self) -> str:
        """Wohin geschrieben wird, im Klartext - und was fehlt.

        Der Satz ist so lang, weil die Falle es ist: eine Anordnung, die
        nur in ~/.config/hypr landet, ueberschreibt start-hyprland beim
        naechsten Anmelden aus dem Profil. Wer das nicht weiss, stellt
        seine Schirme jeden Morgen neu ein.

        OHNE SPITZE KLAMMERN, und das ist gemessen und kein Geschmack:
        Adw.ActionRow liest seinen Untertitel als Pango-Auszeichnung.
        "save-profile <name>" ergab am 12.08.2026 ein Gtk-WARNING
        ("Element markup was closed, but the currently open element is
        name") und danach eine LEERE Zeile - die Erklaerung, wegen der
        die Zeile es gibt, war weg.
        """
        where = displays.targets()
        profile = displays.current_profile()
        if len(where) > 1:
            return (f"{where[0]} und das aktive Profil \"{profile}\" "
                    f"({where[1]}). Ohne die zweite waere die Anordnung bei "
                    "der naechsten Anmeldung wieder weg: start-hyprland "
                    "kopiert das Profil darueber.")
        if profile:
            return (f"{where[0]}. Das Profil \"{profile}\" hat kein "
                    f"Verzeichnis - `save-profile {profile}` legt eins an, "
                    "und die Anordnung ueberlebt dann die naechste "
                    "Anmeldung.")
        return (f"{where[0]}. Kein Profil ist aktiv; `save-profile` mit "
                "einem Namen macht aus dieser Anordnung eine, die "
                "`start-hyprland` mit demselben Namen wiederherstellt.")

    def _on_desk_changed(self) -> None:
        self._show_selection()
        self._show_state()

    # ---- Rueckrufe -------------------------------------------------

    def _on_chosen(self, row, _parameter) -> None:
        if self._quiet:
            return
        self.area.select(self.desk.placements[row.get_selected()].name)

    def _changed(self, **fields) -> None:
        """Einen Wert am gewaehlten Schirm setzen - wenn er neu ist.

        Die Pruefung auf "schon so" ist die zweite Haelfte der Behebung
        aus _rebuild_lists(): libadwaita meldet "notify::selected" nach
        einem set_model() NACHTRAEGLICH, also ausserhalb jedes
        Stillhalte-Schalters. Ohne diese Zeile wuerde jeder solche
        Rueckruf wie eine Bedienung behandelt - er setzte denselben Wert
        noch einmal, zeichnete neu und meldete "geaendert".
        """
        item = self.desk.get(self.selected)
        if all(getattr(item, key) == value for key, value in fields.items()):
            return
        self.desk.change(self.selected, **fields)
        self.area.queue_draw()
        self._on_desk_changed()

    def _on_enabled(self, row, _parameter) -> None:
        if self._quiet:
            return
        self._changed(enabled=row.get_active())

    def _on_mode(self, row, _parameter) -> None:
        if self._quiet:
            return
        mode = self.mode_options[row.get_selected()]
        self._changed(width=mode.width, height=mode.height,
                      refresh=mode.refresh)

    def _on_scale(self, row, _parameter) -> None:
        if self._quiet:
            return
        self._changed(scale=self.scale_options[row.get_selected()])

    def _on_transform(self, row, _parameter) -> None:
        if self._quiet:
            return
        self._changed(transform=row.get_selected())

    # ---- Anwenden, auf Probe ---------------------------------------

    def _on_apply(self, _button) -> None:
        self.apply_now()

    def apply_now(self) -> str:
        """Waechter scharfmachen, anwenden, fragen.

        Oeffentlich, weil das kopflose Kind hier hineingreift - siehe
        DeskArea.drag_to(). Der Rueckgabewert ist der Bericht, damit ein
        Aufrufer ihn lesen kann, ohne eine Beschriftung abzufragen.
        """
        try:
            self.attempt = displays.arm_and_apply(
                self.desk.placements, self.desk.original)
        except (displays.NoScreenLeft, displays.GuardRefused,
                displays.ApplyFailed, OSError) as problem:
            self.attempt = None
            self._say(f"Nicht angewandt: {problem}")
            self._show_state()
            return self.report

        self._say("Angewandt, auf Probe.")
        self._ask()
        return self.report

    def _say(self, text: str) -> None:
        self.report = text
        self.on_report(text)

    def _ask(self) -> None:
        """Die Rueckfrage mit dem Zaehler.

        Sie ist NICHT der Rueckfall - der laeuft im Waechter, in einem
        eigenen Prozess. Sie ist die Hoeflichkeit davor: wer sieht, was
        er bestellt hat, soll nicht funfzehn Sekunden warten muessen, und
        wer nichts sieht, soll wissen, dass gleich etwas passiert.
        """
        self.countdown = displays.CONFIRM_SECONDS
        dialog = Adw.AlertDialog(heading="Diese Anordnung behalten?",
                                 body=self._countdown_text())
        dialog.add_response("zurueck", "Zuruecknehmen")
        dialog.add_response("behalten", "Behalten")
        dialog.set_response_appearance("behalten",
                                       Adw.ResponseAppearance.SUGGESTED)
        # Die Vorgabe ist ZURUECKNEHMEN, und das ist der Unterschied
        # zwischen einer Rueckfrage und einer Falle: die Escape-Taste und
        # jedes versehentliche Schliessen bedeuten hier "ich sehe nichts".
        dialog.set_default_response("zurueck")
        dialog.set_close_response("zurueck")
        dialog.connect("response", self._on_answer)
        self.dialog = dialog
        self.countdown_source = GLib.timeout_add_seconds(1, self._tick)
        dialog.present(self)

    def _countdown_text(self) -> str:
        return (
            f"Ohne Antwort wird in {self.countdown} Sekunden die alte "
            "Anordnung wiederhergestellt.\n\n"
            "Das passiert auch dann, wenn dieses Fenster in der "
            "Zwischenzeit abstuerzt: der Rueckweg laeuft in einem eigenen "
            "Prozess.")

    def _tick(self) -> bool:
        self.countdown -= 1
        if self.countdown > 0:
            if self.dialog is not None:
                self.dialog.set_body(self._countdown_text())
            return GLib.SOURCE_CONTINUE
        self.countdown_source = 0
        self._settle(False)
        return GLib.SOURCE_REMOVE

    def _on_answer(self, _dialog, response: str) -> None:
        """Die Frage ist beantwortet - auch dann, wenn niemand sie
        angeklickt hat.

        WARUM HIER `self.dialog = None` STEHT, UND ZWAR VOR _settle()
            Weil eine beantwortete Rueckfrage sich SELBST schliesst. Sie
            hier noch einmal zu schliessen, wie _settle() es fuer den
            Weg ueber den Zaehler tun muss, bringt libadwaita zum
            Abbruch:

                Adwaita:ERROR ../libadwaita/src/adw-dialog-host.c:221:
                dialog_closing_cb: assertion failed:
                (g_ptr_array_find (self->dialogs, dialog, &index))

            GEMESSEN am 12.08.2026 unter gtk4-broadwayd, und der Weg
            dorthin ist der, der zaehlt: das FENSTER wurde geschlossen,
            waehrend die Frage stand. libadwaita schliesst dann seine
            Dialoge selbst, mit dem Schliess-Ergebnis - hier also
            "zurueck" -, und dieser Rueckruf lief, bevor irgendein
            close-request-Behandler etwas hatte tun koennen. Das Kind
            endete mit -6 statt 0.

            Damit erledigt sich der Fall auch inhaltlich von selbst, und
            zwar richtig: wer das Fenster zumacht, statt zu antworten,
            sieht nicht, was er bestaetigen soll, und bekommt die alte
            Anordnung zurueck. Es braucht dafuer keinen eigenen
            Behandler - er waere ein zweiter Weg zu demselben Ergebnis,
            und der erste ist der, den GTK ohnehin geht.
        """
        self.dialog = None
        self._settle(response == "behalten")

    def _settle(self, keep: bool) -> None:
        """Behalten oder zuruecknehmen - und beim Behalten SCHREIBEN.

        Die Datei wird HIER geschrieben und nicht vor dem Anwenden. Der
        Kopf von src/displays.py fuehrt aus, warum: eine schon
        geschriebene Datei braeuchte einen zweiten Rueckfall, und eine
        Sitzung, die danach mit ihr startet, findet keinen Schirm mehr,
        auf dem sie fragen koennte.

        ZUERST AUFGERAEUMT, DANN GEHANDELT, und das ist kein Geschmack:
        dialog.force_close() loest selbst wieder "response" aus, also
        diese Methode noch einmal. Steht das Aufraeumen hinten, nimmt der
        zweite Durchlauf denselben Waechter noch einmal - und `keep`
        waere beim zweiten Mal das Schliess-Ergebnis, also
        "zuruecknehmen", nach einem "behalten".
        """
        if self.countdown_source:
            GLib.Source.remove(self.countdown_source)
            self.countdown_source = 0
        dialog, self.dialog = self.dialog, None
        attempt, self.attempt = self.attempt, None
        if dialog is not None:
            dialog.force_close()
        if attempt is None:
            return

        if not keep:
            outcome = attempt.revert()
            self.desk.placements = list(self.desk.original)
            self._say(f"Zurueckgenommen. {outcome.report}".strip())
            self._on_desk_changed()
            return

        outcome = attempt.keep()
        if not outcome.kept:
            # Der Waechter hat trotz "behalten" zurueckgestellt: er kam
            # nicht mehr dazu, es zu hoeren, weil seine Frist genau in
            # diesem Moment ablief. Dann gilt SEIN Ergebnis und nicht die
            # Absicht - auf dem Schirm steht die alte Anordnung, also
            # wird auch die alte geschrieben, naemlich keine.
            self.desk.placements = list(self.desk.original)
            self._say("Der Waechter hatte schon zurueckgestellt: "
                      + outcome.report)
            self._on_desk_changed()
            return

        try:
            written = displays.write(self.desk.placements)
        except OSError as problem:
            self._say(f"Angewandt, aber nicht geschrieben: {problem}. Die "
                      "Anordnung steht bis zum naechsten Anmelden.")
            self._on_desk_changed()
            return

        self.desk.original = tuple(self.desk.placements)
        self._say("Behalten und geschrieben: "
                  + ", ".join(str(path) for path in written))
        self._on_desk_changed()
