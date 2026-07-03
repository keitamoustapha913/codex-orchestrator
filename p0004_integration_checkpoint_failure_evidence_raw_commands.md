# P0004 Integration Checkpoint Failure Evidence Raw Commands

All commands were run from `/home/theyeq-admin-lap/master-workspace-research/codex-orchestrator` unless noted. Commands were read-only except creation of the requested evidence files and the requested bundle export command.

## 1. Baseline metadata

- command: `export UV_CACHE_DIR=/tmp/uv-cache; pwd; git status --short; git rev-parse --show-toplevel; git rev-parse --verify HEAD || true; uv run --no-sync python --version; uv run --no-sync python -m codex_orchestrator --version; uv run --no-sync cxor --version; uv run --no-sync codex-orchestrator --version; uv --version; codex --version || true; git branch --show-current`
- exit code: 0
- output excerpt:

```text
/home/theyeq-admin-lap/master-workspace-research/codex-orchestrator
 M IMPLEMENTATION_STATUS.md
 M README.md
 M docs/cli.md
 M docs/real_codex_smoke.md
 M docs/release.md
 M docs/runbooks/real_codex_smoke_runbook.md
 M src/codex_orchestrator/diagnostics.py
 M src/codex_orchestrator/prompt_templates/real_codex_patchlet_contract.md
 M src/codex_orchestrator/stages/regenerate_patchlets.py
 M src/codex_orchestrator/stages/run_patchlet.py
 M src/codex_orchestrator/stages/verify_group.py
 M src/codex_orchestrator/worker_capsule.py
 M src/codex_orchestrator/workers/codex_exec.py
 M tests/integration/test_real_codex_failure_diagnosis.py
?? real_codex_report_contract_failure_evidence_note.md
?? real_codex_tg001_routing_failure_evidence_note.md
?? repair_patchlet_report_contract_hardening_implementation_note.md
?? tests/integration/test_real_codex_prompt_contract.py
?? tests/integration/test_real_codex_report_contract_enforcement.py
?? tests/integration/test_real_codex_verified_no_change_chain.py
?? tests/integration/test_regenerate_patchlets_transaction_group_source_resolution.py
?? tests/integration/test_transaction_group_failure_source_modeling.py
?? tests/integration/test_worker_capsule_final_report_contract.py
?? tests/integration/test_worker_capsule_report_contract.py
?? tests/integration/test_wrapper_gate_final_status_marker.py
?? tests/unit/test_docs_report_contract_hardening.py
?? tests/unit/test_docs_wrapper_gate_and_tg_routing_hardening.py
?? verified_no_change_wrapper_gate_and_tg_repair_routing_implementation_note.md
/home/theyeq-admin-lap/master-workspace-research/codex-orchestrator
0941c7e76648fb79b98da83cf957d137caec8bfb
Python 3.10.20
codex-orchestrator 0.1.0
codex-orchestrator 0.1.0
codex-orchestrator 0.1.0
uv 0.11.23 (x86_64-unknown-linux-gnu)
codex-cli 0.142.4
main
```
- purpose: establish baseline versions and uncommitted state.
- read-only: yes.

## 2. Baseline full suite

- command: `export UV_CACHE_DIR=/tmp/uv-cache; uv run --no-sync pytest -q`
- exit code: 0
- output:

```text
........................................................................ [  8%]
........................................................................ [ 17%]
........................................................................ [ 26%]
........................................................................ [ 35%]
........................................................................ [ 43%]
........................................................................ [ 52%]
........................................................................ [ 61%]
........................................................................ [ 70%]
......................................................ss................ [ 78%]
........................................................................ [ 87%]
........................................................................ [ 96%]
.............................                                            [100%]
819 passed, 2 skipped in 61.20s (0:01:01)
```
- purpose: prove deterministic baseline before evidence inspection.
- read-only: yes.

## 3. Latest runbook listing

- command: `export UV_CACHE_DIR=/tmp/uv-cache; uv run --no-sync cxor list-real-codex-smoke-runbooks --latest --json`
- exit code: 0
- output excerpt:

```json
{
  "bundles": [
    {
      "diagnosis_primary_category": "network_or_api_error",
      "explicit_smoke": {"outcome": "safe_failure", "run": true},
      "name": "2026-07-03T16-28-35-real-codex-smoke",
      "outcome": "safe_failure",
      "run_dir": ".operator-runs/real-codex-smoke/2026-07-03T16-28-35-real-codex-smoke",
      "selected_policy": {"live_progress_enabled": true, "model": "gpt-5.4-mini", "progress_interval_seconds": 30, "reasoning": "medium", "timeout_seconds": 600},
      "timed_out": false,
      "valid": true,
      "validation_status": "valid"
    }
  ],
  "count": 1,
  "invalid_count": 0,
  "valid_count": 1
}
```
- purpose: identify latest preserved live bundle.
- read-only: yes.

## 4. Bundle validation

- command: `export UV_CACHE_DIR=/tmp/uv-cache; uv run --no-sync cxor validate-real-codex-smoke-runbook --run-dir .operator-runs/real-codex-smoke/2026-07-03T16-28-35-real-codex-smoke`
- exit code: 0
- output:

```json
{
  "errors": [],
  "kind": "real_codex_smoke_runbook_validation",
  "run_dir": ".operator-runs/real-codex-smoke/2026-07-03T16-28-35-real-codex-smoke",
  "schema_version": "1.0",
  "valid": true,
  "validated": {"copied_diagnosis_files": true, "diagnosis_paths": true, "required_files": true, "result": true, "selected_policy": true, "text_evidence": true},
  "warnings": []
}
```
- purpose: prove bundle validates.
- read-only: yes.

## 5. Bundle export

- command: `export UV_CACHE_DIR=/tmp/uv-cache; uv run --no-sync cxor export-real-codex-smoke-runbook --run-dir .operator-runs/real-codex-smoke/2026-07-03T16-28-35-real-codex-smoke`
- exit code: 0
- output excerpt:

```json
{
  "archive_path": ".operator-runs/exports/2026-07-03T16-28-35-real-codex-smoke.zip",
  "exported": true,
  "manifest_path": ".operator-runs/exports/2026-07-03T16-28-35-real-codex-smoke.zip.manifest.json",
  "source_run_dir": ".operator-runs/real-codex-smoke/2026-07-03T16-28-35-real-codex-smoke",
  "valid": true
}
```
- purpose: preserve bundle export evidence.
- read-only: no, writes export archive/manifest as requested by investigation prompt.

## 6. Artifact index generation

- command: Python script hashing every file under `.operator-runs/real-codex-smoke/2026-07-03T16-28-35-real-codex-smoke` and writing `p0004_integration_checkpoint_failure_artifact_index.json`.
- exit code: 0
- output:

```json
{"latest_run_dir": ".operator-runs/real-codex-smoke/2026-07-03T16-28-35-real-codex-smoke", "file_count": 14, "artifact_index": "p0004_integration_checkpoint_failure_artifact_index.json"}
```
- purpose: produce requested artifact hash index.
- read-only: no, writes requested evidence file only.

## 7. Target cleanliness and cache evidence

- command: target git status, app.py diff, untracked files, and `__pycache__` listing for `/tmp/pytest-of-theyeq-admin-lap/pytest-459/test_real_codex_auto_worktree_0/target`.
- exit code: 0
- output excerpt:

```text
TARGET=/tmp/pytest-of-theyeq-admin-lap/pytest-459/test_real_codex_auto_worktree_0/target
TARGET_EXISTS
?? .artifacts/
?? .codex-orchestrator/
?? __pycache__/
__pycache__/app.cpython-310.pyc
/tmp/pytest-of-theyeq-admin-lap/pytest-459/test_real_codex_auto_worktree_0/target/__pycache__/app.cpython-310.pyc
-rw-rw-r-- 1 theyeq-admin-lap theyeq-admin-lap 279 Jul  3 16:38 /tmp/pytest-of-theyeq-admin-lap/pytest-459/test_real_codex_auto_worktree_0/target/__pycache__/app.cpython-310.pyc
```
- purpose: distinguish product/runtime cleanliness from artifact/cache dirtiness.
- read-only: yes.

## 8. Result, diagnosis, manifest, checkpoint, and integration validation summaries

- command: Python JSON extraction plus `uv run --no-sync cxor validate-integration-artifacts --repo /tmp/pytest-of-theyeq-admin-lap/pytest-459/test_real_codex_auto_worktree_0/target`.
- exit code: 1 because integration artifact validation returned invalid.
- output excerpt:

