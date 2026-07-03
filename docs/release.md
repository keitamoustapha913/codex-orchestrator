# Release checklist

Use this checklist before tagging a release candidate.

Normal deterministic command:

```bash
cxor auto --repo <repo> --master <prompt> --until DONE
```

mock mode is deterministic and CI-safe:

```bash
uv run --no-sync pytest -q
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py
```

The default suite and default smoke check do not run real Codex. real Codex is
opt-in only.

Version and packaging checks:

```bash
uv run --no-sync python -m codex_orchestrator --version
uv run --no-sync cxor --version
uv run --no-sync codex-orchestrator --version
```

Integration safety checks:

```bash
cxor validate-integration-artifacts --repo <repo>
```

The integration ref keeps the target clean between patchlets. Accepted patchlet
changes advance `refs/cxor/runs/<run_id>/integration`; target product/runtime
files are not dirtied between accepted patchlets.

apply-results is explicit finalization:

```bash
cxor apply-results --repo <repo> --mode patch
cxor apply-results --repo <repo> --mode branch
cxor apply-results --repo <repo> --mode working-tree
```

Patch mode writes a final diff without mutating product files. Branch mode
creates a result branch without checkout. Working-tree mode requires a clean
target and mutates only after explicit operator request.

Operator-run real-Codex evidence flow:

```bash
cxor real-codex-smoke-runbook --dry-run
cxor validate-real-codex-smoke-runbook --run-dir <bundle>
cxor list-real-codex-smoke-runbooks
cxor export-real-codex-smoke-runbook --run-dir <bundle>
```

`cxor export-real-codex-smoke-runbook --run-dir <bundle>` packages one
validated bundle into `.operator-runs/exports/<bundle>.zip` and writes a
sidecar `.manifest.json` containing relative file paths, sizes, and sha256
hashes. Invalid bundles are refused unless `--force` is provided. The export
command is read-only for the source bundle, does not run Codex, and does not
run pytest.

Live real-Codex release evidence is operator-gated:

```bash
CODEX_PATCHLET_TIMEOUT_SECONDS=600 \
uv run --no-sync cxor real-codex-smoke-runbook --run-real-codex --live-progress

uv run --no-sync cxor list-real-codex-smoke-runbooks --latest --json
uv run --no-sync cxor validate-real-codex-smoke-runbook --run-dir <latest_bundle>
uv run --no-sync cxor export-real-codex-smoke-runbook --run-dir <latest_bundle>
```

`safe_failure` is evidence capture, not DONE. DONE means the orchestrator
validators accepted the run.

When a live run safe-fails with `patchlet_report_schema_violation`, treat it as
a report contract failure, not a `network_or_api_error`. The only allowed
patchlet report statuses are `COMPLETE`, `VERIFIED_NO_CHANGE_NEEDED`,
`BLOCKED_WITH_EVIDENCE`, and `FAILED_WITH_EVIDENCE`; `FIXED`, `DONE`,
`SUCCESS`, `PASSED`, and `OK` are invalid. `cleanup_proof` must be a string,
not an object. `changed_product_runtime_file`, `deterministic_run_counts`,
`before_after_state`, `row_ledger`, and `trace_ledger` are required. Repair
patchlets receive a report skeleton and must edit product/runtime files under
`CXOR_EXECUTION_ROOT`; product/runtime files under `CXOR_TARGET_ROOT` are
read-only to Codex workers.

The final Markdown report has a separate wrapper gate. It must contain a
standalone canonical marker line: `FINAL_STATUS: PASS`,
`FINAL_STATUS: BLOCKED`, or `FINAL_STATUS: FAILED`. Non-canonical examples such
as `Marker: `FINAL_STATUS: PASS`` or backticked markers are rejected, and a
valid report JSON alone does not bypass the wrapper gate. The precise diagnosis
is `wrapper_gate_final_status_marker_error`; `network_or_api_error` does not
mask structured gate or routing failures.

Transaction group ids such as `TG001` are not patchlet ids. Failure records for
transaction groups preserve `source_patchlet_ids`, regeneration expands those
member patchlets, and missing mapping reports
`transaction_group_source_mapping_missing`.

## P0004 Checkpoint Cleanliness Release Gate

Before release, verify that checkpoint cleanliness is not treated as a blind
`__pycache__/` ignore. The checkpoint cleanliness taxonomy must be present:
`product_runtime_clean`, `artifact_dirs_ignored`, `cache_artifacts_detected`,
`cache_artifacts_removed`, `unknown_dirty_paths`, and
`whole_repo_clean_after_hygiene`.

`target_working_tree_clean_after_checkpoint` remains strict and must be true.
Product/runtime clean means files such as `app.py` are clean. Whole target
clean means product files are clean, `.codex-orchestrator/` and `.artifacts/`
are treated as allowed evidence directories, and known cache artifacts have
gone through the Target Hygiene Gate. `target_hygiene_gate_result.json` records
cache evidence, including hashes and `cache_artifacts_removed`; unknown dirty
paths are not deleted and must fail precisely.

Worker subprocesses set `PYTHONDONTWRITEBYTECODE=1`. Generated worker capsule
and prompt text require `python -B` or `PYTHONDONTWRITEBYTECODE=1 python` for
Python probes that import target or execution code.

Run manifest lifecycle entries must include `ATTEMPT_STARTED`,
`WORKER_EXITED`, `REPORT_VALIDATED`, `WRAPPER_GATE_EVALUATED`,
`TARGET_HYGIENE_EVALUATED`, `INTEGRATION_CHECKPOINT_WRITTEN`,
`INTEGRATION_ARTIFACTS_VALIDATED`, `ATTEMPT_ACCEPTED`, and
`ATTEMPT_FAILED_WITH_EVIDENCE`. Late failures must still have current attempt
manifest evidence. Operator-run bundles must expose runbook attempt
consistency via `attempt_consistency`.

Release diagnoses must prefer structured categories:
`integration_checkpoint_target_cleanliness_error`,
`integration_artifact_validation_error`, `run_manifest_attempt_lifecycle_error`,
`runbook_attempt_evidence_mismatch`, and `target_cache_artifact_leak`.
`network_or_api_error` requires actual external error evidence and must not be
triggered by prompt text or ordinary model/timeout metadata.

After every live real-Codex run, execute:

```bash
cxor validate-real-codex-smoke-runbook --run-dir <bundle>
cxor list-real-codex-smoke-runbooks --latest --json
cxor export-real-codex-smoke-runbook --run-dir <bundle>
```

## v0.1.0-rc1 Release Evidence

The final release evidence bundle for the v0.1.0 release candidate is:

```text
.operator-runs/real-codex-smoke/2026-07-03T18-15-05-real-codex-smoke
.operator-runs/exports/2026-07-03T18-15-05-real-codex-smoke.zip
.operator-runs/exports/2026-07-03T18-15-05-real-codex-smoke.zip.manifest.json
```

This bundle reached `DONE`, validated with `errors: []` and `warnings: []`,
and exported successfully with a hash manifest.
