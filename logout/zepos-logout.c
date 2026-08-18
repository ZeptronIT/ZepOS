/* SPDX-License-Identifier: GPL-3.0-or-later
 *
 * zepos-logout - die Abmeldemaske, die SUPER+M oeffnet.
 *
 * WARUM ZepOS DIESES PROGRAMM SELBST SCHREIBT
 *     Der Nutzer hat am 11.08.2026 entschieden, dass die Oberflaeche
 *     durchgehend auf GTK4 steht. Gemessen an der Installation dieser
 *     Maschine stand die Abmeldemaske nicht darauf:
 *
 *         objdump -p /usr/bin/wlogout | grep NEEDED
 *           NEEDED  libgtk-3.so.0
 *           NEEDED  libgtk-layer-shell.so.0
 *
 *     Es gibt keinen Weg, das an wlogout zu beheben. Gemessen am
 *     Ursprung (ArtsyMacaw/wlogout, HEAD 350fe88, 26.05.2024 - seither
 *     kein Commit): meson.build Zeile 73 fordert `gtk+-wayland-3.0`,
 *     main.c ruft gtk_main_quit() und gtk_widget_destroy(), und
 *     `git grep -i gtk4` findet im ganzen Baum keine Zeile. Ein GTK4-
 *     wlogout waere eine Neufassung von main.c gegen eine andere API -
 *     also dieses Programm, nur unter fremdem Namen.
 *
 * WARUM NICHT wleave
 *     Die Vermutung, wleave (AMNatty/wleave) sei GTK4, ist RICHTIG und
 *     an der Quelle belegt: Cargo.toml von HEAD 0cc1a0b (25.07.2026)
 *     nennt gtk4 0.10, gtk4-layer-shell 0.7 und libadwaita 0.8. Das
 *     Toolkit ist also nicht der Grund, aus dem es hier nicht steht.
 *
 *     Der Grund steht in packaging/aylurs-gtk-shell/PKGBUILD unter "WHY
 *     THE NPM DEPENDENCY IS A SOURCE AND NOT A BUILD STEP": ein Bau, der
 *     einen Paketmanager eine Registry befragen laesst, ist das
 *     Gegenteil eines angehefteten Baus. Fuer AGS war das EIN Tarball,
 *     der als source= mit Pruefsumme eingetragen wurde. wleaves
 *     Cargo.lock zaehlt 295 Kisten; packaging/Dockerfile hat ausserdem
 *     keine Rust-Werkzeugkette. Fuer dieses Programm hat er alles:
 *     base-devel, meson, ninja, pkgconf, gtk4, gtk4-layer-shell und
 *     json-glib stehen schon darin, der Bau braucht am Container keine
 *     Zeile.
 *
 * WARUM KEIN AGS-WIDGET
 *     AGS laeuft ohnehin und ist GTK4 - das waere billiger gewesen. Eine
 *     Abmeldemaske, die die Shell zum Leben braucht, ist aber genau dann
 *     eine tote Taste, wenn die Shell nicht mehr laeuft; und das ist der
 *     Moment, in dem jemand sie sucht.
 *
 * WARUM ES KEINE EINGEBAUTE VORGABE UND KEIN /etc/zepos-logout GIBT
 *     Weil beides eine zweite Quelle fuer Symbole und Aktionen waere,
 *     und die zweite Quelle ist die, die veraltet. Das Layout kann auf
 *     einem laufenden Desktop auch nicht fehlen, gemessen an der
 *     Aufrufkette: start-hyprland ruft vor JEDEM Sitzungsstart
 *     `hyprland-status generate`, und das ruft `generate_config.sh
 *     -logout-config` und `-logout-style`
 *     (src/templates/hyprland-status-config.template). Fehlt die Datei
 *     doch, nennt dieses Programm den Befehl, der sie schreibt, statt
 *     stumm zu enden.
 */
#include <gtk/gtk.h>
#include <gtk4-layer-shell.h>
#include <json-glib/json-glib.h>
#include <stdlib.h>
#include <string.h>

#define ZEPOS_LOGOUT_NAMESPACE "zepos-logout"

typedef struct {
    char *label;    /* zugleich der CSS-Knotenname: button#lock */
    char *icon;     /* Nerd-Font-Glyphe aus src/icon_definition.py */
    char *text;
    char *action;   /* Shell-Zeile */
    guint keyval;   /* 0, wenn die Vorlage keinen Tastenkuerzel nennt */
    char *keybind;  /* die Beschriftung dazu */
} ZepEntry;

