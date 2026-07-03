# P0004 Checkpoint Cleanliness Architecture Implementation Note

## Baseline

- cwd: /home/theyeq-admin-lap/master-workspace-research/codex-orchestrator
- git root: /home/theyeq-admin-lap/master-workspace-research/codex-orchestrator
- HEAD: 0941c7e76648fb79b98da83cf957d137caec8bfb
- git status before implementation: existing uncommitted report-contract, wrapper/TG, docs, and evidence files were present; they were not reverted
- Python: Python 3.10.20
- uv: uv 0.11.23 (x86_64-unknown-linux-gnu)
- codex version: codex-cli 0.142.4
- full suite result: 819 passed, 2 skipped in 61.98s
- cxor version: codex-orchestrator 0.1.0
- codex-orchestrator version: codex-orchestrator 0.1.0

## Evidence basis

- latest evidence report path: p0004_integration_checkpoint_failure_evidence_report.md
- latest real-Codex bundle: .operator-runs/real-codex-smoke/2026-07-03T16-28-35-real-codex-smoke
- latest export archive: .operator-runs/exports/2026-07-03T16-28-35-real-codex-smoke.zip
- observed failure: WorkerExecutionError: integration artifact validation failed
- proven dirty paths: .artifacts/, .codex-orchestrator/, __pycache__/
- proven clean product/runtime files: app.py had no diff
- proven manifest mismatch: P0004 run artifacts existed while latest manifest entry was P0003
- proven diagnosis mismatch: runbook result mixed P0004 paths with P0003 diagnosis and reported network_or_api_error

## Implementation phase order

1. Target hygiene gate and cleanliness taxonomy
2. Worker Python bytecode prevention contract
3. Integration checkpoint cleanliness sidecar and schema summary
4. Attempt lifecycle manifest entries
5. Runbook attempt consistency
6. Diagnosis taxonomy and precedence
7. Full-chain fake-Codex reproductions
8. Docs and release guidance
9. Final verification

## Risks and rollback points

- risk: accidentally weakening checkpoint strictness
- mitigation: keep target_working_tree_clean_after_checkpoint required and const true
- rollback: remove checkpoint schema additions and target hygiene integration

- risk: deleting evidence or unknown dirty files during hygiene
- mitigation: only remove untracked Python cache artifacts outside .codex-orchestrator/ and .artifacts/
- rollback: remove target_hygiene.py and restore checkpoint writer to previous behavior

- risk: breaking existing run_manifest consumers
- mitigation: add lifecycle fields while preserving runs list and stable top-level fields
- rollback: remove upsert lifecycle calls and keep append-only records

- risk: runbook validation changes rejecting old bundles
- mitigation: warn for absent attempt_consistency on old bundles and enforce consistency for new generated bundles
- rollback: remove attempt consistency validation/list/export fields

- risk: broad diagnosis changes hiding true network/API failures
- mitigation: add structured categories before network/API while keeping true external-error tests
- rollback: remove new category branches and restore previous network classifier
