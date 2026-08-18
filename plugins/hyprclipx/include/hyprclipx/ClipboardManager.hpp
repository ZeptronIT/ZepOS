#pragma once
// Die Seite, die den clipman-daemon anspricht (Unix-Socket auf
// /tmp/clipman.sock). Sie ersetzt die Aufrufe, die AGS als
// execAsync("python3 clipman-client.py ...") gemacht hat.

#include "ClipboardEntry.hpp"
#include "Config.hpp"
#include <string>
#include <vector>

namespace hyprclipx {

class ClipboardManager {
public:
    explicit ClipboardManager(const Config& config);

    // Die Befehle des Dienstes, dieselben wie in clipman-client.py
    std::vector<ClipboardEntry> fetchItems(const std::string& filter = "all",
                                           const std::string& search = "",
                                           int limit = 50);
    bool paste(const std::string& uuid);
    bool toggleFavorite(const std::string& uuid);
    bool deleteItem(const std::string& uuid);
    bool clearAll();
    bool ping();

private:
    const Config& m_config;

    // Einen Befehl schicken und die Antwort als JSON zurueckgeben
    std::string sendCommand(const std::string& cmd, const std::string& argsJson = "{}");

    // Die Antwortliste in Eintraege uebersetzen
    std::vector<ClipboardEntry> parseListResponse(const std::string& json);
};

} // namespace hyprclipx
