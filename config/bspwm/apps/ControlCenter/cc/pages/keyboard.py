"""Keyboard: backlight colour and effects (HP RGB keyboards, via
bin/kbd-effect). Changes go to the keyboard straight away."""

import json
import math
import os

from gi.repository import Adw, Gdk, Gtk

from ..common import BSPDIR, Page, group, read_file, run_quiet, slider_row, tool
from ..pickers import ColorButton

ZONES = "/sys/devices/platform/hp-wmi/rgb_zones"
SETTINGS = os.path.join(BSPDIR, "config", "keyboard.json")
PALETTE = os.path.join(BSPDIR, "kbd-colors.conf")
EFFECTS = [("static", "Static"), ("breathing", "Breathing"), ("rainbow", "Rainbow")]
MODE_NAMES = {"low-power": "Saver", "cool": "Cool", "quiet": "Quiet", "balanced": "Balanced",
              "balanced-performance": "Balanced+", "performance": "Performance"}


def available():
    return os.path.isdir(ZONES)


def settings():
    try:
        with open(SETTINGS) as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    color = (s.get("color") or read_file("/etc/kbd-backlight.conf") or "FFFFFF").upper()
    return {"effect": s.get("effect", "static"), "color": color, "speed": int(s.get("speed", 5)),
            "brightness": int(s.get("brightness", 100)), "follow_power": bool(s.get("follow_power", False)),
            "power_colors": s.get("power_colors", {})}


def palette():
    out = []
    for line in read_file(PALETTE).splitlines():
        parts = line.split(None, 1)
        if parts and not line.lstrip().startswith("#") and len(parts[0]) == 6:
            out.append((parts[0].upper(), parts[1].strip() if len(parts) > 1 else parts[0]))
    return out


def rgb(hexstr):
    h = hexstr.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


class KeyboardPreview(Gtk.DrawingArea):
    """A laptop keyboard drawing, lit in the current colour (or a rainbow)."""

    ROWS = [14, 14, 13, 12, 11, 7]

    def __init__(self):
        super().__init__(content_height=170, hexpand=True)
        self.color, self.effect, self.brightness = "FFFFFF", "static", 100
        self.set_draw_func(self._draw)

    def show(self, color, effect, brightness):
        self.color, self.effect, self.brightness = color, effect, brightness
        self.queue_draw()

    def _draw(self, _a, cr, w, h):
        pad, gap = 10, 4
        cr.set_source_rgb(0.09, 0.09, 0.1)
        self._round(cr, 0, 0, w, h, 12)
        cr.fill()
        rows = len(self.ROWS)
        key_h = (h - 2 * pad - (rows - 1) * gap) / rows
        k = self.brightness / 100
        for r, n in enumerate(self.ROWS):
            y = pad + r * (key_h + gap)
            widths = [1.0] * n
            if r == 5:                       # space bar row
                widths = [1.2, 1.0, 1.2, 6.0, 1.2, 1.0, 1.2]
            elif n < 14:
                widths[0] = widths[-1] = 1 + (14 - n) / 2
            unit = (w - 2 * pad - (len(widths) - 1) * gap) / sum(widths)
            x = pad
            for i, kw in enumerate(widths):
                kwp = kw * unit
                if self.effect == "rainbow":
                    hue = (x + kwp / 2) / w
                    c = Gdk.RGBA()
                    c.parse(f"hsl({int(hue * 360)}, 95%, 55%)")
                    col = (c.red, c.green, c.blue)
                else:
                    col = rgb(self.color)
                glow = 0.6 if self.effect == "breathing" else 1.0
                cr.set_source_rgb(0.16, 0.16, 0.18)
                self._round(cr, x, y, kwp, key_h, 4)
                cr.fill()
                # the legend/edge glow in the backlight colour
                cr.set_source_rgba(*col, 0.55 * k * glow)
                self._round(cr, x + 1, y + 1, kwp - 2, key_h - 2, 3.5)
                cr.set_line_width(1.6)
                cr.stroke()
                cr.set_source_rgba(*col, 0.9 * k * glow)
                cr.arc(x + kwp / 2, y + key_h / 2, min(2.2, key_h / 6), 0, 2 * math.pi)
                cr.fill()
                x += kwp + gap

    @staticmethod
    def _round(cr, x, y, w, h, r):
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()


