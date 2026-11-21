"""Windows: how windows are arranged (layouts, bin/Layout) and what happens
when an app opens (window rules, bin/ExternalRules)."""

import json
import math
import re
import subprocess

import gi

from gi.repository import Adw, Gio, GLib, Gtk

from .. import rules
from ..common import Page, group, quick, run_quiet, text_button, tool, widgets_changed

try:
    gi.require_version("GioUnix", "2.0")
    from gi.repository import GioUnix
    DesktopAppInfo = GioUnix.DesktopAppInfo
except (ImportError, ValueError):
    DesktopAppInfo = Gio.DesktopAppInfo

LAYOUTS = [("tiled", "Split"), ("tall", "Main on the left"), ("rtall", "Main on the right"),
           ("wide", "Main on top"), ("rwide", "Main at the bottom"), ("grid", "Grid"), ("even", "Columns"),
           ("monocle", "One at a time")]
POPUPS = {"FloaTerm": "Floating terminal", "Updating": "Updates window", "YaziTerm": "Files pop-up (yazi)",
          "MusicTerm": "Music pop-up", "FetchTerm": "System info pop-up", "Toolkit": "Toolkit pop-up",
          "Scratch": "Scratchpad terminal", "Xdg-desktop-portal-gtk": "“Choose a file” windows",
          "ControlCenter": "Control Center"}


# ----- layout pictures -----

def _boxes(name):
    """Window rectangles (x, y, w, h in 0..1) for a layout picture."""
    if name == "tiled":
        return [(0, 0, .5, 1), (.5, 0, .5, .5), (.5, .5, .5, .5)]
    if name in ("tall", "rtall"):
        m = [(0, 0, .58, 1)] + [(.58, i / 3, .42, 1 / 3) for i in range(3)]
        return m if name == "tall" else [(1 - x - w, y, w, h) for x, y, w, h in m]
    if name in ("wide", "rwide"):
        m = [(0, 0, 1, .58)] + [(i / 3, .58, 1 / 3, .42) for i in range(3)]
        return m if name == "wide" else [(x, 1 - y - h, w, h) for x, y, w, h in m]
    if name == "grid":
        return [(0, 0, .5, .5), (.5, 0, .5, .5), (0, .5, .5, .5), (.5, .5, .5, .5)]
    if name == "even":
        return [(i / 3, 0, 1 / 3, 1) for i in range(3)]
    return [(0, 0, 1, 1)]


def layout_picture(name, accent):
    area = Gtk.DrawingArea(content_width=120, content_height=72)

    def draw(_a, cr, w, h):
        gap = 4
        for i, (x, y, bw, bh) in enumerate(_boxes(name)):
            rx, ry = x * w + gap / 2, y * h + gap / 2
            rw, rh = bw * w - gap, bh * h - gap
            r = 5
            cr.new_sub_path()
            cr.arc(rx + rw - r, ry + r, r, -math.pi / 2, 0)
            cr.arc(rx + rw - r, ry + rh - r, r, 0, math.pi / 2)
            cr.arc(rx + r, ry + rh - r, r, math.pi / 2, math.pi)
            cr.arc(rx + r, ry + r, r, math.pi, 3 * math.pi / 2)
            cr.close_path()
            cr.set_source_rgba(accent.red, accent.green, accent.blue, 0.85 if i == 0 else 0.4)
            cr.fill()
    area.set_draw_func(draw)
    return area


# ----- apps: names and icons for window classes -----

def app_for(cls):
    """(name, Gio.Icon or None) for a window class, from installed apps."""
    low = cls.lower()
    for a in Gio.AppInfo.get_all():
        if not isinstance(a, DesktopAppInfo):
            continue
        wm = (a.get_startup_wm_class() or "").lower()
        aid = (a.get_id() or "").lower().removesuffix(".desktop")
        exe = (a.get_executable() or "").split("/")[-1].lower()
        if low in (wm, aid, exe) or (aid and aid.split(".")[-1] == low):
            return a.get_name(), a.get_icon()
    return None, None


