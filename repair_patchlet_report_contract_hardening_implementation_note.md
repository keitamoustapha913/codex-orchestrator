# Repair Patchlet Report Contract Hardening Implementation Note

## Preflight Findings

Baseline before implementation was `709 passed, 2 skipped`. The live evidence bundle validates and exports. The repo had no source changes before this increment other than local notes added during evidence preservation.

## Latest Live Run Evidence

The latest real-Codex operator run launched Codex, produced live progress, completed multiple attempts, and safe-failed with preserved evidence.

## Latest Bundle Path

`.operator-runs/real-codex-smoke/2026-07-03T12-13-30-real-codex-smoke`

## Latest Bundle Validation Result

`cxor validate-real-codex-smoke-runbook` returned `valid=true`.

## Latest Bundle Export Result

`cxor export-real-codex-smoke-runbook` produced `.operator-runs/exports/2026-07-03T12-13-30-real-codex-smoke.zip` and `.operator-runs/exports/2026-07-03T12-13-30-real-codex-smoke.zip.manifest.json`.

## Observed Misdiagnosis

The copied diagnosis classified the run as `network_or_api_error`, but the structured run manifest shows a report schema validation failure after a worker exit code of `0`.

## Observed Report Validation Error

The report validation reason names missing required fields, an unsupported `FIXED` status, and an object-valued `cleanup_proof` where the schema requires a string.

## Observed Unsupported Status

`FIXED` appeared in the worker report and was correctly rejected by the report schema.

## Observed cleanup_proof Type Error

`cleanup_proof` was an object with cleanup flags. The report schema requires a string.

## Observed Missing Required Report Fields

The live validation reason named missing `changed_product_runtime_file`, `deterministic_run_counts`, `before_after_state`, `row_ledger`, and `trace_ledger`.

## Observed contract_injected Value

`contract_injected=false` for the repair attempt.

## Observed Target Dirty Path

The linked temp target showed `app.py` dirty after the safe failure.

## Existing Report Schema Contract

`patchlet_report.schema.json` permits only `COMPLETE`, `VERIFIED_NO_CHANGE_NEEDED`, `BLOCKED_WITH_EVIDENCE`, and `FAILED_WITH_EVIDENCE`. It requires `cleanup_proof` to be a string and requires the missing live-run fields.

## Existing Report Validator Behavior

`validate_patchlet_report_file` already rejects the malformed report. The validator should remain strict.

## Existing Real-Codex Prompt Contract

Initial compiled patchlets can include `real_codex_patchlet_contract.md` when `CXOR_REAL_CODEX_CONTRACT_PATH` is set. The contract currently has a valid example, but repair patchlet regeneration does not include it.

## Existing Worker Capsule Memory Contract

Worker Capsule memory records the task, live memory, allowed paths, stage files, and time budget. It does not yet include a dedicated report schema contract artifact.

## Existing Diagnosis Precedence

Diagnosis checks capsule path violations, target-dirty integration apply, timeout evidence, auth/CLI/network/permission text, then unknown. It currently has no report schema violation category, so incidental network/API text can mask the structured report validation failure.

## Existing Fake-Codex Test Pattern

Existing tests use fake `codex` binaries via `CXOR_CODEX_BINARY`/`PATH`, temp target repos, generated run manifests, and artifact inspection. The invalid-report reproduction can use the same path without invoking real Codex.

## Implementation Plan

1. Add diagnosis tests for `patchlet_report_schema_violation`.
2. Add diagnosis classifier before generic output-text classification.
3. Harden generated real-Codex prompt and repair-patchlet prompt contract.
4. Add execution-root vs target-root edit instructions to prompt and Worker Capsule memory.
5. Add `REPORT_SCHEMA_CONTRACT.md` to Worker Capsule memory and reference it.
6. Add deterministic fake-Codex invalid report reproduction.
7. Update docs and run final verification.

## Risks and Stop Conditions

Do not add `FIXED` as an allowed status. Do not relax `cleanup_proof`. Do not hide `report_valid=false`. Do not classify structured report validation as network/API. Do not make default tests invoke real Codex.
