"""FastAPI app exposing the prediction pipeline over HTTP + WebSocket.

Endpoints:
    GET  /                          serves the SPA shell
    GET  /static/*                  static assets
    GET  /api/discover              bundled-tools auto-discovery + defaults
    POST /api/pick-file             native file/folder picker (server-side)
    POST /api/predict               start a job, returns {"job_id": ...}
    GET  /api/jobs/{id}             current status snapshot
    WS   /api/jobs/{id}/events      streams ProgressEvents as JSON
    GET  /api/jobs/{id}/download    download merged_predictions.csv
    POST /api/open-folder           open output folder in the OS file manager
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from srna_win_target.core.models import (
    BackendKind,
    PredictionJob,
    ProgressEvent,
    RunStatus,
    ToolConfig,
)
from srna_win_target.core.pipeline import run_pipeline
from srna_win_target.data.format_check import (
    FastaValidationError,
    validate_input_fasta,
)
from srna_win_target.web.discover import (
    discover_bundled_tools,
    environment_summary,
)

STATIC_DIR = Path(__file__).parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"

app = FastAPI(title="sRNA Windows Target Predictor")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Tkinter root must be touched from a single thread at a time.
_TK_LOCK = threading.Lock()


# ----- Job registry ---------------------------------------------------------


@dataclass
class JobState:
    job_id: str
    status: str = "queued"
    merged_csv: Optional[Path] = None
    report_html: Optional[Path] = None
    error: Optional[str] = None
    events: list[dict] = field(default_factory=list)
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    loop: Optional[asyncio.AbstractEventLoop] = None


JOBS: dict[str, JobState] = {}


# ----- Helpers --------------------------------------------------------------


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_under_bundled_tools(p: Path) -> bool:
    """True iff `p` resolves to a file inside the local bundled_tools/ tree.

    Used as an allowlist gate for caller-supplied tool/script/perl paths: the
    local HTTP server trusts only its own bundle, not arbitrary disk files.
    """
    try:
        from srna_win_target.web.discover import get_app_dir
        bundled_root = (get_app_dir() / "bundled_tools").resolve(strict=False)
        return bundled_root in p.resolve(strict=False).parents or p.resolve(strict=False) == bundled_root
    except Exception:  # noqa: BLE001
        return False


def _build_job(payload: dict[str, Any]) -> PredictionJob:
    required = ["mirna", "targets", "out"]
    for key in required:
        if not payload.get(key):
            raise HTTPException(400, f"missing field: {key}")

    try:
        validate_input_fasta(Path(payload["mirna"]), role="miRNA FASTA")
        validate_input_fasta(Path(payload["targets"]), role="Targets FASTA")
    except FastaValidationError as exc:
        raise HTTPException(422, str(exc)) from exc

    discovered = discover_bundled_tools()
    tools_cfg = payload.get("tools") or {}
    tools: list[ToolConfig] = []

    def _resolve_tool_path(provided: str, discovered_path: Optional[Path], label: str) -> Path:
        """Resolve a tool binary path. Caller-supplied paths must live under
        bundled_tools/. If the user didn't supply one, fall back to discovered.
        Defends against `/api/predict {"miranda":{"exe": "/usr/bin/python"}}`.
        """
        if provided:
            cand = Path(provided)
            if not _is_under_bundled_tools(cand):
                raise HTTPException(
                    403,
                    f"{label}: 自定义路径必须位于 bundled_tools/ 之内，拒绝 {cand}",
                )
            return cand
        if discovered_path is None:
            raise HTTPException(
                400, f"{label}: bundle 中未找到可用二进制，且请求未提供路径"
            )
        return discovered_path

    if "miranda" in tools_cfg:
        cfg = tools_cfg["miranda"]
        d = discovered.get("miranda")
        exe = _resolve_tool_path(
            _coerce_str(cfg.get("exe")),
            d.executable if (d and d.ready) else None,
            "miranda",
        )
        tools.append(
            ToolConfig(
                name="miranda",
                executable=exe,
                parameters={k: v for k, v in cfg.items() if k != "exe"},
            )
        )
    if "rnahybrid" in tools_cfg:
        cfg = tools_cfg["rnahybrid"]
        d = discovered.get("rnahybrid")
        exe = _resolve_tool_path(
            _coerce_str(cfg.get("exe")),
            d.executable if (d and d.ready) else None,
            "rnahybrid",
        )
        tools.append(
            ToolConfig(
                name="rnahybrid",
                executable=exe,
                parameters={k: v for k, v in cfg.items() if k != "exe"},
            )
        )
    if "pita" in tools_cfg:
        cfg = tools_cfg["pita"]
        d = discovered.get("pita")
        script_path = _resolve_tool_path(
            _coerce_str(cfg.get("script")),
            d.script if (d and d.ready) else None,
            "pita.script",
        )
        perl_provided = _coerce_str(cfg.get("perl"))
        perl_path = _resolve_tool_path(
            perl_provided,
            d.bundled_perl if (d and d.ready) else None,
            "pita.perl",
        )
        params: dict[str, Any] = {"script": str(script_path), "perl": str(perl_path)}
        for k, v in cfg.items():
            if k not in ("script", "perl"):
                params[k] = v
        tools.append(ToolConfig(name="pita", parameters=params))
    if not tools:
        raise HTTPException(400, "configure at least one tool")

    try:
        backend = BackendKind(payload.get("backend", "local"))
    except ValueError as exc:
        raise HTTPException(400, f"invalid backend: {exc}")

    return PredictionJob(
        mirna_fasta=Path(payload["mirna"]),
        target_fasta=Path(payload["targets"]),
        out_dir=Path(payload["out"]),
        tools=tools,
        workers=int(payload.get("workers", 4)),
        chunk_size=int(payload.get("chunk_size", 500)),
        mirna_chunk_size=int(payload.get("mirna_chunk_size", 0)),
        resume=bool(payload.get("resume", True)),
        backend=backend,
    )


def _broadcast(state: JobState, message: dict[str, Any]) -> None:
    with state.lock:
        state.events.append(message)
    if state.loop is None:
        return
    for queue in list(state.subscribers):
        try:
            state.loop.call_soon_threadsafe(queue.put_nowait, message)
        except RuntimeError:  # event loop closed
            pass


def _run_job(state: JobState, job: PredictionJob) -> None:
    state.status = "running"
    _broadcast(state, {"type": "status", "status": "running"})

    def emit(event: ProgressEvent) -> None:
        _broadcast(
            state,
            {
                "type": "progress",
                "chunk_id": event.chunk_id,
                "tool": event.tool,
                "status": event.status.value if isinstance(event.status, RunStatus) else str(event.status),
                "completed": event.completed,
                "total": event.total,
                "message": event.message,
            },
        )

    try:
        merged = run_pipeline(job, on_progress=emit)
        state.merged_csv = merged
        report_candidate = merged.parent / "predictions.html"
        if report_candidate.exists():
            state.report_html = report_candidate
        state.status = "completed"
        _broadcast(state, {
            "type": "done",
            "merged_csv": str(merged),
            "report_html": str(state.report_html) if state.report_html else None,
        })
    except Exception as exc:  # noqa: BLE001
        state.error = f"{type(exc).__name__}: {exc}"
        state.status = "failed"
        _broadcast(state, {"type": "error", "message": state.error})


# ----- Routes ---------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


@app.post("/api/predict")
async def predict(payload: dict[str, Any]) -> dict[str, str]:
    job = _build_job(payload)
    job_id = uuid.uuid4().hex[:12]
    state = JobState(job_id=job_id)
    state.loop = asyncio.get_running_loop()
    JOBS[job_id] = state

    thread = threading.Thread(target=_run_job, args=(state, job), daemon=True)
    thread.start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict[str, Any]:
    state = JOBS.get(job_id)
    if state is None:
        raise HTTPException(404, "unknown job")
    with state.lock:
        return {
            "job_id": state.job_id,
            "status": state.status,
            "merged_csv": str(state.merged_csv) if state.merged_csv else None,
            "error": state.error,
            "event_count": len(state.events),
        }


@app.get("/api/jobs/{job_id}/download")
def job_download(job_id: str):
    state = JOBS.get(job_id)
    if state is None or state.merged_csv is None:
        raise HTTPException(404, "no merged CSV for this job")
    if not state.merged_csv.exists():
        raise HTTPException(410, "merged CSV no longer on disk")
    return FileResponse(
        path=str(state.merged_csv),
        filename=state.merged_csv.name,
        media_type="text/csv",
    )


@app.get("/api/jobs/{job_id}/report", response_class=HTMLResponse)
def job_report(job_id: str):
    """Serve predictions.html inline (text/html) for in-browser viewing."""
    state = JOBS.get(job_id)
    if state is None or state.report_html is None:
        raise HTTPException(404, "no report for this job")
    if not state.report_html.exists():
        raise HTTPException(410, "report no longer on disk")
    return state.report_html.read_text(encoding="utf-8")


@app.websocket("/api/jobs/{job_id}/events")
async def job_events(ws: WebSocket, job_id: str) -> None:
    if job_id not in JOBS:
        await ws.close(code=4404)
        return
    state = JOBS[job_id]
    await ws.accept()
    queue: asyncio.Queue = asyncio.Queue()
    state.subscribers.append(queue)
    try:
        # Replay backlog first so a late subscriber doesn't miss prior events.
        with state.lock:
            backlog = list(state.events)
        for message in backlog:
            await ws.send_json(message)
        # Then stream new events.
        while True:
            message = await queue.get()
            await ws.send_json(message)
            if message.get("type") in ("done", "error"):
                break
    except WebSocketDisconnect:
        pass
    finally:
        if queue in state.subscribers:
            state.subscribers.remove(queue)
        try:
            await ws.close()
        except Exception:  # pragma: no cover
            pass


@app.get("/api/healthz")
def healthz() -> JSONResponse:
    return JSONResponse({"ok": True, "jobs": len(JOBS)})


@app.get("/api/discover")
def discover() -> JSONResponse:
    """Bundled-tools status + default output dir + example inputs."""
    return JSONResponse(environment_summary())


# ---- Native file picker ----------------------------------------------------
#
# Browsers don't expose the absolute path of files selected via <input type=
# "file">, so we drive a server-side Tk dialog instead. This works on the
# Windows portable build (tkinter is part of stdlib) as long as the .spec
# adds tkinter to hiddenimports.


_FILETYPES = {
    "fasta": [["FASTA", "*.fa *.fasta *.fna *.fastq *.fq *.txt"], ["All files", "*.*"]],
    "any": [["All files", "*.*"]],
}


def _open_tk_dialog(mode: str, title: str, initialdir: str, filetypes_key: str) -> str:
    """Open a single native dialog and return the picked path (or '' on cancel)."""
    import tkinter as tk
    from tkinter import filedialog

    types = _FILETYPES.get(filetypes_key, _FILETYPES["any"])
    with _TK_LOCK:
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            raise RuntimeError(f"cannot initialise Tk display: {exc}") from exc
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        try:
            if mode == "file":
                path = filedialog.askopenfilename(
                    parent=root,
                    title=title,
                    initialdir=initialdir,
                    filetypes=[tuple(t) for t in types],
                )
            elif mode == "dir":
                path = filedialog.askdirectory(
                    parent=root, title=title, initialdir=initialdir, mustexist=False
                )
            elif mode == "save":
                path = filedialog.asksaveasfilename(
                    parent=root,
                    title=title,
                    initialdir=initialdir,
                    filetypes=[tuple(t) for t in types],
                )
            else:
                path = ""
        finally:
            try:
                root.destroy()
            except Exception:
                pass
    return path or ""


@app.post("/api/pick-file")
def pick_file(payload: dict[str, Any]) -> dict[str, str]:
    mode = payload.get("mode", "file")
    if mode not in ("file", "dir", "save"):
        raise HTTPException(400, f"invalid mode: {mode}")
    title = payload.get("title") or {
        "file": "Select a file",
        "dir": "Select a folder",
        "save": "Save as",
    }[mode]
    initialdir = _coerce_str(payload.get("initialdir")) or str(Path.home())
    filetypes_key = payload.get("filetypes") or "any"
    try:
        picked = _open_tk_dialog(mode, str(title), initialdir, str(filetypes_key))
    except Exception as exc:  # pragma: no cover — Tk may be absent in dev
        raise HTTPException(503, f"native file dialog unavailable: {exc}")
    return {"path": picked}


@app.post("/api/open-folder")
def open_folder(payload: dict[str, Any]) -> dict[str, bool]:
    """Open the OS file manager at a job output dir.

    Restricted: only paths that are the `out_dir` of a known job (or a
    descendant) are allowed. This prevents a curious local caller from
    coercing the server into shell-opening arbitrary disk paths
    (e.g. `os.startfile(r"C:\\Windows\\System32\\cmd.exe")`).
    """
    target = _coerce_str(payload.get("path"))
    if not target:
        raise HTTPException(400, "missing field: path")
    p = Path(target)
    if not p.exists():
        raise HTTPException(404, f"path does not exist: {p}")
    if not p.is_dir():
        raise HTTPException(400, f"path is not a directory: {p}")
    try:
        target_resolved = p.resolve(strict=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"cannot resolve path: {exc}")

    # Allowlist: the path must be (or live under) some active job's output dir.
    allowed = False
    for state in JOBS.values():
        merged = state.merged_csv
        if merged is None:
            continue
        try:
            job_root = merged.parent.parent.resolve(strict=False)  # results/.. → out_dir
        except Exception:  # noqa: BLE001
            continue
        if target_resolved == job_root or job_root in target_resolved.parents:
            allowed = True
            break
    if not allowed:
        raise HTTPException(
            403,
            f"open-folder is restricted to known job output directories; "
            f"{target_resolved} matches none",
        )

    # Reject UNC / network shares — `os.startfile` would launch a shell
    # handler that we don't want to expose.
    if sys.platform.startswith("win") and str(target_resolved).startswith("\\\\"):
        raise HTTPException(403, "UNC / network paths are not allowed")

    try:
        if sys.platform.startswith("win"):
            os.startfile(str(target_resolved))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target_resolved)])
        else:
            subprocess.Popen(["xdg-open", str(target_resolved)])
    except Exception as exc:  # pragma: no cover
        raise HTTPException(500, f"could not open folder: {exc}")
    return {"ok": True}
