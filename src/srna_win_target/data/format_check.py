from __future__ import annotations

import re
import sys
from pathlib import Path

from Bio import SeqIO
from Bio.SeqRecord import SeqRecord

# Characters allowed in cleaned sequence (ACGTU + IUPAC ambiguity)
_VALID_BASES = frozenset("ACGTURYSWKMBDHVN")
_ILLEGAL_ID_CHARS = re.compile(r"[|:/\\,;]")


class FastaValidationError(ValueError):
    """Raised with a user-facing reason describing why a file isn't usable FASTA."""


def detect_sequence_format(path: Path) -> str:
    """Return fasta, fastq, or unknown from the first non-empty character."""
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(">"):
                return "fasta"
            if stripped.startswith("@"):
                return "fastq"
            return "unknown"
    return "unknown"


def validate_input_fasta(path: Path, role: str = "input") -> None:
    """Pre-flight sanity check with concrete error reasons for the UI.

    Raises FastaValidationError with a Chinese-first message stating exactly
    what is wrong (path doesn't exist / empty file / first line not '>' /
    no records / all records empty / non-nucleotide chars dominate).
    Pass `role` (e.g. 'miRNA FASTA', 'Targets FASTA') so the error names
    which field failed.
    """
    if not path.exists():
        raise FastaValidationError(f"{role}: 文件不存在 — {path}")
    if not path.is_file():
        raise FastaValidationError(f"{role}: 路径不是文件 — {path}")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise FastaValidationError(f"{role}: 无法读取文件属性 — {exc}") from exc
    if size == 0:
        raise FastaValidationError(f"{role}: 文件为空（0 字节）")
    if size > 5 * 1024 * 1024 * 1024:  # 5 GB safety net
        raise FastaValidationError(
            f"{role}: 文件超过 5 GB（{size / 1e9:.1f} GB），请先拆分"
        )

    # --- First non-empty line must start with '>' (or '@' if FASTQ) ---
    first: str | None = None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.strip():
                    first = line.rstrip("\n\r")
                    break
    except OSError as exc:
        raise FastaValidationError(f"{role}: 读取失败 — {exc}") from exc
    if first is None:
        raise FastaValidationError(f"{role}: 文件只有空白行，没有序列")
    if not (first.startswith(">") or first.startswith("@")):
        snippet = first[:40] + ("…" if len(first) > 40 else "")
        raise FastaValidationError(
            f"{role}: 首行不是 '>' 开头（看起来不是 FASTA / FASTQ）；"
            f"实际首行：{snippet!r}"
        )

    # --- Try to actually parse with Bio.SeqIO and look at first ~10 records ---
    fmt = "fastq" if first.startswith("@") else "fasta"
    n_records = 0
    n_empty = 0
    n_invalid_dominant = 0
    sampled_invalid_ids: list[str] = []
    try:
        for record in SeqIO.parse(str(path), fmt):
            n_records += 1
            seq = str(record.seq).replace("-", "").replace(".", "")
            seq = re.sub(r"\s+", "", seq).upper()
            if not seq:
                n_empty += 1
                if len(sampled_invalid_ids) < 3:
                    sampled_invalid_ids.append(record.id or "(no-id)")
            else:
                bad = sum(1 for c in seq if c not in _VALID_BASES)
                if bad / max(len(seq), 1) > 0.5:
                    n_invalid_dominant += 1
                    if len(sampled_invalid_ids) < 3:
                        sampled_invalid_ids.append(record.id or "(no-id)")
            if n_records >= 200:
                # Probed enough; trust the file structure
                break
    except Exception as exc:  # noqa: BLE001 — Bio.SeqIO raises various types
        raise FastaValidationError(
            f"{role}: 解析失败（{type(exc).__name__}）— {exc}"
        ) from exc

    if n_records == 0:
        raise FastaValidationError(
            f"{role}: 没有解析出任何序列记录（首行虽是 '>' 但下文为空）"
        )
    if n_empty == n_records:
        raise FastaValidationError(
            f"{role}: 共 {n_records} 条记录，全部为空序列"
        )
    if n_invalid_dominant == n_records:
        sample = ", ".join(sampled_invalid_ids) or "未知"
        raise FastaValidationError(
            f"{role}: 共 {n_records} 条记录，全部超过 50% 非 ACGTU 字符 "
            f"（举例 ID：{sample}）— 可能是蛋白序列或损坏的文件"
        )


def normalize_input_fasta(src: Path, dst: Path, molecule: str = "rna") -> Path:
    """Normalize FASTA or FASTQ input into a clean single-line-per-sequence FASTA.

    Steps applied to each record:
    - ID cleaning: first whitespace token, illegal chars replaced with _, deduped with _dup1/_dup2/...
    - Sequence: gaps and whitespace stripped, upper-cased, invalid bases replaced with N,
      T<->U conversion per molecule parameter.
    - Empty post-cleaning records are skipped with a stderr warning.
    - A single stderr warning is printed at the end if any bases were repaired.

    Returns dst.
    """
    fmt = detect_sequence_format(src)
    if fmt == "unknown":
        fmt = "fasta"  # fall back; Bio.SeqIO will raise if truly invalid

    dst.parent.mkdir(parents=True, exist_ok=True)

    mol = molecule.lower()
    seen_ids: dict[str, int] = {}
    total_repaired = 0

    with dst.open("w", encoding="utf-8") as out:
        for record in SeqIO.parse(str(src), fmt):
            original_id = record.id

            # --- Clean ID ---
            # Take first whitespace-delimited token from the full description
            raw_id = record.description.split()[0] if record.description else record.id
            clean_id = _ILLEGAL_ID_CHARS.sub("_", raw_id)

            # Uniqueness
            if clean_id in seen_ids:
                seen_ids[clean_id] += 1
                clean_id = f"{clean_id}_dup{seen_ids[clean_id]}"
            else:
                seen_ids[clean_id] = 0

            # --- Clean sequence ---
            seq = str(record.seq)
            # Strip gaps and whitespace
            seq = seq.replace("-", "").replace(".", "")
            seq = re.sub(r"\s+", "", seq)
            seq = seq.upper()

            # Replace invalid bases with N
            repaired = 0
            cleaned_chars = []
            for ch in seq:
                if ch in _VALID_BASES:
                    cleaned_chars.append(ch)
                else:
                    cleaned_chars.append("N")
                    repaired += 1
            seq = "".join(cleaned_chars)
            total_repaired += repaired

            # T<->U conversion
            if mol == "rna":
                seq = seq.replace("T", "U")
            else:
                seq = seq.replace("U", "T")

            # Skip empty records
            if not seq:
                print(
                    f"WARNING: record '{original_id}' is empty after cleaning, skipping.",
                    file=sys.stderr,
                )
                continue

            out.write(f">{clean_id}\n{seq}\n")

    if total_repaired > 0:
        print(
            f"WARNING: {total_repaired} base(s) replaced with N due to invalid characters.",
            file=sys.stderr,
        )

    return dst
