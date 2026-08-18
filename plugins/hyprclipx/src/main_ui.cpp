// hyprclipx-ui - der Zwischenablage-Verlauf von ZepOS, als eigener
// GTK4-Prozess (NICHT im Compositor!)
// Laeuft als gewoehnlicher Wayland-Client und nimmt seine Befehle ueber
// einen Unix-Socket entgegen - derselbe Aufbau wie unter AGS, wo die
// Oberflaeche ebenfalls ein eigener Prozess war.

#include "hyprclipx/ClipboardRenderer.hpp"
#include "hyprclipx/ClipboardManager.hpp"
#include "hyprclipx/ConfigParser.hpp"
#include <gtk/gtk.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <csignal>
#include <cstdlib>
#include <cstring>
#include <string>

using namespace hyprclipx;

static const char* SOCKET_PATH = "/tmp/hyprclipx-ui.sock";
static ClipboardRenderer* g_renderer = nullptr;
static int g_listenSock = -1;

// ============================================================================
// Einen Befehl an eine schon laufende Oberflaeche schicken. Wahr, wenn
// er angekommen ist.
// ============================================================================

static bool sendCommand(const char* cmd) {
    int sock = socket(AF_UNIX, SOCK_STREAM, 0);
    if (sock == -1) return false;

    struct sockaddr_un addr{};
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, SOCKET_PATH, sizeof(addr.sun_path) - 1);

    if (connect(sock, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr)) == -1) {
        close(sock);
        return false;
    }

    ssize_t written = write(sock, cmd, strlen(cmd));
    close(sock);
    return written > 0;
}

// ============================================================================
// Der Socket, an dem die Compositor-Haelfte ihre Befehle abliefert
// ============================================================================

static gboolean onSocketAccept(GIOChannel*, GIOCondition, gpointer) {
    struct sockaddr_un clientAddr{};
    socklen_t clientLen = sizeof(clientAddr);
    int clientSock = accept(g_listenSock,
        reinterpret_cast<struct sockaddr*>(&clientAddr), &clientLen);
    if (clientSock == -1) return TRUE;

    char buf[64] = {};
    ssize_t n = read(clientSock, buf, sizeof(buf) - 1);
    close(clientSock);

    if (n > 0 && g_renderer) {
        std::string cmd(buf, static_cast<size_t>(n));
        if (cmd == "toggle") g_renderer->toggle();
        else if (cmd == "show") g_renderer->show();
        else if (cmd == "hide") g_renderer->hide();
    }

    return TRUE;
}

static bool createSocketListener() {
    unlink(SOCKET_PATH);

    g_listenSock = socket(AF_UNIX, SOCK_STREAM, 0);
    if (g_listenSock == -1) return false;

    struct sockaddr_un addr{};
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, SOCKET_PATH, sizeof(addr.sun_path) - 1);

    if (bind(g_listenSock, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr)) == -1) {
        close(g_listenSock);
        g_listenSock = -1;
        return false;
    }

    listen(g_listenSock, 5);

    GIOChannel* channel = g_io_channel_unix_new(g_listenSock);
    g_io_add_watch(channel, G_IO_IN, onSocketAccept, nullptr);
    g_io_channel_unref(channel);

    return true;
}

// ============================================================================
// Das Ende, wenn ein Signal kommt
// ============================================================================

static GMainLoop* g_mainLoop = nullptr;

static void onSignal(int) {
    if (g_mainLoop) g_main_loop_quit(g_mainLoop);
}

// ============================================================================
// Main
// ============================================================================

int main(int argc, char* argv[]) {
    // Den Befehl von der Befehlszeile lesen
    std::string cmd;
    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];
        if (arg == "--toggle" || arg == "toggle") cmd = "toggle";
        else if (arg == "--show" || arg == "show") cmd = "show";
        else if (arg == "--hide" || arg == "hide") cmd = "hide";
    }

    // Gibt es einen Befehl, zuerst die laufende Oberflaeche fragen
    if (!cmd.empty()) {
        if (sendCommand(cmd.c_str())) {
            return 0;  // angekommen, mehr ist nicht zu tun
        }
        // Es laeuft keine - also eine starten und den Befehl ausfuehren
    }

    // GTK hochfahren. Unbedenklich: das hier ist ein eigener
    // Wayland-Client und NICHT der Compositor.
    gtk_init();

    // Die Konfiguration
    //
    // Hier standen drei Zeilen, die drei Pfade unter ~ zusammensetzten
    // - dieselben drei, die Globals.cpp auf der anderen Seite noch
    // einmal zusammensetzte. Zwei Kopien einer Pfadberechnung sind zwei
    // Kopien, die auseinanderlaufen; jetzt setzt loadConfig() sie, und
    // die Begruendung steht in Config.hpp.
    Config config = loadConfig();

    // Die Teile
    ClipboardManager manager(config);
    ClipboardRenderer renderer(config, manager);
    g_renderer = &renderer;

    // Die Oberflaeche bauen - Fenster, Stil, Widgets -, aber noch nicht
    // zeigen
    renderer.initialize();

    // Den Socket aufmachen, ueber den die Compositor-Haelfte spricht
    createSocketListener();

    // Wurde mit einem Befehl gestartet, kommt er jetzt dran
    if (!cmd.empty()) {
        if (cmd == "toggle" || cmd == "show") {
            renderer.show();
        }
    }

    // Signale
    signal(SIGINT, onSignal);
    signal(SIGTERM, onSignal);

    // Die Hauptschleife von GLib
    g_mainLoop = g_main_loop_new(nullptr, FALSE);
    g_main_loop_run(g_mainLoop);
    g_main_loop_unref(g_mainLoop);

    // Aufraeumen
    g_renderer = nullptr;
    unlink(SOCKET_PATH);
    if (g_listenSock >= 0) close(g_listenSock);

    return 0;
}
