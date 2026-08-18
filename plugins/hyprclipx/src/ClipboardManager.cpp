// Die Seite, die den clipman-daemon ueber seinen Unix-Socket
// anspricht. Sie ersetzt die Aufrufe, die AGS als
// execAsync("python3 clipman-client.py ...") gemacht hat.

#include "hyprclipx/ClipboardManager.hpp"
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <cstring>
#include <algorithm>

namespace hyprclipx {

ClipboardManager::ClipboardManager(const Config& config)
    : m_config(config) {
}

// ============================================================================
// Der Unix-Socket, so wie send_command in clipman-client.py ihn spricht
// ============================================================================

std::string ClipboardManager::sendCommand(const std::string& cmd, const std::string& argsJson) {
    int sock = socket(AF_UNIX, SOCK_STREAM, 0);
    if (sock == -1) return "";

    struct sockaddr_un addr{};
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, m_config.socketPath.c_str(), sizeof(addr.sun_path) - 1);

    // Die Wartezeit, dieselbe wie in clipman-client.py: fuenf Sekunden
    struct timeval tv{5, 0};
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));

    if (connect(sock, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr)) == -1) {
        close(sock);
        return "";
    }

    // Die Anfrage als JSON, in der Form von clipman-client.py
    std::string request = "{\"cmd\":\"" + cmd + "\",\"args\":" + argsJson + "}";
    send(sock, request.c_str(), request.size(), 0);

    // Die Antwort lesen
    char buf[65536];
    ssize_t n = recv(sock, buf, sizeof(buf) - 1, 0);
    close(sock);

    if (n > 0) {
        buf[n] = '\0';
        return std::string(buf, static_cast<size_t>(n));
    }
    return "";
}

// ============================================================================
// Die Befehle des Dienstes
// ============================================================================

std::vector<ClipboardEntry> ClipboardManager::fetchItems(const std::string& filter,
                                                          const std::string& search,
                                                          int limit) {
    std::string args = "{\"filter\":\"" + filter + "\"";
    if (!search.empty()) {
        // Anfuehrungszeichen im Suchtext maskieren
        std::string escaped = search;
        size_t pos = 0;
        while ((pos = escaped.find('"', pos)) != std::string::npos) {
            escaped.replace(pos, 1, "\\\"");
            pos += 2;
        }
        args += ",\"search\":\"" + escaped + "\"";
    }
    args += ",\"limit\":" + std::to_string(limit) + "}";

    std::string response = sendCommand("list", args);
    if (response.empty()) return {};

    return parseListResponse(response);
}

bool ClipboardManager::paste(const std::string& uuid) {
    std::string args = "{\"uuid\":\"" + uuid + "\"}";
    std::string response = sendCommand("paste", args);
    return response.find("\"ok\"") != std::string::npos;
}

bool ClipboardManager::toggleFavorite(const std::string& uuid) {
    std::string args = "{\"uuid\":\"" + uuid + "\"}";
    std::string response = sendCommand("favorite", args);
    return response.find("\"ok\"") != std::string::npos;
}

bool ClipboardManager::deleteItem(const std::string& uuid) {
    std::string args = "{\"uuid\":\"" + uuid + "\"}";
    std::string response = sendCommand("delete", args);
    return response.find("\"ok\"") != std::string::npos;
}

bool ClipboardManager::clearAll() {
    std::string response = sendCommand("clear");
    return response.find("\"ok\"") != std::string::npos;
}

bool ClipboardManager::ping() {
    std::string response = sendCommand("ping");
    return response.find("\"ok\"") != std::string::npos;
}

// ============================================================================
// JSON lesen - das Noetigste, und nur fuer die Antworten des
// clipman-daemon
// ============================================================================

static std::string extractJsonString(const std::string& json, const std::string& key) {
    std::string needle = "\"" + key + "\":";
    size_t pos = json.find(needle);
    if (pos == std::string::npos) return "";
    pos += needle.size();

    // Leerraum ueberspringen
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) pos++;

    if (pos >= json.size()) return "";

    if (json[pos] == '"') {
        // Eine Zeichenkette
        pos++;
        std::string result;
        while (pos < json.size() && json[pos] != '"') {
            if (json[pos] == '\\' && pos + 1 < json.size()) {
                pos++;
                if (json[pos] == '"') result += '"';
                else if (json[pos] == '\\') result += '\\';
                else if (json[pos] == 'n') result += '\n';
                else if (json[pos] == 't') result += '\t';
                else result += json[pos];
            } else {
                result += json[pos];
            }
            pos++;
        }
        return result;
    }

    if (json[pos] == 'n') return "";  // null

    // Eine Zahl oder ein Wahrheitswert - bis zum naechsten Trennzeichen
    std::string result;
    while (pos < json.size() && json[pos] != ',' && json[pos] != '}' && json[pos] != ']') {
        result += json[pos++];
    }
    return result;
}

std::vector<ClipboardEntry> ClipboardManager::parseListResponse(const std::string& json) {
    std::vector<ClipboardEntry> items;

    // Hat es geklappt?
    if (json.find("\"ok\"") == std::string::npos) return items;

    // Die Liste finden
    size_t dataPos = json.find("\"data\":");
    if (dataPos == std::string::npos) return items;

    size_t arrayStart = json.find('[', dataPos);
    if (arrayStart == std::string::npos) return items;

    // In Objekte zerlegen, ueber Klammerzaehlung
    int depth = 0;
    size_t objStart = 0;
    for (size_t i = arrayStart; i < json.size(); i++) {
        if (json[i] == '{') {
            if (depth == 0) objStart = i;
            depth++;
        } else if (json[i] == '}') {
            depth--;
            if (depth == 0) {
                std::string obj = json.substr(objStart, i - objStart + 1);

                ClipboardEntry entry;
                entry.uuid = extractJsonString(obj, "uuid");
                entry.type = extractJsonString(obj, "type");
                if (entry.type.empty())
                    entry.type = extractJsonString(obj, "content_type");
                entry.preview = extractJsonString(obj, "preview");
                entry.thumb = extractJsonString(obj, "thumb");
                entry.createdAt = extractJsonString(obj, "created_at");

                std::string fav = extractJsonString(obj, "favorite");
                if (fav.empty()) fav = extractJsonString(obj, "is_favorite");
                entry.favorite = (fav == "true" || fav == "1" || fav == "True");

                if (!entry.uuid.empty()) {
                    items.push_back(std::move(entry));
                }
            }
        } else if (json[i] == ']' && depth == 0) {
            break;
        }
    }

    return items;
}

} // namespace hyprclipx
