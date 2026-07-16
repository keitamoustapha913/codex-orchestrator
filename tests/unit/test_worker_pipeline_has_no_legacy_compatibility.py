from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_FILES = [
    "src/codex_orchestrator/patch_promotion.py",
    "src/codex_orchestrator/worker_evidence.py",
    "src/codex_orchestrator/report_contract.py",
    "src/codex_orchestrator/report_ingestion.py",
    "src/codex_orchestrator/report_reorganization.py",
    "src/codex_orchestrator/semantic_result_normalization.py",
    "src/codex_orchestrator/worker_capsule.py",
    "src/codex_orchestrator/stages/run_patchlet.py",
    "src/codex_orchestrator/stages/status.py",
]


def _source_text() -> str:
    return "\n".join((ROOT / relative).read_text(encoding="utf-8") for relative in SOURCE_FILES)


def test_worker_pipeline_has_no_legacy_evidence_classifier():
    text = _source_text()
    assert "LEGACY_" + "APPROVED_PROBE_EVIDENCE" not in text
    assert "classify_legacy_" + "worker_evidence" not in text
    assert "approved_legacy_" + "run_ids" not in text


def test_worker_pipeline_has_no_v1_report_alias_adapter():
    text = _source_text()
    assert "DOCUMENTED_LEGACY_" + "ALIASES" not in text
    assert "adapt_documented_" + "legacy_fields" not in text
    assert "WorkerPatchletReportV1-" + "to-V2-aliases" not in text


def test_worker_pipeline_has_no_semantic_goal_alias_table():
    assert "GOAL_ITEM_" + "ALIASES" not in _source_text()


def test_worker_pipeline_has_no_legacy_work_slice_fallback():
    assert "legacy-" + "invariant-slice" not in _source_text()


def test_worker_pipeline_has_no_direct_root_scratch_quarantine():
    text = _source_text()
    assert "_quarantine_execution_root_scratch_files" not in text
    assert "WORKER_SCRATCH_PATH_" + "CONTRACT_VIOLATION" not in text


def test_worker_classification_schema_has_no_old_classes():
    schema = json.loads(
        (ROOT / "src/codex_orchestrator/schemas/worker_change_classification_ledger.schema.json").read_text(
            encoding="utf-8"
        )
    )
    text = json.dumps(schema, sort_keys=True)
    old = {
        "APPROVED_PROBE_EVIDENCE",
        "BOUNDED_SCRATCH_WARNING",
        "FORBIDDEN_TRACKED_CHANGE",
        "PROTECTED_FILE_CHANGE",
        "UNKNOWN_WORKER_OUTPUT",
        "UNSAFE_PATH_OBJECT",
    }
    assert not any(value in text for value in old)


def test_worker_hygiene_schema_has_no_legacy_fields():
    schema = json.loads(
        (ROOT / "src/codex_orchestrator/schemas/worker_sandbox_hygiene_result.schema.json").read_text(
            encoding="utf-8"
        )
    )
    text = json.dumps(schema, sort_keys=True)
    for field in (
        "warning_entries",
        "rejected_entries",
        "legacy_evidence_file_count",
        "unknown_worker_output_count",
        "protected_change_count",
    ):
        assert field not in text
