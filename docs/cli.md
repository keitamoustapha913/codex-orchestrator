# CLI

Primary MVP command:

```bash
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode mock
```

Rerun controls:

```bash
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --resume
cxor auto --repo /path/to/target-repo --master /path/to/new_prompt.md --new-run
cxor auto --repo /path/to/target-repo --master /path/to/new_prompt.md --force-new-run
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --allow-dirty-target
cxor archive --repo /path/to/target-repo
cxor reset --repo /path/to/target-repo --archive
cxor workflows --repo /path/to/target-repo --json
```

`workflow_identity.json` stores the goal fingerprint. Changed prompt path,
changed prompt content, or dirty product/runtime state is refused by default
instead of silently reusing old `DONE` state. `rerun_preflight_result.json`
records the decision and recommended command. `--live-progress` creates an
invocation cursor so old operator events are not replayed.

Stage commands implemented:

```bash
cxor init
cxor status
cxor validate-state
cxor census
cxor normalize
cxor classify-evidence
cxor build-inventory
cxor extract-invariants
cxor compile-patchlets
cxor run-next
cxor run-all
cxor validate-report
cxor verify-group
cxor verify-all-groups
cxor verify-global
cxor inspect-capsule
cxor validate-capsule
cxor diagnose-real-codex
cxor real-codex-smoke-runbook
cxor list-real-codex-smoke-runbooks
cxor export-real-codex-smoke-runbook
cxor classify-failures
cxor plan-repair
cxor apply-repair
cxor rediscover
cxor rebuild-inventory
cxor regenerate-patchlets
cxor auto
cxor archive
cxor reset
cxor workflows
```

`cxor stop --after-current-attempt` records `control/stop_requested.json`.
During patchlet execution, the request is honored at the between-patchlet safe
point after the current attempt reaches a terminal state and before another
patchlet is selected. The orchestrator writes `control/stop_result.json`, the
next patchlet does not start, and `cxor apply-results --scope accepted
--allow-partial` applies only the accepted checkpoint. Pending or unaccepted
work is not applied. If no accepted checkpoint exists, `stop_result.json`
records `applyable_progress=false`.

Repair loop:
`failure -> classification -> repair plan -> apply repair -> regenerate patchlets -> verify`

No blind retry. Use:

```bash
cxor apply-repair --repo /path/to/target-repo
cxor regenerate-patchlets --repo /path/to/target-repo --from-repair-plan latest
```

These repair replay commands are idempotent when the corresponding durable artifacts already exist:

```bash
cxor apply-repair --repo /path/to/target-repo
cxor regenerate-patchlets --repo /path/to/target-repo --from-repair-plan latest
cxor auto --repo /path/to/target-repo --resume --until DONE --worker-mode mock
```

If the workflow is already `DONE`, `cxor apply-repair` and `cxor regenerate-patchlets` become terminal no-op commands. They exit successfully, report the no-op, and leave state, patchlet index, final verification, and product/runtime files unchanged.

Durable probe artifacts and `probe_artifact_refs` are required for successful patchlet reports.
Canonical reports keep `probe_artifact_refs` object-shaped. Raw real-Codex
string refs are accepted only at report ingress when the files are safe,
existing, and under `.artifacts/probes/`; canonical reports still reject
string refs. Inspect `.codex-orchestrator/runs/<attempt>/gates/report_ingestion_result.json`
and `report_validation_errors.json` for normalization or failure details. The
specific repeated string-ref signature is `probe_artifact_refs_not_objects`,
not `unknown_repeated_failure`. Full details are in `docs/report_contract.md`.

Transaction group and global verification commands:

```bash
cxor verify-group --repo /path/to/target-repo TG001
cxor verify-all-groups --repo /path/to/target-repo
cxor verify-global --repo /path/to/target-repo
```

Advanced repair and rediscovery commands:

```bash
cxor rediscover --repo /path/to/target-repo --scope impacted
cxor rediscover --repo /path/to/target-repo --scope full
cxor rebuild-inventory --repo /path/to/target-repo --scope impacted
```

Optional worktree execution with validated merge:

```bash
cxor run-next --repo /path/to/target-repo --worker-mode mock --use-worktree
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode mock --use-worktree
```

