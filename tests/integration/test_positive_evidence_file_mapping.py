from __future__ import annotations

import hashlib
from pathlib import Path

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.work_decomposition import build_work_decomposition_plan


PYTHON_SLICES = [
    ("GI001", "PO001", "GP001", "codename", "zephyr-42"),
    ("GI002", "PO002", "GP002", "batch_limit", "19"),
    ("GI003", "PO003", "GP003", "audit_enabled", "True"),
    ("GI004", "PO004", "GP004", "storage_mode", "append-only"),
    ("GI005", "PO005", "GP005", "fallback_action", "isolate"),
]


JS_SLICES = [
    ("GI001", "PO001", "GP001", "region", "eu-central"),
    ("GI002", "PO002", "GP002", "timeoutMs", "19000"),
    ("GI003", "PO003", "GP003", "compression", "br"),
    ("GI004", "PO004", "GP004", "cacheMode", "immutable"),
    ("GI005", "PO005", "GP005", "authStrategy", "isolated"),
]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _goal_and_proof(
    *,
    product_file: str,
    slices=PYTHON_SLICES,
    support_file: str | None = None,
    variant: str = "primary",
    target_files: list[str] | None = None,
):
    goals = []
    obligations = []
    probes = []
    for index, (gid, oid, pid, symbol, expected) in enumerate(slices, start=1):
        target = target_files[index - 1] if target_files and index <= len(target_files) else product_file
        if variant == "explicit_support" and index == 1 and support_file:
            target = support_file
        if variant == "unmatched_goal" and index == 1:
            target = "src/missing-target.txt"
        boundaries = [target]
        if variant == "ambiguous" and index == 1:
            boundaries = [target, "src/ambiguous-peer.txt"]
        goals.append({
            "goal_item_id": gid,
            "source_span_ids": ["MPS001"],
            "goal_type": "behavioral_change",
            "subject": symbol,
            "desired_state": f"{symbol} -> {expected}",
            "must_change_product": "true",
            "acceptance_meaning": f"{pid} passes",
            "required": True,
            "target_boundaries": boundaries,
            "affected_runtime_boundaries": boundaries,
            "entrypoints": [f"{target}:{symbol}"],
            "metadata": {"symbol": symbol, "expected_observation": expected},
        })
        obligations.append({
            "obligation_id": oid,
            "goal_item_ids": [gid],
            "source_span_ids": ["MPS001"],
            "required": True,
            "proof_strategy": "executable_probe",
            "proof_kind": "executable_probe",
            "status": "UNPROVEN",
            "evidence_requirements": ["exact_probe"],
            "claim": f"{target} {symbol}={expected}",
            "expected": f"{symbol}={expected}",
            "target_boundaries": boundaries,
            "affected_runtime_boundaries": boundaries,
            "entrypoints": [f"{target}:{symbol}"],
            "metadata": {"symbol": symbol, "expected_observation": expected},
        })
        if not (variant == "missing_probe" and index == 1):
            probes.append({
                "probe_id": pid,
                "obligation_ids": [oid],
                "probe_kind": "test",
                "owner": "model_planned_orchestrator_validated",
                "execution_context": "integration_candidate",
                "side_effect_policy": "no_product_mutation",
                "rerunnable_by_orchestrator": True,
                "status": "PLANNED",
                "command": f"/bin/true # {symbol}",
                "expected_observation": {"type": "exit_code_zero", "value": expected},
            })
    return goals, obligations, probes


