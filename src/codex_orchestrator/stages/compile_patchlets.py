from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath

from codex_orchestrator.codex_execution_policy import resolve_patchlet_timeout_seconds, soft_deadline_seconds
from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.state import load_state, transition
from codex_orchestrator.target_repo import TargetRepoContext


def _slug(path: str) -> str:
    stem = PurePosixPath(path).stem or "repo"
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", stem).strip("_")[:40] or "repo"


def _node_file_map(ctx: TargetRepoContext) -> dict[str, str]:
    graph = read_json(ctx.paths.inventory_graph) if ctx.paths.inventory_graph.exists() else {"nodes": []}
    node_map: dict[str, str] = {}
    for node in graph.get("nodes", []):
        file = node.get("file")
        if file and not file.startswith(".codex-orchestrator/") and not file.startswith(".artifacts/"):
            node_map[node["id"]] = file
    return node_map


def _load_invariants(ctx: TargetRepoContext) -> list[dict]:
    if not ctx.paths.invariants.exists():
        raise RuntimeError("Cannot compile patchlets: invariants.json is missing")
    document = read_json(ctx.paths.invariants)
    return document.get("invariants", [])


def _existing_patchlets(ctx: TargetRepoContext) -> dict[str, dict]:
    if not ctx.paths.patchlet_index.exists():
        return {}
    index = read_json(ctx.paths.patchlet_index)
    return {patchlet["patchlet_id"]: patchlet for patchlet in index.get("patchlets", [])}


def _real_codex_contract_text() -> str:
    contract_path = os.environ.get("CXOR_REAL_CODEX_CONTRACT_PATH")
    if not contract_path:
        return ""
    path = Path(contract_path)
    if not path.exists():
        raise RuntimeError(f"Missing real Codex contract template: {path}")
    return "\n\n" + path.read_text(encoding="utf-8").strip() + "\n"


def compile_patchlets(ctx: TargetRepoContext) -> dict:
    node_file_map = _node_file_map(ctx)
    invariants = _load_invariants(ctx)
    existing_patchlets = _existing_patchlets(ctx)
    real_codex_contract = _real_codex_contract_text()
    timeout_seconds = resolve_patchlet_timeout_seconds(os.environ)
    soft_deadline = soft_deadline_seconds(timeout_seconds)
    patchlets: list[dict] = []
    transaction_groups: list[dict] = []

    for idx, invariant in enumerate(invariants, start=1):
        patchlet_id = f"P{idx:04d}"
        node_ids = invariant.get("graph_node_ids", [])
        producer_nodes = invariant.get("producer_nodes", [])
        candidate_nodes = producer_nodes + [node_id for node_id in node_ids if node_id not in producer_nodes]
        runtime_file = next((node_file_map[node_id] for node_id in candidate_nodes if node_id in node_file_map), None)
        if runtime_file is None:
            raise RuntimeError(f"Cannot compile patchlet for invariant {invariant['invariant_id']}: no product/runtime file found")
        slug = _slug(runtime_file)
        subprompt_rel = f".codex-orchestrator/subprompts/{idx:04d}_{slug}.md"
        existing = existing_patchlets.get(patchlet_id, {})
        patchlet = {
            "schema_version": "1.0",
            "kind": "patchlet",
            "patchlet_id": patchlet_id,
            "subprompt_path": subprompt_rel,
            "master_goal_ids": [invariant["master_goal_id"]],
            "invariant_ids": [invariant["invariant_id"]],
            "evidence_ids": invariant["evidence_ids"],
            "graph_node_ids": invariant["graph_node_ids"],
            "allowed_product_runtime_file": runtime_file,
            "allowed_artifact_dirs": [
                ".artifacts/probes/",
                ".codex-orchestrator/reports/",
                ".codex-orchestrator/runs/",
            ],
            "transaction_group_id": f"TG{idx:03d}",
            "depends_on": [],
            "status": existing.get("status", "PENDING"),
        }
        for key in ["repair_plan_id", "source_failure_ids", "is_repair_patchlet"]:
            if key in existing:
                patchlet[key] = existing[key]
        patchlets.append(patchlet)
        transaction_groups.append({
            "schema_version": "1.0",
            "kind": "transaction_group",
            "transaction_group_id": f"TG{idx:03d}",
            "description": f"Transaction group for {patchlet_id}",
            "patchlet_ids": [patchlet_id],
            "invariant_ids": [invariant["invariant_id"]],
            "verification_commands": invariant.get("regression_commands", []),
            "status": "PENDING",
            "result": None,
            "failure_ids": [],
        })

        subprompt = ctx.root / subprompt_rel
        subprompt.parent.mkdir(parents=True, exist_ok=True)
        subprompt.write_text(
            f"# Root-Cause Patchlet {patchlet_id}\n\n"
            f"Allowed product/runtime file: `{runtime_file}`\n\n"
            "## ROOT-CAUSE PROBE-ONLY INVESTIGATION\n\n"
            f"First create and run a minimal direct runtime probe under `.artifacts/probes/{patchlet_id}/`. "
            "Do not edit product/runtime code during this investigation gate.\n\n"
            "## Durable probe artifacts\n\n"
            f"Write durable probe artifacts under `.artifacts/probes/{patchlet_id}/run_001/`, including "
            "`row_ledger.jsonl`, `trace_ledger.jsonl`, `before_state.json`, `after_state.json`, and `cleanup_proof.json`.\n\n"
            "## TDD checklist\n\n"
            "1. Write or identify the failing test first.\n"
            "2. Run the focused red test before editing the allowed product/runtime file.\n"
            "3. Implement the smallest fix inside the allowed file boundary.\n"
            "4. Rerun focused tests, then relevant suites, then full verification.\n\n"
            "## Proof-of-fix gate\n\n"
            "Only after the direct probe proves the root cause may the allowed file be edited. "
            "After implementation, rerun baseline, proof-of-fix, and negative-control probes.\n\n"
            "## Report contract\n\n"
            f"Write `.codex-orchestrator/reports/{patchlet_id}.json` with status COMPLETE, "
            "VERIFIED_NO_CHANGE_NEEDED, BLOCKED_WITH_EVIDENCE, or FAILED_WITH_EVIDENCE, "
            "and include valid `probe_artifact_refs`.\n"
            "\n## Wall-clock budget\n\n"
            f"You have a hard timeout of {timeout_seconds} seconds. "
            f"Aim to finish by {soft_deadline} seconds. "
            "If you cannot complete, write `worker_stage/05_final_report.md` with an explicit "
            "BLOCKED or FAILED status and preserve what you learned. "
            "Do not keep investigating indefinitely. Do not use blind retry.\n"
            + real_codex_contract,
            encoding="utf-8",
        )

    for patchlet_id, patchlet in existing_patchlets.items():
        if patchlet_id.startswith("P") and patchlet not in patchlets and patchlet.get("is_repair_patchlet"):
            patchlets.append(patchlet)

    index = {"schema_version": "1.0", "kind": "patchlet_index", "patchlets": patchlets}
    write_json(ctx.paths.patchlet_index, index)
    write_json(ctx.paths.transaction_groups, {
        "schema_version": "1.0",
        "kind": "transaction_groups",
        "transaction_groups": transaction_groups,
    })
    state = load_state(ctx)
    state.pending_patchlets = [
        patchlet["patchlet_id"]
        for patchlet in patchlets
        if patchlet.get("status") == "PENDING"
    ]
    transition(ctx, state, "PATCHLETS_READY", reason="patchlets compiled")
    return index
