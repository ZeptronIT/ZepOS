#pragma once
// hyprclipx-ui - der Zwischenablage-Verlauf von ZepOS
// Ein GTK4-Layer-Shell-Fenster als eigener Wayland-Client - NICHT im
// Compositor!

#include "Forward.hpp"
#include "Config.hpp"
#include "ClipboardEntry.hpp"
#include <gtk/gtk.h>
#include <gtk4-layer-shell.h>
#include <string>
#include <vector>
#include <atomic>

namespace hyprclipx {

class ClipboardRenderer {
public:
    explicit ClipboardRenderer(Config& config, ClipboardManager& manager);
    ~ClipboardRenderer();

    void initialize();
    void show();
    void hide();
    void toggle();
    bool isVisible() const;
    void setOffset(int x, int y);
    void refresh();

private:
    Config& m_config;
    ClipboardManager& m_manager;

    // Die Widgets
    GtkWidget* m_window       = nullptr;
    GtkWidget* m_listBox      = nullptr;
    GtkWidget* m_favBox       = nullptr;
    GtkWidget* m_searchEntry  = nullptr;
    GtkWidget* m_scrolled     = nullptr;
    GtkWidget* m_offsetLabel  = nullptr;
    GtkWidget* m_countLabel   = nullptr;
    GtkWidget* m_filterButtons[4] = {};

    // Der Zustand
    std::string m_filter = "all";
    std::string m_search;
    std::vector<ClipboardEntry> m_items;
    int m_selectedIndex = 0;
    int m_filterIndex   = 0;
    std::atomic<bool> m_visible{false};
    std::string m_previousWindowAddress;

    // Der Aufbau der Oberflaeche
    void buildUI();
    GtkWidget* createSidebarHeader();
    GtkWidget* createSidebarBody();
    GtkWidget* createSearchBar();
    GtkWidget* createHintBar();

    // Die Liste
    void updateList();
    void updateSelection(int newIndex);
    void updateFilterIcons();
    void scrollToIndex(int index);
    void updateOffsetOverlay();

    // Das Einfuegen, das weiss, wohin es einfuegt (1:1 aus AGS)
    void pasteItem(const std::string& uuid, const std::string& itemType);

    // Das Fenster selbst
    void repositionWindow();
    void loadCaretOffset();
    void saveCaretOffset();

    // Welches Fenster vorher den Fokus hatte (1:1 aus AGS)
    struct WindowInfo {
        std::string windowClass, initialClass, title, initialTitle, address;
        int pid = 0;
        bool xwayland = false;
    };
    WindowInfo getActiveWindowInfo();
    bool isTerminal(const WindowInfo& win);
    bool isKittyTerminal(const WindowInfo& win);
    bool isBrowser(const WindowInfo& win);

    // Die Tastatur
    static gboolean onKeyPress(GtkEventControllerKey*, guint, guint,
                               GdkModifierType, gpointer);

    // Handwerkszeug
    void removeAllChildren(GtkWidget* box);
    std::string exec(const std::string& cmd);

    // ITEM_HEIGHT = 28 stand hier und ist am 11.08.2026 entfallen.
    //
    // Es war die ANGENOMMENE Hoehe einer Listenzeile, mit der
    // scrollToIndex() gerechnet hat. Solange das Aussehen im
    // uebersetzten Objekt stand, war die Annahme richtig. Jetzt kommt
    // es aus einem erzeugten Stylesheet, dessen Schrift dem Regler aus
    // src/sizes.py folgt - eine Zeile ist bei Faktor 1.85 rund
    // doppelt so hoch, und die Liste haette beim Blaettern mit den
    // Pfeiltasten um denselben Faktor daneben gescrollt.
    //
    // Statt die Zahl zu einer zweiten Einstellung zu machen, wird sie
    // gemessen: gtk_widget_compute_bounds() sagt, wie hoch die Zeile
    // WIRKLICH ist. So macht es der Starter in
    // plugins/hyprlaunch/src/LauncherRenderer.cpp seit jeher, und eine
    // gemessene Hoehe kann bei keinem Faktor falsch sein.
    static constexpr int OFFSET_STEP  = 20;
};

} // namespace hyprclipx
