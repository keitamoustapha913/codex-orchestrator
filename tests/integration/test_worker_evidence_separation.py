from __future__ import annotations

import subprocess
from pathlib import Path

import codex_orchestrator.worker_evidence as worker_evidence
from codex_orchestrator.integration_state import ensure_integration_state
from codex_orchestrator.jsonio import read_json
from codex_orchestrator.patch_promotion import prepare_clean_patch_candidate
from codex_orchestrator.patchlet_run_context import PatchletRunContext
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file
from codex_orchestrator.worker_evidence import create_worker_evidence_contract


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


def _case(tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "metrics.mjs").write_text("export const metric = 'old';\n", encoding="utf-8")
    (target / "README.md").write_text("support material\n", encoding="utf-8")
    _git(target, "init")
    _git(target, "config", "user.email", "test@example.invalid")
    _git(target, "config", "user.name", "Test User")
    _git(target, "add", ".")
    _git(target, "commit", "-m", "baseline")
    ctx = resolve_target_repo(repo=target)
    checkpoint = ensure_integration_state(ctx)["integration_sha"]
    sandbox = tmp_path / "attempt-sandbox"
    checkout = sandbox / "checkout"
    sandbox.mkdir()
    _git(target, "worktree", "add", "--detach", str(checkout), checkpoint)
    run_dir = target / ".codex-orchestrator" / "runs" / "P0003_attempt1"
    run_dir.mkdir(parents=True)
    run_ctx = PatchletRunContext(
        target_root=target,
        execution_root=checkout,
        artifact_root=target,
        workflow_dir=target / ".codex-orchestrator",
        probe_dir=target / ".artifacts" / "probes",
        reports_dir=target / ".codex-orchestrator" / "reports",
        runs_dir=target / ".codex-orchestrator" / "runs",
        run_dir=run_dir,
        is_worktree=True,
        worktree_path=checkout,
        execution_boundary_root=sandbox,
    )
    patchlet = {
        "patchlet_id": "P0003",
        "allowed_product_runtime_file": "metrics.mjs",
        "allowed_product_runtime_files": ["metrics.mjs"],
        "goal_item_ids": ["GI003"],
        "proof_obligation_ids": ["PO003"],
        "probe_ids": ["GP003"],
    }
    create_worker_evidence_contract(run_ctx, patchlet)
    return ctx, run_ctx, patchlet


def _write_product(run_ctx: PatchletRunContext) -> None:
    (run_ctx.execution_root / "metrics.mjs").write_text(
        "export const metric = 'new';\n",
        encoding="utf-8",
    )


def _write_checkout_local_probe_tree(run_ctx: PatchletRunContext) -> Path:
    root = run_ctx.execution_root / ".artifacts" / "probes" / "P0003" / "run_001"
    root.mkdir(parents=True)
    (root / "result.json").write_text('{"diagnostic": true}\n', encoding="utf-8")
    (root / "trace.log").write_text("trace\n", encoding="utf-8")
    return root


def _prepare(ctx, run_ctx, patchlet):
    _write_product(run_ctx)
    return prepare_clean_patch_candidate(
        ctx=ctx,
        run_ctx=run_ctx,
        patchlet=patchlet,
        report_path=None,
    )


def test_checkout_local_artifacts_are_plain_sandbox_debris(tmp_path: Path):
    ctx, run_ctx, patchlet = _case(tmp_path)
    _write_checkout_local_probe_tree(run_ctx)

    result = _prepare(ctx, run_ctx, patchlet)

    checkout_entries = [
        row for row in result.hygiene_result["entries"] if row["path"].startswith(".artifacts/")
    ]
    assert checkout_entries
    assert all(row["classification"] == "SANDBOX_DEBRIS" for row in checkout_entries)
    assert all(row["blocking"] is False for row in checkout_entries)


def test_checkout_local_probe_tree_does_not_enter_canonical_patch(tmp_path: Path):
    ctx, run_ctx, patchlet = _case(tmp_path)
    _write_checkout_local_probe_tree(run_ctx)

    result = _prepare(ctx, run_ctx, patchlet)

    assert result.changed_paths == ["metrics.mjs"]
    assert [row["path"] for row in result.patch_manifest["changed_paths"]] == ["metrics.mjs"]
    assert ".artifacts/probes" not in result.diff_text
    assert not (result.verification_root / ".artifacts").exists()


def test_checkout_local_probe_tree_does_not_block_promotion(tmp_path: Path):
    ctx, run_ctx, patchlet = _case(tmp_path)
    _write_checkout_local_probe_tree(run_ctx)

    result = _prepare(ctx, run_ctx, patchlet)

    assert result.accepted is True
    assert result.hygiene_result["promotion_blocked"] is False
    assert result.patch_validation["accepted"] is True
    assert result.reconstruction_result["accepted"] is True


