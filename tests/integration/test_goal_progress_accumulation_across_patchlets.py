from __future__ import annotations

import json
from pathlib import Path

from codex_orchestrator.goal_progress import update_goal_progress


def _workflow(root: Path) -> Path:
    workflow = root / ".codex-orchestrator"
    workflow.mkdir(parents=True)
    (workflow / "master_prompt_frozen.json").write_text(
        json.dumps({"workflow_id": "WF", "run_id": "R0001", "sha256": "a" * 64}),
        encoding="utf-8",
    )
    (workflow / "provability").mkdir()
    (workflow / "provability" / "provability_result.json").write_text(
        json.dumps({"provability_status": "PROVABLE", "can_start_product_patchlets": True}),
        encoding="utf-8",
    )
    (workflow / "patchlets").mkdir()
    (workflow / "patchlets" / "patchlet_index.json").write_text(
        json.dumps({"patchlets": [{"patchlet_id": f"P000{i}", "status": "PENDING"} for i in range(1, 6)]}),
        encoding="utf-8",
    )
    return workflow


def _obligations() -> dict:
    return {
        "obligations": [
            {"obligation_id": f"PO00{i}", "required": True, "status": "UNPROVEN"}
            for i in range(1, 6)
        ]
    }


def _gate(patchlet_id: str, obligation_id: str) -> dict:
    return {
        "accepted": True,
        "accepted_for_patchlet_progress": True,
        "accepted_for_done": False,
        "patchlet_id": patchlet_id,
        "attempt_id": f"{patchlet_id}_attempt1",
        "covered_obligation_ids": [obligation_id],
        "proven_current_obligation_ids": [obligation_id],
        "failed_current_obligation_ids": [],
        "evidence_paths": [f".codex-orchestrator/runs/{patchlet_id}_attempt1/gates/proof.json"],
    }


def _update(workflow: Path, patchlet_id: str, obligation_id: str) -> dict:
    return update_goal_progress(
        workflow_root=workflow,
        event_reason="goal_coverage_gate",
        workflow_iteration=int(patchlet_id[-1]),
        proof_obligations=_obligations(),
        latest_gate_result=_gate(patchlet_id, obligation_id),
    )


def test_goal_progress_accumulates_proven_obligations_across_patchlets(tmp_path: Path):
    workflow = _workflow(tmp_path)
    _update(workflow, "P0001", "PO001")
    progress = _update(workflow, "P0002", "PO002")
    assert progress["counts"]["proven"] == 2


def test_goal_progress_does_not_replace_previous_proven_obligations(tmp_path: Path):
    workflow = _workflow(tmp_path)
    _update(workflow, "P0001", "PO001")
    progress = _update(workflow, "P0002", "PO002")
    statuses = {row["obligation_id"]: row["status"] for row in progress["obligations"]}
    assert statuses["PO001"] == "PROVEN_BY_ORCHESTRATOR"
    assert statuses["PO002"] == "PROVEN_BY_ORCHESTRATOR"


def test_goal_progress_jsonl_records_p0001_then_p0002_progression(tmp_path: Path):
    workflow = _workflow(tmp_path)
    _update(workflow, "P0001", "PO001")
    _update(workflow, "P0002", "PO002")
    rows = [json.loads(line) for line in (workflow / "goal_progress.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [row["counts"]["proven"] for row in rows[-2:]] == [1, 2]


def test_goal_progress_status_after_p0002_is_two_of_five(tmp_path: Path):
    workflow = _workflow(tmp_path)
    _update(workflow, "P0001", "PO001")
    progress = _update(workflow, "P0002", "PO002")
    assert progress["counts"] == {"required_obligations": 5, "proven": 2, "failed": 0, "blocked": 0, "unproven": 3}


def test_goal_progress_future_obligations_remain_unproven(tmp_path: Path):
    workflow = _workflow(tmp_path)
    _update(workflow, "P0001", "PO001")
    progress = _update(workflow, "P0002", "PO002")
    statuses = {row["obligation_id"]: row["status"] for row in progress["obligations"]}
    assert statuses["PO003"] == "UNPROVEN"
    assert statuses["PO004"] == "UNPROVEN"
    assert statuses["PO005"] == "UNPROVEN"


def test_goal_progress_done_eligibility_false_until_all_five(tmp_path: Path):
    workflow = _workflow(tmp_path)
    _update(workflow, "P0001", "PO001")
    progress = _update(workflow, "P0002", "PO002")
    assert progress["overall_goal_status"] == "PARTIALLY_PROVEN"


def test_final_goal_progress_proven_after_all_five(tmp_path: Path):
    workflow = _workflow(tmp_path)
    progress = {}
    for i in range(1, 6):
        progress = _update(workflow, f"P000{i}", f"PO00{i}")
    assert progress["counts"]["proven"] == 5
    assert progress["overall_goal_status"] == "PROVEN"
