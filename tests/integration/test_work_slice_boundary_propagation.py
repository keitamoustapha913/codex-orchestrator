from __future__ import annotations

from pathlib import Path
import sys

from codex_orchestrator.jsonio import read_json

sys.path.append(str(Path(__file__).resolve().parent))
from test_positive_evidence_file_mapping import run_decomposition


def _first(workflow: Path):
    return read_json(workflow / "decomposition" / "work_slices.json")["slices"][0]


def test_symbol_boundary_propagates_to_work_slice(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path)
    assert _first(workflow)["current_slice_boundary"]["symbol"] == "codename"


def test_expected_observation_propagates_to_work_slice(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path)
    assert _first(workflow)["current_slice_boundary"]["expected_observation"] == "zephyr-42"


def test_probe_ids_propagate_to_patchlet_plan(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path)
    patchlet = read_json(workflow / "decomposition" / "patchlet_plan.json")["patchlets"][0]
    assert patchlet["probe_ids"] == ["GP001"]


def test_current_boundary_excluded_from_future_boundaries(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path)
    first = _first(workflow)
    assert first["current_slice_boundary"]["proof_obligation_id"] == "PO001"
    assert "PO001" not in [row["proof_obligation_id"] for row in first["future_slice_boundaries"]]


def test_last_same_file_patchlet_has_no_future_boundaries(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path)
    last = read_json(workflow / "decomposition" / "work_slices.json")["slices"][-1]
    assert last["future_slice_boundaries"] == []
