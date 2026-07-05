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


def _route_ctx():
    return {
        "patchlet_id": "P0001",
        "work_slice_id": "WS001",
        "selected_goal_item_ids": ["GI001"],
        "selected_proof_obligation_ids": ["PO001"],
        "allowed_product_runtime_file": "gateway.routes",
        "proof_obligations": {
            "obligations": [
                {
                    "obligation_id": "PO001",
                    "goal_item_ids": ["GI001"],
                    "required": True,
                    "claim": "The accepted integration state has gateway.routes containing /health -> ready-health.",
                    "target_boundaries": ["gateway.routes"],
                },
                {
                    "obligation_id": "PO002",
                    "goal_item_ids": ["GI002"],
                    "required": True,
                    "claim": "The accepted integration state has policy.rules containing default_action=deny.",
                    "target_boundaries": ["policy.rules"],
                },
            ]
        },
        "probe_plan": {
            "probes": [
                {
                    "probe_id": "GP001",
                    "obligation_ids": ["PO001"],
                    "expected_observation": {"type": "file_contains", "value": "/health -> ready-health"},
                }
            ]
        },
        "slice_change_boundary": None,
    }


def _normalize_route(raw_items):
    return normalize_semantic_goal_results(raw_items=raw_items, **_route_ctx())


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


def test_route_style_shorthand_mentions_current_boundary_by_file_route_and_target():
    result = _normalize_route([
        {"goal_item": "GI001", "result": "Updated gateway.routes only; /health now routes to ready-health."}
    ])
    assert result["accepted"] is True
    match = result["accepted_raw_claims"][0]["boundary_evidence_match"]
    assert {row["token"] for row in match["matched_evidence"]} >= {"gateway.routes", "/health", "ready-health"}


def test_route_style_shorthand_mentions_current_boundary_by_route_and_target_without_exact_line():
    result = _normalize_route([
        {"goal_item": "GI001", "result": "/health now routes to ready-health without touching other files."}
    ])
    assert result["accepted"] is True


def test_route_style_shorthand_preserves_raw_worker_output():
    raw = {"goal_item": "GI001", "result": "Updated gateway.routes only; /health now routes to ready-health."}
    result = _normalize_route([raw])
    assert result["accepted_raw_claims"][0]["raw_item"] == raw


def test_route_style_shorthand_rejects_vague_route_claim():
    result = _normalize_route([{"goal_item": "GI001", "result": "fixed"}])
    assert result["accepted"] is False
    assert result["rejected_raw_claims"][0]["error_code"] == "VAGUE_RESULT_TEXT"


def test_route_style_shorthand_rejects_future_file_claims():
    result = _normalize_route([
        {"goal_item": "GI001", "result": "gateway.routes is done and policy.rules default_action=deny is also complete."}
    ])
    assert result["accepted"] is False
    assert result["rejected_raw_claims"][0]["error_code"] == "FUTURE_SLICE_CLAIM"


def test_route_style_shorthand_rejects_future_route_claims():
    ctx = _route_ctx()
    ctx["proof_obligations"]["obligations"].append(
        {
            "obligation_id": "PO003",
            "goal_item_ids": ["GI003"],
            "required": True,
            "claim": "The accepted state has gateway.routes containing /api -> ready-api.",
            "target_boundaries": ["gateway.routes"],
        }
    )
    ctx["slice_change_boundary"] = {"forbidden_future_proof_obligation_ids": ["PO003"]}
    result = normalize_semantic_goal_results(
        raw_items=[{"goal_item": "GI001", "result": "/health routes to ready-health and /api -> ready-api is complete."}],
        **ctx,
    )
    assert result["accepted"] is False
    assert result["rejected_raw_claims"][0]["error_code"] == "FUTURE_SLICE_CLAIM"


def test_section_style_shorthand_mentions_current_boundary():
    ctx = _ctx()
    ctx["allowed_product_runtime_file"] = "policy.bundle"
    ctx["slice_change_boundary"] = {
        "boundary_type": "section_key_value_update",
        "section": "[runtime]",
        "allowed_changes": [{"section": "[runtime]", "key": "mode", "old_value": "permissive", "new_value": "strict"}],
    }
    ctx["proof_obligations"]["obligations"][0]["claim"] = "The accepted state has policy.bundle runtime mode strict."
    ctx["probe_plan"]["probes"][0]["expected_observation"]["value"] = "mode=strict"
    result = normalize_semantic_goal_results(
        raw_items=[{"goal_item": "GI001", "result": "runtime mode is now strict in policy.bundle"}],
        **ctx,
    )
    assert result["accepted"] is True


def test_line_exact_shorthand_mentions_current_boundary():
    ctx = _ctx()
    ctx["allowed_product_runtime_file"] = "ownership.record"
    ctx["slice_change_boundary"] = {
        "boundary_type": "line_exact_change",
        "allowed_changes": [{"old_line": "owner: unknown", "new_line": "owner: platform"}],
    }
    ctx["proof_obligations"]["obligations"][0]["claim"] = "The accepted state contains owner: platform."
    ctx["probe_plan"]["probes"][0]["expected_observation"]["value"] = "owner: platform"
    result = normalize_semantic_goal_results(
        raw_items=[{"goal_item": "GI001", "result": "owner: platform is present in ownership.record"}],
        **ctx,
    )
    assert result["accepted"] is True


