from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from codex_orchestrator.errors import WorkerExecutionError, WorkerPreconditionError
from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo


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


def _read_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_fake_codex(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def test_worker_events_log_before_and_after_worker_execution(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")

    events = _read_events(ctx.paths.runs_dir / "P0001_attempt1" / "worker_hooks" / "events.jsonl")
    names = [event["event"] for event in events]
    assert "before_worker_start" in names
    assert "after_worker_exit" in names


def test_worker_events_log_worker_exception_without_suppressing_exception(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    ctx = _compiled_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
raise SystemExit(23)
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex")

    events = _read_events(ctx.paths.runs_dir / "P0001_attempt1" / "worker_hooks" / "events.jsonl")
    exception_events = [event for event in events if event["event"] == "after_worker_exception"]
    assert exception_events
    assert exception_events[-1]["exception_type"] == "WorkerExecutionError"


def test_worker_events_log_validation_steps_when_validation_runs(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")

    events = _read_events(ctx.paths.runs_dir / "P0001_attempt1" / "worker_hooks" / "events.jsonl")
    names = [event["event"] for event in events]
    assert "after_diff_capture" in names
    assert "after_report_validation" in names
    assert "after_probe_validation" in names


def test_worker_events_are_jsonl_objects(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")

    events = _read_events(ctx.paths.runs_dir / "P0001_attempt1" / "worker_hooks" / "events.jsonl")
    assert events
    assert all(event["kind"] == "worker_event" for event in events)
    assert all(event["schema_version"] == "1.0" for event in events)


def test_worker_events_are_under_target_run_dir(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    events_path = ctx.paths.runs_dir / "P0001_attempt1" / "worker_hooks" / "events.jsonl"
    assert events_path.exists()
    assert str(events_path).startswith(str(ctx.root))


def test_worker_events_reference_capsule_manifest(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")

    events = _read_events(ctx.paths.runs_dir / "P0001_attempt1" / "worker_hooks" / "events.jsonl")
    assert events
    assert all(event["worker_capsule_manifest"] == ".codex-orchestrator/runs/P0001_attempt1/worker_capsule.json" for event in events)


def test_patchlet_without_work_slice_id_fails_before_worker_launch(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    ctx = _compiled_ctx(git_repo)
    index = read_json(ctx.paths.patchlet_index)
    index["patchlets"][0].pop("work_slice_id")
    write_json(ctx.paths.patchlet_index, index)
    launched = False

    class NeverLaunchWorker:
        def run_patchlet(self, *_args, **_kwargs):
            nonlocal launched
            launched = True
            raise AssertionError("worker must not launch")

    monkeypatch.setattr(
        "codex_orchestrator.stages.run_patchlet.worker_for_mode",
        lambda _mode: NeverLaunchWorker(),
    )

    with pytest.raises(WorkerPreconditionError, match="work_slice_id"):
        run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    assert launched is False
