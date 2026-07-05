from __future__ import annotations

from pathlib import Path


DOCS = [
    Path("README.md"),
    Path("IMPLEMENTATION_STATUS.md"),
    Path("docs/general_work_decomposition.md"),
    Path("docs/real_codex_smoke.md"),
    Path("docs/runbooks/real_codex_smoke_runbook.md"),
    Path("docs/goal_progress_and_partial_apply.md"),
    Path("docs/cli.md"),
]


def _text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOCS)


def test_docs_explain_scratch_artifacts_quarantined():
    text = _text()
    assert "scratch artifacts" in text
    assert "quarantined" in text


def test_docs_explain_quarantine_not_silent_delete():
    assert "not silently deleted" in _text()


def test_docs_explain_product_files_still_rejected():
    text = _text()
    assert "Unknown root product" in text or "unknown root product" in text
    assert "rejected" in text


def test_docs_explain_one_file_rule_preserved():
    assert "one-file rule" in _text()


def test_docs_explain_slice_boundary_preserved():
    assert "slice boundary" in _text() or "slice-boundary" in _text()


def test_docs_explain_quarantine_metadata():
    text = _text()
    assert "scratch_artifact_quarantine_result.json" in text
    assert "sha256" in text
