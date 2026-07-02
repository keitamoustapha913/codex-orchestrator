from __future__ import annotations

import json
from pathlib import Path

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.target_repo import TargetRepoContext

from .base import Worker, WorkerResult


def _default_report(patchlet: dict) -> dict:
    pid = patchlet["patchlet_id"]
    return {
        "schema_version": "1.0",
        "kind": "patchlet_report",
        "patchlet_id": pid,
        "status": "VERIFIED_NO_CHANGE_NEEDED",
        "changed_product_runtime_file": None,
        "changed_artifact_files": [f".artifacts/probes/{pid}/probe.py"],
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
        },
        "before_after_state": [{"before": "satisfying", "after": "satisfying"}],
        "row_ledger": [],
        "trace_ledger": [],
        "cleanup_proof": "mock probe writes no persistent product state",
        "probe_artifact_refs": [{
            "patchlet_id": pid,
            "probe_root": f".artifacts/probes/{pid}",
            "run_id": "run_001",
        }],
        "acceptance_criteria_result": "pass",
    }


def _write_probe_run_artifacts(ctx: TargetRepoContext, patchlet_id: str) -> list[str]:
    probe_root = ctx.paths.probe_dir / patchlet_id
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
    }
    changed = [f".artifacts/probes/{patchlet_id}/probe.py"]
    for name, content in files_and_contents.items():
        path = run_root / name
        path.write_text(content, encoding="utf-8")
        changed.append(f".artifacts/probes/{patchlet_id}/run_001/{name}")
    return changed


class MockWorker(Worker):
    def run_patchlet(self, ctx: TargetRepoContext, patchlet: dict, *, run_dir: Path) -> WorkerResult:
        pid = patchlet["patchlet_id"]
        scenario_path = ctx.paths.workflow_dir / "mock" / "next_patchlet_result.json"
        scenario = read_json(scenario_path) if scenario_path.exists() else {}

        for rel, content in scenario.get("unauthorized_files", {}).items():
            path = ctx.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        if scenario.get("change_allowed_product"):
            product = ctx.root / patchlet["allowed_product_runtime_file"]
            with product.open("a", encoding="utf-8") as fh:
                fh.write("\n# cxor mock allowed product change\n")

        changed_probe_artifacts = _write_probe_run_artifacts(ctx, pid)

        report = _default_report(patchlet)
        report["changed_artifact_files"] = changed_probe_artifacts
        if scenario.get("status") == "COMPLETE":
            report["status"] = "COMPLETE"
            report["changed_product_runtime_file"] = patchlet["allowed_product_runtime_file"]
            report["acceptance_criteria_result"] = "pass"
        report.update(scenario.get("report_override", {}))
        if scenario.get("force_failed_report"):
            report["status"] = "FAILED_WITH_EVIDENCE"
            report["acceptance_criteria_result"] = "fail"
            report["root_cause_classification"]["observed_failure"] = "mock failure requested"

        report_path = ctx.paths.reports_dir / f"{pid}.json"
        write_json(report_path, report)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "output.jsonl").write_text(json.dumps({"mock": True, "patchlet_id": pid}) + "\n", encoding="utf-8")
        if scenario.get("consume_after_run") and scenario_path.exists():
            scenario_path.unlink()
        return WorkerResult(exit_code=0, stdout="mock worker completed", stderr="", report_path=report_path)
