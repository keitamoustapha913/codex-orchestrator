from __future__ import annotations

from pathlib import Path


DOCS = [
    Path("README.md"),
    Path("IMPLEMENTATION_STATUS.md"),
    Path("docs/general_goal_proof_contract.md"),
    Path("docs/semantic_goal_satisfaction.md"),
    Path("docs/real_codex_smoke.md"),
    Path("docs/runbooks/real_codex_smoke_runbook.md"),
    Path("docs/general_work_decomposition.md"),
]


def _text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOCS)


def test_docs_explain_shorthand_semantic_results_are_worker_claims():
    text = _text()
    assert "shorthand `semantic_goal_results`" in text
    assert "raw worker semantic claim" in text


def test_docs_explain_worker_claims_are_not_proof():
    assert "Worker claims are not proof" in _text()


def test_docs_explain_orchestrator_canonicalizes_after_probe():
    text = _text()
    assert "canonicalizes" in text
    assert "after independent probe rerun" in text


def test_docs_explain_vague_shorthand_rejected():
    text = _text()
    assert "Vague shorthand" in text or "vague shorthand" in text
    assert "probably passes" in text


def test_docs_explain_future_slice_claims_rejected():
    assert "future-slice claims" in _text()


def test_docs_explain_raw_worker_output_preserved():
    assert "raw worker output is preserved" in _text()
