# SPDX-License-Identifier: GPL-3.0-or-later
"""Das VPN-Schild und das vierte Wort: "niemand weiss es".

WORUM ES GEHT
    `vpn.py --status` kannte bis zum 01.09.2026 drei Woerter, und
    `disconnected` trug zwei voellig verschiedene Aussagen:

        "der Nutzer hat getrennt"           - eine Entscheidung
        "NetworkManager antwortet nicht"    - ein Ausfall

    Auf dem Schild ist dieser Unterschied nicht akademisch. "Getrennt"
    heisst fuer den Leser "dein Verkehr laeuft ungeschuetzt" - eine
    Aussage, aus der er handelt. "Niemand antwortet" heisst "niemand
    weiss, ob dein Verkehr geschuetzt ist" - das Fehlen einer. Das
    Schild gibt es genau dafuer, den beiden nicht dasselbe Bild zu
    geben.

    Die Begruendung fuer den Zustand selbst steht in src/vpn.py bei
    UNKNOWN und wird von tests/src/test_vpn_unbekannt.py gemessen. Hier
    geht es um den Leser: dass das Wort ankommt, dass es ein eigenes
    Zeichen bekommt, und dass der Kurzhinweis den Unterschied
    AUSSPRICHT statt ihn dem Leser zu ueberlassen.

    Dass jeder Zustand eine eigene FARBE hat, misst
    tests/src/test_bar_vpn.py::test_every_state_arrives_in_its_own_colour
    fuer alle vier auf einmal - siehe Abschnitt 4 unten.

DAS VERFAHREN
    Die Vorrichtung aus tests/src/test_bar_vpn.py, unveraendert
    uebernommen statt nachgebaut: die Vorlage wird gerendert und unter
    `env -i` mit einem Attrappenverzeichnis als GANZEM PATH ausgefuehrt.
    Ein zweiter Nachbau waere die Stelle, an der die beiden Dateien
    irgendwann verschiedene Welten aufbauen und verschiedene Antworten
    fuer dasselbe Modul bekommen.

    NICHT GEPRUEFT WIRD DER QUELLTEXT DER VORLAGE. Ein Test, der nach
    `vpn-unknown` sucht, ist gruen, sobald jemand die Schreibweise
    aendert, und misst nie, ob das Schild den Zweig auch erreicht. Jede
    Zusicherung hier fuehrt das Modul aus.
"""
from __future__ import annotations

import pytest

from src.vpn import STATUS_WORDS
from tests.src.test_bar_vpn import Sandbox, WIREGUARD, _document, _nm

pytestmark = pytest.mark.allow_subprocess

# Die Rueckgabewerte von nmcli(1), an denen die Unterscheidung haengt.
# 8 heisst "NetworkManager laeuft nicht", 10 "die genannte Verbindung
# gibt es nicht". Nur die zweite ist eine Auskunft ueber den Tunnel.
NM_NICHT_DA = 8
NM_KEINE_SOLCHE_VERBINDUNG = 10

# Wie die Welt aussehen muss, damit `vpn.py --status` jedes der vier
# Woerter schreibt. Eine Attrappe je Wort, und der Schluessel IST das
# Wort - test_das_schild_kennt_jedes_wort_des_vertrags haelt diese
# Tabelle gegen vpn.STATUS_WORDS und faellt um, sobald ein fuenftes
# dazukommt.
_STUBS = {
    "connected": _nm(address="10.9.0.2/24"),
    "stale": _nm(),
    "disconnected": _nm(state="deactivated"),
    "unknown": f"exit {NM_NICHT_DA}",
}


@pytest.fixture
def box(tmp_path) -> Sandbox:
    """Eine eingerichtete WireGuard-Verbindung und eine stumme Welt.

    Dieselbe Ausgangslage wie die `box` in tests/src/test_bar_vpn.py -
    hier eigen aufgeschrieben, weil eine Vorrichtung aus einem anderen
    Modul nicht mit importiert wird.
    """
    sandbox = Sandbox(tmp_path)
    sandbox.recording_stub("nmcli", "exit 0")
    sandbox.recording_stub("pgrep", "exit 1")
    sandbox.recording_stub("ip", "exit 0")
    sandbox.settings(_document(WIREGUARD))
    return sandbox


