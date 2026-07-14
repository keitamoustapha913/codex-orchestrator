from __future__ import annotations

import hashlib
from pathlib import Path

from conftest import read_json, run

from codex_orchestrator.jsonio import write_json
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file
from codex_orchestrator.workflow_identity import build_workflow_identity, write_workflow_identity


def _write_planning(ctx, *, targets: list[tuple[str, str, str]]) -> None:
    prompt_hash = hashlib.sha256((ctx.root / "master_prompt.md").read_bytes()).hexdigest()
    goals = []
    obligations = []
    probes = []
    for index, (target_file, symbol, expected) in enumerate(targets, start=1):
        goal_id = f"GI{index:03d}"
        obligation_id = f"PO{index:03d}"
        probe_id = f"GP{index:03d}"
        boundaries = [target_file]
        goals.append({
            "goal_item_id": goal_id,
            "source_span_ids": ["MPS001"],
            "goal_type": "behavioral_change",
            "subject": symbol,
            "desired_state": f"{symbol} -> {expected}",
            "must_change_product": "true",
            "acceptance_meaning": f"{probe_id} passes",
            "required": True,
            "target_boundaries": boundaries,
            "affected_runtime_boundaries": boundaries,
            "entrypoints": [f"{target_file}:{symbol}"],
            "metadata": {"symbol": symbol, "expected_observation": expected},
        })
        obligations.append({
            "obligation_id": obligation_id,
            "goal_item_ids": [goal_id],
            "source_span_ids": ["MPS001"],
            "required": True,
            "proof_strategy": "executable_probe",
            "proof_kind": "executable_probe",
            "status": "UNPROVEN",
            "evidence_requirements": ["exact_probe"],
            "claim": f"{target_file} {symbol}={expected}",
            "expected": f"{symbol}={expected}",
            "target_boundaries": boundaries,
            "affected_runtime_boundaries": boundaries,
            "entrypoints": [f"{target_file}:{symbol}"],
            "metadata": {"symbol": symbol, "expected_observation": expected},
        })
        probes.append({
            "probe_id": probe_id,
            "obligation_ids": [obligation_id],
            "probe_kind": "test",
            "owner": "model_planned_orchestrator_validated",
            "execution_context": "integration_candidate",
            "side_effect_policy": "no_product_mutation",
            "rerunnable_by_orchestrator": True,
            "status": "PLANNED",
            "command": f"/bin/true # {symbol}",
            "expected_observation": {"type": "exit_code_zero", "value": expected},
        })
    write_json(ctx.paths.workflow_dir / "goal_interpretation.json", {
        "schema_version": "1.0",
        "kind": "goal_interpretation",
        "master_prompt_sha256": prompt_hash,
        "master_prompt_frozen_path": ".codex-orchestrator/master_prompt_frozen.json",
        "interpretation_status": "CONCORDANT",
        "goal_summary": "positive-evidence regression",
        "goal_items": goals,
        "proof_not_claimed_here": True,
    })
    write_json(ctx.paths.workflow_dir / "proof_obligations.json", {
        "schema_version": "1.0",
        "kind": "proof_obligations",
        "master_prompt_sha256": prompt_hash,
        "obligations": obligations,
    })
    write_json(ctx.paths.workflow_dir / "probe_plan.json", {
        "schema_version": "1.0",
        "kind": "probe_plan",
        "master_prompt_sha256": prompt_hash,
        "probes": probes,
    })
    write_json(ctx.paths.workflow_dir / "provability" / "provability_result.json", {
        "schema_version": "1.0",
        "kind": "provability_result",
        "workflow_id": "WF000001",
        "run_id": "R0001",
        "master_prompt_sha256": prompt_hash,
        "provability_stage": "pre_patchlet",
        "provability_status": "PROVABLE",
        "overall_goal_status": "UNPROVEN",
        "can_start_product_patchlets": True,
        "probe_plan_required": True,
        "proof_obligation_count": len(obligations),
        "required_capabilities": ["local_execution"],
        "available_capabilities": ["local_execution"],
        "missing_capabilities": [],
        "blocking_reasons": [],
        "reasons": ["test helper supplied schema-valid positive-evidence planning artifacts"],
        "goal_interpretation_path": ".codex-orchestrator/goal_interpretation/goal_interpretation.json",
    })


