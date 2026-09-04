# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Fuss ist so breit wie seine Symbole - auch wieder schmaler.

WAS BESTELLT WURDE
    Der Nutzer am 20.08.2026, woertlich: "ausserdem passt sich die dock
    nicht an die aktuelle zahl der icons an. wenn wir neue terminals
    haben und sie entfernt werden bleibt die dock gleich lang".

WARUM DAS NUR HIER MESSBAR IST
    Kopflos (tests/src/dock_headless_child.tsx) waere die Antwort immer
    gruen gewesen, und zwar zu Recht: der INHALT hat nie falsch
    gerechnet. GEMESSEN am 20.08.2026 mit einer Sonde in update(), die
    bei jedem Ereignis die natuerliche Breite der Knopfreihe neben die
    zugeteilte gestellt hat:

        ein Fenster geht auf   nat 411   zugeteilt 353 -> 411
        ein zweites geht auf   nat 460   zugeteilt 411 -> 460
        eines geschlossen      nat 411   zugeteilt 460   (bleibt)
        beide geschlossen      nat 353   zugeteilt 460   (bleibt)

    Die Reihe misst sich also tadellos schmaler. Was stehenblieb, war
    die LAYER-SHELL-FLAECHE - und die gibt es nur an einem Compositor.

    Das ist zugleich die Antwort auf den ersten Verdacht: die Aenderung
    vom selben Tag, die minimierte Fenster im Fuss stehen laesst
    (0e25b63), hat damit NICHTS zu tun. Sie haelt einen Knopf, dessen
    Fenster noch existiert; hier verschwindet das Fenster ganz, der
    Knopf geht mit, und die Reihe misst sich schmaler. Nur die Flaeche
    fragte nicht nach.

WAS AUSSER DER BREITE GEMESSEN WIRD
    Die untere reservierte Zone. Der Fuss ist EXKLUSIV: was er sich
    nimmt, fehlt jedem Fenster des Schirms. Blieb er zu breit stehen und
    dabei auch zu hoch, kostete das dauerhaft Bildschirmhoehe fuer einen
    Knopf, den es nicht mehr gibt - GEMESSEN 96 statt 84 Punkte, bis die
    Oberflaeche neu startete.
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.render.desktop_session import (                      # noqa: E402
    Session, bundle, render_configuration, required_tools, workspaces_file,
)

BREITE, HOEHE = 1920, 1080
SETTLE = 7.0

# Wie lange nach jedem Fenster gewartet wird. Der Fuss haengt an Hyprlands
# Ereignisstrom; gemessen wird das Ergebnis, nicht die Dauer.
RUHE = 4.0

DOCK = "zepos-dock"

# Das Fenster, mit dem gemessen wird. ZWEI davon, und zwar vom selben
# Programm: gleiche Fenster geben gleich breite Knoepfe, also haengt der
# Unterschied zwischen den Stufen nur an der Reihe und nicht daran,
# welches Symbol ein Programm mitbringt.
TERMINAL = "foot"

# Die modulweite Vorrichtung `breite` misst die BEMALTE Breite des
# Fusses in einer verschachtelten Sitzung. Kopflos war die Antwort immer
# gruen, und zwar zu Recht: der Inhalt hat nie falsch gerechnet, die
# Flaeche blieb trotzdem stehen. Die Breite einer Layer-Flaeche kennt
# nur der Compositor.
pytestmark = pytest.mark.allow_subprocess


def _reserviert_unten(sitzung: Session) -> int:
    daten = sitzung.hyprctl_json("monitors") or []
    for monitor in daten:
        if monitor.get("name") == sitzung.output:
            return monitor["reserved"][3]
    raise AssertionError(f"{sitzung.output} steht nicht in hyprctl monitors")


def _stand(sitzung: Session) -> tuple:
    """Kasten des Fusses und die untere reservierte Zone."""
    return (sitzung.layers().get(DOCK), _reserviert_unten(sitzung))


def _schliesse(sitzung: Session, klasse: str) -> None:
    """Ein Fenster dieser Klasse schliessen - ueber den Compositor."""
    for client in (sitzung.hyprctl_json("clients") or []):
        if client.get("class") == klasse:
            sitzung.hyprctl("dispatch", "closewindow",
                            f"address:{client['address']}")
            return
    raise AssertionError(f"kein Fenster der Klasse {klasse} offen")


