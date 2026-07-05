from __future__ import annotations

from pathlib import Path

from codex_orchestrator.errors import StagePreconditionError
from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.operator_events import append_operator_event
from codex_orchestrator.state import load_state, now_iso, transition
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.validators.report_validator import ReportValidationError, validate_patchlet_report_file
from codex_orchestrator.run_records import load_run_manifest


ALLOWED_PATCHLET_STATUSES = {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}
FAILED_PATCHLET_STATUSES = {"FAILED_WITH_EVIDENCE", "BLOCKED_WITH_EVIDENCE", "BLOCKED_BY_FAILED_DEPENDENCY"}


def _load_transaction_groups(ctx: TargetRepoContext) -> dict:
    if not ctx.paths.transaction_groups.exists():
        raise FileNotFoundError(f"Missing transaction groups: {ctx.paths.transaction_groups}")
    return read_json(ctx.paths.transaction_groups)


def _save_transaction_groups(ctx: TargetRepoContext, groups: dict) -> None:
    write_json(ctx.paths.transaction_groups, groups)


def _group_output_dir(ctx: TargetRepoContext, transaction_group_id: str) -> Path:
    return ctx.paths.workflow_dir / "transaction_groups" / transaction_group_id


def _latest_patchlet_run(ctx: TargetRepoContext, patchlet_id: str) -> dict | None:
    manifest = load_run_manifest(ctx)
    runs = [run for run in manifest.get("runs", []) if run.get("patchlet_id") == patchlet_id]
    return runs[-1] if runs else None


def _replacement_patchlet_ids_for_source_patchlet(
    ctx: TargetRepoContext,
    *,
    state,
    source_patchlet_id: str,
) -> list[str]:
    replacement_ids: list[str] = []
    for cycle in state.repair_cycles:
        generated_patchlet_ids = cycle.get("generated_patchlet_ids", [])
        if not generated_patchlet_ids:
            continue
        for failure_id in cycle.get("source_failure_ids", []):
            failure_path = ctx.paths.failures_dir / f"{failure_id}.json"
            if not failure_path.exists():
                continue
            failure = read_json(failure_path)
            if failure.get("source_id") == source_patchlet_id:
                for patchlet_id in generated_patchlet_ids:
                    if patchlet_id not in replacement_ids:
                        replacement_ids.append(patchlet_id)
                break
    return replacement_ids


def _record_group_failure(
    ctx: TargetRepoContext,
    *,
    transaction_group_id: str,
    source_patchlet_ids: list[str],
    invariant_ids: list[str],
    observed_failure: str,
    gate_failure_reasons: list[str],
) -> str:
    existing = sorted(ctx.paths.failures_dir.glob("F*.json"))
    failure_id = f"F{len(existing) + 1:04d}"
    record = {
        "schema_version": "1.0",
        "kind": "failure_record",
        "failure_id": failure_id,
        "source": "TRANSACTION_GROUP_VERIFICATION_FAILED",
        "source_type": "transaction_group",
        "source_id": transaction_group_id,
        "source_transaction_group_id": transaction_group_id,
        "source_patchlet_ids": source_patchlet_ids,
        "observed_failure": observed_failure,
        "gate_failure_reasons": gate_failure_reasons,
        "blocking_invariant_ids": invariant_ids,
        "evidence_ids": [],
        "graph_node_ids": [],
        "changed_paths": [],
        "suspected_scope": "inside_known_graph",
        "required_next_step": "classify",
        "created_at": now_iso(),
    }
    write_json(ctx.paths.failures_dir / f"{failure_id}.json", record)
    (ctx.paths.failures_dir / f"{failure_id}.md").write_text(
        f"# {failure_id}\n\nTransaction group {transaction_group_id} failed verification.\n\n{observed_failure}\n",
        encoding="utf-8",
    )
    return failure_id


