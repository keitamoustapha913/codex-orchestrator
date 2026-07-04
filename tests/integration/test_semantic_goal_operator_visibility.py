from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from conftest import read_json, run


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "codex_orchestrator", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _setup(git_repo: Path, *, app_value: str, prompt_value: str = "me"):
    (git_repo / "app.py").write_text(f"def main():\n    return {app_value!r}\n", encoding="utf-8")
    prompt = git_repo / "master_prompt_semantic.md"
    prompt.write_text(f"Make app return {prompt_value} and prove it.\n", encoding="utf-8")
    run(["git", "add", "app.py", "master_prompt_semantic.md"], git_repo)
    run(["git", "commit", "-m", "semantic setup"], git_repo)
    return prompt


def _disable_semantic_autofix(git_repo: Path):
    path = git_repo / ".codex-orchestrator" / "mock" / "next_patchlet_result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"disable_semantic_autofix": true}', encoding="utf-8")


def test_operator_event_written_when_semantic_goal_spec_created(git_repo: Path):
    prompt = _setup(git_repo, app_value="me")
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(prompt), "--worker-mode", "mock", "--until", "PATCHLETS_READY"], cwd=git_repo)
    events = (git_repo / ".codex-orchestrator/operator_events.jsonl").read_text(encoding="utf-8")
    assert "semantic_goal_spec_created" in events


def test_operator_event_written_when_semantic_goal_check_passes(git_repo: Path):
    prompt = _setup(git_repo, app_value="me")
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(prompt), "--worker-mode", "mock"], cwd=git_repo)
    assert "semantic_goal_check_passed" in (git_repo / ".codex-orchestrator/operator_events.jsonl").read_text(encoding="utf-8")


def test_operator_event_written_when_semantic_goal_check_fails(git_repo: Path):
    prompt = _setup(git_repo, app_value="ok")
    _disable_semantic_autofix(git_repo)
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(prompt), "--worker-mode", "mock"], cwd=git_repo)
    assert "semantic_goal_check_failed" in (git_repo / ".codex-orchestrator/operator_events.jsonl").read_text(encoding="utf-8")


def test_live_progress_prints_semantic_goal_failure(git_repo: Path):
    prompt = _setup(git_repo, app_value="ok")
    _disable_semantic_autofix(git_repo)
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(prompt), "--worker-mode", "mock", "--live-progress"], cwd=git_repo)
    assert "semantic goal SGC001 failed" in result.stderr


def test_live_progress_prints_goal_satisfaction_gate_failure(git_repo: Path):
    prompt = _setup(git_repo, app_value="ok")
    _disable_semantic_autofix(git_repo)
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(prompt), "--worker-mode", "mock", "--live-progress"], cwd=git_repo)
    assert "goal satisfaction gate failed for P0001" in result.stderr


def test_monitor_shows_semantic_goal_events(git_repo: Path):
    prompt = _setup(git_repo, app_value="ok")
    _disable_semantic_autofix(git_repo)
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(prompt), "--worker-mode", "mock"], cwd=git_repo)
    result = _run_cli(["monitor", "--repo", str(git_repo), "--event-type", "semantic_goal_check_failed"], cwd=git_repo)
    assert "semantic_goal_check_failed" in result.stdout


def test_status_json_includes_semantic_goal_pass(git_repo: Path):
    prompt = _setup(git_repo, app_value="me")
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(prompt), "--worker-mode", "mock"], cwd=git_repo)
    result = _run_cli(["status", "--repo", str(git_repo), "--json"], cwd=git_repo)
    assert '"status": "PASSED"' in result.stdout


def test_status_json_includes_semantic_goal_failure(git_repo: Path):
    prompt = _setup(git_repo, app_value="ok")
    _disable_semantic_autofix(git_repo)
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(prompt), "--worker-mode", "mock"], cwd=git_repo)
    result = _run_cli(["status", "--repo", str(git_repo), "--json"], cwd=git_repo)
    assert '"actual_value": "ok"' in result.stdout
    assert '"status": "FAILED"' in result.stdout


def test_diagnosis_category_semantic_goal_unsatisfied(git_repo: Path):
    prompt = _setup(git_repo, app_value="ok")
    _disable_semantic_autofix(git_repo)
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(prompt), "--worker-mode", "mock"], cwd=git_repo)
    failure = read_json(git_repo / ".codex-orchestrator/failures/F0001.json")
    assert failure["diagnosis"]["primary_category"] == "semantic_goal_unsatisfied"


def test_semantic_goal_unsatisfied_outranks_network_or_unknown(git_repo: Path):
    prompt = _setup(git_repo, app_value="ok")
    _disable_semantic_autofix(git_repo)
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(prompt), "--worker-mode", "mock"], cwd=git_repo)
    failure = read_json(git_repo / ".codex-orchestrator/failures/F0001.json")
    assert failure["diagnosis"]["primary_category"] not in {"network_or_api_error", "unknown"}
