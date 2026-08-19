# SPDX-License-Identifier: GPL-3.0-or-later
"""Kasten in Kasten: kein Bauteil des Kits als Kind eines anderen, wenn
beide ihre eigene Flaeche malen.

GEMELDET am 19.08.2026, woertlich: "komischerweise waren die buttons der
sidebar die links sozusagen doppeltzeilige und irgendwie kasten in kasten
verschachtelt wodurch alles verbuggt aussah".

GEFUNDEN am selben Tag, in genau DREI Vorlagen - alle drei mit derselben
Zeile, weil eine den Bauplan der anderen wortwoertlich zitiert
(ags-network.template:462 "dieselbe Zusammensetzung wie createDeviceRow()
in ags-bluetooth.template", ags-bluetooth.template:481 "dieselbe
Zusammensetzung wie createNetworkRow()"):

    zepSidebar()       ags-templates/ags-kit.template:199
    createNetworkRow()  ags-templates/ags-network.template:496
    createDeviceRow()   ags-templates/ags-bluetooth.template:499

    const knopf = zepButton("", "umrandet", aktion)
    knopf.set_child(zepRow({ ... }))

DIE ZAHLEN, mit denen die REPARATUR (nicht dieser Auftrag) arbeiten kann,
bei Vorgabegroesse (Faktor SCALE_DEFAULT = 20/13, src/sizes.py):

    Aussen  zepButton("umrandet")   min-height  49px (Grundwert 32)
                                    border-radius  8px (RADIUS_CONTROL, Grundwert 5)
                                    padding     0 25px (nur waagerecht, SPACE_16)
                                    border      1px, sichtbar (immer, nicht nur bei :hover)
                                    background  rgba(surface, 0.55) (immer)
    Innen   zepRow                 min-height  74px (Grundwert 48) - GROESSER als aussen!
                                    border-radius 12px (RADIUS_CARD, Grundwert 8) - GROESSER als aussen!
                                    padding     0 18px (nur waagerecht, SPACE_12)
                                    border-left 3px, reserviert IMMER (auch unmarkiert)

    Weil der Knopf 0 Polsterung senkrecht traegt, sein Kind (die Zeile)
    aber 74px verlangt, entscheidet die INNERE Huelle die Hoehe - nicht
    die aeussere, "richtige" Knopfhoehe. Und weil die innere Rundung (12)
    groesser ist als die aeussere (8), bei 25px waagerechtem und 0px
    senkrechtem Abstand zwischeneinander, liegen die beiden Randlinien
    nie konzentrisch - sichtbar wird das, sobald die innere Zeile eine
    ANDERE Farbe traegt als der Knopf (":hover", "ausgewaehlt"/".active"):
    dann zeigt sich eine zweite, kleinere abgerundete Flaeche INNERHALB
    der ersten. GEMESSEN im Bild der Seitenleiste (Aufgabe 15,
    Bericht dieser Aufgabe): genau dort, wo der aktive Eintrag der Schale
    seine Randfarbe wechselt, wird die Doppel-Huelle sichtbar.

WARUM EIN REGULAERER AUSDRUCK UND KEIN AST
    Dieselbe Entscheidung wie test_schale.py::test_kein_fenster_baut...:
    die Vorlagen sind TypeScript-AEHNLICH, aber esbuild/AGS verarbeitet
    sie erst NACH der Platzhalter-Ersetzung - ein echter TS-Parser haette
    hier {{STYLE_*}}-Platzhalter zu verdauen, fuer die er nicht gebaut
    ist. Ein Ausdruck, der beide Zeilen (zepButton(...) und ein
    set_child(zepRow(...)) - ODER ein set_child(name) mit `name` als
    zepRow-Ergebnis - INNERHALB WENIGER ZEILEN DANACH) findet, reicht,
    weil das Muster selbst nur drei Zeilen lang ist.
"""
import re
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[2]
VORLAGEN = WURZEL / "src" / "templates"

