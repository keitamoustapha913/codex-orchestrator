from __future__ import annotations

import subprocess
from pathlib import Path

from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json
from codex_orchestrator.workflow_identity import build_workflow_identity, compute_goal_fingerprint, write_workflow_identity


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE)
    (repo / "app.py").write_text("def main():\n    return 'x'\n", encoding="utf-8")
    (repo / "master_prompt.md").write_text("Make app return ok.\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py", "master_prompt.md"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-m", "init"], cwd=repo, check=True, stdout=subprocess.PIPE)
    return repo


def test_workflow_identity_created_for_new_workflow(tmp_path: Path):
    repo = _repo(tmp_path)
    ctx = resolve_target_repo(repo=repo)
    identity = write_workflow_identity(ctx, build_workflow_identity(ctx, master=repo / "master_prompt.md", worker_mode="mock", use_worktree=True, until="DONE"))
    assert (repo / ".codex-orchestrator" / "workflow_identity.json").exists()
    assert identity["kind"] == "workflow_identity"


def test_workflow_identity_contains_master_prompt_path_and_sha(tmp_path: Path):
    repo = _repo(tmp_path)
    identity = build_workflow_identity(resolve_target_repo(repo=repo), master=repo / "master_prompt.md", worker_mode="mock", use_worktree=False, until="DONE")
    assert identity["master_prompt_path"] == str((repo / "master_prompt.md").resolve())
    assert len(identity["master_prompt_sha256"]) == 64


def test_workflow_identity_contains_target_head_and_tree(tmp_path: Path):
    repo = _repo(tmp_path)
    identity = build_workflow_identity(resolve_target_repo(repo=repo), master=repo / "master_prompt.md", worker_mode="mock", use_worktree=False, until="DONE")
    assert identity["target_head_sha"]
    assert identity["target_tree_sha"]


def test_workflow_identity_contains_dirty_status_at_start(tmp_path: Path):
    repo = _repo(tmp_path)
    (repo / "app.py").write_text("dirty\n", encoding="utf-8")
    identity = build_workflow_identity(resolve_target_repo(repo=repo), master=repo / "master_prompt.md", worker_mode="mock", use_worktree=False, until="DONE")
    assert "M app.py" in identity["target_dirty_status_at_start"]


def test_goal_fingerprint_is_deterministic(tmp_path: Path):
    repo = _repo(tmp_path)
    ctx = resolve_target_repo(repo=repo)
    a = build_workflow_identity(ctx, master=repo / "master_prompt.md", worker_mode="mock", use_worktree=False, until="DONE")
    b = build_workflow_identity(ctx, master=repo / "master_prompt.md", worker_mode="mock", use_worktree=False, until="DONE")
    assert compute_goal_fingerprint(a) == compute_goal_fingerprint(b)


def test_goal_fingerprint_changes_when_master_prompt_content_changes(tmp_path: Path):
    repo = _repo(tmp_path)
    ctx = resolve_target_repo(repo=repo)
    a = build_workflow_identity(ctx, master=repo / "master_prompt.md", worker_mode="mock", use_worktree=False, until="DONE")
    (repo / "master_prompt.md").write_text("Make app return me.\n", encoding="utf-8")
    b = build_workflow_identity(ctx, master=repo / "master_prompt.md", worker_mode="mock", use_worktree=False, until="DONE")
    assert a["goal_fingerprint"] != b["goal_fingerprint"]


def test_goal_fingerprint_changes_when_master_prompt_path_changes(tmp_path: Path):
    repo = _repo(tmp_path)
    (repo / "other.md").write_text("Make app return ok.\n", encoding="utf-8")
    ctx = resolve_target_repo(repo=repo)
    a = build_workflow_identity(ctx, master=repo / "master_prompt.md", worker_mode="mock", use_worktree=False, until="DONE")
    b = build_workflow_identity(ctx, master=repo / "other.md", worker_mode="mock", use_worktree=False, until="DONE")
    assert a["goal_fingerprint"] != b["goal_fingerprint"]


def test_goal_fingerprint_changes_when_target_head_changes(tmp_path: Path):
    repo = _repo(tmp_path)
    ctx = resolve_target_repo(repo=repo)
    a = build_workflow_identity(ctx, master=repo / "master_prompt.md", worker_mode="mock", use_worktree=False, until="DONE")
    (repo / "new.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "new.txt"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-m", "new"], cwd=repo, check=True, stdout=subprocess.PIPE)
    b = build_workflow_identity(ctx, master=repo / "master_prompt.md", worker_mode="mock", use_worktree=False, until="DONE")
    assert a["goal_fingerprint"] != b["goal_fingerprint"]


def test_goal_fingerprint_changes_when_target_dirty_status_changes(tmp_path: Path):
    repo = _repo(tmp_path)
    ctx = resolve_target_repo(repo=repo)
    a = build_workflow_identity(ctx, master=repo / "master_prompt.md", worker_mode="mock", use_worktree=False, until="DONE")
    (repo / "app.py").write_text("dirty\n", encoding="utf-8")
    b = build_workflow_identity(ctx, master=repo / "master_prompt.md", worker_mode="mock", use_worktree=False, until="DONE")
    assert a["goal_fingerprint"] != b["goal_fingerprint"]


def test_goal_fingerprint_ignores_timestamps(tmp_path: Path):
    repo = _repo(tmp_path)
    identity = build_workflow_identity(resolve_target_repo(repo=repo), master=repo / "master_prompt.md", worker_mode="mock", use_worktree=False, until="DONE")
    changed = dict(identity)
    changed["created_at"] = "2099-01-01T00:00:00Z"
    assert compute_goal_fingerprint(identity) == compute_goal_fingerprint(changed)


def test_workflow_identity_schema_validates(tmp_path: Path):
    repo = _repo(tmp_path)
    identity = build_workflow_identity(resolve_target_repo(repo=repo), master=repo / "master_prompt.md", worker_mode="mock", use_worktree=False, until="DONE")
    validate_json(identity, "workflow_identity.schema.json")
