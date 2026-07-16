from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.workers.mock import MockWorker


def _compiled_ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _update_patchlet(ctx, **updates) -> None:
    index = read_json(ctx.paths.patchlet_index)
    index["patchlets"][0].update(updates)
    write_json(ctx.paths.patchlet_index, index)


def _scenario(ctx, payload: dict) -> None:
    path = ctx.paths.workflow_dir / "mock" / "next_patchlet_result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _failure_records(ctx) -> list[Path]:
    return sorted(ctx.paths.failures_dir.glob("F*.json"))


class DebrisWorker:
    def __init__(self, paths: dict[str, str], *, symlinks: dict[str, Path | str] | None = None):
        self.paths = paths
        self.symlinks = symlinks or {}
        self.mock = MockWorker()

    def run_patchlet(self, ctx, patchlet, *, run_dir=None, run_ctx=None):
        result = self.mock.run_patchlet(ctx, patchlet, run_dir=run_dir, run_ctx=run_ctx)
        assert run_ctx is not None
        for relative, content in self.paths.items():
            path = run_ctx.execution_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        for relative, target in self.symlinks.items():
            path = run_ctx.execution_root / relative
            if path.exists() or path.is_symlink():
                path.unlink()
            path.symlink_to(target)
        return result


def _run_with_worker(ctx, monkeypatch: pytest.MonkeyPatch, worker: DebrisWorker):
    monkeypatch.setattr("codex_orchestrator.stages.run_patchlet.worker_for_mode", lambda _mode: worker)
    return run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)


def test_dot_codex_debris_does_not_create_failure(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _compiled_ctx(git_repo)
    result = _run_with_worker(ctx, monkeypatch, DebrisWorker({".codex/runtime/state.json": "{}\n"}))
    assert result.status in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}
    assert _failure_records(ctx) == []


def test_dot_agents_debris_does_not_create_failure(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _compiled_ctx(git_repo)
    result = _run_with_worker(ctx, monkeypatch, DebrisWorker({".agents/cache/trace.txt": "trace\n"}))
    assert result.status in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}
    assert _failure_records(ctx) == []


def test_arbitrary_peer_change_does_not_create_failure(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _compiled_ctx(git_repo)
    peer = ctx.root / "peer.py"
    peer.write_text("PEER = 'original'\n", encoding="utf-8")
    subprocess.run(["git", "add", "peer.py"], cwd=ctx.root, check=True)
    subprocess.run(["git", "commit", "-m", "add peer"], cwd=ctx.root, check=True, stdout=subprocess.PIPE)
    result = _run_with_worker(ctx, monkeypatch, DebrisWorker({"peer.py": "PEER = 'worker'\n"}))
    assert result.status in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}
    assert peer.read_text(encoding="utf-8") == "PEER = 'original'\n"
    assert _failure_records(ctx) == []


def test_debris_does_not_generate_repair_patchlet(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _compiled_ctx(git_repo)
    _run_with_worker(ctx, monkeypatch, DebrisWorker({"cache/nested/output.tmp": "temporary\n"}))
    patchlets = read_json(ctx.paths.patchlet_index)["patchlets"]
    assert [row["patchlet_id"] for row in patchlets] == ["P0001"]
    assert _failure_records(ctx) == []


def test_missing_required_allowed_change_generates_failure(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    _update_patchlet(ctx, required_allowed_product_change=True)
    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert result.status == "FAILED_WITH_EVIDENCE"
    assert _failure_records(ctx)


def test_invalid_allowed_path_generates_failure(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _compiled_ctx(git_repo)
    peer = ctx.root / "peer.py"
    peer.write_text("peer\n", encoding="utf-8")
    subprocess.run(["git", "add", "peer.py"], cwd=ctx.root, check=True)
    subprocess.run(["git", "commit", "-m", "add peer"], cwd=ctx.root, check=True, stdout=subprocess.PIPE)
    _update_patchlet(ctx, required_allowed_product_change=True)
    result = _run_with_worker(ctx, monkeypatch, DebrisWorker({}, symlinks={"app.py": "peer.py"}))
    assert result.status == "FAILED_WITH_EVIDENCE"
    assert _failure_records(ctx)


def test_allowed_slice_boundary_violation_generates_failure(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    _update_patchlet(
        ctx,
        slice_change_boundary={
            "allowed_changes": [{"key": "NEVER", "old_value": "old", "new_value": "new"}],
            "forbidden_changes": [],
        },
    )
    _scenario(ctx, {"change_allowed_product": True, "status": "COMPLETE"})
    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert result.status == "FAILED_WITH_EVIDENCE"
    assert _failure_records(ctx)


def test_clean_reconstruction_failure_generates_failure(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    import codex_orchestrator.patch_promotion as promotion

    ctx = _compiled_ctx(git_repo)
    original = promotion.reconstruct_clean_candidate

    def rejected_reconstruction(**kwargs):
        result, root = original(**kwargs)
        result["accepted"] = False
        result["proposal_reconstructed_equality"] = False
        result["errors"] = ["forced reconstruction mismatch"]
        return result, root

    monkeypatch.setattr(promotion, "reconstruct_clean_candidate", rejected_reconstruction)
    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert result.status == "FAILED_WITH_EVIDENCE"
    assert _failure_records(ctx)


def test_independent_proof_failure_generates_failure(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    import codex_orchestrator.stages.run_patchlet as stage

    ctx = _compiled_ctx(git_repo)
    original = stage.run_independent_probe_rerun_gate

    def rejected_probe(**kwargs):
        result = original(**kwargs)
        result.update(accepted=False, proven_obligation_ids=[], failed_obligation_ids=result.get("selected_obligation_ids", []))
        return result

    monkeypatch.setattr(stage, "run_independent_probe_rerun_gate", rejected_probe)
    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert result.status == "FAILED_WITH_EVIDENCE"
    assert _failure_records(ctx)


def test_coverage_failure_generates_failure(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    import codex_orchestrator.stages.run_patchlet as stage

    ctx = _compiled_ctx(git_repo)
    original = stage.evaluate_goal_coverage_gate

    def rejected_coverage(**kwargs):
        result = original(**kwargs)
        result.update(accepted=False, accepted_for_patchlet_progress=False, failed_obligation_ids=["PO001"])
        return result

    monkeypatch.setattr(stage, "evaluate_goal_coverage_gate", rejected_coverage)
    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert result.status == "FAILED_WITH_EVIDENCE"
    assert _failure_records(ctx)


def test_canonical_semantic_failure_generates_failure(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    import codex_orchestrator.stages.run_patchlet as stage

    ctx = _compiled_ctx(git_repo)
    original = stage.build_canonical_patchlet_semantic_result

    def rejected_semantic(**kwargs):
        result = original(**kwargs)
        result.update(accepted=False, errors=["forced canonical semantic failure"])
        return result

    monkeypatch.setattr(stage, "build_canonical_patchlet_semantic_result", rejected_semantic)
    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert result.status == "FAILED_WITH_EVIDENCE"
    assert _failure_records(ctx)


def test_containment_violation_generates_security_failure(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    ctx = _compiled_ctx(git_repo)
    result = _run_with_worker(ctx, monkeypatch, DebrisWorker({}, symlinks={"escape": ctx.root}))
    assert result.status == "FAILED_WITH_EVIDENCE"
    failure = read_json(_failure_records(ctx)[0])
    assert "CONTAINMENT" in failure["observed_failure"].upper()
