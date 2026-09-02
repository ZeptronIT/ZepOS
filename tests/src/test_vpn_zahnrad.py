# SPDX-License-Identifier: GPL-3.0-or-later
"""Das Zahnrad je VPN-Zeile, und WELCHE Verbindung es oeffnet.

WAS GEMELDET WURDE
    Der Nutzer am 02.09.2026, woertlich: "ich kann uebrigens in der
    liste kein einstellung icon pro vpn sehen um direkt zur vpn zu
    gelangen stattdessen muss ich es aktivieren und dann komme ich auf
    die vpn bzw einstellungen statt direkt dort hinzugelangen" - und
    praezisiert: "ich will neben dem toggle auch ein icon fuer
    einstellung haben das zahnrad".

    Das Zahnrad gab es zweimal, und beide sassen in der EINZELHEIT
    (connectedSettingsBtn, formSettingsBtn). Aus der Liste fuehrte
    darum kein Weg dorthin, der nicht ueber die Einzelheit ging.

DIE EINE FRAGE, AN DER ALLES HAENGT: WELCHE KENNUNG
    Ein Zahnrad in der Liste muss `openVpnSettings(eintrag.id)` rufen -
    die Kennung DIESER Zeile. `gewaehlteId` waere die Verbindung, die
    die Einzelheit gerade zeigt, und aus der Liste heraus ist das eine
    andere.

    Damit der Unterschied ueberhaupt MESSBAR ist, drueckt dieser Lauf
    das Zahnrad der ZWEITEN Zeile, waehrend `active` in der
    Einstellungsdatei auf die ERSTE zeigt (`_einstellungen` in
    test_vpn_schalter.py: c1 "Zuhause", c2 "Arbeit", active c1). Stuende
    `gewaehlteId` im Quelltext, kaeme `vpn-settings:c1` heraus. Am
    Zahnrad der ERSTEN Zeile waeren beide Kennungen gleich, und die
    Zusicherung waere gruen, ohne etwas zu unterscheiden - genau die
    Sorte blinde Messung, die dieser Zweig schon dreimal gefunden hat.

WIE DIE WIRKUNG GELESEN WIRD, OHNE ETWAS ANZUFASSEN
    `openVpnSettings` setzt `ags request vpn-settings:<kennung>` ab.
    Dieser Test legt eine ATTRAPPE namens `ags` VOR /usr/bin in den PATH
    des Kindes; sie schreibt ihre Aufrufzeile in eine Datei und tut
    sonst nichts.

    Das ist nicht nur bequem, es ist die Sicherheitsbedingung: ein
    echtes `ags request` spricht ueber den Astal-Socket eine LAUFENDE
    Oberflaeche an. Die Attrappe stellt sicher, dass diese Messung
    niemals in der Sitzung des Nutzers landet, egal was die Vorlage
    aufruft.

WAS AUSSERDEM GEMESSEN WIRD
    Dass das Zahnrad NICHT schaltet und NICHT in die Einzelheit
    blaettert, und dass der Schalter umgekehrt KEINE Einstellungen
    oeffnet. Drei Laeufe: einmal Zahnrad, einmal Schalter, einmal
    NICHTS. Der dritte ist die Gegenprobe - ohne ihn waere "nach dem
    Druck steht eine Anfrage in der Datei" auch dann erfuellt, wenn die
    Seite beim Aufbauen von sich aus eine absetzt.

    Was ein ZEIGERdruck traefe und was eine echte Taste tut, misst
    tests/render/test_zeprow_verschachtelung.py - dort gibt es einen
    Compositor und wtype.

SICHERHEIT
    Eigener gtk4-broadwayd in eigenem XDG_RUNTIME_DIR. `vpn.py` ist eine
    Attrappe, die ein Wort druckt; `ags` ist eine Attrappe, die eine
    Zeile schreibt. Niemand fragt NetworkManager oder strongSwan etwas,
    und niemand funkt in eine laufende Oberflaeche.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Den Aufbau von test_vpn_schalter.py leihen statt ihn abzuschreiben.
_SPEC = importlib.util.spec_from_file_location(
    "_vpn_schalter_harness",
    ROOT / "tests" / "src" / "test_vpn_schalter.py")
_HARNESS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HARNESS)

pytestmark = pytest.mark.allow_subprocess

KIND = Path(__file__).resolve().parent / "vpn_zahnrad_child.tsx"

# Die Kennungen aus _einstellungen(). Die ZWEITE ist das Ziel, die
# ERSTE ist die, die `gewaehlteId` traegt - siehe den Dateikopf.
AKTIVE_KENNUNG = "c1"
ZIEL_KENNUNG = "c2"
ZIEL_NAME = _HARNESS.ARBEIT

ZIELE = ("zahnrad", "schalter", "nichts")


def _lauf(wurzel: Path, ziel: str):
    """Ein Lauf, in dem `ziel` betaetigt wird."""
    server_befehl = _HARNESS.broadwayd()
    if server_befehl is None:
        pytest.skip("gtk4-broadwayd fehlt; es kommt mit dem Paket gtk4")

    # GEBAUT WIRD MIT DEM ECHTEN `ags` (ausserhalb dieser Umgebung), und
    # NUR DER LAUF bekommt die Attrappe. `ags bundle` ist der Uebersetzer
    # und muss echt sein; `ags request` ist die Wirkung und darf es nicht.
    buendel, _system = _HARNESS._baue(wurzel, kind=KIND)
    attrappen, ags_protokoll = _HARNESS._ags_attrappe(wurzel)

    laufzeit = wurzel / "run"
    laufzeit.mkdir()
    laufzeit.chmod(0o700)

    user_root = wurzel / "zepos"
    _HARNESS._einstellungen(user_root)

    spur = wurzel / "spur"
    nummer = next(_HARNESS._DISPLAYS)
    server, _socket = _HARNESS.start_broadwayd(server_befehl, laufzeit, nummer)
    try:
        ergebnis = subprocess.run(
            [str(buendel)],
            env={
                # DIE ATTRAPPE VOR /usr/bin - die eine Zeile, an der
                # diese Messung haengt.
                "PATH": f"{attrappen}:/usr/bin:/bin",
                "HOME": str(wurzel),
                "GDK_BACKEND": "broadway",
                "BROADWAY_DISPLAY": f":{nummer}",
                "XDG_RUNTIME_DIR": str(laufzeit),
                "XDG_CONFIG_HOME": str(wurzel / "config"),
                "ZEPOS_USER_ROOT": str(user_root),
                "DBUS_SESSION_BUS_ADDRESS": f"unix:path={wurzel}/kein-bus",
                "LC_ALL": "C",
                "LANG": "C",
                "ZEPOS_TRACE": str(spur),
                "ZEPOS_ZIEL": ziel,
            },
            capture_output=True, text=True,
            timeout=_HARNESS.CHILD_TIMEOUT,
        )
    finally:
        _HARNESS.stop_broadwayd(server)

    lauf = _HARNESS.Lauf(ergebnis.returncode, ergebnis.stdout,
                         ergebnis.stderr,
                         spur.read_text() if spur.exists() else "")
    lauf.ags_aufrufe = (
        ags_protokoll.read_text(encoding="utf-8").splitlines()
        if ags_protokoll.exists() else [])
    return lauf


@pytest.fixture(scope="module")
def laeufe(tmp_path_factory) -> dict:
    """Drei Laeufe, einer je Ziel. `ags bundle` kostet Sekunden."""
    return {ziel: _lauf(tmp_path_factory.mktemp(f"zahnrad-{ziel}"), ziel)
            for ziel in ZIELE}


def _bericht(lauf) -> str:
    return f"{lauf.bericht}\nags-Aufrufe: {lauf.ags_aufrufe}"


# ----------------------------------------------------------------------
# Die Gegenproben zuerst
# ----------------------------------------------------------------------

def test_die_liste_steht_mit_beiden_zeilen(laeufe):
    """Ohne Liste liest alles darunter leere Marken.

    Eine Zusicherung, die etwas NICHT sehen will, waere damit erfuellt,
    ohne dass es die Liste gibt.
    """
    for ziel, lauf in laeufe.items():
        assert lauf.marke("zeilen-anzahl") == "2", (
            f"{ziel}: die Liste zeigt nicht zwei Zeilen\n{_bericht(lauf)}")
        assert lauf.marke("ziel-zahnrad").startswith("GtkButton"), (
            f"{ziel}: in der zweiten Zeile ist kein Zahnrad zu finden\n"
            f"{_bericht(lauf)}")
        assert lauf.marke("ziel-schalter").startswith("GtkSwitch"), (
            f"{ziel}: in der zweiten Zeile ist kein Schalter zu finden\n"
            f"{_bericht(lauf)}")


def test_ohne_druck_setzt_die_seite_von_sich_aus_nichts_ab(laeufe):
    """DIE GEGENPROBE ZUR KENNUNGSMESSUNG.

    Ohne sie waere "nach dem Druck aufs Zahnrad steht eine Anfrage in
    der Datei" auch dann erfuellt, wenn die Seite beim Aufbauen von sich
    aus eine absetzt - die Zusicherung unten haette dann nicht das
    Zahnrad gemessen, sondern den Seitenaufbau.
    """
    lauf = laeufe["nichts"]
    assert lauf.ags_aufrufe == [], (
        "die Seite hat von sich aus ein `ags` gerufen, ohne dass jemand "
        f"etwas gedrueckt hat:\n{_bericht(lauf)}")


def test_in_jedem_lauf_ist_wirklich_gedrueckt_worden(laeufe):
    """Sonst waere "keine Wirkung" von "keine Betaetigung" nicht zu
    unterscheiden."""
    for ziel, lauf in laeufe.items():
        assert f"--gedrueckt:{ziel}--" in lauf.marke("fahrtenbuch"), (
            f"{ziel}: im Fahrtenbuch steht nicht, dass gedrueckt "
            f"wurde\n{_bericht(lauf)}")


# ----------------------------------------------------------------------
# Der Aufbau: ein Zahnrad JE Zeile, links vom Schalter, ausserhalb der
# Huelle
# ----------------------------------------------------------------------

def test_jede_zeile_hat_ein_zahnrad(laeufe):
    """"pro vpn" war die Bestellung.

    Gemessen je Zeile und nicht nur an der ersten: eine Liste, in der
    eine Zeile eines hat und die andere nicht, saehe nach einer Regel
    aus, die es nicht gibt.
    """
    lauf = laeufe["nichts"]
    assert lauf.marke("zahnrad-je-zeile") == "ja,ja", (
        "nicht jede Zeile traegt ein Zahnrad\n" + _bericht(lauf))


def test_das_zahnrad_steht_links_vom_schalter(laeufe):
    """Die Anordnung ist eine Ansage: Zahnrad, dann Schalter.

    Der Schalter ist das, was oft gedrueckt wird, und er bleibt an der
    Kante, wo er schon war - wer ihn blind trifft, soll ihn weiter blind
    treffen.
    """
    lauf = laeufe["nichts"]
    assert lauf.marke("ende-reihenfolge") == "zahnrad>schalter,zahnrad>schalter", (
        "die Reihenfolge im Zeilenende stimmt nicht\n" + _bericht(lauf))


def test_das_zahnrad_liegt_nicht_in_der_klickhuelle(laeufe):
    """Sonst waere es genau der Mangel, der am 01.09.2026 den Schalter traf.

    Ein bedienbares Kind IN einem Gtk.Button: der Tabulator erreicht es,
    die Leertaste dort loest aber die ZEILE aus. Fuer das Zahnrad faellt
    das mit `endeBedienbar` ohne Zutun weg - `ende` haengt als Ganzes
    NEBEN der Huelle. Gemessen, statt es aus der Herleitung zu folgern.
    """
    lauf = laeufe["nichts"]
    assert lauf.marke("zahnrad-unter-huelle") == "nein,nein", (
        "das Zahnrad steckt in der klickbaren Huelle der Zeile - dann "
        "loest die Leertaste darauf die Zeile aus statt die "
        "Einstellungen\n" + _bericht(lauf))


def test_das_zahnrad_nennt_seine_verbindung(laeufe):
    """Ein Zeichen ohne Wort braucht einen Namen, und der Name muss die
    Verbindung NENNEN.

    In der Liste stehen mehrere gleich aussehende Zahnraeder
    untereinander; "Einstellungen" allein sagt nicht, wessen.
    """
    lauf = laeufe["nichts"]
    namen = lauf.marke("zahnrad-name")
    for name in (_HARNESS.ZUHAUSE, ZIEL_NAME):
        assert name in namen, (
            f"kein Hinweistext nennt {name!r}: {namen!r}\n" + _bericht(lauf))


# ----------------------------------------------------------------------
# Die Wirkung
# ----------------------------------------------------------------------

def test_das_zahnrad_oeffnet_die_einstellungen_DIESER_verbindung(laeufe):
    """DIE ZUSICHERUNG DIESER DATEI.

    Gedrueckt wird das Zahnrad der ZWEITEN Zeile (c2), waehrend `active`
    auf die erste zeigt (c1). Stuende `gewaehlteId` im Quelltext statt
    `eintrag.id`, stuende hier `vpn-settings:c1`.
    """
    lauf = laeufe["zahnrad"]
    assert lauf.ags_aufrufe, (
        "das Zahnrad hat gar kein `ags` gerufen - die Einstellungen "
        f"gehen damit nicht auf\n{_bericht(lauf)}")
    erwartet = f"request vpn-settings:{ZIEL_KENNUNG}"
    assert any(erwartet == aufruf for aufruf in lauf.ags_aufrufe), (
        f"kein Aufruf lautet {erwartet!r}. Steht dort "
        f"`vpn-settings:{AKTIVE_KENNUNG}`, dann reicht die Vorlage "
        "`gewaehlteId` weiter statt `eintrag.id` - und das Zahnrad "
        "oeffnet die Verbindung, die die Einzelheit zeigt, statt der, "
        f"deren Zahnrad gedrueckt wurde.\n{_bericht(lauf)}")
    # Der Griff ist bis zum Ende durchgelaufen und nicht auf halbem Weg
    # geworfen: openVpnSettings ruft `schliessen()` als Letztes.
    assert "SCHLIESSEN" in lauf.marke("fahrtenbuch"), (
        "openVpnSettings hat `schliessen()` nicht erreicht\n"
        + _bericht(lauf))


def test_das_zahnrad_schaltet_nicht(laeufe):
    """Ein Weg zu den Einstellungen darf die Verbindung nicht anfassen.

    Waere das Zahnrad in der Huelle oder loeste es den Schalter mit aus,
    wuerde ein Blick in die Einstellungen einen Tunnel auf- oder abbauen.
    """
    lauf = laeufe["zahnrad"]
    buch = lauf.marke("fahrtenbuch")
    assert "ZAHNRAD-clicked" in buch, (
        "das Zahnrad hat gar nicht ausgeloest\n" + _bericht(lauf))
    assert "SCHALTER-notify" not in buch, (
        "der Druck aufs Zahnrad hat den Schalter mitbewegt\n"
        + _bericht(lauf))


def test_das_zahnrad_blaettert_nicht_in_die_einzelheit(laeufe):
    """Der Nutzer will DIREKT in die Einstellungen, nicht ueber die
    Einzelheit - das war die Meldung.

    Vorher UND nachher gelesen: ein Zustand, der schon vorher so war,
    belegt nichts.
    """
    lauf = laeufe["zahnrad"]
    vorher = lauf.marke("lage-vorher")
    nachher = lauf.marke("lage-nachher")
    assert vorher.startswith("ja|"), (
        f"die Liste war schon vor dem Druck nicht sichtbar ({vorher}) - "
        f"dann misst diese Zusicherung nichts\n{_bericht(lauf)}")
    assert nachher == vorher, (
        f"der Druck aufs Zahnrad hat die Ansicht gewechselt: {vorher} -> "
        f"{nachher}\n{_bericht(lauf)}")


def test_der_schalter_oeffnet_keine_einstellungen(laeufe):
    """Die Gegenrichtung, und sie ist der eigentliche Beweis.

    "Das Zahnrad oeffnet die Einstellungen" waere auch dann erfuellt,
    wenn JEDER Griff in der Zeile sie oeffnete - dann waere nicht das
    Zahnrad gemessen, sondern die Zeile.
    """
    lauf = laeufe["schalter"]
    assert "SCHALTER-notify" in lauf.marke("fahrtenbuch"), (
        "der Schalter hat sich gar nicht bewegt - dann misst diese "
        f"Zusicherung nichts\n{_bericht(lauf)}")
    assert not any("vpn-settings" in aufruf for aufruf in lauf.ags_aufrufe), (
        "das Umlegen des Schalters hat die Einstellungen geoeffnet\n"
        + _bericht(lauf))
    assert "ZAHNRAD-clicked" not in lauf.marke("fahrtenbuch"), (
        "das Umlegen des Schalters hat das Zahnrad mit ausgeloest\n"
        + _bericht(lauf))
