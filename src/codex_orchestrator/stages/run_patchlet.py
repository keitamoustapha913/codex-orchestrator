from __future__ import annotations

import json
import os
import re
import subprocess
import shutil
import hashlib
import mimetypes
from dataclasses import dataclass
from pathlib import Path

from codex_orchestrator.codex_adapter import worker_for_mode
from codex_orchestrator.codex_execution_policy import soft_deadline_seconds
from codex_orchestrator.errors import (
    WorkerExecutionError,
    WorkerInterruptedError,
    WorkerPreconditionError,
    WorkerTimeoutError,
)
from codex_orchestrator.git_guard import changed_between, git_diff, snapshot_status
from codex_orchestrator.integration_state import (
    advance_integration_ref_from_diff,
    advance_integration_ref_from_worktree,
    record_accepted_change,
)
from codex_orchestrator.goal_coverage import evaluate_goal_coverage_gate
from codex_orchestrator.goal_progress import update_goal_progress
from codex_orchestrator.independent_probe_rerun import run_independent_probe_rerun_gate
from codex_orchestrator.patchlet_run_context import PatchletRunContext, build_patchlet_run_context
from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.loop_governor import record_failure_signature
from codex_orchestrator.operator_events import append_operator_event
from codex_orchestrator.prompt_index import upsert_prompt_index_entry
from codex_orchestrator.report_ingestion import ingest_patchlet_report
from codex_orchestrator.run_records import upsert_run_record
from codex_orchestrator.semantic_result_normalization import canonicalize_semantic_goal_results_after_probe
from codex_orchestrator.semantic_goal_runner import run_semantic_goal_checks
from codex_orchestrator.semantic_goals import load_semantic_goal_spec, required_structured_criteria
from codex_orchestrator.state import load_state, now_iso, transition
from codex_orchestrator.target_hygiene import run_target_hygiene_gate
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.worker_capsule import (
    append_worker_event,
    build_worker_capsule,
    ensure_worker_capsule,
    ensure_worker_memory,
    ensure_worker_stage_templates,
    _semantic_worker_prompt_section,
    slice_boundary_contract_text,
    write_wrapper_gate_result,
)
from codex_orchestrator.validators.diff_validator import validate_changed_paths
from codex_orchestrator.validators.integration_artifact_validator import validate_integration_artifacts
from codex_orchestrator.validators.report_validator import ReportValidationError, validate_patchlet_report_file
from codex_orchestrator.workflow_identity import read_workflow_identity
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

EXECUTION_ROOT_SCRATCH_FILENAMES = {
    ".report_check.json",
    "report_validation.json",
}

SCRATCH_TEXT_EXTENSIONS = {".json", ".txt", ".log", ".md", ".out", ".scratch", ".tmp"}
SCRATCH_ROLE_PREFIXES = (
    "report_check",
    "report_validation",
    "report_validated",
    "probe_check",
    "probe_validation",
    "validation_report",
    "worker_report_check",
)
MAX_SCRATCH_ARTIFACT_BYTES = 1024 * 1024
SCRATCH_ROLE_SUBJECTS = {"report", "probe", "artifact", "result"}
SCRATCH_ROLE_ACTIONS = {"check", "valid", "validate", "validated", "validation", "verify", "verified", "verification"}
PATCHLET_REPORT_FORMATTING_ROLE_ACTIONS = {
    "pretty",
    "formatted",
    "format",
    "check",
    "validated",
    "validation",
    "valid",
    "verify",
    "verification",
    "output",
    "rendered",
}


def _declared_scratch_artifacts(report_path: Path | None) -> set[str]:
    if report_path is None or not report_path.exists():
        return set()
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    declared: set[str] = set()
    for value in data.get("changed_artifact_files", []):
        if isinstance(value, str) and "/" not in value and value:
            declared.add(value)
    return declared


def _is_quarantinable_declared_scratch(path: Path, *, declared: set[str], allowed_product_runtime_file: str | None) -> bool:
    if path.name not in declared:
        return False
    if path.name == allowed_product_runtime_file:
        return False
    return path.suffix.lower() in SCRATCH_TEXT_EXTENSIONS


def _scratch_name_tokens(path: Path) -> list[str]:
    normalized = path.stem.replace("-", "_").replace(".", "_").lstrip(".").lower()
    return [token for token in normalized.split("_") if token]


def _has_patchlet_id_token(tokens: list[str]) -> bool:
    if any(re.fullmatch(r"p\d{4,}", token) for token in tokens):
        return True
    return any(
        token == "p" and index + 1 < len(tokens) and re.fullmatch(r"\d{4,}", tokens[index + 1])
        for index, token in enumerate(tokens)
    )


def _is_patchlet_prefixed_report_formatting_scratch(path: Path) -> bool:
    tokens = _scratch_name_tokens(path)
    if not _has_patchlet_id_token(tokens):
        return False
    if "report" not in tokens:
        return False
    return bool(PATCHLET_REPORT_FORMATTING_ROLE_ACTIONS.intersection(tokens))


def _scratch_role_reason(path: Path) -> str | None:
    stem = path.stem.lower().replace("-", "_").lstrip(".")
    if _is_patchlet_prefixed_report_formatting_scratch(path):
        return "patchlet_prefixed_report_formatting_scratch"
    prefix_reasons = {
        "validation_report": "role_shaped_report_validation_output",
    }
    for prefix in SCRATCH_ROLE_PREFIXES:
        if stem == prefix or stem.startswith(prefix + "_"):
            return prefix_reasons.get(prefix, f"role_shaped_{prefix}_output")
    tokens = [token for token in stem.split("_") if token]
    subjects = SCRATCH_ROLE_SUBJECTS.intersection(tokens)
    actions = SCRATCH_ROLE_ACTIONS.intersection(tokens)
    if subjects and actions:
        subject = "probe" if "probe" in subjects else "report" if "report" in subjects else sorted(subjects)[0]
        action = "validate" if "validate" in actions else "validation" if actions.intersection({"valid", "validated", "validation"}) else sorted(actions)[0]
        if action == "validate" and "report" in subjects:
            return "role_shaped_report_validate_output"
        if action == "validate" and "probe" in subjects:
            return "role_shaped_probe_validate_output"
        return f"role_shaped_{subject}_{action}_output"
    if ("validation" in tokens or "validate" in tokens) and {"report", "result", "output", "check"}.intersection(tokens):
        action = "validate" if "validate" in tokens else "validation"
        return f"role_shaped_report_{action}_output"
    if stem.startswith(("report_", "report-", ".report_", ".report-", "probe_", "probe-", ".probe_", ".probe-")):
        return "role_shaped_worker_scratch_output"
    return None


def _is_executable(path: Path) -> bool:
    return bool(path.stat().st_mode & 0o111)


def _is_tracked_in_execution_root(path: Path, execution_root: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(execution_root), "ls-files", "--error-unmatch", path.name],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result.returncode == 0


def _content_type(path: Path) -> str:
    guessed = mimetypes.guess_type(path.name)[0]
    if guessed:
        return guessed
    if path.suffix.lower() in {".out", ".log", ".txt", ".tmp", ".scratch", ".md"}:
        return "text/plain"
    return "application/octet-stream"


def _scratch_rejection(path: Path, *, allowed_product_runtime_file: str | None, execution_root: Path, declared: set[str]) -> dict | None:
    if path.name == allowed_product_runtime_file:
        return {
            "original_path": path.name,
            "classification": "allowed_product_runtime_file",
            "reason": "allowed_product_runtime_file_not_quarantined",
        }
    if _is_tracked_in_execution_root(path, execution_root):
        return {
            "original_path": path.name,
            "classification": "tracked_file",
            "reason": "tracked_file_not_quarantined",
        }
    if path.stat().st_size > MAX_SCRATCH_ARTIFACT_BYTES:
        return {
            "original_path": path.name,
            "classification": "oversized_scratch_candidate",
            "reason": "scratch_candidate_exceeds_size_limit",
        }
    if _is_executable(path):
        return {
            "original_path": path.name,
            "classification": "executable_root_file",
            "reason": "executable_root_file_not_quarantined",
        }
    if path.suffix.lower() not in SCRATCH_TEXT_EXTENSIONS:
        return {
            "original_path": path.name,
            "classification": "unauthorized_product_runtime_candidate",
            "reason": "unknown_root_file_not_declared_and_not_role_shaped_scratch",
        }
    if path.name in declared:
        return None
    if path.name in EXECUTION_ROOT_SCRATCH_FILENAMES:
        return None
    if _scratch_role_reason(path):
        return None
    return {
        "original_path": path.name,
        "classification": "unauthorized_product_runtime_candidate",
        "reason": "unknown_root_file_not_declared_and_not_role_shaped_scratch",
    }


