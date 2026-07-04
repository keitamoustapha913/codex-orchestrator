# Codex Orchestrator — Rerun, Reset, and Workflow Identity Evidence-First Plan

This file contains the next builder handoff and the post-evidence implementation plan backlog.

The first builder task is evidence-only. Do not implement until the evidence report is returned and the architecture is updated from actual local facts.

---

# Part 1 — Evidence-only builder prompt

## Step 0 — Stop before editing anything

You are the Builder Layer for the local `codex-orchestrator` repository.

This is an evidence-only investigation prompt.

This is not an implementation prompt.

Do not fix anything.

Do not change code.

Do not change tests.

Do not change docs.

Do not change schemas.

Do not change prompt templates.

Do not change generated workflow artifacts.

Do not run real Codex.

Do not run `cxor auto` again against `/tmp/cxor-target`.

Do not run `apply-results` again.

Do not delete `.codex-orchestrator/`.

Do not delete `.artifacts/`.

Do not run `git clean`.

Do not reset, stash, commit, or modify `/tmp/cxor-target`.

The operator reproduced a new issue after the `v0.1.0-rc3` checkpoint.

The first run worked:

```text
app.py before: return "not ok"
cxor auto --worker-mode real_codex --use-worktree --live-progress reached DONE
apply-results --mode working-tree changed app.py to return "ok"
```

Then the operator manually changed `app.py`:

```python
def main():
    return "ok me"
```

Then the operator reran `cxor auto` on the same master prompt. It immediately reported `DONE` and appeared to reuse the previous workflow.

Then the operator created a different master prompt:

```text
Make app return me and prove it.
```

and ran:

```bash
CODEX_PATCHLET_TIMEOUT_SECONDS=600 \
uv run --no-sync cxor auto \
  --repo /tmp/cxor-target \
  --master /tmp/cxor-target/master_prompt_me.md \
  --until DONE \
  --worker-mode real_codex \
  --use-worktree \
  --live-progress
```

It still immediately reported `DONE`.

The operator's major issues are:

```text
1. If the target repo changes after a fix, rerunning cxor does nothing.
2. If the master prompt changes, rerunning cxor still does nothing.
3. There is no clear supported way to clear previous cxor work and run a new prompt.
4. Live progress appears to duplicate or replay previous workflow events.
```

Your job is to gather evidence so the Architect Layer can identify root causes and design the fix.

Do not fix.

Do not patch.

Do not infer without evidence.

---

## Step 1 — Investigation title and output files

Use this title:

```text
Evidence Report — Direct Auto Terminal Workflow Reuse, Changed Prompt Ignored, and Missing Reset/New-Run Semantics
```

Create only these evidence files:

```text
rerun_reset_workflow_identity_evidence_report.md
rerun_reset_workflow_identity_raw_commands.md
rerun_reset_workflow_identity_artifact_index.json
```

If another evidence artifact is necessary, prefix it with:

```text
rerun_reset_workflow_identity_
```

---

## Step 2 — Baseline capture

Run from the orchestrator repo:

```bash
export UV_CACHE_DIR=/tmp/uv-cache

date -u +"%Y-%m-%dT%H:%M:%SZ"
pwd
git status --short
git rev-parse --show-toplevel
git rev-parse HEAD
git branch --show-current

uv run --no-sync python --version
uv --version
codex --version || true
uv run --no-sync cxor --version
uv run --no-sync codex-orchestrator --version
uv run --no-sync python -m codex_orchestrator --version
```

Record investigation start, repo root, HEAD, branch, git status, Python, uv, codex, and cxor version.

Do not run the full suite unless explicitly instructed.

---

## Step 3 — Capture target repository state

Target:

```text
/tmp/cxor-target
```

Run:

```bash
target=/tmp/cxor-target

test -d "$target" && echo TARGET_EXISTS || echo TARGET_MISSING
git -C "$target" status --short
git -C "$target" status --porcelain=v1
git -C "$target" rev-parse --show-toplevel
git -C "$target" rev-parse HEAD
git -C "$target" rev-parse HEAD^{tree}
git -C "$target" branch --show-current
git -C "$target" log --oneline --decorate -10
git -C "$target" diff -- app.py || true
git -C "$target" diff --stat || true
git -C "$target" ls-files --stage

echo '--- app.py'
sed -n '1,120p' "$target/app.py" 2>/dev/null || true

echo '--- master_prompt.md'
sed -n '1,120p' "$target/master_prompt.md" 2>/dev/null || true

echo '--- master_prompt_me.md'
sed -n '1,120p' "$target/master_prompt_me.md" 2>/dev/null || true

sha256sum "$target/master_prompt.md" 2>/dev/null || true
sha256sum "$target/master_prompt_me.md" 2>/dev/null || true
sha256sum "$target/app.py" 2>/dev/null || true

git -C "$target" worktree list --porcelain || true
find "$target" -maxdepth 3 -type d | sort
find "$target" -maxdepth 4 -type f | sort | sed -n '1,600p'
```

