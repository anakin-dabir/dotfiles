"""Pictures of each app menu (rofi launcher) style, for Customize > App menu.

Each style is opened off-screen (nothing shows on screen) and photographed.
Pictures are cached per theme (the menus' colours, fonts and layouts), so
this only runs again after one of those changes."""

import glob
import hashlib
import os
import re
import shutil
import subprocess
import time

from .common import BSPDIR, CACHE

STYLES_DIR = os.path.join(BSPDIR, "config", "rofi-themes")
NAMES = {1: "Classic", 2: "Wallpaper header", 3: "Compact", 4: "Spotlight", 5: "Launchpad", 6: "Side panel"}
WIDTH = 360          # width of the saved pictures
VERSION = "1"        # bump when the way pictures are taken changes


def styles():
    """[(number, name)] of the styles in config/rofi-themes."""
    out = []
    for p in glob.glob(os.path.join(STYLES_DIR, "style_*.rasi")):
        m = re.search(r"style_(\d+)\.rasi$", p)
        if m:
            n = int(m.group(1))
            out.append((n, NAMES.get(n, f"Style {n}")))
    return sorted(out)


def cache_dir():
    h = hashlib.sha1(VERSION.encode())
    for p in [os.path.join(STYLES_DIR, "shared.rasi")] + sorted(glob.glob(os.path.join(STYLES_DIR, "style_*.rasi"))):
        try:
            with open(p, "rb") as f:
                h.update(f.read())
        except OSError:
            pass
    return os.path.join(CACHE, "launcher", h.hexdigest()[:16])


def is_complete(folder):
    return os.path.exists(os.path.join(folder, ".complete"))


def shown_dir():
    """The current set once it's complete; until then the last complete one."""
    cur = cache_dir()
    if is_complete(cur):
        return cur
    base = os.path.dirname(cur)
    old = [os.path.join(base, d) for d in os.listdir(base)] if os.path.isdir(base) else []
    old = [d for d in old if d != cur and is_complete(d)]
    return max(old, key=lambda d: os.path.getmtime(os.path.join(d, ".complete"))) if old else cur


def picture(n):
    path = os.path.join(shown_dir(), f"style_{n}.png")
    return path if os.path.exists(path) else None


def _offscreen_window():
    """The rofi window we opened (the one far right of the screen), or None."""
    out = subprocess.run(["xdotool", "search", "--class", "rofi"], capture_output=True, text=True).stdout.split()
    for w in reversed(out):
        g = subprocess.run(["xdotool", "getwindowgeometry", "--shell", w], capture_output=True, text=True).stdout
        m = re.search(r"X=(-?\d+)", g)
        if m and int(m.group(1)) >= 3000:
            return int(w)
    return None


def _grab(wid):
    from PIL import Image
    from Xlib import X, display
    d = display.Display()
    try:
        w = d.create_resource_object("window", wid)
        g = w.get_geometry()
        img = w.get_image(0, 0, g.width, g.height, X.ZPixmap, 0xFFFFFFFF)
        return Image.frombytes("RGB", (g.width, g.height), img.data, "raw", "BGRX")
    finally:
        d.close()


def capture():
    folder = cache_dir()
    os.makedirs(folder, exist_ok=True)
    for n, _name in styles():
        out = os.path.join(folder, f"style_{n}.png")
        if os.path.exists(out):
            continue                      # (an interrupted run continues)
        # Full-screen styles are drawn at the screen's size, off-screen
        extra = ""
        with open(os.path.join(STYLES_DIR, f"style_{n}.rasi")) as f:
            if re.search(r"fullscreen:\s*true", f.read()):
                extra = "fullscreen: false; width: 1920px; height: 1080px;"
        p = subprocess.Popen(["rofi", "-show", "drun", "-theme", os.path.join(STYLES_DIR, f"style_{n}.rasi"),
                              "-theme-str", "window { location: north west; anchor: north west; "
                              f"x-offset: 4000px; y-offset: 0px; {extra} }}"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            wid = None
            for _ in range(40):           # (up to 2 s to appear)
                time.sleep(0.05)
                wid = _offscreen_window()
                if wid:
                    break
            if wid is None:
                continue
            time.sleep(0.35)              # icons
            img = _grab(wid)
            img = img.resize((WIDTH, round(img.height * WIDTH / img.width)))
            img.save(out)
        except Exception:                 # noqa: BLE001  (no picture this time)
            pass
        finally:
            p.terminate()
            p.wait(timeout=3)
    if all(os.path.exists(os.path.join(folder, f"style_{n}.png")) for n, _ in styles()):
        open(os.path.join(folder, ".complete"), "w").close()
        base = os.path.dirname(folder)
        for d in os.listdir(base):
            p = os.path.join(base, d)
            if p != folder and os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
    return folder
