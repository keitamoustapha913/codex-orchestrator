from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import write_json
from codex_orchestrator.paths import relative_to_repo
from codex_orchestrator.semantic_goal_runner import run_semantic_goal_checks
from codex_orchestrator.semantic_goals import load_semantic_goal_spec


def run_independent_probe_rerun_gate(
    *,
    repo_root: Path,
    workflow_root: Path,
    attempt_id: str,
    patchlet_id: str,
    proof_obligations: dict[str, Any],
    probe_plan: dict[str, Any],
    integration_ref: str | None,
    execution_root: Path | None,
) -> dict[str, Any]:
    gate_dir = workflow_root / "runs" / attempt_id / "gates"
    out_dir = gate_dir / "independent_probe_rerun"
    out_dir.mkdir(parents=True, exist_ok=True)
    semantic_spec = load_semantic_goal_spec(repo_root)
    probe_results: list[dict[str, Any]] = []
    proven: list[str] = []
    failed_obligations: list[str] = []
    blocked: list[str] = []
    check = run_semantic_goal_checks(
        repo_root=repo_root,
        execution_root=execution_root,
        integration_ref=integration_ref,
        semantic_goal_spec=semantic_spec or {"semantic_mode": "unsupported", "criteria": []},
        patchlet_id=patchlet_id,
        attempt_id=attempt_id,
    )
    rows = check.get("criteria", [])
    for probe in probe_plan.get("probes", []):
        if probe.get("rerunnable_by_orchestrator") is not True:
            blocked.append(probe["probe_id"])
            failed_obligations.extend(probe.get("obligation_ids", []))
            continue
        row = rows[0] if rows else {}
        stdout_path = row.get("stdout_path")
        stderr_path = row.get("stderr_path")
        passed = row.get("passed") is True
        obligation_ids = probe.get("obligation_ids", [])
        if passed:
            proven.extend(obligation_ids)
        else:
            failed_obligations.extend(obligation_ids)
        probe_results.append(
            {
                "probe_id": probe["probe_id"],
                "obligation_ids": obligation_ids,
                "command": probe.get("command"),
                "execution_context": probe.get("execution_context"),
                "exit_code": row.get("exit_code", 1),
                "passed": passed,
                "expected_actual": {
                    "expected": row.get("expected_value"),
                    "actual": row.get("actual_value"),
                },
                "stdout_path": stdout_path or relative_to_repo(repo_root, out_dir / f"{probe['probe_id']}.stdout.txt"),
                "stderr_path": stderr_path or relative_to_repo(repo_root, out_dir / f"{probe['probe_id']}.stderr.txt"),
            }
        )
    result = {
        "schema_version": "1.0",
        "kind": "independent_probe_rerun_result",
        "workflow_id": proof_obligations.get("workflow_id"),
        "run_id": proof_obligations.get("run_id"),
        "patchlet_id": patchlet_id,
        "attempt_id": attempt_id,
        "master_prompt_sha256": proof_obligations.get("master_prompt_sha256"),
        "accepted": bool(probe_results) and not failed_obligations and not blocked,
        "probe_results": probe_results,
        "proven_obligation_ids": sorted(set(proven)),
        "failed_probe_ids": [row["probe_id"] for row in probe_results if row.get("passed") is not True],
        "blocked_probe_ids": blocked,
        "failed_obligation_ids": sorted(set(failed_obligations)),
        "failure_signature": None if not failed_obligations and not blocked else ("probe_not_rerunnable" if blocked else "independent_probe_rerun_failed"),
    }
    write_json(gate_dir / "independent_probe_rerun_result.json", result)
    return result
