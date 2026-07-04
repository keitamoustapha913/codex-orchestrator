# Codex Orchestrator

Standalone installable `cxor` CLI for probe-gated root-cause Codex orchestration.

This repository contains the orchestrator source. Target repositories receive only durable workflow artifacts under `.codex-orchestrator/` and `.artifacts/probes/`.

## MVP implemented here

- installable package skeleton with `cxor` and `codex-orchestrator` entrypoints
- target repository resolver using `--repo` or current Git root discovery
- target artifact initialization
- atomic JSON writes and state validation
- deterministic census stage
- deterministic placeholder normalization/evidence/inventory/invariant/patchlet stages
- mock worker patchlet execution
- target-repo diff guard
- patchlet report validation
- global verification and autonomous mock loop to `DONE`

## Basic use

```bash
uv venv --python 3.10
. .venv/bin/activate
uv pip install -e ".[dev]"
cd /path/to/target-repo
cxor auto --master ./master_prompt.md --until DONE --worker-mode mock
```

## Reruns And Workflow Lifecycle

`cxor auto` writes `.codex-orchestrator/workflow_identity.json` with a
deterministic goal fingerprint from the target HEAD/tree, dirty status,
master prompt path and SHA-256, worker mode, worktree mode, and `--until`.
Rerun preflight writes `.codex-orchestrator/rerun_preflight_result.json`.

Same-goal terminal reruns return existing `DONE` explicitly. Changed prompts
or changed target state do not silently reuse old results. Use `--new-run`,
`--force-new-run`, `--resume`, and `--allow-dirty-target` to state intent.

Safe lifecycle commands:

```bash
cxor workflows --repo /path/to/target-repo
cxor archive --repo /path/to/target-repo
cxor reset --repo /path/to/target-repo --archive
```

`cxor auto --live-progress` is invocation-scoped and does not replay old
operator events. After `cxor apply-results --mode working-tree`, review and
commit the working-tree diff before starting a new goal. See
`docs/workflow_lifecycle.md`.

## Repair loop

Local development baseline: `uv + Python 3.10`.

Repair flow:
`failure -> classification -> repair plan -> apply repair -> regenerate patchlets -> verify`

No blind retry is allowed. Unauthorized diffs must be converted into a classified failure, a repair plan, a repair application, and repair patchlet regeneration before verification continues.

The repair replay commands are idempotent when the durable artifacts already exist and remain consistent:
`cxor apply-repair`, `cxor regenerate-patchlets`, and `cxor auto --resume --until DONE` can be rerun safely without creating duplicate repair artifacts.

After the workflow is `DONE`, `cxor apply-repair` and `cxor regenerate-patchlets` are terminal no-op commands. They report the no-op explicitly and do not rewrite state, patchlets, final verification, or product files.

```bash
cxor apply-repair --repo /path/to/target-repo
cxor regenerate-patchlets --repo /path/to/target-repo --from-repair-plan latest
cxor auto --repo /path/to/target-repo --resume --until DONE --worker-mode mock
```

## Durable probes and verification

Patchlet reports must carry `probe_artifact_refs` that point at durable probe artifacts under `.artifacts/probes/`.
Canonical patchlet reports require `probe_artifact_refs` entries to be objects,
not string-only paths. Raw real-Codex reports may contain string refs only
before report ingestion; safe refs under `.artifacts/probes/` are normalized
into canonical objects and unsafe refs fail with
`report_ingestion_result.json` plus `report_validation_errors.json`. See
`docs/report_contract.md` for the canonical object shape, valid and invalid
examples, `probe_artifact_refs_not_objects`, and the report-only repair policy.

The root-cause gate is explicit:
`ROOT-CAUSE PROBE-ONLY INVESTIGATION`

The global verifier does not allow `DONE` unless patchlet reports validate, transaction groups pass, invariants are proven, and unresolved failures are absent.

## Advanced repair and rediscovery

Advanced repair classifications currently include:

- `INSIDE_KNOWN_GRAPH`
- `OUTSIDE_KNOWN_GRAPH`
- `INVENTORY_CONTRADICTION`
- `REPEATED_REPAIR_FAILURE`
- `MASTER_GOAL_CHANGED`
- `EXCESSIVE_IMPACTED_SCOPE`

