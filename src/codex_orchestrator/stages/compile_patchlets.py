from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath

from codex_orchestrator.codex_execution_policy import resolve_patchlet_timeout_seconds, soft_deadline_seconds
from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.operator_events import append_operator_event
from codex_orchestrator.patchlet_planner import validate_patchlet_plan
from codex_orchestrator.prompt_index import upsert_prompt_index_entry
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


def _decomposition_dir(ctx: TargetRepoContext) -> Path:
    return ctx.paths.workflow_dir / "decomposition"


def _patchlet_plan_path(ctx: TargetRepoContext) -> Path:
    return _decomposition_dir(ctx) / "patchlet_plan.json"


def _file_mapping_result_path(ctx: TargetRepoContext) -> Path:
    return _decomposition_dir(ctx) / "file_mapping_result.json"


def _transaction_group_plan_path(ctx: TargetRepoContext) -> Path:
    return _decomposition_dir(ctx) / "transaction_group_plan.json"


def _mapping_rejection(ctx: TargetRepoContext) -> dict | None:
    path = _file_mapping_result_path(ctx)
    if not path.exists():
        return None
    mapping = read_json(path)
    if mapping.get("accepted") is not False:
        return None
    return mapping


def _ensure_decomposition_plan(ctx: TargetRepoContext, *, timeout_seconds: int) -> dict | None:
    required_artifacts = [
        _decomposition_dir(ctx) / "impact_dependency_analysis.json",
        _decomposition_dir(ctx) / "work_decomposition_plan.json",
        _decomposition_dir(ctx) / "work_slices.json",
        _decomposition_dir(ctx) / "patchlet_plan.json",
        _decomposition_dir(ctx) / "dependency_graph.json",
        _decomposition_dir(ctx) / "transaction_group_plan.json",
    ]
    missing = [str(path.relative_to(ctx.root)) for path in required_artifacts if not path.exists()]
    if missing:
        append_operator_event(
            ctx.root,
            event_type="work_decomposition_invalid",
            severity="error",
            stage="PATCHLET_COMPILATION_REQUIRED",
            summary="Patchlet compilation blocked: required decomposition artifacts are missing.",
            artifact_paths=[],
            details={"missing_artifacts": missing, "failure_signature": "missing_required_decomposition_artifact"},
        )
        raise RuntimeError("Cannot compile patchlets: missing required decomposition artifacts: " + ", ".join(missing))
    plan_path = _patchlet_plan_path(ctx)
    plan = read_json(plan_path)
    validate_patchlet_plan(plan)
    return plan


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


def _semantic_fields(patchlet: dict, semantic_criteria: list[dict]) -> None:
    if not semantic_criteria:
        return
    criterion = semantic_criteria[0]
    patchlet["semantic_criteria"] = [item["criterion_id"] for item in semantic_criteria]
    patchlet["expected_behavior"] = {
        "kind": criterion.get("kind"),
        "target_file": criterion.get("target_file"),
        "module_name": criterion.get("module_name"),
        "function_name": criterion.get("function_name"),
        "expected_value": criterion.get("expected_value"),
    }
    if criterion.get("kind") == "python_module_function_returns":
        patchlet["title"] = (
            f"{patchlet.get('allowed_product_runtime_file')} — make "
            f"{criterion.get('module_name')}.{criterion.get('function_name')} "
            f"return {criterion.get('expected_value')!r}"
        )


def _slice_boundary_prompt_section(patchlet: dict) -> str:
    boundary = patchlet.get("slice_change_boundary") or {}
    if not boundary:
        return ""
    allowed_changes = boundary.get("allowed_changes") or []
    forbidden = boundary.get("forbidden_changes") or []
    current_boundary = boundary.get("current_boundary") or patchlet.get("current_slice_boundary") or {}
    future_boundaries = boundary.get("future_boundaries") or patchlet.get("future_slice_boundaries") or []
    current_lines = []
    for change in allowed_changes:
        if change.get("operation") == "replace_line":
            current_lines.append(f"- replace exactly `{change.get('old_line')}` with `{change.get('new_line')}`")
        elif change.get("key"):
            current_lines.append(f"- update `{change.get('key')}` only")
    if current_boundary:
        current_lines.append(
            "- current structured boundary: "
            f"file `{current_boundary.get('file')}`, "
            f"symbol `{current_boundary.get('symbol')}`, "
            f"expected observation `{current_boundary.get('expected_observation')}`, "
            f"goal `{current_boundary.get('goal_item_id')}`, "
            f"proof `{current_boundary.get('proof_obligation_id')}`, "
            f"probes `{', '.join(current_boundary.get('probe_ids') or [])}`"
        )
    forbidden_lines = [f"- `{row.get('key')}`" for row in forbidden if row.get("key")]
    forbidden_lines.extend(
        "- future structured boundary: "
        f"file `{row.get('file')}`, "
        f"symbol `{row.get('symbol')}`, "
        f"expected observation `{row.get('expected_observation')}`, "
        f"goal `{row.get('goal_item_id')}`, "
        f"proof `{row.get('proof_obligation_id')}`"
        for row in future_boundaries
    )
    return (
        "## Allowed change boundary\n\n"
        f"Boundary type: `{boundary.get('boundary_type')}`\n\n"
        + ("\n".join(current_lines) if current_lines else "- no static allowed changes declared")
        + "\n\nDo not change future-slice keys:\n"
        + ("\n".join(forbidden_lines) if forbidden_lines else "- none")
        + "\n\n"
        "If you change future-slice keys in this patchlet, the orchestrator will reject the patchlet as over-scoped even though the file is allowed.\n\n"
        "Your local proof for this patchlet should prove only the listed current allowed change.\n\n"
    )


