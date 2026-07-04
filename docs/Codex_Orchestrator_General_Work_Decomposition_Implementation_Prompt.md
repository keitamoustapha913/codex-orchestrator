# Codex Orchestrator — General Work Decomposition, Multi-Patchlet Planning, and Transaction Graph Implementation Prompt

This is the expanded implementation handoff for the corrected work-decomposition architecture.

It includes all approved reflections, corrections, additions, and implementation requirements.

It must not be compacted.

It must not be reduced to “one file equals one patchlet.”

It must preserve the correct rule:

```text
one patchlet -> exactly one allowed product/runtime file
```

and the equally important corollary:

```text
two or more patchlets may work the same product/runtime file
```

---

# Step 0 — Read this entire prompt before editing anything

You are the Builder Layer for the local `codex-orchestrator` repository.

You are implementing the architecture in:

```text
Codex_Orchestrator_General_Work_Decomposition_Architecture.md
Codex_Orchestrator_General_Work_Decomposition_Implementation_Prompt.md
```

The current release-candidate safety baseline includes:

```text
v0.1.0-rc4 semantic goal satisfaction
workflow identity / rerun reset
report ingestion hardening
canonical probe artifact references
operator live progress
invocation-scoped live progress
master prompt source-of-truth proof layer
general goal proof contract
goal progress visibility
stop and partial apply
```

Do not weaken any of these.

The new problem is not proof validation.

The new problem is work decomposition.

The latest evidence shows the current pipeline still has a deterministic bottleneck:

```text
classify_evidence -> many evidence rows
build_inventory -> many graph nodes
extract_invariants -> one invariant I001
compile_patchlets -> one patchlet P0001
```

Therefore a complex target with many runtime files still produces one patchlet.

The operator has corrected the architecture:

```text
The architecture is not one runtime file -> one patchlet.
The architecture is one patchlet -> exactly one allowed product/runtime file.
Multiple patchlets may target the same file.
Patchlets must be small work units.
Patchlets must avoid memory compacting by keeping prompts narrow.
Patchlet prompts must fit the default CODEX_PATCHLET_TIMEOUT_SECONDS=600 budget.
```

The implementation must introduce a general decomposition layer.

Do not fake multiple patchlets by editing generated artifacts.

Do not simply create one invariant per file.

Do not use file count as the only decomposition strategy.

Decompose by:

```text
proof obligations
impact analysis
repo graph nodes
dependency boundaries
risk
task size
time budget
same-file sequencing
patchlet proof contribution
```

---

# Step 1 — Baseline before implementation

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
general_work_decomposition_implementation_note.md
```

Start it with:

```text
# General Work Decomposition Implementation Note

## Baseline

- investigation_start_utc:
- cwd:
- git root:
- branch:
- HEAD:
- git status before implementation:
- Python:
- uv:
- codex CLI:
- full deterministic suite:
- default smoke skip:
- cxor version:
- codex-orchestrator version:

## Existing safety baseline

- rc4 semantic goal gate present:
- general goal proof contract present:
- master prompt frozen source-of-truth present:
- report ingestion hardening present:
- workflow identity and rerun reset present:
- invocation-scoped live progress present:
- stop and partial apply present:
- target hygiene present:
- integration validation present:

## Approved corrections

- not one file -> one patchlet:
- one patchlet -> exactly one allowed product/runtime file:
- multiple patchlets may target same file:
- patchlets are small bounded work units:
- patchlets must fit CODEX_PATCHLET_TIMEOUT_SECONDS default 600:
- prompts must be narrow enough to avoid memory compacting:
- decomposition must be obligation/dependency/risk/task-size based:

## Implementation phase order

1. Evidence-preserving decomposition audit.
2. Decomposition schemas and artifacts.
3. Impact analysis.
4. Work slices.
5. Dependency graph.
6. Patchlet plan.
7. Transaction group plan.
8. Decomposition gates.
9. Compile patchlets from patchlet plan.
10. Worker prompt scope and budget contract.
11. Runtime one-file diff enforcement alignment.
12. Decomposition progress and operator visibility.
13. Stop/partial apply multi-patchlet behavior.
14. Regression of general proof and rc4 semantic gates.
15. Documentation.
16. Final verification.

