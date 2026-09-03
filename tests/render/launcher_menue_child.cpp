// SPDX-License-Identifier: GPL-3.0-or-later
//
// Das Kind, das den Rechtsklick des Anwendungsstarters in einer echten
// Wayland-Sitzung ausloest - fuer tests/render/test_launcher_menue.py.
//
// WARUM ES DIESE DATEI GIBT, UND WARUM SIE NICHT DER STARTER SELBST IST
//     Gemessen werden soll, was auf einem Compositor passiert, wenn
//     jemand auf eine Trefferzeile rechtsklickt: ob ein GtkPopover auf
//     einer Layer-Shell-Flaeche ueberhaupt aufgeht, ob er ueber ihren
//     Rand darf, und was Escape dann tut.
//
//     Ein Mausklick laesst sich in diese Sitzung nicht schieben.
//     GEMESSEN am 21.08.2026 auf dieser Maschine: `wtype` ist da (und
//     schickt Tasten), ydotool, wlrctl und dotool sind es nicht - es
//     gibt kein Werkzeug fuer einen Zeigerknopf. tests/render/
//     test_starter.py hat denselben Befund schon einmal aufgeschrieben.
//
//     Also loest dieses Kind die Geste selbst aus. NICHT, indem es
//     showMenu() ruft - das ist privat, und ein Test, der sich Zugang
//     zu privaten Feldern verschafft, misst etwas anderes als das
//     Programm. Sondern ueber den Weg, den GTK dafuer offen haelt:
//
//         gtk_widget_observe_controllers(row)
//             -> die Controller, die WIRKLICH an der Zeile haengen
//         gtk_gesture_single_get_button(gesture)
//             -> welche Taste dieser Controller erwartet
//         g_signal_emit_by_name(gesture, "pressed", 1, x, y)
//             -> derselbe Rueckruf, den ein echter Knopfdruck ausloest
//
//     Was damit NICHT gemessen ist: dass Hyprland den Knopfdruck an die
//     Flaeche zustellt. Das ist die Aufgabe des Compositors und nicht
//     die dieses Patches. Alles danach - die Geste, ihr Rueckruf, der
//     Popover, sein Stylesheet, die Tastatur - ist echt.
//
// WIE ES BEDIENT WIRD
//     Zeilenweise ueber die Standardeingabe, Antwort auf der
//     Standardausgabe. Dieselbe Form wie dock_menue_child.tsx, damit
//     ein Leser nicht zwei Bedienweisen lernen muss.
//
//         bereit        wieviele Trefferzeilen stehen da
//         rechtsklick   die Geste der ersten Zeile ausloesen
//         menue         steht ein Menue, und mit welchen Punkten
//         ende          Schluss

#include "hyprlaunch/AppDiscovery.hpp"
#include "hyprlaunch/ConfigParser.hpp"
#include "hyprlaunch/LauncherRenderer.hpp"

#include <gtk/gtk.h>
#include <cstdio>
#include <string>
#include <vector>

using namespace hyprlaunch;

