# Codex Orchestrator — No-Compatibility Repo-Agnostic Goal Proof and General Work Decomposition Implementation Plan

## Document purpose

This implementation plan is the detailed builder handoff for the architecture file:

```text
Codex_Orchestrator_No_Compatibility_Repo_Agnostic_Goal_Proof_Work_Decomposition_Architecture.md
```

This plan incorporates every approved correction from the design discussion.

It is intentionally strict.

It is intentionally not backward-compatible with the old shortcut architecture.

It is intentionally not compact.

The purpose of this implementation is to replace target-specific parser behavior, repo-specific semantic shortcuts, smoke-shaped regexes, and invariant-collapse fallback behavior with a general, repo-agnostic, language-agnostic orchestration path.

The old architecture used valuable safety gates, but it still allowed or preserved shortcut behavior that is no longer accepted:

```text
hardcoded semantic prompt patterns
fixed target file/function/language assumptions
Python-specific goal recognition
app/main-style fast paths
smoke-scenario parser expansion
legacy compatibility tests
legacy invariant fallback to one global invariant
silent I001 -> P0001 collapse
structural continuation when general artifacts were missing
```

The new implementation must remove those shortcuts and require the full general path:

```text
frozen master prompt
  -> model-mediated goal interpretation
  -> early provability classification
  -> model-mediated proof obligation planning
  -> model/repo-aware probe planning
  -> repo inventory and impact/dependency analysis
  -> general work decomposition
  -> patchlet plan
  -> dependency graph
  -> transaction group plan
  -> small bounded patchlets
  -> independent proof rerun or validation
  -> goal coverage gate
  -> global master-prompt concordance verifier
  -> global master-prompt satisfaction verifier
  -> DONE only if the frozen master prompt is proven satisfied
```

---

## 0. Final approved architecture rules

### 0.1 Remove all backwards and compatibility shims

This is a breaking pre-release correction.

The implementation must remove all backward and compatibility shims related to the old shortcut architecture.

Required removals:

```text
Remove hardcoded semantic prompt pattern recognition from the general path.
Remove repo-specific semantic shortcuts.
Remove target-file-specific semantic shortcuts.
Remove target-function-specific semantic shortcuts.
Remove language-specific semantic assumptions from the general path.
Remove smoke-scenario regex patterns.
Remove legacy fast-path tests whose purpose is preserving the old shortcut behavior.
Remove docs that present the old fast path as a supported general architecture.
Remove compile_patchlets legacy invariant fallback as normal behavior.
Remove silent fallback to a single global invariant and a single patchlet.
Remove structural continuation when goal interpretation, proof obligations, probe plan, or decomposition artifacts are missing.
```

The implementation must not create a new compatibility adapter under another name.

Do not create:

```text
legacy_builtin_goal_adapter.py
compat_goal_adapter.py
semantic_fast_path.py
old_semantic_adapter.py
app_main_adapter.py
parser_backcompat.py
```

If a module exists only to preserve the old shortcut behavior, remove it or replace it with a general model-mediated implementation.

### 0.2 Master prompt is the source of truth

The master prompt is read-only source of truth.

The following artifacts are derived artifacts, not sources of truth:

```text
goal_interpretation.json
proof_obligations.json
probe_plan.json
work_decomposition_plan.json
work_slices.json
patchlet_plan.json
dependency_graph.json
transaction_group_plan.json
worker reports
worker-authored probes
model responses
```

The final verifier must check that the accepted integration state satisfies the frozen master prompt itself.

Internal consistency of derived artifacts is necessary but not sufficient.

### 0.3 Model-mediated goal interpretation is required

All goal interpretation must go through a model-mediated, repo-agnostic process.

The model must be the configured verifier/global-verifier model class used by the orchestrator.

The model must receive:

```text
frozen master prompt
source spans
repo census summary
repo inventory summary
detected languages/frameworks, if discovered from repo evidence
current proof contract instructions
strict goal interpretation schema
```

The model must return structured goal items.

The orchestrator must preserve raw model IO, validate the response, normalize it, and block the workflow if the response is invalid, ambiguous, contradictory, ungrounded, or not source-span-linked.

### 0.4 Model-mediated proof obligation planning is required

Proof obligations must be proposed by a model-mediated proof planner.

The orchestrator validates the plan.

The model may propose executable, static, existing-test, artifact-inspection, or composite proof strategies.

The orchestrator decides whether the obligations are acceptable.

No proof obligation is accepted unless it is:

```text
traceable to goal items
traceable to frozen master prompt spans
schema-valid
concrete enough to verify
linked to evidence requirements
covered by at least one rerunnable or independently validatable probe
```

### 0.5 Model/repo-aware probe planning is required

Probe planning must be repo-aware but not repo-specific in code.

The probe planner may propose probes based on discovered repo facts.

The orchestrator validates safety, side effects, rerunnability, and coverage.

