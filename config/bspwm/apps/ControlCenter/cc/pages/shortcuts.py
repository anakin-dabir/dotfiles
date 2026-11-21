"""Shortcuts: every key combination (config/sxhkdrc), what it does, change
its keys, turn it off, add your own. Changes work at once."""

from gi.repository import Adw, Gdk, GLib, Gtk

from .. import shortcuts as sk
from ..common import Page, group, icon_button, text_button, widgets_changed

MODS = {"Super_L", "Super_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Shift_L", "Shift_R",
        "Meta_L", "Meta_R", "ISO_Level3_Shift", "Hyper_L", "Hyper_R"}


def keys_from_event(keyval, state):
    """sxhkd keys ("super + shift + q") for a key press, or None for a modifier alone."""
    name = Gdk.keyval_name(Gdk.keyval_to_lower(keyval)) or ""
    if not name or name in MODS:
        return None
    mods = []
    if state & Gdk.ModifierType.SUPER_MASK:
        mods.append("super")
    if state & Gdk.ModifierType.CONTROL_MASK:
        mods.append("ctrl")
    if state & Gdk.ModifierType.ALT_MASK:
        mods.append("alt")
    if state & Gdk.ModifierType.SHIFT_MASK:
        mods.append("shift")
    return " + ".join(mods + [name])


class KeyRecorder(Adw.Dialog):
    """"Press the new keys": catches one key combination (sxhkd paused meanwhile)."""

    def __init__(self, title, done):
        super().__init__(title=title, content_width=420)
        self.done, self.keys = done, None
        view = Adw.ToolbarView()
        head = Adw.HeaderBar(show_end_title_buttons=False, show_start_title_buttons=False)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: self.close())
        self.save = Gtk.Button(label="Use these keys", sensitive=False)
        self.save.add_css_class("suggested-action")
        self.save.connect("clicked", lambda *_: (self.close(), self.done(self.keys)))
        head.pack_start(cancel)
        head.pack_end(self.save)
        view.add_top_bar(head)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=24, margin_bottom=28,
                      margin_start=24, margin_end=24)
        self.big = Gtk.Label(label="Press the keys…")
        self.big.add_css_class("title-1")
        hint = Gtk.Label(label="Hold Super, Ctrl, Alt or Shift and press a key. Your other shortcuts are paused "
                               "while this is open.", wrap=True, justify=Gtk.Justification.CENTER)
        hint.add_css_class("dim-label")
        self.warn = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER, visible=False)
        self.warn.add_css_class("warning")
        box.append(self.big)
        box.append(hint)
        box.append(self.warn)
        view.set_content(box)
        self.set_child(view)
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._pressed)
        self.add_controller(keys)
        self.connect("closed", lambda *_: sk.resume())
        sk.pause()
        self.used = {}
        for sc in sk.load():
            if sc.on:
                for c in sc.combos():
                    self.used.setdefault(c, sc.title())

    def _pressed(self, _c, keyval, _code, state):
        keys = keys_from_event(keyval, state)
        if keys is None:
            return True
        self.keys = keys
        self.big.set_label(sk.pretty(keys))
        clash = self.used.get(sk._norm(keys))
        self.warn.set_label(f"Already used by “{clash}”. Using it here too makes a clash." if clash else "")
        self.warn.set_visible(bool(clash))
        self.save.set_sensitive(True)
        return True


