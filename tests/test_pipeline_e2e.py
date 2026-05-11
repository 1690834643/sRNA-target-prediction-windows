"""End-to-end pipeline integration tests using the in-process FakeBackend.

These cover the wiring between normalize -> split -> scheduler -> backend ->
parser -> streaming writer -> manifest. The real subprocess layer is replaced
by FakeBackend, so the test runs identically on Linux/macOS/Windows without
any external tool installed.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from srna_win_target.cli._selftest import FakeBackend, run_selftest
from srna_win_target.core.models import (
    BackendKind,
    PredictionJob,
    ToolConfig,
)
from srna_win_target.core.pipeline import run_pipeline


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_selftest_produces_expected_merged_csv(tmp_path: Path) -> None:
    merged = run_selftest(tmp_path)
    rows = _read_csv(merged)

    # 3 targets, chunk_size=2 -> 2 chunks, 2 hits per chunk = 4 rows total.
    assert len(rows) == 4
    assert {row["tool"] for row in rows} == {"miranda"}
    assert all(row["mirna_id"].startswith("selftest_mir_") for row in rows)
    assert all(row["score"] for row in rows)


def test_pipeline_writes_manifest_and_logs(tmp_path: Path) -> None:
    run_selftest(tmp_path)
    work = tmp_path / "out" / "work"
    manifest_path = work / "manifest.json"
    assert manifest_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest["entries"]
    assert len(entries) == 2          # one per chunk
    statuses = {e["status"] for e in entries}
    assert statuses == {"completed"}

    log_dir = work / "logs"
    log_files = sorted(log_dir.glob("*.log"))
    assert len(log_files) == 2
    for log in log_files:
        assert "selftest:" in log.read_text(encoding="utf-8")


def test_pipeline_resume_skips_completed_chunks(tmp_path: Path) -> None:
    """Running the pipeline twice with resume=True should add 0 new rows
    the second time (cached hits are replayed into the merged CSV)."""
    mirna = tmp_path / "mirna.fa"
    target = tmp_path / "targets.fa"
    mirna.write_text(">m1\nACGUACGUACGU\n", encoding="utf-8")
    target.write_text(">t1\nACGUACGUACGU\n>t2\nACGUACGUACGU\n", encoding="utf-8")

    out_dir = tmp_path / "out"
    job = PredictionJob(
        mirna_fasta=mirna,
        target_fasta=target,
        out_dir=out_dir,
        tools=[ToolConfig(name="miranda", executable=Path(sys.executable))],
        workers=1,
        chunk_size=1,
        resume=True,
        backend=BackendKind.LOCAL,
    )

    backend = FakeBackend(hits_per_chunk=3)
    merged1 = run_pipeline(job, backend=backend)
    rows1 = _read_csv(merged1)
    assert len(rows1) == 6  # 2 chunks x 3 hits

    merged2 = run_pipeline(job, backend=backend)
    rows2 = _read_csv(merged2)
    # Streaming writer rewrites the CSV each run; replay path adds parsed
    # hits from the cached output files.
    assert len(rows2) == 6
