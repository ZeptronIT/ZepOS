#pragma once

#include "Forward.hpp"
#include "Config.hpp"
#include "AppEntry.hpp"
#include <gtk/gtk.h>
#include <gtk4-layer-shell.h>
#include <string>
#include <vector>
#include <atomic>

namespace hyprlaunch {

enum class LauncherMode { Apps, Helpers };

class LauncherRenderer {
public:
    explicit LauncherRenderer(Config& config, AppDiscovery& discovery);
    ~LauncherRenderer();

    void initialize();
    void show();
    void hide();
    void toggle();
    bool isVisible() const;
    void setMode(LauncherMode mode);

private:
    Config& m_config;
    AppDiscovery& m_discovery;

    // Die Widgets
    GtkWidget* m_window      = nullptr;
    GtkWidget* m_searchEntry = nullptr;
    GtkWidget* m_resultsList = nullptr;
    GtkWidget* m_scroll      = nullptr;

    // Der Zustand
    LauncherMode m_mode = LauncherMode::Apps;
    std::string m_query;
    std::vector<AppEntry> m_results;
    std::string m_calculatorResult;
    int m_selectedIndex = 0;
    std::atomic<bool> m_visible{false};

    // Die Trefferzeilen, um zu wissen, welche gerade gewaehlt ist
    std::vector<GtkWidget*> m_resultButtons;

    // Der Aufbau der Oberflaeche
    void buildUI();

    // Die Treffer
    void updateResults();
    void updateSelection(int newIndex);
    void scrollToIndex(int index);
    void onSearch(const std::string& text);
    void activateSelected();

    // Die Tastatur
    static gboolean onKeyPress(GtkEventControllerKey*, guint keyval, guint,
                               GdkModifierType, gpointer data);

    // Handwerkszeug
    void removeAllChildren(GtkWidget* box);

    // Die Hoehe, mit der das Fenster aufgeht - die eingestellte
    // Zeilenzahl, gedeckelt auf das, was der Schirm hergibt. Siehe
    // LauncherRenderer.cpp.
    int fittingHeight() const;
};

} // namespace hyprlaunch