Worker-proposed probes are not proof until validated or rerun by the orchestrator.

### 0.6 Work decomposition artifacts are mandatory

Patchlet compilation must require general work-decomposition artifacts.

Required artifacts:

```text
.codex-orchestrator/decomposition/impact_dependency_analysis.json
.codex-orchestrator/decomposition/work_decomposition_plan.json
.codex-orchestrator/decomposition/work_slices.json
.codex-orchestrator/decomposition/patchlet_plan.json
.codex-orchestrator/decomposition/dependency_graph.json
.codex-orchestrator/decomposition/transaction_group_plan.json
```

If those artifacts are missing or invalid, product-editing patchlets must not compile.

There must be no fallback to a single global invariant.

### 0.7 Correct patchlet decomposition rule

The architecture is not:

```text
one file -> one patchlet
```

The architecture is:

```text
one patchlet -> exactly one allowed product/runtime file
```

Multiple patchlets may target the same product/runtime file.

Each patchlet is a small bounded work unit.

Each patchlet has:

```text
exactly one allowed product/runtime file
one work slice
proof obligation references
goal item references
dependency references
time budget seconds
prompt scope boundaries
memory compacting avoidance policy
```

### 0.8 Patchlet budget and no-memory-compacting rule

Each patchlet must fit the task time budget.

Default:

```text
CODEX_PATCHLET_TIMEOUT_SECONDS = 600
```

If the environment overrides this value, the following must all agree:

```text
patchlet_plan.json
patchlet_index.json
worker prompt
worker memory contracts
command timeout
soft deadline
operator events
run manifest
status output
```

Patchlet prompts must avoid memory compacting by being narrow, bounded, self-contained, and single-edit-file scoped.

### 0.9 Early safe failure

The workflow must stop before product-editing patchlets if it cannot produce and validate:

```text
master_prompt_frozen.json
goal_interpretation.json
provability_result.json
proof_obligations.json
probe_plan.json
impact_dependency_analysis.json
work_decomposition_plan.json
work_slices.json
patchlet_plan.json
dependency_graph.json
transaction_group_plan.json
```

Early safe-failure signatures include:

```text
goal_not_interpretable
goal_ambiguous
goal_unprovable
goal_blocked_by_missing_capability
proof_obligations_invalid
probe_plan_invalid
work_decomposition_invalid
patchlet_plan_invalid
missing_required_orchestration_artifact
```

### 0.10 DONE eligibility

DONE requires:

```text
frozen master prompt exists
model-mediated goal interpretation accepted
provability accepted as sufficient to proceed
proof obligations accepted
probe plan accepted
work decomposition accepted
patchlet plan accepted
required obligations proven by orchestrator-owned rerun or validation
goal coverage accepted
transaction groups accepted
integration artifacts valid
target hygiene passed
master prompt concordance accepted
master prompt satisfaction accepted
no unresolved required obligations
no unresolved failures
```

DONE must be impossible when any required artifact is missing, invalid, ambiguous, or failed.

---

## 1. Implementation strategy overview

The implementation should be staged as a TDD refactor.

The implementation must start by removing shortcut assumptions, then introducing strict model-mediated and decomposition-required gates.

The order matters.

A safe order is:

```text
1. Baseline and inventory current shortcuts.
2. Remove shortcut parser behavior and tests.
3. Add model-mediated goal interpretation request/response artifacts.
4. Add model-mediated proof planning request/response artifacts.
5. Add model/repo-aware probe planning request/response artifacts.
6. Make missing interpretation/proof/probe artifacts safe-fail before patchlets.
7. Remove invariant fallback from patchlet compilation.
8. Make decomposition artifacts mandatory before patchlet compilation.
9. Enforce exactly one allowed product/runtime file per patchlet.
10. Preserve multiple patchlets per same file.
11. Enforce patchlet time budget and narrow prompt scope.
12. Integrate independent proof rerun and goal coverage.
13. Integrate master prompt concordance and satisfaction.
14. Add stop/partial apply regression coverage.
15. Add operator visibility and docs.
16. Run full suite.
```

---

## 2. Step-by-step builder instructions

### Step 2.1 Baseline

Run:

```bash
export UV_CACHE_DIR=/tmp/uv-cache

date -u +"%Y-%m-%dT%H:%M:%SZ"
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
uv run --no-sync python -m codex_orchestrator --version
uv run --no-sync cxor --version
uv run --no-sync codex-orchestrator --version
```

Create:

```text
no_compat_repo_agnostic_goal_proof_decomposition_implementation_note.md
```

Record:

```text
baseline full suite
default smoke skip
current HEAD
git status
known shortcut files
known fallback code paths
planned removals
planned additions
rollback plan
```

Stop if the baseline suite is red.

### Step 2.2 Source inspection

Run:

