// SPDX-License-Identifier: GPL-3.0-or-later
//
// Das vierte Kind von tests/src/test_bar_headless.py: es baut die zwei
// freistehenden Knoepfe am Dock - den Abschaltknopf unten links und den
// Starterknopf unten rechts - und schreibt auf, wo die TINTE ihres
// Zeichens in ihrer Platte liegt und in welcher Schrift sie gezeichnet
// wurde.
//
// WARUM ES DIESES KIND SEIT DEM 20.08.2026 GIBT (Aufgabe 47)
//     GEMELDET, woertlich: "die 6 punkte sind nicht zentriert".
//
//     Das Messgeraet dieses Hauses konnte die Frage nicht beantworten.
//     bar_fit_child.tsx misst die Lage der Tinte seit dem selben Tag -
//     aber nur fuer die LEISTE: es baut BarContent(), und was in einem
//     EIGENEN Fenster steht, kommt darin nicht vor. Genau deshalb ist
//     derselbe Fehler an diesen zwei Knoepfen dreimal unbemerkt geblieben
//     (fehlende Schriftgroesse am 19.08., fehlende Schriftfamilie am
//     20.08., die Mitte des Zeichens heute): jedes Mal, weil ein eigenes
//     Fenster nichts von der Leiste erbt, und jedes Mal gemeldet vom
//     Nutzer statt von einer Zusicherung.
//
// WARUM DER INHALT UND NICHT DAS LAYER-SHELL-FENSTER
//     Dieselbe Trennung und derselbe Grund wie in
//     bar_headless_child.tsx: Astal.Window ruft in ihrem Konstruktor
//     gtk_layer_init_for_window auf, und das prueft
//     GDK_IS_WAYLAND_DISPLAY. Deshalb sind PowerButtonContent() und
//     StarterButtonContent() in ihren Vorlagen von PowerButton() und
//     StarterButton() getrennt - dieses Kind baut GENAU die Funktion,
//     die auf dem Schreibtisch die Platte baut, und keinen Nachbau
//     davon.
//
// WARUM EIN Gtk.Fixed UND KEIN window.set_child(plate)
//     Ein Gtk.Window teilt seinem Kind die GANZE Fensterflaeche zu. Die
//     Platte waere damit so breit wie das Fenster, ihr einziger Knopf
//     staende am linken Rand, und "sitzt das Zeichen mittig in der
//     Platte" waere eine Frage ueber eine Platte, die es nicht gibt.
//
//     Auf dem Schreibtisch ist die Flaeche INHALTSBEMESSEN: sie ist an
//     BOTTOM und einer Seitenkante verankert, also genau so gross wie
//     ihr Inhalt. Ein Gtk.Fixed tut dasselbe - es teilt seinen Kindern
//     ihre NATUERLICHE Groesse zu. Das ist derselbe Griff, mit dem
//     bar_fit_child.tsx seine Proben nebeneinanderlegt.
//
// WARUM JE EIN EIGENES FENSTER UND NICHT BEIDE IN EINEM
//     Weil die Schrift an der FLAECHE haengt und nicht am Knopf:
//     window.power-button-window und window.starter-button-window sind
//     zwei verschiedene Wahlausdruecke in bar.css, und genau das, was
//     sie nennen (Familie und Schnitt), ist der Posten, der hier
//     gemessen werden soll. Beide Platten in einem Fenster bekaemen die
//     Schrift EINES der beiden Wahlausdruecke - und der Lauf waere
//     gruen, obwohl der andere leer ist.

import { Gtk, Gdk } from "ags/gtk4"
import GLib from "gi://GLib"
import Pango from "gi://Pango"
import { PowerButtonContent } from "./widget/PowerButton"
import { StarterButtonContent } from "./widget/StarterButton"

const TRACE = GLib.getenv("ZEPOS_TRACE") ?? ""
const CSS = GLib.getenv("ZEPOS_CSS") ?? ""
const lines: string[] = []

