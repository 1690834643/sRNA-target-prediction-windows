"""End-to-end GUI integration test: simulate clicking Run, drive the
PipelineWorker against an in-process FakeBackend, then assert the log view
shows the success line and the merged CSV exists.

Skipped automatically when PySide6 is not installed.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from srna_win_target.cli._selftest import FakeBackend  # noqa: E402
from srna_win_target.gui.main_window import MainWindow  # noqa: E402
from srna_win_target.gui.worker import PipelineWorker  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _wait_for(signal, timeout_ms: int = 5000):
    """Block the event loop until ``signal`` fires or timeout elapses."""
    loop = QEventLoop()
    captured: dict[str, object] = {}

    def _capture(*args):
        captured["args"] = args
        loop.quit()

    signal.connect(_capture)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    return captured.get("args")


def test_main_window_run_drives_pipeline_to_completion(qapp, monkeypatch, tmp_path: Path) -> None:
    """Click Run -> worker runs -> finished_ok fires -> log shows merged CSV."""
    mirna = tmp_path / "m.fa"
    targets = tmp_path / "t.fa"
    out_dir = tmp_path / "out"
    mirna.write_text(">m1\nACGUACGU\n>m2\nUUUUACGU\n", encoding="utf-8")
    targets.write_text(">t1\nACGUACGUACGU\n>t2\nACGUACGUACGU\n>t3\nUUUUACGUACGU\n", encoding="utf-8")
    fake_exe = tmp_path / "fake_miranda"
    fake_exe.write_text("# placeholder", encoding="utf-8")

    # Patch PipelineWorker so the GUI's worker construction injects FakeBackend.
    import srna_win_target.gui.main_window as mod

    original = mod.PipelineWorker

    def _make_worker(job, parent=None):
        return original(job, backend=FakeBackend(hits_per_chunk=2), parent=parent)

    monkeypatch.setattr(mod, "PipelineWorker", _make_worker)

    w = MainWindow()
    try:
        w.mirna_picker.setText(str(mirna))
        w.targets_picker.setText(str(targets))
        w.outdir_picker.setText(str(out_dir))
        w.chunk_spin.setValue(2)
        w.workers_spin.setValue(1)
        w.tool_miranda.path.setText(str(fake_exe))
        w.tool_miranda.enabled.setChecked(True)

        w.on_run()                                # synchronous: kicks worker off
        assert w._worker is not None
        result = _wait_for(w._worker.finished_ok, timeout_ms=10000)
        assert result is not None, "worker never emitted finished_ok"
        merged_csv = result[0]
        assert merged_csv.exists()

        # Final log line should include the ok marker.
        log_text = w.log_view.toPlainText()
        assert "[ok] Merged predictions" in log_text
        # And some chunk-level events should have shown up.
        assert "[done]" in log_text or "[run]" in log_text or "[queued]" in log_text
    finally:
        if w._worker is not None:
            w._worker.wait(3000)
        w.deleteLater()


def test_collect_config_dict_includes_params(qapp, tmp_path: Path) -> None:
    fake_exe = tmp_path / "miranda-exe"
    fake_exe.write_text("# placeholder", encoding="utf-8")
    w = MainWindow()
    try:
        w.tool_miranda.path.setText(str(fake_exe))
        w.tool_miranda.enabled.setChecked(True)
        w.tool_miranda.set_parameters({"score_cutoff": 175, "energy_cutoff": -25.0, "strict": True})

        cfg = w._collect_config_dict()
        assert "miranda" in cfg
        section = cfg["miranda"]
        assert section["exe"] == str(fake_exe)
        assert section["score_cutoff"] == 175
        assert section["energy_cutoff"] == -25.0
        assert section["strict"] is True
    finally:
        w.deleteLater()


def test_apply_config_dict_populates_widgets(qapp, tmp_path: Path) -> None:
    w = MainWindow()
    try:
        w._apply_config_dict(
            {
                "miranda": {"exe": "/tmp/miranda", "score_cutoff": 200, "energy_cutoff": -30.0},
                "pita": {"script": "/tmp/pita.pl", "perl": "/usr/bin/perl"},
            }
        )
        assert w.tool_miranda.enabled.isChecked()
        assert w.tool_miranda.path.value() == Path("/tmp/miranda")
        assert w.tool_miranda.params["score_cutoff"].value() == 200
        assert w.tool_miranda.params["energy_cutoff"].value() == -30.0

        assert w.tool_pita.enabled.isChecked()
        assert w.tool_pita.path.value() == Path("/tmp/pita.pl")
        assert w.tool_pita.params["perl"].text() == "/usr/bin/perl"

        # rnahybrid section was absent -> stays disabled.
        assert not w.tool_rnahybrid.enabled.isChecked()
    finally:
        w.deleteLater()


def test_toml_round_trip_via_files(qapp, tmp_path: Path) -> None:
    """Write current GUI state to TOML, reload it into a fresh window, fields match."""
    from srna_win_target.gui.main_window import _serialize_toml

    fake_exe = tmp_path / "miranda-exe"
    fake_exe.write_text("# placeholder", encoding="utf-8")
    src = MainWindow()
    try:
        src.tool_miranda.path.setText(str(fake_exe))
        src.tool_miranda.enabled.setChecked(True)
        src.tool_miranda.set_parameters({"score_cutoff": 175, "energy_cutoff": -25.0, "strict": True})

        config_path = tmp_path / "tools.toml"
        config_path.write_text(_serialize_toml(src._collect_config_dict()), encoding="utf-8")

        # Parse back via tomllib and apply to a new window.
        import tomllib

        loaded = tomllib.loads(config_path.read_text(encoding="utf-8"))
        dst = MainWindow()
        try:
            dst._apply_config_dict(loaded)
            assert dst.tool_miranda.enabled.isChecked()
            assert dst.tool_miranda.path.value() == fake_exe
            assert dst.tool_miranda.params["score_cutoff"].value() == 175
            assert dst.tool_miranda.params["energy_cutoff"].value() == -25.0
            assert dst.tool_miranda.params["strict"].isChecked()
        finally:
            dst.deleteLater()
    finally:
        src.deleteLater()
