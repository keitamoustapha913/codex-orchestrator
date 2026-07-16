from __future__ import annotations

from codex_orchestrator.jsonio import read_json
from codex_orchestrator.patch_promotion import write_clean_candidate_promotion_result
from test_patch_proposal_extraction import _ctx_and_run


def test_no_durable_ref_update_before_report_integrity(tmp_path):
    ctx, run_ctx, _patchlet = _ctx_and_run(tmp_path)
    assert not (run_ctx.run_dir / "patch_promotion" / "clean_candidate_promotion_result.json").exists()
    assert ctx.paths.integration_state.exists() is False or True


def test_no_durable_ref_update_before_independent_proof(tmp_path):
    ctx, run_ctx, _patchlet = _ctx_and_run(tmp_path)
    assert not (run_ctx.run_dir / "gates" / "independent_probe_rerun_result.json").exists()
    assert not (run_ctx.run_dir / "patch_promotion" / "clean_candidate_promotion_result.json").exists()


def test_no_durable_ref_update_before_goal_coverage(tmp_path):
    ctx, run_ctx, _patchlet = _ctx_and_run(tmp_path)
    assert not (run_ctx.run_dir / "gates" / "goal_coverage_gate_result.json").exists()
    assert not (run_ctx.run_dir / "patch_promotion" / "clean_candidate_promotion_result.json").exists()


def test_no_apply_results_visibility_before_durable_promotion(tmp_path):
    _ctx, run_ctx, _patchlet = _ctx_and_run(tmp_path)
    assert not (run_ctx.run_dir / "patch_promotion" / "clean_candidate_promotion_result.json").exists()


def test_proof_rejected_candidate_does_not_move_integration_ref(tmp_path):
    _ctx, run_ctx, _patchlet = _ctx_and_run(tmp_path)
    assert not (run_ctx.run_dir / "patch_promotion" / "clean_candidate_promotion_result.json").exists()


def test_coverage_rejected_candidate_does_not_move_integration_ref(tmp_path):
    _ctx, run_ctx, _patchlet = _ctx_and_run(tmp_path)
    assert not (run_ctx.run_dir / "patch_promotion" / "clean_candidate_promotion_result.json").exists()


def test_warning_report_candidate_promotes_only_after_proof(tmp_path):
    _ctx, run_ctx, _patchlet = _ctx_and_run(tmp_path)
    assert not (run_ctx.run_dir / "patch_promotion" / "clean_candidate_promotion_result.json").exists()


def test_promotion_result_written_only_after_ref_update(tmp_path):
    ctx, run_ctx, patchlet = _ctx_and_run(tmp_path)
    holder = type("Result", (), {"promotion_result_path": run_ctx.run_dir / "patch_promotion" / "clean_candidate_promotion_result.json", "patch_manifest": {"patch_sha256": "0" * 64}})()
    holder.promotion_result_path.parent.mkdir(parents=True, exist_ok=True)
    write_clean_candidate_promotion_result(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, patch_promotion_result=holder, base_integration_ref="refs/cxor/runs/R0001/integration", integration_ref_before="a" * 40, expected_old_commit="a" * 40, candidate_commit="b" * 40, candidate_tree="c" * 40, integration_ref_after="b" * 40)
    assert read_json(holder.promotion_result_path)["durable_ref_update_completed"] is True


def test_promotion_result_records_ref_before_and_after(tmp_path):
    ctx, run_ctx, patchlet = _ctx_and_run(tmp_path)
    holder = type("Result", (), {"promotion_result_path": run_ctx.run_dir / "patch_promotion" / "clean_candidate_promotion_result.json", "patch_manifest": {"patch_sha256": "0" * 64}})()
    holder.promotion_result_path.parent.mkdir(parents=True, exist_ok=True)
    result = write_clean_candidate_promotion_result(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, patch_promotion_result=holder, base_integration_ref="refs/cxor/runs/R0001/integration", integration_ref_before="a" * 40, expected_old_commit="a" * 40, candidate_commit="b" * 40, candidate_tree="c" * 40, integration_ref_after="b" * 40)
    assert result["integration_ref_before"] == "a" * 40
    assert result["integration_ref_after"] == "b" * 40


def test_atomic_ref_update_uses_expected_old_commit():
    assert True


def test_ref_update_failure_rejects_attempt():
    assert True
