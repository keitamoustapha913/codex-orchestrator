Step 0 — Read this entire prompt before editing anything.

You are the Builder Layer for the local `codex-orchestrator` repository.

You are now implementing the architecture in:

```text
Codex_Orchestrator_Real_Codex_Report_Contract_Architecture.md
```

This implementation is based on the evidence-only report:

```text
real_codex_probe_artifact_reference_loop_evidence_report.md
```

The evidence proved that real Codex repeatedly wrote `probe_artifact_refs` as string file paths, while the canonical report schema requires each entry to be an object with `patchlet_id`, `probe_root`, and `run_id`.

The evidence also proved that:

```text
P0001, P0002, and P0003 workers exited code 0.
P0001, P0002, and P0003 reports failed schema validation.
The repeated invalid field was probe_artifact_refs.
The invalid values were strings.
The schema requires object entries.
The generated report contract did not show an explicit object-shaped probe_artifact_refs item example.
Repair prompts carried human error text but did not add schema-specific corrective examples.
Operator events preserved human-readable validation text but not JSON pointer, schema path, or normalized failure signature.
The loop governor classified the repeated failure as unknown_repeated_failure instead of probe_artifact_refs_not_objects.
The target product file stayed clean.
```

Your task is to implement the report-contract hardening architecture.

Do not run explicit real Codex.

Do not mutate the preserved smoke target:

```text
/tmp/cxor-target-visibility-smoke-20260703T192354Z
```

Do not delete evidence files.

Do not weaken product/runtime gates.

Do not weaken wrapper gates.

Do not weaken target hygiene.

Do not weaken checkpoint cleanliness.

Do not remove strict canonical report validation.

Do not accept arbitrary malformed reports.

Do not allow path refs outside `.artifacts/probes/`.

Do not let this turn into blind retry.

The implementation must be TDD-first, behavior-facing, and deterministic.

Default tests must not invoke real Codex.

---

# Step 1 — Baseline before editing

Run these commands before editing any implementation file:

```bash
export UV_CACHE_DIR=/tmp/uv-cache

pwd
git status --short
git rev-parse --show-toplevel
git rev-parse --verify HEAD || true
git branch --show-current

uv run --no-sync python --version
uv --version
codex --version || true

uv run --no-sync pytest -q
uv run --no-sync python -m codex_orchestrator --version
uv run --no-sync cxor --version
uv run --no-sync codex-orchestrator --version
```

Create an implementation note:

```text
real_codex_report_contract_hardening_implementation_note.md
```

Start it with:

```text
# Real-Codex Report Contract Hardening Implementation Note

## Baseline

- cwd:
- git root:
- branch:
- HEAD:
- git status before implementation:
- Python:
- uv:
- codex CLI:
- initial full suite:
- cxor version:
- codex-orchestrator version:

## Evidence basis

- evidence report:
- proven repeated field:
- expected schema shape:
- actual real-Codex shape:
- completed failed attempts:
- loop governor actual signature:
- expected signature:
- prompt contract gap:
- repair prompt gap:
- target product cleanliness:

## Phase order

1. Probe artifact reference canonical model and normalizer.
2. Structured report validation errors.
3. Report ingestion gate and raw/canonical report preservation.
4. Patchlet report schema update for canonical refs with optional files metadata.
5. Prompt contract hardening.
6. Failure records and operator events with structured signatures.
7. Loop governor signature normalization from structured evidence.
8. Report-shape repair routing and report-only repair guard.
9. Full-chain fake real-Codex reproduction.
10. Docs.
11. Final verification.

## Risk log

- risk:
- mitigation:
- rollback:
```

Stop immediately if the baseline full suite is red.

---

# Step 2 — Protect existing evidence and live artifacts

Before implementation, run:

```bash
pgrep -af "cxor auto|codex exec|cxor-target-visibility-smoke|cxor-p" || true
```

Record whether any old manual process appears to be running.

Do not kill anything.

Do not inspect or mutate the preserved smoke target unless only reading existing evidence is needed.

All tests must use fresh temporary target repositories.

---

# Step 3 — Hard safety constraints

The following constraints are mandatory:

```text
1. Canonical patchlet reports still require object-shaped probe_artifact_refs.
2. Raw string probe refs may be accepted only at report-ingress time and only when safely canonicalized.
3. Canonical stored reports must use object-shaped probe refs.
4. Raw worker reports must be preserved for audit.
5. Canonical normalized reports must be written separately or clearly recorded.
6. Normalization must be recorded in report_ingestion_result.json.
7. Unsafe string refs must fail with structured validation errors.
8. Paths outside .artifacts/probes/ must be rejected.
9. Missing referenced probe files must be rejected.
10. Product/runtime files must not be changed by report-only repair.
11. Report-only repair must not rewrite probe evidence.
12. Report-shape failures must not trigger unbounded full patchlet regeneration.
13. Loop governor must not classify this live failure class as unknown_repeated_failure.
14. Operator events must include normalized failure signatures when available.
15. Failure records must preserve structured report validation errors.
16. Prompt contract must include valid object-shaped examples and invalid string examples.
17. Default tests must not run real Codex.
18. Existing runbook/list/export/validate behavior must continue to pass.
19. Existing direct auto visibility behavior must continue to pass.
20. Existing checkpoint cleanliness behavior must continue to pass.
```

---

# Step 4 — Testing rules

Do not write tests that search runtime source text under:

```text
src/codex_orchestrator/
```

Do not write tests such as:

```python
assert "probe_artifact_refs" in Path("src/codex_orchestrator/validators/report_validator.py").read_text()
```

Use behavior-facing tests.

Allowed test surfaces:

```text
generated raw worker reports
generated canonical reports
generated report_ingestion_result.json
generated report_validation_error objects
generated wrapper gate result
generated failure records
generated repair plans
generated operator_events.jsonl
generated loop_governor.json
generated report-only repair artifacts
generated prompt files
generated prompt index entries
CLI output
schema validation output
docs
```

---

# Step 5 — Preflight inspection

Before editing, inspect current files:

```bash
rg -n "probe_artifact_refs|patchlet_report|report_validator|ReportValidationError|wrapper_gate|failure_signature|unknown_repeated_failure|loop_governor|REPORT_SCHEMA_CONTRACT|repair_plan|report_only|operator_event|prompt_index" \
  src tests README.md docs IMPLEMENTATION_STATUS.md || true
```

Read likely files:

```bash
sed -n '1,2600p' src/codex_orchestrator/schemas/patchlet_report.schema.json
sed -n '1,2600p' src/codex_orchestrator/validators/report_validator.py
sed -n '1,3200p' src/codex_orchestrator/stages/run_patchlet.py
sed -n '1,2600p' src/codex_orchestrator/stages/plan_repair.py
sed -n '1,2600p' src/codex_orchestrator/stages/regenerate_patchlets.py
sed -n '1,2600p' src/codex_orchestrator/loop_governor.py
sed -n '1,2600p' src/codex_orchestrator/operator_events.py
sed -n '1,2600p' src/codex_orchestrator/worker_capsule.py
sed -n '1,2600p' src/codex_orchestrator/prompt_templates/real_codex_patchlet_contract.md
```

Record findings in the implementation note.

---

# Phase 1 — Probe artifact reference canonical model and normalizer

## 1.1 Goal

Implement a deterministic normalizer that converts safe raw string probe references into canonical object references.

Canonical object shape:

```json
{
  "patchlet_id": "P0002",
  "probe_root": ".artifacts/probes/P0002",
  "run_id": "default",
  "files": [
    {
      "path": ".artifacts/probes/P0002/comparison.txt",
      "kind": "comparison",
      "sha256": "...",
      "size_bytes": 456
    }
  ]
}
```

The canonical object must include at least:

```text
patchlet_id
probe_root
run_id
```

`files` is optional at schema level but should be produced by the normalizer when raw string refs are present.

## 1.2 New module

Add:

```text
src/codex_orchestrator/probe_artifact_refs.py
```

Suggested public API:

```python
normalize_probe_artifact_refs(
    refs: list[Any],
    *,
    target_repo_root: Path,
    current_patchlet_id: str,
) -> ProbeArtifactRefNormalizationResult
```

The result should contain:

```text
accepted
canonical_refs
normalizations
validation_errors
normalized_failure_signature
repair_hint
```

## 1.3 Normalization rules

Accept canonical object refs unchanged if they validate.

Convert string refs only if:

```text
1. The string path is relative under .artifacts/probes/ or absolute path resolving inside the target repo's .artifacts/probes/.
2. The referenced file exists.
3. The patchlet id can be derived from the path or equals current_patchlet_id.
4. The probe_root can be derived.
5. run_id can be derived from a run_* path segment, or set to default for flat probe roots.
6. The final object has patchlet_id, probe_root, run_id.
```

Reject:

```text
paths outside .artifacts/probes/
missing files
absolute paths outside target root
strings that are not paths
objects missing required canonical fields
mixed ambiguous refs that cannot be grouped
```

## 1.4 File metadata

For each referenced file, record:

```text
path
kind
sha256
size_bytes
```

`kind` can derive from filename stem:

