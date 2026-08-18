/* SPDX-License-Identifier: GPL-3.0-or-later
 *
 * zepos-lock - der Sperrbildschirm, den SUPER+L oeffnet.
 *
 * WARUM ZepOS DIESES PROGRAMM SELBST SCHREIBT
 *     Der Nutzer hat am 11.08.2026 entschieden, dass die Oberflaeche
 *     durchgehend auf GTK4 steht, und am selben Tag zum Sperrbildschirm:
 *     "4 sollten wir selber machen also sperrbildschirm gtk4". Dort
 *     stand hyprlock, und es ist kein GTK-Programm - gemessen am
 *     12.08.2026 an der Installation dieser Maschine:
 *
 *         objdump -p /usr/bin/hyprlock | grep NEEDED
 *           NEEDED  libpam.so.0
 *           NEEDED  libEGL.so.1
 *           NEEDED  libGLESv2.so.2
 *           NEEDED  libcairo.so.2
 *           ... und keine Zeile mit gtk
 *
 *     Es zeichnet sich selbst mit GLES und Cairo. Das ist kein Mangel an
 *     hyprlock, sondern der Grund, aus dem seine Konfiguration keine
 *     einzige Farbe dieses Projekts tragen konnte:
 *     src/templates/hyprlock-config.template hatte zwoelf rgb()- und
 *     rgba()-Literale in Terminalgruen, auf einem #0c0c0c, das seit dem
 *     Umzug von kittys Chrom auf die Marke nirgends sonst mehr vorkam.
 *     Das Erste, was ein Nutzer nach jeder Pause sieht, war das Einzige,
 *     was nicht nach ZepOS aussah.
 *
 * DAS PROTOKOLL - DIE FRAGE, DIE VOR ALLEM ANDEREN STEHT
 *     Ein Fenster ganz oben ist KEIN Sperrbildschirm. Stirbt das
 *     Programm, ist der Schreibtisch offen; das ist der Unterschied
 *     zwischen zepos-logout, das ein Layer-Shell-Overlay ist und sein
 *     darf, und diesem hier.
 *
 *     Das Protokoll, das den Unterschied macht, heisst
 *     ext-session-lock-v1. Der Compositor garantiert damit, dass unter
 *     der Sperre nichts sichtbar wird, auch nicht beim Absturz des
 *     Sperrprogramms.
 *
 *     Die Vermutung beim Anfangen war, dass GTK4 das nicht hergibt und
 *     dieser Bildschirm deshalb ein anderes Toolkit oder rohes
 *     libwayland braeuchte. SIE WAR FALSCH, und zwar an der Bibliothek,
 *     die zepos-logout ohnehin schon benutzt: gtk4-layer-shell 1.3.0
 *     liefert neben gtk4-layer-shell.h auch gtk4-session-lock.h -
 *     GtkSessionLockInstance, gtk_session_lock_instance_lock() und
 *     gtk_session_lock_instance_assign_window_to_monitor(). Es ist
 *     dieselbe .so, dasselbe pkg-config-Modul, dieselbe Abhaengigkeit.
 *
 *     GEMESSEN am 12.08.2026 in einem verschachtelten Hyprland 0.55.4
 *     (die Fassung, auf die packaging/zepos-hyprland festgenagelt ist):
 *
 *         gtk_session_lock_is_supported()          1
 *         gtk_session_lock_instance_lock()         1
 *         Signal ::locked                          kam
 *         zweiter Client, der zu sperren versucht  ::failed
 *
 *     Die letzte Zeile ist der unabhaengige Zeuge und der Grund, aus dem
 *     die Tests dieses Programms nicht "ein Fenster ist da" messen:
 *     dass die Sitzung GESPERRT ist, sagt nicht dieses Programm, sondern
 *     der Compositor, indem er einem zweiten Sperr-Client absagt.
 *
 * WAS BEIM ABSTURZ PASSIERT
 *     Der Text des Protokolls, ext-session-lock-v1.xml Zeile 111:
 *     "If the client dies while the session is locked, the compositor
 *     must not unlock the session in response. It is acceptable for the
 *     session to be permanently locked if this happens."
 *
 *     GEMESSEN, statt geglaubt: im verschachtelten Hyprland gesperrt,
 *     das sperrende Programm mit SIGKILL erschlagen, danach der Zeuge
 *     von oben gefragt - er wird weiterhin abgewiesen. Die Sitzung
 *     bleibt also gesperrt. Hyprland 0.55.4 kennt zwar den Schalter
 *     misc:allow_session_lock_restore, mit dem ein neues Sperrprogramm
 *     eine verwaiste Sperre uebernehmen koennte; er stand im Versuch auf
 *     0 und liess sich weder aus der Konfigurationsdatei noch mit
 *     `hyprctl keyword` setzen (`getoption` antwortete danach
 *     unveraendert "int: 0 set: false"). Es gibt auf dieser Fassung
 *     also keine Uebernahme.
 *
 *     DARAUS FOLGT DIE BAUART DIESES PROGRAMMS, und sie ist der
 *     eigentliche Inhalt der Datei: alles, was fehlschlagen kann,
 *     passiert VOR dem Sperren. Das Stylesheet wird vorher gelesen, der
 *     Benutzername vorher aufgeloest, die Unterstuetzung des Protokolls
 *     vorher erfragt. Nach dem Sperren gibt es keinen Pfad mehr, der
 *     dieses Programm beendet, ausser einem Passwort, das PAM
 *     angenommen hat. Ein fehlendes Stylesheet ist deshalb eine
 *     haessliche Sperre und keine offene Sitzung, und ein kaputter
 *     PAM-Stapel ist eine Sperre, die niemanden hereinlaesst - nicht
 *     eine, die aufgeht.
 *
 * WARUM KEIN RUECKFALL AUF LAYER-SHELL
 *     Weil ein Rueckfall hier die Luecke IST. Ein Programm, das ohne das
 *     Protokoll ein Overlay zeigt, sieht in jedem Bild und in jedem Test
 *     aus wie ein Sperrbildschirm und ist keiner. Also endet dieses
 *     Programm mit einer Meldung, wenn der Compositor das Protokoll
 *     nicht spricht - ein Schreibtisch, der sichtbar nicht sperrt, ist
 *     besser als einer, der es zu tun scheint.
 *
 * WARUM KEIN GLAS
 *     Die Seitenleiste hat seit dem 11.08.2026 einen Glaseffekt
 *     (brand.GLASS_PANEL_ALPHA, die layerrules in
 *     hyprland-universal-config.template). Hier ist er zweimal falsch.
 *
 *     Erstens vom Zweck her: Glas laesst sehen, was dahinter ist, und
 *     dahinter ist der Schreibtisch des Nutzers - offene Dokumente,
 *     Postfaecher, Namen. Ein Sperrbildschirm hat den zu VERBERGEN.
 *     Hyprland hat fuer das Gegenteil sogar einen eigenen Schalter,
 *     misc:session_lock_xray, und der bleibt aus.
 *
 *     Zweitens technisch, und das ist der haerte Grund: `layerrule`
 *     spricht eine Flaeche ueber ihren Layer-Shell-Namensraum an. Eine
 *     ext_session_lock_surface_v1 IST keine Layer-Shell-Flaeche und hat
 *     keinen Namensraum - sie taucht in `hyprctl layers` nicht auf.
 *     Eine layerrule fuer diesen Bildschirm koennte gar nicht greifen.
 *     tests/lock/test_lock_screen.py misst beides: dass nichts unter
 *     diesem Namen in `hyprctl layers` steht, und dass die Sitzung
 *     trotzdem gesperrt ist.
 *
 * WARUM DIE PRUEFUNG IN EINEM EIGENEN FADEN LAEUFT
 *     pam_authenticate() blockiert. pam_unix ruft /usr/bin/unix_chkpwd
 *     als eigenen Prozess, und pam_faildelay laesst nach einem
 *     Fehlversuch absichtlich Sekunden vergehen. In der Hauptschleife
 *     hiesse das: der Sperrbildschirm zeichnet in dieser Zeit nicht,
 *     beantwortet keine Konfigurationsereignisse des Compositors und
 *     nimmt keine Taste an. Bei einem gewoehnlichen Fenster waere das
 *     ein Hakler; bei diesem ist es der Moment, in dem der Nutzer denkt,
 *     die Maschine haenge, und den Einschaltknopf sucht.
 */