Rediscovery and rebuild commands:

```bash
cxor rediscover --repo /path/to/target-repo --scope impacted
cxor rediscover --repo /path/to/target-repo --scope full
cxor rebuild-inventory --repo /path/to/target-repo --scope impacted
```

## Worktree mode

Worktree mode is optional. It is not the default execution path.

Validated merge flow:

```bash
cxor run-next --repo /path/to/target-repo --worker-mode mock --use-worktree
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode mock --use-worktree
```

The target repo must be clean apart from volatile workflow artifacts before worktree execution starts.
Worktree execution writes reports, runs, and durable probe artifacts to the target repo artifact root, validates the worktree diff, validates the report, and only then applies a validated merge back to the target product/runtime file.
Unauthorized worktree diffs are isolated as failure evidence and do not mutate target product/runtime files.

No source is copied into the target repo beyond durable workflow artifacts and validated target-file edits.

## Opt-in real Codex smoke

Real Codex smoke is opt-in only. The default suite does not run real Codex and the smoke is not part of the default test suite.

Run it explicitly:

```bash
export UV_CACHE_DIR=/tmp/uv-cache
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py --run-real-codex -s
```

The smoke drives `cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode real_codex --use-worktree`.

Fake-success parity now proves the exact `worker_mode=real_codex` +
`auto --use-worktree` orchestrator wiring. A fake Codex binary can reach
`DONE` only by producing a valid report and durable probe artifacts that pass
the existing validators.

Real Codex success to DONE is not guaranteed. It still depends on actual Codex
output quality, including a valid report, valid `probe_artifact_refs`, and
durable probe artifacts. Do not weaken validators to make real Codex pass.

Operator rules:

- do not weaken validators to make real Codex pass;
- real Codex runs inside an isolated worktree and only validated diffs may merge back to the target repo;
- real Codex failure is acceptable only when it stays contained and preserves evidence;
- inspect `run_manifest.json` for the failed patchlet attempt entry;
- inspect `.codex-orchestrator/runs/`, `.codex-orchestrator/failures/`, and `.artifacts/probes/` after each smoke run;
- on safe failure, expect a `WORKER_FAILED` run-manifest entry plus preserved `stdout.txt`, `stderr.txt`, `command.json`, and `output.jsonl`;
- blind retry is not allowed.

Patchlet real-Codex execution uses a bounded 10 minutes / 600 seconds by
default. `CODEX_TIMEOUT_SECONDS` overrides the global timeout, and
`CODEX_PATCHLET_TIMEOUT_SECONDS` overrides the patchlet timeout specifically.
The Worker Capsule and generated subprompt include the hard timeout plus a soft
deadline of `timeout - 60` seconds. The subprocess receives
`CXOR_TIMEOUT_SECONDS` and `CXOR_SOFT_DEADLINE_SECONDS` and is instructed to
write `worker_stage/05_final_report.md` with a BLOCKED or FAILED status before
the hard timeout if it cannot complete.

Invalid timeout values such as non-integers, zero, or negative seconds fail as
structured precondition errors before Codex launches. The stable error text
includes the env var name, the bad value, and `expected positive integer seconds`.

Real-Codex liveness is written to
`.codex-orchestrator/runs/<attempt>/progress.jsonl`. This compact progress is
liveness, not success; timeout safe-failure is containment evidence, not task
success and not `DONE`.

`cxor diagnose-real-codex` classifies command evidence with `timed_out=true`
and `exit_code=124` as `orchestrator_subprocess_timeout`. That category means
the orchestrator killed the subprocess at the configured timeout; it is not
task success. If `progress.jsonl` exists, the diagnosis links it as evidence
that Codex was alive before timeout.

The explicit real-Codex smoke is an operator-run check and is not part of the
default test suite.

For repeatable operator evidence capture, prefer the runbook command:

```bash
uv run --no-sync cxor real-codex-smoke-runbook --dry-run
CODEX_PATCHLET_TIMEOUT_SECONDS=600 uv run --no-sync cxor real-codex-smoke-runbook --run-real-codex
```