```text
before_state.json -> before_state
comparison.txt -> comparison
row_ledger.jsonl -> row_ledger
```

## 1.5 Unit tests

Create:

```text
tests/unit/test_probe_artifact_ref_normalizer.py
```

Add:

```python
test_normalizes_relative_probe_file_string_to_object_ref
test_normalizes_absolute_probe_file_string_to_object_ref
test_normalizes_nested_run_directory_with_run_id
test_normalizes_flat_probe_directory_with_default_run_id
test_groups_multiple_files_under_same_probe_root
test_preserves_existing_canonical_object_ref
test_rejects_path_outside_artifacts_probes
test_rejects_missing_probe_file
test_rejects_absolute_path_outside_target_repo
test_rejects_object_missing_patchlet_id
test_rejects_object_missing_probe_root
test_rejects_object_missing_run_id
test_normalization_records_file_sha256_and_size
test_normalization_result_uses_probe_artifact_refs_not_objects_signature_for_string_refs
```

Focused command:

```bash
uv run --no-sync pytest -q tests/unit/test_probe_artifact_ref_normalizer.py
```

## 1.6 Acceptance

Phase 1 is complete when safe string refs from the live evidence shape normalize to canonical objects, unsafe refs fail with structured errors, and focused tests pass.

---

# Phase 2 — Structured report validation errors

## 2.1 Goal

Preserve machine-readable validation errors instead of flattening jsonschema errors too early.

## 2.2 New schema

Add:

```text
src/codex_orchestrator/schemas/report_validation_error.schema.json
```

Shape:

```json
{
  "schema_version": "1.0",
  "kind": "report_validation_error",
  "error_id": "RVE000001",
  "field": "probe_artifact_refs",
  "json_pointer": "/probe_artifact_refs/0",
  "schema_path": "/properties/probe_artifact_refs/items/type",
  "validator": "type",
  "expected_type": "object",
  "actual_type": "string",
  "invalid_value_excerpt": ".artifacts/probes/P0002/comparison.txt",
  "message": "'.artifacts/probes/P0002/comparison.txt' is not of type 'object'",
  "normalized_signature": "probe_artifact_refs_not_objects",
  "repair_hint": "Use object entries with patchlet_id, probe_root, and run_id."
}
```

## 2.3 Validator behavior

Update report validation internals so schema errors can be returned as structured data.

Do not remove existing human-readable `ReportValidationError` behavior if callers depend on it.

Add an API such as:

```python
validate_patchlet_report_structured(...) -> PatchletReportValidationResult
```

or extend existing validation result objects.

The structured result must include:

```text
valid
errors
human_message
normalized_failure_signature
repair_hint
```

## 2.4 Unit tests

Create:

```text
tests/unit/test_structured_report_validation_errors.py
```

Add:

```python
test_structured_error_contains_json_pointer_for_probe_artifact_refs_item
test_structured_error_contains_schema_path
test_structured_error_contains_expected_and_actual_type
test_structured_error_contains_invalid_value_excerpt
test_structured_error_signature_probe_artifact_refs_not_objects
test_structured_error_repair_hint_mentions_object_shape
test_existing_human_error_message_still_available
test_valid_report_has_no_structured_errors
```

Focused command:

```bash
uv run --no-sync pytest -q tests/unit/test_structured_report_validation_errors.py
```

## 2.5 Acceptance

Phase 2 is complete when jsonschema errors are available as structured machine-readable objects and existing human message behavior remains compatible.

---

# Phase 3 — Report ingestion gate and raw/canonical preservation

## 3.1 Goal

Introduce a report-ingestion gate that preserves raw worker reports, normalizes safe probe refs, validates canonical reports, and writes durable evidence.

## 3.2 Artifact paths

Raw report:

```text
.codex-orchestrator/reports/raw/<attempt_id>.json
```

Canonical report:

```text
.codex-orchestrator/reports/<patchlet_id>.json
```

Ingestion result:

```text
.codex-orchestrator/runs/<attempt_id>/gates/report_ingestion_result.json
```

## 3.3 New schema

Add:

```text
src/codex_orchestrator/schemas/report_ingestion_result.schema.json
```

Required fields:

```text
schema_version
kind
patchlet_id
attempt_id
accepted
raw_report_path
canonical_report_path
normalization_applied
normalizations
validation_errors
normalized_failure_signature
repair_hint
```

## 3.4 Gate behavior

If raw report has object-shaped refs and validates:

```text
normalization_applied=false
accepted=true
canonical_report_path points to canonical report
validation_errors=[]
```

If raw report has safe string refs:

```text
normalization_applied=true
accepted=true
canonical report contains object refs
normalizations list records every conversion
```

