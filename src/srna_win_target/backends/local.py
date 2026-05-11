from __future__ import annotations

import subprocess
from pathlib import Path

from srna_win_target.backends.base import Backend, BackendResult
from srna_win_target.core.models import LogicalCommand


class LocalBackend(Backend):
    name = "local"

    def run(self, command: LogicalCommand, log_file: Path | None = None) -> BackendResult:
        command.cwd.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            command.argv,
            cwd=str(command.cwd),
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
                f"$ {' '.join(command.argv)}\n"
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
