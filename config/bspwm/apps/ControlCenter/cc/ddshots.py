"""Pictures of each dropdown section, for the Dropdowns page.

Each dropdown is opened off-screen (nothing flashes on screen) with one
section switched on at a time, and photographed. Pictures are cached per
theme (and per dropdown layout), so this only runs again after a change."""

import hashlib
import json
import os
import subprocess
import time

from gi.repository import GdkPixbuf, GLib

from .common import BIN, BSPDIR, CACHE

EWW = ["eww", "--no-daemonize", "-c", os.path.join(BSPDIR, "eww")]
SHOW_FILE = os.path.join(BSPDIR, "config", "dropdowns.json")
HEAD = 42           # height of a dropdown's header (bp-head)
GAP = 12            # space between sections


def cache_dir():
    h = hashlib.sha1()
    for p in (os.path.join(BSPDIR, "eww", "colors.scss"), os.path.join(BSPDIR, "eww", "barpanels", "barpanels.yuck"),
              os.path.join(BSPDIR, "eww", "barpanels", "barpanels.scss")):
        try:
            with open(p, "rb") as f:
                h.update(f.read())
        except OSError:
            pass
    return os.path.join(CACHE, "dropdowns", h.hexdigest()[:16])


def _eww(*args):
    subprocess.run(EWW + list(args), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)


def _grab(name):
    """The dropdown window's pixels as an RGBA pixbuf."""
    from Xlib import X, display      # python-xlib
    out = subprocess.run(["xdotool", "search", "--name", f"^Eww - bp-{name}$"], capture_output=True, text=True).stdout.split()
    if not out:
        return None
    d = display.Display()
    try:
        win = d.create_resource_object("window", int(out[0]))
        g = win.get_geometry()
        img = win.get_image(0, 0, g.width, g.height, X.ZPixmap, 0xFFFFFFFF)
        data = bytearray(img.data)
    finally:
        d.close()
    data[0::4], data[2::4] = data[2::4], data[0::4]          # BGRA -> RGBA
    return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(bytes(data)), GdkPixbuf.Colorspace.RGB, True, 8,
                                           g.width, g.height, g.width * 4)


def dropdown_open():
    """Is one of the user's dropdowns open right now? (don't disturb it)"""
    try:
        with open(os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "barpanel", "open")) as f:
            return bool(f.read().strip())
    except OSError:
        return False


def capture(dropdowns, keys_off, done_one=None):
    """dropdowns: [(name, [section keys])]. Saves <cache>/<key>.png.
    Returns the folder. Runs in a background thread."""
    folder = cache_dir()
    os.makedirs(folder, exist_ok=True)
    try:
        with open(SHOW_FILE) as f:
            saved = json.dumps(json.load(f), separators=(",", ":"))
    except (OSError, ValueError):
        saved = "{}"
    try:
        for name, keys in dropdowns:
            data = subprocess.run([os.path.join(BIN, "BarPanelData"), name], capture_output=True, text=True, timeout=10).stdout.strip()
            if data:
                _eww("update", f"bp_{name}={data}")
            _eww("update", f"bp_open={name}", "bp_view=main", "bp_show=" + json.dumps(keys_off))
            _eww("open", f"bp-{name}", "--screen", "0", "--pos", "4000x0", "--anchor", "top left")
            time.sleep(0.6)
            head = _grab(name)
            if head is None:
                continue
            h0 = head.get_height()
            edge = max(0, (h0 - HEAD) // 2)          # border + padding around the content
            for key in keys:
                _eww("update", "bp_show=" + json.dumps({**keys_off, key: True}))
                time.sleep(0.35)
                pix = _grab(name)
                if pix is None:
                    continue
                h1, w = pix.get_height(), pix.get_width()
                section = h1 - h0 - GAP
                if section <= 4:                       # (not shown on this computer, e.g. no power modes)
                    continue
                part = pix.new_subpixbuf(edge, h1 - edge - section, w - 2 * edge, section)
                part.savev(os.path.join(folder, key + ".png"), "png", [], [])
                if done_one:
                    GLib.idle_add(done_one, key)
            _eww("close", f"bp-{name}")
    finally:
        _eww("update", "bp_open=", "bp_show=" + saved)
    with open(os.path.join(folder, ".complete"), "w") as f:
        f.write("")
    return folder
