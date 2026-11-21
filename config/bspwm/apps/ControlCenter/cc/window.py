"""Main window: a sidebar of sections and the selected section's page."""

import gi

gi.require_version("Graphene", "1.0")
from gi.repository import Adw, GLib, Graphene, Gtk  # noqa: E402

from .common import set_pointer_root, widgets_changed
from .pages.about import AboutPage
from .pages.appearance import AppearancePage
from .pages.bar import BarPage
from .pages.bluetooth import BluetoothPage
from .pages.customize import CustomizePage
from .pages.display import DisplayPage
from .pages.dropdowns import DropdownsPage
from .pages.network import NetworkPage
from .pages.notifications import NotificationsPage
from .pages.power import PowerPage
from .pages.sound import SoundPage

PAGES = [AppearancePage, CustomizePage, BarPage, DropdownsPage, DisplayPage, SoundPage, NetworkPage,
         BluetoothPage, PowerPage, NotificationsPage, AboutPage]


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
        # (no animation: sliding moved the whole page for a quarter second)
        self.sticky = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.NONE)
        self.sticky.add_css_class("cc-sticky")
        content_view.add_top_bar(self.sticky)
        self.sticky_toggle = Gtk.ToggleButton(icon_name="view-reveal-symbolic", active=True,
                                              tooltip_text="Show or hide the preview")
        self.sticky_toggle.connect("toggled", lambda *_: self._show_sticky())
        header.pack_end(self.sticky_toggle)
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
            box.append(Gtk.Label(label=p.title, xalign=0))
            row = Gtk.ListBoxRow(child=box)
            row.page = p
            self.list.append(row)
        self.list.connect("row-selected", self._selected)
        side_view = Adw.ToolbarView()
        side_view.add_top_bar(Adw.HeaderBar(show_title=True))
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


    def _show_sticky(self):
        page = self.page
        has = page is not None and getattr(page, "sticky_widget", None) is not None
        self.sticky_toggle.set_visible(has)
        self.sticky.set_reveal_child(has and self.sticky_toggle.get_active())

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
        self.stack.set_visible_child(page)
        self.content.set_title(page.title)
        self.heading.set_title(page.title)
        widget = getattr(page, "sticky_widget", None)
        if widget is not None and self.sticky.get_child() is not widget:
            self.sticky.set_child(widget)
        self._show_sticky()
        self.split.set_show_content(True)
        page.refresh()
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
