from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from conftest import read_json

from codex_orchestrator.operator_events import read_operator_events
from codex_orchestrator.jsonio import write_json
from codex_orchestrator.report_ingestion import ingest_patchlet_report
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file


def _ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    _scenario(ctx, [])
    return ctx


def _scenario(ctx, refs):
    path = ctx.paths.workflow_dir / "mock" / "next_patchlet_result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "report_production_override": {
                    "schema_version": "2.0",
                    "kind": "worker_patchlet_report",
                    "probe_artifact_refs": refs,
                }
            }
        ),
        encoding="utf-8",
    )


def _report_with_changed_runtime_file_alias() -> dict:
    return {
        "schema_version": "2.0",
        "kind": "worker_patchlet_report",
        "patchlet_id": "P0001",
        "status": "COMPLETE",
        "changed_runtime_file": "app.py",
        "changed_artifact_files": [],
        "probe_commands": ["python app.py"],
        "deterministic_run_counts": {},
        "root_cause_classification": {},
        "before_after_state": [],
        "row_ledger": [],
        "trace_ledger": [],
        "cleanup_proof": "clean",
        "probe_artifact_refs": [],
        "semantic_goal_results": [],
    }


def _identity_gate_report(*, schema_version: str = "1.0", kind: str = "patchlet_report") -> dict:
    return {
        "schema_version": schema_version,
        "kind": kind,
        "patchlet_id": "P0001",
        "status": "COMPLETE",
        "changed_product_runtime_file": "app.py",
        "changed_artifact_files": [],
        "probe_commands": ["python app.py"],
        "deterministic_run_counts": {
            "baseline": "1/1",
            "proof_of_fix": "1/1",
            "negative_controls": "1/1",
        },
        "root_cause_classification": {
            "observed_failure": "old value",
            "immediate_cause": "old implementation",
            "why_immediate_cause_happened": "current slice was absent",
            "deeper_owner_boundary": "app.py",
            "producer_transformer_consumer_boundary": "app.py to probe",
            "not_downstream_of_unprobed_state_proof": "direct probe",
            "negative_control_proof": "peer values unchanged",
            "recursive_why_audit": ["bounded cause"],
        },
        "before_after_state": [],
        "row_ledger": [],
        "trace_ledger": [],
        "cleanup_proof": "clean",
        "probe_artifact_refs": [
            {
                "patchlet_id": "P0001",
                "probe_root": ".artifacts/probes/P0001",
                "run_id": "default",
            }
        ],
        "semantic_goal_results": [],
    }


def _ingest_identity_gate_report(ctx, report: dict, *, source_text: str | None = None):
    source = ctx.root / "P0001.identity-gate.json"
    source.write_text(source_text if source_text is not None else json.dumps(report), encoding="utf-8")
    result = ingest_patchlet_report(
        ctx,
        patchlet={
            "patchlet_id": "P0001",
            "goal_item_ids": ["GI001"],
            "proof_obligation_ids": ["PO001"],
            "probe_ids": ["GP001"],
            "work_slice_id": "WS001",
            "allowed_product_runtime_file": "app.py",
            "slice_change_boundary": {
                "allowed_changes": [{"key": "app", "new_value": "requested_state"}],
                "forbidden_changes": [],
            },
        },
        attempt_id="P0001_attempt1",
        report_path=source,
    )
    return result, source


def test_v1_report_is_rejected_before_reorganization(git_repo: Path):
    ctx = _ctx(git_repo)
    result, _ = _ingest_identity_gate_report(ctx, _identity_gate_report())
    assert result["accepted"] is False
    assert result["report_reorganization_used"] is False


def test_v1_report_is_rejected_before_probe_ref_normalization(git_repo: Path):
    ctx = _ctx(git_repo)
    result, _ = _ingest_identity_gate_report(ctx, _identity_gate_report())
    assert result["normalization_applied"] is False
    assert result["normalization_kinds"] == []
    assert not (ctx.paths.runs_dir / "P0001_attempt1/gates/probe_artifact_refs_normalization_result.json").exists()


def test_v1_report_is_rejected_before_probe_command_normalization(git_repo: Path):
    ctx = _ctx(git_repo)
    result, _ = _ingest_identity_gate_report(ctx, _identity_gate_report())
    assert result["normalization_applied"] is False
    assert not (ctx.paths.runs_dir / "P0001_attempt1/gates/probe_commands_normalization_result.json").exists()


