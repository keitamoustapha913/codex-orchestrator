from __future__ import annotations

import json
from pathlib import Path

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.patchlet_run_context import PatchletRunContext
from codex_orchestrator.target_repo import TargetRepoContext

from .base import Worker, WorkerResult, ensure_run_context


def _default_report(patchlet: dict) -> dict:
    pid = patchlet["patchlet_id"]
    semantic_goal_results = []
    behavior = patchlet.get("expected_behavior") or {}
    criteria = patchlet.get("semantic_criteria") or []
    if behavior.get("kind") == "python_module_function_returns":
        expected = behavior.get("expected_value")
        semantic_goal_results.append({
            "criterion_id": criteria[0] if criteria else "SGC001",
            "kind": "python_module_function_returns",
            "expected_value": expected,
            "actual_value": expected,
            "passed": True,
            "probe_artifact_ref": {"path": f".artifacts/probes/{pid}/run_001/semantic_goal_result.json"},
        })
    return {
        "schema_version": "1.0",
        "kind": "task_worker_completion_handoff",
        "patchlet_id": pid,
        "status": "VERIFIED_NO_CHANGE_NEEDED",
        "probe_commands": [f"python .artifacts/probes/{pid}/probe.py"],
        "deterministic_run_counts": {"baseline": "5/5", "proof_of_fix": "5/5", "negative_controls": "5/5"},
        "root_cause_classification": {
            "observed_failure": "minimal direct probe passed before implementation",
            "immediate_cause": "no change required",
            "why_immediate_cause_happened": "target behavior already satisfies this patchlet",
            "deeper_owner_boundary": patchlet.get("allowed_product_runtime_file"),
            "producer_transformer_consumer_boundary": "direct probe -> target runtime boundary",
            "not_downstream_of_unprobed_state_proof": "probe executed directly against target boundary",
            "negative_control_proof": "negative controls passed deterministically",
            "recursive_why_audit": [
                "Why did the behavior appear change-worthy? Probe-driven investigation suggested no persistent runtime defect.",
                "Why is the owner boundary sufficient? The allowed file defines the immediate runtime boundary under test.",
                "Why is the mock result bounded? The mock worker only edits the allowed product/runtime file or durable artifacts.",
            ],
        },
        "before_after_state": [{"before": "satisfying", "after": "satisfying"}],
        "row_ledger": [],
        "trace_ledger": [],
        "cleanup_proof": "mock probe writes no persistent product state",
        "semantic_goal_results": semantic_goal_results,
    }


def _final_status_for_report(report_status: str) -> str:
    if report_status in {"COMPLETE", "VERIFIED_NO_CHANGE_NEEDED"}:
        return "PASS"
    if report_status == "BLOCKED_WITH_EVIDENCE":
        return "BLOCKED"
    return "FAILED"


def _write_final_report_stage(run_ctx: PatchletRunContext, patchlet: dict, report_status: str) -> None:
    final_report = run_ctx.run_dir / "worker_stage" / "05_final_report.md"
    final_report.parent.mkdir(parents=True, exist_ok=True)
    final_report.write_text(
        "# Final Report\n\n"
        f"- Patchlet: `{patchlet['patchlet_id']}`\n"
        f"FINAL_STATUS: {_final_status_for_report(report_status)}\n"
        f"- Worker report status: `{report_status}`\n",
        encoding="utf-8",
    )


def _write_probe_run_artifacts(run_ctx: PatchletRunContext, patchlet: dict) -> None:
    patchlet_id = patchlet["patchlet_id"]
    probe_ids = sorted(set(patchlet.get("probe_ids") or []))
    probe_id = probe_ids[0] if probe_ids else patchlet_id
    probe_root = run_ctx.worker_evidence_dir / probe_id
    probe_root.mkdir(parents=True, exist_ok=True)
    probe = probe_root / "probe.py"
    probe.write_text("print('mock probe passed')\n", encoding="utf-8")

    run_root = probe_root / "run_001"
    run_root.mkdir(parents=True, exist_ok=True)
    files_and_contents = {
        "row_ledger.jsonl": json.dumps({"row": 1}) + "\n",
        "trace_ledger.jsonl": json.dumps({"trace": 1}) + "\n",
        "before_state.json": json.dumps({"state": "before"}) + "\n",
        "after_state.json": json.dumps({"state": "after"}) + "\n",
        "cleanup_proof.json": json.dumps({"cleanup_passed": True}) + "\n",
        "semantic_goal_result.json": json.dumps({"mock": "semantic"}) + "\n",
    }
    for name, content in files_and_contents.items():
        path = run_root / name
        path.write_text(content, encoding="utf-8")


