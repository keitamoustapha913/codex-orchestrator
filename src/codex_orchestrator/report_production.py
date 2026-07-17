"""Constrained production of WorkerPatchletReportV2 from a task handoff.

The report-production worker is deliberately non-authoritative.  It receives
copies of bounded diagnostic inputs, writes to a closed disposable output
directory, and cannot decide proof, coverage, semantic acceptance, or
promotion.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any

from .jsonio import write_json
from .probe_artifact_refs import normalize_probe_artifact_refs
from .report_contract import (
    RawReportError,
    classify_fields,
    contract_fingerprint,
    parse_raw_report,
    render_primary_worker_report_template,
)
from .semantic_result_normalization import normalize_semantic_goal_results
from .validators.report_validator import validate_patchlet_report_structured
from .validators.schema_validator import iter_jsonschema_errors


REPORT_FILENAME = "worker_patchlet_report_v2.json"
TRACE_FILENAME = "report_production_trace.json"
RESULT_FILENAME = "report_production_worker_result.json"
WORKER_ALLOWED_OUTPUTS = frozenset({REPORT_FILENAME})
REPORT_PRODUCTION_MAX_ATTEMPTS = 1
TASK_HANDOFF_MAX_BYTES = 2 * 1024 * 1024
TASK_HANDOFF_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "patchlet_id",
        "status",
        "probe_commands",
        "deterministic_run_counts",
        "root_cause_classification",
        "before_after_state",
        "row_ledger",
        "trace_ledger",
        "cleanup_proof",
        "semantic_goal_results",
    }
)

_TASK_HANDOFF_REPORT_FIELDS = frozenset(
    {
        "probe_commands",
        "deterministic_run_counts",
        "root_cause_classification",
        "before_after_state",
        "row_ledger",
        "trace_ledger",
        "cleanup_proof",
        "semantic_goal_results",
        "blocking_boundary_reason",
        "failed_probe_evidence",
    }
)

_FORBIDDEN_GOAL_ITEM_ALIASES = frozenset({"goal_item", "goal", "goal_id"})
_UNSAFE_DIAGNOSTIC_REFERENCE = re.compile(r"(?:^|[\s=:'\"])(?:/|~/|\.\.(?:/|\\)|file://)")

_ORCHESTRATOR_OWNED_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "patchlet_id",
        "changed_product_runtime_file",
        "changed_artifact_files",
        "probe_artifact_refs",
    }
)

_REQUIRED_COMPLETE_ROOT_CAUSE_FIELDS = (
    "observed_failure",
    "immediate_cause",
    "why_immediate_cause_happened",
    "deeper_owner_boundary",
    "producer_transformer_consumer_boundary",
    "not_downstream_of_unprobed_state_proof",
    "negative_control_proof",
    "recursive_why_audit",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _nonempty_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _unsafe_diagnostic_reference(value: Any) -> bool:
    if isinstance(value, str):
        return bool(_UNSAFE_DIAGNOSTIC_REFERENCE.search(value))
    if isinstance(value, list):
        return any(_unsafe_diagnostic_reference(item) for item in value)
    if isinstance(value, dict):
        return any(_unsafe_diagnostic_reference(item) for item in value.values())
    return False


def validate_task_completion_handoff(
    path: Path,
    *,
    patchlet_id: str,
    goal_item_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    raw = path.read_bytes()
    if len(raw) > TASK_HANDOFF_MAX_BYTES:
        return [{"code": "TASK_COMPLETION_HANDOFF_SIZE_LIMIT_EXCEEDED"}]
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return [{"code": "TASK_COMPLETION_HANDOFF_INVALID_JSON"}]
    if not isinstance(value, dict):
        return [{"code": "TASK_COMPLETION_HANDOFF_NOT_OBJECT"}]
    if value.get("schema_version") != "1.0" or value.get("kind") != "task_worker_completion_handoff":
        errors.append({"code": "TASK_COMPLETION_HANDOFF_INVALID_IDENTITY"})
    if value.get("patchlet_id") != patchlet_id:
        errors.append({"code": "TASK_COMPLETION_HANDOFF_PATCHLET_MISMATCH"})
    missing = sorted(TASK_HANDOFF_REQUIRED_FIELDS - set(value))
    if missing:
        errors.append({"code": "TASK_COMPLETION_HANDOFF_MISSING_FIELDS", "fields": missing})
    if value.get("status") not in {
        "COMPLETE",
        "VERIFIED_NO_CHANGE_NEEDED",
        "BLOCKED_WITH_EVIDENCE",
        "FAILED_WITH_EVIDENCE",
    }:
        errors.append({"code": "TASK_COMPLETION_HANDOFF_INVALID_STATUS"})
    semantic_items = value.get("semantic_goal_results")
    if not isinstance(semantic_items, list):
        errors.append({"code": "TASK_COMPLETION_HANDOFF_SEMANTIC_RESULTS_NOT_ARRAY"})
        return errors
    assigned_goal_item_ids = {
        item.strip() for item in (goal_item_ids or []) if isinstance(item, str) and item.strip()
    }
    for index, item in enumerate(semantic_items):
        if not isinstance(item, dict):
            errors.append(
                {
                    "code": "TASK_COMPLETION_HANDOFF_INVALID_SEMANTIC_RESULT_SHAPE",
                    "index": index,
                }
            )
            continue
        aliases = sorted(_FORBIDDEN_GOAL_ITEM_ALIASES.intersection(item))
        if aliases:
            errors.append(
                {
                    "code": "TASK_COMPLETION_HANDOFF_FORBIDDEN_GOAL_ITEM_ALIAS",
                    "index": index,
                    "fields": aliases,
                }
            )
        goal_item_id = _nonempty_text(item.get("goal_item_id"))
        if goal_item_id is None:
            errors.append(
                {
                    "code": "TASK_COMPLETION_HANDOFF_MISSING_GOAL_ITEM_ID",
                    "index": index,
                }
            )
        elif assigned_goal_item_ids and goal_item_id not in assigned_goal_item_ids:
            errors.append(
                {
                    "code": "TASK_COMPLETION_HANDOFF_UNASSIGNED_GOAL_ITEM_ID",
                    "index": index,
                    "goal_item_id": goal_item_id,
                }
            )
        result = _nonempty_text(item.get("result"))
        status = _nonempty_text(item.get("status"))
        evidence = _nonempty_text(item.get("evidence"))
        if result is None and status is None and evidence is None:
            errors.append(
                {
                    "code": "TASK_COMPLETION_HANDOFF_SEMANTIC_RESULT_NOT_ORGANIZABLE",
                    "index": index,
                }
            )
        if _unsafe_diagnostic_reference(
            {name: item.get(name) for name in ("result", "status", "evidence")}
        ):
            errors.append(
                {
                    "code": "TASK_COMPLETION_HANDOFF_UNSAFE_SEMANTIC_REFERENCE",
                    "index": index,
                }
            )
    return errors


def _captured_aliases(preservation: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in preservation.get("files", []):
        if not isinstance(item, dict) or item.get("capture_status") != "CAPTURED":
            continue
        alias = item.get("diagnostic_alias_path")
        digest = item.get("diagnostic_alias_sha256")
        if not isinstance(alias, str) or not isinstance(digest, str):
            continue
        rows.append(
            {
                "path": alias,
                "kind": PurePosixPath(alias).stem.lower().replace(" ", "_"),
                "sha256": digest,
                "size_bytes": int(item.get("size_bytes") or 0),
            }
        )
    return sorted(rows, key=lambda row: row["path"])


def _group_probe_refs(
    *,
    patchlet_id: str,
    probe_ids: list[str],
    aliases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for item in aliases:
        path = PurePosixPath(item["path"])
        if len(path.parts) < 4:
            continue
        probe_root = path.parent.as_posix()
        run_id = path.parent.name if len(path.parts) >= 5 else "default"
        group = groups.setdefault(
            (probe_root, run_id),
            {
                "patchlet_id": patchlet_id,
                "probe_root": probe_root,
                "run_id": run_id,
                "files": [],
            },
        )
        group["files"].append(item)
    if not groups:
        # A report reference is diagnostic, not proof.  Keep the required
        # report grouping without inventing a file when no evidence was
        # durably captured.
        return [
            {
                "patchlet_id": patchlet_id,
                "probe_root": f".artifacts/probes/{patchlet_id}",
                "run_id": "default",
                "files": [],
                "mapped_probe_ids": sorted(set(probe_ids)),
            }
        ]
    return [groups[key] for key in sorted(groups)]


def _first_nonempty(*values: Any) -> Any:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list) and value:
            return value
    return None


def _organize_root_cause(
    handoff: dict[str, Any],
    *,
    assigned_path: str,
    patchlet_id: str,
) -> dict[str, Any]:
    """Organize task observations into the diagnostic V2 root-cause shape.

    These values remain worker claims.  This transformation only supplies the
    formal field shape; none of the resulting prose is authoritative.
    """
    source = handoff.get("root_cause_classification")
    source = dict(source) if isinstance(source, dict) else {}
    detail = _first_nonempty(source.get("detail"), source.get("description"))
    classification = _first_nonempty(source.get("class"), source.get("classification"))
    states = handoff.get("before_after_state")
    states = states if isinstance(states, list) else []
    before = next(
        (
            row
            for row in states
            if isinstance(row, dict) and str(row.get("phase", "")).lower() == "before"
        ),
        None,
    )
    negative = next(
        (
            row
            for row in states
            if isinstance(row, dict)
            and str(row.get("phase", "")).lower() in {"negative", "negative_control"}
        ),
        None,
    )
    commands = [str(item) for item in handoff.get("probe_commands", []) if str(item).strip()]
    counts = handoff.get("deterministic_run_counts")
    counts = counts if isinstance(counts, dict) else {}

    observed = _first_nonempty(
        source.get("observed_failure"),
        detail,
        json.dumps(before, sort_keys=True) if before else None,
        f"Task worker recorded a bounded current-slice failure for {patchlet_id}.",
    )
    immediate = _first_nonempty(
        source.get("immediate_cause"),
        classification,
        detail,
        "The assigned product boundary did not satisfy the current slice.",
    )
    why = _first_nonempty(
        source.get("why_immediate_cause_happened"),
        detail,
        classification,
        "The required current-slice state was absent from the assigned product boundary.",
    )
    direct_probe = _first_nonempty(
        source.get("not_downstream_of_unprobed_state_proof"),
        f"Task worker reported direct probe command: {commands[0]}" if commands else None,
        "Task handoff records a direct probe of the assigned current-slice boundary.",
    )
    negative_control = _first_nonempty(
        source.get("negative_control_proof"),
        json.dumps(negative, sort_keys=True) if negative else None,
        (
            "Task worker reported deterministic negative-control runs: "
            + str(counts.get("negative_controls"))
            if counts.get("negative_controls")
            else None
        ),
        "Task handoff records bounded negative-control observations.",
    )
    audit = _first_nonempty(
        source.get("recursive_why_audit"),
        [str(item) for item in (detail, classification) if item],
        ["Report Production Worker organized the task worker's bounded observations."],
    )
    return {
        **source,
        "observed_failure": observed,
        "immediate_cause": immediate,
        "why_immediate_cause_happened": why,
        # The assigned path is orchestrator-owned.  Do not copy a sandbox path
        # or a peer relative path from worker prose into this formal field.
        "deeper_owner_boundary": assigned_path,
        "producer_transformer_consumer_boundary": _first_nonempty(
            source.get("producer_transformer_consumer_boundary"),
            f"{assigned_path} -> mapped independent probe",
        ),
        "not_downstream_of_unprobed_state_proof": direct_probe,
        "negative_control_proof": negative_control,
        "recursive_why_audit": audit,
    }


def _organize_semantic_goal_results(
    handoff: dict[str, Any],
    *,
    goal_item_ids: list[str],
    assigned_path: str,
    slice_change_boundary: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert bounded task observations into non-authoritative V2 shorthand."""
    raw_items = handoff.get("semantic_goal_results")
    if not isinstance(raw_items, list):
        return [], [
            {
                "warning_code": "TASK_SEMANTIC_RESULTS_NOT_ARRAY",
                "blocking": False,
                "authoritative": False,
            }
        ]
    organized: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items):
        if isinstance(item, dict):
            goal_item_id = _nonempty_text(item.get("goal_item_id"))
            result = _nonempty_text(item.get("result"))
            if goal_item_id is None:
                warnings.append(
                    {
                        "warning_code": "TASK_SEMANTIC_ITEM_DROPPED",
                        "raw_item_index": index,
                        "blocking": True,
                        "authoritative": False,
                    }
                )
                continue
            if result is None:
                observations = []
                status = _nonempty_text(item.get("status"))
                evidence = _nonempty_text(item.get("evidence"))
                if status is not None:
                    observations.append(f"status={status}")
                if evidence is not None:
                    observations.append(f"diagnostic evidence={evidence}")
                if not observations:
                    warnings.append(
                        {
                            "warning_code": "TASK_SEMANTIC_ITEM_DROPPED",
                            "raw_item_index": index,
                            "blocking": True,
                            "authoritative": False,
                        }
                    )
                    continue
                current_boundary = (slice_change_boundary or {}).get("current_boundary")
                current_boundary = current_boundary if isinstance(current_boundary, dict) else {}
                symbol = _nonempty_text(current_boundary.get("symbol"))
                expected = _nonempty_text(current_boundary.get("expected_observation"))
                boundary_detail = ""
                if symbol is not None and expected is not None:
                    boundary_detail = f" current slice {symbol}={expected}"
                elif symbol is not None:
                    boundary_detail = f" current slice symbol={symbol}"
                elif expected is not None:
                    boundary_detail = f" current slice expected={expected}"
                result = (
                    f"{goal_item_id} task observation for {assigned_path}{boundary_detail}: "
                    + "; ".join(observations)
                    + "."
                )
                warnings.append(
                    {
                        "warning_code": "TASK_SEMANTIC_DIAGNOSTIC_ORGANIZED",
                        "raw_item_index": index,
                        "blocking": False,
                        "authoritative": False,
                    }
                )
            organized.append({"goal_item_id": goal_item_id, "result": result})
            continue
        warnings.append(
            {
                "warning_code": "TASK_SEMANTIC_ITEM_DROPPED",
                "raw_item_index": index,
                "blocking": False,
                "authoritative": False,
            }
        )
    return organized, warnings


