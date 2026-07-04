# Codex Orchestrator — Step-by-Step Usage Guide

Version target: `v0.1.0-rc3` release-candidate workflow  
Primary CLI: `cxor`  
Primary goal: run a durable autonomous root-cause probe-gated loop until `DONE`, with operator-visible progress, prompt visibility, report-ingestion safety, structured evidence, and clean target-repo product files until explicit result application.

---

## 0. Current release-candidate proof

The current release-candidate checkpoint is:

```text
v0.1.0-rc3
```

The release-candidate commit recorded in the workflow was:

```text
dd2b49df3e1f62b64487099b06a1359e163003ca
```

The current deterministic proof is:

```text
1212 passed, 2 skipped
```

The latest manual real-Codex direct-auto smoke proof reached:

```text
DONE
```

The latest live smoke target preserved in release docs is:

```text
/tmp/cxor-target-report-contract-smoke-20260703T203745Z
```

## 0.1 Rerun, Reset, And New Workflow Identity

Every new `cxor auto` workflow writes
`.codex-orchestrator/workflow_identity.json` and computes a goal fingerprint
from target HEAD/tree, dirty status, master prompt path and SHA-256, worker
mode, worktree mode, and `--until`.

Rerunning `cxor auto` on a target with an existing workflow is intentional:

- same goal fingerprint and existing `DONE`: returns existing DONE with an
  explicit message;
- changed prompt path or changed prompt content: refuses unless `--new-run` or
  `--force-new-run` is used;
- dirty product/runtime target: refuses unless `--allow-dirty-target` is used;
- old evidence is preserved by `cxor archive` and `cxor reset --archive`.

Use:

```bash
cxor workflows --repo /path/to/target
cxor auto --repo /path/to/target --master /path/to/new_prompt.md --new-run
cxor archive --repo /path/to/target
cxor reset --repo /path/to/target --archive
```

`cxor auto --live-progress` creates an invocation cursor under
`.codex-orchestrator/invocations/` so stale operator events are not replayed as
current progress.

The latest live smoke confirmed:

```text
Worker: P0001_attempt1 exited 0
Report status: COMPLETE
Report ingestion: accepted
Report normalization: not needed in that run
Wrapper gate: accepted
Target hygiene: passed
Integration validation: passed
Workflow: DONE
Target product files: clean
```

This guide supersedes the older `v0.1.0-rc2` usage guide. The major additions since `rc2` are:

```text
direct cxor auto --live-progress
operator_events.jsonl
cxor monitor
cxor status --json / --watch
cxor prompts
prompt_index.json
loop_governor.json
raw/canonical report ingestion
safe probe_artifact_refs normalization
structured report_validation_errors.json
report_ingestion_result.json
report-contract prompt hardening
specific loop signatures such as probe_artifact_refs_not_objects
```

---

## 1. What this tool does

`codex-orchestrator` is a local CLI that runs Codex as a disposable worker inside a durable workflow owned by the orchestrator.

The orchestrator owns:

- workflow state
- patchlets
- transaction groups
- worker prompts
- prompt indexes
- Worker Capsule contracts
- probes
- raw reports
- canonical normalized reports
- report-ingestion gates
- report-validation errors
- wrapper gates
- target hygiene checks
- integration checkpoints
- run manifests
- operator events
- loop governance
- diagnosis
- repair/regeneration routing
- final verification
- evidence bundle validation/export

Codex is treated as a worker. Codex may propose edits and write required evidence, but the orchestrator decides whether the attempt is accepted.

The normal target end state is:

```text
DONE
```

A `safe_failure` is not `DONE`. It means the orchestrator stopped safely and preserved evidence.

---

## 2. Mental model

There are three important roots.

```text
orchestrator repo
  The repository that contains the cxor CLI implementation.

target repo
  The repository you want the orchestrator to work on.
  Durable workflow artifacts are written here.

execution root / worktree
  A temporary worktree where product/runtime edits happen.
  This protects the target repo from accidental dirty product files.
```

The target repo receives durable artifacts under:

```text
<target>/.codex-orchestrator/
<target>/.artifacts/probes/
```

Direct target workflow artifacts include:

```text
.codex-orchestrator/state.json
.codex-orchestrator/run_manifest.json
.codex-orchestrator/operator_events.jsonl
.codex-orchestrator/prompt_index.json
.codex-orchestrator/loop_governor.json
.codex-orchestrator/reports/<PATCHLET>.raw.json
.codex-orchestrator/reports/<PATCHLET>.json
.codex-orchestrator/runs/<ATTEMPT>/gates/report_ingestion_result.json
.codex-orchestrator/runs/<ATTEMPT>/gates/report_validation_errors.json
.codex-orchestrator/runs/<ATTEMPT>/gates/wrapper_gate_result.json
.codex-orchestrator/runs/<ATTEMPT>/gates/target_hygiene_gate_result.json
```

Operator real-Codex smoke runbook evidence is stored under the orchestrator repo:

