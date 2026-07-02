from __future__ import annotations

import json
import subprocess
import shutil
import tempfile
from pathlib import Path
from typing import Any

from codex_orchestrator.git_guard import repo_head, snapshot_status
from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.paths import relative_to_repo
from codex_orchestrator.state import now_iso
from codex_orchestrator.target_repo import TargetRepoContext


DEFAULT_INTEGRATION_RUN_ID = "R0001"


def ensure_integration_state(ctx: TargetRepoContext) -> dict[str, Any]:
    ctx.paths.integration_dir.mkdir(parents=True, exist_ok=True)
    ctx.paths.integration_checkpoints_dir.mkdir(parents=True, exist_ok=True)
    if not ctx.paths.accepted_changes.exists():
        ctx.paths.accepted_changes.write_text("", encoding="utf-8")
    if ctx.paths.integration_state.exists():
        state = read_json(ctx.paths.integration_state)
        current_head = repo_head(ctx.root)
        if not state.get("accepted_patchlets") and current_head and current_head != state.get("target_head_sha"):
            state["target_head_sha"] = current_head
            state["integration_sha"] = current_head
            write_json(ctx.paths.integration_state, state)
        return state

    target_head_sha = repo_head(ctx.root)
    state = {
        "schema_version": "1.0",
        "kind": "integration_state",
        "target_head_sha": target_head_sha,
        "integration_ref": f"refs/cxor/runs/{DEFAULT_INTEGRATION_RUN_ID}/integration",
        "integration_sha": target_head_sha,
        "apply_mode": "finalize_only",
        "target_product_dirty_allowed": False,
        "accepted_patchlets": [],
        "last_checkpoint_path": None,
        "final_diff_path": relative_to_repo(ctx.root, ctx.paths.final_diff_path),
    }
    write_json(ctx.paths.integration_state, state)
    return state


def record_accepted_change(
    ctx: TargetRepoContext,
    *,
    patchlet: dict[str, Any],
    attempt_id: str,
    changed_product_runtime_files: list[str],
    diff_path: Path,
    report_path: Path | None,
    probe_root: Path,
    wrapper_gate_result: str | None,
    new_integration_sha: str | None = None,
) -> dict[str, Any]:
    state = ensure_integration_state(ctx)
    patchlet_id = patchlet["patchlet_id"]
    previous_sha = state.get("integration_sha")
    new_sha = new_integration_sha or previous_sha
    run_id = DEFAULT_INTEGRATION_RUN_ID
    checkpoint_path = ctx.paths.integration_checkpoints_dir / f"{patchlet_id}.json"
    target_clean_after_checkpoint = _target_product_runtime_clean(ctx)

    entry = {
        "schema_version": "1.0",
        "kind": "accepted_change",
        "run_id": run_id,
        "patchlet_id": patchlet_id,
        "attempt_id": attempt_id,
        "previous_integration_sha": previous_sha,
        "new_integration_sha": new_sha,
        "integration_ref": state["integration_ref"],
        "allowed_product_runtime_files": [patchlet.get("allowed_product_runtime_file")]
        if patchlet.get("allowed_product_runtime_file")
        else [],
        "changed_product_runtime_files": changed_product_runtime_files,
        "diff_path": relative_to_repo(ctx.root, diff_path),
        "report_path": relative_to_repo(ctx.root, report_path) if report_path else None,
        "probe_root": relative_to_repo(ctx.root, probe_root),
        "wrapper_gate_result": wrapper_gate_result,
        "accepted_at": now_iso(),
    }
    with ctx.paths.accepted_changes.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")

    checkpoint = {
        "schema_version": "1.0",
        "kind": "integration_checkpoint",
        "run_id": run_id,
        "patchlet_id": patchlet_id,
        "attempt_id": attempt_id,
        "previous_integration_sha": previous_sha,
        "new_integration_sha": new_sha,
        "integration_ref": state["integration_ref"],
        "changed_product_runtime_files": changed_product_runtime_files,
        "diff_path": relative_to_repo(ctx.root, diff_path),
        "wrapper_gate_result": wrapper_gate_result,
        "target_working_tree_clean_after_checkpoint": target_clean_after_checkpoint,
    }
    write_json(checkpoint_path, checkpoint)

    accepted_patchlets = list(state.get("accepted_patchlets", []))
    if patchlet_id not in accepted_patchlets:
        accepted_patchlets.append(patchlet_id)
    state.update(
        {
            "integration_sha": new_sha,
            "accepted_patchlets": accepted_patchlets,
            "last_checkpoint_path": relative_to_repo(ctx.root, checkpoint_path),
        }
    )
    write_json(ctx.paths.integration_state, state)
    return checkpoint


