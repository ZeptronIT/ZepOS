// SPDX-License-Identifier: GPL-3.0-or-later
//
// Der Dateiwaehler auf dem WEG DES NUTZERS - und was danach von der
// Ueberlagerung uebrig ist.
//
// WARUM ES DIESES KIND NEBEN dateiwaehler_child.ts GIBT (01.09.2026)
//     Das Kind daneben ist am 01.09.2026 entstanden und war gruen,
//     waehrend der Nutzer denselben Fehler ein zweites Mal gemeldet hat:
//     "immernoch sobald ich den datei icon klick um die datei
//      auszuwaehlen kommt kien datei auswaehler sondern alle ags sachen
//      werden blockiert irgendwie voll komisch".
//
//     Es war gruen, weil es an DREI Stellen etwas anderes tut als die
//     Oberflaeche:
//
//       1. Es baut seine Flaeche mit `new Astal.Window({...})` von Hand
//          nach, statt createOverlayWindow() zu rufen. Die Fabrik ist
//          aber genau die Stelle, an der Ebene und Tastenmodus des
//          Fensters herkommen - und an der sie beim naechsten Aufgehen
//          NICHT wieder gesetzt werden.
//       2. Es oeffnet den Waehler aus einem GLib.timeout heraus, nicht
//          aus dem Rueckruf eines Knopfes.
//       3. Es BRICHT DEN WAEHLER IMMER AB, aus dem Programm heraus, mit
//          einem Gio.Cancellable. Damit feuert der Rueckruf von
//          Gtk.FileDialog.open() in jedem Lauf - und zurueck() lief.
//          Genau der Fall, ueber den der Nutzer klagt, ist der Fall, in
//          dem dieser Rueckruf NIE feuert; den hat dort nichts gemessen.
//
//     Dieses Kind laesst deshalb alle drei Unterschiede weg: echte
//     Fabrik, echter Knopfdruck, und ein Lauf, in dem NICHT abgebrochen
//     wird.
//
// WAS ES BERICHTET, UND WARUM UEBER print() UND NICHT UEBER hyprctl
//     Ebene und Tastenmodus stehen im Compositor (hyprctl layers) - die
//     misst der Test. Was der Compositor NICHT sagt, ist der Zustand des
//     Widgets: ob GTK die Flaeche als Elternfenster eines modalen
//     Dialogs unempfindlich gestellt hat (get_sensitive), und mit
//     welcher Ebene das Fenster beim NAECHSTEN Aufgehen wiederkommt.
//     Beides steht nur im Prozess, also sagt es der Prozess.
//
// DIE BETRIEBSARTEN
//     ZEPOS_SONDE=offen      Waehler auf, NICHT abbrechen. Misst den
//                            Zustand, waehrend er steht.
//     ZEPOS_SONDE=zweitesmal Waehler auf, NICHT abbrechen, Fenster
//                            schliessen (wie ESC oder das Schliesskreuz)
//                            und WIEDER OEFFNEN. Misst, was der Nutzer
//                            beim naechsten Klick auf das Zahnrad
//                            bekommt.
import app from "ags/gtk4/app"
import Astal from "gi://Astal?version=4.0"
import { Gtk } from "ags/gtk4"
import GLib from "gi://GLib"
import { createOverlayWindow, waehleDatei } from "./utils/overlay"
import { zepButton } from "./utils/kit"

const SONDE = GLib.getenv("ZEPOS_SONDE") ?? "offen"

// Derselbe Name, unter dem der Test die Flaeche in `hyprctl layers`
// sucht. `createOverlayWindow` gibt ihn als `namespace` weiter.
const NAMENSRAUM = "waehler-sonde"
const FENSTERTITEL = "ZEPOS-SONDE-DIALOG"

// Die Sprosse L und die Hoehe, die das Einstellungsfenster anmeldet -
// dieselben zwei Zahlen, mit denen VpnSettings die Fabrik ruft.
const BREITE = 880
const HOEHE = 600

