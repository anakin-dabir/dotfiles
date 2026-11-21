"""About: this rice and this computer."""

import os
import platform
import re

from gi.repository import Adw, Gtk

from ..common import BSPDIR, HOME, Page, current_rice, group, launch, read_file, run, text_button, thumbnail

REPO = "https://github.com/anakin-dabir/dotfiles"


def os_name():
    for line in read_file("/etc/os-release").splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip('"')
    return platform.system()


def cpu():
    for line in read_file("/proc/cpuinfo").splitlines():
        if line.startswith("model name"):
            return re.sub(r"\s+", " ", line.split(":", 1)[1]).replace("(R)", "").replace("(TM)", "").strip()
    return platform.processor()


def memory():
    for line in read_file("/proc/meminfo").splitlines():
        if line.startswith("MemTotal:"):
            return f"{int(line.split()[1]) / 1024 / 1024:.1f} GB"
    return "–"


def main_bar(rice):
    text = read_file(os.path.join(BSPDIR, "rices", rice, "theme-config.bash"))
    m = re.search(r'^main_bar="?([^"\n]+)"?', text, re.M)
    return m.group(1) if m else "–"


class AboutPage(Page):
    name = "about"
    title = "About"
    icon = "help-about-symbolic"
    interval = 0

    def __init__(self, window):
        super().__init__(window)
        hero = group(self)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, halign=Gtk.Align.CENTER, margin_bottom=6)
        self.preview = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
        self.preview.set_size_request(150, 198)
        self.preview.add_css_class("cc-tile-image")
        self.preview.set_overflow(Gtk.Overflow.HIDDEN)
        self.preview.set_halign(Gtk.Align.CENTER)
        box.append(self.preview)
        self.name_lbl = Gtk.Label()
        self.name_lbl.add_css_class("cc-hero-title")
        box.append(self.name_lbl)
        sub = Gtk.Label(label="bspwm rice · anakin-dabir/dotfiles")
        sub.add_css_class("dim-label")
        box.append(sub)
        hero.add(box)

        rice = group(self, "Desktop")
        self.theme_row = self._row(rice, "Theme")
        self.bar_row = self._row(rice, "Bar")
        self._row(rice, "Window manager").value.set_label("bspwm")
        repo = Adw.ActionRow(title="Source and installer", subtitle=REPO.replace("https://", ""))
        repo.add_suffix(text_button("Open", lambda: launch(["xdg-open", REPO])))
        rice.add(repo)
        folder = Adw.ActionRow(title="Rice files", subtitle=BSPDIR.replace(HOME, "~"))
        folder.add_suffix(text_button("Open", lambda: launch(["xdg-open", BSPDIR])))
        rice.add(folder)

        pc = group(self, "This computer")
        product = read_file("/sys/class/dmi/id/product_name")
        vendor = read_file("/sys/class/dmi/id/sys_vendor")
        self._row(pc, "Model").value.set_label(f"{vendor} {product}".strip() or "–")
        self._row(pc, "Processor").value.set_label(cpu())
        self._row(pc, "Memory").value.set_label(memory())
        self.gpu = self._row(pc, "Graphics")
        self._row(pc, "System").value.set_label(os_name())
        self._row(pc, "Kernel").value.set_label(platform.release())
        self.uptime = self._row(pc, "Up for")

        def gpu(ok, out, _e):
            names = []
            for line in out.splitlines():
                if re.search(r"VGA|3D|Display", line):
                    n = line.split(": ", 1)[-1]
                    n = re.sub(r"\s*\(rev [^)]*\)", "", n)
                    names.append(n.replace("Corporation ", ""))
            self.gpu.value.set_label("\n".join(names) or "–")
        run(["lspci"], gpu)

    def _row(self, g, title):
        row = Adw.ActionRow(title=title)
        row.value = Gtk.Label(selectable=True, wrap=True, xalign=1, justify=Gtk.Justification.RIGHT, max_width_chars=40)
        row.value.add_css_class("dim-label")
        row.add_suffix(row.value)
        g.add(row)
        return row

    def refresh(self):
        rice = current_rice()
        self.name_lbl.set_label(rice.capitalize())
        self.theme_row.value.set_label(rice.capitalize())
        self.bar_row.value.set_label(main_bar(rice))
        thumbnail(os.path.join(BSPDIR, "rices", rice, "preview.webp"), 300, 396,
                  lambda tex: tex and self.preview.set_paintable(tex))
        try:
            secs = int(float(read_file("/proc/uptime", "0").split()[0]))
        except (ValueError, IndexError):
            secs = 0
        h, m = divmod(secs // 60, 60)
        self.uptime.value.set_label(f"{h} h {m} min" if h else f"{m} min")
