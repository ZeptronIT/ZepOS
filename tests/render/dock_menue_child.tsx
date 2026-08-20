// SPDX-License-Identifier: GPL-3.0-or-later
//
// Das Kind zu tests/render/test_menue.py: es baut den ERZEUGTEN
// Fuss als echte Layer-Shell-Flaeche und klappt sein Rechtsklick-Menue
// auf.
//
// WARUM EIN KIND UND NICHT EIN ZEIGER
//     Dieselbe Antwort wie in starter_click_child.tsx, und hier noch
//     eine Stufe zwingender: diese Maschine hat kein Werkzeug, das
//     einen MAUSKLICK in eine Wayland-Sitzung schiebt - `wlrctl` und
//     `ydotool` sind nicht installiert, `wtype` kann nur Tasten, und
//     Hyprland hat keinen Dispatcher dafuer (`movecursor` setzt den
//     Zeiger, druecken kann er nicht). Ein RECHTSklick erst recht
//     nicht.
//
//     Geklickt wird deshalb da, wo GTK den Klick auch entgegennaehme:
//     am Signal "pressed" der Gtk.GestureClick, die die Vorlage an den
//     Knopf haengt - gefunden ueber observe_controllers(), also an der
//     Stelle, an der GTK die Steuerungen eines Widgets ohnehin fuehrt.
//     Was daran ECHT ist und den Ausschlag gibt: es ist der Fuss aus
//     der erzeugten widget/Dock.tsx, in einem echten Compositor, auf
//     einer echten Layer-Shell-Flaeche - und was das Menue daraufhin
//     tut, tut es wirklich.
//
// WAS DIE ESCAPE-TASTE ANGEHT
//     Die kommt NICHT von hier, sondern von aussen: der Test schickt
//     sie mit `wtype` an den Compositor, also auf demselben Weg wie
//     ein Mensch. Das ist der Punkt der ganzen Messung - ein Fuss auf
//     Astal.Keymode.NONE bekommt vom Compositor gar keine
//     Tastenereignisse, und ob die Umschaltung auf ON_DEMAND das
//     aendert, kann nur der Compositor beantworten.
//
// WARUM `ags request` UND KEIN ZEITPLAN
//     Der Test misst ZWISCHEN den Schritten (hyprctl layers, ein Bild,
//     wtype). Ein Kind, das seine Schritte nach der Uhr abarbeitet,
//     zwaenge ihn, die Uhr zu treffen. So sagt er, wann der naechste
//     Schritt dran ist, und bekommt die Antwort zurueck.

import app from "ags/gtk4/app"
import GLib from "gi://GLib"
import { Gtk } from "ags/gtk4"
import Dock from "./widget/Dock"
// BEIDE Stylesheets, und zwar so, wie app.ts sie auftraegt: style.scss
// als `css` beim Start, bar.css danach obendrauf. Ohne sie misst dieser
// Lauf einen Adwaita-Fuss mit einem Adwaita-Menue - also nicht das, was
// ZepOS ausliefert. Dieselbe Falle, die dock_headless_child.tsx im Kopf
// beschreibt, nur mit einem Bild statt einer Zahl.
import style from "./style.scss"

const INSTANZ = "zepos-dock-menue"
const BAR_CSS = `${GLib.get_user_config_dir()}/ags/bar.css`

// AUF WELCHEM SCHIRM GEMESSEN WIRD, und warum das eine eigene Zeile ist
//     Dock() baut ein Fenster JE AUSGANG. Der verschachtelte Compositor
//     hat zwei - den Kasten auf dem Schirm des Wirts und den kopflosen,
//     den grim abbildet. Ein Menue am falschen der beiden ist ein Menue,
//     das es gibt und das auf keinem Bild steht.
//
//     GEMESSEN am 20.08.2026: genau so ist es zuerst gelaufen. Der
//     Wayland-Mitschnitt zeigte den Popup vollstaendig - get_popup an
//     der Layer-Flaeche, configure(-63, -87, 181, 87), Puffer
//     angehaengt, `wl_surface.enter(wl_output#29)` - und das Bild
//     zeigte null veraenderte Punkte. #29 war der andere Ausgang.
const AUSGANG = GLib.getenv("ZEPOS_AUSGANG") ?? ""

/** Die Flaeche des Fusses auf DEM Schirm, der abgebildet wird. */
function fuss(): Gtk.Window | null {
  const fenster = Gtk.Window.get_toplevels()
  let ersatz: Gtk.Window | null = null
  for (let index = 0; index < fenster.get_n_items(); index++) {
    const eines = fenster.get_item(index) as Gtk.Window
    if (!eines.has_css_class("dock-window")) continue
    if (AUSGANG && eines.get_name() === `dock-${AUSGANG}`) return eines
    if (!ersatz) ersatz = eines
  }
  // Ohne ZEPOS_AUSGANG das erste - fuer einen Aufbau mit einem Schirm
  // ist das dasselbe Fenster.
  return AUSGANG ? null : ersatz
}

/** Die Kinder der Knopfreihe, in ihrer Reihenfolge. */
function reihe(): Gtk.Widget[] {
  const flaeche = fuss()
  const kasten = flaeche ? flaeche.get_child() : null
  const kinder: Gtk.Widget[] = []
  let kind: Gtk.Widget | null = kasten ? kasten.get_first_child() : null
  while (kind) {
    kinder.push(kind)
    kind = kind.get_next_sibling()
  }
  return kinder
}

