"""Colour and font pickers shown inside the window.

GTK's own ColorDialog/FontDialog open separate windows, and with bspwm's
focus-follows-mouse those can stop taking clicks. These open as dialogs
inside the Control Center window instead."""

import warnings

from gi.repository import Adw, Gdk, Gtk, Pango

warnings.filterwarnings("ignore", category=DeprecationWarning)   # Gtk.ColorChooserWidget / FontChooserWidget


def _dialog(window, title, content, on_select, width=420, height=-1):
    d = Adw.Dialog(title=title, content_width=width, content_height=height)
    header = Adw.HeaderBar(show_end_title_buttons=False, show_start_title_buttons=False)
    cancel = Gtk.Button(label="Cancel")
    cancel.connect("clicked", lambda *_: d.close())
    select = Gtk.Button(label="Select")
    select.add_css_class("suggested-action")

    def chosen(*_):
        on_select()
        d.close()
    select.connect("clicked", chosen)
    header.pack_start(cancel)
    header.pack_end(select)
    view = Adw.ToolbarView(content=content)
    view.add_top_bar(header)
    d.set_child(view)
    d.set_default_widget(select)
    d.present(window)


class ColorButton(Gtk.Button):
    """A swatch of the colour; clicking it opens the picker.
    Emits nothing itself: on_change(hex) is called with '#RRGGBB'."""

    def __init__(self, title, on_change):
        super().__init__(valign=Gtk.Align.CENTER, tooltip_text="Choose a colour")
        self.title = title
        self.on_change = on_change
        self.rgba = Gdk.RGBA()
        self.rgba.parse("#000000")
        self.swatch = Gtk.DrawingArea(content_width=34, content_height=20)
        self.swatch.set_draw_func(self._draw)
        self.set_child(self.swatch)
        self.connect("clicked", self._open)

    def _draw(self, _area, cr, w, h):
        r = 5
        cr.new_sub_path()
        for (x, y, a) in ((w - r, r, -90), (w - r, h - r, 0), (r, h - r, 90), (r, r, 180)):
            cr.arc(x, y, r, a * 3.14159 / 180, (a + 90) * 3.14159 / 180)
        cr.close_path()
        Gdk.cairo_set_source_rgba(cr, self.rgba)
        cr.fill_preserve()
        cr.set_source_rgba(0.5, 0.5, 0.5, 0.45)
        cr.set_line_width(1)
        cr.stroke()

    def set_hex(self, value):
        c = Gdk.RGBA()
        if c.parse(value):
            self.rgba = c
            self.swatch.queue_draw()

    def _open(self, *_):
        chooser = Gtk.ColorChooserWidget(use_alpha=False, margin_top=12, margin_bottom=12,
                                         margin_start=12, margin_end=12)
        chooser.set_rgba(self.rgba)

        def select():
            c = chooser.get_rgba()
            self.rgba = c
            self.swatch.queue_draw()
            self.on_change("#%02X%02X%02X" % (round(c.red * 255), round(c.green * 255), round(c.blue * 255)))
        _dialog(self.get_root(), self.title, chooser, select)


class FontButton(Gtk.Button):
    """Shows the font's name in that font; clicking it opens the picker.
    family_only: pick a family (no size). on_change(Pango.FontDescription)."""

    def __init__(self, title, on_change, family_only=False, monospace=False):
        super().__init__(valign=Gtk.Align.CENTER, tooltip_text="Choose a font")
        self.title = title
        self.on_change = on_change
        self.family_only = family_only
        self.monospace = monospace
        self.desc = Pango.FontDescription.from_string("Sans 10")
        self.label = Gtk.Label(ellipsize=3, max_width_chars=22)
        self.set_child(self.label)
        self.connect("clicked", self._open)

    def set_desc(self, desc):
        self.desc = desc
        size = desc.get_size() / Pango.SCALE if desc.get_size() else 0
        text = desc.get_family() or "Sans"
        if not self.family_only and size:
            text += f"  {size:g}"
        self.label.set_label(text)
        show = Pango.FontDescription.from_string(desc.get_family() or "Sans")
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_font_desc_new(show))
        self.label.set_attributes(attrs)

    def _open(self, *_):
        chooser = Gtk.FontChooserWidget(margin_top=6, margin_bottom=6, margin_start=6, margin_end=6,
                                        vexpand=True)
        chooser.set_level(Gtk.FontChooserLevel.FAMILY if self.family_only
                          else Gtk.FontChooserLevel.FAMILY | Gtk.FontChooserLevel.STYLE | Gtk.FontChooserLevel.SIZE)
        if self.monospace:
            chooser.set_filter_func(lambda family, _face: family.is_monospace())
        chooser.set_font_desc(self.desc)

        def select():
            desc = chooser.get_font_desc()
            if desc:
                self.set_desc(desc)
                self.on_change(desc)
        _dialog(self.get_root(), self.title, chooser, select, width=460, height=560)
