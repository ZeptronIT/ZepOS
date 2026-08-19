// SPDX-License-Identifier: GPL-3.0-or-later
//
// Das zweite Kind von tests/src/test_bar_headless.py: es baut die
// erzeugte Leiste auf mehreren Schirmbreiten und schreibt auf, wo jedes
// Modul liegt und wie gross es sein will.
//
// ES HIESS bar_width_child.tsx UND MASS BREITEN, DANN bar_fit_child
//     Die Leiste lief bis zum 11.08.2026 waagerecht, war fuer einen Tag
//     eine Seitenleiste und liegt seit dem 12.08.2026 wieder oben. Der
//     Name nennt deshalb weiter nicht die Achse, sondern die Frage:
//     passt es. Er hat die Drehung hin und die Drehung zurueck
//     ueberstanden, und das ist der Beleg dafuer, dass er richtig
//     gewaehlt war.
//
// WARUM EIN ZWEITES KIND UND NICHT EIN ZWEITER DURCHGANG IM ERSTEN
//     bar_headless_child.tsx baut die Leiste OHNE ihr Stylesheet und
//     misst daran, was sie enthaelt: welche Module, in welcher
//     Reihenfolge, mit welchem Text. Dafuer ist das Stylesheet
//     gleichgueltig.
//
//     Fuer die Groesse ist es alles. GEMESSEN am 11.08.2026: ohne
//     bar.css meldet dieselbe Leiste ein Vielfaches weniger - die
//     Vorlage traegt die Schriftgroesse (24 px bei sizes.scale 1.85) und
//     alle Innen- und Aussenabstaende. Ein Groessentest ohne Stylesheet
//     misst eine Leiste, die es nicht gibt.
//
// WARUM EINE EIGENE FLAECHE UND KEIN GEWOEHNLICHES FENSTER
//     Ein Gtk.Window wird nie kleiner als sein Inhalt: `set_default_size
//     (800, ...)` an einer Leiste, die 1200 braucht, ergibt ein 1200 px
//     breites Fenster und keinen Ueberlauf. Unter gtk4-broadwayd kommt
//     noch dazu, dass der Anzeigeserver ohne verbundenen Browser einen
//     festen Schirm von 1024x768 meldet und JEDES Fenster darauf
//     begrenzt.
//
//     Die Layer-Shell macht das Gegenteil: sie teilt der Leiste GENAU
//     die Breite des Schirms zu, und was nicht hineinpasst, wird
//     abgeschnitten. Surface unten ist diese Zuteilung, in zwei
//     vfuncs - sie meldet eine feste Groesse und gibt ihrem Kind genau
//     die. In einem Gtk.Fixed liegend bekommt sie diese Groesse auch
//     dann, wenn sie groesser ist als das Fenster: Gtk.Fixed schneidet
//     die Zuteilung seiner Kinder nicht auf die eigene zu.

import { Gtk, Gdk } from "ags/gtk4"
import GLib from "gi://GLib"
import GObject from "gi://GObject"
import { BAR_THICKNESS, BarContent } from "./widget/Bar"

const TRACE = GLib.getenv("ZEPOS_TRACE") ?? ""
const WIDTHS = (GLib.getenv("ZEPOS_WIDTHS") ?? "1920").split(",").map(Number)
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

const Surface = GObject.registerClass({ GTypeName: "ZepOSProbeSurface" },
  class Surface extends Gtk.Widget {
    _child!: Gtk.Widget
    _w!: number
    _h!: number
    _init(child: Gtk.Widget, w: number, h: number) {
      // @ts-ignore - _init ist der GJS-Konstruktor, kein TypeScript-Erbe
      super._init()
      this._child = child
      this._w = w
      this._h = h
      child.set_parent(this)
    }
    vfunc_measure(orientation: Gtk.Orientation, _forSize: number) {
      const size = orientation === Gtk.Orientation.HORIZONTAL ? this._w : this._h
      return [size, size, -1, -1]
    }
    vfunc_size_allocate(width: number, height: number, baseline: number) {
      this._child.allocate(width, height, baseline, null)
    }
  })