```text
.operator-runs/real-codex-smoke/
.operator-runs/exports/
```

---

## 3. Install and verify the CLI

### 3.1 Use from the orchestrator repo with `uv`

From the `codex-orchestrator` repository:

```bash
export UV_CACHE_DIR=/tmp/uv-cache

uv run --no-sync python --version
uv run --no-sync cxor --version
uv run --no-sync codex-orchestrator --version
uv run --no-sync python -m codex_orchestrator --version
```

Expected CLI version output:

```text
codex-orchestrator 0.1.0
```

### 3.2 Optional editable install from source

Use this when you want `cxor` callable from outside the orchestrator repo.

```bash
uv venv /tmp/cxor-install-check-venv --python 3.10
uv pip install --python /tmp/cxor-install-check-venv/bin/python -e .

cd /tmp
/tmp/cxor-install-check-venv/bin/cxor --version
/tmp/cxor-install-check-venv/bin/codex-orchestrator --version
```

Expected:

```text
codex-orchestrator 0.1.0
```

---

## 4. Verify the deterministic suite before serious use

From the orchestrator repo:

```bash
export UV_CACHE_DIR=/tmp/uv-cache
uv run --no-sync pytest -q
```

The current `v0.1.0-rc3` release-candidate evidence passed with:

```text
1212 passed, 2 skipped
```

Also verify that the real-Codex smoke test remains opt-in by default:

```bash
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py
```

Expected default behavior:

```text
1 skipped
```

---

## 5. Prepare a target repository

The target must be a Git repository.

Example minimal target:

```bash
mkdir -p /tmp/cxor-target
cd /tmp/cxor-target

git init
cat > app.py <<'PY'
def main():
    return "not ok"
PY

cat > master_prompt.md <<'MD'
Make app return ok and prove it.
MD

git add app.py master_prompt.md
git commit -m "Initial target"
```

Before running the orchestrator, confirm product files are clean:

```bash
git status --short
```

The orchestrator will write artifacts under:

```text
/tmp/cxor-target/.codex-orchestrator/
/tmp/cxor-target/.artifacts/probes/
```

These artifact directories are expected. They are durable evidence, not product/runtime source edits.

---

## 6. Run the autonomous loop in deterministic mock mode

Use mock mode first when validating the workflow or debugging the CLI.

From the orchestrator repo:

```bash
uv run --no-sync cxor auto \
  --repo /tmp/cxor-target \
  --master /tmp/cxor-target/master_prompt.md \
  --until DONE \
  --worker-mode mock \
  --use-worktree
```

Expected successful end state:

```text
DONE
```

After the run, inspect target artifacts:

```bash
find /tmp/cxor-target/.codex-orchestrator -maxdepth 3 -type f | sort
find /tmp/cxor-target/.artifacts/probes -maxdepth 4 -type f | sort
```

Validate integration artifacts:

```bash
uv run --no-sync cxor validate-integration-artifacts --repo /tmp/cxor-target
```

Expected:

```json
{
  "valid": true
}
```

The exact JSON has more fields, but `valid: true` is the key result.

---

## 7. Run direct `cxor auto` with real Codex and live progress

Real Codex is opt-in. Use it only after deterministic mode is healthy.

### 7.1 Confirm Codex CLI is available

```bash
codex --version
which codex
```

The release-candidate evidence used:

```text
codex-cli 0.142.4
```

### 7.2 Recommended direct real-Codex command

Use `--live-progress` for direct `cxor auto`; it prints concise operator progress without dumping raw Codex JSON or full prompt bodies.

```bash
CODEX_PATCHLET_TIMEOUT_SECONDS=600 \
uv run --no-sync cxor auto \
  --repo /tmp/cxor-target \
  --master /tmp/cxor-target/master_prompt.md \
  --until DONE \
  --worker-mode real_codex \
  --use-worktree \
  --live-progress
```

Expected successful end state:

```text
DONE
```

### 7.3 Live progress examples

Direct auto live progress is concise and stage-level:

```text
[cxor +000s] workflow started repo=/tmp/cxor-target until=DONE worker=real_codex
[cxor +000s] Started patchlet P0001: app.py — worker task
[cxor +000s] Prompt saved for P0001_attempt1.
[cxor +000s] Worker started for P0001_attempt1 mode=real_codex.
[cxor +151s] Worker exited for P0001_attempt1 code=0.
[cxor +151s] Report ingestion passed for P0001.
[cxor +151s] Report validation passed for P0001: COMPLETE.
[cxor +151s] Wrapper gate accepted P0001_attempt1.
[cxor +151s] Workflow reached DONE.
```

For report normalization, live progress may show:

```text
[cxor +118s] report ingestion P0002 normalized 2 probe artifact path refs.
[cxor +119s] report P0002 valid after canonicalization.
```

For repeated failures, live progress may show:

```text
[cxor +447s] Repeated failure signature probe_artifact_refs_not_objects seen 3 times across P0001, P0002, P0003; continuing in warning mode.
```

