from __future__ import annotations

import shutil
import hashlib
from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.operator_events import append_operator_event
from codex_orchestrator.probe_artifact_refs import normalize_probe_artifact_refs
from codex_orchestrator.report_validation_errors import (
    errors_artifact,
    report_validation_error_detail,
)
from codex_orchestrator.report_contract import (
    DERIVED_CANONICAL_REPORT_FIELD_METADATA,
    RawReportError,
    classify_fields,
    contract_fingerprint,
    parse_raw_report,
)
from codex_orchestrator.report_reorganization import launch_report_reorganization_worker
from codex_orchestrator.semantic_result_normalization import normalize_semantic_goal_results
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.validators.report_validator import validate_patchlet_report_structured


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _raw_report_error(exc: RawReportError) -> dict[str, Any]:
    # Preserve the established downstream probe-path signature while retaining
    # the new envelope failure code as the authoritative raw-boundary code.
    signature = "probe_artifact_refs_unsafe_path" if "probe_artifact_refs" in str(exc) else exc.code
    return {
        "field": "raw_worker_report",
        "json_pointer": "",
        "schema_path": "",
        "message": str(exc),
        "normalized_signature": signature,
        "raw_envelope_failure_code": exc.code,
        "repair_hint": "Produce a bounded UTF-8 JSON object without unsafe references.",
    }


