from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from srna_win_target.backends.base import Backend, BackendResult
from srna_win_target.core.models import ChunkJob, LogicalCommand, PredictionHit, ToolConfig


@dataclass(frozen=True)
class RawToolOutput:
    tool_name: str
    chunk_id: str
    stdout: str
    stderr: str
    output_file: Path | None
    returncode: int = 0


class ToolRunner(ABC):
    name: str

    def __init__(self, config: ToolConfig):
        self.config = config

    @abstractmethod
    def check_ready(self) -> None:
        """Raise a clear error if executable/script dependencies are missing."""

    @abstractmethod
    def build_logical_command(self, chunk_job: ChunkJob) -> LogicalCommand:
        """Build a backend-agnostic command. The backend translates and runs it."""

    @abstractmethod
    def parse_output(self, output: RawToolOutput) -> list[PredictionHit]:
        """Parse one raw output into normalized hits."""

    def expected_output_file(self, chunk_job: ChunkJob) -> Path | None:
        return chunk_job.out_dir / f"{chunk_job.job_id}.{self.name}.txt"

    def run(
        self,
        chunk_job: ChunkJob,
        backend: Backend,
        log_file: Path | None = None,
    ) -> RawToolOutput:
        self.check_ready()
        chunk_job.out_dir.mkdir(parents=True, exist_ok=True)
        command = self.build_logical_command(chunk_job)
        result: BackendResult = backend.run(command, log_file=log_file)
        if result.returncode != 0:
            raise RuntimeError(
                f"{self.name} failed for {chunk_job.job_id} (rc={result.returncode}): "
                f"{result.stderr[:2000]}"
            )
        return RawToolOutput(
            tool_name=self.name,
            chunk_id=chunk_job.job_id,
            stdout=result.stdout,
            stderr=result.stderr,
            output_file=result.output_file,
            returncode=result.returncode,
        )

    def parse_many(self, outputs: list[RawToolOutput]) -> list[PredictionHit]:
        hits: list[PredictionHit] = []
        for output in outputs:
            hits.extend(self.parse_output(output))
        return hits

    def probe_version(self, backend: Backend) -> str:
        """Best-effort version string. Subclasses may override.

        Default: try executing `<exe> --version`; if that fails, return "unknown".
        """
        if not self.config.executable:
            return "unknown"
        try:
            from srna_win_target.core.models import LogicalCommand

            cmd = LogicalCommand(
                argv=[str(self.config.executable), "--version"],
                cwd=Path(".").resolve(),
                expected_output_file=None,
            )
            result = backend.run(cmd)
            text = (result.stdout or result.stderr).strip().splitlines()
            return text[0] if text else "unknown"
        except Exception:
            return "unknown"
