from __future__ import annotations

import json
from pathlib import Path

from codex_orchestrator.jsonio import write_json
from codex_orchestrator.report_contract import contract_fingerprint
from codex_orchestrator.report_production import (
    REPORT_FILENAME,
    launch_report_production_worker,
    produce_report,
    validate_task_completion_handoff,
    verify_report_production_output_boundary,
)


def _handoff(path: Path, **overrides) -> Path:
    value = {
        "schema_version": "1.0",
        "kind": "task_worker_completion_handoff",
        "patchlet_id": "P0001",
        "status": "COMPLETE",
        "probe_commands": ["awk -f profile.awk -f test/probe1.awk"],
        "deterministic_run_counts": {
            "baseline": "5/5",
            "proof_of_fix": "5/5",
            "negative_controls": "5/5",
        },
        "root_cause_classification": {
            "observed_failure": "old profile",
            "immediate_cause": "stale profile",
            "why_immediate_cause_happened": "the requested slice was absent",
            "deeper_owner_boundary": "profile.awk",
            "producer_transformer_consumer_boundary": "profile.awk to probe",
            "not_downstream_of_unprobed_state_proof": "direct probe",
            "negative_control_proof": "peer functions unchanged",
            "recursive_why_audit": ["bounded cause"],
        },
        "before_after_state": [],
        "row_ledger": [],
        "trace_ledger": [],
        "cleanup_proof": "worker scratch cleaned",
        "semantic_goal_results": [],
    }
    value.update(overrides)
    write_json(path, value)
    return path


def _context(handoff: Path) -> dict:
    import hashlib

    return {
        "schema_version": "1.0",
        "kind": "report_production_context",
        "patchlet_id": "P0001",
        "attempt_id": "P0001_attempt1",
        "allowed_product_runtime_file": "profile.awk",
        "work_slice_id": "WS001",
        "goal_item_ids": ["GI001"],
        "proof_obligation_ids": ["PO001"],
        "probe_ids": ["GP001"],
        "contract_fingerprint": contract_fingerprint(),
        "task_handoff_sha256": hashlib.sha256(handoff.read_bytes()).hexdigest(),
        "candidate_patch_sha256": "1" * 64,
    }


def _evidence(tmp_path: Path, *, status: str = "CAPTURED") -> tuple[Path, Path]:
    inventory = tmp_path / "worker_evidence_inventory.json"
    preservation = tmp_path / "worker_evidence_preservation_result.json"
    write_json(
        inventory,
        {
            "entries": [
                {
                    "relative_path": "GP001/run_001/proof_runs.jsonl",
                    "capture_status": status,
                }
            ],
            "inventory_truncated": status == "SKIPPED_LIMIT",
            "skipped_file_count": int(status != "CAPTURED"),
        },
    )
    files = []
    if status == "CAPTURED":
        files.append(
            {
                "capture_status": "CAPTURED",
                "diagnostic_alias_path": ".artifacts/probes/P0001/run_001/proof_runs.jsonl",
                "diagnostic_alias_sha256": "a" * 64,
                "size_bytes": 21,
            }
        )
    write_json(preservation, {"files": files, "preservation_complete": True})
    return inventory, preservation


def test_report_producer_owns_exact_product_path_and_ignores_handoff_path(tmp_path: Path):
    handoff = _handoff(
        tmp_path / "handoff.json",
        changed_product_runtime_file="/tmp/disposable/checkout/profile.awk",
    )
    inventory, preservation = _evidence(tmp_path)

    result = launch_report_production_worker(
        task_handoff_path=handoff,
        context=_context(handoff),
        evidence_inventory_path=inventory,
        evidence_preservation_path=preservation,
        output_dir=tmp_path / "production" / "attempt_1",
    )

    assert result["accepted"] is True
    report = json.loads((tmp_path / "production/attempt_1" / REPORT_FILENAME).read_text())
    assert report["changed_product_runtime_file"] == "profile.awk"
    assert "/tmp" not in json.dumps(report)
    contract = (tmp_path / "REPORT_SCHEMA_CONTRACT.md").read_text()
    assert "must equal that exact repository-relative value" in contract
    assert "`profile.awk`" in contract


def test_report_producer_references_only_durably_captured_evidence(tmp_path: Path):
    handoff = _handoff(tmp_path / "handoff.json")
    inventory, preservation = _evidence(tmp_path, status="SKIPPED_LIMIT")

    result = launch_report_production_worker(
        task_handoff_path=handoff,
        context=_context(handoff),
        evidence_inventory_path=inventory,
        evidence_preservation_path=preservation,
        output_dir=tmp_path / "production" / "attempt_1",
    )

    assert result["accepted"] is True
    report = json.loads((tmp_path / "production/attempt_1" / REPORT_FILENAME).read_text())
    assert report["changed_artifact_files"] == []
    assert report["probe_artifact_refs"][0]["files"] == []


