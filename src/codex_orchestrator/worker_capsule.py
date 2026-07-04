from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path

from codex_orchestrator.codex_execution_policy import resolve_patchlet_timeout_seconds, soft_deadline_seconds
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
    "SEMANTIC_GOAL_CONTRACT.md",
    "REPORT_SCHEMA_CONTRACT.md",
    "FINAL_REPORT_CONTRACT.md",
    "PYTHON_RUNTIME_SIDE_EFFECT_CONTRACT.md",
    "LIVE_MEMORY.md",
    "LIVE_MEMORY.json",
    "KNOWN_FACTS.json",
    "ALLOWED_PATHS.json",
    "PREVIOUS_FAILURES.md",
    "CURRENT_STAGE.md",
    "WRITE_THESE_FILES.md",
)

ALLOWED_REPORT_STATUSES = (
    "COMPLETE",
    "VERIFIED_NO_CHANGE_NEEDED",
    "BLOCKED_WITH_EVIDENCE",
    "FAILED_WITH_EVIDENCE",
)

FORBIDDEN_REPORT_STATUSES = (
    "FIXED",
    "DONE",
    "SUCCESS",
    "PASSED",
    "OK",
)

FINAL_STATUS_VALUES = (
    "PASS",
    "BLOCKED",
    "FAILED",
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


def _minimal_report_skeleton(patchlet_id: str) -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "kind": "patchlet_report",
            "patchlet_id": patchlet_id,
            "status": "VERIFIED_NO_CHANGE_NEEDED",
            "final_status_marker": "FINAL_STATUS: PASS",
            "changed_product_runtime_file": None,
            "changed_artifact_files": [],
            "probe_commands": [],
            "deterministic_run_counts": {
                "baseline": "5/5",
                "proof_of_fix": "5/5",
                "negative_controls": "5/5",
            },
            "root_cause_classification": {
                "observed_failure": "",
                "immediate_cause": "",
                "why_immediate_cause_happened": "",
                "deeper_owner_boundary": "",
                "producer_transformer_consumer_boundary": "",
                "not_downstream_of_unprobed_state_proof": "",
                "negative_control_proof": "",
                "recursive_why_audit": [],
            },
            "before_after_state": [],
            "row_ledger": [],
            "trace_ledger": [],
            "cleanup_proof": "cleanup passed; no transient files remain",
            "probe_artifact_refs": [
                {
                    "patchlet_id": patchlet_id,
                    "probe_root": f".artifacts/probes/{patchlet_id}",
                    "run_id": "default",
                    "files": [
                        {
                            "path": f".artifacts/probes/{patchlet_id}/summary.json",
                            "kind": "summary",
                            "sha256": "<sha256>",
                            "size_bytes": 123,
                        }
                    ],
                }
            ],
            "semantic_goal_results": [],
            "acceptance_criteria_result": "pass",
        },
        indent=2,
    )


def _semantic_contract_report_section(patchlet: dict | None = None) -> str:
    criteria = (patchlet or {}).get("expected_behavior")
    criterion_ids = (patchlet or {}).get("semantic_criteria") or []
    if not criteria or criteria.get("kind") != "python_module_function_returns":
        return ""
    criterion_id = criterion_ids[0] if criterion_ids else "SGC001"
    expected = criteria.get("expected_value")
    return (
        "## semantic_goal_results\n\n"
        "When semantic_goal_spec.json has required criteria, the report must include semantic_goal_results.\n\n"
        f"For {criterion_id}:\n\n"
        "Expected:\n"
        f"  {criteria.get('module_name')}.{criteria.get('function_name')}() == {expected!r}\n\n"
        "Valid passing entry:\n"
        "```json\n"
        "{\n"
        f"  \"criterion_id\": \"{criterion_id}\",\n"
        "  \"kind\": \"python_module_function_returns\",\n"
        f"  \"expected_value\": {json.dumps(expected)},\n"
        f"  \"actual_value\": {json.dumps(expected)},\n"
        "  \"passed\": true\n"
        "}\n"
        "```\n\n"
        "Invalid for this goal:\n"
        "```json\n"
        "{\n"
        f"  \"criterion_id\": \"{criterion_id}\",\n"
        f"  \"expected_value\": {json.dumps(expected)},\n"
        "  \"actual_value\": \"ok\",\n"
        "  \"passed\": true\n"
        "}\n"
        "```\n\n"
        f"If actual_value is \"ok\" and expected_value is {json.dumps(expected)}, passed must be false.\n\n"
    )


