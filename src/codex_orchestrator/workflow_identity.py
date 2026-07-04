from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.state import now_iso
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.version import __version__


SCHEMA_VERSION = "1.0"


def workflow_identity_path(repo_root: Path | str) -> Path:
    return Path(repo_root) / ".codex-orchestrator" / "workflow_identity.json"


def read_workflow_identity(repo_root: Path | str) -> dict[str, Any] | None:
    path = workflow_identity_path(repo_root)
    return read_json(path) if path.exists() else None


def build_workflow_identity(
    ctx: TargetRepoContext,
    *,
    master: str | Path | None,
    worker_mode: str,
    use_worktree: bool,
    until: str,
    workflow_id: str | None = None,
    run_id: str = "R0001",
    allow_dirty_target: bool = False,
) -> dict[str, Any]:
    master_path = Path(master).expanduser().resolve() if master is not None else ctx.paths.master_prompt.resolve()
    prompt_bytes = master_path.read_bytes() if master_path.exists() else b""
    dirty_status = _identity_dirty_status(_git_lines(ctx.root, "status", "--porcelain=v1"))
    target_head_sha = _git_text(ctx.root, "rev-parse", "HEAD")
    target_tree_sha = _git_text(ctx.root, "rev-parse", "HEAD^{tree}")
    first_line = prompt_bytes.decode("utf-8", errors="replace").splitlines()[0] if prompt_bytes else ""
    identity = {
        "schema_version": SCHEMA_VERSION,
        "kind": "workflow_identity",
        "workflow_id": workflow_id or "WF000001",
        "run_id": run_id,
        "created_at": now_iso(),
        "repo_root": str(ctx.root),
        "target_head_sha": target_head_sha,
        "target_tree_sha": target_tree_sha,
        "target_dirty_status_at_start": dirty_status,
        "master_prompt_path": str(master_path),
        "master_prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
        "master_prompt_size_bytes": len(prompt_bytes),
        "master_prompt_first_line": first_line,
        "worker_mode": worker_mode,
        "use_worktree": bool(use_worktree),
        "until": until,
        "orchestrator_version": __version__,
        "command_args": {
            "worker_mode": worker_mode,
            "use_worktree": bool(use_worktree),
            "until": until,
            "allow_dirty_target": bool(allow_dirty_target),
        },
    }
    identity["goal_fingerprint"] = compute_goal_fingerprint(identity)
    return identity


def write_workflow_identity(ctx: TargetRepoContext, identity: dict[str, Any]) -> dict[str, Any]:
    write_json(workflow_identity_path(ctx.root), identity)
    return identity


def compute_goal_fingerprint(identity: dict[str, Any]) -> str:
    payload = {
        "schema_version": identity.get("schema_version", SCHEMA_VERSION),
        "repo_root": identity.get("repo_root"),
        "target_head_sha": identity.get("target_head_sha"),
        "target_tree_sha": identity.get("target_tree_sha"),
        "target_dirty_status_at_start": identity.get("target_dirty_status_at_start", []),
        "master_prompt_path": identity.get("master_prompt_path"),
        "master_prompt_sha256": identity.get("master_prompt_sha256"),
        "worker_mode": identity.get("worker_mode"),
        "use_worktree": bool(identity.get("use_worktree")),
        "until": identity.get("until"),
    }
    import json

    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _git_text(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def _git_lines(repo: Path, *args: str) -> list[str]:
    text = _git_text(repo, *args)
    return [line for line in text.splitlines() if line]


def _identity_dirty_status(status: list[str]) -> list[str]:
    ignored = (".codex-orchestrator/", ".artifacts/")
    dirty = []
    for line in status:
        path = line[3:] if len(line) > 3 else line
        if path.startswith(ignored):
            continue
        dirty.append(line)
    return dirty