```text
explicit_smoke.outcome= safe_failure
parsed_smoke.attempt_id= P0003_attempt1
parsed_smoke.error_type= WorkerExecutionError
parsed_smoke.error_message= integration artifact validation failed
parsed_smoke.diagnosis_primary_category= network_or_api_error
parsed_smoke.run_dir= .../.codex-orchestrator/runs/P0004_attempt1
run_manifest_entry.attempt_id= P0003_attempt1
run_manifest_entry.patchlet_id= P0003
run_manifest_entry.status= VERIFIED_NO_CHANGE_NEEDED
run_manifest_entry.report_valid= True
run_count= 3
.codex-orchestrator/runs/P0004_attempt1/command.json True
.codex-orchestrator/reports/P0004.json True
.codex-orchestrator/runs/P0004_attempt1/gates/wrapper_gate_result.json True
.codex-orchestrator/integration/checkpoints/P0004.json True
```

```json
{
  "errors": [{"message": "True was expected", "path": ".codex-orchestrator/integration/checkpoints/P0004.json", "schema": "integration_checkpoint.schema.json"}],
  "valid": false,
  "validated": {"accepted_changes": true, "apply_results": true, "checkpoints": false, "final_diff": true, "integration_state": true}
}
```
- purpose: prove P0004 artifact exists, P0004 manifest entry is absent, and integration validation fails on P0004 checkpoint.
- read-only: yes.

## 9. P0004 artifacts and probes

- command: read P0004 command, wrapper gate, final report, report JSON, and probe files.
- exit code: 0
- output excerpts:

```text
P0004 wrapper gate: accepted true, final_status_marker "FINAL_STATUS: PASS", final_status_marker_canonical true.
P0004 final report first line: FINAL_STATUS: PASS.
P0004 report status: VERIFIED_NO_CHANGE_NEEDED.
P0004 report changed_product_runtime_file: null.
P0004 report changed_product_runtime_files in checkpoint: [].
```

P0004 probe imports target app through `importlib.util.spec_from_file_location`:

```python
TARGET_APP = TARGET_ROOT / "app.py"
def load_main_from(path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
```
- purpose: prove P0004 report/gate success and inspect likely cache creator.
- read-only: yes.

## 10. PYC metadata and search

- command: inspect `__pycache__/app.cpython-310.pyc` header/code filename and search P0004 artifacts for cache/import/bytecode terms.
- exit code: 0
- output excerpt:

```text
pyc_path= /tmp/pytest-of-theyeq-admin-lap/pytest-459/test_real_codex_auto_worktree_0/target/__pycache__/app.cpython-310.pyc
source_mtime_utc= 2026-07-03T14:28:35Z
source_size= 28
code_filename= /tmp/pytest-of-theyeq-admin-lap/pytest-459/test_real_codex_auto_worktree_0/target/app.py
```

Search showed P0004 probe imports via `importlib.util`, P0004 stdout recorded a temporary execution-root `__pycache__` cleanup, and no evidence that target-root `__pycache__` was cleaned.
- purpose: identify cache source path and bytecode suppression absence.
- read-only: yes.

## 11. Schema/source inspections

- command: read `integration_checkpoint.schema.json`, related tests/docs, and source snippets in `integration_state.py`, `run_patchlet.py`, `real_codex_smoke.py`, `diagnostics.py`, `git_guard.py`.
- exit code: 0
- output facts:
  - schema has `"target_working_tree_clean_after_checkpoint": {"const": true}`.
  - `record_accepted_change()` writes checkpoint before validation.
  - `_target_product_runtime_clean()` ignores `.codex-orchestrator/` and `.artifacts/` only; it does not ignore `__pycache__/`.
  - `_target_product_runtime_clean()` uses `snapshot_status(ctx.root).status`, which is `git status --porcelain`.
  - `run_patchlet.py` calls `_write_integration_validation_result(ctx)` and raises `WorkerExecutionError` before `append_run_record(...)`.
  - runbook selection uses latest run dir for paths but latest manifest entry for diagnosis.
  - diagnosis scans combined output for broad keywords including `network`, `api`, `timeout`, `connection`, and `model unavailable`.
- purpose: correlate artifact behavior with current source behavior.
- read-only: yes.
