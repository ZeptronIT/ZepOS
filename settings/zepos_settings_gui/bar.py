# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Seite "Leiste": was oben steht, in welcher Reihenfolge, und was im Fuss.

WARUM ES SIE GIBT, MIT DATUM
    GEMELDET am 12.08.2026, nachdem ein Mensch das gebaute Medium
    benutzt hat: "im footer war ein einstellungs icon was man nicht
    oeffnen konnte genau sowas will ich im ZepOS zu customizen wenn du
    verstehst".

    GEMESSEN am selben Tag: die zwoelf Module rechts standen in
    src/style_definition.py, die fuenf links in
    src/templates/ags-bar.template, die Anheftungen des Docks kamen
    ueber src/apps.py aus dem depends-Array eines PKGBUILD. Alle drei
    Dateien liegen auf einer Installation gar nicht, und
    user-settings.json hatte keinen Abschnitt dafuer. Wer sein Dock
    aendern wollte, konnte es nicht - und zwar nicht "nur mit Terminal",
    sondern ueberhaupt nicht.

WAS DIESE DATEI ENTSCHEIDET: NICHTS
    Wie in app.py: hier stehen Widgets. Was eine Haelfte ist, was "wie
    ausgeliefert" heisst, was mit einem Namen passiert, den es nicht
    gibt, und wo der Abdruck der Auslieferung liegt - alles in
    src/settings.py, neben dem Abschnitt, den es beschreibt. Der
    Erzeuger liest dieselben Funktionen. Zwei Antworten auf "was steht
    auf dieser Leiste" waeren zwei Leisten.

WARUM DIE ZEILEN DIE NAMEN TRAGEN UND KEINE DEUTSCHEN WOERTER
    "custom/floating-layouts" ist haesslich und es ist der Name, unter
    dem das Modul in ags-bar.template steht, in
    src/style_definition.py, in jeder Fehlermeldung der Leiste und in
    `zepos-settings get bar`. Eine Tabelle mit huebschen Beschriftungen
    daneben waere die zweite Liste, die veraltet, sobald jemand ein
    Modul umbenennt - und dann hiesse ein Modul im Fenster anders als
    ueberall sonst, wo man danach sucht.

    Die Anheftungen des Docks tragen trotzdem Beschriftungen: die
    kommen aus dem Anwendungseintrag dieser Maschine (GIO, derselbe Weg
    wie im Dock), hilfsweise aus dem Abdruck - und nie aus einer Tabelle
    hier. Wo beides schweigt, steht der Paketname.

WARUM HOCH/RUNTER UND KEIN ZIEHEN MIT DER MAUS
    Gtk.ListBox kann umsortiert werden, aber nur ueber eine eigene
    Ziehquelle und ein eigenes Ziel je Zeile, und die Reihenfolge waere
    danach nur noch mit einer Maus zu aendern. Zwei Knoepfe sind mit der
    Tastatur erreichbar, vom Vorleser benennbar und in einem kopflosen
    Lauf messbar - siehe tests/settings/settings_headless_child.py, das
    genau diese Knoepfe drueckt. Ziehen waere schoener und waere die
    einzige Bedienung dieses Fensters, die sich nicht pruefen laesst.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, Gtk  # noqa: E402

import settings as settings_file  # noqa: E402

from . import model  # noqa: E402

# Was der Knopf zum Zuruecksetzen an seiner Zeile sagt. Im Wortlaut und
# an einer Stelle, weil er dreimal dasteht - einmal je Haelfte - und
# drei Wortlaute fuer eine Handlung wie drei Handlungen lesen.
RESET_LABEL = "Zuruecksetzen"
RESET_TITLE = "Wie ausgeliefert"


