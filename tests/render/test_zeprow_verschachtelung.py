# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Schalter IM Knopf - am abgebildeten Fenster, mit echten Tasten.

WAS HIER GEKLAERT WIRD, UND WARUM ES VOR DEM UMBAU KOMMT
    Im Bericht zu Aufgabe 76 steht ein Befund, den ich selbst
    aufgeschrieben und NICHT gemessen habe:

        "zepRow haengt sein `ende` - also den Gtk.Switch - INNERHALB der
         Zeile ein und wickelt die Zeile dann in einen Gtk.Button. In
         GTK4 ist ein Button kein Behaelter fuer bedienbare Kinder; die
         beiden Klickgesten liegen ineinander. Es funktioniert heute,
         weil die innere Geste die Sequenz beansprucht - verlassen wuerde
         ich mich darauf nicht."

    Der geplante Aufbau soll darauf bauen: "ein Klick auf den Schalter
    schaltet, ein Klick auf den Rest oeffnet". Ein Fundament, dessen
    Beschreibung mit "verlassen wuerde ich mich darauf nicht" endet, ist
    keines.

    Die ZAEHLUNG, wie oft es diese Verschachtelung ueberhaupt gibt,
    steht in tests/src/test_zeprow_zaehlung.py (Antwort: genau
    einmal, und nicht - wie der Bericht vermutete - auch bei Bluetooth,
    Netz und der Seitenleiste). Hier steht, was daraus WIRD.

WARUM UNTER EINEM COMPOSITOR UND NICHT UNTER gtk4-broadwayd
    Der erste Anlauf stand unter broadwayd und hat gemessen - nur nichts
    Brauchbares. GEMESSEN am 01.09.2026:

        zuteilung:     700x729   (die Seite als Ganzes)
        lage-liste:    700x110   bounds=0,39,700,110
        lage-schalter:   0x0     bounds=-1,38,2,2
        lage-titel:      0x0     bounds=0,39,0,0

    Die Liste hatte ihre Zuteilung, ihre KINDER hatten keine: die Seite
    zeichnet ihre Liste neu, sobald die Antwort auf `vpn.py --status` da
    ist, und die zweite Zuteilungsrunde braucht einen Bildrahmen. Ein
    broadwayd ohne angeschlossenen Betrachter liefert keinen. `pick()`
    traf damit fuer BEIDE Punkte dieselbe Titelleiste, weil beide Punkte
    derselbe Punkt (0,39) waren.

    Unter einem echten Compositor fliessen die Rahmen - und dort laesst
    sich ausserdem eine TASTE druecken (wtype) statt eine Funktion zu
    rufen, die dieselbe vfunc anspringt.

WAS GEMESSEN WIRD
    1. der Aufbau: steckt der Schalter wirklich in der klickbaren Huelle?
    2. wohin ein Zeigerdruck geht - `Gtk.Widget.pick()`, die Funktion,
       mit der GTK4 das selbst entscheidet;
    3. was eine ECHTE Leertaste tut - einmal mit dem Fokus auf dem
       Schalter, einmal mit dem Fokus auf der Zeile, jedes Mal mit einem
       Fahrtenbuch, das jedes `clicked` und jedes `notify::active` mit
       Zeitstempel und Fokus mitschreibt.

WAS SICH NICHT MESSEN LIESS, UND DAS GEHOERT HIERHER
    Ob die Geste des Schalters die Sequenz BEANSPRUCHT und den Knopf
    darum herum stillstellt. Dafuer braeuchte es ein echtes
    ZEIGERereignis, und auf dieser Maschine gibt es keines zu erzeugen:

      * Gdk.ButtonEvent hat in GTK4 keinen Konstruktor - nachgesehen am
        01.09.2026 in /usr/share/gir-1.0/Gdk-4.0.gir: die Klasse traegt
        eine Methode und keinen `constructor`.
      * Hyprland hat keinen Klick-Dispatcher - `hyprctl dispatch` am
        selben Tag durchgesehen: movecursor ja, sendshortcut ja
        (Tastatur), Zeigerdruck nein.
      * ydotool, wlrctl und dotool sind nicht installiert.

    Was bleibt, ist die Haelfte, die sich messen laesst - und fuer den
    Entwurf ist es die entscheidende: WELCHES Widget das Ereignis
    bekommt und welche Kette darueber liegt.

SICHERHEIT
    Verschachtelter Compositor mit eigenem XDG_RUNTIME_DIR und eigenem
    Sitzungsbus. Das Buendel entsteht ueber den Aufbau von
    tests/src/test_vpn_schalter.py, und der schiebt ein vpn.py unter,
    das "disconnected" druckt - das echte vpn.py laeuft nicht, also
    fragt niemand NetworkManager oder strongSwan etwas. `wtype` spricht
    NUR den verschachtelten Compositor an (eigenes WAYLAND_DISPLAY,
    eigenes XDG_RUNTIME_DIR); die Sitzung des Nutzers bekommt keine
    Taste.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.render import desktop_session as _sitzung               # noqa: E402
