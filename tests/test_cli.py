from __future__ import annotations

from pathlib import Path

import pytest

from typer.testing import CliRunner

from srna_win_target.cli.app import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _write(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_cli_help_lists_subcommands(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "predict" in result.output
    assert "validate-tools" in result.output


def test_predict_dry_run_lists_planned_commands(runner: CliRunner, tmp_path: Path) -> None:
    mirna = _write(tmp_path / "mirna.fa", ">m1\nACGU\n")
    targets = _write(tmp_path / "targets.fa", ">t1\nACGUACGU\n>t2\nACGUACGU\n")
    config = _write(
        tmp_path / "tools.toml",
        '[miranda]\nexe = "/bin/true"\nscore_cutoff = 140\n',
    )

    result = runner.invoke(
        app,
        [
            "predict",
            "--mirna",
            str(mirna),
            "--targets",
            str(targets),
            "--out",
            str(tmp_path / "out"),
            "--config",
            str(config),
            "--chunk-size",
            "1",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "dry-run" in result.output
    # Two chunks of 1 target each, one command per chunk for miranda.
    assert result.output.count("miranda_targets.chunk_") >= 2


def test_validate_tools_reports_missing_executable(runner: CliRunner, tmp_path: Path) -> None:
    config = _write(
        tmp_path / "tools.toml",
        '[miranda]\nexe = "/does/not/exist"\n',
    )
    result = runner.invoke(app, ["validate-tools", "--config", str(config)])
    assert result.exit_code == 0
    assert "miranda" in result.output
    assert "fail" in result.output
