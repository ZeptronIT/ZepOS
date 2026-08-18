#!/bin/bash

# generate_config.sh - Generates configs from templates with icons
# Usage: ./generate_config.sh -ags-bar|-hyprland|-kitty|...

# Where this script itself lives, with its own symlinks resolved: called
# through a link in ~/.local/bin, a plain dirname would report that link's
# directory and the whole package would appear to live there.
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

# The three roles the origin project kept in a single directory.
#
# ZEPOS_SYSTEM_ROOT holds templates, styles and the SSOT; it belongs to
# the package and is only read. Its default is this script's own
# directory rather than the literal /usr/share/zepos: on an installed
# system the two are the same path, in a checkout they are not, and
# hard-coding the installed one would make every run from a checkout read
# templates out of a package that need not even be installed.
#
# ZEPOS_USER_ROOT holds settings, profiles, the generated helper scripts
# and any template the user overrides. It is what a package must never
# own.
#
# ZEPOS_OUTPUT_ROOT is where the generated configuration of OTHER
# programs goes - hypr, ags, kitty. It is deliberately not separately
# overridable: those programs read their configuration from
# XDG_CONFIG_HOME and would not follow us anywhere else.
ZEPOS_SYSTEM_ROOT="${ZEPOS_SYSTEM_ROOT:-$SCRIPT_DIR}"
ZEPOS_USER_ROOT="${ZEPOS_USER_ROOT:-${XDG_CONFIG_HOME:-$HOME/.config}/zepos}"
ZEPOS_OUTPUT_ROOT="${XDG_CONFIG_HOME:-$HOME/.config}"

# Which of the two template directories the current config comes from.
# Style templates live in styles/, everything else in templates/.
ZEPOS_TEMPLATE_SUBDIR="${ZEPOS_TEMPLATE_SUBDIR:-templates}"

# Arrays, not strings. A string holding "python3 /some/path/x.py" has to
# be invoked unquoted to be a command at all, and an unquoted expansion
# is split on every space in it: measured with a checkout under a path
# containing one, every single call became
# `python3: can't open file '.../sp'`, ninety-eight times over in a
# --all run. Expanded as "${ARRAY[@]}" each element stays one word,
# whatever it contains.
PYTHON_CMD=(python3 "$ZEPOS_SYSTEM_ROOT/template_processor.py")

# Checks the staged tree and moves it into place. Its own header explains
# why the move is file by file and never directory by directory.
VALIDATE_CMD=(python3 "$ZEPOS_SYSTEM_ROOT/validate_output.py")

# This script, by a path that works from anywhere.
#
# The recursive calls used $0, which is whatever the caller typed: from
# inside src/, `bash generate_config.sh --all` gave every child
# "generate_config.sh" - not a path - and bash answered
# "generate_config.sh: command not found" ninety-nine times while the run
# reported ninety-nine failures with no other explanation. SCRIPT_DIR is
# resolved above and does not depend on the caller's shell.
#
# The usage text keeps $0 on purpose: it should echo the name the user
# typed, and it is printed, not executed.
SELF="$SCRIPT_DIR/$(basename "$(readlink -f "${BASH_SOURCE[0]}")")"

