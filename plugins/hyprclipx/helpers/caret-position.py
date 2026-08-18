#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
#
# Urspruenglich get-caret-position.py von azzuriel, aus helpers/ des
# hyprclipx-Baums. Urhebervermerk und Haftungsausschluss stehen in
# plugins/LICENSE.
"""Wo die Schreibmarke steht - die zweite von drei Strategien.

WOZU DAS GEBRAUCHT WIRD
    Das Fenster des Verlaufs setzt sich an die Schreibmarke des
    Fensters, aus dem heraus SUPER+SHIFT+V gedrueckt wurde. Die erste
    Strategie liest sie direkt im Compositor aus text-input-v3
    (plugins/hyprclipx/src/Globals.cpp) und deckt alles ab, was das
    Protokoll spricht - Firefox, GTK, Qt, kitty, foot, Electron. Diese
    Datei ist die zweite: sie fragt AT-SPI und trifft damit
    XWayland-Fenster und alles, was kein text-input-v3 anmeldet. Die
    dritte ist der Mauszeiger.

WARUM SIE SEIT DEM 12.08.2026 IM BAUM LIEGT
    Weil Globals.cpp sie unter $HOME/.local/bin suchte, fest verdrahtet,
    und ein pacman-Paket dort nichts ablegen darf. Sie war damit auf
    jeder Installation abwesend, und die Strategie dazwischen fiel
    lautlos aus: popen() auf eine Datei, die es nicht gibt, gibt einen
    Ausgabestrom ohne Inhalt zurueck, kein Fehler, keine Zeile
    irgendwo. Der Verlauf oeffnete dann am Mauszeiger statt an der
    Schreibmarke - was aussieht wie eine Design-Entscheidung und keine
    war.

    Sie liegt jetzt in /usr/lib/hyprclipx/, und der Pfad steht in
    ~/.config/hyprclipx/config; Config.hpp begruendet beides.

WARUM DER RUECKFALL AM ENDE 100 PIXEL ADDIERT
    Er ist eine Schaetzung und gibt sich als solche: wenn AT-SPI nichts
    weiss, ist die linke obere Ecke des Fensters die einzige bekannte
    Groesse, und ein Verlaufsfenster genau darauf zu setzen verdeckt
    die Titelzeile dessen, worin getippt wird.
"""
import json
import subprocess

def get_caret_atspi():
    """Ueber AT-SPI, das die Wayland-eigenen Anwendungen beantworten."""
    try:
        import gi
        gi.require_version('Atspi', '2.0')
        from gi.repository import Atspi

        def find_caret(obj, depth=0):
            if depth > 15:
                return None
            try:
                state = obj.get_state_set()
                if state and state.contains(Atspi.StateType.FOCUSED):
                    text = obj.get_text()
                    if text:
                        offset = text.get_caret_offset()
                        if offset >= 0:
                            rect = text.get_character_extents(offset, Atspi.CoordType.SCREEN)
                            if rect and rect.x >= 0 and rect.y >= 0:
                                return {"x": rect.x, "y": rect.y}
                for i in range(obj.get_child_count()):
                    child = obj.get_child_at_index(i)
                    if child:
                        result = find_caret(child, depth + 1)
                        if result:
                            return result
            except:
                pass
            return None

        desktop = Atspi.get_desktop(0)
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            if app:
                result = find_caret(app)
                if result:
                    return result
    except:
        pass
    return None

def get_focused_window_position():
    """Der Rueckfall: die Lage des fokussierten Fensters, aus Hyprland."""
    try:
        result = subprocess.run(['hyprctl', 'activewindow', '-j'],
                              capture_output=True, text=True, timeout=1)
        if result.returncode == 0:
            import json as j
            data = j.loads(result.stdout)
            # Ein Punkt INNERHALB des Fensters, gemessen von seiner
            # linken oberen Ecke
            return {"x": data["at"][0] + 100, "y": data["at"][1] + 100}
    except:
        pass
    return None

if __name__ == "__main__":
    # Zuerst AT-SPI, das trifft die Wayland-eigenen Anwendungen
    pos = get_caret_atspi()

    # Sonst die Lage des fokussierten Fensters
    if not pos:
        pos = get_focused_window_position()

    if pos:
        print(json.dumps(pos))
    else:
        print(json.dumps({"x": -1, "y": -1}))
