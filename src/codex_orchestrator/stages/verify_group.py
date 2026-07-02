from __future__ import annotations

from codex_orchestrator.errors import StagePreconditionError
from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.state import load_state, now_iso, transition
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.validators.report_validator import ReportValidationError, validate_patchlet_report_file


ALLOWED_PATCHLET_STATUSES = {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}
FAILED_PATCHLET_STATUSES = {"FAILED_WITH_EVIDENCE", "BLOCKED_WITH_EVIDENCE"}


def _load_transaction_groups(ctx: TargetRepoContext) -> dict:
    if not ctx.paths.transaction_groups.exists():
        raise FileNotFoundError(f"Missing transaction groups: {ctx.paths.transaction_groups}")
    return read_json(ctx.paths.transaction_groups)


def _save_transaction_groups(ctx: TargetRepoContext, groups: dict) -> None:
    write_json(ctx.paths.transaction_groups, groups)


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


def _record_group_failure(ctx: TargetRepoContext, *, transaction_group_id: str, invariant_ids: list[str], observed_failure: str) -> str:
    existing = sorted(ctx.paths.failures_dir.glob("F*.json"))
    failure_id = f"F{len(existing) + 1:04d}"
    record = {
        "schema_version": "1.0",
        "kind": "failure_record",
        "failure_id": failure_id,
        "source": "TRANSACTION_GROUP_VERIFICATION_FAILED",
        "source_id": transaction_group_id,
        "observed_failure": observed_failure,
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
    for patchlet in required_patchlets:
        patchlet_id = patchlet["patchlet_id"]
        report_path = ctx.paths.reports_dir / f"{patchlet_id}.json"
        if not report_path.exists():
            failed_patchlet_ids.append(patchlet_id)
            validation_errors.append(f"missing report {report_path}")
            continue
        try:
            report = validate_patchlet_report_file(report_path, patchlet)
        except ReportValidationError as exc:
            failed_patchlet_ids.append(patchlet_id)
            validation_errors.append(f"{patchlet_id}: {exc}")
            continue
        if report["status"] not in ALLOWED_PATCHLET_STATUSES:
            failed_patchlet_ids.append(patchlet_id)
            validation_errors.append(f"{patchlet_id}: report status {report['status']} is not transaction-passable")
            continue
        validated_patchlet_ids.append(patchlet_id)

    if failed_patchlet_ids:
        failure_id = _record_group_failure(
            ctx,
            transaction_group_id=transaction_group_id,
            invariant_ids=group.get("invariant_ids", []),
            observed_failure="; ".join(validation_errors),
        )
        group["status"] = "FAILED"
        group["failure_ids"] = [failure_id]
        group["result"] = {
            "source_patchlet_ids": source_patchlet_ids,
            "validated_patchlet_ids": validated_patchlet_ids,
            "failed_patchlet_ids": failed_patchlet_ids,
            "verified_at": now_iso(),
            "artifact_path": str(ctx.paths.transaction_groups),
        }
        _save_transaction_groups(ctx, groups)
        transition(ctx, state, "FAILURE_CLASSIFICATION_REQUIRED", reason=f"{transaction_group_id} verification failed")
        return {
            "transaction_group_id": transaction_group_id,
            "status": "FAILED",
            "artifact_path": str(ctx.paths.transaction_groups),
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
    }
    _save_transaction_groups(ctx, groups)
    transition(ctx, state, "TRANSACTION_VERIFICATION_COMPLETE", reason=f"{transaction_group_id} verification passed")
    return {
        "transaction_group_id": transaction_group_id,
        "status": "PASSED",
        "artifact_path": str(ctx.paths.transaction_groups),
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