The runbook writes `.operator-runs/real-codex-smoke/<timestamp>-real-codex-smoke/`
with `selected_policy.json`, `result.json`, `diagnosis_paths.json`,
`explicit_smoke_stdout.txt`, and `explicit_smoke_stderr.txt`. Dry-run mode does
not invoke real Codex. Explicit mode may consume account, network, model, token,
and wall-clock resources. `safe_failure is a successful runbook capture`, not
task DONE; `DONE means the orchestrator validators accepted the run`.

Validate a captured runbook bundle with:

```bash
cxor validate-real-codex-smoke-runbook --run-dir .operator-runs/real-codex-smoke/<timestamp>-real-codex-smoke
```

This command is read-only, does not run Codex, and does not run pytest. It
checks `real_codex_smoke_selected_policy.schema.json`,
`real_codex_smoke_operator_result.schema.json`,
`real_codex_smoke_diagnosis_paths.schema.json`,
`real_codex_smoke_runbook_validation.schema.json`, and required text evidence
files such as `environment.txt`, `default_skip_stdout.txt`, and
`explicit_smoke_stdout.txt`.

List local runbook bundles with:

```bash
cxor list-real-codex-smoke-runbooks
cxor list-real-codex-smoke-runbooks --json
cxor list-real-codex-smoke-runbooks --root .operator-runs/real-codex-smoke --latest
cxor list-real-codex-smoke-runbooks --only-invalid --limit 10
```

This command is read-only, does not run Codex, and does not run pytest. It
summarizes timestamp, outcome, validation status, selected model, reasoning,
timeout, timeout result, diagnosis category, `result.json`, and
`validation_result.json`. Invalid bundles are listed rather than hidden; use
`cxor validate-real-codex-smoke-runbook --run-dir <dir>` to inspect one bundle.

Export one validated bundle with:

```bash
cxor export-real-codex-smoke-runbook --run-dir .operator-runs/real-codex-smoke/<timestamp>-real-codex-smoke
```

The export command writes a zip archive under `.operator-runs/exports/` plus a
sidecar hash manifest. It is read-only for the source bundle, does not run
Codex, does not run pytest, uses relative archive paths, and refuses invalid
bundles unless `--force` is passed.

See `docs/runbooks/real_codex_smoke_runbook.md` for how to compare runs.

Final Markdown reports have their own wrapper gate contract. The marker must
be a standalone canonical line such as `FINAL_STATUS: PASS`,
`FINAL_STATUS: BLOCKED`, or `FINAL_STATUS: FAILED`. Non-canonical marker text
is rejected, including `Marker: `FINAL_STATUS: PASS``, markers wrapped in
backticks, markers inside sentences, and invalid values such as
`FINAL_STATUS: OK`. A valid report JSON alone does not bypass the wrapper gate.
These failures diagnose as `wrapper_gate_final_status_marker_error`;
`network_or_api_error` does not mask structured gate or routing failures.

Transaction group ids such as `TG001` are not patchlet ids. Transaction-group
failure records keep `source_type: transaction_group`, keep the TG source id,
and preserve member patchlet ids in `source_patchlet_ids`. Regeneration expands
those member patchlets before creating repair patchlets. If that mapping is
missing, the structured failure is `transaction_group_source_mapping_missing`,
not a lookup for a patchlet named `TG001`.

Patchlet Codex defaults to `gpt-5.4-mini` with `CODEX_REASONING=medium`.
Non-patchlet/orchestrator Codex profiles default to `gpt-5.5` with
`CODEX_REASONING=medium`. `CODEX_MODEL`/`CODEX_REASONING` override both when
specific patchlet or orchestrator variables are absent.

Operator prompt contract:

- `src/codex_orchestrator/prompt_templates/real_codex_patchlet_contract.md`

For the opt-in smoke, this contract is injected into the smoke prompt and the
generated subprompt artifact under `.codex-orchestrator/subprompts/` so the
real Codex subprocess sees the same path and payload rules that the fake-success
parity harness proved.

The contract includes a minimal valid report example written to
`CXOR_REPORT_PATH`, a durable probe tree rooted at `CXOR_PROBE_ROOT`, and
explicit instructions not to invent alternate paths or mutate any file other
than the allowed product/runtime file.

Real Codex failure diagnosis:

```bash
cxor diagnose-real-codex --repo /path/to/target-repo --attempt P0001_attempt1
```

