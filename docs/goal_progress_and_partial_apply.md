# Goal Progress And Partial Apply

cxor writes `.codex-orchestrator/goal_progress.json` as the latest goal progress summary and `.codex-orchestrator/goal_progress.jsonl` as an append-only timeline. Progress is updated after provability, proof obligation creation, probe plan creation, patchlet attempts, independent rerun, goal coverage, global verification, stop handling, and partial apply.

Use `cxor goal-progress --repo <repo>` for human output, `cxor goal-progress --repo <repo> --json` for machine output, and `cxor goal-progress --repo <repo> --watch` for repeated updates. `cxor status --json`, `cxor monitor`, and `cxor auto --live-progress` expose goal progress and proof events.

Use `cxor stop --repo <repo>` to write `control/stop_requested.json`. For
`--after-current-attempt`, the safe point is after the current patchlet attempt
has reached a terminal accepted, failed, or blocked state and before the next
patchlet is selected. At that point the orchestrator writes
`control/stop_result.json`, records the latest accepted checkpoint, and the next
patchlet does not start. A stop request is not treated as DONE or as a product
failure.

Partial apply is explicit. For a stopped non-DONE workflow,
`cxor apply-results --repo <repo> --mode patch --scope accepted --allow-partial`
applies only the accepted integration state. Pending and unaccepted patchlet
work is not applied. Without `--allow-partial`, stopped workflows are refused.
If no accepted checkpoint exists, `stop_result.json` records
`applyable_progress=false` and partial apply is refused even with
`--allow-partial`.

In-progress unaccepted worker changes are never applied by default. `partial_apply_result.json` records the accepted checkpoint, mode, scope, warning that the full master prompt may not be satisfied, and whether the working tree was mutated.

## Multi-Patchlet Progress

`goal_progress.json` includes decomposition counts, per-file patchlet counts, ready/waiting/accepted/blocked patchlets, and same-file multi-patchlet groups. In multi-patchlet workflows, stop and partial apply still use the latest accepted checkpoint only; pending, failed, blocked, or in-progress patchlets are not applied. See `docs/multi_patchlet_transaction_graph.md`.

## RC6 Partial Coverage

PARTIAL progress accepts patchlet progress but blocks DONE. A patchlet can be accepted when its selected current obligations pass; future obligations remain unproven, not failed. DONE is available only after workflow-level coverage proves every required obligation and master-prompt satisfaction passes. Same-file progress also requires a slice-level allowed-change boundary because one allowed file per patchlet is necessary but not sufficient, and future slice changes are rejected.

Scratch artifact quarantine does not change goal progress. Recognized worker
scratch files are preserved under the attempt artifact root and removed from
the candidate product diff before acceptance. Product/runtime files remain
restricted by the one-file rule and same-file slice boundary before any PARTIAL
or DONE status is considered.

Each attempt has a worker scratch directory, and workers are told: Do not write
scratch/check/validation files in the target repository root. The root scratch
sweep quarantines role-based scratch under the run directory, records
`root_scratch_sweep_result.json`, and the diff is recomputed after quarantine.
Random root .txt and .out files are not automatically allowed, and product/runtime
files are still rejected before any checkpoint can be accepted.

Patchlet-prefixed report formatting scratch does not affect goal progress and is
quarantined only after safety checks: untracked, non-executable,
text/JSON-like, patchlet-prefixed, report-role shaped, and
formatting/check/output-role shaped. Not all JSON files are allowed. Not all
pretty files are allowed. Product/runtime files remain rejected, changed peer
product files remain rejected, quarantine preserves content and hash metadata,
and the diff is recomputed after quarantine.

Scratch quarantine does not let file presence masquerade as a product diff. The
guard uses actual changed/untracked paths, not file presence. Unchanged peer
product files are ignored because presence is not a change; changed peer product
files are rejected. Role-shaped validation scratch such as `validate_report.out`
is quarantined only after safety checks.
The allowed file from the patchlet plan is authoritative, not filename
convention, so `control.plan` and `rollout.table` are handled by the same
changed-path rules as any other product/runtime names.
