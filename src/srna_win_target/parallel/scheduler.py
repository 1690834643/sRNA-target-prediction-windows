from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from srna_win_target.backends.base import Backend
from srna_win_target.core.models import (
    ChunkJob,
    PredictionJob,
    ProgressEvent,
    RunStatus,
)
from srna_win_target.parallel.manifest import RunManifest
from srna_win_target.results.streaming_writer import StreamingHitWriter
from srna_win_target.tools.base import RawToolOutput, ToolRunner

ProgressCallback = Callable[[ProgressEvent], None]


def build_chunk_jobs(
    job: PredictionJob,
    mirna_fasta: Path | list[Path],
    chunks: list[Path],
) -> list[ChunkJob]:
    """Build the tool × (mirna_chunk?) × target_chunk job matrix.

    If `mirna_fasta` is a list, each entry pairs with every target chunk
    to give matrix-level parallelism — useful when the miRNA pool is large
    enough that target chunking alone leaves CPUs idle.
    """
    mirna_chunks: list[Path] = mirna_fasta if isinstance(mirna_fasta, list) else [mirna_fasta]
    chunk_jobs: list[ChunkJob] = []
    for tool in job.tools:
        for m_chunk in mirna_chunks:
            for t_chunk in chunks:
                if len(mirna_chunks) == 1:
                    chunk_id = f"{tool.name}_{t_chunk.stem}"
                else:
                    chunk_id = f"{tool.name}_{m_chunk.stem}__{t_chunk.stem}"
                chunk_jobs.append(
                    ChunkJob(
                        job_id=chunk_id,
                        tool=tool,
                        mirna_fasta=m_chunk,
                        target_chunk=t_chunk,
                        out_dir=job.out_dir / "work" / "raw" / tool.name,
                    )
                )
    return chunk_jobs


def _log_path(job: PredictionJob, chunk_job: ChunkJob) -> Path:
    return job.out_dir / "work" / "logs" / f"{chunk_job.job_id}.log"


def _execute_one(
    chunk_job: ChunkJob,
    runner: ToolRunner,
    backend: Backend,
    log_file: Path,
) -> RawToolOutput:
    return runner.run(chunk_job, backend=backend, log_file=log_file)


def run_chunk_jobs(
    job: PredictionJob,
    chunk_jobs: list[ChunkJob],
    runners: dict[str, ToolRunner],
    backend: Backend,
    manifest: RunManifest,
    hit_writer: StreamingHitWriter,
    on_progress: ProgressCallback | None = None,
    tool_versions: dict[str, str] | None = None,
) -> dict[str, int]:
    """Execute chunk jobs with bounded thread parallelism.

    Returns counts: {"completed", "skipped", "failed"}.
    Streams parsed hits into `hit_writer` as each chunk finishes so we do not
    accumulate millions of rows in memory.
    """

    versions = tool_versions or {}
    counts = {"completed": 0, "skipped": 0, "failed": 0}
    total = len(chunk_jobs)
    pending: list[tuple[str, ChunkJob, Path]] = []

    for chunk_job in chunk_jobs:
        version = versions.get(chunk_job.tool.name, "unknown")
        key = manifest.cache_key_for(chunk_job, version)
        if job.resume and manifest.is_completed(key):
            counts["skipped"] += 1
            _emit(
                on_progress,
                chunk_job,
                RunStatus.SKIPPED,
                completed=_done(counts),
                total=total,
                message="cached",
            )
            entry = manifest.get(key)
            if entry and entry.output_file:
                _replay_parsed_hits(
                    runners[chunk_job.tool.name],
                    chunk_job,
                    Path(entry.output_file),
                    hit_writer,
                )
            continue
        pending.append((key, chunk_job, _log_path(job, chunk_job)))
        manifest.mark_running(key, chunk_job)
        _emit(
            on_progress,
            chunk_job,
            RunStatus.PENDING,
            completed=_done(counts),
            total=total,
        )

    if not pending:
        return counts

    with ThreadPoolExecutor(max_workers=max(1, job.workers)) as pool:
        future_map = {
            pool.submit(
                _execute_one,
                chunk_job,
                runners[chunk_job.tool.name],
                backend,
                log_file,
            ): (key, chunk_job, log_file)
            for key, chunk_job, log_file in pending
        }
        for future in as_completed(future_map):
            key, chunk_job, log_file = future_map[future]
            try:
                raw_output = future.result()
            except Exception as exc:  # pragma: no cover - defensive
                counts["failed"] += 1
                manifest.mark_failed(key, chunk_job, str(exc), log_file)
                _emit(
                    on_progress,
                    chunk_job,
                    RunStatus.FAILED,
                    completed=_done(counts),
                    total=total,
                    message=str(exc)[:300],
                )
                continue

            runner = runners[chunk_job.tool.name]
            try:
                hits = runner.parse_output(raw_output)
            except Exception as exc:  # pragma: no cover - defensive
                counts["failed"] += 1
                manifest.mark_failed(key, chunk_job, f"parse_output: {exc}", log_file)
                _emit(
                    on_progress,
                    chunk_job,
                    RunStatus.FAILED,
                    completed=_done(counts),
                    total=total,
                    message=f"parse_output: {exc}"[:300],
                )
                continue

            hit_writer.write(hits)
            manifest.mark_completed(key, chunk_job, raw_output.output_file, log_file)
            counts["completed"] += 1
            _emit(
                on_progress,
                chunk_job,
                RunStatus.COMPLETED,
                completed=_done(counts),
                total=total,
            )

    return counts


def _emit(
    callback: ProgressCallback | None,
    chunk_job: ChunkJob,
    status: RunStatus,
    *,
    completed: int = 0,
    total: int = 0,
    message: str = "",
) -> None:
    if callback is None:
        return
    callback(
        ProgressEvent(
            chunk_id=chunk_job.job_id,
            tool=chunk_job.tool.name,
            status=status,
            message=message,
            completed=completed,
            total=total,
        )
    )


def _done(counts: dict[str, int]) -> int:
    return counts["completed"] + counts["skipped"] + counts["failed"]


def _replay_parsed_hits(
    runner: ToolRunner,
    chunk_job: ChunkJob,
    output_file: Path,
    hit_writer: StreamingHitWriter,
) -> None:
    """Re-parse a cached output so its hits land in the merged CSV."""
    raw = RawToolOutput(
        tool_name=runner.name,
        chunk_id=chunk_job.job_id,
        stdout="",
        stderr="",
        output_file=output_file,
        returncode=0,
    )
    try:
        hits = runner.parse_output(raw)
    except Exception:
        return
    hit_writer.write(hits)
