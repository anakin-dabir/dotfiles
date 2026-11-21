"""A small drawing of the desktop with the theme's current (unsaved) values:
bar, a focused terminal and another window (borders, gap, corners,
shadow), a notification pop-up where it will appear, and a dropdown."""

import math
import os
import re
import threading

import gi

gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango, PangoCairo  # noqa: E402

from .common import HOME, read_file  # noqa: E402

REAL_W = 1920          # the drawing is a scaled-down 1920x1080 screen
GROW = 2.2             # borders, gaps and corners drawn bigger than scale, so they're visible


def rgb(v, fallback=(0.5, 0.5, 0.5)):
    v = (v or "").strip()
    m = re.fullmatch(r"#([0-9A-Fa-f]{6})([0-9A-Fa-f]{2})?", v)
    if m and len(v) == 7:
        h = m.group(1)
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    if re.fullmatch(r"#[0-9A-Fa-f]{8}", v):      # #AARRGGBB
        h = v[3:]
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return fallback


def num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def current_wallpaper():
    m = re.search(r"--bg-\w+\s+'([^']+)'", read_file(os.path.join(HOME, ".fehbg")))
    return m.group(1) if m else ""


def rounded(cr, x, y, w, h, r):
    r = max(0, min(r, w / 2, h / 2))
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def _layout(cr, s, font, size, bold):
    layout = PangoCairo.create_layout(cr)
    desc = Pango.FontDescription.from_string(font or "Sans 9")
    if size:
        desc.set_absolute_size(size * Pango.SCALE)
    if bold:
        desc.set_weight(Pango.Weight.BOLD)
    layout.set_font_description(desc)
    layout.set_text(s, -1)
    return layout


def measure(cr, s, font, size=None, bold=False):
    return _layout(cr, s, font, size, bold).get_pixel_size()[0]


def text(cr, s, x, y, font, color, size=None, bold=False, max_w=None):
    layout = PangoCairo.create_layout(cr)
    desc = Pango.FontDescription.from_string(font or "Sans 9")
    if size:
        desc.set_absolute_size(size * Pango.SCALE)
    if bold:
        desc.set_weight(Pango.Weight.BOLD)
    layout.set_font_description(desc)
    layout.set_text(s, -1)
    if max_w:
        layout.set_width(int(max_w * Pango.SCALE))
        layout.set_ellipsize(Pango.EllipsizeMode.END)
    cr.set_source_rgb(*color)
    cr.move_to(x, y)
    PangoCairo.show_layout(cr, layout)
    return layout.get_pixel_size()


