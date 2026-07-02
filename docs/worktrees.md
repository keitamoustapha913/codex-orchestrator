# Worktrees

Worktree mode is optional. It is not the default.

Command:

```bash
cxor run-next --repo /path/to/target-repo --worker-mode mock --use-worktree
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode mock --use-worktree
```

Safety contract:

- worktree execution requires a clean target repo apart from volatile workflow artifacts;
- reports, run records, and durable probe artifacts are written to the target repo artifact root;
- target product/runtime files are not mutated before diff validation and report validation pass;
- validated merge applies only the allowed product/runtime diff;
- unauthorized worktree diffs are isolated as failure evidence;
- no source is copied into the target repo;
- no blind retry is allowed.

This is a validated merge flow, not a default execution mode.

Real Codex recommendation:

```bash
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py --run-real-codex -s
```

The real_codex smoke uses `cxor auto --use-worktree` so that Codex edits happen in the worktree first. The default suite does not run real Codex. Do not weaken validators to make the smoke pass. After the run, inspect `.codex-orchestrator/runs/`, `.codex-orchestrator/failures/`, and `.artifacts/probes/`.

Fake-success parity proves the exact `worker_mode=real_codex` worktree path can
reach `DONE` when the subprocess writes a valid report and durable probe
artifacts into the target artifact root. Real Codex success to DONE is still
not guaranteed; it depends on real Codex output quality and prompt-following.

If the worker fails before diff or report validation, inspect `run_manifest.json` for a `WORKER_FAILED` entry and then inspect the preserved `stdout.txt`, `stderr.txt`, `command.json`, and `output.jsonl` files for that attempt. Blind retry is not allowed.

Use `src/codex_orchestrator/prompt_templates/real_codex_patchlet_contract.md`
when you need an operator-facing contract for what the real Codex subprocess
must write.
