from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from srna_win_target.core.models import LogicalCommand


@dataclass(frozen=True)
class BackendResult:
    returncode: int
    stdout: str
    stderr: str
    output_file: Path | None
    log_file: Path | None


class Backend(ABC):
    """Translates a LogicalCommand into a real subprocess invocation."""

    name: str

    @abstractmethod
    def run(self, command: LogicalCommand, log_file: Path | None = None) -> BackendResult:
        """Execute the command. If `log_file` is given, write stderr there."""

    def translate_path(self, path: Path) -> str:
        """Translate a host path into the backend's view of the same file.

        Default behaviour is identity. WSL/Docker backends override this.
        """
        return str(path)