class DesktopPreview(Gtk.DrawingArea):
    def __init__(self):
        super().__init__(content_height=290, hexpand=True)
        self.v = {}
        self.wall = None
        self.wall_path = None
        self.set_draw_func(self._draw)

    def update(self, values):
        self.v = dict(values)
        path = current_wallpaper()
        if path != self.wall_path:
            self.wall_path = path
            self._load_wall(path)
        self.queue_draw()

    def _load_wall(self, path):
        def work():
            try:
                pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 1200, -1, True)
            except (GLib.Error, TypeError):
                pix = None
            GLib.idle_add(lambda: (setattr(self, "wall", pix), self.queue_draw(), False)[2])
        if path:
            threading.Thread(target=work, daemon=True).start()

    # ----- drawing -----

    def _draw(self, _area, cr, w, h):
        v = self.v
        s = w / REAL_W
        g = lambda px: px * s * GROW          # noqa: E731
        bg, fg, bg_alt = rgb(v.get("bg"), (0.1, 0.1, 0.12)), rgb(v.get("fg"), (0.95, 0.95, 0.95)), rgb(v.get("bg_alt"), (0.18, 0.18, 0.2))
        accent, other = rgb(v.get("FOCUSED_BC"), (0.2, 0.5, 1)), rgb(v.get("NORMAL_BC"), (0.3, 0.3, 0.3))
        pal = {k: rgb(v.get(k)) for k in ("red", "green", "yellow", "blue", "magenta", "cyan")}
        app_font = v.get("gtk_font") or "Sans 10"
        menu_font = v.get("dunst_font") or "Sans 10"
        term_font = v.get("term_font_name") or "Monospace"
        bar_font = v.get("_bar_font") or app_font

        # Screen + wallpaper
        rounded(cr, 0, 0, w, h, 10)
        cr.clip()
        if self.wall:
            pw, ph = self.wall.get_width(), self.wall.get_height()
            k = max(w / pw, h / ph)
            cr.save()
            cr.scale(k, k)
            Gdk.cairo_set_source_pixbuf(cr, self.wall, (w / k - pw) / 2, (h / k - ph) / 2)
            cr.paint()
            cr.restore()
        else:
            cr.set_source_rgb(*bg_alt)
            cr.paint()

        # Bar
        bar_h = 22
        cr.set_source_rgba(*bg, 0.92)
        cr.rectangle(0, 0, w, bar_h)
        cr.fill()
        x = 10
        for i in range(5):
            cr.set_source_rgb(*(accent if i == 0 else fg))
            cr.arc(x + i * 13, bar_h / 2, 3.2 if i == 0 else 2.3, 0, 2 * math.pi)
            cr.fill()
        clock = "Sat 21 Nov  07:30"
        layout_w = measure(cr, clock, bar_font, 10)
        text(cr, clock, w - layout_w - 12, 4, bar_font, fg, size=10)
        text(cr, "  56%    100%", w - layout_w - 110, 4, bar_font, fg, size=10)

        # Windows: focused terminal on the left, another window on the right
        gap = max(2, g(num(v.get("WINDOW_GAP"), 6)))
        border = g(num(v.get("BORDER_WIDTH"), 2))
        radius = g(num(v.get("P_CORNER_R"), 0))
        top = bar_h + gap
        area = w * 0.66                       # windows on the left, wallpaper shows on the right
        wa = (area - 3 * gap) * 0.58
        wb = area - 3 * gap - wa
        hh = h - top - gap
        self._window(cr, gap, top, wa, hh, radius, border, accent, v.get("P_SHADOWS") == "true", True)
        self._terminal(cr, gap, top, wa, hh, radius, border, bg, fg, pal, term_font,
                       max(0.35, num(v.get("P_TERM_OPACITY"), 1.0)))
        self._window(cr, 2 * gap + wa, top, wb, hh, radius, border, other, v.get("P_SHADOWS") == "true", False)
        self._app(cr, 2 * gap + wa, top, wb, hh, radius, border, bg, bg_alt, fg, accent, app_font)

        # Dropdown under the bar's right end
        dd_w, dd_h = 150, 98
        dx, dy = w - dd_w - 16, bar_h + 4
        dr = g(num(v.get("dunst_corner_radius"), 10)) * 0.7
        self._shadow(cr, dx, dy, dd_w, dd_h, dr)
        rounded(cr, dx, dy, dd_w, dd_h, dr)
        cr.set_source_rgba(*bg, 0.98)
        cr.fill()
        text(cr, "Sound", dx + 10, dy + 8, menu_font, fg, size=11, bold=True)
        cr.set_source_rgba(*fg, 0.1)
        rounded(cr, dx + 10, dy + 34, dd_w - 20, 6, 3)
        cr.fill()
        cr.set_source_rgb(*accent)
        rounded(cr, dx + 10, dy + 34, (dd_w - 20) * 0.56, 6, 3)
        cr.fill()
        rounded(cr, dx + 10, dy + 52, dd_w - 20, 36, dr * 0.6)
        cr.set_source_rgba(*fg, 0.06)
        cr.fill()
        cr.set_source_rgb(*accent)
        cr.arc(dx + 24, dy + 70, 7, 0, 2 * math.pi)
        cr.fill()
        text(cr, "Headphones", dx + 36, dy + 62, menu_font, fg, size=9.5, max_w=dd_w - 50)

        # Notification pop-up where dunst puts it
        nw, nh = 190, 52
        origin = v.get("dunst_origin") or "top-right"
        nx = {"left": 12, "center": (w - nw) / 2}.get(origin.split("-")[-1], w - nw - 12)
        ny = bar_h + 10 if origin.startswith("top") else h - nh - 12
        if origin.startswith("top") and nx + nw > dx:      # don't sit on the dropdown
            ny = dy + dd_h + 12
        nr = g(num(v.get("dunst_corner_radius"), 10)) * 0.7
        self._shadow(cr, nx, ny, nw, nh, nr)
        rounded(cr, nx, ny, nw, nh, nr)
        cr.set_source_rgba(*bg, 0.97)
        cr.fill_preserve()
        cr.set_source_rgba(*rgb(v.get("dunst_frame_color"), other), 0.9)
        cr.set_line_width(1)
        cr.stroke()
        cr.set_source_rgb(*accent)
        rounded(cr, nx + 10, ny + 12, 28, 28, nr * 0.5)
        cr.fill()
        text(cr, "Notification", nx + 46, ny + 10, menu_font, fg, size=10.5, bold=True, max_w=nw - 56)
        text(cr, "This is how pop-ups look", nx + 46, ny + 28, menu_font, fg, size=9, max_w=nw - 56)

    def _shadow(self, cr, x, y, w, h, r):
        for i in range(6, 0, -1):
            cr.set_source_rgba(0, 0, 0, 0.035)
            rounded(cr, x - i, y - i + 3, w + 2 * i, h + 2 * i, r + i)
            cr.fill()

    def _window(self, cr, x, y, w, h, r, border, color, shadow, focused):
        if shadow:
            self._shadow(cr, x, y, w, h, r)
        if border > 0:
            rounded(cr, x, y, w, h, r)
            cr.set_source_rgb(*color)
            cr.fill()

    def _terminal(self, cr, x, y, w, h, r, border, bg, fg, pal, font, opacity):
        ix, iy, iw, ih = x + border, y + border, w - 2 * border, h - 2 * border
        rounded(cr, ix, iy, iw, ih, max(0, r - border))
        cr.set_source_rgba(*bg, opacity)
        cr.fill()
        lh, size = 15, 10.5
        lx, ly = ix + 12, iy + 10
        user = text(cr, "user", lx, ly, font, pal["green"], size=size, bold=True)[0]
        text(cr, "@", lx + user, ly, font, fg, size=size)
        at = measure(cr, "@", font, size)
        host = text(cr, "arch", lx + user + at, ly, font, pal["blue"], size=size, bold=True)[0]
        text(cr, " ~ $ ls", lx + user + at + host, ly, font, fg, size=size)
        y2 = ly + lh
        cx = lx
        for name, col in (("Documents", "blue"), ("notes.md", None), ("run.sh", "green"), ("photo.png", "magenta")):
            cw = text(cr, name, cx, y2, font, pal[col] if col else fg, size=size)[0]
            cx += cw + 14
        y3 = y2 + lh * 1.6
        text(cr, "Colors", lx, y3, font, fg, size=size)
        for i, k in enumerate(("red", "green", "yellow", "blue", "magenta", "cyan")):
            cr.set_source_rgb(*pal[k])
            cr.rectangle(lx + i * 22, y3 + lh + 2, 18, 12)
            cr.fill()
        y4 = y3 + lh * 2.6
        text(cr, "user", lx, y4, font, pal["green"], size=size, bold=True)
        text(cr, "@arch ~ $ ", lx + user, y4, font, fg, size=size)
        cr.set_source_rgb(*fg)
        cw = measure(cr, "@arch ~ $ ", font, size)
        cr.rectangle(lx + user + cw, y4 + 2, 7, 13)
        cr.fill()

    def _app(self, cr, x, y, w, h, r, border, bg, bg_alt, fg, accent, font):
        ix, iy, iw, ih = x + border, y + border, w - 2 * border, h - 2 * border
        rounded(cr, ix, iy, iw, ih, max(0, r - border))
        cr.set_source_rgb(*bg)
        cr.fill()
        text(cr, "Files", ix + 12, iy + 9, font, fg, size=11, bold=True)
        for i, name in enumerate(("Home", "Pictures", "Music", "Downloads")):
            yy = iy + 34 + i * 26
            if i == 0:
                rounded(cr, ix + 8, yy - 3, iw - 16, 22, 5)
                cr.set_source_rgb(*accent)
                cr.fill()
            else:
                rounded(cr, ix + 8, yy - 3, iw - 16, 22, 5)
                cr.set_source_rgb(*bg_alt)
                cr.fill()
            text(cr, name, ix + 16, yy, font, (1, 1, 1) if i == 0 else fg, size=10, max_w=iw - 32)