def advance_integration_ref_from_worktree(
    ctx: TargetRepoContext,
    *,
    worktree_path: Path,
    patchlet_id: str,
    changed_product_runtime_files: list[str],
) -> str:
    state = ensure_integration_state(ctx)
    previous_sha = state.get("integration_sha")
    if not previous_sha:
        raise RuntimeError("integration_state.json is missing integration_sha")
    if not changed_product_runtime_files:
        return str(previous_sha)

    subprocess_run(
        ["git", "-C", str(worktree_path), "reset", "--mixed", str(previous_sha)],
    )
    subprocess_run(
        ["git", "-C", str(worktree_path), "add", "--", *changed_product_runtime_files],
    )
    subprocess_run(
        [
            "git",
            "-C",
            str(worktree_path),
            "-c",
            "user.name=cxor",
            "-c",
            "user.email=cxor@example.invalid",
            "commit",
            "-m",
            f"cxor: accept {patchlet_id}",
        ],
    )
    new_sha = subprocess_run(["git", "-C", str(worktree_path), "rev-parse", "HEAD"]).stdout.strip()
    subprocess_run(["git", "-C", str(ctx.root), "update-ref", state["integration_ref"], new_sha])
    return new_sha


def advance_integration_ref_from_diff(
    ctx: TargetRepoContext,
    *,
    diff_path: Path,
    patchlet_id: str,
    changed_product_runtime_files: list[str],
) -> str:
    state = ensure_integration_state(ctx)
    previous_sha = state.get("integration_sha")
    if not previous_sha:
        raise RuntimeError("integration_state.json is missing integration_sha")
    if not changed_product_runtime_files:
        return str(previous_sha)

    temp_root = Path(tempfile.mkdtemp(prefix=f"cxor-integrate-{patchlet_id.lower()}-", dir="/tmp")).resolve()
    try:
        subprocess_run(["git", "-C", str(ctx.root), "worktree", "add", "--detach", str(temp_root), str(previous_sha)])
        subprocess_run(["git", "-C", str(temp_root), "apply", str(diff_path)])
        new_sha = advance_integration_ref_from_worktree(
            ctx,
            worktree_path=temp_root,
            patchlet_id=patchlet_id,
            changed_product_runtime_files=changed_product_runtime_files,
        )
    finally:
        subprocess.run(
            ["git", "-C", str(ctx.root), "worktree", "remove", "--force", str(temp_root)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if temp_root.exists():
            shutil.rmtree(temp_root)
    return new_sha


def subprocess_run(args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"command failed: {' '.join(args)}")
    return result


def _target_product_runtime_clean(ctx: TargetRepoContext) -> bool:
    status = snapshot_status(ctx.root).status
    for path in status:
        if path.startswith(".codex-orchestrator/") or path.startswith(".artifacts/"):
            continue
        return False
    return True


def target_product_runtime_clean(ctx: TargetRepoContext) -> bool:
    return _target_product_runtime_clean(ctx)


def write_final_diff(ctx: TargetRepoContext) -> dict[str, str | None]:
    state = ensure_integration_state(ctx)
    target_head = state.get("target_head_sha")
    integration_sha = state.get("integration_sha")
    ctx.paths.integration_dir.mkdir(parents=True, exist_ok=True)
    if target_head and integration_sha:
        result = subprocess.run(
            ["git", "-C", str(ctx.root), "diff", str(target_head), str(integration_sha)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "unable to generate final diff")
        ctx.paths.final_diff_path.write_text(result.stdout, encoding="utf-8")
    else:
        ctx.paths.final_diff_path.write_text("", encoding="utf-8")
    return {
        "integration_ref": state.get("integration_ref"),
        "integration_sha": integration_sha,
        "target_head_sha": target_head,
        "final_diff_path": relative_to_repo(ctx.root, ctx.paths.final_diff_path),
    }
