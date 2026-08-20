// SPDX-License-Identifier: GPL-3.0-or-later
//
// Das Rechtsklick-Menue des Fusses - aufgeklappt, aufgeschrieben,
// angeklickt.
//
// WARUM EIN FUENFTES KIND
//     dock_headless_child.tsx misst einen Fuss OHNE Compositor,
//     dock_minimized_child.tsx einen mit abgelegten Fenstern. Beide
//     fragen, WAS auf dem Fuss steht. Hier ist die Frage, was ein
//     Rechtsklick DARAUF anbietet und was ein Menuepunkt AUSLOEST - zwei
//     Dinge, die keines der beiden Kinder beruehrt.
//
//     Das Gegenstueck dazu ist tests/render/dock_menue_child.tsx: dort
//     an einer echten Layer-Flaeche, mit Bild und Compositor, fuer die
//     Frage "erscheint es ueberhaupt und geht es wieder zu". Hier
//     kopflos, dafuer mit einem Compositor, der jeden Befehl mitschreibt
//     und einem Einstellungsbefehl, der jedes Dokument aufhebt. Die
//     Trennung ist die ueberall in diesem Baum: dort, was auf dem Schirm
//     wird, hier, was das Programm tut.
//
// WARUM DER KLICK HIER STATTFINDET UND NICHT IM TEST
//     Wortgleich zu dock_minimized_child.tsx: ein Gtk.Button hat sein
//     "clicked" im Prozess, der ihn gebaut hat. Der Rechtsklick geht
//     ueber die Gtk.GestureClick, die die Vorlage an den Knopf haengt -
//     gefunden ueber observe_controllers(), also an der Stelle, an der
//     GTK die Steuerungen eines Widgets ohnehin fuehrt.

import { Gtk, Gdk } from "ags/gtk4"
import GLib from "gi://GLib"
import { DockContent } from "./widget/Dock"

const TRACE = GLib.getenv("ZEPOS_TRACE") ?? ""
const marks: string[] = []

function mark(name: string, value: string): void {
  marks.push(`${name}:${value}`)
}

Gtk.init()