typedef struct {
    GPtrArray *entries;     /* ZepEntry* */
    GPtrArray *windows;     /* GtkWindow* */
    GMainLoop *loop;
    char *chosen;           /* die Aktion, die ausgefuehrt wird; NULL = keine */
    int columns;
} ZepApp;

static void
zep_entry_free(gpointer data)
{
    ZepEntry *e = data;
    g_free(e->label);
    g_free(e->icon);
    g_free(e->text);
    g_free(e->action);
    g_free(e->keybind);
    g_free(e);
}

/* Die beiden Pfade, und in dieser Reihenfolge.
 *
 * $XDG_CONFIG_HOME/zepos-logout/ ist, wohin generate_config.sh schreibt
 * (CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/zepos-logout"). Der Fall, dass
 * XDG_CONFIG_HOME leer ist, ist nicht der exotische: die Variable ist auf
 * einer frischen Anmeldung oft nicht gesetzt, und g_get_user_config_dir()
 * beantwortet genau das mit ~/.config, statt einen leeren Pfad zu bauen. */
static char *
zep_config_path(const char *basename)
{
    return g_build_filename(g_get_user_config_dir(), ZEPOS_LOGOUT_NAMESPACE,
                            basename, NULL);
}

static char *
zep_member_string(JsonObject *obj, const char *name)
{
    if (!json_object_has_member(obj, name))
        return NULL;
    JsonNode *node = json_object_get_member(obj, name);
    if (!JSON_NODE_HOLDS_VALUE(node))
        return NULL;
    const char *value = json_node_get_string(node);
    return value ? g_strdup(value) : NULL;
}

/* Liest das erzeugte Layout.
 *
 * Ein Eintrag ohne `label` oder ohne `action` wird abgewiesen statt
 * uebersprungen. Uebersprungen hiesse: eine Schaltflaeche weniger, ohne
 * ein Wort - und die eine, die fehlt, ist die, die jemand sucht. */
static gboolean
zep_load_layout(ZepApp *app, const char *path, GError **error)
{
    g_autoptr(JsonParser) parser = json_parser_new();
    if (!json_parser_load_from_file(parser, path, error))
        return FALSE;

    JsonNode *root = json_parser_get_root(parser);
    if (root == NULL || !JSON_NODE_HOLDS_ARRAY(root)) {
        g_set_error(error, G_FILE_ERROR, G_FILE_ERROR_INVAL,
                    "%s ist kein JSON-Array", path);
        return FALSE;
    }

    JsonArray *array = json_node_get_array(root);
    guint count = json_array_get_length(array);
    for (guint i = 0; i < count; i++) {
        JsonNode *node = json_array_get_element(array, i);
        if (!JSON_NODE_HOLDS_OBJECT(node)) {
            g_set_error(error, G_FILE_ERROR, G_FILE_ERROR_INVAL,
                        "%s: Eintrag %u ist kein Objekt", path, i);
            return FALSE;
        }
        JsonObject *obj = json_node_get_object(node);

        ZepEntry *entry = g_new0(ZepEntry, 1);
        entry->label = zep_member_string(obj, "label");
        entry->icon = zep_member_string(obj, "icon");
        entry->text = zep_member_string(obj, "text");
        entry->action = zep_member_string(obj, "action");
        entry->keybind = zep_member_string(obj, "keybind");
        if (entry->keybind != NULL && entry->keybind[0] != '\0')
            entry->keyval = gdk_unicode_to_keyval(g_utf8_get_char(entry->keybind));

        if (entry->label == NULL || entry->action == NULL) {
            zep_entry_free(entry);
            g_set_error(error, G_FILE_ERROR, G_FILE_ERROR_INVAL,
                        "%s: Eintrag %u hat kein \"label\" oder kein \"action\"",
                        path, i);
            return FALSE;
        }
        g_ptr_array_add(app->entries, entry);
    }

    if (app->entries->len == 0) {
        g_set_error(error, G_FILE_ERROR, G_FILE_ERROR_INVAL,
                    "%s nennt keinen einzigen Eintrag", path);
        return FALSE;
    }
    return TRUE;
}

/* Die Maske verschwindet VOR der Aktion, nicht danach.
 *
 * Gemessen an wlogout, das es genauso macht und aus demselben Grund: die
 * Aktion von `lock` startet zepos-lock, und ein Overlay-Layer, das noch
 * steht, laege darueber. Der Prozess wird nach der Schleife gestartet,
 * damit auch der letzte Frame weg ist, bevor irgendetwas anderes den
 * Bildschirm nimmt. */
