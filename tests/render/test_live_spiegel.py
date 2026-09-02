# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Installer auf beiden Schirmen - an echtem cage, in Pixeln.

WAS HIER GEMESSEN WIRD UND WARUM ES WOANDERS NICHT GEHT
    tests/iso/test_live_schirme.py fuehrt /usr/local/bin/
    zepos-live-schirme aus und prueft, WELCHE Aufrufe es macht. Ob diese
    Aufrufe dann wirklich ein Bild auf den zweiten Schirm bringen, kann
    es nicht sagen - das ist eine Aussage ueber den Compositor.

    Diese Datei stellt genau diese Frage, an echtem cage: zwei
    Ausgaenge, der ausgelieferte Installer-Aufbau darin, und aufgenommen
    wird ueber cages EIGENES wlr-screencopy, je Ausgang.

    Das geht ohne Wirtssitzung: cage kann auf dem headless-Backend
    starten (WLR_BACKENDS=headless), anders als Hyprland. Nichts hier
    beruehrt die Sitzung des Nutzers - eigenes XDG_RUNTIME_DIR, eigener
    Socket, und beendet wird nur der eigene Prozess.

    UND ES GIBT HIER EINEN BILDBEWEIS, anders als beim
    Anmeldebildschirm. tests/render/test_anmeldung_spiegel.py kann keinen
    haben: ein Hyprland-Spiegel verliert sein wl_output, `grim -o` sagt
    danach "unknown output", und was dort belegt wird, ist die Aussage
    des Compositors ueber sich selbst. Hier wird nicht gespiegelt,
    sondern UEBERLAGERT - beide Ausgaenge bleiben echte Ausgaenge, und
    beide lassen sich abziehen und Byte fuer Byte vergleichen.

WOHER DER CLIENT KOMMT, DEN DAS SKRIPT RUFT
    Im Betrieb ist das wlr-randr aus dem Abbild. Auf der
    Werkstattmaschine lag es am 01.09.2026 nicht, und ohne es uebersprang
    diese Datei vollstaendig - die tragende Behauptung des ganzen Fixes
    war damit von keinem Lauf gedeckt.

    Sie baut ihn deshalb selbst: tests/render/live_schirme_client.c,
    uebersetzt gegen tests/render/wlr-output-management-unstable-v1.xml,
    abgelegt unter dem Namen `wlr-randr` in einem eigenen Verzeichnis,
    das VOR den Suchpfad des Kindes kommt. Das AUSGELIEFERTE Skript
    laeuft dabei unveraendert.

    Was das deckt und was nicht, steht im Kopf der beiden Dateien. Kurz:
    der Compositor-Teil ist gedeckt und kann nicht falsch gruen werden,
    die genaue TEXTFORM des echten wlr-randr ist es nicht.

WAS AUSDRUECKLICH OFFENBLEIBT
    Ob auf einem echten Kabel Licht ankommt. Gemessen wird ein
    headless-Backend; es sagt, was der Compositor auf einen Ausgang
    ZEICHNET, nicht, was ein Bildschirm daraus macht.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHIRME = (ROOT / "iso" / "profile-release" / "airootfs"
           / "usr" / "local" / "bin" / "zepos-live-schirme")
HIER = Path(__file__).resolve().parent
PROTOKOLL_XML = HIER / "wlr-output-management-unstable-v1.xml"
CLIENT_C = HIER / "live_schirme_client.c"

# Wie lange gewartet wird, bis der Compositor und sein Kind stehen.
# Gemessen wird das Ergebnis, nicht die Dauer.
RUHE = 6.0
FRIST = 25.0

# Die Groesse, mit der das headless-Backend jeden Ausgang anlegt, und die
# kleinere, auf die einer davon fuer den Ungleich-Versuch gestellt wird.
GROSS = (1280, 720)
KLEIN = (800, 600)


def fehlt_kiosk() -> list[str]:
    """Was diese Maschine fuer den Kiosk braucht.

    Namentlich, damit ein Uebersprung SAGT, was fehlt - ein "skipped"
    ohne Grund ist ein Test, der aufgehoert hat zu messen, ohne dass es
    jemandem auffaellt.
    """
    return [name for name in ("cage", "foot", "grim")
            if shutil.which(name) is None]


