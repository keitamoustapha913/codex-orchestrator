# Codex Orchestrator TDD Implementation Status

## Scope implemented in this MVP

This source tree implements the first practical TDD slice of the Codex Orchestrator autonomous root-cause probe-gated loop.

Local development baseline: `uv` + Python 3.10.

Implemented capabilities:

- standalone installable Python package named `codex-orchestrator`;
- console scripts: `cxor` and `codex-orchestrator`;
- `python -m codex_orchestrator` module entrypoint;
- target repository resolver using `--repo` or current Git-root discovery;
- target-local artifact creation under `.codex-orchestrator/` and `.artifacts/probes/`;
- target-local config, state, run manifest, census directories, patchlet directories, report directories, failure directories, repair-plan directories, and final verification artifacts;
- self-target safety guard for the orchestrator source repository;
- atomic JSON state writes;
- state schema validation;
- deterministic census with command metadata and tool availability recording;
- deterministic placeholder stages for goal normalization, evidence classification, inventory graph generation, invariant extraction, and patchlet compilation;
- root-cause patchlet subprompt generation with the `ROOT-CAUSE PROBE-ONLY INVESTIGATION` gate;
- mock worker adapter for TDD and orchestration tests without real Codex calls;
- real Codex worker adapter scaffold using `codex exec --json`;
- manual and CI-only worker modes as scaffolds;
- target-repo diff guard enforcing one allowed product/runtime file and approved artifact directories;
- patchlet report validator enforcing explicit statuses and root-cause/proof fields;
- patchlet executor with run records, reports, diff capture, and failure record creation;
- transaction-group verifier with durable pass/fail state and failure evidence;
- global verifier that marks `DONE` only when patchlet reports validate, transaction groups pass, invariants are proven, and unresolved failures are absent;
- failure classification, repair planning, and repair application scaffolds;
- repair application artifacts and repair patchlet regeneration without blind retry;
- idempotent replay for `cxor apply-repair`, `cxor regenerate-patchlets`, and `cxor auto --resume --until DONE` when durable repair artifacts already exist;
- terminal `DONE` guards for `cxor apply-repair` and `cxor regenerate-patchlets` so post-completion repair commands are explicit no-op operations;
- advanced repair classifications for inside-known-graph, outside-known-graph, inventory contradiction, repeated repair failure, master-goal change, and excessive impacted scope;
- durable rediscovery records and inventory rebuild routing;
- optional worktree execution with validated merge and unauthorized diff isolation;
- `cxor auto --use-worktree` routing through the validated worktree patchlet execution path;
- opt-in `real_codex` smoke harness for `cxor auto --use-worktree`;
- read-only capsule inspection, validation, and real-Codex diagnosis commands;
- matrix-backed transaction-group and global verification artifacts;
- `cxor auto` mock-mode autonomous loop that initializes, discovers, compiles, runs, verifies, and reaches `DONE`.

## TDD status

The test suite was written before/alongside implementation and currently passes:

```text
448 passed, 2 skipped
```

Covered tests:

- target repo resolution from explicit repo, nested path, current working directory, non-git override, and self-target guard;
- target artifact initialization and no source-copy leakage into target repos;
- state file validation and atomic save behavior;
- diff guard acceptance/rejection behavior;
- patchlet report validation acceptance/rejection behavior;
- deterministic census outputs and command metadata;
- goal normalization output;
- patchlet compilation output and root-cause prompt gate;
- mock patchlet execution and state updates;
- transaction group verification;
- global verification to `DONE`;
- autonomous mock loop to `DONE`;
- advanced repair classification and rediscovery flows;
- optional worktree execution and validated merge;
- CLI invocation from outside the source tree using module entrypoint.

## Current limitations

This is not the full final orchestrator. The following are intentionally still scaffolds or deterministic MVP placeholders:

- Codex-driven semantic classification is not yet implemented beyond the adapter scaffold.
- Evidence classification, inventory graph construction, invariant extraction, and patchlet compilation are deterministic placeholder implementations.
- Repair planning records structured intent but does not yet synthesize enriched repair patchlets automatically.
- CI/documentation contract coverage still needs expansion around all newly added commands and worker modes.
- Root-cause validation is strict for report fields but does not yet perform secondary model/human semantic verification.
- Real Codex success remains model- and environment-dependent, so the smoke accepts contained safe failure as long as validators remain strict and evidence is preserved.

## Current command surface

Notable verified commands now include:

