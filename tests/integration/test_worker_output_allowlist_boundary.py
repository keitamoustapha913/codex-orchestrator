from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path

from codex_orchestrator.integration_state import ensure_integration_state
from codex_orchestrator.jsonio import read_json
from codex_orchestrator.patch_promotion import (
    build_patch_proposal,
    inspect_worker_sandbox,
    prepare_clean_patch_candidate,
    reconstruct_clean_candidate,
)
from codex_orchestrator.patchlet_run_context import PatchletRunContext
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
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


def _boundary_fixture(tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    files = {
        "app.py": "CURRENT=legacy\nFUTURE=legacy\n\ndef main():\n    return 'legacy'\n",
        "peer.py": "PEER = 'original'\n",
        "README.md": "original documentation\n",
        "tests/test_app.py": "def test_original():\n    assert True\n",
    }
    for relative, content in files.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(target, "init")
    _git(target, "config", "user.email", "test@example.invalid")
    _git(target, "config", "user.name", "Test User")
    _git(target, "add", ".")
    _git(target, "commit", "-m", "baseline")
    ctx = resolve_target_repo(repo=target)
    checkpoint = ensure_integration_state(ctx)["integration_sha"]
    worker = tmp_path / "worker"
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
    )
    patchlet = {
        "patchlet_id": "P0001",
        "allowed_product_runtime_file": "app.py",
        "allowed_product_runtime_files": ["app.py"],
        "required_allowed_product_change": True,
        "goal_item_ids": ["GI001"],
        "proof_obligation_ids": ["PO001"],
        "probe_ids": ["GP001"],
    }
    return ctx, run_ctx, patchlet


def _compiled_ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    return ctx


def _prepare_with_allowed_change(ctx, run_ctx, patchlet):
    (run_ctx.execution_root / "app.py").write_text(
        "CURRENT=legacy\nFUTURE=legacy\n\ndef main():\n    return 'new'\n",
        encoding="utf-8",
    )
    return prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)


def _assert_debris_non_blocking(result, debris_path: str) -> None:
    assert result.accepted is True
    assert result.hygiene_result["promotion_blocked"] is False
    assert [row["path"] for row in result.patch_manifest["changed_paths"]] == ["app.py"]
    assert result.changed_paths == ["app.py"]
    assert "diff --git a/app.py b/app.py" in result.diff_text
    assert debris_path not in result.diff_text
    reconstructed_changes = _git(result.verification_root, "diff", "--name-only", "HEAD").splitlines()
    assert reconstructed_changes == ["app.py"]
    entry = next(row for row in result.hygiene_result["change_classification_ledger"] if row["path"] == debris_path)
    assert entry["classification"] == "SANDBOX_DEBRIS"
    assert entry["blocking"] is False
    assert entry["promotion_eligible"] is False
    assert entry["excluded_from_promotion"] is True


