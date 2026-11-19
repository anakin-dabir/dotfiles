#!/bin/sh
# cupertino — per-rice hook. Runs last (via config/modules/99-rice-hook.sh),
# after the shared modules have written their configs.
#
# Everything here is scoped to this rice: shared.rasi is regenerated from
# scratch each time ANY rice is applied, so appending to it cannot leak into
# other themes.

_RICE_DIR="$HOME/.config/bspwm/rices/cupertino"
_ROFI="$HOME/.config/bspwm/config/rofi-themes/shared.rasi"

# ── 1. macOS shapes for every rofi dialog ───────────────────────
# (colours already came from theme-config.bash via 09-rofi.sh)
cat >>"$_ROFI" <<'EOF'

/* ── cupertino: macOS-style geometry ───────────────────────── */
window {
    border-radius: 12px;
    border:        1px;
    border-color:  @bg-alt;
    padding:       0px;
}
mainbox  { padding: 8px; spacing: 6px; }
inputbar {
    background-color: @bg-alt;
    border-radius:    9px;
    padding:          9px 12px;
    spacing:          8px;
}
entry    { placeholder-color: @foreground; }
listview { spacing: 2px; padding: 2px 0px; }
element  { border-radius: 8px; padding: 8px 12px; spacing: 10px; }
element selected {
    background-color: @selected;
    text-color:       #FFFFFF;
}
element-icon { size: 22px; }
button   { border-radius: 8px; padding: 6px; }
message  { border-radius: 9px; padding: 8px; }
EOF
