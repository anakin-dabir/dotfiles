#!/bin/sh

_write "$HOME/.config/bspwm/bars/colors.ini" << EOF
;; Colors generated for the ${RICE} theme.
[color]
bg = ${bg_alpha:-$bg}
bg-alt = $bg_alt
fg = $fg
pill = $accent_color
trans = $trans

black = $black
red = $red
green = $green
yellow = $yellow
blue = $blue
magenta = $magenta
cyan = $cyan
white = $white
black-bright = $blackb
red-bright = $redb
green-bright = $greenb
yellow-bright = $yellowb
blue-bright = $blueb
magenta-bright = $magentab
cyan-bright = $cyanb
white-bright = $whiteb

purple = $purple
pink = $pink
lime = $lime
amber = $amber
orange = $orange
grey = $grey
indigo = $indigo
blue-gray = $bluegray
blue-arch = $arch_icon
EOF

# The rice's accent: its focused-window border colour (#AARRGGBB -> #RRGGBB).
# The eww bars colour the notification bell with it when there's something unread.
_bar_accent=$(printf '%s' "${FOCUSED_BC:-$blue}" | sed 's/^#..\([0-9A-Fa-f]\{6\}\)$/#\1/')

_write "$HOME/.config/bspwm/bars/colors.scss" << EOF
\$bg: ${bg_alpha_css:-$bg};
\$accent: ${_bar_accent};
\$bg-alt: $bg_alt;
\$fg: $fg;
\$pill: $accent_color;
\$trans: $trans;

\$black: $black;
\$red: $red;
\$green: $green;
\$yellow: $yellow;
\$blue: $blue;
\$magenta: $magenta;
\$cyan: $cyan;
\$white: $white;
\$black-bright: $blackb;
\$red-bright: $redb;
\$green-bright: $greenb;
\$yellow-bright: $yellowb;
\$blue-bright: $blueb;
\$magenta-bright: $magentab;
\$cyan-bright: $cyanb;
\$white-bright: $whiteb;

\$purple: $purple;
\$pink: $pink;
\$lime: $lime;
\$amber: $amber;
\$orange: $orange;
\$grey: $grey;
\$indigo: $indigo;
\$blue-gray: $bluegray;
\$blue-arch: $arch_icon;
EOF
