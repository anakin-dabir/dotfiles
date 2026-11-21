"""Notifications: do not disturb, history, notification center."""

import json
import os
import re
import time

from gi.repository import Adw, GLib, Gtk

from ..common import HOME, Page, group, launch, run, run_quiet, text_button, tool

STATE = os.path.join(os.environ.get("XDG_STATE_HOME", os.path.join(HOME, ".local", "state")), "notifications")
LOG = os.path.join(STATE, "log.jsonl")
SEEN = os.path.join(STATE, "last-seen")


def ago(t):
    s = max(0, int(time.time() - t))
    if s < 60:
        return "now"
    if s < 3600:
        return f"{s // 60} min ago"
    if s < 86400:
        return f"{s // 3600} h ago"
    return time.strftime("%b %-d", time.localtime(t))


class NotificationsPage(Page):
    name = "notifications"
    title = "Notifications"
    icon = "preferences-system-notifications-symbolic"
    interval = 3

    def __init__(self, window):
        super().__init__(window)
        self.dnd_on = None
        self.recent_key = None

        top = group(self)
        self.dnd = Adw.SwitchRow(title="Do not disturb",
                                 subtitle="No pop-ups. Notifications still go to the notification center.")
        self.dnd.add_prefix(Gtk.Image.new_from_icon_name("notifications-disabled-symbolic"))
        self.dnd.connect("notify::active", self._dnd)
        top.add(self.dnd)

        hist = group(self, "History")
        self.count = Adw.ActionRow(title="Notification center")
        self.count.add_prefix(Gtk.Image.new_from_icon_name("preferences-system-notifications-symbolic"))
        self.count.add_suffix(text_button("Open", lambda: launch([tool("NotifyCenter")])))
        hist.add(self.count)
        clear = Adw.ActionRow(title="Clear all notifications", subtitle="The last list is kept as a backup")
        clear.add_suffix(text_button("Clear All", self._clear, css=["destructive-action"]))
        hist.add(clear)
        test = Adw.ActionRow(title="Send a test notification", subtitle="See how pop-ups look in this theme")
        test.add_suffix(text_button("Send", lambda: run_quiet(
            ["notify-send", "-a", "Control Center", "-i", "preferences-system-notifications",
             "Hello there", "This is how notifications look in this theme."])))
        hist.add(test)

        self.recent = group(self, "Recent")
        self.recent_rows = []

    def _dnd(self, row, _p):
        if self._updating or row.get_active() == self.dnd_on:
            return
        self.dnd_on = row.get_active()
        run_quiet([tool("NotifyCenter"), "--dnd"])

    def _clear(self):
        d = Adw.AlertDialog(heading="Clear all notifications?", body="They're removed from the notification center.")
        d.add_response("cancel", "Cancel")
        d.add_response("clear", "Clear All")
        d.set_response_appearance("clear", Adw.ResponseAppearance.DESTRUCTIVE)
        d.connect("response", lambda _d, r: r == "clear" and run_quiet(
            [tool("NotifyCenter"), "--clear"], lambda _ok: (setattr(self, "recent_key", None), self.refresh())))
        d.present(self.window)

    def refresh(self):
        def paused(ok, out, _e):
            self.dnd_on = out.strip() == "true"
            self.quietly(lambda: self.dnd.set_active(self.dnd_on))
        run(["dunstctl", "is-paused"], paused)

        items = []
        try:
            with open(LOG) as f:
                for line in f:
                    try:
                        items.append(json.loads(line))
                    except ValueError:
                        pass
        except OSError:
            pass
        try:
            seen = int(open(SEEN).read().strip())
        except (OSError, ValueError):
            seen = 0
        unread = sum(1 for i in items if i.get("time", 0) > seen)
        self.count.set_subtitle(f"{len(items)} notification{'s' if len(items) != 1 else ''}"
                                + (f" · {unread} unread" if unread else ""))

        latest = sorted(items, key=lambda i: i.get("time", 0), reverse=True)[:6]
        key = repr([(i.get("key"), i.get("time")) for i in latest])
        if key == self.recent_key:
            return
        self.recent_key = key
        for r in self.recent_rows:
            self.recent.remove(r)
        self.recent_rows.clear()
        self.recent.set_visible(bool(latest))
        for i in latest:
            title = i.get("summary") or i.get("app") or "Notification"
            body = re.sub(r"<[^>]+>", "", i.get("body") or "").replace("\n", " ").strip()
            row = Adw.ActionRow(title=GLib.markup_escape_text(title),
                                subtitle=GLib.markup_escape_text((i.get("app") or "") + (" · " if body else "") + body[:90]))
            row.set_subtitle_lines(1)
            when = Gtk.Label(label=ago(i.get("time", 0)))
            when.add_css_class("dim-label")
            row.add_suffix(when)
            self.recent.add(row)
            self.recent_rows.append(row)
