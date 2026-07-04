from __future__ import annotations

import subprocess
from pathlib import Path

from codex_orchestrator.errors import StagePreconditionError
from codex_orchestrator.integration_state import target_product_runtime_clean, write_final_diff
from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.state import load_state, now_iso
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.validators.integration_artifact_validator import validate_integration_artifacts


def apply_results(ctx: TargetRepoContext, *, mode: str = "patch", scope: str = "final", allow_partial: bool = False) -> dict:
    if mode not in {"patch", "branch", "working-tree"}:
        raise ValueError(f"unsupported apply-results mode: {mode}")
    if scope not in {"final", "accepted"}:
        raise ValueError(f"unsupported apply-results scope: {scope}")
    if not ctx.paths.integration_state.exists():
        raise StagePreconditionError(
            "apply-results",
            current_stage=_current_stage(ctx),
            target_repo=str(ctx.root),
            detail=f"missing integration_state.json: {ctx.paths.integration_state}",
        )

    workflow_stage = _current_stage(ctx)
    latest_checkpoint = _latest_checkpoint(ctx)
    if workflow_stage == "STOPPED":
        if not allow_partial:
            raise StagePreconditionError(
                "apply-results",
                current_stage=workflow_stage,
                target_repo=str(ctx.root),
                detail="stopped non-DONE workflows require --allow-partial",
            )
        if not latest_checkpoint:
            raise StagePreconditionError(
                "apply-results",
                current_stage=workflow_stage,
                target_repo=str(ctx.root),
                detail="no accepted checkpoint is safely applyable",
            )
        scope = "accepted"
    elif scope == "accepted" and allow_partial and not latest_checkpoint:
        raise StagePreconditionError(
            "apply-results",
            current_stage=workflow_stage,
            target_repo=str(ctx.root),
            detail="no accepted checkpoint is safely applyable",
        )

    state = read_json(ctx.paths.integration_state)
    final_diff = write_final_diff(ctx)
    created_branch = None
    mutated_working_tree = False

    if mode == "branch":
        run_id = _run_id_from_ref(str(state["integration_ref"]))
        created_branch = f"cxor/results/{run_id}"
        _run_git(ctx.root, "branch", "-f", created_branch, str(state["integration_sha"]))
    elif mode == "working-tree":
        if not target_product_runtime_clean(ctx):
            raise StagePreconditionError(
                "apply-results",
                current_stage=_current_stage(ctx),
                target_repo=str(ctx.root),
                detail="working-tree mode requires a clean target working tree",
            )
        if ctx.paths.final_diff_path.read_text(encoding="utf-8"):
            _run_git(ctx.root, "apply", str(ctx.paths.final_diff_path))
            mutated_working_tree = True

    result = {
        "schema_version": "1.0",
        "kind": "apply_results_result",
        "mode": mode,
        "scope": scope,
        "allow_partial": allow_partial,
        "workflow_stage": workflow_stage,
        "target_head_sha": final_diff["target_head_sha"],
        "integration_sha": final_diff["integration_sha"],
        "integration_ref": final_diff["integration_ref"],
        "final_diff_path": final_diff["final_diff_path"],
        "mutated_working_tree": mutated_working_tree,
        "created_branch": created_branch,
        "created_at": now_iso(),
        "rerun_guidance": {
            "working_tree_mutated": mutated_working_tree,
            "recommended_next_steps": [
                "review git diff",
                "commit applied results before starting a new workflow",
                "run cxor auto --new-run for a new goal after committing or use --allow-dirty-target",
            ],
        },
    }
    result_dir = ctx.paths.integration_dir / "apply_results"
    result_dir.mkdir(parents=True, exist_ok=True)
    write_json(result_dir / f"{mode}_result.json", result)
    latest_dir = ctx.paths.workflow_dir / "apply_results"
    latest_dir.mkdir(parents=True, exist_ok=True)
    write_json(latest_dir / "latest_apply_result.json", result)
    if allow_partial and workflow_stage == "STOPPED":
        partial = {
            "schema_version": "1.0",
            "kind": "partial_apply_result",
            "mode": mode,
            "scope": scope,
            "allow_partial": True,
            "workflow_stage": workflow_stage,
            "latest_accepted_integration_ref": final_diff["integration_ref"],
            "latest_accepted_checkpoint": latest_checkpoint,
            "goal_progress_summary": _goal_progress_summary(ctx),
            "mutated_working_tree": mutated_working_tree,
            "warnings": [
                "Applied latest accepted progress from a stopped workflow. The full master prompt may not be satisfied."
            ],
        }
        partial_dir = ctx.paths.workflow_dir / "apply_results"
        partial_dir.mkdir(parents=True, exist_ok=True)
        write_json(partial_dir / "partial_apply_result.json", partial)
    validation = validate_integration_artifacts(ctx.root)
    write_json(result_dir / f"{mode}_validation_result.json", validation)
    if not validation["valid"]:
        raise RuntimeError("apply-results integration artifact validation failed")
    return result


def _current_stage(ctx: TargetRepoContext) -> str:
    try:
        return load_state(ctx).stage
    except Exception:
        return "UNKNOWN"


def _run_id_from_ref(ref: str) -> str:
    parts = ref.split("/")
    if "runs" in parts:
        index = parts.index("runs")
        if index + 1 < len(parts):
            return parts[index + 1]
    return "R0001"


def _latest_checkpoint(ctx: TargetRepoContext) -> str | None:
    checkpoints = sorted(
        path
        for path in ctx.paths.integration_checkpoints_dir.glob("P*.json")
        if not path.name.endswith("_cleanliness.json")
    )
    if not checkpoints:
        return None
    return checkpoints[-1].relative_to(ctx.root).as_posix()


def _goal_progress_summary(ctx: TargetRepoContext) -> dict:
    path = ctx.paths.workflow_dir / "goal_progress.json"
    if not path.exists():
        return {}
    progress = read_json(path)
    counts = progress.get("counts", {})
    return {
        "overall_goal_status": progress.get("overall_goal_status"),
        "proven": counts.get("proven", 0),
        "required_obligations": counts.get("required_obligations", 0),
    }


def _run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout
