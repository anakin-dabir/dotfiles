"""Fans & Performance: temperatures and fan speeds, fans automatic or full
speed, power mode and graphics mode (HP laptops / envycontrol)."""

import glob
import os
import shlex

from gi.repository import Adw, Gtk

from ..common import Page, group, have, launch, read_file, run, run_quiet, text_button, tool
from .apps import app_picker, command_of

MODE_NAMES = {"low-power": "Saver", "cool": "Cool", "quiet": "Quiet", "balanced": "Balanced",
              "balanced-performance": "Balanced+", "performance": "Performance"}
GPU_MODES = [("integrated", "Integrated", "Intel only: longest battery, the NVIDIA card is off"),
             ("hybrid", "Hybrid", "Intel by default, NVIDIA when an app asks for it"),
             ("nvidia", "NVIDIA", "Always the NVIDIA card: fastest, uses the most power")]


def hwmon(name):
    for d in glob.glob("/sys/class/hwmon/hwmon*"):
        if read_file(os.path.join(d, "name")) == name:
            return d
    return None


def available():
    hp = hwmon("hp")
    return bool(hp and glob.glob(os.path.join(hp, "fan*_input")))


def nvidia_device():
    for d in glob.glob("/sys/bus/pci/devices/*"):
        if read_file(os.path.join(d, "vendor")) == "0x10de" and read_file(os.path.join(d, "class")).startswith("0x03"):
            return d
    return None


class FansPage(Page):
    name = "fans"
    title = "Fans & Performance"
    icon = "weather-windy-symbolic"
    interval = 2

    def __init__(self, window):
        super().__init__(window)
        self.gpu_mode = None

        now = group(self, "Right now")
        self.cpu_t = self._value_row(now, "Processor temperature", "temperature-symbolic")
        self.gpu_t = self._value_row(now, "Graphics card temperature", "video-display-symbolic")
        self.fans = []
        hp = hwmon("hp")
        for i, f in enumerate(sorted(glob.glob(os.path.join(hp, "fan*_input"))) if hp else []):
            row = self._value_row(now, f"Fan {i + 1}", "weather-windy-symbolic")
            self.fans.append((row, f))

        fan = group(self, "Fans")
        self.fan_mode = Adw.ToggleGroup(homogeneous=True, margin_top=10, margin_bottom=10,
                                        margin_start=10, margin_end=10)
        self.fan_mode.add(Adw.Toggle(name="auto", label="Automatic"))
        self.fan_mode.add(Adw.Toggle(name="max", label="Full speed"))
        self.fan_mode.connect("notify::active-name", self._fan)
        fan.add(Adw.PreferencesRow(activatable=False, child=self.fan_mode))
        self.allow = Adw.ActionRow(title="Changing fans and power mode needs a one-time permission",
                                   subtitle="Asks for your password once")
        self.allow.add_suffix(text_button("Allow…", self._allow, css=["suggested-action"]))
        fan.add(self.allow)
        curves = Adw.ActionRow(title="Custom fan curves",
                               subtitle="Set in OMEN Hub, whose fan service controls the fans directly")
        if have("omen-hub"):
            curves.add_suffix(text_button("Open", lambda: launch(["omen-hub"])))
        else:
            curves.set_subtitle("Install OMEN Hub (omen-hub) for custom fan curves")
        fan.add(curves)

        perf = group(self, "Power mode", "How hard the processor and fans may work.")
        self.modes = Adw.ToggleGroup(homogeneous=True, margin_top=10, margin_bottom=10,
                                     margin_start=10, margin_end=10)
        for m in read_file("/sys/firmware/acpi/platform_profile_choices").split():
            self.modes.add(Adw.Toggle(name=m, label=MODE_NAMES.get(m, m.capitalize())))
        self.modes.connect("notify::active-name", self._mode)
        perf.add(Adw.PreferencesRow(activatable=False, child=self.modes))
        perf.set_visible(bool(read_file("/sys/firmware/acpi/platform_profile_choices")))

        self.gpu = group(self, "Graphics", "Which graphics card to use. Changing it needs a restart.")
        self.gpu_rows = {}
        for mode, title, sub in GPU_MODES:
            row = Adw.ActionRow(title=title, subtitle=sub, activatable=True)
            check = Gtk.CheckButton(valign=Gtk.Align.CENTER, can_target=False)
            row.add_prefix(check)
            row.check = check
            row.connect("activated", lambda _r, m=mode: self._gpu(m))
            self.gpu.add(row)
            self.gpu_rows[mode] = row
        # Run one app on the NVIDIA card (prime-run), the rest staying on the other one
        if have("prime-run"):
            nv = Adw.ActionRow(title="Run an app on the NVIDIA card",
                               subtitle="For games and heavy apps, while everything else uses the power-saving card")
            nv.add_prefix(Gtk.Image.new_from_icon_name("video-display-symbolic"))
            pick = Gtk.MenuButton(label="Choose app…", valign=Gtk.Align.CENTER)
            pick.set_popover(app_picker(lambda a: self._nvidia(a)))
            nv.add_suffix(pick)
            self.gpu.add(nv)
        self.gpu.set_visible(have("envycontrol") or have("prime-run"))
        if have("envycontrol"):
            run(["envycontrol", "--query"], lambda ok, out, _e: self._gpu_now(out.strip().splitlines()[-1] if out.strip() else ""))

    def _nvidia(self, app):
        try:
            argv = shlex.split(command_of(app))
        except ValueError:
            return
        launch(["prime-run"] + argv)
        self.toast(f"{app.get_name()} on the NVIDIA card")

    def _value_row(self, g, title, icon):
        row = Adw.ActionRow(title=title)
        row.add_prefix(Gtk.Image.new_from_icon_name(icon))
        row.value = Gtk.Label()
        row.value.add_css_class("numeric")
        row.add_suffix(row.value)
        g.add(row)
        return row

    # ----- live readings -----

    def refresh(self):
        core = hwmon("coretemp")
        temp = read_file(os.path.join(core, "temp1_input")) if core else ""
        self.cpu_t.value.set_label(f"{int(temp) // 1000} °C" if temp.isdigit() else "–")
        for row, f in self.fans:
            rpm = read_file(f)
            row.value.set_label(f"{int(rpm):,} rpm".replace(",", " ") if rpm.isdigit() else "–")
        self._gpu_temp()
        def fan_now(ok, out, _e):
            if ok and out.strip() in ("auto", "max"):
                self.quietly(lambda: self.fan_mode.set_active_name(out.strip()))
        run([tool("FanMode")], fan_now)
        profile = read_file("/sys/firmware/acpi/platform_profile")
        if profile:
            self.quietly(lambda: self.modes.set_active_name(profile))
        writable = os.access("/sys/firmware/acpi/platform_profile", os.W_OK) and all(
            os.access(p, os.W_OK) for p in glob.glob("/sys/devices/platform/hp-wmi/hwmon/hwmon*/pwm1_enable"))
        self.allow.set_visible(not writable)
        self.fan_mode.set_sensitive(writable)
        self.modes.set_sensitive(os.access("/sys/firmware/acpi/platform_profile", os.W_OK))

    def _gpu_temp(self):
        dev = nvidia_device()
        if not dev:
            self.gpu_t.set_visible(False)
            return
        # Asking a sleeping NVIDIA card for its temperature would wake it up
        if read_file(os.path.join(dev, "power", "runtime_status")) != "active":
            self.gpu_t.value.set_label("Asleep (saving power)")
            return
        if have("nvidia-smi"):
            run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                lambda ok, out, _e: self.gpu_t.value.set_label(f"{out.strip()} °C" if ok and out.strip().isdigit() else "–"))

    # ----- changes -----

    def _fan(self, g, _p):
        name = g.get_active_name()
        if not self._updating and name:
            run_quiet([tool("FanMode"), name], lambda ok: ok or self.toast("Couldn't change the fans"))

    def _mode(self, g, _p):
        name = g.get_active_name()
        if not self._updating and name:
            run_quiet([tool("BarPanelAction"), "power-mode", name])

    def _allow(self):
        run_quiet([tool("AllowHardware")], lambda ok: (self.toast("Done: fans and power mode can be changed now"
                                                                  if ok else "Permission wasn't given"), self.refresh()))

    def _gpu_now(self, mode):
        self.gpu_mode = mode
        for m, row in self.gpu_rows.items():
            row.check.set_active(m == mode)
            row.set_subtitle(next(sub for mm, _t, sub in GPU_MODES if mm == m) + ("  ·  in use" if m == mode else ""))

    def _gpu(self, mode):
        if mode == self.gpu_mode:
            return
        title = next(t for m, t, _s in GPU_MODES if m == mode)
        d = Adw.AlertDialog(heading=f"Switch to {title} graphics?",
                            body="Asks for your password. The change takes effect after a restart.")
        d.add_response("cancel", "Cancel")
        d.add_response("switch", "Switch")
        d.set_response_appearance("switch", Adw.ResponseAppearance.SUGGESTED)

        def answered(_d, r):
            if r != "switch":
                return

            def done(ok, _o, err):
                if not ok:
                    self.toast("Graphics mode wasn't changed")
                    return
                self._gpu_now(mode)
                again = Adw.AlertDialog(heading="Restart now?", body=f"{title} graphics will be used after a restart.")
                again.add_response("later", "Later")
                again.add_response("restart", "Restart")
                again.set_response_appearance("restart", Adw.ResponseAppearance.DESTRUCTIVE)
                again.connect("response", lambda _d2, r2: r2 == "restart" and launch(["systemctl", "reboot"]))
                again.present(self.window)
            run(["pkexec", "envycontrol", "-s", mode], done)
        d.connect("response", answered)
        d.present(self.window)