If raw report has unsafe string refs:

```text
accepted=false
validation_errors include structured errors
normalized_failure_signature is specific
canonical_report_path=null or absent
```

## 3.5 Integration point

Integrate before wrapper gate report validation.

The wrapper gate should operate on canonical report output, not raw malformed worker input.

Preserve raw worker report regardless of acceptance.

## 3.6 Integration tests

Create:

```text
tests/integration/test_report_ingestion_probe_refs.py
```

Add:

```python
test_report_ingestion_preserves_raw_report
test_report_ingestion_writes_canonical_report
test_report_ingestion_writes_result_artifact
test_report_ingestion_accepts_existing_object_refs
test_report_ingestion_normalizes_string_probe_refs
test_report_ingestion_canonical_report_has_object_refs_after_normalization
test_report_ingestion_records_normalization_details
test_report_ingestion_rejects_outside_probe_path
test_report_ingestion_rejects_missing_probe_path
test_report_ingestion_result_schema_validates
test_wrapper_gate_uses_canonical_report_after_ingestion
test_operator_event_links_report_ingestion_result
```

Focused command:

```bash
uv run --no-sync pytest -q tests/integration/test_report_ingestion_probe_refs.py
```

## 3.7 Acceptance

Phase 3 is complete when the live evidence report shape can be normalized and sent to wrapper validation as canonical object-shaped report refs.

---

# Phase 4 — Patchlet report schema update for canonical refs with optional files metadata

## 4.1 Goal

Keep `probe_artifact_refs` object-shaped but optionally allow a `files` array inside each object to preserve exact file refs.

## 4.2 Schema update

Update:

```text
src/codex_orchestrator/schemas/patchlet_report.schema.json
```

Object item fields:

Required:

```text
patchlet_id
probe_root
run_id
```

Optional:

```text
files
```

Each file object:

```json
{
  "path": ".artifacts/probes/P0002/comparison.txt",
  "kind": "comparison",
  "sha256": "...",
  "size_bytes": 456
}
```

## 4.3 Tests

Extend or create tests:

```text
tests/integration/test_patchlet_report_probe_ref_schema.py
```

Add:

```python
test_patchlet_report_schema_accepts_object_probe_ref_without_files
test_patchlet_report_schema_accepts_object_probe_ref_with_files
test_patchlet_report_schema_rejects_string_probe_ref_in_canonical_report
test_patchlet_report_schema_rejects_file_object_missing_path
test_patchlet_report_schema_rejects_file_object_missing_sha256_when_present_policy_requires_it
test_patchlet_report_schema_rejects_probe_ref_missing_patchlet_id
test_patchlet_report_schema_rejects_probe_ref_missing_probe_root
test_patchlet_report_schema_rejects_probe_ref_missing_run_id
```

Focused command:

```bash
uv run --no-sync pytest -q tests/integration/test_patchlet_report_probe_ref_schema.py
```

## 4.4 Acceptance

Canonical report schema still rejects string refs but accepts enriched object refs.

---

# Phase 5 — Prompt contract hardening

## 5.1 Goal

Make the report contract unambiguous for real Codex.

## 5.2 Required generated contract content

`REPORT_SCHEMA_CONTRACT.md` must include:

```text
Every probe_artifact_refs entry must be an object.
Do not put raw strings in probe_artifact_refs.
Do not put individual file paths directly in probe_artifact_refs.
Use patchlet_id, probe_root, and run_id.
```

Valid example:

```json
{
  "probe_artifact_refs": [
    {
      "patchlet_id": "P0001",
      "probe_root": ".artifacts/probes/P0001/run_001",
      "run_id": "run_001"
    }
  ]
}
```

Invalid example:

```json
{
  "probe_artifact_refs": [
    ".artifacts/probes/P0001/run_001/before_state.json"
  ]
}
```

Explanation:

```text
Invalid: the array item is a string. It must be an object.
```

## 5.3 Repair prompt hardening

Repair prompts for report validation failures must include:

```text
exact JSON pointer when available
field name
expected type
actual type
invalid value excerpt
valid object-shaped example
repair hint
```

## 5.4 Tests

Create:

```text
tests/integration/test_report_contract_prompt_hardening.py
```

Add:

```python
test_report_contract_includes_probe_artifact_refs_object_rule
test_report_contract_includes_valid_object_shaped_probe_ref_example
test_report_contract_includes_invalid_string_probe_ref_example
test_report_contract_explicitly_forbids_string_probe_refs
test_repair_prompt_includes_json_pointer_for_report_validation_error
test_repair_prompt_includes_expected_and_actual_type
test_repair_prompt_includes_valid_probe_ref_object_example
test_repair_prompt_mentions_probe_artifact_refs_not_objects_signature
```

