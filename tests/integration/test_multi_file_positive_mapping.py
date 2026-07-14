from __future__ import annotations

from pathlib import Path
import sys

from codex_orchestrator.jsonio import read_json

sys.path.append(str(Path(__file__).resolve().parent))
from test_positive_evidence_file_mapping import PYTHON_SLICES, run_decomposition


def _multi(tmp_path: Path):
    files = [f"src/product_{idx}.txt" for idx in range(1, 6)]
    return run_decomposition(tmp_path, product_file=files[0], extra_products=files, variant="multi_file", slices=PYTHON_SLICES), files


def test_five_explicit_product_files_produce_five_patchlets(tmp_path: Path):
    (repo, workflow), files = _multi(tmp_path)
    plan = read_json(workflow / "decomposition" / "patchlet_plan.json")
    assert len(plan["patchlets"]) == 5


def test_each_multi_file_patchlet_allows_exactly_one_file(tmp_path: Path):
    (_, workflow), files = _multi(tmp_path)
    patchlets = read_json(workflow / "decomposition" / "patchlet_plan.json")["patchlets"]
    assert [row["allowed_product_runtime_files"] for row in patchlets] == [[file] for file in files]


def test_multi_file_mapping_preserves_goal_obligation_probe_linkage(tmp_path: Path):
    (_, workflow), _ = _multi(tmp_path)
    patchlets = read_json(workflow / "decomposition" / "patchlet_plan.json")["patchlets"]
    assert [(p["goal_item_ids"], p["proof_obligation_ids"], p["probe_ids"]) for p in patchlets] == [
        ([gid], [oid], [pid]) for gid, oid, pid, _symbol, _expected in PYTHON_SLICES
    ]


def test_explicit_support_file_target_is_not_blocked(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path, variant="explicit_support")
    assert read_json(workflow / "decomposition" / "file_mapping_result.json")["accepted"] is True
