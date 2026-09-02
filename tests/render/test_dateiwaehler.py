# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Dateiwaehler aus einer Layer-Flaeche heraus - gemessen, nicht gelesen.

WAS GEMELDET WURDE (01.09.2026), WOERTLICH
    "bei klick auf 'datei auswaehlen' in dem dialog verbuggt alles, man
     kann nichts mehr sehen."

WARUM DAS NICHT AUS DEM QUELLTEXT ZU BEANTWORTEN IST
    Ob ein Fenster zu sehen ist, entscheidet der Compositor. Der
    Dateiwaehler von GTK4 ist ein GEWOEHNLICHES Fenster (ein
    xdg_toplevel); die Flaeche, aus der er geoeffnet wird, ist eine
    Layer-Flaeche auf der Ebene OVERLAY - und OVERLAY liegt ueber jedem
    gewoehnlichen Fenster. Diese Reihenfolge steht in keiner Zeile
    dieses Baums, sie steht im wlr-layer-shell-Protokoll.

    Der erste Anlauf am 01.09.2026, mit einer nachgebauten Flaeche und
    einem Bildschirmabzug bei 1920x1200:

        Flaeche  "probe-schale"        hyprctl layers    0,0  880x600
        Fenster  "PROBE-DATEIWAEHLER"  hyprctl clients  21,21 1878x1158

    Auf dem Abzug fehlten dem Waehler seine Seitenleiste, sein
    Abbrechen-Knopf und der Anfang seiner Liste; sein Titel las sich
    "ROBE-DATEIWAEHLER". Genau der Satz des Nutzers.

WAS DIESE DATEI MISST, UND WARUM DIE EBENE UND NICHT DIE BILDPUNKTE
    Die Ebene ist die URSACHE, die Verdeckung ist ihre Folge. `hyprctl
    -j layers` fuehrt die Flaechen je Schirm unter ihrer Ebene auf
    ("0" Hintergrund, "1" unten, "2" oben, "3" Ueberlagerung) - eine
    Zahl, die der Compositor selbst nennt und die kein Bildvergleich
    braucht.

    Ein Bildvergleich waere ausserdem der schwaechere Beleg: er haengt
    daran, WO der Compositor den Waehler hinlegt, und das ist eine
    Frage der Fensterregeln der Sitzung, nicht des Fehlers.

DIE GEGENPROBE GEHOERT DAZU
    `roh` ruft Gtk.FileDialog.open() genauso, wie es bis zum 01.09.2026
    in ags-vpn-settings.template stand, und verlangt, dass die Flaeche
    dabei auf Ebene 3 stehenbleibt. Ohne diesen Lauf waere "Ebene 1"
    eine Zahl, von der niemand weiss, ob sie etwas geaendert hat.

