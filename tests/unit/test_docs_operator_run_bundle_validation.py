from __future__ import annotations

from pathlib import Path


DOCS = [
    Path("README.md"),
    Path("docs/cli.md"),
    Path("docs/real_codex_smoke.md"),
    Path("docs/runbooks/real_codex_smoke_runbook.md"),
    Path("IMPLEMENTATION_STATUS.md"),
]


def _combined_docs() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOCS if path.exists())


def test_docs_explain_operator_run_bundle_validation_command():
    assert "cxor validate-real-codex-smoke-runbook --run-dir" in _combined_docs()


def test_docs_explain_selected_policy_result_and_diagnosis_schemas():
    text = _combined_docs()

    assert "real_codex_smoke_selected_policy.schema.json" in text
    assert "real_codex_smoke_operator_result.schema.json" in text
    assert "real_codex_smoke_diagnosis_paths.schema.json" in text


def test_docs_explain_required_text_evidence_files():
    text = _combined_docs()

    assert "environment.txt" in text
    assert "default_skip_stdout.txt" in text
    assert "explicit_smoke_stdout.txt" in text


def test_docs_explain_validation_is_read_only():
    assert "read-only" in _combined_docs()


def test_docs_explain_validation_does_not_run_codex():
    text = _combined_docs()

    assert "does not run Codex" in text
    assert "does not run pytest" in text


def test_docs_explain_safe_failure_is_capture_not_done():
    assert "safe_failure is a successful runbook capture" in _combined_docs()
