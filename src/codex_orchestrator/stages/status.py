from __future__ import annotations

from codex_orchestrator.activity_classifier import classify_activity
from codex_orchestrator.jsonio import read_json
from codex_orchestrator.state import load_state
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.workflow_identity import read_workflow_identity
from codex_orchestrator.workflow_lifecycle import read_workflow_registry
from codex_orchestrator.semantic_goals import load_semantic_goal_spec
import subprocess


def status(ctx: TargetRepoContext) -> dict:
    state = load_state(ctx)
    manifest = read_json(ctx.paths.run_manifest) if ctx.paths.run_manifest.exists() else {"runs": []}
    runs = manifest.get("runs", []) if isinstance(manifest, dict) else []
    latest_run = runs[-1] if runs else {}
    activity = classify_activity(ctx.root)
    identity = read_workflow_identity(ctx.root) or {}
    registry = read_workflow_registry(ctx.root)
    preflight_path = ctx.paths.workflow_dir / "rerun_preflight_result.json"
    latest_preflight = read_json(preflight_path) if preflight_path.exists() else None
    latest_apply_result_path = ctx.paths.workflow_dir / "apply_results" / "latest_apply_result.json"
    latest_apply_result = read_json(latest_apply_result_path) if latest_apply_result_path.exists() else None
    goal_progress = _goal_progress_status(ctx)
    decomposition = _decomposition_status(ctx)
    master_prompt_proof = _master_prompt_proof_status(ctx)
    applyable_progress = _applyable_progress_status(ctx, goal_progress)
    patch_promotion = _patch_promotion_status(ctx)
    last_report_ingestion = None
    for run in reversed(runs):
        attempt_id = run.get("attempt_id")
        patchlet_id = run.get("patchlet_id")
        if not attempt_id:
            continue
        result_path = ctx.paths.runs_dir / attempt_id / "gates" / "report_ingestion_result.json"
        if result_path.exists():
            result = read_json(result_path)
            last_report_ingestion = {
                "patchlet_id": result.get("patchlet_id") or patchlet_id,
                "attempt_id": result.get("attempt_id") or attempt_id,
                "accepted": result.get("accepted"),
                "normalization_applied": result.get("normalization_applied"),
                "normalized_failure_signature": result.get("normalized_failure_signature"),
                "result_path": f".codex-orchestrator/runs/{attempt_id}/gates/report_ingestion_result.json",
            }
            break
    semantic_goal = _semantic_goal_status(ctx)
    return {
        "schema_version": "1.0",
        "kind": "operator_status",
        "workflow_id": state.workflow_id,
        "active_workflow_id": registry.get("active_workflow_id") or identity.get("workflow_id") or state.workflow_id,
        "run_id": identity.get("run_id"),
        "goal_fingerprint": identity.get("goal_fingerprint"),
        "master_prompt_path": identity.get("master_prompt_path"),
        "master_prompt_sha256": identity.get("master_prompt_sha256"),
        "target_head_sha_at_start": identity.get("target_head_sha"),
        "target_tree_sha_at_start": identity.get("target_tree_sha"),
        "target_dirty_status_at_start": identity.get("target_dirty_status_at_start", []),
        "current_target_dirty_status": _current_dirty_status(ctx),
        "latest_rerun_preflight": latest_preflight,
        "latest_apply_result": latest_apply_result,
        "repo": str(ctx.root),
        "stage": state.stage,
        "target_repo": str(ctx.root),
        "pending_patchlets": state.pending_patchlets,
        "completed_patchlets": state.completed_patchlets,
        "verified_no_change_needed": state.verified_no_change_needed,
        "failed_patchlets": state.failed_patchlets,
        "blocked_patchlets": state.blocked_patchlets,
        "current_patchlet_id": state.current_patchlet_id,
        "current_attempt_id": activity.get("current_attempt_id") or latest_run.get("attempt_id"),
        "current_loop_iteration": state.current_loop_iteration,
        "completed_patchlet_count": len(state.completed_patchlets) + len(state.verified_no_change_needed),
        "failed_patchlet_count": len(state.failed_patchlets),
        "pending_patchlet_count": len(state.pending_patchlets),
        "run_count": len(runs),
        "last_event": activity.get("last_event"),
        "active_prompt_path": activity.get("active_prompt_path"),
        "last_progress_path": activity.get("last_progress_path"),
        "last_progress_age_seconds": activity.get("last_progress_age_seconds"),
        "classification": activity.get("classification"),
        "next_action": activity.get("next_action"),
        "last_report_ingestion": last_report_ingestion,
        "semantic_goal": semantic_goal,
        "master_prompt_proof": master_prompt_proof,
        "goal_progress": goal_progress,
        "decomposition": decomposition,
        "applyable_progress": applyable_progress,
        "patch_promotion": patch_promotion,
    }


