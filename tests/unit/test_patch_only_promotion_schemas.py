from __future__ import annotations

from codex_orchestrator.validators.schema_validator import validate_json


def _ledger_entry(classification: str, path: str = "app.py") -> dict:
    allowed = classification in {"ALLOWED_PRODUCT_CHANGE", "ALLOWED_PRODUCT_PATH_VIOLATION"}
    blocking = classification in {"ALLOWED_PRODUCT_PATH_VIOLATION", "SANDBOX_CONTAINMENT_VIOLATION"}
    return {
        "path": path,
        "classification": classification,
        "inside_execution_boundary": classification != "SANDBOX_CONTAINMENT_VIOLATION",
        "allowed_product_match": allowed,
        "promotion_eligible": classification == "ALLOWED_PRODUCT_CHANGE",
        "excluded_from_promotion": classification != "ALLOWED_PRODUCT_CHANGE",
        "blocking": blocking,
    }


def _ledger(classification: str = "SANDBOX_DEBRIS") -> dict:
    return {
        "schema_version": "1.0",
        "kind": "worker_change_classification_ledger",
        "patchlet_id": "P0001",
        "attempt_id": "P0001_attempt1",
        "entries": [_ledger_entry(classification, ".tmp")],
        "every_path_classified_once": True,
        "promotion_blocked": classification
        in {"ALLOWED_PRODUCT_PATH_VIOLATION", "SANDBOX_CONTAINMENT_VIOLATION"},
    }


def _hygiene(status: str = "CLEAN") -> dict:
    allowed = _ledger_entry("ALLOWED_PRODUCT_CHANGE")
    debris = [_ledger_entry("SANDBOX_DEBRIS", ".tmp")] if status == "DEBRIS_PRESENT" else []
    allowed_violations = (
        [_ledger_entry("ALLOWED_PRODUCT_PATH_VIOLATION")] if status == "ALLOWED_PATH_VIOLATION" else []
    )
    containment_violations = (
        [_ledger_entry("SANDBOX_CONTAINMENT_VIOLATION", "../escape")] if status == "CONTAINMENT_VIOLATION" else []
    )
    blocked = bool(allowed_violations or containment_violations)
    entries = [allowed, *debris, *allowed_violations, *containment_violations]
    return {
        "schema_version": "1.0",
        "kind": "worker_sandbox_hygiene_result",
        "candidate_scope": "raw_worker_sandbox",
        "patchlet_id": "P0001",
        "attempt_id": "P0001_attempt1",
        "sandbox_root": "/tmp/worker",
        "accepted_checkpoint": "abc123",
        "status": status,
        "entries": entries,
        "debris_entries": debris,
        "allowed_path_violations": allowed_violations,
        "containment_violations": containment_violations,
        "inspection_complete": True,
        "inspection_limits": {"maximum_entry_count": 5000},
        "promotion_blocked": blocked,
        "include_paths": [] if blocked else ["app.py"],
        "change_classification_ledger": entries,
        "sandbox_debris_count": len(debris),
        "allowed_product_change_count": 1,
        "allowed_path_violation_count": len(allowed_violations),
        "containment_violation_count": len(containment_violations),
        "inventory_truncated": False,
        "errors": ["blocking violation"] if blocked else [],
    }


def _manifest() -> dict:
    return {
        "schema_version": "1.0",
        "kind": "patch_proposal_manifest",
        "candidate_scope": "patch_proposal",
        "patchlet_id": "P0001",
        "attempt_id": "P0001_attempt1",
        "accepted_checkpoint_commit": "abc123",
        "accepted_checkpoint_tree": "def456",
        "patch_path": "/tmp/patch.patch",
        "patch_sha256": "0" * 64,
        "patch_size_bytes": 10,
        "changed_paths": [{"path": "app.py"}],
        "goal_item_ids": ["GI001"],
        "proof_obligation_ids": ["PO001"],
        "probe_ids": ["GP001"],
        "current_slice_boundary": {"symbol": "main"},
        "future_slice_boundaries": [],
        "excluded_sandbox_paths": [".tmp"],
        "worker_hygiene_status": "DEBRIS_PRESENT",
    }


def _validation() -> dict:
    return {
        "schema_version": "1.0",
        "kind": "patch_proposal_validation_result",
        "candidate_scope": "patch_proposal",
        "patchlet_id": "P0001",
        "attempt_id": "P0001_attempt1",
        "schema_valid": True,
        "allowed_file_validation": True,
        "current_boundary_validation": True,
        "future_boundary_validation": True,
        "support_file_validation": True,
        "verification_file_validation": True,
        "binary_patch_validation": True,
        "accepted": True,
        "errors": [],
    }


def _reconstruction() -> dict:
    return {
        "schema_version": "1.0",
        "kind": "patch_reconstruction_result",
        "candidate_scope": "clean_reconstruction",
        "patchlet_id": "P0001",
        "attempt_id": "P0001_attempt1",
        "base_checkpoint": "abc123",
        "base_tree": "def456",
        "patch_sha256": "0" * 64,
        "verification_root": "/tmp/verify",
        "apply_check_returncode": 0,
        "apply_returncode": 0,
        "reconstructed_changed_paths": ["app.py"],
        "reconstructed_diff_sha256": "0" * 64,
        "proposal_reconstructed_equality": True,
        "unexpected_paths": [],
        "clean_before": True,
        "clean_after_relative_to_proposal": True,
        "accepted": True,
        "errors": [],
    }