```bash
cxor verify-group --repo /path/to/target-repo TG001
cxor verify-all-groups --repo /path/to/target-repo
cxor verify-global --repo /path/to/target-repo
cxor rediscover --repo /path/to/target-repo --scope impacted
cxor rebuild-inventory --repo /path/to/target-repo --scope impacted
cxor run-next --repo /path/to/target-repo --worker-mode mock --use-worktree
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode mock --use-worktree
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py --run-real-codex -s
cxor inspect-capsule --repo /path/to/target-repo --attempt P0001_attempt1
cxor validate-capsule --repo /path/to/target-repo --attempt P0001_attempt1
cxor diagnose-real-codex --repo /path/to/target-repo --attempt P0001_attempt1
cxor real-codex-smoke-runbook --dry-run
CODEX_PATCHLET_TIMEOUT_SECONDS=600 cxor real-codex-smoke-runbook --run-real-codex
```

`No blind retry` remains a required contract.

The default suite does not run real Codex. Do not weaken validators for real Codex smoke runs. Inspect `.codex-orchestrator/runs/`, `.codex-orchestrator/failures/`, and `.artifacts/probes/` after each opt-in real_codex smoke run.

Fake-success parity now proves the exact `worker_mode=real_codex` +
`auto --use-worktree` wiring to `DONE` with a fake Codex binary that writes a
valid report and durable probe artifacts. Real Codex success to DONE remains
dependent on actual Codex output quality and is not guaranteed.

Use `src/codex_orchestrator/prompt_templates/real_codex_patchlet_contract.md`
as the operator-facing patchlet contract for required paths, report fields, and
durable probe files.

For the opt-in smoke, that contract is injected into the generated prompt
artifact under `.codex-orchestrator/subprompts/` so the installed Codex binary
receives the same path contract already proven by fake-success parity. The
template now includes a minimal valid report example for `CXOR_REPORT_PATH` and
a minimal durable probe example rooted at `CXOR_PROBE_ROOT`.

When a real/non-mock worker exits non-zero, `run_manifest.json` should retain a `WORKER_FAILED` patchlet run entry together with preserved `stdout.txt`, `stderr.txt`, `command.json`, and `output.jsonl` artifact paths. Blind retry is not allowed.

Real-Codex patchlet timeout defaults to 10 minutes / 600 seconds.
`CODEX_TIMEOUT_SECONDS` overrides the global timeout, and
`CODEX_PATCHLET_TIMEOUT_SECONDS` overrides patchlet execution. The patchlet
sees `CXOR_TIMEOUT_SECONDS` and `CXOR_SOFT_DEADLINE_SECONDS`, and the generated
Worker Capsule/subprompt tells it to write `worker_stage/05_final_report.md`
with BLOCKED or FAILED status before timeout if it cannot finish.

Invalid timeout env values are structured errors before Codex launches.
`CODEX_TIMEOUT_SECONDS`, `CODEX_PATCHLET_TIMEOUT_SECONDS`, and
`CODEX_PROGRESS_INTERVAL_SECONDS` must be positive integer seconds. The error
includes the env var name, the bad value, and `expected positive integer
seconds`.

Real-Codex attempts write compact liveness events to `progress.jsonl`. This is
not success evidence. Timeout safe-failure preserves evidence and containment;
it is not task success and not `DONE`.

Diagnosis classifies command/run-manifest evidence with `timed_out=true` and
`exit_code=124` as `orchestrator_subprocess_timeout`. The category documents
bounded containment, not task success, and links `progress.jsonl` when present.

The explicit real-Codex smoke remains an operator-run command, not part of the
default test suite.

The operator-controlled smoke runbook writes timestamped artifacts under
`.operator-runs/real-codex-smoke/<timestamp>-real-codex-smoke/`, including
`selected_policy.json`, `result.json`, `diagnosis_paths.json`,
`explicit_smoke_stdout.txt`, and `explicit_smoke_stderr.txt`. Dry-run mode does
not invoke real Codex and records outcome dry_run. Explicit mode may consume
account, network, model, token, and wall-clock resources up to
`CODEX_PATCHLET_TIMEOUT_SECONDS`. Compare runs by diffing
`selected_policy.json`, `result.json`, and `diagnosis_paths.json`.
`safe_failure is a successful runbook capture`, not task DONE; `DONE means the
orchestrator validators accepted the run`.

Patchlet Codex defaults to `gpt-5.4-mini` with reasoning `medium`.
Non-patchlet/orchestrator Codex profiles default to `gpt-5.5` with reasoning
`medium`.

