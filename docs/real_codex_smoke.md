# Real Codex Smoke

The real Codex smoke is opt-in only. The default suite does not run real Codex.

Run it with:

```bash
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py --run-real-codex -s
```

Patchlet real-Codex execution defaults to 10 minutes / 600 seconds. Operators
can set `CODEX_TIMEOUT_SECONDS`, and patchlet-specific runs can set
`CODEX_PATCHLET_TIMEOUT_SECONDS` to take precedence. The patchlet receives
`CXOR_TIMEOUT_SECONDS` and `CXOR_SOFT_DEADLINE_SECONDS`.

Invalid timeout env values are structured errors before Codex launches.
`CODEX_TIMEOUT_SECONDS`, `CODEX_PATCHLET_TIMEOUT_SECONDS`, and
`CODEX_PROGRESS_INTERVAL_SECONDS` must be positive integer seconds. Invalid
values report the env var name, the bad value, and `expected positive integer
seconds`.

That smoke exercises:

```bash
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode real_codex --use-worktree
```

When repeating a real-Codex smoke on the same target, check
`cxor workflows --repo <target>` first. Existing terminal workflows have a
`workflow_identity.json` and goal fingerprint. A changed prompt requires
`--new-run` or `--force-new-run`; dirty product/runtime files are refused
unless `--allow-dirty-target` is used and recorded. `--live-progress` uses an
invocation cursor so old `operator_events.jsonl` entries are not replayed.

The generated smoke prompt injects the operator contract from:

- `src/codex_orchestrator/prompt_templates/real_codex_patchlet_contract.md`
- `.codex-orchestrator/subprompts/<attempt>.md`

Before doing any task work, real Codex is instructed to read:

- `.codex-orchestrator/runs/P0001_attempt1/worker_memory/TASK_CONTRACT.md`
- `.codex-orchestrator/runs/P0001_attempt1/worker_memory/LIVE_MEMORY.md`
- `.codex-orchestrator/runs/P0001_attempt1/worker_memory/WRITE_THESE_FILES.md`

Then it must write:

- `.codex-orchestrator/runs/P0001_attempt1/worker_stage/00_preflight.md`

Before the final response, it must write:

- `.codex-orchestrator/runs/P0001_attempt1/worker_stage/05_final_report.md`

The worker must use `CXOR_WORKER_STAGE_DIR`, `CXOR_PREFLIGHT_PATH`, and
`CXOR_FINAL_REPORT_PATH` for stage files. Do not create target-root
worker_stage/. If real Codex writes a top-level `worker_stage/`, diagnosis
reports `worker_capsule_path_violation`. This is a Codex path-obedience issue,
not orchestrator wiring failure. Do not weaken validators.

If a real-Codex attempt exits `0` but writes a malformed patchlet report, the
diagnosis is `patchlet_report_schema_violation`, not `network_or_api_error`.
The valid report statuses are `COMPLETE`, `VERIFIED_NO_CHANGE_NEEDED`,
`BLOCKED_WITH_EVIDENCE`, and `FAILED_WITH_EVIDENCE`. `FIXED`, `DONE`,
`SUCCESS`, `PASSED`, and `OK` are invalid. `cleanup_proof` must be a string,
not an object, and `changed_product_runtime_file`, `deterministic_run_counts`,
`before_after_state`, `row_ledger`, and `trace_ledger` must be present. Repair
patchlets receive a report skeleton with these fields.

For probe artifacts, canonical reports require object-shaped
`probe_artifact_refs`. Raw real-Codex string refs are preserved in
`.codex-orchestrator/reports/<PATCHLET_ID>.raw.json` and may be normalized only
by report ingestion when they point to existing files under
`.artifacts/probes/` for the current patchlet. The canonical report remains
`.codex-orchestrator/reports/<PATCHLET_ID>.json`. Unsafe refs write
`report_ingestion_result.json` and `report_validation_errors.json` with
specific signatures such as `probe_artifact_refs_not_objects` or
`probe_artifact_refs_unsafe_path`; this class must not be reduced to
`unknown_repeated_failure`. See `docs/report_contract.md`.

Workers edit product/runtime files only in `CXOR_EXECUTION_ROOT`.
`CXOR_TARGET_ROOT` product/runtime files are read-only to the worker; target
root remains writable only for `.codex-orchestrator/` and `.artifacts/probes/`
evidence.

The final Markdown report must contain a canonical `FINAL_STATUS` marker as a
standalone line beginning at column 1. Accepted lines are `FINAL_STATUS: PASS`,
`FINAL_STATUS: BLOCKED`, and `FINAL_STATUS: FAILED`. Non-canonical forms are
rejected, including `Marker: `FINAL_STATUS: PASS``, markers wrapped in
backticks, markers inside sentences, and invalid values such as
`FINAL_STATUS: OK`. A valid report JSON alone does not bypass the wrapper gate.
Marker failures diagnose as `wrapper_gate_final_status_marker_error`;
`network_or_api_error` does not mask structured wrapper-gate failures.
Any non-canonical marker should be treated as a worker contract failure, not as
DONE.

