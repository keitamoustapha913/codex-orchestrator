# Codex Worker Capsule — Approved Architecture, Reflections, Corrections, and Implementation Blueprint

Status: Approved for inclusion in the Codex Orchestrator implementation plan.

Date: 2026-07-02

This document preserves the approved reflections about adapting the `codex-compaction-memory-lab` ideas into the `codex-orchestrator` project. It is intentionally detailed. It does not compress the ideas into a short summary. It keeps the approved reasoning, the proposed architecture, the warnings, the gaps, the implementation direction, and the design corrections in one markdown file.

The core approved decision is:

```text
Do not copy codex-compaction-memory-lab directly.
Adapt its philosophy into an orchestrator-native Codex Worker Capsule.
Codex is an unreliable worker until durable artifacts and external validators prove success.
```

The compaction part of `codex-compaction-memory-lab` is explicitly out of scope here. The useful ideas are the durable evidence model: durable memory, stage artifacts, lifecycle hooks, and wrapper-side gates.

---

# 1. Approved Source Reflections Preserved

The following section preserves the approved reflections and design language from the discussion. Minor formatting has been cleaned only where needed to make this a standalone markdown file. The meaning and details are preserved.

Your idea is good, but I would **not copy `codex-compaction-memory-lab` directly**. I would adapt its philosophy into a stricter orchestrator-native design.

The useful principle from that repo is:

```text
Codex is not the owner of truth.
Codex is a worker that must leave durable evidence.
The wrapper/orchestrator decides whether the work is valid.
```

That repo’s strongest ideas are durable memory, stage handoff artifacts, hooks, and wrapper-side gates. It also proves the right attitude: do not trust active model memory, do not trust “agent says success,” use durable artifacts, explicit phase gates, and final markers.  

For your orchestrator, I would turn this into a **Codex Worker Capsule** for every `codex exec`.

---

# My intake

Your orchestrator already has stronger foundations than `codex-compaction-memory-lab`: state machine, patchlets, reports, probes, diff guard, transaction/global verification, repair planning, worktrees, and run manifests. The original plan already says durable runtime state should live in `.codex-orchestrator/` and `.artifacts/probes/`, and that Codex should not own global state.  

What `codex-compaction-memory-lab` adds is a missing **worker-continuity discipline**:

```text
Before Codex runs:
  give it local durable memory and stage instructions.

During/after Codex runs:
  force it to leave evidence.

After Codex exits:
  wrapper gates decide success, not Codex.
```

This is especially relevant because real Codex is currently failing before producing the required report/probe artifacts. We now know the orchestrator wiring works, but real Codex output quality is the remaining uncertainty. A per-exec memory/stage/gate wrapper can make the real-Codex side easier to diagnose and steer.

---

# The design I recommend: Codex Worker Capsule

Every `codex exec` attempt should get its own isolated capsule:

```text
.codex-orchestrator/runs/P0001_attempt1/
  command.json
  stdout.txt
  stderr.txt
  output.jsonl
  diff.patch
  diff_name_status.txt

  worker_memory/
    LIVE_MEMORY.md
    TASK_CONTRACT.md
    KNOWN_FACTS.json
    ALLOWED_PATHS.json
    PREVIOUS_FAILURES.md
    CURRENT_STAGE.md

  worker_stage/
    00_preflight.md
    01_investigation.md
    02_probe_plan.md
    03_implementation.md
    04_validation.md
    05_final_report.md

  worker_hooks/
    session_start_context.md
    prompt_submit_context.md
    pre_run_snapshot.json
    post_run_snapshot.json
    failure_snapshot.json

  gates/
    final_status.json
    required_artifacts_check.json
    report_validation.json
    probe_validation.json
    diff_validation.json
    wrapper_gate_result.json
```

This is the orchestrator-native version of the lab’s `.codex-state/LIVE_MEMORY.md`, `.codex-stage/`, lifecycle hooks, and wrapper gates.

But important: **these are not global memory files.** They are per-run, per-patchlet worker memory files.

---

# 1. Durable memory — how to adapt it

In `codex-compaction-memory-lab`, durable memory is a repo-level `LIVE_MEMORY.md`. For your orchestrator, I would not use one global Codex memory file because it can become polluted, stale, or overly broad.

I would use **scoped memory**:

```text
Patchlet memory:
  .codex-orchestrator/runs/P0001_attempt1/worker_memory/LIVE_MEMORY.md

Transaction group memory:
  .codex-orchestrator/transaction_groups/TG001/group_memory.md

Global verification memory:
  .codex-orchestrator/global/global_memory.md
```

The patchlet memory should contain only:

```text
patchlet id
allowed product/runtime file
goal ids
invariant ids
evidence ids
graph nodes
contract reminders
current failure context
required report path
required probe path
what Codex tried
what Codex observed
what Codex wrote
what remains unresolved
```

It should **not** contain broad repo memory. The orchestrator already owns broad repo truth through `goal_spec.json`, `inventory_graph.json`, `invariants.json`, `path_mapping.json`, reports, probes, and final verification.

## Better proposition

Make durable memory **structured plus human-readable**:

```text
LIVE_MEMORY.md      # readable for Codex
LIVE_MEMORY.json    # machine-validated summary
```

The JSON version should be gate-checked. Codex can write markdown, but the orchestrator should validate the JSON.

---

# 2. Stage artifacts — how to adapt them

The lab uses stage artifacts so Codex can continue from files instead of chat memory. That maps very well to patchlet execution.

For each patchlet attempt, require stage artifacts:

```text
worker_stage/00_preflight.md
worker_stage/01_investigation.md
worker_stage/02_probe_plan.md
worker_stage/03_implementation.md
worker_stage/04_validation.md
worker_stage/05_final_report.md
```

Each one should have a narrow purpose.

## 00_preflight.md

Codex must restate:

```text
allowed file
forbidden files
report path
probe path
current state
patchlet goal
required validators
```

## 01_investigation.md

Codex records what it inspected.

But the orchestrator should treat this as **claim evidence**, not truth.

## 02_probe_plan.md

Codex writes the minimal root-cause probe plan.

This aligns with your root-cause standard: minimal reproduction, deterministic failure, controlled initial state, producer → transformer → consumer boundary, negative control, cleanup proof, and durable artifacts. 

## 03_implementation.md

Codex records the actual edit plan.

## 04_validation.md

Codex records commands run and outcomes.

## 05_final_report.md

Codex states final status, but this is only accepted if wrapper-side gates pass.

## Better proposition

Do not merely ask Codex to write these. Make them **required stage gates**:

```text
If 00_preflight.md missing → worker failed.
If 02_probe_plan.md missing → report cannot be COMPLETE.
If 04_validation.md missing → report cannot be COMPLETE.
If 05_final_report.md lacks FINAL_STATUS → wrapper gate fails.
```

---

# 3. Codex lifecycle hooks — how to adapt them

I would be careful here.

