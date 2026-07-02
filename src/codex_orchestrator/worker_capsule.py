from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from codex_orchestrator.jsonio import write_json
from codex_orchestrator.patchlet_run_context import PatchletRunContext
from codex_orchestrator.paths import relative_to_repo
from codex_orchestrator.state import now_iso
from codex_orchestrator.target_repo import TargetRepoContext
from codex_orchestrator.validators.schema_validator import validate_json_file


@dataclass(frozen=True)
class WorkerCapsule:
    patchlet_id: str
    attempt_id: str
    run_dir: Path
    worker_memory_dir: Path
    worker_stage_dir: Path
    worker_hooks_dir: Path
    gates_dir: Path
    diagnostics_dir: Path
    manifest_path: Path


REQUIRED_MEMORY_FILES = (
    "TASK_CONTRACT.md",
    "LIVE_MEMORY.md",
    "LIVE_MEMORY.json",
    "KNOWN_FACTS.json",
    "ALLOWED_PATHS.json",
    "PREVIOUS_FAILURES.md",
    "CURRENT_STAGE.md",
    "WRITE_THESE_FILES.md",
)

REQUIRED_STAGE_FILES = (
    "00_preflight.md",
    "01_investigation.md",
    "02_probe_plan.md",
    "03_implementation.md",
    "04_validation.md",
    "05_final_report.md",
)


def build_worker_capsule(run_context: PatchletRunContext, patchlet: dict) -> WorkerCapsule:
    patchlet_id = patchlet["patchlet_id"]
    attempt_id = run_context.run_dir.name
    run_dir = run_context.run_dir.resolve()
    return WorkerCapsule(
        patchlet_id=patchlet_id,
        attempt_id=attempt_id,
        run_dir=run_dir,
        worker_memory_dir=run_dir / "worker_memory",
        worker_stage_dir=run_dir / "worker_stage",
        worker_hooks_dir=run_dir / "worker_hooks",
        gates_dir=run_dir / "gates",
        diagnostics_dir=run_dir / "diagnostics",
        manifest_path=run_dir / "worker_capsule.json",
    )


def write_worker_capsule_manifest(ctx: TargetRepoContext, capsule: WorkerCapsule) -> dict:
    capsule.run_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": "1.0",
        "kind": "worker_capsule",
        "patchlet_id": capsule.patchlet_id,
        "attempt_id": capsule.attempt_id,
        "run_dir": relative_to_repo(ctx.root, capsule.run_dir),
        "worker_memory_dir": relative_to_repo(ctx.root, capsule.worker_memory_dir),
        "worker_stage_dir": relative_to_repo(ctx.root, capsule.worker_stage_dir),
        "worker_hooks_dir": relative_to_repo(ctx.root, capsule.worker_hooks_dir),
        "gates_dir": relative_to_repo(ctx.root, capsule.gates_dir),
        "diagnostics_dir": relative_to_repo(ctx.root, capsule.diagnostics_dir),
    }
    write_json(capsule.manifest_path, data)
    return data


def ensure_worker_capsule(ctx: TargetRepoContext, capsule: WorkerCapsule) -> dict:
    capsule.run_dir.mkdir(parents=True, exist_ok=True)
    capsule.worker_memory_dir.mkdir(parents=True, exist_ok=True)
    capsule.worker_stage_dir.mkdir(parents=True, exist_ok=True)
    capsule.worker_hooks_dir.mkdir(parents=True, exist_ok=True)
    capsule.gates_dir.mkdir(parents=True, exist_ok=True)
    capsule.diagnostics_dir.mkdir(parents=True, exist_ok=True)
    return write_worker_capsule_manifest(ctx, capsule)