def entry_for(program: str):
    """Der Anwendungseintrag zu einem Paketnamen, oder None.

    WORTGLEICH zu entryFor() in src/templates/ags-dock.template, und das
    ist keine Kopie aus Bequemlichkeit: es gibt keinen Weg, dieselbe
    Funktion zu benutzen - die eine ist TypeScript im Schreibtisch, die
    andere Python in diesem Fenster. Was beide teilen, ist die QUELLE:
    dieselbe Bibliothek (GIO), dieselben zwei Versuche, dieselbe
    Maschine. Eine eigene Tabelle hier waere dagegen eine zweite
    Wahrheit darueber, welche Anwendung es gibt.

    Erst `<name>.desktop` - so heissen die meisten Eintraege in Arch -,
    dann die Suche ueber das Programm der Exec-Zeile, weil GNOME seine
    Eintraege in Umkehr-DNS benennt (org.gnome.Nautilus.desktop).

    GIO liefert einen Eintrag NUR aus, wenn das Programm seiner
    Exec-Zeile auffindbar ist; eine verwaiste .desktop-Datei antwortet
    hier also mit None. Das ist gemessen (11.08.2026, gjs gegen drei
    identisch gebaute Eintraege) und steht im Kopf des Docks.
    """
    # try/except und nicht `if is None`, und das ist gemessen: PyGObject
    # macht aus einem Konstruktor, der NULL zurueckgibt, keinen None,
    # sondern wirft `TypeError: constructor returned NULL`. In GJS - und
    # damit im Dock - ist derselbe Aufruf schlicht null.
    #
    # GEMESSEN am 12.08.2026 im kopflosen Lauf: ohne diese zwei Zeilen
    # riss der erste Name ohne Anwendungseintrag das GANZE
    # Einstellungsfenster mit, beim Aufbau, bevor irgendetwas zu sehen
    # war - und "nicht installiert" ist der Normalfall fuer eine
    # Auswahl, die auf jeder Maschine dieselbe ist.
    try:
        direct = Gio.DesktopAppInfo.new(f"{program}.desktop")
    except TypeError:
        direct = None
    if direct is not None:
        return direct
    for info in Gio.AppInfo.get_all():
        executable = info.get_executable()
        if executable and executable.split("/")[-1] == program:
            return info
    return None


def dock_entry(program: str) -> tuple[str, str]:
    """Wie das Dock diesen Namen sieht: Beschriftung und Hinderungsgrund.

    Die Beschriftung kommt aus dem Eintrag der MASCHINE und nicht aus
    dem Abdruck. Das ist kein zweiter Weg zu demselben Wert, sondern der
    einzige, der auf einer Installation etwas liefert: der Abdruck
    entsteht in einem Bau-Chroot, in dem GIO nichts beantworten kann, und
    traegt fuer jede fremde Anwendung ein leeres `label` (GEMESSEN am
    12.08.2026 - nur zepos-settings, dessen Eintrag im Checkout liegt,
    hat eins). Genau dieselbe Zeile zeigt das Dock als Kurzhinweis an
    seinem Knopf.
    """
    info = entry_for(program)
    if info is None:
        return "", model.dock_reason(False, False)
    # get_nodisplay() ungeschuetzt, wie im Dock: unter Linux ist jeder
    # Eintrag aus Gio.AppInfo.get_all() ein Gio.DesktopAppInfo. Ein
    # `hasattr` davor wuerde einen Eintrag, der die Frage nicht
    # beantwortet, still fuer eine Anwendung halten - und das ist die
    # Antwort, die einen toten Knopf erzeugt.
    return (info.get_display_name() or "",
            model.dock_reason(True, info.get_nodisplay()))


