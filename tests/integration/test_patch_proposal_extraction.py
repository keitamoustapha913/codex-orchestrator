from __future__ import annotations

import subprocess
from pathlib import Path

from codex_orchestrator.integration_state import ensure_integration_state
from codex_orchestrator.patch_promotion import (
    prepare_clean_patch_candidate,
    write_independent_proof_effective_source_manifest,
)
from codex_orchestrator.patchlet_run_context import PatchletRunContext
from codex_orchestrator.target_repo import resolve_target_repo


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout.strip()


def _ctx_and_run(tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "app.py").write_text("def main():\n    return 'legacy'\n", encoding="utf-8")
    (target / "README.md").write_text("support\n", encoding="utf-8")
    _git(target, "init")
    _git(target, "config", "user.email", "test@example.invalid")
    _git(target, "config", "user.name", "Test User")
    _git(target, "add", ".")
    _git(target, "commit", "-m", "baseline")
    ctx = resolve_target_repo(repo=target)
    state = ensure_integration_state(ctx)
    worker = tmp_path / "worker"
    _git(target, "worktree", "add", "--detach", str(worker), state["integration_sha"])
    run_dir = target / ".codex-orchestrator" / "runs" / "P0001_attempt1"
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
    )
    run_dir.mkdir(parents=True)
    return ctx, run_ctx, {
        "patchlet_id": "P0001",
        "allowed_product_runtime_file": "app.py",
        "goal_item_ids": ["GI001"],
        "proof_obligation_ids": ["PO001"],
        "probe_ids": ["GP001"],
    }


def test_extracts_only_allowed_tracked_modification(tmp_path: Path):
    ctx, run_ctx, patchlet = _ctx_and_run(tmp_path)
    (run_ctx.execution_root / "app.py").write_text("def main():\n    return 'new'\n", encoding="utf-8")

    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    assert result.accepted is True
    assert result.changed_paths == ["app.py"]
    assert result.hygiene_result["status"] == "CLEAN"
    assert "return 'new'" in (result.verification_root / "app.py").read_text(encoding="utf-8")


def test_excludes_unknown_regular_root_file(tmp_path: Path):
    ctx, run_ctx, patchlet = _ctx_and_run(tmp_path)
    (run_ctx.execution_root / "app.py").write_text("def main():\n    return 'new'\n", encoding="utf-8")
    (run_ctx.execution_root / ".json_validation.out").write_text("{}\n", encoding="utf-8")

    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    assert result.accepted is True
    assert result.hygiene_result["status"] == "DEBRIS_PRESENT"
    assert result.hygiene_result["candidate_scope"] == "raw_worker_sandbox"
    assert result.patch_manifest["candidate_scope"] == "patch_proposal"
    assert result.patch_validation["candidate_scope"] == "patch_proposal"
    assert result.reconstruction_result["candidate_scope"] == "clean_reconstruction"
    assert result.hygiene_result["debris_entries"][0]["path"] == ".json_validation.out"
    assert result.hygiene_result["debris_entries"][0]["classification"] == "SANDBOX_DEBRIS"
    assert not (result.verification_root / ".json_validation.out").exists()


def test_discards_non_allowlisted_tracked_modification(tmp_path: Path):
    ctx, run_ctx, patchlet = _ctx_and_run(tmp_path)
    (run_ctx.execution_root / "app.py").write_text("def main():\n    return 'new'\n", encoding="utf-8")
    (run_ctx.execution_root / "README.md").write_text("changed support\n", encoding="utf-8")

    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    assert result.accepted is True
    entry = next(row for row in result.hygiene_result["debris_entries"] if row["path"] == "README.md")
    assert entry["classification"] == "SANDBOX_DEBRIS"
    assert "README.md" not in result.diff_text


