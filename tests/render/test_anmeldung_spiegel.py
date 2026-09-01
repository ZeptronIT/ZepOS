# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Anmeldung steht auf JEDEM Schirm - gemessen an echtem Hyprland.

WAS BESTELLT WURDE
    Der Nutzer am 01.09.2026: der Anmeldebildschirm verschwindet, sobald
    ein zweiter Monitor angesteckt wird. Er sah einen schwarzen Schirm
    ohne Anmeldung und kam nur ueber das GRUB-Menue zurueck ins System.
    Zwischen drei Wegen hat er gewaehlt: "Nur den echten Fix, dafuer
    richtig" - cage raus, Hyprland rein, Spiegelung auf alle Ausgaenge.
    Und dazu: "Kein Notausgang", also KEINE Zeitablauf-Umschaltung auf
    tuigreet.

DIE URSACHE, GEMESSEN am 01.09.2026
    src/bin/zepos-greeter rief `cage -s -d -- ...`. `cage -h` der Fassung
    0.3.1-1 kennt genau zwei Betriebsarten:

        -m extend  Extend the display across all connected outputs (default)
        -m last    Use only the last connected output

    Ohne -m gilt `extend`: cage baut aus allen Ausgaengen EINE Flaeche,
    und regreets einziges Fenster sitzt am Ursprung - also auf dem ersten
    Ausgang. Kommt ein Schirm dazu, aendert sich die Anordnung, und die
    Anmeldung liegt auf einem Schirm, auf den niemand schaut. Die
    Rueckfaelle des Skripts griffen nicht, weil cage nicht SCHEITERTE -
    es tat, was seine Vorgabe sagt.

WAS HIER GEMESSEN WIRD UND WAS NICHT
    Gemessen wird an einem VERSCHACHTELTEN Hyprland mit der
    AUSGELIEFERTEN Konfiguration - src/login/greeter-hyprland.conf, Byte
    fuer Byte dieselbe Datei, die zepos-config nach
    /etc/greetd/zepos-greeter-hyprland.conf legt - und mit dem ECHTEN
    src/bin/zepos-greeter-spiegel darin. Die Ausgaenge kommen ueber
    `hyprctl output create headless`, dieselbe Zeile, mit der
    tests/render/test_mehrschirm.py seinen zweiten Schirm ansteckt.

    NICHT gemessen wird, ob auf einem echten Kabel wirklich Licht
    ankommt. Ein gespiegelter Ausgang verliert sein wl_output - GEMESSEN
    am 01.09.2026: `grim -o HEADLESS-2` antwortet danach mit "unknown
    output 'HEADLESS-2'" -, also kann kein Bildschirmabzug den Inhalt
    eines Spiegels belegen. Was hier belegt wird, ist die Aussage des
    Compositors ueber sich selbst: `hyprctl monitors all` nennt fuer
    jeden Spiegel das Feld mirrorOf mit der ID seiner Quelle.

WAS HIER NICHT PASSIERT
    Nichts beruehrt die Sitzung des Menschen, der den Lauf gestartet hat.
    refuse_the_real_session() prueft vor JEDEM Kindprozess, dass
    XDG_RUNTIME_DIR und der Wayland-Socket nicht die des Nutzers sind,
    und `hyprctl` bekommt die Kennung genau dieses Compositors mit.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.lock.nested_compositor import (                       # noqa: E402
    SUN_PATH_MAX, host_wayland_socket, missing_tools,
    refuse_the_real_session,
)

ROOT = Path(__file__).resolve().parents[2]
GREETER_CONFIG = ROOT / "src" / "login" / "greeter-hyprland.conf"
SPIEGEL = ROOT / "src" / "bin" / "zepos-greeter-spiegel"
MASKE = ROOT / "src" / "bin" / "zepos-greeter-maske"

# Wie oft zepos-greeter-spiegel nachsieht. Steht im Skript als
# ZEPOS_SPIEGEL_INTERVALL und wird hier heruntergesetzt, damit ein Test
# nicht laenger wartet als noetig - der Wert im Betrieb ist 2 s.
INTERVALL = "0.4"

# Wie lange ein Test auf eine Aenderung wartet, bevor er sie fuer
# ausgeblieben haelt. Grosszuegig: gemessen wird das Ergebnis, nicht die
# Dauer, und ein zu knapper Wert macht aus einer langsamen Maschine
# einen Fehlbefund.
FRIST = 25.0

# Wie lange gewartet wird, bis zepos-greeter-spiegel eine neue Lage
# uebernommen hat. Es gibt dafuer nichts abzufragen - welchen Schirm das
# Skript sich gemerkt hat, steht in einer Shell-Variablen in einem
# fremden Prozess -, also wird gewartet, und zwar ein Mehrfaches des
# Abfrageintervalls oben.
SETZEN = 4 * float(INTERVALL)


def required() -> list[str]:
    return missing_tools("Hyprland", "hyprctl", "awk")