def test_dot_codex_directory_is_non_blocking_sandbox_debris(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    debris = run_ctx.execution_root / ".codex" / "runtime" / "state.json"
    debris.parent.mkdir(parents=True)
    debris.write_text("{}\n", encoding="utf-8")
    result = _prepare_with_allowed_change(ctx, run_ctx, patchlet)
    _assert_debris_non_blocking(result, ".codex/runtime/state.json")


def test_dot_agents_directory_is_non_blocking_sandbox_debris(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    debris = run_ctx.execution_root / ".agents" / "cache" / "trace.txt"
    debris.parent.mkdir(parents=True)
    debris.write_text("trace\n", encoding="utf-8")
    result = _prepare_with_allowed_change(ctx, run_ctx, patchlet)
    _assert_debris_non_blocking(result, ".agents/cache/trace.txt")


def test_arbitrary_hidden_file_is_non_blocking_sandbox_debris(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    (run_ctx.execution_root / ".worker-state").write_text("temporary\n", encoding="utf-8")
    result = _prepare_with_allowed_change(ctx, run_ctx, patchlet)
    _assert_debris_non_blocking(result, ".worker-state")


def test_arbitrary_untracked_file_is_non_blocking_sandbox_debris(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    (run_ctx.execution_root / "anything.cache").write_text("temporary\n", encoding="utf-8")
    result = _prepare_with_allowed_change(ctx, run_ctx, patchlet)
    _assert_debris_non_blocking(result, "anything.cache")


def test_arbitrary_untracked_directory_is_non_blocking_sandbox_debris(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    debris = run_ctx.execution_root / "cache" / "nested" / "value.bin"
    debris.parent.mkdir(parents=True)
    debris.write_bytes(b"cache")
    result = _prepare_with_allowed_change(ctx, run_ctx, patchlet)
    _assert_debris_non_blocking(result, "cache/nested/value.bin")


def test_changed_tracked_peer_file_is_discarded_as_sandbox_debris(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    (run_ctx.execution_root / "README.md").write_text("worker rewrite\n", encoding="utf-8")
    result = _prepare_with_allowed_change(ctx, run_ctx, patchlet)
    _assert_debris_non_blocking(result, "README.md")
    assert (result.verification_root / "README.md").read_text(encoding="utf-8") == "original documentation\n"


def test_deleted_tracked_peer_file_is_discarded_as_sandbox_debris(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    (run_ctx.execution_root / "README.md").unlink()
    result = _prepare_with_allowed_change(ctx, run_ctx, patchlet)
    _assert_debris_non_blocking(result, "README.md")
    assert (result.verification_root / "README.md").read_text(encoding="utf-8") == "original documentation\n"


def test_changed_protected_test_file_is_discarded_as_sandbox_debris(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    (run_ctx.execution_root / "tests/test_app.py").write_text("def test_worker():\n    assert False\n", encoding="utf-8")
    result = _prepare_with_allowed_change(ctx, run_ctx, patchlet)
    _assert_debris_non_blocking(result, "tests/test_app.py")
    assert "test_original" in (result.verification_root / "tests/test_app.py").read_text(encoding="utf-8")


def test_changed_peer_product_file_is_discarded_as_sandbox_debris(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    (run_ctx.execution_root / "peer.py").write_text("PEER = 'worker'\n", encoding="utf-8")
    result = _prepare_with_allowed_change(ctx, run_ctx, patchlet)
    _assert_debris_non_blocking(result, "peer.py")
    assert (result.verification_root / "peer.py").read_text(encoding="utf-8") == "PEER = 'original'\n"


def test_deleted_peer_product_file_is_discarded_as_sandbox_debris(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    (run_ctx.execution_root / "peer.py").unlink()
    result = _prepare_with_allowed_change(ctx, run_ctx, patchlet)
    _assert_debris_non_blocking(result, "peer.py")
    assert (result.verification_root / "peer.py").read_text(encoding="utf-8") == "PEER = 'original'\n"


def test_unknown_artifacts_tree_is_discarded_as_sandbox_debris(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    debris = run_ctx.execution_root / ".artifacts" / "unknown" / "probe.json"
    debris.parent.mkdir(parents=True)
    debris.write_text("{}\n", encoding="utf-8")
    result = _prepare_with_allowed_change(ctx, run_ctx, patchlet)
    _assert_debris_non_blocking(result, ".artifacts/unknown/probe.json")


def test_worker_staged_peer_file_is_discarded_as_sandbox_debris(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    (run_ctx.execution_root / "README.md").write_text("staged worker rewrite\n", encoding="utf-8")
    _git(run_ctx.execution_root, "add", "README.md")
    result = _prepare_with_allowed_change(ctx, run_ctx, patchlet)
    _assert_debris_non_blocking(result, "README.md")
    assert (result.verification_root / "README.md").read_text(encoding="utf-8") == "original documentation\n"


def test_non_allowlisted_symlink_inside_sandbox_is_discarded_as_debris(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    (run_ctx.execution_root / "local-link").symlink_to("app.py")
    result = _prepare_with_allowed_change(ctx, run_ctx, patchlet)
    _assert_debris_non_blocking(result, "local-link")


def test_all_non_allowlisted_entries_share_one_sandbox_debris_classification(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    (run_ctx.execution_root / ".hidden").write_text("hidden\n", encoding="utf-8")
    (run_ctx.execution_root / "README.md").write_text("worker rewrite\n", encoding="utf-8")
    (run_ctx.execution_root / "local-link").symlink_to("app.py")
    result = _prepare_with_allowed_change(ctx, run_ctx, patchlet)
    for path in (".hidden", "README.md", "local-link"):
        _assert_debris_non_blocking(result, path)
    debris_classes = {
        row["classification"]
        for row in result.hygiene_result["change_classification_ledger"]
        if not row["allowed_product_match"]
    }
    assert debris_classes == {"SANDBOX_DEBRIS"}


def test_sandbox_debris_never_sets_promotion_blocked(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    (run_ctx.execution_root / "random.tmp").write_text("temporary\n", encoding="utf-8")
    result = _prepare_with_allowed_change(ctx, run_ctx, patchlet)
    _assert_debris_non_blocking(result, "random.tmp")


def test_sandbox_debris_never_enters_canonical_patch(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    (run_ctx.execution_root / "generated.log").write_text("temporary\n", encoding="utf-8")
    result = _prepare_with_allowed_change(ctx, run_ctx, patchlet)
    _assert_debris_non_blocking(result, "generated.log")


def test_clean_reconstruction_contains_no_sandbox_debris(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    (run_ctx.execution_root / "worker-output.json").write_text("{}\n", encoding="utf-8")
    result = _prepare_with_allowed_change(ctx, run_ctx, patchlet)
    _assert_debris_non_blocking(result, "worker-output.json")
    assert not (result.verification_root / "worker-output.json").exists()


def test_debris_does_not_generate_repair_failure(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    (run_ctx.execution_root / "diagnostic.txt").write_text("non-authoritative\n", encoding="utf-8")
    result = _prepare_with_allowed_change(ctx, run_ctx, patchlet)
    _assert_debris_non_blocking(result, "diagnostic.txt")
    assert result.patch_validation["accepted"] is True
    assert result.patch_validation["errors"] == []


def test_required_allowed_file_change_must_exist(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)

    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    assert result.accepted is False
    assert result.hygiene_result["promotion_blocked"] is True
    violation = next(
        row for row in result.hygiene_result["allowed_path_violations"] if row["path"] == "app.py"
    )
    assert violation["classification"] == "ALLOWED_PRODUCT_PATH_VIOLATION"
    assert violation["blocking"] is True
    assert result.patch_manifest["changed_paths"] == []


def test_allowed_file_must_be_regular_file_or_valid_deletion(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    (run_ctx.execution_root / "app.py").unlink()

    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    assert result.accepted is True
    entry = next(row for row in result.hygiene_result["entries"] if row["path"] == "app.py")
    assert entry["classification"] == "ALLOWED_PRODUCT_CHANGE"
    assert entry["object_type"] == "missing"
    assert not (result.verification_root / "app.py").exists()


def test_allowed_file_symlink_is_rejected(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    (run_ctx.execution_root / "app.py").unlink()
    (run_ctx.execution_root / "app.py").symlink_to("peer.py")

    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    assert result.accepted is False
    entry = next(row for row in result.hygiene_result["entries"] if row["path"] == "app.py")
    assert entry["classification"] == "ALLOWED_PRODUCT_PATH_VIOLATION"
    assert entry["blocking"] is True
    assert result.patch_manifest["changed_paths"] == []


def test_allowed_file_fifo_is_rejected(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    (run_ctx.execution_root / "app.py").unlink()
    os.mkfifo(run_ctx.execution_root / "app.py")

    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    assert result.accepted is False
    entry = next(row for row in result.hygiene_result["entries"] if row["path"] == "app.py")
    assert entry["classification"] == "ALLOWED_PRODUCT_PATH_VIOLATION"
    assert entry["object_type"] == "fifo"
    assert entry["blocking"] is True


def test_allowed_file_socket_is_rejected(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    (run_ctx.execution_root / "app.py").unlink()
    worker_socket = socket.socket(socket.AF_UNIX)
    worker_socket.bind(str(run_ctx.execution_root / "app.py"))
    try:
        result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)
    finally:
        worker_socket.close()

    assert result.accepted is False
    entry = next(row for row in result.hygiene_result["entries"] if row["path"] == "app.py")
    assert entry["classification"] == "ALLOWED_PRODUCT_PATH_VIOLATION"
    assert entry["object_type"] == "socket"
    assert entry["blocking"] is True


def test_allowed_file_change_must_match_current_slice_boundary(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    patchlet["slice_change_boundary"] = {
        "allowed_changes": [{"key": "CURRENT", "old_value": "legacy", "new_value": "current"}],
        "forbidden_changes": [{"key": "FUTURE"}],
    }
    (run_ctx.execution_root / "app.py").write_text(
        "CURRENT=wrong\nFUTURE=legacy\n\ndef main():\n    return 'legacy'\n",
        encoding="utf-8",
    )

    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    assert result.accepted is False
    entry = next(row for row in result.hygiene_result["entries"] if row["path"] == "app.py")
    assert entry["classification"] == "ALLOWED_PRODUCT_PATH_VIOLATION"
    assert result.patch_validation["current_boundary_validation"] is False


def test_allowed_file_change_must_preserve_future_slice_boundaries(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    patchlet["slice_change_boundary"] = {
        "allowed_changes": [{"key": "CURRENT", "old_value": "legacy", "new_value": "current"}],
        "forbidden_changes": [{"key": "FUTURE"}],
    }
    (run_ctx.execution_root / "app.py").write_text(
        "CURRENT=current\nFUTURE=premature\n\ndef main():\n    return 'legacy'\n",
        encoding="utf-8",
    )

    result = prepare_clean_patch_candidate(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)

    assert result.accepted is False
    entry = next(row for row in result.hygiene_result["entries"] if row["path"] == "app.py")
    assert entry["classification"] == "ALLOWED_PRODUCT_PATH_VIOLATION"
    assert result.patch_validation["future_boundary_validation"] is False


def test_canonical_patch_must_contain_at_most_the_allowlisted_paths(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    (run_ctx.execution_root / "app.py").write_text("CURRENT=current\nFUTURE=legacy\n", encoding="utf-8")
    (run_ctx.execution_root / "peer.py").write_text("PEER = 'worker'\n", encoding="utf-8")
    hygiene = inspect_worker_sandbox(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)
    hygiene["include_paths"].append("peer.py")
    peer_entry = next(row for row in hygiene["entries"] if row["path"] == "peer.py")
    peer_entry["classification"] = "ALLOWED_PRODUCT_CHANGE"
    peer_entry["promotion_eligible"] = True
    peer_entry["excluded_from_promotion"] = False

    manifest, validation, _patch_path, patch_text = build_patch_proposal(
        ctx=ctx,
        run_ctx=run_ctx,
        patchlet=patchlet,
        hygiene_result=hygiene,
    )

    assert validation["accepted"] is False
    assert [row["path"] for row in manifest["changed_paths"]] == ["app.py"]
    assert "peer.py" not in patch_text


def test_clean_reconstruction_must_equal_canonical_patch(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    (run_ctx.execution_root / "app.py").write_text("CURRENT=current\nFUTURE=legacy\n", encoding="utf-8")
    hygiene = inspect_worker_sandbox(ctx=ctx, run_ctx=run_ctx, patchlet=patchlet, report_path=None)
    manifest, validation, patch_path, _patch_text = build_patch_proposal(
        ctx=ctx,
        run_ctx=run_ctx,
        patchlet=patchlet,
        hygiene_result=hygiene,
    )
    patch_path.write_text(patch_path.read_text(encoding="utf-8") + "\ninvalid trailing patch data\n", encoding="utf-8")

    reconstruction, _verification_root = reconstruct_clean_candidate(
        ctx=ctx,
        run_ctx=run_ctx,
        patchlet=patchlet,
        manifest=manifest,
        validation=validation,
        patch_path=patch_path,
    )

    assert reconstruction["accepted"] is False
    assert reconstruction["proposal_reconstructed_equality"] is False


def test_write_capable_worker_always_uses_disposable_sandbox(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=False)

    manifest = read_json(ctx.paths.run_manifest)
    run = next(row for row in manifest["runs"] if row.get("patchlet_id") == "P0001")
    assert run["execution_mode"] == "worktree"
    assert run["worktree"]["enabled"] is True


def test_write_capable_worker_cannot_select_direct_execution(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=False)

    manifest = read_json(ctx.paths.run_manifest)
    run = next(row for row in manifest["runs"] if row.get("patchlet_id") == "P0001")
    assert run["execution_mode"] != "direct"
    assert run["worktree"]["path"]


def test_direct_scratch_quarantine_artifact_is_never_written(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=False)

    gates = ctx.paths.runs_dir / "P0001_attempt1" / "gates"
    assert not (gates / "scratch_artifact_quarantine_result.json").exists()
    assert not (gates / "root_scratch_sweep_result.json").exists()
    source = Path("src/codex_orchestrator/stages/run_patchlet.py").read_text(encoding="utf-8")
    assert "_quarantine_execution_root_scratch_files" not in source


def test_root_filename_shape_does_not_affect_classification(tmp_path: Path):
    ctx, run_ctx, patchlet = _boundary_fixture(tmp_path)
    (run_ctx.execution_root / "P0001_report_check.json").write_text("{}\n", encoding="utf-8")

    result = _prepare_with_allowed_change(ctx, run_ctx, patchlet)

    _assert_debris_non_blocking(result, "P0001_report_check.json")
