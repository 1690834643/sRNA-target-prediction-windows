"""QThread wrapper around `run_pipeline` so the GUI stays responsive."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal

from srna_win_target.backends.base import Backend
from srna_win_target.core.models import PredictionJob, ProgressEvent
from srna_win_target.core.pipeline import run_pipeline


class PipelineWorker(QThread):
    """Runs the prediction pipeline off the GUI thread.

    Signals:
        progress(ProgressEvent): every chunk transition.
        finished_ok(Path):       merged CSV path on success.
        failed(str):             error message on failure.

    The optional ``backend`` parameter is mainly a test seam: production GUI
    calls leave it None so the backend is built from ``job.backend``. Tests
    inject a ``FakeBackend`` so the worker can run end-to-end without any
    real tool.
    """

    progress = Signal(object)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, job: PredictionJob, backend: Optional[Backend] = None, parent=None):
        super().__init__(parent)
        self._job = job
        self._backend = backend

    def run(self) -> None:  # noqa: D401 — QThread entry point
        try:
            result = run_pipeline(
                self._job,
                backend=self._backend,
                on_progress=self._emit_progress,
            )
            self.finished_ok.emit(result)
        except Exception as exc:  # noqa: BLE001 — surface anything to the user
            self.failed.emit(f"{type(exc).__name__}: {exc}")

    def _emit_progress(self, event: ProgressEvent) -> None:
        self.progress.emit(event)