def test_v1_report_is_rejected_before_semantic_normalization(git_repo: Path):
    ctx = _ctx(git_repo)
    result, _ = _ingest_identity_gate_report(ctx, _identity_gate_report())
    assert result["normalization_applied"] is False
    assert not (ctx.paths.runs_dir / "P0001_attempt1/gates/semantic_goal_results_normalization_result.json").exists()


def test_v1_report_raw_bytes_are_preserved(git_repo: Path):
    ctx = _ctx(git_repo)
    raw_text = json.dumps(_identity_gate_report(), indent=3) + "\n"
    result, source = _ingest_identity_gate_report(ctx, _identity_gate_report(), source_text=raw_text)
    assert result["accepted"] is False
    assert (ctx.paths.reports_dir / "P0001.raw.json").read_bytes() == source.read_bytes()


def test_v1_report_writes_unsupported_version_failure(git_repo: Path):
    ctx = _ctx(git_repo)
    result, _ = _ingest_identity_gate_report(ctx, _identity_gate_report())
    assert result["normalized_failure_signature"] == "WORKER_REPORT_UNSUPPORTED_SCHEMA_VERSION"


def test_wrong_v2_kind_is_rejected_before_reorganization(git_repo: Path):
    ctx = _ctx(git_repo)
    report = _identity_gate_report(schema_version="2.0", kind="patchlet_report")
    result, _ = _ingest_identity_gate_report(ctx, report)
    assert result["accepted"] is False
    assert result["report_reorganization_used"] is False
    assert result["normalization_applied"] is False


def test_wrong_v2_kind_writes_invalid_kind_failure(git_repo: Path):
    ctx = _ctx(git_repo)
    report = _identity_gate_report(schema_version="2.0", kind="patchlet_report")
    result, _ = _ingest_identity_gate_report(ctx, report)
    assert result["normalized_failure_signature"] == "WORKER_REPORT_INVALID_KIND"


def test_v1_rejection_never_writes_canonical_report(git_repo: Path):
    ctx = _ctx(git_repo)
    result, _ = _ingest_identity_gate_report(ctx, _identity_gate_report())
    assert result["canonical_report_path"] is None
    assert not (ctx.paths.reports_dir / "P0001.json").exists()


def _v2_extension_report(**extensions) -> dict:
    report = _identity_gate_report(
        schema_version="2.0",
        kind="worker_patchlet_report",
    )
    report.update(extensions)
    return report


def _ingest_v2_extension(ctx, **extensions):
    return _ingest_identity_gate_report(ctx, _v2_extension_report(**extensions))[0]


def test_acceptance_criteria_result_is_unknown_v2_extension(git_repo: Path):
    ctx = _ctx(git_repo)
    result = _ingest_v2_extension(
        ctx,
        acceptance_criteria_result="PASS: worker claims success",
    )
    assert result["unknown_fields"] == ["acceptance_criteria_result"]
    assert result["unknown_field_status"] == "WARNING"
    assert result["report_reorganization_used"] is True


def test_acceptance_criteria_result_value_is_never_normalized(git_repo: Path):
    ctx = _ctx(git_repo)
    result = _ingest_v2_extension(
        ctx,
        acceptance_criteria_result="PASS: worker claims success",
    )
    canonical = read_json(ctx.root / result["canonical_report_path"])
    assert canonical["acceptance_criteria_result"] == "PASS: worker claims success"


def test_acceptance_criteria_result_never_adds_raw_or_detail_fields(git_repo: Path):
    ctx = _ctx(git_repo)
    result = _ingest_v2_extension(
        ctx,
        acceptance_criteria_result="PASS: worker claims success",
    )
    canonical = read_json(ctx.root / result["canonical_report_path"])
    assert "acceptance_criteria_result_raw" not in canonical
    assert "acceptance_criteria_result_detail" not in canonical
    assert "acceptance_criteria_result_status_prefix" not in canonical


def test_acceptance_criteria_result_never_enters_normalization_kinds(git_repo: Path):
    ctx = _ctx(git_repo)
    result = _ingest_v2_extension(
        ctx,
        acceptance_criteria_result="PASS: worker claims success",
    )
    assert "acceptance_criteria_result_status_prefix" not in result["normalization_kinds"]
    assert "acceptance_criteria_result_normalization" not in result


def test_acceptance_criteria_result_never_emits_normalized_status_event(git_repo: Path):
    ctx = _ctx(git_repo)
    _ingest_v2_extension(
        ctx,
        acceptance_criteria_result="PASS: worker claims success",
    )
    assert not any(
        event["event_type"] == "report_ingestion_normalized_status"
        for event in read_operator_events(ctx.root)
    )


