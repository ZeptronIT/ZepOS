# SPDX-License-Identifier: GPL-3.0-or-later
"""Bewegtaufnahmen der erzeugten Oberflaeche - dasselbe wie shoot.py, ueber die Zeit.

    .venv/bin/python -m tests.render.film [--out VERZEICHNIS] [--breite N]
                                          [--takt N] [--nur-bilder]

WAS ENTSTEHT
    dateien-finden.gif      Ein Ablauf, vom Ruhezustand bis zum offenen
                            Dateiverwalter: der Starter geht auf, jemand
                            tippt "datei", die Trefferliste wird kuerzer,
                            Eingabetaste, das Fenster steht.
    messwerte.txt           Was dabei GEMESSEN wurde - Bildrate, Abstand
                            zwischen zwei Bildern, Gesamtlaenge, Groesse.
                            Kein Wort davon ist geschaetzt.
    bilder/                 Jedes Einzelbild, unveraendert, mit seinem
                            Zeitstempel im Namen. Wer die Aufnahme auf
                            Personenbezug pruefen will, prueft DIESE
                            Dateien und nicht das fertige GIF.

WIE AUFGENOMMEN WIRD, UND WARUM SO
    Es gibt auf dieser Maschine keinen Rekorder fuer wlr-screencopy
    (wf-recorder fehlt, gifski fehlt). Es gibt aber grim, und grim IST
    ein Rekorder mit einem Bild Laenge. Ein Nebenlaeufer zieht in festem
    Takt Einzelbilder, notiert zu jedem die Uhrzeit, und ffmpeg baut aus
    Bildern plus Zeiten das GIF. Die Bildrate ist damit nicht gesetzt,
    sondern GEMESSEN: was der Takt nicht schafft, steht als kleinere Zahl
    in messwerte.txt.

WAS DIE AUFNAHME NICHT ZEIGT, UND ZWAR ABSICHTLICH
    Den Tastendruck SUPER+SPACE. Er laesst sich hier nicht ausloesen -
    GEMESSEN am 24.08.2026, siehe _WARUM_KEIN_TASTENDRUCK weiter unten.
    Der Starter wird deshalb mit genau dem Befehl geoeffnet, den die
    Compositor-Haelfte des Plugins auf diese Taste hin ausfuehrt. Was
    danach kommt - das Tippen, die Eingabetaste - sind echte Tasten.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.adopted_plugin_source import _apply_unified_patch   # noqa: E402
from tests.render import desktop_session as session            # noqa: E402

SRC = ROOT / "src"

# DER GANZE LAUF LIEGT AUSSERHALB VON /tmp, UND DAS IST KEINE VORLIEBE
#
#     hyprlaunch-ui traegt seinen Steuersocket als Literal im Programm:
#     /tmp/hyprlaunch-ui.sock (src/main_ui.cpp). Beim Start UNLINKT es
#     diesen Pfad und legt seinen eigenen an; mit einem Befehl auf der
#     Zeile schickt es den Befehl vorher an den, der schon da ist.
#
#     GEMESSEN am 24.08.2026: auf DIESER Maschine haengt an diesem Pfad
#     der laufende Starter des Nutzers (eigene Sitzung, eigenes
#     /run/user/1000). Ein Aufruf von hyprlaunch-ui aus einem Bildlauf
#     heraus wuerde also entweder SEIN Fenster aufmachen oder ihm den
#     Socket unter den Fuessen wegloeschen. Beides ist genau das, was
#     dieser Messstand seit dem ersten Tag nicht tun darf.
#
#     Der Starter laeuft deshalb in einem eigenen Mount-Namensraum mit
#     einem eigenen /tmp (_starter_kommando). Damit dieser private /tmp
#     nicht die Sitzung selbst verdeckt, liegen Laufzeitverzeichnis,
#     Bauplatz und Programm unter /dev/shm - auch ein tmpfs, also
#     genauso schnell, aber nicht der Pfad, den das Literal nennt.
AUSSERHALB_TMP = Path("/dev/shm")

# Der Takt, in dem Bilder gezogen werden. GEMESSEN am 24.08.2026 auf
# diesem Schirm: ein `grim -l 1` auf 1920x1080 braucht 64 ms, ein
# `grim -l 6` 114 ms. Bei 100 ms Takt bleibt also Luft, und die
# tatsaechlich erreichte Rate steht hinterher in messwerte.txt.
TAKT_MS = 100

# PNG-Stufe 1 und nicht 6: 64 statt 114 ms je Bild, 384 statt 331 kB
# Datei. Die Datei ist ein Zwischenschritt, die Millisekunde nicht.
PNG_STUFE = "1"

# Wie lange die Oberflaeche Zeit bekommt, bevor aufgenommen wird -
# wortgleich zu shoot.py, aus demselben Grund.
SETTLE = 6.0

# Die Vorlagen, die diese Aufnahme zusaetzlich zu den AGS-Vorlagen
# braucht, und wohin generate_config.sh sie legt (abgelesen an den
# case-Zweigen `hyprlaunch-config`, `hyprlaunch-style`,
# `gtk4-settings-config`, `gtk4-colors-config` in src/generate_config.sh).
NEBENVORLAGEN = {
    "templates/hyprlaunch-config.template": "hyprlaunch/config",
    "styles/hyprlaunch-style.template": "hyprlaunch/style.css",
    "templates/gtk4-settings-config.template": "gtk-4.0/settings.ini",
    "templates/gtk4-colors-config.template": "gtk-4.0/gtk.css",
}

# Der Anwendungsstarter, aus dem angehefteten Commit und dem Patch dieses
# Repos - dieselben zwei Dateien, aus denen packaging/zepos-hyprlaunch
# das Paket baut.
STARTER_TARBALL = (ROOT / "packaging" / "zepos-hyprlaunch"
                   / "hyprlaunch-24e5c8b82f96f87ac25000353e36a8b17ced4b00.tar.gz")
STARTER_PATCH = (ROOT / "packaging" / "zepos-hyprlaunch"
                 / "zepos-hyprlaunch.patch")


# _WARUM_KEIN_TASTENDRUCK
#
#     Der geschachtelte Compositor faehrt mit einer minimalen
#     hyprland.conf (Session.start in tests/render/desktop_session.py):
#     Monitor, misc, Animationen aus, decoration, layerrule. KEINE
#     einzige bind-Zeile. Das ist kein Versehen - die Messsitzungen
#     brauchen Geometrie und Glas, keine Tastatur -, aber es heisst,
#     dass SUPER+SPACE dort nichts tut.
#
#     Zuschalten laesst sich das zur Laufzeit, ohne eine bestehende
#     Sitzung anzufassen: `hyprctl keyword bind ...`. GEMESSEN am
#     24.08.2026 wurden so drei Bindungen registriert und in
#     `hyprctl -j binds` als (modmask, Taste, Dispatcher) wiedergefunden:
#
#         (0, 'F9', 'exec')  (64, 'SPACE', 'exec')  (12, 'T', 'exec')
#
#     Ausgeloest hat KEINE davon. Sechs Varianten von wtype - Taste
#     allein, Modifikator als Zustand, Modifikator als echte Taste,
#     jeweils mit und ohne Pausen dazwischen - liefen alle mit
#     Rueckgabewert 0 durch, und die Quittungsdatei blieb jedes Mal
#     leer. `hyprctl dispatch exec` desselben Befehls schreibt sie
#     sofort; an den Bindungen und am Ausfuehren liegt es also nicht.
#
#     Dass die Tasten ankommen, ist im selben Lauf gemessen: derselbe
#     wtype-Aufruf tippt "datei" in das Suchfeld des Starters, und der
#     Treffer wechselt. Tasten aus einer virtuellen Tastatur erreichen
#     also den fokussierten Client, aber nicht den Bindungsabgleich des
#     Compositors.
#
#     Ob Hyprland Bindungen fuer zwp_virtual_keyboard_v1 grundsaetzlich
#     nicht auswertet oder ob es an dieser Verschachtelung liegt, ist
#     hier NICHT entscheidbar: die Gegenprobe waere ein Druck auf die
#     echte Tastatur, und die gehoert dem Menschen, der nebenan
#     arbeitet.
#
#     Die Aufnahme faelscht den Tastendruck deshalb nicht. Sie ruft den
#     Starter mit dem Befehl auf, den das Plugin auf diese Taste hin
#     ausfuehrt - `hyprlaunch-ui --toggle`, woertlich aus
#     sendUICommand() in src/Globals.cpp des angehefteten Commits.


def _kommando(*teile: str) -> list[str]:
    return [str(teil) for teil in teile]


def starter_bauen(ziel: Path) -> Path:
    """hyprlaunch-ui bauen - aus dem Tarball und dem Patch dieses Repos.

    NICHT das Programm der Maschine, und das ist eine Entscheidung.
    Auf dieser Maschine liegt unter ~/.local/bin/hyprlaunch-ui ein
    Programm unbekannter Herkunft (es ist der laufende Starter des
    Nutzers). Was auf dem Bild zu sehen sein soll, ist das, was
    packaging/zepos-hyprlaunch baut: der angeheftete Commit plus der
    Patch, der im Repository liegt.

    Gebaut wird NUR das eigenstaendige GTK4-Programm. Die andere Haelfte
    - hyprlaunch.so, das Objekt im Compositor - bleibt ungebaut: es
    traegt zu dieser Aufnahme nur die Tastenbindung bei, und die feuert
    hier ohnehin nicht (siehe _WARUM_KEIN_TASTENDRUCK).
    """
    assert STARTER_TARBALL.is_file(), f"{STARTER_TARBALL} fehlt"
    assert STARTER_PATCH.is_file(), f"{STARTER_PATCH} fehlt"

    ziel.mkdir(parents=True, exist_ok=True)
    with tarfile.open(STARTER_TARBALL, "r:gz") as tar:
        tar.extractall(ziel, filter="data")
    entries = [pfad for pfad in ziel.iterdir() if pfad.is_dir()]
    assert len(entries) == 1, f"unerwarteter Tarball-Aufbau: {entries}"
    baum = entries[0]
    _apply_unified_patch(STARTER_PATCH.read_text(encoding="utf-8"), baum)

    for schritt in (
            _kommando("cmake", "-S", baum, "-B", baum / "build", "-G", "Ninja",
                      "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_INSTALL_PREFIX=/usr",
                      "-DCMAKE_SKIP_RPATH=ON"),
            _kommando("cmake", "--build", baum / "build",
                      "--target", "hyprlaunch-ui")):
        ergebnis = subprocess.run(schritt, capture_output=True, text=True,
                                  timeout=900)
        assert ergebnis.returncode == 0, (
            f"{schritt[0]} ist gescheitert:\n{ergebnis.stdout}{ergebnis.stderr}")

    programm = baum / "build" / "hyprlaunch-ui"
    assert programm.is_file(), f"{programm} ist nicht entstanden"
    assert not str(programm).startswith("/tmp/"), (
        f"{programm} liegt unter /tmp und waere im eigenen /tmp des "
        "Starters unsichtbar")
    return programm


def _starter_kommando(programm: Path, befehl: str) -> list[str]:
    """Der Starter, in einem eigenen /tmp.

    DREI BEDINGUNGEN, MIT `&&` VERKETTET, DAMIT DER FEHLERFALL NICHTS TUT
        Faellt eine davon aus, wird das Programm NICHT ausgefuehrt. Ein
        Aufruf, der ohne eigenes /tmp durchrutscht, waere ein Aufruf
        gegen den Socket des Nutzers.

          1. mount -t tmpfs  - ein leeres, privates /tmp
          2. test ! -e ...   - und darin gibt es den Socket nicht mehr
          3. exec            - erst jetzt das Programm

    `--map-root-user` ist noetig und nicht bequem: mount(2) verlangt
    CAP_SYS_ADMIN im Namensraum, und Faehigkeiten ueberleben ein execve
    nur bei uid 0. GEMESSEN am 24.08.2026: mit --map-current-user
    scheitert der Aufruf an "mount darf nur der Administrator
    verwenden". Auf dem Bild ist davon nichts zu sehen - der Starter
    zeigt keinen Kontonamen -, und HOME zeigt ohnehin in das
    Wegwerfverzeichnis dieses Laufs.
    """
    innen = (f"mount -t tmpfs none /tmp && "
             f"test ! -e /tmp/hyprlaunch-ui.sock && "
             f"exec {programm} {befehl}")
    return ["unshare", "--mount", "--map-root-user", "sh", "-c", innen]


def anwendungsverzeichnis(ziel: Path) -> tuple[Path, list[str]]:
    """Ein XDG_DATA_DIRS, das NUR die ausgelieferten Anwendungen fuehrt.

    WARUM DAS SEIN MUSS
        Der Starter liest jeden Anwendungseintrag der Maschine
        (g_app_info_get_all in src/AppDiscovery.cpp). GEMESSEN am
        24.08.2026 im ersten Lauf: auf "datei" antwortete er mit
        "Dateien" UND "Dateimanager Thunar" - ein Programm, das ZepOS
        nicht ausliefert und das nur sagt, was auf DIESER Maschine
        installiert ist. Dieselbe Falle hat am selben Tag zwei eigene
        Programme des Nutzers in die Trefferliste gehoben.

    WIE
        Ein Verzeichnis, das auf alles unter /usr/share zeigt - damit
        GTK sein Symbolthema, seine Schriften und seine Uebersetzungen
        behaelt - und nur `applications` durch ein eigenes ersetzt.
        Darin liegen genau die Eintraege der Pakete aus
        src/apps.shipped(), nachgeschlagen mit `pacman -Ql`. Was auf
        dieser Maschine nicht installiert ist, fehlt dann auch in der
        Liste; das ist richtig so und steht in messwerte.txt.
    """
    wurzel = ziel / "anwendungsdaten"
    eintraege = wurzel / "applications"
    eintraege.mkdir(parents=True, exist_ok=True)
    for pfad in sorted(Path("/usr/share").iterdir()):
        if pfad.name == "applications":
            continue
        verweis = wurzel / pfad.name
        if not verweis.exists():
            verweis.symlink_to(pfad)

    sys.path.insert(0, str(SRC))
    try:
        import apps
        namen = apps.shipped(SRC)
    finally:
        sys.path.remove(str(SRC))

    gefunden: list[str] = []
    for name in namen:
        ergebnis = subprocess.run(["pacman", "-Ql", name], capture_output=True,
                                  text=True, timeout=60)
        if ergebnis.returncode != 0:
            continue
        for zeile in ergebnis.stdout.splitlines():
            datei = zeile.split(" ", 1)[-1].strip()
            if (datei.startswith("/usr/share/applications/")
                    and datei.endswith(".desktop")):
                quelle = Path(datei)
                if not quelle.is_file():
                    continue
                (eintraege / quelle.name).symlink_to(quelle)
                gefunden.append(f"{name}: {quelle.name}")
    assert gefunden, (
        "kein einziger Anwendungseintrag der ausgelieferten Pakete gefunden - "
        "der Starter waere leer, und ein leerer Starter zeigt nichts")
    return wurzel, gefunden


def benutzerordner(home: Path) -> list[str]:
    """Die XDG-Ordner im Wegwerf-Home anlegen, mit dem echten Werkzeug.

    Ohne sie steht der Dateiverwalter auf einem leeren Ordner, und der
    Ablauf endet auf nichts. `xdg-user-dirs-update` ist das Programm,
    das sie auf jeder frischen Anmeldung anlegt; die Namen kommen damit
    aus der Sprache und nicht aus dieser Datei.
    """
    umgebung = {
        "PATH": os.environ.get("PATH", "/usr/bin"),
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "LANG": session.SESSION_LOCALE,
        "LC_ALL": session.SESSION_LOCALE,
    }
    subprocess.run(["xdg-user-dirs-update", "--force"], env=umgebung,
                   capture_output=True, text=True, timeout=60)
    return sorted(pfad.name for pfad in home.iterdir() if pfad.is_dir()
                  and not pfad.name.startswith("."))


def nachtrag_ags_vorlagen(ags: Path) -> list[str]:
    """Jede ags-Vorlage erzeugen, die RENDERED noch nicht kennt.

    WARUM DAS HIER STEHT UND NICHT IN DER TABELLE
        RENDERED in tests/render/desktop_session.py ist eine ABSCHRIFT
        der case-Zweige von src/generate_config.sh, und Abschriften
        laufen aus. tests/src/test_render_table.py bewacht genau das
        und ist rot, sobald ein Ziel fehlt.

        GEMESSEN am 24.08.2026: `ags-bluetooth-agent` stand im Erzeuger
        und in app.ts, aber nicht in der Tabelle, und `ags bundle` brach
        mit `Could not resolve "./widget/BluetoothAgent"` ab. Das ist
        fremde, laufende Arbeit an einer geteilten Datei - sie zu
        reparieren hiesse, einem anderen in die Zeile zu schreiben.

        Diese Funktion liest deshalb DIESELBE Quelle, aus der die
        Tabelle abgeschrieben ist, und traegt nach, was dort fehlt. Sie
        aendert an keiner bestehenden Messsitzung etwas: sie legt
        Dateien in den Bauplatz DIESES Laufs. Ist die Tabelle wieder
        vollstaendig, findet sie nichts und tut nichts.
    """
    text = (SRC / "generate_config.sh").read_text(encoding="utf-8")
    ziele: dict[str, tuple[str, str]] = {}
    aktuell: str | None = None
    ordner: str | None = None
    for zeile in text.splitlines():
        zweig = re.match(r"\s*(ags-[a-z0-9-]+)\)\s*$", zeile)
        if zweig:
            aktuell, ordner = zweig.group(1), None
            continue
        if not aktuell:
            continue
        pfad = re.search(r'CONFIG_DIR="\$ZEPOS_OUTPUT_ROOT/ags/?([^"]*)"', zeile)
        if pfad:
            ordner = pfad.group(1)
            continue
        datei = re.search(r'CONFIG_FILE="([^"]+)"', zeile)
        if datei:
            if ordner is not None and datei.group(1).endswith((".ts", ".tsx")):
                ziele[aktuell] = (ordner, datei.group(1))
            aktuell = None

    prozessor = session._processor()
    nachgetragen: list[str] = []
    for ziel, (ordner_name, datei_name) in sorted(ziele.items()):
        vorlage = f"templates/{ziel}.template"
        if vorlage in session.RENDERED:
            continue
        quelle = SRC / vorlage
        if not quelle.is_file():
            continue
        ausgabe = ags / ordner_name / datei_name
        ausgabe.parent.mkdir(parents=True, exist_ok=True)
        prozessor.apply_template(quelle, ausgabe)
        nachgetragen.append(f"{vorlage} -> {ordner_name}/{datei_name}")
    return nachgetragen


def bus_umgebung(live: session.Session, **zusatz: str) -> list[str]:
    """Dem EIGENEN Sitzungsbus sagen, in welcher Sitzung er startet.

    WARUM DAS OHNE DIESEN SCHRITT NICHT GEHT, UND ES IST GEMESSEN
        org.gnome.Nautilus.desktop traegt `DBusActivatable=true`. GIOs
        `g_app_info_launch` startet so einen Eintrag deshalb NICHT
        selbst, sondern laesst ihn vom Sitzungsbus aktivieren - und der
        Bus gibt dem Kind seine EIGENE Umgebung mit.

        Diesen Bus startet desktop_session.start_bus() mit genau drei
        Variablen (PATH, HOME, XDG_RUNTIME_DIR), und das ist dort auch
        richtig so: er soll nichts von der Sitzung des Nutzers erben.
        Nur hat ein so gestartetes Nautilus dann kein WAYLAND_DISPLAY.

        GEMESSEN am 24.08.2026: der erste Lauf drueckte die Eingabetaste,
        der Starter schloss sich - und es kam kein Fenster. Die Aufnahme
        endete auf einem leeren Schreibtisch, also auf nichts.

    WAS HIER PASSIERT, PASSIERT AUF JEDER ECHTEN ANMELDUNG
        `dbus-update-activation-environment` ist genau das Programm, das
        eine Sitzung beim Start aufruft, um dem Bus ihre Variablen zu
        geben. Aufgerufen wird es gegen den EIGENEN Bus (die Adresse
        steht in der Umgebung, die refuse_the_real_session() geprueft
        hat) und mit einer namentlichen Liste - nicht mit `--all`, damit
        nichts aus der Umgebung des Aufrufers mitwandert.
    """
    umgebung = live.environment(**zusatz)
    namen = ("WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "HOME", "XDG_CONFIG_HOME",
             "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_DATA_DIRS",
             "GDK_BACKEND", "LANG", "LC_ALL", "PATH",
             "HYPRLAND_INSTANCE_SIGNATURE", "NO_AT_BRIDGE", "GTK_A11Y")
    paare = [f"{name}={umgebung[name]}" for name in namen if name in umgebung]
    ergebnis = subprocess.run(
        ["dbus-update-activation-environment", *paare],
        env=umgebung, capture_output=True, text=True, timeout=60)
    assert ergebnis.returncode == 0, (
        "der eigene Bus hat die Umgebung nicht angenommen:\n"
        + ergebnis.stdout + ergebnis.stderr)
    return paare


def nur_ein_schirm(live: session.Session) -> list[str]:
    """Den Ausgang des Wirtsfensters abschalten - EIN Schirm, wie bei einem Menschen.

    WARUM, UND ES IST AN EINEM FEHLER GEMESSEN
        Der geschachtelte Compositor hat zwei Ausgaenge: den headless-
        Ausgang, der abgebildet wird (1920x1080), und WAYLAND-1, das
        Fenster beim Wirt. Dessen Groesse bestimmt der Wirt; GEMESSEN am
        24.08.2026 war es 931x521.

        LauncherRenderer::fittingHeight() im Starter sucht den
        KUERZESTEN aller Monitore und leitet daraus ab, wie viele
        Trefferzeilen das Fenster hoch sein darf. Der kuerzeste war
        dieses 521 Pixel hohe Wirtsfenster, und der Starter zeigte
        deshalb ZWEI Zeilen - obwohl sieben Anwendungen aufloesen.

        Das steht nicht nur in dieser Aufnahme: `docs/bilder/starter.webp`
        im Hauptzweig zeigt denselben zweizeiligen Starter, aus demselben
        Grund. Es ist ein Artefakt des Messstands und kein Zustand, den
        irgendein Nutzer je sieht.

        Mit `monitor = WAYLAND-1, disable` bleibt genau ein Ausgang
        uebrig - GEMESSEN danach: sechs Zeilen statt zwei. Das ist keine
        Schoenung, sondern das Entfernen einer Kulisse, die nur dieser
        Aufbau hat.

    NUR IN DIESER SITZUNG, UND VOR DER OBERFLAECHE
        Ueber `hyprctl keyword`, also zur Laufzeit - keine bestehende
        Messsitzung aendert sich davon. Vor `shell()`, damit die
        Oberflaeche gar nicht erst ein zweites Fenster je Ausgang baut.
    """
    vorher = [m["name"] for m in live.hyprctl_json("monitors") or []]
    fremde = [name for name in vorher if name != live.output]
    for name in fremde:
        ergebnis = live.hyprctl("keyword", "monitor", f"{name}, disable")
        assert ergebnis.returncode == 0, (
            f"{name} liess sich nicht abschalten: {ergebnis.stderr}")
    time.sleep(1.5)
    nachher = [m["name"] for m in live.hyprctl_json("monitors") or []]
    assert nachher == [live.output], (
        f"nach dem Abschalten stehen noch {nachher} statt nur {live.output}")
    return [f"abgeschaltet: {name}" for name in fremde]


def _general_block() -> list[tuple[str, str]]:
    """Der `general`-Block aus der echten Vorlage, als Schluessel/Wert.

    Er fehlt in der Sitzung von desktop_session.py, und fuer ein
    Standbild von Leiste und Fuss braucht ihn auch niemand: beide sind
    Layer-Flaechen, und Layer-Flaechen kennen keine Fensterabstaende.
    Eine Aufnahme mit einem FENSTER darin ist der erste Fall, in dem es
    auffaellt - ohne diese Zahlen klebte der Dateiverwalter randlos am
    Schirm, und das waere ein Schreibtisch, den ZepOS nicht ausliefert.

    Gesetzt wird zur Laufzeit, mit `hyprctl keyword`, also nur in DIESER
    Sitzung. Die Vorlage selbst wird gelesen, nicht angefasst.
    """
    prozessor = session._processor()
    with tempfile.TemporaryDirectory(prefix="zepfilm-hypr-") as platz:
        erzeugt = Path(platz) / "hyprland.conf"
        prozessor.apply_template(
            SRC / "templates" / "hyprland-universal-config.template", erzeugt)
        text = erzeugt.read_text(encoding="utf-8")

    werte: list[tuple[str, str]] = []
    tiefe = 0
    for zeile in text.splitlines():
        if tiefe == 0 and zeile.startswith("general {"):
            tiefe = 1
            continue
        if tiefe:
            tiefe += zeile.count("{") - zeile.count("}")
            if tiefe == 0:
                break
            blank = zeile.strip()
            if not blank or blank.startswith("#") or "=" not in blank:
                continue
            schluessel, wert = blank.split("=", 1)
            werte.append((schluessel.strip(), wert.strip()))
    assert werte, ("der general-Block steht nicht mehr in "
                   "hyprland-universal-config.template")
    return werte


class Aufnahme:
    """Einzelbilder in festem Takt, mit der Uhrzeit zu jedem.

    Ein eigener Faden, damit das Drehbuch im Hauptfaden weiterlaeuft.
    Der Faden misst NICHT nach, ob er den Takt haelt - er notiert, wann
    er ein Bild gezogen hat, und die Auswertung rechnet hinterher aus,
    was daraus geworden ist. Ein Rekorder, der seine eigene Bildrate
    behauptet, waere eine Zahl ohne Deckung.
    """

    def __init__(self, live: session.Session, ordner: Path,
                 takt_ms: int = TAKT_MS) -> None:
        self.live = live
        self.ordner = ordner
        self.takt = takt_ms / 1000.0
        self.bilder: list[tuple[float, Path]] = []
        self.marken: list[tuple[float, str]] = []
        self._laeuft = False
        self._faden: threading.Thread | None = None
        self._start = 0.0
        self._umgebung: dict[str, str] = {}

    def marke(self, text: str) -> None:
        """Was gerade passiert, mit Zeitstempel - fuer messwerte.txt."""
        self.marken.append((time.monotonic() - self._start, text))

    def __enter__(self) -> "Aufnahme":
        self.ordner.mkdir(parents=True, exist_ok=True)
        self._umgebung = self.live.environment()
        # Einmal, nicht je Bild: Hyprlands eigene Einblendungen wegraeumen.
        self.live.hyprctl("dismissnotify")
        self._laeuft = True
        self._start = time.monotonic()
        self._faden = threading.Thread(target=self._lauf, daemon=True)
        self._faden.start()
        return self

    def __exit__(self, *_fehler) -> None:
        self._laeuft = False
        if self._faden:
            self._faden.join(timeout=30)

    def _lauf(self) -> None:
        nummer = 0
        while self._laeuft:
            begonnen = time.monotonic()
            pfad = self.ordner / f"bild-{nummer:05d}.png"
            ergebnis = subprocess.run(
                ["grim", "-l", PNG_STUFE, "-o", self.live.output, str(pfad)],
                env=self._umgebung, capture_output=True, text=True, timeout=60)
            if ergebnis.returncode != 0 or not pfad.is_file():
                # Nicht abbrechen: ein verlorenes Bild ist eine Luecke in
                # der Aufnahme, ein Abbruch waere die ganze Aufnahme.
                self.marken.append((begonnen - self._start,
                                    f"BILD VERLOREN: {ergebnis.stderr.strip()}"))
                time.sleep(self.takt)
                continue
            self.bilder.append((begonnen - self._start, pfad))
            nummer += 1
            rest = self.takt - (time.monotonic() - begonnen)
            if rest > 0:
                time.sleep(rest)

    # -- Auswertung --------------------------------------------------

    def messwerte(self) -> dict:
        assert len(self.bilder) >= 2, "weniger als zwei Bilder"
        zeiten = [zeit for zeit, _ in self.bilder]
        abstaende = [b - a for a, b in zip(zeiten, zeiten[1:])]
        laenge = zeiten[-1] - zeiten[0]
        return {
            "bilder": len(self.bilder),
            "laenge_s": laenge,
            "bilder_je_sekunde": (len(self.bilder) - 1) / laenge if laenge else 0,
            "abstand_ms_min": min(abstaende) * 1000,
            "abstand_ms_max": max(abstaende) * 1000,
            "abstand_ms_mittel": sum(abstaende) / len(abstaende) * 1000,
            "verlorene_bilder": sum(1 for _, text in self.marken
                                    if text.startswith("BILD VERLOREN")),
        }


def gif_bauen(bilder: list[tuple[float, Path]], ziel: Path, breite: int,
              takt_hz: float) -> list[str]:
    """Aus Einzelbildern und ihren Zeiten ein GIF, mit eigener Farbtabelle.

    ZWEI DURCHGAENGE, UND DER ERSTE IST DER, DER DIE GROESSE MACHT
        `palettegen` rechnet EINE Farbtabelle fuer genau diese Aufnahme
        aus, `paletteuse` malt damit. Bei einer dunklen Oberflaeche mit
        wenigen Farben ist das der groesste Hebel, den es gibt - die
        Vorgabe von GIF waere eine feste Tabelle aus 216 Websicherheits-
        farben, und in der kommt kein einziger Ton dieses Schreibtischs
        vor.

    DIE ZEITEN KOMMEN AUS DER MESSUNG UND NICHT AUS EINER ANNAHME
        Die concat-Liste traegt je Bild die GEMESSENE Dauer bis zum
        naechsten. Wo der Takt gestolpert ist, steht die laengere Dauer
        drin; das GIF laeuft dadurch so schnell ab wie die Sitzung
        wirklich war und nicht so schnell, wie der Takt es vorhatte.
    """
    liste = ziel.parent / "bilder.concat"
    zeilen = []
    for nummer, (zeit, pfad) in enumerate(bilder):
        naechste = (bilder[nummer + 1][0] if nummer + 1 < len(bilder)
                    else zeit + 1.0 / takt_hz)
        # ABSOLUT, und das ist gemessen: der concat-Leser loest relative
        # Pfade gegen das Verzeichnis der LISTE auf, nicht gegen das
        # Arbeitsverzeichnis. Mit relativen Pfaden suchte ffmpeg
        # out/film/out/film/bilder/bild-00000.png.
        zeilen.append(f"file '{pfad.resolve()}'")
        zeilen.append(f"duration {max(naechste - zeit, 0.01):.4f}")
    zeilen.append(f"file '{bilder[-1][1].resolve()}'")   # die letzte zweimal
    liste.write_text("\n".join(zeilen) + "\n", encoding="utf-8")

    tabelle = ziel.parent / "farbtabelle.png"
    skalierung = f"scale={breite}:-1:flags=lanczos"
    protokoll: list[str] = []
    for schritt in (
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(liste),
             "-vf", f"{skalierung},palettegen=stats_mode=diff", str(tabelle)],
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(liste),
             "-i", str(tabelle), "-lavfi",
             f"{skalierung}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5"
             ":diff_mode=rectangle",
             "-loop", "0", "-f", "gif", str(ziel)]):
        ergebnis = subprocess.run(schritt, capture_output=True, text=True,
                                  timeout=900)
        assert ergebnis.returncode == 0, (
            f"ffmpeg ist gescheitert:\n{ergebnis.stderr[-2000:]}")
        protokoll.append(" ".join(schritt))
    return protokoll


def _tippen(live: session.Session, text: str, je_zeichen_ms: int = 90) -> None:
    """Tippen wie ein Mensch - Zeichen fuer Zeichen, mit Pause dazwischen."""
    subprocess.run(["wtype", "-d", str(je_zeichen_ms), text],
                   env=live.environment(), check=True, timeout=60)


def _taste(live: session.Session, name: str) -> None:
    subprocess.run(["wtype", "-k", name], env=live.environment(), check=True,
                   timeout=30)


def drehbuch_dateien_finden(live: session.Session, starter: Path,
                            build: Path, film: Aufnahme,
                            daten: Path) -> None:
    """"Wie finde ich meine Dateien" - ein Ablauf, von vorn bis zu Ende.

    Die Zeiten sind das, was ein Mensch braucht, und nicht das, was
    schnell aussieht. Wer eine Vorfuehrung in halber Geschwindigkeit
    schneidet, zeigt eine Bedienung, die es nicht gibt.
    """
    film.marke("Ruhezustand: Tapete, Leiste, Home, Fuss")
    time.sleep(2.0)

    film.marke("Starter auf - derselbe Befehl, den SUPER+SPACE ausfuehrt")
    prozess = live.spawn(_starter_kommando(starter, "--toggle"),
                         log=Path(live.runtime) / "starter.log",
                         XDG_CONFIG_HOME=str(build),
                         XDG_DATA_DIRS=str(daten))
    time.sleep(2.5)
    flaechen = live.layers()
    assert "hyprlaunch" in flaechen, (
        "der Starter liegt nicht auf dem abgebildeten Schirm: "
        + str(sorted(flaechen)))
    assert prozess.poll() is None, "der Starter ist sofort wieder weg"

    film.marke('getippt: "datei"')
    _tippen(live, "datei", je_zeichen_ms=140)
    time.sleep(2.0)

    film.marke("Eingabetaste - der Dateiverwalter startet")
    _taste(live, "Return")
    time.sleep(2.0)

    fenster = live.hyprctl_json("clients") or []
    film.marke("Fenster auf dem Schirm: "
               + str([f["class"] for f in fenster] if fenster else "keins"))
    assert fenster, ("nach der Eingabetaste steht kein Fenster auf dem "
                     "Schirm - die Aufnahme endete auf nichts")
    time.sleep(3.5)
    film.marke("Ende")


def required_tools() -> list[str]:
    fehlend = list(session.required_tools())
    for werkzeug in ("wtype", "ffmpeg", "cmake", "ninja", "unshare",
                     "xdg-user-dirs-update", "pacman"):
        if shutil.which(werkzeug) is None:
            fehlend.append(werkzeug)
    return fehlend


def herkunft() -> list[str]:
    """Aus WELCHEM Baum diese Aufnahme stammt - wortgleich zu shoot.py."""
    def git(*argumente: str) -> str:
        try:
            return subprocess.run(["git", "-C", str(ROOT), *argumente],
                                  capture_output=True, text=True,
                                  timeout=30).stdout.strip()
        except (OSError, subprocess.SubprocessError):        # pragma: no cover
            return "?"

    zeilen = [f"Stand: {git('rev-parse', '--short', 'HEAD')} "
              f"auf {git('rev-parse', '--abbrev-ref', 'HEAD')}"]
    schmutzig = [zeile for zeile in git("status", "--short").splitlines()
                 if zeile]
    if schmutzig:
        zeilen.append("Nicht eingecheckte Aenderungen im Baum, aus dem diese "
                      "Aufnahme stammt:")
        zeilen.extend(f"    {zeile}" for zeile in schmutzig)
    return zeilen


def main() -> int:
    zerleger = argparse.ArgumentParser(description=__doc__)
    zerleger.add_argument("--out", type=Path, default=ROOT / "out" / "film")
    zerleger.add_argument("--breite", type=int, default=960,
                          help="Breite des GIF in Bildpunkten")
    zerleger.add_argument("--takt", type=int, default=TAKT_MS,
                          help="Abstand zwischen zwei Bildern in ms")
    zerleger.add_argument("--nur-bilder", action="store_true",
                          help="kein GIF bauen, nur die Einzelbilder")
    argumente = zerleger.parse_args()

    fehlend = required_tools()
    if fehlend:
        print("Diese Programme fehlen und ohne sie gibt es keine Aufnahme: "
              + ", ".join(fehlend), file=sys.stderr)
        return 1

    # Siehe AUSSERHALB_TMP: alles, was der Starter sehen muss, liegt
    # ausserhalb von /tmp.
    tempfile.tempdir = str(AUSSERHALB_TMP)

    out = argumente.out
    out.mkdir(parents=True, exist_ok=True)
    build = Path(tempfile.mkdtemp(prefix="zepfilm-bau-"))
    bericht: list[str] = herkunft()
    bericht.append(f"Bauplatz: {build}")

    print(f"Bauplatz: {build}")
    starter = starter_bauen(build / "starter")
    bericht.append(f"Starter: {starter} (aus {STARTER_TARBALL.name} + "
                   f"{STARTER_PATCH.name})")

    ags = session.render_configuration(build)
    nachgetragen = nachtrag_ags_vorlagen(ags)
    if nachgetragen:
        bericht.append("Vorlagen, die RENDERED noch nicht kennt und die "
                       "dieser Lauf selbst nachgetragen hat:")
        bericht.extend(f"    {zeile}" for zeile in nachgetragen)
    session.bundle(ags, build)
    prozessor = session._processor()
    for vorlage, ausgabe in NEBENVORLAGEN.items():
        ziel = build / ausgabe
        ziel.parent.mkdir(parents=True, exist_ok=True)
        prozessor.apply_template(SRC / vorlage, ziel)

    daten, eintraege = anwendungsverzeichnis(build)
    bericht.append(f"XDG_DATA_DIRS: {daten}")
    bericht.append("Anwendungseintraege, die der Starter ueberhaupt sehen "
                   f"kann ({len(eintraege)}):")
    bericht.extend(f"    {zeile}" for zeile in eintraege)

    live = session.Session(1920, 1080)
    bilder = out / "bilder"
    if bilder.is_dir():
        shutil.rmtree(bilder)
    try:
        live.start()
        live.start_bus()
        bericht.append("Umgebung, die der eigene Bus fuer Aktivierungen "
                       "bekommen hat:")
        # PATH bleibt aus dem BERICHT draussen - er traegt das
        # Heimatverzeichnis des Menschen, der diesen Lauf gestartet hat,
        # und dieser Bericht wird gelesen und zitiert. Dem Bus wird er
        # trotzdem gegeben; ohne ihn findet eine Aktivierung ihr
        # Programm nicht.
        bericht.extend(f"    {paar}" for paar in bus_umgebung(
            live, XDG_CONFIG_HOME=str(build), XDG_DATA_DIRS=str(daten),
            HYPRLAND_INSTANCE_SIGNATURE=live.signature() or "")
            if not paar.startswith("PATH="))
        session.workspaces_file(build, live.output)
        ordner = benutzerordner(live.home)
        bericht.append(f"Ordner im Wegwerf-Home: {ordner}")
        bericht.extend(f"    {zeile}" for zeile in nur_ein_schirm(live))
        live.wallpaper()

        # Abstaende und Rahmen aus der echten Vorlage - siehe _general_block.
        for schluessel, wert in _general_block():
            ergebnis = live.hyprctl("keyword", f"general:{schluessel}", wert)
            assert ergebnis.returncode == 0, (
                f"general:{schluessel} = {wert} kam nicht an: {ergebnis.stderr}")

        # Zeiger UND Fokus auf den abgebildeten Schirm. Beides noetig, und
        # das ist gemessen: der geschachtelte Compositor hat zwei
        # Ausgaenge, und ohne focusmonitor legte der Starter seine
        # Layer-Flaeche auf den des Wirtsfensters - `hyprctl layers`
        # fuehrte sie unter WAYLAND-1, und auf dem Bild war nichts.
        live.move_cursor(live.width // 2, live.height // 2)
        ergebnis = live.hyprctl("dispatch", "focusmonitor", live.output)
        assert ergebnis.returncode == 0, ergebnis.stderr

        time.sleep(2.0)
        live.shell(build / "zepos-shell.js", build)
        time.sleep(SETTLE)
        flaechen = live.layers()
        assert "zepos-bar" in flaechen and "zepos-dock" in flaechen, (
            "die Oberflaeche steht nicht:\n" + live.read_shell_log())

        with Aufnahme(live, bilder, argumente.takt) as film:
            drehbuch_dateien_finden(live, starter, build, film, daten)

        (out / "shell.log").write_text(live.read_shell_log(), encoding="utf-8")
        starter_log = Path(live.runtime) / "starter.log"
        if starter_log.is_file():
            (out / "starter.log").write_text(
                starter_log.read_text(errors="replace"), encoding="utf-8")
    finally:
        live.stop()

    werte = film.messwerte()
    bericht.append("")
    bericht.append("GEMESSEN AN DER AUFNAHME")
    bericht.append(f"    Takt, der vorgegeben war   {argumente.takt} ms "
                   f"= {1000/argumente.takt:.1f} Bilder/s")
    bericht.append(f"    Bilder                     {werte['bilder']}")
    bericht.append(f"    Laenge                     {werte['laenge_s']:.2f} s")
    bericht.append(f"    Bildrate, erreicht         "
                   f"{werte['bilder_je_sekunde']:.2f} Bilder/s")
    bericht.append(f"    Abstand zwischen Bildern   "
                   f"{werte['abstand_ms_min']:.0f} / "
                   f"{werte['abstand_ms_mittel']:.0f} / "
                   f"{werte['abstand_ms_max']:.0f} ms (min/mittel/max)")
    bericht.append(f"    Verlorene Bilder           {werte['verlorene_bilder']}")
    bericht.append("")
    bericht.append("WAS WANN PASSIERT IST")
    for zeit, text in film.marken:
        bericht.append(f"    {zeit:6.2f} s  {text}")

    if not argumente.nur_bilder:
        ziel = out / "dateien-finden.gif"
        befehle = gif_bauen(film.bilder, ziel, argumente.breite,
                            1000.0 / argumente.takt)
        bericht.append("")
        bericht.append("DAS GIF")
        bericht.append(f"    Breite                     {argumente.breite} px")
        bericht.append(f"    Groesse                    "
                       f"{ziel.stat().st_size} Byte "
                       f"= {ziel.stat().st_size/1024/1024:.2f} MiB")
        pruefsumme = hashlib.sha256(ziel.read_bytes()).hexdigest()
        bericht.append(f"    sha256                     {pruefsumme}")
        bericht.extend(f"    ffmpeg: {befehl}" for befehl in befehle)

    (out / "messwerte.txt").write_text("\n".join(bericht) + "\n",
                                       encoding="utf-8")
    print("\n".join(bericht))
    print(f"\nAufnahme in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
