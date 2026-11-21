"""Window rules: bin/ExternalRules (what bspwm does with a new window of an
app: which workspace, floating, size...). Read and changed for the Windows
page. Only plain rules - one `result "..."` line - can be changed; rules
with their own logic are shown as they are."""

import os
import re

from . import rice
from .common import BSPDIR

FILE = os.path.join(BSPDIR, "bin", "ExternalRules")


class Rule:
    def __init__(self, names, kind, body, start, end):
        self.names = names          # ["firefox", "Navigator"]
        self.kind = kind            # "class" or "instance"
        self.body = body            # the lines between "name)" and ";;"
        self.start, self.end = start, end     # line numbers [start, end)
        code = "\n".join(ln for ln in body.split("\n") if ln.strip() and not ln.strip().startswith("#"))
        m = re.fullmatch(r'\s*result\s+"([^"]*)"\s*', code) if code.count("\n") == 0 else None
        self.simple = m is not None
        self.settings = parse(m.group(1)) if m else {}

    @property
    def name(self):
        return self.names[0]


def parse(text):
    """'state=floating desktop=^5 follow=on' -> dict"""
    out = {}
    for part in text.split():
        k, _, v = part.partition("=")
        if k == "center-on":                  # (typos in old rules: center-on, desktop^10)
            k, v = "center", "on"
        elif k.startswith("desktop^"):
            k, v = "desktop", k[len("desktop"):]
        out[k] = v
    return out


def dump(settings):
    order = ["desktop", "state", "focus", "follow", "center", "sticky", "rectangle"]
    keys = [k for k in order if k in settings] + [k for k in settings if k not in order]
    return " ".join(f"{k}={settings[k]}" for k in keys if settings[k] not in ("", None))


def _lines():
    with open(FILE) as f:
        return f.read().split("\n")


def load():
    """[Rule] of the `case "$class"` and `case "$instance"` blocks (first of duplicates)."""
    try:
        lines = _lines()
    except OSError:
        return []
    out, seen = [], set()
    kind, i = None, 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r'\s*case\s+"\$(class|instance)"\s+in', line)
        if m:
            kind = m.group(1)
            i += 1
            continue
        if kind and re.match(r"\s*esac\b", line):
            kind = None
            i += 1
            continue
        if kind:
            m = re.match(r"\s*([\w.*'\"|-]+)\)\s*$", line)
            if m:
                names = [n.strip() for n in m.group(1).split("|")]
                start, j, body = i, i + 1, []
                while j < len(lines) and not re.match(r"\s*;;\s*$", lines[j]) and not re.match(r"\s*esac\b", lines[j]) \
                        and not re.match(r"\s*[\w.*'\"|-]+\)\s*$", lines[j]):
                    body.append(lines[j])
                    j += 1
                end = j + 1 if j < len(lines) and re.match(r"\s*;;\s*$", lines[j]) else j
                key = (kind, names[0])
                if key not in seen:
                    seen.add(key)
                    out.append(Rule(names, kind, "\n".join(body), start, end))
                i = end
                continue
        i += 1
    return out


def _write(lines):
    rice.keep_original(FILE)
    with open(FILE, "w") as f:
        f.write("\n".join(lines))


def save(rule, settings):
    """Change a plain rule's settings."""
    lines = _lines()
    for n in range(rule.start + 1, rule.end):
        if re.match(r'\s*result\s+"', lines[n]):
            indent = re.match(r"\s*", lines[n]).group(0)
            lines[n] = f'{indent}result "{dump(settings)}"'
            break
    _write(lines)


def add(name, settings, kind="class"):
    lines = _lines()
    for i, line in enumerate(lines):
        if re.match(rf'\s*case\s+"\${kind}"\s+in', line):
            j = i + 1
            while j < len(lines) and not re.match(r"\s*esac\b", lines[j]):
                j += 1
            # (the entry before may lack its ";;")
            k = j - 1
            while k > i and not lines[k].strip():
                k -= 1
            if k > i and not re.match(r"\s*;;\s*$", lines[k]):
                lines.insert(k + 1, "\t\t;;")
                j += 1
            lines[j:j] = [f"\t{name})", "\t\t# (added in Control Center > Windows)",
                          f'\t\tresult "{dump(settings)}"', "\t\t;;"]
            _write(lines)
            return


def remove(rule):
    lines = _lines()
    del lines[rule.start:rule.end]
    _write(lines)


def has_original():
    return rice.has_original(FILE)


def reset():
    return rice.restore_original(FILE)
