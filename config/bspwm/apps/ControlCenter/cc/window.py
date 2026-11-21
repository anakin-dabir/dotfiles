"""Main window: a sidebar of sections and the selected section's page."""

import re

import gi

gi.require_version("Graphene", "1.0")
from gi.repository import Adw, GLib, Graphene, Gtk  # noqa: E402

from .common import set_pointer_root, widgets_changed
from .pages.about import AboutPage
from .pages.appearance import AppearancePage
from .pages.apps import AppsPage
from .pages.bar import BarPage
from .pages.bluetooth import BluetoothPage
from .pages.customize import CustomizePage
from .pages.display import DisplayPage
from .pages import fans, keyboard
from .pages.dropdowns import DropdownsPage
from .pages.network import NetworkPage
from .pages.notifications import NotificationsPage
from .pages.phones import PhonesPage
from .pages.power import PowerPage
from .pages.shortcuts import ShortcutsPage
from .pages.sound import SoundPage
from .pages.typing import TypingPage
from .pages.updates import UpdatesPage

PAGES = [AppearancePage, CustomizePage, BarPage, DropdownsPage, AppsPage, DisplayPage, SoundPage, NetworkPage,
         BluetoothPage, ShortcutsPage, TypingPage]
# Hardware pages, only on laptops that have the hardware
PAGES += [P for P, here in ((keyboard.KeyboardPage, keyboard.available()), (fans.FansPage, fans.available())) if here]
PAGES += [PowerPage, NotificationsPage, PhonesPage, UpdatesPage, AboutPage]

# Other words people may search for, besides the names on each page
KEYWORDS = {
    "appearance": "theme rice wallpaper background picture slideshow",
    "customize": "colours colors accent font size border gap corners rounded shadow blur fade "
                 "animations transparency opacity terminal gtk icons cursor picom vsync "
                 "app menu launcher rofi spotlight launchpad",
    "bar": "polybar modules items widgets panel top bar weather city location forecast media music "
           "clipboard screenshot recording",
    "dropdowns": "panels menus processor cpu memory ram storage disk sound network battery",
    "display": "screen brightness night light redshift resolution refresh rate monitor",
    "sound": "audio volume speakers headphones microphone mic output input",
    "network": "wifi wi-fi internet ethernet airplane vpn hidden",
    "bluetooth": "pair devices headphones",
    "keyboard": "backlight rgb lights colour color rainbow breathing",
    "fans": "temperature cooling performance gpu nvidia graphics",
    "power": "battery sleep suspend lock power mode saver performance lid",
    "notifications": "do not disturb dunst popups",
    "about": "system version kernel computer",
    "shortcuts": "keys keybindings hotkeys sxhkd keyboard shortcuts",
    "updates": "upgrade pacman aur yay paru packages system update",
    "typing": "keyboard layout language caps lock key repeat urdu arabic input",
    "phones": "android iphone mtp afc usb phone files photos scrcpy mount",
    "apps": "default browser file manager editor terminal startup autostart login",
}