### 7.4 Quiet mode

To explicitly suppress terminal progress while still writing durable events:

```bash
uv run --no-sync cxor auto \
  --repo /tmp/cxor-target \
  --master /tmp/cxor-target/master_prompt.md \
  --until DONE \
  --worker-mode real_codex \
  --use-worktree \
  --no-live-progress
```

### 7.5 Progress format and interval

Compact format is the normal operator format:

```bash
uv run --no-sync cxor auto \
  --repo /tmp/cxor-target \
  --master /tmp/cxor-target/master_prompt.md \
  --until DONE \
  --worker-mode real_codex \
  --use-worktree \
  --live-progress \
  --progress-format compact \
  --progress-interval-seconds 15
```

JSONL progress format prints one structured operator event per line:

```bash
uv run --no-sync cxor auto \
  --repo /tmp/cxor-target \
  --master /tmp/cxor-target/master_prompt.md \
  --until DONE \
  --worker-mode real_codex \
  --use-worktree \
  --live-progress \
  --progress-format jsonl
```

---

## 8. Watch a running workflow from a second terminal

The direct-auto visibility system writes:

```text
<target>/.codex-orchestrator/operator_events.jsonl
```

Use the following read-only commands from another terminal.

### 8.1 Monitor operator events

```bash
uv run --no-sync cxor monitor --repo /tmp/cxor-target
```

Follow new events:

```bash
uv run --no-sync cxor monitor --repo /tmp/cxor-target --follow
```

JSON output:

```bash
uv run --no-sync cxor monitor --repo /tmp/cxor-target --json
```

Useful filters:

```bash
uv run --no-sync cxor monitor --repo /tmp/cxor-target --since OE000010
uv run --no-sync cxor monitor --repo /tmp/cxor-target --patchlet P0001
uv run --no-sync cxor monitor --repo /tmp/cxor-target --attempt P0001_attempt1
uv run --no-sync cxor monitor --repo /tmp/cxor-target --event-type report_ingestion_normalized
uv run --no-sync cxor monitor --repo /tmp/cxor-target --limit 50
```

`cxor monitor` is read-only. It does not invoke Codex and does not modify workflow state.

### 8.2 Inspect current status

Human output:

```bash
uv run --no-sync cxor status --repo /tmp/cxor-target
```

JSON output:

```bash
uv run --no-sync cxor status --repo /tmp/cxor-target --json
```

Watch mode:

```bash
uv run --no-sync cxor status --repo /tmp/cxor-target --watch
```

Expected useful fields in JSON include:

```text
stage
current_patchlet_id
current_attempt_id
current_loop_iteration
completed_patchlet_count
failed_patchlet_count
pending_patchlet_count
run_count
last_event
active_prompt_path
last_progress_path
last_progress_age_seconds
classification
next_action
last_report_ingestion
```

Common classifications:

```text
active
silent_but_active
likely_stalled
done
failed
unknown
```

`cxor status` is read-only. It does not invoke Codex and does not modify workflow state.

---

## 9. Inspect prompts sent to Codex

The orchestrator writes a prompt index:

```text
<target>/.codex-orchestrator/prompt_index.json
```

List prompts:

```bash
uv run --no-sync cxor prompts --repo /tmp/cxor-target
```

JSON output:

```bash
uv run --no-sync cxor prompts --repo /tmp/cxor-target --json
```

Show the latest prompt metadata:

```bash
uv run --no-sync cxor prompts --repo /tmp/cxor-target --latest
```

Filter by patchlet, attempt, or kind:

```bash
uv run --no-sync cxor prompts --repo /tmp/cxor-target --patchlet P0001
uv run --no-sync cxor prompts --repo /tmp/cxor-target --attempt P0001_attempt1
uv run --no-sync cxor prompts --repo /tmp/cxor-target --kind patchlet_worker_prompt
uv run --no-sync cxor prompts --repo /tmp/cxor-target --kind repair_worker_prompt
```

Show a prompt body explicitly:

```bash
uv run --no-sync cxor prompts --repo /tmp/cxor-target --show PR000003 --lines 160
```

Show by path:

```bash
uv run --no-sync cxor prompts \
  --repo /tmp/cxor-target \
  --show-path .codex-orchestrator/runs/P0001_attempt1/codex_task_prompt.md \
  --lines 160
```

Prompt bodies are not printed by default in list mode. This prevents accidental terminal spam and keeps live progress concise.

`cxor prompts` is read-only. It does not invoke Codex and does not modify workflow state.

---

## 10. Understand operator event behavior

The operator event stream is:

```text
<target>/.codex-orchestrator/operator_events.jsonl
```

Event IDs are monotonic:

```text
OE000001
OE000002
OE000003
```

Common event types include:

