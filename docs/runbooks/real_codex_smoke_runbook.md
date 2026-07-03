# Real Codex Smoke Runbook

Default pytest does not run real Codex. The `real-codex-smoke-runbook`
command is an operator-controlled evidence capture for manual installed-Codex
smoke runs, and it is not part of the default test suite.

## Dry Run

Use dry-run mode first:

```bash
export UV_CACHE_DIR=/tmp/uv-cache
uv run --no-sync cxor real-codex-smoke-runbook --dry-run
```

`--dry-run` creates the operator-run artifact directory, captures environment
and policy evidence, runs the default skipped smoke check, and does not invoke
real Codex. The expected result is `result.json` with outcome dry_run.

## Explicit Run

Use explicit mode only when the environment is safe for an installed Codex
invocation:

```bash
export UV_CACHE_DIR=/tmp/uv-cache
CODEX_PATCHLET_TIMEOUT_SECONDS=600 \
uv run --no-sync cxor real-codex-smoke-runbook --run-real-codex
```

`--run-real-codex` may consume account, network, model availability, token, and
wall-clock resources. It may run up to `CODEX_PATCHLET_TIMEOUT_SECONDS`.
Patchlet default policy is recorded in `selected_policy.json`, including
`codex_patchlet_timeout_seconds`, model, reasoning, and progress interval.

## Artifact Layout

Each run writes:

```text
.operator-runs/real-codex-smoke/<timestamp>-real-codex-smoke/
  README.md
  environment.txt
  git_status.txt
  codex_version.txt
  selected_policy.json
  default_skip_stdout.txt
  default_skip_stderr.txt
  explicit_smoke_stdout.txt
  explicit_smoke_stderr.txt
  result.json
  diagnosis_paths.json
```

The runbook preserves raw stdout and stderr even when explicit smoke output
cannot be parsed as JSON. When diagnosis files are referenced and present, the
runbook copies them into the operator-run directory as `diagnosis.json` and
`diagnosis.md`.

Each bundle also writes `validation_result.json`. Validate any saved bundle
again with:

```bash
cxor validate-real-codex-smoke-runbook --run-dir .operator-runs/real-codex-smoke/<timestamp>-real-codex-smoke
```

The validator is read-only, does not run Codex, does not run pytest, and only
inspects the supplied operator-run directory. It checks JSON schemas for
`selected_policy.json`, `result.json`, and `diagnosis_paths.json`:

- `real_codex_smoke_selected_policy.schema.json`
- `real_codex_smoke_operator_result.schema.json`
- `real_codex_smoke_diagnosis_paths.schema.json`
- `real_codex_smoke_runbook_validation.schema.json`

It also checks required text evidence files including `environment.txt`,
`git_status.txt`, `codex_version.txt`, `default_skip_stdout.txt`,
`default_skip_stderr.txt`, `explicit_smoke_stdout.txt`, and
`explicit_smoke_stderr.txt`. Dry-run bundles and explicit-run bundles can both
be validated after capture.

## Compare Runs

To compare runs, diff `selected_policy.json`, `result.json`, and
`diagnosis_paths.json` across timestamped directories. Use stdout/stderr files
to verify what the smoke printed, and use copied diagnosis artifacts to inspect
the preserved cause classification.

List local bundles first:

```bash
cxor list-real-codex-smoke-runbooks
cxor list-real-codex-smoke-runbooks --json
cxor list-real-codex-smoke-runbooks --root .operator-runs/real-codex-smoke
cxor list-real-codex-smoke-runbooks --latest
cxor list-real-codex-smoke-runbooks --only-invalid
cxor list-real-codex-smoke-runbooks --limit 10
```

The list command is read-only, does not run Codex, and does not run pytest. It
summarizes each timestamped run's outcome, validation status, selected
model/reasoning, timeout, `timed_out`, diagnosis category, `result.json`, and
`validation_result.json`. Invalid bundles are listed rather than hidden. Use
`cxor validate-real-codex-smoke-runbook --run-dir <dir>` for full validation of
one bundle.

Export one validated bundle for release evidence:

```bash
cxor export-real-codex-smoke-runbook --run-dir <dir>
cxor export-real-codex-smoke-runbook --run-dir <dir> --out /tmp/runbook.zip
cxor export-real-codex-smoke-runbook --run-dir <dir> --force
```

The export command creates a zip archive plus sidecar manifest. The manifest
records source bundle validity, outcome, selected model/reasoning, timeout,
diagnosis category, relative file paths, file sizes, and sha256 hashes. The
source bundle is not modified. Invalid bundles require `--force`.

`safe_failure is a successful runbook capture`, not task DONE. It means the
runbook captured evidence for a contained real-Codex failure. `DONE means the
orchestrator validators accepted the run`, including report validation, probe
artifact validation, wrapper gates, transaction groups, and global verification.

## Live Progress And Accepted Results

With `--run-real-codex --live-progress`, the runbook tees only compact
`[cxor:...]` live progress lines. Use `--no-live-progress` or
`CXOR_LIVE_CODEX_PROGRESS=0` to silence terminal progress. The durable record is
still `progress.jsonl`.

Accepted changes are not applied to the operator working tree during the smoke.
They advance `refs/cxor/runs/<run_id>/integration`; the target repo remains
clean between patchlets and subsequent worktrees start from the integration
SHA. After DONE, use `cxor apply-results --mode patch`, `cxor apply-results
--mode branch`, or `cxor apply-results --mode working-tree`.