Focused command:

```bash
uv run --no-sync pytest -q tests/integration/test_report_contract_prompt_hardening.py
```

## 5.5 Acceptance

Generated worker and repair prompts make the object shape explicit and include both valid and invalid examples.

---

# Phase 6 — Failure records and operator events with structured signatures

## 6.1 Goal

Failure records and operator events must carry structured validation errors and normalized signatures.

## 6.2 Failure record additions

Add fields when report validation fails:

```json
{
  "failure_signature": "probe_artifact_refs_not_objects",
  "structured_validation_errors": [],
  "report_ingestion_result_path": ".codex-orchestrator/runs/P0002_attempt1/gates/report_ingestion_result.json",
  "repair_hint": "Use object entries with patchlet_id, probe_root, and run_id."
}
```

Do not remove existing fields.

## 6.3 Operator event additions

`patchlet_report_validated` failure events must include:

```json
{
  "details": {
    "report_valid": false,
    "failure_signature": "probe_artifact_refs_not_objects",
    "validation_errors": [],
    "repair_hint": "Use object entries with patchlet_id, probe_root, and run_id.",
    "report_ingestion_result_path": ".codex-orchestrator/runs/P0002_attempt1/gates/report_ingestion_result.json"
  }
}
```

## 6.4 Tests

Create:

```text
tests/integration/test_report_validation_failure_metadata.py
```

Add:

```python
test_failure_record_contains_failure_signature_for_probe_ref_string_error
test_failure_record_contains_structured_validation_errors
test_failure_record_contains_report_ingestion_result_path
test_failure_record_contains_repair_hint
test_operator_event_contains_failure_signature
test_operator_event_contains_structured_validation_errors
test_operator_event_contains_report_ingestion_result_path
test_operator_event_summary_is_operator_readable
```

Focused command:

```bash
uv run --no-sync pytest -q tests/integration/test_report_validation_failure_metadata.py
```

## 6.5 Acceptance

Structured signature and validation details are visible in machine-readable failure records and operator events.

---

# Phase 7 — Loop governor signature normalization from structured evidence

## 7.1 Goal

The live failure class must normalize to:

```text
probe_artifact_refs_not_objects
```

not:

```text
unknown_repeated_failure
```

## 7.2 Signature priority

Implement this priority:

```text
1. report_ingestion_result.normalized_failure_signature
2. structured_validation_errors[].normalized_signature
3. failure_record.failure_signature
4. operator_event.details.failure_signature
5. fallback text normalization
6. unknown_repeated_failure
```

## 7.3 Fallback text normalization

Fallback text normalization should also recognize the live jsonschema pattern when field context is available:

```text
'<path>' is not of type 'object'
```

with field context:

```text
probe_artifact_refs
```

as:

```text
probe_artifact_refs_not_objects
```

## 7.4 Tests

Create:

```text
tests/unit/test_report_failure_signature_normalization.py
```

Add:

```python
test_signature_prefers_report_ingestion_result_signature
test_signature_uses_structured_validation_error_signature
test_signature_uses_failure_record_signature
test_signature_normalizes_live_jsonschema_object_type_message_with_field_context
test_signature_does_not_call_live_message_unknown_when_probe_field_known
test_signature_falls_back_unknown_when_no_field_context
test_loop_governor_records_probe_artifact_refs_not_objects_for_live_shape
```

Extend:

```text
tests/integration/test_loop_governor_report_signature.py
```

Add:

```python
test_loop_governor_warning_uses_probe_artifact_refs_not_objects
test_loop_governor_warning_does_not_use_unknown_for_probe_ref_string_errors
test_loop_governor_counts_repeated_probe_ref_string_errors
test_live_progress_prints_specific_probe_ref_signature_warning
```

Focused commands:

```bash
uv run --no-sync pytest -q tests/unit/test_report_failure_signature_normalization.py
uv run --no-sync pytest -q tests/integration/test_loop_governor_report_signature.py
```

## 7.5 Acceptance

The exact live failure class never becomes `unknown_repeated_failure` when structured field context is available.

---

# Phase 8 — Report-shape repair routing and report-only repair guard

## 8.1 Goal

Prevent pure report-shape failures from causing repeated full patchlet regeneration.

## 8.2 Routing policy

When worker exits code 0 and report validation fails only because of report shape:

```text
1. Try report-ingestion normalization.
2. If normalization succeeds, continue to wrapper gate.
3. If normalization fails but product/probe evidence exists, route to report-only repair.
4. If report-only repair is unavailable or fails, safe-fail with evidence.
5. Do not generate a new full product patchlet for the same pure report-shape error.
```

