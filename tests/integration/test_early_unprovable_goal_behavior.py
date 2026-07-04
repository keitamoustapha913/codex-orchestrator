from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from conftest import read_json


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "codex_orchestrator", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _write_prompt(git_repo: Path, text: str):
    (git_repo / "master_prompt.md").write_text(text + "\n", encoding="utf-8")
    subprocess.run(["git", "add", "master_prompt.md"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "unprovable prompt"], cwd=git_repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _auto(git_repo: Path):
    _write_prompt(git_repo, "Make this project feel more delightful in a way everyone agrees is perfect.")
    return _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--use-worktree", "--until", "DONE"], git_repo)


def test_unprovable_goal_safe_fails_before_product_patchlet(git_repo: Path):
    assert _auto(git_repo).returncode != 0
    assert read_json(git_repo / ".codex-orchestrator/provability/provability_result.json")["can_start_product_patchlets"] is False


def test_ambiguous_goal_safe_fails_before_product_patchlet(git_repo: Path):
    assert _auto(git_repo).returncode != 0
    assert read_json(git_repo / ".codex-orchestrator/provability/provability_result.json")["provability_status"] == "AMBIGUOUS"


def test_missing_capability_goal_safe_fails_before_product_patchlet(git_repo: Path):
    test_ambiguous_goal_safe_fails_before_product_patchlet(git_repo)


def test_provability_failure_writes_goal_not_provable_result(git_repo: Path):
    _auto(git_repo)
    assert (git_repo / ".codex-orchestrator/provability/goal_not_provable_result.json").exists()


def test_provability_failure_status_explains_reason(git_repo: Path):
    _auto(git_repo)
    assert read_json(git_repo / ".codex-orchestrator/provability/goal_not_provable_result.json")["reasons"]


def test_no_product_patchlet_started_for_unprovable_goal(git_repo: Path):
    _auto(git_repo)
    assert read_json(git_repo / ".codex-orchestrator/patchlets/patchlet_index.json")["patchlets"] == []


def test_no_worker_codex_invoked_for_unprovable_goal(git_repo: Path):
    _auto(git_repo)
    assert not list((git_repo / ".codex-orchestrator/runs").glob("*"))


def test_goal_progress_records_unprovable_status(git_repo: Path):
    _auto(git_repo)
    assert read_json(git_repo / ".codex-orchestrator/goal_progress.json")["overall_goal_status"] == "UNPROVABLE"


def test_operator_event_records_goal_not_provable(git_repo: Path):
    _auto(git_repo)
    events = (git_repo / ".codex-orchestrator/operator_events.jsonl").read_text(encoding="utf-8")
    assert "goal_ambiguous" in events or "goal_not_provable" in events


def test_late_goal_unprovable_signature_if_discovered_after_patchlets(git_repo: Path):
    _auto(git_repo)
    assert read_json(git_repo / ".codex-orchestrator/provability/goal_not_provable_result.json")["failure_signature"] in {"goal_ambiguous", "goal_not_provable"}
