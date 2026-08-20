// SPDX-License-Identifier: GPL-3.0-or-later
//
// Das Kind von tests/src/test_bar_notifications.py: es baut die erzeugte
// Leiste mit einem ATTRAPPEN-Melder und schreibt auf, was das
// Glockenmodul in vier Zustaenden tut.
//
// WARUM EIN EIGENES KIND
//     bar_headless_child.tsx misst, WELCHE Module auf der Leiste stehen,
//     und reicht dafuer einen Melder herein, der immer "nichts" sagt.
//     Hier geht es um genau das Gegenteil: was passiert, wenn er etwas
//     sagt - und was passiert, wenn er wieder aufhoert.
//
// WARUM EINE ATTRAPPE UND NICHT DER ECHTE MELDER
//     Der echte liegt in ags/widget/Notifications.tsx und haengt an
//     AstalNotifd; dessen get_default() meldet sich am
//     D-Bus-SITZUNGSBUS an. Der Kopf von bar_headless_child.tsx fuehrt
//     das aus: auf einer Maschine, auf der jemand arbeitet, ist das
//     SEINE Sitzung. Genau deshalb reicht die Leiste ihren Melder
//     herein, statt ihn zu importieren - und genau deshalb laesst sich
//     das hier ueberhaupt messen.

import { Gtk } from "ags/gtk4"
import GLib from "gi://GLib"
import { BarContent } from "./widget/Bar"

const TRACE = GLib.getenv("ZEPOS_TRACE") ?? ""
const lines: string[] = []

// Der Melder als Attrappe: zwei Werte und eine Liste von Zuhoerern,
// genau die drei Funktionen, die NotificationView verlangt.
let dnd = false
let unseen = 0
const listeners: Array<() => void> = []
const notifications = {
  dnd: () => dnd,
  unseen: () => unseen,
  onChange: (listener: () => void) => { listeners.push(listener) },
}
function announce(): void {
  for (const listener of listeners) listener()
}

Gtk.init()

const window = new Gtk.Window({ title: "zepos-notification-bar" })
const bar = BarContent("PROBE-1", () => {}, () => 3840, notifications)
window.set_child(bar)
window.set_default_size(1920, 60)
window.present()

/** Das Glockenmodul im linken Kasten, oder null. */
function bell(): Gtk.Widget | null {
  const box = bar.get_start_widget() as Gtk.Box | null
  let child = box ? box.get_first_child() : null
  while (child) {
    if (child.get_name() === "custom-notifications") return child
    child = child.get_next_sibling()
  }
  return null
}

/** Was ein Modul sagt - aus seiner Zelle und seinem Wert zusammen.
 *
 * ZWEI STUECKE SEIT DEM 20.08.2026 (Aufgabe 41). Hier stand
 * `widget.get_first_child() as Gtk.Label`, also die Annahme, ein Modul
 * sei EINE Beschriftung. Seit die Glocke ihr Zeichen in einer eigenen
 * Zelle traegt (ModuleLabel in src/templates/ags-bar.template, die
 * ganze Messung steht dort), ist das erste Kind ein Gtk.CenterBox und
 * `get_label` gibt es darauf nicht.
 *
 * GEAENDERT HAT SICH DAS MESSGERAET UND KEINE ZUSICHERUNG: was diese
 * Datei aufschreibt, ist unveraendert "was steht auf der Leiste", und
 * die Zeilen in test_bar_notifications.py fragen unveraendert danach.
 * Der Trenner ist ein Leerzeichen - genau das, was zwischen Zeichen und
 * Wert stand, bevor splitSymbol() es dem Stylesheet ueberliess.
 */
function shown(widget: Gtk.Widget): string {
  const stuecke: string[] = []
  let piece = widget.get_first_child()
  while (piece) {
    const label = piece instanceof Gtk.Label ? piece
      : (piece.has_css_class("bar-symbol")
         ? piece.get_first_child() : null)
    if (label instanceof Gtk.Label && piece.visible && label.get_label()) {
      stuecke.push(label.get_label())
    }
    piece = piece.get_next_sibling()
  }
  return stuecke.join(" ")
}

/** Sichtbarkeit, Beschriftung und Klassen - in einer Zeile. */
function record(label: string): void {
  const widget = bell()
  if (!widget) {
    lines.push(`${label}:FEHLT::`)
    return
  }
  const text = shown(widget)
  const state = widget.visible ? "sichtbar" : "verborgen"
  lines.push(`${label}:${state}:${text}:${widget.get_css_classes().join(" ")}`)
}

// Der Ruhezustand zuerst - er ist der haeufigste und der, in dem das
// Modul NICHTS kosten darf.
record("ruhe")

unseen = 3
announce()
record("ungesehen")

unseen = 0
dnd = true
announce()
record("dnd")

// Und wieder zurueck. Ein Modul, das einmal aufgegangen ist und nicht
// mehr verschwindet, waere achtzehneinhalb Module statt achtzehn.
dnd = false
announce()
record("zurueck")

GLib.file_set_contents(TRACE, new TextEncoder().encode(lines.join("\n")))
