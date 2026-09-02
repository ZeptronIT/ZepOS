// SPDX-License-Identifier: GPL-3.0-or-later
//
// Der Schalter IM Knopf - an einem wirklich abgebildeten Fenster.
//
// WARUM DIESES KIND UNTER EINEM COMPOSITOR LAEUFT UND NICHT UNTER
// gtk4-broadwayd
//     Der erste Anlauf am 01.09.2026 stand unter broadwayd, und er hat
//     gemessen. Nur nichts Brauchbares:
//
//         zuteilung:700x729                 (die Seite als Ganzes)
//         lage-liste:   700x110  bounds=0,39,700,110
//         lage-schalter:  0x0    bounds=-1,38,2,2
//         lage-titel:     0x0    bounds=0,39,0,0
//
//     Die Liste hatte ihre Zuteilung, ihre KINDER hatten keine. Der
//     Grund: die Seite zeichnet ihre Liste neu, sobald die Antwort auf
//     `vpn.py --status` da ist, und die zweite Zuteilungsrunde braucht
//     einen Bildrahmen. Ein broadwayd, an dem kein Betrachter haengt,
//     liefert keinen. `pick()` traf damit die Titelleiste des Fensters -
//     fuer beide Punkte dieselbe Antwort, weil beide Punkte derselbe
//     Punkt waren.
//
//     Unter einem echten Compositor fliessen die Rahmen, und dort
//     laesst sich ausserdem eine TASTE druecken (wtype) statt eine
//     Funktion zu rufen, die dieselbe vfunc anspringt.
//
// WAS GEMESSEN WIRD
//     1. DER AUFBAU: steckt der Schalter wirklich in der klickbaren
//        Huelle von zepRow?
//     2. WOHIN EIN ZEIGERDRUCK GEHT - `Gtk.Widget.pick()`. Das ist kein
//        Ersatz: pick() IST die Funktion, mit der GTK4 entscheidet,
//        welches Widget ein Zeigerereignis bekommt.
//     3. DIE TASTATUR, mit echten Tasten. Das Kind schreibt JEDES
//        `clicked` und JEDES `notify::active` mit Zeitstempel und dem
//        Widget mit, das gerade den Fokus hatte. Der Test drueckt
//        dazwischen die Leertaste. Damit steht am Ende da, was eine
//        Taste WIRKLICH ausloest - und an welchem Widget.
//
// DREI ZIELE SEIT DEM 02.09.2026, VORHER ZWEI
//     Die Zeile traegt seither DREI Bedienelemente: die klickbare
//     Huelle, das Zahnrad (`.vpn-row-settings`) und den Schalter. Der
//     Nutzer hat das Zahnrad bestellt ("ich will neben dem toggle auch
//     ein icon fuer einstellung haben das zahnrad"), und damit stellt
//     sich dieselbe Frage ein drittes Mal: erreicht der Tabulator es,
//     und tut die Leertaste dort DAS SEINE - statt die Zeile
//     aufzublaettern oder den Tunnel zu schalten.
//
//     Die gemessene Fokuskette je Zeile (02.09.2026):
//
//         GtkButton[zep-row-click.zep-row-click-getrennt]
//         > GtkButton[zep-btn.zep-btn-still.vpn-row-settings.text-button]
//         > GtkSwitch[zep-toggle]
//
// WAS SICH NICHT MESSEN LIESS
//     Ob die Geste des Schalters die Sequenz beansprucht und den Knopf
//     darum herum stillstellt. Dafuer braeuchte es ein echtes
//     ZEIGERereignis. Gdk.ButtonEvent hat in GTK4 keinen Konstruktor
//     (nachgesehen in /usr/share/gir-1.0/Gdk-4.0.gir), Hyprland hat
//     keinen Klick-Dispatcher (`hyprctl dispatch`, durchgesehen), und
//     ydotool/wlrctl/dotool gibt es auf dieser Maschine nicht. wtype
//     kann nur Tastatur.