## Risks

- over-decomposition:
- under-decomposition:
- same-file patchlet conflict:
- broad prompts:
- proof obligation drift:
- partial apply safety:
- regression risk:
```

Stop if the baseline suite is red.

---

# Step 2 — Evidence-preserving decomposition audit

Before editing, inspect the current bottleneck.

Do not fix during this phase.

Run:

```bash
rg -n "classify_evidence|build_inventory|extract_invariants|compile_patchlets|invariant|patchlet_index|transaction_groups|allowed_product_runtime|allowed_product_runtime_file|allowed_product_runtime_files|proof_obligations|probe_plan|goal_progress" src tests docs README.md IMPLEMENTATION_STATUS.md || true
```

Read:

```bash
sed -n '1,3600p' src/codex_orchestrator/stages/classify_evidence.py
sed -n '1,3600p' src/codex_orchestrator/stages/build_inventory.py
sed -n '1,3600p' src/codex_orchestrator/stages/extract_invariants.py
sed -n '1,3600p' src/codex_orchestrator/stages/compile_patchlets.py
sed -n '1,3600p' src/codex_orchestrator/stages/run_patchlet.py
sed -n '1,3600p' src/codex_orchestrator/stages/verify_group.py
sed -n '1,3600p' src/codex_orchestrator/stages/verify_global.py
sed -n '1,3600p' src/codex_orchestrator/goal_progress.py
sed -n '1,3600p' src/codex_orchestrator/proof_obligations.py
sed -n '1,3600p' src/codex_orchestrator/probe_plan.py
```

Inspect tests:

```bash
find tests -maxdepth 3 -type f | sort | sed -n '1,500p'