// Der Fahrplan, in Millisekunden nach dem Start. Grosszuegig, weil die
// Fabrik ihre Lage ueber `hyprctl` holt und der Waehler von GTK gebaut
// wird - beides dauert, und ein zu enger Takt maesse den Aufbau statt
// des Zustands.
const T_OEFFNEN = 3000     // Fenster aufziehen
const T_KLICK = 6000       // auf den Knopf druecken
const T_MESSEN = 11000     // Zustand melden, waehrend der Waehler steht
const T_ZU = 13000         // Fenster schliessen (nur "zweitesmal")
const T_WIEDER = 15000     // Fenster wieder aufziehen (nur "zweitesmal")
const T_ENDE = 19000       // letzte Meldung

let fenster: Astal.Window | null = null
let inhalt: Gtk.Widget | null = null
// Der Knopf, den der Fahrplan unten drueckt. Als Modulvariable und nicht
// ueber globalThis: buildContent() laeuft einmal, und der Fahrplan
// braucht danach genau diesen einen Knopf.
let blaetterKnopf: Gtk.Button | null = null

function melde(marke: string): void {
  if (!fenster) {
    print(`SONDE:${marke}:kein-fenster`)
    return
  }
  // get_layer()/get_keymode() liefern die Aufzaehlung als Zahl. Sie wird
  // roh gemeldet und nicht uebersetzt: der Test kennt die Namen, und
  // eine Uebersetzung hier waere eine zweite Stelle, an der sie stehen.
  print(`SONDE:${marke}:ebene=${fenster.get_layer()}`
    + `:tastenmodus=${fenster.get_keymode()}`
    + `:sichtbar=${fenster.visible}`
    + `:empfindlich=${fenster.get_sensitive()}`
    + `:inhalt-empfindlich=${inhalt ? inhalt.get_sensitive() : "?"}`)
}

app.start({
  main() {
    const ueberlagerung = createOverlayWindow({
      name: NAMENSRAUM,
      width: BREITE,
      height: HOEHE,
      cssClass: "SondeFenster",
      headerIcon: "S",
      headerTitle: "ZEPOS-SONDE",
      buildContent: (win) => {
        fenster = win
        const rumpf = new Gtk.Box({
          orientation: Gtk.Orientation.VERTICAL, spacing: 12 })
        rumpf.set_size_request(BREITE - 26, 400)
        // DER ECHTE KNOPF: dieselbe Fabrik (zepButton), dieselbe Rolle
        // ("still") und derselbe Rueckruf wie der Blaetter-Knopf der
        // beiden Einleser in ags-vpn-settings.template.
        const knopf = zepButton("D", "still", () => {
          const ging = waehleDatei(win, FENSTERTITEL, (pfad) => {
            print(`SONDE:pfad:${pfad}`)
          })
          print(`SONDE:waehleDatei:${String(ging)}`)
        })
        rumpf.append(knopf)
        inhalt = rumpf
        // Der Knopf wird spaeter GEDRUECKT und nicht geklickt: unter
        // Hyprland laesst sich kein Zeigerereignis erzeugen, aber
        // `clicked` ist dasselbe Signal, das ein Klick ausloest.
        blaetterKnopf = knopf
        return rumpf
      },
    })

    GLib.timeout_add(GLib.PRIORITY_DEFAULT, T_OEFFNEN, () => {
      void ueberlagerung.show()
      return GLib.SOURCE_REMOVE
    })

    GLib.timeout_add(GLib.PRIORITY_DEFAULT, T_KLICK, () => {
      melde("vor-dem-klick")
      blaetterKnopf?.emit("clicked")
      return GLib.SOURCE_REMOVE
    })

    GLib.timeout_add(GLib.PRIORITY_DEFAULT, T_MESSEN, () => {
      melde("waehrend-des-waehlers")
      return GLib.SOURCE_REMOVE
    })

    if (SONDE === "zweitesmal") {
      GLib.timeout_add(GLib.PRIORITY_DEFAULT, T_ZU, () => {
        // Was der Nutzer tut, wenn nichts kommt: das Fenster zumachen.
        ueberlagerung.hide()
        melde("nach-dem-schliessen")
        return GLib.SOURCE_REMOVE
      })
      GLib.timeout_add(GLib.PRIORITY_DEFAULT, T_WIEDER, () => {
        void ueberlagerung.show()
        return GLib.SOURCE_REMOVE
      })
    }

    GLib.timeout_add(GLib.PRIORITY_DEFAULT, T_ENDE, () => {
      melde("am-ende")
      return GLib.SOURCE_REMOVE
    })
  },
})