The lab’s native hooks are useful, but real compaction hooks were not proven, and you already said compaction is out of scope. The repo itself treats real PreCompact/PostCompact as unproven. 

So I would **not depend on Codex lifecycle hooks as the primary mechanism**.

Instead, implement **orchestrator-owned lifecycle hooks** around `codex exec`.

Use wrapper hooks like:

```text
before_worker_start
after_prompt_written
after_worker_exit
after_diff_capture
after_report_validation
after_probe_validation
after_failure
```

These are deterministic because the orchestrator controls them.

Native Codex hooks can be optional later, but they should be treated as extra telemetry, not truth.

## Better proposition

Create a hook adapter interface:

```text
cxor worker-hook before-start
cxor worker-hook after-exit
cxor worker-hook after-validation
cxor worker-hook after-failure
```

Every hook writes a durable JSON event:

```text
.codex-orchestrator/runs/P0001_attempt1/events.jsonl
```

Example event:

```json
{
  "schema_version": "1.0",
  "kind": "worker_event",
  "event": "after_worker_exit",
  "patchlet_id": "P0001",
  "attempt_id": "P0001_attempt1",
  "worker_mode": "real_codex",
  "exit_code": 1,
  "stdout_path": "...",
  "stderr_path": "...",
  "output_jsonl_path": "...",
  "timestamp": "..."
}
```

This is more reliable than depending on Codex’s internal lifecycle hooks.

---

# 4. Wrapper-side gates — how to adapt them

This is the most important piece.

The lab checks `turn.completed`, rejects failed/error events, checks `FINAL_STATUS: PASS`, runs pytest, and checks memory markers. 

Your orchestrator should have a stronger wrapper gate for every patchlet:

```text
Worker exit gate:
  process exit code is 0
  no worker-level error event

Artifact gate:
  required report exists
  required probe artifacts exist
  required stage artifacts exist
  required memory artifacts exist

Diff gate:
  only allowed product/runtime file changed
  allowed artifact directories only

Report gate:
  patchlet report schema passes
  semantic validator passes
  root-cause/proof validators pass

Probe gate:
  row ledger exists
  trace ledger exists
  before/after state exists
  cleanup proof exists
  deterministic run counts exist

Final marker gate:
  Codex says FINAL_STATUS: PASS
  but this alone is never sufficient

Wrapper decision:
  COMPLETE, FAILED_WITH_EVIDENCE, BLOCKED_WITH_EVIDENCE, or WORKER_FAILED
```

## Better proposition

Add a single machine-readable gate result per attempt:

```text
.codex-orchestrator/runs/P0001_attempt1/gates/wrapper_gate_result.json
```

Shape:

```json
{
  "schema_version": "1.0",
  "kind": "wrapper_gate_result",
  "patchlet_id": "P0001",
  "attempt_id": "P0001_attempt1",
  "accepted": false,
  "final_status_claim": "PASS",
  "worker_exit_gate": "pass",
  "artifact_gate": "fail",
  "diff_gate": "not_run",
  "report_gate": "fail",
  "probe_gate": "fail",
  "reasons": [
    "missing .codex-orchestrator/reports/P0001.json",
    "missing .artifacts/probes/P0001/run_001/row_ledger.jsonl"
  ],
  "next_state": "FAILURE_CLASSIFICATION_REQUIRED"
}
```

This is exactly the principle: Codex can claim anything, but the wrapper decides.

---

# How this applies to patchlets

For every patchlet attempt:

```text
P0001_attempt1 gets:
  Durable memory
  Stage artifacts
  Lifecycle events
  Wrapper gates
```

The flow becomes:

```text
1. Orchestrator creates worker capsule.
2. Orchestrator writes TASK_CONTRACT.md.
3. Orchestrator writes LIVE_MEMORY.md from graph/invariant/failure context.
4. Orchestrator writes stage artifact templates.
5. Codex runs inside worktree.
6. Codex updates memory/stage artifacts.
7. Codex writes report/probes.
8. Orchestrator captures stdout/stderr/output/diff.
9. Orchestrator runs wrapper gates.
10. Only then does state advance.
```

The important improvement is that real Codex gets a **small local memory surface**, not only a massive prompt.

That could help with the current real-Codex problem because actual Codex may be failing before producing valid artifacts. A `TASK_CONTRACT.md` plus stage templates may give it clearer file targets than one giant injected prompt.

---

# How this applies to transaction/group verification

Your idea that group verify should cross-verify patchlet outputs is correct.

Transaction group verification should create its own capsule:

```text
.codex-orchestrator/transaction_groups/TG001/
  group_memory.md
  group_stage/
    00_inputs.md
    01_patchlet_report_matrix.md
    02_probe_crosscheck.md
    03_diff_scope_check.md
    04_group_verdict.md
  gates/
    group_gate_result.json
```

Group verify should not simply ask, “Are all patchlets complete?”

It should cross-check:

```text
Patchlet P0001 says it fixed invariant I001.
Does its report reference I001?
Does its probe artifact exist?
Does the row ledger mention the same boundary?
Did it only edit its allowed file?
Does transaction_groups.json expect P0001?
Are there conflicting claims across patchlets?
Did any patchlet mark COMPLETE while another marks related evidence FAILED?
```

## Better proposition

Add a `patchlet_output_matrix.json`:

```json
{
  "schema_version": "1.0",
  "kind": "patchlet_output_matrix",
  "transaction_group_id": "TG001",
  "patchlets": [
    {
      "patchlet_id": "P0001",
      "status": "COMPLETE",
      "report_valid": true,
      "probe_valid": true,
      "allowed_diff_valid": true,
      "goal_ids": ["G001"],
      "invariant_ids": ["I001"],
      "evidence_ids": ["E001"],
      "contradictions": []
    }
  ],
  "group_verdict": "PASSED"
}
```

This would make group verification stronger and easier to debug.

---

# How this applies to global verification

Global verification should also get a capsule, but it should not behave like Codex execution.

Global verification is mostly deterministic. It should use Codex only, if at all, as a low-trust summarizer.

Global capsule:

```text
.codex-orchestrator/global_verification/
  global_memory.md
  global_stage/
    00_inputs.md
    01_goal_matrix.md
    02_invariant_matrix.md
    03_transaction_matrix.md
    04_failure_matrix.md
    05_final_verdict.md
  gates/
    global_gate_result.json
```

Global verify should cross-check:

```text
Every master goal has proof.
Every invariant has proof.
Every transaction group passed.
Every patchlet report validates.
Every probe validates.
Every failure is resolved or explicitly blocked.
No unauthorized diffs remain.
No blind retry occurred.
Final verification is consistent with state.json.
```

## Better proposition

Add a deterministic `verification_matrix.json` before `final_verification.json`.

```json
{
  "schema_version": "1.0",
  "kind": "verification_matrix",
  "goals": [],
  "invariants": [],
  "transaction_groups": [],
  "patchlets": [],
  "failures": [],
  "unresolved": [],
  "verdict": "DONE_ALLOWED"
}
```

