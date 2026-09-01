# SPDX-License-Identifier: GPL-3.0-or-later
"""Eine VPN-Verbindung loeschen - und was dabei alles mit weg muss.

WAS GEMELDET WURDE (01.09.2026), WOERTLICH
    "ich kann vpn verbindungen auch nicht loeschen"

WORAN ES LAG: ES WAR NIE GEBAUT
    GEZAEHLT am 01.09.2026 im ganzen Baum - src/vpn.py kannte weder
    `--delete` noch `--remove` noch eine Funktion mit del/rem/loesch im
    Namen, und die beiden `deleteBtn` in ags-vpn-settings.template
    loeschen eine ZEILE innerhalb eines Eintrags (ein geroutetes Netz,
    eine Gegenstelle), nicht die Verbindung.

    Zusammen mit dem Fehler, der das Oeffnen eines gespeicherten
    Eintrags verhinderte (siehe die Kennungs-Ursache im Bericht zu
    Aufgabe 76), war die Liste damit praktisch schreibgeschuetzt:
    anlegen ging, oeffnen nicht, loeschen gab es nicht. Wer sich
    vertippt hatte, wurde den Eintrag nie wieder los.

WARUM DIESE DATEI DIE GEHEIMNISSE MISST UND NICHT DIE OBERFLAECHE
    Ein Loeschen, das den privaten Schluessel auf der Platte laesst, ist
    schlimmer als keins: die Verbindung ist aus der Liste verschwunden,
    also sucht sie niemand mehr - und der Schluessel liegt weiter da.
    Genau das ist die Zusicherung, die diese Datei traegt, und sie
    braucht dafuer keine Oberflaeche, sondern ein Verzeichnis.

    Die Dateien hier sind ERFUNDEN und stehen unter tmp_path. Es wird
    kein Geheimnis des Nutzers gelesen, kein Verzeichnis von ihm
    angefasst und kein nmcli ausgefuehrt - der Aufrufer bekommt einen
    Runner untergeschoben, der nur aufschreibt, was er bekommen haette.

DIE PRUEFUNG, DIE NICHT FEHLEN DARF
    Eine Geheimnisdatei wird nur geloescht, wenn KEINE andere Verbindung
    sie ebenfalls nennt. Der Fall ist real und nicht theoretisch: alles,
    was vor dem 22.08.2026 angelegt oder von dort gewandert ist, zeigt
    auf dieselbe Datei "psk" (siehe psk_file_name() in src/vpn.py). Zwei
    solche Eintraege, und das Loeschen des einen naehme dem anderen
    seinen Schluessel.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import vpn  # noqa: E402
from settings import UnusableSettings  # noqa: E402


@pytest.fixture
def heim(tmp_path, monkeypatch) -> Path:
    """Ein XDG_CONFIG_HOME unter tmp_path, mit den drei Verzeichnissen.

    monkeypatch auf die Umgebungsvariable und nicht auf die drei
    *_key_dir()-Funktionen: gemessen werden soll der Weg, den vpn.py
    wirklich geht, und der liest genau diese Variable.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    for name in ("wireguard", "openvpn", "strongswan"):
        (tmp_path / name).mkdir()
    return tmp_path


class Mitschrift:
    """Ein Runner, der nichts tut und alles aufschreibt.

    Es darf in dieser Datei KEIN nmcli laufen: die Maschine, auf der die
    Suite laeuft, ist die des Nutzers, und `nmcli connection delete`
    trifft dort seine Verbindungen.
    """

    def __init__(self, returncode: int = 0) -> None:
        self.aufrufe: list[list[str]] = []
        self.returncode = returncode

    def __call__(self, argv, **kwargs):
        self.aufrufe.append(list(argv))
        return subprocess.CompletedProcess(argv, self.returncode, "", "")


def _dokument(*eintraege: dict) -> dict:
    return {"vpn": {"active": eintraege[0]["id"] if eintraege else "",
                    "connections": list(eintraege)}}


# ----------------------------------------------------------------------
# Was einer Verbindung gehoert
# ----------------------------------------------------------------------

