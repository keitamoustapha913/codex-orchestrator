from __future__ import annotations

from pathlib import Path
from typing import Any
import os
import subprocess

from codex_orchestrator.jsonio import write_json
from codex_orchestrator.paths import relative_to_repo


def _required_obligation_ids(proof_obligations: dict[str, Any]) -> list[str]:
    return [
        row["obligation_id"]
        for row in proof_obligations.get("obligations", [])
        if row.get("required") is True and row.get("obligation_id")
    ]


def select_patchlet_probe_scope(
    *,
    proof_obligations: dict[str, Any],
    probe_plan: dict[str, Any],
    patchlet: dict[str, Any],
    scope: str = "patchlet",
) -> dict[str, Any]:
    required = _required_obligation_ids(proof_obligations)
    if scope == "workflow":
        selected_obligations = required
    else:
        selected_obligations = [oid for oid in patchlet.get("proof_obligation_ids", []) if oid in required]
        if not selected_obligations:
            selected_obligations = required
    selected_set = set(selected_obligations)
    selected_probes = [
        probe
        for probe in probe_plan.get("probes", [])
        if selected_set & set(probe.get("obligation_ids", []))
    ]
    future = [oid for oid in required if oid not in selected_set]
    return {
        "scope": scope,
        "patchlet_id": patchlet.get("patchlet_id"),
        "work_slice_id": patchlet.get("work_slice_id"),
        "selected_obligation_ids": selected_obligations,
        "not_selected_future_obligation_ids": future,
        "selected_probes": selected_probes,
    }


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
    patchlet: dict[str, Any] | None = None,
    scope: str = "patchlet",
) -> dict[str, Any]:
    gate_dir = workflow_root / "runs" / attempt_id / "gates"
    out_dir = gate_dir / "independent_probe_rerun"
    out_dir.mkdir(parents=True, exist_ok=True)
    probe_results: list[dict[str, Any]] = []
    proven: list[str] = []
    failed_obligations: list[str] = []
    blocked: list[str] = []
    probe_scope = select_patchlet_probe_scope(
        proof_obligations=proof_obligations,
        probe_plan=probe_plan,
        patchlet=patchlet or {"patchlet_id": patchlet_id, "proof_obligation_ids": _required_obligation_ids(proof_obligations)},
        scope=scope,
    )
    for probe in probe_scope["selected_probes"]:
        if probe.get("rerunnable_by_orchestrator") is not True:
            blocked.append(probe["probe_id"])
            failed_obligations.extend(probe.get("obligation_ids", []))
            continue
        row = _run_probe(
            repo_root=repo_root,
            execution_root=execution_root or repo_root,
            out_dir=out_dir,
            probe=probe,
        )
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
                "command": row.get("command") or probe.get("command"),
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
        "work_slice_id": probe_scope.get("work_slice_id"),
        "attempt_id": attempt_id,
        "scope": scope,
        "selected_obligation_ids": probe_scope["selected_obligation_ids"],
        "not_selected_future_obligation_ids": probe_scope["not_selected_future_obligation_ids"],
        "master_prompt_sha256": proof_obligations.get("master_prompt_sha256"),
        "accepted": bool(probe_results) and not failed_obligations and not blocked,
        "probe_results": probe_results,
        "proven_obligation_ids": sorted(set(proven)),
        "failed_probe_ids": [row["probe_id"] for row in probe_results if row.get("passed") is not True],
        "blocked_probe_ids": blocked,
        "failed_obligation_ids": sorted(set(failed_obligations)),
        "unproven_future_obligation_ids": probe_scope["not_selected_future_obligation_ids"],
        "failure_signature": None if not failed_obligations and not blocked else ("probe_not_rerunnable" if blocked else "independent_probe_rerun_failed"),
    }
    write_json(gate_dir / "independent_probe_rerun_result.json", result)
    return result


def _run_probe(*, repo_root: Path, execution_root: Path, out_dir: Path, probe: dict[str, Any]) -> dict[str, Any]:
    probe_id = probe["probe_id"]
    stdout_path = out_dir / f"{probe_id}.stdout.txt"
    stderr_path = out_dir / f"{probe_id}.stderr.txt"
    command = probe.get("command")
    script_path = probe.get("script_path")
    if command:
        proc = subprocess.run(
            command,
            cwd=execution_root,
            env=os.environ.copy(),
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    elif script_path:
        script = execution_root / script_path
        proc = subprocess.run(
            [str(script)],
            cwd=execution_root,
            env=os.environ.copy(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        command = str(script_path)
    elif probe.get("expected_observation", {}).get("type") == "artifact_exists":
        rel_path = probe.get("expected_observation", {}).get("path")
        exists = bool(rel_path) and (execution_root / rel_path).exists()
        stdout_path.write_text("artifact exists\n" if exists else "artifact missing\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return {
            "command": "artifact_exists",
            "exit_code": 0 if exists else 1,
            "passed": exists,
            "expected_value": rel_path,
            "actual_value": "exists" if exists else "missing",
            "stdout_path": relative_to_repo(repo_root, stdout_path),
            "stderr_path": relative_to_repo(repo_root, stderr_path),
        }
    else:
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text("probe has no command, script_path, or supported expected_observation\n", encoding="utf-8")
        return {
            "command": None,
            "exit_code": 1,
            "passed": False,
            "expected_value": probe.get("expected_observation"),
            "actual_value": None,
            "stdout_path": relative_to_repo(repo_root, stdout_path),
            "stderr_path": relative_to_repo(repo_root, stderr_path),
        }
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")
    expected = probe.get("expected_observation") or {}
    passed = proc.returncode == 0
    if expected.get("type") == "stdout_contains":
        passed = passed and str(expected.get("value", "")) in proc.stdout
    return {
        "command": command,
        "exit_code": proc.returncode,
        "passed": passed,
        "expected_value": expected or "exit_code_zero",
        "actual_value": proc.stdout.strip(),
        "stdout_path": relative_to_repo(repo_root, stdout_path),
        "stderr_path": relative_to_repo(repo_root, stderr_path),
    }
