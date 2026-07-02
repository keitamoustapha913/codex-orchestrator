from __future__ import annotations

import re
from pathlib import PurePosixPath

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.state import load_state, transition
from codex_orchestrator.target_repo import TargetRepoContext


def _slug(path: str) -> str:
    stem = PurePosixPath(path).stem or "repo"
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", stem).strip("_")[:40] or "repo"


def _select_runtime_file(ctx: TargetRepoContext) -> str:
    graph = read_json(ctx.paths.inventory_graph) if ctx.paths.inventory_graph.exists() else {"nodes": []}
    for node in graph.get("nodes", []):
        file = node.get("file")
        if file and not file.startswith(".codex-orchestrator/") and not file.startswith(".artifacts/"):
            return file
    if ctx.paths.census_repo_files.exists():
        for line in ctx.paths.census_repo_files.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith(".codex-orchestrator/") and not line.startswith(".artifacts/"):
                return line
    raise RuntimeError("Cannot compile patchlet: no product/runtime file found in inventory or census")


def compile_patchlets(ctx: TargetRepoContext) -> dict:
    runtime_file = _select_runtime_file(ctx)
    slug = _slug(runtime_file)
    subprompt_rel = f".codex-orchestrator/subprompts/0001_{slug}.md"
    patchlet = {
        "schema_version": "1.0",
        "kind": "patchlet",
        "patchlet_id": "P0001",
        "subprompt_path": subprompt_rel,
        "master_goal_ids": ["G001"],
        "invariant_ids": ["I001"],
        "evidence_ids": ["E001"],
        "graph_node_ids": ["N001"],
        "allowed_product_runtime_file": runtime_file,
        "allowed_artifact_dirs": [
            ".artifacts/probes/",
            ".codex-orchestrator/reports/",
            ".codex-orchestrator/runs/",
        ],
        "transaction_group_id": "TG001",
        "depends_on": [],
        "status": "PENDING",
    }
    index = {"schema_version": "1.0", "kind": "patchlet_index", "patchlets": [patchlet]}
    write_json(ctx.paths.patchlet_index, index)
    write_json(ctx.paths.transaction_groups, {
        "schema_version": "1.0",
        "kind": "transaction_groups",
        "transaction_groups": [{
            "schema_version": "1.0",
            "kind": "transaction_group",
            "transaction_group_id": "TG001",
            "description": "MVP transaction group for P0001",
            "patchlet_ids": ["P0001"],
            "invariant_ids": ["I001"],
            "verification_commands": [],
            "status": "PENDING",
        }],
    })
    subprompt = ctx.root / subprompt_rel
    subprompt.parent.mkdir(parents=True, exist_ok=True)
    subprompt.write_text(
        f"# Root-Cause Patchlet P0001\n\n"
        f"Allowed product/runtime file: `{runtime_file}`\n\n"
        "## ROOT-CAUSE PROBE-ONLY INVESTIGATION\n\n"
        "First create and run a minimal direct runtime probe under `.artifacts/probes/P0001/`. "
        "Do not edit product/runtime code during this investigation gate.\n\n"
        "## Proof-of-fix gate\n\n"
        "Only after the direct probe proves the root cause may the allowed file be edited. "
        "After implementation, rerun baseline, proof-of-fix, and negative-control probes.\n\n"
        "## Report contract\n\n"
        "Write `.codex-orchestrator/reports/P0001.json` with status COMPLETE, "
        "VERIFIED_NO_CHANGE_NEEDED, BLOCKED_WITH_EVIDENCE, or FAILED_WITH_EVIDENCE.\n",
        encoding="utf-8",
    )
    state = load_state(ctx)
    state.pending_patchlets = ["P0001"]
    transition(ctx, state, "PATCHLETS_READY", reason="patchlets compiled")
    return index
