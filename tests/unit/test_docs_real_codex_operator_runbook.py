from __future__ import annotations

from pathlib import Path


def _docs_text() -> str:
    repo = Path(__file__).resolve().parents[2]
    paths = [
        repo / "README.md",
        repo / "docs" / "cli.md",
        repo / "docs" / "real_codex_smoke.md",
        repo / "docs" / "runbooks" / "real_codex_smoke_runbook.md",
        repo / "IMPLEMENTATION_STATUS.md",
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths if path.exists())


def test_docs_explain_operator_runbook_is_not_default_suite():
    text = _docs_text().lower()

    assert "real-codex-smoke-runbook" in text
    assert "not part of the default test suite" in text
    assert "default pytest does not run real codex" in text


def test_docs_explain_dry_run_mode():
    text = _docs_text().lower()

    assert "--dry-run" in text
    assert "does not invoke real codex" in text
    assert "outcome dry_run" in text


def test_docs_explain_explicit_real_codex_mode():
    text = _docs_text().lower()

    assert "--run-real-codex" in text
    assert "may consume account" in text
    assert "codex_patchlet_timeout_seconds" in text


def test_docs_explain_operator_run_artifact_layout():
    text = _docs_text()

    assert ".operator-runs/real-codex-smoke/" in text
    assert "selected_policy.json" in text
    assert "diagnosis_paths.json" in text
    assert "explicit_smoke_stdout.txt" in text


def test_docs_explain_safe_failure_is_capture_not_done():
    text = _docs_text().lower()

    assert "safe_failure is a successful runbook capture" in text
    assert "not task done" in text
    assert "done means the orchestrator validators accepted the run" in text


def test_docs_explain_how_to_compare_runs():
    text = _docs_text().lower()

    assert "compare runs" in text
    assert "result.json" in text
    assert "selected_policy.json" in text
