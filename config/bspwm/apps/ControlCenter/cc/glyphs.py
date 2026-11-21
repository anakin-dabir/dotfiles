"""Icon fonts the bar can use (Phosphor, Material Design Icons): their icons
by name, read straight from the font files (no extra Python packages)."""

import os
import struct
import subprocess
from functools import lru_cache

PHOSPHOR = "Phosphor"
MDI = "Material Design Icons Desktop"

# (set id, title, font family, which names)
SETS = [
    ("phosphor-bold", "Outline", PHOSPHOR, "bold"),
    ("phosphor", "Thin outline", PHOSPHOR, "regular"),
    ("phosphor-fill", "Filled", PHOSPHOR, "fill"),
    ("mdi", "Material", MDI, "all"),
]
_WEIGHTS = ("-bold", "-fill", "-thin", "-light", "-duotone")


def font_file(family):
    try:
        out = subprocess.run(["fc-match", family, "--format=%{family}|%{file}"],
                             capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    fam, _, path = out.partition("|")
    return path if family.lower() in fam.lower() and os.path.isfile(path) else None


def _read(path):
    """{codepoint: glyph name} for the icons (private-use area) in a TrueType font."""
    data = open(path, "rb").read()
    tables = {}
    for i in range(struct.unpack(">H", data[4:6])[0]):
        tag, _c, off, ln = struct.unpack(">4sIII", data[12 + 16 * i:28 + 16 * i])
        tables[tag.decode("latin1")] = (off, ln)
    cmap = {}
    off = tables["cmap"][0]
    for i in range(struct.unpack(">H", data[off + 2:off + 4])[0]):
        _pid, _eid, so = struct.unpack(">HHI", data[off + 4 + 8 * i:off + 12 + 8 * i])
        t = off + so
        fmt = struct.unpack(">H", data[t:t + 2])[0]
        if fmt == 12:
            for g in range(struct.unpack(">I", data[t + 12:t + 16])[0]):
                s, e, gid = struct.unpack(">III", data[t + 16 + 12 * g:t + 28 + 12 * g])
                for c in range(s, e + 1):
                    cmap.setdefault(c, gid + c - s)
        elif fmt == 4:
            segx2 = struct.unpack(">H", data[t + 6:t + 8])[0]
            seg = segx2 // 2
            ends = struct.unpack(f">{seg}H", data[t + 14:t + 14 + segx2])
            starts = struct.unpack(f">{seg}H", data[t + 16 + segx2:t + 16 + 2 * segx2])
            deltas = struct.unpack(f">{seg}h", data[t + 16 + 2 * segx2:t + 16 + 3 * segx2])
            rpos = t + 16 + 3 * segx2
            roffs = struct.unpack(f">{seg}H", data[rpos:rpos + segx2])
            for k in range(seg):
                for c in range(starts[k], ends[k] + 1):
                    if c == 0xFFFF:
                        continue
                    if roffs[k] == 0:
                        gid = (c + deltas[k]) & 0xFFFF
                    else:
                        p = rpos + 2 * k + roffs[k] + 2 * (c - starts[k])
                        gid = struct.unpack(">H", data[p:p + 2])[0]
                        gid = (gid + deltas[k]) & 0xFFFF if gid else 0
                    cmap.setdefault(c, gid)
    names = {}
    off, ln = tables.get("post", (0, 0))
    if off and struct.unpack(">I", data[off:off + 4])[0] == 0x00020000:
        ng = struct.unpack(">H", data[off + 32:off + 34])[0]
        idx = struct.unpack(f">{ng}H", data[off + 34:off + 34 + 2 * ng])
        p, extra = off + 34 + 2 * ng, []
        while p < off + ln:
            n = data[p]
            extra.append(data[p + 1:p + 1 + n].decode("latin1"))
            p += 1 + n
        for gid, ix in enumerate(idx):
            if ix >= 258 and ix - 258 < len(extra):
                names[gid] = extra[ix - 258]
    out = {}
    for c, g in cmap.items():
        if c >= 0xE000 and g in names and not names[g].startswith(("uni", ".")):
            out[c] = names[g]
    return out


@lru_cache(maxsize=None)
def font_icons(family):
    path = font_file(family)
    try:
        return _read(path) if path else {}
    except (OSError, KeyError, struct.error, IndexError):
        return {}


@lru_cache(maxsize=None)
def icon_set(set_id):
    """[(name, char)] of one set, by name, one char per name."""
    _sid, _title, family, which = next(s for s in SETS if s[0] == set_id)
    seen, out = set(), []
    for c, name in sorted(font_icons(family).items()):
        if which == "bold" and name.endswith("-bold"):
            name = name[:-5]
        elif which == "fill" and name.endswith("-fill"):
            name = name[:-5]
        elif which == "regular" and not name.endswith(_WEIGHTS):
            pass
        elif which != "all":
            continue
        if name not in seen:
            seen.add(name)
            out.append((name, chr(c)))
    return sorted(out)


def family_of(char):
    """Which icon font draws this char (Phosphor or Material), or None."""
    c = ord(char)
    for family in (MDI, PHOSPHOR) if c >= 0xF0000 else (PHOSPHOR, MDI):
        if c in font_icons(family):
            return family
    return None
