"""PySide6 GUI entry point for srna-win-target."""
from __future__ import annotations

import sys


def launch_gui() -> int:
    """Open the main window. Returns the Qt exit code."""
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise RuntimeError(
            "GUI dependency missing. Install with: pip install '.[gui]'"
        ) from exc

    from srna_win_target.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
