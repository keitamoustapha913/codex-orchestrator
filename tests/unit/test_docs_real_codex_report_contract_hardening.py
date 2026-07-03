from __future__ import annotations

from pathlib import Path


DOCS = [
    Path("README.md"),
    Path("docs/cli.md"),
    Path("docs/autonomous_loop.md"),
    Path("docs/real_codex_smoke.md"),
    Path("docs/runbooks/real_codex_smoke_runbook.md"),
    Path("docs/release.md"),
    Path("docs/report_contract.md"),
    Path("IMPLEMENTATION_STATUS.md"),
]


def _docs_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOCS if path.exists())


def test_docs_explain_canonical_probe_refs_are_objects():
    text = _docs_text()
    assert "Canonical patchlet reports" in text or "Canonical reports" in text
    assert "`probe_artifact_refs` entries are objects" in text or "`probe_artifact_refs` object-shaped" in text


def test_docs_explain_raw_string_refs_are_ingress_only():
    text = _docs_text()
    assert "Raw real-Codex reports" in text or "Raw worker reports" in text
    assert "ingress-only" in text or "only during report ingress" in text


def test_docs_explain_report_ingestion_result():
    assert "report_ingestion_result.json" in _docs_text()


def test_docs_explain_report_validation_errors():
    assert "report_validation_errors.json" in _docs_text()


def test_docs_explain_safe_artifacts_probes_boundary():
    text = _docs_text()
    assert ".artifacts/probes/" in text
    assert "under `.artifacts/probes/`" in text


def test_docs_explain_unsafe_refs_fail():
    text = _docs_text()
    assert "Unsafe refs" in text or "unsafe refs" in text
    assert "fail with structured" in text


def test_docs_explain_probe_artifact_refs_not_objects_signature():
    text = _docs_text()
    assert "probe_artifact_refs_not_objects" in text
    assert "unknown_repeated_failure" in text


def test_docs_explain_report_only_repair_policy():
    text = _docs_text()
    assert "report-only repair" in text.lower()
    assert "must not edit product" in text or "forbids product/runtime edits" in text


def test_docs_explain_full_patchlet_repair_still_used_for_product_failures():
    text = _docs_text()
    assert "Full patchlet repair" in text or "full patchlet repair" in text
    assert "true product failures" in text


def test_docs_include_valid_probe_ref_object_example():
    text = _docs_text()
    assert '"patchlet_id": "P0002"' in text
    assert '"probe_root": ".artifacts/probes/P0002"' in text
    assert '"files"' in text


def test_docs_include_invalid_string_ref_example():
    text = _docs_text()
    assert '".artifacts/probes/P0002/comparison.txt"' in text
    assert "Invalid canonical report shape" in text


def test_docs_explain_live_progress_report_ingestion_visibility():
    text = _docs_text()
    assert "--live-progress" in text
    assert "report ingestion P0002 normalized" in text
