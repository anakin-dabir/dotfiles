"""Keyboard shortcuts: config/sxhkdrc, read and changed for the Shortcuts page.

A shortcut is a description comment, a keys line and indented command
line(s). Turned-off shortcuts keep their place, commented out with "#off ".
Shortcuts added in Control Center go in their own section at the end.
"""

import itertools
import os
import re
import subprocess

from . import rice
from .common import BSPDIR

FILE = os.path.join(BSPDIR, "config", "sxhkdrc")
OFF = "#off "
MINE = "# ----- Your shortcuts (Control Center) ----- #"

PRETTY = {
    "super": "Super", "alt": "Alt", "ctrl": "Ctrl", "shift": "Shift", "space": "Space", "@space": "Space",
    "Return": "Enter", "Escape": "Esc", "grave": "`", "comma": ",", "period": ".", "plus": "+",
    "minus": "−", "Print": "Print Screen", "Left": "←", "Right": "→", "Up": "↑", "Down": "↓",
    "XF86MonBrightnessUp": "Brightness up", "XF86MonBrightnessDown": "Brightness down",
    "XF86AudioRaiseVolume": "Volume up", "XF86AudioLowerVolume": "Volume down", "XF86AudioMute": "Mute",
    "XF86AudioNext": "Next track", "XF86AudioPrev": "Previous track", "XF86AudioPlay": "Play/Pause",
    "XF86AudioStop": "Stop", "button3": "Right click", "Tab": "Tab",
}


class Shortcut:
    def __init__(self):
        self.desc = ""          # the comment above it
        self.section = ""       # the heading it's under
        self.keys = ""          # as written ("super + {_,alt + }q")
        self.command = ""       # as written (may be several lines)
        self.start = self.end = 0   # line numbers in the file [start, end)
        self.on = True
        self.mine = False

    @property
    def simple(self):
        """One key combination (no {a,b} lists, no chains): can be changed here."""
        return "{" not in self.keys and ";" not in self.keys

    def combos(self):
        """Every key combination it stands for, normalised (for clashes)."""
        return [_norm(k) for k in expand(self.keys)]

    def pretty_keys(self):
        return [pretty(k) for k in expand(self.keys)]

    def title(self):
        if self.desc:
            return self.desc
        cmd = self.command.strip().splitlines()[0] if self.command.strip() else ""
        return cmd[:60]


def expand(keys):
    """sxhkd's {a,b,c} lists and {1-9} ranges, expanded."""
    parts = re.split(r"(\{[^}]*\})", keys)
    choices = []
    for p in parts:
        if p.startswith("{") and p.endswith("}"):
            items = []
            for x in p[1:-1].split(","):
                m = re.fullmatch(r"\s*(\w)-(\w)\s*", x)
                if m and len(m.group(1)) == 1:
                    items += [chr(c) for c in range(ord(m.group(1)), ord(m.group(2)) + 1)]
                else:
                    items.append("" if x.strip() == "_" else x)
            choices.append(items)
        else:
            choices.append([p])
    out = []
    for combo in itertools.product(*choices):
        k = re.sub(r"\s+", " ", "".join(combo)).strip()
        k = re.sub(r"\+\s*\+", "+", k).strip(" +")
        out.append(k)
    return out


def _norm(k):
    # (~ and @ are kept: "@keys" runs on release, "~keys" lets the key through,
    # so they don't clash with the plain keys)
    parts = [p.strip() for p in k.split(";")]
    out = []
    for part in parts:
        keys = [x.strip() for x in part.split("+") if x.strip()]
        mods = sorted(x for x in keys if x in ("super", "alt", "ctrl", "shift", "mod1", "mod4"))
        rest = [x.lower() for x in keys if x not in mods]
        out.append("+".join(mods + rest))
    return " ; ".join(out)


def pretty(k):
    chain = []
    for part in k.split(";"):
        keys = [x.strip().lstrip("~@") for x in re.split(r"\s+\+\s+|\s+(?=\S)", part.strip()) if x.strip() and x.strip() != "+"]
        names = []
        for x in keys:
            n = PRETTY.get(x, x)
            names.append(n.upper() if len(n) == 1 and n.isalpha() else n)
        chain.append(" + ".join(names))
    return ", then ".join(chain)


