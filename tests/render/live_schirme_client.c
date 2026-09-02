// SPDX-License-Identifier: GPL-3.0-or-later
//
// Der kleinste wlr-output-management-Client, der die Frage beantwortet,
// die tests/render/test_live_spiegel.py stellt.
//
// WOZU ER DA IST
//     Im Betrieb ruft /usr/local/bin/zepos-live-schirme das Programm
//     wlr-randr. Auf der Werkstattmaschine lag es am 01.09.2026 nicht,
//     also uebersprang der Test, der beweisen soll, dass das Ueberlagern
//     zweier Ausgaenge wirklich dasselbe Bild ergibt - die tragende
//     Behauptung des ganzen Fixes.
//
//     Dieses Programm tritt an wlr-randrs Stelle. Der Test legt es unter
//     dem Namen `wlr-randr` in ein eigenes Verzeichnis und haengt NUR
//     dieses vor den Suchpfad des Kindes; das AUSGELIEFERTE Skript laeuft
//     dabei unveraendert.
//
// WAS ER KANN, UND WARUM NICHT MEHR
//     Genau das, was das Skript braucht, und ein Stueck fuer den Test:
//
//         (ohne Argumente)          Ausgaenge auflisten
//         --output NAME --pos X,Y   einen Ausgang an eine Stelle legen
//         --output NAME --custom-mode BxH   seine Groesse setzen
//
//     Das dritte benutzt das Skript NIE. Es steht hier, weil sich ohne
//     es keine ungleich grossen Schirme nachstellen lassen: das
//     headless-Backend von wlroots legt jeden Ausgang mit 1280x720 an,
//     und ohne eine Moeglichkeit, das zu aendern, bliebe die Frage
//     "was passiert bei ungleichen Aufloesungen" ungemessen. Sie ist
//     gemessen; das Ergebnis steht in test_live_spiegel.py.
//
//     Alles andere, was wlr-randr kann - Modi aus der Liste waehlen,
//     Drehung, Skalierung, Ein und Aus - fehlt absichtlich. Ein
//     Testwerkzeug, das mehr kann als die Frage verlangt, ist eine
//     zweite Sache, die kaputtgehen kann.
//
// WAS EIN BESTANDENER LAUF BEDEUTET
//     Dass ein echter Compositor wirklich umgestellt hat. Eine falsche
//     Protokollbeschreibung - siehe den Kopf von
//     wlr-output-management-unstable-v1.xml - ergaebe einen
//     Protokollfehler oder eine abgelehnte Konfiguration, und dann
//     bliebe der zweite Ausgang leer und der Test fiele. Falsch gruen
//     kann dieser Weg nicht werden.
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wayland-client.h>
#include "wlr-output-management-unstable-v1-client-protocol.h"

#define MAX_HEADS 16
#define MAX_MODES 32

struct mode_info {
    struct zwlr_output_mode_v1 *proxy;
    int32_t w, h, refresh;
    int preferred;
};

struct head_info {
    struct zwlr_output_head_v1 *proxy;
    char name[128];
    char description[256];
    int enabled;
    int32_t x, y;
    int32_t phys_w, phys_h;
    int32_t transform;
    wl_fixed_t scale;
    struct mode_info modes[MAX_MODES];
    int n_modes;
    struct zwlr_output_mode_v1 *current;
    // Was auf der Befehlszeile fuer diesen Ausgang verlangt wurde.
    int want_pos;
    int32_t want_x, want_y;
    int want_custom;
    int32_t custom_w, custom_h;
};

static struct head_info heads[MAX_HEADS];
static int n_heads = 0;
static struct zwlr_output_manager_v1 *manager = NULL;
static uint32_t manager_serial = 0;
static int have_serial = 0;
static int apply_result = -1;   // 0 = angenommen, sonst abgelehnt

