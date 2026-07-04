# Codex Implementation Prompt — General Goal Proof Contract, Early Provability, Goal Progress, and Safe Partial Apply

Step 0 — Read this entire prompt before editing anything.

You are the Builder Layer for the local `codex-orchestrator` repository.

You are implementing the general goal-proof architecture.

This implementation follows the approved correction:

```text
The system must not be limited to app.py.
The system must not be a collection of hardcoded parsers.
The system must not require users to provide acceptance commands for every task.
The master prompt is read-only and the source of truth.
The orchestrator may extract goals, but final verification must verify that the frozen master prompt goal itself is achieved.
Provability must be identified when the workflow receives the master prompt, before product-editing patchlets begin.
Goal progress must be visible after each workflow iteration.
The operator must be able to stop the orchestrator and apply the latest accepted progress safely.
```

Do not run real Codex during implementation.

Do not mutate preserved smoke targets.

Do not delete evidence.

Do not weaken existing `v0.1.0-rc4` behavior.

Do not remove the existing app.main semantic fast path.

Do not make `DONE` easier to reach.

Do not make unsupported goals silently pass.

Do not trust worker reports alone.

Do not trust goal interpretation alone.

Do not accept `DONE` unless master prompt concordance and master prompt satisfaction pass.

---

# Part A — Baseline and preflight

Run:

```bash
export UV_CACHE_DIR=/tmp/uv-cache

pwd
git status --short
git rev-parse --show-toplevel
git rev-parse HEAD
git branch --show-current

uv run --no-sync python --version
uv --version
codex --version || true
uv run --no-sync pytest -q
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py
uv run --no-sync cxor --version
uv run --no-sync codex-orchestrator --version
uv run --no-sync python -m codex_orchestrator --version
```

Create:

```text
general_goal_proof_contract_implementation_note.md
```

Record:

```text
baseline full suite
smoke skip
current HEAD
git status
existing rc4 semantic goal behavior
implementation phase list
rollback plan
```

Stop if the baseline suite is red.

---

# Part B — Non-negotiable requirements

The implementation must satisfy these requirements:

```text
1. Master prompt is frozen and hashed.
2. Downstream artifacts reference the frozen master prompt hash.
3. Goal interpretation is derived from the frozen master prompt, not mutable source text.
4. Proof obligations reference goal items and master prompt spans.
5. Probe plans reference proof obligations.
6. Provability is classified before product-editing patchlets begin.
7. Ambiguous/unprovable goals stop early with evidence.
8. Worker proof alone cannot satisfy required obligations.
9. Orchestrator-owned independent probe rerun is required for required obligations.
10. Goal coverage gate tracks covered/uncovered/failed obligations.
11. Goal progress updates after each workflow iteration.
12. Status/monitor/live progress expose goal progress.
13. Global verification checks master prompt concordance.
14. Global verification checks master prompt satisfaction.
15. DONE requires master prompt satisfaction, not only artifact consistency.
16. Operator can stop the workflow safely.
17. Operator can apply latest accepted progress with explicit partial flag.
18. Unaccepted in-progress work is not applied by default.
19. Existing app.main return-value semantic path still works as a fast path.
20. Existing report-ingestion, rerun/reset, live-progress, and target-hygiene tests remain green.
```

---

# Phase 1 — Master prompt source-of-truth artifact

## Goal

Create a durable immutable master prompt source-of-truth artifact.

## Add schema

```text
src/codex_orchestrator/schemas/master_prompt_frozen.schema.json
```

## Add or update module

```text
src/codex_orchestrator/master_prompt_source.py
```

## Artifact

```text
.codex-orchestrator/master_prompt_frozen.json
```

## Required fields

```text
schema_version
kind
workflow_id
run_id
source_path
frozen_copy_path
sha256
size_bytes
created_at
read_only_source_of_truth
source_spans
```

## Tests

Create:

```text
tests/unit/test_master_prompt_source_of_truth.py
```

Tests:

