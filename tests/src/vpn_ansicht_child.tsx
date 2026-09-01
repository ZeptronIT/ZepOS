// SPDX-License-Identifier: GPL-3.0-or-later
//
// Die VPN-Seite blaettert von der Liste in die Einzelheit und zurueck -
// wirklich geklickt, und danach nachgesehen, was sichtbar ist.
//
// WARUM ES DIESES KIND GIBT (01.09.2026)
//     Bestellt, woertlich: "ich will eine reine liste bei vpn sehen,
//     und bei klick auf das item einer vpn oder 'neu erstellen' will
//     ich auf die details kommen."
//
//     Bis dahin hing `mainBox` drei Kaesten untereinander - Liste,
//     verbundene Ansicht, Formular -, und zwei davon waren immer
//     zugleich zu sehen. Eine Vorlage zu LESEN kann bezeugen, dass dort
//     jetzt zwei Huellen stehen; nicht, dass ein Klick auf eine Zeile
//     die eine aus- und die andere einblendet, und schon gar nicht,
//     dass der Zurueck-Knopf zurueckfuehrt. Genau diese drei sind die
//     Frage.
//
// WARUM DIESELBE VORRICHTUNG WIE vpn_schalter_child.tsx
//     Gebaut wird GENAU die Funktion, die auf dem Schreibtisch die
//     Seite baut (`vpnSeite.bauen`), in demselben Aufbau (broadwayd,
//     eigenes XDG_RUNTIME_DIR, ein vpn.py, das "disconnected" druckt).
//     Der Python-Teil dieser Messung leiht sich `_baue`/`_lauf` aus
//     tests/src/test_vpn_schalter.py, statt sie abzuschreiben.
//
// WAS "SICHTBAR" HIER HEISST
//     `Gtk.Widget.is_visible()` - der Wert, der die VORFAHREN einbezieht.
//     `get_visible()` allein saehe nur die eigene Flagge und meldete die
//     Liste auch dann als sichtbar, wenn die Huelle darum ausgeblendet
//     ist. Genau das waere der Fehler, den es zu finden gilt.

import { Gtk, Gdk } from "ags/gtk4"
import GLib from "gi://GLib"
import { vpnSeite } from "./widget/VpnManager"

const TRACE = GLib.getenv("ZEPOS_TRACE") ?? ""
const marks: string[] = []

function mark(name: string, value: string): void {
  marks.push(`${name}:${value}`)
}

Gtk.init()

