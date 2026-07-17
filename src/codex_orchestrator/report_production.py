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
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any

from .jsonio import write_json
from .report_contract import contract_fingerprint, render_primary_worker_report_template


REPORT_FILENAME = "worker_patchlet_report_v2.json"
TRACE_FILENAME = "report_production_trace.json"
RESULT_FILENAME = "report_production_worker_result.json"
WORKER_ALLOWED_OUTPUTS = frozenset({REPORT_FILENAME})
REPORT_PRODUCTION_MAX_ATTEMPTS = 2
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
    }
)

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


def validate_task_completion_handoff(path: Path, *, patchlet_id: str) -> list[dict[str, Any]]:
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
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Shape task prose without granting it semantic authority."""
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
            organized.append(item)
            continue
        if isinstance(item, str) and item.strip() and len(goal_item_ids) == 1:
            organized.append(
                {
                    "goal_item_id": goal_item_ids[0],
                    "result": item.strip(),
                }
            )
            warnings.append(
                {
                    "warning_code": "TASK_SEMANTIC_PROSE_ORGANIZED",
                    "raw_item_index": index,
                    "blocking": False,
                    "authoritative": False,
                }
            )
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


def _pre_submission_errors(
    report: dict[str, Any],
    *,
    assigned_path: str,
) -> list[dict[str, Any]]:
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
        if name in _ORCHESTRATOR_OWNED_FIELDS or name == "status":
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
    mock_override = context.get("mock_report_override")
    if isinstance(mock_override, dict):
        report.update(mock_override)
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
    assigned_path = str(context["allowed_product_runtime_file"])
    deterministic_errors = _pre_submission_errors(report, assigned_path=assigned_path)
    aliases = _captured_aliases(preservation)
    _, semantic_organization_warnings = _organize_semantic_goal_results(
        handoff,
        goal_item_ids=[str(item) for item in context.get("goal_item_ids", []) if str(item)],
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
            if name not in _ORCHESTRATOR_OWNED_FIELDS and name != "status"
        ),
        "orchestrator_owned_fields": sorted(_ORCHESTRATOR_OWNED_FIELDS),
        "captured_evidence_reference_count": len(aliases),
        "skipped_evidence_reference_count": int(inventory.get("skipped_file_count") or 0),
        "semantic_organization_warnings": semantic_organization_warnings,
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
