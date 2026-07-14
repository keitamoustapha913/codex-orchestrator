from __future__ import annotations

import sys
from pathlib import Path

from codex_orchestrator.jsonio import read_json

sys.path.append(str(Path(__file__).resolve().parent))
from test_positive_evidence_file_mapping import run_decomposition


def test_unmapped_required_goal_blocks_before_worker_execution(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path, variant="unmatched_goal")
    mapping = read_json(workflow / "decomposition" / "file_mapping_result.json")
    assert mapping["accepted"] is False
    assert "GI001" in mapping["unmapped_goal_item_ids"]
    assert any(row["code"] == "UNMAPPED_REQUIRED_GOAL_ITEM" for row in mapping["errors"])


def test_unmapped_required_obligation_blocks_before_worker_execution(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path, variant="unmatched_goal")
    mapping = read_json(workflow / "decomposition" / "file_mapping_result.json")
    assert mapping["accepted"] is False
    assert "PO001" in mapping["unmapped_proof_obligation_ids"]
    assert any(row["code"] == "UNMAPPED_REQUIRED_PROOF_OBLIGATION" for row in mapping["errors"])


def test_missing_probe_blocks_before_worker_execution(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path, variant="missing_probe")
    mapping = read_json(workflow / "decomposition" / "file_mapping_result.json")
    assert mapping["accepted"] is False
    assert "PO001" in mapping["missing_probe_obligation_ids"]
    assert any(row["code"] == "MISSING_MANDATORY_PROBE" for row in mapping["errors"])


def test_ambiguous_target_file_blocks_before_worker_execution(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path, variant="ambiguous")
    mapping = read_json(workflow / "decomposition" / "file_mapping_result.json")
    assert mapping["accepted"] is False
    assert "GI001" in mapping["ambiguous_goal_item_ids"]
    assert "PO001" in mapping["ambiguous_proof_obligation_ids"]
    assert any(row["code"] == "AMBIGUOUS_REQUIRED_TARGET" for row in mapping["errors"])


def test_unresolved_item_creates_no_patchlet(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path, variant="unmatched_goal")
    patchlets = read_json(workflow / "decomposition" / "patchlet_plan.json")["patchlets"]
    assert patchlets == []