from tests.render.desktop_session import Session, required_tools   # noqa: E402
from tests.render.measure import bounds_of, changed_pixels, read_png  # noqa: E402

# Denselben Aufbau leihen wie test_vpn_ansicht.py - `_baue` ist dort
# schon fuer ein zweites Kind geoeffnet worden, samt Wegwerf-vpn.py.
_SPEC = importlib.util.spec_from_file_location(
    "_vpn_schalter_harness",
    ROOT / "tests" / "src" / "test_vpn_schalter.py")
_HARNESS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HARNESS)

pytestmark = pytest.mark.allow_subprocess

KIND = Path(__file__).resolve().parent / "zeprow_verschachtelung_child.tsx"

# Wann der Test die Leertaste drueckt, in Sekunden nach dem Start des
# Kindes. Mitten in dem Fenster, das der Fahrplan des Kindes dafuer offen
# laesst (T_FOKUS 4 s bis T_LESEN 6 s) - reichlich Luft nach beiden
# Seiten.
TASTE_S = 4.7
LAUFZEIT_S = 9.0

# Die zwei Bildabzuege um den Fokuswechsel herum. Das Kind nimmt den
# Fokus nach seiner Fokuskette wieder weg (bei T_MESSEN, 2,5 s); VOR_S
# liegt also im fokuslosen Fenster, NACH_S nach den Tabulatoren und vor
# der Leertaste.
VOR_S = 3.0
TAB_S = 3.4
NACH_S = 4.3

# WIEVIEL TABULATOREN BIS ZUM ZIEL - abgelesen an der Fokuskette, die
# dieselbe Datei misst (Marke `fokuskette`, gemessen am 01.09.2026):
#
#     GtkButton[zep-row-click] > GtkSwitch[zep-toggle]
#     > GtkButton[zep-row-click] > GtkSwitch[zep-toggle] > ...
#
# Vom fokuslosen Fenster aus fuehrt ein Tabulator auf die Huelle der
# ersten Zeile und ein zweiter auf ihren Schalter.
#
# MIT ECHTEN TASTEN UND NICHT MEHR MIT grab_focus() - die Begruendung
# steht im Kind bei T_FOKUS und ist eine Messung: GTK4 setzt
# `:focus-visible` nur fuer einen Fokus, der ueber die TASTATUR
# gekommen ist. Mit grab_focus() blieb das Bild darum in JEDEM Fall
# unveraendert, auch bei tadellosem Stil - eine Messung, die fuer jede
# Lage dieselbe Antwort gibt, misst nichts.
ZIELTABS = {"zeile": 1, "schalter": 2}

# ZWEI LAEUFE, EINER JE ZIEL - und das ist eine Messung und keine
# Bequemlichkeit. Der erste Anlauf am 01.09.2026 wollte beide in einem
# Lauf messen; der zweite Teil hat nichts gemessen, weil die Taste auf
# dem Schalter die ZEILE ausgeloest, auf die Einzelheiten umgeblattert
# und die Liste damit abgeraeumt hatte. Die Begruendung steht im Kind.
ZIELE = ("schalter", "zeile")


def _spur_lesen(text: str) -> dict[str, str]:
    """Die Spur des Kindes als Abbildung. Die LETZTE Marke gewinnt."""
    gefunden: dict[str, str] = {}
    for zeile in text.splitlines():
        name, trenner, wert = zeile.partition(":")
        if trenner:
            gefunden[name] = wert
    return gefunden


