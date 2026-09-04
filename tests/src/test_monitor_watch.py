# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Waechter fuer Schirmwechsel, an einer Buehne gemessen.

WAS GEMELDET WURDE (04.09.2026), WOERTLICH
    "bei anschliessen eines weiteren bildschirm wird der background
     schwarz und wenn ich verusche allgemein ags sachen dort zu machen
     erscheinen die fenster nur auf der edp also dem laptop monitor und
     sie werdne nicht als getrennte instanzen behandelt"

    Drei Dinge werden aus "welche Schirme haengen dran" abgeleitet, und
    alle drei standen als `exec-once` in der Hyprland-Konfiguration -
    sie liefen genau einmal, beim Anmelden. Ein Schirm, der spaeter
    dazukam, bekam kein swaybg (er ist schwarz) und keine eigene
    Arbeitsflaeche; damit lag JEDE Arbeitsflaeche weiter auf dem ersten
    Schirm. hypr-monitor-watch.py zieht die drei bei einem Wechsel nach.

WARUM DAS HIER STEHT UND NICHT IN tests/render/
    Dort stand es zuerst, an einem echten verschachtelten Compositor,
    und es hat am 04.09.2026 dreimal die Tapete der laufenden Sitzung
    eines Menschen erlegt. Der Grund ist kein Versehen, sondern eine
    Regel, die dieser Baum ausgeschrieben hat und die ich uebersehen
    habe:

        tests/render/desktop_session.py, Kopf der Klasse Session:
        "Es gibt hier kein pkill: ein Mustertreffer im Prozessbaum der
         Maschine faende das AGS des Nutzers."

        derselbe Kopf, "WAS NICHT AUSGEFUEHRT WIRD": src/
        generate_config.sh, weil es die laufende Oberflaeche beendet
        "und trifft damit die Prozesse des Nutzers, egal welches HOME er
        bekommt".

        tests/conftest.py, NEVER_PASSTHROUGH: hyprctl, swaybg, pkill,
        pgrep, setsid - "must never reach its real binary".

    `wallpaper-manager` raeumt mit `pkill -9 -x swaybg` auf, und ein
    Muster kennt keine Sitzung. Es gehoert damit in dieselbe Klasse wie
    generate_config.sh: ein Messstand fuehrt es nicht aus. Kein Zaun
    darum repariert das - der Zaun waere eine Ausnahme von einer Regel,
    die es aus einem gemessenen Grund gibt.

WAS DIESE BUEHNE STATTDESSEN TUT
    Sie stellt dem Waechter alles hin, was er anfasst, und schreibt
    jeden Aufruf mit:

        .socket2.sock     ein echter AF_UNIX-Server dieses Laufes. Der
                          Waechter findet ihn ueber
                          XDG_RUNTIME_DIR/hypr/$HIS, genau wie im
                          Betrieb.
        hyprctl           ein Stummel: er antwortet auf `monitors -j`
                          mit dem Inhalt einer Datei, die der Test
                          aendert, und schreibt jeden Aufruf mit.
        die drei Skripte  Stummel an genau den Pfaden, die der Waechter
                          bildet.

    Damit ist MEHR messbar als am Compositor: das Entprellen und die
    Mengenpruefung (ein `reload` kann selbst monitoradded senden) waren
    dort ungemessen, weil sich ein Ereignisschwall nicht bestellen
    laesst. Hier wird er geschickt.

    Dass `wallpaper-manager restore` fuer JEDEN gemeldeten Schirm ein
    swaybg startet - die andere Haelfte von Symptom A - misst
    tests/src/test_wallpaper_manager.py, mit denselben Stummeln.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
sys.path.insert(0, str(ROOT / "tests"))

import conftest                                            # noqa: E402

VORLAGE = SRC / "templates" / "hypr-monitor-watch-config.template"

# Die Kennung der Sitzung. Ein Wert und kein echter: der Waechter baut
# aus ihm nur einen Pfad.
KENNUNG = "zepbuehne-0123456789abcdef"

# Wie lange auf eine Wirkung gewartet wird. Der Waechter entprellt 0,6 s
# und ruft danach vier Befehle, die hier Stummel sind.
FRIST = 15.0

# Muss echt sein, darf aber nichts aendern: der Waechter ruft die drei
# Skripte mit `bash <pfad>`, und die Stummel dort sind Bash-Skripte.
# bash steht nicht in conftest.NEVER_PASSTHROUGH - es aendert nichts von
# sich aus.
DURCHREICHEN = ("bash",)

