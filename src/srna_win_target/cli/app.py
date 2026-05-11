from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import typer

import csv
import tempfile

from srna_win_target.backends import build_backend
from srna_win_target.cli._selftest import run_selftest
from srna_win_target.core.models import (
    BackendKind,
    PredictionJob,
    ProgressEvent,
    RunStatus,
    ToolConfig,
)
from srna_win_target.core.pipeline import run_pipeline
from srna_win_target.data.fasta_split import split_fasta
from srna_win_target.data.format_check import normalize_input_fasta
from srna_win_target.parallel.scheduler import build_chunk_jobs
from srna_win_target.tools.registry import build_runner

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - fallback for 3.10
    import tomli as tomllib  # type: ignore[no-redef]

app = typer.Typer(help="Windows wrapper for sRNA/miRNA target prediction tools.")


def _load_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.exists():
        raise typer.BadParameter(f"Config file not found: {path}")
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _tools_from_config_and_flags(
    cfg: dict[str, Any],
    miranda_exe: Path | None,
    rnahybrid_exe: Path | None,
    pita_script: Path | None,
    intarna_exe: Path | None,
) -> list[ToolConfig]:
    tools: list[ToolConfig] = []

    miranda_cfg = cfg.get("miranda", {})
    miranda_path = miranda_exe or _maybe_path(miranda_cfg.get("exe"))
    if miranda_path is not None:
        tools.append(
            ToolConfig(
                name="miranda",
                executable=miranda_path,
                parameters={
                    k: v for k, v in miranda_cfg.items() if k != "exe"
                },
            )
        )

    rnahybrid_cfg = cfg.get("rnahybrid", {})
    rnahybrid_path = rnahybrid_exe or _maybe_path(rnahybrid_cfg.get("exe"))
    if rnahybrid_path is not None:
        tools.append(
            ToolConfig(
                name="rnahybrid",
                executable=rnahybrid_path,
                parameters={
                    k: v for k, v in rnahybrid_cfg.items() if k != "exe"
                },
            )
        )

    pita_cfg = cfg.get("pita", {})
    pita_path = pita_script or _maybe_path(pita_cfg.get("script"))
    if pita_path is not None:
        params: dict[str, Any] = {"script": str(pita_path)}
        if "perl" in pita_cfg:
            params["perl"] = pita_cfg["perl"]
        tools.append(ToolConfig(name="pita", parameters=params))

    intarna_cfg = cfg.get("intarna", {})
    intarna_path = intarna_exe or _maybe_path(intarna_cfg.get("exe"))
    if intarna_path is not None:
        tools.append(
            ToolConfig(
                name="intarna",
                executable=intarna_path,
                parameters={k: v for k, v in intarna_cfg.items() if k != "exe"},
            )
        )

    return tools


def _maybe_path(value: Any) -> Path | None:
    if value is None:
        return None
    return Path(str(value))


@app.command()
def predict(
    mirna: Path = typer.Option(..., exists=True, help="miRNA/sRNA FASTA file"),
    targets: Path = typer.Option(..., exists=True, help="Target or 3UTR FASTA file"),
    out: Path = typer.Option(Path("srna_target_results"), help="Output directory"),
    workers: int = typer.Option(4, min=1, help="Parallel subprocess workers"),
    chunk_size: int = typer.Option(500, min=1, help="Target records per chunk"),
    mirna_chunk_size: int = typer.Option(
        0, min=0,
        help="If >0, also split the miRNA FASTA into chunks of this size for matrix parallelism.",
    ),
    backend: BackendKind = typer.Option(BackendKind.LOCAL, help="Execution backend"),
    config: Path | None = typer.Option(None, exists=False, help="TOML tool config"),
    miranda_exe: Path | None = typer.Option(None, help="Path to miRanda executable"),
    rnahybrid_exe: Path | None = typer.Option(None, help="Path to RNAhybrid executable"),
    pita_script: Path | None = typer.Option(None, help="Path to PITA script"),
    intarna_exe: Path | None = typer.Option(None, help="Path to IntaRNA executable"),
    no_resume: bool = typer.Option(False, help="Force re-run; ignore manifest"),
    quiet: bool = typer.Option(False, help="Suppress progress events"),
    dry_run: bool = typer.Option(False, help="Print planned commands and exit"),
):
    cfg = _load_config(config)
    tools = _tools_from_config_and_flags(
        cfg, miranda_exe, rnahybrid_exe, pita_script, intarna_exe
    )
    if not tools:
        raise typer.BadParameter("Configure at least one tool (CLI flag or config file).")

    job = PredictionJob(
        mirna_fasta=mirna,
        target_fasta=targets,
        out_dir=out,
        tools=tools,
        workers=workers,
        chunk_size=chunk_size,
        mirna_chunk_size=mirna_chunk_size,
        resume=not no_resume,
        backend=backend,
    )

    if dry_run:
        _dry_run(job)
        return

    on_progress = None if quiet else _print_progress
    result = run_pipeline(job, on_progress=on_progress)
    typer.echo(f"Merged result written to: {result}")


