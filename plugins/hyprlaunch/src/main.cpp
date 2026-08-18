// hyprlaunch - der Anwendungsstarter von ZepOS, Plugin-Haelfte
// Der Einstieg des Plugins, und er ist absichtlich duenn: kein GTK,
// keine Threads. Die Oberflaeche laeuft als eigener Prozess
// (hyprlaunch-ui).

#define WLR_USE_UNSTABLE
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/Compositor.hpp>

#include "hyprlaunch/Globals.hpp"

using namespace hyprlaunch;

// g_pHandle STAND HIER UND IST WEG (12.08.2026)
//
// Es hielt eine zweite Kopie desselben Zeigers, den Globals.cpp als
// g_handle fuehrt. Gelesen wurde es an genau einer Stelle - der
// Abmeldemeldung in PLUGIN_EXIT -, und die ist mit derselben
// Aenderung gegangen. Was blieb, war eine Zuweisung ohne Leser.

// ============================================================================
// Die Befehle von `hyprctl hyprlaunch:<befehl>`
// ============================================================================

static std::string cmdShow(eHyprCtlOutputFormat, std::string) {
    sendUICommand("show");
    return "ok";
}

static std::string cmdHide(eHyprCtlOutputFormat, std::string) {
    sendUICommand("hide");
    return "ok";
}

static std::string cmdToggle(eHyprCtlOutputFormat, std::string) {
    sendUICommand("toggle");
    return "ok";
}

static std::string cmdApps(eHyprCtlOutputFormat, std::string) {
    sendUICommand("apps");
    return "ok";
}

static std::string cmdHelpers(eHyprCtlOutputFormat, std::string) {
    sendUICommand("helpers");
    return "ok";
}

static std::string cmdReload(eHyprCtlOutputFormat, std::string) {
    reloadConfig();
    return "config reloaded";
}

// ============================================================================
// Die Dispatcher, ueber die eine Tastenbindung dasselbe erreicht
// ============================================================================

static SDispatchResult dispatchShow(std::string) {
    sendUICommand("show");
    return {.success = true};
}

static SDispatchResult dispatchHide(std::string) {
    sendUICommand("hide");
    return {.success = true};
}

static SDispatchResult dispatchToggle(std::string) {
    sendUICommand("toggle");
    return {.success = true};
}

static SDispatchResult dispatchApps(std::string) {
    sendUICommand("apps");
    return {.success = true};
}

static SDispatchResult dispatchHelpers(std::string) {
    sendUICommand("helpers");
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

    // Die Befehle anmelden (hyprctl hyprlaunch:<befehl>)
    HyprlandAPI::registerHyprCtlCommand(g_handle,
        SHyprCtlCommand{"hyprlaunch:show", true, cmdShow});
    HyprlandAPI::registerHyprCtlCommand(g_handle,
        SHyprCtlCommand{"hyprlaunch:hide", true, cmdHide});
    HyprlandAPI::registerHyprCtlCommand(g_handle,
        SHyprCtlCommand{"hyprlaunch:toggle", true, cmdToggle});
    HyprlandAPI::registerHyprCtlCommand(g_handle,
        SHyprCtlCommand{"hyprlaunch:apps", true, cmdApps});
    HyprlandAPI::registerHyprCtlCommand(g_handle,
        SHyprCtlCommand{"hyprlaunch:helpers", true, cmdHelpers});
    HyprlandAPI::registerHyprCtlCommand(g_handle,
        SHyprCtlCommand{"hyprlaunch:reload", true, cmdReload});

    // Die Dispatcher anmelden
    HyprlandAPI::addDispatcherV2(handle, "hyprlaunch:show", dispatchShow);
    HyprlandAPI::addDispatcherV2(handle, "hyprlaunch:hide", dispatchHide);
    HyprlandAPI::addDispatcherV2(handle, "hyprlaunch:toggle", dispatchToggle);
    HyprlandAPI::addDispatcherV2(handle, "hyprlaunch:apps", dispatchApps);
    HyprlandAPI::addDispatcherV2(handle, "hyprlaunch:helpers", dispatchHelpers);

    // Die Konfigurationsschluessel anmelden
    HyprlandAPI::addConfigValue(handle, "plugin:hyprlaunch:enabled",
                                Hyprlang::INT{1});
    HyprlandAPI::addConfigValue(handle, "plugin:hyprlaunch:hotkey",
                                Hyprlang::STRING{"SUPER D"});

    // HIER STAND EINE ERFOLGSMELDUNG, UND SIE IST ERSATZLOS WEG
    //
    //     HyprlandAPI::addNotification(handle,
    //         "[HyprLaunch] Loaded successfully!",
    //         CHyprColor(0.2f, 0.8f, 0.2f, 1.0f), 5000);
    //
    // GEMESSEN am 12.08.2026: PLUGIN_INIT laeuft, wenn Hyprland die
    // Konfiguration liest, also bei JEDER Anmeldung. hyprclipx hatte
    // dieselbe Zeile. Ein Nutzer bekam damit bei jedem Start zwei
    // gruene Kaesten fuenf Sekunden lang aufs Bild, in englischer
    // Sprache und unter einem fremden Produktnamen - auf einem
    // Schreibtisch, der sonst durchgehend deutsch ist.
    //
    // WARUM LOESCHEN UND NICHT UEBERSETZEN
    //     Weil eine Meldung, die IMMER kommt, keine Meldung ist. Sie
    //     sagt "es hat geklappt" ueber etwas, das der Nutzer nicht
    //     angestossen hat und dessen Klappen er an der Taste merkt.
    //     Was wirklich eine Nachricht waere - das Plugin laedt NICHT -
    //     kann diese Zeile ohnehin nicht melden: sie steht hinter dem
    //     Laden. Diesen Fall deckt src/plugins.py ab, das den Block gar
    //     nicht erst schreibt und in die erzeugte Datei hineinschreibt,
    //     warum.
    //
    // Dasselbe gilt fuer die Zeile in PLUGIN_EXIT. Sie kam beim
    // Abmelden und beim Neuladen der Konfiguration - in dem einen Fall
    // sieht sie niemand mehr, in dem anderen folgt ihr eine halbe
    // Sekunde spaeter die Erfolgsmeldung von oben.

    // Der dritte Eintrag ist der URHEBER, den `hyprctl plugin list`
    // als "by ..." ausgibt. Dort stand der Produktname des fremden
    // Baums. Was ZepOS ausliefert, ist eine Bearbeitung, deren
    // Herkunft in plugins/LICENSE steht - und die Frage, die ein
    // Nutzer mit `plugin list` stellt, ist "von wem habe ich das".
    return {
        "hyprlaunch",
        "Der Anwendungsstarter von ZepOS",
        "ZepOS",
        "0.1.0"
    };
}

APICALL EXPORT void PLUGIN_EXIT() {
    cleanupGlobals();
}