/* explicit_bzero() ist eine Erweiterung von glibc und BSD, kein ISO C.
 * meson stellt hier `c11` ein; ohne diese Zeile ist die Funktion nicht
 * deklariert und der Bau faellt aus. Muss vor dem ersten Systemkopf
 * stehen. */
#define _DEFAULT_SOURCE

#include <gtk/gtk.h>
#include <gtk4-session-lock.h>

#include <pwd.h>
#include <string.h>
#include <strings.h>
#include <sys/types.h>
#include <unistd.h>

#include "zepos-lock-auth.h"

#define ZEPOS_LOCK_NAMESPACE "zepos-lock"

/* Die Rueckgabewerte, und was sie bedeuten.
 *
 * Sie sind Teil der Schnittstelle: `zepos-lock` steht in einer
 * Tastenbindung, und ein Programm, das mit 0 endet, ohne gesperrt zu
 * haben, ist eins, dem man das nicht ansieht. */
#define ZEP_EXIT_UNLOCKED 0  /* gesperrt gewesen, PAM hat aufgemacht */
#define ZEP_EXIT_NOT_LOCKED 1 /* nie gesperrt - der Schreibtisch ist offen */
#define ZEP_EXIT_LOST 2      /* gesperrt gewesen, aber nicht durch uns geoeffnet */

typedef struct {
    GtkWidget *window;
    GtkWidget *clock;
    GtkWidget *date;
    GtkWidget *entry;
    GtkWidget *message;
    GtkWidget *capslock;
} ZepScreen;

typedef struct {
    GtkSessionLockInstance *lock;
    GMainLoop *loop;
    GPtrArray *screens;      /* ZepScreen* */
    GtkEntryBuffer *typed;   /* EINE Eingabe fuer alle Schirme */
    char *user;
    char *realname;
    gboolean locked;         /* hat der Compositor je zugestimmt */
    gboolean checking;
    int status;
} ZepLock;

typedef struct {
    ZepLock *app;
    char *password;          /* gehoert dem Faden, wird dort geloescht */
    ZepAuthResult result;
} ZepAttempt;

/* ------------------------------------------------------------------
   Die Texte
   ------------------------------------------------------------------ */