DIESE DATEI WAR GRUEN, WAEHREND DER FEHLER OFFEN WAR - NACHGETRAGEN am
01.09.2026, und es gehoert an den Anfang und nicht ans Ende
    Der Nutzer hat denselben Fehler noch einmal gemeldet ("immernoch
    sobald ich den datei icon klick ... kommt kien datei auswaehler
    sondern alle ags sachen werden blockiert"), und die vier
    Zusicherungen darunter standen dabei auf gruen.

    Sie messen, was sie behaupten - aber sie messen einen NACHBAU: ein
    handgebautes Astal.Window statt der Fabrik, einen Zeitgeber statt
    eines Knopfes, einen Waehler, der IMMER abgebrochen wird, und eine
    Sitzung OHNE xdg-desktop-portal. Alle vier Unterschiede haben je
    einen Teil des Fehlers versteckt.

    Diese Datei bleibt, weil ihre Gegenprobe (der rohe Aufruf) etwas
    zeigt, was sonst niemand zeigt. Gemessen wird der Weg des Nutzers
    seither in tests/render/test_dateiwaehler_echt.py - dort steht auch
    die Aufzaehlung der vier Unterschiede mit den Zahlen dazu.

WAS NICHT GEMESSEN WIRD, UND DAS SOLL DASTEHEN
    Die TASTATUR. waehleDatei() nimmt der Flaeche fuer die Dauer des
    Waehlers auch den Tastenmodus (ON_DEMAND -> NONE), damit sich ein
    Dateiname tippen laesst. Dieser Messstand klickt nie, also hat die
    Flaeche hier nie eine Tastatur zu halten - `hyprctl activewindow`
    meldete in beiden Laeufen `null`. Die Ebene ist geprueft, der
    Tastenmodus ist begruendet; die Begruendung steht bei waehleDatei()
    in ags-overlay-utils.template.

SICHERHEIT
    Verschachtelter Compositor mit eigenem XDG_RUNTIME_DIR und eigenem
    Sitzungsbus (tests/render/desktop_session.py). Es wird KEINE Datei
    gewaehlt, kein VPN angefasst und kein Prozess des Nutzers beruehrt;
    der Waehler wird aus dem Programm heraus wieder abgebrochen.
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.render.desktop_session import (             # noqa: E402
    Session, bundle, render_configuration, required_tools,
)

KIND = Path(__file__).resolve().parent / "dateiwaehler_child.ts"

# Derselbe Name wie im Kind. Zwei Schreibweisen waeren zwei Flaechen.
NAMENSRAUM = "waehler-probe"
FENSTERTITEL = "ZEPOS-WAEHLER-DIALOG"

# Die Ebenen, wie `hyprctl -j layers` sie zaehlt. Sie stehen hier
# benannt, damit ein Fehlschlag "3 statt 1" nicht als nackte Zahl
# dasteht.
EBENE_UNTEN = "1"
EBENE_UEBERLAGERUNG = "3"

# Wann das Kind den Waehler oeffnet und wann es ihn abbricht, in
# Millisekunden nach seinem Start. Der Test misst dazwischen und danach.
OEFFNEN_MS = 4000
ABBRUCH_MS = 9000

# Die modulweiten Vorrichtungen `roh` und `repariert` uebersetzen je ein
# Kind mit `ags bundle` und lassen es in einer verschachtelten Sitzung
# aufgehen. Der Dateiwaehler von GTK4 ist ein xdg_toplevel, die Flaeche
# darunter eine Layer-Flaeche auf OVERLAY: welches von beiden der Nutzer
# sieht, entscheidet allein der Compositor.
pytestmark = pytest.mark.allow_subprocess


def _ebene(sitzung: Session, namensraum: str) -> str | None:
    """Auf welcher Ebene die Flaeche gerade liegt - oder None.

    Nur der abgebildete Schirm: der verschachtelte Compositor hat zwei
    Ausgaenge, und der des Wirtsfensters traegt dieselben Namensraeume.
    Dieselbe Einschraenkung wie in Session.layers().
    """
    daten = sitzung.hyprctl_json("layers") or {}
    schirm = daten.get(sitzung.output) or {}
    for ebene, flaechen in (schirm.get("levels") or {}).items():
        for flaeche in flaechen:
            if flaeche.get("namespace") == namensraum:
                return ebene
    return None


def _waehlerfenster(sitzung: Session):
    """Das Fenster des Waehlers, an seinem Titel erkannt."""
    for kunde in sitzung.hyprctl_json("clients") or []:
        if kunde.get("title") == FENSTERTITEL:
            return kunde
    return None


def _lauf(bau: Path, modus: str) -> dict:
    """Eine Sitzung, ein Waehler, drei Messpunkte."""
    ags = render_configuration(bau)

    # Das Kind IN den erzeugten Baum, damit `./utils/overlay` genau die
    # Datei trifft, die auch das Einstellungsfenster benutzt. Ein
    # Nachbau von waehleDatei() im Testverzeichnis wuerde den Nachbau
    # messen.
    ziel = ags / "dateiwaehler-probe.ts"
    shutil.copyfile(KIND, ziel)
    bundle_pfad = bau / f"waehler-{modus}.js"
    import subprocess
    ergebnis = subprocess.run(
        ["ags", "bundle", str(ziel), str(bundle_pfad), "-r", str(ags), "-g", "4"],
        capture_output=True, text=True, timeout=600)
    assert ergebnis.returncode == 0, (
        "`ags bundle` hat das Kind nicht uebersetzt:\n"
        + ergebnis.stdout + ergebnis.stderr)

    protokoll = bau / f"waehler-{modus}.log"
    messung: dict = {"modus": modus}
    # 1920x1200 - der Schirm des Nutzers. Ein Waehler, der auf einem
    # anderen Mass gemessen wird, ist ein anderer Waehler.
    with Session(1920, 1200) as sitzung:
        sitzung.start_bus()
        sitzung.hyprctl("keyword", "cursor:invisible", "true")
        sitzung.wallpaper()
        sitzung.move_cursor(960, 600)
        kind = sitzung.spawn(
            [str(bundle_pfad)], log=protokoll,
            HYPRLAND_INSTANCE_SIGNATURE=sitzung.signature(),
            ZEPOS_WAEHLER_MODUS=modus,
            ZEPOS_WAEHLER_OEFFNEN=str(OEFFNEN_MS),
            ZEPOS_WAEHLER_ABBRUCH=str(ABBRUCH_MS))

        # Vor dem Waehler: die Flaeche steht, wo createOverlayWindow()
        # sie hinstellt.
        frist = time.monotonic() + 30.0
        while time.monotonic() < frist:
            if _ebene(sitzung, NAMENSRAUM):
                break
            time.sleep(0.3)
        messung["ebene_vorher"] = _ebene(sitzung, NAMENSRAUM)

        # Waehrend der Waehler offen ist. Auf das FENSTER gewartet und
        # nicht auf eine feste Zeit: wann GTK es anmeldet, entscheidet
        # GTK.
        frist = time.monotonic() + 30.0
        while time.monotonic() < frist:
            if _waehlerfenster(sitzung):
                break
            time.sleep(0.3)
        fenster = _waehlerfenster(sitzung)
        messung["fenster"] = None if not fenster else {
            "at": fenster.get("at"), "size": fenster.get("size"),
            "class": fenster.get("class"),
        }
        messung["ebene_waehrend"] = _ebene(sitzung, NAMENSRAUM)
        sitzung.shoot(bau / f"waehler-{modus}-offen.png")

        # Nach dem Abbruch.
        frist = time.monotonic() + 30.0
        while time.monotonic() < frist:
            if not _waehlerfenster(sitzung):
                break
            time.sleep(0.3)
        time.sleep(1.0)
        messung["ebene_nachher"] = _ebene(sitzung, NAMENSRAUM)
        messung["fenster_nachher"] = _waehlerfenster(sitzung)
        messung["lebt"] = kind.poll() is None
        messung["protokoll"] = sitzung.read_shell_log()
        if protokoll.exists():
            messung["protokoll"] = protokoll.read_text(
                encoding="utf-8", errors="replace")
        messung["bild"] = bau / f"waehler-{modus}-offen.png"
    return messung


@pytest.fixture(scope="module")
def repariert(tmp_path_factory) -> dict:
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Bildlauf fehlt: {', '.join(fehlt)}")
    return _lauf(tmp_path_factory.mktemp("zepwaehler-neu"), "repariert")


@pytest.fixture(scope="module")
def roh(tmp_path_factory) -> dict:
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Bildlauf fehlt: {', '.join(fehlt)}")
    return _lauf(tmp_path_factory.mktemp("zepwaehler-alt"), "roh")


def test_der_waehler_geht_ueberhaupt_auf(repariert):
    """Die Gegenprobe zuerst.

    Alles darunter misst eine Flaeche waehrend eines Waehlers. Gibt es
    den Waehler gar nicht, sind die Zahlen beliebig - und der Test
    meldete Erfolg fuer ein Fenster, das nie da war.
    """
    assert repariert["fenster"] is not None, (
        "kein Fenster mit dem Titel des Waehlers in `hyprctl clients`:\n"
        + repariert["protokoll"][-3000:])
    assert "WAEHLER:offen:true" in repariert["protokoll"], (
        "waehleDatei() hat false gemeldet - GTK konnte keinen Waehler "
        f"bauen:\n{repariert['protokoll'][-3000:]}")


def test_die_flaeche_sinkt_fuer_die_dauer_des_waehlers(repariert):
    """Waehrend der Waehler offen ist, liegt die Flaeche UNTEN.

    Das ist die Reparatur, in einer Zahl: eine Flaeche auf Ebene 1 liegt
    unter jedem gewoehnlichen Fenster, eine auf Ebene 3 ueber jedem.
    """
    assert repariert["ebene_vorher"] == EBENE_UEBERLAGERUNG, (
        "die Flaeche stand schon vor dem Waehler nicht auf der "
        f"Ueberlagerung: {repariert['ebene_vorher']}")
    assert repariert["ebene_waehrend"] == EBENE_UNTEN, (
        "die Flaeche liegt waehrend des Waehlers auf Ebene "
        f"{repariert['ebene_waehrend']} statt {EBENE_UNTEN} - der Waehler "
        "steht damit wieder darunter, und der Nutzer sieht ihn nur zur "
        "Haelfte. Siehe waehleDatei() in ags-overlay-utils.template.")


def test_die_flaeche_kommt_danach_zurueck(repariert):
    """Und danach steht sie wieder da, wo sie war.

    Eine Reparatur, die die Schale unten liegen laesst, waere schlimmer
    als der Fehler: das Fenster verschwaende hinter jedem anderen.
    """
    assert repariert["fenster_nachher"] is None, (
        "der Waehler steht nach dem Abbruch noch")
    assert repariert["ebene_nachher"] == EBENE_UEBERLAGERUNG, (
        "die Flaeche ist nach dem Waehler auf Ebene "
        f"{repariert['ebene_nachher']} geblieben statt auf "
        f"{EBENE_UEBERLAGERUNG}")
    assert repariert["lebt"], "der Prozess hat den Waehler nicht ueberlebt"


def test_ohne_die_reparatur_bleibt_die_flaeche_oben(roh):
    """Die Gegenprobe: der Aufruf, wie er bis zum 01.09.2026 dastand.

    Er geht nicht kaputt und wirft nichts - der Waehler geht sogar auf.
    Er geht nur UNTER der Flaeche auf, und genau das hat der Nutzer
    gesehen. Diese Zusicherung haelt fest, dass die Messung oben etwas
    misst: ohne sie waere "Ebene 1" eine Zahl ohne Vergleich.
    """
    assert roh["fenster"] is not None, (
        "auch der rohe Aufruf soll einen Waehler bauen - sonst misst die "
        f"Gegenprobe etwas anderes:\n{roh['protokoll'][-3000:]}")
    assert roh["ebene_waehrend"] == EBENE_UEBERLAGERUNG, (
        "der rohe Aufruf laesst die Flaeche nicht mehr auf der "
        f"Ueberlagerung liegen ({roh['ebene_waehrend']}) - dann hat sich "
        "etwas ausserhalb dieser Datei geaendert, und die Zusicherungen "
        "darueber messen nicht mehr den Unterschied, den sie behaupten.")
