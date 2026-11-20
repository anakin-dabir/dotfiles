#!/bin/sh

# Notification center panel shape: same corners, border and font as the
# rice's dunst popups (see dunst_* in theme-config.bash).
_nc_radius=${dunst_corner_radius:-14}
_nc_card_radius=$(( _nc_radius > 4 ? _nc_radius - 4 : 0 ))
[ "$_nc_radius" -eq 0 ] && _nc_pill_radius=0 || _nc_pill_radius=999
_nc_font=$(printf '%s' "${dunst_font:-Adwaita Sans 10}" | sed 's/ *[0-9.]*$//')
if [ "${dunst_border:-0}" -gt 0 ]; then
    _nc_border="${dunst_border}px solid ${dunst_frame_color:-$fg}"
else
    _nc_border="1px solid rgba(${fg}, 0.10)"
fi

# Accent: the rice's focused-window border color, its signature color.
# Text on top of it is dark or white, whichever reads better.
_nc_accent=${FOCUSED_BC:-$blue}
_nc_hex=$(printf '%s' "$_nc_accent" | sed 's/^#//; s/^\(..\)\(......\)$/\2/')   # drop alpha of #AARRGGBB
if printf '%s' "$_nc_hex" | grep -qE '^[0-9A-Fa-f]{6}$'; then
    _nc_lum=$(printf '%s' "$_nc_hex" | awk '{ printf "%d", (299 * strtonum("0x" substr($0, 1, 2)) + 587 * strtonum("0x" substr($0, 3, 2)) + 114 * strtonum("0x" substr($0, 5, 2))) / 1000 }')
else
    _nc_accent=$blue; _nc_lum=0
fi
[ "$_nc_lum" -gt 165 ] && _nc_on_accent="#111111" || _nc_on_accent="#ffffff"

_write "$HOME/.config/bspwm/eww/colors.scss" << EOF
\$bg: ${bg};
\$bg-alt: ${accent_color};
\$fg: ${fg};
\$black: ${blackb};
\$red: ${red};
\$green: ${green};
\$yellow: ${yellow};
\$blue: ${blue};
\$magenta: ${magenta};
\$cyan: ${cyan};
\$archicon: ${arch_icon};

// Notification center
\$nc-radius: ${_nc_radius}px;
\$nc-card-radius: ${_nc_card_radius}px;
\$nc-pill-radius: ${_nc_pill_radius}px;
\$nc-border: ${_nc_border};
\$nc-theme-font: "${_nc_font}";
\$nc-accent: ${_nc_accent};
\$nc-on-accent: ${_nc_on_accent};
EOF