def test_acceptance_criteria_result_never_changes_report_acceptance(git_repo: Path):
    ctx = _ctx(git_repo)
    result = _ingest_v2_extension(
        ctx,
        acceptance_criteria_result="PASS: worker claims success",
    )
    assert result["accepted"] is True


def test_worker_supplied_semantic_claims_is_unknown_extension(git_repo: Path):
    ctx = _ctx(git_repo)
    result = _ingest_v2_extension(
        ctx,
        worker_semantic_claims=[{"claim_id": "worker-invented"}],
    )
    assert result["unknown_fields"] == ["worker_semantic_claims"]
    assert result["unknown_field_status"] == "WARNING"


def test_worker_supplied_semantic_claims_never_survives_as_canonical_authority(git_repo: Path):
    ctx = _ctx(git_repo)
    result = _ingest_v2_extension(
        ctx,
        worker_semantic_claims=[{"claim_id": "worker-invented"}],
    )
    canonical = read_json(ctx.root / result["canonical_report_path"])
    assert {"claim_id": "worker-invented"} not in canonical.get("worker_semantic_claims", [])


def test_worker_supplied_semantic_claims_is_replaced_by_normalized_claims(git_repo: Path):
    ctx = _ctx(git_repo)
    report = _v2_extension_report(
        worker_semantic_claims=[{"claim_id": "worker-invented"}],
        semantic_goal_results=[
            {
                "goal_item_id": "GI001",
                "result": "app.py app=requested_state current slice is ready",
            }
        ],
    )
    result, _ = _ingest_identity_gate_report(ctx, report)
    canonical = read_json(ctx.root / result["canonical_report_path"])
    assert {"claim_id": "worker-invented"} not in canonical["worker_semantic_claims"]
    assert canonical["worker_semantic_claims"]


def test_worker_supplied_semantic_claims_without_semantic_results_is_removed(git_repo: Path):
    ctx = _ctx(git_repo)
    report = _v2_extension_report(
        worker_semantic_claims=[{"claim_id": "worker-invented"}],
    )
    report.pop("semantic_goal_results")
    result, _ = _ingest_identity_gate_report(ctx, report)
    canonical = read_json(ctx.root / result["canonical_report_path"])
    assert "worker_semantic_claims" not in canonical


def test_derived_semantic_claims_are_created_only_by_normalizer(git_repo: Path):
    ctx = _ctx(git_repo)
    report = _v2_extension_report()
    report.pop("semantic_goal_results")
    result, _ = _ingest_identity_gate_report(ctx, report)
    canonical = read_json(ctx.root / result["canonical_report_path"])
    assert "worker_semantic_claims" not in canonical


def test_raw_worker_semantic_claims_remain_available_only_in_raw_report(git_repo: Path):
    ctx = _ctx(git_repo)
    result = _ingest_v2_extension(
        ctx,
        worker_semantic_claims=[{"claim_id": "worker-invented"}],
    )
    raw = read_json(ctx.paths.reports_dir / "P0001.raw.json")
    canonical = read_json(ctx.root / result["canonical_report_path"])
    assert raw["worker_semantic_claims"] == [{"claim_id": "worker-invented"}]
    assert {"claim_id": "worker-invented"} not in canonical.get("worker_semantic_claims", [])


def test_changed_runtime_file_is_unknown_v2_extension(git_repo: Path):
    ctx = _ctx(git_repo)
    source = git_repo / "P0001.alias.json"
    write_json(source, _report_with_changed_runtime_file_alias())

    result = ingest_patchlet_report(
        ctx,
        patchlet={
            "patchlet_id": "P0001",
            "goal_item_ids": ["GI001"],
            "proof_obligation_ids": ["PO001"],
            "probe_ids": ["GP001"],
        },
        attempt_id="P0001_attempt1",
        report_path=source,
    )

    assert result["unknown_fields"] == ["changed_runtime_file"]
    assert "legacy_field_mappings" not in result


def test_changed_runtime_file_never_populates_changed_product_runtime_file(git_repo: Path):
    ctx = _ctx(git_repo)
    source = git_repo / "P0001.alias.json"
    write_json(source, _report_with_changed_runtime_file_alias())

    result = ingest_patchlet_report(
        ctx,
        patchlet={
            "patchlet_id": "P0001",
            "goal_item_ids": ["GI001"],
            "proof_obligation_ids": ["PO001"],
            "probe_ids": ["GP001"],
        },
        attempt_id="P0001_attempt1",
        report_path=source,
    )

    canonical = read_json(ctx.paths.reports_dir / "P0001.json")
    assert result["accepted"] is False
    assert "changed_product_runtime_file" not in canonical