def _structured_python_return_content(patchlet: dict) -> str | None:
    behavior = patchlet.get("expected_behavior") or {}
    if behavior.get("kind") != "python_module_function_returns":
        return None
    if behavior.get("target_file") != patchlet.get("allowed_product_runtime_file"):
        return None
    if behavior.get("module_name") != "app" or behavior.get("function_name") != "main":
        return None
    return f"def main():\n    return {behavior.get('expected_value')!r}\n"


class MockWorker(Worker):
    def run_patchlet(
        self,
        ctx: TargetRepoContext,
        patchlet: dict,
        *,
        run_dir: Path | None = None,
        run_ctx: PatchletRunContext | None = None,
    ) -> WorkerResult:
        pid = patchlet["patchlet_id"]
        run_ctx = ensure_run_context(ctx, patchlet=patchlet, run_dir=run_dir, run_ctx=run_ctx)
        run_dir = run_ctx.run_dir
        scenario_path = run_ctx.workflow_dir / "mock" / "next_patchlet_result.json"
        scenario = read_json(scenario_path) if scenario_path.exists() else {}

        for rel, content in scenario.get("unauthorized_files", {}).items():
            path = run_ctx.execution_root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        if scenario.get("change_allowed_product"):
            product = run_ctx.execution_root / patchlet["allowed_product_runtime_file"]
            with product.open("a", encoding="utf-8") as fh:
                fh.write("\n# cxor mock allowed product change\n")
        if scenario.get("allowed_product_content") is not None:
            product = run_ctx.execution_root / patchlet["allowed_product_runtime_file"]
            product.write_text(str(scenario["allowed_product_content"]), encoding="utf-8")
        semantic_content = _structured_python_return_content(patchlet)
        if semantic_content is not None and scenario.get("change_allowed_product"):
            semantic_content += "\n# cxor mock allowed product change\n"
        semantic_autofix_applied = False
        if (
            semantic_content is not None
            and not scenario.get("disable_semantic_autofix")
            and not scenario.get("force_failed_report")
            and scenario.get("allowed_product_content") is None
        ):
            product = run_ctx.execution_root / patchlet["allowed_product_runtime_file"]
            before = product.read_text(encoding="utf-8") if product.exists() else None
            if before != semantic_content:
                product.write_text(semantic_content, encoding="utf-8")
                semantic_autofix_applied = True

        _write_probe_run_artifacts(run_ctx, patchlet)
        extra_evidence_count = int(scenario.get("extra_worker_evidence_file_count") or 0)
        if extra_evidence_count:
            probe_id = sorted(set(patchlet.get("probe_ids") or []))[0]
            extra_root = run_ctx.worker_evidence_dir / probe_id / "run_001" / "zz-overflow"
            extra_root.mkdir(parents=True, exist_ok=True)
            for index in range(extra_evidence_count):
                (extra_root / f"evidence-{index:02d}.txt").write_text(
                    f"diagnostic {index}\n",
                    encoding="utf-8",
                )

        report = _default_report(patchlet)
        if scenario.get("status") == "COMPLETE" or semantic_autofix_applied:
            report["status"] = "COMPLETE"
        report.update(scenario.get("handoff_override", {}))
        if scenario.get("force_failed_report"):
            report["status"] = "FAILED_WITH_EVIDENCE"
            report["failed_probe_evidence"] = "mock failure requested by scenario"
            report["root_cause_classification"]["observed_failure"] = "mock failure requested"

        report_path = run_ctx.task_completion_handoff_path(pid)
        write_json(report_path, report)
        if scenario.get("report_production_override") is not None:
            write_json(
                run_dir / "mock_report_production_override.json",
                scenario["report_production_override"],
            )
        _write_final_report_stage(run_ctx, patchlet, report["status"])
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "output.jsonl").write_text(json.dumps({"mock": True, "patchlet_id": pid}) + "\n", encoding="utf-8")
        if scenario.get("consume_after_run") and scenario_path.exists():
            scenario_path.unlink()
        return WorkerResult(exit_code=0, stdout="mock worker completed", stderr="", report_path=report_path)
