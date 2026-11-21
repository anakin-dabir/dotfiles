"""Typing: keyboard layouts (and the key that switches between them), Caps
Lock, key repeat. Saved in config/typing.json and applied by
bin/KeyboardSetup (also at login)."""

import json
import os
import re
from functools import lru_cache

from gi.repository import Adw, GLib, Gtk

from ..common import BSPDIR, Page, group, icon_button, run_quiet, slider_row, tool, widgets_changed

SETTINGS = os.path.join(BSPDIR, "config", "typing.json")
RULES = "/usr/share/X11/xkb/rules/evdev.lst"
SWITCH = [("", "No key (use the layout menu: Super + Alt + K)"), ("grp:alt_shift_toggle", "Alt + Shift"),
          ("grp:ctrl_shift_toggle", "Ctrl + Shift"), ("grp:win_space_toggle", "Super + Space (instead of the app menu)"),
          ("grp:caps_toggle", "Caps Lock"), ("grp:shifts_toggle", "Both Shift keys")]
CAPS = [("", "Caps Lock"), ("ctrl:nocaps", "Another Ctrl"), ("caps:escape", "Escape"),
        ("caps:swapescape", "Escape, and Escape is Caps Lock"), ("caps:none", "Nothing")]


@lru_cache(maxsize=None)
def all_layouts():
    """[(code, name)] - "us", "English (US)"; variants as "us:intl"."""
    try:
        text = open(RULES).read()
    except OSError:
        return [("us", "English (US)")]
    out, names = [], {}
    sec = None
    for line in text.splitlines():
        if line.startswith("! "):
            sec = line[2:].strip()
            continue
        if sec == "layout":
            m = re.match(r"\s+(\S+)\s+(.*)", line)
            if m:
                names[m.group(1)] = m.group(2).strip()
                out.append((m.group(1), m.group(2).strip()))
        elif sec == "variant":
            m = re.match(r"\s+(\S+)\s+(\S+):\s+(.*)", line)
            if m:
                out.append((f"{m.group(2)}:{m.group(1)}", m.group(3).strip()))
    return out


def layout_name(code):
    return dict(all_layouts()).get(code, code)


def settings():
    try:
        with open(SETTINGS) as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    return {"layouts": list(s.get("layouts") or ["us"]), "switch": s.get("switch", ""), "caps": s.get("caps", ""),
            "delay": int(s.get("delay", 660)), "rate": int(s.get("rate", 25))}