```text
test_freezes_master_prompt_with_hash_and_copy_path
test_source_spans_include_full_prompt_for_simple_prompt
test_downstream_reference_payload_contains_master_prompt_sha
test_changed_source_prompt_after_freeze_is_detected
test_frozen_copy_remains_source_of_truth_after_source_change
test_master_prompt_frozen_schema_validates
```

Run:

```bash
uv run --no-sync pytest -q tests/unit/test_master_prompt_source_of_truth.py
```

---

# Phase 2 — Goal interpretation artifact

## Goal

Create a structured goal interpretation artifact that references master prompt spans, but does not itself prove success.

## Add schema

```text
src/codex_orchestrator/schemas/goal_interpretation.schema.json
```

## Add or update module

```text
src/codex_orchestrator/goal_interpretation.py
```

## Artifact

```text
.codex-orchestrator/goal_interpretation.json
```

## Required behavior

```text
- records goal_items
- records source_span_ids
- records ambiguities
- records assumptions
- records whether external resources are required
- supports CONCORDANT, INCOMPLETE, CONTRADICTORY, AMBIGUOUS statuses
```

## Tests

Create:

```text
tests/integration/test_goal_interpretation_artifact.py
```

Tests:

```text
test_goal_interpretation_written_after_master_prompt_freeze
test_goal_item_references_master_prompt_span
test_goal_interpretation_records_ambiguity
test_goal_interpretation_schema_validates
test_goal_interpretation_does_not_mark_goal_proven
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_goal_interpretation_artifact.py
```

---

# Phase 3 — Early provability gate

## Goal

Classify whether the master prompt is provable before product-editing patchlets begin.

## Add schema

```text
src/codex_orchestrator/schemas/provability_result.schema.json
```

## Add module

```text
src/codex_orchestrator/provability.py
```

## Artifact

```text
.codex-orchestrator/provability/provability_result.json
```

## Required statuses

```text
PROVABLE
PARTIALLY_PROVABLE
NEEDS_READ_ONLY_DISCOVERY
AMBIGUOUS
UNPROVABLE
BLOCKED_BY_MISSING_CAPABILITY
```

## Required behavior

```text
- runs after master prompt freeze and repo census
- runs before patchlet compilation that can edit product files
- unprovable/ambiguous goals stop early with safe failure evidence
- needs-discovery goals run read-only proof discovery only
- late unprovability is recorded as late_goal_unprovable_discovered
```

## Tests

Create:

```text
tests/integration/test_goal_provability_gate.py
```

Tests:

```text
test_provable_goal_allows_patchlet_compilation
test_ambiguous_goal_stops_before_product_patchlet
test_unprovable_goal_safe_fails_before_product_patchlet
test_needs_discovery_goal_runs_read_only_discovery
test_provability_result_written
test_provability_result_schema_validates
test_late_unprovability_records_defect_signature
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_goal_provability_gate.py
```

---

# Phase 4 — General proof obligation contract

## Goal

Represent what evidence is required to prove the master prompt goal.

## Add schema

```text
src/codex_orchestrator/schemas/proof_obligations.schema.json
```

## Add module

```text
src/codex_orchestrator/proof_obligations.py
```

## Artifact

```text
.codex-orchestrator/proof_obligations.json
```

## Required statuses

```text
UNPROVEN
IN_PROGRESS
PROVEN_BY_WORKER
PROVEN_BY_ORCHESTRATOR
FAILED
BLOCKED
WAIVED_BY_POLICY
```

## Required behavior

```text
- every required goal item has at least one required proof obligation
- every proof obligation references source spans and goal items
- required obligations cannot be skipped silently
- existing SGC app.main semantic criterion maps into proof obligation PO001
```

## Tests

Create:

```text
tests/integration/test_general_goal_proof_contract.py
```

Tests:

```text
test_proof_obligations_written_for_structured_goal
test_every_goal_item_has_required_obligation
test_obligation_references_source_span
test_obligation_status_lifecycle
test_app_main_semantic_fast_path_maps_to_proof_obligation
test_missing_obligation_blocks_provability
test_proof_obligations_schema_validates
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_general_goal_proof_contract.py
```

---

# Phase 5 — General probe plan contract

## Goal

Represent which probes will prove each proof obligation.

## Add schema

```text
src/codex_orchestrator/schemas/probe_plan.schema.json
```

## Add module

```text
src/codex_orchestrator/probe_plan.py
```

## Artifact

```text
.codex-orchestrator/probe_plan.json
```

## Required behavior

```text
- every required obligation has at least one probe plan entry
- probe has side-effect policy
- probe is marked rerunnable_by_orchestrator
- worker-proposed probes can be recorded but not trusted until rerun
- invalid probes cannot prove obligations
```

## Tests

Create:

```text
tests/integration/test_general_probe_plan.py
```

Tests:

```text
test_probe_plan_written_for_required_obligation
test_probe_plan_references_obligation_ids
test_probe_plan_requires_rerunnable_by_orchestrator_for_required_goal
test_probe_plan_records_side_effect_policy
test_worker_proposed_probe_is_not_enough_to_prove_obligation
test_invalid_probe_plan_blocks_goal_coverage
test_probe_plan_schema_validates
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_general_probe_plan.py
```

---

# Phase 6 — Independent probe rerun gate

## Goal

Ensure Codex may propose proof, but the orchestrator owns proof acceptance.

## Add schema

```text
src/codex_orchestrator/schemas/independent_probe_rerun_result.schema.json
```

## Add module

```text
src/codex_orchestrator/independent_probe_rerun.py
```

## Artifact

```text
.codex-orchestrator/runs/<attempt_id>/gates/independent_probe_rerun_result.json
```

## Required behavior

```text
- rerun mapped probes in controlled context
- record expected/actual
- record stdout/stderr
- mark obligations PROVEN_BY_ORCHESTRATOR only after rerun pass
- fail expected/actual mismatch
- do not create pycache leaks
```

## Tests

Create:

```text
tests/integration/test_independent_probe_rerun_gate.py
```

Tests:

```text
test_worker_proof_alone_does_not_prove_obligation
test_orchestrator_rerun_proves_obligation
test_rerun_expected_actual_mismatch_fails
test_rerun_stdout_stderr_are_persisted
test_rerun_result_schema_validates
test_rerun_does_not_create_pycache
test_failed_rerun_creates_failure_signature_independent_probe_rerun_failed
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_independent_probe_rerun_gate.py
```

---

# Phase 7 — Goal coverage gate

## Goal

Decide whether the current attempt covers required proof obligations.

## Add schema

```text
src/codex_orchestrator/schemas/goal_coverage_gate_result.schema.json
```

## Add module or integrate with run_patchlet

```text
src/codex_orchestrator/goal_coverage.py
```

## Artifact

```text
.codex-orchestrator/runs/<attempt_id>/gates/goal_coverage_gate_result.json
```

## Required behavior

```text
- all required obligations must be covered and proven by orchestrator for DONE path
- failed obligations block acceptance or route repair
- VERIFIED_NO_CHANGE_NEEDED requires coverage pass
- COMPLETE requires coverage pass
- missing obligation coverage blocks acceptance
```

## Tests

Create:

```text
tests/integration/test_goal_coverage_gate.py
```

Tests:

```text
test_goal_coverage_passes_when_required_obligation_proven
test_goal_coverage_fails_when_required_obligation_unproven
test_goal_coverage_fails_when_probe_failed
test_verified_no_change_requires_goal_coverage_pass
test_complete_requires_goal_coverage_pass
test_goal_coverage_result_schema_validates
test_goal_coverage_failure_routes_to_repair
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_goal_coverage_gate.py
```

---

# Phase 8 — Goal progress visibility

## Goal

Show goal progress after each workflow iteration.

## Add schema

```text
src/codex_orchestrator/schemas/goal_progress.schema.json
```