class BarPage(Adw.PreferencesPage):
    """Drei Gruppen, je eine Haelfte, und in jeder derselbe Satz Knoepfe.

    Die Seite haengt am Speichern-Knopf des Fensters, anders als die
    Bildschirme: was hier eingestellt wird, geht nach
    user-settings.json, also gilt dafuer dieselbe Zusicherung wie fuer
    jeden Regler - erst beim Speichern, und dann sagt das Fenster, was
    ein Anwenden kostet.
    """

    def __init__(self, draft: model.Draft, section: dict, *,
                 on_change=None) -> None:
        super().__init__()

        self.draft = draft
        self.section = section
        self.on_change = on_change

        # Die ausgelieferte Leiste, einmal gelesen. Nicht je Auffrischung
        # neu: der Abdruck liegt unter /usr/share und aendert sich
        # waehrend einer Sitzung nicht, und ein Dateizugriff je
        # Knopfdruck waere eine Messung der Platte statt der Bedienung.
        self.shipped, self.labels, self.note = model.shipped_bar()

        # Was das Dock aus einem Namen macht - einmal je Name gefragt,
        # nicht je Auffrischung: jede Antwort ist ein Dateizugriff durch
        # GIO, und der Bestand an Anwendungseintraegen aendert sich
        # waehrend einer Sitzung nicht.
        #
        # Nur fuer die Anheftungen. Ein Leistenmodul ist keine
        # Anwendung; `custom/date` hat keinen Anwendungseintrag und soll
        # auch keinen haben.
        self.dock: dict[str, tuple[str, str]] = {}
        for name in set(self.shipped[settings_file.BAR_PINS] or []) | set(
                self._stored_pins()):
            self.dock[name] = dock_entry(name)

        # Die Griffe, die das kopflose Kind bedient - namentlich, wie im
        # Fenster selbst, und nicht ueber ein Durchsuchen des
        # Widget-Baums.
        self.groups: dict[str, Adw.PreferencesGroup] = {}
        self.shown: dict[str, list[str]] = {}
        self.missing: dict[str, list[str]] = {}
        self.refused: dict[str, list[str]] = {}
        self.titles: dict[str, dict[str, str]] = {}
        self.subtitles: dict[str, dict[str, str]] = {}
        self.buttons: dict[str, dict[str, dict[str, Gtk.Button]]] = {}
        self.add_rows: dict[str, Adw.ComboRow] = {}
        self.add_buttons: dict[str, Gtk.Button] = {}
        self.reset_buttons: dict[str, Gtk.Button] = {}
        self.complaints: dict[str, str] = {}
        self._children: dict[str, list[Gtk.Widget]] = {}

        self._build()

    def _stored_pins(self) -> list[str]:
        """Die Anheftungen aus der Einstellungsdatei, auch die kaputten.

        Nur zum Fragen, was das Dock aus ihnen macht: ein Name, den der
        Nutzer gespeichert hat und der auf dieser Maschine kein Programm
        mehr ist, soll seinen Grund daneben stehen haben.
        """
        try:
            return self.draft.current_bar(settings_file.BAR_PINS) or []
        except settings_file.UnusableSettings:
            return []

    # ---- Aufbau ----------------------------------------------------

    def _build(self) -> None:
        if self.note:
            # Ganz oben und nicht in einer Fussnote: wenn die
            # Auslieferung unbekannt ist, ist ALLES darunter anders zu
            # lesen - eine Liste ohne "hinzufuegen" sieht sonst aus wie
            # eine Leiste, die nur diese Module kennt.
            group = Adw.PreferencesGroup(title="Die ausgelieferte Leiste")
            group.add(Adw.ActionRow(title=self.note, title_lines=0))
            self.add(group)

        for key, title, description in model.BAR_SIDES:
            group = Adw.PreferencesGroup(title=title, description=description)
            self.groups[key] = group
            self._children[key] = []
            self.add(group)
            self._fill(key)

    def _fill(self, key: str) -> None:
        """Eine Gruppe aus dem heutigen Stand des Entwurfs aufbauen."""
        group = self.groups[key]
        for widget in self._children[key]:
            group.remove(widget)
        self._children[key] = []
        self.buttons[key] = {}
        self.titles[key] = {}
        self.subtitles[key] = {}

        order, complaint = self._order(key)
        self.shown[key] = order
        self.complaints[key] = complaint

        if complaint:
            self._attach(key, Adw.ActionRow(title=complaint, title_lines=0))

        for index, name in enumerate(order):
            self._attach(key, self._entry_row(key, name, index, len(order)))

        # ANGEBOTEN WIRD DAS MOEGLICHE UND NICHT DAS AUSGELIEFERTE
        # (12.08.2026, Aufgabe #96)
        #
        #     Bis dahin war beides dieselbe Liste, weil die Vorgabe
        #     jedes Modul aufstellte, das es gibt. Seit die Vorgabe eine
        #     AUSWAHL ist, waere "was ausgeliefert wird" die falsche
        #     Frage: das Wetter stuende dann in keiner der beiden Listen
        #     dieser Seite - nicht oben bei den aufgestellten und nicht
        #     unten zur Wahl - und waere von hier aus unerreichbar.
        placeable = model.placeable_in(self.shipped, key)
        # Und nicht, was auf der ANDEREN Haelfte schon steht. Das
        # Moegliche ist EINE Liste fuer beide Haelften - ein Modul ist
        # nicht links oder rechts von Natur aus -, also stuende die Uhr
        # sonst rechts zur Wahl, waehrend sie links dasteht. Wer sie
        # beide Male aufstellt, hat zwei Uhren.
        elsewhere = self._elsewhere(key)
        # Angeboten wird nur, was auch ankaeme. Ein Name, den das Dock
        # ohnehin verwirft, waere hier eine Wahl, die nichts bewirkt -
        # siehe model.dock_reason(). Er verschwindet dabei nicht
        # stillschweigend: die Zeile darunter sagt, wie viele und warum.
        self.refused[key] = [name for name in (placeable or [])
                             if name not in order and name not in elsewhere
                             and self._reason(name)]
        self.missing[key] = ([name for name in placeable if name not in order
                              and name not in elsewhere
                              and not self._reason(name)]
                             if placeable is not None else [])
        self._attach(key, self._add_row(key))
        self._attach(key, self._reset_row(key))

    def _reason(self, name: str) -> str:
        """Warum das Dock diesen Namen auslaesst - leer fuer alle anderen."""
        return self.dock.get(name, ("", ""))[1]

    def _elsewhere(self, key: str) -> set[str]:
        """Was auf der anderen Haelfte der Leiste schon steht.

        Aus dem ENTWURF gelesen und nicht aus self.shown: die Gruppen
        werden der Reihe nach aufgebaut, und beim Fuellen der ersten
        gibt es die zweite noch nicht. Ein Angebot, das davon abhinge,
        welche Gruppe gerade dran ist, waere beim ersten Oeffnen ein
        anderes als nach dem ersten Klick.

        Die Anheftungen des Docks haben keine andere Haelfte: sie sind
        Programmnamen und stehen in einer eigenen Welt.
        """
        if key == settings_file.BAR_PINS:
            return set()
        names: set[str] = set()
        for other in (settings_file.BAR_LEFT, settings_file.BAR_RIGHT):
            if other != key:
                names.update(self._order(other)[0])
        return names

    def _attach(self, key: str, row: Gtk.Widget) -> None:
        self.groups[key].add(row)
        self._children[key].append(row)

    def _order(self, key: str) -> tuple[list[str], str]:
        """Was dasteht, und was daran zu melden ist.

        Der zweite Teil ist der Grund, aus dem diese Seite ueberhaupt
        etwas meldet: ein Name, den es nicht mehr gibt, waere sonst ein
        leerer Platz auf der Leiste oder ein Knopf im Dock, der nichts
        oeffnet. Der Nutzer sieht dann ein Symbol weniger und hat keinen
        Anhaltspunkt, warum.
        """
        try:
            chosen = self.draft.current_bar(key)
        except settings_file.UnusableSettings as problem:
            # Die Datei traegt fuer diese Haelfte etwas, das keine Liste
            # von Namen ist. Angezeigt wird dann NICHTS statt irgendwas,
            # und der Weg heraus steht unten in der Gruppe: der
            # Zuruecksetzen-Knopf schreibt null und repariert damit
            # genau diesen Schluessel.
            return [], (f"{problem}. Bis das gerade gerueckt ist, zeigt "
                        f"diese Seite dafuer nichts an - "
                        f"\"{RESET_TITLE}\" unten setzt den Schluessel "
                        f"auf die Auslieferung zurueck.")

        order, discarded = settings_file.bar_order(
            chosen, model.placeable_in(self.shipped, key), self.shipped[key])
        return order, settings_file.bar_complaint(key, discarded)

    def _entry_row(self, key: str, name: str, index: int,
                   count: int) -> Adw.ActionRow:
        # Die Beschriftung: erst der Eintrag dieser Maschine, dann der
        # Abdruck, dann der blosse Name. Die Reihenfolge ist gemessen
        # und nicht Geschmack - der Abdruck entsteht in einem
        # Bau-Chroot ohne GIO und traegt fuer fremde Anwendungen ein
        # LEERES label, waehrend dieselbe Maschine, auf der dieses
        # Fenster laeuft, "Dateien" und "Firefox" beantworten kann.
        machine, reason = self.dock.get(name, ("", ""))
        label = machine or self.labels.get(name, "")
        # Und darunter der Name, unter dem er gespeichert wird - mit dem
        # Grund, falls das Dock ihn nicht anheften wird. Ohne diesen
        # Zusatz stuende hier eine Zeile mehr als im Fuss, und niemand
        # koennte sagen, welche.
        subtitle = f"{name} - {reason}" if reason else (name if label else "")
        row = Adw.ActionRow(title=label or name, subtitle=subtitle,
                            subtitle_lines=0)
        self.titles[key][name] = row.get_title()
        self.subtitles[key][name] = row.get_subtitle() or ""

        buttons = {
            "up": Gtk.Button(icon_name="go-up-symbolic",
                             tooltip_text="Weiter nach vorn"),
            "down": Gtk.Button(icon_name="go-down-symbolic",
                               tooltip_text="Weiter nach hinten"),
            "remove": Gtk.Button(icon_name="list-remove-symbolic",
                                 tooltip_text="Herunternehmen"),
        }
        buttons["up"].set_sensitive(index > 0)
        buttons["down"].set_sensitive(index < count - 1)
        buttons["up"].connect("clicked", self._on_move, key, name, -1)
        buttons["down"].connect("clicked", self._on_move, key, name, 1)
        buttons["remove"].connect("clicked", self._on_remove, key, name)

        # In einem Kasten mit einer Sprosse dazwischen, wie die zwei
        # Knoepfe einer Farbzeile - siehe model.SPACE_RUNG. Drei Knoepfe
        # unmittelbar nebeneinander sehen aus wie einer mit drei
        # Symbolen, und einer davon nimmt etwas weg.
        suffix = Gtk.Box(spacing=model.space(self.section),
                         valign=Gtk.Align.CENTER)
        for button in buttons.values():
            button.add_css_class("flat")
            button.set_valign(Gtk.Align.CENTER)
            suffix.append(button)
        row.add_suffix(suffix)

        self.buttons[key][name] = buttons
        return row

    def _add_row(self, key: str) -> Adw.ComboRow:
        """Die Zeile, ohne die das Entfernen eine Einbahnstrasse waere.

        Angeboten wird, was die Leiste TRAGEN KANN und hier gerade NICHT
        steht - und, bei den Anheftungen, was auch wirklich im Fuss
        ankaeme. Also die Menge aller moeglichen Eintraege minus der
        aktiven minus der aussichtslosen, und keine eigene Liste.

        "Tragen kann" und nicht "wird ausgeliefert", seit die Vorgabe
        eine Auswahl ist: siehe model.placeable_in() und den Kopf von
        BAR_AVAILABLE in src/settings.py.

        Was der Abdruck nicht kennt, gibt es nicht: ein Name, den man
        frei tippen koennte, waere ein leerer Platz auf der Leiste - und
        genau den soll diese Seite nicht erzeugen koennen. Dasselbe gilt
        fuer einen Namen, den das Dock ohnehin verwirft; der Unterschied
        ist nur, dass er auf einer anderen Maschine sehr wohl ankommen
        kann, weshalb er nicht verschwiegen, sondern unten benannt wird.
        """
        missing = self.missing[key]
        row = Adw.ComboRow(title="Wieder hinzufuegen",
                           model=Gtk.StringList.new(missing))

        button = Gtk.Button(label="Hinzufuegen", valign=Gtk.Align.CENTER)
        button.connect("clicked", self._on_add, key)
        row.add_suffix(button)

        if model.placeable_in(self.shipped, key) is None:
            said = ["Solange die ausgelieferte Reihenfolge unbekannt ist, "
                    "gibt es nichts anzubieten."]
        elif missing:
            # Ein- und Mehrzahl, weil "1 Eintraege" die Art Fehler ist,
            # die eine Oberflaeche unfertig aussehen laesst, ohne dass
            # jemand sagen koennte, woran es liegt.
            said = [("Ein Eintrag steht nicht da" if len(missing) == 1
                     else f"{len(missing)} Eintraege stehen nicht da")
                    + " - was hier gewaehlt wird, kommt ans Ende."]
        else:
            # "was das Dock anheften kann" und nicht "was ZepOS
            # ausliefert": ausgeliefert wird auch, was es nie anheften
            # wird, und der Satz muss neben der Zeile darunter noch
            # stimmen.
            said = ["Es steht alles da, was hier hinkann."]

        # Und was ZepOS zwar ausliefert, das Dock aber nie zeigt. Es
        # steht hier NICHT zur Wahl - ein Knopf, der ein Symbol
        # verspricht, das nie erscheint, ist genau der Fehler, den diese
        # Seite behebt - und es wird trotzdem gesagt, weil eine Auswahl
        # ohne Begruendung wie eine unvollstaendige aussieht.
        refused = self.refused.get(key) or []
        if refused:
            why = sorted({self._reason(name) for name in refused})
            said.append(f"Nicht zur Wahl: {', '.join(sorted(refused))} - "
                        f"{'; '.join(why)}.")
        row.set_subtitle(" ".join(said))
        row.set_subtitle_lines(0)

        row.set_sensitive(bool(missing))
        button.set_sensitive(bool(missing))
        self.add_rows[key] = row
        self.add_buttons[key] = button
        return row

    def _reset_row(self, key: str) -> Adw.ActionRow:
        """Der Weg zurueck, sichtbar und nicht versteckt.

        Er schreibt null und nicht die gerade sichtbare Liste - siehe
        model.Draft.reset_bar(). Eine eingefrorene Liste saehe heute
        genauso aus und zeigte nach dem naechsten neuen Modul auf eine
        Leiste, die es so nicht mehr gibt: das neue Modul erschiene bei
        niemandem, der einmal hier war.
        """
        own = self._own(key)
        row = Adw.ActionRow(
            title=RESET_TITLE,
            title_lines=0,
            subtitle=("Gibt diese Haelfte an die Auslieferung zurueck - "
                      "auch jedes Modul, das ZepOS spaeter hinzufuegt."
                      if own else
                      "Hier ist nichts eingestellt; es steht schon die "
                      "ausgelieferte Reihenfolge da."))

        # OHNE `destructive-action`, obwohl der Knopf die eigene Liste
        # wegwirft: libadwaita faerbt diese Klasse rot, und Rot heisst
        # auf jedem Schreibtisch "Vorsicht". Das hier ist der Rueckweg
        # aus jeder Sackgasse - wer ihn braucht, hat sich schon
        # verlaufen, und ein Warnzeichen davor ist genau die Hemmung,
        # die ihn in der Sackgasse haelt.
        button = Gtk.Button(label=RESET_LABEL, valign=Gtk.Align.CENTER)
        button.set_sensitive(own)
        button.connect("clicked", self._on_reset, key)
        row.add_suffix(button)

        self.reset_buttons[key] = button
        return row

    def _own(self, key: str) -> bool:
        """Ob fuer diese Haelfte ueberhaupt etwas Eigenes gespeichert ist.

        Die Ausnahme faengt genau den Fall, in dem Zuruecksetzen am
        noetigsten ist: eine Haelfte, die nicht gelesen werden kann,
        traegt etwas Eigenes - nur eben nichts Brauchbares.
        """
        try:
            return self.draft.current_bar(key) is not None
        except settings_file.UnusableSettings:
            return True

    def rebind(self, draft: model.Draft) -> None:
        """Den Entwurf austauschen, den diese Seite bedient.

        Nach dem Speichern faengt das Fenster mit einem frischen Entwurf
        an - dem Stand, der jetzt auf der Platte steht. Ohne diese Zeile
        schriebe diese Seite danach weiter in den ALTEN: die Zeilen
        saehen richtig aus, der Speichern-Knopf bliebe grau, und die
        zweite Aenderung eines Abends erreichte die Datei nicht mehr.
        Die anderen Seiten haben das Problem nicht, weil sie den Entwurf
        bei jedem Rueckruf am Fenster nachschlagen; diese haelt ihn,
        weil sie ihre Zeilen aus ihm aufbaut.
        """
        self.draft = draft
        for key in self.groups:
            self._fill(key)

    # ---- Rueckrufe -------------------------------------------------

    def _store(self, key: str, order: list[str]) -> None:
        """Die neue Reihenfolge in den Entwurf, und die Seite neu bauen.

        Ob daraus eine Liste oder ein null wird, entscheidet
        model.bar_stored() und nicht diese Datei - es ist genau die Art
        Entscheidung, die ohne Anzeige messbar sein muss.
        """
        value = model.bar_stored(order, self.shipped[key])
        if value is None:
            self.draft.reset_bar(key)
        else:
            self.draft.set_bar(key, value)
        self._changed(key)

    def _changed(self, key: str) -> None:
        self._fill(key)
        if self.on_change is not None:
            self.on_change()

    def _on_move(self, _button, key: str, name: str, step: int) -> None:
        order = list(self.shown[key])
        index = order.index(name)
        target = index + step
        if not 0 <= target < len(order):
            return
        order[index], order[target] = order[target], order[index]
        self._store(key, order)

    def _on_remove(self, _button, key: str, name: str) -> None:
        self._store(key, [item for item in self.shown[key] if item != name])

    def _on_add(self, _button, key: str) -> None:
        missing = self.missing[key]
        index = self.add_rows[key].get_selected()
        if not missing or index >= len(missing):
            return
        # Ans Ende, nicht an die ausgelieferte Stelle: die Reihenfolge
        # ist jetzt die des Nutzers, und ein Eintrag, der beim
        # Hinzufuegen irgendwo in der Mitte auftaucht, ist einer, den
        # man erst sucht. Von dort wandert er mit den Pfeilen dorthin,
        # wo er hin soll.
        self._store(key, [*self.shown[key], missing[index]])

    def _on_reset(self, _button, key: str) -> None:
        self.draft.reset_bar(key)
        self._changed(key)
