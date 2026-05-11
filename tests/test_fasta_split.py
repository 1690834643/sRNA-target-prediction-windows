"""Tests for srna_win_target.data.fasta_split (Phase 2)."""
from __future__ import annotations

from pathlib import Path

import pytest
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from srna_win_target.data.fasta_split import split_fasta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fasta(path: Path, n: int, prefix: str = "seq") -> Path:
    """Write a FASTA file with n records, each with a 10-base poly-A sequence."""
    records = [
        SeqRecord(Seq("AAAAAAAAAA"), id=f"{prefix}{i}", description="")
        for i in range(n)
    ]
    with path.open("w") as fh:
        SeqIO.write(records, fh, "fasta")
    return path


def _count_records(path: Path) -> int:
    return sum(1 for _ in SeqIO.parse(str(path), "fasta"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_split_exact_multiple(tmp_path):
    src = _make_fasta(tmp_path / "in.fa", 10)
    out_dir = tmp_path / "chunks"
    chunks = split_fasta(src, out_dir, records_per_chunk=5)
    assert len(chunks) == 2
    assert _count_records(chunks[0]) == 5
    assert _count_records(chunks[1]) == 5
    assert chunks[0].name == "targets.chunk_00000.fa"
    assert chunks[1].name == "targets.chunk_00001.fa"


def test_split_non_multiple_last_chunk_short(tmp_path):
    src = _make_fasta(tmp_path / "in.fa", 7)
    out_dir = tmp_path / "chunks"
    chunks = split_fasta(src, out_dir, records_per_chunk=3)
    assert len(chunks) == 3
    assert _count_records(chunks[0]) == 3
    assert _count_records(chunks[1]) == 3
    assert _count_records(chunks[2]) == 1


def test_split_single_record(tmp_path):
    src = _make_fasta(tmp_path / "in.fa", 1)
    out_dir = tmp_path / "chunks"
    chunks = split_fasta(src, out_dir, records_per_chunk=500)
    assert len(chunks) == 1
    assert _count_records(chunks[0]) == 1


def test_split_empty_file_returns_empty_list(tmp_path):
    src = tmp_path / "empty.fa"
    src.write_text("", encoding="utf-8")
    out_dir = tmp_path / "chunks"
    chunks = split_fasta(src, out_dir, records_per_chunk=10)
    assert chunks == []


def test_split_records_per_chunk_one(tmp_path):
    src = _make_fasta(tmp_path / "in.fa", 4)
    out_dir = tmp_path / "chunks"
    chunks = split_fasta(src, out_dir, records_per_chunk=1)
    assert len(chunks) == 4
    for chunk in chunks:
        assert _count_records(chunk) == 1


def test_split_invalid_records_per_chunk_raises(tmp_path):
    src = _make_fasta(tmp_path / "in.fa", 3)
    out_dir = tmp_path / "chunks"
    with pytest.raises(ValueError):
        split_fasta(src, out_dir, records_per_chunk=0)
    with pytest.raises(ValueError):
        split_fasta(src, out_dir, records_per_chunk=-5)