# A user template beats the packaged one. Without this order a package
# update would silently discard every local change.
find_template() {
    local name="$1"
    local subdir="$2"
    local candidate
    for candidate in "$ZEPOS_USER_ROOT/$subdir/$name.template" \
                     "$ZEPOS_SYSTEM_ROOT/$subdir/$name.template"; do
        if [ -f "$candidate" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

# Every template name in one directory, system and user, each listed
# once. Without the user root a template that exists only as a local
# addition stays invisible to --all, even though naming it explicitly
# works - which is the kind of gap nobody reports as a bug.
list_template_names() {
    local subdir="$1"
    local path
    for path in "$ZEPOS_SYSTEM_ROOT/$subdir"/*.template \
                "$ZEPOS_USER_ROOT/$subdir"/*.template; do
        [ -f "$path" ] && basename "$path" .template
    done | sort -u
}

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# =========================================
# STAGING
# =========================================
#
# Nothing reaches the live configuration until the whole run has been
# generated and checked. Everything is written into a staging area first,
# mirroring absolute paths below <stage>/files, and validate_output.py
# moves the files into place at the end.
#
# The files are moved ONE BY ONE and the directory is never replaced,
# because none of the target directories belong to this program.
# ~/.config/hypr also holds monitors.conf, which the settings
# application writes, workspaces.conf, which save-profile writes,
# current-profile,
# emergency-backups/ and every .backup.<date> this generator itself took.
# Replacing the directory would delete all of them: the monitor layout,
# which cannot be regenerated from anything in this tree, and the very
# backups that exist so a bad generation can be undone.
#
# A --all run creates ONE staging area and exports it. Every child stages
# into it and publishes nothing, so a template that fails at number
# seventy stops the sixty-nine before it from reaching the disk.

# True when this process created the staging area and therefore has to
# check it and publish it.
STAGE_OWNER=false

new_stage() {
    local root="${XDG_CACHE_HOME:-$HOME/.cache}/zepos"
    mkdir -p "$root" || return 1

    local stage
    stage="$(mktemp -d "$root/stage-$(date +%Y-%m-%d-%H%M%S)-XXXXXX")" || return 1
    mkdir -p "$stage/files" || return 1

    # validate_output.py walks every file below what it is handed, so it
    # refuses a directory without this marker. Pointed at a home
    # directory by a wrong argument it would otherwise read all of it.
    : > "$stage/.zepos-stage" || return 1

    printf '%s\n' "$stage"
}

# Check the staged tree, then move it into place. On a finding nothing is
# written at all, the staging area is kept for inspection, and the reason
# names the file it came from.
publish_stage() {
    local stage="$1"

    echo -e "${GREEN}→ Checking generated configuration...${NC}"
    if ! "${VALIDATE_CMD[@]}" check "$stage"; then
        echo -e "${RED}✗ The generated configuration was rejected.${NC}" >&2
        echo -e "${RED}  Nothing was written; the previous configuration is unchanged.${NC}" >&2
        echo -e "${YELLOW}  The generated files were kept for inspection in:${NC}" >&2
        echo -e "${YELLOW}  $stage/files${NC}" >&2
        return 1
    fi

    echo -e "${GREEN}→ Putting the generated configuration in place...${NC}"
    if ! "${VALIDATE_CMD[@]}" publish "$stage"; then
        echo -e "${RED}✗ Could not put the generated configuration in place.${NC}" >&2
        echo -e "${YELLOW}  The generated files were kept in: $stage/files${NC}" >&2
        return 1
    fi

    rm -rf "$stage"
}

# Ensure ~/.local/bin exists and warn if not in PATH
ensure_local_bin() {
    local LOCAL_BIN="$HOME/.local/bin"

    # Create directory if it doesn't exist
    if [ ! -d "$LOCAL_BIN" ]; then
        echo -e "${YELLOW}→ Creating $LOCAL_BIN${NC}"
        mkdir -p "$LOCAL_BIN"
    fi

    # Check if in PATH
    if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
        echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
        echo -e "${YELLOW}⚠ WARNING: ~/.local/bin is NOT in your PATH!${NC}"
        echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
        echo ""
        echo "Add this to your ~/.zshrc or ~/.bashrc:"
        echo ""
        echo -e "  ${GREEN}export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
        echo ""
        echo "Then run: source ~/.zshrc"
        echo ""
        echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
        echo ""
    fi
}

# Run check at startup
ensure_local_bin

# Function to generate all configs
generate_all_configs() {
    echo -e "${YELLOW}=== Generating ALL configs ===${NC}"
    echo ""
    echo -e "${GREEN}Using universal Hyprland config (profile selected at startup: start-hyprland <profile>)${NC}"
    echo ""

    local success_count=0
    local fail_count=0
    local total_count=0

    # Every config that generated cleanly, in the order it was generated.
    # Their post-generation actions - the restarts and the merges - run
    # after the whole run has been published, against files that are
    # actually in place.
    local generated_names=()

    # One staging area for the entire run, exported so every child stages
    # into it instead of publishing on its own.
    ZEPOS_STAGE_DIR="$(new_stage)" || {
        echo -e "${RED}✗ Could not create a staging directory${NC}" >&2
        return 1
    }
    export ZEPOS_STAGE_DIR

    # Find all templates, in both roots. The directory travels with the
    # name because the name alone does not say whether a config is a
    # style, and the two live in different directories.
    local all_templates=()
    local name

    while IFS= read -r name; do
        [ -n "$name" ] && all_templates+=("templates:$name")
    done < <(list_template_names templates)

    while IFS= read -r name; do
        [ -n "$name" ] && all_templates+=("styles:$name")
    done < <(list_template_names styles)

    # System-Integration, kein Nutzer-Config: die sudoers-Regel, mit der
    # der VPN-Watcher und der Netz-Watchdog ohne zwischengespeichertes
    # Passwort arbeiten koennen. Eigenes Verzeichnis, weil
    # tests/src/test_inventory.py die Anzahl in templates/ als Vertrag
    # festhaelt - eine 78. Datei dort waere ein Vertragsbruch, kein Feature.
    while IFS= read -r name; do
        [ -n "$name" ] && all_templates+=("system:$name")
    done < <(list_template_names system)

    # Process each template
    local entry
    for entry in "${all_templates[@]}"; do
        local subdir="${entry%%:*}"
        local base_name="${entry#*:}"

        # Skip OLD profile-specific Hyprland configs (replaced by universal config)
        if [[ "$base_name" =~ ^hyprland-(gaming|work-home|work-office)-config$ ]]; then
            echo -e "${YELLOW}→ Skipping:${NC} ${base_name} (deprecated - using universal config)"
            continue
        fi

        # Skip OLD start-hyprland-* scripts (replaced by universal start-hyprland)
        if [[ "$base_name" =~ ^start-hyprland-(gaming|home|office)-config$ ]]; then
            echo -e "${YELLOW}→ Skipping:${NC} ${base_name} (deprecated - using universal start-hyprland)"
            continue
        fi

        ((total_count++))
        echo -e "${GREEN}→ Processing:${NC} ${base_name%-config}"

        # Tell the child which of the two template directories to look in
        ZEPOS_TEMPLATE_SUBDIR="$subdir" "$SELF" -"$base_name"

        if [ $? -eq 0 ]; then
            echo -e "  ${GREEN}✓ Success${NC}"
            ((success_count++))
            generated_names+=("$base_name")
        else
            echo -e "  ${RED}✗ Failed${NC}"
            ((fail_count++))
        fi
    done


    # Summary
    echo ""
    echo -e "${YELLOW}=== Summary ===${NC}"
    echo -e "Total configs: ${total_count}"
    echo -e "Successful: ${GREEN}${success_count}${NC}"
    if [ $fail_count -gt 0 ]; then
        echo -e "Failed: ${RED}${fail_count}${NC}"
    fi
    echo ""

    # One failure anywhere means the run publishes nothing. The point of
    # the staging area: the configs that DID generate are not written
    # either, so the user is left with the set that was working rather
    # than a half-updated one.
    if [ $fail_count -gt 0 ]; then
        echo -e "${RED}✗ Some configs failed!${NC}"
        echo -e "${RED}  Nothing was written; the previous configuration is unchanged.${NC}"
        echo -e "${YELLOW}  The generated files were kept for inspection in:${NC}"
        echo -e "${YELLOW}  $ZEPOS_STAGE_DIR/files${NC}"
        echo ""  # Extra newline for clean prompt
        return 1
    fi

    publish_stage "$ZEPOS_STAGE_DIR" || return 1

    # The children see it in their environment and would stage instead of
    # publishing. Everything below writes to the live configuration.
    unset ZEPOS_STAGE_DIR

    # Each config's own post-generation step - the service restarts and
    # the workspace detection - now that its file is in place.
    local generated_name
    for generated_name in "${generated_names[@]}"; do
        "$SELF" --post "-$generated_name"
    done

    echo -e "${GREEN}✓ All configs generated successfully!${NC}"
    echo ""

    # Ensure mako notification daemon is disabled (AGS handles notifications)
    echo -e "${YELLOW}→ Ensuring AGS notification service...${NC}"
    if systemctl --user list-unit-files mako.service &>/dev/null; then
        local mako_state
        mako_state=$(systemctl --user is-enabled mako.service 2>/dev/null || true)
        if [ "$mako_state" != "masked" ]; then
            systemctl --user stop mako.service 2>/dev/null || true
            systemctl --user disable mako.service 2>/dev/null || true
            systemctl --user mask mako.service 2>/dev/null || true
            echo -e "  ${GREEN}✓ Mako notification daemon masked${NC}"
        else
            echo -e "  ${GREEN}✓ Mako already masked${NC}"
        fi
    else
        echo -e "  ${GREEN}✓ Mako not installed (nothing to mask)${NC}"
    fi

    # Create D-Bus service file so org.freedesktop.Notifications activates AGS (not mako)
    local dbus_services_dir="$HOME/.local/share/dbus-1/services"
    local dbus_service_file="$dbus_services_dir/org.freedesktop.Notifications.service"
    mkdir -p "$dbus_services_dir"
    cat > "$dbus_service_file" <<DBUS_EOF
[D-BUS Service]
Name=org.freedesktop.Notifications
Exec=/usr/bin/ags run -d $ZEPOS_OUTPUT_ROOT/ags
DBUS_EOF
    # Remove old disabled mako service file if present
    rm -f "$dbus_services_dir/fr.emersion.mako.service.disabled" 2>/dev/null
    echo -e "  ${GREEN}✓ D-Bus notification service points to AGS${NC}"

    # Start/restart AGS (all widgets) - seamless restart via notification stub
    echo -e "${YELLOW}→ Starting AGS...${NC}"

    # Start notification stub FIRST - takes over D-Bus name from old AGS
    # This ensures org.freedesktop.Notifications is ALWAYS owned (no gap)
    python3 "$ZEPOS_SYSTEM_ROOT/helpers/notification-stub.py" >/dev/null 2>&1 &
    local STUB_PID=$!
    sleep 0.3  # Let stub claim the D-Bus name

    # Now kill old AGS - stub holds the name so no gap
    ags quit 2>/dev/null || pkill -f "gjs.*ags" 2>/dev/null
    local quit_attempts=0
    while [ $quit_attempts -lt 20 ]; do
        if ! pgrep -f "gjs.*ags" >/dev/null 2>&1; then
            break
        fi
        ((quit_attempts++))
        sleep 0.1
    done
    if pgrep -f "gjs.*ags" >/dev/null 2>&1; then
        pkill -9 -f "gjs.*ags" 2>/dev/null
        sleep 0.2
    fi

    # Start new AGS - it will claim the name, stub auto-exits.
    # The command is assembled here rather than written inline: single
    # quotes would keep $ZEPOS_OUTPUT_ROOT unexpanded and hand the
    # child a literal dollar sign to cd into.
    setsid bash -c "exec >/dev/null 2>&1; cd \"$ZEPOS_OUTPUT_ROOT/ags\" && ags run" &

    # Wait for AGS notification service to be ready on DBus
    local max_attempts=50
    local attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if dbus-send --session --dest=org.freedesktop.DBus --type=method_call \
            --print-reply /org/freedesktop/DBus org.freedesktop.DBus.ListNames 2>/dev/null \
            | grep -q "org.freedesktop.Notifications"; then
            if dbus-send --session --dest=org.freedesktop.Notifications --type=method_call \
                --print-reply /org/freedesktop/Notifications \
                org.freedesktop.Notifications.GetCapabilities >/dev/null 2>&1; then
                break
            fi
        fi
        ((attempt++))
        sleep 0.1
    done

    # Clean up notification stub (auto-exits when AGS claims name, but kill just in case)
    kill $STUB_PID 2>/dev/null
    wait $STUB_PID 2>/dev/null

    if [ $attempt -lt $max_attempts ]; then
        echo -e "  ${GREEN}✓ AGS started (notification service ready)${NC}"
    else
        echo -e "  ${YELLOW}✓ AGS started (notification service not confirmed)${NC}"
    fi

    # No clipboard daemon is started here, on purpose: the clipboard is
    # served by cliphist, which hyprland.conf starts with `wl-paste
    # --watch`, and by the HyprClipX plugin on SUPER+SHIFT+V. Neither is
    # a systemd unit and neither survives a `hyprctl reload`, so there is
    # nothing for a post-generation step to restart.

    return 0
}

# Show help
show_help() {
    echo "Usage: $0 -<config_name>"
    echo ""
    echo "Special options:"
    echo "  --all           Generate all configs"
    echo ""
    echo "Available configs:"
    list_template_names templates | sed 's/^/  -/'
    list_template_names styles | sed 's/^/  -/'
    list_template_names system | sed 's/^/  -/'
    echo ""
    echo "Example: $0 -ags-bar"
}

# Print error and exit
error_exit() {
    echo -e "${RED}Error: $1${NC}" >&2
    exit 1
}

# A staging area handed down by a --all run. Checked here rather than
# trusted: a ZEPOS_STAGE_DIR left over in a login shell would otherwise
# make every single run stage into it and publish nothing, while still
# reporting success.
if [ -n "$ZEPOS_STAGE_DIR" ] && [ ! -f "$ZEPOS_STAGE_DIR/.zepos-stage" ]; then
    error_exit "ZEPOS_STAGE_DIR=$ZEPOS_STAGE_DIR is not a ZepOS staging directory"
fi

# Main logic
if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

# Run only the post-generation step - the service restarts and the bar
# workspace merge - for a config that is already in place. A --all run
# publishes the whole run at once and then calls itself back this way, so
# nothing is restarted against a file that was never written.
POST_ONLY=false
if [ "$1" = "--post" ]; then
    POST_ONLY=true
    shift
    [ $# -eq 1 ] || error_exit "--post takes exactly one config name"
fi

# The user's settings, read once, before anything is generated.
#
# Every {{STYLE_*}} value comes out of that one file, so a file that
# exists and cannot be read is not a small problem: the style layer would
# answer every question from its own defaults instead, every placeholder
# would resolve, the checks would pass - they look for surviving
# placeholders, broken JSON, shell syntax errors and missing plugin
# objects, and defaults produce none of those - and the run would replace
# a configured machine with a fresh-install one while printing a success.
# Measured on a settings file truncated to 60 bytes: vpn-connect.sh went
# from a working VPN to ROUTED_NETWORKS="" and VPN_SERVER="".
#
# So the run refuses, before a staging area is even created. NO settings
# file is a different answer and a legitimate one - a fresh installation
# has none - and settings.py check says so by staying quiet about it.
#
# Asked by the process that OWNS the run: a child of a --all run inherits
# ZEPOS_STAGE_DIR, and without this it would repeat the same refusal once
# per template, seventy-seven times, burying the one line that says what
# to repair.
if [ "$POST_ONLY" != true ] && [ -z "$ZEPOS_STAGE_DIR" ]; then
    if ! ZEPOS_USER_ROOT="$ZEPOS_USER_ROOT" python3 "$ZEPOS_SYSTEM_ROOT/settings.py" check; then
        echo -e "${RED}✗ Nothing was generated.${NC}" >&2
        echo -e "${RED}  The previous configuration is unchanged.${NC}" >&2
        exit 1
    fi
fi

# Check for --all flag
if [ "$1" = "--all" ] || [ "$1" = "-all" ]; then
    generate_all_configs
    exit $?
fi

# Extract the config name from the argument
CONFIG_NAME="${1#-}"

# Determine the target config
case "$CONFIG_NAME" in
    kitty-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/kitty"
        CONFIG_FILE="kitty.conf"
        ;;
    date-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/scripts"
        CONFIG_FILE="date.sh"
        MAKE_EXECUTABLE=true
        ;;
    # One route for any number of extra clocks. There were two, one per
    # country, and a third country would have needed a third - see
    # src/templates/bar-clocks-config.template.
    bar-clocks-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/scripts"
        CONFIG_FILE="clocks.sh"
        MAKE_EXECUTABLE=true
        ;;
    # Die Eingabezeile. Hier stand bis zum 12.08.2026 starship-config,
    # das ~/.config/starship.toml schrieb - eine zweite, vollstaendige
    # Prompt-Konfiguration mit vier eigenen Farbliteralen (#00cc00,
    # #00ff00, #1a1a1a, #0c0c0c), die NIEMAND geladen hat: starship stand
    # in keiner Paketliste, und kein `starship init zsh` stand in
    # ~/.zshrc. Sie kam durch, weil tests/src/test_reference_resolution.py
    # sie unter READ_BY_CONVENTION mit "starship, via STARSHIP_CONFIG's
    # default" entschuldigte - ein Leser, den es auf keiner Installation
    # gab.
    p10k-config)
        CONFIG_DIR="$HOME"
        CONFIG_FILE=".p10k.zsh"
        ;;
    zshrc-config)
        CONFIG_DIR="$HOME"
        CONFIG_FILE=".zshrc"
        ;;
    hypr-shortcuts-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/scripts"
        CONFIG_FILE="hypr-shortcuts.py"
        MAKE_EXECUTABLE=true
        ;;
    hardware-monitor-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/scripts"
        CONFIG_FILE="hardware-monitor.py"
        MAKE_EXECUTABLE=true
        ;;
    # Der Sperrbildschirm, und er braucht NUR seinen Stil.
    #
    # Hier stand bis zum 12.08.2026 hyprlock-config, das
    # ~/.config/hypr/hyprlock.conf schrieb - eine Datei in hyprlocks
    # eigenem Format, mit hyprlocks eigenen Farbliteralen, weil hyprlock
    # kein GTK-Programm war und kein Stylesheet nehmen konnte. Das
    # Programm ist weg, die Route mit ihm.
    #
    # WARUM ES HIER KEIN GEGENSTUECK ZU logout-config GIBT
    #     zepos-logout liest zwei erzeugte Dateien, layout.json und
    #     style.css, weil sein Inhalt - sechs Aktionen mit Symbolen und
    #     Tastenkuerzeln - erzeugter Inhalt IST. Der Sperrbildschirm hat
    #     vier Zeilen, von denen drei Tatsachen der Maschine sind
    #     (Uhrzeit, Datum, Benutzer). Eine Layout-Datei dafuer waere eine
    #     Datei, ohne die SUPER+L nicht mehr sperrt, und das ist der eine
    #     Handel, den dieser Bildschirm nicht eingehen darf.
    lock-style)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/zepos-lock"
        CONFIG_FILE="style.css"
        ZEPOS_TEMPLATE_SUBDIR="styles"
        ;;
    logout-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/zepos-logout"
        # Mit Endung, im Gegensatz zu wlogouts "layout": src/
        # validate_output.py laesst jede erzeugte .json durch
        # json.loads() laufen, bevor sie veroeffentlicht wird. Ohne
        # Endung faende ein Tippfehler in der Vorlage niemand beim
        # Erzeugen - sondern der Nutzer beim Druecken von SUPER+M.
        CONFIG_FILE="layout.json"
        ;;
    logout-style)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/zepos-logout"
        CONFIG_FILE="style.css"
        ZEPOS_TEMPLATE_SUBDIR="styles"
        ;;
    gpg-agent-config)
        # Nicht unter ~/.config, weil gpg-agent dort nicht nachsieht:
        # gelesen wird ausschliesslich $GNUPGHOME/gpg-agent.conf, und
        # GNUPGHOME ist voreingestellt ~/.gnupg. Eine systemweite
        # Entsprechung gibt es nicht - /etc/gnupg/gpg-agent.conf liest
        # GnuPG 2.4 nicht -, also ist die Datei je Nutzer die einzige
        # Stelle, an der pinentry-program gesetzt werden kann.
        CONFIG_DIR="$HOME/.gnupg"
        CONFIG_DIR_MODE="0700"
        CONFIG_FILE="gpg-agent.conf"
        ZEPOS_TEMPLATE_SUBDIR="system"
        ;;
    zepos-privileges-config)
        CONFIG_DIR="$ZEPOS_USER_ROOT/system"
        # Ohne Punkt im Namen: sudo's #includedir ueberspringt jede Datei,
        # deren Name einen enthaelt - eine "zepos.conf" laege da und
        # wuerde schweigend nie gelesen.
        CONFIG_FILE="zepos"
        ZEPOS_TEMPLATE_SUBDIR="system"
        ;;
    zepos-menu-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/zepos-menu"
        CONFIG_FILE="config"
        ;;
    ncspot-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ncspot"
        CONFIG_FILE="config.toml"
        ;;
    zepos-menu-style)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/zepos-menu"
        CONFIG_FILE="style.css"
        ZEPOS_TEMPLATE_SUBDIR="styles"
        ;;
    # Die beiden eigenen Plugins mit einer Oberflaeche, je zwei Dateien
    # in ihrem eigenen Namensraum.
    #
    # WARUM NICHT NACH ~/.config/hypr
    #     Upstream las ~/.config/hypr/hyprlaunch.toml. Dort liegen
    #     hyprland.conf, plugins.conf und ein halbes
    #     Dutzend erzeugter Skripte; eine Datei mit einem fremden Format
    #     dazwischen ist eine, die beim naechsten Aufraeumen erwischt
    #     wird. Ein Namensraum je Programm ist ausserdem, was
    #     zepos-logout und zepos-menu schon machen - und beide Programme
    #     bauen ihren Pfad genauso, aus g_get_user_config_dir()
    #     beziehungsweise XDG_CONFIG_HOME.
    #
    # OHNE ENDUNG, wie bei zepos-menu-config: src/validate_output.py
    # laesst jede erzeugte .json und .sh durch einen Pruefer laufen, und
    # fuer dieses Format gibt es keinen. Eine erfundene Endung wuerde
    # nur behaupten, es gaebe einen.
    hyprlaunch-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/hyprlaunch"
        CONFIG_FILE="config"
        ;;
    hyprlaunch-style)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/hyprlaunch"
        CONFIG_FILE="style.css"
        ZEPOS_TEMPLATE_SUBDIR="styles"
        ;;
    hyprclipx-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/hyprclipx"
        CONFIG_FILE="config"
        ;;
    hyprclipx-style)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/hyprclipx"
        CONFIG_FILE="style.css"
        ZEPOS_TEMPLATE_SUBDIR="styles"
        ;;
    mako-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/mako"
        CONFIG_FILE="config"
        ;;
    hyprland-gaming-config|hyprland-work-office-config|hyprland-work-home-config)
        echo -e "${RED}DEPRECATED: replaced by the profile system.${NC}"
        echo ""
        echo "Use instead:"
        echo "  ./generate_config.sh -hyprland-universal-config"
        echo ""
        echo "And start Hyprland with:"
        echo "  start-hyprland <profile>   (list them with: list-profiles)"
        exit 1
        ;;
    random-wallpaper-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/hypr"
        CONFIG_FILE="random-wallpaper.sh"
        MAKE_EXECUTABLE=true
        ;;
    clean-config-cache-config)
        CONFIG_DIR="$ZEPOS_USER_ROOT/helpers"
        CONFIG_FILE="clean-config-cache.sh"
        MAKE_EXECUTABLE=true
        ;;
    backup-cleanup-config)
        CONFIG_DIR="$ZEPOS_USER_ROOT/helpers"
        CONFIG_FILE="backup-cleanup.sh"
        MAKE_EXECUTABLE=true
        ;;
    zepos-terminals-config)
        CONFIG_DIR="$ZEPOS_USER_ROOT/helpers"
        CONFIG_FILE="zepos-terminals.sh"
        MAKE_EXECUTABLE=true
        ;;
    hypr-monitor-detect-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/hypr"
        CONFIG_FILE="hypr-monitor-detect.sh"
        MAKE_EXECUTABLE=true
        ;;
    hypr-window-rescue-config)
        CONFIG_DIR="$ZEPOS_USER_ROOT/helpers"
        CONFIG_FILE="hypr-window-rescue.sh"
        MAKE_EXECUTABLE=true
        ;;
    hypr-emergency-reset-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/hypr"
        CONFIG_FILE="emergency-reset.sh"
        MAKE_EXECUTABLE=true
        ;;
    hyprland-status-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/hypr"
        CONFIG_FILE="hyprland-status"
        MAKE_EXECUTABLE=true
        ;;
    hyprland-failsafe-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/hypr"
        CONFIG_FILE="hyprland-failsafe.conf"
        ;;
    tty-monitor-rotation-config)
        CONFIG_DIR="$ZEPOS_USER_ROOT/helpers"
        CONFIG_FILE="tty-monitor-rotation.sh"
        MAKE_EXECUTABLE=true
        ;;
    tty-text-fix-config)
        # Beside tty-monitor-rotation.sh, which is what it repairs after:
        # the console keeps drawing at the old boundaries once the screen
        # has been rotated, and this resets it.
        #
        # It had no entry here at all and fell through to the generic
        # branch, which wrote it to ~/.config/tty-text-fix-config/config
        # - a bash script, without the executable bit, in a directory no
        # program reads, under a name that does not say it is a script.
        # Generated on every run since it was added and reachable by
        # nothing.
        CONFIG_DIR="$ZEPOS_USER_ROOT/helpers"
        CONFIG_FILE="tty-text-fix.sh"
        MAKE_EXECUTABLE=true
        ;;
    network-diagnostic-config)
        CONFIG_DIR="$ZEPOS_USER_ROOT/helpers"
        CONFIG_FILE="network-diagnostic.sh"
        MAKE_EXECUTABLE=true
        ;;
    network-watchdog-config)
        CONFIG_DIR="$ZEPOS_USER_ROOT/helpers"
        CONFIG_FILE="network-watchdog.sh"
        MAKE_EXECUTABLE=true
        ;;
    network-watchdog-service)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/systemd/user"
        CONFIG_FILE="network-watchdog.service"
        ;;
    ags-overlay-utils)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/utils"
        CONFIG_FILE="overlay.ts"
        ;;
    # Das Bauteil-Kit. Neben overlay.ts und i18n.ts der dritte Baustein
    # unter ags/utils/ - kein Fenster, sondern das, woraus Fenster
    # gebaut werden.
    ags-kit)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/utils"
        CONFIG_FILE="kit.ts"
        ;;
    # Die Uebersetzung. Ein Baustein wie overlay.ts und aus demselben
    # Grund dort: JEDES Widget importiert `_` daraus.
    ags-i18n)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/utils"
        CONFIG_FILE="i18n.ts"
        ;;
    # Der Hyprland-Klient und die Statusablage sind Bausteine, keine
    # Widgets: Bar.tsx und Dock.tsx importieren sie aus ../utils.
    ags-hyprland)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/utils"
        CONFIG_FILE="hyprland.ts"
        ;;
    ags-tray)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/utils"
        CONFIG_FILE="tray.ts"
        ;;
    ags-bar)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/widget"
        CONFIG_FILE="Bar.tsx"
        ;;
    ags-dock)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/widget"
        CONFIG_FILE="Dock.tsx"
        ;;
    # Der Stil der Leiste. Nicht style.scss, sondern eine zweite Datei,
    # die app.ts ueber app.apply_css() nachlaedt - siehe dort, und siehe
    # den Kopf von src/styles/bar-style.template.
    bar-style)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags"
        CONFIG_FILE="bar.css"
        ZEPOS_TEMPLATE_SUBDIR="styles"
        ;;
    # Fuenf Module, ein Aufruf. Siehe den Kopf der Vorlage.
    bar-status-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/scripts"
        CONFIG_FILE="status.sh"
        MAKE_EXECUTABLE=true
        ;;
    # Die drei Skripte der BEDINGTEN Module (Aufgabe #94). Sie stehen
    # neben status.sh und nicht darin, obwohl dessen Kopf einen guten
    # Grund fuer ein gemeinsames Skript nennt: "fuenf einzelne Skripte
    # im Zweisekundentakt waeren 150 Prozessstarts je Minute".
    #
    # Der Grund ist der TAKT, und ein gemeinsames Skript kann nur einen
    # haben - naemlich den schnellsten. status.sh laeuft alle zwei
    # Sekunden, weil eine Lautstaerke sich sofort zeigen muss.
    # updates.sh liest einen Zustand, den ein Zeitgeber taeglich
    # schreibt; im Zweisekundentakt waeren das 43199 Laeufe am Tag fuer
    # eine Angabe, die sich einmal aendert.
    #
    # Was die zwei schnellen kosten, ist gemessen (12.08.2026): der
    # /proc-Durchlauf von privacy.sh 6-9 ms bei 439 Prozessen,
    # playerctl fuer media.sh 4 ms.
    ags-privacy-scripts)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/scripts"
        CONFIG_FILE="privacy.sh"
        MAKE_EXECUTABLE=true
        ;;
    ags-media-scripts)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/scripts"
        CONFIG_FILE="media.sh"
        MAKE_EXECUTABLE=true
        ;;
    ags-updates-scripts)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/scripts"
        CONFIG_FILE="updates.sh"
        MAKE_EXECUTABLE=true
        ;;
    ags-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags"
        CONFIG_FILE="app.ts"
        ;;
    ags-vpn)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/widget"
        CONFIG_FILE="VpnManager.tsx"
        ;;
    ags-vpn-settings)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/widget"
        CONFIG_FILE="VpnSettings.tsx"
        ;;
    ags-style)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags"
        CONFIG_FILE="style.scss"
        ;;
    ags-notifications)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/widget"
        CONFIG_FILE="Notifications.tsx"
        ;;
    ags-calendar)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/widget"
        CONFIG_FILE="Calendar.tsx"
        ;;
    ags-shortcuts)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/widget"
        CONFIG_FILE="Shortcuts.tsx"
        ;;
    ags-battery)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/widget"
        CONFIG_FILE="Battery.tsx"
        ;;
    ags-disk)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/widget"
        CONFIG_FILE="DiskUsage.tsx"
        ;;
    ags-control-center)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/widget"
        CONFIG_FILE="ControlCenter.tsx"
        ;;
    ags-network)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/widget"
        CONFIG_FILE="NetworkManager.tsx"
        ;;
    # Seit dem 17.08.2026. Es ist das Fenster, das der Klick auf das
    # Bluetooth-Modul der Leiste oeffnet - bis dahin startete der ein
    # blueman-manager, also einen GTK3-Prozess neben der Sitzung.
    ags-bluetooth)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/widget"
        CONFIG_FILE="BluetoothManager.tsx"
        ;;
    ags-wallpaper)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/widget"
        CONFIG_FILE="WallpaperSelector.tsx"
        ;;
    ags-style-editor)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/widget"
        CONFIG_FILE="StyleEditor.tsx"
        ;;
    ags-network-scripts)
        CONFIG_DIR="$HOME/.local/bin"
        CONFIG_FILE="ags-network-scripts"
        MAKE_EXECUTABLE=true
        ;;
    gtk-theme-fix-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/hypr"
        CONFIG_FILE="gtk-theme-fix.sh"
        MAKE_EXECUTABLE=true
        ;;
    monitor-color-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/hypr"
        CONFIG_FILE="monitor-color.sh"
        MAKE_EXECUTABLE=true
        ;;
    cliphist-menu-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/hypr"
        CONFIG_FILE="cliphist-menu.sh"
        MAKE_EXECUTABLE=true
        ;;
    wireplumber-config)
        # Straight into WirePlumber's own drop-in directory, which is
        # where the template's header has always said this file belongs.
        #
        # It used to be written to $ZEPOS_USER_ROOT/profiles/gaming/ and
        # copied from there by start-hyprland on a profile switch. That
        # gate made sense while the file carried one person's headset and
        # microphone by USB product string - it was one desk's file, so
        # it was kept behind one desk's profile. Since the contents come
        # from the user settings (audio.default_sink, .default_source,
        # .blocked_sources) there is one answer per MACHINE and no reason
        # to ask it per profile: a profile here is a monitor layout, and
        # save-profile stores exactly that plus env, autostart, keybinds
        # and windowrules - never a sound device.
        #
        # Measured before it was changed: `--all` created a "gaming"
        # directory under the user root's profiles/, holding these two
        # files and nothing else, on every installation. list-profiles
        # then advertised "gaming (missing monitors.conf)" - ZepOS ships
        # laptop and desktop - and `start-hyprland gaming` printed five
        # `cp: cannot stat` lines, wrote "gaming" into current-profile
        # and launched the session anyway. Meanwhile a user on any other
        # profile got no audio configuration at all, so every
        # `zepos-settings set audio.*` they made was inert.
        #
        # 99- keeps the fragment last, which is what makes it an
        # override; the name says who wrote it and what it is.
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/wireplumber/wireplumber.conf.d"
        CONFIG_FILE="99-zepos-audio.conf"
        ;;
    easyeffects-config)
        # Global for the same reason as the WirePlumber fragment above,
        # and into the location EasyEffects itself reads.
        #
        # The file is KConfig INI, not a format of ours: EasyEffects 8 -
        # the version Arch ships - is the Qt6/QML rewrite and depends on
        # kconfigwidgets, kirigami and
        # qqc2-desktop-style. That is also what the kdeglobals and
        # BreezeDark.colors below exist for; a GTK application would read
        # neither.
        #
        # Which answers the question the template's sibling could not:
        # measured against kconfig 6.27, a `#` comment header is READ
        # without complaint - every key still resolves - and is dropped
        # the first time the application saves, because KConfig rewrites
        # the file from its entry map. So a "DO NOT EDIT DIRECTLY" banner
        # here would not break anything; it would silently disappear and
        # leave the file looking hand-written. That is why this template,
        # alone among ours, carries no header.
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/easyeffects/db"
        CONFIG_FILE="easyeffectsrc"
        ;;
    gtk4-settings-config)
        # Die GROESSE fuer fremde GTK4-Fenster, neben den Farben
        # darunter. Derselbe Pfad und derselbe Grund: gtk-4.0/ ist das
        # Verzeichnis, in dem die Bibliothek sucht, und settings.ini der
        # Name, unter dem sie es tut.
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/gtk-4.0"
        CONFIG_FILE="settings.ini"
        ;;
    gtk4-colors-config)
        # Die benannten Farben von libadwaita, aus src/brand.py. Jede
        # Anwendung aus packaging/zepos-apps liest diese Datei beim
        # Start; sie ist der ganze Grund, aus dem ein fremdes Fenster auf
        # diesem Schreibtisch nicht grau ist.
        #
        # Der Pfad ist GTK4s eigener und nicht verhandelbar - gtk-4.0/
        # ist das Verzeichnis, in dem die Bibliothek sucht, und ein
        # anderer Name waere eine Datei, die niemand liest.
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/gtk-4.0"
        CONFIG_FILE="gtk.css"
        ;;
    kdeglobals-config)
        # Kirigami/KColorScheme SSOT - the theme manager's source for the
        # Qt6/QtQuick applications on this desktop, EasyEffects 8 being
        # the one this project configures itself.
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT"
        CONFIG_FILE="kdeglobals"
        ;;
    breezedark-colors-config)
        # KColorScheme file of the dark variant. The name has to be
        # BreezeDark - that is the default Kirigami applications look for.
        # Contents derived from KvDark.colors.
        CONFIG_DIR="$HOME/.local/share/color-schemes"
        CONFIG_FILE="BreezeDark.colors"
        ;;
    bar-workspace-detect-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags"
        CONFIG_FILE="bar-workspace-detect.sh"
        MAKE_EXECUTABLE=true
        ;;
    terminal-green-style)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/sublime-text/Packages/User"
        CONFIG_FILE="Terminal Green.sublime-color-scheme"
        MAKE_EXECUTABLE=false
        ZEPOS_TEMPLATE_SUBDIR="styles"
        ;;
    vpn-control-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/scripts"
        CONFIG_FILE="vpn-control.sh"
        MAKE_EXECUTABLE=true
        ;;
    vpn-connect-script)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/scripts"
        CONFIG_FILE="vpn-connect.sh"
        MAKE_EXECUTABLE=true
        ;;
    vpn-watcher-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/scripts"
        CONFIG_FILE="vpn-watcher.sh"
        MAKE_EXECUTABLE=true
        ;;
    floating-center-desktop)
        CONFIG_DIR="$HOME/.local/share/applications"
        CONFIG_FILE="floating-center.desktop"
        # Create directory if it doesn't exist
        mkdir -p "$CONFIG_DIR"
        ;;
    printer-manager-config)
        # Der generische Ersatz für die drei gerätegebundenen
        # Druckerskripte. Landet neben den anderen Nutzerwerkzeugen in
        # ~/.local/bin, weil er von Hand und aus Tastenkombinationen
        # heraus aufgerufen wird, nicht von der Leiste.
        CONFIG_DIR="$HOME/.local/bin"
        CONFIG_FILE="printer-manager"
        MAKE_EXECUTABLE=true
        ;;
    bar-weather-config)
        # Ein Leistenmodul, also zu den anderen Modulskripten. Ohne
        # eingestellten Ort gibt es eine leere Zeile aus und fragt
        # niemanden - erzeugt wird es trotzdem, sonst müsste der Nutzer
        # nach dem Eintragen des Ortes wissen, dass er hier noch etwas
        # zu erzeugen hat.
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/scripts"
        CONFIG_FILE="weather.sh"
        MAKE_EXECUTABLE=true
        ;;
    floating-window-manager)
        CONFIG_DIR="$HOME/.local/bin"
        CONFIG_FILE="floating-window-manager"
        MAKE_EXECUTABLE=true
        ;;
    floating-layouts-bar)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/scripts"
        CONFIG_FILE="floating-layouts-bar.sh"
        MAKE_EXECUTABLE=true
        ;;
    helpers-bar)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/scripts"
        CONFIG_FILE="helpers-bar.py"
        MAKE_EXECUTABLE=true
        ;;
    grid-wallpaper-toggle)
        CONFIG_DIR="$HOME/.local/bin"
        CONFIG_FILE="grid-wallpaper-toggle"
        MAKE_EXECUTABLE=true
        ;;
    grid-wallpaper-toggle-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/hypr"
        CONFIG_FILE="grid-wallpaper-toggle-config.sh"
        ;;
    grid-wallpaper-toggle-style)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/hypr"
        CONFIG_FILE="grid-wallpaper-style.css"
        ZEPOS_TEMPLATE_SUBDIR="styles"
        ;;
    start-hyprland-office-config|start-hyprland-gaming-config)
        echo -e "${RED}DEPRECATED: replaced by 'start-hyprland'.${NC}"
        echo ""
        echo "Use instead:"
        echo "  ./generate_config.sh -start-hyprland-config"
        echo ""
        echo "And start with:"
        echo "  start-hyprland <profile>"
        exit 1
        ;;
    start-hyprland-home-config)
        echo -e "${RED}DEPRECATED: replaced by 'start-hyprland'.${NC}"
        echo "Use: ./generate_config.sh -start-hyprland-config"
        exit 1
        ;;
    restore-latest-backup-config)
        CONFIG_DIR="$HOME/.local/bin"
        CONFIG_FILE="restore-latest-backup"
        MAKE_EXECUTABLE=true
        ;;
    hyprland-universal-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/hypr"
        CONFIG_FILE="hyprland.conf"
        ;;
    # Alles, was ein GELADENES Plugin voraussetzt: die plugin=-Zeilen,
    # die plugin{}-Bloecke und die Tastenbelegungen mit
    # Plugin-Dispatcher. hyprland.conf sourced die Datei; welcher Block
    # darin landet, entscheidet plugins.py am vorhandenen .so - siehe
    # den Filterschritt weiter unten und Spec §7.4.
    hyprland-plugins-config)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/hypr"
        CONFIG_FILE="plugins.conf"
        ;;
    start-hyprland-config)
        CONFIG_DIR="$HOME/.local/bin"
        CONFIG_FILE="start-hyprland"
        MAKE_EXECUTABLE=true
        ;;
    save-profile-config)
        CONFIG_DIR="$HOME/.local/bin"
        CONFIG_FILE="save-profile"
        MAKE_EXECUTABLE=true
        ;;
    list-profiles-config)
        CONFIG_DIR="$HOME/.local/bin"
        CONFIG_FILE="list-profiles"
        MAKE_EXECUTABLE=true
        ;;
    network-manager-gui-config)
        CONFIG_DIR="$HOME/.local/bin"
        CONFIG_FILE="network-manager-gui"
        MAKE_EXECUTABLE=true
        ;;
    wallpaper-manager-config)
        CONFIG_DIR="$HOME/.local/bin"
        CONFIG_FILE="wallpaper-manager"
        MAKE_EXECUTABLE=true
        ;;
    hyprbars-toggle-config)
        CONFIG_DIR="$HOME/.local/bin"
        CONFIG_FILE="hyprbars-toggle"
        MAKE_EXECUTABLE=true
        ;;
    */*|.*|"")
        # The fallback below drops CONFIG_NAME straight into a path that
        # mkdir -p then creates. Without this guard a name carrying a
        # slash - "-../foo" - builds a directory OUTSIDE the output root,
        # silently, from an argument nothing validated. Rejected on the
        # same grounds as in paths.py: with "/" and a leading "." ruled
        # out, what is left can only be one ordinary path component.
        error_exit "Invalid config name: $CONFIG_NAME"
        ;;
    *)
        # Fallback: config in a folder of the same name
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/$CONFIG_NAME"
        CONFIG_FILE="config"
        ;;
esac

# The staging area mirrors absolute paths, and the publish step maps them
# back by stripping the mirror's root. A relative CONFIG_DIR would stage
# somewhere that cannot be mapped back at all.
case "$CONFIG_DIR" in
    /*) ;;
    *)  CONFIG_DIR="$PWD/$CONFIG_DIR" ;;
esac

# Full path to the generated config
FULL_CONFIG_PATH="$CONFIG_DIR/$CONFIG_FILE"

if [ "$POST_ONLY" != true ]; then
    # Resolve the template AFTER the case statement, which is where a style
    # config gets the chance to point at the styles directory.
    TEMPLATE_FILE="$(find_template "$CONFIG_NAME" "$ZEPOS_TEMPLATE_SUBDIR")" || error_exit \
        "Template not found: $CONFIG_NAME (looked in $ZEPOS_USER_ROOT/$ZEPOS_TEMPLATE_SUBDIR and $ZEPOS_SYSTEM_ROOT/$ZEPOS_TEMPLATE_SUBDIR)"

    # Check whether the config directory exists
    #
    # CONFIG_DIR_MODE ist fuer das eine Verzeichnis, dem seine Rechte
    # nicht gleichgueltig sind: ~/.gnupg. GnuPG prueft sie bei jedem
    # Start und meldet "unsafe permissions on homedir" - eine Warnung,
    # die weiterlaeuft und die ZepOS dann selbst verursacht haette, weil
    # `mkdir -p` das Verzeichnis mit der umask des Nutzers anlegt und die
    # ueblichen 0755 sind. Ueberall sonst leer, dann bleibt es bei der
    # umask, was fuer ~/.config richtig ist.
    if [ ! -d "$CONFIG_DIR" ]; then
        mkdir -p "$CONFIG_DIR" || error_exit "Could not create directory: $CONFIG_DIR"
        if [ -n "${CONFIG_DIR_MODE:-}" ]; then
            chmod "$CONFIG_DIR_MODE" "$CONFIG_DIR" || error_exit \
                "Could not set mode $CONFIG_DIR_MODE on $CONFIG_DIR"
        fi
    fi

    # A single-config run opens its own staging area; a --all run handed
    # one down, and the check above has already confirmed it is one.
    if [ -z "$ZEPOS_STAGE_DIR" ]; then
        ZEPOS_STAGE_DIR="$(new_stage)" || error_exit "Could not create a staging directory"
        STAGE_OWNER=true
    fi

    STAGED_FILE="$ZEPOS_STAGE_DIR/files$FULL_CONFIG_PATH"
    mkdir -p "$(dirname "$STAGED_FILE")" || error_exit \
        "Could not create staging directory for $FULL_CONFIG_PATH"

    # Generate the config into the staging area, never into the live one.
    #
    # The system root travels along in the environment because the processor
    # substitutes {{ZEPOS_SYSTEM_ROOT}}: a generated script lands in
    # ~/.local/bin or ~/.config/ags/scripts and cannot work out which
    # package it came from, so the value is baked in here instead of left as
    # a default the artifact would have to guess. Passed for THIS call only -
    # exporting it into a login shell is what paths.py warns against, because
    # it would then silently redirect every template lookup afterwards.
    echo -e "${GREEN}→ Generating config from template...${NC}"
    ZEPOS_SYSTEM_ROOT="$ZEPOS_SYSTEM_ROOT" "${PYTHON_CMD[@]}" apply "$TEMPLATE_FILE" -o "$STAGED_FILE" || {
        rm -f "$STAGED_FILE"
        # Nothing usable was staged, so there is nothing to inspect. A
        # --all run keeps its own area: the files generated before this
        # one are in it.
        [ "$STAGE_OWNER" = true ] && rm -rf "$ZEPOS_STAGE_DIR"
        error_exit "Generation failed"
    }

    # The plugin include, resolved against THIS machine.
    #
    # After the template processor and not instead of it: the hyprbars
    # block carries {{STYLE_*}} and {{ICON_*}}, so a block has to be
    # finished configuration before it can be kept or dropped. plugins.py
    # writes the plugin= line itself, so the path in the file is by
    # construction the path it just found - see its header for why the
    # question is answered here and not at session start.
    if [ "$CONFIG_NAME" = "hyprland-plugins-config" ]; then
        echo -e "${GREEN}→ Resolving plugin objects...${NC}"
        python3 "$ZEPOS_SYSTEM_ROOT/plugins.py" filter "$STAGED_FILE" || {
            rm -f "$STAGED_FILE"
            [ "$STAGE_OWNER" = true ] && rm -rf "$ZEPOS_STAGE_DIR"
            error_exit "Plugin include could not be resolved"
        }
    fi

    # Die angehefteten Anwendungen des Docks, aus der ausgelieferten
    # Auswahl.
    #
    # Dieselbe Stelle und derselbe Grund wie eine Zeile weiter oben: die
    # Auswahl ist eine Angabe ueber diese Maschine und kein Platzhalter,
    # den ein SSOT beantworten koennte. Ein Fehlschlag hier bricht den
    # Lauf ab, statt ein Dock ohne Anwendungen zu veroeffentlichen - das
    # waere genau der Zustand, den der Nutzer am 11.08.2026 als "es fehlt
    # gefuehlt alles" gemeldet hat, und er waere still.
    if [ "$CONFIG_NAME" = "ags-dock" ]; then
        echo -e "${GREEN}→ Resolving pinned applications...${NC}"
        ZEPOS_SYSTEM_ROOT="$ZEPOS_SYSTEM_ROOT" python3 "$ZEPOS_SYSTEM_ROOT/apps.py" filter "$STAGED_FILE" || {
            rm -f "$STAGED_FILE"
            [ "$STAGE_OWNER" = true ] && rm -rf "$ZEPOS_STAGE_DIR"
            error_exit "Pinned applications could not be resolved"
        }
    fi

    # Set on the STAGED file: the publish step moves the file itself, so
    # the mode travels with it to the target.
    if [ "$MAKE_EXECUTABLE" = true ]; then
        chmod +x "$STAGED_FILE" || error_exit "Could not make $FULL_CONFIG_PATH executable"
    fi

    if [ "$STAGE_OWNER" != true ]; then
        # A --all run owns the staging area. It checks the whole run,
        # publishes it in one go and calls the post-generation step back
        # afterwards, so there is nothing left to do here.
        echo -e "${GREEN}✓ Staged: $FULL_CONFIG_PATH${NC}"
        exit 0
    fi

    publish_stage "$ZEPOS_STAGE_DIR" || exit 1

    if [ "$MAKE_EXECUTABLE" = true ]; then
        echo -e "${GREEN}✓ Made executable: $FULL_CONFIG_PATH${NC}"
    fi

    echo -e "${GREEN}✓ Config successfully generated: $FULL_CONFIG_PATH${NC}"
fi

# Restart the service
case "$CONFIG_NAME" in
    bar-workspace-detect-config)
        # Die Arbeitsbereiche des Schreibtischs, hier und nicht in einem
        # Nachlauf der Leiste.
        #
        # Hier stand ein jq-Aufruf, der zwei Schluessel aus
        # waybar-workspaces.conf in config.jsonc hineinschrieb, nachdem
        # die Leistenkonfiguration erzeugt worden war - eine erzeugte
        # Datei, die eine zweite erzeugte Datei nachtraeglich aendert.
        # Genau daran ist die doppelte Schreibweise
        # persistent_workspaces/persistent-workspaces entstanden: die
        # Vorlage schrieb die eine, der Merge die andere, und beide
        # standen in der ausgelieferten Datei.
        #
        # Die AGS-Leiste liest ~/.config/ags/workspaces.json beim
        # Aufbauen selbst. Damit gibt es keinen Merge mehr, sondern zwei
        # Dateien, von denen jede einen Erzeuger hat.
        if [ -x "$FULL_CONFIG_PATH" ]; then
            echo -e "${GREEN}→ Generating workspace configuration...${NC}"
            "$FULL_CONFIG_PATH" > /dev/null 2>&1 || true
        fi
        ;;
    p10k-config)
        echo -e "${GREEN}✓ Prompt (powerlevel10k) config updated${NC}"
        echo -e "${YELLOW}Info: Run 'source ~/.p10k.zsh' or restart your terminal${NC}"
        ;;
    zshrc-config)
        echo -e "${GREEN}✓ Zsh config updated${NC}"
        echo -e "${YELLOW}Info: Run 'source ~/.zshrc' or restart your terminal${NC}"
        ;;
    hyprland-universal-config)
        # One placeholder for every file hyprland.conf sources and no
        # template produces. They are filled in later by save-profile and
        # start-hyprland; until then they have to EXIST, because a
        # source= line that matches nothing is not skipped - Hyprland
        # answers it with "source= globbing error: found no match" and
        # stops reading that line, on the first `hyprctl reload` after a
        # fresh installation.
        #
        # profile-windowrules.conf was missing from this list while
        # hyprland.conf sourced it and start-hyprland touched it, so the
        # error appeared on exactly the installations that had never run
        # start-hyprland yet. The list is now kept in step with the
        # source= lines by tests/src/test_reference_resolution.py rather
        # than by hand.
        HYPR_DIR="$ZEPOS_OUTPUT_ROOT/hypr"
        echo -e "${GREEN}→ Ensuring placeholder files exist...${NC}"

        # keyboard.conf joined this list on 17.08.2026. It is filled in
        # by zepos-session rather than by save-profile, and its empty
        # state is the right one: with no `input` block in it, the
        # kb_layout the template ships stands. The FIRST login writes the
        # layout this machine was installed with - see the block "Die
        # Tastaturbelegung des Desktops" in src/bin/zepos-session.
        for placeholder in monitors.conf workspaces.conf workspaces-generated.conf profile-env.conf profile-autostart.conf profile-keybinds.conf profile-windowrules.conf keyboard.conf; do
            if [ ! -f "$HYPR_DIR/$placeholder" ]; then
                echo -e "${YELLOW}→ Creating placeholder: $HYPR_DIR/$placeholder${NC}"
                echo "# Placeholder - will be populated by save-profile/start-hyprland/zepos-session" > "$HYPR_DIR/$placeholder"
            fi
        done

        # plugins.conf is NOT in that loop, because it is not a
        # placeholder: -hyprland-plugins-config generates it, and every
        # --all run does. What it shares with the seven above is that
        # hyprland.conf sources it unconditionally, so a machine that has
        # only ever run -hyprland-universal-config - which is exactly
        # what start-hyprland does before the first login - must not meet
        # the globbing error. An empty file is the failsafe state anyway:
        # no plugin loaded, session up.
        if [ ! -f "$HYPR_DIR/plugins.conf" ]; then
            echo -e "${YELLOW}→ Creating placeholder: $HYPR_DIR/plugins.conf${NC}"
            {
                echo "# Noch nicht erzeugt. Kein Plugin ist geladen; die Sitzung startet."
                echo "# Mit \`zepos-generate -hyprland-plugins-config\` (oder --all) fuellen."
            } > "$HYPR_DIR/plugins.conf"
        fi

        echo -e "${YELLOW}Info: Run 'hyprctl reload' to reload Hyprland config${NC}"
        echo -e "${YELLOW}Info: Arrange the screens in Systemeinstellungen > Bildschirme, then save-profile <name>${NC}"
        ;;
    hyprland*-config)
        echo -e "${YELLOW}Info: Run 'hyprctl reload' to reload Hyprland config${NC}"
        ;;
esac