class KeyboardPage(Page):
    name = "keyboard"
    title = "Keyboard"
    icon = "input-keyboard-symbolic"
    interval = 0

    def __init__(self, window):
        super().__init__(window)
        self.s = settings()

        self.preview = KeyboardPreview()
        self.sticky_widget = Adw.Clamp(child=self.preview, maximum_size=520, margin_top=10, margin_bottom=12,
                                       margin_start=12, margin_end=12)

        eff = group(self, "Effect")
        self.effects = Adw.ToggleGroup(homogeneous=True)
        for name, label in EFFECTS:
            self.effects.add(Adw.Toggle(name=name, label=label))
        self.effects.connect("notify::active-name", self._effect)
        eff.add(self.effects)

        col = group(self, "Colour", "Click a colour to use it. Not used by Rainbow.")
        self.swatches = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=12,
                                    min_children_per_line=6, column_spacing=6, row_spacing=6, homogeneous=True)
        for hexc, label in palette():
            self.swatches.append(self._swatch(hexc, label))
        self.swatches.set_margin_top(10)
        self.swatches.set_margin_bottom(10)
        self.swatches.set_margin_start(10)
        self.swatches.set_margin_end(10)
        col.add(Adw.PreferencesRow(activatable=False, child=self.swatches))
        custom = Adw.ActionRow(title="Your own colour")
        self.custom = ColorButton("Keyboard colour", lambda value: self.apply(color=value.lstrip("#").upper()))
        custom.add_suffix(self.custom)
        custom.set_activatable_widget(self.custom)
        col.add(custom)

        look = group(self, "Light")
        self.bright = slider_row("Brightness", "display-brightness-symbolic", 10, 100,
                                 lambda v: self.apply(brightness=v))
        look.add(self.bright)
        self.speed = slider_row("Speed", "media-playlist-repeat-symbolic", 1, 10,
                                lambda v: self.apply(speed=v), unit="")
        self.speed.set_subtitle("Breathing and Rainbow")
        look.add(self.speed)

        self.power = group(self, "Power mode colours", "A colour for each power mode, used when you switch modes.")
        self.follow = Adw.SwitchRow(title="Change colour with the power mode")
        self.follow.connect("notify::active", lambda r, _p: self._updating or self._save(follow_power=r.get_active()))
        self.power.add(self.follow)
        self.mode_rows = []
        for mode in read_file("/sys/firmware/acpi/platform_profile_choices").split():
            row = Adw.ActionRow(title=MODE_NAMES.get(mode, mode.capitalize()))
            btn = ColorButton(f"{MODE_NAMES.get(mode, mode)} colour", lambda value, m=mode: self._mode_color(m, value))
            row.add_suffix(btn)
            row.set_activatable_widget(btn)
            row.btn, row.mode = btn, mode
            self.power.add(row)
            self.mode_rows.append(row)
        self.power.set_visible(bool(self.mode_rows))
        self.load()

    def _swatch(self, hexc, label):
        b = Gtk.Button(tooltip_text=label)
        b.add_css_class("cc-swatch")
        area = Gtk.DrawingArea(content_width=26, content_height=26)
        area.set_draw_func(lambda _a, cr, w, h: (cr.set_source_rgb(*rgb(hexc)),
                                                  cr.arc(w / 2, h / 2, min(w, h) / 2, 0, 2 * math.pi), cr.fill()))
        b.set_child(area)
        b.connect("clicked", lambda *_: self.apply(color=hexc))
        return b

    # ----- state -----

    def load(self):
        self.s = settings()
        s = self.s

        def put():
            self.effects.set_active_name(s["effect"])
            self.follow.set_active(s["follow_power"])
            for row in self.mode_rows:
                row.btn.set_hex("#" + s["power_colors"].get(row.mode, s["color"]))
        self.quietly(put)
        self.custom.set_hex("#" + s["color"])
        self.bright.set_value(s["brightness"])
        self.speed.set_value(s["speed"])
        self.speed.set_sensitive(s["effect"] != "static")
        self.preview.show(s["color"], s["effect"], s["brightness"])

    def refresh(self):
        self.load()

    def _effect(self, group_, _p):
        name = group_.get_active_name()
        if not self._updating and name:
            self.apply(effect=name)

    def apply(self, effect=None, color=None, brightness=None, speed=None):
        s = self.s
        if effect:
            s["effect"] = effect
        if color:
            s["color"] = color
            if s["effect"] == "rainbow":          # picking a colour means you want it
                s["effect"] = "static"
                self.quietly(lambda: self.effects.set_active_name("static"))
        if brightness is not None:
            s["brightness"] = int(brightness)
        if speed is not None:
            s["speed"] = int(speed)
        argv = [tool("kbd-effect"), s["effect"]]
        if s["effect"] != "rainbow":
            argv.append(s["color"])
        argv += ["--speed", str(s["speed"]), "--brightness", str(s["brightness"])]
        run_quiet(argv)
        self.custom.set_hex("#" + s["color"])
        self.speed.set_sensitive(s["effect"] != "static")
        self.preview.show(s["color"], s["effect"], s["brightness"])

    def _save(self, **changes):
        try:
            with open(SETTINGS) as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        data.update(changes)
        os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
        with open(SETTINGS, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

    def _mode_color(self, mode, value):
        colors = dict(self.s.get("power_colors", {}))
        colors[mode] = value.lstrip("#").upper()
        self.s["power_colors"] = colors
        self._save(power_colors=colors)
