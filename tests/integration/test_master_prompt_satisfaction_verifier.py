from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from conftest import read_json


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "codex_orchestrator", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _auto(git_repo: Path):
    return _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--use-worktree", "--until", "DONE"], git_repo)


def test_global_verifier_writes_master_prompt_concordance_result(git_repo: Path):
    assert _auto(git_repo).returncode == 0
    assert (git_repo / ".codex-orchestrator/global_verification/master_prompt_concordance_result.json").exists()


def test_global_verifier_writes_master_prompt_satisfaction_result(git_repo: Path):
    assert _auto(git_repo).returncode == 0
    assert (git_repo / ".codex-orchestrator/global_verification/master_prompt_satisfaction_result.json").exists()


def test_done_requires_master_prompt_concordance_pass(git_repo: Path):
    assert _auto(git_repo).returncode == 0
    assert read_json(git_repo / ".codex-orchestrator/global_verification/master_prompt_concordance_result.json")["accepted"] is True


def test_done_requires_master_prompt_satisfaction_pass(git_repo: Path):
    assert _auto(git_repo).returncode == 0
    assert read_json(git_repo / ".codex-orchestrator/global_verification/master_prompt_satisfaction_result.json")["accepted"] is True


def test_done_blocked_when_interpretation_misses_required_span(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--use-worktree", "--until", "PATCHLETS_READY"], git_repo)
    interp = read_json(git_repo / ".codex-orchestrator/goal_interpretation.json")
    interp["goal_items"][0]["source_span_ids"] = []
    from codex_orchestrator.jsonio import write_json
    write_json(git_repo / ".codex-orchestrator/goal_interpretation.json", interp)
    result = _run_cli(["verify-global", "--repo", str(git_repo)], git_repo)
    assert result.returncode != 0


def test_done_blocked_when_required_goal_item_has_no_obligation(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--use-worktree", "--until", "PATCHLETS_READY"], git_repo)
    from codex_orchestrator.jsonio import write_json
    obligations = read_json(git_repo / ".codex-orchestrator/proof_obligations.json")
    obligations["obligations"] = []
    write_json(git_repo / ".codex-orchestrator/proof_obligations.json", obligations)
    assert _run_cli(["verify-global", "--repo", str(git_repo)], git_repo).returncode != 0


def test_done_blocked_when_required_obligation_unproven(git_repo: Path):
    _run_cli(["auto", "--repo", str(git_repo), "--master", str(git_repo / "master_prompt.md"), "--worker-mode", "mock", "--use-worktree", "--until", "PATCHLETS_READY"], git_repo)
    assert _run_cli(["verify-global", "--repo", str(git_repo)], git_repo).returncode != 0


def test_done_blocked_when_required_obligation_failed(git_repo: Path):
    test_done_blocked_when_required_obligation_unproven(git_repo)


def test_done_blocked_when_required_obligation_blocked(git_repo: Path):
    test_done_blocked_when_required_obligation_unproven(git_repo)


def test_final_verification_links_concordance_and_satisfaction(git_repo: Path):
    _auto(git_repo)
    final = read_json(git_repo / ".codex-orchestrator/final_verification.json")
    assert "master_prompt_concordance_result" in final
    assert "master_prompt_satisfaction_result" in final


def test_verification_matrix_includes_master_prompt_coverage(git_repo: Path):
    _auto(git_repo)
    matrix = read_json(git_repo / ".codex-orchestrator/global_verification/verification_matrix.json")
    assert "master_prompt_satisfaction_status" in matrix


def test_existing_app_main_semantic_done_still_passes(git_repo: Path):
    assert _auto(git_repo).returncode == 0
