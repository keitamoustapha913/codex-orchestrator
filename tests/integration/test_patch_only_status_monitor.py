from __future__ import annotations

from codex_orchestrator.jsonio import read_json, write_json
from codex_orchestrator.operator_events import append_operator_event, read_operator_events
from codex_orchestrator.patch_promotion import prepare_clean_patch_candidate, write_clean_candidate_promotion_result
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.status import status
from test_patch_proposal_extraction import _ctx_and_run


def _ctx_with_debris_status(tmp_path):
    ctx, run_ctx, patchlet = _ctx_and_run(tmp_path)
    master = ctx.root / "master_prompt.md"
    master.write_text("Update app.py only.\n", encoding="utf-8")
    init_workflow(ctx, master=master, invocation_argv=["cxor", "init"])
    (run_ctx.execution_root / "app.py").write_text("def main():\n    return 'new'\n", encoding="utf-8")
    (run_ctx.execution_root / ".json_validation.out").write_text("{}\n", encoding="utf-8")
    staged = run_ctx.worker_evidence_dir / "GP001" / "run_001"
    staged.mkdir(parents=True, exist_ok=True)
    (staged / "diagnostic.json").write_text("{}\n", encoding="utf-8")
    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)
    write_json(
        run_ctx.run_dir / "gates" / "independent_probe_rerun_result.json",
        {"schema_version": "1.0", "kind": "independent_probe_rerun_result", "candidate_scope": "clean_reconstruction", "accepted": True},
    )
    write_clean_candidate_promotion_result(
        ctx=ctx,
        run_ctx=run_ctx,
        patchlet=patchlet,
        patch_promotion_result=result,
        base_integration_ref="refs/cxor/runs/R0001/integration",
        integration_ref_before="a" * 40,
        expected_old_commit="a" * 40,
        candidate_commit="b" * 40,
        candidate_tree="c" * 40,
        integration_ref_after="b" * 40,
    )
    write_json(
        run_ctx.run_dir / "patch_promotion" / "worker_sandbox_disposal_result.json",
        {
            "schema_version": "1.0",
            "kind": "worker_sandbox_disposal_result",
            "candidate_scope": "raw_worker_sandbox",
            "patchlet_id": "P0001",
            "attempt_id": "P0001_attempt1",
            "sandbox_root": str(run_ctx.execution_root),
            "attempt_result": "accepted",
            "promotion_result": True,
            "evidence_retained": True,
            "excluded_debris_metadata_retained": True,
            "sandbox_archived": False,
            "cleanup_attempted": True,
            "cleanup_succeeded": True,
            "remaining_path_exists": False,
            "errors": [],
        },
    )
    return ctx


def test_status_reports_debris_as_non_blocking(tmp_path):
    payload = status(_ctx_with_debris_status(tmp_path))["patch_promotion"]
    assert payload["worker_hygiene_status"] == "DEBRIS_PRESENT"
    assert payload["product_result"] == "accepted"
    assert payload["promotion_blocked"] is False


def test_status_reports_sandbox_debris_count(tmp_path):
    payload = status(_ctx_with_debris_status(tmp_path))["patch_promotion"]
    assert payload["sandbox_debris_count"] == 2


def test_status_separates_product_evidence_debris_and_canonical_counts(tmp_path):
    payload = status(_ctx_with_debris_status(tmp_path))["patch_promotion"]
    assert payload["allowed_product_change_count"] == 1
    assert payload["diagnostic_evidence_files"] == 1
    assert payload["sandbox_debris_count"] == 2
    assert payload["canonical_patch_paths"] == 1
    assert payload["promotion_blocked"] is False


def test_status_never_reports_legacy_evidence_count(tmp_path):
    payload = status(_ctx_with_debris_status(tmp_path))["patch_promotion"]
    assert "legacy_evidence_files" not in payload


def test_status_reports_patch_proposal_status(tmp_path):
    assert status(_ctx_with_debris_status(tmp_path))["patch_promotion"]["patch_proposal_status"] == "ACCEPTED"


def test_status_reports_clean_reconstruction_status(tmp_path):
    assert status(_ctx_with_debris_status(tmp_path))["patch_promotion"]["clean_reconstruction_status"] == "ACCEPTED"


def test_status_reports_independent_proof_status(tmp_path):
    assert status(_ctx_with_debris_status(tmp_path))["patch_promotion"]["independent_proof_status"] == "ACCEPTED"


def test_status_reports_promotion_status(tmp_path):
    assert status(_ctx_with_debris_status(tmp_path))["patch_promotion"]["promotion_status"] == "ACCEPTED"


def test_status_reports_raw_sandbox_not_promoted(tmp_path):
    assert status(_ctx_with_debris_status(tmp_path))["patch_promotion"]["raw_worker_sandbox_promoted"] is False


def test_status_reports_disposal_result(tmp_path):
    assert status(_ctx_with_debris_status(tmp_path))["patch_promotion"]["sandbox_disposal_status"] == "COMPLETE"


def test_status_json_validates_against_cli_contract(tmp_path):
    payload = status(_ctx_with_debris_status(tmp_path))
    assert payload["kind"] == "operator_status"
    assert payload["patch_promotion"]["candidate_scopes"]["worker_hygiene"] == "raw_worker_sandbox"


