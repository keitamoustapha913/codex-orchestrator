from __future__ import annotations

import json
import subprocess
from pathlib import Path

from codex_orchestrator.git_guard import changed_between, snapshot_status
from codex_orchestrator.patchlet_run_context import PatchletRunContext
from codex_orchestrator.stages.run_patchlet import _quarantine_execution_root_scratch_files
from codex_orchestrator.validators.diff_validator import validate_changed_paths


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout


def _execution_ctx(tmp_path: Path) -> PatchletRunContext:
    target = tmp_path / "target"
    execution = tmp_path / "execution"
    run_dir = target / ".codex-orchestrator" / "runs" / "P0001_attempt1"
    for path in [target, execution, run_dir]:
        path.mkdir(parents=True, exist_ok=True)
    for name, content in {
        "gateway.routes": "/health -> legacy-health\n",
        "observability.ini": "metrics=disabled\n",
        "release.env": "release_channel=blue\n",
    }.items():
        (execution / name).write_text(content, encoding="utf-8")
    _git("init", cwd=execution)
    _git("add", ".", cwd=execution)
    _git("commit", "-m", "baseline", cwd=execution)
    return PatchletRunContext(
        target_root=target,
        execution_root=execution,
        artifact_root=target,
        workflow_dir=target / ".codex-orchestrator",
        reports_dir=target / ".codex-orchestrator" / "reports",
        probe_dir=target / ".artifacts" / "probes",
        runs_dir=target / ".codex-orchestrator" / "runs",
        run_dir=run_dir,
        is_worktree=True,
        worktree_path=execution,
    )


def _patchlet() -> dict:
    return {
        "patchlet_id": "P0001",
        "allowed_product_runtime_file": "gateway.routes",
        "allowed_artifact_dirs": [".artifacts/probes/", ".codex-orchestrator/runs/"],
    }


