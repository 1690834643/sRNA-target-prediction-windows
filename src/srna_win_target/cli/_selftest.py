"""End-to-end self-test that runs the full pipeline without any real tool.

Used by `srna-win-target selftest` so a user (especially on Windows) can verify
that their install + the wrapper plumbing all work, before they bother
installing miRanda / RNAhybrid / PITA.
"""
from __future__ import annotations

import sys
from pathlib import Path

from srna_win_target.backends.base import Backend, BackendResult
from srna_win_target.core.models import (
    BackendKind,
    LogicalCommand,
    PredictionJob,
    ToolConfig,
)
from srna_win_target.core.pipeline import run_pipeline


_FAKE_MIRANDA_LINE = (
    ">{mirna}\t{target}\t{score}\t{energy}\t1 22\t10 31\t22\t95.00%\t100.00%"
    "\t||||||||||||||||||||||"
)


class FakeBackend(Backend):
    """A backend that writes deterministic miRanda-shaped output to the
    expected output file instead of executing anything. The real
    MirandaRunner.parse_output() then turns that into PredictionHits, so the
    integration covers everything except the actual tool binary."""

    name = "fake"

    def __init__(self, hits_per_chunk: int = 2) -> None:
        self.hits_per_chunk = hits_per_chunk

    def run(self, command: LogicalCommand, log_file: Path | None = None) -> BackendResult:
        if command.expected_output_file is not None:
            command.expected_output_file.parent.mkdir(parents=True, exist_ok=True)
            lines = [
                _FAKE_MIRANDA_LINE.format(
                    mirna=f"selftest_mir_{i}",
                    target=f"selftest_target_{i}",
                    score=140 + i,
                    energy=-20 - i,
                )
                for i in range(self.hits_per_chunk)
            ]
            command.expected_output_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if log_file is not None:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            log_file.write_text(f"# selftest: {' '.join(command.argv)}\n", encoding="utf-8")
        return BackendResult(
            returncode=0,
            stdout="",
            stderr="",
            output_file=command.expected_output_file,
            log_file=log_file,
        )


_DEFAULT_MIRNAS = """\
>selftest_miR_a
UGAGGUAGUAGGUUGUAUAGUU
>selftest_miR_b
UAAAGUGCUUAUAGUGCAGGUAG
"""

_DEFAULT_TARGETS = """\
>selftest_gene_1
AAAUUUGCAUACAAACCUACUACCUCAUUUUGCAUGCAUGCAU
>selftest_gene_2
UUUACCUACUGCACUAUAAGCACUUUAACCCGGGAAAUUUCCC
>selftest_gene_3
GCAUACGAUGCACGUUACGUACGUACGUACGUACGUACGAUCG
"""


def run_selftest(work_dir: Path) -> Path:
    """Drive the pipeline against the FakeBackend; return the merged CSV path."""
    work_dir.mkdir(parents=True, exist_ok=True)
    mirna_fa = work_dir / "mirna.fa"
    target_fa = work_dir / "targets.fa"
    mirna_fa.write_text(_DEFAULT_MIRNAS, encoding="utf-8")
    target_fa.write_text(_DEFAULT_TARGETS, encoding="utf-8")

    job = PredictionJob(
        mirna_fasta=mirna_fa,
        target_fasta=target_fa,
        out_dir=work_dir / "out",
        tools=[
            ToolConfig(
                name="miranda",
                # The runner's check_ready() just verifies the path exists.
                # sys.executable is guaranteed to exist on every platform.
                executable=Path(sys.executable),
            )
        ],
        workers=2,
        chunk_size=2,
        resume=False,
        backend=BackendKind.LOCAL,
    )

    return run_pipeline(job, backend=FakeBackend(hits_per_chunk=2))
