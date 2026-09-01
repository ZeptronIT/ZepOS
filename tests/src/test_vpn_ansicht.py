# SPDX-License-Identifier: GPL-3.0-or-later
"""Die VPN-Seite ist eine Liste, und ein Klick fuehrt in die Einzelheit.

DER AUFTRAG, WOERTLICH (01.09.2026)
    "auch wenn ich die liste sehen will: es wird wie in einer reihe
     aufgelistet statt eine liste, und auch da viel zu wenig platz. ...
     ich will eine reine liste bei vpn sehen, und bei klick auf das item
     einer vpn oder 'neu erstellen' will ich auf die details kommen."

WAS VORHER DASTAND, UND WARUM ES ZU WENIG PLATZ WAR
    `mainBox` in ags-vpn.template hing DREI Kaesten untereinander:
    `listenBox`, `connectedView`, `formView`. Zwei davon waren immer
    zugleich sichtbar - die Liste UND eine der beiden Einzelheiten -,
    und beide teilten sich die Hoehe EINER Schalenseite. Mit drei
    Verbindungen blieb fuer keines von beiden genug.

    Die Aufteilung war also nicht falsch gebaut, sie war falsch
    GESCHNITTEN: nebeneinander (waagerecht im Einstellungsfenster) und
    uebereinander (senkrecht auf der Schalenseite) teilen sich zwei
    Ansichten den Platz. Nacheinander teilen sie ihn nicht.

WARUM EIN KIND UND KEIN TEST AUF DEN QUELLTEXT
    Dass in der Vorlage zwei Huellen stehen, kann ein Leser bezeugen.
    Dass ein Klick auf eine Zeile die eine aus- und die andere
    einblendet, und dass der Zurueck-Knopf zurueckfuehrt, kann er nicht:
    beides passiert in dem Prozess, der die Widgets gebaut hat.
    tests/src/vpn_ansicht_child.tsx baut sie und klickt wirklich.

WOHER DER AUFBAU KOMMT
    `_baue`/`_lauf`/`Lauf` aus tests/src/test_vpn_schalter.py - dieselbe
    Attrappe fuer vpn.py, dieselbe Einstellungsdatei, derselbe
    broadwayd. Abgeschrieben wird nichts: zwei Kopien einer
    Anzeigeserver-Startroutine sind zwei Kopien, die auseinanderlaufen,
    und die, die nicht angefasst wurde, misst dann still etwas anderes.

SICHERHEIT
    Wie dort: eigener Anzeigeserver in einem eigenen XDG_RUNTIME_DIR,
    kein Sitzungsbus, und `{{ZEPOS_SYSTEM_ROOT}}` zeigt auf ein
    Wegwerfverzeichnis mit einem vpn.py, das "disconnected" druckt. Das
    echte vpn.py laeuft nicht, also fragt niemand NetworkManager oder
    strongSwan etwas.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]

# Dieselbe Art, eine Nachbardatei zu leihen, wie sie
# tests/src/test_vpn_liste.py fuer test_ags_i18n.py benutzt.
_SPEC = importlib.util.spec_from_file_location(
    "_vpn_schalter_harness",
    Path(__file__).resolve().parent / "test_vpn_schalter.py")
_HARNESS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HARNESS)

pytestmark = pytest.mark.allow_subprocess

KIND = Path(__file__).resolve().parent / "vpn_ansicht_child.tsx"

# Die Zeile, die das Kind anklickt: die zweite (Arbeit, IPsec) - dieselbe
# wie in test_vpn_schalter.py, damit beide Messungen denselben Weg
# nehmen und ein Unterschied zwischen ihnen etwas bedeutet.
GEKLICKT = 1


@pytest.fixture(scope="module")
def lauf(tmp_path_factory):
    """Ein Lauf, drei Messpunkte: Anfang, nach dem Klick, nach zurueck.

    Modulweit, weil `ags bundle` und der Anzeigeserver zusammen mehrere
    Sekunden brauchen und jede Zusicherung darunter dieselbe Messung
    liest.
    """
    return _HARNESS._lauf(tmp_path_factory.mktemp("vpn-ansicht"), kind=KIND)


def test_die_seite_hat_liste_und_zurueck_knopf(lauf):
    """Die Gegenprobe zuerst.

    Alles darunter liest Sichtbarkeiten. Faende das Kind die Liste oder
    den Zurueck-Knopf gar nicht, waeren die Lagen unten `fehlt|fehlt` -
    und eine Zusicherung, die nur "nicht sichtbar" verlangt, waere damit
    erfuellt, ohne dass es die Ansicht gibt.
    """
    assert lauf.marke("liste") == "da", lauf.bericht
    assert lauf.marke("zurueck-knopf") == "da", lauf.bericht
    assert lauf.marke("zeilen") == "2", lauf.bericht


def test_am_anfang_steht_nur_die_liste(lauf):
    """"ich will eine reine liste bei vpn sehen."

    Die Liste ist sichtbar, das Formular nicht - und das ist der ganze
    Unterschied zum Zustand vom 22.08.2026, in dem BEIDE dastanden und
    sich die Hoehe teilten.
    """
    assert lauf.marke("lage-anfang") == "ja|nein", lauf.bericht


def test_ein_klick_auf_eine_zeile_fuehrt_in_die_einzelheit(lauf):
    """"bei klick auf das item einer vpn ... will ich auf die details
    kommen."

    Nach dem Klick ist es genau andersherum: das Formular steht da, die
    Liste nicht. Geklickt wird der Gtk.Button, an dem zepRow seine
    `aktion` haengt - derselbe Weg, den ein Finger nimmt.
    """
    assert lauf.marke("geklickt") == f"zeile-{GEKLICKT}", lauf.bericht
    assert lauf.marke("lage-nach-klick") == "nein|ja", lauf.bericht


def test_der_zurueck_knopf_fuehrt_zur_liste(lauf):
    """Und zurueck.

    Ohne diese Zusicherung waere die Einzelheit eine Sackgasse: der
    Nutzer kaeme hinein und nur ueber das Schliessen der ganzen Schale
    wieder heraus.
    """
    assert lauf.marke("zurueck") == "geklickt", lauf.bericht
    assert lauf.marke("lage-nach-zurueck") == "ja|nein", lauf.bericht


# --------------------------------------------------------------------
# Der Platz - mit DREI Eintraegen, weil danach gefragt wurde
# --------------------------------------------------------------------

# Was die Schale einer Seite laesst, und die Zahl ist NICHT hier
# ausgerechnet: sie steht bei `fuelltDieSprosse` in
# ags-overlay-utils.template, wo sie bei jedem Aufgehen GEMESSEN wird.
#
#     Sprosse L (src/sizes.py, MODAL_WIDTHS)                  880
#     .overlay-outer, Rahmen 1px, zweimal                      -2
#     senkrechte Bildlaufleiste (immer reserviert)            -24
#                                                            ----
#     was der Rumpf der Schale bekommt                         854
#     zepSidebar, 208 plus ihre 1px-Randlinie                -209
#                                                            ----
#     was EINE Schalenseite bekommt                            645
#
# Dieselbe 645 nennt der Kommentar in ags-vpn.template seit dem
# 20.08.2026 ("immer noch weit unter dem, was die Schale ihr laesst
# (645 auf 1920x1080)").
SEITENBREITE = 645


@pytest.fixture(scope="module")
def lauf_drei(tmp_path_factory):
    """Derselbe Lauf, aber mit drei Verbindungen."""
    return _HARNESS._lauf(tmp_path_factory.mktemp("vpn-ansicht-drei"),
                          kind=KIND, dritte=True)


def test_drei_verbindungen_geben_drei_zeilen(lauf_drei):
    """Die Gegenprobe fuer die Messung darunter.

    Ein Platzbedarf fuer eine Liste, die in Wahrheit zwei Zeilen hat,
    waere eine Zahl ueber etwas anderes.
    """
    assert lauf_drei.marke("zeilen") == "3", lauf_drei.bericht
    assert lauf_drei.marke("lage-anfang") == "ja|nein", lauf_drei.bericht


def test_die_liste_mit_drei_eintraegen_passt_in_die_seite(lauf_drei):
    """Was die Liste verlangt, gegen das, was die Seite hat.

    GEMESSEN am 01.09.2026: 335x156 fuer drei Eintraege, gegen 645
    Punkte Seitenbreite.

    DIESE ZAHL IST DIE UNTERE SCHRANKE UND NICHT DIE WAHRE BREITE, und
    das soll dastehen: dieser Aufbau laedt KEIN Stylesheet (ZEPOS_CSS
    ist nicht gesetzt, siehe das Kind), die Zeilen tragen also
    GTK-Vorgabepolster und -schriften statt der eigenen. Was hier
    gemessen wird, ist der Anspruch des Bauplans; was auf dem Schirm
    steht, misst tests/render/test_vpn_liste_platz.py am echten
    Compositor.

    Trotzdem sagt sie etwas: sie faellt um, sobald jemand ein breites,
    nicht dehnbares Bauteil in die Zeile setzt - genau der Fehler, den
    das Einstellungsfenster am 18.08.2026 hatte.

    KEIN DECKEL AUF DIE HOEHE: die Schale rollt senkrecht (die Fabrik
    setzt `vscrollbar_policy: AUTOMATIC`), eine lange Liste ist dort
    kein Fehler. Die BREITE rollt nicht - sie wuerde abschneiden, und
    genau das war der Befund vom 18.08.2026 am Einstellungsfenster.
    """
    roh = lauf_drei.marke("anspruch-liste")
    assert "x" in roh, lauf_drei.bericht
    breite, hoehe = (int(teil) for teil in roh.split("x"))
    print(f"\nDie Liste mit drei Eintraegen verlangt {breite}x{hoehe} "
          f"(ohne Stylesheet); die Schalenseite hat {SEITENBREITE} Punkte "
          f"Breite. Die ganze Seite verlangt "
          f"{lauf_drei.marke('anspruch-seite')}.")
    assert breite <= SEITENBREITE, (
        f"die Liste verlangt {breite} Punkte, die Schalenseite hat "
        f"{SEITENBREITE} - der Inhalt wuerde waagerecht abgeschnitten. "
        + lauf_drei.bericht)
