// Die Befehle der Compositor-Haelfte - KEIN GTK hier!
// Weitergereicht wird an hyprclipx-ui, ueber fork+exec.

#include "hyprclipx/IPCHandler.hpp"
#include "hyprclipx/Globals.hpp"

namespace hyprclipx {

IPCHandler::IPCHandler() {
    registerCommand("show", cmdShow);
    registerCommand("hide", cmdHide);
    registerCommand("toggle", cmdToggle);
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
    captureAndSendUI("show");
    return "ok";
}

std::string IPCHandler::cmdHide(const std::string&) {
    sendUICommand("hide");
    return "ok";
}

std::string IPCHandler::cmdToggle(const std::string&) {
    captureAndSendUI("toggle");
    return "ok";
}

std::string IPCHandler::cmdReload(const std::string&) {
    reloadConfig();
    return "config reloaded";
}

} // namespace hyprclipx