static void
zep_choose(ZepApp *app, const char *action)
{
    g_free(app->chosen);
    app->chosen = action ? g_strdup(action) : NULL;
    g_main_loop_quit(app->loop);
}

static void
on_button_clicked(GtkButton *button, gpointer user_data)
{
    ZepApp *app = user_data;
    const ZepEntry *entry = g_object_get_data(G_OBJECT(button), "zep-entry");
    zep_choose(app, entry->action);
}

static gboolean
on_key_pressed(GtkEventControllerKey *controller, guint keyval,
               guint keycode, GdkModifierType state, gpointer user_data)
{
    (void) controller; (void) keycode; (void) state;
    ZepApp *app = user_data;

    if (keyval == GDK_KEY_Escape) {
        zep_choose(app, NULL);
        return TRUE;
    }

    guint lower = gdk_keyval_to_lower(keyval);
    for (guint i = 0; i < app->entries->len; i++) {
        const ZepEntry *entry = g_ptr_array_index(app->entries, i);
        if (entry->keyval != 0 && gdk_keyval_to_lower(entry->keyval) == lower) {
            zep_choose(app, entry->action);
            return TRUE;
        }
    }
    return FALSE;
}

/* Ein Klick neben die Schaltflaechen schliesst.
 *
 * Der Zeiger liegt beim Oeffnen irgendwo, und "irgendwo" ist auf einer
 * Maske, die den ganzen Bildschirm einnimmt, meistens neben einer
 * Schaltflaeche. Ohne das hier haette die Maus keinen Weg heraus - die
 * Tastatur haette Escape, die Maus nichts. */
static void
on_background_pressed(GtkGestureClick *gesture, int n_press,
                      double x, double y, gpointer user_data)
{
    (void) gesture; (void) n_press; (void) x; (void) y;
    zep_choose(user_data, NULL);
}

/* Die Spaltenzahl, wenn niemand eine nennt: die Wurzel, aufgerundet.
 *
 * Sechs Eintraege werden damit 3x2 statt 6x1. Eine Zeile aus sechs
 * Feldern auf einem 3440er Schirm sind sechs sehr flache Streifen, und
 * die Trefferflaeche einer Schaltflaeche ist das, was diese Maske
 * ausmacht: sie wird unter Zeitdruck bedient. */
static int
zep_default_columns(guint count)
{
    int columns = 1;
    while ((guint) (columns * columns) < count)
        columns++;
    return columns;
}

static GtkWidget *
zep_build_grid(ZepApp *app)
{
    GtkWidget *grid = gtk_grid_new();
    gtk_widget_set_name(grid, "buttons");
    gtk_grid_set_row_homogeneous(GTK_GRID(grid), TRUE);
    gtk_grid_set_column_homogeneous(GTK_GRID(grid), TRUE);
    gtk_widget_set_hexpand(grid, TRUE);
    gtk_widget_set_vexpand(grid, TRUE);

    int columns = app->columns > 0 ? app->columns
                                   : zep_default_columns(app->entries->len);

    for (guint i = 0; i < app->entries->len; i++) {
        ZepEntry *entry = g_ptr_array_index(app->entries, i);

        GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
        gtk_widget_set_halign(box, GTK_ALIGN_CENTER);
        gtk_widget_set_valign(box, GTK_ALIGN_CENTER);

        /* Das Symbol ist eine Glyphe und kein Bild.
         *
         * wlogout zeichnete sechs PNG aus /usr/share/wlogout/icons als
         * background-image. Die kamen aus dem fremden Paket, sie lagen
         * neben der Symbolquelle dieses Projekts statt darin, und mit
         * dem Paket waeren sie weg. src/icon_definition.py fuehrt
         * ICON_LOCK, ICON_LOGOUT, ICON_REBOOT, ICON_SHUTDOWN,
         * ICON_SUSPEND und ICON_HIBERNATE ohnehin - die Vorlage setzt
         * sie ein, und das Symbol steht damit unter derselben Regel wie
         * jedes andere im Desktop. */
        if (entry->icon != NULL && entry->icon[0] != '\0') {
            GtkWidget *icon = gtk_label_new(entry->icon);
            gtk_widget_add_css_class(icon, "icon");
            gtk_box_append(GTK_BOX(box), icon);
        }
        if (entry->text != NULL && entry->text[0] != '\0') {
            GtkWidget *text = gtk_label_new(entry->text);
            gtk_widget_add_css_class(text, "text");
            gtk_box_append(GTK_BOX(box), text);
        }
        if (entry->keybind != NULL && entry->keybind[0] != '\0') {
            GtkWidget *key = gtk_label_new(entry->keybind);
            gtk_widget_add_css_class(key, "keybind");
            gtk_box_append(GTK_BOX(box), key);
        }

        GtkWidget *button = gtk_button_new();
        /* Der Knotenname ist das, worauf die Stilvorlage zeigt:
         * button#lock, button#shutdown. Ohne ihn traegt jede
         * Schaltflaeche dieselbe Farbe, und die Kostenleiter - sicher,
         * Neustart, Ausschalten - waere unsichtbar, ohne dass irgendetwas
         * fehlschluege. */
        gtk_widget_set_name(button, entry->label);
        gtk_button_set_child(GTK_BUTTON(button), box);
        gtk_widget_set_hexpand(button, TRUE);
        gtk_widget_set_vexpand(button, TRUE);
        g_object_set_data(G_OBJECT(button), "zep-entry", entry);
        g_signal_connect(button, "clicked", G_CALLBACK(on_button_clicked), app);

        gtk_grid_attach(GTK_GRID(grid), button,
                        (int) i % columns, (int) i / columns, 1, 1);
    }
    return grid;
}