def run_decomposition(
    tmp_path: Path,
    *,
    product_file: str = "src/runtime_profile.py",
    support_file: str = "src/__init__.py",
    verification_file: str = "tests/test_runtime_profile.py",
    slices=PYTHON_SLICES,
    variant: str = "primary",
    extra_products: list[str] | None = None,
):
    repo = tmp_path / "repo"
    workflow = repo / ".codex-orchestrator"
    decomp = workflow / "decomposition"
    decomp.mkdir(parents=True)
    _write(repo / "master_prompt.md", "Master prompt\n")
    _write(repo / product_file, "\n".join(f"def {row[3]}(): pass" for row in slices) + "\n")
    _write(repo / support_file, "support marker\n")
    _write(repo / verification_file, "verification marker\n")
    if variant == "ambiguous":
        _write(repo / "src/ambiguous-peer.txt", "peer\n")
    for file in extra_products or []:
        _write(repo / file, "value=legacy\n")
    target_files = extra_products if variant == "multi_file" and extra_products else None
    goals, obligations, probes = _goal_and_proof(
        product_file=product_file,
        slices=slices,
        support_file=support_file,
        variant=variant,
        target_files=target_files,
    )
    prompt_hash = hashlib.sha256((repo / "master_prompt.md").read_bytes()).hexdigest()
    goal = {
        "schema_version": "1.0",
        "kind": "goal_interpretation",
        "master_prompt_sha256": prompt_hash,
        "master_prompt_frozen_path": ".codex-orchestrator/master_prompt_frozen.json",
        "interpretation_status": "CONCORDANT",
        "goal_summary": "test",
        "goal_items": goals,
        "proof_not_claimed_here": True,
    }
    proof = {
        "schema_version": "1.0",
        "kind": "proof_obligations",
        "master_prompt_sha256": prompt_hash,
        "obligations": obligations,
    }
    probe = {
        "schema_version": "1.0",
        "kind": "probe_plan",
        "master_prompt_sha256": prompt_hash,
        "probes": probes,
    }
    write_json(workflow / "probe_plan.json", probe)
    files = [product_file, support_file, verification_file, "master_prompt.md"] + (extra_products or [])
    if variant == "ambiguous":
        files.append("src/ambiguous-peer.txt")
    inventory = {
        "schema_version": "1.0",
        "kind": "inventory_graph",
        "nodes": [
            {"id": f"N{index:03d}", "file": file, "symbol": None, "role": "runtime_boundary", "evidence_ids": [f"E{index:03d}"], "confidence": "medium"}
            for index, file in enumerate(files, start=1)
        ],
        "edges": [],
    }
    master = {"sha256": prompt_hash, "workflow_id": None, "run_id": None}
    build_work_decomposition_plan(
        repo_root=repo,
        workflow_root=workflow,
        inventory_graph=inventory,
        proof_obligations=proof,
        goal_interpretation=goal,
        master_prompt_frozen=master,
        timeout_seconds=600,
    )
    return repo, workflow


def _patchlets(workflow: Path):
    return read_json(workflow / "decomposition" / "patchlet_plan.json")["patchlets"]


def test_unmatched_support_file_receives_no_goal_ids(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path)
    mapping = read_json(workflow / "decomposition" / "file_mapping_result.json")
    support = next(row for row in mapping["unmatched_candidate_files"] if row["file"] == "src/__init__.py")
    assert support["goal_item_ids"] == []


def test_unmatched_support_file_receives_no_obligation_ids(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path)
    mapping = read_json(workflow / "decomposition" / "file_mapping_result.json")
    support = next(row for row in mapping["unmatched_candidate_files"] if row["file"] == "src/__init__.py")
    assert support["proof_obligation_ids"] == []


def test_unmatched_support_file_receives_no_probe_ids(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path)
    mapping = read_json(workflow / "decomposition" / "file_mapping_result.json")
    support = next(row for row in mapping["unmatched_candidate_files"] if row["file"] == "src/__init__.py")
    assert support["probe_ids"] == []


def test_unmatched_support_file_produces_no_work_slice(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path)
    slices = read_json(workflow / "decomposition" / "work_slices.json")["slices"]
    assert "src/__init__.py" not in {row["allowed_product_runtime_file"] for row in slices}


def test_unmatched_support_file_produces_no_patchlet(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path)
    assert "src/__init__.py" not in {row["allowed_product_runtime_file"] for row in _patchlets(workflow)}


def test_explicit_support_file_goal_remains_selectable(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path, variant="explicit_support")
    assert "src/__init__.py" in {row["allowed_product_runtime_file"] for row in _patchlets(workflow)}


def test_unmatched_goal_is_recorded_not_fanned_out(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path, variant="unmatched_goal")
    mapping = read_json(workflow / "decomposition" / "file_mapping_result.json")
    assert mapping["accepted"] is False
    assert "GI001" in mapping["unmapped_goal_item_ids"]
    assert _patchlets(workflow) == []


def test_ambiguous_multi_file_goal_is_not_arbitrarily_resolved(tmp_path: Path):
    _, workflow = run_decomposition(tmp_path, variant="ambiguous")
    mapping = read_json(workflow / "decomposition" / "file_mapping_result.json")
    assert mapping["accepted"] is False
    assert "GI001" in mapping["ambiguous_goal_item_ids"]
    assert _patchlets(workflow) == []
