from __future__ import annotations

import csv
from pathlib import Path

from srna_win_target.core.models import PredictionHit
from srna_win_target.results.streaming_writer import StreamingHitWriter


def test_streaming_writer_writes_header_and_rows(tmp_path: Path) -> None:
    out = tmp_path / "merged.csv"
    hits = [
        PredictionHit(tool="miranda", mirna_id="m1", target_id="t1", score=150.0),
        PredictionHit(tool="rnahybrid", mirna_id="m1", target_id="t1", energy=-25.0),
    ]
    with StreamingHitWriter(out) as writer:
        writer.write(hits[:1])
        writer.write(hits[1:])

    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert len(rows) == 2
    assert rows[0]["tool"] == "miranda"
    assert rows[1]["tool"] == "rnahybrid"
    assert rows[0]["mirna_id"] == "m1"


def test_streaming_writer_empty_hits_no_error(tmp_path: Path) -> None:
    out = tmp_path / "empty.csv"
    with StreamingHitWriter(out) as writer:
        assert writer.write([]) == 0
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert rows == []


def test_streaming_writer_row_count(tmp_path: Path) -> None:
    out = tmp_path / "count.csv"
    with StreamingHitWriter(out) as writer:
        writer.write([PredictionHit(tool="x", mirna_id=str(i), target_id="t") for i in range(5)])
        writer.write([PredictionHit(tool="y", mirna_id=str(i), target_id="t") for i in range(3)])
        assert writer.row_count == 8
