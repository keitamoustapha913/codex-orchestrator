from __future__ import annotations

from pathlib import Path

from conftest import read_json

from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.state import load_state, sha256_file
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file


def _ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def test_verify_global_maps_results_to_goals_invariants_and_transaction_groups(git_repo: Path):
    from codex_orchestrator.stages.verify_global import verify_global
    from codex_orchestrator.stages.verify_group import verify_all_groups

    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")
    verify_all_groups(ctx)

    result = verify_global(ctx)

    final = read_json(ctx.paths.final_verification_json)
    assert result.done is True
    assert validate_json_file(ctx.paths.final_verification_json, "final_verification.schema.json") == []
    assert final["status"] == "DONE"
    assert final["proven_goal_ids"] == ["G001"]
    assert final["proven_invariant_ids"] == ["I001"]
    assert final["transaction_group_results"][0]["transaction_group_id"] == "TG001"
    assert final["transaction_group_results"][0]["status"] == "PASSED"


def test_verify_global_refuses_done_when_transaction_group_cannot_be_passed(git_repo: Path):
    from codex_orchestrator.stages.verify_global import verify_global

    ctx = _ctx(git_repo)

    result = verify_global(ctx)

    assert result.done is False
    assert read_json(ctx.paths.final_verification_json)["status"] == "FAILED"
    assert load_state(ctx).stage == "FAILURE_CLASSIFICATION_REQUIRED"


def test_verify_global_refuses_done_with_unresolved_required_invariant(git_repo: Path):
    from codex_orchestrator.stages.verify_global import verify_global
    from codex_orchestrator.stages.verify_group import verify_all_groups

    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")
    verify_all_groups(ctx)
    invariants = read_json(ctx.paths.invariants)
    invariants["invariants"][0]["required_probes"] = []
    ctx.paths.invariants.write_text(__import__("json").dumps(invariants, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = verify_global(ctx)

    final = read_json(ctx.paths.final_verification_json)
    assert result.done is False
    assert "I001" in final["unproven_invariant_ids"]


def test_verify_global_refuses_done_with_unresolved_failure_record(git_repo: Path):
    from codex_orchestrator.stages.verify_global import verify_global
    from codex_orchestrator.stages.verify_group import verify_all_groups

    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")
    verify_all_groups(ctx)
    failure = {
        "schema_version": "1.0",
        "kind": "failure_record",
        "failure_id": "F0001",
        "source": "MANUAL_TEST",
        "source_id": "manual",
        "observed_failure": "unresolved failure",
        "blocking_invariant_ids": ["I001"],
        "evidence_ids": ["E001"],
        "graph_node_ids": ["N001"],
        "changed_paths": [],
        "suspected_scope": "inside_known_graph",
        "required_next_step": "classify",
    }
    ctx.paths.failures_dir.mkdir(parents=True, exist_ok=True)
    (ctx.paths.failures_dir / "F0001.json").write_text(__import__("json").dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = verify_global(ctx)

    final = read_json(ctx.paths.final_verification_json)
    assert result.done is False
    assert final["unresolved_failures"] == ["F0001"]


def test_verify_global_records_repair_cycle_evidence(git_repo: Path):
    from codex_orchestrator.stages.verify_global import verify_global
    from codex_orchestrator.stages.verify_group import verify_all_groups

    ctx = _ctx(git_repo)
    state = load_state(ctx)
    state.repair_cycles.append({
        "repair_plan_id": "RP0001",
        "source_failure_ids": ["F0001"],
        "generated_patchlet_ids": ["P0001"],
    })
    from codex_orchestrator.state import save_state
    save_state(ctx, state)
    run_next_patchlet(ctx, worker_mode="mock")
    verify_all_groups(ctx)

    verify_global(ctx)

    final = read_json(ctx.paths.final_verification_json)
    assert final["repair_cycles"][0]["repair_plan_id"] == "RP0001"


def test_verify_global_validates_probe_artifact_refs_through_reports(git_repo: Path):
    from codex_orchestrator.stages.verify_global import verify_global
    from codex_orchestrator.stages.verify_group import verify_all_groups

    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")
    verify_all_groups(ctx)
    (ctx.paths.probe_dir / "P0001" / "run_001" / "cleanup_proof.json").unlink()

    result = verify_global(ctx)

    assert result.done is False
    assert read_json(ctx.paths.final_verification_json)["status"] == "FAILED"


def test_verify_global_is_read_only_for_product_runtime_files(git_repo: Path):
    from codex_orchestrator.stages.verify_global import verify_global
    from codex_orchestrator.stages.verify_group import verify_all_groups

    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")
    verify_all_groups(ctx)
    app_hash_before = sha256_file(ctx.root / "app.py")

    verify_global(ctx)

    assert sha256_file(ctx.root / "app.py") == app_hash_before


def test_cli_verify_global_outputs_status_and_artifact_paths(git_repo: Path, tmp_path: Path):
    import os
    import subprocess
    import sys

    from codex_orchestrator.stages.verify_group import verify_all_groups

    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock")
    verify_all_groups(ctx)
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    result = subprocess.run(
        [sys.executable, "-m", "codex_orchestrator", "verify-global", "--repo", str(git_repo)],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "DONE" in result.stdout
    assert "final_verification" not in result.stderr
