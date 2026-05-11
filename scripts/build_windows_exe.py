"""Build a srna-win-target Windows binary with PyInstaller.

Cross-platform wrapper. PyInstaller does NOT cross-compile, so to produce a
Windows .exe this script must be run on Windows. Running on Linux/macOS
produces a host-native binary that doubles as a smoke check that the spec
file resolves all imports.

Two flavours are available:

    python scripts/build_windows_exe.py            # default: web (~40–80 MB)
    python scripts/build_windows_exe.py web        # FastAPI + browser UI
    python scripts/build_windows_exe.py gui        # PySide6 native window (~200 MB)

Prerequisites:
    pip install . pyinstaller        # plus [web] or [gui] depending on flavour

Output goes to dist/.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

SPECS = {
    "web": "srna-win-target-web.spec",
    "gui": "srna-win-target.spec",
}


def main(argv: list[str]) -> int:
    flavour = argv[1] if len(argv) > 1 else "web"
    if flavour not in SPECS:
        print(f"Unknown flavour: {flavour}. Choose: {', '.join(SPECS)}", file=sys.stderr)
        return 2

    root = Path(__file__).resolve().parent.parent
    spec = root / SPECS[flavour]
    if not spec.exists():
        print(f"Missing spec file: {spec}", file=sys.stderr)
        return 2

    for directory in ("build", "dist"):
        target = root / directory
        if target.exists():
            shutil.rmtree(target)

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", str(spec)]
    print("Running:", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(root))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
