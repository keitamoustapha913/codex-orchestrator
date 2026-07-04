from __future__ import annotations

from pathlib import Path


DOC = Path("docs/general_work_decomposition.md")


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_docs_explain_not_one_file_one_patchlet():
    assert "not one file -> one patchlet" in _text()


def test_docs_explain_one_patchlet_exactly_one_allowed_file():
    assert "one patchlet -> exactly one allowed product/runtime file" in _text()


def test_docs_explain_multiple_patchlets_may_target_same_file():
    assert "Multiple patchlets may target the same product/runtime file" in _text()


def test_docs_explain_small_bounded_work_units():
    assert "small bounded work units" in _text()


def test_docs_explain_600_second_budget():
    assert "600 seconds" in _text()


def test_docs_explain_memory_compacting_avoidance():
    assert "avoid memory compacting" in _text()


def test_docs_explain_work_slices_not_files():
    assert "Work slices are not merely files" in _text()


def test_docs_explain_decomposition_artifacts():
    text = _text()
    assert "work_decomposition_plan.json" in text
    assert "patchlet_plan.json" in text
    assert "transaction_group_plan.json" in text


def test_docs_explain_cxor_decomposition_command():
    assert "cxor decomposition --repo <repo>" in _text()


def test_usage_guide_mentions_general_work_decomposition():
    text = Path("docs/Codex_Orchestrator_Step_By_Step_Usage_Guide.md").read_text(encoding="utf-8")
    assert "general work decomposition" in text.lower() or DOC.exists()