# --------------------------------------------------------------------
# 1. Der Ausfall bekommt sein eigenes Bild
# --------------------------------------------------------------------

def test_ein_toter_networkmanager_ist_nicht_getrennt(box):
    """rc=8, und das Schild sagt nicht mehr "getrennt".

    Der eine Fall, um dessentwillen es das vierte Wort gibt: der Dienst,
    der die Auskunft geben soll, laeuft nicht. Bis zum 01.09.2026 sah
    das aus wie ein Nutzer, der sein VPN ausgeschaltet hat.
    """
    box.stub("nmcli", f"exit {NM_NICHT_DA}")

    antwort = box.run()

    assert antwort["class"] == "vpn-unknown", antwort
    assert antwort["class"] != "vpn-disconnected"


def test_der_kurzhinweis_spricht_den_unterschied_aus(box):
    """Die Farbe allein reicht nicht - der Satz muss dastehen.

    Ein Schild in einer neuen Farbe, dessen Kurzhinweis "VPN getrennt"
    sagt, haette den Fehler nur umlackiert. Zwei Dinge muessen darin
    stehen und beide werden hier gemessen: WAS passiert ist
    (NetworkManager antwortet nicht) und WAS DARAUS FOLGT (niemand
    weiss, ob der Verkehr geschuetzt ist). Der zweite Satz ist der
    wichtigere: der naheliegende Schluss aus dem ersten - "dann laeuft
    wohl nichts" - ist genau der falsche.
    """
    box.stub("nmcli", f"exit {NM_NICHT_DA}")

    hinweis = box.run()["tooltip"]

    assert "NetworkManager antwortet nicht" in hinweis, hinweis
    assert "Niemand weiß" in hinweis, hinweis
    assert "geschützt" in hinweis, hinweis
    # Und das alte Wort steht NICHT mehr da. Ein Kurzhinweis, der beides
    # sagt, ist schlimmer als einer, der sich irrt.
    assert "getrennt" not in hinweis.lower(), hinweis


def test_der_name_der_verbindung_steht_auch_hier(box):
    """Wie in jedem anderen Zustand.

    Der Kurzhinweis nennt sonst immer, WORUEBER er spricht. Ein
    Zustand, der das weglaesst, laesst den Nutzer raten, welche seiner
    Verbindungen gemeint ist - und auf einer Maschine mit zweien ist
    das die Haelfte der Auskunft.
    """
    box.stub("nmcli", f"exit {NM_NICHT_DA}")

    hinweis = box.run()["tooltip"]

    assert "Arbeit" in hinweis, hinweis
    assert "WireGuard" in hinweis, hinweis


# DAS ZEICHEN: GEMESSEN IN tests/src/test_bar_vpn.py
#
#     Hier stand bis zum 02.09.2026
#     test_das_zeichen_ist_von_den_drei_schildern_verschieden. Es ist
#     dorthin eingezogen, wo die Zusicherung ueber die drei aelteren
#     Zeichen schon stand - test_every_state_arrives_with_its_own_symbol
#     geht seither vpn.STATUS_WORDS durch und deckt alle vier ab.
#
#     Zwei Tests ueber dieselbe Eigenschaft waeren die Doppelung, die
#     dieser Auftragsstrang aufloest: zwei Stellen, die dasselbe
#     behaupten, und eine davon veraltet. Genau das war hier schon
#     passiert - die aeltere zaehlte drei, waehrend es vier gab.

# --------------------------------------------------------------------
# 2. Was WEITERHIN "getrennt" heisst
# --------------------------------------------------------------------

def test_eine_nicht_eingerichtete_verbindung_bleibt_getrennt(box):
    """rc=10 IST eine Auskunft: die Verbindung gibt es nicht.

    Die andere Haelfte der Aufgabe, und ohne sie waere die erste
    wertlos. Saugte `unknown` jeden Fehlschlag auf, haette man
    `disconnected` bloss umbenannt - und eine Maschine ohne
    eingerichtete Verbindung truege dauerhaft ein warnendes Schild fuer
    einen voellig gewoehnlichen Zustand.
    """
    box.stub("nmcli", f"exit {NM_KEINE_SOLCHE_VERBINDUNG}")

    antwort = box.run()

    assert antwort["class"] == "vpn-disconnected", antwort
    assert "getrennt" in antwort["tooltip"], antwort


