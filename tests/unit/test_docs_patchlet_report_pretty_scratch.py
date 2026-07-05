from __future__ import annotations

from pathlib import Path


DOC_PATHS = [
    Path("README.md"),
    Path("IMPLEMENTATION_STATUS.md"),
    Path("docs/real_codex_smoke.md"),
    Path("docs/runbooks/real_codex_smoke_runbook.md"),
    Path("docs/general_work_decomposition.md"),
    Path("docs/goal_progress_and_partial_apply.md"),
    Path("docs/cli.md"),
]


def _docs_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8").lower() for path in DOC_PATHS)


def test_docs_explain_patchlet_prefixed_report_pretty_scratch():
    text = _docs_text()

    assert "patchlet-prefixed report formatting scratch" in text


def test_docs_explain_not_all_pretty_files_allowed():
    text = _docs_text()

    assert "not all pretty files are allowed" in text


def test_docs_explain_not_all_json_files_allowed():
    text = _docs_text()

    assert "not all json files are allowed" in text


def test_docs_explain_product_files_still_rejected():
    text = _docs_text()

    assert "product/runtime files remain rejected" in text
    assert "changed peer product files remain rejected" in text


def test_docs_explain_content_hash_preserved():
    text = _docs_text()

    assert "content and hash" in text


def test_docs_explain_diff_recomputed_after_quarantine():
    text = _docs_text()

    assert "diff is recomputed after quarantine" in text
