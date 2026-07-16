from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.state import load_state, save_state
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


class CodexRuntimeDebrisWorker:
    def __init__(self):
        self.mock = MockWorker()

    def run_patchlet(self, ctx, patchlet, *, run_dir=None, run_ctx=None):
        result = self.mock.run_patchlet(ctx, patchlet, run_dir=run_dir, run_ctx=run_ctx)
        assert run_ctx is not None
        outputs = {
            ".codex/runtime/session/state.json": "{}\n",
            ".agents/cache/nested/trace.txt": "trace\n",
            ".worker-hidden": "temporary\n",
            "cache/deep/runtime.bin": "cache\n",
            "temporary-output.tmp": "temporary\n",
        }
        for relative, content in outputs.items():
            path = run_ctx.execution_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return result


def _run_regression(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    limits = git_repo / "limits.mjs"
    limits.write_text("export const limit = 1;\n", encoding="utf-8")
    subprocess.run(["git", "add", "limits.mjs"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "add limits target"], cwd=git_repo, check=True, stdout=subprocess.PIPE)
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)

    index = read_json(ctx.paths.patchlet_index)
    patchlet = index["patchlets"][0]
    patchlet.update(
        patchlet_id="P0002",
        allowed_product_runtime_file="limits.mjs",
        allowed_product_runtime_files=["limits.mjs"],
        required_allowed_product_change=True,
        expected_behavior=None,
    )
    write_json(ctx.paths.patchlet_index, index)
    state = load_state(ctx)
    state.pending_patchlets = ["P0002"]
    state.current_patchlet_id = None
    save_state(ctx, state)
    scenario = ctx.paths.workflow_dir / "mock" / "next_patchlet_result.json"
    scenario.parent.mkdir(parents=True, exist_ok=True)
    scenario.write_text(json.dumps({"change_allowed_product": True, "status": "COMPLETE"}), encoding="utf-8")
    monkeypatch.setattr(
        "codex_orchestrator.stages.run_patchlet.worker_for_mode",
        lambda _mode: CodexRuntimeDebrisWorker(),
    )

    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=False)
    run_dir = ctx.paths.runs_dir / "P0002_attempt1"
    return ctx, result, run_dir


def _debris_paths(hygiene: dict) -> set[str]:
    return {
        row["path"]
        for row in hygiene["change_classification_ledger"]
        if row["classification"] == "SANDBOX_DEBRIS"
    }


def test_p0002_dot_codex_runtime_debris_reaches_proof_and_promotion(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _ctx, result, run_dir = _run_regression(git_repo, monkeypatch)
    assert result.status == "COMPLETE"
    assert read_json(run_dir / "gates" / "independent_probe_rerun_result.json")["accepted"] is True
    assert read_json(run_dir / "gates" / "goal_coverage_gate_result.json")["accepted"] is True
    assert read_json(run_dir / "gates" / "canonical_patchlet_semantic_result.json")["accepted"] is True
    assert read_json(run_dir / "patch_promotion" / "clean_candidate_promotion_result.json")["promotion_accepted"] is True


def test_p0002_dot_codex_runtime_debris_is_inventoried(git_repo: Path, monkeypatch: pytest.MonkeyPatch):
    _ctx, _result, run_dir = _run_regression(git_repo, monkeypatch)
    hygiene = read_json(run_dir / "gates" / "worker_sandbox_hygiene_result.json")
    debris = _debris_paths(hygiene)
    assert ".codex/runtime/session/state.json" in debris
    assert ".agents/cache/nested/trace.txt" in debris
    assert ".worker-hidden" in debris
    assert hygiene["promotion_blocked"] is False


def test_p0002_dot_codex_runtime_debris_is_not_in_canonical_patch(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _ctx, _result, run_dir = _run_regression(git_repo, monkeypatch)
    manifest = read_json(run_dir / "patch_promotion" / "patch_proposal_manifest.json")
    patch = (run_dir / "patch_promotion" / "patch_proposal.patch").read_text(encoding="utf-8")
    assert [row["path"] for row in manifest["changed_paths"]] == ["limits.mjs"]
    assert ".codex" not in patch
    assert ".agents" not in patch


def test_p0002_dot_codex_runtime_debris_is_not_in_clean_reconstruction(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _ctx, _result, run_dir = _run_regression(git_repo, monkeypatch)
    reconstruction = read_json(run_dir / "patch_promotion" / "patch_reconstruction_result.json")
    manifest = read_json(run_dir / "patch_promotion" / "patch_proposal_manifest.json")
    assert reconstruction["accepted"] is True
    assert reconstruction["proposal_reconstructed_equality"] is True
    assert [row["path"] for row in manifest["changed_paths"]] == ["limits.mjs"]


def test_p0002_dot_codex_runtime_debris_does_not_generate_p0006(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    ctx, _result, _run_dir = _run_regression(git_repo, monkeypatch)
    assert not (ctx.paths.reports_dir / "P0006.json").exists()
    assert not list(ctx.paths.failures_dir.glob("F*.json"))
    assert [row["patchlet_id"] for row in read_json(ctx.paths.patchlet_index)["patchlets"]] == ["P0002"]
