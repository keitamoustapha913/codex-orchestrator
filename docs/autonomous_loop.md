# Autonomous Loop

Local baseline: `uv + Python 3.10`.

Primary autonomous command:

```bash
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode mock
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode mock --use-worktree
```

Before running stages, `cxor auto` performs rerun preflight. It compares the
requested workflow identity and goal fingerprint with any existing terminal or
active workflow. Same-goal DONE returns explicitly; changed prompt path,
changed prompt content, and dirty product/runtime target state are refused by
default. Use `--resume`, `--new-run`, `--force-new-run`, or
`--allow-dirty-target` to state intent. Use `cxor archive`,
`cxor reset --archive`, and `cxor workflows` instead of manually deleting
`.codex-orchestrator/`.

The autonomous loop is probe-gated and evidence-bound:

`normalize -> census -> classify-evidence -> build-inventory -> extract-invariants -> compile-patchlets -> run patchlets -> transaction groups -> verify-global -> DONE`

If failures occur, the loop routes through:

`failure -> classification -> repair plan -> apply repair -> regenerate patchlets -> verify`

For advanced cases it can also route through:

`PARTIAL_REDISCOVERY_REQUIRED`
`FULL_REDISCOVERY_REQUIRED`
`INVENTORY_REBUILD_REQUIRED`

No blind retry is allowed.

Report-contract failures are handled before wrapper-gate acceptance. Raw
real-Codex reports are preserved, safe `.artifacts/probes/` string refs are
normalized at ingress into canonical object-shaped `probe_artifact_refs`, and
unsafe refs fail with structured `report_validation_errors.json` evidence.
Report-shape-only failures use report-only repair policy when possible and do
not imply product/runtime failure. Full patchlet repair is still used for true
product failures, worker timeouts, target hygiene failures, or invalid probe
evidence. See `docs/report_contract.md`.

`ci_only` mode is read-only and intended for CI-safe resume and verification flows:

```bash
cxor auto --repo /path/to/target-repo --resume --until DONE --worker-mode ci_only
```

`--use-worktree` is optional, not default. When enabled for patchlet-executing worker modes, the target repo must be clean apart from volatile workflow artifacts before worktree execution starts.

Opt-in real Codex smoke command:

```bash
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py --run-real-codex -s
```

This command is not part of the default test suite. It runs the autonomous loop with `--worker-mode real_codex --use-worktree`. Do not weaken validators to make real Codex pass. Inspect `.codex-orchestrator/runs/`, `.codex-orchestrator/failures/`, and `.artifacts/probes/` to review contained success or failure evidence.

Fake-success parity now proves that this exact `worker_mode=real_codex` +
`auto --use-worktree` path can reach `DONE` when the subprocess produces a
valid report and durable probe artifacts. Real Codex success to DONE is still
not guaranteed, because real Codex must still produce output that satisfies the
existing validators.

Safe failures are expected to leave a `run_manifest.json` entry with status `WORKER_FAILED` and preserved `stdout.txt`, `stderr.txt`, `command.json`, and `output.jsonl` paths for the failed patchlet attempt. Blind retry is not allowed.

Real-Codex patchlets are bounded by a default 10 minutes / 600 seconds timeout.
`CODEX_TIMEOUT_SECONDS` overrides the global timeout, and
`CODEX_PATCHLET_TIMEOUT_SECONDS` overrides patchlet execution specifically.
Generated Worker Capsule files and subprompts include the hard timeout, the
soft deadline, and instructions to write `worker_stage/05_final_report.md`
with BLOCKED or FAILED status before timeout if the task cannot complete.

Invalid timeout env values fail structurally before Codex launches.
`CODEX_TIMEOUT_SECONDS`, `CODEX_PATCHLET_TIMEOUT_SECONDS`, and
`CODEX_PROGRESS_INTERVAL_SECONDS` must be positive integer seconds. Invalid
messages include the env var name, bad value, and `expected positive integer
seconds`.

`progress.jsonl` is written under each real-Codex attempt run directory as
small liveness evidence. Progress is not success evidence. Timeout
safe-failure is not task success and not `DONE`; it only proves containment and
artifact preservation.

