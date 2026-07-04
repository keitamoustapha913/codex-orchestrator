# Codex Orchestrator — Semantic Goal Satisfaction Implementation Prompt

## Step 0 — Read before editing

You are the Builder Layer for the local `codex-orchestrator` repository.

You are implementing the semantic-goal-satisfaction architecture.

This implementation is based on the evidence report:

```text
semantic_goal_done_false_positive_evidence_report.md
```

The evidence proved that a fresh second workflow for a changed prompt reached `DONE` while the requested semantic behavior was not satisfied.

The prompt was:

```text
Make app return me and prove it.
```

The accepted final behavior was:

```python
def main():
    return "ok"
```

The worker report said:

```text
VERIFIED_NO_CHANGE_NEEDED
```

The orchestrator accepted it because the existing gates validated workflow structure, report shape, target hygiene, integration artifacts, transaction groups, and global artifact consistency. None of those gates independently proved that `app.main()` returned `"me"`.

Your job is to implement the missing semantic goal-satisfaction plane.

Do not guess.

Do not weaken existing gates.

Do not remove the rerun/reset workflow identity fix.

Do not remove report ingestion hardening.

Do not remove target hygiene.

Do not remove operator visibility.

Do not remove raw/canonical report handling.

Do not run real Codex during implementation.

Use fresh temporary repos and fake/mock workers for tests.

---

# Step 1 — Baseline

Run before editing:

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
uv run --no-sync python -m codex_orchestrator --version
uv run --no-sync cxor --version
uv run --no-sync codex-orchestrator --version
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py
```

Create:

```text
semantic_goal_satisfaction_implementation_note.md
```

Record:

```text
baseline full suite result
current HEAD
git status
Python/uv/codex versions
default smoke skip result
evidence report path
proven false-positive summary
implementation phase list
rollback plan
```

Stop if the full suite is red.

---

# Step 2 — Preflight inspection

Before editing, inspect:

```bash
rg -n "goal_spec|acceptance|criteria|VERIFIED_NO_CHANGE_NEEDED|final_verification|verify_global|verify_group|compile_patchlets|patchlet_report|wrapper_gate|operator_events|status|prompt_index" \
  src tests docs README.md IMPLEMENTATION_STATUS.md || true

