// SPDX-License-Identifier: GPL-3.0-or-later
//
// Das Kind von tests/src/test_bar_headless.py: es baut die erzeugte
// Leiste und das erzeugte Dock auf einer echten GTK4-Anzeige und
// schreibt auf, was dabei entstanden ist.
//
// WARUM EIN EIGENES KIND UND NICHT `ags run`
//     `ags run` startet app.ts, also die ganze Oberflaeche mit ihren elf
//     Ueberlagerungen, dem Benachrichtigungsdienst UND einem
//     Astal-Socket unter dem Instanznamen "ags". Auf einer Maschine, auf
//     der der Nutzer gerade arbeitet, ist das der Socket SEINER Sitzung.
//     Dieses Kind importiert stattdessen die beiden Funktionen, die den
//     INHALT bauen, und haengt ihn in ein gewoehnliches Gtk.Window.
//
// WARUM DER INHALT UND NICHT DAS LAYER-SHELL-FENSTER
//     Astal.Window ruft in ihrem Konstruktor gtk_layer_init_for_window
//     auf, und das prueft GDK_IS_WAYLAND_DISPLAY. GEMESSEN am 11.08.2026
//     unter gtk4-broadwayd: das Fenster entsteht und zeichnet, aber es
//     schreibt vier CRITICAL-Zeilen auf stderr ("can not initialize
//     layer shell on window"). Eine kritische Meldung ist in diesem
//     Projekt ein Testfehler - siehe tests/installer/test_gui_headless.py -
//     und sie waere hier auch falsch: dass eine HTML5-Anzeige keine
//     Layer-Shell hat, ist kein Fehler, sondern die Antwort.
//
//     Deshalb sind BarContent() und DockContent() in ihren Vorlagen von
//     Bar() und Dock() getrennt. Der Teil, der von einem Compositor
//     abhaengt, ist damit klein und benannt; alles andere ist messbar.

import { Gtk } from "ags/gtk4"
import GLib from "gi://GLib"
import { BAR_THICKNESS, BarContent } from "./widget/Bar"
import { DockContent } from "./widget/Dock"

const TRACE = GLib.getenv("ZEPOS_TRACE") ?? ""
const marks: string[] = []

function mark(name: string, value: string): void {
  marks.push(`${name}:${value}`)
}

function childNames(box: Gtk.Widget | null): string[] {
  const names: string[] = []
  let child = box ? (box as Gtk.Box).get_first_child() : null
  while (child) {
    names.push(child.get_name())
    child = child.get_next_sibling()
  }
  return names
}

function write(path: string, text: string): void {
  GLib.file_set_contents(path, new TextEncoder().encode(text))
}

Gtk.init()

const toggled: string[] = []
const window = new Gtk.Window({ title: "zepos-bar-headless" })
// Der dritte Wert ist die BREITE des Schirms - die Leiste laeuft
// waagerecht. Hier ein Wert, auf den alles passt: was die Leiste tut,
// wenn er zu klein ist, misst bar_fit_child.tsx - und zwar mit dem
// Stylesheet, ohne das die Leiste nur halb so gross ist, wie sie in
// Wirklichkeit wird.
// Der Melder als ATTRAPPE, und das ist der Grund, aus dem die Leiste
// ihn HEREINGEREICHT bekommt statt ihn zu importieren.
//
// Der echte liegt in ags/widget/Notifications.tsx und haengt an
// AstalNotifd; dessen get_default() meldet sich am D-Bus-SITZUNGSBUS
// an. Der Kopf dieser Datei sagt oben, warum sie nicht `ags run`
// benutzt - "auf einer Maschine, auf der der Nutzer gerade arbeitet,
// ist das der Socket SEINER Sitzung". Ein Import in Bar.tsx haette
// genau das ueber die Hintertuer zurueckgeholt.
//
// Sie meldet "nichts zu melden": das Glockenmodul ist bedingt und
// bleibt damit unsichtbar - so wie es auf einer ruhigen Sitzung auch
// ist.
const notifications = {
  dnd: () => false,
  unseen: () => 0,
  onChange: (_listener: () => void) => {},
}

const bar = BarContent(GLib.getenv("ZEPOS_MONITOR") ?? "PROBE-1",
                       (name: string) => toggled.push(name),
                       () => 3840,
                       notifications)
window.set_child(bar)
// Die DICKE kommt aus der Leiste selbst und nicht aus dieser Datei.
//
// Hier stand eine 92 - der Wert, den src/sizes.py heute ausrechnet -,
// und damit mass der Test seine eigene Konstante: eine Leiste, deren
// Dicke gar nicht mehr aus der Tabelle kommt, waere trotzdem 92 px
// gewesen. GEMESSEN: die Mutation `Size(1, BARE, FIXED)` kam durch.
//
// Die Kopfleiste ist so breit wie der Schirm und BAR_THICKNESS hoch.
window.set_default_size(1920, BAR_THICKNESS)
window.present()

