from __future__ import annotations

import json
from pathlib import Path
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

    combined_output = "\n".join([stdout_text, stderr_text] + [json.dumps(event, sort_keys=True) for event in output_events]).strip()

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

    if _contains_any(combined_output, ["network", "api", "rate limit", "timeout", "connection", "model unavailable"]):
        observed_signals.append("captured_output_contains_network_or_api_error")
        supported_by.extend(["stderr.txt" if stderr_text else "output.jsonl"])
        return (
            observed_signals,
            {
                "primary_category": "network_or_api_error",
                "confidence": "medium",
                "summary": "captured stderr or output.jsonl contains network, API, timeout, or model availability error text.",
                "supported_by": sorted(set(supported_by)),
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
    output_events = _load_jsonl_events(output_jsonl_path)
    worker_events = _load_jsonl_events(worker_events_path)
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
    if not artifact_presence["preflight_stage"] and diagnosis_block["primary_category"] != "orchestrator_subprocess_timeout":
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
