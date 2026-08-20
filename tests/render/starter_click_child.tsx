// SPDX-License-Identifier: GPL-3.0-or-later
//
// Das Kind zu tests/render/test_starter.py: es baut den ERZEUGTEN
// Starterknopf in einem verschachtelten Compositor und klickt ihn.
//
// WARUM EIN KIND UND NICHT EIN ZEIGER
//     Diese Maschine hat kein Werkzeug, das einen Mausklick in eine
//     Wayland-Sitzung schiebt: `wlrctl` und `ydotool` sind nicht
//     installiert, `wtype` kann nur Tasten - und der Knopf ist
//     Astal.Keymode.NONE, nimmt die Tastatur also nie. Hyprland selbst
//     hat dafuer keinen Dispatcher (`movecursor` setzt den Zeiger,
//     druecken kann er nicht).
//
//     Geklickt wird deshalb da, wo GTK den Klick auch entgegennaehme:
//     am Signal "clicked" des Gtk.Button. Was daran ECHT ist und den
//     Ausschlag gibt: es ist der Knopf aus der erzeugten
//     widget/StarterButton.tsx, in einem echten Compositor mit einer
//     echten Layer-Shell-Flaeche, und was danach passiert, passiert
//     wirklich - die Frage an den Compositor geht ueber den echten
//     Socket, und der Rueckfall startet einen echten Prozess.
//
// WARUM DER KNOPF GESUCHT UND NICHT UEBERGEBEN WIRD
//     StarterButton() gibt nichts zurueck - genau wie PowerButton().
//     Ein Rueckgabewert nur fuer diesen Test waere eine Aenderung an der
//     Vorlage, die auf keiner Installation einen Leser haette. Gesucht
//     wird stattdessen an der Stelle, an der GTK jedes Fenster ohnehin
//     fuehrt (Gtk.Window.get_toplevels), ueber die CSS-Klasse, die die
//     Vorlage setzt.

import app from "ags/gtk4/app"
import GLib from "gi://GLib"
import { Gtk } from "ags/gtk4"
import StarterButton from "./widget/StarterButton"

// Wie lange gewartet wird, bevor geklickt wird. Die Flaeche muss beim
// Compositor angemeldet und abgebildet sein - ein Klick auf ein Fenster,
// das es noch nicht gibt, meldete "KEIN KNOPF" und saehe wie ein Befund
// aus.
const WARTEN_MS = 1500

app.start({
  instanceName: "zepos-starter-klick",
  main() {
    StarterButton()

    GLib.timeout_add(GLib.PRIORITY_DEFAULT, WARTEN_MS, () => {
      const toplevels = Gtk.Window.get_toplevels()
      let getroffen = 0
      for (let index = 0; index < toplevels.get_n_items(); index++) {
        const fenster = toplevels.get_item(index) as Gtk.Window
        if (!fenster.has_css_class("starter-button-window")) continue
        const platte = fenster.get_child()
        const knopf = platte ? platte.get_first_child() : null
        if (!knopf) continue
        knopf.emit("clicked")
        getroffen += 1
      }
      console.log(`GEKLICKT:${getroffen}`)
      return GLib.SOURCE_REMOVE
    })
  },
})
