# Codex Orchestrator

Standalone installable `cxor` CLI for probe-gated root-cause Codex orchestration.

This repository contains the orchestrator source. Target repositories receive only durable workflow artifacts under `.codex-orchestrator/` and `.artifacts/probes/`.

## MVP implemented here

- installable package skeleton with `cxor` and `codex-orchestrator` entrypoints
- target repository resolver using `--repo` or current Git root discovery
- target artifact initialization
- atomic JSON writes and state validation
- deterministic census stage
- deterministic placeholder normalization/evidence/inventory/invariant/patchlet stages
- mock worker patchlet execution
- target-repo diff guard
- patchlet report validation
- global verification and autonomous mock loop to `DONE`

## Basic use

```bash
uv venv --python 3.10
. .venv/bin/activate
uv pip install -e ".[dev]"
cd /path/to/target-repo
cxor auto --master ./master_prompt.md --until DONE --worker-mode mock
```

## Repair loop

Local development baseline: `uv + Python 3.10`.

Repair flow:
`failure -> classification -> repair plan -> apply repair -> regenerate patchlets -> verify`

No blind retry is allowed. Unauthorized diffs must be converted into a classified failure, a repair plan, a repair application, and repair patchlet regeneration before verification continues.

The repair replay commands are idempotent when the durable artifacts already exist and remain consistent:
`cxor apply-repair`, `cxor regenerate-patchlets`, and `cxor auto --resume --until DONE` can be rerun safely without creating duplicate repair artifacts.

After the workflow is `DONE`, `cxor apply-repair` and `cxor regenerate-patchlets` are terminal no-op commands. They report the no-op explicitly and do not rewrite state, patchlets, final verification, or product files.

```bash
cxor apply-repair --repo /path/to/target-repo
cxor regenerate-patchlets --repo /path/to/target-repo --from-repair-plan latest
cxor auto --repo /path/to/target-repo --resume --until DONE --worker-mode mock
```

## Durable probes and verification

Patchlet reports must carry `probe_artifact_refs` that point at durable probe artifacts under `.artifacts/probes/`.

The root-cause gate is explicit:
`ROOT-CAUSE PROBE-ONLY INVESTIGATION`

The global verifier does not allow `DONE` unless patchlet reports validate, transaction groups pass, invariants are proven, and unresolved failures are absent.

## Advanced repair and rediscovery

Advanced repair classifications currently include:

- `INSIDE_KNOWN_GRAPH`
- `OUTSIDE_KNOWN_GRAPH`
- `INVENTORY_CONTRADICTION`
- `REPEATED_REPAIR_FAILURE`
- `MASTER_GOAL_CHANGED`
- `EXCESSIVE_IMPACTED_SCOPE`

Rediscovery and rebuild commands:

```bash
cxor rediscover --repo /path/to/target-repo --scope impacted
cxor rediscover --repo /path/to/target-repo --scope full
cxor rebuild-inventory --repo /path/to/target-repo --scope impacted
```

## Worktree mode

Worktree mode is optional. It is not the default execution path.

Validated merge flow:

```bash
cxor run-next --repo /path/to/target-repo --worker-mode mock --use-worktree
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode mock --use-worktree
```

The target repo must be clean apart from volatile workflow artifacts before worktree execution starts.
Worktree execution writes reports, runs, and durable probe artifacts to the target repo artifact root, validates the worktree diff, validates the report, and only then applies a validated merge back to the target product/runtime file.
Unauthorized worktree diffs are isolated as failure evidence and do not mutate target product/runtime files.

No source is copied into the target repo beyond durable workflow artifacts and validated target-file edits.

## Opt-in real Codex smoke

Real Codex smoke is opt-in only. The default suite does not run real Codex and the smoke is not part of the default test suite.

Run it explicitly:

```bash
export UV_CACHE_DIR=/tmp/uv-cache
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py --run-real-codex -s
```

The smoke drives `cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode real_codex --use-worktree`.

Fake-success parity now proves the exact `worker_mode=real_codex` +
`auto --use-worktree` orchestrator wiring. A fake Codex binary can reach
`DONE` only by producing a valid report and durable probe artifacts that pass
the existing validators.

Real Codex success to DONE is not guaranteed. It still depends on actual Codex
output quality, including a valid report, valid `probe_artifact_refs`, and
durable probe artifacts. Do not weaken validators to make real Codex pass.

Operator rules:

- do not weaken validators to make real Codex pass;
- real Codex runs inside an isolated worktree and only validated diffs may merge back to the target repo;
- real Codex failure is acceptable only when it stays contained and preserves evidence;
- inspect `run_manifest.json` for the failed patchlet attempt entry;
- inspect `.codex-orchestrator/runs/`, `.codex-orchestrator/failures/`, and `.artifacts/probes/` after each smoke run;
- on safe failure, expect a `WORKER_FAILED` run-manifest entry plus preserved `stdout.txt`, `stderr.txt`, `command.json`, and `output.jsonl`;
- blind retry is not allowed.

Operator prompt contract:

- `src/codex_orchestrator/prompt_templates/real_codex_patchlet_contract.md`

## CI-safe commands

```bash
export UV_CACHE_DIR=/tmp/uv-cache
uv run --no-sync pytest -q
uv run --no-sync cxor doctor --repo /path/to/target-repo
uv run --no-sync cxor validate-state --repo /path/to/target-repo
uv run --no-sync cxor verify-global --repo /path/to/target-repo
uv run --no-sync cxor auto --repo /path/to/target-repo --resume --until DONE --worker-mode ci_only
```
