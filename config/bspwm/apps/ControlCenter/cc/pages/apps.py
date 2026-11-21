"""Apps: the apps your shortcuts open (browser, files, code editor, text
editor, terminal) and the apps that open when you log in."""

import json
import os
import re
import shlex

import gi

from gi.repository import Adw, Gio, GLib, Gtk

from ..common import BSPDIR, Page, group, icon_button, read_file, text_button, widgets_changed

try:
    gi.require_version("GioUnix", "2.0")
    from gi.repository import GioUnix
    DesktopAppInfo = GioUnix.DesktopAppInfo
except (ImportError, ValueError):
    DesktopAppInfo = Gio.DesktopAppInfo

APPS = os.path.join(BSPDIR, "config", "apps.json")
STARTUP = os.path.join(BSPDIR, "config", "startup.json")
TERM = os.path.join(BSPDIR, "config", ".term")

# (key in apps.json, title, what it's for, categories it can be, default command)
KINDS = [
    ("browser", "Web browser", "Super + W", ("WebBrowser",), "google-chrome-stable"),
    ("files", "File manager", "Super + R and the dropdowns' Files buttons", ("FileManager",), "thunar"),
    ("editor", "Code editor", "Super + E", ("IDE", "TextEditor"), "code dash/"),
    ("text_editor", "Text editor", "Quick notes and files", ("TextEditor",), "geany"),
]
TERMINALS = [("alacritty", "Alacritty"), ("kitty", "kitty"), ("st", "St")]   # (what bin/Term knows)


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def command_of(app):
    """The app's command without %U-style placeholders."""
    cmd = app.get_commandline() or app.get_executable() or ""
    return re.sub(r"\s*%[fFuUdDnNickvm]", "", cmd).strip()


def installed(categories):
    out = []
    for a in Gio.AppInfo.get_all():
        if not isinstance(a, DesktopAppInfo) or not a.should_show():
            continue
        cats = (a.get_categories() or "").split(";")
        if any(c in cats for c in categories):
            out.append(a)
    return sorted(out, key=lambda a: a.get_name().lower())


def program(cmd):
    """The real program a command runs ("code" -> code-oss: it's a link to it)."""
    try:
        first = shlex.split(cmd)[0] if cmd else ""
    except ValueError:
        first = cmd.split()[0] if cmd else ""
    path = GLib.find_program_in_path(first) if first else None
    return os.path.basename(os.path.realpath(path)) if path else os.path.basename(first)