def open_classes():
    """Window classes open right now."""
    out = []
    for nid in quick(["bspc", "query", "-N", "-n", ".window"]).split():
        m = re.search(r'"([^"]*)",\s*"([^"]*)"', quick(["xprop", "-id", nid, "WM_CLASS"]))
        if m and m.group(2) not in out:
            out.append(m.group(2))
    return out


def summary(s):
    parts = []
    d = s.get("desktop", "")
    if d:
        parts.append(f"Workspace {d.lstrip('^')}" + (" · go there" if s.get("follow") == "on" else ""))
    if s.get("state") == "floating":
        size = re.match(r"(\d+)x(\d+)", s.get("rectangle", ""))
        parts.append("Floating" + (f" {size.group(1)}×{size.group(2)}" if size else ""))
    elif s.get("state"):
        parts.append(s["state"].replace("_", " ").capitalize())
    if s.get("center") == "on":
        parts.append("centred")
    if s.get("sticky") == "on":
        parts.append("on every workspace")
    return " · ".join(parts) or "No changes"


class RuleDialog(Adw.Dialog):
    def __init__(self, page, title, settings, save, remove=None):
        super().__init__(title=title, content_width=440)
        self.s = dict(settings)
        view = Adw.ToolbarView()
        head = Adw.HeaderBar(show_end_title_buttons=False, show_start_title_buttons=False)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: self.close())
        ok = Gtk.Button(label="Save")
        ok.add_css_class("suggested-action")
        ok.connect("clicked", lambda *_: (self.close(), save(self._collect())))
        head.pack_start(cancel)
        head.pack_end(ok)
        view.add_top_bar(head)
        page_ = Adw.PreferencesPage()
        g = Adw.PreferencesGroup(description="What happens when this app opens a window.")
        self.ws = Adw.ComboRow(title="Open on", model=Gtk.StringList.new(
            ["The workspace you're on"] + [f"Workspace {i}" for i in range(1, 11)]))
        d = self.s.get("desktop", "").lstrip("^")
        self.ws.set_selected(int(d) if d.isdigit() and 1 <= int(d) <= 10 else 0)
        g.add(self.ws)
        self.follow = Adw.SwitchRow(title="Go to that workspace with it", active=self.s.get("follow") == "on")
        g.add(self.follow)
        self.float = Adw.SwitchRow(title="Floating", subtitle="Not tiled with the others",
                                   active=self.s.get("state") == "floating")
        g.add(self.float)
        size = re.match(r"(\d+)x(\d+)", self.s.get("rectangle", ""))
        self.w = Adw.SpinRow.new_with_range(0, 3840, 10)
        self.w.set_title("Width (0: the app decides)")
        self.w.set_value(int(size.group(1)) if size else 0)
        self.h = Adw.SpinRow.new_with_range(0, 2160, 10)
        self.h.set_title("Height")
        self.h.set_value(int(size.group(2)) if size else 0)
        g.add(self.w)
        g.add(self.h)
        self.center = Adw.SwitchRow(title="Centred", active=self.s.get("center") == "on")
        g.add(self.center)
        self.sticky = Adw.SwitchRow(title="On every workspace", active=self.s.get("sticky") == "on")
        g.add(self.sticky)
        for w in (self.w, self.h, self.center):
            self.float.bind_property("active", w, "sensitive", GObject_flags())
        page_.add(g)
        if remove:
            g2 = Adw.PreferencesGroup()
            rm = Adw.ButtonRow(title="Remove this rule")
            rm.add_css_class("destructive-action")
            rm.connect("activated", lambda *_: (self.close(), remove()))
            g2.add(rm)
            page_.add(g2)
        view.set_content(page_)
        self.set_child(view)
        self.set_content_height(560)

    def _collect(self):
        s = {k: v for k, v in self.s.items() if k not in ("desktop", "follow", "state", "center", "sticky", "rectangle")}
        if self.ws.get_selected():
            s["desktop"] = f"^{self.ws.get_selected()}"
        if self.follow.get_active():
            s["follow"] = "on"
        if self.float.get_active():
            s["state"] = "floating"
            if self.w.get_value() and self.h.get_value():
                pos = re.search(r"(\+\d+\+\d+)$", self.s.get("rectangle", ""))
                s["rectangle"] = f"{int(self.w.get_value())}x{int(self.h.get_value())}{pos.group(1) if pos else '+0+0'}"
            if self.center.get_active():
                s["center"] = "on"
        elif self.s.get("state") and self.s["state"] != "floating":
            s["state"] = self.s["state"]
        if self.sticky.get_active():
            s["sticky"] = "on"
        return s