Then `final_verification.json` becomes a conclusion over that matrix.

---

# Missing gaps in your current orchestrator

Based on where the implementation has reached, I see these gaps:

## Gap 1 — Real Codex still lacks a “small working memory surface”

You inject the strict contract into the subprompt, which is good. But real Codex may need a more concrete run-local file layout:

```text
TASK_CONTRACT.md
LIVE_MEMORY.md
CURRENT_STAGE.md
WRITE_THESE_FILES.md
```

The contract should not only be inside the prompt. It should exist as files in the run dir, and the prompt should say:

```text
First read:
.codex-orchestrator/runs/P0001_attempt1/worker_memory/TASK_CONTRACT.md
```

This makes the target concrete.

## Gap 2 — No explicit stage artifact requirement per patchlet yet

You have reports/probes, but not Codex-authored stage artifacts like:

```text
01_investigation.md
02_probe_plan.md
03_validation.md
```

These would help diagnose whether Codex understood the task before failing.

## Gap 3 — Native Codex hooks are not needed, but wrapper hooks should be formalized

You already capture run artifacts. But there is no explicit lifecycle event stream like:

```text
events.jsonl
```

That would make diagnosing real-Codex failures easier.

## Gap 4 — Wrapper-side gate result should be first-class

You have validators and run manifests, but a single `wrapper_gate_result.json` per attempt would make the final accept/reject reason obvious.

## Gap 5 — Group/global verification could become matrix-based

Group/global verification exists, but it can be made more transparent by generating matrices before verdicts:

```text
patchlet_output_matrix.json
verification_matrix.json
```

These are easier for humans and Codex to inspect than only final verdict files.

---

# Issues to avoid

## Do not create one global memory file for everything

A global `LIVE_MEMORY.md` will eventually become noisy and dangerous.

Use scoped memory:

```text
patchlet memory
transaction memory
global memory
```

## Do not let Codex memory override deterministic artifacts

If `LIVE_MEMORY.md` says “done” but report validation fails, the result is failure.

Memory is context, not proof.

## Do not rely on native compaction hooks

Compaction is out of scope, and the lab did not prove real PreCompact/PostCompact trigger. Treat native Codex hooks as optional telemetry, not core correctness. 

## Do not allow Codex to edit its own gate results

Codex may write stage artifacts and final claims. The orchestrator writes gate results.

## Do not let wrapper gates become text-only

`FINAL_STATUS: PASS` is useful, but insufficient. Every gate must be backed by machine-validated JSON, files, diff, and schemas.

---

# My better proposition: three-layer evidence model

I would implement this as three layers.

## Layer 1 — Worker Capsule

Per `codex exec`.

```text
memory
stage artifacts
event log
wrapper gates
```

Purpose:

```text
Make each Codex call self-contained, auditable, and resumable.
```

## Layer 2 — Transaction Crosscheck

Per transaction group.

```text
patchlet_output_matrix.json
group_gate_result.json
group_memory.md
```

Purpose:

```text
Make sure patchlets agree with each other and with the group invariant.
```

## Layer 3 — Global Proof Matrix

Per workflow.

```text
verification_matrix.json
global_gate_result.json
final_verification.json
```

Purpose:

```text
Make DONE a deterministic conclusion, not a narrative.
```

---

# What I would implement first

I would not start with group/global memory. I would start with the **per-patchlet Worker Capsule**, because it directly addresses the current real-Codex failure.

First increment:

```text
Add per-attempt worker_memory/ and worker_stage/ artifacts for CodexExecWorker.
```

Minimum files:

```text
.codex-orchestrator/runs/P0001_attempt1/worker_memory/TASK_CONTRACT.md
.codex-orchestrator/runs/P0001_attempt1/worker_memory/LIVE_MEMORY.md
.codex-orchestrator/runs/P0001_attempt1/worker_stage/00_preflight.md
.codex-orchestrator/runs/P0001_attempt1/gates/wrapper_gate_result.json
```

Then update the real-Codex prompt to say:

```text
Before doing anything, read TASK_CONTRACT.md and write 00_preflight.md.
```

That gives real Codex a smaller, more concrete operating surface.

---

# My final recommendation

Yes, integrate the lab’s ideas, but not as loose `.codex-state` files.

Integrate them as:

```text
Codex Worker Capsules
```

Each `codex exec` gets:

```text
1. Durable memory — scoped to that attempt.
2. Stage artifacts — required handoff/checkpoint files.
3. Lifecycle hooks — orchestrator-owned events, not native compaction hooks.
4. Wrapper-side gates — machine-written accept/reject verdicts.
```

Then transaction verification gets:

```text
patchlet_output_matrix.json
group_gate_result.json
```

And global verification gets:

```text
verification_matrix.json
global_gate_result.json
```

This would make the orchestrator’s Codex execution more robust, more diagnosable, and more faithful to the principle:

```text
Codex is an unreliable worker until durable artifacts and external validators prove success.
```

---

# 2. Approved Decision: Codex Worker Capsule

The approved architectural decision is to introduce a **Codex Worker Capsule** for every Codex execution attempt managed by `codex-orchestrator`.

The capsule is a durable, per-attempt filesystem boundary. It is not a memory gimmick. It is a correctness and observability boundary.

The purpose is to make each Codex call:

```text
self-contained
bounded
auditable
resumable
diagnosable
externally validated
unable to claim success without evidence
```

This is a direct adaptation of the strongest parts of `codex-compaction-memory-lab`, but transformed into the stronger architecture that the orchestrator already has:

```text
codex-compaction-memory-lab:
  durable memory
  stage artifacts
  hooks
  wrapper gates
  final status markers

codex-orchestrator:
  target repo resolution
  state machine
  patchlets
  report validation
  durable probes
  diff guard
  repair loop
  transaction verification
  global verification
  worktree isolation
  real-Codex smoke
  run manifests
  worker capsules
```

The new design does not replace the orchestrator’s existing artifacts. It wraps Codex execution with additional per-attempt artifacts that help Codex operate more concretely and help the orchestrator diagnose and reject bad work more clearly.

---

# 3. Core Principle

The central principle is repeated because it must drive every implementation decision:

```text
Codex is not the owner of truth.
Codex is a worker that must leave durable evidence.
The wrapper/orchestrator decides whether the work is valid.
```

The orchestrator must not accept any of these as proof by themselves:

```text
Codex said it succeeded.
Codex wrote FINAL_STATUS: PASS.
Codex exited with code 0.
Codex wrote a plausible summary.
Codex updated a memory file.
Codex wrote a report that looks reasonable.
Codex produced a diff.
Codex wrote stage notes.
```

The orchestrator can only accept a patchlet when all relevant external gates pass:

```text
process/worker gate
artifact existence gate
diff gate
report schema gate
semantic report gate
root-cause proof gate
probe artifact gate
transaction group gate
global verification gate
```