sed -n '1,3200p' src/codex_orchestrator/stages/compile_patchlets.py
sed -n '1,3200p' src/codex_orchestrator/stages/run_patchlet.py
sed -n '1,3200p' src/codex_orchestrator/stages/verify_group.py
sed -n '1,3200p' src/codex_orchestrator/stages/verify_global.py
sed -n '1,3200p' src/codex_orchestrator/validators/report_validator.py
sed -n '1,3200p' src/codex_orchestrator/worker_capsule.py
sed -n '1,3200p' src/codex_orchestrator/operator_events.py
sed -n '1,3200p' src/codex_orchestrator/stages/status.py
sed -n '1,3200p' src/codex_orchestrator/prompt_templates/real_codex_patchlet_contract.md
```

Record findings in the implementation note.

---

# Phase 1 — Semantic goal parser

## Goal

Create a narrow deterministic parser that turns simple master prompts into structured semantic goals.

## New module

```text
src/codex_orchestrator/semantic_goal_parser.py
```

## Supported pattern

Initial support must be conservative:

```text
Make app return me and prove it.
Make app return ok and prove it.
Make app.py return "ready" and prove it.
Make main return done and prove it.
```

All should produce a `python_function_return` goal.

## Output

```json
{
  "goal_id": "G001",
  "goal_type": "python_function_return",
  "source": "builtin_prompt_parser",
  "confidence": "high",
  "target_file": "app.py",
  "function_name": "main",
  "expected_return_value": "me",
  "expected_return_type": "str",
  "requires_independent_verification": true,
  "acceptance_criteria_ids": ["AC001"]
}
```

## Ambiguous prompts

Ambiguous prompts must not be guessed.

They should produce:

```json
{
  "requires_explicit_acceptance_criteria": true,
  "unparsed_requirements": ["..."]
}
```

## Tests

Create:

```text
tests/unit/test_semantic_goal_parser.py
```

Tests:

```python
test_parse_make_app_return_me
test_parse_make_app_return_ok
test_parse_quoted_return_value
test_parse_main_return_value
test_parser_is_case_tolerant_for_make_app_return
test_parser_rejects_ambiguous_prompt
test_parser_does_not_overgeneralize_multi_file_prompt
test_parser_preserves_original_prompt_text
test_parser_marks_unparsed_requirements
```

Run:

```bash
uv run --no-sync pytest -q tests/unit/test_semantic_goal_parser.py
```

---

# Phase 2 — Semantic goal spec and acceptance criteria artifacts

## Goal

Write durable artifacts that bind the master prompt to machine-checkable acceptance criteria.

## Artifacts

```text
.codex-orchestrator/semantic/goal_spec.json
.codex-orchestrator/semantic/acceptance_criteria.json
```

## Schemas

Add:

```text
src/codex_orchestrator/schemas/semantic_goal_spec.schema.json
src/codex_orchestrator/schemas/acceptance_criteria.schema.json
```

## goal_spec.json

```json
{
  "schema_version": "1.0",
  "kind": "semantic_goal_spec",
  "workflow_id": "WF...",
  "run_id": "R0002",
  "master_prompt_path": "/tmp/.../master_prompt_me.md",
  "master_prompt_sha256": "...",
  "master_prompt_text": "Make app return me and prove it.",
  "goals": [],
  "unparsed_requirements": [],
  "requires_explicit_acceptance_criteria": false
}
```

## acceptance_criteria.json

```json
{
  "schema_version": "1.0",
  "kind": "acceptance_criteria",
  "workflow_id": "WF...",
  "run_id": "R0002",
  "criteria": [
    {
      "criterion_id": "AC001",
      "goal_id": "G001",
      "criterion_type": "python_function_return_equals",
      "target_file": "app.py",
      "function_name": "main",
      "expected_value": "me",
      "expected_type": "str",
      "must_pass_before_done": true,
      "must_pass_for_verified_no_change_needed": true
    }
  ]
}
```

## Integration point

Run after master prompt normalization and workflow identity creation, before patchlet compilation.

## Tests

Create:

```text
tests/integration/test_semantic_goal_artifacts.py
```

Tests:

```python
test_goal_spec_written_after_master_prompt
test_goal_spec_contains_master_prompt_text_and_hash
test_goal_spec_contains_python_return_goal
test_acceptance_criteria_written
test_acceptance_criteria_contains_expected_return_value
test_goal_spec_schema_validates
test_acceptance_criteria_schema_validates
test_ambiguous_prompt_writes_requires_explicit_acceptance_criteria
test_workflow_identity_and_goal_spec_share_workflow_id
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_semantic_goal_artifacts.py
```

---

# Phase 3 — Patchlet and worker prompt binding

## Goal

Ensure generated patchlet and worker prompts explicitly carry semantic acceptance criteria.

The bad case happened because the worker effectively proved `"ok"` while the workflow identity requested `"me"`.

## Required prompt text

Generated subprompt and worker prompt must include:

```text
Semantic acceptance criteria for this workflow:

- AC001 / G001:
  app.py main() must return "me".

VERIFIED_NO_CHANGE_NEEDED is allowed only if this criterion already passes.
If app.py main() returns anything other than "me", do not report VERIFIED_NO_CHANGE_NEEDED.
If the criterion fails and app.py is the allowed product/runtime file, implement the smallest change and prove the criterion passes.
```

## Worker memory

Add to worker capsule:

```text
SEMANTIC_GOAL_CONTRACT.md
```

Contents:

```text
# SEMANTIC GOAL CONTRACT

The user goal is not satisfied unless all must-pass acceptance criteria pass.

Acceptance criteria:
- AC001: app.py main() must return "me".

