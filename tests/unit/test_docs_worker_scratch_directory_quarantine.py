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


def test_docs_explain_worker_scratch_directory_quarantine():
    text = _text()
    assert "worker scratch directory" in text
    assert "Only role-shaped untracked worker scratch directories are eligible for" in text
    assert "quarantine." in text


def test_docs_explain_not_all_scratch_dirs_allowed():
    text = _text()
    assert "Not all directories are allowed." in text
    assert "Not all scratch directories are allowed." in text


def test_docs_explain_untracked_only():
    text = _text()
    assert "untracked worker scratch directories" in text


def test_docs_explain_executable_content_rejected():
    text = _text()
    assert "Executable scratch content is rejected." in text


def test_docs_explain_tracked_worker_scratch_rejected():
    text = _text()
    assert "Tracked `worker_scratch` content is rejected." in text


def test_docs_explain_changed_paths_recomputed_after_quarantine():
    text = _text()
    assert "changed paths are recomputed after quarantine" in text


def test_docs_explain_manifest_preserves_hashes():
    text = _text()
    assert "Directory quarantine preserves hashes and metadata" in text
