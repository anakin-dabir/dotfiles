#############################
#   Cupertino Theme
#   macOS-style layout: menubar + dock.
#   Uses WhiteSur (GPL, community) — not Apple assets.
#############################

bg="#1C1C1E"
fg="#F5F5F7"
bg_alt="#2C2C2E"
trans="#001C1C1E"

# Bar opacity (used by the shared bars/ colors when another bar is picked)
_alpha="B3"
bg_alpha="#${_alpha}${bg#\#}"
bg_alpha_css="rgba(28, 28, 30, 0.70)"

black="#48484A"
red="#FF453A"
green="#30D158"
yellow="#FF9F0A"
blue="#0A84FF"
magenta="#BF5AF2"
cyan="#0A84FF"
white="#F5F5F7"
blackb="#98989D"
redb="#FF375F"
greenb="#30D158"
yellowb="#FF9F0A"
blueb="#0A84FF"
magentab="#BF5AF2"
cyanb="#0A84FF"
whiteb="#FFFFFF"

# Extend (Apple system colors)
purple="#BF5AF2"
amber="#FFD60A"
pink="#FF375F"
orange="#FF9F0A"
indigo="#5E5CE6"
lime="#30D158"
grey="#98989D"
bluegray="#8E8E93"

accent_color="#2C2C2E"
arch_icon="#F5F5F7"

# Bar (bars/cupertino — macOS menubar)
main_bar="cupertino"

# Bspwm — space for menubar (top) and dock (bottom)
BORDER_WIDTH="0"
WINDOW_GAP="6"
TOP_PADDING="0"
BOTTOM_PADDING="0"
LEFT_PADDING="2"
RIGHT_PADDING="2"
NORMAL_BC="#48484A"
FOCUSED_BC="#0A84FF"

# Terminal
term_font_size="10"
term_font_name="JetBrainsMono Nerd Font"

# Picom — macOS vibrancy: strong blur, soft shadow, rounded windows
P_FADE="true"
P_SHADOWS="true"
SHADOW_C="#000000"
P_CORNER_R="10"
P_BLUR="true"
P_ANIMATIONS="@"
P_TERM_OPACITY="1.0"

# Dunst — notification-centre style
dunst_offset='(14, 40)'
dunst_origin='top-right'
dunst_transparency='6'
dunst_corner_radius='14'
dunst_font='Adwaita Sans 10'
dunst_border='1'
dunst_frame_color="#48484A"
dunst_icon_theme="WhiteSur"
dunst_close_preset="fly-out"
dunst_close_direction="up"
dunst_open_preset="fly-in"
dunst_open_direction="right"

# Jgmenu
jg_bg="$bg"
jg_fg="$fg"
jg_sel_bg="#007AFF"
jg_sel_fg="#FFFFFF"
jg_sep="#48484A"

# Rofi — spotlight-ish
rofi_font="Adwaita Sans 11"
rofi_background="${bg}F2"
rofi_bg_alt="#2C2C2E"
rofi_background_alt="${bg}E6"
rofi_fg="$fg"
rofi_selected="#007AFFF0"
rofi_active="#34C759"
rofi_urgent="#FF3B30"

# Screenlocker
sl_bg="${bg}"
sl_fg="${fg}"
sl_ring="#007AFF"
sl_wrong="#FF3B30"
sl_date="#98989D"
sl_verify="#34C759"

# Gtk — WhiteSur (open-source macOS-style)
gtk_theme="WhiteSur-Dark"
gtk_icons="WhiteSur-dark"
gtk_cursor="WhiteSur-cursors"

# Wallpaper
ENGINE="CustomDir"
CUSTOM_DIR="$HOME/Pictures/wallpapers"
DEFAULT_WALL="$HOME/Pictures/wallpapers/japan-artistic-5120x2880-25406.jpg"
ANIMATED_WALL="$HOME/.config/bspwm/config/assets/animated_wall.mp4"

# Added by Control Center
LAUNCHER_STYLE="4"

# Added by Control Center
WALL_ACCENT="off"