def test_checkout_local_evidence_is_not_migrated(tmp_path: Path):
    ctx, run_ctx, patchlet = _case(tmp_path)
    _write_checkout_local_probe_tree(run_ctx)

    result = _prepare(ctx, run_ctx, patchlet)

    inventory = read_json(run_ctx.run_dir / "gates" / "worker_evidence_inventory.json")
    preservation = read_json(run_ctx.run_dir / "gates" / "worker_evidence_preservation_result.json")
    assert result.accepted is True
    assert inventory["entries"] == []
    assert inventory["captured_file_count"] == 0
    assert preservation["files"] == []
    assert not run_ctx.preserved_worker_evidence_dir.exists() or not any(
        run_ctx.preserved_worker_evidence_dir.rglob("*")
    )


def test_staged_diagnostic_evidence_remains_non_authoritative(tmp_path: Path):
    ctx, run_ctx, patchlet = _case(tmp_path)
    staged = run_ctx.worker_evidence_dir / "GP003" / "run_001"
    staged.mkdir(parents=True)
    (staged / "result.json").write_text('{"diagnostic": true}\n', encoding="utf-8")

    result = _prepare(ctx, run_ctx, patchlet)

    inventory_path = run_ctx.run_dir / "gates" / "worker_evidence_inventory.json"
    preservation_path = run_ctx.run_dir / "gates" / "worker_evidence_preservation_result.json"
    inventory = read_json(inventory_path)
    preservation = read_json(preservation_path)
    assert result.accepted is True
    assert inventory["captured_file_count"] == 1
    assert inventory["entries"][0]["classification"] == "SANDBOX_DEBRIS"
    assert inventory["entries"][0]["diagnostic_role"] == "PROBE_EVIDENCE"
    assert inventory["entries"][0]["capture_status"] == "CAPTURED"
    assert inventory["authoritative_proof"] is False
    assert inventory["promotion_blocked"] is False
    assert preservation["authoritative_proof"] is False
    assert preservation["promotion_blocked"] is False
    assert validate_json_file(inventory_path, "worker_evidence_inventory.schema.json") == []
    assert validate_json_file(preservation_path, "worker_evidence_preservation_result.schema.json") == []


def test_diagnostic_evidence_budget_truncation_is_non_blocking(tmp_path: Path):
    ctx, run_ctx, patchlet = _case(tmp_path)
    staged = run_ctx.worker_evidence_dir / "GP003" / "run_001"
    staged.mkdir(parents=True)
    for index in range(65):
        (staged / f"evidence-{index:02d}.txt").write_text(str(index), encoding="utf-8")

    result = _prepare(ctx, run_ctx, patchlet)

    inventory = read_json(run_ctx.run_dir / "gates" / "worker_evidence_inventory.json")
    assert result.accepted is True
    assert result.hygiene_result["promotion_blocked"] is False
    assert inventory["inventory_truncated"] is True
    assert inventory["captured_file_count"] == 64
    assert inventory["skipped_file_count"] == 1
    assert inventory["promotion_blocked"] is False


def test_diagnostic_evidence_preservation_failure_is_non_blocking(
    tmp_path: Path,
    monkeypatch,
):
    ctx, run_ctx, patchlet = _case(tmp_path)
    staged = run_ctx.worker_evidence_dir / "GP003" / "run_001"
    staged.mkdir(parents=True)
    (staged / "result.json").write_text('{"diagnostic": true}\n', encoding="utf-8")

    def fail_copy(*_args, **_kwargs):
        raise OSError("simulated diagnostic preservation failure")

    monkeypatch.setattr(worker_evidence.shutil, "copyfile", fail_copy)
    result = _prepare(ctx, run_ctx, patchlet)

    preservation = read_json(run_ctx.run_dir / "gates" / "worker_evidence_preservation_result.json")
    assert result.accepted is True
    assert result.hygiene_result["promotion_blocked"] is False
    assert preservation["preservation_complete"] is False
    assert preservation["promotion_blocked"] is False
    assert preservation["errors"]


def test_protected_file_copy_in_diagnostic_evidence_is_not_promoted(tmp_path: Path):
    ctx, run_ctx, patchlet = _case(tmp_path)
    staged = run_ctx.worker_evidence_dir / "GP003" / "run_001"
    staged.mkdir(parents=True)
    (staged / "README.md").write_bytes((run_ctx.execution_root / "README.md").read_bytes())

    result = _prepare(ctx, run_ctx, patchlet)

    inventory = read_json(run_ctx.run_dir / "gates" / "worker_evidence_inventory.json")
    assert result.accepted is True
    assert inventory["entries"][0]["capture_status"] == "SKIPPED_UNSAFE_OBJECT"
    assert inventory["entries"][0]["protected_copy_paths"] == ["README.md"]
    assert inventory["promotion_blocked"] is False
    assert result.changed_paths == ["metrics.mjs"]
    assert "README.md" not in result.diff_text
