// SPDX-License-Identifier: GPL-3.0-or-later
//
// Das Kind zu tests/src/test_sprachwechsel.py.
//
// Es meldet ZEILEN der Form name=wert, weil der Elternprozess sie so
// einliest - dieselbe Form wie die uebrigen Messkinder dieses Baums.
// Was es meldet, entscheidet ZEPOS_SPRACHPROBE_FENSTER: ohne die
// Variable nur die vier Zeichenketten, mit ihr die Messung an einem
// wirklich gezeichneten Fenster. Ein Kind und nicht zwei, weil beide
// dasselbe gebuendelte utils/i18n.ts brauchen und `ags bundle` ueber
// eine Sekunde kostet.
import Gettext from "gettext"
import GLib from "gi://GLib"

import { DOMAIN, _, spracheDerMaschine, spracheAnwenden } from "./utils/i18n"

const PROBE = "Disk space"

// Was in der Maschinendatei steht, und was danach wirklich gilt.
print(`maschine=${spracheDerMaschine()}`)
print(`angewandt=${spracheAnwenden() ?? ""}`)
print(`katalog=${_(PROBE)}`)

const FENSTER = GLib.getenv("ZEPOS_SPRACHPROBE_FENSTER")
if (FENSTER) {
  // Der zweite Teil: bleibt eine GEZEICHNETE Beschriftung stehen?
  //
  // Das Fenster muss wirklich stehen, bevor gemessen wird - ein Widget,
  // das nie realisiert wurde, beweist ueber gezeichnete Beschriftungen
  // nichts. Deshalb present(), ein Durchlauf der Hauptschleife und
  // get_realized() in der Meldung.
  const Gtk = (await import("gi://Gtk?version=4.0")).default
  Gtk.init()

  // GEMESSEN WIRD HIER AUCH, OB Gtk.init() DEN KATALOG WIEDER UMWIRFT.
  //
  // gtk_init() ruft setlocale(LC_ALL, "") - es holt die Sprachumgebung
  // also aus der UMGEBUNG, und die ist in einer laufenden Sitzung eine
  // Abschrift von /etc/locale.conf von der Anmeldung. Wenn das die
  // Arbeit von spracheAnwenden() rueckgaengig machte, spraeche die
  // Schale nach dem Neustart wieder die alte Sprache - und niemand
  // saehe, warum.
  print(`nachInit=${_(PROBE)}`)

  const fenster = new Gtk.Window({ title: "Sprachprobe" })
  const kasten = new Gtk.Box({ orientation: Gtk.Orientation.VERTICAL })
  const alt = new Gtk.Label({ label: _(PROBE) })
  kasten.append(alt)
  fenster.set_child(kasten)
  fenster.present()

  const schleife = GLib.MainLoop.new(null, false)
  GLib.timeout_add(GLib.PRIORITY_DEFAULT, 400, () => {
    print(`gezeichnet=${fenster.get_realized()}`)
    print(`A=${alt.get_label()}`)

    Gettext.setlocale(Gettext.LocaleCategory.MESSAGES, FENSTER)

    print(`B=${_(PROBE)}`)
    print(`C=${alt.get_label()}`)

    const neu = new Gtk.Label({ label: _(PROBE) })
    kasten.append(neu)
    print(`D=${neu.get_label()}`)

    schleife.quit()
    return GLib.SOURCE_REMOVE
  })
  schleife.run()
}

// DOMAIN wird eingelesen, damit der Buendler den Export nicht wegwirft
// und damit hier steht, gegen WELCHE Domaene gemessen wurde.
print(`domaene=${DOMAIN}`)
