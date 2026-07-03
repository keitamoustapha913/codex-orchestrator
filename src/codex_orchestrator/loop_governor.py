from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.operator_events import append_operator_event
from codex_orchestrator.state import now_iso


def loop_governor_path(repo_root: Path | str) -> Path:
    return Path(repo_root) / ".codex-orchestrator" / "loop_governor.json"


def normalize_failure_signature(failure: dict[str, Any] | str) -> tuple[str, str]:
    if isinstance(failure, dict):
        category = str(failure.get("category") or failure.get("failure_category") or failure.get("source") or "unknown_repeated_failure")
        text = " ".join(
            str(failure.get(key) or "")
            for key in ("observed_failure", "error_message", "message", "diagnosis")
        )
    else:
        category = "unknown_repeated_failure"
        text = str(failure)
    lowered = re.sub(r"[\s_-]+", " ", text.lower())
    if "probe artifact refs" in lowered or "probe_artifact_refs" in text:
        if "json object" in lowered or "not objects" in lowered or "instead of objects" in lowered:
            return "patchlet_report_schema_violation", "probe_artifact_refs_not_objects"
    if "patchlet report schema" in lowered:
        return "patchlet_report_schema_violation", "patchlet_report_schema_violation"
    if "wrapper gate" in lowered and "final status" in lowered:
        return "wrapper_gate_final_status_marker_error", "wrapper_gate_final_status_marker_error"
    if "integration checkpoint" in lowered and "clean" in lowered:
        return "integration_checkpoint_target_cleanliness_error", "integration_checkpoint_target_cleanliness_error"
    if "integration artifact validation" in lowered:
        return "integration_artifact_validation_error", "integration_artifact_validation_error"
    if "__pycache__" in text or ".pyc" in lowered:
        return "target_cache_artifact_leak", "target_cache_artifact_leak"
    return category, "unknown_repeated_failure"


def _default_governor(*, max_repeated_failure_signature: int, mode: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "kind": "loop_governor",
        "max_total_iterations": 150,
        "max_repeated_failure_signature": max_repeated_failure_signature,
        "max_repair_cycles_per_patchlet": 5,
        "mode": mode,
        "failure_signatures": [],
        "warnings": [],
        "blocked": False,
        "blocked_reason": None,
    }


def read_loop_governor(repo_root: Path | str, *, max_repeated_failure_signature: int = 3, mode: str = "warning") -> dict[str, Any]:
    path = loop_governor_path(repo_root)
    if not path.exists():
        return _default_governor(max_repeated_failure_signature=max_repeated_failure_signature, mode=mode)
    data = read_json(path)
    if not isinstance(data, dict):
        return _default_governor(max_repeated_failure_signature=max_repeated_failure_signature, mode=mode)
    data.setdefault("failure_signatures", [])
    data.setdefault("warnings", [])
    data.setdefault("blocked", False)
    data.setdefault("blocked_reason", None)
    data["max_repeated_failure_signature"] = max_repeated_failure_signature
    data["mode"] = mode
    return data


def record_failure_signature(
    repo_root: Path | str,
    *,
    failure_record: dict[str, Any],
    max_repeated_failure_signature: int = 3,
    mode: str = "warning",
) -> dict[str, Any]:
    root = Path(repo_root)
    governor = read_loop_governor(
        root,
        max_repeated_failure_signature=max_repeated_failure_signature,
        mode=mode,
    )
    category, fingerprint = normalize_failure_signature(failure_record)
    signatures = governor.setdefault("failure_signatures", [])
    signature = next((item for item in signatures if item.get("message_fingerprint") == fingerprint), None)
    now = now_iso()
    if signature is None:
        signature = {
            "schema_version": "1.0",
            "kind": "failure_signature",
            "signature_id": f"FS{len(signatures) + 1:06d}",
            "category": category,
            "message_fingerprint": fingerprint,
            "first_seen_at": now,
            "last_seen_at": now,
            "count": 0,
            "patchlet_ids": [],
            "failure_ids": [],
        }
        signatures.append(signature)
    signature["category"] = category
    signature["last_seen_at"] = now
    signature["count"] = int(signature.get("count", 0)) + 1
    patchlet_ids = signature.setdefault("patchlet_ids", [])
    for patchlet_id in failure_record.get("source_patchlet_ids", []) or [failure_record.get("source_id")]:
        if isinstance(patchlet_id, str) and patchlet_id and patchlet_id not in patchlet_ids:
            patchlet_ids.append(patchlet_id)
    failure_ids = signature.setdefault("failure_ids", [])
    failure_id = failure_record.get("failure_id")
    if isinstance(failure_id, str) and failure_id not in failure_ids:
        failure_ids.append(failure_id)

    warning_key = f"{fingerprint}:{signature['count']}"
    threshold_reached = signature["count"] >= max_repeated_failure_signature
    if mode == "safe-fail" and threshold_reached and not governor.get("blocked"):
        reason = (
            f"Repeated failure signature {fingerprint} exceeded threshold "
            f"{max_repeated_failure_signature}; safe-failing to preserve evidence and prevent unbounded repair loop."
        )
        governor["blocked"] = True
        governor["blocked_reason"] = reason
        append_operator_event(
            root,
            event_type="loop_governor_blocked",
            severity="error",
            stage="REPAIR_PLANNING_REQUIRED",
            summary=reason,
            artifact_paths=[".codex-orchestrator/loop_governor.json"],
            details={
                "message_fingerprint": fingerprint,
                "count": signature["count"],
                "threshold": max_repeated_failure_signature,
                "patchlet_ids": list(patchlet_ids),
                "failure_ids": list(failure_ids),
            },
        )
    if (
        mode == "warning"
        and threshold_reached
        and warning_key not in {warning.get("warning_key") for warning in governor.get("warnings", [])}
    ):
        warning = {
            "warning_key": warning_key,
            "signature_id": signature["signature_id"],
            "message_fingerprint": fingerprint,
            "count": signature["count"],
            "threshold": max_repeated_failure_signature,
            "patchlet_ids": list(patchlet_ids),
            "failure_ids": list(failure_ids),
            "created_at": now,
        }
        governor.setdefault("warnings", []).append(warning)
        append_operator_event(
            root,
            event_type="loop_governor_warning",
            severity="warning",
            stage="REPAIR_PLANNING_REQUIRED",
            summary=(
                f"Repeated failure signature {fingerprint} seen {signature['count']} times "
                f"across {', '.join(patchlet_ids)}; continuing in warning mode."
            ),
            artifact_paths=[".codex-orchestrator/loop_governor.json"],
            details=warning,
        )

    path = loop_governor_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, governor)
    return governor
