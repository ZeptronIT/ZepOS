// SPDX-License-Identifier: GPL-3.0-or-later
//
// Das Dock mit ABGELEGTEN Fenstern darin - gebaut, aufgeschrieben,
// angeklickt.
//
// WARUM EIN VIERTES KIND UND NICHT EINE ZEILE IN dock_headless_child
//     Jenes Kind misst ein Dock OHNE Compositor: Hyprland.refresh()
//     findet keinen Socket, meldet den leeren Zustand, und die Frage
//     dort lautet "steht der Fuss da, obwohl kein Fenster offen ist".
//
//     Die Frage hier ist die genaue Gegenrichtung - was macht der Fuss
//     aus Fenstern, und zwar aus abgelegten. Dafuer muss ein Compositor
//     antworten, und der Test daneben stellt einen hin: ein Unix-Socket
//     unter $XDG_RUNTIME_DIR/hypr/<Kennung>/.socket.sock, der auf
//     `j/clients` eine Tabelle zurueckgibt, die der Test bestimmt, und
//     der jedes `dispatch ...` mitschreibt.
//
//     Zwei Kinder und nicht eines, weil die beiden Umgebungen sich
//     widersprechen: das eine BRAUCHT den fehlenden Socket.
//
// WARUM DER KLICK HIER STATTFINDET UND NICHT IM TEST
//     Ein Gtk.Button hat sein "clicked" im Prozess, der ihn gebaut hat.
//     Von aussen liesse sich hoechstens ein Zeigerereignis schicken, und
//     dann maesse der Lauf, ob der Zeiger den Knopf trifft - eine andere
//     Frage als die, welchen Befehl der Knopf absetzt.

import { Gtk, Gdk } from "ags/gtk4"
import GLib from "gi://GLib"
import { DockContent } from "./widget/Dock"

const TRACE = GLib.getenv("ZEPOS_TRACE") ?? ""
const marks: string[] = []

function mark(name: string, value: string): void {
  marks.push(`${name}:${value}`)
}

Gtk.init()

// Dasselbe Stylesheet wie im Nachbarkind, und aus demselben Grund: ohne
// es misst `hoehe` unten die Hoehe einer Adwaita-Knopfreihe und nicht
// die des Fusses, den ZepOS ausliefert.
const CSS = GLib.getenv("ZEPOS_CSS") ?? ""
const display = Gdk.Display.get_default()
if (CSS && display) {
  const provider = new Gtk.CssProvider()
  provider.load_from_path(CSS)
  Gtk.StyleContext.add_provider_for_display(
    display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
}

const window = new Gtk.Window({ title: "zepos-dock-abgelegt" })
const dock = DockContent()
window.add_css_class("dock-window")
window.set_child(dock)
window.set_default_size(1920, 96)
window.present()

// Was auf dem Fuss steht, in der Reihenfolge, in der es dort steht -
// die Reihenfolge ist die halbe Bestellung ("rechts neben den standard
// icons").
const zeilen: string[] = []
let kind: Gtk.Widget | null = dock.get_first_child()
while (kind) {
  const klassen = kind.get_css_classes().join(" ")
  const name = kind.get_tooltip_text() ?? kind.get_css_name()
  zeilen.push(`${name}[${klassen}]${kind.visible ? "" : "(aus)"}`)
  kind = kind.get_next_sibling()
}
mark("kinder", zeilen.join(","))

// Die Hoehe des Fusses MIT diesem Inhalt. Der Test laesst dasselbe Kind
// zweimal laufen - einmal mit abgelegten Fenstern, einmal mit denselben
// Fenstern auf einem gewoehnlichen Bereich - und vergleicht die beiden
// Zahlen. Sie muessen gleich sein: der Fuss haelt eine exklusive Zone,
// ein Punkt mehr schoebe jedes Fenster des Schirms.
mark("hoehe", String(dock.measure(Gtk.Orientation.VERTICAL, -1)[0]))

/** Der Knopf mit dieser Aufschrift, oder null. */
function knopf(aufschrift: string): Gtk.Button | null {
  let kind: Gtk.Widget | null = dock.get_first_child()
  while (kind) {
    if (kind.get_tooltip_text() === aufschrift) return kind as Gtk.Button
    kind = kind.get_next_sibling()
  }
  return null
}

// Die Knoepfe, die dieser Lauf anklicken soll - durch "|" getrennt,
// weil eine Aufschrift wie "Dateien (1)" ein Leerzeichen enthaelt und
// ein Komma in einem Fenstertitel stehen darf.
for (const gesucht of (GLib.getenv("ZEPOS_KLICKS") ?? "").split("|")) {
  if (!gesucht) continue
  const button = knopf(gesucht)
  if (!button) {
    mark("klick-ohne-knopf", gesucht)
    continue
  }
  button.emit("clicked")
  mark("geklickt", gesucht)
}

if (TRACE) {
  GLib.file_set_contents(TRACE, new TextEncoder().encode(marks.join("\n") + "\n"))
}
print(marks.join("\n"))
