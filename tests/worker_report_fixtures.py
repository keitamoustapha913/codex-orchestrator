from __future__ import annotations

from typing import Any


def worker_patchlet_report_v2(
    *,
    patchlet_id: str = "P0001",
    status: str = "VERIFIED_NO_CHANGE_NEEDED",
    changed_product_runtime_file: str | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": "2.0",
        "kind": "worker_patchlet_report",
        "patchlet_id": patchlet_id,
        "status": status,
        "changed_product_runtime_file": changed_product_runtime_file,
        "changed_artifact_files": [],
        "probe_commands": ["python -c \"print('probe')\""],
        "deterministic_run_counts": {
            "baseline": "1/1",
            "proof_of_fix": "1/1",
            "negative_controls": "1/1",
        },
        "root_cause_classification": {
            "observed_failure": "bounded observation",
            "immediate_cause": "bounded cause",
            "why_immediate_cause_happened": "current slice state",
            "deeper_owner_boundary": changed_product_runtime_file or "current boundary",
            "producer_transformer_consumer_boundary": "producer to probe",
            "not_downstream_of_unprobed_state_proof": "direct probe",
            "negative_control_proof": "peer state unchanged",
            "recursive_why_audit": ["bounded why"],
        },
        "before_after_state": [],
        "row_ledger": [],
        "trace_ledger": [],
        "cleanup_proof": "clean",
        "probe_artifact_refs": [
            {
                "patchlet_id": patchlet_id,
                "probe_root": f".artifacts/probes/{patchlet_id}",
                "run_id": "default",
            }
        ],
        "semantic_goal_results": [],
    }
    report.update(overrides)
    return report


def complete_worker_patchlet_report_v2(
    *,
    patchlet_id: str = "P0001",
    product_file: str = "app.py",
    **overrides: Any,
) -> dict[str, Any]:
    return worker_patchlet_report_v2(
        patchlet_id=patchlet_id,
        status="COMPLETE",
        changed_product_runtime_file=product_file,
        **overrides,
    )


def verified_no_change_worker_patchlet_report_v2(
    *, patchlet_id: str = "P0001", **overrides: Any
) -> dict[str, Any]:
    return worker_patchlet_report_v2(
        patchlet_id=patchlet_id,
        status="VERIFIED_NO_CHANGE_NEEDED",
        changed_product_runtime_file=None,
        **overrides,
    )


def failed_worker_patchlet_report_v2(
    *, patchlet_id: str = "P0001", **overrides: Any
) -> dict[str, Any]:
    return worker_patchlet_report_v2(
        patchlet_id=patchlet_id,
        status="FAILED_WITH_EVIDENCE",
        changed_product_runtime_file=None,
        failed_probe_evidence="probe failed deterministically",
        **overrides,
    )


def blocked_worker_patchlet_report_v2(
    *, patchlet_id: str = "P0001", **overrides: Any
) -> dict[str, Any]:
    return worker_patchlet_report_v2(
        patchlet_id=patchlet_id,
        status="BLOCKED_WITH_EVIDENCE",
        changed_product_runtime_file=None,
        blocking_boundary_reason="bounded dependency outside current slice",
        **overrides,
    )