Worktree mode is optional, not default. It requires a clean target repo apart from volatile workflow artifacts and isolates unauthorized diffs before any target product/runtime merge.

During real-Codex worktree runs, `cxor` may quarantine recognized root-level
worker scratch artifacts such as report/probe validation outputs. Quarantine is
recorded in `scratch_artifact_quarantine_result.json` with preserved content
hash metadata, and the diff guard is rerun against the remaining product
changes. Unknown root product/runtime files are rejected; the one-file rule and
slice boundary still apply.

Each attempt exposes `.codex-orchestrator/runs/<attempt>/worker_scratch/` as the
worker scratch directory and tells Codex: Do not write scratch/check/validation
files in the target repository root. After worker exit, the root scratch sweep
uses role-based quarantine, writes `root_scratch_sweep_result.json`, and records
content/hash metadata. Only role-shaped untracked worker scratch directories
are eligible for quarantine. Not all directories are allowed. Not all scratch
directories are allowed. Tracked `worker_scratch` content is rejected.
Executable scratch content is rejected. Changed peer product files remain
rejected. Directory quarantine preserves hashes and metadata, and changed paths
are recomputed after quarantine.

Patchlet-prefixed report formatting scratch is quarantined only when safe:
untracked, non-executable, text/JSON-like, patchlet-prefixed, report-role
shaped, and formatting/check/output-role shaped. Not all JSON files are allowed.
Not all pretty files are allowed. Product/runtime files remain rejected, changed
peer product files remain rejected, quarantine preserves content and hash
metadata, and the diff is recomputed after quarantine.

The sweep uses actual changed/untracked paths, not file presence. Unchanged peer
product files are ignored because presence is not a change. Changed peer product
files are rejected, while safe role-shaped validation scratch such as
`validate_report.out` can be quarantined.
The allowed file from the patchlet plan is authoritative, not filename
convention; arbitrary names such as `control.plan`, `rollout.table`, and
`verify_result.log` follow the same policy.

Operator shorthand: random root .txt files are not automatically allowed.

Opt-in real Codex smoke:

```bash
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py --run-real-codex -s
```

This smoke is not part of the default test suite. It exercises `cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode real_codex --use-worktree`.

Fake-success parity also covers this exact `worker_mode=real_codex` path with a
fake Codex binary that reaches `DONE` only by writing a valid report and
durable probe artifacts. That proves the orchestrator wiring without claiming
that installed real Codex will always succeed.

Operator rules:

- do not weaken validators for real Codex;
- real Codex success to DONE is not guaranteed and still depends on valid report and durable probe artifact output;
- inspect `run_manifest.json` for the failed patchlet attempt entry;
- inspect `.codex-orchestrator/runs/`, `.codex-orchestrator/failures/`, and `.artifacts/probes/`;
- on safe failure, expect a `WORKER_FAILED` run-manifest entry plus preserved `stdout.txt`, `stderr.txt`, `command.json`, and `output.jsonl`;
- treat contained failure evidence as acceptable smoke output when real Codex does not reach `DONE`.

Patchlet real-Codex runs default to a 10 minutes / 600 seconds timeout.
`CODEX_TIMEOUT_SECONDS` overrides the global timeout, while
`CODEX_PATCHLET_TIMEOUT_SECONDS` wins for patchlet execution. The generated
Worker Capsule and subprompt tell Codex the hard timeout and soft deadline
(`timeout - 60` seconds) and require a durable final report before timeout if
the task cannot complete.

Invalid timeout env values fail structurally before Codex launches. Values for
`CODEX_TIMEOUT_SECONDS`, `CODEX_PATCHLET_TIMEOUT_SECONDS`, and
`CODEX_PROGRESS_INTERVAL_SECONDS` must be positive integer seconds; otherwise
the error names the env var, the bad value, and `expected positive integer
seconds`.

`progress.jsonl` under the attempt run directory records compact real-Codex
liveness signals. It is not success evidence. A timeout safe-failure means the
orchestrator contained the failed attempt and preserved artifacts; it is not
task success and it is not `DONE`.

