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


def test_docs_explain_worker_scratch_directory():
    assert "worker scratch directory" in _text()


def test_docs_explain_no_root_scratch_instruction():
    assert "not to write root scratch" in _text() or "Do not write scratch/check/validation files" in _text()


def test_docs_explain_root_scratch_sweep():
    assert "root scratch sweep" in _text()


def test_docs_explain_role_based_quarantine():
    assert "role-based" in _text()


def test_docs_explain_random_txt_not_automatically_allowed():
    text = _text()
    assert "random root .txt" in text or "random .txt" in text
    assert "not automatically allowed" in text


def test_docs_explain_product_files_still_rejected():
    text = _text()
    assert "product/runtime files" in text
    assert "rejected" in text


def test_docs_explain_diff_recomputed_after_quarantine():
    assert "diff is recomputed after quarantine" in _text()
