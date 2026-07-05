from __future__ import annotations

from pathlib import Path


DOCS = [
    Path("README.md"),
    Path("IMPLEMENTATION_STATUS.md"),
    Path("docs/general_goal_proof_contract.md"),
    Path("docs/semantic_goal_satisfaction.md"),
    Path("docs/general_work_decomposition.md"),
    Path("docs/real_codex_smoke.md"),
    Path("docs/runbooks/real_codex_smoke_runbook.md"),
]


def _text() -> str:
    return " ".join("\n".join(path.read_text(encoding="utf-8") for path in DOCS).lower().split())


def test_docs_explain_short_tokens_do_not_match_substrings():
    text = _text()
    assert "short tokens" in text
    assert "do not match as substrings" in text


def test_docs_explain_future_claim_requires_role_combination():
    text = _text()
    assert "future-slice rejection requires" in text
    assert "role-aware" in text


def test_docs_explain_same_file_token_alone_not_future_claim():
    text = _text()
    assert "same-file mention alone" in text
    assert "not a future claim" in text


def test_docs_explain_event_logging_on_example():
    text = _text()
    assert "event_logging=on" in text


def test_docs_explain_worker_text_not_proof():
    assert "worker text is not proof" in _text()