```text
workflow_started
patchlet_started
patchlet_prompt_written
patchlet_worker_started
patchlet_worker_exited
report_ingestion_started
report_ingestion_normalized
report_ingestion_passed
report_ingestion_failed
patchlet_report_validated
patchlet_wrapper_gate_passed
patchlet_wrapper_gate_failed
patchlet_target_hygiene_passed
patchlet_target_hygiene_failed
patchlet_checkpoint_written
patchlet_integration_validated
patchlet_accepted
patchlet_failed_with_evidence
failure_record_created
repair_plan_created
repair_patchlets_regenerated
loop_governor_warning
loop_governor_blocked
transaction_group_started
transaction_group_passed
transaction_group_failed
global_verifier_started
global_verifier_passed
global_verifier_failed
workflow_done
workflow_safe_failed
verifier_no_prompt
```

Operator events include paths to deeper evidence artifacts, such as:

```text
.codex-orchestrator/runs/P0001_attempt1/codex_task_prompt.md
.codex-orchestrator/runs/P0001_attempt1/progress.jsonl
.codex-orchestrator/runs/P0001_attempt1/gates/report_ingestion_result.json
.codex-orchestrator/runs/P0001_attempt1/gates/report_validation_errors.json
.codex-orchestrator/runs/P0001_attempt1/gates/wrapper_gate_result.json
.codex-orchestrator/failures/F0001.json
.codex-orchestrator/repair_plans/RP0001.json
```

---

## 11. Understand loop governance

The loop governor records repeated failure signatures in:

```text
<target>/.codex-orchestrator/loop_governor.json
```

Default mode is warning mode. Warning mode surfaces repeated patterns but does not block continuation.

Example warning:

```text
Repeated failure signature probe_artifact_refs_not_objects seen 3 times across P0001, P0002, P0003; continuing in warning mode.
```

Use safe-fail mode to stop repeated identical failures with evidence instead of allowing a long repair loop:

```bash
uv run --no-sync cxor auto \
  --repo /tmp/cxor-target \
  --master /tmp/cxor-target/master_prompt.md \
  --until DONE \
  --worker-mode real_codex \
  --use-worktree \
  --live-progress \
  --loop-governor-mode safe-fail \
  --max-repeated-failure-signature 3
```

Safe-fail mode does not delete evidence. It should preserve failure records, repair plans, operator events, and loop-governor state.

---

## 12. Understand raw and canonical report ingestion

The report-ingestion gate prevents real-Codex report-shape drift from becoming an unbounded repair loop.

The worker may produce a raw report. The orchestrator preserves it exactly:

```text
<target>/.codex-orchestrator/reports/<PATCHLET>.raw.json
```

The orchestrator then writes the canonical report:

```text
<target>/.codex-orchestrator/reports/<PATCHLET>.json
```

The canonical report remains strict. It must not contain string-only `probe_artifact_refs`.

The report-ingestion result is:

```text
<target>/.codex-orchestrator/runs/<ATTEMPT>/gates/report_ingestion_result.json
```

The structured validation errors artifact is:

```text
<target>/.codex-orchestrator/runs/<ATTEMPT>/gates/report_validation_errors.json
```

A successful ingestion result may show:

```json
{
  "accepted": true,
  "normalization_applied": false,
  "normalized_failure_signature": null
}
```

If raw string probe refs are safely normalized, it may show:

```json
{
  "accepted": true,
  "normalization_applied": true,
  "normalization_kinds": [
    "probe_artifact_refs_string_paths_to_objects"
  ]
}
```

---

## 13. Understand canonical `probe_artifact_refs`

Canonical reports use object-shaped probe references.

Valid:

```json
{
  "probe_artifact_refs": [
    {
      "patchlet_id": "P0001",
      "probe_root": ".artifacts/probes/P0001/run_001",
      "run_id": "run_001",
      "files": [
        {
          "path": ".artifacts/probes/P0001/run_001/before_state.json",
          "kind": "before_state",
          "sha256": "<sha256>",
          "size_bytes": 123
        }
      ]
    }
  ]
}
```

Invalid in canonical report JSON:

```json
{
  "probe_artifact_refs": [
    ".artifacts/probes/P0001/run_001/before_state.json"
  ]
}
```

String probe refs are accepted only as raw worker-report input at report-ingestion time. They are normalized only if they are safe.

Safe string refs must:

```text
exist
resolve inside the target repo
resolve under .artifacts/probes/
match the current patchlet id
not escape through symlinks
```

Unsafe examples are rejected:

```text
/etc/passwd
../outside.txt
app.py
master_prompt.md
.artifacts/not-probes/file.txt
.artifacts/probes/P9999/file.txt when current patchlet is P0001
.artifacts/probes/P0001/missing.txt
.artifacts/probes/P0001/symlink_to_outside
```

---

## 14. Understand structured report validation errors

Report validation errors are now machine-readable, not only human text.

The artifact path is:

```text
<target>/.codex-orchestrator/runs/<ATTEMPT>/gates/report_validation_errors.json
```

Structured error fields may include:

```text
field
json_pointer
schema_path
message
validator
expected_type
actual_type
invalid_value_excerpt
normalized_signature
repair_hint
canonical_example
```

