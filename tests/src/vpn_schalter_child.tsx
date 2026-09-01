// SPDX-License-Identifier: GPL-3.0-or-later
//
// Der Schalter der VPN-Liste - wirklich betaetigt, und danach
// nachgesehen, was sich geaendert hat.
//
// WARUM ES DIESES KIND GIBT (22.08.2026)
//     Die Liste mit einem Schalter je Eintrag ist die Hauptneuerung von
//     0.1.11 (Zusage bc93496, "aus einer Verbindung wird eine Liste").
//     GEZAEHLT am 22.08.2026 ueber den ganzen Baum: `schalte`,
//     `vpnListe` und `laufendeId` aus ags-vpn.template kamen in KEINER
//     Testdatei vor. Der einzige Test, der die Seite ueberhaupt
//     anfasste, war tests/render/test_vpn_breite.py - und der zaehlt
//     Bildpunkte. Ein Fenster ganz OHNE Liste haette ihn genauso
//     bestanden.
//
// WARUM EIN KIND UND KEIN PYTHON-TEST AUF DEN QUELLTEXT
//     Wortgleich zu dock_menue_child.tsx: ein Gtk.Switch hat sein
//     "notify::active" in dem Prozess, der ihn gebaut hat. Ein Test, der
//     die Vorlage nur LIEST, kann bezeugen, dass dort ein zepToggle
//     steht - nicht, dass sein Rueckruf ankommt, nicht, dass danach eine
//     andere Zeile ausgewaehlt ist, und schon gar nicht, dass die Liste
//     sich neu zeichnet. Genau diese drei sind die Frage.
//
// WARUM vpnSeite.bauen() UND KEIN NACHBAU
//     Dieselbe Trennung wie in corner_button_child.tsx: gebaut wird
//     GENAU die Funktion, die auf dem Schreibtisch die Seite baut.
//     `bauen` erwartet eine Astal.Window; ein Gtk.Window genuegt ihm,
//     weil es davon nur `visible` und `connect` benutzt (siehe das Ende
//     von bauen() in ags-vpn.template) - Astal.Window ihrerseits ruft in
//     ihrem Konstruktor gtk_layer_init_for_window, und das verlangt
//     einen Wayland-Compositor, den es hier nicht gibt.
//
// WELCHE ZEILE UMGELEGT WIRD, UND WARUM DAS EINE ENTSCHEIDUNG IST
//     Die Zeile, die ZEPOS_SCHALTER nennt - im Lauf dieses Baums die
//     IPsec-Verbindung. schalte() verbindet bei ihr NICHT: eine
//     Verbindung, die eine Anmeldung braucht, wird ausgewaehlt und zeigt
//     ihr Formular (siehe "WAS DER SCHALTER BEDEUTET" in
//     ags-vpn.template). Damit misst dieser Lauf genau den Weg, um den
//     es geht - Auswahl und Neuzeichnen -, und startet dabei keinen
//     einzigen Unterprozess, der etwas verbinden koennte.

import { Gtk, Gdk } from "ags/gtk4"
import GLib from "gi://GLib"
import { vpnSeite } from "./widget/VpnManager"

const TRACE = GLib.getenv("ZEPOS_TRACE") ?? ""
const marks: string[] = []

function mark(name: string, value: string): void {
  marks.push(`${name}:${value}`)
}

Gtk.init()