def _patch_promotion_status(ctx: TargetRepoContext) -> dict:
    if not ctx.paths.runs_dir.exists():
        return {"available": False}
    attempts = sorted([path for path in ctx.paths.runs_dir.iterdir() if path.is_dir()])
    for attempt_dir in reversed(attempts):
        hygiene_path = attempt_dir / "gates" / "worker_sandbox_hygiene_result.json"
        evidence_inventory_path = attempt_dir / "gates" / "worker_evidence_inventory.json"
        evidence_preservation_path = attempt_dir / "gates" / "worker_evidence_preservation_result.json"
        proposal_manifest_path = attempt_dir / "patch_promotion" / "patch_proposal_manifest.json"
        proposal_validation_path = attempt_dir / "patch_promotion" / "patch_proposal_validation_result.json"
        reconstruction_path = attempt_dir / "patch_promotion" / "patch_reconstruction_result.json"
        proof_path = attempt_dir / "gates" / "independent_probe_rerun_result.json"
        coverage_path = attempt_dir / "gates" / "goal_coverage_gate_result.json"
        semantic_quality_path = attempt_dir / "gates" / "worker_report_semantic_quality_result.json"
        canonical_semantic_path = attempt_dir / "gates" / "canonical_patchlet_semantic_result.json"
        preparation_path = attempt_dir / "patch_promotion" / "clean_candidate_preparation_result.json"
        promotion_path = attempt_dir / "patch_promotion" / "clean_candidate_promotion_result.json"
        disposal_path = attempt_dir / "patch_promotion" / "worker_sandbox_disposal_result.json"
        if not any(path.exists() for path in [hygiene_path, proposal_validation_path, reconstruction_path, proof_path, coverage_path, semantic_quality_path, canonical_semantic_path, preparation_path, promotion_path, disposal_path]):
            continue
        hygiene = read_json(hygiene_path) if hygiene_path.exists() else {}
        evidence_inventory = read_json(evidence_inventory_path) if evidence_inventory_path.exists() else {}
        proposal_manifest = read_json(proposal_manifest_path) if proposal_manifest_path.exists() else {}
        proposal = read_json(proposal_validation_path) if proposal_validation_path.exists() else {}
        reconstruction = read_json(reconstruction_path) if reconstruction_path.exists() else {}
        proof = read_json(proof_path) if proof_path.exists() else {}
        coverage = read_json(coverage_path) if coverage_path.exists() else {}
        semantic_quality = read_json(semantic_quality_path) if semantic_quality_path.exists() else {}
        canonical_semantic = read_json(canonical_semantic_path) if canonical_semantic_path.exists() else {}
        preparation = read_json(preparation_path) if preparation_path.exists() else {}
        promotion = read_json(promotion_path) if promotion_path.exists() else {}
        disposal = read_json(disposal_path) if disposal_path.exists() else {}
        promotion_accepted = promotion.get("promotion_accepted") is True
        hygiene_status = hygiene.get("status")
        return {
            "available": True,
            "attempt_id": attempt_dir.name,
            "worker_hygiene_status": hygiene_status,
            "sandbox_debris_count": hygiene.get("sandbox_debris_count", 0),
            "allowed_product_change_count": hygiene.get("allowed_product_change_count", 0),
            "allowed_path_violation_count": hygiene.get("allowed_path_violation_count", 0),
            "containment_violation_count": hygiene.get("containment_violation_count", 0),
            "diagnostic_evidence_files": evidence_inventory.get("captured_file_count", 0),
            "canonical_patch_paths": len(proposal_manifest.get("changed_paths", [])),
            "promotion_blocked": hygiene.get("promotion_blocked", False),
            "patch_proposal_status": "ACCEPTED" if proposal.get("accepted") is True else "REJECTED" if proposal else None,
            "clean_reconstruction_status": "ACCEPTED" if reconstruction.get("accepted") is True else "REJECTED" if reconstruction else None,
            "candidate_preparation_status": "PREPARED" if preparation.get("candidate_prepared") is True else "REJECTED" if preparation else None,
            "independent_proof_status": "ACCEPTED" if proof.get("accepted") is True else "REJECTED" if proof else None,
            "goal_coverage_status": "ACCEPTED" if coverage.get("accepted") is True else "REJECTED" if coverage else None,
            "worker_report_semantic_quality": semantic_quality.get("status"),
            "canonical_semantic_status": "ACCEPTED" if canonical_semantic.get("accepted") is True else "REJECTED" if canonical_semantic else None,
            "promotion_status": "ACCEPTED" if promotion_accepted else "REJECTED" if promotion else "NOT_PROMOTED",
            "sandbox_disposal_status": "COMPLETE" if disposal.get("cleanup_succeeded") is True else "INCOMPLETE" if disposal else None,
            "raw_worker_sandbox_promoted": False,
            "product_result": "accepted" if promotion_accepted else "prepared" if preparation else "rejected" if promotion else None,
            "candidate_scopes": {
                "worker_hygiene": hygiene.get("candidate_scope"),
                "patch_proposal": proposal.get("candidate_scope"),
                "clean_reconstruction": reconstruction.get("candidate_scope"),
                "candidate_preparation": preparation.get("candidate_scope"),
                "independent_proof": proof.get("candidate_scope"),
                "goal_coverage": coverage.get("candidate_scope"),
                "worker_report_semantic_quality": semantic_quality.get("candidate_scope"),
                "canonical_semantic": canonical_semantic.get("candidate_scope"),
                "promotion": promotion.get("candidate_scope"),
                "sandbox_disposal": disposal.get("candidate_scope"),
            },
            "artifact_paths": {
                "worker_hygiene": f".codex-orchestrator/runs/{attempt_dir.name}/gates/worker_sandbox_hygiene_result.json" if hygiene_path.exists() else None,
                "worker_evidence_inventory": f".codex-orchestrator/runs/{attempt_dir.name}/gates/worker_evidence_inventory.json" if evidence_inventory_path.exists() else None,
                "worker_evidence_preservation": f".codex-orchestrator/runs/{attempt_dir.name}/gates/worker_evidence_preservation_result.json" if evidence_preservation_path.exists() else None,
                "patch_proposal_validation": f".codex-orchestrator/runs/{attempt_dir.name}/patch_promotion/patch_proposal_validation_result.json" if proposal_validation_path.exists() else None,
                "clean_reconstruction": f".codex-orchestrator/runs/{attempt_dir.name}/patch_promotion/patch_reconstruction_result.json" if reconstruction_path.exists() else None,
                "candidate_preparation": f".codex-orchestrator/runs/{attempt_dir.name}/patch_promotion/clean_candidate_preparation_result.json" if preparation_path.exists() else None,
                "independent_proof": f".codex-orchestrator/runs/{attempt_dir.name}/gates/independent_probe_rerun_result.json" if proof_path.exists() else None,
                "goal_coverage": f".codex-orchestrator/runs/{attempt_dir.name}/gates/goal_coverage_gate_result.json" if coverage_path.exists() else None,
                "worker_report_semantic_quality": f".codex-orchestrator/runs/{attempt_dir.name}/gates/worker_report_semantic_quality_result.json" if semantic_quality_path.exists() else None,
                "canonical_semantic": f".codex-orchestrator/runs/{attempt_dir.name}/gates/canonical_patchlet_semantic_result.json" if canonical_semantic_path.exists() else None,
                "promotion": f".codex-orchestrator/runs/{attempt_dir.name}/patch_promotion/clean_candidate_promotion_result.json" if promotion_path.exists() else None,
                "sandbox_disposal": f".codex-orchestrator/runs/{attempt_dir.name}/patch_promotion/worker_sandbox_disposal_result.json" if disposal_path.exists() else None,
            },
        }
    return {"available": False}