/* Sie stehen hier und nicht in einer erzeugten Datei, und das ist bei
 * DIESEM Programm eine andere Entscheidung als bei zepos-logout.
 *
 * zepos-logout liest sein Layout aus layout.json, weil dort SECHS
 * Eintraege mit Symbolen, Beschriftungen, Aktionen und Tastenkuerzeln
 * stehen - Inhalt, der sich aendert. Hier gibt es vier Zeilen, von denen
 * drei Tatsachen der Maschine sind (Uhrzeit, Datum, Benutzer) und eine
 * ein Wort ist. Eine erzeugte Datei dafuer waere eine Datei, ohne die
 * SUPER+L nicht mehr sperrt - und genau das darf dieser Bildschirm nicht
 * haben. Er braucht ausser seinem Stylesheet nichts, und auch ohne das
 * sperrt er.
 *
 * Aus demselben Grund traegt er keine Glyphe aus src/icon_definition.py:
 * die kaemen ueber eine erzeugte Datei herein, und das waere derselbe
 * Handel - ein Symbol gegen eine Sperre, die ausfallen kann. */
#define ZEP_TEXT_PROMPT "Passwort"
#define ZEP_TEXT_CHECKING "Wird geprueft ..."
#define ZEP_TEXT_REFUSED "Passwort abgelehnt"
#define ZEP_TEXT_CAPSLOCK "Feststelltaste ist an"
#define ZEP_TEXT_DATE "%A, %d. %B %Y"
#define ZEP_TEXT_CLOCK "%H:%M"

/* ------------------------------------------------------------------
   Kleinkram
   ------------------------------------------------------------------ */

static void
zep_screen_free(gpointer data)
{
    g_free(data);
}

/* Der angemeldete Benutzer.
 *
 * getpwuid(getuid()) und nicht $USER: die Umgebungsvariable kann jeder
 * setzen, der dieses Programm startet, und ein Sperrbildschirm, der
 * gegen ein Konto prueft, das in einer Variablen steht, prueft gegen das
 * Konto, das der Angreifer hineingeschrieben hat. getuid() ist das, was
 * der Kern ueber diesen Prozess weiss. */
static void
zep_resolve_user(ZepLock *app)
{
    const struct passwd *entry = getpwuid(getuid());

    if (entry == NULL || entry->pw_name == NULL) {
        app->user = NULL;
        app->realname = NULL;
        return;
    }
    app->user = g_strdup(entry->pw_name);
    /* Das GECOS-Feld ist "Voller Name,Zimmer,Telefon,..." - nur der
     * erste Teil ist ein Name. Wo es leer ist, steht der Kontoname. */
    if (entry->pw_gecos != NULL && entry->pw_gecos[0] != '\0'
        && entry->pw_gecos[0] != ',') {
        char **parts = g_strsplit(entry->pw_gecos, ",", 2);
        app->realname = g_strdup(parts[0]);
        g_strfreev(parts);
    } else {
        app->realname = g_strdup(app->user);
    }
}

static void
zep_set_message(ZepLock *app, const char *text, gboolean failure)
{
    guint index;

    for (index = 0; index < app->screens->len; index++) {
        ZepScreen *screen = g_ptr_array_index(app->screens, index);
        gtk_label_set_text(GTK_LABEL(screen->message), text != NULL ? text : "");
        if (failure) {
            gtk_widget_add_css_class(screen->message, "failure");
            /* Auch am Feld, und nicht nur an der Zeile darunter: der
             * Blick liegt beim Tippen auf dem Feld. */
            gtk_widget_add_css_class(screen->entry, "failure");
        } else {
            gtk_widget_remove_css_class(screen->message, "failure");
            gtk_widget_remove_css_class(screen->entry, "failure");
        }
    }
}

static void
zep_set_busy(ZepLock *app, gboolean busy)
{
    guint index;

    for (index = 0; index < app->screens->len; index++) {
        ZepScreen *screen = g_ptr_array_index(app->screens, index);
        gtk_widget_set_sensitive(screen->entry, !busy);
        if (busy)
            gtk_widget_add_css_class(screen->entry, "checking");
        else
            gtk_widget_remove_css_class(screen->entry, "checking");
    }
    if (!busy && app->screens->len > 0) {
        ZepScreen *first = g_ptr_array_index(app->screens, 0);
        gtk_widget_grab_focus(first->entry);
    }
}

/* ------------------------------------------------------------------
   Uhr und Datum
   ------------------------------------------------------------------ */

static gboolean
zep_tick(gpointer data)
{
    ZepLock *app = data;
    g_autoptr(GDateTime) now = g_date_time_new_now_local();
    g_autofree char *clock = g_date_time_format(now, ZEP_TEXT_CLOCK);
    g_autofree char *date = g_date_time_format(now, ZEP_TEXT_DATE);
    guint index;

    for (index = 0; index < app->screens->len; index++) {
        ZepScreen *screen = g_ptr_array_index(app->screens, index);
        gtk_label_set_text(GTK_LABEL(screen->clock), clock != NULL ? clock : "");
        gtk_label_set_text(GTK_LABEL(screen->date), date != NULL ? date : "");
    }
    return G_SOURCE_CONTINUE;
}

/* ------------------------------------------------------------------
   Die Feststelltaste
   ------------------------------------------------------------------ */
/* Der haeufigste Grund, aus dem ein richtiges Passwort abgelehnt wird,
 * und der einzige, den das Programm selbst sehen kann. Ohne den Hinweis
 * probiert jemand dasselbe Passwort dreimal und laeuft damit in
 * pam_faillock. */