class TypingPage(Page):
    name = "typing"
    title = "Typing"
    icon = "input-keyboard-symbolic"
    interval = 0

    def __init__(self, window):
        super().__init__(window)
        self.layouts = group(self, "Layouts", "The first one is used when you log in. Saved right away.")
        add = Gtk.MenuButton(label="Add…", valign=Gtk.Align.CENTER)
        add.add_css_class("suggested-action")
        add.set_popover(self._add_popover())
        self.layouts.set_header_suffix(add)
        self.layout_rows = []
        self.switch = Adw.ComboRow(title="Switch layouts with", model=Gtk.StringList.new([t for _v, t in SWITCH]))
        self.switch.connect("notify::selected", lambda r, _p: self._set(switch=SWITCH[r.get_selected()][0]))

        keys = group(self, "Keys")
        self.caps = Adw.ComboRow(title="Caps Lock key works as", model=Gtk.StringList.new([t for _v, t in CAPS]))
        self.caps.connect("notify::selected", lambda r, _p: self._set(caps=CAPS[r.get_selected()][0]))
        keys.add(self.caps)
        self.delay = slider_row("Repeat starts after", "input-keyboard-symbolic", 150, 1000,
                                lambda v: self._set(delay=int(v)), step=10, unit=" ms")
        self.delay.set_subtitle("How long you hold a key before it repeats")
        keys.add(self.delay)
        self.rate = slider_row("Repeat speed", "media-seek-forward-symbolic", 10, 60,
                               lambda v: self._set(rate=int(v)), unit=" per second")
        keys.add(self.rate)
        test = Adw.EntryRow(title="Try it here")
        keys.add(test)
        self.load()

    # ----- state -----

    def load(self):
        s = settings()
        for r in self.layout_rows:
            self.layouts.remove(r)
        self.layout_rows.clear()
        n = len(s["layouts"])
        for i, code in enumerate(s["layouts"]):
            r = Adw.ActionRow(title=GLib.markup_escape_text(layout_name(code)), subtitle=code.replace(":", " · "))
            r.add_prefix(Gtk.Image.new_from_icon_name("input-keyboard-symbolic"))
            up = icon_button("go-up-symbolic", "Move up (first: used at login)", lambda i=i: self._move(i, -1))
            up.set_sensitive(i > 0)
            r.add_suffix(up)
            rm = icon_button("user-trash-symbolic", "Remove", lambda i=i: self._remove(i))
            rm.set_sensitive(n > 1)
            r.add_suffix(rm)
            self.layouts.add(r)
            self.layout_rows.append(r)
        self.layouts.add(self.switch)
        self.layout_rows.append(self.switch)
        self.switch.set_visible(n > 1)

        def put():
            self.switch.set_selected(next((i for i, (v, _t) in enumerate(SWITCH) if v == s["switch"]), 0))
            self.caps.set_selected(next((i for i, (v, _t) in enumerate(CAPS) if v == s["caps"]), 0))
        self.quietly(put)
        self.delay.set_value(s["delay"])
        self.rate.set_value(s["rate"])
        widgets_changed()

    def _save(self, s, repeat_only=False):
        try:
            with open(SETTINGS, "w") as f:
                json.dump(s, f, indent=2)
                f.write("\n")
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
            return False
        if repeat_only:              # (sliders: just the repeat, not the layouts again)
            run_quiet(["xset", "r", "rate", str(s["delay"]), str(s["rate"])])
        else:
            run_quiet([tool("KeyboardSetup")])
        return True

    def _set(self, **changes):
        if self._updating:
            return
        s = settings()
        s.update(changes)
        self._save(s, repeat_only=set(changes) <= {"delay", "rate"})

    def _move(self, i, step):
        s = settings()
        j = i + step
        if 0 <= j < len(s["layouts"]):
            s["layouts"][i], s["layouts"][j] = s["layouts"][j], s["layouts"][i]
            if self._save(s):
                self.load()

    def _remove(self, i):
        s = settings()
        if len(s["layouts"]) > 1:
            gone = s["layouts"].pop(i)
            if self._save(s):
                self.load()
                self.toast(f"Removed {layout_name(gone)}")

    def _add(self, code):
        s = settings()
        if code in s["layouts"]:
            return
        s["layouts"].append(code)
        if len(s["layouts"]) == 2 and not s["switch"]:
            s["switch"] = "grp:alt_shift_toggle"          # (a way to switch, from the start)
        if self._save(s):
            self.load()
            self.toast(f"Added {layout_name(code)}" + (" · switch with Alt + Shift" if len(s["layouts"]) == 2 else ""))

    def _add_popover(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=8, margin_bottom=8,
                      margin_start=8, margin_end=8)
        search = Gtk.SearchEntry(placeholder_text="Search (Urdu, Arabic, French…)")
        lst = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        lst.add_css_class("navigation-sidebar")
        for code, name in sorted(all_layouts(), key=lambda x: (":" in x[0], x[1].lower())):
            r = Gtk.ListBoxRow()
            lab = Gtk.Label(label=name, xalign=0, ellipsize=3, max_width_chars=38, margin_top=3, margin_bottom=3)
            if ":" in code:
                lab.add_css_class("dim-label")
            r.set_child(lab)
            r.code, r.text = code, (name + " " + code).lower()
            lst.append(r)
        lst.set_filter_func(lambda r: all(w in r.text for w in search.get_text().lower().split()))
        search.connect("search-changed", lambda *_: lst.invalidate_filter())
        scroll = Gtk.ScrolledWindow(child=lst, min_content_height=340, min_content_width=320,
                                    hscrollbar_policy=Gtk.PolicyType.NEVER)
        box.append(search)
        box.append(scroll)
        pop = Gtk.Popover(child=box)
        lst.connect("row-activated", lambda _l, r: (pop.popdown(), self._add(r.code)))
        return pop