def test_eine_geantwortete_abmeldung_bleibt_getrennt(box):
    """nmcli hat geantwortet, und die Antwort heisst "nicht aktiviert".

    Der haeufigste Zustand ueberhaupt. Er darf durch den Umbau kein
    Warnzeichen bekommen - ein Schild, das im Ruhezustand warnt, wird
    nach dem dritten Tag nicht mehr gelesen.
    """
    box.stub("nmcli", _nm(state="deactivated"))

    assert box.run()["class"] == "vpn-disconnected"


# --------------------------------------------------------------------
# 3. Der Vertrag, und dass das Schild ihn ganz kennt
# --------------------------------------------------------------------

def test_das_schild_kennt_jedes_wort_des_vertrags(box):
    """Jedes Wort aus vpn.STATUS_WORDS bekommt ein eigenes Bild.

    DIE ZUSICHERUNG, DIE EIN FUENFTES WORT UMWIRFT
        src/vpn.py fuehrt STATUS_WORDS an einer Stelle, damit ein neues
        Wort nicht bloss hinzugefuegt werden kann, sondern die
        Zusicherungen der Leser umwirft. Dies ist der Leser, an dem das
        haengt: die Tabelle oben muss vollstaendig sein, sonst faellt
        schon die erste Zeile.

    UND KEINES DAVON IST DER SONST-ZWEIG
        Das Schild hat einen Zweig fuer ein Wort, das der Vertrag nicht
        kennt - Warnzeichen, Klasse "broken", das fremde Wort im
        Kurzhinweis. Ein Zustand, der DORT landet, sieht auf dem
        Bildschirm nach einem kaputten Programm aus, obwohl er im
        Vertrag steht. Genau das faende ein Test, der nur "es kommt
        irgendein Modul heraus" prueft, niemals.
    """
    assert set(_STUBS) == set(STATUS_WORDS), (
        "die Tabelle der Attrappen und der Vertrag in src/vpn.py sind "
        f"auseinander: {sorted(set(_STUBS) ^ set(STATUS_WORDS))}")

    klassen = {}
    for wort, stub in _STUBS.items():
        box.stub("nmcli", stub)
        antwort = box.run()
        assert antwort["class"] != "broken", (
            f"das Schild haelt `{wort}` fuer ein unbekanntes Wort: "
            + str(antwort))
        assert antwort["text"], f"`{wort}` ergibt ein leeres Modul: {antwort}"
        klassen[wort] = antwort["class"]

    assert len(set(klassen.values())) == len(STATUS_WORDS), (
        "zwei Woerter des Vertrags landen in derselben Klasse: "
        + str(klassen))


# --------------------------------------------------------------------
# 4. Die vierte Farbe - GEMESSEN IN tests/src/test_bar_vpn.py
# --------------------------------------------------------------------
#
# HIER STAND BIS ZUM 02.09.2026 test_der_vierte_zustand_hat_eine_eigene_farbe
#
#     Es war eine ZWEITE Zusicherung ueber dieselbe Eigenschaft: dass
#     jeder Zustand des Schildes einen eigenen Farbnamen und einen
#     eigenen Wert hat. Die erste stand in tests/src/test_bar_vpn.py und
#     zaehlte drei; diese hier zaehlte vier.
#
#     Sie ist nicht geloescht, sondern eingezogen worden: der Test dort
#     heisst jetzt test_every_state_arrives_in_its_own_colour und holt
#     seine Liste aus vpn.STATUS_WORDS. Damit deckt er ab, was diese
#     Fassung abdeckte, und mehr - ein fuenftes Wort wirft ihn um,
#     waehrend zwei getippte Listen nebeneinander genau die Doppelung
#     gewesen waeren, die dieser ganze Auftragsstrang aufloest: zwei
#     Stellen, die dasselbe behaupten, und eine davon veraltet.
#
#     WELCHE der Zustand traegt - die Warnfarbe und nicht das
#     Kritischrot, und nicht die Abblendung von "getrennt" - begruendet
#     src/styles/bar-style.template an der Regel selbst.
