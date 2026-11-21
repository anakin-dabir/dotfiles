"""Customize: edit the current theme (colours, windows, fonts, notifications,
GTK look). Changes are collected and applied together with "Apply"."""

import glob
import os
import re

from gi.repository import Adw, Gdk, Gtk, Pango

from .. import rice
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


def _rgba_hex(rgba):
    return "#%02X%02X%02X" % (round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255))


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


def _monospace(item):
    fam = item if isinstance(item, Pango.FontFamily) else item.get_family()
    return fam.is_monospace()


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
        fonts.add(self._font("gtk_font", "Apps", "Text in apps like this one, file manager and settings",
                             Gtk.FontLevel.FONT))
        fonts.add(self._font("term_font_name", "Terminal", "", Gtk.FontLevel.FAMILY, monospace=True))
        fonts.add(self._spin("term_font_size", "Terminal font size", "", 6, 24, 1))
        fonts.add(self._font("dunst_font", "Notifications and menus",
                             "Pop-ups, notification center and bar dropdowns", Gtk.FontLevel.FONT))
        fonts.add(self._font("rofi_font", "App launcher and pickers", "", Gtk.FontLevel.FONT))

        notif = group(self, "Notification pop-ups")
        notif.add(self._combo("dunst_origin", "Position", [o for o, _ in ORIGINS], [t for _, t in ORIGINS]))
        notif.add(self._spin("dunst_corner_radius", "Rounded corners", "Also used by the dropdowns", 0, 24, 1))

        look = group(self, "Apps")
        themes, icons, cursors = gtk_themes(), icon_themes(), cursor_themes()
        look.add(self._combo("gtk_theme", "App theme (GTK)", themes, themes))
        look.add(self._combo("gtk_icons", "Icons", icons, icons))
        look.add(self._combo("gtk_cursor", "Mouse pointer", cursors, cursors))

        self.load()

    # ----- rows -----

    def _changed(self, var, value):
        if self._updating:
            return
        if self.vals.get(var) == value:
            self.changes.pop(var, None)
        else:
            self.changes[var] = value
        self.window.update_pending()

    def _color_row(self, var, title, sub):
        row = Adw.ActionRow(title=title, subtitle=sub)
        btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False, title=title), valign=Gtk.Align.CENTER)
        btn.connect("notify::rgba", lambda b, _p: self._changed(var, _rgba_hex(b.get_rgba())))
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

    def _font(self, var, title, sub, level, monospace=False):
        row = Adw.ActionRow(title=title, subtitle=sub)
        dialog = Gtk.FontDialog(title=title)
        if monospace:
            dialog.set_filter(Gtk.CustomFilter.new(_monospace))
        btn = Gtk.FontDialogButton(dialog=dialog, level=level, valign=Gtk.Align.CENTER, use_font=True)
        btn.connect("notify::font-desc", lambda b, _p: self._changed(var, self._font_value(b, level)))
        row.add_suffix(btn)
        row.set_activatable_widget(btn)
        self.widgets[var] = ("font", btn, level)
        return row

    @staticmethod
    def _font_value(btn, level):
        desc = btn.get_font_desc()
        if desc is None:
            return ""
        if level == Gtk.FontLevel.FAMILY:
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
                        w.set_rgba(c)
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
                        w.set_font_desc(Pango.FontDescription.from_string(val))
        self.quietly(put)
        self.window.update_pending()

    def refresh(self):
        if current_rice() != self.rice and not self.changes:
            self.load()

    def pending_text(self):
        n = len(self.changes)
        return f"{n} unsaved change{'s' if n != 1 else ''} to {self.rice.capitalize()}" if n else ""

    def discard(self):
        self.load()

    def apply(self):
        changes = dict(self.changes)
        # The bar's see-through background follows a new background colour
        if "bg" in changes and "bg_alpha_css" in self.vals:
            m = re.search(r"rgba\([^)]*,\s*([\d.]+)\s*\)", self.vals["bg_alpha_css"])
            if m:
                h = changes["bg"].lstrip("#")
                r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
                changes["bg_alpha_css"] = f"rgba({r}, {g}, {b}, {m.group(1)})"
        try:
            rice.set_theme_vars(changes)
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
            return
        self.changes = {}
        self.window.update_pending()
        self._run_theme("Applying your changes…", "Changes applied")

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
