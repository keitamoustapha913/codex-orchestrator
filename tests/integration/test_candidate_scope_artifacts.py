from __future__ import annotations

from conftest import read_json

from codex_orchestrator.jsonio import write_json
from codex_orchestrator.patch_promotion import (
    prepare_clean_patch_candidate,
    write_clean_candidate_promotion_result,
    write_independent_proof_effective_source_manifest,
)
from test_patch_proposal_extraction import _ctx_and_run


def _accepted_result(tmp_path):
    ctx, run_ctx, patchlet = _ctx_and_run(tmp_path)
    (run_ctx.execution_root / "app.py").write_text("def main():\n    return 'new'\n", encoding="utf-8")
    (run_ctx.execution_root / ".json_validation.out").write_text("{}\n", encoding="utf-8")
    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)
    probe_plan = {"probes": [{"probe_id": "GP001", "obligation_ids": ["PO001"], "command": "python app.py"}]}
    source = write_independent_proof_effective_source_manifest(
        run_ctx=run_ctx,
        patchlet=patchlet,
        patch_manifest=result.patch_manifest,
        verification_root=result.verification_root,
        probe_plan=probe_plan,
    )
    write_json(
        run_ctx.run_dir / "gates" / "independent_probe_rerun_result.json",
        {"schema_version": "1.0", "kind": "independent_probe_rerun_result", "candidate_scope": "clean_reconstruction", "accepted": True},
    )
    write_json(
        run_ctx.run_dir / "gates" / "goal_coverage_gate_result.json",
        {"schema_version": "1.0", "kind": "goal_coverage_gate_result", "candidate_scope": "clean_reconstruction", "accepted": True},
    )
    return ctx, run_ctx, result, source


def test_worker_hygiene_result_is_raw_worker_sandbox(tmp_path):
    _ctx, _run_ctx, result, _source = _accepted_result(tmp_path)
    assert result.hygiene_result["candidate_scope"] == "raw_worker_sandbox"


def test_patch_manifest_is_patch_proposal(tmp_path):
    _ctx, _run_ctx, result, _source = _accepted_result(tmp_path)
    assert result.patch_manifest["candidate_scope"] == "patch_proposal"


def test_patch_validation_is_patch_proposal(tmp_path):
    _ctx, _run_ctx, result, _source = _accepted_result(tmp_path)
    assert result.patch_validation["candidate_scope"] == "patch_proposal"


def test_reconstruction_result_is_clean_reconstruction(tmp_path):
    _ctx, _run_ctx, result, _source = _accepted_result(tmp_path)
    assert result.reconstruction_result["candidate_scope"] == "clean_reconstruction"


def test_effective_source_manifest_is_clean_reconstruction(tmp_path):
    _ctx, _run_ctx, _result, source = _accepted_result(tmp_path)
    assert source["candidate_scope"] == "clean_reconstruction"


def test_clean_independent_proof_is_clean_reconstruction(tmp_path):
    _ctx, run_ctx, _result, _source = _accepted_result(tmp_path)
    proof = read_json(run_ctx.run_dir / "gates" / "independent_probe_rerun_result.json")
    assert proof["candidate_scope"] == "clean_reconstruction"


def test_clean_goal_coverage_is_clean_reconstruction(tmp_path):
    _ctx, run_ctx, _result, _source = _accepted_result(tmp_path)
    coverage = read_json(run_ctx.run_dir / "gates" / "goal_coverage_gate_result.json")
    assert coverage["candidate_scope"] == "clean_reconstruction"


def test_promotion_result_is_promoted_candidate(tmp_path):
    ctx, run_ctx, result, _source = _accepted_result(tmp_path)
    write_clean_candidate_promotion_result(
        ctx=ctx,
        run_ctx=run_ctx,
        patchlet={"patchlet_id": "P0001"},
        patch_promotion_result=result,
        base_integration_ref="refs/cxor/runs/R0001/integration",
        integration_ref_before="a" * 40,
        expected_old_commit="a" * 40,
        candidate_commit="b" * 40,
        candidate_tree="c" * 40,
        integration_ref_after="b" * 40,
    )
    promotion = read_json(result.promotion_result_path)
    assert promotion["candidate_scope"] == "promoted_candidate"


def test_preparation_result_is_clean_reconstruction(tmp_path):
    _ctx, _run_ctx, result, _source = _accepted_result(tmp_path)
    preparation = read_json(result.preparation_result_path)
    assert preparation["candidate_scope"] == "clean_reconstruction"
    assert preparation["durable_integration_updated"] is False


def test_rc6m_reader_rejects_missing_authoritative_scope(tmp_path):
    _ctx, _run_ctx, result, _source = _accepted_result(tmp_path)
    assert result.reconstruction_result["candidate_scope"]