Memory and stage notes help Codex work, but they are not proof. They are context and evidence. The orchestrator-owned validators decide.

---

# 4. Why This Is Needed Now

The current orchestrator implementation has reached an advanced state:

```text
mock/fake worker path is strong
real_codex worker path is wired
worktree execution is implemented
auto --use-worktree is implemented
fake-success parity proves the real_codex path can reach DONE
real Codex smoke is opt-in and safely contained
run_manifest records WORKER_FAILED evidence
contract injection exists
```

The remaining practical issue is that actual installed Codex still has trouble producing the exact report/probe artifacts required by the orchestrator validators.

The orchestrator has already proven that the path works if the subprocess writes correct artifacts. The missing part is making actual Codex more likely to understand and follow the artifact contract.

A single large prompt is not always the best interface for a worker. The worker may need a concrete local working surface:

```text
read this local task contract
write this preflight file
write this probe plan
write this validation note
write this final status
write the report here
write probes here
only edit this allowed product file
```

That is the reason for the Worker Capsule.

---

# 5. Non-Goals and Boundaries

## 5.1 Compaction Is Out of Scope

The compaction portion of `codex-compaction-memory-lab` is not part of this approved design.

The lab did not prove real PreCompact/PostCompact firing in the authentic Codex runtime. It proved durable memory discipline and hook simulation, but not real compaction. Therefore the orchestrator should not depend on native Codex compaction hooks for correctness.

Approved boundary:

```text
Do not build correctness on native Codex compaction hooks.
Do not require PreCompact/PostCompact behavior.
Do not treat compaction events as necessary for this design.
```

## 5.2 Native Codex Hooks Are Optional Telemetry

Native Codex lifecycle hooks can be useful later, but they must not be the primary correctness mechanism.

The orchestrator should use deterministic, orchestrator-owned lifecycle events instead.

Approved boundary:

```text
Native hooks may be recorded as optional telemetry.
Orchestrator-owned hooks/events decide the actual lifecycle evidence.
```

## 5.3 No Global Codex Memory File

Do not introduce one global `LIVE_MEMORY.md` for the entire target repo.

A single global memory file becomes noisy, stale, and dangerous. It can leak context across unrelated patchlets, preserve outdated assumptions, and tempt Codex to treat memory as proof.

Approved boundary:

```text
Use scoped memory.
Patchlet memory is per attempt.
Transaction memory is per transaction group.
Global verification memory is per verification workflow.
Memory is context, not proof.
```

## 5.4 Codex Cannot Write Its Own Gate Verdict

Codex can write claims, notes, reports, and final status claims.

Codex must not write the orchestrator’s final gate verdict.

Approved boundary:

```text
Codex may write worker_stage/*.
Codex may write worker_memory/LIVE_MEMORY.md.
Codex may write a patchlet report.
Codex may write probe artifacts.
The orchestrator writes gates/wrapper_gate_result.json.
The orchestrator writes diff/report/probe validation gate outputs.
The orchestrator decides state transitions.
```

---

# 6. Worker Capsule Directory Contract

Every `codex exec` attempt should receive one durable capsule under the run directory.

Canonical path:

```text
.codex-orchestrator/runs/<PATCHLET_ID>_attempt<N>/
```

Example:

```text
.codex-orchestrator/runs/P0001_attempt1/
```

Approved initial layout:

```text
.codex-orchestrator/runs/P0001_attempt1/
  command.json
  stdout.txt
  stderr.txt
  output.jsonl
  diff.patch
  diff_name_status.txt
  run_record.json or run_manifest entry

  worker_memory/
    TASK_CONTRACT.md
    LIVE_MEMORY.md
    LIVE_MEMORY.json
    KNOWN_FACTS.json
    ALLOWED_PATHS.json
    PREVIOUS_FAILURES.md
    CURRENT_STAGE.md
    WRITE_THESE_FILES.md

  worker_stage/
    00_preflight.md
    01_investigation.md
    02_probe_plan.md
    03_implementation.md
    04_validation.md
    05_final_report.md

  worker_events/
    events.jsonl

  worker_hooks/
    session_start_context.md
    prompt_submit_context.md
    pre_run_snapshot.json
    post_run_snapshot.json
    failure_snapshot.json

  gates/
    final_status.json
    required_artifacts_check.json
    memory_validation.json
    stage_validation.json
    report_validation.json
    probe_validation.json
    diff_validation.json
    wrapper_gate_result.json
```

The exact names may be adapted to existing code style, but the logical categories are approved:

```text
worker_memory
worker_stage
worker_events / lifecycle events
gates
```

---

# 7. Worker Memory Contract

## 7.1 Purpose

Worker memory is a local working surface for a single Codex attempt. It helps Codex keep its task focused and gives the orchestrator something to inspect when Codex fails.

Worker memory is not proof of success.

Worker memory should answer:

```text
What is this patchlet?
What is the allowed file?
What is forbidden?
What report path must be written?
What probe path must be written?
What evidence does this patchlet depend on?
What failure context exists?
What did Codex already try?
What remains unresolved?
```

## 7.2 Files

### TASK_CONTRACT.md

This is orchestrator-written. Codex reads it first.

It should include:

```text
patchlet_id
attempt_id
worker_mode
target_root
execution_root
artifact_root
allowed product/runtime file
forbidden product/runtime files
allowed artifact directories
report path
probe root
run dir
required report status values
required probe files
required stage artifacts
final status claim format
no blind retry rule
validator weakening forbidden
```

TASK_CONTRACT.md must be clear, direct, and path-specific.

It should explicitly say:

```text
Before doing anything, read this file.
Before editing product/runtime code, write worker_stage/00_preflight.md.
Before implementation, write worker_stage/02_probe_plan.md.
Before final report, write worker_stage/04_validation.md.
Write the final patchlet report to the exact report path.
Write durable probes under the exact probe root.
Only edit the allowed product/runtime file.
Do not invent alternate artifact paths.
```

### LIVE_MEMORY.md

This is Codex-readable and may be Codex-updated.

It should include a narrative attempt-local memory:

```text
current patchlet goal
current known facts
current inspected files
current probe plan
current implementation decision
current validation status
current blockers
current unresolved issues
```

This file helps Codex maintain continuity within one run. It is not broad project memory.

### LIVE_MEMORY.json

This is machine-validated. Codex may write it, but the orchestrator validates it.

Suggested shape:

```json
{
  "schema_version": "1.0",
  "kind": "worker_live_memory",
  "patchlet_id": "P0001",
  "attempt_id": "P0001_attempt1",
  "current_stage": "probe_plan",
  "allowed_product_runtime_file": "app.py",
  "observations": [],
  "files_inspected": [],
  "probes_planned": [],
  "probes_run": [],
  "changes_made": [],
  "validation_commands": [],
  "blockers": [],
  "unresolved_questions": [],
  "final_status_claim": null
}
```

