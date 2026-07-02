from __future__ import annotations

from dataclasses import dataclass

from codex_orchestrator.codex_adapter import worker_for_mode
from codex_orchestrator.git_guard import changed_between, git_diff, snapshot_status
from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.run_records import append_run_record
from codex_orchestrator.state import load_state, now_iso, transition
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.validators.diff_validator import validate_changed_paths
from codex_orchestrator.validators.report_validator import ReportValidationError, validate_patchlet_report_file


@dataclass(frozen=True)
class PatchletExecutionResult:
    patchlet_id: str
    status: str
    changed_paths: list[str]
    report_valid: bool
    message: str


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
        "source_id": source_id,
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


def run_next_patchlet(ctx: TargetRepoContext, *, worker_mode: str = "mock") -> PatchletExecutionResult:
    index = _load_patchlet_index(ctx)
    patchlet = _next_pending_patchlet(index)
    if patchlet is None:
        return PatchletExecutionResult("", "NO_PENDING_PATCHLETS", [], True, "no pending patchlets")
    pid = patchlet["patchlet_id"]
    state = load_state(ctx)
    state.current_patchlet_id = pid
    state.attempts[pid] = state.attempts.get(pid, 0) + 1
    transition(ctx, state, "PATCHLET_EXECUTION_IN_PROGRESS", reason=f"running {pid}")

    before = snapshot_status(ctx.root)
    run_id = f"{pid}_attempt{state.attempts[pid]}"
    run_dir = ctx.paths.runs_dir / run_id
    worker = worker_for_mode(worker_mode)
    worker_result = worker.run_patchlet(ctx, patchlet, run_dir=run_dir)
    after = snapshot_status(ctx.root)
    changed_paths = changed_between(before, after)
    diff_text = git_diff(ctx.root)
    (run_dir / "diff.patch").write_text(diff_text, encoding="utf-8")
    (run_dir / "diff_name_status.txt").write_text("\n".join(changed_paths) + "\n", encoding="utf-8")

    diff_result = validate_changed_paths(changed_paths, patchlet)
    append_run_record(ctx, {
        "stage": "PATCHLET_EXECUTION_IN_PROGRESS",
        "worker": worker_mode,
        "patchlet_id": pid,
        "repair_plan_id": patchlet.get("repair_plan_id"),
        "source_failure_ids": patchlet.get("source_failure_ids", []),
        "exit_code": worker_result.exit_code,
        "stdout": worker_result.stdout,
        "stderr": worker_result.stderr,
        "changed_files": changed_paths,
        "diff_allowed": diff_result.allowed,
    })

    if not diff_result.allowed:
        failure_id = _record_failure(
            ctx,
            source_id=pid,
            observed_failure=f"Unauthorized diff detected: {', '.join(diff_result.unauthorized_paths)}",
            changed_paths=changed_paths,
        )
        patchlet["status"] = "FAILED_WITH_EVIDENCE"
        _save_patchlet_index(ctx, index)
        state = load_state(ctx)
        if pid not in state.failed_patchlets:
            state.failed_patchlets.append(pid)
        if pid in state.pending_patchlets:
            state.pending_patchlets.remove(pid)
        transition(ctx, state, "FAILURE_CLASSIFICATION_REQUIRED", reason=f"{pid} unauthorized diff {failure_id}")
        return PatchletExecutionResult(pid, "FAILED_WITH_EVIDENCE", changed_paths, False, f"unauthorized diff; failure {failure_id}")

    report_valid = False
    report_status = "FAILED_WITH_EVIDENCE"
    try:
        if worker_result.report_path is None:
            raise ReportValidationError("Worker did not create a report")
        report = validate_patchlet_report_file(worker_result.report_path, patchlet)
        report_valid = True
        report_status = report["status"]
    except ReportValidationError as exc:
        _record_failure(ctx, source_id=pid, observed_failure=f"Invalid or missing patchlet report: {exc}", changed_paths=changed_paths)
        report_status = "FAILED_WITH_EVIDENCE"

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


def run_all_patchlets(ctx: TargetRepoContext, *, worker_mode: str = "mock") -> list[PatchletExecutionResult]:
    results: list[PatchletExecutionResult] = []
    while True:
        result = run_next_patchlet(ctx, worker_mode=worker_mode)
        if result.status == "NO_PENDING_PATCHLETS":
            break
        results.append(result)
        if result.status in {"FAILED_WITH_EVIDENCE", "BLOCKED_WITH_EVIDENCE"}:
            break
    return results
