// Die Befehle der Compositor-Haelfte - KEIN GTK hier!
// Weitergereicht wird an hyprlaunch-ui, ueber fork+exec.

#include "hyprlaunch/IPCHandler.hpp"
#include "hyprlaunch/Globals.hpp"

namespace hyprlaunch {

IPCHandler::IPCHandler() {
    registerCommand("show", cmdShow);
    registerCommand("hide", cmdHide);
    registerCommand("toggle", cmdToggle);
    registerCommand("apps", cmdApps);
    registerCommand("helpers", cmdHelpers);
    registerCommand("reload", cmdReload);
}

IPCHandler::~IPCHandler() = default;

void IPCHandler::registerCommand(const std::string& name,
                                  std::function<std::string(const std::string&)> handler) {
    m_commands[name] = std::move(handler);
}

std::string IPCHandler::handleCommand(const std::string& command,
                                       const std::string& args) {
    auto it = m_commands.find(command);
    if (it != m_commands.end()) {
        return it->second(args);
    }
    return "unknown command: " + command;
}

std::string IPCHandler::cmdShow(const std::string&) {
    sendUICommand("show");
    return "ok";
}

std::string IPCHandler::cmdHide(const std::string&) {
    sendUICommand("hide");
    return "ok";
}

std::string IPCHandler::cmdToggle(const std::string&) {
    sendUICommand("toggle");
    return "ok";
}

std::string IPCHandler::cmdApps(const std::string&) {
    sendUICommand("apps");
    return "ok";
}

std::string IPCHandler::cmdHelpers(const std::string&) {
    sendUICommand("helpers");
    return "ok";
}

std::string IPCHandler::cmdReload(const std::string&) {
    reloadConfig();
    return "config reloaded";
}

} // namespace hyprlaunch