def GObject_flags():
    from gi.repository import GObject
    return GObject.BindingFlags.SYNC_CREATE


class WindowsPage(Page):
    name = "windows"
    title = "Windows"
    icon = "preferences-system-windows-symbolic"
    interval = 0

    def __init__(self, window):
        super().__init__(window)
        lay = group(self, "Layout of this workspace", "How its windows are arranged. Also on the bar's window title.")
        self.lay_grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, column_spacing=6,
                                    row_spacing=6, min_children_per_line=4, max_children_per_line=4)
        self.lay_tiles = {}
        accent = self.get_color()
        for name, label in LAYOUTS:
            b = Gtk.Button()
            b.add_css_class("flat")
            b.add_css_class("cc-tile")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.append(layout_picture(name, accent))
            lab = Gtk.Label(label=label)
            lab.add_css_class("cc-tile-name")
            box.append(lab)
            b.set_child(box)
            b.connect("clicked", lambda _b, n=name, l=label: self._layout(n, l))
            self.lay_grid.append(b)
            self.lay_tiles[name] = b
        lay.add(Adw.PreferencesRow(activatable=False, child=self.lay_grid))

        self.header_widget = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Add a window rule")
        self.header_widget.connect("clicked", lambda *_: self._add())
        self.rules_group = group(self, "Window rules", "What happens when an app opens. Add one with + at the top right.")
        self.popups_group = group(self, "Terminal pop-ups and the rice's own windows")
        self.rule_rows = []
        self.reset = group(self)
        rr = Adw.ActionRow(title="Reset window rules", subtitle="Back to how they were before any change here")
        rr.add_suffix(text_button("Reset…", self._reset_rules))
        self.reset.add(rr)
        self.key = None
        self.refresh()

    # ----- layouts -----

    def refresh(self):
        cur = quick([tool("Layout"), "get"]).strip()
        if cur in ("", "-"):
            cur = quick(["bspc", "query", "-T", "-d", "focused"])
            try:
                cur = json.loads(cur).get("layout", "tiled")
            except ValueError:
                cur = "tiled"
        for n, b in self.lay_tiles.items():
            (b.add_css_class if n == cur else b.remove_css_class)("cc-current")
        rs = rules.load()
        key = repr([(r.names, r.body) for r in rs])
        self.reset.set_visible(rules.has_original())
        if key != self.key:
            self.key = key
            self._fill(rs)

    def _layout(self, name, label):
        run_quiet([tool("Layout"), "set", name], lambda _ok: self.refresh())
        self.toast(f"This workspace: {label}")

    # ----- rules -----

    def _fill(self, rs):
        for g, r in self.rule_rows:
            g.remove(r)
        self.rule_rows.clear()
        for rule in rs:
            popup = rule.kind == "instance" or rule.name in POPUPS
            g = self.popups_group if popup else self.rules_group
            name, icon = (POPUPS.get(rule.name), None) if popup else app_for(rule.name)
            title = name or rule.name
            r = Adw.ActionRow(title=GLib.markup_escape_text(title),
                              subtitle=GLib.markup_escape_text(summary(rule.settings) if rule.simple
                                                               else "Has its own rule (not changed here)"))
            r.add_prefix(Gtk.Image.new_from_gicon(icon) if icon else
                         Gtk.Image.new_from_icon_name("application-x-executable-symbolic"))
            r.set_tooltip_text(f"Window class: {' | '.join(rule.names)}")
            if rule.simple:
                r.set_activatable(True)
                r.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
                r.connect("activated", lambda _r, rule=rule, t=title: self._edit(rule, t))
            else:
                r.add_css_class("dim-label")
            g.add(r)
            self.rule_rows.append((g, r))
        widgets_changed()

    def _done(self, text):
        self.key = None
        self.refresh()
        self.toast(text)

    def _edit(self, rule, title):
        def save(s):
            try:
                rules.save(rule, s)
            except OSError as e:
                self.toast(f"Couldn't save: {e.strerror}")
                return
            self._done(f"{title}: {summary(s)}")

        def remove():
            try:
                rules.remove(rule)
            except OSError as e:
                self.toast(f"Couldn't save: {e.strerror}")
                return
            self._done(f"Removed the rule for {title}")
        RuleDialog(self, title, rule.settings, save, remove).present(self.window)

    def _add(self):
        """Pick an app (open windows first, then installed apps), then its rule."""
        d = Adw.Dialog(title="Rule for which app?", content_width=400, content_height=520)
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_start=12, margin_end=12, margin_bottom=12)
        search = Gtk.SearchEntry(placeholder_text="Search apps")
        lst = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        lst.add_css_class("boxed-list")
        have = {n.lower() for r in rules.load() for n in r.names}
        seen = set()
        items = []
        for cls in open_classes():
            name, icon = app_for(cls)
            items.append((cls, name or cls, icon, "Open now"))
            seen.add(cls.lower())
        for a in sorted((a for a in Gio.AppInfo.get_all() if isinstance(a, DesktopAppInfo) and a.should_show()),
                        key=lambda a: a.get_name().lower()):
            cls = a.get_startup_wm_class() or (a.get_executable() or "").split("/")[-1]
            if cls and cls.lower() not in seen:
                seen.add(cls.lower())
                items.append((cls, a.get_name(), a.get_icon(), ""))
        for cls, name, icon, note in items:
            if cls.lower() in have:
                continue
            r = Adw.ActionRow(title=GLib.markup_escape_text(name), subtitle=note, activatable=True)
            r.add_prefix(Gtk.Image.new_from_gicon(icon) if icon else Gtk.Image.new_from_icon_name("application-x-executable-symbolic"))
            r.cls, r.text = cls, f"{name} {cls}".lower()
            r.connect("activated", lambda row: (d.close(), self._new(row.cls, row.get_title())))
            lst.append(r)
        lst.set_filter_func(lambda r: all(w in r.text for w in search.get_text().lower().split()))
        search.connect("search-changed", lambda *_: lst.invalidate_filter())
        box.append(search)
        box.append(Gtk.ScrolledWindow(child=lst, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER))
        view.set_content(box)
        d.set_child(view)
        d.present(self.window)

    def _new(self, cls, title):
        def save(s):
            try:
                rules.add(cls, s)
            except OSError as e:
                self.toast(f"Couldn't save: {e.strerror}")
                return
            self._done(f"{title}: {summary(s)}")
        RuleDialog(self, title, {}, save).present(self.window)

    def _reset_rules(self):
        d = Adw.AlertDialog(heading="Reset window rules?", body="Every change made here is undone.")
        d.add_response("cancel", "Cancel")
        d.add_response("reset", "Reset")
        d.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        d.connect("response", lambda _d, r: r == "reset" and (rules.reset(), self._done("Window rules are reset")))
        d.present(self.window)
