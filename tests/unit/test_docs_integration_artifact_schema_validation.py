from __future__ import annotations

from pathlib import Path


DOCS = [
    Path("README.md"),
    Path("docs/cli.md"),
    Path("docs/worktrees.md"),
    Path("docs/autonomous_loop.md"),
    Path("docs/real_codex_smoke.md"),
    Path("IMPLEMENTATION_STATUS.md"),
]


def _combined_docs() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOCS if path.exists())


def test_docs_explain_integration_artifact_schemas():
    text = _combined_docs()

    assert "integration_state.schema.json" in text
    assert "integration_checkpoint.schema.json" in text


def test_docs_explain_accepted_changes_jsonl_schema_validation():
    text = _combined_docs()

    assert "accepted_changes.jsonl" in text
    assert "accepted_change.schema.json" in text
    assert "line-by-line" in text


def test_docs_explain_apply_results_schema_validation():
    text = _combined_docs()

    assert "apply_results_result.schema.json" in text
    assert "patch_result.json" in text


def test_docs_explain_validate_integration_artifacts_command():
    text = _combined_docs()

    assert "cxor validate-integration-artifacts --repo" in text


def test_docs_explain_validation_is_read_only_and_does_not_run_codex():
    text = _combined_docs()

    assert "read-only" in text
    assert "does not run Codex" in text
