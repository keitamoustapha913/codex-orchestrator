from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from conftest import read_json

from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.classify_failures import classify_failures
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.plan_repair import plan_repair
from codex_orchestrator.state import load_state
from codex_orchestrator.target_repo import resolve_target_repo


def _base_ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _write_failure(ctx, *, suspected_scope: str, source: str = "MANUAL_TEST", failure_id: str = "F0001"):
    record = {
        "schema_version": "1.0",
        "kind": "failure_record",
        "failure_id": failure_id,
        "source": source,
        "source_id": "manual-source",
        "observed_failure": f"{suspected_scope} observed",
        "blocking_invariant_ids": ["I001"],
        "evidence_ids": ["E001"],
        "graph_node_ids": ["N001"],
        "changed_paths": ["app.py"],
        "suspected_scope": suspected_scope,
        "required_next_step": "classify",
    }
    ctx.paths.failures_dir.mkdir(parents=True, exist_ok=True)
    (ctx.paths.failures_dir / f"{failure_id}.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _outside_known_graph_ctx(git_repo: Path):
    ctx = _base_ctx(git_repo)
    _write_failure(ctx, suspected_scope="outside_known_graph")
    classify_failures(ctx)
    plan_repair(ctx)
    return ctx


def test_rediscover_impacted_scope_writes_durable_rediscovery_record(git_repo: Path):
    from codex_orchestrator.stages.rediscover import rediscover

    ctx = _outside_known_graph_ctx(git_repo)

    record = rediscover(ctx, scope="impacted")

    record_path = ctx.paths.workflow_dir / "rediscovery" / "RD0001.json"
    assert record_path.exists()
    assert record["rediscovery_id"] == "RD0001"
    assert record["scope"] == "impacted"
    assert record["source_repair_plan_id"] == "RP0001"
    assert record["source_failure_ids"] == ["F0001"]
    assert (ctx.paths.workflow_dir / "census" / "rediscovery_RD0001").exists()
    assert load_state(ctx).stage == "INVENTORY_REBUILD_REQUIRED"


def test_rediscover_impacted_scope_preserves_prior_failure_and_repair_artifacts(git_repo: Path):
    from codex_orchestrator.stages.rediscover import rediscover

    ctx = _outside_known_graph_ctx(git_repo)
    failure_path = ctx.paths.failures_dir / "F0001.json"
    repair_plan_path = ctx.paths.repair_plans_dir / "RP0001.json"

    rediscover(ctx, scope="impacted")

    assert failure_path.exists()
    assert repair_plan_path.exists()


def test_rediscover_full_scope_writes_full_scope_record(git_repo: Path):
    from codex_orchestrator.stages.rediscover import rediscover

    ctx = _base_ctx(git_repo)
    _write_failure(ctx, suspected_scope="master_goal_changed", source="MASTER_PROMPT_CHANGED")
    classify_failures(ctx)
    plan_repair(ctx)

    record = rediscover(ctx, scope="full")

    assert record["rediscovery_id"] == "RD0001"
    assert record["scope"] == "full"
    assert load_state(ctx).stage == "INVENTORY_REBUILD_REQUIRED"


def test_rebuild_inventory_impacted_preserves_unaffected_graph_nodes(git_repo: Path):
    from codex_orchestrator.stages.rediscover import rediscover
    from codex_orchestrator.stages.rebuild_inventory import rebuild_inventory

    ctx = _outside_known_graph_ctx(git_repo)
    before_nodes = [node["id"] for node in read_json(ctx.paths.inventory_graph)["nodes"]]
    rediscover(ctx, scope="impacted")

    rebuild_inventory(ctx, scope="impacted")

    after_nodes = [node["id"] for node in read_json(ctx.paths.inventory_graph)["nodes"]]
    assert set(before_nodes).issubset(set(after_nodes))


def test_rebuild_inventory_impacted_advances_to_patchlet_regeneration_required(git_repo: Path):
    from codex_orchestrator.stages.rediscover import rediscover
    from codex_orchestrator.stages.rebuild_inventory import rebuild_inventory

    ctx = _outside_known_graph_ctx(git_repo)
    rediscover(ctx, scope="impacted")

    rebuild_inventory(ctx, scope="impacted")

    assert load_state(ctx).stage == "PATCHLET_REGENERATION_REQUIRED"


def test_auto_routes_outside_known_graph_failure_to_partial_rediscovery(git_repo: Path):
    from codex_orchestrator.stages.auto import run_auto

    ctx = _outside_known_graph_ctx(git_repo)

    result = run_auto(ctx, resume=True, until="PATCHLET_REGENERATION_REQUIRED", worker_mode="mock", max_iterations=10)

    assert result.stage == "PATCHLET_REGENERATION_REQUIRED"
    assert (ctx.paths.workflow_dir / "rediscovery" / "RD0001.json").exists()


def test_cli_rediscover_impacted_and_full_scope(git_repo: Path, tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    impacted_ctx = _outside_known_graph_ctx(git_repo)
    impacted = subprocess.run(
        [sys.executable, "-m", "codex_orchestrator", "rediscover", "--repo", str(git_repo), "--scope", "impacted"],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert impacted.returncode == 0, impacted.stderr
    assert "RD0001" in impacted.stdout

    full_repo = tmp_path / "full-target"
    subprocess.run(["cp", "-R", str(git_repo), str(full_repo)], check=True)
    full_ctx = _base_ctx(full_repo)
    _write_failure(full_ctx, suspected_scope="master_goal_changed", source="MASTER_PROMPT_CHANGED")
    classify_failures(full_ctx)
    plan_repair(full_ctx)
    full = subprocess.run(
        [sys.executable, "-m", "codex_orchestrator", "rediscover", "--repo", str(full_repo), "--scope", "full"],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert full.returncode == 0, full.stderr
    assert "full" in full.stdout


def test_cli_rebuild_inventory_impacted_scope(git_repo: Path, tmp_path: Path):
    from codex_orchestrator.stages.rediscover import rediscover

    ctx = _outside_known_graph_ctx(git_repo)
    rediscover(ctx, scope="impacted")
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    result = subprocess.run(
        [sys.executable, "-m", "codex_orchestrator", "rebuild-inventory", "--repo", str(git_repo), "--scope", "impacted"],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "PATCHLET_REGENERATION_REQUIRED" in result.stdout
