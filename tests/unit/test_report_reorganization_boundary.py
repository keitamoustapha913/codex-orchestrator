from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from codex_orchestrator.report_contract import RawReportError, classify_fields, parse_raw_report
from codex_orchestrator.report_reorganization import reorganize_report, verify_reorganization, verify_reorganization_values, verify_worker_output_boundary
from codex_orchestrator.report_reorganization_worker import main as reorganization_worker_main


def test_raw_report_is_byte_preserved_and_unknown_field_is_warning_candidate():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "raw_worker_report.json"
        original = b'{"schema_version":"2.0","kind":"worker_patchlet_report","acceptance_criteria_result":{"status":"PASS"}}'
        path.write_bytes(original)
        envelope = parse_raw_report(path)
        assert envelope.raw_bytes == original
        _, unknown = classify_fields(envelope.value)
        assert [row["field_name"] for row in unknown] == ["acceptance_criteria_result"]


def test_reorganization_accounts_for_every_field_and_verifies_source_hash():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "raw.json"
        path.write_text('{"schema_version":"2.0","kind":"worker_patchlet_report","x":true}', encoding="utf-8")
        envelope = parse_raw_report(path)
        artifacts = reorganize_report(envelope.value, source_report_sha256=envelope.sha256,
            patchlet_id="P0005", attempt_id="P0005_attempt1", output_dir=Path(directory) / "scratch")
        assert artifacts["trace"]["raw_field_count"] == 3
        assert verify_reorganization(artifacts["candidate"], artifacts["trace"],
            raw_report_sha256=envelope.sha256, patchlet_id="P0005", attempt_id="P0005_attempt1") == []
        assert verify_reorganization(artifacts["candidate"], artifacts["trace"],
            raw_report_sha256="0" * 64, patchlet_id="P0005", attempt_id="P0005_attempt1")[0]["code"] == "REPORT_REORGANIZATION_SOURCE_HASH_MISMATCH"


def test_reorganization_rejects_changed_values_types_and_dropped_fields():
    raw = {"schema_version": "2.0", "kind": "worker_patchlet_report", "patchlet_id": "P0005", "status": "COMPLETE"}
    with tempfile.TemporaryDirectory() as directory:
        artifacts = reorganize_report(raw, source_report_sha256="0" * 64, patchlet_id="P0005", attempt_id="P0005_attempt1", output_dir=Path(directory))
        candidate = artifacts["candidate"]
        candidate["normalized_known_fields"]["status"] = 3
        assert {error["code"] for error in verify_reorganization_values(candidate, artifacts["trace"], raw)} >= {"REPORT_REORGANIZATION_TYPE_CHANGED"}
        candidate["normalized_known_fields"].pop("status")
        assert any(error["code"] == "REPORT_REORGANIZATION_FIELD_DROPPED" for error in verify_reorganization_values(candidate, artifacts["trace"], raw))


def test_reorganization_never_maps_v1_alias_to_v2_field(tmp_path: Path):
    raw = {"changed_runtime_file": "app.py"}

    artifacts = reorganize_report(
        raw,
        source_report_sha256="0" * 64,
        patchlet_id="P0001",
        attempt_id="P0001_attempt1",
        output_dir=tmp_path,
    )

    candidate = artifacts["candidate"]
    assert "changed_product_runtime_file" not in candidate["normalized_known_fields"]
    assert [row["field_name"] for row in candidate["unrecognized_fields"]] == ["changed_runtime_file"]
    assert "legacy_field_mappings" not in candidate
    trace = artifacts["trace"]["fields"][0]
    assert trace["mapping_type"] == "UNRECOGNIZED_EXTENSION"
    assert trace["destination_canonical_field"] is None


def test_worker_output_boundary_rejects_extra_files(tmp_path: Path):
    (tmp_path / "report_reorganization_candidate.json").write_text("{}", encoding="utf-8")
    (tmp_path / "unexpected.txt").write_text("no", encoding="utf-8")
    assert verify_worker_output_boundary(tmp_path)[0]["code"] == "REPORT_REORGANIZATION_OUTPUT_BOUNDARY_VIOLATION"


def test_worker_output_boundary_rejects_symlinks_and_recursive_requests(tmp_path: Path):
    target = tmp_path / "target"
    target.write_text("x", encoding="utf-8")
    (tmp_path / "report_reorganization_trace.json").symlink_to(target)
    assert verify_worker_output_boundary(tmp_path)[0]["code"] == "REPORT_REORGANIZATION_OUTPUT_BOUNDARY_VIOLATION"
    assert reorganization_worker_main(["raw", "out", "hash", "P0005", "A1", "recursive"]) == 2


@pytest.mark.parametrize(("payload", "code"), [
    (b"[]", "RAW_WORKER_REPORT_NOT_OBJECT"),
    (b'{"x":1,"x":2}', "RAW_WORKER_REPORT_DUPLICATE_KEY"),
    (b"\xff", "RAW_WORKER_REPORT_INVALID_UTF8"),
    (b'{"probe_artifact_refs":["/etc/passwd"]}', "RAW_WORKER_REPORT_UNSAFE_REFERENCE"),
])
def test_raw_envelope_failures_are_hard_and_pre_reorganization(payload: bytes, code: str):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "raw.json"
        path.write_bytes(payload)
        with pytest.raises(RawReportError) as error:
            parse_raw_report(path)
        assert error.value.code == code


@pytest.mark.parametrize("field", ["changed_artifact_files", "probe_artifact_refs"])
@pytest.mark.parametrize("reference", ["/tmp/worker/evidence.json", "../outside/evidence.json", "~/evidence.json"])
def test_raw_report_rejects_absolute_home_and_traversal_artifact_references(field: str, reference: str):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "raw.json"
        value = [reference] if field == "changed_artifact_files" else [{"probe_root": reference}]
        path.write_text(json.dumps({field: value}), encoding="utf-8")
        with pytest.raises(RawReportError) as error:
            parse_raw_report(path)
        assert error.value.code == "RAW_WORKER_REPORT_UNSAFE_REFERENCE"


def test_raw_report_accepts_bounded_logical_evidence_reference():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "raw.json"
        path.write_text(json.dumps({
            "changed_artifact_files": [".artifacts/probes/P0002/GP002/run_001/before_state.json"],
            "probe_artifact_refs": [{"probe_root": ".artifacts/probes/P0002/GP002/run_001"}],
        }), encoding="utf-8")
        envelope = parse_raw_report(path)
        assert envelope.value["changed_artifact_files"][0].startswith(".artifacts/probes/")