def _stylesheet(wurzel: Path) -> Path:
    """Das ECHTE Stylesheet dieses Projekts, uebersetzt nach CSS.

    WARUM DIESE FUNKTION AM 01.09.2026 NOETIG WURDE, UND SIE IST EINE
    BERICHTIGUNG
        Der Aufbau, den diese Datei sich von tests/src/test_vpn_schalter.py
        leiht, erzeugt DREI Vorlagen: i18n.ts, kit.ts, VpnManager.tsx. Ein
        Stylesheet ist nicht dabei, und das Kind ruft `Gtk.init()` statt
        AGS' `App` - es laedt also gar keines.

        Der erste Bildvergleich hier hat das nicht gewusst und trotzdem
        gemessen: 4928 Punkte, ein 2px-Rahmen in (128,165,211). Das sah
        aus wie ein Befund ueber die Regeln dieses Projekts und war einer
        ueber GTKs Vorgabe - denn keine einzige Regel des Projekts war
        geladen. Dieselbe Sorte Fehler wie die blinde Zusicherung weiter
        unten: die Messung lief, nur ueber etwas anderes als gedacht.

        $accent ist #33C9EE, ein helles Cyan; (128,165,211) ist Adwaitas
        Blau. Die zwei Farben auseinanderzuhalten ist der ganze Zweck.

    Uebersetzt wird mit `sass`, weil das Stylesheet SCSS ist (Variablen,
    Verschachtelung) und Gtk.CssProvider nur CSS liest. AGS tut im
    Normalbetrieb dasselbe.
    """
    stil = wurzel / "stil"
    scss = stil / "style.scss"
    scss.parent.mkdir(parents=True, exist_ok=True)
    _prozessor = _sitzung._processor(None, stil)
    _prozessor.apply_template(_sitzung.SRC / "templates/ags-style.template", scss)

    css = stil / "style.css"
    ergebnis = subprocess.run(["sass", "--no-source-map", str(scss), str(css)],
                              capture_output=True, text=True, timeout=120)
    assert ergebnis.returncode == 0, (
        "`sass` hat das Stylesheet nicht uebersetzt:\n"
        + ergebnis.stdout + ergebnis.stderr)
    text = css.read_text(encoding="utf-8")
    # Die Gegenprobe zur Gegenprobe: steht die Regel, um die es geht,
    # ueberhaupt im uebersetzten Blatt? Ohne sie maesse der Vergleich
    # wieder GTKs Vorgabe, nur diesmal mit geladenem Stylesheet.
    assert ".zep-row-click-getrennt" in text, (
        "die uebersetzte CSS-Datei kennt `.zep-row-click-getrennt` nicht "
        "- dann ist die Regel aus ags-style.template verschwunden, und "
        "der Bildvergleich unten pruefte wieder nichts")
    return css


def _lauf(wurzel: Path, buendel: Path, ziel: str, css: Path) -> dict:
    """Ein Lauf: Fenster auf, Fokus auf `ziel`, eine echte Leertaste."""
    spur = wurzel / f"spur-{ziel}"
    protokoll = wurzel / f"kind-{ziel}.log"
    tasten: list[str] = []

    with Session(1280, 900) as sitzung:
        sitzung.start_bus()
        sitzung.hyprctl("keyword", "cursor:invisible", "true")
        sitzung.move_cursor(640, 450)
        kind = sitzung.spawn(
            [str(buendel)], log=protokoll,
            ZEPOS_USER_ROOT=str(wurzel / "zepos"),
            ZEPOS_TRACE=str(spur),
            ZEPOS_ZIEL=ziel,
            # Das uebersetzte Stylesheet - siehe _stylesheet() oben.
            ZEPOS_CSS=str(css),
            # Damit `_` die englischen msgid liefert und die Erwartungen
            # nicht an der Sprache dieser Maschine haengen.
            LANG="C", LC_ALL="C")

        umgebung = sitzung.environment()
        beginn = time.monotonic()

        # ZWEI ABZUEGE UM DEN FOKUSWECHSEL HERUM - was der Nutzer SIEHT,
        # wenn er die Zeile mit dem Tabulator erreicht.
        #
        #     Die Marken oben sagen, WO der Fokus liegt. Ob man das auch
        #     ansieht, sagen sie nicht - und genau daran haengt der
        #     Umbau vom 01.09.2026: die zwei Regeln, die den Fokusrahmen
        #     malen, lauten in ags-style.template
        #     `.zep-row-click:focus-visible > .zep-row` und
        #     `.zep-row-click:active > .zep-row`. Der Nachfahrenpfeil
        #     verlangt, dass `.zep-row` das UNMITTELBARE Kind der Huelle
        #     ist - in der getrennten Betriebsart ist es genau
        #     andersherum. Ob dabei ein Rahmen verlorengeht, ist eine
        #     Frage an das BILD und nicht an den Baum.
        #
        #     VOR_S liegt nach der Fokuskette des Kindes (das dort den
        #     Fokus wieder wegnimmt) und vor den Tabulatoren, NACH_S
        #     hinter ihnen und vor der Leertaste.
        rest = VOR_S - (time.monotonic() - beginn)
        if rest > 0:
            time.sleep(rest)
        bild_vor = sitzung.shoot(wurzel / f"fokus-vor-{ziel}.png")

        rest = TAB_S - (time.monotonic() - beginn)
        if rest > 0:
            time.sleep(rest)
        for _nummer in range(ZIELTABS[ziel]):
            tab = subprocess.run(["wtype", "-k", "Tab"], env=umgebung,
                                 capture_output=True, text=True, timeout=30)
            tasten.append(f"{round(time.monotonic() - beginn, 1)}s Tab "
                          f"rc={tab.returncode} {tab.stderr.strip()}")
            time.sleep(0.15)

        rest = NACH_S - (time.monotonic() - beginn)
        if rest > 0:
            time.sleep(rest)
        bild_nach = sitzung.shoot(wurzel / f"fokus-nach-{ziel}.png")

        rest = TASTE_S - (time.monotonic() - beginn)
        if rest > 0:
            time.sleep(rest)
        # `-k space`: eine echte Taste ueber das
        # virtual-keyboard-Protokoll AN DEN VERSCHACHTELTEN COMPOSITOR.
        # Die Umgebung kommt aus der Sitzung, also zeigt WAYLAND_DISPLAY
        # auf sie und nicht auf die des Nutzers.
        ergebnis = subprocess.run(["wtype", "-k", "space"],
                                  env=umgebung, capture_output=True,
                                  text=True, timeout=30)
        tasten.append(f"{round(time.monotonic() - beginn, 1)}s "
                      f"rc={ergebnis.returncode} {ergebnis.stderr.strip()}")

        rest = LAUFZEIT_S - (time.monotonic() - beginn)
        if rest > 0:
            time.sleep(rest)
        text = spur.read_text(encoding="utf-8") if spur.exists() else ""
        log = protokoll.read_text(encoding="utf-8", errors="replace") \
            if protokoll.exists() else ""
        kind.poll()

    return {"spur": _spur_lesen(text), "roh": text, "log": log,
            "tasten": tasten, "ziel": ziel,
            "bild_vor": bild_vor, "bild_nach": bild_nach}


