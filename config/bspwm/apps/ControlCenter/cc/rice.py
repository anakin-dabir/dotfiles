"""Reading and changing the rice's own files: a theme's theme-config.bash
and a bar's config.ini. Before a file is changed the first time, its
original is copied aside, so "Reset" can always bring it back."""

import os
import re
import shutil

from .common import BSPDIR, HOME, current_rice

ORIGINALS = os.path.join(os.environ.get("XDG_STATE_HOME", os.path.join(HOME, ".local", "state")),
                         "control-center", "originals")


# ----- originals -----

def _original_path(path):
    return os.path.join(ORIGINALS, os.path.relpath(os.path.realpath(path), os.path.realpath(BSPDIR)))


def keep_original(path):
    dst = _original_path(path)
    if not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(path, dst)


def has_original(path):
    return os.path.exists(_original_path(path))


def restore_original(path):
    """Put the original back (the file is then untouched again: no backup kept)."""
    src = _original_path(path)
    if os.path.exists(src):
        shutil.copy2(src, path)
        os.remove(src)
        return True
    return False


# ----- theme-config.bash -----

def theme_file(rice=None):
    return os.path.join(BSPDIR, "rices", rice or current_rice(), "theme-config.bash")


_ASSIGN = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)=("(?:[^"\\]|\\.)*"|\'[^\']*\'|[^\s#]*)(.*)$')


def _unquote(v):
    if len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1]
    if len(v) >= 2 and v[0] == v[-1] == '"':
        return re.sub(r'\\(["\\$`])', r"\1", v[1:-1])
    return v


def theme_vars(rice=None):
    """{name: value} with $var / ${var} references filled in, like bash would."""
    out = {"HOME": HOME}
    try:
        with open(theme_file(rice)) as f:
            lines = f.read().splitlines()
    except OSError:
        return out
    for line in lines:
        m = _ASSIGN.match(line.strip())
        if not m:
            continue
        raw = m.group(2)
        val = _unquote(raw)
        if not raw.startswith("'"):
            # ${name#\#} (the value without its leading #), then $name / ${name}
            val = re.sub(r"\$\{([A-Za-z_]\w*)#\\?#\}", lambda r: out.get(r.group(1), "").lstrip("#"), val)
            val = re.sub(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?",
                         lambda r: out.get(r.group(1), os.environ.get(r.group(1), "")), val)
        out[m.group(1)] = val
    return out


def _quote(value):
    value = str(value)
    home = os.path.expanduser("~") + "/"
    lead = ""
    if value.startswith(home):            # $HOME/..., like the theme files (and no user name in the repo)
        lead, value = "$HOME/", value[len(home):]
    return '"' + lead + re.sub(r'(["\\$`])', r"\\\1", value) + '"'


def set_theme_vars(changes, rice=None):
    """Write NAME="value" for each change, keeping comments after the value.
    Names that aren't in the file yet are added at the end."""
    path = theme_file(rice)
    keep_original(path)
    with open(path) as f:
        lines = f.read().split("\n")
    todo = dict(changes)
    for i, line in enumerate(lines):
        m = _ASSIGN.match(line)
        if m and m.group(1) in todo:
            lines[i] = f"{m.group(1)}={_quote(todo.pop(m.group(1)))}{m.group(3)}"
    if todo:
        if lines and lines[-1] == "":
            lines.pop()
        lines.append("")
        lines.append("# Added by Control Center")
        lines.extend(f"{k}={_quote(v)}" for k, v in todo.items())
        lines.append("")
    with open(path, "w") as f:
        f.write("\n".join(lines))


# ----- bars -----

BARS = os.path.join(BSPDIR, "bars")


def bar_names():
    return sorted(d for d in os.listdir(BARS) if os.path.isdir(os.path.join(BARS, d)))


def is_polybar(bar):
    return os.path.exists(os.path.join(BARS, bar, "config.ini"))


def bar_config(bar):
    return os.path.join(BARS, bar, "config.ini")


def launched_sections(bar):
    """Names of the [bar/...] sections Bar.bash actually starts."""
    text = ""
    try:
        with open(os.path.join(BARS, bar, "Bar.bash")) as f:
            text = f.read()
    except OSError:
        pass
    names = re.findall(r"polybar\s+(?:-\S+\s+)*([A-Za-z0-9_-]+)\s+-c", text)
    names += re.findall(r"polybar\s+-q\s+([A-Za-z0-9_-]+)", text)
    seen = []
    for n in names:
        if n not in seen:
            seen.append(n)
    return seen


def _sections(text):
    """[(name, start, end)] for each [bar/NAME] section (character offsets)."""
    marks = [(m.group(1), m.start()) for m in re.finditer(r"(?m)^\[([^\]]+)\]", text)]
    out = []
    for i, (name, start) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else len(text)
        out.append((name, start, end))
    return out


def bar_layout(bar, section):
    """{'left': [...], 'center': [...], 'right': [...]} for one [bar/section]."""
    with open(bar_config(bar)) as f:
        text = f.read()
    for name, start, end in _sections(text):
        if name == f"bar/{section}":
            body = text[start:end]
            out = {}
            for side in ("left", "center", "right"):
                m = re.search(rf"(?m)^modules-{side}\s*=\s*(.*)$", body)
                out[side] = m.group(1).split() if m else []
            return out
    return {"left": [], "center": [], "right": []}


