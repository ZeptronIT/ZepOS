// SPDX-License-Identifier: GPL-3.0-or-later
//
// Eine Zeile der Geraeteliste wirklich angeklickt - und danach
// nachgesehen, WELCHE bluetoothctl-Aufrufe das ausgeloest hat.
//
// WAS GEMELDET WURDE
//     Der Nutzer, woertlich: "ausserdem habe ich irgendwie
//     schwierigkeiten meine maus zu finden" und "nein ich finde per
//     bluetooth meine maus nicht egal mache erstmal weiter mit dem
//     rest". Die Meldung ist seither offen.
//
// WARUM EIN KIND UND KEIN PYTHON-TEST AUF DEN QUELLTEXT
//     tests/src/test_bluetooth_pairing.py hat 500 Zeilen und prueft
//     ausschliesslich TEXT: `"RequestAuthorization" in code`,
//     `'CAPABILITY = "KeyboardDisplay"' in code`. Solche Zusicherungen
//     bezeugen, dass ein Wort in einer Vorlage steht - nicht, was beim
//     Klick auf ein Geraet geschieht. Genau das ist hier die Frage, und
//     sie ist nur an einem laufenden Fenster zu beantworten.
//
// WARUM bluetoothSeite.bauen() UND KEIN NACHBAU
//     Dieselbe Trennung wie in vpn_schalter_child.tsx: gebaut wird
//     GENAU die Funktion, die auf dem Schreibtisch die Seite baut.
//     `bauen` erwartet eine Astal.Window; ein Gtk.Window genuegt ihr,
//     weil sie davon nur `visible` und `connect` benutzt (siehe das
//     Ende von bauen() in ags-bluetooth.template) - Astal.Window ruft
//     in ihrem Konstruktor gtk_layer_init_for_window, und das verlangt
//     einen Wayland-Compositor, den es hier nicht gibt.
//
// WAS DIESES KIND NICHT ANFASST
//     Den Adapter dieser Maschine. `bluetoothctl` ist im PATH dieses
//     Laufs eine Attrappe, die NUR mitschreibt und antwortet - der
//     echte Adapter, der echte Dienst und die echten gekoppelten
//     Geraete des Nutzers bleiben unberuehrt. Der PATH traegt das
//     Attrappenverzeichnis VORNE; die Begruendung steht in
//     tests/src/test_bluetooth_kopplung.py.

import { Gtk, Gdk } from "ags/gtk4"
import GLib from "gi://GLib"
import { bluetoothSeite } from "./widget/BluetoothManager"

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

const window = new Gtk.Window({ title: "zepos-bluetooth-kopplung" })
// `as any`: siehe den Kopf - der Typ verlangt eine Astal.Window, der
// KOERPER von bauen() verlangt `visible` und `connect`.
const seite = bluetoothSeite.bauen(window as any, () => {}, () => true)
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

/** Der Text der ersten Beschriftung mit dieser Klasse. */
function text(wurzel: Gtk.Widget, klasse: string): string {
  const treffer = suche(wurzel, (w) => w.has_css_class(klasse))
  return treffer instanceof Gtk.Label ? treffer.get_label() : ""
}

// Die Liste ueber ihre Klasse und nicht ueber die Reihenfolge der
// Kinder: `.bt-list` ist der Name, den ags-bluetooth.template vergibt
// (deviceList.add_css_class), und ein Zaehlen von Kindern maesse den
// Aufbau der Seite statt der Liste.
const liste = suche(seite, (w) => w.has_css_class("bt-list"))

interface Zeile {
  titel: string
  unter: string
  huelle: Gtk.Button | null
}

function zeilen(): Zeile[] {
  const gefunden: Zeile[] = []
  let kind = liste ? liste.get_first_child() : null
  while (kind) {
    const rahmen = suche(kind, (w) => w.has_css_class("zep-row"))
    if (rahmen) {
      // Die anklickbare Huelle. zepRow mit `aktion` liefert einen
      // Gtk.Button mit dieser Klasse und haengt den Rueckruf an
      // "clicked" (ags-kit.template) - ein emit("clicked") geht also
      // durch dieselbe Tuer wie ein Zeigerdruck.
      const huelle = suche(kind, (w) => w.has_css_class("zep-row-click"))
      gefunden.push({
        titel: text(kind, "zep-row-title"),
        unter: text(kind, "zep-row-sub"),
        huelle: huelle instanceof Gtk.Button ? huelle : null,
      })
    }
    kind = kind.get_next_sibling()
  }
  return gefunden
}

/** Die Zeilen als eine Zeile Text: Titel|Nebenzeile|anklickbar. */
function aufschrift(): string {
  return zeilen().map((z) => [
    z.titel, z.unter, z.huelle ? "klickbar" : "starr",
  ].join("|")).join(";")
}

const loop = GLib.MainLoop.new(null, false)

// ANLAUF: `container.connect("map", ...)` loest updateDisplay() aus,
// und das fragt vier Unterprozesse GLEICHZEITIG (siehe die Messung in
// ags-bluetooth.template). Vor deren Antwort zu messen hiesse, die
// leere Liste zu messen - den Zustand, den niemand zu sehen bekommt.
const ANLAUF_MS = 900

// UND EIN NACHLAUF, der lang genug ist fuer die ganze Kette, die ein
// Klick ausloest. Die Attrappe antwortet sofort; was hier gewartet
// wird, ist der Weg durch execAsync und zurueck.
const NACHLAUF_MS = 1500

GLib.timeout_add(GLib.PRIORITY_DEFAULT, ANLAUF_MS, () => {
  mark("liste", liste ? "da" : "fehlt")
  mark("zeilen-vorher", aufschrift())

  // Angeklickt wird die Zeile mit DIESEM Titel und nicht die an einer
  // Position: welche Zeile wo steht, entscheidet die Sortierung der
  // Seite (verbunden, dann gekoppelt, dann gefunden), und ein Test, der
  // an einer Position haengt, misst beim naechsten Umsortieren etwas
  // anderes, ohne es zu sagen.
  const ziel = GLib.getenv("ZEPOS_ZIEL") ?? ""
  const zeile = zeilen().find((z) => z.titel === ziel)
  if (!zeile) {
    mark("geklickt", "keine-zeile")
  } else if (!zeile.huelle) {
    mark("geklickt", "nicht-klickbar")
  } else {
    zeile.huelle.emit("clicked")
    mark("geklickt", zeile.titel)
  }

  GLib.timeout_add(GLib.PRIORITY_DEFAULT, NACHLAUF_MS, () => {
    mark("zeilen-nachher", aufschrift())
    if (TRACE) {
      GLib.file_set_contents(
        TRACE, new TextEncoder().encode(marks.join("\n") + "\n"))
    }
    print(marks.join("\n"))
    loop.quit()
    return false
  })
  return false
})

loop.run()
