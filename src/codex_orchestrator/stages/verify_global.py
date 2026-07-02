from __future__ import annotations

from dataclasses import dataclass

from codex_orchestrator.errors import StagePreconditionError
from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.state import load_state, now_iso, transition
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.validators.report_validator import ReportValidationError, validate_patchlet_report_file
from .verify_group import verify_all_groups


@dataclass(frozen=True)
class GlobalVerificationResult:
    done: bool
    status: str
    failed_patchlets: list[str]
    unproven_patchlets: list[str]


def verify_global(ctx: TargetRepoContext) -> GlobalVerificationResult:
    index = read_json(ctx.paths.patchlet_index) if ctx.paths.patchlet_index.exists() else {"patchlets": []}
    goal_spec = read_json(ctx.paths.goal_spec) if ctx.paths.goal_spec.exists() else {"success_goals": [], "target_invariants": []}
    invariants_document = read_json(ctx.paths.invariants) if ctx.paths.invariants.exists() else {"invariants": []}
    transaction_groups = read_json(ctx.paths.transaction_groups) if ctx.paths.transaction_groups.exists() else {"transaction_groups": []}
    state = load_state(ctx)
    patchlets = index.get("patchlets", [])
    patchlets_by_id = {patchlet["patchlet_id"]: patchlet for patchlet in patchlets}
    failed: list[str] = []
    unproven: list[str] = []
    proven: list[str] = []
    resolved_source_patchlets: set[str] = set()
    resolved_failure_ids: list[str] = []
    passed_probe_commands: list[str] = []
    failed_probe_commands: list[str] = []
    passed_regression_commands: list[str] = []
    failed_regression_commands: list[str] = []
    evidence: list[str] = []

    if transaction_groups.get("transaction_groups"):
        try:
            verify_all_groups(ctx)
        except StagePreconditionError:
            pass
        transaction_groups = read_json(ctx.paths.transaction_groups) if ctx.paths.transaction_groups.exists() else {"transaction_groups": []}

    def _validated_report_status(patchlet_id: str) -> str | None:
        patchlet = patchlets_by_id.get(patchlet_id)
        if patchlet is None:
            return None
        report_path = ctx.paths.reports_dir / f"{patchlet_id}.json"
        if not report_path.exists():
            return None
        try:
            report = validate_patchlet_report_file(report_path, patchlet)
        except ReportValidationError:
            return None
        return report["status"]

    for cycle in state.repair_cycles:
        generated_patchlet_ids = cycle.get("generated_patchlet_ids", [])
        if not generated_patchlet_ids:
            continue
        statuses = [_validated_report_status(pid) for pid in generated_patchlet_ids]
        if not statuses or any(status not in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"} for status in statuses):
            continue
        for failure_id in cycle.get("source_failure_ids", []):
            failure_path = ctx.paths.failures_dir / f"{failure_id}.json"
            if not failure_path.exists():
                continue
            failure = read_json(failure_path)
            source_id = failure.get("source_id")
            if source_id:
                resolved_source_patchlets.add(source_id)
                resolved_failure_ids.append(failure_id)

    for patchlet in patchlets:
        pid = patchlet["patchlet_id"]
        patchlet_status = patchlet.get("status")
        if pid in resolved_source_patchlets:
            continue
        if patchlet_status in {"FAILED_WITH_EVIDENCE", "BLOCKED_WITH_EVIDENCE"}:
            failed.append(pid)
            continue
        report_path = ctx.paths.reports_dir / f"{pid}.json"
        if not report_path.exists():
            unproven.append(pid)
            continue
        try:
            report = validate_patchlet_report_file(report_path, patchlet)
        except ReportValidationError:
            failed.append(pid)
            continue
        if report["status"] in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}:
            proven.append(pid)
            passed_probe_commands.extend(report.get("probe_commands", []))
            evidence.extend(report.get("probe_artifact_refs", []))
        elif report["status"] in {"FAILED_WITH_EVIDENCE", "BLOCKED_WITH_EVIDENCE"}:
            failed.append(pid)
            failed_probe_commands.extend(report.get("probe_commands", []))
        else:
            unproven.append(pid)

    transaction_group_results: list[dict] = []
    all_groups_passed = True
    for group in transaction_groups.get("transaction_groups", []):
        transaction_group_results.append({
            "transaction_group_id": group["transaction_group_id"],
            "status": group.get("status", "PENDING"),
            "patchlet_ids": group.get("patchlet_ids", []),
            "invariant_ids": group.get("invariant_ids", []),
        })
        if group.get("status") != "PASSED":
            all_groups_passed = False

    all_goal_ids = [goal["goal_id"] for goal in goal_spec.get("success_goals", [])]
    all_invariants = invariants_document.get("invariants", [])
    proven_invariant_ids: list[str] = []
    failed_invariant_ids: list[str] = []
    unproven_invariant_ids: list[str] = []
    for invariant in all_invariants:
        invariant_id = invariant["invariant_id"]
        group_statuses = [
            result["status"]
            for result in transaction_group_results
            if invariant_id in result.get("invariant_ids", [])
        ]
        if not invariant.get("required_probes") or not invariant.get("negative_controls"):
            unproven_invariant_ids.append(invariant_id)
        elif any(status == "FAILED" for status in group_statuses):
            failed_invariant_ids.append(invariant_id)
        elif group_statuses and all(status == "PASSED" for status in group_statuses):
            proven_invariant_ids.append(invariant_id)
        else:
            unproven_invariant_ids.append(invariant_id)

    proven_goal_ids: list[str] = []
    unproven_goal_ids: list[str] = []
    for goal_id in all_goal_ids:
        goal_invariants = [invariant["invariant_id"] for invariant in all_invariants if invariant.get("master_goal_id") == goal_id]
        if goal_invariants and all(invariant_id in proven_invariant_ids for invariant_id in goal_invariants):
            proven_goal_ids.append(goal_id)
        else:
            unproven_goal_ids.append(goal_id)

    all_failure_ids = sorted(path.stem for path in ctx.paths.failures_dir.glob("F*.json"))
    unresolved_failures = [failure_id for failure_id in all_failure_ids if failure_id not in resolved_failure_ids]

    done = (
        bool(index.get("patchlets"))
        and not failed
        and not unproven
        and all_groups_passed
        and not failed_invariant_ids
        and not unproven_invariant_ids
        and not unresolved_failures
        and not unproven_goal_ids
    )
    status = "DONE" if done else "FAILED"
    final = {
        "schema_version": "1.0",
        "kind": "final_verification",
        "status": status,
        "proven_goal_ids": proven_goal_ids,
        "unproven_goal_ids": unproven_goal_ids,
        "proven_invariant_ids": proven_invariant_ids,
        "failed_invariant_ids": failed_invariant_ids,
        "unproven_invariant_ids": unproven_invariant_ids,
        "transaction_group_results": transaction_group_results,
        "passed_probe_commands": passed_probe_commands,
        "failed_probe_commands": failed_probe_commands,
        "passed_regression_commands": passed_regression_commands,
        "failed_regression_commands": failed_regression_commands,
        "changed_files": [],
        "allowed_diff_result": "pass" if not failed else "fail",
        "resolved_failures": resolved_failure_ids,
        "unresolved_failures": unresolved_failures,
        "created_at": now_iso(),
        "repair_cycles": state.repair_cycles,
        "evidence": [str(item) for item in evidence],
    }
    write_json(ctx.paths.final_verification_json, final)
    ctx.paths.final_verification_md.write_text(
        "# Final Verification\n\n"
        f"Status: `{status}`\n\n"
        f"Proven goals: {', '.join(proven_goal_ids) or 'none'}\n\n"
        f"Proven invariants: {', '.join(proven_invariant_ids) or 'none'}\n\n"
        f"Unresolved failures: {', '.join(unresolved_failures) or 'none'}\n",
        encoding="utf-8",
    )
    if done:
        transition(ctx, state, "DONE", reason="global verification passed")
    else:
        transition(ctx, state, "FAILURE_CLASSIFICATION_REQUIRED", reason="global verification failed")
    return GlobalVerificationResult(done=done, status=status, failed_patchlets=failed, unproven_patchlets=unproven)
