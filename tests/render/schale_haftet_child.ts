// SPDX-License-Identifier: GPL-3.0-or-later
//
// Eine Schale mit einer absichtlich zu langen Seite - und der Befehl,
// alles zu blaettern, was sich blaettern laesst.
//
// WARUM DIESES KIND UND NICHT DAS KONTROLLZENTRUM SELBST (02.09.2026)
//     Die Frage lautet: bleibt die Seitenleiste stehen, wenn geblaettert
//     wird? Sie ist nur beantwortbar, wenn ueberhaupt geblaettert WIRD -
//     und GEMESSEN am 02.09.2026 blaettert das Kontrollzentrum auf
//     1920x1080 auf keiner seiner sechs Seiten: der Trenner der
//     Netzwerkseite laeuft von Versatz 210 bis 878 durch, also steht
//     rechts keine senkrechte Leiste (mit ihr endet er 24 Punkte
//     frueher, siehe tests/render/test_schale_stil.py). Eine Messung an
//     einem Fenster, in dem nichts blaettert, gaebe fuer JEDEN Aufbau
//     dieselbe Antwort - genau die Sorte gruener Zusicherung, die an
//     diesem Tag achtmal aufgeflogen ist.
//
//     Die Seite hier ist deshalb absichtlich zu lang (ZEILEN Zeilen aus
//     zepRow, dieselbe Zeile wie jede Inhaltsliste des Projekts). Was
//     gemessen wird, ist trotzdem die ECHTE Fabrik: createShellWindow()
//     aus ./utils/overlay, in den erzeugten Baum kopiert und von dort
//     gebuendelt - kein Nachbau.
//
// WAS ES BERICHTET, UND WARUM DER PROZESS UND NICHT hyprctl
//     Wieviele Gtk.ScrolledWindow es im Fenster gibt und welche davon
//     ueberhaupt etwas zu blaettern hat (upper gegen page_size), steht
//     nur im Prozess. Der Compositor kennt die Flaeche des Fensters und
//     kein Widget darin. Die LAGE der Seitenleiste vor und nach dem
//     Blaettern steht ebenfalls hier - und dieselbe Frage stellt der
//     Test daneben noch einmal am BILD, weil ein Widget, das seine
//     Zuteilung behauptet, noch nicht malt, wo es sie hat.
//
// WARUM DIE ADJUSTMENT UND KEIN MAUSRAD
//     Auf dieser Maschine gibt es kein Zeigerereignis zu erzeugen -
//     Gdk.ScrollEvent hat in GTK4 keinen Konstruktor, `hyprctl
//     dispatch` kennt keinen Zeigerdruck und kein Rad, ydotool/wlrctl/
//     dotool sind nicht installiert (alles nachgesehen am 01.09.2026,
//     siehe der Blattkopf von tests/render/test_zeprow_verschachtelung.
//     py). Die vadjustment IST das, was ein Mausrad verstellt; sie hier
//     zu setzen ist derselbe Weg, nur ohne Zeiger.
//
//     GEBLAETTERT WIRD JEDE Flaeche, die etwas zu blaettern hat, und
//     nicht eine ausgesuchte. Das ist der Kern der Messung: die Frage
//     lautet "was auch immer in diesem Fenster blaettert - die
//     Seitenleiste darf nicht mitfahren". Ein Kind, das sich die
//     richtige Flaeche heraussucht, haette die Antwort schon
//     vorweggenommen.
import app from "ags/gtk4/app"
import Astal from "gi://Astal?version=4.0"
import { Gtk } from "ags/gtk4"
import GLib from "gi://GLib"
import style from "./style.scss"
import { createShellWindow } from "./utils/overlay"
import { zepRow } from "./utils/kit"

// Derselbe Name, unter dem der Test die Flaeche in `hyprctl layers`
// sucht - createOverlayWindow() gibt ihn als `namespace` weiter.
const NAMENSRAUM = "haft-sonde"

// So viele Zeilen, dass keine Schirmhoehe dieses Aufbaus reicht. 40 mal
// STYLE_NAV_ROW_HEIGHT waeren schon 1960 Punkte; eine Zeile ohne
// `navEintrag` ist noch hoeher.
const ZEILEN = 40

// Der Fahrplan, in Millisekunden nach dem Start. Grosszuegig, weil die
// Fabrik ihre Lage ueber `hyprctl` holt - ein zu enger Takt maesse den
// Aufbau statt des Zustands.
const T_OEFFNEN = 3000
const T_VOR = 7000      // Bericht "vorher"; der Test knipst danach
const T_BLAETTERN = 10000
const T_NACH = 13000    // Bericht "nachher"; der Test knipst danach
const T_ENDE = 17000

let fenster: Astal.Window | null = null

/** Jedes Widget unter `wurzel`, Wurzel eingeschlossen, in Baumfolge. */
function alleWidgets(wurzel: Gtk.Widget): Gtk.Widget[] {
  const gefunden: Gtk.Widget[] = [wurzel]
  let kind = wurzel.get_first_child()
  while (kind) {
    gefunden.push(...alleWidgets(kind))
    kind = kind.get_next_sibling()
  }
  return gefunden
}