@pytest.fixture(scope="module")
def breite(tmp_path_factory) -> dict:
    """Zwei Fenster auf, zwei Fenster zu, fuenf Messungen."""
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Bildlauf fehlt: {', '.join(fehlt)}")
    if shutil.which(TERMINAL) is None:
        pytest.skip(f"{TERMINAL} fehlt - ohne ein Fenster waechst der Fuss nie")

    bau = tmp_path_factory.mktemp("zepbreite-bau")
    ags = render_configuration(bau)
    schale = bundle(ags, bau)

    with Session(BREITE, HOEHE) as sitzung:
        sitzung.start_bus()
        workspaces_file(bau, sitzung.output)
        sitzung.hyprctl("keyword", "cursor:invisible", "true")
        sitzung.wallpaper()
        sitzung.shell(schale, bau)
        # AUF DIE RUHE UND NICHT AUF DIE UHR - seit dem 04.09.2026.
        # "Die Flaeche ist da" reicht nicht: gemessen stand der Fuss
        # dann auf (860, 880, 200, 200) statt auf (784, 996, 353, 60).
        # Die Begruendung steht bei Session.warte_auf_ruhe().
        sitzung.warte_auf_ruhe("zepos-dock", "zepos-bar", frist=40.0)

        leer = _stand(sitzung)
        assert leer[0] is not None, (
            "der Fuss liegt gar nicht auf dem Schirm:\n"
            + sitzung.read_shell_log())

        # AUF DIE AENDERUNG UND NICHT AUF DIE UHR - seit dem
        # 04.09.2026. Gewartet wird genau auf das, was diese Datei misst:
        # dass der Fuss auf ein Fenster reagiert. WAS er dann anzeigt,
        # sagen die Zusicherungen unten - der Wartevorgang nimmt ihnen
        # nichts ab.
        # ANDERS ALS VORHER *UND* ZUR RUHE GEKOMMEN.
        #
        #     Der erste Versuch wartete nur auf "anders als vorher" und
        #     war GEMESSEN falsch: der Fuss geht ueber ZWISCHENSTUFEN -
        #     das Fenster ist da, die Breite noch nicht nachgezogen.
        #     Wer die erste Abweichung nimmt, misst die Zwischenstufe,
        #     und der naechste Schritt vergleicht dann gegen einen Stand,
        #     den es nie gab. Der Lauf endete mit "der Fuss hat das
        #     geschlossene Fenster bemerkt (zuletzt: None)".
        #
        #     Zwei gleiche Messungen hintereinander heissen: er ist
        #     fertig. Das ist dieselbe Aussage, die die sechs Sekunden
        #     behaupten wollten - nur gepruft statt geschaetzt.
        def ruhig_und_anders(vorher):
            zuletzt = {"stand": None}

            def pruefe():
                jetzt = _stand(sitzung)
                vorher_gesehen = zuletzt["stand"]
                zuletzt["stand"] = jetzt
                if jetzt == vorher:
                    return None
                return jetzt if jetzt == vorher_gesehen else None

            return pruefe

        def anders_als(vorher):
            return ruhig_und_anders(vorher)

        sitzung.spawn([TERMINAL])
        eins = sitzung.warte_bis(anders_als(leer), frist=25.0,
                                 was="der Fuss hat das erste Fenster bemerkt")

        sitzung.spawn([TERMINAL])
        zwei = sitzung.warte_bis(anders_als(eins), frist=25.0,
                                 was="der Fuss hat das zweite Fenster bemerkt")

        _schliesse(sitzung, TERMINAL)
        wieder_eins = sitzung.warte_bis(
            anders_als(zwei), frist=25.0,
            was="der Fuss hat das geschlossene Fenster bemerkt")

        _schliesse(sitzung, TERMINAL)
        wieder_leer = sitzung.warte_bis(
            anders_als(wieder_eins), frist=25.0,
            was="der Fuss ist wieder leer")

        protokoll = sitzung.read_shell_log()

    return {
        "leer": leer, "eins": eins, "zwei": zwei,
        "wieder_eins": wieder_eins, "wieder_leer": wieder_leer,
        "protokoll": protokoll,
    }


