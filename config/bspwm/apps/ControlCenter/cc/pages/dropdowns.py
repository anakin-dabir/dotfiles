"""Dropdowns: choose which sections each bar dropdown shows, by ticking
pictures of the sections. Saved right away (config/dropdowns.json)."""

import json
import os
import threading

from gi.repository import Adw, GLib, Gtk

from .. import ddshots
from ..common import BSPDIR, Page, group, run_quiet, widgets_changed

FILE = os.path.join(BSPDIR, "config", "dropdowns.json")

DROPDOWNS = [
    ("cpu", "Processor", [
        ("cpu_graph", "Usage graph and cores"),
        ("cpu_stats", "Temperature, load and threads"),
        ("cpu_apps", "Apps using the most CPU"),
        ("cpu_button", "System Monitor button"),
    ]),
    ("memory", "Memory", [
        ("memory_graph", "Usage graph and swap"),
        ("memory_apps", "Apps using the most memory"),
        ("memory_button", "System Monitor button"),
    ]),
    ("disk", "Storage", [
        ("disk_buttons", "Files and Analyze buttons"),
    ]),
    ("sound", "Sound", [
        ("sound_volume", "Volume slider"),
        ("sound_output", "Output devices"),
        ("sound_mic", "Microphone slider"),
        ("sound_button", "Sound Settings button"),
    ]),
    ("network", "Network", [
        ("network_speed", "Download and upload speed"),
        ("network_airplane", "Airplane mode"),
        ("network_wifi", "Wi-Fi (with its list of networks)"),
        ("network_bluetooth", "Bluetooth (with its list of devices)"),
        ("network_button", "Network Settings button"),
    ]),
    ("battery", "Battery", [
        ("battery_details", "Charge, health and cycles"),
        ("battery_mode", "Power mode"),
        ("battery_brightness", "Brightness slider"),
        ("battery_night", "Night light"),
        ("battery_awake", "Keep awake"),
        ("battery_buttons", "Settings and Power Off buttons"),
    ]),
]
ALL_KEYS = [k for _d, _t, parts in DROPDOWNS for k, _n in parts]


def load():
    shown = {k: True for k in ALL_KEYS}
    try:
        with open(FILE) as f:
            shown.update({k: bool(v) for k, v in json.load(f).items()})
    except (OSError, ValueError):
        pass
    return shown


class Section(Gtk.Box):
    """A picture of one dropdown section with a tick box. Clicking anywhere
    on it ticks or unticks it; unticked sections are faded."""

    def __init__(self, key, name, on_toggle):
        super().__init__(spacing=12, margin_top=6, margin_bottom=6, margin_start=10, margin_end=10)
        self.key = key
        self.check = Gtk.CheckButton(valign=Gtk.Align.CENTER, tooltip_text=name)
        self.check.connect("toggled", lambda c: on_toggle(key, c.get_active()))
        self.append(self.check)
        self.stack = Gtk.Stack(hexpand=True, halign=Gtk.Align.START)
        self.picture = Gtk.Picture(can_shrink=False, halign=Gtk.Align.START, tooltip_text=name)
        self.picture.add_css_class("cc-tile-image")
        self.picture.set_overflow(Gtk.Overflow.HIDDEN)
        self.label = Gtk.Label(label=name, xalign=0)
        self.stack.add_named(self.label, "text")
        self.stack.add_named(self.picture, "picture")
        self.append(self.stack)
        click = Gtk.GestureClick()
        click.connect("released", lambda *_: self.check.set_active(not self.check.get_active()))
        self.stack.add_controller(click)
        self.stack.set_cursor_from_name("pointer")

    def set_picture(self, path):
        if os.path.exists(path):
            self.picture.set_filename(path)
            self.stack.set_visible_child_name("picture")

    def set_on(self, on):
        self.check.set_active(on)
        self.stack.set_opacity(1.0 if on else 0.35)


class DropdownsPage(Page):
    name = "dropdowns"
    title = "Dropdowns"
    icon = "view-list-symbolic"
    interval = 0

    def __init__(self, window):
        super().__init__(window)
        self.shown = load()
        self.sections = {}
        self.capturing = False
        intro = group(self, description="The panels that open when you click an item on the bar. "
                                        "Untick what you don't need; it's saved right away.")
        self.status = Adw.ActionRow(title="Taking pictures of your dropdowns…",
                                    subtitle="Once per theme, off-screen")
        self.status.add_prefix(Adw.Spinner())
        self.status.set_visible(False)
        intro.add(self.status)
        for _dd, title, parts in DROPDOWNS:
            g = group(self, title)
            box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            box.add_css_class("boxed-list")
            for key, name in parts:
                sec = Section(key, name, self._toggle)
                box.append(Gtk.ListBoxRow(child=sec, activatable=False))
                self.sections[key] = sec
            g.add(box)

    def refresh(self):
        self.shown = load()
        self.quietly(lambda: [s.set_on(self.shown.get(k, True)) for k, s in self.sections.items()])
        folder = ddshots.cache_dir()
        for k, s in self.sections.items():
            s.set_picture(os.path.join(folder, k + ".png"))
        if not os.path.exists(os.path.join(folder, ".complete")):
            self._capture()

    def _capture(self):
        if self.capturing:
            return
        if ddshots.dropdown_open():          # don't disturb an open dropdown; try again shortly
            GLib.timeout_add_seconds(3, lambda: (self.window.page is self and self.refresh(), False)[1])
            return
        self.capturing = True
        self.status.set_visible(True)
        folder = ddshots.cache_dir()

        def one(key):
            self.sections[key].set_picture(os.path.join(folder, key + ".png"))
            return False

        def work():
            try:
                ddshots.capture([(dd, [k for k, _n in parts]) for dd, _t, parts in DROPDOWNS],
                                {k: False for k in ALL_KEYS}, one)
            finally:
                GLib.idle_add(finished)

        def finished():
            self.capturing = False
            self.status.set_visible(False)
            widgets_changed()
            return False
        threading.Thread(target=work, daemon=True).start()

    def _toggle(self, key, on):
        self.sections[key].stack.set_opacity(1.0 if on else 0.35)
        if self._updating:
            return
        self.shown[key] = on
        try:
            with open(FILE, "w") as f:
                json.dump(self.shown, f, indent=2)
                f.write("\n")
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
            return
        if not self.capturing:      # an open dropdown follows at once
            run_quiet(["eww", "--no-daemonize", "-c", os.path.join(BSPDIR, "eww"), "update",
                       "bp_show=" + json.dumps(self.shown, separators=(",", ":"))])
