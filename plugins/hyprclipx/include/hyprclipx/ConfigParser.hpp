// SPDX-License-Identifier: BSD-3-Clause
//
// Urspruenglich hyprclipx von azzuriel, Commit
// 1eed6ee90a1c3e48ec76510377f8b05f27a4e650. plugins/LICENSE.
//
// WAS ZEPOS HIER GELOESCHT HAT (11.08.2026)
//   * `bool saveConfig(const Config&)`. Es schrieb die
//     Konfigurationsdatei zurueck, und die wird jetzt erzeugt - ein
//     Programm, das seine erzeugte Konfiguration ueberschreibt, wirft
//     beim naechsten Start weg, was der Regler in src/sizes.py gesagt
//     hat. Aufgerufen wurde es von nichts (`grep -rn saveConfig
//     plugins/`, null Treffer ausser Deklaration und Definition).
//   * `std::string getDataDir()`. Ebenfalls ohne Aufrufer, und es hatte
//     eine Nebenwirkung: es legte ~/.local/share/hyprclipx an. Ein
//     Verzeichnis, das eine ungenutzte Funktion nebenbei erzeugt, ist
//     ein Verzeichnis, das niemand erklaeren kann.
#pragma once
#include "Config.hpp"
#include <string>

namespace hyprclipx {

Config loadConfig();

// Die erzeugte Datei, die loadConfig() liest.
std::string getConfigPath();

// Das Verzeichnis, in dem sie und das Stylesheet liegen.
std::string getConfigDir();

} // namespace hyprclipx