```bash
rg -n "semantic_goals|PATTERNS|app\.main|app\.py|builtin|compat|legacy|fast path|fallback|I001|P0001|extract_invariants|compile_patchlets|proof_obligations|probe_plan|work_decomposition|patchlet_plan|goal_interpretation|model_request|model_response|CODEX_PATCHLET_TIMEOUT_SECONDS" \
  src tests docs README.md IMPLEMENTATION_STATUS.md || true
```

Inspect likely files:

```bash
sed -n '1,3200p' src/codex_orchestrator/semantic_goals.py 2>/dev/null || true
sed -n '1,3600p' src/codex_orchestrator/stages/normalize.py
sed -n '1,3600p' src/codex_orchestrator/stages/extract_invariants.py
sed -n '1,4200p' src/codex_orchestrator/stages/compile_patchlets.py
sed -n '1,3600p' src/codex_orchestrator/proof_obligations.py
sed -n '1,3600p' src/codex_orchestrator/probe_plan.py
sed -n '1,3600p' src/codex_orchestrator/work_decomposition.py 2>/dev/null || true
sed -n '1,3600p' src/codex_orchestrator/work_slice_planner.py 2>/dev/null || true
sed -n '1,3600p' src/codex_orchestrator/patchlet_planner.py 2>/dev/null || true
sed -n '1,3600p' src/codex_orchestrator/stages/run_patchlet.py
sed -n '1,3600p' src/codex_orchestrator/stages/verify_global.py
sed -n '1,3600p' src/codex_orchestrator/worker_capsule.py
```

Record in the implementation note:

```text
all shortcut parser code found
all app/function/language-specific semantic assumptions found
all legacy compatibility tests found
all docs describing old fast path
all fallback paths from missing decomposition to invariants
all I001/P0001 assumptions
all patchlet compiler fallback paths
```

### Step 2.3 Remove shortcut semantic behavior

Remove or neutralize any general-path code that recognizes fixed prompt strings and maps them to fixed file/function/language shapes.

Required removals:

```text
hardcoded semantic PATTERNS
fixed target file names in the semantic interpreter
fixed function names in the semantic interpreter
language-specific assumptions in the general semantic interpreter
smoke-specific prompt patterns
```

If a module has no remaining general purpose after removals, remove it.

If import references break, replace them with the new model-mediated flow.

Do not create a legacy adapter.

Do not keep a compatibility parser.

### Step 2.4 Add no-compatibility tests

Create:

```text
tests/integration/test_no_compatibility_shortcuts.py
```

Behavior-facing tests should include:

```python
def test_pipeline_like_prompt_does_not_create_fixed_app_main_semantic_spec(...):
    ...

def test_missing_model_goal_interpretation_safe_fails_before_workers(...):
    ...

def test_missing_proof_obligations_safe_fails_before_workers(...):
    ...

def test_missing_probe_plan_safe_fails_before_workers(...):
    ...

def test_missing_decomposition_artifacts_do_not_fallback_to_single_invariant(...):
    ...

def test_compile_patchlets_requires_patchlet_plan(...):
    ...
```

If a source-level removal test is unavoidable, make it narrow and targeted. Prefer generated-artifact behavior.

Expected behavior:

```text
No generated semantic artifact should contain fixed app/main/Python assumptions unless they were explicitly derived by the model response and validated against the target repo.
Missing general artifacts must safe-fail.
Missing decomposition artifacts must not produce I001 -> P0001 fallback.
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_no_compatibility_shortcuts.py
```

---

## 3. Phase A — Model-mediated goal interpretation

### 3.1 Goal

Replace parser-based semantic goal extraction with model-mediated goal interpretation.

### 3.2 Artifacts

Create directory:

```text
.codex-orchestrator/goal_interpretation/
```

Write:

```text
.codex-orchestrator/goal_interpretation/model_request.json
.codex-orchestrator/goal_interpretation/model_response.raw.json
.codex-orchestrator/goal_interpretation/goal_interpretation.json
.codex-orchestrator/goal_interpretation/validation_result.json
```

### 3.3 Schema

Add or update:

```text
src/codex_orchestrator/schemas/goal_interpretation.schema.json
src/codex_orchestrator/schemas/goal_interpretation_validation_result.schema.json
```

### 3.4 Model request shape

```json
{
  "schema_version": "1.0",
  "kind": "goal_interpretation_model_request",
  "workflow_id": "WF...",
  "run_id": "R0001",
  "master_prompt_sha256": "<sha>",
  "master_prompt_frozen_path": ".codex-orchestrator/master_prompt_frozen.json",
  "source_spans": [],
  "repo_context": {
    "census_summary_path": ".codex-orchestrator/census/...",
    "inventory_summary_path": ".codex-orchestrator/inventory_graph.json",
    "detected_languages": [],
    "detected_frameworks": [],
    "entrypoint_candidates": []
  },
  "instructions": {
    "master_prompt_is_source_of_truth": true,
    "do_not_claim_proof": true,
    "do_not_assume_language_or_framework": true,
    "derive_repo_context_from_supplied_evidence_only": true,
    "return_schema": "goal_interpretation.schema.json"
  }
}
```