def report_schema_contract_text(*, patchlet_id: str, report_path: str, patchlet: dict | None = None) -> str:
    allowed = "\n".join(f"- {status}" for status in ALLOWED_REPORT_STATUSES)
    forbidden = "\n".join(f"- {status}" for status in FORBIDDEN_REPORT_STATUSES)
    return (
        "# REPORT SCHEMA CONTRACT\n\n"
        "## Required report path\n\n"
        f"Write the patchlet report JSON to `{report_path}`.\n\n"
        "## Allowed status values\n\n"
        f"{allowed}\n\n"
        "## Forbidden status values\n\n"
        f"{forbidden}\n\n"
        "Never invent new statuses. Never use `FIXED`.\n\n"
        "## Required top-level fields\n\n"
        "- schema_version\n"
        "- kind\n"
        "- patchlet_id\n"
        "- status\n"
        "- final_status_marker\n"
        "- changed_product_runtime_file\n"
        "- changed_artifact_files\n"
        "- probe_commands\n"
        "- deterministic_run_counts\n"
        "- root_cause_classification\n"
        "- before_after_state\n"
        "- row_ledger\n"
        "- trace_ledger\n"
        "- cleanup_proof\n"
        "- probe_artifact_refs\n"
        "- acceptance_criteria_result\n\n"
        "## Required type reminders\n\n"
        "- `cleanup_proof` must be a string, not an object.\n"
        "- `changed_product_runtime_file` must be present and must be a string or null.\n"
        "- Use the allowed product/runtime path string when exactly one product file changed.\n"
        "- Use null when no product/runtime file changed.\n"
        "- `deterministic_run_counts` must be present.\n"
        "- `before_after_state` must be present.\n"
        "- `row_ledger` must be present.\n"
        "- `trace_ledger` must be present.\n"
        "- `probe_artifact_refs` entries must be objects, never string-only paths.\n\n"
        "## probe_artifact_refs MUST be object entries\n\n"
        "Do not write probe_artifact_refs as strings.\n\n"
        "Invalid:\n\n"
        "```json\n"
        "\"probe_artifact_refs\": [\n"
        f"  \".artifacts/probes/{patchlet_id}/comparison.txt\"\n"
        "]\n"
        "```\n\n"
        "Valid:\n\n"
        "```json\n"
        "\"probe_artifact_refs\": [\n"
        "  {\n"
        f"    \"patchlet_id\": \"{patchlet_id}\",\n"
        f"    \"probe_root\": \".artifacts/probes/{patchlet_id}\",\n"
        "    \"run_id\": \"default\",\n"
        "    \"files\": [\n"
        "      {\n"
        f"        \"path\": \".artifacts/probes/{patchlet_id}/comparison.txt\",\n"
        "        \"kind\": \"comparison\",\n"
        "        \"sha256\": \"<sha256>\",\n"
        "        \"size_bytes\": 123\n"
        "      }\n"
        "    ]\n"
        "  }\n"
        "]\n"
        "```\n\n"
        "Nested run example:\n\n"
        "```json\n"
        "{\n"
        f"  \"patchlet_id\": \"{patchlet_id}\",\n"
        f"  \"probe_root\": \".artifacts/probes/{patchlet_id}/run_001\",\n"
        "  \"run_id\": \"run_001\",\n"
        "  \"files\": [\n"
        "    {\n"
        f"      \"path\": \".artifacts/probes/{patchlet_id}/run_001/before_state.json\",\n"
        "      \"kind\": \"before_state\",\n"
        "      \"sha256\": \"<sha256>\",\n"
        "      \"size_bytes\": 123\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "```\n\n"
        "If no probe artifacts are produced, use `\"probe_artifact_refs\": []`.\n"
        "If probe artifacts are produced, every entry must be an object, never a string.\n\n"
        f"{_semantic_contract_report_section(patchlet)}"
        "## Minimal valid JSON skeleton\n\n"
        "```json\n"
        f"{_minimal_report_skeleton(patchlet_id)}\n"
        "```\n\n"
        "Use COMPLETE only when you changed the allowed product/runtime file and have proof.\n"
        "Use VERIFIED_NO_CHANGE_NEEDED when probes prove the existing runtime already satisfies the goal.\n"
        "Use BLOCKED_WITH_EVIDENCE when blocked by a real external or policy constraint but evidence exists.\n"
        "Use FAILED_WITH_EVIDENCE when the patchlet failed but evidence exists.\n\n"
        "## Pre-submit checklist\n\n"
        "Before final response, verify the report JSON has:\n"
        "- schema_version\n"
        "- kind\n"
        "- patchlet_id\n"
        "- status\n"
        "- final_status_marker\n"
        "- changed_product_runtime_file\n"
        "- changed_artifact_files\n"
        "- probe_commands\n"
        "- deterministic_run_counts\n"
        "- root_cause_classification\n"
        "- before_after_state\n"
        "- row_ledger\n"
        "- trace_ledger\n"
        "- cleanup_proof\n"
        "- probe_artifact_refs\n"
        "- acceptance_criteria_result\n\n"
        "Verify:\n"
        "- status is one of COMPLETE, VERIFIED_NO_CHANGE_NEEDED, BLOCKED_WITH_EVIDENCE, FAILED_WITH_EVIDENCE\n"
        "- status is not FIXED\n"
        "- cleanup_proof is a string\n"
        "- changed_product_runtime_file exists and is a string or null\n"
        "- JSON parses with python -m json.tool\n"
    )


