from __future__ import annotations

import pytest

from codex_orchestrator.patchlet_probe_mapping import (
    MISSING_PATCHLET_PROBE_MAPPING,
    PatchletProbeMappingError,
    resolve_patchlet_probe_ids,
)
from codex_orchestrator.worker_evidence import render_worker_evidence_prompt_contract


def _patchlet(**values):
    return {
        "patchlet_id": "P0001",
        "goal_item_ids": ["GI001"],
        "proof_obligation_ids": ["PO001"],
        **values,
    }


def test_explicit_empty_probe_ids_safe_fail_structured():
    with pytest.raises(PatchletProbeMappingError) as raised:
        resolve_patchlet_probe_ids(_patchlet(probe_ids=[]))
    assert raised.value.details == {
        "failure_signature": MISSING_PATCHLET_PROBE_MAPPING,
        "patchlet_id": "P0001",
        "goal_item_ids": ["GI001"],
        "proof_obligation_ids": ["PO001"],
        "supplied_probe_ids": [],
        "derived_probe_candidates": [],
        "reason": "probe_ids was explicitly supplied as empty or invalid",
    }


def test_absent_probe_ids_derives_exactly_one_to_one_mapping():
    assert resolve_patchlet_probe_ids(
        _patchlet(),
        probe_plan={"probes": [{"probe_id": "GP001", "obligation_ids": ["PO001"]}]},
    ) == ["GP001"]


@pytest.mark.parametrize(
    "probe_plan, reason",
    [
        ({"probes": []}, "resolves to 0 probes"),
        (
            {"probes": [
                {"probe_id": "GP001", "obligation_ids": ["PO001"]},
                {"probe_id": "GP002", "obligation_ids": ["PO001"]},
            ]},
            "resolves to 2 probes",
        ),
    ],
)
def test_absent_probe_ids_missing_or_ambiguous_safe_fails(probe_plan, reason):
    with pytest.raises(PatchletProbeMappingError, match=reason):
        resolve_patchlet_probe_ids(_patchlet(), probe_plan=probe_plan)


def test_no_global_probe_fallback():
    with pytest.raises(PatchletProbeMappingError):
        resolve_patchlet_probe_ids(_patchlet(), probe_plan={"probes": [{"probe_id": "UNRELATED", "obligation_ids": ["PO999"]}]})


def test_explicit_valid_probe_ids_compile_mapping_normally():
    assert resolve_patchlet_probe_ids(_patchlet(probe_ids=["GP001"])) == ["GP001"]


def test_shared_prompt_contract_is_deterministic_and_separates_roots():
    patchlet = _patchlet(probe_ids=["GP001"])
    first = render_worker_evidence_prompt_contract(
        patchlet=patchlet,
        attempt_id="run_001",
        evidence_dir="$CXOR_WORKER_EVIDENCE_DIR",
        scratch_dir="$CXOR_WORKER_SCRATCH_DIR",
    )
    second = render_worker_evidence_prompt_contract(
        patchlet=patchlet,
        attempt_id="run_001",
        evidence_dir="$CXOR_WORKER_EVIDENCE_DIR",
        scratch_dir="$CXOR_WORKER_SCRATCH_DIR",
    )
    assert first == second
    assert "durable probe artifacts" in first
    assert "$CXOR_WORKER_EVIDENCE_DIR/GP001/run_001/" in first
    assert "$CXOR_WORKER_SCRATCH_DIR" in first
    assert "Product edits must be limited to the assigned product file." in first
    assert ".artifacts/probes" in first
    assert "Do not create or use checkout-local `.artifacts/probes/`" in first