def _is_heading(line):
    s = line.strip()
    return bool(re.fullmatch(r"#+", s) or re.fullmatch(r"#\s*-{2,}.*-{2,}\s*#?", s))


def load():
    """[Shortcut] in file order."""
    try:
        with open(FILE) as f:
            lines = f.read().split("\n")
    except OSError:
        return []
    out, section, desc, mine = [], "", "", False
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            desc = ""
            i += 1
            continue
        if s == MINE:
            mine, section, desc = True, "Your shortcuts", ""
            i += 1
            continue
        if _is_heading(s):
            m = re.search(r"-{2,}\s*(.*?)\s*-{2,}", s)
            if m and m.group(1):
                section = m.group(1)
            desc = ""
            i += 1
            continue
        off = s.startswith(OFF)
        if s.startswith("#") and not off:
            if not desc:                  # (the first line of a comment block names it)
                desc = s.lstrip("#").strip()
            i += 1
            continue
        # a keys line (maybe turned off), then its indented command lines
        sc = Shortcut()
        sc.section, sc.desc, sc.mine, sc.on, sc.start = section, desc, mine, not off, i
        sc.keys = s[len(OFF):] if off else s
        i += 1
        cmd = []
        while i < len(lines):
            t = lines[i]
            body = t[len(OFF):] if off and t.startswith(OFF) else t
            if body.startswith((" ", "\t")) and body.strip():
                cmd.append(body)
                i += 1
            else:
                break
        sc.command, sc.end = "\n".join(cmd), i
        out.append(sc)
        desc = ""
    return out


def clashes(items):
    """{normalised combo: [Shortcut]} for keys used by more than one shortcut
    that's on (also keys that are the first step of a chain, like super + n
    and "super + n, then x")."""
    seen = {}
    for sc in items:
        if sc.on:
            for c in set(sc.combos()):
                seen.setdefault(c, []).append(sc)
                if " ; " in c:
                    seen.setdefault(c.split(" ; ")[0] + " (first key)", []).append(sc)
    out = {c: v for c, v in seen.items() if len(set(id(x) for x in v)) > 1 and not c.endswith("(first key)")}
    for c, v in seen.items():
        if c.endswith(" (first key)"):
            plain = c[:-len(" (first key)")]
            if plain in seen:
                out[plain] = list(dict.fromkeys(seen[plain] + v))
    return out


def _write(lines):
    rice.keep_original(FILE)
    with open(FILE, "w") as f:
        f.write("\n".join(lines))
    reload()


def _lines():
    with open(FILE) as f:
        return f.read().split("\n")


def reload():
    subprocess.run(["pkill", "-USR1", "-x", "sxhkd"], check=False)


def set_on(sc, on):
    lines = _lines()
    for n in range(sc.start, sc.end):
        if on and lines[n].startswith(OFF):
            lines[n] = lines[n][len(OFF):]
        elif not on and not lines[n].startswith(OFF):
            lines[n] = OFF + lines[n]
    _write(lines)


def set_keys(sc, keys):
    lines = _lines()
    lines[sc.start] = (OFF if not sc.on else "") + keys
    _write(lines)


def add(desc, keys, command):
    lines = _lines()
    while lines and not lines[-1].strip():
        lines.pop()
    if MINE not in [x.strip() for x in lines]:
        lines += ["", MINE]
    lines += ["", f"# {desc}", keys, "    " + command, ""]
    _write(lines)


def remove(sc):
    """Only for shortcuts added here."""
    lines = _lines()
    start = sc.start - 1 if sc.start > 0 and lines[sc.start - 1].startswith("#") else sc.start
    del lines[start:sc.end]
    _write(lines)


def has_original():
    return rice.has_original(FILE)


def reset():
    ok = rice.restore_original(FILE)
    reload()
    return ok


# While new keys are being recorded, sxhkd must not catch them
def pause():
    subprocess.run(["pkill", "-x", "sxhkd"], check=False)


def resume():
    if subprocess.run(["pgrep", "-x", "sxhkd"], capture_output=True).returncode != 0:
        subprocess.Popen(["sxhkd", "-c", FILE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, start_new_session=True)
