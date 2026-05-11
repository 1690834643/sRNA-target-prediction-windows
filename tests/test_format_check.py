"""Tests for srna_win_target.data.format_check (Phase 2)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from srna_win_target.data.format_check import (
    FastaValidationError,
    detect_sequence_format,
    normalize_input_fasta,
    validate_input_fasta,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _read_records(path: Path) -> list[tuple[str, str]]:
    """Return list of (id, seq) from a FASTA file."""
    records = []
    current_id = None
    for line in path.read_text().splitlines():
        if line.startswith(">"):
            current_id = line[1:]
        elif line and current_id is not None:
            records.append((current_id, line))
            current_id = None
    return records


# ---------------------------------------------------------------------------
# detect_sequence_format
# ---------------------------------------------------------------------------

def test_detect_sequence_format_fasta(tmp_path):
    p = _write(tmp_path, "a.fa", ">seq1\nACGU\n")
    assert detect_sequence_format(p) == "fasta"


def test_detect_sequence_format_fastq(tmp_path):
    p = _write(tmp_path, "a.fq", "@seq1\nACGU\n+\nIIII\n")
    assert detect_sequence_format(p) == "fastq"


def test_detect_sequence_format_unknown(tmp_path):
    p = _write(tmp_path, "a.txt", "ACGU\n")
    assert detect_sequence_format(p) == "unknown"


# ---------------------------------------------------------------------------
# normalize_input_fasta — basic FASTA round-trip
# ---------------------------------------------------------------------------

def test_normalize_basic_fasta(tmp_path):
    src = _write(tmp_path, "in.fa", ">seq1\nACGTACGT\n")
    dst = tmp_path / "out.fa"
    result = normalize_input_fasta(src, dst, molecule="dna")
    assert result == dst
    records = _read_records(dst)
    assert len(records) == 1
    assert records[0] == ("seq1", "ACGTACGT")


# ---------------------------------------------------------------------------
# normalize_input_fasta — FASTQ input
# ---------------------------------------------------------------------------

def test_normalize_fastq_input(tmp_path):
    fastq_text = "@read1\nACGT\n+\nIIII\n@read2\nTTTT\n+\nIIII\n"
    src = _write(tmp_path, "in.fq", fastq_text)
    dst = tmp_path / "out.fa"
    normalize_input_fasta(src, dst, molecule="dna")
    records = _read_records(dst)
    assert len(records) == 2
    assert records[0][0] == "read1"
    assert records[1][0] == "read2"


# ---------------------------------------------------------------------------
# Duplicate IDs get _dup suffixes
# ---------------------------------------------------------------------------

def test_normalize_duplicate_ids_get_suffixed(tmp_path):
    src = _write(tmp_path, "dup.fa", ">seq1\nACGT\n>seq1\nTTTT\n>seq1\nGGGG\n")
    dst = tmp_path / "out.fa"
    normalize_input_fasta(src, dst, molecule="dna")
    records = _read_records(dst)
    ids = [r[0] for r in records]
    assert ids[0] == "seq1"
    assert ids[1] == "seq1_dup1"
    assert ids[2] == "seq1_dup2"


# ---------------------------------------------------------------------------
# Illegal chars in sequence become N
# ---------------------------------------------------------------------------

def test_normalize_illegal_chars_become_N(tmp_path, capsys):
    # '1', '2', '3' are not valid IUPAC bases
    src = _write(tmp_path, "bad.fa", ">seq1\nACG123\n")
    dst = tmp_path / "out.fa"
    normalize_input_fasta(src, dst, molecule="dna")
    records = _read_records(dst)
    assert records[0][1] == "ACGNNN"
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "3" in captured.err or "base" in captured.err.lower()


# ---------------------------------------------------------------------------
# T -> U (molecule=rna)
# ---------------------------------------------------------------------------

def test_normalize_t_to_u(tmp_path):
    src = _write(tmp_path, "in.fa", ">seq1\nACGT\n")
    dst = tmp_path / "out.fa"
    normalize_input_fasta(src, dst, molecule="rna")
    records = _read_records(dst)
    assert records[0][1] == "ACGU"


# ---------------------------------------------------------------------------
# U -> T (molecule=dna)
# ---------------------------------------------------------------------------

def test_normalize_u_to_t(tmp_path):
    src = _write(tmp_path, "in.fa", ">seq1\nACGU\n")
    dst = tmp_path / "out.fa"
    normalize_input_fasta(src, dst, molecule="dna")
    records = _read_records(dst)
    assert records[0][1] == "ACGT"


# ---------------------------------------------------------------------------
# Lowercase -> uppercase
# ---------------------------------------------------------------------------

def test_normalize_lowercase_uppercased(tmp_path):
    src = _write(tmp_path, "in.fa", ">seq1\nacgt\n")
    dst = tmp_path / "out.fa"
    normalize_input_fasta(src, dst, molecule="dna")
    records = _read_records(dst)
    assert records[0][1] == "ACGT"


# ---------------------------------------------------------------------------
# Gaps and whitespace stripped
# ---------------------------------------------------------------------------

def test_normalize_gap_and_whitespace_stripped(tmp_path):
    src = _write(tmp_path, "in.fa", ">seq1\nAC-G.T\n")
    dst = tmp_path / "out.fa"
    normalize_input_fasta(src, dst, molecule="dna")
    records = _read_records(dst)
    assert records[0][1] == "ACGT"


# ---------------------------------------------------------------------------
# Empty record skipped with warning
# ---------------------------------------------------------------------------

def test_normalize_empty_record_skipped(tmp_path, capsys):
    # After cleaning, this record has no valid sequence
    src = _write(tmp_path, "in.fa", ">empty\n---\n>good\nACGT\n")
    dst = tmp_path / "out.fa"
    normalize_input_fasta(src, dst, molecule="dna")
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "empty" in captured.err
    records = _read_records(dst)
    # Only the 'good' record should appear
    assert len(records) == 1
    assert records[0][0] == "good"


# ---------------------------------------------------------------------------
# validate_input_fasta — user-facing pre-flight checks
# ---------------------------------------------------------------------------

def test_validate_missing_file(tmp_path):
    with pytest.raises(FastaValidationError, match="文件不存在"):
        validate_input_fasta(tmp_path / "nope.fa", role="miRNA FASTA")


def test_validate_empty_file(tmp_path):
    p = _write(tmp_path, "in.fa", "")
    with pytest.raises(FastaValidationError, match="文件为空"):
        validate_input_fasta(p, role="Targets FASTA")


def test_validate_not_fasta_first_line(tmp_path):
    p = _write(tmp_path, "in.fa", "this is plain text\nno header here\n")
    with pytest.raises(FastaValidationError, match="首行不是 '>' 开头"):
        validate_input_fasta(p)


def test_validate_blank_only(tmp_path):
    p = _write(tmp_path, "in.fa", "\n\n   \n")
    with pytest.raises(FastaValidationError, match="只有空白行"):
        validate_input_fasta(p)


def test_validate_all_records_empty(tmp_path):
    p = _write(tmp_path, "in.fa", ">a\n\n>b\n   \n")
    with pytest.raises(FastaValidationError):
        validate_input_fasta(p)


def test_validate_protein_sequence_dominant(tmp_path):
    # Sequence is mostly non-IUPAC letters (E/L/F/Q/I/P all invalid).
    p = _write(tmp_path, "in.fa", ">prot1\nMEEPILEQFREELY\n>prot2\nLLEEFFIIPPQQ\n")
    with pytest.raises(FastaValidationError, match="非 ACGTU"):
        validate_input_fasta(p)


def test_validate_happy_path(tmp_path):
    p = _write(tmp_path, "in.fa", ">seq1\nACGUACGU\n>seq2\nAUGCAUGC\n")
    validate_input_fasta(p)  # must not raise
