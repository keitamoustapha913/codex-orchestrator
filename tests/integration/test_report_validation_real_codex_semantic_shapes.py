from __future__ import annotations

from codex_orchestrator.semantic_result_normalization import normalize_semantic_goal_results
from codex_orchestrator.validators.schema_validator import validate_json


def _base_report(semantic_goal_results):
    return {
        "schema_version": "1.0",
        "kind": "patchlet_report",
        "patchlet_id": "P0001",
        "status": "COMPLETE",
        "changed_product_runtime_file": "service.cfg",
        "changed_artifact_files": [],
        "probe_commands": ["grep -Fx status=ready-no-compat service.cfg"],
        "deterministic_run_counts": {"baseline": "1/1", "proof_of_fix": "1/1", "negative_controls": "1/1"},
        "root_cause_classification": {
            "observed_failure": "status was pending",
            "immediate_cause": "status line not updated",
            "why_immediate_cause_happened": "current slice not applied",
            "deeper_owner_boundary": "P0001",
            "producer_transformer_consumer_boundary": "worker to diff gate",
            "not_downstream_of_unprobed_state_proof": "independent proof follows",
            "negative_control_proof": "future keys unchanged",
            "recursive_why_audit": ["bounded"],
        },
        "before_after_state": [],
        "row_ledger": [],
        "trace_ledger": [],
        "cleanup_proof": "clean",
        "acceptance_criteria_result": "pass",
        "semantic_goal_results": semantic_goal_results,
    }


def _normalization(raw_items):
    return normalize_semantic_goal_results(
        raw_items=raw_items,
        patchlet_id="P0001",
        work_slice_id="WS001",
        selected_goal_item_ids=["GI001"],
        selected_proof_obligation_ids=["PO001"],
        proof_obligations={"obligations": [{"obligation_id": "PO001", "goal_item_ids": ["GI001"], "required": True}]},
        probe_plan={"probes": [{"probe_id": "GP001", "obligation_ids": ["PO001"], "expected_observation": {"value": "status=ready-no-compat"}}]},
        slice_change_boundary={"allowed_changes": [{"key": "status", "new_value": "ready-no-compat"}], "forbidden_changes": [{"key": "mode"}]},
    )


def test_report_validation_accepts_canonical_semantic_goal_result():
    errors = validate_json(_base_report([{"criterion_id": "PO001", "kind": "orchestrator_verified_proof_obligation_result", "expected_value": "status=ready-no-compat", "actual_value": "status=ready-no-compat", "passed": True}]), "patchlet_report.schema.json")
    assert errors == []


def test_report_validation_accepts_safe_shorthand_semantic_goal_result():
    errors = validate_json(_base_report([{"goal_item_id": "GI001", "result": "status=ready-no-compat"}]), "patchlet_report.schema.json")
    assert errors == []
    assert _normalization([{"goal_item_id": "GI001", "result": "status=ready-no-compat"}])["accepted"] is True


def test_report_validation_rejects_shorthand_without_goal_item():
    assert validate_json(_base_report([{"result": "status=ready-no-compat"}]), "patchlet_report.schema.json")


def test_report_validation_rejects_shorthand_without_result_text():
    assert validate_json(_base_report([{"goal_item_id": "GI001"}]), "patchlet_report.schema.json")


def test_report_validation_warns_for_shorthand_with_unknown_extra_proof_claim():
    result = _normalization([{"goal_item_id": "GI001", "result": "status=ready-no-compat", "passed": True}])
    assert result["accepted"] is True
    assert result["semantic_quality_warnings"][0]["error_code"] == "WORKER_PROOF_CLAIM_NOT_ALLOWED"


def test_report_validation_warns_for_shorthand_claiming_all_future_work_done():
    result = _normalization([{"goal_item_id": "GI001", "result": "all future work complete and all five settings updated"}])
    assert result["accepted"] is True
    assert result["semantic_quality_warnings"][0]["error_code"] == "FUTURE_SLICE_CLAIM"


def test_report_validation_reports_structured_error_for_unlinked_shorthand():
    result = _normalization([{"goal_item_id": "GI999", "result": "status=ready-no-compat"}])
    assert result["semantic_quality_warnings"][0]["error_code"] == "UNLINKED_GOAL_ITEM"


def test_report_validation_reports_structured_error_for_vague_shorthand():
    result = _normalization([{"goal_item_id": "GI001", "result": "ok"}])
    assert result["semantic_quality_warnings"][0]["error_code"] == "VAGUE_RESULT_TEXT"


def test_patchlet_report_schema_requires_canonical_goal_item_id():
    assert validate_json(
        _base_report([{"goal": "GI001", "result": "status=ready-no-compat"}]),
        "patchlet_report.schema.json",
    )
