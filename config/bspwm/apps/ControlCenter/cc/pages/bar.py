"""Bar: pick the bar design for the current theme, edit which items it shows
and in what order, and its text font. Item and font changes are collected
and applied together with "Apply"."""

import hashlib
import os
import re

from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk, Pango

from .. import rice
from ..common import CACHE, Page, current_rice, group, icon_button, run_quiet, text_button, tool, widgets_changed
from ..common import _pool
from ..pickers import FontButton
from .appearance import grid, tile

SIDES = [("left", "Left"), ("center", "Center"), ("right", "Right")]

FRIENDLY = {
    "bspwm": ("Workspaces", "view-grid-symbolic"),
    "title": ("Window title", "focus-windows-symbolic"),
    "launcher": ("App launcher", "view-app-grid-symbolic"),
    "tray": ("System tray", "view-more-horizontal-symbolic"),
    "pulseaudio": ("Volume", "audio-volume-high-symbolic"),
    "network": ("Network", "network-wireless-symbolic"),
    "battery": ("Battery", "battery-good-symbolic"),
    "date": ("Clock", "preferences-system-time-symbolic"),
    "notifications": ("Notifications", "preferences-system-notifications-symbolic"),
    "power": ("Power button", "system-shutdown-symbolic"),
    "updates": ("Updates", "software-update-available-symbolic"),
    "mplayer": ("Now playing", "audio-x-generic-symbolic"),
    "mpd": ("Music (MPD)", "audio-x-generic-symbolic"),
    "mpd_control": ("Music controls", "media-playback-start-symbolic"),
    "layout": ("Window layout", "view-dual-symbolic"),
    "mod": ("Layout mode", "view-dual-symbolic"),
    "filesystem": ("Storage", "drive-harddisk-symbolic"),
    "cpu_bar": ("Processor", "computer-symbolic"),
    "cpu": ("Processor", "computer-symbolic"),
    "memory_bar": ("Memory", "drive-multidisk-symbolic"),
    "memory": ("Memory", "drive-multidisk-symbolic"),
    "bluetooth": ("Bluetooth", "bluetooth-active-symbolic"),
    "usercard": ("User card", "avatar-default-symbolic"),
    "r00t": ("User menu", "avatar-default-symbolic"),
    "colorpicker": ("Color picker", "color-select-symbolic"),
    "weather": ("Weather", "weather-few-clouds-symbolic"),
    "xkeyboard": ("Keyboard layout", "input-keyboard-symbolic"),
    "brightness": ("Brightness", "display-brightness-symbolic"),
    "vpn": ("VPN", "network-vpn-symbolic"),
    "target": ("Target", "find-location-symbolic"),
    "terminal": ("Terminal shortcut", "utilities-terminal-symbolic"),
    "filem": ("Files shortcut", "system-file-manager-symbolic"),
    "editor": ("Editor shortcut", "accessories-text-editor-symbolic"),
    "browser": ("Browser shortcut", "web-browser-symbolic"),
    "whats": ("WhatsApp shortcut", "chat-symbolic"),
    "fetch": ("System info shortcut", "dialog-information-symbolic"),
}


PREVIEW_W = 480


