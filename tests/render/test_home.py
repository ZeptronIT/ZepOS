# SPDX-License-Identifier: GPL-3.0-or-later
"""Das Home, an einem laufenden Compositor gemessen.

WARUM DIESE ZUSICHERUNG NICHT KOPFLOS LAUFEN KANN
    Die drei Aussagen, auf denen das Home steht, sind alle drei Aussagen
    ueber den COMPOSITOR und nicht ueber ein Widget:

      auf welcher Ebene      entscheidet, ob ein Klick beim Fenster
      es liegt               bleibt und ob ein Tapetenwechsel es
                             verdeckt
      wie gross es wird      entscheidet der Compositor aus Anker und
                             exklusiver Zone, nicht das Widget
      ob die Tapete          entscheidet die undurchsichtige Region,
      durchscheint           die GTK anmeldet

    Keine davon ist einer Rechnung zugaenglich. Eine kopflose Messung
    saehe ein Widget, das genau das behauptet, was man hineingegeben hat.

DIE MESSUNG, DIE DIESER DATEI IHREN NAMEN GIBT
    GEMESSEN am 20.08.2026 im verschachtelten Compositor, bevor diese
    Vorlage entstand: eine bildschirmfuellende Layer-Shell-Flaeche OHNE
    `background: transparent` malt GTKs helles Grau ueber den ganzen
    Schirm. Tapete gruen (0,204,0), Bildpunkt in der Schirmmitte:

        ohne die Regel   (246, 245, 244)
        mit  der Regel   (0, 204, 0)

    GTK meldet `wl_surface.set_opaque_region(0, 0, <ganzer Schirm>)`,
    solange die Flaeche einen Hintergrund hat. Ein Home, das diese Regel
    verliert, ist keine halbdurchsichtige Scheibe - es ist eine graue
    Platte, hinter der die Tapete VERSCHWINDET. Das ist der Fehler, den
    test_die_tapete_scheint_durch_das_home unten fangen soll, und er ist
    ein einzelnes verlorenes CSS-Wort weit entfernt.
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
    Session, bundle, render_configuration, required_tools,
    workspaces_file,
)

# Dieselbe Beruhigungszeit wie in test_geometry.py: das Home fragt
# settings.py in einem Kindprozess, und ein Bild vor dessen Antwort
# zeigte eine leere Flaeche.
SETTLE = 6.0

BREITE, HOEHE = 1920, 1080

# Die Ebenen, wie Hyprland sie in `hyprctl layers` durchnummeriert.
# Ausgeschrieben, weil "1" an einer Zusicherung nichts sagt und
# "bottom" alles.
EBENEN = {"0": "background", "1": "bottom", "2": "top", "3": "overlay"}

NAMENSRAUM = "zepos-home"


def _ebenen(sitzung) -> dict[str, str]:
    """Namensraum -> Ebene, nur fuer den abgebildeten Schirm.

    Session.layers() gibt die Rechtecke und laesst die Ebene weg - sie
    hat sie fuer Kopf und Fuss nie gebraucht, weil beide auf `top`
    liegen. Fuer das Home IST die Ebene die Aussage, also wird sie hier
    gelesen. Kein zweiter Weg zu denselben Daten: derselbe
    `hyprctl layers`-Aufruf, nur eine andere Frage daran.
    """
    daten = sitzung.hyprctl_json("layers") or {}
    heraus: dict[str, str] = {}
    for name, schirm in daten.items():
        if name != sitzung.output:
            continue
        for nummer, eintraege in schirm.get("levels", {}).items():
            for flaeche in eintraege:
                heraus[flaeche.get("namespace")] = EBENEN.get(nummer, nummer)
    return heraus


@pytest.fixture(scope="module")
def gemessen(tmp_path_factory) -> dict:
    """Ein Schirm mit Tapete, einmal ohne und einmal mit dem Home."""
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Bildlauf fehlt: {', '.join(fehlt)}")

    bau = tmp_path_factory.mktemp("zephome-bau")
    bilder = tmp_path_factory.mktemp("zephome-bild")
    ags = render_configuration(bau)
    bundle(ags, bau)

    with Session(BREITE, HOEHE) as sitzung:
        sitzung.start_bus()
        workspaces_file(bau, sitzung.output)
        ergebnis = sitzung.hyprctl("keyword", "cursor:invisible", "true")
        assert ergebnis.returncode == 0, (
            f"cursor:invisible liess sich nicht setzen: {ergebnis.stderr}")

        # Die Tapete, wie sie auf einer Installation entsteht: swaybg auf
        # `background`. Ohne sie waere jede Aussage ueber Durchsicht eine
        # Aussage ueber Schwarz.
        sitzung.wallpaper()
        sitzung.move_cursor(BREITE // 2, HOEHE // 2)
        time.sleep(2.0)
        nur_tapete = sitzung.shoot(bilder / "nur-tapete.png")

        sitzung.shell(bau / "zepos-shell.js", bau)
        time.sleep(SETTLE)

        ebenen = _ebenen(sitzung)
        flaechen = sitzung.layers()
        assert NAMENSRAUM in ebenen, (
            "das Home liegt nicht auf dem Schirm:\n"
            + sitzung.read_shell_log())
        mit_home = sitzung.shoot(bilder / "mit-home.png")

        return {
            "ebenen": ebenen,
            "flaechen": flaechen,
            "vorher": measure.read_png(nur_tapete),
            "nachher": measure.read_png(mit_home),
            "protokoll": sitzung.read_shell_log(),
        }


def test_das_home_liegt_auf_bottom(gemessen):
    """Die Ebene IST die Sicherung, an der die Bedienbarkeit haengt.

    GEMESSEN am 20.08.2026: GTK4 ruft `wl_surface.set_input_region` nie
    (`grep -c input_region` im Wayland-Mitschnitt ergab 0), also gilt die
    Vorgabe des Protokolls - die Eingaberegion dieser Flaeche ist der
    GANZE Schirm. Sie beansprucht jeden Bildpunkt fuer sich.

    Dass Fenster trotzdem anklickbar bleiben, entscheidet allein die
    Stapelreihenfolge: der Compositor liefert an die oberste Flaeche am
    Zeigerpunkt, und `bottom` liegt unter jedem gewoehnlichen Fenster.
    Ein Home auf `top` waere eine Sitzung, in der kein Fenster mehr
    einen Klick bekommt.

    Deshalb steht hier die Ebene und nicht ein simulierter Klick: die
    Ebene ist die URSACHE, und sie ist ohne Eingabewerkzeug messbar -
    diese Maschine hat weder wlrctl noch ydotool (siehe den Kopf von
    tests/render/starter_click_child.tsx).
    """
    assert gemessen["ebenen"][NAMENSRAUM] == "bottom", (
        f"das Home liegt auf {gemessen['ebenen'][NAMENSRAUM]!r} statt auf "
        "'bottom' - auf jeder hoeheren Ebene schluckt es die Klicks, die "
        "den Fenstern gelten, und der Nutzer kann nichts mehr bedienen")


def test_das_home_liegt_ueber_der_tapete_und_unter_der_leiste(gemessen):
    """Die drei Ebenen in der Reihenfolge, in der sie stehen muessen.

    swaybg auf `background`, das Home darueber auf `bottom`, Leiste und
    Fuss auf `top`. Der mittlere Platz ist der einzige, der beides kann:
    ueber der Tapete (sonst saehe man die Symbole nicht) und unter den
    Fenstern (sonst bedient man nichts mehr).

    WARUM NICHT AUF `background` NEBEN swaybg - GEMESSEN am 20.08.2026
        Auf DERSELBEN Ebene entscheidet die Anmeldereihenfolge, und
        wallpaper-manager startet swaybg bei jedem Tapetenwechsel neu:

            vor dem Wechsel:   ['wallpaper', 'zepos-home']
            nach dem Wechsel:  ['zepos-home', 'wallpaper']

        Nach dem ersten Tapetenwechsel laege die Tapete ueber dem Home,
        und die Symbole waeren fort - lautlos.
    """
    ebenen = gemessen["ebenen"]
    assert ebenen.get("wallpaper") == "background", (
        "die Tapete liegt nicht auf 'background' - dann ist die Aussage "
        "dieses Tests ueber die Reihenfolge keine mehr")
    assert ebenen[NAMENSRAUM] == "bottom"
    for streifen in ("zepos-bar", "zepos-dock"):
        assert ebenen.get(streifen) == "top", (
            f"{streifen} liegt nicht mehr auf 'top' - das Home wuerde "
            "darueber liegen")


def test_das_home_laesst_leiste_und_fuss_ihren_streifen(gemessen):
    """Exclusivity.NORMAL, an der zugeteilten Flaeche gemessen.

    Mit IGNORE (exclusive_zone -1) laege das Home UNTER der Leiste, und
    die oberste Symbolzeile stuende hinter ihr. Unter Windows liegt auch
    kein Symbol unter der Taskleiste.

    Und es darf selbst NICHTS reservieren: eine bildschirmfuellende
    Flaeche mit eigener exklusiver Zone naehme jedem Fenster den Platz.
    Das wird daran gemessen, dass Leiste und Fuss noch dort liegen, wo
    sie liegen - eine Zone des Homes haette sie verschoben.
    """
    home = gemessen["flaechen"][NAMENSRAUM]
    x, y, breite, hoehe = home

    assert x == 0, f"das Home faengt bei x={x} an und nicht am linken Rand"
    assert breite == BREITE, (
        f"das Home ist {breite} breit und der Schirm {BREITE} - es "
        "verankert sich nicht mehr an beiden Seitenkanten")

    bar = gemessen["flaechen"]["zepos-bar"]
    dock = gemessen["flaechen"]["zepos-dock"]
    assert y >= bar[1] + bar[3], (
        f"das Home faengt bei y={y} an, die Leiste endet bei "
        f"{bar[1] + bar[3]} - es liegt unter ihr")
    assert y + hoehe <= dock[1], (
        f"das Home endet bei y={y + hoehe}, der Fuss faengt bei {dock[1]} "
        "an - es liegt unter ihm")


def test_die_tapete_scheint_durch_das_home(gemessen):
    """DIE Zusicherung dieser Datei - siehe den Kopf.

    Gemessen wird an einem Streifen, auf dem KEIN Symbol liegt: die
    Symbole fuellen sich spaltenweise vom linken Rand nach unten (siehe
    lege() in ags-home.template), das rechte Viertel bleibt bei der
    ausgelieferten Auswahl frei. Dort muss das Bild MIT Home Punkt fuer
    Punkt dasselbe sein wie das Bild ohne.

    Ein Unterschied dort heisst: das Home malt eine Flaeche. Und weil es
    den ganzen Schirm einnimmt, heisst "malt eine Flaeche" hier
    "verdeckt die Tapete vollstaendig".
    """
    vorher, nachher = gemessen["vorher"], gemessen["nachher"]
    home = gemessen["flaechen"][NAMENSRAUM]
    x, y, breite, hoehe = home

    # Das rechte Viertel des Homes, mit Sicherheitsabstand zu seinen
    # Kanten - dort steht bei der ausgelieferten Auswahl kein Symbol.
    links = x + (breite * 3) // 4
    rechts = x + breite - 4
    oben = y + 4
    unten = y + hoehe - 4

    verschieden = []
    for px in range(links, rechts, 17):
        for py in range(oben, unten, 17):
            if vorher.at(px, py) != nachher.at(px, py):
                verschieden.append((px, py, vorher.at(px, py),
                                    nachher.at(px, py)))

    assert verschieden == [], (
        f"{len(verschieden)} Bildpunkte auf der freien Flaeche haben ihre "
        "Farbe gewechselt, obwohl dort kein Symbol liegt - das Home malt "
        "einen Hintergrund und verdeckt damit die Tapete. Die Regel, die "
        "fehlt, heisst `background: transparent` auf window.home-window "
        f"in src/styles/home-style.template. Erste Abweichungen: "
        f"{verschieden[:5]}")


def test_das_home_zeichnet_wirklich_symbole(gemessen):
    """Die Gegenprobe zur Zusicherung darueber.

    Ohne sie bestuende "die Tapete scheint durch" auch ein Home, das gar
    nichts zeichnet - und zwar am besten von allen. Gemessen wird am
    LINKEN Rand, wo die erste Symbolspalte steht: dort MUSS sich etwas
    geaendert haben.
    """
    vorher, nachher = gemessen["vorher"], gemessen["nachher"]
    x, y, _breite, hoehe = gemessen["flaechen"][NAMENSRAUM]

    geaendert = 0
    for px in range(x + 2, x + 200, 3):
        for py in range(y + 2, y + hoehe - 2, 3):
            if vorher.at(px, py) != nachher.at(px, py):
                geaendert += 1

    assert geaendert > 100, (
        f"nur {geaendert} Bildpunkte haben sich in der ersten Symbolspalte "
        "geaendert - das Home zeichnet keine Symbole. Was das Protokoll "
        "sagt:\n" + gemessen["protokoll"][-2000:])
