from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from srna_win_target.core.models import ChunkJob, RunStatus
from srna_win_target.parallel.cache import cache_key, file_sha256


@dataclass
class ManifestEntry:
    cache_key: str
    chunk_id: str
    tool: str
    status: str
    output_file: str | None
    log_file: str | None
    started_at: str | None
    finished_at: str | None
    error: str | None = None


class RunManifest:
    """JSON-backed record of which (input, tool, params) chunks have been run.

    Lets a re-run skip work that already completed successfully. Thread-safe
    for concurrent updates from a ThreadPoolExecutor.
    """

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._entries: dict[str, ManifestEntry] = {}
        self._input_hashes: dict[str, str] = {}
        if path.exists():
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for raw in data.get("entries", []):
            entry = ManifestEntry(**raw)
            self._entries[entry.cache_key] = entry

    def _save_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "entries": [asdict(e) for e in self._entries.values()],
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def cache_key_for(
        self,
        chunk_job: ChunkJob,
        tool_version: str,
    ) -> str:
        mirna_hash = self._cached_input_hash(chunk_job.mirna_fasta)
        target_hash = self._cached_input_hash(chunk_job.target_chunk)
        return cache_key(
            {
                "mirna": mirna_hash,
                "target": target_hash,
                "tool": chunk_job.tool.name,
                "tool_version": tool_version,
                "params": dict(chunk_job.tool.parameters),
            }
        )

    def _cached_input_hash(self, path: Path) -> str:
        key = str(path)
        cached = self._input_hashes.get(key)
        if cached is not None:
            return cached
        digest = file_sha256(path)
        self._input_hashes[key] = digest
        return digest

    def get(self, key: str) -> ManifestEntry | None:
        return self._entries.get(key)

    def is_completed(self, key: str) -> bool:
        entry = self._entries.get(key)
        if entry is None or entry.status != RunStatus.COMPLETED.value:
            return False
        if entry.output_file:
            output_path = Path(entry.output_file)
            if not output_path.exists():
                return False
        return True

    def mark_running(self, key: str, chunk_job: ChunkJob) -> None:
        with self._lock:
            self._entries[key] = ManifestEntry(
                cache_key=key,
                chunk_id=chunk_job.job_id,
                tool=chunk_job.tool.name,
                status=RunStatus.RUNNING.value,
                output_file=None,
                log_file=None,
                started_at=_now(),
                finished_at=None,
            )
            self._save_locked()

    def mark_completed(
        self,
        key: str,
        chunk_job: ChunkJob,
        output_file: Path | None,
        log_file: Path | None,
    ) -> None:
        with self._lock:
            entry = self._entries.get(key)
            started_at = entry.started_at if entry else _now()
            self._entries[key] = ManifestEntry(
                cache_key=key,
                chunk_id=chunk_job.job_id,
                tool=chunk_job.tool.name,
                status=RunStatus.COMPLETED.value,
                output_file=str(output_file) if output_file else None,
                log_file=str(log_file) if log_file else None,
                started_at=started_at,
                finished_at=_now(),
            )
            self._save_locked()

    def mark_failed(
        self,
        key: str,
        chunk_job: ChunkJob,
        error: str,
        log_file: Path | None,
    ) -> None:
        with self._lock:
            entry = self._entries.get(key)
            started_at = entry.started_at if entry else _now()
            self._entries[key] = ManifestEntry(
                cache_key=key,
                chunk_id=chunk_job.job_id,
                tool=chunk_job.tool.name,
                status=RunStatus.FAILED.value,
                output_file=None,
                log_file=str(log_file) if log_file else None,
                started_at=started_at,
                finished_at=_now(),
                error=error[:2000],
            )
            self._save_locked()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
