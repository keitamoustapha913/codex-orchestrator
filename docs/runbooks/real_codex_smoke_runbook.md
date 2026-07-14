# Real Codex Smoke Runbook

For repeat runs on the same target, do not manually delete
`.codex-orchestrator/`. `cxor auto` records `workflow_identity.json` and
refuses changed prompts or dirty product/runtime targets unless the operator
uses `--new-run`, `--force-new-run`, or `--allow-dirty-target`. Use
`cxor workflows`, `cxor archive`, and `cxor reset --archive` to preserve
evidence and start a fresh workflow. `--live-progress` is invocation-scoped and
does not replay old operator events.

Default pytest does not run real Codex. The `real-codex-smoke-runbook`
command is an operator-controlled evidence capture for manual installed-Codex
smoke runs, and it is not part of the default test suite.

## Dry Run

Use dry-run mode first:

```bash
export UV_CACHE_DIR=/tmp/uv-cache
uv run --no-sync cxor real-codex-smoke-runbook --dry-run
```

`--dry-run` creates the operator-run artifact directory, captures environment
and policy evidence, runs the default skipped smoke check, and does not invoke
real Codex. The expected result is `result.json` with outcome dry_run.

## Explicit Run

Use explicit mode only when the environment is safe for an installed Codex
invocation:

```bash
export UV_CACHE_DIR=/tmp/uv-cache
CODEX_PATCHLET_TIMEOUT_SECONDS=600 \
uv run --no-sync cxor real-codex-smoke-runbook --run-real-codex
```

`--run-real-codex` may consume account, network, model availability, token, and
wall-clock resources. It may run up to `CODEX_PATCHLET_TIMEOUT_SECONDS`.
Patchlet default policy is recorded in `selected_policy.json`, including
`codex_patchlet_timeout_seconds`, model, reasoning, and progress interval.

## Artifact Layout

Each run writes:

```text
.operator-runs/real-codex-smoke/<timestamp>-real-codex-smoke/
  README.md
  environment.txt
  git_status.txt
  codex_version.txt
  selected_policy.json
  default_skip_stdout.txt
  default_skip_stderr.txt
  explicit_smoke_stdout.txt
  explicit_smoke_stderr.txt
  result.json
  diagnosis_paths.json
```

The runbook preserves raw stdout and stderr even when explicit smoke output
cannot be parsed as JSON. When diagnosis files are referenced and present, the
runbook copies them into the operator-run directory as `diagnosis.json` and
`diagnosis.md`.

Each bundle also writes `validation_result.json`. Validate any saved bundle
again with:

```bash
cxor validate-real-codex-smoke-runbook --run-dir .operator-runs/real-codex-smoke/<timestamp>-real-codex-smoke
```

The validator is read-only, does not run Codex, does not run pytest, and only
inspects the supplied operator-run directory. It checks JSON schemas for
`selected_policy.json`, `result.json`, and `diagnosis_paths.json`:

- `real_codex_smoke_selected_policy.schema.json`
- `real_codex_smoke_operator_result.schema.json`
- `real_codex_smoke_diagnosis_paths.schema.json`
- `real_codex_smoke_runbook_validation.schema.json`

It also checks required text evidence files including `environment.txt`,
`git_status.txt`, `codex_version.txt`, `default_skip_stdout.txt`,
`default_skip_stderr.txt`, `explicit_smoke_stdout.txt`, and
`explicit_smoke_stderr.txt`. Dry-run bundles and explicit-run bundles can both
be validated after capture.

## Compare Runs

To compare runs, diff `selected_policy.json`, `result.json`, and
`diagnosis_paths.json` across timestamped directories. Use stdout/stderr files
to verify what the smoke printed, and use copied diagnosis artifacts to inspect
the preserved cause classification.

List local bundles first:

```bash
cxor list-real-codex-smoke-runbooks
cxor list-real-codex-smoke-runbooks --json
cxor list-real-codex-smoke-runbooks --root .operator-runs/real-codex-smoke
cxor list-real-codex-smoke-runbooks --latest
cxor list-real-codex-smoke-runbooks --only-invalid
cxor list-real-codex-smoke-runbooks --limit 10
```

