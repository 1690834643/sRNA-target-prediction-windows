from pathlib import Path

from srna_win_target.data.format_check import detect_sequence_format


def test_detect_sequence_format_fasta(tmp_path: Path):
    fasta = tmp_path / "x.fa"
    fasta.write_text(">mir1\nUGCA\n", encoding="utf-8")
    assert detect_sequence_format(fasta) == "fasta"
