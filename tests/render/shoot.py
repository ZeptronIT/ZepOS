# SPDX-License-Identifier: GPL-3.0-or-later
"""Bilder der erzeugten Oberflaeche machen - Leiste, Dock, Aufklappfenster.

    .venv/bin/python -m tests.render.shoot [--out VERZEICHNIS]

WAS DABEI ENTSTEHT, und warum genau diese Bilder
    schreibtisch-1920.png   Der ganze Schirm bei 1920x1080, mit der
                            ausgelieferten Tapete dahinter. Kopf und Fuss
                            auf EINEM Bild, weil der Nutzer verlangt hat,
                            dass beide gleich dick sind und denselben
                            Randabstand haben - eine Zahl kann das
                            behaupten, ein Bild zeigt es.
    leiste-1920.png         Nur der Kopfstreifen, ausgeschnitten.
    schreibtisch-1366.png   Derselbe Schreibtisch bei 1366x768 - der
                            verbreitetste Notebookschirm. Bis zum
                            12.08.2026 lagen dort sechs von achtzehn
                            Modulen hinter dem Einklapp-Knopf; seit dem
                            Umbau der Vorgabe steht die Leiste
                            vollstaendig darauf (COMPLETE_FROM in
                            tests/src/test_bar_headless.py). Das Bild
                            ist der Beleg dafuer.
    leiste-1366.png         Der Kopfstreifen davon.
    dock.png                Nur die Fusszeile, ausgeschnitten.
    kalender.png            Das Aufklappfenster des Datums.
    kontrollzentrum.png     Das Kontrollzentrum. Beide, weil der Nutzer
                            gemeldet hat, die Modale seien "zu hoch".

    Daneben schreibt jeder Lauf messwerte.txt: die Lage jeder
    Layer-Shell-Flaeche, so wie der Compositor sie kennt. Ein Bild ohne
    Koordinaten laesst sich beschreiben, aber nicht nachrechnen.

DIE BILDER GEHOEREN NICHT IN DEN COMMIT
    out/ steht in .gitignore. Was ein Bild belegt, gehoert in einen
    Bericht; was es zeigt, entsteht in zwei Minuten neu.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.render import desktop_session as session      # noqa: E402
from tests.render import measure                         # noqa: E402

# Wie lange die Oberflaeche Zeit bekommt, bevor abgezogen wird.
#
# Die Skriptmodule laufen ueber execAsync, und ein Modul vor seiner
# ersten Antwort ist ein unsichtbarer Kasten der Breite null. Ein Bild
# davon zeigte eine Leiste mit sieben Modulen weniger.
SETTLE = 6.0

# Wie lange ein Aufklappfenster braucht, bis es steht.
POPOVER_SETTLE = 2.5

# Die beiden Schirme.
#
#   1920x1080  Full HD, der Schirm, an dem die Groessen abgeleitet sind.
#   1366x768   der verbreitetste Notebookschirm ueberhaupt, und seit dem
#              12.08.2026 der bindende Fall: laut
#              tests/src/test_bar_headless.py (COMPLETE_FROM) muss die
#              ausgelieferte Leiste HIER vollstaendig ankommen. Ueberlauf
#              misst die Suite seither auf 1024.
SCREENS = ((1920, 1080), (1366, 768))


def _measure(shell_session, label: str) -> list[str]:
    """Die Lage jeder Flaeche, in den Koordinaten des Compositors."""
    lines = [f"[{label}] {shell_session.width}x{shell_session.height} "
             f"auf {shell_session.output}"]
    for namespace, (x, y, width, height) in sorted(
            shell_session.layers().items()):
        lines.append(f"    {namespace:20s} x={x:5d} y={y:5d} "
                     f"b={width:5d} h={height:5d}")
    return lines


def _crop(x: int, y: int, width: int, height: int) -> str:
    return f"{x},{y} {width}x{height}"


def desktop(width: int, height: int, build: Path, out: Path,
            report: list[str]) -> None:
    """Ein Schreibtisch dieser Groesse, abgebildet."""
    live = session.Session(width, height)
    try:
        live.start()
        live.start_bus()
        session.workspaces_file(build, live.output)
        live.wallpaper()
        time.sleep(2.0)
        # Der Schirm OHNE Oberflaeche. Er ist kein Beiwerk, sondern die
        # Vergleichsflaeche: erst der Unterschied zwischen diesem Bild
        # und dem naechsten sagt, welche Bildpunkte die Leiste wirklich
        # bemalt - also wie breit ihr Aussenrand ist und wo ihre Rundung
        # aufhoert.
        plain = live.shoot(out / f"nur-tapete-{width}.png")

        live.shell(build / "zepos-shell.js", build)
        time.sleep(SETTLE)

        report.extend(_measure(live, f"{width}x{height}"))
        places = live.layers()
        assert "zepos-bar" in places, (
            "es liegt keine Leiste auf dem Schirm:\n" + live.read_shell_log())
        assert "zepos-dock" in places, (
            "es liegt kein Dock auf dem Schirm:\n" + live.read_shell_log())

        dressed = live.shoot(out / f"schreibtisch-{width}.png")

        # Was davon wirklich Farbe bekommen hat. Die beiden Bereiche sind
        # das obere und das untere Drittel; sie muessen getrennt gemessen
        # werden, weil ein Rechteck um Kopf UND Fuss ueber keinen von
        # beiden etwas sagt.
        report.extend(measure.describe(plain, dressed, {
            "Kopf": (0, 0, width, height // 3),
            "Fuss": (0, height - height // 3, width, height // 3),
        }))

        # Und wie viel Tapete durch die beiden Flaechen noch zu sehen
        # ist. Gemessen INNERHALB der Flaeche, mit Abstand zu Rand und
        # Rundung, damit nicht die Kante die Antwort gibt.
        plain_image = measure.read_png(plain)
        dressed_image = measure.read_png(dressed)
        bar_x, bar_y, bar_w, bar_h = places["zepos-bar"]
        dock_x, dock_y, dock_w, dock_h = places["zepos-dock"]
        for name, box in (
                ("Kopf", (bar_x + 30, bar_y + 30, bar_w - 60, bar_h - 40)),
                ("Fuss", (dock_x + 10, dock_y + 10, dock_w - 20,
                          dock_h - 20))):
            report.append(f"    {name:12s} "
                          + measure.glass_probe(plain_image, dressed_image,
                                                box))

        # Der Kopfstreifen. Etwas hoeher als die Leiste, damit die
        # UNTERKANTE mit auf das Bild kommt: wo sie genau sitzt, ist die
        # halbe Frage.
        live.shoot(out / f"leiste-{width}.png",
                   _crop(0, 0, bar_w, min(bar_h + 40, height)))

        # Die Fusszeile, mit Luft ringsum - der Randabstand ist Teil der
        # Aussage, und die Tapete daneben ist der Beleg dafuer, ob das
        # Glas des Docks eines ist.
        margin = 40
        live.shoot(out / f"dock-{width}.png", _crop(
            max(dock_x - margin, 0), max(dock_y - margin, 0),
            min(dock_w + 2 * margin, width),
            min(dock_h + 2 * margin, height - max(dock_y - margin, 0))))

        # Die Aufklappfenster. Nur auf dem grossen Schirm, weil ein
        # Modal, das schon auf 1080 Zeilen zu hoch ist, auf 768 nichts
        # Neues zeigt - und weil es auf 1366 dieselbe Aussage waere.
        if (width, height) == (1920, 1080):
            # Der Zeiger dorthin, wo der Nutzer ihn haette: unter das
            # Modul, dessen Fenster gleich aufgeht. utils/overlay.ts
            # zentriert das Fenster WAAGERECHT AM ZEIGER - eine feste
            # Bildmitte waere eine Lage, die kein Klick je erzeugt.
            #
            # Das Datum steht links aussen, das Kontrollzentrum haengt
            # am Zahnrad rechts aussen.
            for request, name, cursor in (
                    ("calendar", "kalender", (180, bar_h + 10)),
                    ("control", "kontrollzentrum",
                     (width - 60, bar_h + 10))):
                live.move_cursor(*cursor)
                answer = live.request(request)
                time.sleep(POPOVER_SETTLE)
                report.append(f"    Zeiger {cursor}, ags request "
                              f"{request} -> {answer!r}")
                report.extend(_measure(live, f"nach {request}"))
                live.shoot(out / f"{name}.png")
                live.request(request)          # wieder zu
                time.sleep(1.0)

        log = live.read_shell_log()
        (out / f"shell-{width}.log").write_text(log, encoding="utf-8")
    finally:
        live.stop()


def provenance() -> list[str]:
    """Aus WELCHEM Baum diese Bilder stammen.

    WARUM DAS OBEN IN JEDER MESSDATEI STEHT
        Der Bildlauf verarbeitet die Vorlagen aus dem ARBEITSBAUM, nicht
        aus dem letzten Commit. An diesem Baum arbeiten mehrere Leute
        gleichzeitig; ein Bild ohne die Angabe, welcher Stand darauf zu
        sehen ist, laesst sich einen Tag spaeter niemandem mehr zuordnen.
        "Da war doch ein Bild" ist kein Beleg.
    """
    def git(*arguments: str) -> str:
        try:
            return subprocess.run(["git", "-C", str(ROOT), *arguments],
                                  capture_output=True, text=True,
                                  timeout=30).stdout.strip()
        except (OSError, subprocess.SubprocessError):        # pragma: no cover
            return "?"

    lines = [f"Stand: {git('rev-parse', '--short', 'HEAD')} "
             f"auf {git('rev-parse', '--abbrev-ref', 'HEAD')}"]
    dirty = [line for line in git("status", "--short").splitlines() if line]
    if dirty:
        lines.append("Nicht eingecheckte Aenderungen im Baum, aus dem diese "
                     "Bilder stammen:")
        lines.extend(f"    {line}" for line in dirty)
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path,
                        default=ROOT / "out" / "render")
    arguments = parser.parse_args()

    missing = session.required_tools()
    if missing:
        print("Diese Programme fehlen und ohne sie gibt es kein Bild: "
              + ", ".join(missing), file=sys.stderr)
        return 1

    out = arguments.out
    out.mkdir(parents=True, exist_ok=True)

    # DER BAUPLATZ LIEGT AUSSERHALB DES ARBEITSBAUMS, UND DAS IST GEMESSEN
    #     Er lag zuerst unter out/render/build/. Das erzeugte Buendel ist
    #     1,7 MB in EINER Zeile, und darin steht der ganze Quelltext noch
    #     einmal base64-kodiert. tests/src/test_inventory.py durchsucht
    #     das GANZE Verzeichnis - nicht nur src/ - nach den Namen, die
    #     aus dem Ursprungsprojekt nicht ueberleben duerfen, und seine
    #     Denkliste arbeitet mit Pruefsummen ueber Zeichengruppen. Auf
    #     1,7 MB Base64 trifft sie zufaellig, und der Lauf meldete
    #
    #         out/render/build/zepos-shell.js:5
    #
    #     Das war kein Fund, sondern ein Bauartefakt an einer Stelle, an
    #     der nur Quelltext stehen soll. Ein Bildlauf, der die Suite rot
    #     macht, ist ein Bildlauf, den niemand mehr startet.
    #
    #     Im Baum bleiben deshalb nur die BILDER und die Messwerte.
    build = Path(tempfile.mkdtemp(prefix="zepshot-bau-"))
    print(f"Bauplatz: {build}")
    ags = session.render_configuration(build)
    session.bundle(ags, build)

    report: list[str] = provenance()
    for width, height in SCREENS:
        desktop(width, height, build, out, report)

    (out / "messwerte.txt").write_text("\n".join(report) + "\n",
                                       encoding="utf-8")
    print("\n".join(report))
    print(f"\nBilder in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
