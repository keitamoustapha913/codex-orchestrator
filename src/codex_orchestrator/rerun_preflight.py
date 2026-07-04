from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_orchestrator.errors import CxorError
from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.state import load_state, now_iso
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.workflow_identity import build_workflow_identity, read_workflow_identity


TERMINAL_STAGES = {"DONE", "SAFE_FAILED", "FAILED"}


class RerunPreflightError(CxorError):
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        super().__init__(_format_preflight_error(result))


def rerun_preflight_path(repo_root: Path | str) -> Path:
    return Path(repo_root) / ".codex-orchestrator" / "rerun_preflight_result.json"


def run_rerun_preflight(
    ctx: TargetRepoContext,
    *,
    master: str | Path | None,
    worker_mode: str,
    use_worktree: bool,
    until: str,
    resume: bool = False,
    new_run: bool = False,
    force_new_run: bool = False,
    allow_dirty_target: bool = False,
) -> dict[str, Any]:
    state = load_state(ctx) if ctx.paths.state.exists() else None
    existing = read_workflow_identity(ctx.root)
    effective_master = master
    effective_worker_mode = worker_mode
    effective_use_worktree = use_worktree
    if resume and existing:
        if effective_master is None:
            effective_master = existing.get("master_prompt_path")
        if worker_mode == "ci_only":
            effective_worker_mode = existing.get("worker_mode") or worker_mode
        effective_use_worktree = bool(existing.get("use_worktree", use_worktree))
    requested = build_workflow_identity(
        ctx,
        master=effective_master,
        worker_mode=effective_worker_mode,
        use_worktree=effective_use_worktree,
        until=until,
        allow_dirty_target=allow_dirty_target,
    )
    requested_master_path = Path(requested["master_prompt_path"])
    current_dirty = _product_dirty_status(requested["target_dirty_status_at_start"], ctx.root, requested_master_path)
    result = {
        "schema_version": "1.0",
        "kind": "rerun_preflight_result",
        "created_at": now_iso(),
        "requested_goal_fingerprint": requested["goal_fingerprint"],
        "existing_goal_fingerprint": existing.get("goal_fingerprint") if existing else None,
        "existing_workflow_id": existing.get("workflow_id") if existing else getattr(state, "workflow_id", None),
        "existing_run_id": existing.get("run_id") if existing else None,
        "existing_stage": state.stage if state else None,
        "decision": None,
        "reasons": [],
        "changed_fields": [],
        "recommended_commands": [],
        "requested_identity": requested,
        "current_target_dirty_status": requested["target_dirty_status_at_start"],
    }

    if current_dirty and not allow_dirty_target and not new_run and not force_new_run:
        result.update(
            decision="REFUSE_DIRTY_TARGET",
            reasons=["target product/runtime working tree is dirty"],
            changed_fields=["target_dirty_status_at_start"],
            recommended_commands=["commit or revert product/runtime changes", "cxor auto ... --allow-dirty-target"],
        )
    elif state is None:
        result.update(decision="START_NEW_WORKFLOW", reasons=["no existing workflow"])
    elif existing is None and resume:
        result.update(
            decision="RETURN_EXISTING_DONE" if state.stage in TERMINAL_STAGES else "RESUME_ACTIVE_WORKFLOW",
            reasons=["existing workflow has no workflow_identity.json", "explicit --resume requested"],
            recommended_commands=["finish this workflow, then start future goals with workflow identity"],
        )
    elif existing is None:
        result.update(
            decision="REFUSE_AMBIGUOUS_TERMINAL_WORKFLOW",
            reasons=["existing workflow has no workflow_identity.json"],
            recommended_commands=["cxor auto ... --new-run", "cxor archive --repo <repo>", "cxor reset --repo <repo> --archive"],
        )
    else:
        changed = _changed_fields(existing, requested)
        same = not changed
        terminal = state.stage in TERMINAL_STAGES
        result["changed_fields"] = changed
        if terminal and same and not new_run and not force_new_run:
            result.update(decision="RETURN_EXISTING_DONE", reasons=["existing workflow is terminal DONE for the same goal fingerprint"])
        elif terminal and changed and not new_run and not force_new_run:
            result.update(
                decision="REFUSE_REQUIRES_NEW_RUN",
                reasons=["existing workflow is terminal DONE", "requested goal differs from workflow identity"],
                recommended_commands=["cxor auto ... --new-run", "cxor archive --repo <repo>", "cxor reset --repo <repo> --archive"],
            )
        elif terminal and (new_run or force_new_run):
            result.update(decision="START_NEW_WORKFLOW", reasons=["new run requested for terminal workflow"])
        elif not terminal and changed:
            result.update(
                decision="REFUSE_REQUIRES_NEW_RUN",
                reasons=["existing workflow is active", "requested goal differs from workflow identity"],
                recommended_commands=["cxor auto ... --resume", "finish or archive the active workflow before starting a new one"],
            )
        elif not terminal and (resume or same):
            result.update(decision="RESUME_ACTIVE_WORKFLOW", reasons=["existing active workflow matches requested fingerprint"])
        else:
            result.update(decision="REFUSE_REQUIRES_RESUME", reasons=["existing active workflow requires explicit resume"])

    write_json(rerun_preflight_path(ctx.root), result)
    return result


def _changed_fields(existing: dict[str, Any], requested: dict[str, Any]) -> list[str]:
    fields = [
        "master_prompt_path",
        "master_prompt_sha256",
        "target_head_sha",
        "target_tree_sha",
        "target_dirty_status_at_start",
        "worker_mode",
        "use_worktree",
        "until",
    ]
    return [field for field in fields if existing.get(field) != requested.get(field)]


def _product_dirty_status(status: list[str], repo_root: Path, requested_master_path: Path) -> list[str]:
    ignored = (".codex-orchestrator/", ".artifacts/")
    dirty = []
    requested_master_rel = _repo_relative_path(repo_root, requested_master_path)
    for line in status:
        path = line[3:] if len(line) > 3 else line
        if path.startswith(ignored):
            continue
        if requested_master_rel is not None and path == requested_master_rel:
            continue
        dirty.append(line)
    return dirty


def _repo_relative_path(repo_root: Path, path: Path) -> str | None:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return None


def _format_preflight_error(result: dict[str, Any]) -> str:
    decision = result.get("decision")
    if decision == "REFUSE_REQUIRES_NEW_RUN":
        existing = result.get("requested_identity", {})
        return (
            "Existing cxor workflow is DONE or active for a different goal. "
            f"Changed fields: {', '.join(result.get('changed_fields', []))}. "
            f"Requested prompt: {existing.get('master_prompt_path')}. "
            "Run with --new-run or archive/reset the existing workflow."
        )
    if decision == "REFUSE_DIRTY_TARGET":
        return "Target product/runtime working tree is dirty; commit/revert it or pass --allow-dirty-target."
    if decision == "REFUSE_AMBIGUOUS_TERMINAL_WORKFLOW":
        return "Existing cxor workflow is missing workflow_identity.json; use --new-run or archive/reset before rerunning."
    return f"cxor rerun preflight refused: {decision}"
