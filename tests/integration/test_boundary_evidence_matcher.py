from __future__ import annotations

from codex_orchestrator.boundary_evidence import (
    detect_future_boundary_claim,
    is_vague_worker_claim,
    match_worker_claim_to_current_boundary,
)


def _proof(claim: str = "The accepted state has control.plan containing status=ready.") -> dict:
    return {
        "obligations": [
            {
                "obligation_id": "PO001",
                "goal_item_ids": ["GI001"],
                "claim": claim,
                "target_boundaries": ["control.plan"],
            },
            {
                "obligation_id": "PO002",
                "goal_item_ids": ["GI002"],
                "claim": "The accepted state has rollout.table containing wave=green.",
                "target_boundaries": ["rollout.table"],
            },
        ]
    }


def _probe(value: str = "status=ready") -> dict:
    return {
        "probes": [
            {
                "probe_id": "GP001",
                "obligation_ids": ["PO001"],
                "expected_observation": {"type": "file_contains", "value": value},
            }
        ]
    }


def _match(text: str, **overrides):
    kwargs = {
        "worker_text": text,
        "allowed_product_runtime_file": "control.plan",
        "slice_change_boundary": {
            "boundary_type": "text_key_value_update",
            "allowed_changes": [
                {
                    "key": "status",
                    "old_value": "pending",
                    "new_value": "ready",
                    "old_line": "status=pending",
                    "new_line": "status=ready",
                }
            ],
        },
        "proof_obligations": _proof(),
        "probe_plan": _probe(),
        "selected_proof_obligation_ids": ["PO001"],
        "future_proof_obligation_ids": ["PO002"],
    }
    kwargs.update(overrides)
    return match_worker_claim_to_current_boundary(**kwargs)


def test_key_value_boundary_matches_key_old_new():
    result = _match("status moved from pending to ready")
    assert result["mentions_current_boundary"] is True


def test_key_value_boundary_matches_file_and_new_value():
    result = _match("control.plan now has ready status")
    assert result["mentions_current_boundary"] is True


def test_route_boundary_matches_file_route_and_new_target():
    result = _match(
        "Updated route.map only; /health now routes to ready-health.",
        allowed_product_runtime_file="route.map",
        slice_change_boundary=None,
        proof_obligations=_proof("The accepted state has route.map containing /health -> ready-health."),
        probe_plan=_probe("/health -> ready-health"),
    )
    assert result["mentions_current_boundary"] is True
    assert {row["token"] for row in result["matched_evidence"]} >= {"route.map", "/health", "ready-health"}


def test_route_boundary_matches_route_and_new_target():
    result = _match(
        "/health now routes to ready-health",
        allowed_product_runtime_file="route.map",
        slice_change_boundary=None,
        proof_obligations=_proof("The accepted state has route.map containing /health -> ready-health."),
        probe_plan=_probe("/health -> ready-health"),
    )
    assert result["mentions_current_boundary"] is True


def test_section_boundary_matches_section_key_new_value():
    result = _match(
        "runtime mode is now strict in policy.bundle",
        allowed_product_runtime_file="policy.bundle",
        slice_change_boundary={
            "boundary_type": "section_key_value_update",
            "section": "[runtime]",
            "allowed_changes": [{"section": "[runtime]", "key": "mode", "old_value": "permissive", "new_value": "strict"}],
        },
        proof_obligations=_proof("The accepted state has policy.bundle [runtime] mode strict."),
        probe_plan=_probe("mode=strict"),
    )
    assert result["mentions_current_boundary"] is True


def test_exact_line_boundary_matches_new_line():
    result = _match(
        "the exact line owner: platform is now present",
        slice_change_boundary={
            "boundary_type": "line_exact_change",
            "allowed_changes": [{"old_line": "owner: unknown", "new_line": "owner: platform"}],
        },
        proof_obligations=_proof("The accepted state contains owner: platform."),
        probe_plan=_probe("owner: platform"),
    )
    assert result["mentions_current_boundary"] is True


def test_probe_expected_observation_counts_as_boundary_evidence():
    result = _match("control.plan contains status=ready")
    assert result["mentions_current_boundary"] is True


def test_future_boundary_mention_detected():
    result = _match("rollout.table wave=green is also complete")
    assert result["mentions_future_boundary"] is True


def test_future_boundary_completion_claim_rejected():
    assert detect_future_boundary_claim(
        "rollout.table wave=green is also complete",
        proof_obligations=_proof(),
        future_proof_obligation_ids=["PO002"],
        slice_change_boundary={"forbidden_changes": [{"key": "wave", "new_value": "green"}]},
    ) is True


def test_future_value_word_without_boundary_combo_is_not_future_claim():
    assert detect_future_boundary_claim(
        "Changed only the allowed key with red, green, and negative-control probes.",
        proof_obligations=_proof(),
        future_proof_obligation_ids=["PO002"],
        slice_change_boundary={"forbidden_changes": [{"key": "wave", "new_value": "green"}]},
    ) is False


