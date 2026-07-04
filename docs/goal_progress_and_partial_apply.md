# Goal Progress And Partial Apply

cxor writes `.codex-orchestrator/goal_progress.json` as the latest goal progress summary and `.codex-orchestrator/goal_progress.jsonl` as an append-only timeline. Progress is updated after provability, proof obligation creation, probe plan creation, patchlet attempts, independent rerun, goal coverage, global verification, stop handling, and partial apply.

Use `cxor goal-progress --repo <repo>` for human output, `cxor goal-progress --repo <repo> --json` for machine output, and `cxor goal-progress --repo <repo> --watch` for repeated updates. `cxor status --json`, `cxor monitor`, and `cxor auto --live-progress` expose goal progress and proof events.

Use `cxor stop --repo <repo>` to write `control/stop_requested.json`. The orchestrator stops at a safe point and writes `control/stop_result.json` with the latest accepted checkpoint, applyable progress, and preserved unaccepted attempts.

Partial apply is explicit. For a stopped non-DONE workflow, `cxor apply-results --repo <repo> --mode patch --scope accepted --allow-partial` applies only the accepted integration state. Without `--allow-partial`, stopped workflows are refused. If no accepted checkpoint exists, partial apply is refused even with `--allow-partial`.

In-progress unaccepted worker changes are never applied by default. `partial_apply_result.json` records the accepted checkpoint, mode, scope, warning that the full master prompt may not be satisfied, and whether the working tree was mutated.
