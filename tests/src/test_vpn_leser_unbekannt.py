# SPDX-License-Identifier: GPL-3.0-or-later
"""Die zwei Shell-Leser von `vpn.py --status` und das vierte Wort.

WORUM ES GEHT
    Vier Stellen lesen die eine Zeile, die `vpn.py --status` schreibt.
    Zwei davon sind Shell-Skripte, und beide hatten am 01.09.2026
    dasselbe Loch: ein Wort, das sie nicht kennen, faellt bei ihnen auf
    "es laeuft nichts" durch.

        src/templates/ags-network-scripts.template::vpn_info
            kennt `connected` und `stale`, alles andere faellt in den
            Rueckfall - und der fragt NETWORKMANAGER ein zweites Mal.
            Bei `unknown` ist das genau der Dienst, der eben nicht
            geantwortet hat: er faende nichts und schriebe "Aus".

        src/templates/vpn-control-config.template::read_vpn_state
            setzte eine leere Antwort auf "disconnected" und reichte
            das an `status` und an den Umschalter weiter.

    Der Unterschied, um den es geht, steht in src/vpn.py bei UNKNOWN:
    "getrennt" ist eine Aussage ueber den Tunnel, "niemand antwortet"
    ist das Fehlen einer. Wer das zweite als das erste anzeigt,
    behauptet etwas ueber den Schutz des Nutzers, das gerade niemand
    weiss.

DAS VERFAHREN - AUSGEFUEHRT, NICHT DURCHSUCHT
    Beide Vorlagen werden gerendert und unter `env -i` mit einem
    Attrappenverzeichnis als GANZEM PATH ausgefuehrt. `--status` selbst
    kommt aus einer ATTRAPPE: ZEPOS_SYSTEM_ROOT zeigt beim Rendern auf
    ein Verzeichnis, in dem ein vier Zeilen langes vpn.py liegt, das
    genau ein Wort schreibt.

    Das ist Absicht und keine Bequemlichkeit. Gemessen wird hier, was
    die LESER aus einem Wort des Vertrags machen; dass src/vpn.py das
    richtige Wort schreibt, misst tests/src/test_vpn_unbekannt.py. Das
    echte Modul zu benutzen hiesse, in jeder Zusicherung beide Fragen
    auf einmal zu stellen und bei einem Fehlschlag nicht zu wissen,
    welche der beiden ihn hat.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.vpn import STATUS_WORDS

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

BASH = "/bin/bash"
ENV = "/usr/bin/env"

pytestmark = pytest.mark.allow_subprocess

# Die Werkzeuge, die die beiden Skripte fuer den STATUS-Weg wirklich
# brauchen. Durchgereicht wird nur, was nichts ueber die Maschine
# verraet und nichts an ihr aendert - `nmcli`, `pgrep` und `ip` gehoeren
# ausdruecklich NICHT dazu und sind Attrappen, die ihren Aufruf
# mitschreiben.
DURCHGEREICHT = ("date", "mkdir", "id", "cat", "sed", "grep", "awk", "tr",
                 "command")


class Welt:
    """Ein gerendertes Skript und die Attrappenwelt, in der es laeuft."""

    def __init__(self, root: Path, vorlage: str, wort: str) -> None:
        self.root = root
        self.stubs = root / "stubs"
        self.stubs.mkdir(parents=True)
        self.aufrufe = root / "aufrufe"
        self.runtime = root / "run"
        self.runtime.mkdir()
        self.runtime.chmod(0o700)
        self.home = root / "home"
        self.home.mkdir()

        for name in DURCHGEREICHT:
            echt = _wo(name)
            if echt:
                self.stub(name, f'exec "{echt}" "$@"')

        # Der Interpreter unter dem Namen, unter dem das Kind ihn ruft -
        # absolut benannt, damit das Finden nicht vom Attrappen-PATH
        # abhaengt. Dieselbe Bauart wie die Sandbox in
        # tests/src/test_bar_vpn.py.
        self.stub("python3", f'exec "{sys.executable}" "$@"')

        # Jedes Werkzeug, mit dem ein Skript die Lage der Maschine
        # abfragen oder aendern koennte, schreibt seinen Aufruf ZUERST
        # mit. Eine Zusicherung darueber, was NICHT gerufen wurde, ist
        # nur so viel wert, wie jeder Aufruf aufgeschrieben wird.
        for name in ("nmcli", "pgrep", "ip", "swanctl", "systemctl", "sudo",
                     "notify-send"):
            self.mitschreibende_attrappe(name, "exit 1")

        self.system_root = root / "system"
        self.system_root.mkdir()
        (self.system_root / "vpn.py").write_text(
            "import sys\nprint({!r})\n".format(wort), encoding="utf-8")

        self.script = self._rendern(vorlage)

    def _rendern(self, vorlage: str) -> Path:
        sys.path.insert(0, str(SRC))
        try:
            import template_processor
            processor = template_processor.ConfigProcessor(
                paths={"ZEPOS_SYSTEM_ROOT": str(self.system_root)})
        finally:
            sys.path.remove(str(SRC))
        ziel = self.root / vorlage.replace(".template", "")
        processor.apply_template(SRC / "templates" / vorlage, ziel)
        ziel.chmod(0o755)
        return ziel

    def stub(self, name: str, body: str) -> None:
        pfad = self.stubs / name
        pfad.write_text(f"#!/bin/bash\n{body}\n", encoding="utf-8")
        pfad.chmod(0o755)

    def mitschreibende_attrappe(self, name: str, body: str) -> None:
        self.stub(name, f"printf '{name} %s\\n' \"$*\" >> '{self.aufrufe}'\n"
                        + body)

    def notierte_aufrufe(self) -> list[str]:
        if not self.aufrufe.exists():
            return []
        return self.aufrufe.read_text(encoding="utf-8").splitlines()

    def lauf(self, *argumente: str) -> subprocess.CompletedProcess:
        pfad = str(self.stubs)
        assert pfad.split(os.pathsep) == [pfad], "PATH traegt genau einen Eintrag"
        return subprocess.run(
            [ENV, "-i", f"PATH={pfad}", f"HOME={self.home}",
             f"XDG_RUNTIME_DIR={self.runtime}",
             f"XDG_CONFIG_HOME={self.home}/.config",
             BASH, str(self.script), *argumente],
            env={}, input="", capture_output=True, text=True, timeout=60)


def _wo(name: str) -> str:
    """Wo ein Werkzeug wirklich liegt - oder "" fuer ein eingebautes."""
    from shutil import which
    return which(name, path="/usr/bin:/bin:/usr/local/bin") or ""


# --------------------------------------------------------------------
# 1. Die Netzuebersicht
# --------------------------------------------------------------------

def _netz(tmp_path, wort: str) -> Welt:
    return Welt(tmp_path / wort, "ags-network-scripts.template", wort)


def test_die_netzuebersicht_sagt_unbekannt_statt_aus(tmp_path):
    """`unknown` darf nicht in den NetworkManager-Rueckfall laufen.

    Der Rueckfall unter dem `case` fragt `nmcli con show --active` -
    also genau den Dienst, dessen Schweigen dieses Wort ueberhaupt
    ausgeloest hat. Ohne eigenen Zweig laeuft die Funktion bis ans Ende
    durch und schreibt "Aus".

    "Aus" ist eine Aussage: es laeuft kein VPN. Sie steht in der
    Netzuebersicht neben WLAN und Kabel, dort, wo der Nutzer nachsieht,
    bevor er etwas Vertrauliches tut - und sie ist an dieser Stelle
    nicht bekannt.
    """
    welt = _netz(tmp_path, "unknown")

    ergebnis = welt.lauf("vpn")

    assert ergebnis.stdout.strip() == "Unbekannt", (
        ergebnis.stdout + ergebnis.stderr)
    assert ergebnis.stdout.strip() != "Aus"


def test_die_netzuebersicht_fragt_bei_unbekannt_nicht_noch_einmal(tmp_path):
    """Und sie fragt den stummen Dienst kein zweites Mal.

    Die Zusicherung, ohne die die erste nur die Zeichenkette prueft:
    ein Zweig, der das richtige Wort schreibt und trotzdem vorher den
    Rueckfall durchlaeuft, waere gruen - und wuerde bei jedem Takt der
    Uhr einen Unterprozess gegen einen Dienst starten, der nicht
    antwortet.
    """
    welt = _netz(tmp_path, "unknown")

    welt.lauf("vpn")

    assert [zeile for zeile in welt.notierte_aufrufe()
            if zeile.startswith("nmcli")] == [], welt.notierte_aufrufe()


@pytest.mark.parametrize("wort,erwartet", [
    ("connected", "Verbunden"),
    ("stale", "Unvollständig"),
])
def test_die_anderen_woerter_sind_unberuehrt(tmp_path, wort, erwartet):
    """Die Zweige, die es schon gab, antworten wie vorher."""
    welt = _netz(tmp_path, wort)

    assert welt.lauf("vpn").stdout.strip() == erwartet


def test_getrennt_faellt_weiterhin_auf_den_networkmanager_zurueck(tmp_path):
    """`disconnected` behaelt seinen Weg - der Umbau ist additiv.

    Das ist der Zweig, der KEINEN eigenen Fall bekommt, und mit Absicht:
    NetworkManager kann eine aktive VPN-Verbindung fuehren, von der
    vpn.py nichts weiss (eine, die der Nutzer selbst angelegt hat).
    Genau dafuer gibt es den Rueckfall, und `disconnected` ist die
    Auskunft, bei der er etwas finden KANN.
    """
    welt = _netz(tmp_path, "disconnected")

    ergebnis = welt.lauf("vpn")

    assert ergebnis.stdout.strip() == "Aus", ergebnis.stdout
    assert [zeile for zeile in welt.notierte_aufrufe()
            if zeile.startswith("nmcli")] != [], (
        "der Rueckfall hat NetworkManager gar nicht gefragt")


# --------------------------------------------------------------------
# 2. Der Schalter - eine Durchreiche, keine zweite Meinung
# --------------------------------------------------------------------

def _schalter(tmp_path, wort: str) -> Welt:
    return Welt(tmp_path / wort, "vpn-control-config.template", wort)


@pytest.mark.parametrize("wort", sorted(STATUS_WORDS))
def test_der_schalter_reicht_jedes_wort_des_vertrags_durch(tmp_path, wort):
    """`status` gibt weiter, was es bekommt - alle vier Woerter.

    Die Liste kommt aus vpn.STATUS_WORDS und nicht aus einer eigenen
    Aufzaehlung: eine getippte waere die naechste Menge, die veraltet,
    und ein fuenftes Wort soll diese Zusicherung umwerfen statt still
    an ihr vorbeizugehen.
    """
    welt = _schalter(tmp_path, wort)

    ergebnis = welt.lauf("status")

    assert ergebnis.stdout.strip() == wort, ergebnis.stdout + ergebnis.stderr


def test_eine_leere_antwort_heisst_unbekannt_und_nicht_getrennt(tmp_path):
    """Der Rueckfall im Skript selbst - dieselbe Frage eine Ebene hoeher.

    Hier stand `${VPN_STATE:-disconnected}`. Antwortet vpn.py gar nicht
    - es fehlt, es stuerzt ab, python3 ist nicht da -, dann WEISS
    dieses Skript nichts, und "der Tunnel steht nicht" ist eine
    Behauptung darueber.
    """
    welt = Welt(tmp_path / "stumm", "vpn-control-config.template", "")
    (welt.system_root / "vpn.py").write_text(
        "import sys\nsys.exit(1)\n", encoding="utf-8")

    assert welt.lauf("status").stdout.strip() == "unknown"


def test_der_umschalter_handelt_bei_unbekannt_nicht(tmp_path):
    """Ein Umschalter braucht eine Ausgangslage, und hier gibt es keine.

    DIE EINE STELLE, AN DER DER VIERTE ZUSTAND NICHT ADDITIV WAERE
        `toggle` verband bisher, wenn der Zustand "disconnected" war,
        und trennte sonst. Ein nicht antwortendes nmcli hiess bis zum
        01.09.2026 "disconnected" - der Griff verband also, sinnlos,
        aber harmlos. Mit dem vierten Wort und OHNE eigenen Zweig waere
        daraus das Gegenteil geworden: "nicht disconnected" heisst
        trennen, und ein Griff, der einen vielleicht stehenden Tunnel
        abbaut, weil gerade niemand nachsehen kann, ist genau der
        Schaden, gegen den es den Zustand gibt.

        Also wird nichts getan und gesagt, warum. Gemessen wird beides:
        dass kein Werkzeug angefasst wurde, und dass der Rueckgabewert
        die Untaetigkeit meldet, statt Erfolg zu behaupten.
    """
    welt = _schalter(tmp_path, "unknown")

    ergebnis = welt.lauf("toggle")

    assert ergebnis.returncode != 0, ergebnis.stdout + ergebnis.stderr
    gehandelt = [zeile for zeile in welt.notierte_aufrufe()
                 if zeile.split(" ", 1)[0] in ("swanctl", "systemctl", "sudo")]
    assert gehandelt == [], (
        "der Umschalter hat auf einen unbekannten Zustand hin gehandelt: "
        + str(gehandelt))


def test_der_umschalter_sagt_warum_er_nicht_gehandelt_hat(tmp_path):
    """Und er sagt es dem NUTZER, nicht nur dem Protokoll.

    Ein Griff, der nichts tut und nichts sagt, ist von einem kaputten
    Griff nicht zu unterscheiden - der Nutzer drueckt ein zweites und
    ein drittes Mal. Die Meldung muss ausserdem den Unterschied
    aussprechen, um den es geht, und nicht bloss "Fehler" sagen.
    """
    welt = _schalter(tmp_path, "unknown")

    welt.lauf("toggle")

    meldungen = [zeile for zeile in welt.notierte_aufrufe()
                 if zeile.startswith("notify-send")]
    assert meldungen, welt.notierte_aufrufe()
    text = "\n".join(meldungen)
    assert "unbekannt" in text.lower(), text
    assert "NetworkManager antwortet nicht" in text, text