Do not substitute an older expected value.
Do not use the previous workflow's expected value.
Do not report VERIFIED_NO_CHANGE_NEEDED unless AC001 passes.
```

## Tests

Create:

```text
tests/integration/test_semantic_goal_prompt_binding.py
```

Tests:

```python
test_patchlet_subprompt_includes_semantic_acceptance_criteria
test_worker_prompt_includes_semantic_acceptance_criteria
test_worker_prompt_forbids_verified_no_change_when_criterion_fails
test_worker_capsule_writes_semantic_goal_contract
test_semantic_goal_contract_lists_expected_value
test_prompt_index_references_semantic_goal_contract
test_old_prompt_expected_value_not_used_in_new_run_prompt
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_semantic_goal_prompt_binding.py
```

---

# Phase 4 — Orchestrator-owned semantic probes

## Goal

Add independent semantic probes that are generated and run by the orchestrator, not by Codex.

## Module

```text
src/codex_orchestrator/semantic_probe.py
```

## Artifact root

```text
.codex-orchestrator/semantic/probes/G001/
```

## Probe result

```text
.codex-orchestrator/semantic/probes/G001/semantic_probe_result.json
```

## Behavior

For `python_function_return_equals`:

```text
1. Create an isolated probe worktree or use the integration candidate worktree.
2. Add the relevant root to sys.path.
3. Import the target module without writing bytecode.
4. Call the named function.
5. Compare actual return value to expected value.
6. Write durable result.
```

Use:

```text
PYTHONDONTWRITEBYTECODE=1
python -B
```

## Result

```json
{
  "schema_version": "1.0",
  "kind": "semantic_probe_result",
  "goal_id": "G001",
  "criterion_id": "AC001",
  "target_file": "app.py",
  "function_name": "main",
  "expected_value": "me",
  "actual_value": "ok",
  "passed": false,
  "stdout": "",
  "stderr": "",
  "probe_command": "...",
  "created_at": "..."
}
```

## Tests

Create:

```text
tests/integration/test_semantic_probe.py
```

Tests:

```python
test_semantic_probe_passes_when_main_returns_expected_value
test_semantic_probe_fails_when_main_returns_wrong_value
test_semantic_probe_records_expected_and_actual
test_semantic_probe_uses_python_no_bytecode_policy
test_semantic_probe_does_not_create_target_root_pycache
test_semantic_probe_result_schema_validates
test_semantic_probe_handles_import_error
test_semantic_probe_handles_missing_function
test_semantic_probe_runs_against_candidate_integration_state
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_semantic_probe.py
```

---

# Phase 5 — Semantic goal gate before patchlet acceptance

## Goal

Add a semantic gate that runs after wrapper/report validation and before patchlet acceptance.

## Artifact

```text
.codex-orchestrator/semantic/goal_verification_result.json
```

## Rejection case

The observed bad case must now reject:

```text
goal: app.py main() must return "me"
report: VERIFIED_NO_CHANGE_NEEDED
actual: "ok"
```

Expected result:

```json
{
  "semantic_done": false,
  "valid": false,
  "failed_goal_ids": ["G001"],
  "operator_summary": "Goal G001 failed: app.main() returned 'ok', expected 'me'."
}
```

## Event

Emit:

```text
semantic_goal_verification_failed
```

or:

```text
semantic_goal_verification_passed
```

## Failure category

```text
semantic_goal_not_satisfied
```

## Tests

Create:

```text
tests/integration/test_semantic_goal_gate.py
```

Tests:

```python
test_verified_no_change_rejected_when_expected_me_actual_ok
test_verified_no_change_accepted_when_expected_ok_actual_ok
test_complete_rejected_when_semantic_probe_fails
test_complete_accepted_when_semantic_probe_passes
test_semantic_goal_gate_result_written
test_semantic_goal_gate_result_schema_validates
test_semantic_goal_failure_record_created
test_operator_event_emitted_for_semantic_goal_failure
test_patchlet_not_accepted_when_semantic_goal_fails
test_integration_checkpoint_not_written_when_semantic_goal_fails
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_semantic_goal_gate.py
```

---

# Phase 6 — Global verifier enforcement

## Goal

Make global verification require semantic goal success before `DONE`.

## Update final_verification.json

Add:

```json
{
  "workflow_artifacts_valid": true,
  "transaction_groups_valid": true,
  "semantic_goals_valid": false,
  "semantic_goal_verification_result": ".codex-orchestrator/semantic/goal_verification_result.json",
  "failed_goal_ids": ["G001"],
  "proven_goal_ids": [],
  "unproven_goal_ids": ["G001"],
  "status": "SAFE_FAILURE"
}
```

## DONE policy

`DONE` is allowed only if:

```text
semantic_goals_valid == true
unresolved_failures == []
transaction_groups_valid == true
workflow_artifacts_valid == true
```

## Tests

Create:

```text
tests/integration/test_global_verifier_semantic_goal.py
```

Tests:

```python
test_global_verifier_refuses_done_when_semantic_goal_fails
test_global_verifier_allows_done_when_semantic_goal_passes
test_final_verification_includes_semantic_goal_result_path
test_final_verification_includes_failed_goal_ids
test_verification_matrix_includes_semantic_goal_status
test_workflow_done_event_not_emitted_when_semantic_goal_fails
test_workflow_safe_failed_event_emitted_when_semantic_goal_fails
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_global_verifier_semantic_goal.py
```

---

# Phase 7 — Report schema and wrapper gate semantic fields

## Goal

Make reports carry expected-vs-actual semantic results, and ensure `VERIFIED_NO_CHANGE_NEEDED` is not trusted without semantic proof.

## Report fields

Add:

```json
{
  "semantic_goal_results": [
    {
      "goal_id": "G001",
      "criterion_id": "AC001",
      "expected_value": "me",
      "actual_value": "ok",
      "passed": false
    }
  ],
  "verified_no_change_reason": {
    "goal_id": "G001",
    "criterion_id": "AC001",
    "existing_behavior_satisfies_goal": false
  }
}
```

## Wrapper gate behavior

If `status == VERIFIED_NO_CHANGE_NEEDED` and any semantic goal exists:

```text
require semantic gate pass
reject if semantic_goal_results missing or failing
reject if verified_no_change_reason.existing_behavior_satisfies_goal is false
```

The orchestrator semantic gate remains authoritative even if report claims pass.

## Tests

Create:

```text
tests/integration/test_report_semantic_goal_fields.py
```

Tests:

```python
test_report_schema_accepts_semantic_goal_results
test_report_schema_accepts_verified_no_change_reason
test_verified_no_change_report_without_semantic_goal_results_rejected_when_goal_exists
test_verified_no_change_report_with_failing_semantic_goal_result_rejected
test_verified_no_change_report_with_passing_semantic_goal_result_and_gate_passes_accepted
test_complete_report_with_semantic_goal_result_passes_when_gate_passes
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_report_semantic_goal_fields.py
```

---

# Phase 8 — Status, monitor, and live progress

## Goal

Expose semantic verification clearly.

## Live progress examples

```text
[cxor +001s] semantic goal G001: app.py main() must return "me"
[cxor +010s] semantic probe G001 failed: expected "me", got "ok"
[cxor +011s] patchlet P0001 rejected: semantic_goal_not_satisfied
```

## Status JSON

Add:

```json
{
  "semantic": {
    "semantic_done": false,
    "goals": [
      {
        "goal_id": "G001",
        "expected": "me",
        "actual": "ok",
        "status": "FAILED"
      }
    ]
  }
}
```

## Tests

Create:

```text
tests/integration/test_semantic_goal_operator_visibility.py
```

Tests:

```python
test_live_progress_prints_semantic_goal_started
test_live_progress_prints_semantic_probe_passed
test_live_progress_prints_semantic_probe_failed
test_monitor_lists_semantic_goal_events
test_status_json_includes_semantic_goal_status
test_status_json_shows_expected_and_actual_values
test_compact_output_does_not_dump_probe_body
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_semantic_goal_operator_visibility.py
```

---

# Phase 9 — Full-chain false-DONE reproduction

## Goal

Reproduce the live false positive without real Codex.

## Scenario

```text
target app.py returns "ok"
master_prompt_me.md says Make app return me and prove it.
fake worker writes VERIFIED_NO_CHANGE_NEEDED
fake report is structurally valid
fake report says no changed_product_runtime_file
```

Expected:

```text
semantic gate fails
workflow does not reach DONE
failure category semantic_goal_not_satisfied
final_verification semantic_goals_valid=false
operator status shows expected "me", actual "ok"
```

## Tests

Create:

```text
tests/integration/test_semantic_false_done_chain.py
```

Tests:

```python
test_false_done_reproduction_rejected
test_fake_verified_no_change_for_wrong_goal_does_not_reach_done
test_failure_category_semantic_goal_not_satisfied
test_final_verification_records_semantic_failure
test_no_integration_checkpoint_written_after_semantic_failure
test_operator_status_reports_semantic_failure
test_valid_no_change_same_goal_still_reaches_done
test_valid_change_to_me_reaches_done
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_semantic_false_done_chain.py
```

---

# Phase 10 — Docs

Update:

```text
README.md
docs/cli.md
docs/autonomous_loop.md
docs/real_codex_smoke.md
docs/release.md
docs/runbooks/real_codex_smoke_runbook.md
docs/workflow_lifecycle.md
docs/Codex_Orchestrator_Step_By_Step_Usage_Guide.md
IMPLEMENTATION_STATUS.md
```

Create:

```text
docs/semantic_goal_verification.md
```

Docs must explain:

```text
semantic goal spec
acceptance criteria
supported built-in parser
python_function_return goal
semantic probe
semantic gate
VERIFIED_NO_CHANGE_NEEDED restrictions
global verifier semantic enforcement
status semantic fields
manual real-Codex smoke expectations
```

Docs tests:

```text
tests/unit/test_docs_semantic_goal_verification.py
```

Tests:

```python
test_docs_explain_semantic_goal_spec
test_docs_explain_acceptance_criteria
test_docs_explain_python_function_return_goal
test_docs_explain_verified_no_change_requires_semantic_proof
test_docs_explain_semantic_gate_before_done
test_docs_explain_global_verifier_semantic_enforcement
test_docs_include_false_done_example
test_usage_guide_mentions_semantic_goal_verification
```

Run:

```bash
uv run --no-sync pytest -q tests/unit/test_docs_semantic_goal_verification.py
```

---

# Phase 11 — Final verification

Run:

```bash
export UV_CACHE_DIR=/tmp/uv-cache