@pytest.fixture(scope="module")
def laeufe(tmp_path_factory) -> dict[str, dict]:
    """Beide Laeufe, einer je Ziel - ein Buendel fuer beide.

    Modulweit: `ags bundle` kostet mehrere Sekunden, und jede
    Zusicherung darunter liest dieselben zwei Messungen.
    """
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Lauf fehlt: {', '.join(fehlt)}")
    if shutil.which("wtype") is None:
        pytest.skip("wtype fehlt - ohne echte Taste misst dieser Lauf nur "
                    "die Haelfte, und die halbe Messung ist genau die, "
                    "gegen die diese Datei gebaut ist")

    if shutil.which("sass") is None:
        pytest.skip("sass fehlt - ohne uebersetztes Stylesheet maesse der "
                    "Bildvergleich unten GTKs Vorgaben statt der Regeln "
                    "dieses Projekts")

    wurzel = tmp_path_factory.mktemp("zeprow-nest")
    buendel, _system = _HARNESS._baue(wurzel, kind=KIND)
    _HARNESS._einstellungen(wurzel / "zepos")
    return {ziel: _lauf(wurzel, buendel, ziel, _stylesheet(wurzel))
            for ziel in ZIELE}


@pytest.fixture(scope="module")
def messung(laeufe) -> dict:
    """Der Lauf mit dem Fokus auf dem SCHALTER.

    Er traegt auch alles, was gar nicht am Ziel haengt - Aufbau,
    Zuteilung, pick(), Fokuskette. Das Kind misst beides in jedem Lauf;
    hier wird einer davon gelesen, statt dieselbe Zahl zweimal zu
    pruefen.
    """
    return laeufe["schalter"]


def _bericht(messung: dict) -> str:
    return (f"Ziel: {messung['ziel']}"
            + "\nTasten: " + "; ".join(messung["tasten"])
            + "\nSpur:\n" + messung["roh"]
            + "\nProtokoll:\n" + messung["log"][-2000:])


# ----------------------------------------------------------------------
# Die Gegenprobe
# ----------------------------------------------------------------------

def test_die_seite_steht_und_ist_zugeteilt(messung):
    """Ohne Zuteilung ist jede Koordinate darunter eine Zahl ueber nichts.

    Genau das war der erste Anlauf unter broadwayd (siehe Dateikopf), und
    er sah wie eine Messung aus.
    """
    spur = messung["spur"]
    assert spur.get("schalter", "").startswith("GtkSwitch"), _bericht(messung)
    for name in ("lage-schalter", "lage-titel"):
        lage = spur.get(name, "")
        breite = lage.split("x")[0] if "x" in lage else "0"
        assert breite.isdigit() and int(breite) > 0, (
            f"{name} ist {lage!r} - ohne Zuteilung misst alles darunter "
            f"nichts:\n{_bericht(messung)}")


def test_in_beiden_laeufen_sind_wirklich_tasten_gedrueckt_worden(laeufe):
    """JEDER wtype-Aufruf muss ohne Fehler zurueckgekommen sein.

    Sonst waere "keine Reaktion" von "keine Taste" nicht zu
    unterscheiden - und die Zusicherungen unten waeren gruen, ohne dass
    jemand etwas gedrueckt haette.

    Gezaehlt werden die Tabulatoren bis zum Ziel PLUS die eine
    Leertaste. Die Zahl steht in ZIELTABS und ist an der gemessenen
    Fokuskette abgelesen, nicht geraten.
    """
    for ziel, lauf in laeufe.items():
        # Ohne Stylesheet redet der Bildvergleich unten ueber GTKs
        # Vorgaben statt ueber dieses Projekt - siehe _stylesheet().
        assert lauf["spur"].get("stylesheet") == "geladen", _bericht(lauf)
        assert len(lauf["tasten"]) == ZIELTABS[ziel] + 1, _bericht(lauf)
        for eintrag in lauf["tasten"]:
            assert "rc=0" in eintrag, _bericht(lauf)
        assert lauf["spur"].get("ziel") == ziel, _bericht(lauf)