def test_report_ingestion_preserves_raw_report(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    assert (ctx.paths.reports_dir / "P0001.raw.json").exists()


def test_p0005_v2_unknown_acceptance_criteria_result_is_warning_and_does_not_block(git_repo: Path):
    ctx = _ctx(git_repo)
    scenario = ctx.paths.workflow_dir / "mock" / "next_patchlet_result.json"
    scenario.parent.mkdir(parents=True, exist_ok=True)
    scenario.write_text(json.dumps({"handoff_override": {
        "acceptance_criteria_result": {"status": "PASS"},
    }}), encoding="utf-8")

    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    assert result.status != "FAILED_WITH_EVIDENCE"
    raw_path = ctx.paths.reports_dir / "P0001.raw.json"
    ingestion = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/report_ingestion_result.json")
    assert raw_path.read_bytes() == raw_path.read_bytes()
    assert ingestion["raw_envelope"]["parseable"] is True
    assert ingestion["unknown_fields"] == ["acceptance_criteria_result"]
    assert ingestion["unknown_field_status"] == "WARNING"
    assert ingestion["report_reorganization_used"] is True
    assert ingestion["report_reorganization_result"] == "ACCEPTED"
    assert read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/worker_report_integrity_result.json")["accepted"] is True
    assert not any("repair" in path.name.lower() for path in ctx.paths.patchlets_dir.glob("*.json"))


def test_v2_report_without_acceptance_criteria_result_is_valid_and_no_repair(git_repo: Path):
    ctx = _ctx(git_repo)
    report = {
        "schema_version": "2.0", "kind": "worker_patchlet_report", "patchlet_id": "P0001",
        "status": "COMPLETE", "changed_product_runtime_file": "app.py", "changed_artifact_files": [],
        "probe_commands": ["python .artifacts/probes/P0001/probe.py"],
        "deterministic_run_counts": {"baseline": "5/5", "proof_of_fix": "5/5", "negative_controls": "5/5"},
        "root_cause_classification": {
            "observed_failure": "baseline failed", "immediate_cause": "wrong value",
            "why_immediate_cause_happened": "stale implementation", "deeper_owner_boundary": "app.py",
            "producer_transformer_consumer_boundary": "app.py -> probe",
            "not_downstream_of_unprobed_state_proof": "direct probe", "negative_control_proof": "adjacent values unchanged",
            "recursive_why_audit": ["why1", "why2"],
        },
        "before_after_state": [], "row_ledger": [], "trace_ledger": [], "cleanup_proof": "clean",
        "probe_artifact_refs": [{"patchlet_id": "P0001", "probe_root": ".artifacts/probes/P0001", "run_id": "default"}],
        "semantic_goal_results": [],
    }
    source = git_repo / "P0001.v2-no-acceptance.json"
    write_json(source, report)
    result = ingest_patchlet_report(ctx, patchlet={"patchlet_id": "P0001", "goal_item_ids": ["GI001"], "proof_obligation_ids": ["PO001"], "probe_ids": ["GP001"]}, attempt_id="P0001_attempt1", report_path=source)
    assert result["accepted"] is True, json.dumps(result, indent=2)
    assert result["unknown_fields"] == []
    assert result["validation"]["valid"] is True
    assert not any("repair" in path.name.lower() for path in ctx.paths.patchlets_dir.glob("*.json"))


@pytest.mark.parametrize("repeat", range(5))
def test_exact_p0005_attempt1_report_ingestion_identity_and_hash(git_repo: Path, repeat: int):
    ctx = _ctx(git_repo)
    report = {
        "schema_version": "2.0", "kind": "worker_patchlet_report", "patchlet_id": "P0005",
        "status": "COMPLETE", "changed_product_runtime_file": "owner.mjs",
        "changed_artifact_files": [], "probe_commands": ["probe GP005"],
        "deterministic_run_counts": {"baseline": "1/1", "negative_controls": "1/1", "proof_of_fix": "1/1"}, "root_cause_classification": {
            "observed_failure": "observed", "immediate_cause": "cause", "why_immediate_cause_happened": "why",
            "deeper_owner_boundary": "owner.mjs", "producer_transformer_consumer_boundary": "boundary",
            "not_downstream_of_unprobed_state_proof": "direct", "negative_control_proof": "negative",
            "recursive_why_audit": ["why"],
        },
        "before_after_state": [], "row_ledger": [], "trace_ledger": [],
        "cleanup_proof": "clean", "semantic_goal_results": [],
        "probe_artifact_refs": [{"patchlet_id": "P0005", "probe_root": ".artifacts/probes/P0005", "run_id": "default"}],
        "acceptance_criteria_result": {"status": "PASS"},
    }
    source = git_repo / "P0005.worker.json"
    write_json(source, report)
    expected_bytes = source.read_bytes()
    result = ingest_patchlet_report(ctx, patchlet={
        "patchlet_id": "P0005", "goal_item_ids": ["GI005"],
        "proof_obligation_ids": ["PO005"], "probe_ids": ["GP005"],
    }, attempt_id="P0005_attempt1", report_path=source)
    assert result["accepted"] is True, json.dumps(result, indent=2)
    assert result["attempt_id"] == "P0005_attempt1"
    assert result["patchlet_id"] == "P0005"
    assert (ctx.paths.reports_dir / "P0005.raw.json").read_bytes() == expected_bytes
    assert result["raw_report_sha256"] == hashlib.sha256(expected_bytes).hexdigest()
    assert result["unknown_fields"] == ["acceptance_criteria_result"]


def test_report_ingestion_writes_canonical_report(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    report = read_json(ctx.paths.reports_dir / "P0001.json")
    assert isinstance(report["probe_artifact_refs"][0], dict)


def test_report_ingestion_normalizes_probe_ref_strings(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json", ".artifacts/probes/P0001/run_001/after_state.json"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    result = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/report_ingestion_result.json")
    assert result["normalization_applied"] is True
    assert result["canonical_probe_artifact_refs"][0]["files"][0]["path"].endswith("after_state.json")


def test_report_ingestion_records_raw_and_canonical_paths(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    result = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/report_ingestion_result.json")
    assert result["raw_report_path"] == ".codex-orchestrator/reports/P0001.raw.json"
    assert result["canonical_report_path"] == ".codex-orchestrator/reports/P0001.json"


def test_report_ingestion_records_normalization_kinds(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    result = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/report_ingestion_result.json")
    assert result["normalization_kinds"] == ["probe_artifact_refs_string_paths_to_objects"]


def test_report_ingestion_writes_result_json(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert (ctx.paths.runs_dir / "P0001_attempt1/gates/report_ingestion_result.json").exists()


def test_report_ingestion_writes_validation_errors_json(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert (ctx.paths.runs_dir / "P0001_attempt1/gates/report_validation_errors.json").exists()


def test_report_ingestion_result_schema_validates(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert validate_json_file(ctx.paths.runs_dir / "P0001_attempt1/gates/report_ingestion_result.json", "report_ingestion_result.schema.json") == []


def test_report_ingestion_errors_schema_validates(git_repo: Path):
    ctx = _ctx(git_repo)
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    assert validate_json_file(ctx.paths.runs_dir / "P0001_attempt1/gates/report_validation_errors.json", "report_validation_errors.schema.json") == []


def test_report_ingestion_rejects_unsafe_path(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, ["/etc/passwd"])

    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    errors = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/report_validation_errors.json")["errors"]
    assert result.status == "FAILED_WITH_EVIDENCE"
    assert errors[0]["normalized_signature"] == "probe_artifact_refs_unsafe_path"


def test_report_ingestion_rejects_missing_probe_file(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/missing.txt"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    errors = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/report_validation_errors.json")["errors"]
    assert errors[0]["normalized_signature"] == "probe_artifact_refs_missing_file"


def test_report_ingestion_accepts_inventory_known_skipped_limit_ref_with_warning(git_repo: Path):
    ctx = _ctx(git_repo)
    skipped_path = ".artifacts/probes/P0001/run_001/zz-overflow/evidence-57.txt"
    scenario = ctx.paths.workflow_dir / "mock" / "next_patchlet_result.json"
    scenario.write_text(
        json.dumps(
            {
                "extra_worker_evidence_file_count": 65,
                "report_production_override": {
                    "probe_artifact_refs": [
                        {
                            "patchlet_id": "P0001",
                            "probe_root": ".artifacts/probes/P0001/run_001/zz-overflow",
                            "run_id": "zz-overflow",
                            "files": [
                                {
                                    "path": skipped_path,
                                    "kind": "diagnostic",
                                    "sha256": "f" * 64,
                                    "size_bytes": 999999,
                                }
                            ],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    ingestion = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/report_ingestion_result.json")
    normalization = read_json(
        ctx.paths.runs_dir / "P0001_attempt1/gates/probe_artifact_refs_normalization_result.json"
    )
    canonical = read_json(ctx.paths.reports_dir / "P0001.json")
    assert result.status == "VERIFIED_NO_CHANGE_NEEDED"
    assert ingestion["accepted"] is True
    assert ingestion["probe_artifact_ref_warning_count"] == 1
    assert normalization["warnings"] == [
        f"probe_artifact_ref_not_durable:SKIPPED_LIMIT:{skipped_path}"
    ]
    assert canonical["probe_artifact_refs"][0]["files"] == []
    assert not (ctx.root / skipped_path).exists()


def test_report_only_retry_does_not_rerun_task_worker_or_mutate_frozen_candidate(git_repo: Path):
    ctx = _ctx(git_repo)
    scenario = ctx.paths.workflow_dir / "mock" / "next_patchlet_result.json"
    scenario.write_text(
        json.dumps(
            {
                "status": "COMPLETE",
                "change_allowed_product": True,
                "report_production_override": {
                    "changed_product_runtime_file": "other.py",
                },
            }
        ),
        encoding="utf-8",
    )

    result = run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    run_dir = ctx.paths.runs_dir / "P0001_attempt1"
    first = read_json(run_dir / "gates/report_production_worker/attempt_1/report_production_trace.json")
    second = read_json(run_dir / "gates/report_production_worker/attempt_2/report_production_trace.json")
    events = read_operator_events(ctx.root)
    assert result.status == "FAILED_WITH_EVIDENCE"
    assert first["candidate_patch_sha256"] == second["candidate_patch_sha256"]
    assert first["task_handoff_sha256"] == second["task_handoff_sha256"]
    assert first["deterministic_validation"]["valid"] is False
    assert second["deterministic_validation"]["valid"] is False
    assert sum(event["event_type"] == "patchlet_worker_started" for event in events) == 1
    assert sum(event["event_type"] == "report_production_worker_failed" for event in events) == 2
    assert not (run_dir / "patch_promotion/clean_candidate_promotion_result.json").exists()


def test_report_ingestion_rejects_patchlet_mismatch(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json", ".artifacts/probes/P9999/file.txt"])
    bad = git_repo / ".artifacts/probes/P9999/file.txt"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("x", encoding="utf-8")

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    errors = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/report_validation_errors.json")["errors"]
    assert any(error["normalized_signature"] == "probe_artifact_refs_patchlet_mismatch" for error in errors)


def test_report_ingestion_rejects_symlink_escape(git_repo: Path, tmp_path: Path):
    ctx = _ctx(git_repo)
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    link = git_repo / ".artifacts/probes/P0001/symlink_to_outside"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside)
    _scenario(ctx, [".artifacts/probes/P0001/symlink_to_outside"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    errors = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/report_validation_errors.json")["errors"]
    assert errors[0]["normalized_signature"] == "probe_artifact_refs_unsafe_path"


def test_report_ingestion_emits_normalized_operator_event(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    assert any(event["event_type"] == "report_ingestion_normalized" for event in read_operator_events(ctx.root))


def test_report_ingestion_emits_failed_operator_event(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, ["/etc/passwd"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    events = [event for event in read_operator_events(ctx.root) if event["event_type"] == "report_ingestion_failed"]
    assert events[-1]["details"]["failure_signature"] == "probe_artifact_refs_unsafe_path"


def test_wrapper_gate_uses_canonical_report_after_ingestion(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, [".artifacts/probes/P0001/run_001/before_state.json"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    gate = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/wrapper_gate_result.json")
    assert gate["report_gate"] == "pass"
    assert gate["accepted"] is True


def test_wrapper_gate_rejects_failed_ingestion_with_structured_error(git_repo: Path):
    ctx = _ctx(git_repo)
    _scenario(ctx, ["/etc/passwd"])

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    gate = read_json(ctx.paths.runs_dir / "P0001_attempt1/gates/wrapper_gate_result.json")
    failure = read_json(ctx.paths.failures_dir / "F0001.json")
    assert gate["accepted"] is False
    assert failure["failure_signature"] == "probe_artifact_refs_unsafe_path"
