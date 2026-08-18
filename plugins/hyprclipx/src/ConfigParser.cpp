// SPDX-License-Identifier: BSD-3-Clause
//
// Urspruenglich hyprclipx von azzuriel, Commit
// 1eed6ee90a1c3e48ec76510377f8b05f27a4e650. plugins/LICENSE.
//
// WAS ZEPOS HIER GEAENDERT HAT (11.08.2026)
//   * Der Pfad: ~/.config/hyprclipx/config statt
//     ~/.config/hypr/hyprclipx.toml. Der Grund steht im ConfigParser
//     von hyprlaunch in voller Laenge - kurz: ~/.config/hypr gehoert
//     Hyprland und ist voll erzeugter Dateien dieses Projekts, und ein
//     eigenes Format dazwischen wird beim Aufraeumen erwischt.
//   * saveConfig() und getDataDir() sind geloescht, siehe
//     ConfigParser.hpp.
//   * Die Abstandsleiter aus src/sizes.py wird gelesen.
//   * parseInt() nimmt ein nachgestelltes "px" hin und weist alles
//     andere zurueck, statt es wortlos zu 0 zu machen.

#include "hyprclipx/ConfigParser.hpp"
#include <fstream>
#include <sstream>
#include <cstdlib>

namespace hyprclipx {

static const char* CONFIG_NAMESPACE = "hyprclipx";

std::string getConfigDir() {
    const char* xdgConfig = std::getenv("XDG_CONFIG_HOME");
    std::string configDir;

    if (xdgConfig && *xdgConfig) {
        configDir = xdgConfig;
    } else {
        const char* home = std::getenv("HOME");
        configDir = home ? std::string(home) + "/.config" : "/tmp";
    }

    return configDir + "/" + CONFIG_NAMESPACE;
}

std::string getConfigPath() {
    return getConfigDir() + "/config";
}

static std::string trim(const std::string& str) {
    size_t start = str.find_first_not_of(" \t\r\n");
    size_t end = str.find_last_not_of(" \t\r\n");
    return (start == std::string::npos) ? "" : str.substr(start, end - start + 1);
}

static std::string parseString(const std::string& value) {
    std::string v = trim(value);
    if (v.size() >= 2 && v.front() == '"' && v.back() == '"') {
        return v.substr(1, v.size() - 2);
    }
    return v;
}

// Wortgleich zu plugins/hyprlaunch/src/ConfigParser.cpp, und die
// Begruendung fuer das geduldete "px" steht dort.
//
// WARUM ES HIER TROTZDEM EIN ZWEITES MAL STEHT
//     Weil die beiden Programme keine gemeinsame Bibliothek haben und
//     auch keine bekommen sollen: es sind zwei CMake-Projekte, zwei
//     Pakete und zwei Namensraeume, und ein drittes Paket, das nichts
//     enthaelt als vierzig Zeilen Zahlenlesen, waere eine
//     Abhaengigkeit mehr fuer jede der beiden.
//
//     Die Vorgaengerfassung war upstreams `int parseInt(const
//     std::string&)`, das bei Unfug eine 0 zurueckgab. Damit machte
//     eine vertippte Zeile in der Konfiguration aus einem Fenster ein
//     nulldimensionales, ohne ein Wort. Jetzt bleibt der Grundwert
//     stehen, wenn ein Wert nicht lesbar ist.
static bool parseInt(const std::string& value, int& out) {
    std::string v = trim(value);
    if (v.size() > 2 && v.compare(v.size() - 2, 2, "px") == 0)
        v = trim(v.substr(0, v.size() - 2));
    if (v.empty())
        return false;

    size_t consumed = 0;
    int parsed = 0;
    try {
        parsed = std::stoi(v, &consumed);
    } catch (...) {
        return false;
    }
    if (consumed != v.size())
        return false;

    out = parsed;
    return true;
}

Config loadConfig() {
    Config config;
    config.styleSheet = getConfigDir() + "/style.css";
    // Beide Haelften kommen hier durch, also steht der Pfad hier und
    // nicht zweimal daneben - siehe Config.hpp, Abschnitt "Paths".
    config.userSettingsFile = getConfigDir() + "/settings.json";

    std::string configPath = getConfigPath();
    std::ifstream file(configPath);
    if (!file.is_open()) {
        return config;
    }

    std::string line;
    while (std::getline(file, line)) {
        line = trim(line);

        if (line.empty() || line[0] == '#' || line[0] == '[') {
            continue;
        }

        size_t eq = line.find('=');
        if (eq == std::string::npos) continue;

        std::string key = trim(line.substr(0, eq));
        std::string value = trim(line.substr(eq + 1));

        if (key == "hotkey") {
            config.hotkey = parseString(value);
            continue;
        }
        if (key == "socket_path") {
            config.socketPath = parseString(value);
            continue;
        }
        // Der Schreibmarken-Helfer. Ohne diesen Schluessel bleibt der
        // Grundwert aus Config.hpp stehen, also der Pfad, an den das
        // Paket ihn legt.
        if (key == "caret_helper") {
            config.caretHelper = parseString(value);
            continue;
        }

        // Eine Sprosse der Abstandsleiter, ueber den Namen erkannt und
        // nicht ueber eine feste Liste - die Leiter steht in
        // src/sizes.py, und eine zweite Aufzaehlung hier waere die
        // Kopie, die beim naechsten Sprossenzuwachs stehen bleibt.
        if (key.rfind("space_", 0) == 0) {
            int rung = 0;
            int pixels = 0;
            if (parseInt(key.substr(6), rung) && parseInt(value, pixels))
                config.spacing[rung] = pixels;
            continue;
        }

        int number = 0;
        if (!parseInt(value, number))
            continue;

        if (key == "window_width") config.windowWidth = number;
        else if (key == "window_height") config.windowHeight = number;
        else if (key == "offset_x") config.offsetX = number;
        else if (key == "offset_y") config.offsetY = number;
        else if (key == "max_items") config.maxItems = number;
        else if (key == "preview_chars") config.previewChars = number;
    }

    return config;
}

} // namespace hyprclipx
