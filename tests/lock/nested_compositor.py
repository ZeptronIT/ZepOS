# SPDX-License-Identifier: GPL-3.0-or-later
"""Ein Compositor, in dem gesperrt werden darf - und niemals der echte.

WARUM ES DIESE DATEI GIBT UND NICHT tests/gtk4_headless.py REICHT
    Die Anzeige, auf der der Rest dieser Suite GTK4-Widgets baut, ist
    gtk4-broadwayd - GTKs eigener HTML5-Anzeigeserver. Er braucht kein
    Wayland, keine GPU und keine Hardware, und genau deshalb kann er
    hier nichts: ext-session-lock-v1 ist ein WAYLAND-Protokoll. Unter
    broadway antwortet gtk_session_lock_is_supported() mit FALSE, und
    ein Test, der dort liefe, wuerde messen, dass ein Programm ohne
    Protokoll nicht sperrt. Das ist wahr und uninteressant.

    Was gemessen werden muss, ist die Sperre selbst, und die gibt es nur
    bei einem Compositor, der das Protokoll spricht.

DIE EINE REGEL, DIE DIESE DATEI DURCHSETZT
    Auf der Sitzung des Nutzers wird NIE gesperrt. Ein Testlauf, der das
    taete, sperrte den Menschen aus, der ihn gestartet hat - und weil
    das Protokoll beim Absturz des Sperrprogramms ausdruecklich gesperrt
    BLEIBT (ext-session-lock-v1.xml, Zeile 111), waere das nicht einmal
    mit Strg-C zurueckzunehmen.

    Deshalb faehrt jeder Lauf in einem verschachtelten Hyprland mit
    EIGENEM XDG_RUNTIME_DIR, und refuse_the_real_session() unten prueft
    vor jedem Kindprozess nach, dass die Umgebung, die es bekommt,
    wirklich dorthin zeigt und nicht auf den Socket des Nutzers.

WAS DAS VERSCHACHTELN GEKOSTET HAT - GEMESSEN AM 12.08.2026
    * `Hyprland --socket NAME` gibt es, und es hilft nicht: der Aufruf
      bricht mit "Hyprland was launched with only one of --socket and
      --wayland-fd" ab. Der Schalter ist fuer die Socket-Uebergabe beim
      Sitzungsstart, nicht zum Benennen. Also bekommt der verschachtelte
      Compositor ein privates XDG_RUNTIME_DIR, legt dort seine
      wayland-N an und der Name wird danach GELESEN statt gesetzt.

    * Der erste Versuch legte dieses Verzeichnis unter den Arbeitsbaum
      dieses Zweiges, und Hyprland starb reihenweise mit

          error: socket path ".../scratchpad/zepos-lock/rt/wayland-16"
          plus null terminator exceeds 108 bytes

      dreiunddreissigmal, einmal je Anzeigenummer, und dann mit
      "m_szWLDisplaySocket was null!". sockaddr_un.sun_path ist 108
      Bytes, und der Pfad eines pytest-tmp_path kann mit einem langen
      Testnamen darueber hinauskommen. Deshalb liegt das Verzeichnis
      hier unter tempfile.gettempdir() mit einem kurzen Praefix, und
      seine Laenge wird geprueft, statt gehofft.

    * WAYLAND_DISPLAY darf ein ABSOLUTER Pfad sein, und das ist der
      Trick, mit dem beides zusammengeht: der verschachtelte Compositor
      bekommt XDG_RUNTIME_DIR=<privat> fuer seinen eigenen Socket und
      WAYLAND_DISPLAY=<voller Pfad zum Socket des Nutzers>, um sich beim
      Wirt anzumelden.

WAS DAS SICHTBAR KOSTET
    Ein Fenster. Der verschachtelte Compositor braucht einen Wirt, also
    erscheint waehrend dieser Tests je Test kurz ein Hyprland-Fenster auf
    dem Schirm dessen, der die Suite laufen laesst - etwa eine halbe
    Minute lang, ueber alle Tests dieses Verzeichnisses zusammen. Das
    ist nicht schoen und es ist die einzige Moeglichkeit: Hyprland hat
    keinen Headless-Backend-Schalter (siehe host_wayland_socket()), und
    gtk4-broadwayd, mit dem der Rest der Suite ohne Bildschirm auskommt,
    spricht das Protokoll nicht, um das es hier geht.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK_SOURCE = ROOT / "lock"

# sockaddr_un.sun_path, minus dem Nullbyte. Der Compositor legt
# <runtime>/wayland-N an, also muss der ganze Pfad hineinpassen.
SUN_PATH_MAX = 107

# Die Konfiguration des verschachtelten Compositors: so wenig wie
# moeglich, damit hier nicht die Vorlage dieses Projekts gemessen wird,
# sondern das Protokoll.
NESTED_CONFIG = """monitor = , 1280x800@60, 0x0, 1
misc {
    disable_hyprland_logo = true
    disable_splash_rendering = true
    force_default_wallpaper = 0
}
animations { enabled = false }
decoration { blur { enabled = false } }
"""


def missing_tools(*names: str) -> list[str]:
    """Welche der genannten Programme diese Maschine nicht hat.

    Als Liste und nicht als Wahrheitswert, damit die Uebersprungmeldung
    NENNT, was fehlt. Ein "skipped" ohne Grund ist ein Test, der
    aufgehoert hat zu messen, ohne dass es jemandem auffaellt.
    """
    return [name for name in names if shutil.which(name) is None]


def host_wayland_socket() -> Path | None:
    """Der Socket der laufenden Sitzung - der, auf dem NICHT gesperrt wird.

    None, wo es keinen gibt: dann laeuft die Suite in einem Container
    oder auf einer Textkonsole, und die Tests, die einen verschachtelten
    Compositor brauchen, koennen nicht laufen. Hyprland braucht einen
    Wirt; einen Headless-Schalter hat es nicht (`Hyprland --help` vom
    12.08.2026 nennt --config, --socket, --wayland-fd, --watchdog-fd,
    --safe-mode, --systeminfo, --verify-config und --version, und keinen
    davon).
    """
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    display = os.environ.get("WAYLAND_DISPLAY")
    if not runtime or not display:
        return None
    socket = Path(display) if display.startswith("/") else Path(runtime) / display
    return socket if socket.exists() else None


def refuse_the_real_session(environment: dict[str, str]) -> None:
    """Abbrechen, bevor ein Kind auf der Sitzung des Nutzers sperren kann.

    DIE ZUSICHERUNG, DIE ALLE ANDEREN TRAEGT. Jeder Kindprozess dieser
    Tests bekommt seine Umgebung durch diese Funktion. Sie prueft zwei
    Dinge, und beide sind noetig:

      * XDG_RUNTIME_DIR zeigt woanders hin als das des Nutzers. Ohne das
        legt der Compositor seinen Socket neben den echten, und ein
        Client, der wayland-1 sucht, findet moeglicherweise den echten.
      * Der Socket, auf den WAYLAND_DISPLAY zeigt, ist NICHT der der
        laufenden Sitzung.

    Der zweite Punkt allein reichte nicht: WAYLAND_DISPLAY ist oft nur
    ein Name wie "wayland-1", und derselbe Name bedeutet in zwei
    verschiedenen Laufzeitverzeichnissen zwei verschiedene Sockets.
    """
    host_runtime = os.environ.get("XDG_RUNTIME_DIR")
    child_runtime = environment.get("XDG_RUNTIME_DIR")
    assert child_runtime, (
        "Ein Kind ohne XDG_RUNTIME_DIR faende den Socket des Nutzers ueber "
        "libwaylands Vorgabe. Es darf nicht starten.")
    if host_runtime:
        assert Path(child_runtime).resolve() != Path(host_runtime).resolve(), (
            f"Das Kind soll in {child_runtime} laufen, und das IST das "
            "Laufzeitverzeichnis der Sitzung des Nutzers. Ein Sperrprogramm "
            "dort sperrt den Menschen aus, der diese Tests gestartet hat.")

    display = environment.get("WAYLAND_DISPLAY")
    assert display, "Ein Kind ohne WAYLAND_DISPLAY sucht sich einen Compositor."
    socket = (Path(display) if display.startswith("/")
              else Path(child_runtime) / display)
    host = host_wayland_socket()
    if host is not None:
        assert socket.resolve() != host.resolve(), (
            f"WAYLAND_DISPLAY zeigt auf {socket}, und das ist der Socket der "
            "laufenden Sitzung.")


def a_free_broadway_display(first: int = 300, tries: int = 50) -> int:
    """Eine Anzeigenummer, die auf DIESER MASCHINE gerade frei ist.

    Nicht eine feste Zahl, und das ist gemessen. tests/gtk4_headless.py
    beschreibt in refuse_a_foreign_display() in voller Laenge, warum die
    Nummer ein maschinenweiter Name ist, egal was XDG_RUNTIME_DIR sagt:
    broadwayd legt seinen Socket zusaetzlich unter dem echten
    Laufzeitverzeichnis an, und ein Client faende den fremden statt des
    eigenen.

    Der Fehler ist am 12.08.2026 in diesem Zweig noch einmal aufgetreten,
    mit einer festen 77: ein Handversuch hatte
    /run/user/1000/broadway78.socket liegen lassen, und der Test fiel
    danach bei jedem Lauf um. Eine feste Nummer ist auf einer Maschine,
    auf der mehrere Testlaeufe nebeneinander stattfinden koennen, kein
    Name, sondern eine Wette.

    Bei 300 angefangen, weil der Docstring dort broadway auf :300 als
    freilaufend gemessen hat und die niedrigen Nummern die sind, die
    andere Tests dieser Suite belegen.
    """
    machine_runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not machine_runtime:
        return first
    for display in range(first, first + tries):
        if not (Path(machine_runtime) / f"broadway{display + 1}.socket").exists():
            return display
    raise AssertionError(
        f"keine freie broadway-Anzeigenummer zwischen {first} und "
        f"{first + tries} in {machine_runtime}")


def build(name: str, sources: list[Path], workdir: Path,
          extra_defines: list[str] | None = None) -> Path:
    """Uebersetzt C-Quellen zu einem Programm und gibt den Pfad zurueck.

    Mit gcc und pkg-config statt mit meson, und das ist eine bewusste
    Arbeitsteilung: das AUSGELIEFERTE Programm baut
    tests/lock/test_lock_screen.py mit lock/meson.build, damit auch das
    Bauskript gemessen wird. Diese Funktion ist fuer die MUTANTEN - die
    absichtlich falschen Fassungen, an denen geprueft wird, ob eine
    Zusicherung ihren Fehler ueberhaupt faengt. Fuer die waere ein
    eigener meson-Baum je Mutant Aufwand ohne Ertrag.
    """
    flags = subprocess.run(
        ["pkg-config", "--cflags", "--libs", "gtk4", "gtk4-layer-shell-0"],
        capture_output=True, text=True, check=True).stdout.split()
    binary = workdir / name
    command = ["gcc", "-o", str(binary), *(str(path) for path in sources),
               f"-I{LOCK_SOURCE}", '-DZEPOS_LOCK_VERSION="test"',
               *(extra_defines or []), *flags, "-lpam"]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, (
        f"{name} liess sich nicht uebersetzen:\n{result.stderr}")
    return binary


class NestedHyprland:
    """Ein Hyprland im Hyprland, mit eigenem Laufzeitverzeichnis."""

    def __init__(self) -> None:
        self.runtime = Path(tempfile.mkdtemp(prefix="zeplock-"))
        self.runtime.chmod(0o700)
        self.home = self.runtime / "home"
        self.home.mkdir()
        self.process: subprocess.Popen | None = None
        self.display: str | None = None
        self.log = self.runtime / "hyprland.log"

    def start(self, timeout: float = 30.0) -> None:
        # Der Socket, den der Compositor gleich anlegt, muss in
        # sockaddr_un passen. Lieber hier sagen, als dreiunddreissig
        # Fehlversuche im Protokoll suchen.
        probe = self.runtime / "wayland-99"
        assert len(str(probe)) <= SUN_PATH_MAX, (
            f"{probe} ist {len(str(probe))} Bytes lang, und sockaddr_un.sun_"
            f"path fasst {SUN_PATH_MAX}. Der Compositor koennte seinen Socket "
            "nicht anlegen.")

        host = host_wayland_socket()
        assert host is not None, (
            "Es laeuft keine Wayland-Sitzung, in die hinein verschachtelt "
            "werden koennte.")

        config = self.runtime / "hyprland.conf"
        config.write_text(NESTED_CONFIG, encoding="utf-8")

        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin"),
            "HOME": str(self.home),
            "XDG_RUNTIME_DIR": str(self.runtime),
            # Der WIRT, als absoluter Pfad - das ist der eine Fall, in dem
            # ein Kind dieser Tests den echten Socket sehen darf: es meldet
            # sich dort als gewoehnliches Fenster an, es sperrt dort nicht.
            "WAYLAND_DISPLAY": str(host),
            "HYPRLAND_NO_CRASHREPORTER": "1",
            "HYPRLAND_NO_SD_NOTIFY": "1",
            "XDG_CACHE_HOME": str(self.home / "cache"),
            "XDG_CONFIG_HOME": str(self.home / "config"),
        }
        with self.log.open("wb") as sink:
            self.process = subprocess.Popen(
                ["Hyprland", "-c", str(config)],
                env=environment, stdout=sink, stderr=subprocess.STDOUT)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            found = sorted(path.name for path in self.runtime.iterdir()
                           if path.name.startswith("wayland-")
                           and not path.name.endswith(".lock"))
            if found:
                self.display = found[0]
                return
            if self.process.poll() is not None:
                raise AssertionError(
                    "Das verschachtelte Hyprland endete, bevor es einen "
                    "Socket hatte:\n"
                    + self.log.read_text(encoding="utf-8", errors="replace"))
            time.sleep(0.05)
        self.stop()
        raise AssertionError(
            "Das verschachtelte Hyprland hat in "
            f"{timeout} s keinen Socket angelegt:\n"
            + self.log.read_text(encoding="utf-8", errors="replace"))

    def environment(self, **extra: str) -> dict[str, str]:
        """Die Umgebung fuer ein Kind IN diesem Compositor - geprueft."""
        assert self.display is not None, "start() wurde nicht gerufen"
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin"),
            "HOME": str(self.home),
            "XDG_RUNTIME_DIR": str(self.runtime),
            "WAYLAND_DISPLAY": self.display,
            "XDG_CACHE_HOME": str(self.home / "cache"),
            "XDG_CONFIG_HOME": str(self.home / "config"),
            "GDK_BACKEND": "wayland",
            # Ohne das sucht GTK den Zugaenglichkeitsbus der echten
            # Sitzung und schreibt eine Zeile Gtk-CRITICAL, die in jeder
            # Ausgabe steht, die ein Test liest.
            "NO_AT_BRIDGE": "1",
            "GTK_A11Y": "none",
            "LC_ALL": "C",
        }
        environment.update(extra)
        refuse_the_real_session(environment)
        return environment

    def signature(self) -> str | None:
        """Die Instanzkennung, mit der hyprctl DIESEN Compositor findet."""
        directory = self.runtime / "hypr"
        if not directory.is_dir():
            return None
        entries = [path.name for path in directory.iterdir() if path.is_dir()]
        return entries[0] if len(entries) == 1 else None

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:      # pragma: no cover
                self.process.kill()
                self.process.wait(timeout=10)
        self.process = None
        shutil.rmtree(self.runtime, ignore_errors=True)