Gtk.init()

const display = Gdk.Display.get_default()
if (CSS && display) {
  const provider = new Gtk.CssProvider()
  provider.load_from_path(CSS)
  Gtk.StyleContext.add_provider_for_display(
    display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
}

interface Probe {
  /** Der Name der Platte - derselbe, den die Vorlage set_name() gibt. */
  name: string
  /** Die Klasse der Flaeche, aus der die Schrift kommt. */
  klasse: string
  plate: Gtk.Widget
  /** Der gemeinsame Bezugspunkt - siehe messen(), warum es einen gibt. */
  root: Gtk.Fixed
}

// Die zwei Knoepfe. Sie stehen hier als Aufzaehlung, weil ein
// TypeScript-Kind keine Vorlagen durchsuchen kann - dass es GENAU diese
// zwei sind und nicht drei, prueft die Python-Seite an den Quellen
// (test_every_freestanding_button_window_uses_the_cell_the_bar_uses). Kommt ein
// dritter dazu, wird dort rot, bis er auch hier steht.
const proben: Probe[] = [
  {
    name: "power-button",
    klasse: "power-button-window",
    plate: PowerButtonContent(() => {}),
    root: new Gtk.Fixed(),
  },
  {
    name: "starter-button",
    klasse: "starter-button-window",
    plate: StarterButtonContent(),
    root: new Gtk.Fixed(),
  },
]

for (const probe of proben) {
  const window = new Gtk.Window({ title: `zepos-${probe.name}` })
  window.add_css_class(probe.klasse)
  window.set_child(probe.root)
  probe.root.put(probe.plate, 0, 0)
  window.set_default_size(400, 200)
  window.present()
}

/** Wo ein Widget liegt, gemessen gegen `root`: (links, Breite). */
function bounds(widget: Gtk.Widget, root: Gtk.Widget): [number, number] {
  const [ok, rect] = widget.compute_bounds(root)
  if (!ok) return [-1, -1]
  return [Math.round(rect.get_x()), Math.round(rect.get_width())]
}

/** Wie hoch ein Widget ist. */
function hoehe(widget: Gtk.Widget): number {
  const [ok, rect] = widget.compute_bounds(widget)
  return ok ? Math.round(rect.get_height()) : -1
}

/** Der erste Nachfahre, auf den `treffer` zutrifft - in Tiefensuche. */
function suche(widget: Gtk.Widget | null,
               treffer: (w: Gtk.Widget) => boolean): Gtk.Widget | null {
  if (!widget) return null
  if (treffer(widget)) return widget
  let child = widget.get_first_child()
  while (child) {
    const gefunden = suche(child, treffer)
    if (gefunden) return gefunden
    child = child.get_next_sibling()
  }
  return null
}

function messen(probe: Probe): void {
  const plate = probe.plate
  // ALLES GEGEN EINEN GEMEINSAMEN BEZUGSPUNKT, UND DAS IST GEMESSEN
  // (20.08.2026).
  //
  // Hier stand `bounds(kind, plate)`, also die Platte selbst als
  // Bezugspunkt - und das mischt zwei Koordinatensysteme. GEMESSEN mit
  // genau diesem Aufbau: `platte 53x57`, aber `kasten 0+43` fuer einen
  // Knopf, der 5 Punkte vom Plattenrand entfernt sitzt.
  //
  // Der Grund ist GTK4s Kastenmodell: die BREITE eines Widgets ist die
  // seines Rahmenkastens (53 = 43 + zweimal 4 Polsterung + zweimal
  // 1 Rahmen), die Koordinaten seiner KINDER zaehlen dagegen ab dem
  // Inhaltskasten. Beides in einer Rechnung ergibt einen Rand, der um
  // die Polsterung daneben liegt - die Zahl sah nach "nicht zentriert"
  // aus und war eine falsche Messung.
  //
  // Das Gtk.Fixed darum ist der eine Bezugspunkt, in dem beide Angaben
  // dasselbe bedeuten.
  const root = probe.root
  const [px, pw] = bounds(plate, root)

  lines.push(`knopf ${probe.name}`)
  lines.push(`  platte ${pw}x${hoehe(plate)}`)

  const button = suche(plate, w => w instanceof Gtk.Button)
  if (button) {
    const [bx, bw] = bounds(button, root)
    lines.push(`  kasten ${bx - px}+${bw}`)
  }

  // Die Zelle, wenn es eine gibt. Sie hat die Klasse, die auch jedes
  // Modul der Leiste traegt - danach wird gesucht und nicht nach einem
  // Gtk.CenterBox: die Klasse ist das, was die Vorlagen teilen.
  const cell = suche(plate, w => w.has_css_class("bar-symbol"))
  if (cell) {
    const [cx, cw] = bounds(cell, root)
    lines.push(`  zelle ${cx - px}+${cw}`)
  } else {
    lines.push("  zelle keine")
  }

  const symbol = suche(plate, w => w instanceof Gtk.Label) as Gtk.Label | null
  if (!symbol) {
    lines.push("  tinte fehlt")
    return
  }

  // GEMESSEN WIRD DER SATZ UND NICHT DAS WIDGET - dieselbe
  // Unterscheidung, die bar_fit_child.tsx in seinem Kopf begruendet:
  // eine Gtk.Label ist nicht ihr Text, und get_layout_offsets() gibt
  // die Lage des PangoLayout in Widget-Koordinaten.
  const [sx] = bounds(symbol, root)
  const [ox] = symbol.get_layout_offsets()
  const layout = symbol.get_layout()
  const [tinte, vorschub] = layout.get_pixel_extents()
  const anfang = sx + ox

  const tl = anfang + tinte.x - px
  lines.push(`  tinte ${tl}:${pw - tl - tinte.width}`)
  const vl = anfang + vorschub.x - px
  lines.push(`  zeichen ${vl}:${pw - vl - vorschub.width}`)
  lines.push(`  ausmass ${tinte.width}x${tinte.height}`)

  if (cell) {
    const [cx, cw] = bounds(cell, root)
    const ctl = anfang + tinte.x - cx
    lines.push(`  tinte-zelle ${ctl}:${cw - ctl - tinte.width}`)
  }

  // DIE SCHRIFT, DIE DAS ZEICHEN WIRKLICH BEKOMMEN HAT.
  //
  // Nicht das, was in bar.css steht - das ist die Absicht -, sondern
  // das, was GTK dem Widget daraus zugeteilt hat. Genau hier klafft die
  // Luecke, an der dieser Knopf dreimal gescheitert ist: ein eigenes
  // Fenster erbt Familie, Schnitt und Groesse der Leiste nicht, und wo
  // sie fehlen, steht die Vorgabe des GTK-Themas.
  const beschreibung = symbol.get_pango_context().get_font_description()
  const familie = beschreibung.get_family() ?? ""
  const schnitt = beschreibung.get_weight()
  const groesse = beschreibung.get_size() / Pango.SCALE
  const absolut = beschreibung.get_size_is_absolute() ? "px" : "pt"
  lines.push(`  schrift ${familie}|${schnitt}|${groesse}|${absolut}`)
}

const loop = GLib.MainLoop.new(null, false)
// Eine halbe Sekunde: hier laeuft kein Skript und wird nichts
// nachgeladen, aber die Zeichen werden erst gemittet, wenn die
// Beschriftung an der Anzeige haengt ("map", siehe SymbolCell in
// ags-bar.template) - und das ist der Takt, den es abzuwarten gilt.
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
  for (const probe of proben) messen(probe)
  if (TRACE) {
    GLib.file_set_contents(TRACE, new TextEncoder().encode(lines.join("\n") + "\n"))
  }
  print(lines.join("\n"))
  loop.quit()
  return false
})

loop.run()