import { Gtk, Gdk } from "ags/gtk4"
import GLib from "gi://GLib"
import { vpnSeite } from "./widget/VpnManager"
import { zepRow, zepToggle } from "./utils/kit"

const TRACE = GLib.getenv("ZEPOS_TRACE") ?? ""
const marks: string[] = []

function mark(name: string, value: string): void {
  marks.push(`${name}:${value}`)
}

Gtk.init()

// DAS ECHTE STYLESHEET, UND OHNE ES MISST DER BILDVERGLEICH GTK
//
//     Dieses Kind ruft `Gtk.init()` und nicht AGS' `App` - es bekommt
//     also kein Stylesheet geschenkt. Bis zum 01.09.2026 lud es auch
//     keines, und der erste Bildvergleich hat darum brav einen
//     Fokusrahmen gemessen, der GTK gehoerte und nicht diesem Projekt
//     (2px, (128,165,211) - Adwaitas Blau; $accent ist #33C9EE).
//
//     Der Test uebersetzt die Vorlage mit `sass` und reicht den Pfad
//     hier herein. Ohne ihn laeuft das Kind weiter - die Marken ueber
//     den Baum brauchen keinen Stil -, aber der Bildvergleich im Test
//     wuerde dann wieder ueber GTKs Vorgaben reden.
const CSS = GLib.getenv("ZEPOS_CSS") ?? ""
if (CSS) {
  const anbieter = new Gtk.CssProvider()
  anbieter.load_from_path(CSS)
  Gtk.StyleContext.add_provider_for_display(
    Gdk.Display.get_default()!, anbieter,
    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
}
mark("stylesheet", CSS ? "geladen" : "fehlt")

const window = new Gtk.Window({ title: "ZEPOS-ZEPROW-PROBE" })
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

/** Wie ein Widget in der Spur heisst: Typ und CSS-Klassen. */
function beschreibe(w: Gtk.Widget | null): string {
  if (!w) return "nichts"
  const typ = (w as any).constructor?.$gtype?.name ?? "?"
  const klassen = w.get_css_classes().join(".")
  return klassen ? `${typ}[${klassen}]` : typ
}

/** Die Kette von `w` bis zum Fenster, von innen nach aussen. */
function kette(w: Gtk.Widget | null): string {
  const teile: string[] = []
  let lauf: Gtk.Widget | null = w
  while (lauf && teile.length < 12) {
    teile.push(beschreibe(lauf))
    if (lauf === (window as unknown as Gtk.Widget)) break
    lauf = lauf.get_parent()
  }
  return teile.join(" < ")
}

/** Der Mittelpunkt eines Widgets in den Koordinaten des Fensters. */
function mitte(w: Gtk.Widget | null): [number, number] | null {
  if (!w) return null
  const [ok, r] = w.compute_bounds(window as unknown as Gtk.Widget)
  if (!ok || r.get_width() <= 0 || r.get_height() <= 0) return null
  return [r.get_x() + r.get_width() / 2, r.get_y() + r.get_height() / 2]
}

// Das Fahrtenbuch: jedes Signal mit Zeitstempel und dem Widget, das
// gerade den Fokus hielt. Es ist der ganze Beweis fuer den Tastenteil -
// eine blosse Zaehlung sagte nicht, WOBEI gezaehlt wurde.
const start = GLib.get_monotonic_time()
const buch: string[] = []
function eintragen(was: string): void {
  const ms = Math.round((GLib.get_monotonic_time() - start) / 1000)
  buch.push(`${ms}ms ${was} fokus=${beschreibe(window.get_focus())}`)
}

const loop = GLib.MainLoop.new(null, false)

// Der Fahrplan, in Millisekunden. Grosszuegig: die Seite fragt beim
// Sichtbarwerden einen Unterprozess, und die zweite Zuteilungsrunde
// braucht einen Bildrahmen.
//
// UND ALLES MUSS VOR 5000ms DURCH SEIN - GEMESSEN am 02.09.2026
//
//     `UPDATE_INTERVAL = 5000` in ags-vpn.template: fuenf Sekunden nach
//     dem Sichtbarwerden laeuft `updateStatusDisplay()` das erste Mal
//     und ruft `zeichneListe()`. Die Liste wird abgeraeumt und neu
//     gebaut - die Widgets, an die unten die Mitschrift gehaengt wird,
//     sind danach weg, und der Tastaturfokus mit ihnen.
//
//     Ein Anlauf mit T_FOKUS=5000 und der Leertaste bei 5,4s hat das
//     vorgefuehrt: im Fahrtenbuch stand nur noch
//
//         5000ms --fokus-gelesen-- fokus=GtkSwitch[zep-toggle]
//
//     Die Taste loeste NICHTS aus, dreimal reproduziert. Der Fahrplan
//     hat also von T_MESSEN bis 5000ms Platz und keine Millisekunde
//     mehr. Die drei Tabulatoren (bis zum Schalter) brauchen zusammen
//     etwa 0,3s - es passt, aber nicht mit beliebiger Luft.
const T_MESSEN = 2500      // Aufbau, Zuteilung, pick(), Fokuskette
const T_FOKUS = 4000       // der Test hat bis hier getabbt; nur ABLESEN
const T_LESEN = 4800       // der Test drueckt dazwischen die Taste
const T_ENDE = 4900        // noch vor dem Neuzeichnen bei 5000ms

// EIN ZIEL JE LAUF, UND DAS IST EINE MESSUNG UND KEINE BEQUEMLICHKEIT
//
//     Der erste Anlauf am 01.09.2026 wollte beide Ziele in EINEM Lauf
//     messen: erst der Fokus auf den Schalter, Taste, dann der Fokus auf
//     die Zeile, Taste. Der zweite Teil hat nichts gemessen, und der
//     Grund ist genau der Befund:
//
//         3500ms --fokus-auf-schalter-- fokus=GtkSwitch[zep-toggle]
//         4513ms KNOPF-clicked          fokus=GtkSwitch[zep-toggle]
//         6501ms --fokus-auf-zeile--    fokus=nichts
//
//     Die Taste auf dem Schalter hat die ZEILE ausgeloest, die Zeile hat
//     auf die Einzelheiten umgeblattert, und die Liste war weg - es gab
//     danach keinen Knopf mehr, auf den ein Fokus haette gehen koennen.
//
//     Zwei Laeufe also, jeder von einer frischen Liste aus.
const ZIEL = GLib.getenv("ZEPOS_ZIEL") ?? "schalter"

let schalter: Gtk.Switch | null = null
let knopf: Gtk.Button | null = null
// NACHGETRAGEN am 02.09.2026: das Zahnrad je Zeile. Es ist das dritte
// Bedienelement in derselben Zeile, und damit dieselbe Frage noch
// einmal - welches Widget bekommt die Taste, und was loest sie aus.
let zahnrad: Gtk.Button | null = null

GLib.timeout_add(GLib.PRIORITY_DEFAULT, T_MESSEN, () => {
  const liste = suche(seite, (w) => w.has_css_class("vpn-connection-list"))
  const zeile = suche(liste, (w) => w.has_css_class("zep-row"))
  schalter = suche(zeile, (w) => w instanceof Gtk.Switch) as Gtk.Switch | null
  // DIE HUELLE WIRD VON DER LISTE AUS GESUCHT, NICHT VON DER ZEILE -
  // und das ist eine MESSUNG und keine Umstaendlichkeit.
  //
  //     Ueber die KLASSE und nicht ueber `get_ancestor(Gtk.Button)`:
  //     seit dem Umbau vom 01.09.2026 hat der Schalter keinen Button
  //     mehr ueber sich, und eine Suche nach oben faende dann nichts.
  //
  //     Von der LISTE aus und nicht von der ZEILE, weil die Huelle in
  //     den beiden Betriebsarten auf verschiedenen Seiten der Zeile
  //     liegt:
  //
  //         Vorgabe:  Button[.zep-row-click] > Box[.zep-row]   (darueber)
  //         getrennt: Box[.zep-row] > Button[.zep-row-click]   (darunter)
  //
  //     GEMESSEN am 01.09.2026: mit `suche(zeile, ...)` und ohne
  //     `endeBedienbar` stand in der Spur `knopf:nichts`. Dann wird
  //     unten kein `clicked` verbunden, und das Fahrtenbuch KANN kein
  //     KNOPF-clicked mehr enthalten - die Zusicherung "die Leertaste
  //     auf dem Schalter loest die Zeile NICHT aus" waere erfuellt
  //     gewesen, weil niemand hinsah. Eine Gegenprobe, die den Mangel
  //     nicht mehr sehen kann, den sie ausschliessen soll, ist keine.
  //
  //     Die Liste enthaelt die Huelle in BEIDEN Betriebsarten.
  knopf = suche(liste, (w) => w.has_css_class("zep-row-click")) as Gtk.Button | null
  const titel = suche(zeile, (w) => w.has_css_class("zep-row-title"))
  // Das Zahnrad derselben Zeile. Ueber die Klasse, die ags-vpn.template
  // vergibt - `instanceof Gtk.Button` traefe auch die Huelle.
  zahnrad = suche(zeile, (w) => w.has_css_class("vpn-row-settings")) as Gtk.Button | null

  /** Liegt `w` unter einem Widget mit der Klasse `.zep-row-click`? */
  const unterDerHuelle = (w: Gtk.Widget | null): string => {
    let lauf: Gtk.Widget | null = w
    while (lauf) {
      if (lauf.has_css_class("zep-row-click")) return "ja"
      lauf = lauf.get_parent()
    }
    return "nein"
  }

  mark("schalter", beschreibe(schalter))
  mark("knopf", beschreibe(knopf))
  mark("zahnrad", beschreibe(zahnrad))
  mark("kette-schalter", kette(schalter))
  mark("kette-zahnrad", kette(zahnrad))
  mark("schalter-im-knopf", unterDerHuelle(schalter))
  // Das Zahnrad haengt in derselben Box wie der Schalter, und die haengt
  // NEBEN der Huelle - `endeBedienbar` in ags-kit.template. Steckte es
  // darin, traefe es genau der Mangel vom 01.09.2026: Tabulator kommt
  // hin, Leertaste loest die ZEILE aus.
  mark("zahnrad-im-knopf", unterDerHuelle(zahnrad))
  mark("titel-im-knopf", unterDerHuelle(titel))
  mark("knopf-klasse", knopf && knopf.has_css_class("zep-row-click")
    ? "zep-row-click" : "andere")

  // ---- DIE VORGABE, UNANGETASTET -----------------------------------
  //
  //     Die neue Betriebsart darf nicht versehentlich zur Vorgabe
  //     werden. Gezaehlt wird das in tests/src/; hier wird es GEBAUT:
  //     eine Zeile mit `aktion` UND `ende`, aber OHNE `endeBedienbar`,
  //     muss weiterhin den alten Baum ergeben - Huelle aussen, alles
  //     darin.
  const vorgabe = zepRow({
    symbol: "V", titel: "Vorgabe", aktion: () => { },
    ende: zepToggle(false, () => { }),
  })
  const vorgabeSchalter = suche(vorgabe, (w) => w instanceof Gtk.Switch)
  mark("vorgabe-wurzel", beschreibe(vorgabe))
  mark("vorgabe-schalter-im-knopf", unterDerHuelle(vorgabeSchalter))

  // Und eine Zeile ohne `ende` - die Form, die Bluetooth, Netz, die
  // Seitenleiste, das Kontrollzentrum und Home benutzen.
  const nurAktion = zepRow({ symbol: "N", titel: "Nur Aktion",
                             aktion: () => { } })
  mark("nur-aktion-wurzel", beschreibe(nurAktion))

  // Und die dritte Form: `ende` OHNE `aktion`. Das ist
  // ags-settings.template, viermal - die Zeile ist gar kein Knopf, sie
  // traegt nur ein Bedienelement am rechten Rand.
  //
  //     NACHGETRAGEN am 01.09.2026: die beiden Formen darueber decken
  //     `aktion+ende` und `aktion` ab, diese hier fehlte. Die Zaehlung
  //     in tests/src/test_zeprow_zaehlung.py sagt, WELCHE Formen es im
  //     Baum gibt - dass jede von ihnen denselben Baum wie vorher
  //     ergibt, muss gebaut und nicht gezaehlt werden. Ohne diese Marke
  //     waere das Einstellungsfenster die einzige der sechs Seiten aus
  //     dem Auftrag, ueber die hier nichts gemessen worden waere.
  const nurEnde = zepRow({ symbol: "E", titel: "Nur Ende",
                           ende: zepToggle(false, () => { }) })
  const nurEndeSchalter = suche(nurEnde, (w) => w instanceof Gtk.Switch)
  mark("nur-ende-wurzel", beschreibe(nurEnde))
  mark("nur-ende-hat-huelle",
    suche(nurEnde, (w) => w.has_css_class("zep-row-click")) ? "ja" : "nein")
  mark("nur-ende-schalter-drin", nurEndeSchalter ? "ja" : "nein")
  mark("schalter-fokussierbar", schalter ? String(schalter.get_focusable()) : "?")
  mark("knopf-fokussierbar", knopf ? String(knopf.get_focusable()) : "?")

  const lage = (w: Gtk.Widget | null): string =>
    w ? `${w.get_width()}x${w.get_height()} abgebildet=${w.get_mapped()}` : "nichts"
  mark("lage-schalter", lage(schalter))
  mark("lage-titel", lage(titel))
  mark("lage-zahnrad", lage(zahnrad))
  mark("lage-liste", lage(liste))

  // ---- Wohin ein Zeigerdruck geht ----------------------------------
  const aufSchalter = mitte(schalter)
  const aufTitel = mitte(titel)
  const aufZahnrad = mitte(zahnrad)
  mark("punkt-schalter", aufSchalter ? aufSchalter.map(Math.round).join(",") : "-")
  mark("punkt-titel", aufTitel ? aufTitel.map(Math.round).join(",") : "-")
  mark("punkt-zahnrad", aufZahnrad ? aufZahnrad.map(Math.round).join(",") : "-")

  const trefferSchalter = aufSchalter
    ? window.pick(aufSchalter[0], aufSchalter[1], Gtk.PickFlags.DEFAULT) : null
  const trefferTitel = aufTitel
    ? window.pick(aufTitel[0], aufTitel[1], Gtk.PickFlags.DEFAULT) : null
  const trefferZahnrad = aufZahnrad
    ? window.pick(aufZahnrad[0], aufZahnrad[1], Gtk.PickFlags.DEFAULT) : null
  mark("pick-schalter", beschreibe(trefferSchalter))
  mark("pick-schalter-kette", kette(trefferSchalter))
  mark("pick-titel", beschreibe(trefferTitel))
  mark("pick-titel-kette", kette(trefferTitel))
  mark("pick-zahnrad", beschreibe(trefferZahnrad))
  mark("pick-zahnrad-kette", kette(trefferZahnrad))

  mark("pick-schalter-unter-knopf", unterDerHuelle(trefferSchalter))
  mark("pick-titel-unter-knopf", unterDerHuelle(trefferTitel))
  mark("pick-zahnrad-unter-knopf", unterDerHuelle(trefferZahnrad))
  // Trifft der Punkt in der Mitte des Zahnrads das Zahnrad selbst (oder
  // ein Kind davon)? GTK setzt seine Beschriftung als eigenes Label
  // darunter - gefragt ist also die KETTE und nicht die Gleichheit.
  const inZahnrad = (w: Gtk.Widget | null): string => {
    let lauf: Gtk.Widget | null = w
    while (lauf) {
      if (lauf.has_css_class("vpn-row-settings")) return "ja"
      lauf = lauf.get_parent()
    }
    return "nein"
  }
  mark("pick-zahnrad-im-zahnrad", inZahnrad(trefferZahnrad))

  // ---- Die Fokuskette ----------------------------------------------
  window.set_focus(null)
  const stationen: string[] = []
  for (let i = 0; i < 10; i++) {
    const weiter = window.child_focus(Gtk.DirectionType.TAB_FORWARD)
    stationen.push(weiter ? beschreibe(window.get_focus()) : "ende")
    if (!weiter) break
  }
  mark("fokuskette", stationen.join(" > "))
  mark("schalter-per-tab-erreichbar",
    stationen.some((s) => s.startsWith("GtkSwitch")) ? "ja" : "nein")
  mark("knopf-per-tab-erreichbar",
    stationen.some((s) => s.indexOf("zep-row-click") >= 0) ? "ja" : "nein")
  mark("zahnrad-per-tab-erreichbar",
    stationen.some((s) => s.indexOf("vpn-row-settings") >= 0) ? "ja" : "nein")

  // DEN FOKUS WIEDER WEGNEHMEN, und das ist kein Aufraeumen.
  //
  //     Die Schleife darueber laesst ihn auf der ZEHNTEN Station
  //     liegen. Der Test macht zwischen hier und T_FOKUS einen
  //     Bildabzug, der als "nichts hat den Fokus" gelten soll - und
  //     vergleicht ihn mit einem zweiten, nachdem der Fokus auf dem Ziel
  //     sitzt. Bliebe hier ein Fokusrahmen irgendwo stehen, maesse der
  //     Unterschied zwischen beiden Bildern das Wandern eines Rahmens
  //     statt sein Erscheinen.
  window.set_focus(null)

  // Ab jetzt wird mitgeschrieben. NICHT frueher: das Neuzeichnen der
  // Liste baut Schalter und wuerde jede Zaehlung mit seinen eigenen
  // notify::active fuellen.
  if (knopf) knopf.connect("clicked", () => eintragen("KNOPF-clicked"))
  if (schalter) schalter.connect("notify::active", () => eintragen("SCHALTER-notify"))
  if (zahnrad) zahnrad.connect("clicked", () => eintragen("ZAHNRAD-clicked"))
  return false
})

// DER FOKUS KOMMT MIT ECHTEN TABULATORTASTEN UND NICHT MEHR AUS
// grab_focus(), UND DAS IST EINE MESSUNG
//
//     Bis zum 01.09.2026 stand hier `ziel.grab_focus()`. Der Fokus lag
//     danach nachweislich richtig - und auf dem Bild aenderte sich
//     TROTZDEM kein einziger Punkt, weder auf der Zeile noch auf dem
//     Schalter (gemessen, beide Male 0 Punkte).
//
//     Der Grund ist nicht der Stil, sondern woher der Fokus kam: GTK4
//     setzt `:focus-visible` nur, wenn er ueber die TASTATUR dorthin
//     gewandert ist. Ein programmatisches grab_focus() setzt ihn nicht.
//     Eine Messung mit grab_focus() haette also fuer JEDEN Stil
//     "kein Rahmen" gesagt - auch fuer einen, der tadellos ist. Sie
//     haette wie ein Befund ausgesehen und war keiner.
//
//     Der Test tabbt darum vor diesem Zeitpunkt mit `wtype` bis zum
//     Ziel (ZIELTABS dort). Hier wird nur noch ABGELESEN, wo der Fokus
//     gelandet ist - und ob das das Ziel ist, sichert der Test zu.
GLib.timeout_add(GLib.PRIORITY_DEFAULT, T_FOKUS, () => {
  mark("ziel", ZIEL)
  mark("fokus-auf-ziel", beschreibe(window.get_focus()))
  eintragen("--fokus-gelesen--")
  return false
})

GLib.timeout_add(GLib.PRIORITY_DEFAULT, T_LESEN, () => {
  mark("nach-der-taste", buch.join(" | "))
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