def test_discards_non_allowlisted_in_sandbox_symlink_addition(tmp_path: Path):
    ctx, run_ctx, patchlet = _ctx_and_run(tmp_path)
    (run_ctx.execution_root / "app.py").write_text("def main():\n    return 'new'\n", encoding="utf-8")
    (run_ctx.execution_root / "scratch-link").symlink_to(run_ctx.execution_root / "app.py")

    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    assert result.accepted is True
    entry = next(row for row in result.hygiene_result["debris_entries"] if row["path"] == "scratch-link")
    assert entry["classification"] == "SANDBOX_DEBRIS"
    assert not (result.verification_root / "scratch-link").exists()


def test_worker_staging_area_is_not_trusted(tmp_path: Path):
    ctx, run_ctx, patchlet = _ctx_and_run(tmp_path)
    (run_ctx.execution_root / "app.py").write_text("def main():\n    return 'new'\n", encoding="utf-8")
    (run_ctx.execution_root / "README.md").write_text("staged support change\n", encoding="utf-8")
    _git(run_ctx.execution_root, "add", "README.md")

    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    assert result.accepted is True
    assert "README.md" not in result.diff_text


def test_probe_runs_in_clean_candidate_without_sandbox_debris(tmp_path: Path):
    ctx, run_ctx, patchlet = _ctx_and_run(tmp_path)
    (run_ctx.execution_root / "app.py").write_text("def main():\n    return 'new'\n", encoding="utf-8")
    (run_ctx.execution_root / ".json_validation.out").write_text("{}\n", encoding="utf-8")
    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    probe = subprocess.run(
        ["python", "app.py"],
        cwd=result.verification_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.accepted is True
    assert probe.returncode == 0
    assert not (result.verification_root / ".json_validation.out").exists()


def test_probe_dependency_on_discarded_debris_fails_as_independent_proof(tmp_path: Path):
    ctx, run_ctx, patchlet = _ctx_and_run(tmp_path)
    (run_ctx.execution_root / "app.py").write_text("def main():\n    return 'new'\n", encoding="utf-8")
    (run_ctx.execution_root / ".json_validation.out").write_text("{}\n", encoding="utf-8")
    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    probe = subprocess.run(
        ["sh", "-c", "test -f .json_validation.out"],
        cwd=result.verification_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.accepted is True
    assert probe.returncode != 0


def test_debris_reference_never_changes_canonical_patch(tmp_path: Path):
    ctx, run_ctx, patchlet = _ctx_and_run(tmp_path)
    (run_ctx.execution_root / "app.py").write_text("def main():\n    return 'new'\n", encoding="utf-8")
    (run_ctx.execution_root / ".json_validation.out").write_text("{}\n", encoding="utf-8")
    report_path = run_ctx.execution_root / "worker-report.json"
    report_path.write_text('{"diagnostic": ".json_validation.out"}\n', encoding="utf-8")

    result = prepare_clean_patch_candidate(
        ctx=ctx,
        run_ctx=run_ctx,
        patchlet=patchlet,
        report_path=report_path,
    )

    assert result.accepted is True
    assert [row["path"] for row in result.patch_manifest["changed_paths"]] == ["app.py"]
    assert ".json_validation.out" not in result.diff_text
    assert "worker-report.json" not in result.diff_text


def test_effective_source_manifest_uses_clean_candidate_blob(tmp_path: Path):
    ctx, run_ctx, patchlet = _ctx_and_run(tmp_path)
    (run_ctx.execution_root / "app.py").write_text("def main():\n    return 'new'\n", encoding="utf-8")
    (run_ctx.execution_root / ".json_validation.out").write_text("{}\n", encoding="utf-8")
    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    manifest = write_independent_proof_effective_source_manifest(
        run_ctx=run_ctx,
        patchlet=patchlet,
        patch_manifest=result.patch_manifest,
        verification_root=result.verification_root,
        probe_plan={"probes": [{"probe_id": "GP001", "obligation_ids": ["PO001"], "command": "python app.py"}]},
    )

    assert manifest["candidate_scope"] == "clean_reconstruction"
    assert manifest["effective_sources"][0]["path"] == "app.py"
    assert manifest["effective_sources"][0]["blob_sha256"] != ""
    assert not any(row["path"] == ".json_validation.out" for row in manifest["effective_sources"])