def final_report_contract_text(*, patchlet_id: str, attempt_id: str, final_report_path: str, report_path: str, probe_root: str) -> str:
    accepted = "\n".join(f"- FINAL_STATUS: {value}" for value in FINAL_STATUS_VALUES)
    return (
        "# FINAL REPORT CONTRACT\n\n"
        "## Required final report path\n\n"
        f"Write the final Markdown report to `{final_report_path}`.\n\n"
        "## Canonical final status line\n\n"
        "The first non-empty line must be a standalone canonical marker beginning at column 1:\n\n"
        "```text\n"
        "FINAL_STATUS: PASS\n"
        "```\n\n"
        "## Accepted final status lines\n\n"
        f"{accepted}\n\n"
        "## Forbidden non-canonical examples\n\n"
        "Do not write:\n\n"
        "```text\n"
        "Marker: `FINAL_STATUS: PASS`\n"
        "`FINAL_STATUS: PASS`\n"
        "The marker is FINAL_STATUS: PASS\n"
        "FINAL_STATUS PASS\n"
        "FINAL_STATUS: OK\n"
        "FINAL_STATUS: SUCCESS\n"
        "```\n\n"
        "Do not wrap the final status marker in backticks.\n"
        "Do not prefix the marker with \"Marker:\".\n"
        "Do not place the marker inside a sentence.\n"
        "The marker must be a standalone line beginning at column 1.\n\n"
        "## Minimal final report template\n\n"
        "```text\n"
        "FINAL_STATUS: PASS\n"
        "\n"
        "# Final Report\n"
        "\n"
        f"- Patchlet: {patchlet_id}\n"
        f"- Attempt: {attempt_id}\n"
        "- Outcome: <one sentence>\n"
        f"- Report JSON: {report_path}\n"
        f"- Probe root: {probe_root}\n"
        "```\n\n"
        "## Pre-submit checklist\n\n"
        "- Verify the first non-empty line is exactly one of the accepted final status lines.\n"
        "- Verify the marker starts at column 1.\n"
        "- Verify the marker is not wrapped in backticks.\n"
        "- Verify the marker is not prefixed by \"Marker:\".\n"
        "- Verify the report JSON was written and follows REPORT_SCHEMA_CONTRACT.md.\n"
    )


