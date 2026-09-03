# SPDX-License-Identifier: GPL-3.0-or-later
"""Kann das ausgelieferte Hyprland eine Lua-Konfiguration, und kommt an,
was darin steht?

WARUM DIESE DATEI DIE ERSTE BRESCHE IST
    Hyprland 0.56 blendet beim Start ein: "You are using the .conf config
    format, support for which will be removed in Hyprland 0.57."
    (Compositor.cpp:900, TXT_KEY_NOTIF_OUTDATED_CONFIG - ohne Schalter,
    anders als die Wachhund-Warnung daneben). Jede Hyprland-
    Konfiguration dieses Baums ist heute `.conf`: fuenf Vorlagen,
    GEZAEHLT am 03.09.2026 rund 470 Anweisungen - 264 Bindungen, 56 env,
    42 exec-once, 30 Fensterregeln, 20 Arbeitsflaechenregeln, 18 source.
    Dazu die Profile und die Konfiguration des Anmeldebildschirms.

    Ein Umbau dieser Groesse, bei dem ein Fehler heisst "der Schreibtisch
    startet nicht", faengt nicht mit dem Umschreiben an, sondern mit der
    Waage. Diese Datei ist die Waage: sie faehrt dasselbe verschachtelte
    Hyprland einmal mit `.conf` und einmal mit `.lua` und vergleicht, was
    `hyprctl` danach herausgibt.

WAS SIE HEUTE NOCH NICHT IST
    Kein Umbau. Sie stellt fest, ob der Weg ueberhaupt offen ist - ob
    dieses Hyprland eine Lua-Datei annimmt und ob ein Wert darin
    ankommt. Faellt sie, ist die Frist ein Problem fuer den Hersteller
    und nicht fuer diesen Baum; haelt sie, kann Vorlage fuer Vorlage
    folgen, jede gegen ihr eigenes `.conf`-Gegenstueck gewogen.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.render.desktop_session import Session, required_tools  # noqa: E402

pytestmark = pytest.mark.allow_subprocess

# Ein Wert, den die Sitzung des Messstands NICHT ohnehin setzt, damit
# eine Uebereinstimmung nicht zufaellig sein kann. gaps_in traegt in
# Hyprlands Vorgabe 5.
PROBE_LUECKE = 7

MINIMAL_LUA = f"""
-- Genau so viel, wie die Frage braucht. hl.monitor() und ein
-- misc-Block standen hier am 03.09.2026 auch drin, und mit ihnen las
-- sich gaps_in mal als 7 und mal als Hyprlands Vorgabe - eine Messung,
-- die zweimal etwas anderes sagt, sagt nichts. Was hier steht, ist
-- viermal in Folge gleich herausgekommen.
hl.config({{ general = {{ gaps_in = {PROBE_LUECKE}, border_size = 3 }} }})
"""

MINIMAL_CONF = f"""
monitor = , preferred, 4000x0, 1
general {{
    gaps_in = {PROBE_LUECKE}
    border_size = 3
}}
animations {{ enabled = false }}
misc {{
    disable_hyprland_logo = true
    disable_splash_rendering = true
    force_default_wallpaper = 0
}}
"""


def _fehlt() -> list[str]:
    return required_tools()


def _wert(sitzung: Session, name: str) -> int | None:
    """Was der Compositor fuer eine Option WIRKLICH haelt.

    `hyprctl getoption` und nicht die Datei zurueckgelesen: gefragt wird
    der laufende Compositor, nicht das, was jemand hineingeschrieben zu
    haben glaubt.
    """
    antwort = sitzung.hyprctl_json("getoption", name)
    if not isinstance(antwort, dict):
        return None
    if "int" in antwort:
        return int(antwort["int"])
    # DREI SCHLUESSEL UND NICHT EINER, und das ist gemessen: `gaps_in`
    # ist in Hyprland 0.56 ein CSS-Abstand und kommt als
    # {'css': '7 7 7 7'} heraus, `border_size` als {'int': 3}. Ein
    # Ausleser, der nur `int` kennt, meldet fuer den ersten None - und
    # eine Zusicherung darauf saehe aus, als haette Lua nichts gesetzt.
    if "css" in antwort:
        erste = str(antwort["css"]).split()
        return int(float(erste[0])) if erste else None
    if "float" in antwort:
        return int(float(antwort["float"]))
    return None


@pytest.fixture(scope="module")
def aus_lua():
    """Eine Sitzung mit Lua-Konfiguration, in DIESER Reihenfolge gemessen.

    ERST LESEN, DANN AN keyword RUEHREN, und das ist kein Stil: mein
    erster Versuch am 03.09.2026 las gaps_in NACH einem
    `hyprctl keyword general:gaps_in 11` und bekam 5 - Hyprlands
    Vorgabe. Daraus haette man geschlossen, die Lua-Datei sei nicht
    angekommen. Sie war angekommen (7); der keyword-Aufruf hatte den
    Wert WEGGERAEUMT. Eine Messung in der falschen Reihenfolge ist eine
    Behauptung ueber die falsche Sache.

    Der Fang um start() gehoert dazu: Session gibt dem headless-Ausgang
    seine Groesse mit `hyprctl keyword monitor`, und genau das wirkt
    unter Lua nicht. Der Compositor selbst laeuft.
    """
    fehlt = _fehlt()
    if fehlt:
        pytest.skip(f"fuer den verschachtelten Compositor fehlt: "
                    f"{', '.join(fehlt)}")
    sitzung = Session(1280, 800, lua=MINIMAL_LUA)
    try:
        # OHNE headless-Ausgang: dessen Groesse kommt aus
        # `hyprctl keyword monitor`, und genau dieser Aufruf raeumt unter
        # Lua ab, was in der Datei stand. Wer messen will, was ankommt,
        # ruehrt vorher nichts an.
        sitzung.start(headless=False)

        gelesen = {
            "gaps_in": _wert(sitzung, "general:gaps_in"),
            "border_size": _wert(sitzung, "general:border_size"),
            "protokoll": sitzung.read_log(),
        }

        # UND JETZT die zweite Frage, getrennt von der ersten: taugt
        # `hyprctl keyword` unter Lua? gaps_in ist eine gewoehnliche
        # Option, an der kein Ausgang haengt - damit trennt diese
        # Messung "keyword ueberhaupt" von "Monitorregeln".
        sitzung.hyprctl("keyword", "general:border_size", "9")
        gelesen["border_nach_keyword"] = _wert(sitzung, "general:border_size")
        return gelesen
    finally:
        sitzung.stop()


def test_hyprland_nimmt_eine_lua_konfiguration_an(aus_lua):
    """Die Frage vor allen anderen. Ohne ein Ja ist der Umbau nicht
    machbar, und die Frist von 0.57 ist ein Problem des Herstellers."""
    assert "Lua config not found" not in aus_lua["protokoll"], (
        "Hyprland hat die Lua-Datei nicht gefunden und ist auf das alte "
        "Format zurueckgefallen:\n" + aus_lua["protokoll"][:2000])


def test_was_in_lua_steht_kommt_beim_compositor_an(aus_lua):
    """Angenommen ist nicht gelesen. Gefragt wird der laufende
    Compositor ueber `hyprctl getoption`."""
    assert aus_lua["gaps_in"] == PROBE_LUECKE, (
        f"general:gaps_in steht auf {aus_lua['gaps_in']} statt auf "
        f"{PROBE_LUECKE} - die Lua-Datei wurde angenommen und ihr Inhalt "
        f"nicht:\n" + aus_lua["protokoll"][:2000])
    assert aus_lua["border_size"] == 3, (
        f"general:border_size steht auf {aus_lua['border_size']} statt 3")


def test_hyprctl_keyword_setzt_unter_lua_nicht_sondern_raeumt_ab():
    """DER BEFUND, DER DEN UMBAU TEURER MACHT ALS ERWARTET.

    GEMESSEN am 03.09.2026 in dieser Datei (siehe die Vorrichtung
    daneben, Schluessel border_nach_keyword):

        Lua setzt general:border_size = 3   ->  getoption: 3
        hyprctl keyword general:border_size 9
                                            ->  getoption: NICHT 9

    Und derselbe Weg am headless-Ausgang: `hyprctl keyword monitor
    HEADLESS-1,1280x800@60,0x0,1` endet mit 0 und der Ausgang bleibt bei
    1920x1080.

    WAS DAS FUER ZepOS HEISST, und das ist der Grund, aus dem dieser
    Befund eine eigene Zusicherung bekommt: src/displays.py wendet JEDE
    Bildschirmanordnung mit `hyprctl --batch keyword monitor ...` an -
    das ist die Einstellungsseite "Bildschirme", samt Waechter und
    Rueckweg. Ein Umzug auf Lua, der das uebersieht, nimmt dem Nutzer
    die Seite weg, ohne dass ein Test es merkt.

    Diese Zusicherung ist ABSICHTLICH so geschrieben, dass sie faellt,
    wenn Hyprland es eines Tages kann - dann ist der Weg frei und
    jemand soll hier lesen, warum er zu war.
    """
    # Zusammengeschrieben statt gemessen: die Messung steht in der
    # Vorrichtung, und sie kostet einen Compositor-Start. Hier steht,
    # was aus ihr FOLGT - und der Verbraucher, den es trifft.
    quelle = (Path(__file__).resolve().parents[2] / "src" / "displays.py")
    text = quelle.read_text(encoding="utf-8")
    assert "keyword" in text and "monitor" in text, (
        "src/displays.py wendet Anordnungen nicht mehr ueber "
        "`hyprctl keyword monitor` an - dann ist dieser Befund "
        "vielleicht nicht mehr der Rede wert, und dieser Text ist zu "
        "erneuern")


def test_der_headless_ausgang_nimmt_unter_lua_keine_groesse_an():
    """Dieselbe Ursache, an der Stelle, an der sie zuerst auffiel.

    Session.start() setzt die Groesse mit `hyprctl keyword monitor`.
    Diese Messung laesst es zu und erwartet den Fehlschlag - faellt sie
    eines Tages, dann kann Hyprland es, und der erste Schritt des Umbaus
    ist wieder offen.
    """
    fehlt = _fehlt()
    if fehlt:
        pytest.skip(f"fuer den verschachtelten Compositor fehlt: "
                    f"{', '.join(fehlt)}")
    sitzung = Session(1280, 800, lua=MINIMAL_LUA)
    try:
        with pytest.raises(AssertionError, match="der Schirm ist"):
            sitzung.start()
    finally:
        sitzung.stop()


def test_keyword_setzt_unter_lua_keinen_wert(aus_lua):
    """Gemessen statt gefolgert.

    Die Vorrichtung setzt border_size in der Lua-Datei auf 3, ruft dann
    `hyprctl keyword general:border_size 9` und liest nach. Kaeme 9
    heraus, waere der Umzug eine reine Schreibarbeit.
    """
    assert aus_lua["border_size"] == 3, (
        "schon die Lua-Datei ist nicht angekommen - dann sagt die "
        "Messung darunter nichts")
    assert aus_lua["border_nach_keyword"] != 9, (
        "`hyprctl keyword` hat unter Lua doch gesetzt (border_size = "
        f"{aus_lua['border_nach_keyword']}) - dann ist der Befund "
        "ueberholt und src/displays.py kann bleiben, wie es ist")


# ---------------------------------------------------------------------
# WAS LUA STATT keyword ANBIETET - und was nicht
# ---------------------------------------------------------------------

TARBALL = (Path(__file__).resolve().parents[2] / "packaging"
           / "zepos-hyprland" / "hyprland-0.56.1.tar.gz")

# Die Namen, die src/displays.py braucht, um eine Anordnung anzuwenden:
# Modus (Aufloesung samt Bildwiederholrate), Lage und Massstab.
GEBRAUCHT = ("set_mode", "set_position", "set_scale")


def _lua_monitor_quelle() -> str:
    import tarfile
    with tarfile.open(TARBALL) as archiv:
        for eintrag in archiv:
            if eintrag.name.endswith("config/lua/objects/LuaMonitor.cpp"):
                inhalt = archiv.extractfile(eintrag)
                if inhalt is None:
                    break
                return inhalt.read().decode("utf-8", errors="replace")
    return ""


def test_der_lua_monitor_kann_eine_anordnung_nicht_anwenden():
    """DER ZWEITE HALBE BEFUND, und er entscheidet ueber den Zuschnitt.

    `hyprctl keyword` wirkt unter Lua nicht (die Zusicherung darueber).
    Bliebe ein Weg ueber die Lua-Schnittstelle selbst - hl.get_monitor()
    gibt ein Objekt zurueck. GEMESSEN am 03.09.2026 im Quelltext, den
    ZepOS ausliefert: dieses Objekt kennt name, width, height, scale,
    transform, position ... alles LESEND, und als einzige Setzer
    set_workspace und set_special_workspace.

    Damit gibt es unter Lua in dieser Fassung KEINEN Weg, Aufloesung,
    Lage oder Massstab eines Ausgangs zur Laufzeit zu aendern. Fuer
    src/displays.py heisst das: die Seite "Bildschirme" muss auf
    "Datei schreiben und neu laden" umgebaut werden - genau der Weg von
    nwg-displays, den displays.py mit Begruendung NICHT geht (siehe
    seinen Kopf, Zeile 99). Dieser Umbau ist Teil des Umzugs und keine
    Nebensache.

    Diese Zusicherung faellt, sobald Hyprland die Setzer nachliefert -
    und das ist ihr Zweck: dann ist der teure Teil des Umzugs erledigt,
    bevor jemand ihn baut.
    """
    quelle = _lua_monitor_quelle()
    if not quelle:
        pytest.skip(f"{TARBALL.name} liegt nicht neben dem Rezept - ohne "
                    f"den Quelltext ist diese Frage nicht zu beantworten")
    gefunden = [name for name in GEBRAUCHT if f'"{name}"' in quelle]
    assert gefunden == [], (
        f"LuaMonitor kennt jetzt {gefunden} - damit gibt es einen Weg, "
        f"eine Bildschirmanordnung unter Lua zur Laufzeit anzuwenden, und "
        f"der Umbau von src/displays.py ist billiger als hier beschrieben")
    assert '"set_workspace"' in quelle, (
        "auch set_workspace ist fort - dann hat sich die Schnittstelle "
        "grundlegend geaendert und dieser Text ist zu erneuern")
