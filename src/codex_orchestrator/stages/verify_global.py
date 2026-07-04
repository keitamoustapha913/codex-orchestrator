from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codex_orchestrator.errors import StagePreconditionError
from codex_orchestrator.integration_state import target_product_runtime_clean, write_final_diff
from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.operator_events import append_operator_event
from codex_orchestrator.state import load_state, now_iso, transition
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.validators.report_validator import ReportValidationError, validate_patchlet_report_file
from codex_orchestrator.semantic_goals import load_semantic_goal_spec, required_structured_criteria
from .verify_group import verify_all_groups


@dataclass(frozen=True)
class GlobalVerificationResult:
    done: bool
    status: str
    failed_patchlets: list[str]
    unproven_patchlets: list[str]
    artifact_path: str


def _global_verification_dir(ctx: TargetRepoContext) -> Path:
    return ctx.paths.workflow_dir / "global_verification"


def _latest_run_manifest(ctx: TargetRepoContext) -> dict:
    return read_json(ctx.paths.run_manifest) if ctx.paths.run_manifest.exists() else {"runs": []}


def _repair_plan_summary(ctx: TargetRepoContext, plan_path: Path) -> dict:
    plan = read_json(plan_path)
    application_path = plan_path.with_name(f"{plan['repair_plan_id']}_application.json")
    application_exists = application_path.exists()
    application = read_json(application_path) if application_exists else {}
    return {
        "repair_plan_id": plan["repair_plan_id"],
        "classification": plan.get("classification"),
        "recommended_action": plan.get("recommended_action"),
        "source_failure_ids": plan.get("source_failure_ids", []),
        "generated_patchlet_ids": plan.get("generated_patchlet_ids", []),
        "application_artifact": f".codex-orchestrator/repair_plans/{plan['repair_plan_id']}_application.json" if application_exists else None,
        "application_exists": application_exists,
        "next_stage": application.get("next_stage"),
        "requires_patchlet_regeneration": bool(plan.get("requires_patchlet_regeneration", False)),
    }


def _latest_semantic_result(ctx: TargetRepoContext) -> dict:
    spec = load_semantic_goal_spec(ctx.root)
    criteria = required_structured_criteria(spec)
    result_path = ctx.paths.workflow_dir / "semantic_goal_checks" / "semantic_goal_check_result.json"
    result = read_json(result_path) if result_path.exists() else None
    if not spec:
        return _semantic_summary("UNSUPPORTED", None, [], [], [], [], [])
    if not criteria:
        return _semantic_summary("UNSUPPORTED", ".codex-orchestrator/semantic_goal_spec.json", [], [], [], [], [])
    required_ids = [criterion["criterion_id"] for criterion in criteria]
    if not result:
        return _semantic_summary("BLOCKED", ".codex-orchestrator/semantic_goal_spec.json", [], [], required_ids, [], [])
    rows = result.get("criteria", [])
    proven = [row["criterion_id"] for row in rows if row.get("passed") is True]
    failed = [row["criterion_id"] for row in rows if row.get("passed") is not True]
    unproven = [criterion_id for criterion_id in required_ids if criterion_id not in proven and criterion_id not in failed]
    status = "FAILED" if failed else ("BLOCKED" if unproven else "PASSED")
    matrix_rows = [
        {
            "criterion_id": row.get("criterion_id"),
            "status": "PASSED" if row.get("passed") else "FAILED",
            "expected": row.get("expected_value"),
            "actual": row.get("actual_value"),
            "evidence": ".codex-orchestrator/semantic_goal_checks/semantic_goal_check_result.json",
        }
        for row in rows
    ]
    return _semantic_summary(
        status,
        ".codex-orchestrator/semantic_goal_spec.json",
        [".codex-orchestrator/semantic_goal_checks/semantic_goal_check_result.json"],
        proven,
        unproven,
        failed,
        matrix_rows,
    )