Transaction group ids such as `TG001` are not patchlet ids. Transaction-group
failures preserve the TG id and member patchlet ids in `source_patchlet_ids`;
regeneration expands those member patchlets instead of looking for a patchlet
named `TG001`. If the mapping is absent, the structured error is
`transaction_group_source_mapping_missing`.

The smoke remains validator-backed and evidence-bound:

- inspect `.codex-orchestrator/runs/`, `.codex-orchestrator/failures/`, and `.artifacts/probes/`
- use `cxor inspect-capsule --repo /path/to/target-repo --attempt P0001_attempt1`
- use `cxor validate-capsule --repo /path/to/target-repo --attempt P0001_attempt1`
- use `cxor diagnose-real-codex --repo /path/to/target-repo --attempt P0001_attempt1` after safe failure
- do not weaken validators
- do not allow blind retry

Safe failure should preserve:

- `run_manifest.json`
- `stdout.txt`
- `stderr.txt`
- `command.json`
- `output.jsonl`
- `progress.jsonl`

`progress.jsonl` is a compact liveness stream, not success evidence. Timeout
safe-failure means containment and preserved evidence; it is not task success
and does not mean `DONE`.

When `command.json` or the run manifest proves `timed_out=true` with
`exit_code=124`, `diagnose-real-codex` reports
`orchestrator_subprocess_timeout`. This category means the orchestrator
terminated the Codex subprocess at the configured timeout. It is not task
success, and it links `progress.jsonl` if Codex emitted liveness before
timeout.

The explicit real-Codex smoke is an operator-run command. It is not part of the
default test suite and should only be run when the environment is safe for an
installed Codex invocation.

For repeatable evidence capture, use the operator runbook:

```bash
uv run --no-sync cxor real-codex-smoke-runbook --dry-run
CODEX_PATCHLET_TIMEOUT_SECONDS=600 uv run --no-sync cxor real-codex-smoke-runbook --run-real-codex
```

Default pytest does not run real Codex. `--dry-run` does not invoke real Codex
and writes `result.json` with outcome dry_run. `--run-real-codex` may consume
account, network, model, token, and wall-clock resources and may run up to
`CODEX_PATCHLET_TIMEOUT_SECONDS`.

The runbook writes
`.operator-runs/real-codex-smoke/<timestamp>-real-codex-smoke/` with
`README.md`, `environment.txt`, `git_status.txt`, `codex_version.txt`,
`selected_policy.json`, `default_skip_stdout.txt`, `default_skip_stderr.txt`,
`explicit_smoke_stdout.txt`, `explicit_smoke_stderr.txt`, `result.json`, and
`diagnosis_paths.json`. Compare runs by diffing `selected_policy.json`,
`result.json`, and `diagnosis_paths.json`.

Each bundle can be checked after capture:

```bash
cxor validate-real-codex-smoke-runbook --run-dir .operator-runs/real-codex-smoke/<timestamp>-real-codex-smoke
```

The validator is read-only, does not run Codex, and does not run pytest. It
uses `real_codex_smoke_selected_policy.schema.json`,
`real_codex_smoke_operator_result.schema.json`,
`real_codex_smoke_diagnosis_paths.schema.json`, and
`real_codex_smoke_runbook_validation.schema.json`. It also checks required text
evidence files such as `environment.txt`, `default_skip_stdout.txt`,
`default_skip_stderr.txt`, `explicit_smoke_stdout.txt`, and
`explicit_smoke_stderr.txt`.

List local operator-run bundles with:

```bash
cxor list-real-codex-smoke-runbooks
cxor list-real-codex-smoke-runbooks --root .operator-runs/real-codex-smoke --json
cxor list-real-codex-smoke-runbooks --latest
cxor list-real-codex-smoke-runbooks --only-invalid
cxor list-real-codex-smoke-runbooks --limit 10
```

The list command is read-only, does not run Codex, and does not run pytest. It
shows which bundle is latest, which bundles are valid, their outcome, selected
model/reasoning, timeout, `timed_out`, diagnosis category, and paths to
`result.json` and `validation_result.json`. Invalid bundles are listed rather
than hidden; validate one bundle with
`cxor validate-real-codex-smoke-runbook --run-dir <dir>`.

Export one validated bundle with:

```bash
cxor export-real-codex-smoke-runbook --run-dir .operator-runs/real-codex-smoke/<timestamp>-real-codex-smoke
```

The export command writes a zip archive and sidecar manifest with relative
paths, sizes, and sha256 hashes. It is read-only for the source bundle, does
not run Codex, does not run pytest, and refuses invalid bundles unless
`--force` is passed.

`safe_failure is a successful runbook capture`, not task DONE. `DONE means the
orchestrator validators accepted the run`.

Patchlet Codex defaults to `gpt-5.4-mini` with reasoning `medium`.
Non-patchlet/orchestrator Codex profiles default to `gpt-5.5` with reasoning
`medium`.

If the preserved artifacts do not justify a narrower claim, the diagnosis
should stay at `unknown_codex_nonzero_exit`.