## Add module

```text
src/codex_orchestrator/goal_progress.py
```

## Artifacts

```text
.codex-orchestrator/goal_progress.json
.codex-orchestrator/goal_progress.jsonl
```

## Add CLI

```bash
cxor goal-progress --repo <repo>
cxor goal-progress --repo <repo> --json
cxor goal-progress --repo <repo> --watch
```

## Required behavior

```text
- update after each workflow iteration
- append timeline entry
- status JSON includes goal progress summary
- monitor shows goal_progress_updated events
- live progress prints compact goal progress summary
```

## Tests

Create:

```text
tests/integration/test_goal_progress_visibility.py
```

Tests:

```text
test_goal_progress_json_written_after_provability
test_goal_progress_updates_after_patchlet_attempt
test_goal_progress_jsonl_is_append_only
test_status_json_includes_goal_progress_summary
test_monitor_shows_goal_progress_updated_events
test_live_progress_prints_goal_progress_summary
test_goal_progress_cli_human_output
test_goal_progress_cli_json_output
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_goal_progress_visibility.py
```

---

# Phase 9 — Global master-prompt concordance and satisfaction verifier

## Goal

Make final verification check the frozen master prompt itself, not only the derived artifacts.

## Add schemas

```text
src/codex_orchestrator/schemas/master_prompt_concordance_result.schema.json
src/codex_orchestrator/schemas/master_prompt_satisfaction_result.schema.json
```

## Artifacts

```text
.codex-orchestrator/global_verification/master_prompt_concordance_result.json
.codex-orchestrator/global_verification/master_prompt_satisfaction_result.json
```

## Required behavior

```text
- final verifier verifies goal interpretation covers master prompt spans
- final verifier verifies proof obligations cover goal items
- final verifier verifies all required obligations are proven by orchestrator
- final verifier blocks DONE if master prompt has uncovered required goals
- final verifier blocks DONE if satisfaction status is NOT_SATISFIED, AMBIGUOUS, UNPROVABLE, or BLOCKED
- final_verification.json includes concordance and satisfaction paths
- verification_matrix includes master prompt coverage and proof obligation coverage
```

## Tests

Create:

```text
tests/integration/test_master_prompt_satisfaction_verifier.py
```

Tests:

```text
test_global_verifier_writes_master_prompt_concordance_result
test_global_verifier_writes_master_prompt_satisfaction_result
test_done_requires_master_prompt_concordance_pass
test_done_requires_master_prompt_satisfaction_pass
test_done_blocked_when_interpretation_misses_required_span
test_done_blocked_when_required_obligation_unproven
test_done_blocked_when_required_obligation_failed
test_final_verification_links_concordance_and_satisfaction
test_verification_matrix_includes_master_prompt_coverage
test_existing_app_main_semantic_done_still_passes
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_master_prompt_satisfaction_verifier.py
```

---

# Phase 10 — Early unprovable and ambiguous goal behavior

## Goal

Avoid discovering unsupported/ambiguous goals only at the end.

## Required behavior

```text
- unprovable goal safe-fails before product editing
- ambiguous goal safe-fails before product editing
- partially provable goal records partial status before product editing
- operator status shows why product patchlets did not start
- no worker product edits occur when provability fails early
```

## Tests

Create:

```text
tests/integration/test_early_unprovable_goal_behavior.py
```

Tests:

```text
test_unprovable_goal_safe_fails_before_product_patchlet
test_ambiguous_goal_safe_fails_before_product_patchlet
test_provability_failure_writes_goal_not_provable_result
test_provability_failure_status_explains_reason
test_no_product_patchlet_started_for_unprovable_goal
test_no_worker_codex_invoked_for_unprovable_goal
test_late_goal_unprovable_signature_if_discovered_after_patchlets
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_early_unprovable_goal_behavior.py
```

---

# Phase 11 — Stop command and safe partial apply

## Goal

Allow operator to stop the orchestrator and apply latest accepted progress.

## Add schemas

