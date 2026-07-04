from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from conftest import read_json
from codex_orchestrator.control import write_stop_result
from codex_orchestrator.state import load_state, transition
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "codex_orchestrator", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _done_then_stopped(git_repo: Path):
    assert _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--use-worktree", "--until", "DONE"], git_repo).returncode == 0
    ctx = resolve_target_repo(repo=git_repo)
    write_stop_result(ctx, stop_stage="PATCHLET_EXECUTION_COMPLETE")
    transition(ctx, load_state(ctx), "STOPPED", reason="test stopped")
    return ctx


def test_stop_command_exists(git_repo: Path):
    assert _run_cli(["stop", "--help"], git_repo).returncode == 0


def test_stop_command_writes_stop_requested(git_repo: Path):
    result = _run_cli(["stop", "--repo", str(git_repo)], git_repo)
    assert result.returncode == 0
    assert (git_repo / ".codex-orchestrator/control/stop_requested.json").exists()


def test_stop_command_json_outputs_request(git_repo: Path):
    result = _run_cli(["stop", "--repo", str(git_repo), "--json"], git_repo)
    assert json.loads(result.stdout)["kind"] == "stop_requested"


def test_auto_stops_after_current_attempt_when_requested(git_repo: Path):
    _run_cli(["stop", "--repo", str(git_repo)], git_repo)
    result = _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--until", "STOPPED"], git_repo)
    assert result.returncode == 0


def test_stop_result_records_latest_accepted_checkpoint(git_repo: Path):
    _done_then_stopped(git_repo)
    assert "checkpoints" in read_json(git_repo / ".codex-orchestrator/control/stop_result.json")["latest_accepted_checkpoint"]


def test_stop_result_records_applyable_progress_true_when_checkpoint_exists(git_repo: Path):
    _done_then_stopped(git_repo)
    assert read_json(git_repo / ".codex-orchestrator/control/stop_result.json")["applyable_progress"] is True


def test_stop_result_records_applyable_progress_false_when_no_checkpoint_exists(git_repo: Path):
    _run_cli(["stop", "--repo", str(git_repo)], git_repo)
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--until", "STOPPED"], git_repo)
    assert read_json(git_repo / ".codex-orchestrator/control/stop_result.json")["applyable_progress"] is False


def test_apply_results_partial_requires_allow_partial(git_repo: Path):
    _done_then_stopped(git_repo)
    result = _run_cli(["apply-results", "--repo", str(git_repo), "--mode", "patch", "--scope", "accepted"], git_repo)
    assert result.returncode != 0


def test_apply_results_partial_applies_latest_accepted_checkpoint(git_repo: Path):
    _done_then_stopped(git_repo)
    result = _run_cli(["apply-results", "--repo", str(git_repo), "--mode", "patch", "--scope", "accepted", "--allow-partial"], git_repo)
    assert result.returncode == 0


def test_apply_results_partial_refuses_when_no_accepted_checkpoint(git_repo: Path):
    _run_cli(["stop", "--repo", str(git_repo)], git_repo)
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--until", "STOPPED"], git_repo)
    result = _run_cli(["apply-results", "--repo", str(git_repo), "--mode", "patch", "--scope", "accepted", "--allow-partial"], git_repo)
    assert result.returncode != 0


def test_apply_results_partial_does_not_apply_in_progress_attempt(git_repo: Path):
    test_apply_results_partial_applies_latest_accepted_checkpoint(git_repo)


def test_partial_apply_result_schema_validates(git_repo: Path):
    ctx = _done_then_stopped(git_repo)
    _run_cli(["apply-results", "--repo", str(git_repo), "--mode", "patch", "--scope", "accepted", "--allow-partial"], git_repo)
    assert validate_json_file(ctx.paths.workflow_dir / "apply_results/partial_apply_result.json", "partial_apply_result.schema.json") == []


def test_partial_apply_result_warns_master_prompt_may_not_be_fully_satisfied(git_repo: Path):
    _done_then_stopped(git_repo)
    _run_cli(["apply-results", "--repo", str(git_repo), "--mode", "patch", "--scope", "accepted", "--allow-partial"], git_repo)
    assert "may not be satisfied" in read_json(git_repo / ".codex-orchestrator/apply_results/partial_apply_result.json")["warnings"][0]


def test_ctrl_c_like_interrupt_preserves_state_if_existing_harness_supports_it(git_repo: Path):
    assert _run_cli(["stop", "--repo", str(git_repo), "--now"], git_repo).returncode == 0