Real success is not guaranteed. It still depends on real Codex producing a
valid report and durable probe artifacts that satisfy the existing validators.

## Live Progress And Integration Results

Explicit runbook mode enables compact live progress by default and tees only
lines beginning with `[cxor:`. Disable terminal progress with
`CXOR_LIVE_CODEX_PROGRESS=0` or pass `--no-live-progress`; `progress.jsonl`
remains the durable liveness record. Live progress does not prove success, and
safe failure is not DONE.

Accepted real-Codex changes advance `refs/cxor/runs/<run_id>/integration`; the
target repo remains clean between patchlets and the next worktree starts from
the integration SHA. DONE verifies that integration SHA. Use
`cxor apply-results --mode patch`, `cxor apply-results --mode branch`, or
`cxor apply-results --mode working-tree` after DONE to consume results.

The integration artifacts used by those steps are schema-validated:
`integration_state.json` uses `integration_state.schema.json`,
`accepted_changes.jsonl` is validated line-by-line with
`accepted_change.schema.json`, checkpoints use
`integration_checkpoint.schema.json`, and apply-results files such as
`patch_result.json` use `apply_results_result.schema.json`.

```bash
cxor validate-integration-artifacts --repo /path/to/target-repo
```

The validator is read-only, does not run Codex, and helps compare whether a
safe failure preserved structurally valid integration evidence.

## P0004 Checkpoint Cleanliness

Live smoke bundles now preserve checkpoint cleanliness taxonomy and runbook
attempt consistency. `target_working_tree_clean_after_checkpoint` remains
strictly `true`; the system does not accept false checkpoints. The Target
Hygiene Gate writes `target_hygiene_gate_result.json` and classifies
`product_runtime_clean`, `artifact_dirs_ignored`, `cache_artifacts_detected`,
`cache_artifacts_removed`, and `unknown_dirty_paths`.

Product/runtime clean is distinct from whole target clean: `app.py` and other
runtime files must be clean, while `.codex-orchestrator/` and `.artifacts/`
remain writable evidence directories. `__pycache__/` is not blindly ignored;
known untracked cache artifacts are evidence-recorded, safely removed, and
listed in the checkpoint sidecar. Unknown dirty paths are not deleted and
produce precise failure evidence.

Real-Codex worker subprocesses set `PYTHONDONTWRITEBYTECODE=1`. Generated
worker prompts instruct probes to use `python -B` or
`PYTHONDONTWRITEBYTECODE=1 python` when importing target or execution code.
Checkpoints include `target_cleanliness`, and sidecars are written under
`.codex-orchestrator/integration/checkpoints/<PATCHLET>_cleanliness.json`.

The run manifest records `ATTEMPT_STARTED`, `WORKER_EXITED`,
`REPORT_VALIDATED`, `WRAPPER_GATE_EVALUATED`, `TARGET_HYGIENE_EVALUATED`,
`INTEGRATION_CHECKPOINT_WRITTEN`, `INTEGRATION_ARTIFACTS_VALIDATED`,
`ATTEMPT_ACCEPTED`, and `ATTEMPT_FAILED_WITH_EVIDENCE`. Runbook results expose
`attempt_consistency` so P0004 paths cannot be silently mixed with P0003
manifest or diagnosis evidence.

Structured categories such as
`integration_checkpoint_target_cleanliness_error`,
`integration_artifact_validation_error`, `run_manifest_attempt_lifecycle_error`,
`runbook_attempt_evidence_mismatch`, and `target_cache_artifact_leak` outrank
`network_or_api_error`. `network_or_api_error` requires actual external error
evidence. After each live smoke, run `validate-real-codex-smoke-runbook`,
`list-real-codex-smoke-runbooks`, and `export-real-codex-smoke-runbook`.

## Direct Auto Visibility After Smoke Hardening

For manual direct real-Codex operation, use:

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

Direct auto progress is based on `.codex-orchestrator/operator_events.jsonl`.
Use `--no-live-progress` for quiet mode, `--progress-interval-seconds` for
heartbeats, and `--progress-format jsonl` for structured event lines. It does
not print raw Codex JSON or full prompt bodies.

Read-only visibility commands:

```bash
uv run --no-sync cxor monitor --repo /tmp/cxor-target --follow
uv run --no-sync cxor status --repo /tmp/cxor-target --watch
uv run --no-sync cxor prompts --repo /tmp/cxor-target --latest
uv run --no-sync cxor prompts --repo /tmp/cxor-target --show PR000001 --lines 160
```

Prompts are indexed in `.codex-orchestrator/prompt_index.json`. Repeated repair
loops are tracked in `.codex-orchestrator/loop_governor.json`; warnings surface
as `loop_governor_warning`, and safe-fail mode is explicit:

```bash
uv run --no-sync cxor auto \
  --repo /tmp/cxor-target \
  --master /tmp/cxor-target/master_prompt.md \
  --until DONE \
  --worker-mode real_codex \
  --use-worktree \
  --live-progress \
  --loop-governor-mode safe-fail \
  --max-repeated-failure-signature 3
```

Default tests do not invoke real Codex.