def set_bar_layout(bar, section, layout):
    path = bar_config(bar)
    keep_original(path)
    with open(path) as f:
        text = f.read()
    for name, start, end in _sections(text):
        if name != f"bar/{section}":
            continue
        body = text[start:end]
        for side in ("left", "center", "right"):
            line = f"modules-{side} = {' '.join(layout[side])}"
            if re.search(rf"(?m)^modules-{side}\s*=", body):
                body = re.sub(rf"(?m)^modules-{side}\s*=.*$", lambda _m: line, body)
            elif layout[side]:          # (no line for an empty part that had none)
                body = body.rstrip("\n") + "\n" + line + "\n\n"
        text = text[:start] + body + text[end:]
        break
    with open(path, "w") as f:
        f.write(text)


def bar_modules(bar):
    """Every module defined for this bar (modules.ini and included files)."""
    names = []
    for fname in ("modules.ini", "config.ini"):
        try:
            with open(os.path.join(BARS, bar, fname)) as f:
                names += re.findall(r"(?m)^\[module/([^\]]+)\]", f.read())
        except OSError:
            pass
    try:
        with open(os.path.join(BSPDIR, "config", "system.ini")) as f:
            names += re.findall(r"(?m)^\[module/([^\]]+)\]", f.read())
    except OSError:
        pass
    return sorted(set(names))


def bar_text_font(bar, section):
    """(family, size) of the bar's main text font (font-0), or None."""
    with open(bar_config(bar)) as f:
        text = f.read()
    for name, start, end in _sections(text):
        if name == f"bar/{section}":
            m = re.search(r'(?m)^font-0\s*=\s*"?([^":;]+)([^"]*)"?', text[start:end])
            if m:
                size = re.search(r"size=([\d.]+)", m.group(2))
                return m.group(1).strip(), float(size.group(1)) if size else 10.0
    return None


def set_bar_text_font(bar, family, size):
    """Use `family` (at `size`) wherever the bar used its old text font,
    in every [bar/...] section; styles and vertical offsets are kept."""
    path = bar_config(bar)
    keep_original(path)
    with open(path) as f:
        text = f.read()
    old = None
    m = re.search(r'(?m)^font-0\s*=\s*"?([^":;]+)', text)
    if m:
        old = m.group(1).strip()
    if not old:
        return

    def fix(line_match):
        line = line_match.group(0)
        fm = re.match(r'^(font-\d+\s*=\s*"?)([^":;]+)(.*)$', line)
        if not fm or fm.group(2).strip() != old:
            return line
        rest = fm.group(3)
        if "size=" in rest:
            rest = re.sub(r"size=[\d.]+", f"size={size:g}", rest)
        return f"{fm.group(1)}{family}{rest}"

    text = re.sub(r"(?m)^font-\d+\s*=.*$", fix, text)
    with open(path, "w") as f:
        f.write(text)


# ----- bar item icons (Control Center > Bar > ... > Change icon) -----

ICON_KEYS = ("format-prefix", "label")   # where an item keeps its icon (also format-<state>-prefix)
SHARED_ICONS = ("media", "clipboard", "capture")      # config/system.ini items, icon in the bar's [icons]


def _section_body(text, name):
    for sec, start, end in _sections(text):
        if sec == name:
            return start, end
    return None


def bar_fonts(bar, section):
    """Font families of one [bar/section], in font-0, font-1... order."""
    with open(bar_config(bar)) as f:
        text = f.read()
    span = _section_body(text, f"bar/{section}")
    if not span:
        return []
    fonts = {}
    for n, fam in re.findall(r'(?m)^font-(\d+)\s*=\s*"?([^:";]+)', text[span[0]:span[1]]):
        fonts[int(n)] = fam.strip()
    return [fonts[k] for k in sorted(fonts)]


def _icon_only(value):
    """The icon in a value that is only an icon (tags and spaces aside), or None."""
    v = re.sub(r"%\{[^}]*\}", "", value).strip().strip('"').strip()
    return v if v and len(v) <= 2 and all(ord(c) >= 0xE000 for c in v) else None


NOTIFY_STATES = [("notify", "No new notifications", ""), ("notify-unread", "Something unread", ""),
                 ("notify-dnd", "Do not disturb", "")]
LEVELS = ["Almost empty", "Low", "Half", "High", "Full"]


def _slot_label(key):
    m = re.fullmatch(r"ramp-capacity-(\d+)", key)
    if m:
        n = int(m.group(1))
        return f"Battery: {LEVELS[n] if n < len(LEVELS) else n + 1}"
    m = re.fullmatch(r"animation-charging-(\d+)", key)
    if m:
        return f"Charging, step {int(m.group(1)) + 1}"
    m = re.fullmatch(r"ramp-volume-(\d+)", key)
    if m:
        return f"Volume level {int(m.group(1)) + 1}"
    m = re.fullmatch(r"format-([a-z]+)-prefix", key)
    if m:
        return {"connected": "Connected", "disconnected": "Not connected", "mounted": "Icon",
                "unmounted": "Not mounted", "full": "Battery full", "muted": "Muted",
                "volume": "Sound on", "charging": "Charging", "discharging": "On battery"}.get(m.group(1), m.group(1).capitalize())
    return "Icon"


