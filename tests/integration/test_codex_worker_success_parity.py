from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from codex_orchestrator.patchlet_run_context import build_patchlet_run_context
from codex_orchestrator.patch_promotion import prepare_clean_patch_candidate
from codex_orchestrator.stages.build_inventory import build_inventory
from codex_orchestrator.stages.census import run_census
from codex_orchestrator.stages.classify_evidence import classify_evidence
from codex_orchestrator.stages.compile_patchlets import compile_patchlets
from codex_orchestrator.stages.extract_invariants import extract_invariants
from codex_orchestrator.stages.init import init_workflow
from codex_orchestrator.stages.normalize import normalize_master_prompt
from codex_orchestrator.target_repo import resolve_target_repo
from codex_orchestrator.validators.probe_artifact_validator import validate_probe_artifact_run
from codex_orchestrator.report_production import validate_task_completion_handoff
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


def _write_fake_codex_success_binary(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path

target_root = Path(os.environ["CXOR_TARGET_ROOT"])
execution_root = Path(os.environ["CXOR_EXECUTION_ROOT"])
artifact_root = Path(os.environ["CXOR_ARTIFACT_ROOT"])
workflow_dir = Path(os.environ["CXOR_WORKFLOW_DIR"])
probe_dir = Path(os.environ["CXOR_PROBE_DIR"])
reports_dir = Path(os.environ["CXOR_REPORTS_DIR"])
runs_dir = Path(os.environ["CXOR_RUNS_DIR"])
run_dir = Path(os.environ["CXOR_RUN_DIR"])
patchlet_id = os.environ["CXOR_PATCHLET_ID"]
attempt_id = os.environ["CXOR_ATTEMPT_ID"]
allowed_file = os.environ["CXOR_ALLOWED_PRODUCT_RUNTIME_FILE"]
handoff_path = Path(os.environ["CXOR_TASK_COMPLETION_HANDOFF_PATH"])
probe_root = Path(os.environ["CXOR_PROBE_ROOT"])

run_dir.mkdir(parents=True, exist_ok=True)
(run_dir / "env.json").write_text(json.dumps({
    "target_root": str(target_root),
    "execution_root": str(execution_root),
    "artifact_root": str(artifact_root),
    "workflow_dir": str(workflow_dir),
    "probe_dir": str(probe_dir),
    "reports_dir": str(reports_dir),
    "runs_dir": str(runs_dir),
    "run_dir": str(run_dir),
    "patchlet_id": patchlet_id,
    "attempt_id": attempt_id,
    "allowed_file": allowed_file,
    "handoff_path": str(handoff_path),
    "probe_root": str(probe_root)
}, indent=2, sort_keys=True), encoding="utf-8")

product_path = execution_root / allowed_file
product_path.write_text(
    "def main():\\n    return 'ok'\\n# fake codex success parity\\n",
    encoding="utf-8",
)

probe_run_dir = probe_root / "run_001"
probe_run_dir.mkdir(parents=True, exist_ok=True)
(probe_root / "probe.py").write_text("print('probe')\\n", encoding="utf-8")
(probe_run_dir / "row_ledger.jsonl").write_text(json.dumps({"row": 1}) + "\\n", encoding="utf-8")
(probe_run_dir / "trace_ledger.jsonl").write_text(json.dumps({"trace": 1}) + "\\n", encoding="utf-8")
(probe_run_dir / "before_state.json").write_text(json.dumps({"value": "before"}) + "\\n", encoding="utf-8")
(probe_run_dir / "after_state.json").write_text(json.dumps({"value": "after"}) + "\\n", encoding="utf-8")
(probe_run_dir / "cleanup_proof.json").write_text(json.dumps({"cleanup_passed": True}) + "\\n", encoding="utf-8")

handoff_path.parent.mkdir(parents=True, exist_ok=True)
handoff_path.write_text(json.dumps({
    "schema_version": "1.0",
    "kind": "task_worker_completion_handoff",
    "patchlet_id": patchlet_id,
    "status": "COMPLETE",
    "probe_commands": [f"python .artifacts/probes/{patchlet_id}/probe.py"],
    "deterministic_run_counts": {
        "baseline": "5/5",
        "proof_of_fix": "5/5",
        "negative_controls": "5/5"
    },
    "root_cause_classification": {
        "observed_failure": "baseline failed before allowed change",
        "immediate_cause": "allowed file lacked required parity change",
        "why_immediate_cause_happened": "fake codex parity path applies a minimal deterministic fix",
        "deeper_owner_boundary": allowed_file,
        "producer_transformer_consumer_boundary": f"producer {allowed_file} -> consumer probe",
        "not_downstream_of_unprobed_state_proof": "probe ran directly against the changed boundary",
        "negative_control_proof": "adjacent paths remained unchanged during parity run",
        "recursive_why_audit": ["why1", "why2", "why3"]
    },
    "before_after_state": [{"before": "old", "after": "new"}],
    "row_ledger": [],
    "trace_ledger": [],
    "cleanup_proof": "probe created isolated temp data and cleaned it",
    "proof_of_fix": {
        "summary": "direct probe passed after allowed change",
        "deterministic_run_count": "5/5"
    },
    "semantic_goal_results": [{
        "goal_item_id": "GI001",
        "status": "satisfied",
        "evidence": "GP001"
    }],
}, indent=2) + "\\n", encoding="utf-8")

print(str(execution_root))
print("fake codex success parity", file=__import__("sys").stderr)
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _run_fake_success(ctx, patchlet: dict, *, execution_root: Path, artifact_root: Path):
    run_ctx = build_patchlet_run_context(
        ctx,
        patchlet=patchlet,
        run_id="P0001_attempt1",
        execution_root=execution_root,
        artifact_root=artifact_root,
        is_worktree=True,
        worktree_path=execution_root,
    )
    result = CodexExecWorker().run_patchlet(ctx, patchlet, run_ctx=run_ctx)
    env_dump = json.loads((run_ctx.run_dir / "env.json").read_text(encoding="utf-8"))
    return run_ctx, result, env_dump


def test_fake_codex_success_payload_writes_valid_task_handoff_and_probe_artifacts(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch,
):
    ctx, patchlet = _setup_patchlet_ctx(git_repo)
    execution_root = tmp_path / "execution-root"
    shutil.copytree(ctx.root, execution_root)
    fake_codex = tmp_path / "codex"
    _write_fake_codex_success_binary(fake_codex)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    run_ctx, result, _ = _run_fake_success(ctx, patchlet, execution_root=execution_root, artifact_root=ctx.root)

    assert result.report_path == run_ctx.run_dir / "P0001.task_completion_handoff.json"
    assert result.report_path.exists()
    assert (run_ctx.worker_evidence_dir / "GP001" / "probe.py").exists()
    assert (run_ctx.worker_evidence_dir / "GP001" / "run_001" / "row_ledger.jsonl").exists()
    assert not (ctx.paths.probe_dir / "P0001" / "probe.py").exists()
    assert (run_ctx.run_dir / "env.json").exists()


def test_fake_codex_success_payload_passes_handoff_and_evidence_boundaries(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch,
):
    ctx, patchlet = _setup_patchlet_ctx(git_repo)
    execution_root = tmp_path / "execution-root"
    shutil.copytree(ctx.root, execution_root)
    fake_codex = tmp_path / "codex"
    _write_fake_codex_success_binary(fake_codex)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    run_ctx, result, _env = _run_fake_success(ctx, patchlet, execution_root=execution_root, artifact_root=ctx.root)
    prepare_clean_patch_candidate(
        ctx=ctx,
        run_ctx=run_ctx,
        patchlet=patchlet,
        report_path=result.report_path,
    )

    handoff_errors = validate_task_completion_handoff(result.report_path, patchlet_id="P0001")
    probe_result = validate_probe_artifact_run(ctx.paths.probe_dir / "P0001" / "run_001", patchlet_id="P0001")

    assert handoff_errors == []
    evidence_inventory = json.loads(
        (run_ctx.run_dir / "gates" / "worker_evidence_inventory.json").read_text(encoding="utf-8")
    )
    assert evidence_inventory["captured_file_count"] == 6
    assert probe_result["valid"] is True


def test_fake_codex_success_payload_changes_only_allowed_file_in_execution_root(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch,
):
    ctx, patchlet = _setup_patchlet_ctx(git_repo)
    execution_root = tmp_path / "execution-root"
    shutil.copytree(ctx.root, execution_root)
    fake_codex = tmp_path / "codex"
    _write_fake_codex_success_binary(fake_codex)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    _run_fake_success(ctx, patchlet, execution_root=execution_root, artifact_root=ctx.root)

    status = subprocess.run(
        ["git", "-C", str(execution_root), "status", "--porcelain"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    changed_paths = sorted(
        line[3:]
        for line in status.stdout.splitlines()
        if line.strip()
        and not line[3:].startswith(".artifacts/")
        and not line[3:].startswith(".codex-orchestrator/")
    )

    assert changed_paths == ["app.py"]


def test_fake_codex_success_payload_uses_only_cxor_environment_paths(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch,
):
    ctx, patchlet = _setup_patchlet_ctx(git_repo)
    execution_root = tmp_path / "execution-root"
    shutil.copytree(ctx.root, execution_root)
    fake_codex = tmp_path / "codex"
    _write_fake_codex_success_binary(fake_codex)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

    _, _, env_dump = _run_fake_success(ctx, patchlet, execution_root=execution_root, artifact_root=ctx.root)

    assert env_dump["target_root"] == str(ctx.root)
    assert env_dump["execution_root"] == str(execution_root)
    assert env_dump["artifact_root"] == str(ctx.root)
    assert env_dump["handoff_path"] == str(
        ctx.paths.runs_dir / "P0001_attempt1" / "P0001.task_completion_handoff.json"
    )
    assert env_dump["probe_root"] == str(Path(env_dump["probe_dir"]) / patchlet["probe_ids"][0])
    assert env_dump["run_dir"] == str(ctx.paths.runs_dir / "P0001_attempt1")
    assert Path(env_dump["handoff_path"]).exists()
    assert Path(env_dump["probe_root"]).exists()
    assert not env_dump["handoff_path"].startswith(str(execution_root))
    assert not env_dump["probe_root"].startswith(str(execution_root))
