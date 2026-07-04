from __future__ import annotations

import json
from pathlib import Path

from codex_orchestrator.patchlet_run_context import PatchletRunContext
from codex_orchestrator.stages.run_patchlet import _quarantine_execution_root_scratch_files


def _run_ctx(tmp_path: Path) -> PatchletRunContext:
    target = tmp_path / "target"
    execution = tmp_path / "execution"
    run_dir = target / ".codex-orchestrator" / "runs" / "P0001_attempt1"
    reports = target / ".codex-orchestrator" / "reports"
    probes = target / ".artifacts" / "probes"
    for path in [target, execution, run_dir, reports, probes]:
        path.mkdir(parents=True, exist_ok=True)
    return PatchletRunContext(
        target_root=target,
        execution_root=execution,
        artifact_root=target,
        workflow_dir=target / ".codex-orchestrator",
        reports_dir=reports,
        probe_dir=probes,
        runs_dir=target / ".codex-orchestrator" / "runs",
        run_dir=run_dir,
        is_worktree=True,
        worktree_path=execution,
    )


def _report(path: Path, changed_artifact_files: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"changed_artifact_files": changed_artifact_files}), encoding="utf-8")
    return path


def test_known_root_scratch_file_quarantined(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "report_validation.json").write_text("{}", encoding="utf-8")
    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")
    assert result[0]["original_path"] == "report_validation.json"
    assert not (run_ctx.execution_root / "report_validation.json").exists()


def test_unknown_json_root_scratch_file_quarantined_when_declared_by_worker_report(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "custom_check.json").write_text("{}", encoding="utf-8")
    report = _report(run_ctx.reports_dir / "P0001.json", ["custom_check.json"])
    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=report, allowed_product_runtime_file="service.cfg")
    assert result[0]["declared_by_report"] is True


def test_report_role_root_scratch_file_quarantined_without_declaration(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "report_validated.json").write_text("{}", encoding="utf-8")
    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")
    assert result[0]["original_path"] == "report_validated.json"
    assert result[0]["reason"] == "worker_root_scratch_artifact"


def test_unknown_root_scratch_file_rejected_when_not_declared(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "custom_check.json").write_text("{}", encoding="utf-8")
    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")
    assert result == []
    assert (run_ctx.execution_root / "custom_check.json").exists()


def test_root_product_file_still_rejected(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "other.cfg").write_text("x=1\n", encoding="utf-8")
    report = _report(run_ctx.reports_dir / "P0001.json", ["other.cfg"])
    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=report, allowed_product_runtime_file="service.cfg")
    assert result == []
    assert (run_ctx.execution_root / "other.cfg").exists()


def test_quarantined_scratch_file_recorded_in_gate_result(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / ".report_check.json").write_text("{}", encoding="utf-8")
    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")
    record = json.loads((run_ctx.run_dir / "quarantined_scratch" / "quarantined_scratch_files.json").read_text(encoding="utf-8"))
    assert record["quarantined_scratch_files"] == result


def test_quarantine_preserves_original_content(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / ".report_check.json").write_text('{"ok": true}', encoding="utf-8")
    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")
    quarantined = run_ctx.target_root / result[0]["quarantine_path"]
    assert quarantined.read_text(encoding="utf-8") == '{"ok": true}'


def test_quarantine_removes_root_scratch_from_worktree_before_diff_acceptance(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / ".report_check.json").write_text("{}", encoding="utf-8")
    _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")
    assert not (run_ctx.execution_root / ".report_check.json").exists()


def test_quarantine_does_not_weaken_one_file_rule(tmp_path: Path):
    run_ctx = _run_ctx(tmp_path)
    (run_ctx.execution_root / "service.cfg").write_text("status=ready\n", encoding="utf-8")
    result = _quarantine_execution_root_scratch_files(run_ctx, report_path=None, allowed_product_runtime_file="service.cfg")
    assert result == []
    assert (run_ctx.execution_root / "service.cfg").exists()
