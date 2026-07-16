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
from codex_orchestrator.worker_capsule import build_worker_capsule


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


def test_run_next_creates_worker_capsule_before_worker_execution(
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
capsule_path = run_dir / "worker_capsule.json"
snapshot = {
    "capsule_exists": capsule_path.exists(),
    "worker_memory_dir_exists": (run_dir / "worker_memory").is_dir(),
    "worker_stage_dir_exists": (run_dir / "worker_stage").is_dir(),
    "worker_hooks_dir_exists": (run_dir / "worker_hooks").is_dir(),
    "gates_dir_exists": (run_dir / "gates").is_dir(),
    "diagnostics_dir_exists": (run_dir / "diagnostics").is_dir()
}
(run_dir / "capsule_check.json").write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
raise SystemExit(17)
""",
    )
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    with pytest.raises(WorkerExecutionError):
        run_next_patchlet(ctx, worker_mode="real_codex")

    snapshot = read_json(ctx.paths.runs_dir / "P0001_attempt1" / "capsule_check.json")
    assert snapshot["capsule_exists"] is True
    assert snapshot["worker_memory_dir_exists"] is True
    assert snapshot["worker_stage_dir_exists"] is True
    assert snapshot["worker_hooks_dir_exists"] is True
    assert snapshot["gates_dir_exists"] is True
    assert snapshot["diagnostics_dir_exists"] is True


def test_failed_worker_attempt_still_has_worker_capsule(
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

    run_dir = ctx.paths.runs_dir / "P0001_attempt1"
    assert (run_dir / "worker_capsule.json").exists()
    assert (run_dir / "worker_memory").is_dir()
    assert (run_dir / "worker_stage").is_dir()
    assert (run_dir / "worker_hooks").is_dir()
    assert (run_dir / "gates").is_dir()
    assert (run_dir / "diagnostics").is_dir()


def test_worktree_run_creates_capsule_under_target_run_dir(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock", use_worktree=True)

    run_dir = ctx.paths.runs_dir / "P0001_attempt1"
    assert run_dir.exists()
    assert (run_dir / "worker_capsule.json").exists()


def test_capsule_creation_is_idempotent_for_existing_attempt(git_repo: Path):
    from codex_orchestrator.worker_capsule import build_worker_capsule, ensure_worker_capsule

    ctx = _compiled_ctx(git_repo)
    patchlet = read_json(ctx.paths.patchlet_index)["patchlets"][0]
    run_ctx = build_patchlet_run_context(ctx, patchlet=patchlet, run_id="P0001_attempt1")
    capsule = build_worker_capsule(run_ctx, patchlet)

    first = ensure_worker_capsule(ctx, capsule)
    second = ensure_worker_capsule(ctx, capsule)

    assert first["attempt_id"] == second["attempt_id"] == "P0001_attempt1"
    assert read_json(capsule.manifest_path)["attempt_id"] == "P0001_attempt1"


def test_run_manifest_references_worker_capsule_manifest_when_available(git_repo: Path):
    ctx = _compiled_ctx(git_repo)

    run_next_patchlet(ctx, worker_mode="mock")

    run = read_json(ctx.paths.run_manifest)["runs"][-1]
    assert run["worker_capsule_manifest"].endswith("worker_capsule.json")


def test_worker_capsule_requires_work_slice_id(git_repo: Path):
    ctx = _compiled_ctx(git_repo)
    patchlet = read_json(ctx.paths.patchlet_index)["patchlets"][0]
    patchlet.pop("work_slice_id")
    run_ctx = build_patchlet_run_context(
        ctx,
        patchlet=patchlet,
        run_id="P0001_attempt1",
    )

    with pytest.raises(ValueError, match="work_slice_id"):
        build_worker_capsule(run_ctx, patchlet)


def test_worker_prompt_never_emits_legacy_invariant_slice():
    import codex_orchestrator.stages.run_patchlet as run_patchlet_module
    import codex_orchestrator.worker_capsule as worker_capsule_module

    source = Path(worker_capsule_module.__file__).read_text(encoding="utf-8")
    source += Path(run_patchlet_module.__file__).read_text(encoding="utf-8")
    assert "legacy-" + "invariant-slice" not in source
