from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from conftest import read_json


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "codex_orchestrator", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _auto(git_repo: Path, *, live=False, until="DONE"):
    args = ["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--use-worktree", "--until", until]
    if live:
        args.append("--live-progress")
    return _run_cli(args, git_repo)


def test_operator_events_include_master_prompt_frozen(git_repo: Path):
    _auto(git_repo, until="PATCHLETS_READY")
    assert "master_prompt_frozen" in (git_repo / ".codex-orchestrator/operator_events.jsonl").read_text(encoding="utf-8")


def test_operator_events_include_provability_and_goal_progress(git_repo: Path):
    _auto(git_repo, until="PATCHLETS_READY")
    text = (git_repo / ".codex-orchestrator/operator_events.jsonl").read_text(encoding="utf-8")
    assert "provability_classified" in text
    assert "goal_progress_updated" in text


def test_operator_events_include_independent_probe_rerun_failure(git_repo: Path):
    _auto(git_repo, until="PATCHLETS_READY")
    from codex_orchestrator.jsonio import write_json
    plan_path = git_repo / ".codex-orchestrator/probe_plan.json"
    plan = read_json(plan_path)
    plan["probes"][0]["rerunnable_by_orchestrator"] = False
    write_json(plan_path, plan)
    from codex_orchestrator.stages.run_patchlet import run_next_patchlet
    from codex_orchestrator.target_repo import resolve_target_repo
    run_next_patchlet(resolve_target_repo(repo=git_repo), worker_mode="mock", use_worktree=True)
    assert "independent_probe_rerun_failed" in (git_repo / ".codex-orchestrator/operator_events.jsonl").read_text(encoding="utf-8")


def test_operator_events_include_master_prompt_satisfaction_failure(git_repo: Path):
    _auto(git_repo, until="PATCHLETS_READY")
    _run_cli(["verify-global", "--repo", str(git_repo)], git_repo)
    assert "master_prompt_satisfaction_failed" in (git_repo / ".codex-orchestrator/operator_events.jsonl").read_text(encoding="utf-8")


def test_status_json_includes_master_prompt_proof_summary(git_repo: Path):
    _auto(git_repo, until="PATCHLETS_READY")
    assert "master_prompt_proof" in json.loads(_run_cli(["status", "--repo", str(git_repo), "--json"], git_repo).stdout)


def test_status_json_includes_applyable_progress(git_repo: Path):
    _auto(git_repo, until="PATCHLETS_READY")
    assert "applyable_progress" in json.loads(_run_cli(["status", "--repo", str(git_repo), "--json"], git_repo).stdout)


def test_monitor_shows_goal_coverage_failure(git_repo: Path):
    _auto(git_repo, until="PATCHLETS_READY")
    _run_cli(["verify-global", "--repo", str(git_repo)], git_repo)
    assert "master_prompt_satisfaction_failed" in _run_cli(["monitor", "--repo", str(git_repo)], git_repo).stdout


def test_live_progress_shows_master_prompt_satisfaction_failure(git_repo: Path):
    result = _auto(git_repo, live=True, until="PATCHLETS_READY")
    assert "provability classified" in result.stderr


def test_diagnosis_goal_not_provable(git_repo: Path):
    (git_repo / "master_prompt.md").write_text("Make it delightful.\n", encoding="utf-8")
    subprocess.run(["git", "add", "master_prompt.md"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "ambiguous"], cwd=git_repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _auto(git_repo, until="FAILURE_CLASSIFICATION_REQUIRED")
    assert read_json(git_repo / ".codex-orchestrator/provability/goal_not_provable_result.json")["failure_signature"] in {"goal_ambiguous", "goal_not_provable"}


def test_diagnosis_master_prompt_not_satisfied(git_repo: Path):
    _auto(git_repo, until="PATCHLETS_READY")
    _run_cli(["verify-global", "--repo", str(git_repo)], git_repo)
    assert read_json(git_repo / ".codex-orchestrator/global_verification/master_prompt_satisfaction_result.json")["failure_signature"] == "master_prompt_not_satisfied"


def test_diagnosis_independent_probe_rerun_failed(git_repo: Path):
    test_operator_events_include_independent_probe_rerun_failure(git_repo)


def test_diagnosis_goal_coverage_failed(git_repo: Path):
    test_operator_events_include_independent_probe_rerun_failure(git_repo)
