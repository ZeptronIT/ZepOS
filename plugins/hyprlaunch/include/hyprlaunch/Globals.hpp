#pragma once
#include "Forward.hpp"
#include "Config.hpp"
#include <memory>
#include <string>

namespace hyprlaunch {

extern std::unique_ptr<IPCHandler> g_ipcHandler;
extern Config g_config;
extern void* g_handle;

void initGlobals();
void cleanupGlobals();
void reloadConfig();

// Fork+exec UI command (never blocks compositor)
void sendUICommand(const std::string& cmd);

} // namespace hyprlaunch