class Anmeldung:
    """Ein verschachteltes Hyprland mit der ausgelieferten Greeter-Datei.

    Jeder Prozess, den diese Klasse startet, steht in self.children, und
    beendet wird ausschliesslich, was dort steht. Kein pkill: ein
    Mustertreffer im Prozessbaum der Maschine faende das Hyprland des
    Nutzers.
    """

    def __init__(self) -> None:
        self.runtime = Path(tempfile.mkdtemp(prefix="zepanmeld-"))
        self.runtime.chmod(0o700)
        self.home = self.runtime / "home"
        (self.home / ".config").mkdir(parents=True)
        self.log = self.runtime / "hyprland.log"
        self.spiegel_log = self.runtime / "spiegel.log"
        self.maske_log = self.runtime / "maske.log"
        self.stubs = self.runtime / "stubs"
        self.stubs.mkdir()
        self.compositor: subprocess.Popen | None = None
        self.display: str | None = None

    # -- Umgebung ----------------------------------------------------

    def _basis(self, **extra: str) -> dict[str, str]:
        """Die gemeinsamen Werte - OHNE Pruefung, weil der Compositor
        selbst auf den Socket des Wirts zeigen MUSS."""
        environment = {
            # Der volle Suchpfad, mit dem Stub-Verzeichnis DAVOR: der
            # Compositor startet seine exec-once ueber `/bin/sh -c`, und
            # die sollen zepos-greeter-maske als Platzhalter und
            # zepos-greeter-spiegel als das ECHTE Skript finden. Dieselbe
            # Freiheit, die tests/render/desktop_session.py sich nimmt -
            # hier wird ein Compositor gemessen und kein Skript, und der
            # braucht sein Werkzeug.
            "PATH": f"{self.stubs}{os.pathsep}{os.environ.get('PATH', '/usr/bin')}",
            "HOME": str(self.home),
            "XDG_RUNTIME_DIR": str(self.runtime),
            "XDG_CACHE_HOME": str(self.home / ".cache"),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "HYPRLAND_NO_CRASHREPORTER": "1",
            "HYPRLAND_NO_SD_NOTIFY": "1",
            "ZEPOS_SPIEGEL_INTERVALL": INTERVALL,
            "ZEPOS_SPIEGEL_LOG": str(self.spiegel_log),
        }
        environment.update(extra)
        return environment

    def environment(self, **extra: str) -> dict[str, str]:
        """Die Umgebung fuer ein KIND, und sie wird geprueft.

        Der Compositor selbst bekommt sie nicht: er meldet sich als
        Fenster beim Wirt an, sein WAYLAND_DISPLAY IST also der Socket
        des Nutzers, und refuse_the_real_session() wuerde ihn zu Recht
        beanstanden. Dieselbe Trennung trifft
        tests/render/desktop_session.py in Session.start().
        """
        environment = self._basis(**extra)
        refuse_the_real_session(environment)
        return environment

    # -- Start -------------------------------------------------------

    def start(self, *, layout: str | None = None,
              timeout: float = 40.0) -> None:
        probe = self.runtime / "wayland-99"
        assert len(str(probe)) <= SUN_PATH_MAX, (
            f"{probe} ist {len(str(probe))} Bytes lang, sockaddr_un.sun_path "
            f"fasst {SUN_PATH_MAX}")
        host = host_wayland_socket()
        assert host is not None, (
            "Es laeuft keine Wayland-Sitzung, in die hinein verschachtelt "
            "werden koennte. Hyprland hat keinen Headless-Schalter.")

        # Das ECHTE Spiegel-Skript unter dem Namen, den die ausgelieferte
        # Konfiguration ruft. Ein Durchreicher und keine Kopie: waere es
        # eine Kopie, pruefte dieser Test eine Datei, die niemand
        # ausliefert.
        (self.stubs / "zepos-greeter-spiegel").write_text(
            f'#!/bin/bash\nexec "{SPIEGEL}" "$@"\n', encoding="utf-8")
        (self.stubs / "zepos-greeter-spiegel").chmod(0o755)

        # Die Maske dagegen IST ein Platzhalter: regreet ist auf dieser
        # Maschine nicht installiert, und die Frage dieser Datei ist die
        # Anordnung der Schirme und nicht das Aussehen der Maske. Er
        # haelt den Compositor am Leben, damit ueberhaupt etwas zu messen
        # ist - das echte zepos-greeter-maske misst tests/src/
        # test_login.py, dort wo es hingehoert.
        (self.stubs / "zepos-greeter-maske").write_text(
            "#!/bin/bash\n"
            f'printf "maske lief\\n" >>"{self.maske_log}"\n'
            "sleep 3600\n", encoding="utf-8")
        (self.stubs / "zepos-greeter-maske").chmod(0o755)

        # Der WIRT, als absoluter Pfad: hier meldet sich der
        # verschachtelte Compositor als gewoehnliches Fenster an. Das ist
        # die eine Umgebung, die NICHT durch refuse_the_real_session()
        # geht - sie zeigt absichtlich auf den Socket des Nutzers, und
        # der Nutzer bekommt davon ein Fenster und sonst nichts.
        environment = self._basis(WAYLAND_DISPLAY=str(host))
        if layout is not None:
            environment["XKB_DEFAULT_LAYOUT"] = layout

        with self.log.open("wb") as sink:
            self.compositor = subprocess.Popen(
                ["Hyprland", "-c", str(GREETER_CONFIG)],
                env=environment, stdout=sink, stderr=subprocess.STDOUT)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            found = sorted(path.name for path in self.runtime.iterdir()
                           if path.name.startswith("wayland-")
                           and not path.name.endswith(".lock"))
            if found:
                self.display = found[0]
                break
            if self.compositor.poll() is not None:
                raise AssertionError(
                    "Das verschachtelte Hyprland endete, bevor es einen "
                    "Socket hatte:\n" + self.read_log())
            time.sleep(0.05)
        assert self.display, f"kein Socket in {timeout} s:\n" + self.read_log()

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.json("monitors"):
                return
            time.sleep(0.2)
        raise AssertionError("der verschachtelte Compositor meldet keinen "
                             "Ausgang:\n" + self.read_log())

    # -- Steuerung ---------------------------------------------------

    def signature(self) -> str | None:
        directory = self.runtime / "hypr"
        if not directory.is_dir():
            return None
        entries = [path.name for path in directory.iterdir() if path.is_dir()]
        return entries[0] if len(entries) == 1 else None

    def hyprctl(self, *arguments: str) -> subprocess.CompletedProcess:
        signature = self.signature()
        assert signature, "der verschachtelte Compositor hat keine Kennung"
        assert self.display
        return subprocess.run(
            ["hyprctl", *arguments],
            env=self.environment(WAYLAND_DISPLAY=self.display,
                                 HYPRLAND_INSTANCE_SIGNATURE=signature),
            capture_output=True, text=True, timeout=20)

    def json(self, *arguments: str):
        if self.signature() is None:
            return None
        result = self.hyprctl("-j", *arguments)
        if result.returncode != 0:
            return None
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return None

    # -- Was der Compositor ueber seine Schirme sagt ------------------

    def sichtbare(self) -> list[str]:
        """Die Ausgaenge, die eine eigene Flaeche haben.

        `hyprctl monitors` fuehrt einen gespiegelten Ausgang NICHT mehr -
        gemessen am 01.09.2026. Genau das macht diese Liste zur Antwort
        auf "wie viele verschiedene Bilder zeigt diese Maschine".
        """
        return sorted(m["name"] for m in (self.json("monitors") or []))

    def alle(self) -> dict[str, str]:
        """{Name: mirrorOf} ueber ALLE Ausgaenge, auch die Spiegel.

        mirrorOf traegt die ID der Quelle als Zeichenkette, oder "none" -
        src/debug/HyprCtl.cpp:286 der ausgelieferten Fassung 0.56.1:
        `m->m_mirrorOf ? std::format("{}", m->m_mirrorOf->m_id) : "none"`.
        """
        return {m["name"]: m.get("mirrorOf")
                for m in (self.json("monitors", "all") or [])}

    def kennungen(self) -> dict[str, str]:
        return {m["name"]: str(m["id"])
                for m in (self.json("monitors", "all") or [])}

    def steck_an(self, timeout: float = FRIST) -> str:
        vorher = set(self.kennungen())
        ergebnis = self.hyprctl("output", "create", "headless")
        assert ergebnis.returncode == 0, (
            f"kein headless-Ausgang: {ergebnis.stdout}{ergebnis.stderr}")
        frist = time.monotonic() + timeout
        while time.monotonic() < frist:
            neu = sorted(set(self.kennungen()) - vorher)
            if neu:
                return neu[0]
            time.sleep(0.2)
        raise AssertionError("der angesteckte Ausgang ist nicht erschienen: "
                             f"{self.kennungen()}")

    def steck_ab(self, name: str, timeout: float = FRIST) -> None:
        ergebnis = self.hyprctl("output", "remove", name)
        assert ergebnis.returncode == 0, (
            f"{name} liess sich nicht abstecken: "
            f"{ergebnis.stdout}{ergebnis.stderr}")
        frist = time.monotonic() + timeout
        while time.monotonic() < frist:
            if name not in self.kennungen():
                return
            time.sleep(0.2)
        raise AssertionError(f"{name} steht immer noch da: {self.kennungen()}")

    def warte_bis(self, bedingung, timeout: float = FRIST):
        """Auf ein Ergebnis warten und das letzte zurueckgeben.

        Ohne Ausnahme: der Test soll seine EIGENE Meldung schreiben
        koennen, und die braucht den zuletzt gesehenen Zustand.
        """
        frist = time.monotonic() + timeout
        letzte = None
        while time.monotonic() < frist:
            letzte = bedingung()
            if letzte:
                return letzte
            time.sleep(0.25)
        return letzte

    # -- Ende --------------------------------------------------------

    def read_log(self) -> str:
        text = self.log.read_text(errors="replace") if self.log.exists() else ""
        spiegel = (self.spiegel_log.read_text(errors="replace")
                   if self.spiegel_log.exists() else "(kein Spiegelprotokoll)")
        return f"--- hyprland.log ---\n{text[-4000:]}\n--- spiegel ---\n{spiegel}"

    def _eigene_kinder(self) -> list[int]:
        """Die Prozesse, die NUR aus diesem Aufbau stammen koennen.

        Erkannt am eigenen Laufzeitverzeichnis in der Befehlszeile -
        /tmp/zepanmeld-<zufall>/..., von tempfile.mkdtemp vergeben. Es
        gibt kein Muster auf einen PROGRAMMNAMEN hier, und das ist der
        ganze Punkt: ein `pkill zepos-greeter-spiegel` faende auf einer
        Maschine, die gerade ZepOS installiert, den echten.
        """
        marke = str(self.runtime).encode()
        gefunden: list[int] = []
        for eintrag in Path("/proc").iterdir():
            if not eintrag.name.isdigit():
                continue
            try:
                zeile = (eintrag / "cmdline").read_bytes()
            except OSError:
                continue
            if marke in zeile:
                gefunden.append(int(eintrag.name))
        return gefunden

    def stop(self) -> None:
        if self.compositor and self.compositor.poll() is None:
            self.compositor.terminate()
            try:
                self.compositor.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.compositor.kill()
                self.compositor.wait(timeout=10)

        # UND DIE KINDER DES COMPOSITORS HINTERHER.
        #
        #     Hyprland startet seine exec-once ueber `fork` und setzt
        #     SA_NOCLDWAIT (src/main.cpp:44-52) - es beobachtet sie also
        #     nicht und nimmt sie beim Beenden auch nicht mit. GEMESSEN
        #     am 01.09.2026: nach einem Testlauf standen zehn
        #     zepos-greeter-maske-Platzhalter in der Prozessliste, jeder
        #     mit einem `sleep 3600` darin.
        #
        #     Im Betrieb raeumt greetd die Sitzung ab, dort faellt das
        #     nicht auf. Hier faellt es auf, und ein Testlauf, der
        #     Prozesse hinterlaesst, ist ein Testlauf, der die Maschine
        #     des Entwicklers vollstellt.
        for pid in self._eigene_kinder():
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        frist = time.monotonic() + 5.0
        while time.monotonic() < frist and self._eigene_kinder():
            time.sleep(0.1)
        for pid in self._eigene_kinder():
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    def __enter__(self) -> "Anmeldung":
        return self

    def __exit__(self, *_exception) -> None:
        self.stop()
        shutil.rmtree(self.runtime, ignore_errors=True)


