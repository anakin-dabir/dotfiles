#!/bin/sh

# Set the gtk theme corresponding to rice
sed -i "$HOME"/.config/bspwm/config/xsettingsd \
    -e "s|Net/ThemeName .*|Net/ThemeName \"$gtk_theme\"|" \
    -e "s|Net/IconThemeName .*|Net/IconThemeName \"$gtk_icons\"|" \
    -e "s|Gtk/CursorThemeName .*|Gtk/CursorThemeName \"$gtk_cursor\"|"

sed -i -e "s/Inherits=.*/Inherits=$gtk_cursor/" "$HOME"/.icons/default/index.theme

# Electron/Chromium apps read settings.ini directly and ignore xsettingsd,
# so keep those in sync too.
for _v in 3.0 4.0; do
    _f="$HOME/.config/gtk-$_v/settings.ini"
    [ -f "$_f" ] || continue
    for _k in theme-name:"$gtk_theme" icon-theme-name:"$gtk_icons" cursor-theme-name:"$gtk_cursor"; do
        _key="gtk-${_k%%:*}"; _val="${_k#*:}"
        if grep -q "^$_key=" "$_f"; then
            sed -i "s|^$_key=.*|$_key=$_val|" "$_f"
        else
            printf '%s=%s\n' "$_key" "$_val" >>"$_f"
        fi
    done
done

# Reload daemon and apply gtk theme
if pidof -q xsettingsd; then
    pkill -1 xsettingsd
fi
xsetroot -cursor_name left_ptr
