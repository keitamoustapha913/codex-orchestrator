from __future__ import annotations

from codex_orchestrator.semantic_result_normalization import normalize_semantic_goal_results


def _ctx():
    proof_obligations = {
        "obligations": [
            {"obligation_id": "PO001", "goal_item_ids": ["GI001"], "required": True},
            {"obligation_id": "PO002", "goal_item_ids": ["GI002"], "required": True},
        ]
    }
    probe_plan = {
        "probes": [
            {
                "probe_id": "GP001",
                "obligation_ids": ["PO001"],
                "expected_observation": {"type": "file_contains", "value": "status=ready-no-compat"},
            }
        ]
    }
    boundary = {
        "boundary_type": "text_key_value_update",
        "allowed_changes": [
            {
                "key": "status",
                "old_value": "pending",
                "new_value": "ready-no-compat",
                "old_line": "status=pending",
                "new_line": "status=ready-no-compat",
            }
        ],
        "forbidden_future_goal_item_ids": ["GI002"],
        "forbidden_future_proof_obligation_ids": ["PO002"],
        "forbidden_changes": [{"key": "mode", "reason": "reserved for P0002"}],
    }
    return {
        "patchlet_id": "P0001",
        "work_slice_id": "WS001",
        "selected_goal_item_ids": ["GI001"],
        "selected_proof_obligation_ids": ["PO001"],
        "proof_obligations": proof_obligations,
        "probe_plan": probe_plan,
        "slice_change_boundary": boundary,
    }


def _normalize(raw_items):
    return normalize_semantic_goal_results(raw_items=raw_items, **_ctx())


def test_real_codex_goal_item_result_shorthand_is_accepted_as_raw_claim():
    result = _normalize([{"goal_item": "GI001", "result": "status updated from pending to ready-no-compat without changing reserved keys"}])
    assert result["accepted"] is True
    assert result["accepted_raw_claims"][0]["claim_status"] == "LINKED_PENDING_ORCHESTRATOR_PROOF"


def test_shorthand_goal_item_alias_maps_to_goal_item_id():
    result = _normalize([{"goal": "GI001", "result": "status is ready-no-compat"}])
    assert result["accepted_raw_claims"][0]["goal_item_id"] == "GI001"


def test_shorthand_result_is_linked_to_current_patchlet_goal_and_obligation():
    result = _normalize([{"goal_item_id": "GI001", "result": "status=ready-no-compat"}])
    claim = result["accepted_raw_claims"][0]
    assert claim["proof_obligation_id"] == "PO001"
    assert claim["linkage"] == {
        "goal_item_linked": True,
        "proof_obligation_linked": True,
        "slice_boundary_linked": True,
        "probe_plan_linked": True,
    }


def test_shorthand_result_preserves_raw_worker_output():
    raw = {"goal_item": "GI001", "result": "status updated from pending to ready-no-compat without changing reserved keys"}
    result = _normalize([raw])
    assert result["accepted_raw_claims"][0]["raw_item"] == raw


def test_shorthand_result_does_not_set_passed_true_before_independent_proof():
    result = _normalize([{"goal_item": "GI001", "result": "status=ready-no-compat"}])
    assert "passed" not in result["accepted_raw_claims"][0]
    assert result["proof_not_claimed_here"] is True


def test_shorthand_result_rejects_unknown_goal_item():
    result = _normalize([{"goal_item": "GI999", "result": "status=ready-no-compat"}])
    assert result["accepted"] is False
    assert result["rejected_raw_claims"][0]["error_code"] == "UNLINKED_GOAL_ITEM"


def test_shorthand_result_rejects_goal_item_not_selected_for_current_patchlet():
    result = _normalize([{"goal_item": "GI002", "result": "mode=strict"}])
    assert result["accepted"] is False
    assert result["rejected_raw_claims"][0]["error_code"] == "FUTURE_GOAL_ITEM"


def test_shorthand_result_rejects_future_goal_item():
    result = _normalize([{"goal": "GI002", "result": "mode changed to strict"}])
    assert result["accepted"] is False
    assert result["rejected_raw_claims"][0]["goal_item_id"] == "GI002"


def test_shorthand_result_rejects_vague_result_text():
    result = _normalize([{"goal_item": "GI001", "result": "done"}])
    assert result["accepted"] is False
    assert result["rejected_raw_claims"][0]["error_code"] == "VAGUE_RESULT_TEXT"


def test_shorthand_result_rejects_claim_that_future_slices_were_completed():
    result = _normalize([{"goal_item": "GI001", "result": "all five settings updated"}])
    assert result["accepted"] is False
    assert result["rejected_raw_claims"][0]["error_code"] == "FUTURE_SLICE_CLAIM"


def test_shorthand_result_accepts_text_that_mentions_current_slice_boundary():
    result = _normalize([{"goal_item": "GI001", "result": "status moved from pending to ready-no-compat"}])
    assert result["accepted"] is True
    assert result["accepted_raw_claims"][0]["safety"]["mentions_current_boundary"] is True


def test_shorthand_result_schema_validation_passes_after_normalization():
    result = _normalize([{"goal_item": "GI001", "result": "status=ready-no-compat"}])
    assert result["kind"] == "semantic_goal_results_normalization_result"
    assert result["accepted"] is True
