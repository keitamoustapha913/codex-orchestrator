Preflight Findings
Baseline suite is green with 532 passed and 2 skipped. The workspace already contains the live-progress and integration-ref changes from the prior increment.

Existing schema validation infrastructure
The project uses jsonschema through src/codex_orchestrator/validators/schema_validator.py. Public helpers are validate_json(data, schema_name) and validate_json_file(path, schema_name), returning lists of error strings.

Existing schema file locations
Schema files live under src/codex_orchestrator/schemas/ and are named <artifact>.schema.json.

Existing JSON schema library usage
jsonschema.Draft202012Validator is used. Schemas declare "$schema": "https://json-schema.org/draft/2020-12/schema".

Existing CLI validator commands
Existing commands include validate-state, validate-report, validate-capsule, and validate-global style commands. They print either stable text or JSON depending on command purpose.

Integration artifact shapes currently generated
integration_state.json includes schema_version, kind, target_head_sha, integration_ref, integration_sha, apply_mode, target_product_dirty_allowed, accepted_patchlets, last_checkpoint_path, and final_diff_path.

Accepted changes JSONL shape
accepted_changes.jsonl contains one accepted_change object per non-empty line with run_id, patchlet_id, attempt_id, previous/new integration SHA, integration_ref, allowed/changed product runtime files, diff/report/probe/wrapper paths, and accepted_at.

Checkpoint artifact shape
checkpoints/P0001.json contains integration_checkpoint metadata, changed product/runtime files, diff path, wrapper gate result, and target_working_tree_clean_after_checkpoint.

Apply-results artifact shape
apply_results/<mode>_result.json contains apply_results_result metadata, mode, target/integration SHA, integration_ref, final_diff_path, mutated_working_tree, created_branch, and created_at.

Schema integration strategy
Add four schema files in the existing schemas package. Add an integration artifact validator module that uses existing schema_validator helpers, validates JSONL line-by-line, and returns structured JSON-compatible results. Expose it through cxor validate-integration-artifacts.

Risks and stop conditions
Do not alter integration-ref behavior unless generated artifacts contradict the approved shape. Do not make validation invoke Codex. Do not mutate product/runtime files while validating. Keep bad JSONL lines visible as structured errors.