# --------------------------------------------------------------------
# Die Messungen
# --------------------------------------------------------------------

@pytest.fixture(scope="module")
def spiegelung() -> dict:
    """Einer, zwei, drei Schirme - und einer, der mittendrin dazukommt."""
    fehlt = required()
    if fehlt:
        pytest.skip(f"fuer den Spiegellauf fehlt: {', '.join(fehlt)}")
    if host_wayland_socket() is None:
        pytest.skip("keine Wayland-Sitzung, in die hinein verschachtelt "
                    "werden koennte - Hyprland hat keinen Headless-Schalter")

    with Anmeldung() as sitzung:
        sitzung.start()

        # ZUERST DEN WIRTSAUSGANG LOSWERDEN, und das ist keine
        # Bequemlichkeit, sondern der Unterschied zwischen einem Test und
        # einem Test, der etwas misst.
        #
        #     Ein verschachteltes Hyprland hat den Ausgang seines
        #     Wirtsfensters (WAYLAND-1, Kennung 0), und der ist immer der
        #     erste - also waehlt zepos-greeter-spiegel IHN als Quelle.
        #     Die Frage "was passiert, wenn die Quelle abgesteckt wird"
        #     waere an ihm gar nicht zu stellen: auf echter Hardware ist
        #     jede Quelle ein DRM-Ausgang, und ein DRM-Ausgang geht.
        #
        #     Also kommt erst ein headless-Ausgang dazu, dann geht der
        #     Wirt, und ab hier sind ALLE Ausgaenge von derselben Sorte -
        #     jeder ansteckbar, jeder absteckbar.
        sitzung.steck_an()

        # UND ZWISCHENDURCH ABWARTEN, BIS DER SPIEGEL EINMAL DURCH IST.
        #
        #     Ohne diese Zeile hing der Aufbau an einem Wettlauf, und der
        #     hat am 01.09.2026 einen Fehlbefund erzeugt: wird der Wirt
        #     abgesteckt, bevor zepos-greeter-spiegel ueberhaupt zum
        #     ersten Mal gelaufen ist, faellt seine erste Quellenwahl auf
        #     eine Lage mit zwei Schirmen - und HYPRLAND VERGIBT DIE
        #     KENNUNG DES ABGESTECKTEN WIRTS NEU. Gemessen: der danach
        #     angesteckte HEADLESS-2 bekam die 0, also die des Wirts.
        #
        #     Das Ergebnis war trotzdem richtig - ein Bild auf allen
        #     Schirmen -, nur eben mit einer anderen Quelle als der Test
        #     erwartete. Ein Test, der das nicht abwartet, misst die
        #     Reihenfolge zweier Uhren und nicht das Verhalten.
        sitzung.warte_bis(
            lambda: len(sitzung.sichtbare()) == 1 and len(sitzung.alle()) == 2)
        sitzung.steck_ab("WAYLAND-1")

        # EIN Schirm. Der Normalfall, und er darf durch diese ganze
        # Anordnung nicht schlechter werden.
        einer = sitzung.warte_bis(
            lambda: sitzung.sichtbare() if len(sitzung.sichtbare()) == 1
            and len(sitzung.alle()) == 1 else None)
        allein = dict(sitzung.alle())

        # Und noch einmal warten, bis der Spiegel diesen einen Schirm als
        # seine Quelle uebernommen hat. Dieselbe Begruendung wie oben:
        # sonst faellt seine Wahl erst bei ZWEI Schirmen, und dann
        # entscheidet die neu vergebene Kennung.
        time.sleep(SETZEN)
        quelle_allein = sitzung.sichtbare()[0]

        # ZWEI: der angesteckte muss verschwinden - in einen Spiegel.
        zweiter = sitzung.steck_an()
        zu_zweit = sitzung.warte_bis(
            lambda: sitzung.alle() if len(sitzung.sichtbare()) == 1
            and len(sitzung.alle()) == 2 else None)
        quelle_zu_zweit = sitzung.sichtbare()[0] if zu_zweit else None

        # DREI, waehrend der Spiegel schon laeuft. Das ist die
        # Bestellung: ein Schirm, der NACH dem Start dazukommt.
        dritter = sitzung.steck_an()
        zu_dritt = sitzung.warte_bis(
            lambda: sitzung.alle() if len(sitzung.sichtbare()) == 1
            and len(sitzung.alle()) == 3 else None)

        kennungen = dict(sitzung.kennungen())
        sichtbar_zu_dritt = sitzung.sichtbare()
        quelle_zu_dritt = sichtbar_zu_dritt[0] if sichtbar_zu_dritt else None

        # UND JETZT FAELLT DIE QUELLE WEG. Der Fall, der einen schwarzen
        # Schirm ergaebe, wenn Hyprland einen Spiegel ohne Quelle
        # stehenliesse - und der, an dem am 01.09.2026 ein echter Fehler
        # in zepos-greeter-spiegel gefunden wurde. Die Begruendung steht
        # im Skript, am Aufruf von `dispatch forcerendererreload`.
        quelle = sichtbar_zu_dritt[0]
        sitzung.steck_ab(quelle)
        nach_verlust = sitzung.warte_bis(
            lambda: sitzung.alle() if len(sitzung.alle()) == 2
            and len(sitzung.sichtbare()) == 1 else None)
        sichtbar_nach_verlust = sitzung.sichtbare()

        protokoll = sitzung.read_log()

    return {"einer": einer, "allein": allein,
            "zweiter": zweiter, "zu_zweit": zu_zweit,
            "dritter": dritter, "zu_dritt": zu_dritt,
            "kennungen": kennungen,
            "sichtbar_zu_dritt": sichtbar_zu_dritt,
            "quelle_allein": quelle_allein,
            "quelle_zu_zweit": quelle_zu_zweit,
            "quelle_zu_dritt": quelle_zu_dritt,
            "quelle": quelle,
            "nach_verlust": nach_verlust,
            "sichtbar_nach_verlust": sichtbar_nach_verlust,
            "protokoll": protokoll}


