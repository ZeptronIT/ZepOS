// SPDX-License-Identifier: GPL-3.0-or-later
//
// Das Zahnrad in der VPN-Listenzeile - betaetigt statt betrachtet.
//
// WARUM DIESES KIND EXISTIERT (02.09.2026)
//     Nutzermeldung, woertlich: "ich kann uebrigens in der liste kein
//     einstellung icon pro vpn sehen um direkt zur vpn zu gelangen
//     stattdessen muss ich es aktivieren und dann komme ich auf die vpn
//     bzw einstellungen statt direkt dort hinzugelangen" - und
//     praezisiert: "ich will neben dem toggle auch ein icon fuer
//     einstellung haben das zahnrad".
//
// DIE EINE FRAGE, AN DER ALLES HAENGT: WELCHE KENNUNG
//     Das Zahnrad ruft `openVpnSettings(eintrag.id)`. Die zwei
//     Zahnraeder in der EINZELHEIT rufen `openVpnSettings(gewaehlteId)`,
//     und das ist dort richtig - dort gibt es nur eine gemeinte
//     Verbindung. In der LISTE ist es falsch: `gewaehlteId` ist die
//     Verbindung, die die Einzelheit zeigt, nicht die, deren Zahnrad
//     man drueckt.
//
//     Damit dieser Unterschied MESSBAR ist, drueckt dieses Kind das
//     Zahnrad der ZWEITEN Zeile, waehrend `active` in der
//     Einstellungsdatei auf die ERSTE zeigt. Stuende im Quelltext
//     `gewaehlteId`, kaeme `c1` heraus statt `c2` - beim Zahnrad der
//     ersten Zeile waeren beide gleich, und die Messung waere blind.
//
// WIE DIE WIRKUNG SICHTBAR WIRD, OHNE ETWAS ANZUFASSEN
//     `openVpnSettings` setzt `ags request vpn-settings:<kennung>` ab.
//     Der Test legt dafuer eine ATTRAPPE namens `ags` vor /usr/bin in
//     den PATH, die ihre Aufrufzeile in eine Datei schreibt. Damit steht
//     die Kennung hinterher Zeichen fuer Zeichen da - und es wird
//     niemals ein echtes `ags request` abgesetzt, das in der Sitzung des
//     Nutzers landen koennte.
//
//     Dazu kommt `schliessen`: openVpnSettings ruft es als Letztes.
//     Dieses Kind reicht dafuer keinen leeren Rumpf herein, sondern
//     einen, der es ins Fahrtenbuch schreibt - so ist belegt, dass der
//     Griff bis zum Ende durchgelaufen ist und nicht auf halbem Weg
//     geworfen hat.
//
// WAS DAS ZAHNRAD NICHT TUN DARF
//     Nicht schalten (kein `notify::active`) und nicht in die Einzelheit
//     blaettern (Liste bleibt sichtbar). Beides wird VOR und NACH dem
//     Druck abgelesen, nicht nur danach - ein Zustand, der schon vorher
//     so war, belegt nichts.

import { Gtk } from "ags/gtk4"
import GLib from "gi://GLib"
import { vpnSeite } from "./widget/VpnManager"

const TRACE = GLib.getenv("ZEPOS_TRACE") ?? ""
const marks: string[] = []

function mark(name: string, value: string): void {
  marks.push(`${name}:${value}`)
}

// Was betaetigt wird: "zahnrad", "schalter" oder "nichts".
//
//     "nichts" ist die GEGENPROBE und kein Leerlauf: ohne sie waere
//     "nach dem Druck aufs Zahnrad steht eine Anfrage in der Datei"
//     auch dann erfuellt, wenn die Seite beim Aufbauen von sich aus
//     eine absetzt.
const ZIEL = GLib.getenv("ZEPOS_ZIEL") ?? "zahnrad"

Gtk.init()

const start = GLib.get_monotonic_time()
const buch: string[] = []
function eintragen(was: string): void {
  const ms = Math.round((GLib.get_monotonic_time() - start) / 1000)
  buch.push(`${ms}ms ${was}`)
}

const window = new Gtk.Window({ title: "ZEPOS-VPN-ZAHNRAD" })
// `as any`: der Typ verlangt eine Astal.Window, der Koerper von bauen()
// verlangt `visible` und `connect` - beides hat ein Gtk.Window. Siehe
// vpn_schalter_child.tsx.
//
// Der zweite Parameter ist `schliessen`. KEIN leerer Rumpf: siehe oben.
const seite = vpnSeite.bauen(window as any,
                             () => { eintragen("SCHLIESSEN") },
                             () => true)
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

/** Liegt `w` unter einem Widget mit der Klasse `.zep-row-click`? */
function unterDerHuelle(w: Gtk.Widget | null): string {
  let lauf: Gtk.Widget | null = w
  while (lauf) {
    if (lauf.has_css_class("zep-row-click")) return "ja"
    lauf = lauf.get_parent()
  }
  return "nein"
}

const liste = suche(seite, (w) => w.has_css_class("vpn-connection-list"))
const formular = suche(seite, (w) => w.has_css_class("vpn-form"))

function sichtbar(w: Gtk.Widget | null): string {
  if (!w) return "fehlt"
  // is_visible() und nicht get_visible(): der Wert, der die VORFAHREN
  // einbezieht. Siehe vpn_ansicht_child.tsx.
  return w.is_visible() ? "ja" : "nein"
}

/** Liste|Formular - der Zustand der Seite in einer Zeile. */
function lage(): string {
  return `${sichtbar(liste)}|${sichtbar(formular)}`
}

/** Die Zeilen der Liste: die Kinder mit der Klasse `.zep-row`.
 *
 * Ueber die Klasse und nicht ueber die Reihenfolge: das erste Kind der
 * Liste ist die Abschnittsmarke (zepSectionLabel), nicht eine Zeile.
 */
