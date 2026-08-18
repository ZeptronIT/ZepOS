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

/** Sichtbarkeit, Beschriftung und Klassen - in einer Zeile. */
function record(label: string): void {
  const widget = bell()
  if (!widget) {
    lines.push(`${label}:FEHLT::`)
    return
  }
  const text = (widget.get_first_child() as Gtk.Label).get_label()
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
