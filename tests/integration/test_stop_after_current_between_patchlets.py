from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

import pytest

from conftest import read_json
from codex_orchestrator.apply_results import apply_results
from codex_orchestrator.control import request_stop
from codex_orchestrator.integration_state import ensure_integration_state, record_accepted_change
from codex_orchestrator.jsonio import write_json
from codex_orchestrator.stages import auto as auto_module
from codex_orchestrator.stages import run_patchlet as run_patchlet_module
from codex_orchestrator.stages.status import status as workflow_status
from codex_orchestrator.stages.run_patchlet import PatchletExecutionResult
from codex_orchestrator.state import load_state, new_state, transition
from codex_orchestrator.target_repo import TargetRepoContext, resolve_target_repo


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def _make_stop_repo(tmp_path: Path) -> TargetRepoContext:
    repo = tmp_path / "target"
    repo.mkdir()
    _run(["git", "init"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Test User"], repo)
    (repo / "gateway.routes").write_text("/ready -> legacy-ready\n/admin -> legacy-admin\n", encoding="utf-8")
    (repo / "policy.rules").write_text("default_action=allow\naudit=off\n", encoding="utf-8")
    (repo / "release.env").write_text("release_channel=blue\napproval_state=pending\n", encoding="utf-8")
    (repo / "master_prompt.md").write_text("Stop after accepted progress.\n", encoding="utf-8")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-m", "initial stop target"], repo)

    ctx = resolve_target_repo(repo=repo)
    ctx.paths.workflow_dir.mkdir(parents=True, exist_ok=True)
    ctx.paths.patchlets_dir.mkdir(parents=True, exist_ok=True)
    ctx.paths.runs_dir.mkdir(parents=True, exist_ok=True)
    ctx.paths.reports_dir.mkdir(parents=True, exist_ok=True)
    ctx.paths.master_prompt.write_text("Stop after accepted progress.\n", encoding="utf-8")
    write_json(ctx.paths.goal_spec, {"schema_version": "1.0", "kind": "goal_spec", "goal": "probe"})
    ctx.paths.census_dir.mkdir(parents=True, exist_ok=True)
    ctx.paths.census_repo_files.write_text("gateway.routes\npolicy.rules\nrelease.env\n", encoding="utf-8")
    ctx.paths.search_evidence_jsonl.write_text("", encoding="utf-8")
    write_json(ctx.paths.inventory_graph, {"schema_version": "1.0", "kind": "inventory_graph", "nodes": []})
    write_json(ctx.paths.invariants, {"schema_version": "1.0", "kind": "invariants", "invariants": []})
    state = new_state(ctx, stage="PATCHLETS_READY", mode="auto", until="DONE")
    state.pending_patchlets = ["P0002", "P0003", "P0004"]
    write_json(ctx.paths.state, state.to_json())
    write_json(
        ctx.paths.patchlet_index,
        {
            "schema_version": "1.0",
            "kind": "patchlet_index",
            "patchlets": [
                {
                    "patchlet_id": "P0002",
                    "status": "PENDING",
                    "allowed_product_runtime_file": "gateway.routes",
                    "allowed_product_runtime_files": ["gateway.routes"],
                    "dependency_patchlet_ids": [],
                },
                {
                    "patchlet_id": "P0003",
                    "status": "PENDING",
                    "allowed_product_runtime_file": "policy.rules",
                    "allowed_product_runtime_files": ["policy.rules"],
                    "dependency_patchlet_ids": ["P0002"],
                },
                {
                    "patchlet_id": "P0004",
                    "status": "PENDING",
                    "allowed_product_runtime_file": "release.env",
                    "allowed_product_runtime_files": ["release.env"],
                    "dependency_patchlet_ids": ["P0003"],
                },
            ],
        },
    )
    ensure_integration_state(ctx)
    return ctx


def _started_attempts(ctx: TargetRepoContext) -> list[str]:
    return sorted(path.name for path in ctx.paths.runs_dir.iterdir() if path.is_dir() and "attempt" in path.name)


def _accepted_patchlets(ctx: TargetRepoContext) -> list[str]:
    return read_json(ctx.paths.integration_state).get("accepted_patchlets", [])


def _fake_runner(
    ctx: TargetRepoContext,
    *,
    stop_during_patchlet: str | None,
) -> Callable[..., PatchletExecutionResult]:
    def fake_run_next_patchlet(_ctx: TargetRepoContext, *, worker_mode: str = "mock", use_worktree: bool = False) -> PatchletExecutionResult:
        index = read_json(ctx.paths.patchlet_index)
        completed = {patchlet["patchlet_id"] for patchlet in index["patchlets"] if patchlet.get("status") == "COMPLETE"}
        patchlet = next(
            (
                candidate
                for candidate in index["patchlets"]
                if candidate.get("status") == "PENDING"
                and all(dep in completed for dep in candidate.get("dependency_patchlet_ids", []))
            ),
            None,
        )
        if patchlet is None:
            return PatchletExecutionResult("", "NO_PENDING_PATCHLETS", [], True, "no pending patchlets")

        pid = patchlet["patchlet_id"]
        state = load_state(ctx)
        state.current_patchlet_id = pid
        state.attempts[pid] = state.attempts.get(pid, 0) + 1
        transition(ctx, state, "PATCHLET_EXECUTION_IN_PROGRESS", reason=f"running {pid}")
        attempt_id = f"{pid}_attempt{state.attempts[pid]}"
        run_dir = ctx.paths.runs_dir / attempt_id
        gates_dir = run_dir / "gates"
        gates_dir.mkdir(parents=True, exist_ok=True)

        if pid == stop_during_patchlet:
            request_stop(ctx, mode="after_current_attempt")

        diff_path = run_dir / "diff.patch"
        diff_path.write_text("", encoding="utf-8")
        wrapper_gate_path = gates_dir / "wrapper_gate_result.json"
        write_json(
            wrapper_gate_path,
            {
                "schema_version": "1.0",
                "kind": "wrapper_gate_result",
                "patchlet_id": pid,
                "attempt_id": attempt_id,
                "accepted": True,
                "report_gate": "pass",
                "probe_gate": "pass",
                "diff_gate": "pass",
            },
        )
        report_path = ctx.paths.reports_dir / f"{pid}.json"
        write_json(report_path, {"schema_version": "1.0", "kind": "probe_report", "patchlet_id": pid, "status": "COMPLETE"})
        probe_root = ctx.paths.probe_dir / pid
        probe_root.mkdir(parents=True, exist_ok=True)
        record_accepted_change(
            ctx,
            patchlet=patchlet,
            attempt_id=attempt_id,
            changed_product_runtime_files=[patchlet["allowed_product_runtime_file"]],
            diff_path=diff_path,
            report_path=report_path,
            probe_root=probe_root,
            wrapper_gate_result=wrapper_gate_path.relative_to(ctx.root).as_posix(),
        )

        patchlet["status"] = "COMPLETE"
        write_json(ctx.paths.patchlet_index, index)
        state = load_state(ctx)
        if pid in state.pending_patchlets:
            state.pending_patchlets.remove(pid)
        if pid not in state.completed_patchlets:
            state.completed_patchlets.append(pid)
        transition(ctx, state, "PATCHLET_EXECUTION_COMPLETE", reason=f"{pid} accepted")
        return PatchletExecutionResult(pid, "COMPLETE", [], True, "accepted")

    return fake_run_next_patchlet


def _run_all_with_fake(monkeypatch: pytest.MonkeyPatch, ctx: TargetRepoContext, *, stop_during_patchlet: str | None) -> list[PatchletExecutionResult]:
    monkeypatch.setattr(run_patchlet_module, "run_next_patchlet", _fake_runner(ctx, stop_during_patchlet=stop_during_patchlet))
    return run_patchlet_module.run_all_patchlets(ctx, worker_mode="mock", use_worktree=True)


def test_stop_after_current_requested_during_p0002_stops_before_p0003(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _make_stop_repo(tmp_path)
    _run_all_with_fake(monkeypatch, ctx, stop_during_patchlet="P0002")
    assert _started_attempts(ctx) == ["P0002_attempt1"]


def test_stop_after_current_writes_stop_result_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _make_stop_repo(tmp_path)
    _run_all_with_fake(monkeypatch, ctx, stop_during_patchlet="P0002")
    assert (ctx.paths.workflow_dir / "control" / "stop_result.json").exists()


def test_stop_after_current_records_latest_accepted_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _make_stop_repo(tmp_path)
    _run_all_with_fake(monkeypatch, ctx, stop_during_patchlet="P0002")
    stop_result = read_json(ctx.paths.workflow_dir / "control" / "stop_result.json")
    assert stop_result["latest_accepted_checkpoint"].endswith("P0002.json")


def test_stop_after_current_records_applyable_progress_true_when_checkpoint_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _make_stop_repo(tmp_path)
    _run_all_with_fake(monkeypatch, ctx, stop_during_patchlet="P0002")
    assert read_json(ctx.paths.workflow_dir / "control" / "stop_result.json")["applyable_progress"] is True


def test_stop_after_current_status_reports_applyable_progress_from_stop_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _make_stop_repo(tmp_path)
    _run_all_with_fake(monkeypatch, ctx, stop_during_patchlet="P0002")
    applyable = workflow_status(ctx)["applyable_progress"]
    assert applyable["available"] is True
    assert applyable["latest_accepted_checkpoint"].endswith("P0002.json")


def test_stop_after_current_does_not_start_downstream_patchlet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _make_stop_repo(tmp_path)
    _run_all_with_fake(monkeypatch, ctx, stop_during_patchlet="P0002")
    assert "P0003_attempt1" not in _started_attempts(ctx)


def test_stop_after_current_does_not_start_repair_patchlet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _make_stop_repo(tmp_path)
    index = read_json(ctx.paths.patchlet_index)
    index["patchlets"].append(
        {
            "patchlet_id": "P0006",
            "status": "PENDING",
            "allowed_product_runtime_file": "gateway.routes",
            "allowed_product_runtime_files": ["gateway.routes"],
            "dependency_patchlet_ids": [],
            "repair_plan_id": "RP001",
        }
    )
    write_json(ctx.paths.patchlet_index, index)
    load_state(ctx).pending_patchlets.append("P0006")
    _run_all_with_fake(monkeypatch, ctx, stop_during_patchlet="P0002")
    assert "P0006_attempt1" not in _started_attempts(ctx)


def test_stop_after_current_state_not_execution_in_progress(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _make_stop_repo(tmp_path)
    _run_all_with_fake(monkeypatch, ctx, stop_during_patchlet="P0002")
    assert load_state(ctx).stage == "STOPPED"


def test_stop_after_current_goal_progress_remains_partial_not_done(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _make_stop_repo(tmp_path)
    _run_all_with_fake(monkeypatch, ctx, stop_during_patchlet="P0002")
    assert load_state(ctx).stage == "STOPPED"
    assert not (ctx.paths.workflow_dir / "global_verification" / "master_prompt_satisfaction_result.json").exists()


def test_stop_after_current_partial_apply_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _make_stop_repo(tmp_path)
    _run_all_with_fake(monkeypatch, ctx, stop_during_patchlet="P0002")
    result = apply_results(ctx, mode="patch", scope="accepted", allow_partial=True)
    assert result["scope"] == "accepted"


def test_stop_after_current_partial_apply_applies_accepted_checkpoint_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _make_stop_repo(tmp_path)
    _run_all_with_fake(monkeypatch, ctx, stop_during_patchlet="P0002")
    apply_results(ctx, mode="patch", scope="accepted", allow_partial=True)
    assert _accepted_patchlets(ctx) == ["P0002"]
    assert "P0003_attempt1" not in _started_attempts(ctx)


def test_stop_after_current_before_any_checkpoint_records_no_applyable_progress(tmp_path: Path):
    ctx = _make_stop_repo(tmp_path)
    request_stop(ctx, mode="after_current_attempt")
    from codex_orchestrator.control import honor_stop_if_requested

    honor_stop_if_requested(ctx, stop_stage=load_state(ctx).stage)
    stop_result = read_json(ctx.paths.workflow_dir / "control" / "stop_result.json")
    assert stop_result["applyable_progress"] is False
    assert stop_result["latest_accepted_checkpoint"] is None


def test_no_stop_request_runs_all_ready_patchlets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _make_stop_repo(tmp_path)
    _run_all_with_fake(monkeypatch, ctx, stop_during_patchlet=None)
    assert _started_attempts(ctx) == ["P0002_attempt1", "P0003_attempt1", "P0004_attempt1"]


def test_stop_request_file_is_cleared_or_marked_consumed_after_stop_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _make_stop_repo(tmp_path)
    _run_all_with_fake(monkeypatch, ctx, stop_during_patchlet="P0002")
    stop_result = read_json(ctx.paths.workflow_dir / "control" / "stop_result.json")
    assert stop_result.get("honored") is True
    assert stop_result.get("honored_at_safe_point") is True


def test_auto_honors_stop_between_accepted_patchlets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _make_stop_repo(tmp_path)
    monkeypatch.setattr(run_patchlet_module, "run_next_patchlet", _fake_runner(ctx, stop_during_patchlet="P0002"))
    monkeypatch.setattr(auto_module, "run_all_patchlets", run_patchlet_module.run_all_patchlets)
    state = auto_module.run_auto(ctx, resume=True, until="STOPPED", worker_mode="mock", use_worktree=True, max_iterations=5)
    assert state.stage == "STOPPED"
    assert _started_attempts(ctx) == ["P0002_attempt1"]
