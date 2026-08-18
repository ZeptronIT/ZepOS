cmake_minimum_required(VERSION 3.19)
project(hyprclipx
    VERSION 0.1.0
    DESCRIPTION "Der Zwischenablage-Verlauf von ZepOS"
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
pkg_check_modules(PANGO REQUIRED pango pangocairo)
pkg_check_modules(CAIRO REQUIRED cairo)

# ============================================================================
# Ziel 1: hyprclipx.so, die Haelfte im Compositor - KEIN GTK, KEINE Threads
# ============================================================================
set(PLUGIN_SOURCES
    src/main.cpp
    src/Globals.cpp
    src/IPCHandler.cpp
    src/ConfigParser.cpp
)

add_library(hyprclipx SHARED ${PLUGIN_SOURCES})

target_include_directories(hyprclipx PRIVATE
    ${CMAKE_SOURCE_DIR}/include
    ${HYPRLAND_INCLUDE_DIRS}
)

# Diese Haelfte bindet NICHTS ausser Hyprland - kein GTK, kein Pango,
# kein Cairo
target_compile_options(hyprclipx PRIVATE
    -Wall -Wextra -Wpedantic -fPIC
    ${HYPRLAND_CFLAGS_OTHER}
)

set_target_properties(hyprclipx PROPERTIES
    PREFIX ""
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}"
)

# ============================================================================
# Ziel 2: hyprclipx-ui, ein eigenstaendiges GTK4-Programm - KEIN Hyprland
# ============================================================================
set(UI_SOURCES
    src/main_ui.cpp
    src/ClipboardRenderer.cpp
    src/ClipboardManager.cpp
    src/ConfigParser.cpp
)

add_executable(hyprclipx-ui ${UI_SOURCES})

target_include_directories(hyprclipx-ui PRIVATE
    ${CMAKE_SOURCE_DIR}/include
    ${GTK4_INCLUDE_DIRS}
    ${GTK4_LAYER_INCLUDE_DIRS}
    ${PANGO_INCLUDE_DIRS}
    ${CAIRO_INCLUDE_DIRS}
)

target_link_libraries(hyprclipx-ui PRIVATE
    ${GTK4_LIBRARIES}
    ${GTK4_LAYER_LIBRARIES}
    ${PANGO_LIBRARIES}
    ${CAIRO_LIBRARIES}
)

target_compile_options(hyprclipx-ui PRIVATE
    -Wall -Wextra -Wpedantic
)

set_target_properties(hyprclipx-ui PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}"
)

# Wohin installiert wird
install(TARGETS hyprclipx LIBRARY DESTINATION lib/hyprland/plugins)
install(TARGETS hyprclipx-ui RUNTIME DESTINATION bin)

# ============================================================================
# Ziel 3: die zwei Python-Haelften
# ============================================================================
#
# WARUM SIE HIER STEHEN UND NICHT IM REZEPT
#     Weil sie zum Programm gehoeren und nicht zur Verpackung. Wer aus
#     dem Arbeitsbaum `cmake --install` aufruft, soll einen
#     funktionierenden Verlauf bekommen und nicht die Haelfte davon;
#     das Rezept prueft danach nur, dass beide da sind.
#
# WARUM /usr/lib/hyprclipx UND NICHT /usr/bin
#     include/hyprclipx/Config.hpp fuehrt das Argument aus: keins der
#     beiden ist ein Programm, das ein Mensch aufruft. Der Sammler ist
#     ein Dienst, den die Sitzung startet, und der Schreibmarken-Helfer
#     druckt ein Koordinatenpaar fuer genau einen Aufrufer.
#
# WARUM lib UND NICHT ${CMAKE_INSTALL_LIBDIR}
#     Weil ${CMAKE_INSTALL_LIBDIR} auf manchen Zielen lib64 ist und der
#     Pfad in Config.hpp eine feste Zeichenkette ist. Zwei Wege, die
#     auseinanderlaufen koennen, waeren ein Helfer, der auf genau den
#     Maschinen fehlt, auf denen niemand danach sucht. Die beiden
#     Zeilen darueber tun dasselbe (lib/hyprland/plugins, bin), aus
#     demselben Grund: Hyprland sucht seine Plugins ebenfalls an einem
#     festen Pfad.
install(PROGRAMS
    helpers/collector.py
    helpers/caret-position.py
    DESTINATION lib/hyprclipx)