const CSS = GLib.getenv("ZEPOS_CSS") ?? ""
const display = Gdk.Display.get_default()
if (CSS && display) {
  const provider = new Gtk.CssProvider()
  provider.load_from_path(CSS)
  Gtk.StyleContext.add_provider_for_display(
    display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
}

const window = new Gtk.Window({ title: "zepos-vpn-schalter" })
// `as any`: siehe den Kopf - der Typ verlangt eine Astal.Window, der
// KOERPER von bauen() verlangt `visible` und `connect`, und beides hat
// ein Gtk.Window.
const seite = vpnSeite.bauen(window as any, () => {}, () => true)
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

/** Der Text der ersten Beschriftung mit dieser Klasse. */
function text(wurzel: Gtk.Widget, klasse: string): string {
  const treffer = suche(wurzel, (w) => w.has_css_class(klasse))
  return treffer instanceof Gtk.Label ? treffer.get_label() : ""
}

// Die Liste selbst. Gesucht wird ueber ihre Klasse und nicht ueber die
// Reihenfolge der Kinder: `.vpn-connection-list` ist der Name, den die
// Vorlage vergibt, und ein Zaehlen von Kindern maesse den Aufbau der
// Seite statt der Liste.
const liste = suche(seite, (w) => w.has_css_class("vpn-connection-list"))

interface Zeile {
  titel: string
  unter: string
  gewaehlt: boolean
  schalter: Gtk.Switch | null
}

function zeilen(): Zeile[] {
  const gefunden: Zeile[] = []
  let kind = liste ? liste.get_first_child() : null
  while (kind) {
    // Eine Zeile ist, was eine `.zep-row` enthaelt. Die
    // Abschnittsmarke daruber ist eine blosse Gtk.Label und faellt so
    // heraus, ohne dass hier eine Position stuende.
    const rahmen = suche(kind, (w) => w.has_css_class("zep-row"))
    if (rahmen) {
      const schalter = suche(kind, (w) => w instanceof Gtk.Switch)
      gefunden.push({
        titel: text(kind, "zep-row-title"),
        unter: text(kind, "zep-row-sub"),
        gewaehlt: rahmen.has_css_class("active"),
        schalter: schalter as Gtk.Switch | null,
      })
    }
    kind = kind.get_next_sibling()
  }
  return gefunden
}

/** Die Zeilen als eine Zeile Text: Titel|Nebenzeile|Auswahl|Schalter. */
function aufschrift(): string {
  return zeilen().map((z) => [
    z.titel,
    z.unter,
    z.gewaehlt ? "gewaehlt" : "-",
    z.schalter ? (z.schalter.get_active() ? "an" : "aus") : "ohne",
  ].join("|")).join(";")
}

/** Der Text der Abschnittsmarke ueber der Liste, wenn es eine gibt. */
function marke(): string {
  let kind = liste ? liste.get_first_child() : null
  while (kind) {
    if (kind instanceof Gtk.Label) return kind.get_label()
    kind = kind.get_next_sibling()
  }
  return ""
}

const loop = GLib.MainLoop.new(null, false)

// ANLAUF: die Seite fragt beim Sichtbarwerden den Tunnelstand ab
// (updateStatusDisplay, ein Unterprozess), und dessen Antwort zeichnet
// die Liste NEU. Vor dieser Antwort zu messen hiesse, einen Zustand zu
// messen, den niemand zu sehen bekommt - dieselbe Falle, die
// tests/render/test_vpn_breite.py in ihrem Kopf fuer die erste Zuteilung
// beschreibt. 700 ms sind das Vielfache eines Aufrufs, der nur
// "disconnected" druckt; der eigene Takt der Seite steht bei 5000 ms und
// kommt uns nicht dazwischen.
const ANLAUF_MS = 700

// UND EIN ZWEITES ABWARTEN NACH DEM UMLEGEN, aus demselben Grund in die
// andere Richtung: waere die Auswahl nur ein Aufblitzen, das der
// naechste Zeichenlauf wieder einkassiert, stuende sie nach 300 ms nicht
// mehr da. Sofort nachzusehen wuerde genau das nicht bemerken.
const NACHLAUF_MS = 300

GLib.timeout_add(GLib.PRIORITY_DEFAULT, ANLAUF_MS, () => {
  mark("liste", liste ? "da" : "fehlt")
  mark("marke", marke())
  mark("zeilen-vorher", aufschrift())

  const ziel = Number(GLib.getenv("ZEPOS_SCHALTER") ?? "1")
  const zeile = zeilen()[ziel]
  if (!zeile) {
    mark("betaetigt", "keine-zeile")
  } else if (!zeile.schalter) {
    // DER FALL, DEN DIE GEGENPROBE HERSTELLT: eine Zeile ohne
    // Schalter. Sie wird gemeldet und nicht uebergangen - ein Lauf,
    // der stumm nichts umlegt und danach "nichts geaendert" sagt,
    // waere von einem kaputten Schalter nicht zu unterscheiden.
    mark("betaetigt", "kein-schalter")
  } else {
    // GTK4 kennt kein "klick auf einen Schalter" von aussen; was ein
    // Zeigerdruck auslost, ist genau diese Zustandsaenderung, und
    // zepToggle haengt seinen Rueckruf an "notify::active" (siehe
    // ags-kit.template). set_active() geht also durch dieselbe Tuer wie
    // ein Finger.
    zeile.schalter.set_active(true)
    mark("betaetigt", zeile.titel)
  }

  GLib.timeout_add(GLib.PRIORITY_DEFAULT, NACHLAUF_MS, () => {
    mark("zeilen-nachher", aufschrift())
    if (TRACE) {
      GLib.file_set_contents(
        TRACE, new TextEncoder().encode(marks.join("\n") + "\n"))
    }
    print(marks.join("\n"))
    loop.quit()
    return false
  })
  return false
})

loop.run()
