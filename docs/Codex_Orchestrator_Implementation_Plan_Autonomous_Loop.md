
# Codex Orchestrator Implementation Plan — Autonomous Root-Cause Probe-Gated Loop

Status: Approved implementation-plan consolidation  
Purpose: Preserve the approved implementation plan, the approved autonomous `cxor auto` correction, and additional detailed implementation guidance in one durable Markdown file without compressing the design.  
Scope: Python-controlled orchestration CLI, durable repository-side state, deterministic census, Codex worker adapter, evidence classification, inventory graph, invariant extraction, root-cause patchlets, patchlet executor, diff guard, report validation, transaction-group verification, global verification, repair planner, and the autonomous non-interactive loop that runs until `DONE`.

---

## Source material preserved in this file

This file consolidates and expands the approved implementation-plan reflections from two approved Markdown notes:

1. The approved implementation plan that recommended a deterministic Python orchestrator with a thin bash wrapper, a strict state machine, schemas, census, Codex adapter, patchlet executor, report validator, transaction/global verifiers, and repair planner.
2. The approved correction that added the missing one-shot autonomous command, `cxor auto --master ./master_prompt.md --until DONE`, and corrected the state model so `FAILED`, `REPAIR_PLANNING_REQUIRED`, `FAILED_WITH_EVIDENCE`, and `BLOCKED_WITH_EVIDENCE` do not stop the workflow in autonomous mode.

The implementation target is not a collection of manual stage commands. The implementation target is a resumable autonomous orchestrator where stage commands are available for debugging, but the primary user-facing command is:

```bash
cxor auto --master ./master_prompt.md --until DONE
```

The implementation should make the following invariant hard to bypass:

> A Codex patchlet cannot be marked complete unless it produced a valid report, obeyed the allowed-file boundary, satisfied the probe-gated root-cause contract, and left durable evidence behind.

The autonomous runner should make the following loop hard to bypass:

```text
failure → evidence → classification → repair/replan/rediscover → patchlets → verification → repeat until DONE
```


3. The approved correction that changes the implementation target from repo-local `tools/codex_orchestrator/` code to a standalone installable CLI package with its own Git repository, plus target repository resolution with `--repo` or current Git-root discovery.

After this update, the main command should be understood in two equivalent forms:

```bash
# Convenient form when already inside the target repo.
cxor auto --master ./master_prompt.md --until DONE

# Explicit form usable from anywhere.
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE
```

The explicit `--repo` form is the canonical fully qualified form. The short form is valid only when `cxor` can resolve the current Git root as the target repository.

---

# Executive implementation decision

Build the system as a standalone installable Python package with a thin shell wrapper and console-script entrypoints.

Do not implement the core state machine in bash.

Do not implement the orchestrator as repo-local code copied into each target repository. The orchestrator must have its own Git repository and must be installed as a CLI. The target repository receives durable workflow artifacts, not orchestrator source code.

Bash can launch the Python module, invoke repository-native commands, and remain useful for small wrappers, but the actual orchestration requires structured state transitions, schemas, atomic writes, retry policy, diff validation, run manifests, report validation, repair classification, and resumability. Those are Python responsibilities.

The project should expose a CLI named:

```bash
cxor
```

The long-form name can be:

```text
codex-orchestrator
```

The short name is better for frequent use:

```text
cxor
```

The primary command is:

```bash
cxor auto --master ./master_prompt.md --until DONE
```

The stage commands are still required, but they are not the main operating mode. They exist for debugging, inspection, CI substeps, manual intervention, and recovery.

---

# Final CLI shape

## Primary autonomous command

```bash
# Start from a master prompt and keep looping until DONE.
cxor auto --master ./master_prompt.md --until DONE
```

```bash
# Resume an existing workflow after interruption.
cxor auto --resume --until DONE
```

```bash
# Fully explicit non-interactive autonomous mode.
cxor auto \
  --master ./master_prompt.md \
  --non-interactive \
  --auto-repair \
  --auto-replan \
  --auto-rediscover \
  --until DONE
```

The shorter command should imply the continuous flags by default:

```bash
cxor auto --master ./master_prompt.md --until DONE
```

Meaning:

```text
--non-interactive
--auto-repair
--auto-replan
--auto-rediscover
```

## Stage and debug commands

```bash
# Initialize durable memory.
cxor init --master ./master_prompt.md

# Produce goal spec.
cxor normalize

# Run deterministic repo census.
cxor census

# Use Codex to classify deterministic evidence.
cxor classify-evidence

# Build graph/table/path mapping.
cxor build-inventory

# Extract invariants.
cxor extract-invariants

# Compile root-cause patchlets.
cxor compile-patchlets

# Run one patchlet.
cxor run-next

# Run all pending patchlets.
cxor run-all

# Validate one patchlet report.
cxor validate-report P0001

# Verify a transaction group.
cxor verify-group TG001

# Verify whole master goal.
cxor verify-global

# Classify failures into repair categories.
cxor classify-failures

# Plan repair from failures.
cxor plan-repair

# Apply the latest repair plan.
cxor apply-repair

# Run partial rediscovery for impacted graph nodes/files.
cxor rediscover --scope impacted

# Run full rediscovery.
cxor rediscover --scope full

# Rebuild only impacted inventory graph sections.
cxor rebuild-inventory --scope impacted

# Regenerate patchlets from latest repair plan.
cxor regenerate-patchlets --from-repair-plan latest

# Show current state.
cxor status

# Validate state file.
cxor validate-state

# Reset run metadata after explicit user request.
cxor reset-run
```

---

# Command hierarchy and intent

The CLI has three layers.

## Layer 1 — Autonomous driver

This is the real product surface:

```bash
cxor auto --master ./master_prompt.md --until DONE
```

It owns the whole loop.

It should be safe to run non-interactively.

It should be resumable.

It should never stop merely because a Codex patchlet failed, a verifier found a problem, or a repair plan is required.

It stops successfully only when the workflow state is `DONE`.

## Layer 2 — Stage commands

These are deterministic or semi-deterministic workflow stages:

```text
init
normalize
census
classify-evidence
build-inventory
extract-invariants
compile-patchlets
run-next
run-all
verify-group
verify-global
classify-failures
plan-repair
apply-repair
rediscover
rebuild-inventory
regenerate-patchlets
```

These commands are called internally by `cxor auto`.

They are also exposed for inspection and controlled manual execution.

## Layer 3 — Validators and internal services

These are not necessarily user-facing commands, but they should exist as Python modules:

```text
state validator
schema validator
report validator
diff guard
run lock
git guard
artifact manifest validator
root-cause contract validator
proof-of-fix validator
repair classifier
patchlet scheduler
transaction verifier
```

The autonomous runner should call these directly.

---

# Repository layout

The orchestrator implementation should live in the repository, for example:

```text
tools/codex_orchestrator/
  __init__.py
  cli.py
  config.py
  paths.py
  errors.py
  jsonio.py
  state.py
  lock.py
  command_runner.py
  codex_adapter.py
  git_guard.py
  artifact_manifest.py
  scheduler.py
  repair.py
  rediscovery.py
  worktree.py
  logging.py
  schemas/
    goal_spec.schema.json
    evidence.schema.json
    inventory_graph.schema.json
    invariant.schema.json
    patchlet.schema.json
    patchlet_index.schema.json
    patchlet_report.schema.json
    transaction_group.schema.json
    final_verification.schema.json
    repair_plan.schema.json
    state.schema.json
    run_manifest.schema.json
  stages/
    init_stage.py
    normalize_stage.py
    census_stage.py
    classify_evidence_stage.py
    inventory_stage.py
    invariant_stage.py
    patchlet_compile_stage.py
    patchlet_execute_stage.py
    group_verify_stage.py
    global_verify_stage.py
    failure_classify_stage.py
    repair_plan_stage.py
    repair_apply_stage.py
    rediscovery_stage.py
  validators/
    schema_validator.py
    diff_validator.py
    report_validator.py
    root_cause_validator.py
    proof_of_fix_validator.py
    state_validator.py
    transaction_validator.py
    final_verification_validator.py
  prompt_templates/
    normalize_master_prompt.md
    classify_evidence.md
    build_inventory.md
    extract_invariants.md
    compile_patchlets.md
    root_cause_patchlet.md
    verify_group.md
    verify_global.md
    classify_failures.md
    plan_repair.md
  workers/
    base.py
    real_codex.py
    mock_codex.py
    manual.py
    ci_only.py
```

The durable workflow artifacts should live under:

```text
.codex-orchestrator/
  master_prompt.md
  config.json
  state.json
  run_manifest.json
  goal_spec.json
  census/
    commands.jsonl
    repo_files.txt
    git_status.txt
    rg_index.jsonl
    search_hits.jsonl
    symbols.json
    tests.json
    imports.json
    routes.json
    configs.json
    tool_availability.json
    stdout/
    stderr/
  search_evidence.jsonl
  search_evidence.md
  inventory_graph.json
  inventory_table.md
  path_mapping.json
  invariants.json
  patchlets/
    patchlet_index.json
    transaction_groups.json
  subprompts/
    0001_<slug>.md
    0002_<slug>.md
  reports/
    P0001.json
    P0001.md
  runs/
    R0001/
      command.json
      stdout.txt
      stderr.txt
      output.jsonl
      git_before.txt
      git_after.txt
      diff_name_status.txt
      diff.patch
    R0002/
  failures/
    F0001.json
    F0001.md
  repair_plans/
    RP0001.json
    RP0001.md
  final_verification.json
  final_verification.md
  .lock

.artifacts/probes/
  P0001/
    probe.py
    run_001/
      row_ledger.jsonl
      trace_ledger.jsonl
      before_state.json
      after_state.json
      cleanup_proof.json
```

The `.codex-orchestrator/` directory is the durable memory.

The `.artifacts/probes/` directory is the durable runtime-proof store.

No Codex call should rely on chat memory. Each Codex worker receives only the prompt and the relevant durable artifacts.

---

# State machine correction

The earlier implementation plan included `FAILED` and `REPAIR_PLANNING_REQUIRED` as if they could stop the workflow.

That is corrected here.

In autonomous mode, `FAILED` should not be a normal terminal state.

`REPAIR_PLANNING_REQUIRED` is not terminal.

`FAILED_WITH_EVIDENCE` is not terminal.

`BLOCKED_WITH_EVIDENCE` is not terminal.

They are evidence-producing internal states that feed repair, replanning, rediscovery, patchlet regeneration, and re-verification.

The only normal successful terminal state is:

```text
DONE
```

There can be an emergency abort state, but it should not represent an ordinary Codex or verification failure.

Use:

```text
ORCHESTRATOR_ABORTED
```

only for conditions where the orchestrator itself cannot safely continue, for example:

```text
- corrupted state.json that cannot be repaired;
- missing repository root;
- invalid permissions;
- unable to acquire lock after configured policy;
- user interrupt;
- disk full;
- unrecoverable schema migration failure;
- configured safety ceiling exceeded.
```

`ORCHESTRATOR_ABORTED` is different from a task failure.

A task failure is input to the loop.

An orchestrator abort is an infrastructure/safety failure of the runner itself.

---

# Corrected state list

Use this state list:

```text
INITIALIZED
MASTER_PROMPT_SAVED
GOAL_SPEC_REQUIRED
GOAL_SPEC_READY
CENSUS_REQUIRED
CENSUS_READY
EVIDENCE_CLASSIFICATION_REQUIRED
EVIDENCE_READY
INVENTORY_BUILD_REQUIRED
INVENTORY_READY
INVARIANT_EXTRACTION_REQUIRED
INVARIANTS_READY
PATCHLET_COMPILATION_REQUIRED
PATCHLETS_READY
PATCHLET_EXECUTION_IN_PROGRESS
PATCHLET_EXECUTION_COMPLETE
TRANSACTION_VERIFICATION_REQUIRED
TRANSACTION_VERIFICATION_COMPLETE
GLOBAL_VERIFICATION_REQUIRED
GLOBAL_VERIFICATION_COMPLETE
FAILURE_CLASSIFICATION_REQUIRED
REPAIR_PLANNING_REQUIRED
REPAIR_PLAN_READY
REPAIR_APPLICATION_REQUIRED
REPAIR_IN_PROGRESS
PARTIAL_REDISCOVERY_REQUIRED
FULL_REDISCOVERY_REQUIRED
INVENTORY_REBUILD_REQUIRED
PATCHLET_REGENERATION_REQUIRED
GLOBAL_REVERIFY_REQUIRED
DONE
ORCHESTRATOR_ABORTED
```

Only `DONE` is a normal successful stop.

`ORCHESTRATOR_ABORTED` is an emergency stop.

All other states are resumable workflow states.

---

# Autonomous loop behavior

`cxor auto` should run until `DONE`.

It should not stop because repair is required.

It should not stop because a patchlet reports `FAILED_WITH_EVIDENCE`.

It should not stop because a patchlet reports `BLOCKED_WITH_EVIDENCE`.

It should not stop because global verification failed.

It should not stop because a transaction group failed.

It should treat those outcomes as structured evidence.

The autonomous loop should convert evidence into one of:

```text
new repair patchlet
same-file enriched patchlet
different-file patchlet
partial rediscovery
full rediscovery
inventory rebuild
invariant refinement
path mapping correction
transaction-group repair
final verifier rerun
```

The conceptual loop is:

```text
cxor auto --master ./master_prompt.md --until DONE
   ↓
init
   ↓
normalize
   ↓
census
   ↓
classify-evidence
   ↓
build-inventory
   ↓
extract-invariants
   ↓
compile-patchlets
   ↓
run-all patchlets
   ↓
verify-groups
   ↓
verify-global
   ↓
DONE?
   ├── yes
   │     ↓
   │   exit 0
   │
   └── no
         ↓
      classify-failures
         ↓
      plan-repair
         ↓
      apply-repair
         ↓
      needed action?
         ├── repair patchlets
         │     ↓
         │   run repair patchlets
         │
         ├── partial rediscovery
         │     ↓
         │   rediscover impacted scope
         │     ↓
         │   rebuild impacted inventory
         │     ↓
         │   regenerate impacted patchlets
         │
         ├── full rediscovery
         │     ↓
         │   census
         │     ↓
         │   classify-evidence
         │     ↓
         │   build-inventory
         │     ↓
         │   extract-invariants
         │     ↓
         │   compile-patchlets
         │
         └── invariant/path correction
               ↓
             regenerate patchlets
         ↓
      verify again
         ↓
      loop until DONE
```

---

# Autonomous loop pseudocode

```python
def auto(master: str | None, resume: bool, until: str = "DONE") -> int:
    with run_lock(".codex-orchestrator/.lock"):
        state = load_or_initialize_state(master=master, resume=resume)

        while state.stage != "DONE":
            state = refresh_state()

            if needs_init(state):
                run_init(master)

            elif needs_goal_spec(state):
                run_normalize()

            elif needs_census(state):
                run_census()

            elif needs_evidence(state):
                run_classify_evidence()

            elif needs_inventory(state):
                run_build_inventory()

            elif needs_invariants(state):
                run_extract_invariants()

            elif needs_patchlets(state):
                run_compile_patchlets()

            elif has_pending_patchlets(state):
                run_next_patchlet_or_repair_current()

            elif needs_transaction_verification(state):
                run_transaction_verifiers()

            elif needs_global_verification(state):
                result = run_global_verifier()

                if result.done:
                    mark_done()
                    break

                record_global_failures(result)
                mark_failure_classification_required()

            elif needs_failure_classification(state):
                classify_failures()

            elif needs_repair_plan(state):
                plan_repair()

            elif needs_repair_application(state):
                apply_repair_plan()
                # This may generate repair patchlets,
                # trigger partial rediscovery,
                # trigger full rediscovery,
                # rebuild inventory,
                # regenerate patchlets,
                # or request global re-verification.

            elif needs_partial_rediscovery(state):
                run_partial_census()
                run_partial_evidence_classification()
                rebuild_impacted_inventory()
                regenerate_impacted_patchlets()

            elif needs_full_rediscovery(state):
                run_census()
                run_classify_evidence()
                run_build_inventory()
                run_extract_invariants()
                run_compile_patchlets()

            elif needs_inventory_rebuild(state):
                rebuild_inventory_for_current_scope()

            elif needs_patchlet_regeneration(state):
                regenerate_patchlets_for_current_scope()

            elif needs_global_reverify(state):
                mark_global_verification_required()

            else:
                classify_unknown_state_and_plan_repair()

        return 0
```

---

# State file design

Use a state file with enough information to resume and audit every autonomous loop iteration.

Example:

```json
{
  "schema_version": "1.0",
  "kind": "cxor_state",
  "workflow_id": "20260702-001",
  "stage": "PATCHLET_EXECUTION_IN_PROGRESS",
  "mode": "auto",
  "until": "DONE",
  "master_prompt_sha256": "...",
  "repo_sha_start": "...",
  "repo_sha_current": "...",
  "current_loop_iteration": 4,
  "current_patchlet_id": "P0012",
  "attempts": {
    "P0012": 2
  },
  "completed_patchlets": ["P0001", "P0002"],
  "verified_no_change_needed": ["P0003"],
  "blocked_patchlets": ["P0009"],
  "failed_patchlets": ["P0012"],
  "pending_patchlets": ["P0013", "P0014"],
  "transaction_groups": [
    {
      "transaction_group_id": "TG001",
      "status": "PENDING"
    }
  ],
  "failure_cycles": [
    {
      "failure_cycle_id": "FC001",
      "source": "GLOBAL_VERIFICATION_FAILED",
      "created_failure_ids": ["F0001", "F0002"],
      "repair_plan_id": "RP0001",
      "status": "REPAIR_IN_PROGRESS"
    }
  ],
  "repair_cycles": [
    {
      "repair_plan_id": "RP0001",
      "classification": "INSIDE_KNOWN_GRAPH",
      "generated_patchlets": ["P0015"],
      "status": "PATCHLETS_GENERATED"
    }
  ],
  "created_at": "...",
  "updated_at": "..."
}
```

