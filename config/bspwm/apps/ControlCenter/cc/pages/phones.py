"""Phones: Android and iPhone over USB - open their files (gvfs: MTP / AFC),
mount and unmount, show an Android screen (scrcpy), open iPhones by
themselves when plugged in (bin/iphone-automount reads config/phones.json)."""

import json
import os
import shlex

from gi.repository import Adw, Gio, GLib, Gtk

from ..common import BSPDIR, Page, group, have, launch, quick, run, text_button, widgets_changed

SETTINGS = os.path.join(BSPDIR, "config", "phones.json")
APPS = os.path.join(BSPDIR, "config", "apps.json")
PHONE_SCHEMES = ("mtp", "afc", "gphoto2")


def phone_settings():
    try:
        with open(SETTINGS) as f:
            return {"iphone_auto": bool(json.load(f).get("iphone_auto", True))}
    except (OSError, ValueError):
        return {"iphone_auto": True}


def file_manager():
    try:
        with open(APPS) as f:
            return json.load(f).get("files", "thunar")
    except (OSError, ValueError):
        return "thunar"


def scheme_of(obj):
    f = obj.get_activation_root() if isinstance(obj, Gio.Volume) else obj.get_root()
    return f.get_uri_scheme() if f else ""


class PhonesPage(Page):
    name = "phones"
    title = "Phones"
    icon = "phone-symbolic"
    interval = 3

    def __init__(self, window):
        super().__init__(window)
        self.monitor = Gio.VolumeMonitor.get()
        for sig in ("volume-added", "volume-removed", "mount-added", "mount-removed", "volume-changed"):
            self.monitor.connect(sig, lambda *_: self._fill())
        self.connected = group(self, "Connected", "Plug a phone in with a USB cable.")
        self.rows = []
        hint = group(self, "Not showing up?")
        for title, sub in [
            ("Android", "On the phone, pull down the notifications, tap the USB one and choose “File transfer”."),
            ("iPhone", "Unlock it and tap “Trust” when it asks whether to trust this computer."),
        ]:
            r = Adw.ActionRow(title=title, subtitle=sub)
            r.set_subtitle_lines(3)
            hint.add(r)
        opts = group(self, "Options")
        self.auto = Adw.SwitchRow(title="Open iPhones by themselves", subtitle="Their photos and media, as soon as "
                                                                              "they're plugged in and trusted")
        self.auto.connect("notify::active", lambda r, _p: self._updating or self._save(iphone_auto=r.get_active()))
        opts.add(self.auto)
        self.quietly(lambda: self.auto.set_active(phone_settings()["iphone_auto"]))
        self.adb = []
        self._fill()

    def refresh(self):
        # Android screen sharing needs USB debugging (adb); check now and then
        if have("adb"):
            run(["adb", "devices"], lambda ok, out, _e: self._adb(out if ok else ""))

    def _adb(self, out):
        devs = [ln.split()[0] for ln in out.splitlines()[1:] if ln.strip().endswith("device")]
        if devs != self.adb:
            self.adb = devs
            self._fill()

    # ----- list -----

    def _phones(self):
        """[(name, volume or None, mount or None)] for phones gvfs sees."""
        out, seen = [], set()
        for v in self.monitor.get_volumes():
            if scheme_of(v) in PHONE_SCHEMES:
                m = v.get_mount()
                out.append((v.get_name(), v, m))
                if m:
                    seen.add(m.get_root().get_uri())
        for m in self.monitor.get_mounts():
            if scheme_of(m) in PHONE_SCHEMES and m.get_root().get_uri() not in seen:
                out.append((m.get_name(), None, m))
        return out

    def _fill(self):
        for r in self.rows:
            self.connected.remove(r)
        self.rows.clear()
        phones = self._phones()
        iphones = quick(["idevice_id", "-l"]).split() if have("idevice_id") else []
        if not phones:
            r = Adw.ActionRow(title="No phone connected" if not iphones else "iPhone connected, not trusted yet",
                              subtitle="" if not iphones else "Unlock it and tap “Trust”")
            r.add_css_class("dim-label")
            self.connected.add(r)
            self.rows.append(r)
        for name, vol, mount in phones:
            kind = "iPhone" if scheme_of(vol or mount) == "afc" else "Android"
            r = Adw.ActionRow(title=GLib.markup_escape_text(name),
                              subtitle=f"{kind} · {'open' if mount else 'not opened yet'}")
            icon = (vol or mount).get_symbolic_icon()
            r.add_prefix(Gtk.Image.new_from_gicon(icon) if icon else Gtk.Image.new_from_icon_name("phone-symbolic"))
            if kind == "Android" and self.adb and have("scrcpy"):
                r.add_suffix(text_button("Show screen", lambda: launch(["scrcpy"])))
            if mount:
                r.add_suffix(text_button("Eject", lambda m=mount: self._eject(m)))
                r.add_suffix(text_button("Open files", lambda m=mount: self._open(m), css=["suggested-action"]))
            elif vol:
                r.add_suffix(text_button("Open files", lambda v=vol: self._mount(v), css=["suggested-action"]))
            self.connected.add(r)
            self.rows.append(r)
        if self.adb and not phones and have("scrcpy"):
            r = Adw.ActionRow(title="Android (USB debugging)", subtitle="Its files: choose “File transfer” on the phone")
            r.add_suffix(text_button("Show screen", lambda: launch(["scrcpy"])))
            self.connected.add(r)
            self.rows.append(r)
        widgets_changed()

    # ----- actions -----

    def _mount(self, vol):
        op = Gtk.MountOperation(parent=self.window)

        def done(v, res):
            try:
                v.mount_finish(res)
            except GLib.Error as e:
                self.toast(f"Couldn't open it: {e.message}")
                return
            if v.get_mount():
                self._open(v.get_mount())
        vol.mount(Gio.MountMountFlags.NONE, op, None, done)

    def _open(self, mount):
        path = mount.get_root().get_path()            # (gvfs makes a normal folder for it)
        if not path:
            Gio.AppInfo.launch_default_for_uri(mount.get_root().get_uri(), None)
            return
        try:
            cmd = shlex.split(file_manager())
        except ValueError:
            cmd = ["thunar"]
        launch(cmd + [path])

    def _eject(self, mount):
        op = Gtk.MountOperation(parent=self.window)

        def done(m, res):
            try:
                m.unmount_with_operation_finish(res)
                self.toast(f"{m.get_name()} can be unplugged")
            except GLib.Error as e:
                self.toast(f"Couldn't eject it: {e.message}")
        mount.unmount_with_operation(Gio.MountUnmountFlags.NONE, op, None, done)

    def _save(self, **changes):
        s = phone_settings()
        s.update(changes)
        try:
            with open(SETTINGS, "w") as f:
                json.dump(s, f, indent=2)
                f.write("\n")
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