`diagnose-real-codex` reports command evidence with `timed_out=true` and
`exit_code=124` as `orchestrator_subprocess_timeout`. This diagnosis is
bounded containment, not task success, and it links `progress.jsonl` when that
liveness artifact exists.

The explicit real-Codex smoke is operator-run only and is not part of the
default test suite.

Operator-controlled real-Codex smoke runbook:

```bash
uv run --no-sync cxor real-codex-smoke-runbook --dry-run
CODEX_PATCHLET_TIMEOUT_SECONDS=600 uv run --no-sync cxor real-codex-smoke-runbook --run-real-codex
```

Dry-run mode does not invoke real Codex and records outcome dry_run. Explicit
mode may consume account, network, model, token, and wall-clock resources up to
`CODEX_PATCHLET_TIMEOUT_SECONDS`. Each run writes
`.operator-runs/real-codex-smoke/<timestamp>-real-codex-smoke/` with
`selected_policy.json`, `result.json`, `diagnosis_paths.json`,
`explicit_smoke_stdout.txt`, and `explicit_smoke_stderr.txt`. Compare runs by
diffing `selected_policy.json`, `result.json`, and `diagnosis_paths.json`.
`safe_failure is a successful runbook capture`, not task DONE; `DONE means the
orchestrator validators accepted the run`.

Patchlet Codex defaults to `gpt-5.4-mini` and reasoning `medium`.
Non-patchlet/orchestrator Codex profiles default to `gpt-5.5` and reasoning
`medium`.

Prompt contract artifact:

- `src/codex_orchestrator/prompt_templates/real_codex_patchlet_contract.md`

During the opt-in smoke, that contract is injected into the smoke prompt and
the generated prompt artifact under `.codex-orchestrator/subprompts/`. Inspect
that generated subprompt artifact first if installed Codex fails safely.

The contract carries a minimal valid report example for `CXOR_REPORT_PATH`, a
minimal durable probe layout for `CXOR_PROBE_ROOT`, and explicit instructions
not to invent alternate paths.

CI-friendly commands that exist:

```bash
cxor doctor --repo /path/to/target-repo
cxor validate-state --repo /path/to/target-repo
cxor verify-global --repo /path/to/target-repo
cxor auto --repo /path/to/target-repo --resume --until DONE --worker-mode ci_only
```

Real Codex safe-failure diagnosis:

```bash
cxor diagnose-real-codex --repo /path/to/target-repo --attempt P0001_attempt1
```

This command does not run Codex and does not mutate product/runtime files. It
reads `stdout.txt`, `stderr.txt`, `output.jsonl`, `command.json`,
`run_manifest.json`, and the generated prompt artifact, then writes:

- generic artifact kinds: `real_codex_failure_diagnosis.json` and `real_codex_failure_diagnosis.md`
- `.codex-orchestrator/diagnostics/real_codex/P0001_attempt1_diagnosis.json`
- `.codex-orchestrator/diagnostics/real_codex/P0001_attempt1_diagnosis.md`

If the preserved artifacts do not justify a more specific root cause, the
diagnosis will report `unknown_codex_nonzero_exit`. Do not weaken validators to
force a narrower classification.

Wrapper gate final-status marker errors are classified separately from
network/API failures. The final Markdown report must contain a standalone
canonical line: `FINAL_STATUS: PASS`, `FINAL_STATUS: BLOCKED`, or
`FINAL_STATUS: FAILED`. Non-canonical forms such as
`Marker: `FINAL_STATUS: PASS`` or backticked markers are rejected, and a valid
report JSON alone does not bypass the wrapper gate. The diagnosis category is
`wrapper_gate_final_status_marker_error`; `network_or_api_error` does not mask
structured gate or routing failures.

Transaction group ids such as `TG001` are not patchlet ids. Transaction-group
failure records preserve `source_patchlet_ids`, and regeneration expands those
member patchlets. Missing mapping reports
`transaction_group_source_mapping_missing`.

## Live Progress And Result Application

Real-Codex subprocesses may print compact live progress lines like
`[cxor:P0001_attempt1 +004s] codex: thread.started`. The durable liveness
record remains `progress.jsonl`; live progress proves only that the subprocess
is alive. Use `CXOR_LIVE_CODEX_PROGRESS=0` to silence terminal progress.