The list command is read-only, does not run Codex, and does not run pytest. It
summarizes each timestamped run's outcome, validation status, selected
model/reasoning, timeout, `timed_out`, diagnosis category, `result.json`, and
`validation_result.json`. Invalid bundles are listed rather than hidden. Use
`cxor validate-real-codex-smoke-runbook --run-dir <dir>` for full validation of
one bundle.

Export one validated bundle for release evidence:

```bash
cxor export-real-codex-smoke-runbook --run-dir <dir>
cxor export-real-codex-smoke-runbook --run-dir <dir> --out /tmp/runbook.zip
cxor export-real-codex-smoke-runbook --run-dir <dir> --force
```

The export command creates a zip archive plus sidecar manifest. The manifest
records source bundle validity, outcome, selected model/reasoning, timeout,
diagnosis category, relative file paths, file sizes, and sha256 hashes. The
source bundle is not modified. Invalid bundles require `--force`.

`safe_failure is a successful runbook capture`, not task DONE. It means the
runbook captured evidence for a contained real-Codex failure. `DONE means the
orchestrator validators accepted the run`, including report validation, probe
artifact validation, wrapper gates, transaction groups, and global verification.

One precise safe-failure category is `patchlet_report_schema_violation`. It
means Codex completed but wrote a report that the existing schema rejected; it
is not a `network_or_api_error`. Valid report statuses are `COMPLETE`,
`VERIFIED_NO_CHANGE_NEEDED`, `BLOCKED_WITH_EVIDENCE`, and
`FAILED_WITH_EVIDENCE`. `FIXED`, `DONE`, `SUCCESS`, `PASSED`, and `OK` are
invalid. `cleanup_proof` must be a string, not an object, and required report
fields such as `changed_product_runtime_file`, `deterministic_run_counts`,
`before_after_state`, `row_ledger`, and `trace_ledger` must exist. Repair
patchlets receive a report skeleton and must not invent new statuses.

For RC6B semantic result failures, inspect
`semantic_goal_results_normalization_result.json` and
`semantic_goal_results_canonicalization_result.json`. Shorthand
`semantic_goal_results` are accepted only as raw worker semantic claims, not as
proof. The orchestrator links them to the current goal item, proof obligation,
slice boundary, and probe plan, preserves the raw worker output, rejects vague
or future-slice claims, and canonicalizes passed/failed only after independent
probe rerun.

For probe artifacts, canonical `probe_artifact_refs` entries are objects.
Raw real-Codex reports may contain string path refs only before report
ingestion. Safe strings are normalized only when the referenced files exist
under `.artifacts/probes/` for the current patchlet and do not escape by
symlink. The raw report is preserved separately from the canonical report, and
normalization or rejection is recorded in `report_ingestion_result.json` and
`report_validation_errors.json`. The specific string-ref shape failure is
`probe_artifact_refs_not_objects`; runbook evidence should not reduce this
class to `unknown_repeated_failure`. See `docs/report_contract.md`.
Object-shaped `probe_artifact_refs` are canonicalized from actual artifact
files. Worker-provided hashes are not trusted, worker-provided sizes are not
trusted, and raw worker metadata is preserved for audit. Unsafe paths, missing
files, patchlet mismatches, and product files remain rejected; do not treat a
worker hash as proof.

For scratch artifacts, inspect
`.codex-orchestrator/runs/<attempt>/gates/scratch_artifact_quarantine_result.json`.
Recognized real-Codex scratch files are quarantined, not silently deleted. The
artifact preserves content hashes and records why the path was scratch. The
diff guard then rechecks product/runtime paths. Unknown root product files,
second product files, executable root files, and slice-boundary violations
remain failures.

Each attempt has a worker scratch directory:
`.codex-orchestrator/runs/<attempt>/worker_scratch/`. The prompt tells Codex:
Do not write scratch/check/validation files in the target repository root. A
root scratch sweep runs after worker exit, writes `root_scratch_sweep_result.json`,
and uses role-based quarantine for report/probe validation outputs. Only
role-shaped untracked worker scratch directories are eligible for quarantine.
Not all directories are allowed. Not all scratch directories are allowed.
Tracked `worker_scratch` content is rejected. Executable scratch content is
rejected. Changed peer product files remain rejected. Directory quarantine
preserves hashes and metadata, and changed paths are recomputed after
quarantine.