# Muss NIE echt laufen. hyprctl steht namentlich in
# conftest.NEVER_PASSTHROUGH: ein echtes hyprctl ohne die Kennung dieser
# Buehne redet mit dem Compositor des Menschen an dieser Maschine.
MITGESCHRIEBEN = ("hyprctl",)

pytestmark = pytest.mark.allow_subprocess


class Buehne:
    """Alles, was der Waechter anfasst - und nichts darueber hinaus."""

    def __init__(self, wurzel: Path) -> None:
        self.wurzel = wurzel
        self.heim = wurzel / "heim"
        # KURZ UND UNTER /tmp, und das ist keine Bequemlichkeit:
        # sockaddr_un.sun_path fasst 108 Bytes, und der Waechter sucht
        # den Socket unter <laufzeit>/hypr/<kennung>/.socket2.sock.
        # Unter pytests tmp_path ("/tmp/pytest-of-<user>/pytest-3/
        # test_ein_langer_testname0/...") reisst das - GEMESSEN am
        # 04.09.2026: "OSError: AF_UNIX path too long". Dieselbe
        # Ueberlegung und derselbe Weg wie in
        # tests/render/desktop_session.py.
        self.laufzeit = Path(tempfile.mkdtemp(prefix="zepwatch-"))
        self.stummel = wurzel / "stummel"
        self.aufrufe = wurzel / "aufrufe.txt"
        self.monitore = wurzel / "monitore.json"
        for ordner in (self.heim, self.stummel):
            ordner.mkdir(parents=True, exist_ok=True)
        self.laufzeit.chmod(0o700)
        self.aufrufe.write_text("", encoding="utf-8")
        self.server: socket.socket | None = None
        self.verbindung: socket.socket | None = None
        self.kind: subprocess.Popen | None = None
        # Wie viele Aufrufe schon standen, als der Waechter
        # fertig hochgekommen war - siehe starte().
        self.grundlinie = 0

    # -- Aufbau ------------------------------------------------------

    def waechter(self) -> Path:
        """Den Waechter aus der Vorlage erzeugen, wie der Generator."""
        sys.path.insert(0, str(SRC))
        try:
            import template_processor
            ziel = self.heim / ".config" / "hypr" / "hypr-monitor-watch.py"
            ziel.parent.mkdir(parents=True, exist_ok=True)
            template_processor.ConfigProcessor().apply_template(VORLAGE, ziel)
            ziel.chmod(0o755)
            return ziel
        finally:
            sys.path.remove(str(SRC))

    def _schreibe_stummel(self, pfad: Path, name: str,
                          antwort: str = "") -> None:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(
            "#!/bin/bash\n"
            f"printf '{name} %s\\n' \"$*\" >> '{self.aufrufe}'\n"
            + antwort
            + "exit 0\n", encoding="utf-8")
        pfad.chmod(0o755)

    def stelle_alles_hin(self, schirme: list[str]) -> Path:
        """Die drei Skripte, hyprctl und bash. Zurueck: der Waechter."""
        self.setze_schirme(schirme)

        # Die drei Schritte der Kette, an genau den Pfaden, die der
        # Waechter aus $HOME und $XDG_CONFIG_HOME bildet.
        self._schreibe_stummel(
            self.heim / ".config" / "hypr" / "hypr-monitor-detect.sh",
            "hypr-monitor-detect")
        self._schreibe_stummel(
            self.heim / ".config" / "ags" / "bar-workspace-detect.sh",
            "bar-workspace-detect")
        self._schreibe_stummel(
            self.heim / ".local" / "bin" / "wallpaper-manager",
            "wallpaper-manager")

        # hyprctl: schreibt mit und antwortet auf `monitors -j`.
        # hyprctl antwortet OHNE `cat`, und das ist der Grund:
        #
        #     Der Stummelordner ist der GANZE PATH. `cat` ist kein
        #     Builtin, es liegt in /usr/bin - und ein Befehl, den
        #     niemand hingestellt hat, wird zu "command not found".
        #     GEMESSEN am 04.09.2026: der Stummel schrieb seinen Aufruf
        #     brav mit und gab NICHTS aus, der Waechter meldete
        #     "hyprctl monitors antwortete kein JSON", und der Lauf sah
        #     aus wie ein kaputter Waechter.
        #
        #     `"$(< datei)"` ist eine Umleitung und damit Bash selbst.
        #     Kein zweiter Durchreicher, keine zweite Stelle, an der
        #     etwas fehlen kann.
        for name in MITGESCHRIEBEN:
            self._schreibe_stummel(
                self.stummel / name, name,
                antwort=('if [ "$1 $2" = "monitors -j" ]; then\n'
                         f"  printf '%s' \"$(< '{self.monitore}')\"\n"
                         "fi\n"))

        for name in DURCHREICHEN:
            conftest.assert_safe_to_passthrough(name)
            echt = shutil.which(name)
            assert echt and echt.startswith("/"), f"{name} fehlt"
            stummel = self.stummel / name
            stummel.write_text(f'#!/bin/bash\nexec "{echt}" "$@"\n',
                               encoding="utf-8")
            stummel.chmod(0o755)

        return self.waechter()

    def setze_schirme(self, namen: list[str]) -> None:
        """Was `hyprctl monitors -j` von jetzt an antwortet."""
        self.monitore.write_text(
            json.dumps([{"id": nummer, "name": name}
                        for nummer, name in enumerate(namen)]),
            encoding="utf-8")

    # -- Betrieb -----------------------------------------------------

    def umgebung(self) -> dict[str, str]:
        """Genau die Umgebung, die der Waechter braucht, und keine mehr.

        Der Stummelordner ist der GANZE PATH - dieselbe Halbe wie in
        tests/src/test_wallpaper_manager.py: ein Befehl, den niemand
        hingestellt hat, wird zu einem lauten "command not found" und
        nicht zu einem stillen Griff an die Maschine.
        """
        return {
            "PATH": str(self.stummel),
            "HOME": str(self.heim),
            "XDG_CONFIG_HOME": str(self.heim / ".config"),
            "XDG_RUNTIME_DIR": str(self.laufzeit),
            "HYPRLAND_INSTANCE_SIGNATURE": KENNUNG,
            "TMPDIR": str(self.wurzel / "tmp"),
        }

    def starte(self, waechter: Path) -> None:
        """Den Ereignisstrom aufmachen, dann den Waechter starten.

        In DIESER Reihenfolge: ein Waechter, der nichts zum Verbinden
        findet, endet mit 1 - und misst dann nichts.
        """
        ordner = self.laufzeit / "hypr" / KENNUNG
        ordner.mkdir(parents=True, exist_ok=True)
        pfad = ordner / ".socket2.sock"
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(pfad))
        self.server.listen(1)

        (self.wurzel / "tmp").mkdir(exist_ok=True)
        python = shutil.which("python3")
        assert python and python.startswith("/"), "python3 fehlt"
        self.kind = subprocess.Popen(
            [python, str(waechter)], env=self.umgebung(),
            stdin=subprocess.DEVNULL,
            stdout=(self.wurzel / "waechter.log").open("wb"),
            stderr=subprocess.STDOUT)

        self.server.settimeout(FRIST)
        self.verbindung, _ = self.server.accept()

        # DIE GRUNDLINIE, und ohne sie messen die Zusicherungen daneben.
        #
        #     Der Waechter sieht BEIM START einmal nach, welche Schirme
        #     es gibt (`hyprctl monitors -j`), und zwar bevor er sich
        #     verbindet. Dieser Aufruf steht also schon im Protokoll,
        #     wenn accept() zurueckkommt - er gehoert zum Hochkommen und
        #     nicht zu einem Ereignis. GEMESSEN am 04.09.2026: zwei
        #     Zusicherungen dieser Datei waren rot, weil sie ihn
        #     mitgezaehlt haben.
        ende = time.monotonic() + FRIST
        while time.monotonic() < ende and not self.gerufen():
            time.sleep(0.05)
        self.grundlinie = len(self.gerufen())

    def sende(self, *ereignisse: str) -> None:
        assert self.verbindung, "starte() wurde nicht gerufen"
        for ereignis in ereignisse:
            self.verbindung.sendall(f"{ereignis}\n".encode())

    def gerufen(self) -> list[str]:
        try:
            return [zeile for zeile
                    in self.aufrufe.read_text(encoding="utf-8").splitlines()
                    if zeile.strip()]
        except OSError:
            return []

    def seit(self) -> list[str]:
        """Die Aufrufe NACH dem Hochkommen - siehe starte()."""
        return self.gerufen()[self.grundlinie:]

    def warte_auf(self, anzahl: int, frist: float = FRIST) -> list[str]:
        """Warten, bis so viele Aufrufe da sind - oder aufgeben."""
        ende = time.monotonic() + frist
        while time.monotonic() < ende:
            if len(self.seit()) >= anzahl:
                # Noch einen Wimpernschlag, damit ein Aufruf ZU VIEL
                # auch sichtbar wird und nicht erst im naechsten Test.
                time.sleep(0.4)
                return self.seit()
            time.sleep(0.1)
        return self.seit()

    def ruhe(self, dauer: float = 3.0) -> list[str]:
        """Abwarten und dann sagen, was gerufen wurde.

        Fuer die Faelle, in denen NICHTS passieren soll: eine Zusicherung
        darueber braucht eine Frist, sonst prueft sie nur, dass es noch
        nicht passiert ist.
        """
        time.sleep(dauer)
        return self.seit()

    def protokoll(self) -> str:
        stuecke = []
        for pfad in ((self.wurzel / "waechter.log"),
                     (self.laufzeit / "zepos-monitor-watch.log")):
            try:
                stuecke.append(f"--- {pfad.name} ---\n"
                               + pfad.read_text(encoding="utf-8"))
            except OSError:
                pass
        return "\n".join(stuecke)

    def raeum_ab(self) -> None:
        for teil in (self.verbindung, self.server):
            if teil:
                try:
                    teil.close()
                except OSError:
                    pass
        if self.kind and self.kind.poll() is None:
            self.kind.terminate()
            try:
                self.kind.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.kind.kill()
        # Das Laufzeitverzeichnis liegt ausserhalb von tmp_path (siehe
        # den Kopf des Konstruktors), also raeumt es niemand sonst weg.
        shutil.rmtree(self.laufzeit, ignore_errors=True)


