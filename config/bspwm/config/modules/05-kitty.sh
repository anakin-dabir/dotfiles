#!/bin/sh

# Opacity (added if kitty.conf doesn't have the line yet); dynamic_background_opacity
# lets windows that are already open change too
_kconf="$HOME/.config/kitty/kitty.conf"
if grep -q '^background_opacity ' "$_kconf"; then
    sed -i "s|^background_opacity .*|background_opacity ${P_TERM_OPACITY}|" "$_kconf"
else
    printf '\nbackground_opacity %s\n' "${P_TERM_OPACITY}" >> "$_kconf"
fi
grep -q '^dynamic_background_opacity ' "$_kconf" || printf 'dynamic_background_opacity yes\n' >> "$_kconf"

# The theme's accent (#AARRGGBB -> #RRGGBB): cursor, selection, links, active border
_term_accent=$(printf '%s' "${FOCUSED_BC:-$blue}" | sed 's/^#..\([0-9A-Fa-f]\{6\}\)$/#\1/')

_write "$HOME/.config/kitty/current-theme.conf" << EOF
# Colors generated for ${RICE} theme.

# The basic colors
foreground              ${fg}
background              ${bg}
selection_foreground    ${bg}
selection_background    ${_term_accent}

# Cursor colors
cursor                  ${_term_accent}
cursor_text_color       ${bg}

# URL underline color when hovering with mouse
url_color               ${_term_accent}

# Kitty window border colors
active_border_color     ${_term_accent}
inactive_border_color   ${blackb}
bell_border_color       ${yellow}

# Tab bar colors
tab_bar_margin_color    ${bg}
active_tab_foreground   ${fg}
active_tab_background   ${black}
inactive_tab_foreground ${bg}
inactive_tab_background ${magenta}
tab_bar_background      ${bg}

# The 16 terminal colors

# black
color0 ${black}
color8 ${blackb}

# red
color1 ${red}
color9 ${redb}

# green
color2  ${green}
color10 ${greenb}

# yellow
color3  ${yellow}
color11 ${yellowb}

# blue
color4  ${blue}
color12 ${blueb}

# magenta
color5  ${magenta}
color13 ${magentab}

# cyan
color6  ${cyan}
color14 ${cyanb}

# white
color7  ${white}
color15 ${whiteb}

EOF

# Kitty
pkill -USR1 -x kitty
