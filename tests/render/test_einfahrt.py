# SPDX-License-Identifier: GPL-3.0-or-later
"""SUPER+B: das Dock faehrt ein - und der Abschaltknopf faehrt mit.

WAS GEMELDET WURDE
    Der Nutzer am 20.08.2026, woertlich: "die dock beim einfahren mit
    super b soll auch links der button mit shutdown auch mit
    verschwinden mit der selben animation".

WAS VORHER WAR, IN ZAHLEN
    GEMESSEN am 20.08.2026 mit genau diesem Aufbau (Hyprland 0.56.2,
    1920x1080, ausgelieferte Groesse), ein einziges `ags request dock`:

        Flaeche       vorher                 nachher
        zepos-dock    (784, 996, 353, 60)    fort
        zepos-power   ( 24, 999,  53, 57)    STAND WEITER DA
        bemalt im unteren Drittel  23593 Punkte -> 2717 Punkte

    Die 2717 waren Punkt fuer Punkt der Kasten des Abschaltknopfes: ein
    Fuss, der einfaehrt, und ein Knopf, der allein auf der Tapete
    zurueckbleibt.

WARUM DIESE ZUSICHERUNG NICHT KOPFLOS LAUFEN KANN
    Dieselbe Antwort wie in test_geometry.py, und hier noch eine Stufe
    schaerfer: gefragt ist nicht, WAS in der Vorlage steht, sondern ob
    zwei Layer-Shell-Flaechen IM SELBEN ZUG verschwinden. Beides gibt es
    nur an einem echten Compositor - eine Flaeche, die sich abmeldet,
    und eine Fensterverwaltung, die sagt, wann sie fort ist.

    Die Vorlagenseite derselben Frage steht in tests/src/test_placement.py
    (test_the_power_button_rides_with_the_dock). Die Trennung ist die
    ueberall in diesem Baum: dort, was in der Vorlage steht, hier, was
    daraus auf dem Schirm wird.

WAS "DIESELBE ANIMATION" HIER HEISST, UND WARUM NIRGENDS EINE DAUER
STEHT
    Weder das Dock noch der Knopf blendet sich selbst aus. Beide setzen
    `visible`, melden damit ihre Flaeche ab, und was man dann sieht,
    malt der Compositor: Hyprland fuehrt dafuer die Klasse `layers` mit
    `layersIn`/`layersOut`. ZepOS schreibt dazu KEINE Regel je
    Namensraum - `hyprctl animations` meldet fuer `layersOut`
    "overridden: 0", also den Erbwert von `global`. Zwei Flaechen
    derselben Art, im selben Durchlauf der Ereignisschleife abgemeldet,
    bekommen deshalb zwangslaeufig dieselbe Dauer und dieselbe Kurve.

    Gemessen wird darum der ZUG und nicht die Dauer: wann jede der
    beiden Flaechen fort ist. Aufloesung ist eine hyprctl-Abfrage, und
    die dauert an diesem Aufbau 4 bis 6 ms (siehe `abfrage_ms` unten).
    Ein Unterschied, der kleiner ist als eine Abfrage, ist keiner, den
    ein Auge sieht.

    Die Bilder dazu, GEMESSEN am 20.08.2026 nach der Kopplung, in
    Anteilen der jeweils voll bemalten Flaeche:

        ms nach der Anfrage    Dock     Knopf
                  98          1.000     0.997
                 186          0.999     0.995
                 279          0.328     0.430
                 366          0.318     0.126
                 699          0.015     0.021

    Beide stehen bis 186 ms, beide sind ab 279 ms im Verblassen, beide
    sind bei 699 ms weg. Dass die Anteile dazwischen auseinanderliegen,
    ist KEIN Zeitversatz, sondern der Unterschied im Inhalt: ein Dock
    voller Symbole hebt sich bei halber Deckkraft noch von der Tapete
    ab, ein einzelnes Zeichen nicht mehr. Genau deshalb steht die
    Zusicherung unten auf dem ZUG (hyprctl) und nicht auf dieser
    Tabelle.

DIE GEGENPROBE IST GEFAHREN, mit DREI Zeilen Unterschied
    Am 20.08.2026, zweimal derselbe Baum - einmal mit dem
    faehrtMitDemDock()-Aufruf am Ende von
    src/templates/ags-power-button.template und einmal ohne ihn:

        ohne den Aufruf   3 von 5 rot. "nach SUPER+B bemalen 2717 Punkte
                          das untere Drittel, Kasten (24, 999, 53, 57)",
                          zepos-power weiterhin in `hyprctl layers`, und
                          im Zug fehlte die zweite Flaeche ganz.
        mit ihm           5 von 5 gruen, 22.8 s.

    Die 2717 sind auf den Punkt die Zahl, die diese Datei oben als
    Meldung des Nutzers fuehrt. Ohne diese Gegenprobe waere der Aufruf
    eine Zeile, die jeder wieder herausnehmen kann.

DER PREIS
    Ein verschachtelter Compositor, rund eine halbe Minute.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.render import measure                       # noqa: E402
from tests.render.desktop_session import (              # noqa: E402
    Session, bundle, empty_home, render_configuration, required_tools,
    size_of, workspaces_file,
)

BREITE, HOEHE = 1920, 1080

# Dieselbe Beruhigungszeit wie in test_geometry.py und shoot.py.
SETTLE = 6.0

# Die beiden Flaechen, um die es geht. Die Namen stehen in
# ags-dock.template und ags-power-button.template als `namespace`.
DOCK = "zepos-dock"
KNOPF = "zepos-power"

# Dreimal hin und zurueck. EINMAL wuerde die Frage nicht beantworten:
# der Fehler, um den es geht, ist ein Zustand, der auseinanderlaeuft,
# und der faellt beim ersten Mal am wenigsten auf.
RUNDEN = 3

# Wie lange auf das Verschwinden bzw. Wiederkommen gewartet wird. Grosszuegig
# gegen die 800 ms, die Hyprlands Erbwert fuer `layers` ausmacht - hier wird
# nicht die Dauer gemessen, sondern der Gleichlauf.
FRIST = 4.0

# Die modulweite Vorrichtung `einfahrt` schickt ein echtes
# `ags request dock` in eine verschachtelte Sitzung und nimmt vorher und
# nachher auf. Ob der Abschaltknopf MITfaehrt, ist ein Unterschied
# zwischen zwei Bildern; im Quelltext steht er nicht.
pytestmark = pytest.mark.allow_subprocess


def _verfolge(sitzung: Session, erwarte_da: bool) -> dict[str, int]:
    """Bei der WIEVIELTEN Abfrage jede Flaeche ihren Zustand erreicht hat.

    Die ABFRAGENUMMER und nicht die Uhrzeit: zwei Flaechen, die in
    derselben Abfrage umspringen, sind fuer diesen Aufbau gleichzeitig -
    feiner kann er nicht sehen, und alles Feinere waere eine Zahl, die
    so tut als ob.
    """
    gesehen: dict[str, int] = {}
    frist = time.monotonic() + FRIST
    nummer = 0
    while time.monotonic() < frist and len(gesehen) < 2:
        flaechen = sitzung.layers()
        for name in (DOCK, KNOPF):
            if name not in gesehen and (name in flaechen) == erwarte_da:
                gesehen[name] = nummer
        nummer += 1
    return gesehen


def _bemalt(vorher, nachher, bereich) -> tuple[int, tuple | None]:
    punkte = measure.changed_pixels(vorher, nachher, bereich)
    return len(punkte), measure.bounds_of(punkte)


def _reserviert_unten(sitzung: Session) -> int:
    """Was der Schirm unten fuer Flaechen freihaelt, in Punkten."""
    daten = sitzung.hyprctl_json("monitors") or []
    for monitor in daten:
        if monitor.get("name") == sitzung.output:
            return monitor["reserved"][3]
    raise AssertionError(f"{sitzung.output} steht nicht in hyprctl monitors")


@pytest.fixture(scope="module")
def einfahrt(tmp_path_factory) -> dict:
    """Der ganze Ablauf einmal: hin, zurueck, und dreimal nachgefasst."""
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Bildlauf fehlt: {', '.join(fehlt)}")

    bau = tmp_path_factory.mktemp("zepein-bau")
    bilder = tmp_path_factory.mktemp("zepein-bild")
    ags = render_configuration(bau)
    bundle(ags, bau)

    # Ein Home OHNE Symbole. Es ist die Flaeche hinter allen Fenstern und
    # legt seine Symbole ins untere Drittel - genau dorthin, wo diese
    # Datei misst, ob nach SUPER+B noch etwas vom Fuss stehenbleibt. Die
    # Symbole des Homes bleiben dort stehen, und zwar zu Recht; sie
    # gehoeren nur nicht in DIESE Messung. Die ganze Begruendung steht
    # bei empty_home() in tests/render/desktop_session.py.
    empty_home(bau)

    with Session(BREITE, HOEHE) as sitzung:
        sitzung.start_bus()
        workspaces_file(bau, sitzung.output)
        # Wie in test_geometry.py: der Mauspfeil wird sonst mitgemalt und
        # waere auf dem Bild ein Befund, der keiner ist.
        sitzung.hyprctl("keyword", "cursor:invisible", "true")
        sitzung.wallpaper()
        sitzung.move_cursor(BREITE // 2, HOEHE // 2)
        time.sleep(2.0)
        tapete = sitzung.shoot(bilder / "0-nur-tapete.png")

        sitzung.shell(bau / "zepos-shell.js", bau)
        # AUF DIE RUHE UND NICHT AUF DIE UHR - seit dem 04.09.2026.
        # Hier stand ein fester Schlaf. Warum "die Flaeche ist da"
        # dafuer nicht reicht - und mit welchen Zahlen das gemessen
        # ist - steht bei Session.warte_auf_ruhe().
        sitzung.warte_auf_ruhe("zepos-bar", "zepos-dock",
                               frist=40.0)

        flaechen = sitzung.layers()
        assert DOCK in flaechen and KNOPF in flaechen, (
            "Dock oder Abschaltknopf liegen gar nicht auf dem Schirm - "
            "dann sagt dieser Lauf ueber ihr Zusammenspiel nichts:\n"
            + sitzung.read_shell_log())

        # Wie lange eine Abfrage dauert. Das IST die Aufloesung dieser
        # Datei, und sie gehoert in den Bericht und nicht in eine
        # Annahme.
        abfrage_ms = []
        for _ in range(5):
            angefangen = time.monotonic()
            sitzung.layers()
            abfrage_ms.append(round((time.monotonic() - angefangen) * 1000))

        aus_flaechen = dict(flaechen)
        reserviert_an = _reserviert_unten(sitzung)
        mit = sitzung.shoot(bilder / "1-ausgefahren.png")

        # -- SUPER+B, und zwar so, wie die Tastenbindung es tut --------
        antwort = sitzung.request("dock")
        zuege_weg = [_verfolge(sitzung, False)]
        time.sleep(2.0)
        eingefahren_flaechen = sitzung.layers()
        reserviert_aus = _reserviert_unten(sitzung)
        ohne = sitzung.shoot(bilder / "2-eingefahren.png")

        antwort_zurueck = sitzung.request("dock")
        zuege_da = [_verfolge(sitzung, True)]
        time.sleep(2.0)
        zurueck_flaechen = sitzung.layers()
        reserviert_zurueck = _reserviert_unten(sitzung)
        wieder = sitzung.shoot(bilder / "3-wieder-da.png")

        # Und noch zweimal, ohne Bilder: was einmal zusammengeht, soll
        # auch beim dritten Mal noch zusammengehen.
        for _ in range(RUNDEN - 1):
            sitzung.request("dock")
            zuege_weg.append(_verfolge(sitzung, False))
            time.sleep(1.5)
            sitzung.request("dock")
            zuege_da.append(_verfolge(sitzung, True))
            time.sleep(1.5)

    leer = measure.read_png(tapete)
    an = measure.read_png(mit)
    aus = measure.read_png(ohne)
    zurueck = measure.read_png(wieder)

    # Das untere Drittel als EIN Bereich: gefragt ist, ob unten noch
    # irgendetwas steht - nicht, ob an einer bestimmten Stelle etwas
    # steht. Ein Kasten um den Knopf herum wuerde einen Rest daneben
    # nicht sehen.
    drittel = HOEHE // 3
    unten = (0, HOEHE - drittel, BREITE, drittel)

    return {
        "antwort": antwort,
        "antwort_zurueck": antwort_zurueck,
        "abfrage_ms": abfrage_ms,
        "flaechen_an": aus_flaechen,
        "flaechen_aus": eingefahren_flaechen,
        "flaechen_zurueck": zurueck_flaechen,
        "reserviert_an": reserviert_an,
        "reserviert_aus": reserviert_aus,
        "reserviert_zurueck": reserviert_zurueck,
        "zuege_weg": zuege_weg,
        "zuege_da": zuege_da,
        "bemalt_an": _bemalt(leer, an, unten),
        "bemalt_aus": _bemalt(leer, aus, unten),
        "bemalt_zurueck": _bemalt(leer, zurueck, unten),
        "bilder": {"tapete": tapete, "an": mit, "aus": ohne,
                   "zurueck": wieder},
    }


def test_super_b_laesst_unten_nichts_stehen(einfahrt):
    """Die Bestellung selbst, an Bildpunkten.

    "soll auch links der button mit shutdown auch mit verschwinden" -
    also bemalt das untere Drittel nach SUPER+B NICHTS mehr. Vor der
    Kopplung waren es 2717 Punkte, und das war genau der Knopf.
    """
    assert einfahrt["antwort"] == "hidden", (
        f"`ags request dock` hat {einfahrt['antwort']!r} geantwortet - "
        "dann ist gar nichts eingefahren")

    punkte, kasten = einfahrt["bemalt_aus"]
    assert punkte == 0, (
        f"nach SUPER+B bemalen {punkte} Punkte das untere Drittel, "
        f"Kasten {kasten}. Genau das hat der Nutzer am 20.08.2026 "
        f"gemeldet: das Dock faehrt ein, und links bleibt etwas stehen. "
        f"Siehe faehrtMitDemDock() in src/templates/ags-dock.template")


def test_beide_flaechen_sind_fort_und_nicht_nur_die_eine(einfahrt):
    """Bildpunkte allein wuerden eine durchsichtige Flaeche uebersehen.

    Eine Flaeche, die noch da ist, aber nichts malt, faengt trotzdem
    Klicks ab - ein unsichtbarer Knopf ueber der Tapete ist schlimmer
    als ein sichtbarer, der nicht mitfaehrt.
    """
    flaechen = einfahrt["flaechen_aus"]
    assert DOCK not in flaechen, "das Dock liegt noch auf dem Schirm"
    assert KNOPF not in flaechen, (
        "der Abschaltknopf liegt noch auf dem Schirm, obwohl er nichts "
        "mehr malt - er faengt dort weiterhin Klicks ab")


def test_beide_gehen_und_kommen_im_selben_zug(einfahrt):
    """"mit der selben animation" - und das ist zuerst eine Frage des
    ZEITPUNKTS.

    Zwei Flaechen, die verschieden lange verblassen, sieht man kaum;
    zwei, die nacheinander anfangen, sieht man sofort. Gemessen wird
    deshalb, bei der wievielten hyprctl-Abfrage jede fort ist - und die
    Abfrage ist an diesem Aufbau 4 bis 6 ms lang.

    GEMESSEN am 20.08.2026, drei Runden hin und zurueck: jedes Mal
    dieselbe Abfrage fuer beide, also ein Versatz unterhalb der
    Aufloesung dieses Messstands. Die Ursache steht in
    ags-dock.template: melde() laeuft SYNCHRON in toggle(), also sind
    beide Flaechen abgemeldet, bevor GTK das naechste Mal zum
    Compositor schreibt.
    """
    aufloesung = max(einfahrt["abfrage_ms"])
    for richtung, zuege in (("fort", einfahrt["zuege_weg"]),
                            ("zurueck", einfahrt["zuege_da"])):
        for runde, zug in enumerate(zuege):
            assert set(zug) == {DOCK, KNOPF}, (
                f"Runde {runde}, Richtung {richtung}: in {FRIST} s sind "
                f"nicht beide Flaechen umgesprungen, gesehen wurde "
                f"{zug}")
            assert zug[DOCK] == zug[KNOPF], (
                f"Runde {runde}, Richtung {richtung}: das Dock springt "
                f"bei Abfrage {zug[DOCK]} um, der Abschaltknopf bei "
                f"{zug[KNOPF]} - also mindestens {aufloesung} ms "
                f"auseinander. Beide sollen im selben Durchlauf der "
                f"Ereignisschleife umgeschaltet werden; siehe melde() in "
                f"src/templates/ags-dock.template")


def test_beide_kommen_zusammen_wieder(einfahrt):
    """Ein zweites SUPER+B stellt genau denselben Schirm wieder her.

    Nicht "ungefaehr wieder da": dieselbe Punktzahl und derselbe Kasten.
    Ein Knopf, der nach dem Wiederausfahren woanders sitzt, waere die
    naechste Meldung.
    """
    assert einfahrt["antwort_zurueck"] == "shown"

    vorher, kasten_vorher = einfahrt["bemalt_an"]
    nachher, kasten_nachher = einfahrt["bemalt_zurueck"]
    assert vorher > 0, "vor SUPER+B war unten gar nichts zu sehen"
    assert (nachher, kasten_nachher) == (vorher, kasten_vorher), (
        f"vor dem Einfahren bemalten {vorher} Punkte {kasten_vorher}, "
        f"danach {nachher} Punkte {kasten_nachher}")

    assert einfahrt["flaechen_zurueck"].get(DOCK) == \
        einfahrt["flaechen_an"].get(DOCK), "das Dock kam woanders zurueck"
    assert einfahrt["flaechen_zurueck"].get(KNOPF) == \
        einfahrt["flaechen_an"].get(KNOPF), \
        "der Abschaltknopf kam woanders zurueck"


def test_der_reservierte_streifen_faehrt_mit_ein(einfahrt):
    """Der Platz, den der Fuss den Fenstern wegnimmt, kommt zurueck.

    Das Dock ist EXCLUSIVE (ags-dock.template) und haelt unten einen
    Streifen frei. Bliebe der stehen, waehrend das Bild verschwindet,
    haette der Nutzer einen unsichtbaren Balken, in dem seine Fenster
    nicht liegen duerfen - und SUPER+B haette ihm nichts zurueckgegeben.

    GEMESSEN am 20.08.2026: 84 px -> 0 px -> 84 px. Die 84 sind
    STYLE_BAR_THICKNESS (60) plus STYLE_GAPS_OUT (24), also die
    Ableitung und nicht eine Zahl von hier.

    UND DIE GEGENPROBE ZUM ABSCHALTKNOPF STECKT IN DERSELBEN ZEILE: bei
    eingefahrenem Dock reserviert der Schirm 0 px, und VOR der Kopplung
    stand der Knopf in genau diesem Zustand noch auf dem Schirm (siehe
    den Dateikopf). Er ist Astal.Exclusivity.IGNORE, nimmt also weder
    vorher noch nachher Platz - es gibt an ihm nichts freizugeben.
    """
    erwartet = size_of("STYLE_BAR_THICKNESS") + size_of("STYLE_GAPS_OUT")

    assert einfahrt["reserviert_an"] == erwartet, (
        f"mit Dock reserviert der Schirm unten "
        f"{einfahrt['reserviert_an']} px, die Ableitung sagt {erwartet}")
    assert einfahrt["reserviert_aus"] == 0, (
        f"das Dock ist eingefahren, und der Schirm haelt unten weiterhin "
        f"{einfahrt['reserviert_aus']} px frei - ein unsichtbarer Balken")
    assert einfahrt["reserviert_zurueck"] == erwartet, (
        f"nach dem Wiederausfahren reserviert der Schirm "
        f"{einfahrt['reserviert_zurueck']} px statt {erwartet}")
