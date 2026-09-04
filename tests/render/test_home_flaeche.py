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

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.render import measure                      # noqa: E402
from tests.render.desktop_session import (             # noqa: E402
    Session, bundle, render_configuration, required_tools, size_of,
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

# WO DIE SYMBOLE FUER DEN UMZUG LIEGEN - siehe die Vorrichtung unten.
# Acht je Reihe, damit auch eine lange Auslieferungsliste in die oberen
# Reihen passt und die Zeile 3 in jedem Fall frei bleibt.
SPALTEN_JE_REIHE = 8
QUELLE = (0, 0)
ZIEL = (0, 3)

# Die modulweite Vorrichtung `gemessen` startet eine verschachtelte
# Sitzung und ruft dazu src/settings.py als Kind, um ein Symbol
# wegzunehmen. Ebene, Groesse und Klickdurchlass des Homes sind alle
# drei Aussagen ueber den Compositor und keine ueber ein Widget.
pytestmark = pytest.mark.allow_subprocess


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
        # AUF DIE RUHE UND NICHT AUF DIE UHR - seit dem 04.09.2026.
        # Hier stand `time.sleep(SETTLE)`. Warum "die Flaeche ist da"
        # dafuer NICHT reicht, steht bei Session.warte_auf_ruhe() - mit
        # den Zahlen, die dieser Lauf dabei gemessen hat.
        sitzung.warte_auf_ruhe(NAMENSRAUM, "zepos-dock", "zepos-bar",
                               frist=40.0)

        ebenen = _ebenen(sitzung)
        flaechen = sitzung.layers()
        assert NAMENSRAUM in ebenen, (
            "das Home liegt nicht auf dem Schirm:\n"
            + sitzung.read_shell_log())
        mit_home = sitzung.shoot(bilder / "mit-home.png")

        # ================================================================
        # DIE FREMDE AENDERUNG - seit dem 21.08.2026 (Aufgabe 53)
        # ================================================================
        #
        # GEMELDET aus 0.1.7, woertlich: "auch im ags launcher bzw
        # hyprlauncher kann ich nicht mit rechtsklick zu home hinzufügen,
        # und wenn ich es dort mit der dock versuche dann passiert
        # nichts".
        #
        # Der Fuss und der Starter bieten seither "Vom Home entfernen"
        # an, und sie setzen dafuer GENAU DIESEN BEFEHL ab -
        # `settings.py home remove <name>`. Hier laeuft er von aussen,
        # waehrend die Oberflaeche steht: kein `ags request`, kein
        # Neustart, kein Erzeugungslauf. Was danach auf dem Bild steht,
        # ist die Antwort auf "kommt es an?".
        entfernt = _nimm_das_erste_symbol_weg(bau)
        time.sleep(SETTLE)
        ohne_erstes = sitzung.shoot(bilder / "ohne-erstes.png")
        ebenen_danach = _ebenen(sitzung)
        flaechen_danach = sitzung.layers()

        # ================================================================
        # DER UMZUG - 03.09.2026
        # ================================================================
        #
        # GEMELDET, woertlich: "ja auf home wenn ich eine icon verschiebe
        # dann ja aber auch das passiert nicht live !!!! ich muss mich
        # ausloggen damit der icon verschoben ist".
        #
        # ZWEI SCHRITTE, und beide gehen ueber `settings.py home set` -
        # den Befehl, den der "drop"-Rueckruf in ags-home.template ueber
        # homeSet() absetzt, wenn ein Symbol abgelegt wird:
        #
        #     1. jedes Symbol bekommt eine ausdrueckliche Zelle. Danach
        #        steht fest, wo welches liegt - ohne diesen Schritt legt
        #        das Home sie selbst, und der Test wuesste es nicht.
        #     2. EINES zieht um, von QUELLE nach ZIEL. Die Belegung ist
        #        sonst dieselbe, genau wie beim Ablegen.
        #
        # Dazwischen liegt kein Neustart, kein Erzeugungslauf, kein
        # `ags request`. Was das zweite Bild vom ersten unterscheidet,
        # ist die Antwort auf "geht das live?".
        namen = _namen(bau)
        assert len(namen) >= 2, (
            f"fuer den Umzug liegen zu wenige Symbole auf dem Home: {namen}")
        _lege(bau, _in_reihen(namen))
        time.sleep(SETTLE)
        in_reihen = sitzung.shoot(bilder / "in-reihen.png")

        belegung = _in_reihen(namen)
        belegung[0]["col"], belegung[0]["row"] = ZIEL
        _lege(bau, belegung)
        time.sleep(SETTLE)
        nach_umzug = sitzung.shoot(bilder / "nach-umzug.png")
        kasten = sitzung.layers().get(NAMENSRAUM)

        return {
            "ebenen": ebenen,
            "flaechen": flaechen,
            "vorher": measure.read_png(nur_tapete),
            "nachher": measure.read_png(mit_home),
            "entfernt": entfernt,
            "danach": measure.read_png(ohne_erstes),
            "ebenen_danach": ebenen_danach,
            "flaechen_danach": flaechen_danach,
            "in_reihen": measure.read_png(in_reihen),
            "nach_umzug": measure.read_png(nach_umzug),
            "umgezogen": namen[0],
            "kasten": kasten,
            "protokoll": sitzung.read_shell_log(),
        }


def _nimm_das_erste_symbol_weg(bau: Path) -> str:
    """Ein Symbol vom Home nehmen - von AUSSEN, ueber settings.py.

    DERSELBE BEFEHL, DEN DER FUSS UND DER STARTER ABSETZEN
        `settings.py home remove <name>` - genau das, was ihr
        Menuepunkt "Vom Home entfernen" seit dem 21.08.2026 ruft. Kein
        `ags request`, kein Erzeugungslauf, kein Neustart: nur ein
        Schreibvorgang in user-settings.json, waehrend die Oberflaeche
        steht.

    DAS ERSTE UND NICHT IRGENDEINES: die uebrigen ruecken dadurch alle
    eine Zelle auf, und die erste Symbolspalte sieht danach ganz anders
    aus. Ein Symbol aus der Mitte einer spaeteren Spalte aenderte nur
    seine eigene Zelle - messbar, aber knapp.

    ZEPOS_USER_ROOT zeigt dorthin, wo die Oberflaeche ihre Datei sucht:
    Session.shell() reicht XDG_CONFIG_HOME=<bau> durch, und
    utils/user-settings.ts leitet daraus `<bau>/zepos` ab (dieselbe
    Ableitung wie src/paths.py).
    """
    namen = _namen(bau)
    assert namen, "auf dem Home lag nichts - dann misst dieser Lauf nichts"

    fertig = subprocess.run(
        [sys.executable, str(ROOT / "src" / "settings.py"),
         "home", "remove", namen[0]],
        capture_output=True, text=True, env=_umgebung(bau), timeout=60)
    assert fertig.returncode == 0, f"{namen[0]}: {fertig.stderr}"
    return namen[0]


def _umgebung(bau: Path) -> dict[str, str]:
    """Die Umgebung, in der settings.py DIESELBE Datei sieht wie die
    laufende Oberflaeche.

    ZEPOS_USER_ROOT zeigt dorthin, wo die Oberflaeche ihre Datei sucht:
    Session.shell() reicht XDG_CONFIG_HOME=<bau> durch, und
    utils/user-settings.ts leitet daraus `<bau>/zepos` ab (dieselbe
    Ableitung wie src/paths.py).
    """
    return {"PATH": os.environ.get("PATH", "/usr/bin"),
            "ZEPOS_SYSTEM_ROOT": str(ROOT / "src"),
            "ZEPOS_USER_ROOT": str(bau / "zepos")}


def _namen(bau: Path) -> list[str]:
    """Was gerade auf dem Home liegt, in seiner Reihenfolge."""
    plan = subprocess.run(
        [sys.executable, str(ROOT / "src" / "settings.py"), "home"],
        capture_output=True, text=True, env=_umgebung(bau), timeout=60)
    assert plan.returncode == 0, plan.stderr
    return [icon["name"] for icon in json.loads(plan.stdout)["icons"]]


def _lege(bau: Path, belegung: list[dict]) -> None:
    """`settings.py home set` - GENAU der Befehl, den das Ablegen absetzt.

    Der "drop"-Rueckruf in ags-home.template ruft homeSet() mit der
    GESAMTEN Belegung, und homeSet() setzt diesen Befehl ab. Von aussen
    gerufen ist er derselbe Schreibvorgang, nur ohne den Zeiger - und
    der Zeiger ist nicht der Teil, der gemeldet wurde.
    """
    fertig = subprocess.run(
        [sys.executable, str(ROOT / "src" / "settings.py"),
         "home", "set", json.dumps(belegung)],
        capture_output=True, text=True, env=_umgebung(bau), timeout=60)
    assert fertig.returncode == 0, fertig.stderr


def _in_reihen(namen: list[str]) -> list[dict]:
    """Jedem Symbol eine AUSDRUECKLICHE Zelle geben.

    Ohne sie legt das Home die Symbole selbst, und dieser Test wuesste
    nicht, wo sie liegen. Mit ihr steht vor dem Umzug fest, welche Zelle
    leer werden muss und welche sich fuellen soll.
    """
    return [{"name": name,
             "col": nummer % SPALTEN_JE_REIHE,
             "row": nummer // SPALTEN_JE_REIHE}
            for nummer, name in enumerate(namen)]


def _zelle(kasten: tuple[int, int, int, int], spalte: int,
           reihe: int) -> tuple[int, int, int, int]:
    """Das Rechteck einer Zelle auf dem Bild, ein Stueck eingerueckt.

    Die Rechnung ist die des Homes, rueckwaerts: `EDGE_GAP + col * CELL`
    (ags-home.template), auf dem Bild um die Ecke der Flaeche versetzt.
    Beide Zahlen kommen aus src/sizes.py und nicht von hier.

    EINGERUECKT UM EIN SECHSTEL, damit die Beschriftung des Nachbarn
    nicht mitzaehlt: sie ist CELL breit und darf ihre Zelle an den
    Raendern weich verlassen. Das Symbol selbst sitzt in der Mitte.
    """
    x, y, _breite, _hoehe = kasten
    kante = size_of("STYLE_HOME_CELL")
    rand = size_of("STYLE_GAPS_OUT")
    innen = kante // 6
    return (x + rand + spalte * kante + innen,
            y + rand + reihe * kante + innen,
            kante - 2 * innen, kante - 2 * innen)


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


# --------------------------------------------------------------------
# Dass eine Aenderung aus einem ANDEREN Fenster ankommt
# --------------------------------------------------------------------

def test_eine_fremde_aenderung_erreicht_das_home_ohne_neustart(gemessen):
    """Der Fehler aus 0.1.7, von der anderen Seite gemessen.

    Zwischen dem Bild mit allen Symbolen und diesem liegt NICHTS ausser
    einem `settings.py home remove` in einem fremden Prozess - kein
    Neustart, kein Erzeugungslauf, kein `ags request`. Was die Aenderung
    ankommen laesst, ist der Gio.FileMonitor in
    utils/user-settings.ts.

    GEMESSEN wird in der ersten Symbolspalte, weil dort das
    weggenommene Symbol stand und alle uebrigen um eine Zelle
    aufruecken - dieselbe Messflaeche wie in
    test_das_home_zeichnet_wirklich_symbole, nur dass dort "es ist
    ueberhaupt etwas da" der Befund ist und hier "es hat sich
    geaendert".

    AB x+8 UND NICHT AB x+2, und das ist gemessen: bei x+2 liegt der
    Rand der Nachbarflaeche, und die ist auf dem Bild "nur Tapete" gar
    nicht da (dort lief noch keine Oberflaeche). GEMESSEN am
    21.08.2026: die Abweichungen dieser einen Spalte waren um 1 bis 15
    Stufen gross - ein weicher Rand, kein Symbol.
    """
    mit, danach = gemessen["nachher"], gemessen["danach"]
    x, y, _breite, hoehe = gemessen["flaechen"][NAMENSRAUM]
    LINKER_RAND = 8

    geaendert = 0
    for px in range(x + LINKER_RAND, x + 200, 3):
        for py in range(y + 2, y + hoehe - 2, 3):
            if mit.at(px, py) != danach.at(px, py):
                geaendert += 1

    assert geaendert > 100, (
        f"nur {geaendert} Bildpunkte haben sich geaendert, nachdem "
        f"\"{gemessen['entfernt']}\" von aussen vom Home genommen wurde - "
        f"die Aenderung ist nicht angekommen.\n"
        + gemessen["protokoll"][-2000:])


def test_die_flaeche_des_homes_bleibt_dabei_liegen(gemessen):
    """Ein Home, dem ein Symbol fehlt, ist immer noch ein Home.

    Es darf dabei weder verschwinden noch die Ebene wechseln: die
    Flaeche traegt das Rechtsklickmenue der freien Flaeche ("Anwendung
    starten", "Aufraeumen", "Tapete", "Einstellungen"), und `bottom` ist
    die Sicherung, an der die Bedienbarkeit jedes Fensters haengt (siehe
    Messung 2 im Kopf von ags-home.template).

    NICHT das RECHTECK: die Hoehe des Homes ist der Schirm minus die
    reservierten Zonen, und die des Fusses aendert sich mit seinem
    Inhalt. Eine Zusicherung darueber waere eine Zusicherung ueber den
    Fuss, und die steht in tests/render/test_dock_breite.py.
    """
    assert NAMENSRAUM in gemessen["ebenen_danach"], (
        "das Home ist mit dem weggenommenen Symbol verschwunden:\n"
        + gemessen["protokoll"][-2000:])
    assert gemessen["ebenen_danach"][NAMENSRAUM] == "bottom", (
        gemessen["ebenen_danach"])
    assert NAMENSRAUM in gemessen["flaechen_danach"], (
        gemessen["flaechen_danach"])


# --------------------------------------------------------------------
# Dass ein VERSCHOBENES Symbol sofort woanders liegt
# --------------------------------------------------------------------

def test_ein_verschobenes_symbol_liegt_sofort_an_seinem_neuen_platz(gemessen):
    """Die andere Haelfte der Meldung vom 03.09.2026.

    "ich muss mich ausloggen damit der icon verschoben ist" - also war
    der Schreibvorgang da und das Bild blieb stehen. Zwischen den beiden
    Bildern dieser Messung liegt ein einziges `settings.py home set`,
    dasselbe, das homeSet() aus dem "drop"-Rueckruf absetzt. Ist die
    Zielzelle danach unveraendert, ist der Umzug NICHT angekommen.

    GEMESSEN WIRD IN DER ZELLE UND NICHT AUF DEM GANZEN SCHIRM: "es hat
    sich irgendwo etwas geaendert" waere auch dann wahr, wenn nur eine
    Uhr weitergelaufen ist.
    """
    assert gemessen["kasten"], (
        "nach dem Umzug liegt das Home nicht mehr auf dem Schirm:\n"
        + gemessen["protokoll"][-2000:])
    ziel = _zelle(gemessen["kasten"], *ZIEL)
    punkte = measure.changed_pixels(
        gemessen["in_reihen"], gemessen["nach_umzug"], ziel)

    assert len(punkte) > 200, (
        f"in der Zielzelle {ZIEL} haben sich nur {len(punkte)} Bildpunkte "
        f"geaendert, nachdem \"{gemessen['umgezogen']}\" dorthin gelegt "
        f"wurde - der Umzug ist nicht angekommen. Gemessen im Rechteck "
        f"{ziel}.\n" + gemessen["protokoll"][-2000:])


def test_die_alte_zelle_ist_danach_wirklich_leer(gemessen):
    """Und es liegt nicht ZWEIMAL da.

    Ein Home, das das neue Symbol zeichnet, ohne das alte wegzunehmen,
    saehe auf dem Zielbild richtig aus und waere trotzdem falsch. Die
    Gegenprobe ist die Tapete: das Home malt keinen Hintergrund (siehe
    test_die_tapete_scheint_durch_das_home), eine leere Zelle ist also
    Bildpunkt fuer Bildpunkt die Tapete.

    DIE FUENFZIG PUNKTE TOLERANZ sind kein Spielraum fuer ein halbes
    Symbol: das Rechteck ist 64x64 = 4096 Punkte gross, und ein Symbol
    schlaegt dort ueber zweihundert. Sie fangen den weichen Rand einer
    Nachbarbeschriftung ab, mehr nicht.
    """
    quelle = _zelle(gemessen["kasten"], *QUELLE)
    vorher = measure.changed_pixels(
        gemessen["vorher"], gemessen["in_reihen"], quelle)
    nachher = measure.changed_pixels(
        gemessen["vorher"], gemessen["nach_umzug"], quelle)

    assert len(vorher) > 200, (
        f"in der Quellzelle {QUELLE} lag vor dem Umzug nichts "
        f"({len(vorher)} Punkte gegen die blosse Tapete) - dann misst "
        f"diese Zusicherung nichts. Gemessen im Rechteck {quelle}.\n"
        + gemessen["protokoll"][-2000:])
    assert len(nachher) <= 50, (
        f"in der Quellzelle {QUELLE} stehen nach dem Umzug noch "
        f"{len(nachher)} Bildpunkte ueber der Tapete - "
        f"\"{gemessen['umgezogen']}\" liegt jetzt an ZWEI Stellen.\n"
        + gemessen["protokoll"][-2000:])