def _generic_execution_ctx(tmp_path: Path) -> PatchletRunContext:
    target = tmp_path / "target"
    execution = tmp_path / "execution"
    run_dir = target / ".codex-orchestrator" / "runs" / "P0100_attempt1"
    for path in [target, execution, run_dir]:
        path.mkdir(parents=True, exist_ok=True)
    for name, content in {
        "control.plan": "gate=legacy\n",
        "rollout.table": "track blue\n",
        "telemetry.flags": "metrics off\n",
        "ownership.record": "team unknown\n",
    }.items():
        (execution / name).write_text(content, encoding="utf-8")
    _git("init", cwd=execution)
    _git("add", ".", cwd=execution)
    _git("commit", "-m", "generic baseline", cwd=execution)
    (target / ".codex-orchestrator" / "decomposition").mkdir(parents=True, exist_ok=True)
    (target / ".codex-orchestrator" / "decomposition" / "patchlet_plan.json").write_text(
        json.dumps(
            {
                "patchlets": [
                    {
                        "patchlet_id": "P0100",
                        "allowed_product_runtime_file": "control.plan",
                        "allowed_artifact_dirs": [".artifacts/probes/", ".codex-orchestrator/runs/"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return PatchletRunContext(
        target_root=target,
        execution_root=execution,
        artifact_root=target,
        workflow_dir=target / ".codex-orchestrator",
        reports_dir=target / ".codex-orchestrator" / "reports",
        probe_dir=target / ".artifacts" / "probes",
        runs_dir=target / ".codex-orchestrator" / "runs",
        run_dir=run_dir,
        is_worktree=True,
        worktree_path=execution,
    )


def _generic_patchlet_from_plan(run_ctx: PatchletRunContext) -> dict:
    plan = json.loads((run_ctx.workflow_dir / "decomposition" / "patchlet_plan.json").read_text(encoding="utf-8"))
    return plan["patchlets"][0]


def test_unchanged_peer_product_file_present_in_execution_root_is_ignored(tmp_path: Path):
    run_ctx = _execution_ctx(tmp_path)

    result = _quarantine_execution_root_scratch_files(
        run_ctx,
        report_path=None,
        allowed_product_runtime_file="gateway.routes",
    )

    assert result == []
    sweep = json.loads((run_ctx.run_dir / "gates" / "root_scratch_sweep_result.json").read_text(encoding="utf-8"))
    assert sweep["rejected"] == []
    assert "observability.ini" in sweep["candidate_source"]["ignored_unchanged_peer_paths"]
    assert "release.env" in sweep["candidate_source"]["ignored_unchanged_peer_paths"]


def test_unchanged_multiple_peer_product_files_are_ignored(tmp_path: Path):
    run_ctx = _execution_ctx(tmp_path)

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="gateway.routes")

    quarantine = run_ctx.run_dir / "gates" / "scratch_artifact_quarantine_result.json"
    assert not quarantine.exists()


def test_changed_peer_product_file_is_rejected(tmp_path: Path):
    run_ctx = _execution_ctx(tmp_path)
    before = snapshot_status(run_ctx.execution_root)
    (run_ctx.execution_root / "release.env").write_text("release_channel=green\n", encoding="utf-8")

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="gateway.routes")
    after = snapshot_status(run_ctx.execution_root)
    diff_result = validate_changed_paths(changed_between(before, after), _patchlet())

    assert diff_result.allowed is False
    assert "release.env" in diff_result.unauthorized_paths


def test_deleted_peer_product_file_is_rejected(tmp_path: Path):
    run_ctx = _execution_ctx(tmp_path)
    before = snapshot_status(run_ctx.execution_root)
    (run_ctx.execution_root / "release.env").unlink()

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="gateway.routes")
    after = snapshot_status(run_ctx.execution_root)
    diff_result = validate_changed_paths(changed_between(before, after), _patchlet())

    assert diff_result.allowed is False
    assert "release.env" in diff_result.unauthorized_paths


def test_created_peer_product_file_is_rejected(tmp_path: Path):
    run_ctx = _execution_ctx(tmp_path)
    before = snapshot_status(run_ctx.execution_root)
    (run_ctx.execution_root / "policy.rules").write_text("default_action=deny\n", encoding="utf-8")

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="gateway.routes")
    after = snapshot_status(run_ctx.execution_root)
    diff_result = validate_changed_paths(changed_between(before, after), _patchlet())

    assert diff_result.allowed is False
    assert "policy.rules" in diff_result.unauthorized_paths


def test_allowed_product_file_is_not_rejected(tmp_path: Path):
    run_ctx = _execution_ctx(tmp_path)
    (run_ctx.execution_root / "gateway.routes").write_text("/health -> ready-health\n", encoding="utf-8")

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="gateway.routes")

    sweep = json.loads((run_ctx.run_dir / "gates" / "root_scratch_sweep_result.json").read_text(encoding="utf-8"))
    assert sweep["rejected"] == []


def test_allowed_product_file_still_goes_through_slice_boundary(tmp_path: Path):
    diff_result = validate_changed_paths(["gateway.routes"], _patchlet())

    assert diff_result.allowed is True
    assert diff_result.path_classifications["gateway.routes"] == "PRODUCT_FILE_CANDIDATE_FOR_SLICE_BOUNDARY_CHECK"


def test_product_runtime_paths_still_rejected_excludes_unchanged_peers(tmp_path: Path):
    run_ctx = _execution_ctx(tmp_path)
    (run_ctx.execution_root / "validate_report.out").write_text("valid\n", encoding="utf-8")

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="gateway.routes")

    quarantine = json.loads((run_ctx.run_dir / "gates" / "scratch_artifact_quarantine_result.json").read_text(encoding="utf-8"))
    assert quarantine["product_runtime_paths_still_rejected"] == []


def test_wrapper_gate_does_not_fail_on_unchanged_peer_files(tmp_path: Path):
    run_ctx = _execution_ctx(tmp_path)
    before = snapshot_status(run_ctx.execution_root)

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="gateway.routes")
    after = snapshot_status(run_ctx.execution_root)
    diff_result = validate_changed_paths(changed_between(before, after), _patchlet())

    assert diff_result.allowed is True
    assert diff_result.unauthorized_paths == []


def test_wrapper_gate_fails_on_changed_peer_product_file(tmp_path: Path):
    run_ctx = _execution_ctx(tmp_path)
    before = snapshot_status(run_ctx.execution_root)
    (run_ctx.execution_root / "observability.ini").write_text("metrics=enabled\n", encoding="utf-8")

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="gateway.routes")
    after = snapshot_status(run_ctx.execution_root)
    diff_result = validate_changed_paths(changed_between(before, after), _patchlet())

    assert diff_result.allowed is False
    assert "observability.ini" in diff_result.unauthorized_paths