interface Probe {
  width: number
  bar: Gtk.CenterBox
  surface: Gtk.Widget
  /** Was die Leiste gerade fuer die Breite ihres Schirms haelt. */
  reported: number
}

const fixed = new Gtk.Fixed()
const window = new Gtk.Window({ title: "zepos-bar-fit" })
window.add_css_class("bar-window")
window.set_child(fixed)

// Der Melder als Attrappe - dieselbe Begruendung wie in
// bar_headless_child.tsx: der echte haengt an AstalNotifd, und das
// meldet sich am D-Bus-Sitzungsbus des angemeldeten Nutzers an.
//
// Fuer die MESSUNG dieser Datei ist er ausserdem gleichgueltig: sie
// fragt, was die Leiste tut, wenn der Platz nicht reicht, und ein
// bedingtes Modul, das nichts zu sagen hat, meldet
// gtk_widget_measure 0.
const notifications = {
  dnd: () => false,
  unseen: () => 0,
  onChange: (_listener: () => void) => {},
}

const probes: Probe[] = []
let offset = 0
for (const width of WIDTHS) {
  const probe = { width } as Probe
  probe.reported = width
  const bar = BarContent("PROBE-1", () => {}, () => probe.reported,
                         notifications)
  // @ts-ignore - GJS-Konstruktor
  const surface: Gtk.Widget = new Surface(bar, width, BAR_THICKNESS)
  surface.add_css_class("bar-window")
  // UNTEREINANDER und nicht nebeneinander: die Proben sind breite
  // flache Streifen. Nebeneinander gestapelt waere das Fenster so breit
  // wie ihre Summe, und Gtk.Fixed reicht das an den Anzeigeserver
  // weiter.
  fixed.put(surface, 0, offset)
  offset += BAR_THICKNESS
  probe.bar = bar
  probe.surface = surface
  probes.push(probe)
}
window.set_default_size(800, offset)
window.present()

/** Wo ein Widget waagerecht liegt: (links, Breite). */
function bounds(widget: Gtk.Widget, root: Gtk.Widget): [number, number] {
  const [ok, rect] = widget.compute_bounds(root)
  if (!ok) return [-1, -1]
  return [Math.round(rect.get_x()), Math.round(rect.get_width())]
}

function named(box: Gtk.Widget | null, want: string): Gtk.Widget | null {
  let child = box ? (box as Gtk.Box).get_first_child() : null
  while (child) {
    if (child.get_name() === want) return child
    child = child.get_next_sibling()
  }
  return null
}

// ZWEI WARTEZEITEN, UND DIE ZWEITE IST NICHT ZIERDE
//     Die erste: die Skriptmodule laufen ueber execAsync, und die Leiste
//     ist erst mit ihren Antworten so gross, wie der Nutzer sie sieht.
//     Die Entscheidung, was eingeklappt wird, faellt danach.
//
//     Die zweite gibt es NICHT MEHR, und das ist eine Reparatur.
//     Hier stand `queue_allocate()` und danach ein zweiter Zeitgeber:
//     eine Zuteilung entsteht sonst erst beim naechsten Takt der
//     Frame-Clock. GEMESSEN am 11.08.2026 - zwei Laeufe DERSELBEN Datei
//     meldeten fuer denselben Knopf zwei verschiedene Zuteilungen, weil
//     die zweite Messung eine von VOR dem letzten Einklappen las.
//
//     Ein halbe-Sekunde-Zeitgeber ist dagegen keine Loesung, sondern
//     eine Wette: er haelt, solange die Maschine nichts anderes tut.
//     GEMESSEN am selben Tag - unter der vollen Suite fiel
//     test_no_two_modules_are_drawn_on_top_of_each_other, allein
//     aufgerufen ging dieselbe Datei durch.
//
//     allocate() zwingt die Zuteilung stattdessen SOFORT und im selben
//     Aufruf. Danach ist compute_bounds() die Wahrheit, ohne dass
//     irgendwo ein Bild gezeichnet worden sein muss.
//
// UND EINE DRITTE RUNDE, DIE DIE GEGENRICHTUNG MISST
//     Einklappen ist die halbe Regel; die andere ist, dass ein Modul
//     zurueckkommt, sobald wieder Platz ist. Auf dem Schreibtisch
//     passiert das nicht, weil der Schirm sich aendert, sondern weil der
//     TEXT eines Moduls kuerzer wird - das Wetter verschwindet, die
//     Hardwarezeile faellt von "88C 12GB" auf "No HW". Nachgestellt wird
//     es hier ueber die einfachere Schraube: die schmalste Leiste
//     bekommt gesagt, ihr Schirm sei jetzt breit.
//
//     Die Neuberechnung stoesst niemand von aussen an - sie faellt beim
//     naechsten Takt eines Moduls, und clocks.sh laeuft jede Sekunde.
//     Genau das soll hier auch gemessen werden: dass die Leiste von
//     allein nachzieht.
/** Die Zuteilung sofort erzwingen, statt auf ein Bild zu warten. */
function settle(): void {
  for (const probe of probes) {
    probe.surface.allocate(probe.width, BAR_THICKNESS, -1, null)
  }
}

