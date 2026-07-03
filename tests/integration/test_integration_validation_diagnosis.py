from __future__ import annotations

from codex_orchestrator.diagnostics import diagnose_real_codex_attempt
from codex_orchestrator.jsonio import write_json

from test_real_codex_failure_diagnosis import _initialized_ctx, _seed_failed_real_codex_attempt


def test_integration_checkpoint_cleanliness_error_precedes_network_or_api(git_repo):
    ctx = _initialized_ctx(git_repo)
    _seed_failed_real_codex_attempt(
        ctx,
        stderr_text="network api timeout model words but structured validation wins\n",
        worker_failure_message="integration artifact validation failed",
        run_overrides={
            "worker_failure": {"type": "WorkerExecutionError", "message": "integration artifact validation failed", "exit_code": 0},
            "integration_artifact_validation": {
                "valid": False,
                "path": ".codex-orchestrator/integration/validation_result.json",
                "errors": [
                    {
                        "path": ".codex-orchestrator/integration/checkpoints/P0001.json",
                        "schema": "integration_checkpoint.schema.json",
                        "message": "target_working_tree_clean_after_checkpoint: True was expected",
                    }
                ],
            },
        },
    )

    result = diagnose_real_codex_attempt(ctx, attempt_id="P0001_attempt1")

    assert result["diagnosis_primary_category"] == "integration_checkpoint_target_cleanliness_error"


def test_integration_artifact_validation_error_precedes_network_or_api(git_repo):
    ctx = _initialized_ctx(git_repo)
    _seed_failed_real_codex_attempt(
        ctx,
        stderr_text="network api timeout model words but structured validation wins\n",
        run_overrides={
            "worker_failure": {"type": "WorkerExecutionError", "message": "integration artifact validation failed", "exit_code": 0},
            "integration_artifact_validation": {
                "valid": False,
                "path": ".codex-orchestrator/integration/validation_result.json",
                "errors": [{"path": ".codex-orchestrator/integration/integration_state.json", "message": "bad state"}],
            },
        },
    )

    result = diagnose_real_codex_attempt(ctx, attempt_id="P0001_attempt1")

    assert result["diagnosis_primary_category"] == "integration_artifact_validation_error"


def test_run_manifest_attempt_lifecycle_error_precedes_network_or_api(git_repo):
    ctx = _initialized_ctx(git_repo)
    _seed_failed_real_codex_attempt(
        ctx,
        stderr_text="network api timeout model words but lifecycle wins\n",
        run_overrides={
            "worker_failure": {"type": "WorkerExecutionError", "message": "late lifecycle failure", "exit_code": 0},
            "lifecycle_status": "ATTEMPT_FAILED_WITH_EVIDENCE",
            "failed_stage": "AFTER_WORKER_EXIT",
        },
    )

    result = diagnose_real_codex_attempt(ctx, attempt_id="P0001_attempt1")

    assert result["diagnosis_primary_category"] == "run_manifest_attempt_lifecycle_error"


def test_runbook_attempt_evidence_mismatch_precedes_network_or_api(git_repo):
    ctx = _initialized_ctx(git_repo)
    _seed_failed_real_codex_attempt(
        ctx,
        stderr_text="network api timeout model words but runbook mismatch wins\n",
        run_overrides={
            "worker_failure": {"type": "WorkerExecutionError", "message": "operator runbook mismatch", "exit_code": 0},
            "attempt_consistency": {
                "valid": False,
                "run_dir_attempt_id": "P0001_attempt1",
                "manifest_attempt_id": "P0000_attempt1",
                "diagnosis_attempt_id": "P0000_attempt1",
                "stdout_attempt_id": "P0001_attempt1",
                "stderr_attempt_id": "P0001_attempt1",
                "output_jsonl_attempt_id": "P0001_attempt1",
                "progress_attempt_id": "P0001_attempt1",
                "mismatches": ["run_dir_attempt_id != manifest_attempt_id"],
            },
        },
    )

    result = diagnose_real_codex_attempt(ctx, attempt_id="P0001_attempt1")

    assert result["diagnosis_primary_category"] == "runbook_attempt_evidence_mismatch"