def _rel(ctx: TargetRepoContext, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.relative_to(ctx.root).as_posix()
    except ValueError:
        return str(path)


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


def _normalize_probe_commands(
    report: dict[str, Any],
    *,
    patchlet_id: str,
    attempt_id: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    commands = report.get("probe_commands")
    if not isinstance(commands, list):
        return report, None

    canonical_commands: list[Any] = []
    raw_items: list[dict[str, Any]] = []
    rejected_items: list[dict[str, Any]] = []
    changed = False

    for index, item in enumerate(commands):
        if isinstance(item, str):
            canonical_commands.append(item)
            continue
        if isinstance(item, dict):
            command = item.get("command")
            if isinstance(command, str) and command.strip():
                normalized_command = command.strip()
                canonical_commands.append(normalized_command)
                raw_items.append(
                    {
                        "raw_item_index": index,
                        "raw_item": item,
                        "normalized_command": normalized_command,
                        "accepted": True,
                    }
                )
                changed = True
                continue
            canonical_commands.append(item)
            rejected_items.append(
                {
                    "raw_item_index": index,
                    "raw_item": item,
                    "accepted": False,
                    "reason": "missing_or_empty_command",
                }
            )
            continue
        canonical_commands.append(item)

    if not changed and not rejected_items:
        return report, None

    canonical = dict(report)
    canonical["probe_commands"] = canonical_commands
    result = {
        "schema_version": "1.0",
        "kind": "probe_commands_normalization_result",
        "patchlet_id": patchlet_id,
        "attempt_id": attempt_id,
        "accepted": not rejected_items,
        "canonical_probe_commands": [item for item in canonical_commands if isinstance(item, str)],
        "raw_probe_command_items": raw_items,
        "rejected_probe_command_items": rejected_items,
    }
    return canonical, result


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


def _report_identity_error(code: str, message: str) -> dict[str, Any]:
    version_error = code == "WORKER_REPORT_UNSUPPORTED_SCHEMA_VERSION"
    return report_validation_error_detail(
        field="schema_version" if version_error else "kind",
        json_pointer="/schema_version" if version_error else "/kind",
        message=message,
        normalized_signature=code,
        repair_hint='Emit schema_version="2.0" and kind="worker_patchlet_report".',
    )


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
    probe_artifact_refs_normalization_path = gates_dir / "probe_artifact_refs_normalization_result.json"
    semantic_normalization_path = gates_dir / "semantic_goal_results_normalization_result.json"
    probe_commands_normalization_path = gates_dir / "probe_commands_normalization_result.json"
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
    try:
        envelope = parse_raw_report(raw_report_path)
    except RawReportError as exc:
        error = _raw_report_error(exc)
        write_json(errors_path, errors_artifact(
            attempt_id=attempt_id, patchlet_id=patchlet_id,
            report_path=_rel(ctx, raw_report_path), canonical_report_path=None,
            valid=False, errors=[error],
        ))
        result = {
            "schema_version": "1.0", "kind": "report_ingestion_result", "accepted": False,
            "attempt_id": attempt_id, "patchlet_id": patchlet_id,
            "raw_report_path": _rel(ctx, raw_report_path), "canonical_report_path": None,
            "raw_report_sha256": _sha256(raw_report_path),
            "contract_fingerprint": contract_fingerprint(),
            "raw_report_byte_size": raw_report_path.stat().st_size,
            "raw_envelope": {"parseable": False, "failure_code": exc.code, "contract_fingerprint": contract_fingerprint()},
            "normalization_applied": False, "normalization_kinds": [],
            "raw_probe_artifact_refs": [], "canonical_probe_artifact_refs": [],
            "validation": {"valid": False, "error_count": 1, "errors_path": _rel(ctx, errors_path)},
            "normalized_failure_signature": error["normalized_signature"],
            "raw_envelope_failure_code": exc.code, "operator_summary": str(exc),
        }
        write_json(ingestion_path, result)
        append_operator_event(ctx.root, event_type="report_ingestion_failed", severity="error",
            stage="PATCHLET_EXECUTION_IN_PROGRESS", summary=f"{error['normalized_signature']}: {exc}",
            artifact_paths=[_rel(ctx, raw_report_path) or "", _rel(ctx, errors_path) or ""],
            patchlet_id=patchlet_id, attempt_id=attempt_id,
            details={"failure_signature": error["normalized_signature"], "raw_envelope_failure_code": exc.code})
        return result
    raw_report = envelope.value
    identity_error = None
    if raw_report.get("schema_version") != "2.0":
        identity_error = _report_identity_error(
            "WORKER_REPORT_UNSUPPORTED_SCHEMA_VERSION",
            f"Unsupported worker report schema_version: {raw_report.get('schema_version')!r}",
        )
    elif raw_report.get("kind") != "worker_patchlet_report":
        identity_error = _report_identity_error(
            "WORKER_REPORT_INVALID_KIND",
            f"Invalid WorkerPatchletReportV2 kind: {raw_report.get('kind')!r}",
        )
    if identity_error is not None:
        write_json(
            errors_path,
            errors_artifact(
                attempt_id=attempt_id,
                patchlet_id=patchlet_id,
                report_path=_rel(ctx, raw_report_path),
                canonical_report_path=None,
                valid=False,
                errors=[identity_error],
            ),
        )
        failure_code = identity_error["normalized_signature"]
        result = {
            "schema_version": "1.0",
            "kind": "report_ingestion_result",
            "accepted": False,
            "attempt_id": attempt_id,
            "patchlet_id": patchlet_id,
            "raw_report_path": _rel(ctx, raw_report_path),
            "canonical_report_path": None,
            "raw_report_sha256": envelope.sha256,
            "contract_fingerprint": contract_fingerprint(),
            "raw_report_byte_size": envelope.byte_size,
            "raw_envelope": {
                "parseable": True,
                "utf8_valid": True,
                "json_object": True,
                "contract_fingerprint": contract_fingerprint(),
                "top_level_field_count": envelope.top_level_field_count,
                "maximum_nesting_depth": envelope.max_depth,
            },
            "unknown_fields": [],
            "unknown_field_status": "NONE",
            "report_reorganization_used": False,
            "report_reorganization_result": "NOT_REQUIRED",
            "normalization_applied": False,
            "normalization_kinds": [],
            "raw_probe_artifact_refs": [],
            "canonical_probe_artifact_refs": [],
            "probe_artifact_refs_normalization_result_path": None,
            "semantic_goal_results_normalization_result_path": None,
            "probe_commands_normalization_result_path": None,
            "worker_semantic_claim_count": 0,
            "worker_semantic_warning_count": 0,
            "validation": {
                "valid": False,
                "error_count": 1,
                "errors_path": _rel(ctx, errors_path),
            },
            "normalized_failure_signature": failure_code,
            "repair_hint": identity_error["repair_hint"],
            "operator_summary": identity_error["message"],
        }
        write_json(ingestion_path, result)
        append_operator_event(
            ctx.root,
            event_type="report_ingestion_failed",
            severity="error",
            stage="PATCHLET_EXECUTION_IN_PROGRESS",
            summary=identity_error["message"],
            artifact_paths=[
                _rel(ctx, raw_report_path) or "",
                _rel(ctx, errors_path) or "",
                _rel(ctx, ingestion_path) or "",
            ],
            patchlet_id=patchlet_id,
            attempt_id=attempt_id,
            details={"failure_signature": failure_code},
        )
        return result
    known_fields, unknown_fields = classify_fields(raw_report)
    reorganization_result = None
    reorganization_used = bool(unknown_fields)
    if reorganization_used:
        reorganization_dir = gates_dir / "report_reorganization_worker"
        append_operator_event(ctx.root, event_type="report_reorganization_started", severity="info",
            stage="PATCHLET_EXECUTION_IN_PROGRESS", summary=f"Report reorganization started for {patchlet_id}.",
            artifact_paths=[_rel(ctx, raw_report_path) or ""], patchlet_id=patchlet_id, attempt_id=attempt_id)
        reorganization_result = launch_report_reorganization_worker(raw_report_path,
            source_report_sha256=envelope.sha256, patchlet_id=patchlet_id, attempt_id=attempt_id,
            output_dir=reorganization_dir)
        if not reorganization_result.get("accepted"):
            append_operator_event(ctx.root, event_type="report_reorganization_failed", severity="error",
                stage="PATCHLET_EXECUTION_IN_PROGRESS", summary=f"Report reorganization failed for {patchlet_id}.",
                artifact_paths=[_rel(ctx, reorganization_dir / "report_reorganization_candidate.json") or ""],
                patchlet_id=patchlet_id, attempt_id=attempt_id,
                details={"failure_code": reorganization_result.get("failure_code"), "errors": reorganization_result.get("errors", [])})
        else:
            append_operator_event(ctx.root, event_type="report_reorganization_completed", severity="info",
                stage="PATCHLET_EXECUTION_IN_PROGRESS", summary=f"Report reorganization completed for {patchlet_id}.",
                artifact_paths=[_rel(ctx, reorganization_dir / name) or "" for name in (
                    "report_reorganization_candidate.json", "report_reorganization_trace.json", "report_reorganization_worker_result.json")],
                patchlet_id=patchlet_id, attempt_id=attempt_id,
                details={"unknown_field_count": len(unknown_fields), "non_authoritative": True})
    raw_refs = raw_report.get("probe_artifact_refs") or []
    evidence_inventory_path = gates_dir / "worker_evidence_inventory.json"
    evidence_preservation_path = gates_dir / "worker_evidence_preservation_result.json"
    evidence_inventory = read_json(evidence_inventory_path) if evidence_inventory_path.exists() else None
    evidence_preservation = read_json(evidence_preservation_path) if evidence_preservation_path.exists() else None
    normalization = normalize_probe_artifact_refs(
        raw_refs,
        target_repo_root=ctx.root,
        patchlet_id=patchlet_id,
        evidence_inventory=evidence_inventory,
        evidence_preservation=evidence_preservation,
    )
    probe_artifact_refs_normalization_result = {
        "schema_version": "1.0",
        "kind": "probe_artifact_refs_normalization_result",
        "patchlet_id": patchlet_id,
        "attempt_id": attempt_id,
        "accepted": not normalization.errors,
        "canonical_refs": normalization.normalized_refs,
        "raw_string_refs": normalization.raw_string_refs,
        "raw_object_refs": normalization.raw_object_refs,
        "rejected_refs": normalization.rejected_refs,
        "warnings": normalization.warnings,
    }
    write_json(probe_artifact_refs_normalization_path, probe_artifact_refs_normalization_result)
    canonical_report: dict[str, Any] | None = None
    validation_errors: list[dict[str, Any]] = list(normalization.errors)
    accepted = False
    validation_valid = False
    if not validation_errors:
        canonical_report = dict(raw_report)
        for field_name in DERIVED_CANONICAL_REPORT_FIELD_METADATA:
            canonical_report.pop(field_name, None)
        canonical_report["probe_artifact_refs"] = normalization.normalized_refs
        canonical_report, run_counts_normalized = _normalize_deterministic_run_counts(canonical_report)
        canonical_report, probe_commands_normalization_result = _normalize_probe_commands(
            canonical_report,
            patchlet_id=patchlet_id,
            attempt_id=attempt_id,
        )
        if probe_commands_normalization_result is not None:
            write_json(probe_commands_normalization_path, probe_commands_normalization_result)
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
                allowed_product_runtime_file=patchlet.get("allowed_product_runtime_file"),
            )
            write_json(semantic_normalization_path, semantic_normalization_result)
            boundary_evidence_path = gates_dir / "boundary_evidence_match_result.json"
            write_json(
                boundary_evidence_path,
                {
                    "schema_version": "1.0",
                    "kind": "boundary_evidence_match_result",
                    "patchlet_id": patchlet_id,
                    "work_slice_id": patchlet.get("work_slice_id") or "",
                    "accepted": semantic_normalization_result.get("accepted"),
                    "matches": semantic_normalization_result.get("boundary_evidence_matches", []),
                },
            )
            canonical_report["semantic_goal_results_raw"] = raw_report.get("semantic_goal_results", [])
            canonical_report["semantic_goal_results"] = semantic_normalization_result.get("canonical_results_from_worker", [])
            canonical_report["worker_semantic_claims"] = semantic_normalization_result.get("accepted_raw_claims", [])
            canonical_report["worker_semantic_quality_warnings"] = semantic_normalization_result.get("semantic_quality_warnings", [])
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
            if semantic_normalization_result.get("semantic_quality_warnings"):
                append_operator_event(
                    ctx.root,
                    event_type="worker_report_semantic_warning",
                    severity="warning",
                    stage="PATCHLET_EXECUTION_IN_PROGRESS",
                    summary=f"worker semantic prose warning recorded for {patchlet_id}.",
                    artifact_paths=[_rel(ctx, semantic_normalization_path) or ""],
                    patchlet_id=patchlet_id,
                    attempt_id=attempt_id,
                    details={"warnings": semantic_normalization_result.get("semantic_quality_warnings", [])},
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
        run_counts_normalized = False
        probe_commands_normalization_result = None
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
        "raw_report_sha256": envelope.sha256,
        "contract_fingerprint": contract_fingerprint(),
        "raw_report_byte_size": envelope.byte_size,
        "raw_envelope": {
            "parseable": True, "utf8_valid": True, "json_object": True,
            "contract_fingerprint": contract_fingerprint(),
            "top_level_field_count": envelope.top_level_field_count,
            "maximum_nesting_depth": envelope.max_depth,
        },
        "unknown_fields": [row["field_name"] for row in unknown_fields],
        "unknown_field_status": "WARNING" if unknown_fields else "NONE",
        "report_reorganization_used": reorganization_used,
        "report_reorganization_result": ("ACCEPTED" if reorganization_result and reorganization_result.get("accepted") else "FAILED") if reorganization_result else "NOT_REQUIRED",
        "canonical_report_path": _rel(ctx, canonical_report_path) if accepted else None,
        "normalization_applied": normalization.normalization_applied or bool(probe_commands_normalization_result),
        "normalization_kinds": (
            (["probe_artifact_refs_string_paths_to_objects"] if normalization.raw_string_refs and normalization.normalization_applied else [])
            + (["probe_artifact_refs_object_metadata_from_actual_files"] if normalization.raw_object_refs and normalization.normalization_applied else [])
            + (["deterministic_run_counts_objects_to_strings"] if run_counts_normalized else [])
            + (["probe_commands_objects_to_strings"] if probe_commands_normalization_result and probe_commands_normalization_result.get("raw_probe_command_items") else [])
            + (["semantic_goal_results_shorthand_to_worker_claims"] if semantic_normalization_result and semantic_normalization_result.get("accepted_raw_claims") else [])
            + (["worker_report_semantic_quality_warnings"] if semantic_normalization_result and semantic_normalization_result.get("semantic_quality_warnings") else [])
        ),
        "raw_probe_artifact_refs": normalization.raw_string_refs,
        "canonical_probe_artifact_refs": canonical_report.get("probe_artifact_refs", []) if canonical_report else [],
        "probe_artifact_ref_warning_count": len(normalization.warnings),
        "probe_artifact_refs_normalization_result_path": _rel(ctx, probe_artifact_refs_normalization_path),
        "semantic_goal_results_normalization_result_path": _rel(ctx, semantic_normalization_path) if semantic_normalization_result else None,
        "probe_commands_normalization_result_path": _rel(ctx, probe_commands_normalization_path) if probe_commands_normalization_result else None,
        "worker_semantic_claim_count": len((semantic_normalization_result or {}).get("accepted_raw_claims", [])),
        "worker_semantic_warning_count": len((semantic_normalization_result or {}).get("semantic_quality_warnings", [])),
        "validation": {
            "valid": validation_valid,
            "error_count": len(validation_errors),
            "errors_path": _rel(ctx, errors_path),
        },
        "normalized_failure_signature": normalized_signature,
        "repair_hint": validation_errors[0].get("repair_hint") if validation_errors else None,
        "operator_summary": (
            f"Normalized probe artifact refs for {patchlet_id}."
            if normalization.normalization_applied
            else (f"Rejected report for {patchlet_id}: {normalized_signature}." if not accepted else f"Report ingestion passed for {patchlet_id}.")
        ),
    }
    write_json(ingestion_path, result)
    if unknown_fields:
        append_operator_event(ctx.root, event_type="report_reorganization_warning", severity="warning",
            stage="PATCHLET_EXECUTION_IN_PROGRESS", summary=f"Unknown worker report fields recorded for {patchlet_id}.",
            artifact_paths=[_rel(ctx, ingestion_path) or ""], patchlet_id=patchlet_id, attempt_id=attempt_id,
            details={"unknown_fields": [row["field_name"] for row in unknown_fields], "blocking": False})
    if normalization.normalization_applied:
        append_operator_event(
            ctx.root,
            event_type="report_ingestion_normalized",
            severity="info",
            stage="PATCHLET_EXECUTION_IN_PROGRESS",
            summary=f"report ingestion {patchlet_id} normalized probe artifact refs.",
            artifact_paths=[_rel(ctx, ingestion_path) or "", _rel(ctx, probe_artifact_refs_normalization_path) or "", _rel(ctx, raw_report_path) or "", _rel(ctx, canonical_report_path) or ""],
            patchlet_id=patchlet_id,
            attempt_id=attempt_id,
            details={"normalization_kinds": result["normalization_kinds"], "normalization_applied": True},
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
    if probe_commands_normalization_result and probe_commands_normalization_result.get("raw_probe_command_items"):
        append_operator_event(
            ctx.root,
            event_type="probe_commands_normalized",
            severity="info",
            stage="PATCHLET_EXECUTION_IN_PROGRESS",
            summary=f"report ingestion {patchlet_id} normalized object-shaped probe_commands.",
            artifact_paths=[_rel(ctx, probe_commands_normalization_path) or ""],
            patchlet_id=patchlet_id,
            attempt_id=attempt_id,
            details={
                "normalization_kind": "probe_commands_objects_to_strings",
                "normalized_count": len(probe_commands_normalization_result.get("raw_probe_command_items", [])),
            },
        )
    if probe_commands_normalization_result and probe_commands_normalization_result.get("rejected_probe_command_items"):
        append_operator_event(
            ctx.root,
            event_type="probe_commands_rejected",
            severity="error",
            stage="PATCHLET_EXECUTION_IN_PROGRESS",
            summary=f"report ingestion {patchlet_id} rejected malformed object-shaped probe_commands.",
            artifact_paths=[_rel(ctx, probe_commands_normalization_path) or ""],
            patchlet_id=patchlet_id,
            attempt_id=attempt_id,
            details={"rejected_probe_command_items": probe_commands_normalization_result.get("rejected_probe_command_items", [])},
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
