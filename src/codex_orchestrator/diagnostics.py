from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from .jsonio import read_json, write_json
from .paths import relative_to_repo
from .target_repo import TargetRepoContext


def _path_from_manifest(ctx: TargetRepoContext, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return ctx.root / path


def _load_attempt_entry(ctx: TargetRepoContext, attempt_id: str) -> dict[str, Any]:
    manifest = read_json(ctx.paths.run_manifest)
    for run in manifest.get("runs", []):
        if run.get("attempt_id") == attempt_id:
            return run
    raise ValueError(f"unknown real_codex attempt: {attempt_id}")


def _load_text(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _load_jsonl_events(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            events.append({"_raw": line, "_parse_error": True})
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
        else:
            events.append({"_value": parsed})
    return events


def _load_json_object(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _contains_any(text: str, patterns: list[str]) -> bool:
    haystack = text.lower()
    return any(pattern in haystack for pattern in patterns)


def _dirty_paths_from_text(text: str) -> list[str]:
    marker = "dirty paths:"
    if marker not in text:
        return []
    _, tail = text.split(marker, 1)
    first_line = tail.strip().splitlines()[0] if tail.strip() else ""
    return [item.strip().strip(",") for item in first_line.split(",") if item.strip()]


CAPSULE_LIKE_TARGET_ROOT_DIRS = (
    "worker_stage",
    "worker_memory",
    "worker_hooks",
    "gates",
    "diagnostics",
)


def _capsule_path_violation(
    ctx: TargetRepoContext,
    *,
    run: dict[str, Any],
    run_dir: Path | None,
    wrapper_gate_path: Path | None,
) -> tuple[list[str], dict[str, Any], list[str], str] | None:
    observed_signals: list[str] = []
    supported_by: list[str] = []
    wrong_dirs: list[str] = []

    for dirname in CAPSULE_LIKE_TARGET_ROOT_DIRS:
        if (ctx.root / dirname).exists():
            wrong_dirs.append(dirname)
            observed_signals.append(f"target_root_{dirname}_present")
            supported_by.append(f"{dirname}/")

    worker_failure_message = str(run.get("worker_failure", {}).get("message", ""))
    wrapper_gate = _load_json_object(wrapper_gate_path)
    wrapper_reasons = "\n".join(str(reason) for reason in wrapper_gate.get("reasons", []) if reason)
    evidence_text = "\n".join([worker_failure_message, wrapper_reasons])
    for dirname in CAPSULE_LIKE_TARGET_ROOT_DIRS:
        if (
            f"worker capsule artifact written outside run directory: {dirname}/" in evidence_text
            or f"dirty paths: {dirname}/" in evidence_text
        ):
            if dirname not in wrong_dirs:
                wrong_dirs.append(dirname)
            observed_signals.append(f"preserved_{dirname}_path_violation_message")
            supported_by.append("run_manifest.json")
            if wrapper_reasons:
                supported_by.append("wrapper_gate_result.json")

    if not wrong_dirs:
        return None

    expected_stage_dir = (
        relative_to_repo(ctx.root, run_dir / "worker_stage") + "/"
        if run_dir is not None
        else ".codex-orchestrator/runs/<attempt>/worker_stage/"
    )
    summary = (
        "Codex wrote Worker Capsule-like artifacts outside the run directory. "
        f"Expected worker_stage artifacts under {expected_stage_dir}; "
        "target-root worker_stage/ is forbidden."
    )
    return (
        sorted(set(observed_signals)),
        {
            "primary_category": "worker_capsule_path_violation",
            "confidence": "high",
            "summary": summary,
            "supported_by": sorted(set(supported_by or ["run_manifest.json"])),
        },
        [],
        (
            "Fix prompt/path instructions so Codex writes stage files to "
            "CXOR_WORKER_STAGE_DIR and CXOR_FINAL_REPORT_PATH; do not create "
            "target-root worker_stage/. Keep validators intact."
        ),
    )


def _target_dirty_after_integration_apply(
    *,
    run: dict[str, Any],
    live_memory: dict[str, Any],
    stderr_text: str,
) -> tuple[list[str], dict[str, Any], list[str], str] | None:
    evidence_text = "\n".join([
        stderr_text,
        str(run.get("worker_failure", {}).get("message", "")),
    ])
    if "clean target repo" not in evidence_text.lower():
        return None
    dirty_paths = _dirty_paths_from_text(evidence_text)
    if not dirty_paths:
        return None
    if any(path.rstrip("/") in CAPSULE_LIKE_TARGET_ROOT_DIRS for path in dirty_paths):
        return None

    allowed_file = live_memory.get("allowed_product_runtime_file")
    if not isinstance(allowed_file, str) or not allowed_file:
        return None
    if allowed_file not in dirty_paths:
        return None

    patchlet_id = str(run.get("patchlet_id", "unknown patchlet"))
    summary = (
        f"A prior patchlet ({patchlet_id}) appears to have produced an accepted product/runtime "
        f"change, but the target working tree retained {allowed_file} as dirty before the next "
        "worktree step. This indicates missing integration-state management, not Codex path failure."
    )
    return (
        ["target_dirty_allowed_product_file"],
        {
            "primary_category": "target_dirty_after_integration_apply",
            "confidence": "high",
            "summary": summary,
            "supported_by": ["run_manifest.json", "worker_memory/LIVE_MEMORY.json"],
        },
        [],
        (
            "Record accepted changes in integration state and advance the integration ref so "
            "the target product/runtime files remain clean between patchlets; do not weaken "
            "the clean-target precondition."
        ),
    )


def _patchlet_report_schema_violation(
    *,
    run: dict[str, Any],
    artifact_presence: dict[str, bool],
) -> tuple[list[str], dict[str, Any], list[str], str] | None:
    if run.get("report_valid") is not False:
        return None

    report_validation = run.get("report_validation")
    report_validation_reason = ""
    if isinstance(report_validation, dict):
        report_validation_reason = str(report_validation.get("reason") or "")
    report_error = str(run.get("report_error") or "")
    reason = report_validation_reason or report_error
    if not reason:
        return None

    worker_failure = run.get("worker_failure")
    exit_code = run.get("exit_code")
    if isinstance(worker_failure, dict) and exit_code is None:
        exit_code = worker_failure.get("exit_code")
    produced_normal_evidence = any(
        artifact_presence.get(key)
        for key in ("stdout", "output_jsonl", "worker_capsule", "worker_memory", "wrapper_gate_result")
    )
    if exit_code not in {0, None} and not produced_normal_evidence:
        return None

    observed_signals = ["report_validation_failed"]
    if "FIXED" in reason:
        observed_signals.append("unsupported_report_status")
    if ("cleanup_proof" in reason or "cleanup_passed" in reason) and "not of type 'string'" in reason:
        observed_signals.append("cleanup_proof_type_error")
    if "required property" in reason:
        observed_signals.append("missing_required_report_fields")

    summary = "Worker completed but produced a patchlet report that failed schema validation."
    if "FIXED" in reason:
        summary += " The report used unsupported status FIXED."

    return (
        observed_signals,
        {
            "primary_category": "patchlet_report_schema_violation",
            "confidence": "high",
            "summary": summary,
            "supported_by": ["run_manifest.json"],
            "report_valid": False,
            "report_validation_reason": reason,
            "report_error": report_error or None,
            "attempt_id": str(run.get("attempt_id", "")),
            "patchlet_id": str(run.get("patchlet_id", "")),
        },
        [],
        (
            "Fix the generated report contract/prompt so Codex writes a schema-valid "
            "patchlet report. Do not add unsupported statuses such as FIXED, do not "
            "weaken the report schema, keep cleanup_proof as a string, and include all "
            "required fields before rerunning."
        ),
    )


def _wrapper_gate_final_status_marker_error(
    *,
    wrapper_gate_path: Path | None,
) -> tuple[list[str], dict[str, Any], list[str], str] | None:
    wrapper_gate = _load_json_object(wrapper_gate_path)
    if not wrapper_gate:
        return None
    if wrapper_gate.get("accepted") is not False:
        return None

    marker_error = wrapper_gate.get("final_status_marker_error")
    reasons = [str(reason) for reason in wrapper_gate.get("reasons", []) if reason]
    reason_text = "\n".join(reasons).lower()
    if not marker_error and "final_status" not in reason_text and "final status" not in reason_text:
        return None
    final_status_gate = wrapper_gate.get("final_status_gate")
    if final_status_gate not in {"fail", "missing"} and not marker_error:
        return None

    subtype = str(marker_error or "final_status_marker_error")
    summary = "Wrapper gate rejected the worker final report because the FINAL_STATUS marker was not canonical."
    if subtype == "missing_final_status_marker":
        summary = "Wrapper gate rejected the worker final report because the required FINAL_STATUS marker was missing."
    if subtype == "invalid_final_status_marker_value":
        summary = "Wrapper gate rejected the worker final report because the FINAL_STATUS marker value was invalid."

    return (
        ["wrapper_gate_final_status_marker_error", subtype],
        {
            "primary_category": "wrapper_gate_final_status_marker_error",
            "confidence": "high",
            "summary": summary,
            "supported_by": ["wrapper_gate_result.json"],
            "subtype": subtype,
            "wrapper_gate_reasons": reasons,
            "final_status_gate": final_status_gate,
            "final_status_marker_noncanonical": wrapper_gate.get("final_status_marker_noncanonical"),
        },
        [],
        (
            "Fix the generated final report contract/prompt so Codex writes a standalone "
            "canonical FINAL_STATUS line at column 1. Do not weaken the wrapper gate."
        ),
    )


def _stage_precondition_or_tg_routing_error(
    *,
    run: dict[str, Any],
) -> tuple[list[str], dict[str, Any], list[str], str] | None:
    worker_failure = run.get("worker_failure")
    if not isinstance(worker_failure, dict):
        return None
    error_type = str(worker_failure.get("type") or "")
    message = str(worker_failure.get("message") or "")
    if error_type != "StagePreconditionError" and "precondition failed for" not in message:
        return None

    stage = None
    match = re.search(r"precondition failed for ([^:]+):", message)
    if match:
        stage = match.group(1)
    tg_match = re.search(r"\b(TG\d{3,})\b", message)
    if stage == "regenerate-patchlets" and tg_match:
        source_id = tg_match.group(1)
        return (
            ["transaction_group_repair_routing_error", "transaction_group_id_used_as_patchlet_id"],
            {
                "primary_category": "transaction_group_repair_routing_error",
                "confidence": "high",
                "summary": (
                    f"Repair regeneration received transaction group id {source_id} where it needed "
                    "member patchlet ids. Transaction groups must not be resolved as patchlet manifests."
                ),
                "supported_by": ["run_manifest.json"],
                "stage": stage,
                "source_id": source_id,
            },
            [],
            (
                "Preserve source_type on failure records and expand transaction-group failures "
                "to member patchlet ids before regenerating patchlets."
            ),
        )

    return (
        ["stage_precondition_error"],
        {
            "primary_category": "stage_precondition_error",
            "confidence": "medium",
            "summary": f"{error_type or 'Stage precondition'} stopped execution: {message}",
            "supported_by": ["run_manifest.json"],
            "stage": stage,
        },
        [],
        "Inspect the structured stage precondition error and fix the stage input state before rerunning.",
    )


def _integration_checkpoint_target_cleanliness_error(
    *,
    run: dict[str, Any],
) -> tuple[list[str], dict[str, Any], list[str], str] | None:
    validation = run.get("integration_artifact_validation")
    if not isinstance(validation, dict) or validation.get("valid") is not False:
        return None
    errors = validation.get("errors", [])
    if not isinstance(errors, list):
        return None
    for error in errors:
        if not isinstance(error, dict):
            continue
        path = str(error.get("path") or "")
        message = str(error.get("message") or "")
        if "integration/checkpoints/" in path and "target_working_tree_clean_after_checkpoint" in message:
            return (
                ["integration_checkpoint_target_cleanliness_error"],
                {
                    "primary_category": "integration_checkpoint_target_cleanliness_error",
                    "confidence": "high",
                    "summary": "Integration checkpoint validation failed because checkpoint target cleanliness was false.",
                    "supported_by": ["run_manifest.json", path],
                    "validation_path": validation.get("path"),
                    "error_path": path,
                    "error_message": message,
                    "target_cleanliness_report_path": run.get("target_cleanliness_report_path"),
                },
                [],
                "Inspect the target hygiene gate and checkpoint cleanliness sidecar; do not weaken the checkpoint schema.",
            )
    return None


def _target_cache_artifact_leak(
    *,
    ctx: TargetRepoContext,
    run: dict[str, Any],
) -> tuple[list[str], dict[str, Any], list[str], str] | None:
    hygiene_path_value = run.get("target_hygiene_gate_result")
    hygiene_path = _path_from_manifest(ctx, str(hygiene_path_value)) if hygiene_path_value else None
    hygiene = _load_json_object(hygiene_path)
    if not hygiene:
        return None
    detected = hygiene.get("cache_artifacts_detected", [])
    removed = hygiene.get("cache_artifacts_removed", [])
    if not isinstance(detected, list) or not detected:
        return None
    if hygiene.get("accepted") is True:
        return None
    paths = [str(item.get("path")) for item in detected if isinstance(item, dict) and item.get("path")]
    return (
        ["target_cache_artifact_leak"],
        {
            "primary_category": "target_cache_artifact_leak",
            "confidence": "high",
            "summary": "Target hygiene detected Python cache artifacts that prevented target cleanliness.",
            "supported_by": ["target_hygiene_gate_result.json"],
            "cache_artifacts_detected": paths,
            "cache_artifacts_removed": [
                str(item.get("path")) for item in removed if isinstance(item, dict) and item.get("path")
            ],
        },
        [],
        "Inspect the recorded cache artifacts and prevention contract; do not silently ignore or delete unknown dirty paths.",
    )


def _integration_artifact_validation_error(
    *,
    run: dict[str, Any],
) -> tuple[list[str], dict[str, Any], list[str], str] | None:
    validation = run.get("integration_artifact_validation")
    if not isinstance(validation, dict) or validation.get("valid") is not False:
        return None
    errors = validation.get("errors", [])
    first_error = errors[0] if isinstance(errors, list) and errors and isinstance(errors[0], dict) else {}
    return (
        ["integration_artifact_validation_error"],
        {
            "primary_category": "integration_artifact_validation_error",
            "confidence": "high",
            "summary": "Integration artifact validation failed after worker evidence was produced.",
            "supported_by": ["run_manifest.json", str(validation.get("path") or "integration validation result")],
            "validation_path": validation.get("path"),
            "error_path": first_error.get("path"),
            "error_message": first_error.get("message"),
        },
        [],
        "Inspect the integration validation result and fix the artifact contract violation; do not classify this as a network/API failure.",
    )


def _run_manifest_attempt_lifecycle_error(
    *,
    run: dict[str, Any],
) -> tuple[list[str], dict[str, Any], list[str], str] | None:
    if run.get("lifecycle_status") != "ATTEMPT_FAILED_WITH_EVIDENCE":
        return None
    if not run.get("failed_stage"):
        return None
    if run.get("integration_artifact_validation"):
        return None
    return (
        ["run_manifest_attempt_lifecycle_error"],
        {
            "primary_category": "run_manifest_attempt_lifecycle_error",
            "confidence": "medium",
            "summary": "Run manifest recorded a failed attempt lifecycle before a more specific validation result was available.",
            "supported_by": ["run_manifest.json"],
            "failed_stage": run.get("failed_stage"),
        },
        [],
        "Inspect the manifest lifecycle events for the failing attempt and preserve current-attempt evidence.",
    )


def _runbook_attempt_evidence_mismatch(
    *,
    run: dict[str, Any],
) -> tuple[list[str], dict[str, Any], list[str], str] | None:
    consistency = run.get("attempt_consistency")
    if not isinstance(consistency, dict) or consistency.get("valid") is not False:
        return None
    mismatches = consistency.get("mismatches", [])
    return (
        ["runbook_attempt_evidence_mismatch"],
        {
            "primary_category": "runbook_attempt_evidence_mismatch",
            "confidence": "high",
            "summary": "Operator runbook evidence contains mismatched attempt identities.",
            "supported_by": ["result.json"],
            "attempt_consistency": consistency,
            "mismatches": mismatches if isinstance(mismatches, list) else [],
        },
        [],
        "Inspect the runbook result attempt_consistency object and avoid using stale manifest or diagnosis evidence.",
    )


def _network_or_api_evidence(stderr_text: str, output_events: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    patterns = [
        "connection failed",
        "connection error",
        "dns",
        "api error",
        "api timeout",
        "http error",
        "rate limit",
        "model unavailable",
        "network timeout",
        "timed out connecting",
        "service unavailable",
        "authentication failed",
        "session expired",
    ]
    haystacks = [stderr_text.lower()]
    for event in output_events:
        for key in ("error", "message", "stderr"):
            value = event.get(key)
            if isinstance(value, str):
                haystacks.append(value.lower())
    hits = sorted({pattern for text in haystacks for pattern in patterns if pattern in text})
    return bool(hits), hits


def _analyze_signals(
    stderr_text: str,
    stdout_text: str,
    output_events: list[dict[str, Any]],
    artifact_presence: dict[str, bool],
    *,
    command: dict[str, Any],
    run: dict[str, Any],
) -> tuple[list[str], dict[str, Any], list[str], str]:
    observed_signals: list[str] = []
    supported_by: list[str] = []
    known_unknowns: list[str] = []

    worker_failure = run.get("worker_failure", {})
    command_timed_out = command.get("timed_out") is True and command.get("exit_code") == 124
    manifest_timed_out = worker_failure.get("timed_out") is True and worker_failure.get("exit_code") == 124
    if command_timed_out or manifest_timed_out:
        timeout_seconds = command.get("timeout_seconds") or worker_failure.get("timeout_seconds")
        observed_signals.append("command_json_records_orchestrator_timeout" if command_timed_out else "run_manifest_records_orchestrator_timeout")
        supported_by.append("command.json" if command_timed_out else "run_manifest.json")
        if command_timed_out and manifest_timed_out:
            supported_by.append("run_manifest.json")
        progress_note = ""
        if artifact_presence.get("progress_jsonl"):
            observed_signals.append("progress_jsonl_present")
            supported_by.append("progress.jsonl")
            progress_note = " Codex was alive before timeout."
        timeout_text = f"{timeout_seconds} seconds" if timeout_seconds is not None else "the configured timeout"
        return (
            observed_signals,
            {
                "primary_category": "orchestrator_subprocess_timeout",
                "confidence": "high",
                "summary": (
                    f"The orchestrator terminated the Codex subprocess after {timeout_text}. "
                    "This is bounded containment, not task success."
                    f"{progress_note}"
                ),
                "supported_by": sorted(set(supported_by)),
            },
            known_unknowns,
            "Increase timeout or simplify prompt/task before rerunning; keep validators intact and blind retry disabled.",
        )

    if _contains_any(stderr_text, ["auth", "authentication", "session", "token", "login"]):
        observed_signals.append("stderr_contains_auth_or_session_error")
        supported_by.append("stderr.txt")
        return (
            observed_signals,
            {
                "primary_category": "auth_or_session_error",
                "confidence": "medium",
                "summary": "stderr contains authentication or session-related failure text.",
                "supported_by": supported_by,
            },
            known_unknowns,
            "Inspect the Codex session or authentication state, then rerun the opt-in smoke without weakening validators.",
        )

    if _contains_any(stderr_text, ["usage:", "unknown option", "unknown argument", "invalid option", "unexpected argument"]):
        observed_signals.append("stderr_contains_cli_usage_error")
        supported_by.append("stderr.txt")
        return (
            observed_signals,
            {
                "primary_category": "codex_cli_usage_error",
                "confidence": "medium",
                "summary": "stderr contains command usage or argument parsing failure text.",
                "supported_by": supported_by,
            },
            known_unknowns,
            "Inspect the preserved command.json and Codex CLI syntax before rerunning the opt-in smoke.",
        )

    has_network_evidence, network_hits = _network_or_api_evidence(stderr_text, output_events)
    if has_network_evidence:
        observed_signals.append("captured_output_contains_network_or_api_error")
        supported_by.extend(["stderr.txt" if stderr_text else "output.jsonl"])
        return (
            observed_signals,
            {
                "primary_category": "network_or_api_error",
                "confidence": "medium",
                "summary": "captured stderr or output.jsonl contains network, API, timeout, or model availability error text.",
                "supported_by": sorted(set(supported_by)),
                "matched_external_error_terms": network_hits,
            },
            known_unknowns,
            "Inspect service availability or transient upstream conditions, but keep blind retry disabled until the evidence is reviewed.",
        )

    if _contains_any(stderr_text, ["permission denied", "operation not permitted", "access denied", "eacces"]):
        observed_signals.append("stderr_contains_permission_error")
        supported_by.append("stderr.txt")
        return (
            observed_signals,
            {
                "primary_category": "permission_error",
                "confidence": "medium",
                "summary": "stderr contains permission-related failure text.",
                "supported_by": supported_by,
            },
            known_unknowns,
            "Inspect filesystem and credential permissions for the Codex subprocess, then rerun only after correcting them.",
        )

    if not stdout_text.strip() and not stderr_text.strip():
        observed_signals.append("stdout_and_stderr_empty")
        supported_by.extend(["stdout.txt", "stderr.txt"])

    if not artifact_presence["report"]:
        observed_signals.append("report_missing_after_worker_exit")
        supported_by.append("run_manifest.json")
    if not artifact_presence["probe_run"]:
        observed_signals.append("probe_run_missing_after_worker_exit")
        supported_by.append("run_manifest.json")
    if not artifact_presence["diff"]:
        observed_signals.append("diff_missing_after_worker_exit")
        supported_by.append("run_manifest.json")

    known_unknowns.append("Captured artifacts do not identify a more specific installed-Codex failure category.")
    return (
        observed_signals,
        {
            "primary_category": "unknown_codex_nonzero_exit",
            "confidence": "medium" if observed_signals else "low",
            "summary": "The installed Codex binary exited non-zero, but the preserved artifacts do not identify a more specific cause.",
            "supported_by": sorted(set(supported_by or ["run_manifest.json"])),
        },
        known_unknowns,
        "Inspect stdout.txt, stderr.txt, output.jsonl, command.json, and the generated prompt artifact before changing prompts or rerunning the opt-in smoke.",
    )


def _markdown_for_diagnosis(diagnosis: dict[str, Any]) -> str:
    evidence = diagnosis["evidence_paths"]
    presence = diagnosis["artifact_presence"]
    worker_failure = diagnosis["worker_failure"]
    diagnosis_block = diagnosis["diagnosis"]
    signals = diagnosis["observed_signals"] or ["none"]
    unknowns = diagnosis["known_unknowns"] or ["none"]
    return "\n".join(
        [
            f"# {diagnosis['attempt_id']} Real Codex Failure Diagnosis",
            "",
            f"- Patchlet: `{diagnosis['patchlet_id']}`",
            f"- Worker mode: `{diagnosis['worker_mode']}`",
            f"- Execution mode: `{diagnosis['execution_mode']}`",
            f"- Outcome: `{diagnosis['outcome']}`",
            f"- Category: `{diagnosis_block['primary_category']}`",
            f"- Confidence: `{diagnosis_block['confidence']}`",
            "",
            "## Worker Failure",
            "",
            f"- Type: `{worker_failure['type']}`",
            f"- Exit code: `{worker_failure['exit_code']}`",
            f"- Message: {worker_failure['message']}",
            "",
            "## Evidence Paths",
            "",
            f"- stdout: `{evidence['stdout']}`",
            f"- stderr: `{evidence['stderr']}`",
            f"- output_jsonl: `{evidence['output_jsonl']}`",
            f"- command: `{evidence['command']}`",
            f"- run_manifest: `{evidence['run_manifest']}`",
            f"- prompt_artifact: `{evidence['prompt_artifact']}`",
            "",
            "## Artifact Presence",
            "",
            *[f"- {key}: `{value}`" for key, value in presence.items()],
            "",
            "## Observed Signals",
            "",
            *[f"- {signal}" for signal in signals],
            "",
            "## Known Unknowns",
            "",
            *[f"- {item}" for item in unknowns],
            "",
            "## Next Action",
            "",
            diagnosis["recommended_next_action"],
        ]
    ) + "\n"


def diagnose_real_codex_attempt(ctx: TargetRepoContext, *, attempt_id: str, prompt_artifact_path: Path | None = None, outcome: str = "safe_failure") -> dict[str, Any]:
    run = _load_attempt_entry(ctx, attempt_id)
    if run.get("worker_mode") != "real_codex":
        raise ValueError(f"attempt is not a real_codex run: {attempt_id}")

    prompt_path = prompt_artifact_path
    if prompt_path is None:
        from .real_codex_smoke import _latest_prompt_artifact_path  # local import to avoid circular import at module load
        prompt_path = _latest_prompt_artifact_path(ctx)
    if prompt_path is None:
        subprompts = sorted(ctx.paths.subprompts_dir.glob("*.md"))
        prompt_path = subprompts[0] if subprompts else None

    paths = run.get("paths", {})
    stdout_path = _path_from_manifest(ctx, paths.get("stdout"))
    stderr_path = _path_from_manifest(ctx, paths.get("stderr"))
    output_jsonl_path = _path_from_manifest(ctx, paths.get("output_jsonl"))
    command_path = _path_from_manifest(ctx, paths.get("command"))
    progress_jsonl_path = _path_from_manifest(ctx, paths.get("progress_jsonl"))
    diff_path = _path_from_manifest(ctx, paths.get("diff"))
    report_path = ctx.paths.reports_dir / f"{run['patchlet_id']}.json"
    probe_run_path = ctx.paths.probe_dir / run["patchlet_id"] / "run_001"
    run_dir = _path_from_manifest(ctx, paths.get("run_dir"))
    worker_capsule_path = run_dir / "worker_capsule.json" if run_dir is not None else None
    worker_memory_dir = run_dir / "worker_memory" if run_dir is not None else None
    live_memory_path = worker_memory_dir / "LIVE_MEMORY.json" if worker_memory_dir is not None else None
    worker_stage_dir = run_dir / "worker_stage" if run_dir is not None else None
    worker_events_path = run_dir / "worker_hooks" / "events.jsonl" if run_dir is not None else None
    wrapper_gate_path = run_dir / "gates" / "wrapper_gate_result.json" if run_dir is not None else None

    artifact_presence = {
        "stdout": bool(stdout_path and stdout_path.exists()),
        "stderr": bool(stderr_path and stderr_path.exists()),
        "output_jsonl": bool(output_jsonl_path and output_jsonl_path.exists()),
        "command": bool(command_path and command_path.exists()),
        "progress_jsonl": bool(progress_jsonl_path and progress_jsonl_path.exists()),
        "prompt_artifact": bool(prompt_path and prompt_path.exists()),
        "report": report_path.exists(),
        "probe_run": probe_run_path.exists(),
        "diff": bool(diff_path and diff_path.exists()),
        "worker_capsule": bool(worker_capsule_path and worker_capsule_path.exists()),
        "worker_memory": bool(worker_memory_dir and worker_memory_dir.exists()),
        "task_contract": bool(worker_memory_dir and (worker_memory_dir / "TASK_CONTRACT.md").exists()),
        "live_memory_json": bool(worker_memory_dir and (worker_memory_dir / "LIVE_MEMORY.json").exists()),
        "worker_stage": bool(worker_stage_dir and worker_stage_dir.exists()),
        "preflight_stage": bool(worker_stage_dir and (worker_stage_dir / "00_preflight.md").exists()),
        "final_report_stage": bool(worker_stage_dir and (worker_stage_dir / "05_final_report.md").exists()),
        "worker_events": bool(worker_events_path and worker_events_path.exists()),
        "wrapper_gate_result": bool(wrapper_gate_path and wrapper_gate_path.exists()),
    }

    stdout_text = _load_text(stdout_path)
    stderr_text = _load_text(stderr_path)
    command = _load_json_object(command_path)
    live_memory = _load_json_object(live_memory_path)
    output_events = _load_jsonl_events(output_jsonl_path)
    worker_events = _load_jsonl_events(worker_events_path)
    capsule_violation = _capsule_path_violation(
        ctx,
        run=run,
        run_dir=run_dir,
        wrapper_gate_path=wrapper_gate_path,
    )
    if capsule_violation is not None:
        observed_signals, diagnosis_block, known_unknowns, next_action = capsule_violation
    else:
        report_violation = _patchlet_report_schema_violation(
            run=run,
            artifact_presence=artifact_presence,
        )
        if report_violation is not None:
            observed_signals, diagnosis_block, known_unknowns, next_action = report_violation
        else:
            wrapper_gate_marker_error = _wrapper_gate_final_status_marker_error(
                wrapper_gate_path=wrapper_gate_path,
            )
            if wrapper_gate_marker_error is not None:
                observed_signals, diagnosis_block, known_unknowns, next_action = wrapper_gate_marker_error
            else:
                stage_or_routing_error = _stage_precondition_or_tg_routing_error(run=run)
                if stage_or_routing_error is not None:
                    observed_signals, diagnosis_block, known_unknowns, next_action = stage_or_routing_error
                else:
                    checkpoint_cleanliness_error = _integration_checkpoint_target_cleanliness_error(run=run)
                    if checkpoint_cleanliness_error is not None:
                        observed_signals, diagnosis_block, known_unknowns, next_action = checkpoint_cleanliness_error
                    else:
                        cache_leak = _target_cache_artifact_leak(ctx=ctx, run=run)
                        if cache_leak is not None:
                            observed_signals, diagnosis_block, known_unknowns, next_action = cache_leak
                        else:
                            integration_validation_error = _integration_artifact_validation_error(run=run)
                            if integration_validation_error is not None:
                                observed_signals, diagnosis_block, known_unknowns, next_action = integration_validation_error
                            else:
                                manifest_lifecycle_error = _run_manifest_attempt_lifecycle_error(run=run)
                                if manifest_lifecycle_error is not None:
                                    observed_signals, diagnosis_block, known_unknowns, next_action = manifest_lifecycle_error
                                else:
                                    runbook_mismatch = _runbook_attempt_evidence_mismatch(run=run)
                                    if runbook_mismatch is not None:
                                        observed_signals, diagnosis_block, known_unknowns, next_action = runbook_mismatch
                                    else:
                                        integration_dirty = _target_dirty_after_integration_apply(
                                            run=run,
                                            live_memory=live_memory,
                                            stderr_text=stderr_text,
                                        )
                                        if integration_dirty is not None:
                                            observed_signals, diagnosis_block, known_unknowns, next_action = integration_dirty
                                        else:
                                            observed_signals, diagnosis_block, known_unknowns, next_action = _analyze_signals(
                                                stderr_text,
                                                stdout_text,
                                                output_events,
                                                artifact_presence,
                                                command=command,
                                                run=run,
                                            )
    if artifact_presence["worker_capsule"]:
        observed_signals.append("worker_capsule_present")
    if artifact_presence["worker_memory"]:
        observed_signals.append("worker_memory_present")
    if not artifact_presence["preflight_stage"]:
        observed_signals.append("preflight_stage_missing")
    if not artifact_presence["final_report_stage"]:
        observed_signals.append("final_report_stage_missing")
    if artifact_presence["wrapper_gate_result"]:
        observed_signals.append("wrapper_gate_result_present")
    if not artifact_presence["preflight_stage"] and diagnosis_block["primary_category"] not in {
        "orchestrator_subprocess_timeout",
        "worker_capsule_path_violation",
        "patchlet_report_schema_violation",
    }:
        next_action = (
            "Inspect the generated prompt artifact and TASK_CONTRACT.md path usage before rerunning the opt-in smoke."
        )

    evidence_paths = {
        "stdout": relative_to_repo(ctx.root, stdout_path) if stdout_path else None,
        "stderr": relative_to_repo(ctx.root, stderr_path) if stderr_path else None,
        "output_jsonl": relative_to_repo(ctx.root, output_jsonl_path) if output_jsonl_path else None,
        "command": relative_to_repo(ctx.root, command_path) if command_path else None,
        "progress_jsonl": relative_to_repo(ctx.root, progress_jsonl_path) if progress_jsonl_path else None,
        "run_manifest": relative_to_repo(ctx.root, ctx.paths.run_manifest),
        "prompt_artifact": relative_to_repo(ctx.root, prompt_path) if prompt_path else None,
        "worker_capsule": relative_to_repo(ctx.root, worker_capsule_path) if worker_capsule_path else None,
        "worker_events": relative_to_repo(ctx.root, worker_events_path) if worker_events_path else None,
        "wrapper_gate_result": relative_to_repo(ctx.root, wrapper_gate_path) if wrapper_gate_path else None,
    }

    diagnosis = {
        "schema_version": "1.0",
        "kind": "real_codex_failure_diagnosis",
        "patchlet_id": run["patchlet_id"],
        "attempt_id": attempt_id,
        "worker_mode": "real_codex",
        "execution_mode": run.get("execution_mode", "direct"),
        "outcome": outcome,
        "worker_failure": {
            "type": run.get("worker_failure", {}).get("type"),
            "exit_code": run.get("worker_failure", {}).get("exit_code"),
            "message": run.get("worker_failure", {}).get("message", ""),
        },
        "evidence_paths": evidence_paths,
        "artifact_presence": artifact_presence,
        "observed_signals": observed_signals,
        "diagnosis": diagnosis_block,
        "known_unknowns": known_unknowns,
        "capsule": {
            "worker_capsule_path": evidence_paths["worker_capsule"],
            "worker_memory_dir": relative_to_repo(ctx.root, worker_memory_dir) if worker_memory_dir else None,
            "worker_stage_dir": relative_to_repo(ctx.root, worker_stage_dir) if worker_stage_dir else None,
            "missing_files": [
                name
                for name, present in {
                    "worker_memory/TASK_CONTRACT.md": artifact_presence["task_contract"],
                    "worker_memory/LIVE_MEMORY.json": artifact_presence["live_memory_json"],
                    "worker_stage/00_preflight.md": artifact_presence["preflight_stage"],
                    "worker_stage/05_final_report.md": artifact_presence["final_report_stage"],
                }.items()
                if not present
            ],
            "last_worker_event": worker_events[-1] if worker_events else None,
            "wrapper_gate_result_path": evidence_paths["wrapper_gate_result"],
        },
        "recommended_next_action": next_action,
        "validator_weakening_allowed": False,
        "blind_retry_allowed": False,
    }

    ctx.paths.real_codex_diagnostics_dir.mkdir(parents=True, exist_ok=True)
    base = ctx.paths.real_codex_diagnostics_dir / f"{attempt_id}_diagnosis"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    write_json(json_path, diagnosis)
    md_path.write_text(_markdown_for_diagnosis(diagnosis), encoding="utf-8")
    return {
        "attempt_id": attempt_id,
        "diagnosis_json_path": str(json_path),
        "diagnosis_md_path": str(md_path),
        "diagnosis_primary_category": diagnosis_block["primary_category"],
        "diagnosis_summary": diagnosis_block["summary"],
    }
