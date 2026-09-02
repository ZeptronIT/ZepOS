# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Fensterrettung holt auch den KOPF auf den Schirm, nicht nur den Inhalt.

DER BEFUND - GEMESSEN am 02.09.2026 in einer verschachtelten Sitzung
    `hyprctl dispatch movewindowpixel "exact X Y"` setzt die Ecke des
    FENSTERINHALTS. Der hyprbars-Kopf ist eine reservierte Dekoration an
    der Oberkante (`info.edges = DECORATION_EDGE_TOP`, `info.reserved =
    true`, `desiredExtents = {{0, HEIGHT}, {0, 0}}` in
    hyprbars/barDeco.cpp) - er liegt also UEBER dieser Ecke.

    Gemessen an Hyprland 0.56.2 mit hyprbars, bar_height 25:

        movewindowpixel exact 100 0   ->  Inhalt y=0,  KOPF y=-25
        togglefloating (Vorgabelage)  ->  Inhalt y=-1, KOPF y=-26

    In beiden Faellen steht der Kopf mit den drei Knoepfen ausserhalb des
    Schirms. Genau das, was am 01.09.2026 gemeldet wurde: "der header wo
    x minimieren und vollbild ist [hat] keinen abstand zum oberen rand".

WARUM DIESE DATEI DIE RETTUNG PRUEFT UND NICHT DAS SCHILD
    hypr-window-rescue.sh ist der eine ZepOS-Schreiber, bei dem der
    Fehler nicht von einer Eingabe abhaengt, sondern GARANTIERT ist:

        ny = max(m['y'], min(y + m['y'], m['y'] + m['height'] - h))

    Die Untergrenze ist die Oberkante des Schirms. Jedes Fenster, das
    weit genug oben lag, landet also mit dem Inhalt auf y = m['y'] und
    mit dem Kopf darueber - ausserhalb. Und der Kopf des Skripts
    verspricht woertlich das Gegenteil: "Clamps so the window always
    lands fully inside the monitor".

    Das Werkzeug heisst Rettung. Es hat einen Zweck: ein Fenster, das
    man nicht sehen kann, wieder greifbar machen. Ohne Kopf ist es
    wieder nicht greifbar - die drei Knoepfe UND die Ziehflaeche sind
    genau das, was der Kopf traegt.

DAS VERFAHREN
    Das gerenderte Skript laeuft unter `env -i` mit einem
    Attrappenverzeichnis als GANZEM PATH. `hyprctl` ist eine Attrappe:
    sie antwortet auf `monitors`, `clients` und `getoption` aus
    vorgegebenen Dateien und SCHREIBT jedes `dispatch` mit. Damit ist
    gemessen, welche Koordinaten das Skript wirklich schickt - und kein
    Compositor wird angefasst.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

BASH = "/bin/bash"
ENV = "/usr/bin/env"

pytestmark = pytest.mark.allow_subprocess

KOPF = 25            # plugin:hyprbars:bar_height, wie ZepOS es setzt
RAND = 1             # general:border_size aus hyprland-universal-config


class Welt:
    """Das gerenderte Rettungsskript und eine erfundene Fensterlage."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.stubs = root / "stubs"
        self.stubs.mkdir(parents=True)
        self.antworten = root / "antworten"
        self.antworten.mkdir()
        self.dispatches = root / "dispatches"

        # `tr` braucht die Attrappe selbst, um den Optionsnamen in einen
        # Dateinamen zu uebersetzen. Ohne sie antwortet sie auf JEDE
        # Frage mit einem Fehler - und der Test waere gruen fuer den
        # falschen Grund, naemlich "es gibt keine Kopfhoehe".
        for name in ("jq", "cat", "date", "tr"):
            echt = _wo(name)
            if echt:
                self.stub(name, f'exec "{echt}" "$@"')
        self.stub("python3", f'exec "{sys.executable}" "$@"')
        self.stub("notify-send", "exit 0")

        # DIE hyprctl-ATTRAPPE. Sie antwortet aus Dateien und schreibt
        # jedes `dispatch` mit - eine Zusicherung darueber, WOHIN
        # geschoben wurde, ist nur so viel wert, wie jeder Schub
        # aufgeschrieben wird.
        self.stub("hyprctl", f"""
case "$1 $2" in
  "monitors -j")  exec cat '{self.antworten}/monitors.json' ;;
  "clients -j")   exec cat '{self.antworten}/clients.json' ;;
esac
if [ "$1" = "getoption" ]; then
    datei='{self.antworten}/getoption-'"$(printf '%s' "$2" | tr ':/' '__')"'.json'
    if [ -f "$datei" ]; then exec cat "$datei"; fi
    echo "no such option" >&2
    exit 1
