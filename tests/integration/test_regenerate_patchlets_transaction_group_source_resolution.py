from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from codex_orchestrator.errors import StagePreconditionError
from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.stages.apply_repair import apply_repair
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.classify_failures import classify_failures
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.plan_repair import plan_repair
from codex_orchestrator.stages.regenerate_patchlets import regenerate_patchlets
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo


def _setup_regeneration_required_ctx(git_repo: Path, *, include_source_patchlets: bool = True):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    run_next_patchlet(ctx, worker_mode="mock")
    index = read_json(ctx.paths.patchlet_index)
    source_patchlet = index["patchlets"][0]
    group_id = source_patchlet["transaction_group_id"]
    failure = {
        "schema_version": "1.0",
        "kind": "failure_record",
        "failure_id": "F0001",
        "source": "TRANSACTION_GROUP_VERIFICATION_FAILED",
        "source_type": "transaction_group",
        "source_id": group_id,
        "source_transaction_group_id": group_id,
        "observed_failure": "Transaction group failed because wrapper gate was not accepted",
        "blocking_invariant_ids": source_patchlet.get("invariant_ids", []),
        "evidence_ids": [],
        "graph_node_ids": [],
        "changed_paths": [],
        "suspected_scope": "inside_known_graph",
        "required_next_step": "classify",
    }
    if include_source_patchlets:
        failure["source_patchlet_ids"] = [source_patchlet["patchlet_id"]]
    write_json(ctx.paths.failures_dir / "F0001.json", failure)
    classify_failures(ctx)
    plan_repair(ctx)
    apply_repair(ctx)
    return ctx, group_id, source_patchlet["patchlet_id"]


def test_regenerate_patchlets_does_not_treat_tg_id_as_patchlet_id(git_repo: Path):
    ctx, group_id, _ = _setup_regeneration_required_ctx(git_repo)

    result = regenerate_patchlets(ctx, from_repair_plan="latest")

    assert result["patchlet_ids"] == ["P0002"]
    repair_prompt = (ctx.root / ".codex-orchestrator/subprompts/0002_repair.md").read_text(encoding="utf-8")
    assert f"missing source patchlet manifest for {group_id}" not in repair_prompt


def test_regenerate_patchlets_expands_transaction_group_failure_to_member_patchlets(git_repo: Path):
    ctx, _, source_patchlet_id = _setup_regeneration_required_ctx(git_repo)

    regenerate_patchlets(ctx, from_repair_plan="latest")
    repair_patchlet = read_json(ctx.paths.patchlet_index)["patchlets"][-1]

    assert repair_patchlet["source_patchlet_ids"] == [source_patchlet_id]


def test_regenerate_patchlets_uses_member_patchlet_manifest_for_tg_failure(git_repo: Path):
    ctx, _, _ = _setup_regeneration_required_ctx(git_repo)

    regenerate_patchlets(ctx, from_repair_plan="latest")
    repair_patchlet = read_json(ctx.paths.patchlet_index)["patchlets"][-1]

    assert repair_patchlet["allowed_product_runtime_file"] == "app.py"


def test_regenerate_patchlets_structured_failure_when_tg_mapping_missing(git_repo: Path):
    ctx, group_id, _ = _setup_regeneration_required_ctx(git_repo, include_source_patchlets=False)
    groups = read_json(ctx.paths.transaction_groups)
    groups["transaction_groups"][0].pop("patchlet_ids", None)
    write_json(ctx.paths.transaction_groups, groups)

    with pytest.raises(StagePreconditionError) as excinfo:
        regenerate_patchlets(ctx, from_repair_plan="latest")

    assert "transaction_group_source_mapping_missing" in str(excinfo.value)
    assert group_id in str(excinfo.value)


def test_regenerate_patchlets_error_message_mentions_transaction_group_mapping_not_missing_patchlet_tg001(git_repo: Path):
    ctx, group_id, _ = _setup_regeneration_required_ctx(git_repo, include_source_patchlets=False)
    groups = read_json(ctx.paths.transaction_groups)
    groups["transaction_groups"][0].pop("patchlet_ids", None)
    write_json(ctx.paths.transaction_groups, groups)

    with pytest.raises(StagePreconditionError) as excinfo:
        regenerate_patchlets(ctx, from_repair_plan="latest")

    assert "transaction_group_source_mapping_missing" in str(excinfo.value)
    assert f"missing source patchlet manifest for {group_id}" not in str(excinfo.value)


def test_verified_no_change_wrapper_gate_failure_does_not_generate_product_edit_against_target_root(git_repo: Path):
    ctx, _, _ = _setup_regeneration_required_ctx(git_repo)

    regenerate_patchlets(ctx, from_repair_plan="latest")
    status = subprocess.run(
        ["git", "-C", str(ctx.root), "status", "--short", "--", "app.py"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert status.stdout.strip() == ""


def test_verified_no_change_wrapper_gate_failure_preserves_no_blind_retry(git_repo: Path):
    ctx, _, _ = _setup_regeneration_required_ctx(git_repo)

    regenerate_patchlets(ctx, from_repair_plan="latest")
    repair_patchlet = read_json(ctx.paths.patchlet_index)["patchlets"][-1]
    repair_prompt = (ctx.root / repair_patchlet["subprompt_path"]).read_text(encoding="utf-8")

    assert "Do not blind retry" in repair_prompt
