# SPDX-License-Identifier: GPL-3.0-or-later
"""Die VPN-Liste mit drei Eintraegen, auf dem Schirm des Nutzers.

WARUM 1920x1200 UND NICHT 1920x1080
    Das ist die Aufloesung, an der der Nutzer sitzt. Der Bildbeweis vom
    22.08.2026 (tests/render/test_vpn_breite.py) entstand auf 1920x1080
    - er hat den Fehler, um den es hier geht, nicht gefunden, und ein
    Bild in falscher Groesse ist die gefaehrlichste Sorte Beleg: es
    sieht aus wie eine Pruefung.

    Nach `hyprctl monitors` der laufenden Sitzung wird NICHT gefragt.
    Session(w, h) legt einen headless-Ausgang in der geforderten Groesse
    an; die Sitzung des Menschen wird dabei nicht angesehen und nicht
    angefasst.

WARUM DREI VERBINDUNGEN
    "bei wireguard, weil ich dort mehrere vpns habe und alle darueber
     verwaltbar sein muessen" - und der Platz, den eine Liste braucht,
    ist eine Frage an ihre Laenge. Mit zweien sah die waagerechte Reihe
    vom 22.08.2026 noch aus wie eine Liste; ab der dritten nicht mehr.

WAS HIER GEMESSEN WIRD, UND WAS test_vpn_breite.py MISST
    Dort: ob der INHALT des Einstellungsfensters breiter ist als seine
    Sprosse (an `hadj.get_upper()`, aus der Meldung der Fabrik).
    Hier: welche Flaeche die beiden Fenster auf dem Schirm des Nutzers
    wirklich BEKOMMEN (`hyprctl layers`) - und ein Bild davon.

    Beides zusammen ist die Antwort auf "wieviel hat die Seite": die
    Sprosse ist das Angebot, die Flaeche ist das, was ankommt.

SICHERHEIT
    Verschachtelter Compositor mit eigenem XDG_RUNTIME_DIR und eigenem
    Sitzungsbus. Es wird keine Verbindung aufgebaut und keine
    Zugangsdatei gelesen: die Einstellungsdatei entsteht unter tmp_path
    aus settings.defaults(), und src/generate_config.sh laeuft nicht
    (siehe der Kopf von desktop_session.py).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.render.desktop_session import (             # noqa: E402
    Session, bundle, render_configuration, required_tools, workspaces_file,
)

SETTLE = 6.0

# Die Anfrage, die die Schale auf der VPN-Seite oeffnet, und der
# Namensraum der Flaeche, die dabei entsteht. Sie sind NICHT dasselbe -
# seit Aufgabe 9 gibt es kein eigenes VPN-Fenster mehr, die Seite lebt in
# der Schale. Dieselbe Unterscheidung wie in test_vpn_breite.py.
SEITE_ANFRAGE = "vpn"
SCHALE = "control"
FENSTER = "vpn-settings"

# Die Bildschirmgroesse des Nutzers.
BREITE, HOEHE = 1920, 1200

# Die modulweite Vorrichtung `messung` legt einen headless-Ausgang in
# 1920x1200 an - der Aufloesung, an der der Nutzer sitzt - und zeichnet
# die VPN-Liste darin. Der Bildbeweis in 1920x1080 hat diesen Fehler
# nicht gefunden: ein Bild in falscher Groesse sieht aus wie eine
# Pruefung. Nach der laufenden Sitzung wird NICHT gefragt.
pytestmark = pytest.mark.allow_subprocess


def _sprosse(name: str) -> int:
    """Eine Sprosse aus DERSELBEN Quelle, aus der die Vorlage sie holt.

    Nicht abgeschrieben - dieselbe Begruendung wie bei _modal_width_l()
    in test_vpn_breite.py: eine abgeschriebene Erwartung misst die
    Abschrift.
    """
    sys.path.insert(0, str(ROOT / "src"))
    try:
        import sizes
        return sizes.MODAL_WIDTH(name)
    finally:
        sys.path.remove(str(ROOT / "src"))


def _drei_verbindungen() -> str:
    """Drei Verbindungen, drei Bauarten - aus settings.defaults()."""
    sys.path.insert(0, str(ROOT / "src"))
    try:
        import settings
        dokument = settings.defaults()

        arbeit = dict(settings.default_connection())
        arbeit.update({"id": "c1", "kind": "ipsec",
                       "connection_name": "arbeit",
                       "server": "gateway.example.invalid"})

        zuhause = dict(settings.default_connection())
        zuhause.update({"id": "c2", "kind": "wireguard",
                        "connection_name": "zuhause"})
        zuhause["wireguard"] = dict(zuhause["wireguard"])
        zuhause["wireguard"]["peers"] = [{
            "public_key": "", "endpoint": "heim.example.invalid:51820",
            "allowed_ips": ["10.9.0.0/24"], "keepalive": 25,
            "preshared_key_file": "",
        }]

        reise = dict(settings.default_connection())
        reise.update({"id": "c3", "kind": "openvpn",
                      "connection_name": "reise"})
        reise["openvpn"] = dict(reise["openvpn"])
        reise["openvpn"]["remote"] = "ovpn.reise.example.invalid"
        reise["openvpn"]["port"] = 1194
        reise["openvpn"]["connection_type"] = "password-tls"
        reise["openvpn"]["username"] = "jemand"

        dokument["vpn"] = {"active": "c1",
                           "connections": [arbeit, zuhause, reise]}
        return json.dumps(dokument, indent=2)
    finally:
        sys.path.remove(str(ROOT / "src"))


def _oeffne(sitzung: Session, anfrage: str, flaeche: str) -> tuple:
    """Eine Anfrage stellen und warten, bis die Flaeche dasteht.

    GERUETTELT STATT GEWARTET, und nur EIN `ags request` - beides
    abgeschrieben von test_vpn_breite.py/test_schale_stil.py, wo es
    begruendet steht: die Flaeche bleibt in einem Teil der Laeufe laenger
    als 20 Sekunden aus, und ein zweiter Aufruf knipst das gerade
    erschienene Fenster wieder zu (GJS ist einstraengig).
    """
    antwort = sitzung.request(anfrage)
    assert "toggled" in antwort or "shown" in antwort, (
        f"ags request {anfrage} antwortete {antwort!r}")
    frist = time.monotonic() + 45.0
    platte = None
    while time.monotonic() < frist:
        platte = sitzung.layers().get(flaeche)
        if platte:
            break
        time.sleep(0.3)
    assert platte, (
        f"keine Flaeche '{flaeche}' nach 'ags request {anfrage}' "
        f"(Antwort: {antwort!r}):\n" + sitzung.read_shell_log())
    # Die erste Zuteilung ist oft noch ein Platzhalter.
    time.sleep(3.0)
    return sitzung.layers().get(flaeche)


def _lauf(bau: Path) -> dict:
    ags = render_configuration(bau)
    bundle(ags, bau)
    (bau / "zepos").mkdir(parents=True, exist_ok=True)
    (bau / "zepos" / "user-settings.json").write_text(
        _drei_verbindungen(), encoding="utf-8")

    ergebnis: dict = {}
    with Session(BREITE, HOEHE) as sitzung:
        sitzung.start_bus()
        workspaces_file(bau, sitzung.output)
        # Der Mauspfeil waere auf dem Bild ein Befund, der keiner ist.
        sitzung.hyprctl("keyword", "cursor:invisible", "true")
        sitzung.wallpaper()
        # DER ZEIGER MUSS AUF DEN ABGEBILDETEN SCHIRM - sonst erscheint
        # die Schale ueberhaupt nicht (utils/overlay.ts fragt `hyprctl
        # cursorpos`). Begruendet in desktop_session.move_cursor().
        sitzung.move_cursor(BREITE // 2, HOEHE // 2)
        sitzung.shell(bau / "zepos-shell.js", bau)
        # AUF DIE RUHE UND NICHT AUF DIE UHR - seit dem 04.09.2026.
        # Hier stand ein fester Schlaf. Warum "die Flaeche ist da"
        # dafuer nicht reicht - und mit welchen Zahlen das gemessen
        # ist - steht bei Session.warte_auf_ruhe().
        sitzung.warte_auf_ruhe("zepos-bar", "zepos-dock",
                               frist=40.0)

        # AUFWAERMEN: der allererste `ags request` einer Sitzung laesst
        # die Flaeche in einem Teil der Laeufe nicht erscheinen - siehe
        # den Kommentar dazu in test_vpn_breite.py.
        sitzung.request(SCHALE)
        frist = time.monotonic() + 45.0
        while time.monotonic() < frist:
            if sitzung.layers().get(SCHALE):
                break
            time.sleep(0.3)
        sitzung.request(SCHALE)
        time.sleep(2.0)

        ergebnis["schale"] = _oeffne(sitzung, SEITE_ANFRAGE, SCHALE)
        ergebnis["bild_schale"] = sitzung.shoot(bau / "vpn-liste-1920x1200.png")
        sitzung.request(SCHALE)
        frist = time.monotonic() + 15.0
        while time.monotonic() < frist:
            if not sitzung.layers().get(SCHALE):
                break
            time.sleep(0.3)
        time.sleep(1.0)

        ergebnis["fenster"] = _oeffne(sitzung, FENSTER, FENSTER)
        ergebnis["bild_fenster"] = sitzung.shoot(
            bau / "vpn-einstellungen-liste-1920x1200.png")

        # UND DASSELBE FENSTER IN DEN EINZELHEITEN - NACHGETRAGEN am
        # 01.09.2026
        #
        #     Bis hierher hat diese Datei (und test_vpn_breite.py daneben)
        #     nur die LISTE gemessen: `onShow` faengt dort an, und ein
        #     Klick laesst sich unter Hyprland nicht erzeugen. Die
        #     Einzelheiten - Reiterleiste, Formular, die vierteilige
        #     Fusszeile, an der die ganze Breitenrechnung dieses Fensters
        #     haengt - waren dabei `visible: false`, und ein unsichtbares
        #     Widget zaehlt in GTK4 nicht in die Messung seines Elterns.
        #     Gemessen wurde also genau die Ansicht, ueber die niemand
        #     geklagt hat.
        #
        #     Seit dem 01.09.2026 gibt es einen Weg dorthin OHNE Klick:
        #     `ags request vpn-settings:<kennung>` (siehe
        #     gewuenschteKennung in ags-vpn-settings.template). Er ist
        #     fuer den Nutzer gebaut worden - er benutzt ihn, wenn er auf
        #     einer Zeile das Zahnrad drueckt -, und er macht diese
        #     Messung nebenbei erst moeglich.
        sitzung.request(FENSTER)
        frist = time.monotonic() + 15.0
        while time.monotonic() < frist:
            if not sitzung.layers().get(FENSTER):
                break
            time.sleep(0.3)
        time.sleep(1.0)
        ergebnis["fenster_detail"] = _oeffne(sitzung, f"{FENSTER}:c1", FENSTER)
        ergebnis["bild_detail"] = sitzung.shoot(
            bau / "vpn-einstellungen-detail-1920x1200.png")

        ergebnis["protokoll"] = sitzung.read_shell_log()
    return ergebnis


@pytest.fixture(scope="module")
def messung(tmp_path_factory) -> dict:
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Bildlauf fehlt: {', '.join(fehlt)}")
    return _lauf(tmp_path_factory.mktemp("zepvpn-platz"))


def test_die_schale_steht_auf_ihrer_sprosse(messung):
    """Was die Schale auf 1920x1200 wirklich bekommt.

    Die Sprosse ist das Angebot (SHELL_WIDTH = MODAL_WIDTH("L") = 880),
    `hyprctl layers` ist das, was ankommt. Beides auseinanderzuhalten ist
    der Grund fuer diese Datei: am 19.08.2026 stand die Schale mit 775
    bis 829 Punkten da, wo 880 angemeldet waren, und niemand hat es
    gemessen, bevor der Nutzer es gemeldet hat.
    """
    x, y, breite, hoehe = messung["schale"]
    print(f"\nDie Schale auf {BREITE}x{HOEHE}: {breite}x{hoehe} an {x},{y} "
          f"(Sprosse L = {_sprosse('L')})")
    assert breite == _sprosse("L"), (
        f"die Schale ist {breite} breit statt {_sprosse('L')}")


def test_das_einstellungsfenster_steht_auf_ihr_auch(messung):
    """Dasselbe fuer das Einstellungsfenster - es steht seit dem
    21.08.2026 ebenfalls auf Sprosse L."""
    x, y, breite, hoehe = messung["fenster"]
    print(f"\nDas Einstellungsfenster auf {BREITE}x{HOEHE}: {breite}x{hoehe} "
          f"an {x},{y} (Sprosse L = {_sprosse('L')})")
    assert breite <= _sprosse("L"), (
        f"das Einstellungsfenster ist {breite} breit und damit breiter als "
        f"seine Sprosse ({_sprosse('L')})")


def test_beide_flaechen_passen_auf_den_schirm(messung):
    """Kein Fenster haengt ueber den Rand.

    Die Fabrik deckelt auf `pos.width`/`pos.height`; diese Zusicherung
    haelt fest, dass der Deckel auf DIESEM Schirm auch greift - auf
    1920x1200 hat noch nie jemand nachgesehen.
    """
    for name in ("schale", "fenster"):
        x, y, breite, hoehe = messung[name]
        assert x >= 0 and y >= 0, f"{name} beginnt bei {x},{y}"
        assert x + breite <= BREITE, (
            f"{name} reicht bis {x + breite}, der Schirm ist {BREITE} breit")
        assert y + hoehe <= HOEHE, (
            f"{name} reicht bis {y + hoehe}, der Schirm ist {HOEHE} hoch")


def _aus_sizes(name: str):
    """Einen Wert aus der Groessentabelle holen, ohne ihn abzuschreiben.

    Dieselbe Begruendung wie bei _sprosse() oben: eine abgeschriebene
    Erwartung misst die Abschrift.
    """
    sys.path.insert(0, str(ROOT / "src"))
    try:
        import sizes
        return getattr(sizes, name)
    finally:
        sys.path.remove(str(ROOT / "src"))


def _hoehendeckel() -> int:
    """Was der Deckel auf DIESEM Schirm hoechstens zulaesst.

    Der harte Platz (nutzbare Hoehe minus zweimal Rand) bleibt aussen
    vor: er haengt an der Dicke der Leiste, die ihrerseits am
    Groessenregler haengt, und auf 1200 bindet er nicht. Er ist die
    Grenze fuer kleine Schirme, und ueber die klagt hier niemand.
    """
    anteil = (_aus_sizes("MEASURE_MODAL_SHARE")
              * _aus_sizes("MEASURE_MODAL_HEIGHT_FACTOR"))
    return min(int(_aus_sizes("MODAL_HEIGHT")), int(HOEHE * anteil))


def test_die_schale_ist_nicht_mehr_auf_die_halbe_schirmhoehe_gedeckelt(messung):
    """Die Hoehe, um die der Nutzer ZWEIMAL gebeten hat.

    WOERTLICH
        "kannst du die vpn ags fenster deutlich hoeher machen 1,5
         ungefaehr also nochmal hoeher"
        "die vpn ags fenster hoeher das ist zu gequetscht alles"

    "Nochmal hoeher" heisst, dass es schon einmal versucht wurde - und
    genau das erklaert, warum nichts passierte: erhoeht wurde der WUNSCH
    (SHELL_HEIGHT = 900 seit dem 18.08.2026), geantwortet hat der DECKEL.
    Der stand auf der halben Schirmhoehe, auf 1200 also auf 600, und war
    damit immer der kleinere der beiden.

    GEMESSEN am 01.09.2026 auf 1920x1200:

        vorher (Anteil 0,5)             600
        jetzt  (Anteil 0,5 mal 1,5)     900

    Und 900 ist zugleich sizes.MODAL_HEIGHT: Wunsch und Deckel treffen
    sich auf diesem Schirm. Genau daran ist zu sehen, dass der Wunsch
    ankommt - stuende hier wieder 600, waere der Faktor weg.

    WARUM DIESE ZUSICHERUNG HIER STEHT UND NICHT IN tests/src/
        Eine Rechnung ueber die Zahlen in den Vorlagen haette die 900
        gelesen und Erfolg gemeldet. Auf dem Schirm standen 600. Der
        Unterschied zwischen Wunsch und Wirklichkeit IST dieser Fehler.
    """
    x, y, breite, hoehe = messung["schale"]
    erwartet = _hoehendeckel()
    print(f"\nDie Schale auf {BREITE}x{HOEHE}: {breite}x{hoehe} an {x},{y} "
          f"(Hoehendeckel = {erwartet})")
    assert hoehe == erwartet, (
        f"die Schale steht {hoehe} Punkte hoch, erlaubt und gewuenscht "
        f"sind {erwartet}. Sind es "
        f"{int(HOEHE * _aus_sizes('MEASURE_MODAL_SHARE'))}, deckelt wieder "
        f"die halbe Schirmhoehe - siehe MEASURE_MODAL_HEIGHT_FACTOR in "
        f"src/sizes.py.")


def test_das_einstellungsfenster_oeffnet_die_angeklickte_verbindung(messung):
    """`ags request vpn-settings:c1` fuehrt in DIESE Verbindung.

    GEMELDET, woertlich: "ich muss mich voll komisch durchklicken sobald
    ich auf eine vpn gehe dann auf icon einstellung will ich direkt dort
    landen". Bis zum 01.09.2026 ging von der VPN-Seite nur
    `ags request vpn-settings` los - ohne jede Angabe, welche Verbindung
    gemeint ist. Das Fenster fing daraufhin immer auf seiner Liste an.

    WAS HIER ZUGESICHERT WIRD UND WAS NICHT
        Dass die Anfrage MIT Kennung angenommen wird und ein Fenster
        entsteht. Dass darin die richtige Verbindung steht, sagt das Bild
        (bild_detail) und keine Zusicherung: der Inhalt einer Layer-
        Flaeche ist von aussen nicht auszulesen, und ein Bildvergleich
        haenge daran, welche Schrift die Maschine gerade hat. Das ist
        eine Luecke, und sie soll dastehen.
    """
    assert messung["fenster_detail"] is not None, (
        "keine Flaeche nach `ags request vpn-settings:c1`:\n"
        + messung["protokoll"][-2000:])
    bild = messung["bild_detail"]
    assert bild.is_file() and bild.stat().st_size > 0, bild
    print(f"\nBildbeweis der Einzelheiten: {bild}")


def test_die_einzelheiten_bekommen_mehr_als_die_halbe_schirmhoehe(messung):
    """Und das Formular selbst ist nicht mehr auf 600 gedeckelt.

    Es trug sein `height: 600` bis zum 01.09.2026 als getippte Zahl. Sie
    war zufaellig genau der Deckel dieses Schirms, also war nie zu sehen,
    welche der beiden Grenzen antwortete.

    DIE SCHRANKE IST EINE UNTERE UND KEINE GLEICHHEIT: wie hoch das
    Fenster wirklich wird, entscheidet daneben der INHALT - die Fabrik
    nimmt `min(natuerliche Hoehe, Deckel)`. Eine Gleichheit waere eine
    Zusicherung ueber die Zeilenzahl dieses Formulars und nicht ueber den
    Deckel.
    """
    x, y, breite, hoehe = messung["fenster_detail"]
    alter_deckel = int(HOEHE * _aus_sizes("MEASURE_MODAL_SHARE"))
    print(f"\nDie Einzelheiten auf {BREITE}x{HOEHE}: {breite}x{hoehe} "
          f"an {x},{y} (alter Deckel = {alter_deckel})")
    assert hoehe > alter_deckel, (
        f"das Einstellungsfenster steht {hoehe} Punkte hoch und damit "
        f"nicht hoeher als der alte Deckel ({alter_deckel}). Entweder "
        f"greift der Faktor nicht, oder der Inhalt ist kuerzer als der "
        f"Deckel - im zweiten Fall ist nicht die Hoehe das Problem, "
        f"sondern der senkrechte Rhythmus darin.")
    assert hoehe <= _hoehendeckel(), (
        f"das Einstellungsfenster steht {hoehe} Punkte hoch und damit "
        f"ueber dem Deckel von {_hoehendeckel()}")
    assert y + hoehe <= HOEHE, (
        f"die Einzelheiten reichen bis {y + hoehe}, der Schirm ist "
        f"{HOEHE} hoch")


def test_es_gibt_ein_bild_von_der_liste(messung):
    """Der Bildbeweis, in der Groesse des Nutzers.

    Er ist der Grund, aus dem diese Datei entstanden ist: der Beweis vom
    22.08.2026 lief auf 1920x1080 und hat weder die waagerechte Reihe im
    Einstellungsfenster noch den Platzmangel gefunden.
    """
    for schluessel in ("bild_schale", "bild_fenster"):
        bild = messung[schluessel]
        assert bild.is_file() and bild.stat().st_size > 0, bild
        print(f"\nBildbeweis: {bild}")
