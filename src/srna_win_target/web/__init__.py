"""FastAPI-based web UI for srna-win-target."""
from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser


def _find_free_port(host: str, start: int, end: int) -> int:
    """Return the first free port in [start, end] on `host`, else `start`."""
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    return start


def launch_web(host: str = "127.0.0.1", port: int = 5173, open_browser: bool = True) -> None:
    """Start the local web server. Defaults to http://127.0.0.1:5173, but if
    that port is taken, walks forward to find a free one (5173..5193)."""
    try:
        import uvicorn  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Web dependency missing. Install with: pip install '.[web]'"
        ) from exc

    from srna_win_target.web.server import app  # lazy import — tests skip the cost

    chosen_port = _find_free_port(host, port, port + 20)
    url = f"http://{host}:{chosen_port}/"
    banner = (
        "\n"
        "  +----------------------------------------------------+\n"
        "  |  sRNA Target Predictor                             |\n"
        "  |  Server running.                                   |\n"
        f"  |  Open in your browser:  {url:<26} |\n"
        "  |  Press Ctrl+C in this window to stop.              |\n"
        "  +----------------------------------------------------+\n"
    )
    # Write banner safely: encode to UTF-8 with replacement so Windows
    # GBK consoles don't raise UnicodeEncodeError, then also write a
    # log file next to the exe so users can find the URL even when the
    # process is launched without a visible console (pythonw / GUI subsystem).
    try:
        sys.stdout.buffer.write(banner.encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()
    except AttributeError:
        # sys.stdout has no .buffer in some frozen environments.
        try:
            print(banner, flush=True)
        except Exception:
            pass
    # Log file next to the exe (always writable, even in GUI-subsystem builds).
    import pathlib
    try:
        log_path = pathlib.Path(sys.executable).parent / "srna-server.log"
        log_path.write_text(banner, encoding="utf-8")
    except Exception:
        pass

    if open_browser:
        # Wait until uvicorn has bound the port before pointing the browser at
        # it, otherwise the browser races the server and the user sees a
        # "cannot connect" error page that never reloads.
        def _open_when_ready():
            for _ in range(30):  # up to 6 seconds
                try:
                    with socket.create_connection((host, chosen_port), timeout=0.5):
                        break
                except OSError:
                    time.sleep(0.2)
            try:
                webbrowser.open_new_tab(url)
            except Exception:  # pragma: no cover
                pass

        threading.Thread(target=_open_when_ready, daemon=True).start()

    import uvicorn
    uvicorn.run(app, host=host, port=chosen_port, log_level="info")
