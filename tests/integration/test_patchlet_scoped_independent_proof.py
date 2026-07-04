from __future__ import annotations

from pathlib import Path

from codex_orchestrator.independent_probe_rerun import select_patchlet_probe_scope
from codex_orchestrator.goal_coverage import evaluate_goal_coverage_gate


def _proof_obligations() -> dict:
    return {
        "workflow_id": "WF",
        "run_id": "R0001",
        "master_prompt_sha256": "b" * 64,
        "obligations": [
            {"obligation_id": f"PO00{i}", "goal_item_ids": [f"GI00{i}"], "required": True}
            for i in range(1, 6)
        ],
    }


def _probe_plan() -> dict:
    return {
        "probes": [
            {
                "probe_id": f"GP00{i}",
                "obligation_ids": [f"PO00{i}"],
                "rerunnable_by_orchestrator": True,
                "expected_observation": {"type": "artifact_exists", "path": f"proof-{i}.txt"},
            }
            for i in range(1, 6)
        ]
    }


def _patchlet() -> dict:
    return {"patchlet_id": "P0001", "work_slice_id": "WS001", "proof_obligation_ids": ["PO001"], "goal_item_ids": ["GI001"]}


def test_patchlet_independent_rerun_runs_only_current_patchlet_obligations():
    scope = select_patchlet_probe_scope(proof_obligations=_proof_obligations(), probe_plan=_probe_plan(), patchlet=_patchlet())
    assert scope["selected_obligation_ids"] == ["PO001"]
    assert [probe["probe_id"] for probe in scope["selected_probes"]] == ["GP001"]


def test_patchlet_independent_rerun_does_not_run_future_obligations():
    scope = select_patchlet_probe_scope(proof_obligations=_proof_obligations(), probe_plan=_probe_plan(), patchlet=_patchlet())
    assert scope["not_selected_future_obligation_ids"] == ["PO002", "PO003", "PO004", "PO005"]


def test_p0001_can_pass_po001_while_po002_to_po005_remain_unproven():
    rerun = {
        "accepted": True,
        "scope": "patchlet",
        "selected_obligation_ids": ["PO001"],
        "not_selected_future_obligation_ids": ["PO002", "PO003", "PO004", "PO005"],
        "proven_obligation_ids": ["PO001"],
        "failed_obligation_ids": [],
    }
    result = evaluate_goal_coverage_gate(
        proof_obligations=_proof_obligations(),
        probe_plan=_probe_plan(),
        independent_probe_rerun_result=rerun,
        patchlet_id="P0001",
        attempt_id="P0001_attempt1",
    )
    assert result["accepted_for_patchlet_progress"] is True
    assert result["future_obligation_ids"] == ["PO002", "PO003", "PO004", "PO005"]


def test_future_obligation_failure_does_not_fail_current_patchlet():
    rerun = {
        "accepted": True,
        "scope": "patchlet",
        "selected_obligation_ids": ["PO001"],
        "not_selected_future_obligation_ids": ["PO002", "PO003", "PO004", "PO005"],
        "proven_obligation_ids": ["PO001"],
        "failed_obligation_ids": ["PO004"],
    }
    result = evaluate_goal_coverage_gate(
        proof_obligations=_proof_obligations(),
        probe_plan=_probe_plan(),
        independent_probe_rerun_result=rerun,
        patchlet_id="P0001",
        attempt_id="P0001_attempt1",
    )
    assert result["accepted_for_patchlet_progress"] is True
    assert result["failed_current_obligation_ids"] == []


def test_transaction_or_global_verification_runs_all_required_obligations():
    scope = select_patchlet_probe_scope(
        proof_obligations=_proof_obligations(),
        probe_plan=_probe_plan(),
        patchlet=_patchlet(),
        scope="workflow",
    )
    assert scope["selected_obligation_ids"] == ["PO001", "PO002", "PO003", "PO004", "PO005"]


def test_done_still_requires_all_required_obligations():
    rerun = {"accepted": True, "scope": "patchlet", "selected_obligation_ids": ["PO001"], "proven_obligation_ids": ["PO001"], "failed_obligation_ids": []}
    result = evaluate_goal_coverage_gate(
        proof_obligations=_proof_obligations(),
        probe_plan=_probe_plan(),
        independent_probe_rerun_result=rerun,
        patchlet_id="P0001",
        attempt_id="P0001_attempt1",
    )
    assert result["accepted_for_done"] is False
    assert result["workflow_goal_status_after_patchlet"] == "PARTIALLY_PROVEN"
