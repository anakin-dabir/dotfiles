"""Customize: edit the current theme (colours, windows, fonts, notifications,
GTK look). Changes are collected and applied together with "Apply"."""

import glob
import os
import re

from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk, Pango

from .. import rice
from ..pickers import ColorButton, FontButton
from ..preview import DesktopPreview
from ..samples import SampleStrip, cursor_samples, gtk_theme_preview, icon_samples
from ..common import Page, current_rice, group, read_file, run_quiet, text_button, tool

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

        self.load()

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

    def _switch(self, var, title, sub=""):
        row = Adw.SwitchRow(title=title, subtitle=sub)
        row.connect("notify::active", lambda r, _p: self._changed(var, "true" if r.get_active() else "false"))
        self.widgets[var] = ("switch", row, None)
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
                    w.set_active(val == "true")
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
        self._show_preview()
        self.window.update_pending()

    def refresh(self):
        if current_rice() != self.rice and not self.changes:
            self.load()

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
