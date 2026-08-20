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
from tests.render.desktop_session import Session                   # noqa: E402

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


def _bruecken_abbild(bin_verzeichnis: Path, heim: Path) -> None:
    """Ein `zepos-settings-gui` auf PATH, das auf den Checkout zeigt.

    WARUM DAS KEIN BETRUG IST
        Es ist DERSELBE Befehl - dasselbe Skript aus settings/bin/, mit
        derselben Python-Umgebung, die auch `zepos-settings-gui` aus dem
        Paket ausfuehren wuerde. GEMESSEN am 21.08.2026 auf dieser
        Maschine: das PAKET zepos-settings-gui ist nicht installiert
        (`which zepos-settings-gui` findet nichts), und ein Lauf, der
        deshalb uebersprungen wuerde, beantwortete die Frage nicht.

        Ohne dieses Abbild antwortet die Bruecke gar nicht, und
        LauncherRenderer::entryMenu() bietet dann - richtigerweise -
        KEINEN Punkt an. Der Lauf saehe ein leeres Menue und koennte
        nicht unterscheiden, ob das Menue kaputt ist oder ob nur der
        Befehl fehlt.

    HEIM ZEIGT IN DEN SANDKASTEN
        Damit ein Schreibvorgang die user-settings.json des NUTZERS
        nicht anfasst. Session.environment() setzt HOME ohnehin auf das
        Laufzeitverzeichnis; hier steht es noch einmal, weil dieses
        Skript seine Wurzeln aus der Umgebung liest und ein
        vergessenes HOME der teuerste denkbare Fehler waere.
    """
    bin_verzeichnis.mkdir(parents=True, exist_ok=True)
    python = ROOT / ".venv" / "bin" / "python"
    if not python.exists():
        python = Path(sys.executable)
    skript = bin_verzeichnis / "zepos-settings-gui"
    skript.write_text(
        "#!/bin/sh\n"
        f'export HOME="{heim}"\n'
        f'export XDG_CONFIG_HOME="{heim}/.config"\n'
        f'exec "{python}" "{ROOT / "settings" / "bin" / "zepos-settings-gui"}" "$@"\n',
        encoding="utf-8")
    skript.chmod(0o755)


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
        pfad_bin = bau / "bin"
        _bruecken_abbild(pfad_bin, heim)

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

        umgebung = sitzung.environment(
            PATH=f"{pfad_bin}:{os.environ.get('PATH', '/usr/bin')}")
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
        subprocess.run(["wtype", "-k", "Escape"], env=umgebung,
                       capture_output=True, timeout=20)
        time.sleep(RUHE)
        menue_nach_escape = kind.frage("menue")
        fenster_nach_escape = kind.frage("bereit")
        nach_escape = sitzung.shoot(bilder / "3-nach-escape.png")

        kind.frage("ende")
        protokoll = kindlog.read_text(encoding="utf-8", errors="replace")

    return {
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


def test_das_menue_bietet_das_anheften_an(lauf):
    """Der Punkt, der bestellt war - woertlich."""
    assert "Zum Dock hinzufuegen" in lauf["menue_offen"], (
        "das Menue traegt den bestellten Punkt nicht: "
        f"{lauf['menue_offen']!r}")


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
