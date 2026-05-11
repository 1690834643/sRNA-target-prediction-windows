from __future__ import annotations

from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

from srna_win_target.results.merge import (
    intersection_table,
    pairs_by_tool,
    write_intersection_csv,
)


def write_merged_csv(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "tool,mirna_id,target_id,start,end,score,energy,pvalue,raw_file,chunk_id",
                "miranda,m1,t1,1,20,150.0,,0.05,miranda.out,chunk-a",
                "rnahybrid,m1,t1,2,21,,-25.0,0.03,rnahybrid.out,chunk-a",
                "pita,m1,t1,3,22,5.0,-12.0,0.01,pita.out,chunk-a",
                "miranda,m1,t2,5,25,140.0,,0.20,miranda.out,chunk-b",
                "pita,m1,t2,6,26,8.0,,0.05,pita.out,chunk-b",
                "rnahybrid,m2,t1,7,27,,-18.0,0.40,rnahybrid.out,chunk-c",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_intersection_table_counts_tools_and_best_values(tmp_path: Path) -> None:
    merged_csv = write_merged_csv(tmp_path / "merged_predictions.csv")

    table = intersection_table(merged_csv)

    row = table.set_index(["mirna_id", "target_id"]).loc[("m1", "t1")]
    assert row["tools"] == "miranda,pita,rnahybrid"
    assert row["n_tools"] == 3
    assert row["best_score"] == 150.0
    assert row["best_energy"] == -25.0
    assert row["best_pvalue"] == 0.01

    assert table[["mirna_id", "target_id", "n_tools"]].to_dict("records") == [
        {"mirna_id": "m1", "target_id": "t1", "n_tools": 3},
        {"mirna_id": "m1", "target_id": "t2", "n_tools": 2},
        {"mirna_id": "m2", "target_id": "t1", "n_tools": 1},
    ]


def test_pairs_by_tool_returns_expected_pair_sets(tmp_path: Path) -> None:
    merged_csv = write_merged_csv(tmp_path / "merged_predictions.csv")

    assert pairs_by_tool(merged_csv) == {
        "miranda": {("m1", "t1"), ("m1", "t2")},
        "pita": {("m1", "t1"), ("m1", "t2")},
        "rnahybrid": {("m1", "t1"), ("m2", "t1")},
    }


def test_write_intersection_csv_round_trips_table(tmp_path: Path) -> None:
    merged_csv = write_merged_csv(tmp_path / "merged_predictions.csv")
    out_csv = tmp_path / "intersections.csv"

    written = write_intersection_csv(merged_csv, out_csv)

    assert written == out_csv
    expected = intersection_table(merged_csv)
    actual = pd.read_csv(out_csv)
    assert_frame_equal(actual, expected)
