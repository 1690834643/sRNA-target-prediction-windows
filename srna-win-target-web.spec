# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the srna-win-target *web-UI* Windows binary.

Bundles FastAPI + uvicorn + the prediction pipeline; excludes PySide6 so the
exe stays small (~40–80 MB instead of ~200 MB). Double-clicking the result
starts the local server at http://127.0.0.1:5173 and opens the browser.

Build with:
    python scripts/build_windows_exe.py web
"""
from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH)  # noqa: F821 — provided by PyInstaller

a = Analysis(
    [str(ROOT / "scripts" / "srna_win_target_web.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[
        (str(ROOT / "src" / "srna_win_target" / "web" / "static"), "srna_win_target/web/static"),
        (str(ROOT / "examples"), "examples"),
    ],
    hiddenimports=[
        "srna_win_target",
        "srna_win_target.backends",
        "srna_win_target.backends.local",
        "srna_win_target.backends.wsl",
        "srna_win_target.cli",
        "srna_win_target.cli.app",
        "srna_win_target.cli._selftest",
        "srna_win_target.core",
        "srna_win_target.core.models",
        "srna_win_target.core.pipeline",
        "srna_win_target.data.fasta_split",
        "srna_win_target.data.format_check",
        "srna_win_target.parallel.scheduler",
        "srna_win_target.parallel.manifest",
        "srna_win_target.results.merge",
        "srna_win_target.results.streaming_writer",
        "srna_win_target.results.visualize",
        "srna_win_target.results.html_report",
        "srna_win_target.results.visualize_alignment",
        "srna_win_target.tools.miranda",
        "srna_win_target.tools.rnahybrid",
        "srna_win_target.tools.pita",
        "srna_win_target.tools.intarna",
        "srna_win_target.tools.registry",
        "srna_win_target.web",
        "srna_win_target.web.server",
        "srna_win_target.web.discover",
        # uvicorn protocols that PyInstaller's static analyser misses.
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.websockets_impl",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        # tkinter is used by /api/pick-file to drive a native file dialog.
        "tkinter",
        "tkinter.filedialog",
        "tkinter.font",
        "tkinter.ttk",
        "_tkinter",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "PySide6", "PyQt5", "PyQt6", "shiboken6",  # GUI not bundled in web exe
        "IPython", "notebook",
        "matplotlib_venn", "upsetplot",            # plots are an optional path
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="srna-win-target-web",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,        # show uvicorn log — familiar Vite-style UX
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
