from __future__ import annotations

from codex_orchestrator.goal_coverage import evaluate_goal_coverage_gate


def _obligations() -> dict:
    return {
        "workflow_id": "WF",
        "run_id": "R0001",
        "master_prompt_sha256": "c" * 64,
        "obligations": [
            {"obligation_id": f"PO00{i}", "goal_item_ids": [f"GI00{i}"], "required": True}
            for i in range(1, 4)
        ],
    }


def _rerun() -> dict:
    return {
        "accepted": True,
        "scope": "patchlet",
        "selected_obligation_ids": ["PO001"],
        "not_selected_future_obligation_ids": ["PO002", "PO003"],
        "proven_obligation_ids": ["PO001"],
        "failed_obligation_ids": [],
    }


def _result() -> dict:
    return evaluate_goal_coverage_gate(
        proof_obligations=_obligations(),
        probe_plan={"probes": []},
        independent_probe_rerun_result=_rerun(),
        patchlet_id="P0001",
        attempt_id="P0001_attempt1",
    )


def test_partial_goal_coverage_accepts_patchlet_when_current_obligations_pass():
    assert _result()["accepted_for_patchlet_progress"] is True


def test_partial_goal_coverage_blocks_done():
    assert _result()["accepted_for_done"] is False


def test_partial_goal_coverage_updates_goal_progress_as_partially_proven():
    assert _result()["workflow_goal_status_after_patchlet"] == "PARTIALLY_PROVEN"


def test_partial_goal_coverage_keeps_future_obligations_unproven():
    assert _result()["future_obligation_ids"] == ["PO002", "PO003"]


def test_partial_goal_coverage_does_not_mark_workflow_failed():
    assert _result()["failure_signature"] is None


def test_partial_goal_coverage_allows_next_dependency_ready_patchlet():
    result = _result()
    assert result["patchlet_coverage_status"] == "PATCHLET_PARTIAL_ACCEPTED"
