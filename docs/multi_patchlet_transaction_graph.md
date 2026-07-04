# Multi-Patchlet Transaction Graph

Patchlet dependencies are explicit in `.codex-orchestrator/decomposition/dependency_graph.json`.
The graph records patchlet nodes, `must_complete_before` edges, cycle status, and topological order.

Same-file multi-patchlet groups are ordered by default.
If `P0001` and `P0002` both target `app.py`, `P0002` waits for `P0001` unless a future planner explicitly proves independence.
For this increment, same-file patchlets are not parallel.

Patchlet readiness requires all dependency patchlets to be accepted.
If a dependency fails or blocks, downstream patchlets become blocked and are not run.
Stop requests prevent starting the next ready patchlet.

Transaction groups are derived from dependency layers and proof-obligation coverage.
`.codex-orchestrator/decomposition/transaction_group_plan.json` records group patchlets, dependency patchlets, goal item IDs, proof obligation IDs, and a layer summary.
The executable `.codex-orchestrator/patchlets/transaction_groups.json` preserves legacy verifier fields while carrying decomposition proof metadata.

Stop and partial apply continue to use accepted checkpoints only.
In a multi-patchlet workflow, `apply-results --scope accepted --allow-partial` applies the latest accepted checkpoint and does not apply pending, blocked, failed, or in-progress patchlet work.
The partial apply result warns that the full master prompt may not be satisfied.

Manual transaction group fabrication is invalid.
Groups must derive from the patchlet dependency graph and proof-obligation coverage so verification, goal progress, status, monitor output, and stop/partial apply all describe the same accepted state.

## RC6 Same-File Boundaries

one allowed file per patchlet is necessary but not sufficient for same-file multi-patchlet workflows. Same-file patchlets require a slice-level allowed-change boundary, and future slice changes are rejected even when they are inside the same allowed product/runtime file. patchlet-scoped proof runs only selected current obligations; future obligations remain unproven, not failed. PARTIAL progress accepts patchlet progress but blocks DONE. Report ingestion accepts pass: / fail: / blocked: descriptive prefixes. Artifact directories are allowed only under approved roots.