fi
if [ "$1" = "dispatch" ]; then
    shift
    printf '%s\\n' "$*" >> '{self.dispatches}'
    exit 0
fi
exit 1
""")
        self.script = self._rendern()

    def stub(self, name: str, body: str) -> None:
        pfad = self.stubs / name
        pfad.write_text(f"#!/bin/bash\n{body}\n", encoding="utf-8")
        pfad.chmod(0o755)

    def _rendern(self) -> Path:
        sys.path.insert(0, str(SRC))
        try:
            import template_processor
            processor = template_processor.ConfigProcessor()
        finally:
            sys.path.remove(str(SRC))
        ziel = self.root / "hypr-window-rescue.sh"
        processor.apply_template(
            SRC / "templates" / "hypr-window-rescue-config.template", ziel)
        ziel.chmod(0o755)
        return ziel

    # -- die erfundene Lage -----------------------------------------

    def schirme(self, *monitore) -> None:
        (self.antworten / "monitors.json").write_text(
            json.dumps(list(monitore)), encoding="utf-8")

    def fenster(self, *clients) -> None:
        (self.antworten / "clients.json").write_text(
            json.dumps(list(clients)), encoding="utf-8")

    def option(self, name: str, wert: int) -> None:
        datei = self.antworten / (
            "getoption-" + name.replace(":", "_").replace("/", "_") + ".json")
        datei.write_text(json.dumps(
            {"option": name, "int": wert, "set": True}), encoding="utf-8")

    def geschoben(self) -> list[str]:
        if not self.dispatches.exists():
            return []
        return self.dispatches.read_text(encoding="utf-8").splitlines()

    def ziel(self) -> tuple[int, int]:
        """Die Koordinaten des einen Schubs."""
        zeilen = [z for z in self.geschoben() if "movewindowpixel" in z]
        assert len(zeilen) == 1, f"nicht genau ein Schub: {self.geschoben()}"
        teile = zeilen[0].split("exact ", 1)[1].split(",")[0].split()
        return int(teile[0]), int(teile[1])

    def lauf(self) -> subprocess.CompletedProcess:
        pfad = str(self.stubs)
        assert pfad.split(os.pathsep) == [pfad], "PATH traegt genau einen Eintrag"
        return subprocess.run(
            [ENV, "-i", f"PATH={pfad}", f"HOME={self.root}",
             BASH, str(self.script)],
            env={}, input="", capture_output=True, text=True, timeout=60)


def _wo(name: str) -> str:
    from shutil import which
    return which(name, path="/usr/bin:/bin:/usr/local/bin") or ""


def _schirm(ident=0, x=0, y=0, w=1920, h=1080) -> dict:
    return {"id": ident, "x": x, "y": y, "width": w, "height": h}


def _fenster(x, y, w=800, h=600, monitor=0, floating=True) -> dict:
    return {"address": "0x1", "at": [x, y], "size": [w, h],
            "floating": floating, "fullscreen": 0, "monitor": monitor,
            "title": "kitty", "class": "kitty"}


@pytest.fixture
def welt(tmp_path) -> Welt:
    w = Welt(tmp_path)
    w.schirme(_schirm())
    w.option("plugin:hyprbars:bar_height", KOPF)
    w.option("general:border_size", RAND)
    return w


# --------------------------------------------------------------------
# 1. Die Zusicherung, um die es geht
# --------------------------------------------------------------------

def test_der_kopf_landet_auf_dem_schirm_und_nicht_darueber(welt):
    """Ein weit oben liegendes Fenster wird MIT seinem Kopf gerettet.

    Der Fall, in dem der alte Anschlag zuschlaegt: das Fenster lag bei
    y = -4000 und damit vollstaendig ausserhalb. Der Anschlag hob es auf
    y = 0 - die Oberkante des Schirms - und schob damit die
    fuenfundzwanzig Punkte Kopf darueber hinaus.

    Verlangt wird die Aussage, die der Kopf des Skripts schon immer
    macht: "Clamps so the window always lands fully inside the
    monitor". Der Kopf IST Teil des Fensters; er traegt die drei Knoepfe
    und die Ziehflaeche, also genau das, was ein gerettetes Fenster
    greifbar macht.
    """
    welt.fenster_lage = None
    welt.fenster(_fenster(x=-4000, y=-4000))

    ergebnis = welt.lauf()
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr

    x, y = welt.ziel()
    assert y - KOPF - RAND >= 0, (
        f"der Inhalt landet auf y={y}, der Kopf also auf "
        f"y={y - KOPF - RAND} - {KOPF + RAND - y} Punkte ueber dem "
        "Schirmrand, und dort ist er nicht anfassbar")


def test_der_rand_zaehlt_mit(welt):
    """Nicht nur der Kopf - der Fensterrahmen liegt ebenfalls aussen.

    `general:border_size` ist 1 in hyprland-universal-config.template.
    Ein Punkt ist wenig und trotzdem der Unterschied zwischen "ganz
    drin" und "fast ganz drin"; die Zusicherung im Kopf des Skripts
    sagt ganz.
    """
    welt.fenster(_fenster(x=-4000, y=-4000))
    welt.lauf()

    _, y = welt.ziel()
    assert y >= KOPF + RAND, f"y={y} laesst {KOPF + RAND - y} Punkte aussen"


# --------------------------------------------------------------------
# 2. Was sich NICHT aendern darf
# --------------------------------------------------------------------

def test_ohne_hyprbars_bleibt_es_beim_alten_anschlag(welt):
    """Kein Plugin, kein Kopf, kein Aufschlag.

    `hyprctl getoption plugin:hyprbars:bar_height` antwortet auf einer
    Maschine ohne geladenes Plugin mit einem Fehler. Der Aufschlag muss
    dann NULL sein und nicht geraten: ein Fenster um
    fuenfundzwanzig Punkte nach unten zu schieben, wo es keinen Kopf
    gibt, waere ein Rand, den niemand bestellt hat.
    """
    (welt.antworten / "getoption-plugin_hyprbars_bar_height.json").unlink()
    welt.fenster(_fenster(x=-4000, y=-4000))
    welt.lauf()

    _, y = welt.ziel()
    assert y == RAND, f"ohne hyprbars landet der Inhalt auf y={y}, erwartet {RAND}"


def test_ein_sichtbares_fenster_wird_nicht_angefasst(welt):
    """Die Sicherheitsregel des Skripts, unberuehrt.

    Nur Fenster, die GANZ ausserhalb aller Schirme liegen, werden
    verschoben. Ein Fenster anzufassen, das der Nutzer gerade benutzt,
    waere schlimmer als eines liegenzulassen, das er nicht sieht.
    """
    welt.fenster(_fenster(x=100, y=100))

    welt.lauf()

    assert [z for z in welt.geschoben() if "movewindowpixel" in z] == [], (
        "ein sichtbares Fenster wurde verschoben: " + str(welt.geschoben()))


def test_ein_gekacheltes_fenster_wird_nicht_angefasst(welt):
    """Gekachelte Fenster legt das Layout, nicht dieses Skript."""
    welt.fenster(_fenster(x=-4000, y=-4000, floating=False))

    welt.lauf()

    assert [z for z in welt.geschoben() if "movewindowpixel" in z] == []


def test_die_untere_kante_bleibt_drin(welt):
    """Der Aufschlag oben darf das Fenster nicht unten hinausschieben.

    Ein Fenster, das fast so hoch ist wie der Schirm, hat oben und
    unten zusammen weniger Luft als Kopf und Rand brauchen. Dann gilt
    die OBERE Kante - ein Fenster, dessen Kopf man nicht fassen kann,
    ist unbrauchbar, eines, dessen Fuss ein Stueck ueberhaengt, nicht.
    Gemessen wird, dass die Entscheidung getroffen und nicht dem Zufall
    der Reihenfolge zweier Anschlaege ueberlassen wird.
    """
    welt.fenster(_fenster(x=-4000, y=-4000, w=800, h=1070))

    welt.lauf()

    _, y = welt.ziel()
    assert y >= KOPF + RAND, (
        f"der Kopf haengt oben hinaus (y={y}) - bei zu wenig Luft muss "
        "die obere Kante gewinnen")


def test_ein_fenster_auf_dem_zweiten_schirm_bleibt_dort(welt):
    """Der Aufschlag rechnet gegen die Oberkante DIESES Schirms.

    Zwei Schirme uebereinander sind der Fall, fuer den das Skript
    ueberhaupt gebaut wurde (ein wieder angestecktes Geraet mit
    globalem Versatz). Ein Aufschlag, der gegen 0 statt gegen m['y']
    rechnet, waere auf dem unteren Schirm um dessen Versatz falsch.
    """
    welt.schirme(_schirm(0, 0, 0, 1920, 1080),
                 _schirm(1, 0, 1080, 1920, 1080))
    welt.fenster(_fenster(x=-4000, y=-4000, monitor=1))

    welt.lauf()

    _, y = welt.ziel()
    assert y >= 1080 + KOPF + RAND, (
        f"y={y} liegt nicht auf dem zweiten Schirm samt Kopfabstand")
