from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from codex_orchestrator.patchlet_run_context import build_patchlet_run_context
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.schema_validator import validate_json_file
from codex_orchestrator.workers.codex_exec import CodexExecWorker


def _setup_patchlet_ctx(git_repo: Path):
    ctx = resolve_target_repo(repo=git_repo)
    init_workflow(ctx, master=git_repo / "master_prompt.md", invocation_argv=["cxor", "init"])
    normalize_master_prompt(ctx)
    run_census(ctx)
    classify_evidence(ctx)
    build_inventory(ctx)
    extract_invariants(ctx)
    compile_patchlets(ctx)
    patchlet_index = json.loads(ctx.paths.patchlet_index.read_text(encoding="utf-8"))
    return ctx, patchlet_index["patchlets"][0]


def _write_fake_codex(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path

run_dir = Path(os.environ["CXOR_RUN_DIR"])
run_dir.mkdir(parents=True, exist_ok=True)
(run_dir / "env.json").write_text(json.dumps(dict(os.environ), indent=2, sort_keys=True), encoding="utf-8")
Path(os.environ["CXOR_REPORT_PATH"]).parent.mkdir(parents=True, exist_ok=True)
Path(os.environ["CXOR_REPORT_PATH"]).write_text(json.dumps({
    "schema_version": "1.0",
    "kind": "patchlet_report",
    "patchlet_id": os.environ["CXOR_PATCHLET_ID"],
    "status": "VERIFIED_NO_CHANGE_NEEDED",
    "changed_product_runtime_file": None,
    "changed_artifact_files": [],
    "probe_commands": ["python noop.py"],
    "deterministic_run_counts": {"baseline": "1/1", "proof_of_fix": "1/1", "negative_controls": "1/1"},
    "root_cause_classification": {
        "observed_failure": "no-op parity check",
        "immediate_cause": "no-op parity check",
        "why_immediate_cause_happened": "no-op parity check",
        "deeper_owner_boundary": "app.py",
        "producer_transformer_consumer_boundary": "producer app.py -> consumer probe",
        "not_downstream_of_unprobed_state_proof": "direct probe",
        "negative_control_proof": "negative control",
        "recursive_why_audit": ["why1"]
    },
    "before_after_state": [{"before": "ok", "after": "ok"}],
    "row_ledger": [],
    "trace_ledger": [],
    "cleanup_proof": "cleanup ok",
    "probe_artifact_refs": [],
    "acceptance_criteria_result": "pass"
}, indent=2), encoding="utf-8")
print(Path.cwd())
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _env_dump(ctx, patchlet: dict, *, execution_root: Path, artifact_root: Path, worktree_path: Path | None = None) -> dict:
    run_id = "P0001_attempt1"
    run_ctx = build_patchlet_run_context(
        ctx,
        patchlet=patchlet,
        run_id=run_id,
        execution_root=execution_root,
        artifact_root=artifact_root,
        is_worktree=worktree_path is not None,
        worktree_path=worktree_path,
    )
    CodexExecWorker().run_patchlet(ctx, patchlet, run_ctx=run_ctx)
    return json.loads((run_ctx.run_dir / "env.json").read_text(encoding="utf-8"))


def test_codex_worker_exposes_target_execution_and_artifact_roots_to_fake_binary(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch,
):
    ctx, patchlet = _setup_patchlet_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    env_dump = _env_dump(ctx, patchlet, execution_root=ctx.root, artifact_root=ctx.root)

    assert env_dump["CXOR_TARGET_ROOT"] == str(ctx.root)
    assert env_dump["CXOR_EXECUTION_ROOT"] == str(ctx.root)
    assert env_dump["CXOR_ARTIFACT_ROOT"] == str(ctx.root)


def test_codex_worker_exposes_patchlet_attempt_report_and_probe_paths(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch,
):
    ctx, patchlet = _setup_patchlet_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    env_dump = _env_dump(ctx, patchlet, execution_root=ctx.root, artifact_root=ctx.root)

    assert env_dump["CXOR_PATCHLET_ID"] == "P0001"
    assert env_dump["CXOR_ATTEMPT_ID"] == "P0001_attempt1"
    assert env_dump["CXOR_REPORTS_DIR"] == str(ctx.paths.reports_dir)
    assert env_dump["CXOR_REPORT_PATH"] == str(ctx.paths.reports_dir / "P0001.json")
    assert env_dump["CXOR_PROBE_ROOT"] == str(Path(env_dump["CXOR_WORKER_EVIDENCE_DIR"]) / patchlet["probe_ids"][0])
    assert env_dump["CXOR_RUNS_DIR"] == str(ctx.paths.runs_dir)
    assert env_dump["CXOR_RUN_DIR"] == str(ctx.paths.runs_dir / "P0001_attempt1")
    assert env_dump["CXOR_ALLOWED_PRODUCT_RUNTIME_FILE"] == "app.py"
    assert Path(env_dump["CXOR_WORKER_EVIDENCE_DIR"]).is_absolute()
    assert env_dump["CXOR_WORKER_EVIDENCE_DIR"] != env_dump["CXOR_WORKER_SCRATCH_DIR"]
    assert env_dump["CXOR_WORKER_EVIDENCE_CONTRACT"].endswith("/gates/worker_evidence_contract.json")


def test_codex_worker_environment_paths_point_to_target_artifact_root_in_worktree_mode(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch,
):
    ctx, patchlet = _setup_patchlet_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    execution_root = tmp_path / "execution-root"
    shutil.copytree(ctx.root, execution_root)

    env_dump = _env_dump(
        ctx,
        patchlet,
        execution_root=execution_root,
        artifact_root=ctx.root,
        worktree_path=execution_root,
    )

    assert env_dump["CXOR_TARGET_ROOT"] == str(ctx.root)
    assert env_dump["CXOR_EXECUTION_ROOT"] == str(execution_root)
    assert env_dump["CXOR_ARTIFACT_ROOT"] == str(ctx.root)
    assert env_dump["CXOR_REPORT_PATH"] == str(ctx.paths.reports_dir / "P0001.json")
    assert env_dump["CXOR_PROBE_ROOT"] == str(Path(env_dump["CXOR_WORKER_EVIDENCE_DIR"]) / patchlet["probe_ids"][0])
    assert env_dump["CXOR_RUN_DIR"] == str(ctx.paths.runs_dir / "P0001_attempt1")
    assert not env_dump["CXOR_WORKER_EVIDENCE_DIR"].startswith(str(execution_root) + os.sep)


def test_codex_worker_environment_does_not_point_artifacts_to_worktree_in_worktree_mode(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch,
):
    ctx, patchlet = _setup_patchlet_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    execution_root = tmp_path / "execution-root"
    shutil.copytree(ctx.root, execution_root)

    env_dump = _env_dump(
        ctx,
        patchlet,
        execution_root=execution_root,
        artifact_root=ctx.root,
        worktree_path=execution_root,
    )

    assert not env_dump["CXOR_REPORT_PATH"].startswith(str(execution_root))
    assert not env_dump["CXOR_PROBE_ROOT"].startswith(str(execution_root))
    assert not env_dump["CXOR_RUN_DIR"].startswith(str(execution_root))


def test_codex_worker_env_exposes_worker_stage_dir(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch,
):
    ctx, patchlet = _setup_patchlet_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    env_dump = _env_dump(ctx, patchlet, execution_root=ctx.root, artifact_root=ctx.root)

    assert env_dump["CXOR_WORKER_STAGE_DIR"] == str(ctx.paths.runs_dir / "P0001_attempt1" / "worker_stage")


def test_codex_worker_env_exposes_worker_memory_dir(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch,
):
    ctx, patchlet = _setup_patchlet_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    env_dump = _env_dump(ctx, patchlet, execution_root=ctx.root, artifact_root=ctx.root)

    run_dir = ctx.paths.runs_dir / "P0001_attempt1"
    assert env_dump["CXOR_WORKER_MEMORY_DIR"] == str(run_dir / "worker_memory")
    assert env_dump["CXOR_WORKER_HOOKS_DIR"] == str(run_dir / "worker_hooks")
    assert env_dump["CXOR_GATES_DIR"] == str(run_dir / "gates")
    assert env_dump["CXOR_DIAGNOSTICS_DIR"] == str(run_dir / "diagnostics")


def test_codex_worker_env_exposes_preflight_and_final_report_paths(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch,
):
    ctx, patchlet = _setup_patchlet_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    env_dump = _env_dump(ctx, patchlet, execution_root=ctx.root, artifact_root=ctx.root)

    stage_dir = ctx.paths.runs_dir / "P0001_attempt1" / "worker_stage"
    assert env_dump["CXOR_PREFLIGHT_PATH"] == str(stage_dir / "00_preflight.md")
    assert env_dump["CXOR_FINAL_REPORT_PATH"] == str(stage_dir / "05_final_report.md")


def test_codex_worker_env_capsule_paths_are_under_target_run_dir_not_worktree(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch,
):
    ctx, patchlet = _setup_patchlet_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    execution_root = tmp_path / "execution-root"
    shutil.copytree(ctx.root, execution_root)

    env_dump = _env_dump(
        ctx,
        patchlet,
        execution_root=execution_root,
        artifact_root=ctx.root,
        worktree_path=execution_root,
    )

    assert env_dump["CXOR_WORKER_STAGE_DIR"].startswith(str(ctx.paths.runs_dir))
    assert env_dump["CXOR_PREFLIGHT_PATH"].startswith(str(ctx.paths.runs_dir))
    assert env_dump["CXOR_FINAL_REPORT_PATH"].startswith(str(ctx.paths.runs_dir))
    assert not env_dump["CXOR_WORKER_STAGE_DIR"].startswith(str(execution_root))
    assert not env_dump["CXOR_PREFLIGHT_PATH"].startswith(str(execution_root))
    assert not env_dump["CXOR_FINAL_REPORT_PATH"].startswith(str(execution_root))


def test_real_worker_environment_exports_cxor_worker_scratch_dir(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch,
):
    ctx, patchlet = _setup_patchlet_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    env_dump = _env_dump(ctx, patchlet, execution_root=ctx.root, artifact_root=ctx.root)

    scratch = Path(env_dump["CXOR_WORKER_SCRATCH_DIR"])
    assert scratch.is_absolute()
    assert scratch == ctx.paths.runs_dir / "P0001_attempt1" / "worker_scratch"
    assert scratch.exists()


def test_real_worker_environment_routes_temp_and_cache_paths_to_worker_scratch(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch,
):
    ctx, patchlet = _setup_patchlet_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    env_dump = _env_dump(ctx, patchlet, execution_root=ctx.root, artifact_root=ctx.root)

    scratch = Path(env_dump["CXOR_WORKER_SCRATCH_DIR"])
    for name in ["TMPDIR", "TMP", "TEMP", "XDG_CACHE_HOME", "PYTHONPYCACHEPREFIX"]:
        value = Path(env_dump[name])
        assert value.is_absolute()
        assert value == scratch or scratch in value.parents
        assert value.exists()


def test_python_bytecode_cache_is_routed_outside_execution_root(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch,
):
    ctx, patchlet = _setup_patchlet_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    execution_root = tmp_path / "execution-root"
    shutil.copytree(ctx.root, execution_root)

    env_dump = _env_dump(
        ctx,
        patchlet,
        execution_root=execution_root,
        artifact_root=ctx.root,
        worktree_path=execution_root,
    )

    pycache_prefix = Path(env_dump["PYTHONPYCACHEPREFIX"])
    assert pycache_prefix.is_absolute()
    assert execution_root not in pycache_prefix.parents
    assert Path(env_dump["CXOR_WORKER_SCRATCH_DIR"]) in pycache_prefix.parents
    assert env_dump["PYTHONDONTWRITEBYTECODE"] == "1"


def test_worker_scratch_environment_artifact_validates(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch,
):
    ctx, patchlet = _setup_patchlet_ctx(git_repo)
    fake_codex = tmp_path / "codex"
    _write_fake_codex(fake_codex)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    _env_dump(ctx, patchlet, execution_root=ctx.root, artifact_root=ctx.root)

    artifact_path = ctx.paths.runs_dir / "P0001_attempt1" / "worker_scratch_environment.json"
    assert validate_json_file(artifact_path, "worker_scratch_environment.schema.json") == []
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["all_paths_absolute"] is True
    assert artifact["all_paths_inside_scratch_root"] is True
    assert artifact["directories_created"] is True