def test_ein_einzelner_schirm_wird_nicht_angefasst(spiegelung):
    """Der Normalfall. Die Maschine der meisten Menschen hat EINEN
    Bildschirm, und fuer sie darf sich durch diese ganze Anordnung
    nichts aendern.

    Ein Spiegel auf sich selbst waere hier der naheliegende Fehler:
    src/output/Monitor.cpp:1345 der Fassung 0.56.1 faengt ihn zwar ab
    ("Cannot mirror self!"), aber ein Skript, das ihn ueberhaupt
    versucht, schreibt bei jedem Durchlauf eine Fehlerzeile in ein
    Protokoll, das auf einem Anmeldebildschirm niemand liest.
    """
    assert spiegelung["einer"] is not None, (
        "der Aufbau hat nie genau einen Schirm gehabt:\n"
        + spiegelung["protokoll"])
    assert len(spiegelung["einer"]) == 1, spiegelung["einer"]
    assert list(spiegelung["allein"].values()) == ["none"], (
        f"der einzige Schirm spiegelt etwas: {spiegelung['allein']}\n"
        + spiegelung["protokoll"])


def test_ein_zweiter_schirm_zeigt_dasselbe_bild(spiegelung):
    """DIE BESTELLUNG. Vor dem 01.09.2026 baute cage aus beiden
    Ausgaengen eine gemeinsame Flaeche und legte die Maske an den
    Ursprung - der zweite Schirm blieb schwarz.

    Gemessen wird an zwei Aussagen zugleich: es gibt nur noch EIN
    eigenstaendiges Bild (`hyprctl monitors` fuehrt Spiegel nicht), und
    der zweite Ausgang nennt die Quelle beim Namen (`monitors all`).
    """
    zu_zweit = spiegelung["zu_zweit"]
    assert zu_zweit is not None, (
        "der zweite Schirm wurde nicht gespiegelt:\n" + spiegelung["protokoll"])
    assert len(zu_zweit) == 2, zu_zweit
    gespiegelt = [name for name, ziel in zu_zweit.items() if ziel != "none"]
    quellen = [name for name, ziel in zu_zweit.items() if ziel == "none"]

    # GEPRUEFT WIRD DIE ZUSICHERUNG UND NICHT, WELCHER SCHIRM SIE
    # ERFUELLT.
    #
    #     Die Zusicherung lautet "beide Schirme zeigen dieselbe
    #     Anmeldung", und die ist erfuellt, sobald es genau EIN
    #     eigenstaendiges Bild gibt und der andere Ausgang darauf zeigt.
    #     WELCHER von beiden zeichnet, ist keine Zusicherung: alle zeigen
    #     dasselbe.
    #
    #     Hier stand bis zum 01.09.2026 `gespiegelt == [der eben
    #     angesteckte]`, und das war zu viel behauptet. Hyprland vergibt
    #     die Kennung eines abgesteckten Ausgangs neu, also kann der
    #     frisch angesteckte Schirm die NIEDRIGERE Kennung tragen und
    #     damit selbst zur Quelle werden. Gemessen genau so: HEADLESS-2
    #     bekam die 0 des abgesteckten Wirts. Der Test fiel durch,
    #     obwohl die Anmeldung auf beiden Schirmen stand.
    #
    #     Dass die Quelle nicht ohne Not wechselt, ist eine EIGENE
    #     Zusicherung und wird unten in
    #     test_die_quelle_wechselt_nicht_wenn_ein_schirm_dazukommt
    #     gemessen - dort, wo sie beobachtbar ist.
    assert len(quellen) == 1, (
        f"es gibt {len(quellen)} eigenstaendige Bilder statt einem: "
        f"{zu_zweit}\n" + spiegelung["protokoll"])
    assert len(gespiegelt) == 1, (
        f"es ist kein Schirm gespiegelt: {zu_zweit}\n"
        + spiegelung["protokoll"])
    assert spiegelung["zweiter"] in zu_zweit, (
        f"der angesteckte Schirm {spiegelung['zweiter']} taucht gar nicht "
        f"auf: {zu_zweit}\n" + spiegelung["protokoll"])