def _schema_errors(report: dict[str, Any]) -> list[dict[str, Any]]:
    errors = []
    for error in iter_jsonschema_errors(report, "worker_patchlet_report_v2.schema.json"):
        pointer = "/" + "/".join(str(item) for item in error.absolute_path)
        errors.append(
            {
                "field": str(error.absolute_path[0]) if error.absolute_path else "worker_report",
                "json_pointer": pointer if pointer != "/" else "",
                "message": error.message,
                "normalized_signature": "REPORT_PRODUCTION_V2_SCHEMA_INVALID",
            }
        )
    return errors


def _pre_submission_errors(
    report: dict[str, Any],
    *,
    context: dict[str, Any],
    inventory: dict[str, Any],
    preservation: dict[str, Any],
    report_path: Path,
) -> list[dict[str, Any]]:
    assigned_path = str(context["allowed_product_runtime_file"])
    errors: list[dict[str, Any]] = []
    if report.get("status") == "COMPLETE" and report.get("changed_product_runtime_file") != assigned_path:
        errors.append(
            {
                "field": "changed_product_runtime_file",
                "json_pointer": "/changed_product_runtime_file",
                "message": (
                    "Report changed_product_runtime_file must exactly match the assigned "
                    "repository-relative product path"
                ),
                "normalized_signature": "changed_product_runtime_file_mismatch",
            }
        )
    if report.get("status") == "COMPLETE":
        root = report.get("root_cause_classification")
        root = root if isinstance(root, dict) else {}
        for field in _REQUIRED_COMPLETE_ROOT_CAUSE_FIELDS:
            value = root.get(field)
            if not ((isinstance(value, str) and value.strip()) or (isinstance(value, list) and value)):
                errors.append(
                    {
                        "field": "root_cause_classification",
                        "json_pointer": f"/root_cause_classification/{field}",
                        "message": f"COMPLETE requires diagnostic root-cause field {field}",
                        "normalized_signature": "report_production_incomplete_root_cause",
                    }
                )
    target_repo_root = context.get("target_repo_root")
    if not isinstance(target_repo_root, str) or not target_repo_root:
        errors.append(
            {
                "field": "report_production_context",
                "json_pointer": "/target_repo_root",
                "message": "Report production context requires target_repo_root",
                "normalized_signature": "REPORT_PRODUCTION_CONTEXT_INCOMPLETE",
            }
        )
    else:
        evidence_result = normalize_probe_artifact_refs(
            report.get("probe_artifact_refs") or [],
            target_repo_root=Path(target_repo_root),
            patchlet_id=str(context.get("patchlet_id") or ""),
            evidence_inventory=inventory,
            evidence_preservation=preservation,
        )
        errors.extend(evidence_result.errors)
        try:
            parse_raw_report(report_path)
        except RawReportError as exc:
            errors.append(
                {
                    "field": "raw_worker_report",
                    "json_pointer": "",
                    "message": str(exc),
                    "normalized_signature": exc.code,
                }
            )
        semantic_items = report.get("semantic_goal_results")
        if isinstance(semantic_items, list) and semantic_items:
            semantic_result = normalize_semantic_goal_results(
                raw_items=semantic_items,
                patchlet_id=str(context.get("patchlet_id") or ""),
                work_slice_id=str(context.get("work_slice_id") or ""),
                selected_goal_item_ids=list(context.get("goal_item_ids") or []),
                selected_proof_obligation_ids=list(context.get("proof_obligation_ids") or []),
                proof_obligations=dict(context.get("proof_obligations") or {}),
                probe_plan=dict(context.get("probe_plan") or {}),
                slice_change_boundary=context.get("slice_change_boundary"),
                allowed_product_runtime_file=assigned_path,
            )
            for rejected in semantic_result.get("rejected_raw_claims", []):
                errors.append(
                    {
                        "field": "semantic_goal_results",
                        "json_pointer": f"/semantic_goal_results/{rejected.get('raw_item_index', 0)}",
                        "message": rejected.get("message") or rejected.get("error_code"),
                        "normalized_signature": rejected.get("error_code"),
                    }
                )
        errors.extend(_schema_errors(report))
        patchlet = {
            "patchlet_id": context.get("patchlet_id"),
            "work_slice_id": context.get("work_slice_id"),
            "allowed_product_runtime_file": assigned_path,
            "allowed_product_runtime_files": [assigned_path],
            "goal_item_ids": list(context.get("goal_item_ids") or []),
            "proof_obligation_ids": list(context.get("proof_obligation_ids") or []),
            "probe_ids": list(context.get("probe_ids") or []),
            "slice_change_boundary": context.get("slice_change_boundary"),
        }
        structured_report = dict(report)
        structured_report["probe_artifact_refs"] = evidence_result.normalized_refs
        structured = validate_patchlet_report_structured(
            structured_report,
            patchlet,
            repo_root=Path(target_repo_root),
        )
        errors.extend(structured.get("errors", []))
    return errors