State updates must be atomic.

Use:

```text
state.json.tmp → fsync → rename → state.json
```

The orchestrator must never leave partially written state after interruption.

---

# Run manifest design

The run manifest should record every operation, including deterministic commands and Codex worker calls.

Example:

```json
{
  "schema_version": "1.0",
  "kind": "run_manifest",
  "workflow_id": "20260702-001",
  "runs": [
    {
      "run_id": "R0001",
      "stage": "CENSUS_REQUIRED",
      "command": "git ls-files",
      "exit_code": 0,
      "stdout_path": ".codex-orchestrator/runs/R0001/stdout.txt",
      "stderr_path": ".codex-orchestrator/runs/R0001/stderr.txt",
      "started_at": "...",
      "ended_at": "...",
      "repo_sha_before": "...",
      "repo_sha_after": "...",
      "changed_files": []
    },
    {
      "run_id": "R0017",
      "stage": "PATCHLET_EXECUTION_IN_PROGRESS",
      "worker": "real_codex",
      "patchlet_id": "P0004",
      "prompt_path": ".codex-orchestrator/subprompts/0004_service_boundary.md",
      "jsonl_path": ".codex-orchestrator/runs/R0017/output.jsonl",
      "exit_code": 0,
      "repo_sha_before": "...",
      "repo_sha_after": "...",
      "diff_path": ".codex-orchestrator/runs/R0017/diff.patch",
      "changed_files": [
        "backend/services/topology.py",
        ".artifacts/probes/P0004/probe.py",
        ".codex-orchestrator/reports/P0004.json"
      ]
    }
  ]
}
```

The run manifest is useful for resuming, debugging, replaying, and proving that the autonomous loop did not skip stages.

---

# Locking rules

The autonomous driver must acquire a run lock before mutating state.

Lock path:

```text
.codex-orchestrator/.lock
```

The lock should include:

```json
{
  "pid": 12345,
  "hostname": "...",
  "workflow_id": "20260702-001",
  "started_at": "...",
  "command": "cxor auto --master ./master_prompt.md --until DONE"
}
```

Rules:

```text
- Only one process may mutate .codex-orchestrator/state.json at a time.
- Stage commands that mutate state must also acquire the lock.
- Read-only commands may read without locking or may acquire a shared lock.
- Stale locks require explicit policy.
- A stale lock should not be deleted silently unless the process is proven absent or a configured timeout has passed.
```

---

# Git guard and diff enforcement

The patchlet executor must treat git diff as a safety boundary.

Before each Codex patchlet:

```bash
git rev-parse HEAD
git status --short
git diff --name-status
```

After each Codex patchlet:

```bash
git rev-parse HEAD
git status --short
git diff --name-status
git diff -- .
```

Allowed changes:

```text
- the one declared product/runtime file;
- .artifacts/probes/**;
- .codex-orchestrator/reports/**;
- .codex-orchestrator/runs/**.
```

Forbidden changes:

```text
- any other product/runtime file;
- changes to orchestrator source during patchlet execution;
- changes to master prompt during patchlet execution;
- changes to goal_spec.json during patchlet execution;
- changes to inventory_graph.json during patchlet execution;
- changes to invariants.json during patchlet execution;
- changes to unrelated tests unless explicitly allowed;
- test weakening;
- deletion of evidence artifacts;
- deletion of previous reports;
- deletion of previous runs.
```

When unauthorized diffs are detected:

```text
1. save the unauthorized diff as an artifact;
2. mark the patchlet result as invalid;
3. roll back unauthorized changes or isolate them in a failed run worktree;
4. classify the failure;
5. continue the autonomous repair loop rather than stopping as terminal failure.
```

The stronger design is to run each patchlet in a temporary git worktree and merge only after validation.

Minimum version:

```text
pre/post SHA guard + git diff validator
```

Stronger version:

```text
per-patchlet worktree + validated merge
```

---

# Worker model

The Codex worker adapter must be swappable.

Required worker modes:

```text
real_codex
mock_codex
```

Future worker modes:

```text
manual
ci_only
```

## real_codex

Executes a real Codex CLI call.

Responsibilities:

```text
- build codex exec command;
- pass prompt content;
- capture stdout;
- capture stderr;
- capture JSONL when available;
- record exit code;
- record start/end timestamps;
- record repo SHA before and after;
- emit run manifest entry.
```

## mock_codex

Used for testing orchestration without spending calls or depending on model behavior.

Responsibilities:

```text
- load configured mock response;
- optionally create mock report files;
- optionally create mock diffs;
- simulate success, blocked, failed, and unauthorized-diff outcomes;
- allow unit tests to validate the state machine.
```

## manual

Allows a human to perform a patchlet but still requires the same report, diff validation, and state transitions.

This is useful when a patchlet is too sensitive or when direct model execution is not desired.

## ci_only

Runs probes and verifiers without allowing Codex edits.

This is useful for verifying previously generated patchlets or checking a branch in CI.

---

# Configuration file

Use:

```text
.codex-orchestrator/config.json
```

Example:

```json
{
  "schema_version": "1.0",
  "kind": "cxor_config",
  "worker_mode": "real_codex",
  "max_attempts_per_patchlet": 3,
  "max_repair_cycles": null,
  "max_auto_iterations": null,
  "stop_only_on_done": true,
  "allow_orchestrator_abort": true,
  "allowed_artifact_dirs": [
    ".artifacts/probes/",
    ".codex-orchestrator/reports/",
    ".codex-orchestrator/runs/"
  ],
  "require_worktree_per_patchlet": false,
  "codex": {
    "exec_command": "codex exec",
    "json_output": true,
    "extra_args": []
  },
  "census": {
    "required_tools": ["git", "rg"],
    "optional_tools": ["ctags", "ast-grep", "tree-sitter", "docker", "npm", "pytest"]
  },
  "verification": {
    "require_transaction_groups": true,
    "require_global_verification": true,
    "allow_non_blocking_invariants_only_with_evidence": true
  },
  "repair": {
    "auto_repair": true,
    "auto_replan": true,
    "auto_rediscover": true,
    "full_rediscovery_only_when_justified": true
  }
}
```

Important policy decision:

```text
max_repair_cycles can be null for truly continuous looping.
```

If a safety ceiling is configured, reaching it should produce `ORCHESTRATOR_ABORTED`, not `DONE`, because the workflow has not succeeded.

---

# Phase-by-phase implementation plan

## Phase 1 — Orchestrator skeleton

Do not start with Codex calls.

Build the external orchestrator shell first.

Deliverables:

```text
tools/codex_orchestrator/
  cli.py
  config.py
  state.py
  paths.py
  errors.py
  command_runner.py
  jsonio.py
  lock.py
  logging.py
  schemas/
    goal_spec.schema.json
    evidence.schema.json
    inventory_graph.schema.json
    invariant.schema.json
    patchlet.schema.json
    patchlet_report.schema.json
    state.schema.json
    run_manifest.schema.json
```

Commands:

```bash
cxor init --master master_prompt.md
cxor status
cxor validate-state
cxor reset-run
```

Acceptance criteria:

```text
- .codex-orchestrator/ is created deterministically.
- .artifacts/probes/ is created deterministically.
- master_prompt.md is copied into .codex-orchestrator/master_prompt.md.
- config.json is initialized.
- state.json is initialized.
- run_manifest.json is initialized.
- All schema files exist.
- cxor status prints current workflow stage.
- cxor validate-state validates state.json against schema.
- No Codex call is needed.
```

## Phase 2 — Corrected state machine

Implement the corrected state machine where `DONE` is the only successful terminal state.

Do not implement `FAILED` as a normal terminal state.

Use `ORCHESTRATOR_ABORTED` only for unrecoverable runner-level conditions.

Acceptance criteria:

```text
- Every command checks allowed transitions.
- Invalid transitions fail early.
- State is resumable.
- State writes are atomic.
- Manual stage commands can advance state only through valid transitions.
- `cxor auto` can route non-terminal failures into repair/replanning states.
```

## Phase 3 — Deterministic repository census

Command:

```bash
cxor census
```

Outputs:

```text
.codex-orchestrator/census/repo_files.txt
.codex-orchestrator/census/git_status.txt
.codex-orchestrator/census/rg_index.jsonl
.codex-orchestrator/census/symbols.json
.codex-orchestrator/census/tests.json
.codex-orchestrator/census/imports.json
.codex-orchestrator/census/routes.json
.codex-orchestrator/census/configs.json
.codex-orchestrator/census/tool_availability.json
.codex-orchestrator/census/commands.jsonl
```

Initial commands:

```bash
git ls-files
git status --short
rg --files
rg -n "<goal keywords>"
```

Optional commands:

```bash
pytest --collect-only
npm test -- --listTests
ctags
ast-grep
tree-sitter
pydeps
pipdeptree
npm ls
docker compose config
```

Acceptance criteria:

```text
- Census is read-only.
- Every command records command, exit code, stdout path, stderr path, timestamp.
- Missing optional tools are recorded, not fatal.
- Required tool absence is fatal to the stage but becomes an orchestrator infrastructure issue, not a Codex task failure.
- Outputs are deterministic enough to diff.
```

## Phase 4 — Codex worker adapter

Command:

```bash
cxor codex-run --prompt-file <file> --output-jsonl <file>
```

Responsibilities:

```text
- Build codex exec command.
- Pass prompt file content.
- Capture stdout/stderr.
- Capture JSONL when supported.
- Record exit code.
- Record repo SHA before and after.
- Record command metadata.
- Support mock mode.
```

Acceptance criteria:

```text
- Codex calls are isolated behind one adapter.
- Every call writes a run record.
- Mock mode can simulate all major outcomes.
- Codex output is not trusted until validated.
```

## Phase 5 — Master prompt normalization

Command:

```bash
cxor normalize
```

Input:

```text
.codex-orchestrator/master_prompt.md
```

Output:

```text
.codex-orchestrator/goal_spec.json
```

Goal spec schema skeleton:

```json
{
  "schema_version": "1.0",
  "kind": "goal_spec",
  "master_goal": "string",
  "success_goals": [],
  "target_invariants": [],
  "forbidden_actions": [],
  "runtime_constraints": [],
  "validation_commands": [],
  "allowed_edit_scope": [],
  "must_preserve": [],
  "known_failure_modes": [],
  "proof_requirements": []
}
```

Acceptance criteria:

```text
- goal_spec.json validates.
- Every success goal has an ID.
- Every target invariant has an ID or placeholder.
- Forbidden actions are explicit.
- Proof requirements include root-cause/probe-gated requirements.
```

## Phase 6 — Evidence classification

Command:

```bash
cxor classify-evidence
```

Inputs:

```text
.codex-orchestrator/goal_spec.json
.codex-orchestrator/census/
```

Outputs:

```text
.codex-orchestrator/search_evidence.jsonl
.codex-orchestrator/search_evidence.md
```

Evidence row schema:

```json
{
  "schema_version": "1.0",
  "kind": "evidence_row",
  "evidence_id": "E001",
  "goal_id": "G001",
  "role": "producer | transformer | consumer | adapter | validator | test | config | state_owner | runtime_boundary",
  "file": "path/to/file",
  "symbol": "symbol_name_or_null",
  "line_range": "L10-L50",
  "found_by": "rg | ctags | pytest_collect | route_listing | codex_classification",
  "command_or_source": "...",
  "why_relevant": "...",
  "confidence": "high | medium | low",
  "connected_evidence_ids": []
}
```

Acceptance criteria:

```text
- Every row has a concrete file path unless repo-level/config-level.
- Every row points to deterministic source when possible.
- Codex-only classification is marked low confidence.
- Evidence IDs are stable and unique.
```

## Phase 7 — Inventory graph and table

Command:

```bash
cxor build-inventory
```

Outputs:

```text
.codex-orchestrator/inventory_graph.json
.codex-orchestrator/inventory_table.md
.codex-orchestrator/path_mapping.json
```

Inventory graph schema skeleton:

```json
{
  "schema_version": "1.0",
  "kind": "inventory_graph",
  "nodes": [
    {
      "id": "N001",
      "file": "path/to/file",
      "symbol": "symbol_name",
      "role": "producer",
      "evidence_ids": ["E001"],
      "confidence": "high"
    }
  ],
  "edges": [
    {
      "id": "EDGE001",
      "from": "N001",
      "to": "N002",
      "kind": "calls | imports | emits | consumes | transforms | validates | persists | reads | writes",
      "evidence_ids": ["E004"],
      "confidence": "high"
    }
  ]
}
```

Acceptance criteria:

```text
- Every graph node links to evidence IDs.
- Every graph edge links to evidence IDs.
- Low-confidence edges are marked.
- inventory_table.md is generated from graph.
- path_mapping.json traces master goals to graph nodes/edges.
```

## Phase 8 — Invariant extraction

Command:

```bash
cxor extract-invariants
```

Output:

```text
.codex-orchestrator/invariants.json
```

Invariant schema:

```json
{
  "schema_version": "1.0",
  "kind": "invariant",
  "invariant_id": "I001",
  "master_goal_id": "G001",
  "description": "...",
  "producer_nodes": [],
  "transformer_nodes": [],
  "adapter_nodes": [],
  "consumer_nodes": [],
  "state_owner_nodes": [],
  "runtime_signal_or_condition": "...",
  "required_probes": [],
  "negative_controls": [],
  "regression_commands": [],
  "evidence_ids": [],
  "graph_node_ids": [],
  "graph_edge_ids": []
}
```

Acceptance criteria:

```text
- Every invariant links to goal IDs.
- Every invariant links to graph nodes/edges.
- Every invariant names the affected runtime boundary.
- Every invariant has a probe requirement or explicit blocked reason.
```

## Phase 9 — Root-Cause Patchlet compiler

Command:

```bash
cxor compile-patchlets
```

Outputs:

```text
.codex-orchestrator/patchlets/patchlet_index.json
.codex-orchestrator/patchlets/transaction_groups.json
.codex-orchestrator/subprompts/0001_<slug>.md
.codex-orchestrator/subprompts/0002_<slug>.md
```

Patchlet manifest schema:

```json
{
  "schema_version": "1.0",
  "kind": "patchlet",
  "patchlet_id": "P0001",
  "subprompt_path": ".codex-orchestrator/subprompts/0001_service_boundary.md",
  "master_goal_ids": ["G001"],
  "invariant_ids": ["I001"],
  "evidence_ids": ["E001", "E002"],
  "graph_node_ids": ["N001", "N002"],
  "allowed_product_runtime_file": "path/to/file.py",
  "allowed_artifact_dirs": [
    ".artifacts/probes/",
    ".codex-orchestrator/reports/",
    ".codex-orchestrator/runs/"
  ],
  "transaction_group_id": "TG001",
  "depends_on": [],
  "status": "PENDING"
}
```

Acceptance criteria:

```text
- Every patchlet has exactly one allowed product/runtime file.
- Artifact directories are explicitly allowed.
- Each patchlet links to evidence, invariants, and graph nodes.
- Each patchlet requires a minimal direct runtime probe as first action.
- Each patchlet includes ROOT-CAUSE PROBE-ONLY INVESTIGATION gate.
- Each patchlet includes proof-of-fix gate.
- Each patchlet includes TDD checklist gate.
```

## Phase 10 — Patchlet executor

Commands:

```bash
cxor run-next
cxor run-all
cxor resume
```

Execution algorithm:

```text
1. Load state.json.
2. Load patchlet_index.json.
3. Select next PENDING patchlet whose dependencies are satisfied.
4. Record repo SHA before execution.
5. Execute Codex with the patchlet subprompt.
6. Capture stdout/stderr/JSONL into .codex-orchestrator/runs/.
7. Inspect git diff.
8. Check that at most one product/runtime file changed.
9. Check that changed product/runtime file is the allowed file.
10. Permit artifact changes only under approved directories.
11. Validate report exists.
12. Validate report schema.
13. Validate root-cause/proof contract.
14. Classify result.
15. Commit state transition.
16. Continue, repair, replan, or rediscover.
```

Acceptance criteria:

```text
- Unauthorized diffs cause immediate invalidation.
- Unauthorized diffs are saved and rolled back or isolated.
- Patchlet cannot mark itself complete without valid report.
- Report status must be valid.
- Blind retries are impossible.
- Failed patchlets feed repair/replanning.
```

## Phase 11 — Patchlet report validator

Command:

```bash
cxor validate-report P0001
```

Report schema:

```json
{
  "schema_version": "1.0",
  "kind": "patchlet_report",
  "patchlet_id": "P0001",
  "status": "COMPLETE | VERIFIED_NO_CHANGE_NEEDED | BLOCKED_WITH_EVIDENCE | FAILED_WITH_EVIDENCE",
  "changed_product_runtime_file": "path/to/file.py|null",
  "changed_artifact_files": [],
  "probe_commands": [],
  "deterministic_run_counts": {
    "baseline": "5/5",
    "proof_of_fix": "5/5",
    "negative_controls": "5/5"
  },
  "root_cause_classification": {
    "observed_failure": "...",
    "immediate_cause": "...",
    "why_immediate_cause_happened": "...",
    "deeper_owner_boundary": "...",
    "producer_transformer_consumer_boundary": "...",
    "not_downstream_of_unprobed_state_proof": "...",
    "negative_control_proof": "..."
  },
  "before_after_state": [],
  "row_ledger": [],
  "trace_ledger": [],
  "cleanup_proof": "...",
  "acceptance_criteria_result": "pass | fail | blocked"
}
```

Acceptance criteria:

```text
- COMPLETE requires implementation evidence and post-implementation probes.
- VERIFIED_NO_CHANGE_NEEDED requires minimal direct probe evidence and no product/runtime diff.
- BLOCKED_WITH_EVIDENCE requires a clear boundary or scope reason.
- FAILED_WITH_EVIDENCE requires failed probe/root-cause/proof-of-fix evidence.
- Vague statuses are rejected.
```