static void
zep_update_capslock(ZepLock *app)
{
    GdkDisplay *display = gdk_display_get_default();
    GdkSeat *seat = display != NULL ? gdk_display_get_default_seat(display) : NULL;
    GdkDevice *keyboard = seat != NULL ? gdk_seat_get_keyboard(seat) : NULL;
    gboolean on = keyboard != NULL && gdk_device_get_caps_lock_state(keyboard);
    guint index;

    for (index = 0; index < app->screens->len; index++) {
        ZepScreen *screen = g_ptr_array_index(app->screens, index);
        gtk_widget_set_visible(screen->capslock, on);
    }
}

static void
on_capslock_changed(GObject *device, GParamSpec *spec, gpointer data)
{
    (void) device; (void) spec;
    zep_update_capslock(data);
}

/* ------------------------------------------------------------------
   Die Pruefung
   ------------------------------------------------------------------ */

static gboolean
zep_attempt_finished(gpointer data)
{
    ZepAttempt *attempt = data;
    ZepLock *app = attempt->app;

    app->checking = FALSE;

    if (attempt->result.accepted) {
        /* Der einzige Weg aus diesem Programm heraus.
         *
         * DIE REIHENFOLGE IST GEMESSEN UND NICHT GESCHMACK: status VOR
         * unlock(). gtk_session_lock_instance_unlock() feuert ::unlocked
         * noch waehrend des Aufrufs, und on_unlocked() unten
         * unterscheidet "wir haben aufgeschlossen" von "der Compositor
         * hat aufgemacht" genau an diesem Feld. Andersherum - und so
         * stand es zuerst - meldete ein erfolgreicher Lauf im Versuch
         * vom 12.08.2026 "die Sperre wurde von aussen aufgehoben",
         * obwohl er selbst der Grund war.
         *
         * unlock() danach und quit() zuletzt: unlock_and_destroy muss
         * beim Compositor angekommen sein, bevor der Prozess endet -
         * sonst stirbt er als Halter einer Sperre, und das Protokoll
         * sagt dann ausdruecklich, dass die Sitzung gesperrt BLEIBT.
         * Der Nachlauf in main() spuelt die Anfrage. */
        app->status = ZEP_EXIT_UNLOCKED;
        gtk_session_lock_instance_unlock(app->lock);
        g_main_loop_quit(app->loop);
    } else {
        /* Was PAM gesagt hat, wenn es etwas gesagt hat - sonst das eine
         * Wort. Der Grund steht bei zep_conversation() in
         * zepos-lock-pam.c: die Ablehnung, die zaehlt, heisst nicht
         * "falsches Passwort", sondern "Konto fuer zehn Minuten
         * gesperrt". */
        zep_set_message(app,
                        attempt->result.reason != NULL
                            && attempt->result.reason[0] != '\0'
                        ? attempt->result.reason : ZEP_TEXT_REFUSED,
                        TRUE);
        zep_set_busy(app, FALSE);
        /* Eine Zeile je Ablehnung, mit dem PAM-Code und ohne alles
         * andere.
         *
         * SIE STEHT HIER, WEIL SONST NIEMAND DIE ABLEHNUNG MESSEN KANN.
         * Der Bildschirm ist gesperrt und bleibt gesperrt - von aussen
         * sieht ein abgewiesener Versuch genauso aus wie gar kein
         * Versuch. Ein Test, der bloss prueft, dass nach einem falschen
         * Passwort noch gesperrt ist, besteht auch dann, wenn die
         * Tasten nie angekommen sind; diese Zeile ist der Unterschied.
         *
         * Was NICHT dasteht, ist der Grund im Klartext: PAMs Meldungen
         * gehen an den Bildschirm, an dem der Mensch sitzt, und nicht
         * in ein Sitzungsprotokoll, das jeder spaeter liest. */
        g_printerr("zepos-lock: abgelehnt (PAM %d)\n", attempt->result.code);
    }

    zep_auth_result_clear(&attempt->result);
    g_free(attempt);
    return G_SOURCE_REMOVE;
}

static gpointer
zep_attempt_thread(gpointer data)
{
    ZepAttempt *attempt = data;

    zep_auth_check(attempt->app->user, attempt->password, &attempt->result);

    /* Die Kopie loeschen, nicht bloss freigeben. explicit_bzero wird -
     * anders als memset - vom Uebersetzer nicht wegoptimiert, wenn der
     * Puffer danach nur noch freigegeben wird. Was GTKs eigener
     * GtkEntryBuffer im Speicher zuruecklaesst, kann dieses Programm
     * nicht beeinflussen; das hier ist die Haelfte, die ihm gehoert. */
    if (attempt->password != NULL) {
        explicit_bzero(attempt->password, strlen(attempt->password));
        g_free(attempt->password);
        attempt->password = NULL;
    }

    g_idle_add(zep_attempt_finished, attempt);
    return NULL;
}

