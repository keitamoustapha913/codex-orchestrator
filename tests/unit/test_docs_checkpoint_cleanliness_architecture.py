from __future__ import annotations

from pathlib import Path


DOC_PATHS = [
    Path("README.md"),
    Path("docs/cli.md"),
    Path("docs/real_codex_smoke.md"),
    Path("docs/runbooks/real_codex_smoke_runbook.md"),
    Path("docs/release.md"),
    Path("IMPLEMENTATION_STATUS.md"),
]


def _docs_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOC_PATHS if path.exists())


def test_docs_explain_checkpoint_cleanliness_taxonomy():
    text = _docs_text()
    assert "checkpoint cleanliness taxonomy" in text
    assert "product_runtime_clean" in text
    assert "unknown_dirty_paths" in text


def test_docs_explain_product_clean_vs_whole_target_clean():
    text = _docs_text()
    assert "product/runtime clean" in text
    assert "whole target clean" in text


def test_docs_explain_python_cache_policy():
    text = _docs_text()
    assert "PYTHONDONTWRITEBYTECODE=1" in text
    assert "python -B" in text
    assert "__pycache__/" in text


def test_docs_explain_target_hygiene_gate():
    text = _docs_text()
    assert "Target Hygiene Gate" in text
    assert "target_hygiene_gate_result.json" in text


def test_docs_explain_cache_evidence_and_cleanup():
    text = _docs_text()
    assert "cache_artifacts_detected" in text
    assert "cache_artifacts_removed" in text
    assert "evidence-recorded" in text


def test_docs_explain_unknown_dirty_path_failure():
    text = _docs_text()
    assert "unknown dirty paths" in text
    assert "not deleted" in text


def test_docs_explain_manifest_attempt_lifecycle():
    text = _docs_text()
    assert "ATTEMPT_STARTED" in text
    assert "INTEGRATION_ARTIFACTS_VALIDATED" in text
    assert "ATTEMPT_FAILED_WITH_EVIDENCE" in text


def test_docs_explain_runbook_attempt_consistency():
    text = _docs_text()
    assert "attempt_consistency" in text
    assert "runbook attempt consistency" in text


def test_docs_explain_integration_checkpoint_diagnosis():
    text = _docs_text()
    assert "integration_checkpoint_target_cleanliness_error" in text
    assert "integration_artifact_validation_error" in text


def test_docs_explain_network_error_tightening():
    text = _docs_text()
    assert "network_or_api_error" in text
    assert "actual external error evidence" in text


def test_docs_explain_validate_list_export_after_live_runs():
    text = _docs_text()
    assert "validate-real-codex-smoke-runbook" in text
    assert "list-real-codex-smoke-runbooks" in text
    assert "export-real-codex-smoke-runbook" in text