def test_die_tabulatoren_landen_wirklich_auf_dem_ziel(laeufe):
    """Die Gegenprobe zur Tabulatorzaehlung.

    ZIELTABS ist eine Zahl aus einer frueheren Messung. Stimmt sie
    nicht mehr - weil eine Zeile dazugekommen ist oder die Reihenfolge
    sich gedreht hat -, dann landet der Fokus woanders, und alles
    darunter maesse etwas anderes als das, was draufsteht.
    """
    assert laeufe["zeile"]["spur"].get("fokus-auf-ziel", "").find(
        "zep-row-click") >= 0, _bericht(laeufe["zeile"])
    assert laeufe["schalter"]["spur"].get(
        "fokus-auf-ziel", "").startswith("GtkSwitch"), _bericht(
            laeufe["schalter"])


# ----------------------------------------------------------------------
# Der Aufbau
# ----------------------------------------------------------------------

def test_der_schalter_steckt_NICHT_MEHR_in_der_klickbaren_huelle(messung):
    """Der Umbau vom 01.09.2026, in einer Zeile.

    Bis dahin steckte der Schalter IN der Huelle - gemessen, und der
    Grund fuer alles darunter. Seit `endeBedienbar` (ags-kit.template)
    ist er ihr GESCHWISTER: die Zeile bleibt der gezeichnete Kasten, die
    Huelle traegt Symbol, Text und Luecke, der Schalter steht daneben.
    """
    spur = messung["spur"]
    assert spur.get("schalter-im-knopf") == "nein", (
        "der Schalter liegt wieder unter der klickbaren Huelle - dann ist "
        "`endeBedienbar` verlorengegangen, und die Leertaste auf dem "
        f"Schalter oeffnet wieder die Einzelheiten:\n{_bericht(messung)}")
    assert spur.get("titel-im-knopf") == "ja", (
        "die Beschriftung liegt NICHT unter der Huelle - dann ist die "
        f"Zeile nicht mehr als Ganzes klickbar:\n{_bericht(messung)}")
    assert spur.get("knopf-klasse") == "zep-row-click", _bericht(messung)


def test_die_vorgabe_von_zeprow_ist_unveraendert(messung):
    """Die neue Betriebsart darf nicht zur Vorgabe geworden sein.

    Das ist die Sorte Fehler, die eine ZAEHLUNG nicht faengt: sie zaehlt
    Aufrufer, nicht Baeume. Eine neue Betriebsart, die versehentlich zur
    Vorgabe wird, laesst jede Zaehlung unveraendert. Hier werden darum
    Zeilen GEBAUT und ihre Baeume nachgesehen.

    ALLE DREI FORMEN, die im Baum ueberhaupt vorkommen - welche das
    sind, zaehlt tests/src/test_zeprow_zaehlung.py:

        `aktion` + `ende`   die Anzeigeseite, zweimal   -> Huelle aussen
        `aktion`            Bluetooth, Netz, die Seitenleiste, das
                            Kontrollzentrum, Dock, Home -> Huelle aussen
        `ende`              das Einstellungsfenster, fuenfmal
                                                       -> gar kein Knopf

    Damit ist jede der sechs Seiten abgedeckt, die sich nicht aendern
    duerfen.
    """
    spur = messung["spur"]
    assert spur.get("vorgabe-wurzel", "").startswith("GtkButton"), (
        "eine Zeile OHNE `endeBedienbar` liefert keine Huelle mehr als "
        f"Wurzel - die Vorgabe hat sich geaendert:\n{_bericht(messung)}")
    assert spur.get("vorgabe-schalter-im-knopf") == "ja", (
        "in der Vorgabe liegt das `ende` nicht mehr unter der Huelle - "
        "die neue Betriebsart ist versehentlich zur Vorgabe geworden:\n"
        + _bericht(messung))
    assert spur.get("nur-aktion-wurzel", "").startswith("GtkButton"), (
        "eine Zeile mit `aktion` und ohne `ende` liefert keine Huelle "
        "mehr als Wurzel - das ist die Form von Bluetooth, Netz und der "
        f"Seitenleiste:\n{_bericht(messung)}")

    # Die dritte Form, und mit ihr ist jede der sechs Seiten aus dem
    # Auftrag abgedeckt: `ende` OHNE `aktion` ist das
    # Einstellungsfenster, fuenfmal. Diese Zeile ist gar kein Knopf.
    assert spur.get("nur-ende-wurzel", "").startswith("GtkBox"), (
        "eine Zeile mit `ende` und ohne `aktion` liefert keinen blossen "
        "Kasten mehr - das ist die Form des Einstellungsfensters, und "
        f"sie war noch nie ein Knopf:\n{_bericht(messung)}")
    assert spur.get("nur-ende-hat-huelle") == "nein", (
        "eine Zeile ohne `aktion` hat jetzt eine klickbare Huelle - dann "
        "ist im Einstellungsfenster jede Zeile anklickbar geworden, ohne "
        f"dass jemand ein `aktion` gesetzt haette:\n{_bericht(messung)}")
    assert spur.get("nur-ende-schalter-drin") == "ja", (
        "das `ende` ist aus einer Zeile ohne `aktion` verschwunden:\n"
        + _bericht(messung))


