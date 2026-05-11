from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("matplotlib")
pytest.importorskip("matplotlib_venn")
pytest.importorskip("upsetplot")

from srna_win_target.results.visualize import make_intersection_plot


def write_merged_csv(path: Path, rows: list[tuple[str, str, str]]) -> Path:
    lines = ["tool,mirna_id,target_id,start,end,score,energy,pvalue,raw_file,chunk_id"]
    lines.extend(
        f"{tool},{mirna},{target},1,20,,,,{tool}.out,chunk-a" for tool, mirna, target in rows
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_two_tool_csv_creates_venn_png(tmp_path: Path) -> None:
    merged_csv = write_merged_csv(
        tmp_path / "merged_predictions.csv",
        [
            ("miranda", "m1", "t1"),
            ("miranda", "m2", "t2"),
            ("pita", "m1", "t1"),
            ("pita", "m3", "t3"),
        ],
    )

    created = make_intersection_plot(merged_csv, tmp_path)

    assert created == [tmp_path / "venn.png"]
    assert (tmp_path / "venn.png").exists()


def test_four_tool_csv_creates_upset_png(tmp_path: Path) -> None:
    merged_csv = write_merged_csv(
        tmp_path / "merged_predictions.csv",
        [
            ("miranda", "m1", "t1"),
            ("rnahybrid", "m1", "t1"),
            ("pita", "m1", "t1"),
            ("intarna", "m1", "t1"),
            ("miranda", "m2", "t2"),
            ("pita", "m2", "t2"),
        ],
    )

    created = make_intersection_plot(merged_csv, tmp_path)

    assert created == [tmp_path / "upset.png"]
    assert (tmp_path / "upset.png").exists()


def test_one_tool_csv_returns_no_plots(tmp_path: Path) -> None:
    merged_csv = write_merged_csv(
        tmp_path / "merged_predictions.csv",
        [
            ("miranda", "m1", "t1"),
            ("miranda", "m2", "t2"),
        ],
    )

    created = make_intersection_plot(merged_csv, tmp_path)

    assert created == []
    assert not (tmp_path / "venn.png").exists()
    assert not (tmp_path / "upset.png").exists()
