// SPDX-License-Identifier: GPL-3.0-or-later
//
// Was das VPN-Fenster aus dem vierten Wort macht.
//
// WAS GEMESSEN WIRD
//     Die Seite fragt beim Sichtbarwerden `vpn.py --status`. Die
//     Attrappe dahinter druckt EIN Wort, das der Test vorgibt. Dieses
//     Kind liest danach ab, was das Fenster daraus gemacht hat:
//
//       * die Beschriftung des Zustands (.vpn-status-label)
//       * die CSS-Klassen des Zustandssymbols (.vpn-status-icon) - an
//         ihnen haengt die FARBE, und die Farbe ist die halbe Aussage
//       * das Zeichen selbst, damit ein vertauschtes Symbol auffaellt
//
// WARUM DIE KLASSEN UND NICHT DIE FARBE
//     Ein Kind ohne Stylesheet sieht keine Farben - dieselbe Falle, die
//     am 01.09.2026 in tests/render/test_zeprow_verschachtelung.py fast
//     einen Befund ueber GTKs Vorgaben erzeugt haette. Die Klasse ist
//     das, was diese Vorlage ZUSICHERT; welche Farbe daraus wird, steht
//     in ags-style.template und wird dort geprueft.
//
// WARUM NICHT AUF DIE ZUTEILUNG GEWARTET WIRD
//     Hier wird Text gelesen, keine Geometrie. Ein Bildrahmen ist dafuer
//     nicht noetig - anders als bei den Messungen, die Punkte zaehlen.

import { Gtk } from "ags/gtk4"
import GLib from "gi://GLib"
import { vpnSeite } from "./widget/VpnManager"

const TRACE = GLib.getenv("ZEPOS_TRACE") ?? ""
const marks: string[] = []

function mark(name: string, value: string): void {
  marks.push(`${name}:${value}`)
}

Gtk.init()

const window = new Gtk.Window({ title: "ZEPOS-VPN-UNBEKANNT" })
const seite = vpnSeite.bauen(window as any, () => { }, () => true)
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

const loop = GLib.MainLoop.new(null, false)

// Grosszuegig: die Seite startet fuer ihre Auskunft einen Unterprozess.
const T_LESEN = 2500
const T_ENDE = 3000

GLib.timeout_add(GLib.PRIORITY_DEFAULT, T_LESEN, () => {
  const symbol = suche(seite, (w) => w.has_css_class("vpn-status-icon"))
  const beschriftung = suche(seite, (w) => w.has_css_class("vpn-status-label"))

  mark("symbol-da", symbol ? "ja" : "nein")
  mark("beschriftung-da", beschriftung ? "ja" : "nein")
  if (symbol) {
    mark("symbol-klassen", symbol.get_css_classes().join("."))
    mark("symbol-zeichen", (symbol as Gtk.Label).get_text())
  }
  if (beschriftung) {
    // Zeilenumbrueche werden ersetzt: die Spur ist zeilenweise, und ein
    // echter Umbruch im Wert zerschnitte die Marke.
    mark("beschriftung", (beschriftung as Gtk.Label).get_text()
      .split("\n").join(" / "))
  }

  // ---- DIE SCHALTER DER LISTE --------------------------------------
  //
  //     Bei `unknown` duerfen sie keine Eingabe annehmen. "Aus" waere
  //     dieselbe falsche Behauptung wie ein "nicht verbunden" im Text,
  //     nur unauffaelliger. Ein Gtk.Switch hat keine dritte STELLUNG,
  //     aber einen dritten ZUSTAND: nicht bedienbar.
  //
  //     Gemessen wird `get_sensitive()` JE Schalter und nicht nur am
  //     ersten: eine Liste, in der einer sperrt und der andere nicht,
  //     waere schlimmer als gar keine Sperre.
  const liste = suche(seite, (w) => w.has_css_class("vpn-connection-list"))
  const schalter: string[] = []
  const sammle = (w: Gtk.Widget | null): void => {
    if (!w) return
    if (w instanceof Gtk.Switch) schalter.push(String(w.get_sensitive()))
    let kind = w.get_first_child()
    while (kind) {
      sammle(kind)
      kind = kind.get_next_sibling()
    }
  }
  sammle(liste)
  mark("schalter-anzahl", String(schalter.length))
  mark("schalter-bedienbar", schalter.join(","))
  return false
})

GLib.timeout_add(GLib.PRIORITY_DEFAULT, T_ENDE, () => {
  if (TRACE) {
    GLib.file_set_contents(
      TRACE, new TextEncoder().encode(marks.join("\n") + "\n"))
  }
  print(marks.join("\n"))
  loop.quit()
  return false
})

loop.run()
