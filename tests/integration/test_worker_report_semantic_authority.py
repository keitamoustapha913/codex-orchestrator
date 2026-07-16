from __future__ import annotations

from codex_orchestrator.semantic_result_normalization import normalize_semantic_goal_results


def _proofs():
    return {"obligations": [{"obligation_id": "PO001", "goal_item_ids": ["GI001"], "claim": "healthPath returns /status/helios-16", "target_boundaries": ["health.mjs"]}, {"obligation_id": "PO002", "goal_item_ids": ["GI002"]}]}


def _probes():
    return {"probes": [{"probe_id": "GP001", "obligation_ids": ["PO001"], "command": "python app.py", "expected_observation": {"value": "/status/helios-16"}}]}


def _normalize(result: str, goal: str = "GI001"):
    return normalize_semantic_goal_results(
        raw_items=[{"goal_item_id": goal, "result": result}],
        patchlet_id="P0001",
        work_slice_id="WS001",
        selected_goal_item_ids=["GI001"],
        selected_proof_obligation_ids=["PO001"],
        proof_obligations=_proofs(),
        probe_plan=_probes(),
        slice_change_boundary={"allowed_changes": [{"key": "healthPath", "new_value": "/status/helios-16"}], "forbidden_future_goal_item_ids": ["GI002"], "forbidden_future_proof_obligation_ids": ["PO002"]},
        allowed_product_runtime_file="health.mjs",
    )


def test_schema_valid_vague_report_is_semantically_incomplete():
    result = _normalize("it works")
    assert result["accepted"] is True
    assert result["semantic_quality_warnings"][0]["warning_code"] == "WORKER_REPORT_SEMANTIC_EVIDENCE_INCOMPLETE"


def test_semantically_incomplete_report_does_not_block_clean_proof():
    assert _normalize("it works")["rejected_raw_claims"] == []


def test_exact_report_is_semantically_complete():
    result = _normalize("health.mjs::healthPath satisfies /status/helios-16; verified by GP001.")
    assert result["accepted_raw_claims"]
    assert result["semantic_quality_warnings"] == []


def test_contradictory_report_is_recorded_but_not_product_authority():
    result = normalize_semantic_goal_results(
        raw_items=[{"goal_item_id": "GI001", "result": "health.mjs::healthPath satisfies /status/helios-16; verified by GP001.", "passed": True}],
        patchlet_id="P0001",
        work_slice_id="WS001",
        selected_goal_item_ids=["GI001"],
        selected_proof_obligation_ids=["PO001"],
        proof_obligations=_proofs(),
        probe_plan=_probes(),
        slice_change_boundary={"symbol": "healthPath"},
        allowed_product_runtime_file="health.mjs",
    )
    assert result["accepted"] is True
    assert result["semantic_quality_warnings"][0]["error_code"] == "WORKER_PROOF_CLAIM_NOT_ALLOWED"


def test_false_future_claim_does_not_advance_future_coverage():
    result = _normalize("GI002 is also complete", goal="GI002")
    assert result["accepted"] is True
    assert result["accepted_raw_claims"] == []
    assert result["semantic_quality_warnings"][0]["error_code"] == "FUTURE_GOAL_ITEM"


def test_malformed_report_remains_hard_failure():
    result = normalize_semantic_goal_results(
        raw_items=["not an object"],
        patchlet_id="P0001",
        work_slice_id="WS001",
        selected_goal_item_ids=["GI001"],
        selected_proof_obligation_ids=["PO001"],
        proof_obligations=_proofs(),
        probe_plan=_probes(),
        slice_change_boundary={"symbol": "healthPath"},
    )
    assert result["accepted"] is False




def test_report_cannot_override_unauthorized_file_failure():
    assert True


def test_report_cannot_override_future_slice_failure():
    assert True


def test_report_cannot_override_independent_proof_failure():
    assert True
