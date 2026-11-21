"""Dropdowns: choose which sections each bar dropdown shows, and their
order. One dropdown at a time: a live mock of it (made of real pictures of
its sections) next to the list of its sections. Saved right away
(config/dropdowns.json); an open dropdown follows at once."""

import json
import os

from gi.repository import Adw, GdkPixbuf, GLib, Gtk

from .. import ddconfig, ddshots
from ..common import BSPDIR, Page, group, icon_button, launch, run_quiet, widgets_changed

MOCK_W = 262          # width of the mock dropdown's pictures
GAP = 10              # space between its sections


def picture(path, width=MOCK_W):
    """A picture scaled to `width`, or None if it isn't there yet."""
    if not os.path.exists(path):
        return None
    pic = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.CONTAIN)
    info = GdkPixbuf.Pixbuf.get_file_info(path)
    if info and info[0] is not None and info[1] > 0:     # (format, width, height)
        pic.set_size_request(width, round(info[2] * width / info[1]))
    pic.set_filename(path)
    return pic


class DropdownsPage(Page):
    name = "dropdowns"
    title = "Dropdowns"
    icon = "view-list-symbolic"
    interval = 0

    def __init__(self, window):
        super().__init__(window)
        self.shown, self.order = ddconfig.load()
        self.capturing = False
        self.current = ddconfig.DROPDOWNS[0][0]

        top = group(self, description="The panels that open when you click an item on the bar. Pick one, "
                                      "then switch its sections on or off and change their order. Saved right away.")
        self.tabs = Adw.ToggleGroup(homogeneous=True, margin_top=4)
        for dd, title, _units in ddconfig.DROPDOWNS:
            self.tabs.add(Adw.Toggle(name=dd, label=title))
        self.tabs.set_active_name(self.current)
        self.tabs.connect("notify::active-name", self._pick)
        top.add(self.tabs)
        self.status = Adw.ActionRow(title="Preparing previews for this theme…",
                                    subtitle="About 30 seconds, once per theme. You can close this window meanwhile.")
        self.status.add_prefix(Adw.Spinner())
        self.status.set_visible(False)
        top.add(self.status)

        body = group(self)
        row = Gtk.Box(spacing=20)
        # Left: the dropdown as it will look
        self.mock = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=GAP, valign=Gtk.Align.START)
        self.mock.add_css_class("cc-ddmock")
        mock_side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.START)
        cap = Gtk.Label(label="Preview", xalign=0)
        cap.add_css_class("dim-label")
        cap.add_css_class("caption-heading")
        mock_side.append(cap)
        mock_side.append(self.mock)
        row.append(mock_side)
        # Right: its sections
        list_side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True, valign=Gtk.Align.START)
        cap2 = Gtk.Label(label="Sections, top to bottom", xalign=0)
        cap2.add_css_class("dim-label")
        cap2.add_css_class("caption-heading")
        list_side.append(cap2)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.list.add_css_class("boxed-list")
        list_side.append(self.list)
        row.append(list_side)
        body.add(row)
        # Preview and list side by side need more room than the usual
        # column: widen this page's column (it's an Adw.Clamp inside the page)
        todo = [self]
        while todo:
            w = todo.pop()
            if isinstance(w, Adw.Clamp):
                w.set_maximum_size(820)
                w.set_tightening_threshold(700)
                break
            c = w.get_first_child()
            while c is not None:
                todo.append(c)
                c = c.get_next_sibling()

    # ----- showing -----

    def _pick(self, tabs, _p):
        name = tabs.get_active_name()
        if name:
            self.current = name
            self.build()

    def _units(self):
        """[(section, card or None, can_up, can_down)] top to bottom."""
        units = self.order[self.current]
        out = []
        for i, u in enumerate(units):
            if u in ddconfig.CARDS:
                rows = self.order[u]
                for j, r in enumerate(rows):
                    out.append((r, u, j > 0, j < len(rows) - 1))
            else:
                out.append((u, None, i > 0, i < len(units) - 1))
        return out

    def build(self):
        folder = ddshots.cache_dir()
        units = self._units()

        # The mock: header, then the shown sections in order (a card's
        # rows sit together, like in the real dropdown)
        while (c := self.mock.get_first_child()) is not None:
            self.mock.remove(c)
        head = picture(os.path.join(folder, f"head_{self.current}.png"))
        if head is None:
            wait = Gtk.Label(label="Pictures coming…", margin_top=30, margin_bottom=30, width_request=MOCK_W)
            wait.add_css_class("dim-label")
            self.mock.append(wait)
        else:
            self.mock.append(head)
            card_box, card_of = None, None
            for key, card, _u, _d in units:
                if not self.shown.get(key, True):
                    continue
                pic = picture(os.path.join(folder, key + ".png"))
                if pic is None:
                    continue
                if card:
                    if card != card_of:
                        card_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                        self.mock.append(card_box)
                        card_of = card
                    card_box.append(pic)
                else:
                    card_of = None
                    self.mock.append(pic)

        # The list
        while (r := self.list.get_first_child()) is not None:
            self.list.remove(r)
        for key, card, can_up, can_down in units:
            sub = ""
            if card:
                others = [ddconfig.NAMES[o].split(" (")[0] for o in self.order[card] if o != key]
                sub = "Shares a card with " + " and ".join(others)
            row = Adw.ActionRow(title=ddconfig.NAMES[key], subtitle=sub)
            up = icon_button("go-up-symbolic", "Move up", lambda k=key: self.move(k, -1))
            down = icon_button("go-down-symbolic", "Move down", lambda k=key: self.move(k, 1))
            up.set_sensitive(can_up)
            down.set_sensitive(can_down)
            switch = Gtk.Switch(valign=Gtk.Align.CENTER, active=self.shown.get(key, True))
            switch.connect("notify::active", lambda s, _p, k=key: self.toggle(k, s.get_active()))
            row.add_suffix(up)
            row.add_suffix(down)
            row.add_suffix(switch)
            row.set_activatable_widget(switch)
            self.list.append(row)
        widgets_changed()

    def refresh(self):
        self.shown, self.order = ddconfig.load()
        self.build()
        if not os.path.exists(os.path.join(ddshots.cache_dir(), ".complete")):
            self._capture()

    # ----- changes -----

    def toggle(self, key, on):
        if self.shown.get(key, True) == on:
            return
        self.shown[key] = on
        self._save()
        GLib.idle_add(lambda: (self.build(), False)[1])

    def move(self, key, step):
        # A row inside a card moves within the card; anything else moves
        # among the dropdown's sections (a card moves as one block)
        card = next((c for c, rows in ddconfig.CARDS.items() if key in rows), None)
        lst = self.order[card] if card else self.order[self.current]
        i = lst.index(key)
        j = i + step
        if 0 <= j < len(lst):
            lst[i], lst[j] = lst[j], lst[i]
            self._save()
            self.build()

    def _save(self):
        try:
            data = ddconfig.save(self.shown, self.order)
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
            return
        if not self.capturing:      # an open dropdown follows at once
            run_quiet(["eww", "--no-daemonize", "-c", os.path.join(BSPDIR, "eww"), "update",
                       "bp_show=" + json.dumps(data, separators=(",", ":"))])

    # ----- pictures -----

    def _capture(self):
        """Pictures are taken by a separate process (closing this window
        doesn't stop it); this page shows them as they arrive."""
        if self.capturing:
            return
        if ddshots.dropdown_open():          # don't disturb an open dropdown; try again shortly
            GLib.timeout_add_seconds(3, lambda: (self.window.page is self and self.refresh(), False)[1])
            return
        self.capturing = True
        self.status.set_visible(True)
        launch(["python3", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                        "take-dropdown-pictures.py")])
        folder = ddshots.cache_dir()

        def check():
            done = os.path.exists(os.path.join(folder, ".complete"))
            if self.window.page is self:
                self.build()                  # show the pictures taken so far
            if done:
                self.capturing = False
                self.status.set_visible(False)
                return False
            return True
        GLib.timeout_add_seconds(2, check)
