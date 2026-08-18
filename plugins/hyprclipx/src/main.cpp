// hyprclipx - der Zwischenablage-Verlauf von ZepOS, Plugin-Haelfte
// Der Einstieg des Plugins, und er ist absichtlich duenn: kein GTK,
// keine Threads. Die Oberflaeche laeuft als eigener Prozess
// (hyprclipx-ui).

#define WLR_USE_UNSTABLE
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/Compositor.hpp>

#include "hyprclipx/Globals.hpp"
#include "hyprclipx/IPCHandler.hpp"

using namespace hyprclipx;

// g_pHandle STAND HIER UND IST WEG (12.08.2026)
//
// Es hielt eine zweite Kopie desselben Zeigers, den Globals.cpp als
// g_handle fuehrt. Gelesen wurde es an genau einer Stelle - der
// Abmeldemeldung in PLUGIN_EXIT -, und die ist mit derselben
// Aenderung gegangen. Was blieb, war eine Zuweisung ohne Leser.

// ============================================================================
// Die Befehle von `hyprctl hyprclipx <befehl> [argumente]`
// ============================================================================

static std::string cmdHyprclipx(eHyprCtlOutputFormat, std::string request) {
    std::string cmd = request;
    std::string args;

    size_t spacePos = cmd.find(' ');
    if (spacePos != std::string::npos) {
        args = cmd.substr(spacePos + 1);
        cmd = cmd.substr(0, spacePos);
    }

    if (g_ipcHandler) {
        return g_ipcHandler->handleCommand(cmd, args);
    }
    return "error: not initialized";
}

// ============================================================================
// Die Dispatcher, in derselben Reihenfolge wie
// ags-toggle-clipboard.template sie hatte
// ============================================================================

static SDispatchResult dispatchShow(std::string) {
    captureAndSendUI("show");
    return {.success = true};
}

static SDispatchResult dispatchHide(std::string) {
    sendUICommand("hide");
    return {.success = true};
}

// Umschalten: die Schreibmarke wird VORHER festgehalten, so wie AGS es
// getan hat - danach liegt der Fokus beim Verlauf
static SDispatchResult dispatchToggle(std::string) {
    captureAndSendUI("toggle");
    return {.success = true};
}

// ============================================================================
// Das Leben des Plugins
// ============================================================================

APICALL EXPORT std::string PLUGIN_API_VERSION() {
    return HYPRLAND_API_VERSION;
}

APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE handle) {
    g_handle = handle;

    initGlobals();

    // Den Befehl anmelden
    HyprlandAPI::registerHyprCtlCommand(g_handle,
        SHyprCtlCommand{"hyprclipx", true, cmdHyprclipx});

    // Die Dispatcher anmelden
    HyprlandAPI::addDispatcherV2(handle, "hyprclipx:show", dispatchShow);
    HyprlandAPI::addDispatcherV2(handle, "hyprclipx:hide", dispatchHide);
    HyprlandAPI::addDispatcherV2(handle, "hyprclipx:toggle", dispatchToggle);

    // Die Konfigurationsschluessel anmelden
    HyprlandAPI::addConfigValue(handle, "plugin:hyprclipx:enabled",
                                Hyprlang::INT{1});
    HyprlandAPI::addConfigValue(handle, "plugin:hyprclipx:hotkey",
                                Hyprlang::STRING{"SUPER V"});

    // Die Erfolgsmeldung bei jeder Anmeldung ist weg, und der Urheber
    // ist jetzt der, der das hier ausliefert. Die Begruendung steht in
    // voller Laenge in plugins/hyprlaunch/src/main.cpp; sie gilt hier
    // wortgleich, und die zwei gruenen Kaesten, die sie zaehlt, waren
    // dieser und der dort.
    return {
        "hyprclipx",
        "Der Zwischenablage-Verlauf von ZepOS",
        "ZepOS",
        "0.1.0"
    };
}

APICALL EXPORT void PLUGIN_EXIT() {
    cleanupGlobals();
}