Accepted patchlets advance `refs/cxor/runs/<run_id>/integration`; the target
repo remains clean between patchlets and worktrees start from the integration
SHA. Consume accepted results explicitly:

```bash
cxor apply-results --repo /path/to/target-repo --mode patch
cxor apply-results --repo /path/to/target-repo --mode branch
cxor apply-results --repo /path/to/target-repo --mode working-tree
```

`--mode patch` does not mutate product/runtime files. `--mode branch` creates a
result branch without checkout. `--mode working-tree` requires a clean target
and mutates only after explicit operator request. A safe failure is evidence
capture, not DONE.

Integration artifact validation:

```bash
cxor validate-integration-artifacts --repo /path/to/target-repo
```

This read-only command does not run Codex. It validates
`integration_state.json` with `integration_state.schema.json`, validates
`accepted_changes.jsonl` line-by-line with `accepted_change.schema.json`,
validates checkpoint files with `integration_checkpoint.schema.json`, and
validates apply-results artifacts such as `patch_result.json` with
`apply_results_result.schema.json`. A non-zero exit means the integration
artifact set is structurally invalid and should not be treated as DONE.

Operator-run real-Codex smoke bundle validation:

```bash
cxor validate-real-codex-smoke-runbook --run-dir .operator-runs/real-codex-smoke/<timestamp>-real-codex-smoke
```

This command is read-only, does not run Codex, and does not run pytest. It
validates `selected_policy.json` with
`real_codex_smoke_selected_policy.schema.json`, validates `result.json` with
`real_codex_smoke_operator_result.schema.json`, validates
`diagnosis_paths.json` with `real_codex_smoke_diagnosis_paths.schema.json`,
validates `validation_result.json` with
`real_codex_smoke_runbook_validation.schema.json` when present, and checks
required text evidence files including `environment.txt`,
`default_skip_stdout.txt`, and `explicit_smoke_stdout.txt`.

List local real-Codex smoke runbook bundles:

```bash
cxor list-real-codex-smoke-runbooks
cxor list-real-codex-smoke-runbooks --root .operator-runs/real-codex-smoke
cxor list-real-codex-smoke-runbooks --json
cxor list-real-codex-smoke-runbooks --latest
cxor list-real-codex-smoke-runbooks --only-invalid
cxor list-real-codex-smoke-runbooks --limit 10
```

The list command is read-only, does not run Codex, and does not run pytest. It
summarizes each bundle's outcome, validation status, model, reasoning, timeout,
`timed_out`, diagnosis category, `result.json`, and `validation_result.json`.
Invalid bundles are listed rather than hidden. Use
`cxor validate-real-codex-smoke-runbook --run-dir <dir>` for one bundle's full
validation details.

Export one validated real-Codex smoke runbook bundle:

```bash
cxor export-real-codex-smoke-runbook --run-dir .operator-runs/real-codex-smoke/<timestamp>-real-codex-smoke
cxor export-real-codex-smoke-runbook --run-dir <bundle> --out /tmp/bundle.zip
cxor export-real-codex-smoke-runbook --run-dir <bundle> --force
```

The export command is read-only for the source bundle, does not run Codex, and
does not run pytest. It writes a zip archive and sidecar manifest with relative
paths, sizes, and sha256 hashes. Invalid bundles are refused unless `--force`
is used.

Worker Capsule inspection:

```bash
cxor inspect-capsule --repo /path/to/target-repo --attempt P0001_attempt1
cxor validate-capsule --repo /path/to/target-repo --attempt P0001_attempt1
```

These commands are read-only for product/runtime files. `inspect-capsule`
prints per-attempt capsule paths and presence bits. `validate-capsule`
validates `worker_capsule.json`, `LIVE_MEMORY.json`, `ALLOWED_PATHS.json`,
`events.jsonl`, and `wrapper_gate_result.json` when present.

Real Codex must write Worker Capsule stage files under `CXOR_WORKER_STAGE_DIR`.
Do not create target-root worker_stage/. If Codex writes a top-level
`worker_stage/`, `diagnose-real-codex` reports
`worker_capsule_path_violation`. This is a Codex path-obedience issue, not an
orchestrator wiring failure. Do not weaken validators.