# ----------------------------------------------------------------------
# Wohin ein Zeigerdruck geht
# ----------------------------------------------------------------------

def test_ein_druck_auf_den_schalter_erreicht_den_schalter(messung):
    """Die eine Haelfte von "ein Klick auf den Schalter schaltet"."""
    spur = messung["spur"]
    assert "GtkSwitch" in spur.get("pick-schalter-kette", ""), (
        "ein Druck in der Mitte des Schalters trifft "
        f"{spur.get('pick-schalter')!r}, und in seiner Kette steht kein "
        f"GtkSwitch:\n{_bericht(messung)}")


def test_ein_druck_auf_die_beschriftung_erreicht_den_schalter_nicht(messung):
    """Und die andere: "ein Klick auf den Rest oeffnet".

    Ohne sie waere "der Schalter wird getroffen" die Aussage, dass der
    Schalter ALLES bekommt.
    """
    spur = messung["spur"]
    assert "GtkSwitch" not in spur.get("pick-titel-kette", ""), _bericht(messung)
    assert spur.get("pick-titel-unter-knopf") == "ja", (
        "ein Druck auf die Beschriftung liegt nicht unter der klickbaren "
        f"Huelle - dann oeffnet die Zeile gar nicht:\n{_bericht(messung)}")


def test_ein_druck_auf_den_schalter_geht_an_der_huelle_vorbei(messung):
    """UND DAMIT IST DIE FRAGE DER SEQUENZBEANSPRUCHUNG WEG.

    Vor dem Umbau lag die Huelle in der Ereigniskette UEBER dem
    Schalter. Ob ein Zeigerdruck dort trotzdem nur den Schalter erreicht,
    haette davon abgehangen, dass dessen Geste die Sequenz beansprucht -
    eine Zusage von GTK, die diese Datei nicht messen kann (siehe
    Dateikopf: kein Gdk.ButtonEvent-Konstruktor, kein Klick-Dispatcher in
    Hyprland, kein ydotool).

    Seit `endeBedienbar` steht die Frage nicht mehr: der Schalter liegt
    gar nicht mehr unter der Huelle. Was vorher eine Folgerung war, ist
    jetzt eine Eigenschaft des Baums - und die ist gemessen.
    """
    spur = messung["spur"]
    assert spur.get("pick-schalter-unter-knopf") == "nein", (
        "ein Druck auf den Schalter landet wieder unter der klickbaren "
        "Huelle - dann haengt die Trennung wieder an einer Zusage von "
        f"GTK statt am Aufbau:\n{_bericht(messung)}")


# ----------------------------------------------------------------------
# Die Tastatur, mit echten Tasten
# ----------------------------------------------------------------------

def test_der_schalter_ist_mit_dem_tabulator_erreichbar(messung):
    """UND DAS WAR EINE UEBERRASCHUNG.

    Der Bericht zu Aufgabe 76 hat vermutet, ein Gtk.Button gebe den
    Fokus nicht an seine Kinder weiter, der Schalter sei also
    tastaturlos. GEMESSEN am 01.09.2026 ist die Fokuskette:

        GtkButton[zep-row-click] > GtkSwitch[zep-toggle]
        > GtkButton[zep-row-click] > GtkSwitch[zep-toggle] > ...

    Der Tabulator erreicht beide, Zeile fuer Zeile abwechselnd. Die
    Vermutung war falsch, und sie stand ungeprueft in einem Bericht -
    genau deshalb steht sie jetzt hier als Zahl.
    """
    spur = messung["spur"]
    assert spur.get("schalter-per-tab-erreichbar") == "ja", (
        "der Schalter ist NICHT mehr mit dem Tabulator erreichbar - wer "
        "die Maus nicht benutzen kann, kann diese Verbindung dann nicht "
        f"mehr schalten:\n{_bericht(messung)}")
    assert spur.get("knopf-per-tab-erreichbar") == "ja", _bericht(messung)


