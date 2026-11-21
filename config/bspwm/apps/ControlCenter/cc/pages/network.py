"""Network: airplane mode, Wi-Fi, connecting to networks."""

import json

from gi.repository import Adw, GLib, Gtk

from ..common import Page, group, have, icon_button, launch, run, run_json, run_quiet, text_button, tool

BARS = {4: "network-wireless-signal-excellent-symbolic", 3: "network-wireless-signal-good-symbolic",
        2: "network-wireless-signal-ok-symbolic", 1: "network-wireless-signal-weak-symbolic"}


class NetworkPage(Page):
    name = "network"
    title = "Network"
    icon = "network-wireless-symbolic"
    interval = 3

    def __init__(self, window):
        super().__init__(window)
        self.state = {}
        self.list_key = None
        self.connecting = None
        self.scanned = False

        top = group(self)
        self.airplane = Adw.SwitchRow(title="Airplane mode", subtitle="Turns off Wi-Fi and Bluetooth")
        self.airplane.add_prefix(Gtk.Image.new_from_icon_name("airplane-mode-symbolic"))
        self.airplane.connect("notify::active", self._airplane)
        top.add(self.airplane)
        self.wifi = Adw.SwitchRow(title="Wi-Fi")
        self.wifi.add_prefix(Gtk.Image.new_from_icon_name("network-wireless-symbolic"))
        self.wifi.connect("notify::active", self._wifi)
        top.add(self.wifi)

        self.current = group(self, "Connection")
        self.conn = Adw.ActionRow(title="Not connected")
        self.conn.add_prefix(Gtk.Image.new_from_icon_name("network-wired-symbolic"))
        self.speed = Gtk.Label()
        self.speed.add_css_class("dim-label")
        self.speed.add_css_class("numeric")
        self.conn.add_suffix(self.speed)
        self.current.add(self.conn)

        self.nets = group(self, "Networks")
        head = Gtk.Box(spacing=6)
        self.spinner = Adw.Spinner(visible=False)
        head.append(self.spinner)
        head.append(icon_button("view-refresh-symbolic", "Search again", self.scan))
        self.nets.set_header_suffix(head)
        self.net_rows = []

        more = group(self)
        if have("nm-connection-editor"):
            row = Adw.ActionRow(title="Hidden networks, VPN and advanced settings", subtitle="Network Connections")
            row.add_suffix(text_button("Open", lambda: launch(["nm-connection-editor"])))
            more.add(row)

    # ----- switches -----

    def _airplane(self, row, _p):
        if self._updating or row.get_active() == self.state.get("airplane"):
            return
        self.state["airplane"] = row.get_active()
        run_quiet([tool("BarPanelAction"), "airplane"], lambda _ok: self.refresh())

    def _wifi(self, row, _p):
        if self._updating or row.get_active() == self.state.get("wifi_on"):
            return
        self.state["wifi_on"] = row.get_active()
        run_quiet([tool("BarPanelAction"), "wifi-toggle"], lambda _ok: (self.refresh(), self.scan()))

    # ----- data -----

    def refresh(self):
        def got(d):
            if not d:
                return
            self.state = d
            self.quietly(lambda: (self.airplane.set_active(d["airplane"]), self.wifi.set_active(d["wifi_on"])))
            if d["kind"] == "none":
                self.conn.set_title("Not connected")
                self.conn.set_subtitle("")
                self.speed.set_label("")
            else:
                self.conn.set_title(d["name"])
                kind = "Wi-Fi" if d["kind"] == "wifi" else "Ethernet"
                sig = f" · signal {d['signal']}%" if d["kind"] == "wifi" else ""
                self.conn.set_subtitle(f"{kind} · {d['ip']} · {d['iface']}{sig}")
                self.speed.set_label(f"↓ {d['down']}   ↑ {d['up']}")
            self.nets.set_visible(d["wifi_on"])
        run_json([tool("BarPanelData"), "network"], got)
        run_json([tool("BarPanelData"), "wifi"], self._networks)
        if not self.scanned:
            self.scanned = True
            self.scan()

    def scan(self):
        if self.spinner.get_visible():
            return
        self.spinner.set_visible(True)

        def done(d):
            self.spinner.set_visible(False)
            if d:
                self._networks(d)
        run_json([tool("BarPanelData"), "wifi", "--rescan"], done)

    def _networks(self, d):
        if not d:
            return
        nets = d.get("networks", [])
        key = json.dumps([(n["ssid"], n["active"], n["known"], n["bars"], n.get("connecting")) for n in nets]) + str(self.connecting)
        if key == self.list_key:
            return
        self.list_key = key
        for r in self.net_rows:
            self.nets.remove(r)
        self.net_rows.clear()
        if not nets:
            row = Adw.ActionRow(title="Looking for networks…" if self.spinner.get_visible() else "No networks found")
            row.add_css_class("dim-label")
            self.nets.add(row)
            self.net_rows.append(row)
        for n in nets:
            self.nets.add(self._row(n))

    def _row(self, n):
        sub = ("Connecting…" if n.get("connecting") or self.connecting == n["ssid"]
               else "Connected" if n["active"] else "Saved" if n["known"] else "")
        row = Adw.ActionRow(title=GLib.markup_escape_text(n["ssid"]), subtitle=sub)
        row.add_prefix(Gtk.Image.new_from_icon_name(BARS.get(n["bars"], BARS[1])))
        if n["secure"]:
            lock = Gtk.Image.new_from_icon_name("system-lock-screen-symbolic")
            lock.add_css_class("dim-label")
            lock.set_tooltip_text("Needs a password")
            row.add_suffix(lock)
        if n["known"]:
            row.add_suffix(icon_button("user-trash-symbolic", "Forget this network", lambda s=n["ssid"]: self.forget(s)))
        if n["active"]:
            check = Gtk.Image.new_from_icon_name("object-select-symbolic")
            check.add_css_class("accent")
            row.add_suffix(check)
        else:
            row.set_activatable(True)
            row.connect("activated", lambda *_: self.connect_to(n))
        self.net_rows.append(row)
        return row

    # ----- connecting -----

    def connect_to(self, n):
        ssid = n["ssid"]
        if n["known"]:
            self._run_connect(ssid, ["nmcli", "con", "up", "id", ssid])
        elif n["secure"]:
            self._ask_password(ssid)
        else:
            self._run_connect(ssid, ["nmcli", "dev", "wifi", "connect", ssid])

    def _ask_password(self, ssid):
        d = Adw.AlertDialog(heading=f"Join “{ssid}”", body="Enter the network password.")
        entry = Adw.PasswordEntryRow(title="Password")
        box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        box.add_css_class("boxed-list")
        box.append(entry)
        d.set_extra_child(box)
        d.add_response("cancel", "Cancel")
        d.add_response("join", "Join")
        d.set_response_appearance("join", Adw.ResponseAppearance.SUGGESTED)
        d.set_default_response("join")
        d.set_response_enabled("join", False)
        entry.set_activates_default(True)   # Enter = Join
        entry.connect("changed", lambda e: d.set_response_enabled("join", len(e.get_text()) >= 8))   # WPA minimum

        def answered(_d, response):
            if response == "join":
                self._run_connect(ssid, ["nmcli", "dev", "wifi", "connect", ssid, "password", entry.get_text()])
        d.connect("response", answered)
        d.present(self.window)
        entry.grab_focus()

    def _run_connect(self, ssid, argv):
        if self.connecting:
            return
        self.connecting = ssid
        self.list_key = None
        self.refresh()

        def done(ok, out, err):
            self.connecting = None
            self.list_key = None
            if ok:
                self.toast(f"Connected to {ssid}")
            else:
                msg = (err or out).strip().splitlines()
                self.toast(f"Couldn't connect to {ssid}" + (f": {msg[-1].split(': ', 1)[-1]}" if msg else ""))
            self.refresh()
        run(argv, done)

    def forget(self, ssid):
        d = Adw.AlertDialog(heading=f"Forget “{ssid}”?",
                            body="Its saved password is deleted. You'll need it again to reconnect.")
        d.add_response("cancel", "Cancel")
        d.add_response("forget", "Forget")
        d.set_response_appearance("forget", Adw.ResponseAppearance.DESTRUCTIVE)

        def answered(_d, response):
            if response == "forget":
                run(["nmcli", "con", "delete", "id", ssid],
                    lambda ok, _o, _e: (self.toast(f"Forgot {ssid}" if ok else f"Couldn't forget {ssid}"),
                                        setattr(self, "list_key", None), self.refresh()))
        d.connect("response", answered)
        d.present(self.window)
