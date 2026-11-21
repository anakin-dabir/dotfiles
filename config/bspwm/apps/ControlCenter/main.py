#!/usr/bin/env python3
"""Control Center for this bspwm rice. Started by bin/ControlCenter."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Repaint the whole window each frame. GTK otherwise repaints only what
# changed, and the tops of letters of a replaced title can stay behind.
# Cheap for a settings window.
os.environ.setdefault("GSK_DEBUG", "full-redraw")

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from cc.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
