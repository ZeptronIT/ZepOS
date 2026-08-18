#pragma once
// Der Aufbau einer Zeile, so wie clipman-daemon sie als JSON schickt

#include <string>

namespace hyprclipx {

struct ClipboardEntry {
    std::string uuid;
    std::string type;         // "text" oder "image"
    std::string preview;
    std::string thumb;        // Voller Pfad zum Vorschaubild (nur Bilder)
    bool favorite = false;
    std::string createdAt;
};

} // namespace hyprclipx
