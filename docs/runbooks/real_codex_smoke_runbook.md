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

## Compare Runs

To compare runs, diff `selected_policy.json`, `result.json`, and
`diagnosis_paths.json` across timestamped directories. Use stdout/stderr files
to verify what the smoke printed, and use copied diagnosis artifacts to inspect
the preserved cause classification.

`safe_failure is a successful runbook capture`, not task DONE. It means the
runbook captured evidence for a contained real-Codex failure. `DONE means the
orchestrator validators accepted the run`, including report validation, probe
artifact validation, wrapper gates, transaction groups, and global verification.
