from __future__ import annotations

import json
import subprocess
import shutil
from dataclasses import dataclass

from codex_orchestrator.codex_adapter import worker_for_mode
from codex_orchestrator.errors import WorkerExecutionError, WorkerPreconditionError
from codex_orchestrator.git_guard import changed_between, git_diff, snapshot_status
from codex_orchestrator.integration_state import (
    advance_integration_ref_from_diff,
    advance_integration_ref_from_worktree,
    record_accepted_change,
)
from codex_orchestrator.patchlet_run_context import PatchletRunContext, build_patchlet_run_context
from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.run_records import upsert_run_record
from codex_orchestrator.state import load_state, now_iso, transition
from codex_orchestrator.target_hygiene import run_target_hygiene_gate
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.worker_capsule import (
    append_worker_event,
    build_worker_capsule,
    ensure_worker_capsule,
    ensure_worker_memory,
    ensure_worker_stage_templates,
    write_wrapper_gate_result,
)
from codex_orchestrator.validators.diff_validator import validate_changed_paths
from codex_orchestrator.validators.integration_artifact_validator import validate_integration_artifacts
from codex_orchestrator.validators.report_validator import ReportValidationError, validate_patchlet_report_file
from codex_orchestrator.worktree import cleanup_patchlet_worktree, create_patchlet_worktree


@dataclass(frozen=True)
class PatchletExecutionResult:
    patchlet_id: str
    status: str
    changed_paths: list[str]
    report_valid: bool
    message: str


def _record_path_for_manifest(ctx: TargetRepoContext, path) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(ctx.root))
    except ValueError:
        return str(path)


def _read_exit_code_from_run_dir(run_dir) -> int | None:
    command_path = run_dir / "command.json"
    if command_path.exists():
        try:
            return json.loads(command_path.read_text(encoding="utf-8")).get("exit_code")
        except Exception:
            return None
    return None


