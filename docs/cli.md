# CLI

Primary MVP command:

```bash
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode mock
```

Stage commands implemented:

```bash
cxor init
cxor status
cxor validate-state
cxor census
cxor normalize
cxor classify-evidence
cxor build-inventory
cxor extract-invariants
cxor compile-patchlets
cxor run-next
cxor run-all
cxor validate-report
cxor verify-group
cxor verify-all-groups
cxor verify-global
cxor inspect-capsule
cxor validate-capsule
cxor diagnose-real-codex
cxor real-codex-smoke-runbook
cxor list-real-codex-smoke-runbooks
cxor export-real-codex-smoke-runbook
cxor classify-failures
cxor plan-repair
cxor apply-repair
cxor rediscover
cxor rebuild-inventory
cxor regenerate-patchlets
cxor auto
```

Repair loop:
`failure -> classification -> repair plan -> apply repair -> regenerate patchlets -> verify`

No blind retry. Use:

```bash
cxor apply-repair --repo /path/to/target-repo
cxor regenerate-patchlets --repo /path/to/target-repo --from-repair-plan latest
```

These repair replay commands are idempotent when the corresponding durable artifacts already exist:

```bash
cxor apply-repair --repo /path/to/target-repo
cxor regenerate-patchlets --repo /path/to/target-repo --from-repair-plan latest
cxor auto --repo /path/to/target-repo --resume --until DONE --worker-mode mock
```

If the workflow is already `DONE`, `cxor apply-repair` and `cxor regenerate-patchlets` become terminal no-op commands. They exit successfully, report the no-op, and leave state, patchlet index, final verification, and product/runtime files unchanged.

Durable probe artifacts and `probe_artifact_refs` are required for successful patchlet reports.

Transaction group and global verification commands:

```bash
cxor verify-group --repo /path/to/target-repo TG001
cxor verify-all-groups --repo /path/to/target-repo
cxor verify-global --repo /path/to/target-repo
```

Advanced repair and rediscovery commands:

```bash
cxor rediscover --repo /path/to/target-repo --scope impacted
cxor rediscover --repo /path/to/target-repo --scope full
cxor rebuild-inventory --repo /path/to/target-repo --scope impacted
```

Optional worktree execution with validated merge:

```bash
cxor run-next --repo /path/to/target-repo --worker-mode mock --use-worktree
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode mock --use-worktree
```

Worktree mode is optional, not default. It requires a clean target repo apart from volatile workflow artifacts and isolates unauthorized diffs before any target product/runtime merge.

Opt-in real Codex smoke:

```bash
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py --run-real-codex -s
```

This smoke is not part of the default test suite. It exercises `cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode real_codex --use-worktree`.

Fake-success parity also covers this exact `worker_mode=real_codex` path with a
fake Codex binary that reaches `DONE` only by writing a valid report and
durable probe artifacts. That proves the orchestrator wiring without claiming
that installed real Codex will always succeed.

Operator rules:

- do not weaken validators for real Codex;
- real Codex success to DONE is not guaranteed and still depends on valid report and durable probe artifact output;
- inspect `run_manifest.json` for the failed patchlet attempt entry;
- inspect `.codex-orchestrator/runs/`, `.codex-orchestrator/failures/`, and `.artifacts/probes/`;
- on safe failure, expect a `WORKER_FAILED` run-manifest entry plus preserved `stdout.txt`, `stderr.txt`, `command.json`, and `output.jsonl`;
- treat contained failure evidence as acceptable smoke output when real Codex does not reach `DONE`.

Patchlet real-Codex runs default to a 10 minutes / 600 seconds timeout.
`CODEX_TIMEOUT_SECONDS` overrides the global timeout, while
`CODEX_PATCHLET_TIMEOUT_SECONDS` wins for patchlet execution. The generated
Worker Capsule and subprompt tell Codex the hard timeout and soft deadline
(`timeout - 60` seconds) and require a durable final report before timeout if
the task cannot complete.

Invalid timeout env values fail structurally before Codex launches. Values for
`CODEX_TIMEOUT_SECONDS`, `CODEX_PATCHLET_TIMEOUT_SECONDS`, and
`CODEX_PROGRESS_INTERVAL_SECONDS` must be positive integer seconds; otherwise
the error names the env var, the bad value, and `expected positive integer
seconds`.