@pytest.fixture
def buehne(tmp_path):
    stand = Buehne(tmp_path)
    try:
        yield stand
    finally:
        stand.raeum_ab()


def _namen(aufrufe: list[str]) -> list[str]:
    return [zeile.split(" ", 1)[0] for zeile in aufrufe]


# --------------------------------------------------------------------
# Dass er ueberhaupt anspringt
# --------------------------------------------------------------------

def test_ein_neuer_schirm_loest_die_ganze_kette_aus(buehne):
    """Die Antwort auf die Meldung, in vier Aufrufen.

    Der Waechter darf nicht auf gut Glueck etwas tun: er soll GENAU die
    drei Ableitungen nachziehen, die es gibt, und Hyprland dazwischen
    zum Neulesen auffordern.
    """
    waechter = buehne.stelle_alles_hin(["eDP-1"])
    buehne.starte(waechter)

    buehne.setze_schirme(["eDP-1", "HDMI-A-1"])
    buehne.sende("monitoradded>>HDMI-A-1")

    aufrufe = buehne.warte_auf(5)
    namen = _namen(aufrufe)

    # Der erste Aufruf nach dem Ereignis ist das Nachsehen, welche
    # Schirme es JETZT gibt - er gehoert zur Entscheidung und nicht zur
    # Kette. Danach kommen die vier Schritte.
    assert namen == ["hyprctl", "hypr-monitor-detect", "hyprctl",
                     "bar-workspace-detect", "wallpaper-manager"], (
        f"die Kette lief nicht in ihrer Reihenfolge: {aufrufe}\n"
        f"{buehne.protokoll()}")