### 3.5 Normalized goal interpretation shape

```json
{
  "schema_version": "1.0",
  "kind": "goal_interpretation",
  "workflow_id": "WF...",
  "run_id": "R0001",
  "master_prompt_sha256": "<sha>",
  "master_prompt_frozen_path": ".codex-orchestrator/master_prompt_frozen.json",
  "interpretation_status": "CONCORDANT",
  "goal_items": [
    {
      "goal_item_id": "GI001",
      "source_span_ids": ["MPS001"],
      "goal_type": "behavioral_change",
      "repo_context": {
        "language_or_framework": "derived_from_repo",
        "entrypoints": ["derived_from_repo"],
        "affected_runtime_boundaries": ["derived_from_repo"]
      },
      "desired_state": "derived from frozen master prompt",
      "success_conditions": ["derived proof condition"],
      "required": true
    }
  ],
  "ambiguities": [],
  "assumptions": [],
  "proof_not_claimed_here": true
}
```

### 3.6 Gate rules

Block if:

```text
model_request.json missing
model_response.raw.json missing
raw response invalid
normalized artifact missing
schema invalid
no goal items
required goal item lacks source span
interpretation claims proof
interpretation contradicts frozen master prompt
interpretation uses repo facts not present in repo context
```

### 3.7 Tests

Create:

```text
tests/integration/test_model_mediated_goal_interpretation.py
```

Tests:

```python
def test_goal_interpretation_model_request_written(...): ...
def test_goal_interpretation_raw_response_preserved(...): ...
def test_goal_interpretation_schema_validates(...): ...
def test_goal_interpretation_references_master_prompt_hash(...): ...
def test_goal_interpretation_references_source_spans(...): ...
def test_goal_interpretation_does_not_claim_proof(...): ...
def test_invalid_goal_interpretation_safe_fails(...): ...
def test_contradictory_goal_interpretation_safe_fails(...): ...
def test_ambiguous_goal_interpretation_safe_fails_before_product_patchlets(...): ...
def test_goal_interpretation_does_not_assume_fixed_file_or_language(...): ...
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_model_mediated_goal_interpretation.py
```

---

## 4. Phase B — Model-mediated proof-obligation planning

### 4.1 Goal

Generate proof obligations through a model-mediated proof planner, then validate them with orchestrator rules.

### 4.2 Artifacts

```text
.codex-orchestrator/proof_planning/model_request.json
.codex-orchestrator/proof_planning/model_response.raw.json
.codex-orchestrator/proof_planning/proof_obligations.json
.codex-orchestrator/proof_planning/validation_result.json
.codex-orchestrator/proof_obligations.json
```

The root-level `proof_obligations.json` may be canonical, with the proof-planning directory preserving request/response lineage.

### 4.3 Model request

```json
{
  "schema_version": "1.0",
  "kind": "proof_obligation_model_request",
  "workflow_id": "WF...",
  "run_id": "R0001",
  "master_prompt_sha256": "<sha>",
  "goal_interpretation_path": ".codex-orchestrator/goal_interpretation/goal_interpretation.json",
  "instructions": {
    "proof_plan_is_not_source_of_truth": true,
    "derive_obligations_from_goal_items": true,
    "map_every_required_goal_item_to_obligations": true,
    "require_independent_verifiability": true,
    "do_not_assume_language_or_framework": true,
    "return_schema": "proof_obligations.schema.json"
  }
}
```

### 4.4 Proof obligations

```json
{
  "schema_version": "1.0",
  "kind": "proof_obligations",
  "workflow_id": "WF...",
  "run_id": "R0001",
  "master_prompt_sha256": "<sha>",
  "obligations": [
    {
      "obligation_id": "PO001",
      "goal_item_ids": ["GI001"],
      "source_span_ids": ["MPS001"],
      "obligation_type": "behavioral_runtime_claim",
      "claim": "The accepted integration state satisfies the requested behavior.",
      "proof_strategy": "executable_probe",
      "required": true,
      "language": "derived_or_unknown",
      "target_boundaries": ["derived_from_repo"],
      "status": "UNPROVEN",
      "evidence_requirements": [
        "expected_actual_record",
        "orchestrator_rerun_or_validation",
        "coverage_link_to_master_prompt"
      ]
    }
  ]
}
```

### 4.5 Gate rules

Block if:

```text
required goal item has no obligation
obligation references missing goal item
obligation references missing source span
obligation lacks proof strategy
obligation lacks evidence requirements
obligation depends on hidden model reasoning
obligation is not independently verifiable
```

### 4.6 Tests

Create:

```text
tests/integration/test_model_mediated_proof_planning.py
```

Tests:

```python
def test_proof_planning_model_request_written(...): ...
def test_proof_planning_raw_response_preserved(...): ...
def test_proof_obligations_schema_validates(...): ...
def test_required_goal_item_requires_obligation(...): ...
def test_obligation_requires_source_span_link(...): ...
def test_obligation_requires_proof_strategy(...): ...
def test_obligation_requires_evidence_requirements(...): ...
def test_invalid_proof_obligation_safe_fails(...): ...
def test_proof_obligations_do_not_assume_fixed_file_or_language(...): ...
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_model_mediated_proof_planning.py
```

---

## 5. Phase C — Model/repo-aware probe planning

### 5.1 Goal

Generate probe plans through a model-mediated or repo-aware planner and require orchestrator validation.

### 5.2 Artifacts

```text
.codex-orchestrator/probe_planning/model_request.json
.codex-orchestrator/probe_planning/model_response.raw.json
.codex-orchestrator/probe_planning/probe_plan.json
.codex-orchestrator/probe_planning/validation_result.json
.codex-orchestrator/probe_plan.json
```

### 5.3 Probe plan

```json
{
  "schema_version": "1.0",
  "kind": "probe_plan",
  "workflow_id": "WF...",
  "run_id": "R0001",
  "master_prompt_sha256": "<sha>",
  "probes": [
    {
      "probe_id": "GP001",
      "obligation_ids": ["PO001"],
      "probe_kind": "executable",
      "owner": "model_planned_orchestrator_validated",
      "execution_context": "integration_candidate",
      "command": null,
      "script_path": ".codex-orchestrator/probes/generated/GP001/probe",
      "expected_observation": {
        "type": "derived_from_proof_obligation"
      },
      "rerunnable_by_orchestrator": true,
      "side_effect_policy": "no_product_mutation"
    }
  ]
}
```

### 5.4 Gate rules

Block if:

```text
required proof obligation has no probe
probe is not rerunnable or independently validatable
probe has unsafe side effects
probe lacks expected observation
probe lacks obligation linkage
probe is worker-proposed but unvalidated
```

### 5.5 Tests

Create:

```text
tests/integration/test_model_mediated_probe_planning.py
```

Tests:

```python
def test_probe_planning_model_request_written(...): ...
def test_probe_planning_raw_response_preserved(...): ...
def test_probe_plan_schema_validates(...): ...
def test_required_obligation_requires_probe(...): ...
def test_required_probe_must_be_rerunnable_or_validatable(...): ...
def test_worker_proposed_probe_not_trusted_without_validation(...): ...
def test_probe_with_product_mutation_policy_rejected(...): ...
def test_probe_without_expected_observation_rejected(...): ...
def test_probe_plan_does_not_assume_fixed_language(...): ...
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_model_mediated_probe_planning.py
```

---

## 6. Phase D — Remove invariant fallback and require decomposition

### 6.1 Goal

Make decomposition mandatory before patchlet compilation.

### 6.2 Required code change

`compile_patchlets` must not use invariant fallback as normal behavior.

The new logic must be:

```text
load patchlet_plan.json
if missing: safe-fail before product patchlets
if invalid: safe-fail before product patchlets
validate one allowed product/runtime file per patchlet
compile patchlet_index.json from patchlet_plan.json
```

Do not do:

```text
if no patchlet_plan:
    iterate invariants
    produce P0001
```

### 6.3 Tests

Create:

```text
tests/integration/test_general_work_decomposition_no_fallbacks.py
```

Tests:

```python
def test_compile_patchlets_requires_patchlet_plan(...): ...
def test_missing_patchlet_plan_safe_fails_before_workers(...): ...
def test_missing_work_slices_safe_fails_before_compile_patchlets(...): ...
def test_missing_dependency_graph_safe_fails_before_compile_patchlets(...): ...
def test_no_fallback_to_I001_P0001_when_decomposition_missing(...): ...
def test_invalid_patchlet_plan_safe_fails(...): ...
def test_patchlet_plan_with_multiple_allowed_files_rejected(...): ...
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_general_work_decomposition_no_fallbacks.py
```

---

## 7. Phase E — General work decomposition

### 7.1 Goal

Generate real decomposition artifacts from proof obligations, probe plan, inventory, and impact analysis.

### 7.2 Artifacts

```text
.codex-orchestrator/decomposition/impact_dependency_analysis.json
.codex-orchestrator/decomposition/work_decomposition_plan.json
.codex-orchestrator/decomposition/work_slices.json
.codex-orchestrator/decomposition/patchlet_plan.json
.codex-orchestrator/decomposition/dependency_graph.json
.codex-orchestrator/decomposition/transaction_group_plan.json
```

### 7.3 Rules

```text
A work slice is a bounded task.
A work slice is not simply a file.
Every work slice has exactly one allowed edit file.
Several work slices may target the same file.
Every patchlet maps to exactly one work slice.
Every patchlet has exactly one allowed product/runtime file.
Every patchlet references proof obligations.
Every patchlet has dependency metadata.
Every patchlet has time_budget_seconds.
Every patchlet has no-memory-compacting prompt policy.
```