This command is read-only for product/runtime files. It does not run Codex. It
reads preserved `stdout.txt`, `stderr.txt`, `output.jsonl`, `command.json`,
`run_manifest.json`, and the generated prompt artifact, then writes:

- generic artifact kinds: `real_codex_failure_diagnosis.json` and `real_codex_failure_diagnosis.md`
- `.codex-orchestrator/diagnostics/real_codex/P0001_attempt1_diagnosis.json`
- `.codex-orchestrator/diagnostics/real_codex/P0001_attempt1_diagnosis.md`

Use the diagnosis only as evidence review. Do not weaken validators. When the
artifacts do not support a more specific cause, expect the conservative category
`unknown_codex_nonzero_exit`.

For the smoke-specific operator guide, see `docs/real_codex_smoke.md`.

## Worker Capsule

Worker Capsule is a per-attempt evidence layer under
`.codex-orchestrator/runs/<attempt>/`.

It contains:

- `worker_capsule.json`
- `worker_memory/`
- `worker_stage/`
- `worker_hooks/events.jsonl`
- `gates/wrapper_gate_result.json`
- `diagnostics/`

Worker memory is context, not proof. Codex may read and write attempt-local
memory and stage files, but the orchestrator writes gate results and decides
whether the attempt is accepted.

Worker stage files must be written under `CXOR_WORKER_STAGE_DIR`, for example
`.codex-orchestrator/runs/P0001_attempt1/worker_stage/`. Do not create
target-root worker_stage/. If real Codex writes a top-level `worker_stage/`,
diagnosis reports `worker_capsule_path_violation`. This is a Codex
path-obedience issue, not orchestrator wiring failure. Do not weaken validators.

If real Codex exits successfully but writes an invalid patchlet report,
diagnosis reports `patchlet_report_schema_violation`. This is not a network
failure and is not a `network_or_api_error`; it means report validation
rejected the worker output.
Allowed report statuses are `COMPLETE`, `VERIFIED_NO_CHANGE_NEEDED`,
`BLOCKED_WITH_EVIDENCE`, and `FAILED_WITH_EVIDENCE`. `FIXED`, `DONE`,
`SUCCESS`, `PASSED`, and `OK` are unsupported and invalid. `cleanup_proof`
must be a string, not an object, and required fields such as
`changed_product_runtime_file`, `deterministic_run_counts`,
`before_after_state`, `row_ledger`, and `trace_ledger` must be present. Repair
patchlets receive a report skeleton and must follow the same contract.

product/runtime edits happen under `CXOR_EXECUTION_ROOT`. Product/runtime
files under `CXOR_TARGET_ROOT` are read-only to Codex workers; target-root
artifact directories remain writable only for evidence under
`.codex-orchestrator/` and `.artifacts/probes/`.

## Live Progress And Integration Results

Real-Codex patchlets can emit compact live progress lines such as
`[cxor:P0001_attempt1 +004s] codex: thread.started`. These lines are liveness
only. The durable progress truth remains
`.codex-orchestrator/runs/<attempt>/progress.jsonl`; live progress is not proof
of success and a `safe_failure` capture is not DONE. Set
`CXOR_LIVE_CODEX_PROGRESS=0` to disable terminal progress, or
`CXOR_LIVE_CODEX_PROGRESS_INTERVAL_SECONDS=15` to adjust throttling.

Accepted worktree patchlets advance an integration ref such as
`refs/cxor/runs/R0001/integration`. The target repo remains clean between
patchlets; accepted product/runtime changes are represented by the integration
SHA, and the next patchlet worktree starts from that integration SHA. Global
verification writes `.codex-orchestrator/integration/final_diff.patch` and
verifies the integration SHA before DONE.

Applying accepted results is explicit:

```bash
cxor apply-results --repo /path/to/target-repo --mode patch
cxor apply-results --repo /path/to/target-repo --mode branch
cxor apply-results --repo /path/to/target-repo --mode working-tree
```

`--mode patch` writes/refreshes the final diff and does not mutate product
files. `--mode branch` creates `cxor/results/<run_id>` without checking it out.
`--mode working-tree` requires a clean target and mutates product/runtime files
only because the operator explicitly requested it.

Integration artifacts are schema-validated. `integration_state.json` validates
against `integration_state.schema.json`, each `accepted_changes.jsonl` entry is
validated line-by-line against `accepted_change.schema.json`, checkpoints
validate against `integration_checkpoint.schema.json`, and apply-results files
such as `patch_result.json` validate against
`apply_results_result.schema.json`. Run the read-only validator with:

