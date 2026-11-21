"""Customize: edit the current theme (colours, windows, fonts, notifications,
GTK look). Changes are collected and applied together with "Apply"."""

import glob
import os
import re

from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk, Pango

from .. import launchershots, rice
from ..pickers import ColorButton, FontButton
from ..preview import DesktopPreview
from ..samples import SampleStrip, cursor_samples, gtk_theme_preview, icon_samples
from ..common import BSPDIR, HOME, Page, current_rice, group, launch, read_file, run, run_quiet, text_button, tool

COLORS = [
    ("bg", "Background", "Windows, bar and menus"),
    ("bg_alt", "Second background", "Cards and highlighted parts"),
    ("fg", "Text", ""),
    ("FOCUSED_BC", "Accent", "Focused window border, highlights in menus and dropdowns"),
    ("NORMAL_BC", "Other windows' border", ""),
]
PALETTE = [("red", "Red"), ("green", "Green"), ("yellow", "Yellow"), ("blue", "Blue"),
           ("magenta", "Magenta"), ("cyan", "Cyan")]
ORIGINS = [("top-right", "Top right"), ("top-center", "Top center"), ("top-left", "Top left"),
           ("bottom-right", "Bottom right"), ("bottom-center", "Bottom center"), ("bottom-left", "Bottom left")]


def _hex(v):
    v = (v or "").strip()
    if re.fullmatch(r"#[0-9A-Fa-f]{8}", v):      # #AARRGGBB (polybar style)
        v = "#" + v[3:]
    return v if re.fullmatch(r"#[0-9A-Fa-f]{6}", v) else None



def _dirs(paths, test):
    out = set()
    for base in paths:
        for d in glob.glob(os.path.join(os.path.expanduser(base), "*")):
            if os.path.isdir(d) and test(d):
                out.add(os.path.basename(d))
    return sorted(out, key=str.lower)


def gtk_themes():
    return _dirs(["~/.local/share/themes", "~/.themes", "/usr/share/themes"],
                 lambda d: os.path.isdir(os.path.join(d, "gtk-3.0")))


def icon_themes():
    def ok(d):
        idx = os.path.join(d, "index.theme")
        return os.path.exists(idx) and "Directories=" in read_file(idx) and os.path.basename(d) not in ("default", "hicolor", "locolor")
    return _dirs(["~/.local/share/icons", "~/.icons", "/usr/share/icons"], ok)


def cursor_themes():
    return _dirs(["~/.local/share/icons", "~/.icons", "/usr/share/icons"],
                 lambda d: os.path.isdir(os.path.join(d, "cursors")) and os.path.basename(d) != "default")


def current_app_font():
    for f in ("~/.config/gtk-3.0/settings.ini", "~/.config/gtk-4.0/settings.ini"):
        m = re.search(r"(?m)^gtk-font-name=(.+)$", read_file(os.path.expanduser(f)))
        if m:
            return m.group(1).strip()
    return "Adwaita Sans 10"