def python_runtime_side_effect_contract_text() -> str:
    return (
        "# PYTHON RUNTIME SIDE EFFECT CONTRACT\n\n"
        "- Do not create Python bytecode cache files under $CXOR_TARGET_ROOT.\n"
        "- The worker environment sets PYTHONDONTWRITEBYTECODE=1.\n"
        "- Prefer python -B for any probe that imports target or execution code.\n"
        "- Do not import target-root product/runtime files in a way that writes cache files.\n"
        "- If comparing target-root and execution-root code, use no-bytecode subprocesses.\n"
        "- Durable evidence belongs under .artifacts/probes/ and .codex-orchestrator/ only.\n"
        "- Never leave __pycache__/ or *.pyc under target root.\n"
        "- If a cache artifact appears, report it explicitly in the probe evidence instead of hiding it.\n"
    )


def _execution_root_contract_text(run_context: PatchletRunContext, allowed_file: str) -> str:
    return (
        "There are two roots:\n\n"
        "1. Execution root:\n"
        f"   `$CXOR_EXECUTION_ROOT` = `{run_context.execution_root}`\n"
        "   This is the worktree where product/runtime files are edited.\n\n"
        "2. Target root:\n"
        f"   `$CXOR_TARGET_ROOT` = `{run_context.target_root}`\n"
        "   This is the durable artifact root and original target repo.\n"
        "   Do not edit product/runtime files in this root.\n"
        "   Product/runtime files under target root are read-only to the worker.\n\n"
        f"Allowed product/runtime file: `{allowed_file}`\n"
        f"Allowed product/runtime edit path: `$CXOR_EXECUTION_ROOT/{allowed_file}` (`{run_context.execution_root / allowed_file}`)\n"
        f"Forbidden product/runtime edit path: `$CXOR_TARGET_ROOT/{allowed_file}` (`{run_context.target_root / allowed_file}`)\n"
        "Target-root artifact directories remain writable only for orchestrator evidence under `.codex-orchestrator/` and `.artifacts/probes/`.\n"
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
    timeout_seconds = resolve_patchlet_timeout_seconds(os.environ)
    soft_deadline = soft_deadline_seconds(timeout_seconds)
    worker_stage_dir = run_context.run_dir / "worker_stage"
    preflight_path = worker_stage_dir / "00_preflight.md"
    final_report_path = worker_stage_dir / "05_final_report.md"
    target_root_worker_stage = run_context.target_root / "worker_stage"
    report_contract_path = run_context.run_dir / "worker_memory" / "REPORT_SCHEMA_CONTRACT.md"
    final_report_contract_path = run_context.run_dir / "worker_memory" / "FINAL_REPORT_CONTRACT.md"
    python_contract_path = run_context.run_dir / "worker_memory" / "PYTHON_RUNTIME_SIDE_EFFECT_CONTRACT.md"
    semantic_contract_path = run_context.run_dir / "worker_memory" / "SEMANTIC_GOAL_CONTRACT.md"
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
        f"- report schema contract: `{report_contract_path}`\n"
        f"- final report contract: `{final_report_contract_path}`\n"
        f"- Python runtime side-effect contract: `{python_contract_path}`\n"
        f"- semantic goal contract: `{semantic_contract_path}`\n"
        f"- required probe root: `.artifacts/probes/{patchlet_id}`\n"
        f"- worker stage dir env: `$CXOR_WORKER_STAGE_DIR` = `{worker_stage_dir}`\n"
        f"- required preflight stage file: `$CXOR_WORKER_STAGE_DIR/00_preflight.md` = `{preflight_path}`\n"
        f"- required final stage file: `$CXOR_WORKER_STAGE_DIR/05_final_report.md` = `{final_report_path}`\n"
        f"- forbidden target-root stage dir: `{target_root_worker_stage}/`\n"
        "- required final status marker: a standalone column-1 line: `FINAL_STATUS: PASS`, `FINAL_STATUS: BLOCKED`, or `FINAL_STATUS: FAILED`\n"
        f"- time budget: hard timeout of {timeout_seconds} seconds\n"
        f"- soft deadline: Aim to finish by {soft_deadline} seconds\n"
        "- if blocked near the budget, write `$CXOR_FINAL_REPORT_PATH` with explicit BLOCKED or FAILED status and preserve what you learned\n"
        "- Do not create target-root worker_stage/; all Worker Capsule stage files must stay under `$CXOR_WORKER_STAGE_DIR`\n"
        "- forbidden edit paths: any product/runtime file other than the allowed file; do not edit orchestrator source paths\n\n"
        "## Execution-root edit contract\n\n"
        f"{_execution_root_contract_text(run_context, allowed_file)}\n"
        "- root-cause/probe contract reminder: direct probe first, then minimal fix, then deterministic proof and negative controls\n"
        "- no blind retry rule: blind retry is not allowed\n"
        "- orchestrator owns gate results: Codex may not write or overwrite gate result files\n"
    )