### KNOWN_FACTS.json

This is orchestrator-written or orchestrator-derived from existing evidence.

It should include stable facts only:

```text
goal ids
invariant ids
evidence ids
graph node ids
transaction group id
prior failure ids
repair plan id if applicable
allowed file
report path
probe path
```

Codex should not be allowed to rewrite these unless explicitly permitted.

### ALLOWED_PATHS.json

This is orchestrator-written.

It should contain:

```json
{
  "schema_version": "1.0",
  "kind": "allowed_paths",
  "patchlet_id": "P0001",
  "allowed_product_runtime_files": ["app.py"],
  "allowed_artifact_roots": [
    ".codex-orchestrator/reports/",
    ".codex-orchestrator/runs/",
    ".artifacts/probes/"
  ],
  "forbidden_patterns": [
    "**/.env",
    "**/secrets*"
  ]
}
```

### PREVIOUS_FAILURES.md

This is useful for repair patchlets.

It should include:

```text
failure_id
failure source
observed failure
classification
failed diff summary
previous worker failure summary
what must not be retried blindly
```

### CURRENT_STAGE.md

This is a small pointer file.

It should contain:

```text
current expected stage
required next worker_stage file
required next artifact
whether product edits are allowed yet
```

### WRITE_THESE_FILES.md

This is a path checklist for real Codex.

It should list exact paths:

```text
You must write:
- .codex-orchestrator/runs/P0001_attempt1/worker_stage/00_preflight.md
- .codex-orchestrator/runs/P0001_attempt1/worker_stage/02_probe_plan.md
- .codex-orchestrator/reports/P0001.json
- .artifacts/probes/P0001/probe.py
- .artifacts/probes/P0001/run_001/row_ledger.jsonl
- .artifacts/probes/P0001/run_001/trace_ledger.jsonl
- .artifacts/probes/P0001/run_001/before_state.json
- .artifacts/probes/P0001/run_001/after_state.json
- .artifacts/probes/P0001/run_001/cleanup_proof.json
```

This file is intentionally concrete. It is meant to reduce ambiguity for real Codex.

---

# 8. Worker Stage Artifact Contract

Stage artifacts are Codex-authored or Codex-filled handoff/checkpoint files. They are not final proof, but they are required evidence of process discipline.

Approved worker stage files:

```text
worker_stage/00_preflight.md
worker_stage/01_investigation.md
worker_stage/02_probe_plan.md
worker_stage/03_implementation.md
worker_stage/04_validation.md
worker_stage/05_final_report.md
```

## 8.1 00_preflight.md

Purpose: prove Codex read and understood the task boundary before editing.

Required content:

```text
patchlet id
attempt id
allowed product/runtime file
forbidden product/runtime files
report path
probe root
current state
patchlet goal
required validators
whether product/runtime edits are allowed yet
```

Gate implication:

```text
If missing, worker capsule gate fails.
If it names the wrong allowed file, worker capsule gate fails.
If it invents a different report/probe path, worker capsule gate fails.
```

## 8.2 01_investigation.md

Purpose: record what Codex inspected.

Required content:

```text
files inspected
commands run
facts observed
uncertain claims
assumptions
links to evidence ids when available
```

The orchestrator treats this as claim evidence, not truth.

## 8.3 02_probe_plan.md

Purpose: record the root-cause/proof probe plan before implementation.

Required content:

```text
minimal direct probe
controlled initial state
producer → transformer → consumer boundary
negative control
expected failing signal before fix
expected passing signal after fix
cleanup proof plan
durable probe artifact paths
```

Gate implication:

```text
If missing, COMPLETE should be rejected.
If no negative control is described, COMPLETE should be rejected.
If no cleanup proof plan exists, COMPLETE should be rejected.
```

## 8.4 03_implementation.md

Purpose: record implementation intent and actual edit summary.

Required content:

```text
file edited
why this file
what changed
why no other product/runtime file was edited
relation to invariant ids
affected probes
```

## 8.5 04_validation.md

Purpose: record validation commands and results.

Required content:

```text
commands run
exit codes
probe run paths
report validation result if known
regression result if any
cleanup proof result
```

Gate implication:

```text
If missing, COMPLETE should be rejected.
```

## 8.6 05_final_report.md

Purpose: Codex final claim.

Required content:

```text
FINAL_STATUS: PASS | FAIL | BLOCKED
patchlet_id
attempt_id
report path
probe root
summary
known unresolved issues
```

Important:

```text
FINAL_STATUS: PASS is only a claim.
It is never sufficient without wrapper gates.
```

---

# 9. Orchestrator-Owned Lifecycle Events

Native Codex hooks are not a correctness dependency. Instead, the orchestrator should write its own lifecycle event stream.

Canonical path:

```text
.codex-orchestrator/runs/P0001_attempt1/worker_events/events.jsonl
```

Approved event names:

```text
capsule_created
memory_written
stage_templates_written
prompt_written
worker_start
worker_exit
diff_captured
report_validation_start
report_validation_complete
probe_validation_start
probe_validation_complete
diff_validation_start
diff_validation_complete
wrapper_gate_start
wrapper_gate_complete
failure_recorded
state_transition_requested
state_transition_committed
```

Example event:

```json
{
  "schema_version": "1.0",
  "kind": "worker_event",
  "event": "worker_exit",
  "patchlet_id": "P0001",
  "attempt_id": "P0001_attempt1",
  "worker_mode": "real_codex",
  "execution_mode": "worktree",
  "exit_code": 1,
  "stdout_path": ".codex-orchestrator/runs/P0001_attempt1/stdout.txt",
  "stderr_path": ".codex-orchestrator/runs/P0001_attempt1/stderr.txt",
  "output_jsonl_path": ".codex-orchestrator/runs/P0001_attempt1/output.jsonl",
  "timestamp": "2026-07-02T00:00:00Z"
}
```

These events improve failure diagnosis and make worker lifecycle transparent.

---

# 10. Wrapper Gate Contract

The wrapper gate is the orchestrator’s final accept/reject verdict for one worker attempt.

Canonical path:

```text
.codex-orchestrator/runs/P0001_attempt1/gates/wrapper_gate_result.json
```

The wrapper gate must be written by the orchestrator, not Codex.

## 10.1 Gate Categories

Approved gate categories:

```text
worker_exit_gate
required_artifacts_gate
memory_gate
stage_gate
diff_gate
report_gate
probe_gate
final_status_gate
state_transition_gate
```

## 10.2 Gate Status Values

Approved gate result values:

```text
pass
fail
not_run
not_applicable
blocked
```

## 10.3 Wrapper Gate JSON Shape