For the historic real-Codex probe-ref failure, the expected signature is:

```text
probe_artifact_refs_not_objects
```

This should not degrade to:

```text
unknown_repeated_failure
```

---

## 15. Use the real-Codex smoke runbook

The runbook is still the preferred operator workflow for release evidence bundles.

### 15.1 Dry run

```bash
uv run --no-sync cxor real-codex-smoke-runbook --dry-run
```

This creates a bundle without invoking real Codex.

### 15.2 Explicit real-Codex smoke run

```bash
CODEX_PATCHLET_TIMEOUT_SECONDS=600 \
uv run --no-sync cxor real-codex-smoke-runbook \
  --run-real-codex \
  --live-progress
```

Runbook live progress lines look like:

```text
[cxor:P0001_attempt1 +000s] codex: process.started
[cxor:P0001_attempt1 +009s] codex: message
[cxor:P0001_attempt1 +140s] codex: exited 0
```

The older `rc2` runbook proof reached:

```text
outcome: success
state_stage: DONE
```

The newer `rc3` direct-auto proof also reached `DONE`, but direct auto artifacts live under the target repo rather than `.operator-runs/real-codex-smoke/`.

---

## 16. List real-Codex runbook bundles

Use this to find local operator-run bundles.

```bash
uv run --no-sync cxor list-real-codex-smoke-runbooks
```

JSON form:

```bash
uv run --no-sync cxor list-real-codex-smoke-runbooks --json
```

Latest only:

```bash
uv run --no-sync cxor list-real-codex-smoke-runbooks --latest --json
```

Only invalid bundles:

```bash
uv run --no-sync cxor list-real-codex-smoke-runbooks --only-invalid --json
```

Limit output:

```bash
uv run --no-sync cxor list-real-codex-smoke-runbooks --limit 5
```

Important fields:

```text
outcome
valid
validation_status
attempt_consistency_valid
attempt_consistency_mismatches
selected_model
selected_reasoning
timeout_seconds
timed_out
diagnosis_primary_category
```

A healthy successful bundle should show:

```text
outcome: success
attempt_consistency_valid: true
attempt_consistency_mismatches: []
diagnosis_primary_category: null
```

---

## 17. Validate a real-Codex runbook bundle

```bash
uv run --no-sync cxor validate-real-codex-smoke-runbook \
  --run-dir .operator-runs/real-codex-smoke/2026-07-03T18-15-05-real-codex-smoke
```

Expected healthy result:

```json
{
  "valid": true,
  "errors": [],
  "warnings": []
}
```

Validation checks include:

```text
required bundle files
selected_policy.json schema
result.json schema
diagnosis_paths.json schema
validation_result.json schema
text evidence files
copied diagnosis files
attempt consistency
```

---

## 18. Export a real-Codex runbook bundle

Export creates a shareable ZIP archive plus a manifest of file hashes.

```bash
uv run --no-sync cxor export-real-codex-smoke-runbook \
  --run-dir .operator-runs/real-codex-smoke/2026-07-03T18-15-05-real-codex-smoke
```

Older `rc2` runbook evidence paths:

```text
.operator-runs/exports/2026-07-03T18-15-05-real-codex-smoke.zip
.operator-runs/exports/2026-07-03T18-15-05-real-codex-smoke.zip.manifest.json
```

The manifest records:

```text
source run dir
archive path
archive format
bundle validity
attempt consistency
outcome
model
reasoning
timeout
file list
size bytes
sha256 for each file
```

Use `--out` to choose a specific path:

```bash
uv run --no-sync cxor export-real-codex-smoke-runbook \
  --run-dir <bundle> \
  --out /tmp/cxor-evidence.zip
```

Invalid bundles are refused by default. Use `--force` only when deliberately exporting invalid evidence for debugging:

```bash
uv run --no-sync cxor export-real-codex-smoke-runbook \
  --run-dir <bundle> \
  --force
```

---

## 19. Validate target integration artifacts

After a target workflow run:

```bash
uv run --no-sync cxor validate-integration-artifacts --repo /tmp/cxor-target
```

Validated artifacts include:

```text
.codex-orchestrator/integration/integration_state.json
.codex-orchestrator/integration/accepted_changes.jsonl
.codex-orchestrator/integration/checkpoints/*.json
.codex-orchestrator/integration/checkpoints/*_cleanliness.json
.codex-orchestrator/integration/apply_results/*_result.json
run target hygiene gate results referenced by checkpoints
```

The P0004 hardening added structured target-cleanliness evidence, including:

```text
target_hygiene_gate_result.json
<PATCHLET>_cleanliness.json
target_cleanliness summary inside checkpoint JSON
```

The checkpoint remains strict:

```json
"target_working_tree_clean_after_checkpoint": true
```

The system does not weaken checkpoint cleanliness. It prevents/remediates known Python cache side effects and fails on unknown dirty paths.

---

## 20. Understand target hygiene behavior

