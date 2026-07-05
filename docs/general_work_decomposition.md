# General Work Decomposition

The orchestrator decomposition architecture is not one file -> one patchlet.
The rule is one patchlet -> exactly one allowed product/runtime file.
Multiple patchlets may target the same product/runtime file when the work is sequential, proof-heavy, risky, or too large for one bounded worker task.

Patchlets are small bounded work units derived from work slices.
Work slices are not merely files. A work slice may be a subtask within a file, and a single file may contain many work slices.
The planner derives slices from the frozen master prompt, goal interpretation, proof obligations, the inventory graph, impact/dependency analysis, risk, dependency boundaries, and task size.

The generated decomposition artifacts live under `.codex-orchestrator/decomposition/`:

- `impact_dependency_analysis.json`
- `work_decomposition_plan.json`
- `work_slices.json`
- `patchlet_plan.json`
- `dependency_graph.json`
- `transaction_group_plan.json`

Each patchlet plan row records one `allowed_product_runtime_file` and an `allowed_product_runtime_files` list with exactly one item.
Context files may include dependencies for reading, but the allowed edit file remains exactly one product/runtime file.
Manual artifact tampering is invalid because `patchlet_index.json`, transaction groups, prompts, worker memory, dependency metadata, and proof coverage must be generated from the same decomposition plan.

Patchlet prompts include the work slice ID, allowed edit path, forbidden product/runtime edit paths, proof obligations, goal items, dependency patchlets, local probe requirements, and independent proof expectations.
The default patchlet budget is `CODEX_PATCHLET_TIMEOUT_SECONDS`, or 600 seconds when the environment variable is unset.
Prompts are intentionally narrow and self-contained so they avoid memory compacting and do not ask a worker to solve unrelated slices.

Operators can inspect the plan with:

```bash
cxor decomposition --repo <repo>
cxor decomposition --repo <repo> --json
cxor decomposition --repo <repo> --patchlets
cxor decomposition --repo <repo> --dependencies
```

`cxor status --json`, `cxor monitor`, live progress, and `goal_progress.json` expose decomposition counts, per-file patchlet counts, same-file multi-patchlet groups, ready/waiting/accepted/blocked patchlets, and the decomposition plan path.

Target complexity alone previously did not create multiple patchlets because patchlet compilation iterated the single global invariant `I001`.
The corrected path compiles patchlets from `patchlet_plan.json`, which is generated from work slices rather than invariant count.

## RC6 Slice Boundary Contract

one allowed file per patchlet is necessary but not sufficient for same-file multi-patchlet workflows. Same-file patchlets require a slice-level allowed-change boundary, and future slice changes are rejected even when they are inside the same allowed product/runtime file. The boundary is propagated through `work_slices.json`, `patchlet_plan.json`, `patchlet_index.json`, worker prompts, worker memory, and the diff guard. patchlet-scoped proof runs only selected current obligations; future obligations remain unproven, not failed. PARTIAL progress accepts patchlet progress but blocks DONE. Report ingestion accepts pass: / fail: / blocked: descriptive prefixes. Artifact directories are allowed only under approved roots.

Worker reports do not expand a patchlet's ownership. If real Codex emits
shorthand `semantic_goal_results`, those entries are raw worker semantic claims
only. They must link to the current slice boundary and selected proof
obligation, they must not claim future slices, and they become canonical
passed/failed semantic results only after orchestrator-owned independent proof.

Real Codex may create root-level scratch artifacts while validating reports or
probes. Recognized worker scratch artifacts are quarantined under the attempt
artifact root with preserved content, sha256, size, and reason metadata. The
orchestrator then rechecks the product diff. Quarantine does not allow a second
product/runtime file and does not weaken same-file slice boundaries.

Each patchlet attempt has a worker scratch directory at
`.codex-orchestrator/runs/<attempt>/worker_scratch/`. The worker contract says:
Do not write scratch/check/validation files in the target repository root. The
orchestrator still runs a root scratch sweep after worker exit. Role-based
quarantine accepts report/probe validation-shaped leftovers, preserves content
hash metadata, and writes `root_scratch_sweep_result.json`. Random root .txt and
.out files are not automatically allowed, product/runtime files are still
rejected, and the diff is recomputed after quarantine.

Execution-root peer files are classified by actual changed/untracked paths, not
file presence. Unchanged peer product files are ignored because presence is not a
change. Changed peer product files are rejected unless they are the current
patchlet's allowed product/runtime file. Role-shaped validation scratch such as
`validate_report.out` may be quarantined after safety checks.
The allowed file from the patchlet plan is authoritative, not filename
convention, so the same rules apply to non-scenario names such as
`control.plan`, `rollout.table`, and `verify_result.log`.

Semantic shorthand matching is boundary-type aware. Route-style claims can
match route/path and expected target evidence, key-value claims can match key
and expected value, section claims can match section/key/value, and exact-line
claims can match the planned new line. Worker claim is still not proof, and
future-slice claims remain rejected until their own patchlets run. Downstream patchlets do not run after failed dependencies; scheduler readiness requires accepted dependencies, not only an earlier attempt directory.

Boundary evidence matching is role-aware. Short tokens such as `on`, `off`,
`no`, or `yes` do not match as substrings inside unrelated words like
`boundary`, `control`, or `now`. Future-slice rejection requires a role-aware
future boundary evidence combination, such as an exact line `event_logging=on`
or matching future key and value. Same-file mention alone is not a future
claim. Worker text is not proof; independent proof remains required.