/* Ein Fenster je Monitor.
 *
 * Ohne gtk_layer_set_monitor legt der Compositor die Oberflaeche auf den
 * Monitor, den er gerade fuer richtig haelt, und die anderen bleiben
 * bedienbar - eine Maske, die den Rest der Sitzung sperren soll, sperrt
 * dann einen Schirm von dreien. */
static void
zep_add_window(ZepApp *app, GdkMonitor *monitor)
{
    GtkWidget *window = gtk_window_new();

    gtk_layer_init_for_window(GTK_WINDOW(window));
    gtk_layer_set_layer(GTK_WINDOW(window), GTK_LAYER_SHELL_LAYER_OVERLAY);
    gtk_layer_set_namespace(GTK_WINDOW(window), ZEPOS_LOGOUT_NAMESPACE);
    gtk_layer_set_monitor(GTK_WINDOW(window), monitor);
    /* EXCLUSIVE, nicht ON_DEMAND: die Tastenkuerzel l/e/b/p/u/h muessen
     * ankommen, ohne dass jemand die Maske erst anklickt. */
    gtk_layer_set_keyboard_mode(GTK_WINDOW(window),
                                GTK_LAYER_SHELL_KEYBOARD_MODE_EXCLUSIVE);
    for (int edge = 0; edge < GTK_LAYER_SHELL_EDGE_ENTRY_NUMBER; edge++)
        gtk_layer_set_anchor(GTK_WINDOW(window), edge, TRUE);

    GtkEventController *keys = gtk_event_controller_key_new();
    g_signal_connect(keys, "key-pressed", G_CALLBACK(on_key_pressed), app);
    gtk_widget_add_controller(window, keys);

    GtkGesture *click = gtk_gesture_click_new();
    g_signal_connect(click, "pressed", G_CALLBACK(on_background_pressed), app);
    gtk_widget_add_controller(window, GTK_EVENT_CONTROLLER(click));

    gtk_window_set_child(GTK_WINDOW(window), zep_build_grid(app));
    g_ptr_array_add(app->windows, window);
    gtk_window_present(GTK_WINDOW(window));
}