def _compile(repo: Path):
    ctx = resolve_target_repo(repo=repo)
    init_workflow(ctx, master=repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    write_workflow_identity(
        ctx,
        build_workflow_identity(
            ctx,
            master=repo / "master_prompt.md",
            worker_mode="mock",
            use_worktree=True,
            until="DONE",
            workflow_id="WF000001",
            run_id="R0001",
        ),
    )
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    repo_files = {path.name for path in repo.iterdir() if path.is_file()}
    if {"pipeline.py", "service.py", "formatter.py", "validator.py"}.issubset(repo_files):
        _write_planning(ctx, targets=[
            ("app.py", "entrypoint", "me"),
            ("pipeline.py", "pipeline", "me"),
            ("service.py", "transform", "me"),
            ("formatter.py", "format_value", "me"),
            ("validator.py", "is_allowed", "me"),
        ])
    else:
        _write_planning(ctx, targets=[
            ("app.py", "parse_input", "parsed"),
            ("app.py", "validate_input", "valid"),
            ("app.py", "transform_value", "me"),
            ("app.py", "format_output", "me"),
        ])
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _complex_repo(git_repo: Path) -> Path:
    files = {
        "app.py": "from pipeline import run_pipeline\n\ndef main():\n    return run_pipeline('raw')\n",
        "pipeline.py": "from service import transform\n\ndef run_pipeline(value):\n    return transform(value)\n",
        "service.py": "from formatter import format_value\nfrom validator import is_allowed\n\ndef transform(value):\n    if not is_allowed(value):\n        return 'not ok'\n    return format_value(value)\n",
        "formatter.py": "def format_value(value):\n    return 'ok'\n",
        "validator.py": "def is_allowed(value):\n    return True\n",
        "config.py": "TARGET_VALUE = 'me'\n",
        "master_prompt.md": "Make the app pipeline return me through the entrypoint and prove it.\n",
    }
    for rel, content in files.items():
        (git_repo / rel).write_text(content, encoding="utf-8")
    run(["git", "add", "."], git_repo)
    run(["git", "commit", "-m", "complex target"], git_repo)
    return git_repo


def _same_file_repo(git_repo: Path) -> Path:
    (git_repo / "app.py").write_text(
        "def parse_input(value):\n    return value\n\n"
        "def validate_input(value):\n    return True\n\n"
        "def transform_value(value):\n    return value\n\n"
        "def format_output(value):\n    return 'ok'\n\n"
        "def main():\n    return format_output(transform_value(parse_input('raw')))\n",
        encoding="utf-8",
    )
    (git_repo / "master_prompt.md").write_text(
        "Make app process the input through validation, transformation, and formatting so main returns me and prove it.\n",
        encoding="utf-8",
    )
    run(["git", "add", "."], git_repo)
    run(["git", "commit", "-m", "same file target"], git_repo)
    return git_repo


def test_complex_multi_file_target_generates_at_least_five_patchlets(git_repo: Path):
    ctx = _compile(_complex_repo(git_repo))
    index = read_json(ctx.paths.patchlet_index)
    assert len(index["patchlets"]) >= 5


def test_multi_patchlet_generation_uses_real_decomposition_artifacts(git_repo: Path):
    ctx = _compile(_complex_repo(git_repo))
    assert (ctx.paths.workflow_dir / "decomposition/work_decomposition_plan.json").exists()
    assert (ctx.paths.workflow_dir / "decomposition/work_slices.json").exists()
    assert (ctx.paths.workflow_dir / "decomposition/patchlet_plan.json").exists()


def test_every_generated_patchlet_has_exactly_one_allowed_file(git_repo: Path):
    ctx = _compile(_complex_repo(git_repo))
    for patchlet in read_json(ctx.paths.patchlet_index)["patchlets"]:
        assert patchlet["allowed_product_runtime_file"]
        assert patchlet["allowed_product_runtime_files"] == [patchlet["allowed_product_runtime_file"]]


def test_generated_patchlets_have_work_slice_ids(git_repo: Path):
    ctx = _compile(_complex_repo(git_repo))
    assert all(p.get("work_slice_id") for p in read_json(ctx.paths.patchlet_index)["patchlets"])


def test_generated_patchlets_have_time_budget_seconds(git_repo: Path):
    ctx = _compile(_complex_repo(git_repo))
    assert all(p.get("time_budget_seconds") == 600 for p in read_json(ctx.paths.patchlet_index)["patchlets"])


def test_generated_patchlets_have_dependency_metadata(git_repo: Path):
    ctx = _compile(_complex_repo(git_repo))
    assert any(p.get("dependency_patchlet_ids") for p in read_json(ctx.paths.patchlet_index)["patchlets"])


def test_generated_patchlets_reference_proof_obligations(git_repo: Path):
    ctx = _compile(_complex_repo(git_repo))
    proof_ids = [
        p.get("proof_obligation_ids", [])
        for p in read_json(ctx.paths.patchlet_index)["patchlets"]
    ]
    assert all(len(row) == 1 for row in proof_ids)
    assert sorted(row[0] for row in proof_ids) == ["PO001", "PO002", "PO003", "PO004", "PO005"]


def test_same_file_can_generate_multiple_ordered_patchlets(git_repo: Path):
    ctx = _compile(_same_file_repo(git_repo))
    patchlets = read_json(ctx.paths.patchlet_index)["patchlets"]
    app_patchlets = [p for p in patchlets if p["allowed_product_runtime_file"] == "app.py"]
    assert len(app_patchlets) >= 2
    assert any(p.get("dependency_patchlet_ids") for p in app_patchlets[1:])


def test_same_file_multiple_patchlets_are_not_parallel_by_default(git_repo: Path):
    ctx = _compile(_same_file_repo(git_repo))
    graph = read_json(ctx.paths.workflow_dir / "decomposition/dependency_graph.json")
    assert graph["edges"]


def test_multi_patchlet_plan_writes_transaction_group_plan(git_repo: Path):
    ctx = _compile(_complex_repo(git_repo))
    assert (ctx.paths.workflow_dir / "decomposition/transaction_group_plan.json").exists()


def test_multi_patchlet_plan_updates_goal_progress(git_repo: Path):
    ctx = _compile(_complex_repo(git_repo))
    from codex_orchestrator.goal_progress import update_goal_progress

    update_goal_progress(workflow_root=ctx.paths.workflow_dir, event_reason="test", workflow_iteration=1)
    assert read_json(ctx.paths.workflow_dir / "goal_progress.json")["decomposition"]["patchlet_count"] >= 5


def test_no_manual_artifact_tampering_required(git_repo: Path):
    ctx = _compile(_complex_repo(git_repo))
    assert validate_json_file(ctx.paths.workflow_dir / "decomposition/patchlet_plan.json", "patchlet_plan.schema.json") == []
