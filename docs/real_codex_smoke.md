# Real Codex Smoke

The real Codex smoke is opt-in only. The default suite does not run real Codex.

Run it with:

```bash
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py --run-real-codex -s
```

Patchlet real-Codex execution defaults to 10 minutes / 600 seconds. Operators
can set `CODEX_TIMEOUT_SECONDS`, and patchlet-specific runs can set
`CODEX_PATCHLET_TIMEOUT_SECONDS` to take precedence. The patchlet receives
`CXOR_TIMEOUT_SECONDS` and `CXOR_SOFT_DEADLINE_SECONDS`.

Invalid timeout env values are structured errors before Codex launches.
`CODEX_TIMEOUT_SECONDS`, `CODEX_PATCHLET_TIMEOUT_SECONDS`, and
`CODEX_PROGRESS_INTERVAL_SECONDS` must be positive integer seconds. Invalid
values report the env var name, the bad value, and `expected positive integer
seconds`.

That smoke exercises:

```bash
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode real_codex --use-worktree
```

The generated smoke prompt injects the operator contract from:

- `src/codex_orchestrator/prompt_templates/real_codex_patchlet_contract.md`
- `.codex-orchestrator/subprompts/<attempt>.md`

Before doing any task work, real Codex is instructed to read:

- `.codex-orchestrator/runs/P0001_attempt1/worker_memory/TASK_CONTRACT.md`
- `.codex-orchestrator/runs/P0001_attempt1/worker_memory/LIVE_MEMORY.md`
- `.codex-orchestrator/runs/P0001_attempt1/worker_memory/WRITE_THESE_FILES.md`

Then it must write:

- `.codex-orchestrator/runs/P0001_attempt1/worker_stage/00_preflight.md`

Before the final response, it must write:

- `.codex-orchestrator/runs/P0001_attempt1/worker_stage/05_final_report.md`

The worker must use `CXOR_WORKER_STAGE_DIR`, `CXOR_PREFLIGHT_PATH`, and
`CXOR_FINAL_REPORT_PATH` for stage files. Do not create target-root
worker_stage/. If real Codex writes a top-level `worker_stage/`, diagnosis
reports `worker_capsule_path_violation`. This is a Codex path-obedience issue,
not orchestrator wiring failure. Do not weaken validators.

The smoke remains validator-backed and evidence-bound:

- inspect `.codex-orchestrator/runs/`, `.codex-orchestrator/failures/`, and `.artifacts/probes/`
- use `cxor inspect-capsule --repo /path/to/target-repo --attempt P0001_attempt1`
- use `cxor validate-capsule --repo /path/to/target-repo --attempt P0001_attempt1`
- use `cxor diagnose-real-codex --repo /path/to/target-repo --attempt P0001_attempt1` after safe failure
- do not weaken validators
- do not allow blind retry

Safe failure should preserve:

- `run_manifest.json`
- `stdout.txt`
- `stderr.txt`
- `command.json`
- `output.jsonl`
- `progress.jsonl`

`progress.jsonl` is a compact liveness stream, not success evidence. Timeout
safe-failure means containment and preserved evidence; it is not task success
and does not mean `DONE`.

When `command.json` or the run manifest proves `timed_out=true` with
`exit_code=124`, `diagnose-real-codex` reports
`orchestrator_subprocess_timeout`. This category means the orchestrator
terminated the Codex subprocess at the configured timeout. It is not task
success, and it links `progress.jsonl` if Codex emitted liveness before
timeout.

The explicit real-Codex smoke is an operator-run command. It is not part of the
default test suite and should only be run when the environment is safe for an
installed Codex invocation.

For repeatable evidence capture, use the operator runbook:

```bash
uv run --no-sync cxor real-codex-smoke-runbook --dry-run
CODEX_PATCHLET_TIMEOUT_SECONDS=600 uv run --no-sync cxor real-codex-smoke-runbook --run-real-codex
```

Default pytest does not run real Codex. `--dry-run` does not invoke real Codex
and writes `result.json` with outcome dry_run. `--run-real-codex` may consume
account, network, model, token, and wall-clock resources and may run up to
`CODEX_PATCHLET_TIMEOUT_SECONDS`.

The runbook writes
`.operator-runs/real-codex-smoke/<timestamp>-real-codex-smoke/` with
`README.md`, `environment.txt`, `git_status.txt`, `codex_version.txt`,
`selected_policy.json`, `default_skip_stdout.txt`, `default_skip_stderr.txt`,
`explicit_smoke_stdout.txt`, `explicit_smoke_stderr.txt`, `result.json`, and
`diagnosis_paths.json`. Compare runs by diffing `selected_policy.json`,
`result.json`, and `diagnosis_paths.json`.

`safe_failure is a successful runbook capture`, not task DONE. `DONE means the
orchestrator validators accepted the run`.

Patchlet Codex defaults to `gpt-5.4-mini` with reasoning `medium`.
Non-patchlet/orchestrator Codex profiles default to `gpt-5.5` with reasoning
`medium`.

If the preserved artifacts do not justify a narrower claim, the diagnosis
should stay at `unknown_codex_nonzero_exit`.

Real success is not guaranteed. It still depends on real Codex producing a
valid report and durable probe artifacts that satisfy the existing validators.

## Live Progress And Integration Results

Explicit runbook mode enables compact live progress by default and tees only
lines beginning with `[cxor:`. Disable terminal progress with
`CXOR_LIVE_CODEX_PROGRESS=0` or pass `--no-live-progress`; `progress.jsonl`
remains the durable liveness record. Live progress does not prove success, and
safe failure is not DONE.

Accepted real-Codex changes advance `refs/cxor/runs/<run_id>/integration`; the
target repo remains clean between patchlets and the next worktree starts from
the integration SHA. DONE verifies that integration SHA. Use
`cxor apply-results --mode patch`, `cxor apply-results --mode branch`, or
`cxor apply-results --mode working-tree` after DONE to consume results.

The integration artifacts used by those steps are schema-validated:
`integration_state.json` uses `integration_state.schema.json`,
`accepted_changes.jsonl` is validated line-by-line with
`accepted_change.schema.json`, checkpoints use
`integration_checkpoint.schema.json`, and apply-results files such as
`patch_result.json` use `apply_results_result.schema.json`.

```bash
cxor validate-integration-artifacts --repo /path/to/target-repo
```

The validator is read-only, does not run Codex, and helps compare whether a
safe failure preserved structurally valid integration evidence.