static gboolean
zep_load_css(const char *path, GError **error)
{
    if (!g_file_test(path, G_FILE_TEST_EXISTS)) {
        g_set_error(error, G_FILE_ERROR, G_FILE_ERROR_NOENT,
                    "%s fehlt", path);
        return FALSE;
    }
    g_autoptr(GFile) file = g_file_new_for_path(path);
    GtkCssProvider *provider = gtk_css_provider_new();
    gtk_css_provider_load_from_file(provider, file);
    gtk_style_context_add_provider_for_display(
        gdk_display_get_default(), GTK_STYLE_PROVIDER(provider),
        GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
    g_object_unref(provider);
    return TRUE;
}

int
main(int argc, char **argv)
{
    g_autofree char *layout_path = NULL;
    g_autofree char *css_path = NULL;
    int columns = 0;
    gboolean show_version = FALSE;

    const GOptionEntry options[] = {
        { "layout", 'l', 0, G_OPTION_ARG_FILENAME, &layout_path,
          "Layoutdatei statt der erzeugten", "PFAD" },
        { "css", 'C', 0, G_OPTION_ARG_FILENAME, &css_path,
          "Stildatei statt der erzeugten", "PFAD" },
        { "columns", 'b', 0, G_OPTION_ARG_INT, &columns,
          "Schaltflaechen je Zeile", "N" },
        { "version", 'v', 0, G_OPTION_ARG_NONE, &show_version,
          "Version ausgeben und enden", NULL },
        { NULL, 0, 0, 0, NULL, NULL, NULL },
    };

    g_autoptr(GOptionContext) context =
        g_option_context_new("- die Abmeldemaske von ZepOS");
    g_option_context_add_main_entries(context, options, NULL);
    g_autoptr(GError) error = NULL;
    if (!g_option_context_parse(context, &argc, &argv, &error)) {
        g_printerr("zepos-logout: %s\n", error->message);
        return 1;
    }
    if (show_version) {
        g_print("zepos-logout %s\n", ZEPOS_LOGOUT_VERSION);
        return 0;
    }

    gtk_init();

    if (css_path == NULL)
        css_path = zep_config_path("style.css");
    if (!zep_load_css(css_path, &error)) {
        /* Kein Abbruch. Ohne Stil ist die Maske haesslich und
         * vollstaendig bedienbar; mit Abbruch waere SUPER+M tot, weil
         * eine CSS-Datei fehlt. Die Kostenleiter waere allerdings weg,
         * also wird es gesagt. */
        g_printerr("zepos-logout: %s - die Maske erscheint ungestylt.\n"
                   "  ./generate_config.sh -logout-style schreibt sie.\n",
                   error->message);
        g_clear_error(&error);
    }

    ZepApp app = {
        .entries = g_ptr_array_new_with_free_func(zep_entry_free),
        .windows = g_ptr_array_new(),
        .loop = g_main_loop_new(NULL, FALSE),
        .chosen = NULL,
        .columns = columns,
    };

    if (layout_path == NULL)
        layout_path = zep_config_path("layout.json");
    if (!zep_load_layout(&app, layout_path, &error)) {
        g_printerr("zepos-logout: %s\n"
                   "  ./generate_config.sh -logout-config schreibt die Datei.\n",
                   error->message);
        return 1;
    }

    GListModel *monitors = gdk_display_get_monitors(gdk_display_get_default());
    guint n_monitors = g_list_model_get_n_items(monitors);
    if (n_monitors == 0) {
        g_printerr("zepos-logout: der Compositor meldet keinen Monitor.\n");
        return 1;
    }
    for (guint i = 0; i < n_monitors; i++) {
        g_autoptr(GdkMonitor) monitor = g_list_model_get_item(monitors, i);
        zep_add_window(&app, monitor);
    }

    g_main_loop_run(app.loop);

    for (guint i = 0; i < app.windows->len; i++)
        gtk_window_destroy(g_ptr_array_index(app.windows, i));
    /* Einmal durch die Hauptschleife, damit das Zerstoeren auch beim
     * Compositor angekommen ist, bevor die Aktion startet. Ohne das
     * bleibt bei `lock` fuer einen Moment ein Overlay ueber dem
     * Sperrbildschirm. */
    while (g_main_context_iteration(NULL, FALSE))
        ;

    int status = 1;
    if (app.chosen != NULL) {
        /* /bin/sh -c, weil die Aktionen aus der Vorlage Kommandozeilen
         * sind und keine Dateinamen: "systemctl poweroff" ist als ein
         * Wort keine ausfuehrbare Datei, und die Vorlage darf jederzeit
         * eine Zeile mit Pipe oder || tragen. Der Prozess wird
         * abgekoppelt: systemctl poweroff beendet diesen hier, waehrend
         * es laeuft. */
        const char *sh[] = { "/bin/sh", "-c", app.chosen, NULL };
        if (!g_spawn_async(NULL, (char **) sh, NULL,
                           G_SPAWN_SEARCH_PATH | G_SPAWN_STDOUT_TO_DEV_NULL,
                           NULL, NULL, NULL, &error)) {
            g_printerr("zepos-logout: %s liess sich nicht starten: %s\n",
                       app.chosen, error->message);
            g_clear_error(&error);
        } else {
            status = 0;
        }
    }

    g_free(app.chosen);
    g_ptr_array_free(app.windows, TRUE);
    g_ptr_array_free(app.entries, TRUE);
    g_main_loop_unref(app.loop);
    return status;
}
