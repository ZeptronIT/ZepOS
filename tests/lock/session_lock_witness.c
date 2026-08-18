/* SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Der Zeuge: fragt den COMPOSITOR, ob die Sitzung gesperrt ist.
 *
 * WARUM ES DIESES PROGRAMM GIBT
 *     Weil "gesperrt" und "ein Fenster ist da" zwei verschiedene Dinge
 *     sind, und weil ein Test, der das erste behauptet und das zweite
 *     misst, genau den Fehler nicht faengt, der zaehlt: ein
 *     Sperrbildschirm, der ein Layer-Shell-Overlay ueber den Schreibtisch
 *     legt, sieht auf jedem Bild wie eine Sperre aus, gibt den
 *     Schreibtisch aber in dem Moment frei, in dem er abstuerzt.
 *
 *     zepos-lock koennte "zepos-lock: gesperrt" auch dann auf stdout
 *     schreiben, wenn es nichts gesperrt haette. Dieses Programm hier
 *     glaubt ihm nicht: es fragt den Compositor selbst.
 *
 * WIE ES FRAGT
 *     ext-session-lock-v1 vergibt die Sperre genau einmal. Ein zweiter
 *     Client, der `lock` verlangt, waehrend ein anderer sie haelt,
 *     bekommt `finished` - in gtk4-layer-shells Sprache das Signal
 *     ::failed. Der Header sagt es selbst: "The ::failed signal may be
 *     emitted ... later (if another process holds a lock)".
 *
 *     Also:
 *         Rueckgabe 0  die Sperre war ZU HABEN  -> Sitzung war FREI
 *         Rueckgabe 1  die Sperre wurde verweigert -> Sitzung GESPERRT
 *
 *     Im Fall 0 wird sofort wieder aufgeschlossen und auf den Compositor
 *     gewartet (gdk_display_sync), bevor der Prozess endet. Ohne das
 *     stuerbe dieser Zeuge als Halter einer Sperre - und liesse den
 *     verschachtelten Compositor nach dem Protokoll fuer immer zu.
 */
#include <gtk/gtk.h>
#include <gtk4-session-lock.h>
#include <stdlib.h>

#define WITNESS_FREE 0
#define WITNESS_LOCKED 1
#define WITNESS_UNKNOWN 3
#define WITNESS_TIMEOUT 4

static GMainLoop *loop;
static GtkSessionLockInstance *instance;
static int verdict = WITNESS_UNKNOWN;

static gboolean
stop(gpointer data)
{
    (void) data;
    g_main_loop_quit(loop);
    return G_SOURCE_REMOVE;
}

static void
on_locked(GtkSessionLockInstance *self, gpointer data)
{
    (void) self; (void) data;
    g_print("witness: frei\n");
    verdict = WITNESS_FREE;
    gtk_session_lock_instance_unlock(instance);
    /* Erst zurueckgeben, dann enden. Der Roundtrip in main() sorgt
     * dafuer, dass unlock_and_destroy angekommen ist. */
    g_idle_add(stop, NULL);
}

static void
on_failed(GtkSessionLockInstance *self, gpointer data)
{
    (void) self; (void) data;
    g_print("witness: gesperrt\n");
    verdict = WITNESS_LOCKED;
    g_idle_add(stop, NULL);
}

static gboolean
ask(gpointer data)
{
    (void) data;
    /* Aus der Hauptschleife heraus und nicht davor: lock() kann
     * ::locked noch waehrend des Aufrufs feuern, und ein
     * g_main_loop_quit() auf eine Schleife, die noch nicht laeuft,
     * verpufft - gemessen am 12.08.2026, der Zeuge lief danach in
     * seine Zeitgrenze. */
    gtk_session_lock_instance_lock(instance);
    return G_SOURCE_REMOVE;
}

static gboolean
bail(gpointer data)
{
    (void) data;
    g_print("witness: keine Antwort\n");
    verdict = WITNESS_TIMEOUT;
    g_main_loop_quit(loop);
    return G_SOURCE_REMOVE;
}

int
main(void)
{
    if (!gtk_init_check()) {
        g_printerr("witness: keine Anzeige\n");
        return WITNESS_UNKNOWN;
    }
    if (!gtk_session_lock_is_supported()) {
        g_printerr("witness: dieser Compositor spricht "
                   "ext-session-lock-v1 nicht\n");
        return WITNESS_UNKNOWN;
    }

    instance = gtk_session_lock_instance_new();
    g_signal_connect(instance, "locked", G_CALLBACK(on_locked), NULL);
    g_signal_connect(instance, "failed", G_CALLBACK(on_failed), NULL);

    loop = g_main_loop_new(NULL, FALSE);
    g_idle_add(ask, NULL);
    g_timeout_add(8000, bail, NULL);
    g_main_loop_run(loop);

    while (g_main_context_iteration(NULL, FALSE))
        ;
    gdk_display_sync(gdk_display_get_default());
    return verdict;
}