uv run --no-sync pytest -q tests/unit/test_semantic_goal_parser.py
uv run --no-sync pytest -q tests/integration/test_semantic_goal_artifacts.py
uv run --no-sync pytest -q tests/integration/test_semantic_goal_prompt_binding.py
uv run --no-sync pytest -q tests/integration/test_semantic_probe.py
uv run --no-sync pytest -q tests/integration/test_semantic_goal_gate.py
uv run --no-sync pytest -q tests/integration/test_global_verifier_semantic_goal.py
uv run --no-sync pytest -q tests/integration/test_report_semantic_goal_fields.py
uv run --no-sync pytest -q tests/integration/test_semantic_goal_operator_visibility.py
uv run --no-sync pytest -q tests/integration/test_semantic_false_done_chain.py
uv run --no-sync pytest -q tests/unit/test_docs_semantic_goal_verification.py

uv run --no-sync pytest -q tests/integration/test_auto_rerun_cli_semantics.py
uv run --no-sync pytest -q tests/integration/test_report_ingestion_gate.py
uv run --no-sync pytest -q tests/integration/test_real_codex_probe_ref_loop_chain.py
uv run --no-sync pytest -q tests/integration/test_direct_auto_live_progress.py
uv run --no-sync pytest -q tests/integration/test_target_hygiene_gate.py

