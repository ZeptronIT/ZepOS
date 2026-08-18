// Anwendungen und Hilfsskripte finden, durchsuchen und starten
// Eins zu eins uebertragen aus der AGS-Vorlage ags-launcher-zofi.template

#include "hyprlaunch/AppDiscovery.hpp"
#include <gio/gio.h>
#include <gio/gdesktopappinfo.h>
#include <glib.h>
#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sstream>
#include <unistd.h>

namespace hyprlaunch {

// ============================================================================
// Der Aufbau
// ============================================================================

AppDiscovery::AppDiscovery(const Config& config) : m_config(config) {
    reloadApps();
    loadRecentApps();
}

// ============================================================================
// Die Anwendungen einlesen (1:1 aus loadApplications in AGS)
// ============================================================================

void AppDiscovery::reloadApps() {
    m_apps.clear();

    GList* appInfos = g_app_info_get_all();
    for (GList* l = appInfos; l != nullptr; l = l->next) {
        GAppInfo* appInfo = G_APP_INFO(l->data);
        if (!g_app_info_should_show(appInfo)) continue;

        AppEntry entry;
        const char* id = g_app_info_get_id(appInfo);
        entry.id = id ? id : "";

        const char* displayName = g_app_info_get_display_name(appInfo);
        const char* name = g_app_info_get_name(appInfo);
        entry.name = displayName ? displayName : (name ? name : "");

        GIcon* iconObj = g_app_info_get_icon(appInfo);
        if (iconObj) {
            char* iconStr = g_icon_to_string(iconObj);
            if (iconStr) {
                entry.icon = iconStr;
                g_free(iconStr);
            }
        }

        const char* cmdline = g_app_info_get_commandline(appInfo);
        entry.exec = cmdline ? cmdline : "";

        const char* desc = g_app_info_get_description(appInfo);
        entry.description = desc ? desc : "";

        // Die Stichworte, nach denen gesucht wird
        std::string nameLower = entry.name;
        std::transform(nameLower.begin(), nameLower.end(), nameLower.begin(),
                       [](unsigned char c) { return std::tolower(c); });

        std::string descLower = entry.description;
        std::transform(descLower.begin(), descLower.end(), descLower.begin(),
                       [](unsigned char c) { return std::tolower(c); });

        std::string idLower = entry.id;
        std::transform(idLower.begin(), idLower.end(), idLower.begin(),
                       [](unsigned char c) { return std::tolower(c); });
        // Die Endung .desktop weg
        size_t pos = idLower.rfind(".desktop");
        if (pos != std::string::npos) idLower = idLower.substr(0, pos);

        entry.keywords = {nameLower, descLower, idLower};
        m_apps.push_back(std::move(entry));
    }
    g_list_free_full(appInfos, g_object_unref);

    std::sort(m_apps.begin(), m_apps.end(),
              [](const AppEntry& a, const AppEntry& b) {
                  return a.name < b.name;
              });
}

// ============================================================================
// Die Hilfsskripte einlesen (1:1 aus loadHelpers in AGS)
// ============================================================================

void AppDiscovery::reloadHelpers() {
    m_helpers.clear();

    GFile* dir = g_file_new_for_path(m_config.helpersDir.c_str());
    if (!g_file_query_exists(dir, nullptr)) {
        g_object_unref(dir);
        return;
    }

    GError* error = nullptr;
    GFileEnumerator* enumerator = g_file_enumerate_children(
        dir, "standard::name,standard::type",
        G_FILE_QUERY_INFO_NONE, nullptr, &error);

    if (!enumerator) {
        if (error) g_error_free(error);
        g_object_unref(dir);
        return;
    }

    GFileInfo* fileInfo;
    while ((fileInfo = g_file_enumerator_next_file(enumerator, nullptr, nullptr)) != nullptr) {
        const char* fileName = g_file_info_get_name(fileInfo);
        if (!fileName) {
            g_object_unref(fileInfo);
            continue;
        }

        std::string name(fileName);
        if (name.size() < 4 || name.substr(name.size() - 3) != ".sh") {
            g_object_unref(fileInfo);
            continue;
        }
        if (name.find(".backup.") != std::string::npos) {
            g_object_unref(fileInfo);
            continue;
        }

        std::string fullPath = m_config.helpersDir + "/" + name;
        std::string displayName = name.substr(0, name.size() - 3);

        // Die erste inhaltliche Kommentarzeile ist die Beschreibung
        std::string description = fullPath;
        std::ifstream scriptFile(fullPath);
        if (scriptFile.is_open()) {
            std::string line;
            bool firstLine = true;
            while (std::getline(scriptFile, line)) {
                if (firstLine) { firstLine = false; continue; }  // die Shebang-Zeile

                // Leerraum vorn weg
                size_t start = line.find_first_not_of(" \t");
                if (start == std::string::npos) continue;
                std::string trimmed = line.substr(start);

                // Die Zeilen des Generators sagen nichts ueber das Skript
                if (trimmed.starts_with("# ====") ||
                    trimmed.starts_with("# Generated") ||
                    trimmed.starts_with("# Edit template")) continue;

                // Der erste echte Kommentar ist die Beschreibung
                if (trimmed.starts_with("#") && trimmed.size() > 2) {
                    size_t textStart = trimmed.find_first_not_of("# ", 1);
                    if (textStart != std::string::npos) {
                        description = trimmed.substr(textStart);
                    }
                    break;
                }

                // Bei der ersten Zeile, die kein Kommentar ist, aufhoeren
                if (!trimmed.starts_with("#") && !trimmed.empty()) break;
            }
        }

        AppEntry entry;
        entry.id = name;
        entry.name = displayName;
        entry.icon = "utilities-terminal";
        entry.exec = fullPath;
        entry.description = description;

        std::string nameLower = displayName;
        std::transform(nameLower.begin(), nameLower.end(), nameLower.begin(),
                       [](unsigned char c) { return std::tolower(c); });
        std::string descLower = description;
        std::transform(descLower.begin(), descLower.end(), descLower.begin(),
                       [](unsigned char c) { return std::tolower(c); });
        entry.keywords = {nameLower, descLower};

        m_helpers.push_back(std::move(entry));
        g_object_unref(fileInfo);
    }

    g_object_unref(enumerator);
    g_object_unref(dir);

    std::sort(m_helpers.begin(), m_helpers.end(),
              [](const AppEntry& a, const AppEntry& b) {
                  return a.name < b.name;
              });
}

// ============================================================================
// Die Bewertung eines Treffers (1:1 aus fuzzyScore in AGS)
// ============================================================================

int AppDiscovery::fuzzyScore(const std::string& query, const std::string& text) {
    std::string q = query;
    std::transform(q.begin(), q.end(), q.begin(),
                   [](unsigned char c) { return std::tolower(c); });
    std::string t = text;
    std::transform(t.begin(), t.end(), t.begin(),
                   [](unsigned char c) { return std::tolower(c); });

    if (t.starts_with(q)) return 1000;
    if (t.find(q) != std::string::npos) return 100;
    return 0;
}

std::vector<AppEntry> AppDiscovery::searchApps(const std::string& query) const {
    if (query.empty()) {
        // Ohne Eingabe: zuerst die zuletzt benutzten, dann alphabetisch
        std::vector<AppEntry> result;
        for (const auto& id : m_recentApps) {
            for (const auto& app : m_apps) {
                if (app.id == id) {
                    result.push_back(app);
                    break;
                }
            }
        }
        for (const auto& app : m_apps) {
            bool isRecent = false;
            for (const auto& id : m_recentApps) {
                if (app.id == id) { isRecent = true; break; }
            }
            if (!isRecent) result.push_back(app);
        }
        if (result.size() > MAX_RESULTS) result.resize(MAX_RESULTS);
        return result;
    }

    struct ScoredApp {
        const AppEntry* app;
        int score;
    };

    std::vector<ScoredApp> scored;
    for (const auto& app : m_apps) {
        int nameScore = fuzzyScore(query, app.name) * 10;
        int descScore = fuzzyScore(query, app.description);
        int keywordScore = 0;
        for (const auto& kw : app.keywords) {
            keywordScore = std::max(keywordScore, fuzzyScore(query, kw));
        }
        int best = std::max({nameScore, descScore, keywordScore});
        if (best > 0) {
            scored.push_back({&app, best});
        }
    }

    std::sort(scored.begin(), scored.end(), [](const ScoredApp& a, const ScoredApp& b) {
        if (b.score != a.score) return b.score < a.score;
        return a.app->name < b.app->name;
    });

    std::vector<AppEntry> result;
    for (const auto& s : scored) {
        result.push_back(*s.app);
        if (static_cast<int>(result.size()) >= MAX_RESULTS) break;
    }
    return result;
}

std::vector<AppEntry> AppDiscovery::searchHelpers(const std::string& query) const {
    if (query.empty()) {
        auto result = m_helpers;
        if (result.size() > static_cast<size_t>(MAX_RESULTS)) result.resize(MAX_RESULTS);
        return result;
    }

    struct ScoredApp {
        const AppEntry* app;
        int score;
    };

    std::vector<ScoredApp> scored;
    for (const auto& h : m_helpers) {
        int nameScore = fuzzyScore(query, h.name) * 10;
        int descScore = fuzzyScore(query, h.description);
        int best = std::max(nameScore, descScore);
        if (best > 0) {
            scored.push_back({&h, best});
        }
    }

    std::sort(scored.begin(), scored.end(), [](const ScoredApp& a, const ScoredApp& b) {
        if (b.score != a.score) return b.score < a.score;
        return a.app->name < b.app->name;
    });

    std::vector<AppEntry> result;
    for (const auto& s : scored) {
        result.push_back(*s.app);
        if (static_cast<int>(result.size()) >= MAX_RESULTS) break;
    }
    return result;
}

// ============================================================================
// Der Rechner (1:1 aus evaluateCalculator in AGS)
// ============================================================================

std::string AppDiscovery::evaluateCalculator(const std::string& expr) {
    // Das fuehrende '=' und den Leerraum weg
    std::string cleanExpr = expr;
    if (!cleanExpr.empty() && cleanExpr[0] == '=') {
        cleanExpr = cleanExpr.substr(1);
    }
    size_t start = cleanExpr.find_first_not_of(" \t");
    if (start == std::string::npos) return "";
    cleanExpr = cleanExpr.substr(start);

    if (cleanExpr.empty()) return "";

    // Die Zeichen pruefen: Ziffern, Rechenzeichen, Klammern, Leerzeichen,
    // Komma. Was hier durchkommt, geht gleich an eine Shell.
    for (char c : cleanExpr) {
        if (!std::isdigit(c) && c != '+' && c != '-' && c != '*' && c != '/' &&
            c != '(' && c != ')' && c != '.' && c != ' ' && c != '%' && c != '^') {
            return "";
        }
    }

    // Gerechnet wird mit bc. Unbedenklich, weil oben nur Rechenzeichen
    // durchgelassen wurden; ^ versteht bc von sich aus, es muss also
    // nicht ersetzt werden.
    std::string bcExpr = "echo 'scale=6; " + cleanExpr + "' | bc -l 2>/dev/null";

    FILE* pipe = popen(bcExpr.c_str(), "r");
    if (!pipe) return "";

    char buf[256] = {};
    std::string result;
    while (fgets(buf, sizeof(buf), pipe)) result += buf;
    int rc = pclose(pipe);

    if (rc != 0 || result.empty()) return "";

    // Leerraum hinten weg
    while (!result.empty() && (result.back() == '\n' || result.back() == ' '))
        result.pop_back();

    // Nullen hinter dem Komma weg
    if (result.find('.') != std::string::npos) {
        while (result.back() == '0') result.pop_back();
        if (result.back() == '.') result.pop_back();
    }

    return result;
}

// ============================================================================
// Starten (1:1 aus launchApp und launchHelper in AGS)
// ============================================================================

void AppDiscovery::launchApp(const AppEntry& entry) {
    GDesktopAppInfo* appInfo = g_desktop_app_info_new(entry.id.c_str());
    if (appInfo) {
        GError* error = nullptr;
        g_app_info_launch(G_APP_INFO(appInfo), nullptr, nullptr, &error);
        if (error) g_error_free(error);
        g_object_unref(appInfo);
        addToRecent(entry.id);
    }
}

void AppDiscovery::launchHelper(const AppEntry& entry) {
    if (fork() == 0) {
        setsid();

        // Braucht das Skript ein Terminal?
        bool needsTerminal = false;
        std::ifstream f(entry.exec);
        if (f.is_open()) {
            std::string content((std::istreambuf_iterator<char>(f)),
                                std::istreambuf_iterator<char>());
            if (content.find("read") != std::string::npos ||
                content.find("dialog") != std::string::npos ||
                content.find("whiptail") != std::string::npos ||
                content.find("select") != std::string::npos) {
                needsTerminal = true;
            }
        }

        if (needsTerminal) {
            execlp("kitty", "kitty", "--class=floating-center", "-e",
                   entry.exec.c_str(), nullptr);
        } else {
            execlp("/bin/bash", "bash", entry.exec.c_str(), nullptr);
        }
        _exit(1);
    }
}

void AppDiscovery::copyToClipboard(const std::string& text) {
    if (fork() == 0) {
        setsid();
        execlp("wl-copy", "wl-copy", text.c_str(), nullptr);
        _exit(1);
    }
}

// ============================================================================
// Zuletzt benutzt (1:1 aus loadRecentApps, saveRecentApps und
// addToRecent in AGS)
// ============================================================================

void AppDiscovery::addToRecent(const std::string& appId) {
    // Steht sie schon in der Liste, dort raus
    m_recentApps.erase(
        std::remove(m_recentApps.begin(), m_recentApps.end(), appId),
        m_recentApps.end());

    // Und vorn wieder hinein
    m_recentApps.insert(m_recentApps.begin(), appId);

    // Nicht mehr als MAX_RECENT
    if (static_cast<int>(m_recentApps.size()) > MAX_RECENT) {
        m_recentApps.resize(MAX_RECENT);
    }

    saveRecentApps();
}

void AppDiscovery::loadRecentApps() {
    m_recentApps.clear();

    std::ifstream f(m_config.recentFile);
    if (!f.is_open()) return;

    std::string content((std::istreambuf_iterator<char>(f)),
                        std::istreambuf_iterator<char>());

    // Die kleinstmoegliche Lesart einer JSON-Liste: ["id1","id2",...]
    size_t pos = content.find('[');
    if (pos == std::string::npos) return;

    while (true) {
        size_t qStart = content.find('"', pos + 1);
        if (qStart == std::string::npos) break;
        size_t qEnd = content.find('"', qStart + 1);
        if (qEnd == std::string::npos) break;

        m_recentApps.push_back(content.substr(qStart + 1, qEnd - qStart - 1));
        pos = qEnd;

        if (static_cast<int>(m_recentApps.size()) >= MAX_RECENT) break;
    }
}

void AppDiscovery::saveRecentApps() {
    std::ofstream f(m_config.recentFile);
    if (!f.is_open()) return;

    f << "[";
    for (size_t i = 0; i < m_recentApps.size(); i++) {
        if (i > 0) f << ",";
        f << "\"" << m_recentApps[i] << "\"";
    }
    f << "]";
}

} // namespace hyprlaunch
