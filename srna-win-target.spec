# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the srna-win-target Windows GUI binary.

Build with:
    python scripts/build_windows_exe.py

The result lands at dist/srna-win-target.exe (Windows) or dist/srna-win-target
on Linux/macOS (host-native binary, useful for spec validation only).
"""
from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH)  # noqa: F821 — provided by PyInstaller

a = Analysis(
    [str(ROOT / "scripts" / "srna_win_target_gui.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[
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
        "srna_win_target.gui",
        "srna_win_target.gui.main_window",
        "srna_win_target.gui.worker",
        "srna_win_target.parallel.scheduler",
        "srna_win_target.parallel.manifest",
        "srna_win_target.results.merge",
        "srna_win_target.results.streaming_writer",
        "srna_win_target.results.visualize",
        "srna_win_target.tools.miranda",
        "srna_win_target.tools.rnahybrid",
        "srna_win_target.tools.pita",
        "srna_win_target.tools.intarna",
        "srna_win_target.tools.registry",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # PySide6 already provides a Qt event loop; tkinter is dead weight.
        "tkinter",
        # We do not use Jupyter / IPython at runtime.
        "IPython",
        "notebook",
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
    name="srna-win-target",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                       # UPX often misbehaves with PySide6
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                   # windowed app — no console pop-up
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
