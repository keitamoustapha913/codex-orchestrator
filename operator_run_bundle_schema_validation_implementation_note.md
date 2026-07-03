Preflight Findings

- Baseline: Python 3.10.20 with uv workflow; full suite passed before changes.
- Dry-run runbook creates `.operator-runs/real-codex-smoke/<timestamp>-real-codex-smoke/`.
- The generated dry-run bundle is evidence-only and does not invoke explicit real Codex.

Existing operator-run bundle shape

- README.md
- environment.txt
- git_status.txt
- codex_version.txt
- selected_policy.json
- default_skip_stdout.txt
- default_skip_stderr.txt
- explicit_smoke_stdout.txt
- explicit_smoke_stderr.txt
- result.json
- diagnosis_paths.json
- copied diagnosis.json / diagnosis.md only when referenced files exist during explicit safe-failure capture.

Existing selected_policy.json shape

- schema_version
- kind = real_codex_smoke_selected_policy
- codex_patchlet_timeout_seconds
- codex_timeout_seconds
- codex_model
- codex_reasoning
- codex_progress_interval_seconds
- live_progress_enabled
- run_real_codex
- dry_run

Existing result.json shape

- schema_version
- kind = real_codex_smoke_operator_result
- outcome
- default_skip
- explicit_smoke
- operator_run_dir
- diagnosis_paths
- explicit runs may also include parsed smoke top-level fields.

Existing diagnosis_paths.json shape

- object shape with schema_version and kind.
- Path fields are strings or null.
- Dry-run stores null path values.
- Explicit safe-failure may store source diagnosis paths and copied diagnosis file names.

Existing schema infrastructure

- Schemas live in `src/codex_orchestrator/schemas/`.
- Validation uses `codex_orchestrator.validators.schema_validator`.
- Prior integration artifact validation returns structured JSON with valid/validated/errors.

Existing CLI validation pattern

- `cxor validate-integration-artifacts --repo ...` prints structured JSON and exits 0/1.
- New runbook validator should follow that pattern but accept `--run-dir`.

Validator design

- Validate selected_policy.json, result.json, and diagnosis_paths.json against JSON Schema.
- Validate required text evidence files for presence and practical minimum content.
- Validate copied diagnosis files only when diagnosis_paths.json references them.
- Return structured errors and warnings.

Read-only proof strategy

- Hash bundle files before and after validator calls in tests.
- Validation should only read the run directory and schemas.

No-Codex proof strategy

- Put a fake marker `codex` binary on PATH during validator/CLI tests.
- Assert the marker is not created.
- Do not run pytest from the validator.

Risks and stop conditions

- Do not overfit text evidence to exact pytest progress output.
- Do not require explicit real-Codex runs for validation tests.
- Do not accept missing required evidence files.
- Do not let invalid JSON pass silently.