def test_die_leertaste_auf_dem_schalter_schaltet_und_oeffnet_nicht(laeufe):
    """DIE ZUSICHERUNG, DIE DEN UMBAU TRAEGT.

    Eine ECHTE Leertaste, mit dem Fokus nachweislich auf dem Schalter.

    WIE ES VORHER WAR - GEMESSEN am 01.09.2026, VOR dem Umbau, mit genau
    diesem Kind:

        3500ms --fokus-gesetzt-- fokus=GtkSwitch[zep-toggle]
        4513ms KNOPF-clicked     fokus=GtkSwitch[zep-toggle]

    Der Fokus lag auf dem SCHALTER, gefeuert hat die ZEILE, und
    `notify::active` kam kein einziges Mal. Wer die Maus nicht benutzen
    konnte, konnte eine VPN-Verbindung nicht ein- und ausschalten - die
    Zeile ist der einzige Ort, an dem der Schalter steht.

    Seit `endeBedienbar` (ags-kit.template) liegt der Schalter nicht mehr
    unter der Huelle, und die Taste erreicht ihn. Das ist die Haelfte von
    "ein Klick auf den Schalter schaltet, ein Klick auf den Rest
    oeffnet"; die andere steht darunter.
    """
    lauf = laeufe["schalter"]
    spur = lauf["spur"]
    assert spur.get("fokus-auf-ziel", "").startswith("GtkSwitch"), (
        f"der Fokus lag gar nicht auf dem Schalter:\n{_bericht(lauf)}")
    buch = spur.get("nach-der-taste", "")
    assert "SCHALTER-notify" in buch, (
        "die Leertaste auf dem Schalter schaltet ihn NICHT. Steht im "
        "Fahrtenbuch stattdessen KNOPF-clicked, dann liegt der Schalter "
        "wieder unter der klickbaren Huelle und `endeBedienbar` ist "
        f"verlorengegangen.\nFahrtenbuch: {buch}\n{_bericht(lauf)}")
    assert "KNOPF-clicked" not in buch, (
        "die Leertaste auf dem Schalter loest AUCH die Zeile aus - dann "
        "blaettert Schalten in die Einzelheiten, und die Trennung haelt "
        f"nicht.\nFahrtenbuch: {buch}\n{_bericht(lauf)}")


def test_die_leertaste_auf_der_zeile_oeffnet_und_schaltet_nicht(laeufe):
    """Die Gegenprobe, in einem EIGENEN Lauf.

    Ohne sie waere "die Taste loest die Zeile aus" die Aussage, dass die
    Taste immer nur die Zeile erreicht - und der Befund darueber waere
    keiner.

    Ein eigener Lauf, weil die Taste im ersten die Ansicht gewechselt
    und die Liste damit abgeraeumt hat (Begruendung im Kind bei ZIEL).
    """
    lauf = laeufe["zeile"]
    spur = lauf["spur"]
    assert spur.get("fokus-auf-ziel", "").find("zep-row-click") >= 0, (
        f"der Fokus lag gar nicht auf der Zeile:\n{_bericht(lauf)}")
    buch = spur.get("nach-der-taste", "")
    assert "KNOPF-clicked" in buch, (
        "die Leertaste auf der Zeile hat sie nicht ausgeloest:\n"
        f"{buch}\n{_bericht(lauf)}")
    assert "SCHALTER-notify" not in buch, (
        "die Leertaste auf der Zeile hat AUCH den Schalter umgelegt:\n"
        f"{buch}\n{_bericht(lauf)}")


# ----------------------------------------------------------------------
# Was man SIEHT, wenn der Tabulator die Zeile erreicht
# ----------------------------------------------------------------------