// Die geladenen Bibliotheken DIESES Prozesses, waehrend das Fenster
// steht. Das ist der Toolkit-Nachweis, und er ist staerker als ein
// objdump auf eine Datei: er sagt nicht, wogegen gelinkt wurde, sondern
// was der Prozess, der die Leiste gezeichnet hat, wirklich geladen hat.
const [ok, maps] = GLib.file_get_contents("/proc/self/maps")
if (ok && TRACE) write(`${TRACE}.maps`, new TextDecoder().decode(maps))

// Eineinhalb Sekunden, weil die Skriptmodule ueber execAsync laufen und
// ihre erste Antwort abwarten muessen. Ohne sie stuende hier eine Leiste
// aus lauter unsichtbaren Kaesten - der Zustand VOR der ersten Antwort,
// nicht der, den der Nutzer sieht.
const loop = GLib.MainLoop.new(null, false)
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1500, () => {
  const centre = bar as Gtk.CenterBox
  mark("left", childNames(centre.get_start_widget()).join(","))
  mark("center", childNames(centre.get_center_widget()).join(","))
  mark("right", childNames(centre.get_end_widget()).join(","))
  mark("allocated", `${window.get_allocated_width()}x${window.get_allocated_height()}`)
  mark("thickness", String(BAR_THICKNESS))

  // Was ein Modul WIRKLICH anzeigt, nachdem sein Skript geantwortet hat.
  const shown: string[] = []
  for (const side of [centre.get_start_widget(), centre.get_end_widget()]) {
    let child = side ? (side as Gtk.Box).get_first_child() : null
    while (child) {
      const label = (child as Gtk.Box).get_first_child()
      if (label instanceof Gtk.Label && child.visible) {
        shown.push(`${child.get_name()}=${label.label}`)
      }
      child = child.get_next_sibling()
    }
  }
  mark("shown", shown.join(","))

  // Die Arbeitsbereichsknoepfe: Zahl und Klassen.
  //
  // Im MITTLEREN Kasten gesucht, seit dem 12.08.2026: "in der mitte die
  // arbeitsbereiche". Vorher stand hier get_start_widget(), und mit dem
  // faende diese Schleife jetzt nichts - die Marke waere leer, und der
  // Test darunter saehe aus wie eine Leiste ohne Arbeitsbereiche.
  let workspaces: Gtk.Widget | null =
    (centre.get_center_widget() as Gtk.Box).get_first_child()
  while (workspaces && workspaces.get_name() !== "workspaces") {
    workspaces = workspaces.get_next_sibling()
  }
  const buttons: string[] = []
  let button = workspaces ? (workspaces as Gtk.Box).get_first_child() : null
  while (button) {
    const label = (button as Gtk.Button).get_child()
    buttons.push(`${(label as Gtk.Label).label}[${button.get_css_classes().join(" ")}]`)
    button = button.get_next_sibling()
  }
  mark("workspaces", buttons.join(","))

  // Ein Klick auf das Datum. Er darf keinen Prozess starten, sondern muss
  // die Funktion erreichen, die dieses Kind uebergeben hat.
  //
  // BEIDE TASTEN, und jede unter ihrer Nummer: das Datum oeffnet seit
  // dem 12.08.2026 links den Kalender und rechts das Meldungszentrum
  // (die Messung dazu steht im Zweig "custom/date" in
  // ags-bar.template). Ohne die Nummer stuenden hier zwei Namen in
  // einer Reihe, und welcher zu welcher Taste gehoert, sagte niemand -
  // ein vertauschtes Paar bestuende die Pruefung.
  let date: Gtk.Widget | null = (centre.get_start_widget() as Gtk.Box).get_first_child()
  while (date && date.get_name() !== "custom-date") date = date.get_next_sibling()
  if (date) {
    for (const controller of listControllers(date)) {
      if (!(controller instanceof Gtk.GestureClick)) continue
      const button = (controller as Gtk.GestureClick).get_button()
      const before = toggled.length
      controller.emit("released", 1, 0, 0)
      for (let index = before; index < toggled.length; index++) {
        toggled[index] = `${button}=${toggled[index]}`
      }
    }
  }
  mark("toggled", toggled.join(","))

  // Was eingeklappt wurde. Ohne Stylesheet sind die Module schmal und
  // der Schirm dieses Laufs ist 3840 px breit - es darf also NICHTS
  // eingeklappt sein. Was die Regel tut, wenn der Platz knapp wird,
  // misst bar_fit_child.tsx mit dem Stylesheet.
  let overflow: Gtk.Widget | null =
    (centre.get_end_widget() as Gtk.Box).get_first_child()
  while (overflow && overflow.get_name() !== "bar-overflow") {
    overflow = overflow.get_next_sibling()
  }
  const popover = overflow
    ? (overflow as Gtk.MenuButton).get_popover() : null
  const tray = popover ? (popover as Gtk.Popover).get_child() : null
  mark("gefaltet", childNames(tray).join(","))

  const dock = DockContent()
  mark("dock", dock.get_name())

  if (TRACE) write(TRACE, marks.join("\n") + "\n")
  loop.quit()
  return false
})

function listControllers(widget: Gtk.Widget): Gtk.EventController[] {
  const found: Gtk.EventController[] = []
  const list = widget.observe_controllers()
  for (let index = 0; index < list.get_n_items(); index++) {
    found.push(list.get_item(index) as Gtk.EventController)
  }
  return found
}

loop.run()