def _task_contract_text(
    run_context: PatchletRunContext,
    patchlet: dict,
    *,
    worker_mode: str,
) -> str:
    allowed_file = patchlet.get("allowed_product_runtime_file", "")
    patchlet_id = patchlet["patchlet_id"]
    attempt_id = run_context.run_dir.name
    return (
        "# TASK CONTRACT\n\n"
        f"- patchlet id: `{patchlet_id}`\n"
        f"- attempt id: `{attempt_id}`\n"
        f"- worker mode: `{worker_mode}`\n"
        f"- target root: `{run_context.target_root}`\n"
        f"- execution root: `{run_context.execution_root}`\n"
        f"- artifact root: `{run_context.artifact_root}`\n"
        f"- allowed product/runtime file: `{allowed_file}`\n"
        f"- required report path: `.codex-orchestrator/reports/{patchlet_id}.json`\n"
        f"- required probe root: `.artifacts/probes/{patchlet_id}`\n"
        f"- required stage files: `worker_stage/00_preflight.md`, `worker_stage/05_final_report.md`\n"
        "- required final status marker: `FINAL_STATUS: PASS` or explicit failure/blocking status\n"
        "- forbidden edit paths: any product/runtime file other than the allowed file; do not edit orchestrator source paths\n"
        "- root-cause/probe contract reminder: direct probe first, then minimal fix, then deterministic proof and negative controls\n"
        "- no blind retry rule: blind retry is not allowed\n"
        "- orchestrator owns gate results: Codex may not write or overwrite gate result files\n"
    )


def _live_memory_json(run_context: PatchletRunContext, patchlet: dict) -> dict:
    patchlet_id = patchlet["patchlet_id"]
    return {
        "schema_version": "1.0",
        "kind": "worker_memory",
        "patchlet_id": patchlet_id,
        "attempt_id": run_context.run_dir.name,
        "allowed_product_runtime_file": patchlet.get("allowed_product_runtime_file"),
        "goal_ids": patchlet.get("master_goal_ids", []),
        "invariant_ids": patchlet.get("invariant_ids", []),
        "evidence_ids": patchlet.get("evidence_ids", []),
        "graph_node_ids": patchlet.get("graph_node_ids", []),
        "required_report_path": f".codex-orchestrator/reports/{patchlet_id}.json",
        "required_probe_root": f".artifacts/probes/{patchlet_id}",
        "current_stage": "worker_initialized",
        "known_facts": [],
        "previous_failures": patchlet.get("source_failure_ids", []),
        "open_questions": [],
    }


def _allowed_paths_json(run_context: PatchletRunContext, patchlet: dict) -> dict:
    return {
        "schema_version": "1.0",
        "kind": "allowed_paths",
        "patchlet_id": patchlet["patchlet_id"],
        "attempt_id": run_context.run_dir.name,
        "allowed_product_runtime_files": [patchlet.get("allowed_product_runtime_file")],
        "allowed_artifact_roots": [
            ".codex-orchestrator/reports",
            ".codex-orchestrator/runs",
            ".artifacts/probes",
        ],
        "forbidden_roots": [
            ".git",
            ".codex-orchestrator/gates",
        ],
    }


def ensure_worker_memory(
    ctx: TargetRepoContext,
    capsule: WorkerCapsule,
    run_context: PatchletRunContext,
    patchlet: dict,
    *,
    worker_mode: str,
) -> None:
    live_memory = _live_memory_json(run_context, patchlet)
    allowed_paths = _allowed_paths_json(run_context, patchlet)
    task_contract_path = capsule.worker_memory_dir / "TASK_CONTRACT.md"
    task_contract_path.write_text(
        _task_contract_text(run_context, patchlet, worker_mode=worker_mode),
        encoding="utf-8",
    )
    write_json(capsule.worker_memory_dir / "LIVE_MEMORY.json", live_memory)
    (capsule.worker_memory_dir / "LIVE_MEMORY.md").write_text(
        "# LIVE MEMORY\n\n"
        f"- patchlet: `{patchlet['patchlet_id']}`\n"
        f"- attempt: `{run_context.run_dir.name}`\n"
        f"- allowed file: `{patchlet.get('allowed_product_runtime_file')}`\n"
        f"- report path: `{live_memory['required_report_path']}`\n"
        f"- probe root: `{live_memory['required_probe_root']}`\n",
        encoding="utf-8",
    )
    write_json(capsule.worker_memory_dir / "KNOWN_FACTS.json", {
        "schema_version": "1.0",
        "kind": "known_facts",
        "patchlet_id": patchlet["patchlet_id"],
        "attempt_id": run_context.run_dir.name,
        "facts": [],
    })
    write_json(capsule.worker_memory_dir / "ALLOWED_PATHS.json", allowed_paths)
    (capsule.worker_memory_dir / "PREVIOUS_FAILURES.md").write_text(
        "# PREVIOUS FAILURES\n\n"
        + ("\n".join(f"- `{failure_id}`" for failure_id in patchlet.get("source_failure_ids", [])) or "- none")
        + "\n",
        encoding="utf-8",
    )
    (capsule.worker_memory_dir / "CURRENT_STAGE.md").write_text(
        "# CURRENT STAGE\n\nworker_initialized\n",
        encoding="utf-8",
    )
    (capsule.worker_memory_dir / "WRITE_THESE_FILES.md").write_text(
        "# WRITE THESE FILES\n\n"
        "- `worker_stage/00_preflight.md`\n"
        "- `worker_stage/05_final_report.md`\n"
        f"- `.codex-orchestrator/reports/{patchlet['patchlet_id']}.json`\n"
        f"- `.artifacts/probes/{patchlet['patchlet_id']}/...`\n",
        encoding="utf-8",
    )


