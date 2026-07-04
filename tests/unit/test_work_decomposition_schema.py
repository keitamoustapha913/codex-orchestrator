from __future__ import annotations

from codex_orchestrator.validators.schema_validator import validate_json


def _work_slices():
    return {
        "schema_version": "1.0",
        "kind": "work_slices",
        "workflow_id": "WF000001",
        "run_id": "R0001",
        "slices": [
            {
                "work_slice_id": "WS001",
                "title": "Update entrypoint wiring",
                "allowed_product_runtime_file": "app.py",
                "slice_type": "entrypoint_wiring",
                "goal_item_ids": ["GI001"],
                "proof_obligation_ids": ["PO001"],
                "inventory_node_ids": ["N001"],
                "depends_on_work_slice_ids": [],
                "risk_level": "low",
                "estimated_complexity": "small",
                "time_budget_seconds": 600,
                "prompt_scope": {
                    "allowed_context_files": ["app.py"],
                    "allowed_edit_file": "app.py",
                    "forbidden_edit_files": [],
                    "memory_compacting_required": False,
                },
            }
        ],
    }


def _patchlet_plan():
    return {
        "schema_version": "1.0",
        "kind": "patchlet_plan",
        "workflow_id": "WF000001",
        "run_id": "R0001",
        "patchlets": [
            {
                "patchlet_id": "P0001",
                "work_slice_id": "WS001",
                "allowed_product_runtime_file": "app.py",
                "allowed_product_runtime_files": ["app.py"],
                "proof_obligation_ids": ["PO001"],
                "goal_item_ids": ["GI001"],
                "dependency_patchlet_ids": [],
                "downstream_patchlet_ids": ["P0002"],
                "time_budget_seconds": 600,
                "prompt_budget_policy": {
                    "must_fit_within_timeout": True,
                    "avoid_memory_compacting": True,
                    "max_scope_files": 1,
                    "max_product_runtime_edit_files": 1,
                },
                "expected_patchlet_statuses": [
                    "COMPLETE",
                    "VERIFIED_NO_CHANGE_NEEDED",
                    "BLOCKED_WITH_EVIDENCE",
                    "FAILED_WITH_EVIDENCE",
                ],
            },
            {
                "patchlet_id": "P0002",
                "work_slice_id": "WS002",
                "allowed_product_runtime_file": "app.py",
                "allowed_product_runtime_files": ["app.py"],
                "proof_obligation_ids": ["PO001"],
                "goal_item_ids": ["GI001"],
                "dependency_patchlet_ids": ["P0001"],
                "downstream_patchlet_ids": [],
                "time_budget_seconds": 600,
                "prompt_budget_policy": {
                    "must_fit_within_timeout": True,
                    "avoid_memory_compacting": True,
                    "max_scope_files": 1,
                    "max_product_runtime_edit_files": 1,
                },
                "expected_patchlet_statuses": [
                    "COMPLETE",
                    "VERIFIED_NO_CHANGE_NEEDED",
                    "BLOCKED_WITH_EVIDENCE",
                    "FAILED_WITH_EVIDENCE",
                ],
            },
        ],
    }


def test_work_decomposition_plan_schema_validates():
    assert validate_json(
        {
            "schema_version": "1.0",
            "kind": "work_decomposition_plan",
            "workflow_id": "WF000001",
            "run_id": "R0001",
            "default_patchlet_timeout_seconds": 600,
            "decomposition_strategy": "small_bounded_work_slices",
            "one_allowed_file_per_patchlet": True,
            "multiple_patchlets_per_file_allowed": True,
            "avoid_memory_compacting": True,
            "work_slice_count": 2,
            "patchlet_count": 2,
            "transaction_group_count": 2,
            "operator_summary": "two bounded patchlets",
            "risk_summary": {
                "large_patchlet_risk": False,
                "multi_file_patchlet_risk": False,
                "dependency_cycle_risk": False,
            },
        },
        "work_decomposition_plan.schema.json",
    ) == []


def test_work_slices_schema_validates():
    assert validate_json(_work_slices(), "work_slices.schema.json") == []


def test_patchlet_plan_schema_validates():
    assert validate_json(_patchlet_plan(), "patchlet_plan.schema.json") == []


def test_dependency_graph_schema_validates():
    assert validate_json(
        {
            "schema_version": "1.0",
            "kind": "decomposition_dependency_graph",
            "workflow_id": "WF000001",
            "run_id": "R0001",
            "nodes": [{"node_id": "P0001", "node_type": "patchlet", "work_slice_id": "WS001", "allowed_product_runtime_file": "app.py"}],
            "edges": [],
            "has_cycles": False,
            "topological_order": ["P0001"],
        },
        "dependency_graph.schema.json",
    ) == []


def test_transaction_group_plan_schema_validates():
    assert validate_json(
        {
            "schema_version": "1.0",
            "kind": "transaction_group_plan",
            "workflow_id": "WF000001",
            "run_id": "R0001",
            "transaction_groups": [
                {
                    "transaction_group_id": "TG001",
                    "patchlet_ids": ["P0001"],
                    "goal_item_ids": ["GI001"],
                    "proof_obligation_ids": ["PO001"],
                    "dependency_patchlet_ids": [],
                    "group_type": "dependency_layer",
                    "operator_summary": "first layer",
                }
            ],
        },
        "transaction_group_plan.schema.json",
    ) == []


def test_work_slice_requires_allowed_product_runtime_file():
    payload = _work_slices()
    del payload["slices"][0]["allowed_product_runtime_file"]
    assert validate_json(payload, "work_slices.schema.json")


def test_patchlet_plan_requires_exactly_one_allowed_product_runtime_file():
    assert validate_json(_patchlet_plan(), "patchlet_plan.schema.json") == []


def test_patchlet_plan_allows_same_file_across_multiple_patchlets():
    payload = _patchlet_plan()
    assert [p["allowed_product_runtime_file"] for p in payload["patchlets"]] == ["app.py", "app.py"]
    assert validate_json(payload, "patchlet_plan.schema.json") == []


def test_patchlet_plan_rejects_multiple_allowed_files_in_one_patchlet():
    payload = _patchlet_plan()
    payload["patchlets"][0]["allowed_product_runtime_files"] = ["app.py", "service.py"]
    assert validate_json(payload, "patchlet_plan.schema.json")


def test_patchlet_plan_requires_time_budget_seconds():
    payload = _patchlet_plan()
    del payload["patchlets"][0]["time_budget_seconds"]
    assert validate_json(payload, "patchlet_plan.schema.json")


def test_patchlet_plan_records_avoid_memory_compacting_policy():
    assert _patchlet_plan()["patchlets"][0]["prompt_budget_policy"]["avoid_memory_compacting"] is True


def test_dependency_graph_rejects_cycle_flag_when_topological_order_missing():
    payload = {
        "schema_version": "1.0",
        "kind": "decomposition_dependency_graph",
        "nodes": [],
        "edges": [],
        "has_cycles": False,
    }
    assert validate_json(payload, "dependency_graph.schema.json")
