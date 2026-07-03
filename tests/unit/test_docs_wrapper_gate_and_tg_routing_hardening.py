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


def test_docs_explain_canonical_final_status_marker():
    text = _docs_text()

    assert "FINAL_STATUS: PASS" in text
    assert "standalone" in text


def test_docs_explain_noncanonical_marker_rejected():
    text = _docs_text()

    assert "non-canonical" in text
    assert "rejected" in text


def test_docs_explain_marker_backticks_not_allowed():
    text = _docs_text()

    assert "Marker: `FINAL_STATUS: PASS`" in text
    assert "backticks" in text


def test_docs_explain_valid_report_does_not_bypass_wrapper_gate():
    text = _docs_text()

    assert "valid report JSON alone does not bypass the wrapper gate" in text


def test_docs_explain_wrapper_gate_marker_diagnosis():
    text = _docs_text()

    assert "wrapper_gate_final_status_marker_error" in text


def test_docs_explain_tg_ids_are_not_patchlet_ids():
    text = _docs_text()

    assert "TG001" in text
    assert "not patchlet ids" in text


def test_docs_explain_tg_failures_preserve_member_patchlets():
    text = _docs_text()

    assert "source_patchlet_ids" in text
    assert "member patchlet" in text


def test_docs_explain_tg_mapping_structured_error():
    text = _docs_text()

    assert "transaction_group_source_mapping_missing" in text


def test_docs_explain_network_error_does_not_mask_gate_or_routing_failures():
    text = _docs_text()

    assert "network_or_api_error" in text
    assert "does not mask" in text


def test_docs_explain_validate_list_export_after_live_smoke():
    text = _docs_text()

    assert "validate-real-codex-smoke-runbook" in text
    assert "list-real-codex-smoke-runbooks" in text
    assert "export-real-codex-smoke-runbook" in text
