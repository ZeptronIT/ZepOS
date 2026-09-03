// SPDX-License-Identifier: GPL-3.0-or-later
//
// Ein Dateiwaehler aus einer Layer-Flaeche heraus - einmal so, wie es
// bis zum 01.09.2026 war, und einmal so, wie es seither ist.
//
// WARUM ES DIESES KIND GIBT (01.09.2026)
//     Gemeldet: "bei klick auf 'datei auswaehlen' in dem dialog
//     verbuggt alles, man kann nichts mehr sehen." Eine Vorlage zu
//     LESEN kann diesen Satz weder bestaetigen noch widerlegen: was
//     passiert, entscheidet der Compositor - ein gewoehnliches Fenster
//     liegt unter einer OVERLAY-Flaeche, und das steht in keinem
//     Quelltext.
//
//     Also wird es gebaut und nachgesehen. Diese Datei wird vom Test
//     in den erzeugten AGS-Baum kopiert und dort gebuendelt, damit sie
//     GENAU die Funktion ruft, die im Einstellungsfenster gerufen wird
//     (waehleDatei aus utils/overlay) - und keinen Nachbau davon.
//
// ZWEI BETRIEBSARTEN, WEIL EINE MESSUNG OHNE GEGENPROBE NICHTS SAGT
//     ZEPOS_WAEHLER_MODUS=roh       der Aufruf, wie er vorher dastand:
//                                   Gtk.FileDialog.open() direkt auf
//                                   die Layer-Flaeche.
//     ZEPOS_WAEHLER_MODUS=repariert ueber waehleDatei().
//     ZEPOS_WAEHLER_MODUS=ohne-gtk  ueber waehleDatei(), aber mit einem
//                                   Gtk.FileDialog, dessen Konstruktor
//                                   wirft - der Boden muss einspringen.
//
//     Ohne den rohen Lauf waere "die Flaeche liegt auf Ebene 1" eine
//     Zahl ohne Bedeutung; mit ihm ist es der Unterschied zwischen 3
//     und 1, und 3 ist die Ebene, auf der der Waehler verdeckt war.
//
// DER ABBRUCH KOMMT AUS DEM PROGRAMM UND NICHT VOM ZEIGER
//     Ein Gio.Cancellable, nach ZEPOS_WAEHLER_ABBRUCH Millisekunden
//     gezogen. Der Messstand klickt nicht - er koennte es unter
//     Hyprland auch gar nicht -, und ohne Abbruch bliebe ungeprueft,
//     ob die Flaeche danach zurueckkommt.
import app from "ags/gtk4/app"
import Astal from "gi://Astal?version=4.0"
import { Gtk } from "ags/gtk4"
import GLib from "gi://GLib"
import Gio from "gi://Gio"
import { waehleDatei } from "./utils/overlay"

const MODUS = GLib.getenv("ZEPOS_WAEHLER_MODUS") ?? "repariert"
const OEFFNEN = Number(GLib.getenv("ZEPOS_WAEHLER_OEFFNEN") ?? "4000")
const ABBRUCH = Number(GLib.getenv("ZEPOS_WAEHLER_ABBRUCH") ?? "9000")

// Derselbe Name, unter dem der Test die Flaeche in `hyprctl layers`
// sucht. Als Konstante, damit er nur an einer Stelle steht.
const NAMENSRAUM = "waehler-probe"

app.start({
  main() {
    // Dieselben vier Werte, die createOverlayWindow() setzt (siehe
    // ags-overlay-utils.template) - Ebene, Tastenmodus, Anker,
    // Namensraum. Ein Fenster mit anderen Werten maesse ein anderes
    // Fenster.
    const fenster = new Astal.Window({
      namespace: NAMENSRAUM,
      layer: Astal.Layer.OVERLAY,
      keymode: Astal.Keymode.ON_DEMAND,
      anchor: Astal.WindowAnchor.TOP | Astal.WindowAnchor.LEFT,
      visible: false,
    })
    const rumpf = new Gtk.Box({ orientation: Gtk.Orientation.VERTICAL })
    rumpf.append(new Gtk.Label({ label: "ZEPOS-WAEHLER-PROBE" }))
    // Die Sprosse L (880) und die Hoehe, die das Einstellungsfenster
    // anmeldet (600) - damit die Flaeche denselben Ausschnitt bedeckt
    // wie das Fenster, um das es geht.
    rumpf.set_size_request(880, 600)
    fenster.set_child(rumpf)
    fenster.visible = true
    print(`WAEHLER:flaeche-offen:${MODUS}`)

    GLib.timeout_add(GLib.PRIORITY_DEFAULT, OEFFNEN, () => {
      const abbruch = new Gio.Cancellable()
      const titel = "ZEPOS-WAEHLER-DIALOG"

      if (MODUS === "roh") {
        // Der Aufruf, wie er bis zum 01.09.2026 in
        // ags-vpn-settings.template stand.
        const waehler = new (Gtk as any).FileDialog({ title: titel })
        waehler.open(fenster, abbruch, (_quelle: any, ergebnis: any) => {
          try { waehler.open_finish(ergebnis) } catch (e) { /* Abbruch */ }
          print("WAEHLER:fertig")
        })
        print("WAEHLER:offen")
      } else if (MODUS === "ohne-gtk") {
        // GTKs Waehler wird UNMOEGLICH gemacht, und zwar an der Stelle,
        // an der waehleDatei() ihn baut: der Konstruktor wirft.
        //
        // WARUM SO UND NICHT DURCH EIN FEHLENDES PORTAL. Der Zustand,
        // den der Nutzer am 03.09.2026 gemeldet hat ("dialoge [...]
        // erscheinen garnicht erst"), hat mindestens zwei Ursachen -
        // GTK_USE_PORTAL und die FileChooser-Zuordnung - und keine davon
        // laesst sich in einer Testsitzung ehrlich nachbauen: der
        // Messstand hat weder seine Portalzuordnung noch seine
        // Umgebung. Was sich nachbauen laesst, ist die WIRKUNG: kein
        // Fenster von GTK. Genau darauf antwortet der Boden in
        // waehleDatei(), und genau das wird hier gemessen.
        const echt = (Gtk as any).FileDialog
        ;(Gtk as any).FileDialog = function () {
          throw new Error("ZEPOS-PROBE: kein Gtk.FileDialog")
        }
        const ging = waehleDatei(fenster, titel, (pfad) => {
          print("WAEHLER:pfad:" + pfad)
        }, abbruch, GLib.get_home_dir(), [".conf"])
        ;(Gtk as any).FileDialog = echt
        print("WAEHLER:offen:" + String(ging))
      } else {
        const ging = waehleDatei(fenster, titel, (pfad) => {
          print("WAEHLER:pfad:" + pfad)
        }, abbruch)
        print("WAEHLER:offen:" + String(ging))
      }

      GLib.timeout_add(GLib.PRIORITY_DEFAULT, ABBRUCH, () => {
        abbruch.cancel()
        print("WAEHLER:abgebrochen")
        return GLib.SOURCE_REMOVE
      })
      return GLib.SOURCE_REMOVE
    })
  },
})