Record target existence, branch, HEAD, tree SHA, git status, whether `app.py` is dirty, whether `master_prompt_me.md` is tracked or untracked, file contents, prompt hashes, worktrees, and artifact directories.

---

## Step 4 — Capture workflow state and terminal result

Run:

```bash
wf=/tmp/cxor-target/.codex-orchestrator

test -d "$wf" && echo WORKFLOW_EXISTS || echo WORKFLOW_MISSING
find "$wf" -maxdepth 4 -type f | sort | sed -n '1,1000p'

cat "$wf/state.json" 2>/dev/null || true
cat "$wf/run_manifest.json" 2>/dev/null || true
cat "$wf/operator_events.jsonl" 2>/dev/null | tail -n 240 || true
cat "$wf/prompt_index.json" 2>/dev/null || true
cat "$wf/loop_governor.json" 2>/dev/null || true
cat "$wf/goal_spec.json" 2>/dev/null || true
cat "$wf/patchlets/patchlet_index.json" 2>/dev/null || true
cat "$wf/patchlets/transaction_groups.json" 2>/dev/null || true
cat "$wf/integration/integration_state.json" 2>/dev/null || true
cat "$wf/integration/accepted_changes.jsonl" 2>/dev/null || true
cat "$wf/integration/final_diff.patch" 2>/dev/null || true
find "$wf/integration" -maxdepth 5 -type f | sort -exec sed -n '1,220p' {} \; 2>/dev/null || true
```

Record state stage, run ID, workflow ID if present, current patchlet, terminal state, manifest entries, event count, workflow_started event count, prompt index entries, prompt path/hash records, integration SHA, final diff, accepted patchlets, and apply-results artifacts.

---

## Step 5 — Determine whether second and third auto runs created new events or replayed old events

Analyze `operator_events.jsonl`.

Run:

```bash
uv run --no-sync python - <<'PY'
import json, pathlib
p = pathlib.Path('/tmp/cxor-target/.codex-orchestrator/operator_events.jsonl')
if not p.exists():
    print('NO_OPERATOR_EVENTS')
    raise SystemExit
for line in p.read_text().splitlines():
    if not line.strip():
        continue
    e = json.loads(line)
    if e.get('event_type') in {'workflow_started','patchlet_started','patchlet_worker_started','patchlet_worker_exited','workflow_done','prompt_index_updated'}:
        print(json.dumps({
            'event_id': e.get('event_id'),
            'created_at': e.get('created_at'),
            'event_type': e.get('event_type'),
            'summary': e.get('summary'),
            'patchlet_id': e.get('patchlet_id'),
            'attempt_id': e.get('attempt_id'),
            'prompt_id': e.get('prompt_id'),
            'prompt_path': e.get('prompt_path'),
            'details': e.get('details'),
        }, sort_keys=True))
PY
```

Record how many `workflow_started` events exist, whether timestamps match each invocation, whether old patchlet events were replayed, whether event IDs advance, whether repeated PR000003 updates are new or stale, and whether operator event details include command invocation identity.

---

## Step 6 — Inspect run attempts and command artifacts

Run:

```bash
runs=/tmp/cxor-target/.codex-orchestrator/runs
find "$runs" -maxdepth 3 -type f | sort | sed -n '1,1000p' || true

for d in "$runs"/*_attempt*; do
  [ -d "$d" ] || continue
  echo "===== ATTEMPT $d"
  find "$d" -maxdepth 4 -type f | sort
  echo '--- command.json'
  sed -n '1,240p' "$d/command.json" 2>/dev/null || true
  echo '--- progress tail'
  tail -n 80 "$d/progress.jsonl" 2>/dev/null || true
  echo '--- stdout tail'
  tail -n 80 "$d/stdout.txt" 2>/dev/null || true
  echo '--- report ingestion'
  sed -n '1,240p' "$d/gates/report_ingestion_result.json" 2>/dev/null || true
  echo '--- wrapper gate'
  sed -n '1,240p' "$d/gates/wrapper_gate_result.json" 2>/dev/null || true
  echo '--- target hygiene'
  sed -n '1,240p' "$d/gates/target_hygiene_gate_result.json" 2>/dev/null || true
  echo '--- prompt first 120 lines'
  sed -n '1,120p' "$d/codex_task_prompt.md" 2>/dev/null || true
done
```

