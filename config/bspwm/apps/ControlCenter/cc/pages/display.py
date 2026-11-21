"""Display: brightness, night light, resolution and refresh rate."""

import os
import re

from gi.repository import Adw, GLib, Gtk

from ..common import HOME, Page, group, launch, read_file, run, run_quiet, slider_row, tool

SAVED = os.path.join(HOME, ".cache", "barpanel")


def parse_xrandr(text):
    """Connected outputs: [{name, primary, builtin, size, current, rate, modes: {WxH: [rates]}}]"""
    outs, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^(\S+) (connected|disconnected)( primary)?\s*(\d+x\d+\+\d+\+\d+)?", line)
        if m:
            cur = None
            if m.group(2) == "connected":
                cur = {"name": m.group(1), "primary": bool(m.group(3)), "on": bool(m.group(4)),
                       "builtin": m.group(1).startswith(("eDP", "LVDS", "DSI")),
                       "current": "", "rate": "", "modes": {}}
                outs.append(cur)
            continue
        if cur is None:
            continue
        m = re.match(r"^\s+(\d+x\d+)\S*\s+(.*)$", line)
        if not m:
            continue
        mode, rest = m.group(1), m.group(2)
        rates = cur["modes"].setdefault(mode, [])
        for r in re.findall(r"([\d.]+)([*+ ]*)", rest):
            if r[0] not in rates:
                rates.append(r[0])
            if "*" in r[1]:
                cur["current"], cur["rate"] = mode, r[0]
    return outs