def test_hyprland_wird_nach_der_zuordnung_zum_neulesen_aufgefordert(buehne):
    """Und ZWISCHEN Zuordnung und Leiste, nicht irgendwo.

    hypr-monitor-detect.sh schreibt workspaces-generated.conf, und
    Hyprland sourct sie. Ein `reload` davor las die alte Datei; die
    Leiste danach zeigt die Aufteilung, die der Compositor wirklich hat.
    """
    waechter = buehne.stelle_alles_hin(["eDP-1"])
    buehne.starte(waechter)
    buehne.setze_schirme(["eDP-1", "HDMI-A-1"])
    buehne.sende("monitoradded>>HDMI-A-1")
    aufrufe = buehne.warte_auf(5)

    reloads = [zeile for zeile in aufrufe if zeile == "hyprctl reload"]
    assert len(reloads) == 1, (
        f"genau ein `hyprctl reload` war erwartet, gerufen wurde: "
        f"{aufrufe}\n{buehne.protokoll()}")

    stellen = {name: nummer for nummer, name in enumerate(_namen(aufrufe))}
    assert (stellen["hypr-monitor-detect"] < aufrufe.index("hyprctl reload")
            < stellen["bar-workspace-detect"]), (
        f"das Neulesen steht nicht zwischen Zuordnung und Leiste: "
        f"{aufrufe}\n{buehne.protokoll()}")