The target hygiene gate runs before checkpoint finalization.

It classifies dirty paths into:

```text
workflow artifacts: .codex-orchestrator/
probe artifacts: .artifacts/
Python cache: __pycache__/, *.pyc, *.pyo
product/runtime dirtiness
unknown dirty paths
```

Known untracked Python cache artifacts may be removed with evidence. Unknown paths are not deleted.

Example cache evidence:

```text
__pycache__/app.cpython-310.pyc
```

The gate records:

```text
git_status_before_hygiene
git_status_after_hygiene
cache_artifacts_detected
cache_artifacts_removed
product_runtime_dirty_paths
unknown_dirty_paths
whole_repo_clean_after_hygiene
```

If the worker leaves an unknown file such as:

```text
tmp.txt
```

then the gate should fail precisely and leave the file in place.

---

## 21. Understand Python bytecode/cache policy

Workers run with:

```text
PYTHONDONTWRITEBYTECODE=1
```

Worker prompts and capsule contracts instruct Codex to use:

```bash
python -B <probe>
```

or:

```bash
PYTHONDONTWRITEBYTECODE=1 python <probe>
```

This prevents target-root `__pycache__/` leaks when probes import target code.

The policy is:

```text
prevent first
remediate known cache second
fail precisely third
```

---

## 22. Understand attempt lifecycle in run_manifest.json

The orchestrator writes a manifest entry at attempt start, then updates it through lifecycle stages.

Important stages:

```text
ATTEMPT_STARTED
WORKER_EXITED
REPORT_VALIDATED
WRAPPER_GATE_EVALUATED
TARGET_HYGIENE_EVALUATED
INTEGRATION_CHECKPOINT_WRITTEN
INTEGRATION_ARTIFACTS_VALIDATED
ATTEMPT_ACCEPTED
ATTEMPT_FAILED_WITH_EVIDENCE
```

This prevents late failures from disappearing from `run_manifest.json`.

A failed P0004 attempt should still have a P0004 manifest entry.

---

## 23. Understand runbook attempt consistency

Runbook result files include attempt consistency fields.

Healthy result:

```json
"attempt_consistency": {
  "valid": true,
  "mismatches": []
}
```

A mismatch means the bundle may be mixing evidence from different attempts, for example:

```text
P0004 run paths
P0003 manifest entry
P0003 diagnosis
```

That old failure mode is now surfaced instead of hidden.

Validation/list/export commands expose attempt consistency.

---

## 24. Inspect final target state

After a successful target run:

```bash
git -C /tmp/cxor-target status --short
git -C /tmp/cxor-target diff -- app.py
```

Expected before `apply-results`:

```text
product/runtime files clean
.codex-orchestrator/ and .artifacts/ may be present as evidence
```

The accepted product changes are represented through the hidden integration ref and final diff, not by dirtying the target working tree.

Inspect the final diff:

```bash
cat /tmp/cxor-target/.codex-orchestrator/integration/final_diff.patch
```

---

## 25. Apply results explicitly

The orchestrator does not silently mutate the target working tree at the end. Use `apply-results` explicitly.

### 25.1 Patch mode

Patch mode refreshes or emits the final diff without mutating product files.

```bash
uv run --no-sync cxor apply-results \
  --repo /tmp/cxor-target \
  --mode patch
```

### 25.2 Branch mode

Branch mode creates or updates a result branch at the integration SHA without checking it out.

```bash
uv run --no-sync cxor apply-results \
  --repo /tmp/cxor-target \
  --mode branch
```

Expected branch pattern:

```text
cxor/results/<run_id>
```

### 25.3 Working-tree mode

Working-tree mode applies the final diff to the target working tree.

Use only when the target is clean.

```bash
git -C /tmp/cxor-target status --short

uv run --no-sync cxor apply-results \
  --repo /tmp/cxor-target \
  --mode working-tree
```

If the target is dirty, working-tree mode should refuse.

---

## 26. Common diagnosis and failure signatures

### 26.1 `probe_artifact_refs_not_objects`

Meaning:

```text
A report wrote probe_artifact_refs as string paths, but canonical reports require object entries.
```

The report-ingestion layer may normalize safe raw string refs before canonical validation. If it cannot, the failure remains precise.

Action:

```bash
cat /tmp/cxor-target/.codex-orchestrator/runs/<ATTEMPT>/gates/report_ingestion_result.json
cat /tmp/cxor-target/.codex-orchestrator/runs/<ATTEMPT>/gates/report_validation_errors.json
cat /tmp/cxor-target/.codex-orchestrator/reports/<PATCHLET>.raw.json
cat /tmp/cxor-target/.codex-orchestrator/reports/<PATCHLET>.json
```

### 26.2 `patchlet_report_schema_violation`

Meaning:

```text
Codex produced a report JSON that failed schema validation.
```

Typical causes:

```text
unsupported status such as FIXED
missing required fields
wrong field type
canonical report field shape error
```

Action:

```text
Inspect .codex-orchestrator/reports/<PATCHLET>.raw.json
Inspect .codex-orchestrator/reports/<PATCHLET>.json
Inspect report_validation_errors.json
Inspect report_ingestion_result.json
```

### 26.3 `wrapper_gate_final_status_marker_error`

Meaning:

```text
The Markdown final report marker was missing, invalid, or non-canonical.
```

Canonical accepted line:

```text
FINAL_STATUS: PASS
```

Rejected example:

```text
Marker: `FINAL_STATUS: PASS`
```

Action:

```text
Inspect worker_stage/05_final_report.md
Inspect gates/wrapper_gate_result.json
```

### 26.4 `transaction_group_repair_routing_error`

Meaning:

```text
A transaction group failure could not be mapped correctly to member patchlets.
```

Action:

```text
Inspect patchlets/transaction_groups.json
Inspect failures/*.json
Inspect repair_plans/*.json
```

### 26.5 `integration_checkpoint_target_cleanliness_error`

Meaning:

```text
Checkpoint cleanliness failed, usually because target hygiene could not produce a clean state.
```

Action:

```text
Inspect gates/target_hygiene_gate_result.json
Inspect integration/checkpoints/<PATCHLET>_cleanliness.json
Inspect git status of target repo
```

### 26.6 `runbook_attempt_evidence_mismatch`

Meaning:

```text
The operator bundle contains evidence from mismatched attempt ids.
```

Action:

```text
Inspect result.json attempt_consistency
Run validate-real-codex-smoke-runbook
Run list-real-codex-smoke-runbooks --json
```

### 26.7 `network_or_api_error`

Meaning:

```text
Actual external/API/network failure evidence was found.
```

Action:

```text
Inspect stderr.txt
Inspect output.jsonl
Check Codex auth/session/network/model availability
```

---

## 27. Release-candidate verification workflow

Use this before tagging or publishing a release candidate.

```bash
export UV_CACHE_DIR=/tmp/uv-cache

uv run --no-sync pytest -q
uv run --no-sync python -m codex_orchestrator --version
uv run --no-sync cxor --version
uv run --no-sync codex-orchestrator --version
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py
```

Then run direct real-Codex smoke evidence on a fresh tiny target:

```bash
rm -rf /tmp/cxor-target-report-contract-smoke
mkdir -p /tmp/cxor-target-report-contract-smoke
cd /tmp/cxor-target-report-contract-smoke

git init
cat > app.py <<'PY'
def main():
    return "not ok"
PY

cat > master_prompt.md <<'MD'
Make app return ok and prove it.
MD

git add app.py master_prompt.md
git commit -m "Initial target"

cd /home/theyeq-admin-lap/master-workspace-research/codex-orchestrator

CODEX_PATCHLET_TIMEOUT_SECONDS=600 \
uv run --no-sync cxor auto \
  --repo /tmp/cxor-target-report-contract-smoke \
  --master /tmp/cxor-target-report-contract-smoke/master_prompt.md \
  --until DONE \
  --worker-mode real_codex \
  --use-worktree \
  --live-progress
```

Inspect live evidence:

```bash
uv run --no-sync cxor monitor --repo /tmp/cxor-target-report-contract-smoke --limit 100
uv run --no-sync cxor status --repo /tmp/cxor-target-report-contract-smoke --json
uv run --no-sync cxor prompts --repo /tmp/cxor-target-report-contract-smoke --latest
uv run --no-sync cxor validate-integration-artifacts --repo /tmp/cxor-target-report-contract-smoke
```

Release-candidate success evidence should include:

```text
full suite green
default smoke test skipped by default
direct real-Codex auto reaches DONE
operator events include workflow_done
status classification is done
report ingestion accepted
report validation errors valid=true with errors=[]
wrapper gate accepted
target hygiene passed
integration validation passed
target product/runtime files remain clean
release evidence paths documented
```

The `v0.1.0-rc3` live direct-auto proof used:

```text
/tmp/cxor-target-report-contract-smoke-20260703T203745Z
```

---

## 28. Tag a release candidate

After a clean commit and release evidence pass:

```bash
git status --short
```

Expected:

```text
# no output
```

Create a release-candidate tag:

```bash
git tag -a v0.1.0-rc3 -m "codex-orchestrator v0.1.0 release candidate 3"
```

Verify tag target:

```bash
git show --no-patch --oneline v0.1.0-rc3
git rev-parse v0.1.0-rc3^{commit}
git rev-parse HEAD
```

The tag commit and `HEAD` should match.

---

## 29. Recommended daily/operator workflow

### 29.1 Safe deterministic workflow

```bash
uv run --no-sync pytest -q
uv run --no-sync cxor auto \
  --repo <target> \
  --master <target>/master_prompt.md \
  --until DONE \
  --worker-mode mock \
  --use-worktree
uv run --no-sync cxor validate-integration-artifacts --repo <target>
```

### 29.2 Direct real-Codex workflow with operator visibility