const CSS = GLib.getenv("ZEPOS_CSS") ?? ""
const display = Gdk.Display.get_default()
if (CSS && display) {
  const provider = new Gtk.CssProvider()
  provider.load_from_path(CSS)
  Gtk.StyleContext.add_provider_for_display(
    display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
}

const window = new Gtk.Window({ title: "zepos-vpn-ansicht" })
// `as any`: siehe vpn_schalter_child.tsx - der Typ verlangt eine
// Astal.Window, der KOERPER von bauen() verlangt `visible` und
// `connect`, und beides hat ein Gtk.Window.
const seite = vpnSeite.bauen(window as any, () => {}, () => true)
window.set_child(seite)
window.set_default_size(700, 900)
window.present()

/** Der erste Nachfahre, auf den `treffer` zutrifft - in Tiefensuche. */
function suche(widget: Gtk.Widget | null,
               treffer: (w: Gtk.Widget) => boolean): Gtk.Widget | null {
  if (!widget) return null
  if (treffer(widget)) return widget
  let kind = widget.get_first_child()
  while (kind) {
    const gefunden = suche(kind, treffer)
    if (gefunden) return gefunden
    kind = kind.get_next_sibling()
  }
  return null
}

/** Ueber die KLASSEN gesucht und nicht ueber die Reihenfolge der
 * Kinder: `.vpn-connection-list`, `.vpn-connected-view`, `.vpn-form`
 * und `.vpn-detail-back` sind die Namen, die die Vorlage vergibt - ein
 * Zaehlen von Kindern maesse den Aufbau der Seite statt ihrer Teile. */
const liste = suche(seite, (w) => w.has_css_class("vpn-connection-list"))
const formular = suche(seite, (w) => w.has_css_class("vpn-form"))
const zurueckZeile = suche(seite, (w) => w.has_css_class("vpn-detail-back"))

function sichtbar(w: Gtk.Widget | null): string {
  if (!w) return "fehlt"
  return w.is_visible() ? "ja" : "nein"
}

/** Liste|Formular - der Zustand der Seite in einer Zeile. */
function lage(): string {
  return `${sichtbar(liste)}|${sichtbar(formular)}`
}

/** Was ein Widget von sich aus verlangt: "<breite>x<hoehe>".
 *
 * Die natuerliche Breite bei unbeschraenkter Hoehe, und dann die
 * natuerliche Hoehe FUER GENAU DIESE BREITE - `measure(VERTICAL, -1)`
 * fragte nach der Hoehe fuer eine unbekannte Breite, und eine Zeile
 * mit gekuerztem Text antwortet darauf etwas anderes als im Fenster.
 */
function anspruch(w: Gtk.Widget | null): string {
  if (!w) return "fehlt"
  const [, breite] = w.measure(Gtk.Orientation.HORIZONTAL, -1)
  const [, hoehe] = w.measure(Gtk.Orientation.VERTICAL, breite)
  return `${breite}x${hoehe}`
}

/** Die anklickbaren Zeilen der Liste: zepRow mit `aktion` ist ein
 * Gtk.Button mit der Klasse `zep-row-click` (siehe ags-kit.template). */
function zeilenKnoepfe(): Gtk.Button[] {
  const gefunden: Gtk.Button[] = []
  let kind = liste ? liste.get_first_child() : null
  while (kind) {
    if (kind instanceof Gtk.Button && kind.has_css_class("zep-row-click")) {
      gefunden.push(kind)
    }
    kind = kind.get_next_sibling()
  }
  return gefunden
}

const loop = GLib.MainLoop.new(null, false)

// Dieselben zwei Wartezeiten wie in vpn_schalter_child.tsx, aus
// denselben Gruenden: die Seite fragt beim Sichtbarwerden den
// Tunnelstand ab (ein Unterprozess), und ein Zustand, der gleich wieder
// eingesammelt wird, ist keiner.
const ANLAUF_MS = 700
const NACHLAUF_MS = 300

GLib.timeout_add(GLib.PRIORITY_DEFAULT, ANLAUF_MS, () => {
  mark("liste", liste ? "da" : "fehlt")
  mark("zurueck-knopf", zurueckZeile ? "da" : "fehlt")
  mark("lage-anfang", lage())
  mark("zeilen", String(zeilenKnoepfe().length))
  // Was die Liste braucht und was die ganze Seite braucht - in DIESEM
  // Zustand, also mit der Liste als einziger sichtbarer Ansicht. Die
  // Zahlen wandern in den Bericht: "wieviel die Liste braucht" war eine
  // der Fragen, und sie soll gemessen beantwortet sein.
  mark("anspruch-liste", anspruch(liste))
  mark("anspruch-seite", anspruch(seite))

  const ziel = Number(GLib.getenv("ZEPOS_ZEILE") ?? "1")
  const knopf = zeilenKnoepfe()[ziel]
  if (!knopf) {
    mark("geklickt", "keine-zeile")
    GLib.timeout_add(GLib.PRIORITY_DEFAULT, NACHLAUF_MS, () => {
      mark("lage-nach-klick", lage())
      mark("lage-nach-zurueck", lage())
      fertig()
      return false
    })
    return false
  }

  // GTK4 kennt kein "Zeigerdruck von aussen"; was ein Klick auf einen
  // Gtk.Button ausloest, ist genau dieses Signal - `aktion` haengt in
  // zepRow an "clicked" (ags-kit.template). emit() geht also durch
  // dieselbe Tuer wie ein Finger.
  knopf.emit("clicked")
  mark("geklickt", "zeile-" + String(ziel))

  GLib.timeout_add(GLib.PRIORITY_DEFAULT, NACHLAUF_MS, () => {
    mark("lage-nach-klick", lage())

    // Und wieder zurueck. Der Knopf sitzt als einziges Kind in der
    // Zeile mit der Klasse `.vpn-detail-back`.
    const zurueck = zurueckZeile
      ? suche(zurueckZeile, (w) => w instanceof Gtk.Button)
      : null
    if (!zurueck) {
      mark("zurueck", "fehlt")
    } else {
      ;(zurueck as Gtk.Button).emit("clicked")
      mark("zurueck", "geklickt")
    }

    GLib.timeout_add(GLib.PRIORITY_DEFAULT, NACHLAUF_MS, () => {
      mark("lage-nach-zurueck", lage())
      fertig()
      return false
    })
    return false
  })
  return false
})

function fertig(): void {
  if (TRACE) {
    GLib.file_set_contents(
      TRACE, new TextEncoder().encode(marks.join("\n") + "\n"))
  }
  print(marks.join("\n"))
  loop.quit()
}

loop.run()