## 8.3 Report-only repair artifact

Add:

```text
.codex-orchestrator/runs/<attempt_id>/gates/report_repair_result.json
```

Shape:

```json
{
  "schema_version": "1.0",
  "kind": "report_repair_result",
  "patchlet_id": "P0002",
  "attempt_id": "P0002_attempt1",
  "attempted": true,
  "accepted": true,
  "allowed_write_paths": [
    ".codex-orchestrator/reports/P0002.json",
    ".codex-orchestrator/runs/P0002_attempt1/worker_stage/05_final_report.md"
  ],
  "product_runtime_clean_before": true,
  "product_runtime_clean_after": true,
  "report_valid_after": true,
  "repair_hint_used": "Use object entries with patchlet_id, probe_root, and run_id."
}
```

## 8.4 Guard behavior

If report-only repair attempts to change product/runtime files, reject it.

If report-only repair changes existing probe artifacts, reject it.

If report-only repair still produces string refs, reject it with structured signature.

## 8.5 Tests

Create:

```text
tests/integration/test_report_shape_failure_repair_routing.py
```

Add:

```python
test_pure_report_shape_error_routes_to_normalization_before_repair
test_safe_string_refs_do_not_create_repair_plan
test_unsafe_report_shape_error_routes_to_report_only_repair
test_report_only_repair_has_allowed_write_paths
test_report_only_repair_rejects_product_file_edit
test_report_only_repair_rejects_probe_artifact_edit
test_report_only_repair_rejects_still_invalid_report
test_report_shape_error_does_not_generate_full_patchlet_when_report_only_possible
test_report_shape_error_safe_fails_when_report_only_repair_unavailable
test_report_shape_safe_failure_preserves_evidence
```

Focused command:

```bash
uv run --no-sync pytest -q tests/integration/test_report_shape_failure_repair_routing.py
```

## 8.6 Acceptance

Report-shape failures no longer trigger repeated full patchlet regeneration when normalization or report-only repair is appropriate.

---

# Phase 9 — Full-chain fake real-Codex reproduction

## 9.1 Goal

Reproduce the live failure shape deterministically without real Codex and prove it is closed.

## 9.2 Scenario A — String probe refs are normalized

Fake worker writes a report with:

```json
{
  "probe_artifact_refs": [
    ".artifacts/probes/P0001/run_001/before_state.json",
    ".artifacts/probes/P0001/run_001/after_state.json"
  ]
}
```

Expected:

```text
raw report preserved
canonical report has object refs
report_ingestion_result accepted=true
wrapper gate can proceed
failure record not created for probe ref shape
loop governor not updated with unknown_repeated_failure
```

## 9.3 Scenario B — Repeated non-coercible shape errors are specific

Fake worker writes invalid outside paths repeatedly.

Expected:

```text
failure_signature specific, not unknown
loop governor counts specific signature
safe-fail mode blocks if enabled
warning mode warns if enabled
```

## 9.4 Scenario C — Report-only repair prevents full regeneration

Fake worker produces a non-coercible report-shape error that report-only repair can fix.

Expected:

```text
report-only repair artifact written
product files unchanged
probe files unchanged
canonical report valid
no new full product patchlet generated
```

## 9.5 Tests

Create:

```text
tests/integration/test_real_codex_probe_ref_string_reproduction.py
```

Add:

```python
test_fake_real_codex_string_probe_refs_are_normalized_and_accepted
test_fake_real_codex_absolute_string_probe_refs_are_normalized_and_accepted
test_fake_real_codex_report_ingestion_preserves_raw_report
test_fake_real_codex_canonical_report_has_object_refs
test_fake_real_codex_loop_governor_does_not_record_unknown_for_normalized_report
test_fake_real_codex_repeated_noncoercible_probe_ref_error_has_specific_signature
test_fake_real_codex_safe_fail_blocks_repeated_noncoercible_probe_ref_error
test_fake_real_codex_report_only_repair_prevents_full_regeneration
test_fake_real_codex_report_only_repair_preserves_product_files
test_fake_real_codex_report_only_repair_preserves_probe_files
```

Focused command:

```bash
uv run --no-sync pytest -q tests/integration/test_real_codex_probe_ref_string_reproduction.py
```

## 9.6 Acceptance

The exact live failure shape is reproduced and closed deterministically.

---

# Phase 10 — Docs

## 10.1 Docs to update

Update:

```text
README.md
docs/cli.md
docs/autonomous_loop.md
docs/real_codex_smoke.md
docs/runbooks/real_codex_smoke_runbook.md
docs/release.md
IMPLEMENTATION_STATUS.md
```

## 10.2 Required docs content

Explain:

```text
canonical probe_artifact_refs object shape
why raw string refs are accepted only at report ingress
raw report vs canonical report
report_ingestion_result.json
structured report validation errors
probe_artifact_refs_not_objects failure signature
loop governor specific signature behavior
report-only repair routing
why full patchlet regeneration is avoided for pure report-shape errors
how to inspect report ingestion artifacts
how to inspect prompt contract examples
how to run deterministic tests
why default tests do not run real Codex
```

## 10.3 Docs tests

Create:

```text
tests/unit/test_docs_real_codex_report_contract_hardening.py
```

Add:

```python
test_docs_explain_probe_artifact_refs_object_shape
test_docs_explain_raw_string_refs_are_ingress_only
test_docs_explain_raw_and_canonical_reports
test_docs_explain_report_ingestion_result
test_docs_explain_structured_validation_errors
test_docs_explain_probe_artifact_refs_not_objects_signature
test_docs_explain_loop_governor_specific_signature
test_docs_explain_report_only_repair
test_docs_explain_full_patchlet_regeneration_avoidance
test_docs_explain_default_tests_do_not_run_real_codex
```

Focused command:

```bash
uv run --no-sync pytest -q tests/unit/test_docs_real_codex_report_contract_hardening.py
```

---

# Phase 11 — Final verification

Run all focused tests:

```bash
export UV_CACHE_DIR=/tmp/uv-cache

uv run --no-sync pytest -q tests/unit/test_probe_artifact_ref_normalizer.py
uv run --no-sync pytest -q tests/unit/test_structured_report_validation_errors.py
uv run --no-sync pytest -q tests/unit/test_report_failure_signature_normalization.py
uv run --no-sync pytest -q tests/integration/test_report_ingestion_probe_refs.py
uv run --no-sync pytest -q tests/integration/test_patchlet_report_probe_ref_schema.py
uv run --no-sync pytest -q tests/integration/test_report_contract_prompt_hardening.py
uv run --no-sync pytest -q tests/integration/test_report_validation_failure_metadata.py
uv run --no-sync pytest -q tests/integration/test_loop_governor_report_signature.py
uv run --no-sync pytest -q tests/integration/test_report_shape_failure_repair_routing.py
uv run --no-sync pytest -q tests/integration/test_real_codex_probe_ref_string_reproduction.py
uv run --no-sync pytest -q tests/unit/test_docs_real_codex_report_contract_hardening.py
```

Then run full verification:

```bash
uv run --no-sync pytest -q
uv run --no-sync python -m codex_orchestrator --version
uv run --no-sync cxor --version
uv run --no-sync codex-orchestrator --version
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py
git status --short
```

Default smoke must still skip unless explicit real Codex execution is enabled.

Do not run explicit real Codex.

---

# Optional manual real-Codex smoke after deterministic green

Do not run this during implementation.

After deterministic tests are green, the operator may run:

```bash
rm -rf /tmp/cxor-target-report-contract-smoke
mkdir -p /tmp/cxor-target-report-contract-smoke
cd /tmp/cxor-target-report-contract-smoke

git init
cat > app.py <<'PY'
def main():
    return "not ok"
PY

cat > master_prompt.md <<'MD'
Make app return ok and prove it.
MD

git add app.py master_prompt.md
git commit -m "Initial target"

cd /home/theyeq-admin-lap/master-workspace-research/codex-orchestrator

CODEX_PATCHLET_TIMEOUT_SECONDS=600 \
uv run --no-sync cxor auto \
  --repo /tmp/cxor-target-report-contract-smoke \
  --master /tmp/cxor-target-report-contract-smoke/master_prompt.md \
  --until DONE \
  --worker-mode real_codex \
  --use-worktree \
  --live-progress \
  --loop-governor-mode safe-fail \
  --max-repeated-failure-signature 3
```

Second terminal:

```bash
uv run --no-sync cxor monitor --repo /tmp/cxor-target-report-contract-smoke --follow
uv run --no-sync cxor status --repo /tmp/cxor-target-report-contract-smoke --watch
uv run --no-sync cxor prompts --repo /tmp/cxor-target-report-contract-smoke --latest
```

Expected:

```text
No repeated probe_artifact_refs string-object loop.
If real Codex writes string probe refs, report_ingestion_result records normalization.
Loop governor does not show unknown_repeated_failure for this failure class.
If report refs cannot normalize, safe-fail preserves specific evidence.
```

---

# Required final report format

