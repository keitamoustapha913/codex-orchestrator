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
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.workflow_identity import build_workflow_identity, write_workflow_identity


def _ctx(git_repo: Path, monkeypatch=None, timeout: str | None = None):
    if timeout and monkeypatch:
        monkeypatch.setenv("CODEX_PATCHLET_TIMEOUT_SECONDS", timeout)
    (git_repo / "service.py").write_text("def value():\n    return 'ok'\n", encoding="utf-8")
    (git_repo / "app.py").write_text("from service import value\n\ndef main():\n    return value()\n", encoding="utf-8")
    (git_repo / "master_prompt.md").write_text("Make app return me and prove it.\n", encoding="utf-8")
    run(["git", "add", "."], git_repo)
    run(["git", "commit", "-m", "prompt scope target"], git_repo)
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    write_workflow_identity(
        ctx,
        build_workflow_identity(ctx, master=git_repo / "master_prompt.md", worker_mode="mock", use_worktree=True, until="DONE", workflow_id="WF000001", run_id="R0001"),
    )
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    return ctx


def _prompt(ctx) -> str:
    return (ctx.paths.runs_dir / "P0001_attempt1" / "codex_task_prompt.md").read_text(encoding="utf-8")


def test_worker_prompt_includes_work_slice_id(git_repo: Path):
    assert "Work slice ID:" in _prompt(_ctx(git_repo))


def test_worker_prompt_includes_single_allowed_file(git_repo: Path):
    text = _prompt(_ctx(git_repo))
    assert "Allowed product/runtime file:" in text
    assert "Allowed edit path:" in text


def test_worker_prompt_forbids_other_product_files(git_repo: Path):
    assert "Forbidden product/runtime edit paths:" in _prompt(_ctx(git_repo))


def test_worker_prompt_includes_time_budget_seconds(git_repo: Path):
    assert "Time budget seconds: `600`" in _prompt(_ctx(git_repo))


def test_worker_prompt_includes_soft_deadline(git_repo: Path):
    assert "Soft deadline seconds:" in _prompt(_ctx(git_repo))


def test_worker_prompt_mentions_small_bounded_work_unit(git_repo: Path):
    assert "small bounded work unit" in _prompt(_ctx(git_repo))


def test_worker_prompt_says_do_not_solve_unrelated_slices(git_repo: Path):
    assert "Do not attempt to solve unrelated work slices." in _prompt(_ctx(git_repo))


def test_worker_prompt_says_do_not_require_memory_compacting(git_repo: Path):
    assert "Do not compact memory" in _prompt(_ctx(git_repo))


def test_work_slice_contract_written(git_repo: Path):
    ctx = _ctx(git_repo)
    assert (ctx.paths.runs_dir / "P0001_attempt1/worker_memory/WORK_SLICE_CONTRACT.md").exists()


def test_task_contract_references_work_slice_contract(git_repo: Path):
    ctx = _ctx(git_repo)
    assert "WORK_SLICE_CONTRACT.md" in (ctx.paths.runs_dir / "P0001_attempt1/worker_memory/TASK_CONTRACT.md").read_text(encoding="utf-8")


def test_live_memory_references_work_slice_contract(git_repo: Path):
    ctx = _ctx(git_repo)
    assert "work slice contract" in (ctx.paths.runs_dir / "P0001_attempt1/worker_memory/LIVE_MEMORY.md").read_text(encoding="utf-8")


def test_write_these_files_references_work_slice_contract(git_repo: Path):
    ctx = _ctx(git_repo)
    assert "WORK_SLICE_CONTRACT.md" in (ctx.paths.runs_dir / "P0001_attempt1/worker_memory/WRITE_THESE_FILES.md").read_text(encoding="utf-8")


def test_prompt_budget_matches_codex_patchlet_timeout_env(git_repo: Path, monkeypatch):
    ctx = _ctx(git_repo, monkeypatch, timeout="120")
    assert "Time budget seconds: `120`" in _prompt(ctx)
    assert read_json(ctx.paths.workflow_dir / "decomposition/patchlet_plan.json")["patchlets"][0]["time_budget_seconds"] == 120


def test_run_manifest_timeout_matches_patchlet_plan(git_repo: Path):
    ctx = _ctx(git_repo)
    latest = read_json(ctx.paths.run_manifest)["runs"][-1]
    assert latest["timeout_seconds"] == read_json(ctx.paths.workflow_dir / "decomposition/patchlet_plan.json")["patchlets"][0]["time_budget_seconds"]