`diagnose-real-codex` reports `patchlet_report_schema_violation` when a worker
exits successfully but the patchlet report fails schema validation. This is not
a `network_or_api_error`. Allowed report statuses are `COMPLETE`,
`VERIFIED_NO_CHANGE_NEEDED`, `BLOCKED_WITH_EVIDENCE`, and
`FAILED_WITH_EVIDENCE`; `FIXED`, `DONE`, `SUCCESS`, `PASSED`, and `OK` are
unsupported and invalid. `cleanup_proof` must be a string, not an object.
`changed_product_runtime_file`, `deterministic_run_counts`,
`before_after_state`, `row_ledger`, and `trace_ledger` are required.

Repair patchlets receive a report skeleton and must edit product/runtime files
only under `CXOR_EXECUTION_ROOT`. Product/runtime files under
`CXOR_TARGET_ROOT` are read-only to workers; only target-root evidence under
`.codex-orchestrator/` and `.artifacts/probes/` is writable.

`diagnose-real-codex` is also read-only and summarizes preserved failure
evidence before writing diagnosis artifacts. `verify-group` and
`verify-global` write matrix-backed gate artifacts before they decide
acceptance.
## P0004 Checkpoint Cleanliness And Attempt Lifecycle

`cxor validate-integration-artifacts --repo <repo>` now checks strict
checkpoint cleanliness plus structured sidecar evidence. The checkpoint field
`target_working_tree_clean_after_checkpoint` still must be `true`; it is not
weakened to allow dirty targets. Each checkpoint can include a
`target_cleanliness` summary and a sidecar
`.codex-orchestrator/integration/checkpoints/<PATCHLET>_cleanliness.json`.

The checkpoint cleanliness taxonomy separates product/runtime clean from whole
target clean. Product/runtime clean means files such as `app.py` are clean.
Whole target clean means allowed evidence directories have been accounted for
and the Target Hygiene Gate has run. `.codex-orchestrator/` and `.artifacts/`
are ignored as durable evidence directories. Python cache artifacts such as
`__pycache__/`, `*.pyc`, and `*.pyo` are evidence-recorded in
`target_hygiene_gate_result.json`; known untracked cache files may be removed
with `cache_artifacts_detected` and `cache_artifacts_removed` recorded.
Unknown dirty paths are not deleted and fail validation.

Workers run with `PYTHONDONTWRITEBYTECODE=1`, and generated prompts instruct
Codex to use `python -B` or `PYTHONDONTWRITEBYTECODE=1 python` for probes that
import target or execution code.

`run_manifest.json` records attempt lifecycle states including
`ATTEMPT_STARTED`, `WORKER_EXITED`, `REPORT_VALIDATED`,
`WRAPPER_GATE_EVALUATED`, `TARGET_HYGIENE_EVALUATED`,
`INTEGRATION_CHECKPOINT_WRITTEN`, `INTEGRATION_ARTIFACTS_VALIDATED`,
`ATTEMPT_ACCEPTED`, and `ATTEMPT_FAILED_WITH_EVIDENCE`. Operator runbook
outputs include `attempt_consistency`; validation, list, and export commands
surface runbook attempt consistency and mismatch details.

Diagnosis categories for this path include
`integration_checkpoint_target_cleanliness_error`,
`integration_artifact_validation_error`, `run_manifest_attempt_lifecycle_error`,
`runbook_attempt_evidence_mismatch`, and `target_cache_artifact_leak`.
`network_or_api_error` now requires actual external error evidence, not prompt
or metadata text alone. After a live smoke, run
`validate-real-codex-smoke-runbook`, `list-real-codex-smoke-runbooks`, and
`export-real-codex-smoke-runbook`.

## Direct Auto Operator Visibility

Use direct auto live progress for real-Codex workflows:

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

`--no-live-progress` keeps the terminal quiet. `--progress-interval-seconds`
sets heartbeat spacing. `--progress-format compact` prints concise stage-level
operator lines, and `--progress-format jsonl` prints structured events. Raw
Codex JSON and full prompt bodies are not printed by default.

Read-only second-terminal commands:

```bash
uv run --no-sync cxor monitor --repo /tmp/cxor-target --follow
uv run --no-sync cxor status --repo /tmp/cxor-target --watch
uv run --no-sync cxor status --repo /tmp/cxor-target --json
uv run --no-sync cxor prompts --repo /tmp/cxor-target --latest
uv run --no-sync cxor prompts --repo /tmp/cxor-target --show PR000001 --lines 160
```

The workflow writes `.codex-orchestrator/operator_events.jsonl`,
`.codex-orchestrator/prompt_index.json`, and
`.codex-orchestrator/loop_governor.json`. `cxor status` distinguishes
active-but-silent from likely stalled work using durable progress artifacts.
Repeated repair-loop warnings emit `loop_governor_warning`; explicit
`--loop-governor-mode safe-fail --max-repeated-failure-signature 3` stops
repeated identical failures with preserved evidence. Default tests do not run
real Codex.

## Semantic Goal Status

For structured semantic goals, `cxor status --json` includes a `semantic_goal`
object with the mode, status, criteria count, failed criteria, and latest
semantic check artifact. `cxor monitor` shows semantic events such as
`semantic_goal_check_failed` and `goal_satisfaction_gate_failed`. A prompt like
`Make app return me and prove it.` cannot reach `DONE` while `app.main()`
returns `"ok"`.

## General goal proof contract

cxor treats the master prompt as the read-only source of truth. Each workflow freezes `.codex-orchestrator/master_prompt.md`, records `.codex-orchestrator/master_prompt_frozen.json`, derives `goal_interpretation.json` without claiming proof, classifies `provability/provability_result.json` before product patchlets, and stops unsupported or ambiguous goals early with `goal_not_provable_result.json` evidence.

Required proof is represented in `proof_obligations.json` and `probe_plan.json`. Worker-proposed proof is not enough: required obligations need orchestrator-owned rerun or validation in `independent_probe_rerun_result.json`, then `goal_coverage_gate_result.json` must pass. There is no compatibility fast path for app.py, app.main, Python-specific prompts, or smoke regexes.

Final DONE requires `master_prompt_concordance_result.json` and `master_prompt_satisfaction_result.json` in addition to transaction groups, integration validation, target hygiene, and unresolved-failure checks. Partial proof is not full DONE unless explicitly allowed by policy. See `docs/general_goal_proof_contract.md`.

## Goal progress, stop, and partial apply

cxor writes `goal_progress.json` and append-only `goal_progress.jsonl`; `cxor goal-progress`, `cxor status --json`, `cxor monitor`, and `cxor auto --live-progress` expose the latest obligation counts, proof state, accepted checkpoint, and next action.

`cxor stop` writes `control/stop_requested.json`; the orchestrator stops at a safe point and writes `control/stop_result.json`. `apply-results --scope accepted --allow-partial` is required for stopped non-DONE workflows and applies only latest accepted progress. In-progress unaccepted worker changes are not applied by default. `partial_apply_result.json` records the warning that the full master prompt may not be satisfied. See `docs/goal_progress_and_partial_apply.md`.

## General Work Decomposition CLI

Use `cxor decomposition --repo <repo>` to inspect generated `impact_dependency_analysis.json`, `work_decomposition_plan.json`, `work_slices.json`, `patchlet_plan.json`, `dependency_graph.json`, and `transaction_group_plan.json`. The CLI shows that decomposition is not one file -> one patchlet; each patchlet has exactly one allowed product/runtime file, and multiple patchlets may target the same file. `--json`, `--patchlets`, and `--dependencies` expose the same contract for automation. See `docs/general_work_decomposition.md`.

## RC6 CLI Visibility

`cxor status --json`, `cxor decomposition --json`, and `cxor goal-progress --json` expose that one allowed file per patchlet is necessary but not sufficient. Same-file patchlets require a slice-level allowed-change boundary, and future slice changes are rejected even when they are inside the same allowed product/runtime file. patchlet-scoped proof runs only selected current obligations; future obligations remain unproven, not failed. PARTIAL progress accepts patchlet progress but blocks DONE. Report ingestion accepts pass: / fail: / blocked: descriptive prefixes. Artifact directories are allowed only under approved roots.
