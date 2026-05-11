"""Tests for alignment parsers + SVG renderer + HTML report generator."""
from __future__ import annotations

from pathlib import Path

import pytest

from srna_win_target.results.visualize_alignment import (
    Alignment,
    parse_miranda,
    parse_rnahybrid,
    render_svg,
    collect_alignments,
)
from srna_win_target.results.html_report import build_report


REPO = Path(__file__).resolve().parents[1]


def test_parse_miranda_real_sample():
    text = (REPO / "tests/golden/real/miranda/sample.out").read_text(encoding="utf-8")
    alns = parse_miranda(text)
    assert len(alns) >= 1
    a = alns[0]
    assert a.tool == "miRanda"
    assert a.mirna_id == "example_miR_1"
    assert a.target_id == "example_gene_1_3ttr"
    assert a.score > 0
    assert a.energy < 0
    assert len(a.query) == len(a.ref) == len(a.match)
    # The middle line should contain at least one Watson-Crick bond.
    assert "|" in a.match


def test_parse_miranda_captures_wobble():
    """The second sample alignment has a `:` wobble — verify we keep it."""
    text = (REPO / "tests/golden/real/miranda/sample.out").read_text(encoding="utf-8")
    alns = parse_miranda(text)
    matches = " ".join(a.match for a in alns)
    assert ":" in matches, f"expected wobble in at least one alignment, got: {matches!r}"


def test_parse_rnahybrid_real_sample():
    text = (REPO / "tests/golden/real/rnahybrid/sample.txt").read_text(encoding="utf-8")
    alns = parse_rnahybrid(text)
    assert len(alns) >= 1
    a = alns[0]
    assert a.tool == "RNAhybrid"
    assert a.score is None              # RNAhybrid has no separate score
    assert a.energy < 0                 # ΔG should be negative
    assert a.pvalue is not None and 0 <= a.pvalue <= 1
    assert "|" in a.match


def test_render_svg_contains_expected_markup():
    a = Alignment(
        tool="miRanda", mirna_id="miR-21", target_id="PDCD4",
        score=181.0, energy=-29.4,
        query="UUGAUAUG-UUGGAUGAUGGAGU", ref="UUGCAUACAAACCUACUACCUCA",
        match="    |||| |||||||||||||| ",
        q_start=2, q_end=19, r_start=5, r_end=27,
    )
    svg = render_svg(a)
    assert svg.startswith("<svg")
    assert "miR-21" in svg and "PDCD4" in svg
    assert "Courier" in svg  # locked sequence font
    assert "Arial" in svg    # locked label font
    assert "5'" in svg and "3'" in svg
    # ΔG / score should appear in metadata strip
    assert "-29.4" in svg
    assert "181" in svg


def test_render_svg_rnahybrid_omits_score_label():
    """RNAhybrid alignments have no `score` separate from energy — verify
    the metadata strip drops the 'score X' segment but keeps ΔG."""
    a = Alignment(
        tool="RNAhybrid", mirna_id="m", target_id="t",
        score=None, energy=-32.1,
        query="UAAGAAGGU", ref="CUUCUUGUA",
        match="||||||||| ",
        q_start=1, q_end=9, r_start=10, r_end=18, pvalue=1.3e-5,
    )
    svg = render_svg(a)
    assert "score" not in svg.lower(), "score should be hidden when None"
    assert "ΔG -32.1" in svg
    assert "p=" in svg  # pvalue shown


def test_collect_alignments_traverses_raw_tree(tmp_path):
    """A faked work/raw/<tool>/<chunk>.out tree should be parsed."""
    raw = tmp_path / "raw"
    (raw / "miranda").mkdir(parents=True)
    sample = (REPO / "tests/golden/real/miranda/sample.out").read_text(encoding="utf-8")
    (raw / "miranda" / "chunk_00.out").write_text(sample, encoding="utf-8")

    by_key = collect_alignments(raw)
    assert len(by_key) >= 1
    key = ("miRanda", "example_miR_1", "example_gene_1_3ttr")
    assert key in by_key


def test_build_report_e2e(tmp_path):
    """Mock merged CSV + raw dir; verify predictions.html is generated."""
    work = tmp_path / "work"
    raw = work / "raw" / "miranda"
    raw.mkdir(parents=True)
    sample = (REPO / "tests/golden/real/miranda/sample.out").read_text(encoding="utf-8")
    (raw / "chunk_00.out").write_text(sample, encoding="utf-8")

    merged = tmp_path / "results" / "merged_predictions.csv"
    merged.parent.mkdir(parents=True)
    merged.write_text(
        "tool,mirna_id,target_id,start,end,score,energy,pvalue,raw_file,chunk_id\n"
        "miranda,example_miR_1,example_gene_1_3ttr,5,27,181.0,-29.36,,,c00\n"
        "rnahybrid,example_miR_1,example_gene_1_3ttr,6,28,,-32.1,1.3e-5,,c00\n",
        encoding="utf-8",
    )

    out = tmp_path / "results" / "predictions.html"
    build_report(merged, work, out)

    body = out.read_text(encoding="utf-8")
    assert "sRNA Target Predictor" in body
    assert "example_miR_1" in body
    assert "example_gene_1_3ttr" in body
    # The JSON payload must contain both hits.
    assert '"miRanda"' in body and '"RNAhybrid"' in body
    # miRanda hit should have an inline SVG because we parsed it from raw.
    assert "<svg" in body