def test_target_cache_artifact_leak_category_includes_cache_paths(git_repo):
    ctx = _initialized_ctx(git_repo)
    _seed_failed_real_codex_attempt(
        ctx,
        run_overrides={
            "worker_failure": {"type": "WorkerExecutionError", "message": "target hygiene gate failed", "exit_code": 0},
            "target_hygiene_gate_result": ".codex-orchestrator/runs/P0001_attempt1/gates/target_hygiene_gate_result.json",
        },
    )
    write_json(
        ctx.paths.runs_dir / "P0001_attempt1" / "gates" / "target_hygiene_gate_result.json",
        {
            "schema_version": "1.0",
            "kind": "target_hygiene_gate_result",
            "accepted": False,
            "cache_artifacts_detected": [{"path": "__pycache__/app.cpython-310.pyc"}],
            "cache_artifacts_removed": [],
        },
    )

    result = diagnose_real_codex_attempt(ctx, attempt_id="P0001_attempt1")

    assert result["diagnosis_primary_category"] == "target_cache_artifact_leak"
    diagnosis = write_json  # keep import behavior visible to static checkers
    assert diagnosis is not None


def test_network_or_api_error_requires_actual_external_error_evidence(git_repo):
    ctx = _initialized_ctx(git_repo)
    _seed_failed_real_codex_attempt(
        ctx,
        stdout_text="prompt text mentions network api model timeout only\n",
        stderr_text="ordinary worker failure\n",
        output_events=[{"message": "prompt text mentions network api model timeout only"}],
    )

    result = diagnose_real_codex_attempt(ctx, attempt_id="P0001_attempt1")

    assert result["diagnosis_primary_category"] != "network_or_api_error"


def test_true_network_api_failure_still_classified_network_or_api(git_repo):
    ctx = _initialized_ctx(git_repo)
    _seed_failed_real_codex_attempt(ctx, stderr_text="api error: rate limit from service\n")

    result = diagnose_real_codex_attempt(ctx, attempt_id="P0001_attempt1")

    assert result["diagnosis_primary_category"] == "network_or_api_error"


def test_stage_precondition_error_still_available_when_no_more_specific_category(git_repo):
    ctx = _initialized_ctx(git_repo)
    _seed_failed_real_codex_attempt(
        ctx,
        run_overrides={
            "worker_failure": {"type": "StagePreconditionError", "message": "precondition failed for verify: missing file", "exit_code": None}
        },
    )

    result = diagnose_real_codex_attempt(ctx, attempt_id="P0001_attempt1")

    assert result["diagnosis_primary_category"] == "stage_precondition_error"


def test_diagnosis_includes_integration_validation_error_path_and_message(git_repo):
    ctx = _initialized_ctx(git_repo)
    _seed_failed_real_codex_attempt(
        ctx,
        run_overrides={
            "worker_failure": {"type": "WorkerExecutionError", "message": "integration artifact validation failed", "exit_code": 0},
            "integration_artifact_validation": {
                "valid": False,
                "path": ".codex-orchestrator/integration/validation_result.json",
                "errors": [{"path": ".codex-orchestrator/integration/accepted_changes.jsonl", "message": "invalid JSONL"}],
            },
        },
    )

    diagnose_real_codex_attempt(ctx, attempt_id="P0001_attempt1")
    diagnosis = write_json
    payload = __import__("json").loads((ctx.paths.real_codex_diagnostics_dir / "P0001_attempt1_diagnosis.json").read_text())

    assert payload["diagnosis"]["error_path"] == ".codex-orchestrator/integration/accepted_changes.jsonl"
    assert payload["diagnosis"]["error_message"] == "invalid JSONL"
    assert diagnosis is not None


def test_diagnosis_includes_checkpoint_cleanliness_report_path_when_available(git_repo):
    ctx = _initialized_ctx(git_repo)
    _seed_failed_real_codex_attempt(
        ctx,
        run_overrides={
            "worker_failure": {"type": "WorkerExecutionError", "message": "integration artifact validation failed", "exit_code": 0},
            "target_cleanliness_report_path": ".codex-orchestrator/integration/checkpoints/P0001_cleanliness.json",
            "integration_artifact_validation": {
                "valid": False,
                "path": ".codex-orchestrator/integration/validation_result.json",
                "errors": [
                    {
                        "path": ".codex-orchestrator/integration/checkpoints/P0001.json",
                        "message": "target_working_tree_clean_after_checkpoint: True was expected",
                    }
                ],
            },
        },
    )

    diagnose_real_codex_attempt(ctx, attempt_id="P0001_attempt1")
    payload = __import__("json").loads((ctx.paths.real_codex_diagnostics_dir / "P0001_attempt1_diagnosis.json").read_text())

    assert payload["diagnosis"]["target_cleanliness_report_path"] == ".codex-orchestrator/integration/checkpoints/P0001_cleanliness.json"