def test_ein_dritter_schirm_wird_auch_noch_eingefangen(spiegelung):
    """Nicht "der zweite", sondern "jeder weitere". Ein Skript, das nur
    den ersten Fremdschirm spiegelt, laesst am dritten Kabel genau den
    schwarzen Schirm stehen, um den es hier geht - und niemand faende
    das, weil zwei Monitore der haeufigste Fall sind.
    """
    zu_dritt = spiegelung["zu_dritt"]
    assert zu_dritt is not None, (
        "der dritte Schirm wurde nicht gespiegelt:\n"
        + spiegelung["protokoll"])
    assert len(zu_dritt) == 3, zu_dritt
    assert len(spiegelung["sichtbar_zu_dritt"]) == 1, (
        f"drei Ausgaenge zeigen {len(spiegelung['sichtbar_zu_dritt'])} "
        f"verschiedene Bilder: {zu_dritt}\n" + spiegelung["protokoll"])


def test_die_quelle_wechselt_nicht_wenn_ein_schirm_dazukommt(spiegelung):
    """Die Anmeldemaske soll nicht springen, waehrend jemand tippt.

    Die Maske liegt auf der Arbeitsflaeche der QUELLE. Wechselt die
    Quelle, wandert das Fenster mit - und wer gerade sein Passwort
    eingibt, sieht es umziehen.

    DIE ERSTE FASSUNG VON zepos-greeter-spiegel MACHTE GENAU DAS.
    Sie waehlte bei jedem Durchlauf neu die niedrigste Kennung, und
    HYPRLAND VERGIBT KENNUNGEN WIEDER: der am 01.09.2026 nach einem
    Abstecken angesteckte HEADLESS-2 bekam die 0 des verschwundenen
    Wirtsausgangs und wurde damit zur Quelle, obwohl schon eine dastand.
    Im Protokoll jenes Laufs:

        HEADLESS-1 zeigt jetzt HEADLESS-2
        HEADLESS-3 zeigt jetzt HEADLESS-2
        HEADLESS-3 zeigt jetzt HEADLESS-1

    Dreimal umgehaengt fuer ein Ergebnis, das jedes Mal gleich aussieht.
    Das Skript merkt sich seine Quelle seither und behaelt sie, solange
    es sie gibt.

    DER SCHRITT, AN DEM DAS UEBERHAUPT MESSBAR IST, IST DER ZWEITE UND
    NICHT DER DRITTE.
        Ein Schirm mit einer HOEHEREN Kennung als die stehende Quelle
        wuerde auch die alte Fassung nicht umhaengen - "die niedrigste"
        bleibt dann dieselbe. Der Unterschied zeigt sich nur, wenn eine
        NIEDRIGERE Kennung frei geworden ist und neu vergeben wird, und
        genau das richtet der Aufbau oben ein: der Wirtsausgang mit der
        Kennung 0 wird abgesteckt, die Quelle traegt danach die 1, und
        der naechste angesteckte Schirm bekommt die freie 0.

        Nachgeprueft am 01.09.2026: mit dieser Behebung bleibt die
        Quelle, ohne sie wandert sie auf den neuen Schirm. Der Vergleich
        weiter unten - zweiter zu drittem Schirm - laeuft mit, ist aber
        allein KEIN Nachweis: er hielt auch, als die Behebung
        versuchsweise wieder ausgebaut wurde.
    """
    allein = spiegelung["quelle_allein"]
    zu_zweit = spiegelung["quelle_zu_zweit"]
    zu_dritt = spiegelung["quelle_zu_dritt"]
    assert allein and zu_zweit and zu_dritt, (
        f"die Lage kam nicht zur Ruhe: allein {allein}, zu zweit "
        f"{zu_zweit}, zu dritt {zu_dritt}\n" + spiegelung["protokoll"])

    assert allein == zu_zweit, (
        f"die Quelle war {allein} und ist nach dem Anstecken des zweiten "
        f"Schirms {zu_zweit}. Der neue Schirm hat die frei gewordene "
        f"niedrigere Kennung bekommen und die Quelle an sich gezogen - "
        f"die Anmeldemaske ist damit umgezogen, waehrend jemand davor "
        f"sitzt:\n" + spiegelung["protokoll"])
    assert zu_zweit == zu_dritt, (
        f"die Quelle war {zu_zweit} und ist nach dem dritten Schirm "
        f"{zu_dritt}:\n" + spiegelung["protokoll"])


