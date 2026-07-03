Preflight Findings

- Baseline full suite passed before this increment.
- Existing runbook bundles are written under `.operator-runs/real-codex-smoke/`.
- Existing bundle validation is implemented by `validate_real_codex_smoke_runbook(run_dir)`.

Existing operator-run root

- Default root is `<repo>/.operator-runs/real-codex-smoke`.
- Tests can use a temporary operator root to avoid touching local operator evidence.

Existing dry-run bundle layout

- Dry-run bundles contain README, environment, git status, codex version, selected policy, skip output, explicit smoke placeholder output, result, diagnosis paths, and validation result artifacts.

Existing validation_result.json shape

- Validation results use `kind: real_codex_smoke_runbook_validation`, `valid`, `validated`, `errors`, and `warnings`.

Existing result.json shape

- Results use `kind: real_codex_smoke_operator_result` with `outcome`, `default_skip`, `explicit_smoke`, `operator_run_dir`, diagnosis path references, and validation fields.

Existing selected_policy.json shape

- Selected policy records patchlet timeout, model, reasoning, progress interval, live progress enablement, and dry-run/explicit-run mode.

Existing diagnosis_paths.json shape

- Diagnosis paths are stored as an object with string-or-null diagnosis/run/stdout/stderr/output/progress fields and copied diagnosis file names.

Existing validator behavior

- The validator is read-only and returns structured errors for missing or malformed artifacts.
- It does not invoke Codex or pytest.

List command output design

- Summary objects should include run directory, timestamp, validation status, outcome, selected policy, timeout, diagnosis category, and artifact paths.
- JSON output should expose full structured details.
- Human output should be compact and should not print raw bundle JSON.

Read-only proof strategy

- Hash generated bundle files before and after listing.
- Listing should only read bundle files and validator output.

No-Codex proof strategy

- Put a marker `codex` binary on PATH and assert no marker is created by list operations.

Malformed bundle strategy

- Invalid or incomplete directories should be included in list results with structured errors instead of crashing or being hidden.

Stop conditions

- Stop if listing invokes Codex or pytest, mutates bundles, hides invalid bundles, crashes on malformed bundles, or emits unparseable JSON.
