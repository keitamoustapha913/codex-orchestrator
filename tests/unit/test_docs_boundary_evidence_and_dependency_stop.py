from __future__ import annotations

from pathlib import Path


DOCS = [
    Path("README.md"),
    Path("IMPLEMENTATION_STATUS.md"),
    Path("docs/general_goal_proof_contract.md"),
    Path("docs/semantic_goal_satisfaction.md"),
    Path("docs/general_work_decomposition.md"),
    Path("docs/multi_patchlet_transaction_graph.md"),
    Path("docs/real_codex_smoke.md"),
    Path("docs/runbooks/real_codex_smoke_runbook.md"),
]


def _text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOCS).lower()


def test_docs_explain_boundary_type_aware_matching():
    assert "boundary-type aware" in _text()


def test_docs_explain_route_style_claims():
    text = _text()
    assert "route-style" in text
    assert "route/path" in text


def test_docs_explain_worker_claim_not_proof():
    assert "worker text is still not proof" in _text() or "worker claim is still not proof" in _text()


def test_docs_explain_future_slice_claim_rejected():
    assert "future-slice claims remain rejected" in _text()


def test_docs_explain_failed_dependency_blocks_downstream():
    assert "downstream patchlets do not run after failed dependencies" in _text()


def test_docs_explain_scheduler_requires_accepted_dependencies():
    assert "scheduler readiness requires accepted dependencies" in _text()