static void
zep_submit(ZepLock *app)
{
    ZepAttempt *attempt;
    GThread *thread;
    const char *typed;

    if (app->checking)
        return;

    /* Eine LEERE Eingabe wird abgeschickt wie jede andere, und das ist
     * eine geerbte Eigenschaft, keine Nachlaessigkeit.
     *
     * hyprlocks Vorlage hatte dafuer `ignore_empty_input = false` und
     * begruendete es selbst: ein leeres Enter loest pam_authenticate
     * aus, damit ein Hardware-Schluessel im Stapel (pam_u2f) seine
     * Aufforderung bekommt - die LED blinkt, man beruehrt den Schluessel,
     * die Sitzung geht auf, ohne dass ein Passwort getippt wurde. Wer
     * ein leeres Enter abfaengt, schaltet diesen Weg still ab.
     *
     * Der Preis ist ein PAM-Aufruf ohne Inhalt, wenn jemand versehentlich
     * Enter drueckt. Den zahlt pam_faildelay mit einer Sekunde, und das
     * Feld ist waehrenddessen sichtbar unempfindlich. */
    typed = gtk_entry_buffer_get_text(app->typed);
    attempt = g_new0(ZepAttempt, 1);
    attempt->app = app;
    attempt->password = g_strdup(typed != NULL ? typed : "");
    attempt->result.accepted = 0;

    /* Das Feld sofort leeren, nicht erst nach der Antwort: die Antwort
     * kann Sekunden dauern, und in dieser Zeit stuende das Passwort als
     * Punktereihe bekannter Laenge auf dem Bildschirm. */
    gtk_entry_buffer_delete_text(app->typed, 0, -1);

    app->checking = TRUE;
    zep_set_busy(app, TRUE);
    zep_set_message(app, ZEP_TEXT_CHECKING, FALSE);

    thread = g_thread_new("zepos-lock-pam", zep_attempt_thread, attempt);
    g_thread_unref(thread);
}

static void
on_entry_activate(GtkEntry *entry, gpointer data)
{
    (void) entry;
    zep_submit(data);
}

static gboolean
on_key_pressed(GtkEventControllerKey *controller, guint keyval,
               guint keycode, GdkModifierType state, gpointer data)
{
    ZepLock *app = data;

    (void) controller; (void) keycode; (void) state;

    /* Escape leert die Eingabe und beendet NICHTS.
     *
     * Das ist der Unterschied zu zepos-logout, wo Escape die Maske
     * schliesst. Hier gibt es keinen Weg heraus ausser dem Passwort;
     * eine Taste, die den Sperrbildschirm schliesst, waere kein
     * Sperrbildschirm. */
    if (keyval == GDK_KEY_Escape) {
        gtk_entry_buffer_delete_text(app->typed, 0, -1);
        zep_set_message(app, ZEP_TEXT_PROMPT, FALSE);
        return TRUE;
    }
    return FALSE;
}

/* ------------------------------------------------------------------
   Ein Fenster je Monitor
   ------------------------------------------------------------------ */

/* Der erste Buchstabe des Namens, gross - das Benutzerbild.
 *
 * WARUM EIN BUCHSTABE UND KEIN BILD
 *     Weil ein Bild eine Datei ist, die fehlen, kaputt sein oder erst
 *     nach dem Sperren geladen werden kann. Genau das ist die eine
 *     Stelle, an der die Bauart dieses Programms ohnehin schon nicht
 *     ganz haelt (siehe den Kopf: das Hintergrundbild laedt GTK erst
 *     beim Zeichnen), und sie ein zweites Mal aufzumachen - fuer ein
 *     Bildchen - waere der schlechteste Handel im ganzen Entwurf.
 *
 *     /var/lib/AccountsService/icons/$USER und ~/.face waeren die
 *     ueblichen Quellen. Beide sind auf einer frischen Installation
 *     leer, also waere der haeufigste Fall ohnehin der Rueckfall - und
 *     der Rueckfall ist das hier.
 */
static char *
zep_initial(const char *name)
{
    gunichar first;

    if (name == NULL || name[0] == '\0')
        return g_strdup("?");
    first = g_unichar_toupper(g_utf8_get_char(name));
    return g_ucs4_to_utf8(&first, 1, NULL, NULL, NULL);
}

/* Die Uhr, oben. Nicht in der Mitte bei allem anderen.
 *
 * Das ist die Anordnung, die der Nutzer am 12.08.2026 gemeint hat
 * ("vgl. apple os login"): die Zeit steht oben am Rand und gehoert dem
 * Bildschirm, die Anmeldung steht in der Mitte und gehoert dem
 * Menschen. In einer gemeinsamen Kachel stuenden beide gleich laut, und
 * die Kachel selbst waere das, was man zuerst sieht - ein Formular.
 */
static GtkWidget *
zep_build_clock(ZepScreen *screen)
{
    GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);

    gtk_widget_set_halign(box, GTK_ALIGN_CENTER);
    gtk_widget_set_valign(box, GTK_ALIGN_START);

    screen->clock = gtk_label_new("");
    gtk_widget_set_name(screen->clock, "clock");
    gtk_box_append(GTK_BOX(box), screen->clock);

    screen->date = gtk_label_new("");
    gtk_widget_set_name(screen->date, "date");
    gtk_box_append(GTK_BOX(box), screen->date);

    return box;
}

