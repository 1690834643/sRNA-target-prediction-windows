from __future__ import annotations

import json
from pathlib import Path

from srna_win_target.core.models import ChunkJob, ToolConfig
from srna_win_target.parallel.manifest import RunManifest


def _make_chunk_job(tmp_path: Path, tool_name: str = "miranda") -> ChunkJob:
    mirna = tmp_path / "mirna.fa"
    target = tmp_path / "target.fa"
    mirna.write_text(">m1\nACGU\n", encoding="utf-8")
    target.write_text(">t1\nACGUACGU\n", encoding="utf-8")
    return ChunkJob(
        job_id=f"{tool_name}_chunk_00000",
        tool=ToolConfig(name=tool_name, parameters={"score_cutoff": 140}),
        mirna_fasta=mirna,
        target_chunk=target,
        out_dir=tmp_path / "out",
    )


def test_manifest_round_trip(tmp_path: Path) -> None:
    cj = _make_chunk_job(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = RunManifest(manifest_path)

    key = manifest.cache_key_for(cj, tool_version="3.3a")
    assert manifest.get(key) is None
    assert manifest.is_completed(key) is False

    manifest.mark_running(key, cj)
    assert manifest.get(key).status == "running"

    output_file = tmp_path / "out" / "result.txt"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text("ok", encoding="utf-8")
    log_file = tmp_path / "log.txt"
    log_file.write_text("done", encoding="utf-8")
    manifest.mark_completed(key, cj, output_file, log_file)

    assert manifest.is_completed(key) is True

    # Reload from disk.
    reloaded = RunManifest(manifest_path)
    assert reloaded.is_completed(key) is True
    entry = reloaded.get(key)
    assert entry.tool == "miranda"
    assert entry.output_file == str(output_file)


def test_manifest_is_completed_false_if_output_missing(tmp_path: Path) -> None:
    cj = _make_chunk_job(tmp_path)
    manifest = RunManifest(tmp_path / "manifest.json")
    key = manifest.cache_key_for(cj, tool_version="3.3a")
    output = tmp_path / "missing.txt"
    manifest.mark_completed(key, cj, output, None)
    assert manifest.is_completed(key) is False  # output_file does not exist


def test_manifest_cache_key_changes_with_params(tmp_path: Path) -> None:
    cj1 = _make_chunk_job(tmp_path)
    cj2 = ChunkJob(
        job_id=cj1.job_id,
        tool=ToolConfig(name="miranda", parameters={"score_cutoff": 160}),
        mirna_fasta=cj1.mirna_fasta,
        target_chunk=cj1.target_chunk,
        out_dir=cj1.out_dir,
    )
    manifest = RunManifest(tmp_path / "m.json")
    assert manifest.cache_key_for(cj1, "v1") != manifest.cache_key_for(cj2, "v1")


def test_manifest_failed_records_error(tmp_path: Path) -> None:
    cj = _make_chunk_job(tmp_path)
    manifest = RunManifest(tmp_path / "m.json")
    key = manifest.cache_key_for(cj, "v1")
    manifest.mark_failed(key, cj, "boom!", None)
    data = json.loads((tmp_path / "m.json").read_text(encoding="utf-8"))
    assert data["entries"][0]["status"] == "failed"
    assert "boom" in data["entries"][0]["error"]
