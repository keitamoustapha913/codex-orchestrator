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

Worker Capsule inspection:

```bash
cxor inspect-capsule --repo /path/to/target-repo --attempt P0001_attempt1
cxor validate-capsule --repo /path/to/target-repo --attempt P0001_attempt1
```

These commands are read-only for product/runtime files. `inspect-capsule`
prints per-attempt capsule paths and presence bits. `validate-capsule`
validates `worker_capsule.json`, `LIVE_MEMORY.json`, `ALLOWED_PATHS.json`,
`events.jsonl`, and `wrapper_gate_result.json` when present.

`diagnose-real-codex` is also read-only and summarizes preserved failure
evidence before writing diagnosis artifacts. `verify-group` and
`verify-global` write matrix-backed gate artifacts before they decide
acceptance.
