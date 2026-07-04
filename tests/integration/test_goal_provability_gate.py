from __future__ import annotations

from pathlib import Path

from conftest import read_json, run

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


def _ctx(git_repo: Path, prompt: str):
    (git_repo / "app.py").write_text("def main():\n    return 'ok'\n", encoding="utf-8")
    (git_repo / "master_prompt.md").write_text(prompt + "\n", encoding="utf-8")
    run(["git", "add", "app.py", "master_prompt.md"], git_repo)
    run(["git", "commit", "-m", "setup"], git_repo)
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    write_workflow_identity(ctx, build_workflow_identity(ctx, master=git_repo / "master_prompt.md", worker_mode="mock", use_worktree=True, until="DONE", workflow_id="WF000001", run_id="R0001"))
    normalize_master_prompt(ctx)
    return ctx


def _discover(ctx):
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)


def test_provable_goal_allows_patchlet_compilation(git_repo: Path):
    ctx = _ctx(git_repo, "Make app return me and prove it.")
    _discover(ctx)
    assert compile_patchlets(ctx)["patchlets"]


def test_provability_runs_before_patchlet_compilation(git_repo: Path):
    ctx = _ctx(git_repo, "Make app return me and prove it.")
    assert (ctx.paths.workflow_dir / "provability/provability_result.json").exists()
    assert not ctx.paths.patchlet_index.exists() or not read_json(ctx.paths.patchlet_index).get("patchlets")


def test_ambiguous_goal_stops_before_product_patchlet(git_repo: Path):
    ctx = _ctx(git_repo, "Make this project delightful.")
    _discover(ctx)
    assert compile_patchlets(ctx)["patchlets"] == []


def test_unprovable_goal_safe_fails_before_product_patchlet(git_repo: Path):
    ctx = _ctx(git_repo, "Make this project delightful.")
    assert read_json(ctx.paths.workflow_dir / "provability/provability_result.json")["can_start_product_patchlets"] is False


def test_unprovable_goal_writes_goal_not_provable_result(git_repo: Path):
    ctx = _ctx(git_repo, "Make this project delightful.")
    assert (ctx.paths.workflow_dir / "provability/goal_not_provable_result.json").exists()


def test_blocked_by_missing_capability_stops_before_product_patchlet(git_repo: Path):
    ctx = _ctx(git_repo, "Make this project delightful.")
    assert read_json(ctx.paths.workflow_dir / "provability/provability_result.json")["provability_status"] == "AMBIGUOUS"


def test_needs_discovery_goal_runs_read_only_discovery(git_repo: Path):
    ctx = _ctx(git_repo, "Make app return me and prove it.")
    before = (git_repo / "app.py").read_text(encoding="utf-8")
    _discover(ctx)
    assert (git_repo / "app.py").read_text(encoding="utf-8") == before


def test_read_only_discovery_does_not_edit_product_files(git_repo: Path):
    ctx = _ctx(git_repo, "Make app return me and prove it.")
    before = (git_repo / "app.py").read_text(encoding="utf-8")
    _discover(ctx)
    assert (git_repo / "app.py").read_text(encoding="utf-8") == before


def test_provability_result_written(git_repo: Path):
    ctx = _ctx(git_repo, "Make app return me and prove it.")
    assert (ctx.paths.workflow_dir / "provability/provability_result.json").exists()


def test_provability_result_schema_validates(git_repo: Path):
    ctx = _ctx(git_repo, "Make app return me and prove it.")
    assert validate_json_file(ctx.paths.workflow_dir / "provability/provability_result.json", "provability_result.schema.json") == []


def test_no_worker_codex_invoked_for_unprovable_goal(git_repo: Path):
    ctx = _ctx(git_repo, "Make this project delightful.")
    _discover(ctx)
    compile_patchlets(ctx)
    assert not list(ctx.paths.runs_dir.glob("*"))


def test_late_unprovability_records_defect_signature(git_repo: Path):
    ctx = _ctx(git_repo, "Make this project delightful.")
    result = read_json(ctx.paths.workflow_dir / "provability/goal_not_provable_result.json")
    assert result["failure_signature"] in {"goal_ambiguous", "goal_not_provable"}
