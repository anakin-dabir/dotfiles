"""Updates: how many system updates are waiting (repo and AUR), the list,
check now, update now (bin/sysupdate in your terminal), how often to check
(the ArchUpdates timer)."""

import os
import re
import time

from gi.repository import Adw, GLib, Gtk

from ..common import BSPDIR, HOME, Page, group, launch, read_file, run, run_quiet, text_button, tool

COUNT = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.join(HOME, ".cache")), "Updates.txt")
DROPIN = os.path.join(HOME, ".config", "systemd", "user", "ArchUpdates.timer.d", "interval.conf")
EVERY = [("15min", "Every 15 minutes"), ("1h", "Every hour"), ("6h", "Every 6 hours"), ("1d", "Once a day"),
         ("never", "Never")]


def terminal_command(argv):
    """Run argv in your terminal (config/.term), the window staying open after."""
    term = read_file(os.path.join(BSPDIR, "config", ".term"), "alacritty").strip().lower() or "alacritty"
    script = " ".join(argv) + "; echo; read -r -p 'Press Enter to close…' _"
    if term == "kitty":
        return ["kitty", "--class", "Updating", "sh", "-c", script]
    if term == "st":
        return ["st", "-c", "Updating", "-e", "sh", "-c", script]
    return ["alacritty", "--class", "Updating,Updating", "-e", "sh", "-c", script]


class UpdatesPage(Page):
    name = "updates"
    title = "Updates"
    icon = "software-update-available-symbolic"
    interval = 0

    def __init__(self, window):
        super().__init__(window)
        self.checking = False
        top = group(self)
        self.status = Adw.ActionRow()
        self.status_icon = Gtk.Image(pixel_size=32)
        self.status.add_prefix(self.status_icon)
        self.check_btn = text_button("Check now", self.check)
        self.spinner = Adw.Spinner(visible=False)
        self.status.add_suffix(self.spinner)
        self.status.add_suffix(self.check_btn)
        top.add(self.status)
        upd = Adw.ActionRow(title="Update everything", subtitle="Repo and AUR, then removes unused packages and old "
                                                              "downloads. Opens a terminal; asks for your password.")
        upd.add_prefix(Gtk.Image.new_from_icon_name("system-software-install-symbolic"))
        self.update_btn = text_button("Update now…", self.update, css=["suggested-action"])
        upd.add_suffix(self.update_btn)
        top.add(upd)

        often = group(self, "Checking")
        self.every = Adw.ComboRow(title="Look for updates", model=Gtk.StringList.new([t for _v, t in EVERY]))
        self.every.set_selected(next((i for i, (v, _t) in enumerate(EVERY) if v == self._interval()), 0))
        self.every.connect("notify::selected", self._set_interval)
        often.add(self.every)

        self.lists = group(self, "Waiting")
        self.list_rows = []
        self.loaded = False

    # ----- state -----

    def refresh(self):
        n = read_file(COUNT, "").strip()
        try:
            age = time.time() - os.path.getmtime(COUNT)
        except OSError:
            age = None
        when = ("" if age is None else "just now" if age < 90 else f"{int(age // 60)} minutes ago" if age < 3600
                else f"{int(age // 3600)} hours ago" if age < 86400 else f"{int(age // 86400)} days ago")
        if n.isdigit() and int(n) > 0:
            self.status.set_title(f"{n} updates waiting")
            self.status_icon.set_from_icon_name("software-update-available-symbolic")
        elif n == "0":
            self.status.set_title("Everything is up to date")
            self.status_icon.set_from_icon_name("emblem-ok-symbolic")
        else:
            self.status.set_title("Not checked yet")
            self.status_icon.set_from_icon_name("software-update-available-symbolic")
        self.status.set_subtitle(f"Checked {when}" if when else "")
        if not self.loaded:
            self.loaded = True
            self._load_list()

    def _load_list(self):
        """The waiting packages (checkupdates + paru -Qua; takes a few seconds)."""
        self._list([("Looking…", "", "")])
        out = {"repo": None, "aur": None}

        def got(kind, ok, text, _e):
            out[kind] = text if ok or text else ""
            if out["repo"] is not None and out["aur"] is not None:
                rows = []
                for kind2, label in (("repo", "Repo"), ("aur", "AUR")):
                    for line in (out[kind2] or "").splitlines():
                        m = re.match(r"(\S+)\s+(\S+)\s+->\s+(\S+)", line)
                        if m:
                            rows.append((m.group(1), f"{m.group(2)} → {m.group(3)}", label))
                self._list(rows or [("Nothing waiting", "", "")])
        run(["checkupdates"], lambda ok, o, e: got("repo", ok, o, e))
        run(["paru", "-Qua"], lambda ok, o, e: got("aur", ok, o, e))

    def _list(self, rows):
        for r in self.list_rows:
            self.lists.remove(r)
        self.list_rows.clear()
        self.lists.set_description(f"{len(rows)} packages" if rows and rows[0][1] else "")
        exp = None
        for i, (name, ver, kind) in enumerate(rows):
            r = Adw.ActionRow(title=GLib.markup_escape_text(name), subtitle=GLib.markup_escape_text(ver))
            if kind:
                tag = Gtk.Label(label=kind)
                tag.add_css_class("dim-label")
                r.add_suffix(tag)
            if i < 12:
                self.lists.add(r)
                self.list_rows.append(r)
            else:
                if exp is None:
                    exp = Adw.ExpanderRow(title=f"{len(rows) - 12} more")
                    self.lists.add(exp)
                    self.list_rows.append(exp)
                exp.add_row(r)

    # ----- actions -----

    def check(self):
        if self.checking:
            return
        self.checking = True
        self.spinner.set_visible(True)
        self.check_btn.set_sensitive(False)

        def done(_ok):
            self.checking = False
            self.spinner.set_visible(False)
            self.check_btn.set_sensitive(True)
            self.loaded = False
            self.refresh()
        run_quiet([tool("Updates"), "--sync-polybar"], done)

    def update(self):
        launch(terminal_command([tool("sysupdate"), "&&", tool("Updates"), "--sync-polybar"]))
        self.toast("Updating in a terminal window")

    # ----- how often -----

    def _interval(self):
        if run_state := read_file(DROPIN, ""):
            m = re.search(r"OnUnitActiveSec=(\S+)", run_state)
            if m:
                return m.group(1)
        enabled = os.path.exists(os.path.join(HOME, ".config", "systemd", "user", "timers.target.wants",
                                              "ArchUpdates.timer"))
        return "15min" if enabled else "never"

    def _set_interval(self, row, _p):
        if self._updating:
            return
        value = EVERY[row.get_selected()][0]
        if value == "never":
            run_quiet(["systemctl", "--user", "disable", "--now", "ArchUpdates.timer"])
        else:
            os.makedirs(os.path.dirname(DROPIN), exist_ok=True)
            with open(DROPIN, "w") as f:
                f.write("# Control Center > Updates\n[Timer]\nOnUnitActiveSec=\nOnUnitActiveSec=" + value + "\n")
            run_quiet(["sh", "-c", "systemctl --user daemon-reload && systemctl --user enable --now ArchUpdates.timer "
                                   "&& systemctl --user restart ArchUpdates.timer"])
        self.toast(f"Look for updates: {EVERY[row.get_selected()][1].lower()}")