```text
src/codex_orchestrator/schemas/stop_requested.schema.json
src/codex_orchestrator/schemas/stop_result.schema.json
src/codex_orchestrator/schemas/partial_apply_result.schema.json
```

## Add CLI

```bash
cxor stop --repo <repo>
cxor stop --repo <repo> --now
cxor stop --repo <repo> --after-current-attempt
cxor stop --repo <repo> --json
```

Extend apply-results:

```bash
cxor apply-results --repo <repo> --mode patch --scope accepted --allow-partial
cxor apply-results --repo <repo> --mode branch --scope accepted --allow-partial
cxor apply-results --repo <repo> --mode working-tree --scope accepted --allow-partial
```

## Required behavior

```text
- stop writes stop_requested.json
- auto loop checks stop request at safe points
- graceful stop writes stop_result.json
- stopped workflow exposes latest accepted checkpoint
- apply-results refuses partial stopped workflow without --allow-partial
- apply-results with --allow-partial applies latest accepted integration ref only
- in-progress unaccepted attempt is not applied
- no accepted checkpoint means apply-results refuses
```

## Tests

Create:

```text
tests/integration/test_stop_and_partial_apply.py
```

Tests:

```text
test_stop_command_writes_stop_requested
test_auto_stops_after_current_attempt_when_requested
test_stop_result_records_latest_accepted_checkpoint
test_apply_results_partial_requires_allow_partial
test_apply_results_partial_applies_latest_accepted_checkpoint
test_apply_results_partial_refuses_when_no_accepted_checkpoint
test_apply_results_partial_does_not_apply_in_progress_attempt
test_ctrl_c_like_interrupt_preserves_state_if_existing_harness_supports_it
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_stop_and_partial_apply.py
```

---

# Phase 12 — Operator events, status, monitor, diagnostics

## Goal

Expose the new architecture to operators.

## Events

Add:

```text
master_prompt_frozen
goal_interpretation_written
provability_classified
proof_obligations_written
probe_plan_written
independent_probe_rerun_started
independent_probe_rerun_passed
independent_probe_rerun_failed
goal_coverage_gate_passed
goal_coverage_gate_failed
goal_progress_updated
master_prompt_concordance_passed
master_prompt_concordance_failed
master_prompt_satisfaction_passed
master_prompt_satisfaction_failed
stop_requested
workflow_stopped
partial_apply_started
partial_apply_completed
```

## Diagnosis signatures

Add:

```text
goal_not_provable
goal_ambiguous
master_prompt_concordance_failed
master_prompt_not_satisfied
proof_obligation_failed
independent_probe_rerun_failed
goal_coverage_failed
late_goal_unprovable_discovered
partial_progress_stopped
```

## Tests

Create:

```text
tests/integration/test_general_goal_proof_operator_visibility.py
```

Tests:

```text
test_operator_events_include_provability_and_goal_progress
test_status_json_includes_master_prompt_proof_summary
test_monitor_shows_goal_coverage_failure
test_live_progress_shows_master_prompt_satisfaction_failure
test_diagnosis_goal_not_provable
test_diagnosis_master_prompt_not_satisfied
test_diagnosis_independent_probe_rerun_failed
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_general_goal_proof_operator_visibility.py
```

---

# Phase 13 — Integration with existing rc4 semantic app.main path

## Goal

Keep the working rc4 semantic path, but express it through the general proof contract.

## Required behavior

```text
- existing semantic_goal_spec remains compatible
- app.main return-value criterion maps to proof obligation PO001
- semantic_goal_runner can be used as independent probe rerun implementation for that obligation
- goal_progress shows PO001
- master_prompt_satisfaction_result passes for correct app.main behavior
- false ok-vs-me path still blocked
```

## Tests

Extend or add:

```text
tests/integration/test_rc4_semantic_fast_path_generalized.py
```

Tests:

```text
test_app_main_return_goal_creates_general_proof_obligation
test_app_main_return_goal_creates_probe_plan
test_app_main_return_goal_updates_goal_progress
test_ok_vs_me_false_done_still_blocked_by_general_coverage_gate
test_correct_me_goal_still_reaches_done
test_unsupported_prompt_does_not_claim_master_prompt_satisfaction
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_rc4_semantic_fast_path_generalized.py
```

---

# Phase 14 — Documentation

Update:

```text
README.md
docs/cli.md
docs/autonomous_loop.md
docs/semantic_goal_satisfaction.md
docs/workflow_lifecycle.md
docs/real_codex_smoke.md
docs/release.md
docs/runbooks/real_codex_smoke_runbook.md
docs/Codex_Orchestrator_Step_By_Step_Usage_Guide.md
IMPLEMENTATION_STATUS.md
```

Add:

```text
docs/general_goal_proof_contract.md
docs/goal_progress_and_partial_apply.md
```

Docs must explain:

```text
master prompt source of truth
frozen prompt hash
master prompt concordance
master prompt satisfaction
early provability
proof obligations
probe plan
independent rerun
goal coverage gate
goal progress after each iteration
stop command
partial apply of accepted progress
why unaccepted in-progress work is not applied
why DONE is impossible without master prompt satisfaction
```

Tests:

```text
tests/unit/test_docs_general_goal_proof_contract.py
tests/unit/test_docs_goal_progress_partial_apply.py
```

Run:

```bash
uv run --no-sync pytest -q tests/unit/test_docs_general_goal_proof_contract.py tests/unit/test_docs_goal_progress_partial_apply.py
```

---

# Phase 15 — Full verification

Run focused new tests:

```bash
export UV_CACHE_DIR=/tmp/uv-cache

uv run --no-sync pytest -q tests/unit/test_master_prompt_source_of_truth.py
uv run --no-sync pytest -q tests/integration/test_goal_interpretation_artifact.py
uv run --no-sync pytest -q tests/integration/test_goal_provability_gate.py
uv run --no-sync pytest -q tests/integration/test_general_goal_proof_contract.py
uv run --no-sync pytest -q tests/integration/test_general_probe_plan.py
uv run --no-sync pytest -q tests/integration/test_independent_probe_rerun_gate.py
uv run --no-sync pytest -q tests/integration/test_goal_coverage_gate.py
uv run --no-sync pytest -q tests/integration/test_goal_progress_visibility.py
uv run --no-sync pytest -q tests/integration/test_master_prompt_satisfaction_verifier.py
uv run --no-sync pytest -q tests/integration/test_early_unprovable_goal_behavior.py
uv run --no-sync pytest -q tests/integration/test_stop_and_partial_apply.py
uv run --no-sync pytest -q tests/integration/test_general_goal_proof_operator_visibility.py
uv run --no-sync pytest -q tests/integration/test_rc4_semantic_fast_path_generalized.py
uv run --no-sync pytest -q tests/unit/test_docs_general_goal_proof_contract.py tests/unit/test_docs_goal_progress_partial_apply.py
```

Run regression tests:

```bash
uv run --no-sync pytest -q tests/integration/test_semantic_goal_false_done_chain.py
uv run --no-sync pytest -q tests/integration/test_goal_satisfaction_gate.py
uv run --no-sync pytest -q tests/integration/test_semantic_goal_verifiers.py
uv run --no-sync pytest -q tests/integration/test_auto_rerun_cli_semantics.py
uv run --no-sync pytest -q tests/integration/test_workflow_registry_namespace.py
uv run --no-sync pytest -q tests/integration/test_live_progress_invocation_cursor.py
uv run --no-sync pytest -q tests/integration/test_direct_auto_live_progress.py
uv run --no-sync pytest -q tests/integration/test_report_ingestion_gate.py
uv run --no-sync pytest -q tests/integration/test_real_codex_probe_ref_loop_chain.py
uv run --no-sync pytest -q tests/integration/test_p0004_checkpoint_failure_chain.py
uv run --no-sync pytest -q tests/integration/test_target_hygiene_gate.py
uv run --no-sync pytest -q tests/integration/test_run_manifest_attempt_lifecycle.py
uv run --no-sync pytest -q tests/integration/test_real_codex_runbook_attempt_consistency.py
```

