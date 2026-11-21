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
    return '"' + re.sub(r'(["\\$`])', r"\\\1", str(value)) + '"'


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
