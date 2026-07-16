"""Bounded report-reorganization worker.

The implementation is intentionally mechanical: it copies values and records
their origin.  It cannot produce proof, coverage, or promotion decisions.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .jsonio import write_json
from .report_contract import KNOWN_FIELD_TYPES, classify_fields, contract_fingerprint

ALLOWED_OUTPUTS = frozenset({
    "report_reorganization_candidate.json",
    "report_reorganization_trace.json",
    "report_reorganization_worker_result.json",
})


def reorganize_report(
    raw_report: dict[str, Any],
    *,
    source_report_sha256: str,
    patchlet_id: str,
    attempt_id: str,
    source_report_version: str = "",
    output_dir: Path,
) -> dict[str, Any]:
    """Run one disposable, non-authoritative reorganization attempt."""
    output_dir.mkdir(parents=True, exist_ok=True)
    known, unknown = classify_fields(raw_report)
    trace = []
    for name, value in raw_report.items():
        destination = name if name in known else None
        mapping_type = "DIRECT" if destination else "UNRECOGNIZED_EXTENSION"
        trace.append({
            "source_field": name,
            "source_path": f"$.{name}",
            "source_value_type": type(value).__name__,
            "destination_canonical_field": destination,
            "mapping_type": mapping_type,
            "mapping_owner": "orchestrator_contract",
            "worker_mapping_explanation": "copied without interpretation",
            "value_preservation_hash": hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest(),
        })
    candidate = {
        "schema_version": "1.0",
        "kind": "report_reorganization_candidate",
        "source_report_sha256": source_report_sha256,
        "contract_fingerprint": contract_fingerprint(),
        "source_report_version": source_report_version,
        "target_contract_version": "2.0",
        "patchlet_id": patchlet_id,
        "attempt_id": attempt_id,
        "normalized_known_fields": known,
        "unrecognized_fields": unknown,
        "missing_required_fields": [],
        "conflicting_fields": [],
        "invented_fields": [],
        "dropped_fields": [],
        "candidate_complete": all(field in known for field in ("patchlet_id", "status", "kind")),
    }
    trace_artifact = {
        "schema_version": "1.0", "kind": "report_reorganization_trace",
        "source_report_sha256": source_report_sha256, "patchlet_id": patchlet_id,
        "attempt_id": attempt_id, "contract_fingerprint": contract_fingerprint(), "fields": trace,
        "raw_field_count": len(raw_report), "accounted_field_count": len(trace),
        "mapping_counts": {kind: sum(row["mapping_type"] == kind for row in trace) for kind in ("DIRECT", "STRUCTURAL_REORGANIZATION", "UNRECOGNIZED_EXTENSION", "CONFLICT")},
    }
    result = {
        "schema_version": "1.0", "kind": "report_reorganization_worker_result",
        "worker_id": "report_reorganization_worker", "patchlet_id": patchlet_id,
        "attempt_id": attempt_id, "accepted": True,
        "unknown_field_count": len(unknown), "blocking_errors": [],
    }
    write_json(output_dir / "report_reorganization_candidate.json", candidate)
    write_json(output_dir / "report_reorganization_trace.json", trace_artifact)
    write_json(output_dir / "report_reorganization_worker_result.json", result)
    return {"candidate": candidate, "trace": trace_artifact, "worker_result": result}


def verify_reorganization(candidate: dict[str, Any], trace: dict[str, Any], *, raw_report_sha256: str, patchlet_id: str, attempt_id: str) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if candidate.get("source_report_sha256") != raw_report_sha256:
        errors.append({"code": "REPORT_REORGANIZATION_SOURCE_HASH_MISMATCH"})
    if candidate.get("contract_fingerprint") != contract_fingerprint() or trace.get("contract_fingerprint") != contract_fingerprint():
        errors.append({"code": "REPORT_REORGANIZATION_CONTRACT_FINGERPRINT_MISMATCH"})
    if candidate.get("patchlet_id") != patchlet_id or candidate.get("attempt_id") != attempt_id:
        errors.append({"code": "REPORT_REORGANIZATION_CONTRACT_FAILURE", "message": "identity mismatch"})
    fields = trace.get("fields") or []
    if trace.get("raw_field_count") != len(fields) or trace.get("accounted_field_count") != len(fields):
        errors.append({"code": "REPORT_REORGANIZATION_FIELD_DROPPED"})
    if candidate.get("invented_fields") or candidate.get("dropped_fields"):
        errors.append({"code": "REPORT_REORGANIZATION_FIELD_INVENTED" if candidate.get("invented_fields") else "REPORT_REORGANIZATION_FIELD_DROPPED"})
    return errors


def verify_reorganization_values(candidate: dict[str, Any], trace: dict[str, Any], raw_report: dict[str, Any]) -> list[dict[str, Any]]:
    """Verify that reorganization copied values and types without interpretation."""
    errors: list[dict[str, Any]] = []
    trace_fields = {row.get("source_field") for row in trace.get("fields", [])}
    if trace_fields != set(raw_report):
        errors.append({"code": "REPORT_REORGANIZATION_FIELD_DROPPED"})
    known, unknown = classify_fields(raw_report)
    candidate_known = candidate.get("normalized_known_fields") or {}
    for name, value in known.items():
        if name not in candidate_known:
            errors.append({"code": "REPORT_REORGANIZATION_FIELD_DROPPED", "field": name})
        elif type(candidate_known[name]) is not type(value):
            errors.append({"code": "REPORT_REORGANIZATION_TYPE_CHANGED", "field": name})
        elif candidate_known[name] != value:
            errors.append({"code": "REPORT_REORGANIZATION_VALUE_CHANGED", "field": name})
    unknown_names = {row.get("field_name") for row in candidate.get("unrecognized_fields", [])}
    expected_unknown_names = {row["field_name"] for row in unknown}
    if unknown_names != expected_unknown_names:
        errors.append({"code": "REPORT_REORGANIZATION_FIELD_DROPPED"})
    return errors


def verify_worker_output_boundary(output_dir: Path, *, allowed: frozenset[str] = ALLOWED_OUTPUTS) -> list[dict[str, Any]]:
    unexpected = sorted(path.name for path in output_dir.iterdir() if path.name not in allowed)
    invalid_allowed = sorted(path.name for path in output_dir.iterdir() if path.name in allowed and (path.is_symlink() or not path.is_file()))
    bad = unexpected + invalid_allowed
    return ([{"code": "REPORT_REORGANIZATION_OUTPUT_BOUNDARY_VIOLATION", "paths": bad}] if bad else [])


def launch_report_reorganization_worker(
    raw_report_path: Path,
    *,
    source_report_sha256: str,
    patchlet_id: str,
    attempt_id: str,
    output_dir: Path,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Execute exactly one disposable auxiliary worker with a closed output set."""
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="report-reorganization-", dir=output_dir.parent))
    inputs = root / "inputs"
    outputs = root / "outputs"
    inputs.mkdir(parents=True)
    outputs.mkdir(parents=True)
    raw_copy = inputs / "raw_worker_report.json"
    shutil.copyfile(raw_report_path, raw_copy)
    raw_copy.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    contract_copy = inputs / "WorkerPatchletReportV2.contract.json"
    write_json(contract_copy, {"contract": "WorkerPatchletReportV2", "known_fields": sorted(KNOWN_FIELD_TYPES)})
    contract_copy.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    command = [sys.executable, "-m", "codex_orchestrator.report_reorganization_worker",
               str(raw_copy), str(outputs), source_report_sha256, patchlet_id, attempt_id]
    try:
        completed = subprocess.run(command, cwd=outputs, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired:
        shutil.rmtree(root, ignore_errors=True)
        return {"accepted": False, "failure_code": "REPORT_REORGANIZATION_FAILED", "timed_out": True}
    boundary_errors = verify_worker_output_boundary(outputs)
    if boundary_errors:
        shutil.rmtree(root, ignore_errors=True)
        return {"accepted": False, "failure_code": boundary_errors[0]["code"], "unexpected_outputs": boundary_errors[0]["paths"]}
    if completed.returncode != 0:
        shutil.rmtree(root, ignore_errors=True)
        return {"accepted": False, "failure_code": "REPORT_REORGANIZATION_FAILED", "stderr": completed.stderr[-2000:]}
    missing = sorted(name for name in ALLOWED_OUTPUTS if not (outputs / name).exists())
    if missing:
        shutil.rmtree(root, ignore_errors=True)
        return {"accepted": False, "failure_code": "REPORT_REORGANIZATION_CONTRACT_FAILURE", "missing_outputs": missing}
    result = json.loads((outputs / "report_reorganization_worker_result.json").read_text(encoding="utf-8"))
    if result.get("worker_id") != "report_reorganization_worker":
        shutil.rmtree(root, ignore_errors=True)
        return {"accepted": False, "failure_code": "REPORT_REORGANIZATION_CONTRACT_FAILURE"}
    raw_value = json.loads(raw_copy.read_text(encoding="utf-8"))
    # Promote only the three declared files out of the disposable worker area.
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in ALLOWED_OUTPUTS:
        shutil.copyfile(outputs / name, output_dir / name)
    shutil.rmtree(root, ignore_errors=True)
    candidate = json.loads((output_dir / "report_reorganization_candidate.json").read_text(encoding="utf-8"))
    trace = json.loads((output_dir / "report_reorganization_trace.json").read_text(encoding="utf-8"))
    errors = verify_reorganization(candidate, trace, raw_report_sha256=source_report_sha256,
        patchlet_id=patchlet_id, attempt_id=attempt_id)
    errors.extend(verify_reorganization_values(candidate, trace, raw_value))
    if errors:
        return {"accepted": False, "failure_code": errors[0].get("code", "REPORT_REORGANIZATION_CONTRACT_FAILURE"), "errors": errors}
    return {"accepted": True, "candidate": candidate, "trace": trace, "worker_result": result}
