from __future__ import annotations

from pathlib import Path

from srna_win_target.core.models import ChunkJob, LogicalCommand, PredictionHit
from srna_win_target.tools.base import RawToolOutput, ToolRunner


class IntaRNARunner(ToolRunner):
    name = "intarna"

    def check_ready(self) -> None:
        if not self.config.executable or not Path(self.config.executable).exists():
            raise FileNotFoundError("IntaRNA executable is not configured or does not exist")

    def build_logical_command(self, chunk_job: ChunkJob) -> LogicalCommand:
        output_file = self.expected_output_file(chunk_job)
        argv = [
            str(self.config.executable),
            "-q",
            str(chunk_job.mirna_fasta),
            "-t",
            str(chunk_job.target_chunk),
            "--outMode",
            "C",
            "--out",
            str(output_file),
        ]
        return LogicalCommand(
            argv=argv,
            cwd=chunk_job.out_dir,
            expected_output_file=output_file,
        )

    def parse_output(self, output: RawToolOutput) -> list[PredictionHit]:
        # Implement after the first three tools land.
        return []
