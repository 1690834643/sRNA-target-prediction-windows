from __future__ import annotations

from pathlib import Path

from srna_win_target.core.models import ChunkJob, LogicalCommand, PredictionHit
from srna_win_target.tools.base import RawToolOutput, ToolRunner


def _parse_miranda_text(text: str) -> list[dict]:
    hits: list[dict] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith(">") or line.startswith(">>"):
            continue

        fields = line[1:].strip().split()
        if len(fields) < 11:
            continue

        try:
            score = float(fields[2])
            energy = float(fields[3])
            ref_start = int(fields[6])
            ref_end = int(fields[7])
        except (ValueError, IndexError):
            continue

        hits.append(
            {
                "mirna_id": fields[0],
                "target_id": fields[1],
                "start": ref_start,
                "end": ref_end,
                "score": score,
                "energy": energy,
                "pvalue": None,
            }
        )
    return hits


class MirandaRunner(ToolRunner):
    name = "miranda"

    def check_ready(self) -> None:
        if not self.config.executable or not Path(self.config.executable).exists():
            raise FileNotFoundError("miRanda executable is not configured or does not exist")

    def build_logical_command(self, chunk_job: ChunkJob) -> LogicalCommand:
        params = self.config.parameters
        output_file = self.expected_output_file(chunk_job)
        argv = [
            str(self.config.executable),
            str(chunk_job.mirna_fasta),
            str(chunk_job.target_chunk),
            "-sc",
            str(params.get("score_cutoff", 140)),
            "-en",
            str(params.get("energy_cutoff", -20)),
            "-out",
            str(output_file),
        ]
        if params.get("strict"):
            argv.append("-strict")
        return LogicalCommand(
            argv=argv,
            cwd=chunk_job.out_dir,
            expected_output_file=output_file,
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
            for fields in _parse_miranda_text(text)
        ]
