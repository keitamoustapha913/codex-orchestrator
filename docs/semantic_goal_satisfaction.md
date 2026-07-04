# Master Prompt Satisfaction

Codex Orchestrator no longer supports an app.py-specific, app.main-specific,
Python-specific, or smoke-prompt regex semantic parser as the general
architecture.

Goal satisfaction now uses the no-compatibility repo-agnostic path:

```text
frozen master prompt
-> model-mediated goal interpretation
-> early provability classification
-> model-mediated proof-obligation planning
-> model/repo-aware probe planning
-> mandatory decomposition artifacts
-> patchlet plan
-> independent proof rerun or validation
-> goal coverage
-> master-prompt concordance
-> master-prompt satisfaction
```

The master prompt is the source of truth. Model interpretation, proof
obligations, probe plans, decomposition plans, patchlet plans, worker reports,
and worker-authored probes are derived artifacts. They are not proof by
themselves.

Real Codex reports may contain shorthand `semantic_goal_results`. A shorthand
item is accepted only as a raw worker semantic claim when it links to the
current patchlet's selected goal item, selected proof obligation, slice
boundary, and probe plan. The raw worker output is preserved. The claim remains
`LINKED_PENDING_ORCHESTRATOR_PROOF` and does not set `passed=true`.

The orchestrator rejects vague shorthand (`done`, `ok`, `looks good`,
`complete`, `seems fine`, `probably passes`) and rejects future-slice claims.
Canonical semantic results are generated only after independent probe rerun
evidence supplies expected and actual values.

Required artifacts include:

```text
.codex-orchestrator/goal_interpretation/model_request.json
.codex-orchestrator/goal_interpretation/model_response.raw.json
.codex-orchestrator/goal_interpretation/goal_interpretation.json
.codex-orchestrator/proof_planning/proof_obligations.json
.codex-orchestrator/probe_planning/probe_plan.json
.codex-orchestrator/decomposition/patchlet_plan.json
.codex-orchestrator/global_verification/master_prompt_concordance_result.json
.codex-orchestrator/global_verification/master_prompt_satisfaction_result.json
```

If model-mediated goal interpretation, proof planning, probe planning, or
decomposition cannot be produced and validated, the workflow safe-fails before
product patchlets. Missing decomposition artifacts do not fall back to one
global invariant or one patchlet.

Every patchlet has exactly one allowed product/runtime file. Multiple patchlets
may target the same file when the work slices are sequential. Patchlet prompts
carry the configured `CODEX_PATCHLET_TIMEOUT_SECONDS` budget, default 600
seconds, and use narrow scope so they do not require memory compacting.

`DONE` requires accepted master-prompt concordance and accepted master-prompt
satisfaction. Worker proof alone is not enough; the orchestrator must rerun or
validate required proof obligations and the goal coverage gate must pass.

Partial apply is separate from `DONE`: `apply-results --scope accepted
--allow-partial` applies only accepted checkpoints and warns that the full
master prompt may not be satisfied.
