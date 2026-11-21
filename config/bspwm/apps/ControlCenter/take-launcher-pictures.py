#!/usr/bin/env python3
"""Take the pictures of the app menu styles for Control Center > Customize
(see cc/launchershots.py). Runs on its own, so closing the Control Center
doesn't stop it; only one runs at a time."""

import fcntl
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")

from cc import launchershots  # noqa: E402
from cc.common import CACHE  # noqa: E402

os.makedirs(os.path.join(CACHE, "launcher"), exist_ok=True)
lock = open(os.path.join(CACHE, "launcher", ".lock"), "w")
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    sys.exit(0)               # already running
launchershots.capture()
