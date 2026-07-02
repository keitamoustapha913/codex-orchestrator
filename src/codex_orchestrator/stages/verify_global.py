from __future__ import annotations

from dataclasses import dataclass

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.state import load_state, now_iso, transition
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.validators.report_validator import ReportValidationError, validate_patchlet_report_file


@dataclass(frozen=True)
class GlobalVerificationResult:
    done: bool
    status: str
    failed_patchlets: list[str]
    unproven_patchlets: list[str]


def verify_global(ctx: TargetRepoContext) -> GlobalVerificationResult:
    index = read_json(ctx.paths.patchlet_index) if ctx.paths.patchlet_index.exists() else {"patchlets": []}
    state = load_state(ctx)
    patchlets = index.get("patchlets", [])
    patchlets_by_id = {patchlet["patchlet_id"]: patchlet for patchlet in patchlets}
    failed: list[str] = []
    unproven: list[str] = []
    proven: list[str] = []
    resolved_source_patchlets: set[str] = set()
    resolved_failure_ids: list[str] = []

    def _validated_report_status(patchlet_id: str) -> str | None:
        patchlet = patchlets_by_id.get(patchlet_id)
        if patchlet is None:
            return None
        report_path = ctx.paths.reports_dir / f"{patchlet_id}.json"
        if not report_path.exists():
            return None
        try:
            report = validate_patchlet_report_file(report_path, patchlet)
        except ReportValidationError:
            return None
        return report["status"]

    for cycle in state.repair_cycles:
        generated_patchlet_ids = cycle.get("generated_patchlet_ids", [])
        if not generated_patchlet_ids:
            continue
        statuses = [_validated_report_status(pid) for pid in generated_patchlet_ids]
        if not statuses or any(status not in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"} for status in statuses):
            continue
        for failure_id in cycle.get("source_failure_ids", []):
            failure_path = ctx.paths.failures_dir / f"{failure_id}.json"
            if not failure_path.exists():
                continue
            failure = read_json(failure_path)
            source_id = failure.get("source_id")
            if source_id:
                resolved_source_patchlets.add(source_id)
                resolved_failure_ids.append(failure_id)

    for patchlet in patchlets:
        pid = patchlet["patchlet_id"]
        patchlet_status = patchlet.get("status")
        if pid in resolved_source_patchlets:
            continue
        if patchlet_status in {"FAILED_WITH_EVIDENCE", "BLOCKED_WITH_EVIDENCE"}:
            failed.append(pid)
            continue
        report_path = ctx.paths.reports_dir / f"{pid}.json"
        if not report_path.exists():
            unproven.append(pid)
            continue
        try:
            report = validate_patchlet_report_file(report_path, patchlet)
        except ReportValidationError:
            failed.append(pid)
            continue
        if report["status"] in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}:
            proven.append(pid)
        elif report["status"] in {"FAILED_WITH_EVIDENCE", "BLOCKED_WITH_EVIDENCE"}:
            failed.append(pid)
        else:
            unproven.append(pid)

    done = bool(index.get("patchlets")) and not failed and not unproven
    status = "DONE" if done else "GLOBAL_VERIFICATION_FAILED"
    final = {
        "schema_version": "1.0",
        "kind": "final_verification",
        "status": status,
        "done": done,
        "proven_patchlets": proven,
        "failed_patchlets": failed,
        "unproven_patchlets": unproven,
        "created_at": now_iso(),
        "evidence_summary": "MVP verifier validates every patchlet report and accepts COMPLETE or VERIFIED_NO_CHANGE_NEEDED.",
        "repair_cycles": state.repair_cycles,
        "resolved_failure_ids": resolved_failure_ids,
    }
    write_json(ctx.paths.final_verification_json, final)
    ctx.paths.final_verification_md.write_text(
        "# Final Verification\n\n"
        f"Status: `{status}`\n\n"
        f"Proven patchlets: {', '.join(proven) or 'none'}\n\n"
        f"Failed patchlets: {', '.join(failed) or 'none'}\n\n"
        f"Unproven patchlets: {', '.join(unproven) or 'none'}\n",
        encoding="utf-8",
    )
    if done:
        transition(ctx, state, "DONE", reason="global verification passed")
    else:
        transition(ctx, state, "FAILURE_CLASSIFICATION_REQUIRED", reason="global verification failed")
    return GlobalVerificationResult(done=done, status=status, failed_patchlets=failed, unproven_patchlets=unproven)
