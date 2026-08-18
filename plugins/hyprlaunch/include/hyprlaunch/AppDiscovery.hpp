#pragma once

#include "AppEntry.hpp"
#include "Config.hpp"
#include <string>
#include <vector>

namespace hyprlaunch {

class AppDiscovery {
public:
    explicit AppDiscovery(const Config& config);

    // Die Listen einlesen
    void reloadApps();
    void reloadHelpers();

    // Die Suche. Bewertet und gefiltert, hoechstens MAX_RESULTS Zeilen.
    std::vector<AppEntry> searchApps(const std::string& query) const;
    std::vector<AppEntry> searchHelpers(const std::string& query) const;

    // Der Rechner
    static std::string evaluateCalculator(const std::string& expr);

    // Starten
    void launchApp(const AppEntry& entry);
    void launchHelper(const AppEntry& entry);
    static void copyToClipboard(const std::string& text);

    // Zuletzt benutzt
    void addToRecent(const std::string& appId);

private:
    const Config& m_config;
    std::vector<AppEntry> m_apps;
    std::vector<AppEntry> m_helpers;
    std::vector<std::string> m_recentApps;

    void loadRecentApps();
    void saveRecentApps();

    static int fuzzyScore(const std::string& query, const std::string& text);

    static constexpr int MAX_RESULTS = 300;
    static constexpr int MAX_RECENT = 10;
};

} // namespace hyprlaunch
