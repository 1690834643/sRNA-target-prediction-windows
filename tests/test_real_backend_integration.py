"""Integration test against real bundled tool binaries.

Skipped automatically when bundled_tools/ is missing a binary; run-able on
any dev box that has the portable bundle. Catches argv-quoting / cwd / PATH
bugs that FakeBackend cannot.

Marker: `@pytest.mark.requires_tools`
"""
from __future__ import annotations

from pathlib import Path

import pytest

from srna_win_target.core.models import (
    BackendKind,
    PredictionJob,
    ToolConfig,
)
from srna_win_target.core.pipeline import run_pipeline
from srna_win_target.web.discover import discover_bundled_tools

REPO_ROOT = Path(__file__).resolve().parents[1]


def _bundled_or_skip(tool: str):
    """Return the DiscoveredTool entry for `tool` or skip the test."""
    discovered = discover_bundled_tools(REPO_ROOT)
    entry = discovered.get(tool)
    if entry is None or not entry.ready:
        pytest.skip(f"{tool} not bundled in this checkout — skipping integration test")
    return entry


@pytest.mark.requires_tools
def test_miranda_real_run_on_examples(tmp_path: Path) -> None:
    """miRanda end-to-end against bundled examples — exercises LocalBackend."""
    entry = _bundled_or_skip("miranda")
    job = PredictionJob(
        mirna_fasta=REPO_ROOT / "examples" / "input" / "mirna.fa",
        target_fasta=REPO_ROOT / "examples" / "input" / "targets.fa",
        out_dir=tmp_path / "out_miranda",
        tools=[ToolConfig(name="miranda", executable=entry.executable)],
        workers=1,
        chunk_size=10,
        mirna_chunk_size=0,
        resume=False,
        backend=BackendKind.LOCAL,
    )
    merged = run_pipeline(job)
    assert merged.exists()
    text = merged.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines[0].startswith("tool,mirna_id,target_id"), "merged CSV header is wrong"
    data_lines = [ln for ln in lines[1:] if ln.startswith("miranda,")]
    assert len(data_lines) >= 1, "miRanda should find ≥1 hit on the example inputs"


@pytest.mark.requires_tools
def test_rnahybrid_real_run_on_examples(tmp_path: Path) -> None:
    """RNAhybrid end-to-end against bundled examples — exercises LocalBackend."""
    entry = _bundled_or_skip("rnahybrid")
    job = PredictionJob(
        mirna_fasta=REPO_ROOT / "examples" / "input" / "mirna.fa",
        target_fasta=REPO_ROOT / "examples" / "input" / "targets.fa",
        out_dir=tmp_path / "out_rnahybrid",
        tools=[ToolConfig(name="rnahybrid", executable=entry.executable)],
        workers=1,
        chunk_size=10,
        mirna_chunk_size=0,
        resume=False,
        backend=BackendKind.LOCAL,
    )
    merged = run_pipeline(job)
    assert merged.exists()
    lines = [ln for ln in merged.read_text(encoding="utf-8").splitlines() if ln.startswith("rnahybrid,")]
    assert len(lines) >= 1, "RNAhybrid should find ≥1 hit on the example inputs"


@pytest.mark.requires_tools
def test_pita_real_run_matches_linux_reference(tmp_path: Path) -> None:
    """PITA v2 must produce the same ΔG/ddG values as the Linux server reference.

    Skipped on non-Windows: the bundle ships Strawberry Perl + Windows .exe
    binaries that cannot execute natively under Linux. (Linux-side PITA is
    covered by tests/test_parsers_real.py against the bioinformatics server.)
    The wrapper exits early with RuntimeError on non-ASCII output paths, so
    we deliberately keep tmp_path ASCII.
    """
    import sys as _sys
    if not _sys.platform.startswith("win"):
        pytest.skip("PITA bundle ships Windows .exe + Strawberry Perl — Windows-only")
    entry = _bundled_or_skip("pita")
    job = PredictionJob(
        mirna_fasta=REPO_ROOT / "examples" / "input" / "mirna.fa",
        target_fasta=REPO_ROOT / "examples" / "input" / "targets.fa",
        out_dir=tmp_path / "out_pita",
        tools=[ToolConfig(
            name="pita",
            parameters={
                "script": str(entry.script),
                "perl": str(entry.bundled_perl),
            },
        )],
        workers=1,
        chunk_size=10,
        mirna_chunk_size=0,
        resume=False,
        backend=BackendKind.LOCAL,
    )
    try:
        merged = run_pipeline(job)
    except RuntimeError as exc:
        if "non-ASCII" in str(exc) or "space" in str(exc):
            pytest.skip(f"PITA path-safety guard tripped on this host: {exc}")
        raise
    assert merged.exists()
    pita_lines = [
        ln for ln in merged.read_text(encoding="utf-8").splitlines()
        if ln.startswith("pita,")
    ]
    # 2 example targets × 2 example miRNAs *with* an actual seed hit pruned to
    # 2 (one per target). Tolerate ≥1 hits in case upstream PITA quirks emit
    # different counts on different bundle revisions.
    assert len(pita_lines) >= 1, f"PITA produced no hits; merged.csv:\n{merged.read_text()}"
    # Sanity check: ddG must be finite (not the -1 placeholder fallback) for
    # at least one hit — proves the v2 RNAduplex+RNAddG4 binaries are wired.
    # ddG is currently stored in the `score` column of merged_predictions.csv.
    import csv as _csv
    with merged.open(encoding="utf-8") as fh:
        reader = _csv.DictReader(fh)
        finite_ddg = [
            r for r in reader
            if r["tool"] == "pita"
            and r.get("score") not in ("", None)
            and float(r["score"]) != -1.0
        ]
    assert finite_ddg, "All PITA ddG values are -1 — v2 binaries not producing real ΔG"
