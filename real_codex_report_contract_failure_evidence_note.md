# Real Codex Report Contract Failure Evidence Note

## 1. latest bundle path

`.operator-runs/real-codex-smoke/2026-07-03T12-13-30-real-codex-smoke`

## 2. validation result path

`.operator-runs/real-codex-smoke/2026-07-03T12-13-30-real-codex-smoke/validation_result.json`

Standalone validation command:

```bash
uv run --no-sync cxor validate-real-codex-smoke-runbook --run-dir .operator-runs/real-codex-smoke/2026-07-03T12-13-30-real-codex-smoke
```

Result: `valid=true`.

## 3. export archive path

`.operator-runs/exports/2026-07-03T12-13-30-real-codex-smoke.zip`

## 4. export manifest path

`.operator-runs/exports/2026-07-03T12-13-30-real-codex-smoke.zip.manifest.json`

## 5. explicit_smoke outcome

`safe_failure`

## 6. diagnosis_primary_category

`network_or_api_error`

This category is misleading for this run because the stronger structured evidence is a patchlet report schema validation failure after the Codex subprocess exited `0`.

## 7. parsed attempt_id

`P0003_attempt1`

## 8. parsed error_type

`WorkerPreconditionError`

## 9. parsed error_message

`Worktree execution requires a clean target repo; dirty paths: app.py`

## 10. report_valid value

`false`

## 11. report_validation reason

`'changed_product_runtime_file' is a required property; 'deterministic_run_counts' is a required property; 'before_after_state' is a required property; 'row_ledger' is a required property; 'trace_ledger' is a required property; {'cleanup_passed': True, 'temp_data_removed': True} is not of type 'string'; 'FIXED' is not one of ['COMPLETE', 'VERIFIED_NO_CHANGE_NEEDED', 'BLOCKED_WITH_EVIDENCE', 'FAILED_WITH_EVIDENCE']`

## 12. whether contract_injected was true or false

`false`

The latest smoke result shows the repair attempt prompt did not include the real-Codex patchlet contract template.

## 13. whether target-root app.py became dirty

Yes. The linked temp target repository still existed during inspection:

`/tmp/pytest-of-theyeq-admin-lap/pytest-436/test_real_codex_auto_worktree_0/target`

`git status --short` showed:

```text
 M app.py
?? .artifacts/
?? .codex-orchestrator/
```

## 14. whether forbidden target/worker_stage existed

No. Inspection of the linked temp target showed `target/worker_stage/` was absent.

## 15. exact next implementation target

Classify structured report validation failures as `patchlet_report_schema_violation`, make that diagnosis outrank generic network/API output text, inject the real-Codex report contract into repair patchlet prompts, add an explicit local Worker Capsule report schema contract artifact, and reproduce the invalid `FIXED`/object `cleanup_proof` report deterministically with fake Codex.
