from __future__ import annotations

import hashlib
import socket
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import version
from .errors import StateError
from .git_guard import repo_head
from .jsonio import read_json, write_json
from .state_machine import assert_stage
from .target_repo import TargetRepoContext


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass
class WorkflowState:
    schema_version: str
    kind: str
    workflow_id: str
    stage: str
    mode: str
    until: str
    orchestrator: dict
    target_repo: dict
    master_prompt_sha256: str | None = None
    current_loop_iteration: int = 0
    current_patchlet_id: str | None = None
    attempts: dict[str, int] = field(default_factory=dict)
    pending_patchlets: list[str] = field(default_factory=list)
    completed_patchlets: list[str] = field(default_factory=list)
    verified_no_change_needed: list[str] = field(default_factory=list)
    blocked_patchlets: list[str] = field(default_factory=list)
    failed_patchlets: list[str] = field(default_factory=list)
    transaction_groups: list[dict] = field(default_factory=list)
    failure_cycles: list[dict] = field(default_factory=list)
    repair_cycles: list[dict] = field(default_factory=list)
    stage_history: list[dict] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_json(self) -> dict:
        data = asdict(self)
        assert_stage(data["stage"])
        return data

    @classmethod
    def from_json(cls, data: dict) -> "WorkflowState":
        assert_stage(data["stage"])
        return cls(**data)


def new_state(ctx: TargetRepoContext, *, stage: str = "INITIALIZED", mode: str = "manual", until: str = "DONE") -> WorkflowState:
    assert_stage(stage)
    current_sha = repo_head(ctx.root)
    return WorkflowState(
        schema_version="1.0",
        kind="workflow_state",
        workflow_id=time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex[:8],
        stage=stage,
        mode=mode,
        until=until,
        orchestrator={
            "package_name": "codex-orchestrator",
            "version": version.__version__,
            "entrypoint": "cxor",
            "install_mode": "source-tree-or-editable",
            "hostname": socket.gethostname(),
        },
        target_repo={
            "root": str(ctx.root),
            "git_root": str(ctx.git_root) if ctx.git_root else None,
            "repo_sha_start": current_sha,
            "current_sha": current_sha,
            "allow_non_git": ctx.allow_non_git,
            "allow_self_target": ctx.allow_self_target,
        },
    )


def load_state(ctx: TargetRepoContext) -> WorkflowState:
    if not ctx.paths.state.exists():
        raise StateError(f"Workflow state does not exist: {ctx.paths.state}")
    return WorkflowState.from_json(read_json(ctx.paths.state))


def save_state(ctx: TargetRepoContext, state: WorkflowState) -> None:
    state.updated_at = now_iso()
    state.target_repo["current_sha"] = repo_head(ctx.root)
    write_json(ctx.paths.state, state.to_json())


def transition(ctx: TargetRepoContext, state: WorkflowState, new_stage: str, *, reason: str | None = None) -> WorkflowState:
    assert_stage(new_stage)
    if state.stage != new_stage:
        state.stage_history.append({
            "from": state.stage,
            "to": new_stage,
            "at": now_iso(),
            "reason": reason or "stage transition",
        })
        state.stage = new_stage
    save_state(ctx, state)
    return state
