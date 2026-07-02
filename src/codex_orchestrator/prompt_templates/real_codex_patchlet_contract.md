# Real Codex Patchlet Contract

Use this contract when running a patchlet through `worker_mode=real_codex`,
especially in `auto --use-worktree` smoke and operator debugging flows.

## Environment Contract

The orchestrator provides these `CXOR_` paths and identifiers:

- `CXOR_TARGET_ROOT`
- `CXOR_EXECUTION_ROOT`
- `CXOR_ARTIFACT_ROOT`
- `CXOR_WORKFLOW_DIR`
- `CXOR_PROBE_DIR`
- `CXOR_REPORTS_DIR`
- `CXOR_RUNS_DIR`
- `CXOR_RUN_DIR`
- `CXOR_PATCHLET_ID`
- `CXOR_ATTEMPT_ID`
- `CXOR_ALLOWED_PRODUCT_RUNTIME_FILE`
- `CXOR_REPORT_PATH`
- `CXOR_PROBE_ROOT`

Treat `CXOR_EXECUTION_ROOT` as the only place where product/runtime file edits
may occur. Treat `CXOR_ARTIFACT_ROOT` as the only place where orchestrator
artifacts must be written.

Do not write report or probe artifacts into the worktree if
`CXOR_EXECUTION_ROOT` differs from `CXOR_ARTIFACT_ROOT`.

## Allowed Edit Scope

Only change the allowed product/runtime file identified by
`CXOR_ALLOWED_PRODUCT_RUNTIME_FILE`.

Do not change any other product/runtime file.

Do not invent extra artifact locations outside:

- `CXOR_REPORTS_DIR`
- `CXOR_RUNS_DIR`
- `CXOR_PROBE_DIR`

## Required Report Output

Write a valid patchlet report JSON to `CXOR_REPORT_PATH`.

The report must include at least:

- `schema_version`
- `kind`
- `patchlet_id`
- `status`
- `changed_product_runtime_file` for `COMPLETE`
- `changed_artifact_files`
- `probe_commands`
- `deterministic_run_counts`
- `root_cause_classification`
- `before_after_state`
- `cleanup_proof`
- `probe_artifact_refs`
- `acceptance_criteria_result`

`probe_artifact_refs` must reference the durable probe run written under
`CXOR_PROBE_ROOT`.

## Required Durable Probe Files

Write these durable probe artifacts:

- `CXOR_PROBE_ROOT/probe.py`
- `CXOR_PROBE_ROOT/run_001/row_ledger.jsonl`
- `CXOR_PROBE_ROOT/run_001/trace_ledger.jsonl`
- `CXOR_PROBE_ROOT/run_001/before_state.json`
- `CXOR_PROBE_ROOT/run_001/after_state.json`
- `CXOR_PROBE_ROOT/run_001/cleanup_proof.json`

The report must include `probe_artifact_refs` pointing at that probe root and
run id.

## Required Investigation Content

For `COMPLETE`, include:

- deterministic baseline run counts
- deterministic proof-of-fix run counts
- deterministic negative controls
- recursive why audit fields
- producer/transformer/consumer boundary evidence
- cleanup proof

Do not claim the issue is transient.
Do not claim the issue is flaky.
Do not use blind retry.
Do not say rerun fixed it.

The orchestrator validators are strict. Do not weaken the report or omit the
durable probe files to make the run appear successful.