def _write_patchlet_subprompt(
    ctx: TargetRepoContext,
    *,
    patchlet: dict,
    idx: int,
    runtime_file: str,
    semantic_criteria: list[dict],
    timeout_seconds: int,
    soft_deadline: int,
    real_codex_contract: str,
) -> None:
    patchlet_id = patchlet["patchlet_id"]
    subprompt = ctx.root / patchlet["subprompt_path"]
    subprompt.parent.mkdir(parents=True, exist_ok=True)
    semantic_section = _semantic_subprompt_section(semantic_criteria)
    forbidden_files = patchlet.get("prompt_scope", {}).get("forbidden_edit_files", [])
    forbidden_text = "\n".join(f"- `{path}`" for path in forbidden_files) or "- any product/runtime file other than the single allowed file"
    work_slice_id = patchlet.get("work_slice_id")
    dependency_ids = patchlet.get("dependency_patchlet_ids", [])
    boundary_section = _slice_boundary_prompt_section(patchlet)
    subprompt.write_text(
        f"# Root-Cause Patchlet {patchlet_id}\n\n"
        "This patchlet is a small bounded work unit.\n\n"
        f"Work slice ID: `{work_slice_id}`\n\n"
        f"Allowed product/runtime file: `{runtime_file}`\n\n"
        f"Allowed edit path: `{runtime_file}`\n\n"
        "Forbidden product/runtime edit paths:\n"
        f"{forbidden_text}\n\n"
        f"Dependency patchlets: {', '.join(dependency_ids) or 'none'}\n\n"
        f"Proof obligations: {', '.join(patchlet.get('proof_obligation_ids', [])) or 'none'}\n\n"
        f"Goal items: {', '.join(patchlet.get('goal_item_ids', [])) or 'none'}\n\n"
        f"{boundary_section}"
        f"Scope statement: {patchlet.get('scope_statement') or 'Only perform this bounded slice.'}\n\n"
        "Do not attempt to solve unrelated work slices.\n\n"
        "Do not edit any product/runtime file except the single allowed file.\n\n"
        "Do not create root-level scratch/check files such as `.report_check.json`; use `/tmp` for scratch checks.\n\n"
        "Do not compact memory by summarizing broad unrelated context.\n\n"
        "Finish within the patchlet time budget.\n\n"
        "If blocked, write BLOCKED_WITH_EVIDENCE with the specific missing dependency or proof obstacle.\n\n"
        f"{semantic_section}"
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
    upsert_prompt_index_entry(ctx.root, {
        "kind": "patchlet_subprompt",
        "stage": "PATCHLET_COMPILATION_REQUIRED",
        "patchlet_id": patchlet_id,
        "attempt_id": None,
        "title": patchlet.get("title") or f"{runtime_file} — patchlet {patchlet_id}",
        "summary": f"Patchlet subprompt for {patchlet_id}.",
        "path": subprompt,
        "subprompt_path": patchlet["subprompt_path"],
        "model": None,
        "reasoning": None,
        "contracts": [],
        "artifact_paths": [patchlet["subprompt_path"]],
    })


def _compile_from_patchlet_plan(
    ctx: TargetRepoContext,
    *,
    patchlet_plan: dict,
    invariants: list[dict],
    existing_patchlets: dict[str, dict],
    semantic_criteria: list[dict],
    timeout_seconds: int,
    soft_deadline: int,
    real_codex_contract: str,
) -> tuple[list[dict], list[dict]]:
    invariant = invariants[0] if invariants else {}
    patchlets: list[dict] = []
    for idx, planned in enumerate(patchlet_plan.get("patchlets", []), start=1):
        runtime_file = planned["allowed_product_runtime_file"]
        if len(planned.get("allowed_product_runtime_files", [runtime_file])) != 1:
            raise RuntimeError(f"{planned['patchlet_id']} violates one allowed product/runtime file rule")
        patchlet_id = planned["patchlet_id"]
        existing = existing_patchlets.get(patchlet_id, {})
        slug = _slug(runtime_file)
        patchlet = {
            "schema_version": "1.0",
            "kind": "patchlet",
            "patchlet_id": patchlet_id,
            "subprompt_path": f".codex-orchestrator/subprompts/{idx:04d}_{slug}.md",
            "master_goal_ids": [invariant["master_goal_id"]] if invariant.get("master_goal_id") else [],
            "invariant_ids": [invariant["invariant_id"]] if invariant.get("invariant_id") else [],
            "evidence_ids": invariant.get("evidence_ids", []),
            "graph_node_ids": invariant.get("graph_node_ids", []),
            "allowed_product_runtime_file": runtime_file,
            "allowed_product_runtime_files": [runtime_file],
            "allowed_artifact_dirs": [
                ".artifacts/probes/",
                ".codex-orchestrator/reports/",
                ".codex-orchestrator/runs/",
            ],
            "transaction_group_id": None,
            "depends_on": list(planned.get("dependency_patchlet_ids", [])),
            "dependency_patchlet_ids": list(planned.get("dependency_patchlet_ids", [])),
            "downstream_patchlet_ids": list(planned.get("downstream_patchlet_ids", [])),
            "work_slice_id": planned.get("work_slice_id"),
            "proof_obligation_ids": list(planned.get("proof_obligation_ids", [])),
            "goal_item_ids": list(planned.get("goal_item_ids", [])),
            "time_budget_seconds": planned.get("time_budget_seconds", timeout_seconds),
            "prompt_budget_policy": planned.get("prompt_budget_policy", {}),
            "prompt_scope": {
                "memory_compacting_required": planned.get("prompt_scope", {}).get("memory_compacting_required", False),
                "scope_statement": planned.get("scope_statement"),
                **planned.get("prompt_scope", {}),
            },
            "slice_change_boundary": planned.get("slice_change_boundary"),
            "boundary_enforcement_status": planned.get("boundary_enforcement_status"),
            "status": existing.get("status", "PENDING"),
        }
        _semantic_fields(patchlet, semantic_criteria)
        for key in ["repair_plan_id", "source_failure_ids", "is_repair_patchlet"]:
            if key in existing:
                patchlet[key] = existing[key]
        patchlets.append(patchlet)

    group_plan_path = _transaction_group_plan_path(ctx)
    if group_plan_path.exists():
        planned_groups = read_json(group_plan_path).get("transaction_groups", [])
    else:
        planned_groups = [
            {
                "transaction_group_id": f"TG{idx:03d}",
                "patchlet_ids": [patchlet["patchlet_id"]],
                "goal_item_ids": patchlet.get("goal_item_ids", []),
                "proof_obligation_ids": patchlet.get("proof_obligation_ids", []),
            }
            for idx, patchlet in enumerate(patchlets, start=1)
        ]
    patchlets_by_id = {patchlet["patchlet_id"]: patchlet for patchlet in patchlets}
    transaction_groups: list[dict] = []
    for group in planned_groups:
        for pid in group.get("patchlet_ids", []):
            if pid in patchlets_by_id:
                patchlets_by_id[pid]["transaction_group_id"] = group["transaction_group_id"]
        transaction_groups.append(
            {
                "schema_version": "1.0",
                "kind": "transaction_group",
                "transaction_group_id": group["transaction_group_id"],
                "description": group.get("operator_summary") or f"Transaction group for {', '.join(group.get('patchlet_ids', []))}",
                "patchlet_ids": list(group.get("patchlet_ids", [])),
                "invariant_ids": [invariant["invariant_id"]] if invariant.get("invariant_id") else [],
                "proof_obligation_ids": list(group.get("proof_obligation_ids", [])),
                "goal_item_ids": list(group.get("goal_item_ids", [])),
                "dependency_patchlet_ids": list(group.get("dependency_patchlet_ids", [])),
                "verification_commands": invariant.get("regression_commands", []),
                "status": "PENDING",
                "result": None,
                "failure_ids": [],
            }
        )
    for idx, patchlet in enumerate(patchlets, start=1):
        if patchlet.get("transaction_group_id") is None:
            patchlet["transaction_group_id"] = f"TG{idx:03d}"
        _write_patchlet_subprompt(
            ctx,
            patchlet=patchlet,
            idx=idx,
            runtime_file=patchlet["allowed_product_runtime_file"],
            semantic_criteria=semantic_criteria,
            timeout_seconds=int(patchlet.get("time_budget_seconds") or timeout_seconds),
            soft_deadline=soft_deadline_seconds(int(patchlet.get("time_budget_seconds") or timeout_seconds)),
            real_codex_contract=real_codex_contract,
        )
    return patchlets, transaction_groups


def compile_patchlets(ctx: TargetRepoContext) -> dict:
    provability_path = ctx.paths.workflow_dir / "provability" / "provability_result.json"
    if provability_path.exists():
        provability = read_json(provability_path)
        if provability.get("can_start_product_patchlets") is not True:
            append_operator_event(
                ctx.root,
                event_type="goal_not_provable" if provability.get("provability_status") != "AMBIGUOUS" else "goal_ambiguous",
                severity="warning",
                stage="PROVABILITY_ASSESSMENT",
                summary="Product patchlet compilation blocked by early provability classification.",
                artifact_paths=[".codex-orchestrator/provability/provability_result.json"],
                details=provability,
            )
            index = {"schema_version": "1.0", "kind": "patchlet_index", "patchlets": []}
            write_json(ctx.paths.patchlet_index, index)
            state = load_state(ctx)
            state.pending_patchlets = []
            transition(ctx, state, "PATCHLETS_READY", reason="goal_not_provable_no_product_patchlets")
            return index
    invariants = _load_invariants(ctx)
    existing_patchlets = _existing_patchlets(ctx)
    real_codex_contract = _real_codex_contract_text()
    timeout_seconds = resolve_patchlet_timeout_seconds(os.environ)
    soft_deadline = soft_deadline_seconds(timeout_seconds)
    semantic_criteria: list[dict] = []
    patchlet_plan = _ensure_decomposition_plan(ctx, timeout_seconds=timeout_seconds)
    mapping_rejection = _mapping_rejection(ctx)
    if mapping_rejection is not None:
        append_operator_event(
            ctx.root,
            event_type="decomposition_mapping_rejected",
            severity="error",
            stage="PATCHLET_COMPILATION_REQUIRED",
            summary="Patchlet compilation blocked: required planning items could not be mapped to bounded work slices.",
            artifact_paths=[".codex-orchestrator/decomposition/file_mapping_result.json"],
            details={
                "failure_signature": "decomposition_mapping_rejected",
                "errors": mapping_rejection.get("errors", []),
                "unmapped_goal_item_ids": mapping_rejection.get("unmapped_goal_item_ids", []),
                "unmapped_proof_obligation_ids": mapping_rejection.get("unmapped_proof_obligation_ids", []),
                "ambiguous_goal_item_ids": mapping_rejection.get("ambiguous_goal_item_ids", []),
                "ambiguous_proof_obligation_ids": mapping_rejection.get("ambiguous_proof_obligation_ids", []),
                "missing_probe_obligation_ids": mapping_rejection.get("missing_probe_obligation_ids", []),
            },
        )
        index = {"schema_version": "1.0", "kind": "patchlet_index", "patchlets": []}
        write_json(ctx.paths.patchlet_index, index)
        write_json(ctx.paths.transaction_groups, {
            "schema_version": "1.0",
            "kind": "transaction_groups",
            "transaction_groups": [],
        })
        state = load_state(ctx)
        state.pending_patchlets = []
        transition(ctx, state, "FAILURE_CLASSIFICATION_REQUIRED", reason="decomposition_mapping_rejected")
        return index
    patchlets, transaction_groups = _compile_from_patchlet_plan(
        ctx,
        patchlet_plan=patchlet_plan,
        invariants=invariants,
        existing_patchlets=existing_patchlets,
        semantic_criteria=semantic_criteria,
        timeout_seconds=timeout_seconds,
        soft_deadline=soft_deadline,
        real_codex_contract=real_codex_contract,
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


def _semantic_subprompt_section(criteria: list[dict]) -> str:
    if not criteria:
        return ""
    lines = ["## Semantic acceptance criteria", ""]
    for criterion in criteria:
        if criterion.get("kind") == "python_module_function_returns":
            expected = criterion.get("expected_value")
            lines.extend(
                [
                    f"Criterion {criterion['criterion_id']}:",
                    "- Kind: python_module_function_returns",
                    f"- Target file: {criterion.get('target_file')}",
                    f"- Module: {criterion.get('module_name')}",
                    f"- Function: {criterion.get('function_name')}",
                    f"- Expected return value: {expected!r}",
                    f"- Required: {'yes' if criterion.get('required') else 'no'}",
                    "",
                    "This patchlet is not complete unless this criterion is satisfied.",
                    "Do not report VERIFIED_NO_CHANGE_NEEDED unless the criterion already passes.",
                    "",
                ]
            )
    return "\n".join(lines)