class AppsPage(Page):
    name = "apps"
    title = "Apps"
    icon = "applications-system-symbolic"
    interval = 0

    def __init__(self, window):
        super().__init__(window)
        apps = _load(APPS, {})

        defaults = group(self, "Default apps", "What your shortcuts and the bar's buttons open. Saved right away.")
        self.terms = [(k, t) for k, t in TERMINALS if GLib.find_program_in_path(k)]
        self.term = Adw.ComboRow(title="Terminal", subtitle="Super + Q", model=Gtk.StringList.new([t for _k, t in self.terms]))
        cur = read_file(TERM, "alacritty").strip().lower()
        if cur in [k for k, _t in self.terms]:
            self.term.set_selected([k for k, _t in self.terms].index(cur))
        self.term.connect("notify::selected", self._term)
        self.term.add_prefix(Gtk.Image.new_from_icon_name("utilities-terminal-symbolic"))
        defaults.add(self.term)

        self.kind_rows = {}
        for key, title, sub, cats, default in KINDS:
            choices = installed(cats)
            current = apps.get(key, default)
            # The current one, even if it isn't a listed app (e.g. "code dash/")
            names = [a.get_name() for a in choices]
            cmds = [command_of(a) for a in choices]
            idx = next((i for i, c in enumerate(cmds) if program(c) == program(current)), None)
            if idx is None:
                names.append(current)
                cmds.append(current)
                idx = len(cmds) - 1
            else:
                cmds[idx] = current           # (keep its extra words, like a folder)
            row = Adw.ComboRow(title=title, subtitle=sub, model=Gtk.StringList.new(names))
            row.set_selected(idx)
            row.cmds = cmds
            icon = choices[idx].get_icon() if idx < len(choices) else None
            img = Gtk.Image.new_from_gicon(icon) if icon else Gtk.Image.new_from_icon_name("application-x-executable-symbolic")
            row.add_prefix(img)
            row.connect("notify::selected", lambda r, _p, k=key: self._pick(k, r))
            defaults.add(row)
            self.kind_rows[key] = row
            if key == "editor":
                self.folder = Adw.EntryRow(title="Folder the code editor opens (empty: none)", show_apply_button=True)
                ed = apps.get("editor", "code dash/").split(None, 1)
                self.folder.set_text(ed[1] if len(ed) > 1 else "")
                self.folder.connect("apply", lambda r: self._folder(r.get_text().strip()))
                defaults.add(self.folder)

        self.start = group(self, "Startup apps", "Open by themselves when you log in. Add one with + at the top right.")
        # "+" at the top right of the window: add a startup app
        self.header_widget = Gtk.MenuButton(icon_name="list-add-symbolic", tooltip_text="Add a startup app")
        self.header_widget.set_popover(self._app_popover())
        self.start_rows = []
        self._fill_startup()

    # ----- default apps -----

    def _term(self, row, _p):
        if self._updating:
            return
        k, t = self.terms[row.get_selected()]
        try:
            with open(TERM, "w") as f:
                f.write(k + "\n")
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")
            return
        self.toast(f"Terminal: {t}")

    def _pick(self, key, row):
        if self._updating:
            return
        cmd = row.cmds[row.get_selected()]
        if key == "editor" and self.folder.get_text().strip() and len(cmd.split()) == 1:
            cmd = f"{cmd} {self.folder.get_text().strip()}"
        self._set(key, cmd)
        self.toast(f"{dict((k, t) for k, t, *_ in KINDS)[key]}: {row.get_selected_item().get_string()}")

    def _folder(self, folder):
        cmd = _load(APPS, {}).get("editor", "code dash/").split(None, 1)[0]
        self._set("editor", f"{cmd} {folder}".strip())
        self.toast("Saved")

    def _set(self, key, value):
        apps = _load(APPS, {})
        apps[key] = value
        try:
            _save(APPS, apps)
        except OSError as e:
            self.toast(f"Couldn't save: {e.strerror}")

    # ----- startup apps -----

    def _app_popover(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=8, margin_bottom=8,
                      margin_start=8, margin_end=8)
        search = Gtk.SearchEntry(placeholder_text="Search apps")
        lst = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        lst.add_css_class("navigation-sidebar")
        apps = sorted((a for a in Gio.AppInfo.get_all() if isinstance(a, DesktopAppInfo) and a.should_show()),
                      key=lambda a: a.get_name().lower())
        for a in apps:
            r = Gtk.ListBoxRow()
            b = Gtk.Box(spacing=10, margin_top=4, margin_bottom=4)
            if a.get_icon():
                b.append(Gtk.Image.new_from_gicon(a.get_icon()))
            b.append(Gtk.Label(label=a.get_name(), xalign=0))
            r.set_child(b)
            r.app = a
            lst.append(r)
        lst.set_filter_func(lambda r: search.get_text().lower() in r.app.get_name().lower())
        search.connect("search-changed", lambda *_: lst.invalidate_filter())
        scroll = Gtk.ScrolledWindow(child=lst, min_content_height=320, min_content_width=280,
                                    hscrollbar_policy=Gtk.PolicyType.NEVER)
        box.append(search)
        box.append(scroll)
        pop = Gtk.Popover(child=box)
        lst.connect("row-activated", lambda _l, r: (pop.popdown(), self._add_startup(r.app)))
        return pop

    def _add_startup(self, app):
        items = _load(STARTUP, [])
        cmd = command_of(app)
        if any(i.get("exec") == cmd for i in items):
            self.toast(f"{app.get_name()} is already there")
            return
        items.append({"name": app.get_name(), "exec": cmd, "icon": app.get_icon().to_string() if app.get_icon() else ""})
        _save(STARTUP, items)
        self._fill_startup()
        self.toast(f"{app.get_name()} opens when you log in")

    def _fill_startup(self):
        for r in self.start_rows:
            self.start.remove(r)
        self.start_rows.clear()
        items = _load(STARTUP, [])
        if not items:
            r = Adw.ActionRow(title="None yet", subtitle="Add apps to open them when you log in")
            r.add_css_class("dim-label")
            self.start.add(r)
            self.start_rows.append(r)
        for i, it in enumerate(items):
            r = Adw.ActionRow(title=GLib.markup_escape_text(it.get("name", it.get("exec", ""))),
                              subtitle=GLib.markup_escape_text(it.get("exec", "")))
            icon = it.get("icon")
            img = Gtk.Image.new_from_gicon(Gio.Icon.new_for_string(icon)) if icon else \
                Gtk.Image.new_from_icon_name("application-x-executable-symbolic")
            r.add_prefix(img)
            sw = Gtk.Switch(active=it.get("on", True), valign=Gtk.Align.CENTER)
            sw.connect("notify::active", lambda s, _p, i=i: self._startup_on(i, s.get_active()))
            r.add_suffix(sw)
            r.add_suffix(icon_button("user-trash-symbolic", "Remove", lambda i=i: self._startup_remove(i)))
            self.start.add(r)
            self.start_rows.append(r)
        widgets_changed()

    def _startup_on(self, i, on):
        items = _load(STARTUP, [])
        if i < len(items):
            items[i]["on"] = on
            _save(STARTUP, items)

    def _startup_remove(self, i):
        items = _load(STARTUP, [])
        if i < len(items):
            name = items.pop(i).get("name", "")
            _save(STARTUP, items)
            self._fill_startup()
            self.toast(f"{name} no longer opens at login")
