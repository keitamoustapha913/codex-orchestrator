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
