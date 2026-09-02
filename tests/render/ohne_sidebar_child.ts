// SPDX-License-Identifier: GPL-3.0-or-later
//
// Zwei ECHTE Aufklappfenster OHNE Seitenleiste - und der Befehl, alles zu
// blaettern, was sich blaettern laesst.
//
// WARUM DIESES KIND (02.09.2026)
//     createOverlayWindow() ist die Fabrik fuer ALLE Aufklappfenster.
//     Aufgabe 83 hat der Schale ihre eigene Bildlaufflaeche gegeben und
//     dabei die Fabrik angefasst (der Waechter fuer waagerechten
//     Ueberhang steht seither als eigene Funktion da). Die zehn Fenster
//     OHNE Seitenleiste sollen davon NICHTS merken: bei ihnen liegt
//     weiterhin GENAU EINE Bildlaufflaeche um den ganzen Inhalt, und der
//     blaettert ganz.
//
//     "Ich habe die Fabrik nicht wirklich angefasst" ist dafuer kein
//     Nachweis, sondern eine Behauptung ueber einen Unterschied - und
//     genau die Sorte Behauptung, die an diesem Tag achtmal falsch war.
//     Also gemessen, an zwei echten Fenstern.
//
// WARUM Shortcuts UND Calendar
//     Beide kommen ohne Argumente aus und bauen sich ohne Systemdienst
//     (kein NetworkManager, kein Bluetooth, kein UPower) - sie laufen im
//     verschachtelten Compositor durch. Shortcuts laeuft auf 1920x1080
//     ueber (GEMESSEN: 700 Inhalt in 601 Sichtfenster) und ist damit der
//     Fall, an dem sich BLAETTERN ueberhaupt messen laesst; Calendar
//     passt hinein (540/540) und ist der kurze Fall. Zwei verschiedene
//     Laengen sind Absicht: die Zusicherung ueber den AUFBAU gilt fuer
//     beide, die ueber das Blaettern kann nur dort greifen, wo etwas
//     ueberlaeuft.
//
// WARUM DIE ADJUSTMENT UND KEIN MAUSRAD
//     Dieselbe Lage wie in schale_haftet_child.ts daneben: auf dieser
//     Maschine gibt es kein Zeigerereignis zu erzeugen (Gdk.ScrollEvent
//     hat in GTK4 keinen Konstruktor, `hyprctl dispatch` kennt kein Rad,
//     ydotool/wlrctl/dotool sind nicht installiert). Die vadjustment IST
//     das, was ein Mausrad verstellt.
//
// WARUM KEIN FESTER FAHRPLAN, SONDERN GEWARTET WIRD - GEMESSEN am
// 02.09.2026, und der erste Entwurf dieser Sonde hatte einen
//     Der erste Entwurf knipste nach festen Zeiten (zeigen bei 3 s,
//     melden bei 7 s). In EINEM von drei Laeufen stand die
//     Layer-Shell-Flaeche zu diesem Zeitpunkt noch gar nicht: gemeldet
//     wurden dann 439x287 - die ERSTE Zuteilung, bevor das Fenster seine
//     Groesse hat -, und `hyprctl layers` kannte weder 'shortcuts' noch
//     'calendar'. Dieselbe Flatterhaftigkeit steht schon im Blattkopf
//     von test_schale_stil.py ("bleibt in einem Teil der Laeufe laenger
//     als 20 Sekunden komplett aus").
//
//     Gewartet wird darum auf einen ZUSTAND und nicht auf eine Uhr: das
//     Fenster muss gemappt sein UND seine Zuteilung drei Messungen lang
//     (750 ms) unveraendert. Erst danach wird gemeldet. Nach jeder
//     Meldung stehen 3 Sekunden Ruhe, in denen der Test sein Bild
//     schiessen kann - er wartet dafuer auf die Zeile im Protokoll,
//     nicht auf eine Zeitmarke.
import app from "ags/gtk4/app"
import Astal from "gi://Astal?version=4.0"
import { Gtk } from "ags/gtk4"
import GLib from "gi://GLib"
import style from "./style.scss"
import Shortcuts from "./widget/Shortcuts"
import Calendar from "./widget/Calendar"

/** Wie lange der Test nach jeder Meldung zum Knipsen hat. */
const RUHE = 3000
/** Obergrenze fuers Warten auf die Flaeche - grosszuegig, siehe oben. */
const WARTE_SCHRITTE = 200
const WARTE_TAKT = 250

function schlafe(ms: number): Promise<void> {
  return new Promise(loesen => {
    GLib.timeout_add(GLib.PRIORITY_DEFAULT, ms, () => {
      loesen()
      return GLib.SOURCE_REMOVE
    })
  })
}

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

function flaechen(fenster: Astal.Window): Gtk.ScrolledWindow[] {
  return alleWidgets(fenster)
    .filter(w => w instanceof Gtk.ScrolledWindow) as Gtk.ScrolledWindow[]
}

/** x,y,b,h eines Widgets, bezogen auf das Fenster - oder "?". */
function lage(w: Gtk.Widget | null, fenster: Astal.Window): string {
  if (!w) return "?"
  const [ok, r] = w.compute_bounds(fenster)
  if (!ok) return "?"
  return `${Math.round(r.get_x())},${Math.round(r.get_y())}`
    + `,${Math.round(r.get_width())},${Math.round(r.get_height())}`
}

