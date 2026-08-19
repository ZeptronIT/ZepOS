# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Oberflaeche. Widgets, und sonst nichts.

Jede Entscheidung steht in model.py - welche Regler es gibt, welche
Grenzen sie haben, was geschrieben wird, was danach noch passieren muss.
Ein Rueckruf hier darf einen Wert von einem Widget ablesen und
hineinreichen, oder ein Ergebnis in eine Beschriftung schreiben, mehr
nicht. Dieselbe Trennung wie zwischen installer/gui/app.py und
installer/gui/pages.py: eine Entscheidung in einem Rueckruf ist eine, die
nur mit Anzeige gemessen werden kann.

WARUM Adw.SpinRow UND KEIN SCHIEBEREGLER
    Ein Schieberegler zeigt "groesser" besser und laesst sich nicht
    tippen. Der ausgelieferte Massstab ist 24/13 = 1.8461...; wer ihn
    nach einem Versuch wiederhaben will, trifft ihn mit der Maus nicht.
    Die SpinRow hat beides - die Pfeile bewegen sie in Schritten von
    SCALE_STEP, das Feld nimmt eine Zahl entgegen -, und sie ist die
    Zeile, die libadwaita fuer eine Zahl vorsieht.

WARUM on_window_shown
    Es ist der einzige Griff, den ein GTK-Fenster von aussen hat: keine
    Skriptschnittstelle, kein Weg, ihm eine Taste zu schicken.
    tests/settings/settings_headless_child.py bedient das Fenster
    darueber. Ohne diesen Parameter waere die einzige pruefbare Aussage
    ueber diese Anwendung, dass sie startet - und genau das ist der
    Zustand, in dem eine Reglertabelle entsteht, die kein Byte bewegt.
    installer/gui/app.py und menu/zepos_menu/main.py tragen denselben
    Griff aus demselben Grund.
