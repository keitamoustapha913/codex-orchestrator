from __future__ import annotations

from pathlib import Path


DOCS = [
    Path("README.md"),
    Path("IMPLEMENTATION_STATUS.md"),
    Path("docs/semantic_goal_satisfaction.md"),
    Path("docs/real_codex_smoke.md"),
    Path("docs/runbooks/real_codex_smoke_runbook.md"),
    Path("docs/workflow_lifecycle.md"),
    Path("docs/release.md"),
    Path("docs/Codex_Orchestrator_Step_By_Step_Usage_Guide.md"),
]


def _text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOCS)


def test_docs_say_no_app_py_general_parser() -> None:
    assert "No app.py-specific" in _text() or "no app.py-specific" in _text()


def test_docs_say_no_python_specific_general_parser() -> None:
    text = _text()
    assert "Python-specific" in text
    assert "no longer supports" in text or "not supported" in text


def test_docs_say_model_mediated_goal_interpretation_required() -> None:
    assert "model-mediated goal interpretation" in _text()


def test_docs_say_proof_planning_required() -> None:
    assert "proof planning" in _text()


def test_docs_say_probe_planning_required() -> None:
    assert "probe planning" in _text()


def test_docs_say_decomposition_required() -> None:
    text = _text()
    assert "mandatory decomposition" in text
    assert "patchlet plan" in text


def test_docs_say_no_invariant_fallback() -> None:
    assert "do not fall back to one" in _text() or "do not fall back to" in _text()


def test_docs_say_one_allowed_file_per_patchlet() -> None:
    assert "exactly one allowed product/runtime file" in _text()


def test_docs_say_multiple_patchlets_same_file_allowed() -> None:
    assert "Multiple patchlets may target the same file" in _text()


def test_docs_say_done_requires_master_prompt_satisfaction() -> None:
    assert "`DONE` requires" in _text() and "master-prompt satisfaction" in _text()


def test_docs_say_partial_apply_accepted_checkpoints_only() -> None:
    text = _text()
    assert "applies only accepted checkpoints" in text or "accepted checkpoints" in text
