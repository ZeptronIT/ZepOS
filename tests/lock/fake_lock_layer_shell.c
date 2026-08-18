/* SPDX-License-Identifier: GPL-3.0-or-later
 *
 * DER MUTANT. Dieses Programm ist ABSICHTLICH falsch.
 *
 * Es ist der Sperrbildschirm, den man baut, wenn man denkt, ein Fenster
 * ganz oben sei eine Sperre: ein Layer-Shell-Overlay auf der obersten
 * Ebene, ueber alles gespannt, mit exklusiver Tastatur - und mit
 * derselben Zeile auf stdout, die auch das echte zepos-lock schreibt.
 *
 * Auf einem Bildschirmfoto ist es von einer Sperre nicht zu
 * unterscheiden. Es ist trotzdem keine: der Compositor weiss nichts
 * davon, ein zweiter Client kann die Sitzung jederzeit sperren, und in
 * dem Moment, in dem dieser Prozess stirbt, liegt der Schreibtisch
 * offen.
 *
 * Es steht hier, damit tests/lock/test_lock_screen.py seine eigene
 * Zusicherung brechen kann. Eine Zusicherung, die "gesperrt" mit "ein
 * Fenster ist da" verwechselt, laesst dieses Programm durch - und dann
 * ist sie wertlos, ohne dass irgendetwas rot wird.
 */
#include <gtk/gtk.h>
#include <gtk4-layer-shell.h>

#define FAKE_NAMESPACE "zepos-lock"

int
main(void)
{
    GListModel *monitors;
    guint count, index;

    if (!gtk_init_check()) {
        g_printerr("fake: keine Anzeige\n");
        return 1;
    }

    monitors = gdk_display_get_monitors(gdk_display_get_default());
    count = g_list_model_get_n_items(monitors);
    for (index = 0; index < count; index++) {
        g_autoptr(GdkMonitor) monitor = g_list_model_get_item(monitors, index);
        GtkWidget *window = gtk_window_new();
        int edge;

        gtk_layer_init_for_window(GTK_WINDOW(window));
        gtk_layer_set_layer(GTK_WINDOW(window), GTK_LAYER_SHELL_LAYER_OVERLAY);
        gtk_layer_set_namespace(GTK_WINDOW(window), FAKE_NAMESPACE);
        gtk_layer_set_monitor(GTK_WINDOW(window), monitor);
        gtk_layer_set_keyboard_mode(GTK_WINDOW(window),
                                    GTK_LAYER_SHELL_KEYBOARD_MODE_EXCLUSIVE);
        for (edge = 0; edge < GTK_LAYER_SHELL_EDGE_ENTRY_NUMBER; edge++)
            gtk_layer_set_anchor(GTK_WINDOW(window), edge, TRUE);
        gtk_window_set_child(GTK_WINDOW(window), gtk_entry_new());
        gtk_window_present(GTK_WINDOW(window));
    }

    /* Dieselbe Zeile wie das echte Programm. Genau darum geht es. */
    g_print("zepos-lock: gesperrt\n");
    g_main_loop_run(g_main_loop_new(NULL, FALSE));
    return 0;
}
