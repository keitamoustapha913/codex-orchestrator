from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.state import now_iso
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.workflow_identity import read_workflow_identity


ACTIVE_TOP_LEVEL_NAMES = {
    "state.json",
    "run_manifest.json",
    "operator_events.jsonl",
    "prompt_index.json",
    "loop_governor.json",
    "goal_spec.json",
    "workflow_identity.json",
    "rerun_preflight_result.json",
    "patchlets",
    "runs",
    "reports",
    "failures",
    "repair_plans",
    "subprompts",
    "integration",
    "apply_results",
    "invocations",
    "census",
    "global_verification",
    "transaction_groups",
    "final_verification.json",
    "final_verification.md",
    "invariants.json",
    "inventory_graph.json",
    "inventory_table.md",
    "master_prompt.md",
    "path_mapping.json",
    "search_evidence.jsonl",
    "search_evidence.md",
}


def registry_path(repo_root: Path | str) -> Path:
    return Path(repo_root) / ".codex-orchestrator" / "workflows" / "registry.json"


def read_workflow_registry(repo_root: Path | str) -> dict[str, Any]:
    path = registry_path(repo_root)
    if path.exists():
        return read_json(path)
    return {"schema_version": "1.0", "kind": "workflow_registry", "active_workflow_id": None, "workflows": []}


def write_workflow_registry(repo_root: Path | str, registry: dict[str, Any]) -> dict[str, Any]:
    write_json(registry_path(repo_root), registry)
    return registry


def record_active_workflow(ctx: TargetRepoContext, identity: dict[str, Any]) -> dict[str, Any]:
    registry = read_workflow_registry(ctx.root)
    workflow_id = identity.get("workflow_id")
    registry["active_workflow_id"] = workflow_id
    existing = {entry.get("workflow_id"): entry for entry in registry.get("workflows", [])}
    record = existing.get(workflow_id, {})
    record.update(
        {
            "workflow_id": workflow_id,
            "run_id": identity.get("run_id"),
            "status": _current_stage(ctx),
            "artifact_root": ".codex-orchestrator",
            "created_at": identity.get("created_at") or now_iso(),
            "archived_at": record.get("archived_at"),
            "goal_fingerprint": identity.get("goal_fingerprint"),
        }
    )
    existing[workflow_id] = record
    registry["workflows"] = list(existing.values())
    return write_workflow_registry(ctx.root, registry)


def next_run_id(repo_root: Path | str) -> str:
    registry = read_workflow_registry(repo_root)
    highest = 0
    for entry in registry.get("workflows", []):
        run_id = entry.get("run_id")
        if isinstance(run_id, str) and run_id.startswith("R") and run_id[1:].isdigit():
            highest = max(highest, int(run_id[1:]))
    return f"R{highest + 1:04d}"


def archive_current_workflow(ctx: TargetRepoContext) -> dict[str, Any]:
    wf = ctx.paths.workflow_dir
    identity = read_workflow_identity(ctx.root) or {}
    workflow_id = identity.get("workflow_id") or "unknown-workflow"
    stamp = now_iso().replace(":", "").replace("-", "")
    archive_dir = wf / "archives" / f"{stamp}-{workflow_id}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir = archive_dir / "snapshot"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    if wf.exists():
        for child in sorted(wf.iterdir()):
            if child.name in {"archives", "workflows"}:
                continue
            destination = snapshot_dir / child.name
            if child.is_dir():
                shutil.copytree(child, destination, dirs_exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(child, destination)
            copied.append(child.name)
    result = {
        "schema_version": "1.0",
        "kind": "workflow_archive_result",
        "created_at": now_iso(),
        "workflow_id": workflow_id,
        "archive_path": archive_dir.relative_to(ctx.root).as_posix(),
        "snapshot_path": snapshot_dir.relative_to(ctx.root).as_posix(),
        "copied_top_level_entries": copied,
    }
    write_json(archive_dir / "archive_result.json", result)
    registry = read_workflow_registry(ctx.root)
    for entry in registry.get("workflows", []):
        if entry.get("workflow_id") == workflow_id:
            entry["status"] = "ARCHIVED"
            entry["archived_at"] = result["created_at"]
            entry["archive_path"] = result["archive_path"]
    registry["active_workflow_id"] = None
    write_workflow_registry(ctx.root, registry)
    return result


def reset_current_workflow(ctx: TargetRepoContext, *, archive: bool = True, hard_delete_artifacts: bool = False) -> dict[str, Any]:
    archive_result = archive_current_workflow(ctx) if archive and ctx.paths.workflow_dir.exists() else None
    removed: list[str] = []
    wf = ctx.paths.workflow_dir
    wf.mkdir(parents=True, exist_ok=True)
    for name in sorted(ACTIVE_TOP_LEVEL_NAMES):
        path = wf / name
        if not path.exists():
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed.append(name)
    if hard_delete_artifacts and ctx.probe_dir.exists():
        shutil.rmtree(ctx.probe_dir)
        removed.append(".artifacts/probes")
    result = {
        "schema_version": "1.0",
        "kind": "workflow_reset_result",
        "created_at": now_iso(),
        "archive": archive,
        "archive_result": archive_result,
        "removed_top_level_entries": removed,
    }
    write_json(wf / "reset_result.json", result)
    return result


def _current_stage(ctx: TargetRepoContext) -> str | None:
    if not ctx.paths.state.exists():
        return None
    try:
        return read_json(ctx.paths.state).get("stage")
    except Exception:
        return None
