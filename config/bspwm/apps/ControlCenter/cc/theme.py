"""The app wears the current rice: background, text, accent, corners and
font come from eww/colors.scss (written by config/modules/06-eww.sh each
time a theme is applied). Re-applied live when the theme changes."""

import os
import re

from gi.repository import Adw, Gdk, Gio, Gtk

from .common import BSPDIR

COLORS = os.path.join(BSPDIR, "eww", "colors.scss")


def _vars(path):
    out = {}
    try:
        with open(path) as f:
            for line in f:
                m = re.match(r"\s*\$([\w-]+)\s*:\s*(.+?)\s*;", line)
                if m:
                    out[m.group(1)] = m.group(2)
    except OSError:
        pass
    return out


def _rgb(value, fallback):
    """'#rgb', '#rrggbb', '#aarrggbb' or 'rgba(r, g, b, a)' -> (r, g, b)."""
    v = (value or "").strip()
    m = re.fullmatch(r"#([0-9a-fA-F]{3,8})", v)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) == 8:          # #AARRGGBB (polybar style)
            h = h[2:]
        if len(h) == 6:
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+).*\)", v)
    if m:
        return tuple(int(x) for x in m.groups())
    return fallback


def _hex(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(x))) for x in c)


def _mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _lum(c):
    return (299 * c[0] + 587 * c[1] + 114 * c[2]) / 1000


class Theme:
    def __init__(self):
        self.provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), self.provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        self.apply()
        self.monitor = Gio.File.new_for_path(COLORS).monitor_file(Gio.FileMonitorFlags.NONE, None)
        self.monitor.connect("changed", self._changed)

    def _changed(self, _mon, _file, _other, event):
        if event in (Gio.FileMonitorEvent.CHANGES_DONE_HINT, Gio.FileMonitorEvent.CREATED):
            self.apply()

    def apply(self):
        v = _vars(COLORS)
        bg = _rgb(v.get("bg"), (30, 30, 34))
        fg = _rgb(v.get("fg"), (240, 240, 244))
        accent = _rgb(v.get("nc-accent", v.get("blue")), (53, 132, 228))
        on_accent = _rgb(v.get("nc-on-accent"), (255, 255, 255))
        dark = _lum(bg) < 128
        Adw.StyleManager.get_default().set_color_scheme(
            Adw.ColorScheme.FORCE_DARK if dark else Adw.ColorScheme.FORCE_LIGHT)

        # Readable accent for text and links on the window background
        accent_text = accent
        for _ in range(6):
            if abs(_lum(accent_text) - _lum(bg)) >= 90:
                break
            accent_text = _mix(accent_text, fg, 0.25)

        try:
            radius = int(re.sub(r"\D", "", v.get("nc-card-radius", "12")) or 12)
        except ValueError:
            radius = 12
        radius = max(0, min(radius, 16))
        font = v.get("nc-theme-font", "").strip('"') or "Adwaita Sans"

        css = f"""
:root {{
  --accent-bg-color: {_hex(accent)};
  --accent-fg-color: {_hex(on_accent)};
  --accent-color: {_hex(accent_text)};
  --window-bg-color: {_hex(bg)};
  --window-fg-color: {_hex(fg)};
  --view-bg-color: {_hex(bg)};
  --view-fg-color: {_hex(fg)};
  --headerbar-bg-color: {_hex(bg)};
  --headerbar-fg-color: {_hex(fg)};
  --headerbar-backdrop-color: {_hex(bg)};
  --sidebar-bg-color: {_hex(_mix(bg, fg, 0.035))};
  --sidebar-fg-color: {_hex(fg)};
  --sidebar-backdrop-color: {_hex(_mix(bg, fg, 0.035))};
  --secondary-sidebar-bg-color: {_hex(_mix(bg, fg, 0.035))};
  --card-bg-color: {_hex(_mix(bg, fg, 0.06))};
  --card-fg-color: {_hex(fg)};
  --popover-bg-color: {_hex(_mix(bg, fg, 0.08))};
  --popover-fg-color: {_hex(fg)};
  --dialog-bg-color: {_hex(_mix(bg, fg, 0.05))};
  --dialog-fg-color: {_hex(fg)};
  --thumbnail-bg-color: {_hex(_mix(bg, fg, 0.06))};
}}
window, window label, window entry, window button {{ font-family: "{font}", "Adwaita Sans", sans-serif; }}
.boxed-list, .card, row.expander, .cc-tile-image {{ border-radius: {radius}px; }}
.boxed-list > row:first-child {{ border-top-left-radius: {radius}px; border-top-right-radius: {radius}px; }}
.boxed-list > row:last-child {{ border-bottom-left-radius: {radius}px; border-bottom-right-radius: {radius}px; }}

/* tiles (themes, wallpapers) */
.cc-tile {{ padding: 6px; border-radius: {radius + 4}px; }}
.cc-tile-image {{ background-color: var(--thumbnail-bg-color); }}
.cc-tile.cc-current .cc-tile-image {{ outline: 3px solid var(--accent-bg-color); outline-offset: 2px; }}
.cc-tile-name {{ font-size: 0.9em; }}
.cc-tile.cc-current .cc-tile-name {{ font-weight: bold; color: var(--accent-color); }}
.cc-sticky {{ background-color: {_hex(bg)}; border-bottom: 1px solid {_hex(_mix(bg, fg, 0.10))}; }}
.cc-swatch {{ padding: 4px; border-radius: 999px; min-width: 0; min-height: 0; }}
.cc-ddmock {{ background-color: {_hex(bg)}; border: 1px solid {_hex(_mix(bg, fg, 0.14))}; border-radius: {radius + 4}px; padding: 12px; }}
.cc-mockbar {{ background-color: {_hex(_mix(bg, fg, 0.10))}; border-radius: 8px; padding: 5px 8px; }}
.cc-ddtab {{ padding: 6px 14px; font-weight: bold; }}
.cc-ddtab:checked {{ background-color: var(--accent-bg-color); color: var(--accent-fg-color); }}
.cc-chip {{ background-color: {_hex(_mix(bg, fg, 0.16))}; border-radius: 6px; padding: 3px 7px; font-size: 0.82em; }}
.cc-hero-title {{ font-size: 1.6em; font-weight: 800; }}
.cc-big {{ font-size: 2.2em; font-weight: 800; }}
"""
        self.provider.load_from_string(css)