def test_die_fokussierte_zeile_ist_auch_zu_sehen(laeufe):
    """DER RAHMEN, DEN DER UMBAU FAST GEKOSTET HAETTE.

    Dass der Fokus auf der Zeile LIEGT, sagen die Marken oben. Ob man
    das ANSIEHT, sagen sie nicht - und ohne sichtbaren Rahmen ist eine
    erreichbare Zeile fuer den, der die Maus nicht benutzt, trotzdem
    verloren: er weiss dann nicht, wo er steht.

    WORAN ES HING - der Grund, warum diese Zusicherung ueberhaupt
    entstanden ist (01.09.2026)
        Den Rahmen malen zwei Regeln in ags-style.template:

            .zep-row-click:focus-visible > .zep-row
            .zep-row-click:active        > .zep-row

        Der Nachfahrenpfeil verlangt, dass `.zep-row` das UNMITTELBARE
        Kind der Huelle ist. Genau das dreht die getrennte Betriebsart
        um: dort ist die Huelle das Kind von `.zep-row`. Die zwei Regeln
        haetten damit nichts mehr getroffen, und der Umbau, der die
        Zeile fuer die Tastatur oeffnet, haette ihr im selben Zug die
        Rueckmeldung genommen.

        Der Baum sagt das nicht - er sagt nur, wer wessen Kind ist. Ob
        ein Rahmen erscheint, ist eine Frage an das BILD. Darum steht
        hier ein Bildvergleich und keine Ueberlegung ueber Selektoren.

    GEMESSEN wird der Unterschied zwischen zwei Abzuegen desselben
    Fensters: einer ohne Fokus (das Kind nimmt ihn nach seiner
    Fokuskette wieder weg), einer mit dem Fokus auf der Zeile. Aendert
    sich kein Punkt, malt nichts.
    """
    lauf = laeufe["zeile"]
    vor = read_png(lauf["bild_vor"])
    nach = read_png(lauf["bild_nach"])
    # Die ganze Flaeche: in diesem Lauf steht nur das Kind auf dem
    # Schirm - keine Leiste, keine Uhr, kein Dock, also auch nichts, was
    # sich von selbst aendert. Der Zeiger ist unsichtbar und steht still.
    punkte = changed_pixels(vor, nach, (0, 0, vor.width, vor.height))
    rechteck = bounds_of(punkte)
    print(f"\nFokusrahmen auf der Zeile: {len(punkte)} Punkte, "
          f"Rechteck {rechteck}")
    assert punkte, (
        "der Fokus liegt auf der Zeile, und das Bild aendert sich um "
        "KEINEN einzigen Punkt - es gibt keinen sichtbaren Fokusrahmen. "
        "Wer die Maus nicht benutzt, sieht dann nicht, wo er steht. "
        "Zu pruefen sind die zwei Regeln zu `.zep-row-click` in "
        "ags-style.template: ihr `> .zep-row` trifft in der getrennten "
        f"Betriebsart nicht mehr.\n{_bericht(lauf)}")

    # UND ES MUSS DER RAHMEN DIESES PROJEKTS SEIN, NICHT IRGENDEINER.
    #
    #     GEMESSEN am 01.09.2026, bevor `.zep-row-click-getrennt`
    #     entstand: es AENDERTE sich etwas - ein 2px-Rechteck 1188x46 in
    #     (128,165,211), GTKs eigenem Blau, und im Inneren kein einziger
    #     Punkt. Die Zusicherung darueber allein war damit gruen, obwohl
    #     beide Regeln des Projekts ins Leere zeigten.
    #
    #     Zwei Dinge trennen den einen Rahmen vom anderen, und beide
    #     werden geprueft: die FUELLUNG (GTK bringt keine mit) und die
    #     FARBE des Rahmens ($accent, #33C9EE - deutlich gruener und
    #     heller als Adwaitas Blau).
    innen = [p for p in punkte
             if rechteck[0] + 4 < p[0] < rechteck[0] + rechteck[2] - 4
             and rechteck[1] + 4 < p[1] < rechteck[1] + rechteck[3] - 4]
    assert len(innen) > len(punkte) // 4, (
        f"nur {len(innen)} der {len(punkte)} geaenderten Punkte liegen "
        "INNERHALB des Rechtecks - die Zeile bekommt also einen blossen "
        "Rahmen und keine Fuellung. Genau so sah es aus, als "
        "`.zep-row-click-getrennt` fehlte und GTKs eigener Rahmen "
        f"einsprang.\n{_bericht(lauf)}")

    akzent = (0x33, 0xC9, 0xEE)
    treffer = [p for p in punkte
               if max(abs(a - b) for a, b in zip(nach.at(*p)[:3], akzent)) <= 24]
    print(f"Punkte in $accent-Naehe: {len(treffer)}")
    assert treffer, (
        "kein einziger geaenderter Punkt hat die Akzentfarbe dieses "
        f"Projekts ({akzent}). Der Rahmen kommt dann von GTK und nicht "
        f"aus ags-style.template.\n{_bericht(lauf)}")


def test_der_fokussierte_schalter_ist_auch_zu_sehen(laeufe):
    """Dieselbe Frage fuer den Schalter, und sie ist nicht dieselbe.

    Der Schalter bringt seinen Fokusrahmen von GTK mit; die Zeile haengt
    an einer Regel dieses Projekts. Faellt diese hier aus, waere der
    Befund ein anderer - dann laege es nicht am Stil, sondern daran, dass
    der Fokus gar nicht ankommt.
    """
    lauf = laeufe["schalter"]
    vor = read_png(lauf["bild_vor"])
    nach = read_png(lauf["bild_nach"])
    punkte = changed_pixels(vor, nach, (0, 0, vor.width, vor.height))
    print(f"\nFokusrahmen auf dem Schalter: {len(punkte)} Punkte, "
          f"Rechteck {bounds_of(punkte)}")
    assert punkte, (
        "der Fokus liegt auf dem Schalter, und das Bild aendert sich um "
        f"keinen Punkt:\n{_bericht(lauf)}")