class ShortcutsPage(Page):
    name = "shortcuts"
    title = "Shortcuts"
    icon = "preferences-desktop-keyboard-shortcuts-symbolic"
    interval = 0

    def __init__(self, window):
        super().__init__(window)
        top = group(self, description="What each key combination does. Changes work at once. "
                                       "Shortcuts with several keys at once (like Super + 1…9) can be turned off "
                                       "but not changed here.")
        row = Adw.ActionRow(title="Your own shortcut", subtitle="Any keys, any command")
        row.add_prefix(Gtk.Image.new_from_icon_name("list-add-symbolic"))
        row.add_suffix(text_button("Add…", self._add, css=["suggested-action"]))
        top.add(row)
        self.reset_row = Adw.ActionRow(title="Reset shortcuts", subtitle="Back to how they were before any change here")
        self.reset_row.add_suffix(text_button("Reset…", self._reset))
        top.add(self.reset_row)
        self.groups = []
        self.key = None
        self.refresh()

    def refresh(self):
        items = sk.load()
        key = repr([(s.keys, s.on, s.desc, s.command) for s in items])
        self.reset_row.set_visible(sk.has_original())
        if key == self.key:
            return
        self.key = key
        for g in self.groups:
            self.remove(g)
        self.groups.clear()
        clash = sk.clashes(items)
        if clash:
            g = group(self, "Clashes", "These keys do more than one thing; usually only one of them works.")
            for combo, scs in clash.items():
                r = Adw.ActionRow(title=GLib.markup_escape_text(sk.pretty(combo.replace("+", " + "))),
                                  subtitle=GLib.markup_escape_text(" · ".join(dict.fromkeys(s.title() for s in scs))))
                r.set_subtitle_lines(3)
                icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
                icon.add_css_class("warning")
                r.add_prefix(icon)
                g.add(r)
            self.groups.append(g)
        sections = {}
        for sc in items:
            sections.setdefault(sc.section or "General", []).append(sc)
        for name, scs in sections.items():
            g = group(self, name)
            for sc in scs:
                g.add(self._row(sc))
            self.groups.append(g)
        widgets_changed()

    def _row(self, sc):
        keys = " · ".join(dict.fromkeys(sc.pretty_keys()))
        r = Adw.ActionRow(title=GLib.markup_escape_text(sc.title()),
                          subtitle=GLib.markup_escape_text(keys + ("" if sc.on else "  (off)")))
        r.set_subtitle_lines(2)
        r.set_tooltip_text(sc.command.strip())
        if sc.simple:
            r.add_suffix(icon_button("document-edit-symbolic", "Change the keys", lambda sc=sc: self._change(sc)))
        if sc.mine:
            r.add_suffix(icon_button("user-trash-symbolic", "Remove this shortcut", lambda sc=sc: self._remove(sc)))
        sw = Gtk.Switch(active=sc.on, valign=Gtk.Align.CENTER, tooltip_text="On or off")
        sw.connect("notify::active", lambda s, _p, sc=sc: s.get_active() != sc.on and self._toggle(sc, s.get_active()))
        r.add_suffix(sw)
        if not sc.on:
            r.add_css_class("dim-label")
        return r

    # ----- changes -----

    def _done(self, text):
        self.key = None
        self.refresh()
        self.toast(text)

    def _toggle(self, sc, on):
        try:
            sk.set_on(sc, on)
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
            return
        GLib.idle_add(lambda: (self._done(f"{sc.title()}: {'on' if on else 'off'}"), False)[1])

    def _change(self, sc):
        def got(keys):
            try:
                sk.set_keys(sc, keys)
            except OSError as e:
                self.toast(f"Couldn't save: {e.strerror}")
                return
            self._done(f"{sc.title()}: {sk.pretty(keys)}")
        KeyRecorder(f"Keys for “{sc.title()}”", got).present(self.window)

    def _remove(self, sc):
        try:
            sk.remove(sc)
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
            return
        self._done(f"Removed {sc.title()}")

    def _add(self):
        d = Adw.AlertDialog(heading="Your own shortcut", body="What it's called, its keys and the command it runs.")
        box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        box.add_css_class("boxed-list")
        name = Adw.EntryRow(title="Name (e.g. Open Firefox)")
        cmd = Adw.EntryRow(title="Command (e.g. firefox)")
        keys_row = Adw.ActionRow(title="Keys", subtitle="Not set")
        state = {"keys": None}

        def got(keys):
            state["keys"] = keys
            keys_row.set_subtitle(sk.pretty(keys))
            ok()
        keys_row.add_suffix(text_button("Set…", lambda: KeyRecorder("Keys for your shortcut", got).present(self.window)))
        for w in (name, keys_row, cmd):
            box.append(w)
        d.set_extra_child(box)
        d.add_response("cancel", "Cancel")
        d.add_response("add", "Add")
        d.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)
        d.set_response_enabled("add", False)

        def ok(*_):
            d.set_response_enabled("add", bool(name.get_text().strip() and cmd.get_text().strip() and state["keys"]))
        name.connect("changed", ok)
        cmd.connect("changed", ok)

        def answered(_d, r):
            if r != "add":
                return
            try:
                sk.add(name.get_text().strip(), state["keys"], cmd.get_text().strip())
            except OSError as e:
                self.toast(f"Couldn't save: {e.strerror}")
                return
            self._done(f"Added {name.get_text().strip()}")
        d.connect("response", answered)
        d.set_close_response("cancel")
        d.present(self.window)

    def _reset(self):
        d = Adw.AlertDialog(heading="Reset shortcuts?", body="All changes made here are undone, including shortcuts you added.")
        d.add_response("cancel", "Cancel")
        d.add_response("reset", "Reset")
        d.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        d.connect("response", lambda _d, r: r == "reset" and (sk.reset(), self._done("Shortcuts are reset")))
        d.present(self.window)
