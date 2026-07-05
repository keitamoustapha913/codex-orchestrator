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


def _combined_docs() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOCS)


def test_docs_explain_peer_files_present_are_not_changes():
    text = _combined_docs()
    assert "unchanged peer product files are ignored" in text
    assert "presence is not a change" in text


def test_docs_explain_changed_peer_files_rejected():
    text = _combined_docs()
    assert "changed peer product files are rejected" in text


def test_docs_explain_validation_scratch_role_tokens():
    text = _combined_docs()
    assert "validate_report.out" in text
    assert "verify_result.log" in text
    assert "role-shaped validation scratch" in text


def test_docs_explain_diff_guard_uses_actual_changes_not_presence():
    text = _combined_docs()
    assert "actual changed/untracked paths" in text
    assert "not file presence" in text


def test_docs_explain_allowed_file_from_patchlet_plan_not_filename_convention():
    text = _combined_docs()
    assert "allowed file from the patchlet plan" in text
    assert "not filename convention" in text