@app.command("validate-tools")
def validate_tools(
    config: Path | None = typer.Option(None, exists=False, help="TOML tool config"),
    backend: BackendKind = typer.Option(BackendKind.LOCAL, help="Execution backend"),
    miranda_exe: Path | None = typer.Option(None),
    rnahybrid_exe: Path | None = typer.Option(None),
    pita_script: Path | None = typer.Option(None),
    intarna_exe: Path | None = typer.Option(None),
):
    """Probe each configured tool: dependency check + version string."""
    cfg = _load_config(config)
    tools = _tools_from_config_and_flags(
        cfg, miranda_exe, rnahybrid_exe, pita_script, intarna_exe
    )
    if not tools:
        raise typer.BadParameter("Configure at least one tool (CLI flag or config file).")

    backend_inst = build_backend(backend)
    typer.echo(f"backend: {backend_inst.name}")
    typer.echo(f"{'tool':<12}{'ready':<10}{'version'}")
    for tool in tools:
        runner = build_runner(tool)
        try:
            runner.check_ready()
            ready = "ok"
        except Exception as exc:
            ready = "fail"
            version = f"{type(exc).__name__}: {exc}"
            typer.echo(f"{tool.name:<12}{ready:<10}{version}")
            continue
        version = runner.probe_version(backend_inst)
        typer.echo(f"{tool.name:<12}{ready:<10}{version}")


@app.command()
def gui():
    """Open the desktop GUI (requires `pip install .[gui]`)."""
    from srna_win_target.gui import launch_gui

    raise typer.Exit(code=launch_gui())


@app.command()
def web(
    host: str = typer.Option("127.0.0.1", help="Bind address (default: loopback only)"),
    port: int = typer.Option(5173, help="Port (default 5173, same as Vite)"),
    no_browser: bool = typer.Option(False, help="Do not auto-open the browser"),
):
    """Start the local web UI (FastAPI + WebSocket). Requires `.[web]`."""
    from srna_win_target.web import launch_web

    launch_web(host=host, port=port, open_browser=not no_browser)


@app.command()
def selftest(
    keep: bool = typer.Option(False, help="Keep the temp working dir for inspection"),
):
    """Run the full pipeline against an internal fake tool. No real tools needed.

    Useful as a Windows sanity check: if this prints `selftest OK`, the
    install, scheduler, manifest, parser, and streaming writer are all working.
    """
    tmp = Path(tempfile.mkdtemp(prefix="srna-selftest-"))
    try:
        merged = run_selftest(tmp)
        with merged.open(encoding="utf-8") as handle:
            row_count = sum(1 for _ in csv.reader(handle)) - 1
        typer.echo(f"selftest OK: {row_count} hits at {merged}")
    finally:
        if not keep:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)
        else:
            typer.echo(f"(kept temp dir: {tmp})")


def _dry_run(job: PredictionJob) -> None:
    """Print the chunk_job × LogicalCommand matrix without executing."""
    work_dir = job.out_dir / "work"
    norm_dir = work_dir / "normalized"
    chunk_dir = work_dir / "chunks"

    typer.echo(f"# dry-run for {len(job.tools)} tool(s); backend={job.backend.value}")
    mirna_fasta = normalize_input_fasta(job.mirna_fasta, norm_dir / "mirna.fa", molecule="rna")
    target_fasta = normalize_input_fasta(job.target_fasta, norm_dir / "targets.fa", molecule="rna")
    chunks = split_fasta(target_fasta, chunk_dir, records_per_chunk=job.chunk_size)
    typer.echo(f"# {len(chunks)} chunk(s) from {target_fasta}")

    runners = {tool.name: build_runner(tool) for tool in job.tools}
    chunk_jobs = build_chunk_jobs(job, mirna_fasta, chunks)
    for cj in chunk_jobs:
        cmd = runners[cj.tool.name].build_logical_command(cj)
        typer.echo(f"  {cj.job_id}: {' '.join(cmd.argv)}")


def _print_progress(event: ProgressEvent) -> None:
    if event.status in (RunStatus.COMPLETED, RunStatus.SKIPPED, RunStatus.FAILED):
        prefix = {
            RunStatus.COMPLETED: "[done]",
            RunStatus.SKIPPED: "[skip]",
            RunStatus.FAILED: "[fail]",
        }[event.status]
        scope = (
            f" ({event.completed}/{event.total})"
            if event.total
            else ""
        )
        message = f" {event.message}" if event.message else ""
        typer.echo(f"{prefix} {event.tool} {event.chunk_id}{scope}{message}")
