// SPDX-License-Identifier: GPL-3.0-or-later
//
// Das dritte Kind unter tests/src/test_bar_headless.py: es baut das
// erzeugte Dock auf einer echten GTK4-Anzeige und schreibt auf, was
// darauf steht.
//
// WARUM EIN EIGENES KIND UND NICHT EINE ZEILE MEHR IM ERSTEN
//     bar_headless_child.tsx baut Leiste UND Dock in EINEM Prozess, und
//     dieser Prozess erbt die Anwendungsverzeichnisse der Maschine, auf
//     der er laeuft. Was das Dock anheftet, haengt aber genau daran:
//     angeheftet wird, wozu es eine .desktop-Datei gibt. Ein Dock, das
//     auf dem Rechner des Entwicklers drei Knoepfe hat und auf dem
//     Bauserver keinen, misst nicht das Dock, sondern die Maschine.
//
//     Also bekommt dieses Kind ein XDG_DATA_DIRS, das NUR auf ein
//     Verzeichnis des Tests zeigt. Was darin liegt, entscheidet der
//     Test - und damit ist auch die Gegenrichtung messbar: ein Name aus
//     der Auswahl, zu dem es keinen Eintrag gibt, darf keinen Knopf
//     bekommen, und das Dock muss trotzdem dastehen.
//
// WARUM DER INHALT UND NICHT DAS LAYER-SHELL-FENSTER
//     Dieselbe Antwort wie beim ersten Kind: Astal.Window ruft
//     gtk_layer_init_for_window, und das prueft GDK_IS_WAYLAND_DISPLAY.
//     Unter gtk4-broadwayd schreibt es CRITICAL-Zeilen, und eine
//     kritische Meldung ist in diesem Projekt ein Testfehler.

import { Gtk, Gdk } from "ags/gtk4"
import GLib from "gi://GLib"
import GioUnix from "gi://GioUnix?version=2.0"
import { DOCK_MARGIN_BOTTOM, DockContent, terminalCommand } from "./widget/Dock"

const TRACE = GLib.getenv("ZEPOS_TRACE") ?? ""
const marks: string[] = []

function mark(name: string, value: string): void {
  marks.push(`${name}:${value}`)
}

Gtk.init()

// Das Stylesheet, wenn der Test eines mitgibt. Ohne es misst die
// Fusszeile Adwaita und nicht ZepOS - dieselbe Falle, die der Kopf von
// bar_fit_child.tsx beschreibt. Fuer die Frage "was steht auf dem Dock"
// ist es gleichgueltig, fuer die Frage "wie hoch ist es" ist es alles.
const CSS = GLib.getenv("ZEPOS_CSS") ?? ""
const display = Gdk.Display.get_default()
if (CSS && display) {
  const provider = new Gtk.CssProvider()
  provider.load_from_path(CSS)
  Gtk.StyleContext.add_provider_for_display(
    display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
}

const window = new Gtk.Window({ title: "zepos-dock-headless" })
const dock = DockContent()
window.add_css_class("dock-window")
window.set_child(dock)
window.set_default_size(1920, 96)
window.present()

mark("dock", dock.get_name())
// Die Frage, um die es geht: steht das Dock da, obwohl KEIN Fenster
// offen ist? Ohne Compositor meldet Hyprland.refresh() den leeren
// Zustand, also ist genau das der Fall, den dieses Kind herstellt.
mark("sichtbar", dock.get_visible() ? "ja" : "nein")

const pinned: string[] = []
const alle: string[] = []
let child: Gtk.Widget | null = dock.get_first_child()
while (child) {
  const klassen = child.get_css_classes()
  const beschriftung = child.get_tooltip_text() ?? child.get_css_name()
  alle.push(`${beschriftung}[${klassen.join(" ")}]${child.visible ? "" : "(aus)"}`)
  if (klassen.includes("dock-pin")) pinned.push(beschriftung)
  child = child.get_next_sibling()
}
mark("angeheftet", pinned.join(","))
mark("kinder", alle.join(","))

// WAS DIE FUSSZEILE AN BILDSCHIRMHOEHE KOSTET
//     Die Flaeche ist nur unten verankert, wird also so hoch wie ihr
//     Inhalt - anders als die Leiste oben, die ihre Dicke vorgegeben
//     bekommt. gtk4-layer-shell rechnet die exklusive Zone aus dieser
//     Hoehe PLUS dem Aussenabstand an der verankerten Kante. Beide
//     Summanden stehen hier, damit die Abnahme sie addieren kann,
//     statt eine der beiden Zahlen aus der Groessentabelle
//     nachzuschlagen und damit an der Vorlage vorbei zu messen.
mark("hoehe", String(dock.measure(Gtk.Orientation.VERTICAL, -1)[0]))
mark("rand", String(DOCK_MARGIN_BOTTOM))

// WAS EIN KLICK AUF EINEN KONSOLENEINTRAG AUSLOEST.
//
// Der Klick selbst ist hier nicht messbar - es gibt keinen Compositor,
// an den Hyprland.dispatch etwas schicken koennte. Messbar ist die
// Entscheidung davor, und genau die war der Fehler: GIOs eigenes
// launch() findet fuer Terminal=true kein Terminal, das ZepOS
// ausliefert, und wirft. Siehe terminalCommand() in ags-dock.template.
for (const program of ["btop", "firefox"]) {
  const info = GioUnix.DesktopAppInfo.new(`${program}.desktop`)
  mark(`terminal-${program}`, info ? (terminalCommand(info) ?? "selbst") : "kein-eintrag")
}

if (TRACE) {
  GLib.file_set_contents(TRACE, new TextEncoder().encode(marks.join("\n") + "\n"))
}
print(marks.join("\n"))