def _current_dirty_status(ctx: TargetRepoContext) -> list[str]:
    result = subprocess.run(["git", "-C", str(ctx.root), "status", "--porcelain=v1"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line and not line[3:].startswith((".codex-orchestrator/", ".artifacts/"))]


def _semantic_goal_status(ctx: TargetRepoContext) -> dict:
    spec = load_semantic_goal_spec(ctx.root)
    result_path = ctx.paths.workflow_dir / "semantic_goal_checks" / "semantic_goal_check_result.json"
    check = read_json(result_path) if result_path.exists() else None
    if not spec:
        return {"mode": "missing", "status": "UNSUPPORTED", "criteria_count": 0, "passed": [], "failed": [], "spec_path": None, "latest_check_result_path": None}
    passed = []
    failed = []
    if check:
        for row in check.get("criteria", []):
            item = {
                "criterion_id": row.get("criterion_id"),
                "expected_value": row.get("expected_value"),
                "actual_value": row.get("actual_value"),
            }
            if row.get("passed") is True:
                passed.append(item)
            else:
                failed.append(item)
    status_value = "FAILED" if failed else ("PASSED" if passed else spec.get("semantic_status"))
    return {
        "mode": spec.get("semantic_mode"),
        "status": status_value,
        "criteria_count": len(spec.get("criteria", [])),
        "passed": passed,
        "failed": failed,
        "spec_path": ".codex-orchestrator/semantic_goal_spec.json",
        "latest_check_result_path": ".codex-orchestrator/semantic_goal_checks/semantic_goal_check_result.json" if check else None,
    }


def _goal_progress_status(ctx: TargetRepoContext) -> dict:
    path = ctx.paths.workflow_dir / "goal_progress.json"
    if not path.exists():
        return {"overall_goal_status": "NOT_STARTED", "required_obligations": 0, "proven": 0, "failed": 0, "blocked": 0, "unproven": 0}
    progress = read_json(path)
    counts = progress.get("counts", {})
    return {
        "overall_goal_status": progress.get("overall_goal_status"),
        "required_obligations": counts.get("required_obligations", 0),
        "proven": counts.get("proven", 0),
        "failed": counts.get("failed", 0),
        "blocked": counts.get("blocked", 0),
        "unproven": counts.get("unproven", 0),
        "goal_progress_path": ".codex-orchestrator/goal_progress.json",
        "decomposition": progress.get("decomposition", {}),
    }


def _decomposition_status(ctx: TargetRepoContext) -> dict:
    decomp_dir = ctx.paths.workflow_dir / "decomposition"
    plan = read_json(decomp_dir / "work_decomposition_plan.json") if (decomp_dir / "work_decomposition_plan.json").exists() else {}
    patchlet_index = read_json(ctx.paths.patchlet_index) if ctx.paths.patchlet_index.exists() else {"patchlets": []}
    patchlets = patchlet_index.get("patchlets", [])
    accepted_statuses = {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}
    accepted = [p["patchlet_id"] for p in patchlets if p.get("status") in accepted_statuses]
    blocked = [p["patchlet_id"] for p in patchlets if p.get("status") in {"FAILED_WITH_EVIDENCE", "BLOCKED_WITH_EVIDENCE", "BLOCKED_BY_FAILED_DEPENDENCY"}]
    accepted_set = set(accepted)
    ready = []
    waiting = []
    same_file: dict[str, list[str]] = {}
    for patchlet in patchlets:
        path = patchlet.get("allowed_product_runtime_file")
        if path:
            same_file.setdefault(path, []).append(patchlet["patchlet_id"])
        if patchlet.get("status") != "PENDING":
            continue
        deps = patchlet.get("dependency_patchlet_ids", patchlet.get("depends_on", []))
        if all(dep in accepted_set for dep in deps):
            ready.append(patchlet["patchlet_id"])
        else:
            waiting.append(patchlet["patchlet_id"])
    return {
        "work_slice_count": plan.get("work_slice_count", 0),
        "patchlet_count": len(patchlets) if patchlets else plan.get("patchlet_count", 0),
        "transaction_group_count": plan.get("transaction_group_count", 0),
        "same_file_multi_patchlet_groups": [
            {"file": path, "patchlet_ids": ids}
            for path, ids in sorted(same_file.items())
            if len(ids) > 1
        ],
        "ready_patchlets": ready,
        "waiting_patchlets": waiting,
        "accepted_patchlets": accepted,
        "blocked_patchlets": blocked,
        "decomposition_plan_path": ".codex-orchestrator/decomposition/work_decomposition_plan.json" if plan else None,
    }


def _master_prompt_proof_status(ctx: TargetRepoContext) -> dict:
    frozen = read_json(ctx.paths.workflow_dir / "master_prompt_frozen.json") if (ctx.paths.workflow_dir / "master_prompt_frozen.json").exists() else {}
    provability = read_json(ctx.paths.workflow_dir / "provability" / "provability_result.json") if (ctx.paths.workflow_dir / "provability" / "provability_result.json").exists() else {}
    concordance = read_json(ctx.paths.workflow_dir / "global_verification" / "master_prompt_concordance_result.json") if (ctx.paths.workflow_dir / "global_verification" / "master_prompt_concordance_result.json").exists() else {}
    satisfaction = read_json(ctx.paths.workflow_dir / "global_verification" / "master_prompt_satisfaction_result.json") if (ctx.paths.workflow_dir / "global_verification" / "master_prompt_satisfaction_result.json").exists() else {}
    return {
        "master_prompt_sha256": frozen.get("sha256"),
        "provability_status": provability.get("provability_status"),
        "goal_progress_path": ".codex-orchestrator/goal_progress.json" if (ctx.paths.workflow_dir / "goal_progress.json").exists() else None,
        "proof_obligations_path": ".codex-orchestrator/proof_obligations.json" if (ctx.paths.workflow_dir / "proof_obligations.json").exists() else None,
        "probe_plan_path": ".codex-orchestrator/probe_plan.json" if (ctx.paths.workflow_dir / "probe_plan.json").exists() else None,
        "master_prompt_concordance_status": concordance.get("coverage_status"),
        "master_prompt_satisfaction_status": satisfaction.get("satisfaction_status"),
    }


def _applyable_progress_status(ctx: TargetRepoContext, goal_progress: dict) -> dict:
    path = ctx.paths.workflow_dir / "goal_progress.json"
    progress = read_json(path) if path.exists() else {}
    stop_result_path = ctx.paths.workflow_dir / "control" / "stop_result.json"
    stop_result = read_json(stop_result_path) if stop_result_path.exists() else {}
    checkpoint = stop_result.get("latest_accepted_checkpoint") or progress.get("latest_accepted_checkpoint")
    return {
        "available": bool(checkpoint),
        "latest_accepted_checkpoint": checkpoint,
        "requires_allow_partial": load_state(ctx).stage != "DONE",
    }
