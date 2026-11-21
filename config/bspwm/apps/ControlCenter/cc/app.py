"""Control Center for this bspwm rice.

    ControlCenter [SECTION]   open (or bring here) at SECTION:
                              appearance customize bar dropdowns apps display
                              sound network bluetooth shortcuts typing keyboard
                              fans power notifications phones updates about
"""

import subprocess
import sys

import gi

from gi.repository import Adw, Gio, GLib

from .theme import Theme
from .window import Window

APP_ID = "io.github.anakin_dabir.ControlCenter"


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None
        self.theme = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        self.theme = Theme()
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Control>q"])
        close = Gio.SimpleAction.new("close", None)
        close.connect("activate", lambda *_: self.window and self.window.close())
        self.add_action(close)
        self.set_accels_for_action("app.close", ["<Control>w"])   # (not Escape: too easy to lose changes)
        find = Gio.SimpleAction.new("find", None)
        find.connect("activate", lambda *_: self.window and self.window.focus_search())
        self.add_action(find)
        self.set_accels_for_action("app.find", ["<Control>f"])

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        if any(a in ("-h", "--help") for a in args):
            command_line.print_literal(__doc__.strip() + "\n")
            return 0
        section = args[0] if args else None
        if self.window is None:
            self.window = Window(self)
            self.window.connect("destroy", lambda *_: setattr(self, "window", None))
            self.window.show_page(section or "appearance")
        else:
            if section:
                self.window.show_page(section)
            self._to_this_workspace()
        self.window.present()
        return 0

    def _to_this_workspace(self):
        """Already open on another workspace: bring it here (bspwm doesn't on its own)."""
        try:
            gi.require_version("GdkX11", "4.0")
            from gi.repository import GdkX11
            surface = self.window.get_surface()
            if isinstance(surface, GdkX11.X11Surface):
                xid = hex(surface.get_xid())
                subprocess.run(["bspc", "node", xid, "-d", "focused"], timeout=2, check=False)
                subprocess.run(["bspc", "node", xid, "-f"], timeout=2, check=False)
        except (ValueError, ImportError, OSError, subprocess.TimeoutExpired):
            pass


def main():
    GLib.set_prgname("ControlCenter")     # window class, for the bspwm rule
    GLib.set_application_name("Control Center")
    return App().run(sys.argv)