def _read_command_from_run_dir(run_dir) -> dict:
    command_path = run_dir / "command.json"
    if command_path.exists():
        try:
            data = json.loads(command_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


CAPSULE_LIKE_TARGET_ROOT_DIRS = (
    "worker_stage",
    "worker_memory",
    "worker_hooks",
    "gates",
    "diagnostics",
)


def _capsule_path_violation_reasons(ctx: TargetRepoContext, run_ctx: PatchletRunContext) -> list[str]:
    reasons: list[str] = []
    for dirname in CAPSULE_LIKE_TARGET_ROOT_DIRS:
        wrong_path = ctx.root / dirname
        if not wrong_path.exists():
            continue
        expected = run_ctx.run_dir / dirname
        reasons.append(
            f"worker capsule artifact written outside run directory: {dirname}/; "
            f"expected {dirname} artifacts under {_record_path_for_manifest(ctx, expected)}/"
        )
    return reasons


def _is_capsule_path_violation_error(exc: Exception) -> bool:
    return "worker capsule artifact written outside run directory:" in str(exc)


def _append_failed_worker_run_record(
    ctx: TargetRepoContext,
    *,
    patchlet: dict,
    run_ctx: PatchletRunContext,
    worker_mode: str,
    use_worktree: bool,
    worktree_ctx,
    cleanup_status: str | None,
    worker_error: Exception,
    state_stage: str,
    worker_capsule_manifest: str | None,
    wrapper_gate_result: str | None,
) -> None:
    run_dir = run_ctx.run_dir
    command = _read_command_from_run_dir(run_dir)
    exit_code = command.get("exit_code")
    paths = _base_manifest_paths(ctx, run_dir)
    _upsert_attempt(ctx, attempt_id=run_dir.name, lifecycle_status="ATTEMPT_FAILED_WITH_EVIDENCE", **{
        "stage": "PATCHLET_EXECUTION_IN_PROGRESS",
        "worker": worker_mode,
        "worker_mode": worker_mode,
        "patchlet_id": patchlet["patchlet_id"],
        "repair_plan_id": patchlet.get("repair_plan_id"),
        "source_failure_ids": patchlet.get("source_failure_ids", []),
        "execution_mode": "worktree" if use_worktree else "direct",
        "status": "WORKER_FAILED",
        "success": False,
        "target_root": str(run_ctx.target_root),
        "execution_root": str(run_ctx.execution_root),
        "artifact_root": str(run_ctx.artifact_root),
        "worker_capsule_manifest": worker_capsule_manifest,
        "paths": paths,
        "worktree": {
            "enabled": use_worktree,
            "path": str(run_ctx.worktree_path) if run_ctx.worktree_path else None,
            "base_sha": worktree_ctx.base_sha if worktree_ctx else None,
            "base_source": worktree_ctx.base_source if worktree_ctx else None,
            "integration_ref": worktree_ctx.integration_ref if worktree_ctx else None,
            "cleanup_policy": worktree_ctx.cleanup_policy if worktree_ctx else None,
            "cleanup_status": cleanup_status,
        },
        "worker_failure": {
            "type": type(worker_error).__name__,
            "message": str(worker_error),
            "exit_code": exit_code,
            "timed_out": command.get("timed_out"),
            "timeout_seconds": command.get("timeout_seconds"),
            "selected_model": command.get("selected_model"),
            "selected_reasoning": command.get("selected_reasoning"),
            "retryable": False,
            "blind_retry_allowed": False,
            "failure_category": "worker_capsule_path_violation" if _is_capsule_path_violation_error(worker_error) else "worker_exception",
        },
        "artifact_preservation": {
            "run_dir_exists": run_dir.exists(),
            "stdout_exists": (run_dir / "stdout.txt").exists(),
            "stderr_exists": (run_dir / "stderr.txt").exists(),
            "command_exists": (run_dir / "command.json").exists(),
            "output_jsonl_exists": (run_dir / "output.jsonl").exists(),
            "progress_jsonl_exists": (run_dir / "progress.jsonl").exists(),
            "diff_exists": (run_dir / "diff.patch").exists(),
        },
        "wrapper_gate_result": wrapper_gate_result,
        "timed_out": command.get("timed_out"),
        "timeout_seconds": command.get("timeout_seconds"),
        "selected_model": command.get("selected_model"),
        "selected_reasoning": command.get("selected_reasoning"),
        "progress_path": paths["progress_jsonl"],
        "diff_validation": {
            "valid": None,
            "reason": "not_run_worker_failed_before_diff_validation",
        },
        "report_validation": {
            "valid": None,
            "reason": "not_run_worker_failed_before_report_validation",
        },
        "state_after_failure": state_stage,
    })


def _load_patchlet_index(ctx: TargetRepoContext) -> dict:
    if not ctx.paths.patchlet_index.exists():
        raise FileNotFoundError(f"Missing patchlet index: {ctx.paths.patchlet_index}")
    return read_json(ctx.paths.patchlet_index)


def _save_patchlet_index(ctx: TargetRepoContext, index: dict) -> None:
    write_json(ctx.paths.patchlet_index, index)


def _next_pending_patchlet(index: dict) -> dict | None:
    completed = {p["patchlet_id"] for p in index.get("patchlets", []) if p.get("status") in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}}
    for patchlet in index.get("patchlets", []):
        if patchlet.get("status") != "PENDING":
            continue
        if all(dep in completed for dep in patchlet.get("depends_on", [])):
            return patchlet
    return None


def _record_failure(ctx: TargetRepoContext, *, source_id: str, observed_failure: str, changed_paths: list[str]) -> str:
    existing = sorted(ctx.paths.failures_dir.glob("F*.json"))
    failure_id = f"F{len(existing) + 1:04d}"
    record = {
        "schema_version": "1.0",
        "kind": "failure_record",
        "failure_id": failure_id,
        "source": "PATCHLET_FAILED",
        "source_type": "patchlet",
        "source_id": source_id,
        "source_patchlet_ids": [source_id],
        "observed_failure": observed_failure,
        "blocking_invariant_ids": ["I001"],
        "evidence_ids": [],
        "graph_node_ids": [],
        "changed_paths": changed_paths,
        "suspected_scope": "inside_known_graph",
        "required_next_step": "classify",
        "created_at": now_iso(),
    }
    write_json(ctx.paths.failures_dir / f"{failure_id}.json", record)
    (ctx.paths.failures_dir / f"{failure_id}.md").write_text(f"# {failure_id}\n\n{observed_failure}\n", encoding="utf-8")
    return failure_id