# EIN KIT-BAUTEIL, DAS SEINE EIGENE FLAECHE MALT
#
# zepButton und zepRow tragen BEIDE eine eigene Klasse mit background/
# border/border-radius in ags-style.template (.zep-btn* / .zep-row) -
# beide also "Flaechen im Sinne dieses Waechters". zepToggle, zepDivider,
# zepSectionLabel malen keine eigene Flaeche (kein background, keine
# border-radius auf sich selbst) und sind hier absichtlich aussen vor:
# ein zepToggle als `ende` einer zepRow (siehe zepStateHeader) ist keine
# Verschachtelung von ZWEI Flaechen, weil nur eine der beiden eine ist.
FLAECHEN_BAUTEILE = ("zepButton", "zepRow")

# `name = zepButton(...)` ODER `const name = zepButton(...)`, gefolgt -
# in den naechsten hoechstens 6 Zeilen - von
# `name.set_child(zepRow(` ODER `name.set_child(irgendwas(...))`, wobei
# `irgendwas` seinerseits eine Funktion ist, die `zepRow(` in ihrem
# EIGENEN Rumpf aufruft (das faengt den Fall createDeviceRow(): eine
# separate `rowContent = (u) => zepRow({...})`-Funktion, deren
# Rueckgabewert erst an set_child geht).
ZUWEISUNG = re.compile(
    r"(?:const|let)\s+(\w+)\s*=\s*zepButton\s*\(")


def _kit_verschachtelungen(text: str) -> list[str]:
    """Jede Stelle, an der ein zepButton-Ergebnis eine zepRow als Kind
    bekommt - direkt oder ueber eine Zwischenfunktion, die selbst nichts
    als eine zepRow zurueckgibt."""
    treffer = []
    zeilen = text.splitlines()
    for zeilennr, zeile in enumerate(zeilen):
        gefunden = ZUWEISUNG.search(zeile)
        if not gefunden:
            continue
        name = gefunden.group(1)
        # 20 Zeilen und nicht 8: in createNetworkRow() (ags-network.
        # template) liegen 12 Zeilen zwischen "const row = zepButton("
        # und "row.set_child(zepRow(" - der Klickrumpf dazwischen ist
        # selbst mehrzeilig (drei Verzweigungen: verbunden trennen,
        # gesichert verbinden, offen verbinden).
        fenster = "\n".join(zeilen[zeilennr:zeilennr + 20])

        # Fall 1: `name.set_child(zepRow(` direkt.
        if re.search(rf"{re.escape(name)}\.set_child\s*\(\s*zepRow\s*\(",
                     fenster):
            treffer.append(f"Zeile {zeilennr + 1}: {name} = zepButton(...), "
                           f"danach {name}.set_child(zepRow(...))")
            continue

        # Fall 2: `name.set_child(sonstwas(...))`, wobei `sonstwas` eine
        # eigene Funktion ist, deren Rumpf `zepRow(` aufruft - der
        # Kunstgriff aus createDeviceRow() (rowContent).
        indirekt = re.search(
            rf"{re.escape(name)}\.set_child\s*\(\s*(\w+)\s*\(", fenster)
        if indirekt:
            zwischenname = indirekt.group(1)
            zwischen_def = re.search(
                rf"(?:const|let)\s+{re.escape(zwischenname)}\s*=[^\n]*"
                r"zepRow\s*\(", text)
            if zwischen_def:
                treffer.append(
                    f"Zeile {zeilennr + 1}: {name} = zepButton(...), danach "
                    f"{name}.set_child({zwischenname}(...)) - und "
                    f"{zwischenname} baut selbst eine zepRow")
    return treffer


