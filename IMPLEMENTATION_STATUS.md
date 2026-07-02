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
- global verifier that marks `DONE` only when all patchlet reports validate as `COMPLETE` or `VERIFIED_NO_CHANGE_NEEDED`;
- failure classification, repair planning, and repair application scaffolds;
- repair application artifacts and repair patchlet regeneration without blind retry;
- idempotent replay for `cxor apply-repair`, `cxor regenerate-patchlets`, and `cxor auto --resume --until DONE` when durable repair artifacts already exist;
- terminal `DONE` guards for `cxor apply-repair` and `cxor regenerate-patchlets` so post-completion repair commands are explicit no-op operations;
- `cxor auto` mock-mode autonomous loop that initializes, discovers, compiles, runs, verifies, and reaches `DONE`.

## TDD status

The test suite was written before/alongside implementation and currently passes:

```text
25 passed
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
- global verification to `DONE`;
- autonomous mock loop to `DONE`;
- CLI invocation from outside the source tree using module entrypoint.

## Current limitations

This is not the full final orchestrator. The following are intentionally still scaffolds or deterministic MVP placeholders:

- Codex-driven semantic classification is not yet implemented beyond the adapter scaffold.
- Evidence classification, inventory graph construction, invariant extraction, and patchlet compilation are deterministic placeholder implementations.
- Repair planning records structured intent but does not yet synthesize enriched repair patchlets automatically.
- Transaction-group verifier is represented through metadata but not fully implemented.
- Worktree isolation and validated merge are not yet implemented.
- Root-cause validation is strict for report fields but does not yet perform secondary model/human semantic verification.

## Verified commands

The following commands were verified after editable install:

```bash
cxor --version
codex-orchestrator --version
python -m codex_orchestrator --version
pytest -q
```
