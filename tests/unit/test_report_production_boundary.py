from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_orchestrator.jsonio import write_json
from codex_orchestrator.report_contract import contract_fingerprint
from codex_orchestrator.report_production import (
    REPORT_FILENAME,
    launch_report_production_worker,
    produce_report,
    validate_task_completion_handoff,
    verify_report_production_output_boundary,
)
from codex_orchestrator.worker_capsule import task_completion_handoff_contract_text


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
        "target_repo_root": str(handoff.parent),
        "work_slice_id": "WS001",
        "goal_item_ids": ["GI001"],
        "proof_obligation_ids": ["PO001"],
        "probe_ids": ["GP001"],
        "slice_change_boundary": {
            "current_boundary": {
                "file": "profile.awk",
                "goal_item_id": "GI001",
                "goal_item_ids": ["GI001"],
                "proof_obligation_id": "PO001",
                "probe_ids": ["GP001"],
                "symbol": "profile_alpha",
                "expected_observation": "new-profile",
            },
            "forbidden_future_goal_item_ids": [],
            "forbidden_future_proof_obligation_ids": [],
        },
        "proof_obligations": {
            "obligations": [
                {
                    "obligation_id": "PO001",
                    "goal_item_ids": ["GI001"],
                    "claim": "profile.awk profile_alpha=new-profile",
                    "expected": "profile_alpha=new-profile",
                    "target_boundaries": ["profile.awk"],
                }
            ]
        },
        "probe_plan": {
            "probes": [
                {
                    "probe_id": "GP001",
                    "obligation_ids": ["PO001"],
                    "command": "awk -f profile.awk -f test/probe1.awk",
                }
            ]
        },
        "contract_fingerprint": contract_fingerprint(),
        "task_handoff_sha256": hashlib.sha256(handoff.read_bytes()).hexdigest(),
        "candidate_patch_sha256": "1" * 64,
    }


def _evidence(tmp_path: Path, *, status: str = "CAPTURED") -> tuple[Path, Path]:
    import hashlib

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
        durable = tmp_path / ".artifacts/probes/P0001/run_001/proof_runs.jsonl"
        durable.parent.mkdir(parents=True, exist_ok=True)
        durable.write_text("diagnostic evidence\n", encoding="utf-8")
        files.append(
            {
                "capture_status": "CAPTURED",
                "diagnostic_alias_path": ".artifacts/probes/P0001/run_001/proof_runs.jsonl",
                "diagnostic_alias_sha256": hashlib.sha256(durable.read_bytes()).hexdigest(),
                "size_bytes": durable.stat().st_size,
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


def test_report_producer_organizes_minimal_task_semantic_observation(tmp_path: Path):
    handoff = _handoff(
        tmp_path / "handoff.json",
        semantic_goal_results=[
            {"goal_item_id": "GI001", "status": "satisfied", "evidence": "GP001"}
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
    assert report["semantic_goal_results"] == [
        {
            "goal_item_id": "GI001",
            "result": "GI001 task observation for profile.awk current slice profile_alpha=new-profile: status=satisfied; diagnostic evidence=GP001.",
        }
    ]
    trace = json.loads(
        (tmp_path / "production/attempt_1/report_production_trace.json").read_text()
    )
    assert trace["semantic_organization_warnings"] == [
        {
            "warning_code": "TASK_SEMANTIC_DIAGNOSTIC_ORGANIZED",
            "raw_item_index": 0,
            "blocking": False,
            "authoritative": False,
        }
    ]
    assert trace["semantic_results_authoritative"] is False


def test_report_producer_preserves_only_canonical_semantic_shorthand_fields(tmp_path: Path):
    handoff = _handoff(
        tmp_path / "handoff.json",
        semantic_goal_results=[
            {
                "goal_item_id": "GI001",
                "result": "profile.awk profile_alpha=new-profile and GP001 passes.",
                "status": "satisfied",
                "evidence": "GP001",
                "invented": "must not cross the reporting boundary",
            }
        ],
        arbitrary_task_field={"invented": True},
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
            "result": "profile.awk profile_alpha=new-profile and GP001 passes.",
        }
    ]
    assert "arbitrary_task_field" not in report


@pytest.mark.parametrize(
    ("semantic_items", "expected_code"),
    [
        ([{"goal_item": "GI001", "status": "satisfied"}], "TASK_COMPLETION_HANDOFF_FORBIDDEN_GOAL_ITEM_ALIAS"),
        ([{"status": "satisfied", "evidence": "GP001"}], "TASK_COMPLETION_HANDOFF_MISSING_GOAL_ITEM_ID"),
        ([{"goal_item_id": "GI001"}], "TASK_COMPLETION_HANDOFF_SEMANTIC_RESULT_NOT_ORGANIZABLE"),
        (["GI001 passed"], "TASK_COMPLETION_HANDOFF_INVALID_SEMANTIC_RESULT_SHAPE"),
        ([{"goal_item_id": "GI999", "status": "satisfied"}], "TASK_COMPLETION_HANDOFF_UNASSIGNED_GOAL_ITEM_ID"),
        ([{"goal_item_id": "GI001", "evidence": "/tmp/worker/proof.json"}], "TASK_COMPLETION_HANDOFF_UNSAFE_SEMANTIC_REFERENCE"),
        ([{"goal_item_id": "GI001", "evidence": "../proof.json"}], "TASK_COMPLETION_HANDOFF_UNSAFE_SEMANTIC_REFERENCE"),
    ],
)
def test_task_handoff_nested_semantic_validation(
    tmp_path: Path,
    semantic_items: list,
    expected_code: str,
):
    handoff = _handoff(tmp_path / "handoff.json", semantic_goal_results=semantic_items)

    errors = validate_task_completion_handoff(
        handoff,
        patchlet_id="P0001",
        goal_item_ids=["GI001"],
    )

    assert expected_code in {error["code"] for error in errors}


def test_report_producer_pre_submission_validator_rejects_missing_result_text(tmp_path: Path):
    handoff = _handoff(
        tmp_path / "handoff.json",
        semantic_goal_results=[
            {"goal_item_id": "GI001", "status": "satisfied", "evidence": "GP001"}
        ],
    )
    inventory, preservation = _evidence(tmp_path)
    context = _context(handoff)
    context["mock_report_override"] = {
        "semantic_goal_results": [
            {"goal_item_id": "GI001", "status": "satisfied", "evidence": "GP001"}
        ]
    }

    result = launch_report_production_worker(
        task_handoff_path=handoff,
        context=context,
        evidence_inventory_path=inventory,
        evidence_preservation_path=preservation,
        output_dir=tmp_path / "production" / "attempt_1",
    )

    trace = json.loads(Path(result["trace_path"]).read_text())
    signatures = {
        error.get("normalized_signature")
        for error in trace["deterministic_validation"]["errors"]
    }
    assert result["accepted"] is False
    assert trace["deterministic_validation"]["valid"] is False
    assert "MISSING_RESULT_TEXT" in signatures


def test_task_handoff_prompt_assigns_reporting_to_report_production_worker():
    text = task_completion_handoff_contract_text(
        patchlet_id="P0002",
        handoff_path="/tmp/P0002.task_completion_handoff.json",
    )

    assert '"goal_item_id": "<assigned goal_item_id>"' in text
    assert '"status": "satisfied"' in text
    assert '"evidence": "<mapped probe id or bounded diagnostic observation>"' in text
    assert "task worker's primary responsibility is to complete and test" in text
    assert "Report Production Worker owns evidence accounting" in text
    assert "goal_item`, `goal`, `goal_id`, and other aliases are forbidden" in text


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
