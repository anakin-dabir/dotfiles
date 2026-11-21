"""Shortcuts: one row per thing a key combination does, its keys as key caps.
Click a row to change its keys, turn it off or put it back. Changes work
at once (config/sxhkdrc; sxhkd reloads)."""

from gi.repository import Adw, Gdk, GLib, Gtk

from .. import shortcuts as sk
from ..common import Page, group, text_button, widgets_changed

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


def caps(text, dim=False):
    """Key caps for "Super + Alt + Q" (", then " and "…" kept as words)."""
    box = Gtk.Box(spacing=4, valign=Gtk.Align.CENTER)
    for i, step in enumerate(text.split(", then ")):
        if i:
            w = Gtk.Label(label="then")
            w.add_css_class("dim-label")
            box.append(w)
        for key in step.split(" + "):
            lab = Gtk.Label(label=key)
            lab.add_css_class("dim-label" if key == "…" else "cc-kbd")
            box.append(lab)
    if dim:
        box.set_opacity(0.45)
    return box


class ShortcutDialog(Adw.Dialog):
    """One shortcut: press new keys, turn it off/on, back to its first keys."""

    def __init__(self, page, action, clash):
        super().__init__(title=action.name, content_width=460)
        self.page, self.a, self.keys = page, action, None
        view = Adw.ToolbarView()
        head = Adw.HeaderBar(show_end_title_buttons=False, show_start_title_buttons=False)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: self.close())
        head.pack_start(cancel)
        self.save = Gtk.Button(label="Save", sensitive=False)
        self.save.add_css_class("suggested-action")
        self.save.connect("clicked", lambda *_: self._save())
        if not action.is_set:
            head.pack_end(self.save)
        view.add_top_bar(head)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin_top=18, margin_bottom=22,
                      margin_start=22, margin_end=22)
        self.shown = Gtk.Box(halign=Gtk.Align.CENTER)
        self._show(" · ".join(action.caps()) if action.is_set else action.caps()[0])
        box.append(self.shown)
        if action.is_set:
            text = "A set of keys, like " + ", ".join(sk.pretty(k) for k in action.all_keys[:4]) + \
                   "… It can be turned off here, but not changed."
        else:
            text = "Press the new keys now (hold Super, Ctrl, Alt or Shift and press a key). " \
                   "Your other shortcuts are paused while this is open."
        hint = Gtk.Label(label=text, wrap=True, justify=Gtk.Justification.CENTER)
        hint.add_css_class("dim-label")
        box.append(hint)
        self.warn = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self.warn.add_css_class("warning")
        self.warn.set_visible(bool(clash))
        if clash:
            self.warn.set_label("Also used by: " + ", ".join(sorted(clash)))
        box.append(self.warn)

        btns = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, margin_top=4)
        onoff = Gtk.Button(label="Turn off" if action.on else "Turn on")
        onoff.connect("clicked", lambda *_: (self.close(), self.page._on(action, not action.on)))
        btns.append(onoff)
        self.default = None if action.is_set else sk.default_keys(action)
        if self.default:
            back = Gtk.Button(label=f"Back to {sk.pretty(self.default)}")
            back.connect("clicked", lambda *_: (self.close(), self.page._change(action, self.default)))
            btns.append(back)
        box.append(btns)
        view.set_content(box)
        self.set_child(view)

        if not action.is_set:
            keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
            keys.connect("key-pressed", self._pressed)
            self.add_controller(keys)
            self.connect("closed", lambda *_: sk.resume())
            sk.pause()
            self.used = {}
            for b in sk.actions():
                if b.on and b is not action and b.command != action.command:
                    for c in b.combos():
                        self.used.setdefault(c, b.name)

    def _show(self, text):
        while (c := self.shown.get_first_child()) is not None:
            self.shown.remove(c)
        c = caps(text)
        c.add_css_class("cc-kbd-big")
        self.shown.append(c)

    def _pressed(self, _c, keyval, _code, state):
        keys = keys_from_event(keyval, state)
        if keys is None:
            return True
        self.keys = keys
        self._show(sk.pretty(keys))
        clash = self.used.get(sk._norm(keys))
        self.warn.set_label(f"Already used by “{clash}”" if clash else "")
        self.warn.set_visible(bool(clash))
        self.save.set_sensitive(True)
        return True

    def _save(self):
        self.close()
        if self.keys:
            self.page._change(self.a, self.keys)


