from __future__ import annotations

from pathlib import Path
import sys

from codex_orchestrator.jsonio import read_json

sys.path.append(str(Path(__file__).resolve().parent))
from test_positive_evidence_file_mapping import JS_SLICES, PYTHON_SLICES, run_decomposition


def _patchlets(workflow: Path):
    return read_json(workflow / "decomposition" / "patchlet_plan.json")["patchlets"]


def test_python_support_module_fixture_produces_exactly_five_patchlets(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path)
    assert len(_patchlets(workflow)) == 5


def test_javascript_support_reexport_fixture_produces_exactly_five_patchlets(tmp_path: Path):
    _, workflow = run_decomposition(
        tmp_path,
        product_file="src/runtime-profile.mjs",
        support_file="src/index.mjs",
        verification_file="test/check-one.mjs",
        slices=JS_SLICES,
    )
    assert [row["allowed_product_runtime_file"] for row in _patchlets(workflow)] == ["src/runtime-profile.mjs"] * 5


def test_javascript_verification_file_without_positive_evidence_produces_no_patchlet(tmp_path: Path):
    _, workflow = run_decomposition(
        tmp_path,
        product_file="src/runtime-profile.mjs",
        support_file="src/index.mjs",
        verification_file="test/check-one.mjs",
        slices=JS_SLICES,
    )
    assert "test/check-one.mjs" not in {row["allowed_product_runtime_file"] for row in _patchlets(workflow)}


def test_each_slice_has_one_primary_goal_item(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path)
    assert [row["goal_item_ids"] for row in _patchlets(workflow)] == [[row[0]] for row in PYTHON_SLICES]


def test_each_slice_has_one_proof_obligation(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path)
    assert [row["proof_obligation_ids"] for row in _patchlets(workflow)] == [[row[1]] for row in PYTHON_SLICES]


def test_each_slice_preserves_probe_mapping(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path)
    assert [row["probe_ids"] for row in _patchlets(workflow)] == [[row[2]] for row in PYTHON_SLICES]


def test_each_slice_preserves_function_boundary(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path)
    assert [row["current_slice_boundary"]["symbol"] for row in _patchlets(workflow)] == [row[3] for row in PYTHON_SLICES]


def test_each_slice_preserves_expected_observation(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path)
    assert [row["current_slice_boundary"]["expected_observation"] for row in _patchlets(workflow)] == [row[4] for row in PYTHON_SLICES]


def test_same_file_future_boundaries_are_preserved(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path)
    patchlets = _patchlets(workflow)
    assert patchlets[0]["future_slice_boundaries"]
    assert patchlets[-1]["future_slice_boundaries"] == []


def test_same_file_dependencies_are_sequential(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path)
    patchlets = _patchlets(workflow)
    assert patchlets[0]["dependency_patchlet_ids"] == []
    assert [row["dependency_patchlet_ids"] for row in patchlets[1:]] == [["P0001"], ["P0002"], ["P0003"], ["P0004"]]
