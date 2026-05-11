"""Web-UI entry point used by PyInstaller to produce the Windows binary.

Double-clicking the resulting .exe starts the FastAPI server on
127.0.0.1:5173 and pops the default browser open to that URL. Overrides:

    SRNA_WEB_HOST       bind host (default 127.0.0.1)
    SRNA_WEB_PORT       bind port (default 5173)
    SRNA_WEB_NO_BROWSER set to 1 to suppress auto-opening the browser
"""
from __future__ import annotations

import multiprocessing
import os
import sys


def main() -> int:
    # Critical for PyInstaller-frozen multiprocessing apps: prevents child
    # workers from re-running the whole bootstrap (which would otherwise
    # cascade into recursive bind attempts on Windows).
    multiprocessing.freeze_support()

    from srna_win_target.web import launch_web

    host = os.environ.get("SRNA_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("SRNA_WEB_PORT", "5173"))
    no_browser = os.environ.get("SRNA_WEB_NO_BROWSER") == "1"
    return launch_web(host=host, port=port, open_browser=not no_browser) or 0


if __name__ == "__main__":
    sys.exit(main())