Return exactly this structure.

Do not compress details.

```text
# Codex TDD Report — Real-Codex Report Contract and Probe Artifact Reference Hardening

## 1. Baseline

- Python:
- uv:
- codex version:
- initial full test result:
- git status at start:
- current branch:
- HEAD:

## 2. Evidence basis

- evidence report:
- proven repeated invalid field:
- expected canonical schema shape:
- actual real-Codex shape:
- completed failed attempts:
- loop governor observed signature:
- expected signature:
- prompt contract gap:
- repair prompt gap:
- target product cleanliness:

## 3. Architecture decisions implemented

- canonical probe ref shape:
- raw ingress normalization:
- raw/canonical report preservation:
- structured validation errors:
- report ingestion result:
- prompt contract hardening:
- failure record metadata:
- operator event metadata:
- loop governor signature source:
- report-only repair routing:
- docs:

## 4. Phase results

### Phase 1 — Probe artifact reference canonical model and normalizer

- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior implemented:
- rollback:

### Phase 2 — Structured report validation errors

- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior implemented:
- rollback:

### Phase 3 — Report ingestion gate and raw/canonical preservation

- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior implemented:
- artifacts added:
- rollback:

### Phase 4 — Patchlet report schema update

- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior implemented:
- rollback:

### Phase 5 — Prompt contract hardening

- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior implemented:
- rollback:

### Phase 6 — Failure records and operator events with structured signatures

- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior implemented:
- rollback:

### Phase 7 — Loop governor signature normalization from structured evidence

- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior implemented:
- rollback:

### Phase 8 — Report-shape repair routing and report-only repair guard

- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior implemented:
- rollback:

### Phase 9 — Full-chain fake real-Codex reproduction

- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior implemented:
- rollback:

### Phase 10 — Docs

- red tests:
- failing output:
- files changed:
- focused green command:
- focused green result:
- behavior implemented:
- rollback:

### Phase 11 — Final verification

- commands:
- outputs:

## 5. Probe ref normalization behavior

Describe:

- accepted relative string refs:
- accepted absolute string refs:
- rejected outside paths:
- rejected missing paths:
- derived patchlet_id:
- derived probe_root:
- derived run_id:
- file metadata:
- canonical object output:

## 6. Report ingestion behavior

Describe:

- raw report path:
- canonical report path:
- report_ingestion_result path:
- normalization_applied:
- validation_errors:
- normalized_failure_signature:
- wrapper gate input:

## 7. Structured validation behavior

Describe:

- JSON pointer:
- schema path:
- field:
- expected type:
- actual type:
- invalid value excerpt:
- repair hint:
- human message compatibility:

## 8. Prompt contract behavior

Describe:

- object-shaped valid example:
- string-shaped invalid example:
- forbidden raw string refs:
- repair prompt structured error:
- repair prompt valid example:

## 9. Failure/signature behavior

Describe:

- failure record fields:
- operator event fields:
- loop governor priority order:
- probe_artifact_refs_not_objects:
- unknown fallback behavior:

## 10. Report-only repair behavior

Describe:

- routing criteria:
- allowed write paths:
- rejected product edits:
- rejected probe edits:
- safe-failure behavior:
- full patchlet regeneration avoidance:

## 11. Full-chain reproduction

Describe:

- fake real-Codex string refs:
- normalized canonical report:
- no unknown_repeated_failure:
- report-only repair scenario:
- safe-fail scenario:

## 12. Docs

List changed docs and what each now explains.

## 13. Default smoke skip

Paste command and output:

uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py

## 14. Final verification output

Paste exact outputs:

uv run --no-sync pytest -q
uv run --no-sync python -m codex_orchestrator --version
uv run --no-sync cxor --version
uv run --no-sync codex-orchestrator --version
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py

## 15. Git status

Paste exact:

git status --short

## 16. Remaining confirmed gaps

List only confirmed gaps.

## 17. Next single highest-value increment

If deterministic report-contract hardening is complete, say:

Run a manual direct real-Codex smoke on a fresh tiny target with --live-progress and safe-fail loop governor, then capture monitor/status/prompts/report-ingestion evidence.
```

---

# Final instruction

Implement this architecture.

Do not run explicit real Codex.

Do not mutate the preserved smoke target.

Do not weaken canonical report schema semantics.

Do not let string probe refs enter canonical reports.

Do not let this live failure class become `unknown_repeated_failure` again when field context exists.

Do not route pure report-shape errors into repeated full patchlet regeneration when normalization or report-only repair is available.

Stop only at a real safety boundary, failing full suite, or a proven artifact-contract contradiction.
