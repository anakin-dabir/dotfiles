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
EOF
