"""Shared helpers: paths, running commands without freezing the window,
thumbnails, and the base class for pages."""

import hashlib
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

HOME = os.path.expanduser("~")
BSPDIR = os.path.join(HOME, ".config", "bspwm")
BIN = os.path.join(BSPDIR, "bin")
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.join(HOME, ".cache")), "control-center")


# ----- pointer cursor on everything clickable -----

_CLICKABLE = (Gtk.Button, Gtk.Switch, Gtk.Scale, Gtk.CheckButton, Gtk.DropDown, Gtk.MenuButton)
_pointer_hook = {"fn": None, "id": 0}


def pointers(root):
    """Give every clickable widget under root the hand cursor."""
    todo = [root]
    while todo:
        w = todo.pop()
        clickable = isinstance(w, _CLICKABLE) or (isinstance(w, Gtk.ListBoxRow) and w.get_activatable()
                                                  and w.get_sensitive())
        if clickable and w.get_cursor() is None:
            w.set_cursor_from_name("pointer")
        c = w.get_first_child()
        while c is not None:
            todo.append(c)
            c = c.get_next_sibling()


def set_pointer_root(fn):
    """fn() returns the widget tree to update (the app window)."""
    _pointer_hook["fn"] = fn


def widgets_changed():
    """Call after adding widgets (rows, dialogs): cursors are set once things settle."""
    if _pointer_hook["fn"] and not _pointer_hook["id"]:
        def go():
            _pointer_hook["id"] = 0
            root = _pointer_hook["fn"]()
            if root is not None:
                pointers(root)
            return False
        _pointer_hook["id"] = GLib.timeout_add(50, go)


def tool(name):
    """Full path of one of the rice's scripts (bspwm/bin)."""
    return os.path.join(BIN, name)


def have(program):
    return GLib.find_program_in_path(program) is not None


def run(argv, done=None, stdin=None):
    """Run a command in the background and call done(ok, stdout, stderr).

    Only for commands that exit by themselves and don't leave anything
    running (their output is read until it closes)."""
    flags = Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
    if stdin is not None:
        flags |= Gio.SubprocessFlags.STDIN_PIPE
    try:
        proc = Gio.Subprocess.new([str(a) for a in argv], flags)
    except GLib.Error as e:
        if done:
            done(False, "", e.message)
        return

    def finished(p, result):
        try:
            _, out, err = p.communicate_utf8_finish(result)
        except GLib.Error as e:
            out, err = "", e.message
        if done:
            done(p.get_successful(), out or "", err or "")
        widgets_changed()

    proc.communicate_utf8_async(stdin, None, finished)


def run_quiet(argv, done=None):
    """Run a command whose output we don't need, e.g. one that starts
    programs that keep running (theme switch, bar restart). done(ok)."""
    flags = Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE
    try:
        proc = Gio.Subprocess.new([str(a) for a in argv], flags)
    except GLib.Error:
        if done:
            done(False)
        return

    def finished(p, result):
        try:
            p.wait_finish(result)
        except GLib.Error:
            pass
        if done:
            done(p.get_successful())
        widgets_changed()

    proc.wait_async(None, finished)


def run_json(argv, done):
    """Run a command that prints JSON; done(data or None)."""
    def parsed(ok, out, _err):
        try:
            done(json.loads(out) if out.strip() else None)
        except ValueError:
            done(None)
    run(argv, parsed)