def _plain(text):
    """For matching: lower case, no dashes or dots ("wifi" finds "Wi-Fi")."""
    return re.sub(r"[-_.·]", "", text.lower()).strip()


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Control Center")
        self.set_default_size(980, 700)
        self.set_size_request(720, 480)
        self.timer = 0

        self.pages = [P(self) for P in PAGES]
        self.by_name = {p.name: p for p in self.pages}

        # Content: header + stack of pages, with toasts on top
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.NONE)
        for p in self.pages:
            self.stack.add_named(p, p.name)
        self.toasts = Adw.ToastOverlay(child=self.stack)
        content_view = Adw.ToolbarView()
        self.heading = Adw.WindowTitle()
        header = Adw.HeaderBar(title_widget=self.heading)
        content_view.add_top_bar(header)
        # A page's preview that stays on screen while its settings scroll
        # (a plain box, shown or hidden at once: an animated strip moved the
        # whole page for a moment, and a revealer kept its space when hidden)
        self.sticky = Gtk.Box()
        self.sticky.add_css_class("cc-sticky")
        content_view.add_top_bar(self.sticky)
        self.sticky_toggle = Gtk.ToggleButton(icon_name="view-reveal-symbolic", active=True,
                                              tooltip_text="Show or hide the preview")
        self.sticky_toggle.connect("toggled", lambda *_: self._show_sticky())
        header.pack_end(self.sticky_toggle)
        # A page's own button(s) at the top right (e.g. Shortcuts' "+")
        self.page_header = Gtk.Box(spacing=6)
        header.pack_end(self.page_header)
        content_view.set_content(self.toasts)

        # "Unsaved changes · Discard · Apply" (pages that collect changes)
        self.pending_label = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)
        discard = Gtk.Button(label="Discard")
        discard.connect("clicked", lambda *_: self.page.discard())
        apply = Gtk.Button(label="Apply")
        apply.add_css_class("suggested-action")
        apply.connect("clicked", lambda *_: self.page.apply())
        bar = Gtk.Box(spacing=8, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
        self.try_btn = Gtk.Button(label="Try It", tooltip_text="Use the changes for a moment, then keep them or go back")
        self.try_btn.connect("clicked", lambda *_: self.page.try_out())
        bar.append(self.pending_label)
        bar.append(discard)
        bar.append(self.try_btn)
        bar.append(apply)
        self.pending_bar = Gtk.Revealer(child=bar, transition_type=Gtk.RevealerTransitionType.SLIDE_UP)
        content_view.add_bottom_bar(self.pending_bar)
        self.content = Adw.NavigationPage(title="", child=content_view)

        # Sidebar
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.add_css_class("navigation-sidebar")
        for p in self.pages:
            box = Gtk.Box(spacing=12, margin_top=2, margin_bottom=2)
            box.append(Gtk.Image.new_from_icon_name(p.icon))
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
            text.append(Gtk.Label(label=p.title, xalign=0))
            hit = Gtk.Label(xalign=0, ellipsize=3, visible=False)
            hit.add_css_class("dim-label")
            hit.add_css_class("caption")
            text.append(hit)
            box.append(text)
            row = Gtk.ListBoxRow(child=box)
            row.page, row.hit_label, row.match = p, hit, None
            self.list.append(row)
        self.list.connect("row-selected", self._selected)
        self.list.connect("row-activated", lambda _l, row: self._go_to_match(row))
        self.list.set_filter_func(self._row_shown)
        nothing = Gtk.Label(label="No settings match", margin_top=24, wrap=True)
        nothing.add_css_class("dim-label")
        self.list.set_placeholder(nothing)

        # Search: every setting's name, not just the page names
        self.query = ""
        self.search = Gtk.SearchEntry(placeholder_text="Search settings", margin_start=8, margin_end=8,
                                      margin_bottom=6)
        self.search.connect("search-changed", self._search_changed)
        self.search.connect("activate", lambda *_: self._open_first())
        self.search.connect("stop-search", lambda e: e.set_text(""))
        self.search.set_key_capture_widget(self)        # typing anywhere starts a search
        side_view = Adw.ToolbarView()
        side_view.add_top_bar(Adw.HeaderBar(show_title=True))
        side_view.add_top_bar(self.search)
        side_view.set_content(Gtk.ScrolledWindow(child=self.list, hscrollbar_policy=Gtk.PolicyType.NEVER))
        sidebar = Adw.NavigationPage(title="Control Center", child=side_view)

        self.split = Adw.NavigationSplitView(sidebar=sidebar, content=self.content)
        self.split.set_min_sidebar_width(210)
        self.set_content(self.split)

        # Narrow window: sidebar and page take turns
        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 640sp"))
        bp.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(bp)

        self.connect("notify::is-active", lambda *_: self._schedule())
        set_pointer_root(lambda: self)
        # Dialogs (password, confirmations) appear inside the window
        self.connect("notify::visible-dialog", lambda *_: widgets_changed())
        self.connect("notify::visible-dialog", self._dialog_shown)
        self.connect("close-request", self._closing)
        dd = self.by_name.get("dropdowns")
        if dd is not None:
            GLib.timeout_add_seconds(3, lambda: (dd.prepare(), False)[1])


    def _show_sticky(self):
        page = self.page
        has = page is not None and getattr(page, "sticky_widget", None) is not None
        self.sticky_toggle.set_visible(has)
        self.sticky.set_visible(has and self.sticky_toggle.get_active())

    def _dialog_shown(self, *_):
        """A click outside an open dialog's card closes it. The dialog covers
        the whole window and gets every click itself, so it listens."""
        d = self.get_visible_dialog()
        if d is None or getattr(d, "_outside_close", False):
            return
        d._outside_close = True
        g = Gtk.GestureClick(button=0)
        g.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        g.connect("pressed", lambda gesture, _n, x, y: self._dialog_click(d, gesture, x, y))
        d.add_controller(g)

    @staticmethod
    def _card(d):
        """The visible card inside a dialog: its biggest part that's smaller
        than the dialog itself (which covers the whole window)."""
        full = d.get_width() * d.get_height()
        best, best_area, todo = None, 0, [d]
        while todo:
            w = todo.pop()
            c = w.get_first_child()
            while c is not None:
                if c.get_mapped():
                    area = c.get_width() * c.get_height()
                    if area < full * 0.95:
                        if area > best_area:
                            best, best_area = c, area
                    else:
                        todo.append(c)
                c = c.get_next_sibling()
        return best

    def _dialog_click(self, d, gesture, x, y):
        card = self._card(d)
        if card is None:
            return
        ok, bounds = card.compute_bounds(d)
        if ok and not bounds.contains_point(Graphene.Point().init(x, y)):
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            d.close()

    # ----- search -----

    def focus_search(self):
        self.split.set_show_content(False)
        self.search.grab_focus()

    @staticmethod
    def _settings_of(page):
        """(name, widget) of each setting on a page: group and row titles."""
        out, todo = [], [page]
        while todo:
            w = todo.pop(0)
            title = None
            if isinstance(w, (Adw.PreferencesGroup, Adw.PreferencesRow)) and w.is_visible():
                title = w.get_title()
            if title:
                out.append((title.replace("&amp;", "&"), w))
            c = w.get_first_child()
            while c is not None:
                todo.append(c)
                c = c.get_next_sibling()
        return out

    def _search_changed(self, entry):
        self.query = _plain(entry.get_text())
        words = self.query.split()
        row = self.list.get_first_child()
        while row is not None:
            if isinstance(row, Gtk.ListBoxRow):
                p = row.page
                row.match, row.shown = None, not words
                if words:
                    if all(w in _plain(p.title + " " + KEYWORDS.get(p.name, "")) for w in words):
                        row.shown = True
                    for name, widget in self._settings_of(p):
                        if all(w in _plain(name) for w in words):
                            row.match, row.shown = (name, widget), True
                            break
                row.hit_label.set_label(row.match[0] if row.match else "")
                row.hit_label.set_visible(row.match is not None and row.match[0] != p.title)
            row = row.get_next_sibling()
        self.list.invalidate_filter()

    @staticmethod
    def _row_shown(row):
        return getattr(row, "shown", True)

    def _open_first(self):
        row = self.list.get_first_child()
        while row is not None and not (isinstance(row, Gtk.ListBoxRow) and row.get_child_visible()):
            row = row.get_next_sibling()
        if row is not None:
            self.list.select_row(row)
            self._go_to_match(row)

    def _go_to_match(self, row):
        """Scroll the page to the setting the search found."""
        if row.match is None:
            return
        widget = row.match[1]

        tries = [20]

        def focus():
            # Scroll so the setting is near the top, then put the focus on it
            sw = widget.get_ancestor(Gtk.ScrolledWindow)
            if sw is not None and sw.get_child() is not None:
                adj = sw.get_vadjustment()
                ok, pt = widget.compute_point(sw.get_child(), Graphene.Point().init(0, 0))
                if (not ok or adj.get_upper() <= 0) and tries[0] > 0:
                    tries[0] -= 1                 # not laid out yet
                    return True
                if ok:
                    adj.set_value(min(max(0, pt.y - 12), adj.get_upper() - adj.get_page_size()))
                    if tries[0] >= 0:            # once more when pictures above it have loaded
                        tries[0] = -1
                        GLib.timeout_add(400, lambda: (focus(), False)[1])
            target = widget
            if isinstance(widget, Adw.PreferencesGroup):       # a heading: its first row
                target = self._first_focusable(widget) or widget
            self.set_focus_visible(True)
            target.grab_focus()
            return False
        GLib.timeout_add(50, focus)            # (once the page has its size)

    @staticmethod
    def _first_focusable(w):
        todo = [w]
        while todo:
            x = todo.pop(0)
            if x is not w and x.get_focusable() and x.is_visible():
                return x
            c = x.get_first_child()
            while c is not None:
                todo.append(c)
                c = c.get_next_sibling()
        return None

    # ----- navigation -----

    def show_page(self, name):
        page = self.by_name.get(name) or self.pages[0]
        row = self.list.get_row_at_index(self.pages.index(page))
        self.list.select_row(row)   # -> _selected

    def _selected(self, _list, row):
        if row is None:
            return
        page = row.page
        if self.page is not None and self.page is not page:
            self.page.leave()
        # Load the page's state before it's on screen: switches then don't
        # slide from their old position and lists don't fill in visibly
        page.refresh()
        self.stack.set_visible_child(page)
        self.content.set_title(page.title)
        self.heading.set_title(page.title)
        widget = getattr(page, "sticky_widget", None)
        current = self.sticky.get_first_child()
        if widget is not None and current is not widget:
            if current is not None:
                self.sticky.remove(current)
            widget.set_hexpand(True)
            self.sticky.append(widget)
        current_head = self.page_header.get_first_child()
        head = getattr(page, "header_widget", None)
        if current_head is not head:
            if current_head is not None:
                self.page_header.remove(current_head)
            if head is not None:
                self.page_header.append(head)
        self._show_sticky()
        self.split.set_show_content(True)
        self.update_pending()
        widgets_changed()
        self._schedule()

    @property
    def page(self):
        return self.stack.get_visible_child()

    # The visible page refreshes itself every few seconds, only while the
    # window is in front (nothing runs when it's in the background)
    def _schedule(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        page = self.page
        if page and page.interval and self.is_active():
            self.timer = GLib.timeout_add_seconds(page.interval, self._tick)

    def _tick(self):
        if self.page and self.is_active():
            self.page.refresh()
            return True
        self.timer = 0
        return False

    def _closing(self, *_):
        if self.page is not None:
            self.page.leave()
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        return False

    def update_pending(self):
        """Show the Discard/Apply bar when the visible page has unsaved changes."""
        if not hasattr(self, "pending_bar"):      # pages load while the window is being built
            return
        text = self.page.pending_text() if self.page else ""
        self.pending_label.set_label(text)
        self.try_btn.set_visible(hasattr(self.page, "try_out"))
        self.pending_bar.set_reveal_child(bool(text))
        widgets_changed()

    def toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(text), timeout=3))
