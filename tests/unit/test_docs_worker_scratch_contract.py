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


def test_docs_explain_disposable_worker_sandbox():
    assert "disposable sandbox" in _text()


def test_docs_explain_all_non_allowlisted_outputs_are_debris():
    text = _text().lower()
    assert "all in-sandbox" in text
    assert "non-allowlisted outputs are sandbox debris" in text


def test_docs_explain_debris_is_inventoried():
    assert "inventoried" in _text()


def test_docs_explain_debris_is_discarded():
    assert "discarded" in _text()


def test_docs_explain_names_do_not_grant_authority():
    text = _text()
    assert "filenames" in text or "name" in text
    assert "authority" in text or "authoritative" in text


def test_docs_explain_only_allowlisted_product_files_are_reconstructed():
    text = _text().lower()
    assert "only valid allowlisted" in text or "only allowlisted" in text
    assert "reconstruct" in text


def test_docs_explain_containment_remains_blocking():
    assert "containment escape remains blocking" in _text()