Use `cxor diagnose-real-codex --repo /path/to/target-repo --attempt P0001_attempt1`
to summarize preserved `stdout.txt`, `stderr.txt`, `output.jsonl`,
`command.json`, `run_manifest.json`, and generated prompt artifacts into:

- generic artifact kinds: `real_codex_failure_diagnosis.json` and `real_codex_failure_diagnosis.md`
- `.codex-orchestrator/diagnostics/real_codex/P0001_attempt1_diagnosis.json`
- `.codex-orchestrator/diagnostics/real_codex/P0001_attempt1_diagnosis.md`

This diagnosis is read-only, does not run Codex, does not weaken validators,
and must fall back to `unknown_codex_nonzero_exit` when the artifacts do not
support a narrower cause.

## Verified commands

The following commands were verified after editable install:

```bash
cxor --version
codex-orchestrator --version
python -m codex_orchestrator --version
pytest -q
```

## Worker Capsule evidence layer

Implemented and covered:

- per-attempt `worker_capsule.json`
- per-attempt `worker_memory/` and `worker_stage/`
- append-only `worker_hooks/events.jsonl`
- orchestrator-owned `gates/wrapper_gate_result.json`
- transaction `patchlet_output_matrix.json`
- global `verification_matrix.json`
- global `global_gate_result.json`
- read-only `cxor inspect-capsule`
- read-only `cxor validate-capsule`
- read-only `cxor diagnose-real-codex`

Memory is context, not proof. The orchestrator writes gate results.

Real Codex must write Worker Capsule stage files under `CXOR_WORKER_STAGE_DIR`
and the exact `CXOR_PREFLIGHT_PATH` / `CXOR_FINAL_REPORT_PATH` values. Do not
create target-root worker_stage/. A top-level `worker_stage/` is diagnosed as
`worker_capsule_path_violation`. This is a Codex path-obedience issue, not
orchestrator wiring failure. Do not weaken validators.

Implemented: real-Codex report contract hardening. If a worker exits `0` but
the patchlet report fails schema validation, diagnosis reports
`patchlet_report_schema_violation`, not `network_or_api_error`. Allowed report
statuses remain `COMPLETE`, `VERIFIED_NO_CHANGE_NEEDED`,
`BLOCKED_WITH_EVIDENCE`, and `FAILED_WITH_EVIDENCE`; `FIXED`, `DONE`,
`SUCCESS`, `PASSED`, and `OK` are invalid. `cleanup_proof` must be a string,
and required fields such as `changed_product_runtime_file`,
`deterministic_run_counts`, `before_after_state`, `row_ledger`, and
`trace_ledger` must exist. Repair patchlets receive a report skeleton and the
same contract. Product/runtime edits are restricted to `CXOR_EXECUTION_ROOT`;
product/runtime files under `CXOR_TARGET_ROOT` are read-only to Codex workers.

Implemented: verified-no-change wrapper gate and transaction-group repair
routing hardening. The final Markdown report must contain a standalone
canonical marker line: `FINAL_STATUS: PASS`, `FINAL_STATUS: BLOCKED`, or
`FINAL_STATUS: FAILED`. Non-canonical forms such as
`Marker: `FINAL_STATUS: PASS`` and backticked markers are rejected with
`wrapper_gate_final_status_marker_error`; a valid report JSON alone does not
bypass the wrapper gate, and `network_or_api_error` does not mask structured
gate or routing failures. Transaction group ids such as `TG001` are not
patchlet ids. Transaction-group failure records preserve
`source_type: transaction_group` and member `source_patchlet_ids`; regeneration
expands those members and reports `transaction_group_source_mapping_missing`
when mapping is unavailable.

## Live Progress And Integration State

Implemented: compact live progress lines (`[cxor:<attempt> +004s] codex:
thread.started`) with `CXOR_LIVE_CODEX_PROGRESS=0` disable support. Durable
liveness remains `progress.jsonl`; live progress and safe failure are not DONE.

Implemented: accepted changes advance `refs/cxor/runs/<run_id>/integration`,
the target repo remains clean between patchlets, worktrees start from the
integration SHA, and final verification writes
`.codex-orchestrator/integration/final_diff.patch`.

Implemented: explicit finalization through `cxor apply-results --mode patch`,
`cxor apply-results --mode branch`, and `cxor apply-results --mode
working-tree`.

