// SPDX-License-Identifier: BSD-3-Clause
//
// Urspruenglich hyprclipx von azzuriel, Commit
// 1eed6ee90a1c3e48ec76510377f8b05f27a4e650. Urhebervermerk und
// Haftungsausschluss stehen in plugins/LICENSE.
//
// Die gemeinsamen Zeiger der Compositor-Haelfte - KEIN GTK hier!
// Was das Fenster ist, sagen die internen Schnittstellen von Hyprland;
// die Oberflaeche wird ueber fork+exec gestartet.
//
// WAS ZEPOS HIER GEAENDERT HAT (12.08.2026)
//
// 1. DAS PROTOKOLL NACH /tmp/hyprclipx-debug.log IST WEG
//     Es waren fuenfzehn Schreibstellen, und sie liefen IM
//     COMPOSITOR-PROZESS, bei jedem Druck auf SUPER+SHIFT+V. Drei
//     Dinge daran, jedes fuer sich ein Grund:
//
//       * Unbegrenzt. `std::ios::app` ohne Obergrenze und ohne Rotation.
//         GEMESSEN am 12.08.2026 an dieser Datei: ein Durchlauf ohne
//         Schreibmarke schreibt 9 Zeilen, rund 260 Byte. Wer den
//         Verlauf hundertmal am Tag oeffnet, legt im Jahr knapp
//         10 MB in /tmp an - ein tmpfs, also im ARBEITSSPEICHER.
//       * Aus dem Compositor heraus. std::ofstream oeffnet, schreibt
//         und schliesst synchron; das haengt an der Taste, die den
//         Verlauf oeffnen soll, und auf einem vollen Dateisystem
//         haengt es laenger.
//       * Weltlesbar. Die Zeilen enthielten `window class` und
//         `window title` des Fensters, in dem der Nutzer gerade tippt.
//         /tmp ist von jedem Konto der Maschine lesbar, und ein
//         Fenstertitel ist der Name des geoeffneten Dokuments.
//
//     Ersatzlos und nicht hinter einen Schalter: ein Schalter waere
//     die Zeile, die trotzdem bei jedem Tastendruck geprueft wird, und
//     die Frage "steht er noch an?" haette niemand mehr gestellt.
//
// 2. DER PFAD ZUM SCHREIBMARKEN-HELFER STEHT NICHT MEHR IM OBJEKT
//     Er war `home + "/.local/bin/get-caret-position.py"`, fest
//     verdrahtet. Ein pacman-Paket darf unterhalb von ~ nichts
//     besitzen (der Kopf von src/paths.py fuehrt das Argument aus),
//     also konnte kein Paket das Programm ausliefern, das diese Zeile
//     sucht. Die Folge stand am 11.08.2026 im Rezept als offener
//     Punkt: das Plugin laedt, sein Fenster oeffnet, und die zweite
//     Strategie der Schreibmarkensuche findet nichts vor.
//
//     Jetzt kommt der Pfad aus ~/.config/hyprclipx/config, mit
//     /usr/lib/hyprclipx/caret-position.py als Grundwert - dem Ort,
//     an den das Paket ihn legt.
//
// 3. clipmanClient IST GELOESCHT
//     GEMESSEN am 12.08.2026, `grep -rn clipmanClient plugins/`: zwei
//     Zuweisungen, NULL Leser. Das Feld zeigte auf clipman-client.py,
//     ein Python-Programm, das Befehle ueber den Socket schickt - und
//     die C++-Haelfte tut das seit ihrer ersten Fassung selbst, in
//     ClipboardManager::sendCommand(). Ein Pfad auf ein Programm, das
//     niemand startet, ist kein Rueckfall, sondern eine Zeile, die
//     erklaert, dass hier frueher etwas anderes stand.

#include "hyprclipx/Globals.hpp"
#include "hyprclipx/IPCHandler.hpp"
#include "hyprclipx/ConfigParser.hpp"

#include <hyprland/src/Compositor.hpp>
#include <hyprland/src/output/Monitor.hpp>
#include <hyprland/src/desktop/Workspace.hpp>
#include <hyprland/src/desktop/view/Window.hpp>
#include <hyprland/src/desktop/state/ViewState.hpp>
#include <hyprland/src/state/MonitorState.hpp>
#include <hyprland/src/pointer/PointerManager.hpp>
#include <hyprland/src/managers/SeatManager.hpp>
#include <hyprland/src/managers/input/InputManager.hpp>