## Phase 12 — Root-cause/proof validators

Required validators:

```text
validate_no_product_edit_during_investigation
validate_minimal_probe_present
validate_deterministic_reproduction
validate_controlled_initial_state
validate_boundary_identified
validate_recursive_why_audit
validate_root_cause_toggle
validate_negative_controls
validate_proof_of_fix_full_path
validate_no_timing_luck_claim
validate_cleanup_proof
```

Fully automatic checks:

```text
- Required report fields exist.
- Commands are recorded.
- Artifacts are emitted.
- Changed files stay within scope.
- Deterministic run count is declared.
- Cleanup proof is present.
```

Semi-automatic checks:

```text
- Root-cause explanation identifies producer → transformer → consumer.
- Proof-of-fix claims full affected runtime path.
- Negative controls are described.
- No timing luck is claimed.
- The report distinguishes investigation from implementation.
```

Acceptance criteria:

```text
- COMPLETE is impossible without root-cause/proof-of-fix fields.
- Product/runtime edits are invalid unless proof-of-fix gate is documented.
- The executor rejects report-only success without durable proof.
```

## Phase 13 — Transaction-group verifier

Command:

```bash
cxor verify-group TG001
```

Transaction group schema:

```json
{
  "schema_version": "1.0",
  "kind": "transaction_group",
  "transaction_group_id": "TG001",
  "description": "...",
  "patchlet_ids": ["P0001", "P0002", "P0003"],
  "invariant_ids": ["I001"],
  "verification_commands": [],
  "status": "PENDING | PASSED | FAILED | BLOCKED"
}
```

Acceptance criteria:

```text
- Group verifier runs only after all required patchlets are COMPLETE or VERIFIED_NO_CHANGE_NEEDED.
- Group verifier runs targeted integration commands.
- Group failure maps to invariant IDs and graph nodes.
- Group failure creates repair input, not blind retry.
```

## Phase 14 — Global verifier

Command:

```bash
cxor verify-global
```

Outputs:

```text
.codex-orchestrator/final_verification.json
.codex-orchestrator/final_verification.md
```

Global verifier checks:

```text
- Which master goals are proven complete?
- Which invariants are proven?
- Which invariants are unproven?
- Which invariants failed?
- What evidence supports each conclusion?
- What probes passed?
- What probes failed?
- What regression commands passed?
- What regression commands failed?
- What files changed?
- Were changed files allowed by patchlets?
- Were failure reports resolved or classified?
```

Acceptance criteria:

```text
- Global verifier is read-only.
- Global verifier validates all patchlet reports.
- Global verifier validates transaction groups.
- Global verifier maps result to master goals and invariants.
- DONE is allowed only when all required invariants are proven or explicitly non-blocking with evidence.
```

## Phase 15 — Repair planner

Command:

```bash
cxor plan-repair
```

Repair classifications:

```text
INSIDE_KNOWN_GRAPH
OUTSIDE_KNOWN_GRAPH
INVENTORY_CONTRADICTION
REPEATED_REPAIR_FAILURE
MASTER_GOAL_CHANGED
EXCESSIVE_IMPACTED_SCOPE
```

Outputs:

```text
.codex-orchestrator/repair_plans/RP0001.json
.codex-orchestrator/repair_plans/RP0001.md
.codex-orchestrator/failures/F0001.json
.codex-orchestrator/failures/F0001.md
```

Acceptance criteria:

```text
- Failures are classified before retry.
- Same-prompt retry is allowed only for proven infrastructure failure.
- Same-file deeper root regenerates enriched same-file patchlet.
- Different-file root creates a new patchlet or blocks with evidence.
- Inventory contradiction triggers partial rediscovery or graph rebuild.
- Full restart is never first repair action unless master goal changed.
```

## Phase 16 — Autonomous driver

Command:

```bash
cxor auto --master ./master_prompt.md --until DONE
```

Purpose:

```text
Run the full orchestration loop non-interactively until the final verifier proves all master goals and target invariants.
```

Responsibilities:

```text
- Initialize missing workflow state.
- Resume existing workflow state.
- Execute all required stages in dependency order.
- Run patchlets.
- Validate patchlet reports.
- Run transaction verifiers.
- Run global verifier.
- Convert verification failures into repair plans.
- Apply repair plans.
- Trigger partial rediscovery when justified.
- Trigger full rediscovery when justified.
- Rebuild impacted inventory when justified.
- Regenerate patchlets when justified.
- Continue until DONE.
```

Acceptance criteria:

```text
- The command does not stop at REPAIR_PLANNING_REQUIRED.
- The command does not stop at FAILED_WITH_EVIDENCE.
- The command does not stop at BLOCKED_WITH_EVIDENCE.
- The command treats those states as inputs to repair/replanning.
- The command exits 0 only when state is DONE.
- Every loop iteration writes durable state and run records.
- The command can resume after interruption.
```

---

# Repair application details

`plan-repair` only decides what should happen.

`apply-repair` performs the next workflow mutation.

In manual mode, it is acceptable to run:

```bash
cxor verify-global
cxor classify-failures
cxor plan-repair
cxor apply-repair
```

In autonomous mode, these steps are internal.

`apply-repair` can do one of the following:

```text
1. Generate repair patchlets inside the known graph.
2. Generate an enriched same-file patchlet.
3. Generate a different-file patchlet because root moved to a different boundary.
4. Trigger partial rediscovery.
5. Trigger full rediscovery.
6. Trigger impacted inventory rebuild.
7. Trigger invariant/path correction.
8. Trigger transaction-group re-verification.
9. Trigger global re-verification.
```

Repair plan schema:

```json
{
  "schema_version": "1.0",
  "kind": "repair_plan",
  "repair_plan_id": "RP0001",
  "source_failure_ids": ["F0001"],
  "classification": "INSIDE_KNOWN_GRAPH",
  "recommended_action": "GENERATE_REPAIR_PATCHLETS",
  "impacted_goal_ids": ["G001"],
  "impacted_invariant_ids": ["I001"],
  "impacted_graph_node_ids": ["N001", "N002"],
  "impacted_files": ["backend/services/topology.py"],
  "generated_patchlet_ids": [],
  "requires_partial_rediscovery": false,
  "requires_full_rediscovery": false,
  "requires_inventory_rebuild": false,
  "requires_patchlet_regeneration": true,
  "why": "...",
  "acceptance_criteria": []
}
```

Failure schema:

```json
{
  "schema_version": "1.0",
  "kind": "failure_record",
  "failure_id": "F0001",
  "source": "GLOBAL_VERIFICATION_FAILED | TRANSACTION_GROUP_FAILED | PATCHLET_FAILED | PATCHLET_BLOCKED | INVENTORY_CONTRADICTION",
  "source_id": "P0007 | TG001 | final_verification",
  "observed_failure": "...",
  "blocking_invariant_ids": ["I001"],
  "evidence_ids": ["E001"],
  "graph_node_ids": ["N001"],
  "suspected_scope": "inside_known_graph | outside_known_graph | inventory_contradiction | unknown",
  "required_next_step": "classify | repair | rediscover | rebuild_inventory | regenerate_patchlets"
}
```

---

# Retry policy

Blind retries are forbidden.

Same-prompt retry is allowed only for proven infrastructure failure.

Examples of retry-eligible infrastructure failures:

```text
- Codex CLI process was killed by OS.
- Temporary filesystem write failed but state remains valid.
- Network/API interruption happened before the worker produced any code changes.
- Lock acquisition failed because another valid run was active, and retry policy allows waiting.
```

Examples that are not retry-eligible as blind same-prompt retries:

```text
- Patchlet produced unauthorized diff.
- Patchlet reported FAILED_WITH_EVIDENCE.
- Patchlet reported BLOCKED_WITH_EVIDENCE.
- Report is missing root-cause proof.
- Proof-of-fix did not cover full runtime path.
- Global verification failed.
- Transaction group failed.
```

Those must be classified.

After classification, the system may produce:

```text
- enriched same-file patchlet;
- different-file patchlet;
- repair transaction group;
- partial rediscovery;
- full rediscovery;
- inventory rebuild;
- invariant refinement;
- path mapping correction.
```

---

# MVP strategy

## MVP 1 — Enforcement layer and one-patchlet execution

Build first:

```text
1. Filesystem layout.
2. State machine.
3. JSON schemas.
4. Schema validators.
5. Command runner.
6. Git diff guard.
7. Mock Codex adapter.
8. Real Codex adapter.
9. Patchlet report validator.
10. `cxor run-next` with mock mode.
```

MVP 1 must enforce:

```text
- one allowed product/runtime file per patchlet;
- artifact directory exception;
- no implementation before probe gates;
- required patchlet report;
- diff guard;
- no vague statuses;
- no blind retry;
- state belongs to orchestrator, not Codex.
```

MVP 1 may simplify:

```text
- transaction groups can exist as metadata only;
- repair planner can emit TODO plans;
- graph edges can be low confidence;
- root-cause validation can be semi-automatic.
```

## MVP 2 — End-to-end manual-stage workflow

Add:

```text
- normalize;
- census;
- classify-evidence;
- build-inventory;
- extract-invariants;
- compile-patchlets;
- run-all;
- verify-group;
- verify-global.
```

MVP 2 can complete a master prompt manually by stage commands.

## MVP 3 — Autonomous loop

Add:

```text
- cxor auto;
- classify-failures;
- plan-repair;
- apply-repair;
- rediscover --scope impacted;
- rebuild-inventory --scope impacted;
- regenerate-patchlets;
- automatic global reverify.
```

MVP 3 is the first version that fully satisfies the approved autonomous requirement.

## MVP 4 — Worktree isolation and advanced repair

Add:

```text
- per-patchlet worktrees;
- validated merge;
- stronger transaction-group repair;
- better partial rediscovery;
- schema migrations;
- CI integration;
- dashboard/report rendering.
```

---

# Test strategy

The orchestrator itself must be tested without Codex first.

Use `mock_codex` to simulate outcomes.

## Required test cases

```text
- init creates expected directories and files.
- state writes are atomic.
- lock prevents concurrent mutation.
- census records command metadata.
- codex adapter records run metadata.
- mock Codex COMPLETE report passes validation.
- mock Codex vague status fails validation.
- unauthorized diff is detected.
- authorized artifact files are allowed.
- authorized one product/runtime file is allowed.
- two product/runtime files are rejected.
- missing report is rejected.
- VERIFIED_NO_CHANGE_NEEDED with product diff is rejected.
- COMPLETE without proof-of-fix fields is rejected.
- FAILED_WITH_EVIDENCE routes to failure classification.
- BLOCKED_WITH_EVIDENCE routes to repair planning.
- global verification failure routes to repair planning.
- repair plan can generate repair patchlets.
- `cxor auto` loops through repair and eventually marks DONE in mock scenario.
- `cxor auto` resumes after simulated interruption.
```

## Mock scenario examples

Scenario A:

```text
- one patchlet;
- minimal probe passes;
- no product/runtime diff;
- report status VERIFIED_NO_CHANGE_NEEDED;
- global verifier returns DONE.
```

Scenario B:

```text
- one patchlet;
- root cause proven;
- proof-of-fix proven;
- one allowed file changed;
- report COMPLETE;
- global verifier returns DONE.
```

Scenario C:

```text
- patchlet changes unauthorized file;
- diff guard rejects;
- failure record created;
- repair plan generated;
- repair patchlet generated;
- repair patchlet completes;
- global verifier returns DONE.
```

Scenario D:

```text
- global verifier finds failure outside known graph;
- repair classifier chooses PARTIAL_REDISCOVERY_REQUIRED;
- impacted census runs;
- inventory rebuild runs;
- patchlets regenerate;
- verification eventually returns DONE.
```

---

# CI integration

The orchestrator should support CI-friendly modes.

Useful CI commands:

```bash
cxor validate-state
cxor validate-report P0001
cxor verify-global --read-only
cxor auto --resume --until DONE --worker-mode ci_only
```

CI should not necessarily allow Codex edits unless explicitly configured.

A safe CI flow:

```text
1. Validate state.
2. Validate schemas.
3. Validate reports.
4. Run transaction verifiers.
5. Run global verifier read-only.
6. Fail CI if final state is not DONE.
```

---

# Final acceptance checklist for implementation

## Core architecture

- [ ] Python orchestrator exists.
- [ ] Bash wrapper is thin.
- [ ] `cxor` CLI exists.
- [ ] `cxor auto --master ./master_prompt.md --until DONE` exists.
- [ ] Stage/debug commands exist.
- [ ] Durable state lives under `.codex-orchestrator/`.
- [ ] Probe artifacts live under `.artifacts/probes/`.

## Autonomous behavior

- [ ] `cxor auto` initializes missing workflow state.
- [ ] `cxor auto` resumes existing workflow state.
- [ ] `cxor auto` executes stages in dependency order.
- [ ] `cxor auto` does not stop at `REPAIR_PLANNING_REQUIRED`.
- [ ] `cxor auto` does not stop at `FAILED_WITH_EVIDENCE`.
- [ ] `cxor auto` does not stop at `BLOCKED_WITH_EVIDENCE`.
- [ ] `cxor auto` treats failures as repair inputs.
- [ ] `cxor auto` exits 0 only when state is `DONE`.
- [ ] `cxor auto` can resume after interruption.

## Safety enforcement

- [ ] One product/runtime file per patchlet is enforced.
- [ ] Artifact directory exception is enforced.
- [ ] Unauthorized diffs are rejected.
- [ ] Unauthorized diffs are saved and rolled back or isolated.
- [ ] Patchlet reports are required.
- [ ] Vague statuses are rejected.
- [ ] Blind retries are forbidden.
- [ ] Same-prompt retry is limited to proven infrastructure failure.

## Root-cause/proof enforcement

- [ ] Minimal direct probe is required.
- [ ] Product/runtime implementation is forbidden before proof gate.
- [ ] Root-cause fields are required for COMPLETE.
- [ ] Proof-of-fix fields are required for COMPLETE.
- [ ] Negative controls are required or explicitly blocked with evidence.
- [ ] Cleanup proof is required.
- [ ] Report must distinguish investigation artifacts from implementation diff.

## Verification and repair

- [ ] Transaction verifier exists.
- [ ] Global verifier exists and is read-only.
- [ ] Failure classifier exists.
- [ ] Repair planner exists.
- [ ] Apply-repair exists.
- [ ] Partial rediscovery exists.
- [ ] Full rediscovery exists.
- [ ] Inventory rebuild exists.
- [ ] Patchlet regeneration exists.
- [ ] Repair loops back into verification.

---

# Final corrected implementation principle

The workflow should not be:

```text
run stages manually until something fails
```

It should be:

```bash
cxor auto --master ./master_prompt.md --until DONE
```

Internally:

```text
failure → evidence → classification → repair/replan/rediscover → patchlets → verification → repeat
```

And enforcement should make it impossible for a Codex patchlet to claim completion unless it leaves durable evidence, obeys its allowed-file boundary, satisfies the probe-gated root-cause contract, and passes validation.

---

# Preserved approved implementation plan

The following section preserves the approved implementation-plan reflection without compression.

---



## Review verdict

The document is now strong enough to become an implementation specification. The core architecture is clear: master prompt → goal spec → deterministic repo census → Codex evidence classification → inventory graph/table → invariants → root-cause patchlets → probe-gated execution → transaction/global verification → repair planning. The file also correctly makes **durable repo artifacts** the source of truth instead of chat memory, and explicitly says Codex should be a disposable evidence-bound worker rather than the owner of orchestration state. 

My main implementation recommendation is:

> Build a deterministic Python orchestrator with a thin bash wrapper. Do not implement the core state machine in bash.

Bash is fine for launching commands, but this workflow depends on JSON schemas, state transitions, diff validation, report parsing, retry classification, artifact manifests, and resumability. Those are much safer in Python.

---

# Proposed implementation target

I would implement this as a local CLI tool named:

```text
codex-orchestrator
```

or shorter:

```text
cxor
```

The tool should live inside the repository using the workflow, for example:

```text
tools/codex_orchestrator/
  __init__.py
  cli.py
  config.py
  state.py
  git_guard.py
  command_runner.py
  codex_adapter.py
  schemas/
  stages/
  validators/
  prompt_templates/
```

The durable runtime state should live where your design already expects it:

```text
.codex-orchestrator/
  master_prompt.md
  goal_spec.json
  config.json
  state.json
  run_manifest.json
  census/
  search_evidence.jsonl
  search_evidence.md
  inventory_graph.json
  inventory_table.md
  invariants.json
  path_mapping.json
  patchlets/
  subprompts/
  reports/
  runs/
  failures/
  repair_plans/
  final_verification.md
  final_verification.json

.artifacts/probes/
```

This aligns with the document’s rule that repository-side artifacts are the durable memory and that probe/report/run artifacts are permitted in approved artifact directories. 

---

# Implementation plan

## Phase 1 — Build the orchestrator skeleton first

Do not start by calling Codex.

Start with the external orchestrator: filesystem layout, state handling, schemas, logging, and dry-run execution.

### Deliverables

```text
tools/codex_orchestrator/
  cli.py
  config.py
  state.py
  paths.py
  errors.py
  command_runner.py
  jsonio.py
  schemas/
    goal_spec.schema.json
    evidence.schema.json
    inventory_graph.schema.json
    invariant.schema.json
    patchlet.schema.json
    patchlet_report.schema.json
    state.schema.json
```

### CLI commands

```bash
cxor init --master master_prompt.md
cxor status
cxor validate-state
cxor reset-run
```

### Core responsibilities

The orchestrator must own:

```text
state
retry count
rollback
diff checking
allowed file enforcement
subtask order
failure classification
logs
final status
```

That matches the approved design: Codex should not own global state; the orchestrator should. 

