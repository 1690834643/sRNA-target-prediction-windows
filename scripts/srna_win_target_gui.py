"""GUI entry point used by PyInstaller to produce the Windows binary."""
from __future__ import annotations

import sys

from srna_win_target.gui import launch_gui

if __name__ == "__main__":
    sys.exit(launch_gui())