sed -n '1,2600p' tests/integration/test_general_goal_proof_contract.py 2>/dev/null || true
sed -n '1,2600p' tests/integration/test_master_prompt_satisfaction_verifier.py 2>/dev/null || true
sed -n '1,2600p' tests/integration/test_goal_progress_visibility.py 2>/dev/null || true
sed -n '1,2600p' tests/integration/test_stop_and_partial_apply.py 2>/dev/null || true
sed -n '1,2600p' tests/integration/test_target_hygiene_gate.py 2>/dev/null || true
```

Record in the implementation note:

```text
where I001 is created
why only I001 is created
how compile_patchlets currently maps invariants to patchlets
where allowed files are enforced
whether plural allowed_product_runtime_files exists
where transaction groups are generated
which tests assume one invariant/one patchlet
which artifacts should remain backward-compatible
```

---

# Phase 1 — Decomposition schemas and artifact roots

## Goal

Create durable decomposition schemas and the artifact root.

## Files to add

```text
src/codex_orchestrator/schemas/impact_analysis.schema.json
src/codex_orchestrator/schemas/work_decomposition_plan.schema.json
src/codex_orchestrator/schemas/work_slices.schema.json
src/codex_orchestrator/schemas/decomposition_dependency_graph.schema.json
src/codex_orchestrator/schemas/patchlet_plan.schema.json
src/codex_orchestrator/schemas/transaction_group_plan.schema.json
src/codex_orchestrator/schemas/decomposition_progress.schema.json
```

Add module:

```text
src/codex_orchestrator/work_decomposition.py
```

Suggested functions:

```python
ensure_decomposition_root(ctx_or_repo_root) -> Path
write_decomposition_artifact(root: Path, name: str, payload: dict) -> Path
load_decomposition_artifact(root: Path, name: str) -> dict
validate_decomposition_artifact(payload: dict, schema_name: str) -> None
```

## Tests

Create:

```text
tests/unit/test_work_decomposition_schemas.py
```

Tests:

```text
test_impact_analysis_schema_accepts_minimal_valid_payload
test_work_decomposition_plan_schema_accepts_rules
test_work_slices_schema_accepts_multiple_slices_same_file
test_dependency_graph_schema_accepts_acyclic_graph
test_patchlet_plan_schema_accepts_one_file_patchlet
test_patchlet_plan_schema_rejects_missing_allowed_file_for_product_patchlet
test_transaction_group_plan_schema_accepts_dependency_groups
test_decomposition_progress_schema_accepts_counts
```

Run:

```bash
uv run --no-sync pytest -q tests/unit/test_work_decomposition_schemas.py
```

---

# Phase 2 — Impact analysis

## Goal

Build `.codex-orchestrator/decomposition/impact_analysis.json` from inventory graph, proof obligations, goal interpretation, and repo file graph.

## Requirements

Impact analysis must:

```text
read inventory graph
read proof obligations
read goal interpretation
mark relevant runtime files
record impact reasons
not create patchlets
not mutate product files
handle unknown/ambiguous nodes explicitly
```

## Suggested functions

```python
build_impact_analysis(
    *,
    workflow_root: Path,
    inventory_graph: dict,
    proof_obligations: dict,
    goal_interpretation: dict,
) -> dict
```

## Tests

Create:

```text
tests/integration/test_work_decomposition_impact_analysis.py
```

Tests:

```text
test_impact_analysis_written
test_impact_analysis_references_inventory_graph
test_impact_analysis_references_proof_obligations
test_impact_analysis_marks_entrypoint_file
test_impact_analysis_marks_dependency_files
test_impact_analysis_records_reasons
test_impact_analysis_preserves_unknown_nodes
test_impact_analysis_does_not_create_patchlets
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_work_decomposition_impact_analysis.py
```

---

# Phase 3 — Work slice generation

## Goal

Generate small bounded work slices.

This is the central implementation phase.

## Rules

Every work slice must include:

```text
work_slice_id
slice_kind
title
description
allowed_product_runtime_file if product-editing
target_node_ids
proof_obligation_ids or enables_slice_ids
dependency_slice_ids
estimated_time_budget_seconds
requires_worker_memory_compaction=false
prompt_scope_summary
acceptance_contribution
status
```

Do not create broad all-repo slices unless the goal is truly artifact-only and explicitly classified.

Do not produce one giant slice for all runtime files when multiple impacted nodes exist.

Do not use file count alone.

Use heuristics:

```text
entrypoint slice
core dependency slice
validation/proof slice
adapter slice
formatting/output slice
final integration slice
same-file follow-up slice when one file has multiple independent edits
```

## Multi-patchlet requirement for complex target

For deterministic tests, create a target repo where:

```text
app.py imports pipeline.py
pipeline.py imports validator.py and formatter.py
formatter.py imports config.py
proof obligation requires final app.main() behavior
```

The decomposition should produce at least five work slices and patchlets for a broad enough master prompt/test fixture.

The decomposition must not require real Codex.

## Tests

Create:

```text
tests/integration/test_small_work_slice_decomposition.py
```

Tests:

```text
test_complex_repo_generates_multiple_work_slices
test_complex_repo_generates_at_least_five_slices_for_broad_goal
test_multiple_slices_may_target_same_file
test_each_slice_has_exactly_one_allowed_file_when_product_editing
test_slice_has_time_budget_600_default
test_slice_has_prompt_scope_summary
test_slice_does_not_require_memory_compacting
test_slice_references_proof_obligation_or_enabling_slice
test_slice_generation_not_equal_one_file_one_slice_only
test_work_slices_schema_validates
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_small_work_slice_decomposition.py
```

---

# Phase 4 — Dependency graph

## Goal

Generate dependency graph over work slices.

## Rules

```text
same-file slices must be ordered unless explicitly independent
slices with imported dependency relationships must be ordered when needed
proof/enabling slices must precede final integration slices
cycles are forbidden
missing dependency IDs are forbidden
```

## Tests

Create:

```text
tests/integration/test_work_slice_dependency_graph.py
```

Tests:

```text
test_dependency_graph_written
test_dependency_graph_has_topological_order
test_same_file_slices_ordered
test_dependency_edges_have_reasons
test_cycle_rejected
test_missing_slice_dependency_rejected
test_dependency_graph_schema_validates
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_work_slice_dependency_graph.py
```

---

# Phase 5 — Patchlet plan from work slices

## Goal

Generate patchlet specs from work slices.

This replaces the invariant-only patchlet generation bottleneck.

## Required mapping

```text
WS001 -> P0001
WS002 -> P0002
WS003 -> P0003
...
```

Every product-editing patchlet must have exactly one allowed file.

Multiple patchlets may target the same file.

## Backward compatibility

If existing code expects `.codex-orchestrator/patchlets/patchlet_index.json`, keep writing it.

But it must now be generated from `patchlet_plan.json` or contain equivalent fields:

```text
work_slice_id
allowed_product_runtime_file
proof_obligation_ids
dependency_patchlet_ids
time_budget_seconds
soft_deadline_seconds
prompt_scope
```

## Tests

Create:

```text
tests/integration/test_patchlet_plan_from_work_slices.py
```

Tests:

```text
test_patchlet_plan_written
test_patchlet_plan_has_one_patchlet_per_work_slice
test_patchlet_ids_are_stable_and_ordered
test_each_patchlet_has_exactly_one_allowed_file
test_multiple_patchlets_can_target_same_file
test_patchlet_plan_records_dependencies
test_patchlet_plan_records_time_budget
test_patchlet_plan_records_prompt_scope
test_patchlet_index_generated_from_patchlet_plan
test_patchlet_plan_schema_validates
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_patchlet_plan_from_work_slices.py
```

---

# Phase 6 — Transaction group plan

## Goal

Generate transaction groups from dependency graph and proof obligations.

## Rules

```text
same-file patchlets are ordered
transaction groups respect topological order
parallel or grouped patchlets must not violate dependencies
each group records proof obligations expected from member patchlets
```

## Tests

Create:

```text
tests/integration/test_transaction_graph_decomposition.py
```

Tests:

```text
test_transaction_group_plan_written
test_transaction_group_plan_uses_patchlet_plan
test_same_file_patchlets_not_parallel_without_order
test_dependency_cycle_rejected_before_group_plan
test_transaction_group_dependencies_recorded
test_existing_transaction_groups_json_generated_from_plan
test_group_verifier_reads_group_plan_fields
test_transaction_group_plan_schema_validates
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_transaction_graph_decomposition.py
```

---

# Phase 7 — Decomposition gates

## Goal

Add gates that enforce decomposition safety before any worker executes.

## Required gate artifacts

```text
.codex-orchestrator/decomposition/gates/work_decomposition_gate_result.json
.codex-orchestrator/decomposition/gates/one_file_patchlet_gate_result.json
.codex-orchestrator/decomposition/gates/patchlet_prompt_budget_gate_result.json
.codex-orchestrator/decomposition/gates/dependency_graph_gate_result.json
.codex-orchestrator/decomposition/gates/proof_contribution_gate_result.json
```

## Tests

Create:

```text
tests/integration/test_work_decomposition_gates.py
```

Tests:

```text
test_work_decomposition_gate_passes_valid_plan
test_work_decomposition_gate_rejects_empty_plan_for_provable_product_goal
test_one_file_patchlet_gate_rejects_multiple_allowed_files
test_one_file_patchlet_gate_allows_same_file_across_multiple_patchlets
test_prompt_budget_gate_requires_600_default
test_prompt_budget_gate_rejects_memory_compacting_required
test_dependency_graph_gate_rejects_cycle
test_proof_contribution_gate_rejects_unrelated_patchlet
test_all_gate_results_schema_validate
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_work_decomposition_gates.py
```

---

# Phase 8 — Compile patchlets from patchlet plan

## Goal

Change `compile_patchlets` so patchlets are generated from the new patchlet plan, not solely from invariants.

## Requirements

```text
read patchlet_plan.json
write patchlet_index.json
write subprompts per patchlet
preserve one allowed file per patchlet
include work_slice_id
include dependency info
include proof obligation IDs
include time budget and prompt scope
preserve previous artifact paths where needed
```

## Tests

Create:

```text
tests/integration/test_compile_patchlets_from_decomposition.py
```

Tests:

```text
test_compile_patchlets_uses_patchlet_plan
test_compile_patchlets_no_longer_limited_to_one_invariant
test_complex_repo_compiles_at_least_five_patchlets
test_patchlet_subprompt_includes_work_slice_id
test_patchlet_subprompt_includes_one_allowed_file
test_patchlet_subprompt_includes_time_budget
test_patchlet_subprompt_includes_dependency_patchlets
test_patchlet_subprompt_includes_proof_obligations
test_patchlet_index_preserves_backward_compatibility_fields
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_compile_patchlets_from_decomposition.py
```

---

# Phase 9 — Worker prompt scope and budget contract

## Goal

Ensure worker prompts are narrow and budget-aware.

## Required prompt section

Every worker prompt must include:

```text
# Patchlet Decomposition Contract

