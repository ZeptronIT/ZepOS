# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Starterknopf unten rechts: er steht da, er faehrt mit, er wirkt.

WAS BESTELLT WURDE, WOERTLICH (20.08.2026)
    "ich will wie shutdown icon unten links, will ich ein icon ganz unten
    rechts genauso, nur mit 6 punkten, was im Prinzip wie SUPER+SPACE
    macht"

    Drei pruefbare Aussagen stecken darin, und diese Datei misst alle
    drei an EINEM verschachtelten Compositor:

      "ganz unten rechts ... genauso"   dieselbe Platte wie der
                                        Abschaltknopf, spiegelbildlich
                                        an der anderen Ecke. Gemessen
                                        wird gegen den Abschaltknopf IM
                                        SELBEN LAUF und nicht gegen
                                        Zahlen in dieser Datei - eine
                                        abgeschriebene Zahl waere die
                                        naechste, die auseinanderlaeuft.
      "wie shutdown icon"               also auch: mit dem Dock ein und
                                        aus. Der Nutzer hat genau das am
                                        selben Tag fuer den
                                        Abschaltknopf nachgefordert
                                        ("soll auch links der button mit
                                        shutdown auch mit verschwinden");
                                        ein Gegenstueck, das
                                        stehenbliebe, waere dieselbe
                                        Meldung noch einmal.
      "was im Prinzip wie SUPER+SPACE   ein Klick oeffnet den
       macht"                           Anwendungsstarter - und zwar auf
                                        DEMSELBEN Weg, den die Taste
                                        nimmt.

WAS AM 20.08.2026 HERAUSGEKOMMEN IST, IN ZAHLEN
    Verschachteltes Hyprland 0.56.2, 1920x1080, ausgelieferte Groesse:

        Flaeche         x     y     b    h
        zepos-power      24   999    53   57
        zepos-dock      784   996   353   60
        zepos-starter  1843   999    53   57

        bemalt, unteres Drittel   ausgefahren  26310 Punkte,
                                               Kasten (24, 996, 1872, 60)
                                  eingefahren      0 Punkte
        bemalt, untere rechte Ecke  ausgefahren  2717 Punkte,
                                               Kasten (1843, 999, 53, 57)
                                    eingefahren     0 Punkte
        unten reserviert          84 -> 0 -> 84 px

    Die 2717 sind auf den Punkt dieselbe Zahl, die
    tests/render/test_einfahrt.py fuer den Abschaltknopf fuehrt - zwei
    Knoepfe mit derselben Platte und derselben Schriftgroesse bemalen
    gleich viele Punkte. Zufall waere das nur, wenn sie sich die Regeln
    nicht teilten.

WAS DIESE DATEI GEGENUEBER tests/src/test_placement.py HINZUFUEGT
    Dort steht, was in der Vorlage STEHT. Hier steht, was daraus auf
    einem Schirm WIRD - dieselbe Trennung wie zwischen
    tests/src/test_placement.py und tests/render/test_einfahrt.py.

    Zwei der Fragen kann eine Vorlagenpruefung gar nicht beantworten:
    wie gross die Platte am Ende ist (das entscheiden Schriftgroesse,
    Innenabstand und GTK zusammen) und ob ein Klick wirklich etwas
    ausloest.

WIE HIER GEKLICKT WIRD, UND WARUM NICHT MIT EINEM ZEIGER
    Die lange Antwort steht im Kopf von starter_click_child.tsx. Kurz:
    diese Maschine hat kein Werkzeug, das einen Mausklick in eine
    Wayland-Sitzung schiebt, und der Knopf nimmt die Tastatur nie. Also
    baut ein eigenes kleines AGS-Kind den ERZEUGTEN Knopf in DIESEM
    Compositor und loest sein "clicked" aus. Alles hinter dem Signal ist
    echt: die Frage an den Compositor geht ueber den echten Socket, und
    der Rueckfall startet einen echten Prozess - hier eine Attrappe
    namens zepos-menu, die aufschreibt, womit sie gerufen wurde.

    DASS DER RUECKFALL UEBERHAUPT DRAN IST, IST KEIN MANGEL DES
    MESSSTANDS, SONDERN DIE HAELFTE DER MESSUNG. In diesem Compositor
    ist kein hyprlaunch-Plugin geladen - genau die Lage, fuer die
    src/plugins.py den zweiten Block schreibt. Der Lauf belegt damit
    BEIDE Haelften auf einmal: dass zuerst der Dispatcher versucht wird
    (der Compositor antwortet mit seinem "Invalid dispatcher"-Satz, und
    der steht im Protokoll des Kindes) und dass danach genau der Befehl
    laeuft, den hyprland-plugins-config.template fuer diesen Fall bindet.

DER PREIS
    Ein verschachtelter Compositor, rund eine halbe Minute - ein Start
    fuer alle Messungen dieser Datei.
"""
from __future__ import annotations

import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.render import measure                        # noqa: E402
from tests.render.desktop_session import (              # noqa: E402
    Session, bundle, empty_home, render_configuration, required_tools,
    size_of, workspaces_file,
)
# DIESELBE Frage an `hyprctl monitors` wie beim Einfahren, und deshalb
# dieselbe Zeile: was der Schirm unten freihaelt, ist eine Zahl mit
# genau einer Quelle. Eine zweite Fassung hier waere eine, die
# auseinanderlaufen kann - und dann behaupteten zwei Dateien
# Verschiedenes ueber denselben Streifen.
from tests.render.test_einfahrt import _reserviert_unten  # noqa: E402

BREITE, HOEHE = 1920, 1080

# Dieselbe Beruhigungszeit wie in test_geometry.py, shoot.py und
# test_einfahrt.py.
SETTLE = 6.0

# Die drei Flaechen am unteren Rand. Die Namen stehen in ags-dock.
# template, ags-power-button.template und ags-starter-button.template als
# `namespace`.
DOCK = "zepos-dock"
ABSCHALTEN = "zepos-power"
STARTER = "zepos-starter"

# Wie lange auf die Attrappe gewartet wird. Grosszuegig: das Kind wartet
# selbst 1500 ms, bevor es klickt (siehe starter_click_child.tsx), und
# danach kommen ein Socketaustausch und ein Prozessstart.
KLICKFRIST = 25.0

# Der Rueckfall, den der Knopf nimmt, wenn kein hyprlaunch-Plugin
# geladen ist. ABGELESEN aus der Vorlage und nicht getippt - sonst
# pruefte diese Datei ihre eigene Erwartung.
STARTER_VORLAGE = ROOT / "src" / "templates" / "ags-starter-button.template"

# Die modulweite Vorrichtung `starter` startet die Schale mit `ags` in
# einer verschachtelten Sitzung. Alle drei Aussagen der Bestellung -
# er steht da, er faehrt mit, er wirkt - sind bemalte Punkte
# beziehungsweise eine Wirkung im laufenden Compositor.
pytestmark = pytest.mark.allow_subprocess


def _rueckfall_der_vorlage() -> list[str]:
    """STARTER_FALLBACK, so wie die Vorlage es fuehrt."""
    for zeile in STARTER_VORLAGE.read_text(encoding="utf-8").splitlines():
        if zeile.startswith("const STARTER_FALLBACK = "):
            roh = zeile.split("=", 1)[1].strip().strip("[]")
            return [teil.strip().strip('"') for teil in roh.split(",")]
    raise AssertionError(
        "ags-starter-button.template fuehrt kein STARTER_FALLBACK mehr - "
        "dann weiss diese Datei nicht, worauf sie warten soll")


def _attrappe(verzeichnis: Path, name: str, marke: Path) -> None:
    """Ein Programm, das nichts tut ausser aufzuschreiben, dass es lief.

    In EINEM Verzeichnis, das dem Kind vorne im PATH steht. Ein echtes
    zepos-menu liegt auf dieser Maschine ohnehin nicht, aber darauf soll
    sich die Messung nicht verlassen: eine Attrappe, die es GIBT, ist
    ein Beleg; ein Programm, das fehlt, waere nur ein Fehlschlag.
    """
    verzeichnis.mkdir(parents=True, exist_ok=True)
    skript = verzeichnis / name
    skript.write_text(
        "#!/bin/sh\n"
        f"printf '%s' \"$*\" > '{marke}'\n",
        encoding="utf-8")
    skript.chmod(skript.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP
                 | stat.S_IXOTH)


def _buendle(eintrag: Path, ags: Path, ziel: Path) -> Path:
    """Wie bundle() in desktop_session.py, nur fuer einen anderen Eingang.

    Dieselben Schalter, damit das Kind unter denselben Bedingungen
    uebersetzt wird wie die Oberflaeche selbst - `-r` auf die erzeugte
    ags-Wurzel ist das, was "./widget/StarterButton" ueberhaupt
    aufloesbar macht.
    """
    ergebnis = subprocess.run(
        ["ags", "bundle", str(eintrag), str(ziel), "-r", str(ags), "-g", "4"],
        capture_output=True, text=True, timeout=600)
    assert ergebnis.returncode == 0, (
        "`ags bundle` hat das Klick-Kind nicht uebersetzt:\n"
        + ergebnis.stdout + ergebnis.stderr)
    return ziel


@pytest.fixture(scope="module")
def starter(tmp_path_factory) -> dict:
    """Ein Compositor, drei Messungen: Klick, Lage, Einfahrt."""
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Bildlauf fehlt: {', '.join(fehlt)}")

    bau = tmp_path_factory.mktemp("zepstart-bau")
    bilder = tmp_path_factory.mktemp("zepstart-bild")
    ags = render_configuration(bau)
    schale = bundle(ags, bau)

    # Ein Home OHNE Symbole. Es ist die Flaeche hinter allen Fenstern und
    # legt seine Symbole ins untere Drittel - genau dorthin, wo diese
    # Datei misst, ob nach SUPER+B noch etwas vom Fuss stehenbleibt. Die
    # Symbole des Homes bleiben dort stehen, und zwar zu Recht; sie
    # gehoeren nur nicht in DIESE Messung. Die ganze Begruendung steht
    # bei empty_home() in tests/render/desktop_session.py.
    empty_home(bau)

    # Das Klick-Kind: dieselbe erzeugte widget/StarterButton.tsx, nur
    # ohne die uebrige Oberflaeche daneben.
    kind_quelle = Path(__file__).resolve().parent / "starter_click_child.tsx"
    kind_ziel = ags / "starter_click_child.tsx"
    kind_ziel.write_text(kind_quelle.read_text(encoding="utf-8"),
                         encoding="utf-8")
    klickbund = _buendle(kind_ziel, ags, bau / "zepos-starter-klick.js")

    marke = bau / "zepos-menu-wurde-gerufen"
    stubs = bau / "stubs"
    _attrappe(stubs, _rueckfall_der_vorlage()[0], marke)
    klicklog = bau / "klick.log"

    with Session(BREITE, HOEHE) as sitzung:
        sitzung.start_bus()
        workspaces_file(bau, sitzung.output)
        # Wie in test_geometry.py und test_einfahrt.py: der Mauspfeil
        # waere sonst auf dem Bild ein Befund, der keiner ist.
        sitzung.hyprctl("keyword", "cursor:invisible", "true")
        sitzung.wallpaper()
        sitzung.move_cursor(BREITE // 2, HOEHE // 2)
        time.sleep(2.0)
        tapete = sitzung.shoot(bilder / "0-nur-tapete.png")

        # WIE VIELE SCHIRME DIESER AUFBAU HAT, und das ist keine
        # Nebensache: es sind ZWEI - der Ausgang des Wirtsfensters und
        # der headless-Ausgang, der abgebildet wird (siehe start() und
        # _add_headless_output() in desktop_session.py). Der Knopf baut
        # eine Flaeche JE Schirm, also muss das Klick-Kind weiter unten
        # auch zwei Knoepfe finden. Genau daran haengt die Zusicherung
        # ueber mehrere Schirme.
        schirme = len(sitzung.hyprctl_json("monitors") or [])
        assert schirme >= 2, (
            f"dieser Aufbau meldet {schirme} Schirm(e) - dann sagt der "
            f"Lauf nichts ueber mehrere")

        # -- Die Oberflaeche -------------------------------------------
        sitzung.shell(schale, bau)
        # AUF DIE RUHE UND NICHT AUF DIE UHR - seit dem 04.09.2026.
        # Hier stand ein fester Schlaf. Warum "die Flaeche ist da"
        # dafuer nicht reicht - und mit welchen Zahlen das gemessen
        # ist - steht bei Session.warte_auf_ruhe().
        sitzung.warte_auf_ruhe("zepos-bar", "zepos-dock",
                               frist=40.0)

        flaechen_an = sitzung.layers()
        assert STARTER in flaechen_an, (
            "der Starterknopf liegt gar nicht auf dem Schirm - dann sagt "
            "dieser Lauf ueber ihn nichts:\n" + sitzung.read_shell_log())
        reserviert_an = _reserviert_unten(sitzung)
        mit = sitzung.shoot(bilder / "1-ausgefahren.png")

        # -- SUPER+B ---------------------------------------------------
        antwort = sitzung.request("dock")
        time.sleep(2.0)
        flaechen_aus = sitzung.layers()
        reserviert_aus = _reserviert_unten(sitzung)
        ohne = sitzung.shoot(bilder / "2-eingefahren.png")

        antwort_zurueck = sitzung.request("dock")
        time.sleep(2.0)
        flaechen_zurueck = sitzung.layers()
        reserviert_zurueck = _reserviert_unten(sitzung)
        wieder = sitzung.shoot(bilder / "3-wieder-da.png")

        schalen_protokoll = sitzung.read_shell_log()

        # -- ZULETZT DER KLICK, und die Reihenfolge ist gemessen --------
        # Das Kind baut seinen EIGENEN zepos-starter - ohne bar.css, also
        # 50 x 34 statt 53 x 57. layers() fuehrt je Namensraum genau
        # EINEN Eintrag, zwei Flaechen desselben Namens machten also jede
        # Lagemessung zu einem Zufall.
        #
        # GEMESSEN am 20.08.2026: das Kind zuerst laufen zu lassen und
        # danach zu beenden reicht NICHT. Nach terminate() und einem
        # sauber zurueckgekehrten wait() stand zepos-starter
        # (1846, 1022, 50, 34) noch zehn Sekunden spaeter in `hyprctl
        # layers` - und nach SUPER+B sah das aus wie ein Knopf, der nicht
        # mitfaehrt. Es war der Rest des Kindes.
        #
        # Also steht der Klick HINTER allem, was gemessen wird. Was er
        # belegt, braucht kein Bild: ein Prozess, der gestartet wurde,
        # und eine Antwort im Protokoll.
        kennung = sitzung.signature()
        klick = sitzung.spawn(
            [str(klickbund)], log=klicklog,
            XDG_CONFIG_HOME=str(bau),
            HYPRLAND_INSTANCE_SIGNATURE=kennung,
            PATH=f"{stubs}:{os.environ.get('PATH', '/usr/bin')}")

        frist = time.monotonic() + KLICKFRIST
        while time.monotonic() < frist and not marke.exists():
            time.sleep(0.2)
        klick_protokoll = (klicklog.read_text(encoding="utf-8",
                                              errors="replace")
                           if klicklog.exists() else "")
        gerufen_mit = (marke.read_text(encoding="utf-8") if marke.exists()
                       else None)
        klick.terminate()
        try:
            klick.wait(timeout=10)
        except subprocess.TimeoutExpired:
            klick.kill()
            klick.wait(timeout=10)

    leer = measure.read_png(tapete)
    an = measure.read_png(mit)
    aus = measure.read_png(ohne)
    zurueck = measure.read_png(wieder)

    # Die untere rechte Ecke, breit genug fuer die Platte und ihren Rand
    # und schmal genug, dass das Dock in der Mitte nicht hineinragt.
    # GEMESSEN in diesem Lauf: das Dock endet bei x=1137, diese Ecke
    # beginnt bei 1620.
    ecke = (BREITE * 3 // 4 + 180, HOEHE - HOEHE // 6, BREITE // 4 - 180,
            HOEHE // 6)
    drittel = HOEHE // 3
    unten = (0, HOEHE - drittel, BREITE, drittel)

    def bemalt(nachher, bereich):
        punkte = measure.changed_pixels(leer, nachher, bereich)
        return len(punkte), measure.bounds_of(punkte)

    return {
        "schirme": schirme,
        "klick_protokoll": klick_protokoll,
        "gerufen_mit": gerufen_mit,
        "rueckfall": _rueckfall_der_vorlage(),
        "schalen_protokoll": schalen_protokoll,
        "antwort": antwort,
        "antwort_zurueck": antwort_zurueck,
        "flaechen_an": flaechen_an,
        "flaechen_aus": flaechen_aus,
        "flaechen_zurueck": flaechen_zurueck,
        "reserviert_an": reserviert_an,
        "reserviert_aus": reserviert_aus,
        "reserviert_zurueck": reserviert_zurueck,
        "ecke_an": bemalt(an, ecke),
        "ecke_aus": bemalt(aus, ecke),
        "unten_aus": bemalt(aus, unten),
        "unten_zurueck": bemalt(zurueck, unten),
        "unten_an": bemalt(an, unten),
        "bilder": {"tapete": tapete, "an": mit, "aus": ohne,
                   "zurueck": wieder},
    }


# --------------------------------------------------------------------
# "ganz unten rechts ... genauso"
# --------------------------------------------------------------------

def test_der_knopf_liegt_unten_rechts_und_malt_dort_auch_etwas(starter):
    """Zuerst die einfachste Frage: sieht man ihn?

    Eine Flaeche in `hyprctl layers` beweist noch kein Bild - sie kann
    durchsichtig sein, und ein unsichtbarer Knopf, der Klicks abfaengt,
    waere schlimmer als gar keiner. Gefragt wird deshalb beides.
    """
    x, y, breite, hoehe = starter["flaechen_an"][STARTER]
    assert x + breite <= BREITE and y + hoehe <= HOEHE, (
        f"der Knopf liegt bei {(x, y, breite, hoehe)} und damit teilweise "
        f"neben dem {BREITE}x{HOEHE}-Schirm")
    assert x > BREITE // 2, (
        f"der Knopf steht bei x={x} und damit in der linken Haelfte - "
        f"bestellt war 'ganz unten rechts'")

    punkte, kasten = starter["ecke_an"]
    assert punkte > 0, (
        "in der unteren rechten Ecke ist gegenueber der blanken Tapete "
        "kein einziger Punkt anders - die Flaeche ist da und malt nichts")
    links, oben, rechts, unten_ = kasten
    assert x <= links and rechts <= x + breite, (
        f"das Bemalte ({kasten}) liegt waagerecht nicht in der Flaeche "
        f"{(x, y, breite, hoehe)}")
    assert y <= oben and unten_ <= y + hoehe, (
        f"das Bemalte ({kasten}) liegt senkrecht nicht in der Flaeche "
        f"{(x, y, breite, hoehe)}")


def test_er_ist_das_spiegelbild_des_abschaltknopfes(starter):
    """"genauso" - gemessen gegen den Abschaltknopf IM SELBEN LAUF.

    Nicht gegen Zahlen in dieser Datei: die beiden sollen gleich sein,
    und was "gleich" heisst, entscheidet die Vorlage. Eine abgeschriebene
    53 hier waere gruen, sobald jemand BEIDE Knoepfe zugleich verstellt -
    und rot, sobald jemand die Schriftgroesse aendert, ohne dass sich
    etwas an ihrem Verhaeltnis geaendert haette.

    GEMESSEN am 20.08.2026 in diesem Aufbau:

        zepos-power     (  24, 999,  53, 57)
        zepos-starter   (1843, 999,  53, 57)

    24 links, 1920 - 1843 - 53 = 24 rechts.
    """
    px, py, pb, ph = starter["flaechen_an"][ABSCHALTEN]
    sx, sy, sb, sh = starter["flaechen_an"][STARTER]

    assert (sb, sh) == (pb, ph), (
        f"der Starterknopf ist {sb}x{sh}, der Abschaltknopf {pb}x{ph} - "
        f"'genauso' heisst dieselbe Platte. Beide lesen dieselben "
        f"Platzhalter (src/styles/bar-style.template), also ist ein "
        f"Unterschied hier einer in einer der beiden Regeln")
    assert sy == py, (
        f"die beiden stehen auf verschiedener Hoehe ({sy} gegen {py}) - "
        f"beide verankern BOTTOM mit demselben Aussenrand")

    rand_links = px
    rand_rechts = BREITE - (sx + sb)
    assert rand_rechts == rand_links, (
        f"der Starterknopf haelt {rand_rechts} px zum rechten Bildrand, "
        f"der Abschaltknopf {rand_links} px zum linken")
    assert rand_rechts == size_of("STYLE_GAPS_OUT"), (
        f"der Rand ist {rand_rechts} px und nicht die Sprosse "
        f"{size_of('STYLE_GAPS_OUT')} aus src/sizes.py - dann traegt "
        f"irgendwer eine eigene Zahl")


def test_er_haelt_denselben_abstand_zum_dock_wie_der_abschaltknopf(starter):
    """"derselbe Abstand zum Dock" ist zuerst eine Frage der Unterkante.

    Alle drei Flaechen haengen an der UNTEREN Kante mit demselben
    Aussenrand, also fallen ihre Unterkanten zusammen. Was sie
    unterscheidet, ist allein die Hoehe - und die ist beim Dock groesser,
    weil es Bilder traegt und keine Schrift (die Rechnung dazu steht in
    src/styles/bar-style.template beim Abschaltknopf).
    """
    unterkanten = {
        name: y + h
        for name, (x, y, w, h) in starter["flaechen_an"].items()
        if name in (DOCK, ABSCHALTEN, STARTER)
    }
    assert set(unterkanten) == {DOCK, ABSCHALTEN, STARTER}, (
        f"nicht alle drei Flaechen liegen auf dem Schirm: {unterkanten}")
    assert len(set(unterkanten.values())) == 1, (
        f"die drei Flaechen enden auf verschiedener Hoehe: {unterkanten}. "
        f"Damit steht eine von ihnen ueber oder unter den anderen")
    einzige = next(iter(unterkanten.values()))
    assert HOEHE - einzige == size_of("STYLE_GAPS_OUT"), (
        f"alle drei enden {HOEHE - einzige} px ueber dem Bildrand statt "
        f"der Sprosse {size_of('STYLE_GAPS_OUT')}")


# --------------------------------------------------------------------
# "wie shutdown icon" - also mit dem Dock ein und aus
# --------------------------------------------------------------------

def test_super_b_nimmt_ihn_mit(starter):
    """Der Fehler, den der Nutzer am selben Tag links gemeldet hat, darf
    rechts nicht noch einmal entstehen."""
    assert starter["antwort"] == "hidden", (
        f"`ags request dock` hat {starter['antwort']!r} geantwortet - "
        "dann ist gar nichts eingefahren")

    assert STARTER not in starter["flaechen_aus"], (
        "der Starterknopf liegt noch auf dem Schirm, obwohl das Dock "
        "eingefahren ist - er faengt dort weiterhin Klicks ab. Siehe "
        "faehrtMitDemDock() in src/templates/ags-dock.template")

    punkte, kasten = starter["ecke_aus"]
    assert punkte == 0, (
        f"nach SUPER+B bemalen {punkte} Punkte die untere rechte Ecke, "
        f"Kasten {kasten} - genau die Sorte Rest, die am 20.08.2026 fuer "
        f"den Abschaltknopf gemeldet wurde")

    punkte, kasten = starter["unten_aus"]
    assert punkte == 0, (
        f"nach SUPER+B bemalen {punkte} Punkte das untere Drittel, "
        f"Kasten {kasten} - unten soll gar nichts stehenbleiben")


def test_er_kommt_mit_dem_dock_unveraendert_zurueck(starter):
    """Nicht "ungefaehr wieder da": dieselbe Punktzahl, derselbe Kasten,
    dieselbe Flaeche an derselben Stelle."""
    assert starter["antwort_zurueck"] == "shown"

    vorher, kasten_vorher = starter["unten_an"]
    nachher, kasten_nachher = starter["unten_zurueck"]
    assert vorher > 0, "vor SUPER+B war unten gar nichts zu sehen"
    assert (nachher, kasten_nachher) == (vorher, kasten_vorher), (
        f"vor dem Einfahren bemalten {vorher} Punkte {kasten_vorher}, "
        f"danach {nachher} Punkte {kasten_nachher}")
    assert starter["flaechen_zurueck"].get(STARTER) == \
        starter["flaechen_an"].get(STARTER), \
        "der Starterknopf kam woanders zurueck"


def test_er_reserviert_keinen_streifen(starter):
    """Astal.Exclusivity.IGNORE, an der einzigen Zahl gemessen, die es
    verraet.

    Ohne IGNORE naehme diese Flaeche unten rechts einen Streifen in
    Anspruch, in dem keine Fenster liegen duerfen - und der Schirm
    reservierte mehr, als das Dock allein kostet. GEMESSEN am 20.08.2026
    mit diesem Knopf auf dem Schirm: 84 -> 0 -> 84, dieselben drei Zahlen
    wie ohne ihn (tests/render/test_einfahrt.py).

    Die 84 sind STYLE_BAR_THICKNESS (60) plus STYLE_GAPS_OUT (24), also
    die Ableitung und nicht eine Zahl von hier.
    """
    erwartet = size_of("STYLE_BAR_THICKNESS") + size_of("STYLE_GAPS_OUT")

    assert starter["reserviert_an"] == erwartet, (
        f"mit Dock und Starterknopf reserviert der Schirm unten "
        f"{starter['reserviert_an']} px, die Ableitung sagt {erwartet} - "
        f"der Knopf traegt etwas bei, obwohl er IGNORE ist")
    assert starter["reserviert_aus"] == 0, (
        f"das Dock ist eingefahren, und der Schirm haelt unten weiterhin "
        f"{starter['reserviert_aus']} px frei")
    assert starter["reserviert_zurueck"] == erwartet, (
        f"nach dem Wiederausfahren reserviert der Schirm "
        f"{starter['reserviert_zurueck']} px statt {erwartet}")


def test_er_steht_auf_jedem_schirm_und_nicht_nur_auf_einem(starter):
    """Mehrere Schirme, an einer Zahl gemessen.

    Der Knopf baut eine Flaeche JE Monitor - dieselbe Entscheidung, die
    das Dock und der Abschaltknopf schon getroffen haben, und aus
    demselben Grund: eine Faehigkeit, die es nur auf einem von mehreren
    Schirmen gibt, ist auf jedem anderen ein Griff ins Leere.

    Die Bildmessungen oben koennen das nicht beantworten - `layers()`
    liest ABSICHTLICH nur den abgebildeten Ausgang, sonst zaehlte es jede
    Flaeche doppelt. Gezaehlt wird deshalb hier: das Klick-Kind sucht
    ALLE Fenster mit der CSS-Klasse des Knopfes und schreibt auf, wie
    viele es waren.

    Dass dieser Aufbau ueberhaupt zwei Schirme hat, ist kein Kunstgriff
    fuer diesen Test: der verschachtelte Compositor fuehrt ohnehin den
    Ausgang des Wirtsfensters und den headless-Ausgang nebeneinander
    (siehe desktop_session.py). Hier wird nur zum ersten Mal etwas
    daraus gefolgert.
    """
    protokoll = starter["klick_protokoll"]
    assert f"GEKLICKT:{starter['schirme']}" in protokoll, (
        f"das Kind hat nicht auf allen {starter['schirme']} Schirmen "
        f"einen Knopf gefunden - eine kleinere Zahl heisst, dass auf "
        f"mindestens einem davon keiner steht:\n" + protokoll)


def test_die_oberflaeche_baut_ihn_ueberhaupt(starter):
    """Ein Fehler beim Bauen faenge app.ts ab (try/catch), und der Knopf
    fehlte still. Das Protokoll sagt, welcher der beiden Zweige lief."""
    protokoll = starter["schalen_protokoll"]
    assert "StarterButton loaded successfully" in protokoll, (
        "app.ts meldet den Starterknopf nicht als gebaut:\n" + protokoll)
    assert "Failed to create StarterButton" not in protokoll, (
        "app.ts hat den Starterknopf nicht bauen koennen:\n" + protokoll)


# --------------------------------------------------------------------
# "was im Prinzip wie SUPER+SPACE macht"
# --------------------------------------------------------------------

def test_ein_klick_fragt_zuerst_den_dispatcher_des_plugins(starter):
    """Die erste Haelfte des Weges, den SUPER+SPACE nimmt.

    Der Knopf fragt den Compositor, bevor er irgendetwas startet - und
    der Compositor antwortet hier, weil in diesem Aufbau kein Plugin
    geladen ist, mit seinem eigenen Satz. DASS dieser Satz im Protokoll
    steht, ist der Beweis, dass der Dispatcher wirklich versucht wurde
    und der Rueckfall nicht einfach fest verdrahtet ist.
    """
    protokoll = starter["klick_protokoll"]
    assert "hyprlaunch antwortet:" in protokoll, (
        "der Knopf hat den Compositor gar nicht erst gefragt:\n"
        + protokoll)
    assert "Invalid dispatcher" in protokoll, (
        "der Compositor hat auf `dispatch hyprlaunch:toggle` etwas "
        "anderes geantwortet als den erwarteten Satz ueber den "
        "fehlenden Dispatcher. Entweder ist hier doch ein Plugin "
        "geladen - dann misst dieser Lauf den anderen Zweig - oder die "
        "Antwort hat sich geaendert:\n" + protokoll)


def test_ein_klick_oeffnet_dann_denselben_starter_wie_die_taste(starter):
    """Die zweite Haelfte - und sie wird nicht gelesen, sondern gelaufen.

    Die Attrappe ist ein echtes Programm, das der Knopf ueber execAsync
    wirklich gestartet hat; was in der Marke steht, sind die Argumente,
    mit denen es gerufen wurde. Verglichen wird gegen
    hyprland-plugins-config.template - die Datei, in der die Taste
    SUPER+SPACE gebunden wird -, damit hier nicht zwei Wege
    nebeneinanderstehen, die sich unabhaengig voneinander aendern
    koennen.
    """
    gerufen = starter["gerufen_mit"]
    assert gerufen is not None, (
        "der Rueckfall hat nichts gestartet - ein Klick auf einer "
        "Maschine ohne hyprlaunch-Plugin taete damit gar nichts:\n"
        + starter["klick_protokoll"])

    rueckfall = starter["rueckfall"]
    assert gerufen.split() == rueckfall[1:], (
        f"die Attrappe wurde mit {gerufen!r} gerufen, die Vorlage fuehrt "
        f"{rueckfall}")

    gebunden = (ROOT / "src" / "templates"
                / "hyprland-plugins-config.template").read_text(
                    encoding="utf-8")
    befehl = " ".join(rueckfall)
    assert f"bind = $mainMod, SPACE, exec, {befehl}" in gebunden, (
        f"SUPER+SPACE bindet in hyprland-plugins-config.template etwas "
        f"anderes als {befehl!r} - dann oeffnet der Knopf einen zweiten "
        f"Starter neben dem der Taste")