### Acceptance criteria

```text
- .codex-orchestrator/ is created deterministically.
- master_prompt.md is copied into .codex-orchestrator/master_prompt.md.
- state.json is initialized.
- run_manifest.json is initialized.
- All schema files exist.
- cxor status can print the current workflow stage.
- cxor validate-state validates state.json against schema.
- No Codex call is needed yet.
```

---

## Phase 2 — Define the state machine

This is the most important foundation.

The workflow should not be a loose sequence of scripts. It should be a strict state machine.

### Suggested states

```text
INITIALIZED
MASTER_PROMPT_SAVED
GOAL_SPEC_READY
CENSUS_READY
EVIDENCE_READY
INVENTORY_READY
INVARIANTS_READY
PATCHLETS_READY
PATCHLET_EXECUTION_IN_PROGRESS
PATCHLET_EXECUTION_COMPLETE
TRANSACTION_VERIFICATION_READY
TRANSACTION_VERIFICATION_COMPLETE
GLOBAL_VERIFICATION_READY
GLOBAL_VERIFICATION_COMPLETE
REPAIR_PLANNING_REQUIRED
DONE
FAILED
```

### Suggested state file

```json
{
  "workflow_id": "20260702-001",
  "stage": "INITIALIZED",
  "master_prompt_sha256": "...",
  "repo_sha_start": "...",
  "current_patchlet_id": null,
  "attempts": {},
  "completed_patchlets": [],
  "verified_no_change_needed": [],
  "blocked_patchlets": [],
  "failed_patchlets": [],
  "transaction_groups": [],
  "repair_cycles": [],
  "created_at": "...",
  "updated_at": "..."
}
```

### Acceptance criteria

```text
- Every CLI command checks whether the current state allows it to run.
- Invalid transitions fail early.
- The state machine is resumable.
- Running the same completed stage twice either no-ops safely or requires --force.
- State changes are written atomically.
```

This directly supports the document’s requirement that durable files, not chat context, preserve progress across compaction and separate Codex calls. 

---

## Phase 3 — Implement deterministic repository census

This phase must be read-only.

The document explicitly says repository census must use deterministic tools before Codex interpretation and that Codex may classify evidence but must not be the only producer of evidence. 

### CLI command

```bash
cxor census
```

### Outputs

```text
.codex-orchestrator/census/repo_files.txt
.codex-orchestrator/census/git_status.txt
.codex-orchestrator/census/rg_index.jsonl
.codex-orchestrator/census/symbols.json
.codex-orchestrator/census/tests.json
.codex-orchestrator/census/imports.json
.codex-orchestrator/census/routes.json
.codex-orchestrator/census/configs.json
.codex-orchestrator/census/tool_availability.json
```

### Deterministic commands to support

Start with the lowest-friction tools:

```bash
git ls-files
git status --short
rg --files
rg -n "<goal keywords>"
pytest --collect-only
npm test -- --listTests
```

Then add optional integrations:

```bash
ctags
ast-grep
tree-sitter
pydeps
pipdeptree
npm ls
docker compose config
```

### Acceptance criteria

```text
- Census never edits product/runtime code.
- Every command result records command, exit code, stdout path, stderr path, and timestamp.
- Missing tools are recorded as unavailable, not treated as fatal unless configured as required.
- Census outputs are deterministic enough to diff between runs.
```

---

## Phase 4 — Add the Codex worker adapter

Only after the orchestrator and census are stable should you add Codex calls.

### CLI command

```bash
cxor codex-run --prompt-file <file> --output-jsonl <file>
```

### Adapter responsibilities

```text
- Build codex exec command.
- Pass prompt file content.
- Capture stdout/stderr.
- Capture JSONL when supported.
- Record exit code.
- Record repo SHA before and after.
- Record command metadata.
- Support mock mode for testing.
```

### Mock mode is mandatory

Add:

```bash
cxor --mock ...
```

Mock mode lets you test the orchestration logic without spending Codex calls or depending on model behavior.

### Acceptance criteria

```text
- Codex calls are isolated behind one adapter.
- Every Codex call writes a run record under .codex-orchestrator/runs/.
- The orchestrator can be tested without Codex using mock worker outputs.
- Codex output is never trusted until validated by schemas and validators.
```

---

## Phase 5 — Master prompt normalization

The document says the master prompt should not be passed raw into every implementation call; it should first become `goal_spec.json`. 

### CLI command

```bash
cxor normalize
```

### Input

```text
.codex-orchestrator/master_prompt.md
```

### Output

```text
.codex-orchestrator/goal_spec.json
```

### Schema

```json
{
  "master_goal": "string",
  "success_goals": [],
  "target_invariants": [],
  "forbidden_actions": [],
  "runtime_constraints": [],
  "validation_commands": [],
  "allowed_edit_scope": [],
  "must_preserve": [],
  "known_failure_modes": [],
  "proof_requirements": []
}
```

### Acceptance criteria

```text
- goal_spec.json validates against schema.
- Every success goal has an ID.
- Every target invariant has an ID or placeholder.
- Forbidden actions are explicit.
- Proof requirements include root-cause/probe-gated requirements.
```

---

## Phase 6 — Evidence classification

This phase lets Codex classify deterministic census output into the search evidence table.

### CLI command

```bash
cxor classify-evidence
```

### Inputs

```text
.codex-orchestrator/goal_spec.json
.codex-orchestrator/census/
```

### Outputs

```text
.codex-orchestrator/search_evidence.jsonl
.codex-orchestrator/search_evidence.md
```

### Evidence row schema

```json
{
  "evidence_id": "E001",
  "goal_id": "G001",
  "role": "producer | transformer | consumer | adapter | validator | test | config | state_owner | runtime_boundary",
  "file": "path/to/file",
  "symbol": "symbol_name_or_null",
  "line_range": "L10-L50",
  "found_by": "rg | ctags | pytest_collect | route_listing | codex_classification",
  "command_or_source": "...",
  "why_relevant": "...",
  "confidence": "high | medium | low",
  "connected_evidence_ids": []
}
```

### Acceptance criteria

```text
- Every evidence row has a concrete file path unless it is explicitly classified as repo-level/config-level.
- Every evidence row points to a deterministic source where possible.
- Codex classifications without deterministic support are marked low confidence.
- Evidence IDs are stable and unique.
```

---

## Phase 7 — Build inventory graph and inventory table

The document requires both a human-readable inventory table and a machine-readable graph. The graph is the source used to generate patchlets; patchlets should come from graph slices, not free-text intuition. 

### CLI command

```bash
cxor build-inventory
```

### Inputs

```text
goal_spec.json
search_evidence.jsonl
```

### Outputs

```text
inventory_graph.json
inventory_table.md
path_mapping.json
```

### Inventory graph schema

```json
{
  "nodes": [
    {
      "id": "N001",
      "file": "path/to/file",
      "symbol": "symbol_name",
      "role": "producer",
      "evidence_ids": ["E001"],
      "confidence": "high"
    }
  ],
  "edges": [
    {
      "id": "EDGE001",
      "from": "N001",
      "to": "N002",
      "kind": "calls | imports | emits | consumes | transforms | validates | persists | reads | writes",
      "evidence_ids": ["E004"],
      "confidence": "high"
    }
  ]
}
```

### Acceptance criteria

```text
- Every graph node links to evidence IDs.
- Every graph edge links to evidence IDs.
- Low-confidence edges are explicitly marked.
- Inventory table is generated from the graph, not separately invented.
- path_mapping.json traces master goals to graph nodes and edges.
```

---

## Phase 8 — Extract invariants

The document makes the invariant layer critical because local file edits are not enough; the goal is end-to-end correctness across producer, transformer, adapter, consumer, state owner, and runtime signal/event boundaries. 

### CLI command

```bash
cxor extract-invariants
```

### Output

```text
.codex-orchestrator/invariants.json
```

### Invariant schema

```json
{
  "invariant_id": "I001",
  "master_goal_id": "G001",
  "description": "...",
  "producer_nodes": [],
  "transformer_nodes": [],
  "adapter_nodes": [],
  "consumer_nodes": [],
  "state_owner_nodes": [],
  "runtime_signal_or_condition": "...",
  "required_probes": [],
  "negative_controls": [],
  "regression_commands": [],
  "evidence_ids": [],
  "graph_node_ids": [],
  "graph_edge_ids": []
}
```

### Acceptance criteria

```text
- Every invariant links to goal IDs.
- Every invariant links to graph nodes/edges.
- Every invariant names the affected runtime boundary.
- Every invariant has at least one probe requirement or explicit reason why probe generation is blocked.
```

---

## Phase 9 — Compile Root-Cause Patchlets

This is the core decomposition step.

The document defines Root-Cause Patchlets as localized, probe-gated Codex tasks with three defining properties: small scope, root-cause first, and implementation only after proof. It also requires that a patchlet first verifies whether the sub-goal already works at runtime before editing product/runtime code. 

### CLI command

```bash
cxor compile-patchlets
```

### Outputs

```text
.codex-orchestrator/patchlets/patchlet_index.json
.codex-orchestrator/subprompts/0001_<slug>.md
.codex-orchestrator/subprompts/0002_<slug>.md
...
```

### Patchlet manifest schema

```json
{
  "patchlet_id": "P0001",
  "subprompt_path": ".codex-orchestrator/subprompts/0001_service_boundary.md",
  "master_goal_ids": ["G001"],
  "invariant_ids": ["I001"],
  "evidence_ids": ["E001", "E002"],
  "graph_node_ids": ["N001", "N002"],
  "allowed_product_runtime_file": "path/to/file.py",
  "allowed_artifact_dirs": [
    ".artifacts/probes/",
    ".codex-orchestrator/reports/",
    ".codex-orchestrator/runs/"
  ],
  "transaction_group_id": "TG001",
  "depends_on": [],
  "status": "PENDING"
}
```

### Acceptance criteria

```text
- Every patchlet has exactly one allowed product/runtime file.
- Artifact directories are explicitly allowed.
- Each patchlet links to evidence, invariants, and graph nodes.
- Each patchlet includes the required minimal direct runtime probe instruction.
- Each patchlet includes the ROOT-CAUSE PROBE-ONLY INVESTIGATION gate.
- Each patchlet includes proof-of-fix and TDD implementation checklist gates.
```

---

## Phase 10 — Implement the patchlet executor

The patchlet executor is where most mistakes can happen, so this must be strict.

The document says the runner must select the next patchlet, record repo SHA, run Codex, capture output, inspect git diff, enforce allowed file restrictions, permit only approved artifact changes, verify report existence/status, and rollback unauthorized changes. 

### CLI command

```bash
cxor run-next
cxor run-all
cxor resume
```

### Execution algorithm

```text
1. Load state.json.
2. Load patchlet_index.json.
3. Select next PENDING patchlet whose dependencies are satisfied.
4. Record repo SHA before execution.
5. Execute Codex with the patchlet subprompt.
6. Capture stdout/stderr/JSONL into .codex-orchestrator/runs/.
7. Inspect git diff.
8. Check that at most one product/runtime file changed.
9. Check that the changed product/runtime file is the allowed file.
10. Permit artifact changes only under approved directories.
11. Validate report exists.
12. Validate report schema.
13. Classify result.
14. Commit state transition.
15. Continue, stop, repair, or replan.
```

### Diff guard rules

```text
Allowed:
- The one declared product/runtime file.
- .artifacts/probes/**
- .codex-orchestrator/reports/**
- .codex-orchestrator/runs/**

Forbidden:
- Any other product/runtime file.
- Test weakening unless explicitly allowed by patchlet.
- Changes to orchestration source during patchlet execution.
- Changes to master prompt, goal spec, inventory, or invariants during patchlet execution.
```

### Acceptance criteria

```text
- Unauthorized diffs cause immediate failure.
- Unauthorized diffs are rolled back or isolated.
- The patchlet cannot mark itself complete without a valid report.
- Report status must be one of COMPLETE, VERIFIED_NO_CHANGE_NEEDED, BLOCKED_WITH_EVIDENCE, FAILED_WITH_EVIDENCE.
- Blind retries are impossible at executor level.
```

---

## Phase 11 — Implement patchlet report validation

Codex output is not sufficient. The report must be machine-validated.

### CLI command

```bash
cxor validate-report P0001
```

### Patchlet report schema

```json
{
  "patchlet_id": "P0001",
  "status": "COMPLETE | VERIFIED_NO_CHANGE_NEEDED | BLOCKED_WITH_EVIDENCE | FAILED_WITH_EVIDENCE",
  "changed_product_runtime_file": "path/to/file.py|null",
  "changed_artifact_files": [],
  "probe_commands": [],
  "deterministic_run_counts": {
    "baseline": "5/5",
    "proof_of_fix": "5/5",
    "negative_controls": "5/5"
  },
  "root_cause_classification": {
    "observed_failure": "...",
    "immediate_cause": "...",
    "why_immediate_cause_happened": "...",
    "deeper_owner_boundary": "...",
    "producer_transformer_consumer_boundary": "...",
    "not_downstream_of_unprobed_state_proof": "...",
    "negative_control_proof": "..."
  },
  "before_after_state": [],
  "row_ledger": [],
  "trace_ledger": [],
  "cleanup_proof": "...",
  "acceptance_criteria_result": "pass | fail | blocked"
}
```

### Acceptance criteria

```text
- COMPLETE requires implementation evidence and post-implementation probes.
- VERIFIED_NO_CHANGE_NEEDED requires minimal direct probe evidence and no product/runtime diff.
- BLOCKED_WITH_EVIDENCE requires a clear boundary or scope reason.
- FAILED_WITH_EVIDENCE requires failed probe/root-cause/proof-of-fix evidence.
- Reports with vague statuses are rejected.
```

This implements the document’s status model and prevents vague “done / looks good / tests passed” completion. 

---

## Phase 12 — Enforce ROOT-CAUSE PROBE-ONLY rules

This phase converts the root-cause standard into validators.

The standard says no product/runtime code may be edited during investigation, every failure must be investigated, root cause must be proven by direct probes, and proof-of-fix must prove the full affected runtime path. 

### Required validators

```text
validate_no_product_edit_during_investigation
validate_minimal_probe_present
validate_deterministic_reproduction
validate_controlled_initial_state
validate_boundary_identified
validate_recursive_why_audit
validate_root_cause_toggle
validate_negative_controls
validate_proof_of_fix_full_path
validate_no_timing_luck_claim
validate_cleanup_proof
```

### Practical implementation

Some validators can be fully automatic:

```text
- Did report contain required fields?
- Were commands recorded?
- Were artifacts emitted?
- Did changed files stay within scope?
- Was deterministic run count declared?
```

Some validators are semi-automatic:

```text
- Does the root-cause explanation identify producer → transformer → consumer?
- Does the proof-of-fix claim full affected runtime path?
- Are negative controls described?
```

Semi-automatic validators should flag missing evidence and require a verifier Codex call or manual review.

### Acceptance criteria

```text
- A patchlet cannot reach COMPLETE without root-cause/proof-of-fix fields.
- A patchlet cannot edit product/runtime code before proof-of-fix fields exist in the report.
- The report must distinguish investigation artifacts from implementation diffs.
```

---

## Phase 13 — Transaction-group verifier

One-file patchlets can be part of larger transaction groups. The document explicitly warns that intermediate states may be broken while a transaction group is incomplete and says group verification should run after related patchlets complete. 

### CLI command

```bash
cxor verify-group TG001
```

### Transaction group manifest

```json
{
  "transaction_group_id": "TG001",
  "description": "...",
  "patchlet_ids": ["P0001", "P0002", "P0003"],
  "invariant_ids": ["I001"],
  "verification_commands": [],
  "status": "PENDING | PASSED | FAILED | BLOCKED"
}
```

### Acceptance criteria

```text
- Group verifier runs only after all required patchlets are COMPLETE or VERIFIED_NO_CHANGE_NEEDED.
- Group verifier runs targeted integration commands.
- Group failure maps back to invariant IDs and graph nodes.
- Group failure creates repair input, not blind retry.
```

---

## Phase 14 — Global verifier

The final verifier must be read-only and evidence-bound.

### CLI command

```bash
cxor verify-global
```

### Outputs

```text
.codex-orchestrator/final_verification.md
.codex-orchestrator/final_verification.json
```

### Global verifier checks

```text
- Which master goals are proven complete?
- Which invariants are proven?
- Which invariants are unproven?
- Which invariants failed?
- What exact evidence supports each conclusion?
- What probes passed?
- What probes failed?
- What regression commands passed?
- What regression commands failed?
- What files changed?
- Were all changed files allowed by their patchlets?
- Were all failure reports resolved or explicitly classified?
```

Those checks match the document’s global verifier requirements. 

### Acceptance criteria

```text
- Global verifier does not edit product/runtime code.
- Global verifier validates all patchlet reports.
- Global verifier validates transaction groups.
- Global verifier maps final result back to master goals and invariants.
- DONE is allowed only when all required invariants are proven or explicitly marked non-blocking with evidence.
```

---

## Phase 15 — Repair planner

Do not implement blind full restart as the default.

The document says full rediscovery should be reserved for justified cases such as inventory contradiction, failure outside the known graph, repeated repair failure, excessive impacted scope, or master-goal change. 

### CLI command

```bash
cxor plan-repair
```

### Repair classification

```text
INSIDE_KNOWN_GRAPH
OUTSIDE_KNOWN_GRAPH
INVENTORY_CONTRADICTION
REPEATED_REPAIR_FAILURE
MASTER_GOAL_CHANGED
EXCESSIVE_IMPACTED_SCOPE
```

### Repair outputs

```text
.codex-orchestrator/repair_plans/R001.json
.codex-orchestrator/failures/F001.md
```

### Acceptance criteria

