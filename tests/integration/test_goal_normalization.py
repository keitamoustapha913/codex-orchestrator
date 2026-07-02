from __future__ import annotations

from pathlib import Path

from conftest import read_json

from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.state import sha256_file
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file


def _ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    return ctx


def test_normalize_master_prompt_writes_schema_valid_goal_spec_with_stable_ids(git_repo: Path):
    ctx = _ctx(git_repo)

    normalize_master_prompt(ctx)

    goal_spec = read_json(ctx.paths.goal_spec)
    assert validate_json_file(ctx.paths.goal_spec, "goal_spec.schema.json") == []
    assert goal_spec["kind"] == "goal_spec"
    assert goal_spec["success_goals"][0]["goal_id"] == "G001"
    assert goal_spec["target_invariants"][0]["invariant_id"] == "I001"


def test_normalize_includes_master_prompt_sha256(git_repo: Path):
    ctx = _ctx(git_repo)

    normalize_master_prompt(ctx)

    goal_spec = read_json(ctx.paths.goal_spec)
    assert goal_spec["master_prompt_sha256"] == sha256_file(ctx.paths.master_prompt)


def test_normalize_extracts_or_defaults_success_goal_and_invariant(git_repo: Path):
    (git_repo / "master_prompt.md").write_text(
        "# Master Prompt\n\n"
        "Success goals:\n"
        "- G001: The app should stay runnable.\n\n"
        "Target invariants:\n"
        "- I001: Direct probes must validate the runtime boundary.\n",
        encoding="utf-8",
    )
    ctx = _ctx(git_repo)

    normalize_master_prompt(ctx)

    goal_spec = read_json(ctx.paths.goal_spec)
    assert goal_spec["success_goals"] == [{
        "goal_id": "G001",
        "description": "The app should stay runnable.",
        "status": "PENDING",
    }]
    assert goal_spec["target_invariants"] == [{
        "invariant_id": "I001",
        "description": "Direct probes must validate the runtime boundary.",
        "status": "PENDING",
    }]


def test_normalize_includes_root_cause_probe_proof_requirements(git_repo: Path):
    ctx = _ctx(git_repo)

    normalize_master_prompt(ctx)

    proof_requirements = read_json(ctx.paths.goal_spec)["proof_requirements"]
    assert "ROOT-CAUSE PROBE-ONLY INVESTIGATION" in proof_requirements
    assert "durable probe artifacts" in proof_requirements
    assert "no blind retry" in proof_requirements


def test_normalize_is_idempotent_for_same_master_prompt(git_repo: Path):
    ctx = _ctx(git_repo)

    normalize_master_prompt(ctx)
    first_hash = sha256_file(ctx.paths.goal_spec)
    first_content = read_json(ctx.paths.goal_spec)

    normalize_master_prompt(ctx)
    second_hash = sha256_file(ctx.paths.goal_spec)
    second_content = read_json(ctx.paths.goal_spec)

    assert first_hash == second_hash
    assert first_content == second_content


def test_normalize_detects_changed_master_prompt_hash(git_repo: Path):
    ctx = _ctx(git_repo)

    normalize_master_prompt(ctx)
    first_hash = read_json(ctx.paths.goal_spec)["master_prompt_sha256"]

    (git_repo / "master_prompt.md").write_text(
        "# Master Prompt\n\nMake app return ok and prove it differently.\n",
        encoding="utf-8",
    )
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    second_hash = read_json(ctx.paths.goal_spec)["master_prompt_sha256"]

    assert second_hash != first_hash
