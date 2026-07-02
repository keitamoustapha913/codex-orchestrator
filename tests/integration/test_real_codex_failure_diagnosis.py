from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_orchestrator.run_records import append_run_record
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _initialized_ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    return ctx


def _seed_failed_real_codex_attempt(
    ctx,
    *,
    stdout_text: str = "",
    stderr_text: str = "codex exited with code 1\n",
    output_events: list[dict] | None = None,
    command_payload: dict | None = None,
    progress_events: list[dict] | None = None,
) -> str:
    run_dir = ctx.paths.runs_dir / "P0001_attempt1"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "worker_memory").mkdir(parents=True, exist_ok=True)
    (run_dir / "worker_stage").mkdir(parents=True, exist_ok=True)
    (run_dir / "worker_hooks").mkdir(parents=True, exist_ok=True)
    (run_dir / "gates").mkdir(parents=True, exist_ok=True)
    (run_dir / "stdout.txt").write_text(stdout_text, encoding="utf-8")
    (run_dir / "stderr.txt").write_text(stderr_text, encoding="utf-8")
    output_payload = output_events or [{"exit_code": 1, "event": "worker_exit"}]
    (run_dir / "output.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in output_payload),
        encoding="utf-8",
    )
    command = command_payload or {
        "args": ["codex", "exec", "--json", "prompt.md"],
        "cwd": str(ctx.root),
        "exit_code": 1,
        "patchlet_id": "P0001",
        "attempt_id": "P0001_attempt1",
    }
    (run_dir / "command.json").write_text(json.dumps(command, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if progress_events is not None:
        (run_dir / "progress.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in progress_events),
            encoding="utf-8",
        )
    (run_dir / "worker_capsule.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "kind": "worker_capsule",
                "patchlet_id": "P0001",
                "attempt_id": "P0001_attempt1",
                "run_dir": ".codex-orchestrator/runs/P0001_attempt1",
                "worker_memory_dir": ".codex-orchestrator/runs/P0001_attempt1/worker_memory",
                "worker_stage_dir": ".codex-orchestrator/runs/P0001_attempt1/worker_stage",
                "worker_hooks_dir": ".codex-orchestrator/runs/P0001_attempt1/worker_hooks",
                "gates_dir": ".codex-orchestrator/runs/P0001_attempt1/gates",
                "diagnostics_dir": ".codex-orchestrator/runs/P0001_attempt1/diagnostics",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "worker_memory" / "TASK_CONTRACT.md").write_text("# task contract\n", encoding="utf-8")
    (run_dir / "worker_memory" / "LIVE_MEMORY.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "kind": "worker_memory",
                "patchlet_id": "P0001",
                "attempt_id": "P0001_attempt1",
                "allowed_product_runtime_file": "app.py",
                "goal_ids": [],
                "invariant_ids": [],
                "evidence_ids": [],
                "graph_node_ids": [],
                "required_report_path": ".codex-orchestrator/reports/P0001.json",
                "required_probe_root": ".artifacts/probes/P0001",
                "current_stage": "worker_initialized",
                "known_facts": [],
                "previous_failures": [],
                "open_questions": [],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "worker_stage" / "05_final_report.md").write_text("# final report\n", encoding="utf-8")
    (run_dir / "worker_hooks" / "events.jsonl").write_text(
        json.dumps({"event": "before_worker_start", "kind": "worker_event"}) + "\n"
        + json.dumps({"event": "after_worker_exception", "kind": "worker_event"}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "gates" / "wrapper_gate_result.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "kind": "wrapper_gate_result",
                "patchlet_id": "P0001",
                "attempt_id": "P0001_attempt1",
                "accepted": False,
                "worker_exit_gate": "fail",
                "artifact_gate": "pass",
                "memory_gate": "pass",
                "stage_gate": "fail",
                "diff_gate": "not_run",
                "report_gate": "not_run",
                "probe_gate": "not_run",
                "final_status_gate": "missing",
                "final_status_claim": None,
                "reasons": ["worker failed"],
                "next_state": "FAILURE_CLASSIFICATION_REQUIRED",
                "blind_retry_allowed": False,
                "validator_weakening_allowed": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    prompt_artifact = ctx.paths.subprompts_dir / "0001_app.md"
    prompt_artifact.parent.mkdir(parents=True, exist_ok=True)
    prompt_artifact.write_text("# Real Codex Patchlet Contract\nCXOR_REPORT_PATH\n", encoding="utf-8")

    append_run_record(
        ctx,
        {
            "stage": "PATCHLET_EXECUTION_IN_PROGRESS",
            "worker": "real_codex",
            "worker_mode": "real_codex",
            "patchlet_id": "P0001",
            "attempt_id": "P0001_attempt1",
            "execution_mode": "worktree",
            "status": "WORKER_FAILED",
            "success": False,
            "target_root": str(ctx.root),
            "execution_root": "/tmp/cxor-p0001-test",
            "artifact_root": str(ctx.root),
            "paths": {
                "run_dir": ".codex-orchestrator/runs/P0001_attempt1",
                "stdout": ".codex-orchestrator/runs/P0001_attempt1/stdout.txt",
                "stderr": ".codex-orchestrator/runs/P0001_attempt1/stderr.txt",
                "command": ".codex-orchestrator/runs/P0001_attempt1/command.json",
                "output_jsonl": ".codex-orchestrator/runs/P0001_attempt1/output.jsonl",
                "progress_jsonl": ".codex-orchestrator/runs/P0001_attempt1/progress.jsonl",
                "diff": ".codex-orchestrator/runs/P0001_attempt1/diff.patch",
            },
            "worktree": {
                "enabled": True,
                "path": "/tmp/cxor-p0001-test",
                "base_sha": "abc123",
                "cleanup_policy": "remove",
                "cleanup_status": "removed",
            },
            "worker_failure": {
                "type": "WorkerExecutionError",
                "message": "codex worker failed with exit_code=1",
                "exit_code": command.get("exit_code", 1),
                "timed_out": command.get("timed_out"),
                "timeout_seconds": command.get("timeout_seconds"),
                "retryable": False,
                "blind_retry_allowed": False,
                "failure_category": "worker_exception",
            },
            "artifact_preservation": {
                "run_dir_exists": True,
                "stdout_exists": True,
                "stderr_exists": True,
                "command_exists": True,
                "output_jsonl_exists": True,
                "progress_jsonl_exists": progress_events is not None,
                "diff_exists": False,
            },
            "diff_validation": {
                "valid": None,
                "reason": "not_run_worker_failed_before_diff_validation",
            },
            "report_validation": {
                "valid": None,
                "reason": "not_run_worker_failed_before_report_validation",
            },
            "state_after_failure": "PATCHLET_EXECUTION_IN_PROGRESS",
        },
    )
    return "P0001_attempt1"


def test_real_codex_failure_diagnosis_writes_json_and_markdown(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(ctx)

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)

    assert result["attempt_id"] == attempt_id
    assert Path(result["diagnosis_json_path"]).exists()
    assert Path(result["diagnosis_md_path"]).exists()
    assert not validate_json_file(Path(result["diagnosis_json_path"]), "real_codex_failure_diagnosis.schema.json")


def test_real_codex_failure_diagnosis_records_evidence_paths(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(ctx)

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert diagnosis["evidence_paths"]["stdout"].endswith("stdout.txt")
    assert diagnosis["evidence_paths"]["stderr"].endswith("stderr.txt")
    assert diagnosis["evidence_paths"]["output_jsonl"].endswith("output.jsonl")
    assert diagnosis["evidence_paths"]["command"].endswith("command.json")
    assert diagnosis["evidence_paths"]["run_manifest"].endswith("run_manifest.json")
    assert diagnosis["evidence_paths"]["prompt_artifact"].endswith("0001_app.md")


def test_real_codex_failure_diagnosis_records_artifact_presence(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(ctx)

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert diagnosis["artifact_presence"]["stdout"] is True
    assert diagnosis["artifact_presence"]["stderr"] is True
    assert diagnosis["artifact_presence"]["output_jsonl"] is True
    assert diagnosis["artifact_presence"]["command"] is True
    assert diagnosis["artifact_presence"]["prompt_artifact"] is True
    assert diagnosis["artifact_presence"]["report"] is False
    assert diagnosis["artifact_presence"]["probe_run"] is False
    assert diagnosis["artifact_presence"]["diff"] is False


def test_real_codex_failure_diagnosis_records_worker_failure_type_exit_code_and_message(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(ctx)

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert diagnosis["worker_failure"]["type"] == "WorkerExecutionError"
    assert diagnosis["worker_failure"]["exit_code"] == 1
    assert "exit_code=1" in diagnosis["worker_failure"]["message"]


def test_real_codex_failure_diagnosis_never_allows_blind_retry_or_validator_weakening(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(ctx)

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert diagnosis["validator_weakening_allowed"] is False
    assert diagnosis["blind_retry_allowed"] is False


def test_real_codex_failure_diagnosis_uses_unknown_category_when_artifacts_do_not_identify_cause(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(ctx)

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert diagnosis["diagnosis"]["primary_category"] == "unknown_codex_nonzero_exit"
    assert diagnosis["diagnosis"]["confidence"] in {"low", "medium"}
    assert diagnosis["diagnosis"]["supported_by"]


def test_diagnosis_detects_auth_or_session_error_from_stderr(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(
        ctx,
        stderr_text="authentication failed: session expired\n",
    )

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert diagnosis["diagnosis"]["primary_category"] == "auth_or_session_error"
    assert "stderr_contains_auth_or_session_error" in diagnosis["observed_signals"]


def test_diagnosis_detects_cli_usage_error_from_stderr(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(
        ctx,
        stderr_text="usage: codex exec [OPTIONS]\nunknown option --bad-flag\n",
    )

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert diagnosis["diagnosis"]["primary_category"] == "codex_cli_usage_error"
    assert "stderr_contains_cli_usage_error" in diagnosis["observed_signals"]


def test_diagnosis_detects_network_or_api_error_from_output_jsonl(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(
        ctx,
        stderr_text="",
        output_events=[{"event": "error", "message": "API timeout while contacting model"}],
    )

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert diagnosis["diagnosis"]["primary_category"] == "network_or_api_error"
    assert "captured_output_contains_network_or_api_error" in diagnosis["observed_signals"]


def test_diagnosis_detects_permission_error_from_stderr(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(
        ctx,
        stderr_text="permission denied while opening credential store\n",
    )

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert diagnosis["diagnosis"]["primary_category"] == "permission_error"
    assert "stderr_contains_permission_error" in diagnosis["observed_signals"]


def test_diagnosis_records_empty_output_when_stdout_and_stderr_are_empty(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(
        ctx,
        stdout_text="",
        stderr_text="",
        output_events=[],
    )

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert "stdout_and_stderr_empty" in diagnosis["observed_signals"]
    assert diagnosis["diagnosis"]["primary_category"] == "unknown_codex_nonzero_exit"


def test_diagnosis_records_missing_report_and_missing_probe_after_worker_exit(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(ctx)

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert "report_missing_after_worker_exit" in diagnosis["observed_signals"]
    assert "probe_run_missing_after_worker_exit" in diagnosis["observed_signals"]


def test_diagnosis_reports_worker_capsule_presence(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(ctx)

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert diagnosis["artifact_presence"]["worker_capsule"] is True
    assert diagnosis["capsule"]["worker_capsule_path"].endswith("worker_capsule.json")


def test_diagnosis_reports_worker_memory_presence(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(ctx)

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert diagnosis["artifact_presence"]["worker_memory"] is True
    assert diagnosis["artifact_presence"]["task_contract"] is True
    assert diagnosis["artifact_presence"]["live_memory_json"] is True


def test_diagnosis_reports_missing_stage_artifacts(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(ctx)

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert diagnosis["artifact_presence"]["preflight_stage"] is False
    assert "worker_stage/00_preflight.md" in diagnosis["capsule"]["missing_files"]


def test_diagnosis_links_wrapper_gate_result(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(ctx)

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert diagnosis["artifact_presence"]["wrapper_gate_result"] is True
    assert diagnosis["evidence_paths"]["wrapper_gate_result"].endswith("wrapper_gate_result.json")


def test_diagnosis_reports_last_worker_event(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(ctx)

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert diagnosis["capsule"]["last_worker_event"]["event"] == "after_worker_exception"


def test_diagnosis_recommends_capsule_prompt_fix_when_preflight_missing(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(ctx)

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert "TASK_CONTRACT.md" in diagnosis["recommended_next_action"] or "prompt artifact" in diagnosis["recommended_next_action"]


def test_diagnosis_does_not_guess_when_capsule_artifacts_are_inconclusive(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(ctx)

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert diagnosis["diagnosis"]["primary_category"] == "unknown_codex_nonzero_exit"


def test_diagnosis_classifies_command_json_timed_out_as_orchestrator_subprocess_timeout(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(
        ctx,
        stderr_text="command timed out after 30 seconds\n",
        command_payload={
            "args": ["codex", "exec", "--json", "prompt.md"],
            "cwd": str(ctx.root),
            "exit_code": 124,
            "timed_out": True,
            "timeout_seconds": 30,
            "patchlet_id": "P0001",
            "attempt_id": "P0001_attempt1",
        },
    )

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert diagnosis["diagnosis"]["primary_category"] == "orchestrator_subprocess_timeout"
    assert "command_json_records_orchestrator_timeout" in diagnosis["observed_signals"]


def test_diagnosis_timeout_category_takes_precedence_over_generic_network_timeout_text(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(
        ctx,
        stderr_text="API timeout while contacting model\ncommand timed out after 30 seconds\n",
        command_payload={
            "args": ["codex", "exec", "--json", "prompt.md"],
            "cwd": str(ctx.root),
            "exit_code": 124,
            "timed_out": True,
            "timeout_seconds": 30,
            "patchlet_id": "P0001",
            "attempt_id": "P0001_attempt1",
        },
    )

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert diagnosis["diagnosis"]["primary_category"] == "orchestrator_subprocess_timeout"
    assert "captured_output_contains_network_or_api_error" not in diagnosis["observed_signals"]


def test_diagnosis_timeout_summary_mentions_configured_timeout_seconds(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(
        ctx,
        command_payload={
            "args": ["codex", "exec", "--json", "prompt.md"],
            "cwd": str(ctx.root),
            "exit_code": 124,
            "timed_out": True,
            "timeout_seconds": 30,
            "patchlet_id": "P0001",
            "attempt_id": "P0001_attempt1",
        },
    )

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert "after 30 seconds" in diagnosis["diagnosis"]["summary"]


def test_diagnosis_timeout_recommends_increase_timeout_or_simplify_prompt(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(
        ctx,
        command_payload={
            "args": ["codex", "exec", "--json", "prompt.md"],
            "cwd": str(ctx.root),
            "exit_code": 124,
            "timed_out": True,
            "timeout_seconds": 30,
            "patchlet_id": "P0001",
            "attempt_id": "P0001_attempt1",
        },
    )

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    next_action = diagnosis["recommended_next_action"].lower()
    assert "increase timeout" in next_action
    assert "simplify prompt" in next_action or "simplify" in next_action


def test_diagnosis_timeout_links_progress_jsonl_when_present(git_repo: Path):
    from codex_orchestrator.diagnostics import diagnose_real_codex_attempt

    ctx = _initialized_ctx(git_repo)
    attempt_id = _seed_failed_real_codex_attempt(
        ctx,
        command_payload={
            "args": ["codex", "exec", "--json", "prompt.md"],
            "cwd": str(ctx.root),
            "exit_code": 124,
            "timed_out": True,
            "timeout_seconds": 30,
            "patchlet_id": "P0001",
            "attempt_id": "P0001_attempt1",
        },
        progress_events=[
            {
                "schema_version": "1.0",
                "kind": "codex_progress",
                "patchlet_id": "P0001",
                "attempt_id": "P0001_attempt1",
                "elapsed_seconds": 1,
                "signal": "thread.started",
                "source": "stdout_jsonl",
            }
        ],
    )

    result = diagnose_real_codex_attempt(ctx, attempt_id=attempt_id)
    diagnosis = _read_json(Path(result["diagnosis_json_path"]))

    assert diagnosis["artifact_presence"]["progress_jsonl"] is True
    assert diagnosis["evidence_paths"]["progress_jsonl"].endswith("progress.jsonl")
    assert "progress_jsonl_present" in diagnosis["observed_signals"]
    assert "Codex was alive before timeout" in diagnosis["diagnosis"]["summary"]