- patchlet id:
- work slice id:
- allowed product/runtime file:
- hard time budget:
- soft deadline:
- dependency patchlets already accepted:
- dependency patchlets not yet accepted:
- proof obligations this patchlet contributes to:
- local acceptance contribution:
- do not edit other product/runtime files:
- do not attempt future work slices:
- do not broaden scope:
- do not compact memory by taking on unrelated work:
```

## Tests

Create:

```text
tests/integration/test_patchlet_prompt_decomposition_contract.py
```

Tests:

```text
test_worker_prompt_includes_patchlet_decomposition_contract
test_worker_prompt_includes_single_allowed_file
test_worker_prompt_includes_hard_time_budget_600
test_worker_prompt_includes_soft_deadline
test_worker_prompt_forbids_future_slices
test_worker_prompt_forbids_other_runtime_files
test_worker_prompt_mentions_same_file_may_have_other_patchlets
test_worker_prompt_includes_dependency_patchlets
test_worker_prompt_includes_proof_obligation_ids
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_patchlet_prompt_decomposition_contract.py
```

---

# Phase 10 — Runtime one-file diff enforcement alignment

## Goal

Ensure run-time diff validation enforces the decomposition rule.

## Requirements

The current run patchlet gate must:

```text
read allowed_product_runtime_file from patchlet plan or patchlet index
allow exactly that one file to be modified
reject edits to any other product/runtime file
allow artifact writes under approved artifact directories
preserve report/probe artifact behavior
```

## Tests

Create:

```text
tests/integration/test_one_file_runtime_diff_enforcement.py
```

Tests:

```text
test_patchlet_diff_allows_its_one_allowed_file
test_patchlet_diff_rejects_second_runtime_file
test_patchlet_diff_rejects_file_from_future_patchlet
test_patchlet_diff_allows_artifact_writes
test_same_file_future_patchlet_does_not_allow_current_patchlet_to_do_future_slice
test_failure_signature_for_multiple_runtime_files_is_precise
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_one_file_runtime_diff_enforcement.py
```

---

# Phase 11 — Decomposition progress and operator visibility

## Goal

Expose decomposition progress to the operator.

## New artifacts

```text
.codex-orchestrator/decomposition/decomposition_progress.json
.codex-orchestrator/decomposition/decomposition_progress.jsonl
```

## New CLI

```bash
cxor decomposition --repo <repo>
cxor decomposition --repo <repo> --json
cxor decomposition --repo <repo> --watch
```

## Status integration

`cxor status --json` must include:

```json
{
  "decomposition": {
    "planned_work_slices": 5,
    "planned_patchlets": 5,
    "accepted_patchlets": 2,
    "pending_patchlets": 3,
    "failed_patchlets": 0,
    "files_with_multiple_patchlets": ["app.py", "pipeline.py"]
  }
}
```

## Tests

Create:

```text
tests/integration/test_decomposition_operator_visibility.py
```

Tests:

```text
test_decomposition_progress_written
test_decomposition_progress_jsonl_append_only
test_status_json_includes_decomposition_summary
test_decomposition_cli_human_output
test_decomposition_cli_json_output
test_decomposition_cli_watch_output
test_monitor_shows_decomposition_events
test_live_progress_prints_decomposition_summary
test_live_progress_prints_patchlet_acceptance_progress
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_decomposition_operator_visibility.py
```

---

# Phase 12 — Stop and partial apply with multiple patchlets

## Goal

Verify stop/apply behavior with accepted subset of multi-patchlet workflow.

## Tests

Create:

```text
tests/integration/test_stop_partial_apply_multi_patchlet.py
```

Tests:

```text
test_stop_after_three_of_five_patchlets_records_accepted_progress
test_stop_result_lists_accepted_pending_and_failed_patchlets
test_partial_apply_requires_allow_partial_for_stopped_workflow
test_partial_apply_applies_only_latest_accepted_integration_ref
test_partial_apply_does_not_apply_pending_patchlet
test_partial_apply_does_not_apply_in_progress_attempt
test_goal_progress_after_partial_apply_shows_remaining_obligations
test_decomposition_progress_after_partial_apply_shows_pending_patchlets
```

Run:

```bash
uv run --no-sync pytest -q tests/integration/test_stop_partial_apply_multi_patchlet.py
```

---

# Phase 13 — Regression tests

Run core regression suites:

```bash
uv run --no-sync pytest -q tests/integration/test_general_goal_proof_contract.py
uv run --no-sync pytest -q tests/integration/test_general_probe_plan.py
uv run --no-sync pytest -q tests/integration/test_independent_probe_rerun_gate.py
uv run --no-sync pytest -q tests/integration/test_goal_coverage_gate.py
uv run --no-sync pytest -q tests/integration/test_master_prompt_satisfaction_verifier.py
uv run --no-sync pytest -q tests/integration/test_semantic_goal_false_done_chain.py
uv run --no-sync pytest -q tests/integration/test_goal_satisfaction_gate.py
uv run --no-sync pytest -q tests/integration/test_auto_rerun_cli_semantics.py
uv run --no-sync pytest -q tests/integration/test_stop_and_partial_apply.py
uv run --no-sync pytest -q tests/integration/test_report_ingestion_gate.py
uv run --no-sync pytest -q tests/integration/test_target_hygiene_gate.py
```

---

# Phase 14 — Documentation

Update:

```text
README.md
docs/cli.md
docs/autonomous_loop.md
docs/general_goal_proof_contract.md
docs/goal_progress_and_partial_apply.md
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
docs/general_work_decomposition.md
```

Docs must explain:

```text
why one-invariant/one-patchlet was insufficient
why one file -> one patchlet is not the design
why one patchlet -> one allowed product/runtime file is the design
why multiple patchlets may target the same file
why small patchlets avoid memory compacting
how CODEX_PATCHLET_TIMEOUT_SECONDS=600 shapes patchlet scope
work_decomposition_plan.json
work_slices.json
dependency_graph.json
patchlet_plan.json
transaction_group_plan.json
decomposition gates
decomposition CLI
stop/partial apply with multiple accepted patchlets
manual smoke expectations
```

Add tests:

```text
tests/unit/test_docs_general_work_decomposition.py
```

Tests:

```text
test_docs_explain_one_patchlet_one_allowed_file
test_docs_explain_multiple_patchlets_may_target_same_file
test_docs_explain_not_one_file_one_patchlet
test_docs_explain_small_work_slices
test_docs_explain_600_second_budget
test_docs_explain_avoid_memory_compacting
test_docs_explain_decomposition_artifacts
test_docs_explain_decomposition_gates
test_docs_explain_stop_partial_apply_multi_patchlet
test_usage_guide_mentions_general_work_decomposition
```

Run:

```bash
uv run --no-sync pytest -q tests/unit/test_docs_general_work_decomposition.py
```

---

# Phase 15 — Full verification

Run all focused tests:

```bash
export UV_CACHE_DIR=/tmp/uv-cache

