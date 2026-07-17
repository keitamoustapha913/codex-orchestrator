from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from codex_orchestrator.goal_coverage import evaluate_goal_coverage_gate
from codex_orchestrator.independent_probe_rerun import run_independent_probe_rerun_gate
from codex_orchestrator.jsonio import write_json
from codex_orchestrator.report_ingestion import ingest_patchlet_report
from codex_orchestrator.target_repo import resolve_target_repo


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def _ctx(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Test User"], repo)
    (repo / "observability.ini").write_text("metrics=disabled\n", encoding="utf-8")
    (repo / "master_prompt.md").write_text("Enable observability metrics and prove it.\n", encoding="utf-8")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-m", "initial"], repo)
    ctx = resolve_target_repo(repo, allow_self_target=True)
    for path in [ctx.paths.workflow_dir, ctx.paths.reports_dir, ctx.paths.runs_dir, ctx.paths.probe_dir / "P0002" / "run_001"]:
        path.mkdir(parents=True, exist_ok=True)
    artifact = ctx.paths.probe_dir / "P0002" / "run_001" / "cleanup_proof.json"
    artifact.write_text(json.dumps({"cleanup": True}) + "\n", encoding="utf-8")
    return ctx, artifact


def _patchlet() -> dict[str, Any]:
    return {
        "patchlet_id": "P0002",
        "work_slice_id": "WS002",
        "allowed_product_runtime_file": "observability.ini",
        "goal_item_ids": ["GI004"],
        "proof_obligation_ids": ["PO004"],
    }


def _proof_obligations():
    return {
        "schema_version": "1.0",
        "workflow_id": "WF-TEST",
        "run_id": "R-TEST",
        "master_prompt_sha256": "0" * 64,
        "obligations": [
            {
                "obligation_id": "PO004",
                "goal_item_ids": ["GI004"],
                "required": True,
                "claim": "observability metrics must be enabled",
            }
        ],
    }


def _probe_plan():
    return {
        "schema_version": "1.0",
        "workflow_id": "WF-TEST",
        "run_id": "R-TEST",
        "probes": [
            {
                "probe_id": "GP004",
                "obligation_ids": ["PO004"],
                "rerunnable_by_orchestrator": True,
                "execution_context": "target_repo",
                "command": "grep -qx 'metrics=enabled' observability.ini",
                "expected_observation": {"type": "exit_code_zero", "value": 0},
            }
        ],
    }


def _report(ctx, artifact: Path, probe_artifact_refs: list[Any]) -> dict[str, Any]:
    rel = artifact.relative_to(ctx.root).as_posix()
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    return {
        "schema_version": "2.0",
        "kind": "worker_patchlet_report",
        "patchlet_id": "P0002",
        "status": "COMPLETE",
        "changed_product_runtime_file": "observability.ini",
        "changed_artifact_files": [".codex-orchestrator/reports/P0002.json"],
        "probe_commands": ["grep -qx 'metrics=enabled' observability.ini"],
        "deterministic_run_counts": {"baseline": "5/5", "proof_of_fix": "5/5", "negative_controls": "5/5"},
        "root_cause_classification": {
            "observed_failure": "metrics disabled",
            "immediate_cause": "observability setting was disabled",
            "why_immediate_cause_happened": "initial target state sets metrics=disabled",
            "deeper_owner_boundary": "target configuration",
            "producer_transformer_consumer_boundary": "repo file -> worker report -> report validator",
            "not_downstream_of_unprobed_state_proof": "probe artifact refs validate through ingestion",
            "negative_control_proof": "unsafe refs are rejected before proof rerun",
            "recursive_why_audit": ["why"],
        },
        "before_after_state": [{"key": "metrics", "before": "disabled", "after": "enabled"}],
        "row_ledger": [{"path": rel, "kind": "row"}],
        "trace_ledger": [{"path": rel, "kind": "trace"}],
        "cleanup_proof": "temporary target only",
        "probe_artifact_refs": probe_artifact_refs
        or [
            {
                "patchlet_id": "P0002",
                "probe_root": ".artifacts/probes/P0002/run_001",
                "run_id": "run_001",
                "files": [{"path": rel, "kind": "cleanup_proof", "sha256": digest, "size_bytes": artifact.stat().st_size}],
            }
        ],
    }


def _stale_ref(artifact: Path, ctx) -> dict[str, Any]:
    return {
        "patchlet_id": "P0002",
        "probe_root": ".artifacts/probes/P0002/run_001",
        "run_id": "run_001",
        "files": [
            {
                "path": artifact.relative_to(ctx.root).as_posix(),
                "kind": "cleanup_proof",
                "sha256": "f" * 64,
                "size_bytes": 999999,
                "description": "worker stale metadata",
            }
        ],
    }


def _run_path(tmp_path: Path, refs_factory):
    ctx, artifact = _ctx(tmp_path)
    (ctx.root / "observability.ini").write_text("metrics=enabled\n", encoding="utf-8")
    report_path = ctx.paths.reports_dir / "P0002.json"
    refs = refs_factory(ctx, artifact)
    write_json(report_path, _report(ctx, artifact, refs))
    ingestion = ingest_patchlet_report(ctx, patchlet=_patchlet(), attempt_id="P0002_attempt1", report_path=report_path)
    if not ingestion["accepted"]:
        return ingestion, None, None
    independent = run_independent_probe_rerun_gate(
        repo_root=ctx.root,
        workflow_root=ctx.paths.workflow_dir,
        attempt_id="P0002_attempt1",
        patchlet_id="P0002",
        proof_obligations=_proof_obligations(),
        probe_plan=_probe_plan(),
        integration_ref=None,
        execution_root=ctx.root,
        patchlet=_patchlet(),
        scope="patchlet",
    )
    coverage = evaluate_goal_coverage_gate(
        proof_obligations=_proof_obligations(),
        probe_plan=_probe_plan(),
        independent_probe_rerun_result=independent,
        patchlet_id="P0002",
        attempt_id="P0002_attempt1",
    )
    return ingestion, independent, coverage


def test_object_probe_artifact_ref_reaches_report_validation_after_canonicalization(tmp_path: Path):
    ingestion, _, _ = _run_path(tmp_path, lambda ctx, artifact: [_stale_ref(artifact, ctx)])

    assert ingestion["accepted"] is True


def test_object_probe_artifact_ref_reaches_independent_probe_rerun_after_canonicalization(tmp_path: Path):
    ingestion, independent, _ = _run_path(tmp_path, lambda ctx, artifact: [_stale_ref(artifact, ctx)])

    assert ingestion["accepted"] is True
    assert independent["accepted"] is True
    assert independent["proven_obligation_ids"] == ["PO004"]


def test_object_probe_artifact_ref_reaches_goal_coverage_after_canonicalization(tmp_path: Path):
    ingestion, _, coverage = _run_path(tmp_path, lambda ctx, artifact: [_stale_ref(artifact, ctx)])

    assert ingestion["accepted"] is True
    assert coverage["accepted"] is True
    assert coverage["accepted_for_patchlet_progress"] is True


def test_missing_file_does_not_reach_independent_probe(tmp_path: Path):
    ingestion, independent, coverage = _run_path(tmp_path, lambda ctx, artifact: [{**_stale_ref(artifact, ctx), "files": [{"path": ".artifacts/probes/P0002/run_001/missing.json"}]}])

    assert ingestion["accepted"] is False
    assert independent is None
    assert coverage is None


def test_patchlet_mismatch_does_not_reach_independent_probe(tmp_path: Path):
    ingestion, independent, coverage = _run_path(tmp_path, lambda ctx, artifact: [{**_stale_ref(artifact, ctx), "patchlet_id": "P9999"}])

    assert ingestion["accepted"] is False
    assert independent is None
    assert coverage is None


def test_unsafe_path_does_not_reach_independent_probe(tmp_path: Path):
    ingestion, independent, coverage = _run_path(tmp_path, lambda ctx, artifact: [{**_stale_ref(artifact, ctx), "files": [{"path": "observability.ini"}]}])

    assert ingestion["accepted"] is False
    assert independent is None
    assert coverage is None