def test_jeder_spiegel_nennt_die_quelle_bei_ihrer_kennung(spiegelung):
    """Die Gegenprobe zu "es ist nur noch einer sichtbar".

    Ein Ausgang, den Hyprland ABGESCHALTET haette, verschwaende ebenfalls
    aus `hyprctl monitors` - und waere schwarz statt gespiegelt. Deshalb
    wird hier nicht die Abwesenheit geprueft, sondern das Ziel: mirrorOf
    muss die ID GENAU DES SCHIRMS tragen, der uebrig geblieben ist.
    """
    zu_dritt = spiegelung["zu_dritt"]
    kennungen = spiegelung["kennungen"]
    quelle = spiegelung["sichtbar_zu_dritt"][0]
    erwartet = kennungen[quelle]
    for name, ziel in zu_dritt.items():
        if name == quelle:
            assert ziel == "none", (
                f"die Quelle {name} spiegelt selbst auf {ziel}\n"
                + spiegelung["protokoll"])
        else:
            assert ziel == erwartet, (
                f"{name} spiegelt auf {ziel!r}, die Quelle {quelle} hat "
                f"aber die Kennung {erwartet!r}: {zu_dritt}\n"
                + spiegelung["protokoll"])


def test_faellt_die_quelle_weg_bleibt_ein_bild_stehen(spiegelung):
    """DER FALL, DER DEN RECHNER SONST VERSCHLIESST.

    Wenn die Quelle abgesteckt wird, haengen zwei Spiegel an einem
    Ausgang, den es nicht mehr gibt. Bliebe es dabei, waere JEDER
    verbliebene Schirm schwarz - und das ist genau der Zustand, aus dem
    der Nutzer am 01.09.2026 nur ueber das GRUB-Menue herauskam.

    GEMESSEN am 01.09.2026 an Hyprland 0.56: es bleibt NICHT dabei.
    src/output/Monitor.cpp:1334-1391 (setMirror) loest den Namen ueber
    State::monitorState()->query(); findet er nichts, nimmt er den Zweig
    "disable mirroring", setzt m_mirrorOf zurueck und ruft
    setupDefaultWS() - der Ausgang wird also ein gewoehnlicher. Der
    Spiegel faengt sich selbst.

    Und danach greift zepos-greeter-spiegel wieder und macht aus den zwei
    uebrig gebliebenen eigenstaendigen Bildern wieder eins.
    """
    nach = spiegelung["nach_verlust"]
    assert nach is not None, (
        "nach dem Verlust der Quelle kam die Anordnung nicht zur Ruhe:\n"
        + spiegelung["protokoll"])
    assert spiegelung["quelle"] not in nach, (
        f"{spiegelung['quelle']} ist abgesteckt und steht noch da: {nach}\n"
        + spiegelung["protokoll"])
    assert len(nach) == 2, nach
    assert len(spiegelung["sichtbar_nach_verlust"]) == 1, (
        "nach dem Verlust der Quelle zeigen "
        f"{len(spiegelung['sichtbar_nach_verlust'])} Ausgaenge verschiedene "
        f"Bilder statt einem: {nach}\n" + spiegelung["protokoll"])
    neue_quelle = spiegelung["sichtbar_nach_verlust"][0]
    for name, ziel in nach.items():
        if name != neue_quelle:
            assert ziel != "none", (
                f"{name} zeigt ein eigenes Bild statt des Anmeldeschirms: "
                f"{nach}\n" + spiegelung["protokoll"])


