from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import read_json

from codex_orchestrator.errors import WorkerExecutionError
from codex_orchestrator.patchlet_run_context import build_patchlet_run_context
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.worker_capsule import build_worker_capsule, write_wrapper_gate_result


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


def _write_fake_codex(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def test_wrapper_gate_result_written_for_successful_patchlet(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")

    gate = read_json(ctx.paths.runs_dir / "P0001_attempt1" / "gates" / "wrapper_gate_result.json")
    assert gate["kind"] == "wrapper_gate_result"
    assert gate["accepted"] is True
    assert gate["worker_exit_gate"] == "pass"
    assert gate["report_gate"] == "pass"
    assert gate["probe_gate"] == "pass"


def test_wrapper_gate_result_written_for_worker_failed_patchlet(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    ctx = _compiled_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(fake_codex, "#!/usr/bin/env python3\nraise SystemExit(17)\n")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex")

    gate = read_json(ctx.paths.runs_dir / "P0001_attempt1" / "gates" / "wrapper_gate_result.json")
    assert gate["accepted"] is False
    assert gate["worker_exit_gate"] == "fail"
    assert gate["diff_gate"] == "not_run"
    assert gate["report_gate"] == "not_run"
    assert gate["probe_gate"] == "not_run"


def test_wrapper_gate_result_rejects_missing_stage_artifacts(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    patchlet = read_json(ctx.paths.patchlet_index)["patchlets"][0]
    run_ctx = build_patchlet_run_context(ctx, patchlet=patchlet, run_id="P0001_attempt1")
    capsule = build_worker_capsule(run_ctx, patchlet)
    run_next_patchlet(ctx, worker_mode="mock")
    (capsule.worker_stage_dir / "00_preflight.md").unlink()

    gate = write_wrapper_gate_result(
        ctx,
        capsule,
        run_ctx,
        worker_mode="mock",
        worker_exit_ok=True,
        diff_allowed=True,
        report_valid=True,
        probe_valid=True,
        next_state="PATCHLETS_READY",
        report_path=ctx.paths.reports_dir / "P0001.json",
    )

    assert gate["accepted"] is False
    assert gate["stage_gate"] == "fail"
    assert "missing worker_stage/00_preflight.md" in gate["reasons"]


def test_wrapper_gate_result_rejects_missing_report(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    patchlet = read_json(ctx.paths.patchlet_index)["patchlets"][0]
    run_ctx = build_patchlet_run_context(ctx, patchlet=patchlet, run_id="P0001_attempt1")
    capsule = build_worker_capsule(run_ctx, patchlet)
    run_next_patchlet(ctx, worker_mode="mock")
    (ctx.paths.reports_dir / "P0001.json").unlink()

    gate = write_wrapper_gate_result(
        ctx,
        capsule,
        run_ctx,
        worker_mode="mock",
        worker_exit_ok=True,
        diff_allowed=True,
        report_valid=True,
        probe_valid=True,
        next_state="PATCHLETS_READY",
        report_path=ctx.paths.reports_dir / "P0001.json",
    )

    assert gate["accepted"] is False
    assert gate["artifact_gate"] == "fail"
    assert "missing report" in gate["reasons"]


def test_wrapper_gate_result_rejects_missing_probe_artifacts(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    patchlet = read_json(ctx.paths.patchlet_index)["patchlets"][0]
    run_ctx = build_patchlet_run_context(ctx, patchlet=patchlet, run_id="P0001_attempt1")
    capsule = build_worker_capsule(run_ctx, patchlet)
    run_next_patchlet(ctx, worker_mode="mock")
    probe_run = ctx.paths.probe_dir / "P0001" / "run_001"
    (probe_run / "cleanup_proof.json").unlink()

    gate = write_wrapper_gate_result(
        ctx,
        capsule,
        run_ctx,
        worker_mode="mock",
        worker_exit_ok=True,
        diff_allowed=True,
        report_valid=True,
        probe_valid=False,
        next_state="FAILURE_CLASSIFICATION_REQUIRED",
        report_path=ctx.paths.reports_dir / "P0001.json",
        reasons=["missing probe artifact"],
    )

    assert gate["accepted"] is False
    assert gate["probe_gate"] == "fail"
    assert "missing probe artifact" in gate["reasons"]


def test_wrapper_gate_result_never_allows_blind_retry(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")

    gate = read_json(ctx.paths.runs_dir / "P0001_attempt1" / "gates" / "wrapper_gate_result.json")
    assert gate["blind_retry_allowed"] is False


def test_wrapper_gate_result_never_allows_validator_weakening(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")

    gate = read_json(ctx.paths.runs_dir / "P0001_attempt1" / "gates" / "wrapper_gate_result.json")
    assert gate["validator_weakening_allowed"] is False


def test_wrapper_gate_result_is_written_by_orchestrator_not_codex(
    git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    ctx = _compiled_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(
        fake_codex,
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path

run_dir = Path(os.environ["CXOR_RUN_DIR"])
gate_path = run_dir / "gates" / "wrapper_gate_result.json"
gate_path.parent.mkdir(parents=True, exist_ok=True)
gate_path.write_text(json.dumps({"accepted": True, "source": "fake-codex"}), encoding="utf-8")
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex")

    gate = read_json(ctx.paths.runs_dir / "P0001_attempt1" / "gates" / "wrapper_gate_result.json")
    assert gate["kind"] == "wrapper_gate_result"
    assert gate["accepted"] is False
    assert gate.get("source") != "fake-codex"


def test_run_manifest_references_wrapper_gate_result(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")

    run = read_json(ctx.paths.run_manifest)["runs"][-1]
    assert run["wrapper_gate_result"] == ".codex-orchestrator/runs/P0001_attempt1/gates/wrapper_gate_result.json"