### 7.4 Tests

Create or update:

```text
tests/integration/test_multi_patchlet_decomposition.py
tests/integration/test_general_work_decomposition_no_fallbacks.py
```

Tests:

```python
def test_complex_target_generates_multiple_work_slices(...): ...
def test_complex_target_generates_multiple_patchlets(...): ...
def test_every_patchlet_has_exactly_one_allowed_file(...): ...
def test_multiple_patchlets_may_target_same_file(...): ...
def test_patchlet_plan_records_600_second_budget(...): ...
def test_patchlet_plan_records_no_memory_compacting(...): ...
def test_dependency_graph_orders_same_file_patchlets(...): ...
def test_transaction_group_plan_derived_from_dependency_layers(...): ...
def test_no_manual_artifact_tampering_required(...): ...
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_multi_patchlet_decomposition.py
```

---

## 8. Phase F — Patchlet prompt scoping and budget

### 8.1 Goal

Every patchlet prompt must be slice-scoped, budget-aware, and exactly-one-edit-file constrained.

### 8.2 Required worker memory

Create:

```text
WORK_SLICE_CONTRACT.md
PROOF_OBLIGATION_CONTRACT.md
PROBE_PLAN_CONTRACT.md
```

### 8.3 Prompt requirements

Each prompt must include:

```text
patchlet_id
work_slice_id
allowed_product_runtime_file
forbidden product/runtime files
time_budget_seconds
soft deadline
proof_obligation_ids
goal_item_ids
dependency_patchlet_ids
scope statement
what this patchlet must do
what this patchlet must not do
no memory compacting rule
local proof requirements
independent rerun expectations
```

### 8.4 Tests

Create or update:

```text
tests/integration/test_patchlet_prompt_scope_and_budget.py
```

Tests:

```python
def test_worker_prompt_includes_work_slice_id(...): ...
def test_worker_prompt_includes_exactly_one_allowed_file(...): ...
def test_worker_prompt_forbids_other_product_runtime_files(...): ...
def test_worker_prompt_includes_600_second_default_budget(...): ...
def test_worker_prompt_uses_timeout_env_override(...): ...
def test_worker_prompt_mentions_small_bounded_work_unit(...): ...
def test_worker_prompt_says_do_not_solve_unrelated_slices(...): ...
def test_worker_prompt_says_no_memory_compacting_required(...): ...
def test_work_slice_contract_written(...): ...
def test_proof_obligation_contract_written(...): ...
def test_probe_plan_contract_written(...): ...
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_patchlet_prompt_scope_and_budget.py
```

---

## 9. Phase G — Master prompt concordance and satisfaction

### 9.1 Goal

Ensure final verification checks the frozen master prompt itself.

### 9.2 Required global artifacts

```text
.codex-orchestrator/global_verification/master_prompt_concordance_result.json
.codex-orchestrator/global_verification/master_prompt_satisfaction_result.json
.codex-orchestrator/global_verification/verification_matrix.json
```

### 9.3 DONE gate

DONE requires:

```text
concordance accepted
satisfaction accepted
all required obligations proven by orchestrator
all required goal items covered
no failed required obligations
no blocked required obligations
no unresolved failures
```

### 9.4 Tests

Create or update:

```text
tests/integration/test_master_prompt_satisfaction_verifier.py
```

Tests:

```python
def test_done_requires_master_prompt_concordance(...): ...
def test_done_requires_master_prompt_satisfaction(...): ...
def test_done_blocked_when_goal_item_uncovered(...): ...
def test_done_blocked_when_obligation_unproven(...): ...
def test_done_blocked_when_probe_not_rerun(...): ...
def test_done_blocked_when_decomposition_missing(...): ...
def test_done_blocked_when_patchlet_plan_missing(...): ...
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_master_prompt_satisfaction_verifier.py
```

---

## 10. Phase H — Stop and partial apply

### 10.1 Goal

Ensure stop and partial apply still work after the no-compatibility and decomposition changes.

### 10.2 Rules

```text
stop request writes stop_requested.json
auto loop stops at safe boundary
stop_result.json records latest accepted checkpoint
partial apply requires --allow-partial
partial apply uses accepted integration checkpoint only
in-progress work is not applied
failed work is not applied
partial apply warns master prompt may not be fully satisfied
```

### 10.3 Tests

Create or update:

```text
tests/integration/test_stop_and_partial_apply.py
```

Tests:

```python
def test_stop_writes_stop_requested(...): ...
def test_auto_stops_at_safe_boundary(...): ...
def test_stop_result_records_latest_accepted_checkpoint(...): ...
def test_partial_apply_requires_allow_partial(...): ...
def test_partial_apply_uses_accepted_checkpoint_only(...): ...
def test_partial_apply_does_not_apply_in_progress_work(...): ...
def test_partial_apply_warns_master_prompt_may_not_be_satisfied(...): ...
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_stop_and_partial_apply.py
```

