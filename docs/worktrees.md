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

Real-Codex patchlet attempts default to a 10 minutes / 600 seconds timeout.
`CODEX_TIMEOUT_SECONDS` overrides the global timeout, and
`CODEX_PATCHLET_TIMEOUT_SECONDS` overrides patchlet execution. The generated
prompt and Worker Capsule include the hard timeout and soft deadline, and
Codex is told to stop before timeout by writing `worker_stage/05_final_report.md`
with BLOCKED or FAILED status if needed.

Attempt-local `progress.jsonl` records compact liveness only, not success.
Timeout safe-failure means the worktree attempt was contained and evidence was
preserved; it is not task success and not `DONE`. Patchlet Codex defaults to
`gpt-5.4-mini` with reasoning `medium`, while non-patchlet/orchestrator Codex
profiles default to `gpt-5.5` with reasoning `medium`.

Use `src/codex_orchestrator/prompt_templates/real_codex_patchlet_contract.md`
when you need an operator-facing contract for what the real Codex subprocess
must write.

For the opt-in real Codex smoke, that contract is injected into the generated
subprompt artifact under `.codex-orchestrator/subprompts/`. The contract
includes a minimal valid report example for `CXOR_REPORT_PATH`, a minimal probe
artifact tree for `CXOR_PROBE_ROOT`, and a rule that Codex must not invent
alternate paths or edit files outside the allowed product/runtime file.

After a safe failure, use:

```bash
cxor diagnose-real-codex --repo /path/to/target-repo --attempt P0001_attempt1
```

This reads preserved `stdout.txt`, `stderr.txt`, `output.jsonl`, `command.json`,
`run_manifest.json`, and the generated prompt artifact, then writes:

- generic artifact kinds: `real_codex_failure_diagnosis.json` and `real_codex_failure_diagnosis.md`
- `.codex-orchestrator/diagnostics/real_codex/P0001_attempt1_diagnosis.json`
- `.codex-orchestrator/diagnostics/real_codex/P0001_attempt1_diagnosis.md`

The command is read-only for product/runtime files. If the evidence cannot
support a narrower claim, the diagnosis should stay at
`unknown_codex_nonzero_exit`. Do not weaken validators.
Worker Capsule artifacts stay under the target repo artifact root even in
worktree mode. Do not treat worker memory or stage notes as proof. The
orchestrator writes wrapper gates after validation, and those gates are what
later transaction and global verification consume.

Capsule inspection remains read-only in worktree mode:

```bash
cxor inspect-capsule --repo /path/to/target-repo --attempt P0001_attempt1
cxor validate-capsule --repo /path/to/target-repo --attempt P0001_attempt1
```
