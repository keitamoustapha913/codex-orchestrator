from __future__ import annotations

from pathlib import Path


DOC = Path("docs/multi_patchlet_transaction_graph.md")


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_docs_explain_dependency_graph():
    assert "dependency_graph.json" in _text()


def test_docs_explain_same_file_patchlet_ordering():
    assert "Same-file multi-patchlet groups are ordered by default" in _text()


def test_docs_explain_transaction_group_plan():
    assert "transaction_group_plan.json" in _text()


def test_docs_explain_patchlet_readiness():
    assert "Patchlet readiness requires all dependency patchlets to be accepted" in _text()


def test_docs_explain_stop_partial_apply_with_multi_patchlets():
    assert "Stop and partial apply" in _text()


def test_docs_explain_no_manual_artifact_tampering():
    assert "Manual transaction group fabrication is invalid" in _text()