Record the number of attempt directories, whether second/third reruns created new attempt directories, whether worker actually invoked real Codex on reruns, whether command artifacts match rerun timestamps, whether prompt content reflects `master_prompt_me.md`, and whether old prompt content was reused.

---

## Step 7 — Inspect apply-results artifacts

Run:

```bash
find /tmp/cxor-target/.codex-orchestrator -type f \
  \( -name '*apply*' -o -path '*/apply_results/*' -o -name '*result*.json' \) \
  | sort | sed -n '1,400p'

find /tmp/cxor-target/.codex-orchestrator/integration -maxdepth 5 -type f | sort | while read f; do
  echo "===== $f"
  sed -n '1,260p' "$f" || true
done
```

Record apply-results result path, mode, mutated_working_tree, integration ref, integration SHA, target HEAD SHA at apply time, and whether later auto considered this state.

---

## Step 8 — Inspect CLI behavior and source semantics read-only

Run from orchestrator repo:

```bash
uv run --no-sync cxor auto --help
uv run --no-sync cxor status --help
uv run --no-sync cxor monitor --help
uv run --no-sync cxor prompts --help
uv run --no-sync cxor apply-results --help

rg -n "cmd_auto|run_auto|resume|DONE|state.stage|workflow_started|operator_events|live_progress|prompt_index|master_prompt|goal_spec|apply-results|apply_results|reset|archive|workflow" src tests docs README.md IMPLEMENTATION_STATUS.md || true
```

Inspect likely files:

```bash
sed -n '1,3200p' src/codex_orchestrator/cli.py
sed -n '1,3200p' src/codex_orchestrator/stages/init.py
sed -n '1,3200p' src/codex_orchestrator/stages/status.py
sed -n '1,3200p' src/codex_orchestrator/stages/run_patchlet.py
sed -n '1,3200p' src/codex_orchestrator/operator_progress.py
sed -n '1,3200p' src/codex_orchestrator/operator_events.py
sed -n '1,3200p' src/codex_orchestrator/prompt_index.py
sed -n '1,3200p' src/codex_orchestrator/integration_state.py
```

Record facts only: whether `cxor auto` has `--new-run`, `--resume`, prompt hash comparison, target state comparison, dirty preflight, DONE short-circuit, live progress cursor behavior, status workflow identity, and reset/archive command support.

---

## Step 9 — Run read-only CLI status/prompts/monitor outputs

These commands are read-only:

```bash
uv run --no-sync cxor status --repo /tmp/cxor-target --json
uv run --no-sync cxor prompts --repo /tmp/cxor-target --json
uv run --no-sync cxor monitor --repo /tmp/cxor-target --limit 80 --json
```

Record whether status explains terminal `DONE`, whether status mentions the current requested master prompt, whether status mentions dirty target, whether prompts show old or new prompt, and whether monitor output distinguishes invocations.

---

## Step 10 — Build artifact index

Create:

```text
rerun_reset_workflow_identity_artifact_index.json
```

Index:

```text
/tmp/cxor-target/.codex-orchestrator
/tmp/cxor-target/.artifacts
/tmp/cxor-target/.git/worktrees
```

Categories include state, manifest, operator_event, prompt_index, prompt, worker outputs, gates, reports, probes, failures, repairs, loop_governor, integration, apply_results, verifier, lock, worktree_metadata, and unknown.

---

## Step 11 — Evidence graphs required in final report

Include Mermaid graphs for observed stale terminal reuse, desired preflight decision path, event replay problem, and reset/archive path.

---

## Step 12 — Root-cause evidence matrix

Include this table:

```text
Candidate Root Cause | Evidence For | Evidence Against | Proven Status | Missing Evidence | Impacted Architecture Area
```

Include at least:

1. `cxor auto` returns immediately when existing state is `DONE`.
2. master prompt path/content is not compared on rerun.
3. target HEAD/tree/dirty status is not compared on rerun.
4. apply-results working-tree mutation is not considered by rerun preflight.
5. dirty product file does not block rerun.
6. direct auto live progress replays stale operator events.
7. repeated `workflow_started` lines are newly appended events.
8. repeated `workflow_started` lines are stale replayed events.
9. prompt index is reused without new workflow namespace.
10. run IDs and patchlet IDs are not workflow-scoped.
11. no reset/archive command exists.
12. existing artifacts cannot be safely cleared by CLI.
13. status command lacks requested-vs-existing identity comparison.
14. new prompt file untracked status affects behavior.
15. auto lacks `--new-run` or equivalent.

---

## Step 13 — Final evidence report format

Return exactly this structure:

```text
# Evidence Report — Direct Auto Terminal Workflow Reuse, Changed Prompt Ignored, and Missing Reset/New-Run Semantics

## 1. Investigation scope
## 2. Operator scenario
## 3. Baseline
## 4. Target repository state
## 5. Existing workflow state
## 6. Rerun behavior evidence
## 7. Live progress replay evidence
## 8. Source and CLI evidence
## 9. Status/prompts/monitor evidence
## 10. Artifact index
## 11. Evidence graphs
## 12. Root-cause evidence matrix
## 13. Proven facts
## 14. Strongly supported but not fully proven facts
## 15. Disproven hypotheses
## 16. Unknowns and missing evidence
## 17. Architecture input questions
## 18. Raw commands appendix
## 19. Final git status
## 20. Final conclusion
```

Do not propose fixes in the report.

---

# Part 2 — Post-evidence implementation plan backlog

This section is not to be executed until the evidence report is returned and reviewed.

## Phase 1 — Workflow identity model

Add `workflow_identity.json` and a deterministic `goal_fingerprint`.

Tests:

- identity includes prompt SHA
- identity includes target HEAD/tree
- identity includes command options
- fingerprint changes when prompt content changes
- fingerprint changes when target HEAD changes
- fingerprint does not change with timestamps

## Phase 2 — Rerun preflight gate

Add `rerun_preflight_result.json` and a gate before auto initialization.

Tests:

- fresh target accepted
- existing terminal same identity reports terminal result
- existing terminal different prompt refused
- existing terminal changed target refused
- dirty product file refused
- operator guidance includes next commands

## Phase 3 — Direct auto CLI semantics

Add explicit flags:

```bash
--new-run
--resume
--rerun-policy refuse|resume|new
```

Tests:

- help includes flags
- changed prompt requires `--new-run`
- in-progress different identity refuses
- same identity resume works

## Phase 4 — Workflow registry and namespace

Implement either full workflow namespace or archive-before-new-run.

Tests:

- new run does not overwrite previous DONE artifacts
- workflow registry lists old/new workflows
- current pointer is updated atomically
- prompts/status/monitor can select current workflow

## Phase 5 — Reset/archive commands

Add:

```bash
cxor workflow list --repo <repo>
cxor workflow current --repo <repo> --json
cxor workflow archive --repo <repo>
cxor workflow reset --repo <repo> --archive --yes
```

Tests:

- archive manifest hashes files
- reset refuses destructive deletion without confirmation
- reset does not delete product files
- reset preserves evidence by default
- after reset, new auto can initialize

## Phase 6 — Live progress cursor hardening

Direct auto live progress must start after the event cursor captured at invocation start.

Tests:

- second invocation does not print old patchlet events
- monitor can still replay old events
- `--since` works
- duplicate `workflow_started` lines are not printed from stale events

## Phase 7 — Status/prompts/monitor workflow-awareness

Extend operator commands to report workflow identity.

Tests:

- status shows workflow_id and goal_fingerprint
- status detects requested prompt mismatch if `--master` is supplied
- prompts can list by workflow
- monitor can follow current workflow only

## Phase 8 — Apply-results rerun guidance

After `apply-results --mode working-tree`, write rerun guidance in apply result or status.

Tests:

- working-tree apply result records mutated target
- status recommends commit/stash/reset before new workflow if product dirty
- new workflow refuses dirty product file by default

## Phase 9 — Docs

Update README, docs/cli.md, docs/autonomous_loop.md, docs/release.md, and the step-by-step usage guide.

Docs must explain how to rerun after a previous `DONE`, how to start a new workflow, how to reset/archive old artifacts, why dirty product files block rerun, and how to commit apply-results output before new workflow.

## Phase 10 — Full regression and manual smoke

Final deterministic commands:

```bash
uv run --no-sync pytest -q
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py
```

Manual smoke after implementation:

```bash
# First prompt: make app return ok
# apply-results working-tree
# commit result
# second prompt: make app return me
# cxor auto --new-run --live-progress
```

Expected:

- second run starts a new workflow
- prompt hash differs
- P0001 prompt reflects new master prompt
- live progress only shows second invocation events
- apply-results can update working tree to new desired result

---

# Part 3 — Non-negotiable implementation constraints after evidence

When implementation eventually starts:

1. Do not run real Codex in default tests.
2. Do not delete evidence without archive.
3. Do not make reset destructive by default.
4. Do not silently reuse terminal workflows for changed goals.
5. Do not start a new workflow from a dirty product working tree by default.
6. Do not replay old events in direct auto live progress.
7. Do not weaken report ingestion, target hygiene, checkpoint validation, or wrapper gates.
8. Do not regress `v0.1.0-rc3` live real-Codex DONE path.
