Preflight Findings

- Baseline suite was green before this increment: 428 passed, 2 skipped.
- Python baseline was 3.10.20 under uv.
- Installed Codex was available as codex-cli 0.142.4.
- The existing real-Codex smoke remains opt-in through --run-real-codex.
- No operator-run artifact model or runbook command existed before this change.

Current smoke helper behavior

- The smoke helper builds a temporary target repo and delegates to the existing auto/worktree path.
- The smoke test prints a JSON result that can include run paths, diagnosis paths, timeout evidence, progress path, and selected model profile.
- Default pytest execution of the smoke file skips unless the explicit real-Codex flag is supplied.

Current diagnosis artifact behavior

- Real-Codex safe failures can produce diagnosis JSON and Markdown artifacts.
- Timeout evidence is classified separately when command/run evidence proves an orchestrator subprocess timeout.
- Safe failure is captured as evidence and must not be treated as DONE.

Current docs/runbook coverage

- Existing docs describe the opt-in real-Codex smoke, timeout policy, progress artifacts, and diagnosis categories.
- Existing docs do not yet define a timestamped operator-run evidence bundle for manual real-Codex smoke execution.

Operator-run artifact design

- Use .operator-runs/real-codex-smoke/<timestamp>-real-codex-smoke/ as the artifact root.
- Keep the runbook artifacts in the orchestrator repo rather than in a temporary target repo.
- Always write README.md, environment.txt, git_status.txt, codex_version.txt, selected_policy.json, default skip logs, explicit smoke logs, result.json, and diagnosis_paths.json.
- Preserve stdout and stderr even when smoke output parsing fails.

Dry-run design

- Dry run creates the full operator-run directory and captures preflight/default-skip evidence.
- Dry run must not invoke explicit real Codex.
- Dry run writes explicit smoke stdout/stderr placeholders stating that explicit smoke was not run.

Stop conditions

- Stop if the baseline suite fails.
- Stop if default pytest invokes real Codex.
- Stop if dry-run invokes real Codex.
- Stop if explicit real Codex can run without an explicit flag.
- Stop if stdout/stderr evidence is discarded.
- Stop if safe failure is hidden or treated as DONE.
- Stop if product/runtime files are mutated by the runbook.
