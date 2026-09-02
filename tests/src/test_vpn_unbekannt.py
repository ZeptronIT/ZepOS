# SPDX-License-Identifier: GPL-3.0-or-later
"""Ein Ausfall darf nicht aussehen wie eine Entscheidung.

DER BEFUND
    `vpn.py --status` kannte drei Woerter, und `disconnected` trug zwei
    voellig verschiedene Aussagen:

        "der Nutzer hat getrennt"            - eine Entscheidung
        "NetworkManager antwortet nicht"     - ein Ausfall

    Der Docstring von wireguard_status() sagte es selbst: "disconnected
    - alles andere, die fehlende Auskunft eingeschlossen." Das ist
    gefaehrlich in BEIDE Richtungen. Wer "getrennt" liest, schliesst
    daraus, sein Verkehr laufe ungeschuetzt, und verbindet neu, obwohl
    vielleicht ein Tunnel steht. Oder er sieht "getrennt", haelt alles
    fuer in Ordnung, und in Wahrheit weiss niemand, was der Tunnel tut.

WAS GENAU ZUSAMMENFIEL - GEMESSEN am 01.09.2026 an src/vpn.py::_run()
    _run() faengt OSError und SubprocessError ab, gibt "" zurueck und
    sieht den Rueckgabewert ueberhaupt nicht an. Vier Lagen ergaben
    dasselbe Wort:

        nmcli fehlt                     OSError          -> disconnected
        nmcli laeuft in den Zeitablauf  TimeoutExpired   -> disconnected
        NetworkManager laeuft nicht     rc=8             -> disconnected
        die Verbindung gibt es nicht    rc=10            -> disconnected

    Nur die letzte davon IST eine Auskunft. Die anderen drei sind das
    Fehlen einer.

DER VIERTE ZUSTAND, UND WARUM ER ADDITIV IST
    `unknown`. Er kommt genau dann, wenn nmcli keine verwertbare Antwort
    gegeben hat - nicht, wenn es eine gegeben hat, die "nicht verbunden"
    heisst.

    Vier Leser haengen an dem einen Wort (Datei und Zeile stehen in
    aufgabe-77-report.md). Drei davon bekommen hier einen eigenen Zweig.
    Der vierte, src/templates/ags-vpn.template, faellt bei jedem
    unbekannten Wort auf "disconnected" durch - also genau auf das, was
    er HEUTE bei nicht antwortendem NetworkManager schon zeigt. Der
    vierte Zustand macht dort nichts schlechter und wartet auf einen
    eigenen Zweig; die Datei gehoert in dieser Sitzung einem anderen.
"""
import subprocess

import pytest

from src.vpn import (CONNECTED, DISCONNECTED, STALE, STATUS_WORDS, UNKNOWN,
                     openvpn_status, wireguard_status)

# Die Rueckgabewerte, an denen die Unterscheidung haengt. nmcli(1)
# fuehrt sie: 8 heisst "NetworkManager laeuft nicht", 10 heisst "die
# genannte Verbindung gibt es nicht".
NM_NICHT_DA = 8
NM_UNBEKANNTE_VERBINDUNG = 10


