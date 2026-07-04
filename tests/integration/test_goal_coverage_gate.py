from __future__ import annotations

from codex_orchestrator.goal_coverage import evaluate_goal_coverage_gate
from codex_orchestrator.validators.schema_validator import validate_json


def _obligations():
    return {"workflow_id": "WF", "run_id": "R0001", "master_prompt_sha256": "a" * 64, "obligations": [{"obligation_id": "PO001", "goal_item_ids": ["GI001"], "required": True}]}


def _plan():
    return {"probes": [{"probe_id": "GP001", "obligation_ids": ["PO001"]}]}


def _rerun(*, accepted=True, proven=None, failed=None):
    return {"accepted": accepted, "proven_obligation_ids": proven or [], "failed_obligation_ids": failed or []}


def test_goal_coverage_passes_when_required_obligation_proven():
    result = evaluate_goal_coverage_gate(proof_obligations=_obligations(), probe_plan=_plan(), independent_probe_rerun_result=_rerun(proven=["PO001"]), patchlet_id="P0001", attempt_id="P0001_attempt1")
    assert result["accepted"] is True


def test_goal_coverage_fails_when_required_obligation_unproven():
    result = evaluate_goal_coverage_gate(proof_obligations=_obligations(), probe_plan=_plan(), independent_probe_rerun_result=_rerun(accepted=False), patchlet_id="P0001", attempt_id="P0001_attempt1")
    assert result["accepted"] is False


def test_goal_coverage_fails_when_probe_failed():
    result = evaluate_goal_coverage_gate(proof_obligations=_obligations(), probe_plan=_plan(), independent_probe_rerun_result=_rerun(accepted=False, failed=["PO001"]), patchlet_id="P0001", attempt_id="P0001_attempt1")
    assert result["coverage_status"] == "FAILED"


def test_goal_coverage_blocks_missing_goal_item_coverage():
    result = evaluate_goal_coverage_gate(proof_obligations=_obligations(), probe_plan=_plan(), independent_probe_rerun_result=_rerun(proven=[]), patchlet_id="P0001", attempt_id="P0001_attempt1")
    assert result["uncovered_goal_item_ids"] == ["GI001"]


def test_verified_no_change_requires_goal_coverage_pass():
    assert evaluate_goal_coverage_gate(proof_obligations=_obligations(), probe_plan=_plan(), independent_probe_rerun_result=_rerun(proven=["PO001"]), patchlet_id="P0001", attempt_id="P0001_attempt1")["accepted"] is True


def test_complete_requires_goal_coverage_pass():
    test_verified_no_change_requires_goal_coverage_pass()


def test_goal_coverage_result_schema_validates():
    result = evaluate_goal_coverage_gate(proof_obligations=_obligations(), probe_plan=_plan(), independent_probe_rerun_result=_rerun(proven=["PO001"]), patchlet_id="P0001", attempt_id="P0001_attempt1")
    assert validate_json(result, "goal_coverage_gate_result.schema.json") == []


def test_goal_coverage_failure_routes_to_repair():
    result = evaluate_goal_coverage_gate(proof_obligations=_obligations(), probe_plan=_plan(), independent_probe_rerun_result=_rerun(accepted=False, failed=["PO001"]), patchlet_id="P0001", attempt_id="P0001_attempt1")
    assert result["failure_signature"] == "goal_coverage_failed"


def test_goal_coverage_partial_records_progress_but_not_done():
    obligations = _obligations()
    obligations["obligations"].append({"obligation_id": "PO002", "goal_item_ids": ["GI002"], "required": True})
    result = evaluate_goal_coverage_gate(proof_obligations=obligations, probe_plan=_plan(), independent_probe_rerun_result=_rerun(proven=["PO001"]), patchlet_id="P0001", attempt_id="P0001_attempt1")
    assert result["coverage_status"] == "PARTIAL"
    assert result["accepted_for_patchlet_progress"] is True
    assert result["accepted_for_done"] is False


def test_goal_coverage_links_independent_rerun_evidence():
    result = evaluate_goal_coverage_gate(proof_obligations=_obligations(), probe_plan=_plan(), independent_probe_rerun_result=_rerun(proven=["PO001"]), patchlet_id="P0001", attempt_id="P0001_attempt1")
    assert "independent_probe_rerun_result.json" in result["evidence_paths"][0]
