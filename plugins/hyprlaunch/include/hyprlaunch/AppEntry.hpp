#pragma once
#include <string>
#include <vector>

namespace hyprlaunch {

struct AppEntry {
    std::string id;
    std::string name;
    std::string icon;
    std::string exec;
    std::string description;
    std::vector<std::string> keywords;
};

} // namespace hyprlaunch