// Dasselbe Stylesheet wie in den Nachbarkindern, aus demselben Grund.
const CSS = GLib.getenv("ZEPOS_CSS") ?? ""
const display = Gdk.Display.get_default()
if (CSS && display) {
  const provider = new Gtk.CssProvider()
  provider.load_from_path(CSS)
  Gtk.StyleContext.add_provider_for_display(
    display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
}

const window = new Gtk.Window({ title: "zepos-dock-menue" })
const dock = DockContent()
window.add_css_class("dock-window")
window.set_child(dock)
window.set_default_size(1920, 96)
window.present()

/** Die Kinder der Knopfreihe, in ihrer Reihenfolge. */
function reihe(): Gtk.Widget[] {
  const kinder: Gtk.Widget[] = []
  let kind: Gtk.Widget | null = dock.get_first_child()
  while (kind) {
    kinder.push(kind)
    kind = kind.get_next_sibling()
  }
  return kinder
}

/** Die Aufschriften der Reihe, so wie die Nachbarkinder sie schreiben. */
function aufschriften(): string {
  return reihe().map(kind => {
    const klassen = kind.get_css_classes().join(" ")
    const name = kind.get_tooltip_text() ?? kind.get_css_name()
    return `${name}[${klassen}]${kind.visible ? "" : "(aus)"}`
  }).join(",")
}

/** Der Knopf mit dieser Aufschrift, oder null. */
function knopf(aufschrift: string): Gtk.Widget | null {
  for (const kind of reihe()) {
    if (kind.get_tooltip_text() === aufschrift) return kind
  }
  return null
}

/** Das offene Menue an diesem Knopf, oder null.
 *
 * Ein Gtk.Popover mit set_parent() ist ein KIND seines Ankers und nicht
 * dessen `child` - gesucht wird deshalb unter den Geschwistern des
 * Knopfinhalts. Es gibt ihn nur, solange das Menue offen ist: die
 * Vorlage baut ihn beim Rechtsklick und nimmt ihn beim Zugehen wieder
 * ab.
 */
function menueVon(k: Gtk.Widget): Gtk.Popover | null {
  let kind: Gtk.Widget | null = k.get_first_child()
  while (kind) {
    if (kind instanceof Gtk.Popover) return kind
    kind = kind.get_next_sibling()
  }
  return null
}

/** Die erste Beschriftung unterhalb dieses Widgets, ohne das Symbol. */
function beschriftung(widget: Gtk.Widget): string {
  if (widget instanceof Gtk.Label) return widget.get_label()
  let kind: Gtk.Widget | null = widget.get_first_child()
  while (kind) {
    if (kind.has_css_class("zep-row-icon")) {
      kind = kind.get_next_sibling()
      continue
    }
    const treffer = beschriftung(kind)
    if (treffer) return treffer
    kind = kind.get_next_sibling()
  }
  return ""
}

/** Das Symbolzeichen einer Menuezeile - fuer die Frage, ob eines dasteht. */
function symbolVon(zeile: Gtk.Widget): string {
  if (zeile.has_css_class("zep-row-icon") && zeile instanceof Gtk.Label) {
    return zeile.get_label()
  }
  let kind: Gtk.Widget | null = zeile.get_first_child()
  while (kind) {
    const treffer = symbolVon(kind)
    if (treffer) return treffer
    kind = kind.get_next_sibling()
  }
  return ""
}

/** Den Rechtsklick an diesem Knopf ausloesen. */
function rechtsklick(k: Gtk.Widget): boolean {
  const steuerungen = k.observe_controllers()
  for (let index = 0; index < steuerungen.get_n_items(); index++) {
    const steuerung = steuerungen.get_item(index)
    if (!(steuerung instanceof Gtk.GestureClick)) continue
    if (steuerung.get_button() !== 3) continue
    steuerung.emit("pressed", 1, 8.0, 8.0)
    return true
  }
  return false
}

/** Die Zeilen des offenen Menues, als "Symbol Text". */
function zeilen(k: Gtk.Widget): string[] {
  const offen = menueVon(k)
  const liste = offen ? offen.get_child() : null
  if (!liste) return []
  const gefunden: string[] = []
  let zeile: Gtk.Widget | null = liste.get_first_child()
  while (zeile) {
    const text = beschriftung(zeile)
    if (text) gefunden.push(`${symbolVon(zeile)} ${text}`)
    zeile = zeile.get_next_sibling()
  }
  return gefunden
}

/** Die Zeile mit diesem Text anklicken. */
function waehle(k: Gtk.Widget, text: string): boolean {
  const offen = menueVon(k)
  const liste = offen ? offen.get_child() : null
  if (!liste) return false
  let zeile: Gtk.Widget | null = liste.get_first_child()
  while (zeile) {
    if (beschriftung(zeile) === text && zeile instanceof Gtk.Button) {
      zeile.emit("clicked")
      return true
    }
    zeile = zeile.get_next_sibling()
  }
  return false
}

// Was auf dem Fuss steht, bevor irgendetwas geklickt wird.
mark("kinder", aufschriften())

// DIE MENUES, DIE DIESER LAUF AUFKLAPPEN SOLL - durch "|" getrennt, weil
// eine Aufschrift wie "Dateien (1)" ein Leerzeichen enthaelt.
for (const gesucht of (GLib.getenv("ZEPOS_MENUES") ?? "").split("|")) {
  if (!gesucht) continue
  const k = knopf(gesucht)
  if (!k) {
    mark(`menue-ohne-knopf`, gesucht)
    continue
  }
  if (!rechtsklick(k)) {
    mark(`menue-ohne-geste`, gesucht)
    continue
  }
  mark(`menue-${gesucht}`, zeilen(k).join(";"))
  // ZUKLAPPEN UND ABNEHMEN. Das Abnehmen macht die Vorlage im Leerlauf,
  // und dieser Zweig laeuft ohne Ereignisschleife - ein Popover, das am
  // Knopf haengenbliebe, meldete beim Beenden "Finalizing GtkButton ...
  // but it still has children left".
  const offen = menueVon(k)
  if (offen) {
    offen.popdown()
    if (offen.get_parent()) offen.unparent()
  }
}

// EINE AUSWAHL, als "Knopf>Zeile". Danach wird gewartet: was ein
// Menuepunkt ausloest, geht ueber execAsync an einen anderen Prozess,
// und dessen Antwort kommt aus der Ereignisschleife zurueck.
const auftrag = GLib.getenv("ZEPOS_WAEHLE") ?? ""
if (!auftrag) {
  schreibe()
} else {
  const [ziel, punkt] = auftrag.split(">")
  const k = knopf(ziel)
  if (!k) {
    mark("wahl-ohne-knopf", ziel)
    schreibe()
  } else if (!rechtsklick(k)) {
    mark("wahl-ohne-geste", ziel)
    schreibe()
  } else {
    mark("gewaehlt", waehle(k, punkt) ? punkt : `nicht-gefunden:${punkt}`)
    const offen = menueVon(k)
    if (offen) offen.popdown()
    // Hier NICHT von Hand abnehmen: die Ereignisschleife laeuft, also
    // tut es die Vorlage selbst - und dass sie es tut, ist ein Teil
    // dessen, was hier gemessen wird.
    // Die Frist, in der die Bruecke antworten und der Fuss seine Reihe
    // neu bauen kann. Grosszuegig: gemessen wird das Ergebnis, nicht die
    // Dauer, und ein zu kurzes Warten maesse "nichts passiert".
    GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2500, () => {
      mark("kinder-danach", aufschriften())
      schreibe()
      loop.quit()
      return GLib.SOURCE_REMOVE
    })
  }
}

function schreibe(): void {
  if (TRACE) {
    GLib.file_set_contents(TRACE,
                           new TextEncoder().encode(marks.join("\n") + "\n"))
  }
  print(marks.join("\n"))
}

// Die Ereignisschleife laeuft NUR, wenn auf eine Antwort gewartet wird.
// Ohne Auftrag ist der Lauf mit der letzten Zeile fertig, und eine
// Schleife, die niemand beendet, waere ein haengender Test.
const loop = GLib.MainLoop.new(null, false)
if (auftrag) loop.run()