def verify_group(ctx: TargetRepoContext, *, transaction_group_id: str) -> dict:
    groups = _load_transaction_groups(ctx)
    index = read_json(ctx.paths.patchlet_index) if ctx.paths.patchlet_index.exists() else {"patchlets": []}
    state = load_state(ctx)
    group = next(
        (item for item in groups.get("transaction_groups", []) if item.get("transaction_group_id") == transaction_group_id),
        None,
    )
    if group is None:
        raise StagePreconditionError(
            "verify-group",
            current_stage=state.stage,
            target_repo=str(ctx.root),
            detail=f"unknown transaction group {transaction_group_id}",
        )

    patchlets_by_id = {patchlet["patchlet_id"]: patchlet for patchlet in index.get("patchlets", [])}
    required_patchlets = []
    source_patchlet_ids = list(group.get("patchlet_ids", []))
    for patchlet_id in source_patchlet_ids:
        patchlet = patchlets_by_id.get(patchlet_id)
        if patchlet is None:
            required_patchlets.append(None)
            continue
        if patchlet.get("status") in FAILED_PATCHLET_STATUSES:
            replacement_ids = _replacement_patchlet_ids_for_source_patchlet(
                ctx,
                state=state,
                source_patchlet_id=patchlet_id,
            )
            if replacement_ids:
                required_patchlets.extend(patchlets_by_id.get(replacement_id) for replacement_id in replacement_ids)
                continue
        required_patchlets.append(patchlet)
    if any(patchlet is None for patchlet in required_patchlets):
        raise StagePreconditionError(
            "verify-group",
            current_stage=state.stage,
            target_repo=str(ctx.root),
            detail=f"missing patchlet manifest for {transaction_group_id}",
        )
    append_operator_event(
        ctx.root,
        event_type="transaction_group_started",
        severity="info",
        stage="TRANSACTION_GROUP_VERIFICATION",
        summary=f"Started transaction group {transaction_group_id} with {len(required_patchlets)} patchlets.",
        artifact_paths=[".codex-orchestrator/patchlets/transaction_groups.json"],
        transaction_group_id=transaction_group_id,
        next_action="Running transaction group verifier.",
        details={"patchlet_ids": source_patchlet_ids},
    )
    append_operator_event(
        ctx.root,
        event_type="verifier_no_prompt",
        severity="debug",
        stage="TRANSACTION_GROUP_VERIFICATION",
        summary=f"Transaction group {transaction_group_id} uses deterministic verifier; no Codex prompt exists.",
        artifact_paths=[".codex-orchestrator/patchlets/transaction_groups.json"],
        transaction_group_id=transaction_group_id,
        terminal_hint="No prompt is generated for this deterministic transaction group verifier.",
    )
    incomplete = [
        patchlet["patchlet_id"]
        for patchlet in required_patchlets
        if patchlet.get("status") not in ALLOWED_PATCHLET_STATUSES and patchlet.get("status") not in FAILED_PATCHLET_STATUSES
    ]
    if incomplete:
        raise StagePreconditionError(
            "verify-group",
            current_stage=state.stage,
            target_repo=str(ctx.root),
            detail=f"{transaction_group_id} requires completed patchlets before verification: {', '.join(incomplete)}",
        )

    validated_patchlet_ids: list[str] = []
    failed_patchlet_ids: list[str] = []
    validation_errors: list[str] = []
    gate_failure_reasons: list[str] = []
    matrix_rows: list[dict] = []
    for patchlet in required_patchlets:
        patchlet_id = patchlet["patchlet_id"]
        report_path = ctx.paths.reports_dir / f"{patchlet_id}.json"
        run_entry = _latest_patchlet_run(ctx, patchlet_id)
        row = {
            "patchlet_id": patchlet_id,
            "status": patchlet.get("status"),
            "report_valid": False,
            "probe_valid": False,
            "allowed_diff_valid": bool(run_entry and run_entry.get("diff_validation", {}).get("valid") is True),
            "wrapper_gate_accepted": bool(run_entry and run_entry.get("wrapper_gate_result")),
            "goal_ids": patchlet.get("master_goal_ids", []),
            "invariant_ids": patchlet.get("invariant_ids", []),
            "evidence_ids": patchlet.get("evidence_ids", []),
            "contradictions": [],
            "semantic_goal_status": "UNSUPPORTED",
            "semantic_goal_check_results": [],
            "failed_semantic_criteria": [],
        }
        goal_gate_path = None
        if run_entry and run_entry.get("goal_satisfaction_gate_result"):
            goal_gate_path = ctx.root / run_entry["goal_satisfaction_gate_result"]
        elif run_entry and run_entry.get("attempt_id"):
            candidate = ctx.paths.runs_dir / run_entry["attempt_id"] / "gates" / "goal_satisfaction_gate_result.json"
            if candidate.exists():
                goal_gate_path = candidate
        if goal_gate_path and goal_gate_path.exists():
            goal_gate = read_json(goal_gate_path)
            row["semantic_goal_status"] = goal_gate.get("overall_status")
            if goal_gate.get("semantic_goal_check_result_path"):
                row["semantic_goal_check_results"] = [goal_gate["semantic_goal_check_result_path"]]
            row["failed_semantic_criteria"] = goal_gate.get("failed_criteria", [])
            if goal_gate.get("semantic_mode") == "structured" and goal_gate.get("accepted") is not True:
                row["contradictions"].append("semantic_goal_unsatisfied")
                gate_failure_reasons.extend(str(reason) for reason in goal_gate.get("reasons", []) if reason)
        if not report_path.exists():
            failed_patchlet_ids.append(patchlet_id)
            validation_errors.append(f"missing report {report_path}")
            row["contradictions"].append("missing_report")
            matrix_rows.append(row)
            continue
        try:
            report = validate_patchlet_report_file(report_path, patchlet)
        except ReportValidationError as exc:
            failed_patchlet_ids.append(patchlet_id)
            validation_errors.append(f"{patchlet_id}: {exc}")
            row["contradictions"].append(f"report_invalid:{exc}")
            matrix_rows.append(row)
            continue
        row["report_valid"] = True
        row["probe_valid"] = True
        wrapper_gate = {}
        if run_entry and run_entry.get("wrapper_gate_result") and (ctx.root / run_entry["wrapper_gate_result"]).exists():
            wrapper_gate = read_json(ctx.root / run_entry["wrapper_gate_result"])
        row["wrapper_gate_accepted"] = bool(wrapper_gate and wrapper_gate.get("accepted") is True)
        if not row["allowed_diff_valid"]:
            row["contradictions"].append("diff_not_validated")
        if not row["wrapper_gate_accepted"]:
            row["contradictions"].append("wrapper_gate_not_accepted")
            gate_failure_reasons.extend(str(reason) for reason in wrapper_gate.get("reasons", []) if reason)
        if group.get("invariant_ids"):
            missing_invariants = [invariant_id for invariant_id in group.get("invariant_ids", []) if invariant_id not in patchlet.get("invariant_ids", [])]
            if missing_invariants:
                row["contradictions"].append(f"missing_invariants:{','.join(missing_invariants)}")
        if report["status"] not in ALLOWED_PATCHLET_STATUSES:
            failed_patchlet_ids.append(patchlet_id)
            validation_errors.append(f"{patchlet_id}: report status {report['status']} is not transaction-passable")
            row["contradictions"].append(f"report_status_not_passable:{report['status']}")
            matrix_rows.append(row)
            continue
        if row["contradictions"]:
            failed_patchlet_ids.append(patchlet_id)
            validation_errors.append(f"{patchlet_id}: contradictions present")
            matrix_rows.append(row)
            continue
        validated_patchlet_ids.append(patchlet_id)
        matrix_rows.append(row)

    output_dir = _group_output_dir(ctx, transaction_group_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    matrix_path = output_dir / "patchlet_output_matrix.json"
    gate_path = output_dir / "gates" / "group_gate_result.json"
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    matrix = {
        "schema_version": "1.0",
        "kind": "patchlet_output_matrix",
        "transaction_group_id": transaction_group_id,
        "patchlets": matrix_rows,
        "group_verdict": "FAILED" if failed_patchlet_ids else "PASSED",
    }
    write_json(matrix_path, matrix)

    if failed_patchlet_ids:
        failure_id = _record_group_failure(
            ctx,
            transaction_group_id=transaction_group_id,
            source_patchlet_ids=source_patchlet_ids,
            invariant_ids=group.get("invariant_ids", []),
            observed_failure="; ".join(validation_errors),
            gate_failure_reasons=gate_failure_reasons,
        )
        group["status"] = "FAILED"
        group["failure_ids"] = [failure_id]
        group["result"] = {
            "source_patchlet_ids": source_patchlet_ids,
            "validated_patchlet_ids": validated_patchlet_ids,
            "failed_patchlet_ids": failed_patchlet_ids,
            "verified_at": now_iso(),
            "artifact_path": str(ctx.paths.transaction_groups),
            "patchlet_output_matrix": str(matrix_path),
            "group_gate_result": str(gate_path),
        }
        write_json(gate_path, {
            "schema_version": "1.0",
            "kind": "group_gate_result",
            "transaction_group_id": transaction_group_id,
            "accepted": False,
            "matrix_path": str(matrix_path),
            "failure_ids": [failure_id],
            "reasons": validation_errors,
            "semantic_goal_status": "FAILED" if any(row.get("failed_semantic_criteria") for row in matrix_rows) else "UNSUPPORTED",
            "semantic_goal_check_results": [path for row in matrix_rows for path in row.get("semantic_goal_check_results", [])],
            "failed_semantic_criteria": [cid for row in matrix_rows for cid in row.get("failed_semantic_criteria", [])],
        })
        _save_transaction_groups(ctx, groups)
        transition(ctx, state, "FAILURE_CLASSIFICATION_REQUIRED", reason=f"{transaction_group_id} verification failed")
        append_operator_event(
            ctx.root,
            event_type="transaction_group_failed",
            severity="error",
            stage="TRANSACTION_GROUP_VERIFICATION",
            summary=f"Transaction group {transaction_group_id} failed; repair planning next.",
            artifact_paths=[
                ".codex-orchestrator/patchlets/transaction_groups.json",
                str(matrix_path.relative_to(ctx.root)),
                str(gate_path.relative_to(ctx.root)),
                f".codex-orchestrator/failures/{failure_id}.json",
            ],
            transaction_group_id=transaction_group_id,
            failure_id=failure_id,
            next_action="Classifying transaction group failure.",
            details={"failed_patchlet_ids": failed_patchlet_ids},
        )
        return {
            "transaction_group_id": transaction_group_id,
            "status": "FAILED",
            "artifact_path": str(ctx.paths.transaction_groups),
            "patchlet_output_matrix": str(matrix_path),
            "group_gate_result": str(gate_path),
            "failure_ids": [failure_id],
        }

    group["status"] = "PASSED"
    group["failure_ids"] = []
    group["result"] = {
        "source_patchlet_ids": source_patchlet_ids,
        "validated_patchlet_ids": validated_patchlet_ids,
        "failed_patchlet_ids": [],
        "verified_at": now_iso(),
        "artifact_path": str(ctx.paths.transaction_groups),
        "patchlet_output_matrix": str(matrix_path),
        "group_gate_result": str(gate_path),
    }
    write_json(gate_path, {
        "schema_version": "1.0",
        "kind": "group_gate_result",
        "transaction_group_id": transaction_group_id,
        "accepted": True,
        "matrix_path": str(matrix_path),
        "failure_ids": [],
        "reasons": [],
        "semantic_goal_status": "PASSED" if any(row.get("semantic_goal_status") == "PASSED" for row in matrix_rows) else "UNSUPPORTED",
        "semantic_goal_check_results": [path for row in matrix_rows for path in row.get("semantic_goal_check_results", [])],
        "failed_semantic_criteria": [],
    })
    _save_transaction_groups(ctx, groups)
    transition(ctx, state, "TRANSACTION_VERIFICATION_COMPLETE", reason=f"{transaction_group_id} verification passed")
    append_operator_event(
        ctx.root,
        event_type="transaction_group_passed",
        severity="success",
        stage="TRANSACTION_GROUP_VERIFICATION",
        summary=f"Transaction group {transaction_group_id} passed.",
        artifact_paths=[
            ".codex-orchestrator/patchlets/transaction_groups.json",
            str(matrix_path.relative_to(ctx.root)),
            str(gate_path.relative_to(ctx.root)),
        ],
        transaction_group_id=transaction_group_id,
        next_action="Running global verifier.",
        details={"validated_patchlet_ids": validated_patchlet_ids},
    )
    return {
        "transaction_group_id": transaction_group_id,
        "status": "PASSED",
        "artifact_path": str(ctx.paths.transaction_groups),
        "patchlet_output_matrix": str(matrix_path),
        "group_gate_result": str(gate_path),
        "failure_ids": [],
    }


def verify_all_groups(ctx: TargetRepoContext) -> list[dict]:
    groups = _load_transaction_groups(ctx)
    results = []
    for group in groups.get("transaction_groups", []):
        if group.get("status") == "PASSED":
            results.append({
                "transaction_group_id": group["transaction_group_id"],
                "status": group["status"],
                "artifact_path": str(ctx.paths.transaction_groups),
                "failure_ids": group.get("failure_ids", []),
            })
            continue
        results.append(verify_group(ctx, transaction_group_id=group["transaction_group_id"]))
    return results
