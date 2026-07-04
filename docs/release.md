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

After working-tree apply, commit the product/runtime diff before starting a
new goal. `latest_apply_result.json` includes rerun guidance, and `cxor status
--json` reports it. Release checks should verify `workflow_identity.json`,
`rerun_preflight_result.json`, `cxor workflows`, archive/reset behavior, and
invocation-scoped live progress so old `operator_events.jsonl` lines are not
replayed.

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

Release checks must preserve strict canonical report validation. Canonical
`probe_artifact_refs` entries are objects; raw real-Codex string refs are
ingress-only and are normalized only when the referenced files exist under
`.artifacts/probes/` without symlink escape or patchlet mismatch. Verify
`report_ingestion_result.json`, `report_validation_errors.json`, raw report
paths, canonical report paths, and the loop-governor signature
`probe_artifact_refs_not_objects`. Repeated report-shape failures should not
show `unknown_repeated_failure`; report-only repair must not edit product files
or probe evidence. See `docs/report_contract.md`.

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

## v0.1.0-rc3 Direct Real-Codex Report-Contract Evidence

The direct real-Codex report-contract smoke for the v0.1.0 release candidate
3 checkpoint is preserved at:

```text
/tmp/cxor-target-report-contract-smoke-20260703T203745Z
```

This fresh tiny target reached `DONE` through direct `cxor auto
--worker-mode real_codex --use-worktree --live-progress`. Real Codex wrote
canonical object-shaped `probe_artifact_refs` directly; report ingress
accepted the report with `normalization_applied=false`, `errors: []`, wrapper
gate accepted, target hygiene passed, integration validation passed, and the
workflow reached `DONE`. No `unknown_repeated_failure` occurred.

## v0.1.0-rc4 Semantic Goal Satisfaction Evidence

The direct real-Codex semantic-goal smoke for the v0.1.0 release candidate 4
checkpoint is preserved at:

```text
/tmp/cxor-target-semantic-goal-smoke-20260704T070533Z
```

This fresh tiny target used the prompt `Make app return me and prove it.` and
reached `DONE` only after independent semantic proof. The semantic criterion
SGC001 expected `"me"`, the semantic runner observed actual value `"me"`, the
goal satisfaction gate accepted the patchlet, and final verification recorded
`semantic_goal_status=PASSED`. The accepted integration ref contains `app.py`
returning `"me"` and the final diff changes `ok -> me`.

This release candidate is materially stronger than rc3: it includes rerun/reset
workflow identity, invocation-scoped progress, report-ingestion hardening, and
semantic goal satisfaction for the `app.main()` return-value task family.

## Direct Auto Visibility Release Guidance

Manual direct auto smoke for operator visibility should use a fresh tiny target
and explicit real-Codex opt-in:

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

Second terminal:

```bash
uv run --no-sync cxor monitor --repo /tmp/cxor-target --follow
uv run --no-sync cxor status --repo /tmp/cxor-target --watch
uv run --no-sync cxor prompts --repo /tmp/cxor-target --latest
uv run --no-sync cxor prompts --repo /tmp/cxor-target --show PR000001 --lines 160
```

Release validation should confirm `.codex-orchestrator/operator_events.jsonl`,
`.codex-orchestrator/prompt_index.json`, and
`.codex-orchestrator/loop_governor.json` exist when relevant. `--no-live-progress`
must keep terminal progress quiet while preserving events. `--progress-format
jsonl` must print structured operator events. Compact progress must not print
raw Codex JSON or prompt bodies by default. `cxor status --json` must classify
active, silent_but_active, likely_stalled, done, and failed states. Repeated
repair-loop warnings use `loop_governor_warning`; explicit safe failure uses
`--loop-governor-mode safe-fail --max-repeated-failure-signature 3`. Default
tests must not invoke real Codex.

Semantic goal satisfaction adds a stricter `DONE` requirement for structured
goals. Built-in Python main-return prompts write `semantic_goal_spec.json`,
run an independent semantic check, write `semantic_goal_check_result.json`,
and gate patchlet acceptance through `goal_satisfaction_gate_result.json`.

## General goal proof contract

cxor treats the master prompt as the read-only source of truth. Each workflow freezes `.codex-orchestrator/master_prompt.md`, records `.codex-orchestrator/master_prompt_frozen.json`, derives `goal_interpretation.json` without claiming proof, classifies `provability/provability_result.json` before product patchlets, and stops unsupported or ambiguous goals early with `goal_not_provable_result.json` evidence.

Required proof is represented in `proof_obligations.json` and `probe_plan.json`. Worker-proposed proof is not enough: required obligations need orchestrator-owned rerun or validation in `independent_probe_rerun_result.json`, then `goal_coverage_gate_result.json` must pass. The rc4 semantic app.main path is now the concrete `SGC001 -> GI001 -> PO001 -> GP001` fast path inside this general contract.

Final DONE requires `master_prompt_concordance_result.json` and `master_prompt_satisfaction_result.json` in addition to transaction groups, integration validation, target hygiene, and unresolved-failure checks. Partial proof is not full DONE unless explicitly allowed by policy. See `docs/general_goal_proof_contract.md`.

## Goal progress, stop, and partial apply

cxor writes `goal_progress.json` and append-only `goal_progress.jsonl`; `cxor goal-progress`, `cxor status --json`, `cxor monitor`, and `cxor auto --live-progress` expose the latest obligation counts, proof state, accepted checkpoint, and next action.

`cxor stop` writes `control/stop_requested.json`; the orchestrator stops at a safe point and writes `control/stop_result.json`. `apply-results --scope accepted --allow-partial` is required for stopped non-DONE workflows and applies only latest accepted progress. In-progress unaccepted worker changes are not applied by default. `partial_apply_result.json` records the warning that the full master prompt may not be satisfied. See `docs/goal_progress_and_partial_apply.md`.
