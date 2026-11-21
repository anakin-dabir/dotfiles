"""Power: battery, power mode, keep awake, and lock/suspend/restart/shut down."""

import json

from gi.repository import Adw, Gtk

from ..common import Page, group, launch, run, run_quiet, text_button, tool

def battery_icon(pct, charging):
    level = min(100, max(0, round(pct / 10) * 10))
    return f"battery-level-{level}{'-charging' if charging else ''}-symbolic"


class PowerPage(Page):
    name = "power"
    title = "Power"
    icon = "battery-good-symbolic"
    interval = 2

    def __init__(self, window):
        super().__init__(window)
        self.modes_key = None

        # Battery summary
        bat = group(self, "Battery")
        self.hero = Adw.ActionRow()
        self.hero_icon = Gtk.Image(pixel_size=32)
        self.hero.add_prefix(self.hero_icon)
        self.pct = Gtk.Label()
        self.pct.add_css_class("cc-big")
        self.hero.add_suffix(self.pct)
        bat.add(self.hero)
        self.level = Gtk.LevelBar(min_value=0, max_value=100, hexpand=True, margin_top=10, margin_bottom=10,
                                  margin_start=12, margin_end=12)
        self.level.add_offset_value("low", 20)
        self.level.add_offset_value("high", 60)
        level_row = Adw.PreferencesRow(activatable=False, child=self.level)
        bat.add(level_row)


        # Power mode
        self.mode_group = group(self, "Power mode", "How hard the processor and fans may work.")
        self.modes = Adw.ToggleGroup(halign=Gtk.Align.FILL, hexpand=True, margin_top=10, margin_bottom=10,
                                     margin_start=10, margin_end=10)
        self.modes.add_css_class("round")
        self.modes.connect("notify::active-name", self._mode)
        self.mode_group.add(Adw.PreferencesRow(activatable=False, child=self.modes))
        self.allow = Adw.ActionRow(title="Changing the power mode needs a one-time permission",
                                   subtitle="Asks for your password once")
        self.allow.add_suffix(text_button("Allow…", self._allow, css=["suggested-action"]))
        self.mode_group.add(self.allow)

        # Sleep
        sleep = group(self, "Sleep")
        self.awake = Adw.SwitchRow(title="Keep awake",
                                   subtitle="Don't sleep, not even with the lid closed, until this is turned off")
        self.awake.add_prefix(Gtk.Image.new_from_icon_name("preferences-system-time-symbolic"))
        self.awake.connect("notify::active", lambda *_: self._updating or run_quiet([tool("BarPanelAction"), "awake"]))
        sleep.add(self.awake)

        # Session
        session = group(self, "Session")
        for label, sub, icon, argv in [
            ("Lock", "Lock the screen", "system-lock-screen-symbolic", [tool("ScreenLocker")]),
            ("Suspend", "Sleep until you open the lid or press a key", "media-playback-pause-symbolic", ["systemctl", "suspend"]),
            ("Log Out", "Close all apps and leave bspwm", "system-log-out-symbolic", ["bspc", "quit"]),
            ("Restart", "", "system-reboot-symbolic", ["systemctl", "reboot"]),
            ("Shut Down", "", "system-shutdown-symbolic", ["systemctl", "poweroff"]),
        ]:
            row = Adw.ActionRow(title=label, subtitle=sub, activatable=True)
            row.add_prefix(Gtk.Image.new_from_icon_name(icon))
            row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
            row.connect("activated", lambda _r, l=label, a=argv: self._session(l, a))
            session.add(row)

    def _value(self, row):
        lbl = Gtk.Label()
        lbl.add_css_class("dim-label")
        lbl.add_css_class("numeric")
        row.add_suffix(lbl)
        return lbl

    def refresh(self):
        def got(ok, out, _e):
            try:
                d = json.loads(out)
            except ValueError:
                return
            charging = d["status"] == "Charging"
            self.hero.set_title(d["status"])
            self.hero.set_subtitle(d["time"] or ("On battery" if d["status"] == "Discharging" else "Plugged in"))
            self.hero_icon.set_from_icon_name(battery_icon(d["pct"], charging))
            self.pct.set_label(f"{d['pct']}%")
            self.level.set_value(d["pct"])

            profiles = d.get("profiles", [])
            self.mode_group.set_visible(bool(profiles))
            key = repr([p["id"] for p in profiles])
            if key != self.modes_key:
                self.modes_key = key
                self.quietly(lambda: self.modes.remove_all())
                for p in profiles:
                    self.modes.add(Adw.Toggle(name=p["id"], label=p["name"],
                                              tooltip=p["name"]))
            self.quietly(lambda: self.modes.set_active_name(d["profile"]) if d["profile"] else None)
            self.modes.set_sensitive(d["can_profile"])
            self.allow.set_visible(not d["can_profile"])
            self.quietly(lambda: self.awake.set_active(d["awake"]))
        run([tool("BarPanelData"), "battery"], got)

    def _mode(self, group_, _p):
        name = group_.get_active_name()
        if self._updating or not name:
            return
        run_quiet([tool("BarPanelAction"), "power-mode", name])

    def _allow(self):
        run_quiet([tool("PowerMode"), "--setup"], lambda ok: (self.toast("Power mode can be changed now" if ok
                                                                         else "Permission wasn't given"), self.refresh()))

    def _session(self, label, argv):
        if label == "Lock":
            launch(argv)
            return
        d = Adw.AlertDialog(heading=f"{label}?", body="Unsaved work in open apps may be lost." if label != "Suspend" else "")
        d.add_response("cancel", "Cancel")
        d.add_response("go", label)
        d.set_response_appearance("go", Adw.ResponseAppearance.DESTRUCTIVE if label != "Suspend"
                                  else Adw.ResponseAppearance.SUGGESTED)
        d.connect("response", lambda _d, r: r == "go" and launch(argv))
        d.present(self.window)
