Preflight Findings

- Baseline suite passed: 410 passed, 2 skipped.
- Working tree was clean before edits.
- Python is 3.10.20 under `uv run --no-sync`.
- Codex CLI is available as `codex-cli 0.142.4`.

Current timeout env parsing

- `resolve_patchlet_timeout_seconds` parses `CODEX_PATCHLET_TIMEOUT_SECONDS` or `CODEX_TIMEOUT_SECONDS` with raw `int(...)`.
- Invalid or non-positive timeout values are not converted to structured user-facing errors.
- `CODEX_PROGRESS_INTERVAL_SECONDS` is not currently parsed or validated.

Current timeout safe-failure evidence

- Timeout command evidence is preserved in `command.json` with `timed_out`, `exit_code`, and `timeout_seconds`.
- Run manifests include timeout/model/progress metadata from `command.json` when a worker failure is recorded.
- Timeout safe-failure still preserves stdout, stderr, command, output, and progress artifacts.

Current diagnosis categories

- Diagnosis currently classifies generic output containing `timeout` as `network_or_api_error`.
- It does not prioritize `command.json` or run manifest evidence proving an orchestrator subprocess timeout.

Current smoke skip behavior

- Real Codex smoke is still guarded by the `real_codex` marker and skips by default without `--run-real-codex`.
- The default suite passed with 2 skipped tests.

Implementation order

- Add red tests for structured timeout/progress env validation.
- Implement positive-integer policy parsing and convert policy errors to `WorkerPreconditionError` before Codex launch.
- Add red diagnosis tests for `orchestrator_subprocess_timeout`.
- Implement diagnosis classification from `command.json`/run manifest before generic output categories.
- Add docs tests and docs updates.
- Reverify default smoke skip and full suite.

Stop conditions

- Stop if baseline or full suite fails.
- Stop if default tests invoke real Codex.
- Stop if invalid env launches Codex.
- Stop if timeout parsing becomes unbounded or weaker.
- Stop if diagnosis guesses unsupported causes or hides command evidence.
- Stop if validators are weakened.