// ---- mode ----------------------------------------------------------
static void mode_size(void *data, struct zwlr_output_mode_v1 *m,
                      int32_t w, int32_t h) {
    struct mode_info *mi = data; (void)m; mi->w = w; mi->h = h;
}
static void mode_refresh(void *data, struct zwlr_output_mode_v1 *m, int32_t r) {
    struct mode_info *mi = data; (void)m; mi->refresh = r;
}
static void mode_preferred(void *data, struct zwlr_output_mode_v1 *m) {
    struct mode_info *mi = data; (void)m; mi->preferred = 1;
}
static void mode_finished(void *data, struct zwlr_output_mode_v1 *m) {
    (void)data; (void)m;
}
static const struct zwlr_output_mode_v1_listener mode_listener = {
    .size = mode_size, .refresh = mode_refresh,
    .preferred = mode_preferred, .finished = mode_finished,
};

// ---- head ----------------------------------------------------------
static void head_name(void *data, struct zwlr_output_head_v1 *h, const char *s) {
    struct head_info *hi = data; (void)h;
    snprintf(hi->name, sizeof hi->name, "%s", s);
}
static void head_description(void *data, struct zwlr_output_head_v1 *h,
                             const char *s) {
    struct head_info *hi = data; (void)h;
    snprintf(hi->description, sizeof hi->description, "%s", s);
}
static void head_physical_size(void *data, struct zwlr_output_head_v1 *h,
                               int32_t w, int32_t hh) {
    struct head_info *hi = data; (void)h; hi->phys_w = w; hi->phys_h = hh;
}
static void head_mode(void *data, struct zwlr_output_head_v1 *h,
                      struct zwlr_output_mode_v1 *m) {
    struct head_info *hi = data; (void)h;
    if (hi->n_modes >= MAX_MODES) return;
    struct mode_info *mi = &hi->modes[hi->n_modes++];
    memset(mi, 0, sizeof *mi);
    mi->proxy = m;
    zwlr_output_mode_v1_add_listener(m, &mode_listener, mi);
}
static void head_enabled(void *data, struct zwlr_output_head_v1 *h, int32_t e) {
    struct head_info *hi = data; (void)h; hi->enabled = e;
}
static void head_current_mode(void *data, struct zwlr_output_head_v1 *h,
                              struct zwlr_output_mode_v1 *m) {
    struct head_info *hi = data; (void)h; hi->current = m;
}
static void head_position(void *data, struct zwlr_output_head_v1 *h,
                          int32_t x, int32_t y) {
    struct head_info *hi = data; (void)h; hi->x = x; hi->y = y;
}
static void head_transform(void *data, struct zwlr_output_head_v1 *h, int32_t t) {
    struct head_info *hi = data; (void)h; hi->transform = t;
}
static void head_scale(void *data, struct zwlr_output_head_v1 *h, wl_fixed_t s) {
    struct head_info *hi = data; (void)h; hi->scale = s;
}
static void head_finished(void *data, struct zwlr_output_head_v1 *h) {
    (void)data; (void)h;
}
static void head_make(void *data, struct zwlr_output_head_v1 *h, const char *s) {
    (void)data; (void)h; (void)s;
}
static void head_model(void *data, struct zwlr_output_head_v1 *h, const char *s) {
    (void)data; (void)h; (void)s;
}
static void head_serial_number(void *data, struct zwlr_output_head_v1 *h,
                               const char *s) {
    (void)data; (void)h; (void)s;
}
static void head_adaptive_sync(void *data, struct zwlr_output_head_v1 *h,
                               uint32_t s) {
    (void)data; (void)h; (void)s;
}
static const struct zwlr_output_head_v1_listener head_listener = {
    .name = head_name, .description = head_description,
    .physical_size = head_physical_size, .mode = head_mode,
    .enabled = head_enabled, .current_mode = head_current_mode,
    .position = head_position, .transform = head_transform,
    .scale = head_scale, .finished = head_finished,
    .make = head_make, .model = head_model,
    .serial_number = head_serial_number, .adaptive_sync = head_adaptive_sync,
};

