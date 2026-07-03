# Codex Orchestrator — Step-by-Step Usage Guide

Version target: `v0.1.0-rc2` release-candidate workflow  
Primary CLI: `cxor`  
Primary goal: run a durable autonomous root-cause probe-gated loop until `DONE`, while preserving all evidence and keeping target-repo product files clean until explicit result application.

---

## 0. What this tool does

`codex-orchestrator` is a local CLI that runs Codex as a disposable worker inside a durable workflow owned by the orchestrator.

The orchestrator owns:

- state
- patchlets
- worker prompts
- Worker Capsule contracts
- probes
- reports
- gates
- target hygiene checks
- integration checkpoints
- run manifests
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

## 1. Mental model

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

Operator real-Codex smoke evidence is stored under the orchestrator repo:

```text
.operator-runs/real-codex-smoke/
.operator-runs/exports/
```

---

## 2. Install and verify the CLI

### 2.1 Use from the orchestrator repo with `uv`

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

### 2.2 Optional editable install from source

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

## 3. Verify the deterministic suite before serious use

From the orchestrator repo:

```bash
export UV_CACHE_DIR=/tmp/uv-cache
uv run --no-sync pytest -q
```

The release-candidate evidence passed with:

```text
909 passed, 2 skipped
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

## 4. Prepare a target repository

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

## 5. Run the autonomous loop in deterministic mock mode

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

## 6. Run the autonomous loop with real Codex

Real Codex is opt-in. Use it only after deterministic mode is healthy.

### 6.1 Confirm Codex CLI is available

```bash
codex --version
which codex
```

The release-candidate evidence used:

```text
codex-cli 0.142.4
```

### 6.2 Run direct real-Codex auto mode

```bash
CODEX_PATCHLET_TIMEOUT_SECONDS=600 \
uv run --no-sync cxor auto \
  --repo /tmp/cxor-target \
  --master /tmp/cxor-target/master_prompt.md \
  --until DONE \
  --worker-mode real_codex \
  --use-worktree
```

The timeout gives real Codex enough time to complete each patchlet attempt.

### 6.3 What to expect

A successful run reaches:

```text
DONE
```

A safe failure should produce structured evidence and a precise diagnosis.

Common safe-failure categories include:

```text
patchlet_report_schema_violation
wrapper_gate_final_status_marker_error
transaction_group_repair_routing_error
integration_checkpoint_target_cleanliness_error
integration_artifact_validation_error
run_manifest_attempt_lifecycle_error
runbook_attempt_evidence_mismatch
target_cache_artifact_leak
stage_precondition_error
network_or_api_error
```

`network_or_api_error` should now be reserved for real external/network/API evidence, not ordinary prompt text containing words such as `timeout` or `model`.

---

## 7. Use the real-Codex smoke runbook

The runbook is the preferred operator workflow for capturing real-Codex evidence.

### 7.1 Dry run

```bash
uv run --no-sync cxor real-codex-smoke-runbook --dry-run
```

This creates a bundle without invoking real Codex.

### 7.2 Explicit real-Codex smoke run

```bash
CODEX_PATCHLET_TIMEOUT_SECONDS=600 \
uv run --no-sync cxor real-codex-smoke-runbook \
  --run-real-codex \
  --live-progress
```

Live progress lines look like:

```text
[cxor:P0001_attempt1 +000s] codex: process.started
[cxor:P0001_attempt1 +009s] codex: message
[cxor:P0001_attempt1 +140s] codex: exited 0
```

The release-candidate proof reached:

```text
outcome: success
state_stage: DONE
```

The successful release-candidate bundle was:

```text
.operator-runs/real-codex-smoke/2026-07-03T18-15-05-real-codex-smoke
```

---

## 8. List real-Codex runbook bundles

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

## 9. Validate a real-Codex runbook bundle

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

## 10. Export a real-Codex runbook bundle

Export creates a shareable ZIP archive plus a manifest of file hashes.

```bash
uv run --no-sync cxor export-real-codex-smoke-runbook \
  --run-dir .operator-runs/real-codex-smoke/2026-07-03T18-15-05-real-codex-smoke
```

Release-candidate evidence paths:

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

## 11. Validate target integration artifacts

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

## 12. Understand target hygiene behavior

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

## 13. Understand Python bytecode/cache policy

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

## 14. Understand attempt lifecycle in run_manifest.json

The orchestrator now writes a manifest entry at attempt start, then updates it through lifecycle stages.

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

## 15. Understand runbook attempt consistency

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

## 16. Inspect final target state

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

## 17. Apply results explicitly

The orchestrator does not silently mutate the target working tree at the end. Use `apply-results` explicitly.

### 17.1 Patch mode

Patch mode refreshes or emits the final diff without mutating product files.

```bash
uv run --no-sync cxor apply-results \
  --repo /tmp/cxor-target \
  --mode patch