const loop = GLib.MainLoop.new(null, false)
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1500, () => {
  settle()
  snapshot("breite")
  for (const probe of probes) probe.reported = 7680
  // Die Neuberechnung stoesst niemand von aussen an - sie faellt beim
  // naechsten Takt eines Moduls. clocks.sh laeuft jede Sekunde, also
  // wird hier auf einen davon gewartet; DASS das reicht, ist die halbe
  // Aussage dieser Runde. Nur die Zuteilung danach wird wieder
  // erzwungen statt erwartet.
  GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1600, () => {
    settle()
    finish()
    return false
  })
  return false
})

function snapshot(prefix: string): void {
  for (const probe of probes) {
    const [minimum] = probe.bar.measure(Gtk.Orientation.HORIZONTAL, -1)
    const [tallest] = probe.bar.measure(Gtk.Orientation.VERTICAL, -1)
    const placed: string[] = []
    // Die HOEHE, die jedes Modul haben will - die Frage quer zur
    // Leiste. Sie entscheidet nicht mehr zur Laufzeit darueber, was
    // eingeklappt wird (siehe den Abschnittskopf in ags-bar.template),
    // sondern darueber, ob BAR_THICKNESS gross genug gewaehlt ist. Sie
    // wird auch fuer die eingeklappten mitgeschrieben: ein Modul im
    // Aufklappfenster ist dasselbe Modul.
    const breadth: string[] = []
    // WO DAS ZEICHEN INNERHALB SEINES MODULS SITZT (19.08.2026).
    //
    // Der Nutzer hat die Zentrierung an diesem Tag ZWEIMAL gemeldet
    // ("die icon im header sind immernoch nicht zentreirt in ihrem
    // kaestchen"), und der erste Versuch hat sie nicht behoben, weil
    // niemand sie gemessen hat: `gestellt` sagt, wo das MODUL liegt,
    // nicht, wo das Zeichen DARIN sitzt. Genau der Unterschied ist die
    // Frage, und genau dafuer gab es bis heute kein Messgeraet.
    //
    // GEMESSEN WIRD DER SATZ UND NICHT DAS WIDGET, und das ist der
    // Unterschied, an dem der erste Versuch vorbeigemessen haette: eine
    // Gtk.Label ist nicht ihr Text. Sie kann breiter sein als er (dann
    // entscheidet ihr xalign, wo er darin liegt) und sie kann genau so
    // breit sein (dann entscheidet der Kasten darum). Nur die Lage des
    // PangoLayout beantwortet beide Faelle in einer Zahl -
    // get_layout_offsets() gibt sie in Widget-Koordinaten.
    //
    // Geschrieben wird je Modul `name=links:rechts`: die beiden
    // Abstaende zwischen der Kante des Moduls und der Kante seines
    // Satzes, in denselben Koordinaten wie `gestellt`. Gleich heisst
    // zentriert; ungleich nennt die Seite, auf der es klemmt.
    const centred: string[] = []
    // Und was DIE PLATTE INNEN tragen muss.
    //
    // `tallest` oben ist die Messung des CenterBox, und die zaehlt
    // seinen eigenen Aussenrand mit - margin-top ist STYLE_GAPS_OUT,
    // also der Abstand der Platte zum Schirmrand. Das ist die richtige
    // Zahl fuer die FLAECHE (sie ist BAR_THICKNESS + EDGE_GAP hoch,
    // siehe set_default_size in ags-bar.template) und die falsche fuer
    // die PLATTE: was in die bemalten BAR_THICKNESS hineinpassen muss,
    // ist der Inhalt OHNE diesen Rand.
    //
    // Bis zum 13.08.2026 wurde `tallest` gegen BAR_THICKNESS gehalten,
    // also der Rand doppelt verlangt. Solange die Flaeche selbst
    // BAR_THICKNESS hoch war, war das richtig; seit dem 12.08.2026 ist
    // sie es nicht mehr, und die Zusicherung hat die Aenderung nicht
    // mitbekommen.
    let inner = 0
    for (const box of [probe.bar.get_start_widget(),
                       probe.bar.get_center_widget(),
                       probe.bar.get_end_widget()]) {
      if (box) {
        inner = Math.max(inner, box.measure(Gtk.Orientation.VERTICAL, -1)[0])
      }
      let child = box ? (box as Gtk.Box).get_first_child() : null
      while (child) {
        if (child.visible) {
          const [x, w] = bounds(child, probe.surface)
          placed.push(`${child.get_name()}@${x}+${w}`)
          // Nur Module, die WIRKLICH eine Beschriftung tragen -
          // moduleBox() in ags-bar.template baut genau das. Die
          // Arbeitsbereiche, die Ablage und der Einklapp-Knopf haben
          // andere Kinder; fuer sie ist die Frage nach der Mitte eines
          // Zeichens gegenstandslos.
          const inside = child.get_first_child()
          if (inside instanceof Gtk.Label && inside.get_text()) {
            const [lx] = bounds(inside, probe.surface)
            const [ox] = inside.get_layout_offsets()
            const [, logical] = inside.get_layout().get_pixel_extents()
            const links = lx + ox + logical.x - x
            const rechts = x + w - (lx + ox + logical.x + logical.width)
            centred.push(`${child.get_name()}=${links}:${rechts}`)
          }
        }
        breadth.push(
          `${child.get_name()}=${child.measure(Gtk.Orientation.VERTICAL, -1)[0]}`)
        child = child.get_next_sibling()
      }
    }

    // Was eingeklappt wurde, steht im Aufklappfenster des Knopfes.
    const overflow = named(probe.bar.get_end_widget(), "bar-overflow")
    const popover = overflow
      ? (overflow as Gtk.MenuButton).get_popover() : null
    const tray = popover ? (popover as Gtk.Popover).get_child() : null
    const folded: string[] = []
    let child = tray ? (tray as Gtk.Box).get_first_child() : null
    while (child) {
      folded.push(child.get_name())
      breadth.push(
        `${child.get_name()}=${child.measure(Gtk.Orientation.VERTICAL, -1)[0]}`)
      child = child.get_next_sibling()
    }

    lines.push(`${prefix} ${probe.width}`)
    lines.push(`  minimum ${minimum}`)
    lines.push(`  hoechste ${tallest}`)
    lines.push(`  innen ${inner}`)
    lines.push(`  dicke ${BAR_THICKNESS}`)
    lines.push(`  knopf ${overflow && overflow.visible ? "sichtbar" : "aus"}`)
    lines.push(`  gestellt ${placed.join(" ")}`)
    lines.push(`  zentriert ${centred.join(" ")}`)
    lines.push(`  eingeklappt ${folded.join(" ")}`)
    lines.push(`  breite ${breadth.join(" ")}`)
  }
}

function finish(): void {
  snapshot("wieder")
  if (TRACE) {
    GLib.file_set_contents(TRACE, new TextEncoder().encode(lines.join("\n") + "\n"))
  }
  print(lines.join("\n"))
  loop.quit()
}

loop.run()