def launch(argv):
    """Start an app and forget about it (it keeps running after we close)."""
    subprocess.Popen([str(a) for a in argv], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def read_file(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def current_rice():
    return read_file(os.path.join(BSPDIR, ".rice"))


# ----- thumbnails -----

_pool = ThreadPoolExecutor(max_workers=3)


def thumbnail(path, width, height, done):
    """Scale and crop an image to width x height (cached on disk), in a
    background thread; done(Gdk.Texture or None) runs in the main thread."""
    try:
        st = os.stat(path)
    except OSError:
        done(None)
        return
    key = hashlib.sha1(f"{path}:{st.st_mtime_ns}:{st.st_size}:{width}x{height}".encode()).hexdigest()
    cached = os.path.join(CACHE, "thumbs", key + ".png")

    def work():
        try:
            if os.path.exists(cached):
                return Gdk.Texture.new_from_filename(cached)
            pix = GdkPixbuf.Pixbuf.new_from_file(path)
            w, h = pix.get_width(), pix.get_height()
            scale = max(width / w, height / h)
            sw, sh = max(1, round(w * scale)), max(1, round(h * scale))
            pix = pix.scale_simple(sw, sh, GdkPixbuf.InterpType.BILINEAR)
            pix = pix.new_subpixbuf((sw - width) // 2, (sh - height) // 2, width, height).copy()
            os.makedirs(os.path.dirname(cached), exist_ok=True)
            pix.savev(cached, "png", [], [])
            return Gdk.Texture.new_from_filename(cached)
        except (GLib.Error, OSError, ValueError):
            return None

    future = _pool.submit(work)
    future.add_done_callback(lambda f: GLib.idle_add(lambda: (done(f.result()), widgets_changed(), False)[2]))


# ----- pages -----

class Page(Adw.PreferencesPage):
    """One section of the app. refresh() is called when the page is shown
    and then every `interval` seconds while it stays on screen."""

    name = ""
    title = ""
    icon = ""
    interval = 0

    def __init__(self, window):
        super().__init__()
        self.window = window
        self._updating = False   # set while refresh() moves switches/sliders

    def refresh(self):
        pass

    def toast(self, text):
        self.window.toast(text)

    # Widgets changed by refresh() shouldn't fire their "user changed it" handlers
    def quietly(self, fn):
        self._updating = True
        try:
            fn()
        finally:
            self._updating = False


def group(page, title="", description=""):
    g = Adw.PreferencesGroup(title=title, description=description)
    page.add(g)
    return g


def slider(lo, hi, step=1):
    s = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, step)
    s.set_hexpand(True)
    s.set_draw_value(False)
    s.set_valign(Gtk.Align.CENTER)
    return s


def slider_row(title, icon, lo, hi, on_change, step=1, unit="%"):
    """Row with an icon, a slider and its value. on_change(value) is called
    (at most every 60 ms) while dragging."""
    row = Adw.ActionRow(title=title)
    if icon:
        row.add_prefix(Gtk.Image.new_from_icon_name(icon))
    s = slider(lo, hi, step)
    s.set_size_request(220, -1)
    value = Gtk.Label(width_chars=5, xalign=1)
    value.add_css_class("dim-label")
    value.add_css_class("numeric")
    row.add_suffix(s)
    row.add_suffix(value)
    pending = {"id": 0}

    def changed(scale):
        value.set_label(f"{round(scale.get_value())}{unit}")
        if getattr(row, "_quiet", False):
            return
        if pending["id"]:
            return

        def fire():
            pending["id"] = 0
            on_change(round(scale.get_value()))
            return False
        pending["id"] = GLib.timeout_add(60, fire)

    s.connect("value-changed", changed)

    def set_value(v):
        if s.get_state_flags() & Gtk.StateFlags.ACTIVE:   # don't fight the user's drag
            return
        row._quiet = True
        s.set_value(v)
        value.set_label(f"{round(v)}{unit}")
        row._quiet = False

    row.set_value = set_value
    row.scale = s
    return row


def icon_button(icon, tooltip, on_click, flat=True):
    b = Gtk.Button(icon_name=icon, tooltip_text=tooltip, valign=Gtk.Align.CENTER)
    if flat:
        b.add_css_class("flat")
    b.connect("clicked", lambda *_: on_click())
    return b


def text_button(label, on_click, css=None):
    b = Gtk.Button(label=label, valign=Gtk.Align.CENTER)
    for c in (css or []):
        b.add_css_class(c)
    b.connect("clicked", lambda *_: on_click())
    return b


def clear(listbox_or_group, rows):
    """Remove previously added rows from a group/list."""
    for r in rows:
        listbox_or_group.remove(r)
    rows.clear()