def test_jedes_fenster_macht_den_fuss_breiter(breite):
    """Die Gegenprobe. Ohne sie sagte 'er schrumpft wieder' nichts - ein
    Fuss, der gar nicht erst waechst, erfuellt sie auch."""
    leer, eins, zwei = breite["leer"][0], breite["eins"][0], breite["zwei"][0]
    assert eins[2] > leer[2], (
        f"mit einem Fenster ist der Fuss {eins[2]} statt mehr als "
        f"{leer[2]} Punkte breit:\n" + breite["protokoll"])
    assert zwei[2] > eins[2], (
        f"mit zwei Fenstern ist der Fuss {zwei[2]} statt mehr als "
        f"{eins[2]} Punkte breit")
    # UND DIE ERSTE STUFE IST GROESSER ALS DIE ZWEITE, obwohl es
    # zweimal dasselbe Fenster ist. GEMESSEN am 20.08.2026 bei der
    # ausgelieferten Groesse: 353 -> 411 -> 460, also +58 und +49.
    #
    # Die neun Punkte Unterschied sind der TRENNER. Er steht immer im
    # Kasten, wird aber erst sichtbar, wenn hinter ihm etwas steht
    # (`separator.set_visible(pins.length > 0 && loose.length > 0)` in
    # ags-dock.template) - das erste lose Fenster bringt also einen
    # Knopf UND den Trenner mit, jedes weitere nur noch einen Knopf.
    #
    # Erwartet wird deshalb genau diese Ordnung und keine Gleichheit;
    # feste Zahlen stehen hier nicht, weil Symbolgroesse und Abstaende
    # einstellbar sind.
    assert eins[2] - leer[2] > zwei[2] - eins[2], (
        f"die erste Stufe ({leer[2]} -> {eins[2]}) ist nicht groesser "
        f"als die zweite ({eins[2]} -> {zwei[2]}) - dann bringt das "
        "erste lose Fenster seinen Trenner nicht mit")


def test_ein_geschlossenes_fenster_macht_ihn_wieder_schmaler(breite):
    """DIE BESTELLUNG. Vor dem 20.08.2026 blieb der Fuss auf seiner
    groessten je erreichten Breite stehen."""
    assert breite["wieder_eins"][0] == breite["eins"][0], (
        "nach dem Schliessen des zweiten Fensters steht der Fuss auf "
        f"{breite['wieder_eins'][0]} statt wieder auf {breite['eins'][0]}")


def test_am_ende_steht_er_genau_so_da_wie_am_anfang(breite):
    """Nicht ungefaehr, sondern auf den Punkt: derselbe Kasten, dieselbe
    Lage. Ein Fuss, der nach zwei Fenstern zehn Punkte breiter bleibt,
    ist nach zwanzig Fenstern hundert breiter."""
    assert breite["wieder_leer"][0] == breite["leer"][0], (
        f"am Ende steht der Fuss auf {breite['wieder_leer'][0]} statt "
        f"wieder auf {breite['leer'][0]}")


def test_die_exklusive_zone_bleibt_nicht_stehen(breite):
    """Was der Fuss sich nimmt, fehlt jedem Fenster des Schirms.

    Die Zone haengt an der HOEHE der Flaeche, und die aendert sich mit,
    sobald ein Knopf hoeher ist als die uebrigen (ein Fenster ohne
    Symbol bekommt das Ersatzzeichen, und das ist ein Label). Steht sie
    danach stehen, kostet ein Knopf, den es nicht mehr gibt, dauerhaft
    Bildschirmhoehe.
    """
    assert breite["wieder_leer"][1] == breite["leer"][1], (
        f"die untere reservierte Zone ist am Ende {breite['wieder_leer'][1]} "
        f"statt wieder {breite['leer'][1]} Punkte")
    assert breite["wieder_eins"][1] == breite["eins"][1], (
        f"nach dem ersten Schliessen ist sie {breite['wieder_eins'][1]} "
        f"statt {breite['eins'][1]}")