class DisplayPage(Page):
    name = "display"
    title = "Display"
    icon = "video-display-symbolic"
    interval = 3

    def __init__(self, window):
        super().__init__(window)
        screen = group(self, "Screen")
        self.bright = slider_row("Brightness", "display-brightness-symbolic", 1, 100,
                                 lambda v: run_quiet(["brightnessctl", "-q", "set", f"{v}%"]))
        screen.add(self.bright)

        night = group(self, "Night light", "Warmer colours in the evening, easier on the eyes. Stays on after a restart.")
        self.night = Adw.SwitchRow(title="Night light")
        self.night.add_prefix(Gtk.Image.new_from_icon_name("weather-clear-night-symbolic"))
        self.night.connect("notify::active", self._night_toggled)
        night.add(self.night)
        self.warmth = slider_row("Warmth", None, 2500, 6000, self._warmth, step=100, unit=" K")
        self.warmth.set_subtitle("Lower is warmer")
        self.warmth.scale.set_inverted(True)        # warmer to the right
        night.add(self.warmth)

        self.monitors = group(self, "Monitors")
        self.monitor_rows = []
        self.layout = None
        self.pending = None   # resolution change waiting for "keep"

    # ----- night light -----

    def _night_toggled(self, row, _p):
        if not self._updating:
            run_quiet([tool("BarPanelAction"), "night"])

    def _warmth(self, kelvin):
        run_quiet([tool("BarPanelAction"), "night-temp", str(kelvin)])

    # ----- refresh -----

    def refresh(self):
        def bright(ok, out, _e):
            parts = out.strip().split(",")
            if ok and len(parts) >= 4:
                self.bright.set_value(int(parts[3].rstrip("%") or 0))
        run(["brightnessctl", "-m"], bright)
        on = os.path.exists(os.path.join(SAVED, "nightlight"))
        temp = read_file(os.path.join(SAVED, "nightlight-temp"), "4000")
        self.quietly(lambda: self.night.set_active(on))
        self.warmth.set_value(int(temp) if temp.isdigit() else 4000)
        self.warmth.set_sensitive(True)
        if self.pending is None:
            run(["xrandr", "--query"], lambda ok, out, _e: ok and self._monitors(parse_xrandr(out)))

    def _monitors(self, outs):
        key = repr([(o["name"], o["current"], o["rate"], o["on"], sorted(o["modes"])) for o in outs])
        if key == self.layout:
            return
        self.layout = key
        for r in self.monitor_rows:
            self.monitors.remove(r)
        self.monitor_rows.clear()
        for o in outs:
            self._monitor_rows(o)

    def _monitor_rows(self, o):
        label = ("Built-in display" if o["builtin"] else "External display") + f" · {o['name']}"
        exp = Adw.ExpanderRow(title=label, subtitle=f"{o['current']} · {float(o['rate'] or 0):.0f} Hz" if o["on"] else "Off")
        exp.add_prefix(Gtk.Image.new_from_icon_name("computer-symbolic" if o["builtin"] else "video-display-symbolic"))
        exp.set_expanded(len(self.monitor_rows) == 0)
        modes = list(o["modes"])          # xrandr lists them biggest first
        res = Adw.ComboRow(title="Resolution", model=Gtk.StringList.new(modes))
        if o["current"] in modes:
            res.set_selected(modes.index(o["current"]))
        rate = Adw.ComboRow(title="Refresh rate")

        def fill_rates(selected_rate=None):
            mode = modes[res.get_selected()]
            rates = sorted(o["modes"][mode], key=float, reverse=True)
            rate.rates = rates
            rate.set_model(Gtk.StringList.new([f"{float(r):.2f} Hz".replace(".00 ", " ") for r in rates]))
            if selected_rate in rates:
                rate.set_selected(rates.index(selected_rate))
        fill_rates(o["rate"])

        def changed(*_):
            if self._updating:
                return
            mode = modes[res.get_selected()]
            r = rate.rates[rate.get_selected()] if rate.get_selected() < len(rate.rates) else rate.rates[0]
            if (mode, r) != (o["current"], o["rate"]):
                self._try_mode(o, mode, r)

        def res_changed(*_):
            if self._updating:
                return
            self.quietly(lambda: fill_rates(o["rate"] if modes[res.get_selected()] == o["current"] else None))
            changed()

        res.connect("notify::selected", res_changed)
        rate.connect("notify::selected", changed)
        exp.add_row(res)
        exp.add_row(rate)
        self.monitors.add(exp)
        self.monitor_rows.append(exp)

    def _try_mode(self, o, mode, rate):
        """Switch, then ask to keep it; switch back after 15 s without an answer."""
        old = ["xrandr", "--output", o["name"], "--mode", o["current"], "--rate", o["rate"]]
        self.pending = old
        run_quiet(["xrandr", "--output", o["name"], "--mode", mode, "--rate", rate], lambda ok: ask(ok))

        def ask(ok):
            if not ok:
                self.toast("That mode didn't work")
                self.pending = None
                self.layout = None
                self.refresh()
                return
            left = [15]
            d = Adw.AlertDialog(heading="Keep these display settings?",
                                body=f"Going back in {left[0]} seconds…")
            d.add_response("revert", "Go Back")
            d.add_response("keep", "Keep")
            d.set_response_appearance("keep", Adw.ResponseAppearance.SUGGESTED)
            d.set_default_response("keep")
            d.set_close_response("revert")

            def tick():
                left[0] -= 1
                if left[0] <= 0:
                    d.force_close()      # -> close response: revert
                    return False
                d.set_body(f"Going back in {left[0]} seconds…")
                return True
            timer = GLib.timeout_add_seconds(1, tick)

            def answered(_d, response):
                GLib.source_remove(timer) if left[0] > 0 else None
                if response == "keep":
                    self._after_change()
                else:
                    run_quiet(old, lambda _ok: self._after_change())
                self.pending = None
                self.layout = None
                GLib.timeout_add(400, lambda: (self.refresh(), False)[1])
            d.connect("response", answered)
            d.present(self.window)

    def _after_change(self):
        # Wallpaper and bars follow the new size
        fehbg = os.path.join(HOME, ".fehbg")
        if os.path.exists(fehbg):
            launch(["sh", fehbg])
        run_quiet(["polybar-msg", "cmd", "restart"])