def test_die_dateien_kommen_aus_den_einstellungen_und_nicht_aus_der_kennung(heim):
    """Die Namen werden GELESEN, nicht gerechnet.

    Sie liessen sich aus der Kennung herleiten (secret_prefix() plus
    Endung), und genau das waere falsch: eine Verbindung von vor dem
    22.08.2026 traegt einen Namen aus dem VERBINDUNGSNAMEN, eine
    gewanderte traegt "psk" ohne jeden Namen. Gerechnete Namen gingen an
    beiden vorbei und liessen die Geheimnisse liegen.
    """
    eintrag = {
        "id": "aa11bb22", "kind": "wireguard", "connection_name": "zuhause",
        "wireguard": {
            # ABSICHTLICH NICHT nach der Kennung benannt: so misst diese
            # Zusicherung, dass gelesen und nicht gerechnet wird.
            "private_key_file": "uralt-name.key",
            "peers": [{"preshared_key_file": "uralt-name-peer1.psk"},
                      {"preshared_key_file": ""}],
        },
    }
    namen = [p.name for p in vpn.secret_files_of(eintrag)]
    assert namen == ["uralt-name.key", "uralt-name-peer1.psk"], namen
    # Der leere Eintrag der zweiten Gegenstelle wird uebergangen und
    # nicht zu einem Pfad auf das Verzeichnis selbst.
    assert all(p.name for p in vpn.secret_files_of(eintrag))


def test_eine_ipsec_verbindung_ohne_psk_file_zeigt_auf_die_alte_datei(heim):
    """`psk` ist der Name aus der Zeit vor den Listen.

    Er ist der Grund fuer die Pruefung weiter unten: zwei gewanderte
    Verbindungen zeigen beide dorthin.
    """
    namen = [p.name for p in vpn.secret_files_of(
        {"id": "c1", "kind": "ipsec", "connection_name": "arbeit"})]
    assert namen == ["psk"], namen


# ----------------------------------------------------------------------
# Das Loeschen selbst
# ----------------------------------------------------------------------

def test_der_schluessel_ist_hinterher_weg(heim):
    """Die Zusicherung, um die es geht.

    Ein Loeschen, das den privaten Schluessel liegen laesst, ist
    schlimmer als keins.
    """
    (heim / "wireguard" / "aa11bb22.key").write_text("nicht-echt")
    (heim / "wireguard" / "aa11bb22-peer1.psk").write_text("nicht-echt")
    dokument = _dokument({
        "id": "aa11bb22", "kind": "wireguard", "connection_name": "zuhause",
        "wireguard": {"private_key_file": "aa11bb22.key",
                      "peers": [{"preshared_key_file": "aa11bb22-peer1.psk"}]},
    })
    lauf = Mitschrift()

    bericht = vpn.forget_connection(dokument, "aa11bb22", lauf)

    assert not (heim / "wireguard" / "aa11bb22.key").exists()
    assert not (heim / "wireguard" / "aa11bb22-peer1.psk").exists()
    assert sorted(bericht["dateien"]) == ["aa11bb22-peer1.psk",
                                          "aa11bb22.key"]
    assert bericht["behalten"] == []


def test_der_tunnel_wird_erst_getrennt_und_dann_das_profil_geloescht(heim):
    """Die Reihenfolge, und dass ueberhaupt beides passiert.

    Ein Profil zu loeschen, waehrend die Verbindung steht, laesst bei
    NetworkManager eine aktive Verbindung ohne Profil zurueck.
    """
    dokument = _dokument({"id": "c9", "kind": "openvpn",
                          "connection_name": "reise", "openvpn": {}})
    lauf = Mitschrift()

    vpn.forget_connection(dokument, "c9", lauf)

    assert lauf.aufrufe == [
        ["nmcli", "connection", "down", "reise"],
        ["nmcli", "connection", "delete", "reise"],
    ], lauf.aufrufe


