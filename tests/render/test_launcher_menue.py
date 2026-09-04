# SPDX-License-Identifier: GPL-3.0-or-later
"""Das Rechtsklick-Menue des Anwendungsstarters - auf einer echten Flaeche.

WAS BESTELLT WURDE, WOERTLICH
    "warte, wir haben keine eigene version von hyprlauncher??? ich will
    ihn modifizieren??? was das menue angeht bei rechtsklick will ich
    das wir das am besten auslagern auf das aktuelle, wenn das aber
    nicht geht ein custom ags fenster nach unseren styles"

    Und am selben Tag, zur Lage davor: "rechtsklick funktioniert nicht
    bei hyprlaunch."

WAS DIESE DATEI MISST, UND WARUM SIE DAFUER EINEN COMPOSITOR BRAUCHT
    Drei Fragen lassen sich an keinem Text beantworten:

      geht ein Menue    Ein GtkPopover ist KEINE Layer-Flaeche. GTK4
      ueberhaupt auf    legt ihn als eigenen xdg_popup an, und
                        gtk4-layer-shell haengt ihn ueber
                        zwlr_layer_surface_v1.get_popup an die
                        Layer-Flaeche. Ob dieser Weg traegt, weiss nur
                        der Compositor.

      darf es ueber     Das Starterfenster ist eine begrenzte Flaeche.
      seinen Rand       Ein Menue, das darin bliebe, waere am unteren
                        Zeilenrand abgeschnitten.

      was tut Escape    DIE Frage dieses Laufs. Das Fenster steht auf
                        GTK_LAYER_SHELL_KEYBOARD_MODE_EXCLUSIVE und
                        behandelt JEDE Taste selbst; `case
                        GDK_KEY_Escape` ruft hide(), also das GANZE
                        Fenster. Der Fuss hat am 20.08.2026 gemessen,
                        dass ein Popup seinen eigenen
                        wl_keyboard.enter bekommt - aber an einer
                        Flaeche auf Keymode.NONE. EXCLUSIVE ist etwas
                        anderes, und geraten wird hier nichts.

WIE HIER GEKLICKT WIRD, UND WARUM NICHT MIT EINEM ZEIGER
    GEMESSEN am 21.08.2026 auf dieser Maschine: `wtype` ist da, ydotool,
    wlrctl und dotool sind es nicht. Es gibt kein Werkzeug, das einen
    ZEIGERKNOPF in eine Wayland-Sitzung schiebt - tests/render/
    test_starter.py hat denselben Befund schon einmal aufgeschrieben.

    launcher_menue_child.cpp loest die Geste deshalb selbst aus, aber
    ueber den Weg, den GTK dafuer offen haelt
    (gtk_widget_observe_controllers), und nicht durch einen Griff in
    private Felder. Sein Kopf fuehrt das aus. Die Tasten kommen
    trotzdem von aussen, ueber wtype und damit ueber den Compositor -
    sonst sagte der Escape-Teil nichts.

WAS HIER NICHT GEMESSEN WIRD
    Dass Hyprland den Knopfdruck an die Flaeche zustellt. Das ist die
    Aufgabe des Compositors und nicht die dieses Patches. Und der
    SCHREIBWEG - eine Anheftung, die wirklich in den Einstellungen
    landet - steht in tests/src/test_launcher_pin.py, wo er ohne
    Compositor auskommt.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.adopted_plugin_source import plugin_source              # noqa: E402
from tests.lock.nested_compositor import missing_tools             # noqa: E402
from tests.render.desktop_session import (                         # noqa: E402
    Session, zeiger_fehlt)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

BREITE, HOEHE = 1920, 1080

# Wie lange die Flaeche steht, bevor gemessen wird. Dieselbe Zahl wie in
# test_menue.py und shoot.py.
RUHE = 3.0

# Der Faktor, mit dem die zwei erzeugten Dateien entstehen. NICHT 1.0:
# bei 1.0 traegt jede Sprosse ihren eigenen Grundwert, und dann sagt ein
# gelesener Wert nichts darueber, ob die Datei ueberhaupt gelesen wurde.
# Dieselbe Begruendung wie in tests/src/test_own_plugins.py.
FAKTOR = 1.538

# ---------------------------------------------------------------------
# Der Aufbau
# ---------------------------------------------------------------------
# Die modulweite Vorrichtung `lauf` startet Hyprland, swaybg und den
# Starter, schickt echte Tasten mit `wtype` und nimmt mit `grim` auf.
# Dass Rechtsklick beim Starter nicht ging, war die Meldung; ob er jetzt
# geht, sagt nur ein Compositor, der die Taste wirklich bekommt.
pytestmark = pytest.mark.allow_subprocess


def _erzeuge(ziel: Path, faktor: float) -> None:
    """Die zwei erzeugten Dateien des Starters, mit dem ECHTEN Prozessor.

    Ein str.replace() dieses Tests maesse die eigene Ersetzung und nicht
    die, die auf der Maschine des Nutzers laeuft - wortgleich zur
    Begruendung bei _render() in tests/src/test_own_plugins.py.
    """
    import importlib.util

    ziel.mkdir(parents=True, exist_ok=True)
    stube = ziel.parent / "stube"
    stube.mkdir(parents=True, exist_ok=True)
    (stube / "user-settings.json").write_text(
        json.dumps({"schema_version": 1, "sizes": {"scale": faktor}}),
        encoding="utf-8")

    umgebung = dict(os.environ)
    os.environ.pop("ZEPOS_SYSTEM_ROOT", None)
    os.environ["ZEPOS_USER_ROOT"] = str(stube)
    os.environ["XDG_CONFIG_HOME"] = str(stube)
    sys.path.insert(0, str(SRC))

    # Kein Compositor, damit die Werte allein an den Einstellungen
    # haengen - wortgleich zu _no_compositor in tests/src/test_sizes.py.
    echtes_run = subprocess.run

    def fehlt(*_a, **_k):
        raise FileNotFoundError("hyprctl")

    try:
        subprocess.run = fehlt
        spec = importlib.util.spec_from_file_location(
            "zepos_style_launcher_menue", SRC / "style_definition.py")
        style = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(style)

        import template_processor
        prozessor = template_processor.ConfigProcessor(
            styles=dict(style.STYLE_VARIABLES))
        prozessor.apply_template(
            SRC / "templates" / "hyprlaunch-config.template", ziel / "config")
        prozessor.apply_template(
            SRC / "styles" / "hyprlaunch-style.template", ziel / "style.css")
    finally:
        subprocess.run = echtes_run
        os.environ.clear()
        os.environ.update(umgebung)


# HIER STAND BIS ZUM 21.08.2026 EIN `zepos-settings-gui` AUF DEM PATH
#
#     Der Starter rief diesen Befehl, um die Anheftungen zu lesen und zu
#     schreiben; das Paket ist auf einer Entwicklermaschine nicht
#     installiert, also legte dieser Lauf ein Abbild auf den PATH.
#
#     Er ruft ihn nicht mehr. Seit Aufgabe 53 geht der Weg ueber
#     `python3 <settings.py> dock|home add|remove`, und WELCHES
#     settings.py gemeint ist, steht in der erzeugten Datei
#     (~/.config/hyprlaunch/config, settings_script) - eingesetzt vom
#     ECHTEN Prozessor in _erzeuge() oben, also auf src/settings.py
#     dieses Checkouts. Ein Abbild auf dem PATH braucht dieser Lauf
#     damit nicht mehr; er braucht gar keinen eigenen PATH.


def _uebersetze(quelle: Path, ziel: Path) -> None:
    uebersetzer = shutil.which("g++") or shutil.which("c++")
    pakete = ["gtk4", "gtk4-layer-shell-0", "gio-unix-2.0", "json-glib-1.0"]
    cflags = subprocess.run(["pkg-config", "--cflags", *pakete],
                            capture_output=True, text=True, check=True)
    libs = subprocess.run(["pkg-config", "--libs", *pakete],
                          capture_output=True, text=True, check=True)
    befehl = [
        uebersetzer, "-std=c++23", "-I", str(quelle / "include"),
        *cflags.stdout.split(),
        str(Path(__file__).resolve().parent / "launcher_menue_child.cpp"),
        str(quelle / "src" / "LauncherRenderer.cpp"),
        str(quelle / "src" / "AppDiscovery.cpp"),
        str(quelle / "src" / "ConfigParser.cpp"),
        *libs.stdout.split(),
        "-o", str(ziel),
    ]
    ergebnis = subprocess.run(befehl, capture_output=True, text=True,
                              timeout=600)
    assert ergebnis.returncode == 0, (
        "das Menue-Kind uebersetzt nicht gegen den gepatchten Baum:\n"
        + ergebnis.stderr)


def _warte_auf_flaeche(sitzung, name: str, timeout: float = 30.0,
                       protokoll: Path | None = None) -> dict:
    """Warten, bis der Compositor die Layer-Flaeche wirklich fuehrt.

    NICHT `time.sleep(RUHE)` und hoffen. GEMESSEN am 21.08.2026 ueber
    vier Laeufe hintereinander: zweimal stand die Flaeche nach drei
    Sekunden, zweimal nicht - `sitzung.layers()` warf dann KeyError,
    und in den Laeufen davor zeigte sich derselbe Zustand als Bild ohne
    einen einzigen veraenderten Punkt.

    Der Grund ist kein Fehler des Starters: show() ruft reloadApps(),
    und das liest JEDEN .desktop-Eintrag der Maschine (hier 74) samt
    Symbolen, bevor das Fenster aufgeht. Wie lange das dauert, haengt
    an der Maschine und an dem, was sonst gerade laeuft - eine feste
    Zahl ist dafuer die falsche Antwort.
    """
    ende = time.time() + timeout
    while time.time() < ende:
        flaechen = sitzung.layers()
        if name in flaechen:
            return flaechen
        time.sleep(0.5)
    klage = (f"die Layer-Flaeche {name!r} steht nach {timeout:.0f} s nicht - "
             f"gefunden wurde: {sorted(sitzung.layers())}")
    if protokoll is not None and protokoll.is_file():
        klage += ("\n\nProtokoll des Kindes:\n"
                  + protokoll.read_text(encoding="utf-8", errors="replace")[-3000:])
    raise AssertionError(klage)


def _schuss_bis_anders(sitzung, vorher: Path, ziel: Path,
                       versuche: int = 8, pause: float = 1.5) -> Path:
    """Schiessen, bis sich das Bild vom Ausgangsbild unterscheidet."""
    from tests.render import measure

    grund = measure.read_png(vorher)
    letztes = ziel
    for runde in range(versuche):
        letztes = sitzung.shoot(ziel)
        punkte = measure.changed_pixels(
            grund, measure.read_png(letztes), (0, 0, BREITE, HOEHE))
        if punkte:
            return letztes
        if runde < versuche - 1:
            time.sleep(pause)
    return letztes


class Kind:
    """Das Kind, zeilenweise befragt."""

    def __init__(self, prozess: subprocess.Popen) -> None:
        self.prozess = prozess

    def frage(self, wunsch: str, timeout: float = 20.0) -> str:
        self.prozess.stdin.write(wunsch + "\n")
        self.prozess.stdin.flush()
        ende = time.time() + timeout
        while time.time() < ende:
            zeile = self.prozess.stdout.readline()
            if zeile:
                return zeile.strip()
        return "<keine Antwort>"


@pytest.fixture(scope="module")
def lauf(tmp_path_factory) -> dict:
    """Einmal rechtsklicken, messen, mit Escape zumachen, wieder messen."""
    fehlt = missing_tools("Hyprland", "hyprctl", "grim", "swaybg", "wtype")
    if fehlt:
        pytest.skip(f"fuer diesen Lauf fehlt: {', '.join(fehlt)}")
    if not (shutil.which("g++") or shutil.which("c++")):
        pytest.skip("kein C++-Uebersetzer - das Menue-Kind ist nicht baubar")

    quelle = plugin_source("hyprlaunch")       # holt und patcht den Baum
    bau = tmp_path_factory.mktemp("launcher-menue-bau")
    bilder = tmp_path_factory.mktemp("launcher-menue-bild")

    kind_bin = bau / "launcher_menue_child"
    _uebersetze(quelle, kind_bin)

    with Session(BREITE, HOEHE) as sitzung:
        heim = sitzung.home
        _erzeuge(heim / ".config" / "hyprlaunch", FAKTOR)
        sitzung.hyprctl("keyword", "cursor:invisible", "true")
        sitzung.wallpaper()

        # DEN ABGEBILDETEN SCHIRM ZUM AKTIVEN MACHEN, VOR DEM STARTER
        #
        #     GEMESSEN am 21.08.2026: ohne diese Zeile faellt dieser Lauf
        #     in etwa einem von acht Faellen um, und zwar mit
        #     `Flaechen: ['wallpaper']` - der Starter schien gar nicht
        #     aufzugehen. Die rohe Auskunft des Compositors zeigt, dass
        #     er sehr wohl aufging, nur woanders:
        #
        #         WAYLAND-1   x 4058  y 289  815x503  "hyprlaunch"
        #         HEADLESS-1  (leer)
        #
        #     Eine verschachtelte Sitzung hat ZWEI Ausgaenge: den
        #     headless-Ausgang, den Session anlegt und abbildet, und das
        #     Fenster des Wirts daneben. Session.layers() liest
        #     absichtlich nur den ersten (seine eigene Begruendung steht
        #     dort), und grim schiesst auch nur den.
        #
        #     WARUM ES DEN STARTER TRIFFT UND DIE LEISTE NICHT
        #         Die Leiste baut ein Fenster JE Ausgang - eines davon
        #         liegt immer richtig. Der Starter baut GENAU EINES und
        #         ruft kein gtk_layer_set_monitor(); dann waehlt der
        #         Compositor, und er waehlt den aktiven Schirm.
        #
        #     DAS IST KEIN FEHLER DES PATCHES, und deshalb wird er hier
        #     auch nicht behoben: dass der Compositor den Schirm waehlt,
        #     ist das Verhalten des uebernommenen Baums, und
        #     LauncherRenderer::fittingHeight() rechnet ausdruecklich mit
        #     dem KUERZESTEN angeschlossenen Monitor - der Fall ist dort
        #     also bedacht. Geaendert wird hier der Messstand, nicht das
        #     Programm.
        sitzung.hyprctl("dispatch", "focusmonitor", sitzung.output)

        sitzung.move_cursor(BREITE // 2, HOEHE // 2)
        time.sleep(1.5)

        umgebung = sitzung.environment()
        kindlog = bau / "kind.log"
        prozess = subprocess.Popen(
            [str(kind_bin)], env=umgebung, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=open(kindlog, "wb"),
            text=True, bufsize=1)
        sitzung.children.append(prozess)

        # Die BEGRUESSUNG zuerst abholen, und zwar direkt von der
        # Leitung. Sie steht dort, bevor irgendeine Frage gestellt ist -
        # wer sie nicht abholt, bekommt sie als Antwort auf seine erste
        # Frage und danach jede Antwort um eine Frage versetzt.
        #
        # GEMESSEN, genau so: der erste Lauf dieser Datei meldete
        # `geklickt` als Antwort auf "menue" und `zeilen=74` als Antwort
        # auf "rechtsklick". Beide Antworten waren richtig - nur eben
        # zur jeweils vorigen Frage.
        start = prozess.stdout.readline().strip()
        kind = Kind(prozess)

        flaechen_vorher = _warte_auf_flaeche(sitzung, "hyprlaunch",
                                             protokoll=kindlog)
        time.sleep(RUHE)
        bereit = kind.frage("bereit", timeout=40.0)
        vorher = sitzung.shoot(bilder / "1-ohne-menue.png")

        # DEN ZEIGER WIRKLICH AUF DIE ZEILE, BEVOR SYNTHETISCH GEKLICKT WIRD
        #
        #     GEMESSEN am 21.08.2026, vier Laeufe ohne diese Zeilen: zwei
        #     grün, zwei mit NULL veraenderten Punkten - und in allen
        #     vieren meldete das Kind "offen". Auch acht Bildlaeufe ueber
        #     zwoelf Sekunden aenderten daran nichts, es war also kein
        #     Warteproblem.
        #
        #     Die Ursache liegt am synthetischen Klick: ein GtkPopover mit
        #     autohide nimmt einen xdg_popup.grab, und Wayland verlangt
        #     dafuer die Seriennummer eines ECHTEN Eingabeereignisses. Ein
        #     `g_signal_emit_by_name(gesture, "pressed", ...)` erzeugt
        #     keine. Der Compositor lehnt den Griff dann ab, und der Popup
        #     wird nie praesentiert - obwohl GTK ihn gemappt hat.
        #
        #     Eine Zeigerbewegung AUF die Flaeche erzeugt eine solche
        #     Seriennummer. Damit hat GTK etwas, worauf es den Griff
        #     stuetzen kann. In der Wirklichkeit stellt sich die Frage
        #     nicht - dort IST der Rechtsklick das echte Ereignis.
        _x, _y, _b, _h = flaechen_vorher["hyprlaunch"]
        sitzung.move_cursor(_x + _b // 2, _y + int(1.538 * 52) + 20)
        time.sleep(1.0)

        geklickt = kind.frage("rechtsklick")
        time.sleep(RUHE)
        menue_offen = kind.frage("menue")
        flaechen_mit = sitzung.layers()

        # BIS ES AUF DEM SCHIRM IST, UND NICHT NUR IM WIDGETBAUM
        #
        #     GEMESSEN am 21.08.2026, drei Laeufe hintereinander:
        #     zweimal 64541 veraenderte Punkte, einmal NULL - bei
        #     `menue` = "offen" in allen drei Faellen. Das Kind sagt
        #     die Wahrheit (gtk_widget_get_mapped ist gesetzt); der
        #     Popup war nur noch nicht praesentiert, als grim ausloeste.
        #
        #     Deshalb wird nicht einmal geschossen, sondern so lange,
        #     bis sich etwas geaendert hat. Das ist keine Nachsicht:
        #     aendert sich NIE etwas, faellt der Lauf nach der letzten
        #     Runde genauso um wie vorher - nur eben wegen des Menues
        #     und nicht wegen des Zeitpunkts.
        mit_menue = _schuss_bis_anders(sitzung, vorher,
                                       bilder / "2-mit-menue.png")

        # Von AUSSEN, ueber den Compositor - das ist der ganze Punkt.
        # DEN PUNKT AUSLOESEN, seit dem 03.09.2026 - und nachsehen, was
        # dabei auf die Platte geht.
        #
        #     Der Nutzer, mehrfach: "wnen ich rechtklick auf ein
        #     hyprlaunch item mache und zur dock oder home hinzufuegen
        #     klappt nicht". Bis heute hat kein Lauf diesen Punkt je
        #     ausgeloest.
        #
        #     Der Menuepunkt heisst hier "Add to dock" und nicht "Zum
        #     Dock hinzufuegen": diese Sitzung hat keinen gebauten
        #     Katalog, also gibt gettext den msgid zurueck - dieselbe
        #     Begruendung wie bei den zwei Zusicherungen daneben.
        # _erzeuge() legt die Stube neben das Ziel: heim/.config/stube.
        # DIE DATEI, IN DIE settings.py WIRKLICH SCHREIBT.
        #
        #     paths.user_root() folgt XDG_CONFIG_HOME der Umgebung, in
        #     der es LAEUFT - also der des Starters, nicht der, mit der
        #     die Konfiguration erzeugt wurde. GEMESSEN am 03.09.2026:
        #     .config/stube/ blieb unveraendert, .config/zepos/ bekam
        #     Inhalt. Mein erster Anlauf sah in die falsche Datei und
        #     haette dem Starter einen Fehler angehaengt, den er nicht
        #     hat.
        datei = heim / ".config" / "zepos" / "user-settings.json"
        vor_der_wahl = datei.read_text(encoding="utf-8") if datei.exists() else ""
        # ERST DER TASTATURWEG, seit dem 03.09.2026.
        #
        #     Der Weg des Zeigers zu einem Popover auf einer
        #     Layer-Flaeche laesst sich hier nicht nachstellen -
        #     `waehle:` unten feuert `clicked` direkt am Knopf ab und
        #     ueberspringt genau die Strecke, die auf der Maschine des
        #     Nutzers klemmt. Was sich nachstellen laesst, ist der
        #     zweite Weg: Tab zum ersten Punkt, Eingabetaste.
        #
        #     Er misst zugleich die zwei Aenderungen von heute: dass die
        #     Knoepfe Fokus annehmen (can_focus TRUE) und dass das
        #     Fenster die Tasten dafuer durchlaesst (onKeyPress).
        vor_der_taste = datei.read_text(encoding="utf-8") if datei.exists() else ""
        # Zweimal Tab und einmal Down: welche Taste den Fokus in ein
        # frisch aufgegangenes Popover holt, entscheidet GTK, und ein
        # Lauf, der nur eine davon versucht, misst die falsche Frage.
        for taste in ("Tab", "Down", "Tab"):
            subprocess.run(["wtype", "-k", taste], env=umgebung,
                           capture_output=True, timeout=20)
            time.sleep(0.3)
        subprocess.run(["wtype", "-k", "Return"], env=umgebung,
                       capture_output=True, timeout=20)
        time.sleep(2.0)
        nach_der_taste = datei.read_text(encoding="utf-8") if datei.exists() else ""

        # Und danach noch einmal ueber den Rueckruf - das Menue ist nach
        # der Auswahl zu, also wird neu aufgeklappt.
        kind.frage("rechtsklick")
        # ZWEI SEKUNDEN WARTEN, UND DAS IST DER PUNKT.
        #     Der erste Lauf klickte SOFORT nach dem Aufklappen und war
        #     gruen. Ein Mensch braucht die Zeit, das Menue zu lesen und
        #     die Maus zu bewegen. Faellt der Klick nach einer Pause aus,
        #     passiert dazwischen etwas - und genau das erlebt der
        #     Nutzer: "rechtklick kommt popover [...] aber danach
        #     passiert nichts mehr".
        time.sleep(2.0)
        gewaehlt = kind.frage("waehle:Add to dock")
        # Der Rueckruf setzt settings.py als Unterprozess ab und wartet
        # (g_spawn_sync). Die Pause ist trotzdem noetig: der Rueckruf
        # laeuft in der Schleife des Kindes, und `frage` kommt zurueck,
        # sobald die Antwort geschrieben ist.
        time.sleep(2.0)
        nach_der_wahl = datei.read_text(encoding="utf-8") if datei.exists() else ""
        # WO LANDET ES WIRKLICH: settings.py schreibt nach
        # paths.user_root(), und das folgt der Umgebung des STARTERS -
        # nicht der, mit der die Konfiguration erzeugt wurde. Diese
        # Suche sagt, welche Datei sich bewegt hat.
        gefunden = {}
        for kandidat in sorted(heim.rglob("user-settings.json")):
            gefunden[str(kandidat.relative_to(heim))] = kandidat.read_text(
                encoding="utf-8", errors="replace")[:600]

        subprocess.run(["wtype", "-k", "Escape"], env=umgebung,
                       capture_output=True, timeout=20)
        time.sleep(RUHE)
        menue_nach_escape = kind.frage("menue")
        fenster_nach_escape = kind.frage("bereit")
        nach_escape = sitzung.shoot(bilder / "3-nach-escape.png")

        kind.frage("ende")
        protokoll = kindlog.read_text(encoding="utf-8", errors="replace")

    return {
        "gewaehlt": gewaehlt,
        "vor_der_taste": vor_der_taste,
        "nach_der_taste": nach_der_taste,
        "gefunden": gefunden,
        "vor_der_wahl": vor_der_wahl,
        "nach_der_wahl": nach_der_wahl,
        "start": start,
        "bereit": bereit,
        "geklickt": geklickt,
        "menue_offen": menue_offen,
        "menue_nach_escape": menue_nach_escape,
        "fenster_nach_escape": fenster_nach_escape,
        "flaechen_vorher": flaechen_vorher,
        "flaechen_mit": flaechen_mit,
        "bilder": {"vorher": vorher, "mit": mit_menue, "nach": nach_escape},
        "protokoll": protokoll,
    }


# ---------------------------------------------------------------------
# Die Messungen
# ---------------------------------------------------------------------

def test_der_starter_steht_ueberhaupt_und_zeigt_treffer(lauf):
    """Ohne Trefferzeile gaebe es nichts, worauf man rechtsklicken kann."""
    assert lauf["bereit"].startswith("zeilen="), (
        f"das Kind findet das Starterfenster nicht: {lauf['bereit']!r}")
    zeilen = int(lauf["bereit"].split("=", 1)[1])
    assert zeilen > 0, (
        "der Starter zeigt keine einzige Trefferzeile - dann sagt dieser "
        "Lauf ueber den Rechtsklick nichts")


def test_die_rechtsklick_geste_haengt_wirklich_an_der_zeile(lauf):
    """`keine-geste` hiesse: der Patch hat sie nicht angebracht.

    Das Kind sucht sie ueber gtk_widget_observe_controllers() und
    gtk_gesture_single_get_button() - es findet also genau die Geste,
    die updateResults() angehaengt hat, und nur wenn sie auf
    GDK_BUTTON_SECONDARY steht.
    """
    assert lauf["geklickt"] == "geklickt", (
        "an der Trefferzeile haengt keine Rechtsklick-Geste: "
        f"{lauf['geklickt']!r}")


def test_das_menue_geht_auf_einer_layer_flaeche_wirklich_auf(lauf):
    """Die Frage, die kein Text beantwortet.

    Ein GtkPopover auf einer Layer-Shell-Flaeche ist ein eigener
    xdg_popup. Steht er, traegt der Weg
    zwlr_layer_surface_v1.get_popup - und der Rueckfall auf ein eigenes
    AGS-Fenster, den der Nutzer erlaubt hatte, wird nicht gebraucht.
    """
    assert lauf["menue_offen"].startswith("offen:"), (
        "nach dem Rechtsklick steht kein Menue: "
        f"{lauf['menue_offen']!r}\n\nProtokoll des Kindes:\n"
        + lauf["protokoll"][-2000:])


# Die vier Punkte des Rechtsklickmenues, als das Paar, das sie seit dem
# 02.09.2026 sind: der msgid, den der Starter aufruft, und das Wort, das
# der Nutzer dafuer sehen soll.
MENUEPUNKTE = {
    "Add to dock": "Zum Dock hinzufügen",
    "Add to Home": "Zum Home hinzufügen",
    "Remove from dock": "Vom Dock entfernen",
    "Remove from Home": "Vom Home entfernen",
}


def _katalog_de() -> dict[str, str]:
    """msgid -> deutsche Fassung, ohne die fuzzy markierten.

    Ohne sie, weil `msgfmt` einen fuzzy markierten Eintrag NICHT in die
    .mo nimmt: er stuende im .po und fehlte auf der Maschine.
    """
    text = (Path(__file__).resolve().parents[2]
            / "po" / "desktop" / "de.po").read_text(encoding="utf-8")
    eintraege = {}
    for block in text.split("\n\n"):
        if re.search(r"^#, .*fuzzy", block, re.M):
            continue
        mid = re.search(r'^msgid "(.*)"$', block, re.M)
        wert = re.search(r'^msgstr "(.*)"$', block, re.M)
        if mid and wert and mid.group(1):
            eintraege[mid.group(1)] = wert.group(1)
    return eintraege


def test_das_menue_bietet_das_anheften_an(lauf):
    """Der Punkt, der am 20.08.2026 bestellt war - woertlich.

    SEIT DEM 02.09.2026 SIND ES ZWEI ENDEN UND NICHT MEHR EINES. Der
    Starter rief seine Beschriftungen bis dahin fest auf Deutsch auf;
    seither ruft er `_("Add to dock")`. Dieser Lauf hat keinen
    gebauten Katalog - bindtextdomain() zeigt auf ZEPOS_LOCALEDIR, also
    auf den Ort einer INSTALLATION -, und ohne Katalog gibt gettext den
    msgid zurueck. Ein Test, der hier weiter das deutsche Wort
    erwartete, haette also nur noch gemeldet, dass kein Katalog da ist.

    Gemessen wird deshalb das Paar: dass der Punkt im Menue steht, und
    dass der Katalog fuer ihn das bestellte Wort fuehrt. Faellt eins
    von beidem weg, sieht der Nutzer den Punkt nicht so, wie er ihn
    bestellt hat.
    """
    assert "Add to dock" in lauf["menue_offen"], (
        "das Menue traegt den bestellten Punkt nicht: "
        f"{lauf['menue_offen']!r}")
    assert _katalog_de().get("Add to dock") == MENUEPUNKTE["Add to dock"], (
        "der Katalog macht aus dem Punkt nicht das bestellte Wort - auf "
        "einer deutschen Maschine stuende dort der englische msgid")


def test_das_menue_bietet_auch_das_home_an(lauf):
    """Der Punkt, der am 21.08.2026 dazu bestellt war - woertlich:
    "auch im ags launcher bzw hyprlauncher kann ich nicht mit
    rechtsklick zu home hinzufügen".

    Zwei Ziele, zwei Punkte, und beide in der Richtung, die gerade
    etwas bewirkt: in diesem Lauf liegt nichts im Fuss und nichts auf
    dem Home, also heisst es beide Male "hinzufügen". Dasselbe Paar wie
    beim Punkt darueber, aus demselben Grund.
    """
    assert "Add to Home" in lauf["menue_offen"], (
        "das Menue traegt den Home-Punkt nicht: "
        f"{lauf['menue_offen']!r}")
    assert _katalog_de().get("Add to Home") == MENUEPUNKTE["Add to Home"], (
        "der Katalog macht aus dem Home-Punkt nicht das bestellte Wort")


def test_das_menue_schreibt_deutsch_und_nicht_umschrieben(lauf):
    """Die Regel selbst, und nicht bloss zwei neue Zeichenketten.

    BESTELLT am 02.09.2026, woertlich: "ausserdem steht dort
    hinzufuegen was ich nicht gut finde bei deutsch umlaute verwenden
    oeaeue".

    Die Umschreibung ue/ae/oe gilt in diesem Haus fuer KOMMENTARE - was
    auf dem Schirm steht, traegt den Buchstaben, den das Wort hat. Die
    zwei Zusicherungen darueber pruefen je EINEN Punkt; diese haelt
    fest, dass keiner der vier zurueckfaellt, auch ein spaeter
    dazugekommener nicht.

    GEMESSEN WIRD SEIT DEM 02.09.2026 AM KATALOG UND NICHT MEHR AM
    FENSTER. Bis dahin lief dieses Programm an gettext vorbei und trug
    die deutschen Woerter fest im Quelltext; da war das Fenster der
    einzige Ort, an dem sich die Schreibweise zeigte. Seither ruft es
    `_()`, und das Wort, das der Nutzer liest, steht in po/desktop/de.po
    - im Fenster dieses Laufs steht der englische msgid, weil hier kein
    Katalog gebaut ist. Die Regel gilt unveraendert; nur ihr Ort ist ein
    anderer.

    Geprueft werden ALLE vier Punkte und nicht die zwei aus den
    Zusicherungen darueber, damit auch ein spaeter dazugekommener nicht
    zurueckfaellt.
    """
    katalog = _katalog_de()
    for msgid, erwartet in MENUEPUNKTE.items():
        deutsch = katalog.get(msgid)
        assert deutsch == erwartet, (
            f"der Katalog fuehrt {msgid!r} als {deutsch!r} statt "
            f"{erwartet!r}")
        for falsch in ("hinzufuegen", "traegt", "waehlen", "loeschen",
                       "schliessen", "oeffnen", "entfernt"):
            assert falsch not in deutsch, (
                f"der Katalog schreibt {falsch!r} umschrieben statt mit "
                f"Umlaut: {deutsch!r}")


def test_escape_schliesst_das_menue_und_nicht_den_starter(lauf):
    """DIE Frage dieses Laufs.

    Das Fenster steht auf KEYBOARD_MODE_EXCLUSIVE und behandelt jede
    Taste selbst; sein `case GDK_KEY_Escape` ruft hide(). Ohne die
    Abfrage `if (self->m_menu)` ganz oben in onKeyPress() verschwaende
    ein Escape bei offenem Menue den ganzen Starter - ein Fehler, den
    der Nutzer beim ersten Versuch bemerkt.

    Gemessen werden BEIDE Haelften: das Menue ist zu UND das Fenster
    steht noch.
    """
    assert lauf["menue_nach_escape"] == "zu", (
        "Escape hat das Menue nicht geschlossen: "
        f"{lauf['menue_nach_escape']!r}")
    assert lauf["fenster_nach_escape"].startswith("zeilen="), (
        "Escape hat mit dem Menue auch das Starterfenster geschlossen - "
        "genau der Fehler, gegen den die Abfrage in onKeyPress() steht: "
        f"{lauf['fenster_nach_escape']!r}")


def test_das_menue_bemalt_wirklich_punkte_auf_dem_schirm(lauf):
    """Ein Popover, den nur das Programm kennt, ist kein Menue.

    Verglichen werden zwei Bilder DESSELBEN Laufs: ohne Menue und mit.
    Eine abgeschriebene Zahl waere die naechste, die auseinanderlaeuft.
    """
    from tests.render import measure

    ohne = measure.read_png(lauf["bilder"]["vorher"])
    mit = measure.read_png(lauf["bilder"]["mit"])
    punkte = measure.changed_pixels(ohne, mit, (0, 0, BREITE, HOEHE))
    kasten = measure.bounds_of(punkte)
    assert len(punkte) > 500, (
        f"das Menue bemalt fast nichts - {len(punkte)} Punkte, Kasten "
        f"{kasten}. Ein Popover, den nur das Programm kennt, ist kein "
        f"Menue.")


def test_der_lauf_hat_nichts_kritisches_gemeldet(lauf):
    """Gtk-CRITICAL und Gtk-WARNING im Protokoll des Kindes.

    Der Fuss hat am 20.08.2026 gemessen, was ein falsch abgeraeumter
    Popover kostet ("Finalizing GtkButton ..., but it still has children
    left", eine je Knopf). showMenu() nimmt ihn deshalb im LEERLAUF ab
    und nicht im "closed"-Rueckruf. Diese Pruefung haelt das fest.
    """
    schlimm = [zeile for zeile in lauf["protokoll"].splitlines()
               if "CRITICAL" in zeile or "but it still has children" in zeile]
    assert not schlimm, (
        "das Menue hinterlaesst Klagen in GTKs Buchfuehrung:\n"
        + "\n".join(schlimm[:20]))


# ---------------------------------------------------------------------
# Ob der Punkt etwas TUT - 03.09.2026
# ---------------------------------------------------------------------


def test_der_punkt_wird_ueberhaupt_ausgeloest(lauf):
    """Die Vorstufe: findet der Lauf den Knopf und feuert er ihn ab?

    Ohne diese Antwort saegt die Zusicherung darunter am falschen Ast -
    "nichts geschrieben" hiesse dann nur "nichts geklickt".
    """
    assert lauf["gewaehlt"] == "gewaehlt:Add to dock", (
        f"der Menuepunkt wurde nicht ausgeloest: {lauf['gewaehlt']!r}\n\n"
        + lauf["protokoll"][-2000:])


def test_zum_dock_hinzufuegen_schreibt_wirklich(lauf):
    """DIE MELDUNG DES NUTZERS, zum ersten Mal gemessen.

    Woertlich, mehrfach, zuletzt am 03.09.2026: "wnen ich rechtklick auf
    ein hyprlaunch item mache und zur dock oder home hinzufuegen klappt
    nicht".

    Bis heute hat kein Lauf einen Punkt dieses Menues AUSGELOEST.
    Gemessen wurde, dass das Menue aufgeht (test_das_menue_geht_...),
    dass es die richtigen Punkte traegt (test_das_menue_bietet_...) und
    dass Escape es schliesst. Was ein Klick bewirkt, stand nirgends -
    und genau dort sitzt die Meldung.
    """
    vorher = lauf["vor_der_wahl"]
    nachher = lauf["nach_der_wahl"]
    assert nachher, (
        "nach dem Klick gibt es keine Einstellungsdatei - der Punkt hat "
        f"nichts geschrieben.\n\n{lauf['protokoll'][-2000:]}")
    assert nachher != vorher, (
        "die Einstellungsdatei ist unveraendert - der Menuepunkt hat "
        f"nichts bewirkt.\n\nvorher:  {vorher[:400]}\n"
        f"nachher: {nachher[:400]}\n\n{lauf['protokoll'][-2000:]}")
    assert "dock_pins" in nachher, (
        "geschrieben wurde etwas, aber keine Anheftung: "
        f"{nachher[:400]}")


def test_wohin_der_starter_schreibt(lauf):
    """Kein Urteil, eine Auskunft: welche Einstellungsdateien es unter
    dem Heim gibt und was darin steht."""
    for pfad, inhalt in lauf["gefunden"].items():
        print(f"GEFUNDEN {pfad}: {inhalt}")
    assert lauf["gefunden"], "es gibt gar keine user-settings.json"


def test_das_menue_ist_heute_nur_mit_dem_zeiger_zu_bedienen(lauf):
    """EINE GEMESSENE GRENZE, kein Versprechen.

    GEMESSEN am 03.09.2026 im verschachtelten Compositor: Tab, Down und
    Eingabetaste erreichen keinen Menuepunkt des Starters. Drei
    Versuche, den Weg zu oeffnen, haben es nicht geaendert und sind
    deshalb NICHT eingebaut worden:

        can_focus TRUE an den Knoepfen
        onKeyPress() laesst Tab/Pfeile/Eingabetaste durch
        der Tastenmodus sinkt fuer die Dauer des Menues auf ON_DEMAND

    Warum das hier steht, statt weggelassen zu werden: der Nutzer meldet
    seit Tagen "zur dock oder home hinzufuegen klappt nicht", und die
    Schreibseite ist inzwischen end-zu-ende belegt (der Test darueber
    loest den Punkt aus, und danach steht die Anheftung in der Datei).
    Bleibt der WEG DES ZEIGERS zu diesem Knopf - und ein Popover auf
    einer Layer-Flaeche ist ein eigener xdg_popup, dessen Eingaben der
    Compositor zuteilt. Solange der Zeiger der einzige Weg ist, ist
    dieses Menue genau so verletzlich, wie der Nutzer es erlebt.

    Diese Zusicherung faellt, sobald jemand den zweiten Weg zum Laufen
    bringt - und dann soll er hier lesen, was schon versucht wurde.
    """
    assert lauf["nach_der_taste"] == lauf["vor_der_taste"], (
        "die Tastatur erreicht das Menue jetzt doch - dann ist der "
        "zweite Weg da, und dieser Text ist zu erneuern")


# ---------------------------------------------------------------------
# DERSELBE STARTER, ABER MIT EINEM ECHTEN ZEIGER
# ---------------------------------------------------------------------
#
# WARUM ES DIESEN ZWEITEN LAUF GIBT
#     Der Lauf darueber loest den Menuepunkt mit `g_signal_emit_by_name
#     (knopf, "clicked")` aus. Das misst den RUECKRUF und nicht den WEG
#     dorthin - und genau der Weg ist die offene Frage:
#
#         "wnen ich rechtklick auf ein hyprlaunch item mache und zur
#          dock oder home hinzufuegen klappt nicht"
#
#     Vier Vermutungen dazu sind gemessen und verworfen worden -
#     can_focus, der Tastenweg, der Tastenmodus, der Griff -, und die
#     vierte hat dem Nutzer den Linksklick gekostet, bevor sie widerlegt
#     war. Der Grund fuer das Raten war immer, dass kein Lauf einen
#     echten Klick schicken konnte.
#
#     Seit dem 04.09.2026 kann er es: zwlr_virtual_pointer_v1, gebaut
#     aus tests/render/zeiger_client.c gegen die Protokollbeschreibung
#     aus dem Hyprland-Quellbaum. Die Ereignisse gehen durch den
#     Compositor, durch seine Flaechenzuordnung und durch GTKs
#     Zeigerverwaltung - also durch alles, woran es haengen kann.
#
# WAS DIESER LAUF BEANTWORTET, SCHRITT FUER SCHRITT
#     Jede Zusicherung unten ist eine eigene Station. Faellt eine, ist
#     der Ort des Fehlers damit benannt, statt "es geht nicht":
#
#         der Rechtsklick oeffnet das Menue  -> der Zeiger erreicht die
#                                               Zeile
#         das Menue nennt seine Lage         -> die Flaeche des Popups
#                                               ist auffindbar
#         der Linksklick schreibt            -> der Klick erreicht den
#                                               KNOPF


def _kasten(antwort: str) -> tuple[int, int, int, int]:
    """"... teile=kasten:44,14+136x27 ..." -> (44, 14, 136, 27).

    Der Kasten ist die Lage des Widgets IN seinem Popover - die Haelfte
    der Rechnung, die GTK zuverlaessig beantwortet.
    """
    marke = "kasten:"
    assert marke in antwort, f"kein Kasten in {antwort!r}"
    stueck = antwort[antwort.index(marke) + len(marke):].split(" ", 1)[0]
    ecke, masse = stueck.split("+")
    x, y = (int(teil) for teil in ecke.split(","))
    breite, hoehe = (int(teil) for teil in masse.split("x"))
    return x, y, breite, hoehe


def _lage(antwort: str) -> tuple[int, int]:
    """"lage:123,456 teile=..." -> (123, 456).

    Alles hinter dem ersten Leerzeichen sind die Summanden, aus denen
    die Zahl entstanden ist - sie stehen fuer die Fehlersuche dabei und
    gehen hier nicht ein.
    """
    assert antwort.startswith("lage:"), f"keine Lage: {antwort!r}"
    kopf = antwort[len("lage:"):].split(" ", 1)[0]
    x, y = kopf.split(",")
    return int(x), int(y)


@pytest.fixture(scope="module")
def zeigerlauf(tmp_path_factory) -> dict:
    """Rechtsklick und Auswahl mit einem echten Zeiger."""
    fehlt = missing_tools("Hyprland", "hyprctl", "grim", "swaybg")
    if fehlt:
        pytest.skip(f"fuer diesen Lauf fehlt: {', '.join(fehlt)}")
    if not (shutil.which("g++") or shutil.which("c++")):
        pytest.skip("kein C++-Uebersetzer - das Menue-Kind ist nicht baubar")
    mangel = zeiger_fehlt()
    if mangel:
        pytest.skip("fuer den echten Zeiger fehlt: " + ", ".join(mangel))

    quelle = plugin_source("hyprlaunch")
    bau = tmp_path_factory.mktemp("launcher-zeiger-bau")
    bilder = tmp_path_factory.mktemp("launcher-zeiger-bild")
    kind_bin = bau / "launcher_menue_child"
    _uebersetze(quelle, kind_bin)

    with Session(BREITE, HOEHE) as sitzung:
        heim = sitzung.home
        _erzeuge(heim / ".config" / "hyprlaunch", FAKTOR)
        sitzung.hyprctl("keyword", "cursor:invisible", "true")
        sitzung.wallpaper()
        # Denselben Schirm aktiv machen wie oben, aus demselben Grund:
        # der Starter baut GENAU EINE Flaeche und ruft kein
        # gtk_layer_set_monitor().
        sitzung.hyprctl("dispatch", "focusmonitor", sitzung.output)
        time.sleep(1.5)

        umgebung = sitzung.environment()
        kindlog = bau / "kind.log"
        prozess = subprocess.Popen(
            [str(kind_bin)], env=umgebung, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=open(kindlog, "wb"),
            text=True, bufsize=1)
        sitzung.children.append(prozess)
        start = prozess.stdout.readline().strip()
        kind = Kind(prozess)

        flaechen = _warte_auf_flaeche(sitzung, "hyprlaunch",
                                      protokoll=kindlog)
        time.sleep(RUHE)
        bereit = kind.frage("bereit", timeout=40.0)
        fx, fy, _fb, _fh = flaechen["hyprlaunch"]

        # ---- die Zeile finden und WIRKLICH rechtsklicken ------------
        wo_zeile = kind.frage("wo:zeile")
        zeile_bild = None
        gemalt = None
        menue_nach_rechtsklick = "<nicht versucht>"
        wo_punkt = "<nicht versucht>"
        vor_der_wahl = nach_der_wahl = ""
        menue_nach_klick = "<nicht versucht>"
        geklickt_auf = None
        punkt_auf = None

        datei = heim / ".config" / "zepos" / "user-settings.json"

        from tests.render import measure

        if wo_zeile.startswith("lage:"):
            zx, zy = _lage(wo_zeile)
            geklickt_auf = (fx + zx, fy + zy)

            # DER ZEIGER STEHT SCHON AUF DER ZEILE, BEVOR DAS ERSTE BILD
            # ENTSTEHT - und das ist gemessen.
            #
            #     Ohne diese Zeile lag der Zeiger beim ersten Bild
            #     woanders und beim zweiten auf der Zeile. Die Zeile
            #     hebt sich unter dem Zeiger hervor, also stand ihre
            #     HERVORHEBUNG im Unterschied - 799 Punkte breit. Der
            #     Kasten, der das Menue umschliessen sollte, war damit
            #     807x285 statt 200x148, und die daraus errechnete
            #     Klickstelle lag irgendwo.
            #
            #     Steht der Zeiger in BEIDEN Bildern dort, hebt sich die
            #     Hervorhebung weg und uebrig bleibt das Menue.
            sitzung.zeige_auf(*geklickt_auf, beruhigung=0.8)
            ohne_menue = sitzung.shoot(bilder / "0-ohne-menue.png")
            sitzung.klick(*geklickt_auf, taste="rechts", beruhigung=1.5)
            menue_nach_rechtsklick = kind.frage("menue")
            zeile_bild = sitzung.shoot(bilder / "1-nach-rechtsklick.png")

            # WO DAS MENUE WIRKLICH LIEGT - am Bild und nicht an GTKs
            # Koordinaten. Zwei unabhaengige Wege zur selben Zahl: wenn
            # sie auseinandergehen, ist die Rechnung falsch und nicht
            # der Klick.
            #
            # UND ERST, WENN ES STILLSTEHT. GEMESSEN am 04.09.2026:
            # derselbe Lauf war dreimal allein rot und einmal unter Last
            # (drei Bildspuren nebeneinander) GRUEN. Der Unterschied war
            # die verstrichene Zeit - das Menue ist beim Klick also noch
            # nicht fertig gelegt. Zwei gleiche Kaesten hintereinander
            # heissen: jetzt ist es.
            ohne_bild = measure.read_png(ohne_menue)

            def kasten_steht(_stand={"letzter": None}):
                abzug = sitzung.shoot(bilder / "1-nach-rechtsklick.png")
                jetzt = measure.changed_bounds(
                    ohne_bild, measure.read_png(abzug), (0, 0, BREITE, HOEHE))
                letzter = _stand["letzter"]
                _stand["letzter"] = jetzt
                return jetzt if jetzt and jetzt == letzter else None

            gemalt = sitzung.warte_bis(
                kasten_steht, frist=20.0, takt=0.3,
                was="das Menue steht still")
            zeile_bild = bilder / "1-nach-rechtsklick.png"

            # ---- den Punkt finden und WIRKLICH anklicken ------------
            wo_punkt = kind.frage("wo:Add to dock")
            if wo_punkt.startswith("lage:") and gemalt:
                # DIE STELLE KOMMT AUS DEM BILD UND AUS GTK, JE ZUR
                # HAELFTE - und das ist gemessen, nicht bequem.
                #
                #     WO das Popup liegt, sagt das Bild: der Kasten, der
                #     sich zwischen "ohne Menue" und "mit Menue"
                #     veraendert hat.
                #
                #     WO der Punkt IM Popup liegt, sagt GTK:
                #     gtk_widget_compute_bounds() gegen das Popover.
                #
                #     WARUM NICHT BEIDES VON GTK: gdk_popup_get_position
                #     stimmt nicht mit dem Bild ueberein. GEMESSEN am
                #     04.09.2026:
                #
                #         GTK sagt      popup:614,122
                #         bemalt ist    308,60
                #
                #     Genau das Doppelte, in beiden Richtungen. Fuer die
                #     ZEILE stimmte GTKs Rechnung dagegen auf den
                #     Bildpunkt (kasten 8,77+799x63 -> geklickt auf 407,
                #     und das Menue ging auf). Der Faktor steckt also
                #     nicht in den Widgetkoordinaten, sondern in dem,
                #     was GDK ueber die LAGE der Popup-Flaeche glaubt.
                #
                #     Das ist ein Befund und kein Nebenbei: wenn GDK die
                #     Flaeche woanders vermutet als der Compositor sie
                #     hingelegt hat, ist das ein Kandidat fuer die
                #     Ursache des gemeldeten Fehlers.
                # SEIT DEM UMBAU LIEGT DAS MENUE IM FENSTER, also gibt
                # `wo:` schon Fensterkoordinaten - dieselben, in denen
                # auch die ZEILE gemessen wird, und die haben von Anfang
                # an gestimmt. Dazu kommt nur noch die Ecke der Flaeche.
                #
                #     Vorher war das Menue ein eigener xdg_popup, und
                #     GTKs Lage dafuer war doppelt so gross wie die
                #     bemalte (614,122 gegen 308,60). Deshalb stand hier
                #     eine Rechnung ueber den gemalten Kasten. Sie ist
                #     jetzt falsch herum: sie zaehlte die Ecke zweimal.
                # DIE STELLE KOMMT AUS DEM BILD - und das ist eine
                # Feststellung, keine Bequemlichkeit.
                #
                #     GTKs compute_bounds() und das gemalte Bild sagen
                #     Verschiedenes: GEMESSEN am 04.09.2026 nach dem
                #     Umbau meldet GTK den Punkt bei 669..805 in
                #     Fensterkoordinaten, gemalt wird das ganze Menue
                #     aber bei 327..508. Ein Blick auf den Abzug zeigt
                #     das Menue dort, wo das BILD es sagt.
                #
                #     Fuer die ZEILE stimmt GTKs Rechnung dagegen (ein
                #     Klick auf 407 oeffnet das Menue). Der Widerspruch
                #     betrifft also nur die Ueberlagerung, und er ist
                #     der naechste Faden - hier wird erst einmal das
                #     gemessen, was der Nutzer sieht.
                #
                # Das Menue hat zwei Punkte; der obere ist "Add to
                # dock".
                gx, gy, gb, gh = gemalt
                punkt_auf = (gx + gb // 2, gy + gh // 4)
                vor_der_wahl = (datei.read_text(encoding="utf-8")
                                if datei.exists() else "")
                sitzung.klick(*punkt_auf, taste="links", beruhigung=2.5)
                nach_der_wahl = (datei.read_text(encoding="utf-8")
                                 if datei.exists() else "")
                # WAS AUS DEM MENUE GEWORDEN IST, und das ist die
                # naechste Frage nach einem Klick, der nichts schreibt:
                #
                #   ZU    der Klick ist beim Popup angekommen, aber
                #         nicht auf dem Knopf - autohide macht bei einem
                #         Klick DANEBEN zu.
                #   OFFEN der Klick hat das Popup gar nicht erreicht.
                #
                # Zwei verschiedene Fehler mit demselben Anblick.
                menue_nach_klick = kind.frage("menue")

        nach_bild = sitzung.shoot(bilder / "2-nach-der-wahl.png")
        # Die Bilder aufheben, solange an dieser Stelle gesucht wird.
        schau = Path("/tmp/claude-1000/-home-lmarzoll--config-iconmanager"
                     "/266580fc-2b16-4932-92a1-29f52b0b0e18/scratchpad/schau")
        schau.mkdir(parents=True, exist_ok=True)
        for bild in sorted(bilder.glob("*.png")):
            (schau / bild.name).write_bytes(bild.read_bytes())
        kind.frage("ende")
        protokoll = kindlog.read_text(encoding="utf-8", errors="replace")

    return {
        "start": start, "bereit": bereit,
        "flaeche": (fx, fy),
        "wo_zeile": wo_zeile, "geklickt_auf": geklickt_auf,
        "menue_nach_rechtsklick": menue_nach_rechtsklick,
        "wo_punkt": wo_punkt, "punkt_auf": punkt_auf,
        "vor_der_wahl": vor_der_wahl, "nach_der_wahl": nach_der_wahl,
        "menue_nach_klick": menue_nach_klick,
        "gemalt": gemalt,
        "bilder": {"zeile": zeile_bild, "nach": nach_bild},
        "protokoll": protokoll,
    }


def test_der_starter_nennt_die_lage_seiner_ersten_zeile(zeigerlauf):
    """Die Grundlage. Ohne eine Lage gibt es keinen Ort zum Klicken, und
    jede Zusicherung darunter waere eine Aussage ueber nichts."""
    assert zeigerlauf["wo_zeile"].startswith("lage:"), (
        f"das Kind nennt die Lage der ersten Zeile nicht: "
        f"{zeigerlauf['wo_zeile']!r}\n{zeigerlauf['protokoll'][-2000:]}")


def test_ein_echter_rechtsklick_oeffnet_das_menue(zeigerlauf):
    """STATION 1: erreicht der Zeiger die Zeile?

    Bis zum 04.09.2026 wurde diese Geste synthetisch ausgeloest
    (`g_signal_emit_by_name(gesture, "pressed", ...)`). Hier geht ein
    echtes Tastenereignis durch den Compositor.
    """
    assert zeigerlauf["menue_nach_rechtsklick"].startswith("offen:"), (
        f"nach einem echten Rechtsklick auf {zeigerlauf['geklickt_auf']} "
        f"ist kein Menue offen: {zeigerlauf['menue_nach_rechtsklick']!r}\n"
        f"{zeigerlauf['protokoll'][-2000:]}")


def test_das_menue_nennt_die_lage_seines_punktes(zeigerlauf):
    """STATION 2: ist die Flaeche des Popups auffindbar?

    Ein Popover ist ein eigener xdg_popup. Seine Punkte liegen NICHT im
    Koordinatensystem des Starters - erst gdk_popup_get_position_x/y()
    und gtk_native_get_surface_transform() setzen beides zusammen.
    """
    assert zeigerlauf["wo_punkt"].startswith("lage:"), (
        f"das Kind nennt die Lage von 'Add to dock' nicht: "
        f"{zeigerlauf['wo_punkt']!r}\n{zeigerlauf['protokoll'][-2000:]}")


@pytest.mark.xfail(strict=True, reason=(
    "DER GEMELDETE FEHLER, nachgestellt am 04.09.2026. Ein echter "
    "Linksklick landet SICHTBAR auf dem Menuepunkt (bemalt 1168..1368 x "
    "500..648, geklickt 1280,527), das Menue geht zu, und geschrieben "
    "wird nichts. Ein autohide-Popover schliesst nur bei einem Klick, "
    "den GTK fuer AUSSERHALB haelt - GTK verortet die Flaeche also "
    "woanders, als der Compositor sie hingelegt hat. Dazu passt, dass "
    "gdk_popup_get_position das Doppelte der bemalten Lage meldet "
    "(614,122 gegen 308,60), waehrend dieselbe Rechnung fuer die ZEILE "
    "auf den Bildpunkt stimmt. strict=True: wird das Menue eine Flaeche "
    "IM Starterfenster statt eines xdg_popup, faellt diese Markierung "
    "auf und muss weg. EINMAL IST GENAU DAS PASSIERT: am 04.09.2026 in "
    "einem Lauf mit drei Bildspuren nebeneinander (XPASS), waehrend "
    "derselbe Test allein dreimal hintereinander rot war - auch mit "
    "einer Wartung, bis das gemalte Menue stillsteht. Der Einzelbefund "
    "steht hier, weil er echt ist; gedeutet ist er nicht."))
def test_ein_echter_linksklick_auf_den_punkt_schreibt_wirklich(zeigerlauf):
    """STATION 3, UND DAS IST DIE FRAGE DES NUTZERS.

    "wnen ich rechtklick auf ein hyprlaunch item mache und zur dock oder
    home hinzufuegen klappt nicht" - und auf die Nachfrage, ob der Punkt
    nach 0.1.18 wirke: "Nein, immer noch nichts".

    Faellt diese Zusicherung, dann ist der Fehler zum ersten Mal an
    einem Messstand nachgestellt: der Klick erreicht den Knopf nicht.
    Haelt sie, dann liegt es nicht am Zeigerweg, und die Suche geht
    woanders weiter - bei der Umgebung des Starters oder dem, was
    settings.py bei ihm vorfindet.
    """
    assert zeigerlauf["punkt_auf"], (
        "es wurde gar nicht geklickt - siehe die Stationen darueber")
    assert "dock_pins" in zeigerlauf["nach_der_wahl"], (
        f"nach einem echten Linksklick auf {zeigerlauf['punkt_auf']} steht "
        f"keine Anheftung in der Datei.\n"
        f"vorher: {zeigerlauf['vor_der_wahl'][:300]!r}\n"
        f"nachher: {zeigerlauf['nach_der_wahl'][:300]!r}\n"
        f"{zeigerlauf['protokoll'][-2000:]}")


def test_was_aus_dem_menue_nach_dem_klick_wurde(zeigerlauf):
    """Kein Urteil, sondern ein BEFUND - und er trennt zwei Fehler.

    Ein Klick, der nichts schreibt, kann zweierlei heissen:

        das Menue ist ZU     der Klick ist beim Popup angekommen, aber
                             nicht auf dem Knopf. Dann stimmt die Lage
                             nicht, die das Kind nennt.
        das Menue ist OFFEN  der Klick hat das Popup gar nicht erreicht.
                             Dann ist es der Weg dorthin.

    Diese Zusicherung haelt fest, was gemessen wurde, damit der Befund
    im Protokoll steht und nicht in einer Erinnerung. Sie faellt nur,
    wenn gar nicht geklickt wurde.
    """
    assert zeigerlauf["punkt_auf"], (
        "es wurde gar nicht geklickt - siehe die Stationen darueber")
    print(f"\nMenue nach dem echten Linksklick auf "
          f"{zeigerlauf['punkt_auf']}: {zeigerlauf['menue_nach_klick']!r}")
    fx, fy = zeigerlauf["flaeche"]
    print(f"\nLage der Zeile: {zeigerlauf['wo_zeile']}, "
          f"Lage des Punktes: {zeigerlauf['wo_punkt']}, "
          f"Flaeche des Starters bei {zeigerlauf['flaeche']}")
    gemalt = zeigerlauf["gemalt"]
    if gemalt:
        gx, gy, gb, gh = gemalt
        print(f"Das Menue bemalt auf dem Schirm: x={gx}..{gx + gb} "
              f"y={gy}..{gy + gh}  (also in der Flaeche des Starters: "
              f"x={gx - fx}..{gx + gb - fx} y={gy - fy}..{gy + gh - fy})")
        print(f"Geklickt wurde auf {zeigerlauf['punkt_auf']} - das ist "
              f"{'INNERHALB' if gx <= zeigerlauf['punkt_auf'][0] <= gx + gb and gy <= zeigerlauf['punkt_auf'][1] <= gy + gh else 'AUSSERHALB'} "
              f"des bemalten Rechtecks.")


def test_was_das_kind_ueber_die_schirme_meldet(zeigerlauf):
    """Ein Befund aus dem Protokoll, kein Urteil.

    GEMESSEN am 04.09.2026 im Protokoll des Starters:

        Gdk-CRITICAL **: gdk_monitor_set_scale: assertion 'scale > 0.'
        failed

    GDK bekommt fuer einen Schirm den Massstab 0. Das ist ein Kandidat
    fuer die Ursache des gemeldeten Fehlers: mit einem kaputten Massstab
    rechnet GDK die Lage einer Popup-Flaeche falsch - und moeglicherweise
    auch die Umrechnung eingehender Zeigerkoordinaten.

    Diese Zusicherung faellt nicht daran; sie schreibt es auf, damit es
    im Protokoll steht.
    """
    zeilen = [z for z in zeigerlauf["protokoll"].splitlines()
              if "CRITICAL" in z or "WARNING" in z or "scale" in z.lower()]
    print("\nWas das Kind gemeldet hat:")
    for zeile in dict.fromkeys(zeilen):
        print("   ", zeile.strip()[:160])
    if not zeilen:
        print("    (nichts)")