def test_report_producer_organizes_simple_task_diagnosis_into_v2_shape(tmp_path: Path):
    handoff = _handoff(
        tmp_path / "handoff.json",
        root_cause_classification={
            "class": "stale_literal_in_profile_alpha",
            "detail": "profile_alpha returned the old value",
        },
        before_after_state=[
            {"phase": "before", "actual_output": "old", "expected_observation": "new"},
            {"phase": "negative_control", "symbol": "profile_beta", "result": "unchanged"},
        ],
    )
    inventory, preservation = _evidence(tmp_path)

    result = launch_report_production_worker(
        task_handoff_path=handoff,
        context=_context(handoff),
        evidence_inventory_path=inventory,
        evidence_preservation_path=preservation,
        output_dir=tmp_path / "production" / "attempt_1",
    )

    assert result["accepted"] is True
    report = json.loads((tmp_path / "production/attempt_1" / REPORT_FILENAME).read_text())
    root = report["root_cause_classification"]
    assert root["observed_failure"] == "profile_alpha returned the old value"
    assert root["immediate_cause"] == "stale_literal_in_profile_alpha"
    assert root["deeper_owner_boundary"] == "profile.awk"
    assert root["negative_control_proof"]
    assert root["recursive_why_audit"]


def test_report_producer_organizes_unstructured_task_semantic_prose(tmp_path: Path):
    handoff = _handoff(
        tmp_path / "handoff.json",
        semantic_goal_results=["profile.awk::SCB001 satisfies; verified by GP001"],
    )
    inventory, preservation = _evidence(tmp_path)

    result = launch_report_production_worker(
        task_handoff_path=handoff,
        context=_context(handoff),
        evidence_inventory_path=inventory,
        evidence_preservation_path=preservation,
        output_dir=tmp_path / "production" / "attempt_1",
    )

    assert result["accepted"] is True
    report = json.loads((tmp_path / "production/attempt_1" / REPORT_FILENAME).read_text())
    assert report["semantic_goal_results"] == [
        {
            "goal_item_id": "GI001",
            "result": "profile.awk::SCB001 satisfies; verified by GP001",
        }
    ]
    trace = json.loads(
        (tmp_path / "production/attempt_1/report_production_trace.json").read_text()
    )
    assert trace["semantic_organization_warnings"][0]["blocking"] is False
    assert trace["semantic_organization_warnings"][0]["authoritative"] is False


def test_report_producer_rejects_absolute_product_path_before_ingestion(tmp_path: Path):
    handoff = _handoff(tmp_path / "handoff.json")
    inventory, preservation = _evidence(tmp_path)
    context = _context(handoff)
    context["mock_report_override"] = {
        "changed_product_runtime_file": "/tmp/disposable/checkout/profile.awk"
    }

    result = launch_report_production_worker(
        task_handoff_path=handoff,
        context=context,
        evidence_inventory_path=inventory,
        evidence_preservation_path=preservation,
        output_dir=tmp_path / "production" / "attempt_1",
    )

    assert result["accepted"] is False
    assert result["failure_code"] == "changed_product_runtime_file_mismatch"
    assert Path(result["result_path"]).exists()


def test_report_producer_rejects_wrong_relative_peer_path_before_ingestion(tmp_path: Path):
    handoff = _handoff(tmp_path / "handoff.json")
    inventory, preservation = _evidence(tmp_path)
    context = _context(handoff)
    context["mock_report_override"] = {"changed_product_runtime_file": "other.awk"}

    result = launch_report_production_worker(
        task_handoff_path=handoff,
        context=context,
        evidence_inventory_path=inventory,
        evidence_preservation_path=preservation,
        output_dir=tmp_path / "production" / "attempt_1",
    )

    assert result["accepted"] is False
    assert result["failure_code"] == "changed_product_runtime_file_mismatch"


def test_task_handoff_rejects_formal_report_identity(tmp_path: Path):
    handoff = _handoff(
        tmp_path / "handoff.json",
        schema_version="2.0",
        kind="worker_patchlet_report",
    )

    assert validate_task_completion_handoff(handoff, patchlet_id="P0001") == [
        {"code": "TASK_COMPLETION_HANDOFF_INVALID_IDENTITY"}
    ]


def test_report_production_worker_cannot_recurse(tmp_path: Path, monkeypatch):
    handoff = _handoff(tmp_path / "handoff.json")
    inventory, preservation = _evidence(tmp_path)
    monkeypatch.setenv("CXOR_REPORT_PRODUCTION_ACTIVE", "1")

    result = launch_report_production_worker(
        task_handoff_path=handoff,
        context=_context(handoff),
        evidence_inventory_path=inventory,
        evidence_preservation_path=preservation,
        output_dir=tmp_path / "production" / "attempt_1",
    )

    assert result["failure_code"] == "RECURSIVE_REPORT_PRODUCTION_WORKER_REJECTED"


def test_report_production_output_boundary_rejects_extra_file(tmp_path: Path):
    (tmp_path / "unexpected.txt").write_text("no")

    assert verify_report_production_output_boundary(tmp_path) == [
        {"code": "REPORT_PRODUCTION_OUTPUT_BOUNDARY_VIOLATION", "paths": ["unexpected.txt"]}
    ]


def test_report_worker_writes_only_the_v2_candidate(tmp_path: Path):
    handoff_path = _handoff(tmp_path / "handoff.json")
    inventory_path, preservation_path = _evidence(tmp_path)
    output_dir = tmp_path / "worker-output"

    produce_report(
        json.loads(handoff_path.read_text()),
        _context(handoff_path),
        json.loads(inventory_path.read_text()),
        json.loads(preservation_path.read_text()),
        output_dir=output_dir,
    )

    assert sorted(path.name for path in output_dir.iterdir()) == [REPORT_FILENAME]
