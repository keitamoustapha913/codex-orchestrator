from __future__ import annotations

from pathlib import Path


DOCS = [
    Path("README.md"),
    Path("docs/cli.md"),
    Path("docs/real_codex_smoke.md"),
    Path("docs/runbooks/real_codex_smoke_runbook.md"),
    Path("docs/release.md"),
    Path("IMPLEMENTATION_STATUS.md"),
]


def _docs_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOCS if path.exists())


def test_docs_explain_patchlet_report_schema_violation():
    assert "patchlet_report_schema_violation" in _docs_text()


def test_docs_list_allowed_patchlet_report_statuses():
    text = _docs_text()
    for status in ["COMPLETE", "VERIFIED_NO_CHANGE_NEEDED", "BLOCKED_WITH_EVIDENCE", "FAILED_WITH_EVIDENCE"]:
        assert status in text


def test_docs_say_fixed_status_is_invalid():
    text = _docs_text()
    assert "FIXED" in text
    assert "invalid" in text.lower() or "unsupported" in text.lower()


def test_docs_explain_cleanup_proof_type_contract():
    text = _docs_text()
    assert "cleanup_proof" in text
    assert "string" in text


def test_docs_explain_report_schema_violation_is_not_network_error():
    text = _docs_text()
    assert "network_or_api_error" in text
    assert "not a network" in text.lower() or "not network" in text.lower()


def test_docs_explain_repair_prompt_report_skeleton():
    text = _docs_text()
    assert "report skeleton" in text.lower()
    assert "repair patchlet" in text.lower()


def test_docs_explain_execution_root_product_edits():
    text = _docs_text()
    assert "CXOR_EXECUTION_ROOT" in text
    assert "product/runtime edits" in text


def test_docs_explain_target_root_product_files_read_only():
    text = _docs_text()
    assert "CXOR_TARGET_ROOT" in text
    assert "read-only" in text


def test_docs_explain_validate_list_export_after_safe_failure():
    text = _docs_text()
    assert "validate-real-codex-smoke-runbook" in text
    assert "list-real-codex-smoke-runbooks" in text
    assert "export-real-codex-smoke-runbook" in text