def test_boundary_matcher_uses_patchlet_plan_not_hardcoded_filename():
    result = normalize_semantic_goal_results(
        raw_items=[{"goal_item": "GI001", "result": "control.plan has lane=open now"}],
        patchlet_id="P0101",
        work_slice_id="WS101",
        selected_goal_item_ids=["GI001"],
        selected_proof_obligation_ids=["PO001"],
        allowed_product_runtime_file="control.plan",
        proof_obligations={"obligations": [{"obligation_id": "PO001", "goal_item_ids": ["GI001"], "claim": "control.plan contains lane=open"}]},
        probe_plan={"probes": [{"probe_id": "GP001", "obligation_ids": ["PO001"], "expected_observation": {"value": "lane=open"}}]},
        slice_change_boundary=None,
    )
    assert result["accepted"] is True


def test_boundary_matcher_second_fixture_different_names_and_extensions():
    result = normalize_semantic_goal_results(
        raw_items=[{"goal_item": "GI001", "result": "rollout.table now contains ring alpha"}],
        patchlet_id="P0101",
        work_slice_id="WS101",
        selected_goal_item_ids=["GI001"],
        selected_proof_obligation_ids=["PO001"],
        allowed_product_runtime_file="rollout.table",
        proof_obligations={"obligations": [{"obligation_id": "PO001", "goal_item_ids": ["GI001"], "claim": "rollout.table contains ring alpha"}]},
        probe_plan={"probes": [{"probe_id": "GP001", "obligation_ids": ["PO001"], "expected_observation": {"value": "ring alpha"}}]},
        slice_change_boundary=None,
    )
    assert result["accepted"] is True


def _scenario3_p0002_ctx():
    return {
        "patchlet_id": "P0002",
        "work_slice_id": "WS002",
        "selected_goal_item_ids": ["GI002"],
        "selected_proof_obligation_ids": ["PO002"],
        "allowed_product_runtime_file": "policy.bundle",
        "proof_obligations": {
            "obligations": [
                {
                    "obligation_id": "PO002",
                    "goal_item_ids": ["GI002"],
                    "claim": "The accepted integration state has policy.bundle containing mode=strict.",
                    "target_boundaries": ["policy.bundle"],
                    "required": True,
                },
                {
                    "obligation_id": "PO004",
                    "goal_item_ids": ["GI004"],
                    "claim": "The accepted integration state has policy.bundle containing event_logging=on.",
                    "target_boundaries": ["policy.bundle"],
                    "required": True,
                },
            ]
        },
        "probe_plan": {
            "probes": [
                {
                    "probe_id": "GP002",
                    "obligation_ids": ["PO002"],
                    "expected_observation": {"value": "mode=strict"},
                }
            ]
        },
        "slice_change_boundary": {
            "boundary_type": "text_key_value_update",
            "allowed_product_runtime_file": "policy.bundle",
            "allowed_changes": [
                {
                    "key": "mode",
                    "old_value": "permissive",
                    "new_value": "strict",
                    "old_line": "mode=permissive",
                    "new_line": "mode=strict",
                }
            ],
            "forbidden_future_goal_item_ids": ["GI004"],
            "forbidden_future_proof_obligation_ids": ["PO004"],
            "forbidden_changes": [{"key": "event_logging", "new_value": "on"}],
        },
    }


def _normalize_scenario3(text: str):
    return normalize_semantic_goal_results(
        raw_items=[{"goal_item": "GI002", "result": text}],
        **_scenario3_p0002_ctx(),
    )


SCENARIO3_STRICT_MODE_CLAIM = (
    "The allowed boundary in policy.bundle was updated from mode=permissive "
    "to mode=strict, and the strict-mode probe now passes while the permissive "
    "negative control fails."
)


def test_scenario3_p0002_strict_mode_claim_is_accepted():
    result = _normalize_scenario3(SCENARIO3_STRICT_MODE_CLAIM)
    assert result["accepted"] is True


def test_scenario3_p0002_strict_mode_claim_preserves_raw_output():
    result = _normalize_scenario3(SCENARIO3_STRICT_MODE_CLAIM)
    assert result["accepted_raw_claims"][0]["raw_result_text"] == SCENARIO3_STRICT_MODE_CLAIM


def test_scenario3_p0002_strict_mode_claim_mentions_current_boundary():
    result = _normalize_scenario3(SCENARIO3_STRICT_MODE_CLAIM)
    assert result["accepted_raw_claims"][0]["boundary_evidence_match"]["mentions_current_boundary"] is True


def test_scenario3_p0002_strict_mode_claim_does_not_mention_future_boundary():
    result = _normalize_scenario3(SCENARIO3_STRICT_MODE_CLAIM)
    assert result["accepted_raw_claims"][0]["boundary_evidence_match"]["mentions_future_boundary"] is False


def test_scenario3_future_event_logging_claim_is_rejected():
    result = _normalize_scenario3("policy.bundle event_logging=on is also complete")
    assert result["accepted"] is False
    assert result["rejected_raw_claims"][0]["error_code"] == "FUTURE_SLICE_CLAIM"


def test_scenario3_vague_fixed_claim_is_rejected():
    result = _normalize_scenario3("fixed")
    assert result["accepted"] is False
    assert result["rejected_raw_claims"][0]["error_code"] == "VAGUE_RESULT_TEXT"


def test_short_future_value_on_regression_in_ingestion_path():
    result = _normalize_scenario3("policy.bundle mode=strict now passes the negative control")
    assert result["accepted"] is True
