"""Which sections the bar dropdowns show, and in what order.

Saved in config/dropdowns.json, which BarPanel hands to eww as bp_show:
  {"<section>": true/false, ...,               which sections are shown
   "<card>": true/false,                        a card with rows (Network's
                                                connections, Battery's switches)
                                                is shown if any row is
   "order": {"<dropdown>": [...], "<card>": [...]},
   "first": {"<card>": "<row>"},                the card's first shown row
                                                (no divider line above it)
   "any": {"<dropdown>": true/false}}           anything shown below the header
"""

import json
import os

from .common import BSPDIR

FILE = os.path.join(BSPDIR, "config", "dropdowns.json")

# (dropdown, title, [(unit, name) or (card, [(row, name), ...])])
DROPDOWNS = [
    ("cpu", "Processor", [
        ("cpu_graph", "Usage graph and cores"),
        ("cpu_stats", "Temperature, load and threads"),
        ("cpu_apps", "Apps using the most CPU"),
        ("cpu_button", "System Monitor button"),
    ]),
    ("memory", "Memory", [
        ("memory_graph", "Usage graph and swap"),
        ("memory_apps", "Apps using the most memory"),
        ("memory_button", "System Monitor button"),
    ]),
    ("disk", "Storage", [
        ("disk_clean", "Clean up (caches, unused packages)"),
        ("disk_buttons", "Files and Analyze buttons"),
    ]),
    ("sound", "Sound", [
        ("sound_volume", "Volume slider"),
        ("sound_output", "Output devices"),
        ("sound_mic", "Microphone slider"),
        ("sound_button", "Sound Settings button"),
    ]),
    ("network", "Network", [
        ("network_speed", "Download and upload speed"),
        ("network_rows", [
            ("network_airplane", "Airplane mode"),
            ("network_wifi", "Wi-Fi (with its list of networks)"),
            ("network_bluetooth", "Bluetooth (with its list of devices)"),
        ]),
        ("network_button", "Network Settings button"),
    ]),
    ("battery", "Battery", [
        ("battery_mode", "Power mode"),
        ("battery_brightness", "Brightness slider"),
        ("battery_toggles", [
            ("battery_night", "Night light"),
            ("battery_awake", "Keep awake"),
        ]),
        ("battery_buttons", "Settings and Power Off buttons"),
    ]),
]

NAMES = {}           # section -> name
CARDS = {}           # card -> [rows]
DEFAULT_ORDER = {}
for _dd, _title, _units in DROPDOWNS:
    DEFAULT_ORDER[_dd] = [u for u, _x in _units]
    for _u, _x in _units:
        if isinstance(_x, list):
            CARDS[_u] = [r for r, _n in _x]
            DEFAULT_ORDER[_u] = list(CARDS[_u])
            NAMES.update(dict(_x))
        else:
            NAMES[_u] = _x
SECTIONS = list(NAMES)


def _fix_order(saved):
    """A saved order with any missing/unknown entries put right."""
    out = {}
    for key, default in DEFAULT_ORDER.items():
        got = [x for x in (saved or {}).get(key, []) if x in default]
        for x in default:                 # new sections go where they are by default
            if x not in got:
                later = [y for y in default[default.index(x) + 1:] if y in got]
                got.insert(got.index(later[0]) if later else len(got), x)
        out[key] = got
    return out


def build(shown, order):
    """The full bp_show value for eww."""
    out = {k: bool(shown.get(k, True)) for k in SECTIONS}
    order = _fix_order(order)
    first = {}
    for card, rows in CARDS.items():
        out[card] = any(out[r] for r in rows)
        first[card] = next((r for r in order[card] if out[r]), "")
    out["order"] = order
    out["first"] = first
    # Does a dropdown show anything below its header? (no empty gap if not)
    out["any"] = {dd: any(out[u] for u in order[dd]) for dd, _t, _u in DROPDOWNS}
    return out


def load():
    """(shown, order) from the saved file."""
    try:
        with open(FILE) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    shown = {k: bool(data.get(k, True)) for k in SECTIONS}
    return shown, _fix_order(data.get("order"))


def save(shown, order):
    data = build(shown, order)
    with open(FILE, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return data
