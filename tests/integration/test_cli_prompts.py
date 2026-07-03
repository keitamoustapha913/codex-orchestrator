from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo


def _run_cli(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "codex_orchestrator", *args],
        cwd=cwd,
        env=os.environ.copy(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _ctx_with_prompts(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    return ctx


def test_cxor_prompts_help_exists(git_repo: Path):
    result = _run_cli(["prompts", "--help"], cwd=git_repo)

    assert result.returncode == 0
    assert "--latest" in result.stdout
    assert "--show" in result.stdout


def test_cxor_prompts_lists_prompt_index_entries(git_repo: Path):
    _ctx_with_prompts(git_repo)

    result = _run_cli(["prompts", "--repo", str(git_repo)], cwd=git_repo)

    assert result.returncode == 0
    assert "patchlet_worker_prompt" in result.stdout
    assert "codex_task_prompt.md" in result.stdout


def test_cxor_prompts_json_outputs_structured_prompt_list(git_repo: Path):
    _ctx_with_prompts(git_repo)

    result = _run_cli(["prompts", "--repo", str(git_repo), "--json"], cwd=git_repo)
    payload = json.loads(result.stdout)

    assert payload["kind"] == "prompt_list"
    assert payload["count"] >= 1


def test_cxor_prompts_latest_returns_latest_prompt(git_repo: Path):
    _ctx_with_prompts(git_repo)

    result = _run_cli(["prompts", "--repo", str(git_repo), "--latest", "--json"], cwd=git_repo)
    payload = json.loads(result.stdout)

    assert payload["count"] == 1


def test_cxor_prompts_filter_by_attempt(git_repo: Path):
    _ctx_with_prompts(git_repo)

    result = _run_cli(["prompts", "--repo", str(git_repo), "--attempt", "P0001_attempt1", "--json"], cwd=git_repo)
    payload = json.loads(result.stdout)

    assert payload["count"] == 1
    assert payload["prompts"][0]["attempt_id"] == "P0001_attempt1"


def test_cxor_prompts_filter_by_patchlet(git_repo: Path):
    _ctx_with_prompts(git_repo)

    result = _run_cli(["prompts", "--repo", str(git_repo), "--patchlet", "P0001", "--json"], cwd=git_repo)
    payload = json.loads(result.stdout)

    assert payload["count"] >= 1
    assert all(prompt["patchlet_id"] == "P0001" for prompt in payload["prompts"])


def test_cxor_prompts_filter_by_kind(git_repo: Path):
    _ctx_with_prompts(git_repo)

    result = _run_cli(["prompts", "--repo", str(git_repo), "--kind", "patchlet_worker_prompt", "--json"], cwd=git_repo)
    payload = json.loads(result.stdout)

    assert payload["count"] == 1
    assert payload["prompts"][0]["kind"] == "patchlet_worker_prompt"


def test_cxor_prompts_show_prints_prompt_body(git_repo: Path):
    _ctx_with_prompts(git_repo)

    result = _run_cli(["prompts", "--repo", str(git_repo), "--show", "PR000003"], cwd=git_repo)

    assert result.returncode == 0
    assert "Worker Prompt Pending" in result.stdout


def test_cxor_prompts_show_lines_limits_output(git_repo: Path):
    _ctx_with_prompts(git_repo)

    result = _run_cli(["prompts", "--repo", str(git_repo), "--show", "PR000003", "--lines", "1"], cwd=git_repo)

    assert result.returncode == 0
    assert len(result.stdout.splitlines()) == 1


def test_cxor_prompts_show_missing_prompt_id_returns_clear_error(git_repo: Path):
    _ctx_with_prompts(git_repo)

    result = _run_cli(["prompts", "--repo", str(git_repo), "--show", "PR999999"], cwd=git_repo)

    assert result.returncode == 1
    assert "prompt id not found" in result.stderr


def test_cxor_prompts_handles_missing_prompt_index(git_repo: Path):
    result = _run_cli(["prompts", "--repo", str(git_repo)], cwd=git_repo)

    assert result.returncode == 0
    assert "No prompt index found" in result.stdout


def test_cxor_prompts_handles_missing_prompt_file(git_repo: Path):
    ctx = _ctx_with_prompts(git_repo)
    (ctx.paths.runs_dir / "P0001_attempt1" / "codex_task_prompt.md").unlink()

    result = _run_cli(["prompts", "--repo", str(git_repo), "--show", "PR000003"], cwd=git_repo)

    assert result.returncode == 1
    assert "prompt file not found" in result.stderr


def test_cxor_prompts_is_read_only(git_repo: Path):
    ctx = _ctx_with_prompts(git_repo)
    before = (ctx.paths.workflow_dir / "prompt_index.json").stat().st_mtime_ns

    result = _run_cli(["prompts", "--repo", str(git_repo), "--json"], cwd=git_repo)
    after = (ctx.paths.workflow_dir / "prompt_index.json").stat().st_mtime_ns

    assert result.returncode == 0
    assert after == before


def test_cxor_prompts_does_not_invoke_codex(git_repo: Path):
    _ctx_with_prompts(git_repo)

    result = _run_cli(["prompts", "--repo", str(git_repo), "--latest"], cwd=git_repo)

    assert result.returncode == 0
    assert "codex exec" not in result.stderr


def test_cxor_prompts_does_not_print_prompt_body_in_list_mode(git_repo: Path):
    _ctx_with_prompts(git_repo)

    result = _run_cli(["prompts", "--repo", str(git_repo)], cwd=git_repo)

    assert "Worker Prompt Pending" not in result.stdout