def _strip_font(v):
    return re.sub(r"%\{T-?\d*\}", "", v)


def item_icons(bar, name):
    """Every icon an item shows, as slots: [{"label", "kind", "path", "section", "key", "font_key", "icon", ...}].
    kind: "ini" (a key's value), "icons" (the bar's [icons] section), "arg" (an argument of the
    script the item runs). Empty if it has no icon of its own."""
    cfg = bar_config(bar)
    if name in SHARED_ICONS or name == "notifications":
        with open(cfg) as f:
            text = f.read()
        span = _section_body(text, "icons")
        body = text[span[0]:span[1]] if span else ""
        keys = dict(re.findall(r"(?m)^([\w-]+)\s*=\s*(.*)$", body))
        if name in SHARED_ICONS:
            return [{"label": "Icon", "kind": "icons", "path": cfg, "section": "icons", "key": name,
                     "font_key": f"{name}-font", "icon": keys.get(name, "").strip()}] if name in keys else []
        return [{"label": label, "kind": "icons", "path": cfg, "section": "icons", "key": k,
                 "font_key": "notify-font", "icon": keys.get(k, default).strip()} for k, label, default in NOTIFY_STATES]
    for fname in ("modules.ini", "config.ini"):
        path = os.path.join(BARS, bar, fname)
        try:
            with open(path) as f:
                text = f.read()
        except OSError:
            continue
        span = _section_body(text, f"module/{name}")
        if not span:
            continue
        body = text[span[0]:span[1]]
        pairs = re.findall(r"(?m)^([\w-]+)\s*=\s*(.*)$", body)
        keys = dict(pairs)
        slots = []
        # script items with their icons as arguments: VolumeBar "<icon>" "<muted icon>"
        m = re.match(r'(\S*VolumeBar)\s+"([^"]*)"\s+"([^"]*)"', keys.get("exec", ""))
        if m:
            for i, label in ((1, "Sound on"), (2, "Muted")):
                icon = _strip_font(m.group(i + 1))
                if _icon_only(icon):
                    slots.append({"label": label, "kind": "arg", "path": path, "section": f"module/{name}",
                                  "key": "exec", "arg": i, "font_key": None, "icon": icon})
            return slots
        for key, value in pairs:
            if key == "format-prefix" or re.fullmatch(r"format-[a-z]+-prefix", key) or key == "label" \
                    or re.fullmatch(r"(ramp|animation)-[a-z]+-\d+", key):
                icon = _icon_only(value)
                if icon:
                    slots.append({"label": _slot_label(key), "kind": "ini", "path": path, "section": f"module/{name}",
                                  "key": key, "font_key": f"{key}-font", "icon": icon})
        return slots
    return []


def item_icon(bar, name):
    """The first of an item's icons (or None)."""
    slots = item_icons(bar, name)
    return slots[0] if slots else None


def _set_keys(path, section, values):
    """Set keys in one [section] of an ini file (added at its end if missing)."""
    keep_original(path)
    with open(path) as f:
        text = f.read()
    span = _section_body(text, section)
    if not span:
        return
    body = text[span[0]:span[1]]
    for key, value in values.items():
        line = f"{key} = {value}"
        if re.search(rf"(?m)^{re.escape(key)}\s*=", body):
            body = re.sub(rf"(?m)^{re.escape(key)}\s*=.*$", lambda _m: line, body, count=1)
        else:
            body = body.rstrip("\n") + "\n" + line + "\n\n"
    with open(path, "w") as f:
        f.write(text[:span[0]] + body + text[span[1]:])


def set_item_icon(where, char, font):
    """Put a new icon in (font: which font-N draws it, plus one; 0 = any)."""
    path, section, key = where["path"], where["section"], where["key"]
    if where["kind"] == "icons":
        _set_keys(path, section, {key: char, where["font_key"]: str(font)})
        return
    with open(path) as f:
        text = f.read()
    span = _section_body(text, section)
    m = re.search(rf"(?m)^{re.escape(key)}\s*=\s*(.*)$", text[span[0]:span[1]])
    old = m.group(1) if m else ""
    if where["kind"] == "arg":
        # the icon travels with its font in the script's output: %{T<n>}icon%{T-}
        shown = f"%{{T{font}}}{char}%{{T-}}" if font else char
        args = re.match(r'(\S*VolumeBar)\s+"([^"]*)"\s+"([^"]*)"(.*)', old)
        parts = [args.group(2), args.group(3)]
        parts[where["arg"] - 1] = shown
        _set_keys(path, section, {key: f'{args.group(1)} "{parts[0]}" "{parts[1]}"{args.group(4)}'})
        return
    value = old.replace(where["icon"], char, 1) if old else char
    _set_keys(path, section, {key: value, where["font_key"]: str(font)})