---

## 11. Phase I — Operator visibility

### 11.1 Commands

Ensure these commands work:

```bash
cxor goal-progress --repo <repo>
cxor goal-progress --repo <repo> --json
cxor decomposition --repo <repo>
cxor decomposition --repo <repo> --json
cxor monitor --repo <repo>
cxor status --repo <repo> --json
```

### 11.2 Status JSON

Status must include:

```json
{
  "master_prompt_proof": {
    "provability_status": "PROVABLE",
    "proof_obligations_path": ".codex-orchestrator/proof_obligations.json",
    "probe_plan_path": ".codex-orchestrator/probe_plan.json",
    "master_prompt_satisfaction_status": "SATISFIED"
  },
  "decomposition": {
    "work_slice_count": 5,
    "patchlet_count": 5,
    "same_file_multi_patchlet_groups": [],
    "decomposition_plan_path": ".codex-orchestrator/decomposition/work_decomposition_plan.json"
  },
  "goal_progress": {
    "required_obligations": 3,
    "proven": 2,
    "failed": 0,
    "blocked": 0,
    "unproven": 1
  }
}
```

### 11.3 Tests

Create or update:

```text
tests/integration/test_general_goal_proof_operator_visibility.py
tests/integration/test_decomposition_operator_visibility.py
```

Tests:

```python
def test_status_json_includes_master_prompt_proof(...): ...
def test_status_json_includes_decomposition(...): ...
def test_status_json_includes_goal_progress(...): ...
def test_monitor_shows_model_interpretation_events(...): ...
def test_monitor_shows_decomposition_events(...): ...
def test_live_progress_shows_early_safe_failure(...): ...
def test_live_progress_shows_decomposition_summary(...): ...
```

---

## 12. Phase J — Documentation

### 12.1 Update docs

Update:

```text
README.md
docs/cli.md
docs/autonomous_loop.md
docs/general_goal_proof_contract.md
docs/goal_progress_and_partial_apply.md
docs/general_work_decomposition.md
docs/multi_patchlet_transaction_graph.md
docs/semantic_goal_satisfaction.md
docs/workflow_lifecycle.md
docs/real_codex_smoke.md
docs/release.md
docs/runbooks/real_codex_smoke_runbook.md
docs/Codex_Orchestrator_Step_By_Step_Usage_Guide.md
IMPLEMENTATION_STATUS.md
```

### 12.2 Remove docs language

Remove or rewrite docs language that presents:

```text
app.py fast path
app.main semantic parser
Python-specific general behavior
legacy compatibility fallback
I001 -> P0001 fallback
```

### 12.3 Add docs language

Docs must explain:

```text
no target-specific parser
no compatibility shortcuts
master prompt source of truth
model-mediated goal interpretation
model-mediated proof planning
model/repo-aware probe planning
early provability
mandatory decomposition artifacts
one patchlet exactly one allowed file
multiple patchlets same file allowed
600-second patchlet budget
no memory compacting
independent proof validation
master prompt satisfaction
stop and partial apply
```

### 12.4 Tests

Create or update:

```text
tests/unit/test_docs_general_goal_proof_contract.py
tests/unit/test_docs_general_work_decomposition.py
tests/unit/test_docs_multi_patchlet_transaction_graph.py
tests/unit/test_docs_no_compatibility_shortcuts.py
```

Run:

```bash
uv run --no-sync pytest -q tests/unit/test_docs_general_goal_proof_contract.py tests/unit/test_docs_general_work_decomposition.py tests/unit/test_docs_multi_patchlet_transaction_graph.py tests/unit/test_docs_no_compatibility_shortcuts.py
```

---

## 13. Phase K — Final verification

### 13.1 Focused suites

Run:

```bash
export UV_CACHE_DIR=/tmp/uv-cache

uv run --no-sync pytest -q tests/integration/test_no_compatibility_shortcuts.py
uv run --no-sync pytest -q tests/integration/test_model_mediated_goal_interpretation.py
uv run --no-sync pytest -q tests/integration/test_model_mediated_proof_planning.py
uv run --no-sync pytest -q tests/integration/test_model_mediated_probe_planning.py
uv run --no-sync pytest -q tests/integration/test_general_work_decomposition_no_fallbacks.py
uv run --no-sync pytest -q tests/integration/test_multi_patchlet_decomposition.py
uv run --no-sync pytest -q tests/integration/test_master_prompt_satisfaction_verifier.py
uv run --no-sync pytest -q tests/integration/test_stop_and_partial_apply.py
uv run --no-sync pytest -q tests/integration/test_general_goal_proof_operator_visibility.py
uv run --no-sync pytest -q tests/integration/test_decomposition_operator_visibility.py
```