def _git_root_path_status(execution_root: Path) -> tuple[list[Path], dict]:
    all_root_files = sorted(
        [path for path in execution_root.iterdir() if path.is_file() and path.name != ".git"],
        key=lambda item: item.name,
    )
    result = subprocess.run(
        ["git", "-C", str(execution_root), "status", "--porcelain"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return all_root_files, {
            "mode": "directory_scan_no_git_status",
            "git_modified_paths": [],
            "git_untracked_paths": [path.name for path in all_root_files],
            "ignored_unchanged_peer_paths": [],
            "candidate_paths": [path.name for path in all_root_files],
        }

    modified: list[str] = []
    untracked: list[str] = []
    candidate_names: set[str] = set()
    deleted_or_missing: list[str] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        code = line[:2]
        raw_path = line[3:]
        if " -> " in raw_path:
            raw_path = raw_path.split(" -> ", 1)[1]
        rel = Path(raw_path)
        if len(rel.parts) != 1 or rel.name == ".git":
            continue
        if code == "??":
            untracked.append(rel.as_posix())
        else:
            modified.append(rel.as_posix())
        candidate_names.add(rel.name)
        if not (execution_root / rel).is_file():
            deleted_or_missing.append(rel.as_posix())

    root_files = [execution_root / name for name in sorted(candidate_names) if (execution_root / name).is_file()]
    ignored = [
        path.name
        for path in all_root_files
        if path.name not in candidate_names and _is_tracked_in_execution_root(path, execution_root)
    ]
    return root_files, {
        "mode": "git_status_actual_changes",
        "git_modified_paths": sorted(modified),
        "git_untracked_paths": sorted(untracked),
        "git_deleted_or_missing_paths": sorted(deleted_or_missing),
        "ignored_unchanged_peer_paths": sorted(ignored),
        "candidate_paths": sorted(path.name for path in root_files),
    }


def _quarantine_record(run_ctx: PatchletRunContext, path: Path, *, declared: set[str], reason: str) -> dict:
    data = path.read_bytes()
    quarantine_dir = run_ctx.quarantine_dir
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    dest = quarantine_dir / path.name
    shutil.move(str(path), dest)
    return {
        "original_path": path.name,
        "quarantine_path": str(dest.relative_to(run_ctx.target_root)),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "classification": "worker_scratch_artifact",
        "reason": reason,
        "declared_by_worker_report": path.name in declared,
        "declared_by_report": path.name in declared,
        "content_type": _content_type(dest),
    }


def _quarantine_execution_root_scratch_files(
    run_ctx: PatchletRunContext,
    *,
    report_path: Path | None,
    allowed_product_runtime_file: str | None,
) -> list[dict]:
    quarantined: list[dict] = []
    rejected: list[dict] = []
    classified: list[dict] = []
    declared = _declared_scratch_artifacts(report_path)
    root_files, candidate_source = _git_root_path_status(run_ctx.execution_root)
    for path in sorted(root_files, key=lambda item: item.name):
        rejection = _scratch_rejection(
            path,
            allowed_product_runtime_file=allowed_product_runtime_file,
            execution_root=run_ctx.execution_root,
            declared=declared,
        )
        if rejection:
            if rejection["classification"] not in {"allowed_product_runtime_file", "tracked_file"}:
                rejected.append(rejection)
            continue
        if path.name in declared:
            reason = "declared_worker_scratch_artifact"
        elif path.name in EXECUTION_ROOT_SCRATCH_FILENAMES:
            reason = "legacy_known_worker_scratch_artifact"
        else:
            reason = _scratch_role_reason(path) or "worker_root_scratch_artifact"
        record = _quarantine_record(run_ctx, path, declared=declared, reason=reason)
        quarantined.append(record)
        classified.append({
            "path": record["original_path"],
            "classification": record["classification"],
            "reason": record["reason"],
            "action": "quarantine",
            "quarantine_path": record["quarantine_path"],
        })
    gates_dir = run_ctx.run_dir / "gates"
    gates_dir.mkdir(parents=True, exist_ok=True)
    root_sweep_result = {
        "schema_version": "1.0",
        "kind": "root_scratch_sweep_result",
        "patchlet_id": run_ctx.run_dir.name.split("_attempt", 1)[0],
        "attempt_id": run_ctx.run_dir.name,
        "root_level_untracked_files": [
            path.name
            for path in root_files
            if path.name in set(candidate_source.get("git_untracked_paths", []))
        ],
        "candidate_source": candidate_source,
        "classified": classified,
        "rejected": rejected,
        "product_runtime_candidates": [allowed_product_runtime_file] if allowed_product_runtime_file else [],
        "recomputed_diff_required": bool(quarantined),
    }
    write_json(gates_dir / "root_scratch_sweep_result.json", root_sweep_result)
    if quarantined or rejected:
        result = {
            "schema_version": "1.0",
            "kind": "scratch_artifact_quarantine_result",
            "patchlet_id": run_ctx.run_dir.name.split("_attempt", 1)[0],
            "attempt_id": run_ctx.run_dir.name,
            "quarantined": quarantined,
            "rejected": rejected,
            "product_runtime_paths_still_rejected": [
                row["original_path"]
                for row in rejected
                if row.get("classification") == "unauthorized_product_runtime_candidate"
            ],
            "one_file_rule_preserved": True,
            "slice_boundary_preserved": True,
            "root_scratch_sweep_completed_before_diff_guard": True,
            "root_scratch_sweep_result_path": str((gates_dir / "root_scratch_sweep_result.json").relative_to(run_ctx.target_root)),
        }
        write_json(gates_dir / "scratch_artifact_quarantine_result.json", result)
    if quarantined:
        quarantine_dir = run_ctx.quarantine_dir
        write_json(quarantine_dir / "quarantined_scratch_files.json", {
            "schema_version": "1.0",
            "kind": "quarantined_scratch_files",
            "quarantined_scratch_files": quarantined,
        })
    return quarantined


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
    timed_out = isinstance(worker_error, WorkerTimeoutError) or command.get("timed_out") is True
    interrupted = isinstance(worker_error, WorkerInterruptedError) or command.get("interrupted") is True
    lifecycle_status = (
        "ATTEMPT_TIMED_OUT"
        if timed_out
        else "ATTEMPT_INTERRUPTED"
        if interrupted
        else "ATTEMPT_FAILED_WITH_EVIDENCE"
    )
    failure_category = (
        "orchestrator_subprocess_timeout"
        if timed_out
        else "attempt_interrupted"
        if interrupted
        else "worker_capsule_path_violation"
        if _is_capsule_path_violation_error(worker_error)
        else "worker_exception"
    )
    _upsert_attempt(ctx, attempt_id=run_dir.name, lifecycle_status=lifecycle_status, **{
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
            "interrupted": command.get("interrupted"),
            "timeout_seconds": command.get("timeout_seconds"),
            "started_at": command.get("started_at"),
            "ended_at": command.get("ended_at"),
            "duration_seconds": command.get("duration_seconds"),
            "termination_signal": command.get("termination_signal"),
            "selected_model": command.get("selected_model"),
            "selected_reasoning": command.get("selected_reasoning"),
            "retryable": False,
            "blind_retry_allowed": False,
            "failure_category": failure_category,
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
        "interrupted": command.get("interrupted"),
        "timeout_seconds": command.get("timeout_seconds"),
        "started_at": command.get("started_at"),
        "ended_at": command.get("ended_at"),
        "duration_seconds": command.get("duration_seconds"),
        "termination_signal": command.get("termination_signal"),
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


def _is_repair_patchlet(patchlet: dict) -> bool:
    return bool(patchlet.get("repair_plan_id") or patchlet.get("source_failure_ids"))


def _next_pending_patchlet(index: dict) -> dict | None:
    completed = {p["patchlet_id"] for p in index.get("patchlets", []) if p.get("status") in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}}
    blocked = {
        p["patchlet_id"]
        for p in index.get("patchlets", [])
        if p.get("status") in {"FAILED_WITH_EVIDENCE", "BLOCKED_WITH_EVIDENCE", "BLOCKED_BY_FAILED_DEPENDENCY"}
    }
    for patchlet in index.get("patchlets", []):
        if patchlet.get("status") != "PENDING":
            continue
        if blocked and not _is_repair_patchlet(patchlet):
            continue
        deps = patchlet.get("dependency_patchlet_ids", patchlet.get("depends_on", []))
        if all(dep in completed for dep in deps):
            return patchlet
    return None


def _write_dependency_block_result(
    ctx: TargetRepoContext,
    *,
    patchlet_id: str,
    blocked_dependency_patchlet_ids: list[str],
    reason: str,
) -> str:
    run_dir = ctx.paths.runs_dir / f"{patchlet_id}_blocked_by_failed_dependency" / "gates"
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "dependency_block_result.json"
    write_json(
        path,
        {
            "schema_version": "1.0",
            "kind": "dependency_block_result",
            "patchlet_id": patchlet_id,
            "status": "BLOCKED_BY_FAILED_DEPENDENCY",
            "blocked_dependency_patchlet_ids": blocked_dependency_patchlet_ids,
            "reason": reason,
            "worker_started": False,
        },
    )
    return _record_path_for_manifest(ctx, path) or str(path)


def _refresh_dependency_states(ctx: TargetRepoContext, index: dict) -> None:
    patchlets = index.get("patchlets", [])
    by_id = {patchlet["patchlet_id"]: patchlet for patchlet in patchlets}
    accepted = {
        pid
        for pid, patchlet in by_id.items()
        if patchlet.get("status") in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}
    }
    blocking = {
        pid
        for pid, patchlet in by_id.items()
        if patchlet.get("status") in {"FAILED_WITH_EVIDENCE", "BLOCKED_WITH_EVIDENCE", "BLOCKED_BY_FAILED_DEPENDENCY"}
    }
    changed = False
    blocked_patchlet_ids: list[str] = []
    for patchlet in patchlets:
        if patchlet.get("status") != "PENDING":
            continue
        deps = list(patchlet.get("dependency_patchlet_ids", patchlet.get("depends_on", [])))
        failed_deps = [dep for dep in deps if dep in blocking]
        if not failed_deps and blocking and not _is_repair_patchlet(patchlet):
            failed_deps = sorted(blocking)
        if failed_deps:
            patchlet["status"] = "BLOCKED_BY_FAILED_DEPENDENCY"
            patchlet["blocked_dependency_patchlet_ids"] = failed_deps
            patchlet["blocked_reason"] = "failed_dependency"
            changed = True
            blocked_patchlet_ids.append(patchlet["patchlet_id"])
            artifact_path = _write_dependency_block_result(
                ctx,
                patchlet_id=patchlet["patchlet_id"],
                blocked_dependency_patchlet_ids=failed_deps,
                reason="dependency patchlet failed before this patchlet was eligible to run",
            )
            append_operator_event(
                ctx.root,
                event_type="patchlet_blocked_by_failed_dependency",
                severity="error",
                stage="PATCHLETS_READY",
                summary=f"Patchlet {patchlet['patchlet_id']} blocked by failed dependency {', '.join(failed_deps)}.",
                artifact_paths=[".codex-orchestrator/patchlets/patchlet_index.json", artifact_path],
                patchlet_id=patchlet["patchlet_id"],
                details={"blocked_dependency_patchlet_ids": failed_deps},
            )
            continue
        waiting = [dep for dep in deps if dep not in accepted]
        if waiting:
            append_operator_event(
                ctx.root,
                event_type="patchlet_waiting_on_dependencies",
                severity="info",
                stage="PATCHLETS_READY",
                summary=f"Patchlet {patchlet['patchlet_id']} waiting on {', '.join(waiting)}.",
                artifact_paths=[".codex-orchestrator/patchlets/patchlet_index.json"],
                patchlet_id=patchlet["patchlet_id"],
                details={"waiting_dependency_patchlet_ids": waiting},
            )
        else:
            append_operator_event(
                ctx.root,
                event_type="patchlet_ready",
                severity="info",
                stage="PATCHLETS_READY",
                summary=f"Patchlet {patchlet['patchlet_id']} is ready.",
                artifact_paths=[".codex-orchestrator/patchlets/patchlet_index.json"],
                patchlet_id=patchlet["patchlet_id"],
            )
    if changed:
        _save_patchlet_index(ctx, index)
        if ctx.paths.state.exists():
            try:
                state = load_state(ctx)
                for patchlet_id in blocked_patchlet_ids:
                    if patchlet_id in state.pending_patchlets:
                        state.pending_patchlets.remove(patchlet_id)
                    if patchlet_id not in state.blocked_patchlets:
                        state.blocked_patchlets.append(patchlet_id)
                if not state.pending_patchlets:
                    transition(ctx, state, "FAILURE_CLASSIFICATION_REQUIRED", reason="failed dependency blocked downstream patchlets")
                else:
                    from codex_orchestrator.state import save_state

                    save_state(ctx, state)
            except Exception:
                pass
        append_operator_event(
            ctx.root,
            event_type="auto_loop_stopped_due_to_failed_dependency",
            severity="error",
            stage="PATCHLETS_READY",
            summary="Pending patchlets were blocked because a required predecessor failed.",
            artifact_paths=[".codex-orchestrator/patchlets/patchlet_index.json"],
            details={"failed_or_blocking_patchlet_ids": sorted(blocking)},
        )


def _record_failure(
    ctx: TargetRepoContext,
    *,
    source_id: str,
    observed_failure: str,
    changed_paths: list[str],
    failure_signature: str | None = None,
    report_validation_errors: list[dict] | None = None,
    report_ingestion_result_path: str | None = None,
    report_validation_errors_path: str | None = None,
) -> str:
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
    if failure_signature:
        record["failure_signature"] = failure_signature
    if report_validation_errors is not None:
        record["report_validation_errors"] = report_validation_errors
    if report_ingestion_result_path:
        record["report_ingestion_result_path"] = report_ingestion_result_path
    if report_validation_errors_path:
        record["report_validation_errors_path"] = report_validation_errors_path
    if failure_signature == "semantic_goal_unsatisfied":
        record["diagnosis"] = {
            "primary_category": "semantic_goal_unsatisfied",
            "confidence": "high",
            "summary": observed_failure,
        }
    write_json(ctx.paths.failures_dir / f"{failure_id}.json", record)
    (ctx.paths.failures_dir / f"{failure_id}.md").write_text(f"# {failure_id}\n\n{observed_failure}\n", encoding="utf-8")
    record_failure_signature(
        ctx.root,
        failure_record=record,
        max_repeated_failure_signature=int(os.environ.get("CXOR_MAX_REPEATED_FAILURE_SIGNATURE", "3")),
        mode=os.environ.get("CXOR_LOOP_GOVERNOR_MODE", "warning"),
    )
    append_operator_event(
        ctx.root,
        event_type="failure_record_created",
        severity="error",
        stage="FAILURE_CLASSIFICATION_REQUIRED",
        summary=f"Failure {failure_id} recorded for {source_id}.",
        artifact_paths=[
            _record_path_for_manifest(ctx, ctx.paths.failures_dir / f"{failure_id}.json"),
            _record_path_for_manifest(ctx, ctx.paths.failures_dir / f"{failure_id}.md"),
        ],
        patchlet_id=source_id if source_id.startswith("P") else None,
        failure_id=failure_id,
        next_action="Classifying recorded failure.",
        details={
            "observed_failure": observed_failure,
            "changed_paths": changed_paths,
            "failure_signature": failure_signature,
            "report_validation_errors_path": report_validation_errors_path,
            "report_ingestion_result_path": report_ingestion_result_path,
        },
    )
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


def _append_patchlet_event(
    ctx: TargetRepoContext,
    event_type: str,
    *,
    patchlet_id: str,
    attempt_id: str | None = None,
    severity: str = "info",
    summary: str,
    artifact_paths: list[str | None] | None = None,
    prompt_path: str | None = None,
    next_action: str | None = None,
    details: dict | None = None,
) -> dict:
    return append_operator_event(
        ctx.root,
        event_type=event_type,
        severity=severity,
        stage="PATCHLET_EXECUTION_IN_PROGRESS",
        summary=summary,
        artifact_paths=[path for path in artifact_paths or [] if path],
        patchlet_id=patchlet_id,
        attempt_id=attempt_id,
        prompt_path=prompt_path,
        next_action=next_action,
        details=details,
    )


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


def _write_goal_satisfaction_gate(
    ctx: TargetRepoContext,
    *,
    patchlet: dict,
    run_ctx: PatchletRunContext,
    report_status: str,
    report: dict | None,
) -> dict:
    pid = patchlet["patchlet_id"]
    attempt_id = run_ctx.run_dir.name
    spec = load_semantic_goal_spec(ctx.root)
    gate_path = run_ctx.run_dir / "gates" / "goal_satisfaction_gate_result.json"
    if not spec:
        result = {
            "schema_version": "1.0",
            "kind": "goal_satisfaction_gate_result",
            "accepted": True,
            "workflow_id": None,
            "run_id": None,
            "patchlet_id": pid,
            "attempt_id": attempt_id,
            "semantic_goal_spec_path": None,
            "semantic_goal_check_result_path": None,
            "semantic_mode": "missing",
            "overall_status": "UNSUPPORTED",
            "failed_criteria": [],
            "reasons": ["No semantic goal spec exists."],
            "report_status": report_status,
            "report_claimed_semantic_pass": False,
        }
        write_json(gate_path, result)
        return result
    criteria = required_structured_criteria(spec)
    if not criteria:
        result = {
            "schema_version": "1.0",
            "kind": "goal_satisfaction_gate_result",
            "accepted": True,
            "workflow_id": spec.get("workflow_id"),
            "run_id": spec.get("run_id"),
            "patchlet_id": pid,
            "attempt_id": attempt_id,
            "semantic_goal_spec_path": ".codex-orchestrator/semantic_goal_spec.json",
            "semantic_goal_check_result_path": None,
            "semantic_mode": spec.get("semantic_mode", "unsupported"),
            "overall_status": "UNSUPPORTED",
            "failed_criteria": [],
            "reasons": spec.get("unsupported_reasons", ["Semantic goal verification is unsupported."]),
            "report_status": report_status,
            "report_claimed_semantic_pass": False,
        }
        write_json(gate_path, result)
        append_operator_event(
            ctx.root,
            event_type="semantic_goal_unverified",
            severity="warning",
            stage="PATCHLET_EXECUTION_IN_PROGRESS",
            summary="Semantic goal verification is unsupported for this workflow.",
            artifact_paths=[_record_path_for_manifest(ctx, gate_path)],
            patchlet_id=pid,
            attempt_id=attempt_id,
            details={"semantic_mode": result["semantic_mode"]},
        )
        return result
    append_operator_event(
        ctx.root,
        event_type="goal_satisfaction_gate_started",
        severity="info",
        stage="PATCHLET_EXECUTION_IN_PROGRESS",
        summary=f"Goal satisfaction gate started for {pid}.",
        artifact_paths=[".codex-orchestrator/semantic_goal_spec.json"],
        patchlet_id=pid,
        attempt_id=attempt_id,
    )
    check = run_semantic_goal_checks(
        repo_root=ctx.root,
        execution_root=run_ctx.execution_root,
        integration_ref=None,
        semantic_goal_spec=spec,
        patchlet_id=pid,
        attempt_id=attempt_id,
    )
    failed = [row["criterion_id"] for row in check.get("criteria", []) if row.get("passed") is not True]
    reasons = [
        f"{row['criterion_id']} expected app.main() == {row.get('expected_value')!r} but observed {row.get('actual_value')!r}."
        for row in check.get("criteria", [])
        if row.get("passed") is not True
    ]
    accepted = check.get("overall_status") == "PASSED" and not failed
    report_claimed = all(item.get("passed") is True for item in (report or {}).get("semantic_goal_results", []))
    result = {
        "schema_version": "1.0",
        "kind": "goal_satisfaction_gate_result",
        "accepted": accepted,
        "workflow_id": spec.get("workflow_id"),
        "run_id": spec.get("run_id"),
        "patchlet_id": pid,
        "attempt_id": attempt_id,
        "semantic_goal_spec_path": ".codex-orchestrator/semantic_goal_spec.json",
        "semantic_goal_check_result_path": ".codex-orchestrator/semantic_goal_checks/semantic_goal_check_result.json",
        "semantic_mode": "structured",
        "overall_status": check.get("overall_status"),
        "failed_criteria": failed,
        "reasons": reasons,
        "report_status": report_status,
        "report_claimed_semantic_pass": report_claimed,
    }
    write_json(gate_path, result)
    append_operator_event(
        ctx.root,
        event_type="goal_satisfaction_gate_passed" if accepted else "goal_satisfaction_gate_failed",
        severity="success" if accepted else "error",
        stage="PATCHLET_EXECUTION_IN_PROGRESS",
        summary=(
            f"goal satisfaction gate passed for {pid}."
            if accepted
            else f"goal satisfaction gate failed for {pid}; patchlet not accepted."
        ),
        artifact_paths=[
            _record_path_for_manifest(ctx, gate_path),
            ".codex-orchestrator/semantic_goal_checks/semantic_goal_check_result.json",
        ],
        patchlet_id=pid,
        attempt_id=attempt_id,
        details={
            "failed_criteria": failed,
            "failure_signature": None if accepted else "semantic_goal_unsatisfied",
            "semantic_goal_check_result_path": ".codex-orchestrator/semantic_goal_checks/semantic_goal_check_result.json",
        },
    )
    return result


def run_next_patchlet(ctx: TargetRepoContext, *, worker_mode: str = "mock", use_worktree: bool = False) -> PatchletExecutionResult:
    index = _load_patchlet_index(ctx)
    _refresh_dependency_states(ctx, index)
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
        worker_scratch_contract={
            "attempt_root": _record_path_for_manifest(ctx, initial_run_dir),
            "attempt_scratch_dir": _record_path_for_manifest(ctx, initial_run_dir / "worker_scratch"),
            "quarantine_dir": _record_path_for_manifest(ctx, initial_run_dir / "quarantined_scratch"),
            "required_report_path": _record_path_for_manifest(ctx, ctx.paths.reports_dir / f"{pid}.json"),
            "required_probe_artifact_root": _record_path_for_manifest(ctx, ctx.paths.probe_dir / pid),
        },
    )
    _append_patchlet_event(
        ctx,
        "patchlet_started",
        patchlet_id=pid,
        attempt_id=run_id,
        summary=(
            f"Started patchlet {pid}: {patchlet.get('allowed_product_runtime_file')} — "
            f"{patchlet.get('title') or patchlet.get('summary') or 'worker task'}"
        ),
        artifact_paths=[_record_path_for_manifest(ctx, initial_run_dir)],
        next_action="Preparing worker prompt.",
    )
    pre_hygiene = run_target_hygiene_gate(
        target_repo_root=ctx.root,
        workflow_dir=ctx.paths.workflow_dir,
        probe_dir=ctx.paths.probe_dir,
        run_dir=initial_run_dir,
        patchlet_id=pid,
        attempt_id=run_id,
        allowed_product_runtime_file=patchlet.get("allowed_product_runtime_file"),
        allowed_dirty_paths=_allowed_prompt_dirty_paths(ctx),
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
    run_ctx.attempt_scratch_dir.mkdir(parents=True, exist_ok=True)
    run_ctx.quarantine_dir.mkdir(parents=True, exist_ok=True)
    run_ctx.required_report_path(pid).parent.mkdir(parents=True, exist_ok=True)
    run_ctx.required_probe_artifact_root(pid).mkdir(parents=True, exist_ok=True)
    ensure_worker_capsule(ctx, worker_capsule)
    ensure_worker_memory(ctx, worker_capsule, run_ctx, patchlet, worker_mode=worker_mode)
    ensure_worker_stage_templates(worker_capsule, run_ctx, patchlet)
    worker_capsule_manifest = _record_path_for_manifest(ctx, worker_capsule.manifest_path)
    wrapper_gate_result_path = _record_path_for_manifest(ctx, worker_capsule.gates_dir / "wrapper_gate_result.json")
    prompt_path = _record_path_for_manifest(ctx, run_dir / "codex_task_prompt.md")
    attempt_prompt_path = run_dir / "codex_task_prompt.md"
    if not attempt_prompt_path.exists():
        report_contract = worker_capsule.worker_memory_dir / "REPORT_SCHEMA_CONTRACT.md"
        final_contract = worker_capsule.worker_memory_dir / "FINAL_REPORT_CONTRACT.md"
        work_slice_contract = worker_capsule.worker_memory_dir / "WORK_SLICE_CONTRACT.md"
        forbidden_files = patchlet.get("prompt_scope", {}).get("forbidden_edit_files", [])
        forbidden_text = "\n".join(f"- `{path}`" for path in forbidden_files) or "- any product/runtime file other than the single allowed file"
        boundary_text = slice_boundary_contract_text(patchlet)
        attempt_prompt_path.write_text(
            f"# Worker Prompt Pending\n\nPatchlet: {pid}\nAttempt: {run_id}\nSubprompt: {patchlet['subprompt_path']}\n\n"
            "This patchlet is a small bounded work unit.\n\n"
            f"Work slice ID: `{patchlet.get('work_slice_id') or 'legacy-invariant-slice'}`\n\n"
            f"Allowed product/runtime file: `{patchlet.get('allowed_product_runtime_file')}`\n\n"
            f"Allowed edit path: `$CXOR_EXECUTION_ROOT/{patchlet.get('allowed_product_runtime_file')}`\n\n"
            "Forbidden product/runtime edit paths:\n"
            f"{forbidden_text}\n\n"
            f"Time budget seconds: `{patchlet.get('time_budget_seconds')}`\n\n"
            f"Soft deadline seconds: `{soft_deadline_seconds(int(patchlet.get('time_budget_seconds') or 1))}`\n\n"
            f"Proof obligations: `{', '.join(patchlet.get('proof_obligation_ids', [])) or 'none'}`\n\n"
            f"Goal items: `{', '.join(patchlet.get('goal_item_ids', [])) or 'none'}`\n\n"
            "## Slice-level allowed-change boundary\n\n"
            f"{boundary_text}\n"
            f"Dependency patchlets: `{', '.join(patchlet.get('dependency_patchlet_ids', patchlet.get('depends_on', []))) or 'none'}`\n\n"
            "Do not attempt to solve unrelated work slices.\n\n"
            "Do not edit any product/runtime file except the single allowed file.\n\n"
            "Do not create root-level scratch/check files such as `.report_check.json`; use `/tmp` for scratch checks.\n\n"
            "Do not compact memory by summarizing broad unrelated context.\n\n"
            "Finish within the patchlet time budget.\n\n"
            "If blocked, write BLOCKED_WITH_EVIDENCE with the specific missing dependency or proof obstacle.\n\n"
            f"{_semantic_worker_prompt_section(patchlet)}"
            "## Work slice contract\n\n"
            f"{work_slice_contract.read_text(encoding='utf-8') if work_slice_contract.exists() else ''}\n\n"
            "## Report schema contract\n\n"
            f"{report_contract.read_text(encoding='utf-8') if report_contract.exists() else ''}\n\n"
            "## Final report contract\n\n"
            f"{final_contract.read_text(encoding='utf-8') if final_contract.exists() else ''}\n",
            encoding="utf-8",
        )
    prompt_entry = upsert_prompt_index_entry(ctx.root, {
        "kind": "repair_worker_prompt" if patchlet.get("is_repair_patchlet") else "patchlet_worker_prompt",
        "stage": "PATCHLET_EXECUTION_IN_PROGRESS",
        "patchlet_id": pid,
        "attempt_id": run_id,
        "repair_plan_id": patchlet.get("repair_plan_id"),
        "failure_ids": patchlet.get("source_failure_ids", []),
        "title": f"{patchlet.get('allowed_product_runtime_file')} — {pid}",
        "summary": f"Worker prompt for patchlet {pid}.",
        "path": attempt_prompt_path,
        "subprompt_path": patchlet.get("subprompt_path"),
        "model": None,
        "reasoning": None,
        "contracts": [
            "TASK_CONTRACT.md",
            "WORK_SLICE_CONTRACT.md",
            "REPORT_SCHEMA_CONTRACT.md",
            "FINAL_REPORT_CONTRACT.md",
            "RUNTIME_SIDE_EFFECT_CONTRACT.md",
        ],
        "artifact_paths": [
            prompt_path,
            _record_path_for_manifest(ctx, worker_capsule.worker_memory_dir / "WORK_SLICE_CONTRACT.md"),
        ],
    })
    _append_patchlet_event(
        ctx,
        "patchlet_prompt_written",
        patchlet_id=pid,
        attempt_id=run_id,
        summary=f"Prompt saved for {run_id}.",
        artifact_paths=[prompt_path],
        prompt_path=prompt_path,
        details={"prompt_id": prompt_entry.get("prompt_id")},
        next_action="Starting worker.",
    )
    _append_patchlet_event(
        ctx,
        "worker_scratch_contract_written",
        patchlet_id=pid,
        attempt_id=run_id,
        summary=f"Worker scratch contract written for {run_id}.",
        artifact_paths=[
            _record_path_for_manifest(ctx, run_ctx.attempt_scratch_dir),
            _record_path_for_manifest(ctx, run_ctx.quarantine_dir),
            _record_path_for_manifest(ctx, worker_capsule.worker_memory_dir / "TASK_CONTRACT.md"),
        ],
        details={
            "attempt_scratch_dir": _record_path_for_manifest(ctx, run_ctx.attempt_scratch_dir),
            "quarantine_dir": _record_path_for_manifest(ctx, run_ctx.quarantine_dir),
            "required_report_path": _record_path_for_manifest(ctx, run_ctx.required_report_path(pid)),
            "required_probe_artifact_root": _record_path_for_manifest(ctx, run_ctx.required_probe_artifact_root(pid)),
        },
    )
    if patchlet.get("slice_change_boundary"):
        _append_patchlet_event(
            ctx,
            "slice_boundary_prompted",
            patchlet_id=pid,
            attempt_id=run_id,
            summary=f"Slice boundary prompted for {pid}.",
            artifact_paths=[prompt_path, _record_path_for_manifest(ctx, worker_capsule.worker_memory_dir / "WORK_SLICE_CONTRACT.md")],
            details={
                "boundary_type": patchlet["slice_change_boundary"].get("boundary_type"),
                "allowed_change_count": len(patchlet["slice_change_boundary"].get("allowed_changes", [])),
                "forbidden_future_change_count": len(patchlet["slice_change_boundary"].get("forbidden_changes", [])),
            },
        )
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
        _append_patchlet_event(
            ctx,
            "patchlet_worker_started",
            patchlet_id=pid,
            attempt_id=run_id,
            summary=f"Worker started for {run_id} mode={worker_mode}.",
            artifact_paths=[
                _record_path_for_manifest(ctx, run_dir / "command.json"),
                _record_path_for_manifest(ctx, run_dir / "progress.jsonl"),
                _record_path_for_manifest(ctx, run_dir / "output.jsonl"),
            ],
            next_action="Waiting for worker to finish.",
            details={"worker_mode": worker_mode, "use_worktree": use_worktree},
        )
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
        _append_patchlet_event(
            ctx,
            "patchlet_worker_exited",
            patchlet_id=pid,
            attempt_id=run_id,
            severity="success" if worker_result.exit_code == 0 else "error",
            summary=f"Worker exited for {run_id} code={worker_result.exit_code}.",
            artifact_paths=[
                _record_path_for_manifest(ctx, run_dir / "stdout.txt"),
                _record_path_for_manifest(ctx, run_dir / "stderr.txt"),
                _record_path_for_manifest(ctx, run_dir / "output.jsonl"),
            ],
            next_action="Validating worker report.",
            details={"exit_code": worker_result.exit_code},
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
        quarantined_scratch_files = _quarantine_execution_root_scratch_files(
            run_ctx,
            report_path=worker_result.report_path,
            allowed_product_runtime_file=patchlet.get("allowed_product_runtime_file"),
        )
        quarantine_result_path = run_dir / "gates" / "scratch_artifact_quarantine_result.json"
        root_sweep_result_path = run_dir / "gates" / "root_scratch_sweep_result.json"
        if root_sweep_result_path.exists():
            _append_patchlet_event(
                ctx,
                "root_scratch_sweep_completed",
                patchlet_id=pid,
                attempt_id=run_id,
                summary=f"Root scratch sweep completed for {run_id}.",
                artifact_paths=[_record_path_for_manifest(ctx, root_sweep_result_path)],
                details=read_json(root_sweep_result_path),
            )
        if quarantine_result_path.exists():
            quarantine_result = read_json(quarantine_result_path)
            for scratch in quarantine_result.get("rejected", []):
                _append_patchlet_event(
                    ctx,
                    "root_scratch_artifact_rejected",
                    patchlet_id=pid,
                    attempt_id=run_id,
                    severity="error",
                    summary=f"Rejected root-level scratch candidate {scratch.get('original_path')}.",
                    artifact_paths=[_record_path_for_manifest(ctx, quarantine_result_path)],
                    details=scratch,
                )
        if quarantined_scratch_files:
            append_worker_event(
                ctx,
                worker_capsule,
                run_ctx,
                event="after_execution_root_scratch_quarantine",
                worker_mode=worker_mode,
                details={"quarantined_scratch_files": quarantined_scratch_files},
            )
            _append_patchlet_event(
                ctx,
                "execution_root_scratch_quarantined",
                patchlet_id=pid,
                attempt_id=run_id,
                summary=f"Quarantined execution-root scratch files for {pid}.",
                artifact_paths=[
                    _record_path_for_manifest(ctx, quarantine_result_path),
                    _record_path_for_manifest(ctx, run_dir / "quarantined_scratch" / "quarantined_scratch_files.json"),
                ],
                details={"quarantined_scratch_files": quarantined_scratch_files},
            )
            for scratch in quarantined_scratch_files:
                _append_patchlet_event(
                    ctx,
                    "root_scratch_artifact_quarantined",
                    patchlet_id=pid,
                    attempt_id=run_id,
                    summary=f"Quarantined worker scratch artifact {scratch.get('original_path')}.",
                    artifact_paths=[_record_path_for_manifest(ctx, quarantine_result_path)],
                    details=scratch,
                )
        after = snapshot_status(run_ctx.execution_root)
        changed_paths = changed_between(before, after)
        diff_text = git_diff(run_ctx.execution_root)
        if quarantined_scratch_files:
            _append_patchlet_event(
                ctx,
                "product_diff_recomputed_after_scratch_sweep",
                patchlet_id=pid,
                attempt_id=run_id,
                summary=f"Product diff rechecked after scratch quarantine for {pid}.",
                artifact_paths=[_record_path_for_manifest(ctx, run_dir / "gates" / "scratch_artifact_quarantine_result.json")],
                details={"changed_paths_after_quarantine": changed_paths},
            )
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
        diff_result = validate_changed_paths(changed_paths, patchlet, diff_text=diff_text)
        _append_patchlet_event(
            ctx,
            "slice_boundary_diff_accepted" if diff_result.allowed else "slice_boundary_diff_rejected",
            patchlet_id=pid,
            attempt_id=run_id,
            severity="info" if diff_result.allowed else "error",
            summary=(
                f"Diff allowed for {pid}."
                if diff_result.allowed
                else f"Diff rejected for {pid}: {', '.join(diff_result.unauthorized_paths)}."
            ),
            artifact_paths=[_record_path_for_manifest(ctx, diff_path)],
            details={
                "changed_paths": changed_paths,
                "path_classifications": diff_result.path_classifications or {},
                "slice_boundary_violations": diff_result.slice_boundary_violations or [],
            },
        )
        artifact_dirs = [
            path
            for path, classification in (diff_result.path_classifications or {}).items()
            if classification == "ARTIFACT_ALLOWED" and (ctx.root / path).is_dir()
        ]
        if artifact_dirs:
            _append_patchlet_event(
                ctx,
                "artifact_directory_diff_allowed",
                patchlet_id=pid,
                attempt_id=run_id,
                summary=f"Allowed artifact directory diff paths for {pid}.",
                artifact_paths=artifact_dirs,
                details={"artifact_directories": artifact_dirs},
            )
    except (WorkerExecutionError, WorkerPreconditionError) as exc:
        worker_error = exc
        _append_patchlet_event(
            ctx,
            "patchlet_worker_exited",
            patchlet_id=pid,
            attempt_id=run_id,
            severity="error",
            summary=f"Worker failed for {run_id}: {type(exc).__name__}.",
            artifact_paths=[
                _record_path_for_manifest(ctx, run_dir / "stdout.txt"),
                _record_path_for_manifest(ctx, run_dir / "stderr.txt"),
                _record_path_for_manifest(ctx, run_dir / "output.jsonl"),
            ],
            next_action="Recording worker failure evidence.",
            details={"error_type": type(exc).__name__, "error_message": str(exc)},
        )
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
        command = _read_command_from_run_dir(run_dir)
        timed_out = isinstance(worker_error, WorkerTimeoutError) or command.get("timed_out") is True
        interrupted = isinstance(worker_error, WorkerInterruptedError) or command.get("interrupted") is True
        failure_signature = (
            "orchestrator_subprocess_timeout"
            if timed_out
            else "attempt_interrupted"
            if interrupted
            else "worker_execution_failed"
        )
        event_type = "patchlet_timed_out" if timed_out else "patchlet_interrupted" if interrupted else "patchlet_failed_with_evidence"
        summary = (
            f"Patchlet {pid} timed out after {command.get('timeout_seconds')} seconds."
            if timed_out
            else f"Patchlet {pid} interrupted with evidence preserved."
            if interrupted
            else f"Patchlet {pid} failed with evidence; worker failed before acceptance."
        )
        failure_id = _record_failure(
            ctx,
            source_id=pid,
            observed_failure=str(worker_error),
            changed_paths=changed_paths,
            failure_signature=failure_signature,
        )
        state = load_state(ctx)
        if pid not in state.failed_patchlets:
            state.failed_patchlets.append(pid)
        if pid in state.pending_patchlets:
            state.pending_patchlets.remove(pid)
        transition(ctx, state, "FAILURE_CLASSIFICATION_REQUIRED", reason=f"{pid} {failure_signature} {failure_id}")
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
        _append_patchlet_event(
            ctx,
            event_type,
            patchlet_id=pid,
            attempt_id=run_id,
            severity="error",
            summary=summary,
            artifact_paths=[
                wrapper_gate_result_path,
                _record_path_for_manifest(ctx, ctx.paths.failures_dir / f"{failure_id}.json"),
            ],
            next_action="Preserving worker failure evidence.",
            details={
                "error_type": type(worker_error).__name__,
                "error_message": str(worker_error),
                "failure_signature": failure_signature,
            },
        )
        raise worker_error

    assert worker_result is not None
    assert diff_result is not None
    failure_id: str | None = None
    report_valid = False
    report_status = "FAILED_WITH_EVIDENCE"
    report_error: str | None = None
    report_ingestion_result: dict | None = None
    report_validation_errors: list[dict] = []
    report_failure_signature: str | None = None
    report: dict | None = None
    integration_checkpoint_sha: str | None = None
    goal_gate_result: dict | None = None
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
                report_ingestion_result = ingest_patchlet_report(
                    ctx,
                    patchlet=patchlet,
                    attempt_id=run_id,
                    report_path=worker_result.report_path,
                )
                canonical_report_path = ctx.root / report_ingestion_result["canonical_report_path"] if report_ingestion_result.get("canonical_report_path") else worker_result.report_path
                report_validation_errors = read_json(ctx.root / report_ingestion_result["validation"]["errors_path"]).get("errors", [])
                report_failure_signature = report_ingestion_result.get("normalized_failure_signature")
                if not report_ingestion_result["accepted"]:
                    message = "; ".join(error.get("message", "") for error in report_validation_errors) or report_ingestion_result.get("operator_summary", "report ingestion failed")
                    raise ReportValidationError(message, report_validation_errors)
                worker_result = type(worker_result)(
                    exit_code=worker_result.exit_code,
                    stdout=worker_result.stdout,
                    stderr=worker_result.stderr,
                    report_path=canonical_report_path,
                )
                report = validate_patchlet_report_file(canonical_report_path, patchlet)
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
                _append_patchlet_event(
                    ctx,
                    "patchlet_report_validated",
                    patchlet_id=pid,
                    attempt_id=run_id,
                    severity="success",
                    summary=f"Report validation passed for {pid}: {report_status}.",
                    artifact_paths=[
                        _record_path_for_manifest(ctx, worker_result.report_path),
                        report_ingestion_result["raw_report_path"],
                        _record_path_for_manifest(ctx, ctx.paths.runs_dir / run_id / "gates" / "report_ingestion_result.json"),
                    ],
                    next_action="Evaluating wrapper gate.",
                    details={
                        "report_valid": True,
                        "report_status": report_status,
                        "report_ingestion_result_path": _record_path_for_manifest(ctx, ctx.paths.runs_dir / run_id / "gates" / "report_ingestion_result.json"),
                        "report_validation_errors_path": report_ingestion_result["validation"]["errors_path"],
                        "normalization_applied": report_ingestion_result["normalization_applied"],
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
                report_validation_errors = getattr(exc, "errors", report_validation_errors)
                report_failure_signature = (
                    report_failure_signature
                    or (report_validation_errors[0].get("normalized_signature") if report_validation_errors else None)
                )
                ingestion_result_path = _record_path_for_manifest(ctx, ctx.paths.runs_dir / run_id / "gates" / "report_ingestion_result.json")
                validation_errors_path = _record_path_for_manifest(ctx, ctx.paths.runs_dir / run_id / "gates" / "report_validation_errors.json")
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
                        "failure_signature": report_failure_signature,
                        "report_validation_errors_path": validation_errors_path,
                        "report_ingestion_result_path": ingestion_result_path,
                    },
                )
                _append_patchlet_event(
                    ctx,
                    "patchlet_report_validated",
                    patchlet_id=pid,
                    attempt_id=run_id,
                    severity="error",
                    summary=f"Report validation failed for {pid}: {report_error}.",
                    artifact_paths=[
                        _record_path_for_manifest(ctx, worker_result.report_path) if worker_result.report_path else None,
                        ingestion_result_path,
                        validation_errors_path,
                    ],
                    next_action="Recording failure evidence.",
                    details={
                        "report_valid": False,
                        "report_error": report_error,
                        "failure_signature": report_failure_signature,
                        "report_validation_errors_path": validation_errors_path,
                        "report_ingestion_result_path": ingestion_result_path,
                        "field": report_validation_errors[0].get("field") if report_validation_errors else None,
                        "expected_type": report_validation_errors[0].get("expected_type") if report_validation_errors else None,
                        "actual_type": report_validation_errors[0].get("actual_type") if report_validation_errors else None,
                    },
                )
                _upsert_attempt(
                    ctx,
                    attempt_id=run_id,
                    lifecycle_status="REPORT_VALIDATED",
                    report_valid=False,
                    report_error=report_error,
                    report_validation={
                        "valid": False,
                        "reason": report_error,
                        "failure_signature": report_failure_signature,
                        "errors_path": validation_errors_path,
                    },
                    status="FAILED_WITH_EVIDENCE",
                )
                failure_id = _record_failure(
                    ctx,
                    source_id=pid,
                    observed_failure=f"Invalid or missing patchlet report: {exc}",
                    changed_paths=changed_paths,
                    failure_signature=report_failure_signature,
                    report_validation_errors=report_validation_errors,
                    report_ingestion_result_path=ingestion_result_path,
                    report_validation_errors_path=validation_errors_path,
                )
                report_status = "FAILED_WITH_EVIDENCE"

            if report_valid and report_status not in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"} and not use_worktree:
                _cleanup_direct_worker_changes(ctx, changed_paths)
    finally:
        pass

    if report_valid and report_status in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"} and diff_result.allowed:
        goal_gate_result = _write_goal_satisfaction_gate(
            ctx,
            patchlet=patchlet,
            run_ctx=run_ctx,
            report_status=report_status,
            report=report,
        )
        _upsert_attempt(
            ctx,
            attempt_id=run_id,
            lifecycle_status="GOAL_SATISFACTION_GATE_EVALUATED",
            goal_satisfaction_gate_result=_record_path_for_manifest(ctx, run_dir / "gates" / "goal_satisfaction_gate_result.json"),
            goal_satisfaction_accepted=goal_gate_result.get("accepted"),
        )
        proof_obligations_path = ctx.paths.workflow_dir / "proof_obligations.json"
        probe_plan_path = ctx.paths.workflow_dir / "probe_plan.json"
        if goal_gate_result.get("accepted") and proof_obligations_path.exists() and probe_plan_path.exists():
            proof_obligations = read_json(proof_obligations_path)
            probe_plan = read_json(probe_plan_path)
            append_operator_event(
                ctx.root,
                event_type="independent_probe_rerun_started",
                severity="info",
                stage="PATCHLET_EXECUTION_IN_PROGRESS",
                summary=f"Independent probe rerun started for {pid}.",
                artifact_paths=[".codex-orchestrator/probe_plan.json"],
                patchlet_id=pid,
                attempt_id=run_id,
            )
            independent_result = run_independent_probe_rerun_gate(
                repo_root=ctx.root,
                workflow_root=ctx.paths.workflow_dir,
                attempt_id=run_id,
                patchlet_id=pid,
                proof_obligations=proof_obligations,
                probe_plan=probe_plan,
                integration_ref=None,
                execution_root=run_ctx.execution_root,
                patchlet=patchlet,
                scope="patchlet",
            )
            semantic_normalization_path = run_dir / "gates" / "semantic_goal_results_normalization_result.json"
            if semantic_normalization_path.exists():
                semantic_canonicalization_result = canonicalize_semantic_goal_results_after_probe(
                    normalization_result=read_json(semantic_normalization_path),
                    independent_probe_rerun_result=independent_result,
                    proof_obligations=proof_obligations,
                    probe_plan=probe_plan,
                )
                semantic_canonicalization_path = run_dir / "gates" / "semantic_goal_results_canonicalization_result.json"
                write_json(semantic_canonicalization_path, semantic_canonicalization_result)
                append_operator_event(
                    ctx.root,
                    event_type="semantic_goal_results_canonicalized_after_probe",
                    severity="success" if all(row.get("passed") is True for row in semantic_canonicalization_result.get("canonical_results", [])) else "error",
                    stage="PATCHLET_EXECUTION_IN_PROGRESS",
                    summary=f"independent proof canonicalized semantic result for {pid}.",
                    artifact_paths=[_record_path_for_manifest(ctx, semantic_canonicalization_path)],
                    patchlet_id=pid,
                    attempt_id=run_id,
                    details={
                        "canonical_result_count": len(semantic_canonicalization_result.get("canonical_results", [])),
                        "proof_source": "independent_probe_rerun",
                    },
                )
            append_operator_event(
                ctx.root,
                event_type="patchlet_scoped_probe_selected",
                severity="info",
                stage="PATCHLET_EXECUTION_IN_PROGRESS",
                summary=f"Selected {len(independent_result.get('selected_obligation_ids', []))} current obligations for {pid}.",
                artifact_paths=[_record_path_for_manifest(ctx, run_dir / "gates" / "independent_probe_rerun_result.json")],
                patchlet_id=pid,
                attempt_id=run_id,
                details={
                    "selected_obligation_ids": independent_result.get("selected_obligation_ids", []),
                    "future_obligation_ids": independent_result.get("not_selected_future_obligation_ids", []),
                },
            )
            if independent_result.get("not_selected_future_obligation_ids"):
                append_operator_event(
                    ctx.root,
                    event_type="future_obligations_deferred",
                    severity="info",
                    stage="PATCHLET_EXECUTION_IN_PROGRESS",
                    summary=f"Deferred future obligations for {pid}.",
                    artifact_paths=[_record_path_for_manifest(ctx, run_dir / "gates" / "independent_probe_rerun_result.json")],
                    patchlet_id=pid,
                    attempt_id=run_id,
                    details={"future_obligation_ids": independent_result.get("not_selected_future_obligation_ids", [])},
                )
            coverage_result = evaluate_goal_coverage_gate(
                proof_obligations=proof_obligations,
                probe_plan=probe_plan,
                independent_probe_rerun_result=independent_result,
                patchlet_id=pid,
                attempt_id=run_id,
            )
            coverage_path = run_dir / "gates" / "goal_coverage_gate_result.json"
            write_json(coverage_path, coverage_result)
            _upsert_attempt(
                ctx,
                attempt_id=run_id,
                lifecycle_status="GOAL_COVERAGE_GATE_EVALUATED",
                independent_probe_rerun_result=_record_path_for_manifest(ctx, run_dir / "gates" / "independent_probe_rerun_result.json"),
                goal_coverage_gate_result=_record_path_for_manifest(ctx, coverage_path),
                goal_coverage_accepted=coverage_result.get("accepted"),
            )
            append_operator_event(
                ctx.root,
                event_type="independent_probe_rerun_passed" if independent_result.get("accepted") else "independent_probe_rerun_failed",
                severity="success" if independent_result.get("accepted") else "error",
                stage="PATCHLET_EXECUTION_IN_PROGRESS",
                summary=(
                    f"independent probe rerun passed for {', '.join(independent_result.get('proven_obligation_ids', []))}."
                    if independent_result.get("accepted")
                    else "independent probe rerun failed."
                ),
                artifact_paths=[_record_path_for_manifest(ctx, run_dir / "gates" / "independent_probe_rerun_result.json")],
                patchlet_id=pid,
                attempt_id=run_id,
                details=independent_result,
            )
            append_operator_event(
                ctx.root,
                event_type="goal_coverage_gate_passed" if coverage_result.get("accepted") else "goal_coverage_gate_failed",
                severity="success" if coverage_result.get("accepted") else "error",
                stage="PATCHLET_EXECUTION_IN_PROGRESS",
                summary=f"Goal coverage gate {coverage_result.get('coverage_status')} for {pid}.",
                artifact_paths=[_record_path_for_manifest(ctx, coverage_path)],
                patchlet_id=pid,
                attempt_id=run_id,
                details=coverage_result,
            )
            if coverage_result.get("accepted_for_patchlet_progress") and not coverage_result.get("accepted_for_done"):
                append_operator_event(
                    ctx.root,
                    event_type="partial_goal_coverage_accepted",
                    severity="info",
                    stage="PATCHLET_EXECUTION_IN_PROGRESS",
                    summary=f"Partial coverage accepted patchlet progress for {pid}; DONE remains blocked.",
                    artifact_paths=[_record_path_for_manifest(ctx, coverage_path)],
                    patchlet_id=pid,
                    attempt_id=run_id,
                    details=coverage_result,
                )
                append_operator_event(
                    ctx.root,
                    event_type="workflow_done_blocked_by_future_obligations",
                    severity="info",
                    stage="PATCHLET_EXECUTION_IN_PROGRESS",
                    summary=f"DONE blocked by future obligations after {pid}.",
                    artifact_paths=[_record_path_for_manifest(ctx, coverage_path)],
                    patchlet_id=pid,
                    attempt_id=run_id,
                    details={"future_obligation_ids": coverage_result.get("future_obligation_ids", [])},
                )
            update_goal_progress(
                workflow_root=ctx.paths.workflow_dir,
                event_reason="goal_coverage_gate",
                workflow_iteration=load_state(ctx).current_loop_iteration,
                proof_obligations=proof_obligations,
                probe_plan=probe_plan,
                latest_gate_result=coverage_result,
            )
            if not coverage_result.get("accepted"):
                if not use_worktree:
                    _cleanup_direct_worker_changes(ctx, changed_paths)
                report_status = "FAILED_WITH_EVIDENCE"
                report_error = "; ".join(coverage_result.get("failed_obligation_ids", [])) or "goal coverage failed"
                failure_id = _record_failure(
                    ctx,
                    source_id=pid,
                    observed_failure=report_error,
                    changed_paths=changed_paths,
                    failure_signature="goal_coverage_failed",
                )
        if not goal_gate_result.get("accepted"):
            if not use_worktree:
                _cleanup_direct_worker_changes(ctx, changed_paths)
            report_status = "FAILED_WITH_EVIDENCE"
            report_error = "; ".join(goal_gate_result.get("reasons", [])) or "semantic goal unsatisfied"
            failure_id = _record_failure(
                ctx,
                source_id=pid,
                observed_failure=report_error,
                changed_paths=changed_paths,
                failure_signature="semantic_goal_unsatisfied",
            )
            _append_patchlet_event(
                ctx,
                "patchlet_failed_with_evidence",
                patchlet_id=pid,
                attempt_id=run_id,
                severity="error",
                summary=f"Patchlet {pid} failed with evidence; semantic goal unsatisfied.",
                artifact_paths=[
                    _record_path_for_manifest(ctx, run_dir / "gates" / "goal_satisfaction_gate_result.json"),
                    ".codex-orchestrator/semantic_goal_checks/semantic_goal_check_result.json",
                    _record_path_for_manifest(ctx, ctx.paths.failures_dir / f"{failure_id}.json"),
                ],
                next_action="Classifying semantic goal failure.",
                details={"failure_signature": "semantic_goal_unsatisfied"},
            )
        elif diff_text:
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
        semantic_goal_valid=goal_gate_result.get("accepted") if goal_gate_result else None,
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
    _append_patchlet_event(
        ctx,
        "patchlet_wrapper_gate_passed" if gate_result["accepted"] else "patchlet_wrapper_gate_failed",
        patchlet_id=pid,
        attempt_id=run_id,
        severity="success" if gate_result["accepted"] else "error",
        summary=f"Wrapper gate {'accepted' if gate_result['accepted'] else 'rejected'} {run_id}.",
        artifact_paths=[wrapper_gate_result_path],
        next_action=(
            "Running target hygiene."
            if gate_result["accepted"] and report_status in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}
            else "Recording patchlet failure evidence."
        ),
        details={"wrapper_gate_accepted": gate_result["accepted"]},
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
            allowed_dirty_paths=_allowed_prompt_dirty_paths(ctx),
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
        _append_patchlet_event(
            ctx,
            "patchlet_target_hygiene_passed" if target_hygiene_result["accepted"] else "patchlet_target_hygiene_failed",
            patchlet_id=pid,
            attempt_id=run_id,
            severity="success" if target_hygiene_result["accepted"] else "error",
            summary=(
                f"Target hygiene passed for {run_id}."
                if target_hygiene_result["accepted"]
                else f"Target hygiene failed for {run_id}."
            ),
            artifact_paths=[target_hygiene_result.get("result_path")],
            next_action="Writing integration checkpoint." if target_hygiene_result["accepted"] else "Recording hygiene failure evidence.",
            details={"target_hygiene_accepted": target_hygiene_result["accepted"]},
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
            _append_patchlet_event(
                ctx,
                "patchlet_failed_with_evidence",
                patchlet_id=pid,
                attempt_id=run_id,
                severity="error",
                summary=f"Patchlet {pid} failed with evidence; target hygiene failed.",
                artifact_paths=[target_hygiene_result.get("result_path")],
                next_action="Preserving hygiene failure evidence.",
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
        _append_patchlet_event(
            ctx,
            "patchlet_checkpoint_written",
            patchlet_id=pid,
            attempt_id=run_id,
            severity="success",
            summary=f"Integration checkpoint written for {pid}.",
            artifact_paths=[
                _record_path_for_manifest(ctx, ctx.paths.integration_checkpoints_dir / f"{pid}.json"),
                _record_path_for_manifest(ctx, ctx.paths.integration_checkpoints_dir / f"{pid}_cleanliness.json"),
            ],
            next_action="Validating integration artifacts.",
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
        _append_patchlet_event(
            ctx,
            "patchlet_integration_validated",
            patchlet_id=pid,
            attempt_id=run_id,
            severity="success" if integration_validation_result.get("valid") else "error",
            summary=(
                f"Integration artifacts validated for {pid}."
                if integration_validation_result.get("valid")
                else f"Integration artifact validation failed for {pid}."
            ),
            artifact_paths=[_record_path_for_manifest(ctx, ctx.paths.integration_dir / "validation_result.json")],
            next_action="Accepting patchlet." if integration_validation_result.get("valid") else "Recording integration validation failure.",
            details={
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
            _append_patchlet_event(
                ctx,
                "patchlet_failed_with_evidence",
                patchlet_id=pid,
                attempt_id=run_id,
                severity="error",
                summary=f"Patchlet {pid} failed with evidence; integration artifact validation failed.",
                artifact_paths=[_record_path_for_manifest(ctx, ctx.paths.integration_dir / "validation_result.json")],
                next_action="Preserving integration validation evidence.",
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
                "slice_boundary_violations": diff_result.slice_boundary_violations or [],
                "path_classifications": diff_result.path_classifications or {},
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
        "timeout_seconds": _read_command_from_run_dir(run_dir).get("timeout_seconds") or patchlet.get("time_budget_seconds"),
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
        _append_patchlet_event(
            ctx,
            "patchlet_failed_with_evidence",
            patchlet_id=pid,
            attempt_id=run_id,
            severity="error",
            summary=f"Patchlet {pid} failed with evidence; unauthorized diff detected.",
            artifact_paths=[
                _record_path_for_manifest(ctx, diff_path),
                _record_path_for_manifest(ctx, ctx.paths.failures_dir / f"{failure_id}.json") if failure_id else None,
            ],
            next_action="Classifying patchlet failure.",
        )
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
        _append_patchlet_event(
            ctx,
            "patchlet_failed_with_evidence",
            patchlet_id=pid,
            attempt_id=run_id,
            severity="error",
            summary=f"Patchlet {pid} failed with evidence; report status {report_status}.",
            artifact_paths=[
                _record_path_for_manifest(ctx, worker_result.report_path) if worker_result.report_path else None,
                _record_path_for_manifest(ctx, ctx.paths.failures_dir / f"{failure_id}.json") if failure_id else None,
            ],
            next_action="Classifying patchlet failure.",
            details={"report_status": report_status, "report_valid": report_valid},
        )
    else:
        transition(ctx, state, "PATCHLET_EXECUTION_COMPLETE", reason=f"{pid} produced {report_status}")
        _append_patchlet_event(
            ctx,
            "patchlet_accepted",
            patchlet_id=pid,
            attempt_id=run_id,
            severity="success",
            summary=f"Patchlet {pid} accepted with status {report_status}.",
            artifact_paths=[
                _record_path_for_manifest(ctx, worker_result.report_path) if worker_result.report_path else None,
                wrapper_gate_result_path,
            ],
            next_action="Verifying transaction group or continuing patchlet execution.",
            details={"report_status": report_status},
        )
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


def _allowed_prompt_dirty_paths(ctx: TargetRepoContext) -> list[str]:
    identity = read_workflow_identity(ctx.root)
    if not identity:
        return []
    allowed: list[str] = []
    prompt_path = identity.get("master_prompt_path")
    if isinstance(prompt_path, str):
        try:
            allowed.append(Path(prompt_path).resolve().relative_to(ctx.root.resolve()).as_posix())
        except ValueError:
            pass
    command_args = identity.get("command_args") if isinstance(identity.get("command_args"), dict) else {}
    if command_args.get("allow_dirty_target"):
        for line in identity.get("target_dirty_status_at_start", []):
            if isinstance(line, str) and len(line) > 3:
                allowed.append(line[3:])
    return sorted(set(allowed))