#include <algorithm>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <format>
#include <unistd.h>
#include <sys/wait.h>

namespace hyprclipx {

std::unique_ptr<IPCHandler> g_ipcHandler;
Config g_config;
void* g_handle = nullptr;

void initGlobals() {
    reloadConfig();
    g_ipcHandler = std::make_unique<IPCHandler>();
}

void cleanupGlobals() {
    g_ipcHandler.reset();
}

void reloadConfig() {
    g_config = loadConfig();
}

// ============================================================================
// Wie die Schreibmarke gefunden wird - drei Wege, in dieser Reihenfolge:
//
//   1. text-input-v3: ein Strukturfeld, direkt im Compositor gelesen.
//      Der schnellste Weg, und er trifft Firefox, die GTK- und
//      Qt-Anwendungen, kitty, foot, alacritty und Electron.
//   2. AT-SPI: fork und Python. Fuer XWayland und alles, was
//      text-input nicht spricht - etwa die JetBrains-Umgebungen.
//   3. Die Mausposition. Der letzte Ausweg.
// ============================================================================

void captureAndSendUI(const std::string& cmd) {
    // Die Kinder frueherer Aufrufe einsammeln, sonst bleiben Zombies
    // im Prozessbaum des Compositors stehen
    while (waitpid(-1, nullptr, WNOHANG) > 0) {}

    // Das Fenster mit dem TASTATURFOKUS, ueber den SeatManager - nicht
    // das unter der Maus. Auf mehreren Schirmen ist das der
    // Unterschied: getippt wird dort, wo der Fokus liegt, und die Maus
    // kann irgendwo stehen.
    PHLWINDOW pFocusedWindow;
    {
        auto focusSurface = g_pSeatManager->m_state.keyboardFocus.lock();
        if (focusSurface) {
            // Hyprland 0.56: CCompositor::getWindowFromSurface() gibt es
            // nicht mehr. Von der Flaeche zur Ansicht fuehrt jetzt der
            // Abfragebauer des Zustandsspeichers. Die Einschraenkung auf
            // VIEW_TYPE_WINDOW bildet das alte Verhalten genau nach:
            // 0.55 loeste hlSurface->view() auf, gab nullptr zurueck,
            // wenn der Typ nicht VIEW_TYPE_WINDOW war, und wandelte dann
            // nach CWindow. Ohne die Einschraenkung faende die Abfrage
            // auch eine Layer-Shell-Flaeche.
            pFocusedWindow = Desktop::viewState()
                                 ->query()
                                 .type(Desktop::View::VIEW_TYPE_WINDOW)
                                 .surface(focusSurface)
                                 .runWindow();
        }
    }

    // Die Adresse des vorherigen Fensters merken, BEVOR die Oberflaeche
    // aufgeht: danach liegt der Fokus beim Verlauf, und die Antwort
    // waere er selbst
    if (pFocusedWindow) {
        std::string windowAddr = std::format("0x{:x}", (uintptr_t)pFocusedWindow.get());
        std::ofstream f(g_config.prevWindowFile);
        if (f.is_open()) f << windowAddr;
    }

    // Der Schirm, auf dem das fokussierte Fenster liegt
    int monX = 0, monY = 0, monW = 1920, monH = 1080;
    {
        PHLMONITOR monitor;
        if (pFocusedWindow)
            monitor = pFocusedWindow->m_monitor.lock();
        if (!monitor) {
            // Hyprland 0.56: CCompositor::getMonitorFromCursor() gibt es
            // nicht mehr. 0.55 hat es als getMonitorFromVector(Zeiger)
            // gebaut, und eine Monitorabfrage mit nur einem vec() geht
            // durch CMonitorQueryCore::closestTo() - dieselbe Logik
            // "der Schirm, auf dem der Punkt liegt, sonst der naechste".
            monitor = State::monitorState()->query().vec(Pointer::mgr()->position()).run();
        }
        if (monitor) {
            monX = static_cast<int>(monitor->m_position.x);
            monY = static_cast<int>(monitor->m_position.y);
            monW = static_cast<int>(monitor->m_size.x);
            monH = static_cast<int>(monitor->m_size.y);
        }
    }

    std::string caretHelper = g_config.caretHelper;
    std::string caretPosFile = g_config.caretPosFile;
    std::string uiArg = "--" + cmd;

    // Die Form der Zeile: caretX,caretY,monX,monY,monW,monH
    auto writeCaretFile = [&](int cx, int cy) {
        std::ofstream f(caretPosFile);
        if (f.is_open())
            f << cx << "," << cy << "," << monX << "," << monY << "," << monW << "," << monH;
    };

    // ---- Weg 1: text-input-v3, direkt im Compositor gelesen ----
    // Wer text-input-v3 spricht, schickt set_cursor_rectangle von
    // selbst. Es ist nur ein Strukturfeld: schnell, verlaesslich, ohne
    // Python und ohne den Umweg ueber eine Datei.
    bool caretCaptured = false;
    if (pFocusedWindow) {
        // Hyprland 0.56: CGeometricMovableAnimated::m_realPosition ist
        // protected geworden. IGeometric::position() ist der oeffentliche
        // Zugang; GEOMETRIC_CURRENT gibt m_realPosition->value()
        // unveraendert zurueck.
        Vector2D winPos = pFocusedWindow->position(Desktop::View::IGeometric::GEOMETRIC_CURRENT);

        CTextInput* ti = g_pInputManager->m_relay.getFocusedTextInput();
        if (ti && ti->isEnabled() && ti->hasCursorRectangle()) {
            CBox cb = ti->cursorBox();
            int cx = static_cast<int>(winPos.x + cb.x);
            int cy = static_cast<int>(winPos.y + cb.y);
            cx = std::clamp(cx, monX, monX + monW - 1);
            cy = std::clamp(cy, monY, monY + monH - 1);
            writeCaretFile(cx, cy);
            caretCaptured = true;
        }
    }

    // Ein Kindprozess fuer die beiden anderen Wege und fuer den Start
    // der Oberflaeche. Nur AT-SPI und die Zeigerabfrage laufen dort -
    // beide blockieren, und im Compositor haenge daran die Taste.
    if (fork() == 0) {
        setsid();

        if (!caretCaptured) {
            auto getCursorPos = [](int& outX, int& outY) -> bool {
                FILE* p = popen("hyprctl cursorpos -j 2>/dev/null", "r");
                if (!p) return false;
                char buf[256] = {};
                std::string result;
                while (fgets(buf, sizeof(buf), p)) result += buf;
                pclose(p);
                size_t xp = result.find("\"x\":");
                size_t yp = result.find("\"y\":");
                if (xp != std::string::npos) outX = std::atoi(result.c_str() + xp + 4);
                if (yp != std::string::npos) outY = std::atoi(result.c_str() + yp + 4);
                return outX >= 0 && outY >= 0;
            };

            // ---- Weg 2: AT-SPI ueber Python, fuer XWayland und alles,
            // was text-input nicht spricht ----
            bool caretFound = false;
            FILE* pipe = popen(("/usr/bin/python3 " + caretHelper + " 2>/dev/null").c_str(), "r");
            if (pipe) {
                char buf[256] = {};
                std::string result;
                while (fgets(buf, sizeof(buf), pipe)) result += buf;
                int rc = pclose(pipe);
                if (rc == 0 && !result.empty()) {
                    int cx = -1, cy = -1;
                    size_t xp = result.find("\"x\":");
                    size_t yp = result.find("\"y\":");
                    if (xp != std::string::npos) cx = std::atoi(result.c_str() + xp + 4);
                    if (yp != std::string::npos) cy = std::atoi(result.c_str() + yp + 4);
                    if (cx >= 0 && cy >= 0) {
                        cx = std::clamp(cx, monX, monX + monW - 1);
                        cy = std::clamp(cy, monY, monY + monH - 1);
                        writeCaretFile(cx, cy);
                        caretFound = true;
                    }
                }
            }

            // ---- Weg 3: die Mausposition, der letzte Ausweg ----
            if (!caretFound) {
                int mx = -1, my = -1;
                if (getCursorPos(mx, my))
                    writeCaretFile(mx, my);
            }
        }

        execlp("hyprclipx-ui", "hyprclipx-ui", uiArg.c_str(), nullptr);
        _exit(1);
    }
}

void sendUICommand(const std::string& cmd) {
    while (waitpid(-1, nullptr, WNOHANG) > 0) {}

    if (fork() == 0) {
        setsid();
        std::string arg = "--" + cmd;
        execlp("hyprclipx-ui", "hyprclipx-ui", arg.c_str(), nullptr);
        _exit(1);
    }
}

} // namespace hyprclipx
