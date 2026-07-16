from __future__ import annotations

import subprocess
from pathlib import Path

import codex_orchestrator.patch_promotion as patch_promotion
from codex_orchestrator.integration_state import ensure_integration_state
from codex_orchestrator.patch_promotion import prepare_clean_patch_candidate
from codex_orchestrator.patchlet_run_context import PatchletRunContext
from codex_orchestrator.target_repo import resolve_target_repo


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout.strip()


def _containment_fixture(tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "app.py").write_text("VALUE = 'legacy'\n", encoding="utf-8")
    (target / "peer.py").write_text("PEER = 'original'\n", encoding="utf-8")
    _git(target, "init")
    _git(target, "config", "user.email", "test@example.invalid")
    _git(target, "config", "user.name", "Test User")
    _git(target, "add", ".")
    _git(target, "commit", "-m", "baseline")
    ctx = resolve_target_repo(repo=target)
    checkpoint = ensure_integration_state(ctx)["integration_sha"]
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    worker = sandbox / "worktree"
    _git(target, "worktree", "add", "--detach", str(worker), checkpoint)
    run_dir = target / ".codex-orchestrator" / "runs" / "P0001_attempt1"
    run_dir.mkdir(parents=True)
    run_ctx = PatchletRunContext(
        target_root=target,
        execution_root=worker,
        artifact_root=target,
        workflow_dir=target / ".codex-orchestrator",
        reports_dir=target / ".codex-orchestrator" / "reports",
        probe_dir=target / ".artifacts" / "probes",
        runs_dir=target / ".codex-orchestrator" / "runs",
        run_dir=run_dir,
        is_worktree=True,
        worktree_path=worker,
        execution_boundary_root=sandbox,
    )
    patchlet = {
        "patchlet_id": "P0001",
        "allowed_product_runtime_file": "app.py",
        "allowed_product_runtime_files": ["app.py"],
        "goal_item_ids": ["GI001"],
        "proof_obligation_ids": ["PO001"],
        "probe_ids": ["GP001"],
    }
    return ctx, run_ctx, patchlet


def _change_allowed(run_ctx: PatchletRunContext) -> None:
    (run_ctx.execution_root / "app.py").write_text("VALUE = 'new'\n", encoding="utf-8")


def _containment_entries(result) -> list[dict]:
    return [
        row
        for row in result.hygiene_result["change_classification_ledger"]
        if row["classification"] == "SANDBOX_CONTAINMENT_VIOLATION"
    ]


def _assert_containment_failure(result) -> None:
    assert result.accepted is False
    assert result.hygiene_result["promotion_blocked"] is True
    assert result.hygiene_result["status"] == "CONTAINMENT_VIOLATION"
    assert result.hygiene_result["containment_violation_count"] > 0
    entries = _containment_entries(result)
    assert entries
    assert all(row["blocking"] is True for row in entries)
    assert all(row["inside_execution_boundary"] is False for row in entries)
    assert all(row["classification"] != "SANDBOX_DEBRIS" for row in entries)


def test_path_traversal_outside_sandbox_is_containment_violation(tmp_path: Path, monkeypatch):
    ctx, run_ctx, patchlet = _containment_fixture(tmp_path)
    _change_allowed(run_ctx)
    outside = run_ctx.execution_root.parent / "escaped.txt"
    outside.write_text("escaped\n", encoding="utf-8")
    original = patch_promotion._status_entries
    monkeypatch.setattr(
        patch_promotion,
        "_status_entries",
        lambda root: original(root) + [("??", "../escaped.txt")],
    )

    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    _assert_containment_failure(result)
    assert any(row["path"] == "../escaped.txt" for row in _containment_entries(result))


def test_allowed_file_symlink_escape_is_containment_violation(tmp_path: Path):
    ctx, run_ctx, patchlet = _containment_fixture(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("outside\n", encoding="utf-8")
    (run_ctx.execution_root / "app.py").unlink()
    (run_ctx.execution_root / "app.py").symlink_to(outside)

    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    _assert_containment_failure(result)
    assert any(row["path"] == "app.py" for row in _containment_entries(result))


def test_non_allowlisted_symlink_escape_is_containment_violation(tmp_path: Path):
    ctx, run_ctx, patchlet = _containment_fixture(tmp_path)
    _change_allowed(run_ctx)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    (run_ctx.execution_root / "escape-link").symlink_to(outside)

    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    _assert_containment_failure(result)
    assert any(row["path"] == "escape-link" for row in _containment_entries(result))


def test_cross_repository_write_is_containment_violation(tmp_path: Path, monkeypatch):
    ctx, run_ctx, patchlet = _containment_fixture(tmp_path)
    _change_allowed(run_ctx)
    other_repo = tmp_path / "other-repository"
    other_repo.mkdir()
    outside = other_repo / "mutated.txt"
    outside.write_text("cross-repository write\n", encoding="utf-8")
    original = patch_promotion._status_entries
    monkeypatch.setattr(
        patch_promotion,
        "_status_entries",
        lambda root: original(root) + [("??", str(outside))],
    )

    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    _assert_containment_failure(result)
    assert any(row["path"] == str(outside) for row in _containment_entries(result))


def test_worker_evidence_path_outside_execution_boundary_is_containment_violation(tmp_path: Path):
    ctx, run_ctx, patchlet = _containment_fixture(tmp_path)
    _change_allowed(run_ctx)
    outside = tmp_path / "outside-evidence"
    outside.mkdir()
    (outside / "proof.json").write_text("{}\n", encoding="utf-8")
    (run_ctx.execution_boundary_root / "evidence").symlink_to(outside, target_is_directory=True)

    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    _assert_containment_failure(result)
    assert any("CXOR_WORKER_EVIDENCE_DIR" in row["path"] for row in _containment_entries(result))


def test_scratch_path_outside_execution_boundary_is_containment_violation(tmp_path: Path):
    ctx, run_ctx, patchlet = _containment_fixture(tmp_path)
    _change_allowed(run_ctx)
    outside = tmp_path / "outside-scratch"
    outside.mkdir()
    (outside / "data.tmp").write_text("temporary\n", encoding="utf-8")
    (run_ctx.execution_root / "scratch").symlink_to(outside, target_is_directory=True)

    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    _assert_containment_failure(result)
    assert any(row["path"] == "scratch" for row in _containment_entries(result))


def test_containment_violation_blocks_before_canonical_patch(tmp_path: Path):
    ctx, run_ctx, patchlet = _containment_fixture(tmp_path)
    _change_allowed(run_ctx)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    (run_ctx.execution_root / "escape-link").symlink_to(outside)

    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    _assert_containment_failure(result)
    assert result.patch_manifest["changed_paths"] == []
    assert result.diff_text == ""
    assert result.patch_validation["accepted"] is False


def test_containment_failure_is_not_classified_as_sandbox_debris(tmp_path: Path):
    ctx, run_ctx, patchlet = _containment_fixture(tmp_path)
    _change_allowed(run_ctx)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    (run_ctx.execution_root / "escape-link").symlink_to(outside)

    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    _assert_containment_failure(result)
    entry = next(row for row in result.hygiene_result["entries"] if row["path"] == "escape-link")
    assert entry["classification"] == "SANDBOX_CONTAINMENT_VIOLATION"
    assert entry not in result.hygiene_result["debris_entries"]
