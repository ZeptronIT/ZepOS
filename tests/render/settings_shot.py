#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Ein Bild der Einstellungs-App - besonders der Seite "Leiste".

WARUM ES DIESE DATEI GIBT
    shoot.py bildet den Schreibtisch ab: Leiste, Dock, Aufklappfenster.
    Die Einstellungs-App ist kein Layer-Shell-Streifen, sondern ein
    gewoehnliches Fenster, und sie faellt deshalb durch dieses Raster.

    Am 12.08.2026 hat sie eine siebte Seite bekommen, mit der der Nutzer
    Module der Leiste und Anheftungen des Docks entfernt, sortiert und
    zuruecksetzt. Sie ist die Antwort auf einen Satz, den er zweimal
    gesagt hat - zuletzt: "genau sowas will ich im ZepOS zu customizen".

    Eine Zusicherung kann pruefen, dass ein Knopf `null` schreibt. Ob die
    Seite BENUTZBAR aussieht - ob die Zeilen nicht quetschen, ob die drei
    Gruppen auseinanderzuhalten sind, ob der Rueckweg auffaellt - steht
    in keinem Testergebnis. Genau diese Luecke hat dieses Projekt
    vierzehn Befunde auf echter Hardware gekostet, weil die Leiste
    monatelang ausgerechnet und nie angesehen wurde.

WAS ES NICHT TUT
    Es bedient nichts. Hyprland 0.55.4 hat keinen Klick-Dispatcher
    (`hyprctl dispatch` kennt movecursor, aber keinen Druck), und
    ydotool/wlrctl liegen hier nicht. Das Bild zeigt also den Zustand
    beim Aufgehen. Welche Seite das ist, entscheidet --page.

SICHERHEIT
    Session.environment() setzt HOME, alle XDG-Wurzeln und den
    D-Bus-Sitzungsbus auf die Wegwerf-Sitzung um und laesst
    refuse_the_real_session() jeden Kindprozess dagegenhalten. Das ist
    hier nicht Kosmetik: diese Anwendung SCHREIBT user-settings.json.
    Ohne die Umlenkung wuerde ein Bildlauf die Einstellungen der
    laufenden Maschine anfassen.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

from render.desktop_session import Session  # noqa: E402

LAUNCHER = ROOT / "settings" / "bin" / "zepos-settings-gui"

# Die Seiten, die ein Bild verdienen. "leiste" ist die neue; die beiden
# anderen stehen daneben, damit man sieht, ob die neue sich einfuegt oder
# aus der Reihe faellt - eine Seite allein sieht immer stimmig aus.
PAGES = ("leiste", "groesse", "uhren")


def wait_for_window(session: Session, timeout: float = 40.0) -> dict | None:
    """Warten, bis das Fenster wirklich auf dem Schirm liegt.

    Nicht `sleep`: eine feste Wartezeit ist entweder zu kurz (das Bild
    zeigt einen leeren Schirm und niemand weiss warum) oder zu lang. Der
    Compositor weiss es genau, also wird er gefragt.
    """
    ende = time.monotonic() + timeout
    while time.monotonic() < ende:
        clients = session.hyprctl_json("clients")
        if clients:
            for client in clients:
                if client.get("mapped") and client.get("size", [0, 0])[0] > 1:
                    # Noch einen Wimpernschlag: gemappt heisst nicht
                    # gezeichnet. libadwaita baut seine Seiten nach dem
                    # ersten Rahmen fertig.
                    time.sleep(1.5)
                    return client
        time.sleep(0.3)
    return None


def shoot_page(session: Session, page: str, out: Path) -> str:
    process = session.spawn(
        [sys.executable, str(LAUNCHER), "--page", page],
        log=out / f"settings-{page}.log")

    client = wait_for_window(session)
    if client is None:
        process.terminate()
        return f"{page}: kein Fenster aufgegangen - siehe settings-{page}.log"

    x, y = client["at"]
    breite, hoehe = client["size"]
    session.shoot(out / f"einstellungen-{page}.png",
                  geometry=f"{x},{y} {breite}x{hoehe}")

    # Nur der eigene Prozess, und nur der, den diese Funktion gestartet
    # hat. Fremdes Beenden ist in diesem Projekt verboten, und zwar aus
    # einem konkreten Anlass: ein Agent hat mit `pkill` die laufende
    # Leiste des Nutzers erwischt.
    process.terminate()
    try:
        process.wait(timeout=10)
    except Exception:
        process.kill()
    return f"{page}: {breite}x{hoehe} bei {x},{y}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path,
                        default=ROOT / "out" / "render")
    parser.add_argument("--page", action="append", dest="pages",
                        help="Seite(n); ohne Angabe: "
                             + ", ".join(PAGES))
    arguments = parser.parse_args()

    if not LAUNCHER.is_file():
        print(f"Der Befehl fehlt: {LAUNCHER}", file=sys.stderr)
        return 1

    out = arguments.out
    out.mkdir(parents=True, exist_ok=True)
    pages = tuple(arguments.pages or PAGES)

    # Kein start(): __enter__ ruft es bereits. Ein zweiter Aufruf setzt
    # einen zweiten Compositor ueber den ersten, und hyprctl findet
    # danach keine Kennung mehr.
    with Session(1920, 1080) as session:
        session.start_bus()
        session.wallpaper()
        for page in pages:
            print(shoot_page(session, page, out))

    print(f"Bilder in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