Run full verification:

```bash
uv run --no-sync pytest -q
uv run --no-sync python -m codex_orchestrator --version
uv run --no-sync cxor --version
uv run --no-sync codex-orchestrator --version
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py
git status --short
```

Do not run explicit real Codex.

---

# Required final report format

Return exactly:

```text
# Codex TDD Report — General Goal Proof Contract, Progress Visibility, and Partial Apply

## 1. Baseline
- Python:
- uv:
- codex version:
- initial full test result:
- default smoke result:
- git status at start:
- current branch:
- HEAD:

## 2. Architecture decisions implemented
- master prompt source of truth:
- goal interpretation:
- early provability:
- proof obligations:
- probe plan:
- independent rerun:
- goal coverage gate:
- goal progress:
- master prompt concordance:
- master prompt satisfaction:
- stop:
- partial apply:
- rc4 semantic fast path integration:

## 3. Phase results

### Phase 1 — Master prompt source-of-truth artifact
- red tests:
- files changed:
- focused green command:
- focused green result:
- behavior:

### Phase 2 — Goal interpretation artifact
- red tests:
- files changed:
- focused green command:
- focused green result:
- behavior:

### Phase 3 — Early provability gate
- red tests:
- files changed:
- focused green command:
- focused green result:
- behavior:

### Phase 4 — General proof obligation contract
- red tests:
- files changed:
- focused green command:
- focused green result:
- behavior:

### Phase 5 — General probe plan contract
- red tests:
- files changed:
- focused green command:
- focused green result:
- behavior:

### Phase 6 — Independent probe rerun gate
- red tests:
- files changed:
- focused green command:
- focused green result:
- behavior:

### Phase 7 — Goal coverage gate
- red tests:
- files changed:
- focused green command:
- focused green result:
- behavior:

### Phase 8 — Goal progress visibility
- red tests:
- files changed:
- focused green command:
- focused green result:
- behavior:

### Phase 9 — Global master-prompt concordance and satisfaction verifier
- red tests:
- files changed:
- focused green command:
- focused green result:
- behavior:

### Phase 10 — Early unprovable and ambiguous goal behavior
- red tests:
- files changed:
- focused green command:
- focused green result:
- behavior:

### Phase 11 — Stop command and safe partial apply
- red tests:
- files changed:
- focused green command:
- focused green result:
- behavior:

### Phase 12 — Operator events, status, monitor, diagnostics
- red tests:
- files changed:
- focused green command:
- focused green result:
- behavior:

### Phase 13 — Integration with existing rc4 semantic app.main path
- red tests:
- files changed:
- focused green command:
- focused green result:
- behavior:

### Phase 14 — Documentation
- red tests:
- files changed:
- focused green command:
- focused green result:
- docs updated:

### Phase 15 — Final verification
- commands:
- outputs:

## 4. Master prompt source of truth

## 5. Early provability behavior

## 6. Proof obligation behavior

## 7. Probe plan and independent rerun behavior

## 8. Goal coverage and progress behavior

## 9. Master prompt final verifier behavior

## 10. Stop and partial apply behavior

## 11. Operator visibility

## 12. rc4 semantic fast-path regression

## 13. Docs

## 14. Default smoke skip

## 15. Final verification output

## 16. Git status

## 17. Remaining confirmed gaps

## 18. Next single highest-value increment
```

---

# Final implementation instruction

Implement the general goal-proof architecture.

Do not run explicit real Codex.

Do not mutate preserved targets.

Do not make DONE easier.

Do not accept unsupported goals as proven.

Do not wait until the final verifier to classify provability.

Do not apply unaccepted in-progress work by default.

Preserve existing rc4 semantic goal behavior and all prior safety gates.
