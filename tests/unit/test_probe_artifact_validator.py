from __future__ import annotations

import json
from pathlib import Path

from codex_orchestrator.validators.probe_artifact_validator import validate_probe_artifact_run


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _create_complete_probe_run(tmp_path: Path, patchlet_id: str = "P0002", run_id: str = "run_001") -> Path:
    probe_root = tmp_path / ".artifacts" / "probes" / patchlet_id
    run_root = probe_root / run_id
    probe_root.mkdir(parents=True, exist_ok=True)
    (probe_root / "probe.py").write_text("print('probe')\n", encoding="utf-8")
    _write_jsonl(run_root / "row_ledger.jsonl", [{"row": 1}])
    _write_jsonl(run_root / "trace_ledger.jsonl", [{"trace": 1}])
    _write_json(run_root / "before_state.json", {"value": "before"})
    _write_json(run_root / "after_state.json", {"value": "after"})
    _write_json(run_root / "cleanup_proof.json", {"cleanup_passed": True})
    return probe_root


def test_probe_artifact_validator_accepts_complete_probe_run(tmp_path: Path):
    probe_root = _create_complete_probe_run(tmp_path)

    result = validate_probe_artifact_run(probe_root / "run_001", patchlet_id="P0002")

    assert result["valid"] is True
    assert result["patchlet_id"] == "P0002"
    assert result["probe_root"] == ".artifacts/probes/P0002"
    assert result["run_id"] == "run_001"
    assert result["errors"] == []


def test_probe_artifact_validator_rejects_missing_probe_root(tmp_path: Path):
    result = validate_probe_artifact_run(
        tmp_path / ".artifacts" / "probes" / "P0002" / "run_001",
        patchlet_id="P0002",
    )

    assert result["valid"] is False
    assert result["errors"][0]["code"] == "MISSING_PROBE_ROOT"


def test_probe_artifact_validator_rejects_missing_probe_executable(tmp_path: Path):
    probe_root = _create_complete_probe_run(tmp_path)
    (probe_root / "probe.py").unlink()

    result = validate_probe_artifact_run(probe_root / "run_001", patchlet_id="P0002")

    assert result["valid"] is False
    assert any(error["code"] == "MISSING_PROBE_EXECUTABLE" for error in result["errors"])


def test_probe_artifact_validator_rejects_missing_row_ledger(tmp_path: Path):
    probe_root = _create_complete_probe_run(tmp_path)
    (probe_root / "run_001" / "row_ledger.jsonl").unlink()

    result = validate_probe_artifact_run(probe_root / "run_001", patchlet_id="P0002")

    assert result["valid"] is False
    assert any(error["code"] == "MISSING_ROW_LEDGER" for error in result["errors"])


def test_probe_artifact_validator_rejects_empty_row_ledger(tmp_path: Path):
    probe_root = _create_complete_probe_run(tmp_path)
    (probe_root / "run_001" / "row_ledger.jsonl").write_text("", encoding="utf-8")

    result = validate_probe_artifact_run(probe_root / "run_001", patchlet_id="P0002")

    assert result["valid"] is False
    assert any(error["code"] == "EMPTY_ROW_LEDGER" for error in result["errors"])


def test_probe_artifact_validator_rejects_invalid_row_ledger_jsonl(tmp_path: Path):
    probe_root = _create_complete_probe_run(tmp_path)
    (probe_root / "run_001" / "row_ledger.jsonl").write_text("{bad json}\n", encoding="utf-8")

    result = validate_probe_artifact_run(probe_root / "run_001", patchlet_id="P0002")

    assert result["valid"] is False
    assert any(error["code"] == "INVALID_ROW_LEDGER_JSONL" for error in result["errors"])


def test_probe_artifact_validator_rejects_missing_trace_ledger(tmp_path: Path):
    probe_root = _create_complete_probe_run(tmp_path)
    (probe_root / "run_001" / "trace_ledger.jsonl").unlink()

    result = validate_probe_artifact_run(probe_root / "run_001", patchlet_id="P0002")

    assert result["valid"] is False
    assert any(error["code"] == "MISSING_TRACE_LEDGER" for error in result["errors"])


def test_probe_artifact_validator_rejects_missing_before_state(tmp_path: Path):
    probe_root = _create_complete_probe_run(tmp_path)
    (probe_root / "run_001" / "before_state.json").unlink()

    result = validate_probe_artifact_run(probe_root / "run_001", patchlet_id="P0002")

    assert result["valid"] is False
    assert any(error["code"] == "MISSING_BEFORE_STATE" for error in result["errors"])


def test_probe_artifact_validator_rejects_missing_after_state(tmp_path: Path):
    probe_root = _create_complete_probe_run(tmp_path)
    (probe_root / "run_001" / "after_state.json").unlink()

    result = validate_probe_artifact_run(probe_root / "run_001", patchlet_id="P0002")

    assert result["valid"] is False
    assert any(error["code"] == "MISSING_AFTER_STATE" for error in result["errors"])


def test_probe_artifact_validator_rejects_missing_cleanup_proof(tmp_path: Path):
    probe_root = _create_complete_probe_run(tmp_path)
    (probe_root / "run_001" / "cleanup_proof.json").unlink()

    result = validate_probe_artifact_run(probe_root / "run_001", patchlet_id="P0002")

    assert result["valid"] is False
    assert any(error["code"] == "MISSING_CLEANUP_PROOF" for error in result["errors"])


def test_probe_artifact_validator_rejects_cleanup_not_passed(tmp_path: Path):
    probe_root = _create_complete_probe_run(tmp_path)
    _write_json(probe_root / "run_001" / "cleanup_proof.json", {"cleanup_passed": False})

    result = validate_probe_artifact_run(probe_root / "run_001", patchlet_id="P0002")

    assert result["valid"] is False
    assert any(error["code"] == "CLEANUP_NOT_PASSED" for error in result["errors"])
