from __future__ import annotations

from pathlib import Path

from codex_orchestrator.patchlet_planner import build_patchlet_plan
from codex_orchestrator.validators.diff_validator import validate_changed_paths
from codex_orchestrator.validators.schema_validator import validate_json
from codex_orchestrator.work_slice_planner import plan_work_slices


SERVICE_CFG = """# service deployment profile
status=pending
mode=permissive
rollout=blue
audit=disabled
enforcement=allow-by-default
"""


EXPECTED = [
    ("GI001", "PO001", "status", "pending", "ready-no-compat"),
    ("GI002", "PO002", "mode", "permissive", "strict"),
    ("GI003", "PO003", "rollout", "blue", "green"),
    ("GI004", "PO004", "audit", "disabled", "enabled"),
    ("GI005", "PO005", "enforcement", "allow-by-default", "deny-by-default"),
]


def _proof_obligations() -> dict:
    return {
        "workflow_id": "WF",
        "run_id": "R0001",
        "master_prompt_sha256": "a" * 64,
        "obligations": [
            {
                "obligation_id": oid,
                "goal_item_ids": [gid],
                "required": True,
                "claim": f"The accepted integration state has service.cfg containing {key}={new}.",
                "target_boundaries": ["service.cfg"],
            }
            for gid, oid, key, _old, new in EXPECTED
        ],
    }


def _work_slices() -> dict:
    impact = {
        "workflow_id": "WF",
        "run_id": "R0001",
        "candidate_files": [
            {
                "path": "service.cfg",
                "content": SERVICE_CFG,
                "inventory_node_ids": ["N001"],
                "goal_item_ids": [row[0] for row in EXPECTED],
                "proof_obligation_ids": [row[1] for row in EXPECTED],
                "dependency_inputs": [],
                "dependency_outputs": [],
                "risk_level": "low",
                "suggested_slice_types": [
                    "configuration_adjustment",
                    "runtime_behavior_change",
                    "validation_adjustment",
                    "formatting_adjustment",
                    "final_integration_adjustment",
                ],
            }
        ],
        "dependency_edges": [],
    }
    return plan_work_slices(
        impact_analysis=impact,
        proof_obligations=_proof_obligations(),
        default_patchlet_timeout_seconds=600,
    )


def _patchlet_plan() -> dict:
    return build_patchlet_plan(work_slices=_work_slices(), default_patchlet_timeout_seconds=600)


def _p0001() -> dict:
    return _patchlet_plan()["patchlets"][0]


def _diff(*, status=True, future=False) -> str:
    old = SERVICE_CFG
    new = old
    if status:
        new = new.replace("status=pending", "status=ready-no-compat")
    if future:
        new = (
            new.replace("mode=permissive", "mode=strict")
            .replace("rollout=blue", "rollout=green")
            .replace("audit=disabled", "audit=enabled")
            .replace("enforcement=allow-by-default", "enforcement=deny-by-default")
        )
    return "\n".join(
        [
            "diff --git a/service.cfg b/service.cfg",
            "index 0000000..1111111 100644",
            "--- a/service.cfg",
            "+++ b/service.cfg",
            "@@ -1,6 +1,6 @@",
            *[f"-{line}" for line in old.rstrip().splitlines()],
            *[f"+{line}" for line in new.rstrip().splitlines()],
            "",
        ]
    )


def test_same_file_patchlet_has_slice_allowed_change_boundary():
    assert _p0001()["slice_change_boundary"]["allowed_changes"][0]["key"] == "status"


def test_same_file_patchlet_prompt_lists_current_slice_only():
    boundary = _p0001()["slice_change_boundary"]
    assert boundary["goal_item_ids"] == ["GI001"]
    assert boundary["proof_obligation_ids"] == ["PO001"]


def test_same_file_patchlet_prompt_forbids_future_slice_changes():
    forbidden = {row["key"] for row in _p0001()["slice_change_boundary"]["forbidden_changes"]}
    assert forbidden == {"mode", "rollout", "audit", "enforcement"}


def test_same_file_overscope_diff_rejected_even_when_file_is_allowed():
    result = validate_changed_paths(["service.cfg"], _p0001(), diff_text=_diff(status=True, future=True))
    assert result.allowed is False
    assert "service.cfg" in result.unauthorized_paths
    assert result.slice_boundary_violations


def test_same_file_current_slice_diff_accepted():
    result = validate_changed_paths(["service.cfg"], _p0001(), diff_text=_diff(status=True, future=False))
    assert result.allowed is True


def test_same_file_future_slice_diff_blocks_patchlet_acceptance():
    result = validate_changed_paths(["service.cfg"], _p0001(), diff_text=_diff(status=False, future=True))
    assert result.allowed is False
    assert result.slice_boundary_violations[0]["reason"] == "future_slice_change"


def test_same_file_slice_boundary_records_future_goal_item_ids():
    assert _p0001()["slice_change_boundary"]["forbidden_future_goal_item_ids"] == ["GI002", "GI003", "GI004", "GI005"]


def test_same_file_slice_boundary_records_allowed_key_or_section():
    change = _p0001()["slice_change_boundary"]["allowed_changes"][0]
    assert change["key"] == "status"
    assert change["old_line"] == "status=pending"
    assert change["new_line"] == "status=ready-no-compat"


def test_same_file_slice_boundary_schema_validates():
    assert validate_json(_work_slices(), "work_slices.schema.json") == []
    assert validate_json(_patchlet_plan(), "patchlet_plan.schema.json") == []
