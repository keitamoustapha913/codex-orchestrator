from __future__ import annotations

import re

from codex_orchestrator.jsonio import write_json
from codex_orchestrator.master_prompt_source import freeze_master_prompt
from codex_orchestrator.model_planning import (
    PlanningModelError,
    build_goal_interpretation_request,
    build_probe_planning_request,
    build_proof_planning_request,
    create_planning_model_client,
    run_planning_model,
    write_validation_result,
)
from codex_orchestrator.prompt_index import upsert_prompt_index_entry
from codex_orchestrator.operator_events import append_operator_event
from pathlib import Path

from codex_orchestrator.goal_interpretation import normalize_goal_interpretation, validate_goal_interpretation
from codex_orchestrator.goal_progress import update_goal_progress
from codex_orchestrator.state import load_state, transition
from codex_orchestrator.probe_plan import normalize_probe_plan, validate_probe_plan, validate_probe_plan_for_required_obligations
from codex_orchestrator.proof_obligations import normalize_proof_obligations, validate_proof_obligations
from codex_orchestrator.provability import classify_goal_provability, missing_goal_interpretation_provability, write_provability_result
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.workflow_identity import read_workflow_identity, write_workflow_identity


SECTION_NAMES = {
    "success goals": "success_goals",
    "target invariants": "target_invariants",
    "forbidden actions": "forbidden_actions",
    "runtime constraints": "runtime_constraints",
    "validation commands": "validation_commands",
    "allowed edit scope": "allowed_edit_scope",
    "must preserve": "must_preserve",
    "known failure modes": "known_failure_modes",
    "proof requirements": "proof_requirements",
}


def _normalize_heading(line: str) -> str | None:
    stripped = line.strip()
    if not stripped:
        return None
    stripped = stripped.lstrip("#").strip()
    if stripped.endswith(":"):
        stripped = stripped[:-1].strip()
    lowered = stripped.lower()
    return SECTION_NAMES.get(lowered)


def _parse_prompt_sections(text: str) -> dict[str, list[str]]:
    sections = {name: [] for name in SECTION_NAMES.values()}
    current: str | None = None
    for raw_line in text.splitlines():
        maybe_heading = _normalize_heading(raw_line)
        if maybe_heading is not None:
            current = maybe_heading
            continue
        stripped = raw_line.strip()
        if not stripped or current is None:
            continue
        if stripped.startswith(("-", "*")):
            item = stripped[1:].strip()
            if item:
                sections[current].append(item)
        elif current in {"runtime_constraints", "validation_commands", "allowed_edit_scope", "must_preserve", "known_failure_modes", "proof_requirements"}:
            sections[current].append(stripped)
    return sections


def _extract_first_meaningful_line(text: str) -> str:
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if _normalize_heading(stripped) is not None:
            continue
        if stripped.startswith(("-", "*")):
            continue
        return stripped
    return "Complete the master prompt safely."


def _parse_goal_items(items: list[str], *, default_id: str, default_description: str, key: str) -> list[dict]:
    parsed: list[dict] = []
    pattern = re.compile(r"^(?P<id>[A-Z]\d{3})\s*:\s*(?P<description>.+)$")
    for item in items:
        match = pattern.match(item)
        if match:
            item_id = match.group("id")
            description = match.group("description").strip()
        else:
            item_id = default_id if not parsed else f"{key[0].upper()}{len(parsed)+1:03d}"
            description = item.strip()
        parsed.append({
            key: item_id,
            "description": description,
            "status": "PENDING",
        })
    if parsed:
        return parsed
    return [{
        key: default_id,
        "description": default_description,
        "status": "PENDING",
    }]


def _merge_unique(items: list[str], defaults: list[str]) -> list[str]:
    merged: list[str] = []
    for item in items + defaults:
        if item not in merged:
            merged.append(item)
    return merged


