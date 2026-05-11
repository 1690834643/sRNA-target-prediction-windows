"""Tests for the FastAPI web UI."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from srna_win_target.cli._selftest import FakeBackend  # noqa: E402
from srna_win_target.web import server as server_mod  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    """Build a TestClient and force the pipeline to use the in-process FakeBackend
    so the web tests do not need real tools installed."""
    original = server_mod.run_pipeline

    def _patched(job, backend=None, on_progress=None):
        return original(job, backend=FakeBackend(hits_per_chunk=2), on_progress=on_progress)

    monkeypatch.setattr(server_mod, "run_pipeline", _patched)
    server_mod.JOBS.clear()
    with TestClient(server_mod.app) as c:
        yield c


def _make_inputs(tmp_path: Path) -> dict[str, str]:
    mirna = tmp_path / "m.fa"
    targets = tmp_path / "t.fa"
    out = tmp_path / "out"
    mirna.write_text(">m1\nACGUACGU\n", encoding="utf-8")
    targets.write_text(">t1\nACGUACGUACGU\n>t2\nACGUACGUACGU\n", encoding="utf-8")
    fake_exe = tmp_path / "miranda-fake"
    fake_exe.write_text("# placeholder", encoding="utf-8")
    return {"mirna": str(mirna), "targets": str(targets), "out": str(out), "exe": str(fake_exe)}


def test_index_serves_html(client) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "sRNA" in res.text
    assert "Target Predictor" in res.text


def test_healthz(client) -> None:
    res = client.get("/api/healthz")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_predict_rejects_missing_fields(client) -> None:
    res = client.post("/api/predict", json={})
    assert res.status_code == 400
    assert "missing field" in res.json()["detail"]


def test_predict_rejects_no_tools(client, tmp_path: Path) -> None:
    paths = _make_inputs(tmp_path)
    res = client.post(
        "/api/predict",
        json={"mirna": paths["mirna"], "targets": paths["targets"], "out": paths["out"]},
    )
    assert res.status_code == 400
    assert "at least one tool" in res.json()["detail"]


def test_predict_runs_job_and_websocket_streams_progress(client, monkeypatch, tmp_path: Path) -> None:
    paths = _make_inputs(tmp_path)
    # /api/predict now restricts caller-supplied tool paths to bundled_tools/.
    # The test would normally inject a fake exe at a tmp_path — register it via
    # the discovery layer instead so the request payload doesn't ship a path.
    import srna_win_target.web.server as srv
    from srna_win_target.web.discover import DiscoveredTool
    monkeypatch.setattr(
        srv, "discover_bundled_tools",
        lambda *a, **kw: {
            "miranda":   DiscoveredTool(name="miranda",   ready=True,  executable=Path(paths["exe"])),
            "rnahybrid": DiscoveredTool(name="rnahybrid", ready=False, reason="n/a"),
            "pita":      DiscoveredTool(name="pita",      ready=False, reason="n/a"),
        },
    )
    monkeypatch.setattr(srv, "_is_under_bundled_tools", lambda p: True)
    payload = {
        "mirna": paths["mirna"],
        "targets": paths["targets"],
        "out": paths["out"],
        "chunk_size": 1,
        "workers": 1,
        "tools": {"miranda": {"score_cutoff": 140}},
    }
    res = client.post("/api/predict", json=payload)
    assert res.status_code == 200
    job_id = res.json()["job_id"]
    assert job_id

    # Open WebSocket and collect events until done.
    events: list[dict] = []
    with client.websocket_connect(f"/api/jobs/{job_id}/events") as ws:
        for _ in range(50):
            try:
                msg = ws.receive_json(mode="text")
            except Exception:
                break
            events.append(msg)
            if msg.get("type") in ("done", "error"):
                break

    types = [e["type"] for e in events]
    assert "done" in types, f"no done event in stream: {types}"

    done = next(e for e in events if e["type"] == "done")
    merged = Path(done["merged_csv"])
    assert merged.exists()

    # Status endpoint reflects completion.
    status = client.get(f"/api/jobs/{job_id}").json()
    assert status["status"] == "completed"
    assert status["merged_csv"] == str(merged)

    # Download endpoint streams the CSV.
    dl = client.get(f"/api/jobs/{job_id}/download")
    assert dl.status_code == 200
    assert dl.text.startswith("tool,mirna_id,target_id")


def test_status_unknown_job_returns_404(client) -> None:
    res = client.get("/api/jobs/does-not-exist")
    assert res.status_code == 404


# ── Phase D: bundled-tools discovery + idiot-proof endpoints ──────────────


def test_discover_returns_full_summary(client) -> None:
    res = client.get("/api/discover")
    assert res.status_code == 200
    body = res.json()
    assert {"app_dir", "frozen", "platform", "tools", "ready_count",
            "total_count", "default_output_dir"} <= body.keys()
    assert set(body["tools"].keys()) == {"miranda", "rnahybrid", "pita"}
    assert body["total_count"] == 3
    for tool in body["tools"].values():
        assert "ready" in tool and "reason" in tool


def test_pick_file_rejects_invalid_mode(client) -> None:
    res = client.post("/api/pick-file", json={"mode": "bogus"})
    assert res.status_code == 400
    assert "invalid mode" in res.json()["detail"]


def test_predict_falls_back_to_bundled_miranda(client, monkeypatch, tmp_path):
    """Empty `exe` payload should resolve via discover_bundled_tools()."""
    paths = _make_inputs(tmp_path)

    from srna_win_target.web.discover import DiscoveredTool

    fake_bundled = {
        "miranda": DiscoveredTool(
            name="miranda", ready=True, executable=Path(paths["exe"])
        ),
        "rnahybrid": DiscoveredTool(name="rnahybrid", ready=False, reason="missing"),
        "pita": DiscoveredTool(name="pita", ready=False, reason="missing"),
    }
    monkeypatch.setattr(server_mod, "discover_bundled_tools", lambda *a, **k: fake_bundled)

    payload = {
        "mirna": paths["mirna"],
        "targets": paths["targets"],
        "out": paths["out"],
        "chunk_size": 1,
        "workers": 1,
        # exe omitted → server should fall back to fake_bundled["miranda"]
        "tools": {"miranda": {"score_cutoff": 140}},
    }
    res = client.post("/api/predict", json=payload)
    assert res.status_code == 200, res.text


def test_find_free_port_skips_taken_port():
    """The port walker should hop over a port held by another socket."""
    import socket as _s

    from srna_win_target.web import _find_free_port

    blocker = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    taken = blocker.getsockname()[1]
    try:
        result = _find_free_port("127.0.0.1", taken, taken + 5)
        assert result != taken, "must not return the taken port"
        assert taken < result <= taken + 5
    finally:
        blocker.close()


def test_predict_400_when_tool_missing_and_unbundled(client, monkeypatch, tmp_path):
    paths = _make_inputs(tmp_path)

    from srna_win_target.web.discover import DiscoveredTool

    fake_bundled = {
        "miranda":   DiscoveredTool(name="miranda",   ready=False, reason="not bundled"),
        "rnahybrid": DiscoveredTool(name="rnahybrid", ready=False, reason="not bundled"),
        "pita":      DiscoveredTool(name="pita",      ready=False, reason="not bundled"),
    }
    monkeypatch.setattr(server_mod, "discover_bundled_tools", lambda *a, **k: fake_bundled)

    res = client.post(
        "/api/predict",
        json={
            "mirna": paths["mirna"], "targets": paths["targets"], "out": paths["out"],
            "tools": {"miranda": {}},  # no exe, no bundled → 400
        },
    )
    assert res.status_code == 400
    assert "miranda" in res.json()["detail"].lower()
