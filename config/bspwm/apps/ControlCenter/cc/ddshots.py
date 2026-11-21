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

from . import ddconfig
from .common import BIN, BSPDIR, CACHE

EWW = ["eww", "--no-daemonize", "-c", os.path.join(BSPDIR, "eww")]
SHOW_FILE = os.path.join(BSPDIR, "config", "dropdowns.json")
HEAD = 42           # height of a dropdown's header (bp-head)
GAP = 12            # space between sections


VERSION = "9"       # bump when the dropdowns' layout or the way pictures are cut changes


def cache_dir():
    """Pictures depend on the theme (colours, corners, fonts), so they're kept
    per theme: they're retaken only after switching theme (or a VERSION bump)."""
    h = hashlib.sha1(VERSION.encode())
    for p in (os.path.join(BSPDIR, "eww", "colors.scss"),):
        try:
            with open(p, "rb") as f:
                h.update(f.read())
        except OSError:
            pass
    return os.path.join(CACHE, "dropdowns", h.hexdigest()[:16])


def forget_old(keep):
    """Delete picture sets of other themes/versions (they're cheap to retake)."""
    import shutil
    base = os.path.dirname(keep)
    for d in os.listdir(base) if os.path.isdir(base) else []:
        p = os.path.join(base, d)
        if p != keep and os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)


def _eww(*args):
    subprocess.run(EWW + list(args), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)


def _height(name):
    out = subprocess.run(["xdotool", "search", "--name", f"^Eww - bp-{name}$"], capture_output=True, text=True).stdout.split()
    if not out:
        return None
    g = subprocess.run(["xdotool", "getwindowgeometry", "--shell", out[0]], capture_output=True, text=True).stdout
    for line in g.splitlines():
        if line.startswith("HEIGHT="):
            return int(line[7:])
    return None


def _settle(name, least=0.5):
    """Wait until the dropdown has redrawn after a change: at least `least`
    seconds, then until its height stops changing."""
    time.sleep(least)
    last, same = _height(name), 0
    for _ in range(20):
        time.sleep(0.1)
        h = _height(name)
        same = same + 1 if h == last else 0
        last = h
        if same >= 2:
            break
    time.sleep(0.1)          # (one more frame for the contents)


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


def capture(done_one=None):
    """A picture of every dropdown section: <cache>/<section>.png.
    Returns the folder. Runs in a background thread."""
    off = {k: False for k in ddconfig.SECTIONS}
    only = lambda key=None: json.dumps(ddconfig.build({**off, **({key: True} if key else {})}, {}),   # noqa: E731
                                       separators=(",", ":"))
    dropdowns = []
    for dd, _t, units in ddconfig.DROPDOWNS:
        keys = []
        for u, x in units:
            keys += [r for r, _n in x] if isinstance(x, list) else [u]
        dropdowns.append((dd, keys))
    folder = cache_dir()
    os.makedirs(folder, exist_ok=True)
    try:
        with open(SHOW_FILE) as f:
            saved = json.dumps(json.load(f), separators=(",", ":"))
    except (OSError, ValueError):
        saved = "{}"
    try:            # (measured once per set, kept for a resumed run)
        edge = int(open(os.path.join(folder, ".edge")).read())
    except (OSError, ValueError):
        edge = None
    try:
        for name, keys in dropdowns:
            if all(os.path.exists(os.path.join(folder, k + ".png")) for k in keys) and \
                    os.path.exists(os.path.join(folder, f"head_{name}.png")):
                continue
            data = subprocess.run([os.path.join(BIN, "BarPanelData"), name], capture_output=True, text=True, timeout=10).stdout.strip()
            if data:
                _eww("update", f"bp_{name}={data}")
            _eww("update", f"bp_open={name}", "bp_view=main", "bp_show=" + only())
            _eww("open", f"bp-{name}", "--screen", "0", "--pos", "4000x0", "--anchor", "top left")
            _settle(name, 0.8)
            head = _grab(name)
            if head is None:
                continue
            h0 = head.get_height()
            # Border + padding around the content, measured once on a dropdown
            # that's only its header with every section off (not Storage: its
            # disk cards always show)
            if edge is None:
                edge = max(0, (h0 - HEAD) // 2)
                with open(os.path.join(folder, ".edge"), "w") as f:
                    f.write(str(edge))
            # Everything above the sections: the header (and Storage's disk cards)
            top = h0 - 2 * edge
            if top > 0:
                head.new_subpixbuf(edge, edge, head.get_width() - 2 * edge, top).savev(
                    os.path.join(folder, f"head_{name}.png"), "png", [], [])
            for key in keys:
                if os.path.exists(os.path.join(folder, key + ".png")):
                    continue            # (taken already: an interrupted run continues)
                _eww("update", "bp_show=" + only(key))
                _settle(name)
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
    forget_old(folder)
    return folder