def _strips(pix):
    """The bar(s) in a mostly see-through preview image, as pixbufs."""
    w, h, rs = pix.get_width(), pix.get_height(), pix.get_rowstride()
    if not pix.get_has_alpha():
        return [pix]
    px = pix.get_pixels()
    rows = [max(px[y * rs + 3:y * rs + w * 4:4]) > 20 for y in range(h)]
    if all(rows):
        return [pix]                     # a full screenshot: show it whole
    bands, start = [], None
    for y, on in enumerate(rows + [False]):
        if on and start is None:
            start = y
        elif not on and start is not None:
            if y - start >= 4:
                bands.append((start, y))
            start = None
    out = []
    for y0, y1 in bands:
        samples = range(y0, y1, max(1, (y1 - y0) // 12))
        cols = [x for x in range(w) if any(px[y * rs + x * 4 + 3] > 20 for y in samples)]
        if not cols:
            continue
        x0, x1 = cols[0], cols[-1] + 1
        piece = pix.new_subpixbuf(x0, y0, x1 - x0, y1 - y0).copy()
        if piece.get_width() < piece.get_height():          # a bar on the side
            piece = piece.rotate_simple(GdkPixbuf.PixbufRotation.COUNTERCLOCKWISE)
        out.append(piece)
    return out or [pix]


def bar_preview(path, done):
    """A readable picture of a bar: long bars are cut in two halves, stacked."""
    try:
        st = os.stat(path)
    except OSError:
        done(None)
        return
    key = hashlib.sha1(f"bar3:{path}:{st.st_mtime_ns}:{PREVIEW_W}".encode()).hexdigest()
    cached = os.path.join(CACHE, "thumbs", key + ".png")

    def work():
        try:
            if not os.path.exists(cached):
                pieces = []
                for strip in _strips(GdkPixbuf.Pixbuf.new_from_file(path)):
                    sw, sh = strip.get_width(), strip.get_height()
                    if sw > PREVIEW_W * 1.2 and sw > sh * 6:      # long and thin: two halves
                        half = sw // 2
                        pieces += [strip.new_subpixbuf(0, 0, half, sh), strip.new_subpixbuf(half, 0, sw - half, sh)]
                    else:
                        pieces.append(strip)
                scaled = []
                for p in pieces:
                    limit = PREVIEW_W if p.get_width() > p.get_height() * 4 else PREVIEW_W * 0.6   # screenshots smaller
                    f = min(1.0, limit / p.get_width())
                    scaled.append(p.scale_simple(max(1, round(p.get_width() * f)), max(1, round(p.get_height() * f)),
                                                 GdkPixbuf.InterpType.BILINEAR))
                gap = 6
                height = sum(p.get_height() for p in scaled) + gap * (len(scaled) - 1)
                width = max(p.get_width() for p in scaled)
                out = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, width, max(1, height))
                out.fill(0)
                y = 0
                for p in scaled:
                    p.copy_area(0, 0, p.get_width(), p.get_height(), out, 0, y)
                    y += p.get_height() + gap
                os.makedirs(os.path.dirname(cached), exist_ok=True)
                out.savev(cached, "png", [], [])
            return Gdk.Texture.new_from_filename(cached)
        except (GLib.Error, OSError, ValueError):
            return None

    f = _pool.submit(work)
    f.add_done_callback(lambda fut: GLib.idle_add(lambda: (done(fut.result()), widgets_changed(), False)[2]))


def module_sections(bar):
    """{name: {key: value}} for every [module/...] the bar defines."""
    out = {}
    for fname in ("modules.ini", "config.ini"):
        try:
            with open(os.path.join(rice.BARS, bar, fname)) as f:
                text = f.read()
        except OSError:
            continue
        for m in re.finditer(r"(?ms)^\[module/([^\]]+)\]\n(.*?)(?=^\[|\Z)", text):
            keys = dict(re.findall(r"(?m)^([\w-]+)\s*=\s*(.*)$", m.group(2)))
            out[m.group(1)] = keys
    return out


def describe(name, info):
    """(title, icon, is_decoration)"""
    if name in FRIENDLY:
        return FRIENDLY[name] + (False,)
    if info.get("type") == "custom/text" and not any(k.startswith("click") for k in info):
        label = re.sub(r"%\{[^}]*\}", "", info.get("label", info.get("content", ""))).strip().strip('"').strip()
        if not label:
            return ("Space", "format-justify-fill-symbolic", True)
        return ("Divider" if label in ("|", "󰇙", "[", "]", "•", "·") else "Edge piece",
                "format-justify-fill-symbolic", True)
    return (name.replace("_", " ").replace("-", " ").capitalize(), "application-x-addon-symbolic", False)


class BarPage(Page):
    name = "bar"
    title = "Bar"
    icon = "view-continuous-symbolic"
    interval = 3

    def __init__(self, window):
        super().__init__(window)
        self.rice = None
        self.bar = None
        self.section = None
        self.saved = {}       # section -> layout as in the file
        self.edits = {}       # section -> edited layout
        self.font_change = None
        self.item_rows = []
        self.modules = {}
        self.sections = []

        # Designs: the current one, and all of them behind "Change…"
        designs = group(self, "Bar design", "Which bar this theme uses")
        self.current_pic = Gtk.Picture(content_fit=Gtk.ContentFit.SCALE_DOWN, can_shrink=False,
                                       halign=Gtk.Align.CENTER, margin_top=12, margin_bottom=6)
        self.current_name = Gtk.Label(margin_bottom=10)
        self.current_name.add_css_class("heading")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(self.current_pic)
        box.append(self.current_name)
        designs.add(Adw.PreferencesRow(activatable=False, child=box))
        self.change = Gtk.ToggleButton(label="Change…", valign=Gtk.Align.CENTER)
        designs.set_header_suffix(self.change)
        self.design_grid = grid(1)
        self.design_grid.set_homogeneous(False)      # each preview as tall as it needs
        self.design_reveal = Gtk.Revealer(child=self.design_grid, transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.change.bind_property("active", self.design_reveal, "reveal-child")
        self.change.connect("toggled", lambda b: b.set_label("Close" if b.get_active() else "Change…"))
        designs.add(self.design_reveal)
        self.design_tiles = {}
        self.previews = {}
        users = {}
        for r in sorted(os.listdir(os.path.join(rice.BARS, "..", "rices"))):
            b = rice.theme_vars(r).get("main_bar")
            if b:
                users.setdefault(b, []).append(r.capitalize())
        self.users = users
        for b in rice.bar_names():
            label = b + (f" · {', '.join(users[b][:2])}" if b in users else "")
            t = tile(label, 2, 2)
            t.picture.set_content_fit(Gtk.ContentFit.SCALE_DOWN)
            t.picture.set_can_shrink(False)
            t.picture.remove_css_class("cc-tile-image")
            t.connect("clicked", lambda _b, b=b: self.pick_design(b))
            self.design_grid.append(t)
            self.design_tiles[b] = t

            def got(tex, t=t, b=b):
                if tex:
                    t.picture.set_paintable(tex)
                    self.previews[b] = tex
                    if b == self.bar:
                        self.current_pic.set_paintable(tex)
            bar_preview(os.path.join(rice.BARS, b, "preview-bar.webp"), got)

        # Items
        self.items = group(self)
        self.which = Adw.ComboRow(title="Bar", subtitle="This design has more than one bar")
        self.which.connect("notify::selected", self._which)
        self.items.add(self.which)
        self.not_polybar = Adw.ActionRow(title="This bar is made with eww",
                                         subtitle="Its items can't be edited here yet. Pick another design to edit items.")
        self.not_polybar.add_prefix(Gtk.Image.new_from_icon_name("dialog-information-symbolic"))
        self.items.add(self.not_polybar)
        self.side_groups = {}
        for side, title in SIDES:
            g = group(self, title)
            add = Gtk.MenuButton(icon_name="list-add-symbolic", tooltip_text=f"Add an item on the {title.lower()}",
                                 valign=Gtk.Align.CENTER)
            add.add_css_class("flat")
            add.set_popover(self._add_popover(side, add))
            g.set_header_suffix(add)
            self.side_groups[side] = g

        # Font and reset
        self.extra = group(self, "Text")
        self.font_row = Adw.ActionRow(title="Bar font", subtitle="Used for the bar's text. Icons keep their own fonts.")
        self.font_btn = FontButton("Bar font", self._font)
        self.font_row.add_suffix(self.font_btn)
        self.font_row.set_activatable_widget(self.font_btn)
        self.extra.add(self.font_row)
        self.reset_row = Adw.ActionRow(title="Reset this bar", subtitle="Undo all item and font changes made here")
        self.reset_row.add_suffix(text_button("Reset…", self._reset))
        self.extra.add(self.reset_row)

        self.load()

    # ----- loading -----

    def load(self):
        self.rice = current_rice()
        self.bar = rice.theme_vars(self.rice).get("main_bar", "")
        self.edits = {}
        self.font_change = None
        for b, t in self.design_tiles.items():
            (t.add_css_class if b == self.bar else t.remove_css_class)("cc-current")
        self.current_pic.set_paintable(self.previews.get(self.bar))
        self.current_name.set_label(self.bar + (f" · {', '.join(self.users[self.bar][:2])}" if self.bar in self.users else ""))
        poly = bool(self.bar) and rice.is_polybar(self.bar)
        self.not_polybar.set_visible(not poly)
        self.items.set_visible(not poly)
        for g in self.side_groups.values():
            g.set_visible(poly)
        self.extra.set_visible(poly)
        self.which.set_visible(False)
        if not poly:
            self._fill_items()
            self.window.update_pending()
            return
        self.modules = module_sections(self.bar)
        sections = rice.launched_sections(self.bar) or [
            n[4:] for n in re.findall(r"(?m)^\[(bar/[^\]]+)\]", open(rice.bar_config(self.bar)).read())]
        self.sections = sections
        self.saved = {s: rice.bar_layout(self.bar, s) for s in sections}
        self.quietly(lambda: (self.which.set_model(Gtk.StringList.new(sections)), self.which.set_selected(0)))
        self.which.set_visible(len(sections) > 1)
        self.items.set_visible(len(sections) > 1)
        self.section = sections[0] if sections else None
        font = rice.bar_text_font(self.bar, self.section) if self.section else None
        self.font_row.set_visible(font is not None)
        if font:
            self.font_btn.set_desc(Pango.FontDescription.from_string(f"{font[0]} {font[1]:g}"))
        self.reset_row.set_sensitive(rice.has_original(rice.bar_config(self.bar)))
        self.side_groups["left"].set_description(f"What {self.bar} shows, from left to right")
        self._fill_items()
        self.window.update_pending()

    def refresh(self):
        if not self.pending_text():
            r = current_rice()
            if r != self.rice or rice.theme_vars(r).get("main_bar", "") != self.bar:
                self.load()

    def layout(self):
        return self.edits.get(self.section) or self.saved.get(self.section, {"left": [], "center": [], "right": []})

    def _which(self, combo, _p):
        if not self._updating and combo.get_selected() < len(self.sections):
            self.section = self.sections[combo.get_selected()]
            self._fill_items()

    # ----- item rows -----

    def _fill_items(self):
        for g, r in self.item_rows:
            g.remove(r)
        self.item_rows.clear()
        if not self.bar or not rice.is_polybar(self.bar) or not self.section:
            return
        lay = self.layout()
        for side, _title in SIDES:
            g = self.side_groups[side]
            items = lay[side]
            if not items:
                r = Adw.ActionRow(title="Nothing here")
                r.add_css_class("dim-label")
                g.add(r)
                self.item_rows.append((g, r))
            for i, name in enumerate(items):
                title, icon, deco = describe(name, self.modules.get(name, {}))
                r = Adw.ActionRow(title=title, subtitle=name)
                img = Gtk.Image.new_from_icon_name(icon)
                if deco:
                    r.add_css_class("dim-label")
                    img.set_opacity(0.5)
                r.add_prefix(img)
                up = icon_button("go-up-symbolic", "Move left", lambda s=side, i=i: self._move(s, i, -1))
                up.set_sensitive(i > 0)
                down = icon_button("go-down-symbolic", "Move right", lambda s=side, i=i: self._move(s, i, 1))
                down.set_sensitive(i < len(items) - 1)
                r.add_suffix(up)
                r.add_suffix(down)
                r.add_suffix(self._move_menu(side, i))
                r.add_suffix(icon_button("list-remove-symbolic", "Remove from the bar", lambda s=side, i=i: self._remove(s, i)))
                g.add(r)
                self.item_rows.append((g, r))

    def _move_menu(self, side, i):
        btn = Gtk.MenuButton(icon_name="view-more-symbolic", tooltip_text="Move to another part", valign=Gtk.Align.CENTER)
        btn.add_css_class("flat")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=4, margin_bottom=4,
                      margin_start=4, margin_end=4)
        pop = Gtk.Popover(child=box)
        for other, title in SIDES:
            if other == side:
                continue
            b = Gtk.Button(label=f"Move to {title.lower()}")
            b.add_css_class("flat")
            b.connect("clicked", lambda _b, o=other: (pop.popdown(), self._to_side(side, i, o)))
            box.append(b)
        btn.set_popover(pop)
        return btn

    def _add_popover(self, side, button):
        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        listbox.add_css_class("navigation-sidebar")
        scroller = Gtk.ScrolledWindow(child=listbox, propagate_natural_height=True, max_content_height=360,
                                      hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_size_request(260, -1)
        pop = Gtk.Popover(child=scroller)

        def showing(_p):
            while (row := listbox.get_first_child()) is not None:
                listbox.remove(row)
            lay = self.layout()
            used = set(lay["left"] + lay["center"] + lay["right"])
            entries = []
            for name, info in self.modules.items():
                title, icon, deco = describe(name, info)
                if info.get("type", "").startswith(("internal/", "custom/")):
                    entries.append((deco, title.lower(), name, title, icon))
            for deco, _k, name, title, icon in sorted(entries):
                box = Gtk.Box(spacing=10)
                box.append(Gtk.Image.new_from_icon_name(icon))
                lbl = Gtk.Label(label=title, xalign=0, hexpand=True)
                box.append(lbl)
                if name in used and not deco:
                    on = Gtk.Label(label="on bar")
                    on.add_css_class("dim-label")
                    box.append(on)
                row = Gtk.ListBoxRow(child=box, activatable=True)
                row.set_tooltip_text(name)
                row.module = name
                listbox.append(row)
            widgets_changed()

        def picked(_l, row):
            pop.popdown()
            self._add(side, row.module)
        listbox.connect("row-activated", picked)
        pop.connect("show", showing)
        return pop

    # ----- edits -----

    def _edit(self, fn):
        lay = {k: list(v) for k, v in self.layout().items()}
        fn(lay)
        if lay == self.saved.get(self.section):
            self.edits.pop(self.section, None)
        else:
            self.edits[self.section] = lay
        self._fill_items()
        self.window.update_pending()

    def _move(self, side, i, step):
        def f(lay):
            items = lay[side]
            j = i + step
            if 0 <= j < len(items):
                items[i], items[j] = items[j], items[i]
        self._edit(f)

    def _to_side(self, side, i, other):
        def f(lay):
            name = lay[side].pop(i)
            # Into the left part: at its end; into the right part: at its start
            if other == "right":
                lay[other].insert(0, name)
            else:
                lay[other].append(name)
        self._edit(f)

    def _remove(self, side, i):
        self._edit(lambda lay: lay[side].pop(i))

    def _add(self, side, name):
        self._edit(lambda lay: lay[side].append(name))

    def _font(self, desc):
        if desc:
            size = desc.get_size() / Pango.SCALE if desc.get_size() else 10
            self.font_change = (desc.get_family(), size)
            self.window.update_pending()

    # ----- apply / discard / reset -----

    def pending_text(self):
        n = sum(1 for _ in self.edits) + (1 if self.font_change else 0)
        if not n:
            return ""
        what = " and ".join(w for w, on in (("items", self.edits), ("font", self.font_change)) if on)
        return f"Unsaved changes to {self.bar}'s {what}"

    def discard(self):
        self.load()

    def apply(self):
        try:
            for section, lay in self.edits.items():
                rice.set_bar_layout(self.bar, section, lay)
            if self.font_change:
                rice.set_bar_text_font(self.bar, *self.font_change)
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
            return
        self.edits = {}
        self.font_change = None
        self.toast("Updating the bar…")
        run_quiet(["polybar-msg", "cmd", "restart"], lambda _ok: (self.load(), self.toast("Bar updated")))
        self.window.update_pending()

    def _reset(self):
        d = Adw.AlertDialog(heading=f"Reset {self.bar}?", body="Its items and font go back to how they were.")
        d.add_response("cancel", "Cancel")
        d.add_response("reset", "Reset")
        d.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)

        def answered(_d, r):
            if r == "reset" and rice.restore_original(rice.bar_config(self.bar)):
                run_quiet(["polybar-msg", "cmd", "restart"], lambda _ok: (self.load(), self.toast(f"{self.bar} is reset")))
        d.connect("response", answered)
        d.present(self.window)

    # ----- design -----

    def pick_design(self, bar):
        if bar == self.bar:
            return
        if self.pending_text():
            self.toast("Apply or discard your changes first")
            return
        try:
            rice.set_theme_vars({"main_bar": bar}, self.rice)
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
            return
        self.change.set_active(False)
        self.toast(f"Switching to {bar}…")
        self.set_sensitive(False)
        run_quiet([tool("Theme.sh")], lambda _ok: (self.set_sensitive(True), self.load(), self.toast(f"Now using {bar}")))
