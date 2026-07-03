# Real Codex TG001 Routing Failure Evidence Note

## 1. latest bundle path

`.operator-runs/real-codex-smoke/2026-07-03T15-05-27-real-codex-smoke`

## 2. validation result

`cxor validate-real-codex-smoke-runbook` returned `valid=true`, `errors=[]`, `warnings=[]`.

## 3. export archive path

`.operator-runs/exports/2026-07-03T15-05-27-real-codex-smoke.zip`

## 4. export manifest path

`.operator-runs/exports/2026-07-03T15-05-27-real-codex-smoke.zip.manifest.json`

## 5. explicit_smoke outcome

`safe_failure`

## 6. diagnosis_primary_category

`network_or_api_error`

This is misleading for the observed chain because structured wrapper-gate and transaction-group routing evidence exists.

## 7. error_type

`StagePreconditionError`

## 8. error_message

`precondition failed for regenerate-patchlets: missing source patchlet manifest for TG001; current stage=PATCHLET_REGENERATION_REQUIRED; target repo=/tmp/pytest-of-theyeq-admin-lap/pytest-449/test_real_codex_auto_worktree_0/target`

## 9. attempt_id

`P0001_attempt1`

## 10. patchlet_id

`P0001`

## 11. report_valid

`true`

## 12. report_status

`VERIFIED_NO_CHANGE_NEEDED`

## 13. contract_injected

`true`

## 14. exact contents of 05_final_report.md marker line

`Marker: \`FINAL_STATUS: PASS\``

## 15. wrapper_gate_result.json accepted value

`false`

## 16. wrapper_gate_result.json final_status_gate value

`missing`

## 17. wrapper_gate_result.json reasons

`missing worker_stage/05_final_report.md FINAL_STATUS marker`

## 18. transaction group id involved

`TG001`

## 19. transaction group member patchlet ids

`["P0001"]`

## 20. failure record source_id and source type if present

`source_id`: `TG001`

`source_type`: not found in preserved evidence.

`source_patchlet_ids`: not found in preserved evidence.

## 21. repair plan source_failure_ids

`["F0001"]`

## 22. regeneration source id that became TG001

`F0001.source_id` was `TG001`, and `regenerate-patchlets` treated that value as a patchlet id.

## 23. whether any product/runtime file was dirty

No. Target git status only showed:

```text
?? .artifacts/
?? .codex-orchestrator/
```

## 24. whether forbidden target/worker_stage existed

No. `target/worker_stage/` did not exist.

## 25. exact full-chain hypothesis to reproduce

Fake Codex should produce a schema-valid `P0001` report with status `VERIFIED_NO_CHANGE_NEEDED`, keep `app.py` clean, and write `05_final_report.md` with non-canonical marker text `Marker: \`FINAL_STATUS: PASS\``. The wrapper gate should reject this precisely as a non-canonical final status marker. The transaction group failure should preserve `source_type=transaction_group`, `source_id=TG001`, and `source_patchlet_ids=["P0001"]`. Regeneration must not look for patchlet `TG001`; it must either map the transaction group to member patchlets or fail with a structured transaction-group mapping error. Diagnosis must not classify this chain as `network_or_api_error`.