def _apply_validated_diff_to_target(ctx: TargetRepoContext, *, diff_path) -> None:
    result = subprocess.run(
        ["git", "-C", str(ctx.root), "apply", str(diff_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"validated merge failed: {result.stderr.strip() or result.stdout.strip()}")


def _reverse_validated_diff_from_target(ctx: TargetRepoContext, *, diff_path) -> None:
    result = subprocess.run(
        ["git", "-C", str(ctx.root), "apply", "-R", str(diff_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"validated target cleanup failed: {result.stderr.strip() or result.stdout.strip()}")


def _cleanup_direct_worker_changes(ctx: TargetRepoContext, changed_paths: list[str]) -> None:
    for rel_path in changed_paths:
        if rel_path.startswith(".codex-orchestrator/") or rel_path.startswith(".artifacts/"):
            continue
        path = ctx.root / rel_path
        if path.exists() and not _is_tracked(ctx, rel_path):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            continue
        subprocess.run(
            ["git", "-C", str(ctx.root), "checkout", "--", rel_path],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )


def _is_tracked(ctx: TargetRepoContext, rel_path: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(ctx.root), "ls-files", "--error-unmatch", rel_path],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result.returncode == 0


def _write_integration_validation_result(ctx: TargetRepoContext) -> dict:
    result = validate_integration_artifacts(ctx.root)
    path = ctx.paths.integration_dir / "validation_result.json"
    write_json(path, result)
    return result


def _base_manifest_paths(ctx: TargetRepoContext, run_dir, diff_path=None) -> dict:
    return {
        "run_dir": _record_path_for_manifest(ctx, run_dir),
        "stdout": _record_path_for_manifest(ctx, run_dir / "stdout.txt"),
        "stderr": _record_path_for_manifest(ctx, run_dir / "stderr.txt"),
        "command": _record_path_for_manifest(ctx, run_dir / "command.json"),
        "output_jsonl": _record_path_for_manifest(ctx, run_dir / "output.jsonl"),
        "progress_jsonl": _record_path_for_manifest(ctx, run_dir / "progress.jsonl"),
        "diff": _record_path_for_manifest(ctx, diff_path or (run_dir / "diff.patch")),
    }


def _upsert_attempt(ctx: TargetRepoContext, *, attempt_id: str, lifecycle_status: str, **record) -> None:
    payload = {"lifecycle_status": lifecycle_status, **record}
    upsert_run_record(ctx, attempt_id=attempt_id, record=payload)


def _merge_hygiene_cache_evidence(final_result: dict, pre_result: dict | None) -> dict:
    if not pre_result:
        return final_result
    merged = dict(final_result)
    for key in ("cache_artifacts_detected", "cache_artifacts_removed"):
        existing = list(merged.get(key, []))
        seen = {
            item.get("path")
            for item in existing
            if isinstance(item, dict)
        }
        for item in pre_result.get(key, []):
            if isinstance(item, dict) and item.get("path") not in seen:
                existing.append(item)
                seen.add(item.get("path"))
        merged[key] = existing
    return merged


def run_next_patchlet(ctx: TargetRepoContext, *, worker_mode: str = "mock", use_worktree: bool = False) -> PatchletExecutionResult:
    index = _load_patchlet_index(ctx)
    patchlet = _next_pending_patchlet(index)
    if patchlet is None:
        return PatchletExecutionResult("", "NO_PENDING_PATCHLETS", [], True, "no pending patchlets")
    pid = patchlet["patchlet_id"]
    state = load_state(ctx)
    state.current_patchlet_id = pid
    state.attempts[pid] = state.attempts.get(pid, 0) + 1
    transition(ctx, state, "PATCHLET_EXECUTION_IN_PROGRESS", reason=f"running {pid}")

    run_id = f"{pid}_attempt{state.attempts[pid]}"
    initial_run_dir = ctx.paths.runs_dir / run_id
    _upsert_attempt(
        ctx,
        attempt_id=run_id,
        lifecycle_status="ATTEMPT_STARTED",
        stage="PATCHLET_EXECUTION_IN_PROGRESS",
        worker=worker_mode,
        worker_mode=worker_mode,
        patchlet_id=pid,
        repair_plan_id=patchlet.get("repair_plan_id"),
        source_failure_ids=patchlet.get("source_failure_ids", []),
        execution_mode="worktree" if use_worktree else "direct",
        status="ATTEMPT_STARTED",
        success=False,
        paths=_base_manifest_paths(ctx, initial_run_dir),
    )
    pre_hygiene = run_target_hygiene_gate(
        target_repo_root=ctx.root,
        workflow_dir=ctx.paths.workflow_dir,
        probe_dir=ctx.paths.probe_dir,
        run_dir=initial_run_dir,
        patchlet_id=pid,
        attempt_id=run_id,
        allowed_product_runtime_file=patchlet.get("allowed_product_runtime_file"),
    )
    if not pre_hygiene["accepted"]:
        raise WorkerPreconditionError("target hygiene gate failed: " + "; ".join(pre_hygiene.get("reasons", [])))
    worktree_ctx = create_patchlet_worktree(ctx, patchlet_id=pid) if use_worktree else None
    run_ctx = build_patchlet_run_context(
        ctx,
        patchlet=patchlet,
        run_id=run_id,
        execution_root=worktree_ctx.path if worktree_ctx else ctx.root,
        artifact_root=ctx.root,
        is_worktree=bool(worktree_ctx),
        worktree_path=worktree_ctx.path if worktree_ctx else None,
    )
    run_dir = run_ctx.run_dir
    worker_capsule = build_worker_capsule(run_ctx, patchlet)
    ensure_worker_capsule(ctx, worker_capsule)
    ensure_worker_memory(ctx, worker_capsule, run_ctx, patchlet, worker_mode=worker_mode)
    ensure_worker_stage_templates(worker_capsule, run_ctx, patchlet)
    worker_capsule_manifest = _record_path_for_manifest(ctx, worker_capsule.manifest_path)
    wrapper_gate_result_path = _record_path_for_manifest(ctx, worker_capsule.gates_dir / "wrapper_gate_result.json")
    append_worker_event(
        ctx,
        worker_capsule,
        run_ctx,
        event="before_worker_start",
        worker_mode=worker_mode,
    )
    worker = worker_for_mode(worker_mode)
    cleanup_status = None
    worker_error: WorkerExecutionError | WorkerPreconditionError | None = None
    before = snapshot_status(run_ctx.execution_root)
    worker_result = None
    changed_paths: list[str] = []
    diff_text = ""
    diff_path = run_dir / "diff.patch"
    diff_result = None
    integration_validation_result: dict | None = None
    try:
        worker_result = worker.run_patchlet(ctx, patchlet, run_dir=run_dir, run_ctx=run_ctx)
        _upsert_attempt(
            ctx,
            attempt_id=run_id,
            lifecycle_status="WORKER_EXITED",
            exit_code=worker_result.exit_code,
            stdout=worker_result.stdout,
            stderr=worker_result.stderr,
            paths=_base_manifest_paths(ctx, run_dir, diff_path),
        )
        capsule_path_violations = _capsule_path_violation_reasons(ctx, run_ctx)
        if capsule_path_violations:
            raise WorkerExecutionError("; ".join(capsule_path_violations))
        append_worker_event(
            ctx,
            worker_capsule,
            run_ctx,
            event="after_prompt_written",
            worker_mode=worker_mode,
            details={
                "command_path": _record_path_for_manifest(ctx, run_dir / "command.json"),
                "output_jsonl_path": _record_path_for_manifest(ctx, run_dir / "output.jsonl"),
            },
        )
        append_worker_event(
            ctx,
            worker_capsule,
            run_ctx,
            event="after_worker_exit",
            worker_mode=worker_mode,
            details={
                "exit_code": worker_result.exit_code,
                "stdout_path": _record_path_for_manifest(ctx, run_dir / "stdout.txt"),
                "stderr_path": _record_path_for_manifest(ctx, run_dir / "stderr.txt"),
                "output_jsonl_path": _record_path_for_manifest(ctx, run_dir / "output.jsonl"),
            },
        )
        after = snapshot_status(run_ctx.execution_root)
        changed_paths = changed_between(before, after)
        diff_text = git_diff(run_ctx.execution_root)
        run_dir.mkdir(parents=True, exist_ok=True)
        diff_path.write_text(diff_text, encoding="utf-8")
        (run_dir / "diff_name_status.txt").write_text("\n".join(changed_paths) + "\n", encoding="utf-8")
        append_worker_event(
            ctx,
            worker_capsule,
            run_ctx,
            event="after_diff_capture",
            worker_mode=worker_mode,
            details={
                "diff_path": _record_path_for_manifest(ctx, diff_path),
                "changed_paths": changed_paths,
            },
        )
        diff_result = validate_changed_paths(changed_paths, patchlet)
    except (WorkerExecutionError, WorkerPreconditionError) as exc:
        worker_error = exc
        append_worker_event(
            ctx,
            worker_capsule,
            run_ctx,
            event="after_worker_exception",
            worker_mode=worker_mode,
            details={
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "exit_code": _read_exit_code_from_run_dir(run_dir),
                "stdout_path": _record_path_for_manifest(ctx, run_dir / "stdout.txt"),
                "stderr_path": _record_path_for_manifest(ctx, run_dir / "stderr.txt"),
                "output_jsonl_path": _record_path_for_manifest(ctx, run_dir / "output.jsonl"),
            },
        )

    if worker_error is not None:
        if worktree_ctx is not None:
            worktree_ctx = cleanup_patchlet_worktree(worktree_ctx)
            cleanup_status = worktree_ctx.cleanup_status
        gate_result = write_wrapper_gate_result(
            ctx,
            worker_capsule,
            run_ctx,
            worker_mode=worker_mode,
            worker_exit_ok=False,
            diff_allowed=None,
            report_valid=None,
            probe_valid=None,
            next_state=load_state(ctx).stage,
            reasons=[str(worker_error)],
        )
        append_worker_event(
            ctx,
            worker_capsule,
            run_ctx,
            event="after_wrapper_gate",
            worker_mode=worker_mode,
            details={
                "accepted": gate_result["accepted"],
                "wrapper_gate_result": wrapper_gate_result_path,
            },
        )
        _append_failed_worker_run_record(
            ctx,
            patchlet=patchlet,
            run_ctx=run_ctx,
            worker_mode=worker_mode,
            use_worktree=use_worktree,
            worktree_ctx=worktree_ctx,
            cleanup_status=cleanup_status,
            worker_error=worker_error,
            state_stage=load_state(ctx).stage,
            worker_capsule_manifest=worker_capsule_manifest,
            wrapper_gate_result=wrapper_gate_result_path,
        )
        raise worker_error

    assert worker_result is not None
    assert diff_result is not None
    failure_id: str | None = None
    report_valid = False
    report_status = "FAILED_WITH_EVIDENCE"
    report_error: str | None = None
    try:
        if not diff_result.allowed:
            if not use_worktree:
                _cleanup_direct_worker_changes(ctx, changed_paths)
            failure_id = _record_failure(
                ctx,
                source_id=pid,
                observed_failure=f"Unauthorized diff detected: {', '.join(diff_result.unauthorized_paths)}",
                changed_paths=changed_paths,
            )
            report_status = "FAILED_WITH_EVIDENCE"
        else:
            try:
                if worker_result.report_path is None:
                    raise ReportValidationError("Worker did not create a report")
                report = validate_patchlet_report_file(worker_result.report_path, patchlet)
                report_valid = True
                report_status = report["status"]
                append_worker_event(
                    ctx,
                    worker_capsule,
                    run_ctx,
                    event="after_report_validation",
                    worker_mode=worker_mode,
                    details={
                        "report_path": _record_path_for_manifest(ctx, worker_result.report_path),
                        "report_valid": True,
                        "report_status": report_status,
                    },
                )
                _upsert_attempt(
                    ctx,
                    attempt_id=run_id,
                    lifecycle_status="REPORT_VALIDATED",
                    report_valid=True,
                    report_validation={"valid": True, "reason": None},
                    status=report_status,
                )
                append_worker_event(
                    ctx,
                    worker_capsule,
                    run_ctx,
                    event="after_probe_validation",
                    worker_mode=worker_mode,
                    details={
                        "report_path": _record_path_for_manifest(ctx, worker_result.report_path),
                        "probe_refs": report.get("probe_artifact_refs", []),
                        "probe_valid": True,
                    },
                )
            except ReportValidationError as exc:
                if not use_worktree:
                    _cleanup_direct_worker_changes(ctx, changed_paths)
                report_error = str(exc)
                append_worker_event(
                    ctx,
                    worker_capsule,
                    run_ctx,
                    event="after_report_validation",
                    worker_mode=worker_mode,
                    details={
                        "report_path": _record_path_for_manifest(ctx, worker_result.report_path) if worker_result.report_path else None,
                        "report_valid": False,
                        "report_error": report_error,
                    },
                )
                _upsert_attempt(
                    ctx,
                    attempt_id=run_id,
                    lifecycle_status="REPORT_VALIDATED",
                    report_valid=False,
                    report_error=report_error,
                    report_validation={"valid": False, "reason": report_error},
                    status="FAILED_WITH_EVIDENCE",
                )
                failure_id = _record_failure(
                    ctx,
                    source_id=pid,
                    observed_failure=f"Invalid or missing patchlet report: {exc}",
                    changed_paths=changed_paths,
                )
                report_status = "FAILED_WITH_EVIDENCE"

            integration_checkpoint_sha: str | None = None
            if report_valid and report_status not in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"} and not use_worktree:
                _cleanup_direct_worker_changes(ctx, changed_paths)
            if report_valid and report_status in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"} and diff_text:
                if use_worktree and worktree_ctx is not None:
                    integration_checkpoint_sha = advance_integration_ref_from_worktree(
                        ctx,
                        worktree_path=worktree_ctx.path,
                        patchlet_id=pid,
                        changed_product_runtime_files=diff_result.product_runtime_paths,
                    )
                else:
                    integration_checkpoint_sha = advance_integration_ref_from_diff(
                        ctx,
                        diff_path=diff_path,
                        patchlet_id=pid,
                        changed_product_runtime_files=diff_result.product_runtime_paths,
                    )
                    _reverse_validated_diff_from_target(ctx, diff_path=diff_path)
    finally:
        pass

    next_state = (
        "FAILURE_CLASSIFICATION_REQUIRED"
        if report_status in {"FAILED_WITH_EVIDENCE", "BLOCKED_WITH_EVIDENCE"} or not diff_result.allowed
        else "PATCHLETS_READY"
    )
    gate_result = write_wrapper_gate_result(
        ctx,
        worker_capsule,
        run_ctx,
        worker_mode=worker_mode,
        worker_exit_ok=True,
        diff_allowed=diff_result.allowed,
        report_valid=report_valid,
        probe_valid=report_valid,
        next_state=next_state,
        report_path=worker_result.report_path,
        reasons=([report_error] if report_error else []),
    )
    append_worker_event(
        ctx,
        worker_capsule,
        run_ctx,
        event="after_wrapper_gate",
        worker_mode=worker_mode,
        details={
            "accepted": gate_result["accepted"],
            "wrapper_gate_result": wrapper_gate_result_path,
        },
    )
    _upsert_attempt(
        ctx,
        attempt_id=run_id,
        lifecycle_status="WRAPPER_GATE_EVALUATED",
        wrapper_gate_result=wrapper_gate_result_path,
        wrapper_gate_accepted=gate_result["accepted"],
    )
    if gate_result["accepted"] and report_status in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}:
        target_hygiene_result = run_target_hygiene_gate(
            target_repo_root=ctx.root,
            workflow_dir=ctx.paths.workflow_dir,
            probe_dir=ctx.paths.probe_dir,
            run_dir=run_dir,
            patchlet_id=pid,
            attempt_id=run_id,
            allowed_product_runtime_file=patchlet.get("allowed_product_runtime_file"),
        )
        target_hygiene_result = _merge_hygiene_cache_evidence(target_hygiene_result, pre_hygiene)
        append_worker_event(
            ctx,
            worker_capsule,
            run_ctx,
            event="after_target_hygiene",
            worker_mode=worker_mode,
            details={
                "accepted": target_hygiene_result["accepted"],
                "target_hygiene_gate_result": target_hygiene_result["result_path"],
            },
        )
        if not target_hygiene_result["accepted"]:
            _upsert_attempt(
                ctx,
                attempt_id=run_id,
                lifecycle_status="TARGET_HYGIENE_EVALUATED",
                target_hygiene_gate_result=target_hygiene_result["result_path"],
                target_hygiene_accepted=False,
                failed_stage="TARGET_HYGIENE_FAILED",
            )
            _upsert_attempt(
                ctx,
                attempt_id=run_id,
                lifecycle_status="ATTEMPT_FAILED_WITH_EVIDENCE",
                failed_stage="TARGET_HYGIENE_FAILED",
                error_type="WorkerExecutionError",
                error_message="target hygiene gate failed: " + "; ".join(target_hygiene_result.get("reasons", [])),
                status="FAILED_WITH_EVIDENCE",
                success=False,
            )
            raise WorkerExecutionError("target hygiene gate failed: " + "; ".join(target_hygiene_result.get("reasons", [])))
        _upsert_attempt(
            ctx,
            attempt_id=run_id,
            lifecycle_status="TARGET_HYGIENE_EVALUATED",
            target_hygiene_gate_result=target_hygiene_result["result_path"],
            target_hygiene_accepted=True,
        )
        record_accepted_change(
            ctx,
            patchlet=patchlet,
            attempt_id=run_id,
            changed_product_runtime_files=diff_result.product_runtime_paths,
            diff_path=diff_path,
            report_path=worker_result.report_path,
            probe_root=ctx.paths.probe_dir / pid,
            wrapper_gate_result=wrapper_gate_result_path,
            new_integration_sha=integration_checkpoint_sha,
            target_hygiene_result=target_hygiene_result,
        )
        _upsert_attempt(
            ctx,
            attempt_id=run_id,
            lifecycle_status="INTEGRATION_CHECKPOINT_WRITTEN",
            integration_checkpoint_path=_record_path_for_manifest(ctx, ctx.paths.integration_checkpoints_dir / f"{pid}.json"),
            target_cleanliness_report_path=_record_path_for_manifest(ctx, ctx.paths.integration_checkpoints_dir / f"{pid}_cleanliness.json"),
        )
        integration_validation_result = _write_integration_validation_result(ctx)
        _upsert_attempt(
            ctx,
            attempt_id=run_id,
            lifecycle_status="INTEGRATION_ARTIFACTS_VALIDATED",
            integration_artifact_validation={
                "path": _record_path_for_manifest(ctx, ctx.paths.integration_dir / "validation_result.json"),
                "valid": integration_validation_result.get("valid"),
                "errors": integration_validation_result.get("errors", []),
            },
        )
        if not integration_validation_result["valid"]:
            _upsert_attempt(
                ctx,
                attempt_id=run_id,
                lifecycle_status="ATTEMPT_FAILED_WITH_EVIDENCE",
                failed_stage="INTEGRATION_ARTIFACTS_VALIDATION_FAILED",
                error_type="WorkerExecutionError",
                error_message="integration artifact validation failed",
                status="FAILED_WITH_EVIDENCE",
                success=False,
            )
            raise WorkerExecutionError("integration artifact validation failed")
    if worktree_ctx is not None:
        worktree_ctx = cleanup_patchlet_worktree(worktree_ctx)
        cleanup_status = worktree_ctx.cleanup_status

    _upsert_attempt(ctx, attempt_id=run_id, lifecycle_status="ATTEMPT_ACCEPTED" if report_status in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"} and gate_result["accepted"] else "ATTEMPT_FAILED_WITH_EVIDENCE", **{
        "stage": "PATCHLET_EXECUTION_IN_PROGRESS",
        "worker": worker_mode,
        "worker_mode": worker_mode,
        "patchlet_id": pid,
        "repair_plan_id": patchlet.get("repair_plan_id"),
        "source_failure_ids": patchlet.get("source_failure_ids", []),
        "execution_mode": "worktree" if use_worktree else "direct",
        "status": report_status,
        "success": report_status not in {"FAILED_WITH_EVIDENCE", "BLOCKED_WITH_EVIDENCE"},
        "target_root": str(run_ctx.target_root),
        "execution_root": str(run_ctx.execution_root),
        "artifact_root": str(run_ctx.artifact_root),
        "worker_capsule_manifest": worker_capsule_manifest,
        "exit_code": worker_result.exit_code,
        "stdout": worker_result.stdout,
        "stderr": worker_result.stderr,
        "changed_files": changed_paths,
        "paths": {
            "run_dir": _record_path_for_manifest(ctx, run_dir),
            "stdout": _record_path_for_manifest(ctx, run_dir / "stdout.txt"),
            "stderr": _record_path_for_manifest(ctx, run_dir / "stderr.txt"),
            "command": _record_path_for_manifest(ctx, run_dir / "command.json"),
            "output_jsonl": _record_path_for_manifest(ctx, run_dir / "output.jsonl"),
            "progress_jsonl": _record_path_for_manifest(ctx, run_dir / "progress.jsonl"),
            "diff": _record_path_for_manifest(ctx, diff_path),
        },
        "diff_allowed": diff_result.allowed,
        "diff_validation": {
            "valid": diff_result.allowed,
            "changed_product_runtime_files": diff_result.product_runtime_paths,
            "artifact_files": diff_result.artifact_paths,
            "unauthorized_files": diff_result.unauthorized_paths,
        },
        "report_validation": {
            "valid": report_valid,
            "reason": None if report_valid else report_error,
        },
        "worktree": {
            "enabled": use_worktree,
            "path": str(run_ctx.worktree_path) if run_ctx.worktree_path else None,
            "base_sha": worktree_ctx.base_sha if worktree_ctx else None,
            "base_source": worktree_ctx.base_source if worktree_ctx else None,
            "integration_ref": worktree_ctx.integration_ref if worktree_ctx else None,
            "cleanup_policy": worktree_ctx.cleanup_policy if worktree_ctx else None,
            "cleanup_status": cleanup_status,
        },
        "wrapper_gate_result": wrapper_gate_result_path,
        "integration_artifact_validation": {
            "path": _record_path_for_manifest(ctx, ctx.paths.integration_dir / "validation_result.json")
            if integration_validation_result is not None
            else None,
            "valid": integration_validation_result.get("valid") if integration_validation_result else None,
        },
        "report_valid": report_valid,
        "report_error": report_error,
        "timed_out": _read_command_from_run_dir(run_dir).get("timed_out"),
        "timeout_seconds": _read_command_from_run_dir(run_dir).get("timeout_seconds"),
        "selected_model": _read_command_from_run_dir(run_dir).get("selected_model"),
        "selected_reasoning": _read_command_from_run_dir(run_dir).get("selected_reasoning"),
        "progress_path": _record_path_for_manifest(ctx, run_dir / "progress.jsonl"),
    })

    if not diff_result.allowed:
        patchlet["status"] = "FAILED_WITH_EVIDENCE"
        _save_patchlet_index(ctx, index)
        state = load_state(ctx)
        if pid not in state.failed_patchlets:
            state.failed_patchlets.append(pid)
        if pid in state.pending_patchlets:
            state.pending_patchlets.remove(pid)
        transition(ctx, state, "FAILURE_CLASSIFICATION_REQUIRED", reason=f"{pid} unauthorized diff {failure_id}")
        return PatchletExecutionResult(pid, "FAILED_WITH_EVIDENCE", changed_paths, False, f"unauthorized diff; failure {failure_id}")

    patchlet["status"] = report_status
    _save_patchlet_index(ctx, index)
    state = load_state(ctx)
    if pid in state.pending_patchlets:
        state.pending_patchlets.remove(pid)
    if report_status == "COMPLETE" and pid not in state.completed_patchlets:
        state.completed_patchlets.append(pid)
    elif report_status == "VERIFIED_NO_CHANGE_NEEDED" and pid not in state.verified_no_change_needed:
        state.verified_no_change_needed.append(pid)
    elif report_status == "BLOCKED_WITH_EVIDENCE" and pid not in state.blocked_patchlets:
        state.blocked_patchlets.append(pid)
    elif report_status == "FAILED_WITH_EVIDENCE" and pid not in state.failed_patchlets:
        state.failed_patchlets.append(pid)

    if report_status in {"FAILED_WITH_EVIDENCE", "BLOCKED_WITH_EVIDENCE"} or not report_valid:
        transition(ctx, state, "FAILURE_CLASSIFICATION_REQUIRED", reason=f"{pid} produced {report_status}")
    else:
        transition(ctx, state, "PATCHLET_EXECUTION_COMPLETE", reason=f"{pid} produced {report_status}")
    return PatchletExecutionResult(pid, report_status, changed_paths, report_valid, "patchlet execution recorded")


def run_all_patchlets(ctx: TargetRepoContext, *, worker_mode: str = "mock", use_worktree: bool = False) -> list[PatchletExecutionResult]:
    results: list[PatchletExecutionResult] = []
    while True:
        result = run_next_patchlet(ctx, worker_mode=worker_mode, use_worktree=use_worktree)
        if result.status == "NO_PENDING_PATCHLETS":
            break
        results.append(result)
        if result.status in {"FAILED_WITH_EVIDENCE", "BLOCKED_WITH_EVIDENCE"}:
            break
    return results