static GtkWidget *
zep_build_card(ZepLock *app, ZepScreen *screen)
{
    GtkWidget *card = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
    GtkWidget *avatar;
    GtkWidget *user;
    g_autofree char *initial = zep_initial(app->realname);

    /* Kein Name und kein Rahmen mehr an dieser Spalte.
     *
     * Hier stand bis zum 12.08.2026 eine Kachel: brand.INK mit einem
     * 1px-Rand aus brand.SHADE_1, uebernommen aus der Anmeldemaske. Auf
     * einem Sperrbildschirm ist das falsch herum - die Kachel ist dann
     * das Auffaelligste im Bild, und was zaehlt (wer ist das, wo tippe
     * ich hin) steht darin. Ohne sie traegt der Hintergrund, und die
     * senkrechte Achse ordnet. */
    gtk_widget_set_halign(card, GTK_ALIGN_CENTER);
    gtk_widget_set_valign(card, GTK_ALIGN_CENTER);

    avatar = gtk_label_new(initial);
    gtk_widget_set_name(avatar, "avatar");
    gtk_widget_set_halign(avatar, GTK_ALIGN_CENTER);
    gtk_box_append(GTK_BOX(card), avatar);

    user = gtk_label_new(app->realname != NULL ? app->realname : "");
    gtk_widget_set_name(user, "user");
    gtk_box_append(GTK_BOX(card), user);

    /* Ein GtkEntry mit abgeschaltetem Echo und nicht GtkPasswordEntry.
     *
     * GEMESSEN AN DEM, WAS DER MEHRSCHIRMBETRIEB VERLANGT
     *     Auf drei Monitoren stehen drei Fenster, und der Compositor
     *     gibt die Tastatur einem davon - dem, auf dem der Zeiger
     *     zuletzt war. Wer auf den falschen Schirm sieht, tippt in ein
     *     Feld, das leer bleibt, und haelt die Maschine fuer haengend.
     *     Ein gemeinsamer GtkEntryBuffer loest das an der Wurzel: es
     *     gibt EINE Eingabe, und alle drei Felder zeigen sie.
     *
     *     GtkPasswordEntry kann das nicht - es nimmt keinen fremden
     *     Puffer entgegen. Was es sonst noch mitbringt, ist eine
     *     Warnung vor der Feststelltaste (die hier eine Zeile weiter
     *     unten selbst steht, weil sie auf allen Schirmen gleichzeitig
     *     erscheinen soll) und ein Auge zum Sichtbarmachen des
     *     Passworts - auf einem Sperrbildschirm die einzige
     *     Schaltflaeche, die man dort nicht haben will. */
    screen->entry = gtk_entry_new_with_buffer(app->typed);
    gtk_widget_set_name(screen->entry, "password");
    gtk_entry_set_visibility(GTK_ENTRY(screen->entry), FALSE);
    gtk_entry_set_invisible_char(GTK_ENTRY(screen->entry), 0x2022);
    gtk_entry_set_placeholder_text(GTK_ENTRY(screen->entry), ZEP_TEXT_PROMPT);
    gtk_entry_set_input_purpose(GTK_ENTRY(screen->entry),
                                GTK_INPUT_PURPOSE_PASSWORD);
    gtk_entry_set_activates_default(GTK_ENTRY(screen->entry), FALSE);
    /* Die Breite in ZEICHEN und nicht in Pixeln.
     *
     * Damit folgt sie der Schriftgroesse, die ihrerseits dem Faktor aus
     * src/sizes.py folgt - ein Feld mit fester Pixelbreite waere auf
     * einem 3440er Schirm bei Faktor 1.85 ein Schlitz. Und es kommt
     * ohne einen neuen Eintrag in sizes.TABLE aus, den sonst eine
     * Vorlage nennen muesste. */
    gtk_editable_set_width_chars(GTK_EDITABLE(screen->entry), 18);
    gtk_widget_set_halign(screen->entry, GTK_ALIGN_CENTER);
    /* Der Text mittig IM Feld, nicht nur das Feld mittig auf dem Schirm.
     *
     * Gesehen an der ersten Aufnahme des neuen Entwurfs
     * (12.08.2026): Uhr, Datum, Kreis und Name standen auf der
     * senkrechten Achse, und die Schreibmarke sass links unten in der
     * Pille - der einzige Punkt im Bild, der aus der Reihe fiel, und
     * ausgerechnet der, auf den man sieht. */
    gtk_entry_set_alignment(GTK_ENTRY(screen->entry), 0.5);
    g_signal_connect(screen->entry, "activate",
                     G_CALLBACK(on_entry_activate), app);
    gtk_box_append(GTK_BOX(card), screen->entry);

    screen->capslock = gtk_label_new(ZEP_TEXT_CAPSLOCK);
    gtk_widget_set_name(screen->capslock, "capslock");
    gtk_widget_set_visible(screen->capslock, FALSE);
    gtk_box_append(GTK_BOX(card), screen->capslock);

    screen->message = gtk_label_new("");
    gtk_widget_set_name(screen->message, "message");
    gtk_box_append(GTK_BOX(card), screen->message);

    return card;
}