def ensure_worker_stage_templates(
    capsule: WorkerCapsule,
    run_context: PatchletRunContext,
    patchlet: dict,
) -> None:
    allowed_file = patchlet.get("allowed_product_runtime_file", "")
    patchlet_id = patchlet["patchlet_id"]
    report_path = f".codex-orchestrator/reports/{patchlet_id}.json"
    probe_root = f".artifacts/probes/{patchlet_id}"

    templates = {
        "00_preflight.md": (
            "# Worker Preflight\n\n"
            "Restate the execution contract before editing anything.\n\n"
            f"- Allowed product/runtime file: `{allowed_file}`\n"
            "- Forbidden files: any product/runtime file outside the allowed boundary\n"
            f"- Report path: `{report_path}`\n"
            f"- Probe path: `{probe_root}`\n"
            f"- Current state: `{run_context.run_dir.name}` started\n"
            f"- Patchlet goal: `{patchlet_id}` must satisfy its scoped invariant slice\n"
            "- Required validators: diff guard, report validation, durable probe validation, wrapper gate\n"
        ),
        "01_investigation.md": (
            "# Investigation\n\n"
            "Capture the minimum grounded observations before changing code.\n"
        ),
        "02_probe_plan.md": (
            "# Probe Plan\n\n"
            "Define the direct proof plan before implementation.\n\n"
            "- Minimal reproduction\n"
            "- Deterministic run count\n"
            "- Controlled initial state\n"
            "- Producer -> transformer -> consumer boundary\n"
            "- Negative control\n"
            "- Cleanup proof\n"
        ),
        "03_implementation.md": (
            "# Implementation\n\n"
            "Record the smallest allowed change applied inside the execution root.\n"
        ),
        "04_validation.md": (
            "# Validation\n\n"
            "Record what was validated, what remains unvalidated, and any blocked checks.\n"
        ),
        "05_final_report.md": (
            "# Final Report\n\n"
            "State the terminal worker claim explicitly.\n\n"
            "- FINAL_STATUS: PASS\n"
            "- Or provide an explicit failure or blocking status with evidence.\n"
        ),
    }
    for filename, content in templates.items():
        (capsule.worker_stage_dir / filename).write_text(content, encoding="utf-8")


def append_worker_event(
    ctx: TargetRepoContext,
    capsule: WorkerCapsule,
    run_context: PatchletRunContext,
    *,
    event: str,
    worker_mode: str,
    details: dict | None = None,
) -> None:
    payload = {
        "schema_version": "1.0",
        "kind": "worker_event",
        "event": event,
        "patchlet_id": capsule.patchlet_id,
        "attempt_id": capsule.attempt_id,
        "worker_mode": worker_mode,
        "execution_mode": "worktree" if run_context.is_worktree else "direct",
        "worker_capsule_manifest": relative_to_repo(ctx.root, capsule.manifest_path),
        "created_at": now_iso(),
    }
    if details:
        payload.update(details)
    events_path = capsule.worker_hooks_dir / "events.jsonl"
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _extract_final_status_claim(capsule: WorkerCapsule) -> str | None:
    final_report_path = capsule.worker_stage_dir / "05_final_report.md"
    if not final_report_path.exists():
        return None
    for raw_line in final_report_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("FINAL_STATUS:"):
            return line.split(":", 1)[1].strip() or None
    return None


