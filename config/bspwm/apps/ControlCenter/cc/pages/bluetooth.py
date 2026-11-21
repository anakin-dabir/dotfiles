"""Bluetooth: on/off, paired devices, finding and pairing new ones."""

import json
import re

from gi.repository import Adw, GLib, Gtk

from ..common import Page, group, have, icon_button, launch, quick, radio_on, run, run_json, text_button, tool

ICONS = {"audio-headset": "audio-headset-symbolic", "audio-headphones": "audio-headphones-symbolic",
         "audio-card": "audio-speakers-symbolic", "input-keyboard": "input-keyboard-symbolic",
         "input-mouse": "input-mouse-symbolic", "input-gaming": "input-gaming-symbolic",
         "phone": "phone-symbolic", "computer": "computer-symbolic"}
MAC = re.compile(r"^([0-9A-F]{2}[:-]){5}[0-9A-F]{2}$", re.I)


def device_icon(kind):
    return ICONS.get(kind, "bluetooth-active-symbolic")


class BluetoothPage(Page):
    name = "bluetooth"
    title = "Bluetooth"
    icon = "bluetooth-active-symbolic"
    interval = 3

    def __init__(self, window):
        super().__init__(window)
        self.on = None
        self.busy = set()          # devices being connected/paired
        self.paired_key = None
        self.found_key = None
        self.paired_macs = set()
        self.searching = False

        top = group(self)
        self.power = Adw.SwitchRow(title="Bluetooth")
        self.power.add_prefix(Gtk.Image.new_from_icon_name("bluetooth-active-symbolic"))
        self.power.connect("notify::active", self._toggle)
        top.add(self.power)

        self.paired = group(self, "My devices")
        self.paired_rows = []

        self.found = group(self, "Other devices", "Put the device in pairing mode, then search.")
        self.search_btn = text_button("Search", self.search)
        self.spinner = Adw.Spinner(visible=False)
        head = Gtk.Box(spacing=8)
        head.append(self.spinner)
        head.append(self.search_btn)
        self.found.set_header_suffix(head)
        self.found_rows = []
        self.paired.set_visible(False)
        self.found.set_visible(False)

        if have("blueman-manager"):
            more = group(self)
            row = Adw.ActionRow(title="Advanced settings and file sending", subtitle="Bluetooth Manager (blueman)")
            row.add_suffix(text_button("Open", lambda: launch(["blueman-manager"])))
            more.add(row)

    def _toggle(self, row, _p):
        if self._updating or row.get_active() == self.on:
            return
        self.on = row.get_active()
        run([tool("BarPanelAction"), "bt-toggle"], lambda *_: self.refresh())
        self._show_lists()

    def _show_lists(self):
        self.paired.set_visible(bool(self.on))
        self.found.set_visible(bool(self.on))

    # ----- paired -----

    def refresh(self):
        # On or off first (before the page is drawn), so the device lists
        # don't show up and then vanish
        if radio_on("bluetooth") is False:
            powered = False
        else:
            powered = "Powered: yes" in quick(["bluetoothctl", "show"])
        if powered != self.on:
            self.on = powered
            self.quietly(lambda: self.power.set_active(powered))
            self._show_lists()

        # First visit: the paired devices before the page is drawn
        if self.paired_key is None and powered:
            try:
                self._paired(json.loads(quick([tool("BarPanelData"), "bt"])))
            except ValueError:
                pass

        def net(d):
            if d:
                self.on = d["bt_on"]
                self.quietly(lambda: self.power.set_active(self.on))
                self._show_lists()
        run_json([tool("BarPanelData"), "network"], net)
        run_json([tool("BarPanelData"), "bt"], self._paired)
        if self.searching:
            self._discovered()

    def _paired(self, d):
        devs = (d or {}).get("devices", [])
        self.paired_macs = {x["mac"] for x in devs}
        key = repr([(x["mac"], x["name"], x["connected"], x["battery"]) for x in devs]) + repr(sorted(self.busy))
        if key == self.paired_key:
            return
        self.paired_key = key
        for r in self.paired_rows:
            self.paired.remove(r)
        self.paired_rows.clear()
        if not devs:
            r = Adw.ActionRow(title="No paired devices yet")
            r.add_css_class("dim-label")
            self.paired.add(r)
            self.paired_rows.append(r)
        for x in devs:
            if x["mac"] in self.busy:
                sub = "Connecting…" if not x["connected"] else "Disconnecting…"
            elif x["connected"]:
                sub = "Connected" + (f" · battery {x['battery']}%" if x["battery"] else "")
            else:
                sub = "Not connected"
            row = Adw.ActionRow(title=GLib.markup_escape_text(x["name"]), subtitle=sub)
            row.add_prefix(Gtk.Image.new_from_icon_name(device_icon(x["icon"])))
            btn = text_button("Disconnect" if x["connected"] else "Connect",
                              lambda m=x["mac"]: self.connect_toggle(m), css=[] if x["connected"] else ["suggested-action"])
            btn.set_sensitive(x["mac"] not in self.busy)
            row.add_suffix(btn)
            row.add_suffix(icon_button("user-trash-symbolic", "Remove this device", lambda x=x: self.remove(x)))
            self.paired.add(row)
            self.paired_rows.append(row)

    def connect_toggle(self, mac):
        self.busy.add(mac)
        self.paired_key = None
        self.refresh()

        def done(*_):
            self.busy.discard(mac)
            self.paired_key = None
            self.refresh()
        run([tool("BarPanelAction"), "bt-connect", mac], done)

    def remove(self, x):
        d = Adw.AlertDialog(heading=f"Remove “{x['name']}”?", body="You'll need to pair it again to use it.")
        d.add_response("cancel", "Cancel")
        d.add_response("remove", "Remove")
        d.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        d.connect("response", lambda _d, r: r == "remove" and run(
            ["bluetoothctl", "remove", x["mac"]], lambda *_: (setattr(self, "paired_key", None), self.refresh())))
        d.present(self.window)

    # ----- finding new devices -----

    def search(self):
        if self.searching:
            return
        self.searching = True
        self.spinner.set_visible(True)
        self.search_btn.set_sensitive(False)
        self.found.set_description("Searching… put the device in pairing mode.")

        def done(*_):
            self.searching = False
            self.spinner.set_visible(False)
            self.search_btn.set_sensitive(True)
            self.found.set_description("Put the device in pairing mode, then search.")
            self._discovered()
        run(["bluetoothctl", "--timeout", "15", "scan", "on"], done)
        GLib.timeout_add(1500, lambda: (self._discovered(), False)[1])

    def _discovered(self):
        def got(ok, out, _e):
            devs = []
            for line in out.splitlines():
                parts = line.split(" ", 2)
                if len(parts) == 3 and parts[0] == "Device" and parts[1] not in self.paired_macs:
                    name = parts[2].strip()
                    if name and not MAC.match(name):
                        devs.append((parts[1], name))
            key = repr(devs) + repr(sorted(self.busy))
            if key == self.found_key:
                return
            self.found_key = key
            for r in self.found_rows:
                self.found.remove(r)
            self.found_rows.clear()
            for mac, name in devs:
                row = Adw.ActionRow(title=GLib.markup_escape_text(name), subtitle="Pairing…" if mac in self.busy else "")
                b = text_button("Pair", lambda m=mac, n=name: self.pair(m, n))
                b.set_sensitive(mac not in self.busy)
                row.add_suffix(b)
                self.found.add(row)
                self.found_rows.append(row)
        run(["bluetoothctl", "devices"], got)

    def pair(self, mac, name):
        self.busy.add(mac)
        self.found_key = None
        self._discovered()
        if not MAC.match(mac):
            return
        script = ('bluetoothctl --timeout 25 pair "$1" && bluetoothctl trust "$1" >/dev/null '
                  '&& bluetoothctl --timeout 15 connect "$1"')

        def done(ok, out, err):
            self.busy.discard(mac)
            self.found_key = self.paired_key = None
            if ok and "Failed" not in out:
                self.toast(f"Paired with {name}")
            else:
                self.toast(f"Couldn't pair with {name}" + (" (try Bluetooth Manager)" if have("blueman-manager") else ""))
            self.refresh()
            self._discovered()
        run(["sh", "-c", script, "sh", mac], done)