class CustomizePage(Page):
    name = "customize"
    title = "Customize"
    icon = "applications-graphics-symbolic"
    interval = 3

    def __init__(self, window):
        super().__init__(window)
        self.rice = current_rice()
        self.vals = {}
        self.changes = {}
        self.widgets = {}      # var -> (kind, widget)

        self.intro = group(self)
        self.intro_row = Adw.ActionRow()
        self.intro_row.add_prefix(Gtk.Image.new_from_icon_name("applications-graphics-symbolic"))
        self.reset_btn = text_button("Reset…", self._reset)
        self.intro_row.add_suffix(self.reset_btn)
        self.intro.add(self.intro_row)
        # The preview stays on screen above the settings (the window shows
        # sticky_widget under its title bar while this page is open)
        self.preview = DesktopPreview()
        self.preview.set_content_height(230)
        self.sticky_widget = Adw.Clamp(child=self.preview, maximum_size=470, margin_top=10, margin_bottom=12,
                                       margin_start=12, margin_end=12)

        colors = group(self, "Colors")
        # Accent taken from the wallpaper (bin/WallAccent), saved right away
        self.wall_accent = Adw.SwitchRow(title="Accent from the wallpaper",
                                         subtitle="Borders, bar icons, menus and dropdowns take its main colour")
        self.wall_accent.add_prefix(Gtk.Image.new_from_icon_name("color-select-symbolic"))
        self.wall_accent.connect("notify::active", self._wall_accent)
        colors.add(self.wall_accent)
        for var, title, sub in COLORS:
            colors.add(self._color_row(var, title, sub))
        pal = Adw.ExpanderRow(title="Color palette", subtitle="Bar icons, terminal colours, warnings")
        for var, title in PALETTE:
            pal.add_row(self._color_row(var, title, ""))
        colors.add(pal)

        win = group(self, "Windows")
        win.add(self._spin("BORDER_WIDTH", "Border width", "", 0, 10, 1))
        win.add(self._spin("WINDOW_GAP", "Gap between windows", "", 0, 40, 1))
        win.add(self._spin("P_CORNER_R", "Rounded corners", "Corner radius of windows", 0, 24, 1))
        win.add(self._switch("P_SHADOWS", "Shadows"))
        win.add(self._switch("P_BLUR", "Blur", "Behind see-through windows and the bar"))
        win.add(self._switch("P_FADE", "Fade windows in and out"))
        win.add(self._switch("P_ANIMATIONS", "Animations", "Windows open, close and move with animations",
                             on="@", off="#"))
        win.add(self._color_row("SHADOW_C", "Shadow colour", ""))
        win.add(self._spin("P_TERM_OPACITY", "Terminal opacity", "1 is solid", 0.5, 1.0, 0.05, digits=2))

        fonts = group(self, "Fonts", "The bar's own font is on the Bar page.")
        fonts.add(self._font("gtk_font", "Apps", "Text in apps like this one, file manager and settings"))
        fonts.add(self._font("term_font_name", "Terminal", "", family_only=True, monospace=True))
        fonts.add(self._spin("term_font_size", "Terminal font size", "", 6, 24, 1))
        fonts.add(self._font("dunst_font", "Notifications and menus",
                             "Pop-ups, notification center and bar dropdowns"))
        fonts.add(self._font("rofi_font", "App launcher and pickers", ""))

        notif = group(self, "Notification pop-ups")
        notif.add(self._combo("dunst_origin", "Position", [o for o, _ in ORIGINS], [t for _, t in ORIGINS]))
        notif.add(self._spin("dunst_corner_radius", "Rounded corners", "Also used by the dropdowns", 0, 24, 1))

        look = group(self, "Apps")
        themes, icons, cursors = gtk_themes(), icon_themes(), cursor_themes()
        look.add(self._combo("gtk_theme", "App theme (GTK)", themes, themes))
        self.gtk_pic = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.CONTAIN, halign=Gtk.Align.START,
                                   margin_top=10, margin_bottom=10, margin_start=14, margin_end=14)
        self.gtk_pic.add_css_class("cc-tile-image")
        self.gtk_pic.set_overflow(Gtk.Overflow.HIDDEN)
        self.gtk_wait = Gtk.Label(label="Drawing a sample window…", margin_top=12, margin_bottom=12)
        self.gtk_wait.add_css_class("dim-label")
        gtk_box = Gtk.Stack()
        gtk_box.add_named(self.gtk_wait, "wait")
        gtk_box.add_named(self.gtk_pic, "pic")
        self.gtk_box = gtk_box
        look.add(Adw.PreferencesRow(activatable=False, child=gtk_box))
        look.add(self._combo("gtk_icons", "Icons", icons, icons))
        self.icon_strip = SampleStrip()
        look.add(Adw.PreferencesRow(activatable=False, child=self.icon_strip))
        look.add(self._combo("gtk_cursor", "Mouse pointer", cursors, cursors))
        self.cursor_strip = SampleStrip()
        look.add(Adw.PreferencesRow(activatable=False, child=self.cursor_strip))

        # The app menu (super+space): a style per theme, saved right away
        self.menu = group(self, "App menu", "Opens with super+space. Saved in this theme right away.")
        self.menu.set_header_suffix(text_button("Open", lambda: launch([tool("RofiLauncher")])))
        self.menu_grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, column_spacing=4,
                                     row_spacing=4, min_children_per_line=3, max_children_per_line=3)
        self.menu.add(self.menu_grid)
        self.menu_tiles = {}
        self.menu_shown = None
        self.menu_capturing = False
        for n, name in launchershots.styles():
            self.menu_grid.append(self._menu_tile(n, name))
        self._menu_pictures(take=False)        # (new pictures only once the page is opened)

        # Not part of a theme: applied right away, for every theme
        general = group(self, "For all themes", "Applied right away (not saved with the theme).")
        self.backend = Adw.ComboRow(title="Compositor backend", subtitle="How picom draws: try another if you see glitches",
                                    model=Gtk.StringList.new(["glx", "xrender", "egl"]))
        self.backend.connect("notify::selected", self._backend)
        general.add(self.backend)
        self.vsync = Adw.SwitchRow(title="vSync", subtitle="No tearing; turn off if it makes things lag")
        self.vsync.connect("notify::active", lambda r, _p: self._updating or self._picom_set("vsync", "true" if r.get_active() else "false"))
        general.add(self.vsync)
        self.pixel = Adw.SwitchRow(title="Pixel art in new terminals", subtitle="A random colour script when a terminal opens")
        self.pixel.connect("notify::active", lambda r, _p: self._updating or self._zshrc("colorscript -r", r.get_active()))
        general.add(self.pixel)
        self.fzf = Adw.SwitchRow(title="Tab completion menu (fzf-tab)", subtitle="A searchable menu when you press Tab in the terminal")
        self.fzf.connect("notify::active", lambda r, _p: self._updating or self._zshrc("disable-fzf-tab", not r.get_active()))
        general.add(self.fzf)

        self.load()

    # ----- app menu -----

    def _menu_tile(self, n, name):
        b = Gtk.Button(tooltip_text=f"Use {name} in this theme")
        b.add_css_class("flat")
        b.add_css_class("cc-tile")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        pic = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, can_shrink=True)
        pic.set_size_request(150, 100)
        pic.add_css_class("cc-tile-image")
        pic.set_overflow(Gtk.Overflow.HIDDEN)
        label = Gtk.Label(label=name, ellipsize=3)
        label.add_css_class("cc-tile-name")
        box.append(pic)
        box.append(label)
        b.set_child(box)
        b.picture = pic
        b.connect("clicked", lambda *_: self._menu_pick(n, name))
        self.menu_tiles[n] = b
        return b

    def _menu_style(self):
        """This theme's app menu style (or the one for every theme)."""
        v = rice.theme_vars(self.rice).get("LAUNCHER_STYLE", "")
        if not v.isdigit():
            v = read_file(os.path.join(BSPDIR, "config", ".launcher"), "1").strip()
        return int(v) if v.isdigit() else 1

    def _menu_mark(self):
        cur = self._menu_style()
        for n, t in self.menu_tiles.items():
            (t.add_css_class if n == cur else t.remove_css_class)("cc-current")

    def _menu_pick(self, n, name):
        try:
            rice.set_theme_vars({"LAUNCHER_STYLE": str(n)}, self.rice)
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
            return
        self.vals["LAUNCHER_STYLE"] = str(n)
        self._menu_mark()
        self.toast(f"App menu: {name}")

    def _menu_pictures(self, take=True):
        """Show the pictures; take new ones (off-screen, a few seconds) if the
        theme or the styles changed. The old ones stay until they're ready."""
        folder = launchershots.shown_dir()
        stamp = (folder, launchershots.is_complete(folder))
        if stamp != self.menu_shown:
            self.menu_shown = stamp
            for n, t in self.menu_tiles.items():
                path = os.path.join(folder, f"style_{n}.png")
                if os.path.exists(path):
                    t.picture.set_filename(path)
        self._menu_mark()
        if not take or launchershots.is_complete(launchershots.cache_dir()) or self.menu_capturing:
            return
        self.menu_capturing = True
        launch(["python3", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                        "take-launcher-pictures.py")])

        def check():
            if launchershots.is_complete(launchershots.cache_dir()):
                self.menu_capturing = False
                self._menu_pictures()
                return False
            return True
        GLib.timeout_add_seconds(2, check)

    # ----- accent from the wallpaper -----

    def _wall_accent(self, row, _p):
        if self._updating:
            return
        on = row.get_active()
        try:
            rice.set_theme_vars({"WALL_ACCENT": "on" if on else "off"}, self.rice)
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
            return
        self.vals["WALL_ACCENT"] = "on" if on else "off"
        run_quiet([tool("AccentSync"), "--force"])
        self._wall_accent_show()
        self.toast("The accent follows your wallpaper" if on else "The theme's own accent is back")

    def _wall_accent_show(self):
        on = rice.theme_vars(self.rice).get("WALL_ACCENT", "off") == "on"
        self.quietly(lambda: self.wall_accent.set_active(on))

        def got(ok, out, _e):
            color = out.strip() if ok else ""
            if on and color:
                self.wall_accent.set_subtitle(f"Now {color}, from your wallpaper. The Accent colour below is the theme's own.")
            elif on:
                self.wall_accent.set_subtitle("Your wallpaper has no strong colour: the theme's accent is used")
            else:
                self.wall_accent.set_subtitle("Borders, bar icons, menus and dropdowns take its main colour"
                                              + (f" (it would be {color})" if color else ""))
        run([tool("WallAccent")], got)

    # ----- rows -----

    def _changed(self, var, value):
        if self._updating:
            return
        if self.vals.get(var) == value:
            self.changes.pop(var, None)
        else:
            self.changes[var] = value
        self._show_preview()
        self.window.update_pending()

    def _show_samples(self, v):
        theme = v.get("gtk_theme", "")
        if theme and theme != getattr(self, "_gtk_shown", None):
            self._gtk_shown = theme
            self.gtk_box.set_visible_child_name("wait")

            def got(path, theme=theme):
                if path and theme == self._gtk_shown:
                    info = GdkPixbuf.Pixbuf.get_file_info(path)
                    if info and info[0] is not None:
                        w = min(360, info[1])
                        self.gtk_pic.set_size_request(w, round(info[2] * w / info[1]))
                    self.gtk_pic.set_filename(path)
                    self.gtk_box.set_visible_child_name("pic")
                elif not path:
                    self.gtk_wait.set_label("No preview for this theme")
            gtk_theme_preview(theme, got)
        if v.get("gtk_icons") != getattr(self, "_icons_shown", None):
            self._icons_shown = v.get("gtk_icons")
            self.icon_strip.show(icon_samples(v.get("gtk_icons", "")))
        if v.get("gtk_cursor") != getattr(self, "_cursor_shown", None):
            self._cursor_shown = v.get("gtk_cursor")
            self.cursor_strip.show(cursor_samples(v.get("gtk_cursor", "")))

    def _show_preview(self):
        v = {**self.vals, **self.changes}
        self._show_samples(v)
        bar = v.get("main_bar", "")
        if bar and rice.is_polybar(bar):
            sections = rice.launched_sections(bar)
            font = rice.bar_text_font(bar, sections[0]) if sections else None
            if font:
                v["_bar_font"] = f"{font[0]} {font[1]:g}"
        self.preview.update(v)

    def _color_row(self, var, title, sub):
        row = Adw.ActionRow(title=title, subtitle=sub)
        btn = ColorButton(title, lambda value: self._changed(var, value))
        row.add_suffix(btn)
        row.set_activatable_widget(btn)
        self.widgets[var] = ("color", btn, row)
        return row

    def _spin(self, var, title, sub, lo, hi, step, digits=0):
        row = Adw.SpinRow.new_with_range(lo, hi, step)
        row.set_title(title)
        row.set_subtitle(sub)
        row.set_digits(digits)
        fmt = (lambda v: f"{v:.2f}") if digits else (lambda v: str(int(round(v))))
        row.connect("notify::value", lambda r, _p: self._changed(var, fmt(r.get_value())))
        self.widgets[var] = ("spin", row, fmt)
        return row

    def _switch(self, var, title, sub="", on="true", off="false"):
        row = Adw.SwitchRow(title=title, subtitle=sub)
        row.connect("notify::active", lambda r, _p: self._changed(var, on if r.get_active() else off))
        self.widgets[var] = ("switch", row, on)
        return row

    def _combo(self, var, title, values, labels):
        row = Adw.ComboRow(title=title, model=Gtk.StringList.new(labels))
        row.values = list(values)
        row.set_enable_search(len(values) > 8)

        def picked(r, _p):
            if r.get_selected() < len(r.values):
                self._changed(var, r.values[r.get_selected()])
        row.connect("notify::selected", picked)
        self.widgets[var] = ("combo", row, None)
        return row

    def _font(self, var, title, sub, family_only=False, monospace=False):
        row = Adw.ActionRow(title=title, subtitle=sub)
        btn = FontButton(title, lambda desc: self._changed(var, self._font_value(desc, family_only)),
                         family_only=family_only, monospace=monospace)
        row.add_suffix(btn)
        row.set_activatable_widget(btn)
        self.widgets[var] = ("font", btn, family_only)
        return row

    # ----- "for all themes" options -----

    PICOM = os.path.join(BSPDIR, "config", "picom", "picom.conf")
    ZSHRC = os.path.join(HOME, ".zshrc")

    def _picom_get(self, key):
        m = re.search(rf'(?m)^{key}\s*=\s*"?([^";]+)"?;', read_file(self.PICOM))
        return m.group(1).strip() if m else ""

    def _picom_set(self, key, value):
        text = read_file(self.PICOM)
        quoted = f'"{value}"' if key == "backend" else value
        new = re.sub(rf'(?m)^{key}\s*=.*$', f"{key} = {quoted};", text, count=1)
        try:
            with open(self.PICOM, "w") as f:
                f.write(new + "\n")
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
            return
        run_quiet(["pkill", "-USR1", "-x", "picom"])        # picom re-reads its config
        self.toast("Compositor updated")

    def _backend(self, row, _p):
        if not self._updating:
            self._picom_set("backend", ["glx", "xrender", "egl"][row.get_selected()])

    def _zshrc_on(self, marker):
        for line in read_file(self.ZSHRC).splitlines():
            if marker in line:
                return not line.lstrip().startswith("#")
        return False

    def _zshrc(self, marker, on):
        """Comment or uncomment the line in ~/.zshrc that contains marker."""
        try:
            with open(self.ZSHRC) as f:
                lines = f.read().split("\n")
        except OSError:
            return
        for i, line in enumerate(lines):
            if marker in line:
                bare = line.lstrip().lstrip("#").lstrip()
                lines[i] = bare if on else "# " + bare
                break
        else:
            return
        with open(self.ZSHRC, "w") as f:
            f.write("\n".join(lines))
        self.toast("Applied to new terminals")

    def _load_general(self):
        backend = self._picom_get("backend")
        def put():
            if backend in ("glx", "xrender", "egl"):
                self.backend.set_selected(["glx", "xrender", "egl"].index(backend))
            self.vsync.set_active(self._picom_get("vsync") == "true")
            self.pixel.set_active(self._zshrc_on("colorscript -r"))
            self.fzf.set_active(not self._zshrc_on("disable-fzf-tab"))
        self.quietly(put)

    @staticmethod
    def _font_value(desc, family_only):
        if family_only:
            return desc.get_family() or ""
        size = desc.get_size() / Pango.SCALE if desc.get_size() else 10
        d = Pango.FontDescription.from_string(desc.to_string())
        d.unset_fields(Pango.FontMask.SIZE)
        return f"{d.to_string()} {size:g}"

    # ----- load / apply -----

    def load(self):
        self.rice = current_rice()
        v = rice.theme_vars(self.rice)
        if not v.get("gtk_font"):
            v["gtk_font"] = current_app_font()
        self.vals = v
        self.changes = {}
        self.intro_row.set_title(f"Editing {self.rice.capitalize()}")
        self.intro_row.set_subtitle("Changes are saved in this theme. Reset brings back its original look."
                                    if rice.has_original(rice.theme_file()) else
                                    "Changes are saved in this theme. Its original is kept so you can go back.")
        self.reset_btn.set_sensitive(rice.has_original(rice.theme_file()))

        def put():
            for var, (kind, w, extra) in self.widgets.items():
                val = v.get(var, "")
                w.set_sensitive(var in v)
                if kind == "color":
                    c = Gdk.RGBA()
                    if _hex(val) and c.parse(_hex(val)):
                        w.set_hex(_hex(val))
                elif kind == "spin":
                    try:
                        w.set_value(float(val))
                    except ValueError:
                        pass
                elif kind == "switch":
                    w.set_active(val == extra)
                elif kind == "combo":
                    if val not in w.values and val:
                        w.values.append(val)
                        w.get_model().append(val)
                    if val in w.values:
                        w.set_selected(w.values.index(val))
                elif kind == "font":
                    if val:
                        w.set_desc(Pango.FontDescription.from_string(val))
        self.quietly(put)
        self._wall_accent_show()
        self._load_general()
        self._show_preview()
        self.window.update_pending()

    def refresh(self):
        if current_rice() != self.rice and not self.changes:
            self.load()
        self._menu_pictures()

    def pending_text(self):
        n = len(self.changes)
        return f"{n} unsaved change{'s' if n != 1 else ''} to {self.rice.capitalize()}" if n else ""

    def discard(self):
        self.load()

    def _changes_to_write(self):
        changes = dict(self.changes)
        # The bar's see-through background follows a new background colour
        if "bg" in changes and "bg_alpha_css" in self.vals:
            m = re.search(r"rgba\([^)]*,\s*([\d.]+)\s*\)", self.vals["bg_alpha_css"])
            if m:
                h = changes["bg"].lstrip("#")
                r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
                changes["bg_alpha_css"] = f"rgba({r}, {g}, {b}, {m.group(1)})"
        return changes

    def apply(self):
        try:
            rice.set_theme_vars(self._changes_to_write())
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
            return
        self.changes = {}
        self.window.update_pending()
        self._run_theme("Applying your changes…", "Changes applied")

    def try_out(self):
        """Use the changes on the real desktop, then keep them or go back
        (automatically after 15 seconds)."""
        path = rice.theme_file()
        had_original = rice.has_original(path)
        with open(path) as f:
            before = f.read()
        try:
            rice.set_theme_vars(self._changes_to_write())
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
            return
        self.set_sensitive(False)
        self.window.pending_bar.set_sensitive(False)

        def ask(_ok):
            left = [15]
            d = Adw.AlertDialog(heading="Keep these changes?", body=f"Going back in {left[0]} seconds…")
            d.add_response("back", "Go Back")
            d.add_response("keep", "Keep")
            d.set_response_appearance("keep", Adw.ResponseAppearance.SUGGESTED)
            d.set_default_response("keep")
            d.set_close_response("back")

            def tick():
                left[0] -= 1
                if left[0] <= 0:
                    d.force_close()
                    return False
                d.set_body(f"Going back in {left[0]} seconds…")
                return True
            timer = GLib.timeout_add_seconds(1, tick)

            def answered(_d, response):
                if left[0] > 0:
                    GLib.source_remove(timer)
                self.window.pending_bar.set_sensitive(True)
                if response == "keep":
                    self.set_sensitive(True)
                    self.changes = {}
                    self.load()
                    self.toast("Changes kept")
                    return
                # Back to how it was; the edits stay here to adjust or discard
                if had_original:
                    with open(path, "w") as f:
                        f.write(before)
                else:
                    rice.restore_original(path)       # untouched again: no backup needed

                def back(_ok):
                    self.set_sensitive(True)
                    self.toast("Went back. Your edits are still here.")
                    self.window.update_pending()
                run_quiet([tool("Theme.sh")], back)
            d.connect("response", answered)
            d.present(self.window)
        run_quiet([tool("Theme.sh")], ask)

    def _run_theme(self, start, done):
        self.toast(start)
        self.set_sensitive(False)

        def finished(_ok):
            self.set_sensitive(True)
            self.load()
            self.toast(done)
        run_quiet([tool("Theme.sh")], finished)

    def _reset(self):
        d = Adw.AlertDialog(heading=f"Reset {self.rice.capitalize()}?",
                            body="All changes made to this theme here are undone.")
        d.add_response("cancel", "Cancel")
        d.add_response("reset", "Reset")
        d.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)

        def answered(_d, r):
            if r == "reset" and rice.restore_original(rice.theme_file()):
                self.changes = {}
                self._run_theme("Resetting…", f"{self.rice.capitalize()} is back to its original look")
        d.connect("response", answered)
        d.present(self.window)
