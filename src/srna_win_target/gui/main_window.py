"""PySide6 main window for srna-win-target.

Three sections, top-to-bottom:
    1. Inputs    — miRNA FASTA, targets FASTA, output dir, workers, chunk size, backend
    2. Tools     — one expandable row per supported tool: enable / executable / params
    3. Run       — Run button, progress bar, scrollable log view

The pipeline runs in a `PipelineWorker` QThread so the UI stays responsive.
ProgressEvents are marshalled back via Qt signals. The File menu lets the
user load or save a TOML tool configuration that round-trips with the CLI.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from srna_win_target.core.models import (
    BackendKind,
    PredictionJob,
    ProgressEvent,
    RunStatus,
    ToolConfig,
)
from srna_win_target.gui.worker import PipelineWorker

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


# ----- Small helpers ---------------------------------------------------------


def _spin(default: int, lo: int = 0, hi: int = 100000) -> Callable[[], QSpinBox]:
    def factory() -> QSpinBox:
        w = QSpinBox()
        w.setRange(lo, hi)
        w.setValue(default)
        return w

    return factory


def _double(default: float, lo: float = -1000.0, hi: float = 1000.0, decimals: int = 2) -> Callable[[], QDoubleSpinBox]:
    def factory() -> QDoubleSpinBox:
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setDecimals(decimals)
        w.setValue(default)
        return w

    return factory


def _line(default: str = "") -> Callable[[], QLineEdit]:
    def factory() -> QLineEdit:
        w = QLineEdit()
        w.setText(default)
        return w

    return factory


def _bool() -> Callable[[], QCheckBox]:
    def factory() -> QCheckBox:
        return QCheckBox()

    return factory


# ----- Widgets ---------------------------------------------------------------


class _PathPicker(QWidget):
    """A line edit plus Browse button."""

    def __init__(self, mode: str, caption: str, parent=None):
        super().__init__(parent)
        self._mode = mode
        self._caption = caption
        self.line = QLineEdit(self)
        self.browse = QPushButton("Browse…", self)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.line, 1)
        layout.addWidget(self.browse)
        self.browse.clicked.connect(self._open_dialog)

    def _open_dialog(self) -> None:
        if self._mode == "file":
            path, _ = QFileDialog.getOpenFileName(self, self._caption)
        elif self._mode == "dir":
            path = QFileDialog.getExistingDirectory(self, self._caption)
        elif self._mode == "save":
            path, _ = QFileDialog.getSaveFileName(self, self._caption, filter="TOML (*.toml)")
        else:
            return
        if path:
            self.line.setText(path)

    def value(self) -> Optional[Path]:
        text = self.line.text().strip()
        return Path(text) if text else None

    def setText(self, value: str) -> None:  # noqa: N802 — Qt convention
        self.line.setText(value)


class _ToolRow(QWidget):
    """Enable checkbox + path picker + per-tool param form."""

    def __init__(
        self,
        label: str,
        mode: str,
        caption: str,
        params_spec: list[tuple[str, Callable[[], QWidget]]],
        parent=None,
    ):
        super().__init__(parent)
        self.tool_label = label
        self.enabled = QCheckBox(label, self)
        self.path = _PathPicker(mode=mode, caption=caption, parent=self)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self.enabled)
        top.addWidget(self.path, 1)

        params_form = QFormLayout()
        params_form.setContentsMargins(24, 0, 0, 6)
        self.params: dict[str, QWidget] = {}
        for name, factory in params_spec:
            widget = factory()
            params_form.addRow(name, widget)
            self.params[name] = widget

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.addLayout(top)
        layout.addLayout(params_form)

    def is_active(self) -> bool:
        return self.enabled.isChecked() and self.path.value() is not None

    def path_value(self) -> Optional[Path]:
        return self.path.value()

    def parameters(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, widget in self.params.items():
            if isinstance(widget, QCheckBox):
                if widget.isChecked():
                    result[name] = True
            elif isinstance(widget, QSpinBox):
                result[name] = widget.value()
            elif isinstance(widget, QDoubleSpinBox):
                result[name] = widget.value()
            elif isinstance(widget, QLineEdit):
                text = widget.text().strip()
                if text:
                    result[name] = text
        return result

    def set_parameters(self, values: dict[str, Any]) -> None:
        for name, value in values.items():
            widget = self.params.get(name)
            if widget is None:
                continue
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value))
            elif isinstance(widget, QLineEdit):
                widget.setText(str(value))


# ----- Main window -----------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("sRNA Windows Target Predictor")
        self.resize(900, 720)
        self._worker: Optional[PipelineWorker] = None

        central = QWidget(self)
        outer = QVBoxLayout(central)
        outer.addWidget(self._build_inputs_group())
        outer.addWidget(self._build_tools_group())
        outer.addWidget(self._build_run_group(), 1)
        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar(self))
        self._make_menu()

    # ----- UI construction ----------------------------------------------------

    def _build_inputs_group(self) -> QGroupBox:
        box = QGroupBox("Inputs", self)
        form = QFormLayout(box)

        self.mirna_picker = _PathPicker(mode="file", caption="Pick miRNA FASTA", parent=box)
        self.targets_picker = _PathPicker(mode="file", caption="Pick targets FASTA", parent=box)
        self.outdir_picker = _PathPicker(mode="dir", caption="Pick output folder", parent=box)
        self.outdir_picker.setText(str(Path.cwd() / "srna_target_results"))

        self.workers_spin = QSpinBox(box)
        self.workers_spin.setRange(1, 64)
        self.workers_spin.setValue(4)

        self.chunk_spin = QSpinBox(box)
        self.chunk_spin.setRange(1, 100000)
        self.chunk_spin.setValue(500)

        self.mirna_chunk_spin = QSpinBox(box)
        self.mirna_chunk_spin.setRange(0, 100000)
        self.mirna_chunk_spin.setValue(0)
        self.mirna_chunk_spin.setSpecialValueText("(whole file)")

        self.backend_combo = QComboBox(box)
        for kind in BackendKind:
            self.backend_combo.addItem(kind.value, kind)

        self.resume_checkbox = QCheckBox("Resume from manifest if available", box)
        self.resume_checkbox.setChecked(True)

        form.addRow("miRNA FASTA", self.mirna_picker)
        form.addRow("Targets FASTA", self.targets_picker)
        form.addRow("Output folder", self.outdir_picker)
        form.addRow("Workers", self.workers_spin)
        form.addRow("Target chunk size", self.chunk_spin)
        form.addRow("miRNA chunk size", self.mirna_chunk_spin)
        form.addRow("Backend", self.backend_combo)
        form.addRow("", self.resume_checkbox)
        return box

    def _build_tools_group(self) -> QGroupBox:
        box = QGroupBox("Tools", self)
        layout = QVBoxLayout(box)
        self.tool_miranda = _ToolRow(
            "miRanda",
            mode="file",
            caption="miRanda executable",
            params_spec=[
                ("score_cutoff", _spin(140, 0, 9999)),
                ("energy_cutoff", _double(-20.0, -500.0, 0.0, 2)),
                ("strict", _bool()),
            ],
            parent=box,
        )
        self.tool_rnahybrid = _ToolRow(
            "RNAhybrid",
            mode="file",
            caption="RNAhybrid executable",
            params_spec=[
                ("energy_cutoff", _double(-20.0, -500.0, 0.0, 2)),
                ("pvalue_cutoff", _double(0.1, 0.0, 1.0, 4)),
                ("set", _line("3utr_human")),
            ],
            parent=box,
        )
        self.tool_pita = _ToolRow(
            "PITA (pita_prediction.pl)",
            mode="file",
            caption="PITA script",
            params_spec=[
                ("perl", _line("perl")),
            ],
            parent=box,
        )
        layout.addWidget(self.tool_miranda)
        layout.addWidget(self.tool_rnahybrid)
        layout.addWidget(self.tool_pita)
        hint = QLabel(
            "Tick the tools you want to run and point each row at its binary or script. "
            "Under the WSL backend, paths can be Windows-style (C:\\…) or POSIX (/mnt/c/…).",
            box,
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return box

    def _build_run_group(self) -> QGroupBox:
        box = QGroupBox("Run", self)
        layout = QVBoxLayout(box)

        controls = QHBoxLayout()
        self.run_button = QPushButton("Run", box)
        self.cancel_button = QPushButton("Cancel", box)
        self.cancel_button.setEnabled(False)
        self.open_button = QPushButton("Open output folder", box)
        self.open_button.setEnabled(False)
        controls.addWidget(self.run_button)
        controls.addWidget(self.cancel_button)
        controls.addStretch(1)
        controls.addWidget(self.open_button)

        self.progress_bar = QProgressBar(box)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.log_view = QPlainTextEdit(box)
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(10000)

        layout.addLayout(controls)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_view, 1)

        self.run_button.clicked.connect(self.on_run)
        self.cancel_button.clicked.connect(self.on_cancel)
        self.open_button.clicked.connect(self.on_open_output)
        return box

    def _make_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        open_action = QAction("&Open config…", self)
        open_action.triggered.connect(self.on_open_config)
        save_action = QAction("&Save config as…", self)
        save_action.triggered.connect(self.on_save_config)
        quit_action = QAction("&Quit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

    # ----- TOML I/O -----------------------------------------------------------

    @Slot()
    def on_open_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open config", filter="TOML (*.toml)")
        if not path:
            return
        try:
            with open(path, "rb") as handle:
                data = tomllib.load(handle)
        except Exception as exc:
            QMessageBox.critical(self, "Load config", f"Could not parse {path}: {exc}")
            return
        self._apply_config_dict(data)
        self.statusBar().showMessage(f"Loaded {path}")

    @Slot()
    def on_save_config(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save config", filter="TOML (*.toml)")
        if not path:
            return
        try:
            Path(path).write_text(_serialize_toml(self._collect_config_dict()), encoding="utf-8")
        except Exception as exc:
            QMessageBox.critical(self, "Save config", f"Could not write {path}: {exc}")
            return
        self.statusBar().showMessage(f"Saved {path}")

    def _apply_config_dict(self, data: dict) -> None:
        for section_key, row in [
            ("miranda", self.tool_miranda),
            ("rnahybrid", self.tool_rnahybrid),
            ("pita", self.tool_pita),
        ]:
            section = data.get(section_key, {})
            if not section:
                continue
            row.enabled.setChecked(True)
            # Path comes from `exe` (miranda/rnahybrid) or `script` (pita).
            path_value = section.get("exe") or section.get("script")
            if path_value:
                row.path.setText(str(path_value))
            params = {k: v for k, v in section.items() if k not in ("exe", "script")}
            row.set_parameters(params)

    def _collect_config_dict(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        if self.tool_miranda.is_active():
            section = {"exe": str(self.tool_miranda.path_value())}
            section.update(self.tool_miranda.parameters())
            result["miranda"] = section
        if self.tool_rnahybrid.is_active():
            section = {"exe": str(self.tool_rnahybrid.path_value())}
            section.update(self.tool_rnahybrid.parameters())
            result["rnahybrid"] = section
        if self.tool_pita.is_active():
            section = {"script": str(self.tool_pita.path_value())}
            section.update(self.tool_pita.parameters())
            result["pita"] = section
        return result

    # ----- Run / cancel / progress -------------------------------------------

    @Slot()
    def on_run(self) -> None:
        job = self._collect_job()
        if job is None:
            return

        self.log_view.clear()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.open_button.setEnabled(False)
        self.statusBar().showMessage("Running…")

        self._worker = PipelineWorker(job, parent=self)
        self._worker.progress.connect(self.on_progress)
        self._worker.finished_ok.connect(self.on_finished_ok)
        self._worker.failed.connect(self.on_failed)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    @Slot()
    def on_cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
            self.log_view.appendPlainText(
                "[cancel] Cancellation requested. Running chunks will finish, no new ones will start."
            )

    @Slot(object)
    def on_progress(self, event: ProgressEvent) -> None:
        if event.total:
            self.progress_bar.setRange(0, event.total)
            self.progress_bar.setValue(event.completed)
        tag = {
            RunStatus.PENDING: "queued",
            RunStatus.RUNNING: "run",
            RunStatus.COMPLETED: "done",
            RunStatus.SKIPPED: "skip",
            RunStatus.FAILED: "fail",
        }.get(event.status, str(event.status))
        line = f"[{tag}] {event.tool} {event.chunk_id}"
        if event.message:
            line += f"  {event.message}"
        self.log_view.appendPlainText(line)

    @Slot(object)
    def on_finished_ok(self, merged: Path) -> None:
        self.log_view.appendPlainText(f"[ok] Merged predictions: {merged}")
        self.statusBar().showMessage(f"Done: {merged.name}")
        self.open_button.setEnabled(True)
        self._last_output_dir = merged.parent

    @Slot(str)
    def on_failed(self, message: str) -> None:
        self.log_view.appendPlainText(f"[error] {message}")
        self.statusBar().showMessage("Failed")
        QMessageBox.critical(self, "Pipeline error", message)

    @Slot()
    def on_open_output(self) -> None:
        if not hasattr(self, "_last_output_dir"):
            return
        path = self._last_output_dir
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices

            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        except Exception as exc:  # pragma: no cover
            QMessageBox.warning(self, "Open folder", f"Could not open {path}: {exc}")

    @Slot()
    def _on_worker_finished(self) -> None:
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    # ----- Job assembly -------------------------------------------------------

    def _collect_job(self) -> Optional[PredictionJob]:
        mirna = self.mirna_picker.value()
        targets = self.targets_picker.value()
        out = self.outdir_picker.value()

        missing = []
        if mirna is None or not mirna.exists():
            missing.append("miRNA FASTA")
        if targets is None or not targets.exists():
            missing.append("targets FASTA")
        if out is None:
            missing.append("output folder")
        if missing:
            QMessageBox.warning(self, "Missing inputs", "Set: " + ", ".join(missing))
            return None

        tools: list[ToolConfig] = []
        if self.tool_miranda.is_active():
            tools.append(
                ToolConfig(
                    name="miranda",
                    executable=self.tool_miranda.path_value(),
                    parameters=self.tool_miranda.parameters(),
                )
            )
        if self.tool_rnahybrid.is_active():
            tools.append(
                ToolConfig(
                    name="rnahybrid",
                    executable=self.tool_rnahybrid.path_value(),
                    parameters=self.tool_rnahybrid.parameters(),
                )
            )
        if self.tool_pita.is_active():
            params = {"script": str(self.tool_pita.path_value())}
            params.update(self.tool_pita.parameters())
            tools.append(ToolConfig(name="pita", parameters=params))
        if not tools:
            QMessageBox.warning(self, "No tools", "Tick at least one tool to run.")
            return None

        backend = self.backend_combo.currentData()
        return PredictionJob(
            mirna_fasta=mirna,
            target_fasta=targets,
            out_dir=out,
            tools=tools,
            workers=self.workers_spin.value(),
            chunk_size=self.chunk_spin.value(),
            mirna_chunk_size=self.mirna_chunk_spin.value(),
            resume=self.resume_checkbox.isChecked(),
            backend=backend,
        )


# ----- Tiny TOML writer ------------------------------------------------------


def _serialize_toml(data: dict[str, dict[str, Any]]) -> str:
    """Minimal TOML serializer for shallow {section: {key: value}} dicts."""
    lines: list[str] = []
    for section, body in data.items():
        if not body:
            continue
        lines.append(f"[{section}]")
        for key, value in body.items():
            if isinstance(value, bool):
                lines.append(f"{key} = {str(value).lower()}")
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                lines.append(f"{key} = {value}")
            else:
                escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'{key} = "{escaped}"')
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
