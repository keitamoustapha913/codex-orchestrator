# Workflow Lifecycle, Reruns, And Reset

`cxor auto` records a durable workflow identity in
`.codex-orchestrator/workflow_identity.json`. The identity includes the target
HEAD and tree, target dirty status at workflow start, master prompt path,
master prompt SHA-256, worker mode, worktree mode, requested `--until`, and a
deterministic goal fingerprint.

Reruns are explicit:

- same goal fingerprint and terminal `DONE`: `cxor auto` returns existing DONE
  with an explicit message;
- changed prompt path or prompt content: `cxor auto` refuses unless the
  operator requests `--new-run` or `--force-new-run`;
- dirty target product/runtime files: `cxor auto` refuses unless
  `--allow-dirty-target` is passed, and the dirty status is recorded in
  workflow identity and rerun preflight evidence;
- active workflows resume only when the requested fingerprint matches, or when
  `--resume` is compatible with the same workflow.

Before each `auto` run, cxor writes
`.codex-orchestrator/rerun_preflight_result.json` with the existing and
requested goal fingerprints, changed fields, the decision, reasons, and
recommended commands.

New workflow controls:

```bash
cxor auto --repo <repo> --master <prompt> --new-run
cxor auto --repo <repo> --master <prompt> --force-new-run
cxor auto --repo <repo> --master <prompt> --allow-dirty-target
cxor archive --repo <repo>
cxor reset --repo <repo> --archive
cxor workflows --repo <repo>
cxor workflows --repo <repo> --json
```

Archive preserves evidence under `.codex-orchestrator/archives/`. Reset with
`--archive` archives first and clears active workflow state. Hard delete
requires `--hard-delete-artifacts` and refuses dirty product/runtime files.

Live progress is invocation-scoped. Each `cxor auto --live-progress` creates
`.codex-orchestrator/invocations/INV*.json` with the event cursor at start.
The progress stream prints only events after that cursor, so old
`operator_events.jsonl` lines are not replayed as if they belong to the current
command.

`cxor status --json` reports workflow identity, goal fingerprint, prompt hash,
target state at start, current dirty status, latest rerun preflight, and latest
apply-results guidance. `cxor monitor`, `cxor prompts`, and `cxor status`
accept `--workflow` filters.

After `cxor apply-results --mode working-tree`, inspect the working tree and
commit the applied product/runtime diff before starting a new goal. The latest
apply result is also written to
`.codex-orchestrator/apply_results/latest_apply_result.json` with rerun
guidance.

## Semantic Goal Satisfaction

Workflow identity links to semantic goal metadata when the master prompt can
be compiled into structured criteria. The semantic goal fingerprint changes
when the parsed expected value changes, for example from `"ok"` to `"me"`.

Structured semantic goals are persisted in
`.codex-orchestrator/semantic_goal_spec.json`. The Python main-return built-in
parser recognizes prompts such as `Make app return ok and prove it.` and
`Make app return me and prove it.`.

`VERIFIED_NO_CHANGE_NEEDED` requires independent goal proof. `DONE` requires
semantic pass for structured goals. Unsupported goals are visible as
unsupported and are not labeled as semantically proven.
