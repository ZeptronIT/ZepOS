// hyprlaunch-ui - der Anwendungsstarter von ZepOS, ein
// GTK4-Layer-Shell-Fenster
// Eins zu eins uebertragen aus der AGS-Vorlage ags-launcher-zofi.template

#include "hyprlaunch/LauncherRenderer.hpp"
#include "hyprlaunch/AppDiscovery.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <algorithm>
#include <string>

namespace hyprlaunch {

// ── Das Stylesheet ──────────────────────────────────────────────
//
// HIER STANDEN 116 ZEILEN CSS, UND GENAU DAS WAR DER AUFTRAG (11.08.2026)
//     Upstream trug sein Aussehen als `static const char*
//     LAUNCHER_CSS = R"CSS(...)"` im uebersetzten Objekt. GEZAEHLT an
//     Commit 24e5c8b: 20 Farbliterale in zehn Toenen, dazu drei
//     rgba(); "Fira Code" als Schriftfamilie an drei Stellen; acht
//     Schriftgroessen; sechs Abstandsregeln.
//
//     Keiner dieser Werte konnte je aus src/brand.py kommen, und keiner
//     aus src/sizes.py. Der Schreibtisch ist petrolfarben
//     (STYLE_COLOR_OVERLAY_BG, #08262C) und der Starter war schwarz
//     (#0a0a0a).
//
//     Bei der Schrift ist der Befund feiner und deshalb interessanter.
//     `font-family: "Fira Code", monospace` nennt dieselbe Familie,
//     die auch brand.FONT_CODE nennt, und ttf-fira-code steht in
//     packaging/zepos-desktop und in iso/profile/packages.x86_64 - die
//     Familie ist also DA. Was fehlte, ist die Kette dahinter:
//     STYLE_FONT_FAMILY ist "Fira Code", "JetBrainsMono Nerd Font",
//     "Font Awesome 6 Free", "Font Awesome 6 Brands", monospace, und
//     genau diese Glieder tragen die Symbole. Der Starter zeichnet
//     Lupe, Abakus, Paket und Uhr; keins dieser Zeichen steht in Fira
//     Code, also hat fontconfig sie wortlos irgendwoher ersetzt.
//     Dieselbe Sorte Fehler wie bei wofi ("der Starter seit jeher in
//     GTKs Standardgrau"), nur ohne die 39 Parserfehler, die ihn dort
//     wenigstens sichtbar machten.
//
//     Das Stylesheet kommt jetzt aus ~/.config/hyprlaunch/style.css,
//     das src/styles/hyprlaunch-style.template erzeugt. Ein Wert, eine
//     Quelle.
//
// WARUM EIN FEHLENDES STYLESHEET DEN STARTER NICHT ANHAELT
//     Dieselbe Abwaegung wie in zepos-logout.c: ohne Stil ist die
//     Oberflaeche haesslich und vollstaendig bedienbar, mit Abbruch
//     waere SUPER+SPACE eine tote Taste, weil eine CSS-Datei fehlt.
//     Gesagt wird es trotzdem, mit dem Befehl, der sie schreibt -
//     sonst ist ein ungestylter Starter ein Zustand ohne Erklaerung.
static void loadStyleSheet(const std::string& path) {
    GtkCssProvider* css = gtk_css_provider_new();

    // load_from_path und nicht load_from_string: GTK meldet einen
    // Parserfehler ueber das Signal "parsing-error", und der Bericht
    // nennt Datei und Zeile nur, wenn der Provider die Datei kennt.
    // Ein Stylesheet mit einem Tippfehler verwirft in GTK4 die
    // betroffene Regel und schweigt sonst - das ist die Falle, in der
    // wofis Stylesheet jahrelang sass.
    g_signal_connect(css, "parsing-error",
        G_CALLBACK(+[](GtkCssProvider*, GtkCssSection* section,
                       const GError* error, gpointer) {
            g_autofree char* where = gtk_css_section_to_string(section);
            g_printerr("hyprlaunch-ui: %s: %s\n", where, error->message);
        }), nullptr);

    if (!g_file_test(path.c_str(), G_FILE_TEST_EXISTS)) {
        g_printerr("hyprlaunch-ui: %s fehlt - der Starter erscheint "
                   "ungestylt.\n"
                   "  zepos-generate -hyprlaunch-style schreibt die Datei.\n",
                   path.c_str());
        g_object_unref(css);
        return;
    }

    gtk_css_provider_load_from_path(css, path.c_str());
    gtk_style_context_add_provider_for_display(
        gdk_display_get_default(),
        GTK_STYLE_PROVIDER(css),
        GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
    g_object_unref(css);
}

// ── Unicode icons ────────────────────────────────────────────────────────────
static const char* ICON_SEARCH     = "\xf0\x9f\x94\x8d";  // Magnifying glass
static const char* ICON_CALCULATOR = "\xf0\x9f\xa7\xae";  // Abacus
static const char* ICON_APP        = "\xf0\x9f\x93\xa6";  // Package
static const char* ICON_RECENT     = "\xf0\x9f\x95\x90";  // Clock

// ============================================================================
// Construction
// ============================================================================

LauncherRenderer::LauncherRenderer(Config& config, AppDiscovery& discovery)
    : m_config(config), m_discovery(discovery) {}

LauncherRenderer::~LauncherRenderer() = default;

// Die Fensterhoehe, die auf den Schirm passt - und die er ihm laesst.
//
// WARUM DAS FENSTER SICH UEBERHAUPT DECKELN MUSS
//     Weil es jetzt mitwaechst. Vor dieser Aenderung war die
//     Zeilenhoehe eine Konstante im Objekt und der Starter blieb bei
//     jedem Faktor gleich gross - falsch, aber harmlos. Mit dem Faktor
//     1.85, den ZepOS ausliefert, ergaebe Config::windowHeight() aus
//     zwanzig Zeilen 1762 Pixel, und auf einem 1080er Schirm ist das
//     das Anderthalbfache der Bildschirmhoehe: der Starter waere
//     unten offen und die letzten Treffer unerreichbar.
//
// GEDECKELT WIRD AUF DIE HAELFTE UND NICHT AUF DEN GANZEN SCHIRM
//     Seit dem 12.08.2026, und die Begruendung steht bei
//     Config::modalCap(): ein Starter, der den ganzen Schirm
//     ausfuellt, hat aufgehoert, sich vor die Arbeit zu STELLEN.
//     Dieselbe Regel, dieselbe Zahl und derselbe Name wie in
//     menu/zepos_menu/window.py, plugins/hyprclipx und
//     src/templates/ags-overlay-utils.template.
//
// DER KLEINSTE SCHIRM UND NICHT DER GROESSTE, UND DAS IST EINE KORREKTUR
//     Hier stand `if (area.height > tallest)` - gedeckelt wurde also
//     gegen den HOECHSTEN angeschlossenen Schirm. Der Kommentar
//     darueber behauptete zugleich, gefragt werde "der Monitor, auf dem
//     der Zeiger steht"; das tat der Code nie. An einem Notebook mit
//     1080 Zeilen und einem 2160er Schirm daneben rechnete der Starter
//     mit 2160 und ging auf dem Notebookschirm unten heraus - genau der
//     Fehler, den diese Funktion verhindern soll, nur auf dem
//     unauffaelligeren der beiden Schirme.
//
//     Welchen Schirm die Layer-Shell nimmt, weiss dieser Prozess nicht:
//     gtk_layer_set_monitor() wird hier nicht gerufen, also entscheidet
//     der Compositor. Eine Grenze, die nur auf einem von zwei Schirmen
//     gilt, ist keine Grenze - deshalb der kleinste.
//
//     Ohne Anzeige - beim Uebersetzen, in einem Test ohne Monitor -
//     bleibt die eingestellte Zeilenzahl stehen: eine Begrenzung gegen
//     einen Schirm, den es nicht gibt, waere eine erfundene Zahl.
int LauncherRenderer::fittingHeight() const {
    GdkDisplay* display = gdk_display_get_default();
    if (display == nullptr)
        return m_config.windowHeight();

    GListModel* monitors = gdk_display_get_monitors(display);
    if (monitors == nullptr)
        return m_config.windowHeight();

    int shortest = 0;
    guint count = g_list_model_get_n_items(monitors);
    for (guint i = 0; i < count; i++) {
        GdkMonitor* monitor = GDK_MONITOR(g_list_model_get_item(monitors, i));
        if (monitor == nullptr)
            continue;
        GdkRectangle area{};
        gdk_monitor_get_geometry(monitor, &area);
        if (area.height > 0 && (shortest == 0 || area.height < shortest))
            shortest = area.height;
        g_object_unref(monitor);
    }
    if (shortest <= 0)
        return m_config.windowHeight();

    const int rows = m_config.rowsThatFit(m_config.modalCap(shortest));
    return m_config.searchHeight + rows * m_config.itemHeight + m_config.chrome;
}

// ============================================================================
// Der Aufbau
// ============================================================================

void LauncherRenderer::initialize() {
    loadStyleSheet(m_config.styleSheet);

    // Das Fenster
    m_window = gtk_window_new();
    // Der Titel, den ein Layer-Shell-Fenster traegt: kein Fenstertitel auf dem Schirm, aber die Antwort von
    // `hyprctl layers` und das, was eine Vorlesehilfe ansagt.
    //
    // Hier stand 'HyprLaunch', der Produktname des Baums, aus dem diese
    // Quelle kommt. Er ist nicht die CSS-Klasse zwei Zeilen weiter
    // unten - die bindet dieses Programm an sein eigenes Stylesheet
    // und bleibt deshalb, wie sie ist.
    gtk_window_set_title(GTK_WINDOW(m_window), "ZepOS Anwendungsstarter");
    gtk_window_set_decorated(GTK_WINDOW(m_window), FALSE);
    gtk_window_set_resizable(GTK_WINDOW(m_window), FALSE);

    gtk_layer_init_for_window(GTK_WINDOW(m_window));
    gtk_layer_set_layer(GTK_WINDOW(m_window), GTK_LAYER_SHELL_LAYER_OVERLAY);
    gtk_layer_set_keyboard_mode(GTK_WINDOW(m_window),
                                 GTK_LAYER_SHELL_KEYBOARD_MODE_EXCLUSIVE);
    const int height = fittingHeight();
    gtk_window_set_default_size(GTK_WINDOW(m_window),
                                 m_config.windowWidth, height);
    gtk_widget_set_size_request(m_window,
                                 m_config.windowWidth, height);
    gtk_layer_set_namespace(GTK_WINDOW(m_window), "hyprlaunch");

    // Die Klasse, ueber die das Stylesheet das Fenster selbst
    // anspricht. Sie hiess "HyprLaunch" - der Produktname des fremden
    // Baums - und heisst jetzt wie jede andere Klasse dieses Fensters,
    // mit dem Praefix launcher-.
    //
    // Es ist eine Bindung zwischen zwei Dateien, die BEIDE uns
    // gehoeren (hier und src/styles/hyprlaunch-style.template), und
    // deshalb ist sie umbenennbar - anders als der Objektname, die
    // Dispatcher und der Konfigurationsnamensraum, an denen der
    // Compositor und src/plugins.py haengen.
    gtk_widget_add_css_class(m_window, "launcher-window");

    // Nicht schliessen, nur verstecken
    g_signal_connect(m_window, "close-request",
        G_CALLBACK(+[](GtkWindow* win, gpointer) -> gboolean {
            gtk_widget_set_visible(GTK_WIDGET(win), FALSE);
            return TRUE;
        }), nullptr);

    // Die Widgets
    buildUI();

    // Die Tastatur
    GtkEventController* keyCtrl = gtk_event_controller_key_new();
    g_signal_connect(keyCtrl, "key-pressed", G_CALLBACK(onKeyPress), this);
    gtk_widget_add_controller(m_window, keyCtrl);
}

// ============================================================================
// Aufgehen, zugehen, umschalten
// ============================================================================

void LauncherRenderer::show() {
    if (!m_window) return;

    // Den Zustand zuruecksetzen
    m_query.clear();
    m_selectedIndex = 0;
    m_calculatorResult.clear();

    // Das Eingabefeld leeren. Der Text im leeren Feld steht in buildUI()
    // und haengt nicht an der Betriebsart - beide suchen, die eine in
    // den Anwendungen, die andere in den Hilfsskripten.
    gtk_editable_set_text(GTK_EDITABLE(m_searchEntry), "");

    // Die Daten neu holen
    if (m_mode == LauncherMode::Apps) {
        m_discovery.reloadApps();
        m_results = m_discovery.searchApps("");
    } else {
        m_discovery.reloadHelpers();
        m_results = m_discovery.searchHelpers("");
    }

    updateResults();

    // Zeigen
    gtk_widget_set_visible(m_window, TRUE);
    m_visible = true;

    // Wieder nach oben blaettern
    if (m_scroll) {
        GtkAdjustment* vadj = gtk_scrolled_window_get_vadjustment(
            GTK_SCROLLED_WINDOW(m_scroll));
        if (vadj) gtk_adjustment_set_value(vadj, 0);
    }
}

void LauncherRenderer::hide() {
    if (!m_window) return;
    gtk_widget_set_visible(m_window, FALSE);
    m_visible = false;
}

void LauncherRenderer::toggle() {
    if (m_visible) {
        hide();
    } else {
        show();
    }
}

bool LauncherRenderer::isVisible() const {
    return m_visible;
}

void LauncherRenderer::setMode(LauncherMode mode) {
    m_mode = mode;
}

// ============================================================================
// Die Oberflaeche
// ============================================================================

// Die Abstaende zwischen den Kindern einer GtkBox stehen als
// m_config.space(N) da und nicht als Zahl.
//
// N IST DIE SPROSSE UND NICHT DAS ERGEBNIS
//     space(12) heisst "die Sprosse, deren Grundwert 12 Full-HD-Pixel
//     ist", und bei dem ausgelieferten Faktor 1.85 kommen daraus 22
//     Pixel. Dieselbe Schreibweise wie {{STYLE_SPACE_12}} im
//     Stylesheet, aus derselben Leiter in src/sizes.py, mit demselben
//     Wert - der Unterschied ist nur, dass GTK fuer diese eine Zahl
//     keinen CSS-Selektor hat (Config.hpp fuehrt das aus).
//
// WARUM 12, 8 UND 4 UND SONST NICHTS
//     Das sind die drei Werte, die upstream hier stehen hatte, und
//     alle drei liegen bereits auf der Leiter. Es war also nichts zu
//     runden - im Gegensatz zu hyprclipx, wo 1 und 6 vorkamen. Gemessen
//     am 11.08.2026 mit `grep -n "gtk_box_new([^,]*, [1-9]"`.
void LauncherRenderer::buildUI() {
    GtkWidget* mainBox = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
    gtk_widget_add_css_class(mainBox, "launcher-container");

    // ── Die Suchzeile ──
    GtkWidget* searchBox = gtk_box_new(GTK_ORIENTATION_HORIZONTAL,
                                       m_config.space(12));
    gtk_widget_add_css_class(searchBox, "launcher-search");

    GtkWidget* searchIcon = gtk_label_new(ICON_SEARCH);
    gtk_widget_add_css_class(searchIcon, "launcher-search-icon");

    m_searchEntry = gtk_entry_new();
    gtk_widget_set_hexpand(m_searchEntry, TRUE);
    gtk_widget_set_can_focus(m_searchEntry, FALSE);
    gtk_widget_add_css_class(m_searchEntry, "launcher-search-input");
    // Der Text im leeren Feld. Er nennt das Gleichheitszeichen, weil
    // der Rechner sonst eine Funktion waere, die niemand findet.
    gtk_entry_set_placeholder_text(GTK_ENTRY(m_searchEntry),
                                    "Anwendungen suchen ... (= rechnet)");

    g_signal_connect(m_searchEntry, "changed",
        G_CALLBACK(+[](GtkEditable* editable, gpointer data) {
            auto* self = static_cast<LauncherRenderer*>(data);
            const char* text = gtk_editable_get_text(editable);
            self->onSearch(text ? text : "");
        }), this);

    gtk_box_append(GTK_BOX(searchBox), searchIcon);
    gtk_box_append(GTK_BOX(searchBox), m_searchEntry);

    // ── Die Trefferliste ──
    m_scroll = gtk_scrolled_window_new();
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(m_scroll),
                                    GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
    gtk_widget_set_vexpand(m_scroll, TRUE);
    gtk_widget_add_css_class(m_scroll, "launcher-scroll");

    m_resultsList = gtk_box_new(GTK_ORIENTATION_VERTICAL, m_config.space(4));
    gtk_widget_add_css_class(m_resultsList, "launcher-list");

    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(m_scroll), m_resultsList);

    // ── Zusammensetzen ──
    gtk_box_append(GTK_BOX(mainBox), searchBox);
    gtk_box_append(GTK_BOX(mainBox), m_scroll);

    gtk_window_set_child(GTK_WINDOW(m_window), mainBox);
}

// ============================================================================
// Was beim Tippen passiert
// ============================================================================

void LauncherRenderer::onSearch(const std::string& text) {
    m_query = text;
    m_selectedIndex = 0;
    m_calculatorResult.clear();

    if (m_mode == LauncherMode::Apps && !text.empty() && text[0] == '=') {
        m_calculatorResult = AppDiscovery::evaluateCalculator(text);
        m_results.clear();
    } else {
        if (m_mode == LauncherMode::Apps) {
            m_results = m_discovery.searchApps(text);
        } else {
            m_results = m_discovery.searchHelpers(text);
        }
    }

    updateResults();

    // Wieder nach oben blaettern
    if (m_scroll) {
        GtkAdjustment* vadj = gtk_scrolled_window_get_vadjustment(
            GTK_SCROLLED_WINDOW(m_scroll));
        if (vadj) gtk_adjustment_set_value(vadj, 0);
    }
}

// ============================================================================
// Die Trefferzeilen
// ============================================================================

void LauncherRenderer::removeAllChildren(GtkWidget* box) {
    GtkWidget* child = gtk_widget_get_first_child(box);
    while (child) {
        GtkWidget* next = gtk_widget_get_next_sibling(child);
        gtk_box_remove(GTK_BOX(box), child);
        child = next;
    }
}

void LauncherRenderer::updateResults() {
    if (!m_resultsList) return;

    removeAllChildren(m_resultsList);
    m_resultButtons.clear();

    // ── Die Zeile mit dem Rechenergebnis ──
    if (!m_calculatorResult.empty()) {
        GtkWidget* calcRow = gtk_button_new();
        gtk_widget_set_can_focus(calcRow, FALSE);
        gtk_widget_add_css_class(calcRow, "launcher-item");
        gtk_widget_add_css_class(calcRow, "calculator");
        if (m_selectedIndex == 0) gtk_widget_add_css_class(calcRow, "selected");

        GtkWidget* calcBox = gtk_box_new(GTK_ORIENTATION_HORIZONTAL,
                                         m_config.space(12));

        GtkWidget* calcIcon = gtk_label_new(ICON_CALCULATOR);
        gtk_widget_add_css_class(calcIcon, "launcher-icon");

        GtkWidget* calcContent = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
        gtk_widget_set_hexpand(calcContent, TRUE);

        GtkWidget* calcValue = gtk_label_new(m_calculatorResult.c_str());
        gtk_label_set_xalign(GTK_LABEL(calcValue), 0);
        gtk_widget_add_css_class(calcValue, "launcher-name");
        gtk_widget_add_css_class(calcValue, "calc-result");

        GtkWidget* calcHint = gtk_label_new("Enter kopiert das Ergebnis");
        gtk_label_set_xalign(GTK_LABEL(calcHint), 0);
        gtk_widget_add_css_class(calcHint, "launcher-desc");

        gtk_box_append(GTK_BOX(calcContent), calcValue);
        gtk_box_append(GTK_BOX(calcContent), calcHint);

        gtk_box_append(GTK_BOX(calcBox), calcIcon);
        gtk_box_append(GTK_BOX(calcBox), calcContent);

        gtk_button_set_child(GTK_BUTTON(calcRow), calcBox);

        // Der Klick
        std::string* resultCopy = new std::string(m_calculatorResult);
        g_signal_connect_data(calcRow, "clicked",
            G_CALLBACK(+[](GtkButton*, gpointer data) {
                auto* result = static_cast<std::string*>(data);
                AppDiscovery::copyToClipboard(*result);
            }), resultCopy,
            +[](gpointer data, GClosure*) {
                delete static_cast<std::string*>(data);
            }, G_CONNECT_DEFAULT);

        gtk_box_append(GTK_BOX(m_resultsList), calcRow);
        m_resultButtons.push_back(calcRow);
    }

    // ── Die Zeilen der gefundenen Anwendungen ──
    for (size_t i = 0; i < m_results.size(); i++) {
        const auto& entry = m_results[i];
        int actualIndex = !m_calculatorResult.empty()
                          ? static_cast<int>(i) + 1
                          : static_cast<int>(i);

        GtkWidget* row = gtk_button_new();
        gtk_widget_set_can_focus(row, FALSE);
        gtk_widget_add_css_class(row, "launcher-item");
        if (actualIndex == m_selectedIndex) {
            gtk_widget_add_css_class(row, "selected");
        }

        // Zuletzt benutzt? Die Frage stellt sich nur bei den
        // Anwendungen und nur, solange nichts getippt ist.
        bool isRecent = false;
        if (m_mode == LauncherMode::Apps && m_query.empty()) {
            // Bei leerer Eingabe stellt die Suche die zuletzt benutzten
            // nach vorn, also sind die ersten Zeilen die zuletzt
            // benutzten. Eine Naeherung ueber die POSITION - genau
            // wuesste es nur, wer die Liste selbst befragt.
            isRecent = (i < 5);
        }
        if (isRecent) {
            gtk_widget_add_css_class(row, "recent");
        }

        GtkWidget* rowBox = gtk_box_new(GTK_ORIENTATION_HORIZONTAL,
                                        m_config.space(12));

        // ── Das Symbol ──
        GtkWidget* iconWidget = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
        gtk_widget_set_valign(iconWidget, GTK_ALIGN_CENTER);
        gtk_widget_add_css_class(iconWidget, "launcher-icon-box");

        if (!entry.icon.empty()) {
            GtkWidget* image = gtk_image_new_from_icon_name(entry.icon.c_str());
            gtk_image_set_pixel_size(GTK_IMAGE(image), m_config.iconSize);
            gtk_box_append(GTK_BOX(iconWidget), image);
        } else {
            GtkWidget* fallback = gtk_label_new(ICON_APP);
            gtk_widget_add_css_class(fallback, "launcher-icon");
            gtk_box_append(GTK_BOX(iconWidget), fallback);
        }

        // ── Name und Beschreibung ──
        GtkWidget* content = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
        gtk_widget_set_hexpand(content, TRUE);
        gtk_widget_set_valign(content, GTK_ALIGN_CENTER);

        GtkWidget* nameRow = gtk_box_new(GTK_ORIENTATION_HORIZONTAL,
                                         m_config.space(8));

        GtkWidget* nameLabel = gtk_label_new(entry.name.c_str());
        gtk_label_set_xalign(GTK_LABEL(nameLabel), 0);
        gtk_label_set_ellipsize(GTK_LABEL(nameLabel), PANGO_ELLIPSIZE_END);
        gtk_widget_add_css_class(nameLabel, "launcher-name");
        gtk_box_append(GTK_BOX(nameRow), nameLabel);

        if (isRecent) {
            GtkWidget* recentBadge = gtk_label_new(ICON_RECENT);
            gtk_widget_add_css_class(recentBadge, "launcher-recent-badge");
            gtk_box_append(GTK_BOX(nameRow), recentBadge);
        }

        gtk_box_append(GTK_BOX(content), nameRow);

        if (!entry.description.empty()) {
            GtkWidget* desc = gtk_label_new(entry.description.c_str());
            gtk_label_set_xalign(GTK_LABEL(desc), 0);
            gtk_label_set_wrap(GTK_LABEL(desc), TRUE);
            gtk_label_set_ellipsize(GTK_LABEL(desc), PANGO_ELLIPSIZE_END);
            gtk_label_set_max_width_chars(GTK_LABEL(desc), m_config.descriptionChars);
            gtk_widget_add_css_class(desc, "launcher-desc");
            gtk_box_append(GTK_BOX(content), desc);
        }

        gtk_box_append(GTK_BOX(rowBox), iconWidget);
        gtk_box_append(GTK_BOX(rowBox), content);

        gtk_button_set_child(GTK_BUTTON(row), rowBox);

        // Der Klick, mit der Nummer der Zeile darin
        struct ClickData {
            LauncherRenderer* self;
            size_t index;
        };
        auto* clickData = new ClickData{this, i};
        g_signal_connect_data(row, "clicked",
            G_CALLBACK(+[](GtkButton*, gpointer data) {
                auto* cd = static_cast<ClickData*>(data);
                auto* self = cd->self;
                size_t idx = cd->index;
                if (idx < self->m_results.size()) {
                    if (self->m_mode == LauncherMode::Apps) {
                        self->m_discovery.launchApp(self->m_results[idx]);
                    } else {
                        self->m_discovery.launchHelper(self->m_results[idx]);
                    }
                    self->hide();
                }
            }), clickData,
            +[](gpointer data, GClosure*) {
                delete static_cast<ClickData*>(data);
            }, G_CONNECT_DEFAULT);

        gtk_box_append(GTK_BOX(m_resultsList), row);
        m_resultButtons.push_back(row);
    }
}

// ============================================================================
// Die Auswahl
// ============================================================================

void LauncherRenderer::updateSelection(int newIndex) {
    int maxIndex = static_cast<int>(m_resultButtons.size()) - 1;
    if (maxIndex < 0) return;

    int clampedIndex = std::max(0, std::min(newIndex, maxIndex));

    for (int i = 0; i <= maxIndex; i++) {
        if (i == clampedIndex) {
            gtk_widget_add_css_class(m_resultButtons[i], "selected");
        } else {
            gtk_widget_remove_css_class(m_resultButtons[i], "selected");
        }
    }

    m_selectedIndex = clampedIndex;
    scrollToIndex(clampedIndex);
}

void LauncherRenderer::scrollToIndex(int index) {
    if (!m_scroll || index < 0 || index >= static_cast<int>(m_resultButtons.size()))
        return;

    GtkAdjustment* vadj = gtk_scrolled_window_get_vadjustment(
        GTK_SCROLLED_WINDOW(m_scroll));
    if (!vadj) return;

    GtkWidget* btn = m_resultButtons[index];
    graphene_rect_t bounds;
    if (!gtk_widget_compute_bounds(btn, m_resultsList, &bounds)) return;

    double itemTop = bounds.origin.y;
    double itemHeight = bounds.size.height;
    double itemBottom = itemTop + itemHeight;

    double scrollY = gtk_adjustment_get_value(vadj);
    double scrollHeight = gtk_adjustment_get_page_size(vadj);

    if (itemBottom > scrollY + scrollHeight) {
        gtk_adjustment_set_value(vadj, itemBottom - scrollHeight + 8);
    } else if (itemTop < scrollY) {
        gtk_adjustment_set_value(vadj, itemTop - 8);
    }
}

// ============================================================================
// Das Gewaehlte ausfuehren
// ============================================================================

void LauncherRenderer::activateSelected() {
    if (!m_calculatorResult.empty() && m_selectedIndex == 0) {
        AppDiscovery::copyToClipboard(m_calculatorResult);
        hide();
        return;
    }

    int appIndex = !m_calculatorResult.empty()
                   ? m_selectedIndex - 1
                   : m_selectedIndex;

    if (appIndex >= 0 && appIndex < static_cast<int>(m_results.size())) {
        if (m_mode == LauncherMode::Apps) {
            m_discovery.launchApp(m_results[appIndex]);
        } else {
            m_discovery.launchHelper(m_results[appIndex]);
        }
        hide();
    }
}

// ============================================================================
// Die Tastatur
// ============================================================================

gboolean LauncherRenderer::onKeyPress(GtkEventControllerKey*, guint keyval,
                                       guint, GdkModifierType, gpointer data) {
    auto* self = static_cast<LauncherRenderer*>(data);
    int maxIndex = static_cast<int>(self->m_resultButtons.size()) - 1;

    switch (keyval) {
        case GDK_KEY_Escape:
            self->hide();
            return TRUE;

        case GDK_KEY_Down:
            self->updateSelection(std::min(self->m_selectedIndex + 1, maxIndex));
            return TRUE;

        case GDK_KEY_Up:
            self->updateSelection(std::max(self->m_selectedIndex - 1, 0));
            return TRUE;

        case GDK_KEY_Page_Down:
            self->updateSelection(std::min(self->m_selectedIndex + 5, maxIndex));
            return TRUE;

        case GDK_KEY_Page_Up:
            self->updateSelection(std::max(self->m_selectedIndex - 5, 0));
            return TRUE;

        case GDK_KEY_Home:
            self->updateSelection(0);
            return TRUE;

        case GDK_KEY_End:
            self->updateSelection(maxIndex);
            return TRUE;

        case GDK_KEY_Return:
        case GDK_KEY_KP_Enter:
            self->activateSelected();
            return TRUE;

        case GDK_KEY_Tab:
            if (maxIndex >= 0) {
                self->updateSelection((self->m_selectedIndex + 1) % (maxIndex + 1));
            }
            return TRUE;

        case GDK_KEY_BackSpace: {
            const char* t = gtk_editable_get_text(GTK_EDITABLE(self->m_searchEntry));
            std::string cur = t ? t : "";
            if (!cur.empty()) {
                cur.pop_back();
                gtk_editable_set_text(GTK_EDITABLE(self->m_searchEntry), cur.c_str());
            }
            return TRUE;
        }

        default: {
            guint32 ch = gdk_keyval_to_unicode(keyval);
            if (ch > 31 && ch < 127) {
                const char* t = gtk_editable_get_text(GTK_EDITABLE(self->m_searchEntry));
                std::string cur = t ? t : "";
                cur += static_cast<char>(ch);
                gtk_editable_set_text(GTK_EDITABLE(self->m_searchEntry), cur.c_str());
                return TRUE;
            }
            return FALSE;
        }
    }
}

} // namespace hyprlaunch
