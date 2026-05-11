from __future__ import annotations

from pathlib import Path

from Bio import SeqIO


def split_fasta(fasta: Path, out_dir: Path, records_per_chunk: int = 500) -> list[Path]:
    """Split a FASTA file by record count and return chunk paths.

    Uses Biopython for both reading and writing. Chunk filenames follow the
    pattern targets.chunk_{NNNNN}.fa with 5-digit zero-padded indices starting at 0.
    """
    if records_per_chunk < 1:
        raise ValueError("records_per_chunk must be >= 1")

    out_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[Path] = []

    buffer: list = []
    chunk_index = 0

    def _flush(buf: list, idx: int) -> Path:
        chunk_path = out_dir / f"targets.chunk_{idx:05d}.fa"
        with chunk_path.open("w", encoding="utf-8") as fh:
            SeqIO.write(buf, fh, "fasta")
        chunks.append(chunk_path)
        return chunk_path

    for record in SeqIO.parse(str(fasta), "fasta"):
        buffer.append(record)
        if len(buffer) == records_per_chunk:
            _flush(buffer, chunk_index)
            chunk_index += 1
            buffer = []

    # Flush remaining records (last shorter chunk)
    if buffer:
        _flush(buffer, chunk_index)

    return chunks
