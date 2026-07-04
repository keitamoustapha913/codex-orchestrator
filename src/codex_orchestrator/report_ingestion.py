from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.operator_events import append_operator_event
from codex_orchestrator.probe_artifact_refs import normalize_probe_artifact_refs
from codex_orchestrator.report_validation_errors import errors_artifact
from codex_orchestrator.semantic_result_normalization import normalize_semantic_goal_results
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.validators.report_validator import validate_patchlet_report_structured


ALLOWED_ACCEPTANCE_STATUS_FORMS = ["pass", "pass: ...", "fail", "fail: ...", "blocked", "blocked: ..."]


def _rel(ctx: TargetRepoContext, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.relative_to(ctx.root).as_posix()
    except ValueError:
        return str(path)


def normalize_acceptance_criteria_result(value: Any) -> dict[str, Any]:
    raw = value
    if not isinstance(value, str):
        return {
            "valid": False,
            "error_code": "INVALID_ACCEPTANCE_CRITERIA_RESULT",
            "raw_value": raw,
            "allowed_forms": ALLOWED_ACCEPTANCE_STATUS_FORMS,
        }
    stripped = value.strip()
    lowered = stripped.lower()
    for status in ("pass", "fail", "blocked"):
        if lowered == status:
            return {"valid": True, "raw_value": raw, "normalized_status": status, "detail": ""}
        prefix = status + ":"
        if lowered.startswith(prefix):
            detail = stripped[len(prefix):].strip()
            return {"valid": True, "raw_value": raw, "normalized_status": status, "detail": detail}
    return {
        "valid": False,
        "error_code": "INVALID_ACCEPTANCE_CRITERIA_RESULT",
        "raw_value": raw,
        "allowed_forms": ALLOWED_ACCEPTANCE_STATUS_FORMS,
    }


def _normalize_report_acceptance_criteria(report: dict[str, Any]) -> tuple[dict[str, Any], bool, dict[str, Any] | None]:
    normalized = normalize_acceptance_criteria_result(report.get("acceptance_criteria_result"))
    if not normalized.get("valid"):
        return report, False, normalized
    raw = normalized["raw_value"]
    status = normalized["normalized_status"]
    detail = normalized.get("detail", "")
    if raw == status and not detail:
        return report, False, normalized
    canonical = dict(report)
    canonical["acceptance_criteria_result_raw"] = raw
    canonical["acceptance_criteria_result"] = status
    canonical["acceptance_criteria_result_detail"] = detail
    return canonical, True, normalized


def _normalize_deterministic_run_counts(report: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    counts = report.get("deterministic_run_counts")
    if not isinstance(counts, dict):
        return report, False
    normalized_counts: dict[str, Any] = {}
    changed = False
    for key, value in counts.items():
        if isinstance(value, str):
            normalized_counts[key] = value
            continue
        if isinstance(value, dict) and isinstance(value.get("runs"), int):
            runs = int(value["runs"])
            normalized_counts[key] = f"{runs}/{runs}"
            changed = True
            continue
        normalized_counts[key] = value
    if not changed:
        return report, False
    canonical = dict(report)
    canonical["deterministic_run_counts_raw"] = counts
    canonical["deterministic_run_counts"] = normalized_counts
    return canonical, True


def _read_workflow_json(ctx: TargetRepoContext, *parts: str) -> dict[str, Any]:
    path = ctx.paths.workflow_dir.joinpath(*parts)
    return read_json(path) if path.exists() else {}


def _semantic_error(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "field": "semantic_goal_results",
        "json_pointer": f"/semantic_goal_results/{row.get('raw_item_index', 0)}",
        "schema_path": "",
        "message": row.get("message") or row.get("error_code") or "invalid shorthand semantic result",
        "normalized_signature": row.get("error_code") or "semantic_goal_results_shorthand_rejected",
        "repair_hint": row.get("message") or "Use canonical semantic result fields or a safe current-slice shorthand claim.",
        "raw_item": row.get("raw_item"),
    }


def ingest_patchlet_report(
    ctx: TargetRepoContext,
    *,
    patchlet: dict[str, Any],
    attempt_id: str,
    report_path: Path,
) -> dict[str, Any]:
    patchlet_id = patchlet["patchlet_id"]
    gates_dir = ctx.paths.runs_dir / attempt_id / "gates"
    gates_dir.mkdir(parents=True, exist_ok=True)
    raw_report_path = ctx.paths.reports_dir / f"{patchlet_id}.raw.json"
    canonical_report_path = ctx.paths.reports_dir / f"{patchlet_id}.json"
    ingestion_path = gates_dir / "report_ingestion_result.json"
    errors_path = gates_dir / "report_validation_errors.json"
    semantic_normalization_path = gates_dir / "semantic_goal_results_normalization_result.json"
    append_operator_event(
        ctx.root,
        event_type="report_ingestion_started",
        severity="info",
        stage="PATCHLET_EXECUTION_IN_PROGRESS",
        summary=f"Report ingestion started for {patchlet_id}.",
        artifact_paths=[_rel(ctx, report_path) or ""],
        patchlet_id=patchlet_id,
        attempt_id=attempt_id,
    )
    if report_path.exists():
        if raw_report_path.resolve() != report_path.resolve():
            shutil.copyfile(report_path, raw_report_path)
        else:
            raw_report_path = report_path
    raw_report = read_json(raw_report_path)
    raw_refs = raw_report.get("probe_artifact_refs") or []
    normalization = normalize_probe_artifact_refs(raw_refs, target_repo_root=ctx.root, patchlet_id=patchlet_id)
    canonical_report: dict[str, Any] | None = None
    validation_errors: list[dict[str, Any]] = list(normalization.errors)
    accepted = False
    validation_valid = False
    if not validation_errors:
        canonical_report = dict(raw_report)
        canonical_report["probe_artifact_refs"] = normalization.normalized_refs
        canonical_report, acceptance_normalized, acceptance_normalization = _normalize_report_acceptance_criteria(canonical_report)
        canonical_report, run_counts_normalized = _normalize_deterministic_run_counts(canonical_report)
        semantic_normalization_result = None
        if isinstance(canonical_report.get("semantic_goal_results"), list):
            proof_obligations = _read_workflow_json(ctx, "proof_obligations.json")
            probe_plan = _read_workflow_json(ctx, "probe_plan.json")
            semantic_normalization_result = normalize_semantic_goal_results(
                raw_items=canonical_report.get("semantic_goal_results", []),
                patchlet_id=patchlet_id,
                work_slice_id=patchlet.get("work_slice_id") or "",
                selected_goal_item_ids=list(patchlet.get("goal_item_ids", [])),
                selected_proof_obligation_ids=list(patchlet.get("proof_obligation_ids", [])),
                proof_obligations=proof_obligations,
                probe_plan=probe_plan,
                slice_change_boundary=patchlet.get("slice_change_boundary"),
            )
            write_json(semantic_normalization_path, semantic_normalization_result)
            canonical_report["semantic_goal_results_raw"] = raw_report.get("semantic_goal_results", [])
            canonical_report["semantic_goal_results"] = semantic_normalization_result.get("canonical_results_from_worker", [])
            canonical_report["worker_semantic_claims"] = semantic_normalization_result.get("accepted_raw_claims", [])
            if semantic_normalization_result.get("accepted_raw_claims"):
                append_operator_event(
                    ctx.root,
                    event_type="semantic_goal_results_shorthand_linked",
                    severity="info",
                    stage="PATCHLET_EXECUTION_IN_PROGRESS",
                    summary=f"worker semantic claim linked for {patchlet_id}; waiting for independent proof.",
                    artifact_paths=[_rel(ctx, semantic_normalization_path) or ""],
                    patchlet_id=patchlet_id,
                    attempt_id=attempt_id,
                    details={
                        "claim_ids": [row.get("claim_id") for row in semantic_normalization_result.get("accepted_raw_claims", [])],
                        "proof_not_claimed_here": True,
                    },
                )
                append_operator_event(
                    ctx.root,
                    event_type="semantic_goal_results_pending_orchestrator_proof",
                    severity="info",
                    stage="PATCHLET_EXECUTION_IN_PROGRESS",
                    summary=f"worker semantic claim for {patchlet_id} is pending orchestrator proof.",
                    artifact_paths=[_rel(ctx, semantic_normalization_path) or ""],
                    patchlet_id=patchlet_id,
                    attempt_id=attempt_id,
                )
            if semantic_normalization_result.get("rejected_raw_claims"):
                append_operator_event(
                    ctx.root,
                    event_type="semantic_goal_results_shorthand_rejected",
                    severity="error",
                    stage="PATCHLET_EXECUTION_IN_PROGRESS",
                    summary=f"worker semantic shorthand rejected for {patchlet_id}.",
                    artifact_paths=[_rel(ctx, semantic_normalization_path) or ""],
                    patchlet_id=patchlet_id,
                    attempt_id=attempt_id,
                    details={"rejected_raw_claims": semantic_normalization_result.get("rejected_raw_claims", [])},
                )
                validation_errors = [_semantic_error(row) for row in semantic_normalization_result.get("rejected_raw_claims", [])]
        else:
            semantic_normalization_result = None
        if not validation_errors:
            write_json(canonical_report_path, canonical_report)
            validation_result = validate_patchlet_report_structured(canonical_report, patchlet, repo_root=ctx.root)
            validation_valid = validation_result["valid"]
            validation_errors = validation_result["errors"]
            accepted = validation_valid
        else:
            write_json(canonical_report_path, canonical_report)
            validation_valid = False
            accepted = False
    else:
        acceptance_normalized = False
        acceptance_normalization = None
        run_counts_normalized = False
        semantic_normalization_result = None
    normalized_signature = validation_errors[0].get("normalized_signature") if validation_errors else None
    write_json(
        errors_path,
        errors_artifact(
            attempt_id=attempt_id,
            patchlet_id=patchlet_id,
            report_path=_rel(ctx, raw_report_path),
            canonical_report_path=_rel(ctx, canonical_report_path) if canonical_report_path.exists() else None,
            valid=validation_valid,
            errors=validation_errors,
        ),
    )
    result = {
        "schema_version": "1.0",
        "kind": "report_ingestion_result",
        "accepted": accepted,
        "attempt_id": attempt_id,
        "patchlet_id": patchlet_id,
        "raw_report_path": _rel(ctx, raw_report_path),
        "canonical_report_path": _rel(ctx, canonical_report_path) if accepted else None,
        "normalization_applied": normalization.normalization_applied or acceptance_normalized,
        "normalization_kinds": (
            (["probe_artifact_refs_string_paths_to_objects"] if normalization.normalization_applied else [])
            + (["acceptance_criteria_result_status_prefix"] if acceptance_normalized else [])
            + (["deterministic_run_counts_objects_to_strings"] if run_counts_normalized else [])
            + (["semantic_goal_results_shorthand_to_worker_claims"] if semantic_normalization_result and semantic_normalization_result.get("accepted_raw_claims") else [])
        ),
        "acceptance_criteria_result_normalization": acceptance_normalization,
        "raw_probe_artifact_refs": normalization.raw_string_refs,
        "canonical_probe_artifact_refs": canonical_report.get("probe_artifact_refs", []) if canonical_report else [],
        "semantic_goal_results_normalization_result_path": _rel(ctx, semantic_normalization_path) if semantic_normalization_result else None,
        "worker_semantic_claim_count": len((semantic_normalization_result or {}).get("accepted_raw_claims", [])),
        "validation": {
            "valid": validation_valid,
            "error_count": len(validation_errors),
            "errors_path": _rel(ctx, errors_path),
        },
        "normalized_failure_signature": normalized_signature,
        "repair_hint": validation_errors[0].get("repair_hint") if validation_errors else None,
        "operator_summary": (
            f"Normalized {len(normalization.raw_string_refs)} probe artifact path refs for {patchlet_id}."
            if normalization.normalization_applied
            else (f"Rejected report for {patchlet_id}: {normalized_signature}." if not accepted else f"Report ingestion passed for {patchlet_id}.")
        ),
    }
    write_json(ingestion_path, result)
    if normalization.normalization_applied:
        append_operator_event(
            ctx.root,
            event_type="report_ingestion_normalized",
            severity="info",
            stage="PATCHLET_EXECUTION_IN_PROGRESS",
            summary=f"report ingestion {patchlet_id} normalized {len(normalization.raw_string_refs)} probe artifact path refs.",
            artifact_paths=[_rel(ctx, ingestion_path) or "", _rel(ctx, raw_report_path) or "", _rel(ctx, canonical_report_path) or ""],
            patchlet_id=patchlet_id,
            attempt_id=attempt_id,
            details={"normalization_kinds": result["normalization_kinds"], "normalization_applied": True},
        )
    if acceptance_normalized:
        append_operator_event(
            ctx.root,
            event_type="report_ingestion_normalized_status",
            severity="info",
            stage="PATCHLET_EXECUTION_IN_PROGRESS",
            summary=f"report ingestion {patchlet_id} normalized acceptance_criteria_result prefix.",
            artifact_paths=[_rel(ctx, ingestion_path) or "", _rel(ctx, raw_report_path) or "", _rel(ctx, canonical_report_path) or ""],
            patchlet_id=patchlet_id,
            attempt_id=attempt_id,
            details={"normalization": acceptance_normalization},
        )
    if run_counts_normalized:
        append_operator_event(
            ctx.root,
            event_type="report_ingestion_normalized_run_counts",
            severity="info",
            stage="PATCHLET_EXECUTION_IN_PROGRESS",
            summary=f"report ingestion {patchlet_id} normalized deterministic_run_counts objects.",
            artifact_paths=[_rel(ctx, ingestion_path) or "", _rel(ctx, raw_report_path) or "", _rel(ctx, canonical_report_path) or ""],
            patchlet_id=patchlet_id,
            attempt_id=attempt_id,
            details={"normalization_kind": "deterministic_run_counts_objects_to_strings"},
        )
    append_operator_event(
        ctx.root,
        event_type="report_ingestion_passed" if accepted else "report_ingestion_failed",
        severity="success" if accepted else "error",
        stage="PATCHLET_EXECUTION_IN_PROGRESS",
        summary=result["operator_summary"],
        artifact_paths=[_rel(ctx, ingestion_path) or "", _rel(ctx, errors_path) or ""],
        patchlet_id=patchlet_id,
        attempt_id=attempt_id,
        details={
            "accepted": accepted,
            "normalization_applied": result["normalization_applied"],
            "failure_signature": normalized_signature,
            "report_ingestion_result_path": _rel(ctx, ingestion_path),
            "report_validation_errors_path": _rel(ctx, errors_path),
        },
    )
    return result
