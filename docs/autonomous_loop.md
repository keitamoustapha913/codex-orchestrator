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

Operator prompt contract:

- `src/codex_orchestrator/prompt_templates/real_codex_patchlet_contract.md`
