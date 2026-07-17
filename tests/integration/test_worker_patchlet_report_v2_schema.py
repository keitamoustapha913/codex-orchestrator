from __future__ import annotations

import hashlib
import json
from pathlib import Path

from codex_orchestrator.report_contract import canonical_example_report
from codex_orchestrator.validators.report_validator import (
    ReportValidationError,
    validate_patchlet_report_file,
)
from codex_orchestrator.validators.schema_validator import validate_json


SCHEMA = "worker_patchlet_report_v2.schema.json"


def _base_report(refs):
    return {
        "schema_version": "2.0",
        "kind": "worker_patchlet_report",
        "patchlet_id": "P0001",
        "status": "VERIFIED_NO_CHANGE_NEEDED",
        "changed_product_runtime_file": None,
        "changed_artifact_files": [],
        "probe_commands": ["probe"],
        "deterministic_run_counts": {"baseline": "5/5", "negative_controls": "5/5"},
        "root_cause_classification": {
            "observed_failure": "none",
            "immediate_cause": "none",
            "why_immediate_cause_happened": "none",
            "deeper_owner_boundary": "app.py",
            "producer_transformer_consumer_boundary": "probe",
            "not_downstream_of_unprobed_state_proof": "probe",
            "negative_control_proof": "probe",
            "recursive_why_audit": ["why"],
        },
        "before_after_state": [],
        "row_ledger": [],
        "trace_ledger": [],
        "cleanup_proof": "ok",
        "probe_artifact_refs": refs,
    }


def _ref(*, files=None):
    ref = {
        "patchlet_id": "P0001",
        "probe_root": ".artifacts/probes/P0001",
        "run_id": "default",
    }
    if files is not None:
        ref["files"] = files
    return ref


def test_worker_patchlet_report_v2_accepts_object_ref_without_files():
    assert validate_json(_base_report([_ref()]), SCHEMA) == []


def test_worker_patchlet_report_v2_accepts_object_ref_with_files():
    report = _base_report(
        [
            _ref(
                files=[
                    {
                        "path": ".artifacts/probes/P0001/a.txt",
                        "kind": "a",
                        "sha256": "0" * 64,
                        "size_bytes": 1,
                    }
                ]
            )
        ]
    )
    assert validate_json(report, SCHEMA) == []


def test_worker_patchlet_report_v2_rejects_string_ref_in_canonical_report():
    assert validate_json(_base_report([".artifacts/probes/P0001/a.txt"]), SCHEMA)


def test_worker_patchlet_report_v2_rejects_file_entry_missing_path():
    report = _base_report(
        [_ref(files=[{"kind": "a", "sha256": "0" * 64, "size_bytes": 1}])]
    )
    assert validate_json(report, SCHEMA)


def test_worker_patchlet_report_v2_rejects_file_entry_missing_sha256():
    report = _base_report(
        [
            _ref(
                files=[
                    {
                        "path": ".artifacts/probes/P0001/a.txt",
                        "kind": "a",
                        "size_bytes": 1,
                    }
                ]
            )
        ]
    )
    assert validate_json(report, SCHEMA)


def test_worker_patchlet_report_v2_rejects_file_entry_missing_size_bytes():
    report = _base_report(
        [
            _ref(
                files=[
                    {
                        "path": ".artifacts/probes/P0001/a.txt",
                        "kind": "a",
                        "sha256": "0" * 64,
                    }
                ]
            )
        ]
    )
    assert validate_json(report, SCHEMA)


def test_worker_patchlet_report_v2_semantic_validation_accepts_matching_file_metadata(git_repo: Path):
    path = git_repo / ".artifacts/probes/P0001/a.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    report = _base_report(
        [
            _ref(
                files=[
                    {
                        "path": ".artifacts/probes/P0001/a.txt",
                        "kind": "a",
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "size_bytes": 1,
                    }
                ]
            )
        ]
    )
    report_path = git_repo / ".codex-orchestrator/reports/P0001.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report), encoding="utf-8")
    assert validate_patchlet_report_file(report_path, {"patchlet_id": "P0001"})


def test_worker_patchlet_report_v2_semantic_validation_rejects_wrong_sha256(git_repo: Path):
    path = git_repo / ".artifacts/probes/P0001/a.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    report = _base_report(
        [
            _ref(
                files=[
                    {
                        "path": ".artifacts/probes/P0001/a.txt",
                        "kind": "a",
                        "sha256": "0" * 64,
                        "size_bytes": 1,
                    }
                ]
            )
        ]
    )
    report_path = git_repo / ".codex-orchestrator/reports/P0001.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report), encoding="utf-8")
    try:
        validate_patchlet_report_file(report_path, {"patchlet_id": "P0001"})
    except ReportValidationError as exc:
        assert "sha256" in str(exc)
    else:
        raise AssertionError("wrong sha256 unexpectedly validated")


def test_generated_worker_patchlet_report_v2_fixture_validates():
    assert validate_json(canonical_example_report(), SCHEMA) == []