uv run --no-sync pytest -q tests/unit/test_work_decomposition_schemas.py
uv run --no-sync pytest -q tests/integration/test_work_decomposition_impact_analysis.py
uv run --no-sync pytest -q tests/integration/test_small_work_slice_decomposition.py
uv run --no-sync pytest -q tests/integration/test_work_slice_dependency_graph.py
uv run --no-sync pytest -q tests/integration/test_patchlet_plan_from_work_slices.py
uv run --no-sync pytest -q tests/integration/test_transaction_graph_decomposition.py
uv run --no-sync pytest -q tests/integration/test_work_decomposition_gates.py
uv run --no-sync pytest -q tests/integration/test_compile_patchlets_from_decomposition.py
uv run --no-sync pytest -q tests/integration/test_patchlet_prompt_decomposition_contract.py
uv run --no-sync pytest -q tests/integration/test_one_file_runtime_diff_enforcement.py
uv run --no-sync pytest -q tests/integration/test_decomposition_operator_visibility.py
uv run --no-sync pytest -q tests/integration/test_stop_partial_apply_multi_patchlet.py
uv run --no-sync pytest -q tests/unit/test_docs_general_work_decomposition.py
```

Then run full suite:

```bash
uv run --no-sync pytest -q
uv run --no-sync python -m codex_orchestrator --version
uv run --no-sync cxor --version
uv run --no-sync codex-orchestrator --version
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py
git status --short
```

Do not run explicit real Codex during implementation.

---

# Optional manual real-Codex smoke after deterministic green

Do not run during implementation.

After deterministic green, recommend this smoke:

```bash
rm -rf /tmp/cxor-target-multi-patchlet-real-smoke
mkdir -p /tmp/cxor-target-multi-patchlet-real-smoke
cd /tmp/cxor-target-multi-patchlet-real-smoke

