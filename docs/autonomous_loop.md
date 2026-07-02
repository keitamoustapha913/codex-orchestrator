# Autonomous Loop

Local baseline: `uv + Python 3.10`.

Primary autonomous command:

```bash
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode mock
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode mock --use-worktree
```

The autonomous loop is probe-gated and evidence-bound:

`normalize -> census -> classify-evidence -> build-inventory -> extract-invariants -> compile-patchlets -> run patchlets -> transaction groups -> verify-global -> DONE`

If failures occur, the loop routes through:

`failure -> classification -> repair plan -> apply repair -> regenerate patchlets -> verify`

For advanced cases it can also route through:

`PARTIAL_REDISCOVERY_REQUIRED`
`FULL_REDISCOVERY_REQUIRED`
`INVENTORY_REBUILD_REQUIRED`

No blind retry is allowed.

`ci_only` mode is read-only and intended for CI-safe resume and verification flows:

```bash
cxor auto --repo /path/to/target-repo --resume --until DONE --worker-mode ci_only
```

`--use-worktree` is optional, not default. When enabled for patchlet-executing worker modes, the target repo must be clean apart from volatile workflow artifacts before worktree execution starts.

Opt-in real Codex smoke command:

```bash
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py --run-real-codex -s
```

This command is not part of the default test suite. It runs the autonomous loop with `--worker-mode real_codex --use-worktree`. Do not weaken validators to make real Codex pass. Inspect `.codex-orchestrator/runs/`, `.codex-orchestrator/failures/`, and `.artifacts/probes/` to review contained success or failure evidence.

Fake-success parity now proves that this exact `worker_mode=real_codex` +
`auto --use-worktree` path can reach `DONE` when the subprocess produces a
valid report and durable probe artifacts. Real Codex success to DONE is still
not guaranteed, because real Codex must still produce output that satisfies the
existing validators.

Safe failures are expected to leave a `run_manifest.json` entry with status `WORKER_FAILED` and preserved `stdout.txt`, `stderr.txt`, `command.json`, and `output.jsonl` paths for the failed patchlet attempt. Blind retry is not allowed.

Real-Codex patchlets are bounded by a default 10 minutes / 600 seconds timeout.
`CODEX_TIMEOUT_SECONDS` overrides the global timeout, and
`CODEX_PATCHLET_TIMEOUT_SECONDS` overrides patchlet execution specifically.
Generated Worker Capsule files and subprompts include the hard timeout, the
soft deadline, and instructions to write `worker_stage/05_final_report.md`
with BLOCKED or FAILED status before timeout if the task cannot complete.

Invalid timeout env values fail structurally before Codex launches.
`CODEX_TIMEOUT_SECONDS`, `CODEX_PATCHLET_TIMEOUT_SECONDS`, and
`CODEX_PROGRESS_INTERVAL_SECONDS` must be positive integer seconds. Invalid
messages include the env var name, bad value, and `expected positive integer
seconds`.

`progress.jsonl` is written under each real-Codex attempt run directory as
small liveness evidence. Progress is not success evidence. Timeout
safe-failure is not task success and not `DONE`; it only proves containment and
artifact preservation.

Diagnosis has a dedicated `orchestrator_subprocess_timeout` category for
`command.json` or run-manifest evidence where `timed_out=true` and
`exit_code=124`. This category takes precedence over generic timeout text in
stderr/output, is not task success, and links `progress.jsonl` when present.

Explicit real-Codex smoke remains an operator-run check and is not part of the
default test suite.

Patchlet Codex defaults to `gpt-5.4-mini` with reasoning `medium`.
Non-patchlet/orchestrator Codex profiles default to `gpt-5.5` with reasoning
`medium`.

Operator prompt contract:

- `src/codex_orchestrator/prompt_templates/real_codex_patchlet_contract.md`

For the opt-in real Codex smoke, the orchestrator injects this contract into
the generated subprompt artifact under `.codex-orchestrator/subprompts/`. That
artifact is the exact prompt context to inspect after a safe failure.

The contract contains a minimal valid report example for `CXOR_REPORT_PATH`, a
minimal durable probe example for `CXOR_PROBE_ROOT`, and explicit instructions
that real success is not guaranteed unless Codex obeys the contract without the
validators being weakened.

If the opt-in smoke fails safely, run:

```bash
cxor diagnose-real-codex --repo /path/to/target-repo --attempt P0001_attempt1
```

This produces:

- generic artifact kinds: `real_codex_failure_diagnosis.json` and `real_codex_failure_diagnosis.md`
- `.codex-orchestrator/diagnostics/real_codex/P0001_attempt1_diagnosis.json`
- `.codex-orchestrator/diagnostics/real_codex/P0001_attempt1_diagnosis.md`

The diagnosis is evidence-bound. It reads `stdout.txt`, `stderr.txt`,
`output.jsonl`, `command.json`, `run_manifest.json`, and the generated prompt
artifact. It does not run Codex and does not weaken validators. If the
artifacts are insufficient, expect `unknown_codex_nonzero_exit`.

The same attempt-local evidence layer is visible through:

```bash
cxor inspect-capsule --repo /path/to/target-repo --attempt P0001_attempt1
cxor validate-capsule --repo /path/to/target-repo --attempt P0001_attempt1
```

Worker Capsule is now part of each patchlet attempt. It is per-attempt memory,
not global memory. The capsule lives under
`.codex-orchestrator/runs/<attempt>/` and includes worker memory, worker stage
templates, lifecycle events, gates, and diagnostics.

Memory is context, not proof. Codex can write memory and stage notes, but the
orchestrator writes gate results. `gates/wrapper_gate_result.json` is the
machine verdict for the attempt. A Codex `FINAL_STATUS` claim is evidence only;
it is not sufficient proof by itself.

Global `DONE` is now backed by transaction and global matrices:

- transaction groups write `patchlet_output_matrix.json`
- global verification writes `verification_matrix.json`
- global verification writes `global_gate_result.json`