```text
- Failures are classified before retry.
- Same-prompt retry is allowed only for proven infrastructure failure.
- Same-file deeper root regenerates enriched same-file patchlet.
- Different-file root creates a new patchlet or blocks with evidence.
- Inventory contradiction triggers partial rediscovery or graph rebuild.
- Full restart is never the first repair action unless master goal changed.
```

---

# Recommended build order

I would not implement the entire system in one pass. Build it in this order:

```text
1. Filesystem layout + state machine
2. JSON schemas + schema validators
3. Deterministic census
4. Codex adapter with mock mode
5. Goal normalization
6. Evidence classification
7. Inventory graph generation
8. Invariant extraction
9. Patchlet compiler
10. Patchlet executor
11. Git diff guard
12. Patchlet report validator
13. Root-cause/proof validators
14. Transaction-group verifier
15. Global verifier
16. Repair planner
```

The first truly useful MVP ends at step 12. At that point you can generate patchlets, run one patchlet, enforce one-file scope, and validate the report.

The second MVP ends at step 15. At that point the system can complete a full master-prompt workflow with group/global verification.

The third MVP ends at step 16. At that point the system can repair rather than simply fail.

---

# Critical design choices

## 1. Python orchestrator, not bash-only

Use bash only as a wrapper:

```bash
#!/usr/bin/env bash
set -euo pipefail
python -m tools.codex_orchestrator.cli "$@"
```

Python should own:

```text
JSON parsing
schemas
state transitions
diff inspection
Codex subprocess execution
report validation
repair planning
```

## 2. Codex adapter must be swappable

Support at least two worker modes:

```text
real_codex
mock_codex
```

Later you can add:

```text
manual
ci_only
```

This lets you test orchestration without model calls.

## 3. Every artifact should be versioned

Add a schema version to every major JSON file:

```json
{
  "schema_version": "1.0",
  "kind": "patchlet_report",
  ...
}
```

Without schema versions, future workflow changes will break older runs.

## 4. Use atomic writes

All state updates should write to a temp file first, then rename.

```text
state.json.tmp → state.json
```

This prevents corrupt state after interrupted runs.

## 5. Use run locks

Add:

```text
.codex-orchestrator/.lock
```

Only one orchestrator run should mutate state at a time.

## 6. Use git worktrees or pre/post SHA guards

The minimum is:

```bash
git rev-parse HEAD
git diff --name-only
```

The stronger design is to run each patchlet in a temporary worktree and merge only after validation.

---

# Concrete MVP scope

The first implementation should deliberately exclude advanced repair planning and fancy graph intelligence.

## MVP 1 should include

```text
cxor init
cxor census
cxor normalize
cxor classify-evidence
cxor build-inventory
cxor extract-invariants
cxor compile-patchlets
cxor run-next
cxor validate-report
cxor status
```

## MVP 1 can simplify

```text
- Transaction groups can exist as metadata but not yet execute complex orchestration.
- Repair planner can emit TODO repair plans but not auto-run them.
- Graph edges can be lower confidence initially.
- Some root-cause validation can be semi-automatic.
```

## MVP 1 must not simplify

```text
- One allowed product/runtime file per patchlet.
- Artifact directory exception.
- No implementation before probe gates.
- Required patchlet report.
- Diff guard.
- No vague statuses.
- No blind retry.
- State belongs to orchestrator, not Codex.
```

Those are the core safety invariants.

---

# Suggested final CLI shape

```bash
# Initialize durable memory
cxor init --master ./master_prompt.md

# Produce goal spec
cxor normalize

# Run deterministic repo census
cxor census

# Use Codex to classify deterministic evidence
cxor classify-evidence

# Build graph/table/path mapping
cxor build-inventory

# Extract invariants
cxor extract-invariants

# Compile root-cause patchlets
cxor compile-patchlets

# Run one patchlet
cxor run-next

# Run all pending patchlets
cxor run-all

# Validate one patchlet report
cxor validate-report P0001

# Verify a transaction group
cxor verify-group TG001

# Verify whole master goal
cxor verify-global

# Plan repair from failures
cxor plan-repair

# Show current state
cxor status
```

---

# My strongest recommendation

Build the **enforcement layer** before the **intelligence layer**.

That means:

```text
First:
- state machine
- schemas
- git diff guard
- report validator
- mock Codex adapter

Then:
- better prompts
- evidence classification
- inventory graph reasoning
- invariant extraction
- repair planning
```

The reason is simple: the workflow’s value comes from preventing unsafe Codex behavior. If the enforcement layer is weak, better prompts will not save the system.

The implementation should make this invariant impossible to bypass:

> A Codex patchlet cannot be marked complete unless it produced a valid report, obeyed the allowed-file boundary, satisfied the probe-gated root-cause contract, and left durable evidence behind.



---

# Preserved approved autonomous correction

The following section preserves the approved correction that added the missing one-shot autonomous driver and corrected the state model so the orchestrator loops until `DONE`.

---



You are right. The CLI shape needs a **top-level autonomous command**.

The individual commands are still necessary, but they are **stage commands**, not the full orchestrator. The missing command should be the command that runs the whole state machine non-interactively until the final state is `DONE`.

The correct addition is:

```bash id="qk5hwc"
cxor auto --master ./master_prompt.md --until DONE
```

or, more explicit:

```bash id="qgmvot"
cxor orchestrate --master ./master_prompt.md --non-interactive --until DONE
```

My preferred name is:

```bash id="j3v1h1"
cxor auto
```

because it is short and clearly means: run the whole workflow automatically.

---

# Corrected CLI shape

The full CLI should now be divided into two categories:

## 1. One-shot autonomous command

```bash id="ov402v"
# Start from a master prompt and keep looping until DONE
cxor auto --master ./master_prompt.md --until DONE
```

Resume an existing workflow:

```bash id="22p6ip"
cxor auto --resume --until DONE
```

Run with no manual confirmation:

```bash id="sgig3d"
cxor auto --master ./master_prompt.md --non-interactive --until DONE
```

Run with automatic repair and replanning:

```bash id="cwfttw"
cxor auto \
  --master ./master_prompt.md \
  --non-interactive \
  --auto-repair \
  --auto-replan \
  --until DONE
```

This is the command that matches your original requirement: **the system keeps running through discovery, patchlets, verification, repair, rediscovery, and replanning until the master goals are proven complete.**

---

## 2. Stage/debug commands

These still exist, but they are lower-level controls:

```bash id="jpxedh"
# Initialize durable memory
cxor init --master ./master_prompt.md

# Produce goal spec
cxor normalize

# Run deterministic repo census
cxor census

# Use Codex to classify deterministic evidence
cxor classify-evidence

# Build graph/table/path mapping
cxor build-inventory

# Extract invariants
cxor extract-invariants

# Compile root-cause patchlets
cxor compile-patchlets

# Run one patchlet
cxor run-next

# Run all pending patchlets
cxor run-all

# Validate one patchlet report
cxor validate-report P0001

# Verify a transaction group
cxor verify-group TG001

# Verify whole master goal
cxor verify-global

# Plan repair from failures
cxor plan-repair

# Show current state
cxor status
```

These commands are useful for inspection, debugging, CI substeps, or manual intervention. But the real orchestration entrypoint is:

```bash id="ynf40v"
cxor auto --master ./master_prompt.md --until DONE
```

---

# Important correction to the state model

You are also right about this:

> no `FAILED`, or `REPAIR_PLANNING_REQUIRED` is allowed to stop the orchestrator since the workflow should keep looping.

So the state model I proposed needs correction.

`FAILED` and `REPAIR_PLANNING_REQUIRED` should **not** be terminal states in autonomous mode.

They should be **internal transition states**.

The only successful terminal state is:

```text id="tqvo8b"
DONE
```

The autonomous runner should treat failures as fuel for the next planning cycle, not as a reason to stop.

This aligns with the approved workflow where global verification failure feeds failures back into repair/replanning and can restart from search when justified. The workflow document describes the loop as discovery → patchlets → verification → repair planner or done, with full rediscovery reserved for inventory contradiction, repeated repair failure, outside-graph failure, excessive impacted scope, or master-goal change. 

---

# Corrected autonomous state machine

Instead of this:

```text id="ffm80j"
DONE
FAILED
REPAIR_PLANNING_REQUIRED
```

Use this:

```text id="4za5j8"
DONE
```

as the only normal terminal state.

Then make these non-terminal loop states:

```text id="o2kgrz"
FAILURE_CLASSIFICATION_REQUIRED
REPAIR_PLANNING_REQUIRED
REPAIR_PLAN_READY
REPAIR_IN_PROGRESS
PARTIAL_REDISCOVERY_REQUIRED
FULL_REDISCOVERY_REQUIRED
PATCHLET_REGENERATION_REQUIRED
GLOBAL_REVERIFY_REQUIRED
```

So the loop becomes:

```text id="4cumgp"
failure
   ↓
classify failure
   ↓
plan repair
   ↓
generate repair patchlets or rediscover
   ↓
run repair patchlets
   ↓
verify again
   ↓
DONE or continue loop
```

---

# Correct behavior of `cxor auto`

The autonomous command should internally run the stage commands in order.

Conceptually:

```text id="cykdfr"
cxor auto --master ./master_prompt.md --until DONE

1. Acquire run lock.
2. Initialize durable memory if needed.
3. Normalize master prompt if goal_spec.json is missing or stale.
4. Run deterministic census if missing or stale.
5. Classify evidence.
6. Build inventory graph/table/path mapping.
7. Extract invariants.
8. Compile root-cause patchlets.
9. Run patchlets until no pending patchlets remain.
10. Verify transaction groups.
11. Verify global master goals.
12. If DONE, stop successfully.
13. If not DONE:
    - classify failures;
    - plan repair;
    - generate repair patchlets;
    - run repair patchlets;
    - verify again.
14. If repair exposes missing evidence:
    - run partial rediscovery;
    - rebuild affected inventory graph region;
    - regenerate affected patchlets;
    - continue.
15. If inventory is contradicted:
    - run full rediscovery;
    - rebuild inventory;
    - regenerate patchlets;
    - continue.
16. Repeat until DONE.
```

This is the missing top-level loop.

---

# Corrected command contract

## `cxor auto`

```bash id="tlgsdy"
cxor auto --master ./master_prompt.md --until DONE
```

### Purpose

Run the full Codex orchestration workflow non-interactively until the master prompt is proven complete.

### It owns

```text id="3h2nr2"
- initialization
- normalization
- deterministic census
- evidence classification
- inventory graph generation
- invariant extraction
- patchlet compilation
- patchlet execution
- patchlet report validation
- transaction-group verification
- global verification
- failure classification
- repair planning
- repair patchlet generation
- partial rediscovery
- full rediscovery when justified
- resume after interruption
```

### It must not stop on

```text id="vpfy4g"
FAILED_WITH_EVIDENCE
BLOCKED_WITH_EVIDENCE
REPAIR_PLANNING_REQUIRED
GLOBAL_VERIFICATION_FAILED
TRANSACTION_GROUP_FAILED
PATCHLET_FAILED
INVENTORY_CONTRADICTION
```

Those become loop inputs.

### It stops successfully only on

```text id="xaz8q4"
DONE
```

---

# Corrected autonomous loop pseudocode

```python id="q4bybb"
def auto(master: str | None, resume: bool, until: str = "DONE") -> int:
    with run_lock(".codex-orchestrator/.lock"):
        state = load_or_initialize_state(master=master, resume=resume)

        while state.stage != "DONE":
            state = refresh_state()

            if needs_init(state):
                run_init(master)

            elif needs_goal_spec(state):
                run_normalize()

            elif needs_census(state):
                run_census()

            elif needs_evidence(state):
                run_classify_evidence()

            elif needs_inventory(state):
                run_build_inventory()

            elif needs_invariants(state):
                run_extract_invariants()

            elif needs_patchlets(state):
                run_compile_patchlets()

            elif has_pending_patchlets(state):
                run_next_patchlet_or_repair_current()

            elif needs_transaction_verification(state):
                run_transaction_verifiers()

            elif needs_global_verification(state):
                result = run_global_verifier()

                if result.done:
                    mark_done()
                    break

                record_global_failures(result)
                mark_repair_planning_required()

            elif needs_failure_classification(state):
                classify_failures()

            elif needs_repair_plan(state):
                plan_repair()

            elif needs_repair_application(state):
                apply_repair_plan()
                # This may generate repair patchlets,
                # trigger partial rediscovery,
                # trigger full rediscovery,
                # or rebuild inventory.

            elif needs_partial_rediscovery(state):
                run_partial_census()
                run_partial_evidence_classification()
                rebuild_impacted_inventory()
                regenerate_impacted_patchlets()

            elif needs_full_rediscovery(state):
                run_census()
                run_classify_evidence()
                run_build_inventory()
                run_extract_invariants()
                run_compile_patchlets()

            else:
                classify_unknown_state_and_plan_repair()

        return 0
```

---

# Corrected failure philosophy

The autonomous runner should not think:

```text id="qeryes"
failure means stop
```

It should think:

```text id="5b5ilu"
failure means produce new evidence for the next loop
```

So these are not terminal:

```text id="uzilj0"
PATCHLET_FAILED
GLOBAL_VERIFICATION_FAILED
REPAIR_PLANNING_REQUIRED
BLOCKED_WITH_EVIDENCE
FAILED_WITH_EVIDENCE
```

They are all evidence-producing states.

The loop should convert them into one of:

```text id="dixfi7"
new repair patchlet
same-file enriched patchlet
different-file patchlet
partial rediscovery
full rediscovery
inventory rebuild
invariant refinement
path mapping correction
```

---

# Required additional commands

To support `cxor auto`, I would add these internal/advanced commands:

```bash id="01gz6z"
# Main autonomous driver
cxor auto --master ./master_prompt.md --until DONE

# Resume autonomous driver
cxor auto --resume --until DONE

# Classify all current failures into repair categories
cxor classify-failures

# Apply the latest repair plan
cxor apply-repair

# Run partial rediscovery for impacted graph nodes/files
cxor rediscover --scope impacted

# Run full rediscovery
cxor rediscover --scope full

# Rebuild only impacted inventory graph sections
cxor rebuild-inventory --scope impacted

# Regenerate patchlets from latest repair plan
cxor regenerate-patchlets --from-repair-plan latest
```

So the expanded CLI becomes:

```bash id="bxxq57"
cxor auto --master ./master_prompt.md --until DONE
cxor auto --resume --until DONE

cxor init --master ./master_prompt.md
cxor normalize
cxor census
cxor classify-evidence
cxor build-inventory
cxor extract-invariants
cxor compile-patchlets

cxor run-next
cxor run-all
cxor validate-report P0001

cxor verify-group TG001
cxor verify-global

cxor classify-failures
cxor plan-repair
cxor apply-repair
cxor rediscover --scope impacted
cxor rediscover --scope full
cxor rebuild-inventory --scope impacted
cxor regenerate-patchlets --from-repair-plan latest

cxor status
cxor validate-state
```

---

# Important implementation detail: repair is not optional in auto mode

In manual mode, this is acceptable:

```bash id="y5hl1m"
cxor verify-global
cxor plan-repair
```

But in auto mode, this is not enough.

In auto mode:

```text id="v9jz51"
verify-global fails
   ↓
classify-failures
   ↓
plan-repair
   ↓
apply-repair
   ↓
continue loop
```

So `plan-repair` is only a planning step. The missing companion is:

```bash id="orz7gm"
cxor apply-repair
```

Without `apply-repair`, the system can identify repairs but cannot keep looping.

---

# Corrected autonomous flow

```text id="gygesk"
cxor auto --master ./master_prompt.md --until DONE
   ↓
init
   ↓
normalize
   ↓
census
   ↓
classify-evidence
   ↓
build-inventory
   ↓
extract-invariants
   ↓
compile-patchlets
   ↓
run-all patchlets
   ↓
verify-groups
   ↓
verify-global
   ↓
DONE?
   ├── yes
   │     ↓
   │   exit 0
   │
   └── no
         ↓
      classify-failures
         ↓
      plan-repair
         ↓
      apply-repair
         ↓
      needed action?
         ├── repair patchlets
         │     ↓
         │   run repair patchlets
         │
         ├── partial rediscovery
         │     ↓
         │   rediscover impacted scope
         │     ↓
         │   rebuild impacted inventory
         │     ↓
         │   regenerate impacted patchlets
         │
         ├── full rediscovery
         │     ↓
         │   census
         │     ↓
         │   classify-evidence
         │     ↓
         │   build-inventory
         │     ↓
         │   extract-invariants
         │     ↓
         │   compile-patchlets
         │
         └── invariant/path correction
               ↓
             regenerate patchlets
         ↓
      verify again
         ↓
      loop until DONE
```

---

# Updated state list

Replace the old terminal-style state list with this:

```text id="cauj5w"
INITIALIZED
MASTER_PROMPT_SAVED
GOAL_SPEC_REQUIRED
GOAL_SPEC_READY
CENSUS_REQUIRED
CENSUS_READY
EVIDENCE_CLASSIFICATION_REQUIRED
EVIDENCE_READY
INVENTORY_BUILD_REQUIRED
INVENTORY_READY
INVARIANT_EXTRACTION_REQUIRED
INVARIANTS_READY
PATCHLET_COMPILATION_REQUIRED
PATCHLETS_READY
PATCHLET_EXECUTION_IN_PROGRESS
PATCHLET_EXECUTION_COMPLETE
TRANSACTION_VERIFICATION_REQUIRED
TRANSACTION_VERIFICATION_COMPLETE
GLOBAL_VERIFICATION_REQUIRED
GLOBAL_VERIFICATION_COMPLETE
FAILURE_CLASSIFICATION_REQUIRED
REPAIR_PLANNING_REQUIRED
REPAIR_PLAN_READY
REPAIR_APPLICATION_REQUIRED
REPAIR_IN_PROGRESS
PARTIAL_REDISCOVERY_REQUIRED
FULL_REDISCOVERY_REQUIRED
INVENTORY_REBUILD_REQUIRED
PATCHLET_REGENERATION_REQUIRED
GLOBAL_REVERIFY_REQUIRED
DONE
```

