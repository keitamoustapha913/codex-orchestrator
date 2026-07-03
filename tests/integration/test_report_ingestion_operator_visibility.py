from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from conftest import read_json

from codex_orchestrator.operator_events import read_operator_events
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo


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


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "codex_orchestrator", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _scenario(ctx, refs):
    p = ctx.paths.workflow_dir / "mock" / "next_patchlet_result.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"report_override": {"probe_artifact_refs": refs}}), encoding="utf-8")


def test_live_progress_prints_report_ingestion_normalized(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])
    result = _run_cli(["auto", "--repo", str(git_repo), "--resume", "--until", "DONE", "--worker-mode", "mock", "--use-worktree", "--live-progress"], cwd=git_repo)
    assert "report ingestion P0001 normalized" in result.stderr


def test_live_progress_prints_report_ingestion_failed_signature(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, ["/etc/passwd"])
    result = _run_cli(["auto", "--repo", str(git_repo), "--resume", "--until", "FAILURE_CLASSIFICATION_REQUIRED", "--worker-mode", "mock", "--use-worktree", "--live-progress"], cwd=git_repo)
    assert "probe_artifact_refs_unsafe_path" in result.stderr


def test_monitor_shows_report_ingestion_events(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    result = _run_cli(["monitor", "--repo", str(git_repo), "--event-type", "report_ingestion_normalized"], cwd=git_repo)
    assert "report_ingestion_normalized" in result.stdout


def test_status_json_includes_last_report_ingestion_or_event_path(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    result = _run_cli(["status", "--repo", str(git_repo), "--json"], cwd=git_repo)
    data = json.loads(result.stdout)
    assert data["last_report_ingestion"]["result_path"].endswith("report_ingestion_result.json")


def test_prompt_listing_unchanged_by_report_ingestion(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    result = _run_cli(["prompts", "--repo", str(git_repo)], cwd=git_repo)
    assert "P0001_attempt1" in result.stdout


def test_compact_progress_does_not_print_full_report_body(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])
    result = _run_cli(["auto", "--repo", str(git_repo), "--resume", "--until", "DONE", "--worker-mode", "mock", "--use-worktree", "--live-progress"], cwd=git_repo)
    assert '"root_cause_classification"' not in result.stderr


def test_jsonl_progress_includes_report_ingestion_event_details(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])
    result = _run_cli(["auto", "--repo", str(git_repo), "--resume", "--until", "DONE", "--worker-mode", "mock", "--use-worktree", "--live-progress", "--progress-format", "jsonl"], cwd=git_repo)
    assert "report_ingestion_normalized" in result.stderr
    assert "normalization_applied" in result.stderr
