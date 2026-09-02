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
    geht es um den Leser: dass das Wort ankommt, dass es eine eigene
    Farbe und ein eigenes Zeichen bekommt, und dass der Kurzhinweis den
    Unterschied AUSSPRICHT statt ihn dem Leser zu ueberlassen.

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
from tests.src.test_bar_vpn import (Sandbox, WIREGUARD, _document, _nm,
                                    _placeholder_of, _shipped_styles)

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


def test_das_zeichen_ist_von_den_drei_schildern_verschieden(box):
    """Farbe traegt nicht allein - dieselbe Regel wie fuer die drei.

    Rot-Gruen ist die haeufigste Farbsehschwaeche, und dieses Modul ist
    genau die Anzeige, bei der ein Irrtum teuer ist. Gemessen wird
    gegen die drei anderen Zeichen und nicht gegen ein Literal: ein
    Vergleich mit einem eingetippten Glyphen waere gruen, wenn zwei
    Zustaende DENSELBEN falschen traegen.
    """
    zeichen = {}
    for wort, stub in _STUBS.items():
        box.stub("nmcli", stub)
        zeichen[wort] = box.run()["text"]

    assert len(set(zeichen.values())) == len(STATUS_WORDS), (
        "zwei Zustaende des Schildes zeigen dasselbe Zeichen: "
        + str(zeichen))


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
# 4. Die vierte Farbe
# --------------------------------------------------------------------

def test_der_vierte_zustand_hat_eine_eigene_farbe(tmp_path, monkeypatch):
    """Vier Zustaende brauchen vier Farben - beide Enden geprueft.

    Dieselbe Bauart wie
    test_the_three_states_arrive_in_three_different_colours in
    tests/src/test_bar_vpn.py, um das vierte Wort erweitert: erst die
    Namen im Stylesheet, dann die Werte, die der Erzeuger daraus macht.
    Verschiedene Namen fuer denselben Wert waeren vier Regeln, die
    dasselbe malen - und jede Zusicherung ueber die KLASSEN bliebe
    dabei gruen.

    WARUM DIE WARNFARBE UND NICHT DAS KRITISCHROT
        Rot ist in der Leiste die Farbe fuer "etwas ist kaputt, und wir
        wissen was". Hier ist nichts festgestellt worden - nur das
        Feststellen ist ausgefallen. Und nicht die Abblendung von
        "getrennt", so nahe das laege: gedaempft heisst in dieser Leiste
        ueberall "vorhanden und in Ruhe", und genau dieser Schluss ist
        der, den der Zustand verhindern soll. Der Test haelt nur fest,
        dass die vier verschieden sind - WELCHE es ist, begruendet
        src/styles/bar-style.template.
    """
    namen = {klasse: _placeholder_of(klasse) for klasse in
             ("vpn-connected", "vpn-stale", "vpn-disconnected",
              "vpn-unknown")}
    assert len(set(namen.values())) == 4, (
        "zwei Zustaende des Schildes zeigen auf denselben Farbnamen: "
        + str(namen))

    styles = _shipped_styles(tmp_path, monkeypatch)
    werte = {}
    for klasse, name in namen.items():
        assert name in styles, (
            f"{name} ist kein Platzhalter, den der Erzeuger kennt - die "
            "Regel bliebe im erzeugten Stylesheet ungefuellt stehen")
        werte[klasse] = str(styles[name])

    assert len(set(werte.values())) == 4, (
        "zwei Farbnamen des Schildes fuehren auf denselben Wert: "
        + str(werte))