def test_scratch_quarantine_runs_only_on_changed_or_untracked_files(tmp_path: Path):
    run_ctx = _execution_ctx(tmp_path)
    (run_ctx.execution_root / "validate_report.out").write_text("valid\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="gateway.routes")

    assert [row["original_path"] for row in result] == ["validate_report.out"]
    assert (run_ctx.execution_root / "observability.ini").exists()
    assert (run_ctx.execution_root / "release.env").exists()


def test_worker_scratch_directory_quarantine_preserves_one_allowed_file_rule(tmp_path: Path):
    run_ctx = _execution_ctx(tmp_path)
    before = snapshot_status(run_ctx.execution_root)
    (run_ctx.execution_root / "gateway.routes").write_text("/health -> ready-health\n", encoding="utf-8")
    scratch_dir = run_ctx.execution_root / "worker_scratch"
    scratch_dir.mkdir()
    (scratch_dir / "report.json").write_text('{"status": "pass"}\n', encoding="utf-8")

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="gateway.routes")
    after = snapshot_status(run_ctx.execution_root)
    diff_result = validate_changed_paths(changed_between(before, after), _patchlet())

    assert diff_result.allowed is True
    assert diff_result.product_runtime_paths == ["gateway.routes"]
    assert not (run_ctx.execution_root / "worker_scratch").exists()


def test_worker_scratch_directory_quarantine_does_not_allow_second_product_file(tmp_path: Path):
    run_ctx = _execution_ctx(tmp_path)
    before = snapshot_status(run_ctx.execution_root)
    (run_ctx.execution_root / "gateway.routes").write_text("/health -> ready-health\n", encoding="utf-8")
    (run_ctx.execution_root / "peer.record").write_text("owner=platform-release\n", encoding="utf-8")
    scratch_dir = run_ctx.execution_root / "worker_scratch"
    scratch_dir.mkdir()
    (scratch_dir / "report.json").write_text('{"status": "pass"}\n', encoding="utf-8")

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="gateway.routes")
    after = snapshot_status(run_ctx.execution_root)
    diff_result = validate_changed_paths(changed_between(before, after), _patchlet())

    assert diff_result.allowed is False
    assert "peer.record" in diff_result.unauthorized_paths


def test_worker_scratch_directory_quarantine_does_not_allow_product_directory(tmp_path: Path):
    run_ctx = _execution_ctx(tmp_path)
    before = snapshot_status(run_ctx.execution_root)
    (run_ctx.execution_root / "gateway.routes").write_text("/health -> ready-health\n", encoding="utf-8")
    product_dir = run_ctx.execution_root / "runtime"
    product_dir.mkdir()
    (product_dir / "state.cfg").write_text("state=dirty\n", encoding="utf-8")
    scratch_dir = run_ctx.execution_root / "worker_scratch"
    scratch_dir.mkdir()
    (scratch_dir / "report.json").write_text('{"status": "pass"}\n', encoding="utf-8")

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="gateway.routes")
    after = snapshot_status(run_ctx.execution_root)
    diff_result = validate_changed_paths(changed_between(before, after), _patchlet())

    assert diff_result.allowed is False
    assert "runtime" in diff_result.unauthorized_paths


def test_worker_scratch_directory_quarantine_does_not_mask_dirty_tracked_files(tmp_path: Path):
    run_ctx = _execution_ctx(tmp_path)
    before = snapshot_status(run_ctx.execution_root)
    (run_ctx.execution_root / "gateway.routes").write_text("/health -> ready-health\n", encoding="utf-8")
    (run_ctx.execution_root / "peer.record").write_text("owner=platform-release\n", encoding="utf-8")
    _git("add", "peer.record", cwd=run_ctx.execution_root)
    _git("commit", "-m", "track peer", cwd=run_ctx.execution_root)
    (run_ctx.execution_root / "peer.record").write_text("owner=platform\n", encoding="utf-8")
    scratch_dir = run_ctx.execution_root / "worker_scratch"
    scratch_dir.mkdir()
    (scratch_dir / "report.json").write_text('{"status": "pass"}\n', encoding="utf-8")

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="gateway.routes")
    after = snapshot_status(run_ctx.execution_root)
    diff_result = validate_changed_paths(changed_between(before, after), _patchlet())

    assert diff_result.allowed is False
    assert "peer.record" in diff_result.unauthorized_paths