Do **not** include `FAILED` as a normal terminal state.

If you keep an emergency state, it should be something like:

```text id="v0gurr"
ORCHESTRATOR_ABORTED
```

But that should mean the orchestrator itself cannot safely continue because of something like corrupted state, missing repository, invalid permissions, or user interrupt. It should not mean the Codex task failed.

---

# Updated final CLI recommendation

The final CLI shape should be:

```bash id="rpa6k3"
# One-command non-interactive autonomous workflow
cxor auto --master ./master_prompt.md --until DONE

# Resume the same autonomous workflow after interruption
cxor auto --resume --until DONE

# Optional: run with explicit continuous repair/replanning
cxor auto \
  --master ./master_prompt.md \
  --non-interactive \
  --auto-repair \
  --auto-replan \
  --auto-rediscover \
  --until DONE
```

The shorter default should imply all of those:

```bash id="kh6j04"
cxor auto --master ./master_prompt.md --until DONE
```

Meaning:

```text id="1la22i"
--non-interactive
--auto-repair
--auto-replan
--auto-rediscover
```

---

# Correction to the implementation plan

Add a new phase before the final CLI section:

## Phase 16 — Autonomous driver

### CLI command

```bash id="p4lckr"
cxor auto --master ./master_prompt.md --until DONE
```

### Purpose

Run the full orchestration loop non-interactively until the final verifier proves all master goals and target invariants.

### Responsibilities

```text id="hdn6wy"
- Initialize missing workflow state.
- Resume existing workflow state.
- Execute all required stages in dependency order.
- Run patchlets.
- Validate patchlet reports.
- Run transaction verifiers.
- Run global verifier.
- Convert verification failures into repair plans.
- Apply repair plans.
- Trigger partial or full rediscovery when justified.
- Regenerate patchlets.
- Continue until DONE.
```

### Acceptance criteria

```text id="7bncbn"
- The command does not stop at REPAIR_PLANNING_REQUIRED.
- The command does not stop at FAILED_WITH_EVIDENCE.
- The command does not stop at BLOCKED_WITH_EVIDENCE.
- The command treats those states as inputs to repair/replanning.
- The command exits 0 only when state is DONE.
- Every loop iteration writes durable state and run records.
- The command can resume after interruption.
```

---

# Final corrected principle

The workflow should not be:

```text id="4qq4v3"
run stages manually until something fails
```

It should be:

```text id="lzzioh"
cxor auto --master ./master_prompt.md --until DONE
```

And internally:

```text id="lke1wz"
failure → evidence → classification → repair/replan/rediscover → patchlets → verification → repeat
```

So yes: the missing command is the most important command.

The final one-command entrypoint is:

```bash id="b1075l"
cxor auto --master ./master_prompt.md --until DONE
```

---

# Approved update — standalone installable orchestrator CLI and separate orchestrator Git repository

Status: Approved implementation-plan correction  
Purpose: Update the implementation plan so the Codex orchestrator is not implemented as repo-local code inside every target repository. The orchestrator must be a standalone installable CLI package with its own Git repository. After installation, the CLI must be callable from anywhere and must operate on whichever target repository is selected by `--repo` or by current-working-directory Git-root discovery.  
Scope of this update: packaging, installation, target-repo resolution, standalone orchestrator repository layout, target-repo artifact ownership, global and target-local configuration, corrected CLI contracts, target-repo safety guards, updated build order, and the interaction between the standalone installed CLI and the existing autonomous `cxor auto --until DONE` loop.

This update does not remove or weaken any previous approved requirements. It adds a deployment and repository-boundary layer around the existing autonomous root-cause probe-gated orchestrator.

The existing autonomous workflow remains correct:

```text
failure → evidence → classification → repair/replan/rediscover → patchlets → verification → repeat until DONE
```

The correction is that the code implementing this loop must live in a separate installed package, while the durable workflow artifacts must live in the target repository.

The corrected high-level model is:

```text
codex-orchestrator/                    # independent orchestrator source repository
  pyproject.toml
  src/codex_orchestrator/
  tests/
  docs/

any-target-repo/                       # repository being operated on
  .codex-orchestrator/                 # durable workflow artifacts created by cxor
  .artifacts/probes/                   # durable probe artifacts created by cxor/Codex patchlets
```

The installed CLI owns orchestration behavior.  
The target repository owns workflow artifacts, product/runtime code, probes, reports, run logs, failures, repair plans, and final verification results.

---

## Superseding correction to the earlier repo-local implementation assumption

Earlier sections of this implementation plan describe a repo-local layout like:

```text
target-repo/
  tools/codex_orchestrator/
    cli.py
    state.py
    git_guard.py
    ...
```

That layout is now deprecated.

The corrected implementation must not require each target repository to copy, vendor, or contain the orchestrator source code. The orchestrator should not be implemented as a `tools/codex_orchestrator/` directory inside the target repo.

The corrected implementation must use this boundary:

```text
orchestrator repo
  owns: CLI source, packaging, tests, docs, schemas, templates, validators, stage code

target repo
  owns: .codex-orchestrator/, .artifacts/probes/, product/runtime code, workflow state, probes, reports, repair plans
```

This separation matters because the previous repo-local layout creates avoidable problems:

```text
- every target repository would need a copied orchestrator implementation;
- different target repositories could drift to different orchestrator versions;
- upgrading the orchestrator would require editing target repos;
- orchestrator source changes could be confused with product/runtime code changes;
- patchlet diff guards would have to distinguish orchestrator code from product code inside the same repo;
- the autonomous runner could accidentally mutate its own implementation while attempting to operate on the target project;
- CI installation and reproducibility would be weaker;
- users could not install once and run from anywhere.
```

The standalone-installable model avoids these problems.

---

# Preserved approved correction text

The following approved correction is preserved without compression. It is included as source material for this update and should be treated as part of the implementation plan.

Approved correction. The implementation plan should be changed from:

```text
target-repo/
  tools/codex_orchestrator/
```

to:

```text
codex-orchestrator/        # its own independent Git repo
  src/codex_orchestrator/
  pyproject.toml
  tests/
  docs/

any-target-repo/
  .codex-orchestrator/     # workflow artifacts created by installed CLI
  .artifacts/probes/
```

The previous plan made the orchestrator live inside the target repository as `tools/codex_orchestrator/` . That should be replaced. The orchestrator should be a **standalone installable CLI package** that can be called from anywhere, while still writing durable workflow artifacts into the repo it is operating on.

---

# Corrected architecture

## Old model

```text
target-repo/
  tools/codex_orchestrator/
    cli.py
    state.py
    git_guard.py
    ...
  .codex-orchestrator/
  .artifacts/probes/
```

This is too repo-local.

It means every target project must copy or vendor the orchestrator code. That creates version drift, makes upgrades harder, and mixes orchestrator source code with the target project’s product/runtime code.

---

## New model

```text
codex-orchestrator/                  # standalone orchestrator repo
  pyproject.toml
  README.md
  LICENSE
  src/
    codex_orchestrator/
      __init__.py
      cli.py
      config.py
      state.py
      target_repo.py
      git_guard.py
      command_runner.py
      codex_adapter.py
      schemas/
      stages/
      validators/
      prompt_templates/
  tests/
  docs/

target-repo/                         # any repo being worked on
  .codex-orchestrator/
    master_prompt.md
    goal_spec.json
    state.json
    run_manifest.json
    census/
    search_evidence.jsonl
    inventory_graph.json
    invariants.json
    patchlets/
    subprompts/
    reports/
    runs/
    failures/
    repair_plans/
    final_verification.json

  .artifacts/
    probes/
```

The installed CLI owns the orchestration code.
The target repo owns the workflow artifacts.

That preserves the earlier durable-memory rule: progress, evidence, reports, probes, failures, and verification results still live inside the target repo, not in chat memory. The implementation plan already required durable files such as `.codex-orchestrator/state.json`, `run_manifest.json`, reports, runs, repair plans, and final verification outputs .

---

# New core principle

Add this to the implementation plan:

> The orchestrator must be an installable standalone CLI package with its own Git repository. It must not be copied into each target repository as local project code. When invoked from any target repository, it discovers or receives the target repo path, creates `.codex-orchestrator/` and `.artifacts/probes/` inside that target repo, and then runs the durable workflow there.

---

# Installation model

The orchestrator should be installable as a CLI.

Recommended command names:

```bash
cxor
```

and optionally:

```bash
codex-orchestrator
```

Both can point to the same entrypoint.

## Install from local clone

```bash
git clone <orchestrator-git-url> codex-orchestrator
cd codex-orchestrator
pip install -e .
```

Then from any repo:

```bash
cd /path/to/target-repo
cxor auto --master ./master_prompt.md --until DONE
```

## Install with pipx

```bash
pipx install git+<orchestrator-git-url>
```

Then from any repo:

```bash
cxor status
cxor auto --master ./master_prompt.md --until DONE
```

## Install from package registry later

```bash
pip install codex-orchestrator
```

or:

```bash
pipx install codex-orchestrator
```

---

# Target repo selection

The CLI must always know which repository it is operating on.

Support three modes.

## 1. Current working directory mode

```bash
cd /path/to/target-repo
cxor auto --master ./master_prompt.md --until DONE
```

In this mode, `cxor` discovers the Git root from the current directory.

Equivalent internal behavior:

```bash
git rev-parse --show-toplevel
```

## 2. Explicit repo mode

```bash
cxor auto \
  --repo /path/to/target-repo \
  --master /path/to/master_prompt.md \
  --until DONE
```

This is useful for CI, scripts, and running from outside the target repo.

## 3. Resume mode

```bash
cxor auto --repo /path/to/target-repo --resume --until DONE
```

This resumes the workflow from:

```text
/path/to/target-repo/.codex-orchestrator/state.json
```

---

# Corrected CLI contract

The one-shot autonomous command becomes:

```bash
cxor auto --repo /path/to/target-repo --master ./master_prompt.md --until DONE
```

But `--repo` should be optional if the user is already inside the target repo:

```bash
cd /path/to/target-repo
cxor auto --master ./master_prompt.md --until DONE
```

The autonomous command still does what we approved earlier: it keeps looping through discovery, patchlets, verification, repair, rediscovery, and replanning until `DONE`. It must not stop at `FAILED_WITH_EVIDENCE`, `BLOCKED_WITH_EVIDENCE`, `REPAIR_PLANNING_REQUIRED`, `GLOBAL_VERIFICATION_FAILED`, or inventory contradiction; those are loop inputs, not terminal states .

---

# Revised command list

## Global/install commands

These operate on the installed orchestrator itself:

```bash
cxor --version
cxor doctor
cxor doctor --repo /path/to/target-repo
cxor config show
cxor config set <key> <value>
```

## Target-repo workflow commands

These operate on the selected target repo:

```bash
cxor init --repo /path/to/target-repo --master ./master_prompt.md
cxor auto --repo /path/to/target-repo --master ./master_prompt.md --until DONE
cxor auto --repo /path/to/target-repo --resume --until DONE

cxor normalize --repo /path/to/target-repo
cxor census --repo /path/to/target-repo
cxor classify-evidence --repo /path/to/target-repo
cxor build-inventory --repo /path/to/target-repo
cxor extract-invariants --repo /path/to/target-repo
cxor compile-patchlets --repo /path/to/target-repo

cxor run-next --repo /path/to/target-repo
cxor run-all --repo /path/to/target-repo
cxor validate-report P0001 --repo /path/to/target-repo

cxor verify-group TG001 --repo /path/to/target-repo
cxor verify-global --repo /path/to/target-repo

cxor classify-failures --repo /path/to/target-repo
cxor plan-repair --repo /path/to/target-repo
cxor apply-repair --repo /path/to/target-repo
cxor rediscover --repo /path/to/target-repo --scope impacted
cxor rediscover --repo /path/to/target-repo --scope full
cxor rebuild-inventory --repo /path/to/target-repo --scope impacted
cxor regenerate-patchlets --repo /path/to/target-repo --from-repair-plan latest

cxor status --repo /path/to/target-repo
cxor validate-state --repo /path/to/target-repo
```

When `--repo` is omitted, the CLI uses the current Git root.

---

# New repository layout for the orchestrator repo

The orchestrator’s own Git repo should look like this:

```text
codex-orchestrator/
  pyproject.toml
  README.md
  LICENSE
  CHANGELOG.md
  .gitignore

  src/
    codex_orchestrator/
      __init__.py
      __main__.py
      cli.py

      app.py
      config.py
      constants.py
      errors.py
      logging_setup.py

      target_repo.py
      paths.py
      git_guard.py
      locks.py
      atomic_io.py
      jsonio.py
      command_runner.py

      codex_adapter.py
      workers/
        base.py
        codex_exec.py
        mock.py
        manual.py

      schemas/
        goal_spec.schema.json
        evidence.schema.json
        inventory_graph.schema.json
        invariant.schema.json
        patchlet.schema.json
        patchlet_report.schema.json
        state.schema.json
        repair_plan.schema.json
        final_verification.schema.json

      stages/
        init.py
        normalize.py
        census.py
        classify_evidence.py
        build_inventory.py
        extract_invariants.py
        compile_patchlets.py
        run_patchlet.py
        validate_report.py
        verify_group.py
        verify_global.py
        classify_failures.py
        plan_repair.py
        apply_repair.py
        rediscover.py
        rebuild_inventory.py
        regenerate_patchlets.py
        auto.py

      validators/
        state_validator.py
        schema_validator.py
        diff_validator.py
        report_validator.py
        root_cause_validator.py
        proof_of_fix_validator.py
        artifact_validator.py

      prompt_templates/
        normalize_master_prompt.md
        classify_evidence.md
        build_inventory.md
        extract_invariants.md
        compile_patchlet.md
        root_cause_patchlet.md
        verify_global.md
        plan_repair.md

      templates/
        target_repo/
          codex_orchestrator_config.toml
          gitignore_snippet.txt

  tests/
    unit/
    integration/
    fixtures/
      fake_target_repo/
      fake_codex_outputs/

  docs/
    installation.md
    cli.md
    target_repo_artifacts.md
    autonomous_loop.md
    root_cause_patchlets.md
```

---

# Packaging entrypoint

Use `pyproject.toml` with console scripts.

```toml
[project]
name = "codex-orchestrator"
version = "0.1.0"
description = "Probe-gated root-cause Codex orchestration CLI"
requires-python = ">=3.11"
dependencies = [
  "typer",
  "rich",
  "pydantic",
  "jsonschema",
]

[project.scripts]
cxor = "codex_orchestrator.cli:main"
codex-orchestrator = "codex_orchestrator.cli:main"
```

This gives the user global commands:

```bash
cxor
codex-orchestrator
```

from any directory after installation.

---

# Target repo artifact model

When called inside a target repo, the installed orchestrator creates:

```text
target-repo/
  .codex-orchestrator/
  .artifacts/probes/
```

The orchestrator source code does **not** get copied into the target repo.

The target repo receives only:

```text
- workflow state
- master prompt copy
- normalized goal spec
- deterministic census outputs
- evidence tables
- inventory graph/table
- invariants
- patchlet prompts
- reports
- run logs
- failure records
- repair plans
- verification outputs
- durable probes
```

This keeps the target repo clean and makes the orchestration reproducible.

---

# Target repo config

Add a target-local config file:

```text
.codex-orchestrator/config.toml
```

Example:

```toml
[repo]
root = "."
name = "target-repo"

[artifacts]
workflow_dir = ".codex-orchestrator"
probe_dir = ".artifacts/probes"

[worker]
mode = "real_codex"
codex_binary = "codex"
default_model = "default"

[execution]
non_interactive = true
auto_repair = true
auto_replan = true
auto_rediscover = true
until = "DONE"
max_patchlet_attempts = 3

[git]
require_clean_start = true
use_worktrees = false
rollback_unauthorized_diffs = true

[commands]
test = ""
lint = ""
typecheck = ""
```

Config precedence should be:

```text
CLI flags
→ environment variables
→ target repo .codex-orchestrator/config.toml
→ user global config
→ orchestrator defaults
```

Possible global config:

```text
~/.config/codex-orchestrator/config.toml
```

---

# Corrected Phase 1

Replace the old Phase 1.

## Old Phase 1

```text
tools/codex_orchestrator/
  cli.py
  config.py
  state.py
  ...
```

## New Phase 1 — Create standalone installable orchestrator repo

### Deliverables

```text
codex-orchestrator/
  pyproject.toml
  src/codex_orchestrator/
  tests/
  docs/
```

### CLI commands

```bash
cxor --version
cxor doctor
cxor init --repo /path/to/target-repo --master ./master_prompt.md
cxor status --repo /path/to/target-repo
```

### Acceptance criteria

```text
- The orchestrator has its own Git repo.
- The package installs with pip or pipx.
- The `cxor` command is available globally after installation.
- `cxor --version` works from any directory.
- `cxor doctor` checks Python version, Git, Codex CLI availability, and target repo validity.
- `cxor init --repo <repo> --master <file>` creates target repo artifacts.
- No orchestrator source code is copied into the target repo.
```

---

# New target repo resolver

Add a module:

```text
src/codex_orchestrator/target_repo.py
```

It should resolve target repo with this logic:

```text
1. If --repo is provided:
   - resolve absolute path;
   - verify it exists;
   - verify it is a Git repository or fail unless --allow-non-git is set.

2. Else:
   - run git rev-parse --show-toplevel from current working directory;
   - use that as target repo root.

3. If neither works:
   - fail with clear error:
     "No target repository found. Run inside a Git repo or pass --repo /path/to/repo."

4. Once resolved:
   - all artifact paths are created relative to target repo root;
   - all subprocess commands run with cwd = target repo root unless explicitly overridden.
```