def test_ipsec_ruft_kein_nmcli(heim):
    """Bei IPsec gibt es kein NetworkManager-Profil.

    Dort ist strongSwan der Gegenpart, und der liest seine Konfiguration
    bei jedem Start neu aus den Einstellungen. Ein `nmcli connection
    delete arbeit` traefe dort im besten Fall nichts und im schlechtesten
    eine gleichnamige Verbindung, die jemand anders angelegt hat.
    """
    (heim / "strongswan" / "c1.psk").write_text("nicht-echt")
    dokument = _dokument({"id": "c1", "kind": "ipsec",
                          "connection_name": "arbeit", "psk_file": "c1.psk"})
    lauf = Mitschrift()

    bericht = vpn.forget_connection(dokument, "c1", lauf)

    assert lauf.aufrufe == []
    assert bericht["dateien"] == ["c1.psk"]
    assert not (heim / "strongswan" / "c1.psk").exists()


def test_eine_datei_die_eine_andere_verbindung_auch_nennt_bleibt(heim):
    """DIE Pruefung, die nicht fehlen darf.

    Zwei gewanderte IPsec-Verbindungen zeigen beide auf ~/.config/
    strongswan/psk (siehe psk_file_name()). Das Loeschen der einen
    naehme der anderen ihren Schluessel - und die andere stuende danach
    unveraendert in der Liste, waere aber nicht mehr zu verbinden.
    """
    (heim / "strongswan" / "psk").write_text("nicht-echt")
    dokument = _dokument(
        {"id": "c1", "kind": "ipsec", "connection_name": "arbeit"},
        {"id": "c2", "kind": "ipsec", "connection_name": "zweitarbeit"},
    )
    lauf = Mitschrift()

    bericht = vpn.forget_connection(dokument, "c1", lauf)

    assert (heim / "strongswan" / "psk").exists(), (
        "die gemeinsame PSK-Datei ist weg - die zweite Verbindung ist "
        "damit stillschweigend unbrauchbar geworden")
    assert bericht["dateien"] == []
    assert bericht["behalten"] == [
        {"datei": "psk",
         "grund": "eine andere Verbindung nennt dieselbe Datei"}]


def test_eine_datei_die_es_nicht_gibt_ist_kein_fehler(heim):
    """Eine Verbindung, die nie einen Schluessel bekommen hat.

    Sie ist der Normalfall direkt nach dem Anlegen, und sie darf das
    Loeschen nicht zum Scheitern bringen.
    """
    dokument = _dokument({"id": "c3", "kind": "ipsec",
                          "connection_name": "frisch", "psk_file": "c3.psk"})

    bericht = vpn.forget_connection(dokument, "c3", Mitschrift())

    assert bericht["dateien"] == []
    assert bericht["behalten"] == []


def test_eine_unbekannte_kennung_loescht_NICHTS(heim):
    """Und das ist die wichtigste Zusicherung dieser Datei.

    vpn.py::connection() faellt bei einer unbekannten Kennung auf die
    ERSTE Verbindung zurueck - fuer jeden Leser ist das richtig und mit
    Grund so gebaut. Fuer einen LOESCHBEFEHL waere es das Schlimmste, was
    er tun kann: ein Tippfehler in der Kennung, und die falsche
    Verbindung ist weg.
    """
    (heim / "strongswan" / "c1.psk").write_text("nicht-echt")
    dokument = _dokument({"id": "c1", "kind": "ipsec",
                          "connection_name": "arbeit", "psk_file": "c1.psk"})
    lauf = Mitschrift()

    with pytest.raises(UnusableSettings) as fehler:
        vpn.forget_connection(dokument, "gibtsnicht", lauf)

    assert "gibtsnicht" in str(fehler.value)
    assert (heim / "strongswan" / "c1.psk").exists()
    assert lauf.aufrufe == []