def _promotion() -> dict:
    return {
        "schema_version": "1.0",
        "kind": "clean_candidate_promotion_result",
        "candidate_scope": "promoted_candidate",
        "patchlet_id": "P0001",
        "attempt_id": "P0001_attempt1",
        "base_integration_ref": "refs/cxor/runs/R0001/integration",
        "integration_ref_before": "a" * 40,
        "expected_old_commit": "a" * 40,
        "candidate_commit": "b" * 40,
        "candidate_tree": "c" * 40,
        "canonical_patch_sha256": "0" * 64,
        "independent_proof_result_ref": {"path": ".codex-orchestrator/runs/P0001_attempt1/gates/independent_probe_rerun_result.json"},
        "goal_coverage_result_ref": {"path": ".codex-orchestrator/runs/P0001_attempt1/gates/goal_coverage_gate_result.json"},
        "canonical_semantic_result_ref": {"path": ".codex-orchestrator/runs/P0001_attempt1/gates/canonical_patchlet_semantic_result.json"},
        "integration_ref_after": "b" * 40,
        "durable_ref_update_completed": True,
        "promotion_accepted": True,
        "errors": [],
    }


def _preparation() -> dict:
    return {
        "schema_version": "1.0",
        "kind": "clean_candidate_preparation_result",
        "candidate_scope": "clean_reconstruction",
        "patchlet_id": "P0001",
        "attempt_id": "P0001_attempt1",
        "base_commit": "abc123",
        "base_tree": "def456",
        "proposal_patch_sha256": "0" * 64,
        "verification_candidate_root": "/tmp/verify",
        "worker_hygiene_status": "DEBRIS_PRESENT",
        "worker_warning_count": 1,
        "candidate_prepared": True,
        "durable_integration_updated": False,
    }


def _disposal() -> dict:
    return {
        "schema_version": "1.0",
        "kind": "worker_sandbox_disposal_result",
        "candidate_scope": "raw_worker_sandbox",
        "patchlet_id": "P0001",
        "attempt_id": "P0001_attempt1",
        "sandbox_root": "/tmp/worker",
        "attempt_result": "accepted",
        "promotion_result": True,
        "evidence_retained": True,
        "excluded_debris_metadata_retained": True,
        "sandbox_archived": False,
        "cleanup_attempted": True,
        "cleanup_succeeded": True,
        "remaining_path_exists": False,
        "errors": [],
    }


def test_clean_hygiene_result_validates():
    assert validate_json(_hygiene("CLEAN"), "worker_sandbox_hygiene_result.schema.json") == []


def test_debris_present_hygiene_result_validates():
    assert validate_json(_hygiene("DEBRIS_PRESENT"), "worker_sandbox_hygiene_result.schema.json") == []


def test_sandbox_debris_classification_validates():
    assert validate_json(_ledger("SANDBOX_DEBRIS"), "worker_change_classification_ledger.schema.json") == []


def test_old_worker_change_classifications_are_rejected():
    old_classes = {
        "APPROVED_PROBE_EVIDENCE",
        "BOUNDED_SCRATCH_WARNING",
        "FORBIDDEN_TRACKED_CHANGE",
        "PROTECTED_FILE_CHANGE",
        "UNKNOWN_WORKER_OUTPUT",
        "UNSAFE_PATH_OBJECT",
        "UNRECOGNIZED_EVIDENCE",
        "UNSAFE_EVIDENCE_OBJECT",
        "EVIDENCE_LIMIT_EXCEEDED",
    }
    for classification in old_classes:
        assert validate_json(
            _ledger(classification),
            "worker_change_classification_ledger.schema.json",
        ), classification


def test_legacy_evidence_classification_is_rejected():
    assert validate_json(
        _ledger("LEGACY_" + "APPROVED_PROBE_EVIDENCE"),
        "worker_change_classification_ledger.schema.json",
    )


def test_worker_hygiene_has_no_rejected_entries_field():
    data = _hygiene()
    data["rejected_entries"] = []
    assert validate_json(data, "worker_sandbox_hygiene_result.schema.json")


def test_worker_hygiene_has_no_legacy_evidence_count():
    data = _hygiene()
    data["legacy_evidence_file_count"] = 0
    assert validate_json(data, "worker_sandbox_hygiene_result.schema.json")


def test_worker_hygiene_blocks_only_allowed_path_or_containment_violations():
    debris = _hygiene("DEBRIS_PRESENT")
    debris["promotion_blocked"] = True
    assert validate_json(debris, "worker_sandbox_hygiene_result.schema.json")
    violation = _hygiene("ALLOWED_PATH_VIOLATION")
    violation["promotion_blocked"] = False
    assert validate_json(violation, "worker_sandbox_hygiene_result.schema.json")


