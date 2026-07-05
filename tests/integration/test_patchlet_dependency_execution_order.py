from __future__ import annotations

from pathlib import Path

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.stages.run_patchlet import _next_pending_patchlet, _refresh_dependency_states
from codex_orchestrator.target_repo import resolve_target_repo


def _ctx(repo: Path):
    ctx = resolve_target_repo(repo, allow_self_target=True)
    ctx.paths.workflow_dir.mkdir(parents=True, exist_ok=True)
    ctx.paths.patchlets_dir.mkdir(parents=True, exist_ok=True)
    ctx.paths.runs_dir.mkdir(parents=True, exist_ok=True)
    return ctx


def _index():
    return {
        "schema_version": "1.0",
        "kind": "patchlet_index",
        "patchlets": [
            {"patchlet_id": "P0001", "status": "FAILED_WITH_EVIDENCE", "dependency_patchlet_ids": []},
            {"patchlet_id": "P0002", "status": "PENDING", "dependency_patchlet_ids": []},
            {"patchlet_id": "P0003", "status": "PENDING", "dependency_patchlet_ids": ["P0002"]},
        ],
    }


def test_failed_dependency_blocks_downstream_patchlet(git_repo: Path):
    ctx = _ctx(git_repo)
    index = _index()
    write_json(ctx.paths.patchlet_index, index)
    _refresh_dependency_states(ctx, index)
    p2 = index["patchlets"][1]
    assert p2["status"] == "BLOCKED_BY_FAILED_DEPENDENCY"
    assert p2["blocked_dependency_patchlet_ids"] == ["P0001"]


def test_failed_p0001_does_not_start_p0002(git_repo: Path):
    ctx = _ctx(git_repo)
    index = _index()
    write_json(ctx.paths.patchlet_index, index)
    _refresh_dependency_states(ctx, index)
    assert _next_pending_patchlet(index) is None


def test_downstream_patchlet_records_blocked_by_failed_dependency(git_repo: Path):
    ctx = _ctx(git_repo)
    index = _index()
    write_json(ctx.paths.patchlet_index, index)
    _refresh_dependency_states(ctx, index)
    artifact = ctx.paths.runs_dir / "P0002_blocked_by_failed_dependency" / "gates" / "dependency_block_result.json"
    assert artifact.exists()
    data = read_json(artifact)
    assert data["kind"] == "dependency_block_result"
    assert data["patchlet_id"] == "P0002"
    assert data["blocked_dependency_patchlet_ids"] == ["P0001"]


def test_auto_loop_stops_or_classifies_after_dependency_failure(git_repo: Path):
    ctx = _ctx(git_repo)
    index = _index()
    write_json(ctx.paths.patchlet_index, index)
    _refresh_dependency_states(ctx, index)
    persisted = read_json(ctx.paths.patchlet_index)
    pending = [row["patchlet_id"] for row in persisted["patchlets"] if row.get("status") == "PENDING"]
    assert "P0002" not in pending


def test_dependency_scheduler_uses_accepted_status_not_attempt_existence(git_repo: Path):
    ctx = _ctx(git_repo)
    run_dir = ctx.paths.runs_dir / "P0001_attempt1"
    run_dir.mkdir(parents=True)
    index = _index()
    write_json(ctx.paths.patchlet_index, index)
    _refresh_dependency_states(ctx, index)
    assert index["patchlets"][1]["status"] == "BLOCKED_BY_FAILED_DEPENDENCY"
    assert _next_pending_patchlet(index) is None