This is essential. Without it, an installed global CLI could accidentally write `.codex-orchestrator/` into the wrong directory.

---

# New safety rule: never mutate the orchestrator repo when operating on a target repo

Add this rule:

> Runtime workflow artifacts must always be written to the target repo, never to the installed orchestrator package directory. The orchestrator repo contains only the orchestrator source code, tests, docs, and release files.

Also add a guard:

```text
If target repo path == orchestrator source repo path:
  allow only when explicitly confirmed with --allow-self-target
```

This prevents accidentally running the orchestrator on itself unless intended.

---

# New install and usage examples

## Install once

```bash
git clone <orchestrator-git-url> ~/src/codex-orchestrator
cd ~/src/codex-orchestrator
pipx install .
```

## Use from a target repo

```bash
cd ~/work/my-target-project
cxor auto --master ./master_prompt.md --until DONE
```

## Use from anywhere

```bash
cxor auto \
  --repo ~/work/my-target-project \
  --master ~/prompts/my-target-project-master.md \
  --until DONE
```

## Resume later

```bash
cxor auto --repo ~/work/my-target-project --resume --until DONE
```

## Inspect status

```bash
cxor status --repo ~/work/my-target-project
```

---

# Updated autonomous command

The final command should now be:

```bash
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE
```

with the convenient short form:

```bash
cd /path/to/target-repo
cxor auto --master ./master_prompt.md --until DONE
```

This preserves the approved autonomous loop while making the CLI globally installable. The earlier approved loop said `cxor auto` must own initialization, normalization, census, evidence classification, inventory generation, invariant extraction, patchlet execution, validation, transaction/global verification, repair planning, rediscovery, and resume behavior . That still holds. The only correction is that `cxor auto` now resolves a target repo first.

---

# Updated build order

The build order should change to this:

```text
1. Create standalone orchestrator Git repo.
2. Add pyproject.toml and console script entrypoints.
3. Implement global CLI shell: cxor --version, cxor doctor.
4. Implement target repo resolver: --repo or current Git root.
5. Implement target artifact path manager.
6. Implement target repo init.
7. Implement global config + target config.
8. Implement state machine and schemas.
9. Implement deterministic census in target repo.
10. Implement Codex adapter with target repo cwd.
11. Implement goal normalization.
12. Implement evidence classification.
13. Implement inventory graph generation.
14. Implement invariant extraction.
15. Implement patchlet compiler.
16. Implement patchlet executor with target repo diff guard.
17. Implement patchlet report validation.
18. Implement root-cause/proof validators.
19. Implement transaction-group verifier.
20. Implement global verifier.
21. Implement repair planner.
22. Implement autonomous `cxor auto` loop.
23. Add install docs and release workflow.
```

The enforcement layer still comes before the intelligence layer, but now installation and target repo resolution come before everything else.

---

# Key correction to preserve

The orchestrator has **two separate repos/locations**:

```text
1. Orchestrator repo
   Owns the CLI source code.

2. Target repo
   Owns workflow artifacts and product/runtime code.
```

The installed CLI acts on the target repo but is not stored inside the target repo.

This is the corrected architecture.

---

# Expanded implementation details for the standalone installable CLI model

The approved correction above establishes the deployment model. This expanded section turns that correction into concrete implementation requirements.

The orchestrator has two different filesystem contexts at runtime:

```text
1. The installed orchestrator package context
   This contains the Python package code, schemas, bundled prompt templates, default config templates, and package metadata.

2. The selected target repository context
   This contains the product/runtime code and the durable workflow artifact directories created by the orchestrator.
```

All workflow mutations must happen in the selected target repository context.

No workflow stage should assume the current Python file location is the repository being operated on.

No workflow stage should write `.codex-orchestrator/` relative to the installed package path.

No workflow stage should run `git` commands in the installed package directory unless the user explicitly targets the orchestrator repository itself.

Every stage must receive or derive a `TargetRepoContext` object and use that object for paths, subprocess working directories, git operations, artifact writes, and diff validation.

---

## New implementation invariant: installed code is separate from target state

Add this implementation invariant to the plan:

> The orchestrator must be installable once and usable from any shell location. It must resolve a target repository for each workflow command, create workflow artifacts inside that target repository, run target-repository commands with the target repository as `cwd`, and never copy orchestrator source code into the target repository.

This invariant applies to every command:

```text
cxor init
cxor auto
cxor normalize
cxor census
cxor classify-evidence
cxor build-inventory
cxor extract-invariants
cxor compile-patchlets
cxor run-next
cxor run-all
cxor validate-report
cxor verify-group
cxor verify-global
cxor classify-failures
cxor plan-repair
cxor apply-repair
cxor rediscover
cxor rebuild-inventory
cxor regenerate-patchlets
cxor status
cxor validate-state
cxor doctor
```

Each command must operate on a resolved target repository, except purely global commands such as:

```text
cxor --version
cxor config show
cxor config set
cxor doctor            # may run without target repo, but should include target checks when --repo is provided or cwd is a repo
```

---

# Standalone orchestrator repository implementation plan

## Repository purpose

The orchestrator repository is the product repository for the orchestration tool itself.

It should be possible to clone it, install it, test it, version it, release it, and upgrade it independently of any target repository.

The orchestrator repository should include:

```text
- Python package source;
- CLI entrypoints;
- schemas;
- validators;
- stage implementations;
- worker adapters;
- prompt templates;
- target-repo artifact templates;
- tests with fake target repositories;
- documentation;
- packaging metadata;
- release notes;
- CI configuration.
```

It should not include target-project-specific workflow outputs except test fixtures.

---

## Standalone orchestrator repository layout

The orchestrator repository should use a modern `src/` layout:

```text
codex-orchestrator/
  pyproject.toml
  README.md
  LICENSE
  CHANGELOG.md
  .gitignore
  .editorconfig
  .python-version

  src/
    codex_orchestrator/
      __init__.py
      __main__.py
      cli.py

      app.py
      config.py
      constants.py
      errors.py
      logging_setup.py
      version.py

      target_repo.py
      paths.py
      git_guard.py
      locks.py
      atomic_io.py
      jsonio.py
      command_runner.py
      run_records.py
      state.py
      state_machine.py
      artifact_manifest.py

      codex_adapter.py
      workers/
        __init__.py
        base.py
        codex_exec.py
        mock.py
        manual.py
        ci_only.py

      schemas/
        goal_spec.schema.json
        evidence.schema.json
        inventory_graph.schema.json
        invariant.schema.json
        patchlet.schema.json
        patchlet_index.schema.json
        patchlet_report.schema.json
        transaction_group.schema.json
        state.schema.json
        repair_plan.schema.json
        failure_record.schema.json
        final_verification.schema.json
        run_record.schema.json
        target_config.schema.json

      stages/
        __init__.py
        init.py
        normalize.py
        census.py
        classify_evidence.py
        build_inventory.py
        extract_invariants.py
        compile_patchlets.py
        run_patchlet.py
        validate_report.py
        verify_group.py
        verify_global.py
        classify_failures.py
        plan_repair.py
        apply_repair.py
        rediscover.py
        rebuild_inventory.py
        regenerate_patchlets.py
        auto.py
        doctor.py

      validators/
        __init__.py
        state_validator.py
        schema_validator.py
        diff_validator.py
        report_validator.py
        root_cause_validator.py
        proof_of_fix_validator.py
        artifact_validator.py
        target_repo_validator.py
        command_result_validator.py
        final_verification_validator.py

      prompt_templates/
        normalize_master_prompt.md
        classify_evidence.md
        build_inventory.md
        extract_invariants.md
        compile_patchlet.md
        root_cause_patchlet.md
        verify_group.md
        verify_global.md
        classify_failures.md
        plan_repair.md
        apply_repair.md

      templates/
        target_repo/
          codex_orchestrator_config.toml
          gitignore_snippet.txt
          README.codex-orchestrator-artifacts.md

  tests/
    unit/
      test_target_repo_resolver.py
      test_paths.py
      test_state_machine.py
      test_atomic_io.py
      test_git_guard.py
      test_config_precedence.py
      test_cli_parsing.py
      test_diff_validator.py
      test_report_validator.py
      test_auto_state_loop.py

    integration/
      test_init_target_repo.py
      test_census_fake_repo.py
      test_mock_auto_until_done.py
      test_resume_existing_workflow.py
      test_apply_repair_loop.py
      test_prevent_wrong_repo_writes.py
      test_self_target_guard.py

    fixtures/
      fake_target_repo/
      fake_target_repo_with_failures/
      fake_codex_outputs/
      fake_patchlet_reports/
      fake_repair_plans/

  docs/
    installation.md
    cli.md
    target_repo_artifacts.md
    target_repo_resolution.md
    autonomous_loop.md
    root_cause_patchlets.md
    repair_planning.md
    configuration.md
    release.md
```

This layout ensures the orchestrator implementation has a clean lifecycle independent from target projects.

---

## Packaging requirements

Use `pyproject.toml` as the package source of truth.

The first implementation can use `setuptools`, `hatchling`, or another standard backend. The exact backend is less important than having stable console scripts and a reproducible install process.

Recommended initial `pyproject.toml` shape:

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "codex-orchestrator"
version = "0.1.0"
description = "Probe-gated root-cause Codex orchestration CLI"
readme = "README.md"
requires-python = ">=3.11"
license = {text = "MIT"}
authors = [
  {name = "Codex Orchestrator Maintainers"}
]
dependencies = [
  "typer>=0.12",
  "rich>=13",
  "pydantic>=2",
  "jsonschema>=4",
  "tomli>=2; python_version < '3.11'"
]

[project.optional-dependencies]
dev = [
  "pytest",
  "pytest-cov",
  "ruff",
  "mypy",
  "build",
  "twine"
]

[project.scripts]
cxor = "codex_orchestrator.cli:main"
codex-orchestrator = "codex_orchestrator.cli:main"
```

Acceptance criteria:

```text
- `pip install -e .` exposes `cxor` and `codex-orchestrator`.
- `pipx install .` exposes `cxor` and `codex-orchestrator` globally.
- `python -m codex_orchestrator --version` works.
- `cxor --version` works outside the orchestrator repository.
- The package can load bundled schemas and templates from installed package resources.
- The package does not rely on relative paths from the current working directory to find its own templates.
```

---

## Console-script entrypoints

Both commands should point to the same CLI application:

```text
cxor
codex-orchestrator
```

`cxor` is the preferred daily command.

`codex-orchestrator` is the explicit descriptive alias.

The CLI should support:

```bash
cxor --version
codex-orchestrator --version
python -m codex_orchestrator --version
```

The module entrypoint should be:

```python
# src/codex_orchestrator/__main__.py
from codex_orchestrator.cli import main

if __name__ == "__main__":
    main()
```

---

# Target repository resolution

## TargetRepoContext object

All workflow commands should resolve a target repo into a structured object before doing anything else.

Recommended dataclass shape:

```python
@dataclass(frozen=True)
class TargetRepoContext:
    root: Path
    workflow_dir: Path
    probe_dir: Path
    config_path: Path
    state_path: Path
    run_manifest_path: Path
    git_root: Path | None
    is_git_repo: bool
    allow_non_git: bool
    allow_self_target: bool
```

Every stage should accept this context instead of recomputing paths.

---

## Target repo resolver algorithm

The `target_repo.py` module should implement this logic:

```text
1. If --repo is provided:
   1. Resolve it to an absolute path.
   2. Verify that the path exists.
   3. Verify that the path is a directory.
   4. Verify that it is a Git repository unless --allow-non-git is set.
   5. If it is a subdirectory of a Git worktree, resolve the Git root unless --repo-exact is set.

2. If --repo is not provided:
   1. Start from current working directory.
   2. Run `git rev-parse --show-toplevel`.
   3. Use the returned Git root as target repo root.
   4. If Git root cannot be resolved, fail unless --allow-non-git is set.

3. If target cannot be resolved:
   Fail with a clear actionable message:
   "No target repository found. Run inside a Git repository or pass --repo /path/to/repo."

4. Once target is resolved:
   1. Set all artifact paths relative to target root.
   2. Run target commands with cwd = target root.
   3. Store target root in `.codex-orchestrator/config.toml` and `state.json`.
   4. Never write workflow artifacts relative to the orchestrator package path.
```

---

## Target repo resolver acceptance criteria

```text
- `cxor status` from inside a target repo finds the Git root.
- `cxor status --repo /path/to/repo` works from outside the repo.
- `cxor auto --repo /path/to/repo --master /path/to/master.md --until DONE` uses the explicit repo.
- `cxor auto --master ./master_prompt.md --until DONE` uses the current Git root when run inside a repo.
- Commands fail clearly when no target repo can be found.
- Commands never create `.codex-orchestrator/` in the user's home directory merely because the user ran `cxor` from the wrong location.
- Commands never write workflow artifacts into the installed package directory.
```

---

# Target repository artifact path manager

The path manager should create and resolve target artifact paths.

Recommended module:

```text
src/codex_orchestrator/paths.py
```

Recommended object:

```python
@dataclass(frozen=True)
class WorkflowPaths:
    repo_root: Path
    workflow_dir: Path
    probe_dir: Path
    master_prompt: Path
    goal_spec: Path
    config: Path
    state: Path
    run_manifest: Path
    census_dir: Path
    search_evidence_jsonl: Path
    search_evidence_md: Path
    inventory_graph: Path
    inventory_table: Path
    invariants: Path
    path_mapping: Path
    patchlets_dir: Path
    subprompts_dir: Path
    reports_dir: Path
    runs_dir: Path
    failures_dir: Path
    repair_plans_dir: Path
    verifier_dir: Path
    final_verification_md: Path
    final_verification_json: Path
```

The default target artifact tree should be:

```text
.target-repo-root/
  .codex-orchestrator/
    master_prompt.md
    goal_spec.json
    config.toml
    state.json
    run_manifest.json
    census/
    search_evidence.jsonl
    search_evidence.md
    inventory_graph.json
    inventory_table.md
    invariants.json
    path_mapping.json
    patchlets/
    subprompts/
    reports/
    runs/
    failures/
    repair_plans/
    verifier/
    final_verification.md
    final_verification.json

  .artifacts/
    probes/
```

This is the only target-state tree required by the orchestrator. The orchestrator source code remains outside the target repo.

---

# Target-local config and global config

The target repo should get a local config file:

```text
.codex-orchestrator/config.toml
```

The user can also have a global config file:

```text
~/.config/codex-orchestrator/config.toml
```

Recommended precedence:

```text
1. CLI flags
2. Environment variables
3. Target repo `.codex-orchestrator/config.toml`
4. User global config `~/.config/codex-orchestrator/config.toml`
5. Orchestrator package defaults
```

The target-local config records project-specific settings. The global config records user-specific defaults.

---

## Target-local config example

```toml
[repo]
root = "."
name = "target-repo"

[artifacts]
workflow_dir = ".codex-orchestrator"
probe_dir = ".artifacts/probes"

[worker]
mode = "real_codex"
codex_binary = "codex"
default_model = "default"

[execution]
non_interactive = true
auto_repair = true
auto_replan = true
auto_rediscover = true
until = "DONE"
max_patchlet_attempts = 3
max_repair_cycles = 0  # 0 means unbounded until DONE unless an emergency abort condition occurs

[git]
require_clean_start = true
use_worktrees = false
rollback_unauthorized_diffs = true
allow_self_target = false
allow_non_git = false

[commands]
test = ""
lint = ""
typecheck = ""
```

Important detail:

```text
max_repair_cycles = 0
```

means the autonomous workflow is intended to keep looping until `DONE`. It should not stop because a patchlet failed, a repair was needed, or a verification failed. It should only abort when the orchestrator itself cannot safely continue.

---

## Global config example

```toml
[worker]
mode = "real_codex"
codex_binary = "codex"

[display]
color = true
verbose = false

[defaults]
until = "DONE"
auto_repair = true
auto_replan = true
auto_rediscover = true
```

Global config should never contain target-repo artifact paths unless explicitly configured for a single-user workflow. Target paths should be target-local.

---

# Global/install commands

These commands operate on the installed orchestrator or on environment checks.

```bash
cxor --version
cxor doctor
cxor doctor --repo /path/to/target-repo
cxor config show
cxor config set <key> <value>
cxor config path
cxor templates list
cxor schemas list
```

## `cxor doctor`

`cxor doctor` should check:

```text
- Python version;
- installed package version;
- package template availability;
- package schema availability;
- Git availability;
- Codex CLI availability;
- whether `codex exec` can be invoked;
- whether current directory is inside a Git repo;
- whether --repo target is valid when provided;
- whether target repo is clean when required;
- whether `.codex-orchestrator/` exists when expected;
- whether target config can be parsed;
- whether state.json validates when present.
```

`cxor doctor` should be safe and read-only.

`cxor doctor --repo /path/to/target-repo` should not initialize the repo. It should report what is missing and suggest `cxor init` or `cxor auto --master ...`.

---

# Target-repo workflow commands with --repo

Every target workflow command should accept `--repo`.

The user should be able to run commands from inside the target repo:

```bash
cd /path/to/target-repo
cxor status
cxor auto --master ./master_prompt.md --until DONE
```

The user should also be able to run commands from anywhere:

```bash
cxor status --repo /path/to/target-repo
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE
```

The full target workflow command list is:

```bash
cxor init --repo /path/to/target-repo --master ./master_prompt.md
cxor auto --repo /path/to/target-repo --master ./master_prompt.md --until DONE
cxor auto --repo /path/to/target-repo --resume --until DONE

cxor normalize --repo /path/to/target-repo
cxor census --repo /path/to/target-repo
cxor classify-evidence --repo /path/to/target-repo
cxor build-inventory --repo /path/to/target-repo
cxor extract-invariants --repo /path/to/target-repo
cxor compile-patchlets --repo /path/to/target-repo