def test_vague_claim_rejected():
    assert is_vague_worker_claim("fixed") is True
    assert _match("fixed")["vague"] is True


def test_random_text_without_boundary_rejected():
    assert _match("The requested work has been handled safely.")["mentions_current_boundary"] is False


def test_matcher_is_repo_agnostic_with_non_scenario_fixture():
    result = _match(
        "verify_result.log confirms control.plan changes the north lane to open",
        allowed_product_runtime_file="control.plan",
        slice_change_boundary={
            "boundary_type": "line_exact_change",
            "allowed_changes": [{"old_line": "north lane: closed", "new_line": "north lane: open"}],
        },
        proof_obligations=_proof("The accepted state has control.plan containing north lane: open."),
        probe_plan=_probe("north lane: open"),
    )
    assert result["mentions_current_boundary"] is True


def _same_file_policy_match(text: str):
    return _match(
        text,
        allowed_product_runtime_file="policy.bundle",
        slice_change_boundary={
            "boundary_type": "text_key_value_update",
            "allowed_changes": [
                {
                    "key": "mode",
                    "old_value": "permissive",
                    "new_value": "strict",
                    "old_line": "mode=permissive",
                    "new_line": "mode=strict",
                }
            ],
            "forbidden_changes": [
                {"key": "event_logging", "new_value": "on"},
                {"key": "default", "new_value": "deny"},
            ],
        },
        proof_obligations={
            "obligations": [
                {
                    "obligation_id": "PO002",
                    "goal_item_ids": ["GI002"],
                    "claim": "The accepted state has policy.bundle containing mode=strict.",
                    "target_boundaries": ["policy.bundle"],
                },
                {
                    "obligation_id": "PO004",
                    "goal_item_ids": ["GI004"],
                    "claim": "The accepted state has policy.bundle containing event_logging=on.",
                    "target_boundaries": ["policy.bundle"],
                },
            ]
        },
        probe_plan={
            "probes": [
                {
                    "probe_id": "GP002",
                    "obligation_ids": ["PO002"],
                    "expected_observation": {"value": "mode=strict"},
                }
            ]
        },
        selected_proof_obligation_ids=["PO002"],
        future_proof_obligation_ids=["PO004"],
    )


def test_short_future_value_on_does_not_match_inside_boundary():
    result = _same_file_policy_match("policy.bundle boundary mode=strict was updated")
    assert result["mentions_current_boundary"] is True
    assert result["mentions_future_boundary"] is False


def test_short_future_value_on_does_not_match_inside_control():
    result = _same_file_policy_match("mode=strict proof used a negative control")
    assert result["mentions_current_boundary"] is True
    assert result["mentions_future_boundary"] is False


def test_short_future_value_on_does_not_match_inside_now():
    result = _same_file_policy_match("mode=strict is now present")
    assert result["mentions_current_boundary"] is True
    assert result["mentions_future_boundary"] is False


def test_short_future_value_on_requires_standalone_token_or_exact_line():
    assert _same_file_policy_match("event_logging is on and complete")["mentions_future_boundary"] is True
    assert _same_file_policy_match("event_logging=on is complete")["mentions_future_boundary"] is True


def test_future_boundary_requires_key_and_value_not_value_alone():
    result = _same_file_policy_match("mode=strict is complete and on")
    assert result["mentions_current_boundary"] is True
    assert result["mentions_future_boundary"] is False


def test_future_boundary_requires_exact_line_or_role_combination():
    assert _same_file_policy_match("event_logging=on is also complete")["mentions_future_boundary"] is True


def test_same_file_token_alone_does_not_trigger_future_claim():
    result = _same_file_policy_match("policy.bundle mode=strict is complete")
    assert result["mentions_current_boundary"] is True
    assert result["mentions_future_boundary"] is False


def test_current_mode_strict_claim_not_rejected_by_future_event_logging_on():
    result = _same_file_policy_match(
        "The allowed boundary in policy.bundle was updated from mode=permissive to mode=strict, and the strict-mode probe now passes while the permissive negative control fails."
    )
    assert result["mentions_current_boundary"] is True
    assert result["mentions_future_boundary"] is False


def test_future_event_logging_on_claim_is_rejected():
    result = _same_file_policy_match("policy.bundle event_logging is on and complete")
    assert result["mentions_future_boundary"] is True


def test_future_exact_line_event_logging_on_is_rejected():
    result = _same_file_policy_match("policy.bundle event_logging=on is also complete")
    assert result["mentions_future_boundary"] is True


def test_vague_claim_fixed_still_rejected():
    assert is_vague_worker_claim("fixed") is True


def test_probe_local_scenario3_claim_is_accepted():
    result = _same_file_policy_match(
        "The allowed boundary in policy.bundle was updated from mode=permissive to mode=strict, and the strict-mode probe now passes while the permissive negative control fails."
    )
    assert result["mentions_current_boundary"] is True
    assert result["mentions_future_boundary"] is False
