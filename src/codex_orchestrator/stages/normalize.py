from __future__ import annotations

from codex_orchestrator.jsonio import write_json
from codex_orchestrator.state import load_state, transition
from codex_orchestrator.target_repo import TargetRepoContext


def normalize_master_prompt(ctx: TargetRepoContext) -> dict:
    if not ctx.paths.master_prompt.exists():
        raise FileNotFoundError(f"Missing master prompt: {ctx.paths.master_prompt}")
    text = ctx.paths.master_prompt.read_text(encoding="utf-8").strip()
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), text[:120])
    goal = {
        "schema_version": "1.0",
        "kind": "goal_spec",
        "master_goal": text,
        "success_goals": [
            {
                "goal_id": "G001",
                "description": first_line or "Complete the master prompt.",
                "status": "PENDING",
            }
        ],
        "target_invariants": [
            {
                "invariant_id": "I001",
                "description": "Master goal behavior is proven across the affected runtime boundary.",
                "status": "PENDING",
            }
        ],
        "forbidden_actions": [
            "Do not weaken tests.",
            "Do not edit more than one product/runtime file per patchlet.",
            "Do not rely on chat memory as durable state.",
        ],
        "runtime_constraints": ["Run all target-repository commands with the target repository as cwd."],
        "validation_commands": [],
        "allowed_edit_scope": [],
        "must_preserve": ["Durable workflow artifacts", "Existing repository behavior outside the target invariant"],
        "known_failure_modes": [],
        "proof_requirements": [
            "Use root-cause probe-gated investigation before implementation.",
            "Write durable probe/report artifacts.",
            "Prove complete or verified-no-change-needed with direct evidence.",
        ],
    }
    write_json(ctx.paths.goal_spec, goal)
    state = load_state(ctx)
    transition(ctx, state, "GOAL_SPEC_READY", reason="normalized master prompt")
    return goal