def test_kein_zepbutton_umschliesst_eine_zeprow():
    """Der Waechter selbst.

    FAELLT HEUTE (19.08.2026) DREIFACH - und das ist der Punkt: dieser
    Test ist ein MESSGERAET fuer Aufgabe 15, keine Reparatur. Er bleibt
    absichtlich rot, bis eine spaetere Aufgabe die Seitenleiste und die
    beiden Listenzeilen auf EINE Huelle umstellt (entweder ein neues,
    eigenstaendiges "anklickbare Zeile"-Bauteil im Kit, oder zepRow
    bekommt selbst eine Klick-Faehigkeit und der umschliessende
    zepButton faellt weg).
    """
    fundstellen: dict[str, list[str]] = {}
    for vorlage in sorted(VORLAGEN.glob("ags-*.template")):
        text = vorlage.read_text(encoding="utf-8")
        treffer = _kit_verschachtelungen(text)
        if treffer:
            fundstellen[vorlage.name] = treffer

    if not fundstellen:
        return

    meldung = ["mindestens ein zepButton umschliesst eine zepRow - beide "
              "malen ihre eigene Flaeche (background/border/"
              "border-radius in ags-style.template), verschachtelt "
              "entsteht 'Kasten in Kasten':"]
    gesamt = 0
    for datei, treffer in fundstellen.items():
        meldung.append(f"  {datei}:")
        for zeile in treffer:
            meldung.append(f"    {zeile}")
            gesamt += 1
    meldung.append(f"  ({gesamt} Fundstelle(n) in {len(fundstellen)} "
                   "Vorlage(n))")
    assert False, "\n".join(meldung)


def test_dieser_waechter_wuerde_ueberhaupt_ausloesen():
    """Ein Waechter, der nie ausloest, ist kein Waechter (derselbe
    Grundsatz wie in test_schale.py). Gegen eine Zeile gehalten, die
    GENAU das Muster von zepSidebar() nachstellt."""
    nachgestellt = '''
    const knopf = zepButton("", "umrandet", () => aufSeite(eintrag.id))
    knopf.set_child(zepRow({
      symbol: eintrag.symbol,
      titel: eintrag.titel,
    }))
    '''
    assert _kit_verschachtelungen(nachgestellt)

    # Und die indirekte Form aus createDeviceRow(): eine Zwischenfunktion,
    # die selbst eine zepRow baut.
    nachgestellt_indirekt = '''
    const rowContent = (unterzeile: string) => zepRow({
      symbol: device.connected ? ICONS.connected : ICONS.bluetooth,
      titel: device.name,
      unterzeile,
    })
    const row = zepButton("", "umrandet", async () => {
      row.set_child(rowContent("Verbinde ..."))
    })
    '''
    assert _kit_verschachtelungen(nachgestellt_indirekt)

    # Ein zepButton OHNE zepRow-Kind (die ganz normale Mehrzahl der
    # Aufrufe - ein Textknopf) soll NICHT anschlagen.
    unauffaellig = '''
    const saveBtn = zepButton("", "voll", async () => {
      await save()
    })
    '''
    assert not _kit_verschachtelungen(unauffaellig)


def test_die_drei_bekannten_fundstellen_sind_genau_diese():
    """Nagelt die AUSGANGSLAGE fest (Aufgabe 15, 19.08.2026): drei
    Vorlagen, eine Fundstelle je Vorlage. Wird diese Zahl kleiner, ist
    eine Fundstelle repariert - wird sie GROESSER, kopiert jemand das
    Muster ein viertes Mal, waehrend es noch kaputt ist.
    """
    erwartet = {
        "ags-kit.template",
        "ags-network.template",
        "ags-bluetooth.template",
    }
    tatsaechlich = set()
    for vorlage in sorted(VORLAGEN.glob("ags-*.template")):
        text = vorlage.read_text(encoding="utf-8")
        if _kit_verschachtelungen(text):
            tatsaechlich.add(vorlage.name)

    assert tatsaechlich == erwartet, (
        f"erwartet {sorted(erwartet)}, gefunden {sorted(tatsaechlich)} - "
        "siehe Bericht zu Aufgabe 15 fuer den Stand vom 19.08.2026")