```json
{
  "schema_version": "1.0",
  "kind": "wrapper_gate_result",
  "patchlet_id": "P0001",
  "attempt_id": "P0001_attempt1",
  "worker_mode": "real_codex",
  "execution_mode": "worktree",
  "accepted": false,
  "worker_claimed_final_status": "PASS",
  "gates": {
    "worker_exit_gate": {
      "status": "pass",
      "reasons": []
    },
    "required_artifacts_gate": {
      "status": "fail",
      "reasons": [
        "missing .codex-orchestrator/reports/P0001.json",
        "missing .artifacts/probes/P0001/run_001/row_ledger.jsonl"
      ]
    },
    "memory_gate": {
      "status": "pass",
      "reasons": []
    },
    "stage_gate": {
      "status": "fail",
      "reasons": [
        "missing worker_stage/02_probe_plan.md"
      ]
    },
    "diff_gate": {
      "status": "not_run",
      "reasons": [
        "worker failed before diff validation"
      ]
    },
    "report_gate": {
      "status": "fail",
      "reasons": [
        "patchlet report missing"
      ]
    },
    "probe_gate": {
      "status": "fail",
      "reasons": [
        "probe root missing"
      ]
    },
    "final_status_gate": {
      "status": "pass",
      "reasons": []
    }
  },
  "final_decision": "WORKER_FAILED",
  "next_state": "FAILURE_CLASSIFICATION_REQUIRED",
  "blind_retry_allowed": false,
  "validator_weakening_allowed": false
}
```

## 10.4 Important Rule

Even when the worker says:

```text
FINAL_STATUS: PASS
```

The wrapper can still reject the run.

This is not a contradiction. It is the system working correctly.

---

# 11. Patchlet Flow With Worker Capsule

The approved patchlet flow becomes:

```text
1. Orchestrator selects pending patchlet.
2. Orchestrator creates run attempt id, for example P0001_attempt1.
3. Orchestrator creates Worker Capsule directories.
4. Orchestrator writes worker_memory/TASK_CONTRACT.md.
5. Orchestrator writes worker_memory/KNOWN_FACTS.json.
6. Orchestrator writes worker_memory/ALLOWED_PATHS.json.
7. Orchestrator writes worker_memory/WRITE_THESE_FILES.md.
8. Orchestrator writes worker_stage templates.
9. Orchestrator writes worker_events/events.jsonl capsule_created event.
10. Orchestrator builds prompt pointing Codex to the capsule files.
11. Codex runs inside the execution root, usually a worktree.
12. Codex reads the local capsule files.
13. Codex writes worker_stage files as it works.
14. Codex writes report/probe artifacts.
15. Orchestrator captures stdout/stderr/output/diff.
16. Orchestrator validates memory/stage artifacts.
17. Orchestrator validates diff.
18. Orchestrator validates report.
19. Orchestrator validates probe artifacts.
20. Orchestrator writes wrapper_gate_result.json.
21. Orchestrator updates run_manifest.json.
22. Orchestrator transitions state only if gates permit it.
```

This flow makes the Codex execution inspectable even when it fails before report creation.

---

# 12. Transaction Group Crosscheck Capsule

Transaction verification should become more transparent by generating a transaction-level capsule.

Canonical path:

```text
.codex-orchestrator/transaction_groups/TG001/
```

Approved layout:

```text
.codex-orchestrator/transaction_groups/TG001/
  group_memory.md
  group_stage/
    00_inputs.md
    01_patchlet_report_matrix.md
    02_probe_crosscheck.md
    03_diff_scope_check.md
    04_group_verdict.md
  gates/
    group_gate_result.json
  patchlet_output_matrix.json
```

## 12.1 Transaction Group Crosschecks

The group verifier should crosscheck:

```text
all expected patchlets exist
all patchlets are in acceptable statuses
all patchlet reports validate
all patchlet probes validate
all patchlet diff gates passed
each patchlet references expected invariant ids
each patchlet references expected goal ids
each patchlet references expected evidence ids
each patchlet belongs to this transaction group
no patchlet contradicts another patchlet
no related patchlet failed while the group claims passed
repair patchlet substitutions are explicit and justified
```

## 12.2 Patchlet Output Matrix

Canonical path:

```text
.codex-orchestrator/transaction_groups/TG001/patchlet_output_matrix.json
```

Suggested shape:

```json
{
  "schema_version": "1.0",
  "kind": "patchlet_output_matrix",
  "transaction_group_id": "TG001",
  "patchlets": [
    {
      "patchlet_id": "P0001",
      "status": "COMPLETE",
      "report_valid": true,
      "probe_valid": true,
      "allowed_diff_valid": true,
      "memory_valid": true,
      "stage_valid": true,
      "wrapper_gate_accepted": true,
      "goal_ids": ["G001"],
      "invariant_ids": ["I001"],
      "evidence_ids": ["E001"],
      "graph_node_ids": ["N001"],
      "contradictions": []
    }
  ],
  "group_verdict": "PASSED"
}
```

## 12.3 Group Gate Result

Canonical path:

```text
.codex-orchestrator/transaction_groups/TG001/gates/group_gate_result.json
```

Suggested shape:

```json
{
  "schema_version": "1.0",
  "kind": "group_gate_result",
  "transaction_group_id": "TG001",
  "accepted": true,
  "patchlet_matrix_path": ".codex-orchestrator/transaction_groups/TG001/patchlet_output_matrix.json",
  "gates": {
    "patchlets_complete_gate": "pass",
    "reports_gate": "pass",
    "probes_gate": "pass",
    "diffs_gate": "pass",
    "memory_stage_gate": "pass",
    "contradiction_gate": "pass"
  },
  "reasons": [],
  "next_state": "TRANSACTION_VERIFICATION_COMPLETE"
}
```

---

# 13. Global Verification Proof Matrix

Global verification should become even more deterministic and transparent by adding a proof matrix before final verification.

Canonical path:

```text
.codex-orchestrator/global_verification/verification_matrix.json
```

Suggested layout:

```text
.codex-orchestrator/global_verification/
  global_memory.md
  global_stage/
    00_inputs.md
    01_goal_matrix.md
    02_invariant_matrix.md
    03_transaction_matrix.md
    04_failure_matrix.md
    05_final_verdict.md
  gates/
    global_gate_result.json
  verification_matrix.json
```

## 13.1 Global Crosschecks

Global verification should crosscheck:

```text
every master goal is proven or explicitly blocked
every invariant is proven or explicitly blocked
every transaction group passed
every patchlet report validates
every probe validates
every wrapper gate accepted for completed patchlets
every unresolved failure is accounted for
no unauthorized diffs remain
no blind retry occurred
state.json is consistent with final verification
run_manifest is consistent with final verification
repair cycles are properly linked to source failures
```

## 13.2 Verification Matrix

Suggested shape:

```json
{
  "schema_version": "1.0",
  "kind": "verification_matrix",
  "goals": [
    {
      "goal_id": "G001",
      "status": "PROVEN",
      "supporting_invariant_ids": ["I001"],
      "supporting_transaction_group_ids": ["TG001"],
      "unresolved_reasons": []
    }
  ],
  "invariants": [
    {
      "invariant_id": "I001",
      "status": "PROVEN",
      "supporting_patchlet_ids": ["P0001"],
      "supporting_probe_refs": [".artifacts/probes/P0001/run_001"],
      "unresolved_reasons": []
    }
  ],
  "transaction_groups": [
    {
      "transaction_group_id": "TG001",
      "status": "PASSED",
      "patchlet_output_matrix": ".codex-orchestrator/transaction_groups/TG001/patchlet_output_matrix.json"
    }
  ],
  "patchlets": [],
  "failures": [],
  "unresolved": [],
  "verdict": "DONE_ALLOWED"
}
```

Then `final_verification.json` should be the final conclusion over `verification_matrix.json`, not an isolated verdict.

---

# 14. Approved Gaps to Close

These are the approved gaps that this design should address.

## Gap 1 — Real Codex lacks a small working memory surface

Current state:

```text
The strict contract is injected into the subprompt.
That is useful, but actual Codex may still fail to produce artifacts.
```

Approved correction:

```text
Create run-local files:
- TASK_CONTRACT.md
- LIVE_MEMORY.md
- CURRENT_STAGE.md
- WRITE_THESE_FILES.md
```

The prompt should instruct Codex:

```text
First read worker_memory/TASK_CONTRACT.md.
Then write worker_stage/00_preflight.md.
Only then continue.
```

## Gap 2 — No explicit per-patchlet stage artifact requirement

Current state:

```text
Reports and probes exist.
Codex-authored stage files are not yet first-class required artifacts.
```

Approved correction:

```text
Require worker_stage files and gate them.
Use them to diagnose whether Codex understood the task.
```

## Gap 3 — Lifecycle events need formalization

Current state:

```text
Run artifacts and run_manifest exist.
A dedicated events.jsonl lifecycle stream is not yet first-class.
```

Approved correction:

```text
Add orchestrator-owned events.jsonl per attempt.
Do not rely on native Codex hooks for correctness.
```

## Gap 4 — Wrapper gate result should be first-class

Current state:

```text
Validators and run manifests exist.
There is no single per-attempt wrapper_gate_result.json explaining accept/reject across all gates.
```

Approved correction:

```text
Add gates/wrapper_gate_result.json.
Make it the canonical per-attempt verdict.
```

## Gap 5 — Group/global verification should become matrix-based

Current state:

```text
Transaction/global verification exists.
The verdict could be more transparent through matrices.
```

Approved correction:

```text
Add patchlet_output_matrix.json for transaction groups.
Add verification_matrix.json for global verification.
```

---

# 15. Implementation Strategy

The approved implementation order should be incremental and test-driven.

Do not implement group/global matrices before the per-worker capsule. The first priority is the worker capsule because it directly addresses the current real-Codex failure mode.

Recommended sequence:

```text
Phase 1 — Worker Capsule directory creation
Phase 2 — Worker memory files
Phase 3 — Worker stage templates
Phase 4 — Orchestrator-owned lifecycle events
Phase 5 — Wrapper gate result
Phase 6 — Real-Codex prompt integration with capsule files
Phase 7 — Worker capsule diagnostics integration
Phase 8 — Transaction patchlet output matrix
Phase 9 — Transaction group gate result
Phase 10 — Global verification matrix
Phase 11 — Global gate result
Phase 12 — Docs and release/status update
```

Each phase must be red-first and behavior-tested. Tests should inspect generated artifacts, not runtime source code.

---

# 16. Phase 1 — Worker Capsule Directory Creation

## Goal

Every patchlet attempt gets a stable capsule directory layout.

## Expected artifacts

```text
.codex-orchestrator/runs/P0001_attempt1/worker_memory/
.codex-orchestrator/runs/P0001_attempt1/worker_stage/
.codex-orchestrator/runs/P0001_attempt1/worker_events/
.codex-orchestrator/runs/P0001_attempt1/gates/
```

## Behavior

The orchestrator creates these directories before invoking the worker.

For worktree mode:

```text
execution_root = temporary worktree
artifact_root = target repo
capsule path = target repo .codex-orchestrator/runs/P0001_attempt1/
```

The capsule must live under the target artifact root, not under the worktree only.

## Tests

Add behavior tests such as:

```text
test_worker_capsule_direct_mode_creates_expected_directories
test_worker_capsule_worktree_mode_writes_capsule_under_target_artifact_root
test_worker_capsule_does_not_write_to_orchestrator_source_repo
test_worker_capsule_path_is_recorded_in_run_manifest
```

---

# 17. Phase 2 — Worker Memory Files

## Goal

Add orchestrator-written worker memory files before Codex runs.

Minimum files:

```text
worker_memory/TASK_CONTRACT.md
worker_memory/LIVE_MEMORY.md
worker_memory/LIVE_MEMORY.json
worker_memory/KNOWN_FACTS.json
worker_memory/ALLOWED_PATHS.json
worker_memory/CURRENT_STAGE.md
worker_memory/WRITE_THESE_FILES.md
```

## Tests

```text
test_worker_memory_task_contract_contains_patchlet_id_attempt_id_and_allowed_file
test_worker_memory_task_contract_contains_report_and_probe_paths
test_worker_memory_allowed_paths_json_matches_patchlet_allowed_file
test_worker_memory_live_memory_json_validates_schema
test_worker_memory_files_are_written_before_worker_start_event
```

## Gate implications

If these files are missing before worker start, the worker should not be invoked.

---

# 18. Phase 3 — Worker Stage Templates

## Goal

Create stage templates before Codex runs and require Codex to fill them.

Templates:

```text
worker_stage/00_preflight.md
worker_stage/01_investigation.md
worker_stage/02_probe_plan.md
worker_stage/03_implementation.md
worker_stage/04_validation.md
worker_stage/05_final_report.md
```

## Tests

```text
test_worker_stage_templates_are_created_before_codex_exec
test_worker_stage_preflight_template_contains_required_headings
test_worker_stage_probe_plan_template_contains_root_cause_requirements
test_worker_stage_final_report_template_requires_final_status_claim
```

## Notes

At first, these can be templates. Later gates can require Codex to fill them. The first implementation should avoid making real Codex impossible to run until prompt integration is complete.

---

# 19. Phase 4 — Orchestrator-Owned Lifecycle Events

## Goal

Add per-attempt `worker_events/events.jsonl`.

## Required events for first implementation

```text
capsule_created
memory_written
stage_templates_written
prompt_written
worker_start
worker_exit
wrapper_gate_start
wrapper_gate_complete
```

Later events can include:

```text
diff_captured
report_validation_start
report_validation_complete
probe_validation_start
probe_validation_complete
diff_validation_start
diff_validation_complete
failure_recorded
state_transition_committed
```

## Tests

```text
test_worker_events_jsonl_exists_for_successful_patchlet
test_worker_events_jsonl_exists_for_failed_worker
test_worker_events_include_worker_start_and_worker_exit
test_worker_events_include_exit_code_for_failed_real_codex_worker
test_worker_events_are_json_objects
```