def produce_report(
    handoff: dict[str, Any],
    context: dict[str, Any],
    inventory: dict[str, Any],
    preservation: dict[str, Any],
    *,
    output_dir: Path,
) -> dict[str, Any]:
    """Produce one untrusted V2 candidate from immutable copied inputs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    patchlet_id = str(context["patchlet_id"])
    assigned_path = str(context["allowed_product_runtime_file"])
    status = handoff.get("status")
    report: dict[str, Any] = {
        "schema_version": "2.0",
        "kind": "worker_patchlet_report",
        "patchlet_id": patchlet_id,
        "status": status,
    }
    copied_fields = []
    for name in handoff:
        if name not in _TASK_HANDOFF_REPORT_FIELDS:
            continue
        report[name] = handoff[name]
        copied_fields.append(name)
    report["root_cause_classification"] = _organize_root_cause(
        handoff,
        assigned_path=assigned_path,
        patchlet_id=patchlet_id,
    )
    semantic_goal_results, semantic_organization_warnings = _organize_semantic_goal_results(
        handoff,
        goal_item_ids=[str(item) for item in context.get("goal_item_ids", []) if str(item)],
        assigned_path=assigned_path,
        slice_change_boundary=context.get("slice_change_boundary"),
    )
    report["semantic_goal_results"] = semantic_goal_results
    report["changed_product_runtime_file"] = assigned_path if status == "COMPLETE" else None
    aliases = _captured_aliases(preservation)
    report["changed_artifact_files"] = [row["path"] for row in aliases]
    report["probe_artifact_refs"] = _group_probe_refs(
        patchlet_id=patchlet_id,
        probe_ids=list(context.get("probe_ids") or []),
        aliases=aliases,
    )
    target_repo_root = context.get("target_repo_root")
    if isinstance(target_repo_root, str) and target_repo_root:
        evidence_normalization = normalize_probe_artifact_refs(
            report["probe_artifact_refs"],
            target_repo_root=Path(target_repo_root),
            patchlet_id=patchlet_id,
            evidence_inventory=inventory,
            evidence_preservation=preservation,
        )
        if not evidence_normalization.errors and not evidence_normalization.warnings:
            report["probe_artifact_refs"] = evidence_normalization.normalized_refs
    mock_override = context.get("mock_report_override")
    if isinstance(mock_override, dict):
        report.update(mock_override)
    if isinstance(target_repo_root, str) and target_repo_root:
        evidence_normalization = normalize_probe_artifact_refs(
            report.get("probe_artifact_refs") or [],
            target_repo_root=Path(target_repo_root),
            patchlet_id=patchlet_id,
            evidence_inventory=inventory,
            evidence_preservation=preservation,
        )
        if not evidence_normalization.errors and not evidence_normalization.warnings:
            report["probe_artifact_refs"] = evidence_normalization.normalized_refs
    report_path = output_dir / REPORT_FILENAME
    write_json(report_path, report)
    return {"report": report}


def _orchestrator_report_metadata(
    *,
    handoff: dict[str, Any],
    context: dict[str, Any],
    inventory: dict[str, Any],
    preservation: dict[str, Any],
    report: dict[str, Any],
    report_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    deterministic_errors = _pre_submission_errors(
        report,
        context=context,
        inventory=inventory,
        preservation=preservation,
        report_path=report_path,
    )
    _, unknown_report_fields = classify_fields(report)
    aliases = _captured_aliases(preservation)
    _, semantic_organization_warnings = _organize_semantic_goal_results(
        handoff,
        goal_item_ids=[str(item) for item in context.get("goal_item_ids", []) if str(item)],
        assigned_path=str(context["allowed_product_runtime_file"]),
        slice_change_boundary=context.get("slice_change_boundary"),
    )
    trace = {
        "schema_version": "1.0",
        "kind": "report_production_trace",
        "worker_id": "report_production_worker",
        "patchlet_id": context.get("patchlet_id"),
        "attempt_id": context.get("attempt_id"),
        "contract_fingerprint": context.get("contract_fingerprint"),
        "task_handoff_sha256": context.get("task_handoff_sha256"),
        "candidate_patch_sha256": context.get("candidate_patch_sha256"),
        "inventory_truncated": bool(inventory.get("inventory_truncated")),
        "copied_handoff_fields": sorted(
            name
            for name in handoff
            if name in _TASK_HANDOFF_REPORT_FIELDS
        ),
        "orchestrator_owned_fields": sorted(_ORCHESTRATOR_OWNED_FIELDS),
        "captured_evidence_reference_count": len(aliases),
        "skipped_evidence_reference_count": int(inventory.get("skipped_file_count") or 0),
        "semantic_organization_warnings": semantic_organization_warnings,
        "semantic_results_authoritative": False,
        "unknown_report_fields": unknown_report_fields,
        "worker_writable_outputs": [REPORT_FILENAME],
        "authoritative": False,
        "deterministic_validation": {
            "valid": not deterministic_errors,
            "errors": deterministic_errors,
        },
    }
    result = {
        "schema_version": "1.0",
        "kind": "report_production_worker_result",
        "worker_id": "report_production_worker",
        "patchlet_id": context.get("patchlet_id"),
        "attempt_id": context.get("attempt_id"),
        "accepted": not deterministic_errors,
        "report_sha256": _sha256(report_path),
        "worker_output_files": [REPORT_FILENAME],
        "product_files_written": 0,
        "evidence_files_written": 0,
        "recursive_worker_started": False,
        "authoritative": False,
        "blocking_errors": deterministic_errors,
    }
    return trace, result


def verify_report_production_output_boundary(output_dir: Path) -> list[dict[str, Any]]:
    unexpected = sorted(
        path.name for path in output_dir.iterdir() if path.name not in WORKER_ALLOWED_OUTPUTS
    )
    invalid = sorted(
        path.name
        for path in output_dir.iterdir()
        if path.name in WORKER_ALLOWED_OUTPUTS and (path.is_symlink() or not path.is_file())
    )
    paths = unexpected + invalid
    return ([{"code": "REPORT_PRODUCTION_OUTPUT_BOUNDARY_VIOLATION", "paths": paths}] if paths else [])


def launch_report_production_worker(
    *,
    task_handoff_path: Path,
    context: dict[str, Any],
    evidence_inventory_path: Path,
    evidence_preservation_path: Path,
    output_dir: Path,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Run one non-recursive report producer against read-only copied inputs."""
    if os.environ.get("CXOR_REPORT_PRODUCTION_ACTIVE") == "1":
        return {"accepted": False, "failure_code": "RECURSIVE_REPORT_PRODUCTION_WORKER_REJECTED"}
    handoff_errors = validate_task_completion_handoff(
        task_handoff_path,
        patchlet_id=str(context.get("patchlet_id") or ""),
        goal_item_ids=list(context.get("goal_item_ids") or []),
    )
    if handoff_errors:
        return {
            "accepted": False,
            "failure_code": handoff_errors[0]["code"],
            "errors": handoff_errors,
        }
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    durable_contract_path = output_dir.parent.parent / "REPORT_SCHEMA_CONTRACT.md"
    durable_contract_path.parent.mkdir(parents=True, exist_ok=True)
    durable_contract_path.write_text(
        render_primary_worker_report_template()
        + "\nAssigned product path for this attempt: `"
        + str(context.get("allowed_product_runtime_file"))
        + "`.\n`changed_product_runtime_file` must equal that exact repository-relative value for COMPLETE.\n",
        encoding="utf-8",
    )
    root = Path(tempfile.mkdtemp(prefix="report-production-", dir=output_dir.parent))
    inputs = root / "inputs"
    outputs = root / "outputs"
    inputs.mkdir()
    outputs.mkdir()
    copies = {
        "task_completion_handoff.json": task_handoff_path,
        "report_production_context.json": None,
        "worker_evidence_inventory.json": evidence_inventory_path,
        "worker_evidence_preservation_result.json": evidence_preservation_path,
        "REPORT_SCHEMA_CONTRACT.md": durable_contract_path,
    }
    context_path = inputs / "report_production_context.json"
    write_json(context_path, context)
    for name, source in copies.items():
        destination = inputs / name
        if source is not None:
            shutil.copyfile(source, destination)
        destination.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    command = [sys.executable, "-m", "codex_orchestrator.report_production_worker", str(inputs), str(outputs)]
    env = {
        "CXOR_REPORT_PRODUCTION_ACTIVE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if os.environ.get("PYTHONPATH"):
        env["PYTHONPATH"] = os.environ["PYTHONPATH"]
    try:
        completed = subprocess.run(
            command,
            cwd=outputs,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        shutil.rmtree(root, ignore_errors=True)
        return {"accepted": False, "failure_code": "REPORT_PRODUCTION_TIMEOUT", "timed_out": True}
    boundary_errors = verify_report_production_output_boundary(outputs)
    if completed.returncode != 0 or boundary_errors:
        shutil.rmtree(root, ignore_errors=True)
        return {
            "accepted": False,
            "failure_code": (
                boundary_errors[0]["code"] if boundary_errors else "REPORT_PRODUCTION_FAILED"
            ),
            "stderr": completed.stderr[-2000:],
            "errors": boundary_errors,
        }
    missing = sorted(name for name in WORKER_ALLOWED_OUTPUTS if not (outputs / name).exists())
    if missing:
        shutil.rmtree(root, ignore_errors=True)
        return {"accepted": False, "failure_code": "REPORT_PRODUCTION_CONTRACT_FAILURE", "missing_outputs": missing}
    report = json.loads((outputs / REPORT_FILENAME).read_text(encoding="utf-8"))
    if (
        report.get("schema_version") != "2.0"
        or report.get("kind") != "worker_patchlet_report"
        or report.get("patchlet_id") != context.get("patchlet_id")
        or context.get("contract_fingerprint") != contract_fingerprint()
    ):
        shutil.rmtree(root, ignore_errors=True)
        return {"accepted": False, "failure_code": "REPORT_PRODUCTION_CONTRACT_FAILURE"}
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / REPORT_FILENAME
    shutil.copyfile(outputs / REPORT_FILENAME, report_path)
    handoff = json.loads(task_handoff_path.read_text(encoding="utf-8"))
    inventory = json.loads(evidence_inventory_path.read_text(encoding="utf-8"))
    preservation = json.loads(evidence_preservation_path.read_text(encoding="utf-8"))
    trace, result = _orchestrator_report_metadata(
        handoff=handoff,
        context=context,
        inventory=inventory,
        preservation=preservation,
        report=report,
        report_path=report_path,
    )
    write_json(output_dir / TRACE_FILENAME, trace)
    write_json(output_dir / RESULT_FILENAME, result)
    shutil.rmtree(root, ignore_errors=True)
    if result.get("accepted") is not True:
        errors = list(result.get("blocking_errors") or [])
        signature = (
            str(errors[0].get("normalized_signature"))
            if errors and isinstance(errors[0], dict)
            else "REPORT_PRODUCTION_DETERMINISTIC_VALIDATION_FAILED"
        )
        return {
            "accepted": False,
            "failure_code": signature,
            "errors": errors,
            "report_path": output_dir / REPORT_FILENAME,
            "trace_path": output_dir / TRACE_FILENAME,
            "result_path": output_dir / RESULT_FILENAME,
            "worker_result": result,
        }
    return {
        "accepted": True,
        "report_path": output_dir / REPORT_FILENAME,
        "trace_path": output_dir / TRACE_FILENAME,
        "result_path": output_dir / RESULT_FILENAME,
        "worker_result": result,
    }