def test_ein_abgestecktes_kabel_zieht_genauso_nach(buehne):
    """Die Haelfte, die weh tut.

    Ein Schirm, der GEHT, laesst eine Zuordnung zurueck, die auf einen
    Ausgang zeigt, den es nicht mehr gibt - und die Leiste zeigt Knoepfe
    fuer eine Aufteilung, die es nicht mehr gibt.
    """
    waechter = buehne.stelle_alles_hin(["eDP-1", "HDMI-A-1"])
    buehne.starte(waechter)
    buehne.setze_schirme(["eDP-1"])
    buehne.sende("monitorremoved>>HDMI-A-1")

    namen = _namen(buehne.warte_auf(5))
    assert "wallpaper-manager" in namen and "hypr-monitor-detect" in namen, (
        f"nach dem Abstecken lief die Kette nicht: {namen}\n"
        f"{buehne.protokoll()}")


# --------------------------------------------------------------------
# Dass er nicht zu oft anspringt
# --------------------------------------------------------------------

def test_ein_schwall_von_ereignissen_ist_ein_einziger_nachzug(buehne):
    """Das Entprellen, und es ist der Grund, warum es es gibt.

    Ein Kabel bringt mehrere Zeilen (monitoradded, monitoraddedv2 und
    die Arbeitsflaechen, die mitwandern), ein Dock bringt mehrere
    Schirme. Ohne das Entprellen liefe die Kette je Zeile - und
    `wallpaper-manager` raeumt jedes Mal alle swaybg ab und startet sie
    neu. Der Nutzer saehe seinen Schreibtisch dabei blinken.
    """
    waechter = buehne.stelle_alles_hin(["eDP-1"])
    buehne.starte(waechter)
    buehne.setze_schirme(["eDP-1", "HDMI-A-1"])
    buehne.sende(
        "monitoradded>>HDMI-A-1",
        "monitoraddedv2>>1,HDMI-A-1,HDMI",
        "workspace>>1",
        "monitoradded>>HDMI-A-1",
        "monitoraddedv2>>1,HDMI-A-1,HDMI",
    )

    aufrufe = buehne.warte_auf(5)
    ketten = _namen(aufrufe).count("hypr-monitor-detect")
    assert ketten == 1, (
        f"die Kette lief {ketten} mal fuer EIN Kabel: {aufrufe}\n"
        f"{buehne.protokoll()}")


def test_dieselben_schirme_loesen_nichts_aus(buehne):
    """Die Schleifensicherung, und sie ist keine Vorsicht auf Verdacht.

    `hyprctl reload` liest monitors.conf neu, und das Anwenden eines
    Monitormodus kann selbst monitoradded senden. Ein Waechter, der auf
    das EREIGNIS reagiert, fuettert sich damit selbst: reload ->
    Ereignis -> reload. Entschieden wird deshalb an der MENGE der
    Schirme.
    """
    waechter = buehne.stelle_alles_hin(["eDP-1"])
    buehne.starte(waechter)

    # Ereignis, aber die Menge bleibt, wie sie war.
    buehne.sende("monitoradded>>eDP-1")

    aufrufe = buehne.ruhe()
    ketten = _namen(aufrufe).count("hypr-monitor-detect")
    assert ketten == 0, (
        f"ohne echte Aenderung lief die Kette {ketten} mal - das ist die "
        f"Schleife: {aufrufe}\n{buehne.protokoll()}")
    assert aufrufe == ["hyprctl monitors -j"], (
        f"erwartet war genau ein Blick auf die Schirme und sonst nichts, "
        f"gerufen wurde: {aufrufe}. Ohne den Blick waere das Gruen "
        f"darueber kein Befund.\n{buehne.protokoll()}")


