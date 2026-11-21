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
    # Safety net: whatever happens to this window, the shortcuts come back
    subprocess.Popen(["sh", "-c", 'sleep 90; pgrep -x sxhkd >/dev/null || exec sxhkd -c "$0"', FILE],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                     start_new_session=True, cwd=os.path.expanduser("~"))


def resume():
    if subprocess.run(["pgrep", "-x", "sxhkd"], capture_output=True).returncode != 0:
        env = {k: v for k, v in os.environ.items() if k not in ("GDK_BACKEND", "BROADWAY_DISPLAY")}
        subprocess.Popen(["sxhkd", "-c", FILE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, start_new_session=True, env=env, cwd=os.path.expanduser("~"))


# ===================== actions: what the Shortcuts page shows =====================
#
# One row per thing a shortcut does. A line with {a,b,c} lists stands for
# several actions: up to SPLIT of them become their own rows (and are split
# into separate lines in the file the first time one is changed); bigger
# sets (Super + 1…9) stay one row.

SPLIT = 4

# (regex on the command, name, group); first match wins
NAMES = [
    (r"OpenApps --terminal", "Open terminal", "Apps"),
    (r"OpenApps --floating", "Open floating terminal", "Apps"),
    (r"OpenApps --menu", "App menu", "Apps"),
    (r"OpenApps --browser", "Open web browser", "Apps"),
    (r"OpenApps --code", "Open code editor", "Apps"),
    (r"OpenApps --editor", "Open text editor", "Apps"),
    (r"OpenApps --filemanager", "Open file manager", "Apps"),
    (r"OpenApps --yazi", "Open Yazi (files in the terminal)", "Apps"),
    (r"OpenApps --nvim", "Open Neovim", "Apps"),
    (r"OpenApps --music", "Open music player", "Apps"),
    (r"OpenApps --soundcontrol", "Open sound mixer", "Apps"),
    (r"OpenApps --telegram", "Open Telegram", "Apps"),
    (r"OpenApps --whats", "Open WhatsApp", "Apps"),
    (r"OpenApps --scratch", "Scratchpad terminal (show/hide)", "Apps"),
    (r"OpenApps --monitor", "System monitor", "Apps"),
    (r"OpenApps --xephyr-sandbox-nvidia", "Sandbox desktop on the NVIDIA card", "Apps"),
    (r"OpenApps --xephyr-sandbox", "Sandbox desktop", "Apps"),
    (r"OpenApps --run-on-nvidia", "Run an app on the NVIDIA card", "Apps"),
    (r"kitty --session", "Open the work terminal tabs", "Apps"),
    (r"^\s*scrcpy", "Show your phone's screen (scrcpy)", "Apps"),
    (r"ControlCenter customize", "Customize the theme", "Control Center"),
    (r"ControlCenter keyboard", "Keyboard lighting", "Control Center"),
    (r"ControlCenter\s*$", "Open Control Center", "Control Center"),
    (r"RiceSelector", "Choose a theme", "Control Center"),
    (r"BarSelector", "Choose a bar design", "Control Center"),
    (r"WallSelect", "Choose a wallpaper", "Control Center"),
    (r"RofiLauncher --choose-style", "Choose the app menu style", "Control Center"),
    (r"Term --selecterm", "Choose the terminal", "Control Center"),
    (r"OpenApps --KeyHelp", "Show all shortcuts", "System"),
    (r"OpenApps --android", "Phones (Control Center)", "Control Center"),
    (r"OpenApps --netmanager", "Network menu", "System"),
    (r"OpenApps --bluetooth", "Bluetooth menu", "System"),
    (r"OpenApps --clipboard", "Clipboard history", "System"),
    (r"OpenApps --pass", "Passwords", "System"),
    (r"OpenApps --keyboard", "Keyboard layout menu", "System"),
    (r"OpenApps --powermenu", "Power menu", "System"),
    (r"NotifyCenter", "Notification center", "System"),
    (r"kbd-rainbow", "Rainbow keyboard on/off", "System"),
    (r"ScreenLocker", "Lock the screen", "System"),
    (r"^\s*xkill", "Close an app by clicking it", "Windows"),
    (r"Kill\.sh", "Close the app under the mouse", "Windows"),
    (r"bspc wm -r", "Restart bspwm", "System"),
    (r"pkill -USR1 -x sxhkd", "Reload shortcuts", "System"),
    (r"HideBar -h", "Hide the bar", "System"),
    (r"HideBar -u", "Show the bar", "System"),
    (r"jgmenu", "Desktop menu (right click)", "System"),
    (r"xte .keydown", "Copilot key works as Right Ctrl", "System"),
    (r"xte .keyup", "Copilot key works as Right Ctrl (release)", "System"),
    (r"OpenApps --screenshot", "Screenshot menu", "Screenshots"),
    (r"flameshot gui", "Screenshot with Flameshot", "Screenshots"),
    (r"Capture text", "Copy text from the screen", "Screenshots"),
    (r"Brightness up", "Brightness up", "Media and hardware keys"),
    (r"Brightness down", "Brightness down", "Media and hardware keys"),
    (r"Volume --inc", "Volume up", "Media and hardware keys"),
    (r"Volume --dec", "Volume down", "Media and hardware keys"),
    (r"Volume --toggle", "Mute", "Media and hardware keys"),
    (r"MediaControl --next", "Next track", "Media and hardware keys"),
    (r"MediaControl --previous", "Previous track", "Media and hardware keys"),
    (r"MediaControl --toggle", "Play / pause", "Media and hardware keys"),
    (r"MediaControl --stop", "Stop", "Media and hardware keys"),
    (r"bspc node -c$", "Close window", "Windows"),
    (r"bspc node -k$", "Force-close window", "Windows"),
    (r"bspc node -t tiled", "Tile window", "Windows"),
    (r"bspc node -t pseudo_tiled", "Pseudo-tile window", "Windows"),
    (r"bspc node -t floating", "Float window", "Windows"),
    (r"bspc node -t fullscreen", "Full screen", "Windows"),
    (r"bspc node -g marked", "Mark window", "Windows"),
    (r"bspc node -g locked", "Lock window (can't be closed)", "Windows"),
    (r"bspc node -g sticky", "Pin window to every workspace", "Windows"),
    (r"bspc node -g private", "Keep window in place", "Windows"),
    (r"HideNode --hide", "Hide window", "Windows"),
    (r"hidden=on", "Hide / bring back a window", "Windows"),
    (r"HideNode --menu", "Bring back hidden windows", "Windows"),
    (r"picom-trans -c -3", "Window more see-through", "Windows"),
    (r"picom-trans -c \+3", "Window less see-through", "Windows"),
    (r"picom-trans -c -d", "Window transparency back to normal", "Windows"),
    (r"bspc node @/ -B", "Even out window sizes", "Windows"),
    (r"bspc node -p east", "Next window opens to the right", "Windows"),
    (r"bspc node -p south", "Next window opens below", "Windows"),
    (r"bspc node -p cancel", "Cancel where the next window opens", "Windows"),
    (r"bspc node -f last", "Previous window", "Windows"),
    (r"bspc desktop -f last", "Previous workspace", "Workspaces"),
    (r"bspc desktop -f prev", "Workspace on the left", "Workspaces"),
    (r"bspc desktop -f next", "Workspace on the right", "Workspaces"),
    (r"bspc node -d prev", "Move window to the workspace on the left", "Workspaces"),
    (r"bspc node -d next", "Move window to the workspace on the right", "Workspaces"),
    (r"tail -n 1", "Last workspace", "Workspaces"),
    (r"DIR=west", "Focus the window on the left", "Windows"),
    (r"DIR=south", "Focus the window below", "Windows"),
    (r"DIR=north", "Focus the window above", "Windows"),
    (r"DIR=east", "Focus the window on the right", "Windows"),
    (r"bspc node -s west", "Swap with the window on the left", "Windows"),
    (r"bspc node -s south", "Swap with the window below", "Windows"),
    (r"bspc node -s north", "Swap with the window above", "Windows"),
    (r"bspc node -s east", "Swap with the window on the right", "Windows"),
    (r"bspc node -z left -20", "Grow window to the left", "Windows"),
    (r"bspc node -z bottom 0 20", "Grow window down", "Windows"),
    (r"bspc node -z top 0 -20", "Grow window up", "Windows"),
    (r"bspc node -z right 20", "Grow window to the right", "Windows"),
    (r"bspc node -z right -20", "Shrink window from the right", "Windows"),
    (r"bspc node -z top 0 20", "Shrink window from the top", "Windows"),
    (r"bspc node -z bottom 0 -20", "Shrink window from the bottom", "Windows"),
    (r"bspc node -z left 20", "Shrink window from the left", "Windows"),
    (r"bspc node -z top_right 20 -20", "Bigger window", "Windows"),
    (r"bspc node -z top_right -20 20", "Smaller window", "Windows"),
    (r"xdo resize -w \+", "Bigger floating window", "Windows"),
    (r"xdo resize -w -", "Smaller floating window", "Windows"),
    (r"bspc node -v -20 0", "Move floating window left", "Windows"),
    (r"bspc node -v 0 20", "Move floating window down", "Windows"),
    (r"bspc node -v 0 -20", "Move floating window up", "Windows"),
    (r"bspc node -v 20 0", "Move floating window right", "Windows"),
    (r"bspc query -N -d \| xargs", "Close every window on this workspace", "Windows"),
    (r"id -c$", "Close the other windows", "Windows"),
    (r"id -k$", "Force-close the other windows", "Windows"),
    (r"\.marked", "Bring marked windows here", "Windows"),
]
SETS = [
    (r"\{desktop -f,node -d\}", "Go to a workspace (with Ctrl: send the window there)", "Workspaces"),
    (r"query -N -d \{1-9\}", "Bring all windows from a workspace here", "Workspaces"),
]
GROUP_ORDER = ["Apps", "Control Center", "Windows", "Workspaces", "Screenshots", "Media and hardware keys",
               "System", "Other", "Your shortcuts"]


def _expand_with(text):
    """[(expanded text, (chosen elements...))] - sxhkd's {a,b} lists and {1-9} ranges."""
    parts = re.split(r"(\{[^{}]*\})", text)
    choices = []
    for p in parts:
        if p.startswith("{") and p.endswith("}"):
            items = []
            for x in p[1:-1].split(","):
                m = re.fullmatch(r"\s*(\w)-(\w)\s*", x)
                if m:
                    items += [chr(c) for c in range(ord(m.group(1)), ord(m.group(2)) + 1)]
                else:
                    items.append("" if x.strip() == "_" else x)
            choices.append(items)
        else:
            choices.append([p])
    out = []
    for combo in itertools.product(*choices):
        chosen = tuple(c for c, p in zip(combo, parts) if p.startswith("{"))
        out.append(("".join(combo), chosen))
    return out


def canonical(keys):
    """"super + alt Left" -> "super + alt + Left" (and chains: "a ; b")."""
    chains = []
    for part in keys.split(";"):
        toks = [t for t in re.split(r"[\s+]+", part.strip()) if t]
        chains.append(" + ".join(toks))
    return " ; ".join(c for c in chains if c)


def name_for(command, desc, chosen=()):
    flat = " ".join(command.split())
    for pattern, name, grp in NAMES:
        if re.search(pattern, flat, re.M):
            return name, grp
    base = desc or flat[:50]
    extra = " ".join(c.strip() for c in chosen if c.strip())
    return (f"{base} — {extra}" if extra else base), "Other"


class Action:
    """One row of the Shortcuts page."""

    def __init__(self, sc, keys, command, name, grp, index=None, is_set=False, all_keys=()):
        self.sc, self.keys, self.command, self.name, self.group = sc, keys, command, name, grp
        self.index = index          # position in sc's expansion (None: the whole line)
        self.is_set = is_set        # a big set (Super + 1…9): shown, turned off as a whole
        self.all_keys = all_keys

    @property
    def on(self):
        return self.sc.on

    def combos(self):
        return [_norm(k) for k in (self.all_keys or [self.keys])]

    def caps(self):
        """Key caps to show: ["Super", "W"] (a set: its first and last, as a range)."""
        if self.is_set:
            return [pretty(self.all_keys[0]), "…", pretty(self.all_keys[-1])]
        return [pretty(self.keys)]


def actions(items=None):
    items = load() if items is None else items
    out = []
    for sc in items:
        grp_mine = "Your shortcuts" if sc.mine else None
        if sc.simple:
            name, grp = name_for(sc.command, sc.desc)
            if sc.mine:
                name = sc.desc or name
            out.append(Action(sc, canonical(sc.keys), sc.command, name, grp_mine or grp))
            continue
        keys = _expand_with(sc.keys)
        cmds = _expand_with(sc.command)
        if len(cmds) == 1:
            cmds = cmds * len(keys)
        if len(keys) > SPLIT or len(cmds) != len(keys):
            flat = " ".join(sc.command.split())
            name, grp = next(((n, g) for p_, n, g in SETS if re.search(p_, flat)), (None, None))
            if name is None:
                name, grp = name_for(sc.command, sc.desc)
                if grp == "Other":
                    name = sc.desc or name
            out.append(Action(sc, "", sc.command, name, grp_mine or grp, is_set=True,
                              all_keys=[canonical(k) for k, _c in keys]))
            continue
        for i, ((k, _kc), (c, cc)) in enumerate(zip(keys, cmds)):
            name, grp = name_for(c, sc.desc, cc)
            out.append(Action(sc, canonical(k), c, name, grp_mine or grp, index=i))
    return out


def action_clashes(acts):
    """{id(action): {names of the other actions on the same keys}} (shortcuts that are on).
    Chains sharing a first key ("Super + N, then X" and "…then K") are fine;
    a plain Super + N next to them is a clash."""
    plain, chains = {}, {}
    for a in acts:
        if a.on:
            for c in set(a.combos()):
                if " ; " in c:
                    chains.setdefault(c.split(" ; ")[0], []).append(a)
                plain.setdefault(c, []).append(a)
    out = {}

    def mark(group):
        uniq = list(dict.fromkeys(group))
        if len(uniq) > 1:
            for a in uniq:
                out.setdefault(id(a), set()).update(b.name for b in uniq if b is not a)
    for c, lst in plain.items():
        mark(lst)
        for a in lst if c in chains else []:          # plain keys that also start chains
            for b in chains[c]:
                if b is not a:
                    out.setdefault(id(a), set()).add(b.name)
                    out.setdefault(id(b), set()).add(a.name)
    return out


def _split(sc):
    """Rewrite a {a,b} line as separate lines (one per action), so each can change on its own."""
    lines = _lines()
    keys = _expand_with(sc.keys)
    cmds = _expand_with(sc.command)
    if len(cmds) == 1:
        cmds = cmds * len(keys)
    start = sc.start - 1 if sc.start > 0 and lines[sc.start - 1].lstrip().startswith("#") \
        and not lines[sc.start - 1].startswith(OFF) else sc.start
    new = []
    for (k, _kc), (c, cc) in zip(keys, cmds):
        name, _g = name_for(c, sc.desc, cc)
        body = [canonical(k)] + c.split("\n")
        if not sc.on:
            body = [OFF + x for x in body]
        new += [f"# {name}"] + body + [""]
    lines[start:sc.end] = new[:-1]
    _write(lines)


def _find(command, keys=None):
    for sc in load():
        if sc.simple and sc.command.strip() == command.strip() and (keys is None or canonical(sc.keys) == keys):
            return sc
    return None


def change_action(a, new_keys):
    if a.index is not None:
        _split(a.sc)
        sc = _find(a.command, a.keys) or _find(a.command)
    else:
        sc = a.sc
    if sc:
        set_keys(sc, new_keys)


def action_on(a, on):
    if a.index is not None:
        _split(a.sc)
        sc = _find(a.command, a.keys) or _find(a.command)
    else:
        sc = a.sc
    if sc:
        set_on(sc, on)


def default_keys(a):
    """The keys this action had before any change here (None if unknown or the same)."""
    global FILE
    orig = rice._original_path(FILE)
    if not os.path.exists(orig):
        return None
    saved, FILE = FILE, orig
    try:
        old = actions()
    finally:
        FILE = saved
    for b in old:
        if " ".join(b.command.split()) == " ".join(a.command.split()) and not b.is_set:
            return None if b.keys == a.keys else b.keys
    return None


def remove_action(a):
    """Delete a shortcut from the file (a set: the whole line). Reset brings it back."""
    if a.index is not None:
        _split(a.sc)
        sc = _find(a.command, a.keys) or _find(a.command)
    else:
        sc = a.sc
    if sc:
        remove(sc)
