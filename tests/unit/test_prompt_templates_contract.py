from __future__ import annotations

from pathlib import Path


def _text() -> str:
    return (Path("src/codex_orchestrator/prompt_templates") / "real_codex_patchlet_contract.md").read_text(encoding="utf-8")


def test_real_codex_patchlet_contract_mentions_cxor_environment_paths():
    text = _text()
    assert "CXOR_TARGET_ROOT" in text
    assert "CXOR_EXECUTION_ROOT" in text
    assert "CXOR_ARTIFACT_ROOT" in text
    assert "CXOR_REPORT_PATH" in text
    assert "CXOR_PROBE_ROOT" in text


def test_real_codex_patchlet_contract_requires_probe_artifact_refs():
    text = _text()
    assert "probe_artifact_refs" in text


def test_real_codex_patchlet_contract_requires_durable_probe_files():
    text = _text()
    assert "probe.py" in text
    assert "row_ledger.jsonl" in text
    assert "trace_ledger.jsonl" in text
    assert "before_state.json" in text
    assert "after_state.json" in text
    assert "cleanup_proof.json" in text


def test_real_codex_patchlet_contract_requires_only_allowed_product_file():
    text = _text()
    assert "CXOR_ALLOWED_PRODUCT_RUNTIME_FILE" in text
    assert "Only change the allowed product/runtime file" in text


def test_real_codex_patchlet_contract_forbids_blind_retry_and_transient_claims():
    text = _text()
    assert "Do not use blind retry" in text
    assert "Do not claim the issue is transient" in text or "Do not claim transient" in text
