cmake_minimum_required(VERSION 3.19)
project(hyprlaunch
    VERSION 0.1.0
    DESCRIPTION "Der Anwendungsstarter von ZepOS"
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Die Abhaengigkeiten suchen
find_package(PkgConfig REQUIRED)
pkg_check_modules(HYPRLAND REQUIRED hyprland)
pkg_check_modules(GTK4 REQUIRED gtk4)
pkg_check_modules(GTK4_LAYER REQUIRED gtk4-layer-shell-0)
pkg_check_modules(GIO_UNIX REQUIRED gio-unix-2.0)

# ============================================================================
# Ziel 1: hyprlaunch.so, die Haelfte im Compositor - KEIN GTK, KEINE Threads
# ============================================================================
set(PLUGIN_SOURCES
    src/main.cpp
    src/Globals.cpp
    src/IPCHandler.cpp
    src/ConfigParser.cpp
)

add_library(hyprlaunch SHARED ${PLUGIN_SOURCES})

target_include_directories(hyprlaunch PRIVATE
    ${CMAKE_SOURCE_DIR}/include
    ${HYPRLAND_INCLUDE_DIRS}
)

target_compile_options(hyprlaunch PRIVATE
    -Wall -Wextra -Wpedantic -fPIC
    ${HYPRLAND_CFLAGS_OTHER}
)

set_target_properties(hyprlaunch PROPERTIES
    PREFIX ""
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}"
)

# ============================================================================
# Ziel 2: hyprlaunch-ui, ein eigenstaendiges GTK4-Programm - KEIN Hyprland
# ============================================================================
set(UI_SOURCES
    src/main_ui.cpp
    src/LauncherRenderer.cpp
    src/AppDiscovery.cpp
    src/ConfigParser.cpp
)

add_executable(hyprlaunch-ui ${UI_SOURCES})

target_include_directories(hyprlaunch-ui PRIVATE
    ${CMAKE_SOURCE_DIR}/include
    ${GTK4_INCLUDE_DIRS}
    ${GTK4_LAYER_INCLUDE_DIRS}
    ${GIO_UNIX_INCLUDE_DIRS}
)

target_link_libraries(hyprlaunch-ui PRIVATE
    ${GTK4_LIBRARIES}
    ${GTK4_LAYER_LIBRARIES}
    ${GIO_UNIX_LIBRARIES}
)

target_compile_options(hyprlaunch-ui PRIVATE
    -Wall -Wextra -Wpedantic
)

set_target_properties(hyprlaunch-ui PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}"
)

# Wohin installiert wird
install(TARGETS hyprlaunch LIBRARY DESTINATION lib/hyprland/plugins)
install(TARGETS hyprlaunch-ui RUNTIME DESTINATION bin)
