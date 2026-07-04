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

Workflow identity links to semantic goal metadata when the master prompt can
be compiled into structured criteria. The semantic goal fingerprint changes
when the parsed expected value changes, for example from `"ok"` to `"me"`.

Structured semantic goals are persisted in
`.codex-orchestrator/semantic_goal_spec.json`. The Python main-return built-in
parser recognizes prompts such as `Make app return ok and prove it.` and
`Make app return me and prove it.`.

`VERIFIED_NO_CHANGE_NEEDED` requires independent goal proof. `DONE` requires
semantic pass for structured goals. Unsupported goals are visible as
unsupported and are not labeled as semantically proven.

## General goal proof contract

cxor treats the master prompt as the read-only source of truth. Each workflow freezes `.codex-orchestrator/master_prompt.md`, records `.codex-orchestrator/master_prompt_frozen.json`, derives `goal_interpretation.json` without claiming proof, classifies `provability/provability_result.json` before product patchlets, and stops unsupported or ambiguous goals early with `goal_not_provable_result.json` evidence.

Required proof is represented in `proof_obligations.json` and `probe_plan.json`. Worker-proposed proof is not enough: required obligations need orchestrator-owned rerun or validation in `independent_probe_rerun_result.json`, then `goal_coverage_gate_result.json` must pass. The rc4 semantic app.main path is now the concrete `SGC001 -> GI001 -> PO001 -> GP001` fast path inside this general contract.

Final DONE requires `master_prompt_concordance_result.json` and `master_prompt_satisfaction_result.json` in addition to transaction groups, integration validation, target hygiene, and unresolved-failure checks. Partial proof is not full DONE unless explicitly allowed by policy. See `docs/general_goal_proof_contract.md`.

## Goal progress, stop, and partial apply

cxor writes `goal_progress.json` and append-only `goal_progress.jsonl`; `cxor goal-progress`, `cxor status --json`, `cxor monitor`, and `cxor auto --live-progress` expose the latest obligation counts, proof state, accepted checkpoint, and next action.

`cxor stop` writes `control/stop_requested.json`; the orchestrator stops at a safe point and writes `control/stop_result.json`. `apply-results --scope accepted --allow-partial` is required for stopped non-DONE workflows and applies only latest accepted progress. In-progress unaccepted worker changes are not applied by default. `partial_apply_result.json` records the warning that the full master prompt may not be satisfied. See `docs/goal_progress_and_partial_apply.md`.
