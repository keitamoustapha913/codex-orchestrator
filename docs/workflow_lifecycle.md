# Workflow Lifecycle, Reruns, And Reset

`cxor auto` records a durable workflow identity in
`.codex-orchestrator/workflow_identity.json`. The identity includes the target
HEAD and tree, target dirty status at workflow start, master prompt path,
master prompt SHA-256, worker mode, worktree mode, requested `--until`, and a
deterministic goal fingerprint.

Reruns are explicit:

- same goal fingerprint and terminal `DONE`: `cxor auto` returns existing DONE
  with an explicit message;
- changed prompt path or prompt content: `cxor auto` refuses unless the
  operator requests `--new-run` or `--force-new-run`;
- dirty target product/runtime files: `cxor auto` refuses unless
  `--allow-dirty-target` is passed, and the dirty status is recorded in
  workflow identity and rerun preflight evidence;
- active workflows resume only when the requested fingerprint matches, or when
  `--resume` is compatible with the same workflow.

Before each `auto` run, cxor writes
`.codex-orchestrator/rerun_preflight_result.json` with the existing and
requested goal fingerprints, changed fields, the decision, reasons, and
recommended commands.

New workflow controls:

```bash
cxor auto --repo <repo> --master <prompt> --new-run
cxor auto --repo <repo> --master <prompt> --force-new-run
cxor auto --repo <repo> --master <prompt> --allow-dirty-target
cxor archive --repo <repo>
cxor reset --repo <repo> --archive
cxor workflows --repo <repo>
cxor workflows --repo <repo> --json
```

Archive preserves evidence under `.codex-orchestrator/archives/`. Reset with
`--archive` archives first and clears active workflow state. Hard delete
requires `--hard-delete-artifacts` and refuses dirty product/runtime files.

Live progress is invocation-scoped. Each `cxor auto --live-progress` creates
`.codex-orchestrator/invocations/INV*.json` with the event cursor at start.
The progress stream prints only events after that cursor, so old
`operator_events.jsonl` lines are not replayed as if they belong to the current
command.

`cxor status --json` reports workflow identity, goal fingerprint, prompt hash,
target state at start, current dirty status, latest rerun preflight, and latest
apply-results guidance. `cxor monitor`, `cxor prompts`, and `cxor status`
accept `--workflow` filters.

After `cxor apply-results --mode working-tree`, inspect the working tree and
commit the applied product/runtime diff before starting a new goal. The latest
apply result is also written to
`.codex-orchestrator/apply_results/latest_apply_result.json` with rerun
guidance.

## Semantic Goal Satisfaction

Workflow identity links to the frozen master prompt and the model-mediated
planning artifacts. No app.py-specific, app.main-specific, Python-specific, or
smoke-prompt regex parser is supported as the general architecture.

`VERIFIED_NO_CHANGE_NEEDED` requires independent proof. `DONE` requires goal
coverage, master-prompt concordance, and master-prompt satisfaction. Ambiguous,
unsupported, contradictory, or unprovable goals safe-fail before product
patchlets.

## General goal proof contract

cxor treats the master prompt as the read-only source of truth. Each workflow freezes `.codex-orchestrator/master_prompt.md`, records `.codex-orchestrator/master_prompt_frozen.json`, derives `goal_interpretation.json` without claiming proof, classifies `provability/provability_result.json` before product patchlets, and stops unsupported or ambiguous goals early with `goal_not_provable_result.json` evidence.

Required proof is represented in `proof_obligations.json` and `probe_plan.json`. Worker-proposed proof is not enough: required obligations need orchestrator-owned rerun or validation in `independent_probe_rerun_result.json`, then `goal_coverage_gate_result.json` must pass. There is no compatibility fast path for app.py, app.main, Python-specific prompts, or smoke regexes.

Final DONE requires `master_prompt_concordance_result.json` and `master_prompt_satisfaction_result.json` in addition to transaction groups, integration validation, target hygiene, and unresolved-failure checks. Partial proof is not full DONE unless explicitly allowed by policy. See `docs/general_goal_proof_contract.md`.

## Goal progress, stop, and partial apply

cxor writes `goal_progress.json` and append-only `goal_progress.jsonl`; `cxor goal-progress`, `cxor status --json`, `cxor monitor`, and `cxor auto --live-progress` expose the latest obligation counts, proof state, accepted checkpoint, and next action.

`cxor stop --after-current-attempt` writes `control/stop_requested.json`; the
orchestrator honors it at the between-patchlet safe point after the current
attempt reaches a terminal state. It writes `control/stop_result.json`, records
the latest accepted checkpoint, and the next patchlet does not start after the
stop is honored. `apply-results --scope accepted --allow-partial` is required
for stopped non-DONE workflows and applies only latest accepted progress.
Pending and unaccepted worker changes are not applied. If there is no accepted
checkpoint, `stop_result.json` records `applyable_progress=false`.
`partial_apply_result.json` records the warning that the full master prompt may
not be satisfied. See `docs/goal_progress_and_partial_apply.md`.

## Decomposition Lifecycle

After inventory and proof analysis, cxor writes decomposition artifacts under `.codex-orchestrator/decomposition/`. Patchlet compilation reads `patchlet_plan.json` when present and preserves legacy invariant fields for verification compatibility. Transaction groups derive from dependency layers and proof-obligation coverage. See `docs/multi_patchlet_transaction_graph.md`.

Before worker execution, the workflow records whether candidate files have
positive planning evidence. An unmatched candidate receives no work and is not
assigned every goal or proof obligation by fallback. Support files remain
targetable when explicitly linked by planning evidence, but untargeted support
or verification files stay out of patchlet work.

Each accepted decomposition slice carries one goal, one proof obligation, and
one probe unless a legitimate obligation has additional explicit probes.
Multiple patchlets may target one file. Unresolved, ambiguous, or missing-probe
mappings are safe pre-worker stop conditions.
