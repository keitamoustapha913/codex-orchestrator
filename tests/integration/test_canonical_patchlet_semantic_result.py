from __future__ import annotations

from types import SimpleNamespace

from codex_orchestrator.patch_promotion import build_canonical_patchlet_semantic_result


def _promotion_result(patch_validation=True, reconstruction=True, hygiene="CLEAN"):
    return SimpleNamespace(
        patch_validation={"accepted": patch_validation},
        reconstruction_result={"accepted": reconstruction, "base_tree": "t" * 40},
        hygiene_result={"status": hygiene},
        patch_manifest={"patch_sha256": "0" * 64},
    )


def _build(tmp_path, *, proof=True, coverage=True, patch=True, reconstruction=True):
    ctx = SimpleNamespace(root=tmp_path)
    run_ctx = SimpleNamespace(run_dir=tmp_path / ".codex-orchestrator" / "runs" / "P0001_attempt1")
    run_ctx.run_dir.mkdir(parents=True)
    patchlet = {"patchlet_id": "P0001", "goal_item_ids": ["GI001"], "proof_obligation_ids": ["PO001"], "probe_ids": ["GP001"], "allowed_product_runtime_file": "app.py", "current_slice_boundary": {"symbol": "main"}, "future_slice_boundaries": []}
    return build_canonical_patchlet_semantic_result(
        ctx=ctx,
        run_ctx=run_ctx,
        patchlet=patchlet,
        patch_promotion_result=_promotion_result(patch, reconstruction),
        worker_report_integrity_result={"accepted": True},
        worker_report_semantic_quality_result={"status": "INCOMPLETE"},
        independent_proof_result={"accepted": proof},
        goal_coverage_result={"accepted": coverage},
    )


def test_canonical_semantic_result_uses_patchlet_plan(tmp_path):
    assert _build(tmp_path)["goal_item_ids"] == ["GI001"]


def test_canonical_semantic_result_uses_patch_manifest(tmp_path):
    assert _build(tmp_path)["canonical_patch_sha256"] == "0" * 64


def test_canonical_semantic_result_uses_clean_candidate_tree(tmp_path):
    assert _build(tmp_path)["clean_candidate_tree"] == "t" * 40


def test_canonical_semantic_result_uses_independent_proof(tmp_path):
    assert _build(tmp_path, proof=False)["accepted"] is False


def test_canonical_semantic_result_uses_goal_coverage(tmp_path):
    assert _build(tmp_path, coverage=False)["accepted"] is False


def test_canonical_semantic_result_records_worker_report_quality(tmp_path):
    assert _build(tmp_path)["worker_report_semantic_status"] == "INCOMPLETE"


def test_incomplete_report_can_accept_only_after_proof_and_coverage(tmp_path):
    assert _build(tmp_path, proof=True, coverage=True)["accepted"] is True


def test_false_future_claim_cannot_expand_coverage(tmp_path):
    assert _build(tmp_path)["future_obligations_advanced"] == []


def test_canonical_semantic_result_rejects_failed_proof(tmp_path):
    assert _build(tmp_path, proof=False)["accepted"] is False


def test_canonical_semantic_result_rejects_failed_boundary_gate(tmp_path):
    assert _build(tmp_path, reconstruction=False)["accepted"] is False