function zeilen(): Gtk.Widget[] {
  const gefunden: Gtk.Widget[] = []
  let kind = liste ? liste.get_first_child() : null
  while (kind) {
    if (kind.has_css_class("zep-row")) gefunden.push(kind)
    kind = kind.get_next_sibling()
  }
  return gefunden
}

const loop = GLib.MainLoop.new(null, false)

// Grosszuegig: die Seite startet fuer ihre Auskunft einen Unterprozess
// und zeichnet die Liste erst danach.
const T_MESSEN = 2500      // Aufbau ablesen
const T_DRUCK = 3000       // betaetigen
const T_LESEN = 4200       // Wirkung ablesen
const T_ENDE = 4700

GLib.timeout_add(GLib.PRIORITY_DEFAULT, T_MESSEN, () => {
  const reihen = zeilen()
  mark("ziel", ZIEL)
  mark("zeilen-anzahl", String(reihen.length))
  mark("lage-vorher", lage())

  // ---- JE ZEILE, UND NICHT NUR AN DER ERSTEN ------------------------
  //
  //     Der Nutzer will das Zahnrad "pro vpn". Eine Liste, in der die
  //     erste Zeile eines hat und die zweite nicht, waere schlimmer als
  //     gar keines - sie saehe nach einer Regel aus, die es nicht gibt.
  //     Darum wird je Zeile abgelesen, und die Marken tragen die Werte
  //     ALLER Zeilen, mit Komma getrennt.
  const zahnraeder: string[] = []
  const reihenfolgen: string[] = []
  const huellenlage: string[] = []
  const namen: string[] = []
  for (const zeile of reihen) {
    const gruppe = suche(zeile, (w) => w.has_css_class("vpn-row-ende"))
    const zahnrad = suche(zeile, (w) => w.has_css_class("vpn-row-settings"))
    zahnraeder.push(zahnrad ? "ja" : "nein")
    huellenlage.push(unterDerHuelle(zahnrad))
    namen.push(zahnrad ? (zahnrad.get_tooltip_text() ?? "") : "")

    // DIE REIHENFOLGE IN DER GRUPPE, und sie ist eine Ansage: "Symbol -
    // Name/Unterzeile - ZAHNRAD - Schalter". Der Schalter bleibt an der
    // Kante, wo er schon war, weil er das ist, was oft gedrueckt wird.
    const teile: string[] = []
    let kind = gruppe ? gruppe.get_first_child() : null
    while (kind) {
      teile.push(kind.has_css_class("vpn-row-settings") ? "zahnrad"
        : kind instanceof Gtk.Switch ? "schalter"
          : beschreibe(kind))
      kind = kind.get_next_sibling()
    }
    reihenfolgen.push(teile.join(">"))
  }
  mark("zahnrad-je-zeile", zahnraeder.join(","))
  mark("zahnrad-unter-huelle", huellenlage.join(","))
  mark("ende-reihenfolge", reihenfolgen.join(","))
  mark("zahnrad-name", namen.join(" / "))

  // ---- Das Ziel der ZWEITEN Zeile -----------------------------------
  //
  //     Die zweite, weil `active` in der Einstellungsdatei auf die
  //     ERSTE zeigt - siehe den Dateikopf. Nur so unterscheidet die
  //     Messung `eintrag.id` von `gewaehlteId`.
  const zweite = reihen.length > 1 ? reihen[1] : null
  const zielZahnrad = suche(zweite, (w) => w.has_css_class("vpn-row-settings"))
  const zielSchalter = suche(zweite, (w) => w instanceof Gtk.Switch)
  mark("ziel-zahnrad", beschreibe(zielZahnrad))
  mark("ziel-schalter", beschreibe(zielSchalter))
  mark("ziel-titel", beschreibe(
    suche(zweite, (w) => w.has_css_class("zep-row-title"))))

  // Ab jetzt wird mitgeschrieben. NICHT frueher: das Neuzeichnen der
  // Liste baut Schalter und wuerde das Fahrtenbuch mit seinen eigenen
  // notify::active fuellen.
  if (zielSchalter) {
    zielSchalter.connect("notify::active", () => eintragen("SCHALTER-notify"))
  }
  if (zielZahnrad) {
    (zielZahnrad as Gtk.Button).connect("clicked",
      () => eintragen("ZAHNRAD-clicked"))
  }

  GLib.timeout_add(GLib.PRIORITY_DEFAULT, T_DRUCK - T_MESSEN, () => {
    // `emit("clicked")` bzw. `activate()` und kein Zeigerereignis: auf
    // dieser Maschine gibt es keines zu erzeugen (Gdk.ButtonEvent hat in
    // GTK4 keinen Konstruktor). WELCHES Widget ein Zeigerdruck traefe,
    // misst tests/render/test_zeprow_verschachtelung.py mit pick() und
    // mit echten Tasten. Hier wird gemessen, was der GRIFF TUT, wenn er
    // ausgeloest wird - und das ist dieselbe Handlerkette.
    if (ZIEL === "zahnrad" && zielZahnrad) {
      (zielZahnrad as Gtk.Button).emit("clicked")
    } else if (ZIEL === "schalter" && zielSchalter) {
      (zielSchalter as Gtk.Switch).set_active(
        !(zielSchalter as Gtk.Switch).get_active())
    }
    eintragen(`--gedrueckt:${ZIEL}--`)
    return false
  })
  return false
})

GLib.timeout_add(GLib.PRIORITY_DEFAULT, T_LESEN, () => {
  mark("lage-nachher", lage())
  mark("fahrtenbuch", buch.join(" | "))
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