def _semantic_summary(
    status: str,
    spec_path: str | None,
    check_results: list[str],
    proven: list[str],
    unproven: list[str],
    failed: list[str],
    matrix_rows: list[dict],
) -> dict:
    return {
        "semantic_goal_status": status,
        "semantic_goal_spec_path": spec_path,
        "semantic_goal_check_results": check_results,
        "proven_semantic_criterion_ids": proven,
        "unproven_semantic_criterion_ids": unproven,
        "failed_semantic_criterion_ids": failed,
        "semantic_goals": matrix_rows,
    }


def verify_global(ctx: TargetRepoContext) -> GlobalVerificationResult:
    index = read_json(ctx.paths.patchlet_index) if ctx.paths.patchlet_index.exists() else {"patchlets": []}
    goal_spec = read_json(ctx.paths.goal_spec) if ctx.paths.goal_spec.exists() else {"success_goals": [], "target_invariants": []}
    invariants_document = read_json(ctx.paths.invariants) if ctx.paths.invariants.exists() else {"invariants": []}
    transaction_groups = read_json(ctx.paths.transaction_groups) if ctx.paths.transaction_groups.exists() else {"transaction_groups": []}
    repair_plans = sorted(
        path
        for path in ctx.paths.repair_plans_dir.glob("RP*.json")
        if not path.name.endswith("_application.json")
    )
    run_manifest = _latest_run_manifest(ctx)
    state = load_state(ctx)
    append_operator_event(
        ctx.root,
        event_type="global_verifier_started",
        severity="info",
        stage="GLOBAL_VERIFICATION",
        summary="Started global verifier.",
        artifact_paths=[],
        next_action="Checking final workflow acceptance.",
    )
    append_operator_event(
        ctx.root,
        event_type="verifier_no_prompt",
        severity="debug",
        stage="GLOBAL_VERIFICATION",
        summary="Global verifier is deterministic; no Codex prompt exists.",
        artifact_paths=[],
        terminal_hint="No prompt is generated for this deterministic global verifier.",
    )
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
        patchlet_runs = [
            run for run in read_json(ctx.paths.run_manifest).get("runs", [])
            if run.get("patchlet_id") == pid
        ] if run_manifest.get("runs") else []
        latest_run = patchlet_runs[-1] if patchlet_runs else None
        wrapper_gate_path = None
        if latest_run and latest_run.get("wrapper_gate_result"):
            wrapper_gate_path = ctx.root / latest_run["wrapper_gate_result"]
            if wrapper_gate_path.exists():
                wrapper_gate = read_json(wrapper_gate_path)
                if wrapper_gate.get("accepted") is not True:
                    failed.append(pid)
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
    integration_final = write_final_diff(ctx)
    target_working_tree_clean = target_product_runtime_clean(ctx)
    semantic = _latest_semantic_result(ctx)

    done = (
        bool(index.get("patchlets"))
        and not failed
        and not unproven
        and target_working_tree_clean
        and all_groups_passed
        and not failed_invariant_ids
        and not unproven_invariant_ids
        and not unresolved_failures
        and not unproven_goal_ids
        and semantic["semantic_goal_status"] in {"PASSED", "UNSUPPORTED"}
    )
    verification_dir = _global_verification_dir(ctx)
    verification_dir.mkdir(parents=True, exist_ok=True)
    matrix_path = verification_dir / "verification_matrix.json"
    global_gate_path = verification_dir / "gates" / "global_gate_result.json"
    global_gate_path.parent.mkdir(parents=True, exist_ok=True)
    verification_matrix = {
        "schema_version": "1.0",
        "kind": "verification_matrix",
        "goals": [
            {
                "goal_id": goal_id,
                "status": "PROVEN" if goal_id in proven_goal_ids else "UNPROVEN",
            }
            for goal_id in all_goal_ids
        ],
        "invariants": [
            {
                "invariant_id": invariant["invariant_id"],
                "status": (
                    "PROVEN"
                    if invariant["invariant_id"] in proven_invariant_ids
                    else "FAILED"
                    if invariant["invariant_id"] in failed_invariant_ids
                    else "UNPROVEN"
                ),
            }
            for invariant in all_invariants
        ],
        "transaction_groups": transaction_group_results,
        "repair_plans": [_repair_plan_summary(ctx, plan_path) for plan_path in repair_plans],
        "patchlets": [
            {
                "patchlet_id": patchlet["patchlet_id"],
                "status": patchlet.get("status"),
                "wrapper_gate_result": next(
                    (
                        run.get("wrapper_gate_result")
                        for run in reversed(run_manifest.get("runs", []))
                        if run.get("patchlet_id") == patchlet["patchlet_id"]
                    ),
                    None,
                ),
            }
            for patchlet in patchlets
        ],
        "failures": all_failure_ids,
        "semantic_goals": semantic["semantic_goals"],
        "unresolved": unresolved_failures,
        "verdict": "DONE_ALLOWED" if done else "DONE_BLOCKED",
    }
    write_json(matrix_path, verification_matrix)
    write_json(global_gate_path, {
        "schema_version": "1.0",
        "kind": "global_gate_result",
        "accepted": done,
        "verification_matrix": str(matrix_path),
        "reasons": unresolved_failures
        or failed
        or unproven
        or failed_invariant_ids
        or unproven_invariant_ids
        or unproven_goal_ids
        or semantic["failed_semantic_criterion_ids"]
        or semantic["unproven_semantic_criterion_ids"],
    })
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
        "verification_matrix": str(matrix_path),
        "global_gate_result": str(global_gate_path),
        "semantic_goal_status": semantic["semantic_goal_status"],
        "semantic_goal_spec_path": semantic["semantic_goal_spec_path"],
        "semantic_goal_check_results": semantic["semantic_goal_check_results"],
        "proven_semantic_criterion_ids": semantic["proven_semantic_criterion_ids"],
        "unproven_semantic_criterion_ids": semantic["unproven_semantic_criterion_ids"],
        "failed_semantic_criterion_ids": semantic["failed_semantic_criterion_ids"],
        **integration_final,
        "target_working_tree_clean": target_working_tree_clean,
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
        append_operator_event(
            ctx.root,
            event_type="global_verifier_passed",
            severity="success",
            stage="GLOBAL_VERIFICATION",
            summary="Global verifier passed; workflow DONE.",
            artifact_paths=[
                str(ctx.paths.final_verification_json.relative_to(ctx.root)),
                str(matrix_path.relative_to(ctx.root)),
                str(global_gate_path.relative_to(ctx.root)),
            ],
            next_action="Workflow reached DONE.",
        )
        append_operator_event(
            ctx.root,
            event_type="workflow_done",
            severity="success",
            stage="DONE",
            summary="Workflow reached DONE.",
            artifact_paths=[str(ctx.paths.final_verification_json.relative_to(ctx.root))],
        )
    else:
        transition(ctx, state, "FAILURE_CLASSIFICATION_REQUIRED", reason="global verification failed")
        append_operator_event(
            ctx.root,
            event_type="global_verifier_failed",
            severity="error",
            stage="GLOBAL_VERIFICATION",
            summary="Global verifier failed; repair planning next.",
            artifact_paths=[
                str(ctx.paths.final_verification_json.relative_to(ctx.root)),
                str(matrix_path.relative_to(ctx.root)),
                str(global_gate_path.relative_to(ctx.root)),
            ],
            next_action="Classifying global verification failure.",
            details={"failed_patchlets": failed, "unproven_patchlets": unproven},
        )
        append_operator_event(
            ctx.root,
            event_type="workflow_safe_failed",
            severity="error",
            stage="FAILURE_CLASSIFICATION_REQUIRED",
            summary="Workflow safe-failed with verification evidence.",
            artifact_paths=[str(ctx.paths.final_verification_json.relative_to(ctx.root))],
        )
    return GlobalVerificationResult(
        done=done,
        status=status,
        failed_patchlets=failed,
        unproven_patchlets=unproven,
        artifact_path=str(ctx.paths.final_verification_json),
    )
