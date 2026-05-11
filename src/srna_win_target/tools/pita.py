from __future__ import annotations

import re
from pathlib import Path

from srna_win_target.core.models import ChunkJob, LogicalCommand, PredictionHit
from srna_win_target.tools.base import RawToolOutput, ToolRunner


def _parse_pita_text(text: str) -> list[dict]:
    lines = [line.strip() for line in text.splitlines()]
    content_lines = [line for line in lines if line and not line.startswith("#")]
    header: list[str] | None = None
    header_index: int | None = None

    for index, line in enumerate(content_lines):
        columns = line.split("\t")
        normalized = [column.strip().lower() for column in columns]
        if "refseq" in normalized or ("microrna" in normalized and "ddg" in normalized):
            header = columns
            header_index = index
            break

    if header is None or header_index is None:
        return []

    column_index = {column.strip().lower(): index for index, column in enumerate(header)}
    # Target column: prefer RefSeq (TargetScan-style) then UTR (PITA-script-style),
    # else fall back to the first column.
    if "refseq" in column_index:
        target_index = column_index["refseq"]
    elif "utr" in column_index:
        target_index = column_index["utr"]
    else:
        target_index = 0
    mirna_index = column_index.get("microrna")
    ddg_index = column_index.get("ddg")
    # Start position can come as Position(s)/Position (TargetScan-style) or
    # an explicit Start column (pita_prediction.pl).
    position_index = column_index.get(
        "position(s)",
        column_index.get("position", column_index.get("start")),
    )
    end_index = column_index.get("end")
    duplex_index = column_index.get("dgduplex")
    if mirna_index is None or ddg_index is None:
        return []

    hits: list[dict] = []
    for line in content_lines[header_index + 1 :]:
        fields = line.split("\t")
        required_index = max(target_index, mirna_index, ddg_index)
        if len(fields) <= required_index:
            continue

        try:
            score = float(fields[ddg_index])
        except ValueError:
            continue

        energy = None
        if duplex_index is not None and len(fields) > duplex_index and fields[duplex_index]:
            try:
                energy = float(fields[duplex_index])
            except ValueError:
                energy = None

        start = None
        if position_index is not None and len(fields) > position_index:
            match = re.search(r"\d+", fields[position_index])
            if match:
                start = int(match.group(0))

        end = None
        if end_index is not None and len(fields) > end_index:
            match = re.search(r"\d+", fields[end_index])
            if match:
                end = int(match.group(0))

        hits.append(
            {
                "mirna_id": fields[mirna_index],
                "target_id": fields[target_index],
                "start": start,
                "end": end,
                "score": score,
                "energy": energy,
                "pvalue": None,
            }
        )
    return hits


class PitaRunner(ToolRunner):
    name = "pita"

    def check_ready(self) -> None:
        script = self.config.parameters.get("script")
        perl = self.config.parameters.get("perl", "perl")
        if not script or not Path(str(script)).exists():
            raise FileNotFoundError("PITA script path is not configured or does not exist")
        if not perl:
            raise FileNotFoundError("Perl executable is not configured")

    def build_logical_command(self, chunk_job: ChunkJob) -> LogicalCommand:
        params = self.config.parameters
        script = Path(str(params["script"])).resolve()
        prefix = (chunk_job.out_dir / chunk_job.job_id).resolve()

        # PITA's pita_prediction.pl + lib/*.pl scripts pass paths through perl
        # `system("cat $prefix | ... > $prefix_out")` shell pipelines. Spaces
        # in interpolated paths reliably break those pipelines. Non-ASCII
        # paths happen to work with Strawberry Perl 5.42 + bundled MSYS
        # coreutils + modern cmd.exe (verified on a Chinese-character
        # Windows desktop path, output bit-exact with Linux reference), so
        # we only refuse on spaces. The space case is still hard-blocked
        # because there is no portable shell-quoting fix in the perl source.
        for label, p in (("mirna FASTA", chunk_job.mirna_fasta),
                         ("targets FASTA", chunk_job.target_chunk),
                         ("output prefix", prefix)):
            if " " in str(p):
                raise RuntimeError(
                    f"PITA {label} 路径包含空格 ({p!r})；PITA 的 perl 脚本会把"
                    " 它拼进 POSIX shell 管道而不加引号。请换一个不含空格的输出文件夹，"
                    "或在 Advanced 把 Backend 切到 'wsl'。"
                )
        # PITA's lib/*.pl scripts `require "lib/<name>.pl"` relative to cwd,
        # and pita_run.pl invokes them via shell pipes — so the working
        # directory must be the bundle dir that contains pita_prediction.pl
        # + lib/. Inputs/outputs are passed as absolute paths.
        argv = [
            str(params.get("perl", "perl")),
            # Strawberry Perl 5.42 (and any Perl 5.26+) excludes "." from @INC
            # by default. PITA's `require "lib/foo.pl"` calls rely on the
            # cwd being on @INC, so we add the bundle dir explicitly.
            "-I",
            str(script.parent),
            str(script),
            "-mir",
            str(Path(chunk_job.mirna_fasta).resolve()),
            "-utr",
            str(Path(chunk_job.target_chunk).resolve()),
            "-prefix",
            str(prefix),
        ]
        # On Windows, cmd.exe does not search the cwd when resolving
        # bare executable names in Perl's system() calls.  Prepend the
        # script directory so that RNAduplex.exe, RNAddG4.exe, and the
        # lib/*.pl helper scripts (also invoked as bare names) are all
        # found without absolute-path changes to the Perl sources.
        import os
        import sys
        script_dir = str(script.parent)
        base_path = os.environ.get("PATH", "")
        augmented_path = os.pathsep.join([
            str(script.parent / "bin"),
            str(script.parent / "perl" / "bin"),
            str(script.parent),
            base_path,
        ])
        run_env = {**os.environ, "PATH": augmented_path}

        return LogicalCommand(
            argv=argv,
            cwd=script.parent,
            env=run_env,
            expected_output_file=self.expected_output_file(chunk_job),
        )

    def expected_output_file(self, chunk_job: ChunkJob) -> Path | None:
        # PITA's pita_prediction.pl writes <prefix>_pita_results.tab.
        return chunk_job.out_dir / f"{chunk_job.job_id}_pita_results.tab"

    def probe_version(self, backend) -> str:
        script = self.config.parameters.get("script")
        if script:
            return f"pita-script:{Path(str(script)).name}"
        return "unknown"

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
            for fields in _parse_pita_text(text)
        ]
