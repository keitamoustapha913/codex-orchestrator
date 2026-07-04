from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from codex_orchestrator.integration_state import ensure_integration_state
from codex_orchestrator.jsonio import write_json
from codex_orchestrator.operator_events import append_operator_event
from codex_orchestrator.paths import relative_to_repo
from codex_orchestrator.semantic_goals import required_structured_criteria
from codex_orchestrator.state import now_iso


def run_semantic_goal_checks(
    *,
    repo_root: Path,
    execution_root: Path | None,
    integration_ref: str | None,
    semantic_goal_spec: dict[str, Any],
    patchlet_id: str | None,
    attempt_id: str | None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    out_dir = repo_root / ".codex-orchestrator" / "semantic_goal_checks"
    out_dir.mkdir(parents=True, exist_ok=True)
    criteria = required_structured_criteria(semantic_goal_spec)
    if semantic_goal_spec.get("semantic_mode") != "structured":
        result = _base_result(repo_root, semantic_goal_spec, patchlet_id, attempt_id, "UNSUPPORTED", "unsupported")
        write_json(out_dir / "semantic_goal_check_result.json", result)
        return result

    append_operator_event(
        repo_root,
        event_type="semantic_goal_check_started",
        severity="info",
        stage="SEMANTIC_GOAL_CHECK",
        summary=f"Started semantic goal check for {patchlet_id or 'workflow'}.",
        patchlet_id=patchlet_id,
        attempt_id=attempt_id,
        artifact_paths=[".codex-orchestrator/semantic_goal_spec.json"],
    )
    checkout_root: Path | None = None
    context_root = execution_root
    execution_context = "execution_root"
    resolved_ref = integration_ref
    try:
        if integration_ref:
            checkout_root = Path(tempfile.mkdtemp(prefix="cxor-semantic-", dir="/tmp")).resolve()
            subprocess.run(
                ["git", "-C", str(repo_root), "worktree", "add", "--detach", str(checkout_root), integration_ref],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            context_root = checkout_root
            execution_context = "integration_ref"
        elif context_root is None:
            state = ensure_integration_state(_Ctx(repo_root))
            resolved_ref = state.get("integration_ref")
            if resolved_ref:
                checkout_root = Path(tempfile.mkdtemp(prefix="cxor-semantic-", dir="/tmp")).resolve()
                subprocess.run(
                    ["git", "-C", str(repo_root), "worktree", "add", "--detach", str(checkout_root), resolved_ref],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                )
                context_root = checkout_root
                execution_context = "integration_ref"
            else:
                context_root = repo_root
                execution_context = "target_root"
        rows: list[dict[str, Any]] = []
        for criterion in criteria:
            rows.append(_run_criterion(repo_root, context_root or repo_root, criterion, out_dir))
        overall = "PASSED" if rows and all(row.get("passed") is True for row in rows) else "FAILED"
        result = _base_result(repo_root, semantic_goal_spec, patchlet_id, attempt_id, overall, execution_context)
        result["integration_ref"] = resolved_ref
        result["criteria"] = rows
        write_json(out_dir / "semantic_goal_check_result.json", result)
        for row in rows:
            append_operator_event(
                repo_root,
                event_type="semantic_goal_check_passed" if row.get("passed") else "semantic_goal_check_failed",
                severity="success" if row.get("passed") else "error",
                stage="SEMANTIC_GOAL_CHECK",
                summary=(
                    f"semantic goal {row['criterion_id']} passed: app.main() returned {json.dumps(row.get('actual_value'))}."
                    if row.get("passed")
                    else f"semantic goal {row['criterion_id']} failed: expected app.main() == {json.dumps(row.get('expected_value'))}, observed {json.dumps(row.get('actual_value'))}."
                ),
                patchlet_id=patchlet_id,
                attempt_id=attempt_id,
                artifact_paths=[".codex-orchestrator/semantic_goal_checks/semantic_goal_check_result.json"],
                details={
                    "criterion_id": row.get("criterion_id"),
                    "kind": row.get("kind"),
                    "expected_value": row.get("expected_value"),
                    "actual_value": row.get("actual_value"),
                    "semantic_goal_check_result_path": ".codex-orchestrator/semantic_goal_checks/semantic_goal_check_result.json",
                },
            )
        return result
    finally:
        if checkout_root is not None:
            subprocess.run(
                ["git", "-C", str(repo_root), "worktree", "remove", "--force", str(checkout_root)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if checkout_root.exists():
                shutil.rmtree(checkout_root)


def _run_criterion(repo_root: Path, context_root: Path, criterion: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    criterion_id = criterion["criterion_id"]
    stdout_path = out_dir / f"{criterion_id}.stdout.txt"
    stderr_path = out_dir / f"{criterion_id}.stderr.txt"
    expected = criterion.get("expected_value")
    script = (
        "import importlib, json, sys\n"
        f"module = importlib.import_module({json.dumps(criterion.get('module_name', 'app'))})\n"
        f"value = getattr(module, {json.dumps(criterion.get('function_name', 'main'))})()\n"
        "print(json.dumps({'actual_value': value}, sort_keys=True))\n"
        f"assert value == {json.dumps(expected)}\n"
    )
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [os.environ.get("PYTHON", sys.executable), "-B", "-c", script],
        cwd=context_root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")
    actual = None
    if proc.stdout.strip():
        try:
            actual = json.loads(proc.stdout.splitlines()[-1]).get("actual_value")
        except Exception:
            actual = None
    return {
        "criterion_id": criterion_id,
        "kind": criterion.get("kind"),
        "target_file": criterion.get("target_file"),
        "module_name": criterion.get("module_name"),
        "function_name": criterion.get("function_name"),
        "expected_value": expected,
        "actual_value": actual,
        "passed": proc.returncode == 0 and actual == expected,
        "command": "PYTHONDONTWRITEBYTECODE=1 python -B -c <orchestrator-owned semantic goal probe>",
        "exit_code": proc.returncode,
        "stdout_path": relative_to_repo(repo_root, stdout_path),
        "stderr_path": relative_to_repo(repo_root, stderr_path),
    }


def _base_result(repo_root: Path, spec: dict[str, Any], patchlet_id: str | None, attempt_id: str | None, status: str, execution_context: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "kind": "semantic_goal_check_result",
        "created_at": now_iso(),
        "workflow_id": spec.get("workflow_id"),
        "run_id": spec.get("run_id"),
        "patchlet_id": patchlet_id,
        "attempt_id": attempt_id,
        "semantic_goal_spec_path": ".codex-orchestrator/semantic_goal_spec.json",
        "execution_context": execution_context,
        "integration_ref": None,
        "overall_status": status,
        "criteria": [],
    }


class _Ctx:
    def __init__(self, root: Path) -> None:
        from codex_orchestrator.paths import build_paths

        self.root = root
        self.paths = build_paths(root)
