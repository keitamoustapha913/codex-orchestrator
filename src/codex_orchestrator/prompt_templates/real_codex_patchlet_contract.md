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
- `CXOR_WORKER_STAGE_DIR`
- `CXOR_WORKER_MEMORY_DIR`
- `CXOR_WORKER_HOOKS_DIR`
- `CXOR_GATES_DIR`
- `CXOR_DIAGNOSTICS_DIR`
- `CXOR_PREFLIGHT_PATH`
- `CXOR_FINAL_REPORT_PATH`
- `CXOR_PATCHLET_ID`
- `CXOR_ATTEMPT_ID`
- `CXOR_TIMEOUT_SECONDS`
- `CXOR_SOFT_DEADLINE_SECONDS`
- `CXOR_ALLOWED_PRODUCT_RUNTIME_FILE`
- `CXOR_REPORT_PATH`
- `CXOR_PROBE_ROOT`

Treat `CXOR_EXECUTION_ROOT` as the only place where product/runtime file edits
may occur. Treat `CXOR_ARTIFACT_ROOT` as the only place where orchestrator
artifacts must be written.

Do not write report or probe artifacts into the worktree if
`CXOR_EXECUTION_ROOT` differs from `CXOR_ARTIFACT_ROOT`.

Worker Capsule files must use the exact capsule paths. Write preflight stage
content only to `CXOR_PREFLIGHT_PATH` and final stage content only to
`CXOR_FINAL_REPORT_PATH`. These paths are under `CXOR_WORKER_STAGE_DIR`, for
example `.codex-orchestrator/runs/P0001_attempt1/worker_stage/`.

Do not create target-root worker_stage/. Do not write `worker_stage/` relative
to `CXOR_TARGET_ROOT` or the current shell directory.

## Wall-clock Budget

You have a hard timeout of 600 seconds by default. The exact timeout is exposed
as `CXOR_TIMEOUT_SECONDS`, and the soft deadline is exposed as
`CXOR_SOFT_DEADLINE_SECONDS`.

Aim to finish by 540 seconds for the default budget. If you cannot complete,
write `CXOR_FINAL_REPORT_PATH` with an explicit BLOCKED or FAILED status and
preserve what you learned before the timeout. Do not keep
investigating indefinitely. Do not use blind retry.

## Allowed Edit Scope

Only change the allowed product/runtime file identified by
`CXOR_ALLOWED_PRODUCT_RUNTIME_FILE`.

Do not change any other product/runtime file.

Do not invent extra artifact locations outside:

- `CXOR_REPORTS_DIR`
- `CXOR_RUNS_DIR`
- `CXOR_PROBE_DIR`
- `CXOR_WORKER_STAGE_DIR`

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

## Minimal Valid COMPLETE Example

Write the report JSON to `CXOR_REPORT_PATH`. A minimal valid shape is:

```json
{
  "schema_version": "1.0",
  "kind": "patchlet_report",
  "patchlet_id": "P0001",
  "status": "COMPLETE",
  "changed_product_runtime_file": "app.py",
  "changed_artifact_files": [
    ".artifacts/probes/P0001/probe.py",
    ".artifacts/probes/P0001/run_001/row_ledger.jsonl",
    ".artifacts/probes/P0001/run_001/trace_ledger.jsonl",
    ".artifacts/probes/P0001/run_001/before_state.json",
    ".artifacts/probes/P0001/run_001/after_state.json",
    ".artifacts/probes/P0001/run_001/cleanup_proof.json"
  ],
  "probe_commands": ["python .artifacts/probes/P0001/probe.py"],
  "deterministic_run_counts": {
    "baseline": "5/5",
    "proof_of_fix": "5/5",
    "negative_controls": "5/5"
  },
  "root_cause_classification": {
    "observed_failure": "baseline failed before the allowed change",
    "immediate_cause": "the allowed file lacked the required behavior",
    "why_immediate_cause_happened": "the behavior was not implemented correctly",
    "deeper_owner_boundary": "app.py",
    "producer_transformer_consumer_boundary": "producer app.py -> consumer probe",
    "not_downstream_of_unprobed_state_proof": "the direct probe ran against the changed boundary",
    "negative_control_proof": "adjacent paths remained unchanged",
    "recursive_why_audit": ["why1", "why2", "why3"]
  },
  "before_after_state": [{"before": "old", "after": "new"}],
  "row_ledger": [],
  "trace_ledger": [],
  "cleanup_proof": "probe created isolated temp data and cleaned it",
  "proof_of_fix": {
    "summary": "direct probe passed after the allowed change",
    "deterministic_run_count": "5/5"
  },
  "probe_artifact_refs": [{
    "patchlet_id": "P0001",
    "probe_root": ".artifacts/probes/P0001",
    "run_id": "run_001"
  }],
  "acceptance_criteria_result": "pass"
}
```

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

Minimal probe file examples:

`CXOR_PROBE_ROOT/run_001/row_ledger.jsonl`

```json
{"row": 1}
```

`CXOR_PROBE_ROOT/run_001/trace_ledger.jsonl`

```json
{"trace": 1}
```

`CXOR_PROBE_ROOT/run_001/before_state.json`

```json
{"value": "before"}
```

`CXOR_PROBE_ROOT/run_001/after_state.json`

```json
{"value": "after"}
```

`CXOR_PROBE_ROOT/run_001/cleanup_proof.json`

```json
{"cleanup_passed": true}
```

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
Do not invent alternate paths.

The orchestrator validators are strict. Do not weaken the report or omit the
durable probe files to make the run appear successful.
