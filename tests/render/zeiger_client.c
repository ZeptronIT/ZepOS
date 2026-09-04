// SPDX-License-Identifier: GPL-3.0-or-later
//
// Ein echter Zeiger fuer den verschachtelten Compositor.
//
// WARUM ES DAS GIBT
//     Seit dem 21.08.2026 haengt ein Fehler im Starter an einer Frage,
//     die dieser Messstand nicht beantworten konnte: erreicht ein Klick
//     den Knopf im Rechtsklickmenue? Vier Vermutungen sind daran
//     gemessen und verworfen worden - can_focus, der Tastenweg, der
//     Tastenmodus, der Griff -, und eine davon hat dem Nutzer den
//     Linksklick gekostet, bevor sie widerlegt war.
//
//     Der Grund fuer das Raten war immer derselbe: `waehle:` im
//     Sondenkind feuert `clicked` DIREKT am Knopf ab. Das misst die
//     Rueckrufe und nicht den Weg dorthin. Fuer einen echten Klick
//     braucht es ein Werkzeug, das im verschachtelten Compositor
//     Zeigerereignisse sendet; ydotool, wlrctl und dotool liegen auf
//     dieser Maschine nicht, und xdotool ist X11.
//
//     zwlr_virtual_pointer_v1 kann genau das, Hyprland kann es, und die
//     Protokollbeschreibung liegt im Quellbaum, den dieses Projekt
//     ohnehin baut (packaging/zepos-hyprland/hyprland-0.56.1.tar.gz).
//     Dasselbe Verfahren wie bei live_schirme_client.c und
//     wlr-output-management-unstable-v1.xml.
//
// AUFRUF
//     zeiger <breite> <hoehe> <x> <y> [links|rechts|mitte]
//
//     Breite und Hoehe sind der Bezugsrahmen fuer die absolute
//     Bewegung - das Protokoll nimmt x und y als Bruchteil davon, nicht
//     als Bildpunkte. Wer den Schirm einsetzt, bekommt Bildpunkte.
//
//     Ohne Taste wird nur bewegt. Mit Taste wird bewegt, gedrueckt und
//     losgelassen - drei Ereignisse, jedes mit seinem eigenen frame().
//
// WAS ES NICHT TUT
//     Es fasst nichts an ausser dem WAYLAND_DISPLAY, das in seiner
//     Umgebung steht. Ein Aufruf ohne verschachtelte Sitzung findet
//     keinen Compositor und endet mit 1 - er kann den Zeiger des
//     Menschen an dieser Maschine nicht bewegen, weil er dessen
//     Display gar nicht kennt.
#include <linux/input-event-codes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <wayland-client.h>

#include "wlr-virtual-pointer-unstable-v1-client-protocol.h"

static struct zwlr_virtual_pointer_manager_v1 *manager = NULL;
static struct wl_seat *seat = NULL;

static void handle_global(void *data, struct wl_registry *registry,
                          uint32_t name, const char *interface,
                          uint32_t version) {
    (void)data;
    (void)version;
    if (strcmp(interface, zwlr_virtual_pointer_manager_v1_interface.name) == 0) {
        manager = wl_registry_bind(
            registry, name, &zwlr_virtual_pointer_manager_v1_interface, 1);
    } else if (strcmp(interface, wl_seat_interface.name) == 0 && !seat) {
        seat = wl_registry_bind(registry, name, &wl_seat_interface, 1);
    }
}

static void handle_global_remove(void *data, struct wl_registry *registry,
                                 uint32_t name) {
    (void)data;
    (void)registry;
    (void)name;
}

static const struct wl_registry_listener registry_listener = {
    .global = handle_global,
    .global_remove = handle_global_remove,
};

// Die Zeit, die das Protokoll in jedem Ereignis will. Sie muss
// MONOTON steigen; der Compositor sortiert danach. Eine feste Zahl
// waere ein Zeiger, dessen zweiter Klick vor dem ersten liegt.
static uint32_t jetzt(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint32_t)(ts.tv_sec * 1000 + ts.tv_nsec / 1000000);
}

int main(int argc, char **argv) {
    if (argc < 5 || argc > 6) {
        fprintf(stderr,
                "Aufruf: %s <breite> <hoehe> <x> <y> [links|rechts|mitte]\n",
                argv[0]);
        return 2;
    }

    const uint32_t breite = (uint32_t)strtoul(argv[1], NULL, 10);
    const uint32_t hoehe = (uint32_t)strtoul(argv[2], NULL, 10);
    const uint32_t x = (uint32_t)strtoul(argv[3], NULL, 10);
    const uint32_t y = (uint32_t)strtoul(argv[4], NULL, 10);

    uint32_t taste = 0;
    if (argc == 6) {
        if (strcmp(argv[5], "links") == 0) {
            taste = BTN_LEFT;
        } else if (strcmp(argv[5], "rechts") == 0) {
            taste = BTN_RIGHT;
        } else if (strcmp(argv[5], "mitte") == 0) {
            taste = BTN_MIDDLE;
        } else {
            fprintf(stderr, "unbekannte Taste: %s\n", argv[5]);
            return 2;
        }
    }

    struct wl_display *display = wl_display_connect(NULL);
    if (!display) {
        fprintf(stderr, "kein Compositor an WAYLAND_DISPLAY\n");
        return 1;
    }

    struct wl_registry *registry = wl_display_get_registry(display);
    wl_registry_add_listener(registry, &registry_listener, NULL);
    wl_display_roundtrip(display);

    if (!manager) {
        fprintf(stderr,
                "der Compositor bietet zwlr_virtual_pointer_manager_v1 "
                "nicht an\n");
        wl_display_disconnect(display);
        return 1;
    }

    struct zwlr_virtual_pointer_v1 *zeiger =
        zwlr_virtual_pointer_manager_v1_create_virtual_pointer(manager, seat);
    if (!zeiger) {
        fprintf(stderr, "der Zeiger liess sich nicht anlegen\n");
        wl_display_disconnect(display);
        return 1;
    }

    // BEWEGEN, DANN frame(). Ohne den Rahmen ist die Bewegung fuer den
    // Compositor nicht abgeschlossen, und er reicht sie nicht weiter -
    // dasselbe wie bei wl_pointer.
    zwlr_virtual_pointer_v1_motion_absolute(zeiger, jetzt(), x, y,
                                            breite, hoehe);
    zwlr_virtual_pointer_v1_frame(zeiger);
    wl_display_roundtrip(display);

    if (taste) {
        zwlr_virtual_pointer_v1_button(zeiger, jetzt(), taste,
                                       WL_POINTER_BUTTON_STATE_PRESSED);
        zwlr_virtual_pointer_v1_frame(zeiger);
        wl_display_roundtrip(display);

        zwlr_virtual_pointer_v1_button(zeiger, jetzt(), taste,
                                       WL_POINTER_BUTTON_STATE_RELEASED);
        zwlr_virtual_pointer_v1_frame(zeiger);
        wl_display_roundtrip(display);
    }

    // ERST DER RUNDLAUF, DANN DAS ZERSTOEREN. Ein Zeiger, der zerstoert
    // wird, bevor der Compositor seine Ereignisse gelesen hat, nimmt sie
    // mit.
    zwlr_virtual_pointer_v1_destroy(zeiger);
    wl_display_roundtrip(display);
    wl_display_disconnect(display);
    return 0;
}
