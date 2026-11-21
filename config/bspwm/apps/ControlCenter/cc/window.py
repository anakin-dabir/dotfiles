"""Main window: a sidebar of sections and the selected section's page."""

from gi.repository import Adw, GLib, Gtk

from .common import set_pointer_root, widgets_changed
from .pages.about import AboutPage
from .pages.appearance import AppearancePage
from .pages.bluetooth import BluetoothPage
from .pages.display import DisplayPage
from .pages.network import NetworkPage
from .pages.notifications import NotificationsPage
from .pages.power import PowerPage
from .pages.sound import SoundPage

PAGES = [AppearancePage, DisplayPage, SoundPage, NetworkPage, BluetoothPage,
         PowerPage, NotificationsPage, AboutPage]


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
        content_view.add_top_bar(Adw.HeaderBar(title_widget=self.heading))
        content_view.set_content(self.toasts)
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
        self.connect("close-request", self._closing)

    # ----- navigation -----

    def show_page(self, name):
        page = self.by_name.get(name) or self.pages[0]
        row = self.list.get_row_at_index(self.pages.index(page))
        self.list.select_row(row)   # -> _selected

    def _selected(self, _list, row):
        if row is None:
            return
        page = row.page
        self.stack.set_visible_child(page)
        self.content.set_title(page.title)
        self.heading.set_title(page.title)
        self.split.set_show_content(True)
        page.refresh()
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
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        return False

    def toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(text), timeout=3))