Implemented: schema validation for integration artifacts.
`integration_state.json` uses `integration_state.schema.json`,
`accepted_changes.jsonl` entries validate line-by-line with
`accepted_change.schema.json`, checkpoint files use
`integration_checkpoint.schema.json`, and apply-results outputs such as
`patch_result.json` use `apply_results_result.schema.json`. Operators can run
`cxor validate-integration-artifacts --repo /path/to/target-repo`; the command
is read-only and does not run Codex.

Implemented: schema validation for operator-run real-Codex smoke bundles.
`selected_policy.json` uses `real_codex_smoke_selected_policy.schema.json`,
`result.json` uses `real_codex_smoke_operator_result.schema.json`,
`diagnosis_paths.json` uses `real_codex_smoke_diagnosis_paths.schema.json`,
and `validation_result.json` uses
`real_codex_smoke_runbook_validation.schema.json`. Operators can run
`cxor validate-real-codex-smoke-runbook --run-dir .operator-runs/real-codex-smoke/<timestamp>-real-codex-smoke`;
the command is read-only, does not run Codex, and does not run pytest.

Implemented: read-only listing for local real-Codex smoke runbook bundles.
`cxor list-real-codex-smoke-runbooks` prints a compact table. `--json` prints
structured summaries. `--root`, `--latest`, `--only-invalid`, and `--limit`
control the scan. The command is read-only, does not run Codex, does not run
pytest, summarizes outcome/model/reasoning/timeout/diagnosis/validation paths,
and invalid bundles are listed rather than hidden. Use
`cxor validate-real-codex-smoke-runbook --run-dir <dir>` for one bundle.

Implemented: export packaging for operator-run real-Codex smoke bundles.
`cxor export-real-codex-smoke-runbook --run-dir <bundle>` writes a zip archive
under `.operator-runs/exports/` by default and writes a sidecar manifest with
relative paths, sizes, and sha256 hashes. The command validates first, refuses
invalid bundles unless `--force` is passed, does not mutate the source bundle,
does not run Codex, and does not run pytest.

Release checklist documentation is in `docs/release.md`. The normal command is
`cxor auto --repo <repo> --master <prompt> --until DONE`; mock mode is
deterministic and CI-safe; real Codex is opt-in only; the integration ref keeps
the target clean between patchlets; and apply-results is explicit finalization.

Implemented: P0004 checkpoint cleanliness, manifest lifecycle, and diagnosis
correctness hardening. Checkpoint cleanliness now has a checkpoint cleanliness
taxonomy: `product_runtime_clean`, `artifact_dirs_ignored`,
`cache_artifacts_detected`, `cache_artifacts_removed`, `unknown_dirty_paths`,
and `whole_repo_clean_after_hygiene`. `target_working_tree_clean_after_checkpoint`
remains strict and must be true. Product/runtime clean is distinct from whole
target clean; `.codex-orchestrator/` and `.artifacts/` are evidence
directories, while `__pycache__/`, `*.pyc`, and `*.pyo` are evidence-recorded
and safely remediated only when known untracked cache artifacts. Unknown dirty
paths are not deleted.

Implemented: Target Hygiene Gate writes `target_hygiene_gate_result.json`,
records cache evidence and `cache_artifacts_removed`, and prevents silent
cleanup. Real-Codex worker environments set `PYTHONDONTWRITEBYTECODE=1`; worker
capsule and prompt instructions require `python -B` or
`PYTHONDONTWRITEBYTECODE=1 python` for probes that import target or execution
code.

Implemented: integration checkpoints include `target_cleanliness` and reference
`.codex-orchestrator/integration/checkpoints/<PATCHLET>_cleanliness.json`.
Run manifests now preserve attempt lifecycle states: `ATTEMPT_STARTED`,
`WORKER_EXITED`, `REPORT_VALIDATED`, `WRAPPER_GATE_EVALUATED`,
`TARGET_HYGIENE_EVALUATED`, `INTEGRATION_CHECKPOINT_WRITTEN`,
`INTEGRATION_ARTIFACTS_VALIDATED`, `ATTEMPT_ACCEPTED`, and
`ATTEMPT_FAILED_WITH_EVIDENCE`.

Implemented: operator-run bundles record runbook attempt consistency through
`attempt_consistency`; validate/list/export expose mismatch evidence.
Structured diagnoses include `integration_checkpoint_target_cleanliness_error`,
`integration_artifact_validation_error`, `run_manifest_attempt_lifecycle_error`,
`runbook_attempt_evidence_mismatch`, and `target_cache_artifact_leak`.
`network_or_api_error` now requires actual external error evidence.
