# Codex Orchestrator TDD Implementation Status

## Scope implemented in this MVP

This source tree implements the first practical TDD slice of the Codex Orchestrator autonomous root-cause probe-gated loop.

Local development baseline: `uv` + Python 3.10.

Implemented capabilities:

- standalone installable Python package named `codex-orchestrator`;
- console scripts: `cxor` and `codex-orchestrator`;
- `python -m codex_orchestrator` module entrypoint;
- target repository resolver using `--repo` or current Git-root discovery;
- target-local artifact creation under `.codex-orchestrator/` and `.artifacts/probes/`;
- target-local config, state, run manifest, census directories, patchlet directories, report directories, failure directories, repair-plan directories, and final verification artifacts;
- self-target safety guard for the orchestrator source repository;
- atomic JSON state writes;
- state schema validation;
- deterministic census with command metadata and tool availability recording;
- deterministic placeholder stages for goal normalization, evidence classification, inventory graph generation, invariant extraction, and patchlet compilation;
- root-cause patchlet subprompt generation with the `ROOT-CAUSE PROBE-ONLY INVESTIGATION` gate;
- mock worker adapter for TDD and orchestration tests without real Codex calls;
- real Codex worker adapter scaffold using `codex exec --json`;
- manual and CI-only worker modes as scaffolds;
- target-repo diff guard enforcing one allowed product/runtime file and approved artifact directories;
- patchlet report validator enforcing explicit statuses and root-cause/proof fields;
- patchlet executor with run records, reports, diff capture, and failure record creation;
- transaction-group verifier with durable pass/fail state and failure evidence;
- global verifier that marks `DONE` only when patchlet reports validate, transaction groups pass, invariants are proven, and unresolved failures are absent;
- failure classification, repair planning, and repair application scaffolds;
- repair application artifacts and repair patchlet regeneration without blind retry;
- idempotent replay for `cxor apply-repair`, `cxor regenerate-patchlets`, and `cxor auto --resume --until DONE` when durable repair artifacts already exist;
- terminal `DONE` guards for `cxor apply-repair` and `cxor regenerate-patchlets` so post-completion repair commands are explicit no-op operations;
- advanced repair classifications for inside-known-graph, outside-known-graph, inventory contradiction, repeated repair failure, master-goal change, and excessive impacted scope;
- durable rediscovery records and inventory rebuild routing;
- optional worktree execution with validated merge and unauthorized diff isolation;
- `cxor auto --use-worktree` routing through the validated worktree patchlet execution path;
- `cxor auto` mock-mode autonomous loop that initializes, discovers, compiles, runs, verifies, and reaches `DONE`.

## TDD status

The test suite was written before/alongside implementation and currently passes:

```text
170 passed, 1 skipped
```

Covered tests:

- target repo resolution from explicit repo, nested path, current working directory, non-git override, and self-target guard;
- target artifact initialization and no source-copy leakage into target repos;
- state file validation and atomic save behavior;
- diff guard acceptance/rejection behavior;
- patchlet report validation acceptance/rejection behavior;
- deterministic census outputs and command metadata;
- goal normalization output;
- patchlet compilation output and root-cause prompt gate;
- mock patchlet execution and state updates;
- transaction group verification;
- global verification to `DONE`;
- autonomous mock loop to `DONE`;
- advanced repair classification and rediscovery flows;
- optional worktree execution and validated merge;
- CLI invocation from outside the source tree using module entrypoint.

## Current limitations

This is not the full final orchestrator. The following are intentionally still scaffolds or deterministic MVP placeholders:

- Codex-driven semantic classification is not yet implemented beyond the adapter scaffold.
- Evidence classification, inventory graph construction, invariant extraction, and patchlet compilation are deterministic placeholder implementations.
- Repair planning records structured intent but does not yet synthesize enriched repair patchlets automatically.
- CI/documentation contract coverage still needs expansion around all newly added commands and worker modes.
- Root-cause validation is strict for report fields but does not yet perform secondary model/human semantic verification.

## Current command surface

Notable verified commands now include:

```bash
cxor verify-group --repo /path/to/target-repo TG001
cxor verify-all-groups --repo /path/to/target-repo
cxor verify-global --repo /path/to/target-repo
cxor rediscover --repo /path/to/target-repo --scope impacted
cxor rebuild-inventory --repo /path/to/target-repo --scope impacted
cxor run-next --repo /path/to/target-repo --worker-mode mock --use-worktree
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE --worker-mode mock --use-worktree
```

`No blind retry` remains a required contract.

## Verified commands

The following commands were verified after editable install:

```bash
cxor --version
codex-orchestrator --version
python -m codex_orchestrator --version
pytest -q
```
