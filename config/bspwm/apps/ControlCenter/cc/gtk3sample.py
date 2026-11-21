#!/usr/bin/env python3
"""Draw a small sample window with a GTK3 theme into a PNG, without showing
anything on screen. Run with the theme in GTK_THEME:

    GTK_THEME=WhiteSur-Dark python3 gtk3sample.py out.png
"""

import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402


def sample():
    win = Gtk.OffscreenWindow()
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.get_style_context().add_class("background")

    header = Gtk.HeaderBar(title="Files", subtitle="Home", show_close_button=True)
    back = Gtk.Button.new_from_icon_name("go-previous-symbolic", Gtk.IconSize.BUTTON)
    header.pack_start(back)
    menu = Gtk.Button.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON)
    header.pack_end(menu)
    outer.pack_start(header, False, False, 0)

    body = Gtk.Grid(column_spacing=12, row_spacing=10, margin=14)
    entry = Gtk.Entry(text="Search files", hexpand=True)
    body.attach(entry, 0, 0, 2, 1)

    normal = Gtk.Button(label="Cancel")
    suggested = Gtk.Button(label="Open")
    suggested.get_style_context().add_class("suggested-action")
    buttons = Gtk.Box(spacing=8)
    buttons.pack_start(normal, False, False, 0)
    buttons.pack_start(suggested, False, False, 0)
    body.attach(buttons, 0, 1, 1, 1)

    toggles = Gtk.Box(spacing=12, halign=Gtk.Align.END)
    check = Gtk.CheckButton(label="Hidden files", active=True)
    switch = Gtk.Switch(active=True, valign=Gtk.Align.CENTER)
    toggles.pack_start(check, False, False, 0)
    toggles.pack_start(switch, False, False, 0)
    body.attach(toggles, 1, 1, 1, 1)

    scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
    scale.set_value(60)
    scale.set_draw_value(False)
    body.attach(scale, 0, 2, 1, 1)
    progress = Gtk.ProgressBar(fraction=0.4, valign=Gtk.Align.CENTER)
    body.attach(progress, 1, 2, 1, 1)

    tabs = Gtk.Notebook()
    for name in ("Recent", "Starred", "Trash"):
        page = Gtk.Label(label="", margin=4)
        tabs.append_page(page, Gtk.Label(label=name))
    body.attach(tabs, 0, 3, 2, 1)

    outer.pack_start(body, True, True, 0)
    win.add(outer)
    win.set_size_request(440, -1)
    return win


def main(out):
    win = sample()
    win.show_all()

    def save():
        pix = win.get_pixbuf()
        if pix is not None:
            pix.savev(out, "png", [], [])
        Gtk.main_quit()
        return False
    GLib.timeout_add(250, save)          # let it lay out and draw first
    GLib.timeout_add(5000, Gtk.main_quit)
    Gtk.main()


if __name__ == "__main__":
    main(sys.argv[1])