def normalize_master_prompt(ctx: TargetRepoContext) -> dict:
    if not ctx.paths.master_prompt.exists():
        raise FileNotFoundError(f"Missing master prompt: {ctx.paths.master_prompt}")
    identity = read_workflow_identity(ctx.root) or {}
    source_prompt = Path(identity["master_prompt_path"]) if identity.get("master_prompt_path") else ctx.paths.master_prompt
    frozen = freeze_master_prompt(
        repo_root=ctx.root,
        workflow_root=ctx.paths.workflow_dir,
        master_prompt_path=source_prompt,
        workflow_id=identity.get("workflow_id"),
        run_id=identity.get("run_id"),
    )
    text = ctx.paths.master_prompt.read_text(encoding="utf-8").strip()
    sections = _parse_prompt_sections(text)
    first_line = _extract_first_meaningful_line(text)
    planning_client = create_planning_model_client({})
    interpretation = None
    proof_obligations = None
    probe_plan = None
    provability = None
    try:
        goal_request = build_goal_interpretation_request(
            workflow_root=ctx.paths.workflow_dir,
            master_prompt_frozen=frozen,
            inventory_graph_path=ctx.paths.inventory_graph,
        )
        append_operator_event(
            ctx.root,
            event_type="goal_interpretation_model_requested",
            severity="info",
            stage="GOAL_SPEC_READY",
            summary="Goal interpretation model requested.",
            artifact_paths=[".codex-orchestrator/goal_interpretation/model_request.json"],
        )
        goal_output = run_planning_model(
            workflow_root=ctx.paths.workflow_dir,
            stage_dir_name="goal_interpretation",
            response_kind="goal_interpretation",
            request=goal_request,
            model_client=planning_client,
        )
        interpretation = normalize_goal_interpretation(model_output=goal_output, master_prompt_frozen=frozen)
        validate_goal_interpretation(interpretation, master_prompt_frozen=frozen)
        write_json(ctx.paths.workflow_dir / "goal_interpretation" / "goal_interpretation.json", interpretation)
        write_json(ctx.paths.workflow_dir / "goal_interpretation.json", interpretation)
        write_validation_result(ctx.paths.workflow_dir, "goal_interpretation", accepted=True, errors=[])
        append_operator_event(
            ctx.root,
            event_type="goal_interpretation_written",
            severity="info",
            stage="GOAL_SPEC_READY",
            summary=f"Goal interpretation written with status {interpretation['interpretation_status']}.",
            artifact_paths=[
                ".codex-orchestrator/goal_interpretation/goal_interpretation.json",
                ".codex-orchestrator/goal_interpretation/model_response.raw.json",
            ],
            details={
                "interpretation_status": interpretation["interpretation_status"],
                "goal_item_count": len(interpretation.get("goal_items", [])),
                "proof_not_claimed_here": True,
            },
        )
        provability = classify_goal_provability(
            master_prompt_frozen=frozen,
            goal_interpretation=interpretation,
            repo_census=None,
            capabilities={"local_execution": True},
        )
        write_provability_result(ctx.paths.workflow_dir, provability)
        append_operator_event(
            ctx.root,
            event_type="provability_classified",
            severity="info" if provability["can_start_product_patchlets"] else "warning",
            stage="PROVABILITY_ASSESSMENT",
            summary=f"provability classified: {provability['provability_status']}.",
            artifact_paths=[".codex-orchestrator/provability/provability_result.json"],
            details=provability,
        )
        if provability["can_start_product_patchlets"] is not True:
            raise PlanningModelError("goal interpretation is not provable")
        proof_request = build_proof_planning_request(
            master_prompt_frozen=frozen,
            goal_interpretation_path=".codex-orchestrator/goal_interpretation/goal_interpretation.json",
        )
        append_operator_event(
            ctx.root,
            event_type="proof_planning_model_requested",
            severity="info",
            stage="PROOF_PLANNING",
            summary="Proof planning model requested.",
            artifact_paths=[".codex-orchestrator/proof_planning/model_request.json"],
        )
        proof_output = run_planning_model(
            workflow_root=ctx.paths.workflow_dir,
            stage_dir_name="proof_planning",
            response_kind="proof_obligations",
            request=proof_request,
            model_client=planning_client,
        )
        proof_obligations = normalize_proof_obligations(
            master_prompt_frozen=frozen,
            goal_interpretation=interpretation,
            model_output=proof_output,
        )
        validate_proof_obligations(
            proof_obligations=proof_obligations,
            goal_interpretation=interpretation,
            master_prompt_frozen=frozen,
        )
        write_json(ctx.paths.workflow_dir / "proof_planning" / "proof_obligations.json", proof_obligations)
        write_json(ctx.paths.workflow_dir / "proof_obligations.json", proof_obligations)
        write_validation_result(ctx.paths.workflow_dir, "proof_planning", accepted=True, errors=[])
        append_operator_event(
            ctx.root,
            event_type="proof_obligations_written",
            severity="info",
            stage="PROOF_PLANNING",
            summary=f"Proof obligations written: {len(proof_obligations.get('obligations', []))} required.",
            artifact_paths=[
                ".codex-orchestrator/proof_planning/proof_obligations.json",
                ".codex-orchestrator/proof_planning/model_response.raw.json",
            ],
            details={"proof_obligation_count": len(proof_obligations.get("obligations", []))},
        )
        probe_request = build_probe_planning_request(
            master_prompt_frozen=frozen,
            proof_obligations_path=".codex-orchestrator/proof_planning/proof_obligations.json",
        )
        append_operator_event(
            ctx.root,
            event_type="probe_planning_model_requested",
            severity="info",
            stage="PROBE_PLANNING",
            summary="Probe planning model requested.",
            artifact_paths=[".codex-orchestrator/probe_planning/model_request.json"],
        )
        probe_output = run_planning_model(
            workflow_root=ctx.paths.workflow_dir,
            stage_dir_name="probe_planning",
            response_kind="probe_plan",
            request=probe_request,
            model_client=planning_client,
        )
        probe_plan = normalize_probe_plan(
            model_output=probe_output,
            proof_obligations=proof_obligations,
            master_prompt_frozen=frozen,
        )
        validate_probe_plan(proof_obligations=proof_obligations, probe_plan=probe_plan)
        probe_coverage = validate_probe_plan_for_required_obligations(proof_obligations=proof_obligations, probe_plan=probe_plan)
        write_json(ctx.paths.workflow_dir / "probe_planning" / "probe_plan.json", probe_plan)
        write_json(ctx.paths.workflow_dir / "probe_plan.json", probe_plan)
        write_validation_result(ctx.paths.workflow_dir, "probe_planning", accepted=True, errors=[])
        append_operator_event(
            ctx.root,
            event_type="probe_plan_written",
            severity="info",
            stage="PROBE_PLANNING",
            summary=f"Probe plan written: {len(probe_plan.get('probes', []))} probes.",
            artifact_paths=[
                ".codex-orchestrator/probe_planning/probe_plan.json",
                ".codex-orchestrator/probe_planning/model_response.raw.json",
            ],
            details=probe_coverage,
        )
        provability = classify_goal_provability(
            master_prompt_frozen=frozen,
            goal_interpretation=interpretation,
            proof_obligations=proof_obligations,
            repo_census=None,
            capabilities={"local_execution": True},
        )
        write_provability_result(ctx.paths.workflow_dir, provability)
    except (PlanningModelError, ValueError) as exc:
        for stage_dir in ["goal_interpretation", "proof_planning", "probe_planning"]:
            path = ctx.paths.workflow_dir / stage_dir / "validation_result.json"
            request_path = ctx.paths.workflow_dir / stage_dir / "model_request.json"
            if request_path.exists() and not path.exists():
                write_validation_result(ctx.paths.workflow_dir, stage_dir, accepted=False, errors=[str(exc)])
        if provability is None:
            provability = missing_goal_interpretation_provability(master_prompt_frozen=frozen, reason=str(exc))
            write_provability_result(ctx.paths.workflow_dir, provability)
        append_operator_event(
            ctx.root,
            event_type="goal_ambiguous" if provability["provability_status"] == "AMBIGUOUS" else "goal_not_provable",
            severity="warning",
            stage="PROVABILITY_ASSESSMENT",
            summary="workflow safe-failed before product patchlets.",
            artifact_paths=[
                ".codex-orchestrator/provability/provability_result.json",
                ".codex-orchestrator/provability/goal_not_provable_result.json",
            ],
            details={"failure_signature": "goal_ambiguous" if provability["provability_status"] == "AMBIGUOUS" else "goal_not_provable", "reason": str(exc)},
        )
    update_goal_progress(
        workflow_root=ctx.paths.workflow_dir,
        event_reason="normalize_master_prompt",
        workflow_iteration=load_state(ctx).current_loop_iteration,
        master_prompt_frozen=frozen,
        provability_result=provability,
        proof_obligations=proof_obligations,
        probe_plan=probe_plan,
    )
    upsert_prompt_index_entry(ctx.root, {
        "kind": "master_prompt",
        "stage": "GOAL_SPEC_READY",
        "title": "Master prompt",
        "summary": "Copied master prompt for this workflow.",
        "path": ctx.paths.master_prompt,
        "patchlet_id": None,
        "attempt_id": None,
        "model": None,
        "reasoning": None,
        "contracts": [],
        "artifact_paths": [
            ".codex-orchestrator/master_prompt_frozen.json",
            ".codex-orchestrator/goal_interpretation/model_request.json",
        ],
    })
    goal = {
        "schema_version": "1.0",
        "kind": "goal_spec",
        "master_goal": text,
        "master_prompt_sha256": frozen["sha256"],
        "master_prompt_frozen_path": ".codex-orchestrator/master_prompt_frozen.json",
        "success_goals": _parse_goal_items(
            sections["success_goals"],
            default_id="G001",
            default_description=first_line,
            key="goal_id",
        ),
        "target_invariants": _parse_goal_items(
            sections["target_invariants"],
            default_id="I001",
            default_description="Master goal behavior is proven across the affected runtime boundary.",
            key="invariant_id",
        ),
        "forbidden_actions": _merge_unique(sections["forbidden_actions"], [
            "Do not weaken tests.",
            "Do not edit more than one product/runtime file per patchlet.",
            "Do not rely on chat memory as durable state.",
        ]),
        "runtime_constraints": _merge_unique(sections["runtime_constraints"], [
            "Run all target-repository commands with the target repository as cwd.",
        ]),
        "validation_commands": sections["validation_commands"],
        "allowed_edit_scope": sections["allowed_edit_scope"],
        "must_preserve": _merge_unique(sections["must_preserve"], [
            "Durable workflow artifacts",
            "Existing repository behavior outside the target invariant",
        ]),
        "known_failure_modes": sections["known_failure_modes"],
        "proof_requirements": _merge_unique(sections["proof_requirements"], [
            "ROOT-CAUSE PROBE-ONLY INVESTIGATION",
            "durable probe artifacts",
            "no blind retry",
        ]),
    }
    write_json(ctx.paths.goal_spec, goal)
    state = load_state(ctx)
    transition(ctx, state, "GOAL_SPEC_READY", reason="normalized master prompt")
    return goal