static void
on_monitor(GtkSessionLockInstance *instance, GdkMonitor *monitor,
           gpointer data)
{
    ZepLock *app = data;
    ZepScreen *screen = g_new0(ZepScreen, 1);
    GtkEventController *keys;
    GtkWidget *layout;

    screen->window = gtk_window_new();
    gtk_widget_set_name(screen->window, "lock");

    /* GtkCenterBox und nicht eine Box mit Fuellstuecken: das mittlere
     * Kind steht damit in der Mitte des BILDSCHIRMS und nicht in der
     * Mitte dessen, was die Uhr uebriglaesst. Ohne `end` waere die
     * Anmeldung um die halbe Uhrhoehe nach unten verschoben, und auf
     * einem 16:9-Schirm sieht man das. */
    layout = gtk_center_box_new();
    gtk_orientable_set_orientation(GTK_ORIENTABLE(layout),
                                   GTK_ORIENTATION_VERTICAL);
    gtk_center_box_set_start_widget(GTK_CENTER_BOX(layout),
                                    zep_build_clock(screen));
    gtk_center_box_set_center_widget(GTK_CENTER_BOX(layout),
                                     zep_build_card(app, screen));
    gtk_window_set_child(GTK_WINDOW(screen->window), layout);

    /* Der Zeiger verschwindet, wie er es unter hyprlock tat
     * (`hide_cursor = true`). Auf dieser Flaeche gibt es nichts
     * anzuklicken ausser dem einen Feld, das ohnehin den Fokus hat. */
    gtk_widget_set_cursor_from_name(screen->window, "none");

    keys = gtk_event_controller_key_new();
    g_signal_connect(keys, "key-pressed", G_CALLBACK(on_key_pressed), app);
    gtk_widget_add_controller(screen->window, keys);

    g_ptr_array_add(app->screens, screen);

    /* Unrealisiert uebergeben, so verlangt es die Bibliothek: sie setzt
     * dem Fenster die Rolle ext_session_lock_surface_v1 auf, und eine
     * Wayland-Flaeche kann nur EINE Rolle haben. Ein vorher
     * praesentiertes Fenster haette schon die xdg_toplevel-Rolle. */
    gtk_session_lock_instance_assign_window_to_monitor(
        instance, GTK_WINDOW(screen->window), monitor);
    gtk_window_present(GTK_WINDOW(screen->window));

    zep_tick(app);
    zep_update_capslock(app);
    gtk_widget_grab_focus(screen->entry);
}

/* ------------------------------------------------------------------
   Die drei Signale der Sperre
   ------------------------------------------------------------------ */

static void
on_locked(GtkSessionLockInstance *instance, gpointer data)
{
    ZepLock *app = data;

    (void) instance;
    app->locked = TRUE;
    /* Auf stdout, damit ein Test es lesen kann, ohne dem Programm
     * glauben zu muessen: der Zeuge in tests/lock/ fragt zusaetzlich den
     * Compositor. Diese Zeile ist die Behauptung, jene die Messung. */
    g_print("zepos-lock: gesperrt\n");
}

static void
on_failed(GtkSessionLockInstance *instance, gpointer data)
{
    ZepLock *app = data;

    (void) instance;
    /* Zwei Faelle, und beide enden hier: der Compositor spricht das
     * Protokoll nicht (dann waere schon zep_refuse() unten gelaufen),
     * oder ein anderes Programm haelt die Sperre bereits. Das zweite
     * ist der Normalfall beim zweiten Druck auf SUPER+L, und es ist
     * kein Fehler des Nutzers - also eine Zeile und Ende, kein
     * Fenster. */
    g_printerr("zepos-lock: der Compositor hat die Sperre nicht gegeben.\n"
               "  Haelt schon ein anderes Programm sie? Dann ist bereits "
               "gesperrt.\n");
    app->status = app->locked ? ZEP_EXIT_LOST : ZEP_EXIT_NOT_LOCKED;
    g_main_loop_quit(app->loop);
}

static void
on_unlocked(GtkSessionLockInstance *instance, gpointer data)
{
    ZepLock *app = data;

    (void) instance;
    /* Kommt auch bei unserem eigenen unlock() - dann ist status schon
     * gesetzt und die Schleife schon beendet. Interessant ist der andere
     * Fall: der Compositor hat aufgemacht, ohne dass PAM gefragt wurde.
     * Das darf nicht als "wir haben aufgeschlossen" durchgehen. */
    if (app->status != ZEP_EXIT_UNLOCKED) {
        g_printerr("zepos-lock: die Sperre wurde von aussen aufgehoben.\n");
        app->status = ZEP_EXIT_LOST;
        g_main_loop_quit(app->loop);
    }
}

/* ------------------------------------------------------------------
   Das Stylesheet
   ------------------------------------------------------------------ */

static char *
zep_config_path(const char *basename)
{
    return g_build_filename(g_get_user_config_dir(), ZEPOS_LOCK_NAMESPACE,
                            basename, NULL);
}

