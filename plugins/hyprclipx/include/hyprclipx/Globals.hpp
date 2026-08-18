#pragma once
#include "Forward.hpp"
#include "Config.hpp"
#include <memory>
#include <string>

namespace hyprclipx {

extern std::unique_ptr<IPCHandler> g_ipcHandler;
extern Config g_config;
extern void* g_handle;

void initGlobals();
void cleanupGlobals();
void reloadConfig();

// Schreibmarke und Fenster ueber die Schnittstellen von Hyprland
// festhalten, dann die Oberflaeche ueber fork+exec ansprechen.
// Festgehalten wird VOR dem Oeffnen des Fensters, genau wie
// ags-toggle-clipboard.template es gemacht hat: danach liegt der Fokus
// beim Verlauf, und die Schreibmarke waere die falsche.
void captureAndSendUI(const std::string& cmd);

// Einen Befehl an die Oberflaeche schicken, ohne die Schreibmarke
// festzuhalten (etwa "hide")
void sendUICommand(const std::string& cmd);

} // namespace hyprclipx
