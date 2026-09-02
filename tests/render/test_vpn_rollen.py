# SPDX-License-Identifier: GPL-3.0-or-later
"""Das waagerechte Rollen im VPN-Fenster - reproduziert, dann weg.

WAS GEMELDET WURDE (01.09.2026), WOERTLICH
    "bei vpn kann mna nach rechts scrollen warum ?"

WAS IM BERICHT ZU AUFGABE 76 DAZU STAND, UND WARUM ES NICHT REICHT
    "Nicht direkt reproduziert. Die Rechnung passt aber: sein Fenster war
     604 statt 880 breit -> 578 Punkte Sichtfenster, die Fusszeile
     verlangt 626."

    Eine Rechnung, die passt, ist keine Reproduktion. Sie kann aus
    denselben zwei Zahlen bestehen und trotzdem die falsche Ursache
    benennen - genau das ist in derselben Aufgabe zweimal passiert (der
    Hoehendeckel, der gar nicht band; die Verschachtelung, die angeblich
    vier Fenster traf und eines trifft).

WAS DIESE DATEI TUT
    Sie stellt den Zustand VON VORHER wieder her und sieht nach, ob das
    Rollen dann da ist - und danach denselben Lauf mit dem
    ausgelieferten Stand, in dem es weg sein muss.

    Der Unterschied zwischen beiden ist EINE Aenderung: die zwei Zeilen
    `fuelltDieSprosse: true` und `fuelltDieHoehe: true` in der erzeugten
    VpnSettings.tsx. Ohne sie wird das Fenster so breit wie sein Inhalt
    (gemessen am 01.09.2026: 604 von 880), mit ihnen fuellt es seine
    Sprosse.

WORAN DAS ROLLEN ERKANNT WIRD
    An der Meldung, die die Fabrik selbst schreibt
    (ags-overlay-utils.template):

        Ueberlagerung "vpn-settings": Inhalt <n>px, Sichtfenster <m>px -
        <k>px breiter als das Fenster erlaubt.

    Sie steht dort seit dem 19.08.2026 und wird NUR geschrieben, wenn der
    Inhalt wirklich breiter ist als das Sichtfenster - also genau dann,
    wenn die waagerechte Bildlaufleiste erscheint. Das ist die Bedingung,
    unter der man "nach rechts scrollen" kann.

DIE EINZELHEITEN UND NICHT DIE LISTE
    Gemessen wird mit `ags request vpn-settings:c1`, also in der
    Detailansicht. Auf der Liste stuende die Fusszeile mit ihren vier
    Knoepfen zwar auch da, aber der breiteste Anspruch dieses Fensters
    entsteht erst mit Reiterleiste und Formular - und `onShow` faengt auf
    der Liste an. Genau diese Luecke hat test_vpn_breite.py bis zum
    01.09.2026 gehabt.

SICHERHEIT
    Verschachtelter Compositor mit eigenem XDG_RUNTIME_DIR und eigenem
    Sitzungsbus. Es wird keine Verbindung aufgebaut; die
    Einstellungsdatei entsteht unter tmp_path aus settings.defaults().
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.render.desktop_session import (             # noqa: E402
    Session, bundle, render_configuration, required_tools, workspaces_file,
)
from tests.render.test_vpn_breite import (             # noqa: E402
    MELDUNG, RAHMEN_UND_LEISTE, _modal_width_l, _shipped_settings,
)

SETTLE = 6.0
NAMENSRAUM = "vpn-settings"
BREITE, HOEHE = 1920, 1200

# Die zwei Zeilen, die das Fenster seine Sprosse ausfuellen lassen -
# woertlich aus der ERZEUGTEN Datei. Als Text und nicht als Muster, damit
# der Lauf LAUT scheitert, sobald jemand sie umschreibt: ein Muster, das
# nichts mehr findet, baute stillschweigend nichts aus, und die
# Gegenprobe waere gruen, ohne den alten Zustand hergestellt zu haben.
FUELLZEILEN = ("    fuelltDieSprosse: true,\n"
               "    fuelltDieHoehe: true,\n")

# Die modulweiten Vorrichtungen `vorher` und `nachher` zeichnen das
# VPN-Fenster zweimal in einer verschachtelten Sitzung. Zu Aufgabe 76
# stand da "nicht direkt reproduziert, die Rechnung passt aber" - eine
# Rechnung, die passt, ist keine Reproduktion. Waagerechtes Rollen sieht
# man nur, wenn wirklich gerollt wird.
pytestmark = pytest.mark.allow_subprocess


def _lauf(bau: Path, ohne_fuellen: bool) -> dict:
    """Das Fenster einmal in den Einzelheiten oeffnen und zusehen."""
    ags = render_configuration(bau)

    if ohne_fuellen:
        datei = ags / "widget" / "VpnSettings.tsx"
        text = datei.read_text(encoding="utf-8")
        assert FUELLZEILEN in text, (
            "die zwei Zeilen, mit denen das Fenster seine Sprosse "
            "ausfuellt, stehen nicht mehr so in der erzeugten "
            "VpnSettings.tsx. Diese Gegenprobe baut genau sie aus - "
            "findet sie sie nicht, stellt sie den alten Zustand gar "
            "nicht her und bewiese nichts. FUELLZEILEN nachziehen.")
        datei.write_text(text.replace(FUELLZEILEN, ""), encoding="utf-8")

    bundle(ags, bau)
    (bau / "zepos").mkdir(parents=True, exist_ok=True)
    (bau / "zepos" / "user-settings.json").write_text(
        _shipped_settings("ipsec"), encoding="utf-8")

    ergebnis: dict = {"ohne_fuellen": ohne_fuellen}
    with Session(BREITE, HOEHE) as sitzung:
        sitzung.start_bus()
        workspaces_file(bau, sitzung.output)
        sitzung.hyprctl("keyword", "cursor:invisible", "true")
        sitzung.wallpaper()
        sitzung.move_cursor(BREITE // 2, HOEHE // 2)
        sitzung.shell(bau / "zepos-shell.js", bau)
        time.sleep(SETTLE)

        # Aufwaermen - siehe test_vpn_breite.py.
        sitzung.request(NAMENSRAUM)
        frist = time.monotonic() + 45.0
        while time.monotonic() < frist:
            if sitzung.layers().get(NAMENSRAUM):
                break
            time.sleep(0.3)
        sitzung.request(NAMENSRAUM)
        time.sleep(2.0)

        antwort = sitzung.request(f"{NAMENSRAUM}:c1")
        ergebnis["antwort"] = antwort
        frist = time.monotonic() + 45.0
        while time.monotonic() < frist:
            if sitzung.layers().get(NAMENSRAUM):
                break
            time.sleep(0.3)
        time.sleep(8.0)

        ergebnis["flaeche"] = sitzung.layers().get(NAMENSRAUM)
        ergebnis["protokoll"] = sitzung.read_shell_log()
        ergebnis["bild"] = sitzung.shoot(
            bau / f"vpn-rollen-{'ohne' if ohne_fuellen else 'mit'}.png")

    ergebnis["meldungen"] = [
        (int(inhalt), int(sicht))
        for name, inhalt, sicht in MELDUNG.findall(ergebnis["protokoll"])
        if name == NAMENSRAUM]
    return ergebnis


@pytest.fixture(scope="module")
def vorher(tmp_path_factory) -> dict:
    """Der Zustand, ueber den der Nutzer geklagt hat."""
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Lauf fehlt: {', '.join(fehlt)}")
    return _lauf(tmp_path_factory.mktemp("vpn-rollen-ohne"), ohne_fuellen=True)


@pytest.fixture(scope="module")
def nachher(tmp_path_factory) -> dict:
    """Und der ausgelieferte Stand."""
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Lauf fehlt: {', '.join(fehlt)}")
    return _lauf(tmp_path_factory.mktemp("vpn-rollen-mit"), ohne_fuellen=False)


def _bericht(lauf: dict) -> str:
    return (f"ohne_fuellen={lauf['ohne_fuellen']} "
            f"Antwort={lauf.get('antwort')!r} Flaeche={lauf.get('flaeche')}\n"
            f"Meldungen: {lauf.get('meldungen')}\n"
            + lauf.get("protokoll", "")[-1500:])


def test_beide_laeufe_haben_das_fenster_gebaut(vorher, nachher):
    """Die Gegenprobe zuerst.

    Beide Zusicherungen darunter lesen Meldungen aus dem Protokoll. Ein
    Fenster, das gar nicht entstanden ist, schreibt keine - und der Lauf
    ohne Fuellzeilen waere dann "kein Rollen" statt "kein Fenster".
    """
    for lauf in (vorher, nachher):
        assert "VpnSettings loaded successfully" in lauf["protokoll"], (
            _bericht(lauf))
        assert lauf["flaeche"] is not None, _bericht(lauf)


def test_ohne_die_fuellzeilen_ist_das_fenster_zu_schmal(vorher):
    """DER ZUSTAND VON VORHER, wiederhergestellt und gemessen.

    GEMESSEN am 01.09.2026: 604 von 880 Punkten. Das ist die Zahl, aus
    der die Rechnung im Bericht bestand - hier steht sie als Messung.
    """
    breite = vorher["flaeche"][2]
    sprosse = _modal_width_l()
    print(f"\nohne Fuellzeilen: {breite} von {sprosse} Punkten")
    assert breite < sprosse, (
        f"das Fenster ist auch ohne die Fuellzeilen {breite} breit und "
        f"damit nicht schmaler als seine Sprosse ({sprosse}). Dann stellt "
        "diese Gegenprobe den alten Zustand nicht mehr her, und die "
        f"Zusicherung darunter misst nichts:\n{_bericht(vorher)}")


def test_ohne_die_fuellzeilen_rollt_das_fenster_waagerecht(vorher):
    """DIE REPRODUKTION.

    Die Fabrik meldet einen Ueberhang genau dann, wenn der Inhalt breiter
    ist als das Sichtfenster - also genau dann, wenn man nach rechts
    rollen kann. Ohne die Fuellzeilen muss diese Meldung da sein.

    Ist sie es NICHT, dann war die Rechnung im Bericht falsch und die
    Ursache des Rollens eine andere. Der Fehlschlagtext sagt das, damit
    niemand die Rechnung stehenlaesst, weil sie plausibel klingt.
    """
    assert vorher["meldungen"], (
        "die Fabrik hat KEINEN Ueberhang gemeldet, obwohl das Fenster "
        f"nur {vorher['flaeche'][2]} von {_modal_width_l()} Punkten breit "
        "ist. Damit ist das waagerechte Rollen NICHT reproduziert, und "
        "die Erklaerung aus dem Bericht zu Aufgabe 76 ('das Fenster war "
        "zu schmal') traegt nicht. Die Ursache ist dann eine andere und "
        f"gehoert gesucht:\n{_bericht(vorher)}")
    zu_breit = [(inhalt, sicht) for inhalt, sicht in vorher["meldungen"]
                if inhalt > sicht]
    print(f"\nohne Fuellzeilen, Ueberhang: {zu_breit}")
    assert zu_breit, _bericht(vorher)


def test_mit_den_fuellzeilen_ist_das_rollen_weg(nachher):
    """UND DIE HEILUNG, am selben Aufbau.

    Dasselbe Fenster, dieselbe Ansicht, dieselbe Einstellungsdatei - nur
    mit den zwei Zeilen. Der Inhalt muss jetzt in das passen, was Sprosse
    L uebriglaesst.
    """
    erlaubt = _modal_width_l() - RAHMEN_UND_LEISTE
    zu_breit = [(inhalt, sicht) for inhalt, sicht in nachher["meldungen"]
                if inhalt > erlaubt]
    print(f"\nmit Fuellzeilen: Flaeche {nachher['flaeche'][2]}, "
          f"Meldungen {nachher['meldungen']}, erlaubt {erlaubt}")
    assert zu_breit == [], (
        f"der Inhalt verlangt mehr als die {erlaubt} Punkte, die Sprosse "
        f"L uebriglaesst: {zu_breit}\n{_bericht(nachher)}")
    assert nachher["flaeche"][2] == _modal_width_l(), (
        f"das Fenster steht {nachher['flaeche'][2]} Punkte breit statt "
        f"auf seiner Sprosse ({_modal_width_l()}):\n{_bericht(nachher)}")


def test_es_gibt_ein_bild_von_beiden(vorher, nachher):
    """Der Bildbeweis, in der Groesse des Nutzers - vorher und nachher."""
    for lauf in (vorher, nachher):
        bild = lauf["bild"]
        assert bild.is_file() and bild.stat().st_size > 0, bild
        print(f"\nBildbeweis ({'ohne' if lauf['ohne_fuellen'] else 'mit'} "
              f"Fuellzeilen): {bild}")