def fehlt_bau() -> list[str]:
    """Und was sie braucht, um den Ausgangs-Client zu bauen."""
    mangel = [name for name in ("wayland-scanner", "pkg-config")
              if shutil.which(name) is None]
    if not (shutil.which("cc") or shutil.which("gcc")):
        mangel.append("cc")
    return mangel


class Bild:
    """Ein Ausgangsabzug, so weit ausgewertet, wie diese Datei ihn braucht.

    Ohne Bildbibliothek: grim schreibt auch PPM, und PPM ist ein Kopf und
    dann Bytes.
    """

    def __init__(self, pfad: Path) -> None:
        roh = pfad.read_bytes()
        teile = roh.split(b"\n", 3)
        assert len(teile) >= 4 and teile[0] == b"P6", f"{pfad} ist kein PPM"
        self.breite, self.hoehe = (int(x) for x in teile[1].split())
        self.daten = teile[3][:self.breite * self.hoehe * 3]

    def punkt(self, x: int, y: int) -> bytes:
        i = (y * self.breite + x) * 3
        return self.daten[i:i + 3]

    @property
    def farben(self) -> int:
        """Ein Ausgang, auf dem nichts steht, ist EINE Farbe. Der
        Installer ist viele. Mehr Unterscheidung braucht es nicht."""
        return len({self.daten[i:i + 3]
                    for i in range(0, len(self.daten), 3)})

    @property
    def grund(self) -> bytes:
        """Die haeufigste Farbe - der Hintergrund des Terminals."""
        return Counter(self.daten[i:i + 3]
                       for i in range(0, len(self.daten), 3)).most_common(1)[0][0]

    def unterste_zeile_mit_inhalt(self) -> int:
        """Die unterste Bildzeile, in der etwas anderes steht als Grund.

        Damit laesst sich sagen, WIE VIEL ein kleinerer Schirm abschneidet
        - und nicht nur, DASS er abschneidet.
        """
        grund = self.grund
        for y in range(self.hoehe - 1, -1, -1):
            zeile = self.daten[y * self.breite * 3:(y + 1) * self.breite * 3]
            if any(zeile[x * 3:x * 3 + 3] != grund for x in range(self.breite)):
                return y
        return -1

    def gleicht_oben_links(self, anderes: "Bild") -> bool:
        """Zeigt dieses Bild genau den linken oberen Ausschnitt des anderen?"""
        if self.breite > anderes.breite or self.hoehe > anderes.hoehe:
            return False
        for y in range(self.hoehe):
            meine = self.daten[y * self.breite * 3:(y + 1) * self.breite * 3]
            seine = anderes.daten[y * anderes.breite * 3:
                                  y * anderes.breite * 3 + self.breite * 3]
            if meine != seine:
                return False
        return True


@pytest.fixture(scope="session")
def ausgangs_client(tmp_path_factory) -> Path:
    """Der gebaute Client, unter dem Namen `wlr-randr`.

    Zurueck kommt das VERZEICHNIS, nicht die Datei: es wird vor den
    Suchpfad des Kindes gehaengt, damit das ausgelieferte Skript sein
    `wlr-randr` findet, ohne dass an ihm etwas geaendert wird.
    """
    mangel = fehlt_bau()
    if mangel:
        pytest.skip("fuer den Ausgangs-Client fehlt: " + ", ".join(mangel))

    bau = tmp_path_factory.mktemp("ausgangs-client")
    kopf = bau / "wlr-output-management-unstable-v1-client-protocol.h"
    code = bau / "wlr-output-management-unstable-v1-protocol.c"
    for art, ziel in (("client-header", kopf), ("private-code", code)):
        lauf = subprocess.run(
            ["wayland-scanner", art, str(PROTOKOLL_XML), str(ziel)],
            capture_output=True, text=True, timeout=60)
        assert lauf.returncode == 0, (
            f"wayland-scanner {art} misslang:\n{lauf.stderr}")

    flags = subprocess.run(
        ["pkg-config", "--cflags", "--libs", "wayland-client"],
        capture_output=True, text=True, timeout=60)
    if flags.returncode != 0:
        pytest.skip("pkg-config kennt wayland-client nicht - ohne die "
                    "Entwicklungsdateien ist der Client nicht baubar")

    ziel = bau / "wlr-randr"
    uebersetzer = shutil.which("cc") or shutil.which("gcc")
    lauf = subprocess.run(
        [uebersetzer, "-O1", "-o", str(ziel), str(CLIENT_C), str(code),
         f"-I{bau}", *flags.stdout.split()],
        capture_output=True, text=True, timeout=180)
    assert lauf.returncode == 0, (
        f"der Ausgangs-Client liess sich nicht uebersetzen:\n{lauf.stderr}")
    return bau


