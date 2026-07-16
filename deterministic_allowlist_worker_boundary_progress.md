# Deterministic Allowlist Worker Boundary — Implementation Progress

This artifact records the required TDD implementation sequence. A step is marked complete only after its prescribed evidence has been captured.

| Step | Status | Evidence |
|---|---|---|
| 1. Capture baseline | COMPLETE | 2026-07-16: `git diff --check` passed; focused baseline: 160 passed in 9.55s; targeted Ruff passed. Pre-existing dirty worktree recorded and preserved. |
| 2. Primary RED allowlist-boundary tests | RED COMPLETE | 18 tests added; mandated RED run: 18 failed for expected old classifications/rejections. No production file had been patched. |
| 3. RED allowed-path failure tests | RED COMPLETE | 9 tests added. RED run exposed missing-change acceptance, invalid-object old classes, deletion reconstruction bug, slice classification gap, and include-list allowlist bypass; reconstruction equality already passed. |
| 4. RED containment tests | RED COMPLETE | 8 tests added; all 8 failed because traversal/cross-repository paths are accepted or escapes use generic rejection. |
| 5. RED schema tests | RED COMPLETE | Required schema tests added; 6 expected failures captured. |
| 6. Classification ledger schema | COMPLETE | Four-class enum and per-class invariants implemented; focused schema run: 4 passed. |
| 7. Worker hygiene schema | COMPLETE | New statuses, fields, counts, and promotion-blocking iff violation invariant implemented; focused run: 5 passed. |
| 8. Raw sandbox classification | COMPLETE | Ordinary non-allowlisted paths unified as debris; containment and allowlisted object failures separated; diagnostics truncate non-blockingly. Boundary run included in 35-pass green. |
| 9. Patch validation decoupling | COMPLETE | Canonical extraction filters allowlist/classification, deletion reconstruction fixed, slice violations feed ledger, preparation ignores debris. Boundary suites: 35 passed. |
| 10. Remove debris-reference rejection | COMPLETE | Schema, validator, and pre-proof gate removed; proof always runs in clean reconstruction. Focused run: 41 passed. |
| 11. Remove checkout-local evidence support | COMPLETE | Legacy classifier/migration/counts removed; staged evidence uses debris + diagnostic capture fields. |
| 12. Replace checkout-local evidence tests | COMPLETE | Eight required tests added; evidence + schema focused run: 30 passed. |
| 13. Remove legacy report aliases | COMPLETE | Alias RED: 5 expected failures; adapter/table/mappings removed; contract artifacts regenerated; full focused run: 52 passed. |
| 14. Remove semantic shorthand aliases | COMPLETE | Alias RED captured; normalizer and report schema require `goal_item_id`; full focused run: 40 passed. |
| 15. Remove work-slice fallback | COMPLETE | Three expected RED failures captured; capsule and run-stage validation now require `work_slice_id` before launch; focused run: 21 passed. |
| 16. Remove direct-checkout quarantine | COMPLETE | Four RED tests added (3 expected failures); obsolete compatibility suites deleted; direct sweep/cleanup removed; write-capable execution always uses a disposable worktree. Full focused run: 64 passed. |
| 17. Update events and status | COMPLETE | Seven required status/event cases added; RED run had 5 expected counter/legacy failures; new counters and four event types implemented. Focused run: 20 passed. |
| 18. Failure-routing tests | COMPLETE | Twelve exact routing tests added; RED exposed missing slice-change enforcement and generic containment taxonomy; both fixed. Routing + regression green: 37 passed. |
| 19. `.codex` live regression | COMPLETE | Five exact P0002 live-regression tests added; all passed against the prior boundary implementation. Combined regression run: 26 passed. |
| 20. Documentation | COMPLETE | Six explicit contract tests plus always-disposable assertions added; RED run had 8 expected failures. Eight documents patched in required order; documentation run: 66 passed. |
| 21. Compatibility-removal audit | COMPLETE | Seven audit tests pass; production scratch-repair compatibility removed; exact forbidden-token scan returns no matches in `src` or `tests`. |
| Focused green validation | COMPLETE | Prescribed groups passed in order: 31, 8, 17, 17, 52, 40, and 49 tests (214 total executions). |
| Full deterministic validation | COMPLETE | Final suite including the supervised proof: 2100 passed, 2 skipped in 353.25s. Changed-file Ruff and `git diff --check` passed before the run; final contract, compatibility, lint, and hygiene checks are recorded below. |
| Five-patchlet behavioral proof | COMPLETE | Supervised JavaScript integration proof: 5 initial, 5 accepted, 0 repairs, 5 canonical patches, 5 clean reconstructions, 5 independent proofs, coverage 5/5, 5 canonical semantic accepts, 5 durable promotions, `SATISFIED`. P0002 and P0004 each emitted `.codex/`, `.agents/`, a hidden file, nested cache, and temporary output; all were non-blocking debris and absent from canonical, reconstructed, and promoted trees. |

## Baseline worktree note

The repository was already dirty before implementation. Several plan-target files were modified or untracked. Those changes are treated as user-owned and will not be reverted.

## Final validation evidence

- Full test suite: `2100 passed, 2 skipped in 353.25s (0:05:53)`.
- Focused supervised proof: `1 passed in 1.84s`.
- Behavioral proof record: `deterministic_allowlist_worker_boundary_behavioral_proof.json`.
- Changed-file Ruff plus the new proof test: passed.
- Report contract drift check: `[]`.
- Exact forbidden compatibility-token scan across `src` and `tests`: no matches.
- `git diff --check`: passed.
- Final `git status --short --untracked-files=all`: captured; the pre-existing dirty worktree remains intentionally unreverted.