git init
cat > app.py <<'PY'
from pipeline import run_pipeline

def main():
    return run_pipeline("raw")
PY
cat > pipeline.py <<'PY'
def run_pipeline(value):
    return value
PY
cat > validator.py <<'PY'
def validate(value):
    return bool(value)
PY
cat > formatter.py <<'PY'
def format_value(value):
    return value
PY
cat > config.py <<'PY'
EXPECTED = "me"
PY
cat > master_prompt.md <<'MD'
Make this app return me through a validated pipeline. Preserve a small-entrypoint design, use the validator and formatter modules, and prove the final behavior.
MD

git add .
git commit -m "Initial multi patchlet target"

cd /home/theyeq-admin-lap/master-workspace-research/codex-orchestrator

CODEX_PATCHLET_TIMEOUT_SECONDS=600 \
uv run --no-sync cxor auto \
  --repo /tmp/cxor-target-multi-patchlet-real-smoke \
  --master /tmp/cxor-target-multi-patchlet-real-smoke/master_prompt.md \
  --until DONE \
  --worker-mode real_codex \
  --use-worktree \
  --live-progress
```

Expected:

```text
multiple planned work slices
multiple patchlets
at least five patchlets for the fixture if decomposition heuristics decide the fixture requires that breadth
one allowed product/runtime file per patchlet
same file may appear in multiple patchlets
no stale event replay
independent proof obligations verified
master prompt satisfaction or precise failure
```

---

# Required final report format

Return exactly this structure.

Do not compress details.

```text
# Codex TDD Report — General Work Decomposition and Multi-Patchlet Planning