class Kiosk:
    """Ein cage auf dem headless-Backend, mit dem Installer-Aufbau darin."""

    def __init__(self) -> None:
        self.runtime = Path(tempfile.mkdtemp(prefix="zeplive-"))
        self.runtime.chmod(0o700)
        self.home = self.runtime / "home"
        self.home.mkdir()
        self.log = self.runtime / "cage.log"
        self.helfer_log = self.runtime / "schirme.log"
        self.cage: subprocess.Popen | None = None
        self.helfer: subprocess.Popen | None = None

        host = os.environ.get("XDG_RUNTIME_DIR")
        assert not host or Path(self.runtime).resolve() != Path(host).resolve(), (
            "der Kiosk soll in einem EIGENEN Laufzeitverzeichnis laufen")

    def environment(self, **extra: str) -> dict[str, str]:
        umgebung = {
            "PATH": os.environ.get("PATH", "/usr/bin"),
            "HOME": str(self.home),
            "XDG_RUNTIME_DIR": str(self.runtime),
            "XDG_CACHE_HOME": str(self.home / ".cache"),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            # Kein DRM und kein Wirt: der Aufbau braucht weder eine
            # Grafikkarte noch eine laufende Sitzung.
            "WLR_BACKENDS": "headless",
            "WLR_HEADLESS_OUTPUTS": "2",
            "WLR_RENDERER": "pixman",
            "LIBSEAT_BACKEND": "noop",
        }
        umgebung.update(extra)
        return umgebung

    def start(self) -> None:
        with self.log.open("wb") as sink:
            self.cage = subprocess.Popen(
                # Dieselbe Form wie zepos-live-session: cage, darin foot,
                # darin das, was der Benutzer sieht.
                ["cage", "--", "foot", "--fullscreen", "bash", "-c",
                 "for i in $(seq 1 60); do "
                 "printf 'ZEPOS INSTALLER ZEILE %02d ################\\n' $i; "
                 "done; sleep 300"],
                env=self.environment(), stdout=sink, stderr=subprocess.STDOUT)

        frist = time.monotonic() + FRIST
        while time.monotonic() < frist:
            if self.socket():
                time.sleep(RUHE)
                return
            if self.cage.poll() is not None:
                raise AssertionError("cage endete, bevor es einen Socket "
                                     "hatte:\n" + self.protokoll())
            time.sleep(0.2)
        raise AssertionError("cage hat keinen Socket angelegt:\n"
                             + self.protokoll())

    def socket(self) -> str | None:
        namen = sorted(p.name for p in self.runtime.iterdir()
                       if p.name.startswith("wayland-")
                       and not p.name.endswith(".lock"))
        return namen[0] if namen else None

    def kiosk_env(self, **extra: str) -> dict[str, str]:
        socket = self.socket()
        assert socket, "der Kiosk hat keinen Socket"
        return self.environment(WAYLAND_DISPLAY=socket, **extra)

    def randr(self, client: Path, *argumente: str) -> subprocess.CompletedProcess:
        """Den Ausgangs-Client von Hand aufrufen - fuer den AUFBAU eines
        Versuchs, nicht fuer den Fix. Den macht das Skript."""
        return subprocess.run(
            [str(client / "wlr-randr"), *argumente],
            env=self.kiosk_env(), capture_output=True, text=True, timeout=60)

    def aufnehmen(self, marke: str) -> dict[str, Bild]:
        """Je Ausgang ein Bild, ueber cages eigenes wlr-screencopy."""
        ergebnis: dict[str, Bild] = {}
        for name in ("HEADLESS-1", "HEADLESS-2"):
            ziel = self.runtime / f"{marke}-{name}.ppm"
            lauf = subprocess.run(
                ["grim", "-t", "ppm", "-o", name, str(ziel)],
                env=self.kiosk_env(), capture_output=True, text=True,
                timeout=30)
            assert ziel.exists() and ziel.stat().st_size, (
                f"kein Bild von {name}: rc={lauf.returncode} "
                f"{lauf.stderr.strip()}")
            ergebnis[name] = Bild(ziel)
        return ergebnis

    def helfer_starten(self, client: Path) -> None:
        """Das AUSGELIEFERTE Skript, gegen diesen Kiosk.

        Der gebaute Client kommt VOR den Suchpfad; alles andere, was das
        Skript ruft - awk, date, sleep, tr -, bleibt das der Maschine.
        """
        pfad = f"{client}{os.pathsep}{os.environ.get('PATH', '/usr/bin')}"
        self.helfer = subprocess.Popen(
            [str(SCHIRME)],
            env=self.kiosk_env(PATH=pfad,
                               ZEPOS_SCHIRME_INTERVALL="0.3",
                               ZEPOS_SCHIRME_LOG=str(self.helfer_log)),
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    def warte_auf_gleichstand(self, marke: str) -> dict[str, Bild]:
        """Aufnehmen, bis beide Ausgaenge dasselbe zeigen - oder die Frist
        um ist. Ohne Frist waere ein misslungener Fix ein haengender Test;
        mit ihr ist er ein fehlgeschlagener."""
        frist = time.monotonic() + FRIST
        stand = self.aufnehmen(marke)
        while time.monotonic() < frist:
            time.sleep(1.0)
            stand = self.aufnehmen(marke)
            if (stand["HEADLESS-1"].daten == stand["HEADLESS-2"].daten):
                return stand
        return stand

    def protokoll(self) -> str:
        cage = self.log.read_text(errors="replace") if self.log.exists() else ""
        helfer = (self.helfer_log.read_text(errors="replace")
                  if self.helfer_log.exists() else "(kein Helferprotokoll)")
        return f"--- cage ---\n{cage[-2500:]}\n--- schirme ---\n{helfer}"

    def stop(self) -> None:
        for kind in (self.helfer, self.cage):
            if kind and kind.poll() is None:
                kind.terminate()
                try:
                    kind.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    kind.kill()
                    kind.wait(timeout=10)

    def __enter__(self) -> "Kiosk":
        return self

    def __exit__(self, *_exception) -> None:
        self.stop()
        shutil.rmtree(self.runtime, ignore_errors=True)


@pytest.fixture(scope="module")
def ohne_helfer() -> dict:
    """Nur cage, ohne alles Weitere - der Fehler, um den es geht.

    EIGENE Sitzung, und das ist Absicht: dieser Nachweis braucht weder
    einen Uebersetzer noch einen Ausgangs-Client, und er soll deshalb
    auch auf einer Maschine laufen, auf der die fehlen. Ein Baum, der
    nicht mehr zeigen kann, WARUM eine Datei existiert, verliert sie beim
    naechsten Aufraeumen.
    """
    mangel = fehlt_kiosk()
    if mangel:
        pytest.skip("fuer den Kiosk fehlt: " + ", ".join(mangel))
    with Kiosk() as kiosk:
        kiosk.start()
        return {"bilder": kiosk.aufnehmen("blank"),
                "protokoll": kiosk.protokoll()}


@pytest.fixture(scope="module")
def spiegelung(ausgangs_client) -> dict:
    """Gleich grosse Schirme: vorher, dann das ausgelieferte Skript."""
    mangel = fehlt_kiosk()
    if mangel:
        pytest.skip("fuer den Kiosk fehlt: " + ", ".join(mangel))

    with Kiosk() as kiosk:
        kiosk.start()
        vorher = kiosk.aufnehmen("vorher")
        kiosk.helfer_starten(ausgangs_client)
        nachher = kiosk.warte_auf_gleichstand("nachher")
        return {"vorher": vorher, "nachher": nachher,
                "protokoll": kiosk.protokoll()}


@pytest.fixture(scope="module")
def ungleich(ausgangs_client) -> dict:
    """Ein kleinerer Schirm neben einem groesseren.

    Der AUFBAU stellt HEADLESS-2 auf 800x600, BEVOR gemessen wird - und
    zwar mit dem Client von Hand, nicht durch das Skript: das Skript
    aendert nie eine Groesse, es verschiebt nur. Danach laeuft es wie im
    Betrieb.
    """
    mangel = fehlt_kiosk()
    if mangel:
        pytest.skip("fuer den Kiosk fehlt: " + ", ".join(mangel))

    with Kiosk() as kiosk:
        kiosk.start()
        aufbau = kiosk.randr(ausgangs_client, "--output", "HEADLESS-2",
                             "--custom-mode", f"{KLEIN[0]}x{KLEIN[1]}")
        assert aufbau.returncode == 0, (
            "der kleinere Schirm liess sich nicht einstellen: "
            + aufbau.stderr)
        time.sleep(4.0)
        vorher = kiosk.aufnehmen("vorher")
        kiosk.helfer_starten(ausgangs_client)
        time.sleep(6.0)
        nachher = kiosk.aufnehmen("nachher")
        return {"vorher": vorher, "nachher": nachher,
                "protokoll": kiosk.protokoll()}


# --------------------------------------------------------------------
# Der Fehler
# --------------------------------------------------------------------

def test_ohne_den_helfer_bleibt_ein_schirm_leer(ohne_helfer):
    """Die Grundlage. Ohne sie sagte "danach zeigen beide dasselbe"
    nichts - ein Aufbau, in dem ohnehin beide dasselbe zeigen, erfuellt
    es auch.

    GEMESSEN am 01.09.2026: ein Ausgang trug EINE Farbe, der andere 185.
    Das ist der schwarze Schirm, um den es geht.

    UND WELCHER der beiden leer bleibt, entscheidet nicht der Mensch.
    Gemessen lag HEADLESS-2 am Ursprung und trug den Installer,
    HEADLESS-1 lag daneben und war leer - also der ZWEITE Ausgang zeigte
    ihn, nicht der erste. Wer davon ausgeht, cage bediene "den ersten
    Schirm", rechnet mit der falschen Haelfte.
    """
    bilder = ohne_helfer["bilder"]
    anzahl = sorted(b.farben for b in bilder.values())
    assert anzahl[0] == 1, (
        f"kein Ausgang war leer: {[(n, b.farben) for n, b in bilder.items()]} - "
        "dann misst dieser Aufbau nicht, was er messen soll:\n"
        + ohne_helfer["protokoll"])
    assert anzahl[-1] > 10, (
        f"kein Ausgang trug den Installer: "
        f"{[(n, b.farben) for n, b in bilder.items()]}\n"
        + ohne_helfer["protokoll"])


# --------------------------------------------------------------------
# Der Fix, an gleich grossen Schirmen
# --------------------------------------------------------------------

def test_danach_zeigen_beide_schirme_denselben_installer(spiegelung):
    """DIE BESTELLUNG, in Pixeln.

    Das ausgelieferte /usr/local/bin/zepos-live-schirme legt beide
    Ausgaenge auf dieselbe Stelle, und ein wlroots-Compositor zeichnet
    dann auf beide denselben Ausschnitt. Geprueft wird nicht "es steht
    irgendetwas da", sondern BYTE-GLEICHHEIT: zwei Ausgaenge derselben
    Groesse, die dasselbe zeigen, sind dasselbe Bild.
    """
    vorher = spiegelung["vorher"]
    assert sorted(b.farben for b in vorher.values())[0] == 1, (
        "schon vor dem Helfer trugen beide Ausgaenge etwas - dieser Lauf "
        "misst dann nichts:\n" + spiegelung["protokoll"])

    nachher = spiegelung["nachher"]
    for name, bild in nachher.items():
        assert bild.farben > 10, (
            f"{name} trug nach dem Ueberlagern nur {bild.farben} Farben - "
            f"dort steht kein Installer:\n" + spiegelung["protokoll"])
    eins, zwei = (b.daten for b in nachher.values())
    assert eins == zwei, (
        "die beiden Ausgaenge zeigen nicht dasselbe Bild:\n"
        + spiegelung["protokoll"])


# --------------------------------------------------------------------
# Und an ungleich grossen - was im Bericht zu Aufgabe 75 offenblieb
# --------------------------------------------------------------------

def test_auch_bei_ungleicher_groesse_bleibt_kein_schirm_leer(ungleich):
    """Das Wichtigste zuerst: der Fix haelt auch dann.

    GEMESSEN am 01.09.2026, dreimal mit gleichem Ergebnis, mit 1280x720
    neben 800x600:

        vorher   HEADLESS-1 (1280x720)   1 Farbe
                 HEADLESS-2  (800x600) 185 Farben
        nachher  beide                 185 Farben

    Der schwarze Schirm ist weg, und zwar ohne dass irgendeine Groesse
    angefasst wurde - das Skript verschiebt nur.
    """
    vorher = ungleich["vorher"]
    assert sorted(b.farben for b in vorher.values())[0] == 1, (
        "schon vorher war kein Ausgang leer - dieser Lauf misst nichts:\n"
        + ungleich["protokoll"])

    for name, bild in ungleich["nachher"].items():
        assert bild.farben > 10, (
            f"{name} blieb leer ({bild.farben} Farben), obwohl ueberlagert "
            f"wurde:\n" + ungleich["protokoll"])


def test_der_kleinere_schirm_zeigt_einen_ausschnitt_und_kein_verkleinertes_bild(
        ungleich):
    """Der Preis, und er wird hier festgenagelt statt beschrieben.

    UEBERLAGERN IST NICHT SPIEGELN. Hyprland skaliert beim Spiegeln
    seitenverhaeltnistreu in die Mitte (Renderer.cpp:1961-1988, siehe
    src/bin/zepos-greeter-spiegel) - da steht die Maske auf JEDEM Schirm
    vollstaendig. Hier zeichnet jeder Ausgang den Ausschnitt ab 0,0 IN
    SEINER EIGENEN GROESSE, und der kleinere schneidet ab.

    GEMESSEN am 01.09.2026, dreimal gleich: das Bild des 800x600-Ausgangs
    war Byte fuer Byte der linke obere 800x600-Ausschnitt des
    1280x720-Ausgangs, und auf dem groesseren stand Inhalt bis Bildzeile
    719 - also 120 Zeilen unterhalb dessen, was der kleinere ueberhaupt
    zeigen kann.

    WARUM DAS TROTZDEM BLEIBT
        Jeder Ausgleich dafuer - set_scale, ein anderer Modus - ist eine
        Konfiguration, die ein ECHTER Bildschirm ablehnen kann, und eine
        abgelehnte Konfiguration heisst: es bleibt beim schwarzen Schirm.
        Der Ausschnitt ist der Preis dafuer, dass der Fix nicht
        fehlschlagen kann. Auf dem groessten angeschlossenen Schirm steht
        der Installer vollstaendig, und dort laesst er sich bedienen.

    Faellt dieser Test eines Tages, weil beide Bilder gleich gross sind,
    dann hat jemand das behoben - und darf diesen Test ersetzen statt ihn
    zu streichen.
    """
    nachher = ungleich["nachher"]
    klein = nachher["HEADLESS-2"]
    gross = nachher["HEADLESS-1"]

    assert (klein.breite, klein.hoehe) == KLEIN, (
        f"der kleinere Ausgang ist {klein.breite}x{klein.hoehe} statt "
        f"{KLEIN[0]}x{KLEIN[1]} - der Aufbau hat nicht gegriffen")
    assert (gross.breite, gross.hoehe) == GROSS, (
        f"der groessere Ausgang ist {gross.breite}x{gross.hoehe} statt "
        f"{GROSS[0]}x{GROSS[1]}")

    assert klein.gleicht_oben_links(gross), (
        "der kleinere Schirm zeigt NICHT den linken oberen Ausschnitt des "
        "groesseren. Dann tut das Ueberlagern etwas anderes als hier "
        "beschrieben, und der Kopf von zepos-live-schirme stimmt nicht "
        "mehr:\n" + ungleich["protokoll"])

    unten = gross.unterste_zeile_mit_inhalt()
    assert unten >= klein.hoehe, (
        f"auf dem groesseren Schirm endet der Inhalt schon bei Zeile "
        f"{unten}, der kleinere reicht bis {klein.hoehe - 1} - dann wird "
        "gar nichts abgeschnitten, und diese Datei beschreibt einen Preis, "
        "den es nicht gibt:\n" + ungleich["protokoll"])
