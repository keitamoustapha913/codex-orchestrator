from __future__ import annotations

from pathlib import Path


def _docs_text() -> str:
    repo = Path(__file__).resolve().parents[2]
    paths = [
        repo / "README.md",
        repo / "docs" / "cli.md",
        repo / "docs" / "worktrees.md",
        repo / "docs" / "autonomous_loop.md",
        repo / "docs" / "real_codex_smoke.md",
        repo / "IMPLEMENTATION_STATUS.md",
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths if path.exists())


def test_docs_explain_patchlet_timeout_default_ten_minutes():
    text = _docs_text().lower()

    assert "600 seconds" in text
    assert "10 minutes" in text


def test_docs_explain_timeout_env_overrides():
    text = _docs_text()

    assert "CODEX_TIMEOUT_SECONDS" in text
    assert "CODEX_PATCHLET_TIMEOUT_SECONDS" in text


def test_docs_explain_progress_jsonl_is_liveness_not_success():
    text = _docs_text().lower()

    assert "progress.jsonl" in text
    assert "liveness" in text
    assert "not success" in text


def test_docs_explain_patchlet_model_default():
    text = _docs_text()

    assert "gpt-5.4-mini" in text


def test_docs_explain_orchestrator_model_default():
    text = _docs_text()

    assert "gpt-5.5" in text


def test_docs_explain_timeout_safe_failure_is_not_done():
    text = _docs_text().lower()

    assert "timeout safe-failure" in text
    assert "not task success" in text


def test_docs_explain_invalid_timeout_env_values_are_structured_errors():
    text = _docs_text().lower()

    assert "invalid timeout" in text
    assert "structured" in text
    assert "expected positive integer seconds" in text


def test_docs_explain_orchestrator_subprocess_timeout_diagnosis():
    text = _docs_text()

    assert "orchestrator_subprocess_timeout" in text
    assert "diagnose-real-codex" in text


def test_docs_explain_timeout_diagnosis_is_not_task_success():
    text = _docs_text().lower()

    assert "orchestrator_subprocess_timeout" in text
    assert "not task success" in text


def test_docs_explain_explicit_real_codex_smoke_is_operator_run():
    text = _docs_text().lower()

    assert "explicit real-codex smoke" in text
    assert "operator-run" in text
    assert "not part of the default test suite" in text