namespace {

GMainLoop* g_loop = nullptr;

/** Antworten und sofort schreiben - der Test liest zeilenweise mit. */
void answer(const std::string& text) {
    std::printf("%s\n", text.c_str());
    std::fflush(stdout);
}

/** Das Fenster des Starters unter allen Toplevels.
 *
 * Ueber die CSS-Klasse, die LauncherRenderer::initialize() vergibt.
 * gtk_window_get_toplevels() ist oeffentlich und nennt genau die
 * Fenster, die GTK gerade fuehrt.
 */
GtkWidget* launcherWindow() {
    GListModel* tops = gtk_window_get_toplevels();
    const guint count = tops ? g_list_model_get_n_items(tops) : 0;
    for (guint i = 0; i < count; i++) {
        auto* window = static_cast<GtkWidget*>(g_list_model_get_item(tops, i));
        if (!window) continue;
        const bool mine = gtk_widget_has_css_class(window, "launcher-window");
        g_object_unref(window);
        if (mine) return window;
    }
    return nullptr;
}

/** Jeden Nachfahren mit dieser CSS-Klasse einsammeln, in Baumfolge. */
void collect(GtkWidget* root, const char* cssClass,
             std::vector<GtkWidget*>& found) {
    if (!root) return;
    if (gtk_widget_has_css_class(root, cssClass))
        found.push_back(root);
    for (GtkWidget* child = gtk_widget_get_first_child(root); child;
         child = gtk_widget_get_next_sibling(child)) {
        collect(child, cssClass, found);
    }
}

std::vector<GtkWidget*> widgetsWithClass(GtkWidget* root, const char* cssClass) {
    std::vector<GtkWidget*> found;
    collect(root, cssClass, found);
    return found;
}

/** Die Rechtsklick-Geste einer Zeile, oder nullptr. */
GtkGesture* secondaryGesture(GtkWidget* row) {
    GListModel* controllers = gtk_widget_observe_controllers(row);
    const guint count = controllers ? g_list_model_get_n_items(controllers) : 0;
    GtkGesture* found = nullptr;

    for (guint i = 0; i < count && !found; i++) {
        auto* controller =
            static_cast<GtkEventController*>(g_list_model_get_item(controllers, i));
        if (!controller) continue;
        if (GTK_IS_GESTURE_CLICK(controller)) {
            const guint button =
                gtk_gesture_single_get_button(GTK_GESTURE_SINGLE(controller));
            if (button == GDK_BUTTON_SECONDARY)
                found = GTK_GESTURE(controller);
        }
        g_object_unref(controller);
    }
    if (controllers) g_object_unref(controllers);
    return found;
}

/** Der offene Popover unter den Toplevels, oder nullptr.
 *
 * Ein GtkPopover ist in GTK4 KEIN Toplevel-Fenster - er haengt am
 * Widget, an das set_parent() ihn gehaengt hat. Gesucht wird er
 * deshalb im Baum des Starterfensters, ueber die Klasse, die
 * showMenu() vergibt.
 */
GtkWidget* openMenu() {
    GtkWidget* window = launcherWindow();
    if (!window) return nullptr;
    for (GtkWidget* found : widgetsWithClass(window, "launcher-menu-popover")) {
        if (gtk_widget_get_mapped(found))
            return found;
    }
    return nullptr;
}

std::string menuLabels() {
    GtkWidget* menu = openMenu();
    if (!menu) return "";
    std::string joined;
    for (GtkWidget* label : widgetsWithClass(menu, "launcher-menu-label")) {
        if (!GTK_IS_LABEL(label)) continue;
        const char* text = gtk_label_get_text(GTK_LABEL(label));
        if (!text) continue;
        if (!joined.empty()) joined += " | ";
        joined += text;
    }
    return joined;
}

// ============================================================================
// Die Befehle
// ============================================================================

void handle(const std::string& command) {
    if (command == "bereit") {
        GtkWidget* window = launcherWindow();
        if (!window) {
            answer("kein-fenster");
            return;
        }
        const auto rows = widgetsWithClass(window, "launcher-item");
        answer("zeilen=" + std::to_string(rows.size()));
        return;
    }

    if (command == "rechtsklick") {
        GtkWidget* window = launcherWindow();
        if (!window) {
            answer("kein-fenster");
            return;
        }
        const auto rows = widgetsWithClass(window, "launcher-item");
        if (rows.empty()) {
            answer("keine-zeile");
            return;
        }
        GtkGesture* gesture = secondaryGesture(rows.front());
        if (!gesture) {
            answer("keine-geste");
            return;
        }
        // Die Punkte sind die Klickstelle IN der Zeile. 12/12 ist
        // irgendwo links oben darin - showMenu() reicht sie als
        // gtk_popover_set_pointing_to() weiter.
        g_signal_emit_by_name(gesture, "pressed", 1, 12.0, 12.0);
        answer("geklickt");
        return;
    }

    if (command == "menue") {
        const std::string labels = menuLabels();
        answer(labels.empty() ? "zu" : ("offen: " + labels));
        return;
    }

    // EINEN PUNKT WIRKLICH AUSLOESEN - seit dem 03.09.2026.
    //
    //     Der Nutzer, mehrfach und zuletzt woertlich: "wnen ich
    //     rechtklick auf ein hyprlaunch item mache und zur dock oder
    //     home hinzufuegen klappt nicht". Bis heute hat KEIN Lauf einen
    //     Punkt dieses Menues je ausgeloest - gemessen wurde, dass es
    //     aufgeht und die richtigen Beschriftungen traegt. Ob der Klick
    //     etwas bewirkt, stand nirgends.
    //
    //     `clicked` und keine Zeigerbewegung: der Knopf traegt seinen
    //     Rueckruf an genau diesem Signal (LauncherRenderer.cpp,
    //     g_signal_connect_data(line, "clicked", ...)). Damit misst
    //     dieser Weg den Rueckruf und nicht GTKs Zeigerverwaltung.
    if (command.rfind("waehle:", 0) == 0) {
        const std::string gesucht = command.substr(7);
        GtkWidget* menu = openMenu();
        if (!menu) {
            answer("kein-menue");
            return;
        }
        for (GtkWidget* label : widgetsWithClass(menu, "launcher-menu-label")) {
            if (!GTK_IS_LABEL(label)) continue;
            const char* text = gtk_label_get_text(GTK_LABEL(label));
            if (!text || gesucht != std::string(text)) continue;
            GtkWidget* knopf = gtk_widget_get_ancestor(label, GTK_TYPE_BUTTON);
            if (!knopf) {
                answer("kein-knopf");
                return;
            }
            g_signal_emit_by_name(knopf, "clicked");
            answer("gewaehlt:" + gesucht);
            return;
        }
        answer("nicht-gefunden:" + gesucht);
        return;
    }

    if (command == "ende") {
        answer("tschuess");
        if (g_loop) g_main_loop_quit(g_loop);
        return;
    }

    answer("unbekannt: " + command);
}

gboolean onInput(GIOChannel* channel, GIOCondition condition, gpointer) {
    if (condition & (G_IO_HUP | G_IO_ERR)) {
        if (g_loop) g_main_loop_quit(g_loop);
        return G_SOURCE_REMOVE;
    }

    gchar* line = nullptr;
    gsize length = 0;
    if (g_io_channel_read_line(channel, &line, &length, nullptr, nullptr)
            != G_IO_STATUS_NORMAL) {
        g_free(line);
        return G_SOURCE_CONTINUE;
    }

    std::string command = line ? line : "";
    g_free(line);
    while (!command.empty() && (command.back() == '\n' || command.back() == '\r'))
        command.pop_back();

    if (!command.empty())
        handle(command);
    return G_SOURCE_CONTINUE;
}

} // namespace

int main() {
    gtk_init();

    Config config = loadConfig();
    AppDiscovery discovery(config);
    LauncherRenderer renderer(config, discovery);

    renderer.initialize();
    renderer.show();

    GIOChannel* input = g_io_channel_unix_new(0);
    g_io_add_watch(input, static_cast<GIOCondition>(G_IO_IN | G_IO_HUP | G_IO_ERR),
                   onInput, nullptr);

    answer("start");

    g_loop = g_main_loop_new(nullptr, FALSE);
    g_main_loop_run(g_loop);
    g_main_loop_unref(g_loop);
    g_io_channel_unref(input);
    return 0;
}