function bildlaufflaechen(): Gtk.ScrolledWindow[] {
  if (!fenster) return []
  return alleWidgets(fenster)
    .filter(w => w instanceof Gtk.ScrolledWindow) as Gtk.ScrolledWindow[]
}

function mitKlasse(name: string): Gtk.Widget | null {
  if (!fenster) return null
  for (const w of alleWidgets(fenster)) {
    if (w.has_css_class(name)) return w
  }
  return null
}

/** x,y,b,h eines Widgets, bezogen auf das Fenster - oder "?". */
function lage(w: Gtk.Widget | null): string {
  if (!w || !fenster) return "?"
  const [ok, rechteck] = w.compute_bounds(fenster)
  if (!ok) return "?"
  return `${Math.round(rechteck.get_x())},${Math.round(rechteck.get_y())}`
    + `,${Math.round(rechteck.get_width())},${Math.round(rechteck.get_height())}`
}

function melde(marke: string): void {
  const flaechen = bildlaufflaechen()
  const teile = flaechen.map((f, i) => {
    const v = f.get_vadjustment()
    return `f${i}=${Math.round(v.get_upper())}/${Math.round(v.get_page_size())}`
      + `@${Math.round(v.get_value())}`
  })
  const sidebar = mitKlasse("zep-sidebar")
  // WELCHE BILDLAUFFLAECHE DIE SEITENLEISTE UEBERHAUPT ENTHAELT - das
  // ist die eigentliche Frage dieser Sonde, und sie ist strukturell und
  // nicht zeitlich zu beantworten: eine Flaeche, in der die
  // Seitenleiste HAENGT, nimmt sie beim Blaettern zwangslaeufig mit.
  // `is_ancestor` ist GTKs eigene Antwort darauf, kein Nachbau ueber
  // get_parent()-Ketten.
  const haelt = flaechen.map(
    f => (sidebar && sidebar.is_ancestor(f)) ? "1" : "0").join("")
  print(`SONDE:${marke}:flaechen=${flaechen.length}`
    + `:${teile.join(":")}`
    + `:sidebar=${lage(sidebar)}`
    + `:haelt-sidebar=${haelt}`
    + `:leiste-sichtbar=${flaechen.map(
        f => f.get_vscrollbar()?.get_mapped() ? "1" : "0").join("")}`)
}

app.start({
  css: style,
  main() {
    // Zwei Gruppen und drei Seiten, damit die Seitenleiste aussieht wie
    // die echte (Gruppenmarke, mehrere Eintraege, genau einer aktiv).
    const seite = (id: string, titel: string, gruppe: string,
                   lang: boolean) => ({
      id, titel, gruppe, symbol: "*",
      bauen: () => {
        const kasten = new Gtk.Box({
          orientation: Gtk.Orientation.VERTICAL, spacing: 0,
          hexpand: true,
        })
        kasten.add_css_class("zep-shell-flaeche")
        const zahl = lang ? ZEILEN : 2
        for (let i = 0; i < zahl; i++) {
          kasten.append(zepRow({ symbol: "#", titel: `${titel} ${i + 1}` }))
        }
        return kasten
      },
    })

    const schale = createShellWindow({
      name: NAMENSRAUM,
      cssClass: "HaftSonde",
      seiten: [
        seite("lang", "Lang", "GRUPPE EINS", true),
        seite("kurz", "Kurz", "GRUPPE EINS", false),
        seite("rand", "Rand", "GRUPPE ZWEI", false),
      ],
      startSeite: "lang",
    })

    GLib.timeout_add(GLib.PRIORITY_DEFAULT, T_OEFFNEN, () => {
      schale.zeigeSeite("lang")
      fenster = schale.window
      return GLib.SOURCE_REMOVE
    })

    GLib.timeout_add(GLib.PRIORITY_DEFAULT, T_VOR, () => {
      melde("vorher")
      return GLib.SOURCE_REMOVE
    })

    GLib.timeout_add(GLib.PRIORITY_DEFAULT, T_BLAETTERN, () => {
      let gerollt = 0
      for (const flaeche of bildlaufflaechen()) {
        const v = flaeche.get_vadjustment()
        const weg = v.get_upper() - v.get_page_size()
        if (weg <= 1) continue
        v.set_value(weg)
        gerollt++
      }
      print(`SONDE:geblaettert:anzahl=${gerollt}`)
      return GLib.SOURCE_REMOVE
    })

    GLib.timeout_add(GLib.PRIORITY_DEFAULT, T_NACH, () => {
      melde("nachher")
      return GLib.SOURCE_REMOVE
    })

    GLib.timeout_add(GLib.PRIORITY_DEFAULT, T_ENDE, () => {
      melde("am-ende")
      return GLib.SOURCE_REMOVE
    })
  },
})