`progress.jsonl` under the attempt run directory records compact real-Codex
liveness signals. It is not success evidence. A timeout safe-failure means the
orchestrator contained the failed attempt and preserved artifacts; it is not
task success and it is not `DONE`.

`diagnose-real-codex` reports command evidence with `timed_out=true` and
`exit_code=124` as `orchestrator_subprocess_timeout`. This diagnosis is
bounded containment, not task success, and it links `progress.jsonl` when that
liveness artifact exists.

The explicit real-Codex smoke is operator-run only and is not part of the
default test suite.

Operator-controlled real-Codex smoke runbook:

```bash
uv run --no-sync cxor real-codex-smoke-runbook --dry-run
CODEX_PATCHLET_TIMEOUT_SECONDS=600 uv run --no-sync cxor real-codex-smoke-runbook --run-real-codex
```

Dry-run mode does not invoke real Codex and records outcome dry_run. Explicit
mode may consume account, network, model, token, and wall-clock resources up to
`CODEX_PATCHLET_TIMEOUT_SECONDS`. Each run writes
`.operator-runs/real-codex-smoke/<timestamp>-real-codex-smoke/` with
`selected_policy.json`, `result.json`, `diagnosis_paths.json`,
`explicit_smoke_stdout.txt`, and `explicit_smoke_stderr.txt`. Compare runs by
diffing `selected_policy.json`, `result.json`, and `diagnosis_paths.json`.
`safe_failure is a successful runbook capture`, not task DONE; `DONE means the
orchestrator validators accepted the run`.

Patchlet Codex defaults to `gpt-5.4-mini` and reasoning `medium`.
Non-patchlet/orchestrator Codex profiles default to `gpt-5.5` and reasoning
`medium`.

Prompt contract artifact:

- `src/codex_orchestrator/prompt_templates/real_codex_patchlet_contract.md`

During the opt-in smoke, that contract is injected into the smoke prompt and
the generated prompt artifact under `.codex-orchestrator/subprompts/`. Inspect
that generated subprompt artifact first if installed Codex fails safely.

The contract carries a minimal valid report example for `CXOR_REPORT_PATH`, a
minimal durable probe layout for `CXOR_PROBE_ROOT`, and explicit instructions
not to invent alternate paths.

CI-friendly commands that exist:

```bash
cxor doctor --repo /path/to/target-repo
cxor validate-state --repo /path/to/target-repo
cxor verify-global --repo /path/to/target-repo
cxor auto --repo /path/to/target-repo --resume --until DONE --worker-mode ci_only
```

Real Codex safe-failure diagnosis:

```bash
cxor diagnose-real-codex --repo /path/to/target-repo --attempt P0001_attempt1
```

This command does not run Codex and does not mutate product/runtime files. It
reads `stdout.txt`, `stderr.txt`, `output.jsonl`, `command.json`,
`run_manifest.json`, and the generated prompt artifact, then writes:

- generic artifact kinds: `real_codex_failure_diagnosis.json` and `real_codex_failure_diagnosis.md`
- `.codex-orchestrator/diagnostics/real_codex/P0001_attempt1_diagnosis.json`
- `.codex-orchestrator/diagnostics/real_codex/P0001_attempt1_diagnosis.md`

If the preserved artifacts do not justify a more specific root cause, the
diagnosis will report `unknown_codex_nonzero_exit`. Do not weaken validators to
force a narrower classification.

## Live Progress And Result Application

Real-Codex subprocesses may print compact live progress lines like
`[cxor:P0001_attempt1 +004s] codex: thread.started`. The durable liveness
record remains `progress.jsonl`; live progress proves only that the subprocess
is alive. Use `CXOR_LIVE_CODEX_PROGRESS=0` to silence terminal progress.

Accepted patchlets advance `refs/cxor/runs/<run_id>/integration`; the target
repo remains clean between patchlets and worktrees start from the integration
SHA. Consume accepted results explicitly:

```bash
cxor apply-results --repo /path/to/target-repo --mode patch
cxor apply-results --repo /path/to/target-repo --mode branch
cxor apply-results --repo /path/to/target-repo --mode working-tree
```

`--mode patch` does not mutate product/runtime files. `--mode branch` creates a
result branch without checkout. `--mode working-tree` requires a clean target
and mutates only after explicit operator request. A safe failure is evidence
capture, not DONE.

Integration artifact validation:

```bash
cxor validate-integration-artifacts --repo /path/to/target-repo
```

This read-only command does not run Codex. It validates
`integration_state.json` with `integration_state.schema.json`, validates
`accepted_changes.jsonl` line-by-line with `accepted_change.schema.json`,
validates checkpoint files with `integration_checkpoint.schema.json`, and
validates apply-results artifacts such as `patch_result.json` with
`apply_results_result.schema.json`. A non-zero exit means the integration
artifact set is structurally invalid and should not be treated as DONE.

Operator-run real-Codex smoke bundle validation:

```bash
cxor validate-real-codex-smoke-runbook --run-dir .operator-runs/real-codex-smoke/<timestamp>-real-codex-smoke
```

This command is read-only, does not run Codex, and does not run pytest. It
validates `selected_policy.json` with
`real_codex_smoke_selected_policy.schema.json`, validates `result.json` with
`real_codex_smoke_operator_result.schema.json`, validates
`diagnosis_paths.json` with `real_codex_smoke_diagnosis_paths.schema.json`,
validates `validation_result.json` with
`real_codex_smoke_runbook_validation.schema.json` when present, and checks
required text evidence files including `environment.txt`,
`default_skip_stdout.txt`, and `explicit_smoke_stdout.txt`.

List local real-Codex smoke runbook bundles:

```bash
cxor list-real-codex-smoke-runbooks
cxor list-real-codex-smoke-runbooks --root .operator-runs/real-codex-smoke
cxor list-real-codex-smoke-runbooks --json
cxor list-real-codex-smoke-runbooks --latest
cxor list-real-codex-smoke-runbooks --only-invalid
cxor list-real-codex-smoke-runbooks --limit 10
```

The list command is read-only, does not run Codex, and does not run pytest. It
summarizes each bundle's outcome, validation status, model, reasoning, timeout,
`timed_out`, diagnosis category, `result.json`, and `validation_result.json`.
Invalid bundles are listed rather than hidden. Use
`cxor validate-real-codex-smoke-runbook --run-dir <dir>` for one bundle's full
validation details.

Export one validated real-Codex smoke runbook bundle:

```bash
cxor export-real-codex-smoke-runbook --run-dir .operator-runs/real-codex-smoke/<timestamp>-real-codex-smoke
cxor export-real-codex-smoke-runbook --run-dir <bundle> --out /tmp/bundle.zip
cxor export-real-codex-smoke-runbook --run-dir <bundle> --force
```

The export command is read-only for the source bundle, does not run Codex, and
does not run pytest. It writes a zip archive and sidecar manifest with relative
paths, sizes, and sha256 hashes. Invalid bundles are refused unless `--force`
is used.

Worker Capsule inspection:

```bash
cxor inspect-capsule --repo /path/to/target-repo --attempt P0001_attempt1
cxor validate-capsule --repo /path/to/target-repo --attempt P0001_attempt1
```

These commands are read-only for product/runtime files. `inspect-capsule`
prints per-attempt capsule paths and presence bits. `validate-capsule`
validates `worker_capsule.json`, `LIVE_MEMORY.json`, `ALLOWED_PATHS.json`,
`events.jsonl`, and `wrapper_gate_result.json` when present.

Real Codex must write Worker Capsule stage files under `CXOR_WORKER_STAGE_DIR`.
Do not create target-root worker_stage/. If Codex writes a top-level
`worker_stage/`, `diagnose-real-codex` reports
`worker_capsule_path_violation`. This is a Codex path-obedience issue, not an
orchestrator wiring failure. Do not weaken validators.

`diagnose-real-codex` is also read-only and summarizes preserved failure
evidence before writing diagnosis artifacts. `verify-group` and
`verify-global` write matrix-backed gate artifacts before they decide
acceptance.
