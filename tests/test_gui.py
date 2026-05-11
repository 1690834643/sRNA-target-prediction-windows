"""GUI smoke tests. Skipped automatically when PySide6 is not installed.

These tests build the main window in offscreen mode and exercise the
job-collection path. They never block on event loop or render anything
to a real screen, so they are safe to run in CI.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

# Force offscreen Qt before PySide6 is imported.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from srna_win_target.core.models import BackendKind, PredictionJob  # noqa: E402
from srna_win_target.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_main_window_builds(qapp) -> None:
    w = MainWindow()
    try:
        assert w.windowTitle() == "sRNA Windows Target Predictor"
        # Expected widgets exist.
        assert w.mirna_picker is not None
        assert w.targets_picker is not None
        assert w.outdir_picker is not None
        assert w.tool_miranda is not None
        assert w.tool_rnahybrid is not None
        assert w.tool_pita is not None
        assert w.run_button.isEnabled()
        assert not w.cancel_button.isEnabled()
    finally:
        w.deleteLater()


def test_collect_job_returns_none_when_inputs_missing(qapp, monkeypatch) -> None:
    """Missing FASTAs/output should pop a warning and return None, not raise."""
    import srna_win_target.gui.main_window as mod

    monkeypatch.setattr(mod.QMessageBox, "warning", lambda *a, **kw: None)

    w = MainWindow()
    try:
        assert w._collect_job() is None
    finally:
        w.deleteLater()


def test_collect_job_assembles_prediction_job(qapp, monkeypatch, tmp_path: Path) -> None:
    """With FASTAs + one tool ticked, _collect_job should return a real PredictionJob."""
    import srna_win_target.gui.main_window as mod

    monkeypatch.setattr(mod.QMessageBox, "warning", lambda *a, **kw: None)

    mirna = tmp_path / "m.fa"
    targets = tmp_path / "t.fa"
    mirna.write_text(">m1\nACGU\n", encoding="utf-8")
    targets.write_text(">t1\nACGUACGU\n", encoding="utf-8")
    fake_miranda = tmp_path / "miranda-fake"
    fake_miranda.write_text("# placeholder", encoding="utf-8")

    w = MainWindow()
    try:
        w.mirna_picker.setText(str(mirna))
        w.targets_picker.setText(str(targets))
        w.outdir_picker.setText(str(tmp_path / "out"))
        w.tool_miranda.path.setText(str(fake_miranda))
        w.tool_miranda.enabled.setChecked(True)
        w.workers_spin.setValue(2)
        w.chunk_spin.setValue(10)

        job = w._collect_job()
        assert isinstance(job, PredictionJob)
        assert job.mirna_fasta == mirna
        assert job.target_fasta == targets
        assert job.workers == 2
        assert job.chunk_size == 10
        assert job.backend == BackendKind.LOCAL
        assert len(job.tools) == 1
        assert job.tools[0].name == "miranda"
        assert job.tools[0].executable == fake_miranda
    finally:
        w.deleteLater()
