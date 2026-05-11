# Architecture

## Overview

The pipeline has six layers:

1. Input normalization
2. Target chunking
3. Tool adapter (logical command construction + parser)
4. Backend (translates logical command into a real subprocess call)
5. Parallel scheduler with manifest-based resume
6. Streaming result writer + reporting

```text
miRNA FASTA            target FASTA / 3UTR FASTA
     |                          |
     +-------- normalize -------+
                  |
            split targets
                  |
        tool x chunk job matrix
                  |
       adapter -> LogicalCommand
                  |
       backend -> argv (local | wsl | docker)
                  |
       ThreadPoolExecutor (I/O bound)
                  |
        raw outputs + per-chunk logs
                  |
        adapter.parse_output()
                  |
        StreamingHitWriter -> merged_predictions.csv
                  |
   intersections / Venn / UpSet / HTML
```

## Package Boundaries

| Package | Responsibility |
|---|---|
| `core` | Shared dataclasses (`PredictionJob`, `ChunkJob`, `LogicalCommand`, `PredictionHit`, `ProgressEvent`) and pipeline orchestration |
| `data` | FASTA/FASTQ format detection, normalization, chunking |
| `tools` | Adapters that produce LogicalCommands and parse raw outputs |
| `backends` | `Backend` ABC plus `LocalBackend`, `WSLBackend`, (later) `DockerBackend` |
| `parallel` | `ThreadPoolExecutor` scheduler, `RunManifest` resume, cache helpers |
| `results` | `StreamingHitWriter`, intersection/merge logic, Venn/UpSet rendering |
| `cli` | Typer command, TOML config loading, progress printing |
| `gui` | PySide6 main window (planned) |

## Adapter / Backend Contract

Adapters do not run subprocesses themselves. Each adapter exposes:

- `check_ready()` — error early if executable/script/Perl is missing
- `build_logical_command(chunk_job) -> LogicalCommand`
- `expected_output_file(chunk_job)` — where the parser should later read from
- `parse_output(raw_output) -> list[PredictionHit]`

The `Backend` class owns subprocess execution:

- `run(LogicalCommand, log_file)` — launches the process, captures stdout/stderr
  to a per-chunk log, optionally redirects stdout to the expected output file
  (RNAhybrid stdout-only mode), and returns a `BackendResult`.
- `translate_path(Path)` — `LocalBackend` is identity; `WSLBackend` rewrites
  `C:\foo\bar` to `/mnt/c/foo/bar` and prepends `wsl --cd ... --`.

This isolation lets a single adapter run under native Windows builds, WSL2,
or a Docker image without code changes.

## Parallel Strategy

- `ThreadPoolExecutor` rather than `ProcessPoolExecutor`. Subprocess
  orchestration is I/O bound; the spawn + pickle cost of process pools (which
  on Windows is the only available start method) buys us nothing here.
- Tool × target-chunk is the unit of work, so independent invocations can
  saturate cores naturally without us touching the underlying algorithms.
- Per-chunk failures are captured into the manifest and a per-chunk log file;
  sibling chunks keep running.

## Resumability

`work/manifest.json` is a JSON-backed table of cache_key -> entry. The cache
key is `sha256({mirna_hash, target_hash, tool, tool_version, params})`. On
re-run, completed chunks whose key matches and whose output file still exists
are skipped, and their cached parser hits are appended to the new merged CSV.

## Streaming Result Output

`StreamingHitWriter` opens `results/merged_predictions.csv` once, writes the
header up front, and accepts hits incrementally from worker threads (guarded
by a lock). This keeps memory usage flat regardless of total hit count.

## Progress Events

The scheduler emits `ProgressEvent(chunk_id, tool, status, completed, total,
message)` after every chunk transition. CLI consumes them with simple text
output; the GUI worker will translate them into Qt signals.

## Windows Execution Model

| Backend | Use case |
|---|---|
| `LocalBackend` | Native Windows binaries dropped into `bundled_tools/` |
| `WSLBackend` | Linux miRanda/RNAhybrid/PITA reused without rebuilding for Windows |
| `DockerBackend` (later) | Reproducible distribution if WSL is not available |

## Rust Decision Point

Rust remains a reasonable later option for a single-exe launcher or a
high-throughput parser engine. The adapter / backend separation is the part
that makes a Rust port tractable: only the small subprocess wrapper layer
needs to change, not the biology.
