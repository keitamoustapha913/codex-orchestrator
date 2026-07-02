Preflight Findings

- Baseline suite passed: 469 passed, 2 skipped.
- Current repository has one untracked architecture document before this implementation.
- `.operator-runs/` is already ignored in `.gitignore`.
- Real-Codex smoke remains opt-in and default smoke skip tests are present.
- No `integration_state.py`, integration ref lifecycle, or `apply-results` command exists yet.

Current command_runner streaming behavior

- `CommandRunner.run` uses `subprocess.Popen`, selectors, line-by-line stdout/stderr capture, timeout killing, and optional `stdout_line_callback`.
- The runner preserves stdout and stderr to artifact files after process completion.
- It does not emit live progress itself.

Current progress.jsonl behavior

- `CodexExecWorker` writes `progress.jsonl` under the attempt run directory.
- It records `process.started` before launch and records compact JSONL-derived signals from Codex stdout.
- The file is durable liveness evidence, not success evidence.

Current live terminal behavior

- Live terminal output is only available through the older `CODEX_PROGRESS_STDERR=1` path.
- That output is not the requested `[cxor:<attempt> +NNNs] codex: <signal>` format.
- Default behavior is quiet.

Current operator runbook capture behavior

- `real_codex_operator_runbook.py` uses `subprocess.run` and captures the explicit smoke stdout/stderr after the process exits.
- The runbook writes stdout/stderr artifacts and prints a final normalized JSON result.
- It cannot currently tee progress lines while the explicit smoke subprocess is running.

Current worktree base behavior

- `create_patchlet_worktree` always uses the target repository HEAD as the detached worktree base.
- Run manifest records the worktree `base_sha`, but not an integration-state base source or integration ref.

Current accepted patchlet merge/apply behavior

- Accepted report-valid patchlet diffs are applied directly to the target repository with `git apply`.
- This can leave accepted product/runtime changes dirty in the target working tree before the next worktree patchlet.

Current target dirty precondition behavior

- Worktree execution enforces a clean target repository except volatile `.codex-orchestrator/` and `.artifacts/` paths.
- Product/runtime dirty files still block worktree creation.
- This guard is correct for external dirtiness, but accepted changes need an integration lifecycle so they do not appear as dirty target files.

Current run manifest behavior

- `append_run_record` assigns sequential run ids.
- Patchlet run records include worker mode, execution root, artifact root, paths, worktree metadata, diff validation, report validation, selected model/reasoning, and progress path.
- There is no accepted-change checkpoint or integration ref record.

Current final verification behavior

- `verify_global` validates patchlet reports, wrapper gates, transaction groups, invariants, and unresolved failures.
- It writes `final_verification.json`, verification matrix, and global gate result.
- It does not reference an integration ref, integration SHA, or final diff.

Integration-ref implementation risks

- Existing tests expect accepted mock/worktree changes may appear in the target working tree; changing this requires careful compatibility or scoped behavior.
- Integration commits must not include `.codex-orchestrator/` or `.artifacts/probes/` unless deliberately intended.
- Worktree cleanup must happen only after checkpointing accepted product/runtime changes.
- Final verification must avoid silently mutating the operator working tree.

Stop conditions

- Stop if the default suite invokes real Codex.
- Stop if baseline/full suite fails.
- Stop if live progress emits raw JSON, prompt text, command output, or file contents.
- Stop if `CXOR_LIVE_CODEX_PROGRESS=0` cannot silence live terminal progress.
- Stop if progress/stdout/stderr/output artifacts are lost.
- Stop if clean-target preconditions are weakened for external dirty files.
- Stop if accepted product/runtime files remain dirty between patchlets after integration-ref behavior is implemented.
- Stop if DONE can be reached without integration-state evidence.