```

### 17.2 Branch mode

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

### 17.3 Working-tree mode

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

## 18. Common diagnosis categories and what to do

### 18.1 `patchlet_report_schema_violation`

Meaning:

```text
Codex produced a report JSON that failed schema validation.
```

Typical causes:

```text
unsupported status such as FIXED
missing required fields
wrong field type such as cleanup_proof object instead of string
```

Action:

```text
Inspect .codex-orchestrator/reports/<PATCHLET>.json
Inspect report_validation.reason in run_manifest.json
```

### 18.2 `wrapper_gate_final_status_marker_error`

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

### 18.3 `transaction_group_repair_routing_error`

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

### 18.4 `integration_checkpoint_target_cleanliness_error`

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

### 18.5 `runbook_attempt_evidence_mismatch`

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

### 18.6 `network_or_api_error`

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

## 19. Release-candidate verification workflow

Use this before tagging or publishing a release candidate.

```bash
export UV_CACHE_DIR=/tmp/uv-cache

uv run --no-sync pytest -q
uv run --no-sync python -m codex_orchestrator --version
uv run --no-sync cxor --version
uv run --no-sync codex-orchestrator --version
uv run --no-sync pytest -q tests/smoke/test_real_codex_auto_worktree.py
```

Then run real-Codex operator evidence:

```bash
CODEX_PATCHLET_TIMEOUT_SECONDS=600 \
uv run --no-sync cxor real-codex-smoke-runbook \
  --run-real-codex \
  --live-progress
```

Then validate/list/export:

```bash
uv run --no-sync cxor list-real-codex-smoke-runbooks --latest --json

uv run --no-sync cxor validate-real-codex-smoke-runbook \
  --run-dir <latest_bundle>

uv run --no-sync cxor export-real-codex-smoke-runbook \
  --run-dir <latest_bundle>
```

Release-candidate success evidence should include:

```text
full suite green
smoke test skipped by default
real-Codex bundle outcome success
state_stage DONE
bundle validation valid=true
attempt_consistency valid=true
attempt_consistency mismatches=[]
export archive exists
export manifest exists
```

The `v0.1.0-rc2` release-candidate proof used:

```text
.operator-runs/real-codex-smoke/2026-07-03T18-15-05-real-codex-smoke
.operator-runs/exports/2026-07-03T18-15-05-real-codex-smoke.zip
.operator-runs/exports/2026-07-03T18-15-05-real-codex-smoke.zip.manifest.json
```

---

## 20. Tag a release candidate

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
git tag -a v0.1.0-rc2 -m "codex-orchestrator v0.1.0 release candidate 2"
```

Verify tag target:

```bash
git show --no-patch --oneline v0.1.0-rc2
git rev-parse v0.1.0-rc2^{commit}
git rev-parse HEAD
```

The tag commit and `HEAD` should match.

---

## 21. Recommended daily/operator workflow

### Safe deterministic workflow

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

### Real-Codex workflow

```bash
CODEX_PATCHLET_TIMEOUT_SECONDS=600 \
uv run --no-sync cxor real-codex-smoke-runbook \
  --run-real-codex \
  --live-progress

uv run --no-sync cxor list-real-codex-smoke-runbooks --latest --json
uv run --no-sync cxor validate-real-codex-smoke-runbook --run-dir <latest_bundle>
uv run --no-sync cxor export-real-codex-smoke-runbook --run-dir <latest_bundle>
```

### Apply final changes

```bash
uv run --no-sync cxor apply-results --repo <target> --mode patch
uv run --no-sync cxor apply-results --repo <target> --mode branch
uv run --no-sync cxor apply-results --repo <target> --mode working-tree
```

Use working-tree mode only when the target repo is clean.

---

## 22. Quick command reference

```bash
# Version
cxor --version
codex-orchestrator --version
python -m codex_orchestrator --version

# Autonomous loop
cxor auto --repo <target> --master <prompt> --until DONE --worker-mode mock --use-worktree
cxor auto --repo <target> --master <prompt> --until DONE --worker-mode real_codex --use-worktree

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

## 23. Release-candidate finish checklist

The implementation is release-candidate complete when all are true:

```text
1. Full deterministic suite is green.
2. Default smoke test skips unless explicitly enabled.
3. Real-Codex operator smoke reaches success / DONE.
4. Real-Codex bundle validates.
5. Attempt consistency is valid.
6. Bundle exports with manifest.
7. Target product/runtime files remain clean until apply-results.
8. Integration artifacts validate.
9. Checkpoint cleanliness sidecars validate.
10. Run manifest contains current attempt lifecycle entries.
11. Diagnosis is null on success or precise on safe failure.
12. Release evidence paths are documented.
13. Git commit is clean.
14. Release candidate tag points to the final commit.
```

For `v0.1.0-rc2`, the release evidence passed with:

```text
full suite: 909 passed, 2 skipped
latest real-Codex bundle: success
state_stage: DONE
bundle valid: true
attempt consistency: valid, no mismatches
export archive: present
export manifest: present
```
