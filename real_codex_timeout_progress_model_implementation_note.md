Preflight Findings

- Baseline suite passed: 370 passed, 2 skipped.
- Repository status was clean before edits.
- Python is 3.10.20 under `uv run --no-sync`.
- Codex CLI is available as `codex-cli 0.142.4`.

Current timeout behavior

- `CodexExecWorker` reads `CODEX_TIMEOUT_SECONDS` and falls back to 120 seconds.
- Timeout failures are converted to exit code 124 by `CommandRunner`.
- `stderr.txt` includes `command timed out after <timeout> seconds`.
- `command.json` and `output.jsonl` include `timed_out` and `timeout_seconds`.

Current command runner behavior

- `CommandRunner.run` uses `subprocess.run`.
- stdout and stderr are only available after the subprocess exits or times out.
- There is no durable progress artifact written while the subprocess is alive.

Current Codex model selection behavior

- Patchlet real-Codex execution defaults to `CODEX_MODEL` or `gpt-5.4-mini`.
- Reasoning defaults to `CODEX_REASONING` or `medium`.
- There is no shared resolver for non-patchlet orchestration Codex profiles.
- There are no current non-patchlet real Codex calls to add.

Current patchlet prompt budget wording

- Generated `codex_task_prompt.md` tells Codex to read Worker Capsule files and write stage files.
- `TASK_CONTRACT.md` and `WRITE_THESE_FILES.md` do not mention a hard timeout or soft deadline.
- `real_codex_patchlet_contract.md` does not mention the 10-minute wall-clock budget.

Current progress observability

- `stdout.txt`, `stderr.txt`, and `output.jsonl` are preserved after exit.
- Worker Capsule events record lifecycle gates around worker execution.
- No `progress.jsonl` exists for streamed Codex JSONL liveness.

Current smoke behavior

- Real Codex smoke is opt-in.
- Default pytest does not run real Codex.
- Smoke safe-failure preserves command and worker artifacts.

Correction plan

- Add behavior tests for 600-second default timeout, env override precedence, timeout recording, and safe timeout failure.
- Add a small model profile resolver and wire patchlet execution through it.
- Add streamed command execution progress support while preserving stdout, stderr, output artifacts, and timeout handling.
- Add Worker Capsule and real-Codex prompt budget wording with `CXOR_TIMEOUT_SECONDS` and `CXOR_SOFT_DEADLINE_SECONDS`.
- Add docs tests and docs updates for timeout, progress, model defaults, and safe-failure semantics.

Stop conditions

- Stop if baseline/full suite regresses.
- Stop if Python 3.10 compatibility regresses.
- Stop if default tests invoke real Codex.
- Stop if timeout becomes unbounded or safe-failure evidence is lost.
- Stop if progress is noisy, blocking, or drops stdout/stderr/output artifacts.
- Stop if validators or Worker Capsule gates are weakened.