class ShortcutsPage(Page):
    name = "shortcuts"
    title = "Shortcuts"
    icon = "preferences-desktop-keyboard-shortcuts-symbolic"
    interval = 0

    def __init__(self, window):
        super().__init__(window)
        top = group(self)
        self.search = Gtk.SearchEntry(placeholder_text="Search shortcuts (window, screenshot, volume…)")
        self.search.connect("search-changed", lambda *_: self._filter())
        top.add(self.search)
        self.notice = group(self)
        self.groups = []
        self.rows = []
        self.key = None
        bottom = group(self, "More")
        add = Adw.ActionRow(title="Add your own shortcut", subtitle="Any keys, any command", activatable=True)
        add.add_prefix(Gtk.Image.new_from_icon_name("list-add-symbolic"))
        add.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        add.connect("activated", lambda *_: self._add())
        bottom.add(add)
        self.reset_row = Adw.ActionRow(title="Reset all shortcuts", subtitle="Back to how they were before any change here")
        self.reset_row.add_suffix(text_button("Reset…", self._reset))
        bottom.add(self.reset_row)
        self.bottom = bottom
        self.refresh()

    # ----- rows -----

    def refresh(self):
        acts = sk.actions()
        key = repr([(a.name, a.keys, a.on, a.all_keys) for a in acts])
        self.reset_row.set_visible(sk.has_original())
        if key == self.key:
            return
        self.key = key
        for g in self.groups:
            self.remove(g)
        self.groups.clear()
        self.rows.clear()
        clash = sk.action_clashes(acts)
        self.notice.set_visible(bool(clash))
        self.notice.set_description("⚠ Some keys do two things; usually only one of them works. "
                                    "They're marked below." if clash else "")
        by = {}
        for a in acts:
            by.setdefault(a.group, []).append(a)
        self.remove(self.bottom)
        for name in sk.GROUP_ORDER:
            if name not in by:
                continue
            g = group(self, name)
            for a in by[name]:
                r = self._row(a, clash.get(id(a)))
                g.add(r)
                self.rows.append((g, r, a))
            self.groups.append(g)
        self.add(self.bottom)
        self._filter()
        widgets_changed()

    def _row(self, a, clash):
        r = Adw.ActionRow(title=GLib.markup_escape_text(a.name), activatable=True)
        r.set_tooltip_text(a.command.strip())
        if clash:
            w = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
            w.add_css_class("warning")
            w.set_tooltip_text("Also used by: " + ", ".join(sorted(clash)))
            r.add_prefix(w)
            r.set_subtitle(GLib.markup_escape_text("Same keys as: " + ", ".join(sorted(clash))))
        if not a.on:
            off = Gtk.Label(label="Off")
            off.add_css_class("dim-label")
            r.add_suffix(off)
        r.add_suffix(caps(" · ".join(a.caps()) if a.is_set else a.caps()[0], dim=not a.on))
        r.connect("activated", lambda *_: ShortcutDialog(self, a, clash).present(self.window))
        return r

    def _filter(self):
        words = self.search.get_text().lower().split()
        shown = {}
        for g, r, a in self.rows:
            text = (a.name + " " + " ".join(a.caps()) + " " + a.group).lower()
            ok = all(w in text for w in words)
            r.set_visible(ok)
            shown[g] = shown.get(g, False) or ok
        for g, ok in shown.items():
            g.set_visible(ok)

    # ----- changes -----

    def _done(self, text):
        self.key = None
        self.refresh()
        self.toast(text)

    def _change(self, a, keys):
        try:
            sk.change_action(a, keys)
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
            return
        self._done(f"{a.name}: {sk.pretty(keys)}")

    def _on(self, a, on):
        try:
            sk.action_on(a, on)
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
            return
        self._done(f"{a.name}: {'on' if on else 'off'}")

    def _add(self):
        d = Adw.AlertDialog(heading="Your own shortcut", body="What it's called, its keys and the command it runs.")
        box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        box.add_css_class("boxed-list")
        name = Adw.EntryRow(title="Name (e.g. Open Firefox)")
        cmd = Adw.EntryRow(title="Command (e.g. firefox)")
        keys_row = Adw.ActionRow(title="Keys", subtitle="Not set")
        state = {"keys": None}

        def ok(*_):
            d.set_response_enabled("add", bool(name.get_text().strip() and cmd.get_text().strip() and state["keys"]))

        def record():
            rec = sk.Action(sk.Shortcut(), "", "", "Your shortcut", "")
            dlg = ShortcutDialog(self, rec, None)
            dlg._save = lambda: (dlg.close(), got(dlg.keys))
            dlg.present(self.window)

        def got(keys):
            if keys:
                state["keys"] = keys
                keys_row.set_subtitle(sk.pretty(keys))
                ok()
        keys_row.add_suffix(text_button("Set…", record))
        for w in (name, keys_row, cmd):
            box.append(w)
        d.set_extra_child(box)
        d.add_response("cancel", "Cancel")
        d.add_response("add", "Add")
        d.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)
        d.set_response_enabled("add", False)
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
        d = Adw.AlertDialog(heading="Reset all shortcuts?", body="Every change made here is undone, "
                                                                 "including shortcuts you added.")
        d.add_response("cancel", "Cancel")
        d.add_response("reset", "Reset")
        d.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        d.connect("response", lambda _d, r: r == "reset" and (sk.reset(), self._done("Shortcuts are reset")))
        d.present(self.window)
