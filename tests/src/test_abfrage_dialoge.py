# SPDX-License-Identifier: GPL-3.0-or-later
"""Ein Dialog, der um Erlaubnis bittet, geht DA auf, WO DER NUTZER IST.

WAS GEMELDET WURDE
    Der Nutzer am 03.09.2026, woertlich: "ausserdem ist mir aufgefallen
    das dialoge garnicht erscheinen beispielsweise dialoge um den pfad
    mit dateien anzugeben oder andere dialog erscheinen garnicht erst".

WAS DER GRUND WAR
    Vier Fensterregeln fuer gcr-prompter, und die vierte lautete
    `workspace 1`. Sie kam aus einem echten Fehler (die Abfrage landete
    auf dem zugeklappten Laptopschirm) und hat ihn gegen einen anderen
    getauscht: wer nicht auf Arbeitsflaeche 1 sass, sah sie nicht.

    `pin on` faengt das NICHT auf. GEMESSEN am Quelltext der Fassung,
    die ZepOS ausliefert (hyprland-0.56.1, src/output/Monitor.cpp:1477):

        // move pinned windows
        for (auto const& w : ...windows()) {
            if (w->m_workspace == POLDWORKSPACE && w->m_pinned)
                w->layoutTarget()->assignToSpace(pWorkspace->m_space);
        }

    Ein gepinntes Fenster wandert nur mit, wenn die Arbeitsflaeche, auf
    der es LIEGT, verlassen wird - nicht, wenn irgendeine andere
    gewechselt wird.

WARUM DIESE ZUSICHERUNG AN DER VORLAGE MISST UND NICHT IM COMPOSITOR
    Ein Lauf im verschachtelten Compositor waere der bessere Beweis und
    ist hier nicht zu haben: gcr-prompter erscheint nur, wenn polkit oder
    der Schluesselbund wirklich nach einem Kennwort fragen, und das
    verlangt einen Systemdienst, den ein Testlauf nicht stellen darf.
    Was PRUEFBAR ist, ist die Regel selbst - und die war der Fehler.
"""
from __future__ import annotations

import re
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[2]
UNIVERSAL = WURZEL / "src" / "templates" / "hyprland-universal-config.template"

# Fensterklassen, die eine FRAGE tragen: ohne eine Antwort darauf geht
# die Arbeit nicht weiter. Deshalb duerfen sie nicht woanders aufgehen.
#
# gcr-prompter    der Schluesselbund und, ueber polkit-gnome, jede
#                 Rechteabfrage - Thema, Sprache, Zeitzone, jede
#                 Einstellung, die der MASCHINE gehoert
# yad             der VPN-Dialog
ABFRAGE_KLASSEN = ("gcr-prompter", "yad")

# Und der Dateidialog, seit dem 03.09.2026. Er traegt keine Frage,
# sondern eine Suche - aber er hat dasselbe Problem: er gehoert nicht
# der Anwendung, die ihn oeffnet, sondern dem Portal, und ohne Regel
# geht er in die Kachelung. GEMELDET: "der order als vault oeffnen
# kommt jetzt ja aber eingerastet und nicht fliegend".
WAEHLER_KLASSE = "xdg-desktop-portal-gtk"


def _zeilen() -> list[str]:
    return [z.strip() for z in UNIVERSAL.read_text(encoding="utf-8").splitlines()
            if z.strip() and not z.lstrip().startswith("#")]


def test_keine_abfrage_wird_auf_eine_feste_arbeitsflaeche_gezwungen():
    """Die Regel, die den Fehler vom 03.09.2026 wieder einbauen wuerde."""
    gezwungen = []
    for zeile in _zeilen():
        if not zeile.startswith("windowrule"):
            continue
        if not any(klasse in zeile for klasse in ABFRAGE_KLASSEN):
            continue
        if re.search(r"\bworkspace\s+\S", zeile):
            gezwungen.append(zeile)

    assert gezwungen == [], (
        "eine Abfrage wird auf eine feste Arbeitsflaeche gezwungen. Wer "
        "nicht dort sitzt, sieht sie nicht - `pin on` holt sie nicht "
        "nach (Monitor.cpp:1477 der ausgelieferten Fassung):\n  "
        + "\n  ".join(gezwungen))


def test_die_abfrage_schwebt_mittig_und_bleibt_beim_flaechenwechsel():
    """Was STATT der Arbeitsflaechenregel dasteht, und dass es dasteht.

    Ohne diese Zusicherung koennte jemand die drei Regeln mit derselben
    Begruendung entfernen, mit der die vierte gefallen ist - und dann
    ginge die Abfrage in der Kachelung auf, mitten in der Anordnung des
    Nutzers.
    """
    regeln = [z for z in _zeilen()
              if z.startswith("windowrule") and "gcr-prompter" in z]
    assert regeln, "es gibt keine einzige Regel fuer die Rechteabfrage"

    zusammen = " ".join(regeln)
    for eigenschaft in ("float on", "center on", "pin on"):
        assert eigenschaft in zusammen, (
            f"der Rechteabfrage fehlt {eigenschaft!r}: {regeln}")


def test_die_zusicherung_wuerde_die_geloeschte_zeile_wiedererkennen():
    """Ein Test, der nichts findet, ist gruen. Also der Gegenbeweis:
    die Zeile von damals, woertlich, muss auffallen."""
    damals = "windowrule = match:class ^(gcr-prompter)$, workspace 1"
    assert re.search(r"\bworkspace\s+\S", damals), (
        "das Muster erkennt die Zeile nicht mehr, die den Fehler "
        "ausgeloest hat - dann sagt der Test oben nichts aus")
    assert any(klasse in damals for klasse in ABFRAGE_KLASSEN)


def test_der_dateidialog_des_portals_schwebt():
    """Obsidian ist Electron, und Electron fragt fuer "Ordner oeffnen"
    das Portal. Das Fenster gehoert damit xdg-desktop-portal-gtk.

    Die Klasse ist nicht geraten: sie steht im Programm selbst
    (`strings /usr/lib/xdg-desktop-portal-gtk`), neben seinem
    D-Bus-Namen org.freedesktop.impl.portal.desktop.gtk.
    """
    regeln = [z for z in _zeilen()
              if z.startswith("windowrule") and WAEHLER_KLASSE in z]
    assert regeln, (
        f"es gibt keine Regel fuer {WAEHLER_KLASSE} - der Dateidialog "
        f"jeder Anwendung, die das Portal fragt, geht dann in die "
        f"Kachelung")

    zusammen = " ".join(regeln)
    for eigenschaft in ("float on", "center on"):
        assert eigenschaft in zusammen, (
            f"dem Dateidialog fehlt {eigenschaft!r}: {regeln}")
    assert "size " in zusammen, (
        "der Dateidialog bekommt keine Groesse - ein Waehler ist eine "
        "Liste, und zu klein heisst blaettern, wo man suchen will")


def test_der_dateidialog_wird_nicht_auf_eine_arbeitsflaeche_gezwungen():
    """Dieselbe Falle wie bei der Rechteabfrage, an einem zweiten
    Fenster: er muss dort aufgehen, wo der Nutzer gerade sucht."""
    gezwungen = [z for z in _zeilen()
                 if z.startswith("windowrule") and WAEHLER_KLASSE in z
                 and re.search(r"\bworkspace\s+\S", z)]
    assert gezwungen == [], (
        f"der Dateidialog wird auf eine feste Arbeitsflaeche gezwungen: "
        f"{gezwungen}")
