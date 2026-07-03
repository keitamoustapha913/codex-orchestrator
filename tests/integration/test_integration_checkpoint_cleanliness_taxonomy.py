from __future__ import annotations

import json
from pathlib import Path

from conftest import read_json

from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.stages.run_patchlet import run_next_patchlet
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.integration_artifact_validator import validate_integration_artifacts
from codex_orchestrator.validators.schema_validator import validate_json_file


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


def _run_mock_no_change(ctx):
    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)


def test_checkpoint_includes_target_cleanliness_summary(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    _run_mock_no_change(ctx)

    checkpoint = read_json(ctx.paths.integration_checkpoints_dir / "P0001.json")
    assert checkpoint["target_working_tree_clean_after_checkpoint"] is True
    assert checkpoint["target_cleanliness"]["product_runtime_clean"] is True
    assert checkpoint["target_cleanliness"]["report_path"] == ".codex-orchestrator/integration/checkpoints/P0001_cleanliness.json"


def test_checkpoint_cleanliness_sidecar_is_written(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    _run_mock_no_change(ctx)

    sidecar = ctx.paths.integration_checkpoints_dir / "P0001_cleanliness.json"
    assert sidecar.exists()
    assert read_json(sidecar)["kind"] == "target_cleanliness_report"


def test_checkpoint_schema_accepts_cleanliness_summary(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    _run_mock_no_change(ctx)

    assert validate_json_file(ctx.paths.integration_checkpoints_dir / "P0001.json", "integration_checkpoint.schema.json") == []


def test_target_cleanliness_sidecar_schema_validates(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    _run_mock_no_change(ctx)

    assert validate_json_file(ctx.paths.integration_checkpoints_dir / "P0001_cleanliness.json", "target_cleanliness_report.schema.json") == []


def test_target_hygiene_gate_result_schema_validates(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    _run_mock_no_change(ctx)

    gate = ctx.paths.runs_dir / "P0001_attempt1" / "gates" / "target_hygiene_gate_result.json"
    assert validate_json_file(gate, "target_hygiene_gate_result.schema.json") == []


def test_checkpoint_with_removed_pycache_still_has_target_working_tree_clean_true(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    cache = git_repo / "__pycache__"
    cache.mkdir()
    (cache / "app.cpython-310.pyc").write_bytes(b"cache")

    _run_mock_no_change(ctx)

    checkpoint = read_json(ctx.paths.integration_checkpoints_dir / "P0001.json")
    sidecar = read_json(ctx.paths.integration_checkpoints_dir / "P0001_cleanliness.json")
    assert checkpoint["target_working_tree_clean_after_checkpoint"] is True
    assert sidecar["cache_artifacts_detected"] == ["__pycache__/app.cpython-310.pyc"]
    assert sidecar["cache_artifacts_removed"] == ["__pycache__/app.cpython-310.pyc"]
    assert not cache.exists()


def test_checkpoint_with_unknown_dirty_path_fails_before_valid_checkpoint(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    (git_repo / "tmp.txt").write_text("unknown", encoding="utf-8")

    try:
        run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)
    except Exception as exc:
        assert "target hygiene gate failed" in str(exc)
    else:
        raise AssertionError("expected target hygiene failure")
    assert (git_repo / "tmp.txt").exists()


def test_validate_integration_artifacts_accepts_checkpoint_after_cache_hygiene(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    cache = git_repo / "__pycache__"
    cache.mkdir()
    (cache / "app.cpython-310.pyc").write_bytes(b"cache")

    _run_mock_no_change(ctx)

    assert validate_integration_artifacts(git_repo)["valid"] is True


def test_validate_integration_artifacts_reports_missing_cleanliness_sidecar(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    _run_mock_no_change(ctx)
    (ctx.paths.integration_checkpoints_dir / "P0001_cleanliness.json").unlink()

    result = validate_integration_artifacts(git_repo)

    assert result["valid"] is False
    assert any("missing cleanliness sidecar" in error["message"] for error in result["errors"])


def test_validate_integration_artifacts_reports_cleanliness_sidecar_schema_errors(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    _run_mock_no_change(ctx)
    sidecar = ctx.paths.integration_checkpoints_dir / "P0001_cleanliness.json"
    payload = read_json(sidecar)
    payload.pop("kind")
    sidecar.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_integration_artifacts(git_repo)

    assert result["valid"] is False
    assert any(error["schema"] == "target_cleanliness_report.schema.json" for error in result["errors"])


def test_validate_integration_artifacts_reports_checkpoint_sidecar_patchlet_mismatch(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    _run_mock_no_change(ctx)
    sidecar = ctx.paths.integration_checkpoints_dir / "P0001_cleanliness.json"
    payload = read_json(sidecar)
    payload["patchlet_id"] = "P9999"
    sidecar.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_integration_artifacts(git_repo)

    assert result["valid"] is False
    assert any("patchlet_id mismatch" in error["message"] for error in result["errors"])


def test_validate_integration_artifacts_reports_checkpoint_sidecar_attempt_mismatch(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    _run_mock_no_change(ctx)
    sidecar = ctx.paths.integration_checkpoints_dir / "P0001_cleanliness.json"
    payload = read_json(sidecar)
    payload["attempt_id"] = "P9999_attempt1"
    sidecar.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_integration_artifacts(git_repo)

    assert result["valid"] is False
    assert any("attempt_id mismatch" in error["message"] for error in result["errors"])