"""
from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gtk  # noqa: E402

import brand  # noqa: E402
import sizes  # noqa: E402

from . import bar, model, screens, style  # noqa: E402

APPLICATION_ID = "de.zeptronit.zepos.Settings"

TITLE = "Einstellungen"

# Die Seiten stehen in model.py und nicht hier: main.py prueft den
# Schalter --page gegen sie, BEVOR es dieses Modul importiert - und
# dieser Import zieht gi herein. Siehe den Kopf von main.py.
PAGES = model.PAGES
PAGE_NAMES = model.PAGE_NAMES
PAGE_OPTION = model.PAGE_OPTION


class SettingsWindow(Adw.ApplicationWindow):
    """Das Fenster mit seinen sieben Seiten - siehe PAGES."""

    def __init__(self, application, draft: model.Draft, *,
                 runner=None, page: str | None = None) -> None:
        super().__init__(application=application, title=TITLE)

        self.draft = draft
        self.runner = runner
        self.section = sizes.settings_section(draft.document)

        self.set_default_size(*model.window_size(self.section))

        # Die Griffe, die das kopflose Kind bedient. Namentlich und nicht
        # ueber ein Durchsuchen des Widget-Baums: ein Test, der Widgets
        # sucht, misst die Reihenfolge des Aufbaus mit.
        self.scale_row: Adw.SpinRow | None = None
        self.dial_rows: dict[str, Adw.SpinRow] = {}
        self.colour_buttons: dict[str, Gtk.ColorDialogButton] = {}
        self.weather_row: Adw.EntryRow | None = None
        self.theme_row: Adw.ComboRow | None = None
        self.theme_names: list[str] = []
        self.update_rows: dict[str, Gtk.Widget] = {}
        self.update_options: dict[str, list] = {}
        self.update_report = ""
        self.screens_page: screens.ScreensPage | None = None
        self.bar_page: bar.BarPage | None = None

        # Waehrend die Anwendung selbst Werte in Widgets schreibt, sind
        # die Rueckrufe still.
        #
        # OHNE DAS WAERE DER MASSSTAB EIN AUSNAHMEN-SETZER: bewegt man
        # ihn, schreibt _on_scale() die neuen Zahlen in die fuenf
        # Ausnahmen-Zeilen, damit man sieht, was daraus wird - und jede
        # dieser Zuweisungen loeste "notify::value" aus, also
        # set_dial(), also einen festen Wert in sizes.values. Nach
        # einmal Ziehen folgte keine der fuenf mehr dem Faktor, und beim
        # naechsten Ziehen bewegte sich keine mehr mit.
        self._quiet = False

        self._build()

        # Die Seite, die eine Aktion aus der .desktop-Datei genannt hat.
        # Ein unbekannter Name wird ignoriert und nicht gemeldet: main.py
        # hat ihn bereits gegen PAGE_NAMES geprueft und waere gar nicht
        # bis hierher gekommen.
        if page in PAGE_NAMES:
            self.stack.set_visible_child_name(page)

    # ---- Aufbau ---------------------------------------------------

    def _build(self) -> None:
        self.banner = Adw.Banner(revealed=False)
        self.banner.connect("button-clicked", self._on_banner_clicked)

        # Aus PAGES und nicht siebenmal von Hand: die Tabelle ist
        # zugleich das, wogegen die .desktop-Datei geprueft wird, und
        # zwei Aufzaehlungen derselben Seiten waeren die erste Stelle,
        # an der die naechste nur in einer von beiden landet.
        builders = {
            "groesse": self._size_page,
            "bildschirme": self._screens_page,
            "leiste": self._bar_page,
            "thema": self._theme_page,
            "farben": self._colour_page,
            "wetter": self._weather_page,
            "aktualisierung": self._update_page,
        }
        self.stack = Adw.ViewStack()
        for name, title, icon in PAGES:
            self.stack.add_titled_with_icon(builders[name](), name, title, icon)

        header = Adw.HeaderBar()
        header.set_title_widget(Adw.ViewSwitcher(
            stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE))

        self.save_button = Gtk.Button(label="Speichern", sensitive=False)
        self.save_button.add_css_class("suggested-action")
        self.save_button.connect("clicked", self._on_save)
        header.pack_end(self.save_button)

        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.add_top_bar(self.banner)
        view.set_content(self.stack)
        self.set_content(view)

    # ---- Seite: Groesse -------------------------------------------

    def _size_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage()

        # DIE BESCHREIBUNGEN DIESER SEITE STEHEN SEIT DEM 19.08.2026
        # (Aufgabe 32) IN model.py ALS NOTE_*, NICHT MEHR HIER: das
        # AGS-Einstellungsfenster zeichnet dieselben Saetze, und zwei
        # Fassungen desselben Satzes driften ab der ersten
        # Umformulierung. Siehe den Kopf des NOTE_*-Blocks dort.
        group = Adw.PreferencesGroup(
            title=model.GROUP_SCALE, description=model.NOTE_SCALE_GROUP)

        self.scale_row = Adw.SpinRow(
            title=model.LABEL_SCALE,
            adjustment=Gtk.Adjustment(
                lower=model.SCALE_MINIMUM, upper=model.SCALE_MAXIMUM,
                step_increment=model.SCALE_STEP,
                page_increment=model.SCALE_STEP * 4,
                value=self.draft.current_scale()),
            digits=2)
        self.scale_row.connect("notify::value", self._on_scale)
        group.add(self.scale_row)

        reset = Gtk.Button(label="Auf den ausgelieferten Massstab",
                           valign=Gtk.Align.CENTER)
        reset.connect("clicked", self._on_scale_reset)
        shipped = Adw.ActionRow(
            title="Zuruecksetzen", subtitle=model.NOTE_SCALE_RESET)
        shipped.add_suffix(reset)
        group.add(shipped)
        page.add(group)

        exceptions = Adw.PreferencesGroup(
            title=model.GROUP_DIALS, description=model.NOTE_DIALS_GROUP)
        for dial in model.DIALS:
            exceptions.add(self._dial_row(dial))
        page.add(exceptions)

        motion = Adw.PreferencesGroup(
            title=model.GROUP_MOTION, description=model.NOTE_MOTION_GROUP)
        self.motion_row = Adw.SwitchRow(
            title=model.LABEL_MOTION, subtitle=model.NOTE_MOTION,
            active=self.draft.current_motion())
        self.motion_row.connect("notify::active", self._on_motion)
        motion.add(self.motion_row)
        page.add(motion)

        rest = Adw.PreferencesGroup()
        rest.add(Adw.ActionRow(title=model.NOTE_SIZES_REST_TITLE,
                               subtitle=model.NOTE_SIZES_REST))
        page.add(rest)
        return page

    def _dial_row(self, dial: model.Dial) -> Adw.SpinRow:
        row = Adw.SpinRow(
            title=dial.label,
            subtitle=dial.note,
            adjustment=Gtk.Adjustment(
                lower=dial.minimum, upper=dial.maximum,
                step_increment=1, page_increment=4,
                value=self.draft.current_size(dial.name)),
            digits=0)

        back = Gtk.Button(icon_name="edit-undo-symbolic",
                          valign=Gtk.Align.CENTER,
                          tooltip_text="Wieder dem Massstab ueberlassen")
        back.add_css_class("flat")
        back.connect("clicked", self._on_dial_reset, dial)
        row.add_suffix(back)

        row.connect("notify::value", self._on_dial, dial)
        self.dial_rows[dial.name] = row
        self._mark_dial(dial)
        return row

    def _mark_dial(self, dial: model.Dial) -> None:
        """Sichtbar machen, ob diese Zeile dem Massstab folgt.

        Eine Zahl allein beantwortet die Frage nicht: 24 kann heissen
        "der Faktor hat 24 daraus gemacht" oder "hier steht fest eine
        24". Der Unterschied ist der ganze Sinn der Ausnahmen.
        """
        row = self.dial_rows[dial.name]
        if self.draft.follows_scale(dial.name):
            row.remove_css_class("accent")
        else:
            row.add_css_class("accent")

    # ---- Seite: Bildschirme ---------------------------------------

    def _screens_page(self) -> Gtk.Widget:
        """Die Anordnung der Bildschirme.

        In einem Bildlauffenster, anders als die vier anderen Seiten:
        Adw.PreferencesPage bringt seins mit, ein Gtk.Box nicht - und
        diese Seite traegt unter der Zeichnung noch acht Zeilen, die auf
        einem Laptopschirm sonst unerreichbar waeren.

        KEIN ENTWURF UND KEIN "SPEICHERN", wie beim Thema und bei der
        Aktualisierung: was hier eingestellt wird, geht nicht in
        user-settings.json, sondern nach ~/.config/hypr/monitors.conf und
        an den laufenden Compositor. Der Knopf dafuer steht auf der Seite
        selbst und heisst "Anwenden".
        """
        self.screens_page = screens.ScreensPage(
            self.section, on_report=self._on_screens_report)
        scroller = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        scroller.set_child(self.screens_page)
        return scroller

    def _on_screens_report(self, text: str) -> None:
        """Was die Bildschirmseite zu melden hat, ins Banner.

        Ohne Knopf: es gibt nichts anzuwenden, was nicht schon angewandt
        waere. Das Banner ist hier ein Protokoll und keine Aufforderung -
        genau wie bei der Aktualisierung.
        """
        self.banner.set_button_label("")
        self.banner.set_title(text)
        self.banner.set_revealed(True)

    # ---- Seite: Leiste --------------------------------------------

    def _bar_page(self) -> Gtk.Widget:
        """Was auf der Leiste steht und was im Dock angeheftet ist.

        MIT Entwurf und am Speichern-Knopf, anders als die Bildschirme:
        das hier geht nach user-settings.json, also gilt dieselbe
        Zusicherung wie fuer jeden Regler - nichts wird geschrieben,
        bevor jemand speichert, und danach sagt das Fenster, was ein
        Anwenden kostet.

        Die Seite baut ihre Zeilen selbst, weil sie sie nach jedem
        Klick neu bauen muss: eine Reihenfolge ist kein Wert, den man in
        ein Widget schreibt.
        """
        self.bar_page = bar.BarPage(self.draft, self.section,
                                    on_change=self._refresh_save)
        return self.bar_page

    # ---- Seite: Farben --------------------------------------------

    def _colour_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage()

        for name, rows in brand.COLOR_GROUPS:
            group = Adw.PreferencesGroup(title=name)
            for key, label in rows:
                group.add(self._colour_row(key, label))
            page.add(group)
        return page

    def _colour_row(self, key: str, label: str) -> Adw.ActionRow:
        row = Adw.ActionRow(title=label, subtitle=key)
        row.add_css_class("zepos-hex")

        button = Gtk.ColorDialogButton(
            dialog=Gtk.ColorDialog(title=label, with_alpha=False),
            valign=Gtk.Align.CENTER)
        button.set_rgba(self._rgba(self.draft.current_colour(key)))
        button.connect("notify::rgba", self._on_colour, key)
        self.colour_buttons[key] = button

        back = Gtk.Button(icon_name="edit-undo-symbolic",
                          valign=Gtk.Align.CENTER,
                          tooltip_text="Auf die ausgelieferte Farbe")
        back.add_css_class("flat")
        back.connect("clicked", self._on_colour_reset, key)

        # In einem Kasten mit einer Sprosse dazwischen, statt beide
        # einzeln an die Zeile gehaengt: siehe SPACE_RUNG oben.
        suffix = Gtk.Box(spacing=model.space(self.section),
                         valign=Gtk.Align.CENTER)
        suffix.append(button)
        suffix.append(back)
        row.add_suffix(suffix)
        return row

    @staticmethod
    def _rgba(colour: str) -> Gdk.RGBA:
        red, green, blue = model.rgb_of(colour)
        return Gdk.RGBA(red=red, green=green, blue=blue, alpha=1.0)

    # ---- Seite: Wetter --------------------------------------------

    def _weather_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(
            title=model.GROUP_WEATHER, description=model.NOTE_WEATHER_GROUP)

        self.weather_row = Adw.EntryRow(title=model.LABEL_WEATHER)
        self.weather_row.set_text(self.draft.current_weather())
        self.weather_row.connect("changed", self._on_weather)
        group.add(self.weather_row)
        page.add(group)
        return page

    # ---- Seite: Aktualisierung ------------------------------------

    # ---- Seite: Thema ---------------------------------------------

    def _theme_page(self) -> Adw.PreferencesPage:
        """Die Palette waehlen - eine Zeile, und dann steht da, was das
        kostet.

        KEIN ENTWURF UND KEIN "SPEICHERN", anders als bei allem anderen
        in diesem Fenster. Der Grund ist derselbe wie bei der
        Aktualisierung: die Datei gehoert der Maschine, das Schreiben
        geht moeglicherweise durch pkexec, und ein Rechtefenster, das
        erst beim Speichern erscheint und dann fuer eine Auswahl fragt,
        die man vor zwei Minuten getroffen hat, ist keine Bestaetigung
        mehr, sondern eine Ueberraschung.
        """
        page = Adw.PreferencesPage()
        writable = model.theme_writable()

        group = Adw.PreferencesGroup(
            title=model.GROUP_THEME, description=model.theme_note(writable))

        names = model.theme_names()
        current = model.current_theme()
        self.theme_names = names
        self.theme_row = Adw.ComboRow(
            title=model.LABEL_THEME,
            subtitle=model.THEME_TIMING,
            model=Gtk.StringList.new(
                [f"{model.theme_label(name)} - "
                 f"{model.theme_description(name)}" for name in names]))
        if current in names:
            self.theme_row.set_selected(names.index(current))
        self.theme_row.connect("notify::selected", self._on_theme)
        group.add(self.theme_row)
        page.add(group)
        return page

    def _on_theme(self, row, _parameter) -> None:
        if self._quiet:
            return
        name = self.theme_names[row.get_selected()]
        outcome = model.set_theme(name, runner=self.runner)
        self.update_report = outcome.message
        if outcome.written:
            self.banner.set_button_label("Jetzt anwenden")
            self.banner.set_title(
                f"Thema {model.theme_label(name)} gesetzt. "
                "Der Anmeldebildschirm zeigt es beim naechsten Mal; der "
                "Schreibtisch nach einem Erzeugungslauf.")
        else:
            self.banner.set_button_label("")
            self.banner.set_title(outcome.message.splitlines()[0])
        self.banner.set_revealed(True)

    def _update_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage()

        try:
            config = model.update_settings()
        except Exception as problem:                         # noqa: BLE001
            # Eine unlesbare Maschinendatei darf die anderen drei Seiten
            # nicht mitnehmen. Sie steht unter /etc und kann von
            # jemandem editiert worden sein, der hier nicht sitzt.
            group = Adw.PreferencesGroup(title="Aktualisierung")
            group.add(Adw.ActionRow(
                title="Die Einstellungen der Maschine sind nicht lesbar",
                subtitle=str(problem)))
            page.add(group)
            return page

        writable = model.update_writable()
        group = Adw.PreferencesGroup(
            title=model.GROUP_UPDATE,
            description=model.update_note(writable))

        enabled = Adw.SwitchRow(
            title=model.UPDATE_LABELS[model.UPDATE_ENABLED],
            subtitle=model.NOTE_UPDATE_ENABLED,
            active=bool(config.get(model.UPDATE_ENABLED)))
        enabled.connect("notify::active", self._on_update_switch,
                        model.UPDATE_ENABLED)
        group.add(enabled)
        self.update_rows[model.UPDATE_ENABLED] = enabled

        group.add(self._update_choice(
            model.UPDATE_SCOPE, model.UPDATE_LABELS[model.UPDATE_SCOPE],
            model.NOTE_UPDATE_SCOPE,
            model.UPDATE_SCOPE_LABELS, config.get(model.UPDATE_SCOPE)))

        group.add(self._update_choice(
            model.UPDATE_NOTIFY, model.UPDATE_LABELS[model.UPDATE_NOTIFY],
            model.NOTE_UPDATE_NOTIFY,
            model.UPDATE_NOTIFY_LABELS, config.get(model.UPDATE_NOTIFY)))

        schedule = config.get("schedule")
        interval = schedule.get("interval") if isinstance(schedule, dict) else None
        group.add(self._update_choice(
            model.UPDATE_INTERVAL, model.UPDATE_LABELS[model.UPDATE_INTERVAL],
            "",
            model.UPDATE_INTERVAL_LABELS, interval))

        page.add(group)

        rest = Adw.PreferencesGroup()
        rest.add(Adw.ActionRow(title=model.NOTE_UPDATE_REST_TITLE,
                               subtitle=model.NOTE_UPDATE_REST))
        page.add(rest)
        return page

    def _update_choice(self, key: str, title: str, subtitle: str,
                       labels: dict, current) -> Adw.ComboRow:
        options = list(labels)
        row = Adw.ComboRow(
            title=title, subtitle=subtitle,
            model=Gtk.StringList.new([labels[name] for name in options]))
        if current in options:
            row.set_selected(options.index(current))
        else:
            # Ein Wert, den diese Oberflaeche nicht anbietet - eine
            # Zeitspanne statt eines Kalenderworts etwa, die `zepos-
            # settings` durchaus setzen kann. Er wird angezeigt statt
            # ueberschrieben: eine Auswahl, die beim blossen Oeffnen des
            # Fensters etwas anderes einstellt, ist kein Anzeigen.
            options = [current, *options]
            row.set_model(Gtk.StringList.new(
                [f"{current} (unveraendert)",
                 *[labels[name] for name in options[1:]]]))
            row.set_selected(0)
        self.update_options[key] = options
        row.connect("notify::selected", self._on_update_choice, key)
        self.update_rows[key] = row
        return row

    # ---- Rueckrufe ------------------------------------------------

    def _set_quietly(self, row, value) -> None:
        """Einen Wert anzeigen, ohne ihn damit zu bestellen."""
        was = self._quiet
        self._quiet = True
        try:
            row.set_value(value)
        finally:
            self._quiet = was

    def _show_dials(self) -> None:
        """Die fuenf Ausnahmen auf das bringen, was gerade gilt."""
        for dial in model.DIALS:
            self._set_quietly(self.dial_rows[dial.name],
                              self.draft.current_size(dial.name))
            self._mark_dial(dial)

    def _on_scale(self, row, _parameter) -> None:
        if self._quiet:
            return
        self.draft.scale = row.get_value()
        self._show_dials()
        self._refresh_save()

    def _on_motion(self, row, _parameter) -> None:
        self.draft.motion = row.get_active()
        self._refresh_save()

    def _on_scale_reset(self, _button) -> None:
        self.draft.scale = sizes.SCALE_DEFAULT
        for dial in model.DIALS:
            self.draft.clear_dial(dial)
        self._set_quietly(self.scale_row, sizes.SCALE_DEFAULT)
        self._show_dials()
        self._refresh_save()

    def _on_dial(self, row, _parameter, dial: model.Dial) -> None:
        if self._quiet:
            return
        self.draft.set_dial(dial, row.get_value())
        self._mark_dial(dial)
        self._refresh_save()

    def _on_dial_reset(self, _button, dial: model.Dial) -> None:
        self.draft.clear_dial(dial)
        self._set_quietly(self.dial_rows[dial.name],
                          self.draft.current_size(dial.name))
        self._mark_dial(dial)
        self._refresh_save()

    def _on_colour(self, button, _parameter, key: str) -> None:
        if self._quiet:
            return
        rgba = button.get_rgba()
        self.draft.colours[key] = model.hex_of(rgba.red, rgba.green, rgba.blue)
        self._refresh_save()

    def _on_colour_reset(self, _button, key: str) -> None:
        self.draft.colours[key] = model.colour_default(key)
        was, self._quiet = self._quiet, True
        try:
            self.colour_buttons[key].set_rgba(
                self._rgba(model.colour_default(key)))
        finally:
            self._quiet = was
        self._refresh_save()

    def _on_weather(self, entry) -> None:
        if self._quiet:
            return
        self.draft.weather = entry.get_text()
        self._refresh_save()

    def _on_update_switch(self, row, _parameter, key: str) -> None:
        if self._quiet:
            return
        self._write_update(key, row.get_active())

    def _on_update_choice(self, row, _parameter, key: str) -> None:
        if self._quiet:
            return
        self._write_update(key, self.update_options[key][row.get_selected()])

    def _write_update(self, key: str, value) -> None:
        outcome = model.set_update_value(key, value, runner=self.runner)
        self.update_report = outcome.message
        # Kein Knopf an dieser Meldung: die Aktualisierung geht an
        # systemd und nicht an den Generator, also gibt es hier nichts
        # anzuwenden. update.apply() hat die Zeitgeber-Ergaenzung schon
        # geschrieben, als set_update_value() zurueckkam.
        self.banner.set_button_label("")
        self.banner.set_title(
            "Die Maschine aktualisiert sich ab sofort nach dieser "
            "Einstellung." if outcome.written
            else outcome.message.splitlines()[0])
        self.banner.set_revealed(True)

    def _refresh_save(self) -> None:
        self.save_button.set_sensitive(self.draft.dirty())

    # ---- Speichern und Anwenden -----------------------------------

    def _on_save(self, _button) -> None:
        model.save(self.draft)
        model.request_regeneration_at_login()

        # Der Entwurf faengt von vorn an, mit dem, was jetzt auf der
        # Platte steht. Ohne das schriebe ein zweites Speichern
        # dieselben Abschnitte noch einmal, und "geaendert" bliebe wahr,
        # obwohl nichts mehr offen ist.
        self.draft = model.load()
        # Und die eine Seite, die den Entwurf HAELT, statt ihn bei jedem
        # Rueckruf hier nachzuschlagen, bekommt den neuen - sonst
        # schriebe sie ab jetzt in den weggelegten.
        if self.bar_page is not None:
            self.bar_page.rebind(self.draft)
        self._refresh_save()

        self.banner.set_title(
            "Gespeichert. Wirksam mit der naechsten Anmeldung - oder "
            "jetzt.")
        self.banner.set_button_label("Jetzt anwenden")
        self.banner.set_revealed(True)

    def _on_banner_clicked(self, _banner) -> None:
        dialog = Adw.AlertDialog(
            heading="Jetzt anwenden?",
            body=model.GENERATE_COST)
        dialog.add_response("nein", "Spaeter")
        dialog.add_response("ja", "Anwenden")
        dialog.set_response_appearance("ja", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("nein")
        dialog.connect("response", self._on_apply_answer)
        dialog.present(self)

    def _on_apply_answer(self, _dialog, response: str) -> None:
        if response != "ja":
            return
        self.apply_now()

    def apply_now(self) -> int:
        """Erzeugen, und melden, was daraus geworden ist.

        Oeffentlich, weil das kopflose Kind hier hineingreift: die
        Alternative waere, den Antwortknopf eines Adw.AlertDialog zu
        emittieren, und das misst GTKs Dialogverwaltung statt dieser
        Anwendung.
        """
        completed = model.regenerate(runner=self.runner)
        if completed.returncode == 0:
            self.banner.set_title("Angewendet.")
        else:
            self.banner.set_title(
                f"Der Generator endete mit {completed.returncode}. Die "
                "Einstellungen sind gespeichert und werden bei der "
                "naechsten Anmeldung noch einmal versucht.")
        self.banner.set_button_label("")
        self.banner.set_revealed(True)
        return completed.returncode


class SettingsApplication(Adw.Application):
    """Ein Fenster, ein Durchlauf."""

    def __init__(self, *, runner=None,
                 on_window_shown: Callable | None = None,
                 page: str | None = None) -> None:
        super().__init__(application_id=APPLICATION_ID)
        self.runner = runner
        self.on_window_shown = on_window_shown
        self.page = page
        self.window: SettingsWindow | None = None

    def do_activate(self) -> None:
        draft = model.load()

        sheet = style.css(sizes.settings_section(draft.document))
        provider = Gtk.CssProvider()
        # load_from_string gibt es seit GTK 4.12 und ist der einzige der
        # beiden Wege, der eine Zeichenkette ohne Laengenangabe nimmt;
        # load_from_data ist der Rueckfall fuer eine aeltere Bibliothek.
        if hasattr(provider, "load_from_string"):
            provider.load_from_string(sheet)
        else:                                                # pragma: no cover
            provider.load_from_data(sheet.encode("utf-8"))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.window = SettingsWindow(self, draft, runner=self.runner,
                                     page=self.page)
        self.window.present()
        if self.on_window_shown is not None:
            self.on_window_shown(self.window)