// ---- manager -------------------------------------------------------
static void manager_head(void *data, struct zwlr_output_manager_v1 *m,
                         struct zwlr_output_head_v1 *h) {
    (void)data; (void)m;
    if (n_heads >= MAX_HEADS) return;
    struct head_info *hi = &heads[n_heads++];
    memset(hi, 0, sizeof *hi);
    hi->proxy = h;
    hi->scale = wl_fixed_from_double(1.0);
    zwlr_output_head_v1_add_listener(h, &head_listener, hi);
}
static void manager_done(void *data, struct zwlr_output_manager_v1 *m,
                         uint32_t serial) {
    (void)data; (void)m;
    manager_serial = serial;
    have_serial = 1;
}
static void manager_finished(void *data, struct zwlr_output_manager_v1 *m) {
    (void)data; (void)m;
}
static const struct zwlr_output_manager_v1_listener manager_listener = {
    .head = manager_head, .done = manager_done, .finished = manager_finished,
};

// ---- configuration -------------------------------------------------
static void conf_succeeded(void *data, struct zwlr_output_configuration_v1 *c) {
    (void)data; (void)c; apply_result = 0;
}
static void conf_failed(void *data, struct zwlr_output_configuration_v1 *c) {
    (void)data; (void)c; apply_result = 1;
}
static void conf_cancelled(void *data, struct zwlr_output_configuration_v1 *c) {
    (void)data; (void)c; apply_result = 2;
}
static const struct zwlr_output_configuration_v1_listener conf_listener = {
    .succeeded = conf_succeeded, .failed = conf_failed,
    .cancelled = conf_cancelled,
};

// ---- registry ------------------------------------------------------
static void reg_global(void *data, struct wl_registry *r, uint32_t name,
                       const char *iface, uint32_t version) {
    (void)data;
    if (strcmp(iface, zwlr_output_manager_v1_interface.name) == 0) {
        uint32_t v = version < 4 ? version : 4;
        manager = wl_registry_bind(r, name,
                                   &zwlr_output_manager_v1_interface, v);
        zwlr_output_manager_v1_add_listener(manager, &manager_listener, NULL);
    }
}
static void reg_global_remove(void *data, struct wl_registry *r, uint32_t name) {
    (void)data; (void)r; (void)name;
}
static const struct wl_registry_listener reg_listener = {
    .global = reg_global, .global_remove = reg_global_remove,
};

static const char *transform_name(int32_t t) {
    switch (t) {
    case 1: return "90";
    case 2: return "180";
    case 3: return "270";
    case 4: return "flipped";
    case 5: return "flipped-90";
    case 6: return "flipped-180";
    case 7: return "flipped-270";
    default: return "normal";
    }
}

