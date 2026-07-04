# Semantic Goal Satisfaction

Codex Orchestrator has a semantic goal satisfaction plane for workflow goals that can be compiled into machine-checkable criteria. It is separate from report schema validation: a structurally valid patchlet report is not enough to prove the user's requested behavior.

## Semantic Goal Spec

New workflows write `.codex-orchestrator/semantic_goal_spec.json`.

For the built-in Python main return family, prompts such as:

```text
Make app return me and prove it.
Make app.py return "ok" and prove it.
Make app main return "hello world" and prove it.
```

compile into structured criteria like:

```json
{
  "criterion_id": "SGC001",
  "kind": "python_module_function_returns",
  "target_file": "app.py",
  "module_name": "app",
  "function_name": "main",
  "expected_value": "me",
  "comparison": "equals",
  "required": true
}
```

Unsupported natural-language prompts are recorded with `semantic_mode: "unsupported"` and `semantic_status: "UNSUPPORTED"`. Unsupported does not mean passed.

## Independent Runner

The orchestrator runs its own semantic goal check and writes:

```text
.codex-orchestrator/semantic_goal_checks/semantic_goal_check_result.json
.codex-orchestrator/semantic_goal_checks/SGC001.stdout.txt
.codex-orchestrator/semantic_goal_checks/SGC001.stderr.txt
```

For `python_module_function_returns`, the check runs under no-bytecode settings and verifies the accepted candidate state with an orchestrator-built Python probe equivalent to:

```bash
PYTHONDONTWRITEBYTECODE=1 python -B -c 'import app; assert app.main() == "me"'
```

Worker-authored probes and report status are useful evidence, but they are not sufficient for structured semantic DONE.

## Goal Satisfaction Gate

Patchlet attempts write:

```text
.codex-orchestrator/runs/<ATTEMPT_ID>/gates/goal_satisfaction_gate_result.json
```

For structured goals, every required semantic criterion must pass before patchlet acceptance. `VERIFIED_NO_CHANGE_NEEDED` is accepted only when the independent semantic gate proves the existing candidate already satisfies the criterion. `COMPLETE` is accepted only when the independent semantic gate proves the changed candidate satisfies the criterion.

The known false-positive class is blocked:

```text
Prompt: Make app return me and prove it.
Observed: app.main() returns "ok"
Result: semantic_goal_unsatisfied, no DONE
```

`app.main()` returning `"ok"` does not satisfy a goal requiring `"me"`.

## Reports

Patchlet reports may include `semantic_goal_results`:

```json
{
  "criterion_id": "SGC001",
  "kind": "python_module_function_returns",
  "expected_value": "me",
  "actual_value": "ok",
  "passed": false
}
```

Report validation rejects self-contradictory semantic evidence, such as `expected_value: "me"`, `actual_value: "ok"`, and `passed: true`.

## Verification

Transaction and global verification include semantic status. For structured goals, final `DONE` requires semantic pass. Failed or unproven structured criteria keep the workflow out of `DONE` and record `semantic_goal_unsatisfied` evidence.

`final_verification.json` and `verification_matrix.json` include semantic fields such as:

```json
{
  "semantic_goal_status": "FAILED",
  "failed_semantic_criterion_ids": ["SGC001"]
}
```

## Operator Visibility

Live progress, monitor output, and `cxor status --json` surface semantic goal state. Status JSON includes a `semantic_goal` object with mode, status, criteria count, passed criteria, failed criteria, and paths to semantic evidence.

Compact progress can show:

```text
semantic goal SGC001 failed: expected app.main() == "me", observed "ok".
goal satisfaction gate failed for P0001; patchlet not accepted.
```

This is distinct from report schema failures, target hygiene failures, and report-ingestion failures.

## General goal proof contract

cxor treats the master prompt as the read-only source of truth. Each workflow freezes `.codex-orchestrator/master_prompt.md`, records `.codex-orchestrator/master_prompt_frozen.json`, derives `goal_interpretation.json` without claiming proof, classifies `provability/provability_result.json` before product patchlets, and stops unsupported or ambiguous goals early with `goal_not_provable_result.json` evidence.

Required proof is represented in `proof_obligations.json` and `probe_plan.json`. Worker-proposed proof is not enough: required obligations need orchestrator-owned rerun or validation in `independent_probe_rerun_result.json`, then `goal_coverage_gate_result.json` must pass. The rc4 semantic app.main path is now the concrete `SGC001 -> GI001 -> PO001 -> GP001` fast path inside this general contract.

Final DONE requires `master_prompt_concordance_result.json` and `master_prompt_satisfaction_result.json` in addition to transaction groups, integration validation, target hygiene, and unresolved-failure checks. Partial proof is not full DONE unless explicitly allowed by policy. See `docs/general_goal_proof_contract.md`.

## Goal progress, stop, and partial apply

cxor writes `goal_progress.json` and append-only `goal_progress.jsonl`; `cxor goal-progress`, `cxor status --json`, `cxor monitor`, and `cxor auto --live-progress` expose the latest obligation counts, proof state, accepted checkpoint, and next action.

`cxor stop` writes `control/stop_requested.json`; the orchestrator stops at a safe point and writes `control/stop_result.json`. `apply-results --scope accepted --allow-partial` is required for stopped non-DONE workflows and applies only latest accepted progress. In-progress unaccepted worker changes are not applied by default. `partial_apply_result.json` records the warning that the full master prompt may not be satisfied. See `docs/goal_progress_and_partial_apply.md`.
