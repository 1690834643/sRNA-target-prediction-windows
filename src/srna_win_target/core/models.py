from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal

ToolName = Literal["miranda", "rnahybrid", "pita", "intarna"]


class BackendKind(str, Enum):
    LOCAL = "local"
    WSL = "wsl"
    DOCKER = "docker"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ToolConfig:
    name: ToolName
    executable: Path | None = None
    parameters: dict[str, str | int | float | bool] = field(default_factory=dict)


@dataclass(frozen=True)
class PredictionJob:
    mirna_fasta: Path
    target_fasta: Path
    out_dir: Path
    tools: list[ToolConfig]
    workers: int = 4
    chunk_size: int = 500          # target records per chunk
    mirna_chunk_size: int = 0      # 0 = whole miRNA file shared across chunks
    resume: bool = True
    backend: BackendKind = BackendKind.LOCAL


@dataclass(frozen=True)
class ChunkJob:
    job_id: str
    tool: ToolConfig
    mirna_fasta: Path
    target_chunk: Path
    out_dir: Path


@dataclass(frozen=True)
class LogicalCommand:
    """A backend-agnostic description of a subprocess invocation.

    Adapters return one of these from build_logical_command(); a Backend
    translates it into the actual argv (Windows native, WSL, Docker, etc.)
    and runs it.
    """

    argv: list[str]
    cwd: Path
    expected_output_file: Path | None
    capture_stdout_to: Path | None = None
    env: dict[str, str] | None = None


@dataclass(frozen=True)
class PredictionHit:
    tool: str
    mirna_id: str
    target_id: str
    start: int | None = None
    end: int | None = None
    score: float | None = None
    energy: float | None = None
    pvalue: float | None = None
    raw_file: Path | None = None
    chunk_id: str | None = None


@dataclass(frozen=True)
class ProgressEvent:
    chunk_id: str
    tool: str
    status: RunStatus
    message: str = ""
    completed: int = 0
    total: int = 0
