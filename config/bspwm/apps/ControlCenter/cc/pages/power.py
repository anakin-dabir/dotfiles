"""Power: battery, power mode, keep awake, and lock/suspend/restart/shut down."""

import json
import os

from gi.repository import Adw, Gtk

from ..common import BSPDIR, Page, group, launch, run, run_quiet, text_button, tool

SETTINGS = os.path.join(BSPDIR, "config", "power.json")


def subprocess_running(name):
    import subprocess
    return subprocess.run(["pgrep", "-f", f"bin/{name}$"], capture_output=True).returncode == 0
DARK = [(0, "Never"), (2, "2 minutes"), (5, "5 minutes"), (10, "10 minutes"), (15, "15 minutes"), (30, "30 minutes")]
LOCK = [(0, "Never"), (5, "5 minutes"), (10, "10 minutes"), (15, "15 minutes"), (30, "30 minutes"), (60, "1 hour")]
EMPTY = [("none", "Only warn"), ("suspend", "Sleep"), ("poweroff", "Shut down")]


def power_settings():
    try:
        with open(SETTINGS) as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    return {"battery_warn": s.get("battery_warn", True), "low": int(s.get("low", 15)),
            "very_low": int(s.get("very_low", 5)), "critical_action": s.get("critical_action", "none"),
            "critical_at": int(s.get("critical_at", 3)), "screen_dark": int(s.get("screen_dark", 0)),
            "lock_after": int(s.get("lock_after", 0)), "lock_on_sleep": bool(s.get("lock_on_sleep", False))}

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

        # Low battery (bin/battery-warn, checked every minute)
        low = group(self, "Low battery", "Warnings while the battery runs down (not while charging).")
        self.warn = Adw.SwitchRow(title="Warn when the battery is low")
        self.warn.connect("notify::active", lambda r, _p: self._set(battery_warn=r.get_active()))
        low.add(self.warn)
        self.low = Adw.SpinRow.new_with_range(5, 50, 1)
        self.low.set_title("First warning at")
        self.low.set_subtitle("Percent")
        self.low.connect("notify::value", lambda r, _p: self._set(low=int(r.get_value())))
        low.add(self.low)
        self.vlow = Adw.SpinRow.new_with_range(2, 30, 1)
        self.vlow.set_title("Urgent warning at")
        self.vlow.set_subtitle("Percent")
        self.vlow.connect("notify::value", lambda r, _p: self._set(very_low=int(r.get_value())))
        low.add(self.vlow)
        self.empty = Adw.ComboRow(title="When it's almost empty", subtitle="Warns a minute before, so you can plug in",
                                  model=Gtk.StringList.new([t for _v, t in EMPTY]))
        self.empty.connect("notify::selected", lambda r, _p: self._set(critical_action=EMPTY[r.get_selected()][0]))
        low.add(self.empty)
        self.empty_at = Adw.SpinRow.new_with_range(1, 15, 1)
        self.empty_at.set_title("Almost empty means")
        self.empty_at.set_subtitle("Percent")
        self.empty_at.connect("notify::value", lambda r, _p: self._set(critical_at=int(r.get_value())))
        low.add(self.empty_at)

        # Screen and lock (bin/IdleWatch)
        lockg = group(self, "Screen and lock", "When you're away. Not while something plays, a window is full "
                                                "screen or Keep awake is on.")
        self.dark = Adw.ComboRow(title="Dark screen after", subtitle="The backlight goes off; any key brings it back",
                                 model=Gtk.StringList.new([t for _v, t in DARK]))
        self.dark.connect("notify::selected", lambda r, _p: self._set(screen_dark=DARK[r.get_selected()][0]))
        lockg.add(self.dark)
        self.lock_after = Adw.ComboRow(title="Lock after", model=Gtk.StringList.new([t for _v, t in LOCK]))
        self.lock_after.connect("notify::selected", lambda r, _p: self._set(lock_after=LOCK[r.get_selected()][0]))
        lockg.add(self.lock_after)
        self.lock_sleep = Adw.SwitchRow(title="Lock before sleeping", subtitle="Also when you close the lid")
        self.lock_sleep.connect("notify::active", lambda r, _p: self._set(lock_on_sleep=r.get_active()))
        lockg.add(self.lock_sleep)
        self._load_settings()

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

    # ----- settings (config/power.json) -----

    def _load_settings(self):
        p = power_settings()

        def put():
            self.warn.set_active(bool(p["battery_warn"]))
            self.low.set_value(p["low"])
            self.vlow.set_value(p["very_low"])
            self.empty.set_selected(next((i for i, (v, _t) in enumerate(EMPTY) if v == p["critical_action"]), 0))
            self.empty_at.set_value(p["critical_at"])
            self.dark.set_selected(next((i for i, (v, _t) in enumerate(DARK) if v == p["screen_dark"]), 0))
            self.lock_after.set_selected(next((i for i, (v, _t) in enumerate(LOCK) if v == p["lock_after"]), 0))
            self.lock_sleep.set_active(p["lock_on_sleep"])
        self.quietly(put)
        for w in (self.low, self.vlow, self.empty, self.empty_at):
            w.set_sensitive(bool(p["battery_warn"]))
        self.empty_at.set_visible(p["critical_action"] != "none")

    def _set(self, **changes):
        if self._updating:
            return
        p = power_settings()
        p.update(changes)
        try:
            with open(SETTINGS, "w") as f:
                json.dump(p, f, indent=2)
                f.write("\n")
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
            return
        self._load_settings()
        # (the watcher reads the file every second; make sure it's running)
        if subprocess_running("IdleWatch") is False:
            launch([tool("IdleWatch")])

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
