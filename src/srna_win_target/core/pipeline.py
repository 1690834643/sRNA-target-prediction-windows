from __future__ import annotations

from pathlib import Path
from typing import Callable

from srna_win_target.backends import build_backend
from srna_win_target.backends.base import Backend
from srna_win_target.core.models import PredictionJob, ProgressEvent
from srna_win_target.data.fasta_split import split_fasta
from srna_win_target.data.format_check import normalize_input_fasta
from srna_win_target.parallel.manifest import RunManifest
from srna_win_target.parallel.scheduler import build_chunk_jobs, run_chunk_jobs
from srna_win_target.results.html_report import build_report
from srna_win_target.results.streaming_writer import StreamingHitWriter
from srna_win_target.tools.registry import build_runner

ProgressCallback = Callable[[ProgressEvent], None]


def run_pipeline(
    job: PredictionJob,
    backend: Backend | None = None,
    on_progress: ProgressCallback | None = None,
) -> Path:
    """Run validation, chunking, prediction, parsing, and merged CSV output."""
    if backend is None:
        backend = build_backend(job.backend)

    work_dir = job.out_dir / "work"
    norm_dir = work_dir / "normalized"
    chunk_dir = work_dir / "chunks"
    result_dir = job.out_dir / "results"
    result_dir.mkdir(parents=True, exist_ok=True)

    mirna_fasta = normalize_input_fasta(job.mirna_fasta, norm_dir / "mirna.fa", molecule="rna")
    target_fasta = normalize_input_fasta(job.target_fasta, norm_dir / "targets.fa", molecule="rna")
    chunks = split_fasta(target_fasta, chunk_dir, records_per_chunk=job.chunk_size)

    mirna_input: Path | list[Path] = mirna_fasta
    if job.mirna_chunk_size and job.mirna_chunk_size > 0:
        mirna_chunk_dir = work_dir / "mirna_chunks"
        mirna_input = split_fasta(
            mirna_fasta, mirna_chunk_dir, records_per_chunk=job.mirna_chunk_size
        ) or [mirna_fasta]

    runners = {tool.name: build_runner(tool) for tool in job.tools}
    chunk_jobs = build_chunk_jobs(job, mirna_input, chunks)
    manifest = RunManifest(work_dir / "manifest.json")
    merged_csv = result_dir / "merged_predictions.csv"

    with StreamingHitWriter(merged_csv) as writer:
        run_chunk_jobs(
            job=job,
            chunk_jobs=chunk_jobs,
            runners=runners,
            backend=backend,
            manifest=manifest,
            hit_writer=writer,
            on_progress=on_progress,
        )

    # Build the interactive single-file HTML report (parses alignments from
    # work/raw/ and emits result_dir/predictions.html). Best-effort: a
    # failure here must not invalidate the merged CSV the user already has.
    try:
        build_report(merged_csv, work_dir, result_dir / "predictions.html")
    except Exception:  # noqa: BLE001
        pass

    return merged_csv
