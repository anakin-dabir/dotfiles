"""Sound: output and input volume, mute, and which device to use."""

import json

from gi.repository import Adw, Gtk

from ..common import Page, group, have, launch, run, run_quiet, slider_row, text_button, tool


def devices(kind, done):
    """kind 'sinks' or 'sources' -> done(list of {name, desc}, default name).
    Leaves out devices whose ports are all unplugged and monitor sources."""
    def listed(ok, out, _e):
        try:
            items = json.loads(out) if ok else []
        except ValueError:
            items = []

        def default(ok2, name, _e2):
            name = name.strip()
            keep = []
            for d in items:
                if kind == "sources" and (d.get("monitor_of_sink") not in (None, "", "n/a") or d["name"].endswith(".monitor")):
                    continue
                ports = d.get("ports") or []
                if ports and all(p.get("availability") == "not available" for p in ports) and d["name"] != name:
                    continue
                keep.append({"name": d["name"], "desc": d.get("description") or d["name"]})
            done(keep, name)
        run(["pactl", "get-default-sink" if kind == "sinks" else "get-default-source"], default)
    run(["pactl", "-f", "json", "list", kind], listed)


class SoundPage(Page):
    name = "sound"
    title = "Sound"
    icon = "audio-volume-high-symbolic"
    interval = 2

    def __init__(self, window):
        super().__init__(window)
        out = group(self, "Output")
        self.vol = slider_row("Volume", None, 0, 100, lambda v: run_quiet([tool("BarPanelAction"), "vol-set", str(v)]))
        out.add(self.vol)
        self.mute = Adw.SwitchRow(title="Mute")
        self.mute.connect("notify::active", lambda *_: self._updating or run_quiet(["pamixer", "-t"]))
        out.add(self.mute)
        self.sink = Adw.ComboRow(title="Play sound through")
        self.sink.names = []
        self.sink.connect("notify::selected", self._pick_sink)
        out.add(self.sink)

        mic = group(self, "Input")
        self.mic = slider_row("Microphone volume", None, 0, 100,
                              lambda v: run_quiet([tool("BarPanelAction"), "mic-set", str(v)]))
        mic.add(self.mic)
        self.mic_mute = Adw.SwitchRow(title="Mute microphone")
        self.mic_mute.connect("notify::active", lambda *_: self._updating or run_quiet(["pamixer", "--default-source", "-t"]))
        mic.add(self.mic_mute)
        self.source = Adw.ComboRow(title="Microphone")
        self.source.names = []
        self.source.connect("notify::selected", self._pick_source)
        mic.add(self.source)

        if have("pavucontrol"):
            more = group(self)
            row = Adw.ActionRow(title="Per-app volume and advanced settings", subtitle="Volume Control (pavucontrol)")
            row.add_suffix(text_button("Open", lambda: launch(["pavucontrol"])))
            more.add(row)

    def _icon(self, vol, muted):
        if muted or vol == 0:
            return "audio-volume-muted-symbolic"
        return "audio-volume-" + ("low" if vol < 34 else "medium" if vol < 67 else "high") + "-symbolic"

    def refresh(self):
        def got(ok, out, _e):
            try:
                d = json.loads(out)
            except ValueError:
                return
            self.vol.set_value(d.get("vol", 0))
            self.mic.set_value(d.get("mic_vol", 0))
            self.quietly(lambda: (self.mute.set_active(bool(d.get("muted"))),
                                  self.mic_mute.set_active(bool(d.get("mic_muted")))))
        run([tool("BarPanelData"), "sound"], got)
        devices("sinks", lambda items, cur: self._fill(self.sink, items, cur))
        devices("sources", lambda items, cur: self._fill(self.source, items, cur))

    def _fill(self, combo, items, current):
        names = [i["name"] for i in items]

        def update():
            if names != combo.names:
                combo.names = names
                combo.set_model(Gtk.StringList.new([i["desc"] for i in items]))
            if current in names:
                combo.set_selected(names.index(current))
            combo.set_sensitive(len(names) > 1)
        self.quietly(update)

    def _pick_sink(self, combo, _p):
        if not self._updating and combo.get_selected() < len(combo.names):
            run_quiet([tool("BarPanelAction"), "sink", combo.names[combo.get_selected()]])

    def _pick_source(self, combo, _p):
        if not self._updating and combo.get_selected() < len(combo.names):
            run_quiet(["pactl", "set-default-source", combo.names[combo.get_selected()]])