cxor run-next --repo /path/to/target-repo
cxor run-all --repo /path/to/target-repo
cxor validate-report P0001 --repo /path/to/target-repo

cxor verify-group TG001 --repo /path/to/target-repo
cxor verify-global --repo /path/to/target-repo

cxor classify-failures --repo /path/to/target-repo
cxor plan-repair --repo /path/to/target-repo
cxor apply-repair --repo /path/to/target-repo
cxor rediscover --repo /path/to/target-repo --scope impacted
cxor rediscover --repo /path/to/target-repo --scope full
cxor rebuild-inventory --repo /path/to/target-repo --scope impacted
cxor regenerate-patchlets --repo /path/to/target-repo --from-repair-plan latest

cxor status --repo /path/to/target-repo
cxor validate-state --repo /path/to/target-repo
```

When `--repo` is omitted, the command should resolve the current Git root.

---

# Corrected autonomous command in installable CLI model

The one-command entrypoint becomes:

```bash
cxor auto --repo /path/to/target-repo --master /path/to/master_prompt.md --until DONE
```

Convenient form from inside a target repo:

```bash
cd /path/to/target-repo
cxor auto --master ./master_prompt.md --until DONE
```

Resume form:

```bash
cxor auto --repo /path/to/target-repo --resume --until DONE
```

`cxor auto` must still own the full loop:

```text
init if needed
normalize if needed
census if needed
classify evidence if needed
build inventory if needed
extract invariants if needed
compile patchlets if needed
run patchlets
validate reports
verify transaction groups
verify global goals
if not DONE: classify failures
plan repair
apply repair
rediscover or regenerate patchlets when needed
verify again
repeat until DONE
```

The only new first step is:

```text
resolve target repository
```

So the corrected autonomous loop starts as:

```text
cxor auto
   ↓
resolve target repository using --repo or current Git root
   ↓
acquire target repo workflow lock
   ↓
initialize or resume target repo state
   ↓
continue normal autonomous loop until DONE
```

---

# Self-target safety guard

The orchestrator should protect against accidentally targeting its own source repository.

This can happen when a developer is inside the `codex-orchestrator/` repo and runs:

```bash
cxor auto --master ./master_prompt.md --until DONE
```

Maybe that is intentional for dogfooding. Maybe it is accidental.

Default behavior should be cautious.

Recommended rule:

```text
If target repo appears to be the orchestrator source repo:
  fail unless --allow-self-target is provided.
```

How to detect:

```text
- target repo contains pyproject.toml with project.name = "codex-orchestrator"; or
- target repo contains src/codex_orchestrator/; or
- target repo package metadata matches the installed package source path when editable-installed.
```

Override:

```bash
cxor auto --repo /path/to/codex-orchestrator --master ./master_prompt.md --until DONE --allow-self-target
```

Acceptance criteria:

```text
- The orchestrator does not accidentally create workflow artifacts in its own source repo during normal use.
- Self-targeting is still possible for dogfooding when explicitly allowed.
- The warning clearly explains the difference between orchestrator repo and target repo.
```

---

# Target repo initialization in installable model

`cxor init` should create only workflow artifacts in the target repo.

It should not copy source files like:

```text
cli.py
state.py
git_guard.py
codex_adapter.py
validators/
stages/
```

It may copy or generate target-local templates like:

```text
.codex-orchestrator/config.toml
.codex-orchestrator/README.md
.codex-orchestrator/.gitignore
.artifacts/probes/.gitkeep
```

Recommended `cxor init` behavior:

```text
1. Resolve target repo.
2. Verify target repo is valid.
3. Create `.codex-orchestrator/` if missing.
4. Create `.artifacts/probes/` if missing.
5. Copy master prompt into `.codex-orchestrator/master_prompt.md` if provided.
6. Create `.codex-orchestrator/config.toml` if missing.
7. Create `.codex-orchestrator/state.json` if missing.
8. Create `.codex-orchestrator/run_manifest.json` if missing.
9. Create empty artifact subdirectories.
10. Record installed orchestrator version in state or manifest.
11. Record target repo root and starting git SHA.
12. Print next command: `cxor auto --resume --until DONE` or continue automatically if invoked through `cxor auto`.
```

Recommended initialization artifact tree:

```text
.codex-orchestrator/
  README.md
  config.toml
  master_prompt.md
  state.json
  run_manifest.json
  census/
  patchlets/
  subprompts/
  reports/
  runs/
  failures/
  repair_plans/
  verifier/

.artifacts/
  probes/
    .gitkeep
```

---

# Gitignore policy for target artifacts

The target repository must decide which artifacts are committed.

The orchestrator should provide a suggested `.gitignore` snippet, but should not silently modify `.gitignore` unless explicitly requested.

Recommended snippet:

```gitignore
# Codex orchestrator volatile run logs
.codex-orchestrator/runs/
.codex-orchestrator/tmp/
.codex-orchestrator/.lock

# Optional: large probe outputs
.artifacts/probes/**/large-output/
```

Recommended committed artifacts:

```text
.codex-orchestrator/master_prompt.md
.codex-orchestrator/goal_spec.json
.codex-orchestrator/search_evidence.jsonl
.codex-orchestrator/search_evidence.md
.codex-orchestrator/inventory_graph.json
.codex-orchestrator/inventory_table.md
.codex-orchestrator/invariants.json
.codex-orchestrator/path_mapping.json
.codex-orchestrator/patchlets/
.codex-orchestrator/subprompts/
.codex-orchestrator/reports/
.codex-orchestrator/failures/
.codex-orchestrator/repair_plans/
.codex-orchestrator/final_verification.md
.codex-orchestrator/final_verification.json
.artifacts/probes/
```

Recommended uncommitted or optional artifacts:

```text
.codex-orchestrator/runs/
.codex-orchestrator/tmp/
.codex-orchestrator/.lock
very large raw logs
machine-local cache files
```

The plan should not force a single gitignore policy, but the CLI should make the artifact categories clear.

---

# Installed package resource loading

Because the CLI is installed globally, prompt templates and schemas must be loaded from package resources, not relative paths from the current directory.

Use Python package resource APIs such as:

```python
from importlib.resources import files

template = files("codex_orchestrator.prompt_templates").joinpath("root_cause_patchlet.md").read_text()
```

Acceptance criteria:

```text
- Templates load when running from outside the orchestrator repo.
- Templates load when installed with pipx.
- Schemas load when installed as a wheel.
- Tests cover package resource loading from a temporary cwd.
```

---

# Subprocess working-directory rule

All target-repo commands must run with:

```text
cwd = target_repo.root
```

This applies to:

```text
git commands
rg commands
pytest commands
npm commands
docker compose commands
codex exec calls that operate on target repo
probe commands
verification commands
repair commands
```

The orchestrator package directory should not be the subprocess working directory unless running orchestrator self-tests.

Recommended command runner signature:

```python
def run_command(
    args: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    timeout_seconds: int | None = None,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> CommandResult:
    ...
```

Every `CommandResult` should record:

```text
command arguments
cwd
exit code
start time
end time
duration
stdout path
stderr path
environment summary
```

---

# Codex worker adapter in installable model

The Codex adapter must run Codex against the target repo, not the orchestrator repo.

For a patchlet:

```text
cwd = target_repo.root
prompt file = target_repo/.codex-orchestrator/subprompts/Pxxxx.md
run output = target_repo/.codex-orchestrator/runs/Pxxxx-attemptN.jsonl
```

The adapter should record:

```text
installed orchestrator version
target repo path
target repo git SHA before
target repo git SHA after
Codex command
Codex exit code
Codex stdout path
Codex stderr path
Codex JSONL path if available
```

Mock mode must also respect target repo paths.

Mock mode should write fake reports and diffs into the target repo fixture, not into the orchestrator repo.

---

# Diff guard in installable model

The diff guard must inspect the selected target repo.

Minimum commands:

```bash
git -C /path/to/target-repo status --short
git -C /path/to/target-repo diff --name-only
git -C /path/to/target-repo rev-parse HEAD
```

The diff guard must not inspect the orchestrator source repo unless the orchestrator source repo is explicitly selected as the target repo.

Allowed changes remain:

```text
- exactly one allowed product/runtime file for the patchlet;
- .artifacts/probes/**;
- .codex-orchestrator/reports/**;
- .codex-orchestrator/runs/**;
- other explicitly allowed artifact files for the current stage.
```

Forbidden changes remain:

```text
- any other product/runtime file;
- test weakening unless explicitly allowed;
- master prompt mutation during patchlet execution;
- goal spec mutation during patchlet execution;
- inventory mutation during patchlet execution;
- invariant mutation during patchlet execution;
- orchestrator source mutation, unless the target repo is explicitly the orchestrator repo and the patchlet allowed file points there.
```

---

# Locking in target repo

The workflow lock should be target-local:

```text
/path/to/target-repo/.codex-orchestrator/.lock
```

Not global.

This allows independent workflows in different repos:

```text
repo-A/.codex-orchestrator/.lock
repo-B/.codex-orchestrator/.lock
```

Only one orchestrator process should mutate a given target repo workflow at a time.

A global lock is not appropriate because it would prevent independent repos from running concurrently.

Lock metadata should include:

```text
process id
hostname
user
start time
command
orchestrator version
target repo root
```

---

# State file additions for installable model

The target repo `state.json` should record the installed orchestrator version and target repo path.

Recommended additions:

```json
{
  "schema_version": "1.0",
  "kind": "workflow_state",
  "workflow_id": "20260702-001",
  "stage": "INITIALIZED",
  "orchestrator": {
    "package_name": "codex-orchestrator",
    "version": "0.1.0",
    "entrypoint": "cxor",
    "install_mode": "pipx|pip|editable|unknown"
  },
  "target_repo": {
    "root": "/absolute/path/to/target-repo",
    "git_root": "/absolute/path/to/target-repo",
    "repo_sha_start": "...",
    "current_sha": "...",
    "allow_non_git": false,
    "allow_self_target": false
  },
  "stage_history": [],
  "current_patchlet_id": null,
  "attempts": {},
  "completed_patchlets": [],
  "verified_no_change_needed": [],
  "blocked_patchlets": [],
  "failed_patchlets": [],
  "transaction_groups": [],
  "repair_cycles": [],
  "created_at": "...",
  "updated_at": "..."
}
```

This is useful for reproducibility. If a future run uses a different orchestrator version, the CLI can record that change.

---

# Run manifest additions for installable model

The run manifest should record both the installed orchestrator and target repository context.

Recommended fields:

```json
{
  "schema_version": "1.0",
  "kind": "run_manifest",
  "workflow_id": "...",
  "target_repo_root": "/path/to/target-repo",
  "orchestrator_version": "0.1.0",
  "invocation": {
    "argv": ["cxor", "auto", "--master", "./master_prompt.md", "--until", "DONE"],
    "cwd": "/path/from/which/user/invoked/cxor",
    "resolved_target_repo": "/path/to/target-repo"
  },
  "runs": []
}
```

This makes it possible to answer later:

```text
Which installed orchestrator version created these artifacts?
Which target repo did it operate on?
From where was the command invoked?
Which exact command started the workflow?
```

---

# Updated build order with installable CLI first

The build order must be updated so installation and target repo resolution come before orchestration intelligence.

Corrected build order:

```text
1. Create standalone orchestrator Git repo.
2. Add `pyproject.toml` and console script entrypoints.
3. Implement package resource loading for schemas and templates.
4. Implement global CLI shell: `cxor --version`, `cxor doctor`.
5. Implement target repo resolver: `--repo` or current Git root.
6. Implement target artifact path manager.
7. Implement target repo init.
8. Implement global config + target-local config.
9. Implement run locks in the target repo.
10. Implement atomic writes in the target repo.
11. Implement state machine and schemas.
12. Implement deterministic census in the target repo.
13. Implement Codex adapter with target repo as cwd.
14. Implement goal normalization.
15. Implement evidence classification.
16. Implement inventory graph generation.
17. Implement invariant extraction.
18. Implement patchlet compiler.
19. Implement patchlet executor with target repo diff guard.
20. Implement patchlet report validation.
21. Implement root-cause/proof validators.
22. Implement transaction-group verifier.
23. Implement global verifier.
24. Implement failure classifier.
25. Implement repair planner.
26. Implement repair applier.
27. Implement impacted-scope rediscovery.
28. Implement full rediscovery.
29. Implement autonomous `cxor auto` loop.
30. Add install docs and release workflow.
31. Add integration tests using fake target repos.
32. Add dogfooding guard and optional `--allow-self-target`.
```

The enforcement layer still comes before the intelligence layer. The difference is that packaging, target resolution, and artifact-path correctness now come before state-machine and stage implementation because every later feature depends on operating in the correct target repo.

---

# New Phase 1 — create standalone installable orchestrator repository

This replaces the earlier repo-local Phase 1.

## Deliverables

```text
codex-orchestrator/
  pyproject.toml
  README.md
  LICENSE
  CHANGELOG.md
  src/codex_orchestrator/
  tests/
  docs/
```

## Required commands in Phase 1

```bash
cxor --version
cxor doctor
cxor init --repo /path/to/target-repo --master ./master_prompt.md
cxor status --repo /path/to/target-repo
```

## Phase 1 acceptance criteria

```text
- The orchestrator has its own Git repository.
- The package installs with `pip install -e .`.
- The package installs with `pipx install .`.
- The `cxor` command is available globally after installation.
- The `codex-orchestrator` command is available globally after installation.
- `cxor --version` works from any directory.
- `python -m codex_orchestrator --version` works.
- `cxor doctor` checks Python version, Git, Codex CLI availability, package templates, package schemas, and target repo validity.
- `cxor init --repo <repo> --master <file>` creates target repo artifacts.
- `cxor status --repo <repo>` reads target repo workflow state.
- No orchestrator source code is copied into the target repo.
- `.codex-orchestrator/` and `.artifacts/probes/` are created inside the target repo, not inside the orchestrator package directory.
```

---

# Updated MVP definitions

## MVP 0 — Installable CLI skeleton

MVP 0 proves the packaging and target-repo boundary.

Includes:

```text
- standalone orchestrator Git repo;
- pyproject.toml;
- `cxor` console script;
- `codex-orchestrator` console script;
- `cxor --version`;
- `cxor doctor`;
- `--repo` option;
- current Git-root discovery;
- target repo artifact path manager;
- target repo init;
- target-local config file;
- target-local state file;
- no orchestrator source copied into target repo.
```

MVP 0 acceptance:

```text
From outside any repo:
  cxor --version works.

From inside a target repo:
  cxor init --master ./master_prompt.md creates .codex-orchestrator/ and .artifacts/probes/ in that repo.

From anywhere:
  cxor init --repo /path/to/repo --master /path/to/master_prompt.md creates artifacts in /path/to/repo.
```

## MVP 1 — Enforcement foundation

MVP 1 builds on MVP 0 and includes:

```text
- state machine;
- schemas;
- deterministic census;
- Codex adapter with mock mode;
- goal normalization;
- evidence classification;
- inventory graph generation;
- invariant extraction;
- patchlet compiler;
- patchlet executor;
- target repo diff guard;
- patchlet report validator;
- status command.
```

MVP 1 must preserve:

```text
- one allowed product/runtime file per patchlet;
- artifact directory exception;
- no implementation before probe gates;
- required patchlet report;
- target repo diff guard;
- no vague statuses;
- no blind retry;
- state belongs to target repo artifacts and orchestrator state machine, not Codex memory;
- installed orchestrator source is not copied into target repo.
```

## MVP 2 — Full verification

MVP 2 includes:

```text
- transaction-group verifier;
- global verifier;
- final verification artifacts;
- read-only evidence-bound global conclusion;
- target repo status showing master goals and invariant status.
```

## MVP 3 — Autonomous repair loop

MVP 3 includes:

```text
- failure classification;
- repair planner;
- repair applier;
- repair patchlet generation;
- impacted rediscovery;
- full rediscovery;
- autonomous `cxor auto --until DONE` loop;
- resume after interruption.
```

MVP 3 acceptance:

```text
- `cxor auto --repo /path/to/repo --master /path/to/master_prompt.md --until DONE` runs without manual stage commands.
- `FAILED_WITH_EVIDENCE`, `BLOCKED_WITH_EVIDENCE`, `REPAIR_PLANNING_REQUIRED`, and verification failures become loop inputs, not terminal states.
- The command exits 0 only on DONE.
- Emergency abort is reserved for orchestrator/system corruption, user interrupt, missing permissions, invalid target repo, invalid state that cannot be repaired, or policy/config stop conditions.
```

---

# Updated final CLI recommendation

The final CLI recommendation now has two layers.

## Install once

```bash
git clone <orchestrator-git-url> ~/src/codex-orchestrator
cd ~/src/codex-orchestrator
pipx install .
```

or:

```bash
pipx install git+<orchestrator-git-url>
```

## Use from inside any target repo

```bash
cd /path/to/target-repo
cxor auto --master ./master_prompt.md --until DONE
```

## Use from anywhere

```bash
cxor auto \
  --repo /path/to/target-repo \
  --master /path/to/master_prompt.md \
  --until DONE
```

## Resume from anywhere

```bash
cxor auto --repo /path/to/target-repo --resume --until DONE
```

## Inspect status from anywhere

```bash
cxor status --repo /path/to/target-repo
```

---

# Final corrected installable architecture principle

The final implementation plan should preserve this principle:

> The orchestrator is its own installable software project. The target repository is the work site. The installed `cxor` CLI resolves the target repository, writes durable workflow artifacts into that target repository, runs all target commands from that target repository, enforces target-repo diffs, and loops through repair/replan/rediscover until the target repository reaches `DONE`. The orchestrator source code is never copied into target repositories and is never mutated as part of target workflow execution unless the orchestrator repository is explicitly selected as the target with `--allow-self-target`.

This principle adds deployment and repository-boundary correctness to the existing root-cause probe-gated autonomous workflow.

