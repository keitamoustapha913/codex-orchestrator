from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import append_jsonl, read_json, write_json
from codex_orchestrator.operator_events import append_operator_event
from codex_orchestrator.proof_obligations import summarize_obligation_coverage
from codex_orchestrator.state import now_iso


def update_goal_progress(
    *,
    workflow_root: Path,
    event_reason: str,
    workflow_iteration: int | None,
    master_prompt_frozen: dict[str, Any] | None = None,
    provability_result: dict[str, Any] | None = None,
    proof_obligations: dict[str, Any] | None = None,
    probe_plan: dict[str, Any] | None = None,
    latest_gate_result: dict[str, Any] | None = None,
    latest_accepted_checkpoint: str | None = None,
) -> dict[str, Any]:
    existing = load_goal_progress(workflow_root) or {}
    frozen = master_prompt_frozen or _read_if_exists(workflow_root / "master_prompt_frozen.json") or {}
    provability = provability_result or _read_if_exists(workflow_root / "provability" / "provability_result.json") or {}
    obligations = proof_obligations or _read_if_exists(workflow_root / "proof_obligations.json") or {"obligations": []}
    patchlet_index = _read_if_exists(workflow_root / "patchlets" / "patchlet_index.json") or {"patchlets": []}
    decomposition_summary = _decomposition_summary(workflow_root, patchlet_index)
    counts = summarize_obligation_coverage(obligations)
    if latest_gate_result and latest_gate_result.get("accepted"):
        for obligation in obligations.get("obligations", []):
            if obligation.get("obligation_id") in latest_gate_result.get("covered_obligation_ids", []):
                obligation["status"] = "PROVEN_BY_ORCHESTRATOR"
                obligation["evidence_paths"] = latest_gate_result.get("evidence_paths", [])
    counts = summarize_obligation_coverage(obligations)
    overall = _overall_status(provability, counts, latest_gate_result)
    latest_checkpoint = latest_accepted_checkpoint or existing.get("latest_accepted_checkpoint")
    progress = {
        "schema_version": "1.0",
        "kind": "goal_progress",
        "workflow_id": frozen.get("workflow_id") or existing.get("workflow_id"),
        "run_id": frozen.get("run_id") or existing.get("run_id"),
        "master_prompt_sha256": frozen.get("sha256") or existing.get("master_prompt_sha256"),
        "updated_at": now_iso(),
        "workflow_iteration": workflow_iteration,
        "overall_goal_status": overall,
        "provability_status": provability.get("provability_status", existing.get("provability_status", "NOT_STARTED")),
        "counts": counts,
        "obligations": [_progress_obligation(row, latest_gate_result) for row in obligations.get("obligations", [])],
        "latest_accepted_checkpoint": latest_checkpoint,
        "applyable_progress": bool(latest_checkpoint),
        "next_action": _next_action(overall, counts),
        "event_reason": event_reason,
        "decomposition": decomposition_summary,
    }
    write_json(workflow_root / "goal_progress.json", progress)
    append_jsonl(workflow_root / "goal_progress.jsonl", progress)
    append_operator_event(
        workflow_root.parent,
        event_type="goal_progress_updated",
        severity="info",
        stage="GOAL_PROGRESS",
        summary=(
            f"goal progress: {counts['proven']}/{counts['required_obligations']} obligations proven, "
            f"{counts['failed']} failed, {counts['unproven']} unproven."
        ),
        artifact_paths=[".codex-orchestrator/goal_progress.json"],
        next_action=progress["next_action"],
        details={
            "overall_goal_status": overall,
            "required_obligations": counts["required_obligations"],
            "proven": counts["proven"],
            "failed": counts["failed"],
            "blocked": counts["blocked"],
            "unproven": counts["unproven"],
            "goal_progress_path": ".codex-orchestrator/goal_progress.json",
            "decomposition": decomposition_summary,
        },
    )
    return progress


def load_goal_progress(workflow_root: Path) -> dict[str, Any] | None:
    path = workflow_root / "goal_progress.json"
    return read_json(path) if path.exists() else None