---

# 20. Phase 5 — Wrapper Gate Result

## Goal

Add first-class wrapper gate result.

Path:

```text
.codex-orchestrator/runs/P0001_attempt1/gates/wrapper_gate_result.json
```

## Tests

```text
test_wrapper_gate_result_exists_for_successful_patchlet
test_wrapper_gate_result_exists_for_worker_failed_attempt
test_wrapper_gate_result_rejects_missing_report_even_if_final_status_claim_pass
test_wrapper_gate_result_records_report_probe_diff_gate_statuses
test_wrapper_gate_result_sets_blind_retry_allowed_false
test_wrapper_gate_result_is_written_by_orchestrator_not_worker
```

## Important behavior

Wrapper gate must not turn failures into success. It must explain why an attempt is accepted or rejected.

---

# 21. Phase 6 — Real-Codex Prompt Integration With Capsule Files

## Goal

Update the real-Codex prompt/subprompt chain to point Codex at the capsule files.

Prompt should instruct:

```text
Before doing any work:
1. Read worker_memory/TASK_CONTRACT.md.
2. Read worker_memory/WRITE_THESE_FILES.md.
3. Write worker_stage/00_preflight.md.
4. Only edit the allowed product/runtime file.
5. Write report/probes to exact paths.
6. Write worker_stage/05_final_report.md with FINAL_STATUS.
```

## Tests

Generated subprompt artifact tests may inspect prompt text because the prompt is the specified artifact.

```text
test_real_codex_subprompt_mentions_task_contract_path
test_real_codex_subprompt_mentions_write_these_files_path
test_real_codex_subprompt_requires_preflight_stage_file
test_real_codex_subprompt_requires_final_report_stage_file
test_fake_codex_contract_sensitive_worker_requires_capsule_instruction
```

---

# 22. Phase 7 — Worker Capsule Diagnostics Integration

## Goal

Integrate capsule information into the existing real-Codex failure diagnosis artifacts.

Diagnosis should include:

```text
worker_memory paths
worker_stage paths
worker_events path
wrapper_gate_result path
which stage files are missing or filled
whether Codex read or referenced the task contract if known
```

## Tests

```text
test_real_codex_failure_diagnosis_links_worker_capsule_paths
test_real_codex_failure_diagnosis_reports_missing_stage_files
test_real_codex_failure_diagnosis_reports_wrapper_gate_result
test_real_codex_failure_diagnosis_reports_worker_events
```

---

# 23. Phase 8 — Transaction Patchlet Output Matrix

## Goal

Make transaction verification generate a matrix of patchlet outputs before verdict.

Path:

```text
.codex-orchestrator/transaction_groups/TG001/patchlet_output_matrix.json
```

## Tests

```text
test_transaction_group_writes_patchlet_output_matrix
test_patchlet_output_matrix_includes_report_probe_diff_and_wrapper_gate_status
test_patchlet_output_matrix_detects_patchlet_invariant_mismatch
test_patchlet_output_matrix_detects_contradictory_patchlet_statuses
```

---

# 24. Phase 9 — Transaction Group Gate Result

## Goal

Add group-level gate verdict.

Path:

```text
.codex-orchestrator/transaction_groups/TG001/gates/group_gate_result.json
```

## Tests

```text
test_group_gate_result_exists_on_pass
test_group_gate_result_exists_on_fail
test_group_gate_result_references_patchlet_output_matrix
test_group_gate_result_blocks_group_when_any_patchlet_wrapper_gate_failed
```

---

# 25. Phase 10 — Global Verification Matrix

## Goal

Generate a deterministic matrix before final verification.

Path:

```text
.codex-orchestrator/global_verification/verification_matrix.json
```

## Tests

```text
test_global_verification_writes_verification_matrix
test_verification_matrix_links_goals_invariants_transaction_groups_patchlets
test_verification_matrix_blocks_done_when_group_gate_failed
test_verification_matrix_blocks_done_when_unresolved_failure_exists
```

---

# 26. Phase 11 — Global Gate Result

## Goal

Add a global gate result before final verification.

Path:

```text
.codex-orchestrator/global_verification/gates/global_gate_result.json
```

## Tests

```text
test_global_gate_result_exists_before_done
test_global_gate_result_references_verification_matrix
test_global_gate_result_done_allowed_only_when_all_required_gates_pass
test_final_verification_derives_from_global_gate_result
```

---

# 27. Acceptance Criteria for the Worker Capsule Feature

The feature is accepted only if:

```text
Every patchlet attempt has a capsule directory.
Every real_codex attempt has TASK_CONTRACT.md and WRITE_THESE_FILES.md.
Every attempt has lifecycle events.
Every attempt has wrapper_gate_result.json.
Codex cannot mark success without gates passing.
Worker memory is scoped, not global.
Stage artifacts are required or at least gate-visible.
Failed real-Codex attempts diagnose missing stage/memory/artifact files.
Group verification can produce patchlet_output_matrix.json.
Global verification can produce verification_matrix.json.
Default tests do not run real Codex.
No validator is weakened.
No blind retry is introduced.
```

---

# 28. Documentation Requirements

Docs should clearly explain:

```text
What a Worker Capsule is.
Why it exists.
Why it is per-attempt, not global.
How it adapts codex-compaction-memory-lab ideas.
Why compaction is out of scope.
Why native Codex hooks are optional telemetry.
How to inspect TASK_CONTRACT.md.
How to inspect worker_stage files.
How to inspect events.jsonl.
How to inspect wrapper_gate_result.json.
How transaction patchlet_output_matrix.json works.
How global verification_matrix.json works.
Why Codex memory is not proof.
Why FINAL_STATUS: PASS is not proof.
Why validators cannot be weakened.
```

Recommended docs files:

```text
README.md
docs/worker_capsules.md
docs/real_codex_smoke.md
docs/worktrees.md
docs/autonomous_loop.md
docs/transaction_groups.md
docs/global_verification.md
IMPLEMENTATION_STATUS.md
```

---

# 29. Final Approved Summary

The approved design is to adapt the best lessons of `codex-compaction-memory-lab` into the orchestrator as **Codex Worker Capsules**.

The design does not copy the lab’s repo-level memory model. It transforms it into per-attempt, per-transaction, and global verification evidence capsules.

The approved design is:

```text
Layer 1 — Worker Capsule
  per codex exec
  memory
  stage artifacts
  event log
  wrapper gates

Layer 2 — Transaction Crosscheck
  per transaction group
  patchlet_output_matrix.json
  group_gate_result.json
  group_memory.md

Layer 3 — Global Proof Matrix
  per workflow
  verification_matrix.json
  global_gate_result.json
  final_verification.json
```

The first implementation should start with Layer 1 because it directly targets the current real-Codex failure mode.

The final governing principle remains:

```text
Codex is an unreliable worker until durable artifacts and external validators prove success.
```