class Antwortet:
    """Ein `runner` mit einem Rueckgabewert und einem Text."""

    def __init__(self, returncode: int = 0, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout

    def __call__(self, argv, **kwargs):
        return subprocess.CompletedProcess(argv, self.returncode,
                                           stdout=self.stdout, stderr="")


class Wirft:
    """Ein `runner`, der gar nicht erst laeuft."""

    def __init__(self, fehler: Exception) -> None:
        self.fehler = fehler

    def __call__(self, argv, **kwargs):
        raise self.fehler


# --------------------------------------------------------------------
# 1. Was NICHT mehr "getrennt" heissen darf
# --------------------------------------------------------------------

@pytest.mark.parametrize("runner,lage", [
    (Wirft(FileNotFoundError("nmcli")), "nmcli liegt nicht auf der Maschine"),
    (Wirft(subprocess.TimeoutExpired("nmcli", 5)), "nmcli antwortet nicht"),
    (Antwortet(returncode=NM_NICHT_DA), "NetworkManager laeuft nicht"),
    (Antwortet(returncode=1), "nmcli meldet einen Fehler ohne Aussage"),
])
def test_ein_ausfall_heisst_unknown_und_nicht_disconnected(runner, lage):
    """Die vier Lagen, die bis zum 01.09.2026 "getrennt" hiessen.

    Der Test nennt jede beim Namen, damit eine spaetere Aenderung, die
    eine davon wieder einsammelt, sagt WELCHE.
    """
    zustand, adresse = wireguard_status("work", runner)
    assert zustand == UNKNOWN, f"{lage}: {zustand!r} statt {UNKNOWN!r}"
    # Keine Adresse zu einem Zustand, ueber den nichts bekannt ist. Eine
    # mitgegebene waere eine Behauptung ueber einen Tunnel, von dem
    # gerade niemand weiss, ob es ihn gibt.
    assert adresse == ""


def test_dieselbe_unterscheidung_gilt_fuer_openvpn():
    """openvpn_status() reicht an wireguard_status() weiter - und muss
    es sichtbar tun. Vier Leser teilen sich eine Zeile Text, und keiner
    von ihnen darf wissen muessen, welche Bauart eingestellt ist."""
    assert openvpn_status("work", Antwortet(returncode=NM_NICHT_DA)) \
        == (UNKNOWN, "")


# --------------------------------------------------------------------
# 2. Was WEITERHIN "getrennt" heisst - die andere Haelfte der Aufgabe
# --------------------------------------------------------------------

def test_eine_unbekannte_verbindung_ist_getrennt_und_nicht_unbekannt():
    """rc=10 IST eine Auskunft: die Verbindung gibt es nicht.

    Die Unterscheidung waere wertlos, wenn `unknown` einfach jeden
    Fehlschlag einsammelte. Dann haette man `disconnected` durch
    `unknown` ersetzt und nichts gewonnen - der Nutzer saehe auf einer
    Maschine ohne eingerichtete Verbindung dauerhaft "niemand weiss es".
    """
    assert wireguard_status("work",
                            Antwortet(returncode=NM_UNBEKANNTE_VERBINDUNG)) \
        == (DISCONNECTED, "")


def test_eine_geantwortete_abmeldung_bleibt_getrennt():
    """nmcli hat geantwortet, und die Antwort heisst "nicht aktiviert"."""
    assert wireguard_status(
        "work", Antwortet(stdout="GENERAL.STATE:deactivated\n")) \
        == (DISCONNECTED, "")


def test_ohne_verbindungsnamen_wird_nicht_gefragt():
    """Kein Name heisst: nichts eingerichtet. Das ist getrennt und nicht
    unbekannt - und es darf keinen Unterprozess kosten."""
    assert wireguard_status("", Wirft(AssertionError("nicht fragen"))) \
        == (DISCONNECTED, "")


@pytest.mark.parametrize("report,erwartet", [
    ("GENERAL.STATE:activated\nIP4.ADDRESS[1]:203.0.113.9/32\n",
     (CONNECTED, "203.0.113.9")),
    ("GENERAL.STATE:activated\n", (STALE, "")),
])
def test_die_beiden_anderen_woerter_sind_unberuehrt(report, erwartet):
    assert wireguard_status("work", Antwortet(stdout=report)) == erwartet


# --------------------------------------------------------------------
# 3. Der Vertrag nach aussen
# --------------------------------------------------------------------

def test_der_vertrag_nennt_genau_vier_woerter():
    """STATUS_WORDS ist die Liste, gegen die die Leser gemessen werden.

    Sie steht in src/vpn.py, damit ein fuenftes Wort nicht bloss
    hinzugefuegt werden kann, sondern die Zusicherungen der Leser
    umwirft - test_das_schild_kennt_jedes_wort_des_vertrags in
    tests/src/test_bar_vpn_unbekannt.py geht genau diese Liste durch.
    """
    assert STATUS_WORDS == (CONNECTED, STALE, DISCONNECTED, UNKNOWN)
    # Vier verschiedene Woerter, nicht dreimal dasselbe.
    assert len(set(STATUS_WORDS)) == 4


def test_status_schreibt_das_vierte_wort(monkeypatch, capsys):
    """`--status` gibt es weiter, statt es unterwegs einzuebnen."""
    import src.vpn as vpn

    monkeypatch.setattr(vpn, "_settings_document",
                        lambda: {"schema_version": 2, "vpn": {
                            "active": "c1",
                            "connections": [{"id": "c1", "kind": "wireguard",
                                             "connection_name": "work"}]}})
    monkeypatch.setattr(vpn, "wireguard_status",
                        lambda name, *a, **k: (UNKNOWN, ""))

    assert vpn.main(["--status"]) == 0
    assert capsys.readouterr().out.strip() == UNKNOWN
