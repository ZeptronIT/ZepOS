// SPDX-License-Identifier: BSD-3-Clause
//
// Urspruenglich hyprlaunch von azzuriel, Commit
// 24e5c8b82f96f87ac25000353e36a8b17ced4b00. plugins/LICENSE.
//
// WAS ZEPOS HIER GEAENDERT HAT (11.08.2026)
//     `bool saveConfig(const Config&)` ist geloescht. Es schrieb die
//     Konfigurationsdatei zurueck - und diese Datei wird jetzt erzeugt.
//     Ein Programm, das seine eigene erzeugte Konfiguration
//     ueberschreibt, verliert beim naechsten Start alles, was der
//     Regler in src/sizes.py gesagt hat, und der Nutzer sucht den
//     Fehler in der Vorlage.
//
//     Aufgerufen wurde es ohnehin von nichts - gemessen mit `grep -rn
//     saveConfig plugins/`, null Treffer ausserhalb seiner eigenen
//     Deklaration und Definition. Es war schon bei upstream toter
//     Code; hier waere es ein scharf gestellter geworden.
#pragma once
#include "hyprlaunch/Config.hpp"
#include <string>

namespace hyprlaunch {

Config loadConfig();

// Die erzeugte Datei, die loadConfig() liest.
std::string getConfigPath();

// Das Verzeichnis, in dem sie und das Stylesheet liegen.
std::string getConfigDir();

} // namespace hyprlaunch
