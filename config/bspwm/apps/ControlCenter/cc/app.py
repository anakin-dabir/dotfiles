"""Control Center for this bspwm rice.

    ControlCenter [SECTION]   open (or bring to front) at SECTION:
                              appearance customize bar dropdowns display sound
                              network bluetooth keyboard fans power
                              notifications about
"""

import sys

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
        elif section:
            self.window.show_page(section)
        self.window.present()
        return 0


def main():
    GLib.set_prgname("ControlCenter")     # window class, for the bspwm rule
    GLib.set_application_name("Control Center")
    return App().run(sys.argv)