```bash
CODEX_PATCHLET_TIMEOUT_SECONDS=600 \
uv run --no-sync cxor auto \
  --repo <target> \
  --master <target>/master_prompt.md \
  --until DONE \
  --worker-mode real_codex \
  --use-worktree \
  --live-progress
```

Second terminal:

```bash
uv run --no-sync cxor monitor --repo <target> --follow
uv run --no-sync cxor status --repo <target> --watch
uv run --no-sync cxor prompts --repo <target> --latest
```

After completion:

```bash
uv run --no-sync cxor validate-integration-artifacts --repo <target>
git -C <target> status --short
```

### 29.3 Real-Codex runbook workflow for evidence bundles

```bash
CODEX_PATCHLET_TIMEOUT_SECONDS=600 \
uv run --no-sync cxor real-codex-smoke-runbook \
  --run-real-codex \
  --live-progress

uv run --no-sync cxor list-real-codex-smoke-runbooks --latest --json
uv run --no-sync cxor validate-real-codex-smoke-runbook --run-dir <latest_bundle>
uv run --no-sync cxor export-real-codex-smoke-runbook --run-dir <latest_bundle>
```

### 29.4 Apply final changes

```bash
uv run --no-sync cxor apply-results --repo <target> --mode patch
uv run --no-sync cxor apply-results --repo <target> --mode branch
uv run --no-sync cxor apply-results --repo <target> --mode working-tree
```

Use working-tree mode only when the target repo is clean.

---

## 30. Quick command reference

```bash
# Version
cxor --version
codex-orchestrator --version
python -m codex_orchestrator --version

# Autonomous loop
cxor auto --repo <target> --master <prompt> --until DONE --worker-mode mock --use-worktree
cxor auto --repo <target> --master <prompt> --until DONE --worker-mode real_codex --use-worktree --live-progress
cxor auto --repo <target> --master <prompt> --until DONE --worker-mode real_codex --use-worktree --no-live-progress
cxor auto --repo <target> --master <prompt> --until DONE --worker-mode real_codex --use-worktree --live-progress --progress-format jsonl

# Operator visibility
cxor monitor --repo <target>
cxor monitor --repo <target> --follow
cxor monitor --repo <target> --json
cxor status --repo <target>
cxor status --repo <target> --json
cxor status --repo <target> --watch
cxor prompts --repo <target>
cxor prompts --repo <target> --latest
cxor prompts --repo <target> --show <prompt_id> --lines 160

# Integration validation
cxor validate-integration-artifacts --repo <target>

# Apply results
cxor apply-results --repo <target> --mode patch
cxor apply-results --repo <target> --mode branch
cxor apply-results --repo <target> --mode working-tree

# Real-Codex runbook
cxor real-codex-smoke-runbook --dry-run
cxor real-codex-smoke-runbook --run-real-codex --live-progress

# Runbook evidence
cxor list-real-codex-smoke-runbooks
cxor list-real-codex-smoke-runbooks --latest --json
cxor validate-real-codex-smoke-runbook --run-dir <bundle>
cxor export-real-codex-smoke-runbook --run-dir <bundle>
```

---

## 31. Release-candidate finish checklist

The implementation is release-candidate complete when all are true:

```text
1. Full deterministic suite is green.
2. Default smoke test skips unless explicitly enabled.
3. Direct real-Codex auto reaches DONE on a fresh target.
4. Direct auto live progress prints concise stage-level events.
5. cxor monitor can read operator_events.jsonl.
6. cxor status --json reports done and last report ingestion evidence.
7. cxor prompts lists prompt metadata and can show prompt bodies explicitly.
8. Report ingestion accepts canonical reports and normalizes safe raw string refs.
9. Report validation errors are structured and precise.
10. Loop governor uses specific signatures, not unknown_repeated_failure, for known report-shape classes.
11. Target product/runtime files remain clean until apply-results.
12. Integration artifacts validate.
13. Checkpoint cleanliness sidecars validate.
14. Run manifest contains current attempt lifecycle entries.
15. Diagnosis is null on success or precise on safe failure.
16. Release evidence paths are documented.
17. Git commit is clean.
18. Release candidate tag points to the final commit.
```

For `v0.1.0-rc3`, the release evidence passed with:

```text
full suite: 1212 passed, 2 skipped
latest direct real-Codex target: /tmp/cxor-target-report-contract-smoke-20260703T203745Z
state_stage: DONE
report ingestion: accepted
report validation errors: valid=true, errors=[]
wrapper gate: accepted
target hygiene: passed
integration validation: passed
target product files: clean
release tag: v0.1.0-rc3
```

## Semantic Goal Satisfaction

For simple Python return-value prompts, Codex Orchestrator records a semantic
goal spec and independently verifies the accepted state. A prompt such as
`Make app return me and prove it.` requires `app.main()` to return `"me"`. If
the app still returns `"ok"`, the goal satisfaction gate fails with
`semantic_goal_unsatisfied` and the workflow must not reach `DONE`.