Diagnosis has a dedicated `orchestrator_subprocess_timeout` category for
`command.json` or run-manifest evidence where `timed_out=true` and
`exit_code=124`. This category takes precedence over generic timeout text in
stderr/output, is not task success, and links `progress.jsonl` when present.

Explicit real-Codex smoke remains an operator-run check and is not part of the
default test suite.

Patchlet Codex defaults to `gpt-5.4-mini` with reasoning `medium`.
Non-patchlet/orchestrator Codex profiles default to `gpt-5.5` with reasoning
`medium`.

Operator prompt contract:

- `src/codex_orchestrator/prompt_templates/real_codex_patchlet_contract.md`

For the opt-in real Codex smoke, the orchestrator injects this contract into
the generated subprompt artifact under `.codex-orchestrator/subprompts/`. That
artifact is the exact prompt context to inspect after a safe failure.

The contract contains a minimal valid report example for `CXOR_REPORT_PATH`, a
minimal durable probe example for `CXOR_PROBE_ROOT`, and explicit instructions
that real success is not guaranteed unless Codex obeys the contract without the
validators being weakened.

If the opt-in smoke fails safely, run:

```bash
cxor diagnose-real-codex --repo /path/to/target-repo --attempt P0001_attempt1
```

This produces:

- generic artifact kinds: `real_codex_failure_diagnosis.json` and `real_codex_failure_diagnosis.md`
- `.codex-orchestrator/diagnostics/real_codex/P0001_attempt1_diagnosis.json`
- `.codex-orchestrator/diagnostics/real_codex/P0001_attempt1_diagnosis.md`

The diagnosis is evidence-bound. It reads `stdout.txt`, `stderr.txt`,
`output.jsonl`, `command.json`, `run_manifest.json`, and the generated prompt
artifact. It does not run Codex and does not weaken validators. If the
artifacts are insufficient, expect `unknown_codex_nonzero_exit`.

The same attempt-local evidence layer is visible through:

```bash
cxor inspect-capsule --repo /path/to/target-repo --attempt P0001_attempt1
cxor validate-capsule --repo /path/to/target-repo --attempt P0001_attempt1
```

Worker Capsule is now part of each patchlet attempt. It is per-attempt memory,
not global memory. The capsule lives under
`.codex-orchestrator/runs/<attempt>/` and includes worker memory, worker stage
templates, lifecycle events, gates, and diagnostics.

Memory is context, not proof. Codex can write memory and stage notes, but the
orchestrator writes gate results. `gates/wrapper_gate_result.json` is the
machine verdict for the attempt. A Codex `FINAL_STATUS` claim is evidence only;
it is not sufficient proof by itself.

Global `DONE` is now backed by transaction and global matrices:

- transaction groups write `patchlet_output_matrix.json`
- global verification writes `verification_matrix.json`
- global verification writes `global_gate_result.json`

## Live Progress And Accepted Changes

Long real-Codex subprocesses can emit compact live progress such as
`[cxor:P0001_attempt1 +004s] codex: thread.started`. The durable record remains
`progress.jsonl`; live progress is liveness only and safe failure is not DONE.
Set `CXOR_LIVE_CODEX_PROGRESS=0` to disable terminal progress.

Accepted changes advance `refs/cxor/runs/<run_id>/integration`. The target repo
remains clean between patchlets, each new worktree starts from the integration
SHA, and DONE is verified against the integration SHA plus
`.codex-orchestrator/integration/final_diff.patch`. Operators finalize results
explicitly with `cxor apply-results --mode patch`, `cxor apply-results --mode
branch`, or `cxor apply-results --mode working-tree`.

Schema validation now covers the integration-ref artifacts. The validator checks
`integration_state.json` with `integration_state.schema.json`,
`accepted_changes.jsonl` line-by-line with `accepted_change.schema.json`,
checkpoints with `integration_checkpoint.schema.json`, and apply-results files
such as `patch_result.json` with `apply_results_result.schema.json`.

```bash
cxor validate-integration-artifacts --repo /path/to/target-repo
```

This command is read-only, does not run Codex, and reinforces that DONE is
based on validated integration-state evidence rather than a dirty target
working tree.

## Direct Auto Operator Visibility And Loop Control