def test_die_einstellungsdatei_wird_nicht_angefasst(heim, tmp_path):
    """Diese Haelfte gehoert dem Fenster.

    Es schreibt user-settings.json ueber `settings.py merge`, das die
    uebrigen Abschnitte behaelt, die Schemaversion nennt und atomar bei
    0600 schreibt. Zwei Schreiber auf einer Datei waeren zwei Schreiber
    auf einer Datei - und der Eintrag darf ausserdem erst NACH diesem
    Aufruf verschwinden, weil hier die Dateinamen aus ihm gelesen
    werden.
    """
    datei = tmp_path / "user-settings.json"
    dokument = _dokument({"id": "c1", "kind": "ipsec",
                          "connection_name": "arbeit"})
    datei.write_text(json.dumps(dokument), encoding="utf-8")
    vorher = datei.read_bytes()

    vpn.forget_connection(dokument, "c1", Mitschrift())

    assert datei.read_bytes() == vorher
    # Und die Verbindung steht auch im Dokument im Speicher noch drin:
    # der Aufrufer nimmt sie heraus, nicht diese Funktion.
    assert [e["id"] for e in vpn.connections(dokument)] == ["c1"]


# ----------------------------------------------------------------------
# Der Befehl auf der Kommandozeile
# ----------------------------------------------------------------------

def test_ohne_kennung_verweigert_der_befehl(heim, capsys):
    """`--forget` ohne Kennung ist kein "loesch die aktive".

    Es waere die naheliegende Bequemlichkeit und genau der Weg, auf dem
    ein Loeschbefehl die falsche Verbindung erwischt.
    """
    assert vpn.main(["--forget"]) == 64
    assert "usage" in capsys.readouterr().err.lower()


def test_der_befehl_meldet_als_json_was_er_getan_hat(heim, monkeypatch,
                                                     capsys):
    """Was getan und was nicht getan wurde, steht im Umschlag.

    Der Aufrufer ist ein Fenster; es kann nur zeigen, was es erfaehrt.

    EINE IPSEC-VERBINDUNG UND KEINE WIREGUARD, und das ist keine
    Bequemlichkeit: `main()` ruft forget_connection() ohne eigenen
    Runner, es gilt also der Vorgabewert `subprocess.run` - und der ist
    an die FUNKTIONSDEFINITION gebunden, ein monkeypatch auf
    vpn.subprocess.run kommt zu spaet. Der Versuch ist gelaufen und
    prompt vom Waechter in tests/conftest.py abgefangen worden ("This
    test tried to start a real process"), was genau richtig ist: auf der
    Maschine, auf der diese Suite laeuft, traefe `nmcli connection
    delete` die Verbindungen des Nutzers.

    IPsec ruft kein nmcli (siehe test_ipsec_ruft_kein_nmcli oben), also
    misst dieser Lauf den ganzen Befehlsweg, ohne dass ueberhaupt ein
    Prozess entstehen KANN. Der nmcli-Teil ist eine Zeile hoeher
    gemessen, mit untergeschobenem Runner.
    """
    (heim / "strongswan" / "z1.psk").write_text("nicht-echt")
    dokument = _dokument({
        "id": "z1", "kind": "ipsec", "connection_name": "arbeit",
        "psk_file": "z1.psk",
    })
    monkeypatch.setattr(vpn, "_settings_document", lambda: dokument)

    assert vpn.main(["--forget", "z1"]) == 0

    umschlag = json.loads(capsys.readouterr().out)
    assert umschlag["id"] == "z1"
    assert umschlag["kind"] == "ipsec"
    assert umschlag["dateien"] == ["z1.psk"]
    assert umschlag["behalten"] == []
    assert not (heim / "strongswan" / "z1.psk").exists()


def test_der_befehl_endet_mit_65_bei_einer_unbekannten_kennung(heim,
                                                               monkeypatch,
                                                               capsys):
    """Und sagt auf stderr, welche Kennungen es gibt.

    Ein Fenster, das eine Kennung schickt, die es nicht mehr gibt, hat
    einen veralteten Stand - und der Mensch davor soll das lesen koennen,
    statt vor einem Knopf zu stehen, der nichts tut.
    """
    dokument = _dokument({"id": "c1", "kind": "ipsec",
                          "connection_name": "arbeit"})
    monkeypatch.setattr(vpn, "_settings_document", lambda: dokument)

    assert vpn.main(["--forget", "weg"]) == 65
    fehler = capsys.readouterr().err
    assert "weg" in fehler and "c1" in fehler