int main(int argc, char **argv) {
    struct wl_display *display = wl_display_connect(NULL);
    if (!display) {
        fprintf(stderr, "live-schirme-client: kein Wayland-Display\n");
        return 1;
    }
    struct wl_registry *registry = wl_display_get_registry(display);
    wl_registry_add_listener(registry, &reg_listener, NULL);
    wl_display_roundtrip(display);
    if (!manager) {
        fprintf(stderr, "live-schirme-client: der Compositor bietet kein "
                        "zwlr_output_manager_v1\n");
        return 1;
    }
    // Die Ausgangsliste kommt in Stufen - erst die Koepfe, dann ihre Modi,
    // dann `done` mit der Seriennummer, ohne die keine Konfiguration
    // angenommen wird.
    for (int i = 0; i < 6 && !have_serial; i++)
        wl_display_roundtrip(display);
    wl_display_roundtrip(display);
    if (!have_serial) {
        fprintf(stderr, "live-schirme-client: keine Ausgangsliste\n");
        return 1;
    }

    // Ohne Argumente: auflisten, in der Form, die wlr-randr schreibt.
    if (argc == 1) {
        for (int i = 0; i < n_heads; i++) {
            struct head_info *h = &heads[i];
            printf("%s \"%s\"\n", h->name, h->description);
            printf("  Make: Unknown\n");
            printf("  Model: Unknown\n");
            printf("  Physical size: %dx%d mm\n", h->phys_w, h->phys_h);
            printf("  Enabled: %s\n", h->enabled ? "yes" : "no");
            printf("  Modes:\n");
            for (int m = 0; m < h->n_modes; m++) {
                struct mode_info *mi = &h->modes[m];
                printf("    %dx%d px, %f Hz", mi->w, mi->h, mi->refresh / 1000.0);
                int cur = (h->current == mi->proxy);
                if (mi->preferred && cur)  printf(" (preferred, current)");
                else if (mi->preferred)    printf(" (preferred)");
                else if (cur)              printf(" (current)");
                printf("\n");
            }
            printf("  Position: %d,%d\n", h->x, h->y);
            printf("  Transform: %s\n", transform_name(h->transform));
            printf("  Scale: %f\n", wl_fixed_to_double(h->scale));
        }
        return 0;
    }

    struct head_info *cur = NULL;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--output") == 0 && i + 1 < argc) {
            cur = NULL;
            for (int k = 0; k < n_heads; k++)
                if (strcmp(heads[k].name, argv[i + 1]) == 0) cur = &heads[k];
            if (!cur) {
                fprintf(stderr, "live-schirme-client: unbekannter Ausgang %s\n",
                        argv[i + 1]);
                return 1;
            }
            i++;
        } else if (strcmp(argv[i], "--pos") == 0 && i + 1 < argc && cur) {
            int x, y;
            if (sscanf(argv[i + 1], "%d,%d", &x, &y) != 2) {
                fprintf(stderr, "live-schirme-client: --pos braucht X,Y\n");
                return 1;
            }
            cur->want_pos = 1; cur->want_x = x; cur->want_y = y;
            i++;
        } else if (strcmp(argv[i], "--custom-mode") == 0 && i + 1 < argc && cur) {
            int w, h;
            if (sscanf(argv[i + 1], "%dx%d", &w, &h) != 2) {
                fprintf(stderr, "live-schirme-client: --custom-mode braucht BxH\n");
                return 1;
            }
            cur->want_custom = 1; cur->custom_w = w; cur->custom_h = h;
            i++;
        } else {
            fprintf(stderr, "live-schirme-client: unverstandenes Argument %s\n",
                    argv[i]);
            return 1;
        }
    }

    // EINE Konfiguration fuer ALLE Koepfe. Das Protokoll verlangt es so -
    // ein Kopf, der weder ein noch aus gesetzt wird, laesst den
    // Compositor die ganze Konfiguration ablehnen.
    struct zwlr_output_configuration_v1 *conf =
        zwlr_output_manager_v1_create_configuration(manager, manager_serial);
    zwlr_output_configuration_v1_add_listener(conf, &conf_listener, NULL);

    for (int i = 0; i < n_heads; i++) {
        struct head_info *h = &heads[i];
        if (!h->enabled) {
            zwlr_output_configuration_v1_disable_head(conf, h->proxy);
            continue;
        }
        struct zwlr_output_configuration_head_v1 *ch =
            zwlr_output_configuration_v1_enable_head(conf, h->proxy);
        if (h->want_custom)
            zwlr_output_configuration_head_v1_set_custom_mode(
                ch, h->custom_w, h->custom_h, 0);
        else if (h->current)
            zwlr_output_configuration_head_v1_set_mode(ch, h->current);
        zwlr_output_configuration_head_v1_set_position(
            ch, h->want_pos ? h->want_x : h->x,
            h->want_pos ? h->want_y : h->y);
    }
    zwlr_output_configuration_v1_apply(conf);

    while (apply_result < 0) {
        if (wl_display_dispatch(display) < 0) {
            fprintf(stderr, "live-schirme-client: die Verbindung brach ab\n");
            return 1;
        }
    }
    if (apply_result != 0) {
        fprintf(stderr, "live-schirme-client: der Compositor hat die "
                        "Konfiguration abgelehnt (%d)\n", apply_result);
        return 1;
    }
    wl_display_roundtrip(display);
    return 0;
}
