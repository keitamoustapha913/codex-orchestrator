from __future__ import annotations

import re

from codex_orchestrator.jsonio import write_json
from codex_orchestrator.prompt_index import upsert_prompt_index_entry
from codex_orchestrator.operator_events import append_operator_event
from codex_orchestrator.semantic_goals import compile_semantic_goal_spec, semantic_goal_summary
from codex_orchestrator.state import load_state, sha256_file, transition
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
    text = ctx.paths.master_prompt.read_text(encoding="utf-8").strip()
    sections = _parse_prompt_sections(text)
    first_line = _extract_first_meaningful_line(text)
    prompt_sha = sha256_file(ctx.paths.master_prompt)
    identity = read_workflow_identity(ctx.root) or {}
    semantic_spec = compile_semantic_goal_spec(
        master_prompt_text=text,
        master_prompt_path=ctx.paths.master_prompt,
        master_prompt_sha256=prompt_sha,
        workflow_id=identity.get("workflow_id"),
        run_id=identity.get("run_id"),
    )
    semantic_spec_path = ctx.paths.workflow_dir / "semantic_goal_spec.json"
    write_json(semantic_spec_path, semantic_spec)
    semantic_summary = semantic_goal_summary(semantic_spec)
    if identity:
        identity.update(semantic_summary)
        write_workflow_identity(ctx, identity)
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
        "artifact_paths": [".codex-orchestrator/semantic_goal_spec.json"],
        **semantic_summary,
    })
    append_operator_event(
        ctx.root,
        event_type="semantic_goal_spec_created",
        severity="info" if semantic_spec["semantic_mode"] == "structured" else "warning",
        stage="GOAL_SPEC_READY",
        summary=(
            f"Semantic goal spec created with {len(semantic_spec.get('criteria', []))} structured criteria."
            if semantic_spec["semantic_mode"] == "structured"
            else "Semantic goal verification is unsupported for this prompt."
        ),
        artifact_paths=[".codex-orchestrator/semantic_goal_spec.json"],
        details={
            "semantic_mode": semantic_spec["semantic_mode"],
            "semantic_status": semantic_spec["semantic_status"],
            "semantic_criteria_count": len(semantic_spec.get("criteria", [])),
        },
    )
    goal = {
        "schema_version": "1.0",
        "kind": "goal_spec",
        "master_goal": text,
        "master_prompt_sha256": prompt_sha,
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
        **semantic_summary,
    }
    write_json(ctx.paths.goal_spec, goal)
    state = load_state(ctx)
    transition(ctx, state, "GOAL_SPEC_READY", reason="normalized master prompt")
    return goal