## 1. Baseline

- Python:
- uv:
- codex version:
- initial full test result:
- default smoke result:
- git status at start:
- current branch:
- HEAD:

## 2. Evidence and approved corrections

- evidence source:
- current bottleneck:
- corrected architecture rule:
- not one file to one patchlet:
- one patchlet to exactly one allowed product/runtime file:
- multiple patchlets may target same file:
- small work unit requirement:
- 600 second default budget:
- avoid memory compacting:

## 3. Architecture decisions implemented

- impact analysis:
- work decomposition plan:
- work slices:
- dependency graph:
- patchlet plan:
- transaction group plan:
- decomposition gates:
- compile patchlets from patchlet plan:
- prompt budget contract:
- one-file runtime enforcement:
- decomposition progress:
- stop/partial apply multi-patchlet behavior:
- docs:

## 4. Phase results

### Phase 1 — Decomposition schemas and artifact roots
- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior:
- rollback:

### Phase 2 — Impact analysis
- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior:
- rollback:

### Phase 3 — Work slice generation
- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior:
- multiple patchlets same file:
- rollback:

### Phase 4 — Dependency graph
- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior:
- rollback:

### Phase 5 — Patchlet plan from work slices
- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior:
- rollback:

### Phase 6 — Transaction group plan
- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior:
- rollback:

### Phase 7 — Decomposition gates
- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior:
- rollback:

### Phase 8 — Compile patchlets from patchlet plan
- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior:
- rollback:

### Phase 9 — Worker prompt scope and budget contract
- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior:
- rollback:

### Phase 10 — Runtime one-file diff enforcement alignment
- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior:
- rollback:

### Phase 11 — Decomposition progress and operator visibility
- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior:
- rollback:

### Phase 12 — Stop and partial apply with multiple patchlets
- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior:
- rollback:

### Phase 13 — Regression tests
- commands:
- outputs:

### Phase 14 — Documentation
- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- docs updated:
- rollback:

### Phase 15 — Final verification
- commands:
- outputs:

## 5. Decomposition artifacts

Describe:

- impact_analysis.json:
- work_decomposition_plan.json:
- work_slices.json:
- dependency_graph.json:
- patchlet_plan.json:
- transaction_group_plan.json:
- decomposition_progress.json:
- decomposition_progress.jsonl:

## 6. One-file patchlet contract

Describe:

- exactly one allowed product/runtime file:
- same file across multiple patchlets:
- artifact-only patchlets:
- runtime diff enforcement:
- failure signatures:

## 7. Small work and budget behavior

Describe:

- 600 second hard budget:
- soft deadline:
- prompt scope:
- memory compaction avoidance:
- broad prompt rejection:

## 8. Dependency and transaction behavior

Describe:

- dependency graph:
- same-file ordering:
- transaction groups:
- cycles:
- group verification:

## 9. Operator visibility

Describe:

- status:
- monitor:
- live progress:
- decomposition CLI:
- decomposition progress:

## 10. Stop and partial apply

Describe:

- accepted patchlets:
- pending patchlets:
- stop result:
- partial apply:
- in-progress work policy:

## 11. Regression preservation

Describe:

- general goal proof:
- rc4 semantic false DONE:
- report ingestion:
- workflow identity/rerun reset:
- invocation progress:
- target hygiene:

## 12. Docs

List changed docs and tests.

## 13. Default smoke skip

Paste output.

## 14. Final verification output

Paste exact outputs.

## 15. Git status

Paste exact git status --short.

## 16. Remaining confirmed gaps

List only confirmed gaps.

## 17. Next single highest-value increment

If deterministic multi-patchlet decomposition is complete, say:

Run a manual real-Codex smoke on a fresh multi-file target and confirm the orchestrator naturally plans multiple small patchlets, each patchlet has exactly one allowed product/runtime file, at least one file may appear in multiple patchlets, and accepted progress can be stopped/applied without applying unaccepted work.
```

---

# Final instruction

Implement general work decomposition.

Do not implement one file -> one patchlet.

Implement one patchlet -> exactly one allowed product/runtime file.

Allow multiple patchlets for the same file.

Keep patchlets small.

Keep prompts narrow.

Keep the default 600-second patchlet budget visible and enforced.

Avoid memory compacting by decomposition.

Do not fake patchlets by editing generated artifacts.

Do not run explicit real Codex during implementation.

Do not mutate preserved smoke targets.

Do not weaken proof gates.

Do not weaken report ingestion.

Do not weaken target hygiene.

Do not weaken stop/partial apply.

Use fresh temp repos and behavior-facing tests.
