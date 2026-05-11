from __future__ import annotations

import re
import subprocess
from pathlib import Path, PureWindowsPath

from srna_win_target.backends.base import Backend, BackendResult
from srna_win_target.core.models import LogicalCommand

_WIN_DRIVE_RE = re.compile(r"^([A-Za-z]):[\\/]")


class WSLBackend(Backend):
    """Run commands inside a default WSL distribution.

    Translates `C:\\path\\to\\file` (or `C:/path/to/file`) into `/mnt/c/path/to/file`
    so Linux tools inside WSL can read host files. Already-Linux paths pass through.
    """

    name = "wsl"

    def __init__(self, wsl_executable: str = "wsl", distro: str | None = None) -> None:
        self.wsl_executable = wsl_executable
        self.distro = distro

    def translate_path(self, path: Path) -> str:
        s = str(path)
        match = _WIN_DRIVE_RE.match(s)
        if match:
            drive = match.group(1).lower()
            rest = s[match.end():].replace("\\", "/")
            return f"/mnt/{drive}/{rest}"
        # Already POSIX-like; assume caller passed a WSL-visible path.
        return s.replace("\\", "/")

    def _wsl_argv(self, inner_argv: list[str], cwd: Path) -> list[str]:
        prefix = [self.wsl_executable]
        if self.distro:
            prefix += ["-d", self.distro]
        prefix += ["--cd", self.translate_path(cwd), "--"]
        return prefix + [self._translate_token(tok) for tok in inner_argv]

    def _translate_token(self, token: str) -> str:
        if _WIN_DRIVE_RE.match(token):
            return self.translate_path(Path(token))
        return token

    def run(self, command: LogicalCommand, log_file: Path | None = None) -> BackendResult:
        command.cwd.mkdir(parents=True, exist_ok=True)
        argv = self._wsl_argv(command.argv, command.cwd)
        proc = subprocess.run(
            argv,
            text=True,
            capture_output=True,
            shell=False,
            check=False,
            env=command.env,
        )

        if command.capture_stdout_to is not None:
            command.capture_stdout_to.parent.mkdir(parents=True, exist_ok=True)
            command.capture_stdout_to.write_text(proc.stdout, encoding="utf-8")

        if log_file is not None:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            log_file.write_text(
                f"$ {' '.join(argv)}\n"
                f"# returncode={proc.returncode}\n"
                f"--- stdout ---\n{proc.stdout}\n"
                f"--- stderr ---\n{proc.stderr}\n",
                encoding="utf-8",
            )

        return BackendResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            output_file=command.expected_output_file,
            log_file=log_file,
        )
