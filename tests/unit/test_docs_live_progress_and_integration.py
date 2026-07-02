from __future__ import annotations

from pathlib import Path


DOC_PATHS = [
    Path("README.md"),
    Path("docs/cli.md"),
    Path("docs/worktrees.md"),
    Path("docs/autonomous_loop.md"),
    Path("docs/real_codex_smoke.md"),
    Path("docs/runbooks/real_codex_smoke_runbook.md"),
    Path("IMPLEMENTATION_STATUS.md"),
]


def _docs_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOC_PATHS if path.exists())


def test_docs_explain_live_codex_progress():
    text = _docs_text()
    assert "live progress" in text.lower()
    assert "[cxor:" in text


def test_docs_explain_live_progress_can_be_disabled():
    text = _docs_text()
    assert "CXOR_LIVE_CODEX_PROGRESS=0" in text


def test_docs_explain_progress_jsonl_remains_durable_truth():
    text = _docs_text()
    assert "progress.jsonl" in text
    assert "durable" in text.lower()


def test_docs_explain_integration_ref():
    text = _docs_text()
    assert "refs/cxor/runs/" in text
    assert "integration ref" in text.lower()


def test_docs_explain_target_remains_clean_between_patchlets():
    text = _docs_text()
    assert "target repo remains clean" in text.lower()
    assert "between patchlets" in text.lower()


def test_docs_explain_worktrees_start_from_integration_sha():
    text = _docs_text()
    assert "integration SHA" in text
    assert "worktree" in text.lower()


def test_docs_explain_apply_results_modes():
    text = _docs_text()
    assert "apply-results" in text
    assert "--mode patch" in text
    assert "--mode branch" in text
    assert "--mode working-tree" in text


def test_docs_explain_safe_failure_not_done():
    text = _docs_text()
    assert "safe failure" in text.lower() or "safe_failure" in text
    assert "not DONE" in text or "not task DONE" in text
