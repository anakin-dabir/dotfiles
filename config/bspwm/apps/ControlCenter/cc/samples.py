"""Sample pictures for theme choices: a few icons from an icon theme and a
few pointers from a cursor theme, shown before the theme is applied."""

import os
import struct

from gi.repository import Gdk, GLib, Gtk

ICONS = ["folder", "user-home", "text-x-generic", "image-x-generic", "audio-x-generic",
         "utilities-terminal", "web-browser", "preferences-system", "user-trash"]
CURSORS = [("left_ptr", "default"), ("hand2", "pointer"), ("xterm", "text"), ("watch", "wait"),
           ("fleur", "move"), ("crosshair", "cross")]
ICON_DIRS = ["~/.local/share/icons", "~/.icons", "/usr/share/icons"]


def icon_samples(theme, size=32):
    """Paintables for a few common icons from `theme` (missing ones skipped)."""
    it = Gtk.IconTheme()
    it.set_theme_name(theme)
    out = []
    for name in ICONS:
        if it.has_icon(name):
            out.append(it.lookup_icon(name, None, size, 1, Gtk.TextDirection.NONE, 0))
    return out


def _xcursor_image(path, want=32):
    """The image closest to `want` px from an Xcursor file, as a texture."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"Xcur":
        return None
    _hsize, _ver, ntoc = struct.unpack_from("<III", data, 4)
    best = None
    for i in range(ntoc):
        typ, sub, pos = struct.unpack_from("<III", data, 16 + i * 12)
        if typ == 0xFFFD0002 and (best is None or abs(sub - want) < abs(best[0] - want)):
            best = (sub, pos)
    if best is None:
        return None
    _h, _t, _s, _v, w, h, _xh, _yh, _d = struct.unpack_from("<IIIIIIIII", data, best[1])
    start = best[1] + 36
    pixels = data[start:start + w * h * 4]
    if len(pixels) < w * h * 4:
        return None
    # Xcursor pixels are premultiplied ARGB, little-endian (bytes B G R A)
    return Gdk.MemoryTexture.new(w, h, Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED, GLib.Bytes.new(pixels), w * 4)


def _cursor_file(theme, names, seen=None):
    seen = seen or set()
    if theme in seen:
        return None
    seen.add(theme)
    for base in ICON_DIRS:
        d = os.path.join(os.path.expanduser(base), theme)
        for n in names:
            p = os.path.join(d, "cursors", n)
            if os.path.exists(p):
                return p
        idx = os.path.join(d, "index.theme")
        if os.path.exists(idx):
            for line in open(idx, errors="ignore"):
                if line.startswith("Inherits="):
                    for parent in line.split("=", 1)[1].split(","):
                        p = _cursor_file(parent.strip(), names, seen)
                        if p:
                            return p
    return None


def cursor_samples(theme):
    out = []
    for names in CURSORS:
        p = _cursor_file(theme, names)
        if p:
            try:
                tex = _xcursor_image(os.path.realpath(p))
            except (OSError, struct.error, GLib.Error):
                tex = None
            if tex:
                out.append(tex)
    return out


class SampleStrip(Gtk.Box):
    """A row of small pictures."""

    def __init__(self):
        super().__init__(spacing=14, margin_top=8, margin_bottom=8, margin_start=14, margin_end=14,
                         halign=Gtk.Align.START)

    def show(self, paintables, size=28):
        while (c := self.get_first_child()) is not None:
            self.remove(c)
        for p in paintables:
            img = Gtk.Image.new_from_paintable(p)
            img.set_pixel_size(size)
            self.append(img)
        if not paintables:
            lbl = Gtk.Label(label="No preview")
            lbl.add_css_class("dim-label")
            self.append(lbl)

