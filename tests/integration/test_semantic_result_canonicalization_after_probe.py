from __future__ import annotations

import pytest

from codex_orchestrator.semantic_result_normalization import (
    canonicalize_semantic_goal_results_after_probe,
    normalize_semantic_goal_results,
)


def _proof_obligations():
    return {"obligations": [{"obligation_id": "PO001", "goal_item_ids": ["GI001"], "required": True}]}


def _probe_plan():
    return {"probes": [{"probe_id": "GP001", "obligation_ids": ["PO001"], "expected_observation": {"value": "status=ready-no-compat"}}]}


def _normalization():
    return normalize_semantic_goal_results(
        raw_items=[{"goal_item_id": "GI001", "result": "status=ready-no-compat"}],
        patchlet_id="P0001",
        work_slice_id="WS001",
        selected_goal_item_ids=["GI001"],
        selected_proof_obligation_ids=["PO001"],
        proof_obligations=_proof_obligations(),
        probe_plan=_probe_plan(),
        slice_change_boundary={"allowed_changes": [{"key": "status", "new_value": "ready-no-compat"}]},
    )


def _probe_result(passed=True):
    return {
        "kind": "independent_probe_rerun_result",
        "patchlet_id": "P0001",
        "work_slice_id": "WS001",
        "selected_obligation_ids": ["PO001"],
        "proven_obligation_ids": ["PO001"] if passed else [],
        "failed_obligation_ids": [] if passed else ["PO001"],
        "probe_results": [
            {
                "probe_id": "GP001",
                "obligation_ids": ["PO001"],
                "passed": passed,
                "expected_actual": {"expected": "status=ready-no-compat", "actual": "status=ready-no-compat" if passed else "status=pending"},
            }
        ],
    }


def _canonicalize(passed=True, normalization_result=None):
    return canonicalize_semantic_goal_results_after_probe(
        normalization_result=normalization_result or _normalization(),
        independent_probe_rerun_result=_probe_result(passed),
        proof_obligations=_proof_obligations(),
        probe_plan=_probe_plan(),
    )


def test_independent_probe_success_canonicalizes_shorthand_result_as_passed():
    result = _canonicalize(True)
    assert result["canonical_results"][0]["passed"] is True


def test_independent_probe_failure_canonicalizes_shorthand_result_as_failed():
    result = _canonicalize(False)
    assert result["canonical_results"][0]["passed"] is False


def test_canonical_result_uses_probe_expected_value():
    assert _canonicalize()["canonical_results"][0]["expected_value"] == "status=ready-no-compat"


def test_canonical_result_uses_probe_actual_value():
    assert _canonicalize(False)["canonical_results"][0]["actual_value"] == "status=pending"


def test_canonical_result_links_worker_claim_id():
    assert _canonicalize()["canonical_results"][0]["worker_claim_id"] == "WSC001"


def test_canonical_result_links_goal_item_id():
    assert _canonicalize()["canonical_results"][0]["goal_item_id"] == "GI001"


def test_canonical_result_links_proof_obligation_id():
    assert _canonicalize()["canonical_results"][0]["proof_obligation_id"] == "PO001"


def test_canonical_result_links_patchlet_id_and_work_slice_id():
    row = _canonicalize()["canonical_results"][0]
    assert row["patchlet_id"] == "P0001"
    assert row["work_slice_id"] == "WS001"


def test_canonical_result_preserves_raw_worker_result():
    assert _canonicalize()["canonical_results"][0]["raw_worker_result"] == {"goal_item_id": "GI001", "result": "status=ready-no-compat"}


def test_canonicalization_not_allowed_without_independent_probe_result():
    with pytest.raises(ValueError, match="independent probe"):
        canonicalize_semantic_goal_results_after_probe(
            normalization_result=_normalization(),
            independent_probe_rerun_result={},
            proof_obligations=_proof_obligations(),
            probe_plan=_probe_plan(),
        )


def test_canonicalization_not_allowed_for_unlinked_worker_claim():
    normalization = _normalization()
    normalization["accepted_raw_claims"][0]["claim_status"] = "UNLINKED"
    with pytest.raises(ValueError, match="linked"):
        _canonicalize(normalization_result=normalization)
