from __future__ import annotations

from pathlib import Path


DOCS = [
    Path("README.md"),
    Path("docs/cli.md"),
    Path("docs/autonomous_loop.md"),
    Path("docs/worktrees.md"),
    Path("docs/real_codex_smoke.md"),
    Path("docs/runbooks/real_codex_smoke_runbook.md"),
    Path("docs/release.md"),
    Path("IMPLEMENTATION_STATUS.md"),
]


def _combined_docs() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOCS if path.exists())


def test_docs_explain_final_auto_command():
    assert "cxor auto --repo <repo> --master <prompt> --until DONE" in _combined_docs()


def test_docs_explain_real_codex_opt_in():
    assert "real Codex is opt-in only" in _combined_docs()


def test_docs_explain_mock_mode_ci_safe():
    assert "mock mode is deterministic and CI-safe" in _combined_docs()


def test_docs_explain_integration_ref_target_clean():
    assert "integration ref keeps the target clean between patchlets" in _combined_docs()


def test_docs_explain_apply_results_explicit():
    assert "apply-results is explicit finalization" in _combined_docs()


def test_docs_explain_runbook_validate_list_export_flow():
    text = _combined_docs()

    assert "cxor real-codex-smoke-runbook --dry-run" in text
    assert "cxor validate-real-codex-smoke-runbook --run-dir" in text
    assert "cxor list-real-codex-smoke-runbooks" in text
    assert "cxor export-real-codex-smoke-runbook --run-dir" in text


def test_docs_explain_release_checklist():
    assert "Release checklist" in _combined_docs()
