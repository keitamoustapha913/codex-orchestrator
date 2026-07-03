from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.operator_events import append_operator_event
from codex_orchestrator.probe_artifact_refs import normalize_probe_artifact_refs
from codex_orchestrator.report_validation_errors import errors_artifact
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.validators.report_validator import validate_patchlet_report_structured


def _rel(ctx: TargetRepoContext, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.relative_to(ctx.root).as_posix()
    except ValueError:
        return str(path)


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
        write_json(canonical_report_path, canonical_report)
        validation_result = validate_patchlet_report_structured(canonical_report, patchlet, repo_root=ctx.root)
        validation_valid = validation_result["valid"]
        validation_errors = validation_result["errors"]
        accepted = validation_valid
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
        "normalization_applied": normalization.normalization_applied,
        "normalization_kinds": ["probe_artifact_refs_string_paths_to_objects"] if normalization.normalization_applied else [],
        "raw_probe_artifact_refs": normalization.raw_string_refs,
        "canonical_probe_artifact_refs": canonical_report.get("probe_artifact_refs", []) if canonical_report else [],
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