uv run --no-sync pytest -q
uv run --no-sync python -m codex_orchestrator --version
uv run --no-sync cxor --version
uv run --no-sync codex-orchestrator --version
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py
git status --short
```

Do not run explicit real Codex.

---

# Manual smoke after deterministic green

Do not run during implementation.

Recommend:

```bash
rm -rf /tmp/cxor-target-semantic-smoke
mkdir -p /tmp/cxor-target-semantic-smoke
cd /tmp/cxor-target-semantic-smoke

git init
cat > app.py <<'PY'
def main():
    return "ok"
PY

cat > master_prompt_me.md <<'MD'
Make app return me and prove it.
MD

git add app.py master_prompt_me.md
git commit -m "Initial semantic target"

CODEX_PATCHLET_TIMEOUT_SECONDS=600 \
uv run --no-sync cxor auto \
  --repo /tmp/cxor-target-semantic-smoke \
  --master /tmp/cxor-target-semantic-smoke/master_prompt_me.md \
  --until DONE \
  --worker-mode real_codex \
  --use-worktree \
  --live-progress
```

Expected after the fix:

```text
If Codex says no change needed while app returns ok:
  semantic gate rejects
  workflow does not reach DONE
  status shows expected me, actual ok

If Codex changes app.py to return me:
  semantic probe passes
  global verifier permits DONE
```

---

# Required final report format

Return exactly:

```text
# Codex TDD Report — Semantic Goal Satisfaction and False-DONE Prevention

## 1. Baseline

## 2. Evidence basis

## 3. Architecture decisions implemented

## 4. Phase results

### Phase 1 — Semantic goal parser
### Phase 2 — Goal spec and acceptance criteria artifacts
### Phase 3 — Prompt binding
### Phase 4 — Semantic probes
### Phase 5 — Semantic goal gate
### Phase 6 — Global verifier enforcement
### Phase 7 — Report semantic fields
### Phase 8 — Operator visibility
### Phase 9 — Full-chain reproduction
### Phase 10 — Docs
### Phase 11 — Final verification

## 5. Semantic goal behavior

## 6. Acceptance criteria behavior

## 7. Semantic probe behavior

## 8. Semantic gate behavior

## 9. Global verifier behavior

## 10. VERIFIED_NO_CHANGE_NEEDED policy

## 11. Operator visibility

## 12. Docs

## 13. Default smoke skip

## 14. Final verification output

## 15. Git status

## 16. Remaining confirmed gaps

## 17. Next single highest-value increment
```

Final next increment if deterministic green:

```text
Run a manual real-Codex semantic smoke and confirm either:
1. Codex changes app.py to return "me" and DONE is valid, or
2. Codex wrongly reports no change needed and the semantic gate blocks DONE with expected="me", actual="ok".
```

---

# Final instruction

Implement semantic goal satisfaction.

Do not run real Codex.

Do not mutate preserved smoke targets.

Do not weaken existing gates.

Do not trust worker-authored probes alone.

Do not allow DONE unless semantic goals pass.

Use fresh temp repos and fake/mock workers for tests.