// WIEVIELE BILDLAUF-HUELLEN UEBER DEM INHALT LIEGEN, UND WO DER INHALT
// WIRKLICH ANFAENGT
//
// ZWEI FEHLGRIFFE STEHEN HIER, WEIL BEIDE GEMESSEN WURDEN UND BEIDE
// GRUEN GEBLIEBEN WAEREN
//
//     (1) `f0.get_child()` gibt den Gtk.Viewport, den eine
//     Gtk.ScrolledWindow selbst um ihr Kind legt. Der Viewport bleibt
//     beim Blaettern STEHEN - er IST das Sichtfenster -, und nur sein
//     Kind wandert. GEMESSEN, Shortcuts vor und nach dem Blaettern um
//     99 Punkte: `1,78,854,601` und noch einmal `1,78,854,601`. Eine
//     Zusicherung auf diese Zahl haette "der Inhalt hat sich nicht
//     bewegt" gemeldet, obwohl im Bild 13 821 Bildpunkte gewechselt
//     hatten.
//
//     (2) Der zweite Entwurf stieg darum eine Ebene tiefer und zaehlte,
//     wieviele Flaechen VORFAHREN dieses Kindes sind. GEMESSEN an der
//     Gegenprobe, die eine ZWEITE Huelle um den Inhalt legt: gemeldet
//     wurde `flaechen=3` und trotzdem `1` - denn das Kind des ersten
//     Sichtfensters war jetzt die zweite Flaeche selbst, und die hat
//     genau einen Vorfahr dieser Art. Die Zusicherung, die die
//     Doppelhuelle finden sollte, blieb an ihr GRUEN.
//
//     Gezaehlt wird deshalb die KETTE: von der Flaeche der Fabrik aus
//     abwaerts, so lange das naechste Glied eine Flaeche oder ein
//     Sichtfenster ist. Die Zahl der Flaechen darin ist die Zahl der
//     Huellen (unveraendert: 1; Doppelhuelle: 2), und wo die Kette
//     endet, faengt der Inhalt an - das ist die Ebene, die beim
//     Blaettern wandert.
function huelleVon(f: Gtk.ScrolledWindow | undefined): {
  huellen: number, inhalt: Gtk.Widget | null,
} {
  let huellen = 0
  let glied: Gtk.Widget | null = f ?? null
  while (glied) {
    if (glied instanceof Gtk.ScrolledWindow) {
      huellen++
      glied = glied.get_child()
    } else if (glied instanceof Gtk.Viewport) {
      glied = glied.get_child()
    } else {
      break
    }
  }
  return { huellen, inhalt: glied }
}

function melde(marke: string, fenster: Astal.Window): void {
  const gefunden = flaechen(fenster)
  const teile = gefunden.map((f, i) => {
    const v = f.get_vadjustment()
    return `f${i}=${Math.round(v.get_upper())}/${Math.round(v.get_page_size())}`
      + `@${Math.round(v.get_value())}`
  })
  // GEZAEHLT WIRD NICHT DER BESTAND DES FENSTERS - Shortcuts bringt eine
  // EIGENE Gtk.ScrolledWindow mit (`#shortcuts-scroll`,
  // ags-shortcuts.template). Die liegt INNEN, im Inhalt, und gehoert dem
  // Widget und nicht der Fabrik. `huellen` zaehlt darum die Kette ueber
  // dem Inhalt und nicht, was es im Fenster sonst noch gibt.
  const { huellen, inhalt } = huelleVon(gefunden[0])
  print(`SONDE:${marke}:flaechen=${gefunden.length}`
    + `:${teile.join(":")}`
    + `:sicht=${lage(gefunden[0] ? gefunden[0].get_child() : null, fenster)}`
    + `:inhalt=${lage(inhalt, fenster)}`
    + `:huellen=${huellen}`
    + `:leiste-sichtbar=${gefunden.map(
        f => f.get_vscrollbar()?.get_mapped() ? "1" : "0").join("")}`)
}

/** Wartet, bis das Fenster gemappt UND seine Zuteilung ruhig ist. */
async function warteAufFlaeche(fenster: Astal.Window): Promise<boolean> {
  let letzte = ""
  let gleich = 0
  for (let i = 0; i < WARTE_SCHRITTE; i++) {
    const f = flaechen(fenster)[0]
    const jetzt = f
      ? `${Math.round(f.get_vadjustment().get_page_size())}`
        + `x${lage(f, fenster)}`
      : "?"
    if (fenster.get_mapped() && jetzt !== "?" && jetzt === letzte) {
      if (++gleich >= 3) return true
    } else {
      gleich = 0
    }
    letzte = jetzt
    await schlafe(WARTE_TAKT)
  }
  return false
}

function blaettere(marke: string, fenster: Astal.Window): void {
  let gerollt = 0
  for (const f of flaechen(fenster)) {
    const v = f.get_vadjustment()
    const weg = v.get_upper() - v.get_page_size()
    if (weg <= 1) continue
    v.set_value(weg)
    gerollt++
  }
  print(`SONDE:${marke}-geblaettert:anzahl=${gerollt}`)
}

async function pruefe(marke: string, teil: {
  window: Astal.Window, show: () => unknown, hide: () => void,
}): Promise<void> {
  teil.show()
  const steht = await warteAufFlaeche(teil.window)
  print(`SONDE:${marke}-steht:ok=${steht ? 1 : 0}`)
  if (!steht) return

  melde(`${marke}-vorher`, teil.window)
  await schlafe(RUHE)
  blaettere(marke, teil.window)
  await schlafe(1000)
  melde(`${marke}-nachher`, teil.window)
  await schlafe(RUHE)
  teil.hide()
  await schlafe(500)
}

app.start({
  css: style,
  main() {
    const fenster = { a: Shortcuts(), b: Calendar() }
    void (async () => {
      await schlafe(2000)
      await pruefe("a", fenster.a)
      await pruefe("b", fenster.b)
      print("SONDE:ende:ok=1")
    })()
  },
})