def test_patch_validation_does_not_depend_on_raw_sandbox_debris():
    data = _validation()
    assert "path_type_validation" not in data
    assert validate_json(data, "patch_proposal_validation_result.schema.json") == []


def test_patch_proposal_manifest_validates():
    assert validate_json(_manifest(), "patch_proposal_manifest.schema.json") == []


def test_patch_validation_result_validates():
    assert validate_json(_validation(), "patch_proposal_validation_result.schema.json") == []


def test_reconstruction_result_validates():
    assert validate_json(_reconstruction(), "patch_reconstruction_result.schema.json") == []


def test_promotion_result_validates():
    assert validate_json(_promotion(), "clean_candidate_promotion_result.schema.json") == []


def test_preparation_result_validates():
    assert validate_json(_preparation(), "clean_candidate_preparation_result.schema.json") == []


def test_promotion_accepted_requires_durable_ref_update():
    data = _promotion()
    data["durable_ref_update_completed"] = False
    assert validate_json(data, "clean_candidate_promotion_result.schema.json")


def test_canonical_semantic_result_validates():
    data = {
        "schema_version": "1.0",
        "kind": "canonical_patchlet_semantic_result",
        "candidate_scope": "clean_reconstruction",
        "patchlet_id": "P0001",
        "attempt_id": "P0001_attempt1",
        "goal_item_ids": ["GI001"],
        "proof_obligation_ids": ["PO001"],
        "probe_ids": ["GP001"],
        "allowed_product_file": "app.py",
        "current_boundary": {"symbol": "main"},
        "future_boundaries": [],
        "canonical_patch_sha256": "0" * 64,
        "clean_candidate_commit": "b" * 40,
        "clean_candidate_tree": "c" * 40,
        "effective_source_manifest_ref": {"path": "effective.json"},
        "independent_proof_result_ref": {"path": "proof.json"},
        "goal_coverage_result_ref": {"path": "coverage.json"},
        "worker_report_integrity_ref": {"path": "integrity.json"},
        "worker_report_semantic_quality_ref": {"path": "quality.json"},
        "worker_report_semantic_status": "INCOMPLETE",
        "current_obligation_proven": True,
        "future_obligations_advanced": [],
        "accepted": True,
        "errors": [],
    }
    assert validate_json(data, "canonical_patchlet_semantic_result.schema.json") == []


def test_semantic_warning_result_is_non_blocking():
    data = {
        "schema_version": "1.0",
        "kind": "worker_report_semantic_quality_result",
        "candidate_scope": "clean_reconstruction",
        "patchlet_id": "P0001",
        "attempt_id": "P0001_attempt1",
        "status": "INCOMPLETE",
        "expected_components": {"file": "app.py"},
        "matched_components": [],
        "missing_components": ["current_boundary"],
        "contradictions": [],
        "overclaims": [],
        "blocking": False,
        "warnings": [{"warning_code": "WORKER_REPORT_SEMANTIC_EVIDENCE_INCOMPLETE"}],
        "errors": [],
    }
    assert validate_json(data, "worker_report_semantic_quality_result.schema.json") == []


def test_integrity_failure_is_blocking():
    data = {
        "schema_version": "1.0",
        "kind": "worker_report_integrity_result",
        "candidate_scope": "raw_worker_sandbox",
        "patchlet_id": "P0001",
        "attempt_id": "P0001_attempt1",
        "accepted": False,
        "report_exists": True,
        "report_parsed": False,
        "schema_valid": False,
        "required_structural_fields_present": False,
        "declared_artifact_references_valid": False,
        "excluded_debris_references_rejected": False,
        "required_evidence_references_valid": False,
        "blocking_errors": [{"message": "malformed"}],
    }
    assert validate_json(data, "worker_report_integrity_result.schema.json") == []


def test_disposal_result_validates():
    assert validate_json(_disposal(), "worker_sandbox_disposal_result.schema.json") == []


def test_effective_source_manifest_validates():
    data = {
        "schema_version": "1.0",
        "kind": "independent_proof_effective_source_manifest",
        "candidate_scope": "clean_reconstruction",
        "patchlet_id": "P0001",
        "attempt_id": "P0001_attempt1",
        "base_checkpoint_commit": "abc123",
        "base_checkpoint_tree": "def456",
        "patch_sha256": "0" * 64,
        "verification_root": "/tmp/verify",
        "probe_id": "GP001",
        "probe_command": "python app.py",
        "probe_cwd": "/tmp/verify",
        "effective_sources": [
            {"path": "app.py", "blob_sha256": "1" * 64, "git_blob_id": "2" * 40, "mode": "100644"}
        ],
        "manifest_sha256": "3" * 64,
    }
    assert validate_json(data, "independent_proof_effective_source_manifest.schema.json") == []


def test_unknown_fields_are_rejected():
    data = _validation()
    data["unexpected"] = True
    assert validate_json(data, "patch_proposal_validation_result.schema.json")


def test_missing_fields_are_rejected():
    data = _promotion()
    data.pop("promotion_accepted")
    assert validate_json(data, "clean_candidate_promotion_result.schema.json")