def write_wrapper_gate_result(
    ctx: TargetRepoContext,
    capsule: WorkerCapsule,
    run_context: PatchletRunContext,
    *,
    worker_mode: str,
    worker_exit_ok: bool,
    diff_allowed: bool | None,
    report_valid: bool | None,
    probe_valid: bool | None,
    next_state: str,
    report_path: Path | None = None,
    reasons: list[str] | None = None,
) -> dict:
    artifact_gate = "pass"
    memory_gate = "pass"
    stage_gate = "pass"
    reason_list = list(reasons or [])

    if not capsule.manifest_path.exists():
        artifact_gate = "fail"
        reason_list.append("missing worker_capsule.json")

    for filename in REQUIRED_MEMORY_FILES:
        if not (capsule.worker_memory_dir / filename).exists():
            memory_gate = "fail"
            reason_list.append(f"missing worker_memory/{filename}")
    if (capsule.worker_memory_dir / "LIVE_MEMORY.json").exists():
        if validate_json_file(capsule.worker_memory_dir / "LIVE_MEMORY.json", "worker_memory.schema.json"):
            memory_gate = "fail"
            reason_list.append("invalid worker_memory/LIVE_MEMORY.json")
    if (capsule.worker_memory_dir / "ALLOWED_PATHS.json").exists():
        if validate_json_file(capsule.worker_memory_dir / "ALLOWED_PATHS.json", "allowed_paths.schema.json"):
            memory_gate = "fail"
            reason_list.append("invalid worker_memory/ALLOWED_PATHS.json")

    for filename in REQUIRED_STAGE_FILES:
        if not (capsule.worker_stage_dir / filename).exists():
            stage_gate = "fail"
            reason_list.append(f"missing worker_stage/{filename}")

    final_status_claim = _extract_final_status_claim(capsule)
    final_status_gate = "present" if final_status_claim else "missing"
    if final_status_claim is None:
        stage_gate = "fail"
        reason_list.append("missing worker_stage/05_final_report.md FINAL_STATUS marker")

    if report_valid is True and report_path is not None and not report_path.exists():
        artifact_gate = "fail"
        reason_list.append("missing report")

    data = {
        "schema_version": "1.0",
        "kind": "wrapper_gate_result",
        "patchlet_id": capsule.patchlet_id,
        "attempt_id": capsule.attempt_id,
        "worker_mode": worker_mode,
        "execution_mode": "worktree" if run_context.is_worktree else "direct",
        "accepted": bool(worker_exit_ok and artifact_gate == "pass" and memory_gate == "pass" and stage_gate == "pass" and diff_allowed is not False and report_valid is not False and probe_valid is not False),
        "worker_exit_gate": "pass" if worker_exit_ok else "fail",
        "artifact_gate": artifact_gate,
        "memory_gate": memory_gate,
        "stage_gate": stage_gate,
        "diff_gate": "pass" if diff_allowed is True else ("fail" if diff_allowed is False else "not_run"),
        "report_gate": "pass" if report_valid is True else ("fail" if report_valid is False else "not_run"),
        "probe_gate": "pass" if probe_valid is True else ("fail" if probe_valid is False else "not_run"),
        "final_status_gate": final_status_gate,
        "final_status_claim": final_status_claim,
        "reasons": reason_list,
        "next_state": next_state,
        "blind_retry_allowed": False,
        "validator_weakening_allowed": False,
        "worker_capsule_manifest": relative_to_repo(ctx.root, capsule.manifest_path),
    }
    write_json(capsule.gates_dir / "wrapper_gate_result.json", data)
    return data
