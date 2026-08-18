// SPDX-License-Identifier: GPL-3.0-or-later
//
// Das Kind von test_the_tray_survives_a_second_screen: es baut die
// erzeugte Ablage ZWEIMAL, so wie ags-bar.template es auf einer
// Maschine mit zwei Schirmen tut.
//
// WARUM ES DAFUER EINEN EIGENEN LAUF BRAUCHT
//     Die anderen Kinder dieser Datei bekommen eine Busadresse, die es
//     nicht gibt ("unix:path=.../kein-bus") - genau, damit sie den
//     Sitzungsbus des Nutzers nicht anfassen. Ohne Bus laeuft der
//     Erwerbs-Rueckruf von Gio.bus_own_name aber NIE, und der Fehler,
//     um den es hier geht, steckt in eben diesem Rueckruf. Ein Lauf
//     ohne Bus haette also gar nichts zu messen.
//
//     Deshalb startet der Test einen EIGENEN Bus (dbus-run-session) und
//     nicht den des Nutzers. Er gehoert diesem Prozess, er stirbt mit
//     ihm, und der Name org.kde.StatusNotifierWatcher darauf ist
//     garantiert frei - was auf dem Bus des Entwicklers nicht so ist,
//     weil dort dessen eigene Leiste laeuft.
//
// WAS GEMESSEN WIRD
//     Der zweite Aufruf darf keinen Fehler auf stderr schreiben. Bis
//     zum 12.08.2026 tat er es:
//         Gio.IOErrorEnum: An object is already exported for the
//         interface org.kde.StatusNotifierWatcher at
//         /StatusNotifierWatcher
//     GDBus beantwortet einen zweiten bus_own_name fuer denselben Namen
//     auf DERSELBEN Verbindung mit ALREADY_OWNER und ruft den
//     Erwerbs-Rueckruf trotzdem; der exportierte dann dasselbe Objekt
//     ein zweites Mal auf denselben Pfad.

import { Gtk } from "ags/gtk4"
import GLib from "gi://GLib"
import { Tray } from "./utils/tray"

const TRACE = GLib.getenv("ZEPOS_TRACE") ?? ""

Gtk.init()

// Zwei Schirme, zwei Ablagen - genau das, was Bar() je Gdk.Monitor tut.
const first = Tray(18)
const second = Tray(18)

const marks: string[] = [
  `boxen:${first === second ? "dieselbe" : "zwei"}`,
  // Eine Ablage, in der kein Programm ein Symbol angemeldet hat, darf
  // nichts zeigen: die Leiste haengt ihr sonst eine Kachel an, die
  // leer ist.
  `leer-sichtbar:${first.get_visible() ? "ja" : "nein"}`,
]

// Der Bus antwortet asynchron. Ohne diesen Durchlauf waere das Kind
// fertig, bevor irgendein Rueckruf gelaufen ist - und die Messung
// gruen, weil nichts passiert ist.
const loop = GLib.MainLoop.new(null, false)
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2000, () => {
  loop.quit()
  return false
})
loop.run()

if (TRACE) {
  GLib.file_set_contents(TRACE, new TextEncoder().encode(
    marks.join("\n") + "\n"))
}
