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
