# General Goal Proof Contract

The master prompt is the read-only source of truth for a workflow. At workflow start, cxor writes `.codex-orchestrator/master_prompt.md` as the frozen copy and `.codex-orchestrator/master_prompt_frozen.json` as the audit record containing the source path, frozen copy path, hash, size, workflow identity, and source spans.

`goal_interpretation.json` records what cxor believes the frozen master prompt asks for. It references `master_prompt_sha256` and source spans, but it is not proof; `proof_not_claimed_here` is always true.

Before product patchlets start, cxor writes `provability/provability_result.json`. Unsupported or ambiguous goals write `goal_not_provable_result.json` and stop before workers or product edits. If late unprovability is discovered, the defect signature is `late_goal_unprovable_discovered`.

`proof_obligations.json` states what must be proven. Required obligations reference goal items and master prompt source spans. `probe_plan.json` maps obligations to rerunnable probes. Worker proposed proof can inform the plan, but worker proof alone is not accepted.

`independent_probe_rerun_result.json` is the orchestrator-owned rerun evidence. For the rc4 app.main fast path, `SGC001` maps to `GI001`, `PO001`, and `GP001`, and the semantic runner records expected/actual results with stdout/stderr.

`goal_coverage_gate_result.json` decides whether required obligations are covered by orchestrator-rerun evidence. `VERIFIED_NO_CHANGE_NEEDED` and `COMPLETE` both require coverage pass. Partial coverage may be recorded but is not full DONE unless policy explicitly allows partial completion.

Global verification writes `master_prompt_concordance_result.json` and `master_prompt_satisfaction_result.json`. DONE requires master prompt concordance, master prompt satisfaction, proven required obligations, transaction groups, integration artifact validation, target hygiene, and no unresolved failures.

Durable object-shaped `probe_artifact_refs` are canonicalized from actual
artifact files before report validation. Worker-provided hashes are not
trusted, worker-provided sizes are not trusted, and raw worker metadata is
preserved for audit. Unsafe paths, missing files, patchlet mismatches, and
product files remain rejected before independent proof or goal coverage.

Unsupported or ambiguous goals are not marked proven. They stop early with `goal_not_provable`, `goal_ambiguous`, `goal_blocked_by_missing_capability`, `goal_coverage_failed`, `independent_probe_rerun_failed`, `proof_obligation_failed`, `master_prompt_concordance_failed`, or `master_prompt_not_satisfied` diagnostics instead of collapsing to unknown.

## Decomposition Proof Mapping

General work decomposition maps work slices and patchlets to proof obligations and goal items. The proof gate remains required for DONE: a patchlet contribution is not enough until the orchestrator-owned independent rerun and goal coverage gate prove the required obligation. See `docs/general_work_decomposition.md`.

## RC6 Patchlet-Scoped Proof

patchlet-scoped proof runs only selected current obligations for the active work slice. Future obligations remain unproven, not failed, until their patchlets run. PARTIAL progress accepts patchlet progress but blocks DONE; workflow-level DONE still requires all required proof obligations and master-prompt satisfaction. one allowed file per patchlet is necessary but not sufficient, so same-file proof must also respect the slice-level allowed-change boundary and reject future slice changes.

## RC6B Semantic Result Normalization

Real Codex may emit shorthand `semantic_goal_results` such as
`{"goal_item_id": "GI001", "result": "status updated from pending to ready-no-compat"}`.
The orchestrator accepts that shape only as a raw worker semantic claim, never
as proof. The raw worker output is preserved and linked to the current
patchlet goal item, proof obligation, slice boundary, and probe plan.

Worker claims are not proof. Vague shorthand such as `done`, `ok`, `looks
good`, `complete`, `seems fine`, or `probably passes` is rejected. Shorthand
that claims future slices or final master-prompt satisfaction is rejected.

Canonical `passed=true` or `passed=false` semantic results are created only
after the orchestrator-owned independent probe rerun. DONE still requires all
required obligations and master-prompt satisfaction.

Boundary evidence matching is role-aware. Short tokens such as `on`, `off`,
`no`, or `yes` do not match as substrings inside unrelated words like
`boundary`, `control`, or `now`. Future-slice rejection requires a role-aware
future boundary evidence combination, such as an exact line `event_logging=on`
or matching future key and value. Same-file mention alone is not a future
claim. Worker text is not proof; independent proof remains required.

## Decomposition Linkage

Goal and proof planning are consumed by decomposition as structured linkage
evidence. For a bounded slice, the expected shape is one goal, one proof
obligation, and one probe, with the current file and boundary carried into the
patchlet plan. Multiple patchlets may target one file when several obligations
share the same product file.

Positive planning evidence is required before a file receives work. An
unmatched candidate receives no work, and unresolved or ambiguous mappings are
treated as safe pre-worker failures rather than broad fallbacks.
