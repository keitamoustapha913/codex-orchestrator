# General Goal Proof Contract

The master prompt is the read-only source of truth for a workflow. At workflow start, cxor writes `.codex-orchestrator/master_prompt.md` as the frozen copy and `.codex-orchestrator/master_prompt_frozen.json` as the audit record containing the source path, frozen copy path, hash, size, workflow identity, and source spans.

`goal_interpretation.json` records what cxor believes the frozen master prompt asks for. It references `master_prompt_sha256` and source spans, but it is not proof; `proof_not_claimed_here` is always true.

Before product patchlets start, cxor writes `provability/provability_result.json`. Unsupported or ambiguous goals write `goal_not_provable_result.json` and stop before workers or product edits. If late unprovability is discovered, the defect signature is `late_goal_unprovable_discovered`.

`proof_obligations.json` states what must be proven. Required obligations reference goal items and master prompt source spans. `probe_plan.json` maps obligations to rerunnable probes. Worker proposed proof can inform the plan, but worker proof alone is not accepted.

`independent_probe_rerun_result.json` is the orchestrator-owned rerun evidence. For the rc4 app.main fast path, `SGC001` maps to `GI001`, `PO001`, and `GP001`, and the semantic runner records expected/actual results with stdout/stderr.

`goal_coverage_gate_result.json` decides whether required obligations are covered by orchestrator-rerun evidence. `VERIFIED_NO_CHANGE_NEEDED` and `COMPLETE` both require coverage pass. Partial coverage may be recorded but is not full DONE unless policy explicitly allows partial completion.

Global verification writes `master_prompt_concordance_result.json` and `master_prompt_satisfaction_result.json`. DONE requires master prompt concordance, master prompt satisfaction, proven required obligations, transaction groups, integration artifact validation, target hygiene, and no unresolved failures.

Unsupported or ambiguous goals are not marked proven. They stop early with `goal_not_provable`, `goal_ambiguous`, `goal_blocked_by_missing_capability`, `goal_coverage_failed`, `independent_probe_rerun_failed`, `proof_obligation_failed`, `master_prompt_concordance_failed`, or `master_prompt_not_satisfied` diagnostics instead of collapsing to unknown.