def _ctx_with_monitor_events(tmp_path):
    ctx = _ctx_with_debris_status(tmp_path)
    for event_type, severity, summary in [
        ("worker_sandbox_debris_inventoried", "info", "Worker sandbox debris inventoried."),
        ("worker_sandbox_debris_discarded", "info", "Worker sandbox debris discarded."),
        ("patch_proposal_extracted", "success", "Canonical patch proposal extracted."),
        ("clean_candidate_reconstructed", "success", "Clean candidate reconstructed."),
        ("clean_candidate_durably_promoted", "success", "Clean reconstructed candidate promoted."),
        ("worker_sandbox_disposed", "success", "Worker sandbox disposed."),
    ]:
        append_operator_event(
            ctx.root,
            event_type=event_type,
            severity=severity,
            stage="PATCHLET_EXECUTION_IN_PROGRESS",
            summary=summary,
            patchlet_id="P0001",
            attempt_id="P0001_attempt1",
        )
    return ctx


def test_monitor_surfaces_sandbox_debris_discarded_event(tmp_path):
    events = read_operator_events(_ctx_with_monitor_events(tmp_path).root)
    assert any(event["event_type"] == "worker_sandbox_debris_discarded" for event in events)


def test_monitor_does_not_create_failure_event_for_debris(tmp_path):
    events = read_operator_events(_ctx_with_monitor_events(tmp_path).root)
    debris_events = [event for event in events if "sandbox_debris" in event["event_type"]]
    assert debris_events
    assert all(event["severity"] == "info" for event in debris_events)
    assert not any(event["event_type"] == "patchlet_failed_with_evidence" for event in events)


def test_monitor_surfaces_patch_proposal_event(tmp_path):
    events = read_operator_events(_ctx_with_monitor_events(tmp_path).root)
    assert any(event["event_type"] == "patch_proposal_extracted" for event in events)


def test_monitor_surfaces_clean_reconstruction_event(tmp_path):
    events = read_operator_events(_ctx_with_monitor_events(tmp_path).root)
    assert any(event["event_type"] == "clean_candidate_reconstructed" for event in events)


def test_monitor_surfaces_clean_promotion_event(tmp_path):
    events = read_operator_events(_ctx_with_monitor_events(tmp_path).root)
    assert any(event["event_type"] == "clean_candidate_durably_promoted" for event in events)


def test_monitor_surfaces_sandbox_disposal_event(tmp_path):
    events = read_operator_events(_ctx_with_monitor_events(tmp_path).root)
    assert any(event["event_type"] == "worker_sandbox_disposed" for event in events)


def test_monitor_does_not_report_debris_only_attempt_as_product_failure(tmp_path):
    ctx = _ctx_with_monitor_events(tmp_path)
    payload = status(ctx)["patch_promotion"]
    assert payload["worker_hygiene_status"] == "DEBRIS_PRESENT"
    assert payload["product_result"] == "accepted"


def test_status_reports_allowed_path_violation_as_blocking(tmp_path):
    ctx = _ctx_with_monitor_events(tmp_path)
    run_dir = ctx.paths.runs_dir / "P0001_attempt1"
    hygiene_path = run_dir / "gates" / "worker_sandbox_hygiene_result.json"
    hygiene = read_json(hygiene_path)
    hygiene["status"] = "ALLOWED_PATH_VIOLATION"
    hygiene["allowed_path_violation_count"] = 1
    hygiene["allowed_path_violations"] = [{"path": "app.py", "classification": "ALLOWED_PRODUCT_PATH_VIOLATION"}]
    hygiene["promotion_blocked"] = True
    write_json(hygiene_path, hygiene)
    promotion_path = run_dir / "patch_promotion" / "clean_candidate_promotion_result.json"
    promotion = read_json(promotion_path)
    promotion["promotion_accepted"] = False
    write_json(promotion_path, promotion)
    payload = status(ctx)["patch_promotion"]
    assert payload["worker_hygiene_status"] == "ALLOWED_PATH_VIOLATION"
    assert payload["allowed_path_violation_count"] == 1
    assert payload["promotion_blocked"] is True


def test_status_reports_containment_violation_as_blocking(tmp_path):
    ctx = _ctx_with_monitor_events(tmp_path)
    hygiene_path = ctx.paths.runs_dir / "P0001_attempt1" / "gates" / "worker_sandbox_hygiene_result.json"
    hygiene = read_json(hygiene_path)
    hygiene["status"] = "CONTAINMENT_VIOLATION"
    hygiene["containment_violation_count"] = 1
    hygiene["containment_violations"] = [{"path": "../outside", "classification": "SANDBOX_CONTAINMENT_VIOLATION"}]
    hygiene["promotion_blocked"] = True
    write_json(hygiene_path, hygiene)

    payload = status(ctx)["patch_promotion"]

    assert payload["worker_hygiene_status"] == "CONTAINMENT_VIOLATION"
    assert payload["containment_violation_count"] == 1
    assert payload["promotion_blocked"] is True
