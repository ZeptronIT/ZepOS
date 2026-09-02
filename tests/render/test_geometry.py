# SPDX-License-Identifier: GPL-3.0-or-later
"""Kopf und Fuss, an dem gemessen, was der Schirm zeigt.

WARUM DIESE ZUSICHERUNG NICHT KOPFLOS LAUFEN KANN
    Es gab am 12.08.2026 zwei Tests fuer "der header soll immer genauso
    gross sein wie unser nwg dock", und beide waren gruen, waehrend die
    Leiste 59 Punkte bemalte und der Fuss 83. Der Grund ist derselbe bei
    beiden: sie konnten es gar nicht sehen.

      tests/src/test_sizes.py          rechnet nur - Tabellenwert gegen
                                       Tabellenwert.
      tests/src/test_bar_headless.py   nimmt fuer die Leiste die
                                       Konstante (bar_fit_child.tsx
                                       teilt seine Flaeche selbst mit
                                       allocate(width, BAR_THICKNESS)
                                       zu) und laedt im Einzellauf
                                       ABSICHTLICH kein Stylesheet.

    Der Rand der Leiste steht aber im Stylesheet (margin-top) und wird
    von der Layer-Shell zugeteilt. Wer kein Blatt laedt und die Flaeche
    selbst aufteilt, misst zwangslaeufig die Zahl, die er hineingegeben
    hat.

    Hier laeuft deshalb das echte Hyprland mit dem echten Blatt, und
    gemessen wird an Bildpunkten: der Unterschied zwischen dem Schirm
    OHNE Oberflaeche und dem Schirm MIT ihr. Was Farbe bekommen hat, ist
    bemalt - das ist, was der Nutzer sieht, und nichts anderes.

WARUM SEIT DEM 13.08.2026 UEBER MEHRERE SCHIRME UND FAKTOREN
    Bis dahin stand hier EIN Fall: 1920x1080 bei Vorgabegroesse. Er war
    gruen, und der Nutzer sah Kopf und Fuss trotzdem verschieden.

    Eine Zusicherung ueber einen einzigen Punkt einer Ableitung sagt
    nichts ueber die Ableitung. Die drei Faelle unten treffen die drei
    Stellen, an denen sie sich unterschiedlich verhaelt:

      1920x1080, Vorgabe    der Fall, an dem die Zahlen abgeleitet sind.
      1366x768,  Vorgabe    der verbreitetste Notebookschirm. Ein anderer
                            Schirm heisst andere Modulbreiten, andere
                            Einklappentscheidungen - und beides koennte
                            die HOEHE anfassen, wenn irgendwo eine
                            Rueckkopplung steckt.
      1280x800,  Faktor 1.0 der kleinste Faktor, den user_settings
                            zulaesst, und zugleich der einzige Bereich,
                            in dem nicht die Schrift die Dicke bestimmt,
                            sondern die Untergrenze des Docksymbols
                            (siehe bar_thickness_px in src/sizes.py).
                            Ohne diese Zeile waere genau der Zweig
                            ungemessen, der bei der Umstellung auf 60 px
                            am 13.08.2026 zum ersten Mal ueberhaupt
                            gegriffen hat.

UND SEIT DEMSELBEN TAG MIT ZEIGER
    "bei hover ist der hintergrund hinter dem icon ueber den header" -
    dieselbe Meldung, dieselbe Ursache: ein Kasten auf einer Platte mit
    runden Ecken. Ohne Zeiger ist der Effekt unsichtbar, deshalb setzt
    der Aufbau ihn und misst ein zweites Bild. Was dabei herauskam und
    wie die Gegenprobe gelaufen ist, steht bei
    test_der_zeigergrund_bleibt_in_der_platte.

DER PREIS
    Ein verschachtelter Compositor je Fall, etwa eine Minute. Das ist
    teuer fuer eine Zusicherung und trotzdem richtig: dieselbe Frage
    wurde dreimal billig beantwortet und war dreimal falsch.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.render import measure                      # noqa: E402
from tests.render.desktop_session import (             # noqa: E402
    Session, bundle, empty_home, render_configuration, required_tools,
    size_of, workspaces_file,
)

# Dieselbe Beruhigungszeit, die shoot.py benutzt: die Skriptmodule
# antworten asynchron, und eine Leiste vor der ersten Antwort ist eine
# andere Leiste als die, die der Nutzer sieht.
SETTLE = 6.0

# (Breite, Hoehe, sizes.scale). None heisst: der ausgelieferte Faktor.
# Die Begruendung je Zeile steht im Kopf dieser Datei.
FAELLE = (
    (1920, 1080, None),
    (1366, 768, None),
    (1280, 800, 1.0),
)

FALLNAMEN = [f"{breite}x{hoehe}@{faktor or 'vorgabe'}"
             for breite, hoehe, faktor in FAELLE]

# Die modulweite Vorrichtung `gemalt` nimmt Kopf und Fuss in einer
# verschachtelten Sitzung auf. Zwei kopflose Tests waren am 12.08.2026
# gruen, waehrend die Leiste 59 Punkte bemalte und der Fuss 83: sie
# konnten es nicht sehen, weil sie Tabellenwerte gegen Tabellenwerte
# rechneten. Diese Datei fragt den Schirm.
pytestmark = pytest.mark.allow_subprocess


@pytest.fixture(scope="module", params=FAELLE, ids=FALLNAMEN)
def gemalt(request, tmp_path_factory) -> dict:
    """Was Kopf und Fuss auf diesem Schirm wirklich bemalen.

    Zurueck kommt ein Wort-zu-Wert-Verzeichnis und kein Tupel: die drei
    Zusicherungen darunter fragen verschiedene Dinge, und `gemalt[3]`
    saegte an genau der Lesbarkeit, um derentwillen dieser Aufbau
    ueberhaupt existiert.
    """
    # required_tools() liefert, was FEHLT - nicht, was gebraucht wird.
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Bildlauf fehlt: {', '.join(fehlt)}")

    breite, hoehe, faktor = request.param
    bau = tmp_path_factory.mktemp("zepgeo-bau")
    bilder = tmp_path_factory.mktemp("zepgeo-bild")
    ags = render_configuration(bau, scale=faktor)
    bundle(ags, bau)

    # Ein Home OHNE Symbole. Es legt seine Symbole ins untere Drittel,
    # und genau dort misst diese Datei, wie viel der FUSS bemalt - seine
    # Symbole waeren dort ein Zuschlag, der mit Kopf und Fuss nichts zu
    # tun hat. Die ganze Begruendung steht bei empty_home() in
    # tests/render/desktop_session.py.
    empty_home(bau)

    # Kein start() hier: __enter__ ruft es. Ein zweiter Aufruf setzt
    # einen zweiten Compositor ueber den ersten, und danach findet
    # hyprctl keine Kennung mehr.
    with Session(breite, hoehe) as sitzung:
        sitzung.start_bus()
        workspaces_file(bau, sitzung.output)
        # DER MAUSPFEIL WIRD NICHT MITGEMALT, UND DAS IST ZWEIMAL
        # GEMESSEN WORDEN
        #     Ein headless-Ausgang hat keinen Hardware-Cursor. Der
        #     Compositor malt den Pfeil deshalb IN das Bild, und grim
        #     nimmt ihn mit, obwohl -c gar nicht angegeben ist.
        #
        #     Am 13.08.2026 hat er die Zusicherung ueber den Zeigergrund
        #     zweimal umgeworfen, und beide Male sah sein Fehlschlag aus
        #     wie ein Befund:
        #
        #       * beim Start steht er in der linken oberen Ecke. Auf dem
        #         Bild MIT Zeiger war er fort - 184 Punkte bei
        #         (0,0)..(13,23), die ihre Farbe wechselten.
        #       * auf dem Modul steht sein Pfeil 24 px weit nach unten
        #         rechts. Bei Faktor 1.0 ist das letzte Modul rund 31 px
        #         breit, seine Mitte liegt also 11 px vor der Kante - und
        #         die Pfeilspitze lag 2 px HINTER ihr: 7 Punkte bei
        #         (1264, 37), gemeldet als Ueberstand der Platte.
        #
        #     `cursor:invisible` nimmt ihn aus dem Bild und laesst den
        #     Zeiger selbst, wo er ist: GTK bekommt sein Enter-Ereignis
        #     weiter, das Modul wird also weiter als beruehrt gezeichnet.
        #     Damit misst diese Datei die Oberflaeche und nicht mehr das
        #     Werkzeug, mit dem sie abgebildet wird.
        ergebnis = sitzung.hyprctl("keyword", "cursor:invisible", "true")
        assert ergebnis.returncode == 0, (
            f"cursor:invisible liess sich nicht setzen: {ergebnis.stderr}")
        sitzung.wallpaper()
        # Und der Zeiger fort von der Leiste: sonst traegt schon das
        # erste Bild einen Zeigergrund, und der Unterschied zum zweiten
        # waere nicht der, um den es geht.
        sitzung.move_cursor(breite // 2, hoehe // 2)
        time.sleep(2.0)
        ohne = sitzung.shoot(bilder / "nur-tapete.png")

        sitzung.shell(bau / "zepos-shell.js", bau)
        time.sleep(SETTLE)
        flaechen = sitzung.layers()
        assert "zepos-bar" in flaechen and "zepos-dock" in flaechen, (
            "Kopf oder Fuss liegen nicht auf dem Schirm:\n"
            + sitzung.read_shell_log())
        mit = sitzung.shoot(bilder / "schreibtisch.png")

        vorher = measure.read_png(ohne)
        nachher = measure.read_png(mit)
        # Oberes und unteres Drittel getrennt. Ein Rechteck um beide sagt
        # ueber keines von beiden etwas.
        drittel = hoehe // 3
        grenzen = {}
        for name, bereich in (("Kopf", (0, 0, breite, drittel)),
                              ("Fuss", (0, hoehe - drittel, breite, drittel))):
            bounds = measure.changed_bounds(vorher, nachher, bereich)
            assert bounds is not None, f"{name}: nichts bemalt"
            grenzen[name] = bounds

        # -- Und was der ZEIGER daran aendert ---------------------------
        #
        # Die Platte punktweise, nicht als Rechteck: der Ueberstand, um
        # den es geht, liegt in ihren runden Ecken. Siehe changed_pixels
        # in tests/render/measure.py.
        platte = measure.changed_pixels(vorher, nachher,
                                        (0, 0, breite, drittel))
        px, py, pw, ph = grenzen["Kopf"]
        # WOHIN GENAU, UND WARUM DIE ZAHL AN DER DICKE HAENGT
        #     Auf das letzte Modul der Leiste - das Zahnrad -, und zwar
        #     in seine Mitte. Seine halbe Breite waechst mit dem
        #     Groessenregler: bei Vorgabegroesse ist der Kasten 48 px
        #     breit, bei Faktor 1.0 rund 31. GEMESSEN am 13.08.2026: ein
        #     fester Abstand von 40 px vom Rand traf bei Faktor 1.0 die
        #     LUECKE zwischen Akku und Zahnrad, und der Abzug zeigte
        #     nichts als den Zeiger - 197 Punkte statt 2370. Eine
        #     Zusicherung, die ihren Gegenstand verfehlt, ist gruen und
        #     wertlos.
        #
        #     ph // 4 ist die halbe Modulbreite, ausgedrueckt in der
        #     einzigen Zahl, die hier schon gemessen vorliegt: 15 px bei
        #     60 px Dicke, 11 bei 47. Beide liegen im Kasten.
        zeiger = (px + pw - max(8, ph // 4), py + 10)

        # Grosszuegig um die Platte herum gesucht: was ausserhalb liegt,
        # soll gefunden werden und nicht am Rand des Suchfensters enden.
        rand = 24
        fenster = (max(px - rand, 0), max(py - rand, 0),
                   pw + 2 * rand, ph + 2 * rand)

        # GERUETTELT STATT GEWARTET, UND BEIDES IST GEMESSEN
        #
        #     Zwei Dinge stehen einem Bild vom Zeigergrund im Weg, und
        #     ein fester Schlaf trifft beide falsch:
        #
        #       zu frueh   der Compositor hat noch nicht neu gemalt. Bei
        #                  Faktor 1.0 kam nach 0,35 s ein Bild zurueck,
        #                  das von dem ohne Zeiger nicht zu
        #                  unterscheiden war - die Zusicherung fiel um,
        #                  ohne dass an der Leiste irgendetwas war.
        #       zu spaet   nach 500 ms steht der Kurzhinweis da. Er ist
        #                  eine eigene Flaeche, liegt ueber der Platte
        #                  und ueber dem, was neben ihr liegt, und waere
        #                  von einem Ueberstand nicht zu unterscheiden.
        #                  GEMESSEN: sein Kasten ist 76 px hoch, wo die
        #                  Platte 47 misst.
        #
        #     Der Ruck von einem Punkt loest den Knoten: GTK setzt die
        #     Frist bis zum Kurzhinweis bei JEDER Zeigerbewegung neu, das
        #     :hover dagegen haengt am Betreten des Widgets und bleibt.
        #     Solange geruettelt wird, kann also gewartet werden, bis das
        #     Bild wirklich da ist.
        #
        #     Genommen wird das erste Bild, dessen Aenderung so hoch ist
        #     wie ein Modulkasten (Dicke minus zweimal
        #     STYLE_MARGIN_VERTICAL). Das schliesst beide Fehlbilder aus:
        #     ein zu fruehes hat gar keinen Kasten, ein zu spaetes einen,
        #     der hoeher ist als die Platte.
        gezeigt = None
        frist = time.monotonic() + 3.0
        versuch = 0
        while gezeigt is None and time.monotonic() < frist:
            sitzung.move_cursor(zeiger[0] + versuch % 2, zeiger[1])
            versuch += 1
            time.sleep(0.1)
            bild = measure.read_png(
                sitzung.shoot(bilder / f"zeiger-{versuch}.png"))
            kasten = measure.changed_bounds(nachher, bild, fenster)
            if kasten and ph - 8 <= kasten[3] <= ph:
                gezeigt = bild

    assert gezeigt is not None, (
        f"auf {zeiger} ist in 3 s kein Zeigergrund von rund {ph - 6} px "
        f"Hoehe entstanden ({versuch} Abzuege). Entweder liegt dort kein "
        "Modul, das auf den Zeiger reagiert, oder der Kurzhinweis war "
        "schneller - beides macht diese Messung wertlos")
    neu = measure.changed_pixels(nachher, gezeigt, fenster)
    return {"grenzen": grenzen, "breite": breite, "hoehe": hoehe,
            "faktor": faktor, "zeiger": zeiger,
            "zeigergrund": neu, "ueberstand": neu - platte}


def test_der_kopf_bemalt_so_viel_wie_der_fuss(gemalt):
    """Die Forderung des Nutzers, an Bildpunkten.

    Gemessen am 12.08.2026 VOR der Korrektur: Kopf 59, Fuss 83. Die
    Differenz war exakt ein STYLE_GAPS_OUT, weil die Flaeche der Leiste
    BAR_THICKNESS hoch war und ihren Rand darin trug, der Fuss seinen
    aber darunter legte. Zwei Lesarten einer Zahl sind zwei Zahlen.
    """
    _, _, _, kopf = gemalt["grenzen"]["Kopf"]
    _, _, _, fuss = gemalt["grenzen"]["Fuss"]

    assert kopf == fuss, (
        f"der Kopf bemalt {kopf} px und der Fuss {fuss} px. Der Nutzer "
        f"hat verlangt, dass beide gleich sind - und beide kommen aus "
        f"STYLE_BAR_THICKNESS, lesen die Zahl also verschieden. Siehe "
        f"sizes.dock_icon_px() und set_default_size in ags-bar.template.")


def test_die_bemalte_hoehe_ist_die_zahl_aus_der_tabelle(gemalt):
    """Gleich heisst nicht richtig.

    Ohne diese zweite Zusicherung koennten Kopf und Fuss gemeinsam von
    der Ableitung abruecken - dann waeren sie gleich, und der Regler,
    mit dem der Nutzer die Groesse stellt, traefe sie beide nicht mehr.
    """
    erwartet = size_of("STYLE_BAR_THICKNESS", gemalt["faktor"])
    _, _, _, kopf = gemalt["grenzen"]["Kopf"]

    assert kopf == erwartet, (
        f"die Streifen bemalen {kopf} px, die Ableitung in src/sizes.py "
        f"sagt {erwartet} px")


def test_kopf_und_fuss_halten_denselben_randabstand(gemalt):
    """"der abstand des header zum rand kann genauso lang sein wie der
    nwg dock zum footer abstand" - gemeldet am 12.08.2026.

    Oben der Abstand des Kopfes zur Schirmkante, unten der des Fusses.
    Beide sollen STYLE_GAPS_OUT sein.
    """
    rand = size_of("STYLE_GAPS_OUT", gemalt["faktor"])
    _, kopf_y, _, _ = gemalt["grenzen"]["Kopf"]
    _, fuss_y, _, fuss_h = gemalt["grenzen"]["Fuss"]
    unten = gemalt["hoehe"] - (fuss_y + fuss_h)

    assert kopf_y == rand, f"der Kopf steht {kopf_y} px vom oberen Rand"
    assert unten == rand, f"der Fuss steht {unten} px vom unteren Rand"


def test_der_streifen_ist_die_bestellten_sechzig_punkte(gemalt):
    """"header und footer auf 60 setzen" - gemeldet am 13.08.2026.

    Die Zeile darueber haelt die bemalte Hoehe an die ABLEITUNG; diese
    hier haelt die Ableitung an die BESTELLUNG. Beides ist noetig: ohne
    die erste koennte die Leiste von ihrer eigenen Tabelle abruecken,
    ohne diese koennte jemand die Tabelle aendern und alles bliebe gruen.

    Nur bei Vorgabegroesse, denn genau darauf bezog sich die Ansage. Wer
    am Regler dreht, bekommt 3 * Grundschrift - die Rechnung steht bei
    STYLE_BAR_THICKNESS in src/sizes.py.
    """
    if gemalt["faktor"] is not None:
        # UND DIESER SPRUNG DRUECKT KEINE MESSUNG WEG, das ist am
        # 13.08.2026 nachgesehen worden: derselbe Fall laeuft eine Zeile
        # hoeher durch test_die_bemalte_hoehe_ist_die_zahl_aus_der_tabelle
        # und wird dort gegen 47 px gehalten - die Zahl, die
        # bar_thickness_px() bei Faktor 1.0 aus der Untergrenze des
        # Docksymbols ergibt. Ungemessen bliebe er nur, wenn hier
        # uebersprungen WUERDE, ohne dass es die andere Zusicherung gibt.
        pytest.skip("die 60 sind die AUSLIEFERUNG, nicht jeder Faktor - "
                    "dieser Fall haengt an der Tabelle, siehe "
                    "test_die_bemalte_hoehe_ist_die_zahl_aus_der_tabelle")

    _, _, _, kopf = gemalt["grenzen"]["Kopf"]
    assert kopf == 60, (
        f"Kopf und Fuss bemalen {kopf} px; bestellt waren am 13.08.2026 "
        "genau 60")


def test_der_zeigergrund_bleibt_in_der_platte(gemalt):
    """"bei hover ist der hintergrund hinter dem icon ueber den header" -
    gemeldet am 13.08.2026.

    WAS HIER GEMESSEN WIRD, UND WARUM PUNKTWEISE
        Der Zeigergrund eines Moduls ist ein Rechteck, die Platte hat
        runde Ecken. Der Ueberstand liegt also genau dort, wo sich die
        beiden UMRISSE unterscheiden - ein Vergleich zweier Rechtecke
        faende ihn nie. Deshalb der Unterschied zweier PUNKTMENGEN:
        jeder Bildpunkt, den der Zeiger anfasst und den die Platte nicht
        bemalt, ist einer zu viel.

    DIE GEGENPROBE IST GEFAHREN, mit EINER Zeile Unterschied
        Am 13.08.2026, zweimal derselbe Baum - einmal mit
        `bar.set_overflow(Gtk.Overflow.HIDDEN)` in
        src/templates/ags-bar.template und einmal mit derselben Zeile
        auskommentiert. Alle drei Faelle dieser Datei, Zeiger jeweils
        auf dem Zahnrad:

            Fall                  mit der Zeile   ohne sie
            1920x1080 Vorgabe          0          60 Punkte, (1888,27,8,54)
            1366x768  Vorgabe          0          60 Punkte, (1334,27,8,54)
            1280x800  Faktor 1.0       0          15 Punkte, (1260,19,4,41)

        Die Kaesten sagen, WO: acht Spalten breit und so hoch wie der
        Modulkasten, also die obere UND die untere rechte Ecke, und
        keine Stelle dazwischen - genau der Verlauf einer Rundung von
        STYLE_RADIUS_PANEL. Bei Faktor 1.0 ist die Rundung dieselbe und
        der Kasten niedriger, deshalb vier Spalten statt acht.

        Ohne diese Zusicherung waere die Zeile in ags-bar.template eine,
        die jeder wieder herausnehmen kann: sie sieht nach nichts aus,
        und kein anderer Test faellt darueber.
    """
    # DASS UEBERHAUPT EIN ZEIGERGRUND DA IST, hat der Aufbau schon
    # sichergestellt: er nimmt erst das Bild, dessen Aenderung so hoch
    # ist wie ein Modulkasten, und faellt sonst mit einer eigenen
    # Meldung um. "Nichts ragt heraus" waere sonst auch dann wahr, wenn
    # gar nichts gemalt worden ist - und genau das ist am 13.08.2026
    # zweimal passiert.
    ueberstand = gemalt["ueberstand"]
    assert not ueberstand, (
        f"der Zeigergrund bemalt {len(ueberstand)} Punkte, an denen die "
        f"Platte nichts malt: {measure.bounds_of(ueberstand)}. Genau das "
        "hat der Nutzer am 13.08.2026 gemeldet - siehe "
        "bar.set_overflow(...) in src/templates/ags-bar.template")
