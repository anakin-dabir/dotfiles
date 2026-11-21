"""Appearance: pick the theme (rice) and the wallpaper."""

import os
import re

from gi.repository import Gtk

from ..common import BSPDIR, Page, current_rice, group, launch, run_quiet, thumbnail, tool

IMAGES = (".png", ".jpg", ".jpeg", ".webp")


def tile(name, width, height):
    """A picture with a name under it (the picture is filled in later)."""
    button = Gtk.Button()
    button.add_css_class("flat")
    button.add_css_class("cc-tile")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
    picture.set_size_request(width // 2, height // 2)
    picture.add_css_class("cc-tile-image")
    picture.set_overflow(Gtk.Overflow.HIDDEN)
    label = Gtk.Label(label=name, ellipsize=3, max_width_chars=16)
    label.add_css_class("cc-tile-name")
    box.append(picture)
    box.append(label)
    button.set_child(box)
    button.picture = picture
    return button


def grid(per_line):
    """Tiles in rows of `per_line` (pictures keep their shape)."""
    return Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, column_spacing=4,
                       row_spacing=4, min_children_per_line=per_line, max_children_per_line=per_line,
                       valign=Gtk.Align.START)


class AppearancePage(Page):
    name = "appearance"
    title = "Appearance"
    icon = "preferences-desktop-appearance-symbolic"
    interval = 3

    def __init__(self, window):
        super().__init__(window)
        self.rice = current_rice()
        self.applying = None

        themes = group(self, "Theme", "Colors, bar, borders and fonts of the whole desktop. Takes a few seconds to apply.")
        self.theme_grid = grid(4)
        themes.add(self.theme_grid)
        self.theme_tiles = {}
        rices_dir = os.path.join(BSPDIR, "rices")
        for name in sorted(d for d in os.listdir(rices_dir) if os.path.isdir(os.path.join(rices_dir, d))):
            t = tile(name.capitalize(), 130, 172)
            t.connect("clicked", lambda _b, n=name: self.apply_theme(n))
            self.theme_grid.append(t)
            self.theme_tiles[name] = t
            thumbnail(os.path.join(rices_dir, name, "preview.webp"), 260, 344,
                      lambda tex, t=t: tex and t.picture.set_paintable(tex))

        self.walls = group(self, "Wallpaper")
        more = Gtk.Box(spacing=6)
        b = Gtk.Button(icon_name="folder-open-symbolic", tooltip_text="Open the wallpaper folder")
        b.add_css_class("flat")
        b.connect("clicked", lambda *_: launch(["xdg-open", self.wall_dir()]))
        more.append(b)
        self.walls.set_header_suffix(more)
        self.wall_grid = grid(3)
        self.walls.add(self.wall_grid)
        self.wall_tiles = {}
        self.load_walls()
        self.mark()

    # ----- themes -----

    def apply_theme(self, name):
        if self.applying or name == current_rice():
            return
        self.applying = name
        with open(os.path.join(BSPDIR, ".rice"), "w") as f:
            f.write(name + "\n")
        self.toast(f"Applying {name.capitalize()}…")
        self.rice = name
        self.mark()

        def done(_ok):
            self.applying = None
            self.toast(f"{name.capitalize()} applied")
            self.load_walls()
            self.mark()
        run_quiet([tool("Theme.sh")], done)

    # ----- wallpapers -----

    def theme_config(self):
        return os.path.join(BSPDIR, "rices", self.rice, "theme-config.bash")

    def wall_dir(self):
        return os.path.join(BSPDIR, "rices", self.rice, "walls")

    def current_wall(self):
        try:
            with open(self.theme_config()) as f:
                m = re.search(r'^DEFAULT_WALL="?([^"\n]*)"?', f.read(), re.M)
        except OSError:
            return ""
        return os.path.expandvars(m.group(1)) if m else ""

    def load_walls(self):
        for t in list(self.wall_tiles.values()):
            self.wall_grid.remove(t.get_parent())
        self.wall_tiles.clear()
        d = self.wall_dir()
        try:
            files = sorted(f for f in os.listdir(d) if f.lower().endswith(IMAGES))
        except OSError:
            files = []
        self.walls.set_description(f"{len(files)} in {self.rice.capitalize()}'s collection" if files else "No wallpapers for this theme")
        for f in files:
            path = os.path.join(d, f)
            t = tile(os.path.splitext(f)[0], 176, 99)
            t.connect("clicked", lambda _b, p=path: self.set_wall(p))
            self.wall_grid.append(t)
            self.wall_tiles[path] = t
            thumbnail(path, 352, 198, lambda tex, t=t: tex and t.picture.set_paintable(tex))
        self.mark()

    def set_wall(self, path):
        # Same as WallSelect: remember it in the theme, show it, recolor
        try:
            cfg = self.theme_config()
            with open(cfg) as f:
                text = f.read()
            text = re.sub(r"^ENGINE=.*$", 'ENGINE="Default"', text, flags=re.M)
            text = re.sub(r"^DEFAULT_WALL=.*$", f'DEFAULT_WALL="{path}"', text, flags=re.M)
            with open(cfg, "w") as f:
                f.write(text)
        except OSError as e:
            self.toast(f"Couldn't save the wallpaper: {e.strerror}")
            return
        run_quiet(["feh", "--bg-fill", path])
        launch([tool("WallSync")])
        self.mark()

    # ----- state -----

    def mark(self):
        for name, t in self.theme_tiles.items():
            (t.add_css_class if name == self.rice else t.remove_css_class)("cc-current")
        cur = os.path.realpath(self.current_wall())
        for path, t in self.wall_tiles.items():
            (t.add_css_class if os.path.realpath(path) == cur else t.remove_css_class)("cc-current")

    def refresh(self):
        rice = current_rice()
        if rice != self.rice and not self.applying:    # changed from elsewhere (rofi, keybind)
            self.rice = rice
            self.load_walls()
        self.mark()
