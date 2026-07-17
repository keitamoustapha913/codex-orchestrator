from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import read_json

from codex_orchestrator.errors import WorkerExecutionError
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file


def _compiled_ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _write_fake_codex(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def test_worker_capsule_writes_task_contract(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")

    task_contract = ctx.paths.runs_dir / "P0001_attempt1" / "worker_memory" / "TASK_CONTRACT.md"
    assert task_contract.exists()


def test_task_contract_contains_handoff_probe_and_allowed_file_paths(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")

    text = (ctx.paths.runs_dir / "P0001_attempt1" / "worker_memory" / "TASK_CONTRACT.md").read_text(encoding="utf-8")
    assert "P0001.task_completion_handoff.json" in text
    assert ".artifacts/probes/P0001" in text
    assert "app.py" in text


def test_task_contract_says_orchestrator_owns_gate_results(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")

    text = (ctx.paths.runs_dir / "P0001_attempt1" / "worker_memory" / "TASK_CONTRACT.md").read_text(encoding="utf-8")
    assert "orchestrator owns gate results" in text.lower()


def test_worker_capsule_writes_machine_validated_live_memory_json(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")

    live_memory = ctx.paths.runs_dir / "P0001_attempt1" / "worker_memory" / "LIVE_MEMORY.json"
    assert validate_json_file(live_memory, "worker_memory.schema.json") == []


def test_worker_capsule_writes_human_live_memory_markdown(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")

    assert (ctx.paths.runs_dir / "P0001_attempt1" / "worker_memory" / "LIVE_MEMORY.md").exists()


def test_worker_capsule_writes_allowed_paths_json(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")

    allowed_paths = ctx.paths.runs_dir / "P0001_attempt1" / "worker_memory" / "ALLOWED_PATHS.json"
    assert validate_json_file(allowed_paths, "allowed_paths.schema.json") == []


def test_worker_capsule_does_not_include_broad_unscoped_repo_memory(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")

    text = (ctx.paths.runs_dir / "P0001_attempt1" / "worker_memory" / "TASK_CONTRACT.md").read_text(encoding="utf-8")
    assert ".codex-orchestrator/census/repo_files.txt" not in text
    assert ".codex-orchestrator/census/rg_index.jsonl" not in text


def test_real_codex_smoke_prompt_points_to_task_contract(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    ctx = _compiled_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import sys
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex")

    command = read_json(ctx.paths.runs_dir / "P0001_attempt1" / "command.json")
    prompt_path = Path(command["prompt_path"])
    prompt_text = prompt_path.read_text(encoding="utf-8")
    assert "worker_memory/TASK_CONTRACT.md" in prompt_text
