from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from . import version
from .jsonio import read_json, write_json
from .state import now_iso
from .target_repo import TargetRepoContext


def init_run_manifest(ctx: TargetRepoContext, *, invocation_argv: list[str] | None = None) -> dict:
    manifest = {
        "schema_version": "1.0",
        "kind": "run_manifest",
        "workflow_id": None,
        "target_repo_root": str(ctx.root),
        "orchestrator_version": version.__version__,
        "invocation": {
            "argv": invocation_argv or sys.argv,
            "cwd": os.getcwd(),
            "resolved_target_repo": str(ctx.root),
        },
        "runs": [],
    }
    write_json(ctx.paths.run_manifest, manifest)
    return manifest


def load_run_manifest(ctx: TargetRepoContext) -> dict:
    if not ctx.paths.run_manifest.exists():
        return init_run_manifest(ctx)
    return read_json(ctx.paths.run_manifest)


def append_run_record(ctx: TargetRepoContext, record: dict[str, Any]) -> str:
    manifest = load_run_manifest(ctx)
    next_id = f"R{len(manifest.get('runs', [])) + 1:04d}"
    record = {
        "run_id": next_id,
        "created_at": now_iso(),
        **record,
    }
    manifest.setdefault("runs", []).append(record)
    write_json(ctx.paths.run_manifest, manifest)
    return next_id


def upsert_run_record(ctx: TargetRepoContext, *, attempt_id: str, record: dict[str, Any]) -> str:
    manifest = load_run_manifest(ctx)
    runs = manifest.setdefault("runs", [])
    existing = None
    for run in runs:
        if run.get("attempt_id") == attempt_id:
            existing = run
            break
    if existing is None:
        existing = {
            "run_id": f"R{len(runs) + 1:04d}",
            "created_at": now_iso(),
            "attempt_id": attempt_id,
            "lifecycle_events": [],
        }
        runs.append(existing)
    existing.update(record)
    lifecycle_status = record.get("lifecycle_status")
    if lifecycle_status:
        events = existing.setdefault("lifecycle_events", [])
        events.append({"stage": lifecycle_status, "at": now_iso()})
    write_json(ctx.paths.run_manifest, manifest)
    return str(existing["run_id"])