Patchlet-prefixed report formatting scratch is quarantined only when it is safe:
untracked, non-executable, text/JSON-like, patchlet-prefixed, report-role
shaped, and formatting/check/output-role shaped. Not all JSON files are allowed.
Not all pretty files are allowed. Product/runtime files remain rejected, changed
peer product files remain rejected, quarantine preserves content and hash
metadata, and the diff is recomputed after quarantine.

When inspecting Scenario 2-style multi-file targets, remember that the guard
uses actual changed/untracked paths, not file presence. Unchanged peer product
files are ignored because presence is not a change. Changed peer product files
are rejected. `validate_report.out` is role-shaped validation scratch, but
`random.out` is not automatically scratch.
The allowed file from the patchlet plan is authoritative, not filename
convention; non-scenario names such as `control.plan`, `rollout.table`, and
`verify_result.log` use the same policy.

The final Markdown report has a separate wrapper gate. It must contain a
standalone canonical marker line: `FINAL_STATUS: PASS`,
`FINAL_STATUS: BLOCKED`, or `FINAL_STATUS: FAILED`. Non-canonical forms are
rejected, including `Marker: `FINAL_STATUS: PASS`` and markers wrapped in
backticks. A valid report JSON alone does not bypass the wrapper gate. Marker
failures diagnose as `wrapper_gate_final_status_marker_error`;
`network_or_api_error` does not mask structured gate or routing failures.

Transaction group ids such as `TG001` are not patchlet ids. Transaction-group
failure records preserve member patchlet ids in `source_patchlet_ids`; repair
regeneration expands those members. If no member mapping exists, the structured
error is `transaction_group_source_mapping_missing`.

Workers edit product/runtime files only under `CXOR_EXECUTION_ROOT`.
Product/runtime files under `CXOR_TARGET_ROOT` are read-only to Codex workers,
while target-root `.codex-orchestrator/` and `.artifacts/probes/` remain
writable for evidence. After any safe failure, use
`cxor validate-real-codex-smoke-runbook --run-dir <dir>`, then
`cxor list-real-codex-smoke-runbooks --latest`, and
`cxor export-real-codex-smoke-runbook --run-dir <dir>` to preserve and compare
the evidence.

## Live Progress And Accepted Results

With `--run-real-codex --live-progress`, the runbook tees only compact
`[cxor:...]` live progress lines. Use `--no-live-progress` or
`CXOR_LIVE_CODEX_PROGRESS=0` to silence terminal progress. The durable record is
still `progress.jsonl`.

Accepted changes are not applied to the operator working tree during the smoke.
They advance `refs/cxor/runs/<run_id>/integration`; the target repo remains
clean between patchlets and subsequent worktrees start from the integration
SHA. After DONE, use `cxor apply-results --mode patch`, `cxor apply-results
--mode branch`, or `cxor apply-results --mode working-tree`.
## P0004 Checkpoint Cleanliness And Evidence Consistency

When a live smoke safe-fails after an accepted worker attempt, inspect the
Target Hygiene Gate before assuming a network failure. Checkpoint cleanliness
uses a checkpoint cleanliness taxonomy: `product_runtime_clean`,
`artifact_dirs_ignored`, `cache_artifacts_detected`,
`cache_artifacts_removed`, `unknown_dirty_paths`, and
`whole_repo_clean_after_hygiene`.

`target_working_tree_clean_after_checkpoint` remains strict and must be true.
The checkpoint also records `target_cleanliness`, and the sidecar
`.codex-orchestrator/integration/checkpoints/<PATCHLET>_cleanliness.json`
explains the decision. `.codex-orchestrator/` and `.artifacts/` are durable
evidence directories. Python cache artifacts such as `__pycache__/` are
evidence-recorded in `target_hygiene_gate_result.json`; removable cache files
are hashed and listed in `cache_artifacts_detected` and
`cache_artifacts_removed`. Unknown dirty paths are not deleted.

Workers set `PYTHONDONTWRITEBYTECODE=1`, and prompts tell Codex to use
`python -B` or `PYTHONDONTWRITEBYTECODE=1 python` for probes that import target
or execution code. Product/runtime clean means target files such as `app.py`
are clean; whole target clean also accounts for allowed artifact directories
and safe cache cleanup.