### 13.2 Full suite

Run:

```bash
uv run --no-sync pytest -q
uv run --no-sync python -m codex_orchestrator --version
uv run --no-sync cxor --version
uv run --no-sync codex-orchestrator --version
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py
git status --short
```

Default smoke must still skip.

Do not run explicit real Codex during implementation.

---

## 14. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Removing shortcut parser breaks old tests | Old tests may expect fixed semantic behavior | Rewrite tests to prove general model-mediated artifacts, not shortcut behavior |
| Model interpretation is wrong | Wrong goal items could be generated | Preserve raw response, schema validate, source-span link, concordance gate |
| Model proof obligations are weak | Wrong thing may be proven | Require obligation-to-goal coverage, rerunnable probes, satisfaction verifier |
| Probe plan is unsafe | Probe may mutate repo or be non-repeatable | Side-effect policy, isolated execution, no product mutation |
| Decomposition missing | Patchlet compilation could accidentally continue | Hard gate: no patchlet plan, no compile_patchlets |
| Decomposition creates fake patchlets | Patchlet count inflated without value | Every patchlet maps to work slice, obligation, dependency, and one allowed file |
| Same-file patchlets conflict | Later patchlet may overwrite earlier work | Same-file patchlets ordered by default |
| Ambiguous goals stop more often | Users may see safe failures | Safer than false DONE; clear evidence and next actions |
| Partial apply misapplies work | Could apply unaccepted scratch | Apply only accepted checkpoint/integration ref |
| Real Codex smoke may need new prompts | The general model path changes pre-worker behavior | First validate with deterministic fake model responses, then opt-in real smoke |

---

## 15. Final report format for builder

The builder must return this structure:

```text
# Codex TDD Report — No-Compatibility Repo-Agnostic Goal Proof and Work Decomposition

## 1. Baseline
- Python:
- uv:
- codex version:
- initial full test result:
- default smoke result:
- git status at start:
- current branch:
- HEAD:

## 2. Removed shortcut behavior
- semantic_goals.py status:
- hardcoded PATTERNS removed:
- app.py/app.main parser removed:
- Python-specific semantic assumptions removed:
- smoke regexes removed:
- legacy tests removed or rewritten:
- docs shortcut language removed:
- invariant fallback removed:

## 3. New model-mediated architecture implemented
- goal interpretation model request:
- goal interpretation raw response:
- goal_interpretation.json:
- proof planning model request:
- proof planning raw response:
- proof_obligations.json:
- probe planning model request:
- probe planning raw response:
- probe_plan.json:

## 4. Mandatory decomposition implemented
- impact_dependency_analysis.json:
- work_decomposition_plan.json:
- work_slices.json:
- patchlet_plan.json:
- dependency_graph.json:
- transaction_group_plan.json:
- compile_patchlets requires patchlet plan:
- no I001/P0001 fallback:

## 5. Gates implemented
- master prompt freeze gate:
- goal interpretation gate:
- provability gate:
- proof obligation gate:
- probe plan gate:
- decomposition gate:
- independent proof gate:
- goal coverage gate:
- master prompt concordance gate:
- master prompt satisfaction gate:

## 6. Patchlet behavior
- one allowed product/runtime file per patchlet:
- multiple patchlets per same file:
- time budget propagation:
- no memory compacting:
- dependency ordering:

## 7. Stop and partial apply
- stop behavior:
- partial apply behavior:
- accepted checkpoint only:
- unaccepted work protection:

## 8. Operator visibility
- status JSON:
- monitor:
- live progress:
- goal-progress:
- decomposition command:

## 9. Tests
- no compatibility tests:
- model interpretation tests:
- proof planning tests:
- probe planning tests:
- decomposition no-fallback tests:
- multi-patchlet tests:
- master prompt satisfaction tests:
- stop/partial apply tests:
- docs tests:

## 10. Final verification
- uv run --no-sync pytest -q:
- version commands:
- default smoke skip:

## 11. Git status
- exact git status --short:

## 12. Remaining confirmed gaps
- list only confirmed gaps:

## 13. Next single highest-value increment
- recommended next step:
```

---

## 16. Final implementation instruction

Implement the no-compatibility repo-agnostic goal proof and work decomposition architecture.

Do not run explicit real Codex during implementation.

Do not mutate preserved targets.

Do not delete evidence.

Do not preserve old shortcuts.

Do not keep app.py/app.main/Python-specific semantic parsers.

Do not keep smoke-specific regexes.

Do not keep invariant fallback to I001/P0001.

Do not let missing model-mediated artifacts continue structurally.

Do not let missing decomposition artifacts compile patchlets.

Do not let worker proof alone satisfy obligations.

Do not let DONE occur without master prompt satisfaction.

Use TDD.

Use behavior-facing tests.

Use fresh temp repos.

Stop only at a real safety boundary, failing full suite, or proven artifact-contract contradiction.
