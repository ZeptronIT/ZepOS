// SPDX-License-Identifier: BSD-3-Clause
//
// Urspruenglich hyprlaunch von azzuriel, Commit
// 24e5c8b82f96f87ac25000353e36a8b17ced4b00. plugins/LICENSE.
//
// WAS ZEPOS HIER GEAENDERT HAT (11.08.2026)
//   * Der Pfad. Upstream las ~/.config/hypr/hyprlaunch.toml, also eine
//     Datei IN dem Verzeichnis, das Hyprland gehoert. ZepOS erzeugt
//     dorthin hyprland.conf, plugins.conf und ein
//     halbes Dutzend Skripte; eine weitere Datei mit einem fremden
//     Format dazwischen ist eine, die beim Aufraeumen erwischt wird.
//     Jetzt: ~/.config/hyprlaunch/, wo auch das erzeugte style.css
//     liegt - dieselbe Aufteilung, die zepos-logout und zepos-menu
//     schon haben (ein Namensraum, zwei erzeugte Dateien).
//   * saveConfig() ist geloescht, Begruendung im Kopf von
//     ConfigParser.hpp.
//   * Die Abstandsleiter aus src/sizes.py wird gelesen: space_2 bis
//     space_24.
//   * parseInt() nimmt ein nachgestelltes "px" hin, siehe dort.

#include "hyprlaunch/ConfigParser.hpp"
#include <fstream>
#include <sstream>
#include <cstdlib>

namespace hyprlaunch {

// Der Namensraum unter ~/.config. Einmal, weil der Pfad an drei
// Stellen gebraucht wird und ein zweiter Schreibweise-Unterschied
// zwischen ihnen ein Programm ergaebe, das seine Konfiguration im
// einen Verzeichnis sucht und sein Stylesheet im anderen.
static const char* CONFIG_NAMESPACE = "hyprlaunch";

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

// Eine fuehrende Tilde durch $HOME ersetzen.
//
// WARUM DAS SEIN MUSS, SOBALD EIN PFAD IN DER DATEI STEHT
//     Die erzeugte Datei kann $HOME nicht kennen - sie wird einmal
//     geschrieben und von dem Konto gelesen, dem sie gehoert. Ohne
//     diese Zeile waere `helpers_dir = "~/.local/bin/helpers"` ein
//     Verzeichnis namens "~" im Arbeitsverzeichnis des Compositors,
//     und der Helfer-Modus faende dort nichts. Das ist genau die Sorte
//     Ausfall, die dieses Programm schon einmal hatte: eine leere
//     Liste sieht aus wie "keine Skripte vorhanden".
//
//     Nur am Anfang und nur "~/" - eine Tilde mitten im Pfad ist ein
//     gueltiges Zeichen in einem Dateinamen, und "~benutzer" waere
//     eine Aufloesung ueber die Passwortdatenbank, die hier niemand
//     braucht und die still das falsche Heimatverzeichnis treffen
//     kann.
static std::string expandHome(const std::string& path) {
    if (path.rfind("~/", 0) != 0)
        return path;
    const char* home = std::getenv("HOME");
    if (!home || !*home)
        return path;
    return std::string(home) + path.substr(1);
}

// Eine Zahl, die auch dann eine ist, wenn ein "px" daran haengt.
//
// WARUM DIESE TOLERANZ UND NICHT ZWEI PLATZHALTER
//     Die Sprossen der Abstandsleiter tragen in src/sizes.py die
//     Einheit px, weil ihr HAUPTleser ein Stylesheet ist. Derselbe
//     Platzhalter fuellt hier eine Zahl fuer gtk_box_new(). Die
//     Alternative waere ein zweiter Satz Platzhalter ohne Einheit -
//     also zwei Namen fuer eine Sprosse, und ab dem ersten Vertippen
//     zwei verschiedene Abstaende, die niemand nebeneinander sieht.
//     src/sizes.py schreibt den Fall selbst auf: "Ob der erzeugte Wert
//     ein 'px' traegt, haengt nicht am Wert, sondern am Leser."
//
//     std::stoi wuerde "23px" ohnehin als 23 lesen und aufhoeren.
//     Verlassen wird sich darauf nicht: dieselbe Nachsicht macht aus
//     einem vertippten "2 3" eine 2, und ein Abstand, der still ein
//     anderer ist, ist genau die Sorte Fehler, die niemand meldet. Der
//     Rest hinter der Zahl muss "px" sein oder nichts.
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

    // Die Pfade, die erst zur Laufzeit feststehen
    const char* homeEnv = std::getenv("HOME");
    std::string home = homeEnv ? homeEnv : "/root";
    config.recentFile = home + "/.cache/hyprlaunch-recent.json";
    config.helpersDir = home + "/.local/bin/helpers";
    config.styleSheet = getConfigDir() + "/style.css";

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

        // Das Verzeichnis, aus dem der Helfer-Modus seine Skripte
        // liest (hyprctl hyprlaunch:helpers, angeboten von der Leiste
        // und vom Kontrollzentrum).
        //
        // WARUM ES HIER STEHT UND WARUM SEIN GRUNDWERT TROTZDEM UNTER ~ LIEGT
        //     Es sind die EIGENEN Skripte des Nutzers, keine Dateien
        //     eines Pakets - das ist der Unterschied zum
        //     Schreibmarken-Helfer von hyprclipx, der unter ~ lag und
        //     deshalb nie ausgeliefert werden konnte. Ein Ort fuer
        //     eigene Skripte gehoert ins Heimatverzeichnis.
        //
        //     Was daran falsch war, ist nur, dass der Pfad im Objekt
        //     stand: wer seine Skripte woanders hat, konnte es dem
        //     Starter nicht sagen. Jetzt sagt es die erzeugte Datei.
        if (key == "helpers_dir") {
            config.helpersDir = expandHome(parseString(value));
            continue;
        }

        // Eine Sprosse der Abstandsleiter: space_12 = 22px.
        //
        // Ueber den Namen und nicht ueber eine feste Liste von sieben
        // Schluesseln: die Leiter steht in src/sizes.py, und eine
        // zweite Aufzaehlung hier waere die Kopie, die beim naechsten
        // Sprossenzuwachs stehen bleibt.
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
        else if (key == "visible_items") config.visibleItems = number;
        else if (key == "search_height") config.searchHeight = number;
        else if (key == "item_height") config.itemHeight = number;
        else if (key == "chrome") config.chrome = number;
        else if (key == "icon_size") config.iconSize = number;
        else if (key == "description_chars") config.descriptionChars = number;
    }

    return config;
}

} // namespace hyprlaunch