# --------------------------------------------------------------------
# Die Tastatur - an derselben ausgelieferten Datei
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
@pytest.mark.parametrize("layout,keymap", [
    # "de" waere hier wertlos: es ist die Belegung dieser Maschine, und
    # ein Test, der sie misst, faellt auch dann nicht durch, wenn die
    # Umgebung gar nicht ankommt.
    ("gb", "English (UK)"),
    ("de", "German"),
])
def test_die_belegung_der_maschine_erreicht_die_tastatur(layout, keymap):
    """AUF DIESEM BILDSCHIRM WIRD EIN PASSWORT VERDECKT GETIPPT.

    src/bin/zepos-greeter loest die Belegung aus /etc/vconsole.conf und
    /usr/share/systemd/kbd-model-map auf und legt sie in
    XKB_DEFAULT_LAYOUT ab. Unter cage kam sie an: wlroots baut seine
    Belegung ueber libxkbcommon, und ohne Angabe liest libxkbcommon
    XKB_DEFAULT_*.

    HYPRLAND TUT DAS NICHT VON SELBST, UND DAS IST DER GRUND FUER DIE
    ZWEI LEEREN ZEILEN IN src/login/greeter-hyprland.conf.
    GEMESSEN am 01.09.2026 an Hyprland 0.56.2, verschachtelt:

        ohne input-Sektion, XKB_DEFAULT_LAYOUT=de
            -> active_keymap = "English (US)"
        kb_layout leer, XKB_DEFAULT_LAYOUT=de
            -> active_keymap = "German"
        kb_layout leer, XKB_DEFAULT_LAYOUT=gb
            -> active_keymap = "English (UK)"

    Die Vorgabe ist naemlich nicht "leer", sondern "us":
    src/config/values/ConfigValues.cpp:272 der Fassung 0.56.1 fuehrt
    `MS<String>("input:kb_layout", "Appropriate XKB keymap parameter",
    "us", ...)`. Eine Konfiguration, die kb_layout nicht ausdruecklich
    leert, stellt also JEDE Maschine auf die amerikanische Belegung -
    genau der Fehler, den das Installationsmedium schon einmal hatte:
    `xyz-abc`, auf einer deutschen Tastatur getippt, kam als `xzy/abc`
    an. Auf einem Anmeldebildschirm ist das ein Konto, in das der
    Besitzer nicht mehr hineinkommt.
    """
    fehlt = required()
    if fehlt:
        pytest.skip(f"fuer den Spiegellauf fehlt: {', '.join(fehlt)}")
    if host_wayland_socket() is None:
        pytest.skip("keine Wayland-Sitzung, in die hinein verschachtelt "
                    "werden koennte")

    with Anmeldung() as sitzung:
        sitzung.start(layout=layout)
        geraete = sitzung.warte_bis(
            lambda: (sitzung.json("devices") or {}).get("keyboards"))
        assert geraete, ("der Compositor meldet keine Tastatur:\n"
                         + sitzung.read_log())
        belegungen = {k.get("active_keymap") for k in geraete}
        assert belegungen == {keymap}, (
            f"XKB_DEFAULT_LAYOUT={layout} ergab {belegungen} statt "
            f"{{{keymap!r}}} - die Belegung dieser Maschine erreicht die "
            f"Anmeldemaske nicht:\n" + sitzung.read_log())