def _semantic_goal_contract_text(patchlet: dict) -> str:
    behavior = patchlet.get("expected_behavior") or {}
    criteria = patchlet.get("semantic_criteria") or []
    if behavior.get("kind") != "python_module_function_returns":
        return (
            "# SEMANTIC GOAL CONTRACT\n\n"
            "- Semantic goal spec: .codex-orchestrator/semantic_goal_spec.json\n"
            "- Semantic mode: unsupported or unavailable for this patchlet.\n"
        )
    criterion_id = criteria[0] if criteria else "SGC001"
    expected = behavior.get("expected_value")
    module = behavior.get("module_name")
    function = behavior.get("function_name")
    return (
        "# SEMANTIC GOAL CONTRACT\n\n"
        "- Semantic goal spec: .codex-orchestrator/semantic_goal_spec.json\n"
        f"- Required criterion: {criterion_id}\n"
        f"- {module}.{function}() expected return value: {expected!r}\n"
        "- VERIFIED_NO_CHANGE_NEEDED is allowed only if the criterion passes before edits.\n"
        "- COMPLETE is allowed only if the criterion passes after edits.\n"
        "- A negative control showing another value is not enough; the positive criterion must pass.\n"
    )


def _semantic_worker_prompt_section(patchlet: dict) -> str:
    behavior = patchlet.get("expected_behavior") or {}
    if behavior.get("kind") != "python_module_function_returns":
        return ""
    expected = behavior.get("expected_value")
    module = behavior.get("module_name")
    function = behavior.get("function_name")
    mismatch = "ok" if expected != "ok" else "not ok"
    return (
        "## Semantic acceptance criteria\n\n"
        f"The current semantic goal is: {module}.{function}() must return {expected!r}.\n\n"
        f"Before reporting VERIFIED_NO_CHANGE_NEEDED, you must prove {module}.{function}() already returns {expected!r}.\n"
        f"Before reporting COMPLETE, you must prove {module}.{function}() returns {expected!r} after your change.\n"
        f"A probe that proves {module}.{function}() returns {mismatch!r} does not satisfy this goal.\n\n"
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
    timeout_seconds = resolve_patchlet_timeout_seconds(os.environ)
    soft_deadline = soft_deadline_seconds(timeout_seconds)
    task_contract_path = capsule.worker_memory_dir / "TASK_CONTRACT.md"
    task_contract_path.write_text(
        _task_contract_text(run_context, patchlet, worker_mode=worker_mode),
        encoding="utf-8",
    )
    report_contract_path = capsule.worker_memory_dir / "REPORT_SCHEMA_CONTRACT.md"
    final_report_contract_path = capsule.worker_memory_dir / "FINAL_REPORT_CONTRACT.md"
    python_contract_path = capsule.worker_memory_dir / "PYTHON_RUNTIME_SIDE_EFFECT_CONTRACT.md"
    semantic_contract_path = capsule.worker_memory_dir / "SEMANTIC_GOAL_CONTRACT.md"
    report_path = f".codex-orchestrator/reports/{patchlet['patchlet_id']}.json"
    final_report_path = f"{capsule.worker_stage_dir / '05_final_report.md'}"
    probe_root = f".artifacts/probes/{patchlet['patchlet_id']}"
    report_contract_path.write_text(
        report_schema_contract_text(
            patchlet_id=patchlet["patchlet_id"],
            report_path=report_path,
            patchlet=patchlet,
        ),
        encoding="utf-8",
    )
    final_report_contract_path.write_text(
        final_report_contract_text(
            patchlet_id=patchlet["patchlet_id"],
            attempt_id=run_context.run_dir.name,
            final_report_path=final_report_path,
            report_path=report_path,
            probe_root=probe_root,
        ),
        encoding="utf-8",
    )
    python_contract_path.write_text(python_runtime_side_effect_contract_text(), encoding="utf-8")
    semantic_contract_path.write_text(_semantic_goal_contract_text(patchlet), encoding="utf-8")
    write_json(capsule.worker_memory_dir / "LIVE_MEMORY.json", live_memory)
    (capsule.worker_memory_dir / "LIVE_MEMORY.md").write_text(
        "# LIVE MEMORY\n\n"
        f"- patchlet: `{patchlet['patchlet_id']}`\n"
        f"- attempt: `{run_context.run_dir.name}`\n"
        f"- allowed file: `{patchlet.get('allowed_product_runtime_file')}`\n"
        f"- report path: `{live_memory['required_report_path']}`\n"
        f"- report schema contract: `{report_contract_path}`\n"
        f"- final report contract: `{final_report_contract_path}`\n"
        f"- Python runtime side-effect contract: `{python_contract_path}`\n"
        f"- semantic goal contract: `{semantic_contract_path}`\n"
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
        f"- `$CXOR_WORKER_STAGE_DIR/00_preflight.md` (`{capsule.worker_stage_dir / '00_preflight.md'}`)\n"
        f"- `$CXOR_WORKER_STAGE_DIR/05_final_report.md` (`{capsule.worker_stage_dir / '05_final_report.md'}`)\n"
        f"- `.codex-orchestrator/reports/{patchlet['patchlet_id']}.json`\n"
        f"- Read and obey `{report_contract_path}` before writing the report.\n"
        f"- Read and obey `{final_report_contract_path}` before writing the final Markdown report.\n"
        f"- Read and obey `{python_contract_path}` before running Python probes.\n"
        f"- Read and obey `{semantic_contract_path}` before claiming semantic success.\n"
        f"- `.artifacts/probes/{patchlet['patchlet_id']}/...`\n"
        + "\n"
        "Product/runtime edits must happen only under `$CXOR_EXECUTION_ROOT`. "
        f"Do not edit `$CXOR_TARGET_ROOT/{patchlet.get('allowed_product_runtime_file')}`.\n\n"
        f"Do not create target-root worker_stage/ at `{ctx.root}/worker_stage/`. "
        "All Worker Capsule stage artifacts must be written under `$CXOR_WORKER_STAGE_DIR`.\n\n"
        f"Time budget: hard timeout of {timeout_seconds} seconds; aim to finish by {soft_deadline} seconds. "
        "If you cannot complete, stop before the hard timeout and write "
        "`$CXOR_FINAL_REPORT_PATH` with explicit BLOCKED or FAILED status. "
        "Preserve what you learned. Do not keep investigating indefinitely. Do not use blind retry.\n",
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
            "FINAL_STATUS: PASS\n\n"
            "# Final Report\n\n"
            "State the terminal worker claim explicitly.\n\n"
            "- Or use `FINAL_STATUS: BLOCKED` or `FINAL_STATUS: FAILED` as a standalone first line with evidence.\n"
            "- Do not write `Marker: `FINAL_STATUS: PASS`` or wrap the marker in backticks.\n"
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


def _extract_final_status_marker(capsule: WorkerCapsule) -> dict:
    final_report_path = capsule.worker_stage_dir / "05_final_report.md"
    if not final_report_path.exists():
        return {
            "claim": None,
            "gate": "missing",
            "marker": None,
            "canonical": False,
            "noncanonical": None,
            "error": "missing_final_status_marker",
            "reason": "missing worker_stage/05_final_report.md FINAL_STATUS marker",
        }
    first_noncanonical: str | None = None
    for raw_line in final_report_path.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("FINAL_STATUS:"):
            claim = raw_line.split(":", 1)[1].strip() or None
            if claim in FINAL_STATUS_VALUES:
                return {
                    "claim": claim,
                    "gate": "present",
                    "marker": raw_line,
                    "canonical": True,
                    "noncanonical": None,
                    "error": None,
                    "reason": None,
                }
            return {
                "claim": claim,
                "gate": "fail",
                "marker": raw_line,
                "canonical": False,
                "noncanonical": None,
                "error": "invalid_final_status_marker_value",
                "reason": f"invalid FINAL_STATUS marker value: {claim}; expected PASS, BLOCKED, or FAILED",
            }
        stripped = raw_line.strip()
        if "FINAL_STATUS:" in stripped or stripped.startswith("FINAL_STATUS "):
            if first_noncanonical is None:
                first_noncanonical = raw_line
    if first_noncanonical is not None:
        return {
            "claim": None,
            "gate": "fail",
            "marker": None,
            "canonical": False,
            "noncanonical": first_noncanonical,
            "error": "noncanonical_final_status_marker",
            "reason": "noncanonical FINAL_STATUS marker found; marker must be a standalone line beginning at column 1",
        }
    return {
        "claim": None,
        "gate": "missing",
        "marker": None,
        "canonical": False,
        "noncanonical": None,
        "error": "missing_final_status_marker",
        "reason": "missing worker_stage/05_final_report.md FINAL_STATUS marker",
    }


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
    semantic_goal_valid: bool | None = None,
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

    final_status = _extract_final_status_marker(capsule)
    final_status_claim = final_status["claim"]
    final_status_gate = final_status["gate"]
    if final_status_gate != "present":
        stage_gate = "fail"
        if final_status["reason"]:
            reason_list.append(final_status["reason"])

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
        "accepted": bool(worker_exit_ok and artifact_gate == "pass" and memory_gate == "pass" and stage_gate == "pass" and diff_allowed is not False and report_valid is not False and probe_valid is not False and semantic_goal_valid is not False),
        "worker_exit_gate": "pass" if worker_exit_ok else "fail",
        "artifact_gate": artifact_gate,
        "memory_gate": memory_gate,
        "stage_gate": stage_gate,
        "diff_gate": "pass" if diff_allowed is True else ("fail" if diff_allowed is False else "not_run"),
        "report_gate": "pass" if report_valid is True else ("fail" if report_valid is False else "not_run"),
        "probe_gate": "pass" if probe_valid is True else ("fail" if probe_valid is False else "not_run"),
        "semantic_goal_gate": "pass" if semantic_goal_valid is True else ("fail" if semantic_goal_valid is False else "not_run"),
        "final_status_gate": final_status_gate,
        "final_status_claim": final_status_claim,
        "final_status_marker": final_status["marker"],
        "final_status_marker_canonical": final_status["canonical"],
        "final_status_marker_noncanonical": final_status["noncanonical"],
        "final_status_marker_error": final_status["error"],
        "reasons": reason_list,
        "next_state": next_state,
        "blind_retry_allowed": False,
        "validator_weakening_allowed": False,
        "worker_capsule_manifest": relative_to_repo(ctx.root, capsule.manifest_path),
    }
    write_json(capsule.gates_dir / "wrapper_gate_result.json", data)
    return data
