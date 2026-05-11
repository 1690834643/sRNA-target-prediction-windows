from __future__ import annotations

import sys
from pathlib import Path

import pytest

from srna_win_target.backends.local import LocalBackend
from srna_win_target.backends.wsl import WSLBackend
from srna_win_target.core.models import LogicalCommand


def test_wsl_translate_windows_drive_paths() -> None:
    b = WSLBackend()
    assert b.translate_path(Path(r"C:\Users\foo\bar.txt")) == "/mnt/c/Users/foo/bar.txt"
    assert b.translate_path(Path("D:/data/x.fa")) == "/mnt/d/data/x.fa"


def test_wsl_translate_passes_posix_paths_through() -> None:
    b = WSLBackend()
    assert b.translate_path(Path("/home/user/file")) == "/home/user/file"
    assert b.translate_path(Path("relative/path.fa")) == "relative/path.fa"


def test_local_backend_runs_command(tmp_path: Path) -> None:
    backend = LocalBackend()
    log = tmp_path / "log.txt"
    cmd = LogicalCommand(
        argv=[sys.executable, "-c", "print('hello')"],
        cwd=tmp_path,
        expected_output_file=None,
    )
    result = backend.run(cmd, log_file=log)
    assert result.returncode == 0
    assert "hello" in result.stdout
    assert log.exists()
    assert "hello" in log.read_text(encoding="utf-8")


def test_local_backend_redirects_stdout_to_capture_file(tmp_path: Path) -> None:
    backend = LocalBackend()
    capture = tmp_path / "captured.txt"
    cmd = LogicalCommand(
        argv=[sys.executable, "-c", "print('captured-line')"],
        cwd=tmp_path,
        expected_output_file=capture,
        capture_stdout_to=capture,
    )
    result = backend.run(cmd)
    assert result.returncode == 0
    assert capture.exists()
    assert "captured-line" in capture.read_text(encoding="utf-8")


def test_local_backend_returns_nonzero_for_failing_command(tmp_path: Path) -> None:
    backend = LocalBackend()
    cmd = LogicalCommand(
        argv=[sys.executable, "-c", "import sys; sys.exit(7)"],
        cwd=tmp_path,
        expected_output_file=None,
    )
    result = backend.run(cmd)
    assert result.returncode == 7


def test_wsl_argv_construction_includes_cd_and_translation() -> None:
    b = WSLBackend()
    argv = b._wsl_argv(["my_tool", r"C:\input.fa"], cwd=Path(r"C:\work"))
    assert argv[0] == "wsl"
    assert "--cd" in argv and "/mnt/c/work" in argv
    # tool stays as-is, drive-style argument is translated
    assert "my_tool" in argv
    assert "/mnt/c/input.fa" in argv