def _read_if_exists(path: Path) -> dict[str, Any] | None:
    return read_json(path) if path.exists() else None


def _decomposition_summary(workflow_root: Path, patchlet_index: dict[str, Any]) -> dict[str, Any]:
    plan = _read_if_exists(workflow_root / "decomposition" / "work_decomposition_plan.json") or {}
    patchlets = patchlet_index.get("patchlets", [])
    accepted_statuses = {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}
    failed_statuses = {"FAILED_WITH_EVIDENCE", "BLOCKED_WITH_EVIDENCE"}
    accepted = [p["patchlet_id"] for p in patchlets if p.get("status") in accepted_statuses]
    blocked = [p["patchlet_id"] for p in patchlets if p.get("status") in failed_statuses]
    ready: list[str] = []
    waiting: list[str] = []
    accepted_set = set(accepted)
    for patchlet in patchlets:
        if patchlet.get("status") != "PENDING":
            continue
        deps = patchlet.get("dependency_patchlet_ids", patchlet.get("depends_on", []))
        if all(dep in accepted_set for dep in deps):
            ready.append(patchlet["patchlet_id"])
        else:
            waiting.append(patchlet["patchlet_id"])
    per_file: dict[str, int] = {}
    same_file: dict[str, list[str]] = {}
    for patchlet in patchlets:
        path = patchlet.get("allowed_product_runtime_file")
        if not path:
            continue
        per_file[path] = per_file.get(path, 0) + 1
        same_file.setdefault(path, []).append(patchlet["patchlet_id"])
    same_file_groups = [
        {"file": path, "patchlet_ids": ids}
        for path, ids in sorted(same_file.items())
        if len(ids) > 1
    ]
    return {
        "work_slice_count": plan.get("work_slice_count", 0),
        "patchlet_count": len(patchlets) if patchlets else plan.get("patchlet_count", 0),
        "transaction_group_count": plan.get("transaction_group_count", 0),
        "total_patchlets": len(patchlets),
        "accepted_patchlets": accepted,
        "blocked_patchlets": blocked,
        "waiting_patchlets": waiting,
        "ready_patchlets": ready,
        "per_file_patchlet_counts": dict(sorted(per_file.items())),
        "same_file_multi_patchlet_groups": same_file_groups,
        "decomposition_plan_path": ".codex-orchestrator/decomposition/work_decomposition_plan.json" if plan else None,
    }


def _overall_status(provability: dict[str, Any], counts: dict[str, int], latest_gate_result: dict[str, Any] | None) -> str:
    if provability.get("can_start_product_patchlets") is False:
        return "UNPROVABLE" if provability.get("provability_status") in {"AMBIGUOUS", "UNPROVABLE"} else "BLOCKED"
    if counts["required_obligations"] and counts["proven"] == counts["required_obligations"]:
        return "PROVEN"
    if counts["proven"]:
        return "PARTIALLY_PROVEN"
    if counts["failed"]:
        return "FAILED"
    return "IN_PROGRESS" if counts["required_obligations"] else "PROVABILITY_ASSESSMENT"


def _progress_obligation(row: dict[str, Any], latest_gate_result: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "obligation_id": row.get("obligation_id"),
        "status": row.get("status", "UNPROVEN"),
        "last_patchlet_id": (latest_gate_result or {}).get("patchlet_id"),
        "last_attempt_id": (latest_gate_result or {}).get("attempt_id"),
        "evidence_paths": row.get("evidence_paths", []),
        "operator_summary": "Required behavior was independently proven." if row.get("status") == "PROVEN_BY_ORCHESTRATOR" else row.get("statement", ""),
    }


def _next_action(overall: str, counts: dict[str, int]) -> str:
    if overall == "PROVEN":
        return "Run global master prompt satisfaction verification."
    if overall in {"UNPROVABLE", "BLOCKED"}:
        return "Stop before product patchlets and inspect provability evidence."
    return "Continue with remaining unproven obligations."