def test_die_ausgelieferte_datei_setzt_keine_eigene_belegung():
    """Die Gegenprobe zum Test darueber, und sie liest statt auszufuehren.

    Ein `kb_layout = de` in dieser Datei waere genau der Fehler, den
    src/templates/hyprland-universal-config.template am 17.08.2026 fuer
    die SITZUNG behoben hat: eine englische Installation mit deutscher
    Tastatur. Die Zeile muss LEER sein, damit XKB_DEFAULT_LAYOUT gilt.
    """
    text = GREETER_CONFIG.read_text(encoding="utf-8")
    zeilen = [z.strip() for z in text.splitlines()]
    for schluessel in ("kb_layout", "kb_variant"):
        treffer = [z for z in zeilen if z.startswith(f"{schluessel}")]
        assert treffer, f"{schluessel} steht gar nicht in {GREETER_CONFIG.name}"
        for zeile in treffer:
            wert = zeile.split("=", 1)[1].strip() if "=" in zeile else "?"
            assert wert == "", (
                f"{GREETER_CONFIG.name} setzt {zeile!r}. Damit gilt diese "
                f"Belegung fuer JEDE Maschine, und XKB_DEFAULT_{schluessel.upper()[3:]} "
                f"aus src/bin/zepos-greeter kommt nicht mehr an.")