static gboolean
zep_load_css(const char *path, GError **error)
{
    g_autoptr(GFile) file = NULL;
    GtkCssProvider *provider;

    if (!g_file_test(path, G_FILE_TEST_EXISTS)) {
        g_set_error(error, G_FILE_ERROR, G_FILE_ERROR_NOENT, "%s fehlt", path);
        return FALSE;
    }
    file = g_file_new_for_path(path);
    provider = gtk_css_provider_new();
    gtk_css_provider_load_from_file(provider, file);
    gtk_style_context_add_provider_for_display(
        gdk_display_get_default(), GTK_STYLE_PROVIDER(provider),
        GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
    g_object_unref(provider);
    return TRUE;
}

/* ------------------------------------------------------------------
   main
   ------------------------------------------------------------------ */

int
main(int argc, char **argv)
{
    g_autofree char *css_path = NULL;
    gboolean show_version = FALSE;
    g_autoptr(GOptionContext) context = NULL;
    g_autoptr(GError) error = NULL;
    GdkDisplay *display;
    GdkSeat *seat;
    GdkDevice *keyboard;
    ZepLock app;
    guint ticker;

    const GOptionEntry options[] = {
        { "css", 'C', 0, G_OPTION_ARG_FILENAME, &css_path,
          "Stildatei statt der erzeugten", "PFAD" },
        { "version", 'v', 0, G_OPTION_ARG_NONE, &show_version,
          "Version ausgeben und enden", NULL },
        { NULL, 0, 0, 0, NULL, NULL, NULL },
    };

    context = g_option_context_new("- der Sperrbildschirm von ZepOS");
    g_option_context_add_main_entries(context, options, NULL);
    if (!g_option_context_parse(context, &argc, &argv, &error)) {
        g_printerr("zepos-lock: %s\n", error->message);
        return ZEP_EXIT_NOT_LOCKED;
    }
    if (show_version) {
        g_print("zepos-lock %s\n", ZEPOS_LOCK_VERSION);
        return 0;
    }

    /* gtk_init_check statt gtk_init: das zweite bricht mit einer
     * GTK-Warnung ab, wenn keine Anzeige da ist, und dieses Programm
     * soll in diesem Fall sagen, dass es NICHT gesperrt hat. */
    if (!gtk_init_check()) {
        g_printerr("zepos-lock: keine Anzeige - es ist NICHT gesperrt.\n");
        return ZEP_EXIT_NOT_LOCKED;
    }

    /* DIE ERSTE FRAGE, UND SIE WIRD VOR ALLEM ANDEREN GESTELLT.
     *
     * Ohne ext-session-lock-v1 gibt es keinen Sperrbildschirm, den
     * dieses Programm bauen koennte - nur ein Fenster, das so aussieht.
     * Der Kopf dieser Datei sagt, warum es das nicht wird. */
    if (!gtk_session_lock_is_supported()) {
        g_printerr(
            "zepos-lock: dieser Compositor spricht ext-session-lock-v1 "
            "nicht.\n"
            "  Es ist NICHT gesperrt. Ein Fenster ueber allem waere kein\n"
            "  Sperrbildschirm - es verschwaende mit diesem Programm.\n");
        return ZEP_EXIT_NOT_LOCKED;
    }

    app.lock = NULL;
    app.loop = g_main_loop_new(NULL, FALSE);
    app.screens = g_ptr_array_new_with_free_func(zep_screen_free);
    app.typed = gtk_entry_buffer_new(NULL, 0);
    app.user = NULL;
    app.realname = NULL;
    app.locked = FALSE;
    app.checking = FALSE;
    app.status = ZEP_EXIT_NOT_LOCKED;

    zep_resolve_user(&app);
    if (app.user == NULL) {
        g_printerr("zepos-lock: zu dieser UID gehoert kein Konto in der "
                   "Passwortdatenbank.\n"
                   "  Es gibt niemanden, gegen den zu pruefen waere; es ist "
                   "NICHT gesperrt.\n");
        return ZEP_EXIT_NOT_LOCKED;
    }

    /* Vor dem Sperren, und der Fehlschlag ist keiner.
     *
     * Die Reihenfolge ist der ganze Punkt: waere das Stylesheet nach dem
     * Sperren geladen, koennte ein Parse-Fehler ein Programm umbringen,
     * das die Sperre schon haelt - und die Sitzung bliebe fuer immer
     * geschlossen. Vorher gelesen ist ein fehlendes Stylesheet eine
     * haessliche Sperre, und das ist der bessere von zwei Zustaenden. */
    if (css_path == NULL)
        css_path = zep_config_path("style.css");
    if (!zep_load_css(css_path, &error)) {
        g_printerr("zepos-lock: %s - der Bildschirm sperrt ungestylt.\n"
                   "  ./generate_config.sh -lock-style schreibt die Datei.\n",
                   error->message);
        g_clear_error(&error);
    }

    display = gdk_display_get_default();
    seat = display != NULL ? gdk_display_get_default_seat(display) : NULL;
    keyboard = seat != NULL ? gdk_seat_get_keyboard(seat) : NULL;
    if (keyboard != NULL)
        g_signal_connect(keyboard, "notify::caps-lock-state",
                         G_CALLBACK(on_capslock_changed), &app);

    app.lock = gtk_session_lock_instance_new();
    g_signal_connect(app.lock, "locked", G_CALLBACK(on_locked), &app);
    g_signal_connect(app.lock, "failed", G_CALLBACK(on_failed), &app);
    g_signal_connect(app.lock, "unlocked", G_CALLBACK(on_unlocked), &app);
    g_signal_connect(app.lock, "monitor", G_CALLBACK(on_monitor), &app);

    if (!gtk_session_lock_instance_lock(app.lock)) {
        g_printerr("zepos-lock: die Sperre wurde sofort verweigert - es ist "
                   "NICHT gesperrt.\n");
        return ZEP_EXIT_NOT_LOCKED;
    }

    ticker = g_timeout_add_seconds(1, zep_tick, &app);
    g_main_loop_run(app.loop);
    g_source_remove(ticker);

    /* Einmal leerlaufen lassen, damit unlock_and_destroy den Compositor
     * erreicht, bevor dieser Prozess endet. Ohne das kann er als Halter
     * einer Sperre sterben, und dann bleibt die Sitzung nach dem
     * Protokoll geschlossen - mit dem richtigen Passwort. */
    while (g_main_context_iteration(NULL, FALSE))
        ;
    if (display != NULL)
        gdk_display_sync(display);

    if (app.status == ZEP_EXIT_UNLOCKED)
        g_print("zepos-lock: entsperrt\n");

    g_free(app.user);
    g_free(app.realname);
    g_ptr_array_free(app.screens, TRUE);
    g_object_unref(app.typed);
    g_main_loop_unref(app.loop);
    return app.status;
}