/** Der erste angeheftete Knopf, oder null. */
function angeheftet(): Gtk.Widget | null {
  for (const kind of reihe()) {
    if (kind.has_css_class("dock-pin")) return kind
  }
  return null
}

/** Das offene Menue, wenn eines offen ist.
 *
 * Ein Gtk.Popover mit set_parent() ist ein KIND seines Ankers und nicht
 * dessen `child` - gesucht wird deshalb unter den Geschwistern des
 * Knopfinhalts und nicht mit get_child().
 */
function menue(): Gtk.Popover | null {
  for (const knopf of reihe()) {
    let kind: Gtk.Widget | null = knopf.get_first_child()
    while (kind) {
      if (kind instanceof Gtk.Popover) return kind
      kind = kind.get_next_sibling()
    }
  }
  return null
}

/** Die Aufschriften des offenen Menues, durch "|" getrennt. */
function eintraege(): string {
  const offen = menue()
  const liste = offen ? offen.get_child() : null
  if (!liste) return ""
  const texte: string[] = []
  let zeile: Gtk.Widget | null = liste.get_first_child()
  while (zeile) {
    // Eine Zeile aus zepRow ist ein Gtk.Button mit .zep-row-click, und
    // ihr Text steht zwei Ebenen tiefer. Ein Trenner hat keinen.
    const text = beschriftung(zeile)
    if (text) texte.push(text)
    zeile = zeile.get_next_sibling()
  }
  return texte.join("|")
}

/** Die erste Beschriftung unterhalb dieses Widgets. */
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

/** Den Rechtsklick an diesem Knopf ausloesen. */
function rechtsklick(knopf: Gtk.Widget): string {
  const steuerungen = knopf.observe_controllers()
  for (let index = 0; index < steuerungen.get_n_items(); index++) {
    const steuerung = steuerungen.get_item(index)
    if (!(steuerung instanceof Gtk.GestureClick)) continue
    if (steuerung.get_button() !== 3) continue
    steuerung.emit("pressed", 1, 8.0, 8.0)
    return "geklickt"
  }
  return "keine-rechtsklick-geste"
}

app.start({
  instanceName: INSTANZ,
  css: style,
  main() {
    if (GLib.file_test(BAR_CSS, GLib.FileTest.EXISTS)) {
      app.apply_css(BAR_CSS, false)
    } else {
      console.error(`kein ${BAR_CSS} - der Fuss misst Adwaita`)
    }
    Dock()
  },
  requestHandler(request: any, res: (response: any) => void) {
    const wunsch = Array.isArray(request) ? request.join(" ") : String(request)

    if (wunsch.includes("rechtsklick")) {
      const knopf = angeheftet()
      res(knopf ? rechtsklick(knopf) : "kein-angehefteter-knopf")
    } else if (wunsch.includes("eintraege")) {
      res(eintraege())
    } else if (wunsch.includes("offen")) {
      // "keins" heisst: es gibt gar keinen Popover mehr an einem der
      // Knoepfe. Genau das ist der Zustand nach dem Zugehen - das Menue
      // entsteht mit dem Rechtsklick und wird beim Schliessen wieder
      // abgenommen (siehe zeigeMenue() in ags-dock.template).
      const offen = menue()
      res(offen ? (offen.get_mapped() ? "abgebildet" : "nur-da") : "keins")
    } else if (wunsch.includes("waehle")) {
      // DIE LETZTE Zeile, und das ist eine Entscheidung mit Grund.
      //
      // Gefragt ist hier nur, ob das Menue nach einer Auswahl zugeht -
      // WELCHER Punkt was tut, misst der kopflose Lauf
      // (tests/src/test_dock_menue.py). Die erste Zeile einer Anheftung
      // ist "Neues Fenster" und STARTET etwas: das Bild danach zeigte
      // im ersten Versuch 1.802.244 veraenderte Punkte, also einen
      // Browser ueber dem halben Schirm - und damit war nicht mehr zu
      // sehen, ob das Menue fort ist oder nur verdeckt.
      //
      // Die letzte Zeile ist "Vom Dock entfernen". Sie ruft
      // zepos-settings-gui, das auf einer Entwicklermaschine nicht
      // installiert ist; der Schreibversuch scheitert, das Menue geht
      // trotzdem zu, und der Schirm bleibt, wie er war. Genau der
      // Zuschnitt, den diese Frage braucht.
      const offen = menue()
      const liste = offen ? offen.get_child() : null
      const letzte = liste ? liste.get_last_child() : null
      if (letzte instanceof Gtk.Button) {
        letzte.emit("clicked")
        res("gewaehlt")
      } else {
        res("keine-zeile")
      }
    } else if (wunsch.includes("angeheftete")) {
      // Die Aufschriften der angehefteten Knoepfe, durch "|" getrennt.
      const namen: string[] = []
      for (const kind of reihe()) {
        if (kind.has_css_class("dock-pin")) {
          namen.push(kind.get_tooltip_text() ?? "?")
        }
      }
      res(namen.join("|"))
    } else if (wunsch.includes("tastatur")) {
      const flaeche = fuss() as any
      res(flaeche ? String(flaeche.keymode) : "keine-flaeche")
    } else {
      res(`unbekannt: ${wunsch}`)
    }
  },
})