def test_worker_scratch_directory_quarantine_does_not_mask_changed_peer_files(tmp_path: Path):
    run_ctx = _execution_ctx(tmp_path)
    before = snapshot_status(run_ctx.execution_root)
    (run_ctx.execution_root / "gateway.routes").write_text("/health -> ready-health\n", encoding="utf-8")
    (run_ctx.execution_root / "release.env").write_text("release_channel=green\n", encoding="utf-8")
    scratch_dir = run_ctx.execution_root / "worker_scratch"
    scratch_dir.mkdir()
    (scratch_dir / "report.json").write_text('{"status": "pass"}\n', encoding="utf-8")

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="gateway.routes")
    after = snapshot_status(run_ctx.execution_root)
    diff_result = validate_changed_paths(changed_between(before, after), _patchlet())

    assert diff_result.allowed is False
    assert "release.env" in diff_result.unauthorized_paths


def test_generic_unchanged_peer_files_with_different_names_extensions_are_ignored(tmp_path: Path):
    run_ctx = _generic_execution_ctx(tmp_path)

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="control.plan")

    sweep = json.loads((run_ctx.run_dir / "gates" / "root_scratch_sweep_result.json").read_text(encoding="utf-8"))
    assert sweep["rejected"] == []
    assert "rollout.table" in sweep["candidate_source"]["ignored_unchanged_peer_paths"]
    assert "telemetry.flags" in sweep["candidate_source"]["ignored_unchanged_peer_paths"]
    assert "ownership.record" in sweep["candidate_source"]["ignored_unchanged_peer_paths"]


def test_generic_changed_peer_files_with_different_names_extensions_are_rejected(tmp_path: Path):
    run_ctx = _generic_execution_ctx(tmp_path)
    before = snapshot_status(run_ctx.execution_root)
    (run_ctx.execution_root / "rollout.table").write_text("track green\n", encoding="utf-8")

    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="control.plan")
    after = snapshot_status(run_ctx.execution_root)
    diff_result = validate_changed_paths(changed_between(before, after), _generic_patchlet_from_plan(run_ctx))

    assert diff_result.allowed is False
    assert "rollout.table" in diff_result.unauthorized_paths


def test_generic_role_shaped_scratch_with_different_name_extension_is_quarantined(tmp_path: Path):
    run_ctx = _generic_execution_ctx(tmp_path)
    (run_ctx.execution_root / "verify_result.log").write_text("verified\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="control.plan")

    assert [row["original_path"] for row in result] == ["verify_result.log"]
    assert result[0]["reason"] == "role_shaped_result_verify_output"


def test_generic_random_scratch_looking_file_without_role_or_declaration_is_rejected(tmp_path: Path):
    run_ctx = _generic_execution_ctx(tmp_path)
    (run_ctx.execution_root / "notes_output.log").write_text("scratch\n", encoding="utf-8")

    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="control.plan")

    assert result == []
    quarantine = json.loads((run_ctx.run_dir / "gates" / "scratch_artifact_quarantine_result.json").read_text(encoding="utf-8"))
    assert quarantine["rejected"][0]["original_path"] == "notes_output.log"


def test_allowed_file_is_derived_from_patchlet_plan_not_filename_convention(tmp_path: Path):
    run_ctx = _generic_execution_ctx(tmp_path)
    patchlet = _generic_patchlet_from_plan(run_ctx)
    before = snapshot_status(run_ctx.execution_root)
    (run_ctx.execution_root / patchlet["allowed_product_runtime_file"]).write_text("gate=ready\n", encoding="utf-8")

    _quarantine_execution_root_scratch_files(
        run_ctx,
        report_path=None,
        allowed_product_runtime_file=patchlet["allowed_product_runtime_file"],
    )
    after = snapshot_status(run_ctx.execution_root)
    diff_result = validate_changed_paths(changed_between(before, after), patchlet)

    assert diff_result.allowed is True
    assert diff_result.product_runtime_paths == ["control.plan"]