The run manifest records attempt lifecycle states:
`ATTEMPT_STARTED`, `WORKER_EXITED`, `REPORT_VALIDATED`,
`WRAPPER_GATE_EVALUATED`, `TARGET_HYGIENE_EVALUATED`,
`INTEGRATION_CHECKPOINT_WRITTEN`, `INTEGRATION_ARTIFACTS_VALIDATED`,
`ATTEMPT_ACCEPTED`, and `ATTEMPT_FAILED_WITH_EVIDENCE`. Bundle `result.json`
contains `attempt_consistency`; mismatches are surfaced by validate/list/export
instead of silently combining P0004 paths with P0003 evidence.

Relevant diagnoses are `integration_checkpoint_target_cleanliness_error`,
`integration_artifact_validation_error`, `run_manifest_attempt_lifecycle_error`,
`runbook_attempt_evidence_mismatch`, and `target_cache_artifact_leak`.
`network_or_api_error` requires actual external error evidence. After a live
run, always use `validate-real-codex-smoke-runbook`,
`list-real-codex-smoke-runbooks`, and `export-real-codex-smoke-runbook`.

## Manual Direct Auto Visibility

Direct manual real-Codex runs should use `cxor auto --live-progress` when the
operator needs concise terminal visibility:

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

Use `--no-live-progress` for quiet mode, `--progress-interval-seconds` for
heartbeat cadence, and `--progress-format jsonl` for structured event output.
Progress comes from `.codex-orchestrator/operator_events.jsonl`; prompt
metadata is in `.codex-orchestrator/prompt_index.json`; repeated repair-loop
state is in `.codex-orchestrator/loop_governor.json`.

Second-terminal read-only commands:

```bash
uv run --no-sync cxor monitor --repo /tmp/cxor-target --follow
uv run --no-sync cxor status --repo /tmp/cxor-target --watch
uv run --no-sync cxor prompts --repo /tmp/cxor-target --latest
uv run --no-sync cxor prompts --repo /tmp/cxor-target --show PR000001 --lines 160
```

Prompt bodies are not printed by default, and compact progress does not print
raw Codex JSON. `cxor status --json` distinguishes active-but-silent from
likely stalled. Loop-governor warning mode emits `loop_governor_warning`; safe
failure requires explicit `--loop-governor-mode safe-fail
--max-repeated-failure-signature 3`. Default tests do not run real Codex.

For supported goals, `DONE` also means model-mediated goal interpretation,
proof planning, probe planning, independent proof rerun or validation, goal
coverage, and master-prompt satisfaction passed. No app.py-specific,
app.main-specific, Python-specific, or smoke-prompt regex parser is supported
as the general architecture.

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

## General Work Decomposition Check

Before optional real-Codex multi-patchlet smoke, deterministic mock tests should confirm `work_decomposition_plan.json`, `work_slices.json`, `patchlet_plan.json`, `dependency_graph.json`, and `transaction_group_plan.json`. Every patchlet must have exactly one allowed product/runtime file, and same-file patchlets must be ordered. See `docs/multi_patchlet_transaction_graph.md`.

## RC6 Real-Codex Matrix Checks

For real-Codex smoke and matrix runs, one allowed file per patchlet is necessary but not sufficient. Same-file patchlets require a slice-level allowed-change boundary, and future slice changes are rejected even when they are inside the same allowed product/runtime file. Confirm patchlet-scoped proof selects only current obligations, future obligations remain unproven, PARTIAL progress accepts patchlet progress but blocks DONE, report ingestion accepts pass: / fail: / blocked: descriptive prefixes, artifact directories are allowed only under approved roots, and the full matrix passes before rc6.

Boundary evidence matching is role-aware. Short tokens such as `on`, `off`,
`no`, or `yes` do not match as substrings inside unrelated words like
`boundary`, `control`, or `now`. Future-slice rejection requires a role-aware
future boundary evidence combination, such as an exact line `event_logging=on`
or matching future key and value. Same-file mention alone is not a future
claim. Worker text is not proof; independent proof remains required.
## Positive-Evidence Checks

When reviewing smoke evidence, confirm that each patchlet is backed by positive
planning evidence. An unmatched candidate must receive no work. Support files
remain targetable when explicitly planned, but they must not inherit unrelated
goals or proof obligations. For same-file work, multiple patchlets may target
one file, with one goal, one proof obligation, and one probe per independently
provable slice. Treat unresolved or ambiguous mappings as safe pre-worker stops.
