"""Appearance: pick the theme (rice) and the wallpaper."""

import json
import os
import re

from gi.repository import Adw, Gio, GLib, Gtk

from .. import rice
from ..common import BSPDIR, HOME, Page, current_rice, group, have, run_quiet, thumbnail, tool
from ..preview import current_wallpaper

IMAGES = (".png", ".jpg", ".jpeg", ".webp")
DAYNIGHT = os.path.join(BSPDIR, "config", "daynight.json")
WIDGETS = os.path.join(BSPDIR, "config", "widgets.json")
CORNERS = [("top left", "Top left"), ("top right", "Top right"), ("bottom left", "Bottom left"),
           ("bottom right", "Bottom right")]


def is_light(name):
    """A theme with a light background."""
    m = re.search(r'(?m)^bg="?#?([0-9A-Fa-f]{6})', open(os.path.join(BSPDIR, "rices", name, "theme-config.bash")).read()) \
        if os.path.exists(os.path.join(BSPDIR, "rices", name, "theme-config.bash")) else None
    if not m:
        return False
    r, g, b = (int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 > 0.5


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


def v_video(name):
    return rice.theme_vars(name).get("ANIMATED_WALL", "")


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

        # Day and night themes (bin/IdleWatch switches them)
        dn = group(self, "Day and night", "A light theme by day and a dark one at night, switched by themselves.")
        self.dn_on = Adw.SwitchRow(title="Change the theme with the time of day")
        self.dn_on.add_prefix(Gtk.Image.new_from_icon_name("weather-clear-night-symbolic"))
        self.dn_on.connect("notify::active", lambda r, _p: self._dn_set(on=r.get_active()))
        dn.add(self.dn_on)
        names = sorted(d for d in os.listdir(rices_dir) if os.path.isdir(os.path.join(rices_dir, d)))
        light = [n for n in names if is_light(n)]
        self.dn_names = light + [n for n in names if n not in light]
        labels = [n.capitalize() + (" (light)" if n in light else "") for n in self.dn_names]
        self.dn_day = Adw.ComboRow(title="Day theme", model=Gtk.StringList.new(labels))
        self.dn_day.connect("notify::selected", lambda r, _p: self._dn_set(day=self.dn_names[r.get_selected()]))
        dn.add(self.dn_day)
        self.dn_night = Adw.ComboRow(title="Night theme", model=Gtk.StringList.new(labels))
        self.dn_night.connect("notify::selected", lambda r, _p: self._dn_set(night=self.dn_names[r.get_selected()]))
        dn.add(self.dn_night)
        self.dn_times = Adw.ComboRow(title="Switch at", model=Gtk.StringList.new(
            ["Sunrise and sunset (from the weather)", "Fixed times"]))
        self.dn_times.connect("notify::selected", lambda r, _p: self._dn_set(times="sun" if r.get_selected() == 0 else "fixed"))
        dn.add(self.dn_times)
        self.dn_day_at = Adw.EntryRow(title="Day starts at (HH:MM)", show_apply_button=True)
        self.dn_day_at.connect("apply", lambda r: self._dn_time("day_at", r.get_text()))
        dn.add(self.dn_day_at)
        self.dn_night_at = Adw.EntryRow(title="Night starts at (HH:MM)", show_apply_button=True)
        self.dn_night_at.connect("apply", lambda r: self._dn_time("night_at", r.get_text()))
        dn.add(self.dn_night_at)
        self._dn_load()

        # Desktop widgets (bin/DesktopWidgets, config/widgets.json)
        dw = group(self, "Desktop widgets", "On the desktop, behind your windows.")
        self.dw_rows = {}
        for key, title, icon in (("clock", "Clock and date", "preferences-system-time-symbolic"),
                                 ("media", "What's playing", "audio-x-generic-symbolic"),
                                 ("weather", "Weather", "weather-few-clouds-symbolic")):
            r = Adw.SwitchRow(title=title)
            r.add_prefix(Gtk.Image.new_from_icon_name(icon))
            r.connect("notify::active", lambda row, _p, k=key: self._dw_set(**{k: row.get_active()}))
            dw.add(r)
            self.dw_rows[key] = r
        self.dw_corner = Adw.ComboRow(title="Where", model=Gtk.StringList.new([t for _v, t in CORNERS]))
        self.dw_corner.connect("notify::selected", lambda r, _p: self._dw_set(corner=CORNERS[r.get_selected()][0]))
        dw.add(self.dw_corner)
        self._dw_load()

        # How the wallpaper is chosen (the theme's ENGINE)
        modes = group(self, "Wallpaper mode")
        self.modes = [("Default", "One picture", "The one you pick below"),
                      ("Random", "Random", "A random picture from this theme's collection at each start"),
                      ("CustomDir", "Random from a folder", "A random picture from a folder of yours at each start"),
                      ("Slideshow", "Slideshow", "A new picture from this theme's collection every 15 minutes")]
        if have("xwinwrap"):
            self.modes.append(("Animated", "Animated", "A looping video"))
        self.mode_row = Adw.ComboRow(title="Mode", model=Gtk.StringList.new([m[1] for m in self.modes]))
        self.mode_row.connect("notify::selected", self._mode)
        modes.add(self.mode_row)
        self.folder_row = self._chooser_row("Your wallpaper folder", "folder-symbolic", "CUSTOM_DIR")
        modes.add(self.folder_row)
        self.video_row = self._chooser_row("Video", "video-x-generic-symbolic", "ANIMATED_WALL")
        modes.add(self.video_row)

        self.walls = group(self, "Wallpaper")
        more = Gtk.Box(spacing=6)
        # Which pictures the grid shows: the theme's or the folder's
        self.source = "theme"
        self.shown = None
        self.sources = Adw.ToggleGroup(valign=Gtk.Align.CENTER, width_request=160)
        self.sources.add(Adw.Toggle(name="theme", label="Theme"))
        self.sources.add(Adw.Toggle(name="folder", label="Folder"))
        self.sources.connect("notify::active-name", self._source)
        more.append(self.sources)
        self.walls.set_header_suffix(more)
        self.wall_grid = grid(3)
        self.walls.add(self.wall_grid)
        self.wall_tiles = {}
        self.load_mode()
        self.follow_mode()

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
            self.load_mode()
            self.follow_mode()
        run_quiet([tool("Theme.sh")], done)

    # ----- wallpapers -----

    def theme_config(self):
        return os.path.join(BSPDIR, "rices", self.rice, "theme-config.bash")

    def theme_dir(self):
        return os.path.join(BSPDIR, "rices", self.rice, "walls")

    def custom_dir(self):
        """The theme's CUSTOM_DIR, if it's a real folder."""
        d = os.path.expanduser(rice.theme_vars(self.rice).get("CUSTOM_DIR", ""))
        return d if d and os.path.isdir(d) else None

    def auto_source(self):
        """The pictures the wallpaper mode uses."""
        custom = self.custom_dir()
        if not custom:
            return "theme"
        v = rice.theme_vars(self.rice)
        engine = v.get("ENGINE", "Default")
        if engine == "CustomDir":
            return "folder"
        if engine == "Default":
            wall = os.path.realpath(os.path.expanduser(v.get("DEFAULT_WALL", "")))
            if wall.startswith(os.path.realpath(custom) + os.sep):
                return "folder"
        return "theme"

    def wall_dir(self):
        return (self.custom_dir() if self.source == "folder" else None) or self.theme_dir()

    def follow_mode(self):
        """Show the pictures the current mode uses."""
        self.source = self.auto_source()
        self.quietly(lambda: self.sources.set_active_name(self.source))
        self.sources.set_visible(self.custom_dir() is not None)
        self.load_walls()

    def _source(self, group_, _p):
        name = group_.get_active_name()
        if not self._updating and name and name != self.source:
            self.source = name
            self.load_walls()

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
        self.shown = d
        try:
            files = sorted(f for f in os.listdir(d) if f.lower().endswith(IMAGES))
        except OSError:
            files = []
        where = (d.replace(HOME, "~", 1) if d != self.theme_dir()
                 else f"{self.rice.capitalize()}'s collection")
        if files:
            self.walls.set_description(f"{len(files)} in {where} · picking one switches to One picture")
        else:
            self.walls.set_description(f"No pictures in {where}")
        for f in files:
            path = os.path.join(d, f)
            t = tile(os.path.splitext(f)[0], 330, 186)
            t.connect("clicked", lambda _b, p=path: self.set_wall(p))
            self.wall_grid.append(t)
            self.wall_tiles[path] = t
            thumbnail(path, 352, 198, lambda tex, t=t: tex and t.picture.set_paintable(tex))
        self.mark()

    def set_wall(self, path):
        # Remember it in the theme (one picture mode) and show it
        try:
            rice.set_theme_vars({"ENGINE": "Default", "DEFAULT_WALL": path})
        except OSError as e:
            self.toast(f"Couldn't save the wallpaper: {e.strerror}")
            return
        run_quiet([tool("WallApply")], lambda _ok: self.mark())   # also stops a slideshow / video
        self.load_mode()
        self.mark()

    # ----- desktop widgets -----

    def _dw(self):
        try:
            with open(WIDGETS) as f:
                c = json.load(f)
        except (OSError, ValueError):
            c = {}
        return {"clock": bool(c.get("clock", False)), "media": bool(c.get("media", False)),
                "weather": bool(c.get("weather", False)), "corner": c.get("corner", "top left")}

    def _dw_load(self):
        c = self._dw()

        def put():
            for k, r in self.dw_rows.items():
                r.set_active(c[k])
            self.dw_corner.set_selected(next((i for i, (v, _t) in enumerate(CORNERS) if v == c["corner"]), 0))
        self.quietly(put)
        self.dw_corner.set_sensitive(any(c[k] for k in self.dw_rows))

    def _dw_set(self, **changes):
        if self._updating:
            return
        c = self._dw()
        c.update(changes)
        try:
            with open(WIDGETS, "w") as f:
                json.dump(c, f, indent=2)
                f.write("\n")
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
            return
        self._dw_load()
        run_quiet([tool("DesktopWidgets")])

    # ----- day and night -----

    def _dn(self):
        try:
            with open(DAYNIGHT) as f:
                c = json.load(f)
        except (OSError, ValueError):
            c = {}
        return {"on": bool(c.get("on", False)), "day": c.get("day", "aline"), "night": c.get("night", "cupertino"),
                "times": c.get("times", "sun"), "day_at": c.get("day_at", "07:00"), "night_at": c.get("night_at", "19:00")}

    def _dn_load(self):
        c = self._dn()

        def put():
            self.dn_on.set_active(c["on"])
            if c["day"] in self.dn_names:
                self.dn_day.set_selected(self.dn_names.index(c["day"]))
            if c["night"] in self.dn_names:
                self.dn_night.set_selected(self.dn_names.index(c["night"]))
            self.dn_times.set_selected(0 if c["times"] == "sun" else 1)
            self.dn_day_at.set_text(c["day_at"])
            self.dn_night_at.set_text(c["night_at"])
        self.quietly(put)
        for w in (self.dn_day, self.dn_night, self.dn_times):
            w.set_sensitive(c["on"])
        for w in (self.dn_day_at, self.dn_night_at):
            w.set_visible(c["on"] and c["times"] == "fixed")

    def _dn_set(self, **changes):
        if self._updating:
            return
        c = self._dn()
        c.update(changes)
        try:
            with open(DAYNIGHT, "w") as f:
                json.dump(c, f, indent=2)
                f.write("\n")
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
            return
        self._dn_load()
        if "on" in changes and changes["on"]:
            self.toast("The right theme for now comes within a minute")

    def _dn_time(self, key, text):
        text = text.strip()
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", text):
            self.toast("Write the time like 07:30")
            return
        self._dn_set(**{key: text})
        self.toast("Saved")

    # ----- wallpaper mode -----

    def _chooser_row(self, title, icon, var):
        row = Adw.ActionRow(title=title, activatable=True)
        row.add_prefix(Gtk.Image.new_from_icon_name(icon))
        b = Gtk.Button(label="Choose…", valign=Gtk.Align.CENTER)
        b.connect("clicked", lambda *_: self.choose(row))
        row.add_suffix(b)
        row.set_activatable_widget(b)
        row.var = var
        return row

    @staticmethod
    def _show_path(row, path, empty):
        path = os.path.expanduser(path)
        ok = os.path.isdir(path) if row.var == "CUSTOM_DIR" else os.path.isfile(path)
        row.set_subtitle(path.replace(HOME, "~", 1) if path and ok else empty)

    def choose(self, row):
        """A file picker for the wallpaper folder or the video."""
        folder = row.var == "CUSTOM_DIR"
        d = Gtk.FileDialog(title="Choose your wallpaper folder" if folder else "Choose a video", modal=True)
        current = os.path.expanduser(rice.theme_vars(self.rice).get(row.var, ""))
        start = current if folder else os.path.dirname(current)
        if not os.path.isdir(start):
            start = os.path.join(HOME, "Pictures") if folder else os.path.join(HOME, "Videos")
        if os.path.isdir(start):
            d.set_initial_folder(Gio.File.new_for_path(start))
        if not folder:
            f = Gtk.FileFilter(name="Videos")
            f.add_mime_type("video/*")
            f.add_mime_type("image/gif")
            filters = Gio.ListStore.new(Gtk.FileFilter)
            filters.append(f)
            d.set_filters(filters)

        def done(dialog, result):
            try:
                file = (dialog.select_folder_finish if folder else dialog.open_finish)(result)
            except GLib.Error:
                return                               # cancelled
            if file is not None and file.get_path():
                self._path(row.var, file.get_path())
        (d.select_folder if folder else d.open)(self.window, None, done)

    def load_mode(self):
        v = rice.theme_vars(self.rice)
        engine = v.get("ENGINE", "Default")
        names = [m[0] for m in self.modes]

        def put():
            if engine in names:
                self.mode_row.set_selected(names.index(engine))
            self.mode_row.set_subtitle(dict((m[0], m[2]) for m in self.modes).get(engine, ""))
            self._show_path(self.folder_row, v.get("CUSTOM_DIR", ""), "No folder chosen")
            self._show_path(self.video_row, v.get("ANIMATED_WALL", ""), "No video chosen")
        self.quietly(put)
        self.folder_row.set_visible(engine == "CustomDir")
        self.video_row.set_visible(engine == "Animated")

    def _mode(self, row, _p):
        if self._updating or row.get_selected() >= len(self.modes):
            return
        engine = self.modes[row.get_selected()][0]
        try:
            rice.set_theme_vars({"ENGINE": engine})
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
            return
        self.load_mode()
        self.follow_mode()
        if engine == "CustomDir" and not self.custom_dir():
            self.choose(self.folder_row)
            return
        if engine == "Animated" and not os.path.isfile(os.path.expanduser(v_video(self.rice))):
            self.choose(self.video_row)
            return
        run_quiet([tool("WallApply")], lambda _ok: self.mark())

    def _path(self, var, text):
        path = os.path.expanduser(text.strip())
        ok = os.path.isdir(path) if var == "CUSTOM_DIR" else os.path.isfile(path)
        if not ok:
            self.toast("That folder doesn't exist" if var == "CUSTOM_DIR" else "That file doesn't exist")
            return
        try:
            rice.set_theme_vars({var: path})
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
            return
        self.load_mode()
        self.follow_mode()
        run_quiet([tool("WallApply")], lambda _ok: (self.mark(), self.toast("Wallpaper updated")))

    # ----- state -----

    def mark(self):
        for name, t in self.theme_tiles.items():
            (t.add_css_class if name == self.rice else t.remove_css_class)("cc-current")
        cur = os.path.realpath(current_wallpaper() or self.current_wall())
        for path, t in self.wall_tiles.items():
            (t.add_css_class if os.path.realpath(path) == cur else t.remove_css_class)("cc-current")

    def refresh(self):
        rice = current_rice()
        if rice != self.rice and not self.applying:    # changed from elsewhere (rofi, keybind)
            self.rice = rice
            self.load_mode()
            self.follow_mode()
        self.mark()