Direct `cxor auto` supports concise progress with `--live-progress`, quiet mode
with `--no-live-progress`, heartbeat tuning with `--progress-interval-seconds`,
and structured output with `--progress-format jsonl`.

```bash
CODEX_PATCHLET_TIMEOUT_SECONDS=600 \
uv run --no-sync cxor auto \
  --repo /tmp/cxor-target \
  --master /tmp/cxor-target/master_prompt.md \
  --until DONE \
  --worker-mode real_codex \
  --use-worktree \
  --live-progress
```

Progress comes from `.codex-orchestrator/operator_events.jsonl`; it is compact
and does not print raw Codex JSON or prompt bodies. Prompt metadata is indexed
in `.codex-orchestrator/prompt_index.json`; show prompt bodies only with:

```bash
uv run --no-sync cxor prompts --repo /tmp/cxor-target --show PR000001 --lines 160
```

Second-terminal read-only commands:

```bash
uv run --no-sync cxor monitor --repo /tmp/cxor-target --follow
uv run --no-sync cxor status --repo /tmp/cxor-target --watch
uv run --no-sync cxor prompts --repo /tmp/cxor-target --latest
```

`cxor status --json` reports active, silent_but_active, likely_stalled, done,
and failed classifications. Repeated repair loops are visible in
`.codex-orchestrator/loop_governor.json`; warning mode emits
`loop_governor_warning`, while `--loop-governor-mode safe-fail
--max-repeated-failure-signature 3` safe-fails with evidence. Default tests do
not run real Codex.

## Semantic Goal Satisfaction

When the master prompt compiles into a structured semantic goal, the loop also
writes `.codex-orchestrator/semantic_goal_spec.json` and requires independent
semantic goal satisfaction. For the built-in Python family, `Make app return
me and prove it.` means `app.main()` must return `"me"`. A probe or report
that only proves `"ok"` does not satisfy that goal.

`VERIFIED_NO_CHANGE_NEEDED` requires independent semantic proof that no change
is needed. Final `DONE` requires semantic pass for structured goals.
Unsupported natural-language goals are recorded as unsupported rather than
semantically proven.

## General goal proof contract

cxor treats the master prompt as the read-only source of truth. Each workflow freezes `.codex-orchestrator/master_prompt.md`, records `.codex-orchestrator/master_prompt_frozen.json`, derives `goal_interpretation.json` without claiming proof, classifies `provability/provability_result.json` before product patchlets, and stops unsupported or ambiguous goals early with `goal_not_provable_result.json` evidence.

Required proof is represented in `proof_obligations.json` and `probe_plan.json`. Worker-proposed proof is not enough: required obligations need orchestrator-owned rerun or validation in `independent_probe_rerun_result.json`, then `goal_coverage_gate_result.json` must pass. The rc4 semantic app.main path is now the concrete `SGC001 -> GI001 -> PO001 -> GP001` fast path inside this general contract.

Final DONE requires `master_prompt_concordance_result.json` and `master_prompt_satisfaction_result.json` in addition to transaction groups, integration validation, target hygiene, and unresolved-failure checks. Partial proof is not full DONE unless explicitly allowed by policy. See `docs/general_goal_proof_contract.md`.

## Goal progress, stop, and partial apply

cxor writes `goal_progress.json` and append-only `goal_progress.jsonl`; `cxor goal-progress`, `cxor status --json`, `cxor monitor`, and `cxor auto --live-progress` expose the latest obligation counts, proof state, accepted checkpoint, and next action.

`cxor stop` writes `control/stop_requested.json`; the orchestrator stops at a safe point and writes `control/stop_result.json`. `apply-results --scope accepted --allow-partial` is required for stopped non-DONE workflows and applies only latest accepted progress. In-progress unaccepted worker changes are not applied by default. `partial_apply_result.json` records the warning that the full master prompt may not be satisfied. See `docs/goal_progress_and_partial_apply.md`.

## General Work Decomposition

The autonomous loop now plans work slices before compiling patchlets. This is not one file -> one patchlet; each patchlet has exactly one allowed product/runtime file, while multiple patchlets may target the same file. `CODEX_PATCHLET_TIMEOUT_SECONDS` defaults to 600 seconds and is propagated into the plan, prompt, worker memory, and run records. See `docs/general_work_decomposition.md`.
