from __future__ import annotations

import json
import os
from pathlib import Path

from codex_orchestrator.patchlet_run_context import build_patchlet_run_context
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.worker_capsule import (
    build_worker_capsule,
    ensure_worker_capsule,
    ensure_worker_memory,
)
from codex_orchestrator.workers.codex_exec import CodexExecWorker


def _setup(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    patchlet = json.loads(ctx.paths.patchlet_index.read_text(encoding="utf-8"))["patchlets"][0]
    run_ctx = build_patchlet_run_context(
        ctx,
        patchlet=patchlet,
        run_id="P0001_attempt1",
        execution_root=ctx.root,
        artifact_root=ctx.root,
        is_worktree=False,
        worktree_path=None,
    )
    capsule = build_worker_capsule(run_ctx, patchlet)
    ensure_worker_capsule(ctx, capsule)
    ensure_worker_memory(ctx, capsule, run_ctx, patchlet, worker_mode="real_codex")
    return ctx, patchlet, run_ctx, capsule


def test_task_contract_mentions_patchlet_timeout_seconds(git_repo: Path):
    _, _, _, capsule = _setup(git_repo)

    text = (capsule.worker_memory_dir / "TASK_CONTRACT.md").read_text(encoding="utf-8")

    assert "hard timeout of 600 seconds" in text


def test_task_contract_mentions_soft_deadline_seconds(git_repo: Path):
    _, _, _, capsule = _setup(git_repo)

    text = (capsule.worker_memory_dir / "TASK_CONTRACT.md").read_text(encoding="utf-8")

    assert "Aim to finish by 540 seconds" in text


def test_write_these_files_tells_codex_to_stop_before_timeout(git_repo: Path):
    _, _, _, capsule = _setup(git_repo)

    text = (capsule.worker_memory_dir / "WRITE_THESE_FILES.md").read_text(encoding="utf-8")

    assert "stop before the hard timeout" in text
    assert "CXOR_FINAL_REPORT_PATH" in text
    assert "BLOCKED or FAILED" in text


def test_write_these_files_uses_cxor_worker_stage_dir_for_stage_paths(git_repo: Path):
    _, _, _, capsule = _setup(git_repo)

    text = (capsule.worker_memory_dir / "WRITE_THESE_FILES.md").read_text(encoding="utf-8")

    assert "$CXOR_WORKER_STAGE_DIR/00_preflight.md" in text
    assert "$CXOR_WORKER_STAGE_DIR/05_final_report.md" in text


def test_write_these_files_contains_absolute_worker_stage_paths(git_repo: Path):
    _, _, _, capsule = _setup(git_repo)

    text = (capsule.worker_memory_dir / "WRITE_THESE_FILES.md").read_text(encoding="utf-8")

    assert str(capsule.worker_stage_dir / "00_preflight.md") in text
    assert str(capsule.worker_stage_dir / "05_final_report.md") in text


def test_write_these_files_forbids_target_root_worker_stage(git_repo: Path):
    ctx, _, _, capsule = _setup(git_repo)

    text = (capsule.worker_memory_dir / "WRITE_THESE_FILES.md").read_text(encoding="utf-8")

    assert f"{ctx.root}/worker_stage/" in text
    assert "Do not create target-root worker_stage/" in text


def test_task_contract_uses_absolute_capsule_stage_paths(git_repo: Path):
    _, _, _, capsule = _setup(git_repo)

    text = (capsule.worker_memory_dir / "TASK_CONTRACT.md").read_text(encoding="utf-8")

    assert str(capsule.worker_stage_dir / "00_preflight.md") in text
    assert str(capsule.worker_stage_dir / "05_final_report.md") in text
    assert "$CXOR_WORKER_STAGE_DIR/00_preflight.md" in text
    assert "$CXOR_WORKER_STAGE_DIR/05_final_report.md" in text


def test_codex_worker_env_exposes_cxor_timeout_and_soft_deadline(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch,
):
    ctx, patchlet, run_ctx, _ = _setup(git_repo)
    fake_codex = tmp_path / "codex"
    fake_codex.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path
run_dir = Path(os.environ["CXOR_RUN_DIR"])
(run_dir / "env.json").write_text(json.dumps(dict(os.environ), sort_keys=True), encoding="utf-8")
Path(os.environ["CXOR_REPORT_PATH"]).parent.mkdir(parents=True, exist_ok=True)
Path(os.environ["CXOR_REPORT_PATH"]).write_text(json.dumps({
    "schema_version": "1.0",
    "kind": "patchlet_report",
    "patchlet_id": "P0001",
    "status": "VERIFIED_NO_CHANGE_NEEDED",
    "changed_product_runtime_file": None,
    "changed_artifact_files": [".artifacts/probes/P0001/probe.py"],
    "probe_commands": ["python .artifacts/probes/P0001/probe.py"],
    "deterministic_run_counts": {"baseline": "5/5", "proof_of_fix": "5/5", "negative_controls": "5/5"},
    "root_cause_classification": {
        "observed_failure": "no change needed",
        "immediate_cause": "no change needed",
        "why_immediate_cause_happened": "already ok",
        "deeper_owner_boundary": "app.py",
        "producer_transformer_consumer_boundary": "producer app.py -> consumer probe",
        "not_downstream_of_unprobed_state_proof": "direct probe",
        "negative_control_proof": "negative control"
    },
    "before_after_state": [{"before": "ok", "after": "ok"}],
    "row_ledger": [],
    "trace_ledger": [],
    "cleanup_proof": "cleanup ok",
    "acceptance_criteria_result": "pass"
}), encoding="utf-8")
""",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("CODEX_PATCHLET_TIMEOUT_SECONDS", "90")

    CodexExecWorker().run_patchlet(ctx, patchlet, run_ctx=run_ctx)

    env = json.loads((run_ctx.run_dir / "env.json").read_text(encoding="utf-8"))
    assert env["CXOR_TIMEOUT_SECONDS"] == "90"
    assert env["CXOR_SOFT_DEADLINE_SECONDS"] == "30"
