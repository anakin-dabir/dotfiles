#!/bin/sh
# =============================================================
# Date:   10.11.2025
# Info:   This file will configure and launch the rice.
#
# Copyright (C) 2021-2026 gh0stzk <z0mbi3.zk@protonmail.com>
# Licensed under GPL-3.0 license
# =============================================================

# Current Rice
read -r RICE < "$HOME"/.config/bspwm/.rice
# Load theme configuration
. "$HOME"/.config/bspwm/rices/"$RICE"/theme-config.bash

# Accent from the wallpaper (Control Center > Customize > Colors), on top of
# the theme's own: window borders, menus, dropdowns and the bar's icons
_wall_accent=""
if [ "${WALL_ACCENT:-off}" = on ]; then
    _wall_accent=$("$HOME/.config/bspwm/bin/WallAccent" 2>/dev/null)
    if [ -n "$_wall_accent" ]; then
        FOCUSED_BC="$_wall_accent"
        rofi_selected="${_wall_accent}F0"
    fi
fi
# Path to modules dir
MODULE_DIR="$HOME/.config/bspwm/config/modules"

# Function to wait for processes to finish correctly
wait_for_termination() {
    local process_name
    process_name="$1"
    while pgrep -f "$process_name" >/dev/null; do
        sleep 0.3
    done
}

# Kill polybar or eww bars when you switch from the current theme to another
if pgrep -x polybar >/dev/null 2>&1; then
    polybar-msg cmd quit >/dev/null 2>&1
    # Force-kill bars that ignore the IPC quit, then wait on the exact process
    # name: `pgrep -f polybar` also matches unrelated commands that merely
    # mention polybar (e.g. `Updates --sync-polybar`) and would never finish.
    sleep 0.3
    pkill -x polybar 2>/dev/null
    while pgrep -x polybar >/dev/null; do sleep 0.1; done
else
    if pkill -f "eww.*bar" >/dev/null 2>&1; then
        wait_for_termination "eww.*bar"
    fi
fi
# Not exact-match: bar18's watcher subscribes to several events at once.
if pkill -f "bspc subscribe node_state" >/dev/null 2>&1; then
    wait_for_termination "bspc subscribe node_state"
fi

# Kill animated wallpaper if is active
if pkill xwinwrap >/dev/null 2>&1; then
    wait_for_termination xwinwrap
fi

# Kill wallpaper refresh loop
if [ -f /tmp/wall_refresh.pid ]; then
    kill "$(cat /tmp/wall_refresh.pid)" 2>/dev/null
    rm -f /tmp/wall_refresh.pid
fi

# Write data atomically, avoiding partial writes and file corruption.
_write() {
    local target dir tmp
    target=$1
    dir=$(dirname "$target")
    tmp=$(mktemp "$dir/.tmp.XXXXXX") || return 1

    cat >"$tmp" || {
        rm -f "$tmp"
        return 1
    }

    mv -f "$tmp" "$target" || {
        rm -f "$tmp"
        return 1
    }
}

# Load all the modules
for module in "$MODULE_DIR"/*.sh; do
    [ -e "$module" ] || continue
    if [ -n "$_wall_accent" ] && [ "${module##*/}" = 02-bar.sh ]; then
        # the bar's icons take the accent too (only the bar: terminals keep their blue)
        _theme_blue=$blue; blue=$_wall_accent; . "$module"; blue=$_theme_blue
    else
        . "$module"
    fi
done
unset module

# Finally load the bar
. "$HOME"/.config/bspwm/bars/"$main_bar"/Bar.bash

# The dock keeps its space (the theme just set the window padding again)
"$HOME/.config/bspwm/bin/Dock" &
