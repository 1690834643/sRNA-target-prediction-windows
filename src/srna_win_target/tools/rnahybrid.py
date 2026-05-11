from __future__ import annotations

from pathlib import Path

from srna_win_target.core.models import ChunkJob, LogicalCommand, PredictionHit
from srna_win_target.tools.base import RawToolOutput, ToolRunner


def _parse_rnahybrid_text(text: str) -> list[dict]:
    hits: list[dict] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        fields = line.split(":")
        if len(fields) != 11:
            continue

        try:
            energy = float(fields[4])
            pvalue = float(fields[5])
            start = int(fields[6])
        except ValueError:
            continue

        hits.append(
            {
                "mirna_id": fields[2],
                "target_id": fields[0],
                "start": start,
                "end": None,
                "score": None,
                "energy": energy,
                "pvalue": pvalue,
            }
        )
    return hits


class RNAhybridRunner(ToolRunner):
    name = "rnahybrid"

    def check_ready(self) -> None:
        if not self.config.executable or not Path(self.config.executable).exists():
            raise FileNotFoundError("RNAhybrid executable is not configured or does not exist")

    def build_logical_command(self, chunk_job: ChunkJob) -> LogicalCommand:
        params = self.config.parameters
        output_file = self.expected_output_file(chunk_job)
        argv = [
            str(self.config.executable),
            "-c",  # compact CSV-like output for parsing
            "-s",
            str(params.get("set", "3utr_human")),
            "-e",
            str(params.get("energy_cutoff", -20)),
            "-p",
            str(params.get("pvalue_cutoff", 0.1)),
            "-m",
            str(params.get("max_target_length", 100000)),
            "-t",
            str(chunk_job.target_chunk),
            "-q",
            str(chunk_job.mirna_fasta),
        ]
        return LogicalCommand(
            argv=argv,
            cwd=chunk_job.out_dir,
            expected_output_file=output_file,
            capture_stdout_to=output_file,
        )

    def parse_output(self, output: RawToolOutput) -> list[PredictionHit]:
        if output.output_file and output.output_file.exists():
            text = output.output_file.read_text(encoding="utf-8", errors="replace")
        else:
            text = output.stdout
        return [
            PredictionHit(
                tool=self.name,
                raw_file=output.output_file,
                chunk_id=output.chunk_id,
                **fields,
            )
            for fields in _parse_rnahybrid_text(text)
        ]