def test_ein_fremdes_ereignis_laesst_ihn_kalt(buehne):
    """Der Gegenbeweis zur Auswahl der Anlaesse.

    Auf .socket2.sock kommt jede Regung des Compositors: jedes Fenster,
    jeder Arbeitsflaechenwechsel, jeder Titel. Ein Waechter, der bei
    allem nachsieht, ruft `hyprctl monitors` hunderte Mal am Tag.
    """
    waechter = buehne.stelle_alles_hin(["eDP-1"])
    buehne.starte(waechter)
    buehne.setze_schirme(["eDP-1", "HDMI-A-1"])     # es HAETTE etwas zu tun
    buehne.sende("workspace>>2", "openwindow>>abc,1,kitty,kitty",
                 "activewindow>>kitty,kitty", "focusedmon>>eDP-1,1")

    aufrufe = buehne.ruhe()
    assert aufrufe == [], (
        f"ein fremdes Ereignis hat ihn bewegt: {aufrufe} (gezaehlt ab dem "
        f"Hochkommen, siehe starte())\n{buehne.protokoll()}")


# --------------------------------------------------------------------
# Dass er das Erste ueberlebt
# --------------------------------------------------------------------

def test_das_zweite_kabel_wird_genauso_nachgezogen(buehne):
    """Der Fehler, der ihn beim ersten Mal getoetet hat.

    Die erste Fassung las den Strom mit `makefile()` und stellte fuer
    das Entprellen eine Zeitgrenze am Socket. Danach ist ein
    Socket-Dateiobjekt unbrauchbar, auch wenn die Grenze wieder weg ist:

        OSError: cannot read from timed out object

    Der Waechter war nach dem ERSTEN Kabel weg - und das zweite des
    Tages wieder schwarz. Ein Prozess, der nur einmal wirkt, sieht in
    einer Messung mit einem Kabel genau richtig aus.
    """
    waechter = buehne.stelle_alles_hin(["eDP-1"])
    buehne.starte(waechter)

    buehne.setze_schirme(["eDP-1", "HDMI-A-1"])
    buehne.sende("monitoradded>>HDMI-A-1")
    erste = buehne.warte_auf(5)
    assert _namen(erste).count("hypr-monitor-detect") == 1, (
        f"schon das erste Kabel wirkte nicht: {erste}\n{buehne.protokoll()}")

    buehne.setze_schirme(["eDP-1", "HDMI-A-1", "DP-3"])
    buehne.sende("monitoradded>>DP-3")
    zweite = buehne.warte_auf(len(erste) + 5)

    assert _namen(zweite).count("hypr-monitor-detect") == 2, (
        f"das zweite Kabel hat nichts ausgeloest - der Waechter lebt nach "
        f"dem ersten nicht weiter: {zweite}\n{buehne.protokoll()}")
    assert buehne.kind and buehne.kind.poll() is None, (
        f"der Waechter ist gestorben (Ende {buehne.kind.poll()}):\n"
        f"{buehne.protokoll()}")


def test_er_endet_wenn_der_compositor_geht(buehne):
    """Und er bleibt nicht als Waise stehen.

    Ohne Compositor gibt es nichts zu bewachen. Ein Prozess, der dann
    weiterlaeuft, haengt an einem Socket, den es nicht mehr gibt - und
    steht bei der naechsten Anmeldung ein zweites Mal daneben.
    """
    waechter = buehne.stelle_alles_hin(["eDP-1"])
    buehne.starte(waechter)
    assert buehne.verbindung
    buehne.verbindung.close()

    ende = time.monotonic() + FRIST
    while time.monotonic() < ende:
        if buehne.kind and buehne.kind.poll() is not None:
            break
        time.sleep(0.1)

    assert buehne.kind and buehne.kind.poll() == 0, (
        f"nach dem Ende des Ereignisstroms laeuft er weiter "
        f"(poll: {buehne.kind.poll() if buehne.kind else 'kein Kind'}):\n"
        f"{buehne.protokoll()}")


def test_ohne_kennung_faengt_er_nicht_an(buehne):
    """HYPRLAND_INSTANCE_SIGNATURE ist der ganze Weg zum Socket.

    Ohne sie gibt es keinen Pfad, und ein Waechter, der es dennoch
    versuchte, raete eine Sitzung. Er soll enden und sagen, warum.
    """
    waechter = buehne.stelle_alles_hin(["eDP-1"])
    umgebung = buehne.umgebung()
    umgebung.pop("HYPRLAND_INSTANCE_SIGNATURE")
    python = shutil.which("python3")
    fertig = subprocess.run(
        [python, str(waechter)], env=umgebung, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, timeout=30)

    assert fertig.returncode == 1, (
        f"ohne Kennung endete er mit {fertig.returncode}:\n{fertig.stdout}")
    assert "HYPRLAND_INSTANCE_SIGNATURE" in fertig.stdout, (
        f"er sagt nicht, was fehlt:\n{fertig.stdout}")