```bash
cxor validate-integration-artifacts --repo /path/to/target-repo
```

This command is read-only for product/runtime files and does not run Codex. It
supports the integration-ref safety model by checking the durable artifacts
that explain which accepted changes are represented by the integration SHA.

Useful read-only commands:

```bash
cxor inspect-capsule --repo /path/to/target-repo --attempt P0001_attempt1
cxor validate-capsule --repo /path/to/target-repo --attempt P0001_attempt1
cxor validate-integration-artifacts --repo /path/to/target-repo
cxor diagnose-real-codex --repo /path/to/target-repo --attempt P0001_attempt1
cxor verify-group --repo /path/to/target-repo TG001
cxor verify-global --repo /path/to/target-repo
```

Transaction verification now writes `patchlet_output_matrix.json` before the
group verdict, and global verification writes `verification_matrix.json` plus
`global_gate_result.json` before concluding `DONE`.

## CI-safe commands

```bash
export UV_CACHE_DIR=/tmp/uv-cache
uv run --no-sync pytest -q
uv run --no-sync cxor doctor --repo /path/to/target-repo
uv run --no-sync cxor validate-state --repo /path/to/target-repo
uv run --no-sync cxor verify-global --repo /path/to/target-repo
uv run --no-sync cxor auto --repo /path/to/target-repo --resume --until DONE --worker-mode ci_only
```

Release checklist: see `docs/release.md`. The normal command is
`cxor auto --repo <repo> --master <prompt> --until DONE`; mock mode is
deterministic and CI-safe; real Codex is opt-in only; the integration ref keeps
the target clean between patchlets; and apply-results is explicit finalization.

## P0004 Checkpoint Cleanliness

The integration checkpoint clean field remains strict:
`target_working_tree_clean_after_checkpoint` must be `true`. The implementation
now records a checkpoint cleanliness taxonomy instead of one opaque dirty flag:
`product_runtime_clean`, `artifact_dirs_ignored`, `cache_artifacts_detected`,
`cache_artifacts_removed`, `unknown_dirty_paths`, and
`whole_repo_clean_after_hygiene`.

Product/runtime clean means files such as `app.py` are not dirty in the target
root. Whole target clean means the target is clean after the allowed artifact
directories are accounted for and safe cache remediation has run.
`.codex-orchestrator/` and `.artifacts/` are durable evidence directories and
are ignored for checkpoint cleanliness. `__pycache__/`, `*.pyc`, and `*.pyo`
are not merely ignored silently: the Target Hygiene Gate records them in
`target_hygiene_gate_result.json`, hashes removable files, removes only known
untracked Python cache artifacts, and reports `cache_artifacts_detected` plus
`cache_artifacts_removed`. unknown dirty paths are not deleted and fail the
gate precisely; the structured field is `unknown_dirty_paths`.

Real-Codex worker environments set `PYTHONDONTWRITEBYTECODE=1`, and generated
worker instructions require `python -B` or `PYTHONDONTWRITEBYTECODE=1 python`
for probes that import target or execution code. Checkpoints include a
`target_cleanliness` summary and reference
`.codex-orchestrator/integration/checkpoints/<PATCHLET>_cleanliness.json`.

Run manifests now use attempt lifecycle entries so late failures keep current
attempt evidence: `ATTEMPT_STARTED`, `WORKER_EXITED`, `REPORT_VALIDATED`,
`WRAPPER_GATE_EVALUATED`, `TARGET_HYGIENE_EVALUATED`,
`INTEGRATION_CHECKPOINT_WRITTEN`, `INTEGRATION_ARTIFACTS_VALIDATED`,
`ATTEMPT_ACCEPTED`, and `ATTEMPT_FAILED_WITH_EVIDENCE`. Operator bundles record
runbook attempt consistency in `attempt_consistency`; mismatches are surfaced
by validation, listing, and export.

