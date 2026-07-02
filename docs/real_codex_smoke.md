# Real Codex Smoke

The real Codex smoke is opt-in only. The default suite does not run real Codex.

Run it with:

```bash
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py --run-real-codex -s
```

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

If the preserved artifacts do not justify a narrower claim, the diagnosis
should stay at `unknown_codex_nonzero_exit`.

Real success is not guaranteed. It still depends on real Codex producing a
valid report and durable probe artifacts that satisfy the existing validators.