Structured diagnosis categories include
`integration_checkpoint_target_cleanliness_error`,
`integration_artifact_validation_error`, `run_manifest_attempt_lifecycle_error`,
`runbook_attempt_evidence_mismatch`, and `target_cache_artifact_leak`.
`network_or_api_error` requires actual external error evidence; prompt text or
normal metadata mentioning timeout, model, network, or API is not enough. After
every live run, use `validate-real-codex-smoke-runbook`,
`list-real-codex-smoke-runbooks`, and `export-real-codex-smoke-runbook`.

## Direct Auto Operator Visibility

Direct `cxor auto` supports `--live-progress`, `--no-live-progress`,
`--progress-interval-seconds`, and `--progress-format compact|jsonl`.
Compact progress prints concise stage-level operator events from
`.codex-orchestrator/operator_events.jsonl`; JSONL progress prints structured
events. Raw Codex JSON and full prompt bodies are not printed by default.

Prompt visibility is recorded in `.codex-orchestrator/prompt_index.json`.
Operators can use `cxor prompts --repo <repo>`, `cxor prompts --latest`, and
`cxor prompts --show PR000001 --lines 160` to inspect prompt metadata or
explicitly show a prompt body.

Use these read-only second-terminal commands while direct auto is running:

```bash
uv run --no-sync cxor monitor --repo /tmp/cxor-target --follow
uv run --no-sync cxor status --repo /tmp/cxor-target --watch
uv run --no-sync cxor prompts --repo /tmp/cxor-target --latest
```

`cxor status --json` reports active, silent_but_active, likely_stalled, done,
and failed classifications, plus current patchlet, current attempt, active
prompt path, last progress age, and next action. Repeated repair loops are
recorded in `.codex-orchestrator/loop_governor.json`; warning mode emits
`loop_governor_warning`, and explicit `--loop-governor-mode safe-fail
--max-repeated-failure-signature 3` safe-fails with evidence. Default tests do
not run real Codex.

## Semantic Goal Satisfaction

For structured goals, `DONE` requires independent semantic proof in addition
to report, wrapper, hygiene, integration, transaction, and global verifier
checks. The built-in Python main-return parser recognizes prompts such as
`Make app return ok and prove it.` and `Make app return me and prove it.`,
writes `.codex-orchestrator/semantic_goal_spec.json`, and verifies
`app.main()` against the requested value.

`VERIFIED_NO_CHANGE_NEEDED` is accepted only when the semantic goal runner
proves the criterion already passes. If the prompt requires `"me"` but
`app.main()` returns `"ok"`, the goal satisfaction gate records
`semantic_goal_unsatisfied` and the workflow does not reach `DONE`. See
`docs/semantic_goal_satisfaction.md`.

## General goal proof contract

cxor treats the master prompt as the read-only source of truth. Each workflow freezes `.codex-orchestrator/master_prompt.md`, records `.codex-orchestrator/master_prompt_frozen.json`, derives `goal_interpretation.json` without claiming proof, classifies `provability/provability_result.json` before product patchlets, and stops unsupported or ambiguous goals early with `goal_not_provable_result.json` evidence.

Required proof is represented in `proof_obligations.json` and `probe_plan.json`. Worker-proposed proof is not enough: required obligations need orchestrator-owned rerun or validation in `independent_probe_rerun_result.json`, then `goal_coverage_gate_result.json` must pass. The rc4 semantic app.main path is now the concrete `SGC001 -> GI001 -> PO001 -> GP001` fast path inside this general contract.

Final DONE requires `master_prompt_concordance_result.json` and `master_prompt_satisfaction_result.json` in addition to transaction groups, integration validation, target hygiene, and unresolved-failure checks. Partial proof is not full DONE unless explicitly allowed by policy. See `docs/general_goal_proof_contract.md`.

## Goal progress, stop, and partial apply

cxor writes `goal_progress.json` and append-only `goal_progress.jsonl`; `cxor goal-progress`, `cxor status --json`, `cxor monitor`, and `cxor auto --live-progress` expose the latest obligation counts, proof state, accepted checkpoint, and next action.

`cxor stop` writes `control/stop_requested.json`; the orchestrator stops at a safe point and writes `control/stop_result.json`. `apply-results --scope accepted --allow-partial` is required for stopped non-DONE workflows and applies only latest accepted progress. In-progress unaccepted worker changes are not applied by default. `partial_apply_result.json` records the warning that the full master prompt may not be satisfied. See `docs/goal_progress_and_partial_apply.md`.
